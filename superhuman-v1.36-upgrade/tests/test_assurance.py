"""Stage 2 tests exercise real task evidence and strategic approval boundaries."""
import io,json,time
from datetime import timedelta
from unittest.mock import patch
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from test_milestones import MilestoneBase
from test_team import Metered
from superhuman.projects import engine as p
from superhuman.team import store as team,work
from superhuman.milestones import store as ms,workflow as mw,engine as me
from superhuman.foundation import storage
from superhuman.capabilities import local
from superhuman.hosted import config,web,auth
from superhuman.assurance import store as s,evidence as ev,workflow as f,investigations as inv,tools,outcomes as out

class AssuranceBase(MilestoneBase):
    def project(self,*args,**kw):
        pid,mid=super().project(*args,**kw);s.setup();return pid,mid
    def confirm(self,mid):s.confirm(mid,s.policy(mid)['version'],'Reviewed the actual requirement scope; no additional separate requirements needed for this synthetic deliverable.')
    def source(self,pid,content='Synthetic pilot count is 12.',sensitivity='internal'):
        scope=team.project(pid)['scope']
        return storage.save(scope,'fact','Synthetic evidence',content=content,fact_key='test.'+str(time.time_ns()),project_kind='team',project_id=pid,sensitivity=sensitivity,access=['twin'],source='Synthetic owner-provided test record',status='approved')
    def supported(self,pid,mid):
        req=s.add_requirement(mid,'test.claim','Validate synthetic pilot count',True,'Synthetic guide section 1');sid=self.source(pid)
        ident=ev.add(req,'storage',sid,'Synthetic pilot count is 12.','section 1','This test record supports the pilot count; not a real business fact.')
        ev.review(ident,1,'accepted','Exact quotation, relevance and test scope checked');self.confirm(mid);return req,sid,ident
    def score(self,mid,actor='twin',verdict='pass'):
        packet=ms.packet(mid);values=[dict(criterion=r['criterion'],verdict=verdict,rationale='Checked the actual criterion against this exact packet and current source evidence.') for r in s.rubric(mid)]
        return f.scorecard(mid,packet['id'],packet['digest'],values,actor)
    def accepted(self,mid):
        self.score(mid);mw.review_packet(mid,ms.milestone(mid)['version'],'accept','Current evidence and full quality rubric meet the criteria');packet=ms.packet(mid);mw.approve(mid,ms.milestone(mid)['version'],packet['id'],'Approve this synthetic strategic milestone');return packet

