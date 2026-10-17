"""Conversation presentation changes retain the governed chat contracts."""
import re,json,unittest
from uuid import uuid4
from pathlib import Path
from fastapi.testclient import TestClient
from test_milestones import MilestoneBase
from superhuman.hosted import config,auth,web
from superhuman.experience import store as ux
from superhuman.team import store as team
from superhuman.dialogue import store as dialogue
from superhuman.workspace import web as workspace
from superhuman.interface.chrome import capture
from superhuman.interface.tree import parse
from superhuman.teamspace import views
from superhuman.milestones import store as ms

class TeamspaceTests(MilestoneBase):
    def setUp(self):
        super().setUp();self.cfg=config.Settings('https://superhuman.example',state_dir=Path('state'));auth.Store(self.cfg.auth_db).setup('owner','synthetic-test-passphrase');self.client=TestClient(web.create_app(self.cfg),base_url=self.cfg.public_origin)
        self.client.post('/login',data=dict(username='owner',password='synthetic-test-passphrase',csrf=self.csrf('/login')))
    def tearDown(self):self.client.close();super().tearDown()
    def csrf(self,url):return re.search(r'name="csrf" value="([^"]+)"',self.client.get(url).text).group(1)
    def test_dark_theme_and_local_script_are_loaded(self):
        body=self.client.get('/').text;self.assertIn('/assets/teamspace.css?v=135',body);self.assertIn('/assets/teamspace.js?v=135',body);css=self.client.get('/assets/teamspace.css');self.assertEqual(css.status_code,200);self.assertIn('background:#173c30',css.text);self.assertIn('max-width:900px',css.text)
    def test_portrait_wrapper_has_no_legacy_bot_class(self):
        body=self.client.get('/team-room?tab=board').text;root=parse(body);wrappers=[n for n in root.find('span') if n.has_class('teamspace-portrait')];self.assertEqual(len(wrappers),8);self.assertFalse(any(n.has_class('ux-avatar') for n in root.find()));self.assertTrue(all(len(n.find('img'))==1 for n in wrappers));self.assertIn('width:128px',self.client.get('/assets/teamspace.css').text)
    def test_direct_message_filter_stays_scoped(self):
        ux.create('marketing','SARAH_ONLY_ROOM');ux.create('applications','JOSE_ONLY_ROOM');body=self.client.get('/team-room?employee=applications').text;self.assertIn('JOSE_ONLY_ROOM',body);self.assertNotIn('SARAH_ONLY_ROOM',body);self.assertIn('Direct messages',body)
    def test_project_channel_filters_exact_association(self):
        a=team.create_project('marketing','Project A','Outcome','Criteria');b=team.create_project('marketing','Project B','Outcome','Criteria');ux.create('marketing','ROOM_A','team',a);ux.create('marketing','ROOM_B','team',b);ux.create('marketing','UNLINKED')
        body=self.client.get('/team-room?project_kind=team&project_id='+a).text;self.assertIn('ROOM_A',body);self.assertNotIn('ROOM_B',body);self.assertNotIn('UNLINKED',body)
    def test_unknown_and_unpaired_project_filters_rejected(self):
        for url in ('/team-room?project_id=bad','/team-room?project_kind=team','/team-room?project_kind=arbitrary&project_id=bad','/team-room?employee=unknown','/team-room?page=0'):
            self.assertIn(self.client.get(url).status_code,(400,404))
    def test_single_team_navigation_row(self):
        body=self.client.get('/team-room').text;self.assertEqual(body.count('data-interface-tabs'),1);self.assertNotIn('aria-label="Section navigation"',body)
    def test_room_preserves_polling_draft_and_dictation_targets(self):
        rid=ux.create('marketing','A conversation');body=self.client.get('/team-room/'+rid).text
        for needle in ('data-room="'+rid+'"','data-transcript','data-proposals','data-chat-status','data-draft-key="'+rid+'"','data-voice','name="submission_key"','/room-controls/'+rid+'/budget'):
            self.assertIn(needle,body)
        self.assertIn('teamspace-chat-head',body);self.assertIn('/assets/agents/marketing.png',body)
    def test_all_existing_post_actions_preserved(self):
        rid=ux.create('marketing','A conversation');old=capture(workspace._v134_show_room,rid,0);new=self.client.get('/team-room/'+rid).text
        def actions(body):return {n.attrs.get('action') for n in parse(body).find('form') if n.attrs.get('method')=='post'}
        self.assertEqual(actions(old),actions(new)-{'/logout'})
    def test_room_user_content_is_escaped(self):
        rid=ux.create('marketing','<script>room()</script>');dialogue.send(rid,'<img src=https://tracker.invalid>',uuid4().hex);body=self.client.get('/team-room/'+rid).text;self.assertNotIn('<script>room()',body);self.assertNotIn('<img src=https://tracker.invalid>',body);self.assertIn('&lt;img',body)
    def test_pending_reply_still_disables_composer(self):
        rid=ux.create('marketing','A conversation');dialogue.send(rid,'Question',uuid4().hex);body=self.client.get('/team-room/'+rid).text;form=next(f for f in parse(body).find('form') if f.attrs.get('action')=='/team-room/'+rid+'/send');self.assertIn('disabled',form.find('button')[0].attrs);self.assertIn('/room-controls/'+rid+'/cancel',body)
    def test_send_requires_csrf_and_queues_one_reply(self):
        rid=ux.create('marketing','A conversation');url='/team-room/'+rid+'/send';payload=dict(message='Question',submission_key=uuid4().hex)
        self.assertEqual(self.client.post(url,data=payload).status_code,403);payload['csrf']=self.csrf('/team-room/'+rid);r=self.client.post(url,data=payload,follow_redirects=False);self.assertEqual(r.status_code,303);self.assertEqual(len(dialogue.turns(rid)),1)
    def test_assets_remain_private(self):
        client=TestClient(web.create_app(self.cfg),base_url=self.cfg.public_origin)
        for path in ('/assets/teamspace.css','/assets/teamspace.js'):
            self.assertIn(client.get(path,follow_redirects=False).status_code,(303,401))
    def test_search_and_pagination_cover_full_history(self):
        for n in range(34):ux.create('marketing','Room '+str(n))
        self.assertIn('Next page',self.client.get('/team-room?employee=marketing').text);body=self.client.get('/team-room?employee=marketing&q=Room+0').text;listing=next(n for n in parse(body).find('div') if n.has_class('teamspace-conversation-list')).text();self.assertIn('Room 0',listing);self.assertNotIn('Room 33',listing)
    def test_read_only_rendering_does_not_start_work(self):
        rid=ux.create('marketing','A conversation');before=(len(team.tasks()),dialogue.get(rid)['used_calls'],len(dialogue.turns(rid)))
        for url in ('/team-room','/team-room?tab=board','/team-room?tab=feed','/team-room/'+rid):self.assertEqual(self.client.get(url).status_code,200)
        self.assertEqual(before,(len(team.tasks()),dialogue.get(rid)['used_calls'],len(dialogue.turns(rid))))
    def test_reply_budget_and_correction_controls_remain(self):
        rid=ux.create('marketing','A conversation');body=self.client.get('/team-room/'+rid).text;self.assertIn('Total reply allowance',body);self.assertIn('/room-controls/'+rid+'/budget',body);self.assertIn('Conversation controls',body)
    def test_room_history_anchor_preserved(self):
        rid=ux.create('marketing','History');body=self.client.get('/team-room/'+rid+'?before=1').text;self.assertIn('data-before="1"',body);self.assertIn('Latest messages',body)
    def test_initial_list_does_not_create_a_room(self):
        before=len(ux.rooms());self.client.get('/team-room?employee=twin');self.assertEqual(before,len(ux.rooms()))
    def test_project_creation_does_not_invent_milestones(self):
        pid=team.create_project('marketing','New work','Outcome','Criteria');self.assertEqual(ms.listing(pid),[]);self.assertIsNone(ms.managed(pid))
    def test_activity_reuses_recorded_feed_in_workspace(self):
        body=self.client.get('/team-room?tab=feed').text;self.assertIn('teamspace-activity',body);self.assertIn('Recorded team exchanges',body);self.assertIn('No recorded employee exchanges yet',body)
