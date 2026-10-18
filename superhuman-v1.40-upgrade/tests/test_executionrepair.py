"""Regression cases from the live v1.38 team run. Synthetic providers only."""
import json,re,unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from test_agentic import AgentTests,Client,decision
from test_assurance import AssuranceBase
from test_team import Metered
from test_teamhub import HubBase
from test_liveqa import LiveQAHTTPTests
from superhuman.agentic import engine as ae,store as agent
from superhuman.projects import engine as p
from superhuman.team import store as team,work,budget
from superhuman.collab import delivery,runner
from superhuman.collab.reliability import render_final
from superhuman.milestones import store as ms,engine as me,workflow as mw
from superhuman.assurance import store as assurance,workflow as aw
from superhuman.hosted import auth,config,web
from superhuman.interface import views
from superhuman.interface.tree import parse
from superhuman.dialogue import store as dialogue
from superhuman.experience import store as ux
from superhuman.teamhub import store as hub

class ActionContractTests(unittest.TestCase):
    setUp=AgentTests.setUp;tearDown=AgentTests.tearDown
    runid=AgentTests.runid;step=AgentTests.step;state=AgentTests.state
    def test_legacy_empty_finish_arguments_and_typed_finish_both_work(self):
        for typed in (False,True):
            pid=self.runid();self.step(pid,decision());aid=agent.get(pid)['actions'][0]['id']
            payload=decision(action='finish',evidence=[aid]);payload['arguments_json']=''
            if typed:payload['arguments']={};payload.pop('arguments_json');payload['tool']=''
            self.step(pid,payload);self.assertEqual(self.state(pid),'completed')
    def test_typed_arguments_are_validated_and_empty_tool_string_stays_invalid(self):
        payload=decision();payload['arguments']={'expression':'2+3'};payload.pop('arguments_json')
        pid=self.runid();self.step(pid,payload);self.assertEqual(agent.get(pid)['actions'][0]['status'],'succeeded')
        payload['arguments']={'expression':5};self.step(pid,payload);self.assertEqual(agent.get(pid)['actions'][-1]['status'],'failed')
        payload['tool']='';payload['arguments']={};self.step(pid,payload);self.assertNotEqual(self.state(pid),'completed')
    def test_legacy_invalid_json_does_not_execute_or_get_silently_repaired(self):
        pid=self.runid();payload=decision();payload['arguments_json']='{"expression":"bad\\q"}'
        self.step(pid,payload);a=agent.get(pid)['actions'][0]
        self.assertEqual(a['status'],'failed');self.assertIn('JSON object',json.loads(a['verification_json'])['reason'])
    def test_typed_finish_does_not_accept_hidden_tool_arguments(self):
        payload=decision(action='finish');payload.pop('arguments_json');payload['arguments']={'expression':'1+1'}
        with self.assertRaisesRegex(ValueError,'empty arguments'):ae.parse(json.dumps(payload))
    def test_finish_still_requires_successful_current_evidence(self):
        pid=self.runid();payload=decision(action='finish',evidence=['invented']);payload['arguments_json']=''
        self.step(pid,payload);self.assertNotEqual(self.state(pid),'completed')
    def test_final_exact_artifact_has_separate_provenance_and_consistent_punctuation(self):
        pid=self.runid();self.step(pid,decision());aid=agent.get(pid)['actions'][0]['id']
        payload=decision(action='finish',evidence=[aid]);payload['final_message']='Synthetic QA - QA-TEAM-838\nAttendees:\nCurrent workflows:\nObstacles:\nDecision criteria:\nOpen questions:'
        # Select the confirmed preference through the real identity selector.
        from superhuman.identity.selection import select_context
        def selected(*args,**kw):return {**select_context(*args,**kw),'forbid_dashes':True}
        with patch('superhuman.identity.selection.select_context',side_effect=selected):
            self.step(pid,payload)
        task=p.get(pid)['tasks'][0];result=json.loads(task['result_json']);text=p._text(result)[1]
        self.assertNotIn('Execution evidence',text);self.assertNotIn('Tool results',text)
        self.assertIn('Synthetic QA; QA-TEAM-838',text);self.assertEqual(result['execution_evidence'][0]['action_id'],aid)
        self.assertTrue(result['quality_report']['passes'])
    def test_unmet_final_word_contract_does_not_finish(self):
        pid=agent.create('marketing','Bounded template','At most 2 words.',('calculate',),max_calls=5)
        self.step(pid,decision());aid=agent.get(pid)['actions'][0]['id']
        self.step(pid,decision(action='finish',evidence=[aid]));self.assertNotEqual(self.state(pid),'completed')
    def test_schema_contains_typed_objects_no_encoded_json(self):
        self.assertIn('arguments',ae.SCHEMA['required']);self.assertNotIn('arguments_json',ae.SCHEMA['properties'])
        variants=ae.SCHEMA['properties']['arguments']['anyOf'];self.assertTrue(variants)
        for variant in variants:self.assertFalse(variant['additionalProperties']);self.assertEqual(set(variant['required']),set(variant['properties']))

