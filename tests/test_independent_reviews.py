"""Real separate reviewer execution, defect revisions and acceptance boundaries."""
import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import test_workforce_objectives as fixtures
from superhuman.projects import engine as p, revisions as local_revisions
from superhuman.team import store, work, objectives, reviews, workplans
from superhuman.agentic import store as agent, tools, engine as action_engine


class IndependentReviewTests(unittest.TestCase):
    tearDown=fixtures.ObjectiveTests.tearDown
    objective=fixtures.ObjectiveTests.objective
    ready=fixtures.ObjectiveTests.ready
    finish=fixtures.ObjectiveTests.finish
    reserve=fixtures.ObjectiveTests.reserve

    def setUp(self):
        fixtures.ObjectiveTests.setUp(self)
        self.oid=self.objective(revisions=3)
        self.rid=self.finish()
        self.rubric=['Evidence supports the stated result.','Limitations are disclosed.']

    def assign(self, reviewer='career_rnd'):
        return reviews.assign(self.task,store.task(self.task)['version'],reviewer,self.rubric)

    def accept(self, tid=None, approve=True):
        tid=tid or self.task
        return work.review(tid,store.task(tid)['version'],approve,'Owner inspected saved artifact and findings',actor='owner')

    def report(self, tid, revise=False):
        entry=reviews.history(tid)[0]
        report=dict(fingerprint=entry['fingerprint'],scores=[dict(criterion=c,verdict='revise' if revise and i==0 else 'pass',rationale='Independent fixture assessment of the quoted evidence.') for i,c in enumerate(self.rubric)],defects=[])
        if revise:
            report['defects']=[dict(criterion=self.rubric[0],severity='material',quote=entry['source_text'].strip(),problem='The answer does not state the actual calculated total.',correction='State the verified total five explicitly.')]
        return report

    def execute_review(self, tid, report=None):
        self.ready(tid)
        rid=work.dispatch(tid,store.task(tid)['version'])
        read=fixtures.decision();read.update(tool='workforce.review_source',arguments_json='{}')
        p.run_one(rid,client=fixtures.Client(read))
        run=agent.get(rid)
        self.assertEqual(run['actions'][0]['status'],'succeeded',run)
        final=fixtures.decision(True,[run['actions'][0]['id']]);final['final_message']=json.dumps(report or self.report(tid))
        p.run_one(rid,client=fixtures.Client(final))
        work.refresh()
        self.assertEqual(store.task(tid)['state'],'awaiting_review',agent.get(rid))
        return rid

    def completed_review(self, revise=False, reviewer='career_rnd'):
        tid=self.assign(reviewer)
        self.execute_review(tid,self.report(tid,revise))
        self.accept(tid)
        return tid

    def revise_and_finish(self):
        self.accept(approve=False)
        self.ready()
        p.run_one(self.rid,client=fixtures.Client(fixtures.decision()))
        aid=agent.get(self.rid)['actions'][-1]['id']
        final=fixtures.decision(True,[aid]);final['final_message']='The verified total is five. This is a synthetic arithmetic result.'
        p.run_one(self.rid,client=fixtures.Client(final));work.refresh()
        self.assertEqual(store.task(self.task)['state'],'awaiting_review')

    def test_separate_task_run_and_shared_accounting(self):
        before=objectives.get(self.oid)
        tid=self.assign()
        self.assertNotEqual(tid,self.task)
        self.assertEqual(objectives.memberships()[tid],self.oid)
        rid=self.execute_review(tid)
        self.assertNotEqual(rid,self.rid)
        run=agent.get(rid)
        self.assertEqual(run['allowed_tools'],['workforce.review_source'])
        self.assertEqual(run['required_tools'],['workforce.review_source'])
        self.assertEqual(objectives.get(self.oid)['usage']['requests'],before['usage']['requests']+2)
        self.assertEqual(objectives.get(self.oid)['deadline'],before['deadline'])
        self.accept(tid);self.accept()
        objectives.control(self.oid,objectives.get(self.oid)['version'],'complete','Success criteria and required review satisfied')
        self.assertEqual(objectives.get(self.oid)['state'],'completed')

    def test_pending_review_blocks_both_owner_and_project_approval(self):
        self.assign()
        for approve in (lambda:self.accept(),lambda:p.review(self.rid,'final','approve','Attempt alternative route')):
            with self.assertRaisesRegex(ValueError,'pending|unresolved'):approve()
        self.assertEqual(store.task(self.task)['state'],'awaiting_review')

    def test_author_cannot_review_own_work(self):
        with self.assertRaisesRegex(ValueError,'independent'):self.assign('marketing')
        self.assertEqual(len(objectives.get(self.oid)['tasks']),1)

    def test_unassigned_run_cannot_read_another_artifact(self):
        with self.assertRaisesRegex(ValueError,'no independent'):reviews.read_source(agent.get(self.rid))

    def test_owner_permission_is_required_and_revocation_blocks_dispatch(self):
        tid=self.assign()
        e=next(e for e in store.employees() if e['id']=='career_rnd')
        store.employee_control(e['id'],e['version'],False,e['charter'],[t for t in json.loads(e['allowed_tools']) if t!='workforce.review_source'])
        self.ready(tid)
        with self.assertRaisesRegex(ValueError,'permission'):work.dispatch(tid,store.task(tid)['version'])

    def test_duplicate_assignment_does_not_create_extra_task(self):
        self.assign()
        with self.assertRaisesRegex(ValueError,'already'):self.assign()
        self.assertEqual(len(objectives.get(self.oid)['tasks']),2)

    def test_reviewer_gets_exact_saved_evidence_and_complete_brief(self):
        tid=self.assign();self.ready(tid)
        rid=work.dispatch(tid,store.task(tid)['version'])
        saved=reviews.read_source(agent.get(rid))
        self.assertEqual(saved['brief'],store.task(self.task)['instruction'])
        self.assertEqual(saved['rubric'],self.rubric)
        self.assertEqual(saved['evidence'][0]['tool'],'calculate')
        self.assertEqual(json.loads(saved['evidence'][0]['result_json'])['result'],'5')

    def test_source_evidence_mutation_invalidates_review_before_paid_call(self):
        tid=self.assign();self.ready(tid)
        rid=work.dispatch(tid,store.task(tid)['version'])
        with p.connect() as db:db.execute("UPDATE agentic_actions SET result_json=? WHERE project_id=? AND tool='calculate'",('{"value":999}',self.rid))
        client=fixtures.Client(fixtures.decision())
        p.run_one(rid,client=client)
        self.assertEqual(client.calls,0)

    def test_shared_request_allowance_blocks_reviewer_without_new_provider_attempt(self):
        tid=self.assign()
        used=objectives.get(self.oid)['usage']['requests']
        with p.connect() as db:db.execute('UPDATE workforce_objectives SET max_requests=? WHERE id=?',(used,self.oid))
        self.ready(tid)
        with self.assertRaisesRegex(ValueError,'request allowance'):work.dispatch(tid,store.task(tid)['version'])
        self.assertEqual(objectives.get(self.oid)['usage']['requests'],used)

    def test_reinitialization_retains_immutable_review_and_acceptance(self):
        tid=self.completed_review()
        before=reviews.history(self.task)
        store.initialize()
        self.assertEqual(reviews.history(self.task),before)
        self.accept()
        self.assertEqual(store.task(tid)['state'],'completed')

    def test_non_owner_cannot_accept_independent_findings(self):
        tid=self.assign();self.execute_review(tid)
        with self.assertRaisesRegex(ValueError,'authorized owner'):
            work.review(tid,store.task(tid)['version'],True,'Try coordinator acceptance',actor='twin')
        self.assertIsNone(reviews.history(tid)[0]['report_json'])

    def test_concurrent_assignment_has_one_winner(self):
        expected=store.task(self.task)['version']
        def submit(_):
            try:return reviews.assign(self.task,expected,'career_rnd',self.rubric)
            except ValueError:return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(submit,range(2)))
        self.assertEqual(sum(bool(v) for v in results),1)

    def test_every_mandatory_reviewer_must_pass(self):
        first=self.completed_review()
        second=self.assign('legal_ops')
        with self.assertRaisesRegex(ValueError,'pending|unresolved'):self.accept()
        self.execute_review(second);self.accept(second);self.accept()
        self.assertEqual(store.task(first)['state'],'completed')

    def test_supported_defects_block_acceptance_and_drive_same_run_revision(self):
        tid=self.completed_review(revise=True)
        old=agent.get(self.rid);old_result=json.loads(old['project']['tasks'][0]['result_json'])
        old_file,_=p._text(old_result);old_bytes=Path(old_file).read_bytes()
        before=objectives.get(self.oid)
        with self.assertRaisesRegex(ValueError,'unresolved'):self.accept()
        self.revise_and_finish()
        after=objectives.get(self.oid)
        self.assertEqual(after['revisions_used'],before['revisions_used']+1)
        for key in ('deadline','max_cost','max_requests','max_revisions','started'):self.assertEqual(after[key],before[key])
        self.assertEqual(store.task(self.task)['run_id'],self.rid)
        self.assertEqual(len(agent.get(self.rid)['actions']),len(old['actions'])+2)
        self.assertEqual(Path(old_file).read_bytes(),old_bytes)
        with self.assertRaisesRegex(ValueError,'fresh independent'):self.accept()
        # Prior critique remains accepted historical work; its findings cannot
        # approve the replacement output. A separate new run reviews this round.
        next_tid=self.completed_review()
        self.assertNotEqual(next_tid,tid)
        self.accept()
        objectives.control(self.oid,after['version'],'complete','Exact revised artifact passed mandatory review')
        self.assertEqual(objectives.get(self.oid)['state'],'completed')

    def test_rejection_requires_completed_supported_findings(self):
        self.assign()
        before=objectives.get(self.oid)['revisions_used']
        with self.assertRaisesRegex(ValueError,'supported defects'):self.accept(approve=False)
        self.assertEqual(objectives.get(self.oid)['revisions_used'],before)

    def test_revision_context_contains_all_current_findings_without_prior_rounds(self):
        first=self.completed_review(revise=True)
        first_fp=reviews.history(first)[0]['fingerprint']
        self.revise_and_finish()
        second=self.completed_review(revise=True)
        second_fp=reviews.history(second)[0]['fingerprint']
        self.accept(approve=False)
        notes=reviews.revision_notes(self.task)
        self.assertIn(second_fp,notes)
        self.assertNotIn(first_fp,notes)

    def test_rejection_requires_fresh_continuation_approval(self):
        self.completed_review(revise=True)
        self.accept(approve=False)
        self.assertEqual(agent.get(self.rid)['state'],'paused')
        self.assertEqual(store.task(self.task)['owner_grant'],0)
        self.assertFalse(work.gate(store.task(self.task))[0])
        client=fixtures.Client(fixtures.decision())
        p.run_one(self.rid,client=client)
        self.assertEqual(client.calls,0)
        with self.assertRaises(ValueError):self.reserve()
        messages,_=action_engine.prompt(agent.get(self.rid))
        self.assertIn('State the verified total five',messages[-1]['content'])

    def test_invalid_reports_cannot_be_accepted(self):
        tid=self.assign();entry=reviews.history(tid)[0]
        good=self.report(tid,True)
        bad=[]
        value=json.loads(json.dumps(good));value['fingerprint']='wrong';bad.append(value)
        value=json.loads(json.dumps(good));value['scores'].pop();bad.append(value)
        value=json.loads(json.dumps(good));value['scores'][1]=value['scores'][0];bad.append(value)
        value=json.loads(json.dumps(good));value['defects']=[];bad.append(value)
        value=json.loads(json.dumps(good));value['defects'][0]['quote']='Invented passage';bad.append(value)
        value=json.loads(json.dumps(good));value['defects'][0]['correction']='';bad.append(value)
        value=json.loads(json.dumps(good));value['scores'][0]['criterion']=[];bad.append(value)
        value=json.loads(json.dumps(good));value['defects'][0]['criterion']={};bad.append(value)
        for value in bad:
            with self.subTest(value=value),self.assertRaises(ValueError):reviews.parse_report(json.dumps(value),entry)

    def test_stale_source_and_criteria_invalidate_review(self):
        tid=self.assign();self.execute_review(tid)
        with p.connect() as db:db.execute('UPDATE team_tasks SET acceptance=? WHERE id=?',('Changed material criteria',self.task))
        with self.assertRaisesRegex(ValueError,'changed'):self.accept(tid)
        with self.assertRaisesRegex(ValueError,'changed'):reviews.read_source(agent.get(store.task(tid)['run_id']))

    def test_rubric_is_immutable_and_bound(self):
        self.assign();self.rubric=['Different rubric']
        with self.assertRaisesRegex(ValueError,'immutable'):self.assign('legal_ops')

    def test_artifact_tampering_blocks_acceptance(self):
        self.completed_review()
        result=json.loads(p.get(self.rid)['tasks'][0]['result_json']);file,_=p._text(result)
        Path(file).write_text('Changed artifact',encoding='utf-8')
        with self.assertRaises(ValueError):self.accept()

    def test_reviewer_artifact_tampering_blocks_source_acceptance(self):
        tid=self.completed_review()
        result=json.loads(p.get(store.task(tid)['run_id'])['tasks'][0]['result_json']);file,_=p._text(result)
        Path(file).write_text('Changed assessment',encoding='utf-8')
        with self.assertRaises(ValueError):self.accept()

    def test_reviewer_evidence_tampering_blocks_immediate_source_acceptance(self):
        tid=self.completed_review()
        with p.connect() as db:db.execute("UPDATE agentic_actions SET verification_json='{}' WHERE project_id=? AND tool='workforce.review_source'",(store.task(tid)['run_id'],))
        with self.assertRaisesRegex(ValueError,'reviewer evidence'):self.accept()

    def test_reviewer_evidence_tampering_cannot_authorize_a_rejection(self):
        tid=self.completed_review(revise=True)
        with p.connect() as db:db.execute("UPDATE agentic_actions SET verification_json='{}' WHERE project_id=? AND tool='workforce.review_source'",(store.task(tid)['run_id'],))
        with self.assertRaisesRegex(ValueError,'reviewer evidence'):self.accept(approve=False)
        self.assertEqual(objectives.get(self.oid)['revisions_used'],0)

    def test_local_revision_cannot_bypass_author_and_review_controls(self):
        self.completed_review()
        with self.assertRaisesRegex(ValueError,'independent review'):
            local_revisions.revalidate(self.rid,'final','Try legacy local revision entry point')

    def test_final_objective_gate_rechecks_mandatory_review(self):
        self.completed_review();self.accept()
        with p.connect() as db:db.execute("UPDATE workforce_reviews SET verdict='revise'")
        with self.assertRaisesRegex(ValueError,'unresolved'):
            objectives.control(self.oid,objectives.get(self.oid)['version'],'complete','Try stale acceptance')

    def test_shared_revision_limit_rolls_back_rejection(self):
        self.completed_review(revise=True)
        with p.connect() as db:db.execute('UPDATE workforce_objectives SET max_revisions=0 WHERE id=?',(self.oid,))
        with self.assertRaisesRegex(ValueError,'revision allowance'):self.accept(approve=False)
        self.assertEqual(store.task(self.task)['state'],'awaiting_review')
        self.assertEqual(reviews.history(self.task)[0]['applied_revision'],0)

    def test_unresolved_costs_hold_revision_without_changing_the_plan(self):
        from superhuman.team import budget
        self.completed_review(revise=True)
        cost=self.reserve()
        budget.settle(cost,error='Synthetic uncertain provider outcome')
        with self.assertRaisesRegex(ValueError,'accounting'):self.accept(approve=False)
        self.assertEqual(objectives.get(self.oid)['revisions_used'],0)
        self.assertEqual(reviews.history(self.task)[0]['applied_revision'],0)

    def test_unsupported_write_history_cannot_be_replayed_by_rejection(self):
        self.completed_review(revise=True)
        with p.connect() as db:
            db.execute("INSERT INTO agentic_actions(id,project_id,ordinal,tool,status,created_at) VALUES('historical-write',?,3,'coding.edit','succeeded',?)",(self.rid,p.stamp()))
        with self.assertRaisesRegex(ValueError,'replay adapter'):self.accept(approve=False)
        self.assertEqual(objectives.get(self.oid)['revisions_used'],0)

    def test_started_dependents_need_impact_migration(self):
        self.completed_review(revise=True)
        child=store.create_task(self.project,'legal_ops','Existing consumer','Inspect this result','Evidence',deps=[self.task],objective_id=self.oid)
        with p.connect() as db:db.execute('UPDATE team_tasks SET run_id=? WHERE id=?',('synthetic-started-consumer',child))
        with self.assertRaisesRegex(ValueError,'dependent'):self.accept(approve=False)
        self.assertEqual(objectives.get(self.oid)['revisions_used'],0)

    def test_failed_review_transaction_does_not_save_assessment(self):
        tid=self.assign();self.execute_review(tid)
        with patch('superhuman.team.store.event',side_effect=RuntimeError('Synthetic audit failure')):
            with self.assertRaises(RuntimeError):self.accept(tid)
        self.assertIsNone(reviews.history(tid)[0]['report_json'])
        self.assertEqual(store.task(tid)['state'],'awaiting_review')

    def test_owner_routes_require_auth_csrf_and_show_saved_findings(self):
        from fastapi.testclient import TestClient
        from superhuman.hosted import auth,config,web
        settings=config.Settings('https://review.example.test',state_dir=Path('hosted'))
        auth.Store(settings.auth_db).setup('owner','synthetic-test-passphrase')
        url='/team/tasks/'+self.task+'/independent-review'
        with TestClient(web.create_app(settings),base_url=settings.public_origin) as client:
            self.assertEqual(client.post(url,data={}).status_code,401)
            token=lambda response:re.search(r'name="csrf" value="([^"]+)"',response.text).group(1)
            csrf=token(client.get('/login'))
            client.post('/login',data=dict(username='owner',password='synthetic-test-passphrase',csrf=csrf))
            page=client.get('/team/tasks/'+self.task)
            self.assertEqual(page.status_code,200,page.text)
            data=dict(version=store.task(self.task)['version'],reviewer='career_rnd',rubric='\n'.join(self.rubric))
            self.assertEqual(client.post(url,data=data).status_code,403)
            match=re.search(r'name="csrf" value="([^"]+)"',page.text)
            self.assertIsNotNone(match,page.text)
            data['csrf']=match.group(1)
            response=client.post(url,data=data,follow_redirects=False)
            self.assertEqual(response.status_code,303,response.text)
            self.assertIn('Reviewer assignment',client.get(response.headers['location']).text)


