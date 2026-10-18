"""Team integration with synthetic data and metered mock model responses."""
import json,re,unittest
from pathlib import Path
from uuid import uuid4
from fastapi.testclient import TestClient
from test_milestones import MilestoneBase
from test_team import Metered
from superhuman.hosted import web,config,auth,jobs
from superhuman.team import store as team
from superhuman.projects import engine as p
from superhuman.dialogue import store as d,engine as de
from superhuman.experience import store as ux
from superhuman.milestones import store as ms
from superhuman.foundation import storage
from superhuman.capabilities import local
from superhuman.teamhub import store as s,engine as e,context as ctx,cards

class HubBase(MilestoneBase):
    def setUp(self):super().setUp();s.initialize()
    def channel(self,workers=None):
        pid,mid=self.project(workers=workers or ['marketing','career_rnd']);cid=s.create_channel(pid,'Product evidence',['marketing','career_rnd','twin']);tid=s.create_topic(cid,'Validation discussion',mid);return pid,mid,cid,tid
    def reply(self,text='A supported discussion response',requests=None,tasks=None):
        value={'reply':text,'tasks':tasks or []}
        if requests is not None:value['requests']=requests
        return de.run_turn(client=Metered(value))
    def complete_direct(self,tid):
        rid=s.send(tid,'Review the evidence','direct','marketing',uuid4().hex);e.advance();self.assertEqual(self.reply()['status'],'done');e.advance();return rid
    def card(self,managed=False):
        if managed:
            pid,mid=self.project();self.start(mid)
        else:pid=team.create_project('marketing','Card project','O','C');mid=''
        room=ux.create('marketing','Discuss work','team',pid);d.send(room,'Suggest a useful bounded task',uuid4().hex)
        self.reply(tasks=[dict(kind='collab',title='Draft evidence summary',details='Draft a local source-backed summary. No external actions.',rationale='Useful first deliverable')]);cards.sync();card=s.one('SELECT * FROM hub_cards WHERE room_id=?',(room,));return pid,mid,room,card

