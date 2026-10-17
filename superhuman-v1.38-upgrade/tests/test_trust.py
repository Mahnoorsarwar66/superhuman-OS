"""Regressions derived from the v1.36 live audit; synthetic fixtures only."""
import json,re,time,hashlib
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch
from uuid import uuid4
from fastapi.testclient import TestClient
from test_workspace import WorkspaceBase
from superhuman.projects import engine as p,revisions
from superhuman.team import store as team,budget
from superhuman.foundation import context,storage
from superhuman.dialogue import engine as de,store as dialogue
from superhuman.experience import calendar,store as ux
from superhuman.practice import store as practice
from superhuman.teamhub import store as hub
from superhuman.interface.tree import parse

class TrustTests(WorkspaceBase):
 def setup_budget(self):
  budget.create_period(10,3,5,1);budget.set_rate('gpt-4o-mini','.1','.2','Synthetic test rate')
 def fake(self,usage=True,error=False):
  self.calls=[]
  def create(**kw):
   self.calls.append(kw)
   if error:raise RuntimeError('Synthetic uncertain provider failure')
   return N(id='qa-response',usage=N(prompt_tokens=30,completion_tokens=10) if usage else None,choices=[N(message=N(content=json.dumps({'reply':'QA-CEDAR-417; market size is unknown.','tasks':[]}),refusal=None),finish_reason='stop')])
  return N(chat=N(completions=N(create=create)),responses=N(create=create))
 def call(self,c):return budget.wrap(c).chat.completions.create(model='gpt-4o-mini',messages=[{'role':'user','content':'Synthetic test'}],max_completion_tokens=100)
 def test_missing_period_blocks_before_provider_for_all_actors(self):
  for actor in ('legacy','twin','marketing'):
   c=self.fake()
   with budget.scope(actor):
    with self.assertRaises(budget.BudgetBlocked):self.call(c)
   self.assertEqual(self.calls,[])
 def test_period_without_rate_blocks_before_provider(self):
  budget.create_period(10,3,5,1);c=self.fake()
  with self.assertRaises(budget.BudgetBlocked):self.call(c)
  self.assertEqual(self.calls,[])
 def test_chat_and_actor_are_accounted(self):
  self.setup_budget();c=self.fake()
  with budget.scope('twin'):self.call(c)
  row=budget.report()['costs'][0];self.assertEqual(row['actor'],'twin');self.assertEqual(row['state'],'metered');self.assertEqual(row['input_tokens'],30);self.assertGreater(row['charged_text'],0);self.assertEqual(len(self.calls),1)
 def test_unknown_usage_retains_reservation(self):
  self.setup_budget();self.call(self.fake(False));r=budget.report()['costs'][0];self.assertEqual(r['state'],'uncertain');self.assertEqual(r['charged_text'],r['reserved_text'])
 def test_provider_failure_retains_reservation(self):
  self.setup_budget()
  with self.assertRaises(RuntimeError):self.call(self.fake(error=True))
  self.assertEqual(budget.report()['costs'][0]['state'],'uncertain')
 def test_dialogue_without_budget_never_dispatches(self):
  rid=ux.create('twin','QA budget gate');dialogue.send(rid,'QA-CEDAR-417',uuid4().hex);c=self.fake();result=de.run_turn(client=c)
  self.assertEqual(result['status'],'failed');self.assertEqual(self.calls,[]);self.assertIn('No provider request',dialogue.turns(rid)[0]['error'])
 def test_dialogue_with_budget_records_reply_cost(self):
  self.setup_budget();rid=ux.create('twin','QA metered reply');dialogue.send(rid,'QA-CEDAR-417',uuid4().hex);self.assertEqual(de.run_turn(client=self.fake())['status'],'done');self.assertEqual(len(budget.report()['costs']),1)
 def test_blank_internal_query_is_safe_and_has_no_reference_leak(self):
  result={'preferences':'','references':'','trace':{'selected':[]}}
  self.assertEqual(context.selection(result,'marketing','',''),result)
 def test_multiline_internal_query_normalizes_but_user_search_stays_strict(self):
  with patch.object(storage,'search',return_value={'items':[],'issues':[]}) as search:context.selection({},'marketing','Title','First\nSecond\tThird');self.assertEqual(search.call_args.args[1],'Title First Second Third')
  with self.assertRaises(ValueError):storage.search('marketing','   ')
 def test_saved_unicode_draft_quality_check_does_not_invoke_search_error(self):
  q={'workstream':'marketing'};t={'kind':'collab','checks':json.dumps({'max_words':80})};result=revisions.assess(q,t,{},'QA-CEDAR-417: university’s checklist.\n• Leave unknown fields blank.')
  self.assertTrue(result['passes']);self.assertNotIn('Search',str(result))
 def test_empty_answer_not_persisted_as_fact(self):
  practice.setup();pid=self.project();r=practice.interview(pid);practice.save(pid,r['version'],{'materials':('answered',''),'current':('research','Unknown market size')},'internal');a=practice.answers(pid);self.assertEqual([x['key'] for x in a],['current']);self.assertEqual(a[0]['status'],'research')
 def test_unresolved_blank_status_is_retained(self):
  practice.setup();pid=self.project();practice.save(pid,practice.interview(pid)['version'],{'current':('later','')},'internal');self.assertEqual(practice.answers(pid)[0]['status'],'later')
 def test_utc_ics_preserves_title_and_time(self):
  v='BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:20261019T100000Z\nDTEND:20261019T103000Z\nSUMMARY:QA Cedar\\, title\nEND:VEVENT\nEND:VCALENDAR';r=calendar.extract_named(v)[0];self.assertEqual(r[4],'QA Cedar, title');self.assertEqual(calendar.local(r[2]).hour,15)
 def test_multiple_ics_titles_do_not_bleed(self):
  v=''.join('BEGIN:VEVENT\nDTSTART:20261019T100000Z\nSUMMARY:'+name+'\nEND:VEVENT\n' for name in ['First','Second']);self.assertEqual([r[4] for r in calendar.extract_named(v)],['First','Second'])
 def test_folded_ics_title_and_plain_text_fallback(self):
  v='BEGIN:VEVENT\nDTSTART:20261019T100000Z\nSUMMARY:Long QA\n  title\nEND:VEVENT';self.assertEqual(calendar.extract_named(v)[0][4],'Long QA title');self.assertEqual(calendar.extract_named('meeting 2026-10-19T10:00Z')[0][4],'Pasted invitation')
 def test_readiness_does_not_confuse_budget_with_team_activation(self):
  from superhuman.trust import readiness
  self.assertFalse(readiness()['work_ready']);self.setup_budget();self.assertTrue(readiness()['paid_ready']);self.assertFalse(readiness()['work_ready']);self.assertIn('disabled',readiness()['reason'])
 def test_labelled_credential_preview_is_masked_without_changing_source(self):
  from superhuman.trust import preview
  raw='Owner\nPassword: synthetic-sensitive-value\nAPI_KEY=test-synthetic-key\nMeeting note retained.';redacted=preview(raw)
  self.assertNotIn('synthetic-sensitive-value',redacted);self.assertNotIn('test-synthetic-key',redacted);self.assertIn('Meeting note retained.',redacted);self.assertIn('synthetic-sensitive-value',raw)

