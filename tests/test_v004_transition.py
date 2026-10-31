"""Additional host transition regression tests for the v0.0.4 staged code."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import host_transition


class DualHostTransitionTests(unittest.TestCase):
    def check(self, old_host, current):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            root=base/'install';root.mkdir()
            (root/'launch_host.pyw').write_bytes(old_host)
            entry=root/'launcher_versions'/current/'launcher.pyw'
            entry.parent.mkdir(parents=True)
            entry.write_text('pass',encoding='utf-8')
            (root/'launcher_runtime.json').write_text(json.dumps({'current':current}))
            (root/'user_data').mkdir()
            record=root/'user_data/combat_power.csv'
            record.write_bytes(b'123,456')
            pkg=base/'package';pkg.mkdir()
            new=(ROOT/'src/bootstrap/launch_host.pyw').read_bytes()
            (pkg/'launch_host.pyw').write_bytes(new)
            (pkg/'transition.json').write_text(json.dumps({'schema':1,
                'old_sha256':host_transition.OLD_HOST,
                'new_sha256':hashlib.sha256(new).hexdigest()}))
            backup=base/'backup'
            host_transition.apply(root,pkg,backup)
            self.assertEqual((root/'launch_host.pyw').read_bytes(),new)
            self.assertEqual(record.read_bytes(),b'123,456')
            host_transition.rollback(root,backup)
            self.assertEqual((root/'launch_host.pyw').read_bytes(),old_host)
            self.assertEqual(record.read_bytes(),b'123,456')

    def test_previous_v003_host(self):
        old=(ROOT/'tests/fixtures/v003_launch_host.pyw').read_bytes()
        self.assertEqual(hashlib.sha256(old).hexdigest(),host_transition.PREVIOUS_HOST)
        self.check(old,'0.0.3')

    def test_reject_unknown_host(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'launch_host.pyw').write_bytes(b'invalid')
            (root/'launcher_runtime.json').write_text('{"current":"0.0.3"}')
            entry=root/'launcher_versions/0.0.3/launcher.pyw'
            entry.parent.mkdir(parents=True)
            entry.write_text('pass')
            pkg=root/'package';pkg.mkdir()
            new=(ROOT/'src/bootstrap/launch_host.pyw').read_bytes()
            (pkg/'launch_host.pyw').write_bytes(new)
            (pkg/'transition.json').write_text(json.dumps({'schema':1,'old_sha256':host_transition.OLD_HOST,
                'new_sha256':hashlib.sha256(new).hexdigest()}))
            with self.assertRaisesRegex(ValueError,'Unknown installed host'):
                host_transition.inspect(root,pkg)

    def test_host_identity_is_pinned(self):
        self.assertEqual(host_transition.PREVIOUS_HOST,
             hashlib.sha256((ROOT/'tests/fixtures/v003_launch_host.pyw').read_bytes()).hexdigest())


if __name__=='__main__':unittest.main()
