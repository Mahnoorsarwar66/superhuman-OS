"""Approved-output intake and source-card adoption with synthetic artifacts."""
import hashlib
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import unittest
from uuid import uuid4
from test_dialogue import DialogueTests,DialogueWebTests
from test_researchdesk import area,source,values,approve
from superhuman.researchreview import store as v
from superhuman.researchdesk import store as r
from superhuman.projects import engine as p
from superhuman.capabilities import local


def complete(a,kind='web',ids=None,refs=None,body='A concise source synopsis. Evidence is limited.',approved=True):
    pid=approve(a,kind,ids or []);job=next(j for j in r.jobs(a) if j['project_id']==pid)
    output=p.OUTPUT_ROOT/pid/'final'/'synthetic'/'draft.md';output.parent.mkdir(parents=True,exist_ok=True);output.write_text(body)
    record=dict(output=str(output),content_sha256=hashlib.sha256(body.encode()).hexdigest(),sources=refs if refs is not None else [dict(url='https://example.com/paper',title='Paper A',origin='api_url_citation')])
    status='approved' if approved else 'needs_review'
    with p.connect() as db:
        db.execute('UPDATE project_tasks SET status=?,output=?,result_json=? WHERE project_id=?',(status,str(output),json.dumps(record),pid))
        db.execute('UPDATE projects SET status=? WHERE id=?',(status,pid))
    return job,output


def candidate(a,**kw):
    job,_=complete(a,**kw);v.collect(job['id']);return v.listing(a)[0]


