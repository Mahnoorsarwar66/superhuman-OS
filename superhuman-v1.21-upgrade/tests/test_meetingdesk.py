"""Versioned meeting records and reviewed local drafts; synthetic dependencies only."""
from concurrent.futures import ThreadPoolExecutor
import re
import unittest
from unittest.mock import patch
from uuid import uuid4
from test_dialogue import DialogueTests,DialogueWebTests
from superhuman.meetingdesk import store as m
from superhuman.calendar import store as c
from superhuman.projects import engine as p
from superhuman.runtime import engine as r
from superhuman.knowledge.store import Store as Memory

START='2026-11-01T10:00:00Z'


def meeting():return c.create('University discovery',START,'','Review workflows and ask about constraints.',uuid4().hex)


def save(event_id,version=0,**values):
    fields=m.empty();fields.update(values);return m.save_notes(event_id,version,fields)


def approve(event_id,kind='preparation',key=None,**changes):
    task=m.draft(event_id,kind)
    task.update(changes)
    return m.queue(event_id,kind,task.get('scope','marketing'),task['title'],task['details'],task['event_version'],task['notes_version'],key or uuid4().hex)


class MeetingStoreTests(unittest.TestCase):
    setUp=DialogueTests.setUp
    tearDown=DialogueTests.tearDown
    def test_viewing_and_preview_do_not_queue_jobs(self):
        eid=meeting();self.assertEqual(m.notes(eid)['version'],0);m.draft(eid,'preparation')
        self.assertEqual(r.status()['projects'],[]);self.assertEqual(m.history(eid),[])
    def test_notes_versions_preserve_source_categories(self):
        eid=meeting();save(eid,statements='University uses spreadsheets.',interpretation='Possible duplication.',decisions='Nothing agreed.')
        save(eid,1,statements='University uses spreadsheets.',interpretation='Needs confirmation.',decisions='Nothing agreed.')
        self.assertEqual(m.notes(eid)['version'],2);history=m.history(eid)
        self.assertEqual(history[1]['fields']['interpretation'],'Possible duplication.');self.assertEqual(history[0]['fields']['interpretation'],'Needs confirmation.')
    def test_stale_notes_refused(self):
        eid=meeting();save(eid,statements='First version')
        with self.assertRaises(ValueError):save(eid,statements='Overwritten')
        self.assertEqual(m.notes(eid)['fields']['statements'],'First version')
    def test_identical_saved_values_do_not_add_history(self):
        eid=meeting();save(eid,statements='Agreed statement');self.assertEqual(save(eid,1,statements='Agreed statement'),1)
        self.assertEqual(len(m.history(eid)),1)
    def test_concurrent_note_edit_has_one_winner(self):
        eid=meeting();m.initialize()
        def edit(i):
            try:return save(eid,statements=str(i))
            except ValueError:return 'stale'
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(edit,range(2)))
        self.assertCountEqual(results,[1,'stale']);self.assertEqual(len(m.history(eid)),1)
    def test_note_limits_and_keys(self):
        eid=meeting()
        with self.assertRaises(ValueError):save(eid,attendees='x'*801)
        with self.assertRaises(ValueError):save(eid,statements='x'*2200,decisions='x'*1600,actions='x'*1600,questions='x'*1000)
        with self.assertRaises(ValueError):m.save_notes(eid,0,{'statements':'incomplete'})
    def test_minutes_need_actual_record_not_only_interpretation(self):
        eid=meeting();save(eid,interpretation='I think it went well.',attendees='Mahnoor')
        with self.assertRaisesRegex(ValueError,'Save participant'):m.draft(eid,'minutes')
        save(eid,1,statements='Partner asked for more information.')
        self.assertIn('Partner asked for more information.',m.draft(eid,'minutes')['details'])
    def test_queue_edit_scope_budget_and_provenance(self):
        eid=meeting();save(eid,statements='Working notes')
        scope=next(k for k in m.dialogue.scopes() if k!='marketing')
        pid=approve(eid,scope=scope,title='Reviewed preparation',details='Prepare a local blank meeting checklist.')
        project=p.get(pid);self.assertEqual(project['workstream'],scope);self.assertEqual(project['objective'],'Reviewed preparation');self.assertEqual(project['max_calls'],3)
        row=m.jobs(eid)[0];self.assertEqual(row['notes_version'],1);self.assertIn('Working notes',row['context_json'])
    def test_same_approval_is_idempotent(self):
        eid=meeting();key=uuid4().hex;pid=approve(eid,key=key)
        self.assertEqual(pid,approve(eid,key=key));self.assertEqual(len(r.status()['projects']),1)
    def test_same_key_different_instructions_refused(self):
        eid=meeting();key=uuid4().hex;approve(eid,key=key)
        with self.assertRaises(ValueError):approve(eid,key=key,details='Prepare another local checklist.')
    def test_concurrent_approval_creates_one_job(self):
        eid=meeting();key=uuid4().hex
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:approve(eid,key=key),range(2)))
        self.assertEqual(results[0],results[1]);self.assertEqual(len(m.jobs(eid)),1)
    def test_atomic_failure_leaves_no_project_or_job(self):
        eid=meeting();original=r._insert_job
        def fail(*a,**kw):original(*a,**kw);raise RuntimeError('Simulated interruption')
        with patch.object(r,'_insert_job',side_effect=fail),self.assertRaises(RuntimeError):approve(eid)
        self.assertEqual(m.jobs(eid),[]);self.assertEqual(r.status()['projects'],[])
    def test_changed_notes_invalidate_open_task_form(self):
        eid=meeting();task=m.draft(eid,'preparation');save(eid,statements='New facts')
        with self.assertRaisesRegex(ValueError,'changed'):m.queue(eid,'preparation','marketing',task['title'],task['details'],task['event_version'],task['notes_version'],uuid4().hex)
        self.assertEqual(m.jobs(eid),[])
    def test_changed_event_invalidates_open_form(self):
        eid=meeting();task=m.draft(eid,'preparation');c.update(eid,1,'Changed meeting',START,'','','confirmed')
        with self.assertRaises(ValueError):m.queue(eid,'preparation','marketing',task['title'],task['details'],1,0,uuid4().hex)
    def test_cancelled_meeting_cannot_queue_preparation(self):
        eid=meeting();c.update(eid,1,'University discovery',START,'','','cancelled')
        with self.assertRaises(ValueError):approve(eid)
    def test_project_keeps_old_snapshot_after_notes_change(self):
        eid=meeting();save(eid,statements='Original');pid=approve(eid,'minutes');old=p.get(pid)['details']
        save(eid,1,statements='Changed');self.assertEqual(p.get(pid)['details'],old);self.assertIn('Original',m.jobs(eid)[0]['context_json'])
    def test_notes_do_not_become_general_memory(self):
        eid=meeting();save(eid,statements='Private working record');self.assertEqual(Memory().list(),[])
    def test_invalid_scope_kind_or_key_refused(self):
        eid=meeting()
        with self.assertRaises(ValueError):approve(eid,scope='unknown')
        with self.assertRaises(ValueError):m.draft(eid,'send')
        with self.assertRaises(ValueError):approve(eid,key='bad')


