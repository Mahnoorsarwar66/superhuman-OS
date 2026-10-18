"""Shared vocabulary and presentation. No user content or submitted values are rewritten."""
from contextvars import ContextVar
from urllib.parse import parse_qs
import re
from .tree import parse,Node,text
capturing=ContextVar('interface_capture',default=False)
STATE={'pass':('Pass','success'),'revise':('Needs revision','warning'),'fail':('Fail','danger'),'planned':('Ready to plan','neutral'),'working':('In progress','info'),'lead review':('Lead review','info'),'specialist review':('Specialist review','info'),'twin review':('Twin review','info'),'owner review':('Needs your decision','warning'),'needs owner':('Needs your attention','warning'),'approved':('Approved','success'),'completed':('Complete','success'),'complete':('Complete','success'),'paused':('Paused','neutral'),'blocked':('Blocked','warning'),'failed':('Needs attention','danger'),'running':('Working','info'),'assigned':('Assigned','info'),'queued':('Queued','neutral'),'ready':('Ready','neutral'),'active':('In progress','info'),'ready to start':('Ready to start','neutral'),'needs review':('Needs review','warning'),'needs your decision':('Needs your decision','warning'),'needs your review':('Needs your review','warning'),'current':('Current','success')}

def tab(name,allowed,default):
    from superhuman.navigation.shell import request_query
    values=parse_qs(request_query.get()).get(name,[default])
    chosen=values[0]
    if chosen not in allowed:
        from fastapi import HTTPException
        raise HTTPException(400,'Choose one of the available workspace tabs')
    return chosen

def capture(fn,*args,**kwargs):
    token=capturing.set(True)
    try:
        response=fn(*args,**kwargs)
        if isinstance(response,str):return response
        return response.body.decode('utf-8')
    finally:capturing.reset(token)

def pill(state):
    from superhuman.navigation.shell import esc
    label,tone=STATE.get(str(state).replace('_',' ').lower(),(str(state).replace('_',' ').capitalize(),'neutral'))
    return '<span class="badge ui-status ui-'+tone+'">'+esc(label)+'</span>'

def polish(body,path):
    root=parse(body)
    # Only generated controls and status badges receive a vocabulary change.
    actions={
      '/register/confirm':'Confirm requirements',
      '/materials':'Approve source access',
      '/scope':'Save scope change',
      '/rubric':'Save review standard',
      '/reopen':'Reopen affected work'}
    for form in root.find('form'):
        action=form.attrs.get('action') or ''
        for suffix,label in actions.items():
            if action.endswith(suffix):
                buttons=form.find('button')
                if len(buttons)==1:buttons[0].replace_text(label)
        if action.endswith('/review') and '/evidence/' in action:
            for b in form.find('button'):b.replace_text('Save evidence review')
        if action.endswith('/submit') and action.startswith('/milestones/'):
            for b in form.find('button'):b.replace_text('Send deliverable for review')
        if action.endswith('/requirements'):
            for b in form.find('button'):b.replace_text('Add requirement')
        # Preserve name/value buttons, hidden tokens, evidence checkboxes and warnings.
        if form.attrs.get('method','get').lower()=='get' and len(form.find('label'))>3 and 'v129-filters' not in (form.attrs.get('class') or ''):form.set('class',(form.attrs.get('class') or '')+' ui-filters')
    for n in root.find():
        if n.has_class('badge') and len(n.children)==1 and isinstance(n.children[0],str):
            key=text(n).replace('_',' ').lower()
            if key in STATE:
                label,tone=STATE[key];n.replace_text(label);n.set('class','badge ui-status ui-'+tone)
    for anchor in root.find('a'):
        if re.fullmatch(r'/milestones/[a-f0-9]+/packet\.txt',anchor.attrs.get('href') or ''):anchor.replace_text('Download deliverable text')
    # Keep generated catalogue navigation in the shared location, once.
    if path.startswith('/storage'):
        for n in list(root.children):
            if isinstance(n,Node) and n.tag=='p':
                hrefs={a.attrs.get('href') for a in n.find('a')}
                if {'/storage','/storage/search','/documents','/research-desk','/memory'}<=hrefs:root.children.remove(n)
    return root.html()

def contextual(key):
    from superhuman.navigation import shell
    links={
      'overview':(),
      'projects':(('/projects','Projects'),('/project-tasks','All tasks'),('/suggested-work','Suggested work')),
      'team':(('/team-hub','Conversations'),('/team-hub?view=employees','Employees'),('/team-hub?view=activity','Activity')),
      'knowledge':(('/storage','Department files'),('/documents','Generated outputs'),('/research-desk','Research')),
      'settings':(('/settings','Manage workspace'),('/system-baseline','System health'),('/memory','Memory & writing')),
      'calendar':(),
    }
    if key not in links:return None
    values=links[key]
    if not values:return ''
    return '<nav class="shell-tabs" aria-label="Section navigation">'+''.join('<a href="'+shell.esc(url)+'"'+(' aria-current="page"' if shell.current_link(url) else '')+'>'+label+'</a>' for url,label in values)+'</nav>'

