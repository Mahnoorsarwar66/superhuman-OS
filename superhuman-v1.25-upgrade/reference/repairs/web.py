"""One task view, recovery controls, in-app reminders and live evidence checks."""
import hashlib,json
from datetime import date,timedelta
from urllib.parse import quote,urlencode
from fastapi import Form,HTTPException
from fastapi.responses import HTMLResponse,RedirectResponse,Response
from superhuman.navigation import shell
from superhuman.departments.store import readonly,tables,rows
from superhuman.projects import engine as projects
from superhuman.runtime import engine as runtime
from superhuman.core.router import WORKSTREAMS
from . import deadlines,checks

E=shell.esc

def task_rows(scope='all'):
    with readonly(projects.DEFAULT_DB) as db:
        if not {'projects','project_tasks'}<=tables(db):return []
        return rows(db,'SELECT t.*,p.objective AS project_title,p.workstream,p.status AS project_status,p.used_calls,p.max_calls FROM project_tasks t JOIN projects p ON p.id=t.project_id'+(' WHERE p.workstream=?' if scope!='all' else '')+' ORDER BY p.updated_at DESC,p.id,t.rowid',() if scope=='all' else (scope,))
def token(t):return hashlib.sha256(json.dumps({k:t.get(k) for k in ('id','status','token','started','result_json','error','details')},sort_keys=True).encode()).hexdigest()
def attention_items():
    from superhuman.knowledge.store import today
    out=[]
    for t in task_rows():
        if t['status'] in ('needs_review','interrupted','failed','quality_blocked','rejected'):
            out.append({'title':t['title'],'reason':t['status'].replace('_',' '),'url':'/projects/'+t['project_id']})
    with readonly(projects.DEFAULT_DB) as db:
        if 'projects' in tables(db):
            for p in db.execute("SELECT id,objective,status FROM projects WHERE status IN ('plan_review','plan_failed','budget_blocked','dependency_blocked')"):
                out.append({'title':p['objective'],'reason':p['status'].replace('_',' '),'url':'/work/'+p['id']})
    with readonly(projects.DEFAULT_DB) as db:
        ts=tables(db)
        if 'dialogue_suggestions' in ts:
            for row in db.execute("SELECT title,thread_id FROM dialogue_suggestions WHERE status='proposed'"):
                out.append({'title':row['title'],'reason':'Task suggestion awaiting approval','url':'/talk/'+row['thread_id']})
        if 'calendar_candidates' in ts:
            for row in db.execute("SELECT id,title FROM calendar_candidates WHERE status='proposed'"):
                out.append({'title':row['title'],'reason':'Calendar suggestion awaiting review','url':'/calendar/suggestion/'+row['id']})
    for item in deadlines.items():
        if date.fromisoformat(item['due'])<=today()+timedelta(days=7):out.append({'title':item['title'],'reason':'Deadline '+item['due'],'url':item['url']})
    from superhuman.planning import priority
    from .actions import milestone_progress
    for scope,_,plan in priority.all_departments():
        progress=milestone_progress(scope,plan)
        for m in plan['milestones']:
            if progress[m['id']]['ready_for_review']:out.append({'title':m['title'],'reason':'Linked projects approved; milestone ready for your assessment','url':priority.edit_url(scope,'milestone',m['id'])})
    from superhuman.agentic.store import listing
    for r in listing():
        if r['state'] in ('awaiting_permission','needs_review','step_limit','budget_blocked'):
            out.append({'title':r['objective'],'reason':r['state'].replace('_',' '),'url':'/agent-runs/'+r['project_id']})
    return out

def attention_link():
    try:n=len(attention_items())
    except (ValueError,OSError):return '<a href="/system-checks">Check system status</a>'
    return '<a href="/attention">Attention ('+str(n)+')</a>'