class RegisterTests(AssuranceBase):
    def test_setup_idempotent_no_jobs_or_budget_changes(self):
        pid,mid=self.project();before=len(team.tasks());s.setup();self.assertEqual(len(team.tasks()),before);self.assertEqual(len(s.rubric(mid)),5);self.assertFalse(s.policy(mid)['register_confirmed'])
    def test_new_milestone_receives_register(self):
        pid,mid=self.project();new=ms.add(pid,'Second','Question','Criteria',['marketing'],deps=[mid]);self.assertIsNotNone(s.policy(new))
    def test_old_approval_is_labelled_historical(self):
        pid,mid=super(AssuranceBase,self).project();self.start(mid);self.packet(mid);self.tick('accept');mw.approve(mid,ms.milestone(mid)['version'],ms.packet(mid)['id'],'Prior stage approval');s.setup();self.assertTrue(s.policy(mid)['legacy']);self.assertEqual(ms.milestone(mid)['state'],'approved')
    def test_in_review_migration_blocks_for_new_gates(self):
        pid,mid=super(AssuranceBase,self).project();self.start(mid);self.packet(mid);s.setup();self.assertTrue(f.block_reason(mid));s.setup();self.assertEqual(len(s.changes(pid)),1)
    def test_requirement_key_is_idempotent_and_content_checked(self):
        pid,mid=self.project();a=s.add_requirement(mid,'claim','Must verify',True,'Guide section');self.assertEqual(a,s.add_requirement(mid,'claim','Must verify',True,'Guide section'))
        with self.assertRaises(ValueError):s.add_requirement(mid,'claim','Different',True,'Guide section')
    def test_outside_roster_cannot_add_requirement(self):
        pid,mid=self.project()
        with self.assertRaises(ValueError):s.add_requirement(mid,'claim','Must verify',True,'Guide',actor='legal_ops')
    def test_stale_scope_confirmation_rejected(self):
        pid,mid=self.project();v=s.policy(mid)['version'];s.add_requirement(mid,'claim','Verify',False,'Guide')
        with self.assertRaises(ValueError):s.confirm(mid,v,'Old view')
    def test_critical_requirement_blocks_unsubstantiated_packet(self):
        pid,mid=self.project();s.add_requirement(mid,'claim','Unsupported',True,'Guide');self.confirm(mid);self.start(mid);self.complete(self.lead(mid)['task_id'])
        with self.assertRaisesRegex(ValueError,'Critical requirement'):mw.submit(mid,ms.milestone(mid)['version'])
    def test_quote_must_exist_and_evidence_starts_proposed(self):
        pid,mid=self.project();req=s.add_requirement(mid,'claim','Count',True,'Guide');sid=self.source(pid)
        with self.assertRaises(ValueError):ev.add(req,'storage',sid,'Invented 99 pilots','section 1','Not grounded')
        eid=ev.add(req,'storage',sid,'Synthetic pilot count is 12.','section 1','Supports test count');self.assertEqual(s.evidence(mid)[0]['status'],'proposed')
        with self.assertRaisesRegex(ValueError,'Critical'):self.confirm(mid);f.gate(mid)
    def test_source_access_requires_lead_and_twin_grants(self):
        pid,mid=self.project();req=s.add_requirement(mid,'claim','Count',True,'Guide')
        sid=storage.save('marketing','fact','Unshared',content='Private number 10',fact_key='unshared',source='Test',sensitivity='confidential',status='approved')
        with self.assertRaisesRegex(ValueError,'Grant'):ev.add(req,'storage',sid,'Private number 10','section 1','Needs private sharing')
    def test_foreign_project_source_rejected(self):
        pid,mid=self.project();other,om=self.project();sid=self.source(other);req=s.add_requirement(mid,'claim','Count',True,'Guide')
        with self.assertRaises(ValueError):ev.add(req,'storage',sid,'Synthetic pilot count is 12.','section 1','Foreign')
    def test_contested_critical_evidence_blocks_even_with_accepted(self):
        pid,mid=self.project();req,sid,eid=self.supported(pid,mid);sid2=self.source(pid,'Synthetic pilot count is disputed.');other=ev.add(req,'storage',sid2,'Synthetic pilot count is disputed.','section 2','Contradicts count');ev.review(other,1,'contested','Conflict must be resolved')
        with self.assertRaisesRegex(ValueError,'contested'):f.gate(mid)
    def test_pdf_quote_can_use_later_page_without_excerpt_claim(self):
        pid,mid=self.project();raw=io.BytesIO();c=canvas.Canvas(raw)
        for n in range(1,81):c.drawString(50,700,'Synthetic guide page '+str(n));c.showPage()
        c.save();local.store_bytes('marketing','guide.pdf',raw.getvalue());sid=storage.save('marketing','document','Guide',filename='guide.pdf',sensitivity='internal',source='Synthetic guide',status='approved',access=['twin']);req=s.add_requirement(mid,'later','Read later page',True,'page:75');eid=ev.add(req,'storage',sid,'Synthetic guide page 75','page:75','Exact later-page evidence');self.assertEqual(ev.health(s.evidence(mid)[0],mid),'Current')
    def test_pdf_locator_is_validated(self):
        pid,mid=self.project();sid=self.pdf(pages=2,scope='marketing');ms.share(pid,sid,1,['marketing','twin']);req=s.add_requirement(mid,'pdf','Read',True,'Guide')
        with self.assertRaises(ValueError):ev.add(req,'storage',sid,'Not there','page:999','Out of bounds')
    def test_private_register_is_filtered_from_public_task_context(self):
        pid,mid=self.project();self.start(mid);req=s.add_requirement(mid,'secret','PRIVATE_REQUIREMENT_SENTINEL',True,'Private record',sensitivity='confidential');sid=self.source(pid,'PRIVATE_EVIDENCE_SENTINEL','confidential');ev.add(req,'storage',sid,'PRIVATE_EVIDENCE_SENTINEL','internal','Private conclusion')
        data=tools.workspace(mid,'marketing','internal');self.assertNotIn('PRIVATE_',json.dumps(data));self.assertTrue(tools.workspace(mid,'marketing','confidential')['requirements'])
    def test_nonlead_cannot_verify_evidence(self):
        pid,mid=self.project(workers=['marketing','career_rnd']);req,sid,eid=self.supported(pid,mid);self.start(mid)
        with self.assertRaises(ValueError):ev.review(eid,2,'accepted','Attempted self-authorisation',actor='career_rnd')

