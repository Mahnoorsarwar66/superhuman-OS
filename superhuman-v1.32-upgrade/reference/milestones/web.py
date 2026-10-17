"""Project leadership and milestone workspace within the existing Projects section."""
import json
from fastapi import Form,HTTPException
from fastapi.responses import RedirectResponse,Response
from superhuman.projects import engine as p
from superhuman.team import store as team
from superhuman.experience import store as ux
from superhuman.foundation import storage
from superhuman.workspace.web import render,E,field,hidden,select,link
from superhuman.workspace.presentation import rich
from . import store as s,workflow as w
NAMES=dict(ux.NAMES,owner='Mahnoor')

def fail(exc):raise HTTPException(409,str(exc)) from exc
def go(url):return RedirectResponse(url,status_code=303)
def name(ident):return NAMES.get(ident,ident)
def check(label,key,value,selected=False):return '<label><input type="checkbox" name="'+E(key)+'" value="'+E(value)+'"'+(' checked' if selected else '')+'> '+E(label)+'</label>'
def team_options(key,values,selected=()):return '<fieldset><legend>'+E(key.capitalize())+'</legend>'+''.join(check(name(e),key,e,e in selected) for e in values)+'</fieldset>'
def project_page(pid):
    q=team.project(pid);cfg=s.managed(pid)
    if not cfg:return render('<h1>'+E(q['title'])+'</h1><p>Appoint '+E(name(q['scope']))+' as project lead. Existing unfinished tasks must be organised first.</p><form method="post" action="/project-leadership/attach">'+hidden('project_id',pid)+'<button>Set up milestone leadership</button></form>','Set up project leadership')
    members=s.roster(pid)
    body='<p>'+link('/projects','Projects')+' / Milestone workspace</p><h1>'+E(q['title'])+'</h1><p>'+E(q['objective'])+'</p><p><strong>Project lead: '+E(name(cfg['lead']))+'</strong> · Supervisor: The Twin · Strategic approval: Mahnoor</p><p>Working team: '+E(', '.join(name(e) for e in members))+'</p>'
    body+='<p>'+link('/project-rooms/'+pid,'Project conversations')+' · '+link('/storage','Storage')+'</p>'
    if cfg['hold']:body+='<section class="error"><strong>Inspection required</strong><p>'+E(cfg['hold'])+'</p><form method="post" action="/project-hub/'+pid+'/resume">'+hidden('expected',cfg['version'])+field('What did you inspect or correct?','note','',True)+'<button>Clear hold after inspection</button></form></section>'
    body+='<details'+(' open' if not cfg['enabled'] or q['status']!='active' else '')+'><summary>Project activation and controls</summary><p>Source documents need separate named grants below. Output-sharing consent covers milestone briefs, contributions and approved packets—including private outputs—within this project’s listed team. External actions remain unavailable.</p><form method="post" action="/project-hub/'+pid+'/configure">'+hidden('expected',cfg['version'])+select('Milestone coordination','enabled',[('no','Paused'),('yes','Enabled')],'yes' if cfg['enabled'] else 'no')+check('Share this project’s work briefs and outputs with its listed participants and The Twin','share_outputs','yes',bool(cfg['share_outputs']))+'<button>Save leadership controls</button></form><form method="post" action="/team/projects/'+pid+'/governance">'+hidden('version',q['version'])+select('Project status','status',[(v,v.capitalize()) for v in ('active','paused','complete')],q['status'])+select('Priority','priority',[(v,v) for v in team.PRIORITIES],q['priority'])+select('Action risk','risk',[(v,v.replace('_',' ').capitalize()) for v in team.RISKS],q['risk'])+select('Default sensitivity','sensitivity',[(v,v.capitalize()) for v in team.SENSITIVITIES],q['sensitivity'])+'<p>Strategic milestone approval is always yours, even when routine internal assignments can proceed independently. Private assignments retain the existing public-web restrictions.</p><button>Save project governance</button></form></details>'
    body+='<h2>Milestones</h2>'
    for m in s.listing(pid):
        body+='<article class="card"><span class="badge">'+E(m['state'].replace('_',' '))+'</span><h2>'+link('/milestones/'+m['id'],'M'+str(m['ordinal'])+' · '+m['title'])+'</h2><p>'+E(m['question'])+'</p><p>Working team: '+E(', '.join(name(e) for e in json.loads(m['workers'])))+'</p><p>Integration lead: '+E(name(cfg['lead']))+' · Criteria '+('confirmed' if m['criteria_confirmed'] else 'provisional')+'</p></article>'
    body+='<details><summary>Add a milestone</summary><form method="post" action="/project-hub/'+pid+'/milestones">'+field('Title','title')+field('Business question','question','',True)+field('Deliverable and acceptance criteria','criteria','',True)+team_options('workers',list(ux.NAMES),[cfg['lead']])+team_options('reviewers',[e for e in ux.NAMES if e not in ('twin',cfg['lead'])])+''.join(check('Depends on M'+str(m['ordinal'])+' · '+m['title'],'deps',m['id']) for m in s.listing(pid))+'<button>Add provisional milestone</button></form></details>'
    body+='<h2>Shared project materials</h2><p>Link a current approved Storage version and choose named recipients. Registration, linking and reading are distinct. Source changes or revoked grants require fresh approval.</p>'
    for g in s.materials(pid):
        item=storage.get(g['item_id']);body+='<article class="card"><h3>'+link('/storage/items/'+item['id'],item['title'])+'</h3><p>'+E(g['purpose'].replace('_',' '))+' · Shared Storage v'+str(g['item_version'])+' · '+('Active' if g['active'] else 'Revoked')+'</p><p>'+E(', '.join(name(e) for e in json.loads(g['recipients'])))+'</p><p>'+E(storage.health(item))+(' · Reapprove current version' if item['version']!=g['item_version'] else '')+'</p>'
        if g['active']:body+='<form method="post" action="/project-hub/'+pid+'/materials/revoke">'+hidden('item_id',item['id'])+hidden('expected',g['version'])+'<button class="secondary">Revoke project grant</button></form>'
        body+='</article>'
    available=[r for r in storage.rows() if r['status']=='approved' and (not r['project_id'] or r['project_id']==pid)]
    body+='<details><summary>Link an approved Storage source</summary>'
    if available:body+='<form method="post" action="/project-hub/'+pid+'/materials">'+select('Current Storage source and version','source',[(r['id']+':'+str(r['version']),r['title']+' · '+r['sensitivity']+' · v'+str(r['version'])) for r in available])+select('Purpose','purpose',[('reference','Reference material'),('required_guide','Required endorsement guide (PDF)')])+team_options('recipients',members)+'<button>Approve named project access</button></form>'
    else:body+='<p>'+link('/storage','Add and approve a source in Storage first')+'</p>'
    body+='</details><details><summary>Start a project conversation</summary><form method="post" action="/project-hub/'+pid+'/room">'+select('Agent','employee',[(e,name(e)) for e in members],cfg['lead'])+field('Conversation title','title')+'<button>Create project conversation</button></form></details>'
    return render(body,'Project milestones')

