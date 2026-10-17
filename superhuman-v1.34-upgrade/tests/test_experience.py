"""v1.28 regression: isolation, governed proposals, truthful presence and timezone edges."""
import hashlib,json,os,re,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from datetime import date,datetime,timezone
from fastapi.testclient import TestClient
from superhuman.projects import engine as p
from superhuman.dialogue import store as d,engine as de
from superhuman.team import store as team
from superhuman.experience import store as ux,calendar as c,inbox,chat
from superhuman.hosted import auth,config,web,jobs
from superhuman.navigation import shell

class ExperienceStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=Path.cwd();os.chdir(self.tmp.name)
        self.env=patch.dict(os.environ,{'SUPERHUMAN_KNOWLEDGE_DB':str(Path('knowledge.db').resolve()),'SUPERHUMAN_MAIL_KEY_FILE':str(Path('mail.key').resolve()),'SUPERHUMAN_IDENTITY_DIR':str(Path('identity').resolve()),'SUPERHUMAN_MEMORY_PATH':str(Path('memory.json').resolve())});self.env.start();ux.initialize()
    def tearDown(self):self.env.stop();os.chdir(self.old);self.tmp.cleanup()
    def project(self,scope='marketing'):return team.create_project(scope,'A project '+uuid4().hex[:6],'Make a local draft','Owner can review it')
    def test_employee_names_and_stable_ids(self):
        self.assertEqual({e['id']:e['name'] for e in team.employees()},ux.NAMES)
        self.assertEqual(len(team.employees()),8)
        ux.initialize();self.assertEqual(len(team.employees()),8)
    def test_two_projects_same_department_have_separate_rooms(self):
        a=self.project();b=self.project();ra=ux.create('marketing','A only','team',a);rb=ux.create('marketing','B only','team',b)
        self.assertEqual([r['id'] for r in ux.project_rooms('team',a)],[ra]);self.assertNotIn(rb,[r['id'] for r in ux.project_rooms('team',a)])
    def test_legacy_chat_unassigned_until_linked(self):
        pid=p.create('marketing','Target','',12);tid=d.create('marketing','Legacy',5)
        self.assertEqual(ux.project_rooms('canonical',pid),[]);ux.link(tid,'canonical',pid)
        self.assertEqual(ux.project_rooms('canonical',pid)[0]['id'],tid)
        with self.assertRaises(ValueError):ux.link(tid,'canonical',pid)
    def test_wrong_department_link_rejected(self):
        pid=self.project('career_rnd');tid=d.create('marketing','Wrong',5)
        with self.assertRaises(ValueError):ux.link(tid,'team',pid)
        with self.assertRaises(ValueError):ux.create('marketing','Wrong','team',pid)
    def test_cannot_rebind_pending_chat(self):
        pid=self.project();tid=d.create('marketing','Pending',5);d.send(tid,'Hello',uuid4().hex)
        with self.assertRaisesRegex(ValueError,'pending'):ux.link(tid,'team',pid)
    def test_project_prompt_excludes_other_projects_and_global_memory(self):
        a=self.project();b=team.create_project('marketing','SECRET_OTHER_PROJECT','SECRET_OTHER_BRIEF','Secret criteria');tid=ux.create('marketing','Room','team',a)
        d.send(tid,'Discuss this project',uuid4().hex);claim=d.claim();messages,trace=de.prompt(claim)
        data=json.dumps(messages);self.assertNotIn('SECRET_OTHER',data);self.assertNotIn('recent_workstream_projects',data)
        self.assertEqual(trace['employee'],'marketing');self.assertEqual(trace['room_project'],a)
    def test_twin_is_actual_chat_identity(self):
        tid=ux.create('twin','Twin chat');team.add_message('preference','Owner values concise updates')
        d.send(tid,'Hello',uuid4().hex);messages,trace=de.prompt(d.claim())
        self.assertEqual(trace['employee'],'twin');self.assertIn('Owner values concise updates',json.dumps(messages))
    def test_stale_room_context_rejected(self):
        tid=ux.create('marketing','Room');d.send(tid,'Hello',uuid4().hex);claim=d.claim();_,trace=de.prompt(claim)
        with p.connect() as db:db.execute('UPDATE ux_rooms SET version=version+1 WHERE thread_id=?',(tid,))
        with self.assertRaisesRegex(ValueError,'changed'):chat.validate(claim,trace)
    def proposal(self,pid):
        tid=ux.create('marketing','Room','team',pid);d.send(tid,'Propose a draft',uuid4().hex);claim=d.claim()
        d.finish(claim,'Proposed only',[dict(kind='collab',title='Draft memo',details='Write a local memo',rationale='Useful draft')],'{}',{})
        return tid,d.suggestions(tid)[0]
    def test_room_proposal_cannot_use_old_direct_dispatch(self):
        from superhuman.taskdesk import store as desk
        tid,s=self.proposal(self.project())
        with self.assertRaisesRegex(ValueError,'Team Room'):desk.approve(tid,s['id'],s['proposal_hash'],s['title'],s['details'])
        self.assertEqual(team.tasks(),[])
    def test_room_proposal_uses_governed_project_and_is_idempotent(self):
        pid=self.project();tid,s=self.proposal(pid);task=ux.approve(s['id'],s['proposal_hash'],pid,s['title'],s['details'])
        t=team.task(task);self.assertEqual(t['project_id'],pid);self.assertEqual(t['risk'],'consequential');self.assertEqual(t['sensitivity'],'restricted');self.assertEqual(t['owner_grant'],0)
        self.assertEqual(ux.approve(s['id'],s['proposal_hash'],pid,s['title'],s['details']),task);self.assertEqual(len(team.tasks()),1)
    def test_room_proposal_wrong_project_rejected(self):
        a=self.project();b=self.project();tid,s=self.proposal(a)
        with self.assertRaisesRegex(ValueError,'linked'):ux.approve(s['id'],s['proposal_hash'],b,s['title'],s['details'])
    def test_offline_is_not_working(self):
        jobs.initialize();jobs.pulse('synthetic','stopped');board=ux.board()
        self.assertTrue(all(r['state']=='offline' for r in board))
    def test_dispatched_does_not_imply_running(self):
        jobs.initialize();jobs.pulse('synthetic','idle');pid=self.project();tid=team.create_task(pid,'marketing','Assigned','Draft','Review')
        with p.connect() as db:db.execute("UPDATE team_tasks SET state='dispatched' WHERE id=?",(tid,))
        row=next(r for r in ux.board() if r['id']=='marketing');self.assertEqual(row['state'],'waiting')
    def test_twin_communications_analysis_is_visible(self):
        from superhuman.comms import store as comms
        comms.initialize();jobs.initialize();jobs.pulse('synthetic','working')
        with p.connect() as db:db.execute("INSERT INTO comms_runs(id,submission,kind,status,snapshot,created_at) VALUES('synthetic-run','synthetic-submission','intake','running','{}',?)",(p.stamp(),))
        row=next(r for r in ux.board() if r['id']=='twin');self.assertEqual(row['state'],'working');self.assertIn('Communications',row['assignment'])

    def test_completed_task_is_not_active(self):
        jobs.initialize();jobs.pulse('synthetic','idle');pid=self.project();tid=team.create_task(pid,'marketing','Complete','Draft','Review')
        with p.connect() as db:db.execute("UPDATE team_tasks SET state='completed' WHERE id=?",(tid,))
        row=next(r for r in ux.board() if r['id']=='marketing');self.assertEqual(row['state'],'idle');self.assertIsNone(row['task'])
    def test_timezone_rollover(self):
        self.assertEqual(c.local(c.zoned('2026-10-16 23:30','America/Los_Angeles')).strftime('%Y-%m-%d %H:%M'),'2026-10-17 11:30')
    def test_timezone_dst_offsets(self):
        self.assertEqual(c.zoned('2026-07-01 09:00','America/New_York'),'2026-07-01T13:00:00+00:00')
        self.assertEqual(c.zoned('2026-01-01 09:00','America/New_York'),'2026-01-01T14:00:00+00:00')
    def test_ambiguous_time_requires_fold(self):
        with self.assertRaisesRegex(ValueError,'twice'):c.zoned('2026-11-01 01:30','America/New_York')
        self.assertNotEqual(c.zoned('2026-11-01 01:30','America/New_York','0'),c.zoned('2026-11-01 01:30','America/New_York','1'))
    def test_nonexistent_time_rejected(self):
        with self.assertRaisesRegex(ValueError,'does not exist'):c.zoned('2026-03-08 02:30','America/New_York')
    def test_ambiguous_abbreviation_and_missing_zone_rejected(self):
        for zone in ('','IST','CST','BST','Invalid/Zone'):
            with self.subTest(zone=zone),self.assertRaises(ValueError):c.zoned('2026-10-16 09:00',zone)
    def test_pst_is_not_pakistan_and_conflicting_abbreviation_rejected(self):
        self.assertEqual(c.local(c.zoned('2026-01-01 09:00','PST')).hour,22)
        with self.assertRaisesRegex(ValueError,'conflicts'):c.zoned('2026-07-01 09:00','PST')
    def test_meeting_extraction_excludes_deadline_and_preserves_uncertainty(self):
        self.assertEqual(c.extract('Payment deadline 2026-10-16 09:00 UTC'),[])
        found=c.extract('Meeting 2026-10-16 09:00 IST');self.assertEqual(found[0][:2],('2026-10-16 09:00','IST'));self.assertEqual(found[0][2],'')
    def test_ics_timezone_and_unknown_zone(self):
        found=c.extract('BEGIN:VEVENT\nDTSTART;TZID=America/New_York:20261016T090000\nDTEND;TZID=America/New_York:20261016T100000\nEND:VEVENT')
        self.assertEqual(found[0][2:4],('2026-10-16T13:00:00+00:00','2026-10-16T14:00:00+00:00'))
        found=c.extract('BEGIN:VEVENT\nDTSTART:20261016T090000\nEND:VEVENT');self.assertEqual(found[0][2],'')
    def test_malformed_ics_does_not_interrupt_intake(self):
        self.assertEqual(c.extract('BEGIN:VEVENT\nDTSTART;TZID=UTC:20269999T990000\nEND:VEVENT'),[])

    def test_meeting_confirmation_preserves_source_and_is_idempotent(self):
        from superhuman.calendar import store as cal
        cal.initialize();ident=uuid4().hex
        with p.connect() as db:db.execute('INSERT INTO ux_meetings(id,source_id,source_digest,title,original,zone,start_at,end_at,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(ident,'','','Meeting','2026-10-16 09:00','America/New_York','','',p.stamp()))
        eid=c.confirm(ident,'Meeting','2026-10-16 09:00','America/New_York');event=cal.get(eid)
        self.assertIn('America/New_York',event['notes']);self.assertEqual(event['start_at'],'2026-10-16T13:00:00+00:00');self.assertEqual(c.confirm(ident,'Meeting','2026-10-16 09:00','America/New_York'),eid)
    def test_multiday_and_midnight_exclusive_end(self):
        event={'start_at':'2026-10-16T18:00:00+00:00','end_at':'2026-10-17T19:00:00+00:00'}
        self.assertTrue(c.on_day(event,date(2026,10,16)));self.assertTrue(c.on_day(event,date(2026,10,17)));self.assertFalse(c.on_day(event,date(2026,10,18)))
    def test_grid_lanes_keep_overlaps_visible(self):
        a={'id':'a','start_at':'2026-10-16T04:00:00+00:00','end_at':'2026-10-16T05:00:00+00:00'};b=dict(a,id='b')
        items=c.lanes([a,b],date(2026,10,16));self.assertEqual([i['lane'] for i in items],[0,1]);self.assertTrue(all(i['lanes']==2 for i in items))
    def test_inbox_mark_is_local_and_validates_source(self):
        with self.assertRaises(ValueError):inbox.mark('missing','reviewed')
        with self.assertRaises(ValueError):inbox.mark('missing','remote_read')

class ExperienceWebTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=Path.cwd();os.chdir(self.tmp.name)
        self.env=patch.dict(os.environ,{'SUPERHUMAN_KNOWLEDGE_DB':str(Path('knowledge.db').resolve()),'SUPERHUMAN_MAIL_KEY_FILE':str(Path('mail.key').resolve()),'SUPERHUMAN_IDENTITY_DIR':str(Path('identity').resolve()),'SUPERHUMAN_MEMORY_PATH':str(Path('memory.json').resolve())});self.env.start();ux.initialize()
        self.cfg=config.Settings('https://superhuman.example',state_dir=Path('state'));auth.Store(self.cfg.auth_db).setup('owner','synthetic-test-passphrase');self.client=TestClient(web.create_app(self.cfg),base_url=self.cfg.public_origin)
        token=self.csrf(self.client.get('/login'));self.client.post('/login',data={'username':'owner','password':'synthetic-test-passphrase','csrf':token})
    def tearDown(self):self.client.close();self.env.stop();os.chdir(self.old);self.tmp.cleanup()
    def csrf(self,r):return re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
    def test_new_screens_and_assets_load(self):
        for path in ('/team-room','/team-room?tab=board','/team-room?tab=feed','/team-room/status','/project-tasks','/suggested-work','/inboxes','/calendar','/calendar?view=week','/calendar?view=day','/calendar?view=agenda','/calendar-intake','/assets/workspace.js','/assets/workspace.css'):
            with self.subTest(path=path):self.assertEqual(self.client.get(path).status_code,200)
    def test_navigation_and_briefing_active_section(self):
        r=self.client.get('/memory/briefing');nav=re.search(r'<nav class="shell-primary".*?</nav>',r.text).group()
        self.assertIn('href="/" aria-current="page"',nav);self.assertIn('href="/coding"',nav);self.assertNotIn('>Tasks</a>',nav);self.assertNotIn('>Talk</a>',nav)
        r=self.client.get('/departments/marketing');self.assertNotIn('aria-label="Section navigation"',r.text)
        for label in ('Summary','Work &amp; priorities','Files &amp; research','Conversations','Activity','Agent &amp; supervision'):
            self.assertTrue(label in r.text or label.replace('&amp;','&') in r.text,label)
    def test_department_tabs(self):
        for tab in ('agent','supervision'):
            r=self.client.get('/departments/marketing/'+tab);self.assertEqual(r.status_code,200,r.text[:300])
    def test_project_conversation_no_workstream_leak(self):
        a=p.create('marketing','A target','',12);b=p.create('marketing','B target','',12);ra=ux.create('marketing','A secret','canonical',a);ux.create('marketing','B secret','canonical',b)
        r=self.client.get('/workspace/projects/'+a+'/conversations');self.assertIn('A secret',r.text);self.assertNotIn('B secret',r.text)
    def test_room_creation_send_and_csrf(self):
        data={'employee':'marketing','title':'My room'}
        self.assertEqual(self.client.post('/team-room/create',data=data).status_code,403)
        data['csrf']=self.csrf(self.client.get('/team-room'));r=self.client.post('/team-room/create',data=data,follow_redirects=False);self.assertEqual(r.status_code,303)
        room=self.client.get(r.headers['location']);self.assertIn('data-voice',room.text);key=re.search(r'name="submission_key" value="([^"]+)"',room.text).group(1)
        r=self.client.post(r.headers['location']+'/send',data={'message':'Hello Sarah','submission_key':key,'csrf':self.csrf(room)},follow_redirects=False);self.assertEqual(r.status_code,303)
        self.assertEqual(len(d.turns(ux.rooms()[0]['id'])),1)
    def test_csp_keeps_inline_scripts_disabled_and_mic_self_only(self):
        r=self.client.get('/team-room');self.assertIn("script-src 'self'",r.headers['content-security-policy']);self.assertNotIn("script-src 'unsafe-inline'",r.headers['content-security-policy']);self.assertIn('microphone=(self)',r.headers['permissions-policy'])
        js=self.client.get('/assets/workspace.js');self.assertIn('Review the transcript',js.text);self.assertNotIn('.submit(',js.text);self.assertIn('ur-PK',js.text)
    def test_unknown_room_404_and_assets_require_login(self):
        self.assertEqual(self.client.get('/team-room/unknown').status_code,404)
        self.client.cookies.clear()
        for path in ('/team-room/status','/assets/workspace.js'):
            self.assertEqual(self.client.get(path,follow_redirects=False).status_code,303)
    def test_calendar_event_links_and_manual_paste(self):
        data={'csrf':self.csrf(self.client.get('/calendar-intake')),'content':'Meeting 2026-10-16 09:00 America/New_York'}
        self.assertEqual(self.client.post('/calendar-intake/paste',data=data).status_code,200)
        m=ux.read('ux_meetings','SELECT * FROM ux_meetings')[0];eid=c.confirm(m['id'],'Meeting',m['original'],m['zone'])
        r=self.client.get('/calendar?view=day&day=2026-10-16');self.assertIn('/calendar/event/'+eid,r.text);self.assertEqual(self.client.get('/calendar/event/'+eid).status_code,200)

if __name__=='__main__':unittest.main()
