import argparse
import json
from superhuman.projects import engine as p
from . import store


def main():
    parser = argparse.ArgumentParser(description='Superhuman conversation state; no model requests')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status')
    sub.add_parser('list')
    item = sub.add_parser('show'); item.add_argument('id')
    args = parser.parse_args()
    if args.command == 'status':
        store.initialize()
        with p.connect() as db:
            count = db.execute('SELECT COUNT(*) FROM dialogue_threads').fetchone()[0]
        result = {'version': '1.11.0', 'conversations': count, 'api_calls': 0}
    elif args.command == 'list': result = store.listing()
    else: result = {'thread': store.get(args.id), 'turns': store.turns(args.id), 'suggestions': store.suggestions(args.id)}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
