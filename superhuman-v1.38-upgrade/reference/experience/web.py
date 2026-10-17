"""Owner workspace routes. GET reads saved state; POST applies explicit choices."""
from datetime import datetime,date,timedelta,timezone
import json
from pathlib import Path
from urllib.parse import urlencode,quote
from uuid import uuid4
from fastapi import Form,HTTPException
from fastapi.responses import HTMLResponse,RedirectResponse,Response
from superhuman.navigation import shell
from superhuman.projects import engine as p
from superhuman.team import store as team
from superhuman.dialogue import store as dialogue
from . import store,calendar,inbox
E=shell.esc

def link(url,text):return '<a href="'+E(url)+'">'+E(text)+'</a>'
def render(body,title):return HTMLResponse(shell.page(body,title))
def redirect(url):return RedirectResponse(url,status_code=303)
def error(exc):raise HTTPException(409,str(exc)) from exc
def hidden(name,value):return '<input type="hidden" name="'+name+'" value="'+E(value)+'">'
def field(label,name,value='',area=False):return '<label>'+E(label)+('<textarea name="'+name+'" maxlength="6000">'+E(value)+'</textarea>' if area else '<input name="'+name+'" value="'+E(value)+'" maxlength="200" required>')+'</label>'
def stamp(v):
    if not v:return 'Never'
    try:
        dt=datetime.fromtimestamp(float(v),timezone.utc) if isinstance(v,(int,float)) else datetime.fromisoformat(v.replace('Z','+00:00'))
        if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(calendar.PKT).strftime('%d %b %Y · %I:%M %p PKT')
    except (TypeError,ValueError):return str(v)

def board(scope=None):
    from superhuman.practice.web import portrait
    body='<div class="ux-board" data-team-status>'
    for item in store.board():
        if scope and item['id']!=scope:continue
        ident=item['id'];task=item['task']
        body+='<article class="card ux-employee" data-employee="'+ident+'"><div class="row"><span class="teamspace-portrait" aria-hidden="true">'+portrait(ident)+'</span><span class="badge" data-state>'+E(item['state'])+'</span></div><h2>'+E(item['name'])+'</h2><small>'+E(item['role'])+'</small><p data-assignment>'+E(task['title'] if task else item['assignment'] or 'No active assignment')+'</p><small data-reason>'+E(item['reason'])+'</small>'
        if task:
            parent=team.project(task['project_id']);body+='<p><a data-project href="/team/projects/'+parent['id']+'">'+E(parent['title'])+'</a></p>'
        else:body+='<p><a data-project></a></p>'
        last=item['last'];body+='<small data-last-action>Last recorded action: '+E((last['action'].replace('_',' ')+' · '+stamp(last['created_at'])) if last else 'No action recorded')+'</small>'
        body+='<div class="ux-actions">'+link('/team-room?employee='+ident,'Chat')+' '+link('/team/employees/'+ident,'Controls')+(' <a data-task-link href="/team/tasks/'+task['id']+'">Open task</a>' if task else '')+'</div></article>'
    return body+'</div><p class="muted" data-refreshed>Saved execution state · refreshes every 15 seconds while this page is open. Offline means worker status cannot be verified.</p>'

def department_panel(scope,tab):
    if tab=='agent':
        from superhuman.supervision.web import panel
        return '<h2>Your department employee</h2>'+board(scope)+'<p>'+link('/team/employees/'+scope,'Manage employee & writing skill')+'</p><h2>Department supervision</h2>'+panel(scope)+'<p>'+link('/supervision/'+scope,'Manage supervision')+'</p>'
    from superhuman.supervision.web import panel
    return '<h2>Department supervision</h2>'+panel(scope)+'<p>'+link('/supervision/'+scope,'Open supervision controls')+'</p>'

def room_form(employee='twin',kind='',pid=''):
    return '<form method="post" action="/team-room/create">'+hidden('kind',kind)+hidden('project_id',pid)+'<label>Employee<select name="employee">'+''.join('<option value="'+k+'"'+(' selected' if k==employee else '')+'>'+E(v+' · '+store.ROLES[k])+'</option>' for k,v in store.NAMES.items() if not kind or k in ('twin',employee))+'</select></label>'+field('Conversation title','title','Project discussion' if pid else 'Talk with '+store.NAMES.get(employee,'the Twin'))+'<button>Start conversation</button></form>'

