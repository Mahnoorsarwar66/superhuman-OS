"""Cross-feature reliability repairs and regression cases from the code review."""
import json,os,re,sqlite3,tempfile,time
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
import unittest
from fastapi.testclient import TestClient
from superhuman.hosted import web,config,auth,jobs
from superhuman.projects import engine as p
from superhuman.runtime import engine as r
from superhuman.planning import store,priority
from superhuman.repairs import recovery,scheduler,deadlines,checks,actions
from superhuman.repairs.web import token

class RepairTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=Path.cwd();os.chdir(self.temp.name)
        self.env=patch.dict(os.environ,{'SUPERHUMAN_PLANNING_DB':str(Path('plans.db').resolve()),'SUPERHUMAN_KNOWLEDGE_DB':str(Path('notes.db').resolve()),'SUPERHUMAN_IDENTITY_DIR':str(Path('identity').resolve()),'SUPERHUMAN_MEMORY_PATH':str(Path('memory.json').resolve()),'SUPERHUMAN_MAIL_KEY_FILE':str(Path('mail.key').resolve())});self.env.start()
        settings=config.Settings('https://superhuman.example',state_dir=Path('state'));auth.Store(settings.auth_db).setup('owner','synthetic-test-passphrase');self.client=TestClient(web.create_app(settings),base_url=settings.public_origin)
    def tearDown(self):self.client.close();self.env.stop();os.chdir(self.old);self.temp.cleanup()
    def csrf(self,response):return re.search(r'name="csrf" value="([^"]+)"',response.text).group(1)
    def login(self):self.client.post('/login',data={'csrf':self.csrf(self.client.get('/login')),'username':'owner','password':'synthetic-test-passphrase'},follow_redirects=False)
    def goal(self,scope='marketing',rank='high',due='2020-01-01',status='active',note=''):
        return store.save_goal(scope,store.snapshot(scope)['goal']['version'],'Campaign goal',rank,due,'Approved result',goal_status=status,completion_note=note)
    def milestone(self,title='Evidence',deps=(),scope='marketing',due='2020-01-01',projects=()):
        return store.save_milestone(scope,uuid4().hex,0,title,due,'Reviewed','planned',project_ids=projects,depends_on=deps)
    def test_restart_marks_running_tasks_and_plans_without_replaying(self):
        pid=r.enqueue('collab','marketing','Interrupted task','Draft');plan=p.create('career_rnd','Interrupted plan','',12);jobs.initialize()
        with p.connect() as db:
            db.execute("UPDATE project_tasks SET status='running',started=? WHERE project_id=?",(time.time(),pid))
            db.execute("UPDATE projects SET status='planning' WHERE id=?",(plan,))
            db.execute("INSERT INTO hosted_plans VALUES(?,'running','old',?,NULL)",(plan,time.time()))
        result=recovery.recover(p.DEFAULT_DB);self.assertEqual(result,{'tasks':1,'plans':1});self.assertEqual(p.get(pid)['tasks'][0]['status'],'interrupted');self.assertEqual(p.get(plan)['status'],'plan_failed')
        self.assertEqual(p.get(pid)['used_calls'],0)
    def test_runtime_uses_priority_and_existing_order_for_ties(self):
        low=r.enqueue('collab','marketing','Low','Draft');high=r.enqueue('collab','career_rnd','High','Draft');self.goal('marketing','low');self.goal('career_rnd','critical')
        self.assertEqual(scheduler.order([low,high],p.DEFAULT_DB),[high,low])
        with patch('superhuman.projects.engine.run_one',return_value={'id':'test','status':'needs_review','output':None}) as run:
            result=r.tick();self.assertEqual(result['project_id'],high);self.assertEqual(run.call_args.args[0],high)
    def test_linked_dependencies_and_holds_gate_scheduling(self):
        pid=r.enqueue('collab','marketing','Linked project','Draft');a=self.milestone('Prerequisite');self.milestone('Dependent',[a['id']],projects=[pid]);self.goal()
        self.assertEqual(scheduler.order([pid],p.DEFAULT_DB),[])
        store.save_milestone('marketing',a['id'],1,'Prerequisite','2020-01-01','Reviewed','complete','Approved')
        self.assertEqual(scheduler.order([pid],p.DEFAULT_DB),[pid])
        self.goal(status='on_hold');self.assertEqual(scheduler.order([pid],p.DEFAULT_DB),[])
    def test_queued_project_plans_use_department_priorities(self):
        a=p.create('marketing','Low plan','',12);b=p.create('career_rnd','High plan','',12);self.goal('marketing','low');self.goal('career_rnd','critical');jobs.request_plan(a);jobs.request_plan(b)
        with patch('superhuman.projects.engine.generate_plan') as generate:
            result=jobs.run_plan();self.assertEqual(result['project_id'],b);self.assertEqual(generate.call_args.args[0],b)
    def test_reviews_and_prerequisites_precede_waiting_milestone(self):
        self.goal();a=self.milestone('Prerequisite',due='2099-01-01');self.milestone('Blocked submission',[a['id']],due='2020-01-01')
        self.assertEqual(priority.actions('marketing')[0]['title'],'Prerequisite')
        fallback=('Review the completed draft: Result','/projects/example')
        self.assertEqual(priority.next_step('marketing',fallback),fallback)
    def test_goal_completion_clears_deadlines_and_is_audited(self):
        self.goal();self.assertTrue(deadlines.items());closed=self.goal(status='complete',note='All evidence reviewed')
        self.assertEqual(closed['status'],'complete');self.assertEqual(deadlines.items(),[])
        self.assertEqual(json.loads(store.history('marketing')[0]['after_json'])['status'],'complete')
        self.goal(status='active');self.assertTrue(deadlines.items())
    def test_cannot_complete_goal_with_open_milestones_or_blockers(self):
        self.goal();self.milestone()
        with self.assertRaises(ValueError):self.goal(status='complete',note='Done')
    def test_department_plan_sources_and_memory_enter_working_context(self):
        self.goal();from superhuman.capabilities import local
        local.store_bytes('marketing','campaign_evidence.txt',b'Campaign evidence includes university outreach conversion results.')
        from superhuman.knowledge.store import Store
        Store().add('marketing','preference','Writing preference','Use clear campaign language.',status='confirmed')
        from superhuman.identity.selection import select_context
        selected=select_context('marketing','Campaign evidence','Prepare campaign evidence')
        self.assertIn('Campaign goal',selected['references']);self.assertIn('campaign_evidence.txt',selected['references']);self.assertIn('Use clear campaign language',selected['preferences'])
        self.assertLessEqual(len(selected['references']),7000)
        kinds={x['kind'] for x in selected['trace']['selected']};self.assertIn('department_plan',kinds);self.assertIn('automatic_file',kinds)
    def test_context_never_reads_other_department_files(self):
        from superhuman.capabilities import local
        local.store_bytes('career_rnd','campaign_other.txt',b'PRIVATE_OTHER_DEPARTMENT_CAMPAIGN')
        from superhuman.identity.selection import select_context
        result=select_context('marketing','Campaign','Campaign')
        self.assertNotIn('PRIVATE_OTHER_DEPARTMENT_CAMPAIGN',result['references'])
    def test_health_reports_actual_release(self):self.assertEqual(self.client.get('/healthz').json()['version'],'1.36.0')
    def test_tasks_unify_statuses_and_retry_requires_csrf_and_current_state(self):
        self.login();pid=r.enqueue('collab','marketing','Failed campaign task','Draft')
        with p.connect() as db:db.execute("UPDATE project_tasks SET status='interrupted' WHERE project_id=?",(pid,))
        task=p.get(pid)['tasks'][0];page=self.client.get('/tasks');self.assertIn('Failed campaign task',page.text);self.assertIn('Authorize a retry',page.text)
        path='/repair-tasks/'+pid+'/'+task['id']+'/retry';data={'expected':token(task),'note':'Retry after review'}
        self.assertEqual(self.client.post(path,data=data).status_code,403)
        data['csrf']=self.csrf(page);self.assertEqual(self.client.post(path,data=data,follow_redirects=False).status_code,303);self.assertEqual(p.get(pid)['tasks'][0]['status'],'pending')
        self.assertEqual(self.client.post(path,data=data).status_code,409)
    def test_tasks_department_filter_and_status_filter(self):
        self.login();r.enqueue('collab','marketing','Visible campaign','Draft');r.enqueue('collab','career_rnd','Other department task','Draft')
        out=self.client.get('/tasks?department=marketing&task_status=pending');self.assertIn('Visible campaign',out.text);self.assertNotIn('Other department task',out.text)
    def test_calendar_and_attention_show_deadlines_with_ics(self):
        self.goal();self.login()
        self.assertIn('Campaign goal',self.client.get('/calendar').text);self.assertIn('Campaign goal',self.client.get('/attention').text)
        feed=self.client.get('/planning-deadlines.ics');self.assertIn('BEGIN:VEVENT',feed.text);self.assertIn('BEGIN:VALARM',feed.text);self.assertIn('DTSTART;VALUE=DATE:20200101',feed.text)
    def test_ics_folds_unicode_and_escapes_newlines(self):
        store.save_goal('marketing',0,'Unicode café '*25+'\nFake: value','high','2026-11-01','')
        text=deadlines.ics();self.assertTrue(all(len(line.encode())<=75 for line in text.split('\r\n')));self.assertIn('\\nFake',text)
    def test_milestone_progress_flags_review_without_auto_completion(self):
        self.goal();pid=p.create('marketing','Approved project','',12)
        with p.connect() as db:db.execute("UPDATE projects SET status='approved' WHERE id=?",(pid,))
        m=self.milestone(projects=[pid]);progress=actions.milestone_progress('marketing');self.assertTrue(progress[m['id']]['ready_for_review']);self.assertEqual(store.snapshot('marketing')['milestones'][0]['status'],'planned')
    def test_system_checks_find_bad_outputs_without_showing_secrets(self):
        self.login();pid=r.enqueue('collab','marketing','Bad artifact','Draft')
        with p.connect() as db:db.execute('UPDATE project_tasks SET result_json=? WHERE project_id=?',(json.dumps({'output':'missing-output.txt'}),pid))
        data=checks.report();self.assertEqual(len(data['artifacts']['problems']),1);self.assertEqual(data['model_requests'],0)
        self.assertEqual(self.client.get('/system-checks').status_code,200);self.assertEqual(self.client.get('/system-checks.json').status_code,200)
    def test_explicit_request_limit_change_and_stale_guard(self):
        self.login();pid=r.enqueue('collab','marketing','Budget task','Draft')
        with p.connect() as db:db.execute("UPDATE projects SET status='budget_blocked' WHERE id=?",(pid,))
        project=p.get(pid);page=self.client.get('/tasks');expected=str(project['used_calls'])+':'+str(project['max_calls'])
        self.assertIn('Authorize updated request limit',page.text)
        path='/repair-projects/'+pid+'/budget';data={'csrf':self.csrf(page),'expected':expected,'maximum':10}
        self.assertEqual(self.client.post(path,data=data,follow_redirects=False).status_code,303)
        self.assertEqual(p.get(pid)['max_calls'],10);self.assertEqual(p.get(pid)['used_calls'],0)
        self.assertEqual(self.client.post(path,data=data).status_code,409)
    def test_inbox_probe_queue_uses_existing_read_only_sync(self):
        with patch('superhuman.mail.store.accounts',return_value=[{'id':'edsync_titan','connected':True},{'id':'personal_gmail','connected':False}]),patch('superhuman.mail.store.queue_sync') as sync:
            queued=checks.queue_inboxes();sync.assert_called_once_with('edsync_titan');self.assertEqual(len(queued),1)
    def test_context_includes_relevant_saved_source_card(self):
        from superhuman.researchdesk import store as research
        area=research.create('Campaign evidence','marketing','Campaign questions','Hypothesis','a'*32)
        values={k:'' for k,_,_ in research.FIELDS};values.update(title='Campaign evidence',synopsis='Campaign conversion evidence from a university pilot',url='https://example.org/evidence',must_read=False,read_state='unread')
        research.save_source(area,values,submission_key='b'*32)
        from superhuman.identity.selection import select_context
        context=select_context('marketing','Campaign evidence','Campaign conversion')
        self.assertIn('university pilot',context['references'])
        self.assertIn('research_card',{x['kind'] for x in context['trace']['selected']})
    def test_export_integrity_is_checked_on_real_generated_file(self):
        from superhuman.capabilities import exports
        record=exports.generate('marketing','docx','Campaign document','Actual exported text')
        good=checks.report();self.assertEqual(good['exports']['checked'],1);self.assertEqual(good['exports']['problems'],[])
        path,_=exports.artifact('marketing',record['export_id']);path.write_bytes(b'changed')
        self.assertEqual(len(checks.report()['exports']['problems']),1)

    def test_held_pending_tasks_are_visible_in_blocked_view(self):
        self.login();r.enqueue('collab','marketing','Held campaign task','Draft');self.goal(status='on_hold')
        out=self.client.get('/tasks?task_status=blocked')
        self.assertIn('Held campaign task',out.text);self.assertIn('Inspect the department plan',out.text)
    def test_closed_goal_cannot_gain_new_open_milestones_or_inputs(self):
        self.goal(status='complete',note='Owner confirmed complete')
        with self.assertRaises(ValueError):self.milestone()
        with self.assertRaises(ValueError):store.save_blocker('marketing',uuid4().hex,0,'New input','','','open')

    def test_new_surfaces_remain_private(self):
        for path in ('/tasks','/attention','/system-checks','/system-checks.json','/planning-deadlines.ics'):
            self.assertEqual(self.client.get(path,follow_redirects=False).status_code,303)

if __name__=='__main__':unittest.main()
