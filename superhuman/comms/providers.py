"""Bounded Slack HTTPS reads, existing email-cache bridge and signed WhatsApp intake."""
import hashlib,hmac,json,re,time
from urllib.request import Request,build_opener
from urllib.parse import urlencode,parse_qs
from urllib.error import HTTPError
from starlette.responses import PlainTextResponse
from superhuman.projects import engine as p
from superhuman.departments.store import tables
from superhuman.mail.providers import NoRedirect
from superhuman.mail import vault
from . import store

METHODS=('auth.test','conversations.history','conversations.replies')
class RateLimited(ValueError):
    def __init__(self,seconds=61):self.seconds=max(61,min(int(seconds),86400));super().__init__('Slack rate limited; retry scheduled')

def strict_json(raw):
    def pairs(items):
        d={}
        for k,v in items:
            if k in d:raise ValueError('Duplicate JSON field')
            d[k]=v
        return d
    return json.loads(raw,object_pairs_hook=pairs)

def slack_request(method,token,params):
    if method not in METHODS:raise ValueError('Only read-only Slack methods are implemented')
    req=Request('https://slack.com/api/'+method,data=urlencode(params).encode(),headers={'Authorization':'Bearer '+token,'Accept':'application/json'})
    try:
        with build_opener(NoRedirect()).open(req,timeout=10) as r:raw=r.read(524289)
    except HTTPError as exc:
        if exc.code==429:
            try:seconds=int(exc.headers.get('Retry-After','61'))
            except ValueError:seconds=61
            raise RateLimited(seconds) from None
        raise ValueError('Slack HTTP '+str(exc.code)) from None
    if len(raw)>524288:raise ValueError('Slack response exceeded size limit')
    value=strict_json(raw)
    if not isinstance(value,dict) or value.get('ok') is not True:
        code=value.get('error','unknown') if isinstance(value,dict) else 'invalid'
        raise ValueError('Slack '+(code if isinstance(code,str) and re.fullmatch(r'[a-z_]{1,50}',code) else 'request_error'))
    return value

def connect_slack(token,expected_team,label,path=p.DEFAULT_DB):
    token=store.text(token,16000,'Slack token',True)
    if not re.fullmatch(r'T[A-Z0-9]{5,39}',expected_team):raise ValueError('Use the expected Slack workspace ID')
    profile=slack_request('auth.test',token,{})
    if profile.get('team_id')!=expected_team or not isinstance(profile.get('user_id'),str):raise ValueError('Slack token belongs to a different workspace/account')
    return store.connect('slack',label,expected_team,profile['user_id'],{'token':token},path=path)

def connect_whatsapp(phone_id,app_secret,verify_token,label,path=p.DEFAULT_DB):
    if not re.fullmatch(r'[0-9]{5,30}',phone_id):raise ValueError('Use the Meta WhatsApp business phone-number ID, not a telephone number')
    app_secret=store.text(app_secret,1000,'Meta app secret',True);verify_token=store.text(verify_token,1000,'Webhook verification token',True)
    if len(app_secret)<20 or len(verify_token)<20:raise ValueError('Use private app/verification secrets of at least 20 characters')
    # Signature-valid, matching-number traffic is the connection check; no broad
    # Meta access token or sending permission is requested by this read-only adapter.
    return store.connect('whatsapp',label,phone_id,phone_id,{'app_secret':app_secret,'verify_token':verify_token},path=path)

def email_bridge(path=p.DEFAULT_DB):
    count=0
    with p.connect(path) as db:
        if 'comms_channels' not in tables(db) or 'mail_messages' not in tables(db):return 0
        for a in db.execute("SELECT * FROM comms_channels WHERE kind='email' AND enabled=1").fetchall():
            if not store.available(a,db):continue
            msgs=db.execute('SELECT * FROM mail_messages m WHERE account_id=? AND NOT EXISTS(SELECT 1 FROM comms_sources s WHERE s.channel_id=? AND s.remote_id=m.id) ORDER BY received,id LIMIT 50',(a['remote_id'],a['id'])).fetchall()
            for m in msgs:
                store.ingest(db,a,m['id'],m['remote_id'],m['sender'],m['subject'],m['body'],m['received'],m['notice']);count+=1
            if msgs:
                original=db.execute('SELECT last_sync,last_error FROM mail_accounts WHERE id=?',(a['remote_id'],)).fetchone()
                db.execute('UPDATE comms_channels SET last_sync=?,last_error=? WHERE id=?',(original['last_sync'],original['last_error'] or '',a['id']))
    return count