class HubConversationTests(HubBase):
    def test_primary_dm_is_stable_and_preserves_existing_history(self):
        rid=ux.create('marketing','Earlier Sarah chat');d.send(rid,'Original question',uuid4().hex);self.reply()
        self.assertEqual(s.primary('marketing'),rid);self.assertEqual(s.primary('marketing'),rid);self.assertEqual(len(d.turns(rid)),1)
    def test_get_read_does_not_mark_seen_or_create_primary(self):
        rid=ux.create('marketing','History');before=s.read('SELECT * FROM hub_primary');s.rooms();s.state(rid);self.assertEqual(before,s.read('SELECT * FROM hub_primary'))
    def test_rename_archive_pin_and_stale_version(self):
        rid=s.primary('marketing');s.room_control(rid,0,'Renamed',True,True,'Founder confirmed constraint');self.assertEqual(d.get(rid)['title'],'Renamed');self.assertEqual(s.rooms(archived=True)[0]['id'],rid)
        with self.assertRaises(ValueError):d.send(rid,'Not authorized while archived',uuid4().hex)
        with self.assertRaises(ValueError):s.room_control(rid,1,'Stale',False,False,'')
    def test_pending_reply_cannot_be_archived(self):
        rid=s.primary('marketing');d.send(rid,'Pending',uuid4().hex)
        with self.assertRaises(ValueError):s.room_control(rid,0,'Title',True,False,'')
    def test_message_body_search_and_exact_project_filter(self):
        a=team.create_project('marketing','A','O','C');b=team.create_project('marketing','B','O','C');rid=ux.create('marketing','Ordinary title','team',a);ux.create('marketing','Other room','team',b);d.send(rid,'Distinctive needle in message',uuid4().hex);self.reply('Reply with another phrase')
        self.assertEqual([x['id'] for x in s.rooms(q='needle',project_id=a)],[rid]);self.assertFalse(s.rooms(q='needle',project_id=b));self.assertEqual(s.rooms(q='another phrase')[0]['id'],rid)
    def test_read_marker_refuses_unseen_new_reply(self):
        rid=s.primary('marketing');sig=s.room_signature(rid);d.send(rid,'Question',uuid4().hex);self.reply()
        with self.assertRaises(ValueError):s.mark_room(rid,sig)
        sig=s.room_signature(rid);s.mark_room(rid,sig);self.assertEqual(s.state(rid)['seen'],sig)
    def test_channel_requires_real_approved_roster(self):
        pid,mid=self.project()
        with self.assertRaises(ValueError):s.create_channel(pid,'Wrong',['marketing','legal_ops'])
        ms.configure(pid,ms.managed(pid)['version'],False,False)
        with self.assertRaises(ValueError):s.create_channel(pid,'Unshared',['marketing'])
    def test_project_has_one_channel_and_topic_is_project_scoped(self):
        pid,mid,cid,tid=self.channel();other,foreign=self.project()
        with self.assertRaises(ValueError):s.create_channel(pid,'Duplicate',['marketing'])
        with self.assertRaises(ValueError):s.create_topic(cid,'Foreign milestone',foreign)
    def test_unauthorized_direct_participant_rejected(self):
        *_,tid=self.channel()
        with self.assertRaises(ValueError):s.send(tid,'Secret','direct','legal_ops',uuid4().hex)
    def test_shared_direct_reply_is_real_persisted_and_hidden_from_legacy_lists(self):
        pid,mid,cid,tid=self.channel();rid=self.complete_direct(tid);step=s.steps(rid)[0];self.assertEqual(step['employee'],'marketing');self.assertEqual(step['reply'],'A supported discussion response');self.assertFalse(any(x['id']==step['thread_id'] for x in s.rooms()))
    def test_team_discussion_routes_contribution_then_lead_synthesis(self):
        pid,mid,cid,tid=self.channel();rid=s.send(tid,'Evaluate positioning','team','',uuid4().hex);e.advance();self.assertEqual(self.reply('I will obtain Amelia’s evidence.',requests=[dict(employee='career_rnd',question='Identify validation limitations')])['status'],'done');e.advance();self.assertEqual(s.steps(rid)[-1]['employee'],'career_rnd');self.assertEqual(self.reply('Actual specialist contribution')['status'],'done');e.advance();self.assertEqual(s.steps(rid)[-1]['stage'],'synthesis');self.assertEqual(self.reply('Integrated finding and remaining uncertainty')['status'],'done');e.advance();self.assertEqual(s.round_(rid)['status'],'done');self.assertEqual(len(s.steps(rid)),3)
    def test_lead_can_answer_without_calling_other_employees(self):
        *_,tid=self.channel();rid=s.send(tid,'Simple question','team','',uuid4().hex);e.advance();self.assertEqual(self.reply(requests=[])['status'],'done');e.advance();self.assertEqual(s.round_(rid)['status'],'done');self.assertEqual(len(s.steps(rid)),1)
    def test_lead_cannot_request_unapproved_or_duplicate_employees(self):
        *_,tid=self.channel();rid=s.send(tid,'Question','team','',uuid4().hex);e.advance();result=self.reply(requests=[dict(employee='legal_ops',question='Unapproved')]);self.assertEqual(result['status'],'failed');e.advance();self.assertEqual(s.round_(rid)['status'],'failed');self.assertEqual(len(s.steps(rid)),1)
    def test_pause_and_roster_revocation_prevent_model_call(self):
        pid,mid,cid,tid=self.channel();rid=s.send(tid,'Question','direct','marketing',uuid4().hex);e.advance();ms.configure(pid,ms.managed(pid)['version'],False,False);result=self.reply();self.assertEqual(result['status'],'failed');self.assertIsNone(s.steps(rid)[0]['reply'])
    def test_channel_budget_caps_all_steps_across_topics(self):
        pid,mid,cid,tid=self.channel()
        with p.connect() as db:db.execute('UPDATE hub_channels SET max_calls=1 WHERE id=?',(cid,))
        self.complete_direct(tid);before=len(s.read('SELECT * FROM hub_rounds'))
        with self.assertRaisesRegex(ValueError,'allowance'):s.send(tid,'Second question','direct','marketing',uuid4().hex)
        self.assertEqual(len(s.read('SELECT * FROM hub_rounds')),before)
    def test_cancel_and_idempotent_send(self):
        *_,tid=self.channel();key=uuid4().hex;rid=s.send(tid,'Q','direct','marketing',key);self.assertEqual(s.send(tid,'Q','direct','marketing',key),rid);s.cancel(rid);e.advance();self.assertFalse(s.steps(rid))
        with self.assertRaises(ValueError):s.send(tid,'Different','direct','marketing',key)
    def test_recovery_never_replays_interrupted_contribution(self):
        *_,tid=self.channel();rid=s.send(tid,'Q','direct','marketing',uuid4().hex);e.advance();d.claim();d.recover_running();e.advance();self.assertEqual(s.round_(rid)['status'],'failed');self.assertEqual(len(s.steps(rid)),1)
    def test_topic_context_visible_in_exact_reply_trace(self):
        pid,mid,cid,tid=self.channel();s.save_note(tid,1,'Owner-confirmed positioning constraint');rid=self.complete_direct(tid);trace=json.loads(d.turn(s.steps(rid)[0]['turn_id'])['context_json']);self.assertEqual(trace['hub_context_visible']['confirmed_context'],'Owner-confirmed positioning constraint');self.assertTrue(trace['hub_context_visible']['history_is_bounded'])
    def test_confirmed_context_change_invalidates_pending_snapshot(self):
        *_,tid=self.channel();s.send(tid,'Q','direct','marketing',uuid4().hex);e.advance();claimed=d.claim();messages,trace=de.prompt(claimed);s.save_note(tid,1,'Changed by owner')
        with self.assertRaises(ValueError):ctx.validate(claimed,trace)
    def test_linked_documents_require_all_participants_and_current_version(self):
        pid,mid,cid,tid=self.channel();local.store_bytes('marketing','reference.txt',b'Document excerpt with sources');item=storage.save('marketing','document','Reference',filename='reference.txt',project_kind='team',project_id=pid,sensitivity='internal',source='Owner supplied',status='approved')
        with self.assertRaises(ValueError):s.link_file(tid,item)
        r=storage.get(item);storage.save('marketing','document','Reference',filename='reference.txt',project_kind='team',project_id=pid,sensitivity='internal',source='Owner supplied',status='approved',access=['career_rnd','twin'],ident=item,expected=r['version']);s.link_file(tid,item);self.assertIn('Document excerpt',s.document_context(tid,'marketing',pid,'internal')[0]['excerpt']);r=storage.get(item);storage.save('marketing','document','Reference',filename='reference.txt',project_kind='team',project_id=pid,sensitivity='internal',source='Owner supplied',status='archived',access=['career_rnd','twin'],ident=item,expected=r['version'])
        with self.assertRaises(ValueError):s.document_context(tid,'marketing',pid,'internal')
    def test_foreign_project_document_cannot_be_linked(self):
        pid,mid,cid,tid=self.channel();other,_=self.project();item=storage.save('marketing','fact','Other project',content='Private project fact',fact_key='other.fact',project_kind='team',project_id=other,source='Owner supplied',sensitivity='internal',access=['career_rnd','twin'],status='approved')
        with self.assertRaises(ValueError):s.link_file(tid,item)

