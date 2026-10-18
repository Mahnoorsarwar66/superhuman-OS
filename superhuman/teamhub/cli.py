import argparse
from pathlib import Path
from . import store

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['check','initialize']);args=parser.parse_args()
    for name in ('teamhub.css','teamhub.js'):
        if not Path(__file__).with_name('assets').joinpath(name).is_file():raise SystemExit('Missing Team asset: '+name)
    if args.command=='initialize':store.initialize()
    print('Team v1.36 ready. Existing budgets, permissions and external-action boundaries retained.')
if __name__=='__main__':main()
