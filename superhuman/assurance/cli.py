"""Idempotent stage 2 schema and bounded internal-tool migration."""
import argparse
from . import store

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['setup']);parser.parse_args();store.setup()
    print('v1.32 evidence and quality registers prepared. No tasks, paid calls or external actions started. Existing approvals remain historical; new gates apply to new packets.')
if __name__=='__main__':main()
