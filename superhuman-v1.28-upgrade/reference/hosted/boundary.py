"""ASGI boundary: origin/transport, authentication, CSRF and upload limits."""
import hmac
from http.cookies import SimpleCookie,CookieError
import ipaddress
import json
import re
from email.parser import BytesParser
from email.policy import default
from urllib.parse import parse_qs
from starlette.responses import HTMLResponse,JSONResponse,RedirectResponse,PlainTextResponse
from .auth import Store,COOKIE,LOGIN_COOKIE
from .config import origin

HEADERS={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY',
         'Referrer-Policy':'same-origin','Permissions-Policy':'camera=(), microphone=(), geolocation=()',
         'Content-Security-Policy':"default-src 'self'; script-src 'none'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"}


def csrf_from(body,content_type,headers):
    supplied=headers.get('x-csrf-token')
    if supplied:return supplied
    if content_type.startswith('application/x-www-form-urlencoded'):
        values=parse_qs(body.decode('utf-8'),max_num_fields=200).get('csrf',[])
        return values[0] if len(values)==1 else ''
    if content_type.startswith('multipart/form-data'):
        msg=BytesParser(policy=default).parsebytes(('Content-Type: '+content_type+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+body)
        values=[]
        if msg.is_multipart():
            for part in msg.iter_parts():
                if part.get_param('name',header='content-disposition')=='csrf' and part.get_filename() is None:
                    value=part.get_payload(decode=True) or b''
                    if len(value)>200:return ''
                    values.append(value.decode('utf-8'))
        return values[0] if len(values)==1 else ''
    return ''


def inject_forms(html,csrf):
    def replace(match):
        tag=match.group()
        if re.search(r'\bmethod\s*=\s*[\"\']?post\b',tag,re.I):
            return tag+'<input type="hidden" name="csrf" value="'+csrf+'">'
        return tag
    return re.sub(r'<form\b[^>]*>',replace,html,flags=re.I)


def cookie(response,key,value,settings,max_age):
    response.set_cookie(key,value,max_age=max_age,httponly=True,secure=settings.secure_cookie,samesite='strict',path='/')


class Boundary:
    def __init__(self,app,settings,login_page):
        self.inner=app;self.settings=settings;self.login_page=login_page
        self.routes=app.routes
    async def __call__(self,scope,receive,send):
        if scope['type']=='lifespan':return await self.inner(scope,receive,send)
        if scope['type']!='http':
            if scope['type']=='websocket':await send({'type':'websocket.close','code':1008})
            return
        settings=self.settings
        async def reply(response):
            for key,value in HEADERS.items():response.headers[key]=value
            if settings and settings.secure_cookie:response.headers['Strict-Transport-Security']='max-age=31536000'
            await response(scope,receive,send)
        if settings is None:return await reply(PlainTextResponse('Service setup required',status_code=503))
        headers={k.decode('latin-1').lower():v.decode('latin-1') for k,v in scope['headers']}
        # Duplicate Host, Origin or Content-Length values are never accepted.
        names=[k.decode('latin-1').lower() for k,v in scope['headers']]
        if any(names.count(name)>1 for name in ('host','origin','content-length')):
            return await reply(PlainTextResponse('Invalid request headers',status_code=400))
        if any(ord(c)<33 for c in headers.get('host','')):
            return await reply(PlainTextResponse('Invalid host',status_code=400))
        try:actual=origin(scope.get('scheme','http')+'://'+headers.get('host',''))
        except ValueError:return await reply(PlainTextResponse('Invalid host',status_code=400))
        if actual!=settings.public_origin:return await reply(PlainTextResponse('Host or transport not allowed',status_code=400))
        if settings.tunnel:
            peer=(scope.get('client') or ('',0))[0]
            try:local=ipaddress.ip_address(peer).is_loopback
            except ValueError:local=False
            if not local:return await reply(PlainTextResponse('Tunnel mode requires a loopback connection',status_code=403))
        if scope['path']=='/favicon.ico' and scope['method'] in ('GET','HEAD'):
            return await reply(PlainTextResponse('',status_code=204))
        if scope['path']=='/healthz' and scope['method']=='GET':
            return await reply(JSONResponse({'status':'ok','version':'1.27.0'}))
        store=Store(settings.auth_db)
        if not store.configured():return await reply(PlainTextResponse('Service setup required',status_code=503))
        if scope['path']=='/hooks/whatsapp':
            if names.count('x-hub-signature-256')>1:return await reply(PlainTextResponse('Invalid signature headers',status_code=400))
            from superhuman.comms.providers import webhook
            return await reply(await webhook(scope,receive,headers))
        cookies=SimpleCookie()
        try:cookies.load(headers.get('cookie',''))
        except CookieError:return await reply(PlainTextResponse('Invalid cookie',status_code=400))
        def raw(key):return cookies[key].value if key in cookies else ''
        path=scope['path'];method=scope['method']
        login=path=='/login'
        session=store.session(raw(LOGIN_COOKIE),'login',600) if login and method=='POST' else store.session(raw(COOKIE),idle=settings.idle_seconds)
        if login and method=='GET':
            token,value=store.new_session('login',600)
            response=HTMLResponse(self.login_page(value['csrf']))
            cookie(response,LOGIN_COOKIE,token,settings,600)
            return await reply(response)
        if session is None:
            if login or method not in ('GET','HEAD'):return await reply(PlainTextResponse('Sign in required',status_code=401))
            return await reply(RedirectResponse('/login',status_code=303))
        unsafe=method not in ('GET','HEAD','OPTIONS')
        body=b''
        if unsafe:
            # Normal browsers send Origin. Token validation also covers clients
            # without Origin; an explicitly foreign/null origin is rejected.
            if 'origin' in headers:
                try:request_origin=origin(headers['origin'])
                except ValueError:request_origin=''
                if request_origin!=settings.public_origin:return await reply(PlainTextResponse('Origin not allowed',status_code=403))
            if headers.get('sec-fetch-site')=='cross-site':return await reply(PlainTextResponse('Cross-site request denied',status_code=403))
            try:length=int(headers.get('content-length','0'))
            except ValueError:return await reply(PlainTextResponse('Invalid body length',status_code=400))
            maximum=8192 if login else settings.max_body
            if length<0 or length>maximum:return await reply(PlainTextResponse('Request is too large',status_code=413))
            parts=[];size=0
            while True:
                message=await receive()
                if message['type']=='http.disconnect':return
                chunk=message.get('body',b'');size+=len(chunk);parts.append(chunk)
                if size>maximum:return await reply(PlainTextResponse('Request is too large',status_code=413))
                if not message.get('more_body',False):break
            body=b''.join(parts)
            try:supplied=csrf_from(body,headers.get('content-type',''),headers)
            except (ValueError,UnicodeError):supplied=''
            if not supplied or not hmac.compare_digest(supplied.encode('utf-8'),session['csrf'].encode('utf-8')):
                return await reply(PlainTextResponse('Form expired or invalid; reload the page',status_code=403))
        if login:
            if method!='POST':return await reply(PlainTextResponse('Method not allowed',status_code=405))
            try:form=parse_qs(body.decode('utf-8'),max_num_fields=10)
            except (ValueError,UnicodeError):return await reply(PlainTextResponse('Invalid sign-in form',status_code=400))
            username=form.get('username',[''])[0];password=form.get('password',[''])[0]
            result=store.login(username,password,(scope.get('client') or ('unknown',0))[0])
            if result!='ok':
                return await reply(HTMLResponse(self.login_page(session['csrf'],'Please wait before trying again.' if result=='limited' else 'Sign-in failed.'),status_code=429 if result=='limited' else 401))
            store.revoke(raw(LOGIN_COOKIE));store.revoke(raw(COOKIE))
            token,value=store.new_session(duration=settings.session_seconds)
            response=RedirectResponse('/',status_code=303)
            cookie(response,COOKIE,token,settings,settings.session_seconds)
            response.delete_cookie(LOGIN_COOKIE,path='/',secure=settings.secure_cookie,httponly=True,samesite='strict')
            return await reply(response)
        if path=='/logout':
            if method!='POST':return await reply(PlainTextResponse('Method not allowed',status_code=405))
            store.revoke(raw(COOKIE));response=RedirectResponse('/login',status_code=303)
            response.delete_cookie(COOKIE,path='/',secure=settings.secure_cookie,httponly=True,samesite='strict')
            return await reply(response)
        scope=dict(scope);scope['state']={**scope.get('state',{}),'csrf':session['csrf']}
        sent=False
        async def replay():
            nonlocal sent
            if not sent:
                sent=True;return {'type':'http.request','body':body,'more_body':False}
            return await receive()
        start=None;chunks=[];html=False;size=0
        async def protected_send(message):
            nonlocal start,html,size
            if message['type']=='http.response.start':
                start=dict(message)
                hdr={k.decode().lower():v.decode('latin-1') for k,v in start.get('headers',[])}
                html='text/html' in hdr.get('content-type','')
                for key,value in HEADERS.items():hdr[key.lower()]=value
                if settings.secure_cookie:hdr['strict-transport-security']='max-age=31536000'
                start['headers']=[(k.encode(),v.encode('latin-1')) for k,v in hdr.items()]
                if not html:await send(start)
            elif message['type']=='http.response.body' and html:
                chunks.append(message.get('body',b''));size+=len(message.get('body',b''))
                if size>3*1024*1024:raise RuntimeError('HTML response exceeds interface limit')
                if not message.get('more_body',False):
                    content=inject_forms(b''.join(chunks).decode('utf-8'),session['csrf']).encode('utf-8')
                    start['headers']=[(k,v) for k,v in start['headers'] if k.lower()!=b'content-length']+[(b'content-length',str(len(content)).encode())]
                    await send(start);await send({'type':'http.response.body','body':content,'more_body':False})
            else:await send(message)
        return await self.inner(scope,replay if unsafe else receive,protected_send)

# knowledge-v110
