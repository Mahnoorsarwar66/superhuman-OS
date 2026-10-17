"""Evidence and outcome workspaces inside the existing project navigation."""
import json
from fastapi import Form,HTTPException
from fastapi.responses import RedirectResponse
from superhuman.team import store as team
from superhuman.foundation import storage
from superhuman.milestones import store as ms
from superhuman.workspace.web import render,E,field,hidden,select,link
from superhuman.milestones.web import check
from . import store as s,evidence as ev,workflow as flow,investigations as gaps,outcomes

def go(url):return RedirectResponse(url,status_code=303)
def fail(exc):raise HTTPException(409,str(exc)) from exc

def impact_summary(pid):
    items=[c for c in s.changes(pid) if c['state']=='open']
    if not items:return ''
    body='<section class="card"><h2>Changes needing your decision</h2><p>Affected work is blocked until you inspect the change. Historical approvals and packets remain visible.</p>'
    for c in items:
        body+='<article><h3>'+E(c['reason'])+'</h3><p>Affects '+E(', '.join('M'+str(ms.milestone(mid)['ordinal']) for mid in json.loads(c['affected'])))+'</p><form method="post" action="/project-hub/'+pid+'/changes/'+c['id']+'/reopen">'+hidden('expected',c['version'])+field('My impact assessment and revision instruction','note','',True)+check('Reopen the affected completed work and require fresh reviews','confirmed','yes')+'<button>Apply change and reopen affected milestones</button></form></article>'
    return body+'</section>'

def milestone_summary(mid):
    if not s.policy(mid):return ''
    return '<section class="card"><h2>Evidence & quality</h2><p>'+str(len(s.requirements(mid)))+' requirements · '+str(sum(g['state'] not in ('resolved','deferred') for g in s.gaps(mid)))+' open investigations · '+('Register scope confirmed' if s.policy(mid)['register_confirmed'] else 'Register scope needs your review')+'</p>'+link('/milestones/'+mid+'/evidence','Open requirements, evidence & scorecards')+'</section>'

