"""Persistent ownership, budget, governance, coordination and restart integration."""
import json,os,re,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from superhuman.team import store,budget,work,engine
from superhuman.projects import engine as p
from superhuman.agentic import store as agent
from superhuman.repairs import scheduler,checks
from superhuman.hosted import jobs,worker,web,auth,config
from test_agentic import Client as ActionClient,decision
MODEL='synthetic-team-model'
class Metered(ActionClient):
    def create(self,**kw):
        result=super().create(**kw);result.usage=N(prompt_tokens=100,completion_tokens=20);result.id='synthetic-response';return result

def twin(action='wait',task=None,**changes):
    d={k:'' for k in engine.STRINGS};d.update(action=action,task_id=task['id'] if task else '',task_version=task['version'] if task else 0,request_version=0,dependency_ids=[],rationale='Follow the saved owner framework.',reply='The next internal step is recorded.')
    d.update(changes);return d

class TeamTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=Path.cwd();os.chdir(self.tmp.name)
        self.env=patch.dict(os.environ,{'SUPERHUMAN_PLANNING_DB':str(Path('plan.db').resolve()),'SUPERHUMAN_KNOWLEDGE_DB':str(Path('notes.db').resolve()),'SUPERHUMAN_IDENTITY_DIR':str(Path('identity').resolve()),'SUPERHUMAN_MEMORY_PATH':str(Path('old-memory.json').resolve()),'SUPERHUMAN_MAIL_KEY_FILE':str(Path('mail.key').resolve())});self.env.start()
    def tearDown(self):self.env.stop();os.chdir(self.old);self.tmp.cleanup()
    def boot(self,enabled=True):
        store.initialize();budget.create_period(1,.3,.5,.1);budget.set_rate(MODEL,'.1','.2','Synthetic test rates');budget.set_rate('gpt-4o-mini','.1','.2','Synthetic test rates');store.configure(store.settings()['version'],enabled,MODEL)
    def project(self,risk='routine',sensitivity='internal',priority='P2'):return store.create_project('marketing','Evidence project','Prepare checked evidence.','An accurate reviewable result.',priority,risk,sensitivity)
    def task(self,project=None,owner='marketing',title='Calculate evidence',**kw):return store.create_task(project or self.project(),owner,title,'Calculate 2+3 and provide action evidence.','Verified total five.',**kw)
    def ready(self,ident):
        t=store.task(ident);engine.apply(twin('assign',t,recipient=t['owner']));return store.task(ident)
    def runid(self,ident):
        t=self.ready(ident);return work.dispatch(t['id'],t['version'])
    def complete(self,ident):
        t=store.task(ident);pid=t['run_id'];p.run_one(pid,client=Metered(decision()));aid=agent.get(pid)['actions'][0]['id'];p.run_one(pid,client=Metered(decision(action='finish',evidence=[aid])));work.refresh();return store.task(ident)
    def test_default_off_and_no_read_side_creation(self):
        self.assertFalse(store.enabled());self.assertEqual(store.employees(),[]);self.assertIsNone(engine.tick(client=Metered()));self.assertFalse(p.DEFAULT_DB.exists())
    def test_eight_identities_and_seven_writing_skills(self):
        store.initialize();self.assertEqual(len(store.employees()),8);self.assertIn('twin',[e['id'] for e in store.employees()]);self.assertNotIn('writing',[e['id'] for e in store.employees()]);self.assertIsNone(store.skill('twin'));self.assertTrue(all(store.skill(e) for e in store.EMPLOYEES if e!='twin'))
    def test_prerequisite_cannot_downgrade_classification(self):
        self.boot();source=self.task(self.project(sensitivity='restricted'))
        with self.assertRaises(ValueError):self.task(deps=[source])
    def test_cross_department_sensitive_dependency_needs_owner_start(self):
        self.boot();q=self.project(sensitivity='confidential');source=self.task(q,owner='career_rnd');target=self.task(q,title='Use prerequisite',deps=[source]);self.assertTrue(store.needs_owner(store.task(target)))
    def test_parent_controls_strengthen_explicit_task_overrides(self):
        self.boot();q=self.project();tid=self.task(q,risk='routine',sensitivity='internal');parent=store.project(q);store.update_project(q,parent['version'],'P2','high_risk','restricted','active');self.assertEqual(store.effective(store.task(tid))['sensitivity'],'restricted');self.assertTrue(store.needs_owner(store.task(tid)))
    def test_default_employee_can_propose_memory(self):
        store.initialize();self.assertTrue(all('team.remember' in json.loads(e['allowed_tools']) for e in store.employees()))
    def test_writer_is_not_a_new_team_department(self):
        with self.assertRaises(ValueError):store.create_project('writing','X','X','X')
    def test_enable_requires_budget_and_rate_card(self):
        store.initialize()
        with self.assertRaises(ValueError):store.configure(1,True,MODEL)
        self.assertFalse(store.enabled())
    def test_settings_optimistic_lock(self):
        self.boot();old=store.settings();store.configure(old['version'],False,MODEL)
        with self.assertRaises(ValueError):store.configure(old['version'],True,MODEL)
    def test_owner_project_and_task_inherit_governance(self):
        self.boot();q=self.project(risk='high_risk',sensitivity='restricted',priority='P0');t=store.task(self.task(q));self.assertEqual(store.effective(t),{'priority':'P0','risk':'high_risk','sensitivity':'restricted'})
    def test_twin_cannot_lower_project_risk_or_sensitivity(self):
        self.boot();q=self.project(risk='high_risk',sensitivity='confidential')
        with self.assertRaises(ValueError):store.create_task(q,'marketing','Task','Instructions','Criteria',risk='routine',actor='twin')
    def test_duplicate_tasks_do_not_create_competing_owners(self):
        self.boot();q=self.project();self.task(q)
        with self.assertRaises(ValueError):self.task(q,title=' calculate evidence ')
    def test_dependencies_must_exist(self):
        self.boot()
        with self.assertRaises(ValueError):self.task(deps=['missing'])
    def test_routine_assignment_executes_existing_core_and_meter(self):
        self.boot();tid=self.task();pid=self.runid(tid);t=self.complete(tid);self.assertEqual(t['state'],'awaiting_review');self.assertEqual(p.get(pid)['used_calls'],2);r=budget.report();self.assertGreater(r['totals']['staff'],0);self.assertTrue(all(c['task_id']==tid for c in r['costs']))
    def test_twin_approves_routine_artifact_with_evidence(self):
        self.boot();tid=self.task();pid=self.runid(tid);t=self.complete(tid);work.review(tid,t['version'],True,'Output satisfies the task acceptance criteria.');self.assertEqual(store.task(tid)['state'],'completed');self.assertEqual(p.get(pid)['status'],'approved');self.assertEqual(store.project(t['project_id'])['status'],'active')
    def test_high_risk_needs_owner_start_and_output_approval(self):
        self.boot();tid=self.task(self.project(risk='high_risk'));t=self.ready(tid);self.assertEqual(t['state'],'owner_review')
        with self.assertRaises(ValueError):work.dispatch(tid,t['version'])
        work.task_control(tid,t['version'],'approve_start');pid=work.dispatch(tid,store.task(tid)['version']);t=self.complete(tid)
        with self.assertRaises(ValueError):work.review(tid,t['version'],True,'Passes')
        work.review(tid,t['version'],True,'Owner verified.',actor='owner');self.assertEqual(p.get(pid)['status'],'approved')
    def test_restricted_information_requires_owner_even_for_routine_work(self):
        self.boot();t=store.task(self.task(self.project(sensitivity='restricted')));self.assertTrue(store.needs_owner(t))
    def test_project_governance_change_invalidates_previous_grant(self):
        self.boot();tid=self.task();pid=self.runid(tid);q=store.project(store.task(tid)['project_id']);store.update_project(q['id'],q['version'],'P1','consequential','internal','active');self.assertFalse(work.run_gate(pid)[0]);self.assertEqual(scheduler.order([pid],p.DEFAULT_DB),[])
    def test_team_employee_project_and_task_pauses_gate_execution(self):
        self.boot();tid=self.task();pid=self.runid(tid);e=next(e for e in store.employees() if e['id']=='marketing');store.employee_control(e['id'],e['version'],True,e['charter'],json.loads(e['allowed_tools']));self.assertFalse(work.run_gate(pid)[0])
        store.employee_control(e['id'],e['version']+1,False,e['charter'],json.loads(e['allowed_tools']));t=store.task(tid);work.task_control(tid,t['version'],'pause');self.assertFalse(work.run_gate(pid)[0]);work.task_control(tid,store.task(tid)['version'],'resume');self.assertTrue(work.run_gate(pid)[0])
        store.configure(store.settings()['version'],False,MODEL);self.assertFalse(work.run_gate(pid)[0])
    def test_withdrawn_employee_permission_holds_run(self):
        self.boot();tid=self.task();pid=self.runid(tid);e=next(e for e in store.employees() if e['id']=='marketing');store.employee_control(e['id'],e['version'],False,e['charter'],['calculate']);self.assertFalse(work.run_gate(pid)[0])
    def test_dependency_waits_for_approved_output(self):
        self.boot();q=self.project();a=self.task(q);b=self.task(q,title='Next task',deps=[a]);self.ready(b);self.assertFalse(work.gate(store.task(b))[0]);self.runid(a);t=self.complete(a);work.review(a,t['version'],True,'Checked');self.assertTrue(work.gate(store.task(b))[0])
    def test_damaged_artifact_cannot_be_approved(self):
        self.boot();tid=self.task();pid=self.runid(tid);t=self.complete(tid);result=json.loads(p.get(pid)['tasks'][0]['result_json']);Path(result['output']).write_text('Changed')
        with self.assertRaises(ValueError):work.review(tid,t['version'],True,'Approve')
        self.assertEqual(store.task(tid)['state'],'awaiting_review')
    def test_routine_revision_keeps_history_and_is_bounded(self):
        self.boot();tid=self.task();pid=self.runid(tid);t=self.complete(tid);work.review(tid,t['version'],False,'Explain the arithmetic.');self.assertEqual(store.task(tid)['attempts'],1);self.assertEqual(agent.get(pid)['state'],'ready');self.assertTrue(any(json.loads(e['detail_json']).get('actor')=='twin' for e in agent.get(pid)['events']))
    def test_priority_override_is_bounded_and_p0_reserved(self):
        self.boot();tid=self.task();t=store.task(tid);engine.apply(twin('reprioritize',t,priority='P1'));self.assertEqual(store.effective(store.task(tid))['priority'],'P1')
        with self.assertRaises(ValueError):engine.apply(twin('reprioritize',store.task(tid),priority='P0'))
        with self.assertRaises(ValueError):engine.apply(twin('reprioritize',store.task(tid),priority='P4'))
    def test_scheduler_respects_team_task_priority(self):
        self.boot();q=self.project(priority='P3');low=self.task(q);high=self.task(self.project(priority='P1'),title='High priority');a=self.runid(low);b=self.runid(high);self.assertEqual(scheduler.order([a,b],p.DEFAULT_DB),[b,a])
    def test_active_assignment_limit_is_enforced(self):
        self.boot();store.configure(store.settings()['version'],True,MODEL,1);q=self.project();a=self.task(q);b=self.task(q,title='Other task');self.runid(a);self.ready(b)
        with self.assertRaises(ValueError):work.dispatch(b,store.task(b)['version'])
    def test_confirmed_memory_is_scoped_and_proposals_are_excluded(self):
        self.boot();a=store.add_memory('twin','preference','PRIVATE_PERSONAL','twin_private','restricted');b=store.add_memory('career_rnd','fact','PRIVATE_RND','department','confidential');self.assertEqual(store.memory('twin','restricted'),[]);store.confirm_memory(a,1,True);store.confirm_memory(b,1,True)
        self.assertIn('PRIVATE_PERSONAL',json.dumps(store.memory('twin','restricted')));self.assertNotIn('PRIVATE_RND',json.dumps(store.memory('marketing','restricted')));self.assertNotIn('PRIVATE_PERSONAL',json.dumps(store.memory('marketing','restricted')))
    def test_shared_memory_rejects_sensitive_classification(self):
        self.boot()
        with self.assertRaises(ValueError):store.add_memory('marketing','fact','Sensitive','shared','confidential')
    def test_writing_skills_are_department_specific_and_versioned(self):
        self.boot();skill=store.skill('career_rnd');store.save_skill('career_rnd',skill['version'],'Explain methods and uncertainty.','Approved technical example.');self.assertIn('technical example',work.writing('career_rnd'));self.assertNotIn('technical example',work.writing('marketing'))
        from superhuman.identity.selection import select_context
        self.assertIn('Explain methods',select_context('career_rnd','Research')['preferences'])
        with self.assertRaises(ValueError):store.save_skill('career_rnd',skill['version'],'Old save')
    def test_temporary_constraints_expire_without_becoming_permanent_memory(self):
        self.boot();ident=store.add_message('temporary_constraint','Busy today',time.time()+10)
        with patch('time.time',return_value=time.time()+20):self.assertNotIn(ident,[m['id'] for m in store.messages()])
        self.assertEqual(store.memory('twin','restricted'),[])
    def test_twin_reads_owner_updates_and_wakes_on_changed_work(self):
        self.boot();store.add_message('instruction','Please review priorities.');fake=Metered(twin());result=engine.tick(client=fake);self.assertEqual(result['status'],'completed');self.assertEqual(fake.calls,1)
        with patch('time.time',return_value=time.time()+10):self.assertIsNone(engine.tick(client=Metered()))
        self.assertEqual(budget.report()['costs'][0]['pool'],'twin')
    def test_twin_creates_and_assigns_persistent_specialist_work(self):
        self.boot();q=self.project();result=engine.tick(client=Metered(twin('create',project_id=q,recipient='marketing',title='New evidence task',instruction='Calculate 2+3.',acceptance='Total five.')));self.assertEqual(result['status'],'completed');t=store.tasks()[0]
        with patch('time.time',return_value=time.time()+10):result=engine.tick(client=Metered(twin('assign',t,recipient='marketing')))
        self.assertEqual(store.task(t['id'])['state'],'ready');result=engine.tick(client=Metered());self.assertEqual(result['status'],'dispatched')
    def test_twin_does_not_silently_confirm_personal_preferences(self):
        self.boot();store.add_message('preference','Prefer concise updates.');engine.tick(client=Metered(twin('propose_memory',instruction='Prefer concise updates.')));self.assertEqual(store.memory('twin','restricted'),[])
    def test_invalid_twin_response_holds_without_automatic_replay(self):
        self.boot();self.project();fake=Metered({'unexpected':'action'});result=engine.tick(client=fake);self.assertEqual(result['status'],'interrupted');self.assertTrue(store.settings()['hold']);self.assertIsNone(engine.tick(client=Metered()))
        with self.assertRaises(ValueError):engine.resume(store.settings()['version'],'')
        engine.resume(store.settings()['version'],'Inspected state and provider usage.');self.assertFalse(store.settings()['hold'])
    def test_owner_change_during_twin_request_invalidates_decision(self):
        self.boot();self.project()
        def change():store.add_message('priority_change','New deadline');return twin()
        result=engine.tick(client=Metered(change));self.assertEqual(result['status'],'interrupted')
    def test_unowned_run_cannot_use_employee_tools(self):
        self.boot();pid=agent.create('marketing','Manual','Task',['calculate'])
        with self.assertRaises(ValueError):work.request_tool('team.challenge',{'reason':'Concern','evidence':'Evidence','alternative':'Alternative'},agent.get(pid))
    def test_specialist_disagreement_stops_until_twin_or_owner_decision(self):
        self.boot();tid=self.task();pid=self.runid(tid);r=work.request_tool('team.challenge',{'reason':'Incorrect assumption','evidence':'Calculation differs','alternative':'Use corrected data'},agent.get(pid));req=store.requests()[0];self.assertEqual(store.task(tid)['state'],'disputed');self.assertFalse(work.run_gate(pid)[0])
        with self.assertRaises(ValueError):work.resolve_request(req['id'],req['version'],'alternative','I prefer it')
        work.resolve_request(req['id'],req['version'],'maintain','Keep the existing bounded instruction.');self.assertEqual(store.task(tid)['state'],'dispatched')
    def test_owner_can_authorize_specialist_alternative(self):
        self.boot();tid=self.task();pid=self.runid(tid);work.request_tool('team.challenge',{'reason':'Concern','evidence':'Evidence','alternative':'Use new data'},agent.get(pid));req=store.requests()[0];work.resolve_request(req['id'],req['version'],'alternative','Verified the specialist evidence.',actor='owner');self.assertIn('Owner-approved alternative',p.get(pid)['details'])
    def test_handoff_creates_owned_child_and_parent_waits(self):
        self.boot();tid=self.task();pid=self.runid(tid);work.request_tool('team.handoff',{'recipient':'career_rnd','title':'Check evidence','instruction':'Calculate a checked value.','acceptance':'Verified total'},agent.get(pid));req=store.requests()[0];child=work.resolve_request(req['id'],req['version'],'accept','Relevant domain help.');self.assertEqual(store.task(child)['owner'],'career_rnd');self.assertEqual(store.task(tid)['state'],'waiting_dependency');self.assertIn(child,json.loads(store.task(tid)['deps']))
        with self.assertRaises(ValueError):work.resolve_request(req['id'],req['version'],'accept','Repeat')
    def test_sensitive_handoff_requires_owner_approval(self):
        self.boot();tid=self.task(self.project(sensitivity='confidential'));pid=self.runid(tid);work.request_tool('team.handoff',{'recipient':'career_rnd','title':'Check','instruction':'Review evidence.','acceptance':'Checked evidence'},agent.get(pid));req=store.requests()[0]
        with self.assertRaises(ValueError):work.resolve_request(req['id'],req['version'],'accept','Share it')
        child=work.resolve_request(req['id'],req['version'],'accept','Approved sharing this brief.',actor='owner');self.assertEqual(store.effective(store.task(child))['sensitivity'],'confidential')
    def test_handoff_result_returns_to_parent_only_after_review(self):
        self.boot();tid=self.task();pid=self.runid(tid);work.request_tool('team.handoff',{'recipient':'career_rnd','title':'Checked value','instruction':'Calculate.','acceptance':'Five'},agent.get(pid));r=store.requests()[0];child=work.resolve_request(r['id'],r['version'],'accept','Please verify.');self.runid(child);t=self.complete(child);self.assertEqual(store.task(tid)['state'],'waiting_dependency');work.review(child,t['version'],True,'Checked evidence.');self.assertEqual(store.task(tid)['state'],'dispatched');self.assertIn('verified_output_excerpt',work.employee_context(store.task(tid)))
    def test_employee_memory_tool_proposes_only(self):
        self.boot();tid=self.task();pid=self.runid(tid);result=work.request_tool('team.remember',{'content':'Observed a useful method.'},agent.get(pid));self.assertEqual(result['data']['status'],'proposed');self.assertEqual(store.memory('marketing'),[])
    def test_unknown_or_self_handoff_is_rejected(self):
        self.boot();tid=self.task();pid=self.runid(tid)
        for recipient in ('twin','marketing','unknown'):
            with self.assertRaises(ValueError):work.request_tool('team.handoff',{'recipient':recipient,'title':'X','instruction':'X','acceptance':'X'},agent.get(pid))
    def test_stale_controls_do_not_override_current_task(self):
        self.boot();tid=self.task();t=store.task(tid);work.task_control(tid,t['version'],'pause')
        with self.assertRaises(ValueError):work.task_control(tid,t['version'],'resume')
    def test_task_limit_changes_are_explicit_and_audited(self):
        self.boot();tid=self.task();pid=self.runid(tid)
        with self.assertRaises(ValueError):p.budget(pid,20)
        t=store.task(tid);work.limits(tid,t['version'],20,24,8);self.assertEqual(p.get(pid)['max_calls'],20);self.assertEqual(store.task(tid)['cost_limit'],8000000)
    def test_legacy_writing_job_is_held_only_when_team_enabled(self):
        self.boot();pid=agent.create('writing','Legacy output','Draft',['calculate']);self.assertFalse(work.run_gate(pid)[0]);store.configure(store.settings()['version'],False,MODEL);self.assertTrue(work.run_gate(pid)[0])
    def test_pause_does_not_disable_dollar_guard(self):
        self.boot(False);fake=Metered('A reply');client=budget.wrap(fake);client.chat.completions.create(model=MODEL,messages=[{'role':'user','content':'Hello'}],max_completion_tokens=100);self.assertEqual(len(budget.report()['costs']),1)
    def test_rate_card_required_before_request(self):
        self.boot();fake=Metered('Reply')
        with self.assertRaises(budget.BudgetBlocked):budget.wrap(fake).chat.completions.create(model='unknown-model',messages=[{'role':'user','content':'Hello'}])
        self.assertEqual(fake.calls,0)
    def test_usage_is_settled_to_token_derived_estimate(self):
        self.boot();client=budget.wrap(Metered('Reply'));client.chat.completions.create(model=MODEL,messages=[{'role':'user','content':'Hello'}],max_completion_tokens=100);r=budget.report()['costs'][0];self.assertEqual(r['state'],'metered');self.assertEqual(r['charged_text'],14);self.assertEqual(r['input_tokens'],100)
    def test_hosted_search_is_bounded_and_metered(self):
        self.boot();seen=[]
        def create(**kw):
            seen.append(kw);return N(id='synthetic-search',usage=N(input_tokens=100,output_tokens=20),output=[N(type='web_search_call')])
        actual=N(responses=N(create=create));budget.wrap(actual).responses.create(model=MODEL,input='Research a local test question',tools=[{'type':'web_search'}],tool_choice='required',max_output_tokens=100)
        self.assertEqual(seen[0]['max_tool_calls'],1);self.assertEqual(budget.report()['costs'][0]['charged_tools'],25000);self.assertEqual(budget.report()['costs'][0]['charged_text'],14)
    def test_old_sdk_without_search_bound_stops_before_request(self):
        self.boot();seen=[]
        def create(model,input,tools):seen.append(True)
        with self.assertRaises(budget.BudgetBlocked):budget.wrap(N(responses=N(create=create))).responses.create(model=MODEL,input='Question',tools=[{'type':'web_search'}])
        self.assertEqual(seen,[]);self.assertEqual(budget.report()['costs'],[])
    def test_worker_uses_twin_without_competing_supervisor(self):
        self.boot();store.add_message('instruction','Acknowledge my internal update.');results=[];fake=Metered(json.dumps(twin()))
        with patch('superhuman.mail.providers.run_sync',return_value=None),patch('superhuman.supervision.engine.tick',side_effect=AssertionError('Competing supervisor')):worker.serve(once=True,client=fake,report=results.append)
        self.assertEqual(fake.calls,1);self.assertIn('team_cycle_id',results[0]);self.assertEqual(budget.report()['costs'][0]['pool'],'twin')
    def test_missing_usage_keeps_full_reservation(self):
        self.boot();budget.wrap(ActionClient('Reply')).chat.completions.create(model=MODEL,messages=[{'role':'user','content':'Hello'}],max_completion_tokens=100);r=budget.report()['costs'][0];self.assertEqual(r['state'],'uncertain');self.assertEqual(r['charged_text'],r['reserved_text'])
    def test_uncertain_provider_exception_is_not_refunded(self):
        self.boot()
        with self.assertRaises(RuntimeError):budget.wrap(Metered(RuntimeError('Uncertain'))).chat.completions.create(model=MODEL,messages=[{'role':'user','content':'Hello'}])
        self.assertEqual(budget.report()['costs'][0]['state'],'uncertain')
    def test_unmetered_multimodal_or_multiple_choice_requests_are_rejected(self):
        self.boot();client=budget.wrap(Metered())
        for kwargs in ({'messages':[{'role':'user','content':[{'type':'image_url','image_url':'x'}]}]},{'messages':[{'role':'user','content':'Hi'}],'n':2},{'messages':[{'role':'user','content':'Hi'}],'stream':True}):
            with self.assertRaises(budget.BudgetBlocked):client.chat.completions.create(model=MODEL,**kwargs)
    def test_insufficient_pool_stops_before_provider(self):
        self.boot();budget.set_rate(MODEL,'100','100','Synthetic high cost');fake=Metered()
        with self.assertRaises(budget.BudgetBlocked):budget.wrap(fake).chat.completions.create(model=MODEL,messages=[{'role':'user','content':'Hello'}],max_completion_tokens=8000)
        self.assertEqual(fake.calls,0)
    def test_concurrent_reservations_cannot_overdraw_pool(self):
        self.boot();budget.set_rate(MODEL,'50','50','Synthetic high cost')
        def reserve(_):
            try:return budget.reserve(MODEL,{'model':MODEL,'messages':[{'role':'user','content':'Hello'}],'max_completion_tokens':100},'chat')
            except budget.BudgetBlocked:return None
        with ThreadPoolExecutor(4) as pool:results=list(pool.map(reserve,range(4)))
        self.assertEqual(sum(x is not None for x in results),1);self.assertLessEqual(budget.report()['totals']['staff'],500000)
    def test_budget_cannot_reset_active_spending_and_reserve_needs_owner_transfer(self):
        self.boot()
        with self.assertRaises(ValueError):budget.create_period(1,.3,.5,.1)
        row=budget.current();budget.release_reserve(row['version'],'staff',.05);self.assertEqual(budget.current()['staff_cap'],550000)
        with self.assertRaises(ValueError):budget.release_reserve(row['version'],'staff',.05)
    def test_expired_period_blocks_paid_work_until_explicit_renewal(self):
        self.boot()
        with p.connect() as db:db.execute('UPDATE team_budget_periods SET end=?',(time.time()-1,))
        with self.assertRaises(budget.BudgetBlocked):budget.wrap(Metered()).chat.completions.create(model=MODEL,messages=[{'role':'user','content':'Hi'}])
    def test_task_dollar_limit_is_independent_of_request_count(self):
        self.boot();tid=self.task();pid=self.runid(tid)
        with p.connect() as db:db.execute('UPDATE team_tasks SET cost_limit=1 WHERE id=?',(tid,))
        p.run_one(pid,client=Metered(decision()));self.assertEqual(agent.get(pid)['state'],'interrupted');self.assertEqual(budget.report()['costs'],[])
    def test_meter_wraps_only_once_even_through_drafting_client(self):
        self.boot();pid=agent.create('marketing','Manual','Task',['calculate']);fake=Metered('A reply');limited=p.LimitedClient(fake,pid,p.DEFAULT_DB,1);budget.wrap(limited).chat.completions.create(model=MODEL,messages=[{'role':'user','content':'Hi'}],max_completion_tokens=100);self.assertEqual(fake.calls,1);self.assertEqual(len(budget.report()['costs']),1)
    def test_owner_can_reconcile_uncertain_reservation_with_evidence(self):
        self.boot();budget.wrap(ActionClient('Reply')).chat.completions.create(model=MODEL,messages=[{'role':'user','content':'Hi'}]);r=budget.report()['costs'][0];budget.reconcile(r['id'],.0001,'Verified provider usage record.');self.assertEqual(budget.report()['costs'][0]['charged_text'],100)
    def test_overrun_holds_further_spending(self):
        self.boot();ident=budget.reserve(MODEL,{'model':MODEL,'messages':[{'role':'user','content':'Hi'}],'max_completion_tokens':10},'chat');budget.settle(ident,N(usage=N(prompt_tokens=10000000,completion_tokens=1)));self.assertTrue(budget.current()['hold'])
        with self.assertRaises(budget.BudgetBlocked):budget.reserve(MODEL,{'messages':[{'role':'user','content':'Hi'}]},'chat')
    def test_restart_retains_cost_reservation_and_holds_twin(self):
        self.boot();ident=budget.reserve(MODEL,{'model':MODEL,'messages':[{'role':'user','content':'Hi'}]},'chat')
        with p.connect() as db:db.execute("INSERT INTO team_cycles VALUES('cycle','running','signature',NULL,NULL,'now',NULL)")
        self.assertEqual(engine.recover(),1);self.assertTrue(store.settings()['hold']);self.assertEqual(budget.report()['costs'][0]['state'],'uncertain');self.assertEqual(engine.recover(),0)
    def test_rollback_quarantines_only_team_runs_and_restores_held(self):
        self.boot();tid=self.task();pid=self.runid(tid);manual=agent.create('marketing','Manual','Task',['calculate']);engine.quarantine_for_rollback();self.assertEqual(p.get(pid)['tasks'][0]['status'],'team_unavailable');self.assertEqual(p.get(manual)['tasks'][0]['status'],'pending');self.assertTrue(jobs.worker_status()['paused']);self.assertFalse(store.enabled());engine.recover();self.assertEqual(p.get(pid)['tasks'][0]['status'],'pending');self.assertEqual(agent.get(pid)['state'],'paused');self.assertFalse(store.enabled())
    def test_rollback_preserves_completed_review_records(self):
        self.boot();tid=self.task();pid=self.runid(tid);self.complete(tid);engine.quarantine_for_rollback();engine.recover();self.assertEqual(p.get(pid)['status'],'needs_review');self.assertEqual(agent.get(pid)['state'],'completed')
    def test_diagnostics_read_team_without_paid_work(self):
        self.boot();result=checks.report();self.assertEqual(result['version'],'1.27.0');self.assertEqual(result['team']['employees'],8);self.assertEqual(result['model_requests'],0)
    def test_web_auth_csrf_twin_project_task_and_budget(self):
        settings=config.Settings('https://superhuman.example',state_dir=Path('state'));auth.Store(settings.auth_db).setup('owner','synthetic-test-passphrase')
        with TestClient(web.create_app(settings),base_url=settings.public_origin) as c:
            for url in ('/team','/team/twin','/team/budget','/team/memory'):self.assertEqual(c.get(url,follow_redirects=False).status_code,303)
            csrf=lambda page:re.search(r'name="csrf" value="([^"]+)"',page.text).group(1)
            c.post('/login',data={'csrf':csrf(c.get('/login')),'username':'owner','password':'synthetic-test-passphrase'})
            self.assertEqual(c.post('/team/setup',data={}).status_code,403);c.post('/team/setup',data={'csrf':csrf(c.get('/team'))});self.assertIn('seven specialists',c.get('/team').text);self.assertIn('Mahnoor Twin',c.get('/team/twin').text)
            d={'scope':'marketing','title':'UI project','objective':'Checked evidence','acceptance':'Reviewed output','priority':'P2','risk':'routine','sensitivity':'internal','csrf':csrf(c.get('/team'))};response=c.post('/team/projects',data=d,follow_redirects=False);self.assertEqual(response.status_code,303);self.assertIn('UI project',c.get(response.headers['location']).text)
            d={'kind':'instruction','content':'<script>bad()</script>','csrf':csrf(c.get('/team/twin'))};self.assertEqual(c.post('/team/twin/messages',data=d).status_code,200);self.assertNotIn('<script>bad()</script>',c.get('/team/twin').text);self.assertIn('&lt;script&gt;',c.get('/team/twin').text)
            self.assertIn('Writing is a skill of each specialist',c.get('/departments').text);self.assertNotIn('/team/employees/writing',c.get('/departments').text)
            self.assertEqual(c.post('/team/budget/rates',data={'model':MODEL,'input_rate':'.1','output_rate':'.2','source':'synthetic','csrf':csrf(c.get('/team/budget'))}).status_code,400)
