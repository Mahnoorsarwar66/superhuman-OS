"""Run on YOUR LAPTOP. Standard-library Desktop OAuth, PKCE and loopback callback.

Produces a private one-time transfer file outside the project. No Gmail password.
"""
import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler,HTTPServer
import json
import os
from pathlib import Path
import secrets
import time
from urllib.parse import urlencode,urlsplit,parse_qs
from urllib.request import Request,build_opener,HTTPRedirectHandler
import webbrowser

SCOPE='https://www.googleapis.com/auth/gmail.readonly'
AUTH='https://accounts.google.com/o/oauth2/v2/auth'
TOKEN='https://oauth2.googleapis.com/token'
PROFILE='https://gmail.googleapis.com/gmail/v1/users/me/profile'
SLOTS=('personal_gmail','edsync_gmail','nextstep_gmail')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*a,**kw):raise ValueError('Unexpected Google redirect')


def api(url,form=None,token=None):
    headers={'Accept':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    req=Request(url,data=urlencode(form).encode() if form else None,headers=headers)
    with build_opener(NoRedirect()).open(req,timeout=20) as response:raw=response.read(65537)
    if len(raw)>65536:raise ValueError('Unexpected Google response size')
    return json.loads(raw)


def authorize(client,email,slot,output,open_browser=webbrowser.open):
    output=Path(output).expanduser()
    if output.exists():raise ValueError('Output exists. Import and remove it before reconnecting.')
    state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(64)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    response={}
    class Callback(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            url=urlsplit(self.path);query=parse_qs(url.query)
            if url.path!='/' or len(query.get('state',[]))!=1 or not secrets.compare_digest(query['state'][0],state):
                self.send_error(400,'Invalid authorization response');return
            if response or not (len(query.get('code',[]))==1 or 'error' in query):
                self.send_error(400,'Invalid authorization response');return
            response.update(query)
            self.send_response(200);self.send_header('Content-Type','text/plain; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Security-Policy',"default-src 'none'");self.end_headers()
            self.wfile.write(b'Authorization response received. Return to the Superhuman setup terminal. You can close this tab.')
    with HTTPServer(('127.0.0.1',0),Callback) as server:
        server.timeout=1;redirect='http://127.0.0.1:'+str(server.server_port)+'/'
        url=AUTH+'?'+urlencode(dict(client_id=client['client_id'],redirect_uri=redirect,response_type='code',scope=SCOPE,
            access_type='offline',prompt='consent select_account',state=state,code_challenge=challenge,code_challenge_method='S256',login_hint=email))
        print('Opening Google consent. Choose exactly: '+email,flush=True)
        if not open_browser(url):print('If no browser opened, open this address on THIS laptop:\n'+url,flush=True)
        deadline=time.monotonic()+300
        while not response and time.monotonic()<deadline:server.handle_request()
    if not response:raise ValueError('Google consent timed out. Run the command again.')
    if 'error' in response:raise ValueError('Google consent was declined or blocked; no credential saved.')
    grant=api(TOKEN,form=dict(code=response['code'][0],client_id=client['client_id'],client_secret=client['client_secret'],
                redirect_uri=redirect,grant_type='authorization_code',code_verifier=verifier))
    if set(grant.get('scope','').split())!={SCOPE}:raise ValueError('Only Gmail read-only access may be granted')
    if not grant.get('refresh_token'):raise ValueError('Google did not return offline access. Reconnect with consent.')
    actual=api(PROFILE,token=grant['access_token'])['emailAddress'].casefold()
    if actual!=email.casefold():raise ValueError('Wrong Google account selected; no credential saved.')
    payload=dict(slot=slot,email=actual,scope=SCOPE,client_id=client['client_id'],client_secret=client['client_secret'],refresh_token=grant['refresh_token'])
    output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with os.fdopen(os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w',encoding='utf-8') as stream:json.dump(payload,stream)
    print('Private credential transfer file saved: '+str(output))
    print('Upload it using SCP, import it on the server, then remove this laptop copy. Do not paste or share its contents.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client',type=Path,required=True);parser.add_argument('--email',required=True)
    parser.add_argument('--slot',choices=SLOTS,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.client.stat().st_size>65536:raise ValueError('Invalid Google client file')
        config=json.loads(args.client.read_text(encoding='utf-8-sig'))
        if 'installed' not in config:raise ValueError('Create a Google Desktop app OAuth client, not a Web application client')
        client=config['installed']
        if not all(isinstance(client.get(k),str) and client[k] for k in ('client_id','client_secret')):raise ValueError('Invalid Desktop client')
        authorize(client,args.email.strip(),args.slot,args.output)
    except Exception as exc:
        parser.exit(1,(str(exc) if isinstance(exc,ValueError) else 'Google connection failed ('+type(exc).__name__+'). Check the setup instructions.')+'\n')


if __name__=='__main__':main()
