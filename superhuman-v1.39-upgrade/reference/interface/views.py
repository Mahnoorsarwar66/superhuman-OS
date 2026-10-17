"""Focused server-rendered workspaces over existing records and POST handlers."""
import json
from urllib.parse import urlencode
from superhuman.projects import engine as p
from superhuman.team import store as team
from superhuman.experience import store as ux
from superhuman.milestones import store as ms
from superhuman.workspace import model
from superhuman.workspace.web import render,E,link,hidden,field,select
from .chrome import capture,tab,pill
from .tree import parse,Node,html,text

def header(title,description='',eyebrow='',actions=''):
    return '<header class="ui-page-head"><div>'+('<p class="eyebrow">'+E(eyebrow)+'</p>' if eyebrow else '')+'<h1>'+E(title)+'</h1>'+('<p class="ui-description">'+E(description)+'</p>' if description else '')+'</div>'+('<div class="ui-head-actions">'+actions+'</div>' if actions else '')+'</header>'
def crumbs(items):return '<nav class="ui-breadcrumb" aria-label="Breadcrumb">'+''.join(link(url,label) if url else '<span aria-current="page">'+E(label)+'</span>' for url,label in items)+'</nav>'
def tabs(base,items,chosen):
    return '<nav class="ui-tabs" aria-label="Workspace navigation" data-interface-tabs>'+''.join('<a href="'+E(base+('?' if '?' not in base else '&')+urlencode({'view':key}))+'"'+(' aria-current="page"' if key==chosen else '')+'>'+E(label)+'</a>' for key,label in items)+'</nav>'
def details(title,body,opened=False):return '<details class="ui-disclosure"'+(' open' if opened else '')+'><summary>'+E(title)+'</summary><div>'+body+'</div></details>'
def empty(title,description,action=''):return '<section class="ui-empty"><h2>'+E(title)+'</h2><p>'+E(description)+'</p>'+action+'</section>'
def next_step(title,reason,url,label):return '<section class="ui-next"><div><p class="eyebrow">Next step</p><h2>'+E(title)+'</h2><p>'+E(reason)+'</p></div><a class="button" href="'+E(url)+'">'+E(label)+'</a></section>'
def action_link(url,label):return '<a class="button secondary" href="'+E(url)+'">'+E(label)+'</a>'

