"""Initiative-to-project linkage and evidence-backed observations, without ROI claims."""
from decimal import Decimal,InvalidOperation
from datetime import date
from uuid import uuid4
from superhuman.projects import engine as p
from superhuman.team import store as team
from superhuman.milestones import store as ms
from superhuman.foundation import storage
from . import store as s,evidence as ev

def initiatives(pid,path=p.DEFAULT_DB):return s.records('assurance_initiatives','SELECT * FROM assurance_initiatives WHERE project_id=? ORDER BY created_at DESC',(pid,),path)
def metrics(initiative,path=p.DEFAULT_DB):return s.records('assurance_metrics','SELECT * FROM assurance_metrics WHERE initiative_id=?',(initiative,),path)
def observations(metric,path=p.DEFAULT_DB):return s.records('assurance_observations','SELECT * FROM assurance_observations WHERE metric_id=? ORDER BY observed_on DESC,created_at DESC',(metric,),path)

def number(value):
    try:
        value=str(value)
        if len(value)>40:raise ValueError()
        n=Decimal(value)
        if not n.is_finite() or abs(n)>Decimal('1e18'):raise ValueError()
        return str(n)
    except (InvalidOperation,ValueError):raise ValueError('Use a finite numeric measurement') from None

def propose(pid,key,title,hypothesis,actor='owner',source_kind='',source_id='',path=p.DEFAULT_DB):
    cfg=ms.managed(pid,path)
    if not cfg or actor not in set(ms.roster(pid,path))|{'owner'}:raise ValueError('Choose a governed project and authorised participant')
    if actor!='owner' and not cfg['share_outputs']:raise ValueError('Project output sharing is required')
    key=team.text(key,100,'Initiative key',True);title=team.text(title,180,'Initiative title',True);hypothesis=team.text(hypothesis,2000,'Expected result and rationale',True)
    if source_kind:
        if source_kind=='signal':
            from superhuman.foundation import proactive
            source=next((v for v in proactive.signals(path,True) if v['id']==source_id),None)
            entities={pid}|{t['id'] for t in team.tasks(path) if t['project_id']==pid}
            if not source or source['entity'] not in entities:raise ValueError('Signal does not belong to this project')
        elif source_kind=='suggestion':
            source=s.records('dialogue_suggestions','SELECT d.id FROM dialogue_suggestions d JOIN ux_rooms r ON r.thread_id=d.thread_id WHERE d.id=? AND r.project_kind=\'team\' AND r.project_id=?',(source_id,pid),path)
            if not source:raise ValueError('Suggestion does not belong to this project conversation')
        else:raise ValueError('Use a project signal or conversation suggestion')
    elif source_id:raise ValueError('Choose the initiative source type')
    ident=uuid4().hex
    with p.connect(path) as db:
        old=db.execute('SELECT * FROM assurance_initiatives WHERE project_id=? AND initiative_key=?',(pid,key)).fetchone()
        if old:
            if (old['title'],old['hypothesis'],old['source_kind'],old['source_id'])!=(title,hypothesis,source_kind,source_id):raise ValueError('Initiative key already has different content')
            return old['id']
        db.execute('INSERT INTO assurance_initiatives(id,project_id,initiative_key,title,hypothesis,actor,source_kind,source_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(ident,pid,key,title,hypothesis,actor,source_kind,source_id,p.stamp()))
        team.event(db,actor,'initiative_proposed',{'id':ident,'project_id':pid})
    return ident

def decide(ident,expected,decision,note,path=p.DEFAULT_DB):
    if decision not in ('approved','rejected'):raise ValueError('Choose an initiative decision')
    note=team.text(note,2000,'Initiative decision',True)
    with p.connect(path) as db:
        if not db.execute("UPDATE assurance_initiatives SET status=?,version=version+1 WHERE id=? AND version=? AND status='proposed'",(decision,ident,expected)).rowcount:raise ValueError('Initiative changed or already decided')
        team.event(db,'owner','initiative_'+decision,{'id':ident,'note':note})

def add_metric(ident,name,unit,baseline,target,due,direction,path=p.DEFAULT_DB):
    rows=s.records('assurance_initiatives','SELECT * FROM assurance_initiatives WHERE id=?',(ident,),path)
    if not rows or rows[0]['status']!='approved':raise ValueError('Approve the initiative before defining its outcome baseline')
    name=team.text(name,180,'Metric',True);unit=team.text(unit,80,'Unit',True);baseline=number(baseline);target=number(target)
    if direction not in ('increase','decrease'):raise ValueError('Choose an improvement direction')
    if direction=='increase' and Decimal(target)<Decimal(baseline) or direction=='decrease' and Decimal(target)>Decimal(baseline):raise ValueError('Target must agree with the improvement direction')
    try:date.fromisoformat(due)
    except ValueError:raise ValueError('Use YYYY-MM-DD for the outcome review date') from None
    mid=uuid4().hex
    with p.connect(path) as db:
        if db.execute('SELECT COUNT(*) FROM assurance_metrics WHERE initiative_id=?',(ident,)).fetchone()[0]>=12:raise ValueError('Metric limit reached')
        db.execute('INSERT INTO assurance_metrics(id,initiative_id,name,unit,baseline,target,due,direction) VALUES(?,?,?,?,?,?,?,?)',(mid,ident,name,unit,baseline,target,due,direction))
        team.event(db,'owner','outcome_baseline_defined',{'metric_id':mid,'initiative_id':ident,'baseline':baseline,'target':target,'unit':unit})
    return mid

def observe(metric,value,observed_on,source_id,quote,note,actor='owner',path=p.DEFAULT_DB):
    rows=s.records('assurance_metrics','SELECT m.*,i.project_id FROM assurance_metrics m JOIN assurance_initiatives i ON i.id=m.initiative_id WHERE m.id=?',(metric,),path)
    if not rows:raise ValueError('Metric not found')
    row=rows[0];value=number(value)
    try:
        day=date.fromisoformat(observed_on)
        if day>storage.today():raise ValueError()
    except ValueError:raise ValueError('Use an actual observation date, not a future forecast') from None
    milestones=ms.listing(row['project_id'],path)
    if not milestones:raise ValueError('Add a milestone to this project first')
    data=ev.source(milestones[0]['id'],'storage',source_id,actor,path=path)
    quote=team.text(quote,2000,'Exact measurement evidence',True);note=team.text(note,1500,'Measurement method and limits',True)
    if quote not in data['text']:raise ValueError('Measurement quotation is not in the source')
    ident=uuid4().hex
    with p.connect(path) as db:
        db.execute('INSERT INTO assurance_observations(id,metric_id,value,observed_on,source_id,source_version,digest,quote,note,actor,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(ident,metric,value,observed_on,source_id,data['version'],data['digest'],quote,note,actor,p.stamp()))
        team.event(db,actor,'outcome_observed',{'id':ident,'metric_id':metric,'status':'proposed'})
    return ident

def accept_observation(ident,path=p.DEFAULT_DB):
    rows=s.records('assurance_observations','SELECT o.*,i.project_id FROM assurance_observations o JOIN assurance_metrics m ON m.id=o.metric_id JOIN assurance_initiatives i ON i.id=m.initiative_id WHERE o.id=?',(ident,),path)
    if not rows or rows[0]['status']!='proposed':raise ValueError('Observation is not awaiting review')
    row=rows[0];mid=ms.listing(row['project_id'],path)[0]['id'];data=ev.source(mid,'storage',row['source_id'],path=path)
    if (data['version'],data['digest'])!=(row['source_version'],row['digest']):raise ValueError('Measurement source changed; add a new observation')
    with p.connect(path) as db:
        db.execute("UPDATE assurance_observations SET status='accepted' WHERE id=? AND status='proposed'",(ident,))
        team.event(db,'owner','outcome_observation_accepted',{'id':ident})

def summary(metric,path=p.DEFAULT_DB):
    rows=s.records('assurance_metrics','SELECT m.*,i.project_id FROM assurance_metrics m JOIN assurance_initiatives i ON i.id=m.initiative_id WHERE m.id=?',(metric,),path)
    if not rows:raise ValueError('Metric not found')
    m=rows[0];valid=[]
    for o in observations(metric,path):
        if o['status']!='accepted':continue
        try:
            source=storage.get(o['source_id'],path)
            if source['status']=='approved' and storage.health(source)=='Current' and (source['version'],source['digest'])==(o['source_version'],o['digest']):valid.append(o)
        except (ValueError,OSError):pass
    latest=valid[0] if valid else None
    result={**m,'latest':latest,'due_for_review':m['due']<=storage.today().isoformat(),'limitation':'Baseline and observations are owner-reviewed inputs. Change is descriptive; it does not prove causation or ROI.'}
    if latest:
        change=Decimal(latest['value'])-Decimal(m['baseline']);result['change']=str(change);result['target_met']=Decimal(latest['value'])>=Decimal(m['target']) if m['direction']=='increase' else Decimal(latest['value'])<=Decimal(m['target'])
    return result

def attention(path=p.DEFAULT_DB):
    items=[]
    for cfg in s.records('milestone_projects','SELECT project_id FROM milestone_projects',path=path):
        pid=cfg['project_id']
        for c in s.changes(pid,path):
            if c['state']=='open':items.append(dict(title=c['reason'],reason='Changed evidence or strategy needs impact inspection',url='/project-hub/'+pid))
        for mid in ms.listing(pid,path):
            for gap in s.gaps(mid['id'],path):
                if gap['state']=='needs_owner':items.append(dict(title=gap['question'],reason='Investigation needs owner inspection',url='/milestones/'+mid['id']+'/evidence'))
            pol=s.policy(mid['id'],path)
            if pol and not pol['register_confirmed'] and mid['state']=='working' and any(a['role']=='lead' and a['state']=='awaiting_review' for a in ms.assignments(mid['id'],path)):
                items.append(dict(title=mid['title'],reason='Requirement register scope needs confirmation',url='/milestones/'+mid['id']+'/evidence'))
        for initiative in initiatives(pid,path):
            if initiative['status']=='proposed':items.append(dict(title=initiative['title'],reason='Initiative proposal needs strategic review',url='/project-hub/'+pid+'/outcomes'))
            for metric in metrics(initiative['id'],path):
                data=summary(metric['id'],path)
                latest=data['latest']
                if data['due_for_review'] and (not latest or latest['observed_on']<metric['due']):items.append(dict(title=metric['name'],reason='Outcome follow-up due; add or review a current measurement',url='/project-hub/'+pid+'/outcomes'))
    return items
