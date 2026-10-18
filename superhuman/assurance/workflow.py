"""Freshness gates, impact propagation and explicit owner reopening."""
import hashlib,json
from uuid import uuid4
from superhuman.projects import engine as p
from superhuman.team import store as team,work
from superhuman.milestones import store as ms
from . import store as s,evidence as ev

def descendants(mid,path=p.DEFAULT_DB):
    m=ms.milestone(mid,path);all_ms=ms.listing(m['project_id'],path);found={mid}
    while True:
        more={row['id'] for row in all_ms if set(json.loads(row['deps']))&found}
        if more<=found:break
        found|=more
    return [row['id'] for row in all_ms if row['id'] in found]

def changed(mid,key,reason,force=False,path=p.DEFAULT_DB):
    if not s.policy(mid,path):return None
    m=ms.milestone(mid,path)
    if not force and (not m['current_packet'] or m['state'] in ('working','lead_review')):return None
    affected=descendants(mid,path);ident=uuid4().hex
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT id FROM assurance_changes WHERE origin_mid=? AND change_key=?',(mid,key)).fetchone()
        if old:return old['id']
        db.execute('INSERT INTO assurance_changes(id,origin_mid,change_key,reason,affected,created_at) VALUES(?,?,?,?,?,?)',(ident,mid,key,team.text(reason,2000,'Change reason',True),json.dumps(affected),p.stamp()))
        for target in affected:
            db.execute('UPDATE assurance_milestones SET version=version+1 WHERE mid=?',(target,))
            s.audit(db,target,'system','change_detected',{'change_id':ident,'origin':mid,'reason':reason})
    return ident

def block_reason(mid,path=p.DEFAULT_DB):
    if not s.policy(mid,path):return ''
    m=ms.milestone(mid,path)
    for c in s.changes(m['project_id'],path):
        if c['state']=='open' and mid in json.loads(c['affected']):return 'An upstream decision or evidence changed; owner impact inspection and reopening are required'
    return ''

def reconcile(mid,path=p.DEFAULT_DB):
    if not s.policy(mid,path):return
    for row in s.evidence(mid,path):
        if row['status'] in ('accepted','contested'):
            health=ev.health(row,mid,path)
            if health!='Current':changed(mid,'stale:'+row['id']+':'+str(row['source_version']),health,force=True,path=path)

def fingerprint(mid,path=p.DEFAULT_DB):
    m=ms.milestone(mid,path)
    payload={'scope':{k:m[k] for k in ('question','criteria','workers','reviewers','deps')},'policy':s.policy(mid,path),'requirements':s.requirements(mid,path),'rubric':s.rubric(mid,path),'evidence':s.evidence(mid,path),'gaps':s.gaps(mid,path)}
    from superhuman.practice.store import signature
    interview_signature=signature(m['project_id'],path)
    if interview_signature!='legacy':payload['project_interview']=interview_signature
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()

def gate(mid,packet=False,path=p.DEFAULT_DB):
    cfg=s.policy(mid,path)
    if not cfg:return
    reconcile(mid,path)
    if block_reason(mid,path):raise ValueError(block_reason(mid,path))
    if cfg['legacy'] and ms.milestone(mid,path)['state']=='approved':return
    if not cfg['register_confirmed']:raise ValueError('The owner must confirm the requirement register scope, including an explicit reason if no separate requirements are needed')
    lead=next((a for a in ms.assignments(mid,path) if a['role']=='lead'),None)
    if lead:
        ceiling=team.effective(team.task(lead['task_id'],path),path)['sensitivity']
        levels=[r['sensitivity'] for r in s.requirements(mid,path)]+[e['sensitivity'] for e in s.evidence(mid,path) if e['status']!='rejected']
        if any(team.SENSITIVITIES.index(level)>team.SENSITIVITIES.index(ceiling) for level in levels):raise ValueError('The evidence register is more private than its integration task; raise task controls and inspect public-web permissions before continuation')
    current=[e for e in s.evidence(mid,path) if e['status']=='accepted' and ev.health(e,mid,path)=='Current']
    for req in s.requirements(mid,path):
        if req['critical'] and any(e['requirement_id']==req['id'] and e['status']=='contested' for e in s.evidence(mid,path)):raise ValueError('Critical requirement has contested evidence: '+req['title'][:120])
        if req['critical'] and not any(e['requirement_id']==req['id'] for e in current):raise ValueError('Critical requirement lacks accepted current evidence: '+req['title'][:120])
    if any(g['critical'] and g['state']!='resolved' for g in s.gaps(mid,path)):raise ValueError('Critical research gaps remain unresolved')
    if packet:
        current=ms.packet(mid,path)
        saved=s.records('assurance_packets','SELECT * FROM assurance_packets WHERE packet_id=?',(current['id'] if current else '',),path)
        if not saved or saved[0]['fingerprint']!=fingerprint(mid,path):raise ValueError('The evidence/register changed after packet assembly; reopen and assemble a fresh packet')

