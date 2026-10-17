"""One internal team workspace, Twin conversation and explicit owner governance."""
import json,time
from fastapi import Form,HTTPException
from fastapi.responses import HTMLResponse,RedirectResponse
from superhuman.navigation import shell
from superhuman.projects import engine as p
from . import store,work,engine,budget
from superhuman.workspace import model as uxmodel
E=shell.esc

def page(body,title='Persistent team'):return HTMLResponse(shell.page(body,title))
def link(url,label):return '<a href="'+E(url)+'">'+E(label)+'</a>'
def input(label,name,value='',area=False):return '<label>'+E(label)+(('<textarea name="'+name+'" maxlength="8000">'+E(value)+'</textarea>') if area else '<input name="'+name+'" value="'+E(value)+'">')+'</label>'
def options(name,values,chosen):return '<label>'+E(name.replace('_',' '))+'<select name="'+name+'">'+''.join('<option value="'+E(v)+'"'+(' selected' if v==chosen else '')+'>'+E(uxmodel.NAMES.get(v,v) if name=='owner' else uxmodel.ROLES.get(v,v) if name=='scope' else uxmodel.label(v))+'</option>' for v in values)+'</select></label>'
def error(exc):raise HTTPException(409,str(exc)) from exc
def redirect(url):return RedirectResponse(url,status_code=303)
def badge(item):return '<span class="badge">'+E(item['state'].replace('_',' '))+'</span>'
def settings_version():return str(store.settings()['version'])
def overview():
    cfg=store.settings();return '<p>'+link('/team','Mahnoor Twin & persistent team')+' · '+('Enabled' if cfg['enabled'] else 'Off until configured')+(' · Needs inspection' if cfg['hold'] else '')+'</p>'
def banner(pid):
    item=work.owned_run(pid)
    if not item:return ''
    good,reason=work.gate(item)
    return '<section class="card"><p>Owned by '+link('/team/employees/'+item['owner'],store.EMPLOYEES[item['owner']][0])+' · '+link('/team/tasks/'+item['id'],'Task, governance and handoffs')+'</p>'+('<p class="error">'+E(reason)+'</p>' if not good else '')+'</section>'
def attention():
    out=[];cfg=store.settings()
    if cfg['hold']:out.append({'title':'Mahnoor Twin','reason':cfg['hold'],'url':'/twin'})
    for t in store.tasks():
        if t['state'] in ('owner_review','held','disputed') or t['state']=='awaiting_review' and store.needs_owner(t):out.append({'title':t['title'],'reason':'Team task '+t['state'].replace('_',' '),'url':'/team/tasks/'+t['id']})
    for r in store.requests():
        if r['status']=='escalated':out.append({'title':'Specialist request','reason':'Owner decision required','url':'/team/requests/'+r['id']})
    return out

