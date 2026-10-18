import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tools.workforce_baseline import inventory, sha256


class BaselineTests(unittest.TestCase):
    def test_inventory_does_not_import_application_or_expose_private_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'superhuman').mkdir()
            (root / 'superhuman/__init__.py').write_text("raise RuntimeError('do not import')")
            (root / '.env').write_text('OPENAI_API_KEY=PRIVATE_SENTINEL')
            (root / 'superhuman/installation.json').write_text('{"secret":"PRIVATE_SENTINEL"}')
            report = inventory(root)
            self.assertNotIn('PRIVATE_SENTINEL', json.dumps(report))
            self.assertEqual(report['source_files']['superhuman/__init__.py']['syntax'], 'pass')
            self.assertEqual(report['runtime_version'], 'unverified')

    def test_schema_read_does_not_change_records_or_leak_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data').mkdir()
            path = root / 'data/business.db'
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('CREATE TABLE records (content TEXT)')
                db.execute("INSERT INTO records VALUES ('PRIVATE_SENTINEL')")
                db.execute('PRAGMA user_version=7')
            before = path.read_bytes()
            report = inventory(root, include_schema=True)
            self.assertEqual(path.read_bytes(), before)
            self.assertNotIn('PRIVATE_SENTINEL', json.dumps(report))
            self.assertEqual(report['databases'][0]['table_count'], 1)
            self.assertEqual(report['databases'][0]['user_version'], 7)
            self.assertEqual(list((root / 'data').iterdir()), [path])

    def test_payload_presence_is_not_installation_and_tampering_is_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / 'superhuman-v1.41-upgrade'
            (package / 'payload').mkdir(parents=True)
            (package / 'payload/engine.py').write_bytes(b'x = 1\n')
            (package / 'FILES.json').write_text(json.dumps({
                'engine.py': {'after': sha256(b'x = 1\n')}}))
            report = inventory(root)['packages'][0]
            self.assertEqual(report['payload_verified'], 1)
            self.assertEqual(report['local_missing'], 1)
            self.assertFalse(report['installation_proven'])
            (package / 'payload/engine.py').write_bytes(b'x = 2\n')
            self.assertEqual(inventory(root)['packages'][0]['payload_invalid'], 1)

    def test_only_known_migration_metadata_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data').mkdir()
            with closing(sqlite3.connect(root / 'data/fixture.db')) as db, db:
                db.execute('CREATE TABLE milestone_migrations (id TEXT PRIMARY KEY)')
                db.execute("INSERT INTO milestone_migrations VALUES ('reading-tools-131')")
                db.execute('CREATE TABLE private_migrations (id TEXT)')
                db.execute("INSERT INTO private_migrations VALUES ('PRIVATE_SENTINEL')")
            report = inventory(root, include_schema=True)
            self.assertEqual(report['databases'][0]['migration_markers'],
                             {'milestone_migrations': ['reading-tools-131']})
            self.assertNotIn('PRIVATE_SENTINEL', json.dumps(report))

    def test_manifest_cannot_traverse_outside_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / 'superhuman-v1.41-upgrade'
            package.mkdir()
            (package / 'FILES.json').write_text(json.dumps({'../.env': {'after': 'x'}}))
            self.assertEqual(inventory(root)['packages'][0]['error'], 'invalid_manifest')


if __name__ == '__main__':
    unittest.main()
