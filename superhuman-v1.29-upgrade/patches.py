"""Exact v1.28 integration. Existing CLI and execution implementations are retained."""
import ast
from pathlib import Path
FILES=('navigation/shell.py','navigation/web.py','departments/store.py','departments/web.py','experience/web.py','experience/store.py','experience/chat.py','experience/inbox.py','experience/assets/workspace.js','hosted/boundary.py','repairs/__init__.py','repairs/web.py','team/web.py')
def canonical(name,text):return text.strip() if name.endswith('.js') else ast.dump(ast.parse(text),include_attributes=False)
def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Missing or repeated source anchor: '+old[:100])
    return text.replace(old,new,1)
def build(name,text,reference):
    if canonical(name,text)!=canonical(name,(Path(reference)/name).read_text()):raise ValueError('Unrecognised v1.28 source: '+name+'; nothing overwritten')
    if name=='repairs/__init__.py':text=once(text,'1.28.0','1.29.0')
    elif name=='hosted/boundary.py':text=once(text,"'version':'1.28.0'","'version':'1.29.0'")
    elif name=='navigation/web.py':text+='\n    from superhuman.workspace.web import install as install_workspace\n    install_workspace(app)\n'
    elif name=='navigation/shell.py':
        text=once(text,"('/team','/talk','/assistant')","('/twin','/team','/talk','/assistant','/room-controls','/room-live','/room-fragment')")
        text=once(text,"'/suggested-work','/tasks')","'/suggested-work','/tasks','/new-project','/new-task','/workspace-projects','/workspace-tasks')")
        text=once(text,"'team':(('/team-room','Team Room'),('/team-room?tab=board','Employee board'),('/team-room?tab=feed','Team activity'))","'team':(('/twin','Mahnoor Twin'),('/team-room','Conversations'),('/team-room?tab=board','Employees'),('/team-room?tab=feed','Activity'))")
        text=once(text,'</script></head><body>','</script><link rel="stylesheet" href="/assets/workspace-v129.css"><script src="/assets/workspace-v129.js" defer></script></head><body>')
        text=once(text,'    if not signed_in:return head+',"    if not signed_in:\n        head=head.split('<link rel=\"stylesheet\"',1)[0]+'</head><body>'\n        return head+")
        text=once(text,"if request_path.get()==url else ''","if current_link(url) else ''")
        text=once(text,'def contextual_links(key):',"def current_link(url):\n    from urllib.parse import urlsplit,parse_qs\n    parsed=urlsplit(url);query=parse_qs(request_query.get())\n    if parsed.path!=request_path.get():return False\n    if parsed.query:return all(query.get(k)==v for k,v in parse_qs(parsed.query).items())\n    return not (parsed.path=='/team-room' and query.get('tab',['room'])[0] in ('board','feed'))\n\ndef contextual_links(key):")
        text=once(text,"request_path = ContextVar", "request_query = ContextVar('superhuman_navigation_query',default='')\nrequest_path = ContextVar")
        text=once(text,"token=request_path.set(scope.get('path','/'))","token=request_path.set(scope.get('path','/'));query_token=request_query.set(scope.get('query_string',b'').decode('latin-1'))")
        text=once(text,'finally:request_path.reset(token)','finally:request_path.reset(token);request_query.reset(query_token)')
        text=once(text,"<a href=\"/team/projects/'+pid+'\">Project & tasks</a><a href=\"/project-rooms/'+pid+'\">Conversations</a>","<a href=\"/team/projects/'+pid+'\"'+(' aria-current=\"page\"' if path.startswith('/team/projects/') else '')+'>Project & tasks</a><a href=\"/project-rooms/'+pid+'\"'+(' aria-current=\"page\"' if path.startswith('/project-rooms/') else '')+'>Conversations</a>")
    elif name=='departments/store.py':
        text=once(text,"    tasks=data['tasks'];projects=data['projects']","    from superhuman.workspace.model import merge\n    try:data=merge(data,path or p.DEFAULT_DB)\n    except sqlite3.Error:data['warnings'].append('Managed project records could not be read. Counts may be incomplete.')\n    tasks=data['tasks'];projects=data['projects']")
        # All generated department next-step links use the normalized record destination.
        for var,prefix,key in [('p','/work/','id'),('t','/projects/','project_id')]:
            old="'"+prefix+"'+"+var+"['"+key+"']"
            text=text.replace(old,var+".get('url',"+old+")")
    elif name=='departments/web.py':
        text=text.replace('Objectives','Projects').replace('Create an objective','Create project')
        anchor="        for warning in d['warnings']:body+='<p class=\"error\">'+esc(warning)+'</p>'"
        text=once(text,anchor,anchor+"\n        if tab in ('summary','projects','activity'):\n            from superhuman.workspace.web import department_body\n            return render(body+department_body(d,tab,page),d['name']+' · '+tab.capitalize())")
        text=once(text,"'/projects?'+urlencode({'workstream':scope})+'#new-project'","'/new-project?'+urlencode({'scope':scope})") if "'/projects?'+urlencode({'workstream':scope})+'#new-project'" in text else text
        text=once(text,'href="/projects?\'+urlencode({\'workstream\':scope})+\'#new-project','href="/new-project?\'+urlencode({\'scope\':scope})+\'') if 'href="/projects?\'+urlencode({\'workstream\':scope})+\'#new-project' in text else text
    elif name=='team/web.py':
        text=once(text,'E=shell.esc','from superhuman.workspace import model as uxmodel\nE=shell.esc')
        text=text.replace("'/team/twin'","'/twin'")
        text=once(text,"E(v)+'</option>'", "E(uxmodel.NAMES.get(v,v) if name=='owner' else uxmodel.ROLES.get(v,v) if name=='scope' else uxmodel.label(v))+'</option>'")
        text=text.replace("E(t['owner'])", "E(store.EMPLOYEES[t['owner']][0])")
        text=once(text,'<form method="post" action="/team/projects/\'+ident+\'/governance">','<details><summary>Project controls</summary><form method="post" action="/team/projects/\'+ident+\'/governance">')
        text=once(text,'Update project governance</button></form><h2>Tasks</h2>','Update project governance</button></form></details><p><a href="/new-task?project_id=\'+ident+\'">Add task</a></p><h2>Tasks</h2>')
        text=once(text,'Add a task yourself','Advanced task assignment')
    elif name=='experience/chat.py':
        text=once(text,'    return messages,', '    from superhuman.workspace.chat import augment\n    messages,trace=augment(claimed,messages,')
        # The original trace expression now belongs to augment; finish its call explicitly.
        anchor="'history_chars':used}"
        text=once(text,anchor,anchor+",path)\n    return messages,trace")
        text=once(text,"    if 'room_version' not in trace:return","    from superhuman.workspace.chat import validate as validate_context\n    validate_context(claimed,trace,path)\n    if 'room_version' not in trace:return")
    elif name=='experience/store.py':
        # Return project identity and a room-specific chat destination for complete board refresh.
        text=once(text,'    return results',"    for item in results:\n        assignment=item['task']\n        parent=team.project(assignment['project_id'],path) if assignment else None\n        item['project']={'id':parent['id'],'title':parent['title']} if parent else None\n    return results")
    elif name=='experience/inbox.py':
        text=once(text,'        if linked:continue',"        if linked:\n            linked['last_sync']=a['last_sync'];linked['last_error']=a['last_error']\n            continue")
        text=once(text,'    values=[];linked=set()',"    values=[];linked=set()\n    aliases={a['remote_id']:'c:'+a['id'] for a in comms.channels(path) if a['kind']=='email'}")
        text=once(text,"account='m:'+m['account_id']","account=aliases.get(m['account_id'],'m:'+m['account_id'])")
        text=once(text,"states.get(m['id'],'unreviewed')","states.get(m['id'],states.get('m:'+m.get('remote_id',''),'unreviewed'))")
    elif name=='experience/assets/workspace.js':
        text=once(text,'if(!r.ok)return;','if(!r.ok||r.redirected)throw new Error(\'Status unavailable\');')
        anchor="node.querySelector('[data-assignment]').textContent=e.task?e.task.title:e.assignment||'No active assignment';"
        text=once(text,anchor,anchor+"\n        const actions=node.querySelector('.ux-actions');\n        let task=actions.querySelector('[data-task-link]');\n        if(e.task){if(!task){task=document.createElement('a');task.setAttribute('data-task-link','');actions.append(task);}task.href='/team/tasks/'+encodeURIComponent(e.task.id);task.textContent='Open task';}else if(task)task.remove();\n        const project=node.querySelector('[data-project]');if(project){project.textContent=e.project?e.project.title:'';if(e.project)project.href='/team/projects/'+encodeURIComponent(e.project.id);else project.removeAttribute('href');}\n        const last=node.querySelector('[data-last-action]');if(last)last.textContent='Last recorded action: '+(e.last?e.last.action.replaceAll('_',' ')+' · '+new Date(e.last.created_at).toLocaleString():'No action recorded');")
    elif name=='experience/web.py':
        text=once(text,"body+='<p>'+link('/team/projects/'+parent['id'],parent['title'])+'</p>'","body+='<p><a data-project href=\"/team/projects/'+parent['id']+'\">'+E(parent['title'])+'</a></p>'\n        else:body+='<p><a data-project></a></p>'")
        text=once(text,"body+='<small>Last recorded action: '","body+='<small data-last-action>Last recorded action: '")
        text=once(text,"(' '+link('/team/tasks/'+task['id'],'Open task') if task else '')","(' <a data-task-link href=\"/team/tasks/'+task['id']+'\">Open task</a>' if task else '')")
        text=once(text,"state,selected,q,page)","state,selected,q,page)") if False else text
        text=once(text,"body+='<div class=\"ux-preview\">'+E(m['body'])+'</div><form method=\"post\" action=\"/inbox-review\">'+hidden('ident',m['id'])", "body+='<div class=\"ux-preview\">'+E(m['body'])+'</div><form method=\"post\" action=\"/inbox-actions/review\">'+hidden('return_to',query(selected=m['id']))+hidden('ident',m['id'])")
        anchor="        body+='<p>'+link(m['url'],'Open original workspace')+'</p><p class=\"muted\">Reply drafts are local. Nothing is sent from this screen.</p>'"
        text=once(text,anchor,"        from superhuman.workspace.web import inbox_actions\n        body+=inbox_actions(m,query(selected=m['id']))\n"+anchor)
        text=once(text,"    if len(all_events)>1000:","    from superhuman.workspace.web import calendar_tools,deadline_chips\n    body+=calendar_tools(view,current)\n    if len(all_events)>1000:")
        text=once(text,"''.join(link(url(v=v),v.capitalize()) for v in ('month','week','day','agenda'))",'\'\'.join(\'<a href="\'+E(url(v=v))+\'"\'+(\' aria-current="page"\' if v==view else \'\')+\'>\'+v.capitalize()+\'</a>\' for v in (\'month\',\'week\',\'day\',\'agenda\'))')
        text=once(text,"            body+='</section>'\n        body+='</div>'","            body+=deadline_chips(d)\n            body+='</section>'\n        body+='</div>'")
        text=once(text,"            body+='<div class=\"ux-timeday\">'","            body+='<div class=\"ux-timeday\">'") if False else text
        text=once(text,"view=day'", "view=day'") if False else text
        text=once(text,"        body+='<section class=\"card\"><h2>'+E(m['title'])", "        body+='<section class=\"card\" id=\"meeting-'+m['id']+'\"><h2>'+E(m['title'])")
        text=once(text,"action=\"/calendar-intake/'+m['id']+'/confirm\"","action=\"/meeting-preview/'+m['id']+'\"")
        text=once(text,"field('Original IANA timezone or UTC','zone',m['zone'])","field('Original IANA timezone (optional if time has UTC offset)','zone',m['zone']).replace(' required','')")
        text=once(text,'Confirm meeting in PKT calendar','Preview PKT time and conflicts')
        # A day view offers one clear date-specific create action.
        text=once(text,"    if not events:body+=", "    if view=='day':body+='<p>'+link('/calendar/new?day='+current.isoformat(),'Add meeting on this date')+'</p>'\n    if not events:body+=")
    elif name=='repairs/web.py':
        text=once(text,'def attention_items():','def legacy_attention_items():')
        text=once(text,'def attention_link():',"def attention_items():\n    from superhuman.workspace.model import decisions\n    return decisions()\n\ndef attention_link():")
    if name.endswith('.py'):ast.parse(text)
    return text
