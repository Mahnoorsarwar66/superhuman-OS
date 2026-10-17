"""Owner-reviewed calendar, protected by the existing hosted boundary."""
from datetime import datetime,timezone,timedelta
import json
from uuid import uuid4
from fastapi import Form,HTTPException
from fastapi.responses import HTMLResponse,RedirectResponse,Response
from superhuman.hosted import views
from superhuman.briefing import engine as briefing
from . import store,export


def local_input(value):return datetime.fromisoformat(value).astimezone(store.PKT).strftime('%Y-%m-%dT%H:%M') if value else ''


def form(action,title='',start_at='',end_at='',notes='',hidden='',button='Save meeting'):
    esc=views.esc
    return '<form method="post" action="'+action+'">'+hidden+'<label>Meeting title<input name="title" maxlength="180" required value="'+esc(title)+'"></label><label>Starts (Pakistan time, UTC+5)<input type="datetime-local" name="start_at" required value="'+esc(local_input(start_at))+'"></label><label>Ends (optional, Pakistan time)<input type="datetime-local" name="end_at" value="'+esc(local_input(end_at))+'"></label><label>Notes<textarea name="notes" maxlength="4000">'+esc(notes)+'</textarea></label><button>'+button+'</button></form>'


def source_links(row):
    refs=json.loads(row['sources_json'])
    return ' · '.join('<a href="/briefing/source/'+views.esc(row['report_id'])+'/'+views.esc(ref)+'">'+views.esc(ref)+'</a>' for ref in refs)