class HubCardTests(HubBase):
    def test_owner_authorization_creates_exact_task_once(self):
        pid,mid,room,card=self.card();tid=cards.authorize(card['id'],card['version'],'Approved exact scope');self.assertEqual(team.task(tid)['instruction'],card['instruction']);self.assertEqual(team.task(tid)['state'],'ready')
        with self.assertRaises(ValueError):cards.authorize(card['id'],card['version'],'Duplicate')
        self.assertEqual(len(team.tasks()),1)
    def test_twin_can_independently_authorize_routine_internal_card(self):
        pid,mid,room,card=self.card();cards.request_review(card['id'],card['version']);self.assertEqual(de.run_turn(client=Metered({'decision':'authorize','note':'Routine internal draft within existing project.'}))['status'],'done');cards.reconcile();card=cards.get(card['id']);self.assertEqual(card['status'],'authorized');self.assertTrue(card['task_id']);self.assertEqual(team.task(card['task_id'])['state'],'queued')
    def test_twin_revision_returns_card_without_creating_work(self):
        *_,card=self.card();cards.request_review(card['id'],card['version']);de.run_turn(client=Metered({'decision':'revise','note':'Need explicit success criteria.'}));cards.reconcile();self.assertEqual(cards.get(card['id'])['status'],'revision');self.assertFalse(team.tasks())
    def test_twin_cannot_self_approve_own_proposal(self):
        pid,mid,room,card=self.card()
        with p.connect() as db:db.execute("UPDATE ux_rooms SET employee='twin' WHERE thread_id=?",(room,))
        with self.assertRaises(ValueError):cards.request_review(card['id'],card['version'])
    def test_consequential_work_requires_owner(self):
        pid,mid,room,card=self.card();cards.edit(card['id'],card['version'],card['title'],card['instruction'],card['criteria'],'marketing','','consequential','confidential','',False);card=cards.get(card['id'])
        with self.assertRaises(ValueError):cards.request_review(card['id'],card['version'])
    def test_card_cannot_lower_project_controls_or_private_sharing_without_confirmation(self):
        *_,card=self.card()
        with self.assertRaises(ValueError):cards.edit(card['id'],card['version'],card['title'],card['instruction'],card['criteria'],'marketing','','routine','internal','',False)
    def test_existing_dialogue_approval_reconciles_without_duplicate_task(self):
        pid,mid,room,card=self.card();from superhuman.workspace.chat import approve
        v=d.suggestions(room)[0];tid=approve(v['id'],v['proposal_hash'],pid,v['title'],v['details'],'routine','confidential','Reviewable output');cards.reconcile();self.assertEqual(cards.get(card['id'])['task_id'],tid);self.assertEqual(len(team.tasks()),1)
    def test_managed_work_must_enter_existing_working_milestone(self):
        pid,mid,room,card=self.card(True)
        with self.assertRaises(ValueError):cards.authorize(card['id'],card['version'],'No milestone selected')
        cards.edit(card['id'],card['version'],card['title'],card['instruction'],card['criteria'],'marketing','','routine','confidential',mid,False);card=cards.get(card['id']);tid=cards.authorize(card['id'],card['version'],'Approved bounded contribution');self.assertEqual(ms.assignment(tid)['milestone_id'],mid)
    def test_changed_card_during_review_is_rejected(self):
        *_,card=self.card();cards.request_review(card['id'],card['version']);card=cards.get(card['id'])
        with self.assertRaises(ValueError):cards.edit(card['id'],card['version'],card['title'],'Changed',card['criteria'],'marketing','','routine','confidential','',False)
    def test_rollback_quarantines_channel_calls_and_preserves_completed_rows(self):
        *_,tid=self.channel();done=self.complete_direct(tid);pending=s.send(tid,'Queued next','direct','marketing',uuid4().hex);e.advance();e.quarantine();self.assertEqual(s.round_(pending)['status'],'cancelled');self.assertEqual(s.round_(done)['status'],'done');self.assertEqual(s.steps(done)[0]['status'],'done')