def slack_tick(path=p.DEFAULT_DB):
    now=time.time()
    with p.connect(path) as db:
        if 'comms_channels' not in tables(db):return None
        db.execute('BEGIN IMMEDIATE')
        # Only one HTTP call per workspace per >=61s, shared by history/threads.
        row=db.execute("SELECT s.id FROM comms_streams s JOIN comms_channels c ON c.id=s.channel_id WHERE c.kind='slack' AND c.connected=1 AND c.enabled=1 AND c.next_poll<=? AND s.enabled=1 AND s.next_poll<=? AND (s.root='' OR CAST(s.root AS REAL)>?) AND EXISTS(SELECT 1 FROM comms_streams parent WHERE parent.channel_id=s.channel_id AND parent.remote_id=s.remote_id AND parent.root='' AND parent.enabled=1) ORDER BY s.next_poll,s.root,s.id LIMIT 1",(now,now,now-7*86400)).fetchone()
        if not row:return None
        stream=dict(db.execute('SELECT * FROM comms_streams WHERE id=?',(row['id'],)).fetchone());a=dict(db.execute('SELECT * FROM comms_channels WHERE id=?',(stream['channel_id'],)).fetchone())
        ceiling=stream['ceiling'] or format(now,'.6f');oldest=stream['floor'] or (stream['watermark'] if float(stream['watermark']) else format(now-7*86400,'.6f'))
        db.execute('UPDATE comms_streams SET ceiling=?,floor=?,next_poll=? WHERE id=?',(ceiling,oldest,now+600,stream['id']));db.execute('UPDATE comms_channels SET next_poll=? WHERE id=?',(now+61,a['id']))
    try:
        secret=vault.open_secret(a['credential']);params={'channel':stream['remote_id'],'limit':15,'oldest':oldest,'latest':ceiling,'inclusive':'true'}
        if stream['cursor']:params['cursor']=stream['cursor']
        if stream['root']:params['ts']=stream['root']
        value=slack_request('conversations.replies' if stream['root'] else 'conversations.history',secret['token'],params)
        messages=value.get('messages',[]);cursor=value.get('response_metadata',{}).get('next_cursor','')
        if not isinstance(messages,list) or len(messages)>15 or not isinstance(cursor,str) or len(cursor)>2000:raise ValueError('Invalid Slack page')
        if cursor and cursor==stream['cursor']:raise ValueError('Slack cursor did not advance; inspect before rescan')
        if value.get('has_more') and not cursor:raise ValueError('Slack continuation missing; page held for inspection')
        with p.connect(path) as db:
            db.execute('BEGIN IMMEDIATE');fresh=db.execute('SELECT * FROM comms_channels WHERE id=?',(a['id'],)).fetchone();current=db.execute('SELECT * FROM comms_streams WHERE id=?',(stream['id'],)).fetchone()
            if not fresh['enabled'] or not fresh['connected'] or fresh['version']!=a['version'] or current['version']!=stream['version'] or not current['enabled']:return {'comms_read':'cancelled'}
            for item in messages:
                if not isinstance(item,dict):raise ValueError('Invalid Slack message')
                if item.get('subtype')=='message_changed':item=item.get('message',{})
                ts=item.get('ts','')
                if not isinstance(ts,str) or not re.fullmatch(r'[0-9]{1,12}\.[0-9]{1,9}',ts):raise ValueError('Invalid Slack message timestamp')
                body=item.get('text','');body=body if isinstance(body,str) else ''
                notice='Text preview only; files, blocks and attachments omitted. Slack identities are IDs, not independently verified people.'
                if item.get('subtype')=='message_deleted':body='[Message deleted]';notice='Provider deletion marker; earlier output may be stale.'
                if len(body)>6000:notice+=' Body truncated.'
                root=item.get('thread_ts',ts)
                store.ingest(db,a,stream['remote_id']+':'+ts,stream['remote_id']+':'+root,str(item.get('user',item.get('bot_id','Unknown')))[:500],stream['label'][:500],body[:6000],float(ts),notice)
                if not stream['root'] and isinstance(item.get('reply_count'),int) and item['reply_count']>0 and float(ts)>now-7*86400:
                    key=store.digest([a['id'],stream['remote_id'],ts])[:32]
                    if db.execute("SELECT COUNT(*) FROM comms_streams WHERE channel_id=? AND root!='' AND enabled=1",(a['id'],)).fetchone()[0]>=100 and not db.execute('SELECT 1 FROM comms_streams WHERE id=?',(key,)).fetchone():raise ValueError('Thread-following capacity reached; inspect conversation coverage')
                    db.execute('INSERT OR IGNORE INTO comms_streams(id,channel_id,remote_id,label,root) VALUES(?,?,?,?,?)',(key,a['id'],stream['remote_id'],stream['label'],ts))
            db.execute('UPDATE comms_streams SET cursor=?,watermark=?,ceiling=?,floor=?,next_poll=? WHERE id=?',(cursor,stream['watermark'] if cursor else ceiling,ceiling if cursor else '',oldest if cursor else '',now+61 if cursor else now+(1200 if stream['root'] else 600),stream['id']))
            db.execute("UPDATE comms_channels SET last_sync=?,last_error='' WHERE id=?",(p.stamp(),a['id']))
        return {'comms_read':'slack','messages':len(messages),'more':bool(cursor)}
    except Exception as exc:
        delay=exc.seconds if isinstance(exc,RateLimited) else 600
        message=str(exc)[:200] if isinstance(exc,ValueError) else type(exc).__name__
        with p.connect(path) as db:db.execute('UPDATE comms_channels SET next_poll=?,last_error=? WHERE id=? AND version=?',(now+delay,message,a['id'],a['version']))
        return {'comms_read':'slack_failed','error_type':type(exc).__name__}

