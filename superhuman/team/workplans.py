"""Owner-prepared impact assessments over existing objective tasks and runs.

No scheduler or model tool. Snapshots retain the old records and artifacts; runs
keep their cumulative request and action limits across plan changes.
"""
import hashlib
import json
import re
from uuid import uuid4

from superhuman.projects import engine as p
from superhuman.departments.store import readonly, tables
from . import store, objectives

SAFE_HISTORY = {'', 'calculate', 'research.web', 'draft.create', 'team.handoff', 'team.challenge'}


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def approval_reason(db, task_id):
    if 'workforce_task_plan_controls' not in tables(db):
        return ''
    row = db.execute('SELECT * FROM workforce_task_plan_controls WHERE task_id=?', (task_id,)).fetchone()
    return f"Owner must approve this changed assignment for plan {row['plan_version']}" if row and not row['approved'] else ''


def boundary(db, run_id):
    if 'workforce_task_plan_controls' not in tables(db):
        return 0
    row = db.execute('SELECT c.action_boundary FROM workforce_task_plan_controls c JOIN team_tasks t ON t.id=c.task_id WHERE t.run_id=?', (run_id,)).fetchone()
    return row['action_boundary'] if row else 0


def _rows(db, sql, args=()):
    return [dict(r) for r in db.execute(sql, args)]


def _snapshot(db, ident):
    obj = db.execute('SELECT * FROM workforce_objectives WHERE id=?', (ident,)).fetchone()
    if not obj:
        raise ValueError('Objective not found')
    obj = dict(obj)
    tasks = _rows(db, 'SELECT t.*,m.plan_version FROM team_tasks t JOIN workforce_objective_tasks m ON m.task_id=t.id WHERE m.objective_id=? ORDER BY t.id', (ident,))
    result = dict(objective=obj, tasks=tasks,
        project=dict(db.execute('SELECT * FROM team_projects WHERE id=?', (obj['project_id'],)).fetchone()),
        costs=_rows(db, 'SELECT c.* FROM team_costs c JOIN workforce_objective_costs o ON o.cost_id=c.id WHERE o.objective_id=? ORDER BY c.id', (ident,)),
        requests=_rows(db, 'SELECT r.* FROM team_requests r JOIN workforce_objective_tasks m ON m.task_id=r.task_id WHERE m.objective_id=? ORDER BY r.id', (ident,)),
        settings=_rows(db, 'SELECT enabled,version,model,max_active,hold FROM team_settings'),
        employees=[], runs={}, sources=[], controls=[])
    for task in tasks:
        result['employees'] += _rows(db, 'SELECT * FROM team_employees WHERE id=?', (task['owner'],))
        if task['run_id']:
            rid = task['run_id']
            result['runs'][rid] = dict(
                project=_rows(db, 'SELECT * FROM projects WHERE id=?', (rid,)),
                tasks=_rows(db, 'SELECT * FROM project_tasks WHERE project_id=? ORDER BY id', (rid,)),
                run=_rows(db, 'SELECT * FROM agentic_runs WHERE project_id=?', (rid,)),
                actions=_rows(db, 'SELECT * FROM agentic_actions WHERE project_id=? ORDER BY ordinal', (rid,)))
        result['controls'] += _rows(db, 'SELECT * FROM workforce_task_plan_controls WHERE task_id=?', (task['id'],))
    if 'conversation_jobs' in tables(db):
        result['sources'] = _rows(db, 'SELECT j.* FROM conversation_jobs j JOIN workforce_objective_tasks m ON m.task_id=j.task_id WHERE m.objective_id=? ORDER BY j.id', (ident,))
        for job in result['sources']:
            result.setdefault('rooms', []).extend(_rows(db, 'SELECT * FROM ux_rooms WHERE thread_id=?', (job['room_id'],)))
            if 'hub_rooms' in tables(db):
                result.setdefault('archives', []).extend(_rows(db, 'SELECT id,archived FROM hub_rooms WHERE id=?', (job['room_id'],)))
    # External dependents are part of the assessment's consistency boundary.
    ids = {t['id'] for t in tasks}
    all_tasks = _rows(db, 'SELECT * FROM team_tasks ORDER BY id')
    result['external'] = [t for t in all_tasks
                          if t['id'] not in ids and (set(json.loads(t['deps'])) & ids or t['parent_id'] in ids)]
    # External inputs are read-only context, but changes to them must also stale
    # a prepared assessment. Capture their dependency closure without enrolling it.
    by_id = {t['id']: t for t in all_tasks}
    inputs, pending = {}, [dep for t in tasks for dep in json.loads(t['deps']) if dep not in ids]
    pending += [t['parent_id'] for t in tasks if t['parent_id'] and t['parent_id'] not in ids]
    while pending:
        task_id = pending.pop()
        if task_id in inputs or task_id in ids:
            continue
        task = by_id.get(task_id)
        if not task:
            raise ValueError('Missing external prerequisite prevents an impact assessment')
        inputs[task_id] = dict(task=task, execution=_rows(db, 'SELECT * FROM project_tasks WHERE project_id=? ORDER BY id', (task['run_id'],)) if task['run_id'] else [])
        pending.extend(json.loads(task['deps']))
        if task['parent_id']:
            pending.append(task['parent_id'])
    result['inputs'] = inputs
    return result


