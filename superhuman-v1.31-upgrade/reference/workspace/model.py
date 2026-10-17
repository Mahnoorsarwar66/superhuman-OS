"""A shared read model across old execution records and governed business projects."""
import json
from datetime import date
from superhuman.projects import engine as p
from superhuman.team import store as team
from superhuman.experience import store as ux
read=ux.read
NAMES=ux.NAMES;ROLES=ux.ROLES
TASK_STATUS={'completed':'approved','awaiting_review':'needs_review','held':'dependency_blocked','disputed':'dependency_blocked','owner_review':'dependency_blocked','waiting_dependency':'dependency_blocked','waiting_handoff':'dependency_blocked','queued':'pending','ready':'pending','dispatched':'pending'}
LABELS={'api_key_required':'API key needs configuration','reading_mail':'Checking communications','working':'Processing work','idle':'No active work','awaiting_review':'Needs review','owner_review':'Needs your decision','held':'Blocked','disputed':'Disagreement to resolve','waiting_dependency':'Waiting for prerequisite','waiting_handoff':'Waiting for teammate','dispatched':'Assigned','ready':'Ready to start','queued':'Queued','needs_review':'Needs review','plan_review':'Plan needs approval','budget_blocked':'Budget needs attention','dependency_blocked':'Blocked','approved':'Complete','completed':'Complete','paused':'Paused','running':'Working','active':'In progress','new':'Ready to plan','complete':'Complete','internal':'Internal','confidential':'Confidential','restricted':'Restricted','public':'Public','routine':'Routine','consequential':'Needs approval','high_risk':'High risk'}
def label(value):return LABELS.get(value,str(value).replace('_',' ').capitalize())
def merge(data,path=p.DEFAULT_DB):
    """Normalize without mutating storage or counting a Team task's execution twice."""
    projects=team.projects(path);tasks=team.tasks(path);owned={t['run_id'] for t in tasks if t['run_id']}
    data['projects']=[dict(q,kind='canonical',url='/work/'+q['id']) for q in data['projects'] if q['id'] not in owned]
    data['tasks']=[dict(t,kind='canonical',url='/projects/'+t['project_id']) for t in data['tasks'] if t['project_id'] not in owned]
    run_state={r['project_id']:r['state'] for r in read('agentic_runs','SELECT project_id,state FROM agentic_runs',path=path)}
    targets={q['id']:q for q in projects if q['scope']==data['scope']}
    for q in targets.values():
        data['projects'].append(dict(q,kind='team',objective=q['title'],details=q['objective'],status='approved' if q['status']=='complete' else q['status'],updated_at=q['created_at'],url='/team/projects/'+q['id'],error='',used_calls=0,max_calls=0))
    for t in tasks:
        if t['project_id'] not in targets:continue
        status='running' if t['state']=='dispatched' and run_state.get(t['run_id'])=='running' else TASK_STATUS.get(t['state'],t['state'])
        data['tasks'].append(dict(t,kind='team',status=status,details=t['instruction'],project_title=targets[t['project_id']]['title'],error='',result_json=None,url='/team/tasks/'+t['id']))
    scoped_task_ids={t['id'] for t in tasks if t['project_id'] in targets}
    for event in read('team_events','SELECT * FROM team_events ORDER BY seq DESC LIMIT 1000',path=path):
        try:detail=json.loads(event['detail_json'])
        except ValueError:continue
        task_id=detail.get('task_id');pid=detail.get('project_id')
        if task_id in scoped_task_ids:pid=next(t['project_id'] for t in tasks if t['id']==task_id)
        if pid not in targets:continue
        data['events'].append(dict(event,project_id=pid,project_title=targets[pid]['title'],url='/team/projects/'+pid,actor_name=NAMES.get(event['actor'],event['actor'])))
    data['projects'].sort(key=lambda q:q.get('updated_at',q['created_at']),reverse=True)
    data['events'].sort(key=lambda q:q['created_at'],reverse=True)
    data['events']=data['events'][:100]
    # Global Twin discussions do not masquerade as one specialist department's conversations.
    global_twin={r['thread_id'] for r in read('ux_rooms',"SELECT thread_id FROM ux_rooms WHERE employee='twin' AND project_id=''",path=path)}
    data['conversations']=[r for r in data['conversations'] if r['id'] not in global_twin]
    return data

