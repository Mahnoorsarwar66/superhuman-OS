"""Owner journeys: one read model, context consent, history and actionable controls."""
import json,os,re,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from fastapi.testclient import TestClient
from superhuman.projects import engine as p
from superhuman.team import store as team
from superhuman.departments import store as dept
from superhuman.experience import store as ux,inbox
from superhuman.dialogue import store as d,engine as de
from superhuman.workspace import model,chat
from superhuman.workspace.presentation import rich
from superhuman.interface.tree import parse
from superhuman.hosted import auth,config,web

class WorkspaceBase(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=Path.cwd();os.chdir(self.tmp.name)
        self.env=patch.dict(os.environ,{key:str(Path(name).resolve()) for key,name in [('SUPERHUMAN_KNOWLEDGE_DB','knowledge.db'),('SUPERHUMAN_MAIL_KEY_FILE','mail.key'),('SUPERHUMAN_MEMORY_PATH','memory.json'),('SUPERHUMAN_IDENTITY_DIR','identity')]});self.env.start();ux.initialize()
    def tearDown(self):self.env.stop();os.chdir(self.old);self.tmp.cleanup()
    def project(self,scope='marketing',**kw):return team.create_project(scope,'Project '+uuid4().hex[:6],'Concrete objective','Reviewable outcome',**kw)
    def proposal(self,pid):
        ident=ux.create('marketing','Room','team',pid);d.send(ident,'Draft a memo',uuid4().hex);claimed=d.claim();d.finish(claimed,'Proposal only',[dict(kind='collab',title='Memo',details='A local draft',rationale='For review')],'{}',{})
        return ident,d.suggestions(ident)[0]
    def comms(self):
        from superhuman.comms import store as c
        c.initialize();cid=c.connect('whatsapp','Selected business number','123456789','123456789',{'app_secret':'synthetic-app-secret-value-12345','verify_token':'synthetic-verify-token-value-12345'});c.control_channel(cid,c.channel(cid)['version'],True,True)
        with p.connect() as db:
            sid=c.ingest(db,c.channel(cid),'unique-id','thread','Sender','Meeting note','A saved source',time.time())
            source=dict(db.execute('SELECT * FROM comms_sources WHERE id=?',(sid,)).fetchone());snapshot={'aliases':{'S1':{'source_id':sid,'channel_id':cid,'digest':source['digest']}}}
            db.execute("INSERT INTO comms_runs(id,submission,kind,status,snapshot,result,created_at,finished_at) VALUES('brief','unique','briefing','done',?,?,?,?)",(json.dumps(snapshot),json.dumps({'summary':'CONSENTED_BRIEFING_SUMMARY','items':[]}),p.stamp(),p.stamp()))
        return cid,sid

class WorkspaceStoreTests(WorkspaceBase):
    def test_department_includes_team_project_and_task(self):
        pid=self.project();tid=team.create_task(pid,'marketing','Assigned draft','Write','Review')
        snap=dept.snapshot('marketing');self.assertEqual(snap['counts']['projects'],1);self.assertEqual(snap['counts']['tasks'],1);self.assertEqual(snap['projects'][0]['url'],'/team/projects/'+pid);self.assertEqual(snap['tasks'][0]['url'],'/team/tasks/'+tid)
    def test_owned_run_not_double_counted(self):
        from superhuman.runtime import engine as runtime
        pid=self.project();tid=team.create_task(pid,'marketing','Employee assignment','Write','Review');run=runtime.enqueue('collab','marketing','Execution copy','Write')
        with p.connect() as db:db.execute("UPDATE team_tasks SET run_id=?,state='dispatched' WHERE id=?",(run,tid))
        snap=dept.snapshot('marketing');self.assertEqual((snap['counts']['projects'],snap['counts']['tasks']),(1,1));self.assertEqual(len(model.tasks()),1);self.assertEqual(len(model.projects()),1)
    def test_department_isolation_and_friendly_next_link(self):
        a=self.project();b=self.project('career_rnd');tid=team.create_task(a,'marketing','Review memo','Write','Review')
        with p.connect() as db:db.execute("UPDATE team_tasks SET state='awaiting_review' WHERE id=?",(tid,))
        snap=dept.snapshot('marketing');self.assertEqual(snap['counts']['outputs_review'],1);self.assertEqual(snap['next'][1],'/team/tasks/'+tid);self.assertNotIn(b,[v['id'] for v in snap['projects']])
    def test_global_twin_room_not_assigned_to_endorsement(self):
        ux.create('twin','Personal discussion');self.assertEqual(dept.snapshot('endorsement')['counts']['conversations'],0)
    def test_routine_proposal_does_not_force_restricted_classification(self):
        pid=self.project();ident,s=self.proposal(pid);tid=chat.approve(s['id'],s['proposal_hash'],pid,s['title'],s['details'],'routine','confidential','Review a local draft')
        task=team.task(tid);self.assertEqual(task['risk'],'routine');self.assertEqual(task['sensitivity'],'confidential');self.assertFalse(team.needs_owner(task));self.assertEqual(task['owner_grant'],0)
    def test_explicit_start_approval_recorded_with_proposal(self):
        pid=self.project();ident,s=self.proposal(pid);tid=chat.approve(s['id'],s['proposal_hash'],pid,s['title'],s['details'],'consequential','restricted','Review draft',start=True)
        t=team.task(tid);self.assertEqual(t['owner_grant'],1);self.assertEqual(t['state'],'ready')
    def test_proposal_cannot_lower_project_controls(self):
        pid=self.project(risk='high_risk',sensitivity='restricted');ident,s=self.proposal(pid)
        with self.assertRaisesRegex(ValueError,'below project'):chat.approve(s['id'],s['proposal_hash'],pid,s['title'],s['details'],'routine','internal','Review',True)
    def test_public_instruction_sharing_requires_confirmation(self):
        pid=self.project();ident,s=self.proposal(pid)
        with self.assertRaisesRegex(ValueError,'private'):chat.approve(s['id'],s['proposal_hash'],pid,s['title'],s['details'],'routine','internal','Review')
        self.assertEqual(team.tasks(),[])
    def test_approval_replay_with_different_details_rejected(self):
        pid=self.project();ident,s=self.proposal(pid);args=(s['id'],s['proposal_hash'],pid,s['title'],s['details'],'routine','confidential','Review');a=chat.approve(*args);self.assertEqual(chat.approve(*args),a)
        with self.assertRaisesRegex(ValueError,'different'):chat.approve(*args,start=True)
    def test_move_conversation_preserves_history_and_checks_version(self):
        a=self.project();b=self.project();ident=ux.create('marketing','Wrong location','team',a);r=ux.room(ident)
        chat.relocate(ident,r['version'],'team',b,True);self.assertEqual(ux.project_rooms('team',a),[]);self.assertEqual(ux.project_rooms('team',b)[0]['id'],ident)
        with self.assertRaisesRegex(ValueError,'changed'):chat.relocate(ident,r['version'],'team',a,True)
    def test_move_requires_confirmation_and_resolved_work(self):
        a=self.project();ident,s=self.proposal(a)
        with self.assertRaisesRegex(ValueError,'Confirm'):chat.relocate(ident,1,'','',False)
        with self.assertRaisesRegex(ValueError,'proposed'):chat.relocate(ident,1,'','',True)
    def test_move_does_not_cross_departments(self):
        ident=ux.create('marketing','Department chat');b=self.project('career_rnd')
        with self.assertRaises(ValueError):chat.relocate(ident,1,'team',b,True)
    def test_twin_gets_consented_saved_briefings(self):
        self.comms();ident=ux.create('twin','Twin');d.send(ident,'What needs attention?',uuid4().hex);messages,trace=de.prompt(d.claim());self.assertIn('CONSENTED_BRIEFING_SUMMARY',json.dumps(messages));self.assertEqual(trace['context_summary_ids'],['brief'])
    def test_revoked_consent_excludes_summary(self):
        from superhuman.comms import store as c
        cid,sid=self.comms();c.control_channel(cid,c.channel(cid)['version'],True,False);self.assertEqual(chat.communications(),[])
    def test_project_twin_room_excludes_global_inbox_context(self):
        self.comms();ident=ux.create('twin','Project','team',self.project());d.send(ident,'Discuss project',uuid4().hex);messages,trace=de.prompt(d.claim());self.assertNotIn('CONSENTED_BRIEFING_SUMMARY',json.dumps(messages))
    def test_revocation_during_reply_invalidates_context(self):
        from superhuman.comms import store as c
        cid,sid=self.comms();ident=ux.create('twin','Twin');d.send(ident,'Discuss',uuid4().hex);claimed=d.claim();messages,trace=de.prompt(claimed);c.control_channel(cid,c.channel(cid)['version'],True,False)
        with self.assertRaisesRegex(ValueError,'consent'):chat.validate(claimed,trace)
    def test_renderer_escapes_html_and_formats_text(self):
        result=rich('# Heading\n**Bold**\n- One\n<script>alert(1)</script>\n```\n<img src=x>\n```')
        self.assertIn('<h3>Heading</h3>',result);self.assertIn('<strong>Bold</strong>',result);self.assertIn('<li>One</li>',result);self.assertNotIn('<script>',result);self.assertNotIn('<img',result)
    def test_email_review_state_survives_linked_source_conversion(self):
        from superhuman.mail import store as mail
        from superhuman.comms import store as c
        mail.initialize();c.initialize()
        with p.connect() as db:db.execute('INSERT INTO mail_messages VALUES(?,?,?,?,?,?,?,?,?)',('original','personal_gmail','remote','Sender','Title',p.stamp(),'Body','',time.time()))
        inbox.mark('m:original','reviewed');cid=c.connect('email','Linked Gmail','owner@example.com','personal_gmail')
        with p.connect() as db:sid=c.ingest(db,c.channel(cid),'original','thread','Sender','Title','Body',time.time())
        found=inbox.messages();self.assertEqual(len(found),1);self.assertEqual(found[0]['id'],'c:'+sid);self.assertEqual(found[0]['review_state'],'reviewed')

    def test_unanalysed_email_remains_visible_under_linked_account(self):
        from superhuman.mail import store as mail
        from superhuman.comms import store as c
        mail.initialize();c.initialize();cid=c.connect('email','Linked Gmail','owner@example.com','personal_gmail')
        with p.connect() as db:db.execute('INSERT INTO mail_messages VALUES(?,?,?,?,?,?,?,?,?)',('old-preview','personal_gmail','remote','Sender','Title',p.stamp(),'Body','',time.time()))
        self.assertEqual(inbox.messages()[0]['account'],'c:'+cid)

    def test_all_decisions_include_new_calendar_and_task_approvals(self):
        pid=self.project(risk='consequential');tid=team.create_task(pid,'marketing','Needs start','Write','Review')
        with p.connect() as db:db.execute("INSERT INTO ux_meetings(id,source_id,source_digest,title,original,zone,start_at,end_at,created_at) VALUES('m','','','Invitation','2026-10-16 09:00','UTC','','',?)",(p.stamp(),))
        urls={a['url'] for a in model.decisions()};self.assertIn('/team/tasks/'+tid,urls);self.assertIn('/calendar-intake#meeting-m',urls)

class WorkspaceWebTests(WorkspaceBase):
    def setUp(self):
        super().setUp();self.cfg=config.Settings('https://superhuman.example',state_dir=Path('state'));auth.Store(self.cfg.auth_db).setup('owner','synthetic-test-passphrase');self.client=TestClient(web.create_app(self.cfg),base_url=self.cfg.public_origin)
        self.client.post('/login',data={'username':'owner','password':'synthetic-test-passphrase','csrf':self.csrf(self.client.get('/login'))})
    def tearDown(self):self.client.close();super().tearDown()
    def csrf(self,r):return re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
    def post(self,url,data,source='/team-room'):
        return self.client.post(url,data=dict(data,csrf=self.csrf(self.client.get(source))),follow_redirects=False)
    def test_login_page_does_not_request_protected_assets(self):
        self.client.cookies.clear();result=self.client.get('/login');self.assertNotIn('<script src=',result.text);self.assertNotIn('<link rel="stylesheet"',result.text)

    def test_primary_journeys_load(self):
        for path in ('/','/projects','/new-project','/new-task','/project-tasks','/reviews','/attention','/twin','/twin?tab=updates','/twin?tab=communications','/team-room','/team-room?tab=board','/team-room?tab=feed','/calendar','/calendar/new?day=2026-10-18','/calendar-search','/inboxes'):
            with self.subTest(path=path):self.assertEqual(self.client.get(path).status_code,200)
    def test_one_project_creation_form_creates_managed_record(self):
        data=dict(scope='marketing',title='One project',objective='A concrete outcome',acceptance='Review draft',risk='routine',sensitivity='internal',priority='P2')
        response=self.post('/workspace-projects/create',data,'/new-project');self.assertEqual(response.status_code,303);self.assertTrue(response.headers['location'].startswith('/project-briefs/'));self.assertEqual(dept.snapshot('marketing')['counts']['projects'],1)
        self.assertNotIn('method="post" action="/projects"',self.client.get('/projects').text)
    def test_selected_employee_only_lists_own_rooms(self):
        ux.create('marketing','SARAH_ONLY_TITLE');ux.create('applications','JOSE_ONLY_TITLE');result=self.client.get('/team-room?employee=applications');self.assertIn('JOSE_ONLY_TITLE',result.text);self.assertNotIn('SARAH_ONLY_TITLE',result.text)
    def test_room_history_search_and_pagination(self):
        for n in range(34):ux.create('marketing','Room '+str(n))
        first=self.client.get('/team-room?employee=marketing');self.assertIn('Next page',first.text);self.assertIn('Room 0',self.client.get('/team-room?employee=marketing&page=2').text)
        self.assertIn('Room 17',self.client.get('/team-room?employee=marketing&q=Room+17').text)
    def test_older_messages_remain_reachable(self):
        ident=ux.create('marketing','Long conversation')
        with p.connect() as db:
            for i in range(1,56):db.execute("INSERT INTO dialogue_turns(id,thread_id,ordinal,submission_key,user_text,status,reply,created_at) VALUES(?,?,?,?,?,'done','Saved reply',?)",(uuid4().hex,ident,i,uuid4().hex,'History message '+str(i),p.stamp()))
        first=self.client.get('/team-room/'+ident);self.assertIn('?before=6',first.text)
        older=self.client.get('/team-room/'+ident+'?before=6');self.assertIn('History message 1',older.text);self.assertNotIn('History message 55',older.text.split('<div data-transcript>')[1].split('<div data-proposals>')[0])

    def test_chat_limit_controls_and_fragment_csrf(self):
        ident=ux.create('marketing','Room');d.set_budget(ident,1)
        with p.connect() as db:db.execute('UPDATE dialogue_threads SET used_calls=1 WHERE id=?',(ident,))
        response=self.client.get('/team-room/'+ident);self.assertIn('reply allowance',response.text);self.assertIn('Update reply allowance',response.text)
        r=self.post('/room-controls/'+ident+'/budget',{'maximum':4},'/team-room/'+ident);self.assertEqual(r.status_code,303);self.assertEqual(d.get(ident)['max_calls'],4)
        d.send(ident,'Queued',uuid4().hex);fragment=self.client.get('/room-fragment/'+ident);self.assertIn('Cancel queued reply',fragment.text);self.assertIn('name="csrf"',fragment.text)
    def test_live_state_changes_and_leaves_composer_outside_fragment(self):
        ident=ux.create('marketing','Room');turn=d.send(ident,'Hello',uuid4().hex);first=self.client.get('/room-live/'+ident).json();self.assertTrue(first['pending']);self.assertFalse(first['can_send']);claimed=d.claim();d.finish(claimed,'# Response\n- Saved answer',[],'{}',{})
        second=self.client.get('/room-live/'+ident).json();self.assertNotEqual(first['signature'],second['signature']);self.assertTrue(second['can_send']);fragment=self.client.get('/room-fragment/'+ident);self.assertIn('<h3>Response</h3>',fragment.text);self.assertNotIn('class="ux-composer"',fragment.text)
    def test_explicit_retry_is_idempotent(self):
        ident=ux.create('marketing','Room');turn=d.send(ident,'Retry me',uuid4().hex);d.cancel(ident,turn);key=uuid4().hex
        for _ in range(2):self.assertEqual(self.post('/room-controls/'+ident+'/retry',dict(turn_id=turn,submission_key=key)).status_code,303)
        self.assertEqual(len(d.turns(ident)),2)
    def test_reviews_and_attention_share_queue(self):
        pid=self.project(risk='consequential');team.create_task(pid,'marketing','Review same title','Write','Review')
        for path in ('/reviews','/attention','/'):
            self.assertIn('Review same title',self.client.get(path).text)
    def test_task_filters_use_names_and_keep_other_tasks_out(self):
        a=self.project();b=self.project('career_rnd');team.create_task(a,'marketing','SARAH task','Write','Review',due='2000-01-01');team.create_task(b,'career_rnd','AMELIA task','Write','Review')
        result=self.client.get('/project-tasks?employee=marketing&due=overdue');self.assertIn('SARAH task',result.text);self.assertNotIn('AMELIA task',result.text);self.assertIn('Sarah',result.text)
    def test_twin_old_routes_converge(self):
        self.assertEqual(self.client.get('/team/twin',follow_redirects=False).headers['location'],'/twin?tab=updates');self.assertEqual(self.client.get('/assistant',follow_redirects=False).headers['location'],'/twin?tab=communications')
    def test_inbox_review_preserves_filters_and_rejects_external_return(self):
        from superhuman.mail import store as mail
        mail.initialize()
        with p.connect() as db:db.execute('INSERT INTO mail_messages VALUES(?,?,?,?,?,?,?,?,?)',('saved','personal_gmail','remote','A','Subject',p.stamp(),'Preview','',time.time()))
        target='/inboxes?account=m%3Apersonal_gmail&state=unreviewed&q=Subject&page=2&selected=m%3Asaved'
        response=self.post('/inbox-actions/review',{'ident':'m:saved','state':'reviewed','return_to':target},'/inboxes');self.assertEqual(response.headers['location'],target)
        self.assertEqual(self.post('/inbox-actions/review',{'ident':'m:saved','state':'reviewed','return_to':'https://evil.invalid/'},'/inboxes').status_code,409)
    def test_calendar_reschedule_keeps_original_invitation_notes(self):
        from superhuman.calendar import store as cal
        ident=cal.create('Meeting','2026-10-16T13:00:00+00:00','','Original America/New_York',uuid4().hex);self.assertIn('Reschedule or edit',self.client.get('/calendar/event/'+ident).text)
        response=self.post('/workspace-calendar/'+ident+'/save',dict(version=1,title='Moved',start_at='2026-10-17T18:00',end_at='',notes='Original America/New_York',status='confirmed'),'/calendar/event/'+ident);self.assertEqual(response.status_code,303);self.assertEqual(cal.get(ident)['start_at'],'2026-10-17T13:00:00+00:00');self.assertIn('Original America',cal.get(ident)['notes'])
    def test_invitation_preview_accepts_explicit_offset_without_zone(self):
        response=self.post('/meeting-preview/test',dict(title='Meeting',original='2026-10-16T09:00:00-04:00',zone='',end='',fold=''),'/calendar-intake');self.assertEqual(response.status_code,200);self.assertIn('06:00 PM PKT',response.text);self.assertIn('Confirm this local meeting',response.text)
    def test_assets_and_live_endpoints_are_private(self):
        ident=ux.create('marketing','Room');self.client.cookies.clear()
        for path in ('/room-live/'+ident,'/room-fragment/'+ident,'/assets/workspace-v129.js'):
            self.assertEqual(self.client.get(path,follow_redirects=False).status_code,303)
    def test_team_tabs_have_one_current_item(self):
        for url in ('/team-room?tab=board','/team-room?tab=feed','/team-room?employee=marketing'):
            response=self.client.get(url);tree=parse(response.text);nav=next(n for n in tree.find('nav') if n.attrs.get('aria-label')=='Team navigation');self.assertEqual(sum(a.attrs.get('aria-current')=='page' for a in nav.find('a')),1)

    def test_canonical_board_has_saved_task_and_employee_profile_links(self):
        pid=self.project();team.create_task(pid,'marketing','Current task','Write','Review');response=self.client.get('/team-room?tab=board');self.assertIn('Current task',response.text);self.assertIn('Workload &amp; profile',response.text);self.assertIn('view=employees&amp;employee=marketing',response.text);self.assertIn('No current worker heartbeat',response.text)

if __name__=='__main__':unittest.main()