def _quiescent(snapshot):
    if snapshot['objective']['state'] != 'paused':
        raise ValueError('Pause the objective before preparing or applying a work change')
    if any(c['state'] in ('reserved', 'uncertain', 'overrun') for c in snapshot['costs']):
        raise ValueError('Settle or reconcile in-flight/uncertain objective costs before changing work')
    if any(r['status'] in ('open', 'escalated') for r in snapshot['requests']):
        raise ValueError('Resolve open handoffs and disagreements before changing work')
    for run in snapshot['runs'].values():
        if (any(t['status'] == 'running' for t in run['tasks'])
                or any(a['status'] in ('deciding', 'executing', 'pending') for a in run['actions'])
                or any(r['state'] in ('running', 'pause_requested', 'cancel_requested') for r in run['run'])):
            raise ValueError('Wait for in-flight work to settle before preparing or applying its change')


def _scope(db, snapshot):
    if 'workforce_reviews' in tables(db) and db.execute('SELECT 1 FROM workforce_reviews r JOIN workforce_objective_tasks m ON m.task_id=r.source_task_id WHERE m.objective_id=?',(snapshot['objective']['id'],)).fetchone():
        raise ValueError('Independent-review work uses supported rejection and revision; broader impact migration is not yet supported')
    obj, project = snapshot['objective'], snapshot['project']
    if ('milestone_projects' in tables(db) and db.execute('SELECT 1 FROM milestone_projects WHERE project_id=?', (obj['project_id'],)).fetchone()
            or 'milestone_assignments' in tables(db) and any(db.execute('SELECT 1 FROM milestone_assignments WHERE task_id=?', (t['id'],)).fetchone() for t in snapshot['tasks'])):
        raise ValueError('Milestone work needs its own reviewed impact adapter')
    origin = json.loads(obj['origin_json'])
    for job in snapshot['sources']:
        room = db.execute('SELECT * FROM ux_rooms WHERE thread_id=?', (job['room_id'],)).fetchone()
        task = next(t for t in snapshot['tasks'] if t['id'] == job['task_id'])
        if (not room or room['employee'] not in ('twin', job['employee']) or task['owner'] != job['employee']
                or room['project_id'] and (room['project_kind'] != 'team' or room['project_id'] != obj['project_id'])
                or (origin.get('room_id'), origin.get('turn_id'), origin.get('task_id')) != (job['room_id'], job['turn_id'], job['task_id'])):
            raise ValueError('Original conversation or assignment scope changed')
        if ('hub_rooms' in tables(db) and db.execute('SELECT 1 FROM hub_rooms WHERE id=? AND archived=1', (job['room_id'],)).fetchone()
                or 'mail_reports' in tables(db) and db.execute('SELECT 1 FROM mail_reports WHERE thread_id=?', (job['room_id'],)).fetchone()):
            raise ValueError('Restore the original direct conversation before changing work')
        if db.execute("SELECT 1 FROM dialogue_turns WHERE thread_id=? AND status IN ('running','queued')", (job['room_id'],)).fetchone():
            raise ValueError('Wait for the pending source conversation reply')
    for task in snapshot['tasks']:
        if task['project_id'] != project['id']:
            raise ValueError('Assignment escaped the objective project')


