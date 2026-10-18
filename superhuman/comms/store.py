"""Durable, opt-in communications; only the owner may share private intake."""
import hashlib,json,re,time
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from superhuman.projects import engine as p
from superhuman.departments.store import readonly,tables,rows
from superhuman.team import store as team,budget
from superhuman.mail import vault

KINDS=('email','slack','whatsapp')
SLOTS=('morning','midday','evening')

def text(value,n,label,required=False):return team.text(value,n,label,required)
def digest(value):return hashlib.sha256(team.encode(value).encode()).hexdigest()
def initialize(path=p.DEFAULT_DB):
    team.initialize(path)
    with p.connect(path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS comms_settings(id INTEGER PRIMARY KEY CHECK(id=1),enabled INTEGER NOT NULL DEFAULT 0,version INTEGER NOT NULL DEFAULT 1,timezone TEXT NOT NULL DEFAULT 'Asia/Karachi',morning TEXT NOT NULL DEFAULT '09:00',midday TEXT NOT NULL DEFAULT '14:00',evening TEXT NOT NULL DEFAULT '20:30',daily_limit INTEGER NOT NULL DEFAULT 12,activated REAL NOT NULL DEFAULT 0,next_intake REAL NOT NULL DEFAULT 0);
        INSERT OR IGNORE INTO comms_settings(id) VALUES(1);
        CREATE TABLE IF NOT EXISTS comms_channels(id TEXT PRIMARY KEY,kind TEXT NOT NULL,label TEXT NOT NULL,identity TEXT NOT NULL,remote_id TEXT NOT NULL,credential TEXT,connected INTEGER NOT NULL DEFAULT 1,enabled INTEGER NOT NULL DEFAULT 0,ai_enabled INTEGER NOT NULL DEFAULT 0,version INTEGER NOT NULL DEFAULT 1,next_poll REAL NOT NULL DEFAULT 0,last_sync TEXT,last_error TEXT NOT NULL DEFAULT '',generation TEXT NOT NULL DEFAULT '',UNIQUE(kind,identity));
        CREATE TABLE IF NOT EXISTS comms_streams(id TEXT PRIMARY KEY,channel_id TEXT NOT NULL,remote_id TEXT NOT NULL,label TEXT NOT NULL,root TEXT NOT NULL DEFAULT '',cursor TEXT NOT NULL DEFAULT '',watermark TEXT NOT NULL DEFAULT '0',ceiling TEXT NOT NULL DEFAULT '',floor TEXT NOT NULL DEFAULT '',next_poll REAL NOT NULL DEFAULT 0,enabled INTEGER NOT NULL DEFAULT 1,version INTEGER NOT NULL DEFAULT 1,UNIQUE(channel_id,remote_id,root));
        CREATE TABLE IF NOT EXISTS comms_sources(id TEXT PRIMARY KEY,channel_id TEXT NOT NULL,remote_id TEXT NOT NULL,thread TEXT NOT NULL,sender TEXT NOT NULL,subject TEXT NOT NULL,body TEXT NOT NULL,received REAL NOT NULL,notice TEXT NOT NULL,digest TEXT NOT NULL,analysed_digest TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 1,archived INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,UNIQUE(channel_id,remote_id));
        CREATE INDEX IF NOT EXISTS comms_source_pending ON comms_sources(channel_id,archived,received);
        CREATE TABLE IF NOT EXISTS comms_runs(id TEXT PRIMARY KEY,submission TEXT NOT NULL UNIQUE,kind TEXT NOT NULL,status TEXT NOT NULL,snapshot TEXT NOT NULL,result TEXT,error TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,finished_at TEXT,version INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS comms_drafts(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,source_id TEXT NOT NULL,source_digest TEXT NOT NULL,body TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'draft',version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS comms_proposals(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,source_id TEXT NOT NULL,source_digest TEXT NOT NULL,department TEXT NOT NULL,title TEXT NOT NULL,instruction TEXT NOT NULL,acceptance TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'proposed',task_id TEXT,version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS comms_alerts(id TEXT PRIMARY KEY,source_id TEXT NOT NULL,digest TEXT NOT NULL,headline TEXT NOT NULL,reason TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'new',created_at TEXT NOT NULL,UNIQUE(source_id,digest));
        CREATE TABLE IF NOT EXISTS comms_events(seq INTEGER PRIMARY KEY AUTOINCREMENT,actor TEXT NOT NULL,action TEXT NOT NULL,detail TEXT NOT NULL,created_at TEXT NOT NULL);
        ''')
def event(db,action,detail=None,actor='owner'):db.execute('INSERT INTO comms_events(actor,action,detail,created_at) VALUES(?,?,?,?)',(actor,action,team.encode(detail or {}),p.stamp()))
def read_rows(table,sql,args=(),path=p.DEFAULT_DB):
    with readonly(path) as db:return rows(db,sql,args) if table in tables(db) else []
def settings(path=p.DEFAULT_DB):
    found=read_rows('comms_settings','SELECT * FROM comms_settings',path=path)
    return found[0] if found else {'enabled':0,'version':0,'timezone':'Asia/Karachi','morning':'09:00','midday':'14:00','evening':'20:30','daily_limit':12,'activated':0,'next_intake':0}
def channels(path=p.DEFAULT_DB):return read_rows('comms_channels','SELECT id,kind,label,identity,remote_id,connected,enabled,ai_enabled,version,next_poll,last_sync,last_error,generation FROM comms_channels ORDER BY kind,label',path=path)
def channel(ident,path=p.DEFAULT_DB,secret=False):
    values=read_rows('comms_channels','SELECT * FROM comms_channels WHERE id=?',(ident,),path)
    if not values:raise ValueError('Communication channel not found')
    result=values[0]
    if not secret:result.pop('credential',None)
    return result
def streams(ident,path=p.DEFAULT_DB):return read_rows('comms_streams','SELECT * FROM comms_streams WHERE channel_id=? ORDER BY root,remote_id',(ident,),path)
def sources(path=p.DEFAULT_DB,limit=100):
    if type(limit) is not int or not 1<=limit<=5000:raise ValueError('Invalid preview limit')
    return read_rows('comms_sources','SELECT * FROM comms_sources ORDER BY received DESC,id LIMIT ?',(limit,),path)
def source(ident,path=p.DEFAULT_DB):
    found=read_rows('comms_sources','SELECT * FROM comms_sources WHERE id=?',(ident,),path)
    if not found:raise ValueError('Message preview not found')
    return found[0]
def runs(path=p.DEFAULT_DB):return read_rows('comms_runs','SELECT * FROM comms_runs ORDER BY created_at DESC,id DESC LIMIT 50',path=path)
def run(ident,path=p.DEFAULT_DB):
    found=read_rows('comms_runs','SELECT * FROM comms_runs WHERE id=?',(ident,),path)
    if not found:raise ValueError('Assistant run not found')
    return found[0]
def proposals(path=p.DEFAULT_DB):return read_rows('comms_proposals','SELECT * FROM comms_proposals ORDER BY created_at DESC LIMIT 100',path=path)
def drafts(path=p.DEFAULT_DB):return read_rows('comms_drafts','SELECT * FROM comms_drafts ORDER BY created_at DESC LIMIT 100',path=path)
def alerts(path=p.DEFAULT_DB):return read_rows('comms_alerts',"SELECT * FROM comms_alerts ORDER BY CASE WHEN state='new' THEN 0 ELSE 1 END,created_at DESC LIMIT 100",path=path)
def audit(path=p.DEFAULT_DB):return read_rows('comms_events','SELECT * FROM comms_events ORDER BY seq DESC LIMIT 100',path=path)

def configure(expected,enabled,timezone,morning,midday,evening,daily_limit=12,path=p.DEFAULT_DB):
    try:ZoneInfo(timezone)
    except (ZoneInfoNotFoundError,ValueError,TypeError):raise ValueError('Choose an installed IANA timezone') from None
    times=(morning,midday,evening)
    if any(not isinstance(v,str) or not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]',v) for v in times) or not morning<midday<evening:raise ValueError('Use three ordered HH:MM briefing times')
    if type(enabled) is not bool or type(daily_limit) is not int or not 3<=daily_limit<=24:raise ValueError('Daily model-run ceiling must be 3–24')
    initialize(path)
    if enabled and (not team.enabled(path) or not budget.ready(team.settings(path)['model'],path)):raise ValueError('Enable the v1.26 team and confirm a live dollar budget/rate card first')
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT * FROM comms_settings WHERE id=1').fetchone()
        if old['version']!=expected:raise ValueError('Assistant settings changed; reload')
        activated=time.time() if enabled and not old['enabled'] else old['activated']
        db.execute('UPDATE comms_settings SET enabled=?,timezone=?,morning=?,midday=?,evening=?,daily_limit=?,activated=?,version=version+1 WHERE id=1',(int(enabled),timezone,*times,daily_limit,activated));event(db,'assistant_configured',{'enabled':enabled,'timezone':timezone,'times':times,'daily_limit':daily_limit})

def _secret(db,value):
    any_secret=db.execute('SELECT 1 FROM comms_channels WHERE credential IS NOT NULL LIMIT 1').fetchone()
    if not any_secret and 'mail_accounts' in tables(db):any_secret=db.execute('SELECT 1 FROM mail_accounts WHERE credential IS NOT NULL LIMIT 1').fetchone()
    vault.cipher(create=not bool(any_secret));return vault.seal(value)

def connect(kind,label,identity,remote_id,secret=None,generation='',path=p.DEFAULT_DB):
    if kind not in KINDS:raise ValueError('Unsupported channel')
    label=text(label,100,'Label',True);identity=text(identity,250,'Account identity',True);remote_id=text(remote_id,250,'Remote account ID',True)
    initialize(path);ident=uuid4().hex
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT * FROM comms_channels WHERE kind=? AND identity=?',(kind,identity)).fetchone()
        if old and old['remote_id']!=remote_id:raise ValueError('Account identity changed; create a distinct connection')
        encrypted=_secret(db,secret) if secret is not None else None
        if old:
            ident=old['id'];db.execute("UPDATE comms_channels SET credential=?,connected=1,enabled=0,ai_enabled=0,version=version+1,generation=?,last_error='' WHERE id=?",(encrypted,generation,ident))
            db.execute("UPDATE comms_runs SET status='cancelled',error='Connection rotated',version=version+1 WHERE status='queued' AND snapshot LIKE ?",('%'+ident+'%',))
        else:db.execute('INSERT INTO comms_channels(id,kind,label,identity,remote_id,credential,generation) VALUES(?,?,?,?,?,?,?)',(ident,kind,label,identity,remote_id,encrypted,generation))
        event(db,'channel_connected',{'channel_id':ident,'kind':kind,'identity':identity})
    return ident

def link_email(slot,path=p.DEFAULT_DB):
    from superhuman.mail import store as mail
    a=mail.account(slot,path)
    if not a['connected']:raise ValueError('Connect this email inbox with the existing mail setup first')
    return connect('email',a['label'],a['email'],slot,generation=a['generation'],path=path)

def control_channel(ident,expected,enabled,ai_enabled,disconnect=False,path=p.DEFAULT_DB):
    if type(enabled) is not bool or type(ai_enabled) is not bool:raise ValueError('Invalid channel controls')
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');a=db.execute('SELECT * FROM comms_channels WHERE id=?',(ident,)).fetchone()
        if not a or a['version']!=expected:raise ValueError('Channel changed; reload')
        if enabled and not a['connected']:raise ValueError('Reconnect the channel first')
        db.execute('UPDATE comms_channels SET enabled=?,ai_enabled=?,connected=?,credential=CASE WHEN ? THEN NULL ELSE credential END,version=version+1 WHERE id=?',(int(enabled and not disconnect),int(ai_enabled and not disconnect),0 if disconnect else a['connected'],int(disconnect),ident))
        event(db,'channel_disconnected' if disconnect else 'channel_controls',{'channel_id':ident,'read':enabled,'model_processing':ai_enabled})

def add_stream(ident,remote_id,label,path=p.DEFAULT_DB):
    a=channel(ident,path);remote_id=text(remote_id,40,'Slack conversation ID',True);label=text(label,100,'Conversation label',True)
    if a['kind']!='slack' or not re.fullmatch(r'[CDG][A-Z0-9]{5,39}',remote_id):raise ValueError('Use a Slack channel or DM conversation ID')
    key=digest([ident,remote_id,''])[:32]
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT COUNT(*) FROM comms_streams WHERE channel_id=? AND root=''",(ident,)).fetchone()[0]>=10 and not db.execute('SELECT 1 FROM comms_streams WHERE id=?',(key,)).fetchone():raise ValueError('Pilot supports up to 10 explicitly selected Slack conversations')
        db.execute('INSERT OR IGNORE INTO comms_streams(id,channel_id,remote_id,label) VALUES(?,?,?,?)',(key,ident,remote_id,label));event(db,'slack_conversation_allowed',{'channel_id':ident,'conversation_id':remote_id})
    return key

def control_stream(ident,expected,enabled,path=p.DEFAULT_DB):
    with p.connect(path) as db:
        cur=db.execute('UPDATE comms_streams SET enabled=?,version=version+1 WHERE id=? AND version=?',(int(enabled),ident,expected))
        if not cur.rowcount:raise ValueError('Conversation changed; reload')
        event(db,'conversation_control',{'stream_id':ident,'enabled':bool(enabled)})

def ingest(db,a,remote_id,thread,sender,subject,body,received,notice=''):
    remote_id=text(remote_id,350,'Remote message ID',True);thread=text(thread,250,'Thread');sender=text(sender,500,'Sender');subject=text(subject,500,'Subject');body=text(body,6000,'Body');notice=text(notice,500,'Coverage notice')
    if type(received) not in (float,int) or not 0<=received<=time.time()+86400:raise ValueError('Invalid received timestamp')
    fingerprint=digest([thread,sender,subject,body,received,notice]);old=db.execute('SELECT * FROM comms_sources WHERE channel_id=? AND remote_id=?',(a['id'],remote_id)).fetchone()
    if old:
        if old['digest']!=fingerprint:db.execute('UPDATE comms_sources SET thread=?,sender=?,subject=?,body=?,received=?,notice=?,digest=?,version=version+1 WHERE id=?',(thread,sender,subject,body,received,notice,fingerprint,old['id']))
        return old['id']
    if db.execute('SELECT COUNT(*) FROM comms_sources WHERE channel_id=? AND archived=0',(a['id'],)).fetchone()[0]>=2000:raise ValueError('Preview capacity reached; archive reviewed previews before continuing')
    ident=uuid4().hex;db.execute('INSERT INTO comms_sources(id,channel_id,remote_id,thread,sender,subject,body,received,notice,digest,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(ident,a['id'],remote_id,thread,sender,subject,body,float(received),notice,fingerprint,p.stamp()));return ident

def available(a,db):
    if not a['connected'] or not a['enabled']:return False
    if a['kind']=='email':
        if 'mail_accounts' not in tables(db):return False
        m=db.execute('SELECT * FROM mail_accounts WHERE id=?',(a['remote_id'],)).fetchone()
        return bool(m and m['credential'] and m['email']==a['identity'] and m['generation']==a['generation'])
    return bool(a['credential'])

def source_allowed(s,a,db):
    if s['archived'] or not available(a,db) or not a['ai_enabled']:return False
    if a['kind']=='slack':
        conversation=s['remote_id'].split(':',1)[0]
        return bool(db.execute("SELECT 1 FROM comms_streams WHERE channel_id=? AND remote_id=? AND root='' AND enabled=1",(a['id'],conversation)).fetchone())
    return True

def archive(ident,expected,path=p.DEFAULT_DB):
    with p.connect(path) as db:
        cur=db.execute('UPDATE comms_sources SET archived=1,version=version+1 WHERE id=? AND version=?',(ident,expected))
        if not cur.rowcount:raise ValueError('Preview changed; reload')
        event(db,'preview_archived',{'source_id':ident})

def acknowledge(ident,path=p.DEFAULT_DB):
    with p.connect(path) as db:db.execute("UPDATE comms_alerts SET state='acknowledged' WHERE id=?",(ident,));event(db,'alert_acknowledged',{'alert_id':ident})

def route(ident,expected,project_id,note,path=p.DEFAULT_DB):
    note=text(note,1500,'Owner sharing rationale',True)
    proposal=next((x for x in proposals(path) if x['id']==ident),None)
    if not proposal or proposal['version']!=expected or proposal['state']!='proposed':raise ValueError('Proposal changed; reload')
    s=source(proposal['source_id'],path);a=channel(s['channel_id'],path)
    if s['digest']!=proposal['source_digest'] or s['archived']:raise ValueError('Source changed; request a fresh analysis')
    project=team.project(project_id,path)
    if project['status']!='active' or project['sensitivity']!='restricted' or project['risk']=='routine':raise ValueError('Private intake needs an owner-approved restricted project with consequential or high-risk controls')
    from superhuman.team import work
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');cur=db.execute("UPDATE comms_proposals SET state='approved',version=version+1 WHERE id=? AND version=? AND state='proposed'",(ident,expected))
        if not cur.rowcount:raise ValueError('Proposal changed')
        current=db.execute('SELECT * FROM comms_sources WHERE id=?',(s['id'],)).fetchone();parent=db.execute('SELECT * FROM team_projects WHERE id=?',(project_id,)).fetchone()
        if current['digest']!=proposal['source_digest'] or current['archived'] or parent['version']!=project['version']:raise ValueError('Source or destination changed')
        instruction=proposal['instruction']+'\nPrivate communication reference: '+s['id']+'. Source claims are unverified. No external communication or public-web disclosure is authorized. Owner sharing note: '+note
        task=team.create_task(project_id,proposal['department'],proposal['title'],instruction[:5000],proposal['acceptance'],risk=project['risk'],sensitivity='restricted',actor='owner',path=path,_db=db)
        db.execute('UPDATE comms_proposals SET task_id=? WHERE id=?',(task,ident));event(db,'private_task_shared',{'proposal_id':ident,'task_id':task,'project_id':project_id,'owner_note':note})
    return task

def reject_proposal(ident,expected,path=p.DEFAULT_DB):
    with p.connect(path) as db:
        cur=db.execute("UPDATE comms_proposals SET state='rejected',version=version+1 WHERE id=? AND version=? AND state='proposed'",(ident,expected))
        if not cur.rowcount:raise ValueError('Proposal changed')
        event(db,'proposal_rejected',{'proposal_id':ident})

def edit_draft(ident,expected,body,path=p.DEFAULT_DB):
    body=text(body,4000,'Reply draft',True)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');d=db.execute('SELECT * FROM comms_drafts WHERE id=?',(ident,)).fetchone()
        if not d or d['version']!=expected:raise ValueError('Draft changed')
        s=db.execute('SELECT * FROM comms_sources WHERE id=?',(d['source_id'],)).fetchone()
        if s['digest']!=d['source_digest'] or s['archived']:raise ValueError('Source changed; review a fresh draft')
        db.execute('UPDATE comms_drafts SET body=?,state=\'owner_edited\',version=version+1 WHERE id=?',(body,ident));event(db,'reply_draft_edited',{'draft_id':ident})


def rescan_stream(ident,expected,note,path=p.DEFAULT_DB):
    note=text(note,1000,'Rescan inspection note',True)
    with p.connect(path) as db:
        cur=db.execute("UPDATE comms_streams SET cursor='',watermark='0',ceiling='',floor='',next_poll=0,version=version+1 WHERE id=? AND version=?",(ident,expected))
        if not cur.rowcount:raise ValueError('Conversation changed')
        event(db,'slack_rescan_authorized',{'stream_id':ident,'note':note})
