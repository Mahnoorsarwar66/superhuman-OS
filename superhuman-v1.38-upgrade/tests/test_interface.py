"""Navigation, focused views and existing approval controls survive the UI redesign."""
import json,re,unittest
from pathlib import Path
from fastapi.testclient import TestClient
from test_assurance import AssuranceBase
from superhuman.hosted import config,web,auth
from superhuman.projects import engine as p
from superhuman.team import store as team
from superhuman.milestones import store as ms,workflow as mw,web as milestone_web
from superhuman.assurance import store as assurance,web as assurance_web
from superhuman.navigation import shell
from superhuman.interface import views,chrome
from superhuman.interface.tree import parse
from superhuman.interface.web import return_location

def form_actions(body):return {n.attrs.get('action','') for n in parse(body).find('form') if (n.attrs.get('method','get') or 'get').lower()=='post'}

class MarkupTests(unittest.TestCase):
    def test_polish_preserves_user_values_and_verbatim_source_text(self):
        original='<h1>Packet owner review</h1><textarea name="content">Packet &lt;script&gt;owner review&lt;/script&gt;</textarea><pre>Record evidence judgment · owner review</pre><input name="token" value="a&amp;b"><span class="badge">owner review</span>'
        result=chrome.polish(original,'/milestones/a')
        self.assertIn('<h1>Packet owner review</h1>',result);self.assertIn('Packet &lt;script&gt;owner review&lt;/script&gt;',result);self.assertIn('<pre>Record evidence judgment · owner review</pre>',result);self.assertIn('value="a&amp;b"',result);self.assertIn('Needs your decision',result)
    def test_status_always_has_readable_text(self):
        self.assertIn('Needs your decision',chrome.pill('owner_review'));self.assertIn('Fail',chrome.pill('fail'));self.assertNotIn('Approved',chrome.pill('pass'))
    def test_untrusted_record_text_remains_escaped(self):
        result=views.header('<script>alert(1)</script>','<img src=x onerror=alert(1)>')
        self.assertNotIn('<script>',result);self.assertNotIn('<img',result);self.assertIn('&lt;script&gt;',result)
    def test_redirect_preserves_only_matching_local_record_view(self):
        url='/project-hub/abc';self.assertEqual(return_location(url,'https://site.test/project-hub/abc?view=files','site.test'),url+'?view=files');self.assertEqual(return_location(url,'https://evil.test/project-hub/abc?view=manage','site.test'),url);self.assertEqual(return_location(url,'https://site.test/project-hub/def?view=manage','site.test'),url);self.assertEqual(return_location(url,'https://site.test/project-hub/abc?view=https://evil.test','site.test'),url)
    def test_evidence_redirect_keeps_investigation_panel(self):self.assertEqual(return_location('/milestones/abc/evidence','https://site.test/milestones/abc/evidence?panel=investigations','site.test'),'/milestones/abc/evidence?panel=investigations')
    def test_capture_context_is_restored_after_failure(self):
        def fails():raise ValueError('Test')
        with self.assertRaises(ValueError):chrome.capture(fails)
        self.assertFalse(chrome.capturing.get())

