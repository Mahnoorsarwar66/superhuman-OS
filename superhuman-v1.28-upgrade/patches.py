"""Exact source guards over v1.27. Legacy CLI / orchestrator variants are untouched."""
import ast
from pathlib import Path
FILES=('navigation/shell.py','navigation/web.py','departments/web.py','dialogue/engine.py','taskdesk/store.py','hosted/boundary.py','hosted/worker.py','repairs/__init__.py','team/store.py')
def canonical(name,text):return ast.dump(ast.parse(text),include_attributes=False)
def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Integration source anchor missing or repeated: '+old[:100])
    return text.replace(old,new,1)
def build(name,text,reference):
    if canonical(name,text)!=canonical(name,(Path(reference)/name).read_text()):raise ValueError('Unrecognised v1.27 source: '+name+'; nothing overwritten')
    if name=='repairs/__init__.py':text=once(text,'1.27.0','1.28.0')
    elif name=='hosted/boundary.py':
        text=once(text,"'version':'1.27.0'","'version':'1.28.0'")
        text=once(text,"script-src 'none'","script-src 'self'")
        text=once(text,'microphone=()','microphone=(self)')
    elif name=='hosted/worker.py':
        text=once(text,'        recover_comms(path)','        recover_comms(path)\n        from superhuman.experience.store import initialize as initialize_experience\n        initialize_experience(path)')
        text=once(text,"                    if mail_result:\n                        result=mail_result","                    if mail_result:\n                        from superhuman.experience.calendar import collect as collect_invitations\n                        collect_invitations(path)\n                        result=mail_result")
    elif name=='team/store.py':
        names={'EdSync Strategy':'Katherine','EdSync Product':'James','Career Algorithm R&D':'Amelia','Sales & Marketing':'Sarah','Graduate Applications':'Jose','Investors & Grants':'Chris','Legal & Operations':'Sam'}
        for old,new in names.items():text=once(text,"('"+old+"',","('"+new+"',")
    elif name=='navigation/shell.py':
        start=text.index('NAV = ');end=text.index('\ndef esc',start)
        text=text[:start]+'''NAV = (('overview','/','Overview'),('team','/team-room','Team'),('departments','/departments','Departments'),('projects','/projects','Projects'),('inbox','/inboxes','Inbox'),('calendar','/calendar','Calendar'),('coding','/coding','Coding'),('reviews','/reviews','Reviews'),('knowledge','/knowledge','Knowledge'),('settings','/settings','Settings'))
'''+text[end:]
        start=text.index('def section(');end=text.index('\nSTYLE =',start)
        text=text[:start]+'''def section(path):
    if path=='/' or path.startswith(('/briefing','/memory/briefing')):return 'overview'
    if path.startswith(('/team/projects/','/team/tasks/','/project-rooms/','/workspace/projects/','/projects','/work/','/project-tasks','/suggested-work','/tasks')):return 'projects'
    if path.startswith(('/departments','/department-plans','/supervision','/priorities')):return 'departments'
    if path.startswith(('/team','/talk','/assistant')):return 'team'
    if path.startswith(('/inboxes','/mail','/inbox-review')):return 'inbox'
    if path.startswith(('/calendar','/meetings')):return 'calendar'
    if path.startswith('/coding'):return 'coding'
    if path.startswith(('/reviews','/attention')):return 'reviews'
    if path.startswith(('/knowledge','/research-desk','/research-review','/tools','/documents')):return 'knowledge'
    if path.startswith(('/settings','/memory','/system-checks','/runtime','/queue','/agent-runs')):return 'settings'
    return 'overview'
'''+text[end:]
        text=once(text,"def project_tabs(path):\n",'''def project_tabs(path):
    team_match=re.fullmatch(r'/(?:team/projects|project-rooms)/([a-f0-9]+)',path)
    if team_match:
        pid=team_match.group(1)
        return '<nav class="shell-tabs" aria-label="Project navigation"><a href="/team/projects/'+pid+'">Project & tasks</a><a href="/project-rooms/'+pid+'">Conversations</a><a href="/project-tasks">All tasks</a><a href="/suggested-work">Suggested work</a></nav>'
''')
        text=once(text,"      'departments':(('/departments','Departments'),('/priorities','Priorities'),('/supervision','Supervision'),('/team','Team & Twin')),","      'departments':(),\n      'team':(('/team-room','Team Room'),('/team-room?tab=board','Employee board'),('/team-room?tab=feed','Team activity')),\n      'projects':(('/projects','Projects'),('/project-tasks','All tasks'),('/suggested-work','Suggested work')),")
        text=once(text,"('/inboxes/setup','Connection guide'))","('/inboxes/setup','Connection guide'),('/runtime','Worker status'),('/queue','Legacy jobs'))")
        text=once(text,"+'</style></head><body>'","+'</style><link rel=\"stylesheet\" href=\"/assets/workspace.css\"><script src=\"/assets/workspace.js\" defer></script></head><body>'")
    elif name=='navigation/web.py':
        start=text.index("            from superhuman.dialogue import store as dialogue",text.index('def project_context('));end=text.index("        elif tab=='knowledge':",start)
        text=text[:start]+"            from superhuman.experience.web import project_conversations\n            body+=project_conversations(pid,page)\n"+text[end:]
        text=once(text,"        body+='<h2>'+str(len(rows))+' objectives</h2>'+cards(rows)","        from superhuman.experience import store as experience\n        from superhuman.experience.web import link\n        from superhuman.team import store as team_store\n        body+='<h2>Governed projects</h2>'\n        for item in team_store.projects():\n            if workstream not in ('all',item['scope']):continue\n            body+='<section class=\"card\"><h3>'+link('/team/projects/'+item['id'],item['title'])+'</h3><p>'+e(item['objective'])+'</p><p>'+e(item['priority']+' · '+item['status'])+' · '+link('/project-rooms/'+item['id'],'Conversations')+'</p></section>'\n        body+='<p>'+link('/team','Create or adopt a governed project')+'</p>'\n        owned={t['run_id'] for t in team_store.tasks() if t['run_id']}\n        rows=[row for row in rows if row['id'] not in owned]\n        body+='<h2>'+str(len(rows))+' existing objectives</h2>'+cards(rows)")
        text+='\n    from superhuman.experience.web import install as install_experience\n    install_experience(app)\n'
    elif name=='departments/web.py':
        text=once(text,"('summary','projects','knowledge','conversations','activity')","('summary','projects','knowledge','conversations','activity','agent','supervision')")
        text=once(text,"('planning','Plan & Priorities')]","('planning','Plan & Priorities'),('agent','Agent'),('supervision','Supervision')]")
        text=once(text,"        body+=supervision_panel(scope)\n        if tab=='summary':","        if tab in ('agent','supervision'):\n            from superhuman.experience.web import department_panel\n            return render(body+department_panel(scope,tab),d['name']+' · '+tab.capitalize())\n        if tab=='summary':")
    elif name=='dialogue/engine.py':
        text=once(text,'    if mail_context is not None: return mail_context','    if mail_context is not None: return mail_context\n    from superhuman.experience.chat import prompt as room_prompt\n    room_context=room_prompt(claimed,path)\n    if room_context is not None:return room_context')
        anchor="        response = wrap(client,path).chat.completions.create(";start=text.index(anchor);end=text.index("        if not response.choices:",start)
        block=text[start:end];block='    '+block.replace('\n','\n    ').rstrip()+'\n'
        text=text[:start]+"        from superhuman.experience.chat import actor\n        from superhuman.team.budget import scope as billing_scope\n        with billing_scope(actor(claimed['thread_id'],path)):\n"+block+text[end:]
        text=once(text,"        store.finish(claimed, parsed['reply']", "        from superhuman.experience.chat import validate as validate_room\n        validate_room(claimed,trace,path)\n        store.finish(claimed, parsed['reply']")
    elif name=='taskdesk/store.py':
        text=once(text,"    title=d.text(title,180,'Task title');details=d.text(details,6000,'Task instructions')","    from superhuman.experience.store import room\n    if room(thread_id,path):raise ValueError('Review this suggestion in Team Room to keep governed project approvals')\n    title=d.text(title,180,'Task title');details=d.text(details,6000,'Task instructions')")
    ast.parse(text);return text
