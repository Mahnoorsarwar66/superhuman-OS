import json
import os
from pathlib import Path
import re
import tempfile
import time
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from fastapi.responses import FileResponse
from superhuman.hosted import config,auth,web,jobs
from superhuman.runtime import engine as runtime
from superhuman.projects import engine as projects

PASSWORD='synthetic-test-passphrase'


def token(response):
    found=re.search(r'name="csrf" value="([^"]+)"',response.text)
    if not found:raise AssertionError('No CSRF token in page: '+str(response.status_code))
    return found.group(1)


class Peer:
    def __init__(self,app,host):self.app=app;self.host=host
    async def __call__(self,scope,receive,send):
        if scope['type']=='http':scope={**scope,'client':(self.host,10000)}
        await self.app(scope,receive,send)


class HostedTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=Path.cwd();os.chdir(self.temp.name)
        self.env=patch.dict(os.environ,{'SUPERHUMAN_IDENTITY_DIR':str(Path('identity').resolve()),'SUPERHUMAN_MEMORY_PATH':str(Path('memory.json').resolve())});self.env.start()
        self.settings=config.Settings('https://superhuman.example',state_dir=Path('state'))
        self.store=auth.Store(self.settings.auth_db);self.store.setup('owner',PASSWORD)
        self.app=web.create_app(self.settings)
        self.client=TestClient(self.app,base_url=self.settings.public_origin)
    def tearDown(self):self.client.close();self.env.stop();os.chdir(self.old);self.temp.cleanup()
    def login(self,client=None):
        client=client or self.client
        csrf=token(client.get('/login'))
        response=client.post('/login',data={'username':'owner','password':PASSWORD,'csrf':csrf},follow_redirects=False)
        self.assertEqual(response.status_code,303)
        return token(client.get('/'))
    def test_all_private_surfaces_require_login(self):
        for path in ('/','/projects','/runtime/state','/tools','/coding','/documents','/documents/download/marketing/id','/projects/id/tasks/final/download'):
            response=self.client.get(path,follow_redirects=False)
            self.assertEqual(response.status_code,303,path)
            self.assertNotIn('objective',response.text)
    def test_login_and_authenticated_mobile_page(self):
        self.login();response=self.client.get('/')
        self.assertEqual(response.status_code,200);self.assertIn('What needs moving forward?',response.text)
        self.assertIn('width=device-width',response.text)
        self.assertEqual(response.headers['cache-control'],'no-store')
    def test_session_cookie_security_and_server_side_storage(self):
        csrf=token(self.client.get('/login'))
        response=self.client.post('/login',data={'username':'owner','password':PASSWORD,'csrf':csrf},follow_redirects=False)
        cookies=response.headers.get_list('set-cookie')
        self.assertTrue(any('HttpOnly' in c and 'Secure' in c and 'SameSite=strict' in c for c in cookies))
        raw=self.client.cookies[auth.COOKIE]
        with self.store.connect() as db:stored=db.execute("SELECT token_hash FROM sessions WHERE kind='owner'").fetchone()[0]
        self.assertNotEqual(stored,raw);self.assertEqual(stored,auth.token_hash(raw))
    def test_password_is_salted_and_not_stored_plaintext(self):
        with self.store.connect() as db:row=db.execute('SELECT * FROM owner').fetchone()
        self.assertNotEqual(row['password_hash'],PASSWORD)
        self.assertEqual(row['password_hash'],auth.password_hash(PASSWORD,row['salt']))
    def test_invalid_password_and_rate_limit(self):
        csrf=token(self.client.get('/login'))
        for _ in range(5):
            response=self.client.post('/login',data={'username':'owner','password':'incorrect','csrf':csrf})
            self.assertEqual(response.status_code,401)
        response=self.client.post('/login',data={'username':'owner','password':PASSWORD,'csrf':csrf})
        self.assertEqual(response.status_code,429)
    def test_missing_and_forged_login_csrf_rejected(self):
        self.client.get('/login')
        for value in ('','not-the-token','非ASCII'):
            self.assertEqual(self.client.post('/login',data={'username':'owner','password':PASSWORD,'csrf':value}).status_code,403)
    def test_foreign_origin_rejected(self):
        csrf=self.login()
        response=self.client.post('/worker/pause',data={'paused':'true','csrf':csrf},headers={'origin':'https://attacker.example'})
        self.assertEqual(response.status_code,403);self.assertFalse(jobs.worker_status()['paused'])
    def test_null_origin_rejected(self):
        csrf=self.login()
        self.assertEqual(self.client.post('/worker/pause',data={'paused':'true','csrf':csrf},headers={'origin':'null'}).status_code,403)
    def test_host_and_transport_restricted(self):
        self.assertEqual(self.client.get('/login',headers={'host':'attacker.example'}).status_code,400)
        with TestClient(self.app,base_url='http://superhuman.example') as client:self.assertEqual(client.get('/login').status_code,400)
    def test_csrf_applies_to_existing_routes(self):
        self.login()
        response=self.client.post('/jobs',data={'project':'marketing','kind':'collab','title':'Draft note'})
        self.assertEqual(response.status_code,403)
    def test_post_forms_receive_csrf_tokens(self):
        self.login()
        for path in ('/','/tools','/coding','/documents','/projects'):
            response=self.client.get(path)
            self.assertEqual(response.status_code,200,path)
            forms=re.findall(r'<form\b[^>]*method=[\"\']?post[^>]*>(.*?)</form>',response.text,re.S|re.I)
            self.assertTrue(forms,path)
            self.assertTrue(all('name="csrf"' in f for f in forms),path)
    def test_create_task_without_web_model_request(self):
        csrf=self.login()
        with patch.object(projects,'client_or_default',side_effect=AssertionError('Web request cannot call model')):
            response=self.client.post('/tasks',data={'workstream':'marketing','kind':'collab','instruction':'Draft a university note','csrf':csrf},follow_redirects=False)
        self.assertEqual(response.status_code,303)
        p=projects.listing()[0];self.assertEqual(p['used_calls'],0);self.assertEqual(p['status'],'active')
    def test_create_objective_queues_plan_without_spending(self):
        csrf=self.login()
        with patch.object(projects,'generate_plan',side_effect=AssertionError('Planning must run in worker')):
            response=self.client.post('/objectives',data={'workstream':'marketing','objective':'Prepare university briefing','details':'Use supplied evidence','max_calls':'12','csrf':csrf},follow_redirects=False)
        self.assertEqual(response.status_code,303)
        p=projects.listing()[0];self.assertEqual(p['status'],'new');self.assertEqual(p['used_calls'],0)
        with projects.connect() as db:self.assertEqual(db.execute('SELECT status FROM hosted_plans').fetchone()[0],'queued')
    def test_pause_and_resume(self):
        csrf=self.login()
        for value,expected in [('true',True),('false',False)]:
            response=self.client.post('/worker/pause',data={'paused':value,'csrf':csrf},follow_redirects=False)
            self.assertEqual(response.status_code,303);self.assertEqual(bool(jobs.worker_status()['paused']),expected)
    def test_logout_revokes_session(self):
        csrf=self.login();response=self.client.post('/logout',data={'csrf':csrf},follow_redirects=False)
        self.assertEqual(response.status_code,303);self.assertEqual(self.client.get('/',follow_redirects=False).status_code,303)
    def test_logout_get_has_no_effect(self):
        self.login();self.assertEqual(self.client.get('/logout').status_code,405)
        self.assertEqual(self.client.get('/').status_code,200)
    def test_expired_session_fails_closed(self):
        self.login()
        with self.store.connect() as db:db.execute("UPDATE sessions SET expires=0 WHERE kind='owner'")
        self.assertEqual(self.client.get('/',follow_redirects=False).status_code,303)
    def test_password_reset_revokes_sessions(self):
        self.login();self.store.reset_password('a-new-synthetic-password')
        self.assertEqual(self.client.get('/',follow_redirects=False).status_code,303)
    def test_login_rotates_old_session(self):
        self.login();old=self.client.cookies[auth.COOKIE];self.login()
        self.assertNotEqual(old,self.client.cookies[auth.COOKIE]);self.assertIsNone(self.store.session(old))
    def test_security_headers_and_no_inline_script(self):
        self.login();response=self.client.get('/')
        self.assertIn("script-src 'self'",response.headers['content-security-policy'])
        self.assertEqual(response.headers['referrer-policy'],'same-origin')
        self.assertIn('<script src="/assets/workspace.js" defer>',response.text);self.assertNotIn('<script>',response.text)
    def test_upload_limit_checked_before_parsing(self):
        self.login()
        response=self.client.post('/tools/upload',content=b'x',headers={'content-length':str(self.settings.max_body+1)})
        self.assertEqual(response.status_code,413)
    def test_multipart_upload_requires_csrf(self):
        csrf=self.login()
        response=self.client.post('/tools/upload',data={'project':'marketing','csrf':csrf},files={'upload':('note.txt',b'Private source text','text/plain')},follow_redirects=False)
        self.assertEqual(response.status_code,303)
        self.assertTrue(any(p.name=='note.txt' for p in Path('data').rglob('note.txt')))
    def test_html_escapes_user_content(self):
        self.login();pid=runtime.enqueue('collab','marketing','Draft <script>bad()</script>')
        response=self.client.get('/work/'+pid)
        self.assertIn('&lt;script&gt;',response.text);self.assertNotIn('<script>bad()',response.text)
    def test_authenticated_download_is_streamed(self):
        file=Path('private.txt');file.write_text('private artifact',encoding='utf-8')
        @self.app.inner.get('/test-private-file')
        def private():return FileResponse(file,media_type='application/octet-stream')
        self.assertEqual(self.client.get('/test-private-file',follow_redirects=False).status_code,303)
        self.login();response=self.client.get('/test-private-file')
        self.assertEqual(response.content,b'private artifact');self.assertEqual(response.headers['cache-control'],'no-store')
    def test_real_project_download_requires_login_and_preserves_content(self):
        pid=runtime.enqueue('collab','marketing','Prepare a draft')
        def execute(task,brief,folder):
            file=folder/'draft.md';file.write_text('Private draft content',encoding='utf-8');return {'output':str(file)}
        projects.run_one(pid,executor=execute)
        route='/projects/'+pid+'/tasks/final/download'
        self.assertEqual(self.client.get(route,follow_redirects=False).status_code,303)
        self.login();response=self.client.get(route)
        self.assertEqual(response.status_code,200);self.assertIn('Private draft content',response.text)
        self.assertIn('text/plain',response.headers['content-type'])
    def test_legacy_review_route_checks_artifact_hash(self):
        csrf=self.login();pid=runtime.enqueue('collab','marketing','Prepare a draft')
        def execute(task,brief,folder):
            file=folder/'draft.md';file.write_text('Original draft',encoding='utf-8');return {'output':str(file)}
        task=projects.run_one(pid,executor=execute)
        Path(task['output']).write_text('Changed without review',encoding='utf-8')
        response=self.client.post('/projects/'+pid+'/review',data={'task':'final','action':'approve','note':'Reviewed','csrf':csrf})
        self.assertEqual(response.status_code,400);self.assertEqual(projects.get(pid)['status'],'needs_review')
    def test_unconfigured_app_fails_closed(self):
        with TestClient(web.create_app(configured=False),base_url='https://superhuman.example') as client:
            self.assertEqual(client.get('/login').status_code,503)
    def test_health_does_not_expose_private_state(self):
        response=self.client.get('/healthz');self.assertEqual(response.status_code,200)
        self.assertEqual(set(response.json()),{'status','version'})
    def test_http_tunnel_only_allows_loopback_peer(self):
        settings=config.Settings('http://127.0.0.1:8000',True,state_dir=self.settings.state_dir)
        app=web.create_app(settings)
        with TestClient(Peer(app,'127.0.0.1'),base_url=settings.public_origin) as c:self.assertEqual(c.get('/login').status_code,200)
        with TestClient(Peer(app,'192.0.2.20'),base_url=settings.public_origin) as c:self.assertEqual(c.get('/login').status_code,403)
    def test_original_app_keeps_local_host_guard(self):
        with TestClient(web.legacy.app,base_url='https://superhuman.example') as client:self.assertEqual(client.get('/').status_code,403)
    def test_configuration_rejects_insecure_public_origins(self):
        for value,tunnel in [('http://public.example',False),('http://public.example',True),('https://user:pass@public.example',False),('https://public.example/path',False)]:
            with self.assertRaises(ValueError):config.Settings(value,tunnel)
    def test_origin_round_trip(self):
        settings=config.Settings('https://Superhuman.Example:443/',state_dir=Path('state'))
        path=Path('state/config.json');config.save(settings,path)
        self.assertEqual(config.load(path).public_origin,'https://superhuman.example')


if __name__=='__main__':unittest.main()
