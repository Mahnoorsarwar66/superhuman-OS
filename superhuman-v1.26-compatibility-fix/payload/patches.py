"""Guarded team integration against delivered v1.25 source."""
import ast
from pathlib import Path
FILES=('hosted/worker.py', 'hosted/boundary.py', 'navigation/web.py', 'navigation/shell.py', 'departments/web.py', 'repairs/__init__.py', 'repairs/web.py', 'repairs/checks.py', 'repairs/scheduler.py', 'projects/engine.py', 'agentic/web.py', 'agentic/engine.py', 'agentic/tools.py', 'identity/selection.py', 'supervision/engine.py', 'collab/runner.py', 'research/runner.py', 'dialogue/engine.py', 'cli.py')
OPTIONAL_ORCHESTRATOR='core/orchestrator.py'
def canonical(name,text):return ast.dump(ast.parse(text),include_attributes=False)
def source_files(root):
    return FILES+((OPTIONAL_ORCHESTRATOR,) if (Path(root)/'superhuman'/OPTIONAL_ORCHESTRATOR).is_file() else ())
def manifest_files(manifest):
    found=set(manifest['before_hashes'])
    if found not in ({'superhuman/'+n for n in FILES},{'superhuman/'+n for n in FILES+(OPTIONAL_ORCHESTRATOR,)}):raise ValueError('Backup has an unrecognised source-file set; nothing changed')
    return tuple(n for n in FILES+(OPTIONAL_ORCHESTRATOR,) if 'superhuman/'+n in found)
def expected_source(name,actual,reference):
    before=Path(reference)/name
    if name=='cli.py' and canonical(name,actual)==canonical(name,(Path(reference)/'production_cli.py').read_text(encoding='utf-8')):before=Path(reference)/'production_cli.py'
    return build(name,before.read_text(encoding='utf-8'),reference)
def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Repair source anchor missing or repeated: '+old[:100])
    return text.replace(old,new,1)
def function(text,name,replacement):
    node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name==name)
    lines=text.splitlines(True)
    return ''.join(lines[:node.lineno-1])+replacement+'\n'+''.join(lines[node.end_lineno:])
