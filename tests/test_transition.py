"""Component-bound legacy epoch reset and non-destructive directory aliases."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/launcher/launcher'))
from update_engine import Store
import update_engine as engine
from unified_updater import is_update, release_order, get_available_releases
import test_launcher as fixtures


class TransitionTests(unittest.TestCase):
    def test_epoch_policy_component_and_tag_binding(self):
        for kind,prefix in [('app','tracker'),('launcher','launcher')]:
            candidate={'kind':kind,'version':'0.0.2','tag':prefix+'-v0.0.2'}
            for old in ['8.0.0','9.9.9','v8.1.2']:
                self.assertTrue(is_update(candidate,kind,old))
            self.assertTrue(is_update(candidate,kind,'0.0.1'))
            self.assertFalse(is_update(candidate,kind,'0.0.2'))
            self.assertFalse(is_update(candidate,kind,'0.0.3'))
            self.assertFalse(is_update(candidate,'launcher' if kind=='app' else 'app','9.0.0'))
            self.assertFalse(is_update({**candidate,'tag':'v0.0.2'},kind,'9.0.0'))
            self.assertFalse(is_update({**candidate,'version':'9.0.0','tag':prefix+'-v9.0.0'},kind,'0.0.1'))
        self.assertGreater(release_order('app','1.0.0'),release_order('app','0.9.0'))

    def test_discovery_selects_modern_epoch_over_legacy_per_component(self):
        releases=[]
        for kind,prefix,asset in [('app','tracker','dokkaebi-app.zip'),('launcher','launcher','dokkaebi-launcher.zip')]:
            for version in ['9.0.0','0.0.2','8.0.0','0.0.1']:
                releases.append({'tag_name':prefix+'-v'+version,'assets':[
                    {'name':asset,'size':100,'digest':'sha256:'+'a'*64,'browser_download_url':'https://github.com/p'},
                    {'name':asset+'.sha256','browser_download_url':'https://github.com/h'}]})
        with patch('unified_updater.github_get',return_value=json.dumps(releases).encode()):
            result=get_available_releases('owner/repo')
        self.assertEqual(result['app']['version'],'0.0.2')
        self.assertEqual(result['launcher']['version'],'0.0.2')

    def test_alias_manual_rollback_and_canonical_precedence(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder)
            legacy=store.versions/'v8.0.0';legacy.mkdir()
            (legacy/'tracker.py').write_text('pass')
            modern=store.versions/'0.0.1';modern.mkdir()
            (modern/'tracker.py').write_text('pass')
            store.set_current('v8.0.0');store.set_current('0.0.1')
            self.assertEqual(store.rollback(),'8.0.0')
            self.assertEqual(store.current_dir(),legacy)
            canonical=store.versions/'8.0.0';canonical.mkdir()
            (canonical/'tracker.py').write_text('pass')
            self.assertEqual(store.current_dir(),canonical)
            self.assertEqual(store.known_versions(),['0.0.1','8.0.0'])
            self.assertTrue(legacy.is_dir())


class MigrationInstallTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.LauncherTests.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.LauncherTests.tearDownClass.__func__)
    # Reuse built real payloads, not simplified manifest fixtures.
    def test_legacy_transition_interruption_and_recovery(self):
        for old in ['8.0.0','9.0.0']:
            with tempfile.TemporaryDirectory() as folder:
                store=Store(folder)
                legacy=store.versions/('v'+old);legacy.mkdir()
                (legacy/'tracker.py').write_text('pass')
                store.set_current(old)
                (store.data/'config.json').write_bytes(b'{"font_size":14}')
                before=store.state_file.read_bytes()
                with patch.object(engine.shutil,'copyfileobj',side_effect=KeyboardInterrupt):
                    with self.assertRaises(KeyboardInterrupt):store.install_package(self.tracker,'0.0.1')
                self.assertEqual(store.state_file.read_bytes(),before)
                self.assertEqual(list(store.versions.glob('.stage-*')),[])
                store.install_package(self.tracker,'0.0.1')
                self.assertEqual(store.state['current'],'0.0.1')
                self.assertEqual(store.rollback(),old)
                self.assertEqual(store.current_dir(),legacy)
                self.assertEqual((store.data/'config.json').read_bytes(),b'{"font_size":14}')

    def test_launcher_legacy_transition_and_manual_rollback(self):
        from unified_updater import LauncherManager
        for old in ['8.0.0','9.0.0']:
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder)
                manager=LauncherManager(root)
                prior=root/'launcher_versions'/('v'+old)
                prior.mkdir();(prior/'launcher.pyw').write_text('pass')
                engine.atomic_json(manager.state_path,{'current':old,'previous':[]})
                manager.install(self.launcher,'0.0.2')
                self.assertEqual(manager.active(),'0.0.2')
                self.assertEqual(manager.rollback(),old)
                self.assertEqual(manager.entry(),prior/'launcher.pyw')

    def test_launcher_interrupted_extraction_keeps_legacy(self):
        from unified_updater import LauncherManager
        with tempfile.TemporaryDirectory() as folder:
            manager=LauncherManager(folder)
            engine.atomic_json(manager.state_path,{'current':'9.0.0','previous':[]})
            before=manager.state_path.read_bytes()
            with patch('unified_updater.shutil.copyfileobj',side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):manager.install(self.launcher,'0.0.2')
            self.assertEqual(manager.state_path.read_bytes(),before)
            self.assertEqual(list(manager.versions.glob('.stage-*')),[])
