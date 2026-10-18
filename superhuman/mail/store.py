"""Mailbox state in the canonical DB; no remote mailbox mutation methods."""
import json
import re
import time
from uuid import uuid4
from superhuman.projects import engine as p
from superhuman.dialogue import store as dialogue
from . import vault

SLOTS = {'personal_gmail': ('Personal Gmail', 'gmail'), 'edsync_gmail': ('EdSync Gmail', 'gmail'),
         'edsync_titan': ('EdSync Titan', 'titan'), 'nextstep_gmail': ('NextSTEP Gmail', 'gmail')}
HOSTS = {'godaddy': 'imap.secureserver.net', 'titan': 'imap.titan.email', 'titan_eu': 'imap0101.titan.email'}


def initialize(path=p.DEFAULT_DB):
    dialogue.initialize(path)
    with p.connect(path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS mail_accounts(
          id TEXT PRIMARY KEY,label TEXT NOT NULL,provider TEXT NOT NULL,email TEXT,
          scope TEXT,credential TEXT,host TEXT,generation TEXT,auto_sync INTEGER NOT NULL DEFAULT 0,
          next_sync REAL NOT NULL DEFAULT 0,last_sync TEXT,last_error TEXT,
          limited INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS mail_messages(
          id TEXT PRIMARY KEY,account_id TEXT NOT NULL,remote_id TEXT NOT NULL,
          sender TEXT NOT NULL,subject TEXT NOT NULL,sent_at TEXT NOT NULL,
          body TEXT NOT NULL,notice TEXT NOT NULL,received REAL NOT NULL,
          UNIQUE(account_id,remote_id));
        CREATE TABLE IF NOT EXISTS mail_syncs(
          id TEXT PRIMARY KEY,account_id TEXT NOT NULL,generation TEXT NOT NULL,
          status TEXT NOT NULL,created REAL NOT NULL,error TEXT);
        CREATE TABLE IF NOT EXISTS mail_reports(
          id TEXT PRIMARY KEY,account_id TEXT NOT NULL,thread_id TEXT NOT NULL,
          turn_id TEXT NOT NULL UNIQUE,snapshot TEXT NOT NULL,created_at TEXT NOT NULL,
          submission_key TEXT NOT NULL UNIQUE);
        ''')
        for slot, (label, provider) in SLOTS.items():
            db.execute('INSERT OR IGNORE INTO mail_accounts(id,label,provider) VALUES(?,?,?)', (slot,label,provider))
    from superhuman.mailflow.state import initialize as initialize_mailflow
    initialize_mailflow(path)


def account(slot, path=p.DEFAULT_DB, secrets=False):
    initialize(path)
    if slot not in SLOTS: raise ValueError('Unknown inbox')
    with p.connect(path) as db:
        result = dict(db.execute('SELECT * FROM mail_accounts WHERE id=?', (slot,)).fetchone())
    result['connected'] = bool(result['credential'])
    if not secrets: result.pop('credential')
    return result


def accounts(path=p.DEFAULT_DB):
    return [account(slot, path) for slot in SLOTS]


def email_address(value):
    if not isinstance(value,str) or len(value)>254 or not re.fullmatch(r'[^\s@<>\x00-\x1f]+@[^\s@<>\x00-\x1f]+\.[^\s@<>\x00-\x1f]+',value):
        raise ValueError('Enter a complete email address')
    return value.strip().casefold()


def connect(slot,email,scope,credential,host=None,path=p.DEFAULT_DB):
    current = account(slot,path,secrets=True); email=email_address(email)
    if scope not in dialogue.scopes(): raise ValueError('Choose a configured workstream')
    if current['email'] and current['email'] != email:
        raise ValueError('This inbox is assigned to another email. Use the original address to preserve source identity.')
    if current['provider']=='titan' and host not in HOSTS.values(): raise ValueError('Unsupported Titan host')
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        saved=db.execute('SELECT email FROM mail_accounts WHERE id=?',(slot,)).fetchone()
        if saved['email'] and saved['email']!=email:
            raise ValueError('This inbox is assigned to another email')
        any_credentials=db.execute('SELECT 1 FROM mail_accounts WHERE credential IS NOT NULL LIMIT 1').fetchone()
        if not any_credentials and db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='comms_channels'").fetchone():
            any_credentials=db.execute('SELECT 1 FROM comms_channels WHERE credential IS NOT NULL LIMIT 1').fetchone()
        # A missing key with existing encrypted credentials is a recovery event.
        vault.cipher(create=not bool(any_credentials))
        encrypted=vault.seal(credential)
        db.execute("UPDATE mail_syncs SET status='cancelled' WHERE account_id=? AND status='queued'",(slot,))
        db.execute('UPDATE mail_accounts SET email=?,scope=?,credential=?,host=?,generation=?,auto_sync=0,last_error=NULL WHERE id=?',
                   (email,scope,encrypted,host,uuid4().hex,slot))


def disconnect(slot,path=p.DEFAULT_DB):
    account(slot,path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('UPDATE mail_accounts SET credential=NULL,generation=?,auto_sync=0 WHERE id=?',(uuid4().hex,slot))
        db.execute("UPDATE mail_syncs SET status='cancelled' WHERE account_id=? AND status='queued'",(slot,))


def set_auto(slot,enabled,path=p.DEFAULT_DB):
    a=account(slot,path)
    if type(enabled) is not bool or not a['connected']: raise ValueError('Connect this inbox first')
    with p.connect(path) as db:
        db.execute('UPDATE mail_accounts SET auto_sync=?,next_sync=? WHERE id=?',(int(enabled),time.time(),slot))


def queue_sync(slot,path=p.DEFAULT_DB):
    a=account(slot,path)
    if not a['connected']: raise ValueError('Connect this inbox first')
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        existing=db.execute("SELECT id FROM mail_syncs WHERE account_id=? AND status IN ('queued','running')",(slot,)).fetchone()
        if existing:return existing['id']
        key=uuid4().hex
        db.execute("INSERT INTO mail_syncs VALUES(?,?,?,'queued',?,NULL)",(key,slot,a['generation'],time.time()))
        return key


def recover(path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:
        db.execute("UPDATE mail_syncs SET status='interrupted',error='Worker restarted. Queue another sync.' WHERE status='running'")


def claim(path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        for a in db.execute('SELECT * FROM mail_accounts WHERE credential IS NOT NULL AND auto_sync=1 AND next_sync<=?',(time.time(),)).fetchall():
            if not db.execute("SELECT 1 FROM mail_syncs WHERE account_id=? AND status IN ('queued','running')",(a['id'],)).fetchone():
                db.execute("INSERT INTO mail_syncs VALUES(?,?,?,'queued',?,NULL)",(uuid4().hex,a['id'],a['generation'],time.time()))
            db.execute('UPDATE mail_accounts SET next_sync=? WHERE id=?',(time.time()+600,a['id']))
        row=db.execute("SELECT s.* FROM mail_syncs s JOIN mail_accounts a ON a.id=s.account_id WHERE s.status='queued' AND a.credential IS NOT NULL AND a.generation=s.generation ORDER BY s.created,s.id LIMIT 1").fetchone()
        if row is None:return None
        db.execute("UPDATE mail_syncs SET status='running' WHERE id=?",(row['id'],))
        return dict(row)


def finish_sync(job,messages,limited=False,error=None,path=p.DEFAULT_DB):
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        a=db.execute('SELECT * FROM mail_accounts WHERE id=?',(job['account_id'],)).fetchone()
        if a['generation']!=job['generation'] or not a['credential']:
            db.execute("UPDATE mail_syncs SET status='cancelled' WHERE id=?",(job['id'],));return
        if not error:
            for m in messages:
                db.execute('INSERT OR IGNORE INTO mail_messages VALUES(?,?,?,?,?,?,?,?,?)',
                           (uuid4().hex,a['id'],m['remote_id'],m['sender'][:500],m['subject'][:500],m['sent_at'][:100],m['body'][:6000],m['notice'][:300],m['received']))
        db.execute('UPDATE mail_accounts SET last_sync=CASE WHEN ? IS NULL THEN ? ELSE last_sync END,last_error=?,limited=?,next_sync=? WHERE id=?',
                   (error,p.stamp(),error,int(limited),time.time()+600,a['id']))
        db.execute('UPDATE mail_syncs SET status=?,error=? WHERE id=?',('failed' if error else 'done',error,job['id']))
        # Retain at most 500 previews per inbox. Saved report snapshots remain intact.
        # Unreported previews are retained; the resumable reader applies capacity backpressure.


def messages(slot,path=p.DEFAULT_DB,limit=50):
    account(slot,path)
    if not 1<=limit<=500:raise ValueError('Invalid message limit')
    with p.connect(path) as db:
        return [dict(row) for row in db.execute('SELECT * FROM mail_messages WHERE account_id=? ORDER BY received DESC,id LIMIT ?',(slot,limit))]


def message(slot,key,path=p.DEFAULT_DB):
    account(slot,path)
    with p.connect(path) as db:
        row=db.execute('SELECT * FROM mail_messages WHERE id=? AND account_id=?',(key,slot)).fetchone()
    if not row:raise ValueError('Message not found in this inbox')
    return dict(row)


def make_report(slot,submission_key,path=p.DEFAULT_DB):
    from superhuman.mailflow.reports import make_report as next_report
    return next_report(slot,submission_key,path)


def report_prompt(claimed,path=p.DEFAULT_DB):
    from superhuman.briefing.engine import mail_prompt
    return mail_prompt(claimed,path)
