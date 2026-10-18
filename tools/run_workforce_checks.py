"""Run packaged offline checks against one explicit source tree in temporary state."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile


CHILD = r'''
import os, runpy, socket, sys
source, tests, runner, case = sys.argv[1:]
sys.path[:0] = [source, tests]
# Preserve loopback for local test infrastructure, prohibit provider connections.
def network_guard(event, arguments):
    if event == 'socket.connect':
        address = arguments[1]
        if isinstance(address, tuple) and address[0] not in ('127.0.0.1', '::1', 'localhost'):
            raise RuntimeError('External network disabled in offline workforce checks')
    if event == 'socket.getaddrinfo' and arguments[0] not in ('127.0.0.1', '::1', 'localhost', None):
        raise RuntimeError('External DNS disabled in offline workforce checks')
sys.addaudithook(network_guard)
import superhuman
if not os.path.realpath(superhuman.__file__).startswith(os.path.realpath(source) + os.sep):
    raise RuntimeError('Wrong application source imported')
if case:
    import unittest
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName(case))
    raise SystemExit(0 if result.wasSuccessful() else 1)
runpy.run_path(runner, run_name='__main__')
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--package', type=Path, default=Path('superhuman-v1.41-upgrade'))
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--case', help='Optional dotted unittest case for focused diagnosis')
    args = parser.parse_args()
    source = args.source.resolve()
    package = args.package.resolve()
    if not (source / 'superhuman/__init__.py').is_file():
        parser.error('Source must contain a complete superhuman package')
    if not (package / 'run_checks.py').is_file():
        parser.error('Package must contain run_checks.py')
    env = {key: value for key, value in os.environ.items() if key.upper() in {
        'PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP', 'LANG', 'LC_ALL',
        'PATHEXT', 'SYSTEMDRIVE', 'USERPROFILE', 'HOME'}}
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHON_DOTENV_DISABLED='1',
               PYTHONIOENCODING='utf-8')
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='workforce-checks-') as directory:
        with args.log.open('w', encoding='utf-8') as log:
            result = subprocess.run([sys.executable, '-c', CHILD, str(source),
                str(package / 'tests'), str(package / 'run_checks.py'), args.case or ''], cwd=directory,
                env=env, stdout=log, stderr=subprocess.STDOUT)
    print(f'Offline checks exit={result.returncode}; log={args.log}')
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
