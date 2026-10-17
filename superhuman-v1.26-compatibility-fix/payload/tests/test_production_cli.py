"""Compatibility with the owner's supplied CLI and separate legacy orchestrator."""
import importlib.util,json,os,sys,types,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace as N
from test_team import TeamTests as Base,Metered,MODEL
from superhuman.team import budget,store
PACKAGE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('production_cli_patch_rules',PACKAGE/'patches.py');rules=importlib.util.module_from_spec(spec);spec.loader.exec_module(rules)
CLI=(PACKAGE/'reference/production_cli.py').read_text()
ORCHESTRATOR=(PACKAGE/'reference/core/orchestrator.py').read_text()
def modules():
    orchestrator=types.ModuleType('compatibility_orchestrator_fixture')
    exec(compile(rules.build('core/orchestrator.py',ORCHESTRATOR,PACKAGE/'reference'),'core/orchestrator.py','exec'),orchestrator.__dict__)
    cli=types.ModuleType('compatibility_cli_fixture')
    with patch.dict(sys.modules,{'superhuman.core.orchestrator':orchestrator}):exec(compile(CLI,'production_cli.py','exec'),cli.__dict__)
    route=N(workstream='marketing',agent='fixture-agent',risk_level='low',approval_required=False,reason='Internal drafting')
    orchestrator.route_task=lambda *args:route;orchestrator.context_for=lambda *args:'Confirmed test context';orchestrator.get_agent_prompt=lambda *args:'Test instructions';cli.route_task=orchestrator.route_task
    return cli,orchestrator

class ProductionCliTests(unittest.TestCase):
    setUp=Base.setUp
    tearDown=Base.tearDown
    boot=Base.boot
    def test_supplied_cli_is_preserved(self):self.assertEqual(rules.build('cli.py',CLI,PACKAGE/'reference'),CLI)
    def test_unknown_cli_and_orchestrator_are_refused(self):
        for name,text in (('cli.py',CLI),('core/orchestrator.py',ORCHESTRATOR)):
            with self.assertRaises(ValueError):rules.build(name,text+'\nUNKNOWN_CHANGE=1\n',PACKAGE/'reference')
    def test_starter_cli_is_still_recognised_and_metered(self):
        baseline=(PACKAGE/'reference/cli.py').read_text();patched=rules.build('cli.py',baseline,PACKAGE/'reference');self.assertIn('client=wrap(client)',patched);self.assertIn('max_retries=0',patched)
    def test_source_selection_and_backup_profiles(self):
        root=Path('app');(root/'superhuman/core').mkdir(parents=True);self.assertEqual(rules.source_files(root),rules.FILES);(root/'superhuman/core/orchestrator.py').write_text(ORCHESTRATOR);self.assertIn('core/orchestrator.py',rules.source_files(root))
        self.assertEqual(len(rules.manifest_files({'before_hashes':{'superhuman/'+n:'' for n in rules.FILES}})),19)
        self.assertEqual(len(rules.manifest_files({'before_hashes':{'superhuman/'+n:'' for n in rules.FILES+('core/orchestrator.py',)}})),20)
        with self.assertRaises(ValueError):rules.manifest_files({'before_hashes':{'../../unexpected':''}})
    def test_migrated_production_pair_has_correct_expected_source(self):
        for name,text in (('cli.py',CLI),('core/orchestrator.py',ORCHESTRATOR)):
            installed=rules.build(name,text,PACKAGE/'reference');self.assertEqual(rules.canonical(name,rules.expected_source(name,installed,PACKAGE/'reference')),rules.canonical(name,installed))
    def test_legacy_commands_preserve_existing_tasks_and_reviews(self):
        cli,_=modules()
        with patch('builtins.print'):cli.init_db();cli.add_task(None,'Existing title','Keep these details');cli.review_task(1,'approve','Owner note');cli.list_tasks();cli.show_task(1)
        with cli.connect() as db:
            row=db.execute('SELECT project,agent,title,details,status FROM tasks WHERE id=1').fetchone();notes=db.execute('SELECT action,note FROM reviews WHERE task_id=1').fetchall()
        self.assertEqual(row,('marketing','fixture-agent','Existing title','Keep these details','approved'));self.assertEqual(notes,[('approve','Owner note')])
    def test_orchestrator_uses_dollar_guard_and_disables_sdk_retries(self):
        self.boot();_,mod=modules();fake=Metered('A useful internal draft.')
        with patch.dict(os.environ,{'OPENAI_API_KEY':'synthetic-test-key','OPENAI_MODEL':MODEL}),patch.object(mod,'OpenAI',return_value=fake) as factory:result=mod.run_superhuman_task(1,'Draft a local note','Use provided facts')
        self.assertEqual(result['status'],'needs_review');self.assertTrue(Path(result['output_path']).exists());self.assertEqual(fake.calls,1);self.assertEqual(factory.call_args.kwargs['max_retries'],0);costs=budget.report()['costs'];self.assertEqual(len(costs),1);self.assertEqual(costs[0]['pool'],'staff');self.assertEqual(costs[0]['actor'],'legacy')
    def test_risk_approval_gate_remains_before_any_provider_call(self):
        _,mod=modules();mod.route_task=lambda *args:N(approval_required=True)
        with patch.object(mod,'OpenAI') as factory:result=mod.run_superhuman_task(1,'External action');factory.assert_not_called()
        self.assertEqual(result['status'],'needs_approval');self.assertIsNone(result['output_path'])
    def test_budget_block_preserves_pending_legacy_task(self):
        self.boot();cli,mod=modules();fake=Metered('Must not be generated');budget.set_rate(MODEL,'100','100','Synthetic high cost')
        with patch('builtins.print'):cli.init_db();cli.add_task(None,'Local draft','Facts')
        with patch.dict(os.environ,{'OPENAI_API_KEY':'synthetic-test-key','OPENAI_MODEL':MODEL}),patch.object(cli,'load_dotenv'),patch.object(mod,'OpenAI',return_value=fake),self.assertRaises(budget.BudgetBlocked):cli.run_task(1)
        self.assertEqual(fake.calls,0)
        with cli.connect() as db:self.assertEqual(db.execute('SELECT status,output_path FROM tasks WHERE id=1').fetchone(),('pending',None))
    def test_pausing_team_does_not_disable_legacy_dollar_guard(self):
        self.boot();cfg=store.settings();store.configure(cfg['version'],False,MODEL);_,mod=modules();budget.set_rate(MODEL,'100','100','Synthetic high cost');fake=Metered('No paid call')
        with patch.dict(os.environ,{'OPENAI_API_KEY':'synthetic-test-key','OPENAI_MODEL':MODEL}),patch.object(mod,'OpenAI',return_value=fake),self.assertRaises(budget.BudgetBlocked):mod.run_superhuman_task(2,'Local draft')
        self.assertEqual(fake.calls,0)

del Base
