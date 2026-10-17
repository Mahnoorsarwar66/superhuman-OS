"""Exact-version work proposals. Independent Twin review delegates routine work only."""
import json
from datetime import date
from uuid import uuid4
from superhuman.projects import engine as p
from superhuman.team import store as team
from superhuman.dialogue import store as d
from superhuman.experience import store as ux
from superhuman.milestones import store as ms
from . import store as s


def get(ident,path=p.DEFAULT_DB):return s.one('SELECT * FROM hub_cards WHERE id=?',(ident,),path)

def sync(path=p.DEFAULT_DB):
    s.initialize(path)
    with p.connect(path) as db:
        db.execute("UPDATE hub_cards SET task_id=(SELECT x.task_id FROM ux_suggestion_tasks x WHERE x.suggestion_id=hub_cards.suggestion_id),status='authorized',decision='Approved through existing conversation controls',version=version+1 WHERE task_id='' AND EXISTS(SELECT 1 FROM ux_suggestion_tasks x WHERE x.suggestion_id=hub_cards.suggestion_id)")
        db.execute("UPDATE hub_cards SET status='dismissed',version=version+1 WHERE task_id='' AND status NOT IN ('dismissed','twin_review') AND EXISTS(SELECT 1 FROM dialogue_suggestions v WHERE v.id=hub_cards.suggestion_id AND v.status='dismissed')")
    rows=s.read('''SELECT v.*,r.employee,r.project_id AS pid FROM dialogue_suggestions v JOIN ux_rooms r ON r.thread_id=v.thread_id WHERE r.project_kind='team' AND v.status='proposed' AND NOT EXISTS(SELECT 1 FROM hub_cards c WHERE c.suggestion_id=v.id) ORDER BY v.created_at LIMIT 30''',path=path)
    for v in rows:
        parent=team.project(v['pid'],path);step=s.read('SELECT r.topic_id FROM hub_steps s JOIN hub_rounds r ON r.id=s.round_id WHERE s.turn_id=?',(v['turn_id'],),path)
        tid=step[0]['topic_id'] if step else '';topic=s.topic(tid,path) if tid else None
        sensitivity=max((parent['sensitivity'],'confidential'),key=team.SENSITIVITIES.index)
        with p.connect(path) as db:
            db.execute('INSERT OR IGNORE INTO hub_cards(id,suggestion_id,topic_id,room_id,project_id,owner,title,instruction,criteria,risk,sensitivity,milestone_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(uuid4().hex,v['id'],tid,v['thread_id'],v['pid'],parent['scope'] if v['employee']=='twin' else v['employee'],v['title'],v['details'],'Produce a reviewable deliverable with sources, explicit uncertainties and practical next actions.',parent['risk'],sensitivity,topic['milestone_id'] if topic else '',p.stamp()))

def edit(ident,expected,title,instruction,criteria,owner,due,risk,sensitivity,mid,share_confirmed,path=p.DEFAULT_DB):
    card=get(ident,path);parent=team.project(card['project_id'],path)
    team.classification(parent['priority'],risk,sensitivity)
    if owner not in team.EMPLOYEES or owner=='twin':raise ValueError('Choose a specialist owner')
    if ms.managed(parent['id'],path):
        if not mid or ms.milestone(mid,path)['project_id']!=parent['id'] or owner not in json.loads(ms.milestone(mid,path)['workers']):raise ValueError('Choose a project milestone and one of its approved authors')
    elif mid or owner!=parent['scope']:raise ValueError('Use this project’s department specialist')
    if team.RISKS.index(risk)<team.RISKS.index(parent['risk']) or team.SENSITIVITIES.index(sensitivity)<team.SENSITIVITIES.index(parent['sensitivity']):raise ValueError('Card controls cannot be below project controls')
    if sensitivity in ('public','internal') and not share_confirmed:raise ValueError('Confirm that the reviewed instructions contain no private conversation material')
    if due:date.fromisoformat(due)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT 1 FROM hub_card_reviews WHERE card_id=? AND status='pending'",(ident,)).fetchone():raise ValueError('Wait for the pending Twin review before editing')
        if not db.execute("UPDATE hub_cards SET title=?,instruction=?,criteria=?,owner=?,due=?,risk=?,sensitivity=?,milestone_id=?,status='proposed',decision='',version=version+1 WHERE id=? AND version=? AND task_id=''",(d.text(title,180,'Title'),d.text(instruction,5000,'Instructions'),d.text(criteria,1500,'Acceptance criteria'),owner,due,risk,sensitivity,mid,ident,expected)).rowcount:raise ValueError('Card changed or already became a task')
        team.event(db,'owner','work_card_edited',{'card_id':ident})

def review_context(claimed,path=p.DEFAULT_DB):
    records=s.read("SELECT * FROM hub_card_reviews WHERE turn_id=? AND status='pending'",(claimed['id'],),path)
    if not records:return None
    r=records[0];card=get(r['card_id'],path)
    if card['version']!=r['card_version'] or card['status']!='twin_review':raise ValueError('Work card changed before review')
    parent=team.project(card['project_id'],path)
    return {k:card[k] for k in ('id','version','project_id','owner','title','instruction','criteria','due','risk','sensitivity','milestone_id')}|{'project_controls':{k:parent[k] for k in ('version','status','risk','sensitivity','objective','acceptance')},'kind':s.one('SELECT kind FROM dialogue_suggestions WHERE id=?',(card['suggestion_id'],),path)['kind']}

def request_review(ident,expected,path=p.DEFAULT_DB):
    card=get(ident,path);parent=team.project(card['project_id'],path)
    source=s.one('SELECT r.employee FROM dialogue_suggestions v JOIN ux_rooms r ON r.thread_id=v.thread_id WHERE v.id=?',(card['suggestion_id'],),path)
    if source['employee']=='twin':raise ValueError('The Twin authored this proposal; you must review it independently')
    if card['risk']!='routine' or parent['risk']!='routine' or card['sensitivity']=='restricted' or parent['sensitivity']=='restricted':raise ValueError('This card requires your review because of its risk or sensitivity')
    if not team.settings(path)['enabled'] or team.settings(path)['hold']:raise ValueError('Resume the supervised team before requesting a Twin review')
    ep=next(e for e in team.employees(path) if e['id']=='twin')
    if ep['paused']:raise ValueError('The Twin is paused')
    if ms.managed(parent['id'],path):
        cfg=ms.managed(parent['id'],path)
        if not cfg['share_outputs']:raise ValueError('Project sharing must be approved before review')
    attempts=s.one('SELECT COUNT(*) AS n FROM hub_card_review_history WHERE card_id=?',(ident,),path)['n']
    if attempts>=2:raise ValueError('Two Twin review attempts used; review this card yourself before further work')
    rid=uuid4().hex;turn=uuid4().hex
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute("UPDATE hub_cards SET status='twin_review',version=version+1 WHERE id=? AND version=? AND task_id='' AND status IN ('proposed','revision','owner_review')",(ident,expected)).rowcount:raise ValueError('Card changed; reload')
        old=db.execute('SELECT turn_id FROM hub_card_reviews WHERE card_id=?',(ident,)).fetchone()
        if old and db.execute('SELECT status FROM dialogue_turns WHERE id=?',(old['turn_id'],)).fetchone()['status'] in ('queued','running'):raise ValueError('A review is already pending')
        db.execute('INSERT INTO dialogue_threads VALUES(?,?,?,1,0,?,?)',(rid,parent['scope'],'Twin review: '+card['title'][:150],p.stamp(),p.stamp()));db.execute('INSERT INTO ux_rooms VALUES(?,?,?,?,1)',(rid,'twin','team',parent['id']))
        db.execute("INSERT INTO dialogue_turns(id,thread_id,ordinal,submission_key,user_text,status,created_at) VALUES(?,?,1,?,?,'queued',?)",(turn,rid,uuid4().hex,'Review the exact work card independently. Authorize only within existing routine internal authority; escalate strategic, external or ambiguous requests.',p.stamp()))
        db.execute("INSERT OR REPLACE INTO hub_card_reviews VALUES(?,?,?,'pending')",(ident,turn,expected+1));db.execute('INSERT INTO hub_card_review_history VALUES(?,?,?)',(ident,turn,expected+1));team.event(db,'owner','twin_card_review_requested',{'card_id':ident,'turn_id':turn})
    return turn

def _instantiate(card,actor,note,db,path):
    parent=team.project(card['project_id'],path)
    if db.execute('SELECT 1 FROM ux_suggestion_tasks WHERE suggestion_id=?',(card['suggestion_id'],)).fetchone() or db.execute('SELECT status FROM dialogue_suggestions WHERE id=?',(card['suggestion_id'],)).fetchone()['status']!='proposed':raise ValueError('Proposal was already decided through another view; refresh its linked work')
    if parent['status']!='active':raise ValueError('Activate this project before authorizing work')
    if team.RISKS.index(card['risk'])<team.RISKS.index(parent['risk']) or team.SENSITIVITIES.index(card['sensitivity'])<team.SENSITIVITIES.index(parent['sensitivity']):raise ValueError('Project controls increased; review this card again')
    if actor=='twin' and (card['risk']!='routine' or parent['risk']!='routine' or card['sensitivity']=='restricted' or parent['sensitivity']=='restricted'):raise ValueError('Owner approval is required')
    cfg=ms.managed(parent['id'],path)
    if cfg:
        if not card['milestone_id']:raise ValueError('Select a milestone before authorizing this work')
        m=ms.milestone(card['milestone_id'],path)
        if m['project_id']!=parent['id'] or m['state']!='working':raise ValueError('Work must enter an existing working milestone; starting or changing a milestone uses its own controls')
        tid=ms.create_assignment(m['id'],card['owner'],card['title'],card['instruction'],card['criteria'],path=path,_db=db,sensitivity_override=card['sensitivity'])
        db.execute('UPDATE team_tasks SET risk=?,due=? WHERE id=?',(card['risk'],card['due'],tid))
    else:
        if card['owner']!=parent['scope']:raise ValueError('Choose this project’s department specialist')
        tid=team.create_task(parent['id'],card['owner'],card['title'],card['instruction'],card['criteria'],risk=card['risk'],sensitivity=card['sensitivity'],due=card['due'],actor=actor,path=path,_db=db)
        if actor=='owner':db.execute("UPDATE team_tasks SET state='ready',owner_grant=1 WHERE id=?",(tid,))
    if actor=='owner':db.execute('UPDATE team_tasks SET owner_grant=1 WHERE id=?',(tid,))
    db.execute("UPDATE hub_cards SET status='authorized',task_id=?,decision=?,version=version+1 WHERE id=?",(tid,note,card['id']))
    db.execute('INSERT INTO ux_suggestion_tasks VALUES(?,?)',(card['suggestion_id'],tid))
    db.execute("UPDATE dialogue_suggestions SET status='approved',approved_hash=?,decided_at=? WHERE id=? AND status='proposed'",('hub:'+card['id'],p.stamp(),card['suggestion_id']))
    team.event(db,actor,'work_card_authorized',{'card_id':card['id'],'task_id':tid,'note':note})
    return tid

def authorize(ident,expected,note,path=p.DEFAULT_DB):
    card=get(ident,path);note=d.text(note,1500,'Approval note')
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');live=db.execute('SELECT * FROM hub_cards WHERE id=?',(ident,)).fetchone()
        if live['version']!=expected or live['task_id'] or live['status']=='twin_review':raise ValueError('Work card changed or is being reviewed')
        return _instantiate(dict(live),'owner',note,db,path)

def reconcile(path=p.DEFAULT_DB):
    sync(path)
    for card in s.read("SELECT k.* FROM hub_cards k JOIN hub_topics t ON t.id=k.topic_id JOIN hub_channels c ON c.id=t.channel_id WHERE c.delegated=1 AND c.archived=0 AND k.status='proposed' AND NOT EXISTS(SELECT 1 FROM hub_card_review_history h WHERE h.card_id=k.id) ORDER BY k.created_at LIMIT 3",path=path):
        try:request_review(card['id'],card['version'],path)
        except ValueError:pass  # The visible card remains for owner review; authority never expands.
    for review in s.read("SELECT * FROM hub_card_reviews WHERE status='pending' ORDER BY rowid LIMIT 10",path=path):
        turn=d.turn(review['turn_id'],path)
        if turn['status'] in ('queued','running'):continue
        card=get(review['card_id'],path)
        try:
            if turn['status']!='done':raise ValueError('Twin review failed or was interrupted; no automatic replay')
            decision=json.loads(turn['context_json'] or '{}').get('hub_card_decision')
            if not decision:raise ValueError('No saved Twin decision')
            from .context import validate
            claimed=dict(turn,scope=team.project(card['project_id'],path)['scope'])
            validate(claimed,json.loads(turn['context_json']),path)
            with p.connect(path) as db:
                db.execute('BEGIN IMMEDIATE');live=dict(db.execute('SELECT * FROM hub_cards WHERE id=?',(card['id'],)).fetchone())
                if live['version']!=review['card_version'] or live['status']!='twin_review':raise ValueError('Work card changed after the Twin review')
                if decision['decision']=='authorize':_instantiate(live,'twin',decision['note'],db,path)
                else:db.execute('UPDATE hub_cards SET status=?,decision=?,version=version+1 WHERE id=?',('revision' if decision['decision']=='revise' else 'owner_review',decision['note'],card['id']))
                db.execute("UPDATE hub_card_reviews SET status='applied' WHERE card_id=?",(card['id'],))
        except ValueError as exc:
            with p.connect(path) as db:
                db.execute("UPDATE hub_cards SET status='owner_review',decision=?,version=version+1 WHERE id=? AND version=?",(str(exc)[:600],card['id'],review['card_version']));db.execute("UPDATE hub_card_reviews SET status='stopped' WHERE card_id=?",(card['id'],))