def milestone_page(mid):
    m=s.milestone(mid);cfg=s.managed(m['project_id']);packet=s.packet(mid)
    body='<p>'+link('/project-hub/'+m['project_id'],'Project workspace')+'</p><h1>M'+str(m['ordinal'])+' · '+E(m['title'])+'</h1><p class="badge">'+E(m['state'].replace('_',' '))+'</p><h2>'+E(m['question'])+'</h2><p>Project lead: '+E(name(cfg['lead']))+' · Working team: '+E(', '.join(name(e) for e in json.loads(m['workers'])))+'</p><p>Independent specialist reviewers: '+E(', '.join(name(e) for e in json.loads(m['reviewers'])) or 'None specified')+' · Supervisor: The Twin · Strategic approval: Mahnoor</p>'
    body+='<section class="card"><h2>Acceptance criteria</h2>'+rich(m['criteria'])+'<p>'+('Owner-confirmed criteria' if m['criteria_confirmed'] else 'Provisional: refine planned milestones after Katherine reviews the complete guide.')+'</p>'
    if not m['criteria_confirmed']:body+='<form method="post" action="/milestones/'+mid+'/confirm">'+hidden('expected',m['version'])+'<button>Confirm these criteria</button></form>'
    if m['state']=='planned':body+='<details><summary>Edit the question and criteria before execution</summary><form method="post" action="/milestones/'+mid+'/criteria">'+hidden('expected',m['version'])+field('Business question','question',m['question'],True)+field('Acceptance criteria','criteria',m['criteria'],True)+check('Confirm these criteria','confirmed','yes',bool(m['criteria_confirmed']))+'<button>Save criteria</button></form></details>'
    body+='</section><h2>Dependencies</h2>'
    for dep in json.loads(m['deps']):
        prior=s.milestone(dep);body+='<p>'+link('/milestones/'+dep,'M'+str(prior['ordinal'])+' · '+prior['title'])+' · '+E(prior['state'].replace('_',' '))+'</p>'
    if not json.loads(m['deps']):body+='<p>No prior milestone required.</p>'
    if m['state']=='planned':body+='<section class="card"><h2>Start this milestone</h2><p>This creates linked specialist assignments in the existing task system. Routine internal work can run within current permissions and budget. Each assignment starts with a $5 ceiling and 12 model requests; M1 guide integration allows up to 48 requests and 40 steps for full PDF coverage. These are limits, not spending commitments. Existing risk gates can still require task start approval.</p><form method="post" action="/milestones/'+mid+'/start">'+hidden('expected',m['version'])+'<button>Start approved milestone work</button></form></section>'
    body+='<h2>Assignments</h2>'
    for a in s.assignments(mid):
        body+='<article class="card"><h3>'+link('/team/tasks/'+a['task_id'],a['title'])+'</h3><p>'+E(name(a['owner'])+' · '+a['role']+' · '+a['state'].replace('_',' '))+'</p>'
        if a['role']!='lead' and a['state']=='awaiting_review':body+='<details><summary>Owner review of this contribution</summary><form method="post" action="/milestones/'+mid+'/assignments/'+a['task_id']+'/review">'+hidden('expected',a['version'])+select('Decision','decision',[('accept','Accept contribution'),('revise','Request revision')])+field('Review rationale','note','',True)+'<button>Record my review</button></form></details>'
        body+='</article>'
    if m['state']=='working':
        body+='<details><summary>Add a scoped contributor assignment</summary><p>Use only the approved working team. No new participants or authority are added here.</p><form method="post" action="/milestones/'+mid+'/assignments">'+select('Specialist','employee',[(e,name(e)) for e in json.loads(m['workers']) if e!='twin'])+select('Work-package sensitivity','sensitivity',[(v,v.capitalize()) for v in team.SENSITIVITIES],team.project(m['project_id'])['sensitivity'])+field('Assignment title','title')+field('Instructions','instruction','',True)+field('Acceptance criteria','criteria','',True)+'<button>Add work package</button></form></details>'
        lead=next((a for a in s.assignments(mid) if a['role']=='lead'),None)
        if lead and lead['state']=='awaiting_review':body+='<form method="post" action="/milestones/'+mid+'/submit">'+hidden('expected',m['version'])+'<p>The project lead normally submits automatically. This owner action submits the verified integrated result on their behalf; it does not approve it.</p><button>Submit current packet on the lead’s behalf</button></form>'
    from .pdf import coverage
    guides=coverage(mid)
    if guides:
        body+='<h2>Guide text extraction coverage</h2><p>Coverage records text pages extracted by assignment tools. It does not establish comprehension, interpretation of images or factual verification.</p>'
        for g in guides:body+='<p>'+E(g['title'])+' · '+str(g.get('extracted_pages',0))+'/'+str(g.get('total_pages','?'))+' text pages · '+str(g.get('owner_reviewed_pages',0))+' pages personally reviewed · '+('Coverage satisfied' if g['complete'] else 'Incomplete')+'</p>'+('<p>Missing pages: '+E(', '.join(map(str,g['missing_pages'][:30])))+'</p>' if g.get('missing_pages') else '')
    for g in guides:
        item=storage.get(g['id'])
        body+='<details><summary>Record my inspection of blank or image-only guide pages</summary><p>This is recorded as your review, separately from machine text extraction. Record what the pages contain or why they are intentionally blank.</p><form method="post" action="/milestones/'+mid+'/page-review">'+hidden('item_id',item['id'])+hidden('expected',item['version'])+field('Page numbers, separated by commas','pages')+field('Findings from my inspection','note','',True)+check('I personally inspected these pages','confirmed','yes')+'<button>Record my page review</button></form></details>'
    memo=s.memo(mid)
    if memo:body+='<details><summary>The Twin contribution — author input, not independent approval</summary>'+rich(memo['body'])+'</details>'
    if packet:
        body+='<section class="card"><h2>Consolidated deliverable · Version '+str(packet['version'])+'</h2><p>'+link('/milestones/'+mid+'/packet.txt','Download exact packet text')+'</p>'
        for ex in json.loads(packet['exports']):body+='<p>'+link(ex['url'],'Download '+ex['format'].upper())+'</p>' if ex.get('url') else '<p class="error">'+E(ex['format'].upper()+': '+ex['error'])+'</p>'
        body+=rich(packet['body'])+'</section>'
    if m['state']=='owner_review':body+='<section class="card"><h2>Your strategic decision</h2><p>The Twin has reviewed this packet. Approval applies to this exact version.</p><form method="post" action="/milestones/'+mid+'/approve">'+hidden('expected',m['version'])+hidden('packet_id',m['current_packet'])+check('I reviewed this packet and approve its strategic decisions','confirmed','yes')+field('Decision and any conditions','note','',True)+'<button>Approve milestone</button></form></section>'
    if m['state'] in ('owner_review','needs_owner'):
        body+='<form method="post" action="/milestones/'+mid+'/owner-revision">'+hidden('expected',m['version'])+field('What should change?','note','',True)+'<button>Request a revision</button></form>'
    if m['state']=='needs_owner':body+='<details><summary>Continue after inspecting the escalation</summary><form method="post" action="/milestones/'+mid+'/continue">'+hidden('expected',m['version'])+field('Inspection decision','note','',True)+'<button>Return to the appropriate work/review stage</button></form></details>'
    body+='<h2>Review and decision history</h2>'
    for r in s.read('milestone_reviews','SELECT * FROM milestone_reviews WHERE milestone_id=? ORDER BY created_at DESC LIMIT 30',(mid,)):body+='<article class="card"><strong>'+E(name(r['actor'])+' · '+r['decision'].replace('_',' '))+'</strong><p>'+E(r['note'])+'</p><small>'+E(r['created_at'])+'</small></article>'
    body+='<details><summary>Previous packet versions</summary>'
    for r in s.read('milestone_packets','SELECT id,version,created_at FROM milestone_packets WHERE milestone_id=? ORDER BY version DESC',(mid,)):body+='<p>'+link('/milestones/'+mid+'/packets/'+r['id'],'Version '+str(r['version']))+' · '+E(r['created_at'])+'</p>'
    return render(body+'</details>','Milestone '+str(m['ordinal']))

