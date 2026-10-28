import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from queuecare.inbox import claim, finish, initialize, publish, read_event


class InboxTransportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = initialize(Path(self.directory.name) / "inbox")

    def test_partial_file_is_not_claimed_and_input_is_preserved(self):
        (self.root / 'incoming' / 'partial.part').write_text('{')
        self.assertEqual(claim(self.root), '')
        publish(self.root, '{"id":"one"}')
        token = claim(self.root)
        self.assertEqual(read_event(self.root, token), '{"id":"one"}')
        self.assertEqual(claim(self.root), '')
        result = json.loads(finish(self.root, token, '{"ok":true,"state":"held"}'))
        self.assertEqual(result['disposition'], 'processed')
        self.assertEqual((self.root / 'processed' / token).read_text(), '{"id":"one"}')
        self.assertEqual(json.loads((self.root / 'receipts' / (token+'.json')).read_text()), result)

    def test_bad_utf8_and_oversize_files_can_be_quarantined_without_losing_input(self):
        for data in (b'\xff', b'x' * 16385):
            (self.root / 'incoming' / 'bad.json').write_bytes(data)
            token = claim(self.root)
            with self.assertRaises((ValueError, UnicodeDecodeError)):
                read_event(self.root, token)
            finish(self.root, token, '{"ok":false}', True)
            self.assertEqual((self.root / 'rejected' / token).read_bytes(), data)

    def test_same_filename_gets_distinct_claims(self):
        tokens = []
        for content in ('first', 'second'):
            (self.root / 'incoming' / 'same.json').write_text(content)
            tokens.append(claim(self.root))
        self.assertNotEqual(*tokens)
        self.assertEqual([read_event(self.root, t) for t in tokens], ['first', 'second'])

    def test_interrupted_claim_remains_for_manual_recovery(self):
        publish(self.root, '{"id":"one"}')
        token = claim(self.root)
        self.assertEqual(claim(self.root), '')
        self.assertTrue((self.root / 'processing' / token).exists())

    def test_long_multibyte_filename_can_be_claimed(self):
        (self.root / 'incoming' / ('한' * 80 + '.json')).write_text('{}')
        token = claim(self.root)
        self.assertLessEqual(len(token.encode('utf-8')), 194)
        self.assertEqual(read_event(self.root, token), '{}')

    def test_token_cannot_escape_processing_directory(self):
        for token in ('../secret', '/tmp/secret', '..', 'x\\secret'):
            with self.assertRaises(ValueError):
                read_event(self.root, token)

    def test_symlink_target_is_not_read_or_modified(self):
        target = Path(self.directory.name) / 'outside.txt'
        target.write_text('keep me')
        link = self.root / 'incoming' / 'link.json'
        try:
            link.symlink_to(target)
        except OSError:
            self.skipTest('Symlink creation unavailable on this host')
        token = claim(self.root)
        with self.assertRaises(ValueError):
            read_event(self.root, token)
        finish(self.root, token, '{"ok":false}', True)
        self.assertEqual(target.read_text(), 'keep me')


if __name__ == '__main__':
    unittest.main()
