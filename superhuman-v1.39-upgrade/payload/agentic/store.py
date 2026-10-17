"""Canonical project integration, durable action ledger and owner controls."""
import hashlib,json,sqlite3
from contextlib import nullcontext
from uuid import uuid4
from superhuman.projects import engine as p
from superhuman.runtime import engine as runtime

ACTIVE=('ready','running','pause_requested','cancel_requested','budget_blocked')

def initialize(path=p.DEFAULT_DB):
    runtime.initialize(path)
    with p.connect(path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS agentic_runs(
          project_id TEXT PRIMARY KEY,allowed_tools TEXT NOT NULL,required_tools TEXT NOT NULL,
          max_actions INTEGER NOT NULL,state TEXT NOT NULL,version INTEGER NOT NULL,
          failures INTEGER NOT NULL DEFAULT 0,error TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS agentic_actions(
          id TEXT PRIMARY KEY,project_id TEXT NOT NULL,ordinal INTEGER NOT NULL,
          status TEXT NOT NULL,tool TEXT NOT NULL DEFAULT '',arguments_json TEXT NOT NULL DEFAULT '{}',
          rationale TEXT NOT NULL DEFAULT '',result_json TEXT,verification_json TEXT,
          fingerprint TEXT,created_at TEXT NOT NULL,finished_at TEXT,
          UNIQUE(project_id,ordinal));
        CREATE TABLE IF NOT EXISTS agentic_events(
          seq INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT NOT NULL,action TEXT NOT NULL,
          detail_json TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS agentic_action_project ON agentic_actions(project_id,ordinal);
        ''')

def encode(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,default=str)
def fingerprint(tool,args):return hashlib.sha256(encode({'tool':tool,'arguments':args}).encode()).hexdigest()
def event(db,pid,action,detail=None):db.execute('INSERT INTO agentic_events(project_id,action,detail_json,created_at) VALUES(?,?,?,?)',(pid,action,encode(detail or {}),p.stamp()))
def update(db,pid,state,error=None):db.execute('UPDATE agentic_runs SET state=?,error=?,version=version+1,updated_at=? WHERE project_id=?',(state,error,p.stamp(),pid))

def create(scope,title,instruction,allowed_tools,required_tools=(),max_calls=8,max_actions=12,path=p.DEFAULT_DB):
    from superhuman.core.router import WORKSTREAMS
    from .tools import REGISTRY
    if scope not in WORKSTREAMS:raise ValueError('Choose a configured department')
    if not isinstance(title,str) or not 1<=len(title.strip())<=180 or not isinstance(instruction,str) or not 1<=len(instruction.strip())<=12000:raise ValueError('Provide a title and instructions within the displayed limits')
    if type(max_calls) is not int or not 1<=max_calls<=100 or type(max_actions) is not int or not 2<=max_actions<=40:raise ValueError('Use 1–100 model requests and 2–40 decision steps')
    allowed=sorted(set(allowed_tools));required=sorted(set(required_tools))
    if not allowed or any(x not in REGISTRY for x in allowed) or any(x not in allowed for x in required) or 'inbox.queue_sync' in required:raise ValueError('Choose known tools; required tools must be permitted for this run')
    initialize(path);pid=uuid4().hex[:12];at=p.stamp()
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        runtime._insert_job(db,pid,'agentic',scope,title.strip(),instruction.strip())
        db.execute('UPDATE projects SET max_calls=? WHERE id=?',(max_calls,pid))
        db.execute("INSERT INTO agentic_runs VALUES(?,?,?,?, 'ready',1,0,NULL,?,?)",(pid,encode(allowed),encode(required),max_actions,at,at))
        event(db,pid,'run_created',{'allowed_tools':allowed,'required_tools':required,'max_calls':max_calls,'max_actions':max_actions})
    return pid

def get(pid,path=p.DEFAULT_DB):
    from superhuman.departments.store import readonly,tables,rows
    with readonly(path) as db:
        if 'agentic_runs' not in tables(db):raise ValueError('Agent run not found')
        row=db.execute('SELECT * FROM agentic_runs WHERE project_id=?',(pid,)).fetchone()
        if not row:raise ValueError('Agent run not found')
        result=dict(row);result['allowed_tools']=json.loads(result['allowed_tools']);result['required_tools']=json.loads(result['required_tools'])
        result['actions']=rows(db,'SELECT * FROM agentic_actions WHERE project_id=? ORDER BY ordinal',(pid,))
        result['events']=rows(db,'SELECT * FROM agentic_events WHERE project_id=? ORDER BY seq DESC LIMIT 100',(pid,))
    result['project']=p.get(pid,path);return result

def listing(path=p.DEFAULT_DB):
    from superhuman.departments.store import readonly,tables,rows
    with readonly(path) as db:
        if 'agentic_runs' not in tables(db):return []
        return rows(db,'SELECT r.*,p.objective,p.workstream,p.used_calls,p.max_calls FROM agentic_runs r JOIN projects p ON p.id=r.project_id ORDER BY r.updated_at DESC')

def runnable(pid,path=p.DEFAULT_DB):
    from superhuman.departments.store import readonly,tables
    with readonly(path) as db:
        if 'agentic_runs' not in tables(db):return True
        row=db.execute('SELECT r.state,p.used_calls,p.max_calls FROM agentic_runs r JOIN projects p ON p.id=r.project_id WHERE r.project_id=?',(pid,)).fetchone()
        if not row:return True
        return row['state']=='ready' or row['state']=='budget_blocked' and row['used_calls']<row['max_calls']

def recover(path=p.DEFAULT_DB):
    from superhuman.departments.store import readonly,tables
    with readonly(path) as db:
        if 'agentic_runs' not in tables(db):return 0
    restore_review_records(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        found=[dict(r) for r in db.execute("SELECT * FROM agentic_runs WHERE state IN ('running','pause_requested','cancel_requested')")]
        for row in found:
            pid=row['project_id'];cancel=row['state']=='cancel_requested'
            db.execute("UPDATE agentic_actions SET status='interrupted',verification_json=?,finished_at=? WHERE project_id=? AND status IN ('deciding','executing')",(encode({'verified':False,'reason':'Worker restarted; previous request/action may have happened'}),p.stamp(),pid))
            update(db,pid,'cancelled' if cancel else 'interrupted','Inspect the last action before authorizing continuation')
            db.execute('UPDATE project_tasks SET status=?,error=? WHERE project_id=? AND kind=\'agentic\'',('cancelled' if cancel else 'interrupted','Worker restarted; no automatic replay',pid))
            if cancel:db.execute("UPDATE projects SET status='cancelled' WHERE id=?",(pid,))
            event(db,pid,'worker_restart_no_replay')
    return len(found)

def control(pid,expected,action,note='',path=p.DEFAULT_DB,_db=None):
    if not isinstance(note,str) or len(note)>2000:raise ValueError('Use a note of at most 2000 characters')
    with (p.connect(path) if _db is None else nullcontext(_db)) as db:
        if _db is None:db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM agentic_runs WHERE project_id=?',(pid,)).fetchone()
        if not row:raise ValueError('Agent run not found')
        if row['version']!=expected:raise ValueError('Run changed; reopen the current page before acting')
        state=row['state']
        if action=='pause':
            if state not in ('ready','running','budget_blocked'):raise ValueError('This run cannot be paused now')
            update(db,pid,'pause_requested' if state=='running' else 'paused')
        elif action=='cancel':
            if state in ('completed','cancelled'):raise ValueError('Run is already finished')
            update(db,pid,'cancel_requested' if state=='running' else 'cancelled')
            if state!='running':
                db.execute("UPDATE projects SET status='cancelled',updated_at=? WHERE id=?",(p.stamp(),pid));db.execute("UPDATE project_tasks SET status='cancelled' WHERE project_id=?",(pid,))
        elif action=='approve_action':
            if state!='awaiting_permission':raise ValueError('No action awaits permission')
            pending=db.execute("SELECT * FROM agentic_actions WHERE project_id=? AND status='awaiting_permission' ORDER BY ordinal DESC LIMIT 1",(pid,)).fetchone()
            if not pending:raise ValueError('Pending action changed')
            db.execute("UPDATE agentic_actions SET status='approved' WHERE id=?",(pending['id'],));update(db,pid,'ready')
        elif action=='resume':
            rejected=state=='completed' and db.execute("SELECT status FROM project_tasks WHERE project_id=? AND id='final'",(pid,)).fetchone()['status']=='rejected'
            if state not in ('paused','needs_review','interrupted','budget_blocked','step_limit') and not rejected:raise ValueError('This run cannot be resumed now')
            if (state in ('interrupted','needs_review') or rejected) and not note.strip():raise ValueError('Record what you inspected and explicitly authorize continuation')
            if state=='step_limit':raise ValueError('This run reached its decision-step limit. Start a new scoped run using the saved evidence.')
            db.execute("UPDATE agentic_actions SET status='abandoned' WHERE project_id=? AND status='interrupted'",(pid,))
            db.execute("UPDATE agentic_runs SET failures=0 WHERE project_id=?",(pid,));update(db,pid,'ready')
            db.execute("UPDATE projects SET status='active',updated_at=? WHERE id=?",(p.stamp(),pid));db.execute("UPDATE project_tasks SET status='pending',token=NULL,error=NULL WHERE project_id=? AND status IN ('interrupted','failed','rejected','agentic_unavailable')",(pid,))
        else:raise ValueError('Unknown control')
        event(db,pid,action,{'note':note})

def quarantine_for_rollback(path=p.DEFAULT_DB):
    """Keep all new-kind tasks out of older runtimes, including later retries."""
    from superhuman.departments.store import readonly,tables
    from superhuman.hosted import jobs
    jobs.pause(True,path)
    with readonly(path) as check:
        if 'agentic_runs' not in tables(check):return
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        runs=[dict(r) for r in db.execute("SELECT * FROM agentic_runs")]
        for run in runs:
            pid=run['project_id']
            old=db.execute("SELECT p.status AS project_status,t.status AS task_status FROM projects p JOIN project_tasks t ON t.project_id=p.id WHERE p.id=? AND t.id='final'",(pid,)).fetchone()
            if not old or old['task_status']=='agentic_unavailable':continue
            detail={'previous_run_state':run['state'],**dict(old)}
            if run['state'] not in ('completed','cancelled'):update(db,pid,'paused','Code rolled back; reinstall v1.24 before resuming')
            db.execute("UPDATE project_tasks SET status='agentic_unavailable',token=NULL,started=NULL WHERE project_id=? AND kind='agentic'",(pid,))
            db.execute("UPDATE projects SET status='dependency_blocked' WHERE id=?",(pid,))
            event(db,pid,'rollback_quarantine',detail)

def restore_review_records(path=p.DEFAULT_DB):
    """After reinstall, restore finished review/cancel state without starting work."""
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        for row in db.execute("SELECT r.project_id,r.state FROM agentic_runs r JOIN project_tasks t ON t.project_id=r.project_id WHERE r.state IN ('completed','cancelled') AND t.id='final' AND t.status='agentic_unavailable'").fetchall():
            e=db.execute("SELECT detail_json FROM agentic_events WHERE project_id=? AND action='rollback_quarantine' ORDER BY seq DESC LIMIT 1",(row['project_id'],)).fetchone()
            if not e:continue
            detail=json.loads(e[0])
            if detail.get('previous_run_state')!=row['state']:continue
            db.execute("UPDATE projects SET status=? WHERE id=?",(detail['project_status'],row['project_id']))
            db.execute("UPDATE project_tasks SET status=? WHERE project_id=? AND id='final'",(detail['task_status'],row['project_id']))
            event(db,row['project_id'],'review_state_restored_after_reinstall')
