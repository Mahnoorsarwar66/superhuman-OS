import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit,parse_qs,urlencode
from urllib.request import urlopen
from urllib.error import HTTPError

spec=importlib.util.spec_from_file_location('gmail_connect',Path(__file__).resolve().parents[1]/'gmail_connect.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)


class GmailSetupTests(unittest.TestCase):
    def flow(self,email='owner@example.com',actual=None,scope=None,deny=False):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        output=Path(self.temp.name)/'private.json';client={'client_id':'client','client_secret':'client-secret'};calls=[]
        def browser(url):
            q=parse_qs(urlsplit(url).query);self.assertEqual(q['scope'],[helper.SCOPE]);self.assertEqual(q['code_challenge_method'],['S256'])
            self.assertEqual(q['access_type'],['offline']);self.assertEqual(q['login_hint'],[email]);self.assertEqual(urlsplit(q['redirect_uri'][0]).hostname,'127.0.0.1')
            import threading
            def callback():
                invalid=q['redirect_uri'][0]+'?'+urlencode(dict(state='forged-state',code='wrong-code'))
                try:
                    urlopen(invalid,timeout=5)
                    self.fail('Forged callback must be rejected')
                except HTTPError as exc:
                    self.assertEqual(exc.code,400)
                target=q['redirect_uri'][0]+'?'+urlencode(dict(state=q['state'][0],**({'error':'access_denied'} if deny else {'code':'authcode'})))
                with urlopen(target,timeout=5) as response:self.assertEqual(response.status,200)
            thread=threading.Thread(target=callback);thread.start();self.addCleanup(thread.join,5)
            return True
        def api(url,form=None,token=None):
            calls.append((url,form,token))
            if url==helper.TOKEN:
                self.assertIn('code_verifier',form)
                return {'scope':scope if scope is not None else helper.SCOPE,'access_token':'access','refresh_token':'PRIVATE-REFRESH'}
            if url==helper.PROFILE:return {'emailAddress':actual or email}
            raise AssertionError('Unexpected endpoint')
        with patch.object(helper,'api',side_effect=api):helper.authorize(client,email,'personal_gmail',output,open_browser=browser)
        return output,calls
    def test_loopback_pkce_identity_and_offline_grant(self):
        output,calls=self.flow();payload=json.loads(output.read_text());self.assertEqual(payload['refresh_token'],'PRIVATE-REFRESH');self.assertNotIn('access_token',payload)
        self.assertEqual(output.stat().st_mode & 0o777,0o600);self.assertEqual(len(calls),2)
    def test_wrong_identity_refuses_file(self):
        with self.assertRaisesRegex(ValueError,'Wrong Google account'):self.flow(actual='other@example.com')
    def test_broad_scopes_refused(self):
        with self.assertRaisesRegex(ValueError,'read-only'):self.flow(scope=helper.SCOPE+' https://mail.google.com/')
    def test_consent_denied_no_file(self):
        with self.assertRaisesRegex(ValueError,'declined'):self.flow(deny=True)
    def test_existing_transfer_file_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'private.json';output.write_text('preserve')
            with self.assertRaisesRegex(ValueError,'Output exists'):helper.authorize({},'a@example.com','personal_gmail',output)
            self.assertEqual(output.read_text(),'preserve')


if __name__=='__main__':unittest.main()