def freeze(mid,path=p.DEFAULT_DB):
    if not s.policy(mid,path):return
    packet=ms.packet(mid,path)
    with p.connect(path) as db:db.execute('INSERT INTO assurance_packets VALUES(?,?,?)',(packet['id'],fingerprint(mid,path),p.stamp()))

def scores(mid,packet_id,actor,path=p.DEFAULT_DB):
    rows=s.records('assurance_scorecards','SELECT * FROM assurance_scorecards WHERE mid=? AND packet_id=? AND actor=? AND fingerprint=?',(mid,packet_id,actor,fingerprint(mid,path)),path)
    return rows[0] if rows else None

def scorecard(mid,packet_id,digest,values,actor,path=p.DEFAULT_DB):
    s.authority(mid,actor,path);m=ms.milestone(mid,path);packet=ms.packet(mid,path)
    if not packet or packet['id']!=packet_id or packet['digest']!=digest:raise ValueError('Score the exact current packet')
    reviewers=json.loads(m['reviewers'])
    if actor!='twin' and actor not in reviewers:raise ValueError('Only assigned independent reviewers and The Twin can record scorecards')
    if actor=='twin' and m['state']!='twin_review':raise ValueError('The Twin scorecard belongs at the Twin review stage')
    if actor!='twin' and not any(a['role']=='reviewer' and a['owner']==actor and a['packet_version']==packet['version'] for a in ms.assignments(mid,path)):raise ValueError('This specialist has no current-packet review assignment')
    if not isinstance(values,list) or len(values)!=len(s.rubric(mid,path)):raise ValueError('Score every rubric criterion exactly once')
    expected={r['criterion'] for r in s.rubric(mid,path)};seen=set()
    for value in values:
        if not isinstance(value,dict) or set(value)!={'criterion','verdict','rationale'} or value['criterion'] not in expected or value['criterion'] in seen or value['verdict'] not in ('pass','revise','fail'):raise ValueError('Invalid or duplicate scorecard criterion')
        seen.add(value['criterion']);team.text(value['rationale'],1000,'Criterion rationale',True)
    gate(mid,packet=True,path=path)
    fp=fingerprint(mid,path);ident=uuid4().hex
    with p.connect(path) as db:
        old=db.execute('SELECT * FROM assurance_scorecards WHERE mid=? AND packet_id=? AND actor=? AND fingerprint=?',(mid,packet_id,actor,fp)).fetchone()
        if old:
            if json.loads(old['scores'])!=values:raise ValueError('This scorecard is immutable; revise the packet before rescoring')
            return old['id']
        db.execute('INSERT INTO assurance_scorecards VALUES(?,?,?,?,?,?,?)',(ident,mid,packet_id,actor,fp,json.dumps(values),p.stamp()))
        s.audit(db,mid,actor,'scorecard_recorded',{'id':ident,'packet_id':packet_id})
    return ident

def quality_gate(mid,twin=False,path=p.DEFAULT_DB):
    if not s.policy(mid,path):return
    gate(mid,packet=True,path=path);m=ms.milestone(mid,path);packet=ms.packet(mid,path)
    for actor in json.loads(m['reviewers'])+(['twin'] if twin else []):
        saved=scores(mid,packet['id'],actor,path)
        if not saved or any(v['verdict']!='pass' for v in json.loads(saved['scores'])):raise ValueError('Current packet needs a passing scorecard from '+team.EMPLOYEES[actor][0])

