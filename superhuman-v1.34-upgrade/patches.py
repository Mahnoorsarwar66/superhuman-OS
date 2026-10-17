"""Exact v1.33 integrations; guard source identity before touching installed files."""
import ast
from pathlib import Path
FILES=('capabilities/exports.py','interface/web.py','interface/decisions.py','navigation/shell.py','navigation/web.py','team/store.py','team/work.py','team/web.py','workspace/web.py','interface/views.py','experience/web.py','agentic/tools.py','milestones/engine.py','milestones/store.py','milestones/workflow.py','assurance/workflow.py','team/budget.py','foundation/__init__.py','repairs/__init__.py','hosted/boundary.py')
def canonical(name,text):return ast.dump(ast.parse(text),include_attributes=False)
def once(text,old,new):
 if text.count(old)!=1:raise ValueError('Missing or repeated v1.34 anchor: '+old[:100])
 return text.replace(old,new,1)
def build(name,text,reference):
 if canonical(name,text)!=canonical(name,(Path(reference)/name).read_text()):raise ValueError('Unrecognised v1.33 source: '+name+'; nothing overwritten')
 if name in ('foundation/__init__.py','repairs/__init__.py','hosted/boundary.py'):text=once(text,'1.33.0','1.34.0')
 elif name=='capabilities/exports.py':
  text=once(text,'def make_docx(path,title,text):', 'def _v133_make_docx(path,title,text):')
  text=once(text,'def make_pdf(path,title,text):', 'def _v133_make_pdf(path,title,text):')
  text+='\n\ndef make_docx(path,title,text):\n    from superhuman.practice.exports import docx\n    return docx(path,title,text)\n\ndef make_pdf(path,title,text):\n    from superhuman.practice.exports import pdf\n    return pdf(path,title,text)\n'
 elif name=='navigation/shell.py':
  text=once(text,'</script></head><body>', '</script><link rel="stylesheet" href="/assets/practice.css?v=134"><script src="/assets/practice.js?v=134" defer></script></head><body>')
  text=once(text,'</nav></details><footer>', '</nav></details><a class="practice-twin" href="/twin"><img src="/assets/agents/twin.png" width="40" height="40" alt="The Twin — illustrated AI employee"><span>The Twin<small>Your Superhuman</small></span></a><footer>')
  text=once(text,"('/project-hub','/milestone'", "('/project-briefs','/project-hub','/milestone'")
  text=once(text,"('/system-baseline','/proactive'", "('/operating-guide','/system-baseline','/proactive'")
 elif name=='interface/web.py':
  text=once(text,'def fallback(path):', "def fallback(path):\n    match=re.match(r'^/project-briefs/([a-f0-9]+)',path)\n    if match:return '/project-briefs/'+match[1]+'?step=5','Return to the project brief'")
 elif name=='interface/decisions.py':
  text=once(text,'    return result', '    from superhuman.practice.attention import items as project_attention\n    result.extend(project_attention(path))\n    return result')
 elif name=='navigation/web.py':text+='\n    from superhuman.practice.web import install as install_practice\n    install_practice(app)\n'
 elif name=='team/store.py':text=once(text,"    return ident\n\ndef create_task", "    from superhuman.practice.store import enroll\n    enroll(ident,path)\n    return ident\n\ndef create_task")
 elif name=='team/work.py':
  text=once(text,'def gate(item,path=p.DEFAULT_DB):', 'def gate(item,path=p.DEFAULT_DB):\n    from superhuman.practice.store import gate as interview_gate\n    allowed,why=interview_gate(item,path)\n    if not allowed:return False,why')
  text=once(text,"    return personality.instruction(item['owner'],path)", "    from superhuman.practice.store import context as project_context\n    body['project_interview']=project_context(item['project_id'],item['owner'],store.effective(item,path)['sensitivity'],path)\n    return personality.instruction(item['owner'],path)")
  text=once(text,"        runtime._insert_job(db,pid", "        from superhuman.practice.store import dispatch_check\n        dispatch_check(db,item)\n        runtime._insert_job(db,pid")
 elif name=='team/web.py':
  text=once(text,"return redirect('/team/projects/'+ident)\n    @app.post('/team/adopt')", "return redirect('/project-briefs/'+ident)\n    @app.post('/team/adopt')")
  text=once(text,"    def employee(ident:str):", "    def employee(ident:str):\n        from superhuman.practice.web import portrait")
  text=once(text,"<h1>'+E(e['name'])+'</h1>", "<div class=\"practice-person\">'+portrait(ident)+'<h1>'+E(e['name'])+'</h1></div>")
 elif name=='workspace/web.py':text=once(text,"return redirect('/team/projects/'+team.create_project(scope,title,objective,acceptance,priority,risk,sensitivity))", "return redirect('/project-briefs/'+team.create_project(scope,title,objective,acceptance,priority,risk,sensitivity))")
 elif name=='interface/views.py':
  text=once(text,'def project_summary(pid):','def project_summary(pid):\n    from superhuman.practice.web import panel\n    interview_panel=panel(pid)')
  text=once(text,"        return body\n    done=", "        return interview_panel+body+'<p>'+link('/project-briefs/'+pid+'/impact','Milestone impact')+'</p>'\n    done=")
  text=once(text,"    return body+'</section><div class=\"ui-quick-links\">'", "    return interview_panel+body+'</section><div class=\"ui-quick-links\">'+action_link('/project-briefs/'+pid+'/impact','Milestone impact')")
  text=once(text,"    body+='<div class=\"ui-facts\"><div><span>Needs your review", "    from superhuman.practice.web import portrait\n    body+='<section class=\"practice-hero\">'+portrait('twin')+'<div><p class=\"eyebrow\">Your Superhuman</p><h2>A clear next step, together.</h2><p>Bring a project, review a decision, or tell The Twin what has changed.</p><div class=\"ui-quick-links\">'+action_link('/new-project','Start a project')+action_link('/operating-guide','How your team works')+'</div></div></section>'\n    from superhuman.practice import store as practice\n    briefs=[q for q in team.projects() if practice.interview(q['id']) and not practice.current(q['id'])]\n    if briefs:\n        body+='<section class=\"practice-callout\"><div><h2>Project expectations need your input</h2><p>'+str(len(briefs))+' project briefs need confirmation before their managed work continues.</p></div>'+action_link('/project-briefs/'+briefs[0]['id'],'Continue interview')+'</section>'\n    body+='<div class=\"ui-facts\"><div><span>Needs your review")
 elif name=='experience/web.py':
  text=once(text,"def board(scope=None):", "def board(scope=None):\n    from superhuman.practice.web import portrait")
  text=once(text,"E(item['name'][0])", "portrait(ident)")
 elif name=='agentic/tools.py':
  text=once(text,"REGISTRY={t.name:t for t in [", "REGISTRY={t.name:t for t in [\n spec('project.interview','Propose one project-specific owner question with reason; no answers, approvals or permissions are changed.','team_collaboration',{'question':str,'reason':str},('question','reason'),mutates=True),")
  text=once(text,"    if name.startswith('assurance.'):", "    if name=='project.interview':\n        from superhuman.practice.store import propose\n        return outcome({'question_id':propose(run,args['question'],args['reason'],path),'status':'proposed; waiting for owner answer'})\n    if name.startswith('assurance.'):")
 elif name=='milestones/engine.py':
  text=once(text,"    body['approved_prior_milestones']=prior[-3:]", "    from superhuman.practice.store import signature\n    key['project_interview']=signature(q['id'],path)\n    body['approved_prior_milestones']=prior[-3:]")
  text=once(text,"    work.refresh(path)", "    from superhuman.practice.store import auto_start\n    started=auto_start(path)\n    if started:return started\n    work.refresh(path)")
  text=once(text,"            payload=json.dumps(body,ensure_ascii=False)", "            from superhuman.practice.store import context as project_context\n            body['project_interview']=project_context(m['project_id'],actor,ceiling,path)\n            payload=json.dumps(body,ensure_ascii=False)")
  text=once(text,"            with budget.scope(actor):", "            from superhuman.practice.billing import scope as project_billing\n            with budget.scope(actor),project_billing(m['project_id'],m['id']):")
 elif name=='milestones/store.py':
  text=once(text,'def active(mid,path=p.DEFAULT_DB):', "def active(mid,path=p.DEFAULT_DB):\n    from superhuman.practice.store import hold\n    if hold(milestone(mid,path)['project_id'],path):return False,'Confirm the current project interview before continuing'")
  text=once(text,'def start(mid,expected,path=p.DEFAULT_DB):', "def start(mid,expected,path=p.DEFAULT_DB):\n    from superhuman.practice.store import hold\n    if hold(milestone(mid,path)['project_id'],path):raise ValueError('Confirm the current project interview before starting')")
 elif name=='milestones/workflow.py':
  text=once(text,'def approve(mid,expected,packet_id,note,path=p.DEFAULT_DB):', "def approve(mid,expected,packet_id,note,path=p.DEFAULT_DB):\n    from superhuman.practice.store import hold\n    if hold(s.milestone(mid,path)['project_id'],path):raise ValueError('Project brief changed; confirm and re-review before approving')")
 elif name=='assurance/workflow.py':
  text=once(text,"    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()", "    from superhuman.practice.store import signature\n    interview_signature=signature(m['project_id'],path)\n    if interview_signature!='legacy':payload['project_interview']=interview_signature\n    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()")
 elif name=='team/budget.py':
  text=once(text,'    return ident\n\ndef value', '        from superhuman.practice.billing import link\n        link(db,ident)\n    return ident\n\ndef value')
 ast.parse(text);return text
