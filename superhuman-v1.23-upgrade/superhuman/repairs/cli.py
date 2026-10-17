import argparse,json
from . import checks

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('check',));parser.add_argument('--queue-inboxes',action='store_true');args=parser.parse_args()
    result=checks.report()
    if args.queue_inboxes:result['queued_inbox_probes']=checks.queue_inboxes()
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
