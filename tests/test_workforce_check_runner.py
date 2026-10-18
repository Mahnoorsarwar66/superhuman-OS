import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class CheckRunnerTests(unittest.TestCase):
    def test_runner_isolates_state_strips_credentials_and_blocks_external_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            package = root / 'package'
            (source / 'superhuman').mkdir(parents=True)
            (source / 'superhuman/__init__.py').write_text('')
            (package / 'tests').mkdir(parents=True)
            (package / 'run_checks.py').write_text('''
import os, socket
from pathlib import Path
assert 'OPENAI_API_KEY' not in os.environ
assert os.environ['PYTHON_DOTENV_DISABLED'] == '1'
assert not Path('data/private.txt').exists()
try:
    socket.socket().connect(('203.0.113.1', 443))
except RuntimeError as error:
    assert 'network disabled' in str(error)
else:
    raise AssertionError('External connection was allowed')
Path('temporary-record.txt').write_text('synthetic')
print('ISOLATION_PASS')
''')
            (source / 'data').mkdir()
            (source / 'data/private.txt').write_text('PRIVATE_SENTINEL')
            script = Path(__file__).resolve().parents[1] / 'tools/run_workforce_checks.py'
            log = root / 'checks.log'
            env = dict(os.environ, OPENAI_API_KEY='PRIVATE_SENTINEL')
            result = subprocess.run([sys.executable, str(script), '--source', str(source),
                '--package', str(package), '--log', str(log)], env=env,
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, log.read_text())
            self.assertIn('ISOLATION_PASS', log.read_text())
            self.assertFalse((source / 'temporary-record.txt').exists())
            self.assertEqual((source / 'data/private.txt').read_text(), 'PRIVATE_SENTINEL')


if __name__ == '__main__':
    unittest.main()
