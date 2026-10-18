"""Owner review screens for prepared objective changes."""
import json
from uuid import uuid4
from fastapi import Form, HTTPException, Request
from fastapi.responses import RedirectResponse, FileResponse
from superhuman.navigation.shell import esc as E
from . import objectives, store, workplans, budget


def links(obj):
    body = '<p><a href="/team/objectives/'+E(obj['id'])+'/changes/new">Review changes to started work</a></p>'
    from superhuman.departments.store import readonly
    from superhuman.projects import engine as p
    with readonly(p.DEFAULT_DB) as db:
        changes = db.execute('SELECT id,state,applied_plan FROM workforce_plan_changes WHERE objective_id=? ORDER BY created_at DESC', (obj['id'],)).fetchall()
    for change in changes:
        body += '<p><a href="/team/objectives/'+E(obj['id'])+'/changes/'+E(change['id'])+'">Impact assessment · '+E(change['state'])+(' · Plan '+str(change['applied_plan']) if change['applied_plan'] else '')+'</a></p>'
    return body


def area(label, name, value='', maximum=5000):
    return '<label>'+label+'<textarea name="'+E(name)+'" maxlength="'+str(maximum)+'" required>'+E(value)+'</textarea></label>'


def hidden(name, value):
    return '<input type="hidden" name="'+E(name)+'" value="'+E(value)+'">'


