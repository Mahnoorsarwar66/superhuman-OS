"""Explicitly requested planning jobs and persistent worker status."""
import json
import time
from uuid import uuid4
from superhuman.projects import engine as p
from superhuman.runtime import engine as r


def initialize(path=p.DEFAULT_DB):
    r.initialize(path)
    with p.connect(path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS hosted_plans(project_id TEXT PRIMARY KEY,status TEXT NOT NULL,token TEXT,started REAL,error_type TEXT);
        CREATE TABLE IF NOT EXISTS hosted_worker(id INTEGER PRIMARY KEY CHECK(id=1),owner TEXT,last_seen REAL,activity TEXT,paused INTEGER NOT NULL DEFAULT 0);
        INSERT OR IGNORE INTO hosted_worker(id,paused) VALUES(1,0);
        ''')


def request_plan(pid,path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        project=db.execute('SELECT status FROM projects WHERE id=?',(pid,)).fetchone()
        if not project or project['status'] not in ('new','plan_failed'):raise ValueError('This project is not ready for planning')
        current=db.execute('SELECT status FROM hosted_plans WHERE project_id=?',(pid,)).fetchone()
        if current and current['status'] in ('queued','running'):raise ValueError('Planning is already queued or running')
        db.execute("INSERT OR REPLACE INTO hosted_plans VALUES(?,'queued',NULL,NULL,NULL)",(pid,))
    r.event('planning_requested',pid,path=path)


def run_plan(path=p.DEFAULT_DB,client=None):
    initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute("SELECT project_id FROM hosted_plans WHERE status='queued' ORDER BY rowid LIMIT 1").fetchone()
        if not row:return None
        pid=row['project_id'];token=uuid4().hex
        db.execute("UPDATE hosted_plans SET status='running',token=?,started=? WHERE project_id=?",(token,time.time(),pid))
    try:
        p.generate_plan(pid,path,client=client)
        status,error='done',None
    except Exception as exc:status,error='failed',type(exc).__name__
    with p.connect(path) as db:
        db.execute('UPDATE hosted_plans SET status=?,error_type=? WHERE project_id=? AND token=?',(status,error,pid,token))
    r.event('planning_'+status,pid,detail={'error_type':error} if error else {},path=path)
    return {'project_id':pid,'status':status,'error_type':error}


def pulse(owner,activity='idle',path=p.DEFAULT_DB):
    with p.connect(path) as db:db.execute('UPDATE hosted_worker SET owner=?,last_seen=?,activity=? WHERE id=1',(owner,time.time(),activity))


def worker_status(path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:
        row=dict(db.execute('SELECT * FROM hosted_worker WHERE id=1').fetchone())
    row['online']=bool(row.get('last_seen') and row['last_seen']>time.time()-30 and row.get('activity')!='stopped')
    return row


def pause(value,path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:db.execute('UPDATE hosted_worker SET paused=? WHERE id=1',(int(bool(value)),))
    r.event('worker_paused' if value else 'worker_resumed',path=path)


def recover_plans(older_than=3600,path=p.DEFAULT_DB):
    if older_than<60:raise ValueError('Recovery age must be at least 60 seconds')
    initialize(path)
    with p.connect(path) as db:
        rows=db.execute("SELECT project_id FROM hosted_plans WHERE status='running' AND started<?",(time.time()-older_than,)).fetchall()
    for row in rows:
        pid=row['project_id'];p.recover(pid,older_than,path)
        with p.connect(path) as db:db.execute("UPDATE hosted_plans SET status='interrupted',error_type='InterruptedPlanning' WHERE project_id=? AND status='running'",(pid,))
        r.event('planning_recovery_requested',pid,path=path)
    return len(rows)
