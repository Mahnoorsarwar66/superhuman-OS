"""Persistent objective scope over team assignments and the canonical cost ledger.

Enrollment is explicit and only before execution. Legacy tasks are not reclassified.
All mutating entry points here are owner controls, not registered model tools.
"""
import json
import time
from uuid import uuid4

from superhuman.projects import engine as p
from superhuman.departments.store import readonly, tables


class ObjectiveBlocked(ValueError):
    """A known pre-execution policy refusal; no tool side effect has occurred."""


def initialize(path=p.DEFAULT_DB):
    with p.connect(path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS workforce_objectives(
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL, root_task_id TEXT UNIQUE NOT NULL,
          lead TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'active', version INTEGER NOT NULL DEFAULT 1,
          current_plan INTEGER NOT NULL DEFAULT 1, max_cost INTEGER NOT NULL, max_requests INTEGER NOT NULL,
          max_revisions INTEGER NOT NULL, revisions_used INTEGER NOT NULL DEFAULT 0,
          started REAL NOT NULL, deadline REAL NOT NULL, origin_json TEXT NOT NULL,
          last_signature TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS workforce_objective_tasks(
          task_id TEXT PRIMARY KEY, objective_id TEXT NOT NULL, plan_version INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS workforce_objective_members ON workforce_objective_tasks(objective_id);
        CREATE TABLE IF NOT EXISTS workforce_objective_plans(
          objective_id TEXT NOT NULL, version INTEGER NOT NULL, brief TEXT NOT NULL,
          criteria TEXT NOT NULL, impact TEXT NOT NULL, created_at TEXT NOT NULL,
          PRIMARY KEY(objective_id,version));
        CREATE TABLE IF NOT EXISTS workforce_objective_costs(
          cost_id TEXT PRIMARY KEY, objective_id TEXT NOT NULL, task_id TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS workforce_objective_ledger ON workforce_objective_costs(objective_id);
        ''')


def memberships(path=p.DEFAULT_DB):
    with readonly(path) as db:
        if 'workforce_objective_tasks' not in tables(db):
            return {}
        return dict(db.execute('SELECT task_id,objective_id FROM workforce_objective_tasks'))


def listing(path=p.DEFAULT_DB):
    with readonly(path) as db:
        if 'workforce_objectives' not in tables(db):
            return []
        return [dict(row) for row in db.execute('SELECT * FROM workforce_objectives ORDER BY created_at,id')]


def for_task(db, task_id):
    if 'workforce_objective_tasks' not in tables(db):
        return None
    row = db.execute('SELECT o.* FROM workforce_objectives o JOIN workforce_objective_tasks t '
                     'ON t.objective_id=o.id WHERE t.task_id=?', (task_id,)).fetchone()
    return dict(row) if row else None


def usage(db, ident):
    row = db.execute('SELECT COUNT(*) requests,COALESCE(SUM(c.charged_text+c.charged_tools),0) cost,'
                     "COALESCE(SUM(c.state IN ('reserved','uncertain','overrun')),0) unresolved "
                     'FROM workforce_objective_costs o JOIN team_costs c ON c.id=o.cost_id '
                     'WHERE o.objective_id=?', (ident,)).fetchone()
    return dict(row)


def reason(db, objective, capacity=False, task_id=None):
    if objective['state'] != 'active':
        return 'Objective is ' + objective['state'] + '; inspect its controls'
    parent = db.execute('SELECT status FROM team_projects WHERE id=?', (objective['project_id'],)).fetchone()
    if not parent or parent['status'] != 'active':
        return 'Objective business project is paused or finished'
    settings = db.execute('SELECT enabled,hold FROM team_settings WHERE id=1').fetchone()
    if not settings or not settings['enabled'] or settings['hold']:
        return 'Objective execution is blocked by paused team controls'
    if time.time() >= objective['deadline']:
        return 'Objective wall-time allowance expired; owner must amend its total allowance'
    consumed = usage(db, objective['id'])
    if consumed['cost'] > objective['max_cost']:
        return 'Objective dollar allowance exceeded; reconcile charges or amend its total allowance'
    if capacity and consumed['cost'] >= objective['max_cost']:
        return 'Objective dollar allowance exhausted'
    if capacity and consumed['requests'] >= objective['max_requests']:
        return 'Objective request allowance exhausted'
    if task_id:
        other = db.execute("SELECT 1 FROM workforce_objective_tasks m JOIN team_tasks t ON t.id=m.task_id "
                           "WHERE m.objective_id=? AND t.id<>? AND (t.state='dispatched' OR EXISTS "
                           "(SELECT 1 FROM project_tasks r WHERE r.project_id=t.run_id AND r.status='running'))",
                           (objective['id'], task_id)).fetchone()
        if other:
            return 'Another assignment owns this objective execution slot; execution is sequential'
    return ''


def task_reason(item, path=p.DEFAULT_DB):
    with readonly(path) as db:
        objective = for_task(db, item['id'])
        return reason(db, objective, capacity=not item.get('run_id'), task_id=item['id']) if objective else ''


def dispatch_check(db, item):
    objective = for_task(db, item['id'])
    if objective:
        problem = reason(db, objective, capacity=True, task_id=item['id'])
        if problem:
            raise ValueError(problem)


def reserve_check(db, task_id, amount):
    """Runs inside budget.reserve's BEGIN IMMEDIATE, before ledger insertion."""
    objective = for_task(db, task_id)
    if not objective:
        return None
    from .budget import BudgetBlocked
    problem = reason(db, objective, capacity=True)
    consumed = usage(db, objective['id'])
    if not problem and consumed['cost'] + amount > objective['max_cost']:
        problem = 'Insufficient unreserved dollars in the objective allowance'
    if not problem and db.execute("SELECT 1 FROM workforce_objective_costs o JOIN team_costs c ON c.id=o.cost_id "
                                  "WHERE o.objective_id=? AND c.state='reserved'", (objective['id'],)).fetchone():
        problem = 'An objective provider request is already in flight; execution is sequential'
    if problem:
        raise BudgetBlocked(problem)
    return objective['id']


def consume_revision(db, task_id):
    objective = for_task(db, task_id)
    if objective:
        if objective['state'] in ('completed', 'cancelled'):
            raise ValueError('Cannot revise work in a finished objective')
        if objective['revisions_used'] >= objective['max_revisions']:
            raise ValueError('Objective revision allowance exhausted; owner must amend its total allowance')
        db.execute('UPDATE workforce_objectives SET revisions_used=revisions_used+1,version=version+1 '
                   'WHERE id=?', (objective['id'],))


def bind(db, task_id, objective_id=None, parent_id=None, actor='owner'):
    """Called in the same transaction as task creation; parent scope is immutable."""
    inherited = for_task(db, parent_id) if parent_id else None
    if inherited:
        if objective_id and objective_id != inherited['id']:
            raise ValueError('A child cannot escape its parent objective allowance')
        objective_id = inherited['id']
    from .budget import billing_context
    context = for_task(db, billing_context.get().get('task_id'))
    if actor != 'owner' and context:
        if objective_id and objective_id != context['id']:
            raise ValueError('Coordinator cannot create work in another objective')
        objective_id = context['id']
    task = db.execute('SELECT * FROM team_tasks WHERE id=?', (task_id,)).fetchone()
    if not objective_id:
        if actor != 'owner' and 'workforce_objectives' in tables(db) and db.execute(
                'SELECT 1 FROM workforce_objectives WHERE project_id=?', (task['project_id'],)).fetchone():
            raise ValueError('Choose an objective before automatically extending this project')
        return
    if 'workforce_objectives' not in tables(db):
        raise ValueError('Objective not found')
    row = db.execute('SELECT * FROM workforce_objectives WHERE id=?', (objective_id,)).fetchone()
    if not row or row['project_id'] != task['project_id']:
        raise ValueError('Objective belongs to another project or does not exist')
    if row['state'] not in ('active', 'paused', 'held'):
        raise ValueError('Cannot add work to a finished objective')
    db.execute('INSERT INTO workforce_objective_tasks VALUES(?,?,?)',
               (task_id, objective_id, row['current_plan']))


def invoke_check(cost_id, path=p.DEFAULT_DB):
    """Recheck controls after local preparation, immediately before provider invocation."""
    from .budget import BudgetBlocked
    with readonly(path) as db:
        if 'workforce_objective_costs' not in tables(db):
            return
        row = db.execute('SELECT o.* FROM workforce_objectives o JOIN workforce_objective_costs c '
                         'ON o.id=c.objective_id WHERE c.cost_id=?', (cost_id,)).fetchone()
        if row:
            problem = reason(db, dict(row))
            if problem:
                raise BudgetBlocked(problem)


def tool_check(run_id, name, path=p.DEFAULT_DB):
    with readonly(path) as db:
        if not {'workforce_objective_tasks', 'team_tasks'} <= tables(db):
            return
        task = db.execute('SELECT id FROM team_tasks WHERE run_id=?', (run_id,)).fetchone()
        objective = for_task(db, task['id']) if task else None
        if not objective:
            return
        problem = reason(db, objective)
        if not problem and name == 'inbox.queue_sync':
            problem = 'Asynchronous inbox work has no objective-bound adapter; use a separately authorized workflow'
        if problem:
            raise ObjectiveBlocked(problem)
    from .work import run_gate
    allowed, problem = run_gate(run_id, path)
    if not allowed:
        raise ObjectiveBlocked(problem)


def verify_accepted(ident, path=p.DEFAULT_DB):
    """Reuse the existing artifact/evidence contracts without a nested write transaction."""
    from superhuman.agentic import tools
    verified = {}
    with readonly(path) as db:
        members = db.execute('SELECT t.* FROM team_tasks t JOIN workforce_objective_tasks m '
                             'ON t.id=m.task_id WHERE m.objective_id=?', (ident,)).fetchall()
        if not members or any(task['state'] != 'completed' for task in members):
            raise ValueError('Every objective assignment must pass its existing output review')
        for task in members:
            result = db.execute("SELECT result_json FROM project_tasks WHERE project_id=? AND id='final' AND status='approved'",
                                (task['run_id'],)).fetchone()
            if not result:
                raise ValueError('Objective assignment has no accepted execution record')
            data = json.loads(result['result_json'])
            p._text(data)
            if not data.get('evidence_action_ids'):
                raise ValueError('Accepted assignment has no recorded execution evidence')
            for aid in data['evidence_action_ids']:
                action = db.execute('SELECT * FROM agentic_actions WHERE project_id=? AND id=?',
                                    (task['run_id'], aid)).fetchone()
                if not action or action['status'] not in ('succeeded', 'cached') or not json.loads(action['verification_json']).get('verified'):
                    raise ValueError('Accepted execution evidence changed or is unverified')
                tools.verify_saved(dict(action), task['owner'], path)
            verified[task['id']] = (task['version'], result['result_json'])
    return verified


def checked_limits(cost, requests, seconds, revisions):
    from .budget import micro
    amount = micro(cost)
    if amount <= 0 or type(requests) is not int or not 1 <= requests <= 2147483647:
        raise ValueError('Provide positive total dollars and model-request attempts')
    if type(seconds) is not int or not 1 <= seconds <= 365 * 86400:
        raise ValueError('Total wall time must be 1 second to 365 days')
    if type(revisions) is not int or not 0 <= revisions <= 1000:
        raise ValueError('Provide a revision allowance between 0 and 1000')
    return amount


def get(ident, path=p.DEFAULT_DB):
    with readonly(path) as db:
        if 'workforce_objectives' not in tables(db):
            raise ValueError('Objective not found')
        row = db.execute('SELECT * FROM workforce_objectives WHERE id=?', (ident,)).fetchone()
        if not row:
            raise ValueError('Objective not found')
        result = dict(row)
        result['usage'] = usage(db, ident)
        result['plans'] = [dict(r) for r in db.execute(
            'SELECT * FROM workforce_objective_plans WHERE objective_id=? ORDER BY version', (ident,))]
        result['tasks'] = [dict(r) for r in db.execute(
            'SELECT t.id,t.title,t.owner,t.state,t.run_id FROM team_tasks t JOIN workforce_objective_tasks m '
            'ON m.task_id=t.id WHERE m.objective_id=? ORDER BY t.created_at,t.id', (ident,))]
        result['blocker'] = '' if result['state'] in ('completed', 'cancelled') else reason(db, result, capacity=True)
        return result


def create(task_id, expected_task, cost, requests, seconds, revisions, note, path=p.DEFAULT_DB):
    from . import store
    amount = checked_limits(cost, requests, seconds, revisions)
    note = store.text(note, 2000, 'Objective authorization note', True)
    store.initialize(path)
    initialize(path)
    ident, started = uuid4().hex, time.time()
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        task = db.execute('SELECT * FROM team_tasks WHERE id=?', (task_id,)).fetchone()
        if not task or task['version'] != expected_task:
            raise ValueError('Task changed; reload before creating its objective')
        if task['run_id'] or task['attempts'] or task['parent_id'] or task['state'] not in ('queued', 'ready', 'owner_review'):
            raise ValueError('Only an unstarted root assignment can begin an objective')
        if for_task(db, task_id) or db.execute('SELECT 1 FROM team_tasks WHERE parent_id=?', (task_id,)).fetchone():
            raise ValueError('Task already has objective scope or existing handoffs')
        if db.execute('SELECT 1 FROM team_costs WHERE task_id=?', (task_id,)).fetchone():
            raise ValueError('Existing spending cannot be reset by objective enrollment')
        if 'milestone_assignments' in tables(db) and db.execute(
                'SELECT 1 FROM milestone_assignments WHERE task_id=?', (task_id,)).fetchone():
            raise ValueError('Milestone enrollment needs an explicit work-package migration; use an ordinary assignment')
        if 'milestone_projects' in tables(db) and db.execute(
                'SELECT 1 FROM milestone_projects WHERE project_id=?', (task['project_id'],)).fetchone():
            raise ValueError('Milestone project enrollment needs an explicit work-package migration')
        origin = {'task_id': task_id}
        if 'conversation_jobs' in tables(db):
            job = db.execute('SELECT turn_id,room_id,request FROM conversation_jobs WHERE task_id=?', (task_id,)).fetchone()
            if job:
                origin.update(dict(job))
        brief = origin.get('request', task['instruction'])
        db.execute('INSERT INTO workforce_objectives(id,project_id,root_task_id,lead,max_cost,max_requests,'
                   'max_revisions,started,deadline,origin_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                   (ident, task['project_id'], task_id, task['owner'], amount, requests, revisions,
                    started, started + seconds, store.encode(origin), p.stamp()))
        db.execute('INSERT INTO workforce_objective_tasks VALUES(?,?,1)', (task_id, ident))
        db.execute('INSERT INTO workforce_objective_plans VALUES(?,1,?,?,?,?)',
                   (ident, brief, task['acceptance'], note, p.stamp()))
        store.event(db, 'owner', 'objective_created', {'objective_id': ident, 'task_id': task_id,
                    'limits': [amount, requests, seconds, revisions], 'note': note})
    return ident


def amend(ident, expected, cost, requests, seconds, revisions, note, path=p.DEFAULT_DB):
    from . import store
    amount = checked_limits(cost, requests, seconds, revisions)
    note = store.text(note, 2000, 'Allowance change reason', True)
    get(ident, path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM workforce_objectives WHERE id=?', (ident,)).fetchone()
        if not row or row['version'] != expected or row['state'] in ('completed', 'cancelled'):
            raise ValueError('Objective changed or finished; reload')
        consumed = usage(db, ident)
        if amount < consumed['cost'] or requests < consumed['requests'] or revisions < row['revisions_used']:
            raise ValueError('Total allowances cannot be below consumed or reserved work')
        if row['started'] + seconds <= time.time():
            raise ValueError('The total wall-time allowance would already be expired')
        db.execute("UPDATE workforce_objectives SET max_cost=?,max_requests=?,max_revisions=?,deadline=?,"
                   "version=version+1,last_signature='' WHERE id=?",
                   (amount, requests, revisions, row['started'] + seconds, ident))
        store.event(db, 'owner', 'objective_allowance_changed', {'objective_id': ident,
                    'before': dict(row), 'after_limits': [amount, requests, seconds, revisions], 'note': note})


def revise_plan(ident, expected, brief, criteria, impact, path=p.DEFAULT_DB):
    """Initial planning revisions only; active-work impact propagation is WF03 work."""
    from . import store
    brief = store.text(brief, 5000, 'Owner brief', True)
    criteria = store.text(criteria, 1500, 'Success criteria', True)
    impact = store.text(impact, 2000, 'Impact assessment', True)
    get(ident, path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM workforce_objectives WHERE id=?', (ident,)).fetchone()
        if not row or row['version'] != expected or row['state'] not in ('active', 'paused'):
            raise ValueError('Objective changed or cannot be revised now')
        members = db.execute('SELECT t.* FROM team_tasks t JOIN workforce_objective_tasks m ON t.id=m.task_id '
                             'WHERE m.objective_id=?', (ident,)).fetchall()
        if len(members) != 1 or members[0]['run_id']:
            raise ValueError('Started work or handoffs require a reviewed impact migration; pause the objective first')
        if 'conversation_jobs' in tables(db) and db.execute(
                'SELECT 1 FROM conversation_jobs WHERE task_id=?', (row['root_task_id'],)).fetchone():
            raise ValueError('Conversation brief changes require the conversation revision workflow; original authority is preserved')
        consume_revision(db, row['root_task_id'])
        version = row['current_plan'] + 1
        db.execute('INSERT INTO workforce_objective_plans VALUES(?,?,?,?,?,?)',
                   (ident, version, brief, criteria, impact, p.stamp()))
        db.execute("UPDATE workforce_objectives SET current_plan=?,last_signature='' WHERE id=?", (version, ident))
        db.execute('UPDATE workforce_objective_tasks SET plan_version=? WHERE objective_id=?', (version, ident))
        db.execute("UPDATE team_tasks SET instruction=?,acceptance=?,owner_grant=0,state='queued',version=version+1,updated_at=? WHERE id=?",
                   (brief, criteria, p.stamp(), row['root_task_id']))
        store.event(db, 'owner', 'objective_plan_revised', {'objective_id': ident, 'plan_version': version, 'impact': impact})


def control(ident, expected, action, note, path=p.DEFAULT_DB):
    from . import store
    note = store.text(note, 2000, 'Objective decision rationale', True)
    transitions = {'pause': (('active', 'held'), 'paused'), 'resume': (('paused', 'held'), 'active'),
                   'cancel': (('active', 'paused', 'held'), 'cancelled'), 'complete': (('active', 'paused'), 'completed')}
    if action not in transitions:
        raise ValueError('Unsupported objective control')
    current = get(ident, path)
    if current['version'] != expected or current['state'] not in transitions[action][0]:
        raise ValueError('Objective changed or transition not permitted')
    accepted = verify_accepted(ident, path) if action == 'complete' else None
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM workforce_objectives WHERE id=?', (ident,)).fetchone()
        allowed, state = transitions[action]
        if not row or row['version'] != expected or row['state'] not in allowed:
            raise ValueError('Objective changed or transition not permitted')
        if action == 'complete':
            members = db.execute('SELECT t.* FROM team_tasks t JOIN workforce_objective_tasks m '
                                 'ON t.id=m.task_id WHERE m.objective_id=?', (ident,)).fetchall()
            if not members or any(t['state'] != 'completed' for t in members):
                raise ValueError('Every objective assignment must pass its existing output review')
            if set(accepted) != {task['id'] for task in members}:
                raise ValueError('Objective assignments changed during completion')
            consumed = usage(db, ident)
            if consumed['unresolved'] or consumed['cost'] > row['max_cost']:
                raise ValueError('Resolve outstanding accounting before objective completion')
            for task in members:
                result = db.execute("SELECT result_json FROM project_tasks WHERE project_id=? AND id='final' AND status='approved'",
                                    (task['run_id'],)).fetchone()
                if not result:
                    raise ValueError('Objective assignment has no accepted execution record')
                if accepted[task['id']] != (task['version'], result['result_json']):
                    raise ValueError('Accepted assignment changed during completion')
                p._text(json.loads(result['result_json']))
            if db.execute("SELECT 1 FROM team_requests r JOIN workforce_objective_tasks m ON m.task_id=r.task_id "
                          "WHERE m.objective_id=? AND r.status IN ('open','escalated')", (ident,)).fetchone():
                raise ValueError('Resolve open handoffs and disagreements before completing the objective')
        db.execute("UPDATE workforce_objectives SET state=?,version=version+1,last_signature='' WHERE id=?", (state, ident))
        store.event(db, 'owner', 'objective_' + action, {'objective_id': ident, 'note': note,
                    'success_criteria_attestation': action == 'complete', 'business_outcome_measured': False})
