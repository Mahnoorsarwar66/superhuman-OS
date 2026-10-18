"""Private local assets, accessible HTML errors and view-preserving redirects."""
import re
from pathlib import Path
from urllib.parse import urlsplit,parse_qs,urlencode
from fastapi.responses import HTMLResponse,FileResponse,RedirectResponse
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import http_exception_handler,request_validation_exception_handler
from starlette.exceptions import HTTPException
from superhuman.navigation import shell
ASSETS=Path(__file__).with_name('assets')

def return_location(location,referrer,host):
    target=urlsplit(location);source=urlsplit(referrer)
    if target.scheme or target.netloc or target.query or source.netloc.lower()!=host.lower():return location
    target_id=re.fullmatch(r'/(?:project-hub|team/projects|milestones)/([a-f0-9]+)(/evidence)?',target.path)
    source_id=re.fullmatch(r'/(?:project-hub|team/projects|milestones)/([a-f0-9]+)(/evidence)?',source.path)
    if not target_id or not source_id or target_id.group(1)!=source_id.group(1):return location
    values=parse_qs(source.query)
    if target_id.group(2):
        panel=values.get('panel',['requirements'])[0]
        return location+'?'+urlencode({'panel':panel}) if panel in ('requirements','investigations','standards') else location
    view=values.get('view',[''])[0]
    allowed=('deliverable','reviews','history','manage') if target.path.startswith('/milestones/') else ('summary','work','files','conversations','activity','manage')
    return location+'?'+urlencode({'view':view}) if view in allowed else location

class ViewReturn:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or scope.get('method')!='POST':return await self.app(scope,receive,send)
        headers=dict(scope.get('headers',[]));ref=headers.get(b'referer',b'').decode('latin-1');host=headers.get(b'host',b'').decode('latin-1')
        async def wrapped(message):
            if message['type']=='http.response.start' and message['status']==303:
                message=dict(message);message['headers']=[(k,return_location(v.decode('latin-1'),ref,host).encode('latin-1') if k.lower()==b'location' else v) for k,v in message.get('headers',[])]
            await send(message)
        await self.app(scope,receive,wrapped)

def fallback(path):
    match=re.match(r'^/project-briefs/([a-f0-9]+)',path)
    if match:return '/project-briefs/'+match[1]+'?step=5','Return to the project brief'
    match=re.match(r'^/milestones/([a-f0-9]+)',path)
    if match:return '/milestones/'+match[1]+'?view=evidence','Return to the milestone'
    match=re.match(r'^/(?:project-hub|team/projects)/([a-f0-9]+)',path)
    if match:return '/team/projects/'+match[1]+'?view=manage','Return to the project'
    if path.startswith('/storage'):return '/storage','Return to Storage'
    if path.startswith('/calendar'):return '/calendar','Return to Calendar'
    return '/','Return to Overview'

def error_page(message,status,path):
    url,label=fallback(path);e=shell.esc
    body='<section class="ui-error"><p class="eyebrow">Action needs attention</p><h1>'+('Page not found' if status==404 else 'Review this before continuing')+'</h1><p role="alert">'+e(message)+'</p><p class="muted">Return to the form to review your entries. If the saved record changed, reload its latest version before trying again.</p><div class="ui-quick-links"><button type="button" data-history-back>Go back</button><a class="button secondary" href="'+e(url)+'">'+e(label)+'</a></div></section>'
    return HTMLResponse(shell.page(body,'Action needs attention'),status_code=status)

def install(app):
    app.add_middleware(ViewReturn)
    @app.get('/assets/interface.css')
    def css():return FileResponse(ASSETS/'design.css',media_type='text/css',headers={'Cache-Control':'private, max-age=3600'})
    @app.get('/assets/interface.js')
    def js():return FileResponse(ASSETS/'design.js',media_type='application/javascript',headers={'Cache-Control':'private, max-age=3600'})
    @app.exception_handler(HTTPException)
    async def http_error(request,exc):
        if 'text/html' not in request.headers.get('accept',''):return await http_exception_handler(request,exc)
        response=error_page(str(exc.detail)[:1200],exc.status_code,request.url.path)
        if exc.headers:
            for key,value in exc.headers.items():response.headers[key]=value
        return response
    @app.exception_handler(RequestValidationError)
    async def validation_error(request,exc):
        if 'text/html' not in request.headers.get('accept',''):return await request_validation_exception_handler(request,exc)
        fields=[]
        for issue in exc.errors()[:8]:
            key=str(issue.get('loc',('entry',))[-1]).replace('_',' ')
            if key not in fields:fields.append(key)
        return error_page('Check the required fields and formats: '+', '.join(fields)+'.',422,request.url.path)
