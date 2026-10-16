"""Project pages alongside the existing local dashboard. Workers stay separate."""
import json
from fastapi import Form, HTTPException
from fastapi.responses import RedirectResponse
from superhuman.dashboard import app as base
from . import engine

app=base.app
original_page=base.page
def page(body,title='Projects'):
    return original_page('<p><a href="/">Task queue</a> · <a href="/projects">Project objectives</a></p>'+body,title)
# Existing dashboard routes resolve their module-global page at request time.
base.page=page
esc=base.esc

@app.get('/projects')
def projects():
    rows=''.join(f'<tr><td><a href="/projects/{esc(p["id"])}">{esc(p["objective"])}</a></td><td>{esc(p["status"])}</td><td>{p["used_calls"]}/{p["max_calls"]}</td></tr>' for p in engine.listing())
    options=''.join(f'<option value="{esc(k)}">{esc(v["name"])}</option>' for k,v in base.WORKSTREAMS.items())
    return page(f'<h1>Project objectives</h1><section class="panel"><form method="post" action="/projects"><label>Workstream<select name="workstream">{options}</select></label><label>Objective<input name="objective" maxlength="1000" required></label><label>Context and limits<textarea name="details" maxlength="12000"></textarea></label><label>API request limit<input name="max_calls" type="number" value="12" min="1" max="100"></label><button>Create objective</button></form></section><p>Creating an objective makes no API request. Planning uses one request. Workers run separately in your terminal.</p><table><tr><th>Objective</th><th>Status</th><th>API attempts</th></tr>{rows}</table>')

@app.post('/projects')
def create(workstream:str=Form(...),objective:str=Form(...),details:str=Form(''),max_calls:int=Form(12)):
    try:pid=engine.create(workstream,objective,details,max_calls)
    except ValueError as e:raise HTTPException(400,str(e)) from e
    return RedirectResponse('/projects/'+pid,status_code=303)

@app.get('/projects/{pid}')
def detail(pid:str):
    try:p=engine.get(pid)
    except ValueError as e:raise HTTPException(404,str(e)) from e
    tasks=''
    for t in p['tasks']:
        content=''
        if t['result_json']:
            try:_,content=engine._text(json.loads(t['result_json']))
            except (ValueError,OSError):content='Output unavailable.'
        controls=''
        if t['status']=='needs_review':
            controls=f'<form method="post" action="/projects/{esc(pid)}/review"><input type="hidden" name="task" value="{esc(t["id"])}"><label>Review note<input name="note" maxlength="2000"></label><button name="action" value="approve">Approve draft</button> <button name="action" value="reject">Reject draft</button></form>'
        tasks+=f'<section class="panel"><h2>{esc(t["id"])}: {esc(t["title"])}</h2><p>{esc(t["status"])} · Dependencies: {esc(t["deps"])}</p><p>{esc(t["error"])}</p><pre>{esc(content[:100000])}</pre>{controls}</section>'
    plan_controls=''
    if p['status'] in ('new','plan_failed'):
        plan_controls=f'<form method="post" action="/projects/{esc(pid)}/plan"><button>Generate plan (one API request)</button></form>'
    if p['status']=='plan_review':
        plan_controls=f'<form method="post" action="/projects/{esc(pid)}/approve-plan"><button>Approve local research/draft plan</button></form>'
    return page(f'<h1>{esc(p["objective"])}</h1><p>{esc(p["status"])} · API attempts {p["used_calls"]}/{p["max_calls"]}</p><p>{esc(p["details"])}</p>{plan_controls}<pre>{esc(p["plan_json"] or "No plan yet")}</pre><p>Worker command: python -m superhuman.projects.cli worker {esc(pid)}</p><p>Dependencies may use quality-passed but unapproved drafts as unverified references. Approval never authorizes external actions. Call caps are not currency budgets.</p>{tasks}')

@app.post('/projects/{pid}/plan')
def plan(pid:str):
    try:engine.generate_plan(pid)
    except Exception as e:raise HTTPException(400,'Planning stopped: '+type(e).__name__) from e
    return RedirectResponse('/projects/'+pid,status_code=303)

@app.post('/projects/{pid}/approve-plan')
def approve_plan(pid:str):
    try:engine.approve_plan(pid)
    except ValueError as e:raise HTTPException(400,str(e)) from e
    return RedirectResponse('/projects/'+pid,status_code=303)

@app.post('/projects/{pid}/review')
def review(pid:str,task:str=Form(...),action:str=Form(...),note:str=Form('')):
    try:engine.review(pid,task,action,note)
    except ValueError as e:raise HTTPException(400,str(e)) from e
    return RedirectResponse('/projects/'+pid,status_code=303)
