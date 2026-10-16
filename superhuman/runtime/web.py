"""Read-only runtime overview alongside all existing v1.7 pages. Local only."""
import json
from superhuman.capabilities import coding_web as coding
from . import engine as r

app=coding.app
esc=coding.esc
_previous_page=coding.page

def page(body,title='Workspace',active='projects'):
    response=_previous_page(body,title,active)
    html=response.body.decode('utf-8').replace('</nav>','<a href="/runtime"><span class="nav-icon" aria-hidden="true">↻</span>Execution</a></nav>',1)
    response.body=html.encode('utf-8');response.headers['content-length']=str(len(response.body))
    return response

# Keep all v1.7 rendering and mutation routes; add navigation only.
coding.page=page
coding.documents.page=page
coding.toolsweb.page=page
coding.toolsweb.studio.page=page
coding.toolsweb.studio.review.web.page=page
coding.toolsweb.studio.base.page=lambda body,title='Task queue':page(body,title,'queue')


@app.get('/runtime')
def runtime_page():
    state=r.status()
    rows=''
    for item in state['projects']:
        rows+='<tr><td><a href="/projects/'+esc(item['id'])+'">'+esc(item['objective'])+'</a></td><td>'+esc(item['status'])+'</td><td>'+str(item['used_calls'])+'/'+str(item['max_calls'])+'</td><td>'+esc('; '.join(item['attention']))+'</td></tr>'
    body='<div class="eyebrow">Unified execution</div><h1>One place to see the work.</h1>'
    body+='<p>The worker advances approved plans and imports never-attempted queue jobs. Quality-blocked work waits for correction. Final deliverables wait for review.</p>'
    body+='<section class="panel"><h2>Run the worker</h2><pre>python -m superhuman.runtime.cli work --max-tasks 20</pre><p>To wait for incoming work, add <code>--watch</code>. The task limit still applies. The web page itself starts no model requests.</p></section>'
    body+='<table><tr><th>Objective</th><th>Status</th><th>API attempts</th><th>Attention</th></tr>'+rows+'</table>'
    body+='<section class="panel"><h2>Legacy queue</h2><pre>'+esc(json.dumps(state['legacy_queue'],indent=2))+'</pre><p>Delegated queue rows are references. Open their canonical objective above for current progress and review.</p></section>'
    body+='<section class="panel"><h2>Recent activity</h2><pre>'+esc(json.dumps(r.history(limit=30),indent=2))+'</pre></section>'
    return coding.page(body,'Unified execution','projects')


@app.get('/runtime/state')
def runtime_state():return r.status()
