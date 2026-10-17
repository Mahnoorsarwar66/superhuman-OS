"""Connected owner-facing journeys. Existing execution endpoints stay compatible."""
from datetime import datetime,date,timedelta
import hashlib,json,re
from pathlib import Path
from urllib.parse import urlencode,urlsplit,parse_qs
from uuid import uuid4
from fastapi import Form,HTTPException,Request
from fastapi.responses import HTMLResponse,RedirectResponse,Response
from superhuman.projects import engine as p
from superhuman.team import store as team
from superhuman.dialogue import store as d
from superhuman.experience import store as ux
from superhuman.experience import web as old,calendar,inbox
from superhuman.navigation import shell
from . import model,chat
from .presentation import rich
E=old.E;link=old.link;hidden=old.hidden;field=old.field;render=old.render;redirect=old.redirect;stamp=old.stamp

def select(label,name,values,chosen=''):
    return '<label>'+E(label)+'<select name="'+name+'">'+''.join('<option value="'+E(k)+'"'+(' selected' if str(k)==str(chosen) else '')+'>'+E(v)+'</option>' for k,v in values)+'</select></label>'
def error(exc):raise HTTPException(409,str(exc)) from exc

def list_projects(scope='all',q='',state='all',page=1,capability='all'):
    from superhuman.interface.views import projects
    return projects(scope,q,state,page,capability)


def pager(path,page,total,size,query):
    return '<nav aria-label="List pages">'+(link(path+'?'+urlencode(dict(query,page=page-1)),'← Previous page') if page>1 else '')+'<span>Page '+str(page)+'</span>'+(link(path+'?'+urlencode(dict(query,page=page+1)),'Next page →') if total>page*size else '')+'</nav>'

def project_form(scope='edsync_product',source=''):
    from superhuman.departments.store import departments
    if scope not in team.EMPLOYEES or scope=='twin':raise HTTPException(400,'Choose a department')
    original=p.get(source) if source else None
    body='<h1>Create project</h1><p>Set the outcome, department and controls. The Twin can plan tasks within these boundaries.</p><form method="post" action="/workspace-projects/create">'+select('Department','scope',departments(),original['workstream'] if original else scope)+field('Project name','title',original['objective'] if original else '')+field('What should this project achieve?','objective',original['details'][:2000] if original else '',True).replace('maxlength="6000"','maxlength="2000"')+field('What would a successful result look like?','acceptance','',True).replace('maxlength="6000"','maxlength="2000"')+select('Priority','priority',[(k,k+' · '+v) for k,v in zip(team.PRIORITIES,('Urgent','High','Normal','Low','Backlog'))],'P2')+select('Decision risk','risk',[(k,model.label(k)) for k in team.RISKS],'routine')+select('Information sensitivity','sensitivity',[(k,model.label(k)) for k in team.SENSITIVITIES],'internal')+hidden('source',source)+'<p class="muted">Creation does not make a model request. Paid work requires an enabled team and budget. Risk, privacy, employee permissions and owner approvals continue to apply.</p><button>Create project</button></form>'
    return render(body,'Create project')

def overview():
    from superhuman.interface.views import overview as show_overview
    return show_overview()


def department_body(data,tab,page):
    c=data['counts'];scope=data['scope'];body=''
    if tab=='summary':
        from superhuman.planning.presentation import summary_panel
        body+='<div class="v129-metrics">'+''.join('<div class="card"><strong>'+str(c[k])+'</strong><small>'+label+'</small></div>' for k,label in [('projects','Projects'),('tasks','Tasks'),('running','Working'),('outputs_review','Needs review')])+'</div>'+summary_panel(scope)+'<h2>Current projects</h2>'
        for a in data['projects'][:8]:body+='<section class="card"><h3>'+link(a['url'],a['objective'])+'</h3><p>'+E(model.label(a['status']))+'</p></section>'
        if not data['projects']:body+='<p>No projects yet. '+link('/new-project?scope='+scope,'Create the first project')+'</p>'
        body+='<h2>Needs attention</h2>'
        waiting=[a for a in data['tasks'] if a['status'] in ('needs_review','dependency_blocked','failed','interrupted')]
        for a in waiting[:10]:body+='<p>'+link(a['url'],a['title'])+' · '+E(model.label(a['status']))+'</p>'
        if not waiting:body+='<p>No saved task blockers or outputs awaiting review.</p>'
        body+='<h2>Research & documents</h2><p>'+str(c['areas'])+' research areas · '+str(c['sources'])+' source cards · '+str(c['files'])+' files · '+str(c['exports'])+' exports.</p>'+link('/departments/'+scope+'/knowledge','Open materials')
    elif tab=='projects':
        from superhuman.planning.presentation import summary_panel
        body+='<section class="ui-notice"><h2>Department priorities</h2>'+summary_panel(scope)+'<p>'+link('/department-plans/'+scope,'Manage plan & priorities')+'</p></section>'
        body+='<p>'+link('/new-project?scope='+scope,'Create project')+' · '+link('/project-tasks?department='+scope,'Filter all department tasks')+'</p><h2>Projects ('+str(c['projects'])+')</h2>'
        for a in data['projects'][(page-1)*50:page*50]:body+='<article class="card"><h3>'+link(a['url'],a['objective'])+'</h3><p>'+E(a['details'][:500])+'</p><span class="badge">'+E(model.label(a['status']))+'</span></article>'
        body+='<h2>Tasks ('+str(c['tasks'])+')</h2>'
        for t in data['tasks'][(page-1)*50:page*50]:body+='<p>'+link(t['url'],t['title'])+' · '+E(model.label(t['status']))+' · '+E(t['project_title'])+'</p>'
        body+=pager('/departments/'+scope+'/projects',page,max(c['projects'],c['tasks']),50,{})
    else:
        body+='<h2>Recorded activity & decisions</h2>'
        for a in data['events'][(page-1)*50:page*50]:body+='<section class="card"><strong>'+E(a['action'].replace('_',' '))+'</strong><p>'+link(a.get('url','/work/'+a['project_id']),a['project_title'])+'</p><small>'+E(stamp(a['created_at']))+'</small></section>'
        for a in data['decisions'][:50]:body+='<section class="card"><h3>'+E(a['title'])+'</h3>'+rich(a['content'])+'</section>'
        if not data['events'] and not data['decisions']:body+='<p>No recorded activity yet.</p>'
        body+=pager('/departments/'+scope+'/activity',page,len(data['events']),50,{})
    return body