def install(app):
    @app.get('/team')
    def home():
        cfg=store.settings();body='<h1>Mahnoor Twin & seven specialists</h1>'+overview()+'<p>Persistent identities share the existing worker. Up to '+str(cfg['max_active'])+' assignments may be active; execution advances one step at a time. Writing is a department skill. Communications and scheduled briefings are in the Personal assistant workspace.</p><p>'+link('/twin','Talk to the Twin')+' · '+link('/team/budget','Dollar budget and rates')+' · '+link('/team/memory','Memory confirmation')+'</p>'
        if not store.employees():body+='<form method="post" action="/team/setup"><button>Initialize team records without enabling paid work</button></form>'
        else:
            body+='<div class="shell-grid">'
            for e in store.employees():
                owned=[t for t in store.tasks() if t['owner']==e['id'] and t['state'] not in ('completed','cancelled')]
                body+='<section class="card"><h2>'+link('/team/employees/'+e['id'],e['name'])+'</h2><p>'+('Paused' if e['paused'] else 'Available')+' · '+str(len(owned))+' unfinished tasks</p><p>'+E(e['charter'])+'</p></section>'
            body+='</div><h2>Team settings</h2><form method="post" action="/team/settings"><input type="hidden" name="version" value="'+settings_version()+'"><label><input type="checkbox" name="enabled_value" value="true"'+(' checked' if cfg['enabled'] else '')+'>Enable the Twin and managed employee work</label>'+input('Exact model identifier','model',cfg['model'])+input('Maximum active assignments (1–7)','max_active',cfg['max_active'])+'<p>Confirm a model rate card and active budget before enabling. Pausing the team does not disable the dollar guard on existing model work.</p><button>Save settings</button></form>'
        body+='<h2>Projects</h2>'
        for q in store.projects():body+='<p>'+link('/team/projects/'+q['id'],q['title'])+' · '+E(q['priority']+' / '+q['risk']+' / '+q['sensitivity']+' / '+q['status'])+'</p>'
        body+='<details><summary>Create an owner-approved project</summary><form method="post" action="/team/projects">'+options('scope',[e for e in store.EMPLOYEES if e!='twin'],'edsync_product')+input('Title','title')+input('Objective (max 2000 characters)','objective','',True)+input('Acceptance criteria (max 2000 characters)','acceptance','',True)+options('priority',store.PRIORITIES,'P2')+options('risk',store.RISKS,'routine')+options('sensitivity',store.SENSITIVITIES,'internal')+'<button>Create project</button></form></details>'
        body+='<details><summary>Adopt an existing agent run</summary><form method="post" action="/team/adopt">'+input('Canonical agent run ID','pid')+input('Acceptance criteria','acceptance','',True)+options('priority',store.PRIORITIES,'P2')+options('risk',store.RISKS,'consequential')+options('sensitivity',store.SENSITIVITIES,'confidential')+'<p>Adoption preserves execution history and starts held unless already complete or awaiting review. Existing v1.25 policy gates still apply.</p><button>Adopt existing run</button></form></details>'
        body+='<details><summary>Ownership and decision audit</summary><pre>'+E(json.dumps(store.audit(),indent=2))+'</pre></details>'
        return page(body)

    @app.post('/team/setup')
    def setup():store.initialize();return redirect('/team')
    @app.post('/team/settings')
    def settings(version:int=Form(...),enabled_value:bool=Form(False),model:str=Form(...),max_active:int=Form(2)):
        try:store.configure(version,enabled_value,model,max_active)
        except ValueError as exc:error(exc)
        return redirect('/team')
    @app.post('/team/projects')
    def create_project(scope:str=Form(...),title:str=Form(...),objective:str=Form(...),acceptance:str=Form(...),priority:str=Form('P2'),risk:str=Form('routine'),sensitivity:str=Form('internal')):
        try:ident=store.create_project(scope,title,objective,acceptance,priority,risk,sensitivity)
        except ValueError as exc:error(exc)
        return redirect('/team/projects/'+ident)
    @app.post('/team/adopt')
    def adopt(pid:str=Form(...),acceptance:str=Form(...),priority:str=Form('P2'),risk:str=Form('consequential'),sensitivity:str=Form('confidential')):
        try:ident=work.adopt(pid,acceptance,priority,risk,sensitivity)
        except ValueError as exc:error(exc)
        return redirect('/team/tasks/'+ident)

    @app.get('/team/projects/{ident}')
    def project(ident:str):
        try:q=store.project(ident)
        except ValueError as exc:raise HTTPException(404,str(exc)) from exc
        body='<p>'+link('/team','Team')+'</p><h1>'+E(q['title'])+'</h1><p>'+E(q['objective'])+'</p><p>Acceptance: '+E(q['acceptance'])+'</p><details><summary>Project controls</summary><form method="post" action="/team/projects/'+ident+'/governance"><input type="hidden" name="version" value="'+str(q['version'])+'">'+options('priority',store.PRIORITIES,q['priority'])+options('risk',store.RISKS,q['risk'])+options('sensitivity',store.SENSITIVITIES,q['sensitivity'])+options('status',('active','paused','complete'),q['status'])+'<p>Governance edits invalidate prior start grants. Marking a business project complete is an owner decision.</p><button>Update project governance</button></form></details><p><a href="/new-task?project_id='+ident+'">Add task</a></p><h2>Tasks</h2>'
        for t in store.tasks():
            if t['project_id']==ident:body+='<p>'+link('/team/tasks/'+t['id'],t['title'])+' · '+E(store.EMPLOYEES[t['owner']][0])+' · '+badge(t)+'</p>'
        body+='<details><summary>Advanced task assignment</summary><form method="post" action="/team/projects/'+ident+'/tasks">'+options('owner',[e for e in store.EMPLOYEES if e!='twin'],q['scope'])+input('Title','title')+input('Instructions (max 5000)','instruction','',True)+input('Acceptance criteria (max 1500)','acceptance','',True)+input('Due date YYYY-MM-DD (optional)','due')+input('Prerequisite team task IDs, comma separated','deps')+'<p>Priority, risk and sensitivity inherit from this project. The Twin may also break an empty active project into bounded tasks.</p><button>Create task</button></form></details>'
        return page(body,q['title'])
    @app.post('/team/projects/{ident}/governance')
    def governance(ident:str,version:int=Form(...),priority:str=Form(...),risk:str=Form(...),sensitivity:str=Form(...),status:str=Form(...)):
        try:store.update_project(ident,version,priority,risk,sensitivity,status)
        except ValueError as exc:error(exc)
        return redirect('/team/projects/'+ident)
    @app.post('/team/projects/{ident}/tasks')
    def create_task(ident:str,owner:str=Form(...),title:str=Form(...),instruction:str=Form(...),acceptance:str=Form(...),due:str=Form(''),deps:str=Form('')):
        try:tid=store.create_task(ident,owner,title,instruction,acceptance,due=due,deps=[d.strip() for d in deps.split(',') if d.strip()])
        except ValueError as exc:error(exc)
        return redirect('/team/tasks/'+tid)

    @app.get('/team/tasks/{ident}')
    def task(ident:str):
        try:t=store.task(ident)
        except ValueError as exc:raise HTTPException(404,str(exc)) from exc
        cls=store.effective(t);body='<p>'+link('/team/projects/'+t['project_id'],'Project')+'</p><h1>'+E(t['title'])+'</h1>'+badge(t)+'<p>Employee: '+E(store.EMPLOYEES[t['owner']][0])+' · '+E(' / '.join(cls.values()))+'</p><p>'+E(t['instruction'])+'</p><p>Acceptance: '+E(t['acceptance'])+'</p><p>Request allowance '+str(t['max_calls'])+' · Steps '+str(t['max_steps'])+' · Task dollar ceiling $'+budget.usd(t['cost_limit'])+'</p>'
        if t['run_id']:body+='<p>'+link('/agent-runs/'+t['run_id'],'Inspect tool actions, artifacts and canonical review')+'</p>'
        good,reason=work.gate(t)
        if not good:body+='<p class="error">'+E(reason)+'</p>'
        body+='<form method="post" action="/team/tasks/'+ident+'/control"><input type="hidden" name="version" value="'+str(t['version'])+'">'+input('Inspection / review note','note','',True)+'<button name="action" value="approve_start">Approve start / continuation</button> <button name="action" value="pause">Pause</button> <button name="action" value="resume">Resume after inspection</button> <button name="action" value="cancel">Cancel</button> <button name="action" value="restrict_private_tools">Remove public-web tools from private run</button>'
        if t['state']=='awaiting_review':body+=' <button name="action" value="approve_output">Approve output</button> <button name="action" value="revise_output">Request revision</button>'
        body+='</form><details><summary>Authorize task limits</summary><form method="post" action="/team/tasks/'+ident+'/limits"><input type="hidden" name="version" value="'+str(t['version'])+'">'+input('Model requests','max_calls',t['max_calls'])+input('Decision steps','max_steps',t['max_steps'])+input('Task dollars','cost_limit',budget.usd(t['cost_limit']))+'<button>Authorize limits</button></form></details><h2>Handoffs and disagreements</h2>'
        for req in store.requests():
            if req['task_id']==ident:body+='<p>'+link('/team/requests/'+req['id'],req['kind'])+' · '+E(req['status'])+'</p>'
        return page(body,t['title'])
    @app.post('/team/tasks/{ident}/control')
    def task_control(ident:str,version:int=Form(...),action:str=Form(...),note:str=Form('')):
        try:
            if action in ('approve_output','revise_output'):work.review(ident,version,action=='approve_output',note,actor='owner')
            else:work.task_control(ident,version,action,note)
        except ValueError as exc:error(exc)
        return redirect('/team/tasks/'+ident)
    @app.post('/team/tasks/{ident}/limits')
    def task_limits(ident:str,version:int=Form(...),max_calls:int=Form(...),max_steps:int=Form(...),cost_limit:str=Form(...)):
        try:work.limits(ident,version,max_calls,max_steps,cost_limit)
        except ValueError as exc:error(exc)
        return redirect('/team/tasks/'+ident)

    @app.get('/team/requests/{ident}')
    def request(ident:str):
        r=next((r for r in store.requests() if r['id']==ident),None)
        if not r:raise HTTPException(404,'Request not found')
        body='<p>'+link('/team/tasks/'+r['task_id'],'Parent task')+'</p><h1>'+E(r['kind'])+'</h1><p>'+E(r['status'])+'</p><pre>'+E(json.dumps(json.loads(r['payload']),indent=2))+'</pre><p>'+E(r['response'])+'</p>'
        if r['status'] in ('open','escalated'):body+='<form method="post" action="/team/requests/'+ident+'"><input type="hidden" name="version" value="'+str(r['version'])+'">'+input('Owner decision rationale','note','',True)+('<button name="action" value="accept">Authorize handoff</button>' if r['kind']=='handoff' else '<button name="action" value="alternative">Authorize specialist alternative</button>')+' <button name="action" value="maintain">Maintain instruction / decline handoff</button></form>'
        return page(body,'Team request')
    @app.post('/team/requests/{ident}')
    def request_decision(ident:str,version:int=Form(...),action:str=Form(...),note:str=Form(...)):
        try:work.resolve_request(ident,version,action,note,actor='owner')
        except ValueError as exc:error(exc)
        return redirect('/team/requests/'+ident)

    @app.get('/twin')
    def twin():
        cfg=store.settings();body='<h1>Mahnoor Twin</h1><p>Your internal coordinator and owner-facing conversation. Use Personal assistant for connected-channel intake, local reply drafts and scheduled briefings.</p>'+overview()
        from superhuman.comms.web import twin_panel
        body+=twin_panel()
        if cfg['hold']:body+='<p class="error">'+E(cfg['hold'])+'</p><form method="post" action="/team/twin/resume"><input type="hidden" name="version" value="'+str(cfg['version'])+'">'+input('What you inspected; authorize another attempt','note','',True)+'<button>Authorize Twin continuation</button></form>'
        body+='<form method="post" action="/team/twin/messages">'+options('kind',('instruction','temporary_constraint','preference','decision','priority_change'),'instruction')+input('Update for the Twin','content','',True)+input('Temporary constraint duration in hours (1–2160)','hours','24')+'<p>Free-text constraints guide planning. Use explicit project/task/team pause controls for an immediate enforced stop. Preferences need confirmation before becoming lasting memory.</p><button>Send internal update</button></form><h2>Your current updates</h2>'
        for m in store.messages():body+='<section class="card"><small>'+E(m['kind']+' · '+m['status'])+'</small><p>'+E(m['content'])+'</p></section>'
        body+='<h2>Twin decisions and replies</h2>'
        for e in store.audit():
            if e['actor']=='twin' and e['action']=='decision':
                d=json.loads(e['detail_json']);body+='<section class="card"><p>'+E(d.get('reply',''))+'</p><small>'+E(d.get('action','')+' · '+d.get('rationale',''))+'</small></section>'
        body+='<p>The Twin wakes for changed work, new updates and reviews. Unchanged idle state makes no repeated model calls. Coordination is capped at 30 model decisions per rolling hour.</p>'
        return page(body,'Mahnoor Twin')
    @app.post('/team/twin/messages')
    def message(kind:str=Form(...),content:str=Form(...),hours:int=Form(24)):
        try:store.add_message(kind,content,time.time()+hours*3600 if kind=='temporary_constraint' else None)
        except ValueError as exc:error(exc)
        return redirect('/twin')
    @app.post('/team/twin/resume')
    def resume(version:int=Form(...),note:str=Form(...)):
        try:engine.resume(version,note)
        except ValueError as exc:error(exc)
        return redirect('/twin')

    @app.get('/team/employees/{ident}')
    def employee(ident:str):
        e=next((e for e in store.employees() if e['id']==ident),None)
        if not e:raise HTTPException(404,'Initialize the team or choose a registered employee')
        from superhuman.agentic.tools import REGISTRY
        body='<p>'+link('/team','Team')+'</p><h1>'+E(e['name'])+'</h1><form method="post" action="/team/employees/'+ident+'"><input type="hidden" name="version" value="'+str(e['version'])+'"><label><input type="checkbox" name="paused" value="true"'+(' checked' if e['paused'] else '')+'>Pause this employee</label>'+input('Charter','charter',e['charter'],True)+'<fieldset><legend>Permitted tools</legend>'
        for n in REGISTRY:body+='<label><input type="checkbox" name="allowed" value="'+n+'"'+(' checked' if n in json.loads(e['allowed_tools']) else '')+'>'+E(n)+'</label>'
        body+='</fieldset><button>Update employee</button></form>'
        sk=store.skill(ident)
        if sk:body+='<h2>Department writing skill</h2><form method="post" action="/team/employees/'+ident+'/skill"><input type="hidden" name="version" value="'+str(sk['version'])+'">'+input('Rules','rules',sk['rules'],True)+input('Owner-approved examples','examples',sk['examples'],True)+'<p>Versioned instructions and examples customise writing; this does not train new model weights.</p><button>Confirm writing skill</button></form>'
        body+='<h2>Owned work</h2>'
        for t in store.tasks():
            if t['owner']==ident:body+='<p>'+link('/team/tasks/'+t['id'],t['title'])+' · '+badge(t)+'</p>'
        body+='<h2>Confirmed employee memory</h2>'
        for m in store.memory(ident,'restricted'):body+='<p>'+E(m['content'])+'</p>'
        return page(body,e['name'])
    @app.post('/team/employees/{ident}')
    def employee_save(ident:str,version:int=Form(...),paused:bool=Form(False),charter:str=Form(...),allowed:list[str]=Form([])):
        try:store.employee_control(ident,version,paused,charter,allowed)
        except ValueError as exc:error(exc)
        return redirect('/team/employees/'+ident)
    @app.post('/team/employees/{ident}/skill')
    def skill_save(ident:str,version:int=Form(...),rules:str=Form(...),examples:str=Form('')):
        try:store.save_skill(ident,version,rules,examples)
        except ValueError as exc:error(exc)
        return redirect('/team/employees/'+ident)

    @app.get('/team/memory')
    def memory():
        body='<h1>Employee memory</h1><p>Proposed notes are excluded from working memory until you confirm them. Shared notes are limited to public/internal classification; personal private notes belong to the Twin.</p><form method="post" action="/team/memory">'+options('employee',list(store.EMPLOYEES),'twin')+options('kind',('fact','preference','decision','lesson'),'preference')+options('visibility',('department','shared','twin_private'),'twin_private')+options('sensitivity',store.SENSITIVITIES,'internal')+input('Memory and evidence/context','content','',True)+'<button>Propose memory</button></form>'
        from superhuman.departments.store import readonly,tables,rows
        with readonly(p.DEFAULT_DB) as db:notes=rows(db,'SELECT * FROM team_memory ORDER BY created_at DESC LIMIT 100') if 'team_memory' in tables(db) else []
        for m in notes:
            body+='<section class="card"><p>'+E(m['employee']+' / '+m['visibility']+' / '+m['sensitivity']+' / '+m['status'])+'</p><p>'+E(m['content'])+'</p>'
            if m['status']=='proposed':body+='<form method="post" action="/team/memory/'+m['id']+'"><input type="hidden" name="version" value="'+str(m['version'])+'"><button name="approve" value="true">Confirm</button> <button name="approve" value="false">Reject</button></form>'
            body+='</section>'
        return page(body,'Employee memory')
    @app.post('/team/memory')
    def memory_add(employee:str=Form(...),kind:str=Form(...),visibility:str=Form(...),sensitivity:str=Form(...),content:str=Form(...)):
        try:store.add_memory(employee,kind,content,visibility,sensitivity)
        except ValueError as exc:error(exc)
        return redirect('/team/memory')
    @app.post('/team/memory/{ident}')
    def memory_review(ident:str,version:int=Form(...),approve:bool=Form(...)):
        try:store.confirm_memory(ident,version,approve)
        except ValueError as exc:error(exc)
        return redirect('/team/memory')

    @app.get('/team/budget')
    def budget_page():
        r=budget.report();period=r['period'];body='<h1>Dollar budget</h1><p>Reservations and token-derived estimates use your confirmed rate cards. Unknown usage retains the full reservation. Search is conservatively accounted at up to $0.025/call. Provider invoices and account hard limits remain the final billing backstop.</p>'
        if not period:body+='<form method="post" action="/team/budget/period">'+input('Pilot total dollars (maximum 200)','total','200')+input('Twin dollars','twin','60')+input('Specialist/legacy dollars','staff','80')+input('Tool dollars','tools','20')+input('Period days (1–31)','days','30')+'<button>Authorize dollar budget period</button></form>'
        else:
            body+='<p>Total $'+budget.usd(period['total'])+' · Reserve $'+budget.usd(period['reserve'])+' · '+('HELD' if period['hold'] else 'Active' if period['end']>time.time() else 'Expired — explicitly renew')+'</p><table><thead><tr><th>Pool</th><th>Charged / reserved</th><th>Ceiling</th></tr></thead><tbody>'+''.join('<tr><td>'+name+'</td><td>$'+budget.usd(r['totals'][name])+'</td><td>$'+budget.usd(period[name+'_cap'])+'</td></tr>' for name in ('twin','staff','tools'))+'</tbody></table><p>Total charged / reserved: $'+budget.usd(r['totals']['text']+r['totals']['tools'])+' · '+str(r['totals']['uncertain'])+' unresolved usage records.</p>'
            body+='<form method="post" action="/team/budget/reserve"><input type="hidden" name="version" value="'+str(period['version'])+'">'+options('pool',('twin','staff','tools'),'staff')+input('Reserve dollars to release','amount')+'<button>Authorize reserve transfer</button></form>'
            if period['hold']:body+='<form method="post" action="/team/budget/hold"><input type="hidden" name="version" value="'+str(period['version'])+'">'+input('Rate/provider reconciliation evidence','note','',True)+'<button>Clear inspected budget hold</button></form>'
            if period['end']<=time.time():body+='<form method="post" action="/team/budget/period">'+input('New total dollars','total','200')+input('Twin','twin','60')+input('Specialists','staff','80')+input('Tools','tools','20')+input('Days','days','30')+'<button>Explicitly renew budget</button></form>'
        body+='<h2>Confirm a model rate card</h2><p>Use exact model names and rates covering your applicable input/output tiers. Cached discounts are not assumed. No model is silently replaced for legacy work.</p><form method="post" action="/team/budget/rates">'+input('Exact model ID','model',store.settings()['model'])+input('Input USD per million tokens','input_rate')+input('Output USD per million tokens','output_rate')+input('Official pricing URL / verification record','source','https://developers.openai.com/api/docs/pricing')+'<label><input type="checkbox" name="confirmed" value="true" required>I verified these rates and this model is available to my account.</label><button>Confirm rate card</button></form><h2>Cost records</h2>'
        for c in r['costs']:
            body+='<details><summary>'+E(c['actor']+' · '+c['model']+' · '+c['state'])+' · $'+budget.usd(c['charged_text']+c['charged_tools'])+'</summary><pre>'+E(json.dumps(c,indent=2))+'</pre><form method="post" action="/team/budget/reconcile">'+input('Cost record ID','ident',c['id'])+input('Total actual provider dollars','total_dollars')+input('Provider invoice/usage evidence','note','',True)+'<button>Reconcile this record</button></form></details>'
        return page(body,'Dollar budget')
    @app.post('/team/budget/period')
    def period(total:str=Form('200'),twin:str=Form('60'),staff:str=Form('80'),tools:str=Form('20'),days:int=Form(30)):
        try:budget.create_period(total,twin,staff,tools,days)
        except ValueError as exc:error(exc)
        return redirect('/team/budget')
    @app.post('/team/budget/rates')
    def rate(model:str=Form(...),input_rate:str=Form(...),output_rate:str=Form(...),source:str=Form(...),confirmed:bool=Form(False)):
        if not confirmed:raise HTTPException(400,'Confirm the rate verification first')
        try:store.initialize();budget.set_rate(model,input_rate,output_rate,source)
        except ValueError as exc:error(exc)
        return redirect('/team/budget')
    @app.post('/team/budget/reserve')
    def reserve(version:int=Form(...),pool:str=Form(...),amount:str=Form(...)):
        try:budget.release_reserve(version,pool,amount)
        except ValueError as exc:error(exc)
        return redirect('/team/budget')
    @app.post('/team/budget/hold')
    def hold(version:int=Form(...),note:str=Form(...)):
        try:budget.clear_hold(version,note)
        except ValueError as exc:error(exc)
        return redirect('/team/budget')
    @app.post('/team/budget/reconcile')
    def reconcile(ident:str=Form(...),total_dollars:str=Form(...),note:str=Form(...)):
        try:budget.reconcile(ident,total_dollars,note)
        except ValueError as exc:error(exc)
        return redirect('/team/budget')
