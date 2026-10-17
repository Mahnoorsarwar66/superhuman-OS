"""Exact v1.34 UI integration; existing chat execution and permissions are preserved."""
import ast
from pathlib import Path
FILES=('navigation/shell.py','navigation/web.py','workspace/web.py','experience/web.py','foundation/__init__.py','repairs/__init__.py','hosted/boundary.py')
def canonical(name,text):return ast.dump(ast.parse(text),include_attributes=False)
def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Missing or repeated v1.35 anchor: '+old[:90])
    return text.replace(old,new,1)
def build(name,text,reference):
    if canonical(name,text)!=canonical(name,(Path(reference)/name).read_text()):raise ValueError('Unrecognised v1.34 source: '+name+'; nothing overwritten')
    if name in ('foundation/__init__.py','repairs/__init__.py','hosted/boundary.py'):text=once(text,'1.34.0','1.35.0')
    elif name=='navigation/shell.py':text=once(text,'</script></head><body>','</script><link rel="stylesheet" href="/assets/teamspace.css?v=135"><script src="/assets/teamspace.js?v=135" defer></script></head><body>')
    elif name=='navigation/web.py':text+='\n    from superhuman.teamspace.web import install as install_teamspace\n    install_teamspace(app)\n'
    elif name=='experience/web.py':text=once(text,'class="ux-avatar" aria-hidden="true"','class="teamspace-portrait" aria-hidden="true"')
    elif name=='workspace/web.py':
        text=once(text,"def team_home(employee='all',tab='room',page=1,q=''):","def _v134_team_home(employee='all',tab='room',page=1,q=''):")
        text=once(text,'def show_room(ident,before=0):','def _v134_show_room(ident,before=0):')
        text=once(text,"def rooms(employee:str='all',tab:str='room',q:str='',page:int=1):return team_home(employee,tab,page,q)","def rooms(employee:str='all',tab:str='room',q:str='',page:int=1,project_id:str='',project_kind:str=''):return team_home(employee,tab,page,q,project_id,project_kind)")
        text+='''\n\ndef team_home(employee='all',tab='room',page=1,q='',project_id='',project_kind=''):
    from superhuman.teamspace.views import home
    return home(employee,tab,page,q,project_id,project_kind,_v134_team_home)

def show_room(ident,before=0):
    from superhuman.teamspace.views import room
    return room(ident,before,_v134_show_room)
'''
    ast.parse(text);return text