class ReviewStoreTests(unittest.TestCase):
    setUp=DialogueTests.setUp
    tearDown=DialogueTests.tearDown
    def save(self,row,**kw):return v.save_citation(row['id'],v.proposal_hash(row),kw.get('title',row['title']),kw.get('must_read',False),kw.get('reason',''))
    def test_collect_is_proposed_only_and_repeat_safe(self):
        a=area();job,_=complete(a);self.assertEqual(v.collect(job['id'])['added'],1);self.assertEqual(v.collect(job['id'])['added'],0)
        self.assertEqual(r.sources(a),[])
    def test_only_approved_outputs_are_eligible(self):
        a=area();job,_=complete(a,approved=False)
        with self.assertRaisesRegex(ValueError,'approve'):v.collect(job['id'])
    def test_modified_output_is_refused(self):
        a=area();job,path=complete(a);path.write_text('Changed externally')
        with self.assertRaises(ValueError):v.collect(job['id'])
    def test_only_api_records_and_valid_urls_are_collected(self):
        a=area();job,_=complete(a,refs=[dict(url='https://example.com/a',title='A',origin='api_url_citation'),dict(url='https://example.com/other',title='Other'),dict(url='javascript:bad()',origin='api_url_citation')])
        result=v.collect(job['id']);self.assertEqual(result['added'],1);self.assertEqual(result['skipped'],2)
    def test_url_normalization_preserves_query_and_scheme(self):
        self.assertEqual(v.url_key('HTTPS://Example.COM:443/paper#methods'),'https://example.com/paper')
        self.assertNotEqual(v.url_key('https://example.com/a?q=1'),v.url_key('https://example.com/a?q=2'))
        self.assertNotEqual(v.url_key('http://example.com/a'),v.url_key('https://example.com/a'))
    def test_duplicate_api_urls_collapse(self):
        a=area();job,_=complete(a,refs=[dict(url='https://EXAMPLE.com:443/paper#a',title='A',origin='api_url_citation'),dict(url='https://example.com/paper#b',title='B',origin='api_url_citation')])
        self.assertEqual(v.collect(job['id'])['usable'],1)
    def test_saving_creates_unread_card_without_invented_summary(self):
        a=area();row=candidate(a);sid=self.save(row,must_read=True,reason='Read the methods')
        card=r.source(sid)['payload'];self.assertEqual(card['synopsis'],'');self.assertEqual(card['excerpt'],'');self.assertEqual(card['read_state'],'unread');self.assertTrue(card['must_read'])
    def test_existing_source_is_preserved_and_linked(self):
        a=area();sid=source(a,url='https://example.com/paper#methods',synopsis='Existing owner notes');row=candidate(a)
        self.assertEqual(self.save(row,title='Different title',must_read=False),sid)
        self.assertEqual(r.source(sid)['payload']['synopsis'],'Existing owner notes');self.assertEqual(len(r.sources(a)),1)
    def test_two_research_jobs_cannot_duplicate_cards(self):
        a=area();one=candidate(a);two=candidate(a)
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(self.save,[one,two]))
        self.assertEqual(results[0],results[1]);self.assertEqual(len(r.sources(a)),1)
    def test_repeat_save_and_changed_approval(self):
        a=area();row=candidate(a);sid=self.save(row);self.assertEqual(sid,self.save(row))
        with self.assertRaises(ValueError):self.save(row,title='Different')
    def test_dismissed_reference_stays_dismissed(self):
        a=area();row=candidate(a);v.dismiss(row['id'],v.proposal_hash(row));v.collect(row['job_id'])
        self.assertEqual(v.listing(a),[]);self.assertEqual(len(v.listing(a,'dismissed')),1)
        with self.assertRaises(ValueError):self.save(row)
    def test_revised_output_requires_recollection(self):
        a=area();row=candidate(a)
        with p.connect() as db:job=db.execute('SELECT project_id FROM research_jobs WHERE id=?',(row['job_id'],)).fetchone()
        project=p.get(job['project_id']);record=json.loads(project['tasks'][0]['result_json']);path=Path(record['output']);path.write_text('Owner-reviewed revised research.');record['content_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        with p.connect() as db:db.execute('UPDATE project_tasks SET result_json=? WHERE project_id=?',(json.dumps(record),job['project_id']))
        with self.assertRaisesRegex(ValueError,'revised'):self.save(row)
        v.collect(row['job_id']);fresh=v.candidate(row['id']);self.assertNotEqual(v.proposal_hash(row),v.proposal_hash(fresh));self.assertTrue(self.save(fresh))
    def test_synopsis_application_keeps_prior_contents_and_flags(self):
        a=area();sid=source(a,synopsis='Previous owner summary',must_read=True);job,_=complete(a,'synopsis',[sid]);value=v.synopsis_preview(job['id'])
        v.apply_synopsis(job['id'],value['output_hash'],value['target']['version'],'Reviewed summary')
        self.assertEqual(r.source(sid)['payload']['synopsis'],'Reviewed summary');self.assertTrue(r.source(sid)['payload']['must_read'])
        self.assertEqual(json.loads(v.history(sid)[0]['previous_json'])['synopsis'],'Previous owner summary')
    def test_synopsis_requires_approved_matching_job(self):
        a=area();sid=source(a);job,_=complete(a,'synopsis',[sid],approved=False)
        with self.assertRaises(ValueError):v.synopsis_preview(job['id'])
        web,_=complete(a)
        with self.assertRaises(ValueError):v.synopsis_preview(web['id'])
    def test_stale_source_form_is_refused(self):
        a=area();sid=source(a);job,_=complete(a,'synopsis',[sid]);value=v.synopsis_preview(job['id']);r.save_source(a,values(read_state='read'),source_id=sid,version=1)
        with self.assertRaises(ValueError):v.apply_synopsis(job['id'],value['output_hash'],1,'Reviewed summary')
    def test_changed_source_material_is_not_silently_reused(self):
        a=area();sid=source(a);job,_=complete(a,'synopsis',[sid]);r.save_source(a,values(excerpt='Different paper content'),source_id=sid,version=1)
        with self.assertRaisesRegex(ValueError,'material'):v.synopsis_preview(job['id'])
    def test_changed_file_is_not_adopted(self):
        a=area();local.store_bytes('marketing','paper.txt',b'Original');sid=source(a,filename='paper.txt');job,_=complete(a,'synopsis',[sid]);local.file_for('marketing','paper.txt').write_text('Changed')
        with self.assertRaises(ValueError):v.synopsis_preview(job['id'])
    def test_repeat_and_concurrent_apply_do_not_overwrite_twice(self):
        a=area();sid=source(a);job,_=complete(a,'synopsis',[sid]);value=v.synopsis_preview(job['id'])
        def apply(_):return v.apply_synopsis(job['id'],value['output_hash'],1,'Reviewed summary')
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(apply,range(2)))
        self.assertEqual(results,[sid,sid]);self.assertEqual(len(v.history(sid)),1);self.assertEqual(r.source(sid)['version'],2)
    def test_changed_apply_text_after_application_is_refused(self):
        a=area();sid=source(a);job,_=complete(a,'synopsis',[sid]);value=v.synopsis_preview(job['id']);v.apply_synopsis(job['id'],value['output_hash'],1,'First reviewed summary')
        with self.assertRaises(ValueError):v.apply_synopsis(job['id'],value['output_hash'],1,'Different summary')
    def test_archiving_blocks_card_changes(self):
        a=area();row=candidate(a);r.update(a,1,'Archived','Question?','','archived')
        with self.assertRaises(ValueError):self.save(row)
    def test_invalid_page_and_length(self):
        a=area()
        with self.assertRaises(ValueError):v.listing(a,page=0)
        sid=source(a);job,_=complete(a,'synopsis',[sid]);value=v.synopsis_preview(job['id'])
        with self.assertRaises(ValueError):v.apply_synopsis(job['id'],value['output_hash'],1,'x'*2501)


