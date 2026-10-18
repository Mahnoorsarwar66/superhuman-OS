import argparse
from pathlib import Path
from . import store
from .policy import DEFERRED

def main():
 parser=argparse.ArgumentParser();parser.add_argument('command',choices=['setup','check']);args=parser.parse_args()
 for name in ['practice.css','practice.js']+[e+'.png' for e in store.team.EMPLOYEES]:
  if not Path(__file__).with_name('assets').joinpath(name).is_file():raise SystemExit('Missing practice asset: '+name)
 if args.command=='setup':store.setup()
 print('v1.34 practice assets ready. Questions 61–67 remain deferred. Existing model, channel and budget settings retained.')
if __name__=='__main__':main()

# Both stylesheet and dictation script are required local assets.
