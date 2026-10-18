"""Exact quotations and source identity are checked separately from semantic judgment."""
import hashlib,json,re
from uuid import uuid4
from superhuman.projects import engine as p
from superhuman.team import store as team
from superhuman.foundation import storage
from superhuman.capabilities import local
from superhuman.milestones import store as ms,workflow as mw
from . import store as s

def source(mid,kind,ident,actor='owner',maximum='restricted',path=p.DEFAULT_DB,locator=''):
    m=ms.milestone(mid,path);cfg=ms.managed(m['project_id'],path)
    if kind=='storage':
        item=storage.get(ident,path)
        if item['status']!='approved' or storage.health(item)!='Current':raise ValueError('Evidence requires a current approved Storage source')
        if item['project_id'] and item['project_id']!=m['project_id']:raise ValueError('Source belongs to another project')
        if actor!='owner' and not storage.allowed(item,actor,m['project_id'],maximum,path):raise ValueError('Source is not permitted for this assignment')
        # The lead and supervisor must retain access to material used in this shared register.
        for employee in (cfg['lead'],'twin'):
            if not storage.allowed(item,employee,m['project_id'],item['sensitivity'],path):raise ValueError('Grant the project lead and The Twin access to this evidence source first')
        if item['kind']=='document' and item['filename'].lower().endswith('.pdf'):
            match=re.fullmatch(r'page:(\d+)',locator.strip().lower())
            if not match:raise ValueError('For PDF evidence use locator page:N and quote that text page')
            from pypdf import PdfReader
            reader=PdfReader(local.file_for(item['scope'],item['filename']));page=int(match[1])
            if len(reader.pages)>500 or not 1<=page<=len(reader.pages):raise ValueError('PDF page is out of bounds')
            text=(reader.pages[page-1].extract_text() or '')[:16000]
        else:text=item['content'] if item['kind']=='fact' else local.extract(item['scope'],item['filename'])['text']
        return dict(text=text,version=item['version'],digest=item['digest'],sensitivity=item['sensitivity'])
    if kind=='task':
        a=ms.assignment(ident,path)
        if not a:raise ValueError('Evidence task must belong to a milestone')
        other=ms.milestone(a['milestone_id'],path)
        if other['project_id']!=m['project_id'] or other['id']!=mid and other['state']!='approved':raise ValueError('Evidence must be in this milestone or an approved predecessor in this project')
        task=team.task(ident,path)
        if task['state']!='completed':raise ValueError('Lead acceptance of the source task is required first')
        level=team.effective(task,path)['sensitivity']
        if team.SENSITIVITIES.index(level)>team.SENSITIVITIES.index(maximum):raise ValueError('Evidence source is more private than this assignment')
        out=mw.result(ident,path)
        return dict(text=out['text'],version=out['task_version'],digest=out['sha256'],sensitivity=level)
    raise ValueError('Choose storage or task evidence. URLs alone are unverified leads; save and approve the source in Storage or use an accepted research output.')

def add(requirement_id,kind,source_id,quote,locator,interpretation,actor='owner',maximum='restricted',path=p.DEFAULT_DB):
    req=s.records('assurance_requirements','SELECT * FROM assurance_requirements WHERE id=?',(requirement_id,),path)
    if not req:raise ValueError('Requirement not found')
    mid=req[0]['mid'];s.authority(mid,actor,path)
    quote=team.text(quote,2000,'Exact source quotation',True);locator=team.text(locator,300,'Page, section or source locator',True);interpretation=team.text(interpretation,1500,'How this supports or challenges the requirement',True)
    data=source(mid,kind,source_id,actor,maximum,path,locator)
    if quote not in data['text']:raise ValueError('Quotation is not present in the available source text; use an exact bounded passage and inspect extraction limits')
    ident=uuid4().hex
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT id FROM assurance_evidence WHERE requirement_id=? AND kind=? AND source_id=? AND digest=? AND quote=?',(requirement_id,kind,source_id,data['digest'],quote)).fetchone()
        if old:return old['id']
        if db.execute('SELECT COUNT(*) FROM assurance_evidence WHERE requirement_id=?',(requirement_id,)).fetchone()[0]>=12:raise ValueError('Evidence limit reached for this requirement')
        db.execute('INSERT INTO assurance_evidence(id,requirement_id,kind,source_id,source_version,digest,quote,locator,interpretation,sensitivity,actor,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(ident,requirement_id,kind,source_id,data['version'],data['digest'],quote,locator,interpretation,data['sensitivity'],actor,p.stamp()))
        s.touch(db,mid,actor,'evidence_proposed',{'id':ident,'requirement_id':requirement_id})
    from .workflow import changed
    changed(mid,'evidence:'+ident,'New evidence requires a fresh milestone review',path=path)
    return ident

def health(row,mid,path=p.DEFAULT_DB):
    try:
        data=source(mid,row['kind'],row['source_id'],path=path,locator=row['locator'])
        if data['digest']!=row['digest'] or data['version']!=row['source_version'] or row['quote'] not in data['text']:return 'Source changed or quotation no longer available'
        if data['sensitivity']!=row['sensitivity']:return 'Source privacy changed'
        return 'Current'
    except (ValueError,OSError,ImportError) as exc:return str(exc)[:200]

def review(ident,expected,decision,note,actor='owner',path=p.DEFAULT_DB):
    rows=s.records('assurance_evidence','SELECT e.*,r.mid FROM assurance_evidence e JOIN assurance_requirements r ON r.id=e.requirement_id WHERE e.id=?',(ident,),path)
    if not rows:raise ValueError('Evidence not found')
    row=rows[0];s.authority(row['mid'],actor,path,lead=True)
    if decision not in ('accepted','rejected','contested'):raise ValueError('Choose a supported evidence decision')
    if decision=='accepted' and health(row,row['mid'],path)!='Current':raise ValueError('Evidence is stale or access changed; add the current source version')
    note=team.text(note,2000,'Evidence review rationale',True)
    with p.connect(path) as db:
        if not db.execute('UPDATE assurance_evidence SET status=?,review_note=?,version=version+1 WHERE id=? AND version=?',(decision,note,ident,expected)).rowcount:raise ValueError('Evidence changed; reload')
        s.touch(db,row['mid'],actor,'evidence_reviewed',{'id':ident,'decision':decision,'note':note})
    from .workflow import changed
    changed(row['mid'],'evidence-review:'+ident+':'+str(expected+1),'Evidence interpretation or acceptance changed',path=path)

def visible(mid,actor,maximum,path=p.DEFAULT_DB):
    result=[]
    for row in s.evidence(mid,path):
        if team.SENSITIVITIES.index(row['sensitivity'])>team.SENSITIVITIES.index(maximum):continue
        try:source(mid,row['kind'],row['source_id'],actor,maximum,path,row['locator'])
        except (ValueError,OSError,ImportError):continue
        result.append({**row,'health':health(row,mid,path)})
    return result
