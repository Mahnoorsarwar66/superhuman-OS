"""Owner-edited planning UI within the existing authenticated/CSRF boundary."""
import json
import sqlite3
from urllib.parse import quote
from uuid import uuid4
from fastapi import Form,HTTPException
from fastapi.responses import HTMLResponse,RedirectResponse
from superhuman.navigation import shell
from superhuman.core.router import WORKSTREAMS
from superhuman.departments.web import STYLE,when
from . import store,priority,presentation as view

E=shell.esc

def options(values,current,labels=None):return ''.join('<option value="'+E(v)+'"'+(' selected' if v==current else '')+'>'+E((labels or {}).get(v,v.replace('_',' ').capitalize()))+'</option>' for v in values)
def field(label,name,value='',maximum=2000,multiline=False,kind='text',required=False):
    attr=' name="'+name+'" maxlength="'+str(maximum)+'"'+(' required' if required else '')
    control='<textarea'+attr+'>'+E(value)+'</textarea>' if multiline else '<input type="'+kind+'"'+attr+' value="'+E(value)+'">'
    return '<label>'+label+control+'</label>'

def header(scope,title):
    name=WORKSTREAMS[scope]['name'];base=priority.edit_url(scope)
    items=(('/departments/'+scope,'Summary'),('/departments/'+scope+'/projects','Projects & Tasks'),('/departments/'+scope+'/knowledge','Research & Documents'),('/departments/'+scope+'/conversations','Conversations'),('/departments/'+scope+'/activity','Activity & Decisions'),(base,'Plan & Priorities'))
    return STYLE+'<p class="shell-context">'+view.link('/departments','Departments')+' / '+E(name)+'</p><h1>'+E(name)+'</h1><nav class="shell-tabs" aria-label="Department navigation">'+''.join('<a href="'+url+'"'+(' aria-current="page"' if url==base else '')+'>'+label+'</a>' for url,label in items)+'</nav><h2>'+E(title)+'</h2><p>'+view.link('/departments/'+scope+'/projects','Back to department work')+'</p>'

def render(body,title,status=200):return HTMLResponse(shell.page(body,title),status_code=status)
def check_scope(scope):
    try:store.scope_check(scope)
    except ValueError as exc:raise HTTPException(404,str(exc)) from exc

def edit_error(scope,exc,submitted):
    status=409 if isinstance(exc,store.Conflict) else 400
    body=header(scope,'Changes were not saved')+'<p class="error">'+E(str(exc))+'</p><p>'+view.link(priority.edit_url(scope),'Reopen the latest department plan')+'</p><details open><summary>Your submitted values</summary><p>Keep these values while comparing with the latest saved record.</p><dl>'
    for key,value in submitted.items():
        if key not in ('scope','version','ident','exc'):body+='<dt>'+E(key.replace('_',' ').capitalize())+'</dt><dd><pre>'+E(', '.join(value) if isinstance(value,list) else value)+'</pre></dd>'
    return render(body+'</dl></details>','Planning edit not saved',status)

