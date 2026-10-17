"""Durable action loop, real local adapters, permission and interruption cases."""
import json,os,re,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from fastapi.testclient import TestClient
from superhuman.agentic import store,engine,tools
from superhuman.projects import engine as p
from superhuman.repairs import scheduler
from superhuman.capabilities import local,coding,exports
from superhuman.hosted import web,config,auth,jobs

def decision(tool='calculate',arguments=None,action='tool',evidence=()):
    return {'action':action,'tool':tool,'arguments_json':json.dumps(arguments if arguments is not None else {'expression':'2+3'}),'rationale':'Complete requested step','final_message':'Result checked and ready for review.' if action=='finish' else '', 'evidence_action_ids':list(evidence)}
class Client:
    def __init__(self,*values):self.values=list(values);self.calls=0;self.chat=NS(completions=NS(create=self.create));self.responses=NS(create=self.create)
    def create(self,**kw):
        self.calls+=1;value=self.values.pop(0)
        if isinstance(value,Exception):raise value
        if callable(value):value=value()
        return NS(choices=[NS(message=NS(content=json.dumps(value) if isinstance(value,dict) else value),finish_reason='stop')])
class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=Path.cwd();os.chdir(self.tmp.name)
        self.env=patch.dict(os.environ,{'SUPERHUMAN_PLANNING_DB':str(Path('plan.db').resolve()),'SUPERHUMAN_KNOWLEDGE_DB':str(Path('memory.db').resolve()),'SUPERHUMAN_IDENTITY_DIR':str(Path('identity').resolve()),'SUPERHUMAN_MAIL_KEY_FILE':str(Path('mail.key').resolve())});self.env.start()
    def tearDown(self):self.env.stop();os.chdir(self.old);self.tmp.cleanup()
    def runid(self,allowed=('calculate',),required=(),calls=8,steps=12):return store.create('marketing','Bounded task','Calculate and prepare a checked result.',allowed,required,calls,steps)
    def step(self,pid,value):return p.run_one(pid,client=Client(value))
    def state(self,pid):return store.get(pid)['state']
    def approve(self,pid):store.control(pid,store.get(pid)['version'],'approve_action')
    def finish(self,pid):
        evidence=[a['id'] for a in store.get(pid)['actions'] if a['status'] in ('succeeded','cached')]
        return self.step(pid,decision(action='finish',evidence=evidence))
    def test_calculate_finish_uses_canonical_budget_and_review(self):
        pid=self.runid(required=('calculate',));self.step(pid,decision());result=self.finish(pid)
        self.assertEqual(self.state(pid),'completed');self.assertEqual(result['status'],'needs_review');self.assertEqual(p.get(pid)['used_calls'],2)
        self.assertIn('Execution evidence',p._text(json.loads(result['result_json']))[1])
    def test_permission_approval_executes_exact_action_without_new_decision(self):
        pid=self.runid();self.step(pid,decision('document.export',{'title':'Report','format':'docx','text':'Reviewed evidence.'}))
        self.assertEqual(self.state(pid),'awaiting_permission');self.assertEqual(__import__('superhuman.departments.store',fromlist=['materials']).materials('marketing')[1],[])
        self.approve(pid);fake=Client();p.run_one(pid,client=fake)
        self.assertEqual(fake.calls,0);self.assertEqual(p.get(pid)['used_calls'],1);self.assertEqual(store.get(pid)['actions'][0]['status'],'succeeded')
    def test_source_read_exports_exact_saved_text_and_artifact_integrity(self):
        local.store_bytes('marketing','evidence.txt',b'Original evidence: five findings.');pid=self.runid(('workspace.read','document.export'),('document.export',))
        self.step(pid,decision('workspace.read',{'filename':'evidence.txt'}));aid=store.get(pid)['actions'][0]['id']
        self.step(pid,decision('document.export',{'title':'Evidence','format':'docx','source_action':aid}));a=store.get(pid)['actions'][-1];data=json.loads(a['result_json']);file,_=exports.artifact('marketing',data['export_id'])
        from docx import Document
        self.assertIn('Original evidence: five findings.','\n'.join(t.text for t in Document(file).paragraphs));self.finish(pid);self.assertEqual(self.state(pid),'completed')
    def test_duplicate_output_is_cached_without_second_file(self):
        pid=self.runid(('document.export',));d=decision('document.export',{'title':'Report','format':'docx','text':'A checked draft.'})
        self.step(pid,d);self.step(pid,d);self.assertEqual(store.get(pid)['actions'][-1]['status'],'cached');self.assertEqual(len(__import__('superhuman.departments.store',fromlist=['materials']).materials('marketing')[1]),1)
    def test_dynamic_source_reads_are_fresh(self):
        local.store_bytes('marketing','source.txt',b'Before');pid=self.runid(('workspace.read',));d=decision('workspace.read',{'filename':'source.txt'})
        self.step(pid,d);local.file_for('marketing','source.txt').write_bytes(b'After');self.step(pid,d)
        self.assertEqual(json.loads(store.get(pid)['actions'][-1]['result_json'])['text'],'After')
    def test_changed_export_prevents_finish(self):
        pid=self.runid(('document.export',));self.step(pid,decision('document.export',{'title':'Report','format':'docx','text':'Actual result'}));data=json.loads(store.get(pid)['actions'][0]['result_json']);file,_=exports.artifact('marketing',data['export_id']);file.write_bytes(b'Changed')
        self.finish(pid);self.assertNotEqual(self.state(pid),'completed');self.assertEqual(store.get(pid)['actions'][-1]['status'],'failed')
    def test_required_tool_cannot_be_skipped(self):
        pid=self.runid(('calculate','document.export'),('document.export',));self.step(pid,decision());self.finish(pid);self.assertNotEqual(self.state(pid),'completed')
    def test_invalid_args_corrected_within_loop(self):
        pid=self.runid();self.step(pid,decision(arguments={'expression':'2+3','scope':'career_rnd'}));self.assertEqual(self.state(pid),'ready');self.step(pid,decision());self.finish(pid);self.assertEqual(self.state(pid),'completed')
    def test_two_invalid_actions_stop_for_owner(self):
        pid=self.runid();self.step(pid,decision('unknown'));self.step(pid,decision('unknown'));self.assertEqual(self.state(pid),'needs_review');self.assertEqual(scheduler.order([pid],p.DEFAULT_DB),[])
    def test_step_cap_stops_even_when_model_repeats_success(self):
        pid=self.runid(steps=2);self.step(pid,decision());self.step(pid,decision());fake=Client();p.run_one(pid,client=fake);self.assertEqual(self.state(pid),'step_limit');self.assertEqual(fake.calls,0)
    def test_paid_tool_budget_waits_before_execution_and_reuses_prepared_action(self):
        pid=self.runid(('draft.create',),calls=1);self.step(pid,decision('draft.create',{'title':'Report','instructions':'Draft'}));self.assertEqual(self.state(pid),'budget_blocked');self.assertEqual(p.get(pid)['used_calls'],1)
        p.budget(pid,5);fake=Client()
        with patch('superhuman.agentic.tools.execute',return_value=tools.outcome({'text':'Draft'})) as execute:p.run_one(pid,client=fake)
        self.assertEqual(fake.calls,0);execute.assert_called_once();self.assertEqual(self.state(pid),'ready')
    def test_decision_request_failure_never_replays(self):
        pid=self.runid();self.step(pid,RuntimeError('Uncertain'));self.assertEqual(self.state(pid),'interrupted');self.assertEqual(p.get(pid)['used_calls'],1);self.assertIsNone(p.run_one(pid,client=Client()))
        with self.assertRaises(ValueError):store.control(pid,store.get(pid)['version'],'resume')
    def test_uncertain_write_requires_new_exact_approval_after_resume(self):
        pid=self.runid(('document.export',));d=decision('document.export',{'title':'Report','format':'docx','text':'Content'})
        with patch('superhuman.agentic.tools.execute',side_effect=OSError('Disk uncertain')):self.step(pid,d)
        self.assertEqual(self.state(pid),'interrupted');store.control(pid,store.get(pid)['version'],'resume','Inspected existing files; continue');self.step(pid,d);self.assertEqual(self.state(pid),'awaiting_permission')
    def test_worker_restart_marks_inflight_no_replay(self):
        pid=self.runid();store.initialize()
        with p.connect() as db:
            db.execute("UPDATE agentic_runs SET state='running' WHERE project_id=?",(pid,));db.execute("INSERT INTO agentic_actions(id,project_id,ordinal,status,created_at) VALUES('test',?,1,'executing','now')",(pid,))
        self.assertEqual(store.recover(),1);self.assertEqual(self.state(pid),'interrupted');self.assertEqual(store.get(pid)['actions'][0]['status'],'interrupted');self.assertEqual(store.recover(),0)
    def test_pause_resume_and_stale_controls(self):
        pid=self.runid();version=store.get(pid)['version'];store.control(pid,version,'pause');self.assertEqual(scheduler.order([pid],p.DEFAULT_DB),[])
        with self.assertRaises(ValueError):store.control(pid,version,'resume')
        store.control(pid,store.get(pid)['version'],'resume');self.assertEqual(scheduler.order([pid],p.DEFAULT_DB),[pid])
    def test_cancel_prevents_next_paid_step(self):
        pid=self.runid();store.control(pid,store.get(pid)['version'],'cancel');self.assertEqual(p.get(pid)['status'],'cancelled');self.assertIsNone(p.run_one(pid,client=Client()))
    def test_legacy_retry_cannot_bypass_run_state(self):
        pid=self.runid();self.step(pid,RuntimeError('Uncertain'))
        with self.assertRaisesRegex(ValueError,'Agent runs'):p.retry(pid,'final','Retry')
    def test_rollback_quarantine_survives_and_can_resume_after_reinstall(self):
        pid=self.runid();store.quarantine_for_rollback();self.assertTrue(jobs.worker_status()['paused']);self.assertEqual(p.get(pid)['tasks'][0]['status'],'agentic_unavailable');self.assertEqual(p.get(pid)['status'],'dependency_blocked')
        store.control(pid,store.get(pid)['version'],'resume');self.assertEqual(p.get(pid)['tasks'][0]['status'],'pending')
    def test_read_cannot_escape_department_or_paths(self):
        local.store_bytes('career_rnd','other.txt',b'Other department');pid=self.runid(('workspace.read',));self.step(pid,decision('workspace.read',{'filename':'../career_rnd/other.txt'}));self.assertEqual(store.get(pid)['actions'][0]['status'],'failed')
    def test_test_runner_unavailable_is_failed_and_cannot_finish(self):
        sid=coding.create('marketing','Code',{'test_example.py':'import unittest\n'})['id'];pid=self.runid(('coding.tests',),('coding.tests',))
        with patch('superhuman.capabilities.coding.run_tests',return_value={'status':'unavailable'}):self.step(pid,decision('coding.tests',{'session_id':sid,'module':'test_example'}))
        self.assertEqual(store.get(pid)['actions'][0]['status'],'failed');self.finish(pid);self.assertNotEqual(self.state(pid),'completed')
    def test_syntax_evidence_invalidated_by_later_edit(self):
        sid=coding.create('marketing','Code',{'main.py':'x=1\n'})['id'];pid=self.runid(('coding.syntax',));self.step(pid,decision('coding.syntax',{'session_id':sid}));a=store.get(pid)['actions'][0];old=coding.read('marketing',sid,'main.py');coding.edit('marketing',sid,'main.py','x=2\n',old['sha256'],'Change')
        with self.assertRaises(ValueError):tools.verify_saved(a,'marketing')
    def test_unknown_tools_duplicate_json_and_unapproved_scope_rejected(self):
        with self.assertRaises(ValueError):engine.parse('{"action":"tool","action":"finish"}')
        with self.assertRaises(ValueError):tools.validate('shell',{'command':'ls'})
        with self.assertRaises(ValueError):self.runid(('nonexistent',))
        with self.assertRaises(ValueError):self.runid(('calculate',),('coding.tests',))
    def test_workspace_search_profile_and_project_listing_real_adapters(self):
        local.store_bytes('marketing','numbers.csv',b'amount\n2\n3\n');pid=self.runid(('workspace.list','workspace.search','table.profile','projects.list'))
        for name,args in [('workspace.list',{}),('workspace.search',{'query':'amount'}),('table.profile',{'filename':'numbers.csv'}),('projects.list',{})]:self.step(pid,decision(name,args))
        self.assertTrue(all(a['status']=='succeeded' for a in store.get(pid)['actions']))
    def test_web_login_csrf_setup_tasks_and_action_controls(self):
        settings=config.Settings('https://superhuman.example',state_dir=Path('state'));auth.Store(settings.auth_db).setup('owner','synthetic-test-passphrase')
        with TestClient(web.create_app(settings),base_url=settings.public_origin) as c:
            self.assertEqual(c.get('/agent-runs',follow_redirects=False).status_code,303)
            csrf=lambda page:re.search(r'name="csrf" value="([^"]+)"',page.text).group(1)
            c.post('/login',data={'csrf':csrf(c.get('/login')),'username':'owner','password':'synthetic-test-passphrase'})
            data={'scope':'marketing','title':'Agent test','instruction':'Calculate 2+3','permissions':['read_workspace'],'max_calls':4,'max_actions':4}
            self.assertEqual(c.post('/agent-runs',data=data).status_code,403);data['csrf']=csrf(c.get('/agent-runs'));response=c.post('/agent-runs',data=data,follow_redirects=False);self.assertEqual(response.status_code,303)
            detail=c.get(response.headers['location']);self.assertIn('Ready for next step',detail.text);self.assertIn(response.headers['location'],c.get('/tasks').text)
            pid=response.headers['location'].split('/')[-1];self.step(pid,decision('document.export',{'title':'Output','format':'docx','text':'Report'}));detail=c.get('/agent-runs/'+pid);self.assertIn('Prepared action needs permission',detail.text);self.assertIn('/agent-runs/'+pid,c.get('/attention').text)
            self.assertEqual(c.post('/agent-runs/'+pid+'/control',data={'version':store.get(pid)['version'],'action':'approve_action'}).status_code,403)

    def test_actual_draft_adapter_accounts_for_all_three_requests(self):
        from test_memory_generation import Client as DraftClient
        inner=DraftClient()
        class Routed(Client):
            def create(self,**kw):
                if kw.get('response_format',{}).get('json_schema',{}).get('name')=='superhuman_agent_action':return super().create(**kw)
                return inner.create(**kw)
        pid=self.runid(('draft.create',),('draft.create',),calls=6)
        client=Routed(decision('draft.create',{'title':'University discovery agenda','instructions':'Prepare a short agenda.'}))
        p.run_one(pid,client=client);self.assertEqual(p.get(pid)['used_calls'],4);self.assertEqual(len(inner.calls),3);self.assertEqual(store.get(pid)['actions'][0]['status'],'succeeded')
        self.finish(pid);self.assertEqual(self.state(pid),'completed')
    def test_research_adapter_uses_cited_response_and_shared_budget(self):
        from test_memory_generation import Client as ResearchClient
        fake=Client(decision('research.web',{'title':'University research','query':'Find current discovery guidance'}));fake.responses=ResearchClient().responses
        pid=self.runid(('research.web',),('research.web',));p.run_one(pid,client=fake)
        self.assertEqual(p.get(pid)['used_calls'],2);self.assertEqual(store.get(pid)['actions'][0]['status'],'succeeded');self.finish(pid);self.assertEqual(self.state(pid),'completed')
    def test_exhausted_decision_budget_is_visible_and_can_be_raised(self):
        pid=self.runid(calls=1);self.step(pid,decision());p.run_one(pid,client=Client());self.assertEqual(self.state(pid),'budget_blocked')
        p.budget(pid,3);self.finish(pid);self.assertEqual(self.state(pid),'completed')
    def test_different_department_inbox_is_rejected(self):
        from superhuman.mail import store as mail
        mail.initialize();slot=next(iter(mail.SLOTS))
        with p.connect() as db:db.execute("UPDATE mail_accounts SET scope='career_rnd' WHERE id=?",(slot,))
        pid=self.runid(('inbox.cached',));self.step(pid,decision('inbox.cached',{'slot':slot}));self.assertEqual(store.get(pid)['actions'][0]['status'],'failed')
    def test_memory_tool_proposes_without_confirming(self):
        from superhuman.knowledge.store import Store
        pid=self.runid(('memory.propose',));self.step(pid,decision('memory.propose',{'title':'Learning','content':'A proposed conclusion from this task.'}));a=store.get(pid)['actions'][0]
        self.assertEqual(a['status'],'succeeded');self.assertEqual(json.loads(a['result_json'])['status'],'proposed')
    def test_coding_edit_and_package_use_isolated_copy_and_download(self):
        sid=coding.create('marketing','Code',{'main.py':'x=1\n'})['id'];pid=self.runid(('coding.edit','coding.package'))
        old=coding.read('marketing',sid,'main.py');self.step(pid,decision('coding.edit',{'session_id':sid,'filename':'main.py','text':'x=2\n','expected_hash':old['sha256'],'note':'Update constant'}));self.assertEqual(store.get(pid)['actions'][-1]['status'],'succeeded')
        folder,_=coding.session('marketing',sid);self.assertEqual((folder/'original/main.py').read_text(),'x=1\n');self.step(pid,decision('coding.package',{'session_id':sid}));a=store.get(pid)['actions'][-1];tools.verify_saved(a,'marketing');self.assertIn('/agent-runs/'+pid,json.loads(a['result_json'])['download_url'])

    def test_resume_correction_note_reaches_next_decision(self):
        pid=self.runid();self.step(pid,decision('unknown'));self.step(pid,decision('unknown'));store.control(pid,store.get(pid)['version'],'resume','Use calculate, then give the total.')
        messages,_=engine.prompt(store.get(pid));self.assertIn('Use calculate, then give the total.',messages[1]['content'])
    def test_runtime_tick_runs_one_step_and_records_progress(self):
        from superhuman.runtime import engine as runtime
        pid=self.runid();result=runtime.tick(client=Client(decision()))
        self.assertEqual(result['project_id'],pid);self.assertEqual(result['status'],'pending');self.assertEqual(self.state(pid),'ready')
        with p.connect() as db:self.assertEqual(db.execute("SELECT action FROM runtime_events WHERE project_id=? ORDER BY seq DESC LIMIT 1",(pid,)).fetchone()[0],'agent_step')
    def test_cancel_arriving_during_step_wins_after_tool_execution(self):
        pid=self.runid()
        def cancelling(*args,**kwargs):
            store.control(pid,store.get(pid)['version'],'cancel');return tools.outcome({'value':5})
        with patch('superhuman.agentic.tools.execute',side_effect=cancelling):self.step(pid,decision())
        self.assertEqual(self.state(pid),'cancelled');self.assertEqual(p.get(pid)['status'],'cancelled')
    def test_pause_arriving_during_decision_holds_prepared_action(self):
        pid=self.runid()
        def pausing():
            store.control(pid,store.get(pid)['version'],'pause');return decision()
        self.step(pid,pausing);self.assertEqual(self.state(pid),'paused');self.assertEqual(store.get(pid)['actions'][0]['status'],'approved')
        store.control(pid,store.get(pid)['version'],'resume');fake=Client();p.run_one(pid,client=fake);self.assertEqual(fake.calls,0);self.assertEqual(store.get(pid)['actions'][0]['status'],'succeeded')

    def test_rejected_deliverable_can_continue_only_with_owner_correction(self):
        pid=self.runid();self.step(pid,decision());self.finish(pid);p.review(pid,'final','reject','Explain the calculation')
        with self.assertRaises(ValueError):store.control(pid,store.get(pid)['version'],'resume')
        store.control(pid,store.get(pid)['version'],'resume','Explain the calculation with its arithmetic.');self.assertEqual(self.state(pid),'ready');self.finish(pid);self.assertEqual(p.get(pid)['status'],'needs_review')
    def test_approved_deliverable_cannot_be_resumed(self):
        pid=self.runid();self.step(pid,decision());self.finish(pid);p.review(pid,'final','approve','Reviewed')
        with self.assertRaises(ValueError):store.control(pid,store.get(pid)['version'],'resume','Redo')
    def test_package_is_invalidated_when_working_copy_changes(self):
        sid=coding.create('marketing','Code',{'main.py':'x=1\n'})['id'];pid=self.runid(('coding.package',));self.step(pid,decision('coding.package',{'session_id':sid}));a=store.get(pid)['actions'][0];old=coding.read('marketing',sid,'main.py');coding.edit('marketing',sid,'main.py','x=2\n',old['sha256'],'Update')
        with self.assertRaises(ValueError):tools.verify_saved(a,'marketing')

    def test_rollback_quarantines_finished_review_and_restores_it_without_work(self):
        pid=self.runid();self.step(pid,decision());self.finish(pid);used=p.get(pid)['used_calls'];store.quarantine_for_rollback()
        self.assertEqual(p.get(pid)['tasks'][0]['status'],'agentic_unavailable');self.assertEqual(p.get(pid)['status'],'dependency_blocked')
        store.recover();self.assertEqual(p.get(pid)['tasks'][0]['status'],'needs_review');self.assertEqual(p.get(pid)['used_calls'],used);self.assertEqual(self.state(pid),'completed')

    def test_cancellation_between_claim_and_run_update_keeps_cancelled_task(self):
        pid=self.runid();claim=p.claim
        def cancel_after_claim(*args,**kwargs):
            task=claim(*args,**kwargs);store.control(pid,store.get(pid)['version'],'cancel');return task
        with patch('superhuman.projects.engine.claim',side_effect=cancel_after_claim):self.step(pid,decision())
        self.assertEqual(self.state(pid),'cancelled');self.assertEqual(p.get(pid)['tasks'][0]['status'],'cancelled');self.assertEqual(p.get(pid)['used_calls'],0)