def progress_panel(scope,plan):
    from .actions import milestone_progress
    from superhuman.planning import priority
    progress=milestone_progress(scope,plan);body='<section class="card"><h3>Linked project progress</h3>'
    for m in plan['milestones']:
        if m['status']=='archived':continue
        r=progress[m['id']]
        body+='<p><a href="'+priority.edit_url(scope,'milestone',m['id'])+'">'+E(m['title'])+'</a>: '+str(r['approved_tasks'])+' / '+str(r['total_tasks'])+' linked tasks approved.'+(' <strong>Ready for milestone assessment.</strong>' if r['ready_for_review'] else '')+'</p>'
    return body+'<small>Task approval is shown automatically; milestone completion still requires your assessment.</small></section>'

def install(app):
    original=next(r.endpoint for r in app.routes if getattr(r,'path','')=='/tasks' and 'GET' in getattr(r,'methods',set()))
    app.router.routes[:]=[r for r in app.routes if not(getattr(r,'path','')=='/tasks' and 'GET' in getattr(r,'methods',set()))]
    def render(body,title='Tasks',status=200):return HTMLResponse(shell.page(body,title),status_code=status)
    @app.get('/tasks')
    def all_tasks(status:str='all',page:int=1,department:str='all',task_status:str='all'):
        if status!='all':return original(status,page)
        if not 1<=page<=10000 or department not in ('all',*WORKSTREAMS) or task_status not in ('all','running','pending','needs_review','blocked','approved','interrupted'):raise HTTPException(400,'Invalid task filter')
        allrows=task_rows(department)
        from .scheduler import order
        active=list(dict.fromkeys(t['project_id'] for t in allrows if t['project_status']=='active'))
        eligible=set(order(active,projects.DEFAULT_DB))
        for t in allrows:t['scheduling_held']=t['status']=='pending' and t['project_status']=='active' and t['project_id'] not in eligible
        filtered=[t for t in allrows if task_status=='all' or (task_status=='blocked' and (t['scheduling_held'] or t['status'] in ('failed','interrupted','quality_blocked','rejected') or t['project_status'] in ('budget_blocked','dependency_blocked','plan_failed'))) or t['status']==task_status]

        body='<h1>All tasks</h1><p><a href="/agent-runs">Start or inspect an agent run</a></p><p>Execution, review and recovery in one view. Task suggestions remain below and retain their original approval controls.</p><form method="get" action="/tasks"><label>Department<select name="department"><option value="all">All departments</option>'+''.join('<option value="'+E(k)+'"'+(' selected' if department==k else '')+'>'+E(v['name'])+'</option>' for k,v in WORKSTREAMS.items())+'</select></label><label>Task status<select name="task_status">'+''.join('<option value="'+s+'"'+(' selected' if task_status==s else '')+'>'+s.replace('_',' ').capitalize()+'</option>' for s in ('all','running','pending','needs_review','blocked','approved','interrupted'))+'</select></label><button class="secondary">Show tasks</button></form><p>'+str(len(filtered))+' matching tasks.</p>'
        with readonly(projects.DEFAULT_DB) as db:
            plans=rows(db,"SELECT id,objective,status,workstream FROM projects WHERE status IN ('new','planning','plan_review','plan_failed','budget_blocked','dependency_blocked') ORDER BY updated_at DESC") if 'projects' in tables(db) else []
        plans=[p for p in plans if department=='all' or p['workstream']==department]
        if plans:
            body+='<section class="card"><h2>Project plans & blocked objectives</h2>'
            for project in plans[:50]:body+='<p><a href="/work/'+project['id']+'">'+E(project['objective'])+'</a> · '+E(project['status'].replace('_',' '))+'</p>'
            if len(plans)>50:body+='<p><a href="/projects">View all '+str(len(plans))+' project objectives</a></p>'
            body+='</section>'
        from superhuman.hosted.jobs import worker_status
        worker=worker_status()
        body+='<p><strong>Worker: '+('Online' if worker['online'] else 'Offline')+(' · Paused' if worker['paused'] else '')+'</strong> · '+E(worker.get('activity') or 'No recent activity')+'</p>'
        for t in filtered[(page-1)*50:page*50]:
            body+='<section class="card"><span class="badge">'+E(t['status'].replace('_',' '))+'</span><h2>'+E(t['title'])+'</h2><p>'+E(t['project_title'])+' · '+E(WORKSTREAMS.get(t['workstream'],{}).get('name',t['workstream']))+'</p><p><a href="/projects/'+t['project_id']+'">Inspect output, task details and review</a></p>'
            if t['kind']=='agentic':body+='<p><a href="/agent-runs/'+t['project_id']+'">Inspect actions, permissions and run controls</a></p>'
            if t.get('error'):body+='<p class="error">'+E(t['error'])+'</p>'
            if t['scheduling_held']:body+='<p class="error">Waiting for the department plan, linked milestone dependencies, a linked blocker or unreadable planning state. <a href="/department-plans/'+E(t['workstream'])+'">Inspect the department plan</a>.</p>'
            if t['kind']!='agentic' and t['status'] in ('failed','interrupted','quality_blocked','rejected'):
                body+='<details><summary>Authorize a retry with corrections</summary><p>Inspect existing outputs first. A retry may spend model requests again and resets dependent work.</p><form method="post" action="/repair-tasks/'+t['project_id']+'/'+t['id']+'/retry"><input type="hidden" name="expected" value="'+token(t)+'"><label>Correction or retry note<textarea name="note" maxlength="2000" required></textarea></label><button>Authorize retry</button></form></details>'
            if t['project_status']=='budget_blocked':
                body+='<form method="post" action="/repair-projects/'+t['project_id']+'/budget"><input type="hidden" name="expected" value="'+str(t['used_calls'])+':'+str(t['max_calls'])+'"><label>New total model-request limit (used '+str(t['used_calls'])+')<input name="maximum" type="number" min="'+str(t['used_calls'])+'" max="100" value="'+str(t['max_calls'])+'" required></label><button>Authorize updated request limit</button></form>'
            body+='</section>'
        if not filtered:body+='<p>No tasks match this view.</p>'
        if page>1:body+='<p><a href="/tasks?'+urlencode({'page':page-1,'department':department,'task_status':task_status})+'">Previous task page</a></p>'
        if len(filtered)>page*50:body+='<p><a href="/tasks?'+urlencode({'page':page+1,'department':department,'task_status':task_status})+'">Next task page</a></p>'
        # Extract only the known shared-shell main, preserving original forms and actions.
        old=original('proposed',page).body.decode('utf-8')
        marker='<main class="shell-main" id="main">'
        inner=old.split(marker,1)[1].rsplit('</main>',1)[0]
        if department=='all':body+='<hr><h2>Task suggestions</h2>'+inner.replace('<h1>Task Desk</h1>','<h3>Review proposed work</h3>',1)
        else:body+='<p><a href="/tasks?status=proposed">Open the global suggestion review queue</a></p>'
        return render(body)

    @app.post('/repair-tasks/{pid}/{tid}/retry')
    def retry(pid:str,tid:str,expected:str=Form(...),note:str=Form(...)):
        if not note.strip() or len(note)>2000:raise HTTPException(400,'Provide a correction note of at most 2000 characters')
        try:
            project=projects.get(pid);t=next(t for t in project['tasks'] if t['id']==tid)
            if token(t)!=expected:raise HTTPException(409,'Task changed; reload before authorizing retry')
            runtime.retry(pid,tid,note)
        except (ValueError,StopIteration) as exc:raise HTTPException(400,str(exc) or 'Task not found') from exc
        return RedirectResponse('/tasks',status_code=303)

    @app.post('/repair-projects/{pid}/budget')
    def budget(pid:str,expected:str=Form(...),maximum:int=Form(...)):
        try:
            project=projects.get(pid)
            if expected!=str(project['used_calls'])+':'+str(project['max_calls']):raise HTTPException(409,'Request usage changed; reload before authorizing a new limit')
            projects.budget(pid,maximum)
        except ValueError as exc:raise HTTPException(400,str(exc)) from exc
        return RedirectResponse('/tasks',status_code=303)

    @app.get('/attention')
    def attention(page:int=1):
        if not 1<=page<=10000:raise HTTPException(400,'Invalid page')
        items=attention_items();body='<h1>Needs your attention</h1><p>Pending reviews, interrupted work, milestone assessments and deadlines within seven days. Refreshed when you open the page.</p>'
        for item in items[(page-1)*50:page*50]:body+='<section class="card"><h2><a href="'+E(item['url'])+'">'+E(item['title'])+'</a></h2><p>'+E(item['reason'])+'</p></section>'
        if not items:body+='<p>No attention items currently recorded.</p>'
        if page>1:body+='<a href="?page='+str(page-1)+'">Previous</a> '
        if len(items)>page*50:body+='<a href="?page='+str(page+1)+'">Next</a>'
        return render(body,'Attention')

    @app.get('/planning-deadlines.ics')
    def export_deadlines():return Response(deadlines.ics(),media_type='text/calendar',headers={'Content-Disposition':'attachment; filename="superhuman-planning-deadlines.ics"'})

    @app.get('/system-checks')
    def system_checks():
        data=checks.report();body='<h1>System checks</h1><p>Release '+E(data['version'])+' · Worker '+E(data['worker']['state'])+(' · paused' if data['worker'].get('paused') else '')+' · '+E(data['worker'].get('activity') or 'No activity recorded')+'</p><p>These checks use saved state and actual saved-output integrity checks. A live inbox sync is verified separately.</p>'
        for row in data['database_checks']:body+='<p>'+E(row['database'])+': '+E(row['result'])+'</p>'
        body+='<h2>Inbox checks</h2>'
        for a in data['inboxes']:body+='<section class="card"><strong>'+E(a['label'])+'</strong><p>'+('Connected configuration' if a['connected'] else 'Not connected')+' · Last successful sync: '+E(a['last_successful_sync'] or 'Not verified')+(' · Latest sync failed' if a['last_sync_failed'] else '')+'</p></section>'
        body+='<form method="post" action="/system-checks/inboxes"><button>Queue read-only checks for connected inboxes</button></form><p>No reports or paid model requests are generated by these sync checks.</p><h2>Saved outputs</h2><p>'+str(data['artifacts']['checked'])+' checked · '+str(len(data['artifacts']['problems']))+' problems.</p>'
        for item in data['artifacts']['problems']:body+='<p><a href="/projects/'+E(item['project_id'])+'">Inspect affected output</a>: '+E(item['issue'])+'</p>'
        body+='<h2>Document exports</h2><p>'+str(data['exports']['checked'])+' checked · '+str(len(data['exports']['problems']))+' problems.</p>'
        for item in data['exports']['problems']:body+='<p class="error">'+E(item['scope'])+': '+E(item['issue'])+'</p>'
        for item in data['assignment_problems']:body+='<p class="error">'+E(item['records'])+': '+E(item['issue'])+' ('+E(item['scope'])+')</p>'
        for item in data['planning_warnings']:body+='<p class="error">'+E(item['scope'])+': '+E(item['issue'])+'</p>'
        body+='<p><a href="/system-checks.json">Download local diagnostic results</a> · <a href="/memory/preview">Inspect memory, plan and source context</a></p>'
        return render(body,'System checks')
    @app.get('/system-checks.json')
    def system_json():return Response(json.dumps(checks.report(),indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="superhuman-system-checks.json"'})
    @app.post('/system-checks/inboxes')
    def inbox_check():checks.queue_inboxes();return RedirectResponse('/system-checks',status_code=303)
