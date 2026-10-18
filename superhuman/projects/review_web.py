"""Local project review UI. No worker launch or model calls on review routes."""
import hashlib
import json
import tempfile
from pathlib import Path
from fastapi import Form, HTTPException
from fastapi.responses import PlainTextResponse, RedirectResponse
from . import web, engine as e, revisions as r
from superhuman.identity.selection import select_context

app = web.app
esc = web.esc
# Replace only the original project detail view; retain queue and plan routes.
app.router.routes[:] = [route for route in app.router.routes
    if not (getattr(route, 'path', '') == '/projects/{pid}' and 'GET' in getattr(route, 'methods', set()))]

def token(task):
    return hashlib.sha256(json.dumps(task, sort_keys=True).encode()).hexdigest()

def task_for(pid, tid):
    try:
        project = e.get(pid)
        task = next(t for t in project['tasks'] if t['id'] == tid)
        return project, task
    except (ValueError, StopIteration) as exc:
        raise HTTPException(404, 'Project or task not found') from exc

def data(value, fallback=None):
    try:
        return json.loads(value) if isinstance(value, str) else value or fallback
    except (ValueError, TypeError):
        return fallback

def dump(value):
    return '<pre>' + esc(json.dumps(value, indent=2, ensure_ascii=False)) + '</pre>'

def history(pid, tid):
    # Opening a review page must not create a revision table or change records.
    with e.connect(e.DEFAULT_DB) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_revisions'").fetchone():
            return []
        return [dict(row) for row in db.execute(
            'SELECT * FROM project_revisions WHERE project_id=? AND task_id=? ORDER BY created_at', (pid, tid))]

def context_html(trace):
    if not isinstance(trace, dict):
        return '<p>No context-selection trace was recorded for this draft.</p>'
    result = '<p>Task type: ' + esc(trace.get('task_type', 'unknown')) + '</p>'
    for key in ('selected', 'excluded'):
        rows = ''.join('<tr><td>'+esc(row.get('label', row.get('id', '')))+
            '</td><td>'+esc(row.get('kind', ''))+'</td><td>'+esc(row.get('reason', ''))+
            '</td><td>'+esc(row.get('score', ''))+'</td></tr>' for row in trace.get(key, []))
        result += '<h3>'+key.title()+'</h3><table><tr><th>Record</th><th>Type</th><th>Reason</th><th>Match score</th></tr>'+rows+'</table>'
    return result + '<p>Reference characters: '+esc(trace.get('reference_chars', 'unknown'))+'</p>'

def task_html(pid, task):
    tid = task['id']; result = data(task.get('result_json'), {})
    content = ''; available = False; assessment = None
    if result:
        try:
            _, content = e._text(result)
            available = True
        except (ValueError, OSError, UnicodeError):
            content = 'Stored draft could not be verified. Restore or investigate the artifact before reviewing.'
    if available and task['status'] in r.EDITABLE:
        try:
            project = e.get(pid)
            assessment = r.assess(project, task, result, content)
        except (ValueError, OSError, UnicodeError) as exc:
            assessment = {'passes': False, 'errors': [str(exc)]}
    errors = [task.get('error')] if task.get('error') else []
    errors += result.get('project_quality_checks', [])
    report = result.get('quality_report', {})
    if isinstance(report, dict): errors += report.get('errors', [])
    # Current assessment is displayed separately from historical stored findings.
    errors = list(dict.fromkeys(str(error) for error in errors if error))
    check_view = ('<p>Saved approval records remain historical; current checks assess this stored draft against current rules. A failed check does not silently rewrite approval history.</p>' if task['status']=='approved' else '') + ('<p>Current local checks: '+('Passed' if assessment['passes'] else 'Blocked')+'</p>'+dump(assessment)) if assessment else '<p>Current local checks have not been evaluated.</p>'
    if result.get('execution_evidence'):
        check_view+='<details><summary>Execution evidence (separate from deliverable)</summary>'+dump(result['execution_evidence'])+'<p>Saved tool integrity is not proof of factual correctness or owner approval.</p></details>'
    if result.get('original_generation_quality_report'):
        check_view += '<details><summary>Archived generation report</summary>'+dump(result['original_generation_quality_report'])+'</details>'
    controls = ''
    if available and task['status'] in r.EDITABLE:
        common = '<input type="hidden" name="version" value="'+token(task)+'">'
        controls = '<p><a href="/projects/'+esc(pid)+'/tasks/'+esc(tid)+'/download">Download verified deliverable text</a></p>'
        controls += '<details><summary>Edit or check a local revision</summary><p>Checks and revisions use no API requests. Saving preserves the old draft, resets dependent tasks, and requires approval again.</p><form method="post" action="/projects/'+esc(pid)+'/tasks/'+esc(tid)+'/local">'+common+'<label>Deliverable<textarea name="text" maxlength="2000000" style="min-height:320px" required>'+esc(content)+'</textarea></label><label>Revision note<input name="note" maxlength="2000"></label><button name="action" value="check">Check edits only</button> <button name="action" value="revise">Save passing revision</button></form></details>'
        if task['status'] == 'needs_review' and assessment and assessment['passes']:
            controls += '<form method="post" action="/projects/'+esc(pid)+'/tasks/'+esc(tid)+'/local">'+common+'<label>Review note<input name="note" maxlength="2000"></label><button name="action" value="approve">Approve draft</button> <button name="action" value="reject">Reject draft</button></form>'
        controls += '<form method="post" action="/projects/'+esc(pid)+'/tasks/'+esc(tid)+'/local">'+common+'<label>Revalidation note<input name="note" maxlength="2000" required></label><button name="action" value="revalidate">Revalidate stored draft</button></form>'
    entries = history(pid, tid)
    audit = ''.join('<section><p>'+esc(row['created_at'])+' | '+esc(row['action'])+'</p><p>'+esc(row['note'])+'</p><p>Invalidated tasks: '+esc(', '.join(x['id'] for x in data(row['invalidated_json'], [])))+'</p></section>' for row in entries) or '<p>No local revisions recorded.</p>'
    return '<section id="task-'+esc(tid)+'" class="panel" style="margin-top:20px"><h2>'+esc(task['title'])+'</h2><p>Status: <strong>'+esc(task['status'])+'</strong> | Dependencies: '+esc(task['deps'])+'</p><p>Last review: '+esc(task.get('review_note') or 'None')+'</p><h3>Stored quality findings</h3>'+(''.join('<p>'+esc(x)+'</p>' for x in errors) or '<p>No stored quality errors.</p>')+check_view+'<h3>Deliverable</h3><pre>'+esc(content or 'No draft yet.')+'</pre>'+controls+'<details><summary>Context recorded at generation</summary>'+context_html(result.get('context_selection'))+'</details><details><summary>Local revision history ('+str(len(entries))+')</summary>'+audit+'</details><p>Factual accuracy is not established by local formatting checks.</p></section>'

