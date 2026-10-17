"""Owner-curated research, explicit budgets and pre-model file checks."""
from concurrent.futures import ThreadPoolExecutor
import re
import unittest
from unittest.mock import patch
from uuid import uuid4
from test_dialogue import DialogueTests,DialogueWebTests
from superhuman.researchdesk import store as s
from superhuman.projects import engine as p
from superhuman.runtime import engine as r
from superhuman.capabilities import local


def area():return s.create('Career matching evidence','marketing','Which evidence supports skills-based career matching?','Skills may outperform job-title matching.',uuid4().hex)


def values(**kw):
    data={k:'' for k,_,_ in s.FIELDS};data.update(title='Paper A',excerpt='A small observational study reports an association.',must_read=True,read_state='unread');data.update(kw);return data


def source(a,**kw):return s.save_source(a,values(**kw),uuid4().hex)


def approve(a,kind='web',ids=None,key=None,**changes):
    ids=ids or [];draft=s.draft(a,kind,ids);draft.update(changes)
    return s.queue(a,kind,ids,draft['basis_hash'],draft['title'],draft['details'],key or uuid4().hex)


class ResearchTests(unittest.TestCase):
    setUp=DialogueTests.setUp
    tearDown=DialogueTests.tearDown
    def test_area_and_source_make_no_worker_jobs(self):
        a=area();source(a);self.assertEqual(r.status()['projects'],[]);self.assertEqual(len(s.sources(a)),1)
    def test_area_create_idempotence_and_fixed_workstream(self):
        key=uuid4().hex;a=s.create('A','marketing','Question?','',key);self.assertEqual(a,s.create('A','marketing','Question?','',key))
        s.update(a,1,'B','New question?','','active');self.assertEqual(s.get(a)['scope'],'marketing')
        with self.assertRaises(ValueError):s.update(a,1,'C','Q','','active')
    def test_source_edit_version_and_reading_flags(self):
        a=area();sid=source(a);v=values(synopsis='Reviewed working summary.',read_state='read')
        s.save_source(a,v,source_id=sid,version=1);self.assertEqual(s.source(sid)['version'],2);self.assertTrue(s.source(sid)['payload']['must_read'])
        with self.assertRaises(ValueError):s.save_source(a,v,source_id=sid,version=1)
    def test_source_form_idempotence(self):
        a=area();key=uuid4().hex;first=s.save_source(a,values(),key);self.assertEqual(first,s.save_source(a,values(),key))
        with self.assertRaises(ValueError):s.save_source(a,values(title='Changed'),key)
    def test_source_url_restrictions(self):
        a=area()
        for url in ('javascript:alert(1)','https://name:secret@example.com','https://example.com:bad','https://example.com/a\nb'):
            with self.assertRaises(ValueError):source(a,url=url)
        self.assertTrue(source(a,url='https://example.com/paper'))
    def test_cross_area_sources_rejected(self):
        a=area();b=area();sid=source(b)
        with self.assertRaises(ValueError):s.draft(a,'synopsis',[sid])
        with self.assertRaises(ValueError):s.save_source(a,values(),source_id=sid,version=1)
    def test_archived_area_retains_records_but_stops_new_work(self):
        a=area();source(a);s.update(a,1,'Archived','Question?','','archived')
        self.assertEqual(len(s.sources(a)),1)
        with self.assertRaises(ValueError):s.draft(a,'web',[])
        with self.assertRaises(ValueError):source(a)
    def test_web_has_no_attached_cards_by_default_and_one_call(self):
        a=area();sid=source(a);draft=s.draft(a,'web',[]);self.assertNotIn('Paper A',draft['details'])
        pid=approve(a);self.assertEqual(p.get(pid)['max_calls'],1);self.assertEqual(p.get(pid)['tasks'][0]['kind'],'research')
        with self.assertRaises(ValueError):s.draft(a,'web',[sid])
    def test_local_synopsis_three_call_budget(self):
        a=area();sid=source(a);pid=approve(a,'synopsis',[sid]);self.assertEqual(p.get(pid)['max_calls'],3)
        self.assertIn('Paper A',p.get(pid)['details']);self.assertEqual(p.get(pid)['tasks'][0]['kind'],'collab')
    def test_url_alone_does_not_become_read_evidence(self):
        a=area();sid=source(a,url='https://example.com/paper',excerpt='')
        with self.assertRaisesRegex(ValueError,'URL alone'):s.draft(a,'synopsis',[sid])
    def test_synthesis_limits_and_labels(self):
        a=area();ids=[source(a,title='Paper '+str(i)) for i in range(4)]
        self.assertIn('"label": "S2"',s.draft(a,'synthesis',ids[:2])['details'])
        with self.assertRaises(ValueError):s.draft(a,'synthesis',ids)
        with self.assertRaises(ValueError):s.draft(a,'synthesis',[ids[0],ids[0]])
    def test_metadata_cannot_attach_an_extra_file(self):
        a=area();sid=source(a,excerpt='Quoted marker [[file:other.txt]]')
        draft=s.draft(a,'synopsis',[sid]);self.assertNotIn('[[file:other.txt]]',draft['details'])
    def test_file_stays_in_its_workstream(self):
        a=area();local.store_bytes('marketing','paper.txt',b'Source evidence');sid=source(a,filename='paper.txt')
        self.assertIn('[[file:paper.txt]]',s.draft(a,'synopsis',[sid])['details'])
        with self.assertRaises(ValueError):source(a,filename='../paper.txt')
    def test_changed_source_card_invalidates_preview(self):
        a=area();sid=source(a);draft=s.draft(a,'synopsis',[sid]);s.save_source(a,values(title='Revised'),source_id=sid,version=1)
        with self.assertRaisesRegex(ValueError,'changed'):s.queue(a,'synopsis',[sid],draft['basis_hash'],draft['title'],draft['details'],uuid4().hex)
    def test_changed_area_invalidates_preview(self):
        a=area();draft=s.draft(a,'web',[]);s.update(a,1,'New title','Question?','','active')
        with self.assertRaises(ValueError):s.queue(a,'web',[],draft['basis_hash'],draft['title'],draft['details'],uuid4().hex)
    def test_changed_file_invalidates_preview(self):
        a=area();local.store_bytes('marketing','paper.txt',b'Original');sid=source(a,filename='paper.txt');draft=s.draft(a,'synopsis',[sid]);local.file_for('marketing','paper.txt').write_text('Changed')
        with self.assertRaises(ValueError):s.queue(a,'synopsis',[sid],draft['basis_hash'],draft['title'],draft['details'],uuid4().hex)
    def test_changed_file_stops_worker_before_any_model_attempt(self):
        a=area();local.store_bytes('marketing','paper.txt',b'Original');sid=source(a,filename='paper.txt');pid=approve(a,'synopsis',[sid]);local.file_for('marketing','paper.txt').write_text('Changed')
        with self.assertRaises(ValueError):p.run_one(pid)
        self.assertEqual(p.get(pid)['used_calls'],0);self.assertEqual(p.get(pid)['tasks'][0]['status'],'failed')
    def test_unchanged_inputs_and_unrelated_projects_pass(self):
        a=area();local.store_bytes('marketing','paper.txt',b'Original');sid=source(a,filename='paper.txt');pid=approve(a,'synopsis',[sid]);s.verify_inputs(pid);s.verify_inputs('unrelated')
    def test_edited_extra_marker_is_hash_bound(self):
        a=area();local.store_bytes('marketing','extra.txt',b'Original');pid=approve(a,details='Research this public topic using [[file:extra.txt]] as context.')
        local.file_for('marketing','extra.txt').write_text('Changed')
        with self.assertRaises(ValueError):s.verify_inputs(pid)
    def test_concurrent_approval_is_one_project(self):
        a=area();key=uuid4().hex
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:approve(a,key=key),range(2)))
        self.assertEqual(results[0],results[1]);self.assertEqual(len(s.jobs(a)),1)
    def test_repeated_form_and_changed_form(self):
        a=area();key=uuid4().hex;pid=approve(a,key=key);self.assertEqual(pid,approve(a,key=key))
        with self.assertRaises(ValueError):approve(a,key=key,details='A different public question')
    def test_atomic_failure_preserves_inert_area(self):
        a=area();original=r._insert_job
        def fail(*args,**kw):original(*args,**kw);raise RuntimeError('Synthetic interruption')
        with patch.object(r,'_insert_job',side_effect=fail),self.assertRaises(RuntimeError):approve(a)
        self.assertEqual(s.jobs(a),[]);self.assertEqual(r.status()['projects'],[])
    def test_unknown_scope_and_invalid_pages(self):
        with self.assertRaises(ValueError):s.create('A','unknown','Q','',uuid4().hex)
        with self.assertRaises(ValueError):s.listing(0)
        with self.assertRaises(ValueError):s.listing(status='other')