def tasks(department='all',employee='all',status='all',priority='all',due='all',q='',page=1):
    if not 1<=page<=10000 or len(q)>200 or due not in ('all','overdue','dated','undated'):raise HTTPException(400,'Invalid task filter')
    from superhuman.departments.store import departments
    today=datetime.now(calendar.PKT).date().isoformat()
    items=[t for t in model.tasks() if (department=='all' or t['scope']==department) and (employee=='all' or t['owner']==employee) and (status=='all' or t['status']==status) and (priority=='all' or t['priority']==priority) and (due=='all' or due=='overdue' and t['due'] and t['due']<today and t['status'] not in ('completed','approved','cancelled') or due=='dated' and t['due'] or due=='undated' and not t['due']) and (not q or q.casefold() in (t['title']+' '+t['project_title']).casefold())]
    query=dict(department=department,employee=employee,status=status,priority=priority,due=due,q=q)
    body='<div class="ux-head"><h1>All tasks</h1>'+link('/new-task','+ Add task')+'</div><p>Employee tasks and earlier execution tasks in one filtered view. An employee task’s execution is counted once.</p><form class="v129-filters" method="get">'+select('Department','department',[('all','All departments')]+departments(),department)+select('Employee','employee',[('all','All employees')]+list(ux.NAMES.items()),employee)+select('Status','status',[(s,model.label(s)) for s in ['all']+sorted({t['status'] for t in model.tasks()})],status)+select('Priority','priority',[(v,v) for v in ['all']+list(team.PRIORITIES)],priority)+select('Deadline','due',[(v,model.label(v)) for v in ('all','overdue','dated','undated')],due)+field('Search','q',q).replace(' required','')+'<button>Apply filters</button></form><p>'+str(len(items))+' matching tasks</p>'
    for t in items[(page-1)*40:page*40]:body+='<article class="card"><span class="badge">'+E(model.label(t['status']))+'</span><h3>'+link(t['url'],t['title'])+'</h3><p>'+E(ux.NAMES.get(t['owner'],ux.ROLES.get(t['owner'],t['owner'])))+' · '+E(t['priority'])+(' · Due '+E(t['due']) if t['due'] else '')+'</p><small>'+E(t['project_title'])+'</small></article>'
    if not items:body+='<p>No tasks match these filters. Clear the filters or add a task to a project.</p>'
    return render(body+pager('/project-tasks',page,len(items),40,query),'All tasks')

def reviews(q='',page=1):
    if not 1<=page<=10000 or len(q)>200:raise HTTPException(400,'Invalid review filter')
    items=[a for a in model.decisions() if not q or q.casefold() in (a['title']+' '+a['reason']).casefold()]
    body='<h1>Decisions waiting for you</h1><p>The same queue powers Reviews, Attention and the Overview count.</p><form method="get">'+field('Find a decision','q',q).replace(' required','')+'<button class="secondary">Search</button></form>'
    for a in items[(page-1)*40:page*40]:body+='<section class="card"><h3>'+link(a['url'],a['title'])+'</h3><p>'+E(a['reason'])+'</p></section>'
    if not items:body+='<p>No decisions match this view.</p>'
    return render(body+pager('/reviews',page,len(items),40,{'q':q}),'Reviews')

def room_listing(employee='all',q='',page=1,project_id=''):
    if employee not in ('all',*ux.NAMES) or not 1<=page<=10000 or len(q)>200:raise HTTPException(400,'Invalid conversation filter')
    # SQL paging covers the entire history, including rooms older than the old 200-row cap.
    conditions=['1=1'];args=[]
    if employee!='all':conditions.append('r.employee=?');args.append(employee)
    if project_id:conditions.append('r.project_id=?');args.append(project_id)
    if q:conditions.append("(instr(lower(d.title),lower(?))>0)");args.append(q)
    where=' AND '.join(conditions)
    items=ux.read('ux_rooms','SELECT d.*,r.employee,r.project_kind,r.project_id FROM ux_rooms r JOIN dialogue_threads d ON d.id=r.thread_id WHERE '+where+' ORDER BY d.updated_at DESC,d.id',tuple(args))
    body='<form class="v129-filters" method="get" action="/team-room">'+select('Employee','employee',[('all','All employees')]+list(ux.NAMES.items()),employee)+field('Find a conversation','q',q).replace(' required','')+'<button class="secondary">Search</button></form>'
    for r in items[(page-1)*30:page*30]:body+='<article class="card"><h3>'+link('/team-room/'+r['id'],r['title'])+'</h3><small>'+E(ux.NAMES[r['employee']])+' · '+('Project conversation' if r['project_id'] else 'Employee conversation')+' · '+E(stamp(r['updated_at']))+'</small></article>'
    if not items:body+='<p>No matching conversations. Start one below.</p>'
    body+=pager('/team-room',page,len(items),30,{'employee':employee,'q':q})
    return body

def team_home(employee='all',tab='room',page=1,q=''):
    if tab=='board':return render('<h1>Your employees</h1><p>Current saved assignments, connectivity and next actions.</p>'+old.board(),'Employees')
    if tab=='feed':return feed(page)
    body='<div class="ux-head"><div><h1>Team conversations</h1><p>Choose an employee, continue a conversation or start a project room.</p></div>'+link('/twin','The Twin')+'</div>'+room_listing(employee,q,page)+'<details'+(' open' if employee!='all' else '')+'><summary>Start a conversation'+(' with '+E(ux.NAMES[employee]) if employee in ux.NAMES else '')+'</summary>'+old.room_form(employee if employee in ux.NAMES else 'twin')+'</details><p>'+link('/talk','Earlier department conversations')+'</p>'
    return render(body,'Team conversations')