def project_conversations(pid,page=1,kind='canonical'):
    target=store.project(kind,pid);body='<p>Only conversations explicitly linked to this project appear here.</p>'
    for r in store.project_rooms(kind,pid)[(page-1)*50:page*50]:body+='<section class="card"><h3>'+link('/team-room/'+r['id'],r['title'])+'</h3><p>'+E(store.NAMES[r['employee']])+' · '+E(stamp(r['updated_at']))+'</p></section>'
    body+='<details><summary>Start a project conversation</summary>'+room_form(target['scope'],kind,pid)+'</details>'
    unlinked=store.read('dialogue_threads','SELECT d.id,d.title FROM dialogue_threads d LEFT JOIN ux_rooms r ON r.thread_id=d.id WHERE d.scope=? AND r.thread_id IS NULL ORDER BY d.updated_at DESC LIMIT 200',(target['scope'],)) if store.read('ux_migrations','SELECT id FROM ux_migrations') else []
    if unlinked:
        body+='<details><summary>Link an existing department conversation</summary><p>Choose only a conversation that belongs entirely to this project. Prior messages will remain visible in it. Inbox reports cannot be linked.</p><form method="post" action="/team-room/link">'+hidden('kind',kind)+hidden('project_id',pid)+'<label>Conversation<select name="thread_id">'+''.join('<option value="'+r['id']+'">'+E(r['title'])+'</option>' for r in unlinked)+'</select></label><button>Link conversation</button></form></details>'
    return body

def team_home(employee='twin',tab='room',page=1):
    if employee not in store.NAMES:raise HTTPException(404,'Employee not found')
    if tab not in ('room','board','feed'):raise HTTPException(404,'Team page not found')
    body='<div class="ux-head"><div><p class="eyebrow">Mahnoor & her team</p><h1>Team</h1><p>Talk, coordinate and see the work that is actually recorded.</p></div><div class="ux-actions">'+link('/team','Team controls')+' '+link('/team/twin','Owner updates')+' '+link('/team/budget','Budget')+'</div></div><nav class="ux-tabs">'+link('/team-room','Team Room')+link('/team-room?tab=board','Employee board')+link('/team-room?tab=feed','Team activity')+'</nav>'
    if tab=='board':return render(body+board(),'Employee board')
    if tab=='feed':
        body+='<p>Recorded handoffs, questions, disagreements and decisions. This shows saved work messages and audit events.</p><div class="ux-feed">'
        requests=store.read('team_requests','SELECT r.*,t.title,t.owner,t.project_id FROM team_requests r JOIN team_tasks t ON t.id=r.task_id ORDER BY r.created_at DESC LIMIT 100')
        for r in requests:body+='<article class="card"><span class="badge">'+E(r['kind']+' · '+r['status'])+'</span><h3>'+link('/team/requests/'+r['id'],store.NAMES.get(r['owner'],r['owner'])+' → '+store.NAMES.get(r['recipient'],r['recipient'] or 'Twin'))+'</h3><p>'+E(r['title'])+'</p><div class="ux-body">'+E(r['payload'])+'</div>'+('<p>Decision / response: '+E(r['response'])+'</p>' if r['response'] else '')+'<small>'+E(stamp(r['created_at']))+'</small></article>'
        if not requests:body+='<p>No employee handoffs or questions recorded yet.</p>'
        body+='</div><details><summary>Recent system activity</summary>'
        for r in store.read('team_events','SELECT * FROM team_events ORDER BY seq DESC LIMIT 100'):body+='<p>'+E(store.NAMES.get(r['actor'],r['actor']))+' · '+E(r['action'].replace('_',' '))+' · '+E(stamp(r['created_at']))+'</p>'
        return render(body+'</details>','Team activity')
    body+='<div class="shell-grid"><section class="card"><h2>Talk with your team</h2><p>Chat with the Twin or a specialist. Project rooms keep the conversation tied to one project. Sending messages does not approve tasks or save standing instructions.</p>'+room_form(employee)+'</section><section class="card"><h2>Recent conversations</h2>'
    for r in store.rooms()[:30]:body+='<p>'+link('/team-room/'+r['id'],r['title'])+'<br><small>'+E(store.NAMES[r['employee']])+(' · Project room' if r['project_id'] else ' · Employee chat')+'</small></p>'
    body+='</section></div><p>'+link('/talk','Earlier department conversations')+' · '+link('/assistant','Personal assistant & communications')+'</p>'
    return render(body,'Team Room')