class MeetingWebTests(unittest.TestCase):
    setUp=DialogueWebTests.setUp
    tearDown=DialogueWebTests.tearDown
    token=DialogueWebTests.token
    login=DialogueWebTests.login
    def test_routes_protected(self):
        for url in ('/meetings','/meetings/unknown','/meetings/unknown/history','/meetings/unknown/draft/preparation'):
            self.assertEqual(self.client.get(url,follow_redirects=False).status_code,303)
    def test_notes_and_queue_require_csrf(self):
        self.login();eid=meeting()
        for url in ('/meetings/'+eid+'/notes','/meetings/'+eid+'/queue'):
            self.assertEqual(self.client.post(url,data={}).status_code,403)
    def test_calendar_links_to_workbench(self):
        self.login();eid=meeting();self.assertIn('/meetings/'+eid,self.client.get('/calendar/event/'+eid).text)
    def test_save_notes_then_review_minutes(self):
        csrf=self.login();eid=meeting()
        result=self.client.post('/meetings/'+eid+'/notes',data=dict(csrf=csrf,version=0,statements='Partner asked about data handling.',interpretation='Needs technical review.'),follow_redirects=False)
        self.assertEqual(result.status_code,303);page=self.client.get('/meetings/'+eid+'/draft/minutes')
        self.assertEqual(page.status_code,200);self.assertIn('Partner asked about data handling.',page.text);self.assertIn('Choose a workstream',page.text)
        self.assertEqual(r.status()['projects'],[])
    def test_review_queue_open_existing_work(self):
        csrf=self.login();eid=meeting();page=self.client.get('/meetings/'+eid+'/draft/preparation');key=re.search('name="submission_key" value="([^"]+)"',page.text).group(1)
        data=dict(csrf=csrf,kind='preparation',scope='marketing',title='Local preparation',details='Prepare a concise local agenda.',event_version=1,notes_version=0,submission_key=key)
        result=self.client.post('/meetings/'+eid+'/queue',data=data,follow_redirects=False)
        self.assertEqual(result.status_code,303);self.assertTrue(result.headers['location'].startswith('/work/'))
        self.assertEqual(self.client.post('/meetings/'+eid+'/queue',data=data,follow_redirects=False).headers['location'],result.headers['location'])
        self.assertIn('Local preparation',self.client.get('/meetings/'+eid).text)
    def test_minutes_require_notes_and_html_is_escaped(self):
        self.login();eid=meeting();self.assertEqual(self.client.get('/meetings/'+eid+'/draft/minutes').status_code,400)
        save(eid,statements='<script>private()</script>');page=self.client.get('/meetings/'+eid)
        self.assertNotIn('<script>private()',page.text);self.assertIn('&lt;script&gt;',page.text)
        self.assertIn('&lt;script&gt;',self.client.get('/meetings/'+eid+'/history').text)
    def test_changed_notes_mark_existing_task(self):
        self.login();eid=meeting();approve(eid);save(eid,statements='New notes')
        self.assertIn('changed since this task was approved',self.client.get('/meetings/'+eid).text)
    def test_missing_meeting_and_invalid_list(self):
        self.login();self.assertEqual(self.client.get('/meetings/unknown').status_code,404)
        self.assertEqual(self.client.get('/meetings?view=bad').status_code,400)


del DialogueTests,DialogueWebTests