class HubWebTests(HubBase):
    def setUp(self):
        super().setUp();self.cfg=config.Settings('https://superhuman.example',state_dir=Path('state'));auth.Store(self.cfg.auth_db).setup('owner','synthetic-test-passphrase');self.client=TestClient(web.create_app(self.cfg),base_url=self.cfg.public_origin);self.client.post('/login',data={'username':'owner','password':'synthetic-test-passphrase','csrf':self.csrf('/login')})
    def tearDown(self):self.client.close();super().tearDown()
    def csrf(self,url):return re.search(r'name="csrf" value="([^"]+)"',self.client.get(url).text).group(1)
    def test_balanced_layout_assets_and_eight_people(self):
        body=self.client.get('/team-hub').text;self.assertIn('hub-layout',body);self.assertIn('Your eight AI employees',body);self.assertIn('/assets/teamhub.css?v=137',body);self.assertIn('Direct messages',body);self.assertIn('Needs your attention',body)
    def test_primary_direct_message_requires_post_csrf(self):
        self.assertEqual(self.client.post('/team-hub/direct/marketing').status_code,403);r=self.client.post('/team-hub/direct/marketing',data={'csrf':self.csrf('/team-hub')},follow_redirects=False);self.assertEqual(r.status_code,303);self.assertIn('/team-room/',r.headers['location'])
    def test_channel_creation_and_rendering_no_model_calls(self):
        pid,mid,cid,tid=self.channel();before=len(s.read('SELECT * FROM dialogue_turns'));r=self.client.get('/team-hub?topic='+tid);self.assertEqual(r.status_code,200);self.assertIn('Team discussion',r.text);self.assertIn('Working context',r.text);self.assertEqual(len(s.read('SELECT * FROM dialogue_turns')),before)
    def test_all_views_and_native_forms_render(self):
        for path in ('/team-hub','/team-hub?view=employees','/team-hub?view=employees&employee=twin','/team-hub?view=attention','/team-hub?view=activity','/team-hub?view=archive','/team-hub?view=new','/team-hub?view=twin'):
            with self.subTest(path=path):self.assertEqual(self.client.get(path).status_code,200)
    def test_body_search_opens_exact_message_anchor(self):
        room=s.primary('marketing');turn=d.send(room,'Distinctive search evidence',uuid4().hex);self.reply();body=self.client.get('/team-hub?q=Distinctive').text;self.assertIn('#turn-'+turn,body);self.assertIn('before=2',body);self.assertIn('id="turn-'+turn+'"',self.client.get('/team-room/'+room+'?before=2').text)
    def test_room_retains_old_controls_and_shows_context(self):
        room=s.primary('marketing');body=self.client.get('/team-room/'+room).text
        for needle in ('data-room','data-transcript','data-proposals','data-voice','data-draft-key','Working context','Conversation settings','/room-controls/'+room+'/budget'):self.assertIn(needle,body)
    def test_owner_content_is_escaped(self):
        *_,tid=self.channel();s.send(tid,'<script>unsafe()</script>','direct','marketing',uuid4().hex);body=self.client.get('/team-hub?topic='+tid).text;self.assertNotIn('<script>unsafe()',body);self.assertIn('&lt;script&gt;',body)
    def test_upload_is_draft_and_keeps_project_tags_and_privacy(self):
        pid,mid,cid,tid=self.channel();r=self.client.post('/team-hub/documents/upload',data={'target':tid,'csrf':self.csrf('/team-hub?topic='+tid)},files={'file':('source.txt',b'Owner source','text/plain')},follow_redirects=False);self.assertEqual(r.status_code,303);item=storage.rows()[0];self.assertEqual(item['project_id'],pid);self.assertEqual(item['status'],'draft');self.assertEqual(item['sensitivity'],'confidential');self.assertFalse(s.read('SELECT * FROM hub_links'))
    def test_new_assets_remain_authenticated(self):
        client=TestClient(web.create_app(self.cfg),base_url=self.cfg.public_origin)
        for path in ('/team-hub','/assets/teamhub.css','/assets/teamhub.js'):self.assertIn(client.get(path,follow_redirects=False).status_code,(303,401))
        client.close()
    def test_malicious_search_and_invalid_filters_rejected_or_escaped(self):
        body=self.client.get('/team-hub?q=%3Cscript%3E').text;self.assertNotIn('value="<script>"',body)
        for url in ('/team-hub?employee=invalid','/team-hub?page=0','/team-hub?day_from=invalid','/team-hub?view=invalid'):self.assertEqual(self.client.get(url).status_code,409)

