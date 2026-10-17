"""Guarded supervision integration against delivered v1.24 source."""
import ast
from pathlib import Path
FILES=('agentic/web.py', 'departments/web.py', 'hosted/boundary.py', 'hosted/worker.py', 'navigation/shell.py', 'navigation/web.py', 'planning/store.py', 'projects/engine.py', 'repairs/__init__.py', 'repairs/checks.py', 'repairs/scheduler.py', 'repairs/web.py')
def canonical(name,text):return ast.dump(ast.parse(text),include_attributes=False)
def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Repair source anchor missing or repeated: '+old[:100])
    return text.replace(old,new,1)
def function(text,name,replacement):
    node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name==name)
    lines=text.splitlines(True)
    return ''.join(lines[:node.lineno-1])+replacement+'\n'+''.join(lines[node.end_lineno:])
def build(name,text,reference):
    if canonical(name,text)!=canonical(name,(Path(reference)/name).read_text(encoding='utf-8')):raise ValueError('Unrecognised v1.24 source: '+name+'; nothing overwritten')
    if name=='hosted/boundary.py':
        text=once(text,"'version':'1.24.0'","'version':'1.25.0'")
    elif name=='repairs/__init__.py':
        text=once(text,'1.24.0','1.25.0')
    elif name=='hosted/worker.py':
        text=once(text,'        recover_agentic(path)','        recover_agentic(path)\n        from superhuman.supervision.store import recover as recover_supervision\n        recover_supervision(path)')
        text=once(text,'        last_was_chat = False','        last_was_chat = False\n        last_was_supervisor = False')
        text=once(text,'                            if not last_was_chat:\n','                            if not last_was_supervisor:\n                                from superhuman.supervision.engine import tick as review_departments\n                                result=review_departments(path,actual)\n                            if result is None and not last_was_chat:\n')
        text=once(text,"                            last_was_chat = bool(result and result.get('conversation_turn_id'))","                            last_was_chat = bool(result and result.get('conversation_turn_id'))\n                            last_was_supervisor = bool(result and result.get('supervision_cycle_id'))")
    elif name=='navigation/shell.py':
        text=once(text,"('/departments','/department-plans')","('/departments','/department-plans','/supervision')")
        text=once(text,"      'tasks':","      'departments':(('/departments','Departments'),('/priorities','Priorities'),('/supervision','Supervision')),\n      'tasks':")
    elif name=='departments/web.py':
        text=once(text,"    body+=card_line(d['scope'])","    body+=card_line(d['scope'])\n    from superhuman.supervision.web import panel as supervision_panel\n    body+=supervision_panel(d['scope'])")
        text=once(text,"        if tab=='summary':","        from superhuman.supervision.web import panel as supervision_panel\n        body+=supervision_panel(scope)\n        if tab=='summary':")
    elif name=='repairs/scheduler.py':
        text=once(text,'    ids=[pid for pid in ids if runnable(pid,path)]','    from superhuman.supervision.store import managed_gate\n    ids=[pid for pid in ids if runnable(pid,path) and managed_gate(pid,path)[0]]')
    elif name=='repairs/web.py':
        text=once(text,'    return out\n','    from superhuman.supervision.web import attention as supervised_attention\n    out.extend(supervised_attention())\n    return out\n')
    elif name=='repairs/checks.py':
        text=once(text,"    result['live_verification']=","    from superhuman.supervision import store as supervision\n    result['supervision']=[{k:r[k] for k in ('scope','enabled','mode','allocated_calls','total_calls','hold','last_summary')} for r in supervision.policies(p.DEFAULT_DB)]\n    result['live_verification']=")
    elif name=='projects/engine.py':
        text=once(text,'def budget(pid,maximum,path=DEFAULT_DB):\n    p=get(pid,path)','def budget(pid,maximum,path=DEFAULT_DB):\n    from superhuman.supervision.store import fixed_budget\n    fixed_budget(pid,maximum,path)\n    p=get(pid,path)')
    elif name=='agentic/web.py':
        text=once(text,"        if r.get('error'):","        from superhuman.supervision.web import managed_banner\n        body+=managed_banner(pid)\n        if r.get('error'):")
    elif name=='planning/store.py':
        text=once(text,'    return result\n\ndef audit','    from superhuman.supervision.context import append_links\n    append_links(scope,result)\n    return result\n\ndef audit')
    elif name=='navigation/web.py':text+='\n    from superhuman.supervision.web import install as install_supervision\n    install_supervision(app)\n'
    ast.parse(text);return text
