"""Authenticated, server-rendered conversations and explicit approval forms."""
import json
from uuid import uuid4
from fastapi import Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from superhuman.hosted import views, jobs
from . import store


def options(values, selected):
    return ''.join('<option value="' + views.esc(value) + '"' + (' selected' if value == selected else '') + '>' + views.esc(value.replace('_', ' ')) + '</option>' for value in values)


def install(app):
    def render(body, title='Talk to Superhuman'):
        return HTMLResponse(views.page(body, title))
    def bad(exc):
        raise HTTPException(400, str(exc)) from exc
    def thread_or_404(thread_id):
        try: return store.get(thread_id)
        except ValueError as exc: raise HTTPException(404, str(exc)) from exc

    @app.get('/talk')
    def home(page: int = 1):
        if not 1 <= page <= 10000: raise HTTPException(400, 'Invalid page')
        threads = store.listing(limit=50, offset=(page - 1) * 50)
        body = '<p class="muted">THINK TOGETHER, THEN APPROVE THE WORK</p><h1>Talk to Superhuman</h1>'
        body += '<p>Discuss your work, ask questions and consider suggested tasks. Suggestions stay here until '
        body += 'you explicitly approve one. Conversation replies have no browsing or external-action tools.</p>'
        body += '<section class="card"><h2>Start a conversation</h2><form method="post" action="/talk/create">'
        body += '<label>Workstream<select name="scope">' + options(store.scopes(), store.scopes()[0]) + '</select></label>'
        body += '<label>Conversation title<input name="title" maxlength="180" required></label>'
        body += '<label>Reply-request limit<input name="max_calls" type="number" min="1" max="100" value="20" required></label>'
        body += '<p class="muted">Creating a conversation is free of model requests. Each message you send '
        body += 'authorizes one model attempt within this limit. Failed attempts also count; no automatic retries. '
        body += 'Approved tasks have separate budgets. Limits count requests, not money.</p><button>Create conversation</button></form></section>'
        for thread in threads:
            body += '<article class="card"><span class="badge">' + views.esc(thread['scope']) + '</span><h2><a href="/talk/' + thread['id'] + '">' + views.esc(thread['title']) + '</a></h2><p>' + str(thread['used_calls']) + ' / ' + str(thread['max_calls']) + ' reply requests</p></article>'
        if page > 1: body += '<p><a href="/talk?page=' + str(page - 1) + '">Previous</a></p>'
        if len(threads) == 50: body += '<p><a href="/talk?page=' + str(page + 1) + '">Next</a></p>'
        return render(body)

    @app.post('/talk/create')
    def create(scope: str = Form(...), title: str = Form(...), max_calls: int = Form(20)):
        try: thread_id = store.create(scope, title, max_calls)
        except ValueError as exc: bad(exc)
        return RedirectResponse('/talk/' + thread_id, status_code=303)

    @app.get('/talk/{thread_id}')
    def conversation(thread_id: str, before: int = 0):
        thread = thread_or_404(thread_id)
        if before < 0: raise HTTPException(400, 'Invalid history page')
        turns = store.turns(thread_id, before=before or None)
        suggestions = store.suggestions(thread_id, turn_ids=[turn['id'] for turn in turns])
        latest = store.turns(thread_id, limit=1)
        pending = bool(latest and latest[0]['status'] in ('queued', 'running'))
        worker = jobs.worker_status()
        body = '<p class="muted">' + views.esc(thread['scope']) + '</p><h1>' + views.esc(thread['title']) + '</h1>'
        body += '<p>' + str(thread['used_calls']) + ' / ' + str(thread['max_calls']) + ' reply requests used. '
        body += 'Worker: ' + ('Online' if worker['online'] else 'Offline') + (' · Paused' if worker['paused'] else '') + '.</p>'
        body += '<div class="stack"><a class="button secondary" href="/talk/' + thread_id + '">Refresh / latest</a><a class="button secondary" href="/talk">All conversations</a><a class="button secondary" href="/memory">Memory</a></div>'
        body += '<p class="muted">Relevant confirmed memory may be sent with your message. Sensitive notes are excluded '
        body += 'from automatic retrieval. Recent conversation history is included; older history is bounded and can be omitted. '
        body += 'Avoid entering credentials. A reply is a model draft, not independently verified evidence.</p>'
        for turn in turns:
            body += '<section class="card"><h2>You · message ' + str(turn['ordinal']) + '</h2><pre>' + views.esc(turn['user_text']) + '</pre>'
            body += '<p><a href="/talk/' + thread_id + '/turn/' + turn['id'] + '/remember">Save this update to memory</a></p>'
            body += '<span class="badge">' + views.esc(turn['status'].replace('_', ' ')) + '</span>'
            if turn['reply']: body += '<h2>Superhuman</h2><pre>' + views.esc(turn['reply']) + '</pre>'
            if turn['error']: body += '<p class="error">' + views.esc(turn['error']) + '</p>'
            if turn['status'] == 'queued':
                body += '<form method="post" action="/talk/' + thread_id + '/cancel"><input type="hidden" name="turn_id" value="' + turn['id'] + '"><button class="secondary">Cancel queued message</button></form>'
            if turn['context_json'] or turn['raw_response']:
                body += '<p><a href="/talk/' + thread_id + '/turn/' + turn['id'] + '/details">Inspect context and saved model response</a></p>'
            body += '</section>'
            for suggestion in [s for s in suggestions if s['turn_id'] == turn['id']]:
                budget = 3 if suggestion['kind'] == 'collab' else 1
                body += '<section class="card"><span class="badge">Task suggestion · ' + views.esc(suggestion['status']) + '</span>'
                body += '<h3>' + views.esc(suggestion['title']) + '</h3><p>' + views.esc(suggestion['rationale']) + '</p>'
                if suggestion['status'] == 'proposed':
                    body += '<p>Review and edit the task and choose its workstream before approval. Suggested workstream: ' + views.esc(thread['scope']) + '. Type: ' + ('local draft' if suggestion['kind'] == 'collab' else 'public-web research') + '. Approving authorizes up to ' + str(budget) + ' additional model requests and queues execution.</p>'
                    body += '<form method="post" action="/talk/' + thread_id + '/approve"><input type="hidden" name="suggestion_id" value="' + suggestion['id'] + '"><input type="hidden" name="expected_hash" value="' + suggestion['proposal_hash'] + '">'
                    body += '<label>Workstream<select name="scope">' + options(store.scopes(), thread['scope']) + '</select></label><label>Task title<input name="title" maxlength="180" required value="' + views.esc(suggestion['title']) + '"></label><label>Task instructions<textarea name="details" maxlength="6000" required>' + views.esc(suggestion['details']) + '</textarea></label><button>Approve task · up to ' + str(budget) + ' requests</button></form>'
                    body += '<form method="post" action="/talk/' + thread_id + '/dismiss"><input type="hidden" name="suggestion_id" value="' + suggestion['id'] + '"><input type="hidden" name="expected_hash" value="' + suggestion['proposal_hash'] + '"><p><button class="secondary">Dismiss suggestion</button></p></form>'
                elif suggestion['project_id']:
                    body += '<p><a href="/work/' + views.esc(suggestion['project_id']) + '">Open approved task and its saved instructions</a></p>'
                else: body += '<pre>' + views.esc(suggestion['details']) + '</pre>'
                body += '</section>'
        if len(turns) == 50:
            body += '<p><a href="/talk/' + thread_id + '?before=' + str(turns[0]['ordinal']) + '">Older messages</a></p>'
        if not before:
            if pending:
                body += '<section class="card"><p>Your reply is queued or running. Refresh to see it. '
                body += 'The worker also handles approved tasks; it may be busy.</p></section>'
            else:
                body += '<section class="card"><h2>Continue the conversation</h2><form method="post" action="/talk/' + thread_id + '/send"><input type="hidden" name="submission_key" value="' + uuid4().hex + '"><label>Message<textarea name="message" maxlength="6000" required></textarea></label><p>Sending authorizes one reply request. Suggested tasks wait for separate approval.</p><button>Send · 1 reply request</button></form></section>'
            body += '<details class="card"><summary>Change conversation request limit</summary><form method="post" action="/talk/' + thread_id + '/budget"><label>Total reply-request limit<input type="number" name="maximum" min="1" max="100" value="' + str(thread['max_calls']) + '" required></label><button>Save request limit</button></form></details>'
        return render(body, thread['title'])

    @app.post('/talk/{thread_id}/send')
    def send(thread_id: str, message: str = Form(...), submission_key: str = Form(...)):
        try: store.send(thread_id, message, submission_key)
        except ValueError as exc: bad(exc)
        return RedirectResponse('/talk/' + thread_id, status_code=303)

    @app.post('/talk/{thread_id}/approve')
    def approve(thread_id: str, suggestion_id: str = Form(...), expected_hash: str = Form(...),
                title: str = Form(...), details: str = Form(...), scope: str = Form('')):
        try: pid = store.approve(thread_id, suggestion_id, expected_hash, title, details, scope=scope or None)
        except ValueError as exc: bad(exc)
        return RedirectResponse('/work/' + pid, status_code=303)

    @app.post('/talk/{thread_id}/dismiss')
    def dismiss(thread_id: str, suggestion_id: str = Form(...), expected_hash: str = Form(...)):
        try: store.dismiss(thread_id, suggestion_id, expected_hash)
        except ValueError as exc: bad(exc)
        return RedirectResponse('/talk/' + thread_id, status_code=303)

    @app.post('/talk/{thread_id}/budget')
    def budget(thread_id: str, maximum: int = Form(...)):
        try: store.set_budget(thread_id, maximum)
        except ValueError as exc: bad(exc)
        return RedirectResponse('/talk/' + thread_id, status_code=303)

    @app.post('/talk/{thread_id}/cancel')
    def cancel(thread_id: str, turn_id: str = Form(...)):
        try: store.cancel(thread_id, turn_id)
        except ValueError as exc: bad(exc)
        return RedirectResponse('/talk/' + thread_id, status_code=303)

    def owned_turn(thread_id, turn_id):
        thread = thread_or_404(thread_id)
        try: turn = store.turn(turn_id)
        except ValueError as exc: raise HTTPException(404, str(exc)) from exc
        if turn['thread_id'] != thread_id: raise HTTPException(404, 'Message not found in this conversation')
        return thread, turn

    @app.get('/talk/{thread_id}/turn/{turn_id}/details')
    def details(thread_id: str, turn_id: str):
        thread, turn = owned_turn(thread_id, turn_id)
        return render('<h1>Saved response details</h1><p>Private diagnostic material. '
                      'Model output is untrusted text.</p><h2>Context selection</h2><pre>' +
                      views.esc(turn['context_json'] or 'Not captured') + '</pre><h2>Raw model response</h2><pre>' +
                      views.esc(turn['raw_response'] or 'Not captured') + '</pre>')

    @app.get('/talk/{thread_id}/turn/{turn_id}/remember')
    def remember(thread_id: str, turn_id: str):
        thread, turn = owned_turn(thread_id, turn_id)
        from superhuman.knowledge.web import form
        content = turn['user_text'] if len(turn['user_text']) <= 4000 else ''
        body = '<h1>Save an update to memory</h1><p>Review and edit before saving. '
        body += 'The new note defaults to Proposed. Choose Confirmed only when it should be eligible for future tasks.</p>'
        if not content:
            body += '<p>Your message exceeds the memory-note limit. Copy a relevant excerpt of up to 4000 characters into the form.</p><pre>' + views.esc(turn['user_text']) + '</pre>'
        body += '<section class="card">' + form(scope=thread['scope'], title=thread['title'],
                                               source='conversation:' + thread_id + '/turn:' + turn_id,
                                               content=content) + '</section>'
        return render(body, 'Review memory note')
