"""Owner-only inbox setup. Secrets are prompted or imported, never CLI arguments."""
import argparse
import getpass
import json
import os
from pathlib import Path
from . import store,providers


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',type=Path,default=store.p.DEFAULT_DB)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('status');sub.add_parser('scopes')
    for name in ('connect-titan','import-gmail','disconnect','sync'):
        cmd=sub.add_parser(name);cmd.add_argument('slot',choices=store.SLOTS)
        if name in ('connect-titan','import-gmail'):
            cmd.add_argument('--email',required=True);cmd.add_argument('--scope',required=True)
        if name=='connect-titan':cmd.add_argument('--host-profile',choices=store.HOSTS,default='godaddy')
        if name=='import-gmail':cmd.add_argument('--file',required=True,type=Path)
    args=parser.parse_args()
    try:
        if args.command=='status':
            result={'inboxes':store.accounts(args.db),'model_calls':0}
        elif args.command=='scopes':result={'workstreams':store.dialogue.scopes()}
        elif args.command=='disconnect':
            store.disconnect(args.slot,args.db);result={'disconnected':args.slot,'saved_previews_retained':True,'google_access_revoked':False}
        elif args.command=='sync':
            result={'queued':store.queue_sync(args.slot,args.db),'model_calls':0}
        elif args.command=='connect-titan':
            if args.slot!='edsync_titan':raise ValueError('Choose edsync_titan')
            email=store.email_address(args.email);host=store.HOSTS[args.host_profile]
            secret={'password':getpass.getpass('Titan email password (typing is invisible): ')}
            if not secret['password']:raise ValueError('Password cannot be blank')
            # EXAMINE and LOGOUT only while checking the credential; no mail fetched yet.
            import imaplib,ssl
            conn=imaplib.IMAP4_SSL(host,993,ssl_context=ssl.create_default_context(),timeout=10)
            try:
                if conn.login(email,secret['password'])[0]!='OK' or conn.select('INBOX',readonly=True)[0]!='OK':
                    raise ValueError('Cannot authenticate and examine this inbox')
            finally:
                try:conn.logout()
                except Exception:pass
            store.connect(args.slot,email,args.scope,secret,host,args.db);result={'connected':args.slot,'read_only':True}
        else:
            if store.SLOTS[args.slot][1]!='gmail':raise ValueError('Choose a Gmail inbox')
            source=args.file.expanduser()
            if source.is_symlink() or source.stat().st_size>65536:raise ValueError('Invalid Gmail credential file')
            if os.name!='nt' and source.stat().st_mode & 0o077:raise ValueError('Run chmod 600 on the imported file first')
            payload=json.loads(source.read_text(encoding='utf-8-sig'))
            if payload.get('slot')!=args.slot or payload.get('email')!=store.email_address(args.email) or payload.get('scope')!=providers.SCOPE:
                raise ValueError('Credential file does not match this inbox and read-only scope')
            secret={key:store.dialogue.text(payload.get(key),16000,key) for key in ('client_id','client_secret','refresh_token')}
            providers.verify_gmail(secret,args.email)
            store.connect(args.slot,args.email,args.scope,secret,path=args.db)
            source.unlink()  # Remove transfer copy only AFTER successful encrypted storage.
            result={'connected':args.slot,'read_only':True,'transfer_copy_removed':True}
        print(json.dumps(result,indent=2))
    except Exception as exc:
        message=str(exc) if isinstance(exc,ValueError) else 'Connection operation failed ('+type(exc).__name__+'). Check the provider and supplied settings.'
        parser.exit(1,message+'\n')


if __name__=='__main__':main()