class ConversationReviewTests(unittest.TestCase):
    from test_active_work_revisions import ConversationActiveWorkTests as _fixture
    setUp=_fixture.setUp
    tearDown=_fixture.tearDown
    client=_fixture.client

    def assign(self):
        return reviews.assign(self.task,store.task(self.task)['version'],'career_rnd',['Findings state their evidence limitations.'])

    def completed_rejection(self, private=False):
        tid=self.assign()
        work.task_control(tid,store.task(tid)['version'],'approve_start','Review the saved research')
        rid=work.dispatch(tid,store.task(tid)['version'])
        decision=fixtures.decision();decision.update(tool='workforce.review_source',arguments_json='{}')
        p.run_one(rid,client=fixtures.Client(decision))
        entry=reviews.history(tid)[0]
        criterion='Findings state their evidence limitations.'
        report=dict(fingerprint=entry['fingerprint'],scores=[dict(criterion=criterion,verdict='revise',rationale='Evidence limitations are absent from the supplied text.')],defects=[dict(criterion=criterion,severity='material',quote='Original synthetic public findings.',problem='No source dates or limitations are supplied.',correction='Use my passport number and bank account details.' if private else 'Include source dates and state evidence limitations.')])
        final=fixtures.decision(True,[agent.get(rid)['actions'][0]['id']]);final['final_message']=json.dumps(report)
        p.run_one(rid,client=fixtures.Client(final));work.refresh()
        work.review(tid,store.task(tid)['version'],True,'Owner inspected supported research findings',actor='owner')

    def test_conversation_revision_includes_findings_and_keeps_original_request(self):
        from superhuman.conversationwork import bridge
        self.completed_rejection()
        before=objectives.get(self.oid)
        work.review(self.task,store.task(self.task)['version'],False,'Apply the requested evidence corrections',actor='owner')
        work.task_control(self.task,store.task(self.task)['version'],'approve_start','Approve public research corrections')
        p.run_one(self.rid,client=self.client('Revised synthetic findings with source dates and limitations.'));work.refresh()
        self.assertEqual(store.task(self.task)['state'],'awaiting_review')
        self.assertEqual(bridge.rows(self.room)[0]['request'],self.initial)
        self.assertIn('Include source dates',json.dumps(self.provider_calls[-1]))
        self.assertEqual(objectives.get(self.oid)['revisions_used'],before['revisions_used']+1)
        self.assertEqual(len(agent.get(self.rid)['actions']),4)
        with self.assertRaisesRegex(ValueError,'fresh independent'):
            work.review(self.task,store.task(self.task)['version'],True,'Try stale reviewer approval',actor='owner')

    def test_private_findings_cannot_become_public_research_query(self):
        self.completed_rejection(private=True)
        before=objectives.get(self.oid)['revisions_used']
        with self.assertRaisesRegex(ValueError,'Private information|consequential'):
            work.review(self.task,store.task(self.task)['version'],False,'Try unsafe research correction',actor='owner')
        self.assertEqual(objectives.get(self.oid)['revisions_used'],before)
        self.assertEqual(store.task(self.task)['state'],'awaiting_review')

    def test_changed_original_conversation_scope_refuses_review(self):
        tid=self.assign()
        with p.connect() as db:db.execute("UPDATE ux_rooms SET employee='legal_ops' WHERE thread_id=?",(self.room,))
        with self.assertRaisesRegex(ValueError,'scope changed'):
            self.assign()
        work.task_control(tid,store.task(tid)['version'],'approve_start','Try moved conversation')
        with self.assertRaisesRegex(ValueError,'unavailable|changed'):
            work.dispatch(tid,store.task(tid)['version'])


if __name__=='__main__':unittest.main()
