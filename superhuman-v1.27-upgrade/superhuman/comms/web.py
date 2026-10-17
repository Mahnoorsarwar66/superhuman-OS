"""Private Twin inbox, source-grounded briefs, local drafts and explicit sharing."""
import json,time
from uuid import uuid4
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import Form,HTTPException
from fastapi.responses import HTMLResponse,RedirectResponse
from superhuman.navigation import shell
from superhuman.team import store as team,budget
from superhuman.team.web import input,options
from . import store,engine,providers
E=shell.esc

def link(path,label):return '<a href="'+E(path)+'">'+E(label)+'</a>'
def redirect(path='/assistant'):return RedirectResponse(path,status_code=303)
def error(exc):raise HTTPException(409,str(exc)) from exc
def page(body,title='Mahnoor Twin assistant'):return HTMLResponse(shell.page(body,title))
def source_link(ident,label='Source preview'):return link('/assistant/sources/'+ident,label)
def check(name,label,checked=False):return '<label><input type="checkbox" name="'+name+'" value="true"'+(' checked' if checked else '')+'>'+E(label)+'</label>'
def local(value):
    if not value:return 'Not yet read'
    try:return datetime.fromisoformat(value).astimezone(ZoneInfo(store.settings()['timezone'])).strftime('%d %b %Y %H:%M %Z')
    except (ValueError,TypeError):return str(value)
def twin_panel():
    cfg=store.settings();recent=next((r for r in store.runs() if r['status']=='done'),None)
    return '<section class="card"><h2>'+link('/assistant','Your communications & personal assistant')+'</h2><p>'+('Enabled' if cfg['enabled'] else 'Off until configured')+' · '+str(sum(a['state']=='new' for a in store.alerts()))+' proposed urgent items</p>'+('<p>'+E(json.loads(recent['result'])['summary'])+'</p>'+link('/assistant/runs/'+recent['id'],'Read the latest Twin brief') if recent else '<p>Connect selected channels and enable processing to start.</p>')+'</section>'
def attention():return [{'title':a['headline'],'reason':'Twin proposed urgent item: '+a['reason'],'url':'/assistant/sources/'+a['source_id']} for a in store.alerts() if a['state']=='new']+[{'title':'Twin assistant analysis','reason':r['error'],'url':'/assistant/runs/'+r['id']} for r in store.runs() if r['status'] in ('interrupted','blocked')]

