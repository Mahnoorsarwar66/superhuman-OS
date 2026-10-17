"""Persistent team ownership, governance, memory, inbox and lifecycle records."""
import hashlib,json,time
from contextlib import nullcontext
from datetime import date
from uuid import uuid4
from superhuman.projects import engine as p
from superhuman.agentic import store as agent
from superhuman.departments.store import readonly,tables,rows
encode=agent.encode
EMPLOYEES={
 'twin':('The Twin','Coordinate priorities, delegate, review internal work and represent owner-confirmed preferences.'),
 'endorsement':('Katherine','Develop evidence-backed endorsement drafts and business-plan arguments.'),
 'edsync_product':('James','Develop precise requirements, user journeys, pilots and acceptance criteria.'),
 'career_rnd':('Amelia','Research methods, datasets, algorithms and testable hypotheses.'),
 'marketing':('Sarah','Develop audience-specific positioning, campaigns and commercial drafts.'),
 'applications':('Jose','Prepare authentic, factually grounded application materials.'),
 'investors_grants':('Chris','Develop evidence-backed funding, partnership and investor materials.'),
 'legal_ops':('Sam','Organize facts, evidence, chronology and careful operational drafts.')}
PRIORITIES=('P0','P1','P2','P3','P4');RISKS=('routine','consequential','high_risk');SENSITIVITIES=('public','internal','confidential','restricted')

def text(value,maximum,label,required=False):
    from superhuman.planning.store import text as checked
    return checked(value,maximum,label,required)