def projects(path=p.DEFAULT_DB):
    owned={t['run_id'] for t in team.tasks(path) if t['run_id']};out=[]
    for q in team.projects(path):out.append(dict(q,kind='team',url='/team/projects/'+q['id'],name=q['title'],description=q['objective']))
    for q in read('projects','SELECT * FROM projects ORDER BY updated_at DESC',path=path):
        if q['id'] not in owned:out.append(dict(q,scope=q['workstream'],kind='canonical',url='/work/'+q['id'],name=q['objective'],description=q['details'],priority='P2',risk='consequential',sensitivity='internal'))
    return out

def tasks(path=p.DEFAULT_DB):
    parents={q['id']:q for q in team.projects(path)};out=[];owned=set()
    run_states={r['project_id']:r['state'] for r in read('agentic_runs','SELECT project_id,state FROM agentic_runs',path=path)}
    for t in team.tasks(path):
        if t['run_id']:owned.add(t['run_id'])
        q=parents[t['project_id']];out.append(dict(t,kind='team',scope=q['scope'],status='running' if t['state']=='dispatched' and run_states.get(t['run_id'])=='running' else t['state'],priority=t['priority'] or q['priority'],project_title=q['title'],url='/team/tasks/'+t['id']))
    for t in read('project_tasks','SELECT t.*,p.workstream,p.objective AS project_title FROM project_tasks t JOIN projects p ON p.id=t.project_id ORDER BY t.rowid DESC',path=path):
        if t['project_id'] not in owned:out.append(dict(t,kind='canonical',scope=t['workstream'],owner=t['workstream'],priority='P2',due='',url='/projects/'+t['project_id']))
    return sorted(out,key=lambda t:(t['priority'],t['due'] or '9999-12-31',t.get('created_at',''),t['id']))

def decisions(path=p.DEFAULT_DB):
    from superhuman.repairs.web import legacy_attention_items
    out=legacy_attention_items() if path==p.DEFAULT_DB else []
    owners={t['run_id']:t for t in team.tasks(path) if t['run_id']}
    for r in out:
        parts=r['url'].split('/')
        if len(parts)>2 and parts[1] in ('projects','work','agent-runs') and parts[2] in owners:
            owner=owners[parts[2]];r['url']='/team/tasks/'+owner['id'];r['title']=owner['title']
        if r['url'].startswith('/talk/'):
            ident=r['url'].split('/')[2]
            if ux.room(ident,path):r['url']='/team-room/'+ident
    for m in read('ux_meetings',"SELECT id,title FROM ux_meetings WHERE status='proposed'",path=path):out.append(dict(title=m['title'],reason='Meeting invitation needs confirmation',url='/calendar-intake#meeting-'+m['id']))
    from superhuman.knowledge.store import default_path
    for n in read('notes',"SELECT id,title FROM notes WHERE status='proposed'",path=default_path()):out.append(dict(title=n['title'],reason='Memory needs confirmation',url='/memory/'+n['id']))
    for m in read('team_memory',"SELECT id,employee FROM team_memory WHERE status='proposed'",path=path):out.append(dict(title=NAMES.get(m['employee'],m['employee'])+' memory',reason='Memory needs confirmation',url='/team/memory'))
    from superhuman.comms import store as comms
    for pr in comms.proposals(path):
        if pr['state']=='proposed':out.append(dict(title=pr['title'],reason='Inbox work suggestion',url='/assistant/proposals/'+pr['id']))
    for t in team.tasks(path):
        if t['state'] in ('queued','ready') and team.needs_owner(t,path) and not t['owner_grant']:out.append(dict(title=t['title'],reason='Task needs your start approval',url='/team/tasks/'+t['id']))
    unique={}
    for item in out:unique.setdefault((item['url'],item['title']),item)
    return list(unique.values())