class InterfaceTests(AssuranceBase):
    def setUp(self):
        super().setUp();self.cfg=config.Settings('https://superhuman.example',state_dir=Path('state'));auth.Store(self.cfg.auth_db).setup('owner','synthetic-test-passphrase');self.client=TestClient(web.create_app(self.cfg),base_url=self.cfg.public_origin)
        csrf=self.token(self.client.get('/login').text);self.client.post('/login',data=dict(username='owner',password='synthetic-test-passphrase',csrf=csrf))
    def token(self,body):return re.search(r'name="csrf" value="([^"]+)"',body).group(1)
    def body(self,url):
        response=self.client.get(url);self.assertEqual(response.status_code,200,response.text[:500]);return response.text
    def test_common_assets_and_keyboard_accessibility(self):
        body=self.body('/');self.assertIn('/assets/interface.css?v=133',body);self.assertIn('Skip to content',body);self.assertIn('Needs your decision',body);self.assertIn('Talk with The Twin',body)
        css=self.client.get('/assets/interface.css');self.assertEqual(css.status_code,200);self.assertIn('prefers-reduced-motion',css.text);self.assertIn('focus-visible',css.text);self.assertIn('font-size:16px',css.text)
    def test_project_list_unifies_milestone_projects_and_filters(self):
        pid,mid=self.project();body=self.body('/projects?capability=milestones');self.assertIn(team.project(pid)['title'],body);self.assertIn('Project type',body);self.assertIn('Milestone project',body);nav=next(n for n in parse(body).find('nav') if n.attrs.get('aria-label')=='Section navigation');self.assertNotIn('Milestone projects',nav.text())
    def test_project_views_have_one_workspace_navigation(self):
        pid,mid=self.project()
        for view in ('summary','work','files','conversations','activity','manage'):
            body=self.body('/project-hub/'+pid+'?view='+view);tree=parse(body);nav=[n for n in tree.find('nav') if 'data-interface-tabs' in n.attrs];self.assertEqual(len(nav),1);self.assertEqual(sum('aria-current' in a.attrs for a in nav[0].find('a')),1)
    def test_project_controls_are_in_manage_and_not_summary(self):
        pid,mid=self.project();summary=self.body('/project-hub/'+pid);manage=self.body('/project-hub/'+pid+'?view=manage');self.assertNotIn('/project-hub/'+pid+'/configure',form_actions(summary));self.assertIn('/project-hub/'+pid+'/configure',form_actions(manage));self.assertIn('/team/projects/'+pid+'/governance',form_actions(manage))
    def test_all_managed_project_post_actions_remain_accessible(self):
        pid,mid=self.project();before=form_actions(chrome.capture(milestone_web._v132_project_page,pid));after=set()
        for v in ('summary','work','files','conversations','activity','manage'):after|=form_actions(self.body('/project-hub/'+pid+'?view='+v))
        self.assertLessEqual(before,after)
    def test_milestone_start_and_criteria_are_in_manage(self):
        pid,mid=self.project();body=self.body('/milestones/'+mid+'?view=manage');self.assertIn('/milestones/'+mid+'/start',form_actions(body));self.assertIn('Success criteria',self.body('/milestones/'+mid));self.assertNotIn('Approve milestone',self.body('/milestones/'+mid))
    def test_existing_milestone_post_controls_survive_all_views(self):
        pid,mid=self.project();self.confirm(mid);self.start(mid);self.packet(mid);self.score(mid);mw.review_packet(mid,ms.milestone(mid)['version'],'accept','Synthetic review passed');before=form_actions(chrome.capture(milestone_web._v132_milestone_page,mid));after=set()
        for v in ('deliverable','evidence','reviews','history','manage'):after|=form_actions(self.body('/milestones/'+mid+'?view='+v))
        self.assertLessEqual(before,after)
    def test_owner_approval_requires_original_exact_packet_and_checkbox(self):
        pid,mid=self.project();self.confirm(mid);self.start(mid);packet=self.packet(mid);self.score(mid);mw.review_packet(mid,ms.milestone(mid)['version'],'accept','Ready for owner');url='/milestones/'+mid+'?view=reviews';body=self.body(url);response=self.client.post('/milestones/'+mid+'/approve',data=dict(expected=ms.milestone(mid)['version'],packet_id=packet['id'],note='Inspect exact result',csrf=self.token(body)),follow_redirects=False);self.assertEqual(response.status_code,409);self.assertEqual(ms.milestone(mid)['state'],'owner_review')
    def test_evidence_confirmation_form_disappears_once_confirmed(self):
        pid,mid=self.project();before=self.body('/milestones/'+mid+'/evidence');self.assertIn('/register/confirm',before);self.confirm(mid);after=self.body('/milestones/'+mid+'/evidence');self.assertNotIn('/milestones/'+mid+'/register/confirm',form_actions(after));self.assertIn('Requirement scope confirmed',after)
    def test_evidence_sections_preserve_all_previous_actions(self):
        pid,mid=self.project();self.supported(pid,mid);before=form_actions(chrome.capture(assurance_web._v132_evidence_page,mid));after=set()
        for v in ('requirements','investigations','standards'):after|=form_actions(self.body('/milestones/'+mid+'/evidence?panel='+v))
        before.discard('/milestones/'+mid+'/register/confirm');self.assertLessEqual(before,after)
    def test_bad_view_is_rejected_without_workflow_changes(self):
        pid,mid=self.project();version=ms.milestone(mid)['version'];self.assertEqual(self.client.get('/project-hub/'+pid+'?view=unknown').status_code,400);self.assertEqual(ms.milestone(mid)['version'],version)
    def test_html_errors_are_actionable_and_json_errors_remain_json(self):
        response=self.client.get('/projects?capability=unknown',headers={'Accept':'text/html'});self.assertEqual(response.status_code,400);self.assertIn('Go back',response.text);self.assertIn('Choose a valid project filter',response.text)
        response=self.client.get('/projects?capability=unknown',headers={'Accept':'application/json'});self.assertIn('detail',response.json())
    def test_form_validation_error_does_not_echo_sensitive_submission(self):
        body=self.body('/projects');response=self.client.post('/project-leadership/attach',data=dict(csrf=self.token(body),secret='DO_NOT_ECHO_SENTINEL'),headers={'Accept':'text/html'});self.assertEqual(response.status_code,422);self.assertNotIn('DO_NOT_ECHO_SENTINEL',response.text);self.assertIn('project id',response.text)
    def test_new_assets_are_still_authenticated(self):
        self.client.cookies.clear();response=self.client.get('/assets/interface.css',follow_redirects=False);self.assertEqual(response.status_code,303)
    def test_unmanaged_project_has_work_and_controls_without_dead_outcome_link(self):
        pid=team.create_project('marketing','Task-based project','Outcome','Success');summary=self.body('/team/projects/'+pid);self.assertNotIn('/outcomes',summary);work=self.body('/team/projects/'+pid+'?view=work');self.assertIn('/team/projects/'+pid+'/tasks',form_actions(work));self.assertIn('/governance',self.body('/team/projects/'+pid+'?view=manage'))
    def test_generic_task_creation_directs_managed_projects_to_milestones(self):
        pid,mid=self.project();body=self.body('/new-task');self.assertIn('Add milestone work',body);self.assertNotIn('action="/workspace-tasks/create"',body)
    def test_department_navigation_keeps_agent_and_supervision_inside_department(self):
        pid,mid=self.project();body=self.body('/departments/marketing/agent');self.assertIn('Manage supervision',body);self.assertIn('Agent &amp; supervision',body);self.assertIn('Work &amp; priorities',body);self.assertIn('Department supervision',body)
    def test_department_work_has_priority_controls(self):self.assertIn('/department-plans/marketing',self.body('/departments/marketing/projects'))
    def test_storage_and_settings_keep_advanced_controls_accessible(self):
        pid,mid=self.project();sid=self.source(pid);body=self.body('/storage/items/'+sid);self.assertIn('Manage source & access',parse(body).text());self.assertIn('Synthetic pilot count is 12.',body);settings=self.body('/settings')
        for url in ('/team/budget','/assistant/connections','/memory/preview','/queue','/coding','/system-checks'):self.assertIn(url,settings)
    def test_project_post_redirect_returns_to_selected_view(self):
        pid,mid=self.project();url='/project-hub/'+pid+'?view=manage';body=self.body(url);cfg=ms.managed(pid);response=self.client.post('/project-hub/'+pid+'/configure',data=dict(expected=cfg['version'],enabled='yes',share_outputs='yes',csrf=self.token(body)),headers={'Referer':self.cfg.public_origin+url},follow_redirects=False);self.assertEqual(response.headers['location'],url)

class DecisionPresentationTests(AssuranceBase):
    def test_owner_queue_has_one_milestone_gate_and_hides_routine_lead_review(self):
        from superhuman.workspace import model
        pid,mid=self.project();self.confirm(mid);self.start(mid);self.packet(mid)
        self.assertFalse(any(r['url'].startswith('/team/tasks/'+self.lead(mid)['task_id']) for r in model.decisions()))
        self.score(mid);mw.review_packet(mid,ms.milestone(mid)['version'],'accept','Ready for owner');items=[r for r in model.decisions() if r['url'].startswith('/milestones/'+mid)];self.assertEqual(len(items),1);self.assertTrue(items[0]['url'].endswith('view=reviews'))