def _verify_retained(db, task, path):
    from superhuman.agentic import tools
    result = db.execute("SELECT result_json FROM project_tasks WHERE project_id=? AND id='final' AND status='approved'", (task['run_id'],)).fetchone()
    if task['state'] != 'completed' or not result:
        raise ValueError('Only accepted completed work can be retained')
    data = json.loads(result['result_json'])
    p._text(data)
    if not data.get('evidence_action_ids'):
        raise ValueError('Retained output has no execution evidence')
    for ident in data['evidence_action_ids']:
        action = db.execute('SELECT * FROM agentic_actions WHERE project_id=? AND id=?', (task['run_id'], ident)).fetchone()
        if not action or action['status'] not in ('succeeded', 'cached') or not json.loads(action['verification_json'] or '{}').get('verified'):
            raise ValueError('Retained execution evidence is not verified')
        tools.verify_saved(dict(action), task['owner'], path)


def _assess(db, snapshot, payload, path):
    _quiescent(snapshot)
    _scope(db, snapshot)
    from superhuman.core.router import route_task
    objective_text = payload['brief']+'\n'+payload['criteria']
    if (re.search(r'\b(send|publish|submit|purchase|buy|pay|delete|deploy|change permissions)\b', objective_text, re.I)
            or route_task(objective_text, objective_text).approval_required):
        raise ValueError('The replacement objective exceeds this internal work-change authority')
    tasks = {t['id']: t for t in snapshot['tasks']}
    assignments = payload['assignments']
    if set(assignments) != set(tasks):
        raise ValueError('Assess every current objective assignment exactly once')
    graph = {i: set(json.loads(t['deps'])) for i, t in tasks.items()}
    graph.update({i: set(json.loads(value['task']['deps'])) for i, value in snapshot['inputs'].items()})
    visiting, visited = set(), set()
    def visit(ident):
        if ident in visiting:
            raise ValueError('Dependency cycle prevents an impact assessment')
        if ident in visited or ident not in graph:
            return
        visiting.add(ident)
        for dep in graph[ident]:
            visit(dep)
        visiting.remove(ident)
        visited.add(ident)
    for ident in tasks:
        visit(ident)
        if any(not db.execute('SELECT 1 FROM team_tasks WHERE id=?', (d,)).fetchone() for d in graph[ident]):
            raise ValueError('Missing prerequisite prevents an impact assessment')
    changed = {i for i, value in assignments.items() if value['disposition'] == 'revise'}
    if not changed:
        raise ValueError('Choose at least one assignment to revise')
    closure = set(changed)
    while True:
        dependent = {i for i, task in tasks.items() if graph[i] & closure or task['parent_id'] in closure}
        if dependent <= closure:
            break
        closure |= dependent
    if closure != changed:
        raise ValueError('Dependent assignments must also be revised: ' + ', '.join(sorted(closure - changed)))
    if any(set(json.loads(t['deps'])) & changed or t['parent_id'] in changed for t in snapshot['external']):
        raise ValueError('Affected work has dependents outside this objective; review their scope first')
    root = snapshot['objective']['root_task_id']
    if assignments[root]['disposition'] == 'revise' and (assignments[root]['brief'], assignments[root]['criteria']) != (payload['brief'], payload['criteria']):
        raise ValueError('The root assignment must use the replacement objective brief and criteria')
    jobs = {j['task_id']: j for j in snapshot['sources']}
    for ident, value in assignments.items():
        task = tasks[ident]
        if value['disposition'] == 'retain':
            if (value['brief'], value['criteria']) != (task['instruction'], task['acceptance']):
                raise ValueError('Retained assignments must keep their original brief and criteria')
            _verify_retained(db, task, path)
            continue
        if task['state'] == 'cancelled':
            raise ValueError('Cancelled assignments cannot be revived by a plan change')
        if task['run_id'] and any(a['tool'] not in SAFE_HISTORY for a in snapshot['runs'][task['run_id']]['actions']):
            raise ValueError('This tool history needs a reviewed replay adapter before changing work')
        project = snapshot['project']
        risk = max((task['risk'] or project['risk'], project['risk']), key=store.RISKS.index)
        sensitivity = max((task['sensitivity'] or project['sensitivity'], project['sensitivity']), key=store.SENSITIVITIES.index)
        combined = value['brief'] + '\n' + value['criteria']
        if (risk != 'routine' or sensitivity == 'restricted'
                or re.search(r'\b(send|publish|submit|purchase|buy|pay|delete|deploy|change permissions)\b', combined, re.I)
                or route_task(combined, combined).approval_required):
            raise ValueError('Revised work exceeds the routine internal authority of this control')
        if ident in jobs:
            from superhuman.conversationwork.revisions import validate_brief
            validate_brief(value['brief'], value['criteria'], jobs[ident]['kind'], risk, sensitivity)


