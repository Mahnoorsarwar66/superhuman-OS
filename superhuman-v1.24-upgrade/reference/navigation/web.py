"""Navigation adapters and read-only landing pages over existing records."""
from importlib import import_module
from urllib.parse import urlencode, quote
from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from . import shell


def install(app):
    from superhuman.hosted import views
    from superhuman.projects import engine as projects
    from superhuman.runtime import engine as runtime
    from superhuman.core.router import WORKSTREAMS
    views.page=shell.page
    def legacy_page(body,title='Workspace',active='projects'):
        return HTMLResponse(shell.page(body,title))
    # All original handlers and forms survive. Replace only their page renderers.
    for module in ('superhuman.runtime.web','superhuman.capabilities.coding_web',
                   'superhuman.capabilities.document_web','superhuman.capabilities.web',
                   'superhuman.projects.studio','superhuman.projects.web','superhuman.dashboard.app'):
        import_module(module).page=legacy_page
    app.add_middleware(shell.PathContext)
    def render(body,title):return HTMLResponse(shell.page(body,title))
    e=shell.esc
    def card(title,description,link,label='Open'):
        return '<section class="card"><h2>'+e(title)+'</h2><p>'+e(description)+'</p><a class="button secondary" href="'+e(link)+'">'+e(label)+'</a></section>'

    # Keep POST /projects intact; consolidate its existing listing under workstreams.
    app.router.routes[:]=[r for r in app.router.routes if not (getattr(r,'path','')=='/projects' and 'GET' in getattr(r,'methods',set()))]
    @app.get('/projects')
    def project_listing(workstream:str='all'):
        if workstream!='all' and workstream not in WORKSTREAMS:raise HTTPException(400,'Unknown workstream')
        from superhuman.projects.studio import cards
        rows=projects.listing()
        if workstream!='all':rows=[p for p in rows if p['workstream']==workstream]
        options='<option value="all">All workstreams</option>'+''.join('<option value="'+e(k)+'"'+(' selected' if k==workstream else '')+'>'+e(v['name'])+'</option>' for k,v in WORKSTREAMS.items())
        create_options=''.join('<option value="'+e(k)+'"'+(' selected' if k==workstream else '')+'>'+e(v['name'])+'</option>' for k,v in WORKSTREAMS.items())
        body='<h1>Your projects</h1><p>Choose a workstream, then open an objective to see its work.</p><form method="get" action="/projects"><label>Workstream<select name="workstream">'+options+'</select></label><button class="secondary">Show projects</button></form>'
        body+='<details id="new-project"><summary>Create a project</summary><form method="post" action="/projects"><label>Workstream<select name="workstream">'+create_options+'</select></label><label>Objective<input name="objective" maxlength="1000" required></label><label>Context<textarea name="details" maxlength="12000"></textarea></label><label>Model request limit<input name="max_calls" type="number" min="1" max="100" value="12" required></label><p class="muted">Creating a project uses no model requests. Review its plan before execution.</p><button>Create project</button></form></details>'
        body+='<h2>'+str(len(rows))+' objectives</h2>'+cards(rows)
        return render(body,'Projects')

    @app.get('/knowledge')
    def knowledge():
        return render('<h1>Your knowledge workspace</h1><p>Find the materials and research behind your work.</p><div class="shell-grid">'+
            card('Source files','Upload, inspect and search files within a workstream.','/tools','Open files')+
            card('Documents','Create and download Word, PDF and spreadsheet outputs.','/documents','Open documents')+
            card('Research','Questions, source cards, reading notes and research outputs.','/research-desk','Open Research Desk')+
            card('Personal memory','Review saved preferences, decisions and feedback.','/memory','Open memory')+'</div>','Knowledge')

    @app.get('/settings')
    def settings():
        return render('<h1>Workspace settings</h1><p>Manage the context Superhuman uses and find connection instructions.</p><div class="shell-grid">'+
            card('Memory & Writing DNA','Review and edit saved preferences, writing guidance and feedback.','/memory')+
            card('Context preview','Inspect which saved information is selected for a task.','/memory/preview')+
            card('Inbox connections','Read the existing connection guide. Credentials continue to be managed with the existing setup tools.','/inboxes/setup','Open connection guide')+
            card('Execution status','Inspect current worker activity and task progress.','/runtime','Open execution')+card('System checks','Check inbox syncs, stored outputs and department assignment.','/system-checks','Open system checks')+'</div>','Settings')

    @app.get('/reviews')
    def reviews():
        rows=[]
        for p in projects.listing():
            full=projects.get(p['id'])
            pending=[t for t in full['tasks'] if t['status']=='needs_review']
            if p['status']=='plan_review' or pending:
                description='Plan awaiting approval.' if p['status']=='plan_review' else str(len(pending))+' task output(s) awaiting review.'
                rows.append(card(p['objective'],description,'/work/'+quote(p['id'],safe=''),'Review project'))
        body='<h1>Decisions waiting for you</h1><p>Open the original review screen to inspect and act on each item.</p>'
        body+=''.join(rows) or '<section class="card"><p>No project plans or task outputs currently await review.</p></section>'
        body+='<h2>Other review queues</h2><div class="shell-grid">'+card('Task suggestions','Approve, edit or dismiss proposed work.','/tasks')+card('Calendar suggestions','Review proposed meetings and events.','/calendar/suggestions')+card('Proposed memory','Confirm or revise proposed preferences and feedback.','/memory?status=proposed')+card('Research source suggestions','Open a research area to review its cited sources and synopsis proposals.','/research-desk')+'</div>'
        return render(body,'Reviews')

    @app.get('/workspace/projects/{pid}/{tab}')
    def project_context(pid:str,tab:str,page:int=1):
        if tab not in ('conversations','knowledge','activity') or not 1<=page<=10000:raise HTTPException(404,'Workspace page not found')
        try:p=projects.get(pid)
        except ValueError as exc:raise HTTPException(404,str(exc)) from exc
        scope=p['workstream'];label=WORKSTREAMS.get(scope,{}).get('name',scope)
        body='<h1>'+e(p['objective'])+'</h1>'
        if tab=='conversations':
            from superhuman.dialogue import store as dialogue
            dialogue.initialize()
            with projects.connect(projects.DEFAULT_DB) as db:
                rows=[dict(r) for r in db.execute('SELECT * FROM dialogue_threads WHERE scope=? ORDER BY updated_at DESC,id LIMIT 50 OFFSET ?',(scope,(page-1)*50))]
            body+='<p>Conversations shared across the '+e(label)+' workstream. Existing conversations are associated with workstreams, rather than individual objectives.</p>'
            for row in rows:body+=card(row['title'],'Updated '+row['updated_at'],'/talk/'+quote(row['id'],safe=''),'Open conversation')
            if not rows:body+='<p>No conversations in this workstream on this page.</p>'
            if page>1:body+='<p><a href="?page='+str(page-1)+'">Previous</a></p>'
            if len(rows)==50:body+='<p><a href="?page='+str(page+1)+'">Next</a></p>'
            body+='<p><a href="/talk">Open Talk to start a conversation</a></p>'
        elif tab=='knowledge':
            body+='<p>Files and document tools shared across the '+e(label)+' workstream. Project deliverables remain on this project’s Tasks tab.</p><div class="shell-grid">'
            body+=card('Source files','Inspect this workstream’s uploaded materials.','/tools?'+urlencode({'project':scope}))
            body+=card('Documents','Open document generation for this workstream.','/documents?'+urlencode({'project':scope}))
            body+='</div><h2>Research areas in this workstream</h2>'
            from superhuman.researchdesk import store as research
            research.initialize()
            with projects.connect(projects.DEFAULT_DB) as db:
                rows=[dict(r) for r in db.execute('SELECT * FROM research_areas WHERE scope=? ORDER BY updated_at DESC,id LIMIT 50 OFFSET ?',(scope,(page-1)*50))]
            for row in rows:
                body+=card(row['title'],'Shared workstream research','/research-desk/'+quote(row['id'],safe=''))
            if not rows:body+='<p>No research areas in this workstream on this page.</p>'
            if page>1:body+='<p><a href="?page='+str(page-1)+'">Previous</a></p>'
            if len(rows)==50:body+='<p><a href="?page='+str(page+1)+'">Next</a></p>'
        else:
            rows=runtime.history(pid,limit=100)
            body+='<p>Latest 100 recorded execution events for this project.</p>'
            if rows:
                body+='<table><thead><tr><th>When</th><th>Action</th><th>Task</th></tr></thead><tbody>'+''.join('<tr><td>'+e(r['created_at'])+'</td><td>'+e(r['action'].replace('_',' '))+'</td><td>'+e(r['task_id'] or 'Project')+'</td></tr>' for r in rows)+'</tbody></table>'
            else:body+='<p>No execution events recorded for this project yet.</p>'
        return render(body,tab.capitalize()+' · '+p['objective'])

    from superhuman.departments.web import install as install_departments
    install_departments(app)

    from superhuman.planning.web import install as install_planning
    install_planning(app)

    from superhuman.repairs.web import install as install_repairs
    install_repairs(app)
