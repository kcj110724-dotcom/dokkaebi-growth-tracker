"""Backup, checksum and no-data-touch checks for the host-only installer."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import host_recovery_upgrade as upgrade

BASELINE = Path(__file__).resolve().parents[2]/'dokkaebi_original/src/bootstrap/launch_host.pyw'


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'installation'
        self.root.mkdir()
        self.host=self.root/'launch_host.pyw'
        # Original fixture is shipped as a test fixture in the standalone bundle.
        original=(Path(__file__).resolve().parents[1]/'tests/fixtures/v003_launch_host.pyw').read_bytes()
        self.host.write_bytes(original)
        self.assertEqual(hashlib.sha256(original).hexdigest(),upgrade.KNOWN_HOST)
        self.backup=Path(self.temp.name)/'host-backup'
        current=self.root/'launcher_versions/0.0.3/launcher.pyw'
        current.parent.mkdir(parents=True)
        current.write_text('pass',encoding='utf-8')
        (self.root/'launcher_runtime.json').write_text(json.dumps({'current':'0.0.3','previous':['0.0.1']}))
        data=self.root/'user_data';data.mkdir()
        (data/'combat_power.csv').write_bytes(b'16800,18099\n')
        (self.root/'launcher_settings.json').write_bytes(b'{"theme":"original"}')
        self.nonhost={p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*')
                      if p.is_file() and p!=self.host}

    def preserved(self):
        for rel,content in self.nonhost.items():
            self.assertEqual((self.root/rel).read_bytes(),content)

    def test_install_then_rollback_with_receipt(self):
        _,_,current=upgrade.inspect(self.root)
        self.assertEqual(current,upgrade.KNOWN_HOST)
        self.assertIn('complete',upgrade.apply(self.root,self.backup))
        self.assertEqual(upgrade.digest(self.host.read_bytes()),upgrade.NEW_HOST)
        self.assertTrue((self.backup/'receipt.json').is_file())
        self.preserved()
        self.assertIn('Already installed',upgrade.apply(self.root,self.backup))
        self.assertIn('restored',upgrade.rollback(self.root,self.backup))
        self.assertEqual(upgrade.digest(self.host.read_bytes()),upgrade.KNOWN_HOST)
        self.preserved()

    def test_reject_pending_update(self):
        path=self.root/'launcher_runtime.json'
        path.write_text(json.dumps({'current':'0.0.3','pending':{'version':'0.0.3'}}))
        with self.assertRaisesRegex(ValueError,'pending'):
            upgrade.apply(self.root,self.backup)
        self.assertFalse(self.backup.exists())
        self.preserved_except_runtime(path)

    def preserved_except_runtime(self,excluded):
        for rel,content in self.nonhost.items():
            if self.root/rel != excluded:
                self.assertEqual((self.root/rel).read_bytes(),content)

    def test_reject_unknown_host_no_backup(self):
        self.host.write_bytes(b'unexpected file')
        with self.assertRaisesRegex(ValueError,'Unknown existing host'):
            upgrade.apply(self.root,self.backup)
        self.assertFalse(self.backup.exists())

    def test_reject_backup_inside_installation(self):
        with self.assertRaisesRegex(ValueError,'separate'):
            upgrade.apply(self.root,self.root/'backups/new-host-backup')
        self.assertEqual(upgrade.digest(self.host.read_bytes()),upgrade.KNOWN_HOST)

    def test_reject_foreign_rollback_receipt(self):
        upgrade.apply(self.root,self.backup)
        receipt=self.backup/'receipt.json'
        info=json.loads(receipt.read_text())
        info['root']=str(Path(self.temp.name)/'other-install')
        receipt.write_text(json.dumps(info))
        with self.assertRaisesRegex(ValueError,'does not match'):
            upgrade.rollback(self.root,self.backup)
        self.assertEqual(upgrade.digest(self.host.read_bytes()),upgrade.NEW_HOST)

    def test_reject_modified_new_host_rollback(self):
        upgrade.apply(self.root,self.backup)
        self.host.write_text('modified')
        with self.assertRaisesRegex(ValueError,'modified'):
            upgrade.rollback(self.root,self.backup)


if __name__=='__main__':unittest.main()
