"""Pakistan calendar, explicit source zones and owner-confirmed intake."""
from datetime import datetime,date,timedelta,timezone
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
import hashlib,re
from uuid import uuid4
from superhuman.projects import engine as p
from superhuman.calendar import store as cal
from . import store
PKT=ZoneInfo('Asia/Karachi');UTC=timezone.utc

def zoned(value,zone='',fold=''):
    value=value.strip()
    try:dt=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:raise ValueError('Use an explicit YYYY-MM-DD HH:MM date and time') from None
    if dt.tzinfo is not None:return dt.astimezone(UTC).isoformat(timespec='seconds')
    if not zone:raise ValueError('Confirm the original timezone; a timezone cannot be guessed')
    aliases={'UTC':'UTC','GMT':'UTC','PKT':'Asia/Karachi','ET':'America/New_York','PT':'America/Los_Angeles','EST':'America/New_York','EDT':'America/New_York','PST':'America/Los_Angeles','PDT':'America/Los_Angeles'}
    if zone.upper() in ('IST','CST','BST'):raise ValueError('Ambiguous abbreviation; choose an IANA timezone such as Asia/Kolkata')
    try:tz=ZoneInfo(aliases.get(zone.upper(),zone))
    except (ZoneInfoNotFoundError,ValueError):raise ValueError('Choose an installed IANA timezone or explicit UTC offset') from None
    valid=[]
    for f in (0,1):
        candidate=dt.replace(tzinfo=tz,fold=f)
        if candidate.astimezone(UTC).astimezone(tz).replace(tzinfo=None)==dt and candidate.utcoffset() not in [x.utcoffset() for x in valid]:valid.append(candidate)
    if not valid:raise ValueError('This local time does not exist during the daylight-saving transition')
    if len(valid)>1:
        if str(fold) not in ('0','1'):raise ValueError('This time occurs twice; choose the first or second occurrence')
        result=dt.replace(tzinfo=tz,fold=int(fold))
    else:result=valid[0]
    if zone.upper() in ('PST','PDT','EST','EDT') and result.tzname()!=zone.upper():raise ValueError('Abbreviation conflicts with daylight saving on this date; use an explicit offset or IANA zone')
    return result.astimezone(UTC).isoformat(timespec='seconds')

def local(value):return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(PKT)

def extract(text):
    """Recognise explicit ISO dates near meeting intent; uncertain text stays editable."""
    if not re.search(r'\b(meeting|call|webinar|interview|appointment|invitation|DTSTART)\b',text,re.I):return []
    found=[]
    for m in re.finditer(r'\b(20\d\d-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?)(?:\s+(UTC|GMT|PKT|PST|PDT|EST|EDT|ET|PT|IST|CST|BST|[A-Za-z_]+/[A-Za-z_]+))?',text):
        raw=m.group(1);zone=m.group(2) or ''
        try:start=zoned(raw,zone)
        except ValueError:start=''
        found.append((raw,zone,start,''))
    # Unfold iCalendar lines; support TZID/UTC instants, no recurrence expansion.
    unfolded=re.sub(r'\r?\n[ \t]','',text)
    for event in re.findall(r'BEGIN:VEVENT\s*(.*?)END:VEVENT',unfolded,re.S|re.I):
        m=re.search(r'^DTSTART(?:;TZID=([^;:\r\n]+))?:(\d{8}T\d{6}Z?)\s*$',event,re.M)
        if not m:continue
        try:raw=datetime.strptime(m.group(2).rstrip('Z'),'%Y%m%dT%H%M%S').isoformat()
        except ValueError:continue
        zone=m.group(1) or ('UTC' if m.group(2).endswith('Z') else '')
        if 'RRULE' in event:zone=zone # Each occurrence still needs owner confirmation; never expand recurrence.
        try:start=zoned(raw,zone)
        except ValueError:start=''
        end='';em=re.search(r'^DTEND(?:;TZID=([^;:\r\n]+))?:(\d{8}T\d{6}Z?)\s*$',event,re.M)
        if em:
            try:
                eraw=datetime.strptime(em.group(2).rstrip('Z'),'%Y%m%dT%H%M%S').isoformat()
                end=zoned(eraw,em.group(1) or ('UTC' if em.group(2).endswith('Z') else zone))
            except ValueError:pass
        found.append((raw,zone,start,end))
    return list(dict.fromkeys(found))[:20]

