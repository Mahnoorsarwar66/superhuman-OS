import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch
from superhuman.knowledge.store import Store
from superhuman.collab import runner
from superhuman.projects import engine
from superhuman.research.runner import run_research


class Client:
    def __init__(self, invalid_review=False):
        self.calls = []; self.invalid_review = invalid_review
        self.chat = N(completions=N(create=self.create))
        self.responses = N(create=self.research)
    def create(self, **kwargs):
        self.calls.append(kwargs)
        name = kwargs.get('response_format', {}).get('json_schema', {}).get('name')
        if name == 'superhuman_stage_review':
            text = json.dumps({'issues': [{'category': 'format', 'requirement': 'invented requirement',
                                           'evidence': 'PROGRAM CHECKS is not draft text', 'correction': 'Remove it'}]}) if self.invalid_review else '{"issues":[]}'
        elif name == 'superhuman_final_deliverable':
            text = json.dumps({'deliverable': 'University discovery agenda\nCurrent workflows:\nOpen questions:', 'verification_needed': []})
        elif name == 'superhuman_project_plan':
            text = json.dumps({'tasks': [{'id': 'agenda', 'kind': 'collab', 'title': 'University discovery agenda',
                                          'details': 'Prepare a short agenda.', 'depends_on': [],
                                          'checks': {'max_words': 100, 'required_terms': []}}]})
        else:
            text = 'University discovery agenda\nCurrent workflows:\nOpen questions:'
        return N(choices=[N(message=N(content=text, refusal=None), finish_reason='stop')])
    def research(self, **kwargs):
        self.calls.append(kwargs)
        return N(output_text='University discovery research findings.', model_dump=lambda **unused: {
            'output': [{'content': [{'annotations': [{'type': 'url_citation', 'url': 'https://example.org/source',
                                                      'title': 'Synthetic citation, no network request'}]}]}]})


class MemoryGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.old = Path.cwd(); os.chdir(self.temp.name)
        self.env = patch.dict(os.environ, {'SUPERHUMAN_KNOWLEDGE_DB': str(Path('data/knowledge/notes.db').resolve()),
                                          'SUPERHUMAN_IDENTITY_DIR': str(Path('identity').resolve()),
                                          'SUPERHUMAN_MEMORY_PATH': str(Path('legacy-memory.json').resolve())})
        self.env.start()
        self.note = Store().add('marketing', 'fact', 'University discovery',
                                'University discovery note: distinguish suggestions from commitments.', status='confirmed')
        Store().add('endorsement', 'fact', 'University discovery', 'PRIVATE OTHER WORKSTREAM', status='confirmed')
        Store().add('marketing', 'fact', 'University discovery', 'SENSITIVE EXCLUDED NOTE', status='confirmed', sensitive=True)
    def tearDown(self):
        self.env.stop(); os.chdir(self.old); self.temp.cleanup()
    def test_drafting_uses_note_versions_without_extra_calls(self):
        client = Client()
        record = runner.run_collaboration('University discovery agenda', 'Prepare a short agenda.', project='marketing', client=client)
        self.assertEqual(len(client.calls), 3)
        for call in client.calls:
            prompt = json.dumps(call['messages'])
            self.assertIn('distinguish suggestions from commitments', prompt)
            self.assertNotIn('PRIVATE OTHER WORKSTREAM', prompt)
            self.assertNotIn('SENSITIVE EXCLUDED NOTE', prompt)
        selected = [r for r in record['context_selection']['selected'] if r['kind'] == 'knowledge_fact']
        self.assertEqual(selected[0]['id'], self.note['id'])
        self.assertEqual(selected[0]['version'], 1)
    def test_planning_uses_same_memory_selector(self):
        client = Client(); pid = engine.create('marketing', 'Prepare university discovery agenda', max_calls=8)
        engine.generate_plan(pid, client=client)
        self.assertEqual(len(client.calls), 1)
        self.assertIn('distinguish suggestions from commitments', json.dumps(client.calls[0]['messages']))
        self.assertEqual(engine.get(pid)['status'], 'plan_review')
    def test_research_uses_memory_without_extra_requests(self):
        client = Client()
        result = run_research('University discovery', 'Research sources.', project='marketing', client=client)
        self.assertEqual(len(client.calls), 1)
        self.assertIn('distinguish suggestions from commitments', client.calls[0]['input'])
        self.assertNotIn('SENSITIVE EXCLUDED NOTE', client.calls[0]['input'])
        self.assertEqual(result['context_selection']['knowledge_version'], '1.10.0')
    def test_invalid_reviewer_stays_blocked_with_specific_reason(self):
        client = Client(invalid_review=True)
        result = runner.run_collaboration('University discovery agenda', 'Prepare a short agenda.', project='marketing', client=client)
        self.assertEqual(result['status'], 'quality_blocked')
        self.assertEqual(len(client.calls), 3)
        self.assertIn('invented a requirement', result['quality_report']['reviewer_error_detail'])
        self.assertIn('invented a requirement', '; '.join(result['quality_report']['errors']))
        self.assertTrue((Path(result['stage_archive']) / 'review.txt').exists())
