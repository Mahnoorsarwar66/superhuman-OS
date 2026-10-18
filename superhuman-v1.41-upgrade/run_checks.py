"""Focused repair regressions plus existing governed teamwork acceptance checks."""
import importlib,inspect,unittest
names=['test_conversationwork','test_organisation','test_executionrepair','test_agentic','test_memory_generation','test_liveqa','test_trust','test_team','test_teamhub','test_milestones','test_assurance','test_practice','test_interface','test_workspace','test_foundation']
suite=unittest.TestSuite()
for name in names:
 module=importlib.import_module(name)
 for _,cls in inspect.getmembers(module,inspect.isclass):
  if cls.__module__==name and issubclass(cls,unittest.TestCase):suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(cls))
result=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