def twin(tab='chat',page=1):
    if tab not in ('chat','updates','communications'):raise HTTPException(400,'Choose Chat, Owner updates or Communications')
    body='<h1>The Twin</h1><p>Superhuman · Your coordinator and personal assistant. Chat discusses work; Owner updates set explicit instructions; Communications holds saved briefings and drafts.</p><nav class="shell-tabs" aria-label="Twin workspace">'+''.join('<a href="/twin?tab='+t+'"'+(' aria-current="page"' if tab==t else '')+'>'+name+'</a>' for t,name in [('chat','Chat'),('updates','Owner updates'),('communications','Communications')])+'</nav>'
    if tab=='chat':
        body+='<p class="muted">Global Twin chats can use your owner updates, confirmed employee memory and up to three saved briefings whose source consent is still valid. They do not fetch live messages. Project chats stay within the project.</p>'+room_listing('twin',page=page)+'<details><summary>Start a new Twin conversation</summary>'+old.room_form('twin')+'</details>'
    elif tab=='updates':
        body+='<section class="card"><h2>Give the Twin a standing update</h2><form data-voice method="post" action="/team/twin/messages">'+select('Update type','kind',[(s,model.label(s)) for s in ('instruction','temporary_constraint','preference','decision','priority_change')],'instruction')+field('Your update','content','',True)+'<label>Temporary constraint duration (hours)<input name="hours" type="number" min="1" max="2160" value="24"></label><p>Use project/task pause controls for an immediate enforced stop. Preferences still require confirmation to become lasting memory.</p><button>Save owner update</button></form></section>'
        for m in team.messages()[:30]:body+='<article class="card"><small>'+E(model.label(m['kind'])+' · '+m['status'])+'</small>'+rich(m['content'])+'</article>'
        cfg=team.settings()
        if cfg['hold']:body+='<section class="card"><h2>Twin needs your decision</h2><p>'+E(cfg['hold'])+'</p><form method="post" action="/team/twin/resume">'+hidden('version',cfg['version'])+field('What did you review?','note','',True)+'<button>Authorise continuation</button></form></section>'
    else:
        from superhuman.comms import store as comms
        cfg=comms.settings();body+='<div class="ux-actions">'+link('/inboxes','Inbox')+link('/assistant/connections','Connections & consent')+link('/assistant/settings','Briefing schedule')+'</div><p>Reading and AI consent remain separate. No messages are sent from this workspace.</p>'
        if not cfg['version']:body+='<form method="post" action="/assistant/setup"><button>Set up communications</button></form>'
        else:body+='<form method="post" action="/assistant/brief">'+hidden('submission',uuid4().hex)+'<button>Request a fresh private briefing</button></form><p>'+('Scheduled briefings enabled' if cfg['enabled'] else 'Scheduled briefings paused')+'</p>'
        for r in comms.runs()[:20]:
            result=json.loads(r['result']) if r['result'] else {};body+='<article class="card"><span class="badge">'+E(model.label(r['status']))+'</span><h3>'+link('/assistant/runs/'+r['id'],'Briefing / analysis · '+stamp(r['created_at']))+'</h3>'+rich(result.get('summary') or r['error'])+'</article>'
        body+='<h2>Reply drafts</h2>'
        for a in comms.drafts()[:30]:body+='<p>'+link('/assistant/drafts/'+a['id'],'Review draft')+' · '+E(a['state'])+'</p>'
    return render(body,'The Twin')

def feed(page=1):
    if not 1<=page<=10000:raise HTTPException(400,'Invalid page')
    items=ux.read('team_requests','SELECT r.*,t.title,t.owner,t.project_id FROM team_requests r JOIN team_tasks t ON t.id=r.task_id ORDER BY r.created_at DESC,r.id')
    body='<h1>Team activity</h1><p>Saved handoffs, questions and decisions. Open a request to review the original instructions and controls.</p><div class="ux-feed">'
    for r in items[(page-1)*30:page*30]:
        try:payload=json.loads(r['payload'])
        except ValueError:payload={'Message':r['payload']}
        body+='<article class="card"><span class="badge">'+E(model.label(r['kind'])+' · '+model.label(r['status']))+'</span><h3>'+link('/team/requests/'+r['id'],ux.NAMES.get(r['owner'],r['owner'])+' → '+ux.NAMES.get(r['recipient'],r['recipient'] or 'twin'))+'</h3><p>'+E(r['title'])+'</p>'
        if isinstance(payload,dict):
            for key,value in payload.items():
                if key.lower() in ('chain_of_thought','private_reasoning','reasoning'):continue
                body+='<p><strong>'+E(model.label(key))+'</strong></p>'+rich(value if isinstance(value,str) else ', '.join(map(str,value)) if isinstance(value,list) else str(value))
        else:body+=rich(str(payload))
        if r['response']:body+='<h4>Saved decision</h4>'+rich(r['response'])
        body+='<small>'+E(stamp(r['created_at']))+'</small></article>'
    if not items:body+='<p>No recorded employee exchanges yet.</p>'
    return render(body+'</div>'+pager('/team-room',page,len(items),30,{'tab':'feed'}),'Team activity')

