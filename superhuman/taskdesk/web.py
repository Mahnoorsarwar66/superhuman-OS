"""Private Task Desk. Viewing, editing forms and saving proposed feedback are free."""
import json
from fastapi import Form,HTTPException
from fastapi.responses import HTMLResponse,RedirectResponse
from superhuman.hosted import views,jobs
from superhuman.dialogue.web import options
from superhuman.mail import store as mail
from superhuman.briefing import engine as briefing
from . import store


def report_for(thread_id):
    mail.initialize()
    with store.p.connect() as db:row=db.execute('SELECT * FROM mail_reports WHERE thread_id=?',(thread_id,)).fetchone()
    return dict(row) if row else None


def install(app):
    esc=views.esc
    def render(body,title='Task Desk'):return HTMLResponse(views.page(body,title))
    def get(key):
        try:return store.get(key)
        except ValueError as exc:raise HTTPException(404,str(exc)) from exc
    def error(exc):raise HTTPException(400,str(exc)) from exc

    @app.get('/tasks')
    def home(status:str='proposed',page:int=1):
        try:rows=store.listing(status,page);counts=store.counts()
        except ValueError as exc:error(exc)
        worker=jobs.worker_status()
        body='<h1>Task Desk</h1><p>Review suggestions, choose the right workstream, then approve useful work.</p>'
        body+='<p>'+str(counts.get('proposed',0))+' proposed · '+str(counts.get('approved',0))+' approved · '+str(counts.get('needs_review',0))+' outputs ready for review · '+str(counts.get('blocked',0))+' projects need attention.</p>'
        body+='<p>Worker: '+('Online' if worker['online'] else 'Offline')+(' · Paused' if worker['paused'] else '')+'.</p><nav>'
        for value in ('proposed','approved','dismissed'):body+='<a href="/tasks?status='+value+'">'+value.capitalize()+'</a>'
        body+='</nav><p class="muted">Opening this page makes no model requests. Approval queues the edited task with its shown request budget. Workstream selection controls its specialist and normal memory context; it does not move the source inbox or change future suggestions.</p>'
        for task in rows:
            title=task['project_title'] if task['status']=='approved' and task['project_title'] else task['title']
            body+='<section class="card"><span class="badge">'+esc(task['status'])+'</span><h2>'+esc(title)+'</h2><p>'+esc(task['rationale'])+'</p>'
            body+='<p>Source: <a href="/talk/'+task['thread_id']+'">'+esc(task['conversation_title'])+'</a> · Suggested '+esc(briefing.local_time(task['created_at']))+'</p>'
            if report_for(task['thread_id']):body+='<p><a href="/tasks/'+task['id']+'/sources">Inspect saved source emails</a></p>'
            if task['status']=='proposed':
                budget=3 if task['kind']=='collab' else 1
                body+='<p>'+('Local draft' if task['kind']=='collab' else 'Public-web research')+' · Approval authorises up to '+str(budget)+' model requests. Review the full instructions and destination.</p>'
                body+='<form method="post" action="/tasks/'+task['id']+'/approve"><input type="hidden" name="expected_hash" value="'+esc(task['proposal_hash'])+'">'
                body+='<label>Workstream<select name="scope">'+options(store.d.scopes(),task['source_scope'])+'</select></label>'
                body+='<label>Task title<input name="title" maxlength="180" required value="'+esc(task['title'])+'"></label><label>Task instructions<textarea name="details" maxlength="6000" required>'+esc(task['details'])+'</textarea></label><button>Approve · up to '+str(budget)+' requests</button></form>'
                body+='<form method="post" action="/tasks/'+task['id']+'/dismiss"><input type="hidden" name="expected_hash" value="'+esc(task['proposal_hash'])+'"><p><button class="secondary">Dismiss suggestion</button></p></form>'
            elif task['project_id']:
                body+='<p>Workstream: '+esc(store.chosen_scope(task))+' · '+esc(views.label(task['project_status'] or 'unavailable'))+' · '+str(task['used_calls'] or 0)+' / '+str(task['max_calls'] or 0)+' requests.</p><p><a class="button" href="/work/'+esc(task['project_id'])+'">Open work and deliverable</a></p>'
            else:body+='<pre>'+esc(task['details'])+'</pre>'
            body+='<p><a href="/tasks/'+task['id']+'/feedback">Save feedback for future work</a></p></section>'
        if not rows:body+='<p>No '+esc(status)+' suggestions on this page. Generate an inbox report or discuss a task in Talk.</p>'
        if page>1:body+='<p><a href="/tasks?status='+status+'&page='+str(page-1)+'">Previous</a></p>'
        if len(rows)==50:body+='<p><a href="/tasks?status='+status+'&page='+str(page+1)+'">Next</a></p>'
        return render(body)

    @app.post('/tasks/{key}/approve')
    def approve(key:str,expected_hash:str=Form(...),title:str=Form(...),details:str=Form(...),scope:str=Form(...)):
        task=get(key)
        try:pid=store.approve(task['thread_id'],key,expected_hash,title,details,scope=scope)
        except ValueError as exc:error(exc)
        return RedirectResponse('/work/'+pid,status_code=303)

    @app.post('/tasks/{key}/dismiss')
    def dismiss(key:str,expected_hash:str=Form(...)):
        task=get(key)
        try:store.d.dismiss(task['thread_id'],key,expected_hash)
        except ValueError as exc:error(exc)
        return RedirectResponse('/tasks',status_code=303)

    @app.get('/tasks/{key}/sources')
    def sources(key:str):
        task=get(key);report=report_for(task['thread_id'])
        if not report:raise HTTPException(404,'This suggestion has no saved inbox snapshot; open its source conversation instead.')
        payload,_=briefing.prepared(json.loads(report['snapshot']))
        body='<h1>Source emails</h1><p>'+esc(payload['label'])+' · '+esc(payload['email'])+'</p><p>These are the saved excerpts for the source report. They may contain more messages than this particular suggestion cites. Sender identities and claims are unverified.</p>'
        for source in payload['messages']:
            body+='<section class="card"><h2><a href="/briefing/source/'+report['id']+'/'+source['reference']+'">'+esc(source['reference'])+' · '+esc(source['subject'])+'</a></h2><p>'+esc(source['sender'])+' · '+esc(source['sent_local'])+'</p></section>'
        return render(body+'<p><a href="/tasks">Task Desk</a> · <a href="/talk/'+task['thread_id']+'">Source report and conversation</a></p>','Task sources')

    @app.get('/tasks/{key}/feedback')
    def feedback(key:str):
        task=get(key)
        from superhuman.knowledge.web import form
        source='project:'+task['project_id'] if task['project_id'] else 'suggestion:'+task['id']
        body='<h1>Feedback for future work</h1><p>Describe what was useful, wrong or missing. Be specific about how the next draft should change. This form creates a proposed memory note; it becomes eligible for future work only after you explicitly confirm it. Saving does not retrain a model or retry the task.</p>'
        body+='<p>Task: '+esc(task['project_title'] or task['title'])+'</p>'
        body+=form(scope=store.chosen_scope(task),title=('Feedback: '+(task['project_title'] or task['title']))[:180],kind='feedback',source=source)
        return render(body,'Review feedback note')
