"""Native multi-step interviews, transparent policy and packet-linked outcome reviews."""
import json
from pathlib import Path
from fastapi import Request,HTTPException,Form
from fastapi.responses import RedirectResponse,FileResponse
from superhuman.navigation import shell
from superhuman.workspace.web import render,E,link,hidden,select
from superhuman.interface.views import header,crumbs,details,action_link
from superhuman.team import store as team
from superhuman.milestones import store as ms
from . import store as s,impact
from .policy import RULES,DEFERRED,questions,DEPARTMENT,FIRST_ASSIGNMENT
ASSETS=Path(__file__).with_name('assets')
STEPS={1:'Your outcome',2:'Context & research',3:'Working together',4:'Success & impact',5:'Review brief'}
def go(pid,step=5,saved=False):return RedirectResponse('/project-briefs/'+pid+'?step='+str(step)+('&saved=1' if saved else ''),303)
def panel(pid):
 r=s.interview(pid)
 if not r:return '<section class="practice-callout"><div><h2>Make this project personal</h2><p>Set your expectations through a short interview. Existing projects stay under their current controls until you enrol them.</p></div>'+action_link('/project-briefs/'+pid,'Set up project interview')+'</section>'
 ready=s.current(pid)
 return '<section class="practice-callout"><div><p class="eyebrow">Your project brief</p><h2>'+('Expectations confirmed' if ready else 'Your answers need confirmation')+'</h2><p>'+('Version '+str(r['version'])+' guides the team. Deeper questions can remain open.' if ready else 'Save your answers, review the brief and confirm it before project work continues.')+'</p></div>'+action_link('/project-briefs/'+pid,'Review brief' if ready else 'Continue interview')+'</section>'
def portrait(ident,size=''):
 if ident not in team.EMPLOYEES:return ''
 return '<img class="practice-avatar '+E(size)+'" src="/assets/agents/'+ident+'.png?v=137" width="64" height="64" alt="'+E(team.EMPLOYEES[ident][0])+' — illustrated AI employee" loading="lazy">'