def transcript(ident,before=0):
    turns=d.turns(ident,before=before or None);r=ux.room(ident);body='<div data-transcript>'
    if turns and turns[0]['ordinal']>1:body+='<p>'+link('/team-room/'+ident+'?before='+str(turns[0]['ordinal']),'← Older messages')+'</p>'
    if before:body+='<p>'+link('/team-room/'+ident,'Latest messages')+'</p>'
    for t in turns:
        body+='<article class="card owner"><small>You · '+E(stamp(t['created_at']))+'</small>'+rich(t['user_text'])+'</article><article class="card reply"><small>'+E(ux.NAMES[r['employee']])+' · '+E(model.label(t['status']))+'</small>'
        body+=rich(t['reply'] or t['error'] or ('Reply is being prepared…' if t['status']=='running' else 'Message queued. The worker will prepare a reply.'))
        if t['status']=='queued':body+='<form method="post" action="/room-controls/'+ident+'/cancel">'+hidden('turn_id',t['id'])+'<button class="secondary">Cancel queued reply</button></form>'
        elif t['status'] in ('failed','cancelled','budget_blocked','interrupted'):
            body+='<details><summary>Request another attempt</summary><p>A fresh attempt may incur model cost. Check the error and current budget before requesting it.</p><form method="post" action="/room-controls/'+ident+'/retry">'+hidden('turn_id',t['id'])+hidden('submission_key',uuid4().hex)+'<button class="secondary">Request a fresh reply</button></form></details>'
        if t['status']=='done':body+='<p>'+link('/talk/'+ident+'/turn/'+t['id']+'/remember','Review for memory')+'</p>'
        body+='</article>'
    return body+'</div>'

def proposals(ident):
    r=ux.room(ident);body='<div data-proposals>'
    for s in d.suggestions(ident):
        body+='<details class="card" id="proposal-'+s['id']+'"><summary>'+E(s['title']+' · '+model.label(s['status']))+'</summary>'+rich(s['rationale'])
        saved=ux.read('ux_suggestion_tasks','SELECT task_id FROM ux_suggestion_tasks WHERE suggestion_id=?',(s['id'],))
        if saved:body+='<p>'+link('/team/tasks/'+saved[0]['task_id'],'Open task')+'</p>'
        elif s['status']=='proposed':
            choices=[a for a in team.projects() if a['status']=='active' and (r['employee']=='twin' or a['scope']==r['employee']) and (not r['project_id'] or r['project_kind']=='team' and a['id']==r['project_id'])]
            if choices:
                parent=choices[0];sensitivity=max((parent['sensitivity'],'confidential'),key=team.SENSITIVITIES.index)
                body+='<form method="post" action="/room-controls/'+ident+'/approve">'+hidden('suggestion_id',s['id'])+hidden('expected_hash',s['proposal_hash'])+select('Project','project_id',[(a['id'],a['title']) for a in choices])+field('Title','title',s['title'])+field('Reviewed instructions','instruction',s['details'],True).replace('maxlength="6000"','maxlength="5000"')+field('Acceptance criteria','acceptance','Produce a reviewable local deliverable; identify assumptions and sources.',True).replace('maxlength="6000"','maxlength="1500"')+select('Decision risk','risk',[(k,model.label(k)) for k in team.RISKS],parent['risk'])+select('Information sensitivity','sensitivity',[(k,model.label(k)) for k in team.SENSITIVITIES],sensitivity)+'<label><input type="checkbox" name="share_confirmed" value="true"> I reviewed the instructions and confirm they contain no private conversation content if I select Public or Internal.</label><label><input type="checkbox" name="start" value="true"> Authorise this exact task to start within existing project, employee, budget and permission controls.</label><p class="muted">Project controls are the minimum. Confidential drafts stay local. Checking start approval does not grant external sending or remove tool permission checks.</p><button>Create reviewed task</button></form>'
            else:body+='<p>'+link('/new-project','Create a managed project before assigning this work')+'</p>'
            body+='<form method="post" action="/room-controls/'+ident+'/dismiss">'+hidden('suggestion_id',s['id'])+hidden('expected_hash',s['proposal_hash'])+'<button class="secondary">Dismiss proposal</button></form>'
        body+='</details>'
    return body+'</div>'

def show_room(ident,before=0):
    r=ux.room(ident)
    if not r:raise HTTPException(404,'Conversation not found')
    thread=d.get(ident);employee=next((e for e in team.employees() if e['id']==r['employee']),{});pending=any(t['status'] in ('queued','running') for t in d.turns(ident));limited=thread['used_calls']>=thread['max_calls']
    latest=d.turns(ident,limit=1);last=E(latest[-1]['user_text'] if latest else '').replace('\n','&#10;').replace('\r','&#13;')
    body='<div class="ux-chat" data-room="'+ident+'" data-last-user="'+last+'" data-before="'+str(before)+'"><p>'+link('/twin' if r['employee']=='twin' else '/team-room?employee='+r['employee'],ux.NAMES[r['employee']])+'</p><h1>'+E(thread['title'])+'</h1><p>'+E(ux.ROLES[r['employee']])+'</p>'
    if r['project_id']:
        target=ux.project(r['project_kind'],r['project_id']);body+='<p class="badge">Project: '+link(('/team/projects/' if r['project_kind']=='team' else '/work/')+r['project_id'],target['title'])+'</p>'
    else:body+='<p class="muted">Employee conversation. Project-specific work should use a linked project room.</p>'
    body+='<p role="status" data-chat-status>Saved replies update automatically while this page is open.</p>'+transcript(ident,before)+proposals(ident)
    if limited:body+='<p class="error">This conversation has reached its reply allowance. Increase it below before sending again.</p>'
    if employee.get('paused'):body+='<p class="error">This employee is paused. '+link('/team/employees/'+r['employee'],'Open employee controls')+'</p>'
    body+='<form class="ux-composer" data-voice data-draft-key="'+ident+'" method="post" action="/team-room/'+ident+'/send">'+hidden('submission_key',uuid4().hex)+'<label>Message '+E(ux.NAMES[r['employee']])+'<textarea name="message" maxlength="6000" required></textarea></label><button'+(' disabled' if pending or limited or employee.get('paused') else '')+'>Send message</button><small>Review speech text before sending. A message does not approve tasks or create a standing instruction. Unsent text is kept in this browser session and cleared on sign out.</small></form><details><summary>Conversation controls · '+str(thread['used_calls'])+' / '+str(thread['max_calls'])+' replies used</summary><form method="post" action="/room-controls/'+ident+'/budget"><label>Total reply allowance<input name="maximum" type="number" min="'+str(max(1,thread['used_calls']))+'" max="100" value="'+str(thread['max_calls'])+'" required></label><button class="secondary">Update reply allowance</button></form>'+move_form(r,thread)+'</details></div>'
    return render(body,thread['title'])

