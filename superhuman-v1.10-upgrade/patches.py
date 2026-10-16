"""Narrow source patches with AST checks against the shipped v1.9 source basis."""
import ast
from pathlib import Path

FILES = ('identity/selection.py', 'collab/runner.py', 'hosted/web.py', 'hosted/views.py',
         'hosted/boundary.py', 'hosted/transfer.py')
MARKER = '# knowledge-v110'


def strip_diagnostic(text):
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    removals = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name) and node.value.func.id == 'print'
                and node.value.args and isinstance(node.value.args[0], ast.Constant)
                and node.value.args[0].value == 'CSRF diagnostic:'):
            removals.append((node.lineno - 1, node.end_lineno))
    for start, end in sorted(removals, reverse=True):
        del lines[start:end]
    return ''.join(lines)


def canonical(name, text):
    if name == 'hosted/boundary.py':
        text = strip_diagnostic(text)
        text = text.replace("'Referrer-Policy':'no-referrer'", "'Referrer-Policy':'same-origin'")
        tree = ast.parse(text)
        # Accept only the two favicon fixes actually issued during this session.
        for node in ast.walk(tree):
            for field, value in ast.iter_fields(node):
                if isinstance(value, list):
                    kept = []
                    for child in value:
                        if isinstance(child, ast.If) and 'favicon.ico' in ast.unparse(child.test):
                            allowed = [
                                "if scope['path']=='/favicon.ico' and scope['method'] in ('GET','HEAD'):\n return await reply(PlainTextResponse('', status_code=204))",
                                "if scope['path']=='/favicon.ico' and scope['method'] in ('GET','HEAD'):\n return await reply(Response(status_code=204))",
                            ]
                            if ast.dump(child, include_attributes=False) not in [ast.dump(ast.parse(s).body[0], include_attributes=False) for s in allowed]:
                                raise ValueError('Unexpected favicon handler')
                            continue
                        kept.append(child)
                    setattr(node, field, kept)
            if isinstance(node, ast.ImportFrom) and node.module == 'starlette.responses':
                node.names = [alias for alias in node.names if alias.name != 'Response']
        return ast.dump(tree, include_attributes=False)
    if name == 'hosted/transfer.py':
        text = text.replace("('-wal','-shm','-journal','.runtime.lock')", "('-wal','-shm','-journal')")
    return ast.dump(ast.parse(text), include_attributes=False)


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Expected source anchor missing or repeated: ' + old[:75])
    return text.replace(old, new, 1)


def build(name, text, reference_root):
    expected = (Path(reference_root) / name).read_text(encoding='utf-8')
    if canonical(name, text) != canonical(name, expected):
        raise ValueError('Unrecognised source in superhuman/' + name + '; nothing overwritten')
    if name == 'identity/selection.py':
        text += '''\n\n# knowledge-v110
_legacy_select_context = select_context


def select_context(project, title, details='', max_reference_chars=7000):
    from superhuman.knowledge.context import augment
    selected = _legacy_select_context(project, title, details, max_reference_chars)
    return augment(selected, project, title, details, max_reference_chars)
'''
    elif name == 'hosted/web.py':
        text = replace_once(text, "    return Boundary(inner,settings,views.login)",
                            "    # knowledge-v110\n    from superhuman.knowledge.web import install as install_knowledge\n    install_knowledge(inner)\n    return Boundary(inner,settings,views.login)")
        text = replace_once(text, "        return HTMLResponse(views.page(body,p['objective']))",
                            "        from superhuman.knowledge.web import feedback_link\n        body += feedback_link(pid)\n        return HTMLResponse(views.page(body,p['objective']))")
    elif name == 'hosted/views.py':
        text = replace_once(text, '<a href="/coding">Coding</a></nav>',
                            '<a href="/coding">Coding</a><a href="/memory">Memory</a></nav>')
        text += '\n# knowledge-v110\n'
    elif name == 'collab/runner.py':
        text = replace_once(text, '    except (ValueError,TypeError):\n        review=',
                            '    except (ValueError,TypeError) as review_error:\n        review=')
        text = replace_once(text, "    report['reviewer_status']='invalid' if review_errors else 'structured_review_completed'",
                            "    # knowledge-v110\n    report['reviewer_status']='invalid' if review_errors else 'structured_review_completed'\n    if review_errors:report['reviewer_error_detail']=review_error_detail")
        text = replace_once(text, "        review_errors.append('Reviewer response incomplete or invalid; inspect archived stages')",
                            "        review_error_detail = str(review_error)\n        review_errors.append('Reviewer response incomplete or invalid: ' + review_error_detail + '; inspect archived stages')")
        text = replace_once(text, "        'Blank form fields are intentional. No issues means an empty issues array.',",
                            "        'Blank form fields are intentional. No issues means an empty issues array. '\n        'PROGRAM CHECKS are separate internal metadata, never evidence from the draft. '\n        'Quote draft evidence only from INITIAL DRAFT. A number range is not a spaced dash clause separator.',")
    elif name == 'hosted/boundary.py':
        text = strip_diagnostic(text).replace("'Referrer-Policy':'no-referrer'", "'Referrer-Policy':'same-origin'")
        if 'favicon.ico' not in text:
            text = replace_once(text, "        if scope['path']=='/healthz' and scope['method']=='GET':",
                                "        if scope['path']=='/favicon.ico' and scope['method'] in ('GET','HEAD'):\n            return await reply(PlainTextResponse('',status_code=204))\n        if scope['path']=='/healthz' and scope['method']=='GET':")
        text += '\n# knowledge-v110\n'
    elif name == 'hosted/transfer.py':
        if "'.runtime.lock'" not in text:
            text = replace_once(text, "('-wal','-shm','-journal')", "('-wal','-shm','-journal','.runtime.lock')")
        text += '\n# knowledge-v110\n'
    ast.parse(text)
    return text