class QualityTests(AssuranceBase):
    def test_packet_freezes_register_and_requires_twin_scorecard(self):
        pid,mid=self.project();self.supported(pid,mid);self.start(mid);packet=self.packet(mid);self.assertTrue(s.records('assurance_packets','SELECT * FROM assurance_packets'))
        with self.assertRaisesRegex(ValueError,'scorecard'):mw.review_packet(mid,ms.milestone(mid)['version'],'accept','Looks good')
        self.accepted(mid);self.assertEqual(ms.milestone(mid)['state'],'approved')
    def test_incomplete_duplicate_or_failing_scores_cannot_pass(self):
        pid,mid=self.project();self.confirm(mid);self.start(mid);packet=self.packet(mid)
        with self.assertRaises(ValueError):f.scorecard(mid,packet['id'],packet['digest'],[],'twin')
        self.score(mid,verdict='fail')
        with self.assertRaisesRegex(ValueError,'passing scorecard'):mw.review_packet(mid,ms.milestone(mid)['version'],'accept','Attempt')
    def test_scorecard_exact_packet_and_immutable(self):
        pid,mid=self.project();self.confirm(mid);self.start(mid);packet=self.packet(mid);self.score(mid)
        with self.assertRaisesRegex(ValueError,'immutable'):self.score(mid,verdict='fail')
        with self.assertRaises(ValueError):f.scorecard(mid,'wrong',packet['digest'],[],'twin')
    def test_specialist_needs_scorecard_before_lead_acceptance(self):
        pid,mid=self.project(reviewers=['career_rnd']);self.confirm(mid);self.start(mid);packet=self.packet(mid);mw.ensure_reviewers(mid);a=next(a for a in ms.assignments(mid) if a['role']=='reviewer');task=self.complete(a['task_id'])
        with self.assertRaisesRegex(ValueError,'scorecard'):mw.review_assignment(task['id'],task['version'],True,'Without scorecard','marketing')
        self.score(mid,'career_rnd');mw.review_assignment(task['id'],task['version'],True,'Scorecard and critique checked','marketing');mw.advance_review(mid);self.accepted(mid)
    def test_authors_cannot_act_as_independent_reviewers(self):
        pid,mid=self.project();self.confirm(mid);self.start(mid);packet=self.packet(mid)
        with self.assertRaises(ValueError):self.score(mid,'marketing')
    def test_real_twin_controller_saves_scores_before_forwarding(self):
        pid,mid=self.project();self.confirm(mid);self.start(mid);packet=self.packet(mid);values=[dict(criterion=r['criterion'],verdict='pass',rationale='Checked exact result and scope.') for r in s.rubric(mid)]
        with p.connect() as db:db.execute('UPDATE milestone_projects SET next_due=0')
        result=me.tick(client=Metered(dict(action='accept',note='All criteria met and uncertainty disclosed.',deliverable='',scores=values)));self.assertEqual(result['status'],'completed');self.assertIsNotNone(f.scores(mid,packet['id'],'twin'));self.assertEqual(ms.milestone(mid)['state'],'owner_review')
    def test_scorecard_does_not_itself_approve_strategy(self):
        pid,mid=self.project();self.confirm(mid);self.start(mid);self.packet(mid);self.score(mid);self.assertEqual(ms.milestone(mid)['state'],'twin_review')

