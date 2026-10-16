"""Guarded patches against the delivered v1.11 source."""
import ast
from pathlib import Path

FILES=('hosted/web.py','hosted/views.py','hosted/worker.py','dialogue/engine.py','hosted/transfer.py')


def dump(text):return ast.dump(ast.parse(text),include_attributes=False)
def canonical(name,text):return dump(text)
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
    if dump(text)!=dump((Path(reference)/name).read_text(encoding='utf-8')):
        raise ValueError('Unrecognised source in superhuman/'+name+'; nothing overwritten')
    if name=='hosted/web.py':
        text=replace_once(text,'    return Boundary(inner,settings,views.login)',
            '    from superhuman.mail.web import install as install_mail\n    install_mail(inner)\n    return Boundary(inner,settings,views.login)')
    elif name=='hosted/views.py':
        text=replace_once(text,'<a href="/talk">Talk</a>','<a href="/talk">Talk</a><a href="/inboxes">Inboxes</a>')
    elif name=='dialogue/engine.py':
        text=replace_once(text,'def prompt(claimed, path=p.DEFAULT_DB):',
            'def prompt(claimed, path=p.DEFAULT_DB):\n    from superhuman.mail.store import report_prompt\n    mail_context = report_prompt(claimed,path)\n    if mail_context is not None: return mail_context')
        text=replace_once(text,"        parsed = parse(raw, claimed['scope'])",
            "        parsed = parse(raw, claimed['scope'])\n        if trace.get('mail_report_id') and any(t['kind'] != 'collab' for t in parsed['tasks']):\n            raise ValueError('Inbox reports can suggest local drafting tasks only')")
    elif name=='hosted/transfer.py':
        text=replace_once(text,"            archive.writestr('bundle-manifest.json',json.dumps(manifest,indent=2))",
            "            if (root/'superhuman/mail').is_dir():\n                dependency=b'cryptography>=44,<51\\n'\n                archive.writestr('requirements-v112.txt',dependency)\n                manifest['files'].append({'name':'requirements-v112.txt','sha256':digest(dependency),'bytes':len(dependency)})\n            archive.writestr('bundle-manifest.json',json.dumps(manifest,indent=2))")
        text=replace_once(text,"if rel.parts[0] not in ('superhuman','data','superhuman-deploy-v19','.gitignore','requirements.txt','requirements-v19.txt'):","if rel.parts[0] not in ('superhuman','data','superhuman-deploy-v19','.gitignore','requirements.txt','requirements-v19.txt','requirements-v112.txt'):")
    else:
        text=replace_once(text,'        last_was_chat = False',
            '        last_was_chat = False\n        last_was_mail = False\n        from superhuman.mail import store as mail_store, providers as mail_providers\n        mail_store.recover(path)')
        start=text.index('                    if actual is None:actual=configured_client()')
        end=text.index("                jobs.pulse(owner,activity['value'],path)",start)
        original=text[start:end]
        replacement="""                    # Alternate bounded read cycles with model work. Do not put
                    # a network sync and a three-call task in the same shutdown window.
                    mail_result=None
                    if not last_was_mail:
                        activity['value']='reading_mail'
                        mail_result=mail_providers.run_sync(path)
                    last_was_mail=bool(mail_result)
                    if mail_result:
                        result=mail_result
                        activity['value']='idle'
                        if report:report(mail_result)
                    else:
"""+''.join('    '+line+'\n' for line in original.splitlines())
        text=text[:start]+replacement+text[end:]
    ast.parse(text)
    return text
