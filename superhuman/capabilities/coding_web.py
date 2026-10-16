"""Coding workspaces in the existing local dashboard."""
import json
from pathlib import Path
from fastapi import Form,File,UploadFile,HTTPException
from fastapi.responses import RedirectResponse,FileResponse
from . import document_web as documents, coding as c, web as toolsweb

app=documents.app;esc=documents.esc;old_page=documents.page

def page(body,title='Workspace',active='projects'):
    response=old_page(body,title,active);html=response.body.decode('utf-8')
    html=html.replace('</nav>','<a href="/coding"'+(' aria-current="page"' if active=='coding' else '')+'><span class="nav-icon" aria-hidden="true">⌘</span>Coding</a></nav>',1)
    response.body=html.encode();response.headers['content-length']=str(len(response.body));return response

documents.page=page;toolsweb.page=page;toolsweb.studio.page=page;toolsweb.studio.review.web.page=page;toolsweb.studio.base.page=lambda body,title='Task queue':page(body,title,'queue')

def render(project,sid=None,name=None,message=''):
    choices=toolsweb.options(project);hidden='<input type="hidden" name="project" value="'+esc(project)+'">'
    body='<div class="eyebrow">Inspect and improve code</div><h1>A separate place to build.</h1><p class="intro">Work on a copy, review changes, check Python syntax and explicitly run selected tests. Your original source files are preserved.</p>'+message
    body+='<form method="get" action="/coding"><label>Workstream<select name="project">'+choices+'</select></label><button>Open workspace</button></form>'
    if not sid:
        rows=''
        for folder in sorted(c.root(project).iterdir(),reverse=True):
            if folder.is_symlink() or not folder.is_dir():continue
            try:_,record=c.session(project,folder.name)
            except (ValueError,OSError):continue
            rows+='<p><a href="/coding?project='+esc(project)+'&amp;sid='+esc(record['id'])+'">'+esc(record['label'])+'</a> <span class="muted">'+esc(record['created_at'][:16])+' UTC</span></p>'
        body+='<div class="grid" style="margin-top:24px"><section class="panel"><h2>Try the example</h2><p>A two-file Python project with a function and two unit tests. Start here to check the workflow.</p><form method="post" action="/coding/demo">'+hidden+'<button>Create example workspace</button></form></section><section class="panel"><h2>Import a Python project</h2><form method="post" action="/coding/import" enctype="multipart/form-data">'+hidden+'<label>Workspace title<input name="label" maxlength="120" required></label><label>ZIP file<input type="file" name="upload" accept=".zip" required></label><p class="muted">Up to 100 supported source files and 5 MB expanded content. Environment files, dependency folders and unsupported files are excluded. No source code is executed during import.</p><button>Import separate copy</button></form></section></div><section class="panel" style="margin-top:24px"><h2>Your coding workspaces</h2>'+ (rows or '<p>No coding workspaces yet.</p>')+'</section>'
    else:
        snapshot=c.inspect(project,sid);folder,_=c.session(project,sid)
        files=''.join('<tr><td><a href="/coding?project='+esc(project)+'&amp;sid='+sid+'&amp;name='+esc(file['name'])+'">'+esc(file['name'])+'</a></td><td>'+('Changed' if file['changed'] else 'Original copy')+'</td><td>'+str(file['bytes'])+'</td></tr>' for file in snapshot['files'])
        body+='<section class="panel" style="margin-top:24px"><h2>'+esc(snapshot['label'])+'</h2><table><tr><th>File</th><th>State</th><th>Bytes</th></tr>'+files+'</table><div class="stack"><form method="post" action="/coding/syntax">'+hidden+'<input type="hidden" name="sid" value="'+sid+'"><button>Check Python syntax</button></form><form method="post" action="/coding/package">'+hidden+'<input type="hidden" name="sid" value="'+sid+'"><button>Create review package</button></form></div></section>'
        if name:
            current=c.read(project,sid,name)
            body+='<section class="panel" style="margin-top:24px"><h2>'+esc(name)+'</h2><form method="post" action="/coding/edit">'+hidden+'<input type="hidden" name="sid" value="'+sid+'"><input type="hidden" name="name" value="'+esc(name)+'"><input type="hidden" name="expected" value="'+current['sha256']+'"><label>Working copy<textarea name="text" maxlength="200000" style="min-height:400px;font-family:Consolas,monospace" required>'+esc(current['text'])+'</textarea></label><label>Change note<input name="note" maxlength="2000"></label><button name="action" value="preview">Preview diff</button> <button name="action" value="save">Save working copy</button></form></section>'
        runtime=c.runtime()
        body+='<section class="panel" style="margin-top:24px"><h2>Run a selected test module</h2><p>'+esc('Container runtime is ready.' if runtime['ready'] else runtime['reason'])+'</p><form method="post" action="/coding/tests">'+hidden+'<input type="hidden" name="sid" value="'+sid+'"><label>Unittest module<input name="module" placeholder="test_calculator" required maxlength="180"></label><label><input type="checkbox" name="confirmed" value="yes" required style="width:auto;display:inline"> I authorize executing this test module in the restricted container.</label><p class="muted">No network, read-only source snapshot, 30-second limit. Standard-library Python only. Missing Docker or image is reported as not run.</p><button>Run selected tests</button></form></section>'
        body+='<details><summary>All changes from original</summary><pre>'+esc(c.full_diff(project,sid) or 'No changes yet.')+'</pre></details>'
        events=[]
        for path in (folder/'events').glob('*.json'):
            events.append(json.loads(path.read_text(encoding='utf-8')))
        events.sort(key=lambda event:event['created_at'],reverse=True)
        body+='<section class="panel"><h2>Recent checks and changes</h2>'+(''.join('<details><summary>'+esc(event['kind'])+' · '+esc(event.get('status','recorded'))+' · '+esc(event['created_at'][:19])+' UTC</summary><pre>'+esc(json.dumps(event,indent=2,ensure_ascii=False))+'</pre></details>' for event in events[:20]) or '<p>No checks or edits recorded yet.</p>')+'</section>'
    return page(body,'Coding workspace','coding')

