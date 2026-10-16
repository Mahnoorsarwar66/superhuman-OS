import argparse
import json
from .local import TOOLS,execute,import_file

def main():
    parser=argparse.ArgumentParser(description='Bounded local tools; no model calls')
    parser.add_argument('--project',required=True)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('list')
    command=sub.add_parser('import');command.add_argument('file')
    for name in TOOLS:
        command=sub.add_parser(name)
        command.add_argument('value')
    args=parser.parse_args()
    if args.command=='list':result=TOOLS
    elif args.command=='import':result=import_file(args.project,args.file)
    else:result=execute(args.project,args.command,**{('expression' if args.command=='calculate' else 'query' if args.command=='search_files' else 'filename'):args.value})
    print(json.dumps(result,indent=2,ensure_ascii=False))
    if result.get('status')=='failed':raise SystemExit(1)
if __name__=='__main__':main()
