"""Run setup, exact-action permissions, observations and verified artifacts."""
import json
from pathlib import Path
from fastapi import Form,HTTPException
from fastapi.responses import HTMLResponse,RedirectResponse,FileResponse
from superhuman.navigation import shell
from superhuman.projects import engine as p
from superhuman.core.router import WORKSTREAMS
from . import store,tools

E=shell.esc
LABELS={'ready':'Ready for next step','running':'Executing a step','completed':'Deliverable ready for owner review','awaiting_permission':'Prepared action needs permission','interrupted':'Interrupted — inspect before continuation','needs_review':'Needs your decision','budget_blocked':'Request limit reached','step_limit':'Decision-step limit reached','paused':'Paused','pause_requested':'Pausing after current step','cancel_requested':'Cancelling after current step','cancelled':'Cancelled'}

def render(body,title='Agent runs',status=200):return HTMLResponse(shell.page(body,title),status_code=status)
def get(pid):
    try:return store.get(pid)
    except ValueError as exc:raise HTTPException(404,str(exc)) from exc

def install(app):
    @app.get('/agent-runs')
    def home(department:str='all'):
        if department not in ('all',*WORKSTREAMS):raise HTTPException(400,'Unknown department')
        body='<h1>Tool-executing agent runs</h1><p>Give Superhuman a bounded task, choose its tools and request limits, then inspect each action and its evidence.</p><section class="card"><h2>Start a run</h2><form method="post" action="/agent-runs"><label>Department<select name="scope">'+''.join('<option value="'+E(k)+'"'+(' selected' if k==department else '')+'>'+E(v['name'])+'</option>' for k,v in WORKSTREAMS.items())+'</select></label><label>Title<input name="title" maxlength="180" required></label><label>Outcome and constraints<textarea name="instruction" maxlength="12000" required placeholder="Read our evidence, prepare a proposal and export it as Word. State what must be included."></textarea></label><label>Total model-request limit<input name="max_calls" type="number" min="1" max="100" value="8" required></label><label>Maximum decision steps, including finish<input name="max_actions" type="number" min="2" max="40" value="12" required></label><p>A decision uses one request. Existing drafting uses three additional requests; web research uses one. Local tools use none. Budgets count requests, not money.</p><fieldset><legend>Permissions for this run</legend>'
        for permission,label in tools.PERMISSIONS.items():body+='<label><input type="checkbox" name="permissions" value="'+permission+'"'+(' checked' if permission in tools.DEFAULT_PERMISSIONS else '')+'>'+E(label)+'</label>'
        body+='</fieldset><fieldset><legend>Required verified tools before a deliverable can finish (optional)</legend><p>Select the tool results that must be present. Overall business success still needs your review.</p>'
        for t in tools.REGISTRY.values():
            if t.name=='inbox.queue_sync':continue
            body+='<label><input type="checkbox" name="required_tools" value="'+E(t.name)+'">'+E(t.name+' — '+t.description)+'</label>'
        body+='</fieldset><p>Required tools must also be permitted. Missing Docker/test images remain unavailable, never a passing test. Actions outside these permissions stop for review. No sending, publishing, purchases or arbitrary shell execution tool is available.</p><button>Start agent run within these limits</button></form></section><h2>Existing runs</h2>'
        for r in store.listing():
            if department!='all' and r['workstream']!=department:continue
            body+='<section class="card"><h3><a href="/agent-runs/'+r['project_id']+'">'+E(r['objective'])+'</a></h3><p>'+E(LABELS.get(r['state'],r['state']))+' · '+E(WORKSTREAMS.get(r['workstream'],{}).get('name',r['workstream']))+' · '+str(r['used_calls'])+' / '+str(r['max_calls'])+' model requests.</p></section>'
        return render(body)

    @app.post('/agent-runs')
    def create(scope:str=Form(...),title:str=Form(...),instruction:str=Form(...),max_calls:int=Form(8),max_actions:int=Form(12),permissions:list[str]=Form([]),required_tools:list[str]=Form([])):
        if any(x not in tools.PERMISSIONS for x in permissions):raise HTTPException(400,'Unknown permission')
        allowed=[t.name for t in tools.REGISTRY.values() if t.permission in permissions]
        try:pid=store.create(scope,title,instruction,allowed,required_tools,max_calls,max_actions)
        except ValueError as exc:raise HTTPException(400,str(exc)) from exc
        return RedirectResponse('/agent-runs/'+pid,status_code=303)

    @app.get('/agent-runs/{pid}')
    def detail(pid:str):
        r=get(pid);project=r['project'];body='<p><a href="/agent-runs">Agent runs</a> / '+E(WORKSTREAMS[project['workstream']]['name'])+'</p><h1>'+E(project['objective'])+'</h1><p class="badge">'+E(LABELS.get(r['state'],r['state']))+'</p><p>'+E(project['details'])+'</p><p>'+str(project['used_calls'])+' / '+str(project['max_calls'])+' model requests · '+str(len(r['actions']))+' / '+str(r['max_actions'])+' decision steps.</p><p><a href="/agent-runs/'+pid+'">Refresh progress</a> · <a href="/projects/'+pid+'">Inspect final deliverable and review</a> · <a href="/department-plans/'+project['workstream']+'">Department policy</a></p>'
        if r['state']=='ready':
            from superhuman.repairs.scheduler import order
            if pid not in order([pid],p.DEFAULT_DB):body+='<p class="error">Waiting for department or milestone policy. Check the department plan.</p>'
        from superhuman.supervision.web import managed_banner
        body+=managed_banner(pid)
        if r.get('error'):body+='<p class="error">'+E(r['error'])+'</p>'
        body+='<details><summary>Tools and execution limits</summary><p>Permitted: '+E(', '.join(r['allowed_tools']))+'</p><p>Required before finish: '+E(', '.join(r['required_tools']) or 'At least one successful tool result')+'</p></details>'
        controls=[]
        if r['state']=='completed' and project['tasks'][0]['status']=='rejected':
            body+='<p class="error">Deliverable rejected. Record the correction and authorize further work within the remaining run limits.</p>'
            controls.append(('resume','Authorize correction work'))
        if r['state'] in ('ready','running','budget_blocked'):controls.append(('pause','Pause after this step'))
        if r['state'] not in ('completed','cancelled'):controls.append(('cancel','Cancel remaining work'))
        if r['state'] in ('paused','needs_review','interrupted'):controls.append(('resume','Authorize continuation'))
        if r['state']=='awaiting_permission':
            a=next(a for a in reversed(r['actions']) if a['status']=='awaiting_permission')
            body+='<section class="card"><h2>Prepared action</h2><p>'+E(a['tool'])+' · '+E(a['rationale'])+'</p><pre>'+E(json.dumps(json.loads(a['arguments_json']),indent=2,ensure_ascii=False))+'</pre><p>Approval authorizes this exact action once. Existing run permissions do not expand.</p></section>'
            controls.append(('approve_action','Authorize this exact action'))
        if controls:
            body+='<form method="post" action="/agent-runs/'+pid+'/control"><input type="hidden" name="version" value="'+str(r['version'])+'"><label>Inspection / correction note (required for interrupted continuation)<textarea name="note" maxlength="2000"></textarea></label><p>Inspect any partially created artifacts before continuing an interrupted action. A new decision can consume another request; an uncertain repeated action requires its own authorization.</p><div class="stack">'+''.join('<button name="action" value="'+key+'">'+label+'</button>' for key,label in controls)+'</div></form>'
        if r['state']=='budget_blocked':body+='<p><a href="/tasks?task_status=blocked">Inspect the request-limit control in Tasks</a>. Saved actions are retained when the limit is raised.</p>'
        if r['state']=='step_limit':body+='<p>This run stopped at its step limit. Inspect its evidence and start a narrower run if more work is needed.</p>'
        body+='<h2>Action record</h2>'
        for a in r['actions']:
            verification=json.loads(a['verification_json'] or '{}');result=json.loads(a['result_json'] or '{}')
            body+='<section class="card"><span class="badge">'+E(a['status'].replace('_',' '))+'</span><h3>Step '+str(a['ordinal'])+': '+E(a['tool'] or 'Choose next action / finish')+'</h3><p>'+E(a['rationale'])+'</p><p>'+E(verification.get('reason','No verified result recorded yet'))+'</p><details><summary>Inputs and observation</summary><pre>'+E(json.dumps({'arguments':json.loads(a['arguments_json']),'observation':result,'verification':verification},ensure_ascii=False,indent=2)[:30000])+'</pre></details>'
            if result.get('download_url'):body+='<p><a href="'+E(result['download_url'])+'">Download verified saved artifact</a></p>'
            if result.get('url'):body+='<p><a href="'+E(result['url'])+'">Open saved record</a></p>'
            body+='</section>'
        return render(body,'Agent run · '+project['objective'])

    @app.post('/agent-runs/{pid}/control')
    def control(pid:str,version:int=Form(...),action:str=Form(...),note:str=Form('')):
        try:store.control(pid,version,action,note)
        except ValueError as exc:raise HTTPException(409,str(exc)) from exc
        return RedirectResponse('/agent-runs/'+pid,status_code=303)

    @app.get('/agent-runs/{pid}/artifacts/{aid}')
    def artifact(pid:str,aid:str):
        r=get(pid);a=next((a for a in r['actions'] if a['id']==aid and a['status'] in ('succeeded','cached')),None)
        if not a:raise HTTPException(404,'Verified artifact not found')
        data=json.loads(a['result_json'] or '{}')
        try:
            tools.verify_saved(a,r['project']['workstream'])
            if a['tool'] in ('draft.create','research.web'):path,_=p._text(data)
            elif a['tool']=='coding.package':
                from superhuman.capabilities import coding
                folder,_=coding.session(r['project']['workstream'],data['session_id']);path=folder/'events'/data['filename']
            else:raise ValueError('Use the original saved-record link for this tool')
        except (ValueError,OSError,KeyError) as exc:raise HTTPException(409,str(exc)) from exc
        return FileResponse(path,filename=Path(path).name)