@app.get('/projects/{pid}')
def detail(pid: str):
    try: project = e.get(pid)
    except ValueError as exc: raise HTTPException(404, str(exc)) from exc
    controls = ''
    if project['status'] in ('new', 'plan_failed'):
        controls = '<form method="post" action="/projects/'+esc(pid)+'/plan"><button>Generate plan (one API request)</button></form>'
    elif project['status'] == 'plan_review':
        controls = '<form method="post" action="/projects/'+esc(pid)+'/approve-plan"><button>Approve local plan</button></form>'
    preview = select_context(project['workstream'], project['objective'], project['details'])
    return web.page('<h1>'+esc(project['objective'])+'</h1><p>Project status: <strong>'+esc(project['status'])+'</strong> | API attempts: '+str(project['used_calls'])+'/'+str(project['max_calls'])+'</p><p>'+esc(project['details'])+'</p><p>'+esc(project.get('error') or '')+'</p>'+controls+'<details><summary>Plan</summary>'+dump(data(project['plan_json'], {}))+'</details><details><summary>Current objective context preview</summary><p>This is a fresh preview for the objective. Recorded task traces below show what was selected for each generated draft.</p>'+context_html(preview['trace'])+'</details><p>Worker command: <code>python -m superhuman.projects.cli worker '+esc(pid)+'</code></p><p>Workers run separately. Draft approval does not authorize external actions.</p>'+''.join(task_html(pid, task) for task in project['tasks']), 'Project review')

@app.get('/projects/{pid}/tasks/{tid}/download')
def download(pid: str, tid: str):
    _, task = task_for(pid, tid)
    try: _, text = e._text(json.loads(task['result_json']))
    except (ValueError, OSError, TypeError, UnicodeError) as exc:
        raise HTTPException(409, 'No verified draft available') from exc
    return PlainTextResponse(text, headers={'Content-Disposition': 'attachment; filename="deliverable.txt"'})

@app.post('/projects/{pid}/tasks/{tid}/local')
def local(pid: str, tid: str, action: str = Form(...), version: str = Form(...), text: str = Form(''), note: str = Form('')):
    project, task = task_for(pid, tid)
    if token(task) != version: raise HTTPException(409, 'Draft changed. Reload the project before applying edits or approval.')
    if len(note) > 2000 or len(text.encode('utf-8')) > 2_000_000: raise HTTPException(400, 'Input too long')
    if any(t['status'] == 'running' for t in project['tasks']): raise HTTPException(409, 'Wait for the project worker to stop before editing or reviewing.')
    try:
        if action in ('check', 'revise'):
            # Server chooses the temporary file; browser cannot choose filesystem paths.
            with tempfile.TemporaryDirectory(prefix='superhuman-review-') as directory:
                source = Path(directory)/'edited.txt'; source.write_text(text, encoding='utf-8')
                outcome = r.check(pid, tid, source) if action == 'check' else r.revise(pid, tid, source, note)
            if action == 'check' or not outcome.get('applied'):
                return web.page('<h1>Revision checks</h1>'+dump(outcome)+'<p>Your submitted text is below. Copy it before leaving this page, or use Back to continue editing.</p><textarea readonly style="min-height:320px">'+esc(text)+'</textarea><p><a href="/projects/'+esc(pid)+'">Return to project</a></p>', 'Revision checks')
        elif action == 'revalidate': r.revalidate(pid, tid, note)
        elif action in ('approve', 'reject'):
            # Recheck actual content before approval, even after the page was loaded.
            if action == 'approve':
                p, t, result, _, content = r.load(pid, tid)
                assessment = r.assess(p, t, result, content)
                if not assessment['passes']: raise ValueError('Current quality checks failed: '+'; '.join(assessment['errors']))
            e.review(pid, tid, action, note)
        else: raise ValueError('Unknown review action')
    except (ValueError, OSError, UnicodeError) as exc: raise HTTPException(400, str(exc)) from exc
    return RedirectResponse('/projects/'+pid, status_code=303)