def show_room(ident):
    r=store.room(ident)
    if not r:raise HTTPException(404,'Room not found')
    thread=dialogue.get(ident);name=store.NAMES[r['employee']]
    body='<div class="ux-chat"><p>'+link('/team-room','Team Room')+' / '+E(name)+'</p><h1>'+E(thread['title'])+'</h1>'
    if r['project_id']:
        target=store.project(r['project_kind'],r['project_id']);url='/team/projects/' if r['project_kind']=='team' else '/work/'
        body+='<p class="badge">Project: '+link(url+r['project_id'],target['title'])+'</p>'
    body+='<p class="muted">'+E(name+' · '+store.ROLES[r['employee']])+' · '+str(thread['used_calls'])+' / '+str(thread['max_calls'])+' requests used. Replies use your configured model and budget.</p>'
    for t in dialogue.turns(ident):
        body+='<article class="card owner"><small>You · '+E(stamp(t['created_at']))+'</small><div class="ux-body">'+E(t['user_text'])+'</div></article>'
        body+='<article class="card reply"><small>'+E(name)+' · '+E(t['status'].replace('_',' '))+'</small><div class="ux-body">'+E(t['reply'] or t['error'] or 'Waiting for the supervised worker…')+'</div>'
        if t['status']=='done':body+='<p>'+link('/talk/'+ident+'/turn/'+t['id']+'/remember','Review an update for memory')+'</p>'
        body+='</article>'
    for s in dialogue.suggestions(ident):
        body+='<details class="card"><summary>Proposed work: '+E(s['title'])+' · '+E(s['status'])+'</summary><p>'+E(s['rationale'])+'</p>'
        saved=store.read('ux_suggestion_tasks','SELECT task_id FROM ux_suggestion_tasks WHERE suggestion_id=?',(s['id'],))
        if saved:body+='<p>'+link('/team/tasks/'+saved[0]['task_id'],'Open governed task')+'</p>'
        elif s['status']=='proposed':
            choices=[a for a in team.projects() if a['status']=='active' and (r['employee']=='twin' or a['scope']==r['employee']) and (not r['project_id'] or r['project_kind']=='team' and a['id']==r['project_id'])]
            if choices:
                body+='<p>Creates a restricted, consequential task for review. Existing budget, Twin and owner execution controls still apply.</p><form method="post" action="/team-room/'+ident+'/approve">'+hidden('suggestion_id',s['id'])+hidden('expected_hash',s['proposal_hash'])+field('Title','title',s['title'])+field('Instructions','instruction',s['details'],True)+'<label>Governed project<select name="project_id">'+''.join('<option value="'+a['id']+'">'+E(a['title'])+'</option>' for a in choices)+'</select></label><button>Create governed task</button></form>'
            else:body+='<p>'+link('/team','Create or adopt a governed project before approving work')+'</p>'
        body+='</details>'
    body+='<form class="ux-composer" data-voice method="post" action="/team-room/'+ident+'/send">'+hidden('submission_key',uuid4().hex)+'<label>Message '+E(name)+'<textarea name="message" maxlength="6000" required placeholder="Share context, ask a question, or discuss this project…"></textarea></label><button>Send message</button><p class="muted">Review speech text before sending. Task execution and standing owner instructions require separate controls.</p></form></div>'
    return render(body,thread['title'])

