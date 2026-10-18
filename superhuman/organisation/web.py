"""Owner review, correction, history and request-level provenance for shared foundation."""
import json
from fastapi import Form,HTTPException
from fastapi.responses import RedirectResponse
from superhuman.projects import engine as p
from superhuman.departments.store import readonly,tables
from superhuman.workspace.web import render,E,link,hidden
from . import store,context

def field(label,name,value='',area=False):
    control=('<textarea id="fm-'+name+'" name="'+name+'" rows="6">'+E(value)+'</textarea>') if area else ('<input id="fm-'+name+'" name="'+name+'" value="'+E(value)+'">')
    return '<label for="fm-'+name+'">'+E(label)+'</label>'+control

def select(label,name,choices,value):
    return '<label for="fm-'+name+'">'+E(label)+'</label><select id="fm-'+name+'" name="'+name+'">'+''.join('<option value="'+E(key)+'"'+(' selected' if key==value else '')+'>'+E(title)+'</option>' for key,title in choices)+'</select>'

def form(r=None):
    r=r or {};out='<form method="post" action="/shared-memory/save">'+hidden('expected',r.get('version',0))
    out+=(hidden('ident',r['id']) if r.get('id') else field('Stable memory key','ident'))
    for label,name,area in [('Title','title',False),('Professional shared memory','content',True),('Source / owner confirmation','source',False),('Source date (YYYY-MM-DD)','source_date',False),('Review on (YYYY-MM-DD, optional)','review_on',False)]:out+=field(label,name,r.get(name,''),area)
    out+=select('Status','status',[(v,v.capitalize()) for v in store.STATUSES],r.get('status','draft'))+select('Category','category',[(v,v.replace('_',' ').capitalize()) for v in store.CATEGORIES],r.get('category','foundation'))
    out+='<label><input type="checkbox" name="shared_confirmed" value="yes" required> This is professional context suitable for all eight AI employees. I reviewed its accuracy and status.</label><p>Active records are owner-authorised context, not independently verified evidence. Historical and unresolved records retain those labels. Draft and archived records are not injected. Saving does not change tools, source permissions or spending authority.</p><button>Save shared memory</button></form>'
    return out

