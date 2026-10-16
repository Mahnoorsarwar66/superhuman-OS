"""Single-event iCalendar export. No recipients, alarms or external invitations."""
from datetime import datetime


def escape(value):return str(value).replace('\\','\\\\').replace('\r','').replace('\n','\\n').replace(';','\\;').replace(',','\\,')


def fold(line):
    parts=[];current=''
    for char in line:
        if len((current+char).encode('utf-8'))>75:
            parts.append(current);current=' '+char
        else:current+=char
    parts.append(current)
    return '\r\n'.join(parts)


def stamp(value):return datetime.fromisoformat(value).strftime('%Y%m%dT%H%M%SZ')


def event(row):
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Superhuman OS//Local meetings//EN','CALSCALE:GREGORIAN',
        'BEGIN:VEVENT','UID:'+row['id']+'@superhuman.local','DTSTAMP:'+stamp(row['updated_at']),
        'SEQUENCE:'+str(row['version']),'DTSTART:'+stamp(row['start_at']),'SUMMARY:'+escape(row['title']),
        'STATUS:'+('CANCELLED' if row['status']=='cancelled' else 'CONFIRMED')]
    if row['end_at']:lines.append('DTEND:'+stamp(row['end_at']))
    if row['notes']:lines.append('DESCRIPTION:'+escape(row['notes']))
    lines+=['END:VEVENT','END:VCALENDAR']
    return ('\r\n'.join(fold(line) for line in lines)+'\r\n').encode('utf-8')
