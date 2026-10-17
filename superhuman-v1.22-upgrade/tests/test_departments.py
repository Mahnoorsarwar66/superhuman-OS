"""Read-only department aggregation, isolation and hosted route integration."""
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from superhuman.hosted import web,config,auth
from superhuman.projects import engine as p
from superhuman.runtime import engine as r
from superhuman.dialogue import store as d
from superhuman.researchdesk import store as research
from superhuman.knowledge.store import Store
from superhuman.departments import store

class DepartmentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=Path.cwd();os.chdir(self.temp.name)
        self.env=patch.dict(os.environ,{'SUPERHUMAN_KNOWLEDGE_DB':str(Path('notes.db').resolve()),'SUPERHUMAN_IDENTITY_DIR':str(Path('identity').resolve()),'SUPERHUMAN_MEMORY_PATH':str(Path('memory.json').resolve()),'SUPERHUMAN_MAIL_KEY_FILE':str(Path('mail.key').resolve())});self.env.start()
        self.settings=config.Settings('https://superhuman.example',state_dir=Path('state'))
        auth.Store(self.settings.auth_db).setup('owner','synthetic-test-passphrase')
        self.client=TestClient(web.create_app(self.settings),base_url=self.settings.public_origin)
    def tearDown(self):self.client.close();self.env.stop();os.chdir(self.old);self.temp.cleanup()
    def login(self):
        csrf=re.search(r'name="csrf" value="([^"]+)"',self.client.get('/login').text).group(1)
        self.client.post('/login',data={'csrf':csrf,'username':'owner','password':'synthetic-test-passphrase'},follow_redirects=False)
    def seed(self):
        a=p.create('marketing','Marketing campaign','Real details',12);b=p.create('career_rnd','Other department secret','',12)
        r.initialize()
        with p.connect() as db:
            db.execute("UPDATE projects SET status='plan_review' WHERE id=?",(a,))
            for tid,status in [('done','approved'),('run','running'),('review','needs_review'),('block','quality_blocked')]:
                db.execute('INSERT INTO project_tasks(project_id,id,kind,title,details,deps,checks,status,error) VALUES(?,?,?,?,?,?,?,?,?)',(a,tid,'collab','Task '+tid,'Details','[]','{}',status,'Recorded blocker' if tid=='block' else None))
            db.execute("UPDATE projects SET status='active' WHERE id=?",(b,))
        r.event('marketing_test_event',a);r.event('private_career_event',b)
        d.create('marketing','Marketing discussion',3);d.create('career_rnd','Other department discussion',3)
        research.create('Marketing evidence','marketing','Marketing questions','Hypothesis','a'*32)
        research.create('Other department research','career_rnd','Questions','Hypothesis','b'*32)
        return a,b
    def test_authentication_and_unknown_routes(self):
        for path in ('/departments','/departments/marketing','/departments/marketing/knowledge'):
            self.assertEqual(self.client.get(path,follow_redirects=False).status_code,303)
        self.login()
        for path in ('/departments/unknown','/departments/marketing/missing','/departments/marketing/projects?page=0'):
            self.assertEqual(self.client.get(path).status_code,404)
    def test_empty_read_does_not_create_records_or_folders(self):
        self.login();before={str(x) for x in Path('.').rglob('*')}
        snap=store.snapshot('marketing');self.assertEqual(snap['counts']['projects'],0)
        result=self.client.get('/departments');self.assertEqual(result.status_code,200)
        self.assertIn('UK Innovator',result.text);self.assertIn('Shared support',result.text)
        self.assertEqual(before,{str(x) for x in Path('.').rglob('*')})
        self.assertFalse(Path('data').exists())
    def test_exact_counts_and_deterministic_next_step(self):
        a,_=self.seed();snap=store.snapshot('marketing');c=snap['counts']
        self.assertEqual((c['projects'],c['tasks'],c['approved'],c['running'],c['outputs_review'],c['plans_review'],c['blocked_tasks']),(1,4,1,1,1,1,1))
        self.assertIn(a,snap['next'][1]);self.assertIn('prepared plan',snap['next'][0])
        self.assertEqual(c['conversations'],1);self.assertEqual(c['areas'],1)
    def test_every_tab_is_scoped(self):
        self.seed();self.login()
        for suffix in ('','/projects','/knowledge','/conversations','/activity'):
            with self.subTest(suffix=suffix):
                out=self.client.get('/departments/marketing'+suffix)
                self.assertEqual(out.status_code,200,out.text[:300])
                self.assertNotIn('Other department',out.text);self.assertNotIn('private career event',out.text)
                self.assertEqual(out.text.count('aria-label="Main navigation"'),1)
                self.assertIn('href="/departments" aria-current="page"',out.text)
                self.assertIn('aria-label="Department navigation"',out.text)
                self.assertEqual(int(out.headers['content-length']),len(out.content))
    def test_departments_above_projects_everywhere(self):
        self.login()
        for path in ('/','/projects','/tools','/tasks','/departments'):
            out=self.client.get(path);primary=re.search(r'<nav class="shell-primary".*?</nav>',out.text).group(0)
            self.assertLess(primary.index('>Departments</a>'),primary.index('>Projects</a>'))
    def test_decisions_exclude_other_scopes_sensitive_proposed_and_expired(self):
        self.seed();self.login();notes=Store()
        notes.add('marketing','decision','Approved decision','Recorded choice',status='confirmed')
        notes.add('career_rnd','decision','Other department decision','Hidden',status='confirmed')
        notes.add('marketing','decision','Sensitive choice','Hidden',status='confirmed',sensitive=True)
        notes.add('marketing','decision','Unconfirmed choice','Hidden',status='proposed')
        notes.add('marketing','decision','Expired choice','Hidden',status='confirmed',expires_on='2000-01-01')
        out=self.client.get('/departments/marketing/activity');self.assertIn('Approved decision',out.text)
        for title in ('Other department decision','Sensitive choice','Unconfirmed choice','Expired choice'):self.assertNotIn(title,out.text)
    def test_files_exports_and_no_hidden_or_symlink_inputs(self):
        self.login();folder=Path('data/workspaces/marketing/inputs');folder.mkdir(parents=True)
        (folder/'report.txt').write_text('Public task source');(folder/'.env').write_text('SECRET')
        other=Path('outside.txt');other.write_text('OTHER');(folder/'link.txt').symlink_to(other.resolve())
        out=Path('data/workspaces/marketing/exports/testexport');out.mkdir(parents=True)
        (out/'record.json').write_text(json.dumps({'project':'marketing','export_id':'testexport','title':'Campaign document','format':'pdf','created_at':'2026-10-16T00:00:00+00:00'}))
        snap=store.snapshot('marketing');self.assertEqual([r['name'] for r in snap['files']],['report.txt']);self.assertEqual(len(snap['exports']),1)
        result=self.client.get('/departments/marketing/knowledge');self.assertIn('Campaign document',result.text);self.assertNotIn('SECRET',result.text);self.assertNotIn('link.txt',result.text)
    def test_large_department_counts_are_not_capped_by_pagination(self):
        self.login()
        for i in range(53):p.create('marketing','Campaign '+str(i),'',12)
        self.assertEqual(store.snapshot('marketing')['counts']['projects'],53)
        first=self.client.get('/departments/marketing/projects');second=self.client.get('/departments/marketing/projects?page=2')
        self.assertIn('Next page',first.text);self.assertIn('Previous page',second.text)
        self.assertIn('Objectives (53)',second.text)
    def test_html_escaping_no_script_and_csrf_unchanged(self):
        pid=p.create('marketing','<script>unsafe</script>','',12);self.login()
        out=self.client.get('/departments/marketing/projects');self.assertIn('&lt;script&gt;unsafe&lt;/script&gt;',out.text);self.assertNotIn('<script>',out.text)
        self.assertIn("script-src 'none'",out.headers['content-security-policy'])
        self.assertEqual(self.client.post('/departments/marketing').status_code,403)
    def test_missing_deadlines_and_goals_are_explicit(self):
        self.login();out=self.client.get('/departments/marketing')
        self.assertIn('Department goal',out.text);self.assertIn('Not set',out.text);self.assertIn('do not have department associations',out.text)
    def test_readonly_queries_preserve_existing_database(self):
        self.seed();before=Path(p.DEFAULT_DB).read_bytes()
        store.snapshot('marketing');self.assertEqual(before,Path(p.DEFAULT_DB).read_bytes())
    def test_corrupt_db_shows_warning(self):
        Path('broken.db').write_bytes(b'not a sqlite database')
        data=store.snapshot('marketing',path='broken.db');self.assertTrue(data['warnings'])
    def test_writing_remains_shared_support(self):
        self.login();self.assertNotIn('writing',[k for k,_ in store.departments()])
        self.assertEqual(self.client.get('/departments/writing').status_code,200)

if __name__=='__main__':unittest.main()
