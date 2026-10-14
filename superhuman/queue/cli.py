import argparse
import json
import time
from .engine import enqueue, get_job, list_jobs, run_one, review


def main():
    p = argparse.ArgumentParser(description='Superhuman OS v0.7 local background queue')
    subs = p.add_subparsers(dest='command', required=True)
    add = subs.add_parser('add')
    add.add_argument('--kind', choices=['research', 'collab'], required=True)
    add.add_argument('--project', required=True)
    add.add_argument('--title', required=True)
    add.add_argument('--details', default='')
    add.add_argument('--max-attempts', type=int, default=2)
    subs.add_parser('list')
    show = subs.add_parser('show'); show.add_argument('job_id')
    worker = subs.add_parser('worker')
    worker.add_argument('--once', action='store_true')
    worker.add_argument('--poll-seconds', type=int, default=15)
    worker.add_argument('--max-jobs', type=int, default=0, help='Max claimed jobs this run; 0 means unlimited')
    for action in ('approve', 'reject'):
        command = subs.add_parser(action)
        command.add_argument('job_id')
        command.add_argument('--note', default='')
    args = p.parse_args()
    if args.command == 'add':
        print('Job created:', enqueue(args.kind, args.project, args.title, args.details, max_attempts=args.max_attempts))
    elif args.command == 'list':
        for j in list_jobs():
            print(f"{j['id']} [{j['status']}] {j['kind']}/{j['project']} attempts={j['attempts']} {j['title']}")
    elif args.command == 'show':
        print(json.dumps(get_job(args.job_id), indent=2))
    elif args.command in ('approve', 'reject'):
        print(json.dumps(review(args.job_id, args.command, args.note), indent=2))
    elif args.command == 'worker':
        if args.poll_seconds < 1 or args.max_jobs < 0:
            p.error('poll-seconds must be >= 1 and max-jobs >= 0')
        print('Local worker started. Research and draft tasks ONLY. Ctrl+C stops after current request.')
        count = 0
        try:
            while True:
                finished = run_one()
                if finished:
                    count += 1
                    print(f"{finished['id']}: {finished['status']} attempts={finished['attempts']}", flush=True)
                if args.once or (args.max_jobs and count >= args.max_jobs):
                    break
                if not finished:
                    time.sleep(args.poll_seconds)
        except KeyboardInterrupt:
            print('Worker stopped.')


if __name__ == '__main__':
    main()
