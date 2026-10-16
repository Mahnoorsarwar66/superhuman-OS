"""Guarded additions to the delivered v1.13 source."""
import ast
from pathlib import Path
FILES=('mail/store.py','mail/providers.py','mail/web.py','briefing/web.py','hosted/web.py')


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
    if name=='mail/store.py':
        n=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='initialize')
        lines=text.splitlines(keepends=True)
        lines.insert(n.end_lineno,'    from superhuman.mailflow.state import initialize as initialize_mailflow\n    initialize_mailflow(path)\n')
        text=''.join(lines)
        text=function(text,'make_report',"def make_report(slot,submission_key,path=p.DEFAULT_DB):\n    from superhuman.mailflow.reports import make_report as next_report\n    return next_report(slot,submission_key,path)")
        old="        db.execute('DELETE FROM mail_messages WHERE account_id=? AND id NOT IN (SELECT id FROM mail_messages WHERE account_id=? ORDER BY received DESC,id LIMIT 500)',(a['id'],a['id']))"
        text=replace_once(text,old,'        # Unreported previews are retained; the resumable reader applies capacity backpressure.')
    elif name=='mail/providers.py':
        text=function(text,'run_sync',"def run_sync(path=store.p.DEFAULT_DB):\n    from superhuman.mailflow.engine import run_sync as resume_sync\n    return resume_sync(path)")
    elif name=='hosted/web.py':
        text=replace_once(text,'    return Boundary(inner,settings,views.login)',
            '    from superhuman.mailflow.web import install as install_mailflow\n    install_mailflow(inner)\n    return Boundary(inner,settings,views.login)')
    elif name=='mail/web.py':
        text=replace_once(text,'        if a[\'limited\']:body+=\'<p class="error">The last sync reached a message or time limit. Some messages were not included.</p>\'',
            "        from superhuman.mailflow.web import panel\n        from superhuman.mailflow.state import summary\n        body+=panel(slot)")
        text=replace_once(text,'        if rows:\n            body+=\'<section class="card"><h2>Prepare a report</h2>',
            '        if rows and summary(slot)[\'waiting\']:\n            body+=\'<section class="card"><h2>Prepare the next report</h2>')
        text=text.replace('up to 25 recent INBOX messages from the last 7 days','seven-day INBOX scans in resumable batches')
        text=text.replace('up to 12 newest saved messages','up to 12 saved messages waiting for a report')
    else:
        text=replace_once(text,"        eligible=[slot for slot in connected if store.messages(slot,limit=1)]",
            "        from superhuman.mailflow import state as coverage\n        from superhuman.mailflow.web import panel\n        eligible=[slot for slot in connected if coverage.summary(slot)['waiting']]")
        text=replace_once(text,"            if account['limited']:body+='<p class=\"error\">Read limit reached; some messages were not included.</p>'",'            body+=panel(slot)')
        text=text.replace('Request '+"'+str(len(eligible))+'"+' reports','Request '+"'+str(len(eligible))+'"+' next reports')
    ast.parse(text)
    return text
