"""Install the paused blueprint or inspect it without model requests."""
import argparse,json
from . import store

def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['setup','status']);a=p.parse_args()
    if a.command=='setup':
        pid=store.seed_endorsement();print(json.dumps({'project_id':pid,'url':'/project-hub/'+pid,'paused':True,'criteria':'provisional','model_requests':0}))
    else:print(json.dumps({'milestones':store.listing(),'model_requests':0}))
if __name__=='__main__':main()
