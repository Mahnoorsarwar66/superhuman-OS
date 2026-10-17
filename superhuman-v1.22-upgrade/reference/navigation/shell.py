"""One server-rendered shell. No scripts, remote assets or data mutations."""
from contextvars import ContextVar
import html
import re
from urllib.parse import quote

request_path = ContextVar('superhuman_navigation_path', default='/')
NAV = (('overview','/','Overview'),('talk','/talk','Talk'),('departments','/departments','Departments'),('projects','/projects','Projects'),
       ('inbox','/inboxes','Inbox'),('tasks','/tasks','Tasks'),('reviews','/reviews','Reviews'),
       ('knowledge','/knowledge','Knowledge'),('calendar','/calendar','Calendar'),('settings','/settings','Settings'))

def esc(value):
    return html.escape(str(value if value is not None else ''), quote=True)

def section(path):
    if path == '/' or path.startswith('/briefing'): return 'overview'
    if path.startswith('/workspace/projects/') or path.startswith(('/projects','/work/')): return 'projects'
    if path.startswith('/departments'): return 'departments'
    if path.startswith('/talk'): return 'talk'
    if path.startswith(('/inboxes','/mail')): return 'inbox'
    if path.startswith('/reviews'): return 'reviews'
    if path.startswith(('/tasks','/runtime','/queue','/coding')): return 'tasks'
    if path.startswith(('/knowledge','/research-desk','/research-review','/tools','/documents')): return 'knowledge'
    if path.startswith(('/calendar','/meetings')): return 'calendar'
    if path.startswith(('/settings','/memory')): return 'settings'
    return 'overview'

STYLE = '''
:root{--ink:#193c33;--muted:#61746c;--line:#dce4de;--paper:#fff;--green:#165b46}
*{box-sizing:border-box}body{margin:0;background:#f5f7f4;color:var(--ink);font:15px/1.65 system-ui,sans-serif}a{color:var(--green);text-underline-offset:3px}h1{font-size:clamp(27px,4vw,38px);line-height:1.2;letter-spacing:-1px;margin:10px 0 20px}h2{font-size:21px;line-height:1.35}h3{font-size:17px}p{margin:10px 0}.muted,small,.intro{color:var(--muted)}
.shell-sidebar{position:fixed;inset:0 auto 0 0;width:234px;background:#143c30;color:#eef6ef;padding:30px 18px;overflow:auto;z-index:10}.shell-brand{display:block;padding:0 14px 28px;color:white;text-decoration:none;font-size:25px;font-weight:750;letter-spacing:-1px}.shell-brand small{display:block;color:#b2c9ba;font-size:10px;letter-spacing:1.7px;font-weight:500}.shell-sidebar nav{display:grid;gap:5px;margin:0}.shell-sidebar nav a{display:block;padding:10px 14px;color:#c9dbcf;text-decoration:none;border-radius:9px;font-weight:550}.shell-sidebar nav a:hover{background:#234e3f}.shell-sidebar nav a[aria-current=page]{background:#e5efdf;color:#153e2e}.shell-menu>summary{display:none}.shell-sidebar footer{margin:26px 14px 0;padding-top:18px;border-top:1px solid #36594b;font-size:12px;color:#b4cabb}.shell-content{margin-left:234px}.shell-header{background:#fff;border-bottom:1px solid var(--line);min-height:76px;display:flex;align-items:center;justify-content:space-between;padding:16px 36px;gap:20px}.shell-header strong{font-size:15px}.shell-header span{font-size:12px;color:var(--muted)}.shell-header form{margin:0}.shell-header button{padding:7px 12px;font-size:13px;min-height:36px;background:#edf2eb;color:var(--ink)}.shell-main{max-width:1280px;padding:30px 36px 70px;margin:auto;min-width:0}.shell-skip{position:absolute;left:-10000px}.shell-skip:focus{left:250px;top:12px;z-index:20;background:white;padding:10px}.shell-tabs{display:flex;gap:8px;flex-wrap:wrap;border-bottom:1px solid var(--line);padding-bottom:12px;margin-bottom:24px}.shell-tabs a{padding:7px 12px;text-decoration:none;border-radius:7px}.shell-tabs a[aria-current=page]{background:#e7efdf;font-weight:650}.shell-context{font-size:12px;color:var(--muted);margin:0 0 10px}.shell-context a{color:inherit}.shell-grid,.grid,.project-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.card,.panel,.project-card,.empty{background:white;border:1px solid var(--line);border-radius:14px;padding:22px;margin:16px 0;min-width:0}.shell-grid>.card,.grid>.card{margin:0}.row,.stack,.lead-row,.section-head,.card-meta{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px}.stack{justify-content:flex-start}.stack form{margin:0}label{display:block;margin:14px 0}input,select,textarea{display:block;width:100%;font:inherit;background:white;border:1px solid #b8c9bc;border-radius:8px;padding:10px;margin-top:6px}textarea{min-height:130px}input[type=checkbox],input[type=radio]{display:inline-block;width:auto}button,.button{display:inline-block;font:inherit;cursor:pointer;border:0;border-radius:8px;padding:10px 16px;background:var(--green);color:white;text-decoration:none;min-height:42px}.secondary{background:#eaf0e7;color:var(--ink)}.badge,.status{display:inline-block;border-radius:20px;background:#edf2e8;padding:3px 10px;font-size:12px}.error,.blocked{background:#fff0e6;padding:12px;border-radius:8px}.eyebrow{font-size:11px;letter-spacing:1.8px;text-transform:uppercase;color:var(--muted)}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:600px;overflow:auto;background:#f2f5ef;border:1px solid var(--line);padding:16px;border-radius:8px;font:13px/1.6 ui-monospace,monospace}table{width:100%;border-collapse:collapse;display:block;overflow-x:auto;margin:18px 0}th,td{text-align:left;padding:12px;border-bottom:1px solid var(--line)}th{font-size:12px;color:var(--muted)}nav:not(.shell-primary){display:flex;gap:14px;flex-wrap:wrap;margin:12px 0 20px}details{margin:12px 0}summary{cursor:pointer;font-weight:600}.login{max-width:440px;margin:8vh auto}.login-wrap{padding:24px}.progress{height:5px;background:#edf2e8;border-radius:5px}.progress i{display:block;height:100%;background:var(--green)}.review-layout{min-width:0}
@media(min-width:801px){.shell-menu>nav{display:grid!important}}
@media(max-width:800px){.shell-sidebar{position:static;width:100%;padding:16px}.shell-brand{padding:0 0 8px;font-size:23px}.shell-brand small{display:none}.shell-menu{margin:0}.shell-menu>summary{display:block;color:#e5efdf;padding:8px 0}.shell-sidebar nav{grid-template-columns:repeat(3,minmax(0,1fr))}.shell-sidebar nav a{padding:8px;font-size:13px}.shell-sidebar footer{display:none}.shell-content{margin:0}.shell-header{min-height:60px;padding:12px 18px}.shell-main{padding:24px 18px 50px}.shell-grid,.grid,.project-grid{grid-template-columns:1fr}.card,.panel{padding:18px}.shell-header span{display:none}.shell-skip:focus{left:16px}.shell-tabs{gap:4px}.shell-tabs a{padding:6px 9px;font-size:13px}}
'''

