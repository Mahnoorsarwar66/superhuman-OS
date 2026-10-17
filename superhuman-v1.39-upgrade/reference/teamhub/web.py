"""One owner workspace: people, project channels, decisions and work, using native forms."""
import json
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4
from fastapi import Form,File,UploadFile,HTTPException
from fastapi.responses import FileResponse
from superhuman.projects import engine as p
from superhuman.team import store as team
from superhuman.experience import store as ux,web as old
from superhuman.dialogue import store as d
from superhuman.milestones import store as ms
from superhuman.foundation import storage
from superhuman.workspace.web import E,hidden,field,select,render,redirect,rich
from superhuman.practice.web import portrait
from superhuman.interface.chrome import capture
from superhuman.interface.tree import parse
from . import store as s,cards

ASSETS=Path(__file__).with_name('assets')

def href(**values):return '/team-hub?'+urlencode(values)
def a(url,label,cls=''):return '<a'+(' class="'+cls+'"' if cls else '')+' href="'+E(url)+'">'+E(label)+'</a>'
def form(action,body,label,cls=''):return '<form method="post" action="'+E(action)+'"'+(' class="'+cls+'"' if cls else '')+'>'+body+'<button>'+E(label)+'</button></form>'
def optional(label,name,value='',area=False):return field(label,name,value,area).replace(' required','')
def fail(exc):raise HTTPException(409,str(exc)) from exc

def strip():
    body='<div class="hub-people" aria-label="Your eight AI employees">'
    from superhuman.trust import readiness
    ready=readiness()
    for item in ux.board():
        state='Worker unavailable' if not item['online'] else {'reviewing':'Output awaiting review','working':'Working','idle':('Ready' if ready['work_ready'] else 'Work blocked'),'waiting':'Waiting','blocked':'Blocked','paused':'Paused'}.get(item['state'],item['state'])
        body+='<a href="'+href(view='employees',employee=item['id'])+'">'+portrait(item['id'])+'<span><strong>'+E(item['name'])+'</strong><small>'+E(state)+'</small></span></a>'
    return body+'</div>'

def attention(path=p.DEFAULT_DB):
    result=[]
    for card in s.read("SELECT * FROM hub_cards WHERE status IN ('proposed','owner_review','revision') ORDER BY created_at DESC",path=path):result.append(dict(title=card['title'],kind='Work proposal · '+card['status'].replace('_',' '),url='/team-hub/cards/'+card['id'],detail=card['decision'] or 'Review the outcome, assignment and authorization needed.'))
    for req in team.requests(path):
        if req['status'] in ('open','escalated'):result.append(dict(title=team.task(req['task_id'],path)['title'],kind='Saved question / handoff',url='/team/requests/'+req['id'],detail=req['kind'].replace('_',' ')))
    for m in ms.listing(path=path):
        if m['state'] in ('owner_review','needs_owner'):result.append(dict(title=m['title'],kind='Milestone decision',url='/milestones/'+m['id'],detail='Review the current packet and saved reviews.'))
    for r in s.read("SELECT r.*,t.channel_id,t.title FROM hub_rounds r JOIN hub_topics t ON t.id=r.topic_id WHERE r.status='failed' ORDER BY r.created_at DESC LIMIT 100",path=path):result.append(dict(title=r['title'],kind='Discussion stopped',url=href(topic=r['topic_id']),detail=r['error']))
    for turn in s.read("SELECT d.id,d.thread_id,d.reply FROM dialogue_turns d LEFT JOIN hub_rooms h ON h.id=d.thread_id WHERE d.status='done' AND (instr(lower(d.reply),'@mahnoor')>0 OR instr(lower(d.reply),'@owner')>0) ORDER BY d.finished_at DESC LIMIT 50",path=path):
        linked=s.read('SELECT t.channel_id FROM hub_steps s JOIN hub_rounds r ON r.id=s.round_id JOIN hub_topics t ON t.id=r.topic_id WHERE s.turn_id=?',(turn['id'],),path)
        unread=channel_unread(s.channel(linked[0]['channel_id'],path)) if linked else s.state(turn['thread_id'],path)['seen']!=s.room_signature(turn['thread_id'],path)
        if unread:result.append(dict(title='Mention in a saved reply',kind='Mention · needs your attention',url='/team-room/'+turn['thread_id']+'#turn-'+turn['id'],detail=turn['reply'][:240]))
    return result

def rail(view='messages',selected=''):
    channels=s.read('SELECT * FROM hub_channels WHERE archived=0 ORDER BY pinned DESC,title');items=attention()
    body='<details class="hub-rail" open><summary>Team navigation</summary><div><p class="hub-label">Workspace</p><nav aria-label="Team navigation">'
    for key,label in [('messages','Conversations'),('attention','Needs your attention'+(' · '+str(len(items)) if items else '')),('employees','Employees'),('activity','Activity'),('archive','Archive')]:body+='<a href="'+href(view=key)+'"'+(' aria-current="page"' if view==key else '')+'>'+label+'</a>'
    body+='</nav><p class="hub-label">Direct messages</p><div class="hub-dms">'
    for ident,name in ux.NAMES.items():body+=form('/team-hub/direct/'+ident,portrait(ident)+'<span>'+E(name)+'</span>','Open',cls='hub-direct')
    body+='</div><p class="hub-label">Project channels</p><nav aria-label="Project channels">'
    for c in channels:body+='<a href="'+href(channel=c['id'])+'"'+(' aria-current="page"' if selected==c['id'] else '')+'># '+E(c['title'])+(' <span class="hub-dot">New replies</span>' if channel_unread(c) else '')+'</a>'
    if not channels:body+='<p class="hub-hint">Add a channel for an approved project team.</p>'
    body+='</nav>'+a(href(view='new'),'＋ Project channel','hub-rail-new')+'<p class="hub-label">The Twin</p><nav>'+a(href(view='twin'),'Priorities, preferences & briefings')+'</nav></div></details>'
    return body