def inbox_home(account='all',state='all',selected='',q='',page=1):
    if state not in ('all','unreviewed','reviewed','follow_up') or not 1<=page<=10000 or len(q)>200:raise HTTPException(400,'Invalid inbox filter')
    accounts=inbox.accounts();values=inbox.messages();lookup={m['id']:m for m in values}
    items=[m for m in values if (account=='all' or m['account']==account) and (state=='all' or m['review_state']==state) and (not q or q.casefold() in (m['sender']+' '+m['subject']+' '+m['body']).casefold())]
    subset=items[(page-1)*30:page*30];chosen=lookup.get(selected) if selected else (subset[0] if subset else None)
    query=lambda **kw:'/inboxes?'+urlencode(dict(account=account,state=state,q=q,page=page,**kw))
    body='<div class="ux-head"><div><p class="eyebrow">Your communications</p><h1>Inbox</h1><p>Read, review and decide what needs attention.</p></div><div class="ux-actions">'+link('/assistant','Twin assistant')+link('/assistant/connections','Connections')+link('/inboxes/setup','Setup guide')+'</div></div><form method="get" action="/inboxes">'+hidden('account',account)+'<div class="row"><label>Search saved previews<input name="q" value="'+E(q)+'" maxlength="200"></label><label>Review state<select name="state">'+''.join('<option value="'+s+'"'+(' selected' if state==s else '')+'>'+s.replace('_',' ').capitalize()+'</option>' for s in ('all','unreviewed','follow_up','reviewed'))+'</select></label><button class="secondary">Filter</button></div></form><div class="ux-inbox"><aside class="card ux-accounts"><h3>Accounts</h3>'+link('/inboxes','All accounts')
    for a in accounts:
        body+='<a href="/inboxes?'+urlencode({'account':a['key'],'state':state})+'"'+(' aria-current="page"' if account==a['key'] else '')+'><strong>'+E(a['label'])+'</strong><br><small>'+E(a['kind'])+' · '+('Connected' if a['connected'] else 'Disconnected')+'<br>Reading '+('on' if a['enabled'] else 'off')+' · AI '+('on' if a['ai_enabled'] else 'off')+'<br>Last actual check: '+E(stamp(a['last_sync']))+('</small><p class="error">Check connection settings</p>' if a['last_error'] else '</small>')+'</a>'
    if not accounts:body+='<p>No connections yet.</p>'
    body+='</aside><section class="card ux-messages"><h3>Messages · '+str(len(items))+'</h3>'
    for m in subset:
        body+='<a href="'+E(query(selected=m['id']))+'"'+(' aria-current="page"' if chosen and chosen['id']==m['id'] else '')+'><small>'+E(m['sender'][:100])+'</small><h3>'+E(m['subject'] or '(No subject)')+'</h3><small>'+E(stamp(m['received']))+' · '+E(m['review_state'].replace('_',' '))+'</small><small>'+E(__import__('superhuman.trust',fromlist=['preview']).preview(m['body'])[:100])+'</small></a>'
    if not subset:body+='<p>No messages match these filters.</p>'
    if page>1:body+=link('/inboxes?'+urlencode(dict(account=account,state=state,q=q,page=page-1)),'Previous')
    if len(items)>page*30:body+=link('/inboxes?'+urlencode(dict(account=account,state=state,q=q,page=page+1)),'Next')
    body+='</section><section class="card ux-selected">'
    if chosen:
        m=chosen;body+='<span class="eyebrow">Saved message preview</span><h2>'+E(m['subject'] or '(No subject)')+'</h2><p>'+E(m['sender'])+'<br><small>'+E(stamp(m['received']))+'</small></p>'
        if m['notice']:body+='<p class="error">'+E(m['notice'])+'</p>'
        body+='<div class="ux-preview">'+E(__import__('superhuman.trust',fromlist=['preview']).preview(m['body']))+'</div><form method="post" action="/inbox-actions/review">'+hidden('return_to',query(selected=m['id']))+hidden('ident',m['id'])+'<label>My review state<select name="state">'+''.join('<option value="'+s+'"'+(' selected' if s==m['review_state'] else '')+'>'+s.replace('_',' ')+'</option>' for s in ('unreviewed','follow_up','reviewed'))+'</select></label><button class="secondary">Save review state</button></form><p><small>Local review state only. Does not mark the original message as read.</small></p><h3>Twin assessment</h3>'
        assessment=inbox.assessment(m['id'])
        if assessment:body+='<p>'+E(assessment['headline'])+'</p><p>'+E(assessment['reason'])+'</p><small>'+('Source changed; reanalyse before relying on this assessment.' if assessment['stale'] else 'Saved '+E(stamp(assessment['created_at'])))+'</small>'
        else:body+='<p class="muted">No saved assessment for this message. Enable AI consent for the chosen channel and request analysis in the assistant.</p>'
        from superhuman.comms import store as comms
        for d in comms.drafts():
            if 'c:'+d['source_id']==m['id']:
                body+='<h3>Reply draft · '+E(d['state'])+'</h3>'+('<p class="error">Source preview changed since this draft was prepared. Review before using.</p>' if d['source_digest']!=m.get('digest') else '')+'<div class="ux-body">'+E(d['body'])+'</div><p>'+link('/assistant/drafts/'+d['id'],'Review or edit draft')+'</p>'
        from superhuman.workspace.web import inbox_actions
        body+=inbox_actions(m,query(selected=m['id']))
        body+='<p>'+link(m['url'],'Open original workspace')+'</p><p class="muted">Reply drafts are local. Nothing is sent from this screen.</p>'
    else:body+='<h2>Select a message</h2><p>Your message, Twin assessment and reply draft will appear here.</p>'
    return render(body+'</section></div><p class="muted">Credential-labelled values are masked in this view on a best-effort basis; original records are retained. Saved previews only. Opening Inbox does not fetch messages, enable reading, or grant AI consent. Latest 5,000 previews are searchable.</p>','Inbox')

