import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'src/launcher/launcher'))
from build_package import build
import update_engine as engine
import unified_updater as updater

class LauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.temp.name)
        for component in ('tracker', 'launcher'):
            build(component, 'a' * 40, cls.folder / component)
        cls.tracker = (cls.folder / 'tracker/dokkaebi-app.zip').read_bytes()
        cls.launcher_version = json.loads((ROOT / 'release-config/launcher.json').read_text())['version']
        cls.launcher = (cls.folder / 'launcher/dokkaebi-launcher.zip').read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_real_launcher_manifest(self):
        files = updater.validate_launcher_archive(self.launcher, self.launcher_version)
        self.assertEqual(len(files), 93)

    def test_release_candidate_matches_ui_and_does_not_reuse_supplied_version(self):
        self.assertEqual(self.launcher_version, '0.0.3')
        source = (ROOT / 'src/launcher/launcher.pyw').read_text(encoding='utf-8')
        self.assertIn("DISPLAY_VERSION = 'v" + self.launcher_version + "'", source)
        self.assertTrue(updater.is_update({'kind':'launcher', 'version':self.launcher_version,
                         'tag':'launcher-v'+self.launcher_version}, 'launcher', '0.0.2'))

    def test_separate_discovery(self):
        def release(kind, version):
            name = 'dokkaebi-launcher.zip' if kind == 'launcher' else 'dokkaebi-app.zip'
            return {'tag_name': kind + '-v' + version, 'assets': [
                {'name': name, 'size': 100, 'digest': 'sha256:' + 'a'*64, 'browser_download_url': 'https://github.com/package'},
                {'name': name + '.sha256', 'browser_download_url': 'https://github.com/hash'}]}
        data = [release('launcher', '0.0.2'), release('tracker', '0.0.1'), release('launcher', '0.0.1')]
        with patch.object(updater, 'github_get', return_value=json.dumps(data).encode()):
            found = updater.get_available_releases('owner/repo')
        self.assertEqual(found['launcher']['version'], '0.0.2')
        self.assertEqual(found['app']['version'], '0.0.1')

    def test_download_hash_mismatch(self):
        with patch.object(engine, 'github_get', side_effect=[b'a'*64, b'corrupted']):
            with self.assertRaises(ValueError):
                engine.get_release_zip({'sha_url':'https://github.com/hash','url':'https://github.com/package'})

    def test_install_rollback_preserves_records_and_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = engine.Store(root)
            old = root / 'versions/8.0.0'
            old.mkdir(); (old / 'tracker.py').write_text('# original')
            (root / 'launcher.pyw').write_text('# original launcher')
            store.set_repo('owner/repo')
            (store.data / 'combat_power.csv').write_bytes(b'original records')
            (store.data / 'config.json').write_bytes(b'{"font_size":14}')
            (store.data / 'assets/user_background.png').write_bytes(b'original art')
            before = {p: p.read_bytes() for p in store.data.rglob('*') if p.is_file()}
            before[store.settings_file] = store.settings_file.read_bytes()
            store.install_package(self.tracker, '0.0.1')
            manager = updater.LauncherManager(root)
            manager.install(self.launcher, self.launcher_version)
            self.assertEqual(store.state['current'], '0.0.1')
            self.assertEqual(manager.active(), self.launcher_version)
            self.assertEqual(manager.rollback(), '0.0.0')
            self.assertEqual(store.rollback(), '8.0.0')
            self.assertTrue(all(p.read_bytes()==b for p,b in before.items()))

    def test_state_write_failure_keeps_active_tracker(self):
        with tempfile.TemporaryDirectory() as folder:
            store = engine.Store(folder)
            before = store.state
            with patch.object(engine, 'atomic_json', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    store.install_package(self.tracker, '0.0.1')
            self.assertEqual(store.state, before)

    def test_existing_modified_tracker_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            store = engine.Store(folder)
            store.install_package(self.tracker, '0.0.1')
            (store.current_dir() / 'tracker.py').write_text('# damaged')
            with self.assertRaises(ValueError):
                store.install_package(self.tracker, '0.0.1')

    def test_failed_launcher_activation_preserves_state(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = updater.LauncherManager(folder)
            with patch.object(updater, 'atomic_json', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    manager.install(self.launcher, self.launcher_version)
            self.assertEqual(manager.active(), '0.0.0')

if __name__ == '__main__':
    unittest.main()
