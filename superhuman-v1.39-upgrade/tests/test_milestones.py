"""Real execution, scoped sharing, layered review and owner strategic gates."""
import io,json,os,re,time,unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from test_workspace import WorkspaceBase
from test_team import Metered,MODEL
from test_agentic import decision
from superhuman.projects import engine as p
from superhuman.team import store as team,work,engine as twin,budget
from superhuman.agentic import store as agent
from superhuman.experience import store as ux,chat
from superhuman.dialogue import store as dialogue
from superhuman.foundation import storage
from superhuman.capabilities import local
from superhuman.milestones import store as s,workflow as w,engine as e
from superhuman.milestones.pdf import read_pages,coverage,note
from superhuman.hosted import auth,config,web

class MilestoneBase(WorkspaceBase):
    def setUp(self):
        super().setUp();s.initialize();budget.create_period(10,3,5,1);budget.set_rate(MODEL,'.1','.2','Synthetic rates');budget.set_rate('gpt-4o-mini','.1','.2','Synthetic rates');team.configure(team.settings()['version'],True,MODEL)
    def project(self,scope='marketing',workers=None,reviewers=(),confirmed=True):
        pid=team.create_project(scope,'Project '+uuid4().hex[:6],'Evidence-backed objective','Reviewable outcome');s.attach(pid,scope);mid=s.add(pid,'Validate proposition','What is supported?','A clear supported result',workers or [scope],reviewers);s.configure(pid,s.managed(pid)['version'],True,True)
        if confirmed:s.confirm_criteria(mid,s.milestone(mid)['version'])
        return pid,mid
    def start(self,mid):s.start(mid,s.milestone(mid)['version'])
    def complete(self,tid,extra=(),final_text=None):
        t=team.task(tid);rid=work.dispatch(tid,t['version'])
        if extra:
            for name,args in extra:p.run_one(rid,client=Metered(decision(name,args)))
        else:p.run_one(rid,client=Metered(decision()))
        actions=agent.get(rid)['actions'];ids=[a['id'] for a in actions if a['status'] in ('succeeded','cached')]
        final=decision(action='finish',evidence=ids)
        if final_text:final['final_message']=final_text
        p.run_one(rid,client=Metered(final));work.refresh();return team.task(tid)
    def lead(self,mid):return next(a for a in s.assignments(mid) if a['role']=='lead')
    def packet(self,mid):
        for a in s.assignments(mid):
            if a['role']=='contributor':
                t=self.complete(a['task_id']);w.review_assignment(t['id'],t['version'],True,'Evidence and criteria checked',s.managed(t['project_id'])['lead'])
        self.complete(self.lead(mid)['task_id']);w.submit(mid,s.milestone(mid)['version']);return s.packet(mid)
    def tick(self,action,deliverable=''):
        with p.connect() as db:db.execute('UPDATE milestone_projects SET next_due=0')
        return e.tick(client=Metered({'action':action,'note':'Checked actual output against the milestone criteria.','deliverable':deliverable}))
    def pdf(self,pages=8,scope='endorsement',sensitivity='internal'):
        raw=io.BytesIO();c=canvas.Canvas(raw)
        for n in range(1,pages+1):c.drawString(50,800,'Guide page '+str(n)+' with meaningful business planning requirements.');c.showPage()
        c.save();local.store_bytes(scope,'guide.pdf',raw.getvalue());return storage.save(scope,'document','Owner endorsement guide',filename='guide.pdf',source='Owner-provided guide',sensitivity=sensitivity,status='approved')