if __name__=='__main__':unittest.main()

class HubAdditionalTests(HubBase):
    def test_two_specialists_have_four_call_ceiling(self):
        pid,mid=self.project(workers=['marketing','career_rnd','edsync_product']);cid=s.create_channel(pid,'Full team',['marketing','career_rnd','edsync_product','twin']);tid=s.create_topic(cid,'Question');rid=s.send(tid,'Q','team','',uuid4().hex);e.advance();self.reply(requests=[dict(employee='career_rnd',question='Evidence'),dict(employee='edsync_product',question='Product')]);e.advance();self.reply('Amelia actual reply');e.advance();self.reply('James actual reply');e.advance();self.reply('Sarah integrates both');e.advance();self.assertEqual(len(s.steps(rid)),4);self.assertEqual(s.round_(rid)['status'],'done')
    def test_more_than_two_requested_specialists_rejected(self):
        *_,tid=self.channel();rid=s.send(tid,'Q','team','',uuid4().hex);e.advance();self.assertEqual(self.reply(requests=[dict(employee='career_rnd',question='Evidence')]*3)['status'],'failed');e.advance();self.assertEqual(len(s.steps(rid)),1)
    def test_shared_source_selection_excludes_agent_private_document(self):
        pid,mid,cid,tid=self.channel();item=storage.save('marketing','fact','Private positioning',content='PrivateOnlySecretEvidence',fact_key='private.value',project_kind='team',project_id=pid,sensitivity='internal',source='Owner',status='approved');s.send(tid,'Private positioning','direct','marketing',uuid4().hex);e.advance();claimed=d.claim();messages,trace=de.prompt(claimed);self.assertNotIn('PrivateOnlySecretEvidence',json.dumps(messages));self.assertNotIn(item,json.dumps(trace.get('foundation',{})))
    def test_full_text_topic_search_returns_real_thread(self):
        *_,tid=self.channel();rid=s.send(tid,'Specialized validation question','direct','marketing',uuid4().hex);e.advance();self.reply('UniqueSpecialistEvidence');e.advance();self.assertEqual(s.topic_search(q='UniqueSpecialistEvidence')[0]['id'],tid);self.assertFalse(s.topic_search(q='Not present'))
    def test_channel_changes_preserve_history_and_archive(self):
        pid,mid,cid,tid=self.channel();rid=self.complete_direct(tid);c=s.channel(cid);s.channel_control(cid,c['version'],'New name',['marketing','career_rnd','twin'],True,True,40);self.assertEqual(s.steps(rid)[0]['reply'],'A supported discussion response')
        with self.assertRaises(ValueError):s.send(tid,'Archived','direct','marketing',uuid4().hex)
    def test_opt_in_delegation_requests_one_review_then_stops_for_revision(self):
        pid,mid,cid,tid=self.channel();c=s.channel(cid);s.channel_control(cid,c['version'],c['title'],json.loads(c['members']),False,False,40,delegated=True);rid=s.send(tid,'Propose a draft','direct','marketing',uuid4().hex);e.advance();self.reply(tasks=[dict(kind='collab',title='Draft local evidence summary',details='Produce a local draft with cited sources.',rationale='Useful output')]);cards.reconcile();card=s.one('SELECT * FROM hub_cards WHERE topic_id=?',(tid,));self.assertEqual(card['status'],'twin_review');self.assertEqual(de.run_turn(client=Metered({'decision':'revise','note':'Need clearer outcome.'}))['status'],'done');cards.reconcile();cards.reconcile();self.assertEqual(cards.get(card['id'])['status'],'revision');self.assertEqual(s.one('SELECT COUNT(*) AS n FROM hub_card_review_history')['n'],1)
    def test_twin_review_lifetime_attempt_limit_is_two(self):
        *_,card=self.card()
        for attempt in range(2):
            card=cards.get(card['id']);cards.request_review(card['id'],card['version']);self.assertEqual(de.run_turn(client=Metered({'decision':'revise','note':'Need owner clarification.'}))['status'],'done');cards.reconcile()
        card=cards.get(card['id'])
        with self.assertRaises(ValueError):cards.request_review(card['id'],card['version'])
    def test_direct_twin_can_link_explicitly_approved_private_document(self):
        room=s.primary('twin');item=storage.save('global','fact','Personal constraint',content='Owner private scheduling limit',fact_key='owner.limit',sensitivity='restricted',access=['twin'],source='Owner',status='approved');s.link_file(room,item);self.assertEqual(s.document_context(room,'twin','','restricted')[0]['id'],item)

