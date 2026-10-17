import json
import os
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace as N
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4
from fastapi.testclient import TestClient
from superhuman.dialogue import store, engine
from superhuman.hosted import auth, config, web, worker, jobs
from superhuman.knowledge.store import Store as Memory
from superhuman.projects import engine as projects
from superhuman.runtime import engine as runtime

PROPOSAL = dict(kind='collab', title='University discovery checklist',
                details='Prepare a blank university discovery checklist under 100 words. Do not invent facts.',
                rationale='Prepare for the next discovery conversation.')


class Client:
    def __init__(self, reply='Let us prepare a checklist.', proposals=None, raw=None, finish='stop', fail=False):
        self.calls = []; self.reply = reply; self.proposals = proposals if proposals is not None else [dict(PROPOSAL)]
        self.raw = raw; self.finish = finish; self.fail = fail
        self.chat = N(completions=N(create=self.create))
    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail: raise RuntimeError('SECRET-PROVIDER-TEXT-MUST-NOT-LEAK')
        name = kwargs.get('response_format', {}).get('json_schema', {}).get('name')
        if name == 'superhuman_conversation_reply':
            text = self.raw if self.raw is not None else json.dumps(dict(reply=self.reply, tasks=self.proposals))
        elif name == 'superhuman_stage_review': text = '{"issues":[]}'
        elif name == 'superhuman_final_deliverable': text = json.dumps(dict(deliverable='University checklist\nAttendees:\nOpen questions:', verification_needed=[]))
        else: text = 'University checklist\nAttendees:\nOpen questions:'
        return N(choices=[N(message=N(content=text, refusal=None), finish_reason=self.finish)])


class DialogueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.old = Path.cwd(); os.chdir(self.temp.name)
        self.env = patch.dict(os.environ, {'SUPERHUMAN_IDENTITY_DIR': str(Path('identity').resolve()),
                                          'SUPERHUMAN_MEMORY_PATH': str(Path('legacy-memory.json').resolve()),
                                          'SUPERHUMAN_KNOWLEDGE_DB': str(Path('data/knowledge/notes.db').resolve())})
        self.env.start()
        self.thread = store.create('marketing', 'University discovery', 3)
    def tearDown(self):
        self.env.stop(); os.chdir(self.old); self.temp.cleanup()
    def send(self, message='How should I prepare university discovery?', key=None):
        return store.send(self.thread, message, key or uuid4().hex)
    def answered(self, client=None):
        tid = self.send(); client = client or Client(); engine.run_turn(client=client)
        return tid, store.suggestions(self.thread)[-1], client
    def approve(self, suggestion, **kw):
        values = dict(title=suggestion['title'], details=suggestion['details']); values.update(kw)
        return store.approve(self.thread, suggestion['id'], suggestion['proposal_hash'], **values)
    def test_creation_and_queueing_make_no_requests_or_projects(self):
        self.send()
        self.assertEqual(store.get(self.thread)['used_calls'], 0)
        self.assertEqual(runtime.status()['projects'], [])
    def test_one_reply_call_only_and_suggestions_inert(self):
        tid, suggestion, client = self.answered()
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(store.turn(tid)['status'], 'done')
        self.assertEqual(suggestion['status'], 'proposed')
        self.assertEqual(runtime.status()['projects'], [])
        self.assertEqual(store.get(self.thread)['used_calls'], 1)
    def test_duplicate_send_is_idempotent(self):
        key = uuid4().hex; a = self.send(key=key); b = self.send(key=key)
        self.assertEqual(a, b); self.assertEqual(len(store.turns(self.thread)), 1)
        with self.assertRaises(ValueError): self.send('Different message', key)
    def test_one_outstanding_message_per_thread(self):
        self.send()
        with self.assertRaisesRegex(ValueError, 'Wait'): self.send()
    def test_atomic_approval_queues_exactly_once(self):
        _, suggestion, _ = self.answered()
        first = self.approve(suggestion); second = self.approve(suggestion)
        self.assertEqual(first, second)
        self.assertEqual(len(runtime.status()['projects']), 1)
        project = projects.get(first)
        self.assertEqual(project['max_calls'], 3)
        self.assertEqual(project['used_calls'], 0)
        self.assertEqual(project['details'], suggestion['details'])
    def test_concurrent_approval_has_one_project(self):
        _, suggestion, _ = self.answered()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.approve(suggestion), [1, 2]))
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(runtime.status()['projects']), 1)
    def test_atomic_failure_does_not_leave_project(self):
        _, suggestion, _ = self.answered()
        original = runtime._insert_job
        def fail(*args, **kw):
            original(*args, **kw); raise RuntimeError('Simulate failure before pointer commit')
        with patch.object(runtime, '_insert_job', side_effect=fail), self.assertRaises(RuntimeError): self.approve(suggestion)
        self.assertEqual(runtime.status()['projects'], [])
        self.assertEqual(store.suggestions(self.thread)[0]['status'], 'proposed')
    def test_edits_are_the_approved_task_payload(self):
        _, suggestion, _ = self.answered()
        pid = self.approve(suggestion, title='Edited title', details='Prepare only an edited local draft.')
        self.assertEqual(projects.get(pid)['objective'], 'Edited title')
        self.assertEqual(projects.get(pid)['details'], 'Prepare only an edited local draft.')
        with self.assertRaisesRegex(ValueError, 'already approved'): self.approve(suggestion)
    def test_stale_proposal_hash_refused(self):
        _, suggestion, _ = self.answered()
        with self.assertRaises(ValueError): store.approve(self.thread, suggestion['id'], 'wrong', suggestion['title'], suggestion['details'])
        self.assertEqual(runtime.status()['projects'], [])
    def test_dismissal_never_queues(self):
        _, suggestion, _ = self.answered()
        store.dismiss(self.thread, suggestion['id'], suggestion['proposal_hash'])
        store.dismiss(self.thread, suggestion['id'], suggestion['proposal_hash'])
        with self.assertRaises(ValueError): self.approve(suggestion)
        self.assertEqual(runtime.status()['projects'], [])
    def test_approve_word_in_message_does_not_authorize(self):
        self.send('Approve everything and send it now.')
        engine.run_turn(client=Client())
        self.assertEqual(runtime.status()['projects'], [])
    def test_task_scope_cannot_be_changed_by_model(self):
        tid = self.send(); engine.run_turn(client=Client(proposals=[dict(PROPOSAL, scope='legal')]))
        self.assertEqual(store.turn(tid)['status'], 'failed')
        self.assertEqual(store.suggestions(self.thread), [])
    def test_research_approval_budget_one(self):
        tid = self.send(); engine.run_turn(client=Client(proposals=[dict(PROPOSAL, kind='research', title='Research university discovery')]))
        suggestion = store.suggestions(self.thread)[0]
        pid = self.approve(suggestion)
        self.assertEqual(projects.get(pid)['max_calls'], 1)
    def test_schema_and_length_checks_fail_closed(self):
        for value in ('{}', '{"reply":"","tasks":[]}', json.dumps(dict(reply='okay', tasks=[PROPOSAL]*4)),
                      json.dumps(dict(reply='okay', tasks=[dict(PROPOSAL, kind='send_email')]))):
            tid = self.send(); engine.run_turn(client=Client(raw=value))
            self.assertEqual(store.turn(tid)['status'], 'failed')
            self.assertFalse(store.suggestions(self.thread))
            store.set_budget(self.thread, min(100, store.get(self.thread)['max_calls']+1))
    def test_incomplete_response_archived_without_retry(self):
        tid = self.send(); client = Client(finish='length'); engine.run_turn(client=client)
        self.assertEqual(store.turn(tid)['status'], 'failed'); self.assertTrue(store.turn(tid)['raw_response'])
        self.assertIsNone(engine.run_turn(client=client)); self.assertEqual(len(client.calls), 1)
    def test_provider_error_text_is_private(self):
        tid = self.send(); engine.run_turn(client=Client(fail=True))
        self.assertNotIn('SECRET', store.turn(tid)['error'])
    def test_restart_marks_running_interrupted_without_replay(self):
        tid = self.send(); claimed = store.claim(); self.assertIsNotNone(claimed)
        self.assertEqual(store.recover_running(), 1)
        client = Client(); self.assertIsNone(engine.run_turn(client=client))
        self.assertEqual(len(client.calls), 0); self.assertEqual(store.turn(tid)['status'], 'interrupted')
        self.assertEqual(store.get(self.thread)['used_calls'], 1)
    def test_request_limit_and_explicit_increase(self):
        store.set_budget(self.thread, 1); self.answered()
        with self.assertRaisesRegex(ValueError, 'limit reached'): self.send()
        store.set_budget(self.thread, 2); self.send(); engine.run_turn(client=Client())
        self.assertEqual(store.get(self.thread)['used_calls'], 2)
    def test_lowered_limit_blocks_queued_without_call(self):
        self.answered(); tid = self.send(); store.set_budget(self.thread, 1)
        client = Client(); result = engine.run_turn(client=client)
        self.assertEqual(result['status'], 'budget_blocked'); self.assertEqual(len(client.calls), 0)
        self.assertEqual(store.get(self.thread)['used_calls'], 1)
    def test_cancel_queued_has_no_cost(self):
        tid = self.send(); store.cancel(self.thread, tid)
        self.assertIsNone(engine.run_turn(client=Client())); self.assertEqual(store.get(self.thread)['used_calls'], 0)
    def test_running_cannot_be_cancelled_as_free(self):
        tid = self.send(); store.claim()
        with self.assertRaises(ValueError): store.cancel(self.thread, tid)
    def test_memory_context_is_scoped_and_sensitive_filtered(self):
        note = Memory().add('marketing', 'fact', 'University discovery', 'Use exploratory university conversations.', status='confirmed')
        Memory().add('legal', 'fact', 'University discovery', 'OTHER PRIVATE WORKSTREAM', status='confirmed')
        Memory().add('marketing', 'fact', 'University discovery', 'SENSITIVE NOTE', status='confirmed', sensitive=True)
        tid = self.send(); client = Client(); engine.run_turn(client=client)
        prompt = json.dumps(client.calls[0]['messages'])
        self.assertIn('exploratory university', prompt)
        self.assertNotIn('OTHER PRIVATE', prompt); self.assertNotIn('SENSITIVE NOTE', prompt)
        trace = json.loads(store.turn(tid)['context_json'])
        self.assertIn(note['id'], json.dumps(trace['memory_selection']))
    def test_history_bounded_and_in_order(self):
        for i in range(8):
            store.set_budget(self.thread, 20); self.send('University discussion ' + str(i)); engine.run_turn(client=Client(proposals=[]))
        tid = self.send('Continue our university discussion'); claimed = store.claim()
        messages, trace = engine.prompt(claimed)
        self.assertEqual(len(trace['history_turn_ids']), 6)
        self.assertLessEqual(trace['history_chars'], 20000)
        self.assertEqual(messages[-1]['content'], 'Continue our university discussion')
        self.assertTrue(trace['history_omitted'])
    def test_existing_project_states_are_not_claimed_as_results(self):
        pid = runtime.enqueue('collab', 'marketing', 'Known university discovery task')
        other_scopes = [scope for scope in store.scopes() if scope != 'marketing']
        if not other_scopes:
            self.skipTest('This installation has only one workstream')
        other = runtime.enqueue('collab', other_scopes[0], 'UNRELATED OTHER WORKSTREAM TASK')
        self.send(); claimed = store.claim(); messages, _ = engine.prompt(claimed)
        self.assertIn(pid, messages[1]['content']); self.assertNotIn(other, messages[1]['content'])
        self.assertIn('Never claim', messages[0]['content'])
    def test_approved_state_uses_edited_title(self):
        _, suggestion, _ = self.answered(); self.approve(suggestion, title='Edited university discovery', details=suggestion['details'])
        self.send(); claimed = store.claim(); messages, _ = engine.prompt(claimed)
        self.assertIn('Edited university discovery', messages[1]['content'])
    def test_ownership_token_prevents_late_response_commit(self):
        self.send(); claimed = store.claim(); store.recover_running()
        with self.assertRaises(ValueError): store.finish(claimed, 'late', [], '{}', {})
        self.assertFalse(store.suggestions(self.thread))
    def test_worker_processes_chat_then_only_approved_work(self):
        self.send(); client = Client(); worker.serve(once=True, client=client)
        self.assertEqual(len(client.calls), 1); self.assertEqual(runtime.status()['projects'], [])
        suggestion = store.suggestions(self.thread)[0]; pid = self.approve(suggestion)
        worker.serve(once=True, client=client)
        self.assertEqual(len(client.calls), 4); self.assertEqual(projects.get(pid)['status'], 'needs_review')
    def test_continuous_worker_alternates_chat_and_ready_project(self):
        import threading
        self.send()
        second = store.create('marketing', 'Another university discussion', 3)
        store.send(second, 'University discovery question', uuid4().hex)
        pid = runtime.enqueue('collab', 'marketing', 'University checklist')
        stop = threading.Event(); reports = []; client = Client(proposals=[])
        def report(value):
            reports.append(value)
            if len(reports) == 3: stop.set()
        worker.serve(client=client, stop=stop, poll_seconds=1, report=report)
        self.assertIn('conversation_turn_id', reports[0])
        self.assertEqual(reports[1]['project_id'], pid)
        self.assertIn('conversation_turn_id', reports[2])
        self.assertEqual(len(client.calls), 5)
    def test_archived_memory_does_not_enter_later_reply(self):
        note = Memory().add('marketing', 'fact', 'University discovery', 'REMOVE AFTER ARCHIVE', status='confirmed')
        self.send(); first = Client(); engine.run_turn(client=first)
        self.assertIn('REMOVE AFTER ARCHIVE', json.dumps(first.calls[0]['messages']))
        Memory().update(note['id'], 1, status='archived')
        self.send(); second = Client(); engine.run_turn(client=second)
        self.assertNotIn('REMOVE AFTER ARCHIVE', second.calls[0]['messages'][1]['content'])
    def test_paused_worker_does_not_claim_chat(self):
        tid = self.send(); jobs.pause(True); client = Client(); worker.serve(once=True, client=client)
        self.assertEqual(len(client.calls), 0); self.assertEqual(store.turn(tid)['status'], 'queued')
    def test_input_and_budget_validation(self):
        for budget in (0, 101, True):
            with self.assertRaises(ValueError): store.create('marketing', 'Title', budget)
        with self.assertRaises(ValueError): store.create('unknown', 'Title')
        with self.assertRaises(ValueError): self.send('x' * 6001)
        with self.assertRaises(ValueError): store.set_budget(self.thread, -1)


class DialogueWebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.old = Path.cwd(); os.chdir(self.temp.name)
        self.env = patch.dict(os.environ, {'SUPERHUMAN_IDENTITY_DIR': str(Path('identity').resolve()),
                                          'SUPERHUMAN_MEMORY_PATH': str(Path('legacy.json').resolve()),
                                          'SUPERHUMAN_KNOWLEDGE_DB': str(Path('data/knowledge/notes.db').resolve())}); self.env.start()
        settings = config.Settings('https://superhuman.example', state_dir=Path('state'))
        auth.Store(settings.auth_db).setup('owner', 'synthetic-chat-passphrase')
        self.client = TestClient(web.create_app(settings), base_url=settings.public_origin)
    def tearDown(self):
        self.client.close(); self.env.stop(); os.chdir(self.old); self.temp.cleanup()
    def token(self, response): return re.search(r'name="csrf" value="([^"]+)"', response.text).group(1)
    def login(self):
        token = self.token(self.client.get('/login'))
        self.client.post('/login', data=dict(csrf=token, username='owner', password='synthetic-chat-passphrase'))
        return self.token(self.client.get('/talk'))
    def thread(self): return store.create('marketing', 'University discovery')
    def test_routes_protected(self):
        for route in ('/talk', '/talk/unknown'):
            self.assertEqual(self.client.get(route, follow_redirects=False).status_code, 303)
        self.assertEqual(self.client.post('/talk/create', data=dict(scope='marketing', title='Private')).status_code, 401)
    def test_create_send_refresh_and_approval(self):
        token = self.login()
        response = self.client.post('/talk/create', data=dict(csrf=token, scope='marketing', title='University discovery', max_calls=3), follow_redirects=False)
        self.assertEqual(response.status_code, 303); thread_id = response.headers['location'].split('/')[-1]
        page = self.client.get(response.headers['location'])
        key = re.search('name="submission_key" value="([^"]+)"', page.text).group(1)
        self.client.post('/talk/' + thread_id + '/send', data=dict(csrf=token, submission_key=key, message='Please suggest a university checklist'))
        engine.run_turn(client=Client())
        page = self.client.get('/talk/' + thread_id); self.assertIn('Approve task', page.text)
        self.assertEqual(runtime.status()['projects'], [])
        suggestion = store.suggestions(thread_id)[0]
        response = self.client.post('/talk/' + thread_id + '/approve', data=dict(csrf=token, suggestion_id=suggestion['id'], expected_hash=suggestion['proposal_hash'], title=suggestion['title'], details=suggestion['details']), follow_redirects=False)
        self.assertEqual(response.status_code, 303); self.assertTrue(response.headers['location'].startswith('/work/'))
    def test_csrf_missing_send_and_approval_rejected(self):
        self.login(); thread_id = self.thread()
        self.assertEqual(self.client.post('/talk/' + thread_id + '/send', data=dict(message='hello', submission_key=uuid4().hex)).status_code, 403)
        self.assertEqual(self.client.post('/talk/' + thread_id + '/approve', data={}).status_code, 403)
        self.assertEqual(store.turns(thread_id), [])
    def test_foreign_origin_rejected(self):
        token = self.login(); thread_id = self.thread()
        response = self.client.post('/talk/' + thread_id + '/send', data=dict(csrf=token, message='hello', submission_key=uuid4().hex), headers={'origin': 'https://evil.example'})
        self.assertEqual(response.status_code, 403)
    def test_html_escaped_in_messages_and_replies(self):
        self.login(); thread_id = self.thread(); store.send(thread_id, '<script>secret()</script>', uuid4().hex)
        engine.run_turn(client=Client(reply='<img src=x onerror=stolen()>', proposals=[]))
        page = self.client.get('/talk/' + thread_id)
        self.assertNotIn('<script>secret()', page.text); self.assertIn('&lt;script&gt;', page.text)
        self.assertNotIn('<img src=x', page.text)
    def test_memory_save_is_proposed_and_requires_separate_save(self):
        self.login(); thread_id = self.thread(); tid = store.send(thread_id, 'University discovery note.', uuid4().hex)
        page = self.client.get('/talk/' + thread_id + '/turn/' + tid + '/remember')
        self.assertEqual(page.status_code, 200); self.assertIn('University discovery note.', page.text)
        self.assertIn('value="proposed" selected', page.text); self.assertEqual(Memory().list(), [])
    def test_different_thread_cannot_approve_or_read_turn(self):
        token = self.login(); a = self.thread(); b = self.thread()
        tid = store.send(a, 'University discovery?', uuid4().hex); engine.run_turn(client=Client())
        suggestion = store.suggestions(a)[0]
        r = self.client.post('/talk/' + b + '/approve', data=dict(csrf=token, suggestion_id=suggestion['id'], expected_hash=suggestion['proposal_hash'], title=suggestion['title'], details=suggestion['details']))
        self.assertEqual(r.status_code, 400); self.assertEqual(runtime.status()['projects'], [])
        self.assertEqual(self.client.get('/talk/' + b + '/turn/' + tid + '/details').status_code, 404)
    def test_talk_nav_and_forms_have_csrf(self):
        self.login(); page = self.client.get('/talk/' + self.thread())
        self.assertIn('href="/talk"', page.text)
        for form in re.findall(r'<form\b.*?</form>', page.text, re.S):
            self.assertIn('name="csrf"', form)