def project_summary(pid):
    from superhuman.practice.web import panel
    interview_panel=panel(pid)
    q=team.project(pid);cfg=ms.managed(pid);milestones=ms.listing(pid);tasks=[t for t in team.tasks() if t['project_id']==pid]
    if not cfg:
        body='<div class="ui-facts"><div><span>Project lead</span><strong>'+E(ux.NAMES[q['scope']])+'</strong></div><div><span>Open assignments</span><strong>'+str(sum(t['state'] not in ('completed','cancelled') for t in tasks))+'</strong></div><div><span>Project status</span><strong>'+E(model.label(q['status']))+'</strong></div></div>'
        body+=next_step('Review the work plan','Tasks inherit this project’s controls and remain linked to its outcome.','/team/projects/'+pid+'?view=work','Open work plan')
        return interview_panel+body+'<p>'+link('/project-briefs/'+pid+'/impact','Milestone impact')+'</p>'
    done=sum(m['state']=='approved' for m in milestones);body='<div class="ui-facts"><div><span>Project lead</span><strong>'+E(ux.NAMES[q['scope']])+'</strong></div><div><span>Supervisor</span><strong>The Twin</strong></div><div><span>Milestones approved</span><strong>'+str(done)+' / '+str(len(milestones))+'</strong></div><div><span>Open assignments</span><strong>'+str(sum(t['state'] not in ('completed','cancelled') for t in tasks))+'</strong></div></div>'
    if cfg and (not cfg['enabled'] or not cfg['share_outputs'] or q['status']!='active'):
        body+=next_step('Review project readiness','Check activation and project sharing before starting work.','/project-hub/'+pid+'?view=manage','Manage project')
    else:
        waiting=next((m for m in milestones if m['state'] in ('owner_review','needs_owner')),None)
        current=waiting or next((m for m in milestones if m['state']!='approved'),None)
        if current:
            body+=next_step(current['title'],'Review the current milestone and its next required action.','/milestones/'+current['id']+('?view=reviews' if waiting else ''),'Review milestone' if waiting else 'Open milestone')
        elif milestones:body+=empty('Milestones approved','Review the outcome and decide whether the overall project can be marked complete.','<p>'+link('/project-hub/'+pid+'/outcomes','Review outcomes')+'</p>')
        else:body+=next_step('Plan the work','Define milestones or assign the first bounded task.','/team/projects/'+pid+'?view=work','Open work plan')
    body+='<section class="ui-section"><div class="row"><h2>Milestone progress</h2>'+link('/project-hub/'+pid+'?view=work','View work plan')+'</div>'
    for m in milestones:
        body+='<article class="ui-list-row"><div><small>Milestone '+str(m['ordinal'])+'</small><h3>'+link('/milestones/'+m['id'],m['title'])+'</h3><p>'+E(', '.join(ux.NAMES[e] for e in json.loads(m['workers'])))+'</p></div>'+pill(m['state'])+'</article>'
    if not milestones:body+='<p class="muted">No milestones defined.</p>'
    return interview_panel+body+'</section><div class="ui-quick-links">'+action_link('/project-briefs/'+pid+'/impact','Milestone impact')+action_link('/project-hub/'+pid+'/outcomes','Initiatives & outcomes')+action_link('/project-hub/'+pid+'?view=conversations','Project conversations')+'</div>'

def project_activity(pid):
    mids={m['id'] for m in ms.listing(pid)};tasks={t['id'] for t in team.tasks() if t['project_id']==pid};items=[]
    for r in ms.read('team_events','SELECT * FROM team_events ORDER BY seq DESC LIMIT 2000'):
        try:d=json.loads(r['detail_json'])
        except (TypeError,ValueError):continue
        if any(d.get(k) in {pid}|mids|tasks for k in ('project_id','task_id','milestone_id','mid','id') if isinstance(d.get(k),str)):
            items.append('<article class="ui-timeline-row"><strong>'+E(r['action'].replace('_',' ').capitalize())+'</strong><p>'+E(ux.NAMES.get(r['actor'],r['actor']))+' · '+E(__import__('superhuman.workspace.web',fromlist=['stamp']).stamp(r['created_at']))+'</p>'+details('Record details','<pre>'+E(json.dumps(d,indent=2,ensure_ascii=False))+'</pre>')+'</article>')
    return '<h2>Project activity</h2><p class="muted">Latest 100 matching records from the latest 2,000 team events. Execution logs remain available in each task.</p>'+(''.join(items[:100]) if items else empty('No activity recorded','Actions and decisions will appear here as work progresses.'))