def move_form(r,thread):
    targets=[a for a in model.projects() if a['scope']==thread['scope'] and r['employee'] in ('twin',a['scope'])]
    return '<h3>Correct conversation location</h3><p>Moves the whole history. Resolve proposals and pending replies first. No history is erased.</p><form method="post" action="/room-controls/'+r['thread_id']+'/move">'+hidden('version',r['version'])+select('Destination','destination',[('','Employee conversation (no project)')]+[(a['kind']+':'+a['id'],a['name']) for a in targets],r['project_kind']+':'+r['project_id'] if r['project_id'] else '')+'<label><input type="checkbox" name="confirmed" value="true" required> The entire conversation belongs here.</label><button class="secondary">Move conversation</button></form>'

def project_conversations(pid,page=1,kind='canonical'):
    if not 1<=page<=10000:raise HTTPException(400,'Invalid page')
    target=ux.project(kind,pid);items=ux.project_rooms(kind,pid);body='<p>Conversations explicitly linked to this project.</p>'
    for r in items[(page-1)*30:page*30]:body+='<article class="card"><h3>'+link('/team-room/'+r['id'],r['title'])+'</h3><small>'+E(ux.NAMES[r['employee']])+' · '+E(stamp(r['updated_at']))+'</small></article>'
    if not items:body+='<p>No linked conversations yet.</p>'
    path='/project-rooms/'+pid if kind=='team' else '/workspace/projects/'+pid+'/conversations'
    body+=pager(path,page,len(items),30,{})+'<details><summary>Start a project conversation</summary>'+old.room_form(target['scope'],kind,pid)+'</details>'
    unlinked=ux.read('dialogue_threads','SELECT d.id,d.title FROM dialogue_threads d LEFT JOIN ux_rooms r ON r.thread_id=d.id WHERE d.scope=? AND r.thread_id IS NULL ORDER BY d.updated_at DESC',(target['scope'],))
    if unlinked:body+='<details><summary>Link an earlier department conversation</summary><p>Link only if the entire history belongs to this project. Inbox reports remain separate.</p><form method="post" action="/team-room/link">'+hidden('kind',kind)+hidden('project_id',pid)+select('Conversation','thread_id',[(r['id'],r['title']) for r in unlinked])+'<button class="secondary">Link conversation</button></form></details>'
    return body

def task_detail(ident):
    from superhuman.team import work,budget
    try:t=team.task(ident);parent=team.project(t['project_id'])
    except ValueError as exc:raise HTTPException(404,str(exc)) from exc
    cfg=team.effective(t);body='<p>'+link('/team/projects/'+parent['id'],parent['title'])+'</p><h1>'+E(t['title'])+'</h1><span class="badge">'+E(model.label(t['state']))+'</span><p>'+E(ux.NAMES[t['owner']])+' · '+E(cfg['priority'])+' · '+E(model.label(cfg['risk']))+' · '+E(model.label(cfg['sensitivity']))+'</p><h2>Assignment</h2>'+rich(t['instruction'])+'<h3>Success criteria</h3>'+rich(t['acceptance'])
    good,reason=work.gate(t)
    if not good:body+='<p class="error">'+E(reason)+'</p>'
    if t['run_id']:
        run=p.get(t['run_id'])
        for output in run['tasks']:
            if output.get('result_json'):
                try:_,text=p._text(json.loads(output['result_json']));body+='<section class="card"><h2>Saved deliverable</h2>'+rich(text[:40000])+'</section>'
                except (ValueError,OSError,TypeError):body+='<p class="error">Saved deliverable could not be verified. Open execution details before approving.</p>'
        body+='<p>'+link('/agent-runs/'+t['run_id'],'Execution details and verified artifacts')+'</p>'
    actions=[]
    if t['state'] in ('queued','owner_review','ready','held') and not t['owner_grant']:actions.append(('approve_start','Approve start / continuation'))
    if t['state']=='awaiting_review':actions.extend([('approve_output','Approve output'),('revise_output','Request revision')])
    if t['state'] in ('paused','held'):actions.append(('resume','Resume after inspection'))
    if actions:body+='<form method="post" action="/team/tasks/'+ident+'/control">'+hidden('version',t['version'])+field('Review / inspection note','note','',True)+''.join('<button name="action" value="'+k+'">'+label+'</button> ' for k,label in actions)+'</form>'
    if t['state'] not in ('completed','cancelled'):
        body+='<details><summary>Pause, cancel or adjust limits</summary><form method="post" action="/team/tasks/'+ident+'/control">'+hidden('version',t['version'])+field('Reason','note','',True)+('' if t['state']=='paused' else '<button class="secondary" name="action" value="pause">Pause task</button> ')+'<button class="secondary" name="action" value="cancel">Cancel task</button> <button class="secondary" name="action" value="restrict_private_tools">Remove public-web tools from private run</button></form><form method="post" action="/team/tasks/'+ident+'/limits">'+hidden('version',t['version'])+field('Reply request limit','max_calls',t['max_calls'])+field('Decision step limit','max_steps',t['max_steps'])+field('Task budget (USD)','cost_limit',budget.usd(t['cost_limit']))+'<button class="secondary">Authorise limits</button></form></details>'
    body+='<h2>Handoffs and decisions</h2>'
    for r in team.requests():
        if r['task_id']==ident:body+='<p>'+link('/team/requests/'+r['id'],model.label(r['kind']))+' · '+E(model.label(r['status']))+'</p>'
    return render(body,t['title'])

def safe_return(value):
    parsed=urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.path!='/inboxes' or parsed.fragment:raise ValueError('Invalid return location')
    fields=parse_qs(parsed.query,keep_blank_values=True)
    if set(fields)-{'account','state','selected','q','page','notice'} or any(len(v)!=1 or len(v[0])>250 for v in fields.values()):raise ValueError('Invalid inbox context')
    return '/inboxes'+('?' +urlencode({k:v[0] for k,v in fields.items()}) if fields else '')

