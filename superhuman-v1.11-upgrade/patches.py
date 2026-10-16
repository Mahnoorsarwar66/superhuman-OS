"""Small AST-guarded patches to the delivered v1.10 source, not fixture snapshots."""
import ast
from pathlib import Path
FILES = ('hosted/web.py', 'hosted/views.py', 'hosted/worker.py', 'knowledge/web.py')


def dump(text): return ast.dump(ast.parse(text), include_attributes=False)


def replace_once(text, old, new):
    if text.count(old) != 1: raise ValueError('Expected source anchor missing or repeated')
    return text.replace(old, new, 1)


def verify_runtime(root, reference):
    current = ast.parse((Path(root) / 'superhuman/runtime/engine.py').read_text(encoding='utf-8'))
    expected = ast.parse((Path(reference) / 'runtime/engine.py').read_text(encoding='utf-8'))
    for name in ('validate_job', '_insert_job'):
        a = next((n for n in current.body if isinstance(n, ast.FunctionDef) and n.name == name), None)
        b = next((n for n in expected.body if isinstance(n, ast.FunctionDef) and n.name == name), None)
        if a is None or b is None or ast.dump(a, include_attributes=False) != ast.dump(b, include_attributes=False):
            raise ValueError('Canonical task creation changed: runtime.' + name)


def build(name, text, reference):
    expected = (Path(reference) / name).read_text(encoding='utf-8')
    if dump(text) != dump(expected): raise ValueError('Unrecognised source in superhuman/' + name + '; nothing overwritten')
    if name == 'hosted/web.py':
        text = replace_once(text, '    return Boundary(inner,settings,views.login)',
                            '    # dialogue-v111\n    from superhuman.dialogue.web import install as install_dialogue\n    install_dialogue(inner)\n    return Boundary(inner,settings,views.login)')
    elif name == 'hosted/views.py':
        text = replace_once(text, '<a href="/memory">Memory</a>', '<a href="/memory">Memory</a><a href="/talk">Talk</a>')
    elif name == 'knowledge/web.py':
        text = replace_once(text, "def form(record=None, scope='global', source='', title='', kind='update'):",
                            "def form(record=None, scope='global', source='', title='', kind='update', content=''):")
        text = replace_once(text, "r = record or dict(scope=scope, kind=kind, title=title, content='', source_type='user',",
                            "r = record or dict(scope=scope, kind=kind, title=title, content=content, source_type='user',")
    else:
        text = replace_once(text, '        jobs.initialize(path)',
                            '        jobs.initialize(path)\n        # dialogue-v111: the global lock excludes another active worker.\n        from superhuman.dialogue import store as dialogue_store, engine as dialogue_engine\n        dialogue_store.recover_running(path)\n        last_was_chat = False')
        old = '''                        result=jobs.run_plan(path,actual)
                        if result is None:result=r.tick(path,client=actual)'''
        new = '''                        # Alternate conversation and project work when both are ready.
                        result = None
                        if not last_was_chat:
                            result = dialogue_engine.run_turn(path,actual)
                        if result is None:
                            result=jobs.run_plan(path,actual)
                        if result is None:result=r.tick(path,client=actual)
                        if result is None and last_was_chat:
                            result=dialogue_engine.run_turn(path,actual)
                        last_was_chat = bool(result and result.get('conversation_turn_id'))'''
        text = replace_once(text, old, new)
    ast.parse(text)
    return text


def canonical(name, text):
    return dump(text)