class InvestigationTests(AssuranceBase):
    def test_gap_dispatch_is_idempotent_and_blocks_integration(self):
        pid,mid=self.project();self.confirm(mid);self.start(mid);gid=inv.open_gap(mid,'market','Find primary evidence','marketing',True,'internal');self.assertFalse(work.gate(team.task(self.lead(mid)['task_id']))[0]);tid=inv.dispatch(mid);self.assertTrue(tid);self.assertIsNone(inv.dispatch(mid));self.assertIn(tid,json.loads(team.task(self.lead(mid)['task_id'])['deps']));self.assertEqual(s.gaps(mid)[0]['task_id'],tid)
    def test_lead_acceptance_resolves_actual_investigation(self):
        pid,mid=self.project();self.confirm(mid);self.start(mid);inv.open_gap(mid,'claim','Verify count','marketing',True,'internal');tid=inv.dispatch(mid);task=self.complete(tid);mw.review_assignment(tid,task['version'],True,'Source-backed answer resolves this question','marketing');self.assertEqual(s.gaps(mid)[0]['state'],'resolved');self.assertTrue(work.gate(team.task(self.lead(mid)['task_id']))[0])
    def test_failed_investigation_stays_open_for_revision(self):
        pid,mid=self.project();self.start(mid);inv.open_gap(mid,'claim','Verify count','marketing',True,'internal');tid=inv.dispatch(mid);task=self.complete(tid);mw.review_assignment(tid,task['version'],False,'Needs actual supporting research','marketing');self.assertEqual(s.gaps(mid)[0]['state'],'assigned');self.assertFalse(work.gate(team.task(self.lead(mid)['task_id']))[0])
    def test_unapproved_worker_and_lower_privacy_rejected(self):
        pid,mid=self.project();self.start(mid)
        with self.assertRaises(ValueError):inv.open_gap(mid,'gap','Research','legal_ops',True,'internal')
        with self.assertRaises(ValueError):inv.open_gap(mid,'gap','Research','marketing',True,'public')
    def test_only_supporting_unassigned_gap_can_be_deferred(self):
        pid,mid=self.project();critical=inv.open_gap(mid,'must','Research','marketing',True,'internal')
        with self.assertRaises(ValueError):inv.deferred_gap(critical,1,'Skip')
        supporting=inv.open_gap(mid,'optional','Research','marketing',False,'internal');inv.deferred_gap(supporting,1,'Not necessary for current acceptance scope');self.assertEqual(s.gaps(mid)[1]['state'],'deferred')
    def test_paused_project_does_not_dispatch(self):
        pid,mid=self.project();self.start(mid);inv.open_gap(mid,'gap','Research','marketing',True,'internal');ms.configure(pid,ms.managed(pid)['version'],False,True);self.assertIsNone(inv.dispatch(mid))

class ChangeTests(AssuranceBase):
    def test_stale_source_blocks_origin_and_downstream(self):
        pid,mid=self.project();req,sid,eid=self.supported(pid,mid);self.start(mid);self.packet(mid);self.accepted(mid);nextid=ms.add(pid,'Next','Question','Criteria',['marketing'],deps=[mid]);source=storage.get(sid);storage.save('marketing','fact','Synthetic evidence',content='Synthetic pilot count is 14.',fact_key=source['fact_key'],project_kind='team',project_id=pid,sensitivity='internal',access=['twin'],source='Updated synthetic record',status='approved',ident=sid,expected=source['version']);f.reconcile(mid)
        self.assertTrue(f.block_reason(nextid));self.assertEqual(ms.milestone(mid)['state'],'approved')
        with self.assertRaises(ValueError):self.start(nextid)
        f.reconcile(mid);self.assertEqual(len(s.changes(pid)),1)
    def test_owner_reopens_approved_result_and_preserves_packet(self):
        pid,mid=self.project();self.confirm(mid);self.start(mid);packet=self.packet(mid);self.accepted(mid);f.change_criteria(mid,ms.milestone(mid)['version'],'Updated question','Updated criteria','Owner strategy changed');change=s.changes(pid)[0];f.reopen(change['id'],change['version'],'Revise the earlier deliverable and rerun review');self.assertEqual(ms.milestone(mid)['state'],'working');self.assertFalse(ms.milestone(mid)['criteria_confirmed']);self.assertEqual(ms.packet(mid)['id'],packet['id']);self.assertEqual(team.task(self.lead(mid)['task_id'])['state'],'dispatched');self.assertFalse(s.policy(mid)['register_confirmed'])
    def test_register_change_cannot_reuse_old_packet_or_scores(self):
        pid,mid=self.project();self.confirm(mid);self.start(mid);packet=self.packet(mid);self.score(mid);s.add_requirement(mid,'new','New requirement',False,'Owner decision')
        with self.assertRaises(ValueError):mw.review_packet(mid,ms.milestone(mid)['version'],'accept','Old packet')
    def test_reopen_requires_current_change_version(self):
        pid,mid=self.project();self.confirm(mid);self.start(mid);self.packet(mid);f.changed(mid,'decision','Strategy changed');change=s.changes(pid)[0]
        with self.assertRaises(ValueError):f.reopen(change['id'],999,'Stale view')
    def test_descendant_propagation_does_not_touch_unrelated_project(self):
        pid,mid=self.project();nextid=ms.add(pid,'Next','Question','Criteria',['marketing'],deps=[mid]);other,om=self.project();f.changed(mid,'decision','Changed',force=True);self.assertEqual(set(f.descendants(mid)),{mid,nextid});self.assertFalse(f.block_reason(om))

