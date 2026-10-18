"""Deduplicated research work uses existing employee tasks and execution budgets."""
import json
from uuid import uuid4
from superhuman.projects import engine as p
from superhuman.team import store as team
from superhuman.milestones import store as ms,workflow as mw
from . import store as s

def open_gap(mid,key,question,employee,critical,sensitivity,actor='owner',path=p.DEFAULT_DB):
    m=s.authority(mid,actor,path)
    key=team.text(key,100,'Gap key',True);question=team.text(question,2000,'Research question',True)
    if employee not in json.loads(m['workers']) or employee=='twin':raise ValueError('Choose a specialist on this milestone working team')
    if type(critical) is not bool or sensitivity not in team.SENSITIVITIES:raise ValueError('Choose valid investigation controls')
    floor=team.project(m['project_id'],path)['sensitivity']
    if team.SENSITIVITIES.index(sensitivity)<team.SENSITIVITIES.index(floor):raise ValueError('Investigation cannot be less private than the project')
    ident=uuid4().hex
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT * FROM assurance_gaps WHERE mid=? AND gap_key=?',(mid,key)).fetchone()
        if old:
            if (old['question'],old['employee'],old['critical'],old['sensitivity'])!=(question,employee,int(critical),sensitivity):raise ValueError('Gap key already has different content')
            return old['id']
        if db.execute('SELECT COUNT(*) FROM assurance_gaps WHERE mid=?',(mid,)).fetchone()[0]>=24:raise ValueError('Investigation limit reached')
        db.execute('INSERT INTO assurance_gaps(id,mid,gap_key,question,employee,critical,sensitivity,created_at) VALUES(?,?,?,?,?,?,?,?)',(ident,mid,key,question,employee,int(critical),sensitivity,p.stamp()))
        s.touch(db,mid,actor,'gap_opened',{'id':ident,'question':question})
    from .workflow import changed
    changed(mid,'gap:'+ident,'A research gap was identified after packet assembly',path=path)
    return ident

def dispatch(mid,path=p.DEFAULT_DB):
    m=ms.milestone(mid,path)
    if m['state']!='working' or not ms.active(mid,path)[0]:return None
    for gap in s.gaps(mid,path):
        if gap['state']!='open':continue
        with p.connect(path) as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT * FROM assurance_gaps WHERE id=?',(gap['id'],)).fetchone()
            if current['state']!='open':continue
            lead=next(a for a in ms.assignments(mid,path) if a['role']=='lead')
            t=dict(db.execute('SELECT * FROM team_tasks WHERE id=?',(lead['task_id'],)).fetchone())
            if t['state'] in ('awaiting_review','completed'):raise ValueError('Completed integration requires an owner revision before adding investigation dependencies')
            if t['run_id'] and db.execute('SELECT state FROM agentic_runs WHERE project_id=?',(t['run_id'],)).fetchone()['state']=='running':return None
            tid=ms.create_assignment(mid,gap['employee'],'Research gap · '+gap['gap_key'],gap['question']+'\nInvestigate independently within current tools and approved sources. Distinguish sourced facts, inference and unresolved questions. Return precise citations, source limitations and a concrete recommendation. Do not invent evidence or claim external action.','A source-backed answer to the gap, with remaining uncertainties and verification needs.',path=path,_db=db,sensitivity_override=gap['sensitivity'])
            deps=list(dict.fromkeys(json.loads(t['deps'])+[tid]))
            db.execute('UPDATE team_tasks SET deps=?,version=version+1 WHERE id=?',(json.dumps(deps),t['id']))
            db.execute("UPDATE assurance_gaps SET state='assigned',task_id=?,version=version+1 WHERE id=?",(tid,gap['id']))
            s.audit(db,mid,ms.managed(m['project_id'],path)['lead'],'investigation_assigned',{'gap_id':gap['id'],'task_id':tid})
        return tid
    return None

def accepted_task(tid,approve,note,actor,path=p.DEFAULT_DB):
    rows=s.records('assurance_gaps','SELECT * FROM assurance_gaps WHERE task_id=?',(tid,),path)
    if not rows:return
    gap=rows[0]
    if approve:mw.result(tid,path)
    with p.connect(path) as db:
        db.execute('UPDATE assurance_gaps SET state=?,note=?,version=version+1 WHERE id=?',('resolved' if approve else 'assigned',note,gap['id']))
        s.touch(db,gap['mid'],actor,'investigation_reviewed',{'id':gap['id'],'accepted':approve,'note':note})


def deferred_gap(ident,expected,note,path=p.DEFAULT_DB):
    rows=s.records('assurance_gaps','SELECT * FROM assurance_gaps WHERE id=?',(ident,),path)
    if not rows:raise ValueError('Gap not found')
    gap=rows[0];note=team.text(note,2000,'Deferral reason',True)
    if gap['critical'] or gap['task_id']:raise ValueError('Only an unassigned noncritical gap can be deferred; critical gaps require investigation')
    with p.connect(path) as db:
        if not db.execute("UPDATE assurance_gaps SET state='deferred',note=?,version=version+1 WHERE id=? AND version=?",(note,ident,expected)).rowcount:raise ValueError('Gap changed')
        s.touch(db,gap['mid'],'owner','gap_deferred',{'id':ident,'note':note})

def retry(ident,expected,note,path=p.DEFAULT_DB):
    row=s.records('assurance_gaps','SELECT * FROM assurance_gaps WHERE id=?',(ident,),path)
    if not row or row[0]['state']!='needs_owner' or row[0]['task_id']:raise ValueError('Choose an unassigned investigation awaiting owner inspection')
    note=team.text(note,2000,'Inspection decision',True)
    with p.connect(path) as db:
        if not db.execute("UPDATE assurance_gaps SET state='open',note=?,version=version+1 WHERE id=? AND version=? AND state='needs_owner'",(note,ident,expected)).rowcount:raise ValueError('Investigation changed; reload')
        s.audit(db,row[0]['mid'],'owner','investigation_retry_authorised',{'id':ident,'note':note})