def calendar_home(view='month',day='',page=1):
    try:current=date.fromisoformat(day) if day else datetime.now(calendar.PKT).date();low,high=calendar.span(view,current)
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc
    all_events=calendar.events(view,current);events=all_events[:1000]
    def url(v=view,d=current):return '/calendar?'+urlencode({'view':v,'day':d.isoformat()})
    if view=='month':
        prev=(current.replace(day=1)-timedelta(days=1)).replace(day=1);nxt=(current.replace(day=28)+timedelta(days=4)).replace(day=1)
    else:prev=current-timedelta(days=1 if view=='day' else 7 if view=='week' else 31);nxt=current+timedelta(days=1 if view=='day' else 7 if view=='week' else 31)
    body='<div class="ux-head"><div><p class="eyebrow">Asia/Karachi · UTC+05:00</p><h1>'+current.strftime('%B %Y')+'</h1></div><div class="ux-actions">'+link('/calendar/new','+ New meeting')+link('/calendar-intake','Invitation intake')+link('/calendar/suggestions','Earlier suggestions')+link('/meetings','Meeting workspace')+'</div></div><nav>'+link(url(d=prev),'← Previous')+link('/calendar?view='+view,'Today')+link(url(v='day',d=datetime.now(calendar.PKT).date()+timedelta(days=1)),'Tomorrow')+link(url(d=nxt),'Next →')+'</nav><nav class="ux-tabs">'+''.join('<a href="'+E(url(v=v))+'"'+(' aria-current="page"' if v==view else '')+'>'+v.capitalize()+'</a>' for v in ('month','week','day','agenda'))+'</nav><p class="muted">All displayed times are Pakistan Standard Time (PKT). Open a meeting for details and original invitation information.</p>'
    from superhuman.workspace.web import calendar_tools,deadline_chips
    body+=calendar_tools(view,current)
    if len(all_events)>1000:body+='<p class="error">Showing the first 1,000 events in this range. Choose a smaller range to see more.</p>'
    if view=='month':
        body+='<div class="ux-calendar ux-month">'+''.join('<div class="ux-weekday">'+s+'</div>' for s in ('MON','TUE','WED','THU','FRI','SAT','SUN'))
        for n in range(42):
            d=low+timedelta(days=n);values=[ev for ev in events if calendar.on_day(ev,d)];body+='<section class="ux-day'+(' today' if d==datetime.now(calendar.PKT).date() else '')+'"><strong>'+link(url(v='day',d=d),str(d.day)+(' '+d.strftime('%b') if d.month!=current.month else ''))+'</strong>'
            for ev in values[:4]:body+='<a class="ux-event" href="/calendar/event/'+ev['id']+'">'+E(calendar.local(ev['start_at']).strftime('%H:%M')+' '+ev['title'])+'</a>'
            if len(values)>4:body+=link(url(v='day',d=d),'+'+str(len(values)-4)+' more')
            body+=deadline_chips(d)
            body+='</section>'
        body+='</div>'
    elif view in ('week','day'):
        count=(high-low).days;body+='<div class="ux-calendar"><div class="ux-timegrid" style="--days:'+str(count)+'"><div class="ux-weekday">PKT</div>'+''.join('<div class="ux-weekday">'+(low+timedelta(days=n)).strftime('%a %d %b')+'</div>' for n in range(count))+'<div class="ux-hours">'+''.join('<span style="--hour:'+str(h)+'">'+str(h).zfill(2)+':00</span>' for h in range(24))+'</div>'
        for n in range(count):
            d=low+timedelta(days=n);body+='<div class="ux-timeday">'
            for item in calendar.lanes(events,d):
                ev=item['event'];body+='<a class="ux-event" href="/calendar/event/'+ev['id']+'" style="--top:'+str(item['top'])+';--height:'+str(item['height'])+';--lane:'+str(item['lane'])+';--lanes:'+str(item['lanes'])+'">'+E(calendar.local(ev['start_at']).strftime('%H:%M')+' '+ev['title'])+('<br>End time unknown' if not ev['end_at'] else '')+'</a>'
            body+='</div>'
        body+='</div></div>'
    else:
        for ev in events:body+='<section class="card"><strong>'+E(stamp(ev['start_at']))+'</strong><h3>'+link('/calendar/event/'+ev['id'],ev['title'])+'</h3><p>'+('Until '+E(stamp(ev['end_at'])) if ev['end_at'] else 'End time not supplied')+'</p></section>'
    if view=='day':body+='<p>'+link('/calendar/new?day='+current.isoformat(),'Add meeting on this date')+'</p>'
    if not events:body+='<p class="muted">No confirmed meetings in this range. Review invitation intake or add a meeting.</p>'
    from superhuman.repairs.deadlines import panel
    body+='<details><summary>Department deadlines & reminders</summary>'+panel()+'</details><p class="muted">This is a local calendar. Email and channel sync does not synchronize Google or Titan calendars. In-app reminders update when you open this page; push notifications are not included.</p>'
    return render(body,'Calendar · PKT')