def channel_count(cid):return s.one("SELECT COUNT(*) AS n FROM hub_steps s JOIN hub_rounds r ON r.id=s.round_id JOIN hub_topics t ON t.id=r.topic_id JOIN dialogue_turns d ON d.id=s.turn_id WHERE t.channel_id=? AND d.status='done'",(cid,))['n']
def channel_unread(c):return channel_count(c['id'])>c['seen']

def layout(body,view='messages',selected='',title='Team',panel=''):
    from superhuman.trust import readiness
    ready=readiness()
    top=('<p class="hub-readiness" role="status">'+E(ready['reason'])+' · '+a('/team/budget','Review budget')+' · '+a('/system-baseline','System readiness')+'</p>')+'<header class="hub-head"><div><p class="eyebrow">Mahnoor & her team</p><h1>Team</h1></div><p>Talk together. Follow the work. Make the decisions that need you.</p></header>'+strip()+'<nav class="hub-mobile-tabs" aria-label="Team workspace" data-interface-tabs>'+a('/team-hub','Conversations')+a(href(view='employees'),'Employees')+a(href(view='attention'),'Needs your attention')+'</nav>'
    return render(top+'<div class="hub-layout">'+rail(view,selected)+'<section class="hub-main">'+body+'</section></div>','Team' if title=='Team' else 'Team · '+title)

def context_panel(target,r=None,t=None):
    if t:
        c=s.channel(t['channel_id']);pid=c['project_id'];members=json.loads(c['members']);note=t['note'];version=t['version'];action='/team-hub/topics/'+target+'/context'
    else:
        pid=r['project_id'];members=[r['employee']];meta=s.state(target);note=meta['note'];version=meta['version'];action='';c=None
    body='<details class="hub-context"><summary>Working context · people, documents & decisions</summary><div><p><strong>Participants:</strong> '+E(', '.join(ux.NAMES[x] for x in members))+'</p>'
    if pid:
        body+='<p>'+a('/team/projects/'+pid if t or r['project_kind']=='team' else '/work/'+pid,'Open project')+'</p>'
        if t or r['project_kind']=='team':
            body+='<p>'+a('/project-briefs/'+pid,'Confirmed project interview')+' · '+a('/project-hub/'+pid,'Milestones & deliverables')+'</p>'
            for m in ms.listing(pid):body+='<p>'+a('/milestones/'+m['id'],m['title'])+' · '+E(m['state'].replace('_',' '))+'</p>'
    body+='<p><strong>Owner-confirmed discussion context</strong></p>'+rich(note or 'No additional context confirmed here.')
    if t:body+=form(action,hidden('version',version)+optional('Correct or confirm the working context','note',note,True),'Confirm context')
    else:body+='<p>'+a('#conversation-settings','Edit confirmed context in conversation settings')+'</p>'
    # This panel discloses selection; it does not imply all historical messages are in a model call.
    body+='<p class="muted">Replies use bounded recent history and scoped reference excerpts. A saved conversation or agent synthesis is not an approved fact or milestone deliverable.</p>'
    links=s.read('SELECT * FROM hub_links WHERE target=?',(target,))
    for l in links:
        item=storage.get(l['item_id']);status=storage.health(item)
        if item['version']!=l['item_version']:status='Changed version — review and relink'
        body+='<p>'+a('/storage/items/'+item['id'],item['title'])+' · linked v'+str(l['item_version'])+' · '+E(status)+'</p>'+form('/team-hub/documents/remove',hidden('target',target)+hidden('item_id',item['id']),'Remove link')
    body+='<details><summary>Link a Storage document</summary><p>Only the exact approved current version accessible to every participant can be used.</p>'+form('/team-hub/documents/link',hidden('target',target)+select('Storage item','item_id',[(x['id'],x['title']+' · '+x['status']) for x in storage.rows()]),'Link reviewed version')+'</details>'
    body+='<details><summary>Upload a document to Storage</summary><p>Upload creates a draft with project tags. Review and approve its access in Storage, then link it here.</p><form enctype="multipart/form-data" method="post" action="/team-hub/documents/upload">'+hidden('target',target)+'<label>Document<input type="file" name="file" required></label><button>Upload draft</button></form></details>'
    # Actual saved context from the latest reply is inspectable and tied to that exact request.
    if t:traces=s.read('SELECT d.id,d.context_json FROM dialogue_turns d JOIN hub_steps s ON s.turn_id=d.id JOIN hub_rounds r ON r.id=s.round_id WHERE r.topic_id=? AND d.status=\'done\' ORDER BY d.finished_at DESC LIMIT 1',(target,))
    else:traces=s.read("SELECT id,context_json FROM dialogue_turns WHERE thread_id=? AND status='done' ORDER BY ordinal DESC LIMIT 1",(target,))
    if traces:
        data=json.loads(traces[0]['context_json'] or '{}')
        visible={k:data[k] for k in ('history_turn_ids','history_chars','hub_context_visible','context_summary_ids') if k in data}
        body+='<details><summary>Context recorded for the latest completed reply</summary><pre>'+E(json.dumps(visible,indent=2,ensure_ascii=False))+'</pre></details>'
    return body+'</div></details>'

