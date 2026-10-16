"""Local tools UI. Uploaded files stay in task workspaces, not identity memory."""
import json
from pathlib import Path
from fastapi import Form, File, UploadFile, HTTPException
from fastapi.responses import RedirectResponse
from superhuman.projects import studio
from . import local

app=studio.app;esc=studio.esc;original_page=studio.page

def page(body,title='Workspace',active='projects'):
    response=original_page(body,title,active)
    html=response.body.decode('utf-8')
    html=html.replace('</nav>','<a href="/tools"'+(' aria-current="page"' if active=='tools' else '')+'><span class="nav-icon" aria-hidden="true">◇</span>Local tools</a></nav>',1)
    response.body=html.encode('utf-8');response.headers['content-length']=str(len(response.body));return response
studio.page=page;studio.review.web.page=page
studio.base.page=lambda body,title='Task queue':page(body,title,'queue')

original_task_html=studio.review.task_html
def task_html(pid,task):
    html=original_task_html(pid,task)
    metadata=studio.review.data(task.get('result_json'),{})
    if metadata.get('local_sources'):
        html+='<details><summary>Local source files recorded for this draft</summary><pre>'+esc(json.dumps(metadata['local_sources'],indent=2))+'</pre></details>'
    return html
studio.review.task_html=task_html

def options(project):
    return ''.join('<option value="'+esc(key)+'"'+(' selected' if key==project else '')+'>'+esc(value['name'])+'</option>' for key,value in studio.base.WORKSTREAMS.items())

def render(project,message=''):
    folder=local.inputs(project);files=[p.name for p in sorted(folder.iterdir()) if p.is_file() and not p.is_symlink() and p.suffix.lower() in local.FORMATS and not p.name.startswith('.')]
    choices=''.join('<option>'+esc(name)+'</option>' for name in files)
    rows=''.join('<tr><td>'+esc(name)+'</td><td><code>[[file:'+esc(name)+']]</code></td></tr>' for name in files)
    hidden='<input type="hidden" name="project" value="'+esc(project)+'">'
    return page('<div class="eyebrow">Practical capabilities</div><h1>Work with your materials.</h1><p class="intro">Read files, find details and check numbers. These tools run locally without model requests. Files are task sources and are not added to permanent memory.</p>'+message+'<form method="get" action="/tools"><label>Workstream<select name="project">'+options(project)+'</select></label><button>Open workspace</button></form><div class="grid" style="margin-top:24px"><section class="panel"><h2>Add a source file</h2><form method="post" action="/tools/upload" enctype="multipart/form-data">'+hidden+'<label>PDF, DOCX, XLSX, TXT, MD, CSV or JSON<input type="file" name="upload" accept=".pdf,.docx,.xlsx,.txt,.md,.csv,.json" required></label><p class="muted">Maximum 10 MB. Existing filenames are preserved; upload under a new name to add a revision.</p><button>Upload to this workspace</button></form></section><section class="panel"><h2>Inspect or profile</h2><form method="post" action="/tools/run">'+hidden+'<label>File<select name="value" required>'+choices+'</select></label><label>Operation<select name="tool"><option value="inspect_file">Read file contents</option><option value="profile_table">Profile a CSV table</option></select></label><button>Run local tool</button></form></section><section class="panel"><h2>Find a detail</h2><form method="post" action="/tools/run">'+hidden+'<input type="hidden" name="tool" value="search_files"><label>Text to find<input name="value" maxlength="200" required></label><button>Search this workspace</button></form></section><section class="panel"><h2>Check arithmetic</h2><form method="post" action="/tools/run">'+hidden+'<input type="hidden" name="tool" value="calculate"><label>Expression<input name="value" maxlength="500" placeholder="(2500 + 750) / 3" required></label><p class="muted">Numbers, parentheses and + − × ÷, typed as + - * /.</p><button>Calculate</button></form></section></div><section class="panel" style="margin-top:24px"><h2>Source files in this workspace</h2>'+('<table><tr><th>File</th><th>Task attachment marker</th></tr>'+rows+'</table>' if files else '<p>No source files uploaded yet.</p>')+'<p>To use a file in a task, copy its marker into the instructions of a project in the same workstream. The drafting and research runners read the file before requesting a model response and record its hash and extraction run. Reading a file locally is free; subsequent model requests use the usual budget.</p><p class="muted">PDFs need selectable text; OCR is not included. Excel formulas are not recalculated. Extraction and context limits are stated in results.</p></section>','Local tools','tools')

@app.get('/tools')
def tools(project:str='marketing'):
    try:return render(project)
    except (ValueError,OSError) as exc:raise HTTPException(400,str(exc)) from exc

@app.post('/tools/upload')
def upload(project:str=Form(...),upload:UploadFile=File(...)):
    try:
        local.store_bytes(project,upload.filename or '',upload.file.read(local.MAX_BYTES+1))
    except (ValueError,OSError) as exc:raise HTTPException(400,str(exc)) from exc
    return RedirectResponse('/tools?project='+project,status_code=303)

@app.post('/tools/run')
def run(project:str=Form(...),tool:str=Form(...),value:str=Form(...)):
    if len(value)>500:raise HTTPException(400,'Input too long')
    try:
        key='expression' if tool=='calculate' else 'query' if tool=='search_files' else 'filename'
        result=local.execute(project,tool,**{key:value})
        content=result.get('result',{})
        if result['status']!='completed':preview='<p>'+esc(result.get('error','Tool failed'))+'</p>'
        elif tool=='inspect_file':preview='<pre>'+esc(content['text'])+'</pre>'
        elif tool=='calculate':preview='<h2>'+esc(content['result'])+'</h2><p>'+esc(content['expression'])+'</p>'
        else:preview='<pre>'+esc(json.dumps(content,indent=2,ensure_ascii=False))+'</pre>'
        warnings=''.join('<p>'+esc(warning)+'</p>' for warning in content.get('warnings',[]))
        return render(project,'<section class="panel"><h2>'+('Tool result' if result['status']=='completed' else 'Tool stopped')+'</h2>'+preview+warnings+'<details><summary>Operation record</summary><pre>'+esc(json.dumps(result,indent=2,ensure_ascii=False))+'</pre></details></section>')
    except (ValueError,OSError) as exc:raise HTTPException(400,str(exc)) from exc
