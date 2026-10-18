"""Impact preparation/application over real objective execution and review records."""
import hashlib
import json
import re
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

import test_workforce_objectives as fixtures
from superhuman.projects import engine as p
from superhuman.team import objectives, store, work, workplans, budget
from superhuman.agentic import store as agent, tools


class ActiveWorkTests(unittest.TestCase):
    tearDown = fixtures.ObjectiveTests.tearDown
    objective = fixtures.ObjectiveTests.objective
    ready = fixtures.ObjectiveTests.ready
    reserve = fixtures.ObjectiveTests.reserve
    finish = fixtures.ObjectiveTests.finish

    def setUp(self):
        fixtures.ObjectiveTests.setUp(self)
        self.oid = self.objective()
        self.brief = 'Calculate 3+4 and provide action evidence.'
        self.criteria = 'Verified total seven.'

    def pause(self):
        obj = objectives.get(self.oid)
        if obj['state'] != 'paused':
            objectives.control(self.oid, obj['version'], 'pause', 'Inspect the changed objective')

    def assignments(self):
        result = {}
        for member in objectives.get(self.oid)['tasks']:
            task = store.task(member['id'])
            root = task['id'] == self.task
            result[task['id']] = dict(disposition='revise' if root or task['state'] != 'completed' else 'retain',
                brief=self.brief if root else task['instruction'], criteria=self.criteria if root else task['acceptance'],
                reason='Changed assumptions require fresh work.' if root else 'Independent completed evidence remains valid.')
        return result

    def prepare(self, **changes):
        self.pause()
        values = dict(ident=self.oid, expected=objectives.get(self.oid)['version'], brief=self.brief,
            criteria=self.criteria, impact='Owner changed the required calculation; assess dependent work.',
            assignments=self.assignments(), submission_key=uuid4().hex)
        values.update(changes)
        return workplans.prepare(**values)

    def apply(self, change=None):
        change = change or self.prepare()
        return workplans.apply(change, workplans.get(change)['digest'])

    def accept(self, task=None):
        task = task or self.task
        work.review(task, store.task(task)['version'], True, 'Synthetic owner output acceptance', actor='owner')

    def test_prepared_assessment_does_not_change_work_or_consume_revision(self):
        rid = self.finish()
        self.pause()
        before, obj = store.task(self.task), objectives.get(self.oid)
        change = self.prepare()
        packet = workplans.get(change)
        self.assertEqual(packet['state'], 'prepared')
        self.assertEqual(store.task(self.task), before)
        self.assertEqual(objectives.get(self.oid), obj)
        snapshot = json.loads(packet['snapshot_json'])
        self.assertEqual(snapshot['runs'][rid]['tasks'][0]['status'], 'needs_review')
        self.assertIn('result_json', snapshot['runs'][rid]['tasks'][0])

    def test_apply_keeps_ids_spend_limits_files_and_prior_review_snapshot(self):
        rid = self.finish()
        self.accept()
        old_run = agent.get(rid)
        record = json.loads(old_run['project']['tasks'][0]['result_json'])
        filename, _ = p._text(record)
        old_bytes = Path(filename).read_bytes()
        self.pause()
        before = objectives.get(self.oid)
        task_before = store.task(self.task)
        self.assertEqual(self.apply(), 2)
        after = objectives.get(self.oid)
        for key in ('id', 'root_task_id', 'origin_json', 'usage', 'started', 'deadline', 'max_cost', 'max_requests', 'max_revisions'):
            self.assertEqual(after[key], before[key], key)
        self.assertEqual(after['revisions_used'], before['revisions_used'] + 1)
        self.assertEqual(after['state'], 'paused')
        task = store.task(self.task)
        self.assertEqual(task['run_id'], rid)
        self.assertEqual(task['owner_grant'], 0)
        for key in ('max_calls', 'max_steps', 'cost_limit'):
            self.assertEqual(task[key], task_before[key])
        run = agent.get(rid)
        self.assertEqual(run['project']['used_calls'], old_run['project']['used_calls'])
        self.assertEqual(run['project']['max_calls'], old_run['project']['max_calls'])
        self.assertEqual(len(run['actions']), len(old_run['actions']))
        self.assertTrue(all(a['status'] == 'superseded' for a in run['actions']))
        self.assertEqual(run['project']['tasks'][0]['status'], 'pending')
        self.assertEqual(Path(filename).read_bytes(), old_bytes)
        with p.connect() as db:
            raw = [dict(a) for a in db.execute('SELECT * FROM agentic_actions WHERE project_id=? ORDER BY ordinal', (rid,))]
            change = db.execute("SELECT snapshot_json FROM workforce_plan_changes WHERE state='applied'").fetchone()
        self.assertEqual(raw, old_run['actions'])
        self.assertEqual(json.loads(change['snapshot_json'])['runs'][rid]['tasks'][0]['status'], 'approved')

    def test_old_actions_cannot_verify_or_export_current_work(self):
        rid = self.finish()
        action = agent.get(rid)['actions'][0]
        self.apply()
        with self.assertRaisesRegex(ValueError, 'earlier plan'):
            tools.verify_saved(action, 'marketing')
        with self.assertRaisesRegex(ValueError, 'successful action'):
            tools.text_from_action(agent.get(rid), dict(source_action=action['id']))
        with self.assertRaises(ValueError):
            objectives.verify_accepted(self.oid)

    def test_new_plan_executes_same_run_with_fresh_actions_and_review(self):
        rid = self.finish()
        before = p.get(rid)['used_calls']
        self.apply()
        work.task_control(self.task, store.task(self.task)['version'], 'approve_start', 'Approve revised assignment')
        objectives.control(self.oid, objectives.get(self.oid)['version'], 'resume', 'Resume the reviewed plan')
        value = fixtures.decision(); value['arguments_json'] = '{"expression":"3+4"}'
        p.run_one(rid, client=fixtures.Client(value))
        new_action = agent.get(rid)['actions'][-1]['id']
        final = fixtures.decision(True, [new_action]); final['final_message'] = 'The verified total is seven.'
        p.run_one(rid, client=fixtures.Client(final))
        work.refresh()
        self.assertEqual(store.task(self.task)['state'], 'awaiting_review')
        self.assertEqual(p.get(rid)['used_calls'], before + 2)
        self.accept()
        objectives.control(self.oid, objectives.get(self.oid)['version'], 'complete', 'New recorded criteria satisfied')
        self.assertEqual(objectives.get(self.oid)['state'], 'completed')

    def test_fresh_owner_approval_cannot_be_bypassed_by_resume_or_ready_state(self):
        rid = self.finish()
        self.apply()
        work.task_control(self.task, store.task(self.task)['version'], 'resume', 'Inspect without new-plan start approval')
        objectives.control(self.oid, objectives.get(self.oid)['version'], 'resume', 'Resume objective')
        with p.connect() as db:
            db.execute("UPDATE team_tasks SET state='ready',owner_grant=1 WHERE id=?", (self.task,))
        self.assertIn('Owner must approve', work.gate(store.task(self.task))[1])
        with self.assertRaisesRegex(budget.BudgetBlocked, 'Owner must approve'):
            self.reserve()
        client = fixtures.Client(fixtures.decision())
        self.assertIsNone(p.run_one(rid, client=client))
        self.assertEqual(client.calls, 0)

    def test_approval_alone_does_not_resume_paused_objective(self):
        rid = self.finish()
        self.apply()
        work.task_control(self.task, store.task(self.task)['version'], 'approve_start', 'Approve the changed assignment')
        self.assertEqual(objectives.get(self.oid)['state'], 'paused')
        self.assertIsNone(p.run_one(rid, client=fixtures.Client(fixtures.decision())))

    def test_verified_independent_completed_assignment_is_retained_unchanged(self):
        sibling = store.create_task(self.project, 'marketing', 'Independent completed work', 'Calculate 2+3.', 'Five.', objective_id=self.oid)
        root = self.task
        self.task = sibling
        rid = self.finish(); self.accept()
        self.task = root
        before, run = store.task(sibling), agent.get(rid)
        self.apply()
        self.assertEqual(store.task(sibling), before)
        self.assertEqual(agent.get(rid), run)

    def test_changed_dependency_forces_downstream_revision(self):
        child = store.create_task(self.project, 'marketing', 'Dependent assignment', 'Calculate dependent result.', 'Checked.', deps=[self.task], objective_id=self.oid)
        assignments = self.assignments()
        assignments[child]['disposition'] = 'retain'
        with self.assertRaisesRegex(ValueError, 'Dependent assignments'):
            self.prepare(assignments=assignments)

    def test_changed_handoff_context_forces_child_revision(self):
        child = store.create_task(self.project, 'legal_ops', 'Handoff child', 'Check calculation.', 'Checked.', parent_id=self.task)
        assignments = self.assignments(); assignments[child]['disposition'] = 'retain'
        with self.assertRaisesRegex(ValueError, 'Dependent assignments'):
            self.prepare(assignments=assignments)

    def test_cross_objective_dependents_and_cycles_are_refused(self):
        external = store.create_task(self.project, 'marketing', 'External dependent', 'Check root.', 'Checked.', deps=[self.task])
        with self.assertRaisesRegex(ValueError, 'outside this objective'):
            self.prepare()
        with p.connect() as db:
            db.execute("UPDATE team_tasks SET deps='[]' WHERE id=?", (external,))
            db.execute('UPDATE team_tasks SET deps=? WHERE id=?', (json.dumps([self.task]), self.task))
        with self.assertRaisesRegex(ValueError, 'cycle'):
            self.prepare()
        with p.connect() as db:
            db.execute('UPDATE team_tasks SET deps=? WHERE id=?', (json.dumps([external]), self.task))
            db.execute('UPDATE team_tasks SET deps=? WHERE id=?', (json.dumps([self.task]), external))
        with self.assertRaisesRegex(ValueError, 'cycle'):
            self.prepare()

    def test_uncertain_cost_is_not_released_or_replayed(self):
        cost = self.reserve(); budget.settle(cost, error='Synthetic uncertain paid outcome')
        before = objectives.get(self.oid)['usage']
        with self.assertRaisesRegex(ValueError, 'uncertain'):
            self.prepare()
        self.assertEqual(objectives.get(self.oid)['usage'], before)

    def test_inflight_task_and_reserved_provider_block_preparation(self):
        self.ready()
        rid = work.dispatch(self.task, store.task(self.task)['version'])
        with p.connect() as db:
            db.execute("UPDATE project_tasks SET status='running' WHERE project_id=?", (rid,))
        with self.assertRaisesRegex(ValueError, 'in-flight work'):
            self.prepare()
        with p.connect() as db:
            db.execute("UPDATE project_tasks SET status='pending' WHERE project_id=?", (rid,))
        objectives.control(self.oid, objectives.get(self.oid)['version'], 'resume', 'Synthetic resume')
        self.reserve()
        with self.assertRaisesRegex(ValueError, 'in-flight/uncertain'):
            self.prepare()

    def test_stale_assessment_after_limit_or_membership_change_does_not_apply(self):
        change = self.prepare()
        work.limits(self.task, store.task(self.task)['version'], 12, 20, '1')
        with self.assertRaisesRegex(ValueError, 'prepare a fresh'):
            self.apply(change)
        self.assertEqual(objectives.get(self.oid)['revisions_used'], 0)

    def test_apply_is_idempotent_and_concurrent_applications_consume_once(self):
        change = self.prepare(); digest = workplans.get(change)['digest']
        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(lambda _: workplans.apply(change, digest), range(2)))
        self.assertEqual(result, [2, 2])
        self.assertEqual(objectives.get(self.oid)['revisions_used'], 1)

    def test_two_prepared_candidates_cannot_both_apply(self):
        a, b = self.prepare(), self.prepare()
        self.apply(a)
        with self.assertRaisesRegex(ValueError, 'prepare a fresh'):
            self.apply(b)
        self.assertEqual(objectives.get(self.oid)['revisions_used'], 1)

    def test_failed_receipt_rolls_back_all_plan_task_and_run_changes(self):
        rid = self.finish()
        change = self.prepare(); before = objectives.get(self.oid); run = agent.get(rid)
        with patch.object(workplans, '_receipt', side_effect=RuntimeError('Synthetic receipt failure')):
            with self.assertRaises(RuntimeError):
                self.apply(change)
        self.assertEqual(objectives.get(self.oid), before)
        self.assertEqual(agent.get(rid), run)
        self.assertEqual(workplans.get(change)['state'], 'prepared')

    def test_tampered_retained_output_refuses_apply(self):
        sibling = store.create_task(self.project, 'marketing', 'Independent output', 'Calculate 2+3.', 'Five.', objective_id=self.oid)
        root = self.task; self.task = sibling
        rid = self.finish(); self.accept(); self.task = root
        change = self.prepare()
        filename, _ = p._text(json.loads(p.get(rid)['tasks'][0]['result_json']))
        Path(filename).write_text('Tampered synthetic result', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.apply(change)
        self.assertEqual(objectives.get(self.oid)['revisions_used'], 0)

    def test_unsupported_tool_history_requires_adapter(self):
        rid = self.finish()
        with p.connect() as db:
            db.execute("UPDATE agentic_actions SET tool='coding.edit' WHERE project_id=? AND ordinal=1", (rid,))
        with self.assertRaisesRegex(ValueError, 'replay adapter'):
            self.prepare()

    def test_prepare_idempotency_and_payload_reuse_validation(self):
        key = uuid4().hex
        a = self.prepare(submission_key=key)
        self.assertEqual(self.prepare(submission_key=key), a)
        with self.assertRaisesRegex(ValueError, 'different content'):
            self.prepare(submission_key=key, impact='Different impact')

    def test_approval_and_snapshot_records_survive_reinitialization(self):
        self.finish(); change = self.prepare(); self.apply(change)
        before = workplans.get(change)
        with p.connect() as db:
            controls = [tuple(r) for r in db.execute('SELECT * FROM workforce_task_plan_controls')]
        store.initialize(); store.initialize()
        self.assertEqual(workplans.get(change), before)
        with p.connect() as db:
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM workforce_task_plan_controls')], controls)

    def test_prepared_payload_is_bound_to_owner_review_digest(self):
        change = self.prepare()
        packet = workplans.get(change)
        payload = json.loads(packet['payload_json']); payload['impact'] = 'Changed after review'
        with p.connect() as db:
            db.execute('UPDATE workforce_plan_changes SET payload_json=? WHERE id=?', (json.dumps(payload), change))
        with self.assertRaisesRegex(ValueError, 'content changed'):
            self.apply(change)
        self.assertEqual(objectives.get(self.oid)['revisions_used'], 0)

    def test_external_input_change_invalidates_prepared_assessment(self):
        source = store.create_task(self.project, 'marketing', 'External input', 'Prepare an input.', 'Checked input.')
        with p.connect() as db:
            db.execute('UPDATE team_tasks SET deps=? WHERE id=?', (json.dumps([source]), self.task))
        change = self.prepare()
        self.assertIn(source, json.loads(workplans.get(change)['snapshot_json'])['inputs'])
        with p.connect() as db:
            db.execute('UPDATE team_tasks SET instruction=?,version=version+1 WHERE id=?', ('Input assumptions changed.', source))
        with self.assertRaisesRegex(ValueError, 'prepare a fresh'):
            self.apply(change)

    def test_milestone_work_cannot_use_ordinary_impact_workflow(self):
        from superhuman.milestones import store as milestones
        milestones.initialize()
        with p.connect() as db:
            db.execute('INSERT INTO milestone_assignments(task_id,milestone_id,role) VALUES(?,?,?)',
                       (self.task, 'synthetic-milestone', 'worker'))
        with self.assertRaisesRegex(ValueError, 'Milestone work'):
            self.prepare()

    def test_stale_run_snapshot_cannot_execute_old_instructions_after_replanning(self):
        rid = self.finish(); old_run = agent.get(rid)
        self.apply()
        work.task_control(self.task, store.task(self.task)['version'], 'approve_start', 'Approve changed work')
        objectives.control(self.oid, objectives.get(self.oid)['version'], 'resume', 'Resume changed work')
        client = fixtures.Client(fixtures.decision())
        with patch.object(agent, 'get', return_value=old_run):
            p.run_one(rid, client=client)
        self.assertEqual(client.calls, 0)
        self.assertEqual(agent.get(rid)['project']['tasks'][0]['status'], 'pending')

    def test_revision_cannot_reset_a_reached_action_limit(self):
        rid = self.finish()
        work.limits(self.task, store.task(self.task)['version'], 12, 2, '1')
        self.apply()
        work.task_control(self.task, store.task(self.task)['version'], 'approve_start', 'Approve changed work')
        objectives.control(self.oid, objectives.get(self.oid)['version'], 'resume', 'Resume changed work')
        client = fixtures.Client(fixtures.decision())
        p.run_one(rid, client=client)
        self.assertEqual(client.calls, 0)
        self.assertEqual(agent.get(rid)['state'], 'step_limit')

    def test_applied_assessment_and_approval_gate_survive_a_fresh_process(self):
        import os, subprocess, sys
        self.finish(); change = self.prepare(); self.apply(change)
        source = str(Path(fixtures.__file__).resolve().parents[1])
        script = ("import sys; sys.path.insert(0,sys.argv[1]); from superhuman.team import workplans,store,work; "
                  "print(workplans.get(sys.argv[2])['state']); print(work.gate(store.task(sys.argv[3]))[1])")
        result = subprocess.run([sys.executable, '-c', script, source, change, self.task],
                                env=dict(os.environ, PYTHON_DOTENV_DISABLED='1'), text=True, capture_output=True, check=True)
        self.assertIn('applied', result.stdout)
        self.assertIn('paused', result.stdout)


    def test_owner_review_routes_require_login_csrf_and_show_concrete_impact(self):
        from fastapi.testclient import TestClient
        from superhuman.hosted import auth, config, web
        rid = self.finish(); self.pause()
        settings = config.Settings('https://active-revision.example.test', state_dir=Path('hosted'))
        auth.Store(settings.auth_db).setup('owner', 'synthetic-test-passphrase')
        url = f'/team/objectives/{self.oid}/changes'
        payload = dict(version=objectives.get(self.oid)['version'], submission_key=uuid4().hex,
            brief=self.brief, criteria=self.criteria, impact='Synthetic owner scope change.',
            **{'disposition_'+self.task:'revise', 'reason_'+self.task:'New total is needed.'})
        with TestClient(web.create_app(settings), base_url=settings.public_origin) as client:
            self.assertEqual(client.post(url, data=payload).status_code, 401)
            token = lambda response: re.search(r'name="csrf" value="([^"]+)"', response.text).group(1)
            csrf = token(client.get('/login'))
            client.post('/login', data=dict(username='owner', password='synthetic-test-passphrase', csrf=csrf))
            self.assertEqual(client.post(url, data=payload).status_code, 403)
            page = client.get(url+'/new'); self.assertIn('Prepare impact assessment', page.text)
            payload['csrf'] = token(page)
            response = client.post(url, data=payload, follow_redirects=False)
            self.assertEqual(response.status_code, 303, response.text)
            review = client.get(response.headers['location'])
            self.assertIn('Requests used 2 / 12', review.text)
            self.assertIn('needs_review', review.text)
            self.assertIn(self.brief, review.text)
            artifact_url=response.headers['location']+'/artifacts/'+self.task
            historical=client.get(artifact_url)
            self.assertEqual(historical.status_code, 200, historical.text)
            self.assertIn('historical-', historical.headers['content-disposition'])
            apply_url = response.headers['location']+'/apply'
            digest = re.search(r'name="digest" value="([^"]+)"', review.text).group(1)
            self.assertEqual(client.post(apply_url, data=dict(digest=digest)).status_code, 403)
            self.assertEqual(client.post(apply_url, data=dict(digest=digest, csrf=token(review)), follow_redirects=False).status_code, 303)
            self.assertEqual(agent.get(rid)['state'], 'paused')
            self.assertEqual(client.get(artifact_url).content, historical.content)


class ConversationActiveWorkTests(unittest.TestCase):
    tearDown = fixtures.ObjectiveTests.tearDown

    def setUp(self):
        fixtures.ObjectiveTests.setUp(self)
        from superhuman.experience import store as ux
        from superhuman.dialogue import store as dialogue, engine as chat
        from superhuman.conversationwork import bridge
        self.room = ux.create('marketing', 'Synthetic research conversation')
        self.initial = 'Please research current official public guidance about business planning.'
        self.turn = dialogue.send(self.room, self.initial, uuid4().hex)
        plan = dict(kind='research', scope='marketing', title='Public guidance', acceptance='Cited public findings.', risk='routine', sensitivity='internal')
        self.assertEqual(chat.run_turn(client=fixtures.Client(dict(reply='Acknowledgement', tasks=[], execution=plan)))['status'], 'done')
        self.job = bridge.rows(self.room)[0]; self.task = self.job['task_id']
        self.oid = objectives.create(self.task, store.task(self.task)['version'], '1', 20, 3600, 3, 'Explicit research allowance')
        work.limits(self.task, store.task(self.task)['version'], 4, 8, '1')
        self.rid = work.dispatch(self.task, store.task(self.task)['version'])
        self.provider_calls = []
        p.run_one(self.rid, client=self.client('Original synthetic public findings.'))
        work.refresh()
        self.brief = 'Please research current official public guidance about business record keeping.'
        self.criteria = 'Include source dates and state evidence limitations.'

    def client(self, text):
        def create(**kwargs):
            self.provider_calls.append(kwargs)
            return fixtures.N(id='synthetic-research', usage=fixtures.N(input_tokens=100, output_tokens=80), output_text=text,
                model_dump=lambda **_: {'output': [{'type':'web_search_call'}, {'content':[{'annotations':[
                    {'type':'url_citation','url':'https://www.gov.uk/set-up-business','title':'Synthetic official fixture'}]}]}]})
        return fixtures.N(responses=fixtures.N(create=create))

    def prepare(self):
        objectives.control(self.oid, objectives.get(self.oid)['version'], 'pause', 'Review changed source request')
        assignments = {self.task:dict(disposition='revise', brief=self.brief, criteria=self.criteria, reason='Research subject changed.')}
        return workplans.prepare(self.oid, objectives.get(self.oid)['version'], self.brief, self.criteria,
                                 'Replace the research subject; retain all prior history and charges.', assignments, uuid4().hex)

    def test_revised_research_uses_same_run_and_returns_current_output_to_source(self):
        from superhuman.conversationwork import bridge
        from superhuman.dialogue import store as dialogue
        old_record = json.loads(p.get(self.rid)['tasks'][0]['result_json'])
        old_file, _ = p._text(old_record); old_bytes = Path(old_file).read_bytes()
        before = objectives.get(self.oid)['usage']
        change = self.prepare()
        workplans.apply(change, workplans.get(change)['digest'])
        self.assertEqual(len(self.provider_calls), 1)
        receipt = dialogue.turns(self.room)[-1]
        self.assertIn('Plan 2 saved after impact review', receipt['reply'])
        self.assertFalse(json.loads(receipt['context_json'])['receipt']['provider_request'])
        self.assertEqual(bridge.status(self.job)['text'], '')
        work.task_control(self.task, store.task(self.task)['version'], 'approve_start', 'Approve revised research')
        objectives.control(self.oid, objectives.get(self.oid)['version'], 'resume', 'Resume revised research')
        p.run_one(self.rid, client=self.client('New synthetic record-keeping findings.'))
        work.refresh()
        self.assertEqual(len(self.provider_calls), 2)
        self.assertIn('business record keeping', str(self.provider_calls[-1]))
        self.assertEqual(p.get(self.rid)['used_calls'], 2)
        self.assertEqual(objectives.get(self.oid)['usage']['requests'], before['requests'] + 1)
        self.assertEqual(store.task(self.task)['run_id'], self.rid)
        self.assertEqual(bridge.status(self.job)['status'], 'awaiting_review')
        self.assertIn('New synthetic record-keeping findings', bridge.render(self.turn))
        self.assertEqual(bridge.job_for_task(self.task)['request'], self.initial)
        self.assertEqual(Path(old_file).read_bytes(), old_bytes)
        self.assertEqual(workplans.apply(change, workplans.get(change)['digest']), 2)
        self.assertEqual(len(dialogue.turns(self.room)), 2)

    def test_archive_or_private_scope_change_prevents_apply(self):
        from superhuman.teamhub import store as hub
        change = self.prepare()
        hub.room_control(self.room, hub.state(self.room)['version'], 'Archived', True, False, '')
        with self.assertRaisesRegex(ValueError, 'Restore'):
            workplans.apply(change, workplans.get(change)['digest'])

    def test_one_remaining_action_slot_blocks_before_a_paid_research_request(self):
        work.limits(self.task, store.task(self.task)['version'], 4, 3, '1')
        change=self.prepare()
        workplans.apply(change,workplans.get(change)['digest'])
        work.task_control(self.task,store.task(self.task)['version'],'approve_start','Approve the revised request')
        objectives.control(self.oid,objectives.get(self.oid)['version'],'resume','Resume reviewed work')
        p.run_one(self.rid,client=self.client('This provider must not be called.'))
        self.assertEqual(len(self.provider_calls),1)
        self.assertEqual(p.get(self.rid)['used_calls'],1)
        self.assertEqual(len(agent.get(self.rid)['actions']),2)
        self.assertEqual(agent.get(self.rid)['state'],'step_limit')
        work.refresh()
        with self.assertRaisesRegex(ValueError,'Amend the task step limit'):
            work.task_control(self.task,store.task(self.task)['version'],'approve_start','Attempt without raising the exhausted limit')
        work.limits(self.task,store.task(self.task)['version'],4,4,'1')
        work.task_control(self.task,store.task(self.task)['version'],'approve_start','Approve continuation under amended total steps')
        p.run_one(self.rid,client=self.client('Current findings after explicit step-limit amendment.'))
        self.assertEqual(len(self.provider_calls),2)
        self.assertEqual(p.get(self.rid)['used_calls'],2)
        self.assertEqual(len(agent.get(self.rid)['actions']),4)
        self.assertEqual(objectives.get(self.oid)['revisions_used'],1)

    def test_private_replacement_public_query_is_refused_before_prepare(self):
        self.brief = 'Please research my passport number 123456789 and current guidance.'
        with self.assertRaisesRegex(ValueError, 'Private information'):
            self.prepare()

    def test_source_receipt_failure_rolls_back_approval_invalidation(self):
        from superhuman.dialogue import store as dialogue
        change = self.prepare()
        before = store.task(self.task)
        with patch.object(dialogue, 'event', side_effect=RuntimeError('Synthetic source receipt failure')):
            with self.assertRaises(RuntimeError):
                workplans.apply(change, workplans.get(change)['digest'])
        self.assertEqual(store.task(self.task), before)
        self.assertEqual(objectives.get(self.oid)['revisions_used'], 0)
        self.assertEqual(len(dialogue.turns(self.room)), 1)



if __name__ == '__main__':
    unittest.main()
