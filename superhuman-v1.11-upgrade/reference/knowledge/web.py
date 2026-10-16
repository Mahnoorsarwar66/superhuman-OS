"""Server-rendered memory centre inside the existing authenticated boundary."""
import json
from fastapi import Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from superhuman.hosted import views
from .store import Store, KINDS, STATUSES, SOURCES, GENRES, today


def options(items, selected):
    return ''.join('<option value="' + views.esc(item) + '"' + (' selected' if item == selected else '') +
                   '>' + views.esc(item.replace('_', ' ')) + '</option>' for item in items)


def scopes():
    from superhuman.core.router import WORKSTREAMS
    return ('global', *WORKSTREAMS.keys())


def form(record=None, scope='global', source='', title='', kind='update'):
    r = record or dict(scope=scope, kind=kind, title=title, content='', source_type='user',
                       source=source, status='proposed', sensitive=False, genre='all', expires_on='')
    action = '/memory/' + r['id'] + '/save' if record else '/memory/add'
    body = '<form method="post" action="' + action + '">'
    if record:
        body += '<input type="hidden" name="version" value="' + str(r['version']) + '">'
    for name, label, choices in (('scope', 'Workstream', scopes()), ('kind', 'Note type', KINDS),
                                 ('source_type', 'Where this came from', SOURCES),
                                 ('genre', 'Apply to task type', GENRES), ('status', 'Status', STATUSES)):
        body += '<label>' + label + '<select name="' + name + '">' + options(choices, r[name]) + '</select></label>'
    body += '<label>Title<input name="title" maxlength="180" required value="' + views.esc(r['title']) + '"></label>'
    body += '<label>Update, decision or feedback<textarea name="content" maxlength="4000" required>' + views.esc(r['content']) + '</textarea></label>'
    body += '<label>Source or related task (optional)<input name="source" maxlength="500" value="' + views.esc(r['source']) + '"></label>'
    body += '<label>Expiry date (optional)<input type="date" name="expires_on" value="' + views.esc(r['expires_on']) + '"></label>'
    body += '<label><input style="display:inline;width:auto" type="checkbox" name="sensitive" value="yes"' + (' checked' if r['sensitive'] else '') + '> Sensitive: never include automatically in model context</label>'
    body += '<p class="muted">Choose Confirmed only when you want this note eligible for future tasks. '
    body += 'Global notes can apply across workstreams. Use a specific workstream for project details. '
    body += 'Preferences can apply without a keyword match; other notes require a topical match. '
    body += 'For a reusable writing rule, choose Preference; Feedback is reference context. '
    body += 'Set a task type to limit where a preference applies. Dates use your configured timezone (Asia/Karachi by default).</p>'
    body += '<button>' + ('Save changes' if record else 'Save note') + '</button></form>'
    return body


def feedback_link(pid):
    return '<section class="card"><h2>Teach Superhuman</h2><p>Save reusable feedback from this work as an explicit note.</p><a class="button secondary" href="/memory/feedback/' + views.esc(pid) + '">Save feedback or a decision</a></section>'


