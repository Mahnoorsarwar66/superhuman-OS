"""Local evidence and proactive scan commands; no API requests."""
import argparse,json
from . import baseline,proactive

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['check','capture','scan']);args=parser.parse_args()
    result=baseline.report() if args.command=='check' else baseline.capture() if args.command=='capture' else proactive.scan(force=True)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
