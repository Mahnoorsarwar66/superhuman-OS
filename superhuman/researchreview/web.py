"""Review citation suggestions and deliberately apply approved synopsis text."""
import json
from fastapi import Form,HTTPException
from fastapi.responses import HTMLResponse,RedirectResponse
from superhuman.hosted import views
from . import store


def task_actions(task):
    if task['kind'] not in ('web','synopsis'):return ''
    if task['status']!='approved':return '<p>Approve the output in the project review before collecting its citations or applying a synopsis.</p>'
    if task['kind']=='web':return '<form method="post" action="/research-review/job/'+task['id']+'/collect"><button class="secondary">Collect cited source suggestions · 0 model requests</button></form>'
    return '<p><a class="button secondary" href="/research-review/job/'+task['id']+'/synopsis">Review synopsis for source card</a></p>'


def install(app):
    esc=views.esc
    def render(body,title='Research review'):return HTMLResponse(views.page(body,title))
    def error(exc):raise HTTPException(400,str(exc)) from exc
    def candidate(key):
        try:return store.candidate(key)
        except ValueError as exc:raise HTTPException(404,str(exc)) from exc
    def back(area_id):return '<p><a href="/research-desk/'+area_id+'">Back to research area</a></p>'
    def go(url):return RedirectResponse(url,status_code=303)

    @app.post('/research-review/job/{job_id}/collect')
    def collect(job_id:str):
        try:result=store.collect(job_id)
        except (ValueError,OSError) as exc:error(exc)
        return render('<h1>Cited source suggestions collected</h1><p>'+str(result['added'])+' new suggestions · '+str(result['usable'])+' usable unique citation URLs in this output · '+str(result['skipped'])+' unusable records skipped.</p><p>No papers were downloaded and no model requests were made.</p><p><a class="button" href="/research-review/area/'+result['area_id']+'">Review source suggestions</a></p>'+back(result['area_id']))

    @app.get('/research-review/area/{area_id}')
    def listing(area_id:str,status:str='proposed',page:int=1):
        try:a=store.research.get(area_id);rows=store.listing(area_id,status,page)
        except ValueError as exc:error(exc)
        body='<h1>Review cited sources</h1>'+back(area_id)+'<p>These URLs came from API citation records attached to approved research outputs. This does not verify a paper, its authorship or support for a claim. Saving creates a reading card; it does not download or read the linked paper.</p><nav>'
        for state in ('proposed','saved','dismissed'):body+='<a href="/research-review/area/'+area_id+'?status='+state+'">'+state.capitalize()+'</a>'
        body+='</nav>'
        if a['status']!='active':body+='<p>This area is archived. Reopen it before saving citation suggestions.</p>'
        for row in rows:
            body+='<section class="card"><h2>'+esc(row['title'])+'</h2><p><a href="'+esc(row['url'])+'" rel="noopener noreferrer" target="_blank">Open original cited URL</a></p>'
            with store.p.connect() as db:job=db.execute('SELECT project_id FROM research_jobs WHERE id=?',(row['job_id'],)).fetchone()
            if job:body+='<p><a href="/work/'+job['project_id']+'">Originating research output</a></p>'
            if row['status']=='saved':body+='<p><a class="button" href="/research-desk/source/'+row['source_id']+'">Open saved source card</a></p>'
            elif row['status']=='proposed' and a['status']=='active':
                duplicate=store.duplicate(row['id']);token=store.proposal_hash(row)
                body+='<form method="post" action="/research-review/citation/'+row['id']+'/save"><input type="hidden" name="expected_hash" value="'+token+'">'
                if duplicate:
                    body+='<p>A matching URL is already on <a href="/research-desk/source/'+duplicate+'">this source card</a>. Linking keeps its title, synopsis and reading flags unchanged.</p><input type="hidden" name="title" value="'+esc(row['title'])+'"><button>Link citation to existing card</button>'
                else:
                    body+='<label>Source title<input name="title" maxlength="180" required value="'+esc(row['title'])+'"></label><label><input type="checkbox" style="width:auto;display:inline-block" name="must_read" value="true"> Flag for personal reading</label><label>Why I should read it<input name="read_reason" maxlength="500"></label><button>Save source card · 0 model requests</button>'
                body+='</form><form method="post" action="/research-review/citation/'+row['id']+'/dismiss"><input type="hidden" name="expected_hash" value="'+token+'"><p><button class="secondary">Dismiss suggestion</button></p></form>'
            body+='</section>'
        if not rows:body+='<p>No '+esc(status)+' citations on this page. After approving a web-research output, use its Collect cited source suggestions button in the research area.</p>'
        if page>1:body+='<a href="/research-review/area/'+area_id+'?status='+status+'&page='+str(page-1)+'">Previous</a> '
        if len(rows)==50:body+='<a href="/research-review/area/'+area_id+'?status='+status+'&page='+str(page+1)+'">Next</a>'
        return render(body,'Cited source suggestions')

    @app.post('/research-review/citation/{key}/save')
    def save(key:str,expected_hash:str=Form(...),title:str=Form(...),must_read:bool=Form(False),read_reason:str=Form('')):
        try:source_id=store.save_citation(key,expected_hash,title,must_read,read_reason)
        except (ValueError,OSError) as exc:error(exc)
        return go('/research-desk/source/'+source_id)

    @app.post('/research-review/citation/{key}/dismiss')
    def dismiss(key:str,expected_hash:str=Form(...)):
        row=candidate(key)
        try:store.dismiss(key,expected_hash)
        except ValueError as exc:error(exc)
        return go('/research-review/area/'+row['area_id'])

    @app.get('/research-review/job/{job_id}/synopsis')
    def preview(job_id:str):
        try:value=store.synopsis_preview(job_id)
        except (ValueError,OSError) as exc:error(exc)
        target=value['target'];body='<h1>Review synopsis for source card</h1>'+back(value['area']['id'])+'<p>Source: <a href="/research-desk/source/'+target['id']+'">'+esc(target['payload']['title'])+'</a> · <a href="/work/'+value['job']['project_id']+'">Approved project output</a></p><p>This updates only the synopsis after your confirmation. It preserves reading flags, file, URL and other card fields, and saves the previous contents in applied-synopsis history. No model requests or general-memory updates.</p><h2>Current saved synopsis</h2><pre>'+esc(target['payload']['synopsis'] or '(blank)')+'</pre>'
        proposed=value['text'] if len(value['text'])<=20000 else ''
        if not proposed:body+='<p>The output is too long for this editor. Read it in the project, then enter a reviewed synopsis below.</p>'
        elif len(proposed)>2500:body+='<p>The draft is '+str(len(proposed))+' characters. Shorten it to 2500 characters or fewer before applying; no text has been silently removed.</p>'
        body+='<form method="post" action="/research-review/job/'+job_id+'/apply"><input type="hidden" name="expected_output" value="'+value['output_hash']+'"><input type="hidden" name="expected_version" value="'+str(target['version'])+'"><label>Reviewed synopsis<textarea name="synopsis" maxlength="2500" required style="min-height:360px">'+esc(proposed)+'</textarea></label><button>Apply reviewed synopsis · 0 model requests</button></form>'
        return render(body,'Apply reviewed synopsis')

    @app.post('/research-review/job/{job_id}/apply')
    def apply(job_id:str,expected_output:str=Form(...),expected_version:int=Form(...),synopsis:str=Form(...)):
        try:source_id=store.apply_synopsis(job_id,expected_output,expected_version,synopsis)
        except (ValueError,OSError) as exc:error(exc)
        return go('/research-desk/source/'+source_id)

    @app.get('/research-review/source/{source_id}/history')
    def history(source_id:str):
        try:target=store.research.source(source_id);rows=store.history(source_id)
        except ValueError as exc:error(exc)
        body='<h1>Applied synopsis history</h1><p><a href="/research-desk/source/'+source_id+'">Back to source card</a></p><p>The 20 most recent applications are shown; older applications remain stored. Ordinary manual source-card edits do not create entries in this history.</p>'
        for row in rows:
            previous=json.loads(row['previous_json']);applied=json.loads(row['applied_json'])
            body+='<section class="card"><h2>Applied to source version '+str(row['previous_version'])+'</h2><p>'+esc(row['created_at'])+' · <a href="/work/'+row['project_id']+'">Originating project</a></p><h3>Previous synopsis</h3><pre>'+esc(previous['synopsis'] or '(blank)')+'</pre><h3>Reviewed synopsis applied</h3><pre>'+esc(applied['synopsis'])+'</pre></section>'
        if not rows:body+='<p>No project synopses applied yet.</p>'
        return render(body,'Synopsis history')
