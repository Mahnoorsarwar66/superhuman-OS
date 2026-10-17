import argparse
from pathlib import Path

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['check']);parser.parse_args()
    for asset in ('teamspace.css','teamspace.js'):
        if not Path(__file__).with_name('assets').joinpath(asset).is_file():raise SystemExit('Missing Team workspace asset: '+asset)
    print('v1.35 Team workspace assets ready. No workflow data, employee permissions or model settings changed.')
if __name__=='__main__':main()