def _payload(ident, expected, brief, criteria, impact, assignments):
    if type(expected) is not int or not isinstance(assignments, dict):
        raise ValueError('Provide the expected objective version and assignment assessment')
    result = dict(objective_id=ident, expected=expected, brief=store.text(brief, 4500, 'Owner brief', True),
                  criteria=store.text(criteria, 1500, 'Success criteria', True), impact=store.text(impact, 2000, 'Impact assessment', True), assignments={})
    for task_id, value in assignments.items():
        if not isinstance(value, dict) or set(value) != {'disposition', 'brief', 'criteria', 'reason'} or value['disposition'] not in ('retain', 'revise'):
            raise ValueError('Each assignment needs a retain/revise decision, brief, criteria, and reason')
        result['assignments'][task_id] = dict(disposition=value['disposition'],
            brief=store.text(value['brief'], 5000, 'Assignment brief', True), criteria=store.text(value['criteria'], 1500, 'Assignment criteria', True),
            reason=store.text(value['reason'], 2000, 'Assignment impact reason', True))
    return result


def prepare(ident, expected, brief, criteria, impact, assignments, submission_key, path=p.DEFAULT_DB):
    payload = _payload(ident, expected, brief, criteria, impact, assignments)
    if not isinstance(submission_key, str) or not 16 <= len(submission_key) <= 80:
        raise ValueError('Invalid submission key; reload the assessment')
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        snapshot = _snapshot(db, ident)
        _scope(db, snapshot)
        old = db.execute('SELECT * FROM workforce_plan_changes WHERE submission_key=?', (submission_key,)).fetchone()
        if old:
            if old['payload_json'] != encode(payload):
                raise ValueError('Submission key was already used with different content')
            return old['id']
        if snapshot['objective']['version'] != expected:
            raise ValueError('Objective changed; reload and prepare a fresh assessment')
        _assess(db, snapshot, payload, path)
        ident_change = uuid4().hex
        raw = encode(snapshot)
        digest = hashlib.sha256(encode(dict(snapshot=snapshot, payload=payload)).encode()).hexdigest()
        db.execute('INSERT INTO workforce_plan_changes(id,objective_id,submission_key,payload_json,snapshot_json,digest,created_at) VALUES(?,?,?,?,?,?,?)',
                   (ident_change, ident, submission_key, encode(payload), raw, digest, p.stamp()))
        store.event(db, 'owner', 'objective_impact_prepared', dict(objective_id=ident, change_id=ident_change))
        return ident_change