def department_tabs(body,path):
    from superhuman.navigation.shell import esc
    match=re.match(r'^/(?:departments|department-plans|supervision)/([a-z_]+)(?:/(.*))?$',path)
    if not match:return body
    scope,view=match.groups();root=parse(body)
    old=next((n for n in root.find('nav') if n.attrs.get('aria-label')=='Department navigation'),None)
    if not old and not path.startswith('/supervision/'):return body
    selected='work' if path.startswith('/department-plans/') or view=='projects' else 'agent' if path.startswith('/supervision/') or view in ('agent','supervision') else {'knowledge':'files','conversations':'conversations','activity':'activity'}.get(view,'summary')
    base='/departments/'+scope
    items=[('summary',base,'Summary'),('work',base+'/projects','Work & priorities'),('files',base+'/knowledge','Files & research'),('conversations',base+'/conversations','Conversations'),('agent',base+'/agent','Agent & supervision'),('activity',base+'/activity','Activity')]
    fresh=parse('<nav class="shell-tabs" aria-label="Department navigation">'+''.join('<a href="'+esc(url)+'"'+(' aria-current="page"' if key==selected else '')+'>'+esc(label)+'</a>' for key,url,label in items)+'</nav>').children[0]
    if old:
        old.raw=fresh.raw;old.attrs=fresh.attrs;old.children=fresh.children
    else:
        index=next((i for i,n in enumerate(root.children) if isinstance(n,Node) and n.tag=='h1'),-1)
        root.children.insert(index+1,fresh)
    return root.html()

BASE_STYLE='''
body{font:16px/1.6 Inter,"Segoe UI",ui-sans-serif,system-ui,-apple-system,sans-serif;color:#1e332d;background:#f6f8f7}h1{font-size:32px;line-height:1.25;letter-spacing:-.65px}h2{font-size:21px;line-height:1.4}h3{font-size:17px}button,input,select,textarea{font-family:inherit}a:focus-visible,button:focus-visible,input:focus-visible,textarea:focus-visible,summary:focus-visible{outline:3px solid #277caa;outline-offset:3px}
'''
ICONS={
'overview':'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
'projects':'M3 6h7l2 3h9v11H3z',
'departments':'M4 21V5h10v16 M14 10h6v11 M7 8h4 M7 12h4 M7 16h4 M3 21h18',
'team':'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M22 21v-2a4 4 0 0 0-3-3.8 M17 3.2a4 4 0 0 1 0 7.6',
'inbox':'M3 4h18v16H3z M3 13h5l2 3h4l2-3h5',
'calendar':'M4 5h16v16H4z M8 3v5 M16 3v5 M4 10h16',
'coding':'m8 6-6 6 6 6 m8-12 6 6-6 6 m-3-15-2 18',
'reviews':'M9 4h11v17H4V4h2 M8 2h8v4H8z m-1 8 3 3 6-6',
'knowledge':'M3 6h7l2 3h9v11H3z M7 13h10 M7 16h7',
'settings':'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2'}
def icon(key):return '<svg class="ui-nav-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="'+ICONS.get(key,ICONS['overview'])+'"></path></svg>'

def reflow(body,path):
    """Group generated navigation/tools while leaving source text and form values intact."""
    root=parse(body)
    if path.startswith('/departments/') or path.startswith('/department-plans/'):
        body=department_tabs(body,path);root=parse(body)
    if path=='/departments':
        for card in root.find('article'):
            if not card.has_class('department-card'):continue
            keep=[];extra=[]
            for child in card.children:
                if isinstance(child,Node) and (child.tag=='h2' or child.has_class('row') or child.has_class('department-metrics') or child.has_class('department-next') or child.tag=='a'):keep.append(child)
                else:extra.append(child)
            if extra:keep.insert(max(0,len(keep)-2),Node('details',[('class','ui-disclosure')],children=[Node('summary',children=['Status details']),Node('div',children=extra)]))
            card.children=keep
    if path=='/inboxes':
        for box in root.find('aside'):
            if box.has_class('ux-accounts'):box.children=[Node('details',[('class','ui-accounts'),('open',None)],children=[Node('summary',children=['Accounts & connection status']),Node('div',children=box.children)])]
        for box in root.find('section'):
            if box.has_class('ux-messages'):
                box.set('id','message-list')
                for a in box.find('a'):
                    href=a.attrs.get('href') or ''
                    if href.startswith('/inboxes?') and 'selected=' in href:a.set('href',href+'#message-detail')
            if box.has_class('ux-selected'):
                box.set('id','message-detail');box.set('aria-label','Selected message')
                box.children.insert(0,Node('p',[('class','ui-message-return')],children=[Node('a',[('href','#message-list')],children=['Back to messages'])]))
    if path=='/calendar':
        bars=[n for n in root.children if isinstance(n,Node) and n.tag=='nav']
        if len(bars)>=2:
            index=root.children.index(bars[0]);root.children=[n for n in root.children if n not in bars[:2]]
            root.children.insert(index,Node('div',[('class','ui-calendar-bar')],children=bars[:2]))
        for n in list(root.children):
            if isinstance(n,Node) and n.has_class('v129-calendar-tools'):
                index=root.children.index(n);root.children[index]=Node('details',[('class','ui-disclosure')],children=[Node('summary',children=['Find a meeting or go to a date']),n])
    if path.startswith('/twin'):
        for n in list(root.children):
            if isinstance(n,Node) and n.tag=='p' and n.has_class('muted') and text(n).startswith('Global Twin chats can use'):
                index=root.children.index(n);root.children[index]=Node('details',[('class','ui-disclosure')],children=[Node('summary',children=['How this conversation uses context']),n])
    return polish(root.html(),path)
