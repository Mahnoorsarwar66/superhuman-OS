"""Read-only local evidence, plus explicit read-only inbox probe queueing."""
import json,sqlite3,time
from pathlib import Path
from . import VERSION

def report():
    from superhuman.projects import engine as p
    from superhuman.departments.store import readonly,tables,rows
    from superhuman.planning import store
    from superhuman.core.router import WORKSTREAMS
    result={'version':VERSION,'model_requests':0,'worker':{'state':'not_started'},'tasks':{},'inboxes':[],'artifacts':{'checked':0,'problems':[]},'exports':{'checked':0,'problems':[]},'assignment_problems':[],'database_checks':[],'planning_warnings':[]}
    for label,path in [('Projects',p.DEFAULT_DB),('Department planning',store.default_path())]:
        try:
            with readonly(path) as db:
                if db:result['database_checks'].append({'database':label,'result':db.execute('PRAGMA quick_check').fetchone()[0]})
                else:result['database_checks'].append({'database':label,'result':'Not created yet'})
        except sqlite3.Error:result['database_checks'].append({'database':label,'result':'Database could not be read'})
    try:
        with readonly(p.DEFAULT_DB) as db:
            ts=tables(db)
            if 'hosted_worker' in ts:
                row=db.execute('SELECT last_seen,activity,paused FROM hosted_worker WHERE id=1').fetchone()
                if row:
                    online=bool(row['last_seen'] and row['last_seen']>time.time()-30 and row['activity']!='stopped')
                    result['worker']={'state':'online' if online else 'offline','activity':row['activity'],'paused':bool(row['paused'])}
            if 'project_tasks' in ts:
                result['tasks']={r['status']:r['n'] for r in db.execute('SELECT status,COUNT(*) n FROM project_tasks GROUP BY status')}
                outputs=rows(db,'SELECT project_id,id,result_json FROM project_tasks WHERE result_json IS NOT NULL ORDER BY rowid DESC LIMIT 200')
                for row in outputs:
                    result['artifacts']['checked']+=1
                    try:p._text(json.loads(row['result_json']))
                    except (ValueError,OSError,TypeError,UnicodeError):result['artifacts']['problems'].append({'project_id':row['project_id'],'task_id':row['id'],'issue':'Output missing, changed or unreadable'})
                result['artifacts']['scope']='Latest 200 saved outputs, with existing content/hash checks'
            if 'mail_accounts' in ts:
                for row in db.execute('SELECT id,label,provider,credential,last_sync,last_error FROM mail_accounts'):
                    result['inboxes'].append({'slot':row['id'],'label':row['label'],'provider':row['provider'],'connected':bool(row['credential']),'last_successful_sync':row['last_sync'],'last_sync_failed':bool(row['last_error'])})
            for table,column in [('projects','workstream'),('dialogue_threads','scope'),('research_areas','scope')]:
                if table in ts:
                    for row in db.execute('SELECT DISTINCT '+column+' scope FROM '+table):
                        if row['scope'] not in WORKSTREAMS:result['assignment_problems'].append({'records':table,'scope':row['scope'],'issue':'Unknown workstream; not moved automatically'})
    except sqlite3.Error:result['database_checks'].append({'database':'Operational records','result':'Some records could not be read'})
    for scope in WORKSTREAMS:
        data=store.snapshot(scope)
        if data['warnings']:result['planning_warnings'].append({'scope':scope,'issue':'Planning records unreadable'})
    from superhuman.departments.store import materials
    from superhuman.capabilities import exports
    for scope in WORKSTREAMS:
        _,records,_=materials(scope)
        for record in records[:50]:
            result['exports']['checked']+=1
            try:exports.artifact(scope,record['export_id'])
            except (ValueError,OSError,KeyError):result['exports']['problems'].append({'scope':scope,'export_id':record['export_id'],'issue':'Export missing, changed or unreadable'})
    result['live_verification']='Inbox connectivity is established by a successful real sync; connection configuration alone is not proof. Saved checks are read-only; no live sync or model call performed by this report.'
    return result

def queue_inboxes():
    from superhuman.mail import store
    outcomes=[]
    for account in store.accounts():
        if not account.get('connected'):continue
        try:store.queue_sync(account['id']);outcomes.append({'slot':account['id'],'result':'Read-only sync queued'})
        except ValueError:outcomes.append({'slot':account['id'],'result':'Could not queue; check existing sync or account settings'})
    return outcomes
