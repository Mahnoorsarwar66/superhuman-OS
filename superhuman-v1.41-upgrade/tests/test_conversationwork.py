"""Real conversation → assignment → research/draft → saved result, synthetic providers."""
import json,time
from pathlib import Path
from types import SimpleNamespace as N
from uuid import uuid4
from unittest.mock import patch
from test_teamhub import HubBase
from test_team import Metered
from superhuman.projects import engine as p
from superhuman.dialogue import engine as chat,store as d
from superhuman.experience import store as ux
from superhuman.team import store as team,work,budget
from superhuman.conversationwork import bridge
from superhuman.agentic import store as a
from superhuman.hosted import jobs

class ConversationWorkTests(HubBase):
    def setUp(self):super().setUp();bridge.initialize()
    def ask(self,question='Hi Katherine, can you go online to research about the UKVI guidance on the UK Innovator Founder Visa for New Businesses?',kind='research',employee='endorsement',room=None,**changes):
        self.room=room or ux.create(employee,'QA direct work');self.turn=d.send(self.room,question,uuid4().hex)
        plan=dict(kind=kind,scope='endorsement' if employee=='twin' else employee,title='QA public guidance research' if kind=='research' else 'QA local draft',acceptance='A useful reviewable result with clear evidence limitations.',risk='routine',sensitivity='internal');plan.update(changes)
        self.result=chat.run_turn(client=Metered({'reply':'A model acknowledgement, not a claim of execution.','tasks':[],'execution':plan}));return bridge.rows(self.room)
    def start(self,job):
        t=team.task(job['task_id']);self.rid=work.dispatch(t['id'],t['version']);return self.rid
    def research(self,missing=False,error=False):
        self.provider_calls=[]
        def create(**kw):
            self.provider_calls.append(kw)
            if error:raise RuntimeError('Synthetic uncertain provider failure')
            annotations=[] if missing else [{'type':'url_citation','url':'https://www.gov.uk/innovator-founder-visa','title':'Synthetic official source fixture'}]
            return N(id='synthetic-research',usage=N(input_tokens=100,output_tokens=80),output_text='Synthetic QA research findings. Verify current official guidance before relying on any application advice.',model_dump=lambda **_: {'output':[{'type':'web_search_call'},{'content':[{'annotations':annotations}]}]})
        return N(responses=N(create=create),chat=N(completions=N(create=lambda **kw: (_ for _ in ()).throw(AssertionError('Unexpected planning call')))))
    def test_exact_owner_question_queues_without_repeated_approval(self):
        jobs_=self.ask();self.assertEqual(self.result['status'],'done');self.assertEqual(len(jobs_),1);t=team.task(jobs_[0]['task_id']);self.assertEqual(t['owner'],'endorsement');self.assertEqual(t['state'],'ready');self.assertEqual(t['max_calls'],1);self.assertEqual(t['cost_limit'],1000000);self.assertIn('research about the UKVI',t['instruction']);self.assertEqual(d.suggestions(self.room),[])
    def test_research_executes_one_search_returns_same_conversation_with_evidence(self):
        job=self.ask()[0];rid=self.start(job);p.run_one(rid,client=self.research());work.refresh()
        self.assertEqual(p.get(rid)['status'],'needs_review');self.assertEqual(p.get(rid)['used_calls'],1);self.assertEqual(len(self.provider_calls),1)
        item=bridge.status(job);self.assertEqual(item['status'],'awaiting_review');self.assertIn('Synthetic QA research findings',item['text']);self.assertEqual(len(a.get(rid)['actions']),2);work.verify(team.task(job['task_id']))
        self.assertIn('Download saved result',bridge.render(self.turn));self.assertIn('gov.uk',bridge.render(self.turn));self.assertIn('Synthetic QA research findings',json.dumps(bridge.context(self.room)))
    def test_no_private_context_or_local_sources_sent_to_web(self):
        self.ask();job=bridge.rows(self.room)[0];rid=self.start(job)
        from superhuman.capabilities import local
        local.store_bytes('endorsement','private.txt',b'NEVER_EXPORT_PRIVATE_SOURCE')
        from superhuman.organisation import store
        store.save('qa-private-business',0,'QA founder private context','NEVER_EXPORT_SHARED_FOUNDER_CONTEXT','active','Synthetic fixture')
        p.run_one(rid,client=self.research());blob=json.dumps(self.provider_calls)
        self.assertNotIn('NEVER_EXPORT_PRIVATE_SOURCE',blob);self.assertNotIn('NEVER_EXPORT_SHARED_FOUNDER_CONTEXT',blob);self.assertNotIn('Fawad Maqbool',blob);self.assertIn('UKVI',blob)
    def test_missing_citations_holds_and_never_claims_completion(self):
        job=self.ask()[0];rid=self.start(job);p.run_one(rid,client=self.research(missing=True));work.refresh();self.assertEqual(bridge.status(job)['status'],'held');self.assertFalse(bridge.status(job)['text']);self.assertNotIn('Download saved result',bridge.render(self.turn));self.assertEqual(len(self.provider_calls),1)
    def test_provider_uncertainty_retains_budget_and_no_automatic_retry(self):
        job=self.ask()[0];rid=self.start(job);p.run_one(rid,client=self.research(error=True));work.refresh();self.assertEqual(team.task(job['task_id'])['state'],'held');self.assertTrue(any(c['state']=='uncertain' for c in budget.report()['costs']));self.assertIsNone(p.run_one(rid,client=self.research()));self.assertEqual(self.provider_calls,[])
    def test_employee_permission_disabled_blocks_with_explanation(self):
        with p.connect() as db:db.execute("UPDATE team_employees SET allowed_tools='[]' WHERE id='endorsement'")
        job=self.ask()[0];self.assertEqual(job['status'],'blocked');self.assertFalse(job['task_id']);self.assertIn('permission',job['reason']);self.assertIn('has not started',d.turn(self.turn)['reply'])
    def test_team_disabled_and_worker_pause_are_specific(self):
        team.configure(team.settings()['version'],False,team.settings()['model']);job=self.ask()[0];self.assertIn('Team activation',job['reason']);self.assertEqual(team.tasks(),[])
    def test_worker_pause_blocks(self):
        jobs.pause(True);job=self.ask()[0];self.assertIn('worker is paused',job['reason']);self.assertFalse(job['task_id'])
    def test_private_research_not_lowered_or_exported(self):
        job=self.ask(question='Research my passport number 123456789 and my medical record',sensitivity='confidential')[0];self.assertEqual(job['status'],'blocked');self.assertIn('Private',job['reason']);self.assertFalse(job['task_id'])
    def test_nonroutine_work_requires_owner(self):
        job=self.ask(risk='high_risk')[0];self.assertIn('owner decision',job['reason']);self.assertEqual(team.tasks(),[])
    def test_specialist_cannot_delegate_to_someone_else(self):
        job=self.ask(scope='marketing')[0];self.assertIn('employee you addressed',job['reason']);self.assertFalse(job['task_id'])
    def test_twin_can_delegate_explicit_routine_work_to_specialist(self):
        job=self.ask(employee='twin')[0];self.assertEqual(job['employee'],'endorsement');self.assertEqual(team.task(job['task_id'])['owner'],'endorsement')
    def test_no_action_from_discussion_or_quoted_request(self):
        for text in ['What would happen if I asked you to research this?', '> Research the market', 'Do not research anything', 'What is research?']:
            self.assertFalse(bridge.explicit(text))
        self.assertTrue(bridge.explicit('Please research the public guidance'))
    def test_model_cannot_invent_execution_lane_for_discussion(self):
        self.ask(question='Who are your teammates?');self.assertEqual(self.result['status'],'failed');self.assertFalse(bridge.rows(self.room));self.assertEqual(team.tasks(),[])
    def test_worker_channel_reply_never_queues_new_work(self):
        _,_,_,topic=self.channel();from superhuman.teamhub import store as hs,engine as he
        hs.send(topic,'Please research public guidance','direct','marketing',uuid4().hex);he.advance();claimed=d.claim();messages,trace=chat.prompt(claimed);self.assertFalse(bridge.candidate(claimed,trace));d.finish(claimed,'Discussion only',[],'{}',trace);self.assertFalse(bridge.rows())
    def test_repeat_active_request_does_not_duplicate_task(self):
        job=self.ask()[0];room=self.room;self.ask(room=room);self.assertEqual(len(team.tasks()),1);self.assertEqual(len(bridge.rows(room)),1)
    def test_paused_linked_project_cannot_fall_back_to_adhoc(self):
        pid=team.create_project('endorsement','QA paused','QA','QA');q=team.project(pid);team.update_project(pid,q['version'],q['priority'],q['risk'],q['sensitivity'],'paused');room=ux.create('endorsement','QA linked','team',pid);job=self.ask(room=room)[0];self.assertIn('paused',job['reason']);self.assertFalse(job['task_id']);self.assertEqual(len(team.projects()),1)
    def test_cancel_before_dispatch_is_preserved(self):
        job=self.ask()[0];t=team.task(job['task_id']);work.task_control(t['id'],t['version'],'cancel');self.assertEqual(bridge.status(job)['status'],'cancelled')
    def test_progress_signature_changes_after_real_execution(self):
        job=self.ask()[0];before=bridge.signature(self.room);rid=self.start(job);p.run_one(rid,client=self.research());self.assertNotEqual(before,bridge.signature(self.room))
    def test_local_draft_uses_existing_three_request_pipeline(self):
        job=self.ask(question='Please draft a short internal meeting agenda.',kind='collab',employee='marketing')[0];rid=self.start(job)
        values=[{'deliverable':'Internal meeting agenda\nTopics:\nOpen questions:','verification_needed':[]},{'findings':[]},{'deliverable':'Internal meeting agenda\nTopics:\nOpen questions:','verification_needed':[]}]
        from test_memory_generation import Client
        client=Client();p.run_one(rid,client=client);work.refresh();self.assertEqual(p.get(rid)['used_calls'],3);self.assertEqual(bridge.status(job)['status'],'awaiting_review');self.assertTrue(bridge.status(job)['text'])
    def test_research_and_send_does_not_authorise_external_component(self):
        job=self.ask(question='Please research the guidance and send the report to the endorsing body.')[0];self.assertFalse(job['task_id']);self.assertIn('external',job['reason'])
    def test_live_research_cannot_be_substituted_with_uncited_local_draft(self):
        job=self.ask(question='Please go online to research official guidance.',kind='collab')[0];self.assertFalse(job['task_id']);self.assertIn('cannot substitute',job['reason'])
    def test_linked_unconfirmed_interview_not_auto_confirmed(self):
        from superhuman.practice import store as practice
        practice.setup();pid=team.create_project('endorsement','QA unconfirmed','QA','QA');room=ux.create('endorsement','QA linked','team',pid);job=self.ask(room=room)[0];self.assertFalse(job['task_id']);self.assertIn('interview',job['reason']);self.assertEqual(practice.interview(pid)['confirmed_version'],0)
    def test_managed_project_without_working_milestone_does_not_bypass(self):
        pid,mid=self.project(scope='endorsement');room=ux.create('endorsement','QA linked','team',pid);job=self.ask(room=room)[0];self.assertFalse(job['task_id']);self.assertIn('working',job['reason']);self.assertEqual(len(team.projects()),1)
    def test_working_milestone_receives_real_linked_assignment(self):
        from superhuman.milestones import store as ms
        pid,mid=self.project(scope='endorsement');self.start_milestone(mid);room=ux.create('endorsement','QA linked','team',pid);job=self.ask(room=room)[0];self.assertTrue(job['task_id']);self.assertEqual(ms.assignment(job['task_id'])['milestone_id'],mid)
    def start_milestone(self,mid):
        from superhuman.milestones import store as ms
        ms.start(mid,ms.milestone(mid)['version'])
    def test_tool_revoked_after_queue_blocks_dispatch(self):
        job=self.ask()[0]
        with p.connect() as db:db.execute("UPDATE team_employees SET allowed_tools='[]',version=version+1 WHERE id='endorsement'")
        with self.assertRaisesRegex(ValueError,'withdrawn'):self.start(job)
    def test_only_required_tool_is_allowed_on_dispatched_work(self):
        job=self.ask()[0];rid=self.start(job);self.assertEqual(a.get(rid)['allowed_tools'],['research.web']);self.assertEqual(a.get(rid)['required_tools'],['research.web'])
    def test_two_active_requests_per_room_limit(self):
        self.ask(question='Please research topic A');room=self.room;self.ask(question='Please research topic B',room=room);third=self.ask(question='Please research topic C',room=room)[-1];self.assertFalse(third['task_id']);self.assertIn('Two work',third['reason']);self.assertEqual(len(team.tasks()),2)
    def test_archive_after_queue_does_not_start_new_chat_actions(self):
        job=self.ask()[0];from superhuman.teamhub import store as hs
        hs.room_control(self.room,hs.state(self.room)['version'],'QA archived',True,False,'')
        with self.assertRaisesRegex(ValueError,'archived'):d.send(self.room,'Research another topic',uuid4().hex)
    def test_scope_does_not_leak_output_into_other_room(self):
        job=self.ask()[0];rid=self.start(job);p.run_one(rid,client=self.research());other=ux.create('endorsement','Unrelated room');self.assertFalse(bridge.context(other));self.assertNotIn('Synthetic QA research findings',json.dumps(bridge.context(other)))
    def test_rollback_pauses_bridge_work_without_replaying_it(self):
        job=self.ask()[0];rid=self.start(job);before=len(budget.report()['costs']);bridge.quarantine();self.assertEqual(team.task(job['task_id'])['state'],'paused');self.assertEqual(a.get(rid)['state'],'paused');self.assertEqual(len(budget.report()['costs']),before)
    def test_finish_failure_never_repeats_successful_search(self):
        job=self.ask()[0];rid=self.start(job)
        with patch('superhuman.agentic.engine.finish',side_effect=ValueError('Synthetic final validation failure')):p.run_one(rid,client=self.research())
        work.refresh();self.assertEqual(bridge.status(job)['status'],'held');self.assertEqual(len(self.provider_calls),1);self.assertEqual(a.get(rid)['actions'][0]['status'],'succeeded')
    def test_task_creation_failure_rolls_back_collection_and_queue(self):
        with patch.object(team,'create_task',side_effect=ValueError('Synthetic creation fault')):self.ask()
        self.assertEqual(self.result['status'],'failed');self.assertFalse(team.tasks());self.assertFalse(team.projects());self.assertFalse(bridge.rows())
    def test_budget_records_source_intent_and_real_search_separately(self):
        job=self.ask()[0];rid=self.start(job);p.run_one(rid,client=self.research());costs=budget.report()['costs'];self.assertEqual(len(costs),2);self.assertEqual(sum(c['task_id']==job['task_id'] for c in costs),1);self.assertTrue(all(c['actor']=='endorsement' for c in costs))