def interview_page(pid,step=1,saved=False):
 q=team.project(pid);r=s.interview(pid);body=crumbs([('/projects','Projects'),('/team/projects/'+pid,q['title']),('','Project interview')])+header('Let’s shape this project','Your answers become a versioned brief for the team. Save each step and return whenever you like.',DEPARTMENT[q['scope']][0])
 if not r:
  return render(body+'<section class="practice-sheet"><h2>A brief before the work</h2><p>This enables a four-part interview for this existing project. It will hold future managed work until you confirm the initial brief. Historical approvals remain historical; enrolment does not verify or rewrite them.</p><form method="post" action="/project-briefs/'+pid+'/enrol"><button>Set up project interview</button></form></section>','Project interview')
 if step not in STEPS:raise ValueError('Choose an available interview step')
 a={v['key']:v for v in s.answers(pid)};done=sum(bool(v['content']) for v in a.values());body+='<div class="practice-guide">'+portrait(q['scope'])+'<p><strong>'+E(team.EMPLOYEES[q['scope']][0])+' leads this interview.</strong><br>The Twin supervises. '+str(done)+' answers recorded · '+('Confirmed' if s.current(pid) else 'Draft / needs confirmation')+' · Version '+str(r['version'])+'</p></div>'
 if saved:body+='<p class="practice-saved" role="status">Your changes were saved. Review and confirm the latest brief before work continues.</p>'
 body+='<nav class="practice-steps" aria-label="Interview progress">'+''.join('<a href="/project-briefs/'+pid+'?step='+str(k)+'"'+(' aria-current="step"' if step==k else '')+'><span>'+str(k)+'</span>'+v+'</a>' for k,v in STEPS.items())+'</nav>'
 if step<5:
  body+='<section class="practice-sheet"><p class="eyebrow">Step '+str(step)+' of 5</p><h2>'+STEPS[step]+'</h2><p>“Research”, “Recommend”, “Undecided” and “Later” keep uncertainty visible. They never become confirmed company facts. The project outcome and success criteria are prefilled for review. Four essential opening answers are needed to confirm a brief.</p><form method="post" action="/project-briefs/'+pid+'/answers">'+hidden('expected',r['version'])+hidden('step',step)
  for x in sorted(questions(q['scope']),key=lambda x:x['stage']):
   if x['stage']!=step:continue
   value=a.get(x['key'],{});key=x['key'];value=value or ({'content':q['objective'],'status':'answered'} if key=='outcome' else {'content':q['acceptance'],'status':'answered'} if key=='success' else {});body+='<fieldset class="practice-question"><legend>'+E(x['title'])+(' <span class="practice-essential">Essential</span>' if x['essential'] else '')+'</legend><label for="status-'+key+'">Answer status</label><select id="status-'+key+'" name="status_'+key+'">'+''.join('<option value="'+status+'"'+(' selected' if value.get('status','answered')==status else '')+'>'+label+'</option>' for status,label in [('answered','Answered'),('research','Research this'),('recommend','Recommend for me'),('undecided','Not decided'),('later','Answer later')])+'</select><label for="answer-'+key+'">Your answer or research request</label><textarea id="answer-'+key+'" name="answer_'+key+'" rows="4" maxlength="1800">'+E(value.get('content',''))+'</textarea><small>Recorded as '+E(x['kind'])+'. Save explicitly before leaving this step.</small></fieldset>'
  body+='<div class="practice-save"><button>Save and continue</button><a href="/project-briefs/'+pid+'?step=5">Review saved brief</a></div></form></section>'
 else:
  body+='<section class="practice-sheet"><h2>Your saved project brief</h2><p>These are owner answers and requests, not independently verified evidence. Confirming does not approve financial commitments, sources, permissions or milestone deliverables.</p>'
  if not a:body+='<p>No answers saved. '+link('/project-briefs/'+pid+'?step=1','Start with your outcome')+'</p>'
  for x in questions(q['scope']):
   value=a.get(x['key']);body+='<article class="practice-answer"><h3>'+E(x['title'])+'</h3><small>'+E((value['status']+' · '+value['kind']) if value and (value['content'] or value['status']!='answered') else 'Not answered')+'</small><p class="practice-text">'+E(value['content'] if value and value['content'] else 'Not provided')+'</p></article>'
  body+='</section><section class="practice-sheet"><h2>Brief controls</h2><form method="post" action="/project-briefs/'+pid+'/controls">'+hidden('expected',r['version'])+select('Interview sensitivity','sensitivity',[(v,v.capitalize()) for v in team.SENSITIVITIES],r['sensitivity'])+'<p>Private answers require matching project and assignment classification. Public-web tools remain subject to existing privacy gates.</p><label><input type="checkbox" name="auto_advance" value="yes"'+(' checked' if r['auto_advance'] else '')+'> Let The Twin start ready milestones, including independent preparation, within the confirmed plan</label><p>All prerequisites must be owner-approved. Criteria, requirement scope, source access, activation, employee and budget gates still apply.</p><button class="secondary">Save brief controls</button></form>'
  if s.current(pid):body+='<p class="practice-saved">This version is confirmed.</p>'
  else:body+='<form method="post" action="/project-briefs/'+pid+'/confirm">'+hidden('expected',r['version'])+'<label><input type="checkbox" required name="confirmed" value="yes"> I reviewed this saved version and its unresolved questions.</label><button>Confirm this brief</button></form>'
  body+='</section>'
  if q['scope']=='endorsement':body+=details('Use our agreed EdSync starting brief','<p>Fill unanswered fields only, using the decisions already agreed in our discussion. Existing answers are retained. Exact deadline, assessment method, pilot cap and financial workbook remain undecided.</p><form method="post" action="/project-briefs/'+pid+'/preset">'+hidden('expected',r['version'])+'<button class="secondary">Use agreed starting answers</button></form>')
 pending=s.read('practice_questions','SELECT * FROM practice_questions WHERE project_id=? ORDER BY created_at',(pid,))
 if pending:
  body+='<section class="practice-sheet"><h2>Questions from your team</h2><p>Questions are batched here. Responses change the brief and require reconfirmation.</p>'
  for row in pending:
   body+='<article class="practice-answer"><h3>'+E(row['question'])+'</h3><p>'+E(row['reason'])+'</p><form method="post" action="/project-briefs/'+pid+'/questions/'+row['id']+'">'+hidden('expected',row['version'])+'<label>Your answer<textarea name="answer" maxlength="1800">'+E(row['answer'])+'</textarea></label>'+select('Status','status',[('answered','Answered'),('later','Later')],row['status'] if row['status']!='open' else 'later')+'<button class="secondary">Save clarification</button></form></article>'
  body+='</section>'
 history=s.read('practice_history','SELECT version,action,created_at FROM practice_history WHERE project_id=? ORDER BY id DESC LIMIT 30',(pid,))
 body+=details('Brief history',''.join('<p>Version '+str(v['version'])+' · '+E(v['action'])+' · '+E(v['created_at'])+'</p>' for v in history) or '<p>No changes recorded yet.</p>')
 return render(body,'Project interview')