def project(pid,legacy):
    q=team.project(pid);cfg=ms.managed(pid)
    if not cfg:return simple_project(pid)
    chosen=tab('view',('summary','work','files','conversations','activity','manage'),'summary')
    nodes=parse(capture(legacy,pid)).children;parts={k:[] for k in ('work','files','conversations','manage','alerts')};mode=None
    for node in nodes:
        if not isinstance(node,Node):
            if mode:parts[mode].append(node)
            continue
        label=text(node)
        if node.tag=='details' and node.find('summary') and text(node.find('summary')[0])=='Project activation and controls':parts['manage'].append(node);continue
        if node.has_class('error') or node.tag=='section' and node.find('h2') and text(node.find('h2')[0])=='Changes needing your decision':parts['alerts'].append(node);continue
        if node.tag=='h2' and label=='Milestones':mode='work';continue
        if node.tag=='h2' and label=='Shared project materials':mode='files';continue
        if node.tag=='details' and node.find('summary') and text(node.find('summary')[0])=='Start a project conversation':parts['conversations'].append(node);continue
        if mode:parts[mode].append(node)
    body=crumbs([('/projects','Projects'),('',q['title'])])+header(q['title'],q['objective'],ux.ROLES[q['scope']],action_link('/project-hub/'+pid+'?view=manage','Manage'))
    body+='<div class="ui-meta">'+pill(q['status'])+'<span>'+E(q['priority'])+'</span><span>Lead: '+E(ux.NAMES[cfg['lead']])+'</span></div>'
    body+=tabs('/project-hub/'+pid,[('summary','Summary'),('work','Plan & work'),('files','Files & evidence'),('conversations','Conversations'),('activity','Activity'),('manage','Manage')],chosen)
    alerts=html(parts['alerts'])
    if chosen=='summary':body+=alerts+project_summary(pid)
    elif chosen=='work':body+='<h2>Plan & work</h2>'+html(parts['work'])
    elif chosen=='files':body+='<h2>Project files & evidence</h2><p>Approved sources and named access for this project. Each milestone holds its own requirement and evidence register.</p>'+html(parts['files'])
    elif chosen=='conversations':
        from superhuman.workspace.web import project_conversations
        body+='<h2>Project conversations</h2>'+capture(project_conversations,pid,kind='team')
    elif chosen=='activity':body+=project_activity(pid)
    else:body+='<h2>Manage project</h2>'+alerts+html(parts['manage'])+'<p>'+link('/team/budget','Budget & spending controls')+'</p>'
    return render(body,'Project · '+q['title'])

def simple_project(pid):
    q=team.project(pid);chosen=tab('view',('summary','work','files','conversations','activity','manage'),'summary')
    from superhuman.team.web import options,input as control
    body=crumbs([('/projects','Projects'),('',q['title'])])+header(q['title'],q['objective'],ux.ROLES[q['scope']],action_link('/team/projects/'+pid+'?view=manage','Manage'))+tabs('/team/projects/'+pid,[('summary','Summary'),('work','Plan & work'),('files','Files & evidence'),('conversations','Conversations'),('activity','Activity'),('manage','Manage')],chosen)
    if chosen=='summary':body+=project_summary(pid)+'<h2>Success criteria</h2><p>'+E(q['acceptance'])+'</p>'
    elif chosen=='work':
        body+='<div class="row"><h2>Tasks</h2>'+action_link('/new-task?project_id='+pid,'Add task')+action_link('/team/projects/'+pid+'?view=manage','Set up milestones')+'</div>'
        for t in team.tasks():
            if t['project_id']==pid:body+='<article class="ui-list-row"><div><h3>'+link('/team/tasks/'+t['id'],t['title'])+'</h3><p>'+E(ux.NAMES[t['owner']])+'</p></div>'+pill(t['state'])+'</article>'
        body+=details('Assign a specialist task','<form method="post" action="/team/projects/'+pid+'/tasks">'+options('owner',[e for e in team.EMPLOYEES if e!='twin'],q['scope'])+control('Title','title')+control('Instructions (max 5000)','instruction','',True)+control('Acceptance criteria (max 1500)','acceptance','',True)+control('Due date YYYY-MM-DD (optional)','due')+control('Prerequisite task IDs (optional)','deps')+'<button>Create task</button></form>')
    elif chosen=='files':body+='<h2>Project files</h2><p>'+link('/storage/departments/'+q['scope']+'?'+urlencode({'project':pid}),'Open this project’s Storage records')+'</p><p>Milestone evidence registers become available after you set up project leadership.</p>'
    elif chosen=='conversations':
        from superhuman.workspace.web import project_conversations
        body+=capture(project_conversations,pid,kind='team')
    elif chosen=='activity':body+=project_activity(pid)
    else:
        body+='<h2>Manage project</h2><form method="post" action="/team/projects/'+pid+'/governance">'+hidden('version',q['version'])+options('priority',team.PRIORITIES,q['priority'])+options('risk',team.RISKS,q['risk'])+options('sensitivity',team.SENSITIVITIES,q['sensitivity'])+options('status',('active','paused','complete'),q['status'])+'<p>Changing controls invalidates prior start grants. Overall project completion remains your decision.</p><button>Save project controls</button></form>'+details('Set up milestone leadership','<p>The department specialist will lead, The Twin will supervise, and you approve strategic milestones. Review existing unfinished tasks before conversion. <a href="/project-tasks?department='+q['scope']+'">Open department tasks</a>. Tasks are retained; no task is automatically cancelled.</p><form method="post" action="/project-leadership/attach">'+hidden('project_id',pid)+'<button>Appoint department lead</button></form>')
    return render(body,'Project · '+q['title'])

