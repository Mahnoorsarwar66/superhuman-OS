"""Owner-facing Storage, personality, readiness and proactive controls."""
import json
from urllib.parse import urlencode
from fastapi import Form,File,UploadFile,HTTPException
from fastapi.responses import RedirectResponse,FileResponse,Response
from superhuman.projects import engine as p
from superhuman.team import store as team
from superhuman.experience import store as ux
from superhuman.workspace.web import render,E,field,hidden,select,link
from superhuman.capabilities import local
from . import storage,personality,baseline,proactive,DEFERRED

def fail(exc):raise HTTPException(409,str(exc)) from exc
def go(url):return RedirectResponse(url,status_code=303)
def folders():return [(k,ux.ROLES[k]) for k in ux.NAMES if k!='twin']+[('global','Shared facts')]
def optional(label,name,value='',area=False):return field(label,name,value,area).replace(' required','')
def nav():return '<p>'+link('/storage','Storage')+' · '+link('/storage/search','Preview retrieval')+' · '+link('/documents','Generated outputs')+' · '+link('/research-desk','Research')+' · '+link('/memory','Memory')+'</p>'
def project_options(scope):
    from superhuman.workspace.model import projects
    return [('', 'Department-wide')]+[(r['kind']+':'+r['id'],r['name']) for r in projects() if r['scope']==scope]
def form(item,scope):
    r=item or {};kind=r.get('kind','document');name=r.get('filename','')
    out='<form method="post" action="/storage/save">'+hidden('ident',r.get('id',''))+hidden('expected',r.get('version',0))
    if r.get('id'):out+=hidden('scope',scope)+hidden('kind',kind)+hidden('filename',name)+'<p>'+E(dict(folders())[scope])+' · '+E(kind)+' · '+E(name)+'</p>'
    else:
        out+=hidden('scope',scope)+select('Item type','kind',[(kind,kind.capitalize())],kind)
        if kind=='document':out+=field('Existing filename in this department','filename',name)
    out+=field('Title','title',r.get('title',''))
    if kind=='fact':out+=field('Stable fact key, e.g. edsync.waitlist','fact_key',r.get('fact_key',''))+field('Confirmed fact or value','content',r.get('content',''),True)
    out+=select('Project','project',project_options(scope),r.get('project_kind','')+':'+r.get('project_id','') if r.get('project_id') else '')+optional('Tags, separated by commas','tags',r.get('tags',''))+select('Sensitivity','sensitivity',[(v,v.capitalize()) for v in team.SENSITIVITIES],r.get('sensitivity','confidential'))
    access=json.loads(r.get('access','[]'))
    out+='<fieldset><legend>Agent access</legend><p>The owning department can retrieve approved material within task sensitivity and project limits. Other agents need a named grant. All agents is limited to public/internal items.</p>'
    for ident,label in [('all','All agents')]+list(ux.NAMES.items()):out+='<label><input type="checkbox" name="access" value="'+E(ident)+'"'+(' checked' if ident in access else '')+'> '+E(label)+'</label>'
    out+='</fieldset>'+optional('Source or evidence reference (required for approval)','source',r.get('source',''))+optional('Source date (YYYY-MM-DD)','source_date',r.get('source_date',''))+optional('Review on (YYYY-MM-DD)','review_on',r.get('review_on',''))+select('Status','status',[(v,v.capitalize()) for v in ('draft','approved','archived')],r.get('status','draft'))+'<p>Approved means you accept this source for use. It does not establish independent factual verification. Approval records the current file hash. If a file changes, reconfirm its version here. Archive an outdated fact before approving a replacement.</p><button>Save Storage record</button></form>'
    return out

