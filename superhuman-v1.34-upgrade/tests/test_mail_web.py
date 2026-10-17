import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
from fastapi.testclient import TestClient
from superhuman.hosted import auth,config,web
from superhuman.mail import store,providers


def token(response):return re.search(r'name="csrf" value="([^"]+)"',response.text).group(1)


class MailWebTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=Path.cwd();os.chdir(self.temp.name)
        self.env=patch.dict(os.environ,{'SUPERHUMAN_MAIL_KEY_FILE':str(Path('private/key').resolve())});self.env.start()
        self.settings=config.Settings('https://superhuman.example',state_dir=Path('state'))
        self.auth=auth.Store(self.settings.auth_db);self.auth.setup('owner','test-private-passphrase')
        self.client=TestClient(web.create_app(self.settings),base_url=self.settings.public_origin)
    def tearDown(self):self.client.close();self.env.stop();os.chdir(self.old);self.temp.cleanup()
    def login(self):
        self.client.post('/login',data={'username':'owner','password':'test-private-passphrase','csrf':token(self.client.get('/login'))})
    def seed(self):
        store.connect('personal_gmail','owner@example.com',store.dialogue.scopes()[0],{'password':'NEVER-SHOW-SECRET'})
        store.queue_sync('personal_gmail');job=store.claim()
        store.finish_sync(job,[providers.parse_message(b'From: <script>alert(1)</script>\r\nSubject: <script>evil()</script>\r\n\r\n<img src="https://tracker.invalid/">','one')])
        return store.messages('personal_gmail')[0]
    def test_all_mail_pages_require_login(self):
        for path in ('/inboxes','/inboxes/setup','/inboxes/personal_gmail','/inboxes/personal_gmail/message/nope'):
            self.assertEqual(self.client.get(path,follow_redirects=False).status_code,303)
    def test_four_labels_and_phone_layout(self):
        self.login();response=self.client.get('/inboxes')
        self.assertEqual(response.status_code,200)
        for label,_ in store.SLOTS.values():self.assertIn(label,response.text)
        self.assertIn('width=device-width',response.text);self.assertEqual(response.headers['cache-control'],'no-store')
    def test_csrf_on_all_new_forms(self):
        self.login();self.seed();response=self.client.get('/inboxes/personal_gmail')
        forms=re.findall(r'<form\b[^>]*method="post"[^>]*>(.*?)</form>',response.text,re.S)
        self.assertGreater(len(forms),3);self.assertTrue(all('name="csrf"' in form for form in forms))
        for action,data in (('sync',{}),('auto',{'enabled':1}),('report',{'submission_key':uuid4().hex}),('disconnect',{})):
            self.assertEqual(self.client.post('/inboxes/personal_gmail/'+action,data=data).status_code,403)
    def test_escaped_preview_no_tracking_image_or_secret(self):
        self.login();m=self.seed();response=self.client.get('/inboxes/personal_gmail/message/'+m['id'])
        self.assertEqual(response.status_code,200);self.assertNotIn('<script>',response.text);self.assertNotRegex(response.text,r'''<img[^>]+src=["'](?:https?:|//)''');self.assertIn('src="/assets/agents/twin.png"',response.text)
        self.assertNotIn('NEVER-SHOW-SECRET',response.text);self.assertIn('&lt;script&gt;',response.text)
    def test_message_id_cannot_cross_account_route(self):
        self.login();m=self.seed();self.assertEqual(self.client.get('/inboxes/edsync_gmail/message/'+m['id']).status_code,404)
    def test_report_post_queues_one_attempt_and_redirects_to_review_flow(self):
        self.login();self.seed();key=uuid4().hex;csrf=token(self.client.get('/inboxes/personal_gmail'))
        first=self.client.post('/inboxes/personal_gmail/report',data={'submission_key':key,'csrf':csrf},follow_redirects=False)
        second=self.client.post('/inboxes/personal_gmail/report',data={'submission_key':key,'csrf':csrf},follow_redirects=False)
        self.assertEqual(first.status_code,303);self.assertEqual(first.headers['location'],second.headers['location'])
        page=self.client.get(first.headers['location']);self.assertIn('1 reply requests',page.text);self.assertIn('queued',page.text)
    def test_sync_does_not_call_provider_in_web_request(self):
        self.login();self.seed();csrf=token(self.client.get('/inboxes/personal_gmail'))
        with patch.object(providers,'gmail',side_effect=AssertionError('Only worker may contact provider')):
            response=self.client.post('/inboxes/personal_gmail/sync',data={'csrf':csrf},follow_redirects=False)
        self.assertEqual(response.status_code,303)
    def test_unexpected_auto_value_refused(self):
        self.login();self.seed();csrf=token(self.client.get('/inboxes/personal_gmail'))
        self.assertEqual(self.client.post('/inboxes/personal_gmail/auto',data={'csrf':csrf,'enabled':2}).status_code,400)
    def test_disconnect_retains_preview(self):
        self.login();m=self.seed();csrf=token(self.client.get('/inboxes/personal_gmail'))
        response=self.client.post('/inboxes/personal_gmail/disconnect',data={'csrf':csrf},follow_redirects=False)
        self.assertEqual(response.status_code,303);self.assertFalse(store.account('personal_gmail')['connected']);self.assertEqual(store.message('personal_gmail',m['id'])['id'],m['id'])
    def test_restart_scan_is_authenticated_csrf_protected_and_only_queued(self):
        self.login();self.seed();page=self.client.get('/inboxes/personal_gmail');csrf=token(page)
        self.assertIn('waiting for a report',page.text)
        self.assertEqual(self.client.post('/mailflow/personal_gmail/restart').status_code,403)
        with patch('superhuman.mailflow.engine.session_factory',side_effect=AssertionError('Do not read in web request')):
            r=self.client.post('/mailflow/personal_gmail/restart',data={'csrf':csrf},follow_redirects=False)
        self.assertEqual(r.status_code,303)


if __name__=='__main__':unittest.main()