def milestone(mid,legacy):
    m=ms.milestone(mid);cfg=ms.managed(m['project_id']);chosen=tab('view',('deliverable','evidence','reviews','history','manage'),'deliverable')
    if chosen=='evidence':
        from superhuman.assurance.web import evidence_page
        return evidence_page(mid)
    nodes=parse(capture(legacy,mid)).children;parts={k:[] for k in ('work','start','criteria','reviews','history','deliverable','coverage','manage')};mode=None
    for node in nodes:
        if not isinstance(node,Node):
            if mode:parts[mode].append(node)
            continue
        label=text(node);head=node.find('h2');heading=text(head[0]) if head else ''
        if node.tag=='section' and heading=='Acceptance criteria':parts['criteria'].append(node);continue
        if node.tag=='section' and heading=='Start this milestone':parts['start'].append(node);continue
        if node.tag=='h2':
            mode={'Dependencies':'manage','Assignments':'work','Guide text extraction coverage':'coverage','Review and decision history':'history'}.get(label,mode)
            if mode:parts[mode].append(node)
            continue
        if node.tag=='section' and heading.startswith('Consolidated deliverable'):
            head[0].replace_text(heading.replace('Consolidated deliverable','Milestone deliverable',1))
            parts['deliverable'].append(node);continue
        if node.tag=='section' and heading=='Your strategic decision':parts['reviews'].append(node);continue
        if node.tag=='section' and heading=='Evidence & quality':continue
        if node.tag=='details':
            summ=node.find('summary');title=text(summ[0]) if summ else ''
            if title=='Previous packet versions':parts['history'].append(node);continue
            if title.startswith('The Twin contribution'):parts['reviews'].append(node);continue
            if title.startswith('Record my inspection'):parts['coverage'].append(node);continue
            if title.startswith('Continue after inspecting'):parts['reviews'].append(node);continue
        if node.tag=='form':
            actions=[node.attrs.get('action','')]
            if any(a.endswith(('/approve','/owner-revision','/continue')) for a in actions):parts['reviews'].append(node);continue
        if mode:parts[mode].append(node)
    body=milestone_head(mid,chosen)
    if chosen=='deliverable':
        body+=milestone_next(mid)+html(parts['deliverable'])
        if not parts['deliverable']:body+=empty('Deliverable not ready yet','Assignments and their saved status appear below. The lead will assemble the milestone result for review.')
        else:body+='<p class="muted">This is the latest saved version. Its status above determines whether it is awaiting review or approved.</p>'
        body+=html(parts['work'])+details('Success criteria',html(parts['criteria']))
    elif chosen=='reviews':
        body+='<h2>Milestone review</h2>'+html(parts['reviews'])
        from superhuman.assurance import store as assurance
        for c in assurance.records('assurance_scorecards','SELECT * FROM assurance_scorecards WHERE mid=? AND packet_id=? ORDER BY created_at',(mid,m['current_packet'] or '')):
            body+='<article class="card"><h3>'+E(ux.NAMES[c['actor']])+' · Review scorecard</h3>'
            for row in json.loads(c['scores']):body+='<div class="ui-score-row"><strong>'+E(row['criterion'].capitalize())+'</strong>'+pill(row['verdict'])+'<p>'+E(row['rationale'])+'</p></div>'
            body+='</article>'
        if not parts['reviews']:body+=empty('No decision waiting here','Reviews appear when the current deliverable reaches its next approval stage.')
    elif chosen=='history':body+='<h2>Milestone history</h2>'+html(parts['history'])
    else:body+='<h2>Manage milestone</h2>'+html(parts['criteria'])+html(parts['manage'])+html(parts['coverage'])+html(parts['start'])
    return render(body,'Milestone '+str(m['ordinal'])+' · '+m['title'])

