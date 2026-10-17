"""One scheduler and canonical project-task records for local research/drafts.

Uses existing runners, quality gates, budgets and revisions. Legacy queue imports
are resumable; delegated queue rows are references, never a second task state.
No sending, shell tools, automatic paid retries or automatic plan approval.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import time
from uuid import uuid4
from superhuman.projects import engine as projects
from superhuman.queue import engine as queue

DEFAULT_DB = projects.DEFAULT_DB
DEFAULT_QUEUE = queue.DEFAULT_DB


def initialize(path=DEFAULT_DB):
    projects.initialize(path)
    with projects.connect(path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS runtime_events(
          seq INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT,
          task_id TEXT, action TEXT NOT NULL, detail_json TEXT NOT NULL,
          created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS runtime_schedule(
          project_id TEXT PRIMARY KEY, served_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS runtime_imports(
          source TEXT NOT NULL, job_id TEXT NOT NULL, project_id TEXT NOT NULL UNIQUE,
          original_json TEXT NOT NULL, created_at TEXT NOT NULL,
          PRIMARY KEY(source,job_id));
        ''')


def event(action, pid=None, tid=None, detail=None, path=DEFAULT_DB):
    # Persist structured operational metadata, never raw exceptions or credentials.
    initialize(path)
    with projects.connect(path) as db:
        db.execute('INSERT INTO runtime_events(project_id,task_id,action,detail_json,created_at) VALUES(?,?,?,?,?)',
                   (pid, tid, action, json.dumps(detail or {}), projects.stamp()))


def history(pid=None, limit=100, path=DEFAULT_DB):
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('History limit must be 1 to 1000')
    initialize(path)
    with projects.connect(path) as db:
        if pid:
            rows=db.execute('SELECT * FROM runtime_events WHERE project_id=? ORDER BY seq DESC LIMIT ?', (pid,limit))
        else:
            rows=db.execute('SELECT * FROM runtime_events ORDER BY seq DESC LIMIT ?', (limit,))
        return [dict(r) for r in rows]


@contextmanager
def worker_lock(path=DEFAULT_DB):
    """OS lock: one unified scheduler per project DB, released on process exit.

    Existing project workers also have atomic per-project claims. Stop all old
    workers before switching; legacy running requests are never stolen.
    """
    lock=Path(str(Path(path).resolve())+'.runtime.lock')
    lock.parent.mkdir(parents=True,exist_ok=True)
    stream=lock.open('a+b')
    locked=False
    try:
        if os.name=='nt':
            import msvcrt
            stream.seek(0,2)
            if stream.tell()==0:
                stream.write(b'0');stream.flush()
            stream.seek(0)
            try:msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as exc:raise RuntimeError('Another unified worker is running for this database') from exc
        else:
            import fcntl
            try:fcntl.flock(stream.fileno(),fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:raise RuntimeError('Another unified worker is running for this database') from exc
        locked=True
        yield
    finally:
        if locked:
            if os.name=='nt':
                import msvcrt
                stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_UN)
        stream.close()


def validate_job(kind, workstream, title, details):
    from superhuman.core.router import WORKSTREAMS, route_task
    if kind not in ('research','collab'):
        raise ValueError('Only local research and collaboration drafts are executable')
    if workstream not in WORKSTREAMS:
        raise ValueError('Unknown workstream')
    if not isinstance(title,str) or not title.strip() or len(title)>200:
        raise ValueError('Title must contain 1 to 200 characters')
    if not isinstance(details,str) or len(details)>12000:
        raise ValueError('Details must be text up to 12000 characters')
    if route_task(title,details).approval_required:
        raise ValueError('External actions are not executable in v1.8; request a local draft instead')


def _insert_job(db, pid, kind, workstream, title, details, status='active'):
    now=projects.stamp()
    task={'id':'final','kind':kind,'title':title.strip(),'details':details,'depends_on':[],'checks':{}}
    db.execute('''INSERT INTO projects(id,workstream,objective,details,status,max_calls,used_calls,plan_json,error,created_at,updated_at)
                  VALUES(?,?,?,?,?,?,0,?,NULL,?,?)''',
               (pid,workstream,title.strip(),details,status,3 if kind=='collab' else 1,json.dumps({'tasks':[task]}),now,now))
    # A standalone job is its own final deliverable; no extra consolidation call.
    db.execute('''INSERT INTO project_tasks(project_id,id,kind,title,details,deps,checks,status)
                  VALUES(?,'final',?,?,?,'[]','{}','pending')''',(pid,kind,title.strip(),details))


def enqueue(kind, workstream, title, details='', path=DEFAULT_DB):
    validate_job(kind,workstream,title,details)
    initialize(path);pid=uuid4().hex[:12]
    with projects.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        _insert_job(db,pid,kind,workstream,title,details)
    event('job_enqueued',pid,detail={'kind':kind},path=path)
    return pid


def import_queue(queue_path=DEFAULT_QUEUE, path=DEFAULT_DB):
    """Called under worker_lock. Resume crash-interrupted imports without reruns.

    Reserve old row -> create inactive canonical task -> delegate old row ->
    activate canonical task. Deterministic IDs and the durable pointer let the
    next worker finish every interrupted stage. Already attempted/running jobs
    are intentionally not replayed. No source records or artifacts are deleted.
    """
    initialize(path)
    if not Path(queue_path).is_file():return []
    source=str(Path(queue_path).resolve());destination=str(Path(path).resolve())
    if source==destination:raise ValueError('Legacy queue and project database must be different files')
    imported=[]
    with queue.connect(queue_path) as db:
        rows=[dict(r) for r in db.execute("SELECT * FROM queue_jobs WHERE status IN ('queued','delegating','delegated') ORDER BY created_at,id")]
    for row in rows:
        pid='q'+hashlib.sha256((source+'\0'+row['id']).encode()).hexdigest()[:19]
        if row['status']=='queued':
            if row['attempts']!=0 or row['next_run_at']>time.time():continue
            try:validate_job(row['kind'],row['project'],row['title'],row['details'])
            except ValueError:
                with projects.connect(path) as db:
                    recorded=db.execute("SELECT 1 FROM runtime_events WHERE action='queue_import_skipped' AND task_id=?",(row['id'],)).fetchone()
                if not recorded:event('queue_import_skipped',tid=row['id'],detail={'reason':'Unsupported legacy task; inspect before migration'},path=path)
                continue
            pointer={'runtime_v18':{'project_id':pid,'project_db':destination},'previous_result_json':row['result_json'],'original_job':row}
            with queue.connect(queue_path) as db:
                db.execute('BEGIN IMMEDIATE')
                changed=db.execute("UPDATE queue_jobs SET status='delegating',result_json=?,updated_at=? WHERE id=? AND status='queued' AND attempts=0",
                                   (json.dumps(pointer),projects.stamp(),row['id'])).rowcount
                if not changed:continue
        else:
            pointer=json.loads(row['result_json'] or '{}')
            link=pointer.get('runtime_v18',{})
            if link.get('project_db')!=destination or link.get('project_id')!=pid:continue
            if row['status']=='delegated':
                with projects.connect(path) as db:
                    existing=db.execute('SELECT status FROM projects WHERE id=?',(pid,)).fetchone()
                if not existing:
                    raise RuntimeError('Delegated job is missing its canonical project; restore the correct database before proceeding')
                if existing['status']!='import_pending':continue
        original=pointer.get('original_job',dict(row))
        if row['status']!='queued' and 'original_job' not in pointer:
            original['status']='queued';original['result_json']=pointer.get('previous_result_json')
        with projects.connect(path) as db:
            db.execute('BEGIN IMMEDIATE')
            known=db.execute('SELECT project_id FROM runtime_imports WHERE source=? AND job_id=?',(source,row['id'])).fetchone()
            if not known:
                _insert_job(db,pid,row['kind'],row['project'],row['title'],row['details'],'import_pending')
                db.execute('INSERT INTO runtime_imports VALUES(?,?,?,?,?)',
                           (source,row['id'],pid,json.dumps(original),projects.stamp()))
        with queue.connect(queue_path) as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT status,result_json FROM queue_jobs WHERE id=?',(row['id'],)).fetchone()
            if current['status'] not in ('delegating','delegated') or json.loads(current['result_json'])!=pointer:
                raise RuntimeError('Legacy job changed during import; canonical job remains inactive')
            db.execute("UPDATE queue_jobs SET status='delegated',updated_at=? WHERE id=?",(projects.stamp(),row['id']))
        with projects.connect(path) as db:
            changed=db.execute("UPDATE projects SET status='active',updated_at=? WHERE id=? AND status='import_pending'",(projects.stamp(),pid)).rowcount
            if changed:
                db.execute('INSERT INTO runtime_events(project_id,task_id,action,detail_json,created_at) VALUES(?,NULL,?,?,?)',
                           (pid,'queue_imported',json.dumps({'legacy_job_id':row['id']}),projects.stamp()))
        imported.append({'legacy_job_id':row['id'],'project_id':pid})
    return imported


def tick(path=DEFAULT_DB, client=None, executor=None):
    """One execution, fairly selected across active projects. Caller holds lock."""
    initialize(path)
    with projects.connect(path) as db:
        candidates=[r['id'] for r in db.execute('''SELECT p.id FROM projects p LEFT JOIN runtime_schedule s ON s.project_id=p.id
             WHERE p.status='active' ORDER BY COALESCE(s.served_at,0),p.created_at,p.id''')]
    from superhuman.repairs.scheduler import order
    candidates=order(candidates,path)
    for pid in candidates:
        p=projects.get(pid,path)
        # An exception on one project must not starve unrelated work.
        try:
            task=projects.run_one(pid,path,client=client,executor=executor)
        except Exception as exc:
            task=next((t for t in projects.get(pid,path)['tasks'] if t['status']=='failed'),None)
            result={'project_id':pid,'task_id':task['id'] if task else None,'status':'error','error_type':type(exc).__name__}
            event('execution_error',pid,result['task_id'],{'error_type':type(exc).__name__},path)
        else:
            if task is None:continue
            result={'project_id':pid,'task_id':task['id'],'status':task['status'],'output':task['output']}
            event('task_completed',pid,task['id'],{'status':task['status']},path)
        with projects.connect(path) as db:
            db.execute('INSERT OR REPLACE INTO runtime_schedule VALUES(?,?)',(pid,time.time()))
        return result
    return None


def work(path=DEFAULT_DB, queue_path=DEFAULT_QUEUE, max_tasks=20, watch=False,
         poll_seconds=5, include_queue=True, client=None, executor=None, report=None):
    if type(max_tasks) is not int or not 1<=max_tasks<=1000:
        raise ValueError('max_tasks must be 1 to 1000')
    if not 1<=poll_seconds<=60:raise ValueError('poll_seconds must be 1 to 60')
    completed=[]
    with worker_lock(path):
        initialize(path)
        while len(completed)<max_tasks:
            if include_queue:import_queue(queue_path,path)
            result=tick(path,client,executor)
            if result:
                completed.append(result)
                if report:report(result)
            elif not watch:break
            else:time.sleep(poll_seconds)
    return completed


def status(path=DEFAULT_DB, queue_path=DEFAULT_QUEUE):
    initialize(path);result=[]
    for p in projects.listing(path):
        p=projects.get(p['id'],path)
        counts={}
        for t in p['tasks']:counts[t['status']]=counts.get(t['status'],0)+1
        attention=[]
        if p['status'] in ('new','plan_failed'):attention.append('Plan required')
        if p['status']=='plan_review':attention.append('Plan approval required')
        if p['status']=='budget_blocked':attention.append('API-attempt budget exhausted')
        if any(counts.get(s) for s in ('failed','interrupted','quality_blocked','rejected')):
            attention.append('Correction or explicit retry required; unaffected tasks may continue')
        if p['status']=='needs_review':attention.append('Final deliverable requires review')
        if p['status']=='import_pending':attention.append('Queue import will resume on next worker run')
        if counts.get('running'):attention.append('Running; if interrupted, inspect and recover explicitly')
        result.append({'id':p['id'],'objective':p['objective'],'status':p['status'],
                       'used_calls':p['used_calls'],'max_calls':p['max_calls'],'tasks':counts,'attention':attention})
    legacy={}
    if Path(queue_path).is_file():
        with queue.connect(queue_path) as db:
            legacy={r['status']:r['n'] for r in db.execute('SELECT status,COUNT(*) AS n FROM queue_jobs GROUP BY status')}
    return {'projects':result,'legacy_queue':legacy,
            'note':'Delegated legacy rows link to canonical project tasks. Only never-attempted queued jobs are imported.'}


def review(pid, tid, action, note='', path=DEFAULT_DB):
    initialize(path)
    # Check the actual artifact before accepting approval, not just its status.
    if action=='approve':
        p=projects.get(pid,path)
        t=next((t for t in p['tasks'] if t['id']==tid),None)
        if not t or t['status']!='needs_review':raise ValueError('Task is not awaiting review')
        projects._text(json.loads(t['result_json']))
    result=projects.review(pid,tid,action,note,path)
    event('review_'+action,pid,tid,path=path)
    return result


def retry(pid,tid,note,path=DEFAULT_DB):
    initialize(path)
    result=projects.retry(pid,tid,note,path)
    event('retry_authorized',pid,tid,path=path)
    return result