def failure(exc):return HTTPException(400,str(exc))

@app.get('/coding')
def home(project:str='marketing',sid:str|None=None,name:str|None=None):
    try:return render(project,sid,name)
    except (ValueError,OSError) as exc:raise failure(exc) from exc

@app.post('/coding/demo')
def demo(project:str=Form(...)):
    try:
        record=c.demo(project);return RedirectResponse('/coding?project='+project+'&sid='+record['id'],status_code=303)
    except (ValueError,OSError) as exc:raise failure(exc) from exc

@app.post('/coding/import')
def import_source(project:str=Form(...),label:str=Form(...),upload:UploadFile=File(...)):
    try:
        record=c.from_zip(project,label,upload.file.read(10_000_001))
        message='<section class="panel"><h2>Imported copy</h2><p>'+str(len(record['original_hashes']))+' source files copied.</p><details><summary>Skipped files</summary><pre>'+esc('\n'.join(record['skipped_files']) or 'None')+'</pre></details></section>'
        return render(project,record['id'],message=message)
    except (ValueError,OSError,UnicodeError,zipfile.BadZipFile) as exc:raise failure(exc) from exc

import zipfile

@app.post('/coding/syntax')
def syntax(project:str=Form(...),sid:str=Form(...)):
    try:
        record=c.syntax(project,sid)
        return render(project,sid,message='<section class="panel"><h2>Syntax '+esc(record['status'])+'</h2><pre>'+esc(json.dumps(record,indent=2))+'</pre></section>')
    except (ValueError,OSError) as exc:raise failure(exc) from exc

@app.post('/coding/edit')
def edit(project:str=Form(...),sid:str=Form(...),name:str=Form(...),text:str=Form(''),expected:str=Form(...),note:str=Form(''),action:str=Form(...)):
    try:
        if action=='preview':
            proposal=c.preview(project,sid,name,text,expected)
            return page('<h1>Proposed change</h1><pre>'+esc(proposal['diff'] or 'No changes.')+'</pre><form method="post" action="/coding/edit"><input type="hidden" name="project" value="'+esc(project)+'"><input type="hidden" name="sid" value="'+sid+'"><input type="hidden" name="name" value="'+esc(name)+'"><input type="hidden" name="expected" value="'+esc(expected)+'"><label>Proposed source<textarea name="text" style="min-height:300px;font-family:Consolas,monospace">'+esc(text)+'</textarea></label><label>Change note<input name="note" maxlength="2000" required value="'+esc(note)+'"></label><button name="action" value="save">Save working copy</button></form>','Proposed change','coding')
        if action!='save':raise ValueError('Unknown edit action')
        c.edit(project,sid,name,text,expected,note)
        return render(project,sid,name,message='<p>Working copy saved. Earlier checks refer to their recorded source hashes; run checks again after edits.</p>')
    except (ValueError,OSError) as exc:raise failure(exc) from exc

@app.post('/coding/tests')
def tests(project:str=Form(...),sid:str=Form(...),module:str=Form(...),confirmed:str=Form('')):
    try:
        result=c.run_tests(project,sid,module,confirmed=='yes')
        return render(project,sid,message='<section class="panel"><h2>Tests '+esc(result['status'])+'</h2><pre>'+esc(json.dumps(result,indent=2))+'</pre></section>')
    except (ValueError,OSError) as exc:raise failure(exc) from exc

@app.post('/coding/package')
def package(project:str=Form(...),sid:str=Form(...)):
    try:
        path=c.package(project,sid)
        return FileResponse(path,media_type='application/zip',filename='coding-review-'+sid+'.zip')
    except (ValueError,OSError) as exc:raise failure(exc) from exc
