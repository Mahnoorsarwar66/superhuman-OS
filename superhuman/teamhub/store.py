"""Additive Team records. Existing conversations, tasks, source files and approvals remain authoritative."""
import hashlib,json,time
from uuid import uuid4
from superhuman.projects import engine as p
from superhuman.experience import store as ux
from superhuman.dialogue import store as d
from superhuman.team import store as team
from superhuman.milestones import store as ms
from superhuman.foundation import storage
from superhuman.departments.store import tables


def initialize(path=p.DEFAULT_DB):
    from superhuman.departments.store import readonly
    with readonly(path) as db:
        if {'hub_rooms','hub_channels','hub_card_reviews'}<=tables(db):return
    ux.initialize(path);ms.initialize(path);storage.initialize(path)
    with p.connect(path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS hub_rooms(id TEXT PRIMARY KEY,archived INTEGER NOT NULL DEFAULT 0,pinned INTEGER NOT NULL DEFAULT 0,seen TEXT NOT NULL DEFAULT '',note TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS hub_dm_threads(room_id TEXT PRIMARY KEY,parent_id TEXT NOT NULL,turn_id TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS hub_primary(employee TEXT PRIMARY KEY,room_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS hub_channels(id TEXT PRIMARY KEY,project_id TEXT NOT NULL UNIQUE,title TEXT NOT NULL,members TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,archived INTEGER NOT NULL DEFAULT 0,pinned INTEGER NOT NULL DEFAULT 0,max_calls INTEGER NOT NULL DEFAULT 40,delegated INTEGER NOT NULL DEFAULT 0,seen INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS hub_topics(id TEXT PRIMARY KEY,channel_id TEXT NOT NULL,title TEXT NOT NULL,milestone_id TEXT NOT NULL DEFAULT '',note TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS hub_rounds(id TEXT PRIMARY KEY,topic_id TEXT NOT NULL,submission_key TEXT NOT NULL UNIQUE,message TEXT NOT NULL,mode TEXT NOT NULL,target TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'queued',plan TEXT NOT NULL DEFAULT '[]',error TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS hub_steps(id TEXT PRIMARY KEY,round_id TEXT NOT NULL,ordinal INTEGER NOT NULL,employee TEXT NOT NULL,stage TEXT NOT NULL,turn_id TEXT NOT NULL UNIQUE,UNIQUE(round_id,ordinal));
        CREATE TABLE IF NOT EXISTS hub_links(target TEXT NOT NULL,item_id TEXT NOT NULL,item_version INTEGER NOT NULL,digest TEXT NOT NULL,PRIMARY KEY(target,item_id));
        CREATE TABLE IF NOT EXISTS hub_card_review_history(card_id TEXT NOT NULL,turn_id TEXT PRIMARY KEY,card_version INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS hub_card_reviews(card_id TEXT PRIMARY KEY,turn_id TEXT NOT NULL UNIQUE,card_version INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'pending');
        CREATE TABLE IF NOT EXISTS hub_cards(id TEXT PRIMARY KEY,suggestion_id TEXT NOT NULL UNIQUE,topic_id TEXT NOT NULL DEFAULT '',room_id TEXT NOT NULL,project_id TEXT NOT NULL,owner TEXT NOT NULL,title TEXT NOT NULL,instruction TEXT NOT NULL,criteria TEXT NOT NULL,due TEXT NOT NULL DEFAULT '',risk TEXT NOT NULL,sensitivity TEXT NOT NULL,milestone_id TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'proposed',task_id TEXT NOT NULL DEFAULT '',decision TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
        ''')
        # Establish a migration baseline; historical replies are not invented unread events.
        for row in db.execute('SELECT thread_id FROM ux_rooms').fetchall():
            history=[dict(x) for x in db.execute('SELECT id,status,finished_at FROM dialogue_turns WHERE thread_id=? ORDER BY ordinal',(row['thread_id'],))]
            seen=hashlib.sha256(json.dumps(history,sort_keys=True).encode()).hexdigest() if history else ''
            db.execute('INSERT OR IGNORE INTO hub_rooms(id,seen) VALUES(?,?)',(row['thread_id'],seen))

def read(sql,args=(),path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:return [dict(r) for r in db.execute(sql,args)]

def one(sql,args=(),path=p.DEFAULT_DB):
    rows=read(sql,args,path)
    if not rows:raise ValueError('Team item not found; return to Team and choose an existing item')
    return rows[0]

def state(rid,path=p.DEFAULT_DB):
    one('SELECT id FROM dialogue_threads WHERE id=?',(rid,),path)
    rows=read('SELECT * FROM hub_rooms WHERE id=?',(rid,),path)
    return rows[0] if rows else dict(id=rid,archived=0,pinned=0,seen='',note='',version=0)

def room_control(rid,expected,title,archived,pinned,note,path=p.DEFAULT_DB):
    title=d.text(title,180,'Conversation title');note=team.text(note,4000,'Confirmed context')
    initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');db.execute('INSERT OR IGNORE INTO hub_rooms(id) VALUES(?)',(rid,))
        row=db.execute('SELECT * FROM hub_rooms WHERE id=?',(rid,)).fetchone()
        if row['version']!=(expected or 1):raise ValueError('Conversation changed; reload before saving')
        if archived and db.execute("SELECT 1 FROM dialogue_turns WHERE thread_id=? AND status IN ('queued','running')",(rid,)).fetchone():raise ValueError('Finish or cancel the pending reply before archiving')
        if not db.execute('UPDATE dialogue_threads SET title=?,updated_at=? WHERE id=?',(title,p.stamp(),rid)).rowcount:raise ValueError('Conversation unavailable')
        db.execute('UPDATE hub_rooms SET archived=?,pinned=?,note=?,version=version+1 WHERE id=?',(bool(archived),bool(pinned),note,rid))
        team.event(db,'owner','team_conversation_organized',{'room_id':rid,'archived':bool(archived),'pinned':bool(pinned),'note_changed':row['note']!=note})

def mark_room(rid,signature,path=p.DEFAULT_DB):
    # POST with an exact visible signature prevents a simultaneous reply being marked read unseen.
    current=room_signature(rid,path)
    if signature!=current:raise ValueError('New messages arrived; review them before marking read')
    with p.connect(path) as db:
        db.execute('INSERT OR IGNORE INTO hub_rooms(id) VALUES(?)',(rid,));db.execute('UPDATE hub_rooms SET seen=? WHERE id=?',(signature,rid))

def room_signature(rid,path=p.DEFAULT_DB):
    rows=read("SELECT id,status,finished_at FROM dialogue_turns WHERE thread_id=? ORDER BY ordinal",(rid,),path)
    from superhuman.conversationwork.bridge import signature as work_signature
    return hashlib.sha256((json.dumps(rows,sort_keys=True)+work_signature(rid,path)).encode()).hexdigest() if rows else ''

def primary(employee,path=p.DEFAULT_DB):
    if employee not in ux.NAMES:raise ValueError('Choose an employee')
    initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT room_id FROM hub_primary WHERE employee=?',(employee,)).fetchone()
        if row:
            db.execute('UPDATE hub_rooms SET archived=0 WHERE id=?',(row['room_id'],));return row['room_id']
        existing=db.execute("SELECT d.id FROM ux_rooms r JOIN dialogue_threads d ON d.id=r.thread_id LEFT JOIN hub_rooms h ON h.id=d.id WHERE r.employee=? AND r.project_id='' AND COALESCE(h.archived,0)=0 ORDER BY d.updated_at DESC LIMIT 1",(employee,)).fetchone()
        rid=existing['id'] if existing else uuid4().hex
        if not existing:
            scope='endorsement' if employee=='twin' else employee
            db.execute('INSERT INTO dialogue_threads VALUES(?,?,?,20,0,?,?)',(rid,scope,'Talk with '+ux.NAMES[employee],p.stamp(),p.stamp()))
            db.execute('INSERT INTO ux_rooms VALUES(?,?,?,?,1)',(rid,employee,'',''))
        db.execute('INSERT INTO hub_primary VALUES(?,?)',(employee,rid));team.event(db,'owner','primary_conversation_selected',{'employee':employee,'room_id':rid})
    return rid

def rooms(q='',employee='',project_id='',archived=False,page=1,day_from='',day_to='',path=p.DEFAULT_DB):
    if employee and employee not in ux.NAMES or len(q)>200 or not 1<=page<=10000:raise ValueError('Invalid conversation filter')
    from datetime import date
    for value in (day_from,day_to):
        if value:date.fromisoformat(value)
    if day_from and day_to and day_from>day_to:raise ValueError('Start date must precede end date')
    sql='''SELECT d.*,r.employee,r.project_id,r.project_kind,COALESCE(h.pinned,0) AS pinned,COALESCE(h.seen,'') AS seen FROM dialogue_threads d JOIN ux_rooms r ON r.thread_id=d.id LEFT JOIN hub_rooms h ON h.id=d.id WHERE COALESCE(h.archived,0)=? AND NOT EXISTS(SELECT 1 FROM hub_steps s JOIN dialogue_turns t ON t.id=s.turn_id WHERE t.thread_id=d.id)''';args=[int(archived)]
    for name,value in [('r.employee',employee),('r.project_id',project_id)]:
        if value:sql+=' AND '+name+'=?';args.append(value)
    if q:sql+=' AND (instr(lower(d.title),lower(?))>0 OR EXISTS(SELECT 1 FROM dialogue_turns t WHERE t.thread_id=d.id AND (instr(lower(t.user_text),lower(?))>0 OR instr(lower(COALESCE(t.reply,\'\')),lower(?))>0)))';args.extend([q,q,q])
    if day_from:sql+=' AND substr(d.updated_at,1,10)>=?';args.append(day_from)
    if day_to:sql+=' AND substr(d.updated_at,1,10)<=?';args.append(day_to)
    sql+=' ORDER BY pinned DESC,d.updated_at DESC,d.id LIMIT 31 OFFSET ?';args.append((page-1)*30)
    return read(sql,tuple(args),path)

def channel(ident,path=p.DEFAULT_DB):return one('SELECT * FROM hub_channels WHERE id=?',(ident,),path)
def topic(ident,path=p.DEFAULT_DB):return one('SELECT * FROM hub_topics WHERE id=?',(ident,),path)
def round_(ident,path=p.DEFAULT_DB):return one('SELECT * FROM hub_rounds WHERE id=?',(ident,),path)
def steps(ident,path=p.DEFAULT_DB):return read('''SELECT s.*,t.thread_id,t.user_text,t.status,t.reply,t.error,t.created_at,t.finished_at FROM hub_steps s JOIN dialogue_turns t ON t.id=s.turn_id WHERE s.round_id=? ORDER BY s.ordinal''',(ident,),path)

def channel_members(c,path=p.DEFAULT_DB):
    cfg=ms.managed(c['project_id'],path)
    if not cfg or not cfg['share_outputs']:raise ValueError('Enable the existing project-team sharing agreement before shared discussions')
    current=set(ms.roster(c['project_id'],path));members=json.loads(c['members'])
    if not set(members)<=current or cfg['lead'] not in members:raise ValueError('Project roster changed. Review channel membership before continuing')
    return members

def create_channel(pid,title,members,path=p.DEFAULT_DB):
    initialize(path);cfg=ms.managed(pid,path)
    if not cfg or not cfg['share_outputs']:raise ValueError('Set up project leadership and approve project-team sharing first')
    members=sorted(set(members));approved=ms.roster(pid,path)
    if cfg['lead'] not in members or set(members)-set(approved):raise ValueError('Include the project lead and choose only approved project participants')
    title=d.text(title,180,'Channel title');ident=uuid4().hex
    with p.connect(path) as db:
        try:db.execute('INSERT INTO hub_channels(id,project_id,title,members,created_at) VALUES(?,?,?,?,?)',(ident,pid,title,json.dumps(members),p.stamp()))
        except __import__('sqlite3').IntegrityError:raise ValueError('This project already has a channel; open it from Team') from None
        team.event(db,'owner','project_channel_created',{'channel_id':ident,'project_id':pid,'members':members})
    return ident

def channel_control(ident,expected,title,members,archived,pinned,maximum,path=p.DEFAULT_DB,delegated=False):
    c=channel(ident,path);cfg=ms.managed(c['project_id'],path)
    if not cfg or cfg['lead'] not in members or set(members)-set(ms.roster(c['project_id'],path)):raise ValueError('Choose the lead and approved project members')
    used=one('SELECT COUNT(*) AS n FROM hub_steps s JOIN hub_rounds r ON r.id=s.round_id JOIN hub_topics t ON t.id=r.topic_id WHERE t.channel_id=?',(ident,),path)['n']
    if not used<=maximum<=500:raise ValueError('Channel allowance must cover existing attempts and be at most 500')
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT 1 FROM hub_rounds r JOIN hub_topics t ON t.id=r.topic_id WHERE t.channel_id=? AND r.status IN ('queued','working')",(ident,)).fetchone():raise ValueError('Finish or cancel active discussions before changing membership or archiving')
        if not db.execute('UPDATE hub_channels SET title=?,members=?,archived=?,pinned=?,max_calls=?,delegated=?,version=version+1 WHERE id=? AND version=?',(d.text(title,180,'Title'),json.dumps(sorted(set(members))),bool(archived),bool(pinned),maximum,bool(delegated),ident,expected)).rowcount:raise ValueError('Channel changed; reload')
        team.event(db,'owner','project_channel_updated',{'channel_id':ident,'members':members,'maximum':maximum,'delegated_card_review':bool(delegated)})

def create_topic(cid,title,milestone_id='',path=p.DEFAULT_DB):
    c=channel(cid,path);channel_members(c,path)
    if c['archived']:raise ValueError('Restore this channel before posting')
    if milestone_id and ms.milestone(milestone_id,path)['project_id']!=c['project_id']:raise ValueError('Choose a milestone in this project')
    ident=uuid4().hex
    with p.connect(path) as db:db.execute('INSERT INTO hub_topics(id,channel_id,title,milestone_id,created_at) VALUES(?,?,?,?,?)',(ident,cid,d.text(title,180,'Topic title'),milestone_id,p.stamp()))
    return ident

def send(tid,message,mode,target,key,path=p.DEFAULT_DB):
    t=topic(tid,path);c=channel(t['channel_id'],path);members=channel_members(c,path)
    if c['archived']:raise ValueError('Restore the channel before posting')
    if mode not in ('direct','team') or mode=='direct' and target not in members:raise ValueError('Choose a channel participant')
    if not 16<=len(key)<=80:raise ValueError('Reload the message form')
    message=d.text(message,6000,'Message');ident=uuid4().hex
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT * FROM hub_rounds WHERE submission_key=?',(key,)).fetchone()
        if old:
            if (old['topic_id'],old['message'],old['mode'],old['target'])!=(tid,message,mode,target):raise ValueError('Message key was used with different content')
            return old['id']
        from .readiness import require
        require(c['id'],target if mode=='direct' else 'team',path,db=db)
        if db.execute("SELECT 1 FROM hub_rounds WHERE topic_id=? AND status IN ('queued','working')",(tid,)).fetchone():raise ValueError('Wait for or cancel the current discussion first')
        db.execute('INSERT INTO hub_rounds(id,topic_id,submission_key,message,mode,target,created_at) VALUES(?,?,?,?,?,?,?)',(ident,tid,key,message,mode,target,p.stamp()))
        team.event(db,'owner','channel_message_queued',{'round_id':ident,'topic_id':tid,'mode':mode,'target':target})
    return ident

def cancel(ident,path=p.DEFAULT_DB):
    r=round_(ident,path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        if r['status'] not in ('queued','working'):raise ValueError('This discussion is already stopped')
        if db.execute("SELECT 1 FROM hub_steps s JOIN dialogue_turns t ON t.id=s.turn_id WHERE s.round_id=? AND t.status='running'",(ident,)).fetchone():raise ValueError('The current request is running and may be billed; wait for it to finish')
        db.execute("UPDATE dialogue_turns SET status='cancelled',finished_at=? WHERE id IN (SELECT turn_id FROM hub_steps WHERE round_id=?) AND status='queued'",(p.stamp(),ident))
        db.execute("UPDATE hub_rounds SET status='cancelled',version=version+1 WHERE id=?",(ident,))

def save_note(tid,expected,note,path=p.DEFAULT_DB):
    with p.connect(path) as db:
        if not db.execute('UPDATE hub_topics SET note=?,version=version+1 WHERE id=? AND version=?',(team.text(note,4000,'Confirmed context'),tid,expected)).rowcount:raise ValueError('Topic context changed; reload')
        team.event(db,'owner','topic_context_confirmed',{'topic_id':tid})

def link_file(target,item_id,path=p.DEFAULT_DB):
    item=storage.get(item_id,path)
    is_topic=read('SELECT * FROM hub_topics WHERE id=?',(target,),path)
    if is_topic:
        c=channel(is_topic[0]['channel_id'],path);members=channel_members(c,path);pid=c['project_id'];maximum=team.project(pid,path)['sensitivity'];kind='team'
    else:
        r=ux.room(target,path)
        if not r:raise ValueError('Conversation not found')
        members=[r['employee']];pid=r['project_id'];kind=r['project_kind'];maximum=ux.project(kind,pid,path).get('sensitivity','internal') if pid else ('restricted' if r['employee']=='twin' else 'confidential')
    if item['project_id'] and (item['project_id']!=pid or item['project_kind']!=kind):raise ValueError('This document belongs to another project')
    if storage.health(item)!='Current' or not all(storage.allowed(item,e,pid,maximum,path) for e in members):raise ValueError('Approve a current version in Storage for every participant within the project sensitivity first')
    with p.connect(path) as db:db.execute('INSERT OR REPLACE INTO hub_links VALUES(?,?,?,?)',(target,item_id,item['version'],item['digest']));team.event(db,'owner','conversation_document_linked',{'target':target,'item_id':item_id,'version':item['version']})

def document_context(target,employee,pid,maximum,path=p.DEFAULT_DB):
    result=[]
    for link in read('SELECT * FROM hub_links WHERE target=? ORDER BY item_id LIMIT 8',(target,),path):
        item=storage.get(link['item_id'],path)
        if item['version']!=link['item_version'] or item['digest']!=link['digest'] or storage.health(item)!='Current' or not storage.allowed(item,employee,pid,maximum,path):raise ValueError('A linked document changed or access was revoked. Review its Storage version and relink or remove it')
        if item['kind']=='fact':excerpt=item['content'][:2500]
        else:
            from superhuman.capabilities import local
            excerpt=local.extract(item['scope'],item['filename'])['text'][:2500]
        result.append(dict(id=item['id'],version=item['version'],title=item['title'],digest=item['digest'],excerpt=excerpt,limited=True))
    return result

def events(pid,path=p.DEFAULT_DB):
    # One source-backed stream: never synthesise dialogue from an execution log.
    req=read('SELECT r.*,t.title,t.owner FROM team_requests r JOIN team_tasks t ON t.id=r.task_id WHERE t.project_id=? ORDER BY r.created_at DESC LIMIT 100',(pid,),path)
    tasks=team.tasks(path);tasks=[t for t in tasks if t['project_id']==pid]
    return req,tasks


def topic_search(q='',employee='',project_id='',archived=False,day_from='',day_to='',page=1,path=p.DEFAULT_DB):
    if len(q)>200 or employee and employee not in ux.NAMES or not 1<=page<=10000:raise ValueError('Invalid topic search')
    sql="""SELECT DISTINCT t.*,c.title AS channel_title,c.project_id FROM hub_topics t JOIN hub_channels c ON c.id=t.channel_id WHERE c.archived=?""";args=[int(archived)]
    if project_id:sql+=' AND c.project_id=?';args.append(project_id)
    if q:
        sql+=""" AND (instr(lower(t.title),lower(?))>0 OR EXISTS(SELECT 1 FROM hub_rounds r LEFT JOIN hub_steps s ON s.round_id=r.id LEFT JOIN dialogue_turns d ON d.id=s.turn_id WHERE r.topic_id=t.id AND (instr(lower(r.message),lower(?))>0 OR instr(lower(COALESCE(d.reply,'')),lower(?))>0)))""";args.extend([q,q,q])
    if employee:sql+=' AND EXISTS(SELECT 1 FROM hub_rounds r JOIN hub_steps s ON s.round_id=r.id WHERE r.topic_id=t.id AND s.employee=?)';args.append(employee)
    if day_from:sql+=' AND substr(t.created_at,1,10)>=?';args.append(day_from)
    if day_to:sql+=' AND substr(t.created_at,1,10)<=?';args.append(day_to)
    sql+=' ORDER BY t.created_at DESC,t.id LIMIT 31 OFFSET ?';args.append((page-1)*30)
    return read(sql,tuple(args),path)


def reply_thread(parent_id,turn_id,title,path=p.DEFAULT_DB):
    r=ux.room(parent_id,path);turn=d.turn(turn_id,path)
    if not r or turn['thread_id']!=parent_id or turn['status']!='done':raise ValueError('Choose a completed message in this conversation')
    if state(parent_id,path)['archived']:raise ValueError('Restore the parent conversation before starting a thread')
    existing=read('SELECT room_id FROM hub_dm_threads WHERE parent_id=? AND turn_id=? ORDER BY created_at LIMIT 1',(parent_id,turn_id),path)
    if existing:return existing[0]['room_id']
    # Same employee and explicit project association; no cross-project history copying.
    rid=ux.create(r['employee'],title,r['project_kind'],r['project_id'],path)
    with p.connect(path) as db:
        db.execute('INSERT INTO hub_dm_threads VALUES(?,?,?,?)',(rid,parent_id,turn_id,p.stamp()))
        team.event(db,'owner','conversation_reply_thread_created',{'room_id':rid,'parent_id':parent_id,'turn_id':turn_id})
    return rid
