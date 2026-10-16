"""Select up to twelve not-yet-included messages without duplicate reservations."""
import json
import re
from uuid import uuid4
from superhuman.projects import engine as p
from superhuman.mail import store
from . import state


def make_report(slot,submission_key,path=p.DEFAULT_DB):
    a=store.account(slot,path)
    if not re.fullmatch(r'[a-f0-9]{32}',submission_key):raise ValueError('Reload the report form')
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        existing=db.execute('SELECT account_id,thread_id FROM mail_reports WHERE submission_key=?',(submission_key,)).fetchone()
        if existing:
            if existing['account_id']!=slot:raise ValueError('Report submission belongs to another inbox')
            return existing['thread_id']
        selected=db.execute('SELECT x.* FROM mail_messages x WHERE account_id=? AND NOT '+state.DONE+' AND NOT '+state.PENDING+' ORDER BY received DESC,id LIMIT 12',(slot,)).fetchall()
        if not selected:raise ValueError('No saved email is waiting for a report. Existing messages are already included or reserved by a pending report; no model request queued.')
        snapshot={'account_id':slot,'label':a['label'],'email':a['email'],'captured_at':p.stamp(),
                  'coverage':'Up to 12 saved messages not yet included in completed or pending reports. Excerpts only; not proof of a full inbox review.',
                  'messages':[dict(source_id=m['id'],sender=m['sender'],subject=m['subject'],sent_at=m['sent_at'],body=m['body'][:2000],
                                   notice=m['notice']+' Report excerpt limited to 2000 characters.') for m in selected]}
        tid=uuid4().hex;turn=uuid4().hex;rid=uuid4().hex;stamp=p.stamp()
        db.execute('INSERT INTO dialogue_threads VALUES(?,?,?,?,0,?,?)',(tid,a['scope'],a['label']+' inbox report',1,stamp,stamp))
        db.execute("INSERT INTO dialogue_turns(id,thread_id,ordinal,submission_key,user_text,status,created_at) VALUES(?,?,1,?,?,'queued',?)",
                   (turn,tid,submission_key,'Review these newly selected inbox excerpts. Summarise decisions and follow-ups; propose useful local drafts for approval.',stamp))
        db.execute('INSERT INTO mail_reports VALUES(?,?,?,?,?,?,?)',(rid,slot,tid,turn,json.dumps(snapshot,ensure_ascii=False),stamp,submission_key))
        db.executemany('INSERT INTO mail_report_members VALUES(?,?)',[(rid,m['id']) for m in selected])
        store.dialogue.event(db,'mail_report_queued',tid,turn,account_id=slot)
    return tid
