"""Transactional planning records, optimistic edits, links, dependencies and history."""
from contextlib import contextmanager
from datetime import date,datetime,timezone
import json
import os
from pathlib import Path
import re
import sqlite3

PRIORITIES=('unset','critical','high','normal','low')
MILESTONE_STATUSES=('planned','in_progress','on_hold','complete','archived')
BLOCKER_STATUSES=('open','resolved')
class Conflict(ValueError):pass

def default_path():return Path(os.getenv('SUPERHUMAN_PLANNING_DB','data/department_planning/plans.db')).resolve()
def now():return datetime.now(timezone.utc).isoformat(timespec='microseconds')
def scope_check(scope):
    from superhuman.core.router import WORKSTREAMS
    if scope not in WORKSTREAMS:raise ValueError('Unknown department')
def text(value,maximum,label,required=False):
    if not isinstance(value,str):raise ValueError(label+' must be text')
    value=value.strip()
    if (required and not value) or len(value)>maximum or any(ord(c)<32 and c not in '\n\r\t' for c in value):raise ValueError(label+' is missing, too long or contains unsupported characters')
    return value

def day(value):
    value=text(value,10,'Target date')
    if value:
        try:
            if date.fromisoformat(value).isoformat()!=value:raise ValueError()
        except ValueError:raise ValueError('Use a valid target date in YYYY-MM-DD format') from None
    return value

def key(value):
    if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{32}',value):raise ValueError('Invalid planning item identifier')
    return value

def version_check(value):
    if type(value) is not int or value<0:raise ValueError('Invalid edit version')