def read_tick(path=p.DEFAULT_DB):
    if not store.channels(path):return None
    try:count=email_bridge(path)
    except ValueError as exc:
        with p.connect(path) as db:store.event(db,'email_bridge_held',{'reason':str(exc)[:200]},'system')
        count=0
    result=slack_tick(path)
    return result or ({'comms_read':'email_cache','messages':count} if count else None)

def whatsapp_candidates(path=p.DEFAULT_DB):
    return [store.channel(a['id'],path,True) for a in store.channels(path) if a['kind']=='whatsapp' and a['connected'] and a['enabled']]

def whatsapp_ingest(raw,signature,path=p.DEFAULT_DB):
    if not re.fullmatch(r'sha256=[0-9a-f]{64}',signature or ''):raise PermissionError('Signature required')
    matches=[]
    for a in whatsapp_candidates(path):
        secret=vault.open_secret(a['credential']);expected='sha256='+hmac.new(secret['app_secret'].encode(),raw,hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected,signature):matches.append(a)
    if not matches:raise PermissionError('Invalid signature')
    value=strict_json(raw)
    if not isinstance(value,dict) or value.get('object')!='whatsapp_business_account' or not isinstance(value.get('entry'),list) or len(value['entry'])>50:raise ValueError('Invalid WhatsApp envelope')
    count=0
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        for entry in value['entry']:
            changes=entry.get('changes',[])
            if not isinstance(changes,list) or len(changes)>100:raise ValueError('Invalid WhatsApp changes')
            for change in changes:
                if change.get('field')!='messages':continue
                v=change.get('value',{});phone=v.get('metadata',{}).get('phone_number_id')
                a=next((a for a in matches if a['remote_id']==phone),None)
                if not a:continue
                current=db.execute('SELECT * FROM comms_channels WHERE id=?',(a['id'],)).fetchone()
                if current['version']!=a['version'] or not current['enabled'] or not current['connected']:continue
                msgs=v.get('messages',[])
                if not isinstance(msgs,list) or len(msgs)>100:raise ValueError('Invalid WhatsApp message list')
                for m in msgs:
                    sender=m.get('from','');ident=m.get('id','');timestamp=m.get('timestamp','')
                    if not isinstance(sender,str) or not re.fullmatch(r'[0-9]{5,20}',sender) or not isinstance(ident,str) or not isinstance(timestamp,str) or not timestamp.isdigit():raise ValueError('Invalid WhatsApp message identity')
                    body=m.get('text',{}).get('body','') if m.get('type')=='text' else '[Unsupported message type: '+str(m.get('type','unknown'))[:30]+']'
                    if not isinstance(body,str):raise ValueError('Invalid WhatsApp text')
                    store.ingest(db,a,ident,sender,sender,'WhatsApp Business message',body[:6000],float(timestamp),'Text preview only; media and personal WhatsApp history are not fetched.');count+=1
                db.execute("UPDATE comms_channels SET last_sync=?,last_error='' WHERE id=?",(p.stamp(),a['id']))
    return count

async def webhook(scope,receive,headers,path=p.DEFAULT_DB):
    if scope['method']=='GET':
        try:
            q=parse_qs(scope.get('query_string',b'').decode(),max_num_fields=5)
            if any(len(v)!=1 for v in q.values()):raise ValueError('Duplicate parameter')
            token=q.get('hub.verify_token',[''])[0];challenge=q.get('hub.challenge',[''])[0]
            if q.get('hub.mode')!=['subscribe'] or not re.fullmatch(r'[0-9]{1,100}',challenge):raise ValueError('Invalid challenge')
            for a in whatsapp_candidates(path):
                secret=vault.open_secret(a['credential'])
                if hmac.compare_digest(token.encode(),secret['verify_token'].encode()):return PlainTextResponse(challenge)
            return PlainTextResponse('Verification denied',status_code=403)
        except (ValueError,UnicodeError):return PlainTextResponse('Invalid verification',status_code=400)
    if scope['method']!='POST':return PlainTextResponse('Method not allowed',status_code=405)
    if not headers.get('content-type','').startswith('application/json'):return PlainTextResponse('JSON required',status_code=415)
    parts=[];size=0
    try:
        while True:
            msg=await receive()
            if msg['type']=='http.disconnect':return PlainTextResponse('Disconnected',status_code=400)
            size+=len(msg.get('body',b''))
            if size>262144:return PlainTextResponse('Payload too large',status_code=413)
            parts.append(msg.get('body',b''))
            if not msg.get('more_body',False):break
        whatsapp_ingest(b''.join(parts),headers.get('x-hub-signature-256',''),path)
        return PlainTextResponse('ok')
    except PermissionError:return PlainTextResponse('Signature denied',status_code=403)
    except (ValueError,TypeError,KeyError,AttributeError,UnicodeError):return PlainTextResponse('Invalid payload',status_code=400)