def collect(path=p.DEFAULT_DB):
    store.initialize(path);cal.initialize(path);added=0
    from .inbox import messages
    for message in messages(path,limit=1000):
        content=message['subject']+'\n'+message['body']
        for original,zone,start,end in extract(content):
            digest=hashlib.sha256(content.encode()).hexdigest();ident=hashlib.sha256((message['id']+digest+original+zone).encode()).hexdigest()[:32]
            with p.connect(path) as db:
                cur=db.execute('INSERT OR IGNORE INTO ux_meetings(id,source_id,source_digest,title,original,zone,start_at,end_at,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(ident,message['id'],digest,message['subject'][:180] or 'Meeting invitation',original,zone,start,end,p.stamp()));added+=cur.rowcount
    return added

def confirm(ident,title,original,zone,end='',fold='',path=p.DEFAULT_DB):
    store.initialize(path);cal.initialize(path)
    start=zoned(original,zone,fold);finish=zoned(end,zone,fold) if end else ''
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM ux_meetings WHERE id=?',(ident,)).fetchone()
        if not row:raise ValueError('Meeting suggestion not found')
        if row['status']=='confirmed':return row['event_id']
        if row['status']!='proposed':raise ValueError('Meeting suggestion is no longer proposed')
        # Detect changed source previews; confirmation never silently imports an old invitation.
        if row['source_id']:
            from .inbox import messages
            source=next((m for m in messages(path,limit=5000) if m['id']==row['source_id']),None)
            if not source or hashlib.sha256((source['subject']+'\n'+source['body']).encode()).hexdigest()!=row['source_digest']:raise ValueError('Invitation source changed or is unavailable; collect and review again')
        values=cal.fields(title,start,finish,'Original: '+original+' '+zone+'\nSource: '+row['source_id']+'\nImported occurrence only; recurring invitations require individual review.')
        eid=uuid4().hex;now=p.stamp()
        db.execute("INSERT INTO calendar_events VALUES(?,?,?,?,?,'confirmed',1,?,?,?)",(eid,*values,now,now,ident))
        db.execute("UPDATE ux_meetings SET status='confirmed',event_id=?,original=?,zone=?,start_at=?,end_at=? WHERE id=?",(eid,original,zone,start,finish,ident))
        return eid

def span(view,day):
    if view=='month':
        first=day.replace(day=1);start=first-timedelta(days=first.weekday());return start,start+timedelta(days=42)
    if view=='week':
        start=day-timedelta(days=day.weekday());return start,start+timedelta(days=7)
    if view=='day':return day,day+timedelta(days=1)
    if view=='agenda':return day,day+timedelta(days=31)
    raise ValueError('Choose Month, Week, Day or Agenda')

def events(view,day,path=p.DEFAULT_DB):
    low,high=span(view,day)
    lo=datetime.combine(low,datetime.min.time(),PKT).astimezone(UTC).isoformat(timespec='seconds');hi=datetime.combine(high,datetime.min.time(),PKT).astimezone(UTC).isoformat(timespec='seconds')
    return store.read('calendar_events',"SELECT * FROM calendar_events WHERE status='confirmed' AND start_at<? AND (start_at>=? OR (end_at!='' AND end_at>?)) ORDER BY start_at,id LIMIT 1001",(hi,lo,lo),path)

def on_day(event,day):
    start=local(event['start_at']);end=local(event['end_at']) if event['end_at'] else start
    lo=datetime.combine(day,datetime.min.time(),PKT);hi=lo+timedelta(days=1)
    return start<hi and (end>lo if event['end_at'] else start>=lo)

def lanes(events,day):
    lo=datetime.combine(day,datetime.min.time(),PKT);hi=lo+timedelta(days=1);items=[];ends=[]
    for ev in events:
        if not on_day(ev,day):continue
        start=max(lo,local(ev['start_at']));end=min(hi,local(ev['end_at'])) if ev['end_at'] else min(hi,start+timedelta(minutes=25))
        lane=next((i for i,v in enumerate(ends) if v<=start),len(ends))
        if lane==len(ends):ends.append(end)
        else:ends[lane]=end
        items.append(dict(event=ev,top=(start-lo).total_seconds()/60,height=max(22,(end-start).total_seconds()/60),lane=lane))
    for item in items:item['lanes']=max(1,len(ends))
    return items
