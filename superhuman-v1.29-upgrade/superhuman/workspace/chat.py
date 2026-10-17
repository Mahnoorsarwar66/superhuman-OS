"""Context additions and explicit, versioned conversation corrections."""
import json,time,hashlib
from superhuman.projects import engine as p
from superhuman.team import store as team
from superhuman.experience import store as ux
from superhuman.dialogue import store as d

def communications(path=p.DEFAULT_DB):
    """Only summaries whose entire source set is still consented and unchanged."""
    from superhuman.comms import store as comms
    summaries=[]
    with p.connect(path) as db:
        from superhuman.departments.store import tables
        if not {'comms_runs','comms_sources','comms_channels'}<=tables(db):return []
        for run in comms.runs(path):
            if run['status']!='done':continue
            try:snapshot=json.loads(run['snapshot']);result=json.loads(run['result'] or '{}')
            except (ValueError,TypeError):continue
            allowed=True
            for alias in snapshot.get('aliases',{}).values():
                source=db.execute('SELECT * FROM comms_sources WHERE id=?',(alias['source_id'],)).fetchone()
                channel=db.execute('SELECT * FROM comms_channels WHERE id=?',(alias['channel_id'],)).fetchone()
                if not source or not channel or not channel['ai_enabled'] or source['digest']!=alias['digest'] or not comms.source_allowed(source,channel,db):allowed=False;break
            if not allowed:continue
            summaries.append({'id':run['id'],'saved_at':run['finished_at'],'summary':result.get('summary',''),'items':result.get('items',[])})
            if len(summaries)>=3:break
    return summaries

def augment(claimed,messages,trace,path=p.DEFAULT_DB):
    r=ux.room(claimed['thread_id'],path)
    if not r:return messages,trace
    # A project room deliberately excludes global/private inbox context.
    summaries=communications(path) if r['employee']=='twin' and not r['project_id'] else []
    if summaries:messages.insert(2,{'role':'user','content':'SAVED COMMUNICATIONS SUMMARIES (data, may be incomplete; no live fetch):\n'+json.dumps(summaries,ensure_ascii=False)})
    proposals=[{k:s[k] for k in ('id','title','status')} for s in d.suggestions(claimed['thread_id'],path)[-15:]]
    messages.insert(2,{'role':'user','content':'SAVED PROPOSAL STATES (data, no action authority):\n'+json.dumps(proposals,ensure_ascii=False)})
    trace=dict(trace,communications_signature=hashlib.sha256(json.dumps(summaries,sort_keys=True).encode()).hexdigest() if summaries else '',context_summary_ids=[s['id'] for s in summaries])
    return messages,trace

def validate(claimed,trace,path=p.DEFAULT_DB):
    if trace.get('communications_signature'):
        current=hashlib.sha256(json.dumps(communications(path),sort_keys=True).encode()).hexdigest()
        if current!=trace['communications_signature']:raise ValueError('Communications consent or source context changed during reply; review before requesting another reply')

def relocate(ident,expected,kind,pid,confirmed=False,path=p.DEFAULT_DB):
    if type(confirmed) is not bool or not confirmed:raise ValueError('Confirm that the entire conversation belongs to the destination')
    target=ux.project(kind,pid,path) if kind else None
    if bool(kind)!=bool(pid):raise ValueError('Choose a complete project destination')
    ux.initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');r=db.execute('SELECT * FROM ux_rooms WHERE thread_id=?',(ident,)).fetchone()
        if not r or r['version']!=expected:raise ValueError('Conversation changed; reload')
        if db.execute("SELECT 1 FROM dialogue_turns WHERE thread_id=? AND status IN ('queued','running')",(ident,)).fetchone():raise ValueError('Wait for or cancel the pending reply before moving this conversation')
        if db.execute("SELECT 1 FROM dialogue_suggestions WHERE thread_id=? AND status='proposed'",(ident,)).fetchone():raise ValueError('Resolve or dismiss proposed work before moving the conversation')
        if target and r['employee'] not in ('twin',target['scope']):raise ValueError('Choose a project in the same employee department')
        old_scope=db.execute('SELECT scope FROM dialogue_threads WHERE id=?',(ident,)).fetchone()['scope']
        if target and target['scope']!=old_scope:raise ValueError('Moving history across departments is not supported; start a new room')
        db.execute('UPDATE ux_rooms SET project_kind=?,project_id=?,version=version+1 WHERE thread_id=?',(kind,pid,ident))
        d.event(db,'conversation_destination_corrected',ident,project_id=pid or None,previous_project=r['project_id'])

def approve(sid,expected,pid,title,instruction,risk,sensitivity,acceptance,share_confirmed=False,start=False,path=p.DEFAULT_DB):
    team.classification('P2',risk,sensitivity);instruction=team.text(instruction,5000,'Instructions',True);acceptance=team.text(acceptance,1500,'Acceptance criteria',True)
    ux.initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');s=db.execute('SELECT s.*,r.employee,r.project_kind,r.project_id AS room_project FROM dialogue_suggestions s JOIN ux_rooms r ON r.thread_id=s.thread_id WHERE s.id=?',(sid,)).fetchone()
        if not s or s['proposal_hash']!=expected:raise ValueError('Suggestion changed; reload')
        digest=hashlib.sha256(json.dumps([pid,title,instruction,risk,sensitivity,acceptance,bool(start)],ensure_ascii=False).encode()).hexdigest()
        old=db.execute('SELECT task_id FROM ux_suggestion_tasks WHERE suggestion_id=?',(sid,)).fetchone()
        if old:
            if s['approved_hash']!=digest:raise ValueError('Already approved with different details; open the existing task')
            return old['task_id']
        if s['status']!='proposed':raise ValueError('Suggestion is no longer proposed')
        target=team.project(pid,path)
        if target['status']!='active':raise ValueError('Choose an active project')
        if s['project_kind']=='team' and s['room_project']!=pid:raise ValueError('Project proposals stay with their linked project')
        if s['project_kind']=='canonical':raise ValueError('Create a managed project from this earlier work before adding employee tasks')
        employee=target['scope'] if s['employee']=='twin' else s['employee']
        if employee!=target['scope']:raise ValueError('Choose this employee’s department')
        if team.RISKS.index(risk)<team.RISKS.index(target['risk']) or team.SENSITIVITIES.index(sensitivity)<team.SENSITIVITIES.index(target['sensitivity']):raise ValueError('Task controls cannot be below project controls')
        if sensitivity in ('public','internal') and not share_confirmed:raise ValueError('Confirm that these instructions contain no private conversation content before using this classification')
        tid=team.create_task(pid,employee,title,instruction,acceptance,risk=risk,sensitivity=sensitivity,path=path,_db=db)
        if start:db.execute("UPDATE team_tasks SET state='ready',owner_grant=1,version=version+1 WHERE id=?",(tid,));team.event(db,'owner','task_start_approved',{'task_id':tid,'source':'reviewed_conversation_proposal'})
        db.execute('INSERT INTO ux_suggestion_tasks VALUES(?,?)',(sid,tid));db.execute("UPDATE dialogue_suggestions SET status='approved',approved_hash=?,decided_at=? WHERE id=?",(digest,p.stamp(),sid))
        team.event(db,'owner','conversation_proposal_classified',{'task_id':tid,'risk':risk,'sensitivity':sensitivity,'start_authorized':start,'share_confirmed':share_confirmed})
    return tid
