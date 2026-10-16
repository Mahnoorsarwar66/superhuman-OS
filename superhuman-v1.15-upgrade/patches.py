"""Guarded additions to the delivered v1.14 source."""
import ast
from pathlib import Path
FILES=('dialogue/store.py','dialogue/web.py','hosted/web.py','hosted/views.py')


def canonical(name,text):return ast.dump(ast.parse(text),include_attributes=False)
def replace_once(text,old,new):
    if text.count(old)!=1:raise ValueError('Expected source anchor missing or repeated')
    return text.replace(old,new,1)


def verify_runtime(root,reference):
    a=ast.parse((Path(root)/'superhuman/runtime/engine.py').read_text(encoding='utf-8'))
    b=ast.parse((Path(reference)/'runtime/engine.py').read_text(encoding='utf-8'))
    for name in ('validate_job','_insert_job'):
        first=next((n for n in a.body if isinstance(n,ast.FunctionDef) and n.name==name),None)
        second=next((n for n in b.body if isinstance(n,ast.FunctionDef) and n.name==name),None)
        if first is None or second is None or ast.dump(first,include_attributes=False)!=ast.dump(second,include_attributes=False):
            raise ValueError('Canonical task creation changed: runtime.'+name)


def function(text,name,replacement):
    n=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name==name)
    lines=text.splitlines(keepends=True)
    return ''.join(lines[:n.lineno-1])+replacement+'\n'+''.join(lines[n.end_lineno:])


def build(name,text,reference):
    if canonical(name,text)!=canonical(name,(Path(reference)/name).read_text(encoding='utf-8')):
        raise ValueError('Unrecognised source in superhuman/'+name+'; nothing overwritten')
    if name=='dialogue/store.py':
        text=function(text,'approve',"def approve(thread_id,suggestion_id,expected_hash,title,details,path=p.DEFAULT_DB,scope=None):\n    from superhuman.taskdesk.store import approve as routed_approve\n    return routed_approve(thread_id,suggestion_id,expected_hash,title,details,path=path,scope=scope)")
    elif name=='dialogue/web.py':
        text=replace_once(text,'title: str = Form(...), details: str = Form(...)):',"title: str = Form(...), details: str = Form(...), scope: str = Form('')):")
        text=replace_once(text,'store.approve(thread_id, suggestion_id, expected_hash, title, details)', 'store.approve(thread_id, suggestion_id, expected_hash, title, details, scope=scope or None)')
        text=replace_once(text,"Review and edit the complete task before approval. Workstream:","Review and edit the task and choose its workstream before approval. Suggested workstream:")
        text=replace_once(text,"body += '<label>Task title<input", "body += '<label>Workstream<select name=\"scope\">' + options(store.scopes(), thread['scope']) + '</select></label><label>Task title<input")
    elif name=='hosted/web.py':
        text=replace_once(text,'    return Boundary(inner,settings,views.login)', '    from superhuman.taskdesk.web import install as install_taskdesk\n    install_taskdesk(inner)\n    return Boundary(inner,settings,views.login)')
    else:
        text=replace_once(text,'<a href="/talk">Talk</a>','<a href="/talk">Talk</a><a href="/tasks">Tasks</a>')
    ast.parse(text)
    return text
