"""Explicit owner feedback controls. Never registered as model-executable tools."""
import json
import re
from uuid import uuid4

from superhuman.projects import engine as p
from superhuman.departments.store import readonly, tables
from superhuman.team import objectives, store as team
from superhuman.dialogue import store as dialogue


def current(job, path=p.DEFAULT_DB):
    """Return the bound plan without changing the immutable original job request."""
    with readonly(path) as db:
        objective = objectives.for_task(db, job['task_id'])
        if not objective:
            return None
        origin = json.loads(objective['origin_json'])
        if (origin.get('room_id'), origin.get('turn_id'), origin.get('task_id')) != (
                job['room_id'], job['turn_id'], job['task_id']):
            return None
        plan = db.execute('SELECT * FROM workforce_objective_plans WHERE objective_id=? AND version=?',
                          (objective['id'], objective['current_plan'])).fetchone()
        return dict(objective=objective, plan=dict(plan))


def validate_brief(brief, criteria, kind, risk, sensitivity):
    """Use the existing conservative conversation capability boundaries."""
    from .bridge import explicit, private_query
    from superhuman.core.router import route_task
    if not explicit(brief, revisions=False):
        raise ValueError('Provide a complete explicit research or local drafting request')
    combined = brief + '\n' + criteria
    if (re.search(r'\b(send|publish|submit|purchase|buy|pay|delete|deploy|change permissions)\b', combined, re.I)
            or route_task(combined, combined).approval_required):
        raise ValueError('Revisions cannot authorize consequential or external actions')
    if risk != 'routine' or sensitivity == 'restricted':
        raise ValueError('This classification requires a separately reviewed workflow')
    if kind == 'research' and (sensitivity in ('confidential', 'restricted') or private_query(combined)):
        raise ValueError('Private information cannot be included in public research')
    if kind == 'collab' and re.search(r'\b(go online|look up|online research|browse|search the web)\b', combined, re.I):
        raise ValueError('This local drafting assignment cannot become live research')


