"""Live planning deadlines on Calendar, with in-app reminders and an ICS feed."""
from datetime import date,timedelta,datetime,timezone
import hashlib
from superhuman.knowledge.store import today
from superhuman.planning import priority,store

def items():
    out=[]
    for scope,name,p in priority.all_departments():
        if p['warnings'] or p['goal'].get('status','active')!='active':continue
        g=p['goal']
        if g['target_date']:out.append(dict(id='goal-'+scope,title=name+': '+(g['objective'] or 'Department target'),due=g['target_date'],url=priority.edit_url(scope),kind='Department goal'))
        for m in p['milestones']:
            if m['target_date'] and m['status'] not in ('complete','archived'):out.append(dict(id='milestone-'+m['id'],title=m['title'],due=m['target_date'],url=priority.edit_url(scope,'milestone',m['id']),kind='Milestone'))
        for b in p['blockers']:
            if b['target_date'] and b['status']=='open':out.append(dict(id='blocker-'+b['id'],title=b['description'],due=b['target_date'],url=priority.edit_url(scope,'blocker',b['id']),kind='Missing input'))
    return sorted(out,key=lambda r:(r['due'],r['id']))
def panel():
    from superhuman.navigation.shell import esc
    rows=items();body='<section class="card"><h2>Department deadlines & reminders</h2><p>Live planning dates, alongside meetings. Completed and archived goals/milestones are excluded. Reminders refresh when you open this workspace.</p>'
    for row in rows[:50]:
        delta=(date.fromisoformat(row['due'])-today()).days
        status='Overdue' if delta<0 else 'Due today' if delta==0 else 'Due within 7 days' if delta<=7 else 'Upcoming'
        body+='<p><span class="badge">'+status+'</span> <a href="'+esc(row['url'])+'">'+esc(row['title'])+'</a> · '+row['due']+' · '+row['kind']+'</p>'
    if not rows:body+='<p>No open department deadlines recorded.</p>'
    if len(rows)>50:body+='<p><a href="/attention">View all reminders and attention items</a></p>'
    return body+'<p><a href="/planning-deadlines.ics">Download planning deadlines for a calendar app</a></p></section>'
def ics():
    def escape(s):return s.replace('\\','\\\\').replace('\r','').replace('\n','\\n').replace(';','\\;').replace(',','\\,')
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Superhuman//Planning deadlines 1.23//EN','CALSCALE:GREGORIAN']
    for r in items():
        dt=date.fromisoformat(r['due']);uid=hashlib.sha256(r['id'].encode()).hexdigest()+'@superhuman'
        lines+=['BEGIN:VEVENT','UID:'+uid,'DTSTAMP:'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'),'DTSTART;VALUE=DATE:'+dt.strftime('%Y%m%d'),'DTEND;VALUE=DATE:'+(dt+timedelta(days=1)).strftime('%Y%m%d'),'SUMMARY:'+escape(r['title']),'DESCRIPTION:'+escape(r['kind']+'; Open Superhuman '+r['url']), 'BEGIN:VALARM','ACTION:DISPLAY','TRIGGER:-P1D','DESCRIPTION:Department deadline tomorrow','END:VALARM','END:VEVENT']
    lines+=['END:VCALENDAR']
    # Fold UTF-8 content lines to at most 75 octets, without splitting a codepoint.
    folded=[]
    for line in lines:
        segment=''
        for c in line:
            if len((segment+c).encode())>75:folded.append(segment);segment=' '+c
            else:segment+=c
        folded.append(segment)
    return '\r\n'.join(folded)+'\r\n'
