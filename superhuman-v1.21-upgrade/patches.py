"""Guarded additions to the exact v1.20 navigation source."""
import ast
from pathlib import Path
FILES=('navigation/shell.py','navigation/web.py')

def canonical(name,text):return ast.dump(ast.parse(text),include_attributes=False)

def build(name,text,reference):
    if canonical(name,text)!=canonical(name,(Path(reference)/name).read_text(encoding='utf-8')):
        raise ValueError('Unrecognised source in superhuman/'+name+'. Install v1.20 first; no files changed.')
    if name=='navigation/shell.py':
        old="('projects','/projects','Projects')"
        if text.count(old)!=1:raise ValueError('Department sidebar anchor changed')
        text=text.replace(old,"('departments','/departments','Departments'),"+old)
        old="    if path.startswith('/talk'): return 'talk'"
        if text.count(old)!=1:raise ValueError('Department section anchor changed')
        text=text.replace(old,"    if path.startswith('/departments'): return 'departments'\n"+old)
    else:
        text+='\n    from superhuman.departments.web import install as install_departments\n    install_departments(app)\n'
    ast.parse(text)
    return text
