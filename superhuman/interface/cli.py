"""Presentation assets only; no setup data, tasks, permissions or model calls."""
from pathlib import Path
import argparse

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['check']);parser.parse_args()
    for name in ('design.css','design.js'):
        if not Path(__file__).with_name('assets').joinpath(name).is_file():raise SystemExit('Missing interface asset: '+name)
    print('v1.33 interface assets ready. No workflow data or execution controls changed.')
if __name__=='__main__':main()
