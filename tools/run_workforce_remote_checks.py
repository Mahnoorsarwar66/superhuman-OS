"""Run captured-source regressions in disposable server /tmp state, never app/data."""
import argparse
import io
import json
from pathlib import Path
import shlex
import subprocess
import zipfile

from run_workforce_checks import CHILD
from workforce_baseline import source_inventory, sha256


REMOTE = r'''
import io, os, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path
raw = sys.stdin.buffer.read()
memory = Path('/dev/shm')
temp_parent = str(memory) if memory.is_dir() and shutil.disk_usage(memory).free > 128 * 1024 * 1024 else None
with tempfile.TemporaryDirectory(prefix='workforce-offline-', dir=temp_parent) as directory:
    root = Path(directory)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for member in archive.infolist():
            dest = root / member.filename
            if not dest.resolve().is_relative_to(root) or member.is_dir():
                raise ValueError('Unsafe test archive')
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(archive.read(member))
    env = {key: value for key, value in os.environ.items() if key in
           ('PATH', 'LANG', 'LC_ALL', 'HOME', 'TMPDIR')}
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHON_DOTENV_DISABLED='1', PYTHONIOENCODING='utf-8')
    state = root / 'state'
    state.mkdir()
    env['TMPDIR'] = str(state)
    print('Offline test storage:', 'tmpfs' if temp_parent else 'system temporary directory', flush=True)
    print('This suite does not establish power-loss durability.', flush=True)
    result = subprocess.run([sys.executable, str(root / 'offline_child.py'),
        str(root / 'source'), str(root / 'tests'), str(root / 'run_checks.py'), ''],
        cwd=state, env=env)
    raise SystemExit(result.returncode)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--package', type=Path, default=Path('superhuman-v1.41-upgrade'))
    parser.add_argument('--key', type=Path, required=True)
    parser.add_argument('--host', default='root@167.71.196.20')
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--candidate', action='store_true', help='Evaluate local changes against captured baseline provenance')
    parser.add_argument('--extra-test', type=Path, action='append', default=[])
    args = parser.parse_args()
    report = json.loads((args.source / 'source-provenance.json').read_text(encoding='utf-8'))
    files = source_inventory(args.source.resolve())
    if files != report['source_files'] and not args.candidate:
        parser.error('Captured source changed; refresh provenance before baseline evaluation')
    extra_names=[]
    for path in args.extra_test:
        if path.suffix!='.py' or not path.name.startswith('test_') or (args.package/'tests'/path.name).exists():
            parser.error('Extra tests must be distinct test_*.py modules')
        extra_names.append(path.stem)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in files:
            archive.writestr('source/' + name, (args.source / name).read_bytes())
        for path in sorted((args.package / 'tests').glob('*.py')):
            archive.writestr('tests/' + path.name, path.read_bytes())
        for path in args.extra_test:archive.writestr('tests/'+path.name,path.read_bytes())
        if extra_names:
            archive.writestr('base_checks.py',(args.package/'run_checks.py').read_bytes())
            runner="import runpy,unittest\nfrom pathlib import Path\ntry:\n runpy.run_path(str(Path(__file__).with_name('base_checks.py')),run_name='__main__')\nexcept SystemExit as exc:\n if exc.code not in (None,0):raise\nsuite=unittest.TestSuite()\n"
            runner+='\n'.join('suite.addTests(unittest.defaultTestLoader.loadTestsFromName('+repr(name)+'))' for name in extra_names)
            runner+="\nresult=unittest.TextTestRunner(verbosity=2).run(suite)\nraise SystemExit(0 if result.wasSuccessful() else 1)\n"
            archive.writestr('run_checks.py',runner)
        else:archive.writestr('run_checks.py', (args.package / 'run_checks.py').read_bytes())
        archive.writestr('offline_child.py', CHILD)
    command = ['ssh', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o',
        'ConnectTimeout=15', '-i', str(args.key), args.host,
        '/home/superhuman/app/.venv/bin/python -c ' + shlex.quote(REMOTE)]
    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.log.with_suffix('.manifest.json').write_text(json.dumps({
        'baseline_source_fingerprint':report['server_source_fingerprint'],
        'candidate_source_fingerprint':sha256(json.dumps(files,sort_keys=True).encode()),
        'source_files':files,'candidate':args.candidate,'extra_tests':extra_names,
        'changed_paths':[name for name,entry in files.items() if report['source_files'].get(name)!=entry],
    },indent=2)+'\n',encoding='utf-8')
    with args.log.open('wb') as log:
        result = subprocess.run(command, input=buffer.getvalue(), stdout=log,
                                stderr=subprocess.STDOUT)
    print(f'Isolated Linux offline checks exit={result.returncode}; log={args.log}')
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
