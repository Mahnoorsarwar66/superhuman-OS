"""Owner controls for ordinary independent review. No provider calls on routes."""
import json
from fastapi import Form, HTTPException
from fastapi.responses import RedirectResponse
from superhuman.navigation.shell import esc as E
from superhuman.departments.store import readonly
from superhuman.projects import engine as p
from . import reviews, store


def panel(task):
    entries=reviews.history(task['id'])
    body='<section><h2>Independent deliverable review</h2>'
    with readonly(p.DEFAULT_DB) as db:
        cfg=reviews.policy(db,task['id'])
        reviewer=reviews.assignment(db,task['id'])
        objective=reviews.objectives.for_task(db,task['id'])
    if not objective and not entries:return ''
    if reviewer:
        body+='<p>Reviewer assignment for <a href="/team/tasks/'+E(reviewer['source_task_id'])+'">this source deliverable</a>. Use the normal start control, then inspect and accept the saved assessment. Accepting a critique records its findings; it does not accept the source.</p>'
    elif objective and task['state']=='awaiting_review':
        rubric='\n'.join(json.loads(cfg['rubric_json'])) if cfg else task['acceptance']
        body+='<p>Assign a specialist who did not author this deliverable. The assignment shares this objective\'s remaining allowance. Enable workforce.review_source in that employee\'s permissions first. Once assigned, independent review becomes mandatory for this deliverable and its later revisions.</p><form method="post" action="/team/tasks/'+E(task['id'])+'/independent-review"><input type="hidden" name="version" value="'+str(task['version'])+'"><label>Reviewer<select name="reviewer">'
        for ident,(name,_) in store.EMPLOYEES.items():
            if ident not in ('twin',task['owner']):body+='<option value="'+E(ident)+'">'+E(name)+'</option>'
        body+='</select></label><label>Rubric: one criterion per line<textarea name="rubric" maxlength="6012" required'+(' readonly' if cfg else '')+'>'+E(rubric)+'</textarea></label><button>Assign independent review</button></form>'
    if cfg:
        body+='<p>Rubric version '+str(cfg['version'])+'; prior approval applies only to the artifact and criteria reviewed. Use Revise output to apply supported findings; inspect and approve continuation before execution.</p>'
    for entry in entries:
        body+='<details><summary>'+E(entry['reviewer'])+' / '+E(entry['verdict'] or 'assessment pending')+'</summary><p><a href="/team/tasks/'+E(entry['reviewer_task_id'])+'">Inspect reviewer assignment and evidence</a></p><p>Artifact fingerprint: '+E(entry['fingerprint'])+'</p><p>'+('Findings applied to a revision; historical assessment.' if entry['applied_revision'] else 'Review has not been applied to a revision.')+'</p><pre>'+E(json.dumps(json.loads(entry['report_json']),indent=2) if entry['report_json'] else 'No accepted assessment yet.')+'</pre></details>'
    return body+'</section>'


def install(app):
    @app.post('/team/tasks/{ident}/independent-review')
    def assign(ident:str,version:int=Form(...),reviewer:str=Form(...),rubric:str=Form(...)):
        try:
            if len(rubric)>6012:raise ValueError('Rubric exceeds the supported limit')
            task=reviews.assign(ident,version,reviewer,[line.strip() for line in rubric.splitlines() if line.strip()])
        except (ValueError,OSError) as exc:raise HTTPException(409,str(exc)) from exc
        return RedirectResponse('/team/tasks/'+task,status_code=303)