def submit(room_id, ident, expected, room_version, brief, criteria, impact, submission_key, path=p.DEFAULT_DB):
    """Save the plan, owner feedback, receipt and audit in one SQLite transaction.

    Called only by the authenticated owner form. No provider request or dispatch.
    A retry of the same submission returns its original saved turn.
    """
    brief = team.text(brief, 4500, 'Owner brief', True)
    criteria = team.text(criteria, 1500, 'Success criteria', True)
    impact = team.text(impact, 2000, 'Impact assessment', True)
    if not isinstance(submission_key, str) or not 16 <= len(submission_key) <= 80:
        raise ValueError('Invalid submission key; reload the conversation')
    payload = dict(room_id=room_id, objective_id=ident, expected=expected, room_version=room_version,
                   brief=brief, criteria=criteria, impact=impact)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        if not {'workforce_objectives', 'conversation_jobs', 'ux_rooms', 'dialogue_turns'} <= tables(db):
            raise ValueError('Objective source conversation not found')
        objective = db.execute('SELECT * FROM workforce_objectives WHERE id=?', (ident,)).fetchone()
        room = db.execute('SELECT * FROM ux_rooms WHERE thread_id=?', (room_id,)).fetchone()
        job = db.execute('SELECT * FROM conversation_jobs WHERE task_id=?', (objective['root_task_id'],)).fetchone() if objective else None
        if not objective or not room or not job:
            raise ValueError('Objective source conversation not found')
        origin = json.loads(objective['origin_json'])
        if (origin.get('room_id'), origin.get('turn_id'), origin.get('task_id')) != (
                room_id, job['turn_id'], job['task_id']) or job['room_id'] != room_id:
            raise ValueError('Revise this objective in its original conversation')
        if (room['version'] != room_version or room['employee'] not in ('twin', job['employee'])
                or room['project_id'] and (room['project_kind'] != 'team' or room['project_id'] != objective['project_id'])):
            raise ValueError('Conversation scope changed; reload its controls')
        if 'hub_rooms' in tables(db) and db.execute('SELECT 1 FROM hub_rooms WHERE id=? AND archived=1', (room_id,)).fetchone():
            raise ValueError('Restore the archived conversation before revising')
        if 'mail_reports' in tables(db) and db.execute('SELECT 1 FROM mail_reports WHERE thread_id=?', (room_id,)).fetchone():
            raise ValueError('Inbox reports cannot authorize objective revisions')
        old = db.execute('SELECT * FROM dialogue_turns WHERE submission_key=?', (submission_key,)).fetchone()
        if old:
            context = json.loads(old['context_json'] or '{}')
            if old['thread_id'] != room_id or context.get('objective_revision') != payload:
                raise ValueError('Submission key was already used with different content')
            return old['id']
        if db.execute("SELECT 1 FROM dialogue_turns WHERE thread_id=? AND status IN ('queued','running')", (room_id,)).fetchone():
            raise ValueError('Wait for the pending conversation reply before revising')
        task = db.execute('SELECT * FROM team_tasks WHERE id=?', (job['task_id'],)).fetchone()
        project = db.execute('SELECT * FROM team_projects WHERE id=?', (objective['project_id'],)).fetchone()
        if (not task or not project or task['owner'] != job['employee'] or job['kind'] not in ('research', 'collab')
                or task['project_id'] != objective['project_id']):
            raise ValueError('Assignment scope changed; inspect its controls')
        sensitivity = max((task['sensitivity'] or project['sensitivity'], project['sensitivity']), key=team.SENSITIVITIES.index)
        risk = max((task['risk'] or project['risk'], project['risk']), key=team.RISKS.index)
        validate_brief(brief, criteria, job['kind'], risk, sensitivity)
        objectives._revise_plan(db, ident, expected, brief, criteria, impact, conversation_job=job['id'])
        plan_version = objective['current_plan'] + 1
        tid, now = uuid4().hex, p.stamp()
        ordinal = db.execute('SELECT COALESCE(MAX(ordinal),0)+1 FROM dialogue_turns WHERE thread_id=?', (room_id,)).fetchone()[0]
        message = f'Revise objective {ident}\nBrief:\n{brief}\nSuccess criteria:\n{criteria}\nImpact:\n{impact}'
        reply = (f'Objective {ident}: plan {plan_version} saved. The assignment is queued for start approval. '
                 'One revision round was used; existing spending, request usage, deadlines and total allowances are retained. '
                 f'Inspect /team/objectives/{ident} for current limits and blockers. No execution was started.')
        context = dict(objective_revision=payload, receipt=dict(objective_id=ident, plan_version=plan_version,
                       kind='owner_control', provider_request=False))
        db.execute("INSERT INTO dialogue_turns(id,thread_id,ordinal,submission_key,user_text,status,reply,context_json,created_at,finished_at) "
                   "VALUES(?,?,?,?,?,'done',?,?,?,?)",
                   (tid, room_id, ordinal, submission_key, message, reply, json.dumps(context), now, now))
        db.execute('UPDATE dialogue_threads SET updated_at=? WHERE id=?', (now, room_id))
        dialogue.event(db, 'conversation_objective_revised', room_id, tid, objective['project_id'],
                       objective_id=ident, plan_version=plan_version, source_turn_id=job['turn_id'])
        return tid


def panel(job, path=p.DEFAULT_DB):
    from superhuman.navigation.shell import esc as E
    from superhuman.experience import store as ux
    bound = current(job, path)
    if not bound:
        return ''
    objective, plan = bound['objective'], bound['plan']
    ident = objective['id']
    body = '<p><a href="/team/objectives/'+E(ident)+'">Objective and plan history</a> · Plan '+str(plan['version'])+'</p>'
    body += '<p><a href="/team/objectives/'+E(ident)+'/changes/new">Review a change to started work</a></p>'
    task = team.task(job['task_id'], path)
    room = ux.room(job['room_id'], path)
    if (not room or objective['state'] not in ('active', 'paused') or task['run_id'] or task['attempts']
            or len(objectives.get(ident, path)['tasks']) != 1):
        return body
    body += '<details><summary>Revise this objective before execution</summary><p>Replace the complete brief and criteria. This uses one revision round and requires start approval again.</p>'
    body += '<form method="post" action="/team-room/'+E(job['room_id'])+'/objectives/'+E(ident)+'/revise">'
    for name, value in (('version', objective['version']), ('room_version', room['version']), ('submission_key', uuid4().hex)):
        body += '<input type="hidden" name="'+name+'" value="'+E(value)+'">'
    for label, name, value, maximum in (('Replacement owner brief', 'brief', plan['brief'], 4500),
                                       ('Success criteria', 'criteria', plan['criteria'], 1500),
                                       ('Impact and reason for this change', 'impact', '', 2000)):
        body += '<label>'+label+'<textarea name="'+name+'" maxlength="'+str(maximum)+'" required>'+E(value)+'</textarea></label>'
    return body + '<button>Save objective revision</button></form></details>'
