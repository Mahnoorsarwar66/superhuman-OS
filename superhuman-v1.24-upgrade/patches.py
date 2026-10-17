"""Guarded agentic integration against delivered v1.23 source."""
import ast
from pathlib import Path
FILES=('hosted/boundary.py', 'hosted/worker.py', 'navigation/shell.py', 'navigation/web.py', 'projects/engine.py', 'repairs/__init__.py', 'repairs/checks.py', 'repairs/scheduler.py', 'repairs/web.py', 'runtime/engine.py')
def canonical(name,text):return ast.dump(ast.parse(text),include_attributes=False)
def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Repair source anchor missing or repeated: '+old[:100])
    return text.replace(old,new,1)
def function(text,name,replacement):
    node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name==name)
    lines=text.splitlines(True)
    return ''.join(lines[:node.lineno-1])+replacement+'\n'+''.join(lines[node.end_lineno:])
def build(name,text,reference):
    if canonical(name,text)!=canonical(name,(Path(reference)/name).read_text(encoding='utf-8')):raise ValueError('Unrecognised v1.23 source: '+name+'; nothing overwritten')
    if name=='projects/engine.py':
        text=once(text,"    p=get(pid,path)\n    # Resolve identity", "    p=get(pid,path)\n    if any(t['kind']=='agentic' for t in p['tasks']):\n        from superhuman.agentic.engine import run_one as agent_run\n        return agent_run(pid,path,client)\n    # Resolve identity")
        text=once(text,"    if not note.strip():raise ValueError('Provide a retry/correction note; retry can spend API calls again')", "    if any(t['kind']=='agentic' for t in get(pid,path)['tasks']):raise ValueError('Use the Agent runs controls to inspect and resume this run')\n    if not note.strip():raise ValueError('Provide a retry/correction note; retry can spend API calls again')")
    elif name=='runtime/engine.py':
        text=once(text,"            event('task_completed',pid,task['id'],{'status':task['status']},path)","            event('agent_step' if task.get('kind')=='agentic' and task['status']!='needs_review' else 'task_completed',pid,task['id'],{'status':task['status']},path)")
    elif name=='repairs/scheduler.py':
        text=once(text,'    kept=[]','    from superhuman.agentic.store import runnable\n    ids=[pid for pid in ids if runnable(pid,path)]\n    kept=[]')
    elif name=='hosted/worker.py':text=once(text,'        recover(path)','        recover(path)\n        from superhuman.agentic.store import recover as recover_agentic\n        recover_agentic(path)')
    elif name=='hosted/boundary.py':text=once(text,"'version':'1.23.0'","'version':'1.24.0'")
    elif name=='repairs/__init__.py':text=once(text,'1.23.0','1.24.0')
    elif name=='navigation/web.py':text+='\n    from superhuman.agentic.web import install as install_agentic\n    install_agentic(app)\n'
    elif name=='navigation/shell.py':
        text=once(text,"('/tasks','/runtime','/queue','/coding')","('/tasks','/agent-runs','/runtime','/queue','/coding')")
        text=once(text,"('/tasks','All tasks')","('/tasks','All tasks'),('/agent-runs','Agent runs')")
    elif name=='repairs/web.py':
        text=once(text,"        body='<h1>All tasks</h1>",'        body=\'<h1>All tasks</h1><p><a href="/agent-runs">Start or inspect an agent run</a></p>')
        text=once(text,"            if t.get('error'):",'            if t[\'kind\']==\'agentic\':body+=\'<p><a href="/agent-runs/\'+t[\'project_id\']+\'">Inspect actions, permissions and run controls</a></p>\'\n            if t.get(\'error\'):')
        text=once(text,"            if t['status'] in ('failed','interrupted','quality_blocked','rejected'):","            if t['kind']!='agentic' and t['status'] in ('failed','interrupted','quality_blocked','rejected'):")
        text=once(text,"    return out\n", "    from superhuman.agentic.store import listing\n    for r in listing():\n        if r['state'] in ('awaiting_permission','needs_review','step_limit','budget_blocked'):\n            out.append({'title':r['objective'],'reason':r['state'].replace('_',' '),'url':'/agent-runs/'+r['project_id']})\n    return out\n")
    elif name=='repairs/checks.py':
        text=once(text,"    result['live_verification']=","    from superhuman.agentic.store import listing\n    from collections import Counter\n    result['agentic']={'release':'1.24.0','run_states':dict(Counter(r['state'] for r in listing(p.DEFAULT_DB)))}\n    result['live_verification']=")
    ast.parse(text);return text
