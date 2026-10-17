"""Document generation UI and verified project-draft exports."""
import json
import hashlib
from fastapi import Form,HTTPException
from fastapi.responses import FileResponse
from . import web as toolsweb,local,exports
from superhuman.projects import engine as e

app=toolsweb.app;esc=toolsweb.esc;old_page=toolsweb.page

def page(body,title='Workspace',active='projects'):
    response=old_page(body,title,active);html=response.body.decode('utf-8')
    html=html.replace('</nav>','<a href="/documents"'+(' aria-current="page"' if active=='documents' else '')+'><span class="nav-icon" aria-hidden="true">▤</span>Documents</a></nav>',1)
    response.body=html.encode();response.headers['content-length']=str(len(response.body));return response

toolsweb.page=page;toolsweb.studio.page=page;toolsweb.studio.review.web.page=page
toolsweb.studio.base.page=lambda body,title='Task queue':page(body,title,'queue')
old_task_html=toolsweb.studio.review.task_html

def task_html(pid,task):
    html=old_task_html(pid,task)
    if task['status'] in ('needs_review','approved') and task.get('result_json'):
        html+='<details><summary>Download as Word or PDF</summary><p>Creates a local file from the stored deliverable. Exporting does not approve a draft or verify its facts.</p><form method="post" action="/documents/project/'+esc(pid)+'/'+esc(task['id'])+'"><input type="hidden" name="version" value="'+toolsweb.studio.review.token(task)+'"><label>File type<select name="format"><option value="docx">Word document</option><option value="pdf">PDF document</option></select></label><button>Create download</button></form></details>'
    return html

toolsweb.studio.review.task_html=task_html

def result(record):
    link='/documents/download/'+record['project']+'/'+record['export_id']
    warnings=''.join('<p>'+esc(warning)+'</p>' for warning in record['warnings'])
    return page('<div class="eyebrow">Document created</div><h1>'+esc(record['title'])+'</h1><p>Your '+esc(record['format'].upper())+' file is ready. No model requests were made.</p><p><a class="button" href="'+link+'">Download file</a></p>'+warnings+'<details><summary>Source and validation record</summary><pre>'+esc(json.dumps(record,indent=2,ensure_ascii=False))+'</pre></details><p><a href="/documents?project='+esc(record['project'])+'">Create another document</a></p>','Document ready','documents')

@app.get('/documents')
def documents(project:str='marketing'):
    try:
        root=local.workspace(project);choices=toolsweb.options(project)
        files=[path.name for path in sorted(local.inputs(project).iterdir()) if path.is_file() and not path.is_symlink() and path.suffix.lower()=='.csv']
        options=''.join('<option>'+esc(name)+'</option>' for name in files)
        records=[];folder=root/'exports'
        if folder.is_dir() and not folder.is_symlink():
            for path in sorted(folder.iterdir(),key=lambda x:x.name):
                if path.is_symlink() or not path.is_dir():continue
                try:_,record=exports.artifact(project,path.name);records.append(record)
                except (ValueError,OSError):continue
        records=sorted(records,key=lambda x:x['created_at'],reverse=True)[:30]
        recent=''.join('<tr><td>'+esc(r['title'])+'</td><td>'+esc(r['format'].upper())+'</td><td>'+esc(r['created_at'][:16].replace('T',' '))+' UTC</td><td><a href="/documents/download/'+project+'/'+r['export_id']+'">Download</a></td></tr>' for r in records)
        return page('<div class="eyebrow">Create useful deliverables</div><h1>Documents you can use.</h1><p class="intro">Create Word and PDF files from text, or turn a CSV into an Excel workbook. To export a project draft directly, open its project and expand Download as Word or PDF.</p><form method="get" action="/documents"><label>Workstream<select name="project">'+choices+'</select></label><button>Open workspace</button></form><div class="grid" style="margin-top:24px"><section class="panel"><h2>Word or PDF from text</h2><form method="post" action="/documents/create"><input type="hidden" name="project" value="'+esc(project)+'"><label>Document title<input name="title" maxlength="200" required></label><label>Content<textarea name="text" maxlength="100000" style="min-height:260px" required></textarea></label><label>File type<select name="format"><option value="docx">Word document</option><option value="pdf">PDF document</option></select></label><p class="muted">Blank lines separate paragraphs. Basic # headings and **bold** are supported. Tables and images need a later layout capability.</p><button>Create document</button></form></section><section class="panel"><h2>Excel from CSV</h2><form method="post" action="/documents/csv"><input type="hidden" name="project" value="'+esc(project)+'"><label>Uploaded CSV<select name="filename" required>'+options+'</select></label><label>Workbook title<input name="title" maxlength="200" required></label><label>Values<select name="numeric"><option value="false">Preserve all values as text</option><option value="true">Convert plain numbers up to 15 digits</option></select></label><p class="muted">Upload CSV files in Local tools first. Formulas remain text. Leading zeros are preserved. The first row becomes the header.</p><button>Create workbook</button></form></section></div><section class="panel" style="margin-top:24px"><h2>Recent exports</h2>'+('<table><tr><th>Document</th><th>Format</th><th>Created</th><th>File</th></tr>'+recent+'</table>' if records else '<p>No exports in this workspace yet.</p>')+'</section>','Documents','documents')
    except (ValueError,OSError) as exc:raise HTTPException(400,str(exc)) from exc

