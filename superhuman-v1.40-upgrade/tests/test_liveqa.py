"""v1.37 live findings: real scoped records and HTTP transitions, synthetic providers."""
import json,re,time
from pathlib import Path
from uuid import uuid4
from fastapi.testclient import TestClient
from test_teamhub import HubBase
from superhuman.projects import engine as p
from superhuman.team import store as team,budget
from superhuman.teamhub import store as s,engine as hub
from superhuman.teamhub.readiness import discussion
from superhuman.teamhub.project import section,rooms
from superhuman.milestones import store as ms
from superhuman.hosted import web,config,auth,jobs
from superhuman.experience import store as ux
from superhuman.interface.tree import parse


class DispatchReadinessTests(HubBase):
    def send(self,tid):return s.send(tid,'QA-CEDAR-417 local question','direct','marketing',uuid4().hex)
    def assert_no_enqueue(self,tid,reason):
        before={table:s.read('SELECT * FROM '+table) for table in ['hub_rounds','hub_steps','dialogue_turns','team_costs','team_events']}
        with self.assertRaisesRegex(ValueError,reason):self.send(tid)
        for table,value in before.items():self.assertEqual(s.read('SELECT * FROM '+table),value,table)
    def test_disabled_team_rejects_without_enqueue_or_spend(self):
        *_,tid=self.channel();team.configure(team.settings()['version'],False,team.settings()['model']);self.assert_no_enqueue(tid,'disabled')
    def test_team_hold_rejects_without_enqueue_or_spend(self):
        *_,tid=self.channel()
        with p.connect() as db:db.execute("UPDATE team_settings SET hold='Owner inspection'")
        self.assert_no_enqueue(tid,'held for inspection')
    def test_paused_worker_rejects_without_enqueue_or_spend(self):
        *_,tid=self.channel();jobs.pause(True);self.assert_no_enqueue(tid,'worker is paused')
    def test_paused_project_rejects_without_enqueue_or_spend(self):
        pid,_,_,tid=self.channel();q=team.project(pid);team.update_project(pid,q['version'],q['priority'],q['risk'],q['sensitivity'],'paused');self.assert_no_enqueue(tid,'paused or complete')
    def test_expired_budget_rejects_without_enqueue_or_spend(self):
        *_,tid=self.channel()
        with p.connect() as db:db.execute('UPDATE team_budget_periods SET end=?',(time.time()-1,))
        self.assert_no_enqueue(tid,'active dollar budget')
    def test_unconfirmed_model_rate_rejects_without_enqueue(self):
        *_,tid=self.channel()
        with p.connect() as db:db.execute('DELETE FROM team_rates')
        self.assert_no_enqueue(tid,'confirmed model rates')
    def test_paused_recipient_rejects_without_enqueue(self):
        *_,tid=self.channel()
        with p.connect() as db:db.execute("UPDATE team_employees SET paused=1 WHERE id='marketing'")
        self.assert_no_enqueue(tid,'Sarah is paused')
    def test_idempotent_existing_submission_is_not_queued_again_after_disable(self):
        *_,tid=self.channel();key=uuid4().hex;rid=s.send(tid,'Same question','direct','marketing',key)
        team.configure(team.settings()['version'],False,team.settings()['model'])
        self.assertEqual(s.send(tid,'Same question','direct','marketing',key),rid);self.assertEqual(len(s.read('SELECT * FROM hub_rounds')),1)
    def test_project_milestone_dispatch_pause_does_not_prevent_authorized_discussion(self):
        pid,_,cid,tid=self.channel();ms.configure(pid,ms.managed(pid)['version'],False,True)
        self.assertTrue(discussion(cid)['ready']);rid=self.send(tid);hub.advance();self.assertEqual(self.reply()['status'],'done');hub.advance();self.assertEqual(s.round_(rid)['status'],'done')
    def test_recheck_in_same_transaction_observes_new_hold(self):
        from superhuman.teamhub.readiness import require
        *_,cid,_=self.channel()
        with p.connect() as db:
            db.execute('BEGIN IMMEDIATE');db.execute("UPDATE team_settings SET hold='Concurrent owner hold'")
            with self.assertRaisesRegex(ValueError,'held'):require(cid,db=db)
    def test_revoked_sharing_blocks_new_send(self):
        pid,_,_,tid=self.channel();ms.configure(pid,ms.managed(pid)['version'],False,False);self.assert_no_enqueue(tid,'sharing agreement')
    def test_project_rooms_do_not_duplicate_channel_worker_conversations(self):
        pid,_,_,tid=self.channel();room=ux.create('marketing','Standalone project chat','team',pid)
        self.complete_direct(tid);self.assertEqual([r['id'] for r in rooms(pid)],[room])
    def test_channel_and_topics_exclude_foreign_project_and_escape_titles(self):
        pid,mid,cid,tid=self.channel();other,_,foreign_cid,_=self.channel()
        with p.connect() as db:db.execute('UPDATE hub_topics SET title=? WHERE id=?',('<script>not markup</script>',tid))
        result=section(pid);self.assertIn(cid,result)
        self.assertIn('&lt;script&gt;',result);self.assertNotIn('<script>',result);self.assertNotIn(foreign_cid,result)
        self.assertFalse(section(pid,kind='canonical'));self.assertNotEqual(pid,other)