def milestone_head(mid,chosen):
    m=ms.milestone(mid);cfg=ms.managed(m['project_id']);q=team.project(m['project_id'])
    return crumbs([('/projects','Projects'),('/project-hub/'+q['id'],q['title']),('','Milestone '+str(m['ordinal']))])+header(m['title'],m['question'],'Milestone '+str(m['ordinal']),action_link('/milestones/'+mid+'?view=manage','Manage'))+'<div class="ui-meta">'+pill(m['state'])+'<span>Lead: '+E(ux.NAMES[cfg['lead']])+'</span><span>The Twin reviews · You approve strategy</span></div>'+tabs('/milestones/'+mid,[('deliverable','Deliverable'),('evidence','Evidence'),('reviews','Reviews'),('history','History'),('manage','Manage')],chosen)

def milestone_next(mid):
    from superhuman.assurance import store as assurance,workflow as af
    m=ms.milestone(mid);cfg=ms.managed(m['project_id']);pol=assurance.policy(mid)
    if af.block_reason(mid):return next_step('Review affected work','An important source or decision changed. Inspect its impact before continuing.','/project-hub/'+m['project_id'],'Review change')
    if cfg['hold']:return next_step('Inspect the project hold',cfg['hold'],'/project-hub/'+m['project_id']+'?view=manage','Inspect hold')
    if m['state'] in ('owner_review','needs_owner'):return next_step('Your review is needed','Open the deliverable and recorded reviews before deciding.','/milestones/'+mid+'?view=reviews','Review milestone')
    if not cfg['enabled'] or not cfg['share_outputs'] or team.project(m['project_id'])['status']!='active':return next_step('Check project readiness','Project activation and sharing must permit work.','/project-hub/'+m['project_id']+'?view=manage','Manage project')
    if m['state']=='planned':return next_step('Review the work before starting','Check the criteria, dependencies and assignment allowance below.','/milestones/'+mid+'?view=manage','Review setup')
    if pol and not pol['register_confirmed']:return next_step('Review requirements','The scope needs your confirmation before a deliverable can be submitted.','/milestones/'+mid+'?view=evidence','Review requirements')
    return '<section class="ui-notice"><strong>'+('Milestone approved' if m['state']=='approved' else 'The team is handling this milestone')+'</strong><p>'+('The approved deliverable and its history remain available.' if m['state']=='approved' else 'Check assignments below or open Evidence for research gaps. No new owner action is inferred from this saved status.')+'</p></section>'