def reopen(ident,expected,note,path=p.DEFAULT_DB):
    rows=s.records('assurance_changes','SELECT * FROM assurance_changes WHERE id=?',(ident,),path)
    if not rows or rows[0]['state']!='open' or rows[0]['version']!=expected:raise ValueError('Change decision changed; reload')
    c=rows[0];note=team.text(note,2000,'Owner impact decision',True);targets=json.loads(c['affected'])
    # Only explicit owner action can invalidate accepted work. History is retained.
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        for mid in targets:
            m=ms.milestone(mid,path)
            leads=[a for a in ms.assignments(mid,path) if a['role']=='lead']
            if leads:
                lead=leads[0];task=team.task(lead['task_id'],path)
                if task['run_id']:
                    run=db.execute('SELECT state FROM agentic_runs WHERE project_id=?',(task['run_id'],)).fetchone()
                    if run and run['state']=='running':raise ValueError('Pause active execution before reopening affected work')
                if m['current_packet'] and task['state'] in ('completed','awaiting_review'):
                    # Reopening withdraws acceptance; it is not approval of stale evidence.
                    # Keep packet history, action ledger and the same budget/request ceilings.
                    db.execute("UPDATE project_tasks SET status='pending',review_note=?,token=NULL,error=NULL WHERE project_id=? AND id='final'",('Owner impact revision: '+note,task['run_id']))
                    db.execute("UPDATE projects SET status='active',updated_at=? WHERE id=?",(p.stamp(),task['run_id']))
                    db.execute("UPDATE agentic_runs SET state='ready',failures=0,version=version+1 WHERE project_id=?",(task['run_id'],))
                    db.execute("UPDATE team_tasks SET state='dispatched',attempts=attempts+1,version=version+1,updated_at=? WHERE id=? AND version=?",(p.stamp(),task['id'],task['version']))
                    from superhuman.agentic import store as agent
                    agent.event(db,task['run_id'],'resume',{'actor':'owner','note':'Impact revision: '+note})
            if m['state']!='planned':db.execute("UPDATE milestones SET state='working',criteria_confirmed=0,revision_count=0,version=version+1 WHERE id=?",(mid,))
            db.execute('UPDATE assurance_milestones SET register_confirmed=0,legacy=0,version=version+1 WHERE mid=?',(mid,))
            s.audit(db,mid,'owner','reopened_for_change',{'change_id':ident,'note':note,'prior_packet':m['current_packet']})
        if not db.execute("UPDATE assurance_changes SET state='applied',resolution=?,version=version+1 WHERE id=? AND version=? AND state='open'",(note,ident,expected)).rowcount:raise ValueError('Change decision changed')
        pid=ms.milestone(c['origin_mid'],path)['project_id'];db.execute("UPDATE milestone_projects SET last_signature='',next_due=0 WHERE project_id=?",(pid,))
    work.refresh(path)

def execution_block(mid,path=p.DEFAULT_DB):
    if not s.policy(mid,path):return ''
    m=ms.milestone(mid,path)
    for other in ms.listing(m['project_id'],path):reconcile(other['id'],path)
    return block_reason(mid,path)

def check_reviewer(tid,path=p.DEFAULT_DB):
    a=ms.assignment(tid,path)
    if not a or a['role']!='reviewer' or not s.policy(a['milestone_id'],path):return
    mid=a['milestone_id'];packet=ms.packet(mid,path);actor=team.task(tid,path)['owner'];saved=scores(mid,packet['id'],actor,path)
    if not saved:raise ValueError('The specialist must record a complete scorecard for this exact packet before critique acceptance')

def change_criteria(mid,expected,question,criteria,note,path=p.DEFAULT_DB):
    m=s.require_policy(mid,path);question=team.text(question,1200,'Question',True);criteria=team.text(criteria,3500,'Criteria',True);note=team.text(note,2000,'Scope change reason',True)
    with p.connect(path) as db:
        if not db.execute('UPDATE milestones SET question=?,criteria=?,criteria_confirmed=0,version=version+1 WHERE id=? AND version=?',(question,criteria,mid,expected)).rowcount:raise ValueError('Milestone changed; reload')
        s.touch(db,mid,'owner','scope_changed',{'old_question':m['question'],'old_criteria':m['criteria'],'question':question,'criteria':criteria,'note':note})
    changed(mid,'scope:'+str(expected+1),'Owner changed the milestone question or acceptance criteria: '+note,force=bool(m['current_packet']),path=path)

def maintenance(path=p.DEFAULT_DB):
    if not s.installed(path):return None
    from .investigations import accepted_task
    for m in ms.listing(path=path):
        reconcile(m['id'],path)
        for gap in s.gaps(m['id'],path):
            if gap['state']=='assigned' and gap['task_id'] and team.task(gap['task_id'],path)['state']=='completed':
                rows=s.records('milestone_reviews',"SELECT actor,note FROM milestone_reviews WHERE milestone_id=? AND decision='contribution_accepted' ORDER BY created_at DESC",(m['id'],),path)
                if rows:accepted_task(gap['task_id'],True,rows[0]['note'],rows[0]['actor'],path)
    return None

def dispatch_one(path=p.DEFAULT_DB):
    if not s.installed(path):return None
    from .investigations import dispatch
    for m in ms.listing(path=path):
        try:tid=dispatch(m['id'],path)
        except ValueError as exc:
            for g in s.gaps(m['id'],path):
                if g['state']=='open':
                    with p.connect(path) as db:
                        db.execute("UPDATE assurance_gaps SET state='needs_owner',note=?,version=version+1 WHERE id=? AND state='open'",(str(exc)[:1000],g['id']))
                        s.audit(db,m['id'],'system','investigation_held',{'gap_id':g['id'],'reason':str(exc)[:1000]})
                    return {'team_cycle_id':'gap-hold:'+g['id'],'status':'needs_owner'}
            continue
        if tid:return {'team_cycle_id':'gap:'+tid,'status':'investigation_assigned'}
    return None