def get(change_id, path=p.DEFAULT_DB):
    with readonly(path) as db:
        row = db.execute('SELECT * FROM workforce_plan_changes WHERE id=?', (change_id,)).fetchone()
        if not row:
            raise ValueError('Impact assessment not found')
        return dict(row)


def apply(change_id, expected_digest, path=p.DEFAULT_DB):
    from superhuman.agentic import store as agent
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM workforce_plan_changes WHERE id=?', (change_id,)).fetchone()
        if not row or row['digest'] != expected_digest:
            raise ValueError('Impact assessment changed; reopen it')
        payload = json.loads(row['payload_json'])
        material_digest = hashlib.sha256(encode(dict(snapshot=json.loads(row['snapshot_json']), payload=payload)).encode()).hexdigest()
        if material_digest != expected_digest:
            raise ValueError('Prepared assessment content changed; prepare a fresh assessment')
        snapshot = _snapshot(db, row['objective_id'])
        _scope(db, snapshot)
        if row['state'] == 'applied':
            return row['applied_plan']
        if encode(snapshot) != row['snapshot_json']:
            raise ValueError('Work, accounting, or authority changed; prepare a fresh impact assessment')
        _assess(db, snapshot, payload, path)
        obj = snapshot['objective']
        objectives.consume_revision(db, obj['root_task_id'])
        version, now = obj['current_plan'] + 1, p.stamp()
        db.execute('INSERT INTO workforce_objective_plans VALUES(?,?,?,?,?,?)', (obj['id'], version, payload['brief'], payload['criteria'], payload['impact'], now))
        db.execute("UPDATE workforce_objectives SET current_plan=?,last_signature='' WHERE id=?", (version, obj['id']))
        for task in snapshot['tasks']:
            value = payload['assignments'][task['id']]
            if value['disposition'] == 'retain':
                if (value['brief'], value['criteria']) != (task['instruction'], task['acceptance']):
                    raise ValueError('Retained assignments must keep their original brief and criteria')
                continue
            action_boundary = 0
            if task['run_id']:
                rid = task['run_id']
                action_boundary = max((a['ordinal'] for a in snapshot['runs'][rid]['actions']), default=0)
                details = (value['brief']+'\n\nProject objective: '+snapshot['project']['objective']
                           +'\nProject criteria: '+snapshot['project']['acceptance']
                           +'\nTask acceptance criteria: '+value['criteria']+'\nNo external commitments are authorized.')
                db.execute("UPDATE projects SET details=?,status='active',updated_at=? WHERE id=?", (details, now, rid))
                db.execute("UPDATE project_tasks SET status='pending',token=NULL,started=NULL,error=NULL,review_note=NULL WHERE project_id=? AND id='final'", (rid,))
                agent.update(db, rid, 'paused', 'Plan changed; owner start approval required')
                agent.event(db, rid, 'plan_changed', dict(change_id=change_id, plan_version=version, old_actions_through=action_boundary))
            db.execute("UPDATE team_tasks SET instruction=?,acceptance=?,owner_grant=0,state='held',attempts=attempts+1,version=version+1,updated_at=? WHERE id=?",
                       (value['brief'], value['criteria'], now, task['id']))
            db.execute('INSERT INTO workforce_task_plan_controls VALUES(?,?,?,?,0) ON CONFLICT(task_id) DO UPDATE SET plan_version=excluded.plan_version,action_boundary=excluded.action_boundary,approved=0',
                       (task['id'], obj['id'], version, action_boundary))
        db.execute('UPDATE workforce_objective_tasks SET plan_version=? WHERE objective_id=?', (version, obj['id']))
        turn_id = _receipt(db, snapshot, payload, change_id, version)
        db.execute("UPDATE workforce_plan_changes SET state='applied',applied_plan=?,receipt_turn_id=?,applied_at=? WHERE id=?", (version, turn_id, now, change_id))
        store.event(db, 'owner', 'objective_impact_applied', dict(objective_id=obj['id'], change_id=change_id, plan_version=version, assignments=payload['assignments']))
        return version


