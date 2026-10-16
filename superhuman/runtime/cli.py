"""Unified execution commands. Installing, status and demo make no API requests."""
import argparse
import json
from pathlib import Path
from . import engine as r
from superhuman.projects import engine as p


def main():
    parser=argparse.ArgumentParser(description='Superhuman v1.8 unified execution')
    parser.add_argument('--db',default=str(r.DEFAULT_DB))
    parser.add_argument('--queue-db',default=str(r.DEFAULT_QUEUE))
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('status')
    sub.add_parser('demo')
    h=sub.add_parser('history');h.add_argument('--project-id');h.add_argument('--limit',type=int,default=100)
    j=sub.add_parser('enqueue');j.add_argument('--kind',choices=['research','collab'],required=True)
    j.add_argument('--project',required=True);j.add_argument('--title',required=True);j.add_argument('--details',default='')
    c=sub.add_parser('create');c.add_argument('--project',required=True);c.add_argument('--objective',required=True)
    c.add_argument('--details',default='');c.add_argument('--max-calls',type=int,default=12)
    for name in ('show','plan','approve-plan','recover','budget'):
        c=sub.add_parser(name);c.add_argument('id')
        if name=='plan':c.add_argument('--file',help='Manual plan JSON; omitting this makes a paid planning request')
        if name=='recover':c.add_argument('--older-than',type=int,default=3600)
        if name=='budget':c.add_argument('--max-calls',type=int,required=True)
    for name in ('approve','reject','retry'):
        c=sub.add_parser(name);c.add_argument('id');c.add_argument('task');c.add_argument('--note',default='')
    w=sub.add_parser('work');w.add_argument('--max-tasks',type=int,default=20)
    w.add_argument('--watch',action='store_true',help='Wait for work until interrupted or max-tasks reached')
    w.add_argument('--poll-seconds',type=float,default=5)
    w.add_argument('--no-legacy-import',action='store_true')
    sub.add_parser('import-queue')
    a=parser.parse_args();path=Path(a.db);qp=Path(a.queue_db)
    try:
        if a.command=='demo':
            from .demo import run
            result=run()
        elif a.command=='status':result=r.status(path,qp)
        elif a.command=='history':result=r.history(a.project_id,a.limit,path)
        elif a.command=='enqueue':result={'project_id':r.enqueue(a.kind,a.project,a.title,a.details,path)}
        elif a.command=='create':
            result={'project_id':p.create(a.project,a.objective,a.details,a.max_calls,path)}
            r.initialize(path);r.event('objective_created',result['project_id'],path=path)
        elif a.command=='show':result=p.get(a.id,path)
        elif a.command=='plan':
            result=p.set_plan(a.id,json.loads(Path(a.file).read_text(encoding='utf-8-sig')),path) if a.file else p.generate_plan(a.id,path)
            r.initialize(path);r.event('plan_prepared',a.id,path=path)
        elif a.command=='approve-plan':
            result=p.approve_plan(a.id,path);r.initialize(path);r.event('plan_approved',a.id,path=path)
        elif a.command in ('approve','reject'):result=r.review(a.id,a.task,a.command,a.note,path)
        elif a.command=='retry':result=r.retry(a.id,a.task,a.note,path)
        elif a.command=='recover':
            result={'interrupted_tasks':p.recover(a.id,a.older_than,path)}
            r.initialize(path);r.event('recovery_requested',a.id,detail=result,path=path)
        elif a.command=='budget':
            result=p.budget(a.id,a.max_calls,path)
            r.initialize(path);r.event('budget_changed',a.id,detail={'max_calls':a.max_calls},path=path)
        elif a.command=='import-queue':
            with r.worker_lock(path):result=r.import_queue(qp,path)
        elif a.command=='work':
            records=r.work(path,qp,a.max_tasks,a.watch,a.poll_seconds,not a.no_legacy_import,
                           report=lambda item:print(json.dumps(item),flush=True))
            result={'executions':len(records),'stopped':'limit reached' if len(records)==a.max_tasks else 'no ready work'}
        print(json.dumps(result,indent=2,ensure_ascii=False))
    except KeyboardInterrupt:
        print('Worker stopped. Inspect status; interrupted requests require recovery and explicit retry.')
        raise SystemExit(130)
    except Exception as exc:
        # Don't print provider exception bodies, which may contain source text/secrets.
        if isinstance(exc,(ValueError,FileNotFoundError)):
            parser.exit(1,str(exc)+'\n')
        parser.exit(1,type(exc).__name__+': command stopped. Inspect status before retrying paid work.\n')


if __name__=='__main__':main()
