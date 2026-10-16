from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch
from uuid import uuid4
from fastapi.testclient import TestClient
from superhuman.briefing import engine,web as briefing_web
from superhuman.mail import store,providers
from superhuman.dialogue import store as dialogue,engine as dialogue_engine
from superhuman.hosted import auth,config,web
from superhuman.projects import engine as projects

SLOT='personal_gmail'
SECRET='Password: 876543\nJoin https://zoom.us/j/123456789?pwd=SECRET\nAccount id: 12345678-1234-1234-1234-123456789abc\nPlease review the renewal on 22 October 2026.'


def response(items=None,tasks=None):
    return {'overview':'A renewal needs review.','items':items if items is not None else [
        {'priority':'decision','headline':'Check the subscription renewal','reason':'The email says renewal is on 22 October; verify the seat count.',
         'sources':['E1'],'meeting_at':''}],'newsletter_count':0,'tasks':tasks or []}


class Model:
    def __init__(self,value=None):self.value=value or response();self.calls=[];self.chat=N(completions=N(create=self.create))
    def create(self,**kwargs):
        self.calls.append(kwargs)
        return N(choices=[N(finish_reason='stop',message=N(refusal=None,content=json.dumps(self.value)))])


class BriefingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=Path.cwd();os.chdir(self.temp.name)
        self.env=patch.dict(os.environ,{'SUPERHUMAN_MAIL_KEY_FILE':str(Path('private/key').resolve())});self.env.start()
        store.initialize()
    def tearDown(self):self.env.stop();os.chdir(self.old);self.temp.cleanup()
    def seed(self,slot=SLOT,body=SECRET):
        store.connect(slot,slot+'@example.com',dialogue.scopes()[0],{'password':'synthetic'},host=store.HOSTS['godaddy'] if slot=='edsync_titan' else None)
        store.queue_sync(slot);job=store.claim()
        store.finish_sync(job,[providers.parse_message(('From: Partner <partner@example.com>\r\nSubject: Renewal\r\nDate: Thu, 15 Oct 2026 17:50:00 +0000\r\n\r\n'+body).encode(),'one')])
    def report(self):return store.make_report(SLOT,uuid4().hex)
    def trace(self):
        self.seed();self.report();claimed=dialogue.claim();messages,trace=engine.mail_prompt(claimed)
        return messages,trace
    def test_local_time_iso_and_rfc_dates(self):
        self.assertEqual(engine.local_time('2026-10-15T20:24:08Z'),'16 Oct 2026, 01:24 AM PKT')
        self.assertEqual(engine.local_time('Thu, 15 Oct 2026 17:50:00 +0000'),'15 Oct 2026, 10:50 PM PKT')
    def test_invalid_or_naive_time_not_invented(self):
        for value in ('bad','',None,'2026-10-15T20:24:08'):
            self.assertEqual(engine.local_time(value),'Time not available')
    def test_common_passwords_codes_and_links_masked(self):
        clean=engine.scrub(SECRET)
        for secret in ('876543','https://zoom','SECRET','123456789abc'):self.assertNotIn(secret,clean)
        self.assertIn('22 October 2026',clean)
    def test_tokens_and_long_numeric_identifiers_masked(self):
        text=engine.scrub('Bearer abcdefghijklmnop\nOTP: 123456\nsk-proj-abcdefghijklm\n987654321')
        for value in ('abcdefghijklmnop','123456','sk-proj','987654321'):self.assertNotIn(value,text)
    def test_secret_removal_before_model_and_sources_have_aliases(self):
        messages,trace=self.trace();prompt=json.dumps(messages)
        for value in ('876543','zoom.us','123456789abc'):self.assertNotIn(value,prompt)
        self.assertIn('E1',prompt);self.assertNotIn(trace['sources']['E1']['source_id'],prompt)
    def test_message_ids_kept_only_in_private_trace(self):
        messages,trace=self.trace();self.assertTrue(re.fullmatch(r'[a-f0-9]{32}',trace['sources']['E1']['source_id']))
    def test_prompt_has_past_event_and_newsletter_rules(self):
        messages,trace=self.trace();self.assertIn('past_event',messages[0]['content']);self.assertIn('Group newsletters',messages[0]['content'])
    def test_strict_schema_selected_for_first_report(self):
        self.seed();thread=self.report();model=Model();result=dialogue_engine.run_turn(client=model)
        self.assertEqual(result['status'],'done');call=model.calls[0]
        self.assertEqual(call['response_format']['json_schema']['name'],'superhuman_inbox_briefing');self.assertNotIn('tools',call)
        self.assertEqual(dialogue.get(thread)['used_calls'],1)
    def test_structured_report_saved_atomically_in_context(self):
        self.seed();thread=self.report();dialogue_engine.run_turn(client=Model())
        turn=dialogue.turns(thread)[0];context=json.loads(turn['context_json'])
        self.assertEqual(context['briefing']['items'][0]['priority'],'decision');self.assertEqual(turn['status'],'done')
    def test_past_event_cannot_stay_current_attention(self):
        _,trace=self.trace();trace['analysed_at']='2026-10-16T00:00:00Z'
        value=response([dict(priority='attention',headline='Meeting reminder',reason='Check whether follow-up is needed.',sources=['E1'],meeting_at='2026-10-15T17:00:00Z')])
        parsed=engine.parse(json.dumps(value),dialogue.scopes()[0],trace)
        self.assertEqual(parsed['briefing']['items'][0]['priority'],'past_event')
    def test_future_event_keeps_priority(self):
        _,trace=self.trace();trace['analysed_at']='2026-10-16T00:00:00Z'
        value=response([dict(priority='attention',headline='Meeting tomorrow',reason='Prepare a draft.',sources=['E1'],meeting_at='2026-10-17T17:00:00Z')])
        self.assertEqual(engine.parse(json.dumps(value),dialogue.scopes()[0],trace)['briefing']['items'][0]['priority'],'attention')
    def test_invalid_event_time_rejected(self):
        _,trace=self.trace();value=response();value['items'][0]['meeting_at']='tomorrow'
        with self.assertRaises(ValueError):engine.parse(json.dumps(value),dialogue.scopes()[0],trace)
    def test_unknown_email_reference_rejected(self):
        _,trace=self.trace();value=response();value['items'][0]['sources']=['E99']
        with self.assertRaisesRegex(ValueError,'unavailable'):engine.parse(json.dumps(value),dialogue.scopes()[0],trace)
    def test_missing_or_duplicate_sources_rejected(self):
        _,trace=self.trace()
        for sources in ([],['E1','E1']):
            value=response();value['items'][0]['sources']=sources
            with self.assertRaises(ValueError):engine.parse(json.dumps(value),dialogue.scopes()[0],trace)
    def test_oversized_report_rejected_no_silent_truncation(self):
        _,trace=self.trace();value=response();value['overview']='x'*1201
        with self.assertRaises(ValueError):engine.parse(json.dumps(value),dialogue.scopes()[0],trace)
    def test_longer_prose_shown_concisely_without_failing_or_losing_detail(self):
        _,trace=self.trace();value=response();value['overview']='Useful context. '*30;value['items'][0]['reason']='Important evidence and deadline. '*20
        clean=engine.parse(json.dumps(value),dialogue.scopes()[0],trace)['briefing']
        self.assertLessEqual(len(clean['overview']),240);self.assertEqual(clean['overview_full'],value['overview'].strip())
        self.assertLessEqual(len(clean['items'][0]['reason']),240);self.assertEqual(clean['items'][0]['reason_full'],value['items'][0]['reason'].strip())
    def test_newsletter_count_is_bounded_by_snapshot(self):
        _,trace=self.trace()
        for count in (True,-1,13,'3'):
            value=response();value['newsletter_count']=count
            with self.assertRaises(ValueError):engine.parse(json.dumps(value),dialogue.scopes()[0],trace)
    def test_invalid_briefing_fails_without_automatic_retry(self):
        self.seed();thread=self.report();value=response();value['items'][0]['sources']=['E99'];model=Model(value)
        self.assertEqual(dialogue_engine.run_turn(client=model)['status'],'failed');self.assertIsNone(dialogue_engine.run_turn(client=model))
        self.assertEqual(dialogue.suggestions(thread),[]);self.assertEqual(len(model.calls),1)
    def test_research_task_rejected(self):
        _,trace=self.trace();value=response(tasks=[dict(kind='research',title='Search',details='Private facts',rationale='No',sources=['E1'])])
        with self.assertRaisesRegex(ValueError,'local drafting'):engine.parse(json.dumps(value),dialogue.scopes()[0],trace)
    def test_draft_tasks_remain_proposed_and_approve_once(self):
        self.seed();thread=self.report();value=response(tasks=[dict(kind='collab',title='Draft renewal checklist',details='Create a local seat-count review checklist.',rationale='Review before renewal.',sources=['E1'])])
        dialogue_engine.run_turn(client=Model(value));suggestion=dialogue.suggestions(thread)[0]
        self.assertEqual(projects.listing(),[]);self.assertIn('Personal Gmail sources: E1',suggestion['details'])
        args=(thread,suggestion['id'],suggestion['proposal_hash'],suggestion['title'],suggestion['details'])
        self.assertEqual(dialogue.approve(*args),dialogue.approve(*args));self.assertEqual(len(projects.listing()),1)
    def test_model_output_masked_in_rendered_briefing(self):
        _,trace=self.trace();value=response();value['overview']='Password: 876543'
        parsed=engine.parse(json.dumps(value),dialogue.scopes()[0],trace);self.assertNotIn('876543',parsed['reply'])
    def test_legacy_snapshot_and_reply_retained_but_new_context_masked(self):
        self.seed();thread=self.report()
        with projects.connect() as db:
            db.execute("UPDATE dialogue_turns SET status='done',reply=? WHERE thread_id=?",(SECRET,thread))
        dialogue.set_budget(thread,2);dialogue.send(thread,'Explain the follow-up',uuid4().hex);claimed=dialogue.claim()
        messages,trace=engine.mail_prompt(claimed);self.assertFalse(trace['briefing_mode']);self.assertNotIn('876543',json.dumps(messages))
        self.assertIn('876543',dialogue.turns(thread)[0]['reply'])
    def test_account_context_does_not_mix(self):
        self.seed(body='ONLY-PERSONAL');self.seed('edsync_gmail',body='ONLY-EDSYNC');thread=self.report()
        with patch('superhuman.identity.selection.select_context',side_effect=AssertionError('No memory')):
            model=Model();dialogue_engine.run_turn(client=model)
        prompt=json.dumps(model.calls[0]['messages']);self.assertIn('ONLY-PERSONAL',prompt);self.assertNotIn('ONLY-EDSYNC',prompt)
    def test_batch_is_idempotent_under_concurrent_submit(self):
        self.seed();self.seed('edsync_gmail');key=uuid4().hex
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:briefing_web.bulk_reports('personal_gmail,edsync_gmail',key),[1,2]))
        self.assertEqual([r['thread_id'] for r in results[0]],[r['thread_id'] for r in results[1]])
        with projects.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM mail_reports').fetchone()[0],2)
        self.assertEqual(projects.listing(),[])
    def test_batch_skips_disconnected_or_empty_account(self):
        self.seed();result=briefing_web.bulk_reports('personal_gmail,nextstep_gmail',uuid4().hex)
        self.assertEqual(result[0]['status'],'queued_or_already_submitted');self.assertEqual(result[1]['status'],'skipped')
    def test_batch_rejects_unknown_and_duplicate_accounts(self):
        for accounts in ('','unknown','personal_gmail,personal_gmail'):
            with self.assertRaises(ValueError):briefing_web.bulk_reports(accounts,uuid4().hex)
    def test_sources_survive_preview_retention(self):
        self.seed();self.report()
        with projects.connect() as db:
            report=db.execute('SELECT id FROM mail_reports').fetchone()[0];db.execute('DELETE FROM mail_messages')
        value=briefing_web.source(report,'E1');self.assertIn('renewal',value['message']['body']);self.assertNotIn('876543',value['message']['body'])
    def test_source_cannot_reference_outside_snapshot(self):
        self.seed();self.report()
        with projects.connect() as db:report=db.execute('SELECT id FROM mail_reports').fetchone()[0]
        with self.assertRaises(ValueError):briefing_web.source(report,'E2')
    def test_original_snapshot_not_changed_by_redaction(self):
        self.seed();self.report();claimed=dialogue.claim();engine.mail_prompt(claimed)
        with projects.connect() as db:self.assertIn('876543',db.execute('SELECT snapshot FROM mail_reports').fetchone()[0])
    def test_display_reclassifies_meeting_that_passed_since_report(self):
        value=response([dict(priority='attention',headline='Meeting',reason='A meeting was scheduled.',sources=['E1'],meeting_at='2026-10-15T17:00:00Z')])
        row={'status':'done','context_json':json.dumps({'briefing':value})}
        displayed=briefing_web.structured(row,at=datetime(2026,10,16,tzinfo=timezone.utc))
        self.assertEqual(displayed['items'][0]['priority'],'past_event')
        self.assertEqual(json.loads(row['context_json'])['briefing']['items'][0]['priority'],'attention')



