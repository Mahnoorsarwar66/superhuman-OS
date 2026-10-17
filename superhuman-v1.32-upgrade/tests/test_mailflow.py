from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import uuid4
from superhuman.mail import store,providers
from superhuman.mailflow import state,engine
from superhuman.dialogue import store as dialogue
from superhuman.projects import engine as p


class Session:
    validity=''
    def __init__(self,count=60,fail=None):self.count=count;self.fail=fail;self.fetched=[];self.listed=[];self.closed=False
    def discover(self,scan,c):
        start=int(c['token'] or 0);end=min(start+30,self.count);self.listed.append(start)
        return [str(i) for i in range(start,end)],str(end) if end<self.count else '',end>=self.count,False
    def fetch(self,remote_id,scan):
        if remote_id==self.fail:raise RuntimeError('PRIVATE-TOKEN')
        self.fetched.append(remote_id)
        return providers.parse_message(b'From: sender@example.com\r\nSubject: Test\r\n\r\nEvidence',remote_id,received=time.time())
    def close(self):self.closed=True


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=Path.cwd();os.chdir(self.temp.name)
        self.env=patch.dict(os.environ,{'SUPERHUMAN_MAIL_KEY_FILE':str(Path('private/key').resolve())});self.env.start()
        store.connect('personal_gmail','owner@example.com',dialogue.scopes()[0],{'refresh_token':'synthetic'})
    def tearDown(self):self.env.stop();os.chdir(self.old);self.temp.cleanup()
    def run_pass(self,session):
        with patch.object(engine,'session_factory',return_value=session):return engine.run_sync()
    def complete(self,session):
        store.queue_sync('personal_gmail')
        for _ in range(20):
            result=self.run_pass(session)
            if result is None or result['status']!='active':return result
        self.fail('Scan did not terminate')
    def report(self):return store.make_report('personal_gmail',uuid4().hex)
    def mark(self,thread,status):
        with p.connect() as db:db.execute('UPDATE dialogue_turns SET status=? WHERE thread_id=?',(status,thread))
    def test_more_than_25_emails_are_read_across_continuations(self):
        session=Session(65);result=self.complete(session)
        self.assertEqual(result['status'],'complete');self.assertEqual(len(store.messages('personal_gmail',limit=100)),65)
        self.assertEqual(len(session.fetched),65);self.assertTrue(session.closed)
    def test_page_tokens_resume_across_passes(self):
        session=Session(65);store.queue_sync('personal_gmail');first=self.run_pass(session)
        self.assertEqual(first['status'],'active');self.assertEqual(len(session.fetched),25)
        self.assertEqual(state.summary('personal_gmail')['scan']['processed'],25)
        while self.run_pass(session)['status']=='active':pass
        self.assertEqual(session.listed,[0,30,60])
    def test_completed_scan_skips_previously_saved_ids_in_new_window(self):
        session=Session(40);self.complete(session);previous=len(session.fetched)
        self.complete(session);self.assertEqual(len(session.fetched),previous)
    def test_new_mail_is_found_on_next_scan(self):
        session=Session(2);self.complete(session);session.count=3;self.complete(session)
        self.assertEqual(session.fetched,['0','1','2'])
    def test_failure_keeps_successful_messages_and_failed_cursor(self):
        session=Session(10,fail='3');result=self.complete(session)
        self.assertEqual(result['status'],'failed');self.assertEqual(len(store.messages('personal_gmail')),3)
        with p.connect() as db:c=json.loads(db.execute('SELECT cursor FROM mail_scans').fetchone()[0])
        self.assertEqual(c['pending'][0],'3');self.assertNotIn('PRIVATE-TOKEN',store.account('personal_gmail')['last_error'])
        session.fail=None;self.complete(session);self.assertEqual(len(store.messages('personal_gmail')),10)
    def test_db_write_failure_does_not_advance_past_unsaved_message(self):
        session=Session(3);store.queue_sync('personal_gmail');actual=state.checkpoint;failed=[False]
        def checkpoint(*args,**kwargs):
            if kwargs.get('message') is not None and not failed[0]:failed[0]=True;raise RuntimeError('DB write failed')
            return actual(*args,**kwargs)
        with patch.object(state,'checkpoint',side_effect=checkpoint):self.run_pass(session)
        self.assertEqual(store.messages('personal_gmail'),[])
        with p.connect() as db:c=json.loads(db.execute('SELECT cursor FROM mail_scans').fetchone()[0])
        self.assertEqual(c['pending'][0],'0');self.complete(session);self.assertEqual(len(store.messages('personal_gmail')),3)
    def test_restart_keeps_deduplication_and_saved_messages(self):
        session=Session(40);store.queue_sync('personal_gmail');self.run_pass(session);self.assertEqual(len(session.fetched),25)
        state.restart('personal_gmail');self.complete(session)
        self.assertEqual(len(session.fetched),40);self.assertEqual(state.summary('personal_gmail')['saved'],40)
    def test_restart_refuses_while_read_running(self):
        store.queue_sync('personal_gmail');store.claim()
        with self.assertRaisesRegex(ValueError,'active read'):state.restart('personal_gmail')
    def test_connection_generation_invalidates_old_checkpoints(self):
        a=store.account('personal_gmail');scan=state.scan(a);store.disconnect('personal_gmail')
        with self.assertRaises(ValueError):state.checkpoint(scan,state.cursor(),message=providers.parse_message(b'\r\nPrivate','1'))
        self.assertEqual(store.messages('personal_gmail'),[])
    def test_same_remote_id_is_separate_per_account(self):
        self.complete(Session(2));store.connect('edsync_gmail','business@example.com',dialogue.scopes()[0],{'refresh_token':'synthetic'})
        store.queue_sync('edsync_gmail')
        with patch.object(engine,'session_factory',return_value=Session(2)):engine.run_sync()
        self.assertEqual(len(store.messages('edsync_gmail')),2);self.assertEqual(len(store.messages('personal_gmail')),2)
    def test_titan_validity_change_resets_pending_namespace(self):
        a=store.account('personal_gmail');scan=state.scan(a);c=state.cursor();c.update(validity='old',pending=['old:1'],listed=True)
        state.checkpoint(scan,c)
        class Changed(Session):
            validity='new'
        self.complete(Changed(2))
        self.assertEqual(len(store.messages('personal_gmail')),2)
    def test_no_paid_model_calls_in_read_batches(self):
        with patch('superhuman.dialogue.engine.run_turn',side_effect=AssertionError('No models')):
            self.assertEqual(self.complete(Session(40))['model_calls'],0)
    def test_capacity_blocks_instead_of_deleting_unreported_previews(self):
        with patch.object(state,'CAPACITY',5):result=self.complete(Session(8))
        self.assertEqual(result['status'],'capacity_blocked');self.assertEqual(state.summary('personal_gmail')['saved'],5)
    def test_completed_report_previews_can_make_space_but_sources_remain(self):
        with patch.object(state,'CAPACITY',5):self.complete(Session(8))
        thread=self.report();self.mark(thread,'done')
        with p.connect() as db:snapshot=db.execute('SELECT snapshot FROM mail_reports WHERE thread_id=?',(thread,)).fetchone()[0]
        with patch.object(state,'CAPACITY',5):result=self.complete(Session(8))
        self.assertEqual(result['status'],'complete');self.assertEqual(len(json.loads(snapshot)['messages']),5)
        self.assertEqual(state.summary('personal_gmail')['waiting'],3)
    def test_reports_select_next_unreserved_messages(self):
        self.complete(Session(30));first=self.report();second=self.report()
        self.assertNotEqual(first,second)
        self.assertEqual(state.summary('personal_gmail')['pending'],24);self.assertEqual(state.summary('personal_gmail')['waiting'],6)
        self.mark(first,'done');self.assertEqual(state.summary('personal_gmail')['included'],12)
    def test_failed_and_cancelled_reports_release_reservations(self):
        self.complete(Session(3));thread=self.report();self.assertEqual(state.summary('personal_gmail')['pending'],3)
        for status in ('failed','cancelled','interrupted','budget_blocked'):
            self.mark(thread,status);self.assertEqual(state.summary('personal_gmail')['waiting'],3)
        self.assertNotEqual(self.report(),thread)
    def test_finished_reports_are_not_automatically_repeated(self):
        self.complete(Session(3));thread=self.report();self.mark(thread,'done')
        with self.assertRaisesRegex(ValueError,'No saved email'):self.report()
        self.assertEqual(state.summary('personal_gmail')['waiting'],0)
    def test_duplicate_form_returns_same_report_even_when_nothing_waits(self):
        self.complete(Session(3));key=uuid4().hex;thread=store.make_report('personal_gmail',key)
        self.assertEqual(store.make_report('personal_gmail',key),thread)
    def test_concurrent_distinct_forms_reserve_different_messages(self):
        self.complete(Session(24))
        with ThreadPoolExecutor(max_workers=2) as pool:threads=list(pool.map(lambda _:self.report(),[1,2]))
        self.assertNotEqual(*threads)
        with p.connect() as db:ids=[r[0] for r in db.execute('SELECT source_id FROM mail_report_members')]
        self.assertEqual(len(set(ids)),24)
    def test_historical_report_membership_backfilled_without_call(self):
        self.complete(Session(2));thread=self.report()
        with p.connect() as db:
            db.execute('DELETE FROM mail_report_members');db.execute('DELETE FROM mail_indexed_reports');db.execute("UPDATE dialogue_turns SET status='done' WHERE thread_id=?",(thread,))
        store.initialize();self.assertEqual(state.summary('personal_gmail')['included'],2)
    def test_unavailable_message_advances_scan_but_is_not_reported(self):
        class Missing(Session):
            def fetch(self,remote_id,scan):return None if remote_id=='1' else super().fetch(remote_id,scan)
        self.complete(Missing(3));summary=state.summary('personal_gmail')
        self.assertEqual(summary['saved'],2);self.assertEqual(summary['scan']['unavailable'],1)
    def test_progress_does_not_claim_all_provider_messages(self):
        session=Session(65);store.queue_sync('personal_gmail');self.run_pass(session)
        value=state.summary('personal_gmail');self.assertEqual(value['scan']['status'],'active')
        self.assertEqual(value['scan']['found'],30);self.assertEqual(value['scan']['processed'],25)