class OutcomeTests(AssuranceBase):
    def test_initiative_approval_does_not_create_work(self):
        pid,mid=self.project();ident=out.propose(pid,'pilot','Pilot improvements','Improve pilot completion through a scoped intervention');out.decide(ident,1,'approved','Relevant initiative; execution remains governed');self.assertFalse(team.tasks());self.assertEqual(out.propose(pid,'pilot','Pilot improvements','Improve pilot completion through a scoped intervention'),ident)
    def test_baseline_requires_approved_initiative_and_finite_values(self):
        pid,mid=self.project();ident=out.propose(pid,'pilot','Pilot improvements','Measurable hypothesis')
        with self.assertRaises(ValueError):out.add_metric(ident,'Pilots','count','0','12','2026-11-01','increase')
        out.decide(ident,1,'approved','Approved')
        with self.assertRaises(ValueError):out.add_metric(ident,'Pilots','count','NaN','12','2026-11-01','increase')
    def test_observation_needs_source_review_and_reports_change_not_roi(self):
        pid,mid=self.project();ident=out.propose(pid,'pilot','Pilot improvements','Measurable hypothesis');out.decide(ident,1,'approved','Approved');metric=out.add_metric(ident,'Pilots','count','5','12',storage.today().isoformat(),'increase');sid=self.source(pid,'Synthetic observed pilot count: 12.');obs=out.observe(metric,'12',storage.today().isoformat(),sid,'Synthetic observed pilot count: 12.','Synthetic count method');self.assertIsNone(out.summary(metric)['latest']);out.accept_observation(obs);data=out.summary(metric);self.assertEqual(data['change'],'7');self.assertTrue(data['target_met']);self.assertTrue(data['due_for_review']);self.assertIn('does not prove',data['limitation'])
    def test_future_observation_and_foreign_signal_rejected(self):
        pid,mid=self.project()
        with self.assertRaises(ValueError):out.propose(pid,'x','Proposal','Hypothesis',source_kind='signal',source_id='unknown')
        ident=out.propose(pid,'pilot','Pilot improvements','Measurable hypothesis');out.decide(ident,1,'approved','Approved');metric=out.add_metric(ident,'Pilots','count','0','12','2026-11-01','increase');sid=self.source(pid)
        with self.assertRaises(ValueError):out.observe(metric,'12',(storage.today()+timedelta(days=1)).isoformat(),sid,'Synthetic pilot count is 12.','Forecast not observation')

class AssuranceWebTests(AssuranceBase):
    def client(self):
        cfg=config.Settings('https://testserver',state_dir=__import__('pathlib').Path('state'));auth.Store(cfg.auth_db).setup('owner','synthetic-test-passphrase');c=TestClient(web.create_app(cfg),base_url=cfg.public_origin);response=c.get('/login');import re;csrf=re.search(r'name="csrf" value="([^"]+)"',response.text).group(1);c.post('/login',data={'username':'owner','password':'synthetic-test-passphrase','csrf':csrf});return c
    def test_evidence_and_outcome_pages_render_with_project_links(self):
        pid,mid=self.project();self.supported(pid,mid);c=self.client()
        for url in ['/milestones/'+mid+'/evidence','/project-hub/'+pid+'/outcomes','/project-hub/'+pid]:self.assertEqual(c.get(url).status_code,200,url)
        self.assertIn('/milestones/'+mid+'?view=evidence',c.get('/milestones/'+mid).text)
    def test_new_pages_require_login_and_posts_require_csrf(self):
        pid,mid=self.project();c=self.client();self.assertEqual(c.post('/milestones/'+mid+'/requirements',data={'key':'x'}).status_code,403);c.cookies.clear();self.assertEqual(c.get('/milestones/'+mid+'/evidence',follow_redirects=False).status_code,303)

