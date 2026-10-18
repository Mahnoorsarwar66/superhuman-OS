import hashlib
import io
import unittest
import zipfile

from tools.capture_workforce_source import verified_members


class CaptureTests(unittest.TestCase):
    def archive(self, files):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        return buffer.getvalue()

    def report(self, files):
        return {'source_files': {name: {'sha256': hashlib.sha256(data).hexdigest()}
                                 for name, data in files.items()}}

    def test_only_exact_inventoried_source_is_accepted(self):
        files = {'superhuman/__init__.py': b'x = 1\n'}
        self.assertEqual(verified_members(self.archive(files), self.report(files)), files)
        with self.assertRaises(ValueError):
            verified_members(self.archive({'superhuman/__init__.py': b'x = 2\n'}), self.report(files))
        with self.assertRaises(ValueError):
            verified_members(self.archive({}), self.report(files))

    def test_private_and_traversal_paths_are_rejected_even_if_in_report(self):
        for name in ('superhuman/../../.env', '/superhuman/file.py',
                     'superhuman/installation.json', 'superhuman/a\\b.py'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                files = {name: b'private'}
                verified_members(self.archive(files), self.report(files))

    def test_required_packaged_seed_and_portraits_are_preserved(self):
        files = {'superhuman/organisation/seed.json': b'[]',
                 'superhuman/practice/assets/twin.png': b'\x89PNG\r\n\x1a\n'}
        self.assertEqual(verified_members(self.archive(files), self.report(files)), files)


if __name__ == '__main__':
    unittest.main()
