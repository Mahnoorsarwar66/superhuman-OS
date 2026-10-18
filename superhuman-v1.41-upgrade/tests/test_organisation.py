"""Shared awareness regressions: real DB, request boundary and HTTP; synthetic providers only."""
import json
from types import SimpleNamespace as N
from unittest.mock import patch
from pathlib import Path
from uuid import uuid4
from fastapi.testclient import TestClient
from test_workspace import WorkspaceBase
from superhuman.projects import engine as p
from superhuman.team import store as team,budget
from superhuman.organisation import store,context
from superhuman.experience import store as ux
from superhuman.dialogue import store as dialogue,engine as chat
from superhuman.milestones import store as ms
from superhuman.hosted import web,config,auth

class OrganisationTests(WorkspaceBase):
    def boot(self):
        budget.create_period(10,3,5,1);budget.set_rate('gpt-4o-mini','.1','.2','Synthetic offline rate');store.initialize()
    def fake(self,callback=None,usage=True):
        self.calls=[]
        def call(**kw):
            self.calls.append(kw)
            if callback:callback()
            return N(id='synthetic-org-response',usage=N(prompt_tokens=30,completion_tokens=10) if usage else None,choices=[N(message=N(content=json.dumps({'reply':'A synthetic test reply.','tasks':[]}),refusal=None),finish_reason='stop')])
        return N(chat=N(completions=N(create=call)),responses=N(create=call))
    def call(self,client,actor='twin',question='Who am I and who are your teammates?'):
        with budget.scope(actor):return budget.wrap(client).chat.completions.create(model='gpt-4o-mini',messages=[{'role':'system','content':'Return the requested test schema.'},{'role':'user','content':question}],max_completion_tokens=100)
    def test_all_eight_receive_owner_team_mission_without_user_explanation(self):
        self.boot()
        for actor in ux.NAMES:
            with self.subTest(actor=actor):
                self.call(self.fake(),actor);messages=json.dumps(self.calls[0]['messages'])
                for value in ['Mahnoor Sarwar','Fawad Maqbool','EdSync','The Twin','Jose','Chris','Sam','Sarah','Amelia','James','Katherine','reports_to','team-hierarchy']:self.assertIn(value,messages)
                self.assertEqual(self.calls[0]['messages'][-1]['content'],'Who am I and who are your teammates?')
    def test_no_duplicate_model_request_or_schema_change(self):
        self.boot();self.call(self.fake());self.assertEqual(len(self.calls),1);self.assertEqual(self.calls[0]['max_completion_tokens'],100);self.assertEqual(len(budget.report()['costs']),1)
    def test_seed_dates_uncertainties_and_no_sensitive_import(self):
        data=context.snapshot('twin');blob=json.dumps(data)
        self.assertEqual(len(data['team_directory']),8);self.assertEqual(len(store.seed()),25)
        self.assertEqual(store.get('edsync-traction-history')['status'],'historical');self.assertEqual(store.get('edsync-founder-team')['status'],'unresolved')
        for value in ['Hb 8.3','AHTC-KHI-198','superhuman_replacement','first wife','100 mg/5 ml']:self.assertNotIn(value,blob)
    def test_initialisation_idempotent_preserves_owner_correction(self):
        store.initialize();r=store.get('owner-profile');store.save(r['id'],r['version'],r['title'],'Corrected professional owner profile','active','Owner correction')
        store.initialize();self.assertEqual(store.get(r['id'])['content'],'Corrected professional owner profile');self.assertEqual(len(store.history(r['id'])),2)
    def test_archive_draft_removed_and_unresolved_labeled(self):
        for status in ['draft','archived']:
            store.save('qa-'+status,0,'QA '+status,'EXCLUDED-'+status,status,'Synthetic fixture')
        blob=json.dumps(context.snapshot('twin'));self.assertNotIn('EXCLUDED-draft',blob);self.assertNotIn('EXCLUDED-archived',blob);self.assertIn('unresolved',blob)
    def test_optimistic_edit_and_invalid_values(self):
        store.initialize();r=store.get('owner-profile')
        with self.assertRaisesRegex(ValueError,'changed'):store.save(r['id'],0,'X','Y','active','Owner')
        for ident,status in [('../escape','active'),('ok','confirmed')]:
            with self.assertRaises(ValueError):store.save(ident,0,'X','Y',status,'Owner')
    def test_all_department_instructions_are_live_and_versioned(self):
        from superhuman.supervision import store as supervision
        from superhuman.planning import store as planning
        supervision.save('endorsement',0,'QA live endorsement instructions','Ground claims','review',False,1,False,20,8,8,['calculate'])
        planning.save_goal('endorsement',0,'QA live goal','high','','QA acceptance')
        data=context.snapshot('twin','Can you review instructions inside the UK Innovator Founder department?');row=next(r for r in data['department_records'] if r['id']=='endorsement')
        self.assertEqual(row['supervision']['mission'],'QA live endorsement instructions');self.assertEqual(row['supervision']['version'],1);self.assertEqual(row['plan']['objective']['text'],'QA live goal')
        self.assertEqual(row['citation'],'ORG:endorsement')
        self.assertNotIn('last_summary',row['supervision'])
    def test_missing_instructions_explicit_not_fabricated(self):
        row=next(r for r in context.snapshot('twin','UK Innovator instructions')['department_records'] if r['id']=='endorsement')
        self.assertIn('supervision',row['missing']);self.assertIsNone(row['supervision'])
    def test_department_update_after_provider_blocks_result_with_metered_charge(self):
        self.boot()
        def change():
            employee=next(e for e in team.employees() if e['id']=='endorsement')
            with p.connect() as db:db.execute('UPDATE team_employees SET charter=?,version=version+1 WHERE id=?',('Changed charter','endorsement'))
        with self.assertRaisesRegex(ValueError,'changed during'):self.call(self.fake(change),question='UK Innovator department instructions')
        with p.connect() as db:row=db.execute('SELECT state FROM org_context_receipts').fetchone();self.assertEqual(row['state'],'stale_context')
        self.assertEqual(budget.report()['costs'][0]['state'],'metered')
    def test_memory_correction_during_provider_call_blocks_stale_result(self):
        self.boot()
        def change():
            r=store.get('owner-profile');store.save(r['id'],r['version'],r['title'],'New owner profile','active','Owner')
        with self.assertRaisesRegex(ValueError,'changed during'):self.call(self.fake(change))
    def test_budget_blocked_before_provider_and_receipt(self):
        client=self.fake()
        with self.assertRaises(budget.BudgetBlocked):self.call(client)
        self.assertEqual(self.calls,[])
    def test_unknown_usage_stays_reserved(self):
        self.boot();self.call(self.fake(usage=False));row=budget.report()['costs'][0];self.assertEqual(row['state'],'uncertain');self.assertEqual(row['reserved_text'],row['charged_text'])
    def test_receipt_failure_before_provider_releases_no_call(self):
        self.boot();client=self.fake()
        with patch.object(store,'receipt',side_effect=OSError('Synthetic disk error')):
            with self.assertRaises(OSError):self.call(client)
        self.assertEqual(self.calls,[]);self.assertEqual(budget.report()['costs'][0]['charged_text'],0)
    def test_request_snapshot_is_immutable_after_edit_and_cost_linked(self):
        self.boot();self.call(self.fake());r=store.get('owner-profile');store.save(r['id'],r['version'],r['title'],'New owner profile','active','Owner')
        with p.connect() as db:receipt=dict(db.execute('SELECT * FROM org_context_receipts').fetchone())
        data=json.loads(receipt['snapshot']);old=next(x for x in data['shared_professional_memory'] if x['id']==r['id']);self.assertEqual(old['version'],1);self.assertEqual(receipt['cost_id'],budget.report()['costs'][0]['id'])
    def managed(self,title='QA shared project',sensitivity='internal',workers=None):
        pid=team.create_project('marketing',title,'Synthetic shared objective','Synthetic acceptance',sensitivity=sensitivity);ms.attach(pid,'marketing');ms.add(pid,'QA milestone','QA question','QA acceptance',workers or ['marketing','career_rnd']);ms.configure(pid,ms.managed(pid)['version'],False,True);return pid
    def test_project_visibility_respects_roster_and_classification(self):
        visible=self.managed();private=self.managed('CONFIDENTIAL PROJECT',sensitivity='confidential');foreign=self.managed('FOREIGN PROJECT',workers=['marketing'])
        data=context.snapshot('career_rnd','current projects');self.assertEqual([r['id'] for r in data['permitted_project_summaries']],[visible]);self.assertNotIn(private,json.dumps(data));self.assertNotIn(foreign,json.dumps(data))
        self.assertEqual(len(data['permitted_project_summaries'][0]['milestones']),1)
    def test_project_context_never_includes_another_project(self):
        a=self.managed();b=self.managed('ANOTHER PROJECT')
        data=context.snapshot('twin','projects',project_id=a,project_kind='team');self.assertEqual([r['id'] for r in data['permitted_project_summaries']],[a]);self.assertNotIn(b,json.dumps(data))
    def test_sharing_revocation_updates_context(self):
        pid=self.managed();before=context.snapshot('twin','projects');ms.configure(pid,ms.managed(pid)['version'],False,False)
        self.assertFalse(context.snapshot('twin','projects')['permitted_project_summaries']);self.assertNotEqual(before['signature'],context.snapshot('twin','projects')['signature'])
    def test_private_employee_memory_and_messages_not_in_shared_context(self):
        team.add_memory('twin','fact','PRIVATE_EMPLOYEE_SECRET','twin_private','restricted');team.add_message('instruction','PRIVATE_OWNER_MESSAGE')
        blob=json.dumps(context.snapshot('marketing','team instructions'));self.assertNotIn('PRIVATE_EMPLOYEE_SECRET',blob);self.assertNotIn('PRIVATE_OWNER_MESSAGE',blob)
    def test_owner_revision_propagates_on_next_call(self):
        self.boot();self.call(self.fake(),'marketing');r=store.get('owner-profile');store.save(r['id'],r['version'],r['title'],'NEW_SHARED_PROFILE','active','Owner')
        self.call(self.fake(),'career_rnd');self.assertIn('NEW_SHARED_PROFILE',json.dumps(self.calls[0]['messages']))
    def test_research_endpoint_receives_shared_identity_and_keeps_tool_bounds(self):
        self.boot();client=self.fake()
        with budget.scope('marketing'):budget.wrap(client).responses.create(model='gpt-4o-mini',instructions='Research public facts only',input='Synthetic research question',tools=[{'type':'web_search'}],max_tool_calls=1,max_output_tokens=100)
        self.assertIn('Mahnoor Sarwar',self.calls[0]['input']);self.assertEqual(self.calls[0]['max_tool_calls'],1);self.assertEqual(self.calls[0]['tools'],[{'type':'web_search'}])
    def test_fresh_dialogue_records_context_receipt(self):
        self.boot();rid=ux.create('twin','QA fresh awareness');dialogue.send(rid,'Do you know about your teammates?',uuid4().hex)
        self.assertEqual(chat.run_turn(client=self.fake())['status'],'done');trace=json.loads(dialogue.turns(rid)[0]['context_json']);self.assertEqual(trace['organisation']['actor'],'twin');self.assertIn('cost_id',trace['organisation']);self.assertIn('The Twin',json.dumps(self.calls))
    def test_bounded_context_discloses_omissions_and_preserves_json(self):
        for i in range(20):store.save('bulk-'+str(i),0,'Bulk','x'*5900,'active','Synthetic test')
        data=context.snapshot('twin');self.assertTrue(data['omitted_memory_ids']);self.assertLess(len(store.encode(data)),85000);self.assertEqual(json.loads(store.encode(data))['schema_version'],1)
    def test_read_only_preview_does_not_create_tasks_or_costs(self):
        self.boot();before=budget.report()['costs'];context.snapshot('twin','projects and department instructions');self.assertEqual(budget.report()['costs'],before);self.assertEqual(team.tasks(),[])

