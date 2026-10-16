"""Private research folders, reading cards and reviewed worker tasks."""
from uuid import uuid4
from fastapi import Form,Query,HTTPException
from fastapi.responses import HTMLResponse,RedirectResponse
from superhuman.hosted import views,jobs
from superhuman.dialogue.web import options
from . import store


def install(app):
    esc=views.esc
    def render(body,title='Research Desk'):return HTMLResponse(views.page(body,title))
    def error(exc):raise HTTPException(400,str(exc)) from exc
    def area(key):
        try:return store.get(key)
        except ValueError as exc:raise HTTPException(404,str(exc)) from exc
    def source(key):
        try:return store.source(key)
        except ValueError as exc:raise HTTPException(404,str(exc)) from exc
    def go(url):return RedirectResponse(url,status_code=303)
    def back(key):return '<p><a href="/research-desk/'+key+'">Back to research area</a> · <a href="/research-desk">All research areas</a></p>'
    def source_form(area_id,payload,hidden='',action=None):
        body='<form method="post" action="'+(action or '/research-desk/'+area_id+'/source')+'">'+hidden
        for key,label,limit in store.FIELDS:
            if key in ('synopsis','excerpt','limitations','read_reason'):body+='<label>'+label+'<textarea name="'+key+'" maxlength="'+str(limit)+'">'+esc(payload.get(key,''))+'</textarea></label>'
            else:body+='<label>'+label+'<input name="'+key+'" maxlength="'+str(limit)+'"'+(' required' if key=='title' else '')+' value="'+esc(payload.get(key,''))+'"></label>'
        body+='<label><input type="checkbox" style="width:auto;display:inline-block" name="must_read" value="true"'+(' checked' if payload.get('must_read') else '')+'> Flag for my personal reading</label><label>Reading status<select name="read_state"><option value="unread"'+(' selected' if payload.get('read_state','unread')=='unread' else '')+'>Not yet read</option><option value="read"'+(' selected' if payload.get('read_state')=='read' else '')+'>Read by me</option></select></label><button>Save source card · 0 model requests</button></form>'
        return body

    @app.get('/research-desk')
    def home(page:int=1,status:str='active'):
        try:rows=store.listing(page,status)
        except ValueError as exc:error(exc)
        body='<h1>Research Desk</h1><p>Organize questions, source notes and research outputs by area. Source cards are working records; saving them does not verify their claims.</p><nav><a href="/research-desk">Active</a><a href="/research-desk?status=archived">Archived</a></nav>'
        body+='<section class="card"><h2>Create a research area</h2><form method="post" action="/research-desk/create"><input type="hidden" name="submission_key" value="'+uuid4().hex+'"><label>Title<input name="title" maxlength="180" required></label><label>Workstream<select name="scope" required><option value="">Choose a workstream</option>'+options(store.dialogue.scopes(),None)+'</select></label><label>Research questions<textarea name="questions" maxlength="4000" required></textarea></label><label>Working hypothesis (optional)<textarea name="hypothesis" maxlength="2000"></textarea></label><button>Create area · 0 model requests</button></form></section>'
        for row in rows:body+='<article class="card"><h2><a href="/research-desk/'+row['id']+'">'+esc(row['title'])+'</a></h2><p>'+esc(row['scope'])+' · '+esc(row['status'])+'</p></article>'
        if page>1:body+='<a href="/research-desk?status='+status+'&page='+str(page-1)+'">Previous</a> '
        if len(rows)==50:body+='<a href="/research-desk?status='+status+'&page='+str(page+1)+'">Next</a>'
        return render(body)

    @app.post('/research-desk/create')
    def create(title:str=Form(...),scope:str=Form(...),questions:str=Form(...),hypothesis:str=Form(''),submission_key:str=Form(...)):
        try:key=store.create(title,scope,questions,hypothesis,submission_key)
        except ValueError as exc:error(exc)
        return go('/research-desk/'+key)

    @app.get('/research-desk/source/{source_id}')
    def source_detail(source_id:str):
        row=source(source_id);a=area(row['area_id']);v=row['payload']
        body='<h1>'+esc(v['title'])+'</h1>'+back(a['id'])+'<p>Read flags and synopses are owner-curated, not independent fact checks.</p>'
        if a['status']=='active':
            body+='<p><a class="button" href="/research-desk/'+a['id']+'/draft/synopsis?source_ids='+source_id+'">Review source-synopsis task</a></p>'
            body+=source_form(a['id'],v,'<input type="hidden" name="version" value="'+str(row['version'])+'">',action='/research-desk/source/'+source_id+'/save')
        else:body+='<p>This area is archived. Reopen it to edit cards or approve work.</p><pre>'+esc(v['synopsis'])+'</pre>'
        return render(body,v['title'])

    @app.post('/research-desk/source/{source_id}/save')
    def edit_source(source_id:str,version:int=Form(...),title:str=Form(...),url:str=Form(''),filename:str=Form(''),synopsis:str=Form(''),excerpt:str=Form(''),limitations:str=Form(''),read_reason:str=Form(''),must_read:bool=Form(False),read_state:str=Form('unread')):
        row=source(source_id)
        values=dict(title=title,url=url,filename=filename,synopsis=synopsis,excerpt=excerpt,limitations=limitations,read_reason=read_reason,must_read=must_read,read_state=read_state)
        try:store.save_source(row['area_id'],values,source_id=source_id,version=version)
        except (ValueError,OSError) as exc:error(exc)
        return go('/research-desk/source/'+source_id)

    @app.get('/research-desk/{area_id}')
    def detail(area_id:str,page:int=1):
        a=area(area_id)
        try:rows=store.sources(area_id,page);tasks=store.jobs(area_id)
        except ValueError as exc:error(exc)
        body='<h1>'+esc(a['title'])+'</h1><p>'+esc(a['scope'])+' · '+esc(a['status'])+'</p><p><a href="/research-desk">All research areas</a> · <a href="/tools?project='+a['scope']+'">Files in this workstream</a></p><h2>Research questions</h2><pre>'+esc(a['questions'])+'</pre><h2>Working hypothesis</h2><pre>'+esc(a['hypothesis'] or '(not set)')+'</pre>'
        if a['status']=='active':body+='<p><a class="button" href="/research-desk/'+area_id+'/draft/web">Review web-research task · up to 1 request</a></p>'
        body+='<h2>Source cards and reading list</h2><p>Upload documents using Files in this workstream, then enter their exact filename on a source card. Original files stay in the workstream workspace; cards group them by research area without moving them. URLs are saved references and are not downloaded by this page.</p>'
        if a['status']=='active':body+='<form method="get" action="/research-desk/'+area_id+'/draft/synthesis">'
        for row in rows:
            v=row['payload'];body+='<article class="card"><h3><a href="/research-desk/source/'+row['id']+'">'+esc(v['title'])+'</a></h3>'
            if a['status']=='active':body+='<label><input type="checkbox" style="width:auto;display:inline-block" name="source_ids" value="'+row['id']+'"> Select for synthesis</label>'
            body+='<p>'+('Flagged for personal reading · ' if v['must_read'] else '')+('Read by me' if v['read_state']=='read' else 'Not yet read')+'</p>'
            if v['read_reason']:body+='<p>'+esc(v['read_reason'])+'</p>'
            if v['filename']:body+='<p>Workspace file: '+esc(v['filename'])+'</p>'
            if v['url']:body+='<p><a href="'+esc(v['url'])+'" rel="noopener noreferrer" target="_blank">Open original source</a></p>'
            body+='<pre>'+esc(v['synopsis'] or 'No synopsis saved. Review a synopsis task or add your own notes.')+'</pre>'
            if v['limitations']:body+='<p>Limitations: '+esc(v['limitations'])+'</p>'
            body+='</article>'
        if a['status']=='active':body+='<p>Select one to three source cards from this page.</p><button>Review synthesis task · up to 3 requests</button></form>'
        if not rows:body+='<p>No source cards yet.</p>'
        if page>1:body+='<a href="/research-desk/'+area_id+'?page='+str(page-1)+'">Previous sources</a> '
        if len(rows)==50:body+='<a href="/research-desk/'+area_id+'?page='+str(page+1)+'">Next sources</a>'
        if a['status']=='active':body+='<details class="card"><summary>Add a source card</summary>'+source_form(area_id,{},'<input type="hidden" name="submission_key" value="'+uuid4().hex+'">')+'</details>'
        body+='<h2>Research tasks and outputs</h2>'
        for task in tasks:body+='<article class="card"><h3>'+esc(task['objective'])+'</h3><p>'+esc(views.label(task['status']))+' · '+str(task['used_calls'])+' / '+str(task['max_calls'])+' requests</p><a class="button" href="/work/'+task['project_id']+'">Open output and review</a></article>'
        if not tasks:body+='<p>No tasks approved in this area yet.</p>'
        if len(tasks)==50:body+='<p>Showing the 50 most recent tasks; older outputs remain in Projects.</p>'
        body+='<details class="card"><summary>Edit or archive this area</summary><p>Workstream stays fixed so source-file access remains in its original workspace.</p><form method="post" action="/research-desk/'+area_id+'/save"><input type="hidden" name="version" value="'+str(a['version'])+'"><label>Title<input name="title" maxlength="180" required value="'+esc(a['title'])+'"></label><label>Research questions<textarea name="questions" maxlength="4000" required>'+esc(a['questions'])+'</textarea></label><label>Working hypothesis<textarea name="hypothesis" maxlength="2000">'+esc(a['hypothesis'])+'</textarea></label><label>Status<select name="status"><option value="active"'+(' selected' if a['status']=='active' else '')+'>Active</option><option value="archived"'+(' selected' if a['status']=='archived' else '')+'>Archived</option></select></label><button>Save area</button></form></details>'
        return render(body,a['title'])

    @app.post('/research-desk/{area_id}/save')
    def save(area_id:str,version:int=Form(...),title:str=Form(...),questions:str=Form(...),hypothesis:str=Form(''),status:str=Form(...)):
        try:store.update(area_id,version,title,questions,hypothesis,status)
        except ValueError as exc:error(exc)
        return go('/research-desk/'+area_id)

    @app.post('/research-desk/{area_id}/source')
    def add_source(area_id:str,title:str=Form(...),url:str=Form(''),filename:str=Form(''),synopsis:str=Form(''),excerpt:str=Form(''),limitations:str=Form(''),read_reason:str=Form(''),must_read:bool=Form(False),read_state:str=Form('unread'),submission_key:str=Form(...)):
        values=dict(title=title,url=url,filename=filename,synopsis=synopsis,excerpt=excerpt,limitations=limitations,read_reason=read_reason,must_read=must_read,read_state=read_state)
        try:store.save_source(area_id,values,submission_key)
        except (ValueError,OSError) as exc:error(exc)
        return go('/research-desk/'+area_id)

    @app.get('/research-desk/{area_id}/draft/{kind}')
    def preview(area_id:str,kind:str,source_ids:list[str]=Query(default=[])):
        a=area(area_id)
        try:task=store.draft(area_id,kind,source_ids)
        except (ValueError,OSError) as exc:error(exc)
        worker=jobs.worker_status();budget=task['budget']
        body='<h1>Review '+esc(store.KINDS[kind][0].lower())+'</h1>'+back(area_id)+'<p>Workstream: '+esc(a['scope'])+' · Worker '+('online' if worker['online'] else 'offline')+(' / paused' if worker['paused'] else '')+'.</p>'
        body+='<p>Review and edit the complete instructions. Approval authorises up to '+str(budget)+' model request'+('s' if budget!=1 else '')+'. Failed attempts count; no automatic paid retries. Normal workstream memory and specialist context also apply.</p>'
        if kind=='web':body+='<p>This uses hosted public web search. Keep confidential details out of the research question. No source cards are attached by default. One research request is a starting point, not an exhaustive literature review.</p>'
        else:body+='<p>This is local drafting with no browsing. URLs alone are not read. File markers attach extracted text when the worker starts, with a shared 12000-character source-text limit. Use Files to inspect the material before approval; PDFs may need OCR and attachments can be incomplete. A synopsis result stays in its project until you review it and copy suitable text to the source card.</p>'
        body+='<form method="post" action="/research-desk/'+area_id+'/queue"><input type="hidden" name="kind" value="'+kind+'"><input type="hidden" name="source_ids" value="'+','.join(source_ids)+'"><input type="hidden" name="expected_basis" value="'+task['basis_hash']+'"><input type="hidden" name="submission_key" value="'+uuid4().hex+'"><label>Task title<input name="title" maxlength="180" required value="'+esc(task['title'])+'"></label><label>Complete task instructions<textarea name="details" maxlength="12000" required style="min-height:420px">'+esc(task['details'])+'</textarea></label><button>Approve · up to '+str(budget)+' model request'+('s' if budget!=1 else '')+'</button></form>'
        return render(body,'Review research task')

    @app.post('/research-desk/{area_id}/queue')
    def queue(area_id:str,kind:str=Form(...),source_ids:str=Form(''),expected_basis:str=Form(...),title:str=Form(...),details:str=Form(...),submission_key:str=Form(...)):
        ids=source_ids.split(',') if source_ids else []
        try:pid=store.queue(area_id,kind,ids,expected_basis,title,details,submission_key)
        except (ValueError,OSError) as exc:error(exc)
        return go('/work/'+pid)
