import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import host_transition as transition


class HostTransitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Windows CI TEMP may use RUNNER~1 while transition resolves runneradmin.
        # Fault injection must target the same canonical destination.
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'installation'
        self.root.mkdir()
        self.package = self.base / 'package'
        self.package.mkdir()
        self.backup = self.base / 'backup'
        self.original = (ROOT / 'tests/fixtures/installed_bootstrap/launch_host.pyw').read_bytes()
        self.host = self.root / 'launch_host.pyw'
        self.host.write_bytes(self.original)
        self.payload = (ROOT / 'src/bootstrap/launch_host.pyw').read_bytes()
        (self.package / 'launch_host.pyw').write_bytes(self.payload)
        (self.package / 'transition.json').write_text(json.dumps({'schema':1,
            'old_sha256':transition.OLD_HOST, 'new_sha256':transition.digest(self.payload)}))
        entry = self.root / 'launcher_versions/0.0.1/launcher.pyw'
        entry.parent.mkdir(parents=True)
        entry.write_text('pass')
        (self.root / 'launcher_runtime.json').write_text('{"current":"0.0.1"}')
        self.protected = {}
        for name in ['user_data/records.csv','launcher_settings.json','user_data/assets/background.png']:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'unchanged fixture')
            self.protected[path] = path.read_bytes()

    def test_apply_repeat_rollback_preserves_files(self):
        transition.apply(self.root, self.package, self.backup)
        self.assertEqual(self.host.read_bytes(), self.payload)
        self.assertIn('already', transition.apply(self.root, self.package, self.backup))
        transition.rollback(self.root, self.backup)
        self.assertEqual(self.host.read_bytes(), self.original)
        self.assertIn('already', transition.rollback(self.root, self.backup))
        self.assertTrue(all(p.read_bytes() == b for p,b in self.protected.items()))

    def test_payload_and_unknown_host_rejected(self):
        (self.package / 'launch_host.pyw').write_bytes(b'corrupted')
        with self.assertRaises(ValueError):transition.apply(self.root,self.package,self.backup)
        self.assertFalse(self.backup.exists())
        (self.package / 'launch_host.pyw').write_bytes(self.payload)
        self.host.write_bytes(b'unknown')
        with self.assertRaises(ValueError):transition.apply(self.root,self.package,self.backup)

    def test_failed_swap_leaves_original_and_backup(self):
        original_replace = transition.os.replace
        def fail(src, dst):
            if Path(dst) == self.host:raise OSError('simulated locked file')
            return original_replace(src,dst)
        with patch.object(transition.os, 'replace', side_effect=fail):
            with self.assertRaises(OSError):transition.apply(self.root,self.package,self.backup)
        self.assertEqual(self.host.read_bytes(),self.original)
        self.assertEqual((self.backup/'launch_host.pyw').read_bytes(),self.original)

    def test_interruption_after_swap_recovers_original(self):
        original_replace = transition.replace
        def interrupt(path,data):
            original_replace(path,data)
            if path == self.host and data == self.payload:raise KeyboardInterrupt()
        with patch.object(transition, 'replace', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):transition.apply(self.root,self.package,self.backup)
        self.assertEqual(self.host.read_bytes(),self.original)

    def test_tampered_backup_and_host_refuse_rollback(self):
        transition.apply(self.root,self.package,self.backup)
        (self.backup/'launch_host.pyw').write_bytes(b'bad')
        with self.assertRaises(ValueError):transition.rollback(self.root,self.backup)
        (self.backup/'launch_host.pyw').write_bytes(self.original)
        self.host.write_bytes(b'changed later')
        with self.assertRaises(ValueError):transition.rollback(self.root,self.backup)

    def test_pending_or_nested_backup_rejected(self):
        with self.assertRaises(ValueError):transition.apply(self.root,self.package,self.root/'backup')
        (self.root/'launcher_runtime.json').write_text('{"current":"0.0.1","pending":{"attempts":1}}')
        with self.assertRaises(ValueError):transition.apply(self.root,self.package,self.backup)