class GroundedDraftReviewTests(unittest.TestCase):
    setUp=AgentTests.setUp;tearDown=AgentTests.tearDown
    def test_requirement_ids_resolve_to_exact_contract_and_unicode_quotes_normalize(self):
        catalog=delivery.review_contract('Keep the fields blank.\nUse concise labels.')
        value={'issues':[{'category':'format','requirement_id':'R2','evidence':'“Current  workflows”','correction':'Use the requested label.'}]}
        reviewed=delivery.parse_review(json.dumps(value),'"Current workflows"','Keep the fields blank.\nUse concise labels.',catalog)
        self.assertEqual(reviewed['issues'][0]['requirement'],'Use concise labels.')
    def test_invented_id_and_nonexistent_evidence_still_fail(self):
        catalog=delivery.review_contract('Keep blank fields.')
        value={'issues':[{'category':'scope','requirement_id':'R99','evidence':'','correction':'Fix.'}]}
        with self.assertRaisesRegex(ValueError,'invented'):delivery.parse_review(json.dumps(value),'Template','Keep blank fields.',catalog)
        value['issues'][0].update(requirement_id='R1',evidence='Invented customers')
        with self.assertRaisesRegex(ValueError,'does not occur'):delivery.parse_review(json.dumps(value),'Template','Keep blank fields.',catalog)
    def test_three_call_review_uses_catalog_and_records_actual_configured_model(self):
        class DraftClient:
            _team_metered=True
            path=p.DEFAULT_DB
            def __init__(self):
                from types import SimpleNamespace as N
                self.calls=[];self.chat=N(completions=N(create=self.create))
            def create(self,**kw):
                from types import SimpleNamespace as N
                self.calls.append(kw);name=kw.get('response_format',{}).get('json_schema',{}).get('name')
                if name=='superhuman_stage_review':
                    self.schema=kw['response_format']['json_schema']['schema'];value='{"issues":[]}'
                elif name=='superhuman_final_deliverable':value=json.dumps({'deliverable':'Synthetic QA - QA-TEAM-838\nAttendees:\nCurrent workflows:\nObstacles:\nDecision criteria:\nOpen questions:','verification_needed':[]})
                else:value='Synthetic blank checklist'
                return N(choices=[N(message=N(content=value,refusal=None),finish_reason='stop')])
        fake=DraftClient();team.initialize();team.configure(team.settings()['version'],True,'gpt-4o-mini')
        with budget.scope('marketing'):
            result=runner.run_collaboration('Blank checklist','Under 80 words, with blank fields.',project='marketing',client=fake,model='old-environment-model')
        self.assertEqual(len(fake.calls),3);self.assertEqual(result['api_calls'],3);self.assertEqual(result['model'],'gpt-4o-mini')
        self.assertTrue(all(c['model']=='gpt-4o-mini' for c in fake.calls));self.assertTrue(result['quality_report']['passes'])
        self.assertIn('requirement_id',fake.schema['properties']['issues']['items']['properties'])
        self.assertTrue((Path(result['stage_archive'])/'review_contract.json').is_file())
    def test_ascii_dash_normalization_preserves_numeric_range(self):
        text,changes=render_final({'deliverable':'Label - detail\nRange 2 - 3','verification_needed':[]},True)
        self.assertIn('Label; detail',text);self.assertIn('2 - 3',text);self.assertTrue(changes)

