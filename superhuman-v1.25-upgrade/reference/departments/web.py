"""Department dashboard and scoped workspaces, behind the existing auth boundary."""
from datetime import datetime,timedelta,timezone
import json
from urllib.parse import quote,urlencode
from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from superhuman.navigation import shell
from . import store

STYLE='''<style>.department-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.department-card{margin:0;display:flex;flex-direction:column;gap:12px}.department-card h2{margin:0}.department-card p{margin:0}.department-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.department-metrics div{background:#f1f5ee;border-radius:9px;padding:10px}.department-metrics strong{display:block;font-size:23px;line-height:1.3}.department-metrics span{font-size:11px;color:#61746c}.department-caption{font-size:12px;color:#61746c}.department-next{border-top:1px solid #dce4de;padding-top:12px;margin-top:auto}.department-list{padding-left:20px}.department-facts{display:grid;grid-template-columns:140px 1fr;gap:8px 15px}.department-facts dt{color:#61746c}.department-facts dd{margin:0}.department-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:20px 0}.department-stats .card{margin:0;padding:15px}.department-stats b{display:block;font-size:28px}.department-stats small{font-size:12px}.department-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.department-label{font-size:11px;letter-spacing:1.6px;text-transform:uppercase;color:#61746c}@media(max-width:800px){.department-grid{grid-template-columns:1fr}.department-stats{grid-template-columns:repeat(2,minmax(0,1fr))}.department-heading{display:block}.department-facts{grid-template-columns:1fr}.department-facts dd{margin-bottom:8px}}</style>'''

def esc(v):return shell.esc(v)
def url(scope,tab='summary'):
    if tab=='planning':return '/department-plans/'+quote(scope,safe='')
    return '/departments/'+quote(scope,safe='')+('/'+tab if tab!='summary' else '')
def when(value):
    try:
        dt=datetime.fromisoformat(value.replace('Z','+00:00'))
        if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone(timedelta(hours=5))).strftime('%d %b %Y, %I:%M %p PKT')
    except (ValueError,TypeError,AttributeError):return value

def link(path,text):return '<a href="'+esc(path)+'">'+esc(text)+'</a>'
def status(d):
    c=d['counts']
    if d['warnings']:return 'Check data availability'
    if c['plans_review']+c['outputs_review']:return 'Needs your review'
    if c['blocked_projects']+c['blocked_tasks']:return 'Has blockers'
    if c['running']:return 'Work running'
    if c['active_projects']:return 'Active objectives'
    if c['projects']:return 'Objectives recorded'
    return 'No objectives yet'

def metrics(d):
    c=d['counts']
    return '<div class="department-metrics">'+''.join('<div><strong>'+str(value)+'</strong><span>'+label+'</span></div>' for label,value in [('Objectives',c['projects']),('Running tasks',c['running']),('Reviews',c['plans_review']+c['outputs_review'])])+'</div>'

def card(d):
    c=d['counts'];body='<article class="card department-card"><div class="row"><span class="badge">'+status(d)+'</span><span class="department-caption">'+str(c['suggestions'])+' task suggestions</span></div><h2>'+link(url(d['scope']),d['name'])+'</h2>'+metrics(d)
    body+='<p>'+str(c['approved'])+' / '+str(c['tasks'])+' tasks approved · '+str(c['blocked_tasks'])+' blocked tasks · '+str(c['blocked_projects'])+' blocked objectives</p>'
    from superhuman.planning.presentation import card_line
    body+=card_line(d['scope'])
    body+='<p class="department-caption">Last record update: '+esc(when(d['last_update']))+'</p>'
    body+='<div class="department-next"><span class="department-label">Suggested next step</span><p>'+link(d['next'][1],d['next'][0])+'</p></div>'
    body+='<a class="button secondary" href="'+url(d['scope'])+'">Open department</a></article>'
    return body