class MilestoneTests(MilestoneBase):
    def test_seed_is_atomic_idempotent_paused_and_exact_roster(self):
        pid=s.seed_endorsement();self.assertEqual(s.seed_endorsement(),pid);self.assertEqual(len(s.listing(pid)),7);self.assertEqual(team.project(pid)['status'],'paused');self.assertFalse(s.managed(pid)['enabled']);self.assertFalse(team.tasks());self.assertTrue(all(not m['criteria_confirmed'] for m in s.listing(pid)))
        ms=s.listing(pid);self.assertEqual(json.loads(ms[1]['workers']),['marketing']);self.assertEqual(set(json.loads(ms[2]['workers'])),{'endorsement','edsync_product','career_rnd'});self.assertIn('twin',json.loads(ms[3]['workers']));self.assertEqual(json.loads(ms[3]['reviewers']),['marketing'])
    def test_lead_is_department_specialist(self):
        pid=team.create_project('marketing','P','O','C')
        with self.assertRaises(ValueError):s.attach(pid,'endorsement')
    def test_existing_open_tasks_require_organisation_first(self):
        pid=team.create_project('marketing','P','O','C');team.create_task(pid,'marketing','Old task','I','C')
        with self.assertRaises(ValueError):s.attach(pid,'marketing')
    def test_sharing_consent_required_before_enable(self):
        pid,mid=self.project();cfg=s.managed(pid)
        with self.assertRaises(ValueError):s.configure(pid,cfg['version'],True,False)
    def test_start_creates_canonical_assignments_and_dependency(self):
        pid,mid=self.project(workers=['marketing','career_rnd']);self.start(mid);a=s.assignments(mid);self.assertEqual(len(a),2);lead=self.lead(mid);child=next(x for x in a if x['role']=='contributor');self.assertEqual(json.loads(team.task(lead['task_id'])['deps']),[child['task_id']]);self.assertFalse(work.gate(team.task(lead['task_id']))[0])
        with self.assertRaises(ValueError):s.start(mid,1)
    def test_stale_start_and_foreign_dependencies_rejected(self):
        pid,mid=self.project()
        with self.assertRaises(ValueError):s.start(mid,1)
        other,dep=self.project()
        with self.assertRaises(ValueError):s.add(pid,'Wrong','Question','Criteria',['marketing'],deps=[dep])
    def test_generic_twin_does_not_plan_or_review_managed_project(self):
        pid,mid=self.project();self.start(mid);_,body,_=twin.snapshot();self.assertFalse(any(q['id']==pid for q in body['projects']));self.assertFalse(any(t['project_id']==pid for t in body['tasks']))
        with self.assertRaises(ValueError):team.create_task(pid,'marketing','Unlinked','I','C',actor='twin')
    def test_managed_proactive_signals_do_not_enter_legacy_twin_planning(self):
        from superhuman.foundation import proactive
        pid,mid=self.project();proactive.configure('next_action',1,True,1,'twin_review');proactive.scan(force=True);self.assertTrue(any(r['entity']==pid for r in proactive.twin_signals()));_,body,_=twin.snapshot();self.assertFalse(any(r['entity']==pid for r in body['proactive_signals']))
    def test_only_approved_roster_can_receive_work(self):
        pid,mid=self.project();self.start(mid)
        with self.assertRaises(ValueError):s.create_assignment(mid,'legal_ops','Unapproved','I','C')
    def test_contributor_full_execution_then_lead_acceptance(self):
        pid,mid=self.project(workers=['marketing','career_rnd']);self.start(mid);a=next(x for x in s.assignments(mid) if x['role']=='contributor');self.complete(a['task_id']);r=self.tick('accept');self.assertEqual(r['status'],'completed');self.assertEqual(team.task(a['task_id'])['state'],'completed');self.assertTrue(work.gate(team.task(self.lead(mid)['task_id']))[0])
    def test_raw_task_and_canonical_review_cannot_skip_milestone_gates(self):
        pid,mid=self.project();self.start(mid);t=self.complete(self.lead(mid)['task_id'])
        with self.assertRaises(ValueError):work.review(t['id'],t['version'],True,'Bypass',actor='owner')
        with self.assertRaises(ValueError):p.review(t['run_id'],'final','approve','Bypass')
    def test_submit_freezes_verified_packet_and_exports(self):
        pid,mid=self.project();self.start(mid);packet=self.packet(mid);self.assertEqual(s.milestone(mid)['state'],'twin_review');self.assertTrue(packet['digest']);self.assertEqual({r['format'] for r in json.loads(packet['exports'])},{'pdf','docx'});w.verify_packet(mid)
    def test_twin_acceptance_is_not_owner_approval(self):
        pid,mid=self.project();self.start(mid);packet=self.packet(mid);r=self.tick('accept');self.assertEqual(r['status'],'completed');self.assertEqual(s.milestone(mid)['state'],'owner_review');self.assertEqual(team.task(self.lead(mid)['task_id'])['state'],'awaiting_review');w.approve(mid,s.milestone(mid)['version'],packet['id'],'Approved strategy');self.assertEqual(s.milestone(mid)['state'],'approved')
    def test_next_milestone_requires_owner_approval(self):
        pid,mid=self.project();nextid=s.add(pid,'Next','Next question','Next criteria',['marketing'],deps=[mid]);self.start(mid);self.packet(mid);self.tick('accept')
        with self.assertRaises(ValueError):self.start(nextid)
        w.approve(mid,s.milestone(mid)['version'],s.packet(mid)['id'],'Approved');self.start(nextid);self.assertEqual(s.milestone(nextid)['state'],'working')
    def test_stale_packet_or_unconfirmed_criteria_cannot_approve(self):
        pid,mid=self.project(confirmed=False);self.start(mid);self.packet(mid)
        with self.assertRaises(ValueError):w.review_packet(mid,s.milestone(mid)['version'],'accept','Not confirmed')
        s.confirm_criteria(mid,s.milestone(mid)['version']);self.tick('accept')
        with self.assertRaises(ValueError):w.approve(mid,s.milestone(mid)['version'],'old-packet','Wrong version')
    def test_two_revision_attempts_then_accept_third_submission(self):
        pid,mid=self.project();self.start(mid);self.packet(mid)
        for n in range(2):
            self.assertEqual(self.tick('revise')['status'],'completed');t=team.task(self.lead(mid)['task_id']);rid=t['run_id'];actions=agent.get(rid)['actions'];p.run_one(rid,client=Metered(decision(action='finish',evidence=[actions[0]['id']])));work.refresh();w.submit(mid,s.milestone(mid)['version'])
        self.assertEqual(s.milestone(mid)['revision_count'],2);self.assertEqual(self.tick('accept')['status'],'completed');self.assertEqual(s.milestone(mid)['state'],'owner_review')
    def test_twin_contribution_requires_independent_reviewer(self):
        pid=team.create_project('marketing','P','O','C');s.attach(pid,'marketing')
        with self.assertRaises(ValueError):s.add(pid,'M','Q','C',['marketing','twin'])
    def test_twin_contribution_and_independent_review_flow(self):
        pid,mid=self.project(scope='endorsement',workers=['endorsement','twin','edsync_product'],reviewers=['marketing']);self.start(mid);a=next(x for x in s.assignments(mid) if x['role']=='contributor');t=self.complete(a['task_id']);self.tick('accept');self.assertFalse(work.gate(team.task(self.lead(mid)['task_id']))[0]);self.tick('contribute','A bounded strategic contribution with explicit uncertainties.');self.assertTrue(s.memo(mid));self.complete(self.lead(mid)['task_id']);self.tick('submit');self.assertEqual(s.milestone(mid)['state'],'specialist_review');self.tick('wait');review=next(a for a in s.assignments(mid) if a['role']=='reviewer');self.complete(review['task_id']);self.tick('accept');self.tick('wait');self.assertEqual(s.milestone(mid)['state'],'twin_review');self.tick('accept');self.assertEqual(s.milestone(mid)['state'],'owner_review')
    def test_changed_source_packet_blocks_review(self):
        pid,mid=self.project();self.start(mid);self.packet(mid);tid=self.lead(mid)['task_id'];run=agent.get(team.task(tid)['run_id']);out=json.loads(run['project']['tasks'][0]['result_json']);Path(out['output']).write_text('Tampered')
        with self.assertRaises(ValueError):w.verify_packet(mid)
    def test_project_material_grant_is_named_versioned_and_scoped(self):
        pid,mid=self.project(scope='endorsement',workers=['endorsement','marketing']);local.store_bytes('endorsement','private.txt',b'Private university pilot evidence');ident=storage.save('endorsement','document','University evidence',filename='private.txt',source='Owner',status='approved',sensitivity='internal');s.share(pid,ident,1,['marketing']);self.assertFalse(storage.search('marketing','university')['items']);self.assertTrue(storage.search('marketing','university',pid)['items']);s.revoke(pid,ident,1);self.assertFalse(storage.search('marketing','university',pid)['items'])
    def test_sharing_cannot_cross_unrelated_projects_or_nonmembers(self):
        pid,mid=self.project();other,om=self.project();ident=storage.save('marketing','fact','Fact',content='Evidence',fact_key='f',source='Owner',status='approved',sensitivity='internal',project_kind='team',project_id=other)
        with self.assertRaises(ValueError):s.share(pid,ident,1,['marketing'])
        ident2=storage.save('marketing','fact','Fact',content='Evidence',fact_key='g',source='Owner',status='approved')
        with self.assertRaises(ValueError):s.share(pid,ident2,1,['legal_ops'])
    def test_project_chat_for_cross_department_member_and_revocation(self):
        pid,mid=self.project(scope='endorsement',workers=['endorsement','marketing']);room=ux.create('marketing','Project discussion','team',pid);dialogue.send(room,'What is our question?',uuid4().hex);claimed=dialogue.claim();messages,trace=chat.prompt(claimed);self.assertIn('project_lead',json.dumps(messages));s.configure(pid,s.managed(pid)['version'],False,False)
        with self.assertRaises(ValueError):chat.validate(claimed,trace)
    def test_guide_required_before_endorsement_start(self):
        pid=s.seed_endorsement();team.update_project(pid,team.project(pid)['version'],'P1','routine','internal','active');s.configure(pid,s.managed(pid)['version'],True,True)
        with self.assertRaises(ValueError):self.start(s.listing(pid)[0]['id'])
    def test_pdf_page_reading_coverage_and_notes(self):
        pid=s.seed_endorsement();team.update_project(pid,team.project(pid)['version'],'P1','routine','internal','active');s.configure(pid,s.managed(pid)['version'],True,True);ident=self.pdf(8);s.share(pid,ident,1,['endorsement','twin'],'required_guide');mid=s.listing(pid)[0]['id'];self.start(mid);child=next(a for a in s.assignments(mid) if a['role']=='contributor');t=self.complete(child['task_id']);w.review_assignment(t['id'],t['version'],True,'Public sources checked','endorsement');self.assertFalse(coverage(mid)[0]['complete']);lead=self.lead(mid);self.complete(lead['task_id'],[('storage.pdf_pages',dict(item_id=ident,start_page=1,end_page=5)),('milestone.note',dict(key='Guide sections',content='Working section notes with page references, not approved facts.',expected_version=0)),('storage.pdf_pages',dict(item_id=ident,start_page=6,end_page=8))]);self.assertTrue(coverage(mid)[0]['complete']);w.submit(mid,s.milestone(mid)['version']);self.assertTrue(s.packet(mid))
    def test_pdf_range_rejects_oversize_and_unauthorised_source(self):
        pid,mid=self.project(scope='endorsement');ident=self.pdf(8);self.start(mid);t=team.task(self.lead(mid)['task_id']);rid=work.dispatch(t['id'],t['version']);run=agent.get(rid)
        with self.assertRaises(ValueError):read_pages(run,ident,1,8)
        with self.assertRaises(ValueError):read_pages(run,ident,9,9)
    def test_partial_pdf_coverage_cannot_submit(self):
        pid=s.seed_endorsement();team.update_project(pid,team.project(pid)['version'],'P1','routine','internal','active');s.configure(pid,s.managed(pid)['version'],True,True);ident=self.pdf(8);s.share(pid,ident,1,['endorsement'],'required_guide');mid=s.listing(pid)[0]['id'];self.start(mid);child=next(a for a in s.assignments(mid) if a['role']=='contributor');t=self.complete(child['task_id']);w.review_assignment(t['id'],t['version'],True,'Checked','endorsement');self.complete(self.lead(mid)['task_id'],[('storage.pdf_pages',dict(item_id=ident,start_page=1,end_page=5))])
        with self.assertRaises(ValueError):w.submit(mid,s.milestone(mid)['version'])
    def test_recovery_holds_project_without_replaying(self):
        pid,mid=self.project();self.start(mid)
        with p.connect() as db:db.execute("INSERT INTO milestone_cycles VALUES('interrupted',?,?,?,'sig','running',NULL,NULL,?,NULL)",(pid,mid,'marketing',p.stamp()))
        e.recover();self.assertTrue(s.managed(pid)['hold']);self.assertIsNone(e.tick(client=Metered()))
    def test_pause_or_previous_gate_blocks_dispatch(self):
        pid,mid=self.project();self.start(mid);s.configure(pid,s.managed(pid)['version'],False,True);self.assertFalse(work.gate(team.task(self.lead(mid)['task_id']))[0])
    def test_working_note_cas_and_scope(self):
        pid,mid=self.project();self.start(mid);t=team.task(self.lead(mid)['task_id']);rid=work.dispatch(t['id'],t['version']);run=agent.get(rid);self.assertEqual(note(run,'section','Notes',0)['version'],1)
        with self.assertRaises(ValueError):note(run,'section','Stale',0)
    def test_output_reader_preserves_project_boundary(self):
        pid,mid=self.project();self.start(mid);self.packet(mid);other,om=self.project();self.start(om);tid=self.lead(om)['task_id'];rid=work.dispatch(tid,team.task(tid)['version'])
        with self.assertRaises(ValueError):w.read_output(agent.get(rid),self.lead(mid)['task_id'])

    def test_changed_revision_can_be_submitted_without_stale_packet_hold(self):
        pid,mid=self.project();self.start(mid);self.packet(mid);self.tick('revise');tid=self.lead(mid)['task_id'];rid=team.task(tid)['run_id'];aid=agent.get(rid)['actions'][0]['id'];d=decision(action='finish',evidence=[aid]);d['final_message']='A materially revised deliverable, with updated conclusions.';p.run_one(rid,client=Metered(d));work.refresh();self.assertEqual(self.tick('submit')['status'],'completed');self.assertEqual(s.packet(mid)['version'],2)
    def test_source_grant_revoked_during_review_holds_without_applying(self):
        pid,mid=self.project();self.start(mid);self.packet(mid)
        def mutate():
            cfg=s.managed(pid);s.configure(pid,cfg['version'],True,False)
            return {'action':'accept','note':'Review result','deliverable':''}
        # Consent revocation is allowed only while disabling coordination.
        def revoke():
            cfg=s.managed(pid);s.configure(pid,cfg['version'],False,False)
            return {'action':'accept','note':'Review result','deliverable':''}
        with p.connect() as db:db.execute('UPDATE milestone_projects SET next_due=0')
        r=e.tick(client=Metered(revoke));self.assertEqual(r['status'],'interrupted');self.assertNotEqual(s.milestone(mid)['state'],'owner_review')
    def test_private_guide_source_uses_private_integration_without_web(self):
        pid=s.seed_endorsement();team.update_project(pid,team.project(pid)['version'],'P1','routine','internal','active');s.configure(pid,s.managed(pid)['version'],True,True);ident=self.pdf(1,sensitivity='confidential');s.share(pid,ident,1,['endorsement'],'required_guide');mid=s.listing(pid)[0]['id'];self.start(mid);child=next(a for a in s.assignments(mid) if a['role']=='contributor');t=self.complete(child['task_id']);w.review_assignment(t['id'],t['version'],True,'Checked public research','endorsement');lead=team.task(self.lead(mid)['task_id']);self.assertEqual(team.effective(lead)['sensitivity'],'confidential');rid=work.dispatch(lead['id'],lead['version']);self.assertNotIn('research.web',agent.get(rid)['allowed_tools']);self.assertEqual(read_pages(agent.get(rid),ident,1,1)['page_count'],1)
    def test_owner_page_review_is_separate_and_version_pinned(self):
        from superhuman.milestones.pdf import record_owner_page_review
        pid=s.seed_endorsement();ident=self.pdf(2);s.share(pid,ident,1,['endorsement'],'required_guide');mid=s.listing(pid)[0]['id'];record_owner_page_review(ident,1,[1,2],'I reviewed the cover and diagrams.');r=coverage(mid)[0];self.assertTrue(r['complete']);self.assertEqual(r['extracted_pages'],0);self.assertEqual(r['owner_reviewed_pages'],2)
        with self.assertRaises(ValueError):record_owner_page_review(ident,2,[1],'Stale review')
    def test_pdf_payload_is_fully_visible_in_action_prompt(self):
        from superhuman.agentic.engine import prompt
        pid,mid=self.project(scope='endorsement');ident=self.pdf(5);self.start(mid);tid=self.lead(mid)['task_id'];rid=work.dispatch(tid,team.task(tid)['version']);p.run_one(rid,client=Metered(decision('storage.pdf_pages',dict(item_id=ident,start_page=1,end_page=5))));messages,_=prompt(agent.get(rid));self.assertIn('Guide page 5',messages[1]['content'])
    def test_rollback_strips_new_tools_and_reinstall_restores_unchanged_permissions(self):
        retired={'storage.pdf_pages','milestone.read_output','milestone.note'}
        before={e['id']:set(json.loads(e['allowed_tools'])) for e in team.employees()};s.pause_for_rollback()
        self.assertTrue(all(not set(json.loads(e['allowed_tools']))&retired for e in team.employees()))
        s.initialize();after={e['id']:set(json.loads(e['allowed_tools'])) for e in team.employees()};self.assertEqual(before,after)
    def test_reinstall_does_not_override_owner_permission_edits_after_rollback(self):
        s.pause_for_rollback()
        with p.connect() as db:db.execute("UPDATE team_employees SET allowed_tools='[]',version=version+1 WHERE id='marketing'")
        s.initialize();self.assertEqual(json.loads(next(e for e in team.employees() if e['id']=='marketing')['allowed_tools']),[])
    def test_workflow_rollback_pause_holds_every_open_assignment(self):
        pid,mid=self.project();self.start(mid);s.pause_for_rollback();self.assertFalse(s.managed(pid)['enabled']);self.assertEqual(team.task(self.lead(mid)['task_id'])['state'],'paused')
    def test_criteria_and_material_changes_do_not_inherit_stale_version(self):
        pid,mid=self.project();self.start(mid)
        with self.assertRaises(ValueError):s.confirm_criteria(mid,1)
        with self.assertRaises(ValueError):s.configure(pid,1,True,True)
    def test_working_notes_are_not_injected_into_other_public_assignments(self):
        pid,mid=self.project(workers=['marketing','career_rnd']);self.start(mid);lead=self.lead(mid);public=next(a for a in s.assignments(mid) if a['role']=='contributor')
        with p.connect() as db:
            db.execute("UPDATE team_tasks SET sensitivity='confidential' WHERE id=?",(lead['task_id'],))
            db.execute("INSERT INTO milestone_notes VALUES(?,'private','CONFIDENTIAL_WORKING_NOTE',1,?)",(lead['task_id'],p.stamp()))
        self.assertNotIn('CONFIDENTIAL_WORKING_NOTE',w.task_context(team.task(public['task_id'])))
    def test_private_prior_packet_is_not_exposed_to_public_research(self):
        pid,mid=self.project();self.start(mid);tid=self.lead(mid)['task_id']
        with p.connect() as db:db.execute("UPDATE team_tasks SET sensitivity='confidential' WHERE id=?",(tid,))
        self.complete(tid,final_text='CONFIDENTIAL_PRIOR_STRATEGY');w.submit(mid,s.milestone(mid)['version']);self.tick('accept');w.approve(mid,s.milestone(mid)['version'],s.packet(mid)['id'],'Approved private strategy')
        nxt=s.add(pid,'Next public research','Investigate public alternatives','C',['career_rnd'],deps=[mid]);self.start(nxt);public=next(a for a in s.assignments(nxt) if a['role']=='contributor');self.assertNotIn('CONFIDENTIAL_PRIOR_STRATEGY',w.task_context(team.task(public['task_id'])));rid=work.dispatch(public['task_id'],team.task(public['task_id'])['version'])
        with self.assertRaises(ValueError):w.read_output(agent.get(rid),tid)
        self.assertEqual(team.effective(team.task(self.lead(nxt)['task_id']))['sensitivity'],'confidential')
    def test_private_contribution_is_not_copied_into_public_lead_context(self):
        pid,mid=self.project(workers=['marketing','career_rnd']);self.start(mid);child=next(a for a in s.assignments(mid) if a['role']=='contributor')
        with p.connect() as db:db.execute("UPDATE team_tasks SET sensitivity='confidential' WHERE id=?",(child['task_id'],))
        t=self.complete(child['task_id'],final_text='PRIVATE_CONTRIBUTION_TEXT');w.review_assignment(t['id'],t['version'],True,'Private result accepted','marketing');lead=team.task(self.lead(mid)['task_id']);self.assertNotIn('PRIVATE_CONTRIBUTION_TEXT',w.task_context(lead))
    def test_model_review_context_obeys_target_privacy_ceiling(self):
        pid,mid=self.project(workers=['marketing','career_rnd']);self.start(mid);child=next(a for a in s.assignments(mid) if a['role']=='contributor');self.complete(child['task_id']);tid=self.lead(mid)['task_id']
        # A private working note is never included in public-result review context.
        with p.connect() as db:db.execute("INSERT INTO milestone_notes VALUES(?,'private','PRIVATE_REVIEW_NOTE',1,?)",(tid,p.stamp()))
        test=self
        class Capture(Metered):
            def create(self,**kw):
                test.assertNotIn('PRIVATE_REVIEW_NOTE',kw['messages'][1]['content']);return super().create(**kw)
        with p.connect() as db:db.execute('UPDATE milestone_projects SET next_due=0')
        r=e.tick(client=Capture({'action':'accept','note':'Verified public contribution','deliverable':''}));self.assertEqual(r['status'],'completed')

    def test_private_work_package_is_explicit_and_keeps_web_disabled(self):
        pid,mid=self.project();self.start(mid);tid=s.create_assignment(mid,'marketing','Private synthesis','Use permitted private sources','C',sensitivity_override='confidential');rid=work.dispatch(tid,team.task(tid)['version']);self.assertNotIn('research.web',agent.get(rid)['allowed_tools'])

    def test_raw_owner_task_creation_cannot_leave_unlinked_work(self):
        pid,mid=self.project()
        with self.assertRaises(ValueError):team.create_task(pid,'marketing','Unlinked owner task','I','C')

