"""Action-specific checks shared by the composer and atomic enqueue guard."""
import json,time
from superhuman.projects import engine as p
from . import store as s


def _check(db,cid,target,check_allowance):
    def one(sql,args=()):
        row=db.execute(sql,args).fetchone()
        return dict(row) if row else None
    c=one('SELECT * FROM hub_channels WHERE id=?',(cid,))
    if not c:raise ValueError('Choose an existing project channel')
    project=one('SELECT * FROM team_projects WHERE id=?',(c['project_id'],))
    cfg=one('SELECT * FROM team_settings WHERE id=1');issues=[]
    if not cfg['enabled']:issues.append('Team coordination is disabled.')
    if cfg['hold']:issues.append('Team coordination is held for inspection.')
    if one("SELECT name FROM sqlite_master WHERE type='table' AND name='hosted_worker'"):
        worker=one('SELECT paused FROM hosted_worker WHERE id=1')
        if worker and worker['paused']:issues.append('The shared worker is paused.')
    if not project or project['status']!='active':issues.append('This project is paused or complete.')
    if c['archived']:issues.append('This channel is archived.')
    leadership=one('SELECT * FROM milestone_projects WHERE project_id=?',(c['project_id'],))
    members=json.loads(c['members'])
    if not leadership or not leadership['share_outputs']:issues.append('Confirm project-team output sharing before requesting AI replies.')
    else:
        roster={leadership['lead'],'twin'}
        for row in db.execute('SELECT workers,reviewers FROM milestones WHERE project_id=?',(c['project_id'],)):
            roster.update(json.loads(row['workers']));roster.update(json.loads(row['reviewers']))
        if not set(members)<=roster or leadership['lead'] not in members:issues.append('Project roster changed; review channel membership.')
    period=one('SELECT * FROM team_budget_periods ORDER BY start DESC LIMIT 1')
    rate=one('SELECT * FROM team_rates WHERE model=?',(cfg['model'],))
    if not period or not period['start']<=time.time()<period['end'] or period['hold'] or not rate:issues.append('An active dollar budget and confirmed model rates are required.')
    recipient=leadership['lead'] if target=='team' and leadership else target
    if recipient and recipient!='team':
        if recipient not in members:issues.append('Choose an approved channel participant.')
        profile=one('SELECT name,paused FROM team_employees WHERE id=?',(recipient,))
        if not profile:issues.append('The requested employee is unavailable.')
        elif profile['paused']:issues.append(profile['name']+' is paused.')
    if check_allowance:
        used=one('SELECT COUNT(*) AS n FROM hub_steps h JOIN hub_rounds r ON r.id=h.round_id JOIN hub_topics t ON t.id=r.topic_id WHERE t.channel_id=?',(cid,))['n']
        if used>=c['max_calls']:issues.append('The channel reply allowance is exhausted.')
    return {'ready':not issues,'issues':issues,'project_id':c['project_id']}


def discussion(cid,target='team',path=p.DEFAULT_DB,check_allowance=True,db=None):
    if db is not None:return _check(db,cid,target,check_allowance)
    s.initialize(path)
    with p.connect(path) as conn:return _check(conn,cid,target,check_allowance)


def require(cid,target='team',path=p.DEFAULT_DB,db=None):
    result=discussion(cid,target,path,db=db)
    if not result['ready']:raise ValueError('AI replies blocked: '+' '.join(result['issues'])+' No discussion or paid request was created.')
