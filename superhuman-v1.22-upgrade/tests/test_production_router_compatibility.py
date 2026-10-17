"""Regression against the owner's supplied production routing rules."""
import unittest
from unittest.mock import patch
from test_dialogue import DialogueTests
from test_researchdesk import area,source
import production_router_fixture as supplied
from superhuman.core import router
from superhuman.researchdesk import store
from superhuman.runtime import engine as runtime

class ProductionRouterCompatibility(unittest.TestCase):
    setUp=DialogueTests.setUp
    tearDown=DialogueTests.tearDown
    def test_generated_web_template_is_accepted(self):
        task=store.draft(area(),'web',[])
        self.assertIn('study methods',task['details'])
        with patch.object(router,'route_task',supplied.route_task),patch.object(router,'WORKSTREAMS',supplied.WORKSTREAMS):
            runtime.validate_job('research','marketing',task['title'],task['details'])
    def test_local_synopsis_and_synthesis_remain_accepted(self):
        a=area();sid=source(a)
        for kind in ('synopsis','synthesis'):
            task=store.draft(a,kind,[sid])
            with patch.object(router,'route_task',supplied.route_task),patch.object(router,'WORKSTREAMS',supplied.WORKSTREAMS):
                runtime.validate_job('collab','marketing',task['title'],task['details'])
    def test_external_action_gates_are_preserved(self):
        with patch.object(router,'route_task',supplied.route_task),patch.object(router,'WORKSTREAMS',supplied.WORKSTREAMS):
            for action in ('send email','publish','submit','spend','pay','sign','file application','contact investor'):
                with self.subTest(action=action),self.assertRaises(ValueError):runtime.validate_job('research','marketing',action,'')
    def test_owner_requested_actions_are_not_sanitized_away(self):
        a=area();store.update(a,1,'Research','Please send email to the university.','','active')
        task=store.draft(a,'web',[])
        self.assertIn('Please send email to the university.',task['details'])
        with patch.object(router,'route_task',supplied.route_task),patch.object(router,'WORKSTREAMS',supplied.WORKSTREAMS),self.assertRaises(ValueError):
            runtime.validate_job('research','marketing',task['title'],task['details'])

del DialogueTests