def impact_page(pid):
 q=team.project(pid);bill=impact.costs(pid);body=crumbs([('/projects','Projects'),('/team/projects/'+pid,q['title']),('','Milestone impact')])+header('What changed because of the work?','Assess accepted deliverables, readiness and observable outcomes separately.','Milestone impact')
 body+='<section class="practice-sheet"><h2>Lifetime attributed model and tool charges</h2><p class="practice-amount">$'+E(bill['charged_usd'])+'</p><p>'+str(bill['entries'])+' entries · '+str(bill['uncertain_entries'])+' reserved or uncertain. Of the ledger total, held reservations: $'+E(bill['reserved_usd'])+'.</p><p>Includes revisions across budget periods and coordination attributed after v1.34. Older unallocated coordination and shared overhead are excluded. Uncertain charges may be conservative reservations, not final invoices. This is not a complete project cost or ROI.</p></section>'
 for m in ms.listing(pid):
  if m['state']!='approved':continue
  packet=ms.packet(m['id']);body+='<section class="practice-sheet"><h2>'+E(m['title'])+'</h2><p>Approved packet version '+str(packet['version'])+'</p><form method="post" action="/project-briefs/'+pid+'/impact/'+m['id']+'">'+hidden('packet_id',packet['id'])
  for key,label in impact.CHECKS.items():body+=select(label,key,[('not_assessed','Not assessed'),('met','Met — explain evidence below'),('revise','Needs attention')],'not_assessed')
  for key,label in [('readiness','What changed in project readiness?'),('outcome','What observable outcome occurred? State “not observed yet” where appropriate.'),('note','Evidence, assessment method and limitations')]:body+='<label>'+E(label)+'<textarea name="'+key+'" required maxlength="1600"></textarea></label>'
  body+=details('Optional additional costs and time ranges','<p>Use non-overlapping amounts in USD. Exclude API/tool charges already counted above. Do not infer working hours from elapsed weeks.</p>'+''.join('<label>'+E(label)+'<input name="'+key+'" type="number" min="0" max="10000000" step="any"></label>' for key,label in [('paid_data','Additional paid data cost'),('hosting','Allocated hosting cost'),('external','External specialist cost'),('owner_review','Owner review cost'),('rework','Additional rework cost not counted elsewhere'),('hours_low','Estimated hours saved — low'),('hours_high','Estimated hours saved — high'),('rate_low','Owner time value USD/hour — low'),('rate_high','Owner time value USD/hour — high')]))+'<button>Save milestone impact review</button></form></section>'
  for row in s.read('practice_impacts','SELECT * FROM practice_impacts WHERE milestone_id=? ORDER BY created_at DESC',(m['id'],)):
   current=row['packet_id']==packet['id'] and row['packet_digest']==packet['digest'];extras=json.loads(row['extras']);body+='<article class="practice-sheet"><h3>Saved review · '+('Current packet' if current else 'Historical packet')+'</h3><p>'+E(row['created_at'])+'</p><ul>'+''.join('<li>'+E(impact.CHECKS[k])+': '+E(v)+'</li>' for k,v in json.loads(row['assessments']).items())+'</ul><p>'+E(row['readiness'])+'</p><p>'+E(row['outcome'])+'</p><p>'+E(row['note'])+'</p>'
   if extras:body+=details('Recorded cost and time inputs','<pre>'+E(json.dumps(extras,indent=2))+'</pre>')
   if all(k in extras for k in ('hours_low','hours_high','rate_low','rate_high')):
    from decimal import Decimal
    low=Decimal(extras['hours_low'])*Decimal(extras['rate_low']);high=Decimal(extras['hours_high'])*Decimal(extras['rate_high']);body+='<p>Estimated gross time value: $'+E(str(low))+'–$'+E(str(high))+'. Owner estimate; not causal savings or net ROI.</p>'
   body+='</article>'
 if not any(m['state']=='approved' for m in ms.listing(pid)):body+='<section class="ui-empty"><h2>Review impact after an approved milestone</h2><p>Approval and current evidence gates come first. No outcome is inferred from agent activity.</p></section>'
 return render(body,'Milestone impact')