def intake():
    body='<h1>Meeting invitation intake</h1><p>Find explicit meeting dates in saved email, Slack and WhatsApp previews, or paste invitation / iCalendar text. Review the original timezone before confirming. Ambiguous dates and recurring occurrences require manual review. Attachments are not fetched.</p><form method="post" action="/calendar-intake/collect"><button>Scan saved previews</button></form><details><summary>Paste invitation or .ics text</summary><form method="post" action="/calendar-intake/paste">'+field('Invitation text','content','',True)+'<button>Extract dates for review</button></form></details>'
    for m in store.read('ux_meetings',"SELECT * FROM ux_meetings WHERE status='proposed' ORDER BY created_at DESC LIMIT 100"):
        body+='<section class="card" id="meeting-'+m['id']+'"><h2>'+E(m['title'])+'</h2>'+('<p>'+link('/inboxes?'+urlencode({'selected':m['source_id']}),'Review saved invitation source')+'</p>' if m['source_id'] else '')+'<p>Original: '+E(m['original']+' '+m['zone'])+'</p><p>'+(('PKT: '+E(stamp(m['start_at']))) if m['start_at'] else 'Timezone / date needs confirmation')+'</p><form method="post" action="/meeting-preview/'+m['id']+'">'+field('Title','title',m['title'])+field('Original date & time (YYYY-MM-DD HH:MM)','original',m['original'])+field('Original IANA timezone (optional if time has UTC offset)','zone',m['zone']).replace(' required','')+'<label>Optional end date & time<input name="end" value="'+E(m['end_at'])+'"></label><label>Repeated DST hour<select name="fold"><option value="">Require confirmation if repeated</option><option value="0">First occurrence</option><option value="1">Second occurrence</option></select></label><button>Preview PKT time and conflicts</button></form><form method="post" action="/calendar-intake/'+m['id']+'/dismiss"><button class="secondary">Dismiss suggestion</button></form></section>'
    return render(body,'Meeting intake')

