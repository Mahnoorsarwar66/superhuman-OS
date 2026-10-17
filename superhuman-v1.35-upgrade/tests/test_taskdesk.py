"""Routing, approval compatibility and authenticated task/source views."""
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import unittest
from uuid import uuid4
from test_dialogue import DialogueTests,DialogueWebTests,Client
from superhuman.dialogue import store as d,engine
from superhuman.taskdesk import store as desk
from superhuman.projects import engine as p
from superhuman.runtime import engine as r
from superhuman.mail import store as mail
from superhuman.knowledge.store import Store as Memory

class RoutingTests(unittest.TestCase):
    setUp=DialogueTests.setUp
    tearDown=DialogueTests.tearDown
    send=DialogueTests.send
    answered=DialogueTests.answered
    def approve(self,s,scope=None,**changes):
        return d.approve(self.thread,s['id'],s['proposal_hash'],changes.get('title',s['title']),changes.get('details',s['details']),scope=scope)
    def other(self):return next(s for s in d.scopes() if s!='marketing')
    def test_destination_and_edits_become_canonical_project(self):
        _,s,_=self.answered();pid=self.approve(s,self.other(),title='Edited title',details='Create a blank internal checklist.')
        project=p.get(pid)
        self.assertEqual(project['workstream'],self.other());self.assertEqual(project['objective'],'Edited title')
        self.assertEqual(project['details'],'Create a blank internal checklist.');self.assertEqual(project['max_calls'],3)
        self.assertEqual(d.get(self.thread)['scope'],'marketing');self.assertEqual(desk.chosen_scope(desk.get(s['id'])),self.other())
    def test_concurrent_routes_approve_once(self):
        _,s,_=self.answered()
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:self.approve(s,self.other()),range(2)))
        self.assertEqual(results[0],results[1]);self.assertEqual(len(r.status()['projects']),1)
    def test_repeated_approval_defaults_to_saved_route(self):
        _,s,_=self.answered();pid=self.approve(s,self.other());self.assertEqual(pid,self.approve(s))
    def test_cannot_reroute_already_approved(self):
        _,s,_=self.answered();self.approve(s,self.other())
        with self.assertRaises(ValueError):self.approve(s,'marketing')
    def test_legacy_hash_remains_idempotent(self):
        _,s,_=self.answered();pid=self.approve(s)
        with p.connect() as db:
            db.execute('DELETE FROM dialogue_routes WHERE suggestion_id=?',(s['id'],))
            db.execute('UPDATE dialogue_suggestions SET approved_hash=? WHERE id=?',(d.proposal_hash(s['kind'],s['title'],s['details'],''),s['id']))
        self.assertEqual(pid,self.approve(s));self.assertEqual(len(r.status()['projects']),1)
    def test_invalid_route_leaves_proposal_and_no_project(self):
        _,s,_=self.answered()
        with self.assertRaises(ValueError):self.approve(s,'unconfigured')
        self.assertEqual(desk.get(s['id'])['status'],'proposed');self.assertEqual(r.status()['projects'],[])
    def test_route_failure_rolls_back_project_and_pointer(self):
        _,s,_=self.answered();original=r._insert_job
        def fail(*args,**kw):original(*args,**kw);raise RuntimeError('Interrupted approval')
        with patch.object(r,'_insert_job',side_effect=fail),self.assertRaises(RuntimeError):self.approve(s,self.other())
        self.assertEqual(r.status()['projects'],[]);self.assertEqual(desk.get(s['id'])['status'],'proposed')
        with p.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM dialogue_routes').fetchone()[0],0)
    def test_stale_hash_rejected(self):
        _,s,_=self.answered()
        with self.assertRaises(ValueError):desk.approve(self.thread,s['id'],'old',s['title'],s['details'],scope=self.other())
    def test_filters_and_counts(self):
        _,s,_=self.answered();self.assertEqual(len(desk.listing()),1)
        self.approve(s);self.assertEqual(desk.listing(),[]);self.assertEqual(desk.counts()['approved'],1)
        with self.assertRaises(ValueError):desk.listing('anything')
    def test_dismissed_cannot_be_approved(self):
        _,s,_=self.answered();d.dismiss(self.thread,s['id'],s['proposal_hash'])
        with self.assertRaises(ValueError):self.approve(s)

