"""Manage personally curated writing samples, decisions, and editorial rules."""
import argparse
from pathlib import Path
from superhuman.identity.store import add, list_records, disable, context_for


def main():
    p = argparse.ArgumentParser(description='Superhuman OS v0.9 identity library')
    commands = p.add_subparsers(dest='cmd', required=True)
    c = commands.add_parser('add-sample')
    c.add_argument('--project', default='global')
    c.add_argument('--label', required=True)
    c.add_argument('--file', required=True)
    c = commands.add_parser('add-decision')
    c.add_argument('--project', default='global')
    c.add_argument('--label', required=True)
    c.add_argument('--file', required=True)
    c = commands.add_parser('add-rule')
    c.add_argument('--project', default='global')
    c.add_argument('--label', required=True)
    c.add_argument('--text', required=True)
    c = commands.add_parser('list')
    c.add_argument('--kind', choices=['writing', 'decisions', 'rules'], required=True)
    c = commands.add_parser('disable')
    c.add_argument('--kind', choices=['writing', 'decisions', 'rules'], required=True)
    c.add_argument('id')
    c = commands.add_parser('preview')
    c.add_argument('--project', default='global')
    a = p.parse_args()
    if a.cmd in ('add-sample', 'add-decision'):
        kind = 'writing' if a.cmd == 'add-sample' else 'decisions'
        path = Path(a.file)
        if not path.is_file() or path.suffix.lower() != '.txt':
            p.error('Provide an existing .txt file containing your own text')
        rec = add(kind, a.project, a.label, path.read_text(encoding='utf-8'),
                  source='original_sample' if kind == 'writing' else 'user_confirmed')
        print('Added', kind, rec['id'])
    elif a.cmd == 'add-rule':
        rec = add('rules', a.project, a.label, a.text)
        print('Added rule', rec['id'])
    elif a.cmd == 'list':
        for r in list_records(a.kind):
            print(r['id'], r['project'], 'active=' + str(r['active']), r['label'])
    elif a.cmd == 'disable':
        print('Disabled' if disable(a.kind, a.id) else 'Not found')
    elif a.cmd == 'preview':
        print(context_for(a.project))


if __name__ == '__main__':
    main()
