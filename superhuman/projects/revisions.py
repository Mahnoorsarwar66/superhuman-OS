"""Local draft revision, validation and audit history. No model/API requests."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4
from . import engine as e

COMMANDS={'export','check','revise','revalidate','history'}
EDITABLE={'quality_blocked','needs_review','approved','rejected'}

def initialize(path=e.DEFAULT_DB):
    e.initialize(path)
    with e.connect(path) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS project_revisions(
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, task_id TEXT NOT NULL,
        action TEXT NOT NULL, note TEXT NOT NULL, old_output TEXT, new_output TEXT,
        old_hash TEXT, new_hash TEXT, invalidated_json TEXT NOT NULL,
        errors_json TEXT NOT NULL, created_at TEXT NOT NULL)''')

def load(pid,tid,path=e.DEFAULT_DB):
    project=e.get(pid,path)
    task=next((t for t in project['tasks'] if t['id']==tid),None)
    if not task:raise ValueError('Task not found')
    if task['status'] not in EDITABLE or not task['result_json']:
        raise ValueError('Task must have a reviewable, blocked or rejected draft')
    result=json.loads(task['result_json'])
    output,text=e._text(result)  # Reject tampering with the stored artifact.
    return project,task,result,output,text

def checks_for(task,max_words=None):
    checks=json.loads(task['checks'])
    if max_words is not None:
        if type(max_words) is not int or not 1<=max_words<=5000:
            raise ValueError('max_words must be 1 to 5000')
        checks['max_words']=min(max_words,checks.get('max_words',max_words))
    return checks

def assess(project,task,result,text,max_words=None):
    checks=checks_for(task,max_words)
    forbid='Prose punctuation preference' in e.identity(project['workstream'])
    # current-text-quality-v14: generation findings describe the old text.
    from superhuman.collab.reliability import validate_final
    current=dict(result);current.pop('quality_report',None)
    errors=e.quality(current,text,checks,task['kind'],forbid_dashes=forbid)
    for issue in validate_final(text,checks,forbid)['errors']:
        if issue not in errors:errors.append(issue)
    # Keep this check independent of an older engine punctuation implementation.
    if forbid and re.search(r'(?<=\S)[ \t]+[\u2014\u2013-][ \t]+(?=\S)',text):
        message='Dash clause separator violates saved preference'
        if message not in errors:errors.append(message)
    return {'passes':not errors,'errors':errors,'word_count':len(text.split()),'checks':checks}

def read_revision(file):
    p=Path(file)
    if not p.is_file() or p.stat().st_size>2_000_000:
        raise ValueError('Provide an existing UTF-8 text file under 2 MB')
    text=p.read_text(encoding='utf-8-sig').strip()
    if not text:raise ValueError('Revision cannot be empty')
    # The runner extractor uses these strings as wrapper delimiters. Treat the
    # edited file as plain deliverable text, not as a whole runner report.
    if '## Revised deliverable' in text or re.search(r'^---\s*$',text,re.M):
        raise ValueError('Use exported deliverable text only; omit report wrappers and horizontal rules')
    return text+'\n'

def export(pid,tid,file=None,path=e.DEFAULT_DB):
    _,task,_,_,text=load(pid,tid,path)
    target=Path(file) if file else e.OUTPUT_ROOT/pid/tid/'revisions'/('edit_'+uuid4().hex[:8]+'.txt')
    target.parent.mkdir(parents=True,exist_ok=True)
    # Never overwrite an existing editable file, including user edits.
    with target.open('x',encoding='utf-8') as f:f.write(text.strip()+'\n')
    return {'file':str(target.resolve()),'task_status':task['status'],'api_calls':0}

def check(pid,tid,file,max_words=None,path=e.DEFAULT_DB):
    project,task,result,_,_=load(pid,tid,path)
    return assess(project,task,result,read_revision(file),max_words)

def descendants(tasks,tid):
    affected={tid}
    while True:
        new={t['id'] for t in tasks if set(json.loads(t['deps'])) & affected}
        if new<=affected:return affected-{tid}
        affected|=new

def commit(project,task,result,text,note,action,assessment,path,output=None):
    if not note.strip() or len(note)>2000:raise ValueError('Provide a revision/revalidation note <=2000 characters')
    initialize(path)
    pid=project['id'];tid=task['id'];rid=uuid4().hex[:12]
    new_output=output or task['output']
    content_hash=hashlib.sha256(text.encode()).hexdigest()
    new_result=dict(result)
    if 'quality_report' in result and 'original_generation_quality_report' not in result:
        new_result['original_generation_quality_report']=result['quality_report']
    new_result['quality_report']={'passes':assessment['passes'],'errors':assessment['errors'],
        'word_count':assessment['word_count'],'factual_accuracy':'Not independently verified',
        'basis':'Current local text checks'}
    new_result.update(output=str(new_output),content_sha256=content_hash,
        project_quality_checks=assessment['errors'],status='needs_review' if assessment['passes'] else 'quality_blocked')
    new_result['local_revision']={'id':rid,'action':action,'note':note,'api_calls':0,'created_at':e.stamp()}
    status='needs_review' if assessment['passes'] else 'quality_blocked'
    # Revalidation does not revoke existing approval when content and checks pass.
    if action=='revalidate' and assessment['passes'] and task['status']=='approved':status='approved'
    with e.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        rows=[dict(r) for r in db.execute('SELECT * FROM project_tasks WHERE project_id=?',(pid,))]
        current=next(r for r in rows if r['id']==tid)
        if any(t['status']=='running' for t in rows):raise ValueError('Stop/wait for running project tasks before revision')
        if current['status']!=task['status'] or current['result_json']!=task['result_json']:
            raise ValueError('Task changed; reload before applying revision')
        invalidated=[]
        must_invalidate=action=='revise' or not assessment['passes']
        if must_invalidate:
            affected=descendants(rows,tid)
            for row in rows:
                if row['id'] in affected:
                    invalidated.append({'id':row['id'],'status':row['status'],'output':row['output'],'result_json':row['result_json']})
                    db.execute("UPDATE project_tasks SET status='pending',token=NULL,started=NULL,output=NULL,result_json=NULL,error=NULL,review_note=NULL WHERE project_id=? AND id=?",(pid,row['id']))
        db.execute('''UPDATE project_tasks SET status=?,output=?,result_json=?,checks=?,error=?,review_note=?
            WHERE project_id=? AND id=?''',(status,str(new_output),json.dumps(new_result),json.dumps(assessment['checks']),
            '; '.join(assessment['errors']) or None,'Local '+action+': '+note,pid,tid))
        if tid=='final':
            pstatus='approved' if status=='approved' else 'needs_review' if assessment['passes'] else 'active'
            db.execute('UPDATE projects SET status=?,updated_at=? WHERE id=?',(pstatus,e.stamp(),pid))
        elif must_invalidate or project['status'] in ('dependency_blocked','rejected'):
            db.execute("UPDATE projects SET status='active',updated_at=? WHERE id=?",(e.stamp(),pid))
        db.execute('INSERT INTO project_revisions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
            (rid,pid,tid,action,note,task['output'],str(new_output),result.get('content_sha256'),content_hash,
             json.dumps(invalidated),json.dumps(assessment['errors']),e.stamp()))
    return {'revision_id':rid,'task_status':status,'output':str(new_output),
            'invalidated_tasks':[r['id'] for r in invalidated],**assessment,'api_calls':0,
            'used_calls':e.get(pid,path)['used_calls']}

def revise(pid,tid,file,note,max_words=None,path=e.DEFAULT_DB):
    project,task,result,_,old_text=load(pid,tid,path)
    if not note.strip():raise ValueError('A revision note is required')
    if any(t['status']=='running' for t in project['tasks']):raise ValueError('Wait for project worker to stop')
    text=read_revision(file)
    assessment=assess(project,task,result,text,max_words)
    if not assessment['passes']:
        return {'applied':False,**assessment,'api_calls':0,'used_calls':project['used_calls']}
    revision_id=uuid4().hex[:12]
    destination=e.OUTPUT_ROOT/pid/tid/'revisions'/revision_id/'revised.md'
    destination.parent.mkdir(parents=True,exist_ok=True)
    wrapper=(f'# {task["title"]}\n\n**Status:** needs_review\n'
             '**Preparation:** local revision; no API calls\n\n## Revised deliverable\n\n'+text)
    destination.write_text(wrapper,encoding='utf-8')
    new_result=dict(result);new_result.pop('content_sha256',None);new_result['output']=str(destination)
    _,actual=e._text(new_result)
    try:return {'applied':True,**commit(project,task,result,actual,note,'revise',assessment,path,str(destination.resolve()))}
    except Exception:
        destination.unlink(missing_ok=True)
        raise

def revalidate(pid,tid,note,max_words=None,path=e.DEFAULT_DB):
    project,task,result,_,text=load(pid,tid,path)
    assessment=assess(project,task,result,text,max_words)
    return commit(project,task,result,text,note,'revalidate',assessment,path)

def history(pid,tid,path=e.DEFAULT_DB):
    initialize(path)
    with e.connect(path) as db:
        return [dict(r) for r in db.execute('SELECT * FROM project_revisions WHERE project_id=? AND task_id=? ORDER BY created_at',(pid,tid))]

def add_parsers(sub):
    for name in sorted(COMMANDS):
        p=sub.add_parser(name);p.add_argument('id');p.add_argument('task')
        if name=='export':p.add_argument('--file')
        if name in ('check','revise'):p.add_argument('--file',required=True)
        if name in ('check','revise','revalidate'):p.add_argument('--max-words',type=int)
        if name in ('revise','revalidate'):p.add_argument('--note',required=True)

def dispatch(a,path):
    if a.cmd=='export':return export(a.id,a.task,a.file,path)
    if a.cmd=='check':return check(a.id,a.task,a.file,a.max_words,path)
    if a.cmd=='revise':return revise(a.id,a.task,a.file,a.note,a.max_words,path)
    if a.cmd=='revalidate':return revalidate(a.id,a.task,a.note,a.max_words,path)
    if a.cmd=='history':return history(a.id,a.task,path)
    raise ValueError('Unknown revision command')

def main():
    import argparse
    p=argparse.ArgumentParser(description='Superhuman local revisions, zero API calls')
    p.add_argument('--db',default=str(e.DEFAULT_DB))
    sub=p.add_subparsers(dest='cmd',required=True);add_parsers(sub)
    a=p.parse_args();print(json.dumps(dispatch(a,Path(a.db)),indent=2))

if __name__=='__main__':main()