class TeamExecutionTests(AssuranceBase):
    def test_all_eight_roles_and_two_milestones_obey_the_review_chain(self):
        workers=['applications','investors_grants','marketing','career_rnd','endorsement','edsync_product','twin']
        pid,mid=self.project(scope='edsync_product',workers=workers,reviewers=['legal_ops']);self.confirm(mid)
        second=ms.add(pid,'Dependent verification','Verify approved prior packet','A concise verification',['edsync_product'],['career_rnd'],deps=[mid]);ms.confirm_criteria(second,ms.milestone(second)['version']);self.confirm(second)
        with self.assertRaisesRegex(ValueError,'Previous'):self.start(second)
        self.start(mid)
        contributors=[a for a in ms.assignments(mid) if a['role']=='contributor'];self.assertEqual(len(contributors),5)
        for a in contributors:
            self.complete(a['task_id'],final_text='Synthetic QA reference QA-TEAM-838.\nAttendees:\nCurrent workflows:\nObstacles:\nDecision criteria:\nOpen questions:')
            response=self.tick('accept');self.assertEqual(response['status'],'completed');self.assertEqual(team.task(a['task_id'])['state'],'completed')
        self.assertFalse(work.gate(team.task(self.lead(mid)['task_id']))[0]);self.tick('contribute','Synthetic scope memo. No real facts or external action.');self.assertTrue(ms.memo(mid))
        self.complete(self.lead(mid)['task_id'],final_text='Synthetic QA reference QA-TEAM-838.\nAttendees:\nCurrent workflows:\nObstacles:\nDecision criteria:\nOpen questions:');self.tick('submit')
        self.assertEqual(ms.milestone(mid)['state'],'specialist_review');self.tick('wait')
        reviewer=next(a for a in ms.assignments(mid) if a['role']=='reviewer');self.assertEqual(reviewer['owner'],'legal_ops');self.complete(reviewer['task_id']);self.score(mid,'legal_ops');self.tick('accept');self.tick('wait')
        self.assertEqual(ms.milestone(mid)['state'],'twin_review')
        values=[dict(criterion=r['criterion'],verdict='pass',rationale='Synthetic fixture reviewed against this exact packet.') for r in assurance.rubric(mid)]
        with p.connect() as db:db.execute('UPDATE milestone_projects SET next_due=0')
        result=me.tick(client=Metered({'action':'accept','note':'All current synthetic packet criteria and independent scores checked.','deliverable':'','scores':values}));self.assertEqual(result['status'],'completed')
        with self.assertRaisesRegex(ValueError,'Previous'):self.start(second)
        packet=ms.packet(mid);mw.approve(mid,ms.milestone(mid)['version'],packet['id'],'QA operator approves synthetic milestone.');self.start(second)
        self.complete(self.lead(second)['task_id']);self.tick('submit');self.tick('wait')
        reviewer=next(a for a in ms.assignments(second) if a['role']=='reviewer');self.complete(reviewer['task_id']);self.score(second,'career_rnd');self.tick('accept');self.tick('wait')
        values=[dict(criterion=r['criterion'],verdict='pass',rationale='Exact current synthetic packet checked.') for r in assurance.rubric(second)]
        with p.connect() as db:db.execute('UPDATE milestone_projects SET next_due=0')
        self.assertEqual(me.tick(client=Metered({'action':'accept','note':'Packet verified for owner review.','deliverable':'','scores':values}))['status'],'completed')
        mw.approve(second,ms.milestone(second)['version'],ms.packet(second)['id'],'Approve synthetic verification.')
        self.assertEqual([m['state'] for m in ms.listing(pid)],['approved','approved']);self.assertEqual(budget.report()['totals']['uncertain'],0)
    def test_ready_contribution_cannot_wait_for_downstream_review(self):
        pid,mid=self.project(scope='edsync_product',workers=['edsync_product','marketing'],reviewers=['legal_ops']);self.confirm(mid);self.start(mid)
        child=next(a for a in ms.assignments(mid) if a['role']=='contributor');self.complete(child['task_id'])
        fake=Metered({'action':'wait','note':'Waiting for Sam review before contribution acceptance.','deliverable':''})
        result=me.tick(client=fake);self.assertEqual(result['status'],'interrupted');self.assertTrue(ms.managed(pid)['hold']);self.assertEqual(team.task(child['task_id'])['state'],'awaiting_review')
        # A nonconforming mock cannot bypass the stage-specific production schema.
        schema=me.decision_schema(mid,'contribution',p.DEFAULT_DB,['accept','revise','escalate'])
        self.assertNotIn('wait',schema['properties']['action']['enum'])
    def test_held_summary_points_to_assignment_and_review_summary_names_lead(self):
        pid,mid=self.project(workers=['marketing','career_rnd']);self.confirm(mid);self.start(mid);child=next(a for a in ms.assignments(mid) if a['role']=='contributor')
        with p.connect() as db:db.execute("UPDATE team_tasks SET state='held' WHERE id=?",(child['task_id'],))
        self.assertIn('Assignment needs inspection',views.milestone_next(mid));self.assertIn('/team/tasks/'+child['task_id'],views.milestone_next(mid))
        with p.connect() as db:db.execute("UPDATE team_tasks SET state='awaiting_review' WHERE id=?",(child['task_id'],))
        self.assertIn('Sarah must review Amelia',views.milestone_next(mid));self.assertNotIn('team is handling',views.milestone_next(mid))
    def test_generic_assignment_names_actual_lead(self):
        pid,mid=self.project(scope='edsync_product',workers=['edsync_product','marketing']);self.confirm(mid);self.start(mid)
        t=team.task(next(a['task_id'] for a in ms.assignments(mid) if a['role']=='contributor'))
        self.assertIn('James (project lead)',t['instruction']);self.assertNotIn('Katherine/the',t['instruction'])
    def test_run_and_parent_resume_are_atomic_on_failure(self):
        pid,mid=self.project();self.confirm(mid);self.start(mid);t=team.task(self.lead(mid)['task_id']);rid=work.dispatch(t['id'],t['version'])
        with p.connect() as db:db.execute("UPDATE team_tasks SET state='held' WHERE id=?",(t['id'],));db.execute("UPDATE agentic_runs SET state='needs_review' WHERE project_id=?",(rid,))
        original=agent.control
        def fail(*args,**kw):original(*args,**kw);raise ValueError('Simulated failure after run state update')
        with patch('superhuman.agentic.store.control',side_effect=fail):
            with self.assertRaisesRegex(ValueError,'Simulated'):work.task_control(t['id'],team.task(t['id'])['version'],'resume','Inspected failed decision; no write occurred.')
        self.assertEqual(agent.get(rid)['state'],'needs_review');self.assertEqual(team.task(t['id'])['state'],'held')
        work.task_control(t['id'],team.task(t['id'])['version'],'resume','Inspected state and authorise bounded retry.')
        self.assertEqual(agent.get(rid)['state'],'ready');self.assertEqual(team.task(t['id'])['state'],'dispatched')
    def test_paused_parent_reason_precedes_stale_interview(self):
        pid,mid=self.project();self.confirm(mid);self.start(mid);t=team.task(self.lead(mid)['task_id'])
        team.update_project(pid,team.project(pid)['version'],'P2','routine','internal','paused')
        self.assertEqual(work.gate(t)[1],'Project is paused or finished')