class AdapterTests(unittest.TestCase):
    def test_titan_adapter_uses_readonly_uid_and_peek_with_internal_date(self):
        import imaplib
        now=time.time();stamp=imaplib.Time2Internaldate(now);commands=[]
        class IMAP:
            def __init__(self,*args,**kwargs):pass
            def login(self,*args):return 'OK',[]
            def select(self,folder,readonly):
                if not readonly:raise AssertionError('Must use EXAMINE')
                return 'OK',[]
            def response(self,name):return name,[b'42']
            def uid(self,*args):
                commands.append(args)
                if args[0]=='SEARCH':return 'OK',[b'1 2']
                if 'INTERNALDATE' in args[2]:return 'OK',[(f'1 (RFC822.SIZE 120 INTERNALDATE {stamp})').encode()]
                return 'OK',[(b'1 (BODY[] {25}',b'Subject: Meeting\r\n\r\nNotes'),b')']
            def logout(self):pass
        with patch.object(engine.imaplib,'IMAP4_SSL',IMAP):
            session=engine.Titan({'host':store.HOSTS['godaddy'],'email':'a@example.com'},{'password':'fake'})
            scan={'start':now-86400,'end':now+10};ids,_,done,_=session.discover(scan,state.cursor());message=session.fetch(ids[0],scan)
        self.assertEqual(ids,['42:2','42:1']);self.assertTrue(done);self.assertEqual(message['body'],'Notes')
        self.assertTrue(all(c[0] in ('SEARCH','FETCH') for c in commands));self.assertIn('BODY.PEEK',commands[-1][2])
    def test_gmail_page_token_and_frozen_query(self):
        account={'email':'owner@example.com'}
        with patch.object(providers,'verify_gmail',return_value='token'):
            session=engine.Gmail(account,{})
        c=state.cursor();c['token']='NEXT'
        with patch.object(providers,'request_json',return_value={'messages':[{'id':'abc'}],'nextPageToken':'AFTER'}) as api:
            ids,token,done,_=session.discover({'start':1000000,'end':2000000},c)
        url=api.call_args.args[0];self.assertIn('pageToken=NEXT',url);self.assertIn('after%3A999999',url)
        self.assertEqual(ids,['abc']);self.assertEqual(token,'AFTER');self.assertFalse(done)
    def test_repeated_gmail_page_token_is_rejected(self):
        with patch.object(providers,'verify_gmail',return_value='token'):session=engine.Gmail({'email':'a@example.com'},{})
        c=state.cursor();c['token']='SAME'
        with patch.object(providers,'request_json',return_value={'messages':[],'nextPageToken':'SAME'}),self.assertRaises(ValueError):session.discover({'start':1,'end':2},c)
    def test_gmail_404_is_explicitly_unavailable(self):
        from urllib.error import HTTPError
        with patch.object(providers,'verify_gmail',return_value='token'):session=engine.Gmail({'email':'a@example.com'},{})
        with patch.object(providers,'request_json',side_effect=HTTPError('url',404,'gone',{},None)):
            self.assertIsNone(session.fetch('abc',{}))


if __name__=='__main__':unittest.main()