class MilestoneWebTests(MilestoneBase):
    def setUp(self):
        super().setUp();self.cfg=config.Settings('https://superhuman.example',state_dir=Path('state'));auth.Store(self.cfg.auth_db).setup('owner','synthetic-test-passphrase');self.client=TestClient(web.create_app(self.cfg),base_url=self.cfg.public_origin);self.client.post('/login',data={'username':'owner','password':'synthetic-test-passphrase','csrf':self.csrf(self.client.get('/login'))})
    def tearDown(self):self.client.close();super().tearDown()
    def csrf(self,r):return re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
    def post(self,url,data,source='/project-leadership'):return self.client.post(url,data=dict(data,csrf=self.csrf(self.client.get(source))),follow_redirects=False)
    def test_pages_and_existing_project_route_are_coherent(self):
        pid,mid=self.project()
        for path in ('/project-leadership','/project-hub/'+pid,'/milestones/'+mid,'/team/projects/'+pid):
            r=self.client.get(path);self.assertEqual(r.status_code,200);self.assertIn('milestone',r.text.lower())
    def test_seed_button_is_idempotent_and_free(self):
        self.assertEqual(self.post('/project-leadership/endorsement',{}).status_code,303);self.assertEqual(self.post('/project-leadership/endorsement',{}).status_code,303);self.assertEqual(len(s.listing()),7);self.assertFalse(team.tasks())
    def test_auth_and_csrf_on_new_routes(self):
        pid,mid=self.project();self.assertEqual(self.client.post('/milestones/'+mid+'/start',data={'expected':2}).status_code,403);self.client.cookies.clear()
        for path in ('/project-leadership','/project-hub/'+pid,'/milestones/'+mid):self.assertEqual(self.client.get(path,follow_redirects=False).status_code,303)
    def test_owner_approval_requires_explicit_checkbox_and_current_packet(self):
        pid,mid=self.project();self.start(mid);packet=self.packet(mid);self.tick('accept');m=s.milestone(mid);data=dict(expected=m['version'],packet_id=packet['id'],note='Approved decision');self.assertEqual(self.post('/milestones/'+mid+'/approve',data).status_code,409);data['confirmed']='yes';self.assertEqual(self.post('/milestones/'+mid+'/approve',data).status_code,303);self.assertEqual(s.milestone(mid)['state'],'approved')
    def test_packet_download_and_history_are_private(self):
        pid,mid=self.project();self.start(mid);packet=self.packet(mid);self.assertEqual(self.client.get('/milestones/'+mid+'/packet.txt').status_code,200);self.assertIn('Historical snapshot',self.client.get('/milestones/'+mid+'/packets/'+packet['id']).text);self.client.cookies.clear();self.assertEqual(self.client.get('/milestones/'+mid+'/packet.txt',follow_redirects=False).status_code,303)
