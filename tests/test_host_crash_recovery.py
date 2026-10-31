"""Post-healthy crash recovery: temporary fixtures only, never real user data."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HOST_SOURCE = Path(__file__).resolve().parents[1] / 'src/bootstrap/launch_host.pyw'


class MockChild:
    def __init__(self, code, on_wait=None):
        self.code = code
        self.on_wait = on_wait

    def wait(self):
        if self.on_wait:
            self.on_wait()
        return self.code


class HealthyCrashRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        loader = importlib.machinery.SourceFileLoader('crash_recovery_host', str(HOST_SOURCE))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        self.host = importlib.util.module_from_spec(spec)
        loader.exec_module(self.host)
        self.host.ROOT = self.root
        self.host.STATE = self.root / 'launcher_runtime.json'
        for version in ('0.0.1', '0.0.3', '0.0.4'):
            path = self.root / 'launcher_versions' / version / 'launcher.pyw'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('pass', encoding='utf-8')
        (self.root/'launcher.pyw').write_text('pass', encoding='utf-8')
        (self.root/'user_data').mkdir()
        self.personal = self.root/'user_data'/'combat_power.csv'
        self.personal.write_bytes(b'original,unmodified\n123,456')
        self.original = self.personal.read_bytes()
        self.host.save({'current': '0.0.3', 'previous': ['0.0.1'],
                        'pending': {'version': '0.0.3', 'attempts': 0}})

    def healthy(self):
        state = self.host.load()
        state.pop('pending', None)
        self.host.save(state)

    def run_host(self, code, on_wait=None):
        with patch.object(self.host.subprocess, 'Popen', return_value=MockChild(code, on_wait)) as popen:
            self.host.main()
        popen.assert_called_once()
        self.assertEqual(self.personal.read_bytes(), self.original)
        return self.host.load()

    def test_crash_after_healthy_selects_previous_version(self):
        state = self.run_host(7, self.healthy)
        self.assertEqual(state['current'], '0.0.1')
        self.assertEqual(state['previous'][0], '0.0.3')
        self.assertNotIn('host_session', state)
        self.assertNotIn('pending', state)

    def test_clean_exit_after_healthy_does_not_rollback(self):
        state = self.run_host(0, self.healthy)
        self.assertEqual(state['current'], '0.0.3')
        self.assertNotIn('pending', state)

    def test_failure_before_healthy_remains_pending_for_next_launch(self):
        first = self.run_host(9)
        self.assertEqual(first['current'], '0.0.3')
        self.assertEqual(first['pending']['attempts'], 1)
        second = self.run_host(0)
        self.assertEqual(second['current'], '0.0.1')
        self.assertNotIn('pending', second)

    def test_old_session_cannot_change_newer_window(self):
        def newer_session():
            self.healthy()
            state = self.host.load()
            state['host_session'] = 'newer-window'
            self.host.save(state)
        state = self.run_host(11, newer_session)
        self.assertEqual(state['current'], '0.0.3')
        self.assertEqual(state['host_session'], 'newer-window')

    def test_old_process_crash_cannot_undo_update(self):
        def newer_install():
            self.host.save({'current': '0.0.4', 'previous': ['0.0.3', '0.0.1'],
                            'pending': {'version': '0.0.4', 'attempts': 0}})
        state = self.run_host(7, newer_install)
        self.assertEqual(state['current'], '0.0.4')
        self.assertEqual(state['pending']['version'], '0.0.4')

    def test_pending_only_exit_never_uses_post_healthy_rollback(self):
        state = self.run_host(7)
        self.assertEqual(state['current'], '0.0.3')
        self.assertEqual(state['pending']['attempts'], 1)

    def test_crash_with_no_previous_version_does_not_corrupt_state(self):
        self.host.save({'current': '0.0.3', 'previous': []})
        state = self.run_host(17)
        self.assertEqual(state['current'], '0.0.3')
        self.assertEqual(state['previous'], [])
        self.assertTrue(state['host_session'])

    def test_legacy_v_prefix_previous_version(self):
        legacy = self.root/'launcher_versions/v9.0.0/launcher.pyw'
        legacy.parent.mkdir(parents=True)
        legacy.write_text('pass', encoding='utf-8')
        self.host.save({'current':'0.0.3','previous':['9.0.0']})
        state = self.run_host(9)
        self.assertEqual(state['current'], '9.0.0')

    def test_no_automatic_rollback_on_normal_exit_after_healthy(self):
        state = self.run_host(0, self.healthy)
        self.assertEqual(state['current'], '0.0.3')

    def _run_real_child(self, exit_code):
        # Uses the actual child interpreter/process monitor rather than Fake Popen.
        # Only a disposable temp root is ever touched; no GUI/game is launched.
        entry=self.root/'launcher_versions/0.0.3/launcher.pyw'
        entry.write_text('''import json, os, sys
from pathlib import Path
state_file=Path(os.environ['DOKKAEBI_LAUNCHER_ROOT'])/'launcher_runtime.json'
state=json.loads(state_file.read_text(encoding='utf-8'))
state.pop('pending',None)
state_file.write_text(json.dumps(state),encoding='utf-8')
raise SystemExit(%d)
''' % exit_code, encoding='utf-8')
        self.host.main()
        self.assertEqual(self.personal.read_bytes(),self.original)
        return self.host.load()

    def test_real_child_crash_after_healthy_rolls_back(self):
        state=self._run_real_child(17)
        self.assertEqual(state['current'],'0.0.1')
        self.assertNotIn('pending',state)

    def test_real_child_clean_exit_after_healthy_keeps_version(self):
        state=self._run_real_child(0)
        self.assertEqual(state['current'],'0.0.3')
        self.assertNotIn('pending',state)


if __name__ == '__main__':
    unittest.main()