class TaskWebTests(unittest.TestCase):
    setUp=DialogueWebTests.setUp
    tearDown=DialogueWebTests.tearDown
    token=DialogueWebTests.token
    login=DialogueWebTests.login
    def suggestion(self):
        tid=d.create('marketing','Private task conversation');d.send(tid,'Prepare an internal checklist',uuid4().hex);engine.run_turn(client=Client())
        return tid,d.suggestions(tid)[0]
    def test_task_routes_require_login(self):
        for url in ('/tasks','/tasks/unknown/sources','/tasks/unknown/feedback'):
            self.assertEqual(self.client.get(url,follow_redirects=False).status_code,303)
    def test_forms_and_edit_routing(self):
        csrf=self.login();tid,s=self.suggestion();page=self.client.get('/tasks')
        self.assertEqual(page.status_code,200);self.assertIn('name="scope"',page.text);self.assertIn(s['title'],page.text)
        route=next(v for v in d.scopes() if v!='marketing')
        data=dict(csrf=csrf,expected_hash=s['proposal_hash'],title='Reviewed checklist',details='Prepare a local blank checklist.',scope=route)
        response=self.client.post('/tasks/'+s['id']+'/approve',data=data,follow_redirects=False)
        self.assertEqual(response.status_code,303);pid=response.headers['location'].split('/')[-1]
        self.assertEqual(p.get(pid)['workstream'],route)
        self.assertIn('Reviewed checklist',self.client.get('/tasks?status=approved').text)
    def test_new_approval_csrf_required(self):
        self.login();_,s=self.suggestion()
        self.assertEqual(self.client.post('/tasks/'+s['id']+'/approve',data={}).status_code,403)
        self.assertEqual(desk.get(s['id'])['status'],'proposed')
    def test_talk_route_accepts_destination(self):
        csrf=self.login();tid,s=self.suggestion();route=next(v for v in d.scopes() if v!='marketing')
        result=self.client.post('/talk/'+tid+'/approve',data=dict(csrf=csrf,suggestion_id=s['id'],expected_hash=s['proposal_hash'],title=s['title'],details=s['details'],scope=route),follow_redirects=False)
        self.assertEqual(result.status_code,303);self.assertEqual(p.get(result.headers['location'].split('/')[-1])['workstream'],route)
    def test_feedback_view_only_does_not_save_memory(self):
        self.login();_,s=self.suggestion();result=self.client.get('/tasks/'+s['id']+'/feedback')
        self.assertEqual(result.status_code,200);self.assertIn('value="proposed" selected',result.text);self.assertEqual(Memory().list(),[])
    def test_non_email_source_is_explicit(self):
        self.login();_,s=self.suggestion();self.assertEqual(self.client.get('/tasks/'+s['id']+'/sources').status_code,404)
    def test_saved_email_sources_link_to_immutable_excerpts(self):
        self.login();tid,s=self.suggestion();mail.initialize()
        snapshot=dict(account_id='personal_gmail',label='Personal Gmail',email='owner@example.com',captured_at=p.stamp(),messages=[dict(source_id='saved-source',subject='<script>private</script>',sender='A',sent_at=p.stamp(),body='Saved excerpt')])
        with p.connect() as db:db.execute('INSERT INTO mail_reports VALUES(?,?,?,?,?,?,?)',('report', 'personal_gmail',tid,d.turns(tid)[0]['id'],json.dumps(snapshot),p.stamp(),uuid4().hex))
        result=self.client.get('/tasks/'+s['id']+'/sources')
        self.assertEqual(result.status_code,200);self.assertIn('/briefing/source/report/E1',result.text)
        self.assertNotIn('<script>private</script>',result.text);self.assertIn('&lt;script&gt;',result.text)
    def test_pagination_validation(self):
        self.login();self.assertEqual(self.client.get('/tasks?page=0').status_code,400)
        self.assertEqual(self.client.get('/tasks?status=unknown').status_code,400)

# Setup helpers are borrowed; their original suites run in test_dialogue.py.
del DialogueTests,DialogueWebTests
