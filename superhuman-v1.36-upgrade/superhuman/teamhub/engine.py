"""Bounded routing over the existing dialogue worker; no second execution engine."""
import json
from uuid import uuid4
from superhuman.projects import engine as p
from superhuman.team import store as team
from superhuman.dialogue import store as d
from superhuman.experience import store as ux
from superhuman.milestones import store as ms
from . import store as s


def schema(trace,fallback):
    if trace.get('hub_stage')=='plan':
        return {**fallback,'properties':{**fallback['properties'],'requests':{'type':'array','items':{'type':'object','properties':{'employee':{'type':'string'},'question':{'type':'string'}},'required':['employee','question'],'additionalProperties':False}}},'required':fallback['required']+['requests']}
    if trace.get('hub_card'):
        return {'type':'object','properties':{'decision':{'type':'string','enum':['authorize','revise','owner']},'note':{'type':'string'}},'required':['decision','note'],'additionalProperties':False}
    return fallback

def parse(raw,scope,trace,path=p.DEFAULT_DB):
    from superhuman.dialogue.engine import parse as original
    if trace.get('hub_card'):
        value=json.loads(raw)
        if set(value)!= {'decision','note'} or value['decision'] not in ('authorize','revise','owner'):raise ValueError('Invalid Twin work-card review')
        note=d.text(value['note'],2000,'Twin review');trace['hub_card_decision']=dict(decision=value['decision'],note=note)
        return {'reply':note,'tasks':[]}
    if trace.get('hub_stage')!='plan':return original(raw,scope)
    value=json.loads(raw);requests=value.pop('requests',None)
    if not isinstance(requests,list) or len(requests)>2:raise ValueError('The lead may request at most two specialist contributions')
    c=s.channel(trace['hub_channel'],path);lead=ms.managed(c['project_id'],path)['lead'];members=s.channel_members(c,path);seen=set()
    for req in requests:
        if not isinstance(req,dict) or set(req)!= {'employee','question'} or req['employee'] not in members or req['employee']==lead or req['employee'] in seen:raise ValueError('Lead requested an unapproved or duplicate participant')
        req['question']=d.text(req['question'],1800,'Specialist question');seen.add(req['employee'])
    trace['hub_requests']=requests
    return original(json.dumps(value),scope)

def _queue(db,r,t,c,employee,stage,instruction,path):
    if employee not in s.channel_members(c,path):raise ValueError('Participant sharing is no longer approved')
    profile=next(e for e in team.employees(path) if e['id']==employee)
    if profile['paused']:raise ValueError(ux.NAMES[employee]+' is paused; resume the employee before retrying')
    used=db.execute('SELECT COUNT(*) FROM hub_steps s JOIN hub_rounds r ON r.id=s.round_id JOIN hub_topics t ON t.id=r.topic_id WHERE t.channel_id=?',(c['id'],)).fetchone()[0]
    if used>=c['max_calls']:raise ValueError('Channel reply allowance reached; review its limit before retrying')
    ident=uuid4().hex;turn=uuid4().hex;ordinal=db.execute('SELECT COUNT(*) FROM hub_steps WHERE round_id=?',(r['id'],)).fetchone()[0]+1
    scope=team.project(c['project_id'],path)['scope']
    db.execute('INSERT INTO dialogue_threads VALUES(?,?,?,1,0,?,?)',(ident,scope,t['title'],p.stamp(),p.stamp()))
    db.execute('INSERT INTO ux_rooms VALUES(?,?,?,?,1)',(ident,employee,'team',c['project_id']))
    db.execute("INSERT INTO dialogue_turns(id,thread_id,ordinal,submission_key,user_text,status,created_at) VALUES(?,?,1,?,?,'queued',?)",(turn,ident,'hub:'+uuid4().hex,instruction,p.stamp()))
    db.execute('INSERT INTO hub_steps VALUES(?,?,?,?,?,?)',(uuid4().hex,r['id'],ordinal,employee,stage,turn))
    db.execute("UPDATE hub_rounds SET status='working',error='',version=version+1 WHERE id=?",(r['id'],))
    team.event(db,employee,'channel_reply_queued',{'round_id':r['id'],'stage':stage,'turn_id':turn})

def advance(path=p.DEFAULT_DB):
    """Called under the one hosted worker lock. Reconcile one round, with no model/network call."""
    s.initialize(path)
    from .cards import reconcile
    reconcile(path)
    cfg=team.settings(path)
    if not cfg['enabled'] or cfg['hold']:return
    candidates=s.read("SELECT * FROM hub_rounds WHERE status IN ('queued','working') ORDER BY created_at,id LIMIT 30",path=path)
    for r in candidates:
        t=s.topic(r['topic_id'],path);c=s.channel(t['channel_id'],path);existing=s.steps(r['id'],path)
        if any(x['status'] in ('queued','running') for x in existing):continue
        try:
            if c['archived'] or team.project(c['project_id'],path)['status']!='active':raise ValueError('Project or channel paused; inspect before retrying')
            s.channel_members(c,path)
            if any(x['status']!='done' for x in existing):raise ValueError('A contribution failed or was interrupted. No automatic replay; review it before retrying')
            lead=ms.managed(c['project_id'],path)['lead']
            plan_trace=json.loads(d.turn(existing[0]['turn_id'],path)['context_json'] or '{}') if existing else {}
            with p.connect(path) as db:
                db.execute('BEGIN IMMEDIATE');cur=db.execute('SELECT * FROM hub_rounds WHERE id=?',(r['id'],)).fetchone()
                if not cur or cur['version']!=r['version']:continue
                if not existing:
                    _queue(db,r,t,c,r['target'] if r['mode']=='direct' else lead,'direct' if r['mode']=='direct' else 'plan',r['message'],path)
                elif existing[-1]['stage'] in ('direct','synthesis'):
                    db.execute("UPDATE hub_rounds SET status='done',version=version+1 WHERE id=?",(r['id'],))
                else:
                    requests=plan_trace.get('hub_requests',[])
                    if len(existing)-1<len(requests):
                        req=requests[len(existing)-1];_queue(db,r,t,c,req['employee'],'contribution',req['question'],path)
                    elif requests:
                        _queue(db,r,t,c,lead,'synthesis','Combine the actual contributions for the owner. Answer the original question, explain disagreements and next actions. Do not claim approval, research or execution that has not occurred.',path)
                    else:db.execute("UPDATE hub_rounds SET status='done',version=version+1 WHERE id=?",(r['id'],))
            return
        except ValueError as exc:
            with p.connect(path) as db:db.execute("UPDATE hub_rounds SET status='failed',error=?,version=version+1 WHERE id=? AND version=?",(str(exc)[:600],r['id'],r['version']))
            return

def quarantine(path=p.DEFAULT_DB):
    """Rollback must not leave queued channel/review calls running without their context guard."""
    s.initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        ids=[r[0] for r in db.execute('SELECT turn_id FROM hub_steps UNION SELECT turn_id FROM hub_card_reviews')]
        for ident in ids:db.execute("UPDATE dialogue_turns SET status='cancelled',error='Team upgrade rolled back; inspect before any new attempt',finished_at=? WHERE id=? AND status IN ('queued','running')",(p.stamp(),ident))
        db.execute("UPDATE hub_rounds SET status='cancelled',error='Upgrade rolled back; saved discussion retained',version=version+1 WHERE status IN ('queued','working')")
        db.execute("UPDATE hub_card_reviews SET status='cancelled' WHERE status='pending'")