def install(app):
    def render(body, title='Memory'):
        return HTMLResponse(views.page(body, title))

    def error(exc):
        raise HTTPException(400, str(exc)) from exc

    @app.get('/memory')
    def home(scope: str = '', status: str = '', q: str = '', page: int = 1):
        if scope and scope not in scopes() or len(q) > 200 or not 1 <= page <= 10000:
            raise HTTPException(400, 'Invalid memory filter')
        try:
            records = Store().list(scope or None, status or None, q, limit=50, offset=(page - 1) * 50)
        except ValueError as exc:
            error(exc)
        body = '<p class="muted">YOUR CONTEXT, UNDER YOUR CONTROL</p><h1>Memory and feedback</h1>'
        body += '<p>Save what matters, correct it as things change, and inspect what a task will use. '
        body += 'Saving notes uses no model requests. This does not train or change the underlying model.</p>'
        body += '<div class="stack"><a class="button secondary" href="/memory/briefing">Work briefing</a><a class="button secondary" href="/memory/preview">Preview task context</a></div>'
        body += '<section class="card"><h2>Save an update</h2>' + form(scope=scope or 'global') + '</section>'
        body += '<section class="card"><h2>Find notes</h2><form method="get" action="/memory"><label>Search<input name="q" maxlength="200" value="' + views.esc(q) + '"></label><label>Workstream<select name="scope">' + options(('', *scopes()), scope) + '</select></label><label>Status<select name="status">' + options(('', *STATUSES), status) + '</select></label><button>Search</button></form></section>'
        for r in records:
            flags = r['status'] + ' · ' + r['scope'] + ' · ' + r['kind']
            if r['sensitive']:
                flags += ' · sensitive'
            if r['expires_on'] and r['expires_on'] < today().isoformat():
                flags += ' · expired'
            body += '<article class="card"><span class="badge">' + views.esc(flags) + '</span><h2><a href="/memory/' + r['id'] + '">' + views.esc(r['title']) + '</a></h2><pre>' + views.esc(r['content']) + '</pre><small>Version ' + str(r['version']) + ' · Updated ' + views.esc(r['updated_at']) + '</small></article>'
        if not records:
            body += '<p>No notes match this view.</p>'
        # Preserve filters through pagination without embedding user text in HTML unescaped.
        from urllib.parse import urlencode
        for label, number in (('Previous page', page - 1), ('Next page', page + 1)):
            if number > 0 and (label == 'Previous page' or len(records) == 50):
                body += '<p><a href="/memory?' + views.esc(urlencode(dict(scope=scope, status=status, q=q, page=number))) + '">' + label + '</a></p>'
        body += '<p class="muted">Archiving stops future selection. Earlier outputs and version history retain their saved content. '
        body += 'Existing legacy identity and memory records remain separate and unchanged.</p>'
        return render(body)

    @app.post('/memory/add')
    def add(scope: str = Form(...), kind: str = Form(...), title: str = Form(...),
            content: str = Form(...), source_type: str = Form('user'), source: str = Form(''),
            status: str = Form('proposed'), sensitive: str = Form(''), genre: str = Form('all'),
            expires_on: str = Form('')):
        if scope not in scopes() or sensitive not in ('', 'yes'):
            raise HTTPException(400, 'Invalid scope or sensitive flag')
        try:
            record = Store().add(scope, kind, title, content, source_type, source, status,
                                 sensitive == 'yes', genre, expires_on)
        except ValueError as exc:
            error(exc)
        return RedirectResponse('/memory/' + record['id'], status_code=303)

    @app.get('/memory/preview')
    def preview_form():
        return render('<h1>Preview task context</h1><p>This is a local preview; it makes no model requests. '
                      'It uses the same selector as drafting and research. Model output can still be wrong.</p>'
                      '<section class="card"><form method="post" action="/memory/preview">'
                      '<label>Workstream<select name="scope">' + options(scopes()[1:], scopes()[1]) + '</select></label>'
                      '<label>Task title<input name="title" maxlength="180" required></label>'
                      '<label>Task details<textarea name="details" maxlength="12000"></textarea></label>'
                      '<button>Preview context</button></form></section>')

    @app.post('/memory/preview')
    def preview(scope: str = Form(...), title: str = Form(...), details: str = Form('')):
        if scope not in scopes()[1:] or not 1 <= len(title) <= 180 or len(details) > 12000:
            raise HTTPException(400, 'Invalid preview input')
        from superhuman.identity.selection import select_context
        selected = select_context(scope, title, details)
        return render('<h1>Context for this task</h1><h2>Preferences</h2><pre>' + views.esc(selected['preferences']) +
                      '</pre><h2>Reference notes</h2><pre>' + views.esc(selected['references']) +
                      '</pre><h2>Selection details</h2><pre>' + views.esc(json.dumps(selected['trace'], indent=2, ensure_ascii=False)) + '</pre>')

    @app.get('/memory/briefing')
    def briefing():
        from superhuman.runtime import engine
        from superhuman.hosted import jobs
        state = engine.status()
        worker = jobs.worker_status()
        body = '<h1>Work briefing</h1><p>This view summarises saved state. It does not read inboxes, '
        body += 'schedule reminders or create work automatically.</p><section class="card"><h2>Worker</h2><p>'
        body += ('Online' if worker['online'] else 'Offline') + (' · Paused' if worker['paused'] else '') + '</p></section>'
        for p in state['projects']:
            if p['status'] == 'approved':
                continue
            body += '<article class="card"><h2><a href="/work/' + views.esc(p['id']) + '">' + views.esc(p['objective']) + '</a></h2><p>' + views.esc(views.label(p['status'])) + '</p><p>' + views.esc('; '.join(p['attention']) or 'No additional attention flags') + '</p></article>'
        body += '<h2>Recent updates and decisions</h2>'
        recent = [r for r in Store().list(status='confirmed', limit=100) if r['kind'] in ('decision', 'update', 'feedback')][:10]
        for r in recent:
            body += '<section class="card"><h3><a href="/memory/' + r['id'] + '">' + views.esc(r['title']) + '</a></h3><p>' + views.esc(r['scope']) + (' · Expired' if r['expires_on'] and r['expires_on'] < today().isoformat() else '') + '</p><pre>' + views.esc(r['content']) + '</pre></section>'
        return render(body, 'Work briefing')

    @app.get('/memory/feedback/{pid}')
    def feedback(pid: str):
        from superhuman.projects import engine
        try:
            project = engine.get(pid)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        body = '<h1>Feedback from this work</h1><p>Describe a reusable correction or decision. '
        body += 'This creates a separate note; it does not approve, retry or rewrite the task.</p>'
        body += '<section class="card">' + form(scope=project['workstream'], source='project:' + pid,
                                                title='Feedback: ' + project['objective'][:165], kind='feedback') + '</section>'
        return render(body)

    @app.get('/memory/{note_id}')
    def edit(note_id: str):
        try:
            record = Store().get(note_id)
            history = Store().history(note_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        body = '<h1>' + views.esc(record['title']) + '</h1><p>Version ' + str(record['version']) + '</p><section class="card">' + form(record) + '</section>'
        body += '<h2>Version history</h2>'
        for old in history:
            body += '<details class="card"><summary>Version ' + str(old['version']) + ' · ' + views.esc(old['status']) + ' · ' + views.esc(old['updated_at']) + '</summary><pre>' + views.esc(json.dumps(old, ensure_ascii=False, indent=2)) + '</pre></details>'
        return render(body, record['title'])

    @app.post('/memory/{note_id}/save')
    def save(note_id: str, version: int = Form(...), scope: str = Form(...), kind: str = Form(...),
             title: str = Form(...), content: str = Form(...), source_type: str = Form(...),
             source: str = Form(''), status: str = Form(...), sensitive: str = Form(''),
             genre: str = Form('all'), expires_on: str = Form('')):
        if scope not in scopes() or sensitive not in ('', 'yes'):
            raise HTTPException(400, 'Invalid scope or sensitive flag')
        try:
            Store().update(note_id, version, scope=scope, kind=kind, title=title, content=content,
                           source_type=source_type, source=source, status=status, sensitive=sensitive == 'yes',
                           genre=genre, expires_on=expires_on)
        except ValueError as exc:
            error(exc)
        return RedirectResponse('/memory/' + note_id, status_code=303)
