"""Communications boundaries, durable cursors, source review, schedules and worker integration."""
import hashlib,hmac,json,os,re,time,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from superhuman.comms import store,providers,engine
from superhuman.team import store as team,budget,work
from superhuman.mail import store as mail,vault
from superhuman.hosted import worker,jobs,auth,web,config
from superhuman.projects import engine as p
from superhuman.repairs import checks
from test_team import TeamTests as Base,Metered,MODEL

def reply(**changes):
    result={'summary':'Here is the checked private overview.','items':[],'drafts':[],'tasks':[]};result.update(changes);return result

def payload(phone='123456789',ident='wamid.synthetic',body='Please review the signed plan.'):
    return json.dumps({'object':'whatsapp_business_account','entry':[{'changes':[{'field':'messages','value':{'metadata':{'phone_number_id':phone},'messages':[{'from':'923001234567','id':ident,'timestamp':str(int(time.time())),'type':'text','text':{'body':body}}]}}]}]}).encode()

class CommsTests(unittest.TestCase):
    setUp=Base.setUp
    tearDown=Base.tearDown
    boot_team=Base.boot
    def boot(self):
        self.boot_team();store.initialize();store.configure(store.settings()['version'],True,'Asia/Karachi','09:00','14:00','20:30',12)
    def channel(self,ai=True,kind='slack'):
        cid=store.connect(kind,kind.title(),'T123456' if kind=='slack' else '123456789','U123456' if kind=='slack' else '123456789',{'token':'synthetic-slack-token'} if kind=='slack' else {'app_secret':'appsecret-synthetic-value-12345','verify_token':'verify-synthetic-value-12345'})
        store.control_channel(cid,store.channel(cid)['version'],True,ai)
        if kind=='slack':store.add_stream(cid,'C123456','Selected conversation')
        return cid
    def source(self,cid,ident='C123456:123.000001',body='Please review this private plan.',received=None):
        with p.connect() as db:return store.ingest(db,store.channel(cid),ident,'C123456:123.000001','U234567','Private message',body,received or time.time(),'Bounded test preview')
    def enable_read(self,cid):store.control_channel(cid,store.channel(cid)['version'],True,True)
    def test_unconfigured_read_paths_do_not_create_database_or_request_work(self):
        self.assertFalse(store.settings()['enabled']);self.assertEqual(store.channels(),[]);self.assertIsNone(engine.tick(client=Metered()));self.assertFalse(p.DEFAULT_DB.exists())
    def test_setup_is_off_without_new_independent_employee(self):
        store.initialize();self.assertFalse(store.settings()['enabled']);self.assertEqual(len(team.employees()),8)
    def test_enable_requires_team_and_dollar_budget(self):
        store.initialize()
        with self.assertRaises(ValueError):store.configure(1,True,'Asia/Karachi','09:00','14:00','20:30')
    def test_schedule_validation_and_stale_setting_controls(self):
        self.boot();c=store.settings()
        for zone,times in [('Bad/Zone',('09:00','14:00','20:30')),('Asia/Karachi',('20:30','14:00','09:00')),('Asia/Karachi',('25:00','26:00','27:00'))]:
            with self.assertRaises(ValueError):store.configure(c['version'],True,zone,*times)
        store.configure(c['version'],False,'Asia/Karachi','09:00','14:00','20:30')
        with self.assertRaises(ValueError):store.configure(c['version'],True,'Asia/Karachi','09:00','14:00','20:30')
    def test_new_connections_start_with_read_and_ai_off(self):
        self.boot();cid=store.connect('slack','Workspace','T123456','U123456',{'token':'private-synthetic-token'});a=store.channel(cid);self.assertFalse(a['enabled']);self.assertFalse(a['ai_enabled']);self.assertNotIn('credential',a);self.assertNotIn('private-synthetic-token',store.channel(cid,secret=True)['credential'])
    def test_missing_existing_key_does_not_silently_replace_credentials(self):
        self.boot();self.channel();vault.key_path().unlink()
        with self.assertRaises(ValueError):self.channel(kind='whatsapp')
        self.assertFalse(vault.key_path().exists())
    def test_legacy_email_setup_cannot_replace_a_missing_communications_key(self):
        self.boot();self.channel();vault.key_path().unlink();mail.initialize()
        with self.assertRaises(ValueError):mail.connect('personal_gmail','owner@example.com','marketing',{'refresh_token':'synthetic'})
        self.assertFalse(vault.key_path().exists())
    def test_slack_identity_checked_before_saving(self):
        self.boot()
        with patch.object(providers,'slack_request',return_value={'team_id':'TOTHER00','user_id':'U123456'}),self.assertRaises(ValueError):providers.connect_slack('synthetic','T123456','Slack')
        self.assertEqual(store.channels(),[])
    def test_slack_auth_is_read_only_and_checks_account(self):
        self.boot()
        with patch.object(providers,'slack_request',return_value={'team_id':'T123456','user_id':'U123456'}) as req:cid=providers.connect_slack('synthetic','T123456','Slack')
        self.assertEqual(req.call_args.args[0],'auth.test');self.assertEqual(store.channel(cid)['identity'],'T123456')
        with self.assertRaises(ValueError):providers.slack_request('chat.postMessage','synthetic',{})
    def test_unselected_slack_conversations_are_never_polled(self):
        self.boot();cid=store.connect('slack','Slack','T123456','U123456',{'token':'synthetic'});self.enable_read(cid)
        with patch.object(providers,'slack_request') as req:self.assertIsNone(providers.slack_tick());req.assert_not_called()
    def test_slack_allowlist_validates_ids_and_stale_controls(self):
        self.boot();cid=self.channel();s=store.streams(cid)[0]
        with self.assertRaises(ValueError):store.add_stream(cid,'https://evil.example','Bad')
        store.control_stream(s['id'],s['version'],False)
        with self.assertRaises(ValueError):store.control_stream(s['id'],s['version'],True)
    def test_slack_pagination_pins_window_and_advances_only_on_terminal_page(self):
        self.boot();cid=self.channel();now=time.time();ts=format(now-5,'.6f');seen=[]
        def page(method,token,params):seen.append(params.copy());return {'ok':True,'messages':[{'ts':ts,'text':'First preview','user':'U234567'}],'has_more':True,'response_metadata':{'next_cursor':'cursor-2'}}
        with patch.object(providers,'slack_request',side_effect=page):providers.slack_tick()
        s=store.streams(cid)[0];self.assertEqual(s['watermark'],'0');self.assertEqual(s['cursor'],'cursor-2');self.assertTrue(s['floor']);ceiling=s['ceiling'];floor=s['floor']
        with patch('time.time',return_value=now+62),patch.object(providers,'slack_request',return_value={'ok':True,'messages':[],'has_more':False}) as req:providers.slack_tick()
        self.assertEqual(req.call_args.args[2]['latest'],ceiling);self.assertEqual(req.call_args.args[2]['oldest'],floor);self.assertEqual(req.call_args.args[2]['cursor'],'cursor-2');s=store.streams(cid)[0];self.assertEqual(s['watermark'],ceiling);self.assertEqual(s['cursor'],'');self.assertEqual(len(store.sources()),1)
    def test_slack_rate_limit_retains_cursor_and_delays_retry(self):
        self.boot();cid=self.channel();s=store.streams(cid)[0]
        with p.connect() as db:db.execute("UPDATE comms_streams SET cursor='saved-cursor',ceiling=?,floor='1' WHERE id=?",(str(time.time()),s['id']))
        with patch.object(providers,'slack_request',side_effect=providers.RateLimited(120)):r=providers.slack_tick()
        self.assertEqual(r['comms_read'],'slack_failed');self.assertEqual(store.streams(cid)[0]['cursor'],'saved-cursor');self.assertGreaterEqual(store.channel(cid)['next_poll'],time.time()+119)
    def test_slack_missing_continuation_does_not_advance_watermark(self):
        self.boot();cid=self.channel()
        with patch.object(providers,'slack_request',return_value={'ok':True,'messages':[],'has_more':True}):r=providers.slack_tick()
        self.assertEqual(r['comms_read'],'slack_failed');self.assertEqual(store.streams(cid)[0]['watermark'],'0')
    def test_slack_recent_threads_are_followed_separately(self):
        self.boot();cid=self.channel();now=time.time();root=format(now-20,'.6f')
        with patch.object(providers,'slack_request',return_value={'ok':True,'messages':[{'ts':root,'text':'Root','user':'U234567','reply_count':2}]}):providers.slack_tick()
        thread=next(s for s in store.streams(cid) if s['root']);self.assertEqual(thread['root'],root)
        with patch('time.time',return_value=now+62),patch.object(providers,'slack_request',return_value={'ok':True,'messages':[{'ts':format(now-10,'.6f'),'thread_ts':root,'text':'Reply','user':'U234567'}]}) as req:providers.slack_tick()
        self.assertEqual(req.call_args.args[0],'conversations.replies');self.assertEqual(len(store.sources()),2)
    def test_channel_revocation_during_slack_request_discards_result(self):
        self.boot();cid=self.channel()
        def changed(*a):store.control_channel(cid,store.channel(cid)['version'],False,False);return {'ok':True,'messages':[{'ts':format(time.time()-1,'.6f'),'text':'Private'}]}
        with patch.object(providers,'slack_request',side_effect=changed):self.assertEqual(providers.slack_tick()['comms_read'],'cancelled')
        self.assertEqual(store.sources(),[])
    def test_source_deduplication_and_edits_preserve_identity(self):
        self.boot();cid=self.channel();at=time.time();a=self.source(cid,received=at);b=self.source(cid,received=at);self.assertEqual(a,b);self.assertEqual(len(store.sources()),1);old=store.source(a);self.source(cid,body='Edited content',received=at);self.assertGreater(store.source(a)['version'],old['version']);self.assertNotEqual(store.source(a)['digest'],old['digest'])
    def test_duplicate_candidates_remain_separate_provenanced_sources(self):
        self.boot();cid=self.channel();body='This is the same sufficiently long message copied across selected conversations for review.';self.source(cid,body=body);self.source(cid,'C123456:124.000001',body=body);snap=engine.capture('intake');self.assertEqual(len(snap['aliases']),2);self.assertEqual(snap['context']['SOURCE_PREVIEWS'][1]['possible_duplicate_of'],'S1')
    def test_ai_consent_is_required_before_private_previews_enter_context(self):
        self.boot();cid=self.channel(ai=False);self.source(cid);self.assertEqual(engine.capture('intake')['aliases'],{});self.enable_read(cid);self.assertEqual(len(engine.capture('intake')['aliases']),1)
    def test_disabled_stream_excludes_old_cached_slack_from_model(self):
        self.boot();cid=self.channel();self.source(cid);s=store.streams(cid)[0];store.control_stream(s['id'],s['version'],False);self.assertEqual(engine.capture('intake')['aliases'],{})
    def test_email_cache_bridge_reuses_existing_read_only_connection(self):
        self.boot();mail.initialize();mail.connect('personal_gmail','owner@example.com','marketing',{'refresh_token':'synthetic'});cid=store.link_email('personal_gmail');self.enable_read(cid)
        with p.connect() as db:db.execute('INSERT INTO mail_messages VALUES(?,?,?,?,?,?,?,?,?)',('saved-email','personal_gmail','remote-email','sender@example.com','Subject','Date','Saved preview','No attachments',time.time()))
        self.assertEqual(providers.email_bridge(),1);self.assertEqual(providers.email_bridge(),0);self.assertEqual(store.sources()[0]['body'],'Saved preview');mail.disconnect('personal_gmail');self.assertEqual(engine.capture('intake')['aliases'],{})
    def test_whatsapp_requires_signature_and_matching_business_number(self):
        self.boot();cid=self.channel(kind='whatsapp');raw=payload();secret=vault.open_secret(store.channel(cid,secret=True)['credential'])
        with self.assertRaises(PermissionError):providers.whatsapp_ingest(raw,'sha256='+'0'*64)
        signature='sha256='+hmac.new(secret['app_secret'].encode(),raw,hashlib.sha256).hexdigest();self.assertEqual(providers.whatsapp_ingest(raw,signature),1);self.assertEqual(providers.whatsapp_ingest(raw,signature),1);self.assertEqual(len(store.sources()),1)
        wrong=payload(phone='999999999');providers.whatsapp_ingest(wrong,'sha256='+hmac.new(secret['app_secret'].encode(),wrong,hashlib.sha256).hexdigest());self.assertEqual(len(store.sources()),1)
    def test_whatsapp_disconnect_removes_connector_secret(self):
        self.boot();cid=self.channel(kind='whatsapp');store.control_channel(cid,store.channel(cid)['version'],False,False,True);self.assertEqual(providers.whatsapp_candidates(),[]);self.assertIsNone(store.channel(cid,secret=True)['credential'])
    def test_initialization_does_not_enable_any_real_connection(self):
        self.boot();self.assertEqual(store.channels(),[]);self.assertIsNone(providers.read_tick())
    def test_assistant_uses_twin_budget_and_keeps_proposals_unexecuted(self):
        self.boot();cid=self.channel();sid=self.source(cid);fake=Metered(reply(items=[{'source':'S1','category':'urgent','headline':'Review the plan','reason':'Verify the actual deadline.'}],drafts=[{'source':'S1','body':'Thank you. I will review the plan.'}],tasks=[{'source':'S1','department':'marketing','title':'Review plan','instruction':'Prepare a local assessment of the proposed plan.','acceptance':'A fact-checked local note.'}]))
        result=engine.tick(client=fake);self.assertEqual(result['status'],'done');self.assertEqual(fake.calls,1);self.assertEqual(budget.report()['costs'][0]['pool'],'twin');self.assertEqual(len(store.alerts()),1);self.assertEqual(len(store.drafts()),1);self.assertEqual(len(store.proposals()),1);self.assertEqual(team.tasks(),[]);self.assertEqual(store.source(sid)['digest'],store.source(sid)['analysed_digest'])
    def test_malformed_or_unavailable_source_response_is_held_without_replay(self):
        self.boot();cid=self.channel();self.source(cid);fake=Metered(reply(items=[{'source':'S99','category':'urgent','headline':'No','reason':'No'}]));result=engine.tick(client=fake);self.assertEqual(result['status'],'interrupted');self.assertEqual(store.alerts(),[])
        with patch('time.time',return_value=time.time()+601):self.assertIsNone(engine.tick(client=Metered()))
    def test_context_change_during_model_request_discards_output(self):
        self.boot();cid=self.channel();self.source(cid)
        def change():store.control_channel(cid,store.channel(cid)['version'],False,False);return reply()
        result=engine.tick(client=Metered(change));self.assertEqual(result['status'],'interrupted');self.assertEqual(store.sources()[0]['analysed_digest'],'')
    def test_owner_update_during_model_request_invalidates_decision(self):
        self.boot();cid=self.channel();self.source(cid)
        def change():team.add_message('temporary_constraint','Do not share this today.',time.time()+3600);return reply()
        self.assertEqual(engine.tick(client=Metered(change))['status'],'interrupted')
    def test_unknown_usage_retains_reservation_and_no_request_replay(self):
        from test_agentic import Client
        self.boot();cid=self.channel();self.source(cid);self.assertEqual(engine.tick(client=Client(reply()))['status'],'done');self.assertEqual(budget.report()['costs'][0]['state'],'uncertain');self.assertIsNone(engine.tick(client=Metered()))
    def test_dollar_guard_blocks_before_provider(self):
        self.boot();cid=self.channel();self.source(cid);budget.set_rate(MODEL,'100','100','Synthetic expensive');fake=Metered(reply());self.assertEqual(engine.tick(client=fake)['status'],'blocked');self.assertEqual(fake.calls,0)
    def test_scheduled_briefs_are_idempotent_in_pakistan_time(self):
        self.boot();fixed=datetime.now(timezone(timedelta(hours=5))).replace(hour=15,minute=0,second=0,microsecond=0)
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return fixed.astimezone(tz or timezone.utc)
        with p.connect() as db:db.execute('UPDATE comms_settings SET activated=?',(fixed.replace(hour=8).timestamp(),))
        with patch.object(engine,'datetime',Clock):ident=engine.schedule();self.assertIsNone(engine.schedule())
        r=store.run(ident);self.assertIn(':midday',r['submission']);self.assertEqual(sum(r['status']=='skipped' for r in store.runs()),1)
    def test_later_slot_supersedes_queued_earlier_brief(self):
        self.boot();fixed=datetime.now(timezone(timedelta(hours=5))).replace(hour=15,minute=0,second=0,microsecond=0)
        with p.connect() as db:db.execute('UPDATE comms_settings SET activated=?',(fixed.replace(hour=8).timestamp(),))
        morning=engine.enqueue('briefing','schedule:'+fixed.date().isoformat()+':morning')
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return fixed.astimezone(tz or timezone.utc)
        with patch.object(engine,'datetime',Clock):engine.schedule()
        self.assertEqual(store.run(morning)['status'],'skipped')
    def test_email_cache_copy_does_not_claim_a_fresh_remote_read(self):
        self.boot();mail.initialize();mail.connect('personal_gmail','owner@example.com','marketing',{'refresh_token':'synthetic'});cid=store.link_email('personal_gmail');self.enable_read(cid)
        with p.connect() as db:
            db.execute("UPDATE mail_accounts SET last_sync='2026-10-01T00:00:00+00:00' WHERE id='personal_gmail'")
            db.execute('INSERT INTO mail_messages VALUES(?,?,?,?,?,?,?,?,?)',('cached','personal_gmail','remote','sender','Subject','Date','Cached body','No attachments',time.time()))
        providers.email_bridge();coverage=engine.capture('intake')['context']['coverage'][0];self.assertEqual(coverage['last_successful_read'],'2026-10-01T00:00:00+00:00');self.assertEqual(store.channel(cid)['last_sync'],'2026-10-01T00:00:00+00:00')
    def test_enabling_after_a_slot_does_not_backfill_old_briefs(self):
        self.boot();fixed=datetime.now(timezone(timedelta(hours=5))).replace(hour=15,minute=0,second=0,microsecond=0)
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return fixed.astimezone(tz or timezone.utc)
        with p.connect() as db:db.execute('UPDATE comms_settings SET activated=?',(fixed.timestamp(),))
        with patch.object(engine,'datetime',Clock):self.assertIsNone(engine.schedule())
    def test_manual_briefing_submission_is_idempotent(self):
        self.boot();a=engine.enqueue('briefing','manual:synthetic');b=engine.enqueue('briefing','manual:synthetic');self.assertEqual(a,b)
    def test_daily_ceiling_reserves_three_slots_for_scheduled_briefs(self):
        self.boot();cid=self.channel();self.source(cid)
        with p.connect() as db:
            for _ in range(9):store.event(db,'model_attempt_started',{},'twin')
        fake=Metered(reply());self.assertIsNone(engine.tick(client=fake));self.assertEqual(fake.calls,0)
    def test_private_proposal_requires_owner_and_restricted_destination(self):
        self.boot();cid=self.channel();self.source(cid);engine.tick(client=Metered(reply(tasks=[{'source':'S1','department':'marketing','title':'Review source','instruction':'Prepare a bounded private note.','acceptance':'Evidence-supported note.'}])));pr=store.proposals()[0];q=team.create_project('marketing','Public','Public goal','Criteria')
        with self.assertRaises(ValueError):store.route(pr['id'],pr['version'],q,'Share this privately.')
        private=team.create_project('marketing','Private','Review private material','Fact checked','P2','consequential','restricted');tid=store.route(pr['id'],pr['version'],private,'I authorize this private department assignment.');self.assertEqual(team.task(tid)['state'],'queued');self.assertTrue(team.needs_owner(team.task(tid)))
        with self.assertRaises(ValueError):store.route(pr['id'],pr['version'],private,'Again')
    def test_private_assignment_excludes_public_web_tools(self):
        self.boot();q=team.create_project('marketing','Private','Review locally','Checked','P2','consequential','restricted');tid=team.create_task(q,'marketing','Local note','Prepare local assessment','Checked');t=team.task(tid);work.task_control(tid,t['version'],'approve_start');pid=work.dispatch(tid,team.task(tid)['version']);from superhuman.agentic import store as agent
        self.assertNotIn('research.web',agent.get(pid)['allowed_tools'])
    def test_existing_private_run_has_an_owner_repair_control(self):
        self.boot();q=team.create_project('marketing','Private','Review locally','Checked','P2','consequential','restricted');tid=team.create_task(q,'marketing','Local note','Prepare local assessment','Checked');work.task_control(tid,team.task(tid)['version'],'approve_start');pid=work.dispatch(tid,team.task(tid)['version'])
        from superhuman.agentic import store as agent
        run=agent.get(pid)
        with p.connect() as db:db.execute('UPDATE agentic_runs SET allowed_tools=? WHERE project_id=?',(team.encode(run['allowed_tools']+['research.web']),pid))
        self.assertFalse(work.gate(team.task(tid))[0]);work.task_control(tid,team.task(tid)['version'],'restrict_private_tools','I inspected this private run and removed public research.');self.assertTrue(work.gate(team.task(tid))[0]);self.assertNotIn('research.web',agent.get(pid)['allowed_tools'])
    def test_changed_source_blocks_draft_and_specialist_sharing(self):
        self.boot();cid=self.channel();sid=self.source(cid);engine.tick(client=Metered(reply(drafts=[{'source':'S1','body':'Draft'}],tasks=[{'source':'S1','department':'marketing','title':'Private task','instruction':'Review facts.','acceptance':'A note.'}])));self.source(cid,body='Changed source');d=store.drafts()[0]
        with self.assertRaises(ValueError):store.edit_draft(d['id'],d['version'],'New draft')
        pr=store.proposals()[0];q=team.create_project('marketing','Private','Review','Checked','P2','consequential','restricted')
        with self.assertRaises(ValueError):store.route(pr['id'],pr['version'],q,'Authorize')
    def test_restart_interrupts_model_job_without_replaying(self):
        self.boot();cid=self.channel();self.source(cid);ident=engine.enqueue()
        with p.connect() as db:db.execute("UPDATE comms_runs SET status='running' WHERE id=?",(ident,))
        self.assertEqual(engine.recover(),1);self.assertEqual(store.run(ident)['status'],'interrupted');self.assertEqual(engine.recover(),0)
    def test_owner_retry_is_atomic_and_cannot_duplicate_paid_jobs(self):
        self.boot();cid=self.channel();self.source(cid);ident=engine.enqueue()
        with p.connect() as db:db.execute("UPDATE comms_runs SET status='interrupted' WHERE id=?",(ident,))
        row=store.run(ident)
        def attempt(_):
            try:return engine.retry(ident,row['version'],'I inspected the interrupted request.')
            except ValueError:return None
        with ThreadPoolExecutor(2) as pool:result=list(pool.map(attempt,range(2)))
        self.assertEqual(sum(x is not None for x in result),1);self.assertEqual(sum(r['status']=='queued' for r in store.runs()),1)
    def test_invalid_provider_reply_cannot_acknowledge_or_share_source(self):
        self.boot();cid=self.channel();sid=self.source(cid);engine.tick(client=Metered({'summary':'Missing required fields'}));self.assertEqual(store.source(sid)['analysed_digest'],'');self.assertEqual(store.drafts(),[]);self.assertEqual(store.proposals(),[])
    def test_rollback_preserves_sources_but_disables_all_background_work(self):
        self.boot();cid=self.channel();sid=self.source(cid);engine.enqueue();engine.quarantine_for_rollback();self.assertFalse(store.settings()['enabled']);self.assertFalse(team.enabled());self.assertFalse(store.channel(cid)['enabled']);self.assertTrue(jobs.worker_status()['paused']);self.assertEqual(store.source(sid)['body'],'Please review this private plan.');self.assertTrue(all(r['status']=='cancelled' for r in store.runs()))
    def test_worker_runs_assistant_in_existing_loop(self):
        self.boot();cid=self.channel();self.source(cid);results=[]
        with patch('superhuman.mail.providers.run_sync',return_value=None),patch('superhuman.comms.providers.read_tick',return_value=None):worker.serve(once=True,client=Metered(reply()),report=results.append)
        self.assertEqual(results[0]['status'],'done');self.assertIn('comms_cycle_id',results[0])
    def test_diagnostics_include_status_without_credentials(self):
        self.boot();self.channel();r=checks.report();self.assertEqual(r['version'],'1.31.0');self.assertFalse(r['communications']['external_sending']);self.assertNotIn('token',json.dumps(r['communications']))
    def test_parser_rejects_duplicate_json_keys_and_unknown_fields(self):
        for raw in ('{"summary":"A","summary":"B","items":[],"drafts":[],"tasks":[]}',json.dumps({**reply(),'send':True})):
            with self.assertRaises(ValueError):engine.parse(raw,{})
    def test_common_secrets_are_masked_before_model_context(self):
        self.boot();cid=self.channel();self.source(cid,body='Password: secret-password\nOpen https://private.example/key to join');value=engine.capture('intake')['context']['SOURCE_PREVIEWS'][0]['body'];self.assertNotIn('secret-password',value);self.assertNotIn('https://',value)
    def test_preview_archive_blocks_pending_analysis(self):
        self.boot();cid=self.channel();sid=self.source(cid);ident=engine.enqueue();s=store.source(sid);store.archive(sid,s['version']);self.assertFalse(engine.valid(json.loads(store.run(ident)['snapshot'])))
    def test_web_auth_csrf_signed_ingress_and_private_pages(self):
        self.boot();cid=self.channel(kind='whatsapp');settings=config.Settings('https://superhuman.example',state_dir=Path('state'));auth.Store(settings.auth_db).setup('owner','synthetic-test-passphrase')
        csrf=lambda r:re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
        with TestClient(web.create_app(settings),base_url=settings.public_origin) as c:
            self.assertEqual(c.get('/assistant',follow_redirects=False).status_code,303)
            self.assertEqual(c.post('/assistant/brief',data={}).status_code,401)
            self.assertEqual(c.get('/hooks/whatsapp',params={'hub.mode':'subscribe','hub.verify_token':'verify-synthetic-value-12345','hub.challenge':'123456'}).text,'123456')
            self.assertEqual(c.get('/hooks/whatsapp',params={'hub.mode':'subscribe','hub.verify_token':'wrong','hub.challenge':'123456'}).status_code,403)
            raw=payload(body='<script>private()</script>');sig='sha256='+hmac.new(b'appsecret-synthetic-value-12345',raw,hashlib.sha256).hexdigest();self.assertEqual(c.post('/hooks/whatsapp',content=raw,headers={'content-type':'application/json','x-hub-signature-256':sig}).status_code,200)
            self.assertEqual(c.post('/hooks/whatsapp',content=raw,headers={'content-type':'application/json'}).status_code,403)
            self.assertEqual(c.post('/hooks/whatsapp/anything',content=raw).status_code,401)
            token=csrf(c.get('/login'));c.post('/login',data={'csrf':token,'username':'owner','password':'synthetic-test-passphrase'})
            for url in ('/assistant','/assistant/settings','/assistant/connections','/team/twin'):self.assertEqual(c.get(url).status_code,200)
            self.assertEqual(c.post('/assistant/settings',data={}).status_code,403)
            sid=store.sources()[0]['id'];self.assertNotIn('<script>private()',c.get('/assistant/sources/'+sid).text);self.assertIn('&lt;script&gt;',c.get('/assistant/sources/'+sid).text)
            self.assertEqual(c.post('/hooks/whatsapp',content=b'x'*262145,headers={'content-type':'application/json','x-hub-signature-256':'sha256='+'0'*64}).status_code,413)

del Base
