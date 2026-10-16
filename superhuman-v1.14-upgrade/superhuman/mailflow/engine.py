"""Small resumable read batches. No model calls and no remote mailbox mutations."""
import base64
from datetime import datetime,timezone,timedelta
import imaplib
import json
import re
import ssl
import time
from urllib.error import HTTPError
from urllib.parse import urlencode,quote
from superhuman.mail import store,providers as old,vault
from . import state


class Gmail:
    validity=''
    def __init__(self,account,secret):self.token=old.verify_gmail(secret,account['email'])
    def discover(self,scan,c):
        args={'labelIds':'INBOX','q':f"after:{int(scan['start'])-1} before:{int(scan['end'])+1}",'maxResults':100}
        if c['token']:args['pageToken']=c['token']
        page=old.request_json(old.API+'messages?'+urlencode(args),access_token=self.token)
        ids=[m['id'] for m in page.get('messages',[])]
        if len(ids)>100 or any(not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',v) for v in ids):raise ValueError('Invalid Gmail page')
        token=page.get('nextPageToken','')
        if not isinstance(token,str) or len(token)>4096 or (token and token==c['token']):raise ValueError('Invalid or repeated Gmail page token')
        return ids,token,not bool(token),False
    def fetch(self,remote_id,scan):
        url=old.API+'messages/'+quote(remote_id,safe='')
        try:
            meta=old.request_json(url+'?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date',access_token=self.token)
            received=int(meta.get('internalDate',int(time.time()*1000)))/1000
            if int(meta.get('sizeEstimate',old.MAX_RAW+1))>old.MAX_RAW:
                headers=meta.get('payload',{}).get('headers',[])
                raw='\r\n'.join(h['name']+': '+h['value'].replace('\r',' ').replace('\n',' ') for h in headers if h['name'].casefold() in ('from','subject','date')).encode()+b'\r\n\r\n'
                return old.parse_message(raw,remote_id,received,'Large message: body omitted; headers only.')
            data=old.request_json(url+'?format=raw',access_token=self.token);encoded=data['raw']
            if len(encoded)>old.MAX_RAW*4//3+8:raise ValueError('Oversized Gmail response')
            return old.parse_message(base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4)),remote_id,received)
        except HTTPError as exc:
            if exc.code==404:return None
            raise
    def close(self):pass


class Titan:
    def __init__(self,account,secret):
        if account['host'] not in store.HOSTS.values():raise ValueError('Unsupported Titan host')
        self.conn=imaplib.IMAP4_SSL(account['host'],993,ssl_context=ssl.create_default_context(),timeout=10)
        try:
            if self.conn.login(account['email'],secret['password'])[0]!='OK':raise ValueError('Authentication failed')
            if self.conn.select('INBOX',readonly=True)[0]!='OK':raise ValueError('Cannot examine inbox')
            data=self.conn.response('UIDVALIDITY')[1]
            if not data or not data[0] or not re.fullmatch(rb'\d+',data[0]):raise ValueError('Missing UID validity')
            self.validity=data[0].decode()
        except Exception:self.close();raise
    def discover(self,scan,c):
        # UID identities are frozen as a bounded list, not sequence numbers that
        # change when another client deletes mail. IMAP day bounds are refined
        # using INTERNALDATE while fetching each message.
        start=datetime.fromtimestamp(scan['start'],timezone.utc);end=datetime.fromtimestamp(scan['end'],timezone.utc)+timedelta(days=1)
        months=('Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec')
        def date(d):return f'{d.day:02d}-{months[d.month-1]}-{d.year}'
        status,data=self.conn.uid('SEARCH',None,'SINCE',date(start),'BEFORE',date(end))
        if status!='OK':raise ValueError('Titan search failed')
        ids=(data[0] or b'').split()
        if any(not re.fullmatch(rb'\d+',v) for v in ids):raise ValueError('Invalid Titan UIDs')
        ids=sorted(set(ids),key=int,reverse=True);excess=len(ids)>50000
        return [self.validity+':'+uid.decode() for uid in ids[:50000]],'',True,excess
    def fetch(self,remote_id,scan):
        validity,uid=remote_id.split(':')
        if validity!=self.validity or not uid.isdigit():raise ValueError('Titan UID namespace changed')
        status,data=self.conn.uid('FETCH',uid.encode(),'(RFC822.SIZE INTERNALDATE)')
        if status!='OK':raise ValueError('Titan metadata unavailable')
        raw=b' '.join(v for v in data if isinstance(v,bytes))
        if not raw:return None
        size=re.search(rb'RFC822.SIZE\s+(\d+)',raw);date=imaplib.Internaldate2tuple(raw)
        if not size or date is None:raise ValueError('Titan size/date missing')
        received=time.mktime(date)
        if not scan['start']<=received<=scan['end']:return None
        large=int(size.group(1))>old.MAX_RAW
        part='(BODY.PEEK[HEADER]<0.16384>)' if large else '(BODY.PEEK[]<0.262144>)'
        status,data=self.conn.uid('FETCH',uid.encode(),part)
        if status!='OK':raise ValueError('Titan message unavailable')
        raw=b''.join(v[1] for v in data if isinstance(v,tuple) and isinstance(v[1],bytes))
        if not raw:return None
        if len(raw)>old.MAX_RAW:raise ValueError('Oversized Titan body')
        return old.parse_message(raw,remote_id,received,'Large message: body omitted.' if large else '')
    def close(self):
        try:self.conn.logout()
        except Exception:pass