def evidence(mid,legacy):
    from superhuman.assurance import store as assurance
    nodes=parse(capture(legacy,mid)).children;cfg=assurance.policy(mid);m=ms.milestone(mid);parts={k:[] for k in ('requirements','gaps','rubric','manage','history','alerts')};mode=None
    for node in nodes:
        if not isinstance(node,Node):
            if mode:parts[mode].append(node)
            continue
        head=node.find('h2');heading=text(head[0]) if head else '';label=text(node)
        if node.tag=='section' and heading=='Changes needing your decision':parts['alerts'].append(node);continue
        if node.tag=='section' and heading=='Requirement register':
            if cfg['register_confirmed']:
                # Confirmation is a saved status, not a form that should be submitted again.
                node.children=parse('<h2>Requirement scope confirmed</h2><p>The scope has been reviewed. Changes to requirements or review standards require confirmation again.</p>').children
            parts['requirements'].append(node);mode='requirements';continue
        if node.tag=='h2':
            mode={'Research investigations':'gaps','Quality rubric & scorecards':'rubric'}.get(label,mode)
            if mode:parts[mode].append(node)
            continue
        if node.tag=='details':
            summaries=node.find('summary');title=text(summaries[0]) if summaries else ''
            if title.startswith('Change the milestone question'):parts['manage'].append(node);continue
            if title=='Evidence and change history':parts['history'].append(node);continue
        if mode:parts[mode].append(node)
    # Human titles lead; stable keys remain available as reference metadata.
    for requirement in assurance.requirements(mid):
        for node in parts['requirements']:
            if not isinstance(node,Node) or node.tag!='article':continue
            headings=node.find('h3')
            if headings and text(headings[0])==requirement['requirement_key']+' · '+requirement['title']:
                headings[0].replace_text(requirement['title'])
                node.children+=parse(details('Reference details','<p>Reference: '+E(requirement['requirement_key'])+'</p><p>Proposed by: '+E(ux.NAMES.get(requirement['actor'],requirement['actor']))+'</p>')).children
    for investigation in assurance.gaps(mid):
        for node in parts['gaps']:
            if not isinstance(node,Node) or node.tag!='article':continue
            headings=node.find('h3')
            if headings and text(headings[0])==investigation['gap_key']:
                headings[0].replace_text(investigation['question'][:120]+('…' if len(investigation['question'])>120 else ''))
                if len(investigation['question'])<=120:
                    node.children=[child for child in node.children if not (isinstance(child,Node) and child.tag=='p' and text(child)==investigation['question'])]
                node.children+=parse(details('Reference details','<p>Reference: '+E(investigation['gap_key'])+'</p>')).children
    chosen=tab('panel',('requirements','investigations','standards'),'requirements')
    body=milestone_head(mid,'evidence')
    req=assurance.requirements(mid);e=assurance.evidence(mid);g=assurance.gaps(mid)
    supported=sum(any(row['requirement_id']==r['id'] and row['status']=='accepted' for row in e) for r in req)
    body+='<section class="ui-readiness"><h2>Evidence readiness</h2><p>'+str(len(req))+(' requirement' if len(req)==1 else ' requirements')+' · '+str(supported)+' with accepted evidence · '+str(sum(row['state'] not in ('resolved','deferred') for row in g))+' open investigations</p><small>Source freshness and conflicting evidence are checked at the review gates. Acceptance is not proof of factual correctness.</small></section>'
    body+='<div class="ui-subviews" aria-label="Evidence sections">'+''.join('<a href="/milestones/'+mid+'/evidence?panel='+key+'"'+(' aria-current="page"' if chosen==key else '')+'>'+label+'</a>' for key,label in [('requirements','Requirements & sources'),('investigations','Investigations'),('standards','Review standards')])+'</div>'+html(parts['alerts'])
    body+=html(parts[{'requirements':'requirements','investigations':'gaps','standards':'rubric'}[chosen]])
    if chosen=='requirements':body+=details('What this evidence means','<p>Quotations identify the source. The project lead evaluates relevance; independent specialists and The Twin review the deliverable. Your approval is still required for strategic decisions.</p>')
    body+=details('Scope changes & audit records',html(parts['manage'])+html(parts['history']))
    return render(body,'Evidence · '+m['title'])

