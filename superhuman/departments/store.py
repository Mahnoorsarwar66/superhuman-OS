"""Read recorded state without initializing tables or creating workspace folders."""
from contextlib import contextmanager
from datetime import datetime,timezone
import json
from pathlib import Path
import sqlite3

BLOCKED={'quality_blocked','budget_blocked','dependency_blocked','plan_failed','failed','rejected','interrupted'}
ORDER=('endorsement','edsync_product','applications','investors_grants','legal_ops','career_rnd','marketing')

def departments():
    from superhuman.core.router import WORKSTREAMS
    keys=[k for k in ORDER if k in WORKSTREAMS]+[k for k in WORKSTREAMS if k not in ORDER and k!='writing']
    return [(k,WORKSTREAMS[k]['name']) for k in keys]

@contextmanager
def readonly(path):
    p=Path(path).resolve()
    if not p.is_file():yield None;return
    db=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,timeout=5)
    db.row_factory=sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        yield db
    finally:db.close()

def tables(db):
    return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} if db else set()

def rows(db,sql,args=()):return [dict(r) for r in db.execute(sql,args)]

def snapshot(scope,path=None):
    from superhuman.projects import engine as p
    from superhuman.core.router import WORKSTREAMS
    from superhuman.knowledge.store import default_path,today
    if scope not in WORKSTREAMS:raise ValueError('Unknown department')
    data=dict(scope=scope,name=WORKSTREAMS[scope]['name'],projects=[],tasks=[],conversations=[],areas=[],sources=[],suggestions=[],events=[],decisions=[],warnings=[])
    try:
        with readonly(path or p.DEFAULT_DB) as db:
            ts=tables(db)
            if 'projects' in ts:
                data['projects']=rows(db,'SELECT * FROM projects WHERE workstream=? ORDER BY updated_at DESC,id',(scope,))
                if 'project_tasks' in ts:
                    data['tasks']=rows(db,'SELECT t.*,p.objective AS project_title FROM project_tasks t JOIN projects p ON p.id=t.project_id WHERE p.workstream=? ORDER BY p.updated_at DESC,t.rowid',(scope,))
                if 'runtime_events' in ts:
                    data['events']=rows(db,'SELECT e.*,p.objective AS project_title FROM runtime_events e JOIN projects p ON p.id=e.project_id WHERE p.workstream=? ORDER BY e.seq DESC LIMIT 100',(scope,))
            if 'dialogue_threads' in ts:
                data['conversations']=rows(db,'SELECT * FROM dialogue_threads WHERE scope=? ORDER BY updated_at DESC,id',(scope,))
            if {'dialogue_suggestions','dialogue_threads'}<=ts:
                has_projects='projects' in ts;has_routes='dialogue_routes' in ts
                joins=(' LEFT JOIN projects p ON p.id=s.project_id' if has_projects else '')+(' LEFT JOIN dialogue_routes r ON r.suggestion_id=s.id' if has_routes else '')
                choices=(['p.workstream'] if has_projects else [])+(['r.scope'] if has_routes else [])+['c.scope']
                effective='COALESCE('+','.join(choices)+')' if len(choices)>1 else choices[0]
                data['suggestions']=rows(db,'SELECT s.*,c.title AS conversation_title FROM dialogue_suggestions s JOIN dialogue_threads c ON c.id=s.thread_id'+joins+' WHERE '+effective+'=? AND s.status=\'proposed\' ORDER BY s.created_at DESC,s.id',(scope,))
            if 'research_areas' in ts:
                data['areas']=rows(db,'SELECT * FROM research_areas WHERE scope=? ORDER BY updated_at DESC,id',(scope,))
                if 'research_sources' in ts:
                    data['sources']=rows(db,'SELECT s.*,a.title AS area_title FROM research_sources s JOIN research_areas a ON a.id=s.area_id WHERE a.scope=? ORDER BY s.updated_at DESC,s.id',(scope,))
    except sqlite3.Error:
        data['warnings'].append('Department records could not be read. Counts may be incomplete; check the existing project and task pages.')
    try:
        with readonly(default_path()) as db:
            if 'notes' in tables(db):
                data['decisions']=rows(db,"SELECT * FROM notes WHERE scope=? AND status='confirmed' AND kind='decision' AND sensitive=0 AND (expires_on='' OR expires_on>=?) ORDER BY updated_at DESC,id",(scope,today().isoformat()))
    except sqlite3.Error:data['warnings'].append('Saved decisions could not be read.')
    data['files'],data['exports'],warnings=materials(scope);data['warnings']+=warnings
    from superhuman.workspace.model import merge
    try:data=merge(data,path or p.DEFAULT_DB)
    except sqlite3.Error:data['warnings'].append('Managed project records could not be read. Counts may be incomplete.')
    tasks=data['tasks'];projects=data['projects']
    data['counts']={
      'projects':len(projects),'active_projects':sum(x['status']=='active' for x in projects),
      'tasks':len(tasks),'approved':sum(x['status']=='approved' for x in tasks),
      'running':sum(x['status']=='running' for x in tasks),'pending':sum(x['status']=='pending' for x in tasks),
      'outputs_review':sum(x['status']=='needs_review' for x in tasks),'plans_review':sum(x['status']=='plan_review' for x in projects),
      'blocked_tasks':sum(x['status'] in BLOCKED for x in tasks),'blocked_projects':sum(x['status'] in BLOCKED for x in projects),
      'suggestions':len(data['suggestions']),'conversations':len(data['conversations']),
      'areas':len(data['areas']),'sources':len(data['sources']),'files':len(data['files']),'exports':len(data['exports'])}
    data['next']=next_step(data)
    dates=[r.get('updated_at') or r.get('created_at') for key in ('projects','conversations','areas','sources','decisions','events') for r in data[key]]
    dates += [r.get('created_at') for r in data['exports']]
    data['last_update']=max((x for x in dates if x),default='No recorded activity')
    data['as_of']=datetime.now(timezone.utc).isoformat(timespec='seconds')
    return data