def session_factory(account,secret):return (Gmail if account['provider']=='gmail' else Titan)(account,secret)


def run_sync(path=store.p.DEFAULT_DB):
    job=store.claim(path)
    if job is None:return None
    scan=None;session=None;c=None;started=time.monotonic()
    try:
        account=store.account(job['account_id'],path,secrets=True)
        if account['generation']!=job['generation']:raise ValueError('Connection changed')
        scan=state.scan(account,path);c=json.loads(scan['cursor'])
        session=session_factory(account,vault.open_secret(account['credential']))
        if session.validity and c['validity'] and session.validity!=c['validity']:
            c=state.cursor();state.checkpoint(scan,c,note='Titan UID validity changed; this scoped scan was restarted safely.',path=path)
        c['validity']=session.validity
        fetched=0;visited=0;pages=0;status='active'
        while fetched<25 and visited<250 and time.monotonic()-started<30:
            if not c['pending']:
                if c['listed']:
                    status='scope_limited' if c['excess'] else 'complete';break
                if pages>=5:break
                ids,token,listed,excess=session.discover(scan,c)
                pages+=1
                c['pending']=list(dict.fromkeys(ids));c['token']=token;c['listed']=listed;c['excess']=excess
                c['found']+=len(c['pending']);c['pages']+=1
                state.checkpoint(scan,c,path=path)
                continue
            remote_id=c['pending'][0];visited+=1
            if state.known(account['id'],remote_id,path):
                c['pending'].pop(0);c['processed']+=1;state.checkpoint(scan,c,path=path);continue
            if not state.make_room(account['id'],path):status='capacity_blocked';break
            message=session.fetch(remote_id,scan);fetched+=1
            c['pending'].pop(0);c['processed']+=1
            if message is None:c['unavailable']+=1
            else:
                c['saved']+=1
                message['notice']=message['notice'].replace('Attachments not downloaded.','Attachment content not extracted or saved.')
            # Cursor + message + durable identity commit together; a crash cannot
            # advance past a message that was never saved.
            state.checkpoint(scan,c,message=message,path=path)
        if not c['pending'] and c['listed']:status='scope_limited' if c['excess'] else 'complete'
        note={'complete':'Scoped scan finished; full bodies and all folders are not covered.',
              'active':'More messages remain; another read batch is queued automatically.',
              'capacity_blocked':'Preview capacity reached. Complete reports, then read again; unreported previews are retained.',
              'scope_limited':'Provider search exceeded the 50,000-message discovery bound; this scan is incomplete.'}[status]
        state.checkpoint(scan,c,status=status,note=note,path=path);state.finish_job(job,scan,status,path=path)
        return {'mail_sync_id':job['id'],'account_id':account['id'],'status':status,'model_calls':0}
    except Exception as exc:
        error='Inbox read stopped ('+type(exc).__name__+'). Saved progress retained. Check access/expiry; retry Read, or restart the scan if its provider cursor expired.'
        if scan is not None:
            try:
                # Reload committed progress: an in-memory pop may have preceded
                # a failed DB write. Never persist that uncommitted advance.
                with store.p.connect(path) as db:
                    saved=db.execute('SELECT cursor FROM mail_scans WHERE account_id=? AND id=?',(scan['account_id'],scan['id'])).fetchone()
                if saved is None:raise ValueError('Scan changed')
                c=json.loads(saved['cursor'])
                state.checkpoint(scan,c,status='error',note=error,path=path);state.finish_job(job,scan,'error',error,path)
            except ValueError:
                with store.p.connect(path) as db:db.execute("UPDATE mail_syncs SET status='cancelled' WHERE id=?",(job['id'],))
        else:store.finish_sync(job,[],error=error,path=path)
        return {'mail_sync_id':job['id'],'account_id':job['account_id'],'status':'failed','model_calls':0}
    finally:
        if session is not None:session.close()
