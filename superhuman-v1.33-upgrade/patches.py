"""Exact v1.32 presentation integration; execution and source schemas remain intact."""
import ast
from pathlib import Path
FILES=('navigation/shell.py','navigation/web.py','workspace/web.py','experience/web.py','milestones/web.py','assurance/web.py','foundation/web.py','departments/web.py','planning/web.py','team/web.py','foundation/__init__.py','repairs/__init__.py','hosted/boundary.py','workspace/model.py')
def canonical(name,text):return ast.dump(ast.parse(text),include_attributes=False)
def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Missing or repeated interface anchor: '+old[:90])
    return text.replace(old,new,1)
def replace_function(text,name,body):
    node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name==name)
    lines=text.splitlines(keepends=True);return ''.join(lines[:node.lineno-1])+body.rstrip()+'\n\n'+''.join(lines[node.end_lineno:])
def delegate(text,name,module,target,args):
    text=once(text,'def '+name+'(', 'def _v132_'+name+'(')
    return text+'\n\ndef '+name+'('+args+'):\n    from '+module+' import '+target+'\n    return '+target+'('+args+',_v132_'+name+')\n'
def build(name,text,reference):
    if canonical(name,text)!=canonical(name,(Path(reference)/name).read_text()):raise ValueError('Unrecognised v1.32 source: '+name+'; nothing overwritten')
    if name in ('foundation/__init__.py','repairs/__init__.py','hosted/boundary.py'):text=once(text,'1.32.0','1.33.0')
    elif name=='navigation/shell.py':
        text=once(text,'def project_tabs(path):','from superhuman.interface.chrome import BASE_STYLE\nSTYLE += BASE_STYLE\n\ndef project_tabs(path):')
        text=once(text,"('tasks','/projects/'+p,'Tasks'),", "('tasks','/projects/'+p,'Plan & work'),")
        text=once(text,"('knowledge','/workspace/projects/'+p+'/knowledge','Knowledge'),", "('knowledge','/workspace/projects/'+p+'/knowledge','Files & evidence'),")
        text=once(text,"def contextual_links(key):", "def _v132_contextual_links(key):")
        text+='\n\ndef contextual_links(key):\n    from superhuman.interface.chrome import contextual\n    if request_path.get().startswith(\"/twin\"):return \"\"\n    value=contextual(key)\n    return _v132_contextual_links(key) if value is None else value\n'
        text=once(text,"def page(body,title='Superhuman',signed_in=True):", "def page(body,title='Superhuman',signed_in=True):\n    from superhuman.interface.chrome import capturing,reflow,icon\n    if capturing.get():return body\n    body=reflow(body,request_path.get())")
        text=once(text,'<script src="/assets/workspace-v129.js" defer></script></head>', '<script src="/assets/workspace-v129.js" defer></script><link rel="stylesheet" href="/assets/interface.css?v=133"><script src="/assets/interface.js?v=133" defer></script></head>')
        text=once(text,"'>'+name+'</a>' for k,url,name in NAV)","'>'+icon(k)+name+'</a>' for k,url,name in NAV)")
        text=once(text,"<strong>'+label+'</strong><br><span>'+esc(title)+'</span>","<strong>'+label+'</strong>")
        text=once(text,"(project_tabs(path) or contextual_links(key))+body", "('' if ' data-interface-tabs>' in body else (project_tabs(path) or contextual_links(key)))+body")
    elif name=='navigation/web.py':
        text+='\n    from superhuman.interface.web import install as install_interface\n    install_interface(app)\n'
        text=once(text,"    def settings():\n        return render(", "    def settings():\n        from superhuman.interface.views import settings as workspace_settings\n        return workspace_settings()\n        return render(")
    elif name=='workspace/model.py':
        text=once(text,'    unique={}',"    from superhuman.interface.decisions import consolidate\n    out=consolidate(out,path)\n    unique={}")
    elif name=='workspace/web.py':
        text=replace_function(text,'overview',"def overview():\n    from superhuman.interface.views import overview as show_overview\n    return show_overview()")
        text=replace_function(text,'list_projects',"def list_projects(scope='all',q='',state='all',page=1,capability='all'):\n    from superhuman.interface.views import projects\n    return projects(scope,q,state,page,capability)")
        text=once(text,"def project_list(workstream:str='all',q:str='',state:str='all',page:int=1):", "def project_list(workstream:str='all',q:str='',state:str='all',page:int=1,capability:str='all'):")
        text=once(text,'return list_projects(workstream,q,state,page)','return list_projects(workstream,q,state,page,capability)')
        text=once(text,"        choices=[a for a in team.projects() if a['status']=='active']", "        from superhuman.milestones.store import managed\n        choices=[a for a in team.projects() if a['status']=='active' and not managed(a['id'])]\n        if not choices and any(managed(a['id']) for a in team.projects()):return render('<h1>Add milestone work</h1><p>Open a project milestone to add a scoped work package for its approved team.</p>'+link('/projects?capability=milestones','Choose a milestone project'),'Add work')")
        text=once(text,"    elif tab=='projects':\n        body+=", "    elif tab=='projects':\n        from superhuman.planning.presentation import summary_panel\n        body+='<section class=\"ui-notice\"><h2>Department priorities</h2>'+summary_panel(scope)+'<p>'+link('/department-plans/'+scope,'Manage plan & priorities')+'</p></section>'\n        body+=")
    elif name=='experience/web.py':
        text=once(text,"    if tab=='agent':return '<h2>Your department employee</h2>'+board(scope)+'<p>'+link('/team/employees/'+scope,'Charter, writing skill and permissions')+'</p>'", "    if tab=='agent':\n        from superhuman.supervision.web import panel\n        return '<h2>Your department employee</h2>'+board(scope)+'<p>'+link('/team/employees/'+scope,'Manage employee & writing skill')+'</p><h2>Department supervision</h2>'+panel(scope)+'<p>'+link('/supervision/'+scope,'Manage supervision')+'</p>'")
    elif name=='milestones/web.py':
        text=delegate(text,'project_page','superhuman.interface.views','project','pid')
        text=delegate(text,'milestone_page','superhuman.interface.views','milestone','mid')
        text=once(text,"    def projects():\n        body=", "    def projects():\n        from superhuman.interface.views import projects as project_list\n        return project_list(capability='milestones')\n        body=")
    elif name=='assurance/web.py':text=delegate(text,'evidence_page','superhuman.interface.views','evidence','mid')
    elif name=='foundation/web.py':
        text=once(text,"body+=form(r,r['scope'])+'<details><summary>Version history</summary>'", "body+=('<section class=\"ui-notice\"><h2>Saved fact</h2><p>'+E(r['content'])+'</p></section>' if r['kind']=='fact' else '')+'<p>'+E(r['status'].capitalize()+' · '+r['sensitivity'].capitalize()+' · Version '+str(r['version']))+'</p><details class=\"ui-disclosure\"><summary>Manage source & access</summary>'+form(r,r['scope'])+'</details><details><summary>Version history</summary>'")
        text=once(text,"optional('Project ID','project',project)","select('Project','project',[('','All projects')]+[(r['id'],r['name']) for r in __import__('superhuman.workspace.model',fromlist=['projects']).projects() if r['scope']==scope],project)")
    elif name=='departments/web.py':
        text=once(text,"if c['plans_review']+c['outputs_review']:return 'Needs your review'","if c['plans_review']+c['outputs_review']:return 'Review pending'")
        text=once(text,"Persistent employee & writing skill", "Agent & writing skill")
    elif name=='planning/web.py':
        # Shared department navigation is normalized by the renderer on every planning page.
        text=once(text,"<h2>'+E(title)+'</h2>'", "<h2>'+E(title)+'</h2><p>'+view.link('/departments/'+scope+'/projects','Back to department work')+'</p>'")
    elif name=='team/web.py':
        text=once(text,"            return project_page(ident)\n        body=", "            return project_page(ident)\n        from superhuman.interface.views import simple_project\n        return simple_project(ident)\n        body=")
        text=once(text,"<h1>'+E(e['name'])+'</h1><form method=", "<h1>'+E(e['name'])+'</h1><p>'+E(e['charter'])+'</p><p>Employee '+('paused' if e['paused'] else 'available under current controls')+'. See the employee board for actual saved assignment and worker status.</p><details class=\"ui-disclosure\"><summary>Manage employee permissions</summary><form method=")
        text=once(text,"</fieldset><button>Update employee</button></form>'", "</fieldset><button>Update employee</button></form></details>'")
        text=once(text,"<h2>Department writing skill</h2><form method=", "<details class=\"ui-disclosure\"><summary>Department writing skill</summary><form method=")
        text=once(text,"<button>Confirm writing skill</button></form>'", "<button>Confirm writing skill</button></form></details>'")
    ast.parse(text);return text