class EmployeeToolTests(AssuranceBase):
    def run(self,*args,**kwargs):return super().run(*args,**kwargs)
    def assigned(self,mid):
        from superhuman.agentic import store as agent
        task=self.lead(mid);rid=work.dispatch(task['task_id'],task['version']);return agent.get(rid)
    def test_employee_can_propose_requirements_through_actual_tool(self):
        from test_agentic import decision
        pid,mid=self.project();self.start(mid);run=self.assigned(mid);p.run_one(run['project_id'],client=Metered(decision('assurance.record',{'record_json':json.dumps(dict(operation='requirement',key='actual',title='Check actual context',critical=True,origin='Assigned project brief'))})));self.assertEqual(s.requirements(mid)[0]['actor'],'marketing');self.assertFalse(s.policy(mid)['register_confirmed'])
    def test_employee_cannot_supply_an_actor_or_lower_privacy(self):
        pid,mid=self.project();self.start(mid);run=self.assigned(mid)
        with self.assertRaises(ValueError):tools.execute('assurance.record',{'record_json':json.dumps(dict(operation='requirement',key='x',title='X',critical=True,origin='Guide',actor='owner'))},run)
    def test_workspace_pages_are_bounded_and_receipts_recheck_sources(self):
        pid,mid=self.project();req,sid,eid=self.supported(pid,mid);self.start(mid);run=self.assigned(mid);data=tools.execute('assurance.workspace',{'section':'evidence','offset':0},run);self.assertLessEqual(len(data['items']),2);tools.verify_receipt(data['assurance_receipt']);item=storage.get(sid);storage.save('marketing','fact',item['title'],content='Source changed',fact_key=item['fact_key'],project_kind='team',project_id=pid,sensitivity='internal',access=['twin'],source='Updated source',status='approved',ident=sid,expected=item['version'])
        with self.assertRaises(ValueError):tools.verify_receipt(data['assurance_receipt'])
    def test_private_evidence_prevents_public_integration_review(self):
        pid,mid=self.project();self.start(mid);req=s.add_requirement(mid,'private','Private requirement',True,'Private source',sensitivity='confidential');sid=self.source(pid,'Private source number 10','confidential');eid=ev.add(req,'storage',sid,'Private source number 10','section 1','Private claim');ev.review(eid,1,'accepted','Checked privately');self.confirm(mid)
        with self.assertRaisesRegex(ValueError,'more private'):f.gate(mid)
    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaises(ValueError):tools.parse('{"operation":"gap","operation":"requirement"}')
    def test_due_outcome_appears_in_existing_attention(self):
        from superhuman.workspace import model
        pid,mid=self.project();ident=out.propose(pid,'pilot','Pilot improvements','Measurable hypothesis');out.decide(ident,1,'approved','Approved');out.add_metric(ident,'Pilots','count','0','12',storage.today().isoformat(),'increase');self.assertTrue(any(r['reason'].startswith('Outcome follow-up') for r in model.decisions()))

class AdditionalGateTests(AssuranceBase):
    def test_blueprint_created_after_setup_receives_all_seven_registers(self):
        s.setup();pid=ms.seed_endorsement();self.assertTrue(all(s.policy(m['id']) for m in ms.listing(pid)));self.assertEqual(len(ms.listing(pid)),7)
    def test_valid_failing_critique_can_trigger_integration_revision(self):
        pid,mid=self.project(reviewers=['career_rnd']);self.confirm(mid);self.start(mid);packet=self.packet(mid);mw.ensure_reviewers(mid);a=next(a for a in ms.assignments(mid) if a['role']=='reviewer');task=self.complete(a['task_id']);self.score(mid,'career_rnd','fail');mw.review_assignment(task['id'],task['version'],True,'The critique correctly identifies a substantive deficiency','marketing');mw.advance_review(mid)
        with self.assertRaisesRegex(ValueError,'passing scorecard'):f.quality_gate(mid)
        mw.review_packet(mid,ms.milestone(mid)['version'],'revise','Address the specialist findings before resubmitting');self.assertEqual(ms.milestone(mid)['state'],'working')
    def test_reconfirming_scope_cannot_invalidate_frozen_packet_silently(self):
        pid,mid=self.project();self.confirm(mid)
        with self.assertRaises(ValueError):self.confirm(mid)