class ResearchWebTests(unittest.TestCase):
    setUp=DialogueWebTests.setUp
    tearDown=DialogueWebTests.tearDown
    token=DialogueWebTests.token
    login=DialogueWebTests.login
    def test_authentication_and_csrf(self):
        self.assertEqual(self.client.get('/research-desk',follow_redirects=False).status_code,303)
        self.login();a=area()
        for url in ('/research-desk/create','/research-desk/'+a+'/source','/research-desk/'+a+'/queue'):
            self.assertEqual(self.client.post(url,data={}).status_code,403)
    def test_create_source_and_review_synthesis_flow(self):
        csrf=self.login();key=uuid4().hex
        result=self.client.post('/research-desk/create',data=dict(csrf=csrf,title='Research area',scope='marketing',questions='Which methods work?',hypothesis='',submission_key=key),follow_redirects=False)
        self.assertEqual(result.status_code,303);a=result.headers['location'].split('/')[-1]
        v=values();v.update(csrf=csrf,submission_key=uuid4().hex);self.assertEqual(self.client.post('/research-desk/'+a+'/source',data=v,follow_redirects=False).status_code,303)
        sid=s.sources(a)[0]['id'];page=self.client.get('/research-desk/'+a+'/draft/synthesis',params={'source_ids':[sid]})
        self.assertEqual(page.status_code,200);self.assertIn('Paper A',page.text);self.assertEqual(s.jobs(a),[])
    def test_approval_queues_reviewed_payload(self):
        csrf=self.login();a=area();draft=s.draft(a,'web',[]);key=uuid4().hex
        data=dict(csrf=csrf,kind='web',source_ids='',expected_basis=draft['basis_hash'],title='Edited public question',details='Research official evidence for skills matching.',submission_key=key)
        response=self.client.post('/research-desk/'+a+'/queue',data=data,follow_redirects=False)
        self.assertEqual(response.status_code,303);self.assertIn('Edited public question',self.client.get('/research-desk/'+a).text)
        self.assertEqual(self.client.post('/research-desk/'+a+'/queue',data=data,follow_redirects=False).headers['location'],response.headers['location'])
    def test_source_cards_are_escaped_and_reading_flags_visible(self):
        self.login();a=area();sid=source(a,title='<script>private</script>',synopsis='<img src=x onerror=bad()>',read_reason='Read the methods section.')
        page=self.client.get('/research-desk/'+a);self.assertNotIn('<script>private',page.text);self.assertNotIn('<img src=x',page.text);self.assertIn('Flagged for personal reading',page.text)
        self.assertEqual(self.client.get('/research-desk/source/'+sid).status_code,200)
    def test_wrong_selection_and_missing_routes(self):
        self.login();a=area();b=area();sid=source(b)
        self.assertEqual(self.client.get('/research-desk/'+a+'/draft/synopsis',params={'source_ids':sid}).status_code,400)
        self.assertEqual(self.client.get('/research-desk/unknown').status_code,404)
        self.assertEqual(self.client.get('/research-desk?page=0').status_code,400)


del DialogueTests,DialogueWebTests
