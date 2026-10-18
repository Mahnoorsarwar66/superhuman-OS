"""Objective integration with actual task dispatch, ledger, review and owner routes."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as N
from unittest.mock import patch

from superhuman.projects import engine as p
from superhuman.team import store, budget, work, engine, objectives
from superhuman.agentic import store as agent

MODEL = 'objective-fixture-model'


class Client:
    def __init__(self, value):
        self.value, self.calls = value, 0
        self.chat = N(completions=N(create=self.create))
        self.responses = N(create=self.create)

    def create(self, **kwargs):
        self.calls += 1
        return N(id='objective-fixture', choices=[N(finish_reason='stop', message=N(
            content=json.dumps(self.value)))], usage=N(prompt_tokens=100, completion_tokens=20))


def decision(finish=False, evidence=()):
    return {'action': 'finish' if finish else 'tool', 'tool': '' if finish else 'calculate',
            'arguments_json': '{}' if finish else '{"expression":"2+3"}',
            'rationale': 'Check synthetic arithmetic.', 'final_message': 'Result checked and ready for review.' if finish else '',
            'evidence_action_ids': list(evidence)}


def twin(action, task=None, **changes):
    value = {key: '' for key in engine.STRINGS}
    value.update(action=action, task_id=task['id'] if task else '', recipient='marketing',
                 task_version=task['version'] if task else 0, request_version=0,
                 dependency_ids=[], rationale='Inspect synthetic objective evidence.', reply='Recorded decision.')
    value.update(changes)
    return value


class ObjectiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = Path.cwd()
        os.chdir(self.tmp.name)
        self.env = patch.dict(os.environ, {'PYTHON_DOTENV_DISABLED': '1',
            'SUPERHUMAN_PLANNING_DB': str(Path('plan.db').resolve()),
            'SUPERHUMAN_KNOWLEDGE_DB': str(Path('notes.db').resolve()),
            'SUPERHUMAN_IDENTITY_DIR': str(Path('identity').resolve()),
            'SUPERHUMAN_MEMORY_PATH': str(Path('memory.json').resolve()),
            'SUPERHUMAN_MAIL_KEY_FILE': str(Path('mail.key').resolve())})
        self.env.start()
        store.initialize()
        budget.create_period(10, 3, 5, 1)
        budget.set_rate(MODEL, '.1', '.2', 'Synthetic fixture rates')
        store.configure(store.settings()['version'], True, MODEL)
        self.project = store.create_project('marketing', 'Synthetic project', 'Check evidence', 'Verified output')
        self.task = store.create_task(self.project, 'marketing', 'Calculate evidence',
                                      'Calculate 2+3 and provide action evidence.', 'Verified total five.')

    def tearDown(self):
        self.env.stop()
        os.chdir(self.old)
        self.tmp.cleanup()

    def objective(self, requests=20, revisions=2, cost='1', task=None):
        tid = task or self.task
        return objectives.create(tid, store.task(tid)['version'], cost, requests, 3600, revisions,
                                 'Explicit synthetic objective allowance')

    def reserve(self, task=None):
        tid=task or self.task
        with budget.scope(store.task(tid)['owner'], tid):
            return budget.reserve(MODEL, {'messages': [{'role': 'user', 'content': 'Synthetic'}],
                                         'max_completion_tokens': 100}, 'chat')

    def ready(self, task=None):
        tid = task or self.task
        work.task_control(tid, store.task(tid)['version'], 'approve_start', 'Synthetic owner instruction')

    def finish(self):
        self.ready()
        rid = work.dispatch(self.task, store.task(self.task)['version'])
        p.run_one(rid, client=Client(decision()))
        aid = agent.get(rid)['actions'][0]['id']
        p.run_one(rid, client=Client(decision(True, [aid])))
        work.refresh()
        self.assertEqual(store.task(self.task)['state'], 'awaiting_review')
        return rid

    def test_creation_preserves_other_requests_and_existing_budget_records(self):
        legacy = store.create_task(self.project, 'marketing', 'Independent request', 'Other work', 'Other criteria')
        oid = self.objective()
        self.assertEqual(objectives.memberships(), {self.task: oid})
        self.assertNotIn(legacy, objectives.memberships())
        self.assertEqual(budget.report()['costs'], [])
        self.assertEqual(objectives.get(oid)['plans'][0]['brief'], store.task(self.task)['instruction'])

    def test_conversation_origin_preserves_exact_owner_request_and_turn(self):
        from superhuman.conversationwork import bridge
        bridge.initialize()
        request = 'Owner exact request, including its stated scope.'
        with p.connect() as db:
            db.execute('INSERT INTO conversation_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                ('synthetic-job', 'owner-turn', 'owner-room', 'marketing', 'research', '{}', request,
                 'synthetic-fingerprint', self.task, self.project, 'queued', '', p.stamp()))
        oid = self.objective()
        obj = objectives.get(oid)
        self.assertEqual(obj['plans'][0]['brief'], request)
        origin = json.loads(obj['origin_json'])
        self.assertEqual(origin['turn_id'], 'owner-turn')
        self.assertEqual(origin['room_id'], 'owner-room')
        with self.assertRaisesRegex(ValueError, 'Conversation brief changes'):
            objectives.revise_plan(oid, obj['version'], 'Different request', 'Criteria', 'Cannot replace original authority')

    def test_enrollment_after_spending_is_rejected_without_resetting_history(self):
        cost = self.reserve()
        budget.settle(cost, error='Synthetic uncertain usage')
        with self.assertRaisesRegex(ValueError, 'spending'):
            self.objective()
        self.assertEqual(len(budget.report()['costs']), 1)

    def test_children_inherit_and_cannot_escape_objective(self):
        oid = self.objective()
        child = store.create_task(self.project, 'career_rnd', 'Child', 'Research calculation', 'Evidence',
                                   parent_id=self.task, actor='twin')
        grandchild = store.create_task(self.project, 'marketing', 'Grandchild', 'Check calculation', 'Evidence',
                                        parent_id=child, actor='twin')
        self.assertEqual(objectives.memberships()[grandchild], oid)
        with self.assertRaisesRegex(ValueError, 'escape'):
            store.create_task(self.project, 'marketing', 'Escape', 'Other work', 'Criteria',
                              parent_id=child, objective_id='different', actor='twin')
        self.assertNotIn('Escape', [task['title'] for task in store.tasks()])
        with self.assertRaisesRegex(ValueError, 'Choose an objective'):
            store.create_task(self.project, 'marketing', 'Untracked', 'Work', 'Criteria', actor='twin')

    def test_delegation_cannot_reset_cumulative_request_consumption(self):
        oid = self.objective(requests=1)
        child = store.create_task(self.project, 'career_rnd', 'Delegated work', 'Check evidence', 'Evidence',
                                  parent_id=self.task, actor='twin')
        cost = self.reserve(child)
        budget.settle(cost, response=N(usage=N(prompt_tokens=100, completion_tokens=20)))
        with self.assertRaisesRegex(budget.BudgetBlocked, 'Objective request allowance'):
            self.reserve()
        self.assertEqual(objectives.get(oid)['usage']['requests'], 1)

    def test_real_handoff_resolution_inherits_parent_objective(self):
        oid = self.objective()
        self.ready()
        rid = work.dispatch(self.task, store.task(self.task)['version'])
        work.request_tool('team.handoff', {'recipient': 'career_rnd', 'title': 'Check evidence',
            'instruction': 'Check synthetic arithmetic', 'acceptance': 'Source-backed result'}, agent.get(rid))
        request = store.requests()[0]
        child = work.resolve_request(request['id'], request['version'], 'accept', 'Routine internal handoff')
        self.assertEqual(objectives.memberships()[child], oid)
        self.assertEqual(store.task(self.task)['state'], 'waiting_dependency')

    def test_concurrent_reservations_cannot_exceed_final_request(self):
        oid = self.objective(requests=1)
        barrier = threading.Barrier(2)
        def attempt():
            barrier.wait()
            try:
                return self.reserve()
            except budget.BudgetBlocked:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: attempt(), range(2)))
        self.assertEqual(sum(value is not None for value in results), 1)
        obj = objectives.get(oid)
        self.assertEqual(obj['usage']['requests'], 1)
        self.assertLessEqual(obj['usage']['cost'], obj['max_cost'])

    def test_dollars_are_checked_before_any_ledger_or_provider_request(self):
        oid = self.objective(cost='.000001')
        with self.assertRaisesRegex(budget.BudgetBlocked, 'objective allowance'):
            self.reserve()
        self.assertEqual(objectives.get(oid)['usage']['requests'], 0)
        self.assertEqual(budget.report()['costs'], [])

    def test_unknown_usage_and_restart_retain_reservations_and_request_consumption(self):
        oid = self.objective(requests=1)
        cost = self.reserve()
        before = objectives.get(oid)['usage']
        budget.recover()
        store.initialize()
        self.assertEqual(objectives.get(oid)['usage'], before)
        with self.assertRaises(ValueError):
            budget.settle(cost, response=N(usage=N(prompt_tokens=0, completion_tokens=0)))
        self.assertEqual(objectives.get(oid)['usage'], before)
        with self.assertRaises(budget.BudgetBlocked):
            self.reserve()
        budget.reconcile(cost, '0', 'Synthetic provider confirms no charge')
        self.assertEqual(objectives.get(oid)['usage']['requests'], 1)
        self.assertEqual(objectives.get(oid)['usage']['cost'], 0)

    def test_fresh_process_reads_same_objective_and_uncertain_consumption(self):
        oid = self.objective()
        cost = self.reserve()
        budget.recover()
        expected = objectives.get(oid)
        script = "import json,sys; sys.path.insert(0,sys.argv[1]); from superhuman.team import objectives; obj=objectives.get(sys.argv[2]); print(json.dumps({'state':obj['state'],'usage':obj['usage'],'deadline':obj['deadline']}))"
        result = subprocess.run([sys.executable, '-c', script, str(Path(p.__file__).resolve().parents[2]), oid],
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), {'state': expected['state'],
                         'usage': expected['usage'], 'deadline': expected['deadline']})

    def test_additive_migration_preserves_legacy_permissions_spending_and_history(self):
        cost = self.reserve()
        budget.settle(cost, error='Synthetic unknown legacy usage')
        new_tables = ('workforce_objective_costs', 'workforce_objective_tasks',
                      'workforce_objective_plans', 'workforce_objectives')
        with p.connect() as db:
            db.execute("UPDATE team_employees SET allowed_tools='[\"calculate\"]' WHERE id='marketing'")
            db.execute('UPDATE team_tasks SET owner_grant=1 WHERE id=?', (self.task,))
            for table in new_tables:
                db.execute('DROP TABLE ' + table)
            names = [row[0] for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            before = {table: [tuple(row) for row in db.execute('SELECT * FROM "' + table + '"')] for table in names}
        store.initialize()
        store.initialize()
        with p.connect() as db:
            after = {table: [tuple(row) for row in db.execute('SELECT * FROM "' + table + '"')] for table in names}
        self.assertEqual(before, after)
        self.assertEqual(objectives.listing(), [])

    def test_cancel_allows_inflight_receipt_to_settle_but_prevents_next_request(self):
        oid = self.objective()
        cost = self.reserve()
        objectives.control(oid, objectives.get(oid)['version'], 'cancel', 'Cancel further work')
        budget.settle(cost, response=N(usage=N(prompt_tokens=100, completion_tokens=20)))
        with self.assertRaisesRegex(budget.BudgetBlocked, 'cancelled'):
            self.reserve()
        self.assertEqual(objectives.get(oid)['usage']['requests'], 1)
        self.assertEqual(objectives.get(oid)['usage']['cost'], 14)

    def test_pause_after_model_response_blocks_the_prepared_tool_action(self):
        oid = self.objective()
        self.ready()
        rid = work.dispatch(self.task, store.task(self.task)['version'])
        value = decision()
        value.update(tool='document.export', arguments_json=json.dumps({
            'title': 'Must not be exported', 'format': 'docx', 'text': 'Synthetic text'}))
        client = Client(value)
        original = client.chat.completions.create
        def respond_and_pause(**kwargs):
            response = original(**kwargs)
            objectives.control(oid, objectives.get(oid)['version'], 'pause', 'Pause after provider response')
            return response
        client.chat.completions.create = respond_and_pause
        p.run_one(rid, client=client)
        action = agent.get(rid)['actions'][-1]
        self.assertEqual(action['status'], 'failed')
        self.assertEqual(json.loads(action['result_json'])['error_type'], 'ObjectiveBlocked')
        self.assertEqual(list(Path('data').rglob('*.docx')), [])
        self.assertEqual(objectives.get(oid)['usage']['cost'], 14)

    def test_untracked_asynchronous_tool_cannot_escape_objective_scope(self):
        from superhuman.agentic import tools
        self.objective()
        self.ready()
        rid = work.dispatch(self.task, store.task(self.task)['version'])
        with self.assertRaisesRegex(objectives.ObjectiveBlocked, 'Asynchronous inbox'):
            tools.execute('inbox.queue_sync', {'slot': 'synthetic'}, agent.get(rid), Client({}), Path('output'), p.DEFAULT_DB)

    def test_existing_alternative_route_cannot_replace_started_objective_brief(self):
        oid = self.objective()
        self.ready()
        rid = work.dispatch(self.task, store.task(self.task)['version'])
        original = store.task(self.task)['instruction']
        work.request_tool('team.challenge', {'concern': 'Synthetic concern', 'evidence': 'Synthetic evidence',
                          'alternative': 'Replace the current owner brief'}, agent.get(rid))
        request = store.requests()[0]
        with self.assertRaisesRegex(ValueError, 'versioned impact revision'):
            work.resolve_request(request['id'], request['version'], 'alternative', 'Owner note', actor='owner')
        self.assertEqual(store.task(self.task)['instruction'], original)
        self.assertEqual(objectives.get(oid)['current_plan'], 1)
        self.assertEqual(store.requests()[0]['status'], 'open')

    def test_objective_completion_rechecks_accepted_export_artifacts(self):
        from superhuman.capabilities import exports
        oid = self.objective()
        self.ready()
        rid = work.dispatch(self.task, store.task(self.task)['version'])
        value = decision()
        value.update(tool='document.export', arguments_json=json.dumps({
            'title': 'Synthetic report', 'format': 'docx', 'text': 'A checked synthetic report.'}))
        p.run_one(rid, client=Client(value))
        action = agent.get(rid)['actions'][0]
        p.run_one(rid, client=Client(decision(True, [action['id']])))
        work.refresh()
        work.review(self.task, store.task(self.task)['version'], True, 'Export inspected', actor='owner')
        data = json.loads(action['result_json'])
        file, _ = exports.artifact('marketing', data['export_id'])
        file.write_bytes(b'Changed after review')
        with self.assertRaises(ValueError):
            objectives.control(oid, objectives.get(oid)['version'], 'complete', 'Try stale artifact')
        self.assertEqual(objectives.get(oid)['state'], 'active')

    def test_pause_resume_and_amendment_do_not_reset_usage_or_start_time(self):
        oid = self.objective()
        cost = self.reserve()
        budget.settle(cost, response=N(usage=N(prompt_tokens=100, completion_tokens=20)))
        before = objectives.get(oid)
        objectives.control(oid, before['version'], 'pause', 'Synthetic pause')
        with self.assertRaisesRegex(budget.BudgetBlocked, 'paused'):
            self.reserve()
        obj = objectives.get(oid)
        objectives.control(oid, obj['version'], 'resume', 'Synthetic resume')
        obj = objectives.get(oid)
        objectives.amend(oid, obj['version'], '2', 30, 7200, 3, 'Explicit larger total')
        after = objectives.get(oid)
        self.assertEqual(after['usage'], before['usage'])
        self.assertEqual(after['started'], before['started'])
        self.assertEqual(after['deadline'], before['started'] + 7200)
        with self.assertRaisesRegex(ValueError, 'changed'):
            objectives.amend(oid, obj['version'], '3', 40, 8000, 4, 'Stale owner form')

    def test_deadline_blocks_next_call_and_task_gate(self):
        oid = self.objective()
        deadline = objectives.get(oid)['deadline']
        with patch('superhuman.team.objectives.time.time', return_value=deadline + 1):
            with self.assertRaisesRegex(budget.BudgetBlocked, 'wall-time'):
                self.reserve()
            self.assertIn('wall-time', work.gate(store.task(self.task))[1])
        self.assertEqual(objectives.get(oid)['usage']['requests'], 0)

    def test_business_project_pause_blocks_objective_provider_calls(self):
        oid = self.objective()
        project = store.project(self.project)
        store.update_project(self.project, project['version'], 'P2', 'routine', 'internal', 'paused')
        with self.assertRaisesRegex(budget.BudgetBlocked, 'business project'):
            self.reserve()
        self.assertEqual(objectives.get(oid)['usage']['requests'], 0)

    def test_pause_during_local_preparation_prevents_provider_invocation(self):
        from superhuman.organisation import store as organisation
        oid = self.objective()
        original = organisation.receipt
        def pause(*args, **kwargs):
            result = original(*args, **kwargs)
            objectives.control(oid, objectives.get(oid)['version'], 'pause', 'Pause before provider call')
            return result
        client = Client({'reply': 'Must never be requested'})
        with patch.object(organisation, 'receipt', side_effect=pause), budget.scope('marketing', self.task):
            with self.assertRaisesRegex(budget.BudgetBlocked, 'paused'):
                budget.wrap(client).chat.completions.create(model=MODEL,
                    messages=[{'role': 'user', 'content': 'Synthetic request'}], max_completion_tokens=100)
        self.assertEqual(client.calls, 0)
        self.assertEqual(objectives.get(oid)['usage']['requests'], 1)
        self.assertEqual(objectives.get(oid)['usage']['cost'], 0)

    def test_dispatch_is_sequential_even_when_team_capacity_is_two(self):
        self.objective()
        child = store.create_task(self.project, 'career_rnd', 'Second assignment', 'Calculate', 'Evidence',
                                   objective_id=objectives.memberships()[self.task])
        self.ready()
        self.ready(child)
        work.dispatch(self.task, store.task(self.task)['version'])
        with self.assertRaisesRegex(ValueError, 'sequential'):
            work.dispatch(child, store.task(child)['version'])
        self.assertIsNone(store.task(child)['run_id'])

    def test_plan_history_and_revisions_are_cumulative(self):
        oid = self.objective(revisions=1)
        obj = objectives.get(oid)
        objectives.revise_plan(oid, obj['version'], 'New owner brief', 'New criteria', 'Old scope superseded')
        obj = objectives.get(oid)
        self.assertEqual([plan['version'] for plan in obj['plans']], [1, 2])
        self.assertEqual(obj['revisions_used'], 1)
        with self.assertRaisesRegex(ValueError, 'revision allowance'):
            objectives.revise_plan(oid, obj['version'], 'Another brief', 'Criteria', 'Further change')

    def test_owner_review_cannot_bypass_objective_revision_allowance(self):
        oid = self.objective(revisions=0)
        self.finish()
        task = store.task(self.task)
        with self.assertRaisesRegex(ValueError, 'revision allowance'):
            work.review(self.task, task['version'], False, 'Revise output', actor='owner')
        self.assertEqual(store.task(self.task)['state'], 'awaiting_review')
        self.assertEqual(store.task(self.task)['attempts'], 0)
        self.assertEqual(objectives.get(oid)['revisions_used'], 0)

    def test_completed_task_does_not_automatically_complete_objective(self):
        oid = self.objective()
        self.finish()
        work.review(self.task, store.task(self.task)['version'], True, 'Output checked', actor='owner')
        obj = objectives.get(oid)
        self.assertEqual(obj['state'], 'active')
        objectives.control(oid, obj['version'], 'complete', 'Recorded criteria are satisfied by the accepted output')
        self.assertEqual(objectives.get(oid)['state'], 'completed')
        event = next(e for e in store.audit() if e['action'] == 'objective_complete')
        self.assertFalse(json.loads(event['detail_json'])['business_outcome_measured'])

    def test_objective_coordinator_calls_are_charged_to_same_allowance(self):
        oid = self.objective()
        client = Client(twin('assign', store.task(self.task)))
        result = engine.tick(client=client)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(store.task(self.task)['state'], 'ready')
        self.assertEqual(objectives.get(oid)['usage']['requests'], 1)
        with p.connect() as db:
            self.assertEqual(db.execute('SELECT task_id FROM team_costs').fetchone()[0], self.task)

    def test_assignment_execution_and_twin_review_share_one_persistent_allowance(self):
        oid = self.objective()
        engine.tick(client=Client(twin('assign', store.task(self.task))))
        dispatched = engine.tick(client=Client({}))
        self.assertEqual(dispatched['status'], 'dispatched')
        rid = store.task(self.task)['run_id']
        p.run_one(rid, client=Client(decision()))
        aid = agent.get(rid)['actions'][0]['id']
        p.run_one(rid, client=Client(decision(True, [aid])))
        work.refresh()
        with p.connect() as db:
            db.execute('UPDATE team_settings SET next_due=0')
        result = engine.tick(client=Client(twin('approve', store.task(self.task))))
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(store.task(self.task)['state'], 'completed')
        self.assertEqual(p.get(rid)['used_calls'], 2)
        self.assertEqual(objectives.get(oid)['usage']['requests'], 4)
        self.assertEqual(len(budget.report()['costs']), 4)
        self.assertEqual(objectives.get(oid)['state'], 'active')

    def test_shared_coordinator_cannot_bypass_objective_accounting(self):
        self.objective()
        with self.assertRaisesRegex(ValueError, 'scoped objective'):
            engine.apply(twin('assign', store.task(self.task)))
        self.assertEqual(store.task(self.task)['state'], 'queued')

    def test_objective_signals_do_not_leak_into_shared_coordinator(self):
        self.objective()
        with patch('superhuman.foundation.proactive.twin_signals', return_value=[{
                'id': 'synthetic', 'episode': 1, 'state': 'open', 'entity': self.task}]):
            _, body, actionable = engine.snapshot()
        self.assertEqual(body['proactive_signals'], [])
        self.assertFalse(actionable)

    def test_objective_wait_cache_prevents_repeated_idle_requests(self):
        oid = self.objective()
        engine.tick(client=Client(twin('wait')))
        with p.connect() as db:
            db.execute('UPDATE team_settings SET next_due=0')
        client = Client(twin('wait'))
        self.assertIsNone(engine.tick(client=client))
        self.assertEqual(client.calls, 0)
        self.assertEqual(objectives.get(oid)['usage']['requests'], 1)

    def test_coordinator_cannot_target_other_objective_and_only_local_objective_is_held(self):
        oid = self.objective()
        foreign = store.create_task(self.project, 'marketing', 'Independent legacy', 'Other', 'Criteria')
        result = engine.tick(client=Client(twin('assign', store.task(foreign))))
        self.assertEqual(result['status'], 'interrupted')
        self.assertEqual(objectives.get(oid)['state'], 'held')
        self.assertFalse(store.settings()['hold'])
        self.assertEqual(store.task(foreign)['state'], 'queued')

    def test_owner_routes_require_login_and_csrf_and_show_cumulative_usage(self):
        from fastapi.testclient import TestClient
        from superhuman.hosted import auth, config, web
        settings = config.Settings('https://objective.example.test', state_dir=Path('hosted'))
        auth.Store(settings.auth_db).setup('owner', 'synthetic-test-passphrase')
        with TestClient(web.create_app(settings), base_url=settings.public_origin) as client:
            url = '/team/tasks/' + self.task + '/objective'
            payload = dict(version=store.task(self.task)['version'], cost_limit='1', max_requests=20,
                           max_seconds=3600, max_revisions=2, note='Explicit owner limits')
            self.assertEqual(client.get('/team/objectives', follow_redirects=False).status_code, 303)
            token = lambda response: re.search(r'name="csrf" value="([^"]+)"', response.text).group(1)
            csrf = token(client.get('/login'))
            client.post('/login', data={'username': 'owner', 'password': 'synthetic-test-passphrase', 'csrf': csrf})
            self.assertEqual(client.post(url, data=payload, follow_redirects=False).status_code, 403)
            payload['csrf'] = token(client.get('/team/tasks/' + self.task))
            response = client.post(url, data=payload, follow_redirects=False)
            self.assertEqual(response.status_code, 303, response.text)
            page = client.get(response.headers['location'])
            self.assertIn('Charged or reserved', page.text)
            self.assertIn('Plan history', page.text)
            self.assertEqual(len(objectives.listing()), 1)


if __name__ == '__main__':
    unittest.main()