class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=Path.cwd();os.chdir(self.temp.name)
        self.env=patch.dict(os.environ,{'SUPERHUMAN_MAIL_KEY_FILE':str(Path('private/key').resolve())});self.env.start()
        settings=config.Settings('https://superhuman.example',state_dir=Path('state'));auth.Store(settings.auth_db).setup('owner','private-test-password')
        self.client=TestClient(web.create_app(settings),base_url=settings.public_origin)
    def tearDown(self):self.client.close();self.env.stop();os.chdir(self.old);self.temp.cleanup()
    def csrf(self,response):return re.search(r'name="csrf" value="([^"]+)"',response.text).group(1)
    def login(self):self.client.post('/login',data={'username':'owner','password':'private-test-password','csrf':self.csrf(self.client.get('/login'))})
    def seed(self):
        store.connect(SLOT,'owner@example.com',dialogue.scopes()[0],{'password':'synthetic'});store.queue_sync(SLOT)
        store.finish_sync(store.claim(),[providers.parse_message(('From: Partner\r\nSubject: <script>evil()</script>\r\n\r\n'+SECRET).encode(),'one')])
    def test_private_pages_require_login(self):
        for path in ('/briefing','/briefing/source/unknown/E1'):
            self.assertEqual(self.client.get(path,follow_redirects=False).status_code,303)
    def test_mobile_page_and_all_four_account_labels(self):
        self.login();r=self.client.get('/briefing');self.assertEqual(r.status_code,200);self.assertIn('width=device-width',r.text)
        for label,_ in store.SLOTS.values():self.assertIn(label,r.text)
        self.assertEqual(r.headers['cache-control'],'no-store')
    def test_read_and_report_forms_require_csrf(self):
        self.login();self.seed()
        for action in ('read','report'):
            self.assertEqual(self.client.post('/briefing/'+action,data={'accounts':SLOT,'submission_key':uuid4().hex}).status_code,403)
        r=self.client.get('/briefing');forms=re.findall(r'<form\b[^>]*method="post"[^>]*>(.*?)</form>',r.text,re.S)
        self.assertTrue(all('name="csrf"' in form for form in forms))
    def test_read_queues_without_provider_or_paid_call(self):
        self.login();self.seed();csrf=self.csrf(self.client.get('/briefing'))
        with patch.object(providers,'run_sync',side_effect=AssertionError('Only worker may read')):
            r=self.client.post('/briefing/read',data={'csrf':csrf,'accounts':SLOT},follow_redirects=False)
        self.assertEqual(r.status_code,303);self.assertEqual(projects.listing(),[])
    def test_batch_cost_and_approval_visible(self):
        self.login();self.seed();r=self.client.get('/briefing')
        self.assertIn('up to 1 model attempts',r.text);self.assertIn('Tasks wait for your approval',r.text)
        csrf=self.csrf(r);key=uuid4().hex
        self.client.post('/briefing/report',data={'csrf':csrf,'accounts':SLOT,'submission_key':key})
        self.client.post('/briefing/report',data={'csrf':csrf,'accounts':SLOT,'submission_key':key})
        with projects.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM mail_reports').fetchone()[0],1)
    def test_new_report_renders_clickable_sources_and_no_password(self):
        self.login();self.seed();store.make_report(SLOT,uuid4().hex);dialogue_engine.run_turn(client=Model())
        r=self.client.get('/briefing');self.assertIn('Email E1',r.text);self.assertIn('Decision needed',r.text);self.assertNotIn('876543',r.text)
        url=re.search(r'href="(/briefing/source/[^\"]+)"',r.text).group(1);source=self.client.get(url)
        self.assertEqual(source.status_code,200);self.assertNotIn('<script>',source.text);self.assertNotIn('876543',source.text);self.assertIn('&lt;script&gt;',source.text)
    def test_legacy_report_not_copied_into_dashboard(self):
        self.login();self.seed();thread=store.make_report(SLOT,uuid4().hex)
        with projects.connect() as db:db.execute("UPDATE dialogue_turns SET status='done',reply=? WHERE thread_id=?",(SECRET,thread))
        r=self.client.get('/briefing');self.assertIn('Earlier reports keep their original format',r.text);self.assertNotIn('876543',r.text)
    def test_bad_source_reference_404(self):
        self.login();self.assertEqual(self.client.get('/briefing/source/unknown/E99').status_code,404)
    def test_stale_report_warning(self):
        self.login();self.seed();store.make_report(SLOT,uuid4().hex);dialogue_engine.run_turn(client=Model())
        with projects.connect() as db:db.execute("UPDATE mail_reports SET created_at='2020-01-01T00:00:00+00:00'")
        self.assertIn('over 12 hours old',self.client.get('/briefing').text)


if __name__=='__main__':unittest.main()