def evidence_page(mid):
    m=ms.milestone(mid)
    cfg=s.policy(mid)
    if not cfg:raise ValueError('Run v1.32 setup before using the evidence register')
    flow.reconcile(mid)
    body='<p>'+link('/milestones/'+mid,'Milestone')+' · '+link('/project-hub/'+m['project_id'],'Project')+'</p><h1>M'+str(m['ordinal'])+' · Evidence & quality</h1><p>Quotes and hashes identify sources. The lead evaluates relevance; specialists and The Twin review quality; strategic approval stays with you.</p>'
    if cfg['legacy']:body+='<p>Existing approval retained from v1.31. It is historical and has not been retrospectively verified against this new register.</p>'
    body+=impact_summary(m['project_id'])
    body+='<section class="card"><h2>Requirement register</h2><p>'+('Scope confirmed' if cfg['register_confirmed'] else 'Scope provisional')+'</p><form method="post" action="/milestones/'+mid+'/register/confirm">'+hidden('expected',cfg['version'])+field('Scope decision, or why no separate requirements are needed','note','',True)+'<button>Confirm register scope</button></form></section>'
    reqs=s.requirements(mid);all_ev=s.evidence(mid)
    for r in reqs:
        accepted=[e for e in all_ev if e['requirement_id']==r['id'] and e['status']=='accepted' and ev.health(e,mid)=='Current']
        body+='<article class="card"><h3>'+E(r['requirement_key']+' · '+r['title'])+'</h3><p>'+('Critical' if r['critical'] else 'Supporting')+' · '+E(r['sensitivity'])+' · '+('Current accepted evidence' if accepted else 'Not supported by accepted current evidence')+'</p><p>Origin: '+E(r['origin'])+'</p><details><summary>Change this requirement</summary><form method="post" action="/milestones/'+mid+'/requirements/'+r['id']+'/edit">'+hidden('expected',r['version'])+field('Requirement','title',r['title'],True)+field('Origin / locator','origin',r['origin'],True)+check('Critical','critical','yes',bool(r['critical']))+field('Reason for the change','note','',True)+'<button>Save requirement change</button></form></details>'
        for e in [e for e in all_ev if e['requirement_id']==r['id']]:
            body+='<details><summary>'+E(e['status'].capitalize()+' · '+e['kind']+' · '+ev.health(e,mid))+'</summary><blockquote>'+E(e['quote'])+'</blockquote><p>'+E(e['locator'])+'</p><p>'+E(e['interpretation'])+'</p><p>Source: '+link('/storage/items/'+e['source_id'] if e['kind']=='storage' else '/team/tasks/'+e['source_id'],e['source_id'])+' · v'+str(e['source_version'])+'</p><p>'+E(e['review_note'])+'</p><form method="post" action="/milestones/'+mid+'/evidence/'+e['id']+'/review">'+hidden('expected',e['version'])+select('Evidence decision','decision',[(v,v.capitalize()) for v in ('accepted','rejected','contested')])+field('Why does this support or challenge the requirement?','note','',True)+'<button>Record evidence judgment</button></form></details>'
        body+='</article>'
    body+='<details><summary>Add a requirement</summary><form method="post" action="/milestones/'+mid+'/requirements">'+field('Stable key','key')+field('Requirement','title','',True)+field('Origin / guide page or decision','origin','',True)+select('Sensitivity','sensitivity',[(v,v.capitalize()) for v in team.SENSITIVITIES],team.project(m['project_id'])['sensitivity'])+check('Critical to acceptance','critical','yes',True)+'<button>Add provisional requirement</button></form></details>'
    if reqs:
        choices=[(i['id'],i['title']) for i in storage.rows() if i['status']=='approved' and (not i['project_id'] or i['project_id']==m['project_id'])]
        choices += [(a['task_id'],a['title']) for other in ms.listing(m['project_id']) if other['id']==mid or other['state']=='approved' for a in ms.assignments(other['id']) if a['state']=='completed']
        body+='<details><summary>Link exact source evidence</summary><p>Source access for the lead and The Twin must already be approved. Task sources are accepted outputs, not automatically primary-source verification.</p><form method="post" action="/milestones/'+mid+'/evidence">'+select('Requirement','requirement_id',[(r['id'],r['requirement_key']) for r in reqs])+select('Source type','kind',[('storage','Approved Storage source'),('task','Accepted milestone task')])+select('Source','source_id',choices)+field('Exact quotation','quote','',True)+field('Page / section / locator','locator')+field('Interpretation and limits','interpretation','',True)+'<button>Propose evidence</button></form></details>'
    body+='<h2>Research investigations</h2>'
    for g in s.gaps(mid):
        body+='<article class="card"><h3>'+E(g['gap_key'])+'</h3><p>'+E(g['question'])+'</p><p>'+E(g['state'].replace('_',' '))+' · '+E(team.EMPLOYEES[g['employee']][0])+' · '+('Critical' if g['critical'] else 'Supporting')+' · '+E(g['sensitivity'])+'</p><p>'+E(g['note'])+'</p>'
        if g['state']=='needs_owner' and not g['task_id']:body+='<form method="post" action="/milestones/'+mid+'/gaps/'+g['id']+'/retry">'+hidden('expected',g['version'])+field('What did I correct before retrying?','note','',True)+'<button>Retry investigation after inspection</button></form>'
        if g['task_id']:body+='<p>'+link('/team/tasks/'+g['task_id'],'Investigation assignment')+'</p>'
        if g['state']=='open' and not g['critical']:body+='<form method="post" action="/milestones/'+mid+'/gaps/'+g['id']+'/defer">'+hidden('expected',g['version'])+field('Reason to defer','note','',True)+'<button>Defer supporting investigation</button></form>'
        body+='</article>'
    body+='<details><summary>Add an investigation</summary><form method="post" action="/milestones/'+mid+'/gaps">'+field('Stable gap key','key')+field('Question to investigate','question','',True)+select('Approved specialist','employee',[(e,team.EMPLOYEES[e][0]) for e in json.loads(m['workers']) if e!='twin'])+select('Sensitivity','sensitivity',[(v,v.capitalize()) for v in team.SENSITIVITIES],team.project(m['project_id'])['sensitivity'])+check('Critical to acceptance','critical','yes',True)+'<button>Record research gap</button></form></details><p>While the milestone is working, the worker assigns one eligible investigation at a time. Existing task limits, risk controls and budgets apply. Started integration work requires owner inspection rather than a silent dependency change.</p>'
    body+='<h2>Quality rubric & scorecards</h2>'
    for r in s.rubric(mid):body+='<details><summary>'+E(r['criterion'].capitalize())+'</summary><p>'+E(r['description'])+'</p><form method="post" action="/milestones/'+mid+'/rubric">'+hidden('criterion',r['criterion'])+hidden('expected',r['version'])+field('Acceptance standard','description',r['description'],True)+'<button>Save review standard</button></form></details>'
    packet=ms.packet(mid)
    if packet:
        for c in s.records('assurance_scorecards','SELECT * FROM assurance_scorecards WHERE mid=? AND packet_id=? ORDER BY created_at',(mid,packet['id'])):
            body+='<article class="card"><h3>'+E(team.EMPLOYEES[c['actor']][0])+' · current packet</h3>'
            for row in json.loads(c['scores']):body+='<p><strong>'+E(row['criterion']+' · '+row['verdict'])+'</strong>: '+E(row['rationale'])+'</p>'
            body+='</article>'
    body+='<details><summary>Change the milestone question or acceptance criteria</summary><p>This records an impact decision and blocks affected packets until you apply the change. Existing packets stay in history.</p><form method="post" action="/milestones/'+mid+'/scope">'+hidden('expected',m['version'])+field('Question','question',m['question'],True)+field('Criteria','criteria',m['criteria'],True)+field('Reason','note','',True)+'<button>Record scope change</button></form></details><details><summary>Evidence and change history</summary>'
    for h in s.records('assurance_history','SELECT * FROM assurance_history WHERE mid=? ORDER BY seq DESC LIMIT 50',(mid,)):body+='<p>'+E(h['actor']+' · '+h['event']+' · '+h['created_at'])+'</p><pre>'+E(h['detail'])+'</pre>'
    return render(body+'</details>','Evidence & quality')

