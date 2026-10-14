"""CLI: python -m superhuman.collab.cli run --title ... [--details ...]"""
import argparse
import json
from superhuman.collab.runner import run_collaboration


def main():
    parser = argparse.ArgumentParser(description='Superhuman OS collaborative draft + review')
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('run')
    run.add_argument('--title', required=True)
    run.add_argument('--details', default='')
    run.add_argument('--project', default=None)
    run.add_argument('--model', default=None)
    args = parser.parse_args()
    if args.command == 'run':
        print(json.dumps(run_collaboration(args.title, args.details, args.project, args.model), indent=2))


if __name__ == '__main__':
    main()