def install(app):
    @app.get('/shared-memory')
    def home(q:str='',status:str=''):
        if len(q)>200 or status not in ('',)+store.STATUSES:raise HTTPException(400,'Invalid memory filter')
        store.initialize();records=store.records();shown=[r for r in records if (not status or r['status']==status) and (not q or q.casefold() in (r['title']+' '+r['content']).casefold())]
        body='<h1>Shared foundation</h1><p>Who you are, why Superhuman exists, what EdSync is building, and how your team works. This professional brief is available to all eight employees in metered conversations, drafting, research and coordination. It is a curated transfer, not a complete ChatGPT history export.</p><p>'+link('/shared-memory/preview','Preview an employee’s current context')+' · '+link('/shared-memory/requests','Request receipts')+' · '+link('/settings','Settings')+'</p><section class="card"><h2>What changed</h2><p>Every model request receives the shared foundation and team directory. Relevant saved department charters, writing rules, goals and supervision instructions are retrieved fresh. Project summaries require existing team sharing and participant access. Source documents keep their existing permission gates.</p><p>Imported business metrics are dated. Missing founder details and product decisions stay unresolved. Sensitive personal material was excluded from the shared import.</p></section>'
        body+='<form method="get">'+field('Search memory','q',q)+select('Status','status',[('','All statuses')]+[(v,v.capitalize()) for v in store.STATUSES],status)+'<button>Search</button></form><p>'+str(len(shown))+' records.</p>'
        for r in shown:body+='<article class="card"><h2>'+link('/shared-memory/items/'+r['id'],r['title'])+'</h2><p>'+E(r['status']+' · v'+str(r['version'])+' · source date '+(r['source_date'] or 'unknown'))+'</p><p>'+E(r['content'])+'</p></article>'
        body+='<details><summary>Add shared professional memory</summary>'+form()+'</details>'
        return render(body,'Shared foundation')
    @app.get('/shared-memory/items/{ident}')
    def item(ident:str):
        try:r=store.get(ident)
        except ValueError as exc:raise HTTPException(404,str(exc)) from exc
        body='<h1>'+E(r['title'])+'</h1><p>'+link('/shared-memory','Shared foundation')+'</p><p>Version '+str(r['version'])+' · '+E(r['status'])+'</p>'+form(r)+'<details><summary>Version history</summary>'
        for h in store.history(ident):body+='<section class="card"><h2>Version '+str(h['version'])+'</h2><pre>'+E(json.dumps(json.loads(h['snapshot']),indent=2,ensure_ascii=False))+'</pre></section>'
        return render(body+'</details>','Shared memory record')
    @app.post('/shared-memory/save')
    def save(ident:str=Form(...),expected:int=Form(...),title:str=Form(...),content:str=Form(...),status:str=Form(...),source:str=Form(...),source_date:str=Form(''),review_on:str=Form(''),category:str=Form('foundation'),shared_confirmed:str=Form('')):
        if shared_confirmed!='yes':raise HTTPException(409,'Confirm this professional context is suitable for the shared team')
        try:store.save(ident,expected,title,content,status,source,source_date,review_on,category)
        except ValueError as exc:raise HTTPException(409,str(exc)) from exc
        return RedirectResponse('/shared-memory/items/'+ident,status_code=303)
    @app.get('/shared-memory/preview')
    def preview(employee:str='twin',q:str='Who am I, what is Superhuman and who are your teammates?'):
        from superhuman.experience.store import NAMES
        if employee not in NAMES or len(q)>1000:raise HTTPException(400,'Invalid preview')
        data=context.snapshot(employee,q)
        body='<h1>Preview employee awareness</h1><p>'+link('/shared-memory','Shared foundation')+'</p><p>Read-only current context; no model call, no paid request and no claim that a model has understood it. Linked source files are not opened by this preview.</p><form method="get">'+select('Employee','employee',list(NAMES.items()),employee)+field('Question or topic','q',q)+'<button>Preview context</button></form><pre>'+E(json.dumps(data,indent=2,ensure_ascii=False))+'</pre>'
        return render(body,'Employee context preview')
    @app.get('/shared-memory/requests')
    def requests():
        body='<h1>Shared context request receipts</h1><p>'+link('/shared-memory','Shared foundation')+'</p><p>Receipts show the exact shared context supplied to a paid model request, its version signature and whether it changed during the call. They do not prove answer accuracy or completed work.</p>'
        with readonly(p.DEFAULT_DB) as db:
            rows=db.execute('SELECT cost_id,actor,state,created_at FROM org_context_receipts ORDER BY created_at DESC LIMIT 100').fetchall() if 'org_context_receipts' in tables(db) else []
        for r in rows:body+='<p>'+link('/shared-memory/requests/'+r['cost_id'],r['actor']+' · '+r['state']+' · '+r['created_at'])+'</p>'
        return render(body,'Context receipts')
    @app.get('/shared-memory/requests/{ident}')
    def request(ident:str):
        with readonly(p.DEFAULT_DB) as db:row=db.execute('SELECT * FROM org_context_receipts WHERE cost_id=?',(ident,)).fetchone() if 'org_context_receipts' in tables(db) else None
        if not row:raise HTTPException(404,'Context receipt not found')
        return render('<h1>Exact shared context supplied</h1><p>'+E(row['actor']+' · '+row['state']+' · '+row['created_at'])+'</p><p>'+link('/shared-memory/requests','Request receipts')+'</p><pre>'+E(json.dumps(json.loads(row['snapshot']),ensure_ascii=False,indent=2))+'</pre>','Context receipt')
