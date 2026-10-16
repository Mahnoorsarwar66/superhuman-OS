"""One private briefing page; account analyses and approvals remain separate."""
from datetime import datetime,timezone
import hashlib
import json
import re
from uuid import uuid4
from fastapi import Form,HTTPException
from fastapi.responses import HTMLResponse,RedirectResponse
from superhuman.hosted import views,jobs
from superhuman.mail import store
from . import engine


def selected_slots(value):
    slots=value.split(',') if isinstance(value,str) else []
    if not 1<=len(slots)<=4 or len(set(slots))!=len(slots) or any(s not in store.SLOTS for s in slots):
        raise ValueError('Choose one to four configured inboxes')
    return slots


def bulk_reports(slots,key,path=store.p.DEFAULT_DB):
    if not re.fullmatch(r'[a-f0-9]{32}',key):raise ValueError('Reload the report form')
    results=[]
    for slot in selected_slots(slots):
        account=store.account(slot,path)
        try:
            if not account['connected']:raise ValueError('Inbox disconnected; reconnect before requesting a new report')
            submission=hashlib.sha256((key+':'+slot).encode()).hexdigest()[:32]
            thread=store.make_report(slot,submission,path)
            results.append({'account_id':slot,'thread_id':thread,'status':'queued_or_already_submitted'})
        except ValueError as exc:results.append({'account_id':slot,'status':'skipped','reason':str(exc)})
    return results


def report_rows(slot,path=store.p.DEFAULT_DB):
    store.account(slot,path)
    with store.p.connect(path) as db:
        return [dict(r) for r in db.execute('''SELECT m.id,m.thread_id,m.created_at,t.status,t.context_json,t.error,
                (SELECT COUNT(*) FROM dialogue_suggestions s WHERE s.thread_id=m.thread_id AND s.status='proposed') AS suggestions
                FROM mail_reports m JOIN dialogue_turns t ON t.id=m.turn_id WHERE m.account_id=?
                ORDER BY m.created_at DESC,m.id DESC LIMIT 20''',(slot,))]


def structured(row,at=None):
    if row['status']!='done':return None
    try:
        trace=json.loads(row['context_json'] or '{}');value=trace.get('briefing')
        if isinstance(value,dict) and isinstance(value.get('items'),list):
            now=at or datetime.now(timezone.utc)
            for item in value['items']:
                meeting=engine.timestamp(item.get('meeting_at',''))
                if meeting is not None and meeting<=now:item['priority']='past_event'
            value['items'].sort(key=lambda i:engine.PRIORITIES.index(i['priority']))
            return value
    except (ValueError,TypeError):pass
    return None


def source(report_id,reference,path=store.p.DEFAULT_DB):
    store.initialize(path)
    if not re.fullmatch(r'E(?:[1-9]|1[0-2])',reference):raise ValueError('Email reference not found')
    with store.p.connect(path) as db:
        row=db.execute('SELECT * FROM mail_reports WHERE id=?',(report_id,)).fetchone()
    if row is None:raise ValueError('Report not found')
    payload,_=engine.prepared(json.loads(row['snapshot']))
    selected=next((m for m in payload['messages'] if m['reference']==reference),None)
    if selected is None:raise ValueError('Email reference not in this report')
    return dict(report_id=report_id,thread_id=row['thread_id'],label=payload['label'],email=payload['email'],
                captured_local=payload['captured_local'],message=selected)


