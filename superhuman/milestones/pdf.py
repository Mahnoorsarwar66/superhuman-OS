"""Page-bounded PDF evidence with explicit extraction coverage, never OCR claims."""
import json
from superhuman.foundation import storage
from superhuman.capabilities import local
from superhuman.projects import engine as p
from superhuman.team import store as team,work
from . import store as s

def read_pages(run,item_id,start_page,end_page,path=p.DEFAULT_DB):
    from pypdf import PdfReader
    item=storage.get(item_id,path);pid,maximum=storage.run_controls(run,path);employee=run['project']['workstream']
    if item['kind']!='document' or not item['filename'].lower().endswith('.pdf') or not storage.allowed(item,employee,pid,maximum,path) or storage.health(item)!='Current':raise ValueError('Use a current approved PDF permitted for this assignment')
    if type(start_page) is not int or type(end_page) is not int or start_page<1 or end_page<start_page or end_page-start_page>4:raise ValueError('Read one to five PDF pages at a time')
    file=local.file_for(item['scope'],item['filename']);reader=PdfReader(file)
    if reader.is_encrypted:raise ValueError('Encrypted PDF is not supported')
    count=len(reader.pages)
    if count>500 or end_page>count:raise ValueError('Page range is outside the supported PDF')
    pages=[];remaining=16000
    for n in range(start_page,end_page+1):
        text=reader.pages[n-1].extract_text() or ''
        take=min(len(text),remaining);remaining-=take
        pages.append({'page':n,'text':text[:take],'complete_text_extraction':bool(text.strip()) and len(text)<=take})
    result={'item_id':item_id,'page_count':count,'pages':pages,'source':item['source'],'storage_receipt':{'id':item_id,'version':item['version'],'employee':employee,'project_id':pid,'maximum':maximum,'sha256':item['digest']},'warnings':['Text extraction only. Images, charts and layout are not interpreted. Empty or truncated pages do not count as complete extraction. Retry truncated batches with fewer pages. Extraction coverage does not prove comprehension or factual accuracy.']}
    while len(json.dumps(result,ensure_ascii=False))>28000:
        longest=max(pages,key=lambda x:len(x['text']));longest['text']=longest['text'][:len(longest['text'])//2];longest['complete_text_extraction']=False
    return result

def coverage(mid,path=p.DEFAULT_DB):
    from pypdf import PdfReader
    m=s.milestone(mid,path);cfg=s.managed(m['project_id'],path)
    if cfg['seed_key']!='endorsement-business-plan-131' or m['ordinal']!=1:return []
    reports=[]
    for grant in s.materials(m['project_id'],path):
        if grant['purpose']!='required_guide' or not grant['active']:continue
        item=storage.get(grant['item_id'],path);seen=set();total=0
        try:
            if item['version']!=grant['item_version'] or item['status']!='approved' or storage.health(item)!='Current':raise ValueError('Guide grant is stale')
            total=len(PdfReader(local.file_for(item['scope'],item['filename'])).pages)
            for a in s.assignments(mid,path):
                if not a['run_id']:continue
                actions=s.read('agentic_actions',"SELECT result_json,verification_json FROM agentic_actions WHERE project_id=? AND tool='storage.pdf_pages' AND status IN ('succeeded','cached')",(a['run_id'],),path)
                for action in actions:
                    data=json.loads(action['result_json'] or '{}');receipt=data.get('storage_receipt',{})
                    if not json.loads(action['verification_json'] or '{}').get('verified') or receipt.get('id')!=item['id'] or receipt.get('version')!=item['version'] or receipt.get('sha256')!=item['digest']:continue
                    seen.update(x['page'] for x in data.get('pages',[]) if x.get('complete_text_extraction'))
            owner_seen=set()
            for check in s.read('milestone_page_checks',"SELECT pages FROM milestone_page_checks WHERE item_id=? AND item_version=? AND digest=? AND actor='owner'",(item['id'],item['version'],item['digest']),path):owner_seen.update(json.loads(check['pages']))
            missing=sorted(set(range(1,total+1))-(seen|owner_seen))
            reports.append({'id':item['id'],'title':item['title'],'total_pages':total,'extracted_pages':len(seen),'owner_reviewed_pages':len(owner_seen),'missing_pages':missing,'complete':bool(total) and not missing})
        except (ValueError,OSError,ImportError):reports.append({'id':item['id'],'title':item['title'],'complete':False,'issue':'Guide or current extraction evidence unavailable'})
    return reports

def note(run,key,content,expected_version,path=p.DEFAULT_DB):
    item=work.owned_run(run['project_id'],path)
    a=s.assignment(item['id'],path) if item else None
    if not a or not s.active(a['milestone_id'],path)[0]:raise ValueError('Working notes require an active milestone assignment')
    key=team.text(key,80,'Note key',True);content=team.text(content,3000,'Working note',True)
    if type(expected_version) is not int or expected_version<0:raise ValueError('Use the current note version')
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT version FROM milestone_notes WHERE task_id=? AND note_key=?',(item['id'],key)).fetchone()
        if old and old['version']!=expected_version or not old and expected_version!=0:raise ValueError('Working note changed; inspect current context')
        if not old and db.execute('SELECT COUNT(*) FROM milestone_notes WHERE task_id=?',(item['id'],)).fetchone()[0]>=12:raise ValueError('Working-note limit reached; consolidate notes')
        db.execute('INSERT INTO milestone_notes VALUES(?,?,?,1,?) ON CONFLICT(task_id,note_key) DO UPDATE SET content=excluded.content,version=version+1,updated_at=excluded.updated_at',(item['id'],key,content,p.stamp()))
    return {'key':key,'version':expected_version+1,'status':'working_note','verification_limit':'Reference notes only; not approved facts, owner preferences or evidence of completed work.'}

def record_owner_page_review(item_id,expected_version,pages,note,path=p.DEFAULT_DB):
    from pypdf import PdfReader
    item=storage.get(item_id,path)
    if item['version']!=expected_version or item['status']!='approved' or item['kind']!='document' or not item['filename'].lower().endswith('.pdf') or storage.health(item)!='Current':raise ValueError('Inspect the current approved PDF version')
    count=len(PdfReader(local.file_for(item['scope'],item['filename'])).pages)
    if not pages or any(type(n) is not int or not 1<=n<=count for n in pages):raise ValueError('Choose valid PDF page numbers')
    note=team.text(note,2000,'Owner page-review findings',True)
    with p.connect(path) as db:
        db.execute("INSERT INTO milestone_page_checks VALUES(?,?,?,?,?,'owner',?)",(item_id,expected_version,item['digest'],json.dumps(sorted(set(pages))),note,p.stamp()))
        team.event(db,'owner','guide_pages_reviewed',{'item_id':item_id,'version':expected_version,'pages':sorted(set(pages))})
