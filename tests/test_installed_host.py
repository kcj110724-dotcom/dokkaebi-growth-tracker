"""Original installed host, isolated state, real disposable child processes."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/launcher'))
sys.path.insert(0, str(ROOT / 'src/launcher/launcher'))
from update_engine import Store, atomic_json, version_tuple
from unified_updater import LauncherManager, is_update


class InstalledHostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        loader = importlib.machinery.SourceFileLoader('installed_host', str(
            ROOT / 'src/bootstrap/launch_host.pyw'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        self.host = importlib.util.module_from_spec(spec)
        loader.exec_module(self.host)
        self.host.ROOT = self.root
        self.host.STATE = self.root / 'launcher_runtime.json'
        self.store = Store(self.root)
        self.store.set_repo('owner/repo')
        for name in ('combat_power.csv', 'stat_latest.json', 'config.json', 'assets/user_background.png'):
            p = self.store.data / name
            p.write_bytes(b'isolated preservation fixture')
        self.protected = {p: p.read_bytes() for p in self.store.data.rglob('*') if p.is_file()}
        self.protected[self.store.settings_file] = self.store.settings_file.read_bytes()
        self.root.joinpath('launcher.pyw').write_text('pass', encoding='utf-8')
        entry = self.root / 'launcher_versions/0.0.2/launcher.pyw'
        entry.parent.mkdir(parents=True)
        entry.write_text('raise SystemExit(7)', encoding='utf-8')
        atomic_json(self.host.STATE, {'current':'0.0.2','previous':['0.0.0'],
                                     'pending':{'version':'0.0.2','attempts':0}})

    @unittest.skipUnless(sys.platform == 'win32', 'Windows .pyw import resolution')
    def test_original_layout_import_collision_blocks_pending_startup(self):
        shutil.copyfile(ROOT / 'tests/fixtures/installed_bootstrap/launch_host.pyw', self.root / 'launch_host.pyw')
        modules = self.root / 'launcher'
        modules.mkdir()
        shutil.copyfile(ROOT / 'src/launcher/launcher/update_engine.py', modules / 'update_engine.py')
        result = subprocess.run([sys.executable, str(self.root / 'launch_host.pyw')],
                                cwd=self.root, capture_output=True, timeout=15,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"'launcher' is not a package", result.stderr)
        self.assertEqual(self.host.load()['pending']['attempts'], 0)
        self.assert_preserved()

    def launch_and_wait(self):
        real_popen = subprocess.Popen
        children = []
        def start(args, **kwargs):
            # Use console Python with CREATE_NO_WINDOW to collect the exit code.
            args[0] = sys.executable
            kwargs['stdout'] = subprocess.DEVNULL
            kwargs['stderr'] = subprocess.DEVNULL
            process = real_popen(args, **kwargs)
            children.append(process)
            return process
        with patch.object(self.host.subprocess, 'Popen', side_effect=start):
            self.host.main()
        return children[0].wait(timeout=15)

    def assert_preserved(self):
        self.assertTrue(all(p.read_bytes() == content for p, content in self.protected.items()))

    def test_crash_before_ready_rolls_back_on_next_launch(self):
        self.assertEqual(self.launch_and_wait(), 7)
        state = self.host.load()
        self.assertEqual(state['current'], '0.0.2')
        self.assertEqual(state['pending']['attempts'], 1)
        self.assertEqual(self.launch_and_wait(), 0)
        self.assertEqual(self.host.load()['current'], '0.0.0')
        self.assertNotIn('pending', self.host.load())
        self.assert_preserved()

    def test_ready_acknowledgement_prevents_rollback(self):
        entry = self.root / 'launcher_versions/0.0.2/launcher.pyw'
        entry.write_text('pass', encoding='utf-8')
        self.assertEqual(self.launch_and_wait(), 0)
        LauncherManager(self.root).confirm_healthy()
        self.assertEqual(self.launch_and_wait(), 0)
        self.assertEqual(self.host.load()['current'], '0.0.2')
        self.assert_preserved()

    def test_missing_launcher_entry_falls_back(self):
        # Alter only the generated disposable test fixture.
        atomic_json(self.host.STATE, {'current':'0.0.3','previous':['0.0.0']})
        self.assertEqual(self.launch_and_wait(), 0)
        self.assertEqual(self.host.load()['current'], '0.0.0')
        self.assert_preserved()

    def test_launcher_rollback_does_not_switch_tracker(self):
        tracker = self.root / 'versions/9.0.0/tracker.py'
        tracker.parent.mkdir(parents=True)
        tracker.write_text('pass')
        self.store.set_current('9.0.0')
        original = self.store.state_file.read_bytes()
        self.launch_and_wait()
        self.launch_and_wait()
        self.assertEqual(self.store.state_file.read_bytes(), original)
        self.assert_preserved()

    def test_legacy_versions_discover_successor_zero_series(self):
        for old in ('8.0.0', '9.0.0'):
            self.assertTrue(is_update({'kind':'app','tag':'tracker-v0.0.1','version':'0.0.1'}, 'app', old))

    def test_prefixed_legacy_directory_resolves_without_renaming(self):
        legacy = self.root / 'versions/v8.0.0'
        legacy.mkdir(parents=True)
        (legacy / 'tracker.py').write_text('pass')
        self.assertEqual(self.store.current_dir(), legacy)
        self.assertTrue((self.store.current_dir() / 'tracker.py').exists())

    def test_fixed_host_saves_in_real_conflicting_windows_layout(self):
        shutil.copyfile(ROOT / 'src/bootstrap/launch_host.pyw', self.root / 'launch_host.pyw')
        # Wait for the disposable child before TemporaryDirectory cleanup; the
        # production host intentionally exits before its GUI child does.
        runner = """import runpy, subprocess, sys
original = subprocess.Popen
def waited(*args, **kwargs):
    process = original(*args, **kwargs)
    process.wait(timeout=15)
    return process
subprocess.Popen = waited
runpy.run_path(sys.argv[1], run_name='__main__')
"""
        result = subprocess.run([sys.executable, '-c', runner, str(self.root / 'launch_host.pyw')],
                                cwd=self.root, capture_output=True, timeout=15,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.host.load()['pending']['attempts'], 1)
        self.assert_preserved()

    def test_host_interrupted_save_preserves_previous_json(self):
        before=self.host.STATE.read_bytes()
        with patch.object(self.host.os, 'replace', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):self.host.save({'current':'0.0.3'})
        self.assertEqual(self.host.STATE.read_bytes(),before)
        self.assertEqual(list(self.root.glob('*.tmp')),[])

    def test_failed_zero_series_launcher_returns_to_prefixed_legacy(self):
        prior=self.root/'launcher_versions/v9.0.0'
        prior.mkdir();(prior/'launcher.pyw').write_text('pass')
        state=self.host.load();state['previous']=['9.0.0']
        self.host.save(state)
        self.assertEqual(self.launch_and_wait(),7)
        self.assertEqual(self.launch_and_wait(),0)
        self.assertEqual(self.host.load()['current'],'9.0.0')
        self.assert_preserved()

if __name__ == '__main__':
    unittest.main()
