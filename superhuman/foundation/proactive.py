"""Deterministic, deduplicated in-app signals. No sending, grants or paid calls."""
import json,time
from datetime import datetime,timedelta,timezone
from superhuman.projects import engine as p
from superhuman.team import store as team
from .storage import today
RULES={
 'deadline':('Deadline approaching',72),
 'stalled':('Stalled assignment',48),
 'dependency':('Dependencies completed',1),
 'review':('Deliverable ready for review',1),
 'communication':('New communication alert',1),
 'next_action':('Active project needs its next action',1),
 'conflict':('Disagreement or conflicting approved facts',1)}
TERMINAL={'completed','cancelled','rejected'}

def initialize(path=p.DEFAULT_DB):
    team.initialize(path)
    with p.connect(path) as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS proactive_control(id INTEGER PRIMARY KEY CHECK(id=1),paused INTEGER NOT NULL DEFAULT 0,next_scan REAL NOT NULL DEFAULT 0);
        INSERT OR IGNORE INTO proactive_control(id) VALUES(1);
        CREATE TABLE IF NOT EXISTS proactive_rules(id TEXT PRIMARY KEY,enabled INTEGER NOT NULL DEFAULT 1,hours INTEGER NOT NULL,action TEXT NOT NULL DEFAULT 'notify',version INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS proactive_signals(id TEXT PRIMARY KEY,rule_id TEXT NOT NULL,entity TEXT NOT NULL,title TEXT NOT NULL,detail TEXT NOT NULL,url TEXT NOT NULL,state TEXT NOT NULL,episode INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS proactive_history(seq INTEGER PRIMARY KEY AUTOINCREMENT,signal_id TEXT NOT NULL,event TEXT NOT NULL,created_at TEXT NOT NULL);''')
        for key,(_,hours) in RULES.items():db.execute('INSERT OR IGNORE INTO proactive_rules(id,hours) VALUES(?,?)',(key,hours))

def rules(path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:return [dict(r) for r in db.execute('SELECT * FROM proactive_rules ORDER BY id')]

def configure(ident,expected,enabled,hours,action,path=p.DEFAULT_DB):
    initialize(path)
    if ident not in RULES or type(enabled) is not bool or type(hours) is not int or not 1<=hours<=8760 or action not in ('notify','twin_review'):raise ValueError('Invalid rule settings')
    with p.connect(path) as db:
        if not db.execute('UPDATE proactive_rules SET enabled=?,hours=?,action=?,version=version+1 WHERE id=? AND version=?',(int(enabled),hours,action,ident,expected)).rowcount:raise ValueError('Rule changed; reload')
        db.execute('UPDATE proactive_control SET next_scan=0 WHERE id=1')
        team.event(db,'owner','proactive_rule_updated',{'rule':ident,'action':action,'enabled':enabled})

def signals(path=p.DEFAULT_DB,include_resolved=False):
    initialize(path)
    with p.connect(path) as db:return [dict(r) for r in db.execute('SELECT * FROM proactive_signals '+('' if include_resolved else "WHERE state!='resolved' ")+'ORDER BY updated_at DESC,id')]

def acknowledge(ident,episode,path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:
        if not db.execute("UPDATE proactive_signals SET state='acknowledged',updated_at=? WHERE id=? AND episode=? AND state='new'",(p.stamp(),ident,episode)).rowcount:raise ValueError('Signal changed or already acknowledged; reload')
        db.execute("INSERT INTO proactive_history(signal_id,event,created_at) VALUES(?,'acknowledged',?)",(ident,p.stamp()))

def scan(path=p.DEFAULT_DB,force=False,now=None):
    initialize(path);now=time.time() if now is None else now
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');control=db.execute('SELECT * FROM proactive_control WHERE id=1').fetchone()
        if control['paused'] or not force and control['next_scan']>now:return {'scanned':False}
        db.execute('UPDATE proactive_control SET next_scan=? WHERE id=1',(now+60,))
    cfg={r['id']:r for r in rules(path)};active={};tasks=team.tasks(path);projects=team.projects(path);parents={q['id']:q for q in projects};byid={t['id']:t for t in tasks}
    def add(rule,entity,title,detail,url):
        if cfg[rule]['enabled']:active[rule+':'+entity]=(rule,entity,title,detail,url)
    for t in tasks:
        if parents[t['project_id']]['status']!='active' or t['state'] in TERMINAL:continue
        url='/team/tasks/'+t['id']
        if t['due'] and t['due']<=(today()+timedelta(hours=cfg['deadline']['hours'])).isoformat():add('deadline',t['id'],t['title'],'Due '+t['due']+' (Pakistan date). Check readiness and blockers.',url)
        try:changed=datetime.fromisoformat(t['updated_at']).replace(tzinfo=timezone.utc).timestamp() if datetime.fromisoformat(t['updated_at']).tzinfo is None else datetime.fromisoformat(t['updated_at']).timestamp()
        except ValueError:changed=now
        if now-changed>=cfg['stalled']['hours']*3600 and t['state'] not in ('awaiting_review','owner_review'):add('stalled',t['id'],t['title'],'No task-state update within the agreed interval; this is a prompt to check, not proof of inactivity.',url)
        deps=json.loads(t['deps'])
        if deps and t['state'] in ('queued','ready','waiting_dependency','held') and all(i in byid and byid[i]['state']=='completed' for i in deps):add('dependency',t['id'],t['title'],'Dependencies are completed. Reassess readiness; existing approval gates still apply.',url)
        if t['state'] in ('awaiting_review','owner_review'):add('review',t['id'],t['title'],'A saved result is ready for the appropriate review. No automatic acceptance.',url)
    for q in projects:
        if q['status']=='active' and not any(t['project_id']==q['id'] and t['state'] not in TERMINAL for t in tasks):add('next_action',q['id'],q['title'],'No open assignment. Ask The Twin to propose the next bounded step, or complete the project.','/team/projects/'+q['id'])
    for req in team.requests(path):
        if req['status'] in ('open','escalated') and req['kind'] in ('challenge','disagreement'):add('conflict','request-'+req['id'],'Specialist concern needs resolution','Review the recorded concern. Only Mahnoor can approve an alternative over The Twin.','/team/tasks/'+req['task_id'])
    # Use already-consented analysis alerts rather than scanning private raw messages.
    from superhuman.comms import store as comms
    for a in comms.alerts(path):
        if a['state']=='new':add('communication',a['id'],'Communication needs attention','A saved communication analysis raised an alert. Review it in Communications.','/twin?tab=communications')
    from . import storage
    groups={}
    for item in storage.rows(path):
        if item['kind']=='fact' and item['status']=='approved' and storage.health(item)=='Current':groups.setdefault(item['fact_key'],[]).append(item)
    for key,items in groups.items():
        if len({r['digest'] for r in items})>1:add('conflict','fact-'+key,'Conflicting approved facts','Resolve the fact key '+key+' before using these values.','/storage/items/'+items[0]['id'])
    stamp=p.stamp()
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        for ident,values in active.items():
            old=db.execute('SELECT * FROM proactive_signals WHERE id=?',(ident,)).fetchone()
            if not old:
                db.execute('INSERT INTO proactive_signals VALUES(?,?,?,?,?,?,?,1,?,?)',(ident,*values,'new',stamp,stamp))
                event='opened'
            elif old['state']=='resolved':
                db.execute("UPDATE proactive_signals SET title=?,detail=?,url=?,state='new',episode=episode+1,updated_at=? WHERE id=?",(values[2],values[3],values[4],stamp,ident));event='reopened'
            else:
                db.execute('UPDATE proactive_signals SET title=?,detail=?,url=? WHERE id=?',(values[2],values[3],values[4],ident));continue
            db.execute('INSERT INTO proactive_history(signal_id,event,created_at) VALUES(?,?,?)',(ident,event,stamp))
        for old in db.execute("SELECT id FROM proactive_signals WHERE state!='resolved'").fetchall():
            if old['id'] not in active:
                db.execute("UPDATE proactive_signals SET state='resolved',updated_at=? WHERE id=?",(stamp,old['id']))
                db.execute("INSERT INTO proactive_history(signal_id,event,created_at) VALUES(?,'resolved',?)",(old['id'],stamp))
    return {'scanned':True,'active':len(active)}

def twin_signals(path=p.DEFAULT_DB):
    cfg={r['id']:r for r in rules(path)}
    return [r for r in signals(path) if r['state']=='new' and cfg[r['rule_id']]['enabled'] and cfg[r['rule_id']]['action']=='twin_review'][:12]

def pause_for_rollback(path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:db.execute('UPDATE proactive_control SET paused=1 WHERE id=1')

def control(path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:return dict(db.execute('SELECT * FROM proactive_control WHERE id=1').fetchone())

def set_pause(expected,value,path=p.DEFAULT_DB):
    initialize(path)
    if type(expected) is not bool or type(value) is not bool:raise ValueError('Choose a valid pause state')
    with p.connect(path) as db:
        if not db.execute('UPDATE proactive_control SET paused=?,next_scan=0 WHERE id=1 AND paused=?',(int(value),int(expected))).rowcount:raise ValueError('Scanner pause state changed; reload')
        team.event(db,'owner','proactive_paused' if value else 'proactive_resumed')
