"""Governed dispatch, evidence review, handoffs, disputes and employee context."""
import json,time
from datetime import date
from uuid import uuid4
from superhuman.projects import engine as p
from superhuman.agentic import store as agent,tools
from superhuman.runtime import engine as runtime
from superhuman.departments.store import readonly,tables,rows
from . import store,budget

def owned_run(pid,path=p.DEFAULT_DB):
    with readonly(path) as db:
        if 'team_tasks' not in tables(db):return None
        row=db.execute('SELECT * FROM team_tasks WHERE run_id=?',(pid,)).fetchone();return dict(row) if row else None

def gate(item,path=p.DEFAULT_DB):
    settings=store.settings(path)
    if not settings['enabled'] or settings['hold']:return False,'Team paused or Twin needs inspection'
    parent=store.project(item['project_id'],path)
    if parent['status']!='active':return False,'Project is paused or finished'
    if item['state'] not in ('ready','dispatched'):return False,'Task is '+item['state'].replace('_',' ')
    employee=next((e for e in store.employees(path) if e['id']==item['owner']),None)
    if not employee or employee['paused']:return False,'Employee paused'
    if store.needs_owner(item,path) and not item['owner_grant']:return False,'Owner approval required by risk/sensitivity'
    all_tasks={t['id']:t for t in store.tasks(path)}
    if any(all_tasks.get(i,{}).get('state')!='completed' for i in json.loads(item['deps'])):return False,'Waiting for approved prerequisite results'
    classification=store.effective(item,path)
    for dep in json.loads(item['deps']):
        c=store.effective(all_tasks[dep],path)
        if store.SENSITIVITIES.index(c['sensitivity'])>store.SENSITIVITIES.index(classification['sensitivity']) or store.RISKS.index(c['risk'])>store.RISKS.index(classification['risk']):return False,'Prerequisite classification increased; owner must update destination controls'
    from superhuman.planning import store as planning
    plan=planning.snapshot(item['owner'])
    if plan['warnings'] or plan['goal'].get('status','active')!='active':return False,'Department goal is held, closed or unreadable'
    if item['run_id']:
        run=agent.get(item['run_id'],path)
        if not set(run['allowed_tools'])<=set(json.loads(employee['allowed_tools'])):return False,'Employee tool permission was withdrawn'
        if run['project']['max_calls']>item['max_calls']:return False,'Run request ceiling exceeds its team allowance'
        for dep in json.loads(item['deps']):
            child=all_tasks[dep]
            if child['run_id']:
                try:p._text(json.loads(p.get(child['run_id'],path)['tasks'][0]['result_json']))
                except (ValueError,OSError,TypeError):return False,'Prerequisite output changed or is unreadable'
    return True,''

def run_gate(pid,path=p.DEFAULT_DB):
    item=owned_run(pid,path)
    if item:return gate(item,path)
    if store.enabled(path):
        with readonly(path) as db:
            if 'projects' in tables(db):
                row=db.execute('SELECT workstream FROM projects WHERE id=?',(pid,)).fetchone()
                if row and row['workstream']=='writing':return False,'Legacy writing work is held; writing is now a department skill'
    return True,''

def ordered(ids,path=p.DEFAULT_DB):
    def key(pid):
        item=owned_run(pid,path)
        if not item:return (2,1,'9999-12-31',0,ids.index(pid))
        c=store.effective(item,path);rank=store.PRIORITIES.index(c['priority']);due=item['due'] or '9999-12-31'
        if item['due'] and item['due']<=date.today().isoformat():rank=max(0,rank-1)
        age=max(0,time.time()-__import__('datetime').datetime.fromisoformat(item['created_at']).timestamp())
        if age>=7*86400:rank=max(1,rank-1)
        return (rank,0 if item['due'] else 1,due,-min(age,30*86400),ids.index(pid))
    return sorted([pid for pid in ids if run_gate(pid,path)[0]],key=key)

