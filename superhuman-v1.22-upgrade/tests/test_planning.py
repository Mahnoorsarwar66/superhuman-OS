"""Planning persistence, isolation, dependency rules, concurrency and hosted UI."""
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from uuid import uuid4
from unittest.mock import patch
from fastapi.testclient import TestClient
from superhuman.hosted import auth,config,web
from superhuman.projects import engine as p
from superhuman.planning import store,priority

class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=Path.cwd();os.chdir(self.temp.name)
        self.env=patch.dict(os.environ,{'SUPERHUMAN_PLANNING_DB':str(Path('data/planning-test/plans.db').resolve()),'SUPERHUMAN_KNOWLEDGE_DB':str(Path('notes.db').resolve()),'SUPERHUMAN_IDENTITY_DIR':str(Path('identity').resolve()),'SUPERHUMAN_MEMORY_PATH':str(Path('memory.json').resolve()),'SUPERHUMAN_MAIL_KEY_FILE':str(Path('mail.key').resolve())});self.env.start()
        settings=config.Settings('https://superhuman.example',state_dir=Path('state'));auth.Store(settings.auth_db).setup('owner','synthetic-test-passphrase')
        self.client=TestClient(web.create_app(settings),base_url=settings.public_origin)
    def tearDown(self):self.client.close();self.env.stop();os.chdir(self.old);self.temp.cleanup()
    def token(self,r):return re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
    def login(self):
        csrf=self.token(self.client.get('/login'));self.client.post('/login',data={'csrf':csrf,'username':'owner','password':'synthetic-test-passphrase'},follow_redirects=False)
    def goal(self,scope='marketing',priority='high',target='2026-11-01'):
        return store.save_goal(scope,0,'Launch department outcome',priority,target,'Deliverable reviewed')
    def milestone(self,scope='marketing',ident=None,version=0,**kwargs):
        values=dict(title='Prepare evidence',target_date='2026-10-25',success_criteria='Evidence reviewed',status='planned');values.update(kwargs)
        return store.save_milestone(scope,ident or uuid4().hex,version,**values)
    def test_empty_reads_do_not_create_planning_database(self):
        self.assertEqual(store.snapshot('marketing')['goal']['version'],0);self.assertFalse(store.default_path().exists())
        self.login();out=self.client.get('/department-plans/marketing');self.assertEqual(out.status_code,200);self.assertFalse(store.default_path().exists())
    def test_goal_save_edit_and_history_survive_reopen(self):
        first=self.goal();self.assertEqual(first['version'],1)
        updated=store.save_goal('marketing',1,'Updated outcome','critical','2026-11-03','Measurable result')
        self.assertEqual(updated['version'],2);self.assertEqual(store.snapshot('marketing')['goal']['objective'],'Updated outcome')
        h=store.history('marketing');self.assertEqual(len(h),2);self.assertEqual(json.loads(h[0]['before_json'])['objective'],'Launch department outcome')
    def test_stale_goal_and_duplicate_creation_do_not_overwrite(self):
        self.goal()
        with self.assertRaises(store.Conflict):store.save_goal('marketing',0,'Stale','low','','')
        self.assertEqual(store.snapshot('marketing')['goal']['priority'],'high');self.assertEqual(len(store.history('marketing')),1)
    def test_project_links_require_same_department(self):
        a=p.create('marketing','Campaign project','',12);b=p.create('career_rnd','Career project','',12)
        m=self.milestone(project_ids=[a]);self.assertEqual(m['project_ids'],[a])
        with self.assertRaises(ValueError):self.milestone(project_ids=[b])
        with self.assertRaises(ValueError):self.milestone(project_ids=['missing'])
        self.assertEqual(len(store.snapshot('marketing')['milestones']),1)
    def test_dependencies_and_completion_rules(self):
        a=self.milestone(title='First');b=self.milestone(title='Second',depends_on=[a['id']])
        with self.assertRaises(ValueError):self.milestone(ident=b['id'],version=1,title='Second',depends_on=[a['id']],status='in_progress')
        self.milestone(ident=a['id'],version=1,title='First',status='complete',completion_note='Evidence approved')
        self.milestone(ident=b['id'],version=1,title='Second',depends_on=[a['id']],status='in_progress')
        with self.assertRaises(ValueError):self.milestone(ident=a['id'],version=2,title='First',status='planned')
        with self.assertRaises(ValueError):self.milestone(status='complete',completion_note='')
    def test_cycles_self_links_and_cross_scope_dependencies_rejected(self):
        a=self.milestone(title='First');b=self.milestone(title='Second',depends_on=[a['id']]);other=self.milestone(scope='career_rnd',title='Other')
        with self.assertRaises(ValueError):self.milestone(ident=a['id'],version=1,depends_on=[b['id']])
        with self.assertRaises(ValueError):self.milestone(ident=a['id'],version=1,depends_on=[a['id']])
        with self.assertRaises(ValueError):self.milestone(depends_on=[other['id']])
        self.assertEqual(store.snapshot('marketing')['milestones'][0]['version'],1)
    def test_blocker_resolution_and_completion(self):
        m=self.milestone();b=store.save_blocker('marketing',uuid4().hex,0,'Need cost figures','Founder','2026-10-20','open',m['id'])
        with self.assertRaises(ValueError):self.milestone(ident=m['id'],version=1,status='complete',completion_note='Done')
        with self.assertRaises(ValueError):store.save_blocker('marketing',b['id'],1,'Need cost figures','Founder','','resolved',m['id'],'')
        store.save_blocker('marketing',b['id'],1,'Need cost figures','Founder','','resolved',m['id'],'Figures received')
        self.milestone(ident=m['id'],version=1,status='complete',completion_note='Reviewed evidence')
        with self.assertRaises(ValueError):store.save_blocker('marketing',uuid4().hex,0,'New issue','','','open',m['id'])
    def test_item_scope_and_stale_edit_protection(self):
        m=self.milestone()
        with self.assertRaises(ValueError):self.milestone(scope='career_rnd',ident=m['id'],version=1)
        with self.assertRaises(store.Conflict):self.milestone(ident=m['id'],version=0)
        b=store.save_blocker('marketing',uuid4().hex,0,'Need document','','','open')
        with self.assertRaises(store.Conflict):store.save_blocker('marketing',b['id'],0,'Overwrite','','','open')
    def test_invalid_dates_priorities_and_text_rejected(self):
        for dt in ('2026-02-30','20261020','today'):
            with self.assertRaises(ValueError):store.save_goal('marketing',0,'Outcome','high',dt,'')
        with self.assertRaises(ValueError):store.save_goal('marketing',0,'Outcome','invalid','','')
        with self.assertRaises(ValueError):self.milestone(title='')
        with self.assertRaises(ValueError):store.save_goal('marketing',0,'Bad\x00text','high','','')
    def test_priority_order_overdue_and_dependencies_explained(self):
        self.goal('marketing','high');self.goal('career_rnd','critical')
        a=self.milestone(title='Marketing earlier',target_date='2020-01-01')
        b=self.milestone(scope='career_rnd',title='Career future',target_date='2099-01-01')
        c=self.milestone(scope='career_rnd',title='Career overdue',target_date='2020-01-01',depends_on=[b['id']])
        _,items=priority.queue();self.assertEqual(items[0]['title'],'Career overdue');self.assertIn('Waiting for: Career future',items[0]['reason'])
        self.assertEqual(items[-1]['title'],'Marketing earlier')
    def test_all_new_pages_require_authentication(self):
        for path in ('/priorities','/department-plans/marketing','/department-plans/marketing/milestone/new','/department-plans/marketing/blocker/new','/department-plans/marketing/history'):
            self.assertEqual(self.client.get(path,follow_redirects=False).status_code,303)
        self.login();self.assertEqual(self.client.get('/department-plans/unknown').status_code,404)
    def test_browser_form_save_csrf_and_conflict_preserve_values(self):
        self.login();csrf=self.token(self.client.get('/department-plans/marketing'))
        data={'version':0,'objective':'Our launch plan','priority':'high','target_date':'2026-11-01','success_criteria':'Reviewed'}
        self.assertEqual(self.client.post('/department-plans/marketing/goal',data=data).status_code,403)
        data['csrf']=csrf;out=self.client.post('/department-plans/marketing/goal',data=data,follow_redirects=False);self.assertEqual(out.status_code,303)
        data['objective']='Stale browser text';out=self.client.post('/department-plans/marketing/goal',data=data)
        self.assertEqual(out.status_code,409);self.assertIn('Stale browser text',out.text);self.assertEqual(store.snapshot('marketing')['goal']['objective'],'Our launch plan')
    def test_form_milestone_blocker_and_links(self):
        self.login();pid=p.create('marketing','Campaign project','',12)
        r=self.client.get('/department-plans/marketing/milestone/new');csrf=self.token(r);action=re.search(r'<form method="post" action="(/department-plans/[^"]+)"',r.text).group(1)
        out=self.client.post(action,data={'csrf':csrf,'version':0,'title':'Evidence milestone','project_ids':[pid]},follow_redirects=False)
        self.assertEqual(out.status_code,303);m=store.snapshot('marketing')['milestones'][0];self.assertEqual(m['project_ids'],[pid])
        r=self.client.get('/department-plans/marketing/blocker/new');action=re.search(r'<form method="post" action="(/department-plans/[^"]+)"',r.text).group(1)
        out=self.client.post(action,data={'csrf':self.token(r),'version':0,'description':'Need forecasts','needed_from':'Co-founder','milestone_id':m['id']},follow_redirects=False)
        self.assertEqual(out.status_code,303)
        out=self.client.get('/department-plans/marketing');self.assertIn('Evidence milestone',out.text);self.assertIn('Campaign project',out.text);self.assertIn('Need forecasts',out.text)
    def test_summary_dashboard_and_overview_use_saved_plan(self):
        self.login();self.goal();self.milestone(title='Visible milestone')
        for path in ('/','/priorities','/departments','/departments/marketing','/department-plans/marketing'):
            with self.subTest(path=path):
                out=self.client.get(path);self.assertEqual(out.status_code,200,out.text[:300]);self.assertIn('High',out.text)
        self.assertIn('Visible milestone',self.client.get('/').text)
        self.assertIn('Launch department outcome',self.client.get('/departments/marketing').text)
    def test_isolation_and_escaping(self):
        self.login();store.save_goal('marketing',0,'<script>Bad</script>','high','','');store.save_goal('career_rnd',0,'OTHER DEPARTMENT GOAL','low','','')
        self.milestone(title='<img src=x onerror=alert(1)>')
        for path in ('/department-plans/marketing','/departments/marketing','/department-plans/marketing/history'):
            out=self.client.get(path);self.assertNotIn('<script>',out.text);self.assertNotIn('<img src=x',out.text);self.assertNotIn('OTHER DEPARTMENT GOAL',out.text)
            self.assertIn("script-src 'none'",out.headers['content-security-policy'])
    def test_history_and_list_pagination(self):
        self.login()
        for i in range(52):store.save_goal('marketing',i,'Goal '+str(i),'normal','','')
        self.assertEqual(len(store.history('marketing',1)),50);self.assertEqual(len(store.history('marketing',2)),2)
        self.assertIn('Next',self.client.get('/department-plans/marketing/history').text)
        self.assertIn('Previous',self.client.get('/department-plans/marketing/history?page=2').text)
    def test_planning_database_is_included_in_existing_private_backup(self):
        self.goal()
        from superhuman.hosted.transfer import bundle
        import zipfile,sqlite3
        Path('superhuman/hosted').mkdir(parents=True)
        bundle(Path.cwd(),Path('private-backup.zip'))
        with zipfile.ZipFile('private-backup.zip') as archive:
            raw=archive.read('data/planning-test/plans.db')
        Path('restored-planning.db').write_bytes(raw)
        with sqlite3.connect('restored-planning.db') as db:
            self.assertEqual(db.execute('SELECT objective FROM department_goals').fetchone()[0],'Launch department outcome')

    def test_existing_project_and_task_records_unchanged(self):
        pid=p.create('marketing','Original project','',12);before=Path(p.DEFAULT_DB).read_bytes();self.goal();self.milestone(project_ids=[pid])
        self.assertEqual(before,Path(p.DEFAULT_DB).read_bytes());self.assertEqual(p.get(pid)['used_calls'],0)

if __name__=='__main__':unittest.main()
