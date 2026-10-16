"""Memory-centre CLI. No model calls. Prefer web forms for private text."""
import argparse
import json
from .store import Store


def main():
    p = argparse.ArgumentParser(description='Superhuman memory centre')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('status')
    item = sub.add_parser('list'); item.add_argument('--scope'); item.add_argument('--status')
    item = sub.add_parser('show'); item.add_argument('id')
    item = sub.add_parser('archive'); item.add_argument('id'); item.add_argument('--version', type=int, required=True)
    item = sub.add_parser('preview'); item.add_argument('--scope', required=True); item.add_argument('--title', required=True); item.add_argument('--details', default='')
    a = p.parse_args(); store = Store()
    try:
        if a.command == 'status':
            result = {'version': '1.10.0', 'database_exists': store.path.exists(), 'api_calls': 0}
        elif a.command == 'list':
            result = store.list(a.scope, a.status)
        elif a.command == 'show':
            result = {'note': store.get(a.id), 'history': store.history(a.id)}
        elif a.command == 'archive':
            result = store.update(a.id, a.version, status='archived')
        else:
            from superhuman.identity.selection import select_context
            result = select_context(a.scope, a.title, a.details)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as exc:
        p.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
