"""Recurring review, bounded launch, progress and stop/recovery integration."""
import json,os,re,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace as NS
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from superhuman.supervision import store,engine,context
from superhuman.agentic import store as agent
from superhuman.projects import engine as p
from superhuman.planning import store as planning
from superhuman.repairs import scheduler,actions,checks
from superhuman.hosted import jobs,worker,auth,config,web
from test_agentic import Client as ActionClient,decision

class Planner:
    def __init__(self,action='propose',effect=None):self.calls=0;self.action=action;self.effect=effect;self.chat=NS(completions=NS(create=self.create))
    def create(self,**kwargs):
        self.calls+=1;body=json.loads(kwargs['messages'][1]['content'])
        value={'action':self.action,'target_key':body['eligible_targets'][0]['key'],'title':'Prepare evidence summary','instruction':'Use calculate to compute 2+3 and provide an evidence-backed result.','summary':'A scoped result is the next ready step. Overall progress requires owner review.'}
        if self.effect:
            result=self.effect(value)
            if isinstance(result,Exception):raise result
            if result is not None:value=result
        return NS(choices=[NS(message=NS(content=json.dumps(value),refusal=None),finish_reason='stop')])

class SupervisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=Path.cwd();os.chdir(self.tmp.name)
        self.env=patch.dict(os.environ,{'SUPERHUMAN_PLANNING_DB':str(Path('plans.db').resolve()),'SUPERHUMAN_KNOWLEDGE_DB':str(Path('notes.db').resolve()),'SUPERHUMAN_IDENTITY_DIR':str(Path('identity').resolve()),'SUPERHUMAN_MEMORY_PATH':str(Path('old-memory.json').resolve()),'SUPERHUMAN_MAIL_KEY_FILE':str(Path('mail.key').resolve())});self.env.start()
    def tearDown(self):self.env.stop();os.chdir(self.old);self.tmp.cleanup()
    def policy(self,scope='marketing',mode='review',enabled=True,total=30,events=False,allowed=('calculate',),required=('calculate',),mission='Advance the saved goal with reviewed evidence.'):
        old=store.policy(scope)
        return store.save(scope,old['version'] if old else 0,mission,'A verified arithmetic result with limitations.',mode,enabled,1,events,total,4,6,allowed,required)
    def goal(self,scope='marketing',status='active'):
        return planning.save_goal(scope,planning.snapshot(scope)['goal']['version'],'Complete evidence','high','','Reviewed evidence',goal_status=status,completion_note='Assessed' if status=='complete' else '')
    def milestone(self,title='Evidence',deps=(),status='planned',projects=()):
        from uuid import uuid4
        return planning.save_milestone('marketing',uuid4().hex,0,title,'','Checked output',status,project_ids=projects,depends_on=deps)
    def cycle(self,planner=None):return engine.tick(client=planner or Planner())
    def item(self):return store.proposals('marketing')[0]
    def launch(self):return engine.launch(self.item()['id'],self.item()['version'])
    def complete(self,pid,approve=False):
        p.run_one(pid,client=ActionClient(decision()));aid=agent.get(pid)['actions'][0]['id'];p.run_one(pid,client=ActionClient(decision(action='finish',evidence=[aid])))
        if approve:p.review(pid,'final','approve','Checked actual evidence')
    def test_no_policy_is_off_and_does_not_create_tables_or_call_model(self):
        fake=Planner();self.assertIsNone(engine.tick(client=fake));self.assertEqual(fake.calls,0);self.assertIsNone(store.policy('marketing'));self.assertFalse(p.DEFAULT_DB.exists())
    def test_review_creates_proposal_without_starting_paid_run(self):
        self.policy();fake=Planner();result=self.cycle(fake);self.assertEqual(result['status'],'proposed');self.assertEqual(fake.calls,1);self.assertIsNone(self.item()['project_id']);self.assertEqual(store.policy('marketing')['allocated_calls'],1)
    def test_auto_launch_reserves_allowance_and_executes_existing_core(self):
        self.policy(mode='auto');self.cycle();item=self.item();pid=item['project_id'];self.assertTrue(pid);self.assertEqual(store.policy('marketing')['allocated_calls'],5);self.assertEqual(p.get(pid)['used_calls'],0)
        self.complete(pid);self.assertEqual(p.get(pid)['status'],'needs_review');self.assertEqual(agent.get(pid)['state'],'completed');self.assertEqual(context.progress('marketing')['runs'][0]['used_calls'],2)
    def test_manual_approval_is_atomic_and_idempotent(self):
        self.policy();self.cycle();item=self.item();pid=self.launch()
        with self.assertRaises(ValueError):engine.launch(item['id'],item['version'])
        self.assertEqual(store.policy('marketing')['allocated_calls'],5);self.assertEqual(len(p.get(pid)['tasks']),1)
    def test_concurrent_approval_only_launches_one_run(self):
        self.policy();self.cycle();item=self.item()
        def start(_):
            try:return engine.launch(item['id'],item['version'])
            except ValueError:return None
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(start,range(2)))
        self.assertEqual(sum(x is not None for x in results),1);self.assertEqual(store.policy('marketing')['allocated_calls'],5)
    def test_total_budget_stops_launch_without_partial_project_or_allocation(self):
        self.policy(total=4);self.cycle()
        with self.assertRaisesRegex(ValueError,'unallocated'):self.launch()
        self.assertEqual(store.policy('marketing')['allocated_calls'],1);self.assertIsNone(self.item()['project_id'])
        with p.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM projects').fetchone()[0],0)
    def test_total_budget_cannot_reset_below_allocations(self):
        self.policy();self.cycle();self.launch()
        with self.assertRaises(ValueError):self.policy(total=4)
        self.assertEqual(store.policy('marketing')['allocated_calls'],5)
    def test_managed_run_budget_cannot_exceed_reserved_amount(self):
        self.policy();self.cycle();pid=self.launch()
        with self.assertRaisesRegex(ValueError,'fixed at launch'):p.budget(pid,8)
        self.assertEqual(p.get(pid)['max_calls'],4)
    def test_normal_agent_run_budget_still_can_be_raised(self):
        pid=agent.create('marketing','Manual','Compute',['calculate'],max_calls=4);p.budget(pid,8);self.assertEqual(p.get(pid)['max_calls'],8)
    def test_department_pause_gates_managed_steps_but_not_manual_runs(self):
        self.policy(mode='auto');self.cycle();pid=self.item()['project_id'];pol=store.policy('marketing');store.control('marketing',pol['version'],'pause')
        manual=agent.create('marketing','Manual','Compute',['calculate']);self.assertEqual(scheduler.order([pid,manual],p.DEFAULT_DB),[manual]);self.assertIsNone(p.run_one(pid,client=ActionClient()))
    def test_withdrawn_tool_grant_holds_existing_run(self):
        self.policy(mode='auto');self.cycle();pid=self.item()['project_id'];self.policy(mode='auto',allowed=('workspace.list',),required=('workspace.list',))
        good,reason=store.managed_gate(pid);self.assertFalse(good);self.assertIn('withdrawn',reason)
    def test_held_goal_never_sends_planner_request(self):
        self.goal(status='on_hold');self.policy(mode='auto');fake=Planner();self.cycle(fake);self.assertEqual(fake.calls,0);self.assertEqual(store.proposals('marketing'),[])
    def test_open_department_blocker_never_sends_planner_request(self):
        self.goal();planning.save_blocker('marketing',__import__('uuid').uuid4().hex,0,'Need evidence','Owner','','open');self.policy();fake=Planner();self.cycle(fake);self.assertEqual(fake.calls,0)
    def test_dependency_selects_only_ready_milestone(self):
        a=self.milestone('First');self.milestone('Second',[a['id']]);self.policy();self.cycle();target=json.loads(self.item()['target_json']);self.assertEqual(target['milestone_id'],a['id'])
    def test_existing_linked_work_blocks_duplicate_milestone(self):
        from superhuman.runtime import engine as runtime
        pid=runtime.enqueue('collab','marketing','Already doing this','Existing');self.milestone(projects=[pid]);self.policy();fake=Planner();self.cycle(fake);self.assertEqual(fake.calls,0)
    def test_managed_run_is_linked_in_saved_plan_and_progress(self):
        m=self.milestone();self.policy(mode='auto');self.cycle();pid=self.item()['project_id'];self.assertIn(pid,planning.snapshot('marketing')['milestones'][0]['project_ids']);self.assertTrue(store.managed_gate(pid)[0]);self.complete(pid,approve=True)
        self.assertTrue(actions.milestone_progress('marketing')[m['id']]['ready_for_review']);self.assertEqual(planning.snapshot('marketing')['milestones'][0]['status'],'planned')
    def test_new_dependency_or_target_edit_holds_managed_run(self):
        m=self.milestone();self.policy(mode='auto');self.cycle();pid=self.item()['project_id'];planning.save_milestone('marketing',m['id'],1,'Changed target','','Different criteria','planned')
        self.assertEqual(scheduler.order([pid],p.DEFAULT_DB),[]);self.assertIn('changed',store.managed_gate(pid)[1])
    def test_pending_review_stops_further_paid_cycles(self):
        self.policy(mode='auto');self.cycle();pid=self.item()['project_id'];self.complete(pid);pol=store.policy('marketing');fake=Planner();engine.tick(client=fake,now=pol['next_due']+1);self.assertEqual(fake.calls,0);self.assertEqual(len(store.proposals('marketing')),1)
    def test_approved_mission_is_not_silently_repeated(self):
        self.policy(mode='auto');self.cycle();self.complete(self.item()['project_id'],approve=True);pol=store.policy('marketing');fake=Planner();engine.tick(client=fake,now=pol['next_due']+1);self.assertEqual(fake.calls,0);self.assertEqual(len(store.proposals('marketing')),1)
    def test_approved_milestone_advances_only_after_owner_completes_it(self):
        a=self.milestone('First');b=self.milestone('Second',[a['id']]);self.policy(mode='auto');self.cycle();self.complete(self.item()['project_id'],approve=True)
        pol=store.policy('marketing');fake=Planner();engine.tick(client=fake,now=pol['next_due']+1);self.assertEqual(fake.calls,0)
        planning.save_milestone('marketing',a['id'],1,'First','','Checked output','complete','Owner assessed');pol=store.policy('marketing');engine.tick(client=fake,now=pol['next_due']+1);self.assertEqual(fake.calls,1);self.assertEqual(json.loads(self.item()['target_json'])['milestone_id'],b['id'])
    def test_schedule_does_not_run_early(self):
        self.policy();self.cycle();pol=store.policy('marketing');fake=Planner();self.assertIsNone(engine.tick(client=fake,now=pol['last_checked']+30));self.assertEqual(fake.calls,0)
    def test_unchanged_waiting_context_does_not_pay_again(self):
        self.policy();self.cycle(Planner('wait'));pol=store.policy('marketing');fake=Planner();engine.tick(client=fake,now=pol['next_due']+1);self.assertEqual(fake.calls,0)
    def test_record_change_can_trigger_a_review_after_five_minutes(self):
        self.policy(events=True);self.cycle(Planner('wait'));pol=store.policy('marketing');self.goal();fake=Planner();engine.tick(client=fake,now=pol['last_checked']+301);self.assertEqual(fake.calls,1)
    def test_invalid_or_foreign_target_stops_and_requires_inspection(self):
        self.policy();fake=Planner(effect=lambda v:{**v,'target_key':'foreign:scope'});self.cycle(fake);pol=store.policy('marketing');self.assertTrue(pol['hold']);self.assertEqual(pol['allocated_calls'],1);self.assertEqual(store.proposals('marketing'),[])
        self.assertIsNone(engine.tick(client=Planner(),now=pol['next_due']+1))
        with self.assertRaises(ValueError):store.control('marketing',pol['version'],'review_now')
        store.control('marketing',pol['version'],'review_now','Inspected response. Retry this bounded review.');self.assertFalse(store.policy('marketing')['hold'])
    def test_uncertain_model_exception_is_charged_once_and_not_replayed(self):
        self.policy();self.cycle(Planner(effect=lambda v:RuntimeError('Uncertain outcome')));self.assertTrue(store.policy('marketing')['hold']);self.assertEqual(store.policy('marketing')['allocated_calls'],1)
    def test_policy_paused_while_model_working_cannot_launch(self):
        self.policy(mode='auto')
        def pause(value):store.control('marketing',store.policy('marketing')['version'],'pause');return value
        result=self.cycle(Planner(effect=pause));self.assertEqual(result['status'],'stale');self.assertEqual(store.proposals('marketing'),[])
    def test_saved_context_change_during_review_discards_proposal(self):
        self.policy();self.cycle(Planner(effect=lambda value:(self.goal(),value)[1]));self.assertEqual(store.proposals('marketing'),[])
    def test_owner_approval_rejects_stale_context_until_refresh(self):
        self.policy();self.cycle();self.goal()
        with self.assertRaisesRegex(ValueError,'context changed'):self.launch()
        item=self.item();engine.edit_proposal(item['id'],item['version'],'refresh');pid=self.launch();self.assertTrue(pid)
    def test_policy_change_requires_explicit_proposal_refresh(self):
        self.policy();self.cycle();self.policy(total=40)
        with self.assertRaisesRegex(ValueError,'Policy changed'):self.launch()
        item=self.item();engine.edit_proposal(item['id'],item['version'],'refresh');self.launch()
    def test_dismissed_proposal_does_not_repeat_but_owner_can_reopen(self):
        self.policy();self.cycle();item=self.item();engine.edit_proposal(item['id'],item['version'],'dismiss');pol=store.policy('marketing');fake=Planner();engine.tick(client=fake,now=pol['next_due']+1);self.assertEqual(fake.calls,0)
        item=self.item();engine.edit_proposal(item['id'],item['version'],'reopen');self.assertEqual(self.item()['status'],'proposed')
    def test_restart_marks_running_review_without_automatic_replay(self):
        self.policy()
        with p.connect() as db:db.execute("INSERT INTO supervision_cycles VALUES('c','marketing',1,'sig','running','',NULL,NULL,1,'now',NULL)")
        self.assertEqual(store.recover(),1);self.assertTrue(store.policy('marketing')['hold']);self.assertEqual(store.recover(),0)
    def test_rollback_holds_managed_runs_and_restores_with_policy_off(self):
        self.policy(mode='auto');self.cycle();pid=self.item()['project_id'];store.quarantine_for_rollback();self.assertTrue(jobs.worker_status()['paused']);self.assertEqual(p.get(pid)['tasks'][0]['status'],'supervision_unavailable');self.assertFalse(store.policy('marketing')['enabled'])
        store.recover();self.assertEqual(p.get(pid)['tasks'][0]['status'],'pending');self.assertEqual(agent.get(pid)['state'],'paused');self.assertFalse(store.managed_gate(pid)[0])
    def test_rollback_preserves_finished_output_review_state(self):
        self.policy(mode='auto');self.cycle();pid=self.item()['project_id'];self.complete(pid);store.quarantine_for_rollback();store.recover();self.assertEqual(p.get(pid)['tasks'][0]['status'],'needs_review');self.assertEqual(agent.get(pid)['state'],'completed')
    def test_auto_requires_verified_tool_requirement_and_valid_limits(self):
        with self.assertRaises(ValueError):self.policy(mode='auto',required=())
        with self.assertRaises(ValueError):self.policy(allowed=('shell',))
        self.assertIsNone(store.policy('marketing'))
    def test_stale_policy_controls_are_rejected(self):
        pol=self.policy();store.control('marketing',pol['version'],'pause')
        with self.assertRaises(ValueError):store.control('marketing',pol['version'],'review_now')
    def test_diagnostics_report_allocations_without_paid_calls(self):
        self.policy();self.cycle();result=checks.report();self.assertEqual(result['version'],'1.30.0');self.assertEqual(result['supervision'][0]['allocated_calls'],1);self.assertEqual(result['model_requests'],0)
    def test_web_auth_csrf_policy_proposal_and_department_links(self):
        settings=config.Settings('https://superhuman.example',state_dir=Path('state'));auth.Store(settings.auth_db).setup('owner','synthetic-test-passphrase')
        with TestClient(web.create_app(settings),base_url=settings.public_origin) as c:
            for url in ('/supervision','/supervision/marketing','/supervision/proposals/unknown'):self.assertEqual(c.get(url,follow_redirects=False).status_code,303)
            csrf=lambda page:re.search(r'name="csrf" value="([^"]+)"',page.text).group(1)
            c.post('/login',data={'csrf':csrf(c.get('/login')),'username':'owner','password':'synthetic-test-passphrase'})
            data={'version':0,'mission':'Advance evidence','acceptance':'Verified arithmetic','enabled':'true','mode':'review','allowed_tools':['calculate'],'required_tools':['calculate'],'interval_hours':1,'total_calls':30,'run_calls':4,'run_steps':6}
            self.assertEqual(c.post('/supervision/marketing/policy',data=data).status_code,403);data['csrf']=csrf(c.get('/supervision/marketing'));response=c.post('/supervision/marketing/policy',data=data,follow_redirects=False);self.assertEqual(response.status_code,303)
            self.cycle();item=self.item();url='/supervision/proposals/'+item['id'];page=c.get(url);self.assertIn('Prepare evidence summary',page.text);self.assertIn(url,c.get('/attention').text);self.assertIn('/supervision/marketing',c.get('/departments').text)
            payload={'version':item['version'],'action':'launch','title':item['title'],'instruction':item['instruction']};self.assertEqual(c.post(url+'/control',data=payload).status_code,403);payload['csrf']=csrf(page);response=c.post(url+'/control',data=payload,follow_redirects=False);self.assertEqual(response.status_code,303);self.assertIn('/agent-runs/',response.headers['location']);self.assertIn('Started by',c.get(response.headers['location']).text)
    def test_worker_runs_supervision_on_existing_persistent_loop(self):
        self.policy();fake=Planner();results=[]
        with patch('superhuman.mail.providers.run_sync',return_value=None):worker.serve(once=True,client=fake,report=results.append)
        self.assertEqual(fake.calls,1);self.assertTrue(results[0]['supervision_cycle_id']);self.assertEqual(self.item()['status'],'proposed')
    def test_concurrent_reviews_reserve_only_one_planner_attempt(self):
        import threading
        self.policy();fake=Planner();barrier=threading.Barrier(2)
        def provider(client):barrier.wait(timeout=5);return client
        with patch('superhuman.projects.engine.client_or_default',side_effect=provider):
            with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:engine.tick(client=fake),range(2)))
        self.assertEqual(fake.calls,1);self.assertEqual(store.policy('marketing')['allocated_calls'],1);self.assertEqual(len(store.proposals('marketing')),1)
    def test_planner_limit_stops_even_an_explicit_new_review(self):
        self.policy(total=1);self.cycle(Planner('wait'));pol=store.policy('marketing');store.control('marketing',pol['version'],'review_now');fake=Planner();result=self.cycle(fake)
        self.assertEqual(result['status'],'budget_blocked');self.assertEqual(fake.calls,0);self.assertEqual(store.policy('marketing')['allocated_calls'],1)
    def test_required_tool_cost_must_fit_before_policy_can_enable(self):
        with self.assertRaisesRegex(ValueError,'cannot fit'):self.policy(mode='auto',allowed=('draft.create',),required=('draft.create',))
    def test_changed_goal_holds_existing_mission_run(self):
        self.goal();self.policy(mode='auto');self.cycle();pid=self.item()['project_id'];self.goal(status='on_hold');self.assertFalse(store.managed_gate(pid)[0]);self.assertEqual(scheduler.order([pid],p.DEFAULT_DB),[])
    def test_finished_milestones_do_not_fall_back_to_an_unbounded_mission(self):
        m=self.milestone();planning.save_milestone('marketing',m['id'],1,m['title'],'','Checked output','complete','Owner assessed');self.policy();fake=Planner();self.cycle(fake);self.assertEqual(fake.calls,0)
    def test_extra_model_permission_fields_are_rejected(self):
        self.policy();self.cycle(Planner(effect=lambda value:{**value,'allowed_tools':['shell']}));self.assertTrue(store.policy('marketing')['hold']);self.assertEqual(store.proposals('marketing'),[])
    def test_department_local_failure_does_not_stop_other_department(self):
        self.policy();self.policy(scope='career_rnd')
        original=context.build
        def build(pol,path):
            if pol['scope']=='marketing':raise ValueError('Broken local context')
            return original(pol,path)
        with patch('superhuman.supervision.context.build',side_effect=build):
            self.cycle();result=self.cycle()
        self.assertTrue(store.policy('marketing')['hold']);self.assertEqual(result['scope'],'career_rnd');self.assertEqual(len(store.proposals('career_rnd')),1)
    def test_rollback_does_not_quarantine_manual_agent_runs(self):
        self.policy(mode='auto');self.cycle();manual=agent.create('marketing','Manual run','Calculate',['calculate']);store.quarantine_for_rollback();self.assertEqual(p.get(manual)['tasks'][0]['status'],'pending');self.assertEqual(agent.get(manual)['state'],'ready')
    def test_department_context_does_not_include_other_workstream(self):
        from superhuman.capabilities import local
        local.store_bytes('career_rnd','other.txt',b'OTHER_DEPARTMENT_PRIVATE_MARKER');p.create('career_rnd','OTHER_DEPARTMENT_PRIVATE_MARKER','Private objective',8);pol=self.policy();view=context.build(pol);self.assertNotIn('OTHER_DEPARTMENT_PRIVATE_MARKER',json.dumps(view['body']))
    def test_supervised_run_creates_real_word_artifact_and_waits_for_review(self):
        from superhuman.capabilities import exports
        self.policy(mode='auto',allowed=('document.export',),required=('document.export',));self.cycle(Planner(effect=lambda v:{**v,'instruction':'Export the checked evidence to Word.'}));pid=self.item()['project_id']
        p.run_one(pid,client=ActionClient(decision('document.export',{'title':'Evidence','format':'docx','text':'Checked evidence for owner review.'})));a=agent.get(pid)['actions'][0];record=json.loads(a['result_json']);file,_=exports.artifact('marketing',record['export_id']);self.assertTrue(file.exists())
        p.run_one(pid,client=ActionClient(decision(action='finish',evidence=[a['id']])));self.assertEqual(p.get(pid)['status'],'needs_review');self.assertEqual(store.policy('marketing')['allocated_calls'],5);self.assertEqual(p.get(pid)['used_calls'],2)

    def test_changed_mission_holds_earlier_run(self):
        self.policy(mode='auto');self.cycle();pid=self.item()['project_id'];self.policy(mode='auto',mission='A newly authorized different mission.')
        self.assertFalse(store.managed_gate(pid)[0]);self.assertIn('mission',store.managed_gate(pid)[1])
    def test_budget_changed_under_older_code_cannot_escape_reservation(self):
        self.policy(mode='auto');self.cycle();pid=self.item()['project_id']
        with p.connect() as db:db.execute('UPDATE projects SET max_calls=20 WHERE id=?',(pid,))
        self.assertEqual(scheduler.order([pid],p.DEFAULT_DB),[]);self.assertIn('reserved allowance',store.managed_gate(pid)[1])
    def test_cancelled_target_can_be_revised_for_a_fresh_bounded_attempt(self):
        m=self.milestone();self.policy(mode='auto');self.cycle();old=self.item()['project_id'];agent.control(old,agent.get(old)['version'],'cancel')
        planning.save_milestone('marketing',m['id'],1,'Revised evidence','','A new checked criterion','planned');self.assertNotIn(old,planning.snapshot('marketing')['milestones'][0]['project_ids'])
        pol=store.policy('marketing');engine.tick(client=Planner(),now=pol['next_due']+1);self.assertEqual(len(store.proposals('marketing')),2);self.assertNotEqual(self.item()['project_id'],old)
