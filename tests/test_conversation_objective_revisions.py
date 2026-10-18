"""Owner feedback stays on its objective and reaches the real execution adapter."""
import json
import re
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

import test_workforce_objectives as fixtures
from superhuman.projects import engine as p
from superhuman.team import store as team, objectives, work, budget
from superhuman.dialogue import store as dialogue, engine as chat
from superhuman.experience import store as ux
from superhuman.conversationwork import bridge, revisions, execution


class ConversationRevisionTests(unittest.TestCase):
    tearDown = fixtures.ObjectiveTests.tearDown

    def setUp(self):
        fixtures.ObjectiveTests.setUp(self)
        self.independent = self.task
        self.room = ux.create('marketing', 'Synthetic source conversation')
        self.original = 'Please draft a short internal meeting agenda about planning.'
        self.source_turn = dialogue.send(self.room, self.original, uuid4().hex)
        plan = dict(kind='collab', scope='marketing', title='Internal agenda',
                    acceptance='A reviewable agenda', risk='routine', sensitivity='internal')
        result = chat.run_turn(client=fixtures.Client(dict(reply='Acknowledgement', tasks=[], execution=plan)))
        self.assertEqual(result['status'], 'done')
        self.job = bridge.rows(self.room)[0]
        self.task = self.job['task_id']
        self.oid = objectives.create(self.task, team.task(self.task)['version'], '1', 20, 3600, 3, 'Owner limits')
        self.brief = 'Please draft an internal meeting agenda focused on delivery milestones.'
        self.criteria = 'Include three topics and a list of open questions.'
        self.impact = 'Replace the planning focus before any execution; preserve the original request.'
        self.key = uuid4().hex

    def submit(self, **changes):
        values = dict(room_id=self.room, ident=self.oid, expected=objectives.get(self.oid)['version'],
                      room_version=ux.room(self.room)['version'], brief=self.brief, criteria=self.criteria,
                      impact=self.impact, submission_key=self.key)
        values.update(changes)
        return revisions.submit(**values)

    def test_revision_saves_feedback_plan_and_actual_status_without_provider_or_new_work(self):
        before = objectives.get(self.oid)
        calls = dialogue.get(self.room)['used_calls']
        tid = self.submit()
        after = objectives.get(self.oid)
        self.assertEqual(after['plans'][0], before['plans'][0])
        self.assertEqual(after['plans'][1]['brief'], self.brief)
        self.assertEqual(after['plans'][1]['criteria'], self.criteria)
        self.assertEqual(after['revisions_used'], 1)
        for field in ('origin_json', 'started', 'deadline', 'max_cost', 'max_requests', 'max_revisions', 'usage'):
            self.assertEqual(after[field], before[field], field)
        turn = dialogue.turn(tid)
        self.assertEqual(turn['status'], 'done')
        self.assertIn('plan 2 saved', turn['reply'])
        self.assertEqual(json.loads(turn['context_json'])['receipt']['kind'], 'owner_control')
        self.assertEqual(dialogue.get(self.room)['used_calls'], calls)
        self.assertEqual(len(team.tasks()), 2)
        self.assertEqual(len(bridge.rows(self.room)), 1)
        self.assertEqual(bridge.job_for_task(self.task)['request'], self.original)
        self.assertEqual(team.task(self.task)['state'], 'queued')
        self.assertEqual(team.task(self.task)['owner_grant'], 0)
        self.assertEqual(team.task(self.independent)['instruction'], 'Calculate 2+3 and provide action evidence.')

    def test_real_dispatch_adapter_uses_revised_brief_and_criteria(self):
        self.submit()
        work.task_control(self.task, team.task(self.task)['version'], 'approve_start', 'Approve revised work')
        rid = work.dispatch(self.task, team.task(self.task)['version'])
        from superhuman.agentic import store as agent
        decision = execution.decision(agent.get(rid))
        self.assertEqual(decision['tool'], 'draft.create')
        self.assertIn(self.brief, decision['arguments']['instructions'])
        self.assertIn(self.criteria, decision['arguments']['instructions'])
        self.assertNotIn(self.original, decision['arguments']['instructions'])
        self.assertEqual(bridge.job_for_run(rid)['request'], self.original)

    def test_identical_retry_after_progress_returns_same_saved_turn(self):
        expected = objectives.get(self.oid)['version']
        tid = self.submit(expected=expected)
        objectives.control(self.oid, objectives.get(self.oid)['version'], 'pause', 'Pause after saved feedback')
        self.assertEqual(self.submit(expected=expected), tid)
        self.assertEqual(objectives.get(self.oid)['revisions_used'], 1)
        self.assertEqual(len(dialogue.turns(self.room)), 2)
        with self.assertRaisesRegex(ValueError, 'different content'):
            self.submit(expected=expected, criteria='Changed payload')

    def test_stale_second_submission_does_not_consume_another_revision(self):
        expected = objectives.get(self.oid)['version']
        self.submit(expected=expected)
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.submit(expected=expected, submission_key=uuid4().hex)
        self.assertEqual(objectives.get(self.oid)['revisions_used'], 1)

    def test_concurrent_feedback_versions_admit_only_one_revision(self):
        expected = objectives.get(self.oid)['version']
        def submit(key):
            try:
                return self.submit(expected=expected, submission_key=key)
            except ValueError as exc:
                return str(exc)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, [uuid4().hex, uuid4().hex]))
        self.assertEqual(sum('changed' in value for value in results), 1)
        self.assertEqual(objectives.get(self.oid)['revisions_used'], 1)
        self.assertEqual(len(dialogue.turns(self.room)), 2)

    def test_no_revision_after_project_becomes_milestone_managed(self):
        from superhuman.milestones import store as milestones
        milestones.initialize()
        with p.connect() as db:
            columns = [r['name'] for r in db.execute('PRAGMA table_info(milestone_assignments)')]
            self.assertIn('task_id', columns)
            # A minimal synthetic link models work-package enrollment after the
            # objective was created; the migration remains deliberately refused.
            db.execute('INSERT INTO milestone_assignments(task_id,milestone_id,role) VALUES(?,?,?)',
                       (self.task, 'synthetic-milestone', 'worker'))
        with self.assertRaisesRegex(ValueError, 'Milestone revisions'):
            self.submit()

    def test_wrong_room_and_changed_scope_are_refused(self):
        other = ux.create('marketing', 'Unrelated room')
        with self.assertRaisesRegex(ValueError, 'original conversation'):
            self.submit(room_id=other)
        with p.connect() as db:
            db.execute('UPDATE ux_rooms SET project_kind=?,project_id=?,version=version+1 WHERE thread_id=?',
                       ('team', self.project, self.room))
        with self.assertRaisesRegex(ValueError, 'scope changed'):
            self.submit()
        self.assertEqual(objectives.get(self.oid)['current_plan'], 1)

    def test_started_task_cannot_be_revised(self):
        work.task_control(self.task, team.task(self.task)['version'], 'approve_start', 'Start original work')
        work.dispatch(self.task, team.task(self.task)['version'])
        with self.assertRaisesRegex(ValueError, 'Started work'):
            self.submit()
        self.assertEqual(len(dialogue.turns(self.room)), 1)

    def test_cancelled_assignment_cannot_be_revised(self):
        work.task_control(self.task, team.task(self.task)['version'], 'cancel', 'Cancel original work')
        with self.assertRaisesRegex(ValueError, 'Started work'):
            self.submit()
        self.assertEqual(team.task(self.task)['state'], 'cancelled')

    def test_archived_conversation_cannot_be_revised(self):
        from superhuman.teamhub import store as hub
        hub.room_control(self.room, hub.state(self.room)['version'], 'Archived source', True, False, '')
        with self.assertRaisesRegex(ValueError, 'archived'):
            self.submit()
        self.assertEqual(objectives.get(self.oid)['current_plan'], 1)

    def test_changed_room_version_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'scope changed'):
            self.submit(room_version=ux.room(self.room)['version'] + 1)

    def test_another_objective_in_same_room_is_not_revised(self):
        turn = dialogue.send(self.room, 'Please draft a separate internal checklist.', uuid4().hex)
        plan = dict(kind='collab', scope='marketing', title='Separate checklist',
                    acceptance='A checklist', risk='routine', sensitivity='internal')
        chat.run_turn(client=fixtures.Client(dict(reply='Acknowledgement', tasks=[], execution=plan)))
        job = next(j for j in bridge.rows(self.room) if j['turn_id'] == turn)
        other = objectives.create(job['task_id'], team.task(job['task_id'])['version'], '1', 10, 3600, 2, 'Separate limits')
        before = objectives.get(other)
        self.submit()
        self.assertEqual(objectives.get(other), before)

    def test_revised_research_reaches_actual_tool_and_returns_saved_result(self):
        turn = dialogue.send(self.room, 'Please research official public guidance.', uuid4().hex)
        plan = dict(kind='research', scope='marketing', title='Public guidance',
                    acceptance='Cited findings', risk='routine', sensitivity='internal')
        chat.run_turn(client=fixtures.Client(dict(reply='Acknowledgement', tasks=[], execution=plan)))
        job = next(j for j in bridge.rows(self.room) if j['turn_id'] == turn)
        oid = objectives.create(job['task_id'], team.task(job['task_id'])['version'], '1', 10, 3600, 2, 'Research limits')
        revisions.submit(self.room, oid, objectives.get(oid)['version'], ux.room(self.room)['version'],
                         'Please research current official public guidance about business planning.',
                         'Include source dates and distinguish assumptions.', 'Narrow the subject before execution.', uuid4().hex)
        work.task_control(job['task_id'], team.task(job['task_id'])['version'], 'approve_start', 'Approve revised research')
        rid = work.dispatch(job['task_id'], team.task(job['task_id'])['version'])
        calls = []
        def create(**kwargs):
            calls.append(kwargs)
            return fixtures.N(id='synthetic-revised-research', usage=fixtures.N(input_tokens=100, output_tokens=80),
                output_text='Synthetic public research result with source evidence.',
                model_dump=lambda **_: {'output': [{'type': 'web_search_call'}, {'content': [{'annotations': [
                    {'type': 'url_citation', 'url': 'https://www.gov.uk/set-up-business', 'title': 'Synthetic official fixture'}]}]}]})
        p.run_one(rid, client=fixtures.N(responses=fixtures.N(create=create)))
        work.refresh()
        self.assertEqual(len(calls), 1)
        self.assertIn('business planning', str(calls[0]))
        self.assertIn('distinguish assumptions', str(calls[0]))
        saved = bridge.status(job)
        self.assertEqual(saved['status'], 'awaiting_review')
        self.assertIn('Synthetic public research result', saved['text'])
        self.assertEqual(bridge.job_for_task(job['task_id'])['request'], 'Please research official public guidance.')

    def test_exhausted_revisions_leave_feedback_and_work_unchanged(self):
        with p.connect() as db:
            db.execute('UPDATE workforce_objectives SET max_revisions=0 WHERE id=?', (self.oid,))
        with self.assertRaisesRegex(ValueError, 'revision allowance exhausted'):
            self.submit()
        self.assertEqual(len(dialogue.turns(self.room)), 1)
        self.assertEqual(objectives.get(self.oid)['current_plan'], 1)

    def test_inflight_cost_blocks_revision_and_settled_consumption_survives(self):
        with budget.scope('marketing', self.task):
            cost = budget.reserve(fixtures.MODEL, dict(messages=[dict(role='user', content='Synthetic')],
                                  max_completion_tokens=100), 'chat')
        with self.assertRaisesRegex(ValueError, 'in flight'):
            self.submit()
        budget.settle(cost, error='Synthetic uncertain provider outcome')
        before = objectives.get(self.oid)['usage']
        self.submit()
        self.assertEqual(objectives.get(self.oid)['usage'], before)
        self.assertEqual(before['unresolved'], 1)

    def test_pending_reply_cannot_race_with_revision(self):
        dialogue.send(self.room, 'Discuss the plan', uuid4().hex)
        with self.assertRaisesRegex(ValueError, 'pending conversation reply'):
            self.submit()

    def test_plan_and_feedback_rollback_together_on_receipt_failure(self):
        with patch.object(dialogue, 'event', side_effect=RuntimeError('Synthetic receipt failure')):
            with self.assertRaisesRegex(RuntimeError, 'receipt failure'):
                self.submit()
        self.assertEqual(objectives.get(self.oid)['current_plan'], 1)
        self.assertEqual(objectives.get(self.oid)['revisions_used'], 0)
        self.assertEqual(len(dialogue.turns(self.room)), 1)
        self.assertNotEqual(team.task(self.task)['instruction'], self.brief)

    def test_external_actions_and_live_research_cannot_be_added_to_draft(self):
        for brief, criteria in ((self.brief, 'Send the result to a customer'),
                                ('Please look up current official guidance online.', self.criteria)):
            with self.assertRaises(ValueError):
                self.submit(brief=brief, criteria=criteria)
        self.assertEqual(objectives.get(self.oid)['current_plan'], 1)

    def test_reference_without_complete_replacement_work_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'complete explicit'):
            self.submit(brief='Please revise this objective.')
        self.assertEqual(objectives.get(self.oid)['current_plan'], 1)

    def test_public_research_rejects_private_criteria(self):
        with self.assertRaisesRegex(ValueError, 'Private information'):
            revisions.validate_brief('Please research official public guidance.', 'Use my passport number 123456789.',
                                     'research', 'routine', 'internal')

    def test_ordinary_messages_do_not_authorize_a_revision(self):
        dialogue.send(self.room, 'Please change the current objective to another draft.', uuid4().hex)
        result = chat.run_turn(client=fixtures.Client(dict(reply='Use the objective revision control.', tasks=[],
                              execution=dict(kind='none', scope='marketing', title='', acceptance='',
                                             risk='routine', sensitivity='internal'))))
        self.assertEqual(result['status'], 'done')
        self.assertEqual(objectives.get(self.oid)['current_plan'], 1)
        self.assertEqual(len(team.tasks()), 2)

    def test_model_cannot_turn_feedback_into_duplicate_new_work(self):
        dialogue.send(self.room, 'Please revise the objective and draft a shorter agenda.', uuid4().hex)
        plan = dict(kind='collab', scope='marketing', title='A duplicate agenda',
                    acceptance='A shorter agenda', risk='routine', sensitivity='internal')
        result = chat.run_turn(client=fixtures.Client(dict(reply='Changed the objective', tasks=[], execution=plan)))
        self.assertEqual(result['status'], 'done')
        self.assertEqual(len(team.tasks()), 2)
        self.assertEqual(objectives.get(self.oid)['current_plan'], 1)
        self.assertIn('no new work was queued', dialogue.turns(self.room)[-1]['reply'])

    def test_owner_form_requires_login_csrf_and_returns_to_saved_conversation(self):
        from fastapi.testclient import TestClient
        from superhuman.hosted import auth, config, web
        settings = config.Settings('https://revision.example.test', state_dir=Path('hosted'))
        auth.Store(settings.auth_db).setup('owner', 'synthetic-test-passphrase')
        url = f'/team-room/{self.room}/objectives/{self.oid}/revise'
        payload = dict(version=objectives.get(self.oid)['version'], room_version=ux.room(self.room)['version'],
                       brief=self.brief, criteria=self.criteria, impact=self.impact, submission_key=self.key)
        with TestClient(web.create_app(settings), base_url=settings.public_origin) as client:
            self.assertEqual(client.post(url, data=payload, follow_redirects=False).status_code, 401)
            token = lambda response: re.search(r'name="csrf" value="([^"]+)"', response.text).group(1)
            csrf = token(client.get('/login'))
            client.post('/login', data=dict(username='owner', password='synthetic-test-passphrase', csrf=csrf))
            self.assertEqual(client.post(url, data=payload).status_code, 403)
            page = client.get('/team-room/'+self.room)
            self.assertIn('Save objective revision', page.text)
            payload['csrf'] = token(page)
            response = client.post(url, data=payload, follow_redirects=False)
            self.assertEqual(response.status_code, 303, response.text)
            self.assertIn('#turn-', response.headers['location'])
            self.assertIn('plan 2 saved', client.get(response.headers['location']).text)
            self.assertEqual(client.post(url, data=payload, follow_redirects=False).status_code, 303)
            self.assertEqual(objectives.get(self.oid)['revisions_used'], 1)


if __name__ == '__main__':
    unittest.main()
