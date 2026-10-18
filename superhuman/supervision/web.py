"""Department policies, proposals, evidence-based progress and audit history."""
import json
from datetime import datetime,timezone,timedelta
from fastapi import Form,HTTPException
from fastapi.responses import HTMLResponse,RedirectResponse
from superhuman.navigation import shell
from superhuman.projects import engine as p
from superhuman.core.router import WORKSTREAMS
from superhuman.agentic import tools
from . import store,engine,context
E=shell.esc

def when(epoch):
    return datetime.fromtimestamp(epoch,timezone(timedelta(hours=5))).strftime('%d %b, %I:%M %p PKT') if epoch else 'Not checked yet'
def field(label,name,value='',kind='text',maximum=4000):
    tag='<textarea name="'+name+'" maxlength="'+str(maximum)+'">'+E(value)+'</textarea>' if kind=='textarea' else '<input name="'+name+'" type="'+kind+'" value="'+E(value)+'" required>'
    return '<label>'+E(label)+tag+'</label>'
def render(body,title='Department supervision'):return HTMLResponse(shell.page(body,title))
def panel(scope):
    pol=store.policy(scope)
    if not pol:return '<p><a href="/supervision/'+scope+'">Set up department supervision</a> · Off until configured.</p>'
    return '<p><a href="/supervision/'+scope+'">Department supervision</a> · '+('Paused' if not pol['enabled'] else 'Needs inspection' if pol['hold'] else 'Proposals for review' if pol['mode']=='review' else 'Automatic starts enabled')+' · '+str(pol['allocated_calls'])+' / '+str(pol['total_calls'])+' requests allocated.</p>'
def managed_banner(pid):
    item=store.managed(pid)
    if not item:return ''
    good,reason=store.managed_gate(pid)
    return '<section class="card"><p>Started by <a href="/supervision/'+item['scope']+'">department supervision</a>. Reserved run allowance: '+str(item['run_calls'])+' requests. <a href="/supervision/proposals/'+item['id']+'">View approved instructions and target</a>.</p>'+('<p class="error">'+E(reason)+'</p>' if not good else '')+'</section>'
def attention():
    out=[]
    for pol in store.policies():
        if pol['hold']:out.append({'title':WORKSTREAMS[pol['scope']]['name'],'reason':'Department review needs inspection','url':'/supervision/'+pol['scope']})
        for item in store.proposals(pol['scope']):
            if item['status']=='proposed':out.append({'title':item['title'],'reason':'Supervised proposal awaiting approval','url':'/supervision/proposals/'+item['id']})
    return out