def overview():
    from superhuman.hosted import jobs
    from superhuman.planning.presentation import overview_panel
    items=model.decisions();projects=model.projects();tasks=model.tasks();worker=jobs.worker_status()
    body=header('Your work, in view','Decisions, progress and the next useful step.','Superhuman',action_link('/twin','Talk with The Twin'))
    from superhuman.practice.web import portrait
    body+='<section class="practice-hero">'+portrait('twin')+'<div><p class="eyebrow">Your Superhuman</p><h2>A clear next step, together.</h2><p>Bring a project, review a decision, or tell The Twin what has changed.</p><div class="ui-quick-links">'+action_link('/new-project','Start a project')+action_link('/operating-guide','How your team works')+'</div></div></section>'
    from superhuman.practice import store as practice
    briefs=[q for q in team.projects() if practice.interview(q['id']) and not practice.current(q['id'])]
    if briefs:
        body+='<section class="practice-callout"><div><h2>Project expectations need your input</h2><p>'+str(len(briefs))+' project briefs need confirmation before their managed work continues.</p></div>'+action_link('/project-briefs/'+briefs[0]['id'],'Continue interview')+'</section>'
    body+='<div class="ui-facts"><div><span>Needs your review</span><strong>'+str(len(items))+'</strong></div><div><span>Active projects</span><strong>'+str(sum(q['status'] in ('active','new','plan_review') for q in projects))+'</strong></div><div><span>Open tasks</span><strong>'+str(sum(t['status'] not in ('completed','approved','cancelled') for t in tasks))+'</strong></div></div>'
    body+='<section class="ui-section"><div class="row"><h2>Needs your decision</h2>'+link('/reviews','View all decisions')+'</div>'
    for item in items[:6]:body+='<article class="ui-list-row"><div><h3>'+link(item['url'],item['title'])+'</h3><p>'+E(item['reason'])+'</p></div>'+action_link(item['url'],'Review')+'</article>'
    if not items:body+=empty('You’re up to date','There are no recorded decisions waiting for you. Review current projects or speak with The Twin.')
    body+='</section><section class="ui-section"><div class="row"><h2>Current projects</h2>'+link('/projects','View all projects')+'</div>'
    for q in projects[:6]:body+='<article class="ui-list-row"><div><h3>'+link(q['url'],q['name'])+'</h3><p>'+E(ux.ROLES.get(q['scope'],q['scope']))+'</p></div>'+pill(q['status'])+'</article>'
    if not projects:body+=empty('Give your team a clear outcome','Create a project to organise its tasks, documents and conversations.',action_link('/new-project','Create project'))
    body+='</section><div class="ui-quick-links">'+action_link('/memory/briefing','Work briefing')+action_link('/briefing','Inbox briefing')+action_link('/new-project','Create project')+'</div>'
    body+=details('Department priorities',overview_panel())
    status='Paused' if worker['paused'] else 'Online' if worker['online'] else 'Offline'
    body+=details('Work status & controls','<p>Background worker: '+E(status)+'. This is saved worker status, not proof of model connectivity.</p><form method="post" action="/worker/pause">'+hidden('paused','false' if worker['paused'] else 'true')+'<button class="secondary">'+('Resume work' if worker['paused'] else 'Pause new work')+'</button></form><p>'+link('/system-baseline','System health')+' · '+link('/proactive','Proactive checks')+'</p>')
    return render(body,'Overview')