class TrustHTTPTests(WorkspaceBase):
 def setUp(self):
  super().setUp();practice.setup()
  from superhuman.hosted import auth,config,web
  self.cfg=config.Settings('https://superhuman.example',state_dir=Path('state'));auth.Store(self.cfg.auth_db).setup('owner','synthetic-test-passphrase');self.client=TestClient(web.create_app(self.cfg),base_url=self.cfg.public_origin);self.client.post('/login',data={'username':'owner','password':'synthetic-test-passphrase','csrf':self.csrf('/login')})
 def csrf(self,url):return re.search(r'name="csrf" value="([^"]+)"',self.client.get(url).text).group(1)
 def tearDown(self):self.client.close();super().tearDown()
 def test_new_project_can_start_as_milestones_and_prefills_interview(self):
  result=self.client.post('/workspace-projects/create',data=dict(scope='edsync_product',title='QA Cedar',objective='QA-CEDAR-417 objective',acceptance='Known acceptance',structure='milestones',csrf=self.csrf('/new-project')),follow_redirects=False)
  self.assertEqual(result.status_code,303);pid=result.headers['location'].split('/')[-1]
  from superhuman.milestones import store as ms
  self.assertIsNotNone(ms.managed(pid));self.assertFalse(ms.managed(pid)['enabled']);body=self.client.get(result.headers['location']).text;self.assertIn('QA-CEDAR-417 objective</textarea>',body);self.assertIn('Known acceptance</textarea>',body)
 def test_legacy_team_destinations_redirect_to_hub(self):
  for tab,view in [('board','employees'),('feed','activity')]:
   r=self.client.get('/team-room?tab='+tab,follow_redirects=False);self.assertEqual(r.status_code,303);self.assertIn('view='+view,r.headers['location'])
 def test_archived_room_disables_composer_and_backend_rejects(self):
  hub.initialize();rid=hub.primary('marketing');hub.room_control(rid,0,'QA archived',True,False,'')
  tree=parse(self.client.get('/team-room/'+rid).text);forms=[f for f in tree.find('form') if f.attrs.get('action')=='/team-room/'+rid+'/send'];self.assertEqual(len(forms),1);self.assertTrue(all('disabled' in n.attrs for n in forms[0].find('textarea')+forms[0].find('button')))
  with self.assertRaises(ValueError):dialogue.send(rid,'No archived dispatch',uuid4().hex)
 def test_generic_milestone_manage_has_no_endorsement_copy(self):
  from superhuman.milestones import store as ms
  pid=self.project('edsync_product');ms.attach(pid,'edsync_product');mid=ms.add(pid,'QA milestone','Business question','QA criteria',['edsync_product']);body=self.client.get('/milestones/'+mid+'?view=manage').text;self.assertIn('project-specific',body);self.assertNotIn('Katherine reviews',body);self.assertNotIn('M1 guide integration',body)
 def test_team_readiness_and_canonical_tabs(self):
  body=self.client.get('/team-hub').text;self.assertIn('Work blocked',body);self.assertIn('Team coordination is disabled',body);self.assertIn('/team-hub?view=employees',self.client.get('/team/budget').text)
 def test_portrait_cache_refresh_and_visibility_css(self):
  self.assertIn('.png?v=137',self.client.get('/team-hub').text);css=self.client.get('/assets/teamhub.css').text;self.assertIn('visibility:visible!important',css);self.assertIn('width:128px',css)
 def test_ics_title_route_and_no_external_event_creation(self):
  text='BEGIN:VEVENT\nDTSTART:20261019T100000Z\nSUMMARY:QA test title\nEND:VEVENT';r=self.client.post('/calendar-intake/paste',data={'content':text,'csrf':self.csrf('/calendar-intake')});self.assertEqual(r.status_code,200);self.assertIn('QA test title',r.text);self.assertIn('03:00 PM PKT',r.text)
 def test_budget_notice_explicit_and_no_automatic_authorization(self):
  self.assertIn('Earlier unmetered history',self.client.get('/team/budget').text);self.assertIsNone(budget.current())