def project_tabs(path):
    match=re.match(r'^/(?:work|projects)/([^/]+)(?:/|$)',path)
    alternate=re.match(r'^/workspace/projects/([^/]+)/([^/]+)$',path)
    if not match and not alternate:return ''
    pid=(match or alternate).group(1)
    tab=alternate.group(2) if alternate else ('summary' if path.startswith('/work/') else 'tasks')
    p=quote(pid,safe='')
    items=(('summary','/work/'+p,'Summary'),('tasks','/projects/'+p,'Tasks'),
           ('conversations','/workspace/projects/'+p+'/conversations','Conversations'),
           ('knowledge','/workspace/projects/'+p+'/knowledge','Knowledge'),
           ('activity','/workspace/projects/'+p+'/activity','Activity'))
    return '<p class="shell-context"><a href="/projects">Projects</a> / Project workspace</p><nav class="shell-tabs" aria-label="Project navigation">'+''.join('<a href="'+url+'"'+(' aria-current="page"' if key==tab else '')+'>'+label+'</a>' for key,url,label in items)+'</nav>'

def contextual_links(key):
    links={
      'overview':(('/','Overview'),('/briefing','Inbox briefing'),('/memory/briefing','Work briefing')),
      'tasks':(('/tasks','Suggestions'),('/runtime','Execution'),('/queue','Legacy queue'),('/coding','Coding workspace')),
      'knowledge':(('/knowledge','Knowledge home'),('/tools','Source files'),('/documents','Documents'),('/research-desk','Research')),
      'calendar':(('/calendar','Calendar'),('/meetings','Meetings')),
      'settings':(('/settings','Settings home'),('/memory','Memory & Writing DNA'),('/memory/preview','Context preview'),('/inboxes/setup','Connection guide')),
    }
    values=links.get(key,())
    if not values:return ''
    return '<nav class="shell-tabs" aria-label="Section navigation">'+''.join('<a href="'+url+'"'+(' aria-current="page"' if request_path.get()==url else '')+'>'+label+'</a>' for url,label in values)+'</nav>'

def page(body,title='Superhuman',signed_in=True):
    head='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(title)+' | Superhuman</title><style>'+STYLE+'</style></head><body>'
    if not signed_in:return head+'<main class="login-wrap">'+body+'</main></body></html>'
    path=request_path.get();key=section(path);label=dict((k,l) for k,_,l in NAV)[key]
    nav=''.join('<a href="'+url+'"'+(' aria-current="page"' if key==k else '')+'>'+name+'</a>' for k,url,name in NAV)
    return head+'<a class="shell-skip" href="#main">Skip to content</a><aside class="shell-sidebar"><a class="shell-brand" href="/">superhuman.<small>YOUR PERSONAL WORKSPACE</small></a><details class="shell-menu" open><summary>Menu</summary><nav class="shell-primary" aria-label="Main navigation">'+nav+'</nav></details><footer>Private workspace<br>Built around how you think.</footer></aside><div class="shell-content"><header class="shell-header"><div><strong>'+label+'</strong><br><span>'+esc(title)+'</span></div><form method="post" action="/logout"><button>Sign out</button></form></header><main class="shell-main" id="main">'+(project_tabs(path) or contextual_links(key))+body+'</main></div></body></html>'

class PathContext:
    """ContextVar propagates into sync FastAPI handlers without global request state."""
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        token=request_path.set(scope.get('path','/'))
        try:return await self.app(scope,receive,send)
        finally:request_path.reset(token)