def install(app):
    from superhuman.organisation.web import install as install_organisation
    install_organisation(app)
    # Replace the old landing destination while preserving its bookmarked URL.
    app.router.routes[:]=[r for r in app.router.routes if not (getattr(r,'path','')=='/knowledge' and 'GET' in (getattr(r,'methods',set()) or set()))]
    @app.get('/knowledge')
    def old_knowledge():return go('/storage')
    @app.get('/storage')
    def home():
        items=storage.rows();body='<h1>Storage</h1><p>Documents and approved facts, organised by owning department. Files remain in their existing workspace.</p>'+nav()+'<div class="shell-grid">'
        for scope,label in folders():
            records=[r for r in items if r['scope']==scope]
            body+='<section class="card"><h2>'+link('/storage/departments/'+scope,label)+'</h2><p>'+str(len(records))+' catalogued items · '+str(sum(r['status']=='approved' for r in records))+' approved</p></section>'
        return render(body+'</div>','Storage')
    @app.get('/storage/departments/{scope}')
    def department(scope:str,q:str='',status:str='',tag:str='',project:str='',page:int=1):
        if scope not in dict(folders()) or len(q)>200 or len(tag)>100 or not 1<=page<=10000 or status not in ('','draft','approved','archived'):raise HTTPException(400,'Invalid Storage filter')
        records=[r for r in storage.rows() if r['scope']==scope and (not status or r['status']==status) and (not tag or tag.casefold() in r['tags'].split(',')) and (not project or r['project_id']==project) and (not q or q.casefold() in (r['title']+' '+r['filename']+' '+r['tags']+' '+r['fact_key']).casefold())]
        body='<h1>'+E(dict(folders())[scope])+'</h1>'+nav()+'<p>'+link('/storage/new?'+urlencode({'scope':scope,'kind':'fact'}),'Add fact')+(' · '+link('/storage/new?'+urlencode({'scope':scope,'kind':'document'}),'Register document') if scope!='global' else '')+'</p>'
        body+='<form method="get">'+optional('Search title, filename, key or tags','q',q)+select('Status','status',[('','All')]+[(v,v.capitalize()) for v in ('draft','approved','archived')],status)+optional('Exact tag','tag',tag)+select('Project','project',[('','All projects')]+[(r['id'],r['name']) for r in __import__('superhuman.workspace.model',fromlist=['projects']).projects() if r['scope']==scope],project)+'<button>Filter</button></form><p>'+str(len(records))+' matching items.</p>'
        for r in records[(page-1)*30:page*30]:body+='<article class="card"><h2>'+link('/storage/items/'+r['id'],r['title'])+'</h2><p>'+E(r['kind']+' · '+r['status']+' · '+r['sensitivity']+' · v'+str(r['version']))+'</p><p>'+E(r['tags'])+'</p><p>'+E(storage.health(r))+'</p>'+('<p>Project: '+link(('/team/projects/' if r['project_kind']=='team' else '/work/')+r['project_id'],r['project_id'])+'</p>' if r['project_id'] else '')+'</article>'
        if not records:body+='<p>No matching catalogued items.</p>'
        if page>1:body+=link('?'+urlencode(dict(q=q,status=status,tag=tag,project=project,page=page-1)),'Previous')
        if len(records)>page*30:body+=link('?'+urlencode(dict(q=q,status=status,tag=tag,project=project,page=page+1)),'Next')
        if scope!='global':
            body+='<details><summary>Upload a source file</summary><p>Supported text, PDF, Word and Excel sources, up to 10 MB. Existing filenames are never overwritten. Upload first, then review the metadata and approve separately.</p><form method="post" action="/storage/upload" enctype="multipart/form-data">'+hidden('scope',scope)+'<label>File<input type="file" name="file" required></label><button>Upload file</button></form></details>'
            registered={r['filename'] for r in storage.rows() if r['scope']==scope and r['kind']=='document'}
            names=sorted(f.name for f in local.inputs(scope).iterdir() if f.is_file() and not f.is_symlink() and f.suffix.lower() in local.FORMATS and f.name not in registered)
            body+='<details><summary>Existing files awaiting registration ('+str(len(names))+')</summary>'
            for name in names[:100]:body+='<p>'+link('/storage/new?'+urlencode(dict(scope=scope,kind='document',filename=name)),name)+'</p>'
            body+='</details>'
        return render(body,'Storage · '+dict(folders())[scope])
    @app.get('/storage/new')
    def new(scope:str='edsync_product',kind:str='document',filename:str=''):
        if scope not in dict(folders()) or kind not in ('document','fact') or scope=='global' and kind=='document':raise HTTPException(400,'Choose a valid department and item type')
        if filename:
            try:local.file_for(scope,filename)
            except ValueError as exc:fail(exc)
        return render('<h1>Register '+E(kind)+'</h1>'+nav()+form({'kind':kind,'filename':filename},scope),'Register Storage item')
    @app.get('/storage/items/{ident}')
    def detail(ident:str):
        try:r=storage.get(ident)
        except ValueError as exc:fail(exc)
        body='<h1>'+E(r['title'])+'</h1>'+nav()+'<p>'+E(storage.health(r))+'</p>'
        if r['kind']=='document':body+='<p>'+link('/storage/files/'+ident,'Download source file')+'</p>'
        body+=('<section class="ui-notice"><h2>Saved fact</h2><p>'+E(r['content'])+'</p></section>' if r['kind']=='fact' else '')+'<p>'+E(r['status'].capitalize()+' · '+r['sensitivity'].capitalize()+' · Version '+str(r['version']))+'</p><details class="ui-disclosure"><summary>Manage source & access</summary>'+form(r,r['scope'])+'</details><details><summary>Version history</summary>'
        with p.connect() as db:history=db.execute('SELECT version,snapshot,created_at FROM storage_versions WHERE id=? ORDER BY version DESC LIMIT 20',(ident,)).fetchall()
        for v in history:
            saved=json.loads(v['snapshot']);body+='<section class="card"><strong>Version '+str(v['version'])+' · '+E(v['created_at'])+'</strong><pre>'+E(json.dumps(saved,indent=2,ensure_ascii=False))+'</pre></section>'
        return render(body+'</details>','Storage item')
    @app.get('/storage/files/{ident}')
    def download(ident:str):
        try:
            r=storage.get(ident)
            if r['kind']!='document':raise ValueError('This item is a fact')
            file=local.file_for(r['scope'],r['filename'])
        except ValueError as exc:fail(exc)
        return FileResponse(file,filename=r['filename'])
    @app.post('/storage/upload')
    async def upload(scope:str=Form(...),file:UploadFile=File(...)):
        try:
            if scope not in dict(folders()) or scope=='global':raise ValueError('Choose a document department')
            content=await file.read(local.MAX_BYTES+1);saved=local.store_bytes(scope,file.filename or '',content)
        except (ValueError,OSError) as exc:fail(exc)
        finally:await file.close()
        return go('/storage/new?'+urlencode(dict(scope=scope,kind='document',filename=saved['filename'])))
    @app.post('/storage/save')
    def save(scope:str=Form(...),kind:str=Form(...),title:str=Form(...),filename:str=Form(''),content:str=Form(''),fact_key:str=Form(''),project:str=Form(''),tags:str=Form(''),sensitivity:str=Form('confidential'),access:list[str]=Form([]),source:str=Form(''),source_date:str=Form(''),review_on:str=Form(''),status:str=Form('draft'),ident:str=Form(''),expected:int=Form(0)):
        try:
            pk,pid=project.split(':',1) if project else ('','')
            ident=storage.save(scope,kind,title,filename,content,fact_key,pk,pid,tags,sensitivity,access,source,source_date,review_on,status,ident,expected)
        except (ValueError,OSError) as exc:fail(exc)
        return go('/storage/items/'+ident)
    @app.get('/storage/search')
    def search(employee:str='twin',q:str='',project_id:str='',maximum:str='internal'):
        if employee not in ux.NAMES or maximum not in team.SENSITIVITIES or len(q)>500:raise HTTPException(400,'Invalid retrieval preview')
        body='<h1>Preview agent retrieval</h1>'+nav()+'<p>This is the owner preview. It shows what the selected agent may retrieve with the selected project and sensitivity ceiling. An actual task uses its own controls.</p><form method="get">'+select('Agent','employee',list(ux.NAMES.items()),employee)+optional('Question or topic','q',q)+optional('Project ID (optional)','project_id',project_id)+select('Sensitivity ceiling','maximum',[(v,v.capitalize()) for v in team.SENSITIVITIES],maximum)+'<button>Preview</button></form>'
        if q:
            try:data=storage.search(employee,q,project_id,maximum)
            except ValueError as exc:fail(exc)
            body+='<p>'+E(data['limitations'])+'</p>'
            for r in data['items']:body+='<article class="card"><h2>'+link(r['url'],r['title'])+'</h2><p>Source: '+E(r['source'])+' · Version '+str(r['version'])+'</p><pre>'+E(r['excerpt'])+'</pre><p>'+E('; '.join(r['warnings']))+'</p></article>'
            for r in data['issues']:body+='<p class="error">'+E(r.get('title','Source'))+': '+E(r['issue'])+'</p>'
            if not data['items']:body+='<p>No current, approved, permitted matches. Check source approval, access, project tags and sensitivity.</p>'
        return render(body,'Retrieval preview')
    @app.get('/agent-personalities')
    def profiles():
        body='<h1>Agent personalities</h1><p>Professional style applies in conversations, specialist assignments and Twin coordination. It does not grant expertise or permissions.</p>'
        for employee in ux.NAMES:
            r=personality.profile(employee);body+='<article class="card"><h2>'+link('/agent-personalities/'+employee,ux.NAMES[employee])+'</h2><p>'+E(ux.ROLES[employee])+'</p><p>'+E(r['style'])+'</p></article>'
        return render(body,'Agent personalities')
    @app.get('/agent-personalities/{employee}')
    def profile(employee:str):
        try:r=personality.profile(employee)
        except ValueError as exc:fail(exc)
        return render('<h1>'+E(ux.NAMES[employee])+'</h1><p>'+E(ux.ROLES[employee])+'</p><p>'+E(personality.GUARD)+'</p><form method="post">'+hidden('expected',r['version'])+field('Professional personality','style',r['style'],True)+'<button>Save personality</button></form>','Personality')
    @app.post('/agent-personalities/{employee}')
    def profile_save(employee:str,expected:int=Form(...),style:str=Form(...)):
        try:personality.update(employee,expected,style)
        except ValueError as exc:fail(exc)
        return go('/agent-personalities/'+employee)
    @app.get('/system-baseline')
    def system_baseline():
        data=baseline.report();body='<h1>System baseline</h1><p>'+E(data['checked_at'])+'</p><p>'+E(data['limitations'])+'</p><form method="post" action="/system-baseline/capture"><button>Save this local baseline</button></form><p>'+link('/system-baseline.json','Download local evidence')+' · '+link('/system-checks','Existing integrity checks')+' · '+link('/inboxes/setup','Connection setup')+'</p>'
        for c in data['checks']:body+='<section class="card"><h2>'+E(c['area'])+'</h2><strong>'+E(c['state'].replace('_',' '))+'</strong><pre>'+E(json.dumps(c['evidence'],indent=2))+'</pre><p>'+E(c['next'])+'</p></section>'
        body+='<h2>Employee activation</h2>'
        for r in data['employees']:body+='<details><summary>'+E(r['name'])+' · '+__import__('superhuman.trust',fromlist=['employee_status']).employee_status(r)+'</summary><p>'+E(', '.join(r['allowed_tools']))+'</p></details>'
        body+='<h2>Connections</h2>'
        for c in data['channels']:body+='<p>'+E(c['label'])+' · '+E(c['evidence_state'])+' · Last sync '+E(c['last_sync'] or 'Not observed')+'</p>'
        if not data['channels']:body+='<p>No connections recorded.</p>'
        body+='<details><summary>Deferred gaps for the next issues review</summary>'+''.join('<p>'+E(v)+'</p>' for v in DEFERRED)+'</details>'
        with p.connect() as db:
            exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='foundation_baselines'").fetchone()
            history=db.execute('SELECT id,checked_at FROM foundation_baselines ORDER BY id DESC LIMIT 5').fetchall() if exists else []
        body+='<h2>Saved baselines</h2>'+''.join('<p>'+link('/system-baseline/saved/'+str(r['id']),r['checked_at'])+'</p>' for r in history)
        return render(body,'System baseline')
    @app.post('/system-baseline/capture')
    def capture():baseline.capture();return go('/system-baseline')
    @app.get('/system-baseline.json')
    def baseline_json():return Response(json.dumps(baseline.report(),indent=2),media_type='application/json')
    @app.get('/system-baseline/saved/{ident}')
    def saved(ident:int):
        with p.connect() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='foundation_baselines'").fetchone():raise HTTPException(404,'Saved baseline not found')
            row=db.execute('SELECT report FROM foundation_baselines WHERE id=?',(ident,)).fetchone()
        if not row:raise HTTPException(404,'Saved baseline not found')
        return Response(row['report'],media_type='application/json')
    @app.get('/proactive')
    def proactive_page(history:bool=False):
        body='<h1>Proactive work checks</h1><p>The worker scans enabled rules at most once a minute while running and unpaused. Scans use no model calls. Notify creates in-app signals. Twin review also makes the signal available to the existing metered coordinator; all approval and budget gates remain.</p><form method="post" action="/proactive/scan"><button>Run local scan now</button></form><p>'+link('/proactive?history=true','Show resolved history')+'</p>'
        paused=bool(proactive.control()['paused'])
        body+='<p>Scanner: '+('Paused' if paused else 'Enabled')+'</p><form method="post" action="/proactive/pause">'+hidden('expected','yes' if paused else 'no')+hidden('paused','no' if paused else 'yes')+'<button class="secondary">'+('Resume proactive scanning' if paused else 'Pause proactive scanning')+'</button></form>'
        for s in proactive.signals(include_resolved=history)[:100]:
            body+='<article class="card"><h2>'+link(s['url'],s['title'])+'</h2><p>'+E(s['detail'])+'</p><small>'+E(s['state'])+' · Episode '+str(s['episode'])+'</small>'
            if s['state']=='new':body+='<form method="post" action="/proactive/acknowledge">'+hidden('ident',s['id'])+hidden('episode',s['episode'])+'<button class="secondary">Acknowledge</button></form>'
            body+='</article>'
        body+='<h2>Rules</h2>'
        for r in proactive.rules():body+='<details><summary>'+E(proactive.RULES[r['id']][0])+' · '+('Enabled' if r['enabled'] else 'Disabled')+'</summary><form method="post" action="/proactive/rules/'+r['id']+'">'+hidden('expected',r['version'])+select('Enabled','enabled',[('yes','Yes'),('no','No')],'yes' if r['enabled'] else 'no')+field('Threshold in hours (deadline/stalled rules)','hours',r['hours'])+select('Action','action',[('notify','Notify in app'),('twin_review','Request Twin review within existing controls')],r['action'])+'<button>Save rule</button></form></details>'
        return render(body,'Proactive checks')
    @app.post('/proactive/scan')
    def scan():proactive.scan(force=True);return go('/proactive')
    @app.post('/proactive/acknowledge')
    def acknowledge(ident:str=Form(...),episode:int=Form(...)):
        try:proactive.acknowledge(ident,episode)
        except ValueError as exc:fail(exc)
        return go('/proactive')
    @app.post('/proactive/rules/{ident}')
    def rule(ident:str,expected:int=Form(...),enabled:str=Form(...),hours:int=Form(...),action:str=Form(...)):
        try:
            if enabled not in ('yes','no'):raise ValueError('Choose Yes or No')
            proactive.configure(ident,expected,enabled=='yes',hours,action)
        except ValueError as exc:fail(exc)
        return go('/proactive')

    @app.post('/proactive/pause')
    def scanner_pause(expected:str=Form(...),paused:str=Form(...)):
        try:
            if expected not in ('yes','no') or paused not in ('yes','no'):raise ValueError('Choose a valid pause state')
            proactive.set_pause(expected=='yes',paused=='yes')
        except ValueError as exc:fail(exc)
        return go('/proactive')
