"""Real catalogue, permissions, alert lifecycle, prompts and authenticated journeys."""
import json,os,re,time,unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
from fastapi.testclient import TestClient
from test_workspace import WorkspaceBase
from superhuman.projects import engine as p
from superhuman.team import store as team,engine as twin,work
from superhuman.experience import store as ux,chat as roomchat
from superhuman.dialogue import store as dialogue
from superhuman.capabilities import local
from superhuman.foundation import storage,personality,proactive,baseline
from superhuman.hosted import auth,config,web

class FoundationTests(WorkspaceBase):
    def fact(self,**kw):
        args=dict(scope='marketing',kind='fact',title='EdSync waitlist',content='600 people',fact_key='edsync.waitlist',sensitivity='internal',source='Owner-confirmed register',status='approved');args.update(kw);return storage.save(**args)
    def document(self,**kw):
        local.store_bytes('marketing','evidence.txt',b'EdSync product evidence and university pilots.');args=dict(scope='marketing',kind='document',title='University evidence',filename='evidence.txt',sensitivity='internal',source='Pilot source',status='approved');args.update(kw);return storage.save(**args)
    def test_new_twin_name_and_role(self):
        self.assertEqual(ux.NAMES['twin'],'The Twin');self.assertEqual(ux.ROLES['twin'],'Superhuman');self.assertEqual(next(e['name'] for e in team.employees() if e['id']=='twin'),'The Twin')
    def test_personalities_persist_and_reject_stale_edit(self):
        r=personality.profile('marketing');personality.update('marketing',r['version'],'Clear, warm and specific.');self.assertIn('specific',personality.instruction('marketing'))
        with self.assertRaises(ValueError):personality.update('marketing',r['version'],'Old edit')
        personality.initialize();self.assertEqual(personality.profile('marketing')['version'],2)
    def test_eight_distinct_styles_and_nonpersonhood_guard(self):
        self.assertEqual(len(set(personality.profile(e)['style'] for e in ux.NAMES)),8);self.assertIn('not a human',personality.instruction('twin'))
    def test_default_private_and_explicit_shared_fact(self):
        self.fact();self.assertFalse(storage.search('endorsement','waitlist')['items']);self.fact(content='Different field',fact_key='edsync.other',access=['endorsement']);self.assertEqual(len(storage.search('endorsement','waitlist')['items']),1)
    def test_confidential_cannot_share_with_everyone(self):
        with self.assertRaises(ValueError):self.fact(sensitivity='confidential',access=['all'])
    def test_sensitivity_ceiling(self):
        self.fact(sensitivity='confidential',access=['endorsement']);self.assertFalse(storage.search('endorsement','waitlist')['items']);self.assertTrue(storage.search('endorsement','waitlist',maximum='confidential')['items'])
    def test_draft_and_archived_not_retrieved(self):
        self.fact(status='draft');self.fact(status='archived',fact_key='archive');self.assertFalse(storage.search('marketing','waitlist')['items'])
    def test_approval_requires_source(self):
        with self.assertRaises(ValueError):self.fact(source='')
    def test_conflicting_fact_values_excluded(self):
        self.fact();self.fact(content='700 people');r=storage.search('marketing','waitlist');self.assertFalse(r['items']);self.assertTrue(any('Conflicting' in e['issue'] for e in r['issues']))
    def test_same_value_is_not_conflict(self):
        self.fact();self.fact();self.assertTrue(storage.search('marketing','waitlist')['items'])
    def test_expired_review_date(self):
        self.fact(review_on='2000-01-01');r=storage.search('marketing','waitlist');self.assertFalse(r['items']);self.assertIn('Review due',r['issues'][0]['issue'])
    def test_project_tag_is_not_cross_project_context(self):
        pid=self.project();self.fact(project_kind='team',project_id=pid);self.assertFalse(storage.search('marketing','waitlist')['items']);self.assertTrue(storage.search('marketing','waitlist',project_id=pid)['items'])
    def test_project_controls_cannot_be_lowered(self):
        pid=self.project(sensitivity='confidential')
        with self.assertRaises(ValueError):self.fact(project_kind='team',project_id=pid,sensitivity='internal')
    def test_foreign_project_rejected(self):
        pid=self.project('career_rnd')
        with self.assertRaises(ValueError):self.fact(project_kind='team',project_id=pid)
    def test_file_hash_change_requires_reconfirmation(self):
        ident=self.document();local.file_for('marketing','evidence.txt').write_text('Changed evidence');r=storage.search('marketing','evidence');self.assertFalse(r['items']);self.assertIn('changed',r['issues'][0]['issue']);self.assertEqual(storage.get(ident)['version'],1)
    def test_file_missing_and_path_traversal(self):
        ident=self.document();local.file_for('marketing','evidence.txt').unlink();self.assertEqual(storage.health(storage.get(ident)),'Source unavailable')
        with self.assertRaises(ValueError):storage.save('marketing','document','Escape',filename='../legal_ops/evidence.txt')
    def test_metadata_revision_and_stale_save(self):
        ident=self.fact();r=storage.get(ident)
        args={k:r[k] for k in ('scope','kind','title','content','fact_key','sensitivity','source','status')}
        storage.save(**args,ident=ident,expected=1,tags='Pilot, pilot, Strategy');self.assertEqual(storage.get(ident)['tags'],'pilot,strategy')
        with self.assertRaises(ValueError):storage.save(**args,ident=ident,expected=1)
        with p.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM storage_versions WHERE id=?',(ident,)).fetchone()[0],2)
    def test_chat_personality_and_reference(self):
        self.fact(access=['twin']);ident=ux.create('twin','Owner chat');dialogue.send(ident,'What is the waitlist?',uuid4().hex);claimed=dialogue.claim();messages,trace=roomchat.prompt(claimed);self.assertIn('PROFESSIONAL PERSONALITY',messages[0]['content']);self.assertIn('600 people',json.dumps(messages));roomchat.validate(claimed,trace)
    def test_chat_rejects_midreply_source_revocation(self):
        ident=self.fact(access=['twin']);room=ux.create('twin','Owner chat');dialogue.send(room,'waitlist',uuid4().hex);claimed=dialogue.claim();_,trace=roomchat.prompt(claimed)
        with p.connect() as db:db.execute("UPDATE storage_items SET status='archived' WHERE id=?",(ident,))
        with self.assertRaises(ValueError):roomchat.validate(claimed,trace)
    def test_chat_rejects_personality_change(self):
        room=ux.create('marketing','Chat');dialogue.send(room,'Hello',uuid4().hex);claimed=dialogue.claim();_,trace=roomchat.prompt(claimed);personality.update('marketing',1,'More concise')
        with self.assertRaises(ValueError):roomchat.validate(claimed,trace)
    def test_assignment_has_department_personality_and_storage(self):
        pid=self.project();self.fact(project_kind='team',project_id=pid);tid=team.create_task(pid,'marketing','Waitlist note','Explain waitlist','Check evidence');text=work.employee_context(team.task(tid));self.assertIn('audience-aware',text);self.assertIn('600 people',text)
    def test_catalogued_draft_excluded_from_legacy_auto_context(self):
        self.document(status='draft');from superhuman.identity.selection import select_context
        result=select_context('marketing','University evidence');self.assertNotIn('EdSync product evidence',result['references'])
    def test_catalogued_draft_cannot_be_read_by_action_tool(self):
        self.document(status='draft');run={'project_id':'legacy','project':{'workstream':'marketing'}}
        with self.assertRaises(ValueError):storage.read_for_run(run,'evidence.txt')
    def test_uncatalogued_legacy_source_remains_readable(self):
        local.store_bytes('marketing','legacy.txt',b'legacy evidence');result=storage.read_for_run({'project_id':'legacy','project':{'workstream':'marketing'}},'legacy.txt');self.assertIn('legacy evidence',result['text'])
    def test_receipt_invalid_after_archive(self):
        ident=self.document();result=storage.read_for_run({'project_id':'legacy','project':{'workstream':'marketing'}},'evidence.txt');storage.verify_receipt(result['storage_receipt'])
        with p.connect() as db:db.execute("UPDATE storage_items SET status='archived' WHERE id=?",(ident,))
        with self.assertRaises(ValueError):storage.verify_receipt(result['storage_receipt'])
    def test_proactive_empty_project_dedup_ack_resolution_reopen(self):
        pid=self.project();proactive.scan(force=True);signal=next(s for s in proactive.signals() if s['entity']==pid);proactive.scan(force=True);self.assertEqual(len([s for s in proactive.signals() if s['entity']==pid]),1);proactive.acknowledge(signal['id'],1);proactive.scan(force=True);self.assertEqual(proactive.signals()[0]['state'],'acknowledged')
        tid=team.create_task(pid,'marketing','First task','Write','Review');proactive.scan(force=True);self.assertFalse(any(s['entity']==pid for s in proactive.signals()))
        with p.connect() as db:db.execute("UPDATE team_tasks SET state='completed' WHERE id=?",(tid,))
        proactive.scan(force=True);signal=next(s for s in proactive.signals() if s['entity']==pid);self.assertEqual(signal['episode'],2);self.assertEqual(signal['state'],'new')
    def test_scan_throttle_and_rollback_pause(self):
        self.assertTrue(proactive.scan(now=100)['scanned']);self.assertFalse(proactive.scan(now=101)['scanned']);proactive.pause_for_rollback();self.assertFalse(proactive.scan(force=True)['scanned'])
    def test_pause_after_reinstall_can_be_resumed(self):
        proactive.pause_for_rollback();self.assertFalse(proactive.scan(force=True)['scanned']);proactive.set_pause(True,False);self.assertTrue(proactive.scan(force=True)['scanned'])
    def test_saved_search_rejects_changed_fact(self):
        ident=self.fact();result=storage.run_search({'project_id':'legacy','project':{'workstream':'marketing'}},'waitlist');storage.verify_lookup(result['storage_lookup'])
        with p.connect() as db:db.execute("UPDATE storage_items SET status='archived' WHERE id=?",(ident,))
        with self.assertRaises(ValueError):storage.verify_lookup(result['storage_lookup'])
    def test_rule_disable_and_stale_configuration(self):
        self.project();r=next(r for r in proactive.rules() if r['id']=='next_action');proactive.configure(r['id'],1,False,1,'notify');proactive.scan(force=True);self.assertFalse(proactive.signals())
        with self.assertRaises(ValueError):proactive.configure(r['id'],1,True,1,'notify')
    def test_notify_does_not_trigger_twin_review(self):
        self.project();proactive.scan(force=True);self.assertFalse(proactive.twin_signals())
    def test_twin_review_is_in_snapshot_without_grant(self):
        pid=self.project();tid=team.create_task(pid,'marketing','Deadline task','Write','Review',due='2000-01-01');proactive.configure('deadline',1,True,72,'twin_review');proactive.scan(force=True);sig,body,actionable=twin.snapshot();self.assertTrue(body['proactive_signals']);self.assertTrue(actionable);self.assertFalse(team.task(tid)['owner_grant'])
    def test_dependency_signal_does_not_dispatch(self):
        pid=self.project();a=team.create_task(pid,'marketing','A','Write','Review');b=team.create_task(pid,'marketing','B','Write','Review',deps=[a])
        with p.connect() as db:db.execute("UPDATE team_tasks SET state='completed' WHERE id=?",(a,))
        proactive.scan(force=True);self.assertTrue(any(s['rule_id']=='dependency' for s in proactive.signals()));self.assertEqual(team.task(b)['state'],'queued')
    def test_conflicting_facts_generate_owner_signal(self):
        self.fact();self.fact(content='700 people');proactive.scan(force=True);self.assertTrue(any(s['rule_id']=='conflict' for s in proactive.signals()))
    def test_baseline_no_secret_or_network_claim(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'DO_NOT_EXPOSE_KEY'}):data=baseline.report()
        text=json.dumps(data);self.assertNotIn('DO_NOT_EXPOSE_KEY',text);self.assertEqual(data['model_requests'],0);self.assertEqual(next(c for c in data['checks'] if c['area']=='Model access')['state'],'configured_unverified');self.assertEqual(len(data['deferred_gaps']),2)
    def test_baseline_capture_retains_history(self):
        baseline.capture();baseline.capture()
        with p.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM foundation_baselines').fetchone()[0],2)