def install(app):
    esc=views.esc
    def render(body,title='Inbox briefing'):return HTMLResponse(views.page(body,title))
    def redirect():return RedirectResponse('/briefing',status_code=303)

    @app.get('/briefing')
    def home():
        accounts=store.accounts();worker=jobs.worker_status();now=datetime.now(timezone.utc)
        connected=[a['id'] for a in accounts if a['connected']]
        eligible=[slot for slot in connected if store.messages(slot,limit=1)]
        body='<p class="muted">'+esc(engine.local_time(now.isoformat()))+'</p><h1>Your inbox briefing</h1>'
        body+='<p>Decisions, follow-ups and useful context across your inboxes. Each account is analysed separately. Tasks wait for your approval.</p>'
        body+='<p>Worker: '+('Online' if worker['online'] else 'Offline')+(' · Paused' if worker['paused'] else '')+'. <a href="/briefing">Refresh</a> · <a href="/inboxes">Manage inboxes</a></p>'
        if connected:
            body+='<section class="card"><h2>Update your briefing</h2><p>First read recent mail, wait for the reads to finish, then request reports from the saved previews.</p>'
            body+='<form method="post" action="/briefing/read"><input type="hidden" name="accounts" value="'+','.join(connected)+'"><button>Read '+str(len(connected))+' inboxes · 0 model requests</button></form>'
            if eligible:
                body+='<form method="post" action="/briefing/report"><input type="hidden" name="accounts" value="'+','.join(eligible)+'"><input type="hidden" name="submission_key" value="'+uuid4().hex+'"><p>Each report sends up to 12 saved excerpts from its own inbox to your configured model. A failed attempt still counts. No automatic paid reports or retries.</p><button>Request '+str(len(eligible))+' reports · up to '+str(len(eligible))+' model attempts</button></form>'
            body+='</section>'
        body+='<p class="muted">Reports cover limited excerpts, not every email or attachment. Urgency and sender claims need verification. Common passwords, codes and links are masked where recognised; masking is not guaranteed for every secret. The original saved emails remain private working records.</p>'
        cached={a['id']:report_rows(a['id']) for a in accounts}
        def account_rank(account):
            value=next((structured(r) for r in cached[account['id']] if structured(r)),None)
            return min((engine.PRIORITIES.index(i['priority']) for i in value['items']),default=5) if value else 5
        for account in sorted(accounts,key=account_rank):
            slot=account['id'];reports=cached[slot];latest=reports[0] if reports else None
            completed=next((r for r in reports if structured(r)),None)
            body+='<section class="card"><h2>'+esc(account['label'])+'</h2><p>'+esc(account['email'] or 'Not connected')+' · '+('Connected' if account['connected'] else 'Disconnected')+'</p>'
            if account['last_sync']:body+='<p>Last successful read: '+esc(engine.local_time(account['last_sync']))+'</p>'
            with store.p.connect() as db:
                job=db.execute('SELECT status FROM mail_syncs WHERE account_id=? ORDER BY created DESC,id DESC LIMIT 1',(slot,)).fetchone()
            if job:body+='<p>Latest read: '+esc(job['status'].replace('_',' '))+'.</p>'
            if account['limited']:body+='<p class="error">Read limit reached; some messages were not included.</p>'
            if account['last_error']:body+='<p class="error">'+esc(account['last_error'])+'</p>'
            if latest:
                body+='<p>Latest report request: '+esc(latest['status'].replace('_',' '))+' · '+esc(engine.local_time(latest['created_at']))+'</p>'
                if latest['status'] in ('failed','interrupted','budget_blocked'):
                    body+='<p class="error">Report stopped. No automatic retry. <a href="/talk/'+latest['thread_id']+'">Inspect this request</a>.</p>'
            if completed:
                value=structured(completed);captured=engine.timestamp(completed['created_at'])
                if captured is not None and (now-captured).total_seconds()>43200:body+='<p class="error">This report is over 12 hours old. Read mail and request a new report for an updated view.</p>'
                if latest['id']!=completed['id']:body+='<p>Showing the last completed briefing below.</p>'
                body+='<p>Report snapshot: '+esc(engine.local_time(completed['created_at']))+'</p><h3>'+esc(value['overview'])+'</h3>'
                if value.get('overview_full',value['overview'])!=value['overview']:
                    body+='<details><summary>Full overview</summary><p>'+esc(value['overview_full'])+'</p></details>'
                for item in value['items']:
                    body+='<article><span class="badge">'+esc(engine.LABELS.get(item['priority'],'Review'))+'</span><h3>'+esc(item['headline'])+'</h3><p>'+esc(item['reason'])+'</p><p>'
                    for ref in item['sources']:
                        body+='<a href="/briefing/source/'+completed['id']+'/'+esc(ref)+'">Email '+esc(ref)+'</a> '
                    body+='</p>'
                    if item.get('reason_full',item['reason'])!=item['reason'] or item.get('headline_full',item['headline'])!=item['headline']:
                        body+='<details><summary>More context</summary><p>'+esc(item.get('headline_full',item['headline']))+'</p><p>'+esc(item.get('reason_full',item['reason']))+'</p></details>'
                    body+='</article>'
                if value['newsletter_count']:body+='<p class="muted">'+str(value['newsletter_count'])+' newsletter / promotional messages grouped.</p>'
                body+='<p><a class="button" href="/talk/'+completed['thread_id']+'">Review report and '+str(completed['suggestions'])+' proposed tasks</a></p>'
            elif latest:
                body+='<p><a href="/talk/'+latest['thread_id']+'">Open existing report</a>. Earlier reports keep their original format. Request a new report for the concise briefing layout.</p>'
            else:body+='<p>No report yet. Read this inbox, then request a report.</p>'
            body+='<p><a href="/inboxes/'+slot+'">Open '+esc(account['label'])+'</a></p></section>'
        return render(body)

    @app.post('/briefing/read')
    def read(accounts:str=Form(...)):
        try:slots=selected_slots(accounts)
        except ValueError as exc:raise HTTPException(400,str(exc)) from exc
        results=[]
        for slot in slots:
            try:results.append(store.queue_sync(slot))
            except ValueError:pass
        if not results:raise HTTPException(400,'No selected inbox is connected. Refresh and reconnect first.')
        return redirect()

    @app.post('/briefing/report')
    def report(accounts:str=Form(...),submission_key:str=Form(...)):
        try:results=bulk_reports(accounts,submission_key)
        except ValueError as exc:raise HTTPException(400,str(exc)) from exc
        body='<h1>Briefing requests</h1><p>Each queued report authorises one model attempt. Repeated submission of this same form does not create duplicate reports.</p>'
        for result in results:
            body+='<section class="card"><h2>'+esc(store.SLOTS[result['account_id']][0])+'</h2>'
            if 'thread_id' in result:body+='<p><a href="/talk/'+result['thread_id']+'">Open queued / previously submitted report</a></p>'
            else:body+='<p>'+esc(result['reason'])+'</p>'
            body+='</section>'
        return render(body+'<p><a class="button" href="/briefing">Return to briefing</a></p>')

    @app.get('/briefing/source/{report_id}/{reference}')
    def excerpt(report_id:str,reference:str):
        try:value=source(report_id,reference)
        except (ValueError,KeyError,TypeError) as exc:raise HTTPException(404,'Saved source not found') from exc
        m=value['message']
        body='<p>'+esc(value['label'])+' · '+esc(value['email'])+'</p><h1>'+esc(m['subject'])+'</h1>'
        body+='<p>Email '+esc(m['reference'])+' · '+esc(m['sender'])+'<br>'+esc(m['sent_local'])+'</p>'
        body+='<p>Saved report excerpt from '+esc(value['captured_local'])+'. This is an excerpt, not the full original email. Attachments are excluded. Common sensitive details are masked where recognised; verify important facts in the original inbox.</p>'
        body+='<p>'+esc(m['notice'])+'</p><pre>'+esc(m['body'])+'</pre><p><a href="/talk/'+value['thread_id']+'">Report and approval</a> · <a href="/briefing">All briefings</a></p>'
        return render(body,'Saved email excerpt')
