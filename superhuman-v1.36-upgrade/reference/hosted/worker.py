"""Persistent supervised worker. Never automatically replays interrupted requests."""
import argparse
import json
import os
from pathlib import Path
import signal
import threading
from uuid import uuid4
from superhuman.runtime import engine as r
from superhuman.projects import engine as p
from . import jobs


def configured_client():
    from dotenv import load_dotenv
    load_dotenv()
    if not os.getenv('OPENAI_API_KEY'):return None
    from openai import OpenAI
    return OpenAI(max_retries=0,timeout=120)


def serve(path=p.DEFAULT_DB,queue_path=r.DEFAULT_QUEUE,poll_seconds=5,once=False,stop=None,client=None,report=None):
    if not 1<=poll_seconds<=60:raise ValueError('Polling interval must be 1 to 60 seconds')
    stop=stop or threading.Event();owner=uuid4().hex;activity={'value':'starting'}
    with r.worker_lock(path):
        jobs.initialize(path)
        from superhuman.repairs.recovery import recover
        recover(path)
        from superhuman.agentic.store import recover as recover_agentic
        recover_agentic(path)
        from superhuman.supervision.store import recover as recover_supervision
        recover_supervision(path)
        from superhuman.team.engine import recover as recover_team
        recover_team(path)
        from superhuman.milestones.engine import recover as recover_milestones
        recover_milestones(path)
        from superhuman.comms.engine import recover as recover_comms
        recover_comms(path)
        from superhuman.experience.store import initialize as initialize_experience
        initialize_experience(path)
        # dialogue-v111: the global lock excludes another active worker.
        from superhuman.dialogue import store as dialogue_store, engine as dialogue_engine
        dialogue_store.recover_running(path)
        last_was_chat = False
        last_was_supervisor = False
        last_was_plan = False
        last_was_mail = False
        from superhuman.mail import store as mail_store, providers as mail_providers
        mail_store.recover(path)
        def heartbeat():
            while not stop.is_set():
                jobs.pulse(owner,activity['value'],path)
                stop.wait(5)
        heart=threading.Thread(target=heartbeat,daemon=True);heart.start()
        result=None;actual=client
        try:
            while not stop.is_set():
                if jobs.worker_status(path)['paused']:
                    activity['value']='paused'
                else:
                    from superhuman.foundation.proactive import scan as proactive_scan
                    proactive_scan(path)
                    # Alternate bounded read cycles with model work. Do not put
                    # a network sync and a three-call task in the same shutdown window.
                    mail_result=None
                    if not last_was_mail:
                        activity['value']='reading_mail'
                        mail_result=mail_providers.run_sync(path)
                        if mail_result is None:
                            from superhuman.comms.providers import read_tick as read_comms
                            mail_result=read_comms(path)
                    last_was_mail=bool(mail_result)
                    if mail_result:
                        from superhuman.experience.calendar import collect as collect_invitations
                        collect_invitations(path)
                        result=mail_result
                        activity['value']='idle'
                        if report:report(mail_result)
                    else:
                        if actual is None:actual=configured_client()
                        if actual is None:activity['value']='api_key_required'
                        else:
                            from superhuman.team.budget import wrap as meter
                            actual=meter(actual,path)
                            activity['value']='working'
                            # Reconcile queued legacy jobs under the same scheduler lock.
                            r.import_queue(queue_path,path)
                            # Alternate conversation and project work when both are ready.
                            result = None
                            if not last_was_supervisor:
                                from superhuman.supervision.engine import tick as review_departments
                                from superhuman.team import store as team_store,engine as team_engine
                                from superhuman.comms.engine import tick as assistant_tick
                                result=assistant_tick(path,actual)
                                if result is None:
                                    from superhuman.milestones.engine import tick as milestone_tick
                                    result=milestone_tick(path,actual)
                                if result is None:result=team_engine.tick(path,actual) if team_store.enabled(path) else review_departments(path,actual)
                            if result is None and not last_was_chat:
                                result = dialogue_engine.run_turn(path,actual)
                            if result is None and not last_was_plan:
                                result=jobs.run_plan(path,actual)
                            if result is None:result=r.tick(path,client=actual)
                            if result is None and last_was_chat:
                                result=dialogue_engine.run_turn(path,actual)
                            if result is None and last_was_plan:
                                result=jobs.run_plan(path,actual)
                            last_was_plan = bool(result and 'error_type' in result and not result.get('task_id'))
                            last_was_chat = bool(result and result.get('conversation_turn_id'))
                            last_was_supervisor = bool(result and (result.get('supervision_cycle_id') or result.get('team_cycle_id') or result.get('comms_cycle_id')))
                            activity['value']='idle'
                            if result and report:report(result)
                jobs.pulse(owner,activity['value'],path)
                if once:break
                stop.wait(0.05 if result else poll_seconds)
                result=None
        finally:
            stop.set();heart.join(timeout=6);jobs.pulse(owner,'stopped',path)
            if client is None and actual is not None and hasattr(actual,'close'):actual.close()
    return result


def main():
    parser=argparse.ArgumentParser(description='Superhuman persistent hosted worker')
    parser.add_argument('--db',default=str(p.DEFAULT_DB));parser.add_argument('--queue-db',default=str(r.DEFAULT_QUEUE))
    parser.add_argument('--poll-seconds',type=float,default=5);parser.add_argument('--once',action='store_true')
    args=parser.parse_args();stop=threading.Event()
    for name in ('SIGINT','SIGTERM'):
        if hasattr(signal,name):signal.signal(getattr(signal,name),lambda *a:stop.set())
    try:serve(Path(args.db),Path(args.queue_db),args.poll_seconds,args.once,stop,report=lambda item:print(json.dumps(item),flush=True))
    except Exception as exc:
        print(json.dumps({'status':'worker_stopped','error_type':type(exc).__name__}),flush=True)
        raise SystemExit(1)


if __name__=='__main__':main()