def install(app):
    esc=views.esc
    def render(body,title='Calendar'):return HTMLResponse(views.page(body,title))
    def error(exc):raise HTTPException(400,str(exc)) from exc
    def event(key):
        try:return store.get(key)
        except ValueError as exc:raise HTTPException(404,str(exc)) from exc
    def candidate(key):
        try:return store.candidate(key)
        except ValueError as exc:raise HTTPException(404,str(exc)) from exc
    def go(url):return RedirectResponse(url,status_code=303)
    def parsed(title,start_at,end_at,notes):return store.fields(title,start_at,end_at,notes,local=True)
    def nav():return '<nav><a href="/calendar">Upcoming</a><a href="/calendar?view=past">Past</a><a href="/calendar?view=cancelled">Cancelled</a><a href="/calendar/suggestions">Review suggestions</a><a href="/calendar/new">Add meeting</a></nav>'
    def event_card(row):
        body='<article class="card"><h2><a href="/calendar/event/'+row['id']+'">'+esc(row['title'])+'</a></h2><p>'+esc(briefing.local_time(row['start_at']))
        if row['end_at']:body+=' to '+esc(briefing.local_time(row['end_at']))
        body+=' · '+esc(row['status'])+'</p>'
        start=datetime.fromisoformat(row['start_at']);now=datetime.now(timezone.utc)
        if row['status']=='confirmed' and now<=start<=now+timedelta(minutes=60):body+='<p class="badge">Starts within an hour</p>'
        if row['status']=='confirmed' and start<now and row['end_at'] and datetime.fromisoformat(row['end_at'])>now:body+='<p class="badge">In progress</p>'
        return body+'</article>'

    @app.get('/calendar')
    def home(view:str='upcoming',page:int=1):
        try:rows=store.events(view,page);agenda=store.tomorrow()
        except ValueError as exc:error(exc)
        body='<h1>Your calendar</h1>'+nav()+'<p>Confirmed local meetings, shown in Pakistan time (UTC+5). <a href="/calendar">Refresh</a> to update the agenda.</p>'
        body+='<p class="muted">Review suggestions from saved email reports to add meetings. This calendar is separate from Google and Titan calendars. Reminders appear here when you open or refresh the page; push notifications and background alerts are not included in this version.</p>'
        if view=='upcoming' and page==1:
            body+='<section class="card"><h2>Tomorrow, '+(datetime.now(store.PKT).date()+timedelta(days=1)).strftime('%d %b')+'</h2>'
            for row in agenda:body+='<p><a href="/calendar/event/'+row['id']+'">'+esc(row['title'])+'</a> · '+esc(briefing.local_time(row['start_at']))+'</p>'
            if not agenda:body+='<p>No confirmed meetings starting tomorrow.</p>'
            body+='</section>'
        for row in rows:body+=event_card(row)
        if not rows:body+='<p>No '+esc(view)+' meetings on this page.</p>'
        if page>1:body+='<a href="/calendar?view='+view+'&page='+str(page-1)+'">Previous</a> '
        if len(rows)==50:body+='<a href="/calendar?view='+view+'&page='+str(page+1)+'">Next</a>'
        return render(body)

    @app.get('/calendar/suggestions')
    def suggestions(page:int=1):
        try:rows=store.candidates(page)
        except ValueError as exc:error(exc)
        body='<h1>Review meeting suggestions</h1>'+nav()+'<section class="card"><h2>Collect from completed inbox reports</h2><p>Uses explicit meeting times already saved in report items. Up to 100 reports per click; repeat to continue through older reports. No model requests.</p><form method="post" action="/calendar/collect"><button>Collect meeting suggestions · 0 model requests</button></form></section>'
        body+='<p>Coverage is limited to completed report items with explicit, timezone-aware meeting times. Not every email is a report item. Read and report new emails in Briefing, collect here, and add missing meetings manually. Truncated excerpts and attachments can omit important details.</p><p>Times are suggestions. Check the original invitation, especially changes or cancellations. Duplicate and nearby-time hints do not establish that two meetings are the same.</p>'
        for row in rows:
            body+='<article class="card"><h2><a href="/calendar/suggestion/'+row['id']+'">'+esc(row['title'])+'</a></h2><p>'+esc(briefing.local_time(row['start_at']))+' · '+esc(mail_label(row['account_id']))+'</p>'
            if datetime.fromisoformat(row['start_at'])<datetime.now(timezone.utc):body+='<p class="badge">Past meeting: review for your record or dismiss</p>'
            body+='<p>Saved source emails: '+source_links(row)+'</p><a class="button" href="/calendar/suggestion/'+row['id']+'">Review date and details</a></article>'
        if not rows:body+='<p>No pending suggestions on this page.</p>'
        if page>1:body+='<a href="/calendar/suggestions?page='+str(page-1)+'">Previous</a> '
        if len(rows)==50:body+='<a href="/calendar/suggestions?page='+str(page+1)+'">Next</a>'
        return render(body,'Meeting suggestions')

    @app.post('/calendar/collect')
    def collect():
        result=store.collect()
        return render('<h1>Meeting collection complete</h1><p>'+str(result['reports'])+' reports checked · '+str(result['added'])+' suggestions added · '+str(result['unusable'])+' unusable entries or malformed reports skipped · '+str(result['remaining'])+' completed reports waiting.</p><p>Reports without explicit meeting times add no suggestions. No model requests were made.</p><p><a class="button" href="/calendar/suggestions">Review suggestions</a></p>','Meeting collection')

    @app.get('/calendar/suggestion/{key}')
    def review(key:str):
        row=candidate(key)
        if row['status']=='confirmed':return go('/calendar/event/'+row['event_id'])
        if row['status']!='proposed':return render('<h1>Suggestion dismissed</h1>'+nav())
        body='<h1>Review meeting</h1><p>'+esc(mail_label(row['account_id']))+' · Saved source emails: '+source_links(row)+'</p><p>Verify the date, timezone and invitation status. The end time is unknown unless you supply it. Confirmation saves a local record; it sends no invitations or calendar updates.</p>'
        nearby=store.conflicts(row['start_at']);duplicates=store.similar_candidates(key)
        if nearby or duplicates:body+='<section class="card"><h2>Possible duplicate or time conflict</h2><p>Other meetings start within 15 minutes. Check before creating a separate meeting.</p>'
        for other in nearby:
            body+='<p><a href="/calendar/event/'+other['id']+'">'+esc(other['title'])+'</a> · '+esc(briefing.local_time(other['start_at']))+'</p><form method="post" action="/calendar/suggestion/'+key+'/link"><input type="hidden" name="event_id" value="'+other['id']+'"><input type="hidden" name="version" value="'+str(other['version'])+'"><button class="secondary">Same meeting: link source to this event</button></form>'
        for other in duplicates:body+='<p>Other suggestion: <a href="/calendar/suggestion/'+other['id']+'">'+esc(other['title'])+'</a> · '+esc(briefing.local_time(other['start_at']))+'</p>'
        if nearby or duplicates:body+='<p>Linking preserves the existing title, time and notes. For a reschedule, edit that event first, then link the new source. For a cancellation, cancel the existing event and dismiss this suggestion. Nearby suggestions remain pending until you review them.</p></section>'
        body+='<section class="card">'+form('/calendar/suggestion/'+key+'/confirm',row['title'],row['start_at'],notes=row['notes'],button='Confirm as a separate local meeting')+'</section>'
        body+='<form method="post" action="/calendar/suggestion/'+key+'/dismiss"><button class="secondary">Dismiss suggestion</button></form>'
        return render(body,'Review meeting')

    @app.post('/calendar/suggestion/{key}/confirm')
    def confirm(key:str,title:str=Form(...),start_at:str=Form(...),end_at:str=Form(''),notes:str=Form('')):
        try:event_id=store.confirm(key,*parsed(title,start_at,end_at,notes))
        except ValueError as exc:error(exc)
        return go('/calendar/event/'+event_id)

    @app.post('/calendar/suggestion/{key}/link')
    def link(key:str,event_id:str=Form(...),version:int=Form(...)):
        try:store.link(key,event_id,version)
        except ValueError as exc:error(exc)
        return go('/calendar/event/'+event_id)

    @app.post('/calendar/suggestion/{key}/dismiss')
    def dismiss(key:str):
        try:store.dismiss(key)
        except ValueError as exc:error(exc)
        return go('/calendar/suggestions')

    @app.get('/calendar/new')
    def new():
        hidden='<input type="hidden" name="submission_key" value="'+uuid4().hex+'">'
        return render('<h1>Add a local meeting</h1>'+nav()+'<p>Enter the date and time in Pakistan time (UTC+5). Saving sends no invitations. Check your existing meetings before adding a duplicate.</p>'+form('/calendar/create',hidden=hidden),'Add meeting')

    @app.post('/calendar/create')
    def create(title:str=Form(...),start_at:str=Form(...),end_at:str=Form(''),notes:str=Form(''),submission_key:str=Form(...)):
        try:event_id=store.create(*parsed(title,start_at,end_at,notes),submission_key)
        except ValueError as exc:error(exc)
        return go('/calendar/event/'+event_id)

    @app.get('/calendar/event/{key}')
    def detail(key:str):
        row=event(key);hidden='<input type="hidden" name="version" value="'+str(row['version'])+'">'
        hidden+='<label>Status<select name="status"><option value="confirmed"'+(' selected' if row['status']=='confirmed' else '')+'>Confirmed</option><option value="cancelled"'+(' selected' if row['status']=='cancelled' else '')+'>Cancelled locally</option></select></label>'
        body='<h1>'+esc(row['title'])+'</h1>'+nav()+'<p>'+esc(briefing.local_time(row['start_at']))+' · '+esc(row['status'])+'</p><p><a href="/calendar/event/'+key+'/download">Download this meeting (.ics)</a></p><p>Edits and cancellations affect this local record only. Downloading an .ics file does not sync Google or Titan; import it yourself if needed. Recurring meetings are stored as individual occurrences.</p>'
        for source in store.sources(key):body+='<p>Source emails: '+source_links(source)+'</p>'
        others=store.conflicts(row['start_at'],exclude=key)
        if others:body+='<p class="badge">'+str(len(others))+' other confirmed meetings start within 15 minutes. Check your calendar for conflicts.</p>'
        body+='<p><a class="button" href="/meetings/'+key+'">Preparation, notes and minutes</a></p>'
        body+='<section class="card">'+form('/calendar/event/'+key+'/save',row['title'],row['start_at'],row['end_at'],row['notes'],hidden,'Save local changes')+'</section>'
        return render(body,row['title'])

    @app.post('/calendar/event/{key}/save')
    def save(key:str,version:int=Form(...),title:str=Form(...),start_at:str=Form(...),end_at:str=Form(''),notes:str=Form(''),status:str=Form(...)):
        try:store.update(key,version,*parsed(title,start_at,end_at,notes),status)
        except ValueError as exc:error(exc)
        return go('/calendar/event/'+key)

    @app.get('/calendar/event/{key}/download')
    def download(key:str):return Response(export.event(event(key)),media_type='text/calendar; charset=utf-8',headers={'Content-Disposition':'attachment; filename="superhuman-meeting.ics"','Cache-Control':'no-store'})


def mail_label(slot):
    value=store.mail.SLOTS.get(slot,{})
    return value['label'] if isinstance(value,dict) else value[0] if isinstance(value,(tuple,list)) and value else str(value)
