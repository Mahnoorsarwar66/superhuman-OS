"""Calendar-linked meeting workbench. Models run only after explicit approval."""
from uuid import uuid4
from fastapi import Form,HTTPException
from fastapi.responses import HTMLResponse,RedirectResponse
from superhuman.hosted import views,jobs
from superhuman.dialogue.web import options
from superhuman.briefing import engine as briefing
from . import store


def install(app):
    esc=views.esc
    def render(body,title='Meeting workbench'):return HTMLResponse(views.page(body,title))
    def error(exc):raise HTTPException(400,str(exc)) from exc
    def meeting(event_id):
        try:return store.calendar.get(event_id)
        except ValueError as exc:raise HTTPException(404,str(exc)) from exc
    def go(url):return RedirectResponse(url,status_code=303)
    def note_fields(values):
        return ''.join('<label>'+esc(label)+'<textarea name="'+key+'" maxlength="'+str(limit)+'">'+esc(values[key])+'</textarea></label>' for key,label,limit in store.FIELDS)
    def links(event_id):return '<p><a href="/calendar/event/'+event_id+'">Calendar details and email sources</a> · <a href="/meetings">All meeting workbenches</a></p>'

    @app.get('/meetings')
    def home(view:str='upcoming',page:int=1):
        try:rows=store.calendar.events(view,page)
        except ValueError as exc:error(exc)
        body='<h1>Meeting workbench</h1><p>Prepare before a meeting, record what happened, then review draft minutes.</p><nav><a href="/meetings">Upcoming</a><a href="/meetings?view=past">Past</a><a href="/meetings?view=cancelled">Cancelled</a><a href="/calendar">Calendar</a></nav>'
        for row in rows:
            body+='<article class="card"><h2><a href="/meetings/'+row['id']+'">'+esc(row['title'])+'</a></h2><p>'+esc(briefing.local_time(row['start_at']))+' · '+esc(row['status'])+'</p></article>'
        if not rows:body+='<p>No '+esc(view)+' meetings on this page. Add or confirm a meeting in Calendar first.</p>'
        if page>1:body+='<a href="/meetings?view='+view+'&page='+str(page-1)+'">Previous</a> '
        if len(rows)==50:body+='<a href="/meetings?view='+view+'&page='+str(page+1)+'">Next</a>'
        return render(body)

    @app.get('/meetings/{event_id}')
    def detail(event_id:str):
        row=meeting(event_id);record=store.notes(event_id);tasks=store.jobs(event_id)
        body='<h1>'+esc(row['title'])+'</h1><p>'+esc(briefing.local_time(row['start_at']))+' · '+esc(row['status'])+'</p>'+links(event_id)
        body+='<section class="card"><h2>Meeting drafts</h2><p>Save note changes below before opening a drafting form. Review and edit the full task instructions and choose a workstream before approving. Each draft authorises up to 3 model requests. Opening forms or saving notes makes no model requests.</p><div class="stack">'
        if row['status']=='confirmed':body+='<a class="button" href="/meetings/'+event_id+'/draft/preparation">Review preparation task</a>'
        body+='<a class="button secondary" href="/meetings/'+event_id+'/draft/minutes">Review minutes task</a></div></section>'
        body+='<section class="card"><h2>Your meeting record</h2><p>Keep participant statements separate from interpretation. Record decisions and actions as agreed only when explicitly confirmed. Leave unknown fields blank. Total note limit: 6000 characters.</p><p>These notes stay attached to this meeting. They are not automatically added to general memory. Superhuman does not join or record the meeting in this version.</p>'
        body+='<p>Saved version: '+str(record['version'])+(' · '+esc(briefing.local_time(record['updated_at'])) if record['updated_at'] else ' · No notes saved')+'</p><form method="post" action="/meetings/'+event_id+'/notes"><input type="hidden" name="version" value="'+str(record['version'])+'">'+note_fields(record['fields'])+'<button>Save meeting notes · 0 model requests</button></form><p><a href="/meetings/'+event_id+'/history">Read saved note history</a></p></section>'
        body+='<h2>Draft tasks and results</h2>'
        for task in tasks:
            body+='<article class="card"><h3>'+esc(task['objective'])+'</h3><p>'+esc(task['workstream'])+' · '+esc(views.label(task['status']))+' · '+str(task['used_calls'])+' / '+str(task['max_calls'])+' requests</p><p>Based on calendar version '+str(task['event_version'])+' and notes version '+str(task['notes_version'])+'.</p>'
            if task['event_version']!=row['version'] or task['notes_version']!=record['version']:body+='<p class="badge">Meeting or notes changed since this task was approved. Its saved instructions stay unchanged.</p>'
            body+='<p><a class="button" href="/work/'+task['project_id']+'">Open draft and review</a></p></article>'
        if not tasks:body+='<p>No drafting tasks have been approved for this meeting.</p>'
        if len(tasks)==50:body+='<p>Showing the 50 most recent tasks. Older tasks remain in Projects.</p>'
        return render(body,row['title'])

    @app.post('/meetings/{event_id}/notes')
    def save(event_id:str,version:int=Form(...),attendees:str=Form(''),statements:str=Form(''),interpretation:str=Form(''),decisions:str=Form(''),actions:str=Form(''),questions:str=Form('')):
        values=dict(attendees=attendees,statements=statements,interpretation=interpretation,decisions=decisions,actions=actions,questions=questions)
        try:store.save_notes(event_id,version,values)
        except ValueError as exc:error(exc)
        return go('/meetings/'+event_id)

    @app.get('/meetings/{event_id}/history')
    def history(event_id:str):
        meeting(event_id);rows=store.history(event_id)
        body='<h1>Saved meeting note history</h1><p><a href="/meetings/'+event_id+'">Back to meeting</a></p><p>The 20 most recent saved versions are shown. Older versions remain stored. This is a read-only history; edit the current record to make changes.</p>'
        for row in rows:
            body+='<section class="card"><h2>Version '+str(row['version'])+' · '+esc(briefing.local_time(row['created_at']))+'</h2>'
            for key,label,_ in store.FIELDS:body+='<h3>'+esc(label)+'</h3><pre>'+esc(row['fields'][key] or '(blank)')+'</pre>'
            body+='</section>'
        if not rows:body+='<p>No saved versions yet.</p>'
        return render(body,'Meeting note history')

    @app.get('/meetings/{event_id}/draft/{kind}')
    def preview(event_id:str,kind:str):
        meeting(event_id)
        try:task=store.draft(event_id,kind)
        except ValueError as exc:error(exc)
        worker=jobs.worker_status()
        body='<h1>Review '+esc(store.KINDS[kind].lower())+' task</h1>'+links(event_id)
        body+='<p>Worker: '+('Online' if worker['online'] else 'Offline')+(' · Paused' if worker['paused'] else '')+'. Approval queues a local drafting task with up to 3 model attempts. Failed attempts count. No automatic paid retries.</p>'
        body+='<p>The complete model task is below. It contains the shown calendar details and saved owner notes, plus normal context for your chosen workstream. Full emails, attachments and recordings are not included. Check for private information before approval. Drafting does not publish minutes or update your notes.</p>'
        body+='<form method="post" action="/meetings/'+event_id+'/queue"><input type="hidden" name="kind" value="'+kind+'"><input type="hidden" name="submission_key" value="'+uuid4().hex+'"><input type="hidden" name="event_version" value="'+str(task['event_version'])+'"><input type="hidden" name="notes_version" value="'+str(task['notes_version'])+'">'
        body+='<label>Workstream<select name="scope" required><option value="" selected>Choose a workstream</option>'+options(store.dialogue.scopes(),None)+'</select></label><label>Task title<input name="title" maxlength="180" required value="'+esc(task['title'])+'"></label><label>Complete task instructions<textarea name="details" maxlength="12000" required style="min-height:420px">'+esc(task['details'])+'</textarea></label><button>Approve draft · up to 3 model requests</button></form>'
        return render(body,'Review meeting draft')

    @app.post('/meetings/{event_id}/queue')
    def queue(event_id:str,kind:str=Form(...),scope:str=Form(...),title:str=Form(...),details:str=Form(...),event_version:int=Form(...),notes_version:int=Form(...),submission_key:str=Form(...)):
        try:pid=store.queue(event_id,kind,scope,title,details,event_version,notes_version,submission_key)
        except ValueError as exc:error(exc)
        return go('/work/'+pid)
