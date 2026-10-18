"""Local, owner-reviewed meetings. Email suggestions never alter confirmed events."""
from datetime import datetime,timezone,timedelta
import hashlib
import json
import re
from uuid import uuid4
from superhuman.projects import engine as p
from superhuman.mail import store as mail
from superhuman.briefing import engine as briefing

UTC=timezone.utc
PKT=briefing.PKT


def initialize(path=p.DEFAULT_DB):
    mail.initialize(path)
    with p.connect(path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS calendar_events(
          id TEXT PRIMARY KEY,title TEXT NOT NULL,start_at TEXT NOT NULL,end_at TEXT NOT NULL,
          notes TEXT NOT NULL,status TEXT NOT NULL,version INTEGER NOT NULL,
          created_at TEXT NOT NULL,updated_at TEXT NOT NULL,submission_key TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS calendar_candidates(
          id TEXT PRIMARY KEY,report_id TEXT NOT NULL,item_index INTEGER NOT NULL,
          title TEXT NOT NULL,start_at TEXT NOT NULL,notes TEXT NOT NULL,sources_json TEXT NOT NULL,
          status TEXT NOT NULL,event_id TEXT,created_at TEXT NOT NULL,decided_at TEXT,
          UNIQUE(report_id,item_index));
        CREATE TABLE IF NOT EXISTS calendar_scanned(
          report_id TEXT PRIMARY KEY,scanned_at TEXT NOT NULL,added INTEGER NOT NULL,ignored INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS calendar_sources(
          candidate_id TEXT PRIMARY KEY,event_id TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS calendar_event_time ON calendar_events(status,start_at);
        ''')


def text(value,limit,label,required=True):
    if not isinstance(value,str):raise ValueError(label+' must be text')
    value=value.strip()
    if (required and not value) or len(value)>limit or any(ord(c)<32 and c not in '\n\t\r' for c in value):
        raise ValueError(label+' is missing, too long or contains invalid characters')
    return value


def instant(value,local=False):
    if not isinstance(value,str):raise ValueError('Enter a valid meeting date and time')
    try:
        result=datetime.fromisoformat(value.strip().replace('Z','+00:00'))
        if result.tzinfo is None:
            if not local:raise ValueError('Meeting time must include a timezone')
            result=result.replace(tzinfo=PKT)
        return result.astimezone(UTC).isoformat(timespec='seconds')
    except (ValueError,OverflowError) as exc:raise ValueError('Enter a valid meeting date and time with the correct timezone') from exc


def fields(title,start_at,end_at='',notes='',local=False):
    title=text(title,180,'Meeting title');notes=text(notes,4000,'Notes',False)
    start=instant(start_at,local);end=instant(end_at,local) if end_at else ''
    if end and end<=start:raise ValueError('End time must be later than start time')
    return title,start,end,notes


def get(key,path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:row=db.execute('SELECT * FROM calendar_events WHERE id=?',(key,)).fetchone()
    if row is None:raise ValueError('Meeting not found')
    return dict(row)


def candidate(key,path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:row=db.execute('SELECT c.*,m.thread_id,m.account_id FROM calendar_candidates c JOIN mail_reports m ON m.id=c.report_id WHERE c.id=?',(key,)).fetchone()
    if row is None:raise ValueError('Meeting suggestion not found')
    return dict(row)


def collect(path=p.DEFAULT_DB):
    """Index at most 100 completed reports. No reanalysis, network or model calls."""
    initialize(path);added=ignored=0
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        rows=db.execute("""SELECT m.id,m.snapshot,t.context_json FROM mail_reports m
            JOIN dialogue_turns t ON t.id=m.turn_id LEFT JOIN calendar_scanned s ON s.report_id=m.id
            WHERE t.status='done' AND s.report_id IS NULL ORDER BY m.created_at,m.id LIMIT 100""").fetchall()
        for row in rows:
            found=missed=0
            try:
                data=json.loads(row['context_json'] or '{}');snapshot=json.loads(row['snapshot'])
                items=data.get('briefing',{}).get('items',[])
                if not isinstance(items,list) or len(items)>6:raise ValueError('Invalid report')
                allowed={'E'+str(i+1) for i in range(min(12,len(snapshot.get('messages',[]))))}
            except (ValueError,TypeError,AttributeError):items=[];allowed=set();missed=1
            for index,item in enumerate(items):
                # Only the explicit meeting_at field qualifies; deadlines never do.
                if not isinstance(item,dict) or not item.get('meeting_at'):continue
                try:
                    title=text(briefing.scrub(item.get('headline') or item.get('headline_full','')),180,'Meeting title')
                    start=instant(item['meeting_at']);sources=briefing.refs(item.get('sources'),allowed)
                    notes=text(briefing.scrub(item.get('reason_full') or item.get('reason','')),4000,'Notes',False)
                except (ValueError,TypeError):missed+=1;continue
                key=hashlib.sha256((row['id']+':'+str(index)).encode()).hexdigest()[:32]
                db.execute("INSERT INTO calendar_candidates VALUES(?,?,?,?,?,?,?,'proposed',NULL,?,NULL)",
                    (key,row['id'],index,title,start,notes,json.dumps(sources),p.stamp()))
                found+=1
            db.execute('INSERT INTO calendar_scanned VALUES(?,?,?,?)',(row['id'],p.stamp(),found,missed))
            added+=found;ignored+=missed
        remaining=db.execute("SELECT COUNT(*) FROM mail_reports m JOIN dialogue_turns t ON t.id=m.turn_id LEFT JOIN calendar_scanned s ON s.report_id=m.id WHERE t.status='done' AND s.report_id IS NULL").fetchone()[0]
    return dict(reports=len(rows),added=added,unusable=ignored,remaining=remaining)


def candidates(page=1,path=p.DEFAULT_DB):
    if type(page) is not int or not 1<=page<=10000:raise ValueError('Invalid page')
    initialize(path)
    with p.connect(path) as db:
        return [dict(r) for r in db.execute("SELECT c.*,m.account_id FROM calendar_candidates c JOIN mail_reports m ON m.id=c.report_id WHERE c.status='proposed' ORDER BY c.start_at DESC,c.id LIMIT 50 OFFSET ?",((page-1)*50,))]


def events(view='upcoming',page=1,path=p.DEFAULT_DB,now=None):
    if view not in ('upcoming','past','cancelled') or type(page) is not int or not 1<=page<=10000:raise ValueError('Invalid calendar page')
    initialize(path);at=(now or datetime.now(UTC)).astimezone(UTC).isoformat(timespec='seconds')
    condition={'upcoming':"status='confirmed' AND (start_at>=? OR (end_at!='' AND end_at>?))",'past':"status='confirmed' AND start_at<? AND (end_at='' OR end_at<=?)",'cancelled':"status='cancelled'"}[view]
    args=[at,at] if view!='cancelled' else []
    order='ASC' if view=='upcoming' else 'DESC'
    with p.connect(path) as db:return [dict(r) for r in db.execute('SELECT * FROM calendar_events WHERE '+condition+' ORDER BY start_at '+order+',id LIMIT 50 OFFSET ?',(*args,(page-1)*50))]


def tomorrow(path=p.DEFAULT_DB,now=None):
    initialize(path);day=(now or datetime.now(UTC)).astimezone(PKT).date()+timedelta(days=1)
    lower=datetime.combine(day,datetime.min.time(),PKT).astimezone(UTC).isoformat(timespec='seconds')
    upper=(datetime.combine(day,datetime.min.time(),PKT)+timedelta(days=1)).astimezone(UTC).isoformat(timespec='seconds')
    with p.connect(path) as db:return [dict(r) for r in db.execute("SELECT * FROM calendar_events WHERE status='confirmed' AND start_at>=? AND start_at<? ORDER BY start_at,id LIMIT 100",(lower,upper))]


def conflicts(start_at,exclude=None,path=p.DEFAULT_DB):
    initialize(path);at=datetime.fromisoformat(instant(start_at));low=(at-timedelta(minutes=15)).isoformat(timespec='seconds');high=(at+timedelta(minutes=15)).isoformat(timespec='seconds')
    with p.connect(path) as db:
        return [dict(r) for r in db.execute("SELECT * FROM calendar_events WHERE status='confirmed' AND start_at BETWEEN ? AND ? AND id!=? ORDER BY start_at,id LIMIT 10",(low,high,exclude or ''))]


def similar_candidates(key,path=p.DEFAULT_DB):
    row=candidate(key,path);at=datetime.fromisoformat(row['start_at'])
    with p.connect(path) as db:return [dict(r) for r in db.execute("SELECT * FROM calendar_candidates WHERE status='proposed' AND id!=? AND start_at BETWEEN ? AND ? ORDER BY start_at,id LIMIT 10",(key,(at-timedelta(minutes=15)).isoformat(timespec='seconds'),(at+timedelta(minutes=15)).isoformat(timespec='seconds')))]


def create(title,start_at,end_at,notes,submission_key,path=p.DEFAULT_DB):
    values=fields(title,start_at,end_at,notes)
    if not isinstance(submission_key,str) or not re.fullmatch('[a-f0-9]{32}',submission_key):raise ValueError('Reload the meeting form')
    initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT * FROM calendar_events WHERE submission_key=?',(submission_key,)).fetchone()
        if old:
            if tuple(old[k] for k in ('title','start_at','end_at','notes'))!=values:raise ValueError('This form was already submitted with different details')
            return old['id']
        key=uuid4().hex;now=p.stamp()
        db.execute("INSERT INTO calendar_events VALUES(?,?,?,?,?,'confirmed',1,?,?,?)",(key,*values,now,now,submission_key))
    return key


def confirm(key,title,start_at,end_at,notes,path=p.DEFAULT_DB):
    values=fields(title,start_at,end_at,notes);initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM calendar_candidates WHERE id=?',(key,)).fetchone()
        if row is None:raise ValueError('Meeting suggestion not found')
        if row['status']=='confirmed':
            event=db.execute('SELECT * FROM calendar_events WHERE id=?',(row['event_id'],)).fetchone()
            if event and event['status']=='confirmed' and tuple(event[k] for k in ('title','start_at','end_at','notes'))==values:return event['id']
            raise ValueError('Already handled. Open the existing meeting to edit it.')
        if row['status']!='proposed':raise ValueError('Suggestion no longer awaiting review')
        event_id=uuid4().hex;now=p.stamp()
        db.execute("INSERT INTO calendar_events VALUES(?,?,?,?,?,'confirmed',1,?,?,NULL)",(event_id,*values,now,now))
        db.execute('INSERT INTO calendar_sources VALUES(?,?)',(key,event_id))
        db.execute("UPDATE calendar_candidates SET status='confirmed',event_id=?,decided_at=? WHERE id=?",(event_id,now,key))
    return event_id


def link(key,event_id,expected_version,path=p.DEFAULT_DB):
    """Owner explicitly identifies a duplicate; preserve the existing event fields."""
    initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM calendar_candidates WHERE id=?',(key,)).fetchone()
        event=db.execute('SELECT * FROM calendar_events WHERE id=?',(event_id,)).fetchone()
        if row is None or event is None or event['status']!='confirmed':raise ValueError('Suggestion or active meeting unavailable')
        if row['status']=='confirmed' and row['event_id']==event_id:return event_id
        if row['status']!='proposed' or event['version']!=expected_version:raise ValueError('Meeting or suggestion changed. Reload before linking.')
        db.execute('INSERT INTO calendar_sources VALUES(?,?)',(key,event_id))
        db.execute("UPDATE calendar_candidates SET status='confirmed',event_id=?,decided_at=? WHERE id=?",(event_id,p.stamp(),key))
    return event_id


def dismiss(key,path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT status FROM calendar_candidates WHERE id=?',(key,)).fetchone()
        if row is None or row['status']=='confirmed':raise ValueError('Suggestion unavailable or already confirmed')
        db.execute("UPDATE calendar_candidates SET status='dismissed',decided_at=? WHERE id=?",(p.stamp(),key))


def update(key,version,title,start_at,end_at,notes,status,path=p.DEFAULT_DB):
    values=fields(title,start_at,end_at,notes)
    if status not in ('confirmed','cancelled'):raise ValueError('Choose confirmed or cancelled')
    initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        changed=db.execute('UPDATE calendar_events SET title=?,start_at=?,end_at=?,notes=?,status=?,version=version+1,updated_at=? WHERE id=? AND version=?',(*values,status,p.stamp(),key,version))
        if not changed.rowcount:raise ValueError('Meeting changed or unavailable. Reload before saving.')


def sources(event_id,path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:return [dict(r) for r in db.execute('SELECT c.* FROM calendar_sources s JOIN calendar_candidates c ON c.id=s.candidate_id WHERE s.event_id=? ORDER BY c.created_at,c.id',(event_id,))]
