"""WF01 synthetic legacy-record migration and old-code readback; no real data."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile


PHASE = r'''
import hashlib, json, sqlite3, sys
from pathlib import Path
source, phase = sys.argv[1:]
sys.path.insert(0, source)
from superhuman.projects import engine as p
path = Path('fixture.db')
def records():
    with sqlite3.connect(path) as db:
        return {table: db.execute('SELECT * FROM ' + table + ' ORDER BY 1,2').fetchall()
                for table in ('projects', 'project_tasks')}
if phase == 'seed':
    p.initialize(path)
    pid = p.create('marketing', 'Synthetic legacy objective', 'Retain this brief', 9, path)
    with p.connect(path) as db:
        db.execute("UPDATE projects SET used_calls=2,status='needs_review' WHERE id=?", (pid,))
        db.execute("INSERT INTO project_tasks(project_id,id,kind,title,details,deps,checks,status,output,review_note) VALUES(?, 'final','collab','Synthetic memo','Retain instructions','[]','[]','needs_review','legacy-output.txt','Retain review note')", (pid,))
    Path('legacy-output.txt').write_bytes(b'Synthetic accepted draft bytes.\n')
    Path('expected.json').write_text(json.dumps({'project_id': pid, 'records': records(),
        'output_sha256': hashlib.sha256(Path('legacy-output.txt').read_bytes()).hexdigest()}))
else:
    expected = json.loads(Path('expected.json').read_text())
    if phase == 'migrate':
        from superhuman.team import store as team
        from superhuman.milestones import store as milestones
        from superhuman.assurance import store as assurance
        from superhuman.organisation import store as organisation
        for _ in range(2):
            team.initialize(path)
            milestones.initialize(path)
            assurance.initialize(path)
            organisation.initialize(path)
    assert json.loads(json.dumps(records())) == expected['records'], 'Legacy business records changed'
    assert hashlib.sha256(Path('legacy-output.txt').read_bytes()).hexdigest() == expected['output_sha256']
    project = p.get(expected['project_id'], path)
    assert project['used_calls'] == 2 and project['max_calls'] == 9
    assert project['status'] == 'needs_review'
    assert project['tasks'][0]['review_note'] == 'Retain review note'
print(phase.upper() + '_PASS: synthetic project, task, call consumption, review note and output bytes')
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--log', type=Path, required=True)
    args = parser.parse_args()
    before, after = args.before.resolve(), args.after.resolve()
    env = {key: value for key, value in os.environ.items() if key.upper() in {
        'PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP', 'LANG', 'LC_ALL',
        'PATHEXT', 'SYSTEMDRIVE'}}
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHON_DOTENV_DISABLED='1', PYTHONIOENCODING='utf-8')
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='workforce-migration-') as directory:
        with args.log.open('w', encoding='utf-8') as log:
            for source, phase in ((before, 'seed'), (after, 'migrate'), (before, 'readback')):
                result = subprocess.run([sys.executable, '-c', PHASE, str(source), phase],
                    cwd=directory, env=env, stdout=log, stderr=subprocess.STDOUT)
                if result.returncode:
                    print(f'Migration rehearsal failed in {phase}; log={args.log}')
                    return result.returncode
    print(f'Synthetic migration and old-code readback passed; log={args.log}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