class FoundationWebTests(WorkspaceBase):
    def setUp(self):
        super().setUp();self.cfg=config.Settings('https://superhuman.example',state_dir=Path('state'));auth.Store(self.cfg.auth_db).setup('owner','synthetic-test-passphrase');self.client=TestClient(web.create_app(self.cfg),base_url=self.cfg.public_origin);self.client.post('/login',data={'username':'owner','password':'synthetic-test-passphrase','csrf':self.csrf(self.client.get('/login'))})
    def tearDown(self):self.client.close();super().tearDown()
    def csrf(self,r):return re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
    def post(self,url,data,source='/storage'):
        return self.client.post(url,data=dict(data,csrf=self.csrf(self.client.get(source))),follow_redirects=False)
    def test_new_pages_render(self):
        for path in ('/storage','/storage/departments/marketing','/storage/departments/global','/storage/new?scope=marketing&kind=document','/storage/new?scope=global&kind=fact','/storage/search','/agent-personalities','/agent-personalities/twin','/proactive','/system-baseline'):
            with self.subTest(path=path):self.assertEqual(self.client.get(path).status_code,200)
    def test_storage_rename_and_legacy_redirect(self):
        self.assertIn('href="/storage"',self.client.get('/').text);self.assertEqual(self.client.get('/knowledge',follow_redirects=False).headers['location'],'/storage');self.assertIn('Superhuman',self.client.get('/twin').text)
    def test_document_register_form_accepts_filename(self):
        html=self.client.get('/storage/new?scope=marketing&kind=document').text;self.assertIn('name="filename"',html);self.assertNotIn('name="filename" value="" type="hidden"',html)
    def test_fact_save_history_and_search(self):
        result=self.post('/storage/save',dict(scope='global',kind='fact',title='<script>waitlist</script>',content='600 people',fact_key='edsync.waitlist',sensitivity='internal',access='twin',source='Owner',status='approved'));self.assertEqual(result.status_code,303);html=self.client.get(result.headers['location']).text;self.assertIn('&lt;script&gt;',html);self.assertIn('Version history',html);self.assertIn('600 people',self.client.get('/storage/search?q=waitlist').text)
    def test_auth_and_csrf_protect_new_endpoints(self):
        self.assertEqual(self.client.post('/proactive/scan').status_code,403);self.client.cookies.clear()
        for path in ('/storage','/system-baseline.json','/proactive','/agent-personalities'):
            self.assertEqual(self.client.get(path,follow_redirects=False).status_code,303)
    def test_manual_scan_does_not_create_tasks(self):
        self.project();self.assertEqual(self.post('/proactive/scan',{}).status_code,303);self.assertEqual(len(team.tasks()),0);self.assertTrue(proactive.signals())
    def test_profile_save_and_stale_edit(self):
        self.assertEqual(self.post('/agent-personalities/twin',dict(expected=1,style='Warm and candid'),'/agent-personalities/twin').status_code,303);self.assertEqual(self.post('/agent-personalities/twin',dict(expected=1,style='Stale'),'/agent-personalities/twin').status_code,409)
    def test_capture_and_download_saved_baseline(self):
        self.assertEqual(self.post('/system-baseline/capture',{},'/system-baseline').status_code,303);self.assertEqual(self.client.get('/system-baseline/saved/1').json()['model_requests'],0)
    def test_upload_and_register_document(self):
        csrf=self.csrf(self.client.get('/storage/departments/marketing'));r=self.client.post('/storage/upload',data=dict(scope='marketing',csrf=csrf),files={'file':('notes.txt',b'University pilot notes','text/plain')},follow_redirects=False);self.assertEqual(r.status_code,303);self.assertIn('notes.txt',r.headers['location']);self.assertIn('value="notes.txt"',self.client.get(r.headers['location']).text)
        self.assertEqual(self.client.post('/storage/upload',data=dict(scope='marketing',csrf=csrf),files={'file':('notes.txt',b'Overwrite','text/plain')},follow_redirects=False).status_code,409)
