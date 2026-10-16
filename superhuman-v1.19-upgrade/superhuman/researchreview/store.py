"""Explicit intake from approved output; no fetching or model requests."""
import hashlib
import json
from urllib.parse import urlsplit,urlunsplit
from uuid import uuid4
from superhuman.projects import engine as p
from superhuman.researchdesk import store as research


def initialize(path=p.DEFAULT_DB):
    research.initialize(path)
    with p.connect(path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS research_citations(
          id TEXT PRIMARY KEY,area_id TEXT NOT NULL,job_id TEXT NOT NULL,url TEXT NOT NULL,
          url_key TEXT NOT NULL,title TEXT NOT NULL,output_hash TEXT NOT NULL,status TEXT NOT NULL,
          source_id TEXT,decision_hash TEXT,created_at TEXT NOT NULL,decided_at TEXT,
          UNIQUE(job_id,url_key));
        CREATE TABLE IF NOT EXISTS research_adoptions(
          id TEXT PRIMARY KEY,job_id TEXT NOT NULL,source_id TEXT NOT NULL,output_hash TEXT NOT NULL,
          approval_hash TEXT NOT NULL,previous_json TEXT NOT NULL,applied_json TEXT NOT NULL,
          previous_version INTEGER NOT NULL,created_at TEXT NOT NULL,UNIQUE(job_id,output_hash));
        ''')


def url_key(value):
    value=research.text(value,2000,'Source URL',True)
    if any(c.isspace() or ord(c)<32 for c in value):raise ValueError('Invalid source URL')
    try:
        u=urlsplit(value);port=u.port
        if u.scheme not in ('http','https') or not u.hostname or u.username or u.password:raise ValueError('Invalid source URL')
        host=u.hostname.lower()
        if ':' in host:host='['+host+']'
        if port is not None and port!={'http':80,'https':443}[u.scheme]:host+=':'+str(port)
        return urlunsplit((u.scheme,host,u.path or '/',u.query,''))
    except ValueError as exc:raise ValueError('Use an http or https source URL without credentials') from exc


def ready(job_id,kind,path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:row=db.execute('SELECT * FROM research_jobs WHERE id=?',(job_id,)).fetchone()
    if row is None or row['kind']!=kind:raise ValueError('Matching research task not found')
    job=dict(row);area=research.get(job['area_id'],path);project=p.get(job['project_id'],path)
    task=next((t for t in project['tasks'] if t['id']=='final'),None)
    if project['status']!='approved' or task is None or task['status']!='approved':raise ValueError('Review and approve the project output before using it here')
    result=json.loads(task['result_json'] or '{}')
    if not isinstance(result,dict) or not result.get('content_sha256'):raise ValueError('Output has no checked content hash; review it through the current project controls first')
    _,content=p._text(result);output_hash=hashlib.sha256(content.encode()).hexdigest()
    if result['content_sha256']!=output_hash:raise ValueError('Approved output content changed')
    return dict(job=job,area=area,task=task,result=result,text=content,output_hash=output_hash)


def locked_ready(db,value):
    row=db.execute("SELECT p.status AS project_status,t.status,t.result_json FROM projects p JOIN project_tasks t ON t.project_id=p.id AND t.id='final' WHERE p.id=?",(value['job']['project_id'],)).fetchone()
    if row is None or row['project_status']!='approved' or row['status']!='approved' or row['result_json']!=value['task']['result_json']:
        raise ValueError('Project output changed. Reload and review it again.')
    area=db.execute('SELECT * FROM research_areas WHERE id=?',(value['job']['area_id'],)).fetchone()
    if area is None or area['status']!='active':raise ValueError('Reopen the research area before applying source changes')


def collect(job_id,path=p.DEFAULT_DB):
    value=ready(job_id,'web',path);refs=value['result'].get('sources')
    if not isinstance(refs,list) or len(refs)>100:raise ValueError('Expected at most 100 API citation records in this output')
    valid={};skipped=0
    for ref in refs:
        try:
            if not isinstance(ref,dict) or ref.get('origin')!='api_url_citation':raise ValueError('Not an API citation')
            url=research.text(ref.get('url'),2000,'URL',True);normalized=url_key(url)
            title=research.text(ref.get('title') or 'Untitled cited source',2000,'Citation title',True)[:180]
            valid.setdefault(normalized,(url,title))
        except ValueError:skipped+=1
    added=0
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');locked_ready(db,value)
        for normalized,(url,title) in valid.items():
            old=db.execute('SELECT * FROM research_citations WHERE job_id=? AND url_key=?',(job_id,normalized)).fetchone()
            if old:
                if old['status']=='proposed':db.execute('UPDATE research_citations SET title=?,output_hash=? WHERE id=?',(title,value['output_hash'],old['id']))
                continue
            db.execute("INSERT INTO research_citations VALUES(?,?,?,?,?,?,?,'proposed',NULL,NULL,?,NULL)",(uuid4().hex,value['area']['id'],job_id,url,normalized,title,value['output_hash'],p.stamp()));added+=1
    return dict(added=added,usable=len(valid),skipped=skipped,area_id=value['area']['id'])


def candidate(candidate_id,path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:row=db.execute('SELECT * FROM research_citations WHERE id=?',(candidate_id,)).fetchone()
    if row is None:raise ValueError('Citation suggestion not found')
    return dict(row)


def proposal_hash(row):return research.digest([row['id'],row['job_id'],row['url'],row['title'],row['output_hash']])


def listing(area_id,status='proposed',page=1,path=p.DEFAULT_DB):
    research.get(area_id,path);initialize(path)
    if status not in ('proposed','saved','dismissed') or type(page) is not int or not 1<=page<=10000:raise ValueError('Invalid citation page')
    with p.connect(path) as db:return [dict(r) for r in db.execute('SELECT * FROM research_citations WHERE area_id=? AND status=? ORDER BY created_at DESC,id LIMIT 50 OFFSET ?',(area_id,status,(page-1)*50))]


def existing_source(db,area_id,normalized):
    for row in db.execute('SELECT id,payload_json FROM research_sources WHERE area_id=? ORDER BY created_at,id',(area_id,)):
        payload=json.loads(row['payload_json'])
        if not payload.get('url'):continue
        try:match=url_key(payload['url'])==normalized
        except ValueError:continue
        if match:return row['id']
    return None


def duplicate(candidate_id,path=p.DEFAULT_DB):
    row=candidate(candidate_id,path)
    with p.connect(path) as db:return existing_source(db,row['area_id'],row['url_key'])


def save_citation(candidate_id,expected_hash,title,must_read,read_reason,path=p.DEFAULT_DB):
    row=candidate(candidate_id,path);title=research.text(title,180,'Source title',True);read_reason=research.text(read_reason,500,'Reading reason')
    if type(must_read) is not bool:raise ValueError('Choose a valid reading flag')
    fingerprint=research.digest([expected_hash,title,must_read,read_reason])
    if row['status']=='saved':
        if row['decision_hash']!=fingerprint:raise ValueError('Already saved with different details. Edit its source card instead.')
        return row['source_id']
    value=ready(row['job_id'],'web',path)
    if value['output_hash']!=row['output_hash']:raise ValueError('Output was revised. Collect citations again before saving this suggestion.')
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');locked_ready(db,value)
        row=db.execute('SELECT * FROM research_citations WHERE id=?',(candidate_id,)).fetchone()
        if row['status']=='saved' and row['decision_hash']==fingerprint:return row['source_id']
        if row['status']!='proposed' or proposal_hash(row)!=expected_hash:raise ValueError('Citation changed or no longer awaiting review. Reload.')
        source_id=existing_source(db,row['area_id'],row['url_key'])
        now=p.stamp()
        if source_id is None:
            payload={key:'' for key,_,_ in research.FIELDS};payload.update(title=title,url=row['url'],must_read=must_read,read_reason=read_reason,read_state='unread')
            payload=research.source_values(payload,value['area']['scope']);source_id=uuid4().hex
            db.execute('INSERT INTO research_sources VALUES(?,?,?,1,?,?,?)',(source_id,row['area_id'],json.dumps(payload,ensure_ascii=False),now,now,uuid4().hex))
        db.execute("UPDATE research_citations SET status='saved',source_id=?,decision_hash=?,decided_at=? WHERE id=?",(source_id,fingerprint,now,candidate_id))
    return source_id


def dismiss(candidate_id,expected_hash,path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM research_citations WHERE id=?',(candidate_id,)).fetchone()
        if row is None or row['status']=='saved':raise ValueError('Suggestion unavailable or already saved')
        if proposal_hash(row)!=expected_hash:raise ValueError('Citation changed. Reload before dismissal.')
        db.execute("UPDATE research_citations SET status='dismissed',decision_hash=?,decided_at=? WHERE id=?",('dismiss:'+expected_hash,p.stamp(),candidate_id))


def synopsis_preview(job_id,path=p.DEFAULT_DB):
    value=ready(job_id,'synopsis',path);ids=json.loads(value['job']['source_ids'])
    if len(ids)!=1:raise ValueError('Synopsis must belong to exactly one source')
    target=research.source(ids[0],path)
    if target['area_id']!=value['area']['id']:raise ValueError('Source is outside this research area')
    snapshot=json.loads(value['job']['context_json']);original=next((x['payload'] for x in snapshot['sources'] if x['id']==target['id']),None)
    if original is None or any(target['payload'][k]!=original[k] for k in ('title','url','filename','excerpt','limitations')):
        raise ValueError('Source material or limitations changed. Generate a fresh synopsis, or review the existing output manually.')
    research.verify_inputs(value['job']['project_id'],path)
    return dict(value,target=target)


def apply_synopsis(job_id,expected_output,expected_version,synopsis,path=p.DEFAULT_DB):
    synopsis=research.text(synopsis,2500,'Reviewed synopsis',True);value=synopsis_preview(job_id,path)
    if value['output_hash']!=expected_output:raise ValueError('Approved output changed. Reload before applying.')
    fingerprint=research.digest([job_id,expected_output,expected_version,synopsis]);target=value['target']
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');locked_ready(db,value)
        old=db.execute('SELECT * FROM research_adoptions WHERE job_id=? AND output_hash=?',(job_id,expected_output)).fetchone()
        if old:
            if old['approval_hash']!=fingerprint:raise ValueError('This synopsis was already applied with different edits. Edit the source card directly.')
            return old['source_id']
        current=db.execute('SELECT * FROM research_sources WHERE id=?',(target['id'],)).fetchone()
        if current is None or current['version']!=expected_version:raise ValueError('Source card changed. Reload before applying the synopsis.')
        payload=json.loads(current['payload_json']);previous=current['payload_json'];payload['synopsis']=synopsis;new=json.dumps(payload,ensure_ascii=False);now=p.stamp()
        db.execute('UPDATE research_sources SET payload_json=?,version=version+1,updated_at=? WHERE id=?',(new,now,target['id']))
        db.execute('INSERT INTO research_adoptions VALUES(?,?,?,?,?,?,?,?,?)',(uuid4().hex,job_id,target['id'],expected_output,fingerprint,previous,new,expected_version,now))
    return target['id']


def history(source_id,path=p.DEFAULT_DB):
    research.source(source_id,path);initialize(path)
    with p.connect(path) as db:return [dict(r) for r in db.execute('SELECT a.*,j.project_id FROM research_adoptions a JOIN research_jobs j ON j.id=a.job_id WHERE a.source_id=? ORDER BY a.created_at DESC,a.id LIMIT 20',(source_id,))]
