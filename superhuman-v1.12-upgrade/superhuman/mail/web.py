"""Private mobile-friendly inbox previews and review-first reports."""
from uuid import uuid4
from fastapi import Form,HTTPException
from fastapi.responses import HTMLResponse,RedirectResponse
from superhuman.hosted import views,jobs
from . import store


def install(app):
    esc=views.esc
    def render(body,title='Inboxes'):return HTMLResponse(views.page(body,title))
    def get(slot):
        try:return store.account(slot)
        except ValueError as exc:raise HTTPException(404,str(exc)) from exc
    def redirect(slot):return RedirectResponse('/inboxes/'+slot,status_code=303)
    def error(exc):raise HTTPException(400,str(exc)) from exc

    @app.get('/inboxes')
    def home():
        worker=jobs.worker_status()
        body='<h1>Your inboxes</h1><p>Read-only previews, reports and tasks for approval.</p>'
        body+='<p>Worker: '+('Online' if worker['online'] else 'Offline')+(' · Paused' if worker['paused'] else '')+'. <a href="/inboxes/setup">Connection instructions</a></p>'
        for a in store.accounts():
            body+='<section class="card"><h2><a href="/inboxes/'+a['id']+'">'+esc(a['label'])+'</a></h2><p>'+esc(a['email'] or 'Not connected')+'</p><p>'+('Connected' if a['connected'] else 'Disconnected')+' · '+('10-minute reading enabled' if a['auto_sync'] else 'Manual reading')+'</p>'
            if a['last_sync']:body+='<p>Last successful read: '+esc(a['last_sync'])+'</p>'
            if a['last_error']:body+='<p class="error">'+esc(a['last_error'])+'</p>'
            body+='</section>'
        return render(body)

    @app.get('/inboxes/setup')
    def setup():
        return render('<h1>Connect your email accounts</h1><p>Use the supplied CONNECTION_GUIDE.txt to connect each account on the server. Gmail uses Google consent in your laptop browser; Titan uses its own mailbox password or supported app password, entered privately in the server terminal.</p><p>No passwords or tokens should be pasted into Talk. The account email is checked before Gmail credentials are saved. Each inbox needs a workstream selected from your existing configuration.</p><p>Read scope: INBOX only, up to 25 recent messages from the last 7 days per sync. Large message bodies and all attachments are omitted. This is a preview, not a complete archive or guaranteed urgent-message alert system.</p><p>Optional automatic reading runs about every 10 minutes while the worker is online and unpaused. Reports only run when requested; each report uses one model attempt and can suggest up to three local drafting tasks for separate approval.</p><p>Disconnect stops future reads and removes the stored credential. Saved previews, reports and tasks remain private working records. For Gmail, revoke access separately in Google Account settings if desired; that can affect other accounts using the same Google project.</p>')

    @app.get('/inboxes/{slot}')
    def inbox(slot:str):
        a=get(slot);rows=store.messages(slot)
        body='<h1>'+esc(a['label'])+'</h1><p>'+esc(a['email'] or 'Not connected')+'</p><p>Workstream: '+esc(a['scope'] or 'Choose during setup')+'</p>'
        body+='<p><a href="/inboxes">All inboxes</a> · <a href="/inboxes/'+slot+'">Refresh</a> · <a href="/inboxes/setup">Setup</a></p>'
        body+='<p>Reads cover up to 25 recent INBOX messages from the last 7 days. Saved previews can be older. Attachments are excluded; message text may be shortened. No messages are marked read, starred, sent or deleted.</p>'
        if a['last_error']:body+='<p class="error">'+esc(a['last_error'])+'</p>'
        if a['limited']:body+='<p class="error">The last sync reached a message or time limit. Some messages were not included.</p>'
        with store.p.connect() as db:
            pending=db.execute("SELECT status FROM mail_syncs WHERE account_id=? ORDER BY created DESC LIMIT 1",(slot,)).fetchone()
            reports=db.execute('SELECT * FROM mail_reports WHERE account_id=? ORDER BY created_at DESC LIMIT 20',(slot,)).fetchall()
        if pending:body+='<p>Latest read job: '+esc(pending['status'])+'.</p>'
        if a['connected']:
            body+='<section class="card"><form method="post" action="/inboxes/'+slot+'/sync"><button>Read recent mail · 0 model requests</button></form>'
            body+='<form method="post" action="/inboxes/'+slot+'/auto"><input type="hidden" name="enabled" value="'+('0' if a['auto_sync'] else '1')+'"><p><button class="secondary">'+('Disable' if a['auto_sync'] else 'Enable')+' reading every 10 minutes</button></p></form></section>'
        if rows:
            body+='<section class="card"><h2>Prepare a report</h2><p>This sends excerpts of up to 12 newest saved messages from this inbox to your configured model. Other inboxes and general memory are excluded. Review the original email for decisions that matter. Nothing is sent to email recipients.</p><form method="post" action="/inboxes/'+slot+'/report"><input type="hidden" name="submission_key" value="'+uuid4().hex+'"><button>Request report · 1 model attempt</button></form></section>'
        if reports:
            body+='<h2>Saved reports</h2>'
            for report in reports:body+='<p><a href="/talk/'+report['thread_id']+'">'+esc(report['created_at'])+' · report and task suggestions</a></p>'
        body+='<h2>Saved message previews</h2>'
        for m in rows:
            body+='<section class="card"><h3><a href="/inboxes/'+slot+'/message/'+m['id']+'">'+esc(m['subject'])+'</a></h3><p>'+esc(m['sender'])+'<br>'+esc(m['sent_at'])+'</p><p>'+esc(m['body'][:220])+'</p></section>'
        if not rows:body+='<p>No previews saved yet. Connect the account, then read recent mail.</p>'
        if a['connected']:body+='<details class="card"><summary>Disconnect this inbox</summary><p>Stops future reading. Saved previews and reports remain.</p><form method="post" action="/inboxes/'+slot+'/disconnect"><button class="secondary">Disconnect</button></form></details>'
        return render(body,a['label'])

    @app.get('/inboxes/{slot}/message/{key}')
    def message(slot:str,key:str):
        a=get(slot)
        try:m=store.message(slot,key)
        except ValueError as exc:raise HTTPException(404,str(exc)) from exc
        return render('<p>'+esc(a['label'])+' · '+esc(a['email'])+'</p><h1>'+esc(m['subject'])+'</h1><p>'+esc(m['sender'])+'<br>'+esc(m['sent_at'])+'</p><p>Source ID: '+esc(m['id'])+'</p><p class="muted">'+esc(m['notice'])+'</p><pre>'+esc(m['body'])+'</pre><p>Sender identity and claims have not been independently verified.</p>')

    @app.post('/inboxes/{slot}/sync')
    def sync(slot:str):
        try:store.queue_sync(slot)
        except ValueError as exc:error(exc)
        return redirect(slot)

    @app.post('/inboxes/{slot}/auto')
    def auto(slot:str,enabled:int=Form(...)):
        try:
            if enabled not in (0,1):raise ValueError('Invalid sync option')
            store.set_auto(slot,bool(enabled))
        except ValueError as exc:error(exc)
        return redirect(slot)

    @app.post('/inboxes/{slot}/report')
    def report(slot:str,submission_key:str=Form(...)):
        try:thread=store.make_report(slot,submission_key)
        except ValueError as exc:error(exc)
        return RedirectResponse('/talk/'+thread,status_code=303)

    @app.post('/inboxes/{slot}/disconnect')
    def disconnect(slot:str):
        try:store.disconnect(slot)
        except ValueError as exc:error(exc)
        return redirect(slot)
