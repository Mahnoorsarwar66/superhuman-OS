import argparse
import getpass
import json
from pathlib import Path
from . import config
from .auth import Store


def password():
    first=getpass.getpass('Choose a password (at least 12 characters): ')
    second=getpass.getpass('Repeat password: ')
    if first!=second:raise ValueError('Passwords do not match')
    return first


def main():
    p=argparse.ArgumentParser(description='Superhuman hosted setup (no model requests)')
    sub=p.add_subparsers(dest='command',required=True)
    s=sub.add_parser('setup');s.add_argument('--origin',required=True);s.add_argument('--tunnel',action='store_true');s.add_argument('--username',default='owner')
    s=sub.add_parser('set-origin');s.add_argument('--origin',required=True);s.add_argument('--tunnel',action='store_true')
    sub.add_parser('reset-password')
    sub.add_parser('status')
    recovery=sub.add_parser('recover-plans');recovery.add_argument('--older-than',type=int,default=3600)
    b=sub.add_parser('bundle');b.add_argument('--output',required=True)
    a=p.parse_args()
    try:
        if a.command=='setup':
            path=config.config_path();settings=config.Settings(a.origin,a.tunnel,state_dir=path.parent)
            store=Store(settings.auth_db)
            if path.exists() or store.configured():raise ValueError('Hosted setup already exists; use set-origin or reset-password')
            store.setup(a.username,password());config.save(settings,path)
            result={'configured':True,'username':a.username,'origin':settings.public_origin,'api_calls':0}
        elif a.command=='reset-password':
            settings=config.load();Store(settings.auth_db).reset_password(password())
            result={'password_changed':True,'sessions_revoked':True,'api_calls':0}
        elif a.command=='set-origin':
            old=config.load();settings=config.Settings(a.origin,a.tunnel,state_dir=old.state_dir,session_seconds=old.session_seconds,idle_seconds=old.idle_seconds)
            config.save(settings)
            with Store(settings.auth_db).connect() as db:db.execute('DELETE FROM sessions')
            result={'origin':settings.public_origin,'restart_web_service':True,'sessions_revoked':True,'api_calls':0}
        elif a.command=='status':
            settings=config.load()
            from . import jobs
            result={'configured':Store(settings.auth_db).configured(),'origin':settings.public_origin,'worker':jobs.worker_status(),'api_calls':0}
        elif a.command=='recover-plans':
            from . import jobs
            from superhuman.runtime import engine as runtime
            with runtime.worker_lock():recovered=jobs.recover_plans(a.older_than)
            result={'interrupted_plans':recovered,'api_calls':0}
        elif a.command=='bundle':
            from .transfer import bundle
            result=bundle(Path.cwd(),a.output)
        print(json.dumps(result,indent=2))
    except (ValueError,OSError) as exc:p.exit(1,str(exc)+'\n')


if __name__=='__main__':main()
