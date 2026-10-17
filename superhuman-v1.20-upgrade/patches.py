"""Guard the only existing source file changed by this release."""
import ast
from pathlib import Path
FILES=('hosted/web.py',)

def canonical(name,text):return ast.dump(ast.parse(text),include_attributes=False)

def build(name,text,reference):
    if canonical(name,text)!=canonical(name,(Path(reference)/name).read_text(encoding='utf-8')):
        raise ValueError('Unrecognised source in superhuman/'+name+'. Install corrected v1.18 and v1.19 first; no files changed.')
    anchor='    return Boundary(inner,settings,views.login)'
    if text.count(anchor)!=1:raise ValueError('Navigation installation anchor changed')
    result=text.replace(anchor,'    from superhuman.navigation.web import install as install_navigation\n    install_navigation(inner)\n'+anchor)
    ast.parse(result)
    return result