def install(app):
    @app.get('/priorities')
    def priorities(page:int=1):
        if not 1<=page<=10000:raise HTTPException(400,'Invalid page')
        records,items=priority.queue();body='<h1>Department priorities</h1><p>You set the priorities and dates. This view orders your recorded milestones and missing inputs; it does not launch tasks.</p>'
        body+='<p class="muted">Order: actionable items first, then department priority and dates. Waiting dependencies and held milestones appear below actionable work. Undated items follow dated ones at the same priority.</p>'
        if any(plan['warnings'] for _,_,plan in records):body+='<p class="error">Some plans are unavailable; counts and actions may be incomplete.</p>'
        body+='<table><thead><tr><th>Department</th><th>Goal</th><th>Priority</th><th>Department target</th></tr></thead><tbody>'
        records.sort(key=lambda r:(priority.RANK[r[2]['goal']['priority']],r[2]['goal']['target_date'] or '9999-12-31',r[0]))
        for scope,name,p in records:
            g=p['goal'];body+='<tr><td>'+view.link(priority.edit_url(scope),name)+'</td><td>'+E(g['objective'] or 'Not set')+'</td><td>'+E(view.LABELS[g['priority']])+'</td><td>'+E(view.due_label(g['target_date']))+'</td></tr>'
        body+='</tbody></table><h2>Next-action list ('+str(len(items))+')</h2>'+view.action_list(items[(page-1)*50:page*50])
        if not items:body+='<p>No actions recorded. Open a department to add its first milestone.</p>'
        if page>1:body+='<p>'+view.link('/priorities?page='+str(page-1),'Previous')+'</p>'
        if len(items)>page*50:body+='<p>'+view.link('/priorities?page='+str(page+1),'Next')+'</p>'
        return render(body,'Department priorities')

    @app.get('/department-plans/{scope}')
    def home(scope:str,page:int=1):
        check_scope(scope)
        if not 1<=page<=10000:raise HTTPException(400,'Invalid page')
        data=store.snapshot(scope);g=data['goal'];base=priority.edit_url(scope);body=header(scope,'Plan & Priorities')
        for warning in data['warnings']:body+='<p class="error">'+E(warning)+'</p>'
        body+='<p>Set the outcome, then break it into milestones. Saving these records does not create tasks or start execution.</p><section class="card"><h3>Department plan</h3><form method="post" action="'+base+'/goal"><input type="hidden" name="version" value="'+str(g['version'])+'">'
        body+=field('Objective','objective',g['objective'],2000,True)+'<label>Priority<select name="priority">'+options(store.PRIORITIES,g['priority'],view.LABELS)+'</select></label>'+field('Department target date (Pakistan calendar date)','target_date',g['target_date'],10,kind='date')+field('What counts as success?','success_criteria',g['success_criteria'],4000,True)+'<label>Goal status<select name="goal_status">'+options(('active','on_hold','complete','archived'),g.get('status','active'))+'</select></label>'+field('Goal completion note (required for complete)','completion_note',g.get('completion_note',''),2000,True)+'<p class="muted">On hold, Complete and Archived pause new project work for this department. Running requests finish. Completing the goal requires finished/archived milestones and resolved blockers.</p><button>Save department plan</button></form></section>'
        if g['updated_at']:body+='<p class="muted">Plan last saved: '+E(when(g['updated_at']))+'</p>'
        body+='<div class="row"><h3>Milestones</h3>'+view.link(base+'/milestone/new','Add milestone')+'</div>'
        from superhuman.repairs.web import progress_panel
        body+=progress_panel(scope,data)
        byid={m['id']:m for m in data['milestones']}
        from superhuman.departments import store as departments
        recorded=departments.snapshot(scope);projects={p['id']:p for p in recorded['projects']}
        for m in data['milestones'][(page-1)*50:page*50]:
            body+='<section class="card"><span class="badge">'+E(m['status'].replace('_',' '))+'</span><h3>'+view.link(base+'/milestone/'+m['id'],m['title'])+'</h3><p>Target: '+E(view.due_label(m['target_date']))+'</p><p>'+E(m['success_criteria'] or 'Success criteria not set')+'</p>'
            if m['depends_on']:body+='<p>Depends on: '+', '.join(view.link(base+'/milestone/'+ident,byid.get(ident,{}).get('title','Missing milestone')) for ident in m['depends_on'])+'</p>'
            if m['project_ids']:body+='<p>Linked projects: '+', '.join(view.link('/work/'+ident,projects.get(ident,{}).get('objective','Unavailable project')) for ident in m['project_ids'])+'</p>'
            if m['completion_note']:body+='<p>Completion note: '+E(m['completion_note'])+'</p>'
            body+='</section>'
        if not data['milestones']:body+='<p>No milestones recorded yet.</p>'
        body+='<div class="row"><h3>Blockers & missing inputs</h3>'+view.link(base+'/blocker/new','Add blocker or missing input')+'</div>'
        for b in data['blockers'][(page-1)*50:page*50]:
            body+='<section class="card"><span class="badge">'+E(b['status'])+'</span><h3>'+view.link(base+'/blocker/'+b['id'],b['description'])+'</h3><p>Needed from: '+E(b['needed_from'] or 'Not assigned')+' · Target: '+E(view.due_label(b['target_date']))+'</p>'
            if b['milestone_id']:body+='<p>Milestone: '+E(byid.get(b['milestone_id'],{}).get('title','Unavailable'))+'</p>'
            if b['resolution_note']:body+='<p>Resolution: '+E(b['resolution_note'])+'</p>'
            body+='</section>'
        if not data['blockers']:body+='<p>No blockers or missing inputs recorded.</p>'
        body+='<p>'+view.link(base+'/history','View edit history')+' · '+view.link('/priorities','All department priorities')+'</p>'
        if page>1:body+='<p>'+view.link(base+'?page='+str(page-1),'Previous')+'</p>'
        if max(len(data['milestones']),len(data['blockers']))>page*50:body+='<p>'+view.link(base+'?page='+str(page+1),'Next')+'</p>'
        return render(body,'Plan & Priorities · '+WORKSTREAMS[scope]['name'])

    @app.post('/department-plans/{scope}/goal')
    def goal_save(scope:str,version:int=Form(...),objective:str=Form(''),priority:str=Form('unset'),target_date:str=Form(''),success_criteria:str=Form(''),goal_status:str=Form('active'),completion_note:str=Form('')):
        check_scope(scope)
        try:store.save_goal(scope,version,objective,priority,target_date,success_criteria,goal_status=goal_status,completion_note=completion_note)
        except ValueError as exc:return edit_error(scope,exc,locals())
        except sqlite3.Error:raise HTTPException(503,'Planning could not be saved. No edit was committed; retry after checking the planning database.') from None
        return RedirectResponse(priority_url(scope),status_code=303)

    @app.get('/department-plans/{scope}/milestone/{ident}')
    def milestone_edit(scope:str,ident:str):
        check_scope(scope);data=store.snapshot(scope)
        if ident=='new':m=dict(id=uuid4().hex,version=0,title='',target_date='',success_criteria='',status='planned',completion_note='',project_ids=[],depends_on=[])
        else:
            m=next((x for x in data['milestones'] if x['id']==ident),None)
            if m is None:raise HTTPException(404,'Milestone not found in this department')
        from superhuman.departments import store as departments
        projects=departments.snapshot(scope)['projects'];base=priority.edit_url(scope)
        body=header(scope,'Add milestone' if ident=='new' else 'Edit milestone')+'<form method="post" action="'+base+'/milestone/'+m['id']+'"><input type="hidden" name="version" value="'+str(m['version'])+'">'
        body+=field('Milestone title','title',m['title'],180,required=True)+field('Target date','target_date',m['target_date'],10,kind='date')+field('Success criteria','success_criteria',m['success_criteria'],4000,True)+'<label>Status<select name="status">'+options(store.MILESTONE_STATUSES,m['status'])+'</select></label>'+field('Completion note (required for complete)','completion_note',m['completion_note'],2000,True)
        body+='<fieldset><legend>Linked projects in this department</legend>'
        for p in projects:body+='<label><input type="checkbox" name="project_ids" value="'+E(p['id'])+'"'+(' checked' if p['id'] in m['project_ids'] else '')+'>'+E(p['objective'])+'</label>'
        if not projects:body+='<p>No projects recorded in this department yet.</p>'
        body+='</fieldset><fieldset><legend>Dependency milestones</legend>'
        for dependency in data['milestones']:
            if dependency['id']==m['id']:continue
            body+='<label><input type="checkbox" name="depends_on" value="'+dependency['id']+'"'+(' checked' if dependency['id'] in m['depends_on'] else '')+'>'+E(dependency['title'])+' · '+E(dependency['status'].replace('_',' '))+'</label>'
        body+='</fieldset><p class="muted">Dependencies must be complete before a milestone starts or completes. Complete requires criteria and a completion note, with no open linked blocker. Project links provide context; their task status is tracked separately.</p><button>Save milestone</button></form>'
        return render(body,'Milestone · '+WORKSTREAMS[scope]['name'])

    @app.post('/department-plans/{scope}/milestone/{ident}')
    def milestone_save(scope:str,ident:str,version:int=Form(...),title:str=Form(...),target_date:str=Form(''),success_criteria:str=Form(''),status:str=Form('planned'),completion_note:str=Form(''),project_ids:list[str]=Form([]),depends_on:list[str]=Form([])):
        check_scope(scope)
        try:store.save_milestone(scope,ident,version,title,target_date,success_criteria,status,completion_note,project_ids,depends_on)
        except ValueError as exc:return edit_error(scope,exc,locals())
        except sqlite3.Error:raise HTTPException(503,'Milestone could not be saved. No edit was committed.') from None
        return RedirectResponse(priority_url(scope),status_code=303)

    @app.get('/department-plans/{scope}/blocker/{ident}')
    def blocker_edit(scope:str,ident:str):
        check_scope(scope);data=store.snapshot(scope)
        if ident=='new':b=dict(id=uuid4().hex,version=0,description='',needed_from='',target_date='',status='open',milestone_id='',resolution_note='')
        else:
            b=next((x for x in data['blockers'] if x['id']==ident),None)
            if b is None:raise HTTPException(404,'Blocker not found in this department')
        base=priority.edit_url(scope);body=header(scope,'Add missing input' if ident=='new' else 'Edit missing input')+'<form method="post" action="'+base+'/blocker/'+b['id']+'"><input type="hidden" name="version" value="'+str(b['version'])+'">'
        body+=field('What is missing or blocked?','description',b['description'],2000,True,required=True)+field('Needed from (person, team or source)','needed_from',b['needed_from'],180)+field('Target date','target_date',b['target_date'],10,kind='date')+'<label>Status<select name="status">'+options(store.BLOCKER_STATUSES,b['status'])+'</select></label><label>Related milestone<select name="milestone_id"><option value="">Department generally</option>'+''.join('<option value="'+m['id']+'"'+(' selected' if m['id']==b['milestone_id'] else '')+'>'+E(m['title'])+'</option>' for m in data['milestones'])+'</select></label>'+field('Resolution note (required to resolve)','resolution_note',b['resolution_note'],2000,True)+'<p class="muted">This records an input request; it does not contact the named person or create a task.</p><button>Save blocker</button></form>'
        return render(body,'Missing input · '+WORKSTREAMS[scope]['name'])

    @app.post('/department-plans/{scope}/blocker/{ident}')
    def blocker_save(scope:str,ident:str,version:int=Form(...),description:str=Form(...),needed_from:str=Form(''),target_date:str=Form(''),status:str=Form('open'),milestone_id:str=Form(''),resolution_note:str=Form('')):
        check_scope(scope)
        try:store.save_blocker(scope,ident,version,description,needed_from,target_date,status,milestone_id,resolution_note)
        except ValueError as exc:return edit_error(scope,exc,locals())
        except sqlite3.Error:raise HTTPException(503,'Blocker could not be saved. No edit was committed.') from None
        return RedirectResponse(priority_url(scope),status_code=303)

    @app.get('/department-plans/{scope}/history')
    def history(scope:str,page:int=1):
        check_scope(scope)
        try:rows=store.history(scope,page)
        except ValueError as exc:raise HTTPException(400,str(exc)) from exc
        body=header(scope,'Planning edit history')
        data=store.snapshot(scope)
        milestone_names={m['id']:m['title'] for m in data['milestones']}
        from superhuman.departments import store as departments
        project_names={p['id']:p['objective'] for p in departments.snapshot(scope)['projects']}
        for row in rows:
            before=json.loads(row['before_json']);after=json.loads(row['after_json'])
            body+='<section class="card"><h3>'+E(row['entity_type'].capitalize()+' '+row['action'])+'</h3><p>'+E(when(row['recorded_at']))+'</p><table><thead><tr><th>Field</th><th>Before</th><th>After</th></tr></thead><tbody>'
            for k in after:
                if k in ('id','scope','version','created_at','updated_at') or before.get(k)==after[k]:continue
                def display(v):
                    if isinstance(v,list):
                        names=project_names if k=='project_ids' else milestone_names
                        return ', '.join(names.get(i,'Unavailable linked item') for i in v) or 'None'
                    if k=='milestone_id':return milestone_names.get(v,'Department generally')
                    if k=='priority':return view.LABELS.get(v,v or 'Not set')
                    return (str(v).replace('_',' ') if k=='status' and v else v) or 'Not set'
                body+='<tr><td>'+E(k.replace('_',' ').capitalize())+'</td><td>'+E(display(before.get(k)))+'</td><td>'+E(display(after[k]))+'</td></tr>'
            body+='</tbody></table></section>'
        if not rows:body+='<p>No planning edits recorded yet.</p>'
        if page>1:body+='<p>'+view.link(priority.edit_url(scope)+'/history?page='+str(page-1),'Previous')+'</p>'
        if len(rows)==50:body+='<p>'+view.link(priority.edit_url(scope)+'/history?page='+str(page+1),'Next')+'</p>'
        return render(body,'Planning history')

def priority_url(scope):return priority.edit_url(scope)
