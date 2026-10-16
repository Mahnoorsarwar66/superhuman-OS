"""Guarded integration with exactly the delivered v1.12 source."""
import ast
from pathlib import Path

FILES=('hosted/web.py','hosted/views.py','mail/web.py','mail/store.py','dialogue/engine.py')


def canonical(name,text):return ast.dump(ast.parse(text),include_attributes=False)
def replace_once(text,old,new):
    if text.count(old)!=1:raise ValueError('Expected source anchor missing or repeated')
    return text.replace(old,new,1)


def verify_runtime(root,reference):
    current=ast.parse((Path(root)/'superhuman/runtime/engine.py').read_text(encoding='utf-8'))
    expected=ast.parse((Path(reference)/'runtime/engine.py').read_text(encoding='utf-8'))
    for name in ('validate_job','_insert_job'):
        a=next((n for n in current.body if isinstance(n,ast.FunctionDef) and n.name==name),None)
        b=next((n for n in expected.body if isinstance(n,ast.FunctionDef) and n.name==name),None)
        if a is None or b is None or ast.dump(a,include_attributes=False)!=ast.dump(b,include_attributes=False):
            raise ValueError('Canonical task creation changed: runtime.'+name)


def build(name,text,reference):
    expected=(Path(reference)/name).read_text(encoding='utf-8')
    if canonical(name,text)!=canonical(name,expected):raise ValueError('Unrecognised source in superhuman/'+name+'; nothing overwritten')
    if name=='hosted/web.py':
        text=replace_once(text,'    return Boundary(inner,settings,views.login)',
            '    from superhuman.briefing.web import install as install_briefing\n    install_briefing(inner)\n    return Boundary(inner,settings,views.login)')
    elif name=='hosted/views.py':
        text=replace_once(text,'<a href="/inboxes">Inboxes</a>','<a href="/inboxes">Inboxes</a><a href="/briefing">Briefing</a>')
    elif name=='mail/web.py':
        text=replace_once(text,"        body='<h1>Your inboxes</h1><p>Read-only previews, reports and tasks for approval.</p>'",
             "        body='<h1>Your inboxes</h1><p>Read-only previews, reports and tasks for approval.</p><p><a class=\"button\" href=\"/briefing\">Open unified briefing</a></p>'")
    elif name=='mail/store.py':
        node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='report_prompt')
        lines=text.splitlines(keepends=True)
        replacement="def report_prompt(claimed,path=p.DEFAULT_DB):\n    from superhuman.briefing.engine import mail_prompt\n    return mail_prompt(claimed,path)\n"
        text=''.join(lines[:node.lineno-1])+replacement+''.join(lines[node.end_lineno:])
    else:
        text=replace_once(text,'        response = client.chat.completions.create(',
            "        from superhuman.briefing import engine as briefing_engine\n        report_mode = bool(trace.get('briefing_mode'))\n        response_schema = briefing_engine.SCHEMA if report_mode else SCHEMA\n        response = client.chat.completions.create(")
        text=replace_once(text,"'name': 'superhuman_conversation_reply', 'strict': True, 'schema': SCHEMA",
            "'name': 'superhuman_inbox_briefing' if report_mode else 'superhuman_conversation_reply', 'strict': True, 'schema': response_schema")
        text=replace_once(text,"        parsed = parse(raw, claimed['scope'])",
            "        parsed = briefing_engine.parse(raw,claimed['scope'],trace) if report_mode else parse(raw, claimed['scope'])\n        if report_mode:\n            trace['briefing'] = parsed.pop('briefing')\n        elif trace.get('mail_report_id'):\n            cleaned = {key: briefing_engine.scrub(parsed[key]) for key in ('reply',)}\n            cleaned['tasks'] = [{k: briefing_engine.scrub(v) for k,v in task.items()} for task in parsed['tasks']]\n            parsed = parse(json.dumps(cleaned),claimed['scope'])")
    ast.parse(text)
    return text