def outcomes_page(pid):
    q=team.project(pid)
    if not ms.managed(pid):raise ValueError('Choose a milestone project')
    body='<p>'+link('/project-hub/'+pid,'Project workspace')+'</p><h1>Initiatives & outcome review</h1><p>'+E(q['title'])+'</p><p>Proposals connect to this project. Approval does not start new work, spend money or permit external action. Measurements show observed change; they do not establish causation or ROI.</p>'
    for i in outcomes.initiatives(pid):
        body+='<section class="card"><h2>'+E(i['title'])+'</h2><p>'+E(i['hypothesis'])+'</p><p>'+E(i['status'])+'</p>'
        if i['source_kind']:body+='<p>Linked '+E(i['source_kind'])+': '+E(i['source_id'])+'</p>'
        if i['status']=='proposed':body+='<form method="post" action="/project-hub/'+pid+'/initiatives/'+i['id']+'/decide">'+hidden('expected',i['version'])+select('Decision','decision',[('approved','Approve initiative'),('rejected','Reject initiative')])+field('Rationale','note','',True)+'<button>Record initiative decision</button></form>'
        for metric in outcomes.metrics(i['id']):
            status=outcomes.summary(metric['id']);body+='<article><h3>'+E(metric['name'])+'</h3><p>Baseline '+E(metric['baseline'])+' → target '+E(metric['target'])+' '+E(metric['unit'])+' · review '+E(metric['due'])+(' · Review due' if status['due_for_review'] else '')+'</p>'
            if status['latest']:body+='<p>Latest accepted observation: '+E(status['latest']['value'])+' · change '+E(status['change'])+' · '+('Target reached' if status['target_met'] else 'Target not reached')+'</p>'
            else:body+='<p>No current accepted observation.</p>'
            for o in outcomes.observations(metric['id']):
                body+='<details><summary>'+E(o['observed_on']+' · '+o['value']+' · '+o['status'])+'</summary><blockquote>'+E(o['quote'])+'</blockquote><p>'+E(o['note'])+'</p>'
                if o['status']=='proposed':body+='<form method="post" action="/project-hub/'+pid+'/observations/'+o['id']+'/accept"><button>Accept measurement after checking its source and method</button></form>'
                body+='</details>'
            sources=[r for r in storage.rows() if r['status']=='approved' and (not r['project_id'] or r['project_id']==pid)]
            body+='<details><summary>Add an observation</summary><form method="post" action="/project-hub/'+pid+'/metrics/'+metric['id']+'/observe">'+field('Observed numeric value','value')+field('Observation date (YYYY-MM-DD)','observed_on')+select('Approved Storage evidence','source_id',[(r['id'],r['title']) for r in sources])+field('Exact source quotation','quote','',True)+field('Measurement method and limitations','note','',True)+'<button>Propose observation</button></form></details></article>'
        if i['status']=='approved':body+='<details><summary>Define an outcome baseline</summary><form method="post" action="/project-hub/'+pid+'/initiatives/'+i['id']+'/metrics">'+field('Metric','name')+field('Unit','unit')+field('Baseline','baseline')+field('Target','target')+field('Review date (YYYY-MM-DD)','due')+select('Improvement direction','direction',[('increase','Increase'),('decrease','Decrease')])+'<button>Save baseline and target</button></form></details>'
        body+='</section>'
    body+='<details><summary>Propose an initiative for this project</summary><form method="post" action="/project-hub/'+pid+'/initiatives">'+field('Stable key','key')+field('Title','title')+field('Expected outcome and rationale','hypothesis','',True)+select('Optional existing source','source_kind',[('','No linked source'),('signal','Project proactive signal'),('suggestion','Project conversation suggestion')])+'<label>Existing source ID (optional)<input name="source_id"></label><button>Save initiative proposal</button></form></details>'
    return render(body,'Initiatives & outcomes')

