"""Versioned evidence and quality records. No record grants execution authority."""
import hashlib
import json
from uuid import uuid4
from superhuman.projects import engine as p
from superhuman.team import store as team
from superhuman.milestones import store as ms

RUBRIC = {
    'evidence': 'Material claims use current, relevant evidence; uncertainty is explicit.',
    'context': 'The deliverable uses the actual project and department context.',
    'completeness': 'The question, confirmed criteria and required outputs are covered.',
    'coherence': 'Claims, calculations, assumptions and recommendations agree.',
    'usefulness': 'The result is specific, actionable and concise enough to use.'}
TOOLS = ('assurance.workspace','assurance.record','assurance.scorecard')

def records(table, sql, args=(), path=p.DEFAULT_DB):
    return ms.read(table, sql, args, path)

def initialize(path=p.DEFAULT_DB):
    ms.initialize(path)
    with p.connect(path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS assurance_control(id INTEGER PRIMARY KEY CHECK(id=1),installed INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS assurance_milestones(mid TEXT PRIMARY KEY,register_confirmed INTEGER NOT NULL DEFAULT 0,version INTEGER NOT NULL DEFAULT 1,legacy INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS assurance_requirements(id TEXT PRIMARY KEY,mid TEXT NOT NULL,requirement_key TEXT NOT NULL,title TEXT NOT NULL,critical INTEGER NOT NULL,origin TEXT NOT NULL,sensitivity TEXT NOT NULL,actor TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,UNIQUE(mid,requirement_key));
        CREATE TABLE IF NOT EXISTS assurance_evidence(id TEXT PRIMARY KEY,requirement_id TEXT NOT NULL,kind TEXT NOT NULL,source_id TEXT NOT NULL,source_version INTEGER NOT NULL,digest TEXT NOT NULL,quote TEXT NOT NULL,locator TEXT NOT NULL,interpretation TEXT NOT NULL,sensitivity TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'proposed',actor TEXT NOT NULL,review_note TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,UNIQUE(requirement_id,kind,source_id,digest,quote));
        CREATE TABLE IF NOT EXISTS assurance_gaps(id TEXT PRIMARY KEY,mid TEXT NOT NULL,gap_key TEXT NOT NULL,question TEXT NOT NULL,employee TEXT NOT NULL,critical INTEGER NOT NULL,sensitivity TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'open',task_id TEXT,note TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,UNIQUE(mid,gap_key));
        CREATE TABLE IF NOT EXISTS assurance_rubrics(mid TEXT NOT NULL,criterion TEXT NOT NULL,description TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(mid,criterion));
        CREATE TABLE IF NOT EXISTS assurance_scorecards(id TEXT PRIMARY KEY,mid TEXT NOT NULL,packet_id TEXT NOT NULL,actor TEXT NOT NULL,fingerprint TEXT NOT NULL,scores TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(mid,packet_id,actor,fingerprint));
        CREATE TABLE IF NOT EXISTS assurance_packets(packet_id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS assurance_changes(id TEXT PRIMARY KEY,origin_mid TEXT NOT NULL,change_key TEXT NOT NULL,reason TEXT NOT NULL,affected TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'open',resolution TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,UNIQUE(origin_mid,change_key));
        CREATE TABLE IF NOT EXISTS assurance_history(seq INTEGER PRIMARY KEY AUTOINCREMENT,mid TEXT NOT NULL,actor TEXT NOT NULL,event TEXT NOT NULL,detail TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS assurance_initiatives(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,initiative_key TEXT NOT NULL,title TEXT NOT NULL,hypothesis TEXT NOT NULL,actor TEXT NOT NULL,source_kind TEXT NOT NULL DEFAULT '',source_id TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'proposed',version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,UNIQUE(project_id,initiative_key));
        CREATE TABLE IF NOT EXISTS assurance_metrics(id TEXT PRIMARY KEY,initiative_id TEXT NOT NULL,name TEXT NOT NULL,unit TEXT NOT NULL,baseline TEXT NOT NULL,target TEXT NOT NULL,due TEXT NOT NULL,direction TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS assurance_observations(id TEXT PRIMARY KEY,metric_id TEXT NOT NULL,value TEXT NOT NULL,observed_on TEXT NOT NULL,source_id TEXT NOT NULL,source_version INTEGER NOT NULL,digest TEXT NOT NULL,quote TEXT NOT NULL,note TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'proposed',actor TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS assurance_tool_restore(employee TEXT PRIMARY KEY,removed TEXT NOT NULL,employee_version INTEGER NOT NULL);
        ''')

def installed(path=p.DEFAULT_DB):
    return bool(records('assurance_control','SELECT id FROM assurance_control',path=path))

def policy(mid,path=p.DEFAULT_DB):
    r=records('assurance_milestones','SELECT * FROM assurance_milestones WHERE mid=?',(mid,),path)
    return r[0] if r else None

def seed(mid,path=p.DEFAULT_DB):
    if not installed(path):return
    m=ms.milestone(mid,path)
    with p.connect(path) as db:
        db.execute('INSERT OR IGNORE INTO assurance_milestones(mid,legacy) VALUES(?,?)',(mid,int(m['state']=='approved')))
        domains={'endorsement':'Match the actual endorsement guide and distinguish innovation, viability and scalability evidence.','marketing':'Use specific audience, customer problem, market evidence and testable acquisition claims.','career_rnd':'Check data provenance, licensing, technical novelty and reproducibility.','edsync_product':'Check delivery feasibility, user workflows and pilot success criteria.','investors_grants':'Check funding assumptions, unit economics and financial consistency.','legal_ops':'Identify jurisdiction, source authority and operational/legal verification needs.','applications':'Use actual programme requirements, deadlines and the applicant’s verified experience.'}
        for key,desc in RUBRIC.items():
            if key=='context':desc+=' '+domains.get(team.project(m['project_id'],path)['scope'],'Apply the department’s actual evidence standard.')
            db.execute('INSERT OR IGNORE INTO assurance_rubrics(mid,criterion,description) VALUES(?,?,?)',(mid,key,desc))

def setup(path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:
        db.execute('INSERT OR IGNORE INTO assurance_control(id) VALUES(1)')
        migrated=db.execute("SELECT 1 FROM milestone_migrations WHERE id='assurance-tools-132'").fetchone()
        if not migrated:
            for e in db.execute('SELECT * FROM team_employees').fetchall():
                allowed=json.loads(e['allowed_tools']);new=list(allowed)
                if 'milestone.read_output' in allowed:new.append('assurance.workspace')
                if 'milestone.note' in allowed:new.extend(('assurance.record','assurance.scorecard'))
                new=list(dict.fromkeys(new))
                if new!=allowed:db.execute('UPDATE team_employees SET allowed_tools=?,version=version+1 WHERE id=?',(json.dumps(new),e['id']))
            db.execute("INSERT INTO milestone_migrations VALUES('assurance-tools-132')")
        for saved in db.execute('SELECT * FROM assurance_tool_restore').fetchall():
            e=db.execute('SELECT * FROM team_employees WHERE id=?',(saved['employee'],)).fetchone()
            if e and e['version']==saved['employee_version']:
                new=list(dict.fromkeys(json.loads(e['allowed_tools'])+json.loads(saved['removed'])))
                db.execute('UPDATE team_employees SET allowed_tools=?,version=version+1 WHERE id=?',(json.dumps(new),e['id']))
            db.execute('DELETE FROM assurance_tool_restore WHERE employee=?',(saved['employee'],))
    for m in ms.listing(path=path):
        seed(m['id'],path)
        if m['current_packet'] and m['state']!='approved' and not records('assurance_packets','SELECT packet_id FROM assurance_packets WHERE packet_id=?',(m['current_packet'],),path):
            from .workflow import changed
            changed(m['id'],'migration-132','Existing in-review packet needs the new evidence and quality gates',force=True,path=path)

def audit(db,mid,actor,event,detail):
    db.execute('INSERT INTO assurance_history(mid,actor,event,detail,created_at) VALUES(?,?,?,?,?)',(mid,actor,event,json.dumps(detail,ensure_ascii=False),p.stamp()))
    team.event(db,actor,'assurance_'+event,{'mid':mid,**detail})

def require_policy(mid,path):
    if not policy(mid,path):raise ValueError('Run the v1.32 setup before using this milestone register')
    return ms.milestone(mid,path)

def authority(mid,actor,path,lead=False):
    m=require_policy(mid,path);cfg=ms.managed(m['project_id'],path)
    allowed={'owner',cfg['lead']} if lead else set(ms.roster(m['project_id'],path))|{'owner'}
    if actor not in allowed:raise ValueError('This actor is outside the delegated project scope')
    if actor!='owner' and (not cfg['share_outputs'] or not ms.active(mid,path)[0]):raise ValueError('Project work or sharing is held')
    return m

def requirements(mid,path=p.DEFAULT_DB):return records('assurance_requirements','SELECT * FROM assurance_requirements WHERE mid=? ORDER BY created_at,id',(mid,),path)
def evidence(mid,path=p.DEFAULT_DB):return records('assurance_evidence','SELECT e.* FROM assurance_evidence e JOIN assurance_requirements r ON r.id=e.requirement_id WHERE r.mid=? ORDER BY e.created_at,e.id',(mid,),path)
def gaps(mid,path=p.DEFAULT_DB):return records('assurance_gaps','SELECT * FROM assurance_gaps WHERE mid=? ORDER BY created_at,id',(mid,),path)
def rubric(mid,path=p.DEFAULT_DB):return records('assurance_rubrics','SELECT * FROM assurance_rubrics WHERE mid=? ORDER BY criterion',(mid,),path)
def changes(pid,path=p.DEFAULT_DB):return records('assurance_changes','SELECT c.* FROM assurance_changes c JOIN milestones m ON m.id=c.origin_mid WHERE m.project_id=? ORDER BY c.created_at DESC',(pid,),path)

def touch(db,mid,actor,event,detail):
    db.execute('UPDATE assurance_milestones SET version=version+1,register_confirmed=CASE WHEN ? THEN 0 ELSE register_confirmed END WHERE mid=?',(int(event in ('requirement_added','rubric_changed')),mid))
    audit(db,mid,actor,event,detail)

def add_requirement(mid,key,title,critical,origin,actor='owner',path=p.DEFAULT_DB,sensitivity=None):
    authority(mid,actor,path)
    floor=team.project(ms.milestone(mid,path)['project_id'],path)['sensitivity']
    sensitivity=sensitivity or floor
    if sensitivity not in team.SENSITIVITIES or team.SENSITIVITIES.index(sensitivity)<team.SENSITIVITIES.index(floor):raise ValueError('Requirement privacy cannot be below project privacy')
    key=team.text(key,100,'Requirement key',True);title=team.text(title,1000,'Requirement',True);origin=team.text(origin,1000,'Requirement origin or locator',True)
    if type(critical) is not bool:raise ValueError('Choose whether this requirement is critical')
    ident=uuid4().hex
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT * FROM assurance_requirements WHERE mid=? AND requirement_key=?',(mid,key)).fetchone()
        if old:
            if (old['title'],old['critical'],old['origin'])!=(title,int(critical),origin):raise ValueError('Requirement key already has different content')
            return old['id']
        if db.execute('SELECT COUNT(*) FROM assurance_requirements WHERE mid=?',(mid,)).fetchone()[0]>=80:raise ValueError('Split the requirements across milestones; limit is 80')
        db.execute('INSERT INTO assurance_requirements(id,mid,requirement_key,title,critical,origin,sensitivity,actor,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(ident,mid,key,title,int(critical),origin,sensitivity,actor,p.stamp()))
        touch(db,mid,actor,'requirement_added',{'id':ident})
    from .workflow import changed
    changed(mid,'requirement:'+ident,'A requirement was added after packet assembly',path=path)
    return ident

def confirm(mid,expected,note,path=p.DEFAULT_DB):
    require_policy(mid,path);note=team.text(note,2000,'Register scope decision',True)
    with p.connect(path) as db:
        if not db.execute('UPDATE assurance_milestones SET register_confirmed=1,version=version+1 WHERE mid=? AND version=? AND register_confirmed=0',(mid,expected)).rowcount:raise ValueError('Register changed; reload before confirming its scope')
        audit(db,mid,'owner','register_confirmed',{'note':note,'requirements':len(requirements(mid,path))})

def set_rubric(mid,key,description,expected,path=p.DEFAULT_DB):
    require_policy(mid,path);description=team.text(description,1200,'Review criterion',True)
    with p.connect(path) as db:
        if not db.execute('UPDATE assurance_rubrics SET description=?,version=version+1 WHERE mid=? AND criterion=? AND version=?',(description,mid,key,expected)).rowcount:raise ValueError('Rubric changed; reload')
        touch(db,mid,'owner','rubric_changed',{'criterion':key})
    from .workflow import changed
    changed(mid,'rubric:'+key+':'+str(expected+1),'A quality criterion changed',path=path)

def pause_for_rollback(path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:
        for e in db.execute('SELECT * FROM team_employees').fetchall():
            allowed=json.loads(e['allowed_tools']);removed=sorted(set(allowed)&set(TOOLS))
            if removed:
                db.execute('INSERT OR REPLACE INTO assurance_tool_restore VALUES(?,?,?)',(e['id'],json.dumps(removed),e['version']+1))
                db.execute('UPDATE team_employees SET allowed_tools=?,version=version+1 WHERE id=?',(json.dumps([t for t in allowed if t not in TOOLS]),e['id']))
        for run in db.execute('SELECT project_id,allowed_tools,state FROM agentic_runs').fetchall():
            allowed=json.loads(run['allowed_tools'])
            if set(allowed)&set(TOOLS):db.execute("UPDATE agentic_runs SET allowed_tools=?,state=CASE WHEN state IN ('completed','cancelled') THEN state ELSE 'paused' END,version=version+1 WHERE project_id=?",(json.dumps([t for t in allowed if t not in TOOLS]),run['project_id']))
        db.execute("UPDATE milestone_projects SET enabled=0,hold='v1.32 rolled back; evidence/change gates unavailable; inspect before resuming',version=version+1")
        db.execute("UPDATE team_tasks SET state='paused',version=version+1 WHERE id IN (SELECT task_id FROM milestone_assignments) AND state NOT IN ('completed','cancelled')")
        db.execute("UPDATE milestone_cycles SET status='interrupted',error='v1.32 rolled back; inspect, no replay' WHERE status='running'")

def revise_requirement(ident,expected,title,critical,origin,note,path=p.DEFAULT_DB):
    rows=records('assurance_requirements','SELECT * FROM assurance_requirements WHERE id=?',(ident,),path)
    if not rows:raise ValueError('Requirement not found')
    old=rows[0];title=team.text(title,1000,'Requirement',True);origin=team.text(origin,1000,'Requirement origin',True);note=team.text(note,2000,'Requirement change rationale',True)
    if type(critical) is not bool:raise ValueError('Choose requirement criticality')
    with p.connect(path) as db:
        if not db.execute('UPDATE assurance_requirements SET title=?,critical=?,origin=?,version=version+1 WHERE id=? AND version=?',(title,int(critical),origin,ident,expected)).rowcount:raise ValueError('Requirement changed; reload')
        touch(db,old['mid'],'owner','requirement_added',{'id':ident,'old':old,'title':title,'critical':critical,'origin':origin,'note':note})
    from .workflow import changed
    changed(old['mid'],'requirement-edit:'+ident+':'+str(expected+1),'Owner changed a requirement: '+note,force=bool(ms.packet(old['mid'],path)),path=path)