class ReviewWebTests(unittest.TestCase):
    setUp=DialogueWebTests.setUp
    tearDown=DialogueWebTests.tearDown
    token=DialogueWebTests.token
    login=DialogueWebTests.login
    def test_authentication_and_csrf(self):
        self.assertEqual(self.client.get('/research-review/area/unknown',follow_redirects=False).status_code,303)
        self.login()
        for url in ('/research-review/job/id/collect','/research-review/job/id/apply','/research-review/citation/id/save'):
            self.assertEqual(self.client.post(url,data={}).status_code,403)
    def test_collection_and_save_flow(self):
        csrf=self.login();a=area();job,_=complete(a)
        self.assertIn('/research-review/job/'+job['id']+'/collect',self.client.get('/research-desk/'+a).text)
        result=self.client.post('/research-review/job/'+job['id']+'/collect',data={'csrf':csrf});self.assertEqual(result.status_code,200)
        row=v.listing(a)[0];page=self.client.get('/research-review/area/'+a);self.assertIn('Paper A',page.text)
        response=self.client.post('/research-review/citation/'+row['id']+'/save',data=dict(csrf=csrf,expected_hash=v.proposal_hash(row),title='Reviewed title'),follow_redirects=False)
        self.assertEqual(response.status_code,303);self.assertTrue(response.headers['location'].startswith('/research-desk/source/'))
    def test_synopsis_apply_and_history_flow(self):
        csrf=self.login();a=area();sid=source(a);job,_=complete(a,'synopsis',[sid]);value=v.synopsis_preview(job['id'])
        page=self.client.get('/research-review/job/'+job['id']+'/synopsis');self.assertIn('A concise source synopsis.',page.text)
        response=self.client.post('/research-review/job/'+job['id']+'/apply',data=dict(csrf=csrf,expected_output=value['output_hash'],expected_version=1,synopsis='Owner-reviewed synopsis'),follow_redirects=False)
        self.assertEqual(response.status_code,303);self.assertIn('Owner-reviewed synopsis',self.client.get('/research-review/source/'+sid+'/history').text)
    def test_unapproved_output_has_no_intake_button(self):
        self.login();a=area();job,_=complete(a,approved=False);page=self.client.get('/research-desk/'+a)
        self.assertNotIn('action="/research-review/job/'+job['id']+'/collect"',page.text)
        self.assertEqual(self.client.get('/research-review/job/'+job['id']+'/synopsis').status_code,400)
    def test_titles_and_synopses_are_escaped(self):
        self.login();a=area();job,_=complete(a,refs=[dict(url='https://example.com/a',title='<script>bad</script>',origin='api_url_citation')]);v.collect(job['id'])
        self.assertNotIn('<script>bad',self.client.get('/research-review/area/'+a).text)
        sid=source(a);job,_=complete(a,'synopsis',[sid],body='<img src=x onerror=bad()>');page=self.client.get('/research-review/job/'+job['id']+'/synopsis')
        self.assertNotIn('<img src=x',page.text);self.assertIn('&lt;img',page.text)


del DialogueTests,DialogueWebTests
