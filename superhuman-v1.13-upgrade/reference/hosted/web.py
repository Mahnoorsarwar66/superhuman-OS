"""Separate authenticated entry point. The original local app is unchanged."""
import json
from fastapi import FastAPI,Form,HTTPException
from fastapi.responses import HTMLResponse,RedirectResponse
from superhuman.runtime import web as legacy,engine as runtime
from superhuman.projects import engine as projects
from superhuman.core.router import WORKSTREAMS,route_task
from . import config,jobs,views
from .boundary import Boundary


def options():return ''.join('<option value="'+views.esc(k)+'">'+views.esc(v['name'])+'</option>' for k,v in WORKSTREAMS.items())


def create_app(settings=None,configured=True):
    if settings is None and configured:
        try:settings=config.load()
        except (ValueError,OSError,KeyError):settings=None
    inner=FastAPI(title='Superhuman private workspace',docs_url=None,redoc_url=None,openapi_url=None)
    # Copy route objects only; don't remove the original app's local-only guard.
    inner.router.routes.extend(route for route in legacy.app.routes if not (
        getattr(route,'path','')=='/' and 'GET' in getattr(route,'methods',set()) or
        getattr(route,'path','') in ('/projects/{pid}/plan','/projects/{pid}/review') and 'POST' in getattr(route,'methods',set())))
    @inner.get('/')
    def home():
        state=runtime.status();worker=jobs.worker_status()
        online='Online' if worker['online'] else 'Offline'
        activity='Paused' if worker['paused'] else worker.get('activity','') or 'Waiting for worker'
        if activity=='api_key_required':activity='API key needs configuration'
        cards=''
        for item in state['projects']:
            cards+='<article class="card"><div class="row"><span class="badge">'+views.esc(views.label(item['status']))+'</span><small>'+str(item['used_calls'])+' / '+str(item['max_calls'])+' requests</small></div><h2><a href="/work/'+views.esc(item['id'])+'">'+views.esc(item['objective'])+'</a></h2>'+('<p class="muted">'+views.esc('; '.join(item['attention']))+'</p>' if item['attention'] else '')+'</article>'
        body='<p class="muted">YOUR WORK, IN ONE PLACE</p><h1>What needs moving forward?</h1>'
        body+='<section class="card"><div class="row"><div><strong>Background worker: '+online+'</strong><p class="muted">'+views.esc(activity)+'</p></div><form method="post" action="/worker/pause"><input type="hidden" name="paused" value="'+('false' if worker['paused'] else 'true')+'"><button class="secondary">'+('Resume work' if worker['paused'] else 'Pause new work')+'</button></form></div><small>Pausing leaves any task already running to finish.</small></section>'
        body+='<div class="grid"><section class="card"><h2>Give Superhuman a task</h2><form method="post" action="/tasks"><label>Workstream<select name="workstream">'+options()+'</select></label><label>Task type<select name="kind"><option value="collab">Prepare a draft</option><option value="research">Research with sources</option></select></label><label>What should be done?<textarea name="instruction" maxlength="12000" required></textarea></label><small>Drafting allows up to three model requests; research allows one. Your worker processes the task when available.</small><p><button>Create task</button></p></form></section>'
        body+='<section class="card"><h2>Plan a larger objective</h2><form method="post" action="/objectives"><label>Workstream<select name="workstream">'+options()+'</select></label><label>Objective<input name="objective" maxlength="1000" required></label><label>Context and requirements<textarea name="details" maxlength="12000"></textarea></label><label>Model-request limit<input name="max_calls" type="number" min="5" max="100" value="12" required></label><small>Preparing a plan uses one request. You review the plan before execution starts.</small><p><button>Create objective and prepare plan</button></p></form></section></div>'
        body+='<div class="row" style="margin-top:28px"><h2>Projects and tasks</h2><a href="/">Refresh</a></div>'+(cards or '<section class="card"><p>No tasks yet. Start with a clear instruction above.</p></section>')
        return HTMLResponse(views.page(body))
    @inner.post('/tasks')
    def task(workstream:str=Form(...),kind:str=Form(...),instruction:str=Form(...)):
        instruction=instruction.strip()
        if not instruction:raise HTTPException(400,'Provide an instruction')
        try:pid=runtime.enqueue(kind,workstream,instruction.splitlines()[0][:180],instruction)
        except ValueError as exc:raise HTTPException(400,str(exc)) from exc
        return RedirectResponse('/work/'+pid,status_code=303)
    @inner.post('/objectives')
    def objective(workstream:str=Form(...),objective:str=Form(...),details:str=Form(''),max_calls:int=Form(12)):
        if max_calls<5:raise HTTPException(400,'Use at least five requests for planning and a minimal project')
        try:
            pid=projects.create(workstream,objective,details,max_calls)
            jobs.request_plan(pid)
        except ValueError as exc:raise HTTPException(400,str(exc)) from exc
        return RedirectResponse('/work/'+pid,status_code=303)
    @inner.get('/work/{pid}')
    def project(pid:str):
        try:p=projects.get(pid)
        except ValueError as exc:raise HTTPException(404,str(exc)) from exc
        body='<p class="muted">'+views.esc(views.label(p['status']))+'</p><h1>'+views.esc(p['objective'])+'</h1><p>'+views.esc(p['details'])+'</p><p class="muted">'+str(p['used_calls'])+' / '+str(p['max_calls'])+' model requests used</p><div class="stack"><a class="button secondary" href="/work/'+views.esc(pid)+'">Refresh</a><a class="button secondary" href="/projects/'+views.esc(pid)+'">Detailed review and editing</a></div>'
        if p['status'] in ('new','plan_failed'):
            body+='<section class="card"><p>Planning runs in the background after you request it.</p><form method="post" action="/projects/'+views.esc(pid)+'/plan"><button>Request plan</button></form></section>'
        if p['status']=='plan_review':
            body+='<section class="card"><h2>Review the plan</h2>'
            for t in p['tasks']:body+='<h3>'+views.esc(t['title'])+'</h3><p>'+views.esc(t['details'])+'</p><p class="muted">Depends on: '+views.esc(', '.join(json.loads(t['deps'])) or 'No other task')+'</p>'
            body+='<form method="post" action="/projects/'+views.esc(pid)+'/approve-plan"><button>Approve plan for execution</button></form></section>'
        for t in p['tasks']:
            body+='<section class="card"><div class="row"><h2>'+views.esc(t['title'])+'</h2><span class="badge">'+views.esc(views.label(t['status']))+'</span></div>'
            if t['error']:body+='<p class="error">'+views.esc(t['error'])+'</p>'
            if t['result_json']:
                try:_,text=projects._text(json.loads(t['result_json']))
                except (ValueError,OSError):text='The saved output could not be verified. Inspect it before retrying.'
                body+='<pre>'+views.esc(text[:20000])+'</pre><p><a href="/projects/'+views.esc(pid)+'/tasks/'+views.esc(t['id'])+'/download">Download full text</a></p>'
                if len(text)>20000:body+='<p>Preview shortened. Use detailed review to inspect the saved artifact.</p>'
            if t['status']=='needs_review':
                body+='<form method="post" action="/work/'+views.esc(pid)+'/review"><input type="hidden" name="task" value="'+views.esc(t['id'])+'"><label>Review note<input name="note" maxlength="2000"></label><div class="stack"><button name="action" value="approve">Approve</button><button class="secondary" name="action" value="reject">Request changes</button></div></form>'
            body+='</section>'
        from superhuman.knowledge.web import feedback_link
        body += feedback_link(pid)
        return HTMLResponse(views.page(body,p['objective']))
    @inner.post('/projects/{pid}/plan')
    def queue_plan(pid:str):
        try:jobs.request_plan(pid)
        except ValueError as exc:raise HTTPException(400,str(exc)) from exc
        return RedirectResponse('/work/'+pid,status_code=303)
    @inner.post('/projects/{pid}/review')
    @inner.post('/work/{pid}/review')
    def review(pid:str,task:str=Form(...),action:str=Form(...),note:str=Form('')):
        try:runtime.review(pid,task,action,note)
        except ValueError as exc:raise HTTPException(400,str(exc)) from exc
        return RedirectResponse('/work/'+pid,status_code=303)
    @inner.post('/worker/pause')
    def pause(paused:str=Form(...)):
        if paused not in ('true','false'):raise HTTPException(400,'Invalid worker state')
        jobs.pause(paused=='true');return RedirectResponse('/',status_code=303)
    # knowledge-v110
    from superhuman.knowledge.web import install as install_knowledge
    install_knowledge(inner)
    # dialogue-v111
    from superhuman.dialogue.web import install as install_dialogue
    install_dialogue(inner)
    from superhuman.mail.web import install as install_mail
    install_mail(inner)
    return Boundary(inner,settings,views.login)


app=create_app()