def install(app):
    @app.get('/supervision')
    def home():
        body='<h1>Department supervision</h1><p>Review goals, identify the next ready target and create bounded agent runs. Every department starts off. Scheduling runs on your server worker.</p><div class="shell-grid">'
        for scope,meta in WORKSTREAMS.items():body+='<section class="card"><h2>'+E(meta['name'])+'</h2>'+panel(scope)+'</section>'
        return render(body+'</div>')

    @app.get('/supervision/proposals/{ident}')
    def detail(ident:str):
        try:item=store.proposal(ident)
        except ValueError as exc:raise HTTPException(404,str(exc)) from exc
        target=json.loads(item['target_json']);body='<p><a href="/supervision/'+item['scope']+'">Department supervision</a></p><h1>'+E(item['title'])+'</h1><p class="badge">'+E(item['status'])+'</p><h2>Target and required evidence</h2><p>'+E(target['title'])+'</p><p>'+E(target['criteria'])+'</p><p>'+str(item['run_calls'])+' reserved model requests on start · '+str(item['run_steps'])+' maximum decision steps. Required tools: '+E(', '.join(json.loads(item['required_tools'])) or 'At least one verified action')+'</p><details><summary>Permitted tools</summary><p>'+E(', '.join(json.loads(item['allowed_tools'])))+'</p></details>'
        if item['project_id']:body+='<p><a href="/agent-runs/'+item['project_id']+'">Inspect execution, outputs and run controls</a></p><pre>'+E(item['instruction'])+'</pre>'
        else:
            body+='<form method="post" action="/supervision/proposals/'+ident+'/control"><input type="hidden" name="version" value="'+str(item['version'])+'">'+field('Title','title',item['title'],maximum=180)+field('Instructions and constraints','instruction',item['instruction'],'textarea',12000)+field('Inspection note','note','','textarea',2000)+'<p>Refresh saves these edits and rechecks current context using the latest policy, without a model call. Approve starts the exact saved instructions. Save edits before approving.</p><button name="action" value="refresh">Save edits and refresh context</button> <button name="action" value="'+('reopen' if item['status']=='dismissed' else 'launch')+'">'+('Reopen proposal' if item['status']=='dismissed' else 'Approve saved proposal and start run')+'</button> <button class="secondary" name="action" value="dismiss">Dismiss</button></form>'
        return render(body,'Supervised proposal')

    @app.post('/supervision/proposals/{ident}/control')
    def proposal_control(ident:str,version:int=Form(...),action:str=Form(...),title:str=Form(''),instruction:str=Form(''),note:str=Form('')):
        try:
            if action=='launch':
                item=store.proposal(ident)
                if title!=item['title'] or instruction!=item['instruction']:raise ValueError('Save the edited instructions before approving the proposal')
                pid=engine.launch(ident,version);return RedirectResponse('/agent-runs/'+pid,status_code=303)
            engine.edit_proposal(ident,version,action,title,instruction,note)
        except ValueError as exc:raise HTTPException(409,str(exc)) from exc
        return RedirectResponse('/supervision/proposals/'+ident,status_code=303)

    @app.get('/supervision/{scope}')
    def department(scope:str):
        if scope not in WORKSTREAMS:raise HTTPException(404,'Unknown department')
        pol=store.policy(scope);values=pol or {'mission':'','acceptance':'','mode':'review','enabled':0,'interval_seconds':86400,'event_trigger':0,'total_calls':40,'allocated_calls':0,'run_calls':8,'run_steps':12,'allowed_tools':[t.name for t in tools.REGISTRY.values() if t.permission in tools.DEFAULT_PERMISSIONS],'required_tools':[],'version':0,'hold':0,'last_checked':0,'next_due':0,'last_summary':'Not configured','last_error':''}
        body='<p><a href="/departments/'+scope+'">'+E(WORKSTREAMS[scope]['name'])+'</a> / <a href="/supervision">Supervision</a></p><h1>'+E(WORKSTREAMS[scope]['name'])+' supervision</h1>'+panel(scope)+'<p>'+E(values['last_summary'])+'</p><p>Last checked: '+when(values['last_checked'])+' · Next scheduled check: '+when(values['next_due'])+'</p>'
        if values['last_error']:body+='<p class="error">'+E(values['last_error'])+'</p>'
        body+='<details'+(' open' if not pol else '')+'><summary>Mission, permissions and schedule</summary><form method="post" action="/supervision/'+scope+'/policy"><input type="hidden" name="version" value="'+str(values['version'])+'">'+field('Mission and constraints','mission',values['mission'],'textarea',1500)+field('Owner acceptance criteria','acceptance',values['acceptance'],'textarea',1500)+'<label>Operating mode<select name="mode"><option value="review"'+(' selected' if values['mode']=='review' else '')+'>Propose for my approval</option><option value="auto"'+(' selected' if values['mode']=='auto' else '')+'>Start bounded runs automatically</option></select></label><label><input name="enabled" type="checkbox" value="true"'+(' checked' if values['enabled'] else '')+'>Enable recurring reviews and managed run execution</label>'+field('Review interval in hours (1–168)','interval_hours',values['interval_seconds']//3600,'number')+'<label><input name="event_trigger" type="checkbox" value="true"'+(' checked' if values['event_trigger'] else '')+'>Also check saved goal, project, memory and source-file changes, at most every five minutes</label>'+field('Total request allocation ceiling (1–1000)','total_calls',values['total_calls'],'number')+field('Request allowance per new run (2–20)','run_calls',values['run_calls'],'number')+field('Decision steps per new run (2–20)','run_steps',values['run_steps'],'number')+'<fieldset><legend>Tools permitted for new runs</legend>'
        for t in tools.REGISTRY.values():body+='<label><input name="allowed_tools" type="checkbox" value="'+t.name+'"'+(' checked' if t.name in values['allowed_tools'] else '')+'>'+E(t.name+' — '+t.description)+'</label>'
        body+='</fieldset><fieldset><legend>Required verified tools before finishing</legend>'
        for t in tools.REGISTRY.values():
            if t.name!='inbox.queue_sync':body+='<label><input name="required_tools" type="checkbox" value="'+t.name+'"'+(' checked' if t.name in values['required_tools'] else '')+'>'+E(t.name)+'</label>'
        body+='</fieldset><p>One model request is allocated before a paid department review. A run reserves its entire allowance before starting. Allocations are conservative and never reset/refund automatically; actual run usage is shown below. Limits count requests, not money. Automatic starts require a verified-tool requirement. One supervised run or pending proposal per department proceeds at a time. Goals, milestones and factual outcomes still need your review.</p><button>Save policy and authorize within these limits</button></form></details>'
        if pol:
            body+='<form method="post" action="/supervision/'+scope+'/control"><input type="hidden" name="version" value="'+str(pol['version'])+'">'+field('Inspection note (required after an interrupted review)','note','','textarea',2000)+'<button name="action" value="review_now">Queue a review now</button> <button name="action" value="pause" class="secondary">Pause reviews and future managed steps</button></form><p>Pause takes effect between steps; in-flight requests can finish. Interrupted reviews do not replay automatically. A manual review may allocate another request. Unchanged saved context normally needs no new model review.</p>'
        progress=context.progress(scope)
        body+='<h2>Work and evidence</h2><p>Saved execution states are not proof of business success. Approve outputs in Agent runs, then assess milestones in the department plan.</p>'
        for row in progress['runs']:
            body+='<section class="card"><h3><a href="/supervision/proposals/'+row['proposal_id']+'">'+E(row['title'])+'</a></h3><p>'+E(row['project_status'] or row['proposal_status'])+' · '+str(row['used_calls'])+' actual run requests. Target: '+E(row['target']['title'])+'</p>'
            if row['project_id']:
                good,reason=store.managed_gate(row['project_id'])
                if not good:body+='<p class="error">'+E(reason)+'</p>'
                body+='<p><a href="/agent-runs/'+row['project_id']+'">Inspect action evidence and review</a></p>'
            body+='</section>'
        cycles,events=store.history(scope)
        body+='<h2>Review history</h2>'
        for cycle in cycles:body+='<details><summary>'+E(cycle['created_at']+' · '+cycle['status'])+'</summary><p>'+E(cycle['summary'])+'</p><p>'+E(cycle['error'] or '')+' · '+str(cycle['allocated'])+' review request allocated.</p></details>'
        body+='<details><summary>Owner decisions and allocation audit</summary><pre>'+E(json.dumps(events,indent=2,ensure_ascii=False))+'</pre></details>'
        return render(body,WORKSTREAMS[scope]['name']+' supervision')

    @app.post('/supervision/{scope}/policy')
    def policy_save(scope:str,version:int=Form(...),mission:str=Form(...),acceptance:str=Form(...),mode:str=Form('review'),enabled:bool=Form(False),interval_hours:int=Form(24),event_trigger:bool=Form(False),total_calls:int=Form(40),run_calls:int=Form(8),run_steps:int=Form(12),allowed_tools:list[str]=Form([]),required_tools:list[str]=Form([])):
        try:store.save(scope,version,mission,acceptance,mode,enabled,interval_hours,event_trigger,total_calls,run_calls,run_steps,allowed_tools,required_tools)
        except ValueError as exc:raise HTTPException(409,str(exc)) from exc
        return RedirectResponse('/supervision/'+scope,status_code=303)

    @app.post('/supervision/{scope}/control')
    def control(scope:str,version:int=Form(...),action:str=Form(...),note:str=Form('')):
        try:store.control(scope,version,action,note)
        except ValueError as exc:raise HTTPException(409,str(exc)) from exc
        return RedirectResponse('/supervision/'+scope,status_code=303)
