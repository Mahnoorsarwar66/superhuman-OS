"""Atomic per-message checkpoints, durable provider identities and report coverage."""
import json
import time
from uuid import uuid4
from superhuman.projects import engine as p

CAPACITY=5000


def initialize(path=p.DEFAULT_DB):
    # Called AFTER the existing mail schema exists. Never calls mail.initialize.
    with p.connect(path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS mail_scans(account_id TEXT PRIMARY KEY,id TEXT NOT NULL,
          generation TEXT NOT NULL,start REAL NOT NULL,end REAL NOT NULL,status TEXT NOT NULL,
          cursor TEXT NOT NULL,note TEXT,updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS mail_seen(account_id TEXT NOT NULL,remote_id TEXT NOT NULL,
          PRIMARY KEY(account_id,remote_id));
        CREATE TABLE IF NOT EXISTS mail_report_members(report_id TEXT NOT NULL,source_id TEXT NOT NULL,
          PRIMARY KEY(report_id,source_id));
        CREATE INDEX IF NOT EXISTS mail_member_source ON mail_report_members(source_id);
        CREATE TABLE IF NOT EXISTS mailflow_migrations(name TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS mail_indexed_reports(id TEXT PRIMARY KEY);
        ''')
        if not db.execute("SELECT 1 FROM mailflow_migrations WHERE name='legacy-seen'").fetchone():
            db.execute('INSERT OR IGNORE INTO mail_seen SELECT account_id,remote_id FROM mail_messages')
            db.execute("INSERT OR IGNORE INTO mailflow_migrations VALUES('legacy-seen')")
        # Backfill memberships for historical reports once; thereafter new reports
        # write membership in the SAME transaction as their queued turn.
        for row in db.execute('SELECT r.id,r.snapshot FROM mail_reports r WHERE NOT EXISTS(SELECT 1 FROM mail_indexed_reports i WHERE i.id=r.id)').fetchall():
            try:members=json.loads(row['snapshot']).get('messages',[])
            except (ValueError,TypeError):members=[]
            for member in members:
                if isinstance(member,dict) and isinstance(member.get('source_id'),str):
                    db.execute('INSERT OR IGNORE INTO mail_report_members VALUES(?,?)',(row['id'],member['source_id']))
            db.execute('INSERT OR IGNORE INTO mail_indexed_reports VALUES(?)',(row['id'],))


def cursor():
    return dict(pending=[],token='',listed=False,validity='',found=0,processed=0,saved=0,unavailable=0,pages=0,excess=False)


def scan(account,path=p.DEFAULT_DB):
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM mail_scans WHERE account_id=?',(account['id'],)).fetchone()
        if row and row['generation']==account['generation'] and row['status'] in ('active','capacity_blocked','error'):
            return dict(row)
        now=time.time()
        value=dict(account_id=account['id'],id=uuid4().hex,generation=account['generation'],start=now-7*86400,
                   end=now,status='active',cursor=json.dumps(cursor()),note=None,updated=p.stamp())
        db.execute('INSERT OR REPLACE INTO mail_scans VALUES(:account_id,:id,:generation,:start,:end,:status,:cursor,:note,:updated)',value)
        return value


def valid(db,scan):
    row=db.execute('SELECT a.generation,a.credential,s.id FROM mail_accounts a JOIN mail_scans s ON s.account_id=a.id WHERE a.id=?',(scan['account_id'],)).fetchone()
    if not row or not row['credential'] or row['generation']!=scan['generation'] or row['id']!=scan['id']:
        raise ValueError('Inbox connection or scan changed during this read')


def checkpoint(scan,cursor,message=None,status='active',note=None,path=p.DEFAULT_DB):
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');valid(db,scan)
        if message is not None:
            db.execute('INSERT OR IGNORE INTO mail_messages VALUES(?,?,?,?,?,?,?,?,?)',
                       (uuid4().hex,scan['account_id'],message['remote_id'],message['sender'][:500],message['subject'][:500],
                        message['sent_at'][:100],message['body'][:6000],message['notice'][:300],message['received']))
            db.execute('INSERT OR IGNORE INTO mail_seen VALUES(?,?)',(scan['account_id'],message['remote_id']))
        db.execute('UPDATE mail_scans SET cursor=?,status=?,note=?,updated=? WHERE account_id=? AND id=?',
                   (json.dumps(cursor),status,note,p.stamp(),scan['account_id'],scan['id']))


def known(slot,remote_id,path=p.DEFAULT_DB):
    with p.connect(path) as db:
        return bool(db.execute('SELECT 1 FROM mail_seen WHERE account_id=? AND remote_id=?',(slot,remote_id)).fetchone()
                    or db.execute('SELECT 1 FROM mail_messages WHERE account_id=? AND remote_id=?',(slot,remote_id)).fetchone())


DONE="""EXISTS(SELECT 1 FROM mail_report_members m JOIN mail_reports r ON r.id=m.report_id
          JOIN dialogue_turns t ON t.id=r.turn_id WHERE m.source_id=x.id AND t.status='done')"""
PENDING="""EXISTS(SELECT 1 FROM mail_report_members m JOIN mail_reports r ON r.id=m.report_id
             JOIN dialogue_turns t ON t.id=r.turn_id WHERE m.source_id=x.id AND t.status IN ('queued','running'))"""


def make_room(slot,path=p.DEFAULT_DB):
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        total=db.execute('SELECT COUNT(*) FROM mail_messages WHERE account_id=?',(slot,)).fetchone()[0]
        if total<CAPACITY:return True
        # Only discard previews already included in a completed report. Immutable
        # report snapshots and durable remote identities remain available.
        ids=[r[0] for r in db.execute('SELECT x.id FROM mail_messages x WHERE x.account_id=? AND '+DONE+' AND NOT '+PENDING+' ORDER BY x.received,x.id LIMIT 100',(slot,))]
        if ids:db.executemany('DELETE FROM mail_messages WHERE id=?',[(v,) for v in ids])
        return total-len(ids)<CAPACITY


def finish_job(job,scan,status,error=None,path=p.DEFAULT_DB):
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        try:valid(db,scan)
        except ValueError:
            db.execute("UPDATE mail_syncs SET status='cancelled' WHERE id=?",(job['id'],));return
        db.execute('UPDATE mail_syncs SET status=?,error=? WHERE id=?',('failed' if error else 'done',error,job['id']))
        db.execute('UPDATE mail_accounts SET last_sync=CASE WHEN ? IS NULL THEN ? ELSE last_sync END,last_error=?,limited=?,next_sync=? WHERE id=?',
                   (error,p.stamp(),error,int(status!='complete'),time.time()+600,scan['account_id']))
        if status=='active' and not error:
            if not db.execute("SELECT 1 FROM mail_syncs WHERE account_id=? AND status IN ('queued','running')",(scan['account_id'],)).fetchone():
                db.execute("INSERT INTO mail_syncs VALUES(?,?,?,'queued',?,NULL)",(uuid4().hex,scan['account_id'],scan['generation'],time.time()))


def summary(slot,path=p.DEFAULT_DB):
    with p.connect(path) as db:
        counts=db.execute('SELECT COUNT(*) AS saved,COALESCE(SUM('+DONE+'),0) AS included,COALESCE(SUM(NOT '+DONE+' AND '+PENDING+'),0) AS pending FROM mail_messages x WHERE account_id=?',(slot,)).fetchone()
        row=db.execute('SELECT * FROM mail_scans WHERE account_id=?',(slot,)).fetchone()
    result=dict(counts);result['waiting']=result['saved']-result['included']-result['pending']
    if row:
        result['scan']={k:row[k] for k in ('status','start','end','note','updated')}
        c=json.loads(row['cursor']);result['scan'].update({k:c[k] for k in ('found','processed','saved','unavailable','pages')})
    else:result['scan']=None
    return result


def restart(slot,path=p.DEFAULT_DB):
    from superhuman.mail import store
    a=store.account(slot,path)
    if not a['connected']:raise ValueError('Connect this inbox first')
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT 1 FROM mail_syncs WHERE account_id=? AND status='running'",(slot,)).fetchone():
            raise ValueError('Wait for the active read to finish before restarting its scan')
        db.execute('DELETE FROM mail_scans WHERE account_id=?',(slot,))
    return store.queue_sync(slot,path)