class HubWorkflowAcceptanceTests(HubBase):
    def test_discussion_to_routine_review_to_scoped_milestone_assignment(self):
        pid,mid=self.project();self.start(mid);cid=s.create_channel(pid,'Working milestone',['marketing','twin']);c=s.channel(cid);s.channel_control(cid,c['version'],c['title'],['marketing','twin'],False,False,40,delegated=True);tid=s.create_topic(cid,'Evidence gap',mid);rid=s.send(tid,'Propose bounded investigation','direct','marketing',uuid4().hex);e.advance();self.reply(tasks=[dict(kind='collab',title='Investigate exact evidence gap',details='Draft a local evidence assessment and disclose uncertainties.',rationale='Resolve an identified limitation')]);e.advance();self.assertEqual(de.run_turn(client=Metered({'decision':'authorize','note':'Routine bounded local contribution within the working milestone.'}))['status'],'done');e.advance();card=s.one('SELECT * FROM hub_cards WHERE topic_id=?',(tid,));self.assertEqual(card['status'],'authorized');self.assertEqual(ms.assignment(card['task_id'])['milestone_id'],mid);self.assertEqual(team.task(card['task_id'])['owner'],'marketing');self.assertEqual(ms.milestone(mid)['state'],'working');self.assertNotEqual(ms.milestone(mid)['state'],'approved')
    def test_project_reclassification_after_twin_reply_prevents_application(self):
        pid,mid,room,card=self.card();cards.request_review(card['id'],card['version']);self.assertEqual(de.run_turn(client=Metered({'decision':'authorize','note':'Routine internal draft.'}))['status'],'done');parent=team.project(pid);team.update_project(pid,parent['version'],parent['priority'],'consequential',parent['sensitivity'],'active');cards.reconcile();self.assertEqual(cards.get(card['id'])['status'],'owner_review');self.assertFalse(team.tasks())