def install(app):
    # Replace only exact GET screens. Existing POST operations and detail URLs remain registered.
    old_calendar=next((r.endpoint for r in app.routes if getattr(r,'path','')=='/calendar' and 'GET' in getattr(r,'methods',())),None)
    app.router.routes[:]=[r for r in app.router.routes if not (getattr(r,'path','') in ('/inboxes','/calendar') and 'GET' in getattr(r,'methods',()))]
    @app.get('/assets/workspace.css')
    def css():return Response((Path(__file__).parent/'assets/workspace.css').read_text(),media_type='text/css')
    @app.get('/assets/workspace.js')
    def js():return Response((Path(__file__).parent/'assets/workspace.js').read_text(),media_type='application/javascript')
    @app.get('/team-room')
    def home(employee:str='twin',tab:str='room',page:int=1):return team_home(employee,tab,page)
    @app.get('/team-room/status')
    def status():return store.board()
    @app.post('/team-room/create')
    def create(employee:str=Form(...),title:str=Form(...),kind:str=Form(''),project_id:str=Form('')):
        try:return redirect('/team-room/'+store.create(employee,title,kind,project_id))
        except ValueError as exc:error(exc)
    @app.post('/team-room/link')
    def attach(thread_id:str=Form(...),kind:str=Form(...),project_id:str=Form(...)):
        try:store.link(thread_id,kind,project_id);return redirect('/team-room/'+thread_id)
        except ValueError as exc:error(exc)
    @app.get('/team-room/{ident}')
    def chat(ident:str):return show_room(ident)
    @app.post('/team-room/{ident}/send')
    def send(ident:str,message:str=Form(...),submission_key:str=Form(...)):
        if not store.room(ident):raise HTTPException(404,'Room not found')
        try:
            employee=next((e for e in team.employees() if e['id']==store.room(ident)['employee']),{})
            if employee.get('paused'):raise ValueError('Employee is paused; resume in employee controls before requesting a reply')
            dialogue.send(ident,message,submission_key);return redirect('/team-room/'+ident)
        except ValueError as exc:error(exc)
    @app.post('/team-room/{ident}/approve')
    def approve(ident:str,suggestion_id:str=Form(...),expected_hash:str=Form(...),project_id:str=Form(...),title:str=Form(...),instruction:str=Form(...)):
        suggestions=dialogue.suggestions(ident)
        if not any(s['id']==suggestion_id for s in suggestions):raise HTTPException(404,'Suggestion not found in room')
        try:tid=store.approve(suggestion_id,expected_hash,project_id,title,instruction);return redirect('/team/tasks/'+tid)
        except ValueError as exc:error(exc)
    @app.get('/inboxes')
    def inbox_screen(account:str='all',state:str='all',selected:str='',q:str='',page:int=1):return inbox_home(account,state,selected,q,page)
    @app.post('/inbox-review')
    def review(ident:str=Form(...),state:str=Form(...)):
        try:inbox.mark(ident,state);return redirect('/inboxes?'+urlencode({'selected':ident}))
        except ValueError as exc:error(exc)
    @app.get('/calendar')
    def calendar_screen(view:str='month',day:str='',page:int=1):
        if view in ('upcoming','past','cancelled') and old_calendar:return old_calendar(view=view,page=page)
        return calendar_home(view,day,page)
    @app.get('/calendar-intake')
    def calendar_intake():return intake()
    @app.post('/calendar-intake/collect')
    def collect():calendar.collect();return redirect('/calendar-intake')
    @app.post('/calendar-intake/paste')
    def paste(content:str=Form(...)):
        if len(content)>20000:raise HTTPException(400,'Invitation text exceeds 20,000 characters')
        store.initialize();found=calendar.extract_named(content)
        if not found:raise HTTPException(409,'No explicit ISO date or supported DTSTART found. Add a meeting manually with a confirmed timezone.')
        import hashlib
        with p.connect(p.DEFAULT_DB) as db:
            for original,zone,start,end,title in found:
                ident=hashlib.sha256((content+original+zone+title).encode()).hexdigest()[:32]
                db.execute('INSERT OR IGNORE INTO ux_meetings(id,source_id,source_digest,title,original,zone,start_at,end_at,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(ident,'',hashlib.sha256(content.encode()).hexdigest(),title,original,zone,start,end,p.stamp()))
        return redirect('/calendar-intake')
    @app.post('/calendar-intake/{ident}/confirm')
    def confirm(ident:str,title:str=Form(...),original:str=Form(...),zone:str=Form(''),end:str=Form(''),fold:str=Form('')):
        try:return redirect('/calendar/event/'+calendar.confirm(ident,title,original,zone,end,fold))
        except ValueError as exc:error(exc)
    @app.post('/calendar-intake/{ident}/dismiss')
    def dismiss(ident:str):
        store.initialize()
        with p.connect(p.DEFAULT_DB) as db:db.execute("UPDATE ux_meetings SET status='dismissed' WHERE id=? AND status='proposed'",(ident,))
        return redirect('/calendar-intake')
    @app.get('/project-tasks')
    def task_list(page:int=1):
        if not 1<=page<=10000:raise HTTPException(400,'Invalid page')
        body='<h1>All tasks</h1><p>Tasks across your projects. Open a task to inspect its assignment, approvals and output.</p>'
        rows=team.tasks();legacy=store.read('project_tasks','SELECT t.*,p.objective FROM project_tasks t JOIN projects p ON p.id=t.project_id ORDER BY t.rowid DESC')
        for t in rows[(page-1)*50:page*50]:body+='<section class="card"><span class="badge">'+E(t['state'])+'</span><h3>'+link('/team/tasks/'+t['id'],t['title'])+'</h3><p>'+E(store.NAMES.get(t['owner'],t['owner']))+' · '+link('/team/projects/'+t['project_id'],team.project(t['project_id'])['title'])+'</p></section>'
        body+='<details><summary>Existing execution tasks ('+str(len(legacy))+')</summary>'
        for t in legacy[(page-1)*50:page*50]:body+='<p>'+link('/projects/'+t['project_id'],t['title'])+' · '+E(t['status'])+' · '+E(t['objective'])+'</p>'
        body+='</details>'
        if not rows and not legacy:body+='<p>No tasks recorded.</p>'
        if page>1:body+=link('/project-tasks?page='+str(page-1),'Previous')
        if max(len(rows),len(legacy))>page*50:body+=link('/project-tasks?page='+str(page+1),'Next')
        return render(body,'All tasks')
    @app.get('/suggested-work')
    def suggested():
        body='<h1>Suggested work</h1><p>Review suggestions in their original conversation or source. Approval creates work under the appropriate project controls.</p>'
        from superhuman.comms import store as comms
        values=store.read('dialogue_suggestions',"SELECT * FROM dialogue_suggestions WHERE status='proposed' ORDER BY created_at DESC LIMIT 200")
        for s in values:body+='<section class="card"><h3>'+E(s['title'])+'</h3><p>'+E(s['rationale'])+'</p>'+link(('/team-room/' if store.room(s['thread_id']) else '/talk/')+s['thread_id'],'Review conversation suggestion')+'</section>'
        proposals=[s for s in comms.proposals() if s['state']=='proposed']
        for s in proposals:body+='<section class="card"><h3>'+E(s['title'])+'</h3><p>'+E(store.NAMES.get(s['department'],s['department']))+'</p>'+link('/assistant/proposals/'+s['id'],'Review inbox suggestion')+'</section>'
        if not values and not proposals:body+='<p>No proposed work waiting for review.</p>'
        return render(body,'Suggested work')
    @app.get('/project-rooms/{ident}')
    def project_room_list(ident:str):
        try:target=team.project(ident);return render('<h1>'+E(target['title'])+'</h1>'+project_conversations(ident,kind='team'),'Project conversations')
        except ValueError as exc:raise HTTPException(404,str(exc)) from exc
