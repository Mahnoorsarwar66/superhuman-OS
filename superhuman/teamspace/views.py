"""Read-only layout helpers. Existing conversations, POST handlers and polling stay authoritative."""
from urllib.parse import urlencode
from fastapi import HTTPException
from superhuman.experience import store as ux,web as old
from superhuman.workspace.web import render,E,link,hidden,field,pager
from superhuman.practice.web import portrait
from superhuman.interface.chrome import capture
from superhuman.interface.tree import Node,parse,html
from superhuman.dialogue import store as dialogue


def room_rows(employee='all',q='',project_id='',project_kind=''):
    if employee not in ('all',*ux.NAMES) or len(q)>200 or bool(project_id)!=bool(project_kind):raise HTTPException(400,'Choose a valid conversation filter')
    if project_kind and project_kind not in ('team','canonical'):raise HTTPException(400,'Choose a valid project type')
    if project_id:
        try:ux.project(project_kind,project_id)
        except ValueError as exc:raise HTTPException(404,str(exc)) from exc
    terms=['1=1'];args=[]
    for col,value in [('r.employee',employee if employee!='all' else ''),('r.project_id',project_id),('r.project_kind',project_kind)]:
        if value:terms.append(col+'=?');args.append(value)
    if q:terms.append('instr(lower(d.title),lower(?))>0');args.append(q)
    return ux.read('ux_rooms','SELECT d.*,r.employee,r.project_kind,r.project_id FROM ux_rooms r JOIN dialogue_threads d ON d.id=r.thread_id WHERE '+' AND '.join(terms)+' ORDER BY d.updated_at DESC,d.id',tuple(args))


def tabs(chosen='room'):
    return '<nav class="ui-tabs teamspace-tabs" aria-label="Team views" data-interface-tabs>'+''.join('<a href="'+url+'"'+(' aria-current="page"' if key==chosen else '')+'>'+label+'</a>' for key,url,label in [('room','/team-room','Conversations'),('board','/team-room?tab=board','Employees'),('feed','/team-room?tab=feed','Activity')])+'</nav>'


def project_name(kind,pid):
    try:return ux.project(kind,pid)['title']
    except ValueError:return 'Unavailable project'


def rail(employee='all',selected='',project_id='',project_kind=''):
    body='<details class="teamspace-rail" open><summary>People & conversations</summary><div class="teamspace-rail-body"><p class="teamspace-rail-title">Your team</p><a class="teamspace-rail-action" href="/team-room?'+urlencode({'employee':employee})+'#new-conversation">＋ New conversation</a><nav aria-label="Conversation shortcuts">'+link('/team-room','All conversations')+'</nav><h2>Direct messages</h2><nav aria-label="Employees">'
    for ident,name in ux.NAMES.items():
        body+='<a class="teamspace-person" href="/team-room?employee='+ident+'"'+(' aria-current="page"' if employee==ident and not project_id else '')+'>'+portrait(ident)+'<span>'+E(name)+'</span></a>'
    body+='</nav><h2>Project conversations</h2><nav aria-label="Project conversations">'
    projects=ux.read('ux_rooms',"SELECT r.project_kind,r.project_id,MAX(d.updated_at) AS recent FROM ux_rooms r JOIN dialogue_threads d ON d.id=r.thread_id WHERE r.project_id<>'' GROUP BY r.project_kind,r.project_id ORDER BY recent DESC LIMIT 30")
    for project in projects:
        active=project_id==project['project_id'] and project_kind==project['project_kind']
        url='/team-room?'+urlencode({'project_id':project['project_id'],'project_kind':project['project_kind']})
        body+='<a href="'+E(url)+'"'+(' aria-current="page"' if active else '')+'><span aria-hidden="true"># </span>'+E(project_name(project['project_kind'],project['project_id']))+'</a>'
    if not projects:body+='<p class="teamspace-rail-hint">Project rooms appear here after you create them from a project’s Conversations view.</p>'
    body+='</nav><h2>Recent conversations</h2><nav aria-label="Recent conversations">'
    recent=room_rows(employee,project_id=project_id,project_kind=project_kind)[:12]
    for r in recent:
        body+='<a href="/team-room/'+r['id']+'"'+(' aria-current="page"' if r['id']==selected else '')+'>'+E(r['title'])+'</a>'
    if not recent:body+='<p class="teamspace-rail-hint">No conversations in this view yet.</p>'
    body+='</nav><div class="teamspace-rail-footer">'+link('/team-room?tab=feed','Team exchanges & decisions')+link('/talk','Earlier department conversations')+'</div></div></details>'
    return body