def projects(scope='all',q='',state='all',page=1,capability='all'):
    from fastapi import HTTPException
    from superhuman.departments.store import departments
    from superhuman.workspace.web import pager
    if not 1<=page<=10000 or len(q)>200 or capability not in ('all','milestones','standard','earlier'):raise HTTPException(400,'Choose a valid project filter')
    if state=='approved':state='complete'  # Retained bookmarks use the same unified completed view.
    configs={r['project_id'] for r in ms.read('milestone_projects','SELECT project_id FROM milestone_projects')}
    items=[a for a in model.projects() if (scope=='all' or a['scope']==scope) and (state=='all' or a['status']==state or state=='complete' and a['status']=='approved') and (not q or q.casefold() in (a['name']+' '+a['description']).casefold()) and (capability=='all' or capability=='milestones' and a['id'] in configs or capability=='standard' and a['kind']=='team' and a['id'] not in configs or capability=='earlier' and a['kind']=='canonical')]
    body=header('Projects','Outcomes, work and conversations in one place.',actions=action_link('/new-project','Create project'))
    body+='<form class="ui-filters" method="get" action="/projects">'+field('Find a project','q',q).replace(' required','')+select('Department','workstream',[('all','All departments')]+departments(),scope)+select('Status','state',[(v,model.label(v)) for v in ('all','active','paused','complete','new','plan_review')],state)+select('Project type','capability',[('all','All projects'),('milestones','With milestones'),('standard','Task-based'),('earlier','Earlier work')],capability)+'<button class="secondary">Apply filters</button></form><p class="muted">'+str(len(items))+' matching projects</p>'
    for a in items[(page-1)*30:page*30]:
        url='/project-hub/'+a['id'] if a['id'] in configs else a['url']
        body+='<article class="ui-list-row"><div><small>'+E(ux.ROLES.get(a['scope'],a['scope']))+' · '+E(a['priority'])+(' · Milestone project' if a['id'] in configs else ' · Earlier work' if a['kind']=='canonical' else '')+'</small><h2>'+link(url,a['name'])+'</h2><p>'+E(a['description'][:350])+'</p></div>'+pill(a['status'])+'</article>'
    if not items:body+=empty('No matching projects','Clear your filters or create a project with a clear outcome.',action_link('/projects','Clear filters'))
    body+=pager('/projects',page,len(items),30,dict(workstream=scope,q=q,state=state,capability=capability))
    setup=''
    if not ms.read('milestone_projects',"SELECT project_id FROM milestone_projects WHERE seed_key='endorsement-business-plan-131'"):
        setup+='<p>Prepare the agreed endorsement plan with Katherine as lead. It starts paused and makes no model requests.</p><form method="post" action="/project-leadership/endorsement"><button>Prepare endorsement project</button></form>'
    choices=[(a['id'],a['title']) for a in team.projects() if a['id'] not in configs]
    if choices:setup+='<h3>Add milestones to an existing project</h3><p>Organise unfinished tasks first. Existing approval controls still apply.</p><form method="post" action="/project-leadership/attach">'+select('Project','project_id',choices)+'<button>Appoint department lead</button></form>'
    if setup:body+=details('Milestone setup',setup)
    return render(body,'Projects')

def settings():
    groups=[('People & working context',[('/agent-personalities','Agent personalities','Department-specific voice and working approach.'),('/memory','Memory & writing','Confirmed preferences and writing guidance.'),('/memory/preview','Context preview','Inspect the saved context used for a task.'),('/team/budget','Budget & spending','Model rates, limits and accounting.')]),('Connections & communications',[('/assistant/connections','Channel connections','Reading, analysis consent and connection controls.'),('/inboxes/setup','Connection guide','Existing inbox setup instructions.'),('/assistant/settings','Briefing schedule','When saved communication briefings are prepared.')]),('Operations & health',[('/system-baseline','System baseline','Inspect current local activation evidence.'),('/runtime','Worker status','Execution activity and worker controls.'),('/system-checks','System checks','Source and workflow checks.'),('/proactive','Proactive checks','Rules for saved work signals.')]),('Advanced tools',[('/team','Team administration','Activation, employee settings and existing team controls.'),('/queue','Earlier jobs','Inspect the retained legacy job queue.'),('/agent-runs','Execution records','Detailed agent run history.'),('/coding','Coding workspace','Open the existing isolated coding tools.')])]
    body=header('Manage your workspace','Settings and diagnostics stay here while everyday work stays in its department.')+'<div class="ui-settings-grid">'
    for title,links in groups:body+='<section class="card"><h2>'+E(title)+'</h2><ul>'+''.join('<li>'+link(url,label)+'<small>'+E(desc)+'</small></li>' for url,label,desc in links)+'</ul></section>'
    return render(body+'</div>','Settings')