def inbox_actions(message,return_to):
    from superhuman.comms import store as comms
    body=''
    if message['id'].startswith('c:'):
        body+='<form method="post" action="/inbox-actions/analyse">'+hidden('source_id',message['source_id'])+hidden('return_to',return_to)+hidden('submission',uuid4().hex)+'<button class="secondary">Request Twin analysis of this message</button><small>Uses the configured model budget and existing channel consent. No new consent is granted.</small></form>'
        for a in comms.drafts():
            if a['source_id']==message['source_id']:body+='<details><summary>Edit this reply draft here</summary><form method="post" action="/inbox-actions/draft">'+hidden('ident',a['id'])+hidden('version',a['version'])+hidden('return_to',return_to)+field('Reply draft','body',a['body'],True)+'<button class="secondary">Save reviewed draft locally</button></form><p>Copy the reviewed text to the original service if you choose to send it. Nothing is sent here.</p></details>'
    else:body+='<p>'+link('/assistant/connections','Link this inbox to Twin analysis in connection settings')+'</p>'
    return body

def calendar_tools(view,day):
    return '<div class="v129-calendar-tools"><form class="v129-filters" method="get" action="/calendar">'+hidden('view',view)+'<label>Go to date<input type="date" name="day" value="'+day.isoformat()+'"></label><button class="secondary">Go</button></form><form class="v129-filters" method="get" action="/calendar-search">'+field('Find a meeting','q','').replace(' required','')+'<button class="secondary">Search calendar</button></form></div>'+deadline_bar(view,day)+'<p><span class="badge">Meeting</span> <span class="v129-deadline">Planning deadline</span> · Open a date to add a meeting; open a meeting to reschedule it.</p>'

def deadline_bar(view,day):
    if view=='month':return ''
    from superhuman.repairs.deadlines import items
    low,high=calendar.span(view,day)
    records=[a for a in items() if low.isoformat()<=a['due']<high.isoformat()]
    return ('<section class="card"><h3>Planning deadlines in this range</h3>'+''.join('<p>'+E(a['due'])+' · '+link(a['url'],a['title'])+'</p>' for a in records)+'</section>') if records else ''

def deadline_chips(day):
    from superhuman.repairs.deadlines import items
    return ''.join('<a class="ux-event v129-deadline" href="'+E(a['url'])+'">Deadline · '+E(a['title'])+'</a>' for a in items() if a['due']==day.isoformat())

def meeting_form(day='',event=None):
    from superhuman.calendar import store as cal
    if event is None:
        try:chosen=date.fromisoformat(day) if day else datetime.now(calendar.PKT).date()
        except ValueError:raise HTTPException(400,'Choose a valid date') from None
        event=dict(title='',start_at='',end_at='',notes='',status='confirmed')
    else:chosen=calendar.local(event['start_at']).date()
    def local_input(value):return calendar.local(value).strftime('%Y-%m-%dT%H:%M') if value else ''
    body=('<h2>Edit meeting</h2>' if event.get('id') else '<h1>New meeting</h1>')+'<p>All editable times below are Pakistan Standard Time (Asia/Karachi). Saving updates your local calendar; it sends no invitations.</p><form method="post" action="'+('/workspace-calendar/'+event['id']+'/save' if event.get('id') else '/workspace-calendar/create')+'">'+(hidden('version',event['version']) if event.get('id') else hidden('submission_key',uuid4().hex))+field('Title','title',event['title'])+'<label>Start (PKT)<input type="datetime-local" name="start_at" value="'+E(local_input(event['start_at']) or chosen.isoformat()+'T09:00')+'" required></label><label>End (optional, PKT)<input type="datetime-local" name="end_at" value="'+E(local_input(event['end_at']))+'"></label>'+field('Notes and original invitation information','notes',event['notes'],True)+select('Status','status',[('confirmed','Confirmed'),('cancelled','Cancelled')],event['status'])+'<button>'+('Save meeting changes' if event.get('id') else 'Create meeting')+'</button></form>'
    return body

def meeting_detail(key):
    from superhuman.calendar import store as cal
    try:event=cal.get(key)
    except ValueError as exc:raise HTTPException(404,str(exc)) from exc
    body='<p>'+link('/calendar?'+urlencode({'view':'day','day':calendar.local(event['start_at']).date().isoformat()}),'Back to calendar')+'</p><h1>'+E(event['title'])+'</h1><span class="badge">'+E(model.label(event['status']))+'</span><p>'+E(stamp(event['start_at']))+(' → '+E(stamp(event['end_at'])) if event['end_at'] else ' · End time unknown')+'</p>'+rich(event['notes'])+'<p>'+link('/meetings/'+key,'Meeting preparation & minutes')+' · '+link('/calendar/event/'+key+'/download','Download calendar event')+'</p><details><summary>Reschedule or edit meeting</summary>'+meeting_form(event=event)+'</details>'
    return render(body,event['title'])