def dispatch(ident,expected,path=p.DEFAULT_DB):
    item=store.task(ident,path)
    if item['version']!=expected or item['run_id']:raise ValueError('Task changed or already dispatched')
    good,reason=gate(item,path)
    if not good:raise ValueError(reason)
    parent=store.project(item['project_id'],path);employee=next(e for e in store.employees(path) if e['id']==item['owner'])
    allowed=json.loads(employee['allowed_tools'])
    if not allowed:raise ValueError('Employee has no permitted tools')
    if not budget.ready(store.settings(path)['model'],path):raise ValueError('Dollar budget or model rate card is not ready')
    instruction=item['instruction']+'\n\nProject objective: '+parent['objective']+'\nProject criteria: '+parent['acceptance']+'\nTask acceptance criteria: '+item['acceptance']+'\nUse the team handoff tool for help; challenge unsafe or incorrect instructions. Finish with evidence for internal review. No external commitments are authorized.'
    if len(instruction)>12000:raise ValueError('Combined task and project brief exceeds 12000 characters')
    active=sum(t['state']=='dispatched' and gate(t,path)[0] for t in store.tasks(path))
    if active>=store.settings(path)['max_active']:raise ValueError('Active assignment limit reached')
    pid=uuid4().hex[:12]
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');cur=db.execute('SELECT * FROM team_tasks WHERE id=?',(ident,)).fetchone();settings=db.execute('SELECT * FROM team_settings WHERE id=1').fetchone();ep=db.execute('SELECT * FROM team_employees WHERE id=?',(item['owner'],)).fetchone();pr=db.execute('SELECT * FROM team_projects WHERE id=?',(item['project_id'],)).fetchone()
        if not cur or cur['version']!=expected or cur['run_id'] or cur['state']!='ready' or not settings['enabled'] or settings['hold'] or ep['paused'] or ep['version']!=employee['version'] or pr['version']!=parent['version'] or pr['status']!='active':raise ValueError('Assignment, employee or project changed before dispatch')
        if db.execute("SELECT COUNT(*) FROM team_tasks WHERE state='dispatched'").fetchone()[0]>=settings['max_active']:raise ValueError('Active assignment limit reached')
        runtime._insert_job(db,pid,'agentic',item['owner'],item['title'],instruction)
        db.execute('UPDATE projects SET max_calls=? WHERE id=?',(item['max_calls'],pid))
        db.execute("INSERT INTO agentic_runs VALUES(?,?,?,?, 'ready',1,0,NULL,?,?)",(pid,store.encode(allowed),'[]',item['max_steps'],p.stamp(),p.stamp()))
        db.execute("UPDATE team_tasks SET run_id=?,state='dispatched',version=version+1,updated_at=? WHERE id=?",(pid,p.stamp(),ident));store.event(db,'twin','task_dispatched',{'task_id':ident,'employee':item['owner'],'run_id':pid});agent.event(db,pid,'team_assignment',{'task_id':ident,'employee':item['owner']})
    return pid

def refresh(path=p.DEFAULT_DB):
    for item in store.tasks(path):
        if not item['run_id'] or item['state'] in ('cancelled','completed','paused','disputed','waiting_handoff','waiting_dependency'):continue
        project=p.get(item['run_id'],path);state=None
        if project['status']=='needs_review':state='awaiting_review'
        elif project['status']=='approved':state='completed'
        elif project['status'] in ('rejected','cancelled'):state='owner_review' if project['status']=='rejected' else 'cancelled'
        elif project['status'] in ('budget_blocked','dependency_blocked') or agent.get(item['run_id'],path)['state'] in ('interrupted','needs_review','step_limit','awaiting_permission'):state='held'
        if state and state!=item['state']:
            with p.connect(path) as db:db.execute('UPDATE team_tasks SET state=?,version=version+1,updated_at=? WHERE id=? AND version=?',(state,p.stamp(),item['id'],item['version']))
    all_tasks={t['id']:t for t in store.tasks(path)}
    for item in all_tasks.values():
        if item['state']=='waiting_dependency' and all(all_tasks.get(d,{}).get('state')=='completed' for d in json.loads(item['deps'])):
            with p.connect(path) as db:db.execute("UPDATE team_tasks SET state=?,version=version+1 WHERE id=? AND state='waiting_dependency'",('dispatched' if item['run_id'] else 'ready',item['id']))

def verify(item,path=p.DEFAULT_DB):
    if not item['run_id']:raise ValueError('No run output')
    run=agent.get(item['run_id'],path);task=run['project']['tasks'][0]
    if task['status']!='needs_review':raise ValueError('Output is not awaiting review')
    result=json.loads(task['result_json'] or '{}');p._text(result)
    evidence=result.get('evidence_action_ids',[])
    if not evidence:raise ValueError('Verified evidence IDs are missing')
    for ident in evidence:
        a=next((a for a in run['actions'] if a['id']==ident and a['status'] in ('succeeded','cached')),None)
        if not a or not json.loads(a['verification_json'] or '{}').get('verified'):raise ValueError('Evidence is not verified')
        tools.verify_saved(a,item['owner'],path)
    return result