@app.post('/documents/create')
def create(project:str=Form(...),title:str=Form(...),text:str=Form(...),format:str=Form(...)):
    if format not in ('docx','pdf'):raise HTTPException(400,'Choose Word or PDF')
    try:return result(exports.generate(project,format,title,text))
    except ImportError as exc:raise HTTPException(400,'Install document dependencies: python -m pip install python-docx reportlab openpyxl') from exc
    except (ValueError,OSError) as exc:raise HTTPException(400,str(exc)) from exc

@app.post('/documents/csv')
def csv_export(project:str=Form(...),title:str=Form(...),filename:str=Form(...),numeric:str=Form('false')):
    try:
        if numeric not in ('true','false'):raise ValueError('Invalid numeric conversion choice')
        path=local.file_for(project,filename)
        if path.suffix.lower()!='.csv':raise ValueError('Choose a CSV file')
        payload=path.read_bytes()
        import hashlib
        source={'kind':'workspace_csv','filename':filename,'sha256':hashlib.sha256(payload).hexdigest()}
        return result(exports.generate(project,'xlsx',title,payload.decode('utf-8-sig'),source,numeric=='true'))
    except ImportError as exc:raise HTTPException(400,'Install document dependencies: python -m pip install python-docx reportlab openpyxl') from exc
    except (ValueError,OSError,UnicodeError) as exc:raise HTTPException(400,str(exc)) from exc

@app.post('/documents/project/{pid}/{tid}')
def project_export(pid:str,tid:str,version:str=Form(...),format:str=Form(...)):
    try:
        project=e.get(pid);task=next((t for t in project['tasks'] if t['id']==tid),None)
        if not task:raise ValueError('Task not found')
        if version!=toolsweb.studio.review.token(task):raise HTTPException(409,'Draft changed. Reload before exporting.')
        if task['status'] not in ('needs_review','approved'):raise ValueError('Export a quality-passed draft or approved deliverable')
        if format not in ('docx','pdf'):raise ValueError('Choose Word or PDF')
        metadata=json.loads(task['result_json']);_,text=e._text(metadata)
        return result(exports.generate(project['workstream'],format,task['title'],text,{'kind':'project_draft','project_id':pid,'task_id':tid,'status_at_export':task['status'],'sha256':hashlib.sha256(text.encode()).hexdigest(),'source_files':metadata.get('local_sources',[])}))
    except ImportError as exc:raise HTTPException(400,'Install document dependencies: python -m pip install python-docx reportlab openpyxl') from exc
    except (ValueError,OSError,UnicodeError) as exc:raise HTTPException(400,str(exc)) from exc

@app.get('/documents/download/{project}/{rid}')
def download(project:str,rid:str):
    try:
        path,record=exports.artifact(project,rid)
        types={'pdf':'application/pdf','docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document','xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}
        return FileResponse(path,media_type=types[record['format']],filename=record['filename'])
    except (ValueError,OSError) as exc:raise HTTPException(404,'Export is missing or changed') from exc