class LiveQAHTTPTests(HubBase):
    def setUp(self):
        super().setUp();self.cfg=config.Settings('https://superhuman.example',state_dir=Path('state'));auth.Store(self.cfg.auth_db).setup('owner','synthetic-test-passphrase');self.client=TestClient(web.create_app(self.cfg),base_url=self.cfg.public_origin);self.client.post('/login',data={'username':'owner','password':'synthetic-test-passphrase','csrf':self.csrf('/login')})
    def tearDown(self):self.client.close();super().tearDown()
    def csrf(self,url):return re.search(r'name="csrf" value="([^"]+)"',self.client.get(url).text).group(1)
    def test_project_tab_and_all_rooms_show_same_channel_and_scoped_topics(self):
        pid,mid,cid,tid=self.channel();foreign,_,fcid,ftid=self.channel()
        for url in ['/project-hub/'+pid+'?view=conversations','/project-rooms/'+pid]:
            body=self.client.get(url).text;self.assertIn('channel='+cid,body);self.assertIn('topic='+tid,body);self.assertNotIn('channel='+fcid,body);self.assertNotIn('topic='+ftid,body);self.assertNotIn('No project conversations yet',body)
    def test_archived_channel_history_is_visible_in_own_project(self):
        pid,_,cid,tid=self.channel();c=s.channel(cid);s.channel_control(cid,c['version'],c['title'],json.loads(c['members']),True,False,40)
        body=self.client.get('/project-hub/'+pid+'?view=conversations').text;self.assertIn('Archived channel',body);self.assertIn('topic='+tid,body)
    def test_project_conversation_keeps_approved_specialist_selector_and_handler(self):
        pid,_,_,_=self.channel();url='/project-hub/'+pid+'?view=conversations';tree=parse(self.client.get(url).text)
        form=next(f for f in tree.find('form') if f.attrs.get('action')=='/project-hub/'+pid+'/room')
        selector=next(n for n in form.find('select') if n.attrs.get('name')=='employee')
        self.assertEqual({n.attrs['value'] for n in selector.find('option')},{'marketing','career_rnd','twin'})
        result=self.client.post('/project-hub/'+pid+'/room',data=dict(employee='career_rnd',title='QA approved specialist room',csrf=self.csrf(url)),follow_redirects=False)
        self.assertEqual(result.status_code,303);room=ux.room(result.headers['location'].split('/')[-1]);self.assertEqual(room['employee'],'career_rnd');self.assertEqual(room['project_id'],pid);self.assertFalse(budget.report()['costs'])
    def test_project_room_pagination_reaches_earlier_saved_history(self):
        pid,_,_,_=self.channel();identifiers=[ux.create('marketing','QA room '+str(i),'team',pid) for i in range(32)]
        first=self.client.get('/project-rooms/'+pid+'?page=1').text;second=self.client.get('/project-rooms/'+pid+'?page=2').text
        self.assertIn('/team-room/'+identifiers[-1],first);self.assertNotIn('/team-room/'+identifiers[0],first)
        self.assertIn('/team-room/'+identifiers[0],second);self.assertNotIn('/team-room/'+identifiers[-1],second)
        self.assertEqual(self.client.get('/project-rooms/'+pid+'?page=0').status_code,400)
    def test_disabled_composer_explains_block_and_server_does_not_enqueue(self):
        *_,tid=self.channel();team.configure(team.settings()['version'],False,team.settings()['model']);url='/team-hub?topic='+tid
        body=self.client.get(url).text;tree=parse(body);form=next(f for f in tree.find('form') if f.attrs.get('action')=='/team-hub/topics/'+tid+'/send')
        self.assertIn('disabled',form.find('button')[-1].attrs);self.assertIn('Team coordination is disabled',body);self.assertIn('discussion-readiness',form.attrs['aria-describedby'])
        response=self.client.post('/team-hub/topics/'+tid+'/send',data=dict(message='Not queued',target='team',submission_key=uuid4().hex,csrf=self.csrf(url)))
        self.assertEqual(response.status_code,409);self.assertIn('Return to the discussion',response.text);self.assertFalse(s.read('SELECT * FROM hub_rounds'));self.assertFalse(budget.report()['costs'])
    def test_historical_queued_message_shows_waiting_and_cancellation_remains(self):
        *_,tid=self.channel();rid=s.send(tid,'Queued before disabling','direct','marketing',uuid4().hex);team.configure(team.settings()['version'],False,team.settings()['model']);url='/team-hub?topic='+tid
        body=self.client.get(url).text;self.assertIn('Waiting for activation / controls',body);self.assertIn('Cancel queued discussion',body)
        result=self.client.post('/team-hub/rounds/'+rid+'/cancel',data={'csrf':self.csrf(url)});self.assertEqual(result.status_code,200);self.assertEqual(s.round_(rid)['status'],'cancelled')
    def test_retry_cannot_queue_while_disabled(self):
        *_,tid=self.channel();rid=s.send(tid,'Original','direct','marketing',uuid4().hex);s.cancel(rid);team.configure(team.settings()['version'],False,team.settings()['model']);url='/team-hub?topic='+tid
        result=self.client.post('/team-hub/rounds/'+rid+'/retry',data=dict(submission_key=uuid4().hex,csrf=self.csrf(url)))
        self.assertEqual(result.status_code,409);self.assertEqual(len(s.read('SELECT * FROM hub_rounds')),1)
    def test_readiness_render_creates_no_model_jobs_or_costs(self):
        *_,tid=self.channel();before={table:s.read('SELECT * FROM '+table) for table in ['hub_rounds','hub_steps','dialogue_turns','team_costs']}
        self.assertEqual(self.client.get('/team-hub?topic='+tid).status_code,200)
        for table,value in before.items():self.assertEqual(s.read('SELECT * FROM '+table),value)
    def test_all_employee_surfaces_distinguish_blocked_work(self):
        team.configure(team.settings()['version'],False,team.settings()['model'])
        for url in ['/system-baseline','/team/employees/marketing','/team-hub?view=employees&employee=twin']:
            body=self.client.get(url).text;self.assertIn('Work blocked',body);self.assertNotIn('available under current controls',body);self.assertNotIn(' · Available',body)
    def test_complete_filter_combines_team_and_canonical_states_and_old_bookmark(self):
        pid,_=self.project();q=team.project(pid);team.update_project(pid,q['version'],q['priority'],q['risk'],q['sensitivity'],'complete')
        old=p.create('marketing','QA earlier completed','Local test')
        with p.connect() as db:db.execute("UPDATE projects SET status='approved' WHERE id=?",(old,))
        for value in ['complete','approved']:
            body=self.client.get('/projects?state='+value).text;tree=parse(body)
            status=next(n for n in tree.find('select') if n.attrs.get('name')=='state');self.assertEqual(sum(n.text()=='Complete' for n in status.find('option')),1)
            self.assertIn('QA earlier completed',body);self.assertIn(q['title'],body)
    def test_existing_task_conversion_remains_non_destructive_and_linked(self):
        pid=team.create_project('marketing','QA task-first','Local test','Checked result');tid=team.create_task(pid,'marketing','Keep this task','Local instructions','Evidence');before=team.task(tid)
        response=self.client.post('/project-leadership/attach',data=dict(project_id=pid,csrf=self.csrf('/projects')))
        self.assertEqual(response.status_code,200);self.assertIn('/team/tasks/'+tid,response.text);self.assertEqual(team.task(tid),before);self.assertIsNone(ms.managed(pid))