def install(app):
    from .web import page

    @app.get('/team/objectives/{ident}/changes/new')
    def new_change(ident:str):
        try:obj=objectives.get(ident)
        except ValueError as exc:raise HTTPException(404,str(exc)) from exc
        plan=obj['plans'][-1]
        body='<h1>Review a change to this objective</h1><p>Pause the objective first and let current work settle. Reconcile any uncertain spending. Preparing an assessment does not change work or authorize execution.</p><p><a href="/team/objectives/'+E(ident)+'">Objective controls and allowances</a></p>'
        body+='<form method="post" action="/team/objectives/'+E(ident)+'/changes">'+hidden('version',obj['version'])+hidden('submission_key',uuid4().hex)
        body+=area('Replacement objective and root assignment brief','brief',plan['brief'],4500)+area('Objective and root success criteria','criteria',plan['criteria'],1500)+area('Reason for the change and expected impact','impact','',2000)
        for member in obj['tasks']:
            task=store.task(member['id']);key=task['id'];retain=task['state']=='completed'
            body+='<fieldset><legend>'+E(task['title'])+'</legend><p>'+E(task['state'])+' · <a href="/team/tasks/'+E(key)+'">Inspect assignment and evidence</a></p><label>Impact decision<select name="disposition_'+E(key)+'"><option value="revise"'+('' if retain else ' selected')+'>Revise and require fresh approval</option><option value="retain"'+(' selected' if retain else '')+'>Retain accepted completed work</option></select></label>'
            if key!=obj['root_task_id']:
                body+=area('Complete assignment brief','brief_'+key,task['instruction'])+area('Assignment success criteria','criteria_'+key,task['acceptance'],1500)
            body+=area('Why this work is affected, or why its accepted output remains valid','reason_'+key,'',2000)+'</fieldset>'
        body+='<p>Revise every assignment that depends on changed work, including affected handoff context. Retained work must already be accepted and keep its brief and criteria. Existing request, step, spending and time limits remain in force.</p><button>Prepare impact assessment</button></form>'
        return page(body,'Prepare objective change')

    @app.post('/team/objectives/{ident}/changes')
    async def prepare_change(ident:str,request:Request):
        form=await request.form()
        try:
            obj=objectives.get(ident);assignments={}
            for member in obj['tasks']:
                task=store.task(member['id']);key=task['id'];disposition=str(form['disposition_'+key])
                root=key==obj['root_task_id']
                assignments[key]=dict(disposition=disposition,
                    brief=str(form['brief']) if root and disposition=='revise' else task['instruction'] if root else str(form['brief_'+key]),
                    criteria=str(form['criteria']) if root and disposition=='revise' else task['acceptance'] if root else str(form['criteria_'+key]),
                    reason=str(form['reason_'+key]))
            change=workplans.prepare(ident,int(str(form['version'])),str(form['brief']),str(form['criteria']),str(form['impact']),assignments,str(form['submission_key']))
        except (ValueError,KeyError) as exc:raise HTTPException(409,str(exc)) from exc
        return RedirectResponse('/team/objectives/'+ident+'/changes/'+change,status_code=303)

    @app.get('/team/objectives/{ident}/changes/{change_id}')
    def review_change(ident:str,change_id:str):
        try:change=workplans.get(change_id)
        except ValueError as exc:raise HTTPException(404,str(exc)) from exc
        if change['objective_id']!=ident:raise HTTPException(404,'Impact assessment not found in this objective')
        payload=json.loads(change['payload_json']);snapshot=json.loads(change['snapshot_json']);obj=snapshot['objective']
        body='<h1>Review prepared impact assessment</h1><p>'+E(change['state'])+'</p><h2>Replacement objective brief</h2><p>'+E(payload['brief'])+'</p><p>Criteria: '+E(payload['criteria'])+'</p><p>Impact: '+E(payload['impact'])+'</p>'
        from datetime import datetime, timezone
        charged=sum(c['charged_text']+c['charged_tools'] for c in snapshot['costs'])
        deadline=datetime.fromtimestamp(obj['deadline'],timezone.utc).strftime('%d %b %Y %H:%M UTC')
        body+='<p>Charged or reserved $'+budget.usd(charged)+' / $'+budget.usd(obj['max_cost'])+' · Requests used '+str(len(snapshot['costs']))+' / '+str(obj['max_requests'])+' · Revisions '+str(obj['revisions_used'])+' / '+str(obj['max_revisions'])+' · Deadline '+E(deadline)+'. Applying uses one revision. Accumulated consumption and all limits remain unchanged.</p>'
        for task in snapshot['tasks']:
            value=payload['assignments'][task['id']]
            body+='<section class="card"><h2>'+E(task['title'])+' · '+E(value['disposition'])+'</h2><p>Reason: '+E(value['reason'])+'</p><p>Prior state: '+E(task['state'])+' · Prior start approval: '+('yes' if task['owner_grant'] else 'no')+'</p><details><summary>Prior brief and criteria</summary><p>'+E(task['instruction'])+'</p><p>'+E(task['acceptance'])+'</p></details><p>Proposed brief: '+E(value['brief'])+'</p><p>Proposed criteria: '+E(value['criteria'])+'</p>'
            body+='<p>'+('Existing completed output and approval are retained after integrity checks.' if value['disposition']=='retain' else 'Prior output and start approvals will no longer apply. Fresh owner start approval and a new output review are required.')+'</p>'
            if task['run_id']:
                run=snapshot['runs'][task['run_id']];project=run['project'][0];final=next(t for t in run['tasks'] if t['id']=='final')
                body+='<p><a href="/agent-runs/'+E(task['run_id'])+'">Prior actions and saved output</a> · Prior review: '+E(final['status'])+'</p><p>Requests used '+str(project['used_calls'])+' / '+str(project['max_calls'])+' · Actions used '+str(len(run['actions']))+' / '+str(run['run'][0]['max_actions'])+'</p>'
                if final['result_json']:
                    from superhuman.projects import engine as p
                    try:
                        _,text=p._text(json.loads(final['result_json']))
                        preview=text[:12000]+('\nPreview shortened; download the historical output below.' if len(text)>12000 else '')
                    except (ValueError,OSError):
                        preview='The recorded artifact is unavailable or changed. Retained work must pass integrity checks before this assessment can be applied.'
                    body+='<details><summary>Prior output and review</summary><pre>'+E(preview)+'</pre><p>'+E(final['review_note'] or '')+'</p></details>'
                    body+='<p><a href="/team/objectives/'+E(ident)+'/changes/'+E(change_id)+'/artifacts/'+E(task['id'])+'">Download historical output from before this change</a> · This does not approve it for the current plan.</p>'
            body+='</section>'
        if change['state']=='prepared':
            body+='<form method="post" action="/team/objectives/'+E(ident)+'/changes/'+E(change_id)+'/apply">'+hidden('digest',change['digest'])+'<p>Apply only after reviewing every retained output and changed assignment. The objective remains paused; this does not start work.</p><button>Apply reviewed plan change</button></form>'
        body+='<p><a href="/team/objectives/'+E(ident)+'">Objective, current limits and plan history</a></p>'
        return page(body,'Review objective change')

    @app.get('/team/objectives/{ident}/changes/{change_id}/artifacts/{task_id}')
    def historical_artifact(ident:str,change_id:str,task_id:str):
        from superhuman.projects import engine as p
        try:
            change=workplans.get(change_id)
            if change['objective_id']!=ident:raise ValueError('Assessment belongs to another objective')
            snapshot=json.loads(change['snapshot_json'])
            task=next((t for t in snapshot['tasks'] if t['id']==task_id),None)
            if not task or not task['run_id']:raise ValueError('No historical output for this assignment')
            final=next(t for t in snapshot['runs'][task['run_id']]['tasks'] if t['id']=='final')
            filename,_=p._text(json.loads(final['result_json'] or '{}'))
        except (ValueError,OSError,StopIteration) as exc:raise HTTPException(409,str(exc)) from exc
        return FileResponse(filename,media_type='text/markdown',filename='historical-'+change_id[:8]+'-'+task_id[:8]+'.md')

    @app.post('/team/objectives/{ident}/changes/{change_id}/apply')
    def apply_change(ident:str,change_id:str,digest:str=Form(...)):
        try:
            if workplans.get(change_id)['objective_id']!=ident:raise ValueError('Impact assessment belongs to another objective')
            workplans.apply(change_id,digest)
        except ValueError as exc:raise HTTPException(409,str(exc)) from exc
        return RedirectResponse('/team/objectives/'+ident,status_code=303)
