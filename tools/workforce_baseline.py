"""Read-only WF01 inventory. Does not import the app or read configuration values."""
import argparse
import ast
from contextlib import closing
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

SOURCE_SUFFIXES = ('.py', '.js', '.css', '.html', '.png', '.svg', '.ico', '.woff2')
SOURCE_DATA = {'superhuman/organisation/seed.json'}
MIGRATION_MARKERS = {'milestone_migrations': 'id', 'practice_migrations': 'id',
                     'ux_migrations': 'id', 'mailflow_migrations': 'name'}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def safe_file(root, path):
    return path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root)


def source_inventory(root):
    records = {}
    app = root / 'superhuman'
    for path in sorted(app.rglob('*')):
        if not safe_file(root, path) or '__pycache__' in path.parts:
            continue
        if path.suffix not in SOURCE_SUFFIXES and path.relative_to(root).as_posix() not in SOURCE_DATA:
            continue
        data = path.read_bytes()
        record = {'sha256': sha256(data), 'bytes': len(data)}
        if path.suffix == '.py':
            try:
                ast.parse(data, filename=str(path))
                record['syntax'] = 'pass'
            except (SyntaxError, UnicodeError):
                record['syntax'] = 'fail'
        records[path.relative_to(root).as_posix()] = record
    return records


def package_inventory(root, sources):
    packages = []
    for manifest in sorted(root.glob('superhuman-v*-upgrade/FILES.json')):
        if not safe_file(root, manifest):
            continue
        try:
            entries = json.loads(manifest.read_text(encoding='utf-8'))
            if not isinstance(entries, dict) or not entries:
                raise ValueError('Expected a nonempty file manifest')
            if not isinstance(entries, dict) or not entries:
                raise ValueError('Expected a nonempty file manifest')
            counts = {'payload_verified': 0, 'payload_invalid': 0,
                      'local_matches_after': 0, 'local_missing': 0, 'local_differs': 0}
            for name, entry in entries.items():
                relative = Path(name)
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('Unsafe manifest path')
                payload = manifest.parent / 'payload' / relative
                valid = (safe_file(root, payload) and
                         sha256(payload.read_bytes()) == entry['after'])
                counts['payload_verified' if valid else 'payload_invalid'] += 1
                local = sources.get('superhuman/' + relative.as_posix())
                key = ('local_missing' if local is None else 'local_matches_after'
                       if local['sha256'] == entry['after'] else 'local_differs')
                counts[key] += 1
            packages.append({'package': manifest.parent.name, 'manifest_sha256':
                             sha256(manifest.read_bytes()), 'files': len(entries), **counts,
                             'installation_proven': False})
        except (ValueError, KeyError, TypeError):
            packages.append({'package': manifest.parent.name, 'error': 'invalid_manifest',
                             'installation_proven': False})
    return packages


def database_inventory(root):
    """Inspect schema only, in SQLite read-only mode; never initialize application tables."""
    records = []
    for path in sorted((root / 'data').rglob('*')):
        if path.suffix not in ('.db', '.sqlite', '.sqlite3') or not safe_file(root, path):
            continue
        record = {'path': path.relative_to(root).as_posix()}
        try:
            with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1)) as db:
                db.execute('PRAGMA query_only=ON')
                db.execute('BEGIN')
                version = db.execute('PRAGMA user_version').fetchone()[0]
                schema = db.execute("SELECT type, name, tbl_name, sql FROM sqlite_schema "
                                    "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name").fetchall()
                table_names = {row[1] for row in schema if row[0] == 'table'}
                markers = {}
                for table, column in MIGRATION_MARKERS.items():
                    if table in table_names:
                        # Both identifiers come from a fixed application-metadata allowlist.
                        markers[table] = [row[0] for row in db.execute(
                            f'SELECT {column} FROM {table} ORDER BY {column} LIMIT 100')]
                record.update(user_version=version, schema_sha256=sha256(
                    json.dumps(schema, ensure_ascii=True).encode()),
                    table_count=sum(row[0] == 'table' for row in schema),
                    migration_markers=markers,
                    migration_state='marker metadata only; full migration compatibility unverified')
        except sqlite3.Error:
            record['error'] = 'schema_unavailable'
        records.append(record)
    return records


def inventory(root, include_schema=False):
    root = Path(root).resolve()
    sources = source_inventory(root)
    try:
        result = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                                capture_output=True, text=True, timeout=5, check=True)
        commit = result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = None
    dependencies = {}
    for name in ('openai', 'fastapi', 'uvicorn', 'python-dotenv', 'python-multipart',
                 'httpx', 'pypdf', 'python-docx', 'openpyxl', 'reportlab'):
        try:
            dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = None
    requirements = {}
    for name in ('requirements.txt', 'requirements-v19.txt'):
        path = root / name
        if safe_file(root, path):
            requirements[name] = {'sha256': sha256(path.read_bytes()),
                                  'specification': path.read_text(encoding='utf-8').splitlines()}
    return {'report_format': 1, 'scope': 'local checkout only', 'commit': commit,
            'runtime_version': 'unverified', 'deployed_state': 'not inspected',
            'python': sys.version.split()[0], 'dependencies': dependencies,
            'requirements': requirements, 'source_files': sources,
            'summary': {'source_files': len(sources),
                        'python_syntax_pass': sum(v.get('syntax') == 'pass' for v in sources.values()),
                        'python_syntax_fail': sum(v.get('syntax') == 'fail' for v in sources.values())},
            'summary': {'source_files': len(sources),
                        'python_syntax_pass': sum(v.get('syntax') == 'pass' for v in sources.values()),
                        'python_syntax_fail': sum(v.get('syntax') == 'fail' for v in sources.values())},
            'source_fingerprint': sha256(json.dumps(sources, sort_keys=True).encode()),
            'packages': package_inventory(root, sources),
            'databases': database_inventory(root) if include_schema else 'not inspected',
            'configuration_values': 'not read', 'provider_calls': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--include-schema', action='store_true')
    args = parser.parse_args()
    print(json.dumps(inventory(args.root, args.include_schema), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