class ExecutionHTTPTests(HubBase):
    csrf=LiveQAHTTPTests.csrf
    def setUp(self):
        super().setUp();self.cfg=config.Settings('https://superhuman.example',state_dir=Path('state'));auth.Store(self.cfg.auth_db).setup('owner','synthetic-test-passphrase')
        from fastapi.testclient import TestClient
        self.client=TestClient(web.create_app(self.cfg),base_url=self.cfg.public_origin)
        self.client.post('/login',data={'username':'owner','password':'synthetic-test-passphrase','csrf':self.csrf('/login')})
    def tearDown(self):self.client.close();super().tearDown()
    def test_archived_retry_is_absent_in_page_fragment_and_polling_stays_blocked(self):
        rid=ux.create('marketing','QA archive');dialogue.send(rid,'Synthetic question',uuid4().hex)
        turn=dialogue.turns(rid)[0];dialogue.cancel(rid,turn['id']);hub.room_control(rid,hub.state(rid)['version'],'QA archive',True,False,'')
        for url in ['/team-room/'+rid,'/room-fragment/'+rid]:
            body=self.client.get(url).text;self.assertNotIn('Request a fresh reply',body);self.assertIn('Restore this archived conversation',body)
        self.assertFalse(self.client.get('/room-live/'+rid).json()['can_send'])
        response=self.client.post('/room-controls/'+rid+'/retry',data={'turn_id':turn['id'],'submission_key':uuid4().hex,'csrf':self.csrf('/team-room/'+rid)})
        self.assertEqual(response.status_code,409);self.assertEqual(len(dialogue.turns(rid)),1)
    def test_fragment_contains_latest_context_and_usage_poll_is_current(self):
        rid=ux.create('marketing','QA refresh');dialogue.send(rid,'Synthetic prompt',uuid4().hex);self.reply('Synthetic response')
        self.assertEqual(self.client.get('/room-live/'+rid).json()['used'],1)
        body=self.client.get('/room-fragment/'+rid).text;self.assertIn('data-live-context',body);self.assertIn('Context recorded for the latest completed reply',body)
        self.assertIn('data-reply-count',self.client.get('/team-room/'+rid).text)
    def test_execution_page_resume_updates_owning_task_and_stale_parent_refuses(self):
        pid,mid=self.project();self.start(mid);t=team.task(self.lead(mid)['task_id']);rid=work.dispatch(t['id'],t['version'])
        with p.connect() as db:db.execute("UPDATE team_tasks SET state='held' WHERE id=?",(t['id'],));db.execute("UPDATE agentic_runs SET state='needs_review' WHERE project_id=?",(rid,))
        page=self.client.get('/agent-runs/'+rid);self.assertIn('name="team_version"',page.text)
        payload=dict(version=agent.get(rid)['version'],team_version=team.task(t['id'])['version'],action='resume',note='Inspected parse error; no partial write.',csrf=self.csrf('/agent-runs/'+rid))
        stale=dict(payload,team_version=payload['team_version']-1)
        self.assertEqual(self.client.post('/agent-runs/'+rid+'/control',data=stale).status_code,409);self.assertEqual(team.task(t['id'])['state'],'held')
        response=self.client.post('/agent-runs/'+rid+'/control',data=payload,follow_redirects=False);self.assertEqual(response.status_code,303)
        self.assertEqual(team.task(t['id'])['state'],'dispatched');self.assertEqual(agent.get(rid)['state'],'ready')
    def test_failed_action_does_not_offer_verified_download(self):
        pid=agent.create('marketing','QA failed draft','Local only',('calculate',))
        p.run_one(pid,client=Metered(decision()))
        action=agent.get(pid)['actions'][0]
        with p.connect() as db:db.execute("UPDATE agentic_actions SET status='failed',result_json=?,verification_json=? WHERE id=?",(json.dumps({'download_url':'/never-verified-artifact'}),json.dumps({'verified':False,'reason':'Invalid reviewer evidence'}),action['id']))
        body=self.client.get('/agent-runs/'+pid).text;self.assertNotIn('/never-verified-artifact',body.split('Inputs and observation')[0]);self.assertNotIn('Download verified saved artifact</a>',body)
