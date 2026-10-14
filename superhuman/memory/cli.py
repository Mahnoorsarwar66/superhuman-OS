"""Memory management commands. Run with python -m superhuman.memory.cli."""
import argparse
from superhuman.memory.store import add_memory, deactivate_memory, load_records, context_for


def main():
    parser = argparse.ArgumentParser(description='Superhuman OS explicit memory')
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('add')
    p.add_argument('--project', required=True)
    p.add_argument('--text', required=True)
    p.add_argument('--source', default='user_confirmed', choices=['user_confirmed', 'document', 'inferred'])
    p = commands.add_parser('list')
    p.add_argument('--project')
    p = commands.add_parser('disable')
    p.add_argument('id')
    p = commands.add_parser('preview')
    p.add_argument('--project', required=True)
    args = parser.parse_args()
    if args.command == 'add':
        record = add_memory(args.project, args.text, args.source)
        print('Memory added:', record['id'])
    elif args.command == 'list':
        for record in load_records():
            if not args.project or args.project == record['project']:
                print(f"{record['id']} [{record['project']}] active={record['active']} ({record['source']}) {record['text']}")
    elif args.command == 'disable':
        print('Memory disabled.' if deactivate_memory(args.id) else 'Memory not found.')
    elif args.command == 'preview':
        print(context_for(args.project))


if __name__ == '__main__':
    main()