class HubThreadTests(HubBase):
    def test_direct_reply_thread_keeps_employee_context_and_parent_link(self):
        parent=s.primary('marketing');turn=d.send(parent,'Original question with exact constraints',uuid4().hex);self.reply('Saved original answer');child=s.reply_thread(parent,turn,'A focused follow-up');self.assertEqual(s.reply_thread(parent,turn,'Repeated click'),child);self.assertEqual(ux.room(child)['employee'],'marketing');self.assertEqual(ux.room(child)['project_id'],'');d.send(child,'Discuss this point further',uuid4().hex);claimed=d.claim();messages,trace=de.prompt(claimed);self.assertEqual(trace['hub_context_visible']['reply_thread_parent']['turn_id'],turn);self.assertIn('Saved original answer',json.dumps(messages))
    def test_thread_cannot_select_foreign_message_or_move_context_silently(self):
        a=s.primary('marketing');b=s.primary('applications');turn=d.send(a,'Original',uuid4().hex);self.reply()
        with self.assertRaises(ValueError):s.reply_thread(b,turn,'Wrong parent')
        child=s.reply_thread(a,turn,'Follow-up');pid=team.create_project('marketing','Other project','O','C')
        with p.connect() as db:db.execute("UPDATE ux_rooms SET project_kind='team',project_id=? WHERE thread_id=?",(pid,child))
        d.send(child,'Question',uuid4().hex);claimed=d.claim()
        with self.assertRaises(ValueError):de.prompt(claimed)
    def test_project_channel_work_history_includes_actual_milestone_reviews(self):
        pid,mid,cid,tid=self.channel()
        with p.connect() as db:db.execute('INSERT INTO milestone_reviews VALUES(?,?,?,?,?,?,?)',(uuid4().hex,mid,None,'twin','needs_revision','Actual saved review finding',p.stamp()))
        from superhuman.teamhub.web import project_activity
        body=project_activity(pid);self.assertIn('Actual saved review finding',body);self.assertIn('The Twin',body);self.assertIn('/milestones/'+mid,body)
    def test_reply_thread_control_survives_live_fragment_rendering(self):
        room=s.primary('marketing');turn=d.send(room,'Original',uuid4().hex);self.reply();from superhuman.workspace.web import transcript
        self.assertIn('/team-hub/rooms/'+room+'/thread',transcript(room));self.assertIn('name="turn_id" value="'+turn+'"',transcript(room))
