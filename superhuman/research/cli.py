"""Usage: python -m superhuman.research.cli run --title ... --details ..."""
import argparse
from .runner import run_research


def main():
    p = argparse.ArgumentParser(description='Superhuman OS evidence-assisted web research')
    sub = p.add_subparsers(dest='command', required=True)
    r = sub.add_parser('run', help='research a task with the hosted web-search tool')
    r.add_argument('--title', required=True)
    r.add_argument('--details', default='')
    r.add_argument('--project', default=None)
    args = p.parse_args()
    if args.command == 'run':
        result = run_research(args.title, args.details, project=args.project)
        print(f"Research draft saved: {result['output']}")
        print(f"Project: {result['workstream']} | URL citations: {result['source_count']} | Status: needs_review")


if __name__ == '__main__':
    main()
