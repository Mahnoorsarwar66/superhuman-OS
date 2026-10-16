"""Guarded additions to the delivered v1.18 source."""
import ast
from pathlib import Path
FILES=('hosted/web.py','researchdesk/web.py')


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


def verify_review_contracts(root,reference):
    for name in ('projects/engine.py','researchdesk/store.py','research/runner.py'):
        if canonical(name,(Path(root)/'superhuman'/name).read_text(encoding='utf-8'))!=canonical(name,(Path(reference)/name).read_text(encoding='utf-8')):
            raise ValueError('Research review contract changed: '+name+'; nothing overwritten')


def build(name,text,reference):
    if canonical(name,text)!=canonical(name,(Path(reference)/name).read_text(encoding='utf-8')):
        raise ValueError('Unrecognised source in superhuman/'+name+'; nothing overwritten')
    if name=='hosted/web.py':
        text=replace_once(text,'    return Boundary(inner,settings,views.login)', '    from superhuman.researchreview.web import install as install_researchreview\n    install_researchreview(inner)\n    return Boundary(inner,settings,views.login)')
    else:
        text=replace_once(text,"        return render(body,v['title'])", "        body+='<p><a href=\"/research-review/source/'+source_id+'/history\">Applied synopsis history</a></p>'\n        return render(body,v['title'])")
        anchor="        if a['status']=='active':body+='<p><a class=\"button\" href=\"/research-desk/'"
        text=replace_once(text,anchor,"        body+='<p><a href=\"/research-review/area/'+area_id+'\">Review cited source suggestions</a></p>'\n"+anchor)
        text=replace_once(text,'        for task in tasks:body+=','        from superhuman.researchreview.web import task_actions\n        for task in tasks:body+=')
        text=replace_once(text,"Open output and review</a></article>'", "Open output and review</a>'+task_actions(task)+'</article>'")
    ast.parse(text)
    return text
