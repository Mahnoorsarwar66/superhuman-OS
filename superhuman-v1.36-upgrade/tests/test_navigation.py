"""Integration checks use a temporary workspace and no paid model requests."""
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from superhuman.hosted import auth,config,web
from superhuman.navigation import shell
from superhuman.projects import engine as projects
from superhuman.runtime import engine as runtime
from superhuman.dialogue import store as dialogue

class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=Path.cwd();os.chdir(self.temp.name)
        self.env=patch.dict(os.environ,{'SUPERHUMAN_IDENTITY_DIR':str(Path('identity').resolve()),'SUPERHUMAN_MEMORY_PATH':str(Path('memory.json').resolve()),'SUPERHUMAN_KNOWLEDGE_DB':str(Path('knowledge.db').resolve()),'SUPERHUMAN_MAIL_KEY_FILE':str(Path('mail.key').resolve())});self.env.start()
        self.settings=config.Settings('https://superhuman.example',state_dir=Path('state'))
        auth.Store(self.settings.auth_db).setup('owner','synthetic-test-passphrase')
        self.app=web.create_app(self.settings);self.client=TestClient(self.app,base_url=self.settings.public_origin)
    def tearDown(self):self.client.close();self.env.stop();os.chdir(self.old);self.temp.cleanup()
    def token(self,r):return re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
    def login(self):
        csrf=self.token(self.client.get('/login'))
        self.client.post('/login',data={'username':'owner','password':'synthetic-test-passphrase','csrf':csrf})
    def test_private_and_login_surface(self):
        for url in ('/knowledge','/reviews','/settings','/workspace/projects/id/activity'):
            self.assertEqual(self.client.get(url,follow_redirects=False).status_code,303)
        self.assertNotIn('aria-label="Main navigation"',self.client.get('/login').text)
    def test_all_existing_pages_share_one_shell(self):
        self.login()
        for url in ('/','/projects','/tools','/documents','/coding','/runtime','/queue','/talk','/memory','/memory/preview','/memory/briefing','/inboxes','/briefing','/tasks','/calendar','/meetings','/research-desk','/knowledge','/settings','/reviews'):
            with self.subTest(url=url):
                r=self.client.get(url)
                self.assertEqual(r.status_code,200,r.text[:300])
                self.assertEqual(r.text.count('aria-label="Main navigation"'),1)
                self.assertNotIn('class="sidebar"',r.text)
                primary=re.search(r'<nav class="shell-primary".*?</nav>',r.text).group(0)
                self.assertEqual(primary.count('aria-current="page"'),1)
                for _,path,name in shell.NAV:self.assertIn('>'+name+'</a>',primary)
                self.assertIn("script-src 'self'",r.headers['content-security-policy'])
                self.assertEqual(int(r.headers['content-length']),len(r.content))
    def test_forms_and_existing_project_creation(self):
        self.login();r=self.client.get('/projects');csrf=self.token(r)
        self.assertEqual(self.client.post('/projects',data={'workstream':'marketing','objective':'A real objective','details':'Context','max_calls':12},follow_redirects=False).status_code,403)
        r=self.client.post('/projects',data={'csrf':csrf,'workstream':'marketing','objective':'A real objective','details':'Context','max_calls':12},follow_redirects=False)
        self.assertEqual(r.status_code,303)
        self.assertIn('A real objective',self.client.get(r.headers['location']).text)
    def test_project_tabs_and_isolation(self):
        self.login();a=projects.create('marketing','Marketing objective','',12);b=projects.create('career_rnd','Career objective','',12)
        runtime.event('synthetic_a',a);runtime.event('synthetic_b',b)
        from superhuman.experience import store as ux
        ux.initialize();tid=dialogue.create('marketing','Marketing conversation',3);ux.link(tid,'canonical',a);dialogue.create('career_rnd','Career conversation',3)
        for path in ('/work/'+a,'/projects/'+a,'/workspace/projects/'+a+'/conversations','/workspace/projects/'+a+'/knowledge','/workspace/projects/'+a+'/activity'):
            r=self.client.get(path);self.assertEqual(r.status_code,200,r.text[:300]);self.assertIn('aria-label="Project navigation"',r.text)
        r=self.client.get('/workspace/projects/'+a+'/activity');self.assertIn('synthetic a',r.text);self.assertNotIn('synthetic b',r.text)
        r=self.client.get('/workspace/projects/'+a+'/conversations');self.assertIn('Marketing conversation',r.text);self.assertNotIn('Career conversation',r.text)
        r=self.client.get('/projects?workstream=marketing');self.assertIn('Marketing objective',r.text);self.assertNotIn('Career objective',r.text)
    def test_project_research_is_shared_only_with_same_workstream(self):
        self.login();pid=projects.create('marketing','University outreach','',12)
        from superhuman.researchdesk import store as research
        research.create('University outreach sources','marketing','Questions','Hypothesis','a'*32)
        research.create('Career private sources','career_rnd','Questions','Hypothesis','b'*32)
        r=self.client.get('/workspace/projects/'+pid+'/knowledge')
        self.assertEqual(r.status_code,200)
        self.assertIn('University outreach sources',r.text)
        self.assertNotIn('Career private sources',r.text)
        self.assertIn('shared across',r.text)

    def test_review_queue_and_html_escaping(self):
        self.login();pid=projects.create('marketing','<script>unsafe</script>','',12)
        with projects.connect() as db:db.execute("UPDATE projects SET status='plan_review' WHERE id=?",(pid,))
        r=self.client.get('/reviews');self.assertIn('&lt;script&gt;unsafe&lt;/script&gt;',r.text);self.assertNotIn('<script>',r.text)
        self.assertIn('/work/'+pid,r.text)
    def test_unknown_workspace_and_filter(self):
        self.login()
        for path in ('/workspace/projects/missing/activity','/workspace/projects/missing/unknown'):
            self.assertEqual(self.client.get(path).status_code,404)
        self.assertEqual(self.client.get('/projects?workstream=unknown').status_code,400)
    def test_shell_context_reset_and_mobile(self):
        self.login();self.client.get('/calendar');r=self.client.get('/knowledge')
        nav=re.search(r'<nav class="shell-primary".*?</nav>',r.text).group(0)
        self.assertIn('href="/storage" aria-current="page"',nav)
        self.assertIn('<summary>Menu</summary>',r.text);self.assertIn('@media(max-width:800px)',r.text)
        self.assertIn('href="#main"',r.text);self.assertIn('<script src="/assets/workspace.js" defer>',r.text);self.assertNotIn('<script>',r.text)

if __name__=='__main__':unittest.main()
