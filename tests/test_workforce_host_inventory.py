import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.workforce_host_inventory import inventory


class HostInventoryTests(unittest.TestCase):
    def test_config_values_and_process_arguments_are_not_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data/hosted').mkdir(parents=True)
            (root / 'data/hosted/config.json').write_text(json.dumps({
                'public_origin': 'PRIVATE_SENTINEL', 'session_seconds': 600}))
            result = SimpleNamespace(stdout='User=superhuman\nActiveState=active\n')
            with patch('tools.workforce_host_inventory.subprocess.run', return_value=result) as run:
                report = inventory(root)
            self.assertNotIn('PRIVATE_SENTINEL', json.dumps(report))
            self.assertEqual(report['configuration_schema']['public_origin'], 'str')
            for call in run.call_args_list:
                self.assertNotIn('ExecStart', ' '.join(call.args[0]))

    def test_version_detection_parses_source_without_importing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'superhuman/hosted').mkdir(parents=True)
            (root / 'superhuman/hosted/boundary.py').write_text(
                "raise RuntimeError('do not import')\nresponse={'version':'1.41.0'}\n")
            with patch('tools.workforce_host_inventory.subprocess.run', side_effect=OSError):
                report = inventory(root)
            self.assertEqual(report['declared_source_versions']['superhuman/hosted/boundary.py'],
                             ['1.41.0'])


if __name__ == '__main__':
    unittest.main()
