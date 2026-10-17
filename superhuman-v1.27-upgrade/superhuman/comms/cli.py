"""Private terminal setup; tokens never appear in shell arguments or output."""
import argparse,getpass,json
from pathlib import Path
from superhuman.projects import engine as p
from . import store,providers

def main():
    parser=argparse.ArgumentParser(description='Superhuman read-only communications setup')
    parser.add_argument('--db',type=Path,default=p.DEFAULT_DB);sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('status');sub.add_parser('initialize')
    email=sub.add_parser('link-email');email.add_argument('slot')
    slack=sub.add_parser('connect-slack');slack.add_argument('--team-id',required=True);slack.add_argument('--label',required=True)
    wa=sub.add_parser('connect-whatsapp');wa.add_argument('--phone-id',required=True);wa.add_argument('--label',required=True)
    stream=sub.add_parser('allow-slack');stream.add_argument('channel_id');stream.add_argument('--conversation-id',required=True);stream.add_argument('--label',required=True)
    scan=sub.add_parser('rescan-slack');scan.add_argument('stream_id');scan.add_argument('--version',type=int,required=True);scan.add_argument('--note',required=True)
    args=parser.parse_args()
    try:
        if args.command=='initialize':store.initialize(args.db);result={'initialized':True,'enabled':False}
        elif args.command=='status':result={'settings':store.settings(args.db),'channels':store.channels(args.db),'model_calls':0}
        elif args.command=='link-email':result={'channel_id':store.link_email(args.slot,args.db),'reading_and_ai':'off until explicit enable'}
        elif args.command=='connect-slack':result={'channel_id':providers.connect_slack(getpass.getpass('Slack read-only token (hidden): '),args.team_id,args.label,args.db),'reading_and_ai':'off until explicit enable'}
        elif args.command=='connect-whatsapp':result={'channel_id':providers.connect_whatsapp(args.phone_id,getpass.getpass('Meta app secret (hidden): '),getpass.getpass('Private webhook verification token, >=20 characters (hidden): '),args.label,args.db),'identity_check':'Pending signed matching-phone webhook','reading_and_ai':'off until explicit enable'}
        elif args.command=='rescan-slack':store.rescan_stream(args.stream_id,args.version,args.note,args.db);result={'rescan_authorized':True}
        else:result={'stream_id':store.add_stream(args.channel_id,args.conversation_id,args.label,args.db)}
        print(json.dumps(result,indent=2))
    except Exception as exc:parser.exit(1,(str(exc) if isinstance(exc,ValueError) else 'Setup failed ('+type(exc).__name__+'); inspect account and private settings.')+'\n')

if __name__=='__main__':main()