class ConversationWorkHTTPTests(HubBase):
    ask=ConversationWorkTests.ask
    start=ConversationWorkTests.start
    research=ConversationWorkTests.research
    def setUp(self):
        super().setUp();bridge.initialize()
        from superhuman.hosted import config,auth,web
        from fastapi.testclient import TestClient
        self.cfg=config.Settings('https://superhuman.example',state_dir=Path('state'));auth.Store(self.cfg.auth_db).setup('owner','synthetic-test-passphrase');self.client=TestClient(web.create_app(self.cfg),base_url=self.cfg.public_origin)
        import re
        csrf=re.search(r'name="csrf" value="([^"]+)"',self.client.get('/login').text).group(1);self.client.post('/login',data={'username':'owner','password':'synthetic-test-passphrase','csrf':csrf})
    def tearDown(self):self.client.close();super().tearDown()
    def test_live_fragment_progress_result_and_download(self):
        job=self.ask()[0];before=self.client.get('/room-live/'+self.room).json()['signature'];rid=self.start(job);p.run_one(rid,client=self.research());self.assertNotEqual(before,self.client.get('/room-live/'+self.room).json()['signature'])
        fragment=self.client.get('/room-fragment/'+self.room);self.assertEqual(fragment.status_code,200);self.assertIn('Synthetic QA research findings',fragment.text);self.assertIn('Download saved result',fragment.text)
        artifact=self.client.get('/projects/'+rid+'/tasks/final/download');self.assertEqual(artifact.status_code,200);self.assertIn('Synthetic QA research findings',artifact.text)
    def test_tampered_output_is_not_presented_as_a_result(self):
        job=self.ask()[0];rid=self.start(job);p.run_one(rid,client=self.research());record=json.loads(p.get(rid)['tasks'][0]['result_json']);Path(record['output']).write_text('Tampered synthetic text')
        fragment=self.client.get('/room-fragment/'+self.room);self.assertEqual(fragment.status_code,200);self.assertNotIn('Download saved result',fragment.text);self.assertIn('could not be reverified',fragment.text)
    def test_blocked_search_budget_shows_budget_controls_without_false_result(self):
        job=self.ask()[0];rid=self.start(job)
        with p.connect() as db:db.execute('UPDATE team_budget_periods SET staff_cap=0')
        p.run_one(rid,client=self.research());item=bridge.status(job);self.assertIn('current dollar budget',item['reason']);self.assertFalse(item['text']);self.assertEqual(self.provider_calls,[])
    def test_changed_saved_work_invalidates_followup_reply(self):
        job=self.ask()[0];rid=self.start(job);p.run_one(rid,client=self.research());d.send(self.room,'Explain the saved result',uuid4().hex);claimed=d.claim();messages,trace=chat.prompt(claimed)
        from superhuman.experience.chat import validate
        record=json.loads(p.get(rid)['tasks'][0]['result_json']);Path(record['output']).write_text('Changed after context capture')
        with self.assertRaisesRegex(ValueError,'changed during reply'):validate(claimed,trace)
    def test_local_followup_receives_actual_saved_research(self):
        job=self.ask()[0];rid=self.start(job);p.run_one(rid,client=self.research());room=self.room
        draft=self.ask(question='Please summarize the research report for internal review.',kind='collab',room=room)[-1];drid=self.start(draft)
        from superhuman.conversationwork.execution import decision
        plan=decision(a.get(drid));self.assertIn('Synthetic QA research findings',plan['arguments']['instructions']);self.assertIn(job['task_id'],plan['arguments']['instructions'])
    def test_local_followup_cannot_inherit_a_more_private_result(self):
        job=self.ask()[0];rid=self.start(job);p.run_one(rid,client=self.research());room=self.room
        with p.connect() as db:db.execute("UPDATE team_tasks SET sensitivity='restricted',version=version+1 WHERE id=?",(job['task_id'],))
        draft=self.ask(question='Please summarize the research report for internal review.',kind='collab',room=room)[-1];drid=self.start(draft)
        from superhuman.conversationwork.execution import decision
        self.assertNotIn('Synthetic QA research findings',decision(a.get(drid))['arguments']['instructions'])
    def test_generated_metadata_cannot_leak_private_history_to_search(self):
        self.ask(title='NEVER_FORWARD_PRIVATE_MODEL_TITLE',acceptance='NEVER_FORWARD_PRIVATE_MODEL_CRITERIA');job=bridge.rows(self.room)[0];rid=self.start(job);p.run_one(rid,client=self.research());payload=json.dumps(self.provider_calls);self.assertNotIn('NEVER_FORWARD_PRIVATE_MODEL',payload);self.assertNotIn('NEVER_FORWARD_PRIVATE_MODEL',team.task(job['task_id'])['instruction']);self.assertNotIn('NEVER_FORWARD_PRIVATE_MODEL',team.task(job['task_id'])['acceptance'])
    def test_common_web_requests_and_current_information_questions(self):
        for text in ['Can you search for official guidance?','Please browse the web for current public requirements.','What are the current public requirements?','Please look into the official guidance.']:
            self.assertTrue(bridge.explicit(text),text)
        self.assertFalse(bridge.explicit('What is research?'));self.assertFalse(bridge.explicit('What if I asked you to research?'))
    def test_reviewed_result_does_not_keep_pending_review_label(self):
        job=self.ask()[0];rid=self.start(job);p.run_one(rid,client=self.research());work.refresh();t=team.task(job['task_id']);work.review(t['id'],t['version'],True,'Synthetic routine review of the actual saved result')
        rendered=bridge.render(self.turn);self.assertIn('Routine review completed',rendered);self.assertNotIn('Review pending;',rendered)
    def test_capability_discussion_knows_worker_path_without_enqueuing(self):
        room=ux.create('endorsement','QA capabilities');d.send(room,'What can you do?',uuid4().hex);claimed=d.claim();messages,trace=chat.prompt(claimed);messages,trace=bridge.augment(claimed,messages,trace)
        self.assertIn('public-web research and local drafting',messages[0]['content']);self.assertNotIn('conversation_execution',trace);self.assertFalse(bridge.rows(room))
