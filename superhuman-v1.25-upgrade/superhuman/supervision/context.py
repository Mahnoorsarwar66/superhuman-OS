"""Read-only progress, owner-defined targets and change detection."""
import hashlib,json
from superhuman.projects import engine as p
from superhuman.departments.store import readonly,tables,rows
from .store import encode

def append_links(scope,plan,path=p.DEFAULT_DB):
    with readonly(path) as db:
        if 'supervision_proposals' not in tables(db):return
        linked=rows(db,"SELECT s.target_json,s.project_id FROM supervision_proposals s JOIN projects p ON p.id=s.project_id WHERE s.scope=? AND s.status='dispatched' AND p.status!='cancelled'",(scope,))
    for row in linked:
        target=json.loads(row['target_json'])
        for m in plan['milestones']:
            if target.get('milestone_id')==m['id'] and (target.get('version')==m['version'] or m['status'] in ('complete','archived')):m['project_ids']=sorted(set(m['project_ids']+[row['project_id']]))

def target_available(scope,target,path=p.DEFAULT_DB,ignore_project=None):
    from superhuman.planning import store as planning
    plan=planning.snapshot(scope)
    if plan['warnings']:return False,'Planning records are unreadable'
    if plan['goal'].get('status','active')!='active':return False,'Department goal is on hold or closed'
    if any(b['status']=='open' and not b['milestone_id'] for b in plan['blockers']):return False,'An open department blocker needs resolution'
    if target.get('milestone_id'):
        m=next((m for m in plan['milestones'] if m['id']==target['milestone_id']),None)
        if not m or m['status'] not in ('planned','in_progress'):return False,'Target milestone is missing, held or finished'
        if m['version']!=target['version']:return False,'Target milestone changed; inspect this run before further work'
        byid={m['id']:m for m in plan['milestones']}
        if any(byid.get(dep,{}).get('status')!='complete' for dep in m['depends_on']):return False,'Milestone prerequisites are not complete'
        if any(b['status']=='open' and b['milestone_id']==m['id'] for b in plan['blockers']):return False,'A milestone blocker needs resolution'
        with readonly(path) as db:
            records={r['id']:r['status'] for r in db.execute('SELECT id,status FROM projects WHERE workstream=?',(scope,))} if 'projects' in tables(db) else {}
        if any(records.get(pid)!='approved' for pid in m['project_ids'] if pid!=ignore_project):return False,'Linked work already exists and needs completion or review'
        if m['project_ids'] and ignore_project is None:return False,'Linked outputs are approved; assess the milestone instead of starting duplicate work'
    else:
        if plan['milestones']:return False,'Use the milestone plan before starting a general mission'
        if plan['goal']['version']!=target['version']:return False,'Department goal changed; inspect the existing run'
    return True,''

def build(pol,path=p.DEFAULT_DB):
    from superhuman.departments.store import snapshot
    from superhuman.planning import store as planning
    from superhuman.identity.selection import select_context
    from superhuman.capabilities import local
    scope=pol['scope'];data=snapshot(scope,path);plan=planning.snapshot(scope)
    selected=select_context(scope,pol['mission'],pol['acceptance'])
    files=[]
    for row in data['files']:
        try:
            stat=local.file_for(scope,row['name']).stat();files.append({**row,'modified_ns':stat.st_mtime_ns})
        except (ValueError,OSError):data['warnings'].append('A source file could not be checked')
    projects=[{k:r[k] for k in ('id','objective','status','used_calls','max_calls')} for r in data['projects']]
    body={'department':scope,'mission':pol['mission'],'acceptance':pol['acceptance'],'plan':plan,'projects':projects,'files':files,'owner_preferences':selected['preferences'],'untrusted_references':selected['references']}
    signature=hashlib.sha256(encode(body).encode()).hexdigest()
    from . import store
    existing=store.proposals(scope,path);keys={r['target_key'] for r in existing}
    targets=[];reasons=[]
    if data['warnings'] or plan['warnings']:reasons.append('Department or planning records are unreadable')
    if plan['goal'].get('status','active')!='active':reasons.append('Department goal is held or closed')
    if any(b['status']=='open' and not b['milestone_id'] for b in plan['blockers']):reasons.append('Resolve the open department blocker')
    if any(r['status']=='proposed' for r in existing):reasons.append('A proposed action is waiting for your decision')
    active_ids={r['project_id'] for r in existing if r['project_id']}
    if any(r['id'] in active_ids and r['status'] not in ('approved','cancelled') for r in projects):reasons.append('Finish or review the existing supervised run first')
    if not reasons:
        for m in plan['milestones']:
            key='milestone:'+m['id']+':'+str(m['version'])
            target={'key':key,'milestone_id':m['id'],'version':m['version'],'title':m['title'],'criteria':m['success_criteria'] or pol['acceptance']}
            good,reason=target_available(scope,target,path)
            if good and key not in keys:targets.append(target)
            elif reason:reasons.append(reason)
        if not plan['milestones']:
            key='mission:'+str(plan['goal']['version'])+':'+hashlib.sha256((pol['mission']+'\n'+pol['acceptance']).encode()).hexdigest()
            if key not in keys:targets.append({'key':key,'milestone_id':'','version':plan['goal']['version'],'title':plan['goal']['objective'] or pol['mission'][:180],'criteria':pol['acceptance']})
        if not targets:reasons.append('No unhandled ready target. Review finished milestones or explicitly revise the mission/target for further work.')
    body['eligible_targets']=targets[:5];body['permitted_tools']=pol['allowed_tools'];body['required_tools']=pol['required_tools'];body['run_request_limit']=pol['run_calls'];body['run_step_limit']=pol['run_steps']
    return {'signature':signature,'body':body,'targets':targets[:5],'reasons':list(dict.fromkeys(reasons)),'projects':projects}

def progress(scope,path=p.DEFAULT_DB):
    from . import store
    from superhuman.planning import store as planning
    items=store.proposals(scope,path);plan=planning.snapshot(scope)
    with readonly(path) as db:
        records={r['id']:dict(r) for r in db.execute('SELECT id,status,used_calls,max_calls FROM projects WHERE workstream=?',(scope,))} if 'projects' in tables(db) else {}
    result=[]
    for item in items:
        project=records.get(item['project_id']);target=json.loads(item['target_json'])
        result.append({'proposal_id':item['id'],'title':item['title'],'proposal_status':item['status'],'project_id':item['project_id'],'project_status':project['status'] if project else None,'used_calls':project['used_calls'] if project else 0,'target':target})
    return {'runs':result,'goal_status':plan['goal'].get('status','active'),'milestones':[{'id':m['id'],'title':m['title'],'status':m['status'],'project_ids':m['project_ids']} for m in plan['milestones']]}