class OrganisationHTTPTests(WorkspaceBase):
    def client(self):
        from superhuman.hosted.config import Settings
        settings=Settings('https://superhuman.example',state_dir=Path('state'))
        owner=auth.Store(settings.auth_db);owner.setup('owner','synthetic-password-12345');token,session=owner.new_session()
        client=TestClient(web.create_app(settings),base_url=settings.public_origin);client.cookies.set(auth.COOKIE,token);return client,session
    def test_owner_pages_and_save_history(self):
        client,session=self.client();r=client.get('/shared-memory');self.assertEqual(r.status_code,200);self.assertIn('Shared foundation',r.text)
        record=store.get('owner-profile');values={k:record[k] for k in ('id','title','content','status','source','source_date','review_on','category')};values['ident']=values.pop('id');values.update(expected=record['version'],shared_confirmed='yes',csrf=session['csrf']);values['content']='QA corrected professional identity'
        r=client.post('/shared-memory/save',data=values);self.assertEqual(r.status_code,200);self.assertIn('QA corrected professional identity',r.text);self.assertEqual(len(store.history(record['id'])),2)
        self.assertEqual(client.post('/shared-memory/save',data=values).status_code,409)
        self.assertEqual(client.get('/shared-memory/preview?employee=twin&q=department+instructions').status_code,200)
    def test_confirmation_auth_and_html_escape(self):
        client,session=self.client();store.save('qa-xss',0,'<script>QA</script>','<img src=x onerror=alert(1)>','draft','Synthetic')
        self.assertIn('&lt;script&gt;',client.get('/shared-memory').text);self.assertNotIn('<img src=x',client.get('/shared-memory').text)
        data=dict(ident='qa-new',expected=0,title='QA',content='QA',status='active',source='Owner',csrf=session['csrf'])
        self.assertEqual(client.post('/shared-memory/save',data=data).status_code,409)
        client.cookies.clear();self.assertIn('/login',client.get('/shared-memory',follow_redirects=False).headers.get('location',''))