def review(ident,expected,approve,note,actor='twin',path=p.DEFAULT_DB):
    item=store.task(ident,path);note=store.text(note,2000,'Review rationale',True)
    if item['version']!=expected or item['state']!='awaiting_review':raise ValueError('Review state changed')
    if actor!='owner' and store.needs_owner(item,path):raise ValueError('This result requires owner approval')
    if actor!='owner' and item['attempts']>=2:raise ValueError('Revision limit reached; owner decision required')
    verify(item,path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        latest=db.execute('SELECT * FROM team_tasks WHERE id=?',(ident,)).fetchone()
        parent=db.execute('SELECT * FROM team_projects WHERE id=?',(item['project_id'],)).fetchone()
        if latest['version']!=expected or latest['state']!='awaiting_review':raise ValueError('Task changed during review')
        if actor!='owner' and ((latest['risk'] or parent['risk'])!='routine' or parent['risk']!='routine' or (latest['sensitivity'] or parent['sensitivity'])=='restricted' or parent['sensitivity']=='restricted'):raise ValueError('Owner approval required')
        cur=db.execute("UPDATE project_tasks SET status=?,review_note=? WHERE project_id=? AND id='final' AND status='needs_review'",('approved' if approve else 'pending',note,item['run_id']))
        if not cur.rowcount:raise ValueError('Canonical review state changed')
        db.execute('UPDATE projects SET status=?,updated_at=? WHERE id=?',('approved' if approve else 'active',p.stamp(),item['run_id']))
        if not approve:
            db.execute("UPDATE agentic_runs SET state='ready',failures=0,version=version+1 WHERE project_id=?",(item['run_id'],));agent.event(db,item['run_id'],'resume',{'note':note,'actor':actor})
            db.execute("UPDATE project_tasks SET token=NULL,error=NULL WHERE project_id=? AND id='final'",(item['run_id'],))
        db.execute('UPDATE team_tasks SET state=?,attempts=attempts+?,version=version+1,updated_at=? WHERE id=?',('completed' if approve else 'dispatched',0 if approve else 1,p.stamp(),ident));store.event(db,actor,'task_approved' if approve else 'task_revision',{'task_id':ident,'rationale':note,'verification':'artifact/evidence rechecked; semantic assessment by '+actor})
    refresh(path)

def task_control(ident,expected,action,note='',path=p.DEFAULT_DB):
    item=store.task(ident,path)
    if item['version']!=expected:raise ValueError('Task changed; reload')
    if action=='approve_start':
        if item['state'] not in ('queued','owner_review','ready','held'):raise ValueError('Task cannot be approved now')
        with p.connect(path) as db:db.execute("UPDATE team_tasks SET owner_grant=1,state=?,version=version+1 WHERE id=?",('dispatched' if item['run_id'] else 'ready',ident));store.event(db,'owner','task_start_approved',{'task_id':ident})
    elif action in ('pause','resume','cancel'):
        if item['state'] in ('completed','cancelled'):raise ValueError('Finished task cannot be changed')
        if action=='resume' and item['state'] not in ('paused','held'):raise ValueError('Task is not held')
        if action=='resume' and item['run_id']:
            run=agent.get(item['run_id'],path)
            if run['state'] in ('paused','interrupted','needs_review','budget_blocked'):
                agent.control(item['run_id'],run['version'],'resume',store.text(note,2000,'Inspection note',True),path)
        if action=='cancel' and item['run_id']:
            run=agent.get(item['run_id'],path)
            if run['state'] not in ('completed','cancelled'):agent.control(item['run_id'],run['version'],'cancel',path=path)
        state='paused' if action=='pause' else 'cancelled' if action=='cancel' else 'dispatched' if item['run_id'] else 'queued'
        with p.connect(path) as db:db.execute('UPDATE team_tasks SET state=?,version=version+1 WHERE id=?',(state,ident));store.event(db,'owner','task_'+action,{'task_id':ident,'note':note})
    else:raise ValueError('Unknown task control')

def request_tool(name,args,run,path=p.DEFAULT_DB):
    item=owned_run(run['project_id'],path)
    if not item:raise ValueError('Team tool requires an assigned employee task')
    ident=uuid4().hex;kind=name.split('.')[1];recipient=args.get('recipient','')
    if kind=='handoff' and (recipient not in store.EMPLOYEES or recipient in ('twin',item['owner'])):raise ValueError('Choose another specialist')
    if kind=='remember':
        note=store.add_memory(item['owner'],args.get('kind','lesson'),args['content'],'department',store.effective(item,path)['sensitivity'],path)
        return tools.outcome({'memory_id':note,'status':'proposed'},True,'Memory proposed; owner confirmation required')
    payload={k:store.text(v,1500 if k=='acceptance' else 180 if k=='title' else 4000,k,True) for k,v in args.items()}
    if kind not in ('handoff','challenge'):raise ValueError('Unknown team action')
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT id FROM team_requests WHERE task_id=? AND kind=? AND payload=?',(item['id'],kind,store.encode(payload))).fetchone()
        if old:return tools.outcome({'request_id':old[0]},True,'Existing tracked request returned')
        db.execute('INSERT INTO team_requests(id,task_id,kind,recipient,payload,created_at) VALUES(?,?,?,?,?,?)',(ident,item['id'],kind,recipient,store.encode(payload),p.stamp()));db.execute('UPDATE team_tasks SET state=?,version=version+1 WHERE id=?',('waiting_handoff' if kind=='handoff' else 'disputed',item['id']));store.event(db,item['owner'],kind+'_requested',{'task_id':item['id'],'request_id':ident})
    return tools.outcome({'request_id':ident,'status':'waiting_for_twin'},True,'Tracked request saved; no alternative or cross-department work executed')

def resolve_request(ident,expected,action,note,actor='twin',path=p.DEFAULT_DB):
    req=next((r for r in store.requests(path) if r['id']==ident),None)
    if not req or req['version']!=expected or req['status'] not in ('open','escalated'):raise ValueError('Request changed')
    item=store.task(req['task_id'],path);payload=json.loads(req['payload']);note=store.text(note,2000,'Decision rationale',True)
    sensitivity=store.effective(item,path)['sensitivity']
    if action=='alternative' and actor!='owner':raise ValueError('Only the owner can authorize an alternative over the Twin instruction')
    if action=='accept' and req['kind']=='handoff' and sensitivity in ('confidential','restricted') and actor!='owner':raise ValueError('Owner approval is required to share sensitive work across departments')
    if action=='escalate':
        with p.connect(path) as db:db.execute("UPDATE team_requests SET status='escalated',response=?,version=version+1 WHERE id=?",(note,ident))
        return None
    if action=='accept' and req['kind']=='handoff':
        classification=store.effective(item,path)
        ancestor=item;depth=0
        while ancestor.get('parent_id'):
            depth+=1;ancestor=store.task(ancestor['parent_id'],path)
        if depth>=3:raise ValueError('Handoff depth limit reached; owner must simplify the task')
        with p.connect(path) as db:
            db.execute('BEGIN IMMEDIATE');cur=db.execute("UPDATE team_requests SET status='accepted',response=?,version=version+1 WHERE id=? AND version=? AND status IN ('open','escalated')",(note,ident,expected))
            if not cur.rowcount:raise ValueError('Request changed')
            child=store.create_task(item['project_id'],req['recipient'],payload['title'],payload['instruction'],payload['acceptance'],priority=classification['priority'],risk=classification['risk'],sensitivity=classification['sensitivity'],actor=actor,parent_id=item['id'],path=path,_db=db)
            deps=json.loads(item['deps']);db.execute("UPDATE team_tasks SET state='waiting_dependency',deps=?,version=version+1 WHERE id=?",(store.encode(deps+[child]),item['id']));store.event(db,actor,'handoff_accepted',{'request_id':ident,'child_task_id':child})
        return child
    if action not in ('maintain','alternative','decline'):raise ValueError('Unsupported request decision')
    if action=='alternative':
        if req['kind']!='challenge' or not payload.get('alternative'):raise ValueError('No alternative was proposed')
        new=item['instruction']+'\n\nOwner-approved alternative: '+payload['alternative']
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');cur=db.execute("UPDATE team_requests SET status='resolved',response=?,version=version+1 WHERE id=? AND version=?",(note,ident,expected))
        if not cur.rowcount:raise ValueError('Request changed')
        if action=='alternative' and item['run_id']:
            db.execute('UPDATE projects SET details=? WHERE id=?',(new,item['run_id']));agent.event(db,item['run_id'],'resume',{'note':'Owner approved alternative: '+note})
        db.execute('UPDATE team_tasks SET state=?,instruction=?,version=version+1 WHERE id=?',('dispatched' if item['run_id'] else 'queued',new if action=='alternative' else item['instruction'],item['id']));store.event(db,actor,'request_'+action,{'request_id':ident,'rationale':note})

def writing(scope,path=p.DEFAULT_DB):
    skill=store.skill(scope,path)
    if not skill:return ''
    return '\nDepartment writing skill v'+str(skill['version'])+':\n'+skill['rules']+'\nOwner-approved examples (style references, not facts to copy):\n'+skill['examples'][:6000]

def employee_context(item,path=p.DEFAULT_DB):
    employee=next(e for e in store.employees(path) if e['id']==item['owner']);notes=store.memory(item['owner'],store.effective(item,path)['sensitivity'],path)
    body={'employee':item['owner'],'charter':employee['charter'],'acceptance':item['acceptance'],'confirmed_memory':[{'kind':n['kind'],'content':n['content']} for n in notes[:12]],'dependencies':[],'request_decisions':[{k:r[k] for k in ('id','kind','status','response')} for r in store.requests(path) if r['task_id']==item['id']]}
    for ident in json.loads(item['deps']):
        child=store.task(ident,path)
        if child['state']=='completed' and child['run_id']:
            result=json.loads(p.get(child['run_id'],path)['tasks'][0]['result_json']);_,content=p._text(result);body['dependencies'].append({'task_id':ident,'owner':child['owner'],'verified_output_excerpt':content[:6000],'excerpt_only':len(content)>6000})
    return '\nTEAM ASSIGNMENT (department boundaries and owner governance apply):\n'+store.encode(body)

def limits(ident,expected,max_calls,max_steps,cost_limit,path=p.DEFAULT_DB):
    amount=budget.micro(cost_limit);item=store.task(ident,path)
    if type(max_calls) is not int or not 2<=max_calls<=100 or type(max_steps) is not int or not 2<=max_steps<=40 or amount<=0:raise ValueError('Invalid request, step or dollar limit')
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM team_tasks WHERE id=?',(ident,)).fetchone()
        if row['version']!=expected:raise ValueError('Task changed; reload')
        charged=db.execute('SELECT COALESCE(SUM(charged_text+charged_tools),0) FROM team_costs WHERE task_id=?',(ident,)).fetchone()[0]
        if amount<charged:raise ValueError('Task limit cannot be below already charged/reserved dollars')
        if row['run_id']:
            used=db.execute('SELECT used_calls FROM projects WHERE id=?',(row['run_id'],)).fetchone()[0]
            actions=db.execute('SELECT COUNT(*) FROM agentic_actions WHERE project_id=?',(row['run_id'],)).fetchone()[0]
            if db.execute("SELECT 1 FROM project_tasks WHERE project_id=? AND status='running'",(row['run_id'],)).fetchone():raise ValueError('Wait for the current step before changing limits')
            if max_calls<used or max_steps<actions:raise ValueError('Limits cannot be below recorded use')
            db.execute('UPDATE projects SET max_calls=? WHERE id=?',(max_calls,row['run_id']));db.execute('UPDATE agentic_runs SET max_actions=?,version=version+1 WHERE project_id=?',(max_steps,row['run_id']))
        db.execute('UPDATE team_tasks SET max_calls=?,max_steps=?,cost_limit=?,version=version+1 WHERE id=?',(max_calls,max_steps,amount,ident));store.event(db,'owner','task_limits_authorized',{'task_id':ident,'max_calls':max_calls,'max_steps':max_steps,'micro_usd':amount})

def fixed_budget(pid,maximum,path=p.DEFAULT_DB):
    item=owned_run(pid,path)
    if item and maximum>item['max_calls']:raise ValueError('Use the Team task limit controls to authorize a higher allowance')

def adopt(pid,acceptance,priority='P2',risk='consequential',sensitivity='confidential',path=p.DEFAULT_DB):
    if owned_run(pid,path):raise ValueError('Run already has a team owner')
    old=p.get(pid,path)
    if old['workstream'] not in store.EMPLOYEES or old['workstream']=='twin' or len(old['tasks'])!=1 or old['tasks'][0]['kind']!='agentic':raise ValueError('Only existing single-task agent runs in a specialist department can be adopted')
    store.initialize(path)
    project_id=store.create_project(old['workstream'],old['objective'],old['details'][:2000],acceptance,priority,risk,sensitivity,path)
    ident=store.create_task(project_id,old['workstream'],old['objective'],old['details'][:5000],acceptance[:1500],path=path)
    status='completed' if old['status']=='approved' else 'awaiting_review' if old['status']=='needs_review' else 'held'
    with p.connect(path) as db:
        db.execute('UPDATE team_tasks SET run_id=?,state=?,max_calls=?,max_steps=? WHERE id=?',(pid,status,old['max_calls'],agent.get(pid,path)['max_actions'],ident));store.event(db,'owner','legacy_run_adopted',{'task_id':ident,'run_id':pid,'status':status})
    return ident