def install(app):
    def render(body,title):return HTMLResponse(shell.page(STYLE+body,title))
    def get(scope):
        try:
            from superhuman.planning.priority import next_step
            result=store.snapshot(scope)
            result['next']=next_step(scope,result['next'])
            return result
        except ValueError as exc:raise HTTPException(404,str(exc)) from exc

    @app.get('/departments')
    def dashboard():
        data=[get(scope) for scope,_ in store.departments()]
        total=lambda key:sum(d['counts'][key] for d in data)
        body='<div class="department-label">Across your workstreams</div><h1>Your departments</h1><p>A consolidated view of recorded work, decisions and next steps.</p>'
        body+='<div class="department-stats">'+''.join('<section class="card"><b>'+str(n)+'</b><small>'+label+'</small></section>' for label,n in [('Departments',len(data)),('Objectives',total('projects')),('Tasks running',total('running')),('Plans & outputs to review',total('plans_review')+total('outputs_review'))])+'</div>'
        if any(d['warnings'] for d in data):body+='<p class="error">Some records could not be read. Open the affected department before relying on its counts.</p>'
        body+='<div class="department-grid">'+''.join(card(d) for d in data)+'</div>'
        from superhuman.core.router import WORKSTREAMS
        if 'writing' in WORKSTREAMS:
            body+='<section class="card"><div class="department-label">Shared support</div><h2>'+link(url('writing'),'Writing DNA & cross-department writing')+'</h2><p>The writing specialist supports every department. Its existing writing workstream is available here separately.</p></section>'
        body+='<p class="department-caption">Live record summary · refreshed when you open this page · '+esc(when(datetime.now(timezone.utc).isoformat()))+'. Ready actions respect dependencies. Pending reviews and interrupted work stay visible in Attention; suggestions do not execute work. Set goals, priorities and milestone dates under Plan &amp; Priorities.</p>'
        return render(body,'Departments')

    @app.get('/departments/{scope}')
    def summary(scope:str):return workspace(scope,'summary',1)

    @app.get('/departments/{scope}/{tab}')
    def workspace(scope:str,tab:str,page:int=1):
        if tab not in ('summary','projects','knowledge','conversations','activity') or not 1<=page<=10000:raise HTTPException(404,'Department page not found')
        d=get(scope);c=d['counts'];size=50
        def slice_of(items):return items[(page-1)*size:page*size]
        body='<p class="shell-context">'+link('/departments','Departments')+' / '+esc(d['name'])+'</p><div class="department-heading"><div><div class="department-label">Department workspace</div><h1>'+esc(d['name'])+'</h1></div><a class="button secondary" href="/projects?'+urlencode({'workstream':scope})+'#new-project">Create an objective</a></div>'
        body+='<nav class="shell-tabs" aria-label="Department navigation">'+''.join('<a href="'+url(scope,key)+'"'+(' aria-current="page"' if key==tab else '')+'>'+label+'</a>' for key,label in [('summary','Summary'),('projects','Projects & Tasks'),('knowledge','Research & Documents'),('conversations','Conversations'),('activity','Activity & Decisions'),('planning','Plan & Priorities')])+'</nav>'
        for warning in d['warnings']:body+='<p class="error">'+esc(warning)+'</p>'
        if tab=='summary':
            body+=metrics(d)+'<section class="card"><h2>Recorded progress</h2><p>'+str(c['approved'])+' of '+str(c['tasks'])+' tasks approved. '+str(c['outputs_review'])+' outputs and '+str(c['plans_review'])+' plans await review.</p>'
            from superhuman.planning.presentation import summary_panel
            body+=summary_panel(scope)+'<p class="department-caption">Last work record update: '+esc(when(d['last_update']))+'</p></section>'
            body+='<section class="card"><h2>Current objectives</h2>'
            active=[p for p in d['projects'] if p['status']!='approved']
            body+=('<ul class="department-list">'+''.join('<li>'+link('/work/'+p['id'],p['objective'])+' · '+esc(p['status'].replace('_',' '))+'</li>' for p in active[:5])+'</ul>') if active else '<p>No unfinished objectives recorded.</p>'
            if len(active)>5:body+='<p>'+link(url(scope,'projects'),'View all '+str(len(active))+' unfinished objectives')+'</p>'
            body+='</section><section class="card"><h2>Waiting for you</h2>'
            waiting=[('Plan',p['objective'],'/work/'+p['id']) for p in d['projects'] if p['status']=='plan_review']+[('Output',t['title'],'/projects/'+t['project_id']) for t in d['tasks'] if t['status']=='needs_review']+[('Task suggestion',s['title'],'/talk/'+s['thread_id']) for s in d['suggestions']]
            body+=('<ul>'+''.join('<li>'+esc(kind)+': '+link(path,title)+'</li>' for kind,title,path in waiting[:10])+'</ul>') if waiting else '<p>No plans, outputs or task suggestions awaiting your review.</p>'
            if len(waiting)>10:body+='<p>'+link(url(scope,'projects'),'View all department tasks and suggestions')+'</p>'
            body+='</section><section class="card"><h2>Blockers</h2>'
            blocked=[('Objective',p['objective'],p.get('error') or p['status'],'/work/'+p['id']) for p in d['projects'] if p['status'] in store.BLOCKED]+[('Task',t['title'],t.get('error') or t['status'],'/projects/'+t['project_id']) for t in d['tasks'] if t['status'] in store.BLOCKED]
            body+=('<ul>'+''.join('<li>'+link(path,kind+': '+title)+'<p>'+esc(reason)+'</p></li>' for kind,title,reason,path in blocked[:10])+'</ul>') if blocked else '<p>No blocked task or objective statuses recorded. Unrecorded dependencies cannot be assessed here.</p>'
            if len(blocked)>10:body+='<p>'+link(url(scope,'projects'),'View all recorded blockers')+'</p>'
            body+='</section><section class="card"><h2>Suggested next step</h2><p>'+link(d['next'][1],d['next'][0])+'</p><p class="department-caption">Suggested from your plan and recorded statuses. Open the linked item to review it; no work starts automatically.</p></section>'
            body+='<section class="card"><h2>Latest execution records</h2>'
            recent=d['events'][:5]
            body+=('<ul>'+''.join('<li>'+esc(r['action'].replace('_',' '))+': '+link('/work/'+r['project_id'],r['project_title'])+' · '+esc(when(r['created_at']))+'</li>' for r in recent)+'</ul>') if recent else '<p>No project execution events recorded yet.</p>'
            body+='</section>'
            body+='<section class="card"><h2>Research & materials</h2><p>'+str(c['areas'])+' research areas · '+str(c['sources'])+' source cards · '+str(c['files'])+' uploaded files · '+str(c['exports'])+' document exports.</p>'+link(url(scope,'knowledge'),'Open research and documents')+'</section>'
        elif tab=='projects':
            body+='<h2>Objectives ('+str(c['projects'])+')</h2>'
            for p in slice_of(d['projects']):body+='<section class="card"><span class="badge">'+esc(p['status'].replace('_',' '))+'</span><h3>'+link('/work/'+p['id'],p['objective'])+'</h3><p>'+esc(p['details'][:500])+'</p>'+link('/projects/'+p['id'],'Open tasks and review')+'</section>'
            if not d['projects']:body+='<p>No objectives recorded yet.</p>'
            body+='<h2>Tasks ('+str(c['tasks'])+')</h2>'
            for t in slice_of(d['tasks']):body+='<section class="card"><h3>'+link('/projects/'+t['project_id'],t['title'])+'</h3><p>'+esc(t['project_title'])+' · '+esc(t['status'].replace('_',' '))+'</p>'+('<p class="error">'+esc(t['error'])+'</p>' if t.get('error') else '')+'</section>'
            if not d['tasks']:body+='<p>No project tasks recorded yet.</p>'
            body+='<h2>Task suggestions ('+str(c['suggestions'])+')</h2>'
            for s in slice_of(d['suggestions']):body+='<section class="card"><h3>'+link('/talk/'+s['thread_id'],s['title'])+'</h3><p>'+esc(s['rationale'])+'</p></section>'
            if not d['suggestions']:body+='<p>No task suggestions awaiting review.</p>'
        elif tab=='knowledge':
            body+='<p>Materials shared within this workstream. Saved source notes are not independently verified by this dashboard.</p><h2>Research areas ('+str(c['areas'])+')</h2>'
            for a in slice_of(d['areas']):body+='<section class="card"><h3>'+link('/research-desk/'+a['id'],a['title'])+'</h3><p>'+esc(a['status'])+'</p><p>'+esc(a['questions'][:500])+'</p></section>'
            if not d['areas']:body+='<p>No research areas recorded.</p>'
            body+='<h2>Source cards ('+str(c['sources'])+')</h2>'
            for s in slice_of(d['sources']):
                try:r=json.loads(s['payload_json'])
                except (ValueError,TypeError):r={}
                if not isinstance(r,dict):r={}
                body+='<section class="card"><h3>'+link('/research-desk/source/'+s['id'],r.get('title') or 'Source card')+'</h3><p>'+esc(s['area_title'])+'</p>'
                if r.get('read_reason'):body+='<p><strong>Why read this:</strong> '+esc(r['read_reason'])+'</p>'
                if r.get('synopsis'):body+='<p><strong>Saved synopsis:</strong> '+esc(str(r['synopsis'])[:500])+'</p>'
                if r.get('limitations'):body+='<p class="department-caption">Limitations: '+esc(str(r['limitations'])[:250])+'</p>'
                body+='</section>'
            if not d['sources']:body+='<p>No source cards recorded.</p>'
            body+='<h2>Uploaded files ('+str(c['files'])+')</h2><ul>'+''.join('<li>'+esc(f['name'])+' · '+str(f['bytes'])+' bytes</li>' for f in slice_of(d['files']))+'</ul><p>'+link('/tools?'+urlencode({'project':scope}),'Inspect or upload workstream files')+'</p>'
            if not d['files']:body+='<p>No uploaded files recorded.</p>'
            body+='<h2>Document exports ('+str(c['exports'])+')</h2><ul>'+''.join('<li>'+link('/documents/download/'+quote(scope,safe='')+'/'+quote(r['export_id'],safe=''),r['title'] or 'Document')+' · '+esc(r['format'].upper())+' · '+esc(when(r['created_at']))+'</li>' for r in slice_of(d['exports']))+'</ul>'
            if not d['exports']:body+='<p>No document exports recorded.</p>'
            outputs=[t for t in d['tasks'] if t.get('result_json')]
            body+='<h2>Saved task outputs ('+str(len(outputs))+')</h2><ul>'+''.join('<li>'+link('/projects/'+t['project_id'],t['title'])+' · '+esc(t['status'].replace('_',' '))+'</li>' for t in slice_of(outputs))+'</ul><p>'+link('/documents?'+urlencode({'project':scope}),'Open document tools')+'</p>'
        elif tab=='conversations':
            body+='<p>Existing conversations associated with this department’s workstream.</p>'
            for t in slice_of(d['conversations']):body+='<section class="card"><h3>'+link('/talk/'+t['id'],t['title'])+'</h3><p>Updated '+esc(when(t['updated_at']))+' · '+str(t['used_calls'])+' / '+str(t['max_calls'])+' requests used.</p></section>'
            if not d['conversations']:body+='<p>No conversations recorded for this department.</p>'
            body+='<p>'+link('/talk','Open Talk to start a conversation')+'</p>'
        else:
            body+='<h2>Execution activity</h2><p>Latest 100 recorded execution events associated with this department’s projects.</p>'
            for r in slice_of(d['events']):body+='<section class="card"><strong>'+esc(r['action'].replace('_',' '))+'</strong><p>'+link('/work/'+r['project_id'],r['project_title'])+' · '+esc(when(r['created_at']))+'</p></section>'
            if not d['events']:body+='<p>No project execution events recorded.</p>'
            body+='<h2>Recent record updates</h2>'
            changes=[(r['updated_at'],'Conversation',r['title'],'/talk/'+r['id']) for r in d['conversations']]+[(r['updated_at'],'Research area',r['title'],'/research-desk/'+r['id']) for r in d['areas']]
            changes.sort(reverse=True)
            body+='<ul>'+''.join('<li>'+esc(kind)+': '+link(path,title)+' · '+esc(when(at))+'</li>' for at,kind,title,path in slice_of(changes))+'</ul>'
            body+='<h2>Confirmed decisions</h2><p>Confirmed, non-sensitive, unexpired decision notes saved for this workstream. These reflect saved decisions, not new recommendations.</p>'
            for n in slice_of(d['decisions']):body+='<section class="card"><h3>'+link('/memory/'+n['id'],n['title'])+'</h3><p>'+esc(n['content'][:1000])+'</p><p class="department-caption">'+esc(when(n['updated_at']))+'</p></section>'
            if not d['decisions']:body+='<p>No eligible confirmed decision notes recorded.</p>'
        if tab!='summary':
            groups={'projects':['projects','tasks','suggestions'],'knowledge':['areas','sources','files','exports'],'conversations':['conversations'],'activity':['events','decisions','conversations','areas']}[tab]
            lengths=[len(d[k]) for k in groups]
            if tab=='knowledge':lengths.append(sum(bool(t.get('result_json')) for t in d['tasks']))
            if tab=='activity':lengths.append(len(d['conversations'])+len(d['areas']))
            body+='<p class="department-caption">Page '+str(page)+' · up to 50 items per list.</p>'
            if page>1:body+='<p>'+link(url(scope,tab)+'?page='+str(page-1),'Previous page')+'</p>'
            if max(lengths,default=0)>page*size:body+='<p>'+link(url(scope,tab)+'?page='+str(page+1),'Next page')+'</p>'
        body+='<p class="department-caption">Live record summary · viewed '+esc(when(d['as_of']))+' · no model-generated synopsis.</p>'
        return render(body,d['name']+' · '+tab.capitalize())