def install(app):
    @app.get('/assistant')
    def home():
        cfg=store.settings();body='<h1>Mahnoor Twin — personal assistant</h1><p>Your private view across selected email, Slack and WhatsApp Business sources. The Twin prepares briefings, reply drafts and proposed specialist work. Messages stay in their original channels; this app does not send them.</p><p>'+link('/team/twin','Update the Twin')+' · '+link('/assistant/connections','Connections & consent')+' · '+link('/assistant/settings','Briefing schedule')+' · '+link('/team/budget','Dollar budget')+'</p>'
        if not cfg['version']:body+='<form method="post" action="/assistant/setup"><button>Initialize assistant records without enabling work</button></form>'
        else:body+='<p>'+('Enabled' if cfg['enabled'] else 'Paused')+' · '+E(cfg['timezone'])+' · '+E(' / '.join(cfg[s] for s in store.SLOTS))+' · Model attempts ceiling '+str(cfg['daily_limit'])+'/day, with three reserved for scheduled briefs.</p><form method="post" action="/assistant/brief"><input type="hidden" name="submission" value="'+uuid4().hex+'"><button>Request a fresh private briefing</button></form>'
        if not team.enabled():body+='<p class="error">The internal team is off. Enable it before paid assistant analysis.</p>'
        if team.settings()['hold']:body+='<p class="error">Twin needs inspection: '+E(team.settings()['hold'])+'</p>'
        body+='<h2>Needs your attention</h2>'
        for a in store.alerts():
            if a['state']=='new':body+='<section class="card"><h3>'+E(a['headline'])+'</h3><p>'+E(a['reason'])+'</p>'+source_link(a['source_id'])+'<form method="post" action="/assistant/alerts/'+a['id']+'"><button>Acknowledge</button></form></section>'
        body+='<h2>Briefings & intake</h2>'
        for r in store.runs()[:20]:
            summary=json.loads(r['result'])['summary'] if r['result'] else r['error']
            body+='<section class="card"><h3>'+link('/assistant/runs/'+r['id'],r['kind'].capitalize()+' · '+r['status'])+'</h3><p>'+E(local(r['created_at']))+'</p><p>'+E(summary)+'</p></section>'
        body+='<h2>Reply drafts</h2>'
        for d in store.drafts()[:20]:body+='<p>'+link('/assistant/drafts/'+d['id'],'Review local reply draft')+' · '+E(d['state'])+' · '+source_link(d['source_id'])+'</p>'
        body+='<h2>Specialist proposals</h2>'
        for pr in store.proposals()[:20]:body+='<p>'+link('/assistant/proposals/'+pr['id'],pr['title'])+' · '+E(pr['department']+' / '+pr['state'])+'</p>'
        body+='<h2>Recent source previews</h2>'
        for s in store.sources(limit=40):body+='<p>'+source_link(s['id'],s['subject'] or '(No subject)')+' · '+E(s['sender'])+(' · archived' if s['archived'] else '')+'</p>'
        body+='<p>Coverage is bounded. Slack follows selected conversations and recent discovered threads, email uses saved previews, and WhatsApp receives subscribed business-number webhooks. Reading and model processing have separate controls. Alerts are in-app proposals and require verification; delivery outside Superhuman is not configured.</p>'
        return page(body)

    @app.post('/assistant/setup')
    def setup():store.initialize();return redirect('/assistant/settings')
    @app.get('/assistant/settings')
    def settings():
        c=store.settings();body='<h1>Twin briefing schedule</h1><p>Morning, midday and evening briefs are saved here in Superhuman while the worker runs. After downtime only the latest elapsed slot is caught up. No past-day batch or automatic external notification is sent.</p>'
        if not c['version']:body+='<p>Initialize the assistant on its main page first.</p>'
        else:body+='<form method="post" action="/assistant/settings"><input type="hidden" name="version" value="'+str(c['version'])+'">'+check('enabled','Enable paid Twin assistant analysis',bool(c['enabled']))+input('IANA timezone','timezone',c['timezone'])+''.join(input(s.capitalize()+' HH:MM',s,c[s]) for s in store.SLOTS)+input('Daily model attempts, including failures (3–24)','daily_limit',c['daily_limit'])+'<p>Uses the confirmed Team model and Twin dollar pool. Source text from opted-in channels is sent to that model. Intake is bounded to 12 previews per batch, about every ten minutes, subject to the daily ceiling, worker availability and dollar budget. Three attempts are reserved for scheduled briefings. Common secrets are masked where recognised; this is not universal redaction.</p><button>Save assistant settings</button></form>'
        return page(body)
    @app.post('/assistant/settings')
    def settings_save(version:int=Form(...),enabled:bool=Form(False),timezone:str=Form(...),morning:str=Form(...),midday:str=Form(...),evening:str=Form(...),daily_limit:int=Form(12)):
        try:store.configure(version,enabled,timezone,morning,midday,evening,daily_limit)
        except ValueError as exc:error(exc)
        return redirect('/assistant/settings')
    @app.post('/assistant/brief')
    def brief(submission:str=Form(...)):
        if not __import__('re').fullmatch(r'[a-f0-9]{32}',submission):raise HTTPException(400,'Reload the briefing form')
        try:ident=engine.enqueue('briefing','manual:'+submission)
        except ValueError as exc:error(exc)
        return redirect('/assistant/runs/'+ident)

    @app.get('/assistant/connections')
    def connections():
        body='<h1>Connections & consent</h1><p>Passwords and tokens are entered privately with the server setup CLI in CONNECTION_GUIDE.md. The app never requests send scopes. Each connection starts paused with model processing off.</p><p>WhatsApp Business receives new text webhooks for its configured business number; it does not read a personal WhatsApp account or history. Slack IDs below are exact conversations, not resolved people.</p>'
        from superhuman.mail import store as mail
        body+='<details><summary>Link an already-connected email inbox</summary><form method="post" action="/assistant/email">'+options('slot',list(mail.SLOTS),'personal_gmail')+'<button>Link saved email connection</button></form><p>Use Inboxes to connect and enable remote email reading. Linking grants neither reading nor model consent here until you enable the controls below.</p></details>'
        for a in store.channels():
            body+='<section class="card"><h2>'+E(a['label'])+'</h2><p>'+E(a['kind']+' · '+a['identity'])+' · '+('Connected' if a['connected'] else 'Disconnected')+'</p><p>Last successful read: '+E(local(a['last_sync']))+'</p>'
            if a['last_error']:body+='<p class="error">'+E(a['last_error'])+'</p>'
            body+='<form method="post" action="/assistant/channels/'+a['id']+'"><input type="hidden" name="version" value="'+str(a['version'])+'">'+check('enabled','Enable selected-channel reading',bool(a['enabled']))+check('ai_enabled','Allow these private previews to be analysed by the Twin model',bool(a['ai_enabled']))+'<button>Save permissions</button> <button name="disconnect" value="true">Disconnect and remove this connector credential</button></form>'
            if a['kind']=='email':body+='<p>'+link('/inboxes/'+a['remote_id'],'Original email inbox & reading controls')+'</p><p>Disconnect here does not revoke the separate existing email connection.</p>'
            if a['kind']=='slack':
                body+='<form method="post" action="/assistant/channels/'+a['id']+'/streams">'+input('Slack channel/DM ID','remote_id')+input('Your display label','label')+'<button>Allow this conversation</button></form>'
                for stream in store.streams(a['id']):
                    if not stream['root']:body+='<form method="post" action="/assistant/streams/'+stream['id']+'"><input type="hidden" name="version" value="'+str(stream['version'])+'">'+check('enabled',stream['label']+' · '+stream['remote_id'],bool(stream['enabled']))+'<button>Save conversation permission</button></form>'
            if a['kind']=='whatsapp':body+='<p>Webhook endpoint: /hooks/whatsapp. Enable reading before Meta verifies this endpoint. Verify receipt with a real signed test message after installation.</p>'
            body+='</section>'
        return page(body)
    @app.post('/assistant/email')
    def email(slot:str=Form(...)):
        try:store.link_email(slot)
        except ValueError as exc:error(exc)
        return redirect('/assistant/connections')
    @app.post('/assistant/channels/{ident}')
    def channel_save(ident:str,version:int=Form(...),enabled:bool=Form(False),ai_enabled:bool=Form(False),disconnect:bool=Form(False)):
        try:store.control_channel(ident,version,enabled,ai_enabled,disconnect)
        except ValueError as exc:error(exc)
        return redirect('/assistant/connections')
    @app.post('/assistant/channels/{ident}/streams')
    def add_stream(ident:str,remote_id:str=Form(...),label:str=Form(...)):
        try:store.add_stream(ident,remote_id,label)
        except ValueError as exc:error(exc)
        return redirect('/assistant/connections')
    @app.post('/assistant/streams/{ident}')
    def stream_save(ident:str,version:int=Form(...),enabled:bool=Form(False)):
        try:store.control_stream(ident,version,enabled)
        except ValueError as exc:error(exc)
        return redirect('/assistant/connections')
    @app.get('/assistant/sources/{ident}')
    def source(ident:str):
        try:s=store.source(ident);a=store.channel(s['channel_id'])
        except ValueError as exc:raise HTTPException(404,str(exc)) from exc
        body='<h1>'+E(s['subject'])+'</h1><p>'+E(a['label']+' · '+a['kind'])+'</p><p>'+E(s['sender'])+' · '+E(datetime.fromtimestamp(s['received'],ZoneInfo(store.settings()['timezone'])).isoformat())+'</p><pre>'+E(s['body'])+'</pre><p>'+E(s['notice'])+'</p><p>Sender identity and source claims are unverified. This is a bounded saved preview.</p>'
        if not s['archived']:body+='<form method="post" action="/assistant/sources/'+ident+'/archive"><input type="hidden" name="version" value="'+str(s['version'])+'"><button>Archive reviewed preview</button></form>'
        return page(body)
    @app.post('/assistant/sources/{ident}/archive')
    def archive(ident:str,version:int=Form(...)):
        try:store.archive(ident,version)
        except ValueError as exc:error(exc)
        return redirect()
    @app.post('/assistant/alerts/{ident}')
    def ack(ident:str):store.acknowledge(ident);return redirect()
    @app.get('/assistant/runs/{ident}')
    def run(ident:str):
        try:r=store.run(ident)
        except ValueError as exc:raise HTTPException(404,str(exc)) from exc
        snap=json.loads(r['snapshot']);result=json.loads(r['result']) if r['result'] else None
        body='<h1>Twin '+E(r['kind'])+'</h1><p>'+E(r['status'])+' · '+E(local(r['created_at']))+'</p>'
        if r['error']:body+='<p class="error">'+E(r['error'])+'</p>'
        if result:
            body+='<p>'+E(result['summary'])+'</p>'
            for item in result['items']:
                ref=snap['aliases'][item['source']];body+='<section class="card"><h2>'+E(item['category']+' · '+item['headline'])+'</h2><p>'+E(item['reason'])+'</p>'+source_link(ref['source_id'],item['source'])+'</section>'
        if snap.get('context'):
            body+='<details><summary>Coverage & captured source previews</summary><pre>'+E(json.dumps({'captured_local':snap['context']['captured_local'],'coverage':snap['context']['coverage'],'previews':snap['context']['SOURCE_PREVIEWS']},ensure_ascii=False,indent=2))+'</pre></details>'
        if r['status'] in ('interrupted','blocked','cancelled'):body+='<form method="post" action="/assistant/runs/'+ident+'/retry"><input type="hidden" name="version" value="'+str(r['version'])+'">'+input('What you checked; authorize a fresh attempt','note','',True)+'<button>Authorize fresh analysis</button></form>'
        return page(body)
    @app.post('/assistant/runs/{ident}/retry')
    def retry(ident:str,version:int=Form(...),note:str=Form(...)):
        try:key=engine.retry(ident,version,note)
        except ValueError as exc:error(exc)
        return redirect('/assistant/runs/'+key if key else '/assistant')
    @app.get('/assistant/drafts/{ident}')
    def draft(ident:str):
        d=next((x for x in store.drafts() if x['id']==ident),None)
        if not d:raise HTTPException(404,'Draft not found')
        s=store.source(d['source_id']);stale=s['digest']!=d['source_digest'] or s['archived']
        body='<h1>Review local reply draft</h1>'+source_link(s['id'])+'<p>Verify the intended recipient and full conversation in the original app, then copy this draft there to send it yourself. The Twin has not contacted anyone.</p>'
        if stale:body+='<p class="error">The source changed or was archived. Recheck it and request a fresh analysis before using this draft.</p>'
        body+='<form method="post" action="/assistant/drafts/'+ident+'"><input type="hidden" name="version" value="'+str(d['version'])+'">'+input('Reply text','body',d['body'],True)+'<button>Save reviewed draft locally</button></form>'
        return page(body)
    @app.post('/assistant/drafts/{ident}')
    def draft_save(ident:str,version:int=Form(...),body:str=Form(...)):
        try:store.edit_draft(ident,version,body)
        except ValueError as exc:error(exc)
        return redirect('/assistant/drafts/'+ident)
    @app.get('/assistant/proposals/{ident}')
    def proposal(ident:str):
        pr=next((x for x in store.proposals() if x['id']==ident),None)
        if not pr:raise HTTPException(404,'Proposal not found')
        body='<h1>'+E(pr['title'])+'</h1>'+source_link(pr['source_id'])+'<p>Department: '+E(pr['department'])+' · '+E(pr['state'])+'</p><pre>'+E(pr['instruction'])+'</pre><p>Acceptance: '+E(pr['acceptance'])+'</p><p>This privately sourced task needs your explicit sharing decision. Choose an active restricted project graded consequential or high risk. The task will still need its start approval.</p>'
        if pr['state']=='proposed':
            projects=[q for q in team.projects() if q['status']=='active' and q['sensitivity']=='restricted' and q['risk']!='routine']
            if projects:body+='<form method="post" action="/assistant/proposals/'+ident+'"><input type="hidden" name="version" value="'+str(pr['version'])+'"><label>Destination project<select name="project_id">'+''.join('<option value="'+E(q['id'])+'">'+E(q['title'])+'</option>' for q in projects)+'</select></label>'+input('Authorize private sharing and explain the purpose','note','',True)+'<button>Approve sharing and create governed task</button></form>'
            else:body+='<p>'+link('/team','Create a suitable restricted project first')+'</p>'
            body+='<form method="post" action="/assistant/proposals/'+ident+'/reject"><input type="hidden" name="version" value="'+str(pr['version'])+'"><button>Reject proposal</button></form>'
        if pr['task_id']:body+='<p>'+link('/team/tasks/'+pr['task_id'],'Open governed specialist task')+'</p>'
        return page(body)
    @app.post('/assistant/proposals/{ident}')
    def route(ident:str,version:int=Form(...),project_id:str=Form(...),note:str=Form(...)):
        try:task=store.route(ident,version,project_id,note)
        except ValueError as exc:error(exc)
        return redirect('/team/tasks/'+task)
    @app.post('/assistant/proposals/{ident}/reject')
    def reject(ident:str,version:int=Form(...)):
        try:store.reject_proposal(ident,version)
        except ValueError as exc:error(exc)
        return redirect('/assistant/proposals/'+ident)
