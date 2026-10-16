"""Guarded additions to the delivered v1.16 source."""
import ast
from pathlib import Path
FILES=('hosted/web.py','hosted/views.py','calendar/web.py')


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


def verify_calendar(root,reference):
    name='calendar/store.py'
    if canonical(name,(Path(root)/'superhuman'/name).read_text(encoding='utf-8'))!=canonical(name,(Path(reference)/name).read_text(encoding='utf-8')):
        raise ValueError('Calendar storage source changed; nothing overwritten')


def build(name,text,reference):
    if canonical(name,text)!=canonical(name,(Path(reference)/name).read_text(encoding='utf-8')):
        raise ValueError('Unrecognised source in superhuman/'+name+'; nothing overwritten')
    if name=='hosted/web.py':
        text=replace_once(text,'    return Boundary(inner,settings,views.login)', '    from superhuman.meetingdesk.web import install as install_meetingdesk\n    install_meetingdesk(inner)\n    return Boundary(inner,settings,views.login)')
    elif name=='hosted/views.py':
        text=replace_once(text,'<a href="/calendar">Calendar</a>','<a href="/calendar">Calendar</a><a href="/meetings">Meetings</a>')
    else:
        anchor="        body+='<section class=\"card\">'+form('/calendar/event/'"
        text=replace_once(text,anchor,"        body+='<p><a class=\"button\" href=\"/meetings/'+key+'\">Preparation, notes and minutes</a></p>'\n"+anchor)
    ast.parse(text)
    return text
