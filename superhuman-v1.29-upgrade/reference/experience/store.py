"""Explicit associations. Existing department chats never acquire guessed projects."""
import json,time
from uuid import uuid4
from superhuman.projects import engine as p
from superhuman.dialogue import store as dialogue
from superhuman.team import store as team
from superhuman.departments.store import readonly,tables,rows
NAMES={'twin':'Mahnoor Twin','applications':'Jose','investors_grants':'Chris','legal_ops':'Sam','marketing':'Sarah','career_rnd':'Amelia','edsync_product':'James','endorsement':'Katherine'}
ROLES={'twin':'Coordinator & personal assistant','applications':'US Graduate Applications','investors_grants':'Investors, Grants & Partnerships','legal_ops':'Legal & Operations','marketing':'EdSync Sales & Marketing','career_rnd':'Career Algorithm R&D','edsync_product':'EdSync Product & University Pilots','endorsement':'UK Innovator Founder'}

def read(table,sql,args=(),path=p.DEFAULT_DB):
    with readonly(path) as db:return rows(db,sql,args) if table in tables(db) else []

def initialize(path=p.DEFAULT_DB):
    team.initialize(path);dialogue.initialize(path)
    with p.connect(path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS ux_migrations(id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS ux_rooms(thread_id TEXT PRIMARY KEY,employee TEXT NOT NULL,project_kind TEXT NOT NULL,project_id TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1);
        CREATE INDEX IF NOT EXISTS ux_room_project ON ux_rooms(project_kind,project_id);
        CREATE TABLE IF NOT EXISTS ux_suggestion_tasks(suggestion_id TEXT PRIMARY KEY,task_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS ux_message_states(source_id TEXT PRIMARY KEY,state TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS ux_meetings(id TEXT PRIMARY KEY,source_id TEXT NOT NULL,source_digest TEXT NOT NULL,title TEXT NOT NULL,original TEXT NOT NULL,zone TEXT NOT NULL,start_at TEXT NOT NULL,end_at TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'proposed',event_id TEXT,created_at TEXT NOT NULL);
        ''')
        if not db.execute("SELECT 1 FROM ux_migrations WHERE id='employee-names-128'").fetchone():
            for ident,name in NAMES.items():db.execute('UPDATE team_employees SET name=?,version=version+1 WHERE id=?',(name,ident))
            db.execute("INSERT INTO ux_migrations VALUES('employee-names-128')")

def room(ident,path=p.DEFAULT_DB):
    found=read('ux_rooms','SELECT * FROM ux_rooms WHERE thread_id=?',(ident,),path)
    return found[0] if found else None

def project(kind,ident,path=p.DEFAULT_DB):
    if kind=='team':
        value=team.project(ident,path)
        return dict(value,title=value['title'],scope=value['scope'])
    if kind=='canonical':
        value=p.get(ident,path)
        return dict(value,title=value['objective'],scope=value['workstream'])
    raise ValueError('Choose a project type')

def create(employee,title,kind='',project_id='',path=p.DEFAULT_DB):
    if employee not in NAMES:raise ValueError('Choose an employee')
    if bool(kind)!=bool(project_id):raise ValueError('Choose both project and project type')
    target=project(kind,project_id,path) if kind else None
    if target and employee not in ('twin',target['scope']):raise ValueError('Project chat belongs to its department or the Twin')
    # Twin is an employee identity; dialogue retains a valid workstream for legacy tooling.
    scope=target['scope'] if target else ('endorsement' if employee=='twin' else employee)
    initialize(path);ident=uuid4().hex;title=dialogue.text(title,180,'Room title')
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO dialogue_threads VALUES(?,?,?,20,0,?,?)',(ident,scope,title,p.stamp(),p.stamp()))
        db.execute('INSERT INTO ux_rooms VALUES(?,?,?,?,1)',(ident,employee,kind,project_id))
        dialogue.event(db,'room_created',ident,project_id=project_id or None,employee=employee,project_kind=kind)
    return ident

def link(ident,kind,project_id,path=p.DEFAULT_DB):
    target=project(kind,project_id,path);thread=dialogue.get(ident,path)
    if thread['scope']!=target['scope']:raise ValueError('Conversation and project must belong to the same department')
    initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM ux_rooms WHERE thread_id=?',(ident,)).fetchone():raise ValueError('This conversation already has an explicit room association')
        if db.execute("SELECT 1 FROM dialogue_turns WHERE thread_id=? AND status IN ('queued','running')",(ident,)).fetchone():raise ValueError('Wait for the pending reply before linking')
        if 'mail_reports' in tables(db) and db.execute('SELECT 1 FROM mail_reports WHERE thread_id=?',(ident,)).fetchone():raise ValueError('Private inbox reports stay in Inbox; start a project conversation instead')
        db.execute('INSERT INTO ux_rooms VALUES(?,?,?,?,1)',(ident,target['scope'],kind,project_id))
        dialogue.event(db,'conversation_project_linked',ident,project_id=project_id,project_kind=kind)

def project_rooms(kind,ident,path=p.DEFAULT_DB):
    return read('ux_rooms','SELECT d.*,r.employee,r.project_kind,r.project_id FROM ux_rooms r JOIN dialogue_threads d ON d.id=r.thread_id WHERE r.project_kind=? AND r.project_id=? ORDER BY d.updated_at DESC',(kind,ident),path)

def rooms(path=p.DEFAULT_DB):
    return read('ux_rooms','SELECT d.*,r.employee,r.project_kind,r.project_id FROM ux_rooms r JOIN dialogue_threads d ON d.id=r.thread_id ORDER BY d.updated_at DESC LIMIT 200',path=path)

def board(path=p.DEFAULT_DB):
    cfg=team.settings(path);employees={r['id']:r for r in team.employees(path)};tasks=team.tasks(path)
    heartbeat=read('hosted_worker','SELECT * FROM hosted_worker WHERE id=1',path=path)
    worker=heartbeat[0] if heartbeat else {}
    online=bool(worker.get('last_seen') and worker['last_seen']>time.time()-30 and worker.get('activity')!='stopped')
    results=[]
    for ident in NAMES:
        employee=employees.get(ident,{});assigned=[t for t in tasks if t['owner']==ident and t['state'] not in ('approved','cancelled','complete','completed')]
        running_ids={v['project_id'] for v in read('agentic_runs',"SELECT project_id FROM agentic_runs WHERE state='running'",path=path)}
        running=next((t for t in assigned if t['state']=='running' or t['run_id'] in running_ids),None)
        pending=next((t for t in assigned if t['state'] not in ('done',)),None)
        turns=read('ux_rooms',"SELECT t.id,t.status,t.thread_id FROM dialogue_turns t JOIN ux_rooms r ON r.thread_id=t.thread_id WHERE r.employee=? AND t.status IN ('running','queued') ORDER BY t.created_at LIMIT 1",(ident,),path)
        cycles=read('team_cycles',"SELECT id FROM team_cycles WHERE status='running' LIMIT 1",path=path) if ident=='twin' else []
        communications=read('comms_runs',"SELECT id,kind FROM comms_runs WHERE status='running' LIMIT 1",path=path) if ident=='twin' else []
        if employee.get('paused'):state,reason='paused','Employee paused by owner'
        elif worker.get('paused'):state,reason='paused','Worker paused'
        elif not online:state,reason='offline','No current worker heartbeat; saved assignment may be stale'
        elif running or cycles or communications or (turns and turns[0]['status']=='running'):state,reason='working',('Communications analysis / briefing is running' if communications else 'Twin coordination cycle is running' if cycles else 'Saved execution is running')
        elif cfg.get('hold'):state,reason='blocked',cfg['hold']
        elif any(t['state'] in ('needs_review','reviewing','awaiting_review','owner_review') for t in assigned):state,reason='reviewing','Output awaits review'
        elif any('blocked' in t['state'] or t['state'] in ('failed','interrupted','held','disputed') for t in assigned):state,reason='blocked','Open task for the saved blocker'
        elif pending or turns:
            from superhuman.team.work import gate
            good,why=gate(pending,path) if pending else (True,'')
            state,reason='waiting',why or 'Queued work; waiting for the supervised worker'
        else:state,reason='idle','No active assignment recorded'
        events=read('team_events','SELECT action,created_at FROM team_events WHERE actor=? ORDER BY seq DESC LIMIT 1',(ident,),path)
        results.append(dict(id=ident,name=NAMES[ident],role=ROLES[ident],state=state,reason=reason,task=running or pending,assignment=('Communications analysis / briefing' if communications else 'Twin coordination cycle' if cycles else ''),last=events[0] if events else None,online=online,worker_activity=worker.get('activity','unknown')))
    return results

def approve(sid,expected,project_id,title,instruction,path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        s=db.execute('SELECT s.*,r.employee,r.project_kind,r.project_id AS room_project FROM dialogue_suggestions s JOIN ux_rooms r ON r.thread_id=s.thread_id WHERE s.id=?',(sid,)).fetchone()
        if not s or s['proposal_hash']!=expected:raise ValueError('Suggestion changed; reload')
        old=db.execute('SELECT task_id FROM ux_suggestion_tasks WHERE suggestion_id=?',(sid,)).fetchone()
        if old:return old['task_id']
        if s['status']!='proposed':raise ValueError('Suggestion is no longer proposed')
        target=team.project(project_id,path)
        if target['status']!='active':raise ValueError('Choose an active governed project')
        if s['project_kind']=='team' and s['room_project']!=project_id:raise ValueError('A project room can only propose work for its linked project')
        if s['project_kind']=='canonical':raise ValueError('Adopt this execution project into a governed Team project before adding work')
        employee=target['scope'] if s['employee']=='twin' else s['employee']
        if employee!=target['scope']:raise ValueError('Choose a project in this employee’s department')
        tid=team.create_task(project_id,employee,title,instruction,'Produce a reviewable local draft; identify assumptions and sources.',risk='consequential',sensitivity='restricted',path=path,_db=db)
        db.execute('INSERT INTO ux_suggestion_tasks VALUES(?,?)',(sid,tid))
        db.execute("UPDATE dialogue_suggestions SET status='approved',decided_at=? WHERE id=?",(p.stamp(),sid))
    return tid