def install(app):
    replaced={'/','/projects','/reviews','/attention','/project-tasks','/team-room','/team-room/{ident}','/team/twin','/assistant','/team/tasks/{ident}','/calendar/new','/calendar/event/{key}'}
    app.router.routes[:]=[r for r in app.router.routes if not (getattr(r,'path','') in replaced and 'GET' in getattr(r,'methods',()))]
    @app.get('/')
    def home():return overview()
    @app.get('/projects')
    def project_list(workstream:str='all',q:str='',state:str='all',page:int=1,capability:str='all'):
        from superhuman.core.router import WORKSTREAMS
        if workstream not in ('all',*WORKSTREAMS):raise HTTPException(400,'Unknown department')
        return list_projects(workstream,q,state,page,capability)
    @app.get('/new-project')
    def new_project(scope:str='edsync_product',source:str=''):return project_form(scope,source)
    @app.post('/workspace-projects/create')
    def create_project(scope:str=Form(...),title:str=Form(...),objective:str=Form(...),acceptance:str=Form(...),priority:str=Form('P2'),risk:str=Form('routine'),sensitivity:str=Form('internal'),source:str=Form('')):
        try:
            if source:
                original=p.get(source)
                if original['workstream']!=scope:raise ValueError('Earlier work must remain in its department')
                objective+='\nEarlier work reference: '+source
            return redirect('/team/projects/'+team.create_project(scope,title,objective,acceptance,priority,risk,sensitivity))
        except ValueError as exc:error(exc)
    @app.get('/new-task')
    def new_task(project_id:str=''):
        from superhuman.milestones.store import managed
        choices=[a for a in team.projects() if a['status']=='active' and not managed(a['id'])]
        if not choices and any(managed(a['id']) for a in team.projects()):return render('<h1>Add milestone work</h1><p>Open a project milestone to add a scoped work package for its approved team.</p>'+link('/projects?capability=milestones','Choose a milestone project'),'Add work')
        if not choices:return render('<h1>Add task</h1><p>Create a project first so this task has a clear owner and outcome.</p>'+link('/new-project','Create project'),'Add task')
        body='<h1>Add task to a project</h1><form method="post" action="/workspace-tasks/create">'+select('Project','project_id',[(a['id'],a['title']) for a in choices],project_id)+field('Title','title')+field('Instructions','instruction','',True).replace('maxlength="6000"','maxlength="5000"')+field('Success criteria','acceptance','',True).replace('maxlength="6000"','maxlength="1500"')+'<label>Due date (optional)<input type="date" name="due"></label><p>The task belongs to the project’s specialist and inherits its priority, risk and sensitivity.</p><button>Create task</button></form>'
        return render(body,'Add task')
    @app.post('/workspace-tasks/create')
    def create_task(project_id:str=Form(...),title:str=Form(...),instruction:str=Form(...),acceptance:str=Form(...),due:str=Form('')):
        try:
            parent=team.project(project_id)
            if parent['status']!='active':raise ValueError('Project is paused or finished')
            return redirect('/team/tasks/'+team.create_task(project_id,parent['scope'],title,instruction,acceptance,due=due))
        except ValueError as exc:error(exc)
    @app.get('/project-tasks')
    def task_list(department:str='all',employee:str='all',status:str='all',priority:str='all',due:str='all',q:str='',page:int=1):return tasks(department,employee,status,priority,due,q,page)
    @app.get('/reviews')
    @app.get('/attention')
    def review_list(q:str='',page:int=1):return reviews(q,page)
    @app.get('/twin')
    def twin_home(tab:str='chat',page:int=1):return twin(tab,page)
    @app.get('/team/twin')
    def old_twin():return redirect('/twin?tab=updates')
    @app.get('/assistant')
    def old_assistant():return redirect('/twin?tab=communications')
    @app.get('/team-room')
    def rooms(employee:str='all',tab:str='room',q:str='',page:int=1):return team_home(employee,tab,page,q)
    @app.get('/team-room/{ident}')
    def room(ident:str,before:int=0):
        if not 0<=before<=1000000:raise HTTPException(400,'Invalid history page')
        return show_room(ident,before)
    @app.get('/room-live/{ident}')
    def room_live(ident:str):
        if not ux.room(ident):raise HTTPException(404,'Conversation not found')
        thread=d.get(ident);turns=d.turns(ident);pending=any(t['status'] in ('running','queued') for t in turns);paused=next((e['paused'] for e in team.employees() if e['id']==ux.room(ident)['employee']),0)
        signature=hashlib.sha256(json.dumps([(t['id'],t['status'],t['reply'],t['error']) for t in turns]+[(s['id'],s['status']) for s in d.suggestions(ident)]+[thread['max_calls'],bool(paused)]).encode()).hexdigest()
        return dict(signature=signature,pending=pending,can_send=not pending and not paused and thread['used_calls']<thread['max_calls'],used=thread['used_calls'],maximum=thread['max_calls'])
    @app.get('/room-fragment/{ident}')
    def fragment(ident:str,before:int=0):
        if not ux.room(ident):raise HTTPException(404,'Conversation not found')
        return HTMLResponse(transcript(ident,before)+proposals(ident))
    @app.post('/room-controls/{ident}/budget')
    def room_budget(ident:str,maximum:int=Form(...)):
        try:d.set_budget(ident,maximum);return redirect('/team-room/'+ident)
        except ValueError as exc:error(exc)
    @app.post('/room-controls/{ident}/cancel')
    def room_cancel(ident:str,turn_id:str=Form(...)):
        try:d.cancel(ident,turn_id);return redirect('/team-room/'+ident)
        except ValueError as exc:error(exc)
    @app.post('/room-controls/{ident}/retry')
    def retry(ident:str,turn_id:str=Form(...),submission_key:str=Form(...)):
        try:
            turn=d.turn(turn_id)
            if turn['thread_id']!=ident or turn['status'] not in ('failed','cancelled','budget_blocked','interrupted'):raise ValueError('Only a failed or cancelled message can be retried')
            employee=ux.room(ident)
            if not employee or any(e['id']==employee['employee'] and e['paused'] for e in team.employees()):raise ValueError('Employee is paused or room is unavailable')
            d.send(ident,turn['user_text'],submission_key);return redirect('/team-room/'+ident)
        except ValueError as exc:error(exc)
    @app.post('/room-controls/{ident}/move')
    def move(ident:str,version:int=Form(...),destination:str=Form(''),confirmed:bool=Form(False)):
        try:
            kind,pid=destination.split(':',1) if destination else ('','');chat.relocate(ident,version,kind,pid,confirmed);return redirect('/team-room/'+ident)
        except ValueError as exc:error(exc)
    @app.post('/room-controls/{ident}/dismiss')
    def dismiss(ident:str,suggestion_id:str=Form(...),expected_hash:str=Form(...)):
        try:d.dismiss(ident,suggestion_id,expected_hash);return redirect('/team-room/'+ident)
        except ValueError as exc:error(exc)
    @app.post('/room-controls/{ident}/approve')
    def approve(ident:str,suggestion_id:str=Form(...),expected_hash:str=Form(...),project_id:str=Form(...),title:str=Form(...),instruction:str=Form(...),risk:str=Form(...),sensitivity:str=Form(...),acceptance:str=Form(...),share_confirmed:bool=Form(False),start:bool=Form(False)):
        if not any(s['id']==suggestion_id for s in d.suggestions(ident)):raise HTTPException(404,'Proposal not found in this conversation')
        try:return redirect('/team/tasks/'+chat.approve(suggestion_id,expected_hash,project_id,title,instruction,risk,sensitivity,acceptance,share_confirmed,start))
        except ValueError as exc:error(exc)
    @app.get('/team/tasks/{ident}')
    def task(ident:str):return task_detail(ident)
    @app.post('/inbox-actions/review')
    def inbox_review(ident:str=Form(...),state:str=Form(...),return_to:str=Form('/inboxes')):
        try:target=safe_return(return_to);inbox.mark(ident,state);return redirect(target)
        except ValueError as exc:error(exc)
    @app.post('/inbox-actions/draft')
    def draft(ident:str=Form(...),version:int=Form(...),body:str=Form(...),return_to:str=Form('/inboxes')):
        from superhuman.comms import store as comms
        try:target=safe_return(return_to);comms.edit_draft(ident,version,body);return redirect(target)
        except ValueError as exc:error(exc)
    @app.post('/inbox-actions/analyse')
    def analyse(source_id:str=Form(...),submission:str=Form(...),return_to:str=Form('/inboxes')):
        from superhuman.comms import engine
        try:
            target=safe_return(return_to);ident=engine.enqueue('intake',submission,selected=source_id)
            if not ident:raise ValueError('No eligible preview. Check current reading/AI consent, or whether this unchanged message was already analysed.')
            return render('<h1>Analysis queued</h1><p>The Twin will analyse this saved message within existing consent and budget controls.</p>'+link(target,'Return to your inbox position')+' · '+link('/assistant/runs/'+ident,'Inspect analysis'),'Analysis queued')
        except ValueError as exc:error(exc)
    @app.get('/calendar/new')
    def new_meeting(day:str=''):return render(meeting_form(day),'New meeting')
    @app.post('/workspace-calendar/create')
    def create_meeting(title:str=Form(...),start_at:str=Form(...),end_at:str=Form(''),notes:str=Form(''),submission:str=Form(...,alias='submission_key'),status:str=Form('confirmed')):
        from superhuman.calendar import store as cal
        try:
            if status!='confirmed':raise ValueError('Create the meeting as confirmed; cancel through its edit controls if needed')
            values=cal.fields(title,start_at,end_at,notes,local=True);return redirect('/calendar/event/'+cal.create(*values,submission))
        except ValueError as exc:error(exc)
    @app.get('/calendar/event/{key}')
    def event(key:str):return meeting_detail(key)
    @app.post('/workspace-calendar/{key}/save')
    def save_meeting(key:str,version:int=Form(...),title:str=Form(...),start_at:str=Form(...),end_at:str=Form(''),notes:str=Form(''),status:str=Form(...)):
        from superhuman.calendar import store as cal
        try:values=cal.fields(title,start_at,end_at,notes,local=True);cal.update(key,version,*values,status);return redirect('/calendar/event/'+key)
        except ValueError as exc:error(exc)
    @app.get('/calendar-search')
    def find_meeting(q:str='',page:int=1):
        if len(q)>200 or not 1<=page<=10000:raise HTTPException(400,'Invalid search')
        items=ux.read('calendar_events','SELECT * FROM calendar_events WHERE instr(lower(title||notes),lower(?))>0 ORDER BY start_at DESC',(q,));body='<h1>Find a meeting</h1><form method="get">'+field('Search','q',q).replace(' required','')+'<button>Search</button></form>'
        for a in items[(page-1)*30:page*30]:body+='<section class="card"><h3>'+link('/calendar/event/'+a['id'],a['title'])+'</h3><p>'+E(stamp(a['start_at']))+' · '+E(model.label(a['status']))+'</p></section>'
        return render(body+pager('/calendar-search',page,len(items),30,{'q':q}),'Calendar search')
    @app.post('/meeting-preview/{ident}')
    def preview(ident:str,title:str=Form(...),original:str=Form(...),zone:str=Form(''),end:str=Form(''),fold:str=Form('')):
        try:start=calendar.zoned(original,zone,fold);finish=calendar.zoned(end,zone,fold) if end else ''
        except ValueError as exc:error(exc)
        if finish and finish<=start:raise HTTPException(409,'End must be after start')
        conflicts=ux.read('calendar_events',"SELECT * FROM calendar_events WHERE status='confirmed' AND start_at<=? AND (end_at>? OR (end_at='' AND start_at=?)) ORDER BY start_at",(finish or start,start,start))
        body='<h1>Review Pakistan time</h1><h2>'+E(title)+'</h2><p>Original: '+E(original+' '+zone)+'</p><p><strong>PKT: '+E(stamp(start))+'</strong>'+(' → '+E(stamp(finish)) if finish else ' · End time unknown')+'</p><h3>Possible overlaps</h3>'
        for a in conflicts:body+='<p>'+link('/calendar/event/'+a['id'],a['title'])+' · '+E(stamp(a['start_at']))+'</p>'
        if not conflicts:body+='<p>No overlaps found in confirmed records. Unknown durations and unimported events cannot be checked.</p>'
        body+='<form method="post" action="/calendar-intake/'+ident+'/confirm">'+''.join(hidden(k,v) for k,v in dict(title=title,original=original,zone=zone,end=end,fold=fold).items())+'<button>Confirm this local meeting</button></form><p>'+link('/calendar-intake#meeting-'+ident,'Back to invitation')+'</p>'
        return render(body,'Review meeting time')
    @app.get('/assets/workspace-v129.js')
    def js():return Response((Path(__file__).parent/'assets/workspace.js').read_text(),media_type='application/javascript')
    @app.get('/assets/workspace-v129.css')
    def css():return Response((Path(__file__).parent/'assets/workspace.css').read_text(),media_type='text/css')