def install(app):
 @app.get('/assets/practice.css')
 def css():return FileResponse(ASSETS/'practice.css',media_type='text/css',headers={'Cache-Control':'private, max-age=3600'})
 @app.get('/assets/practice.js')
 def js():return FileResponse(ASSETS/'practice.js',media_type='application/javascript',headers={'Cache-Control':'private, max-age=3600'})
 @app.get('/assets/agents/{ident}.png')
 def face(ident:str):
  if ident not in team.EMPLOYEES:raise HTTPException(404,'Unknown employee')
  return FileResponse(ASSETS/(ident+'.png'),media_type='image/png',headers={'Cache-Control':'private, max-age=3600'})
 @app.get('/operating-guide')
 def guide():
  body=header('How your team works','Your confirmed decisions, with unresolved choices kept visible.','Operating guide')+''.join('<section class="practice-sheet"><h2>'+E(k.capitalize())+'</h2><p>'+E(v)+'</p></section>' for k,v in RULES.items())+'<section class="practice-sheet"><h2>Next-session questions</h2><ul>'+''.join('<li>Q'+str(q['question'])+' · '+E(q['topic'])+'</li>' for q in DEFERRED)+'</ul><p>These choices have not been inferred or enabled.</p></section>'
  return render(body,'Operating guide')
 @app.get('/project-briefs/{pid}')
 def show(pid:str,step:int=1,saved:bool=False):
  try:return interview_page(pid,step,saved)
  except ValueError as exc:raise HTTPException(409,str(exc)) from exc
 @app.post('/project-briefs/{pid}/enrol')
 def enrol(pid:str):
  try:team.project(pid);s.enroll(pid)
  except ValueError as exc:raise HTTPException(409,str(exc)) from exc
  return go(pid,1)
 @app.post('/project-briefs/{pid}/answers')
 async def answer(pid:str,request:Request):
  form=await request.form()
  try:
   step=int(form['step']);q=team.project(pid)
   if step not in range(1,5):raise ValueError('Invalid step')
   entries={x['key']:(str(form.get('status_'+x['key'],'undecided')),str(form.get('answer_'+x['key'],''))) for x in questions(q['scope']) if x['stage']==step};r=s.interview(pid)
   s.save(pid,int(form['expected']),entries,r['sensitivity'],bool(r['auto_advance']))
  except (ValueError,KeyError,TypeError) as exc:raise HTTPException(409,str(exc)) from exc
  return go(pid,step+1,True)
 @app.post('/project-briefs/{pid}/controls')
 def controls(pid:str,expected:int=Form(...),sensitivity:str=Form(...),auto_advance:str=Form('')):
  try:s.save(pid,expected,{},sensitivity,auto_advance=='yes')
  except ValueError as exc:raise HTTPException(409,str(exc)) from exc
  return go(pid,5,True)
 @app.post('/project-briefs/{pid}/confirm')
 def confirm(pid:str,expected:int=Form(...),confirmed:str=Form('')):
  try:
   if confirmed!='yes':raise ValueError('Review and confirm this saved brief')
   s.confirm(pid,expected)
  except ValueError as exc:raise HTTPException(409,str(exc)) from exc
  return go(pid,5)
 @app.post('/project-briefs/{pid}/preset')
 def preset(pid:str,expected:int=Form(...)):
  try:s.preset(pid,expected)
  except ValueError as exc:raise HTTPException(409,str(exc)) from exc
  return go(pid,5,True)
 @app.post('/project-briefs/{pid}/questions/{ident}')
 def clarify(pid:str,ident:str,expected:int=Form(...),answer:str=Form(''),status:str=Form(...)):
  try:s.answer_question(pid,ident,expected,answer,status)
  except ValueError as exc:raise HTTPException(409,str(exc)) from exc
  return go(pid,5,True)
 @app.get('/project-briefs/{pid}/impact')
 def outcomes(pid:str):
  try:return impact_page(pid)
  except ValueError as exc:raise HTTPException(409,str(exc)) from exc
 @app.post('/project-briefs/{pid}/impact/{mid}')
 async def add_impact(pid:str,mid:str,request:Request):
  f=await request.form()
  try:
   if ms.milestone(mid)['project_id']!=pid:raise ValueError('Milestone belongs to another project')
   keys=('paid_data','hosting','external','owner_review','rework','hours_low','hours_high','rate_low','rate_high')
   impact.add(mid,str(f['packet_id']),{k:str(f.get(k,'')) for k in impact.CHECKS},str(f['readiness']),str(f['outcome']),str(f['note']),{k:str(f.get(k,'')) for k in keys})
  except (ValueError,KeyError) as exc:raise HTTPException(409,str(exc)) from exc
  return RedirectResponse('/project-briefs/'+pid+'/impact',303)