def build(name,text,reference):
    if name=='cli.py' and canonical(name,text)==canonical(name,(Path(reference)/'production_cli.py').read_text(encoding='utf-8')):
        # This reviewed CLI delegates all model work to the companion orchestrator.
        # Preserve its database schema, commands, routing and review behaviour.
        return text
    if canonical(name,text)!=canonical(name,(Path(reference)/name).read_text(encoding='utf-8')):raise ValueError('Unrecognised v1.25 source: '+name+'; nothing overwritten')
    if name==OPTIONAL_ORCHESTRATOR:
        text=once(text,'    client = OpenAI(api_key=api_key)','    client = OpenAI(api_key=api_key, max_retries=0)\n    from superhuman.team.budget import wrap\n    client = wrap(client)')
    elif name=='hosted/boundary.py':
        text=once(text,"'version':'1.25.0'","'version':'1.26.0'")
    elif name=='repairs/__init__.py':
        text=once(text,'1.25.0','1.26.0')
    elif name=='hosted/worker.py':
        text=once(text,'        recover_supervision(path)','        recover_supervision(path)\n        from superhuman.team.engine import recover as recover_team\n        recover_team(path)')
        text=once(text,"                            activity['value']='working'","                            from superhuman.team.budget import wrap as meter\n                            actual=meter(actual,path)\n                            activity['value']='working'")
        text=once(text,'                                result=review_departments(path,actual)','                                from superhuman.team import store as team_store,engine as team_engine\n                                result=team_engine.tick(path,actual) if team_store.enabled(path) else review_departments(path,actual)')
        text=once(text,"bool(result and result.get('supervision_cycle_id'))","bool(result and (result.get('supervision_cycle_id') or result.get('team_cycle_id')))")
    elif name=='navigation/shell.py':
        text=once(text,"    if path.startswith('/talk'): return 'talk'","    if path.startswith(('/talk','/team/twin')): return 'talk'\n    if path.startswith('/team'): return 'departments'")
        text=once(text,"('/supervision','Supervision')","('/supervision','Supervision'),('/team','Team & Twin')")
        text=once(text,"      'departments':","      'talk':(('/talk','Conversations'),('/team/twin','Mahnoor Twin')),\n      'departments':")
    elif name=='departments/web.py':
        text=once(text,"    body+=supervision_panel(d['scope'])","    body+=supervision_panel(d['scope'])\n    if d['scope']!='writing':body+='<p>'+link('/team/employees/'+d['scope'],'Persistent employee & writing skill')+'</p>'")
        text=once(text,'The writing specialist supports every department. Its existing writing workstream is available here separately.','Writing is a skill of each specialist. This legacy workstream retains earlier writing records and shared guidance.')
    elif name=='repairs/web.py':
        text=once(text,'    out.extend(supervised_attention())','    out.extend(supervised_attention())\n    from superhuman.team.web import attention as team_attention\n    out.extend(team_attention())')
    elif name=='repairs/checks.py':
        text=once(text,"    result['live_verification']=","    from superhuman.team import store as team,budget as team_budget\n    result['team']={'enabled':bool(team.settings()['enabled']),'employees':len(team.employees()),'task_states':dict(Counter(t['state'] for t in team.tasks())),'budget':{k:v for k,v in team_budget.report().items() if k!='costs'}}\n    result['live_verification']=")
    elif name=='repairs/scheduler.py':
        text=once(text,'    return [r[-1] for r in sorted(kept)]','    from superhuman.team.work import ordered as team_order\n    return team_order([r[-1] for r in sorted(kept)],path)')
    elif name=='projects/engine.py':
        text=once(text,'class LimitedClient:\n','class LimitedClient:\n    _team_metered=True\n')
        text=once(text,'        self.client=client;self.pid=pid;self.path=path;self.maximum=maximum;self.count=0','        from superhuman.team.budget import wrap\n        self.client=wrap(client,path);self.pid=pid;self.path=path;self.maximum=maximum;self.count=0')
        text=once(text,'        return agent_run(pid,path,client)',"        from superhuman.team.work import owned_run\n        from superhuman.team.budget import scope as billing_scope\n        employee_task=owned_run(pid,path)\n        if employee_task:\n            with billing_scope(employee_task['owner'],employee_task['id']):return agent_run(pid,path,client)\n        return agent_run(pid,path,client)")
        text=once(text,'    fixed_budget(pid,maximum,path)','    fixed_budget(pid,maximum,path)\n    from superhuman.team.work import fixed_budget as team_budget_limit\n    team_budget_limit(pid,maximum,path)')
        text=once(text,'        response=client_or_default(client).chat.completions.create(','        from superhuman.team.budget import wrap\n        response=wrap(client_or_default(client),path).chat.completions.create(')
    elif name=='agentic/web.py':
        text=once(text,'        body+=managed_banner(pid)','        body+=managed_banner(pid)\n        from superhuman.team.web import banner as team_banner\n        body+=team_banner(pid)')
    elif name=='agentic/engine.py':
        text=once(text,"    system='You are the supervised","    from superhuman.team.work import owned_run,employee_context\n    employee_task=owned_run(run['project_id'])\n    if employee_task:body['employee_context']=employee_context(employee_task)\n    system='You are the supervised")
    elif name=='identity/selection.py':
        text=once(text,'    return select(project,title,details,max_reference_chars)',"    result=select(project,title,details,max_reference_chars)\n    from superhuman.team.work import writing\n    result['preferences']+=writing(project)\n    return result")
    elif name=='supervision/engine.py':
        text=once(text,'actual=p.client_or_default(client);cycle=uuid4().hex','actual=p.client_or_default(client)\n        from superhuman.team.budget import wrap\n        actual=wrap(actual,path);cycle=uuid4().hex')
    elif name=='collab/runner.py':
        text=once(text,'    root=Path(output_dir) if output_dir','    from superhuman.team.budget import wrap\n    client=wrap(client)\n    root=Path(output_dir) if output_dir')
    elif name=='research/runner.py':
        text=once(text,'        client = OpenAI()','        client = OpenAI(max_retries=0)')
        text=once(text,'    selected_model = model or','    from superhuman.team.budget import wrap\n    client=wrap(client)\n    selected_model = model or')
    elif name=='dialogue/engine.py':
        text=once(text,'        response = client.chat.completions.create(','        from superhuman.team.budget import wrap\n        response = wrap(client,path).chat.completions.create(')
    elif name=='cli.py':
        text=once(text,'            client = OpenAI()','            client = OpenAI(max_retries=0)\n            from superhuman.team.budget import wrap\n            client=wrap(client)')
    elif name=='agentic/tools.py':
        text=once(text,'REGISTRY={t.name:t for t in [',"REGISTRY={t.name:t for t in [\n spec('team.handoff','Request another specialist: title <=180, instruction <=4000, acceptance <=1500. Parent waits for the Twin.','team_collaboration',{'recipient':str,'title':str,'instruction':str,'acceptance':str},('recipient','title','instruction','acceptance'),mutates=True),\n spec('team.challenge','Record concern, evidence and alternative; pause for the Twin/owner.','team_collaboration',{'reason':str,'evidence':str,'alternative':str},('reason','evidence','alternative'),mutates=True),\n spec('team.remember','Propose scoped employee memory; never confirms it automatically.','team_collaboration',{'kind':str,'content':str},('content',),mutates=True),")
        text=once(text,'PERMISSIONS={',"PERMISSIONS={\n 'team_collaboration':'Internal handoff requests, disagreements and proposed employee memory',")
        text=once(text,"    tool=validate(name,args);scope=run['project']['workstream']","    tool=validate(name,args);scope=run['project']['workstream']\n    if name.startswith('team.'):\n        from superhuman.team.work import request_tool\n        return request_tool(name,args,run,path)")
    elif name=='navigation/web.py':text+='\n    from superhuman.team.web import install as install_team\n    install_team(app)\n'
    ast.parse(text);return text