def install(app):
    @app.get('/milestones/{mid}/evidence')
    def register(mid:str):
        try:return evidence_page(mid)
        except ValueError as exc:fail(exc)
    @app.get('/project-hub/{pid}/outcomes')
    def outcome(pid:str):
        try:return outcomes_page(pid)
        except ValueError as exc:fail(exc)
    @app.post('/milestones/{mid}/requirements')
    def requirement(mid:str,key:str=Form(...),title:str=Form(...),origin:str=Form(...),critical:str=Form(''),sensitivity:str=Form(...)):
        try:s.add_requirement(mid,key,title,critical=='yes',origin,sensitivity=sensitivity)
        except ValueError as exc:fail(exc)
        return go('/milestones/'+mid+'/evidence')
    @app.post('/milestones/{mid}/register/confirm')
    def confirm(mid:str,expected:int=Form(...),note:str=Form(...)):
        try:s.confirm(mid,expected,note)
        except ValueError as exc:fail(exc)
        return go('/milestones/'+mid+'/evidence')
    @app.post('/milestones/{mid}/requirements/{ident}/edit')
    def edit(mid:str,ident:str,expected:int=Form(...),title:str=Form(...),critical:str=Form(''),origin:str=Form(...),note:str=Form(...)):
        try:
            if ident not in {r['id'] for r in s.requirements(mid)}:raise ValueError('Requirement belongs to another milestone')
            s.revise_requirement(ident,expected,title,critical=='yes',origin,note)
        except ValueError as exc:fail(exc)
        return go('/milestones/'+mid+'/evidence')
    @app.post('/milestones/{mid}/evidence')
    def evidence(mid:str,requirement_id:str=Form(...),kind:str=Form(...),source_id:str=Form(...),quote:str=Form(...),locator:str=Form(...),interpretation:str=Form(...)):
        try:
            if requirement_id not in {r['id'] for r in s.requirements(mid)}:raise ValueError('Requirement belongs to another milestone')
            ev.add(requirement_id,kind,source_id,quote,locator,interpretation)
        except ValueError as exc:fail(exc)
        return go('/milestones/'+mid+'/evidence')
    @app.post('/milestones/{mid}/evidence/{ident}/review')
    def review(mid:str,ident:str,expected:int=Form(...),decision:str=Form(...),note:str=Form(...)):
        try:
            if ident not in {r['id'] for r in s.evidence(mid)}:raise ValueError('Evidence belongs to another milestone')
            ev.review(ident,expected,decision,note)
        except ValueError as exc:fail(exc)
        return go('/milestones/'+mid+'/evidence')
    @app.post('/milestones/{mid}/gaps')
    def gap(mid:str,key:str=Form(...),question:str=Form(...),employee:str=Form(...),critical:str=Form(''),sensitivity:str=Form(...)):
        try:gaps.open_gap(mid,key,question,employee,critical=='yes',sensitivity)
        except ValueError as exc:fail(exc)
        return go('/milestones/'+mid+'/evidence')
    @app.post('/milestones/{mid}/gaps/{ident}/defer')
    def defer(mid:str,ident:str,expected:int=Form(...),note:str=Form(...)):
        try:
            if ident not in {g['id'] for g in s.gaps(mid)}:raise ValueError('Gap belongs to another milestone')
            gaps.deferred_gap(ident,expected,note)
        except ValueError as exc:fail(exc)
        return go('/milestones/'+mid+'/evidence')
    @app.post('/milestones/{mid}/gaps/{ident}/retry')
    def retry(mid:str,ident:str,expected:int=Form(...),note:str=Form(...)):
        try:
            if ident not in {g['id'] for g in s.gaps(mid)}:raise ValueError('Gap belongs to another milestone')
            gaps.retry(ident,expected,note)
        except ValueError as exc:fail(exc)
        return go('/milestones/'+mid+'/evidence')
    @app.post('/milestones/{mid}/rubric')
    def rubric(mid:str,criterion:str=Form(...),expected:int=Form(...),description:str=Form(...)):
        try:s.set_rubric(mid,criterion,description,expected)
        except ValueError as exc:fail(exc)
        return go('/milestones/'+mid+'/evidence')
    @app.post('/milestones/{mid}/scope')
    def scope(mid:str,expected:int=Form(...),question:str=Form(...),criteria:str=Form(...),note:str=Form(...)):
        try:flow.change_criteria(mid,expected,question,criteria,note)
        except ValueError as exc:fail(exc)
        return go('/milestones/'+mid+'/evidence')
    @app.post('/project-hub/{pid}/changes/{ident}/reopen')
    def reopen(pid:str,ident:str,expected:int=Form(...),note:str=Form(...),confirmed:str=Form('')):
        try:
            if confirmed!='yes' or ident not in {c['id'] for c in s.changes(pid)}:raise ValueError('Confirm the affected project change')
            flow.reopen(ident,expected,note)
        except ValueError as exc:fail(exc)
        return go('/project-hub/'+pid)
    @app.post('/project-hub/{pid}/initiatives')
    def initiative(pid:str,key:str=Form(...),title:str=Form(...),hypothesis:str=Form(...),source_kind:str=Form(''),source_id:str=Form('')):
        try:outcomes.propose(pid,key,title,hypothesis,source_kind=source_kind,source_id=source_id)
        except ValueError as exc:fail(exc)
        return go('/project-hub/'+pid+'/outcomes')
    @app.post('/project-hub/{pid}/initiatives/{ident}/decide')
    def decide(pid:str,ident:str,expected:int=Form(...),decision:str=Form(...),note:str=Form(...)):
        try:
            if ident not in {i['id'] for i in outcomes.initiatives(pid)}:raise ValueError('Initiative belongs to another project')
            outcomes.decide(ident,expected,decision,note)
        except ValueError as exc:fail(exc)
        return go('/project-hub/'+pid+'/outcomes')
    @app.post('/project-hub/{pid}/initiatives/{ident}/metrics')
    def metric(pid:str,ident:str,name:str=Form(...),unit:str=Form(...),baseline:str=Form(...),target:str=Form(...),due:str=Form(...),direction:str=Form(...)):
        try:
            if ident not in {i['id'] for i in outcomes.initiatives(pid)}:raise ValueError('Initiative belongs to another project')
            outcomes.add_metric(ident,name,unit,baseline,target,due,direction)
        except ValueError as exc:fail(exc)
        return go('/project-hub/'+pid+'/outcomes')
    @app.post('/project-hub/{pid}/metrics/{ident}/observe')
    def observe(pid:str,ident:str,value:str=Form(...),observed_on:str=Form(...),source_id:str=Form(...),quote:str=Form(...),note:str=Form(...)):
        try:
            if ident not in {m['id'] for i in outcomes.initiatives(pid) for m in outcomes.metrics(i['id'])}:raise ValueError('Metric belongs to another project')
            outcomes.observe(ident,value,observed_on,source_id,quote,note)
        except ValueError as exc:fail(exc)
        return go('/project-hub/'+pid+'/outcomes')
    @app.post('/project-hub/{pid}/observations/{ident}/accept')
    def accept(pid:str,ident:str):
        try:
            if ident not in {o['id'] for i in outcomes.initiatives(pid) for m in outcomes.metrics(i['id']) for o in outcomes.observations(m['id'])}:raise ValueError('Observation belongs to another project')
            outcomes.accept_observation(ident)
        except ValueError as exc:fail(exc)
        return go('/project-hub/'+pid+'/outcomes')
