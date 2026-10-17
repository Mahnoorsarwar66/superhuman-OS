"""Explicit department policies, durable cycles, atomic run allocation and audit."""
import json,sqlite3,time,hashlib
from uuid import uuid4
from superhuman.projects import engine as p
from superhuman.agentic import store as agent
from superhuman.departments.store import readonly,tables,rows

encode=agent.encode

def initialize(path=p.DEFAULT_DB):
    agent.initialize(path)
    with p.connect(path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS supervision_policies(
          scope TEXT PRIMARY KEY,mission TEXT NOT NULL,acceptance TEXT NOT NULL,
          mode TEXT NOT NULL,enabled INTEGER NOT NULL,interval_seconds INTEGER NOT NULL,
          event_trigger INTEGER NOT NULL,total_calls INTEGER NOT NULL,allocated_calls INTEGER NOT NULL,
          run_calls INTEGER NOT NULL,run_steps INTEGER NOT NULL,allowed_tools TEXT NOT NULL,
          required_tools TEXT NOT NULL,version INTEGER NOT NULL,next_due REAL NOT NULL,
          last_checked REAL NOT NULL DEFAULT 0,last_signature TEXT NOT NULL DEFAULT '',
          last_summary TEXT NOT NULL DEFAULT '',last_error TEXT NOT NULL DEFAULT '',
          hold INTEGER NOT NULL DEFAULT 0,force_review INTEGER NOT NULL DEFAULT 1,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS supervision_cycles(
          id TEXT PRIMARY KEY,scope TEXT NOT NULL,policy_version INTEGER NOT NULL,
          signature TEXT NOT NULL,status TEXT NOT NULL,summary TEXT NOT NULL DEFAULT '',
          response_json TEXT,error TEXT,allocated INTEGER NOT NULL,created_at TEXT NOT NULL,finished_at TEXT);
        CREATE TABLE IF NOT EXISTS supervision_proposals(
          id TEXT PRIMARY KEY,cycle_id TEXT NOT NULL,scope TEXT NOT NULL,target_key TEXT NOT NULL,
          target_json TEXT NOT NULL,title TEXT NOT NULL,instruction TEXT NOT NULL,
          status TEXT NOT NULL,project_id TEXT UNIQUE,version INTEGER NOT NULL,
          policy_version INTEGER NOT NULL,signature TEXT NOT NULL,
          allowed_tools TEXT NOT NULL,required_tools TEXT NOT NULL,run_calls INTEGER NOT NULL,
          run_steps INTEGER NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
          UNIQUE(scope,target_key));
        CREATE TABLE IF NOT EXISTS supervision_events(
          seq INTEGER PRIMARY KEY AUTOINCREMENT,scope TEXT NOT NULL,action TEXT NOT NULL,
          detail_json TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS supervision_rollback(
          project_id TEXT PRIMARY KEY,snapshot_json TEXT NOT NULL,restored INTEGER NOT NULL DEFAULT 0);
        ''')

def event(db,scope,action,detail=None):db.execute('INSERT INTO supervision_events(scope,action,detail_json,created_at) VALUES(?,?,?,?)',(scope,action,encode(detail or {}),p.stamp()))
def policy(scope,path=p.DEFAULT_DB):
    from superhuman.planning.store import scope_check
    scope_check(scope)
    with readonly(path) as db:
        if 'supervision_policies' not in tables(db):return None
        row=db.execute('SELECT * FROM supervision_policies WHERE scope=?',(scope,)).fetchone()
    if not row:return None
    result=dict(row)
    for key in ('allowed_tools','required_tools'):result[key]=json.loads(result[key])
    return result

def policies(path=p.DEFAULT_DB):
    with readonly(path) as db:
        if 'supervision_policies' not in tables(db):return []
        scopes=[r[0] for r in db.execute('SELECT scope FROM supervision_policies ORDER BY next_due,scope')]
    return [policy(scope,path) for scope in scopes]

def proposals(scope,path=p.DEFAULT_DB):
    with readonly(path) as db:
        if 'supervision_proposals' not in tables(db):return []
        return rows(db,'SELECT * FROM supervision_proposals WHERE scope=? ORDER BY created_at DESC,id',(scope,))

def proposal(ident,path=p.DEFAULT_DB):
    with readonly(path) as db:
        if 'supervision_proposals' not in tables(db):raise ValueError('Proposal not found')
        row=db.execute('SELECT * FROM supervision_proposals WHERE id=?',(ident,)).fetchone()
        if not row:raise ValueError('Proposal not found')
        return dict(row)

def history(scope,path=p.DEFAULT_DB):
    with readonly(path) as db:
        if 'supervision_cycles' not in tables(db):return [],[]
        return rows(db,'SELECT * FROM supervision_cycles WHERE scope=? ORDER BY created_at DESC LIMIT 30',(scope,)),rows(db,'SELECT * FROM supervision_events WHERE scope=? ORDER BY seq DESC LIMIT 60',(scope,))

def save(scope,expected,mission,acceptance,mode,enabled,interval_hours,event_trigger,total_calls,run_calls,run_steps,allowed_tools,required_tools=(),path=p.DEFAULT_DB):
    from superhuman.planning.store import scope_check,text
    from superhuman.agentic.tools import REGISTRY
    scope_check(scope);mission=text(mission,1500,'Mission',True);acceptance=text(acceptance,1500,'Acceptance criteria',True)
    if type(expected) is not int or expected<0 or mode not in ('review','auto') or type(enabled) is not bool or type(event_trigger) is not bool:raise ValueError('Invalid policy settings')
    if type(interval_hours) is not int or not 1<=interval_hours<=168 or type(total_calls) is not int or not 1<=total_calls<=1000 or type(run_calls) is not int or not 2<=run_calls<=20 or type(run_steps) is not int or not 2<=run_steps<=20:raise ValueError('Use 1–168 hours, 1–1000 total requests, 2–20 requests/steps per run')
    allowed=sorted(set(allowed_tools));required=sorted(set(required_tools))
    if not allowed or any(x not in REGISTRY for x in allowed) or any(x not in allowed for x in required) or 'inbox.queue_sync' in required:raise ValueError('Choose known permitted tools and valid required evidence')
    if 1+sum(REGISTRY[name].calls+1 for name in required)>run_calls or len(required)+1>run_steps:raise ValueError('Run allowance cannot fit the required tools and finish step')
    if enabled and mode=='auto' and not required:raise ValueError('Automatic starts require at least one required verified tool')
    initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT * FROM supervision_policies WHERE scope=?',(scope,)).fetchone()
        if (old['version'] if old else 0)!=expected:raise ValueError('Policy changed; reload before saving')
        allocated=old['allocated_calls'] if old else 0
        if total_calls<allocated:raise ValueError('Total request budget cannot be below already allocated requests')
        values=(scope,mission,acceptance,mode,int(enabled),interval_hours*3600,int(event_trigger),total_calls,allocated,run_calls,run_steps,encode(allowed),encode(required),expected+1,time.time(),p.stamp())
        db.execute('''INSERT INTO supervision_policies(scope,mission,acceptance,mode,enabled,interval_seconds,event_trigger,total_calls,allocated_calls,run_calls,run_steps,allowed_tools,required_tools,version,next_due,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(scope) DO UPDATE SET mission=excluded.mission,acceptance=excluded.acceptance,mode=excluded.mode,enabled=excluded.enabled,interval_seconds=excluded.interval_seconds,event_trigger=excluded.event_trigger,total_calls=excluded.total_calls,run_calls=excluded.run_calls,run_steps=excluded.run_steps,allowed_tools=excluded.allowed_tools,required_tools=excluded.required_tools,version=excluded.version,next_due=excluded.next_due,force_review=1,updated_at=excluded.updated_at''',values)
        event(db,scope,'policy_saved',{'version':expected+1,'enabled':enabled,'mode':mode,'total_calls':total_calls,'allowed_tools':allowed,'required_tools':required})
    return policy(scope,path)

def control(scope,expected,action,note='',path=p.DEFAULT_DB):
    from superhuman.planning.store import text
    note=text(note,2000,'Inspection note')
    if not policy(scope,path):raise ValueError('Configure the department policy first')
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM supervision_policies WHERE scope=?',(scope,)).fetchone()
        if not row or row['version']!=expected:raise ValueError('Policy changed; reopen it before acting')
        if action=='pause':db.execute('UPDATE supervision_policies SET enabled=0,version=version+1 WHERE scope=?',(scope,))
        elif action=='review_now':
            if not row['enabled']:raise ValueError('Enable the policy before requesting a review')
            if row['hold'] and not note:raise ValueError('Inspect the interrupted review and record a note before continuing')
            if db.execute("SELECT 1 FROM supervision_cycles WHERE scope=? AND status='running'",(scope,)).fetchone():raise ValueError('Wait for the current review to finish')
            db.execute("UPDATE supervision_policies SET hold=0,last_error='',force_review=1,next_due=?,version=version+1 WHERE scope=?",(time.time(),scope))
        else:raise ValueError('Unknown control')
        event(db,scope,action,{'note':note})

def fixed_budget(pid,maximum,path=p.DEFAULT_DB):
    with readonly(path) as db:
        if 'supervision_proposals' not in tables(db):return
        row=db.execute('SELECT run_calls FROM supervision_proposals WHERE project_id=?',(pid,)).fetchone()
        if row and maximum>row['run_calls']:raise ValueError('Supervised run limit is fixed at launch. Update the department policy for future work; this run cannot exceed its reserved allowance.')

def managed(pid,path=p.DEFAULT_DB):
    with readonly(path) as db:
        if 'supervision_proposals' not in tables(db):return None
        row=db.execute('SELECT * FROM supervision_proposals WHERE project_id=?',(pid,)).fetchone()
        return dict(row) if row else None

def managed_gate(pid,path=p.DEFAULT_DB):
    item=managed(pid,path)
    if not item:return True,''
    pol=policy(item['scope'],path)
    if not pol or not pol['enabled'] or pol['hold']:return False,'Department supervision is paused or needs inspection'
    with readonly(path) as db:
        budget=db.execute('SELECT max_calls,used_calls FROM projects WHERE id=?',(pid,)).fetchone()
    if not budget or max(budget['max_calls'],budget['used_calls'])>item['run_calls']:return False,'Run budget exceeds its reserved allowance; restore its original limit before continuing'
    contract='\n\nOwner mission: '+pol['mission']+'\nOwner acceptance criteria: '+pol['acceptance']+'\n'
    if contract not in item['instruction']:return False,'Department mission or acceptance criteria changed; inspect the earlier run before further work'
    if not set(json.loads(item['allowed_tools']))<=set(pol['allowed_tools']):return False,'A previously permitted tool was withdrawn; inspect and cancel this run or restore its grant'
    from .context import target_available
    return target_available(item['scope'],json.loads(item['target_json']),path,ignore_project=pid)

def recover(path=p.DEFAULT_DB):
    with readonly(path) as db:
        if 'supervision_cycles' not in tables(db):return 0
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        restore=db.execute('SELECT * FROM supervision_rollback WHERE restored=0').fetchall()
        for row in restore:
            old=json.loads(row['snapshot_json']);pid=row['project_id']
            state=old['run_state'] if old['run_state'] in ('completed','cancelled','interrupted','awaiting_permission','needs_review','budget_blocked','step_limit') else 'paused'
            db.execute('UPDATE agentic_runs SET state=?,version=version+1 WHERE project_id=?',(state,pid))
            db.execute("UPDATE project_tasks SET status=?,token=NULL,started=NULL WHERE project_id=? AND kind='agentic'",(old['task_status'],pid))
            db.execute('UPDATE projects SET status=? WHERE id=?',(old['project_status'],pid));db.execute('UPDATE supervision_rollback SET restored=1 WHERE project_id=?',(pid,))
        unfinished=db.execute("SELECT * FROM supervision_cycles WHERE status='running'").fetchall()
        for row in unfinished:
            db.execute("UPDATE supervision_cycles SET status='interrupted',error='Worker restarted; no automatic replay',finished_at=? WHERE id=?",(p.stamp(),row['id']))
            db.execute("UPDATE supervision_policies SET hold=1,last_error='Review interrupted by restart; inspect and explicitly request continuation',version=version+1 WHERE scope=?",(row['scope'],));event(db,row['scope'],'review_restart_no_replay',{'cycle_id':row['id']})
    return len(unfinished)

def quarantine_for_rollback(path=p.DEFAULT_DB):
    from superhuman.hosted import jobs
    jobs.pause(True,path);agent.recover(path)
    with readonly(path) as db:
        if 'supervision_policies' not in tables(db):return
    recover(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');db.execute('UPDATE supervision_policies SET enabled=0,version=version+1')
        found=rows(db,"SELECT s.project_id,p.status AS project_status,t.status AS task_status,r.state AS run_state FROM supervision_proposals s JOIN projects p ON p.id=s.project_id JOIN project_tasks t ON t.project_id=p.id JOIN agentic_runs r ON r.project_id=p.id WHERE t.id='final'")
        for row in found:
            if row['task_status']=='supervision_unavailable':continue
            db.execute('INSERT OR REPLACE INTO supervision_rollback VALUES(?,?,0)',(row['project_id'],encode(row)))
            db.execute("UPDATE agentic_runs SET state='paused',version=version+1 WHERE project_id=?",(row['project_id'],))
            db.execute("UPDATE projects SET status='dependency_blocked' WHERE id=?",(row['project_id'],))
            db.execute("UPDATE project_tasks SET status='supervision_unavailable',token=NULL WHERE project_id=? AND kind='agentic'",(row['project_id'],))
        event(db,'system','rollback_quarantine',{'runs':len(found)})
