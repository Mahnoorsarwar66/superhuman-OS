"""Exact v1.30 integration, retaining the installed CLI and orchestrator."""
import ast
from pathlib import Path
FILES=('navigation/web.py','navigation/shell.py','workspace/web.py','workspace/model.py','team/web.py','team/store.py','team/work.py','team/engine.py','hosted/worker.py','hosted/boundary.py','repairs/__init__.py','projects/engine.py','foundation/storage.py','foundation/__init__.py','experience/store.py','experience/chat.py','agentic/tools.py','agentic/engine.py')
def canonical(name,text):return ast.dump(ast.parse(text),include_attributes=False)
def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Missing or repeated integration anchor: '+old[:100])
    return text.replace(old,new,1)
def build(name,text,reference):
    if canonical(name,text)!=canonical(name,(Path(reference)/name).read_text()):raise ValueError('Unrecognised v1.30 source: '+name+'; nothing overwritten')
    if name=='repairs/__init__.py':text=once(text,'1.30.0','1.31.0')
    elif name=='hosted/boundary.py':text=once(text,"'version':'1.30.0'","'version':'1.31.0'")
    elif name=='navigation/web.py':text+='\n    from superhuman.milestones.web import install as install_milestones\n    install_milestones(app)\n'
    elif name=='navigation/shell.py':
        text=once(text,"if path.startswith(('/team/projects/'","if path.startswith(('/project-hub','/milestone','/project-leadership','/team/projects/'")
        text=once(text,"('/suggested-work','Suggested work'))","('/suggested-work','Suggested work'),('/project-leadership','Milestone projects'))")
    elif name=='workspace/web.py':
        text=once(text,"'<div class=\"ux-head\"><div><h1>Projects</h1>","'<div class=\"ux-head\"><div><h1>Projects</h1>") if False else text
        text=once(text,"    body+='<p>'+str(len(items))+' projects", "    body+='<p>'+link('/project-leadership','Project leadership & milestones')+'</p>'\n    body+='<p>'+str(len(items))+' projects")
    elif name=='workspace/model.py':
        text=once(text,'    unique={}',"    from superhuman.milestones.store import listing as milestones\n    for m in milestones(path=path):\n        if m['state'] in ('owner_review','needs_owner'):out.append(dict(title='M'+str(m['ordinal'])+' · '+m['title'],reason='Milestone strategic approval' if m['state']=='owner_review' else 'Milestone requires owner inspection',url='/milestones/'+m['id']))\n    unique={}")
    elif name=='team/web.py':
        text=once(text,"        body='<p>'+link('/team','Team')+'</p><h1>'+E(q['title'])", "        from superhuman.milestones.store import managed as milestone_project\n        if milestone_project(ident):\n            from superhuman.milestones.web import project_page\n            return project_page(ident)\n        body='<p>'+link('/team','Team')+'</p><h1>'+E(q['title'])")
        text=once(text,"        return page(body,q['title'])", "        body+='<p>'+link('/project-hub/'+ident,'Set up project leadership and milestones')+'</p>'\n        return page(body,q['title'])")
    elif name=='team/store.py':
        text=once(text,"    parent=project(project_id,path)\n    if owner not in EMPLOYEES", "    from superhuman.milestones.workflow import guard_create,task_limit\n    guard_create(project_id,actor,path)\n    parent=project(project_id,path)\n    if owner not in EMPLOYEES")
        text=once(text,"existing={r['id']:r for r in tasks(path)}","existing={r['id']:dict(r) for r in (_db.execute('SELECT * FROM team_tasks').fetchall() if _db is not None else tasks(path))}")
        text=once(text,"if actor!='owner' and len([r for r in existing.values() if r['project_id']==project_id])>=12:","if actor!='owner' and len([r for r in existing.values() if r['project_id']==project_id])>=task_limit(project_id,path):")
    elif name=='team/work.py':
        text=once(text,'import json,time','import json,time\nfrom contextlib import nullcontext')
        text=once(text,"    settings=store.settings(path)","    from superhuman.milestones.store import task_gate\n    permitted,reason=task_gate(item,path)\n    if not permitted:return False,reason\n    settings=store.settings(path)")
        text=once(text,"    allowed=json.loads(employee['allowed_tools'])", "    allowed=json.loads(employee['allowed_tools'])\n    from superhuman.milestones.store import assignment as milestone_assignment\n    if milestone_assignment(item['id'],path):allowed=[n for n in allowed if n!='team.handoff']")
        text=once(text,"    if len(instruction)>12000:","    if milestone_assignment(item['id'],path):instruction=instruction.replace('Use the team handoff tool for help;', 'Use the project lead and milestone work packages for collaboration;')\n    if len(instruction)>12000:")
        text=once(text,"def review(ident,expected,approve,note,actor='twin',path=p.DEFAULT_DB):", "def review(ident,expected,approve,note,actor='twin',path=p.DEFAULT_DB,_db=None,milestone_authority=False):\n    from superhuman.milestones.workflow import review_guard\n    review_guard(ident,actor,approve,milestone_authority,path)")
        text=once(text,"if actor!='owner' and item['attempts']>=2:","if actor!='owner' and not approve and item['attempts']>=2:")
        start=text.index('def review(');end=text.index('\ndef task_control',start);part=text[start:end]
        part=once(part,"    with p.connect(path) as db:\n        db.execute('BEGIN IMMEDIATE')","    with (p.connect(path) if _db is None else nullcontext(_db)) as db:\n        if _db is None:db.execute('BEGIN IMMEDIATE')")
        part=once(part,'    refresh(path)','    if _db is None:refresh(path)');text=text[:start]+part+text[end:]
        text=once(text,"    item=owned_run(run['project_id'],path)\n    if not item:raise ValueError('Team tool requires an assigned employee task')","    item=owned_run(run['project_id'],path)\n    if not item:raise ValueError('Team tool requires an assigned employee task')\n    from superhuman.milestones.store import assignment\n    if name=='team.handoff' and assignment(item['id'],path):raise ValueError('Milestone collaboration uses the project lead and approved roster; request a scoped assignment through the milestone workspace')")
        text=once(text,"    return personality.instruction(item['owner'],path)+", "    from superhuman.milestones.workflow import task_context\n    body['milestone_workspace']=task_context(item,path)\n    return personality.instruction(item['owner'],path)+")
    elif name=='team/engine.py':
        text=once(text,"    key={'tasks':", "    from superhuman.milestones.store import managed\n    managed_tasks={t['id'] for t in tasks if managed(t['project_id'],path)}\n    managed_projects={q['id'] for q in projects if managed(q['id'],path)}\n    signals=[s for s in signals if s.get('entity') not in managed_tasks|managed_projects]\n    tasks=[t for t in tasks if t['id'] not in managed_tasks]\n    projects=[q for q in projects if not managed(q['id'],path)]\n    key={'tasks':")
        text=once(text,"    action=d['action'];ident=d['task_id']", "    action=d['action'];ident=d['task_id']\n    from superhuman.milestones.store import managed\n    if ident and managed(store.task(ident,path)['project_id'],path):raise ValueError('This task follows its delegated milestone workflow')")
    elif name=='hosted/worker.py':
        text=once(text,'        recover_team(path)',"        recover_team(path)\n        from superhuman.milestones.engine import recover as recover_milestones\n        recover_milestones(path)")
        text=once(text,"                                if result is None:result=team_engine.tick(path,actual)","                                if result is None:\n                                    from superhuman.milestones.engine import tick as milestone_tick\n                                    result=milestone_tick(path,actual)\n                                if result is None:result=team_engine.tick(path,actual)")
    elif name=='projects/engine.py':text=once(text,"def review(pid,tid,action,note='',path=DEFAULT_DB):", "def review(pid,tid,action,note='',path=DEFAULT_DB):\n    from superhuman.milestones.store import assignment\n    from superhuman.team.work import owned_run\n    owned=owned_run(pid,path)\n    if owned and assignment(owned['id'],path):raise ValueError('Use the milestone review workflow for this assignment')")
    elif name=='foundation/__init__.py':text=once(text,"VERSION='1.30.0'","VERSION='1.31.0'")
    elif name=='foundation/storage.py':
        text=once(text,"def initialize(path=p.DEFAULT_DB):\n    team.initialize(path)","def initialize(path=p.DEFAULT_DB):\n    from superhuman.departments.store import readonly,tables\n    with readonly(path) as db:\n        if {'storage_items','storage_versions'}<=tables(db):return\n    team.initialize(path)")
        text=once(text,"def allowed(item,employee,project_id='',maximum='internal'):","def allowed(item,employee,project_id='',maximum='internal',path=p.DEFAULT_DB):")
        text=once(text,"    access=json.loads(item['access'])", "    from superhuman.milestones.store import share_allowed\n    if share_allowed(item,employee,project_id,path):return True\n    access=json.loads(item['access'])")
        text=text.replace('allowed(r,employee,project_id,maximum)','allowed(r,employee,project_id,maximum,path)').replace('allowed(item,scope,pid,maximum)','allowed(item,scope,pid,maximum,path)').replace("allowed(item,receipt['employee'],receipt['project_id'],receipt['maximum'])","allowed(item,receipt['employee'],receipt['project_id'],receipt['maximum'],path)")
    elif name=='experience/store.py':
        text=once(text,"    if target and employee not in ('twin',target['scope']):raise ValueError('Project chat belongs to its department or the Twin')", "    from superhuman.milestones.store import roster,managed\n    members=roster(project_id,path) if kind=='team' and managed(project_id,path) and managed(project_id,path)['share_outputs'] else []\n    if target and employee not in ('twin',target['scope']) and employee not in members:raise ValueError('Project chat belongs to its department, approved project team or the Twin')")
    elif name=='experience/chat.py':
        text=once(text,"    if 'room_version' not in trace:return","    from superhuman.milestones.store import managed,roster\n    current=store.room(claimed['thread_id'],path)\n    if current and current['project_kind']=='team' and managed(current['project_id'],path):\n        cfg=managed(current['project_id'],path)\n        if not cfg['share_outputs'] or current['employee'] not in roster(current['project_id'],path):raise ValueError('Project team sharing changed during reply')\n    if 'room_version' not in trace:return")
        text=once(text,"    context['writing_skill']=", "    if r['project_kind']=='team':\n        from superhuman.milestones.store import managed,roster,listing\n        cfg=managed(r['project_id'],path)\n        if cfg:\n            if not cfg['share_outputs'] or r['employee'] not in roster(r['project_id'],path):raise ValueError('Project team sharing was revoked')\n            context['project_lead']=cfg['lead'];context['milestones']=[{k:m[k] for k in ('id','ordinal','title','question','state')} for m in listing(r['project_id'],path)]\n    context['writing_skill']=")
    elif name=='agentic/engine.py':text=once(text,"'observation_excerpt':store.encode(result)[:6000]","'observation_excerpt':store.encode(result)[:30000 if a['tool'] in ('storage.pdf_pages','milestone.read_output') else 6000]")
    elif name=='agentic/tools.py':
        text=once(text," spec('workspace.list'"," spec('milestone.read_output','Read a permitted milestone contribution or approved prior result in full.','read_workspace',{'task_id':str},('task_id',)),\n spec('workspace.list'")
        text=once(text,"    if name.startswith('team.'):","    if name=='milestone.read_output':\n        from superhuman.milestones.workflow import read_output\n        return outcome(read_output(run,args['task_id'],path))\n    if name.startswith('team.'):")
        text=once(text,"    data=json.loads(action['result_json'] or '{}');tool=action['tool'];args=json.loads(action['arguments_json'])","    data=json.loads(action['result_json'] or '{}');tool=action['tool'];args=json.loads(action['arguments_json'])\n    if data.get('milestone_output_receipt'):\n        from superhuman.milestones.workflow import verify_output_receipt\n        verify_output_receipt(data['milestone_output_receipt'],path)")
        text=once(text," spec('workspace.list'"," spec('milestone.note','Save a versioned working note for this milestone; never approves facts.','team_collaboration',{'key':str,'content':str,'expected_version':int},('key','content','expected_version'),mutates=True),\n spec('workspace.list'")
        text=once(text,"    if name.startswith('team.'):","    if name=='milestone.note':\n        from superhuman.milestones.pdf import note\n        return outcome(note(run,args['key'],args['content'],args['expected_version'],path))\n    if name.startswith('team.'):")
        text=once(text," spec('workspace.list'", " spec('storage.pdf_pages','Read up to five complete PDF text pages from a permitted Storage source; no OCR.','read_workspace',{'item_id':str,'start_page':int,'end_page':int},('item_id','start_page','end_page')),\n spec('workspace.list'")
        text=once(text,"    if name.startswith('team.'):","    if name=='storage.pdf_pages':\n        from superhuman.milestones.pdf import read_pages\n        return outcome(read_pages(run,args['item_id'],args['start_page'],args['end_page'],path))\n    if name.startswith('team.'):")
    ast.parse(text);return text
