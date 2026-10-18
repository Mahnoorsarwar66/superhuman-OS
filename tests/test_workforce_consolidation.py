import json
from pathlib import Path
import tempfile
import unittest

from tools.consolidate_workforce_source import consolidate, restore
from tools.workforce_baseline import inventory


class ConsolidationTests(unittest.TestCase):
    def setup_capture(self, directory):
        root = Path(directory) / 'checkout'
        captured = Path(directory) / 'capture'
        for path in (root, captured):
            (path / 'superhuman').mkdir(parents=True)
        (root / 'superhuman/__init__.py').write_text('VERSION = 1\n')
        (captured / 'superhuman/__init__.py').write_text('VERSION = 2\n')
        (captured / 'superhuman/new.py').write_text('VALUE = 3\n')
        expected = inventory(root)
        report = inventory(captured)
        (captured / 'source-provenance.json').write_text(json.dumps({
            'source_files': report['source_files'],
            'server_source_fingerprint': report['source_fingerprint']}))
        return root, captured, expected, root / '.workforce/backup'

    def test_consolidation_preserves_old_source_and_private_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root, captured, expected, backup = self.setup_capture(directory)
            (root / '.env').write_text('PRIVATE_SENTINEL')
            (root / 'data').mkdir()
            (root / 'data/records.db').write_bytes(b'PRIVATE_STATE')
            receipt = consolidate(root, captured, expected, backup)
            self.assertEqual((backup / 'superhuman/__init__.py').read_text(), 'VERSION = 1\n')
            self.assertEqual((root / 'superhuman/__init__.py').read_text(), 'VERSION = 2\n')
            self.assertEqual((root / 'data/records.db').read_bytes(), b'PRIVATE_STATE')
            self.assertEqual((root / '.env').read_text(), 'PRIVATE_SENTINEL')
            self.assertEqual(len(receipt['changed_files']), 2)

    def test_local_edits_after_inventory_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root, captured, expected, backup = self.setup_capture(directory)
            (root / 'superhuman/__init__.py').write_text('OWNER_EDIT = True\n')
            with self.assertRaisesRegex(ValueError, 'Local source changed'):
                consolidate(root, captured, expected, backup)
            self.assertFalse(backup.exists())
            self.assertEqual((root / 'superhuman/__init__.py').read_text(), 'OWNER_EDIT = True\n')

    def test_changed_capture_is_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root, captured, expected, backup = self.setup_capture(directory)
            (captured / 'superhuman/new.py').write_text('CHANGED = True\n')
            with self.assertRaisesRegex(ValueError, 'provenance'):
                consolidate(root, captured, expected, backup)
            self.assertFalse(backup.exists())

    def test_restore_recovers_source_and_removes_only_added_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root, captured, expected, backup = self.setup_capture(directory)
            consolidate(root, captured, expected, backup)
            restore(root, backup)
            self.assertEqual(inventory(root)['source_files'], expected['source_files'])
            self.assertFalse((root / 'superhuman/new.py').exists())
            self.assertFalse((root / 'source-provenance.json').exists())

    def test_restore_refuses_to_overwrite_subsequent_owner_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root, captured, expected, backup = self.setup_capture(directory)
            consolidate(root, captured, expected, backup)
            (root / 'superhuman/new.py').write_text('OWNER_EDIT = True\n')
            with self.assertRaisesRegex(ValueError, 'preserve edits'):
                restore(root, backup)
            self.assertEqual((root / 'superhuman/new.py').read_text(), 'OWNER_EDIT = True\n')


if __name__ == '__main__':
    unittest.main()