def home(employee='all',tab='room',page=1,q='',project_id='',project_kind='',legacy=None):
    if tab not in ('room','board','feed'):raise HTTPException(400,'Choose Conversations, Employees or Activity')
    if not 1<=page<=10000:raise HTTPException(400,'Invalid conversation page')
    if tab=='board':return legacy(employee,tab,page,q)
    if tab=='feed':
        content=capture(legacy,employee,tab,page,q)
        return render(tabs('feed')+'<div class="teamspace-layout">'+rail()+'<section class="teamspace-main teamspace-activity" aria-label="Recorded team exchanges">'+content+'</section></div>','Team activity')
    items=room_rows(employee,q,project_id,project_kind)
    title=project_name(project_kind,project_id) if project_id else 'All conversations' if employee=='all' else 'Conversations with '+ux.NAMES[employee]
    body='<header class="teamspace-page-head"><div><p class="eyebrow">Team</p><h1>Conversations</h1></div><p>People, project discussions and recorded team exchanges in one place.</p></header>'+tabs()+'<div class="teamspace-layout">'+rail(employee,project_id=project_id,project_kind=project_kind)+'<section class="teamspace-main" aria-label="Conversation list"><header class="teamspace-heading"><div><h2>'+E(title)+'</h2><p>'+('Conversations explicitly linked to this project.' if project_id else 'Continue a saved conversation or start a new one.')+'</p></div><a class="button" href="#new-conversation">New conversation</a></header>'
    body+='<form class="teamspace-search" method="get" action="/team-room">'+hidden('employee',employee)+hidden('project_id',project_id)+hidden('project_kind',project_kind)+'<label for="conversation-search">Find a conversation</label><div><input id="conversation-search" name="q" value="'+E(q)+'" maxlength="200" placeholder="Search conversation titles"><button class="secondary">Search</button></div></form><div class="teamspace-conversation-list">'
    for r in items[(page-1)*30:page*30]:
        body+='<a class="teamspace-conversation" href="/team-room/'+r['id']+'">'+portrait(r['employee'])+'<span><strong>'+E(r['title'])+'</strong><small>'+E(ux.NAMES[r['employee']])+(' · '+E(project_name(r['project_kind'],r['project_id'])) if r['project_id'] else ' · Direct conversation')+'</small></span><time>'+E(old.stamp(r['updated_at']))+'</time></a>'
    if not items:body+='<section class="ui-empty"><h2>No matching conversations</h2><p>Start a conversation below, or change your search. Project-specific discussions should stay linked to their project.</p></section>'
    body+='</div>'+pager('/team-room',page,len(items),30,{'employee':employee,'q':q,'project_id':project_id,'project_kind':project_kind})
    # Retain the original form and its project/employee validation. Project channels use linked project context.
    chosen=employee if employee in ux.NAMES else ux.project(project_kind,project_id)['scope'] if project_id else 'twin'
    body+='<details class="teamspace-new ui-disclosure" id="new-conversation"><summary>Start a conversation'+(' with '+E(ux.NAMES[employee]) if employee in ux.NAMES else '')+'</summary><p>A direct message is a conversation with one employee. Project rooms keep context tied to the chosen project. Chatting does not approve work.</p>'+old.room_form(chosen,project_kind,project_id)+'</details></section></div>'
    return render(body,'Team conversations')


def room(ident,before,legacy):
    r=ux.room(ident)
    if not r:raise HTTPException(404,'Conversation not found')
    fragment=parse(capture(legacy,ident,before));chat=next((n for n in fragment.find('div') if n.has_class('ux-chat') and n.attrs.get('data-room')==ident),None)
    if chat is None:raise ValueError('Unrecognised conversation template; reload the current installation')
    thread=dialogue.get(ident);chat.set('class',(chat.attrs.get('class') or '')+' teamspace-chat')
    first=next((i for i,node in enumerate(chat.children) if isinstance(node,Node) and 'data-chat-status' in node.attrs),None)
    if first is None:raise ValueError('Conversation status anchor is missing')
    detail=E(ux.NAMES[r['employee']]+' · '+ux.ROLES[r['employee']])
    if r['project_id']:detail+=' · '+link(('/team/projects/' if r['project_kind']=='team' else '/work/')+r['project_id'],project_name(r['project_kind'],r['project_id']))
    else:detail+=' · Direct conversation'
    heading='<header class="teamspace-chat-head">'+portrait(r['employee'])+'<div><h1>'+E(thread['title'])+'</h1><p>'+detail+'</p></div><a class="button secondary" href="/team-room?'+urlencode({'employee':r['employee']})+'">All conversations</a></header>'
    chat.children=parse(heading).children+chat.children[first:]
    proposals=next((n for n in chat.children if isinstance(n,Node) and 'data-proposals' in n.attrs),None)
    if proposals:
        # Preserve the live target even when empty; future polling may insert a proposal.
        wrapper=Node('details',[('class','teamspace-proposed')],children=[Node('summary',children=['Suggested work & reviewed actions']),proposals])
        chat.children[chat.children.index(proposals)]=wrapper
    body='<div class="teamspace-room-top"><p class="eyebrow">Team conversations</p>'+link('/team-room?employee='+r['employee'],'Browse conversations')+'</div>'+tabs()+'<div class="teamspace-layout teamspace-room-layout">'+rail(r['employee'],ident,r['project_id'],r['project_kind'])+'<section class="teamspace-main" aria-label="Conversation">'+chat.html()+'</section></div>'
    return render(body,thread['title'])