def install(app):
    @app.get('/project-leadership')
    def projects():
        body='<h1>Project leadership & milestones</h1><p>Specialists lead projects, The Twin supervises, and Mahnoor approves strategic milestones.</p>'
        configs=s.read('milestone_projects','SELECT * FROM milestone_projects')
        for cfg in configs:
            q=team.project(cfg['project_id']);ms=s.listing(q['id']);body+='<section class="card"><h2>'+link('/project-hub/'+q['id'],q['title'])+'</h2><p>Lead: '+E(name(cfg['lead']))+' · '+str(sum(m['state']=='approved' for m in ms))+'/'+str(len(ms))+' milestones approved · '+E(q['status'])+'</p></section>'
        if not configs:body+='<p>No milestone projects prepared yet.</p><form method="post" action="/project-leadership/endorsement"><button>Prepare the paused endorsement blueprint</button></form>'
        body+='<details><summary>Set up leadership for another existing project</summary><form method="post" action="/project-leadership/attach">'+select('Project','project_id',[(q['id'],q['title']) for q in team.projects() if not s.managed(q['id'])])+'<button>Appoint department lead</button></form></details>'
        return render(body,'Milestone projects')
    @app.post('/project-leadership/endorsement')
    def blueprint():return go('/project-hub/'+s.seed_endorsement())
    @app.post('/project-leadership/attach')
    def attach(project_id:str=Form(...)):
        try:s.attach(project_id,team.project(project_id)['scope'])
        except ValueError as exc:fail(exc)
        return go('/project-hub/'+project_id)
    @app.get('/project-hub/{pid}')
    def project(pid:str):
        try:return project_page(pid)
        except ValueError as exc:fail(exc)
    @app.post('/project-hub/{pid}/configure')
    def configure(pid:str,expected:int=Form(...),enabled:str=Form(...),share_outputs:str=Form('')):
        try:
            if enabled not in ('yes','no') or share_outputs not in ('','yes'):raise ValueError('Choose valid controls')
            s.configure(pid,expected,enabled=='yes',share_outputs=='yes')
        except ValueError as exc:fail(exc)
        return go('/project-hub/'+pid)
    @app.post('/project-hub/{pid}/resume')
    def resume(pid:str,expected:int=Form(...),note:str=Form(...)):
        try:s.resume(pid,expected,note)
        except ValueError as exc:fail(exc)
        return go('/project-hub/'+pid)
    @app.post('/project-hub/{pid}/milestones')
    def add(pid:str,title:str=Form(...),question:str=Form(...),criteria:str=Form(...),workers:list[str]=Form([]),reviewers:list[str]=Form([]),deps:list[str]=Form([])):
        try:mid=s.add(pid,title,question,criteria,workers,reviewers,deps)
        except ValueError as exc:fail(exc)
        return go('/milestones/'+mid)
    @app.post('/project-hub/{pid}/materials')
    def share(pid:str,source:str=Form(...),recipients:list[str]=Form([]),purpose:str=Form('reference')):
        try:
            ident,version=source.split(':',1);s.share(pid,ident,int(version),recipients,purpose)
        except ValueError as exc:fail(exc)
        return go('/project-hub/'+pid)
    @app.post('/project-hub/{pid}/materials/revoke')
    def revoke(pid:str,item_id:str=Form(...),expected:int=Form(...)):
        try:s.revoke(pid,item_id,expected)
        except ValueError as exc:fail(exc)
        return go('/project-hub/'+pid)
    @app.post('/project-hub/{pid}/room')
    def room(pid:str,employee:str=Form(...),title:str=Form(...)):
        try:
            if not s.managed(pid) or not s.managed(pid)['share_outputs'] or employee not in s.roster(pid):raise ValueError('Confirm project output sharing and choose a participant')
            ident=ux.create(employee,title,'team',pid)
        except ValueError as exc:fail(exc)
        return go('/team-room/'+ident)
    @app.get('/milestones/{mid}')
    def milestone(mid:str):
        try:return milestone_page(mid)
        except ValueError as exc:fail(exc)
    @app.post('/milestones/{mid}/start')
    def start(mid:str,expected:int=Form(...)):
        try:s.start(mid,expected)
        except ValueError as exc:fail(exc)
        return go('/milestones/'+mid)
    @app.post('/milestones/{mid}/criteria')
    def criteria(mid:str,expected:int=Form(...),question:str=Form(...),criteria:str=Form(...),confirmed:str=Form('')):
        try:s.edit(mid,expected,question,criteria,confirmed=='yes')
        except ValueError as exc:fail(exc)
        return go('/milestones/'+mid)
    @app.post('/milestones/{mid}/confirm')
    def confirm(mid:str,expected:int=Form(...)):
        try:s.confirm_criteria(mid,expected)
        except ValueError as exc:fail(exc)
        return go('/milestones/'+mid)
    @app.post('/milestones/{mid}/assignments')
    def assign(mid:str,employee:str=Form(...),title:str=Form(...),instruction:str=Form(...),criteria:str=Form(...),sensitivity:str=Form('internal')):
        try:
            if not s.active(mid)[0] or s.milestone(mid)['state']!='working':raise ValueError('Work packages require an active working milestone')
            s.create_assignment(mid,employee,title,instruction,criteria,sensitivity_override=sensitivity)
        except ValueError as exc:fail(exc)
        return go('/milestones/'+mid)
    @app.post('/milestones/{mid}/assignments/{tid}/review')
    def review(mid:str,tid:str,expected:int=Form(...),decision:str=Form(...),note:str=Form(...)):
        try:
            if decision not in ('accept','revise') or not s.assignment(tid) or s.assignment(tid)['milestone_id']!=mid:raise ValueError('Choose the current milestone contribution')
            w.review_assignment(tid,expected,decision=='accept',note,'owner')
        except ValueError as exc:fail(exc)
        return go('/milestones/'+mid)
    @app.post('/milestones/{mid}/submit')
    def submit(mid:str,expected:int=Form(...)):
        try:w.submit(mid,expected,actor='owner')
        except ValueError as exc:fail(exc)
        return go('/milestones/'+mid)
    @app.post('/milestones/{mid}/approve')
    def approve(mid:str,expected:int=Form(...),packet_id:str=Form(...),note:str=Form(...),confirmed:str=Form('')):
        try:
            if confirmed!='yes':raise ValueError('Confirm review of this exact packet before strategic approval')
            w.approve(mid,expected,packet_id,note)
        except ValueError as exc:fail(exc)
        return go('/milestones/'+mid)
    @app.post('/milestones/{mid}/owner-revision')
    def revise(mid:str,expected:int=Form(...),note:str=Form(...)):
        try:w.request_owner_revision(mid,expected,note)
        except ValueError as exc:fail(exc)
        return go('/milestones/'+mid)
    @app.post('/milestones/{mid}/continue')
    def inspect(mid:str,expected:int=Form(...),note:str=Form(...)):
        try:s.continue_after_inspection(mid,expected,note)
        except ValueError as exc:fail(exc)
        return go('/milestones/'+mid)
    @app.get('/milestones/{mid}/packet.txt')
    def download(mid:str):
        try:packet=w.verify_packet(mid)
        except ValueError as exc:fail(exc)
        return Response(packet['body'],media_type='text/plain',headers={'Content-Disposition':'attachment; filename="milestone-packet-v'+str(packet['version'])+'.txt"'})
    @app.get('/milestones/{mid}/packets/{ident}')
    def history(mid:str,ident:str):
        records=s.read('milestone_packets','SELECT * FROM milestone_packets WHERE id=? AND milestone_id=?',(ident,mid))
        if not records:raise HTTPException(404,'Packet not found')
        packet=records[0]
        return render('<h1>Packet version '+str(packet['version'])+'</h1><p>Historical snapshot; this page cannot approve a milestone.</p>'+link('/milestones/'+mid,'Current milestone')+rich(packet['body']),'Packet history')

    @app.post('/milestones/{mid}/page-review')
    def page_review(mid:str,item_id:str=Form(...),expected:int=Form(...),pages:str=Form(...),note:str=Form(...),confirmed:str=Form('')):
        try:
            from .pdf import record_owner_page_review
            m=s.milestone(mid)
            if confirmed!='yes' or not any(g['item_id']==item_id and g['active'] for g in s.materials(m['project_id'])):raise ValueError('Confirm personal inspection of a linked guide')
            record_owner_page_review(item_id,expected,[int(n.strip()) for n in pages.split(',')],note)
        except ValueError as exc:fail(exc)
        return go('/milestones/'+mid)
