"""Staged, reversible v1.26 code upgrade. Run from the app root with services stopped."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from uuid import uuid4
from patches import FILES, build, canonical, source_files, manifest_files, expected_source


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_write(path, data):
    path = Path(path)
    temporary = path.with_name('.' + path.name + '.' + uuid4().hex + '.tmp')
    try:
        with temporary.open('wb') as stream:
            stream.write(data)
        if path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def rollback(root, directory):
    backup = Path(directory).resolve()
    allowed = root / 'backups'
    if not backup.is_relative_to(allowed):
        raise ValueError('Choose the v1.26 backup directory inside this app/backups')
    manifest = json.loads((backup / 'manifest.json').read_text())
    if manifest['root'] != str(root):
        raise ValueError('Backup belongs to a different app directory')
    restore_files=manifest_files(manifest)
    for relative, installed_hash in manifest['installed_hashes'].items():
        path = root / relative
        if not path.is_file() or digest(path) != installed_hash:
            raise ValueError('Changed installed source; rollback refused: ' + relative)
    package = root / 'superhuman/team'
    expected_package = set(manifest['package_files']) | {'installation.json'}
    found = {str(p.relative_to(package)) for p in package.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    if found != expected_package:
        raise ValueError('Team package has additional files; inspect before rollback')
    for relative, expected_hash in manifest['before_hashes'].items():
        name = Path(relative).relative_to('superhuman')
        if not (backup / name).is_file() or digest(backup / name) != expected_hash:
            raise ValueError('Backup source missing or changed: ' + relative)
    sys.path.insert(0,str(root))
    from superhuman.team.engine import quarantine_for_rollback
    quarantine_for_rollback()
    for name in restore_files:
        atomic_write(root / 'superhuman' / name, (backup / name).read_bytes())
    shutil.rmtree(package)
    print('Code rolled back. Team, memory, accounting, audit and existing records remain in data/. Worker paused; no services restarted.')


def main():
    global FILES
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--preflight', action='store_true', help='Fast source/dependency checks only; no tests or writes')
    parser.add_argument('--rollback', metavar='BACKUP_DIRECTORY')
    args = parser.parse_args()
    root = Path.cwd().resolve(); source = Path(__file__).resolve().parent
    FILES=source_files(root)
    if sum((args.check,args.preflight,bool(args.rollback)))>1:
        parser.error('Choose check, preflight or rollback')
    try:
        try:
            from cryptography.fernet import Fernet
        except ImportError:
            raise ValueError('The existing v1.12 cryptography dependency is missing; repair that environment first') from None
        if args.rollback:
            rollback(root, args.rollback); return
        for name in FILES:
            if not (root / 'superhuman' / name).is_file():
                raise ValueError('Run from the installed v1.25 app directory; missing superhuman/' + name)
        cli_source=(root/'superhuman/cli.py').read_text(encoding='utf-8')
        production_cli=(source/'reference/production_cli.py').read_text(encoding='utf-8')
        if canonical('cli.py',cli_source)==canonical('cli.py',production_cli) and 'core/orchestrator.py' not in FILES:
            raise ValueError('Reviewed production CLI requires its core/orchestrator.py companion; nothing changed')
        package = root / 'superhuman/team'
        payload = source / 'superhuman/team'
        package_files = {p.name: p for p in payload.glob('*.py')}
        if package.exists():
            manifest_path = package / 'installation.json'
            if not manifest_path.exists():
                # Private migration bundles carry Python source, not host-specific
                # installer manifests or old code backups. Recognise that state
                # without fabricating a rollback directory on the new host.
                if any(not (package / name).is_file() or digest(package / name) != digest(file)
                       for name, file in package_files.items()):
                    raise ValueError('Different Team package exists; nothing overwritten')
                for name in FILES:
                    actual = (root / 'superhuman' / name).read_text(encoding='utf-8')
                    expected = expected_source(name, actual, source / 'reference')
                    if canonical(name, actual) != canonical(name, expected):
                        raise ValueError('Different migrated v1.26 source: ' + name)
                print('Migrated v1.26 source verified. No changes made. No local rollback manifest is available.')
                return
            manifest = json.loads(manifest_path.read_text())
            manifest_files(manifest)
            for relative, sha in manifest['installed_hashes'].items():
                if not (root / relative).is_file() or digest(root / relative) != sha:
                    raise ValueError('Installed v1.26 source changed: ' + relative)
            if set(package_files) != set(manifest['package_files']) or any(digest(file) != manifest['payload_hashes'][name] for name, file in package_files.items()):
                raise ValueError('Different v1.26 payload; explicit upgrade needed')
            print('v1.26 is already installed and source checksums match. No changes made.'); return
        payload_before = {name:digest(file) for name,file in package_files.items()}
        before = {str(Path('superhuman') / name): digest(root / 'superhuman' / name) for name in FILES}
        edits = {name: build(name, (root / 'superhuman' / name).read_text(encoding='utf-8'), source / 'reference') for name in FILES}
        for file in package_files.values():
            ast.parse(file.read_text(encoding='utf-8'))
        if args.preflight:
            print('v1.26 preflight passed. Source/dependency checks only; no source, data or model changes.'); return
        with tempfile.TemporaryDirectory(prefix='superhuman-v126-check-') as directory:
            stage = Path(directory)
            shutil.copytree(root / 'superhuman', stage / 'superhuman',
                            ignore=shutil.ignore_patterns('__pycache__', '.env', '.env.*', '*.bak'))
            shutil.copytree(payload, stage / 'superhuman/team', ignore=shutil.ignore_patterns('__pycache__'))
            for name, text in edits.items():
                (stage / 'superhuman' / name).write_text(text, encoding='utf-8')
            env = dict(os.environ)
            env.pop('OPENAI_API_KEY', None)
            env.pop('SUPERHUMAN_KNOWLEDGE_DB', None)
            env.pop('SUPERHUMAN_MAIL_KEY_FILE', None)
            env.pop('SUPERHUMAN_PLANNING_DB', None)
            env['PYTHONPATH'] = str(stage)
            env['PYTHONDONTWRITEBYTECODE'] = '1'
            result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(source / 'tests'), '-v'], cwd=stage, env=env)
            if result.returncode:
                raise ValueError('Staged checks failed. Installed source and data were not changed.')
        if any(digest(file)!=payload_before[name] for name,file in package_files.items()):
            raise ValueError('Upgrade payload changed during checks; nothing installed')
        for relative, sha in before.items():
            if digest(root / relative) != sha:
                raise ValueError('Source changed during checks: ' + relative + '; stop editing and retry')
        if args.check:
            print('v1.26 checks passed. No installation, data changes or model requests.'); return
        backup = root / 'backups' / ('v1.26-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        backup.mkdir(parents=True, mode=0o700)
        for name in FILES:
            dest = backup / name; dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / 'superhuman' / name, dest)
        created_package = False
        try:
            # Add the package before switching the references that import it.
            staging_package = root / 'superhuman' / ('.team-' + uuid4().hex)
            try:
                shutil.copytree(payload, staging_package, ignore=shutil.ignore_patterns('__pycache__'))
                staging_package.rename(package); created_package = True
            finally:
                if staging_package.exists(): shutil.rmtree(staging_package)
            for name, text in edits.items():
                atomic_write(root / 'superhuman' / name, text.encode('utf-8'))
            installed = {str(Path('superhuman') / name): digest(root / 'superhuman' / name) for name in FILES}
            installed.update({str(Path('superhuman/team') / name): digest(package / name) for name in package_files})
            manifest = {'version': '1.26.0', 'root': str(root), 'backup': str(backup),
                        'before_hashes': before,
                        'installed_hashes': installed, 'package_files': sorted(package_files),
                        'payload_hashes': {name: digest(file) for name, file in package_files.items()}}
            raw = json.dumps(manifest, indent=2).encode('utf-8')
            atomic_write(package / 'installation.json', raw)
            atomic_write(backup / 'manifest.json', raw)
        except Exception:
            for name in FILES:
                atomic_write(root / 'superhuman' / name, (backup / name).read_bytes())
            if created_package: shutil.rmtree(package)
            raise
        print('Installed v1.26.0. Existing data, credentials, origin and service files retained.')
        print('No services started or model requests made. Restart web and worker after installation.')
        print('Rollback backup:', backup)
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
