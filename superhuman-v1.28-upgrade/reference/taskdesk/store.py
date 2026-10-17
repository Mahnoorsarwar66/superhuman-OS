"""Explicit task routing; legacy hashes and atomic approval remain compatible."""
from uuid import uuid4
from superhuman.projects import engine as p
from superhuman.runtime import engine as r
from superhuman.dialogue import store as d


def initialize(path=p.DEFAULT_DB):
    d.initialize(path)
    with p.connect(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS dialogue_routes(suggestion_id TEXT PRIMARY KEY,scope TEXT NOT NULL)')


SQL='''SELECT s.*,c.scope AS source_scope,c.title AS conversation_title,
       p.workstream AS project_scope,p.status AS project_status,p.objective AS project_title,
       p.used_calls,p.max_calls,rt.scope AS approved_scope
       FROM dialogue_suggestions s JOIN dialogue_threads c ON c.id=s.thread_id
       LEFT JOIN projects p ON p.id=s.project_id
       LEFT JOIN dialogue_routes rt ON rt.suggestion_id=s.id'''


def get(key,path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:row=db.execute(SQL+' WHERE s.id=?',(key,)).fetchone()
    if row is None:raise ValueError('Task suggestion not found')
    return dict(row)


def listing(status='proposed',page=1,path=p.DEFAULT_DB):
    if status not in ('proposed','approved','dismissed') or type(page) is not int or not 1<=page<=10000:
        raise ValueError('Choose a valid task page')
    initialize(path)
    with p.connect(path) as db:
        return [dict(row) for row in db.execute(SQL+' WHERE s.status=? ORDER BY s.created_at DESC,s.id LIMIT 50 OFFSET ?',(status,(page-1)*50))]


def counts(path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:
        result={row['status']:row['n'] for row in db.execute('SELECT status,COUNT(*) AS n FROM dialogue_suggestions GROUP BY status')}
        result['needs_review']=db.execute("SELECT COUNT(*) FROM dialogue_suggestions s JOIN projects p ON p.id=s.project_id WHERE s.status='approved' AND p.status='needs_review'").fetchone()[0]
        result['blocked']=db.execute("SELECT COUNT(*) FROM dialogue_suggestions s JOIN projects p ON p.id=s.project_id WHERE s.status='approved' AND (p.status IN ('quality_blocked','budget_blocked','dependency_blocked','failed','interrupted') OR EXISTS (SELECT 1 FROM project_tasks t WHERE t.project_id=p.id AND t.status IN ('quality_blocked','failed','interrupted','rejected')))").fetchone()[0]
    return result


def chosen_scope(row):return row['project_scope'] or row['approved_scope'] or row['source_scope']


def approve(thread_id,suggestion_id,expected_hash,title,details,path=p.DEFAULT_DB,scope=None):
    title=d.text(title,180,'Task title');details=d.text(details,6000,'Task instructions')
    initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute(SQL+' WHERE s.id=? AND s.thread_id=?',(suggestion_id,thread_id)).fetchone()
        if row is None or row['proposal_hash']!=expected_hash:raise ValueError('Suggestion changed or unavailable. Reload before approval.')
        destination=scope if scope not in (None,'') else chosen_scope(row)
        if destination not in d.scopes():raise ValueError('Choose a configured workstream')
        approved_hash=d.proposal_hash(row['kind'],title,details,destination)
        if row['status']=='approved':
            # Approvals before v1.15 hashed the edited text without its route.
            wanted=approved_hash if row['approved_scope'] is not None else d.proposal_hash(row['kind'],title,details,'')
            if row['approved_hash']!=wanted or row['project_scope']!=destination:
                raise ValueError('This task was already approved with different text or workstream. Open its existing project.')
            return row['project_id']
        if row['status']!='proposed':raise ValueError('This suggestion is no longer awaiting approval')
        r.validate_job(row['kind'],destination,title,details)
        pid=uuid4().hex[:12]
        r._insert_job(db,pid,row['kind'],destination,title,details)
        db.execute('INSERT INTO dialogue_routes VALUES(?,?)',(suggestion_id,destination))
        db.execute("UPDATE dialogue_suggestions SET status='approved',approved_hash=?,project_id=?,decided_at=? WHERE id=?",(approved_hash,pid,p.stamp(),suggestion_id))
        d.event(db,'conversation_task_approved',thread_id,row['turn_id'],pid,suggestion_id=suggestion_id,
                proposal_hash=expected_hash,approved_hash=approved_hash,source_scope=row['source_scope'],approved_scope=destination)
    return pid
