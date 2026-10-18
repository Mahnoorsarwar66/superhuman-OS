"""Bounded read-only Gmail HTTPS and Titan IMAPS clients. Never send or mark read."""
import base64
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import imaplib
import json
import re
import ssl
import time
from urllib.parse import urlencode, quote
from urllib.request import Request, build_opener, HTTPRedirectHandler
from . import store, vault

SCOPE='https://www.googleapis.com/auth/gmail.readonly'
TOKEN_URL='https://oauth2.googleapis.com/token'
API='https://gmail.googleapis.com/gmail/v1/users/me/'
MAX_RAW=262144
MAX_MESSAGES=25


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('Unexpected provider redirect')


def request_json(url,form=None,access_token=None):
    if not (url==TOKEN_URL or url.startswith(API)):
        raise ValueError('Unsupported provider endpoint')
    headers={'Accept':'application/json'}
    if access_token:headers['Authorization']='Bearer '+access_token
    data=urlencode(form).encode() if form is not None else None
    req=Request(url,data=data,headers=headers)
    with build_opener(NoRedirect()).open(req,timeout=10) as response:
        raw=response.read(524289)
    if len(raw)>524288:raise ValueError('Provider response exceeded the size limit')
    return json.loads(raw)


def refresh(secret):
    result=request_json(TOKEN_URL,form={'client_id':secret['client_id'],'client_secret':secret['client_secret'],
                        'refresh_token':secret['refresh_token'],'grant_type':'refresh_token'})
    if set(result.get('scope','').split())!={SCOPE}:raise ValueError('Gmail grant must be read-only only')
    return result['access_token']


def verify_gmail(secret,expected):
    token=refresh(secret)
    profile=request_json(API+'profile',access_token=token)
    if store.email_address(profile['emailAddress'])!=store.email_address(expected):
        raise ValueError('Google account differs from the requested inbox')
    return token


class PlainHTML(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.parts=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.hidden+=1
        if tag in ('br','p','div','li'):self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.hidden=max(0,self.hidden-1)
    def handle_data(self,text):
        if not self.hidden:self.parts.append(text)


def parse_message(raw,remote_id,received=None,notice=''):
    msg=BytesParser(policy=policy.default).parsebytes(raw)
    plain=[];html=[]
    for part in msg.walk():
        if part.get_content_disposition()=='attachment' or part.get_filename():continue
        if part.get_content_type() not in ('text/plain','text/html'):continue
        data=part.get_payload(decode=True)
        if data is None:continue
        charset=part.get_content_charset() or 'utf-8'
        try:value=data.decode(charset,errors='replace')
        except LookupError:value=data.decode('utf-8',errors='replace')
        (plain if part.get_content_type()=='text/plain' else html).append(value)
    if plain:body='\n'.join(plain)
    else:
        parser=PlainHTML();parser.feed('\n'.join(html));body=''.join(parser.parts)
    body=''.join(c for c in body if c in '\n\t' or ord(c)>=32).strip()
    if len(body)>6000:notice+=' Body preview truncated to 6000 characters.'
    try:
        date=parsedate_to_datetime(str(msg.get('Date','')))
        if date.tzinfo is None:date=date.replace(tzinfo=timezone.utc)
        timestamp=date.timestamp()
    except (ValueError,TypeError,OverflowError):timestamp=time.time()
    return dict(remote_id=remote_id,sender=str(msg.get('From',''))[:500],subject=str(msg.get('Subject','(No subject)'))[:500],
                sent_at=str(msg.get('Date',''))[:100],body=body[:6000],notice=(notice+' Attachments not downloaded.')[:300],
                received=received if received is not None else timestamp)


def gmail(account,secret):
    token=verify_gmail(secret,account['email']);started=time.monotonic()
    page=request_json(API+'messages?'+urlencode({'labelIds':'INBOX','q':'newer_than:7d','maxResults':MAX_MESSAGES}),access_token=token)
    result=[];limited=bool(page.get('nextPageToken'))
    for item in page.get('messages',[])[:MAX_MESSAGES]:
        if time.monotonic()-started>45:limited=True;break
        mid=item['id']
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',mid):raise ValueError('Invalid Gmail message identifier')
        meta=request_json(API+'messages/'+quote(mid,safe='')+'?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date',access_token=token)
        received=int(meta.get('internalDate',int(time.time()*1000)))/1000
        if int(meta.get('sizeEstimate',MAX_RAW+1))>MAX_RAW:
            headers=meta.get('payload',{}).get('headers',[])
            raw='\r\n'.join(h['name']+': '+h['value'].replace('\r',' ').replace('\n',' ') for h in headers if h['name'].casefold() in ('from','subject','date')).encode()+b'\r\n\r\n'
            m=parse_message(raw,mid,received,'Large message: body omitted; subject and sender only.')
        else:
            data=request_json(API+'messages/'+quote(mid,safe='')+'?format=raw',access_token=token)
            encoded=data['raw']
            if len(encoded)>MAX_RAW*4//3+8:raise ValueError('Message exceeded declared size')
            raw=base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4))
            m=parse_message(raw,mid,received)
        result.append(m)
    return result,limited


def titan(account,secret,imap_factory=imaplib.IMAP4_SSL):
    if account['host'] not in store.HOSTS.values():raise ValueError('Unsupported Titan host')
    conn=imap_factory(account['host'],993,ssl_context=ssl.create_default_context(),timeout=10)
    started=time.monotonic()
    try:
        status,_=conn.login(account['email'],secret['password'])
        if status!='OK':raise ValueError('Titan authentication failed')
        status,_=conn.select('INBOX',readonly=True)
        if status!='OK':raise ValueError('Cannot read Titan inbox')
        validity=conn.response('UIDVALIDITY')[1]
        if not validity or not validity[0] or not re.fullmatch(rb'[0-9]+',validity[0]):raise ValueError('Titan UID validity missing')
        prefix=validity[0].decode()+':'
        since=(datetime.now(timezone.utc)-timedelta(days=7)).strftime('%d-%b-%Y')
        status,data=conn.uid('SEARCH',None,'SINCE',since)
        if status!='OK':raise ValueError('Titan search failed')
        ids=(data[0] or b'').split()
        if any(not re.fullmatch(rb'[0-9]+',uid) for uid in ids):raise ValueError('Invalid Titan message identifier')
        result=[];limited=len(ids)>MAX_MESSAGES
        for uid in reversed(ids[-MAX_MESSAGES:]):
            if time.monotonic()-started>45:limited=True;break
            status,size_data=conn.uid('FETCH',uid,'(RFC822.SIZE)')
            size=re.search(rb'RFC822.SIZE\s+(\d+)',b' '.join(x for x in size_data if isinstance(x,bytes)))
            if status!='OK' or not size:raise ValueError('Cannot determine Titan message size')
            large=int(size.group(1))>MAX_RAW
            part='(BODY.PEEK[HEADER]<0.16384>)' if large else '(BODY.PEEK[]<0.262144>)'
            status,data=conn.uid('FETCH',uid,part)
            if status!='OK':raise ValueError('Cannot read Titan message')
            raw=b''.join(x[1] for x in data if isinstance(x,tuple) and isinstance(x[1],bytes))
            if len(raw)>MAX_RAW:raise ValueError('Titan message exceeded size limit')
            result.append(parse_message(raw,prefix+uid.decode(),notice='Large message: body omitted.' if large else ''))
        return result,limited
    finally:
        try:conn.logout()
        except Exception:pass


def run_sync(path=store.p.DEFAULT_DB):
    from superhuman.mailflow.engine import run_sync as resume_sync
    return resume_sync(path)