def list_rooms(q='',employee='',project_id='',archived=False,page=1,day_from='',day_to=''):
    values=s.rooms(q,employee,project_id,archived,page,day_from,day_to)
    body='<header class="hub-pane-head"><h2>'+('Conversation archive' if archived else 'Your conversations')+'</h2>'+a(href(view='new'),'New project channel','button secondary')+'</header><form class="hub-search" method="get" action="/team-hub">'+hidden('view','archive' if archived else 'messages')+optional('Search titles and message content','q',q)+select('Employee','employee',[('','All employees')]+list(ux.NAMES.items()),employee)+select('Project','project_id',[('','All projects')]+[(x['id'],x['title']) for x in team.projects()],project_id)+'<details><summary>Date filters (saved UTC dates)</summary><label>From<input type="date" name="day_from" value="'+E(day_from)+'"></label><label>To<input type="date" name="day_to" value="'+E(day_to)+'"></label></details><button>Search</button></form>'
    for r in values[:30]:
        sig=s.room_signature(r['id']);unread=bool(sig and sig!=r['seen']);snippet=''
        if q:
            hits=s.read("SELECT id,ordinal,user_text,reply FROM dialogue_turns WHERE thread_id=? AND (instr(lower(user_text),lower(?))>0 OR instr(lower(COALESCE(reply,'')),lower(?))>0) ORDER BY ordinal DESC LIMIT 1",(r['id'],q,q))
            if hits:
                hit=hits[0];text=hit['user_text'] if q.casefold() in hit['user_text'].casefold() else hit['reply'];i=text.casefold().find(q.casefold());snippet=text[max(0,i-50):i+180];url='/team-room/'+r['id']+'?before='+str(hit['ordinal']+1)+'#turn-'+hit['id']
            else:url='/team-room/'+r['id']
        else:url='/team-room/'+r['id']
        project=ux.project(r['project_kind'],r['project_id'])['title'] if r['project_id'] else 'Direct conversation'
        body+='<article class="hub-conversation">'+portrait(r['employee'])+'<div>'+a(url,r['title'])+'<small>'+E(ux.NAMES[r['employee']]+' · '+project)+'</small>'+('<p>'+E(snippet)+'</p>' if snippet else '')+'</div>'+('<span class="hub-unread">New activity</span>' if unread else '')+('<span class="badge">Pinned</span>' if r['pinned'] else '')+'</article>'
    if not values:body+='<div class="hub-empty"><h3>No conversations in this view</h3><p>Choose an employee on the left to open their primary direct chat, or start a project channel.</p></div>'
    found_topics=s.topic_search(q,employee,project_id,archived,day_from,day_to,page)
    if found_topics:body+='<h3 class="hub-results-label">Project discussion threads</h3>'
    for t in found_topics[:30]:
        url=href(topic=t['id']);snippet=''
        if q:
            hits=s.read("SELECT r.id,r.message,r.created_at,s.turn_id,d.reply FROM hub_rounds r LEFT JOIN hub_steps s ON s.round_id=r.id LEFT JOIN dialogue_turns d ON d.id=s.turn_id WHERE r.topic_id=? AND (instr(lower(r.message),lower(?))>0 OR instr(lower(COALESCE(d.reply,'')),lower(?))>0) ORDER BY r.created_at DESC,r.id DESC,s.ordinal DESC LIMIT 1",(t['id'],q,q))
            if hits:
                h=hits[0];n=s.one('SELECT COUNT(*) AS n FROM hub_rounds WHERE topic_id=? AND (created_at>? OR (created_at=? AND id>?))',(t['id'],h['created_at'],h['created_at'],h['id']))['n'];anchor='message-'+h['id'] if q.casefold() in h['message'].casefold() else 'turn-'+h['turn_id'];url=href(topic=t['id'],page=n//30+1)+'#'+anchor;snippet=(h['message'] if anchor.startswith('message-') else h['reply'])[:200]
        body+='<article class="hub-conversation"><div>'+a(url,t['title'])+'<small># '+E(t['channel_title'])+'</small>'+('<p>'+E(snippet)+'</p>' if snippet else '')+'</div></article>'

    if archived:
        for c in s.read('SELECT * FROM hub_channels WHERE archived=1 ORDER BY title'):body+='<p>'+a(href(channel=c['id']),'Archived channel: '+c['title'])+'</p>'
    params=dict(view='archive' if archived else 'messages',q=q,employee=employee,project_id=project_id,day_from=day_from,day_to=day_to)
    if page>1:body+=a(href(**params,page=page-1),'Previous page')
    if len(values)>30 or len(found_topics)>30:body+=a(href(**params,page=page+1),'Next page')
    body+='<details class="hub-secondary"><summary>Start a separate conversation / earlier histories</summary>'+old.room_form(employee if employee else 'twin')+'<p>'+a('/talk','Earlier department conversations')+'</p></details>'
    return layout(body,'archive' if archived else 'messages')

def thread_actions(ident,turn):
    if turn['status']!='done':return ''
    return '<details class="hub-reply-thread"><summary>Reply in a separate thread</summary>'+form('/team-hub/rooms/'+ident+'/thread',hidden('turn_id',turn['id'])+field('Thread title','title','Follow-up discussion'),'Open reply thread')+'</details>'

def room_page(ident,before=0):
    from superhuman.teamspace.views import room as old_room
    from superhuman.workspace.web import _v134_show_room
    r=ux.room(ident)
    if not r:raise ValueError('Conversation not found')
    fragment=parse(capture(old_room,ident,before,_v134_show_room));chat=next(n for n in fragment.find('div') if n.has_class('ux-chat'))
    # Accurate return label and current project filter.
    for link in chat.find('a'):
        if link.text()=='All conversations':link.set('href',href(project_id=r['project_id']) if r['project_id'] else href(employee=r['employee']));link.replace_text('Project conversations' if r['project_id'] else 'Employee conversations')
    st=s.state(ident);thread=d.get(ident)
    body='<div class="hub-room-tools">'+a('/team-hub','← Team')+form('/team-hub/rooms/'+ident+'/read',hidden('signature',s.room_signature(ident)),'Mark read')+'</div>'
    if r['project_id']:body+='<details class="hub-secondary"><summary>New conversation in this project</summary>'+old.room_form(r['employee'],r['project_kind'],r['project_id'])+'</details>'
    if st['archived']:
        body+='<p class="error">Archived conversation. <a href="#conversation-settings">Restore this conversation</a> before sending.</p>'
        for f in chat.find('form'):
            if f.attrs.get('action')=='/team-room/'+ident+'/send':
                for control in f.find():
                    if control.tag in ('input','textarea','select','button') and control.attrs.get('type')!='hidden':control.set('disabled',None)
                for b in f.find('button'):
                    if b.attrs.get('type')!='button':b.replace_text('Restore conversation to send')
    pending=s.read("SELECT COUNT(*) AS n FROM dialogue_suggestions WHERE thread_id=? AND status='proposed'",(ident,))[0]['n']
    for node in chat.find('summary'):
        if node.text()=='Suggested work & reviewed actions':node.replace_text('Suggested work & reviewed actions · '+str(pending)+' pending')
    body+=chat.html()+context_panel(ident,r=r)
    body+='<details id="conversation-settings" class="hub-context"><summary>Conversation settings · title, archive, pin & confirmed context</summary>'+form('/team-hub/rooms/'+ident+'/settings',hidden('version',st['version'])+field('Title','title',thread['title'])+optional('Confirmed working context','note',st['note'],True)+'<label><input type="checkbox" name="archived" value="true"'+(' checked' if st['archived'] else '')+'>Archive</label><label><input type="checkbox" name="pinned" value="true"'+(' checked' if st['pinned'] else '')+'>Pin</label>','Save conversation')+'</details>'
    parents=s.read('SELECT * FROM hub_dm_threads WHERE room_id=?',(ident,))
    if parents:body+='<p>'+a('/team-room/'+parents[0]['parent_id']+'#turn-'+parents[0]['turn_id'],'← Original message and conversation')+'</p>'
    children=s.read('SELECT t.*,d.title FROM hub_dm_threads t JOIN dialogue_threads d ON d.id=t.room_id WHERE t.parent_id=? ORDER BY t.created_at',(ident,))
    if children:body+='<section class="hub-work"><h3>Reply threads</h3>'+''.join('<p>'+a('/team-room/'+x['room_id'],x['title'])+'</p>' for x in children)+'</section>'
    cs=s.read('SELECT * FROM hub_cards WHERE room_id=? ORDER BY created_at DESC',(ident,))
    if cs:body+='<section class="hub-work"><h3>Linked work cards</h3>'+''.join('<p>'+a('/team-hub/cards/'+c['id'],c['title'])+' · '+E(c['status'].replace('_',' '))+'</p>' for c in cs)+'</section>'
    return layout(body,selected='',title=thread['title'])

def channel_page(ident):
    c=s.channel(ident);parent=team.project(c['project_id']);topics=s.read('SELECT * FROM hub_topics WHERE channel_id=? ORDER BY created_at DESC',(ident,));cfg=ms.managed(parent['id']);body='<header class="hub-pane-head"><div><p class="eyebrow">Project channel</p><h2># '+E(c['title'])+'</h2><p>'+E(ux.NAMES[cfg['lead']] if cfg else 'Department lead')+' leads · The Twin supervises</p></div>'+a('/team/projects/'+parent['id'],'Open project','button secondary')+'</header>'
    try:s.channel_members(c)
    except ValueError as exc:body+='<p class="error">'+E(str(exc))+'</p>'
    count=channel_count(ident);body+=form('/team-hub/channels/'+ident+'/read',hidden('count',count),'Mark current replies read')
    body+='<section class="hub-topic-list">'
    for t in topics:
        latest=s.read('SELECT status FROM hub_rounds WHERE topic_id=? ORDER BY created_at DESC LIMIT 1',(t['id'],));body+='<article>'+a(href(topic=t['id']),t['title'])+'<small>'+E(latest[0]['status'] if latest else 'No messages yet')+'</small></article>'
    if not topics:body+='<p class="hub-empty">Start a milestone thread or a focused project discussion.</p>'
    body+='</section><details open class="hub-new-topic"><summary>Start a discussion thread</summary>'+form('/team-hub/topics',hidden('channel_id',ident)+field('Topic','title')+select('Related milestone (optional)','milestone_id',[('','General project discussion')]+[(m['id'],m['title']) for m in ms.listing(parent['id'])]),'Create thread')+'</details>'
    body+='<details class="hub-context"><summary>Channel members & controls</summary>'+form('/team-hub/channels/'+ident+'/settings',hidden('version',c['version'])+field('Title','title',c['title'])+''.join('<label><input type="checkbox" name="members" value="'+e+'"'+(' checked' if e in json.loads(c['members']) else '')+'> '+E(ux.NAMES[e])+'</label>' for e in ms.roster(parent['id']))+field('Channel reply allowance (attempts, up to 500)','maximum',c['max_calls'])+'<label><input type="checkbox" name="delegated" value="true"'+(' checked' if c['delegated'] else '')+'>Allow The Twin to review routine internal work proposals in this channel. Existing project, milestone, privacy, budget and tool controls still apply. Strategic work returns to me.</label>'+'<label><input type="checkbox" name="archived" value="true"'+(' checked' if c['archived'] else '')+'>Archive channel</label><label><input type="checkbox" name="pinned" value="true"'+(' checked' if c['pinned'] else '')+'>Pin channel</label>','Save channel')+'</details>'+project_activity(parent['id'])
    return layout(body,selected=ident,title=c['title'])

def project_activity(pid):
    req,tasks=s.events(pid);body='<details class="hub-context"><summary>Recorded project work · assignments, handoffs & decisions</summary>'
    for t in tasks:body+='<p>'+a('/team/tasks/'+t['id'],t['title'])+' · '+E(ux.NAMES[t['owner']]+' · '+t['state'].replace('_',' '))+'</p>'
    for r in req:body+='<article class="hub-event"><strong>'+E(ux.NAMES.get(r['owner'],r['owner'])+' → '+ux.NAMES.get(r['recipient'],r['recipient'] or 'The Twin'))+'</strong><p>'+a('/team/requests/'+r['id'],r['title'])+' · '+E(r['kind']+' · '+r['status'])+'</p>'+('<p>Saved response: '+E(r['response'])+'</p>' if r['response'] else '')+'</article>'
    reviews=s.read('SELECT r.*,m.title FROM milestone_reviews r JOIN milestones m ON m.id=r.milestone_id WHERE m.project_id=? ORDER BY r.created_at DESC LIMIT 100',(pid,))
    for review in reviews:body+='<article class="hub-event"><strong>'+E(ux.NAMES.get(review['actor'],review['actor'])+' · '+review['decision'].replace('_',' '))+'</strong><p>'+a('/milestones/'+review['milestone_id'],review['title'])+'</p>'+rich(review['note'])+'<small>'+E(old.stamp(review['created_at']))+'</small></article>'
    if not req and not tasks and not reviews:body+='<p>No saved project work events yet.</p>'
    return body+'</details>'

def topic_page(ident,page=1):
    if not 1<=page<=10000:raise ValueError('Invalid discussion page')
    t=s.topic(ident);c=s.channel(t['channel_id']);members=json.loads(c['members']);rounds=s.read('SELECT * FROM hub_rounds WHERE topic_id=? ORDER BY created_at DESC,id DESC LIMIT 31 OFFSET ?',(ident,(page-1)*30));has_older=len(rounds)>30;rounds=list(reversed(rounds[:30]));pending=bool(s.read("SELECT 1 FROM hub_rounds WHERE topic_id=? AND status IN ('queued','working') LIMIT 1",(ident,)))
    from .readiness import discussion
    ready=discussion(c['id'])
    blocked=not ready['ready']
    explanation=' '.join(ready['issues'])
    body='<header class="hub-pane-head"><div>'+a(href(channel=c['id']),'← # '+c['title'])+'<h2>'+E(t['title'])+'</h2><p>'+E(', '.join(ux.NAMES[e] for e in members))+'</p></div></header><div class="hub-channel-transcript" data-channel-topic="'+ident+'" data-history="'+str(page)+'">'
    for r in rounds:
        body+='<article class="hub-message hub-owner" id="message-'+r['id']+'"><strong>You</strong><small>'+E(old.stamp(r['created_at']))+'</small>'+rich(r['message'])+'</article>'
        for step in s.steps(r['id']):
            body+='<article class="hub-message" id="turn-'+step['turn_id']+'">'+portrait(step['employee'])+'<div><strong>'+E(ux.NAMES[step['employee']])+'</strong><small>'+E(step['stage'].replace('_',' ')+' · '+step['status'])+'</small>'+rich(step['reply'] or step['error'] or 'Reply queued for the shared worker.')+a('/team-room/'+step['thread_id']+'#turn-'+step['turn_id'],'Open saved reply & controls')+'</div></article>'
        body+='<div class="hub-round-status" role="status">'+E(('Waiting for activation / controls · '+explanation if r['status']=='queued' and blocked else r['status'].replace('_',' '))+(' · '+r['error'] if r['error'] else ''))+'</div>'
        if r['status'] in ('queued','working'):body+=form('/team-hub/rounds/'+r['id']+'/cancel','','Cancel queued discussion')
        elif r['status'] in ('failed','cancelled'):
            if blocked:body+='<p>Retry unavailable until the discussion controls below are ready.</p>'
            else:body+=form('/team-hub/rounds/'+r['id']+'/retry',hidden('submission_key',uuid4().hex), 'Request a fresh attempt (may incur cost)')
    body+='</div>'+ (a(href(topic=ident,page=page+1),'Older messages') if has_older else '')+(' · '+a(href(topic=ident,page=page-1),'Newer messages') if page>1 else '')
    body+='<div id="discussion-readiness" role="status"><strong>'+('AI replies blocked' if blocked else 'Ready to request AI replies')+'</strong><p>'+E(explanation if blocked else 'The shared worker will process this request. Request-specific dollar limits are checked again before each paid call.')+'</p><p>'+a('/project-hub/'+c['project_id']+'?view=manage','Project controls')+' · '+a('/team/budget','Budget')+' · '+a('/system-baseline','Team readiness')+'</p></div>'
    body+='<form class="hub-composer" aria-describedby="discussion-readiness" data-voice data-hub-draft="'+ident+'" method="post" action="/team-hub/topics/'+ident+'/send">'+hidden('submission_key',uuid4().hex)+select('Who should respond?','target',[('team','Team discussion · lead coordinates')]+[(e,ux.NAMES[e]+' · directed question') for e in members])+'<label>Message<textarea name="message" maxlength="6000" required placeholder="Discuss this milestone, ask a question, or request a work proposal…"></textarea></label><button'+(' disabled' if pending or blocked else '')+'>Send message</button><small>Send requests AI replies; it is not a note-only save. A directed reply uses one attempt; a team discussion uses up to four. Monthly dollar limits still apply. Messages do not grant external authority.</small></form>'
    if pending:body+='<p class="hub-refresh">'+('Replies are waiting for activation or controls. ' if blocked else 'Replies are queued or running. ')+a(href(topic=ident),'Refresh saved discussion')+'</p>'
    proposals=s.read('SELECT * FROM hub_cards WHERE topic_id=? ORDER BY created_at DESC',(ident,));body+='<section class="hub-work"><h3>Suggested & authorized work · '+str(sum(x['status'] in ('proposed','revision','owner_review') for x in proposals))+' pending</h3>'
    for card in proposals:body+='<p>'+a('/team-hub/cards/'+card['id'],card['title'])+' · '+E(card['status'].replace('_',' '))+'</p>'
    body+='</section>'+context_panel(ident,t=t)+project_activity(c['project_id'])
    return layout(body,selected=c['id'],title=t['title'])

def employee_page(ident=''):
    if not ident:
        body='<header class="hub-pane-head"><div><h2>Your employees</h2><p>Saved workload and worker availability. Refresh to verify the latest state.</p></div></header><div class="hub-employee-grid">'
        for item in ux.board():
            tasks=[t for t in team.tasks() if t['owner']==item['id'] and t['state'] not in ('completed','cancelled')]
            label='Output awaiting review' if item['state']=='reviewing' else 'Worker unavailable' if not item['online'] else item['state'].capitalize()
            body+='<article class="hub-employee-card"><div>'+portrait(item['id'])+'<span class="badge">'+E(label)+'</span></div><h3>'+E(item['name'])+'</h3><small>'+E(item['role'])+'</small><p>'+E(item['task']['title'] if item['task'] else item['assignment'] or 'No active assignment recorded')+'</p><small>'+E(str(len(tasks))+' open assignments · '+item['reason'])+'</small><p>'+a(href(view='employees',employee=item['id']),'Workload & profile')+'</p>'+form('/team-hub/direct/'+item['id'],'','Open conversation')+'</article>'
        return layout(body+'</div>','employees')
    if ident not in ux.NAMES:raise ValueError('Choose an employee')
    e=next(x for x in team.employees() if x['id']==ident);item=next(x for x in ux.board() if x['id']==ident)
    body='<header class="hub-profile">'+portrait(ident)+'<div><h2>'+E(ux.NAMES[ident])+'</h2><p>'+E(ux.ROLES[ident])+'</p>'+form('/team-hub/direct/'+ident,'','Open direct conversation')+'</div></header><p>'+E(e['charter'])+'</p><p><strong>Worker:</strong> '+('Connected (heartbeat observed)' if item['online'] else 'Heartbeat not verified')+'</p><p><strong>Saved work state:</strong> '+E('Output awaiting review' if item['state']=='reviewing' else item['state'])+' · '+E(item['reason'])+'</p><p>'+E(__import__('superhuman.trust',fromlist=['employee_status']).employee_status(e))+'</p><h3>Workload</h3>'
    for t in team.tasks():
        if t['owner']!=ident:continue
        who=' · awaiting The Twin or owner review' if t['state']=='awaiting_review' else ''
        ass=ms.assignment(t['id'])
        if ass and t['state']=='awaiting_review':who=' · awaiting '+('milestone packet review' if ass['role']=='lead' else ux.NAMES[ms.managed(t['project_id'])['lead']]+' review')
        body+='<article class="hub-conversation"><div>'+a('/team/tasks/'+t['id'],t['title'])+'<small>'+E(t['state'].replace('_',' ')+who)+'</small></div>'+a('/team/projects/'+t['project_id'],'Project')+'</article>'
    body+='<details class="hub-context"><summary>Profile, writing skill, memory & management</summary><p>'+a('/team/employees/'+ident,'Open employee permissions, writing skill and confirmed memory')+' · '+a('/agent-personalities/'+ident,'Personality')+'</p></details>'
    if ident=='twin':body+='<p>'+a(href(view='twin'),'Priorities, preferences and communications')+'</p>'
    return layout(body,'employees',title=ux.NAMES[ident])

def new_channel(pid=''):
    choices=[x for x in team.projects() if ms.managed(x['id']) and ms.managed(x['id'])['share_outputs']]
    body='<header class="hub-pane-head"><h2>Start a project channel</h2></header><p>Choose an existing project with a department lead and approved team-sharing. The channel uses the same roster and approval boundaries.</p><form method="get" action="/team-hub">'+hidden('view','new')+select('Project','project_id',[(x['id'],x['title']) for x in choices],pid)+'<button>Choose project</button></form>'
    if pid:
        parent=team.project(pid);cfg=ms.managed(pid)
        if not cfg or not cfg['share_outputs']:raise ValueError('Approve project-team sharing first')
        body+=form('/team-hub/channels',hidden('project_id',pid)+field('Channel title','title',parent['title'])+'<fieldset><legend>Confirm the people who can use this shared discussion</legend>'+''.join('<label><input type="checkbox" name="members" value="'+e+'" checked> '+E(ux.NAMES[e])+(' · project lead' if e==cfg['lead'] else '')+'</label>' for e in ms.roster(pid))+'</fieldset>','Create project channel')
    if not choices:body+='<p>'+a('/project-leadership','Set up project leadership and sharing')+'</p>'
    return layout(body)

def card_page(ident):
    card=cards.get(ident);parent=team.project(card['project_id']);source=s.one('SELECT kind FROM dialogue_suggestions WHERE id=?',(card['suggestion_id'],));body='<header class="hub-pane-head"><div><p class="eyebrow">Governed work card</p><h2>'+E(card['title'])+'</h2></div><span class="badge">'+E(card['status'].replace('_',' '))+'</span></header><p>'+a('/team/projects/'+parent['id'],parent['title'])+' · '+E(ux.NAMES[card['owner']])+'</p>'+rich(card['instruction'])+'<h3>Acceptance criteria</h3>'+rich(card['criteria'])+'<p>'+E(card['risk']+' · '+card['sensitivity']+' · '+source['kind'])+'</p>'+('<p class="ui-notice">'+E(card['decision'])+'</p>' if card['decision'] else '')
    if card['task_id']:
        task=team.task(card['task_id']);from superhuman.team.work import gate
        good,why=gate(task);body+='<h3>Actual work status: '+E(task['state'].replace('_',' '))+'</h3><p>'+E(why or 'Existing worker, tool, budget and review controls apply.')+'</p>'+a('/team/tasks/'+task['id'],'Open assignment & deliverable','button')
    elif card['status']!='twin_review':
        workers=ms.roster(parent['id']) if ms.managed(parent['id']) else [parent['scope']]
        body+=form('/team-hub/cards/'+ident+'/review',hidden('version',card['version']),'Ask The Twin to review routine work')
        body+='<details class="hub-context"><summary>Review or edit work details</summary>'+form('/team-hub/cards/'+ident+'/edit',hidden('version',card['version'])+field('Title','title',card['title'])+field('Instructions','instruction',card['instruction'],True).replace('maxlength="6000"','maxlength="5000"')+field('Acceptance criteria','criteria',card['criteria'],True).replace('maxlength="6000"','maxlength="1500"')+select('Employee','owner',[(e,ux.NAMES[e]) for e in workers if e!='twin'],card['owner'])+'<label>Due date<input type="date" name="due" value="'+E(card['due'])+'"></label>'+select('Risk','risk',[(x,x) for x in team.RISKS],card['risk'])+select('Sensitivity','sensitivity',[(x,x) for x in team.SENSITIVITIES],card['sensitivity'])+select('Milestone','milestone_id',[('','No milestone')]+[(m['id'],m['title']) for m in ms.listing(parent['id'])],card['milestone_id'])+'<label><input type="checkbox" name="share_confirmed" value="true"> Reviewed instructions contain no private content if using Public or Internal.</label>','Save reviewed details')+'</details>'+form('/team-hub/cards/'+ident+'/authorize',hidden('version',card['version'])+field('Reason / approval note','note')+'<p>This authorizes this exact saved task within existing permissions. It does not authorize external sending or approve its future output.</p>','Authorize this work')
    else:body+='<p role="status">The Twin’s independent review is queued or running. Refresh to see its saved decision.</p>'
    body+='<p>'+a(href(topic=card['topic_id']) if card['topic_id'] else '/team-room/'+card['room_id'],'Back to discussion')+'</p>'
    return layout(body,title=card['title'])

def install(app):
    # Preserve old list bookmarks; active rooms share the new workspace and original POST handlers.
    app.router.routes[:]=[r for r in app.router.routes if not(getattr(r,'path','')=='/team-room/{ident}' and 'GET' in (getattr(r,'methods',set()) or set()))]
    @app.get('/team-room/{ident}')
    def existing_room(ident:str,before:int=0):
        if not ux.room(ident):raise HTTPException(404,'Conversation not found')
        try:return room_page(ident,before)
        except ValueError as exc:fail(exc)
    @app.get('/assets/teamhub.css')
    def css():return FileResponse(ASSETS/'teamhub.css',media_type='text/css')
    @app.get('/assets/teamhub.js')
    def js():return FileResponse(ASSETS/'teamhub.js',media_type='application/javascript')
    @app.get('/team-hub')
    def home(view:str='messages',employee:str='',project_id:str='',q:str='',page:int=1,day_from:str='',day_to:str='',channel:str='',topic:str=''):
        try:
            s.initialize()
            if topic:return topic_page(topic,page)
            if channel:return channel_page(channel)
            if view in ('messages','archive'):return list_rooms(q,employee,project_id,view=='archive',page,day_from,day_to)
            if view=='employees':return employee_page(employee)
            if view=='new':return new_channel(project_id)
            if view=='attention':
                items=attention();body='<header class="hub-pane-head"><h2>Needs your attention · '+str(len(items))+'</h2></header>'
                for x in items:body+='<article class="hub-conversation"><div><small>'+E(x['kind'])+'</small>'+a(x['url'],x['title'])+'<p>'+E(x['detail'])+'</p></div></article>'
                return layout(body+('' if items else '<p class="hub-empty">No saved decisions or questions need you here.</p>'),'attention')
            if view=='activity':
                body='<h2>Recorded team activity</h2><p>Saved actions and decisions, with links to their original work. These are execution records, not invented conversations.</p>'
                from superhuman.workspace.web import feed
                body+=capture(feed,page);return layout(body,'activity')
            if view=='twin':
                from superhuman.workspace.web import twin
                return layout('<h2>The Twin · priorities, preferences & briefings</h2>'+form('/team-hub/direct/twin','','Open primary Twin conversation')+'<p>'+a('/twin?tab=updates','Update priorities, instructions or temporary constraints')+' · '+a('/team/memory','Confirm lasting preferences')+' · '+a('/twin?tab=communications','Briefings & communications')+' · '+a('/assistant/connections','Connections & consent')+'</p>'+capture(twin,'updates',1),'messages')
            raise ValueError('Choose an available Team view')
        except ValueError as exc:fail(exc)
    @app.post('/team-hub/direct/{employee}')
    def direct(employee:str):
        try:return redirect('/team-room/'+s.primary(employee))
        except ValueError as exc:fail(exc)
    @app.post('/team-hub/rooms/{ident}/thread')
    def dm_thread(ident:str,turn_id:str=Form(...),title:str=Form(...)):
        try:return redirect('/team-room/'+s.reply_thread(ident,turn_id,title))
        except ValueError as exc:fail(exc)
    @app.post('/team-hub/rooms/{ident}/settings')
    def settings(ident:str,version:int=Form(...),title:str=Form(...),note:str=Form(''),archived:bool=Form(False),pinned:bool=Form(False)):
        try:s.room_control(ident,version,title,archived,pinned,note);return redirect('/team-room/'+ident)
        except ValueError as exc:fail(exc)
    @app.post('/team-hub/rooms/{ident}/read')
    def read_room(ident:str,signature:str=Form('')):
        try:s.mark_room(ident,signature);return redirect('/team-room/'+ident)
        except ValueError as exc:fail(exc)
    @app.post('/team-hub/channels')
    def create(project_id:str=Form(...),title:str=Form(...),members:list[str]=Form([])):
        try:return redirect(href(channel=s.create_channel(project_id,title,members)))
        except ValueError as exc:fail(exc)
    @app.post('/team-hub/channels/{ident}/settings')
    def channel_settings(ident:str,version:int=Form(...),title:str=Form(...),members:list[str]=Form([]),archived:bool=Form(False),pinned:bool=Form(False),maximum:int=Form(...),delegated:bool=Form(False)):
        try:s.channel_control(ident,version,title,members,archived,pinned,maximum,delegated=delegated);return redirect(href(channel=ident))
        except ValueError as exc:fail(exc)
    @app.post('/team-hub/channels/{ident}/read')
    def channel_read(ident:str,count:int=Form(...)):
        try:
            if count!=channel_count(ident):raise ValueError('New replies arrived; review before marking read')
            with p.connect() as db:db.execute('UPDATE hub_channels SET seen=? WHERE id=?',(count,ident))
            return redirect(href(channel=ident))
        except ValueError as exc:fail(exc)
    @app.post('/team-hub/topics')
    def topic_create(channel_id:str=Form(...),title:str=Form(...),milestone_id:str=Form('')):
        try:return redirect(href(topic=s.create_topic(channel_id,title,milestone_id)))
        except ValueError as exc:fail(exc)
    @app.post('/team-hub/topics/{ident}/send')
    def topic_send(ident:str,message:str=Form(...),target:str=Form(...),submission_key:str=Form(...)):
        try:s.send(ident,message,'team' if target=='team' else 'direct','' if target=='team' else target,submission_key);return redirect(href(topic=ident))
        except ValueError as exc:
            response=layout('<h2>AI reply request not queued</h2><p role="alert">'+E(str(exc))+'</p><p>'+a(href(topic=ident),'Return to the discussion')+'</p><p>Review the controls, then submit again. Your browser keeps the unsent draft in this session.</p>',title='Discussion needs attention')
            response.status_code=409
            return response
    @app.post('/team-hub/topics/{ident}/context')
    def note(ident:str,version:int=Form(...),note:str=Form('')):
        try:s.save_note(ident,version,note);return redirect(href(topic=ident))
        except ValueError as exc:fail(exc)
    @app.post('/team-hub/rounds/{ident}/cancel')
    def cancel(ident:str):
        try:s.cancel(ident);return redirect(href(topic=s.round_(ident)['topic_id']))
        except ValueError as exc:fail(exc)
    @app.post('/team-hub/rounds/{ident}/retry')
    def retry(ident:str,submission_key:str=Form(...)):
        try:
            r=s.round_(ident)
            if r['status'] not in ('failed','cancelled'):raise ValueError('Only a stopped discussion may be retried')
            s.send(r['topic_id'],r['message'],r['mode'],r['target'],submission_key);return redirect(href(topic=r['topic_id']))
        except ValueError as exc:fail(exc)
    @app.post('/team-hub/documents/link')
    def document_link(target:str=Form(...),item_id:str=Form(...)):
        try:s.link_file(target,item_id);return redirect(href(topic=target) if s.read('SELECT id FROM hub_topics WHERE id=?',(target,)) else '/team-room/'+target)
        except ValueError as exc:fail(exc)
    @app.post('/team-hub/documents/remove')
    def document_remove(target:str=Form(...),item_id:str=Form(...)):
        with p.connect() as db:db.execute('DELETE FROM hub_links WHERE target=? AND item_id=?',(target,item_id))
        return redirect(href(topic=target) if s.read('SELECT id FROM hub_topics WHERE id=?',(target,)) else '/team-room/'+target)
    @app.post('/team-hub/documents/upload')
    async def upload(target:str=Form(...),file:UploadFile=File(...)):
        from superhuman.capabilities import local
        try:
            topics=s.read('SELECT * FROM hub_topics WHERE id=?',(target,));c=s.channel(topics[0]['channel_id']) if topics else None;r=None if c else ux.room(target)
            if not c and not r:raise ValueError('Conversation not found')
            pid=c['project_id'] if c else r['project_id'];kind='team' if c else r['project_kind'];scope=team.project(pid)['scope'] if c else ux.project(kind,pid)['scope'] if pid else ('endorsement' if r['employee']=='twin' else r['employee'])
            sensitivity=max(('confidential',ux.project(kind,pid).get('sensitivity','internal') if pid else 'internal'),key=team.SENSITIVITIES.index)
            saved=local.store_bytes(scope,file.filename or '',await file.read(local.MAX_BYTES+1))
            ident=storage.save(scope,'document',saved['filename'],filename=saved['filename'],project_kind=kind,project_id=pid,tags='conversation,'+('project' if pid else 'direct'),sensitivity=sensitivity,access=(),source='Owner upload from Team conversation',status='draft')
            return redirect('/storage/items/'+ident)
        except (ValueError,OSError) as exc:fail(exc)
        finally:await file.close()
    @app.get('/team-hub/cards/{ident}')
    def show_card(ident:str):
        try:return card_page(ident)
        except ValueError as exc:fail(exc)
    @app.post('/team-hub/cards/{ident}/edit')
    def edit_card(ident:str,version:int=Form(...),title:str=Form(...),instruction:str=Form(...),criteria:str=Form(...),owner:str=Form(...),due:str=Form(''),risk:str=Form(...),sensitivity:str=Form(...),milestone_id:str=Form(''),share_confirmed:bool=Form(False)):
        try:cards.edit(ident,version,title,instruction,criteria,owner,due,risk,sensitivity,milestone_id,share_confirmed);return redirect('/team-hub/cards/'+ident)
        except ValueError as exc:fail(exc)
    @app.post('/team-hub/cards/{ident}/review')
    def review_card(ident:str,version:int=Form(...)):
        try:cards.request_review(ident,version);return redirect('/team-hub/cards/'+ident)
        except ValueError as exc:fail(exc)
    @app.post('/team-hub/cards/{ident}/authorize')
    def authorize(ident:str,version:int=Form(...),note:str=Form(...)):
        try:cards.authorize(ident,version,note);return redirect('/team-hub/cards/'+ident)
        except ValueError as exc:fail(exc)