@contextmanager
def write(path=None):
    p=Path(path or default_path());p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    db=sqlite3.connect(p,timeout=15);db.row_factory=sqlite3.Row
    try:
        db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA busy_timeout=15000')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS department_goals(scope TEXT PRIMARY KEY,objective TEXT NOT NULL,priority TEXT NOT NULL,target_date TEXT NOT NULL,success_criteria TEXT NOT NULL,version INTEGER NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS department_milestones(id TEXT PRIMARY KEY,scope TEXT NOT NULL,title TEXT NOT NULL,target_date TEXT NOT NULL,success_criteria TEXT NOT NULL,status TEXT NOT NULL,completion_note TEXT NOT NULL,version INTEGER NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS department_project_links(milestone_id TEXT NOT NULL REFERENCES department_milestones(id),project_id TEXT NOT NULL,PRIMARY KEY(milestone_id,project_id));
        CREATE TABLE IF NOT EXISTS department_dependencies(milestone_id TEXT NOT NULL REFERENCES department_milestones(id),depends_on TEXT NOT NULL REFERENCES department_milestones(id),PRIMARY KEY(milestone_id,depends_on));
        CREATE TABLE IF NOT EXISTS department_blockers(id TEXT PRIMARY KEY,scope TEXT NOT NULL,milestone_id TEXT REFERENCES department_milestones(id),description TEXT NOT NULL,needed_from TEXT NOT NULL,target_date TEXT NOT NULL,status TEXT NOT NULL,resolution_note TEXT NOT NULL,version INTEGER NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS department_plan_history(seq INTEGER PRIMARY KEY AUTOINCREMENT,scope TEXT NOT NULL,entity_type TEXT NOT NULL,entity_id TEXT NOT NULL,action TEXT NOT NULL,before_json TEXT NOT NULL,after_json TEXT NOT NULL,recorded_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS planning_milestones_scope ON department_milestones(scope);
        CREATE INDEX IF NOT EXISTS planning_blockers_scope ON department_blockers(scope);
        CREATE INDEX IF NOT EXISTS planning_history_scope ON department_plan_history(scope,seq);
        ''')
        db.execute('BEGIN IMMEDIATE')
        from superhuman.repairs.lifecycle import initialize
        initialize(db)
        try:yield db;db.commit()
        except Exception:db.rollback();raise
    finally:db.close()

def snapshot(scope,path=None):
    scope_check(scope)
    from superhuman.departments.store import readonly,tables,rows
    result={'goal':{'scope':scope,'objective':'','priority':'unset','target_date':'','success_criteria':'','version':0,'updated_at':''},'milestones':[],'blockers':[],'warnings':[]}
    try:
        with readonly(path or default_path()) as db:
            ts=tables(db)
            if 'department_goals' in ts:
                row=db.execute('SELECT * FROM department_goals WHERE scope=?',(scope,)).fetchone()
                if row:result['goal']=dict(row)
            if 'department_milestones' in ts:
                result['milestones']=rows(db,'SELECT * FROM department_milestones WHERE scope=? ORDER BY CASE WHEN target_date=\'\' THEN 1 ELSE 0 END,target_date,created_at,id',(scope,))
                for m in result['milestones']:
                    m['project_ids']=[r[0] for r in db.execute('SELECT project_id FROM department_project_links WHERE milestone_id=? ORDER BY project_id',(m['id'],))] if 'department_project_links' in ts else []
                    m['depends_on']=[r[0] for r in db.execute('SELECT depends_on FROM department_dependencies WHERE milestone_id=? ORDER BY depends_on',(m['id'],))] if 'department_dependencies' in ts else []
            if 'department_blockers' in ts:result['blockers']=rows(db,'SELECT * FROM department_blockers WHERE scope=? ORDER BY status,CASE WHEN target_date=\'\' THEN 1 ELSE 0 END,target_date,created_at,id',(scope,))
    except sqlite3.Error:result['warnings'].append('Planning records could not be read. Check the saved plan before relying on this view.')
    from superhuman.repairs.lifecycle import read
    with readonly(path or default_path()) as lifecycle_db:
        try:result['goal'].update(read(lifecycle_db,scope))
        except sqlite3.Error:result['warnings'].append('Goal lifecycle could not be read.')
    from superhuman.supervision.context import append_links
    append_links(scope,result)
    return result

def audit(db,scope,kind,ident,before,after):
    db.execute('INSERT INTO department_plan_history(scope,entity_type,entity_id,action,before_json,after_json,recorded_at) VALUES(?,?,?,?,?,?,?)',(scope,kind,ident,'updated' if before else 'created',json.dumps(before,ensure_ascii=False,sort_keys=True),json.dumps(after,ensure_ascii=False,sort_keys=True),now()))

def save_goal(scope,expected_version,objective,priority,target_date,success_criteria,path=None,goal_status='active',completion_note=''):
    scope_check(scope);version_check(expected_version)
    objective=text(objective,2000,'Department objective');success_criteria=text(success_criteria,4000,'Success criteria');target_date=day(target_date)
    if priority not in PRIORITIES:raise ValueError('Choose a supported priority')
    with write(path) as db:
        row=db.execute('SELECT * FROM department_goals WHERE scope=?',(scope,)).fetchone();before=dict(row) if row else {}
        from superhuman.repairs.lifecycle import read as read_lifecycle,save as save_lifecycle
        if before:before.update(read_lifecycle(db,scope))
        if (before.get('version',0))!=expected_version:raise Conflict('This department plan changed. Reopen the latest plan before saving.')
        after=dict(scope=scope,objective=objective,priority=priority,target_date=target_date,success_criteria=success_criteria,version=expected_version+1,updated_at=now())
        db.execute('INSERT INTO department_goals VALUES(:scope,:objective,:priority,:target_date,:success_criteria,:version,:updated_at) ON CONFLICT(scope) DO UPDATE SET objective=excluded.objective,priority=excluded.priority,target_date=excluded.target_date,success_criteria=excluded.success_criteria,version=excluded.version,updated_at=excluded.updated_at',after)
        after.update(save_lifecycle(db,scope,goal_status,completion_note,success_criteria))
        audit(db,scope,'goal',scope,before,after)
    return after

def existing_item(db,table,scope,ident,expected):
    row=db.execute('SELECT * FROM '+table+' WHERE id=?',(ident,)).fetchone()
    if row and row['scope']!=scope:raise ValueError('This item belongs to another department')
    before=dict(row) if row else {}
    if before.get('version',0)!=expected:raise Conflict('This planning item changed. Reopen the latest item before saving.')
    return before

def check_projects(scope,ids):
    from superhuman.departments.store import readonly
    from superhuman.projects import engine as p
    with readonly(p.DEFAULT_DB) as db:
        for ident in ids:
            try:row=db.execute('SELECT workstream FROM projects WHERE id=?',(ident,)).fetchone() if db else None
            except sqlite3.Error:row=None
            if row is None or row['workstream']!=scope:raise ValueError('Link only existing projects in this department')

def lists(values,label):
    if not isinstance(values,(list,tuple)) or len(values)>100 or any(not isinstance(v,str) or len(v)>64 for v in values):raise ValueError('Invalid '+label)
    return sorted(set(values))

def save_milestone(scope,ident,expected_version,title,target_date,success_criteria,status,completion_note='',project_ids=(),depends_on=(),path=None):
    scope_check(scope);key(ident);version_check(expected_version)
    title=text(title,180,'Milestone title',True);target_date=day(target_date);success_criteria=text(success_criteria,4000,'Success criteria');completion_note=text(completion_note,2000,'Completion note')
    if status not in MILESTONE_STATUSES:raise ValueError('Choose a supported milestone status')
    if status=='complete' and (not success_criteria or not completion_note):raise ValueError('Record success criteria and a completion note before marking a milestone complete')
    project_ids=lists(project_ids,'linked projects');depends_on=lists(depends_on,'dependencies');check_projects(scope,project_ids)
    if ident in depends_on:raise ValueError('A milestone cannot depend on itself')
    with write(path) as db:
        from superhuman.repairs.lifecycle import read as goal_lifecycle
        if goal_lifecycle(db,scope)['status'] in ('complete','archived') and status not in ('complete','archived'):raise ValueError('Reopen the department goal before adding or reactivating milestones')
        before=existing_item(db,'department_milestones',scope,ident,expected_version)
        if before:
            before['project_ids']=[r[0] for r in db.execute('SELECT project_id FROM department_project_links WHERE milestone_id=? ORDER BY project_id',(ident,))]
            before['depends_on']=[r[0] for r in db.execute('SELECT depends_on FROM department_dependencies WHERE milestone_id=? ORDER BY depends_on',(ident,))]
        milestones={r['id']:dict(r) for r in db.execute('SELECT * FROM department_milestones WHERE scope=?',(scope,))}
        for dependency in depends_on:
            if dependency not in milestones:raise ValueError('Choose dependencies from this department')
            if milestones[dependency]['status']=='archived':raise ValueError('An archived milestone cannot be a dependency')
        graph={mid:[r[0] for r in db.execute('SELECT depends_on FROM department_dependencies WHERE milestone_id=?',(mid,))] for mid in milestones};graph[ident]=depends_on
        visiting=set();seen=set()
        def visit(mid):
            if mid in visiting:raise ValueError('Milestone dependencies would form a cycle')
            if mid in seen:return
            visiting.add(mid)
            for dep in graph.get(mid,[]):visit(dep)
            visiting.remove(mid);seen.add(mid)
        for mid in graph:visit(mid)
        if status in ('in_progress','complete') and any(milestones[dep]['status']!='complete' for dep in depends_on):raise ValueError('Complete the dependency milestones before starting or completing this milestone')
        dependents=[m for mid,m in milestones.items() if ident in graph.get(mid,[])]
        if status=='archived' and dependents:raise ValueError('Remove this milestone from dependent milestones before archiving it')
        if before.get('status')=='complete' and status!='complete' and any(m['status'] in ('in_progress','complete') for m in dependents):raise ValueError('Move dependent milestones to planned or on hold before reopening their completed dependency')
        if status=='complete' and db.execute("SELECT 1 FROM department_blockers WHERE milestone_id=? AND status='open'",(ident,)).fetchone():raise ValueError('Resolve the open blockers linked to this milestone before completing it')
        at=now();after=dict(id=ident,scope=scope,title=title,target_date=target_date,success_criteria=success_criteria,status=status,completion_note=completion_note,version=expected_version+1,created_at=before.get('created_at',at),updated_at=at)
        db.execute('INSERT INTO department_milestones VALUES(:id,:scope,:title,:target_date,:success_criteria,:status,:completion_note,:version,:created_at,:updated_at) ON CONFLICT(id) DO UPDATE SET title=excluded.title,target_date=excluded.target_date,success_criteria=excluded.success_criteria,status=excluded.status,completion_note=excluded.completion_note,version=excluded.version,updated_at=excluded.updated_at',after)
        db.execute('DELETE FROM department_project_links WHERE milestone_id=?',(ident,));db.executemany('INSERT INTO department_project_links VALUES(?,?)',[(ident,v) for v in project_ids])
        db.execute('DELETE FROM department_dependencies WHERE milestone_id=?',(ident,));db.executemany('INSERT INTO department_dependencies VALUES(?,?)',[(ident,v) for v in depends_on])
        after={**after,'project_ids':project_ids,'depends_on':depends_on};audit(db,scope,'milestone',ident,before,after)
    return after

def save_blocker(scope,ident,expected_version,description,needed_from,target_date,status,milestone_id='',resolution_note='',path=None):
    scope_check(scope);key(ident);version_check(expected_version)
    description=text(description,2000,'Missing input or blocker',True);needed_from=text(needed_from,180,'Needed from');target_date=day(target_date);resolution_note=text(resolution_note,2000,'Resolution note')
    if status not in BLOCKER_STATUSES:raise ValueError('Choose open or resolved')
    if status=='resolved' and not resolution_note:raise ValueError('Add a resolution note before resolving this blocker')
    if milestone_id:key(milestone_id)
    with write(path) as db:
        from superhuman.repairs.lifecycle import read as goal_lifecycle
        if goal_lifecycle(db,scope)['status'] in ('complete','archived') and status=='open':raise ValueError('Reopen the department goal before adding or reopening blockers')
        before=existing_item(db,'department_blockers',scope,ident,expected_version)
        if milestone_id:
            m=db.execute('SELECT * FROM department_milestones WHERE id=? AND scope=?',(milestone_id,scope)).fetchone()
            if m is None:raise ValueError('Choose a milestone in this department')
            if status=='open' and m['status'] in ('complete','archived'):raise ValueError('Reopen the milestone before adding an open blocker to it')
        at=now();after=dict(id=ident,scope=scope,milestone_id=milestone_id or None,description=description,needed_from=needed_from,target_date=target_date,status=status,resolution_note=resolution_note,version=expected_version+1,created_at=before.get('created_at',at),updated_at=at)
        db.execute('INSERT INTO department_blockers VALUES(:id,:scope,:milestone_id,:description,:needed_from,:target_date,:status,:resolution_note,:version,:created_at,:updated_at) ON CONFLICT(id) DO UPDATE SET milestone_id=excluded.milestone_id,description=excluded.description,needed_from=excluded.needed_from,target_date=excluded.target_date,status=excluded.status,resolution_note=excluded.resolution_note,version=excluded.version,updated_at=excluded.updated_at',after)
        audit(db,scope,'blocker',ident,before,after)
    return after

def history(scope,page=1,path=None):
    scope_check(scope)
    if type(page) is not int or not 1<=page<=10000:raise ValueError('Invalid history page')
    from superhuman.departments.store import readonly,tables,rows
    with readonly(path or default_path()) as db:
        if 'department_plan_history' not in tables(db):return []
        return rows(db,'SELECT * FROM department_plan_history WHERE scope=? ORDER BY seq DESC LIMIT 50 OFFSET ?',(scope,(page-1)*50))
