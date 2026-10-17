"""Guarded repair integration against the delivered v1.22 source."""
import ast
from pathlib import Path
FILES=('hosted/worker.py','hosted/jobs.py','hosted/boundary.py','runtime/engine.py','identity/selection.py','planning/store.py','planning/priority.py','planning/presentation.py','planning/web.py','departments/web.py','navigation/web.py','navigation/shell.py','calendar/web.py','projects/engine.py')
def canonical(name,text):return ast.dump(ast.parse(text),include_attributes=False)
def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Repair source anchor missing or repeated: '+old[:100])
    return text.replace(old,new,1)
def function(text,name,replacement):
    node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name==name)
    lines=text.splitlines(True)
    return ''.join(lines[:node.lineno-1])+replacement+'\n'+''.join(lines[node.end_lineno:])
def build(name,text,reference):
    if canonical(name,text)!=canonical(name,(Path(reference)/name).read_text(encoding='utf-8')):raise ValueError('Unrecognised source in superhuman/'+name+'. Requires v1.22; no source overwritten.')
    if name=='hosted/worker.py':
        text=once(text,'        jobs.initialize(path)','        jobs.initialize(path)\n        from superhuman.repairs.recovery import recover\n        recover(path)')
        text=once(text,'        last_was_chat = False','        last_was_chat = False\n        last_was_plan = False')
        text=once(text,"                            if result is None:\n                                result=jobs.run_plan(path,actual)","                            if result is None and not last_was_plan:\n                                result=jobs.run_plan(path,actual)")
        text=once(text,"                            last_was_chat = bool(result and result.get('conversation_turn_id'))","                            if result is None and last_was_plan:\n                                result=jobs.run_plan(path,actual)\n                            last_was_plan = bool(result and 'error_type' in result and not result.get('task_id'))\n                            last_was_chat = bool(result and result.get('conversation_turn_id'))")
    elif name=='runtime/engine.py':text=once(text,'    for pid in candidates:\n        p=projects.get(pid,path)','    from superhuman.repairs.scheduler import order\n    candidates=order(candidates,path)\n    for pid in candidates:\n        p=projects.get(pid,path)')
    elif name=='projects/engine.py':
        text=once(text,'def claim(pid,path=DEFAULT_DB):\n    with connect(path) as db:', 'def claim(pid,path=DEFAULT_DB):\n    from superhuman.repairs.scheduler import order\n    if pid not in order([pid],path):return None\n    with connect(path) as db:')
    elif name=='hosted/jobs.py':
        text=once(text,'        row=db.execute("SELECT project_id FROM hosted_plans WHERE status=\'queued\' ORDER BY rowid LIMIT 1").fetchone()','        candidates=[r[0] for r in db.execute("SELECT project_id FROM hosted_plans WHERE status=\'queued\' ORDER BY rowid")]\n        from superhuman.repairs.scheduler import order\n        ranked=order(candidates,path)\n        row={\'project_id\':ranked[0]} if ranked else None')
    elif name=='hosted/boundary.py':text=once(text,"{'status':'ok','version':'1.9.0'}","{'status':'ok','version':'1.23.0'}")
    elif name=='identity/selection.py':
        old="    from superhuman.knowledge.context import augment\n    selected = _legacy_select_context(project, title, details, max_reference_chars)\n    return augment(selected, project, title, details, max_reference_chars)"
        text=once(text,old,"    from superhuman.repairs.context import select\n    return select(project,title,details,max_reference_chars)")
    elif name=='planning/store.py':
        text=once(text,"        db.execute('BEGIN IMMEDIATE')\n        try:yield db;db.commit()","        db.execute('BEGIN IMMEDIATE')\n        from superhuman.repairs.lifecycle import initialize\n        initialize(db)\n        try:yield db;db.commit()")
        text=once(text,"    return result\n\ndef audit", "    from superhuman.repairs.lifecycle import read\n    with readonly(path or default_path()) as lifecycle_db:\n        try:result['goal'].update(read(lifecycle_db,scope))\n        except sqlite3.Error:result['warnings'].append('Goal lifecycle could not be read.')\n    return result\n\ndef audit")
        text=once(text,'def save_goal(scope,expected_version,objective,priority,target_date,success_criteria,path=None):','def save_goal(scope,expected_version,objective,priority,target_date,success_criteria,path=None,goal_status=\'active\',completion_note=\'\'):')
        text=once(text,"        if (before.get('version',0))!=expected_version:","        from superhuman.repairs.lifecycle import read as read_lifecycle,save as save_lifecycle\n        if before:before.update(read_lifecycle(db,scope))\n        if (before.get('version',0))!=expected_version:")
        text=once(text,"        before=existing_item(db,'department_milestones',scope,ident,expected_version)","        from superhuman.repairs.lifecycle import read as goal_lifecycle\n        if goal_lifecycle(db,scope)['status'] in ('complete','archived') and status not in ('complete','archived'):raise ValueError('Reopen the department goal before adding or reactivating milestones')\n        before=existing_item(db,'department_milestones',scope,ident,expected_version)")
        text=once(text,"        before=existing_item(db,'department_blockers',scope,ident,expected_version)","        from superhuman.repairs.lifecycle import read as goal_lifecycle\n        if goal_lifecycle(db,scope)['status'] in ('complete','archived') and status=='open':raise ValueError('Reopen the department goal before adding or reopening blockers')\n        before=existing_item(db,'department_blockers',scope,ident,expected_version)")
        text=once(text,"        audit(db,scope,'goal',scope,before,after)","        after.update(save_lifecycle(db,scope,goal_status,completion_note,success_criteria))\n        audit(db,scope,'goal',scope,before,after)")
    elif name=='planning/priority.py':
        for fn,args in [('actions','scope,plan=None'),('queue',''),('next_step','scope,fallback')]:
            calls={'actions':'scope,plan','queue':'','next_step':'scope,fallback'}
            text=function(text,fn,'def '+fn+'('+args+'):\n    from superhuman.repairs.actions import '+fn+' as repaired\n    return repaired('+calls[fn]+')')
    elif name=='planning/presentation.py':
        text=once(text,"    pending=[m for m in p['milestones'] if m['status'] not in ('complete','archived')]","    pending=[m for m in p['milestones'] if m['status'] not in ('complete','archived')] if g.get('status','active')=='active' else []")
        text=once(text,"([g['target_date']] if g['target_date'] else [])","([g['target_date']] if g['target_date'] and g.get('status','active')=='active' else [])")
        text=once(text,"esc(g['objective'] or 'Not set')+'</dd><dt>Priority</dt><dd>'","esc(g['objective'] or 'Not set')+'</dd><dt>Goal status</dt><dd>'+esc(g.get('status','active').replace('_',' '))+'</dd><dt>Priority</dt><dd>'")
        text=once(text,"body+=action_list(items[:5]) if items else", "ready=[a for a in items if a.get('state','ready')=='ready']\n    body+=action_list(ready[:5]) if ready else")
        text=once(text,'Ordered by your department priority, overdue dates, target dates and missing inputs. Dependencies and holds are shown as constraints. These suggestions do not start work.','Actionable items appear before waiting work, then your department priorities and dates apply. Reviews and recovery remain available in Attention. These suggestions do not start work.')
        text=once(text,"    return body\n\ndef action_list", "    return body\n\ndef action_list") if False else text
        # Card targets for closed goals must not remain overdue.
        text=once(text,"esc(due_label(g['target_date']))","esc(due_label(g['target_date']) if g.get('status','active')=='active' else 'Goal '+g['status'].replace('_',' '))")
    elif name=='planning/web.py':
        text=once(text,"def goal_save(scope:str,version:int=Form(...),objective:str=Form(''),priority:str=Form('unset'),target_date:str=Form(''),success_criteria:str=Form('')):","def goal_save(scope:str,version:int=Form(...),objective:str=Form(''),priority:str=Form('unset'),target_date:str=Form(''),success_criteria:str=Form(''),goal_status:str=Form('active'),completion_note:str=Form('')):")
        text=once(text,'store.save_goal(scope,version,objective,priority,target_date,success_criteria)','store.save_goal(scope,version,objective,priority,target_date,success_criteria,goal_status=goal_status,completion_note=completion_note)')
        text=once(text,"+'<button>Save department plan</button></form></section>'", "+'<label>Goal status<select name=\"goal_status\">'+options(('active','on_hold','complete','archived'),g.get('status','active'))+'</select></label>'+field('Goal completion note (required for complete)','completion_note',g.get('completion_note',''),2000,True)+'<p class=\"muted\">On hold, Complete and Archived pause new project work for this department. Running requests finish. Completing the goal requires finished/archived milestones and resolved blockers.</p><button>Save department plan</button></form></section>'")
        text=once(text,"        byid={m['id']:m for m in data['milestones']}","        from superhuman.repairs.web import progress_panel\n        body+=progress_panel(scope,data)\n        byid={m['id']:m for m in data['milestones']}")
        text=once(text,'Order: department priority → overdue dates → target dates → missing inputs before milestones on the same date. Items without dates sort after dated items at the same priority. Dependency and hold notes explain what can proceed.','Order: actionable items first, then department priority and dates. Waiting dependencies and held milestones appear below actionable work. Undated items follow dated ones at the same priority.')
    elif name=='departments/web.py':text=once(text,'Suggestions reflect your saved planning priorities and recorded statuses; they do not execute work.','Ready actions respect dependencies. Pending reviews and interrupted work stay visible in Attention; suggestions do not execute work.')
    elif name=='navigation/web.py':
        text+='\n    from superhuman.repairs.web import install as install_repairs\n    install_repairs(app)\n'
        text=once(text,"card('Execution status','Inspect current worker activity and task progress.','/runtime','Open execution')", "card('Execution status','Inspect current worker activity and task progress.','/runtime','Open execution')+card('System checks','Check inbox syncs, stored outputs and department assignment.','/system-checks','Open system checks')")
    elif name=='navigation/shell.py':
        text=once(text,"    if path.startswith('/reviews'): return 'reviews'","    if path.startswith(('/reviews','/attention')): return 'reviews'\n    if path.startswith('/system-checks'): return 'settings'")
        text=once(text,"('/tasks','Suggestions')","('/tasks','All tasks'),('/tasks?status=proposed','Suggestions')")
        text=once(text,"    path=request_path.get();key=section(path);label=", "    from superhuman.repairs.web import attention_link\n    path=request_path.get();key=section(path);label=")
        text=once(text,"</span></div><form method=\"post\" action=\"/logout\">", "</span></div>'+attention_link()+'<form method=\"post\" action=\"/logout\">")
    elif name=='calendar/web.py':
        text=once(text,"        body='<h1>Your calendar</h1>'+nav()", "        from superhuman.repairs.deadlines import panel\n        body=panel()+'<h1>Your calendar</h1>'+nav()")
    ast.parse(text);return text
