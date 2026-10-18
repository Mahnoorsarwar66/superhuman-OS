"""Timestamped local readiness evidence; configuration is never called live proof."""
import json,os,time
from pathlib import Path
from superhuman.projects import engine as p
from superhuman.team import store as team,budget
from superhuman.departments.store import readonly,tables
from . import VERSION,DEFERRED

def report(path=p.DEFAULT_DB):
    with readonly(path) as db:
        ts=tables(db)
        integrity=db.execute('PRAGMA quick_check').fetchone()[0] if db else 'Not created'
        cfg=dict(db.execute('SELECT * FROM team_settings WHERE id=1').fetchone()) if 'team_settings' in ts else {}
        worker=dict(db.execute('SELECT * FROM hosted_worker WHERE id=1').fetchone()) if 'hosted_worker' in ts and db.execute('SELECT 1 FROM hosted_worker WHERE id=1').fetchone() else {}
        calls=[dict(r) for r in db.execute("SELECT model,state,finished_at FROM team_costs WHERE state IN ('metered','overrun') ORDER BY finished_at DESC LIMIT 20")] if 'team_costs' in ts else []
        cycle=db.execute("SELECT finished_at FROM team_cycles WHERE status='completed' ORDER BY finished_at DESC LIMIT 1").fetchone() if 'team_cycles' in ts else None
        employees=[dict(r) for r in db.execute('SELECT id,name,paused,allowed_tools FROM team_employees')] if 'team_employees' in ts else []
        channels=[dict(r) for r in db.execute('SELECT id,kind,label,connected,enabled,ai_enabled,last_sync,last_error FROM comms_channels')] if 'comms_channels' in ts else []
        if 'mail_accounts' in ts:
            for r in db.execute('SELECT id,label,provider,credential,last_sync,last_error FROM mail_accounts'):channels.append({'id':r['id'],'kind':r['provider'],'label':r['label'],'connected':bool(r['credential']),'enabled':None,'ai_enabled':None,'last_sync':r['last_sync'],'last_error':bool(r['last_error'])})
    from dotenv import dotenv_values
    model=cfg.get('model');key_present=bool(os.getenv('OPENAI_API_KEY') or dotenv_values('.env').get('OPENAI_API_KEY'))
    live_model=next((c for c in calls if c['model']==model),None)
    rate=budget.rate(model,path) if model else None
    current=budget.current(path) if cfg else None
    online=bool(worker.get('last_seen') and worker['last_seen']>time.time()-30 and worker.get('activity')!='stopped')
    checks=[
      {'area':'Application release','state':'installed','evidence':VERSION,'next':'Source release is not proof of end-to-end business execution.'},
      {'area':'Operational database','state':'ok' if integrity=='ok' else 'needs_attention','evidence':integrity,'next':'Read-only SQLite quick check.'},
      {'area':'Worker heartbeat','state':'online' if online else 'not_verified','evidence':{'last_seen':worker.get('last_seen'),'activity':worker.get('activity'),'paused':bool(worker.get('paused'))},'next':'A heartbeat is not proof that a task completes.'},
      {'area':'Team activation','state':'enabled' if cfg.get('enabled') else 'disabled','evidence':{'hold':bool(cfg.get('hold')),'employees':len(employees)},'next':'Review employee tools and pause settings below.'},
      {'area':'Model access','state':'historically_observed' if live_model else 'configured_unverified' if key_present else 'not_configured','evidence':{'configured_model':model,'key_present':key_present,'last_metered_response':live_model},'next':'A saved metered response is historical evidence, not a fresh API probe or proof of output quality.'},
      {'area':'Existing budget gate','state':'configured' if current and rate and current['start']<=time.time()<current['end'] and not current['hold'] else 'needs_configuration','evidence':{'active_period':bool(current),'confirmed_rate':bool(rate),'hold':bool(current and current['hold'])},'next':'The existing budget gate still checks remaining allowance before every paid request.'},
      {'area':'Twin coordination','state':'historically_observed' if cycle else 'not_verified','evidence':{'last_saved_cycle':cycle['finished_at'] if cycle else None},'next':'Complete a representative real assignment to establish end-to-end operation.'}]
    return {'version':VERSION,'checked_at':p.stamp(),'model_requests':0,'network_requests':0,'checks':checks,'employees':[{**r,'allowed_tools':json.loads(r['allowed_tools'])} for r in employees],'channels':[{k:v for k,v in c.items() if k!='last_error'}|{'latest_sync_failed':bool(c.get('last_error')),'evidence_state':'historically_synced' if c.get('last_sync') and not c.get('last_error') else 'configured_unverified' if c.get('connected') else 'not_configured'} for c in channels],'deferred_gaps':list(DEFERRED),'limitations':'Local saved-state assessment only. No live API, inbox sync, service restart or model request. No credentials or message bodies are included. Historical evidence does not prove current connectivity.'}

def capture(path=p.DEFAULT_DB):
    data=report(path)
    with p.connect(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS foundation_baselines(id INTEGER PRIMARY KEY AUTOINCREMENT,checked_at TEXT NOT NULL,report TEXT NOT NULL)')
        db.execute('INSERT INTO foundation_baselines(checked_at,report) VALUES(?,?)',(data['checked_at'],json.dumps(data)))
    return data