def initialize(path=p.DEFAULT_DB):
    agent.initialize(path)
    with p.connect(path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS team_settings(id INTEGER PRIMARY KEY CHECK(id=1),enabled INTEGER NOT NULL DEFAULT 0,version INTEGER NOT NULL DEFAULT 1,model TEXT NOT NULL DEFAULT 'gpt-4o-mini',max_active INTEGER NOT NULL DEFAULT 2,last_signature TEXT NOT NULL DEFAULT '',next_due REAL NOT NULL DEFAULT 0,hold TEXT NOT NULL DEFAULT '');
        INSERT OR IGNORE INTO team_settings(id) VALUES(1);
        CREATE TABLE IF NOT EXISTS team_employees(id TEXT PRIMARY KEY,name TEXT NOT NULL,charter TEXT NOT NULL,paused INTEGER NOT NULL DEFAULT 0,allowed_tools TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS team_projects(id TEXT PRIMARY KEY,scope TEXT NOT NULL,title TEXT NOT NULL,objective TEXT NOT NULL,acceptance TEXT NOT NULL,priority TEXT NOT NULL,risk TEXT NOT NULL,sensitivity TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'active',version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS team_tasks(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,owner TEXT NOT NULL,title TEXT NOT NULL,instruction TEXT NOT NULL,acceptance TEXT NOT NULL,priority TEXT,risk TEXT,sensitivity TEXT,due TEXT NOT NULL DEFAULT '',deps TEXT NOT NULL DEFAULT '[]',state TEXT NOT NULL DEFAULT 'queued',run_id TEXT UNIQUE,parent_id TEXT,owner_grant INTEGER NOT NULL DEFAULT 0,version INTEGER NOT NULL DEFAULT 1,attempts INTEGER NOT NULL DEFAULT 0,max_calls INTEGER NOT NULL DEFAULT 12,max_steps INTEGER NOT NULL DEFAULT 16,cost_limit INTEGER NOT NULL DEFAULT 5000000,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(project_id,title));
        CREATE TABLE IF NOT EXISTS team_memory(id TEXT PRIMARY KEY,employee TEXT NOT NULL,kind TEXT NOT NULL,content TEXT NOT NULL,visibility TEXT NOT NULL,sensitivity TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'proposed',version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS team_skills(employee TEXT PRIMARY KEY,rules TEXT NOT NULL,examples TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS team_messages(id TEXT PRIMARY KEY,kind TEXT NOT NULL,content TEXT NOT NULL,expires REAL,status TEXT NOT NULL DEFAULT 'new',created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS team_requests(id TEXT PRIMARY KEY,task_id TEXT NOT NULL,kind TEXT NOT NULL,recipient TEXT NOT NULL DEFAULT '',payload TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open',response TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS team_cycles(id TEXT PRIMARY KEY,status TEXT NOT NULL,signature TEXT NOT NULL,response_json TEXT,error TEXT,created_at TEXT NOT NULL,finished_at TEXT);
        CREATE TABLE IF NOT EXISTS team_events(seq INTEGER PRIMARY KEY AUTOINCREMENT,actor TEXT NOT NULL,action TEXT NOT NULL,detail_json TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS team_rollback(run_id TEXT PRIMARY KEY,snapshot TEXT NOT NULL,restored INTEGER NOT NULL DEFAULT 0);
        ''')
        from superhuman.agentic.tools import REGISTRY
        allowed=[n for n,t in REGISTRY.items() if t.permission in ('read_workspace','create_output','read_web')]
        for ident,(name,charter) in EMPLOYEES.items():
            db.execute('INSERT OR IGNORE INTO team_employees(id,name,charter,allowed_tools,created_at) VALUES(?,?,?,?,?)',(ident,name,charter,encode(allowed+['team.handoff','team.challenge','team.remember']),p.stamp()))
            if ident!='twin':db.execute('INSERT OR IGNORE INTO team_skills(employee,rules) VALUES(?,?)',(ident,charter+' Use owner-confirmed writing preferences. Preserve facts, identify assumptions and adapt terminology to this department.'))
    from . import budget
    budget.initialize(path)

def event(db,actor,action,detail=None):db.execute('INSERT INTO team_events(actor,action,detail_json,created_at) VALUES(?,?,?,?)',(actor,action,encode(detail or {}),p.stamp()))
def settings(path=p.DEFAULT_DB):
    with readonly(path) as db:
        if 'team_settings' not in tables(db):return {'enabled':0,'version':0,'model':'gpt-4o-mini','max_active':2,'hold':'','last_signature':'','next_due':0}
        return dict(db.execute('SELECT * FROM team_settings WHERE id=1').fetchone())
def enabled(path=p.DEFAULT_DB):return bool(settings(path)['enabled'])
def employees(path=p.DEFAULT_DB):
    with readonly(path) as db:
        if 'team_employees' not in tables(db):return []
        return rows(db,'SELECT * FROM team_employees ORDER BY CASE WHEN id=\'twin\' THEN 0 ELSE 1 END,id')
def projects(path=p.DEFAULT_DB):
    with readonly(path) as db:return rows(db,'SELECT * FROM team_projects ORDER BY created_at DESC') if 'team_projects' in tables(db) else []
def tasks(path=p.DEFAULT_DB):
    with readonly(path) as db:return rows(db,'SELECT * FROM team_tasks ORDER BY created_at,id') if 'team_tasks' in tables(db) else []
def task(ident,path=p.DEFAULT_DB):
    with readonly(path) as db:
        if 'team_tasks' not in tables(db):raise ValueError('Team task not found')
        row=db.execute('SELECT * FROM team_tasks WHERE id=?',(ident,)).fetchone()
        if not row:raise ValueError('Team task not found')
        return dict(row)
def project(ident,path=p.DEFAULT_DB):
    item=next((r for r in projects(path) if r['id']==ident),None)
    if not item:raise ValueError('Team project not found')
    return item
def effective(item,path=p.DEFAULT_DB):
    parent=project(item['project_id'],path)
    return {'priority':item.get('priority') or parent['priority'],'risk':max((item.get('risk') or parent['risk'],parent['risk']),key=RISKS.index),'sensitivity':max((item.get('sensitivity') or parent['sensitivity'],parent['sensitivity']),key=SENSITIVITIES.index)}
def classification(priority,risk,sensitivity):
    if priority not in PRIORITIES or risk not in RISKS or sensitivity not in SENSITIVITIES:raise ValueError('Choose a valid priority, action risk and sensitivity')
def needs_owner(item,path=p.DEFAULT_DB):
    c=effective(item,path)
    sensitive_dependency=any(task(i,path)['owner']!=item['owner'] and effective(task(i,path),path)['sensitivity'] in ('confidential','restricted') for i in json.loads(item['deps']))
    return c['risk']!='routine' or c['sensitivity']=='restricted' or sensitive_dependency

def create_project(scope,title,objective,acceptance,priority='P2',risk='routine',sensitivity='internal',path=p.DEFAULT_DB):
    if scope not in EMPLOYEES or scope=='twin':raise ValueError('Choose one of the seven specialist departments')
    classification(priority,risk,sensitivity);title=text(title,180,'Title',True);objective=text(objective,2000,'Objective',True);acceptance=text(acceptance,2000,'Acceptance criteria',True)
    initialize(path);ident=uuid4().hex
    with p.connect(path) as db:
        db.execute('INSERT INTO team_projects(id,scope,title,objective,acceptance,priority,risk,sensitivity,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(ident,scope,title,objective,acceptance,priority,risk,sensitivity,p.stamp()));event(db,'owner','project_created',{'project_id':ident})
    return ident

def create_task(project_id,owner,title,instruction,acceptance,priority=None,risk=None,sensitivity=None,due='',deps=(),actor='owner',parent_id=None,path=p.DEFAULT_DB,_db=None):
    parent=project(project_id,path)
    if owner not in EMPLOYEES or owner=='twin':raise ValueError('Assign a specialist employee')
    classification(priority or parent['priority'],risk or parent['risk'],sensitivity or parent['sensitivity'])
    if actor!='owner':
        if RISKS.index(risk or parent['risk'])<RISKS.index(parent['risk']) or SENSITIVITIES.index(sensitivity or parent['sensitivity'])<SENSITIVITIES.index(parent['sensitivity']):raise ValueError('The Twin cannot lower inherited risk or sensitivity')
    title=text(title,180,'Title',True);instruction=text(instruction,5000,'Instructions',True);acceptance=text(acceptance,1500,'Acceptance criteria',True)
    if due:date.fromisoformat(due)
    if not isinstance(deps,(list,tuple)) or len(deps)>12 or len(set(deps))!=len(deps):raise ValueError('Invalid prerequisites')
    existing={r['id']:r for r in tasks(path)}
    if any(i not in existing for i in deps):raise ValueError('Prerequisite task not found')
    for i in deps:
        c=effective(existing[i],path)
        if SENSITIVITIES.index(c['sensitivity'])>SENSITIVITIES.index(sensitivity or parent['sensitivity']) or RISKS.index(c['risk'])>RISKS.index(risk or parent['risk']):raise ValueError('Prerequisite classification exceeds this task; raise its controls first')
    if actor!='owner' and len([r for r in existing.values() if r['project_id']==project_id])>=12:raise ValueError('Project task limit reached; owner decision required')
    ident=uuid4().hex
    with (p.connect(path) if _db is None else nullcontext(_db)) as db:
        if _db is None:db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM team_tasks WHERE project_id=? AND lower(trim(title))=lower(trim(?))',(project_id,title)).fetchone():raise ValueError('A task with this title already exists in the project')
        db.execute('INSERT INTO team_tasks(id,project_id,owner,title,instruction,acceptance,priority,risk,sensitivity,due,deps,parent_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(ident,project_id,owner,title,instruction,acceptance,priority,risk,sensitivity,due,encode(list(deps)),parent_id,p.stamp(),p.stamp()));event(db,actor,'task_created',{'task_id':ident,'owner':owner})
    return ident

def configure(expected,enabled_value,model,max_active=2,path=p.DEFAULT_DB):
    model=text(model,100,'Model',True)
    if type(enabled_value) is not bool or type(max_active) is not int or not 1<=max_active<=7:raise ValueError('Invalid team settings')
    initialize(path)
    from . import budget
    if enabled_value and not budget.ready(model,path):raise ValueError('Configure an active dollar budget and rate card before enabling the team')
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT version FROM team_settings WHERE id=1').fetchone()
        if row['version']!=expected:raise ValueError('Team settings changed; reload')
        db.execute('UPDATE team_settings SET enabled=?,model=?,max_active=?,version=version+1,next_due=0 WHERE id=1',(int(enabled_value),model,max_active));event(db,'owner','team_configured',{'enabled':enabled_value,'model':model,'max_active':max_active})

def update_project(ident,expected,priority,risk,sensitivity,status,path=p.DEFAULT_DB):
    classification(priority,risk,sensitivity)
    if status not in ('active','paused','complete'):raise ValueError('Invalid project state')
    with p.connect(path) as db:
        cur=db.execute('UPDATE team_projects SET priority=?,risk=?,sensitivity=?,status=?,version=version+1 WHERE id=? AND version=?',(priority,risk,sensitivity,status,ident,expected))
        if not cur.rowcount:raise ValueError('Project changed; reload')
        # Owner grants cannot silently carry over to a new risk classification.
        db.execute('UPDATE team_tasks SET owner_grant=0,version=version+1 WHERE project_id=?',(ident,));event(db,'owner','project_governance_changed',{'project_id':ident})

def employee_control(ident,expected,paused,charter,allowed,path=p.DEFAULT_DB):
    from superhuman.agentic.tools import REGISTRY
    if ident not in EMPLOYEES or any(t not in REGISTRY for t in allowed):raise ValueError('Invalid employee/tools')
    charter=text(charter,3000,'Charter',True)
    with p.connect(path) as db:
        cur=db.execute('UPDATE team_employees SET paused=?,charter=?,allowed_tools=?,version=version+1 WHERE id=? AND version=?',(int(paused),charter,encode(sorted(set(allowed))),ident,expected))
        if not cur.rowcount:raise ValueError('Employee changed; reload')
        event(db,'owner','employee_updated',{'employee':ident,'paused':paused})

def add_message(kind,content,expires=None,path=p.DEFAULT_DB):
    if kind not in ('instruction','temporary_constraint','preference','decision','priority_change'):raise ValueError('Unknown update type')
    content=text(content,6000,'Update',True)
    if kind=='temporary_constraint' and (not isinstance(expires,(int,float)) or not time.time()<expires<=time.time()+90*86400):raise ValueError('Set an expiry within 90 days for a temporary constraint')
    initialize(path);ident=uuid4().hex
    with p.connect(path) as db:db.execute('INSERT INTO team_messages(id,kind,content,expires,created_at) VALUES(?,?,?,?,?)',(ident,kind,content,expires,p.stamp()));db.execute('UPDATE team_settings SET next_due=0 WHERE id=1');event(db,'owner','twin_update',{'message_id':ident,'kind':kind})
    return ident

def messages(path=p.DEFAULT_DB):
    with readonly(path) as db:return rows(db,'SELECT * FROM team_messages WHERE expires IS NULL OR expires>? ORDER BY created_at DESC LIMIT 30',(time.time(),)) if 'team_messages' in tables(db) else []
def add_memory(employee,kind,content,visibility='department',sensitivity='internal',path=p.DEFAULT_DB):
    if employee not in EMPLOYEES or kind not in ('fact','preference','decision','lesson') or visibility not in ('department','shared','twin_private') or sensitivity not in SENSITIVITIES:raise ValueError('Invalid memory classification')
    if visibility=='twin_private' and employee!='twin':raise ValueError('Private personal memory belongs to the Twin')
    if visibility=='shared' and sensitivity in ('confidential','restricted'):raise ValueError('Sensitive memory requires explicit department boundaries')
    initialize(path);ident=uuid4().hex
    with p.connect(path) as db:db.execute('INSERT INTO team_memory(id,employee,kind,content,visibility,sensitivity,created_at) VALUES(?,?,?,?,?,?,?)',(ident,employee,kind,text(content,4000,'Memory',True),visibility,sensitivity,p.stamp()))
    return ident

def confirm_memory(ident,expected,approve,path=p.DEFAULT_DB):
    with p.connect(path) as db:
        cur=db.execute("UPDATE team_memory SET status=?,version=version+1 WHERE id=? AND version=? AND status='proposed'",('confirmed' if approve else 'rejected',ident,expected))
        if not cur.rowcount:raise ValueError('Memory changed; reload')
        event(db,'owner','memory_reviewed',{'memory_id':ident,'approved':approve})
def memory(employee,sensitivity='internal',path=p.DEFAULT_DB):
    if employee not in EMPLOYEES or sensitivity not in SENSITIVITIES:raise ValueError('Invalid memory access')
    with readonly(path) as db:
        if 'team_memory' not in tables(db):return []
        values=rows(db,"SELECT * FROM team_memory WHERE status='confirmed' AND (employee=? OR visibility='shared') ORDER BY created_at DESC LIMIT 100",(employee,))
    return [r for r in values if SENSITIVITIES.index(r['sensitivity'])<=SENSITIVITIES.index(sensitivity) and (r['visibility']!='twin_private' or employee=='twin')]

def skill(employee,path=p.DEFAULT_DB):
    with readonly(path) as db:
        if 'team_skills' not in tables(db):return None
        row=db.execute('SELECT * FROM team_skills WHERE employee=?',(employee,)).fetchone();return dict(row) if row else None

def save_skill(employee,expected,rules,examples='',path=p.DEFAULT_DB):
    if employee not in EMPLOYEES or employee=='twin':raise ValueError('Choose a department writing skill')
    with p.connect(path) as db:
        cur=db.execute('UPDATE team_skills SET rules=?,examples=?,version=version+1 WHERE employee=? AND version=?',(text(rules,4000,'Writing rules',True),text(examples,6000,'Approved examples'),employee,expected))
        if not cur.rowcount:raise ValueError('Writing skill changed; reload')
        event(db,'owner','writing_skill_updated',{'employee':employee,'version':expected+1})

def audit(path=p.DEFAULT_DB):
    with readonly(path) as db:return rows(db,'SELECT * FROM team_events ORDER BY seq DESC LIMIT 100') if 'team_events' in tables(db) else []
def requests(path=p.DEFAULT_DB):
    with readonly(path) as db:return rows(db,'SELECT * FROM team_requests ORDER BY created_at DESC') if 'team_requests' in tables(db) else []