def _receipt(db, snapshot, payload, change_id, version):
    if not snapshot['sources']:
        return None
    from superhuman.dialogue import store as dialogue
    job = snapshot['sources'][0]
    tid, now = uuid4().hex, p.stamp()
    ordinal = db.execute('SELECT COALESCE(MAX(ordinal),0)+1 FROM dialogue_turns WHERE thread_id=?', (job['room_id'],)).fetchone()[0]
    changed = [i for i, value in payload['assignments'].items() if value['disposition'] == 'revise']
    reply = (f'Plan {version} saved after impact review. {len(changed)} assignments need fresh owner start approval. '
             'The objective remains paused. Earlier outputs and reviews are retained in plan history; affected approvals no longer apply. '
             'Spending, request/step usage, limits and deadlines are unchanged. No execution was started.')
    message = 'Apply reviewed objective change\n'+payload['brief']+'\nSuccess criteria:\n'+payload['criteria']+'\nImpact:\n'+payload['impact']
    context = encode(dict(receipt=dict(kind='owner_control', change_id=change_id, plan_version=version, provider_request=False)))
    db.execute("INSERT INTO dialogue_turns(id,thread_id,ordinal,submission_key,user_text,status,reply,context_json,created_at,finished_at) VALUES(?,?,?,?,?,'done',?,?,?,?)",
               (tid, job['room_id'], ordinal, change_id, message, reply, context, now, now))
    db.execute('UPDATE dialogue_threads SET updated_at=? WHERE id=?', (now, job['room_id']))
    dialogue.event(db, 'conversation_objective_impact_applied', job['room_id'], tid, snapshot['objective']['project_id'], change_id=change_id, plan_version=version)
    return tid


def approve_task(db, task, note):
    """Owner-only continuation gate, used atomically by the existing task control."""
    if 'workforce_task_plan_controls' not in tables(db):
        return False
    control = db.execute('SELECT * FROM workforce_task_plan_controls WHERE task_id=?', (task['id'],)).fetchone()
    if not control:
        return False
    run = db.execute('SELECT * FROM agentic_runs WHERE project_id=?', (task['run_id'],)).fetchone() if task['run_id'] else None
    continuation = bool(control and control['approved'] and run and run['state']=='step_limit')
    if control['approved'] and not continuation:
        return False
    note = store.text(note, 2000, 'Review the changed assignment before approval', True)
    live = db.execute('SELECT * FROM team_tasks WHERE id=?', (task['id'],)).fetchone()
    if live['version'] != task['version'] or live['state'] not in ('held', 'queued', 'ready', 'dispatched', 'paused', 'owner_review'):
        raise ValueError('Changed assignment moved; reload its controls')
    if task['run_id']:
        if run['state']=='step_limit':
            count = db.execute('SELECT COUNT(*) FROM agentic_actions WHERE project_id=?', (task['run_id'],)).fetchone()[0]
            source = 'conversation_jobs' in tables(db) and db.execute('SELECT 1 FROM conversation_jobs WHERE task_id=?', (task['id'],)).fetchone()
            pending = db.execute("SELECT 1 FROM agentic_actions WHERE project_id=? AND ordinal>? AND status IN ('approved','budget_wait')", (task['run_id'],control['action_boundary'])).fetchone()
            needed = 1 if not source or pending else 2
            if run['max_actions']-count < needed:
                raise ValueError('Amend the task step limit before approving continuation; prior actions still count')
        if run['state'] not in ('paused', 'ready', 'step_limit'):
            raise ValueError('Inspect the run before approving the new plan')
        db.execute("UPDATE agentic_runs SET state='ready',version=version+1,error=NULL WHERE project_id=?", (task['run_id'],))
    db.execute('UPDATE workforce_task_plan_controls SET approved=1 WHERE task_id=?', (task['id'],))
    db.execute('UPDATE team_tasks SET owner_grant=1,state=?,version=version+1 WHERE id=?', ('dispatched' if task['run_id'] else 'ready', task['id']))
    store.event(db, 'owner', 'changed_assignment_start_approved', dict(task_id=task['id'], note=note))
    return True
