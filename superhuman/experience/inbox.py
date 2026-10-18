"""A read-only view of saved previews; rendering never syncs or grants AI consent."""
from datetime import datetime,timezone
from superhuman.projects import engine as p
from . import store

def accounts(path=p.DEFAULT_DB):
    from superhuman.comms import store as comms
    values=[]
    for c in comms.channels(path):values.append(dict(c,key='c:'+c['id']))
    for a in store.read('mail_accounts','SELECT id,label,provider,email,auto_sync,last_sync,last_error,credential IS NOT NULL AS connected FROM mail_accounts',path=path):
        # Legacy mailbox and its linked communications channel share an account identity.
        linked=next((c for c in values if c['kind']=='email' and c['remote_id']==a['id']),None)
        if linked:
            linked['last_sync']=a['last_sync'];linked['last_error']=a['last_error']
            continue
        values.append(dict(a,key='m:'+a['id'],kind='email',enabled=a['auto_sync'],ai_enabled=0,identity=a['email'] or '',remote_id=a['id']))
    from superhuman.mail.store import SLOTS
    for ident,(label,provider) in SLOTS.items():
        if not any(a.get('remote_id')==ident for a in values):values.append(dict(id=ident,key='m:'+ident,label=label,kind='email',identity='',remote_id=ident,connected=0,enabled=0,ai_enabled=0,last_sync=None,last_error=''))
    return values

def messages(path=p.DEFAULT_DB,limit=5000):
    from superhuman.comms import store as comms
    values=[];linked=set()
    aliases={a['remote_id']:'c:'+a['id'] for a in comms.channels(path) if a['kind']=='email'}
    for m in comms.sources(path,limit):
        if m['archived']:continue
        values.append(dict(m,id='c:'+m['id'],source_id=m['id'],account='c:'+m['channel_id'],url='/assistant/sources/'+m['id']))
        linked.add(m['remote_id'])
    for m in store.read('mail_messages','SELECT * FROM mail_messages ORDER BY received DESC,id LIMIT ?',(limit,),path):
        if m['id'] in linked:continue
        values.append(dict(m,id='m:'+m['id'],source_id=m['id'],account=aliases.get(m['account_id'],'m:'+m['account_id']),url='/inboxes/'+m['account_id']))
    states={r['source_id']:r['state'] for r in store.read('ux_message_states','SELECT * FROM ux_message_states',path=path)}
    for m in values:m['review_state']=states.get(m['id'],states.get('m:'+m.get('remote_id',''),'unreviewed'))
    return sorted(values,key=lambda r:(r['received'],r['id']),reverse=True)[:limit]

def mark(ident,state,path=p.DEFAULT_DB):
    if state not in ('unreviewed','reviewed','follow_up'):raise ValueError('Choose a review state')
    if ident not in {m['id'] for m in messages(path)}:raise ValueError('Message not found')
    store.initialize(path)
    with p.connect(path) as db:db.execute('INSERT INTO ux_message_states(source_id,state) VALUES(?,?) ON CONFLICT(source_id) DO UPDATE SET state=excluded.state,version=version+1',(ident,state))

def assessment(ident,path=p.DEFAULT_DB):
    import json
    from superhuman.comms import store as comms
    if not ident.startswith('c:'):return None
    sid=ident[2:];source=comms.source(sid,path)
    for run in comms.runs(path):
        if run['status']!='done':continue
        try:
            snap=json.loads(run['snapshot']);result=json.loads(run['result'] or '{}')
            for item in result.get('items',[]):
                alias=snap.get('aliases',{}).get(item.get('source'),{})
                if alias.get('source_id',alias.get('id'))==sid:
                    return dict(item,stale=alias.get('digest')!=source['digest'],created_at=run['finished_at'])
        except (ValueError,TypeError,AttributeError):continue
    return None
