"""Versioned milestones over existing projects and tasks; no duplicate task engine."""
from contextlib import nullcontext
import json,hashlib
from pathlib import Path
from uuid import uuid4
from superhuman.projects import engine as p
from superhuman.team import store as team,work
from superhuman.departments.store import readonly,tables,rows
from .blueprints import ENDORSEMENT,COMMON
STATES=('planned','working','lead_review','specialist_review','twin_review','owner_review','approved','needs_owner')

def read(table,sql,args=(),path=p.DEFAULT_DB):
    with readonly(path) as db:return rows(db,sql,args) if table in tables(db) else []
def managed(pid,path=p.DEFAULT_DB):
    r=read('milestone_projects','SELECT * FROM milestone_projects WHERE project_id=?',(pid,),path);return r[0] if r else None
def initialize(path=p.DEFAULT_DB):
    team.initialize(path)
    with p.connect(path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS milestone_tool_restore(employee TEXT PRIMARY KEY,removed TEXT NOT NULL,employee_version INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS milestone_migrations(id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS milestone_page_checks(item_id TEXT NOT NULL,item_version INTEGER NOT NULL,digest TEXT NOT NULL,pages TEXT NOT NULL,note TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS milestone_notes(task_id TEXT NOT NULL,note_key TEXT NOT NULL,content TEXT NOT NULL,version INTEGER NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(task_id,note_key));
        CREATE TABLE IF NOT EXISTS milestone_projects(project_id TEXT PRIMARY KEY,lead TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 0,share_outputs INTEGER NOT NULL DEFAULT 0,version INTEGER NOT NULL DEFAULT 1,seed_key TEXT UNIQUE,last_signature TEXT NOT NULL DEFAULT '',next_due REAL NOT NULL DEFAULT 0,hold TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS milestones(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,ordinal INTEGER NOT NULL,title TEXT NOT NULL,question TEXT NOT NULL,criteria TEXT NOT NULL,criteria_confirmed INTEGER NOT NULL DEFAULT 0,workers TEXT NOT NULL,reviewers TEXT NOT NULL,deps TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'planned',version INTEGER NOT NULL DEFAULT 1,revision_count INTEGER NOT NULL DEFAULT 0,current_packet TEXT,created_at TEXT NOT NULL,UNIQUE(project_id,ordinal));
        CREATE TABLE IF NOT EXISTS milestone_assignments(task_id TEXT PRIMARY KEY,milestone_id TEXT NOT NULL,role TEXT NOT NULL,packet_version INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS milestone_materials(project_id TEXT NOT NULL,item_id TEXT NOT NULL,item_version INTEGER NOT NULL,recipients TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,version INTEGER NOT NULL DEFAULT 1,purpose TEXT NOT NULL DEFAULT 'reference',PRIMARY KEY(project_id,item_id));
        CREATE TABLE IF NOT EXISTS milestone_packets(id TEXT PRIMARY KEY,milestone_id TEXT NOT NULL,version INTEGER NOT NULL,body TEXT NOT NULL,digest TEXT NOT NULL,sources TEXT NOT NULL,twin_memo_hash TEXT NOT NULL DEFAULT '',exports TEXT NOT NULL DEFAULT '[]',created_at TEXT NOT NULL,UNIQUE(milestone_id,version));
        CREATE TABLE IF NOT EXISTS milestone_reviews(id TEXT PRIMARY KEY,milestone_id TEXT NOT NULL,packet_id TEXT,actor TEXT NOT NULL,decision TEXT NOT NULL,note TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS milestone_memos(milestone_id TEXT PRIMARY KEY,body TEXT NOT NULL,digest TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS milestone_cycles(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,milestone_id TEXT NOT NULL,actor TEXT NOT NULL,signature TEXT NOT NULL,status TEXT NOT NULL,response TEXT,error TEXT,created_at TEXT NOT NULL,finished_at TEXT);
        ''')
    with p.connect(path) as db:
        if not db.execute("SELECT 1 FROM milestone_migrations WHERE id='reading-tools-131'").fetchone():
            for e in db.execute('SELECT id,allowed_tools FROM team_employees').fetchall():
                allowed=json.loads(e['allowed_tools']);new=list(allowed)
                if 'workspace.read' in allowed:
                    for tool in ('storage.pdf_pages','milestone.read_output'):
                        if tool not in new:new.append(tool)
                if 'team.handoff' in allowed and 'milestone.note' not in new:new.append('milestone.note')
                if new!=allowed:db.execute('UPDATE team_employees SET allowed_tools=?,version=version+1 WHERE id=?',(json.dumps(new),e['id']))
            db.execute("INSERT INTO milestone_migrations VALUES('reading-tools-131')")
            team.event(db,'owner','milestone_reading_tools_installed',{'permissions':'Existing file-reading and collaboration permissions only; no external actions'})
    with p.connect(path) as db:
        for saved in db.execute('SELECT * FROM milestone_tool_restore').fetchall():
            employee=db.execute('SELECT * FROM team_employees WHERE id=?',(saved['employee'],)).fetchone()
            if employee and employee['version']==saved['employee_version']:
                allowed=json.loads(employee['allowed_tools']);restore=json.loads(saved['removed'])
                db.execute('UPDATE team_employees SET allowed_tools=?,version=version+1 WHERE id=?',(json.dumps(sorted(set(allowed+restore))),employee['id']))
                db.execute('DELETE FROM milestone_tool_restore WHERE employee=?',(employee['id'],))
                team.event(db,'owner','milestone_tools_restored_after_reinstall',{'employee':employee['id'],'tools':restore})

def listing(pid=None,path=p.DEFAULT_DB):
    return read('milestones','SELECT * FROM milestones'+(' WHERE project_id=?' if pid else '')+' ORDER BY project_id,ordinal',(pid,) if pid else (),path)
def milestone(ident,path=p.DEFAULT_DB):
    found=read('milestones','SELECT * FROM milestones WHERE id=?',(ident,),path)
    if not found:raise ValueError('Milestone not found')
    return found[0]
def assignments(mid,path=p.DEFAULT_DB):
    return read('milestone_assignments','SELECT a.*,t.owner,t.title,t.state,t.version,t.run_id,t.attempts FROM milestone_assignments a JOIN team_tasks t ON t.id=a.task_id WHERE a.milestone_id=? ORDER BY t.created_at,t.id',(mid,),path)
def assignment(tid,path=p.DEFAULT_DB):
    found=read('milestone_assignments','SELECT * FROM milestone_assignments WHERE task_id=?',(tid,),path);return found[0] if found else None
def roster(pid,path=p.DEFAULT_DB):
    cfg=managed(pid,path)
    return sorted({cfg['lead'],'twin'}|{e for m in listing(pid,path) for key in ('workers','reviewers') for e in json.loads(m[key])}) if cfg else []
def attach(pid,lead,path=p.DEFAULT_DB):
    q=team.project(pid,path)
    if lead!=q['scope'] or lead not in team.EMPLOYEES or lead=='twin':raise ValueError('The department specialist must lead this project')
    if any(t['project_id']==pid and t['state'] not in ('completed','cancelled') for t in team.tasks(path)):raise ValueError('Organise existing open tasks before attaching milestone leadership')
    initialize(path)
    with p.connect(path) as db:
        if db.execute('SELECT 1 FROM milestone_projects WHERE project_id=?',(pid,)).fetchone():raise ValueError('Project already has milestone leadership')
        db.execute('INSERT INTO milestone_projects(project_id,lead) VALUES(?,?)',(pid,lead));team.event(db,'owner','project_lead_appointed',{'project_id':pid,'lead':lead})
def add(pid,title,question,criteria,workers,reviewers=(),deps=(),path=p.DEFAULT_DB):
    cfg=managed(pid,path)
    if not cfg:raise ValueError('Set up project leadership first')
    workers=list(dict.fromkeys(workers));reviewers=list(dict.fromkeys(reviewers));existing=listing(pid,path)
    if not workers or set(workers+reviewers)-set(team.EMPLOYEES) or 'twin' in reviewers:raise ValueError('Choose a working team and specialist reviewers')
    if 'twin' in workers and not reviewers:raise ValueError('The Twin contribution requires an independent specialist reviewer')
    if set(workers)&set(reviewers) or cfg['lead'] in reviewers:raise ValueError('Independent reviewers must not be authors or the project lead')
    if set(deps)-{m['id'] for m in existing} or len(set(deps))!=len(deps):raise ValueError('Dependencies must be existing milestones in this project')
    if len(existing)>=20:raise ValueError('Milestone limit reached')
    ident=uuid4().hex
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        ordinal=db.execute('SELECT COALESCE(MAX(ordinal),0)+1 FROM milestones WHERE project_id=?',(pid,)).fetchone()[0]
        if ordinal>20:raise ValueError('Milestone limit reached')
        db.execute('INSERT INTO milestones(id,project_id,ordinal,title,question,criteria,workers,reviewers,deps,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(ident,pid,ordinal,team.text(title,180,'Milestone title',True),team.text(question,1200,'Business question',True),team.text(criteria,3500,'Acceptance criteria',True),json.dumps(workers),json.dumps(reviewers),json.dumps(list(deps)),p.stamp()))
        db.execute('UPDATE milestone_projects SET version=version+1 WHERE project_id=?',(pid,));team.event(db,'owner','milestone_created',{'id':ident,'project_id':pid})
    from superhuman.assurance.store import seed
    seed(ident,path)
    return ident

def _seed_endorsement_v131(path=p.DEFAULT_DB):
    initialize(path)
    found=read('milestone_projects',"SELECT project_id FROM milestone_projects WHERE seed_key='endorsement-business-plan-131'",path=path)
    if found:return found[0]['project_id']
    pid=uuid4().hex
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        existing=db.execute("SELECT project_id FROM milestone_projects WHERE seed_key='endorsement-business-plan-131'").fetchone()
        if existing:return existing['project_id']
        db.execute("INSERT INTO team_projects(id,scope,title,objective,acceptance,priority,risk,sensitivity,status,created_at) VALUES(?,'endorsement',?,?,?,'P1','routine','internal','paused',?)",(pid,'EdSync — Innovator International business plan','Develop an evidence-backed operational business plan using the owner-provided guide and verified research.','Seven reviewed milestones; strategic decisions approved by Mahnoor; final package ready for separate submission approval.',p.stamp()))
        db.execute("INSERT INTO milestone_projects(project_id,lead,seed_key) VALUES(?,'endorsement','endorsement-business-plan-131')",(pid,))
        previous=[]
        for ordinal,(title,question,workers,reviewers,deliverable) in enumerate(ENDORSEMENT,1):
            mid=uuid4().hex
            db.execute('INSERT INTO milestones(id,project_id,ordinal,title,question,criteria,workers,reviewers,deps,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(mid,pid,ordinal,title,question,deliverable+' '+COMMON,json.dumps(workers),json.dumps(reviewers),json.dumps(previous),p.stamp()))
            previous=[mid]
        team.event(db,'owner','endorsement_blueprint_prepared',{'project_id':pid,'paused':True,'criteria_provisional':True})
    return pid

def configure(pid,expected,enabled,share_outputs,path=p.DEFAULT_DB):
    if type(enabled) is not bool or type(share_outputs) is not bool:raise ValueError('Choose valid project controls')
    if enabled and not share_outputs:raise ValueError('Confirm project-scoped sharing of work briefs and outputs with the listed team and The Twin')
    with p.connect(path) as db:
        if not db.execute('UPDATE milestone_projects SET enabled=?,share_outputs=?,version=version+1,hold=\'\',next_due=0 WHERE project_id=? AND version=?',(int(enabled),int(share_outputs),pid,expected)).rowcount:raise ValueError('Project leadership changed; reload')
        team.event(db,'owner','milestone_project_configured',{'project_id':pid,'enabled':enabled,'shared_outputs':share_outputs})

def edit(mid,expected,question,criteria,confirmed,path=p.DEFAULT_DB):
    m=milestone(mid,path)
    if m['state'] not in ('planned','working'):raise ValueError('Acceptance criteria are frozen during review; finish the current revision first')
    with p.connect(path) as db:
        if db.execute("SELECT 1 FROM team_tasks t JOIN milestone_assignments a ON a.task_id=t.id WHERE a.milestone_id=? AND t.run_id IS NOT NULL",(mid,)).fetchone():raise ValueError('Criteria are frozen after execution starts. Review or pause this work before changing its scope.')
        if not db.execute('UPDATE milestones SET question=?,criteria=?,criteria_confirmed=?,version=version+1 WHERE id=? AND version=?',(team.text(question,1200,'Question',True),team.text(criteria,3500,'Acceptance criteria',True),int(confirmed),mid,expected)).rowcount:raise ValueError('Milestone changed; reload')
        team.event(db,'owner','milestone_criteria_updated',{'id':mid,'confirmed':confirmed})

def confirm_criteria(mid,expected,path=p.DEFAULT_DB):
    with p.connect(path) as db:
        if not db.execute('UPDATE milestones SET criteria_confirmed=1,version=version+1 WHERE id=? AND version=? AND criteria_confirmed=0',(mid,expected)).rowcount:raise ValueError('Criteria changed or already confirmed')
        team.event(db,'owner','milestone_criteria_confirmed',{'id':mid})

def share(pid,item_id,item_version,recipients,purpose='reference',path=p.DEFAULT_DB):
    from superhuman.foundation import storage
    item=storage.get(item_id,path);members=roster(pid,path)
    if not managed(pid,path) or not recipients or set(recipients)-set(members):raise ValueError('Choose named project participants')
    if item['status']!='approved' or item['version']!=item_version or storage.health(item)!='Current':raise ValueError('Use a current approved Storage version')
    if item['project_id'] and item['project_id']!=pid:raise ValueError('Source belongs to another project')
    if purpose not in ('reference','required_guide'):raise ValueError('Invalid material purpose')
    with p.connect(path) as db:
        db.execute('INSERT INTO milestone_materials(project_id,item_id,item_version,recipients,purpose) VALUES(?,?,?,?,?) ON CONFLICT(project_id,item_id) DO UPDATE SET item_version=excluded.item_version,recipients=excluded.recipients,purpose=excluded.purpose,active=1,version=version+1',(pid,item_id,item_version,json.dumps(sorted(set(recipients))),purpose))
        team.event(db,'owner','project_material_shared',{'project_id':pid,'item_id':item_id,'version':item_version,'recipients':recipients})

def materials(pid,path=p.DEFAULT_DB):return read('milestone_materials','SELECT * FROM milestone_materials WHERE project_id=?',(pid,),path)
def revoke(pid,item_id,expected,path=p.DEFAULT_DB):
    with p.connect(path) as db:
        if not db.execute('UPDATE milestone_materials SET active=0,version=version+1 WHERE project_id=? AND item_id=? AND version=?',(pid,item_id,expected)).rowcount:raise ValueError('Material grant changed; reload')
        team.event(db,'owner','project_material_revoked',{'project_id':pid,'item_id':item_id})
def share_allowed(item,employee,pid,path=p.DEFAULT_DB):
    if not pid or not managed(pid,path):return False
    grants=read('milestone_materials','SELECT * FROM milestone_materials WHERE project_id=? AND item_id=? AND active=1',(pid,item['id']),path)
    return bool(grants and grants[0]['item_version']==item['version'] and employee in json.loads(grants[0]['recipients']) and employee in roster(pid,path) and (not item['project_id'] or item['project_id']==pid))

def active(mid,path=p.DEFAULT_DB):
    from superhuman.assurance.workflow import execution_block
    blocked=execution_block(mid,path)
    if blocked:return False,blocked
    m=milestone(mid,path);cfg=managed(m['project_id'],path);q=team.project(m['project_id'],path)
    if not cfg['enabled'] or not cfg['share_outputs'] or cfg['hold'] or q['status']!='active':return False,'Milestone project is held, paused or not configured'
    if m['state'] not in ('working','lead_review','specialist_review','twin_review'):return False,'Milestone is '+m['state'].replace('_',' ')
    if any(milestone(i,path)['state']!='approved' for i in json.loads(m['deps'])):return False,'Previous milestone requires owner approval'
    return True,''

def task_gate(item,path=p.DEFAULT_DB):
    a=assignment(item['id'],path)
    if not a:return (False,'Unlinked task in a milestone project; add it through the milestone') if managed(item['project_id'],path) else (True,'')
    good,why=active(a['milestone_id'],path)
    if not good:return good,why
    m=milestone(a['milestone_id'],path);cfg=managed(m['project_id'],path)
    allowed=[cfg['lead']] if a['role']=='lead' else json.loads(m['reviewers']) if a['role']=='reviewer' else json.loads(m['workers'])
    if item['owner'] not in allowed:return False,'Assignment owner is not on the approved milestone team'
    if a['role']=='lead':
        from superhuman.assurance.store import gaps
        if any(g['critical'] and g['state']!='resolved' for g in gaps(m['id'],path)):return False,'Resolve critical investigations before integration execution'
        if 'twin' in json.loads(m['workers']) and not memo(m['id'],path):return False,'Waiting for The Twin contribution'
        if m['state']!='working':return False,'Lead result is frozen for milestone review'
    if a['role']=='reviewer' and m['state']!='specialist_review':return False,'Reviewer awaits a current frozen packet'
    if a['role']=='contributor' and m['state']!='working':return False,'Contributor work is frozen for review'
    return True,''

def create_assignment(mid,employee,title,instruction,criteria,role='contributor',deps=(),path=p.DEFAULT_DB,_db=None,sensitivity_override=None):
    m=milestone(mid,path);cfg=managed(m['project_id'],path)
    permitted=[cfg['lead']] if role=='lead' else json.loads(m['reviewers']) if role=='reviewer' else json.loads(m['workers'])
    if employee not in permitted or employee=='twin' or role not in ('lead','contributor','reviewer'):raise ValueError('Choose a permitted specialist assignment')
    current=packet(mid,path)
    if sum(a['role']!='reviewer' or current and a['packet_version']==current['version'] for a in assignments(mid,path))>=12:raise ValueError('Milestone assignment limit reached; owner decision required')
    sensitivity=team.project(m['project_id'],path)['sensitivity']
    if sensitivity_override is not None:
        if sensitivity_override not in team.SENSITIVITIES or team.SENSITIVITIES.index(sensitivity_override)<team.SENSITIVITIES.index(sensitivity):raise ValueError('Work-package sensitivity cannot be below project sensitivity')
        sensitivity=sensitivity_override
    # Only the lead integration includes all linked private materials; public research stays compartmentalised.
    if role=='reviewer':
        lead=next(a for a in assignments(mid,path) if a['role']=='lead')
        sensitivity=team.effective(team.task(lead['task_id'],path),path)['sensitivity']
    if role=='lead':
        from superhuman.foundation import storage
        levels=[sensitivity]+[storage.get(g['item_id'],path)['sensitivity'] for g in materials(m['project_id'],path) if g['active'] and employee in json.loads(g['recipients'])]
        from .workflow import packet_sensitivity
        levels.extend(packet_sensitivity(previous['id'],path) for previous in listing(m['project_id'],path) if previous['state']=='approved')
        for dep in deps:
            row=dict(_db.execute('SELECT * FROM team_tasks WHERE id=?',(dep,)).fetchone()) if _db is not None else team.task(dep,path)
            levels.append(team.effective(row,path)['sensitivity'])
        sensitivity=max(levels,key=team.SENSITIVITIES.index)
    with (p.connect(path) if _db is None else nullcontext(_db)) as db:
        if _db is None:db.execute('BEGIN IMMEDIATE')
        tid=team.create_task(m['project_id'],employee,title,instruction,criteria,sensitivity=sensitivity,deps=deps,actor='milestone:'+cfg['lead'],path=path,_db=db)
        db.execute('INSERT INTO milestone_assignments VALUES(?,?,?,?)',(tid,mid,role,packet(mid,path)['version'] if role=='reviewer' else 0))
        db.execute("UPDATE team_tasks SET state='ready' WHERE id=?",(tid,))
        if role=='lead' and cfg['seed_key']=='endorsement-business-plan-131' and m['ordinal']==1:
            db.execute('UPDATE team_tasks SET max_calls=48,max_steps=40 WHERE id=?',(tid,))
    return tid

def start(mid,expected,path=p.DEFAULT_DB):
    from superhuman.assurance.workflow import execution_block
    if execution_block(mid,path):raise ValueError(execution_block(mid,path))
    m=milestone(mid,path);cfg=managed(m['project_id'],path)
    if m['version']!=expected or m['state']!='planned':raise ValueError('Milestone changed or already started')
    if not cfg['enabled'] or not cfg['share_outputs'] or team.project(m['project_id'],path)['status']!='active':raise ValueError('Enable project leadership, confirm output sharing and activate the project first')
    if any(milestone(i,path)['state']!='approved' for i in json.loads(m['deps'])):raise ValueError('Previous milestones need owner approval')
    if cfg['seed_key']=='endorsement-business-plan-131' and m['ordinal']==1:
        from superhuman.foundation import storage
        guides=[g for g in materials(m['project_id'],path) if g['active'] and g['purpose']=='required_guide' and cfg['lead'] in json.loads(g['recipients']) and storage.get(g['item_id'],path)['kind']=='document' and storage.get(g['item_id'],path)['filename'].lower().endswith('.pdf') and storage.health(storage.get(g['item_id'],path))=='Current' and storage.get(g['item_id'],path)['version']==g['item_version'] and storage.get(g['item_id'],path)['status']=='approved']
        if not guides:raise ValueError('Link the current owner-provided guide from approved Storage and grant Katherine access before starting M1')
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute("UPDATE milestones SET state='working',version=version+1 WHERE id=? AND version=? AND state='planned'",(mid,expected)).rowcount:raise ValueError('Milestone changed; reload')
        deps=[]
        workers=json.loads(m['workers'])
        for e in workers:
            if e in (cfg['lead'],'twin'):continue
            deps.append(create_assignment(mid,e,'M'+str(m['ordinal'])+' · '+team.EMPLOYEES[e][0]+' contribution',m['question']+'\nDeliver your specialist findings for Katherine/the project lead to integrate.\n'+COMMON,m['criteria'][:1500],path=path,_db=db))
        if cfg['seed_key']=='endorsement-business-plan-131' and m['ordinal']==1:
            deps.append(create_assignment(mid,cfg['lead'],'M1 · Public requirements research','Research official public Innovator International materials, Innovator Impulse and documented endorsement examples. Find the correct official sources, distinguish evidence from inference, and cite sources. Do not disclose private guide contents or private EdSync materials to web tools.','A sourced public research report with coverage limitations and unresolved questions.',path=path,_db=db))
        instruction=m['question']+'\nAs project lead, consolidate completed contributions into one polished deliverable. Read linked materials and current project context. For PDF sources, use storage.pdf_pages in consecutive ranges to cover every page; record concise section notes with milestone.note. Do not claim full coverage from a bounded workspace.read excerpt. '+COMMON
        create_assignment(mid,cfg['lead'],'M'+str(m['ordinal'])+' · Integrated deliverable',instruction,m['criteria'][:1500],role='lead',deps=deps,path=path,_db=db)
        team.event(db,'owner','milestone_started',{'id':mid,'project_id':m['project_id'],'criteria_provisional':not m['criteria_confirmed']})
    return mid

def packet(mid,path=p.DEFAULT_DB):
    m=milestone(mid,path)
    found=read('milestone_packets','SELECT * FROM milestone_packets WHERE id=?',(m['current_packet'],),path) if m['current_packet'] else []
    return found[0] if found else None
def memo(mid,path=p.DEFAULT_DB):
    found=read('milestone_memos','SELECT * FROM milestone_memos WHERE milestone_id=?',(mid,),path);return found[0] if found else None

def pause_for_rollback(path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:
        retired={'storage.pdf_pages','milestone.read_output','milestone.note'}
        for employee in db.execute('SELECT id,allowed_tools,version FROM team_employees').fetchall():
            allowed=json.loads(employee['allowed_tools']);removed=sorted(set(allowed)&retired)
            if removed:
                db.execute('INSERT OR REPLACE INTO milestone_tool_restore VALUES(?,?,?)',(employee['id'],json.dumps(removed),employee['version']+1))
                db.execute('UPDATE team_employees SET allowed_tools=?,version=version+1 WHERE id=?',(json.dumps([n for n in allowed if n not in retired]),employee['id']))
        for run in db.execute('SELECT project_id,allowed_tools,state FROM agentic_runs').fetchall():
            allowed=json.loads(run['allowed_tools'])
            if set(allowed)&retired:
                db.execute("UPDATE agentic_runs SET allowed_tools=?,state=CASE WHEN state IN ('completed','cancelled') THEN state ELSE 'paused' END,version=version+1 WHERE project_id=?",(json.dumps([n for n in allowed if n not in retired]),run['project_id']))
        db.execute("UPDATE milestone_projects SET enabled=0,hold='Code rolled back; review before resuming',version=version+1")
        db.execute("UPDATE milestone_cycles SET status='interrupted',error='Code rolled back; no automatic replay',finished_at=? WHERE status='running'",(p.stamp(),))
        db.execute("UPDATE team_tasks SET state='paused',version=version+1 WHERE id IN (SELECT task_id FROM milestone_assignments) AND state NOT IN ('completed','cancelled')")

def resume(pid,expected,note,path=p.DEFAULT_DB):
    note=team.text(note,2000,'Inspection note',True)
    with p.connect(path) as db:
        if not db.execute("UPDATE milestone_projects SET hold='',last_signature='',next_due=0,version=version+1 WHERE project_id=? AND version=?",(pid,expected)).rowcount:raise ValueError('Leadership settings changed; reload')
        team.event(db,'owner','milestone_project_resumed',{'project_id':pid,'note':note})

def continue_after_inspection(mid,expected,note,path=p.DEFAULT_DB):
    m=milestone(mid,path);note=team.text(note,2000,'Inspection decision',True)
    if m['version']!=expected or m['state']!='needs_owner':raise ValueError('Milestone is not awaiting inspection')
    lead=next((a for a in assignments(mid,path) if a['role']=='lead'),None)
    state='twin_review' if m['current_packet'] and lead and lead['state']=='awaiting_review' else 'working'
    with p.connect(path) as db:
        if not db.execute('UPDATE milestones SET state=?,version=version+1 WHERE id=? AND version=?',(state,mid,expected)).rowcount:raise ValueError('Milestone changed; reload')
        db.execute("UPDATE milestone_projects SET last_signature='',next_due=0 WHERE project_id=?",(m['project_id'],))
        team.event(db,'owner','milestone_inspection_completed',{'id':mid,'note':note,'state':state})


def seed_endorsement(path=p.DEFAULT_DB):
    pid=_seed_endorsement_v131(path)
    from superhuman.assurance.store import seed
    for row in listing(pid,path):seed(row["id"],path)
    return pid