def materials(scope):
    from superhuman.capabilities import local
    files=[];exports=[];warnings=[]
    root=local.ROOT.resolve();folder=root/scope
    if folder.is_symlink() or not folder.resolve().is_relative_to(root):return [],[],['This workstream’s file folder could not be safely read.']
    inputs=folder/'inputs';out=folder/'exports'
    try:
        if inputs.is_symlink() or out.is_symlink():return [],[],['This workstream’s file folder could not be safely read.']
        if inputs.is_dir():
            for f in sorted(inputs.iterdir()):
                if not f.is_file() or f.is_symlink():continue
                try:local.valid_name(f.name)
                except ValueError:continue
                files.append({'name':f.name,'bytes':f.stat().st_size})
        if out.is_dir():
            for d in sorted(out.iterdir()):
                if not d.is_dir() or d.is_symlink():continue
                record=d/'record.json'
                if not record.is_file() or record.is_symlink() or record.stat().st_size>1_000_000:continue
                try:
                    r=json.loads(record.read_text(encoding='utf-8'))
                    if not isinstance(r,dict):raise ValueError('Invalid export record')
                    if r.get('project')!=scope or r.get('export_id')!=d.name:continue
                    # Download handler remains responsible for verifying file hashes.
                    exports.append({k:str(r.get(k,'')) for k in ('title','format','created_at','export_id')})
                except (ValueError,UnicodeError):warnings.append('An unreadable document record was omitted.')
    except OSError:warnings.append('Some workspace files could not be listed.')
    return files,sorted(exports,key=lambda r:r['created_at'],reverse=True),warnings

def next_step(data):
    scope=data['scope']
    for p in data['projects']:
        if p['status']=='plan_review':return ('Review the prepared plan: '+p['objective'],p.get('url','/work/'+p['id']))
    for t in data['tasks']:
        if t['status']=='needs_review':return ('Review the completed draft: '+t['title'],t.get('url','/projects/'+t['project_id']))
    for t in data['tasks']:
        if t['status'] in BLOCKED:return ('Inspect the blocked task: '+t['title'],t.get('url','/projects/'+t['project_id']))
    for p in data['projects']:
        if p['status'] in BLOCKED:return ('Inspect the blocked objective: '+p['objective'],p.get('url','/work/'+p['id']))
    if data['suggestions']:return ('Review a proposed task: '+data['suggestions'][0]['title'],'/talk/'+data['suggestions'][0]['thread_id'])
    for p in data['projects']:
        if p['status']=='new':return ('Review the objective and request a plan: '+p['objective'],p.get('url','/work/'+p['id']))
    if data['counts']['running']:return ('Check the work currently running.','/departments/'+scope+'/projects')
    if data['projects']:return ('Review project progress and choose the next priority.','/departments/'+scope+'/projects')
    return ('Create the first objective for this department.','/projects?workstream='+scope+'#new-project')
