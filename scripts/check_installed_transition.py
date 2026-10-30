"""Read an installation, test a private temporary copy, print aggregate evidence.

Does not launch the full GUI, contact GitHub, or modify the supplied installation.
Run with --installation PATH --source-sha FULL_SHA. This is NOT release clearance.
"""
import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

from build_package import build

ROOT = Path(__file__).resolve().parents[1]


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def check(installation, source_sha):
    installation = installation.resolve()
    if any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction())
           for p in installation.rglob('*')):
        raise ValueError('Installation links require separate review')
    before = hashes(installation)
    result = {'source_sha': source_sha, 'scope': 'private installation copy; no full GUI or live Release',
              'original_file_count': len(before), 'release_clearance': False}
    try:
        scratch = ROOT / 'dist'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='dokkaebi-transition-', dir=scratch) as folder:
            root = Path(folder) / 'installation'
            shutil.copytree(installation, root)
            state_file = root / 'launcher_runtime.json'
            assert json.loads(state_file.read_text(encoding='utf-8'))['current'] == '0.0.1'
            # Import the updater actually shipped in the old active payload.
            sys.path.insert(0, str(root / 'launcher_versions/0.0.1/launcher'))
            import update_engine as old_engine
            import unified_updater as old_updater
            assert Path(old_updater.__file__).is_relative_to(root)
            manager = old_updater.LauncherManager(root)
            metadata = build('launcher', source_sha, Path(folder) / 'package')
            payload = (Path(folder) / 'package/dokkaebi-launcher.zip').read_bytes()
            candidate = metadata['version']
            result['candidate_version'] = candidate
            result['package_sha256'] = metadata['sha256']
            result['old_updater_sha256'] = before['launcher_versions/0.0.1/launcher/unified_updater.py']
            result['old_host_sha256'] = before['launch_host.pyw']
            info = {'sha_url': 'https://github.com/local-test/hash',
                    'url': 'https://github.com/local-test/package', 'digest': metadata['sha256']}
            initial_state = state_file.read_bytes()
            with patch.object(old_engine, 'github_get', side_effect=[
                    (metadata['sha256'] + '  dokkaebi-launcher.zip').encode(), b'corrupt']):
                try:
                    old_engine.get_release_zip(info)
                except ValueError:
                    result['old_updater_rejects_bad_hash'] = True
                else:
                    raise AssertionError('bad hash accepted')
            assert state_file.read_bytes() == initial_state
            with patch.object(old_updater.shutil, 'copyfileobj', side_effect=KeyboardInterrupt):
                try:
                    manager.install(payload, candidate)
                except KeyboardInterrupt:
                    pass
            assert state_file.read_bytes() == initial_state
            assert not (root / ('launcher_versions/' + candidate)).exists()
            assert not list((root / 'launcher_versions').glob('.stage-*'))
            result['old_updater_interruption_preserves_state'] = True
            with patch.object(old_engine, 'github_get', side_effect=[
                    (metadata['sha256'] + '  dokkaebi-launcher.zip').encode(), payload]):
                verified = old_engine.get_release_zip(info)
            manager.install(verified, candidate)
            pending = state_file.read_bytes()
            assert manager.read()['previous'][0] == '0.0.1'
            result['old_updater_installs_real_candidate_package'] = True
            # Exercise original Windows host entry point. It fails before spawning UI.
            run = subprocess.run([sys.executable, str(root / 'launch_host.pyw')],
                                 cwd=root, capture_output=True, timeout=20,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            assert run.returncode != 0 and b"'launcher' is not a package" in run.stderr
            assert state_file.read_bytes() == pending
            result['original_host_restart'] = 'BLOCKED: launcher module import collision; pending attempts remains 0'
            # In-memory binding of fixed host to the COPY only. Spawn interception
            # checks selection/state; full child process recovery has separate tests.
            loader = importlib.machinery.SourceFileLoader('copy_host', str(ROOT / 'src/bootstrap/launch_host.pyw'))
            spec = importlib.util.spec_from_loader(loader.name, loader)
            host = importlib.util.module_from_spec(spec)
            loader.exec_module(host)
            host.ROOT, host.STATE = root, state_file
            with patch.object(host.subprocess, 'Popen') as spawn:
                host.main()
                assert Path(spawn.call_args.args[0][1]).samefile(root / ('launcher_versions/' + candidate + '/launcher.pyw'))
                assert host.load()['pending']['attempts'] == 1
                # No healthy acknowledgement: next invocation must restore 0.0.1.
                host.main()
                assert Path(spawn.call_args.args[0][1]).samefile(root / 'launcher_versions/0.0.1/launcher.pyw')
            assert host.load()['current'] == '0.0.1' and 'pending' not in host.load()
            result['fixed_host_selection_without_healthy'] = candidate + ' then 0.0.1 on next invocation; spawn intercepted'
            after_copy = hashes(root)
            changed = [name for name, digest in before.items()
                       if name != 'launcher_runtime.json' and after_copy.get(name) != digest]
            assert not changed
            result['copy_existing_files_preserved_except_runtime'] = len(before) - 1
            result['copy_data_settings_and_tracker_preserved'] = True
    finally:
        result['original_unchanged'] = hashes(installation) == before
        if not result['original_unchanged']:
            raise AssertionError('installation changed during observation')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installation', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.installation, args.source_sha), indent=2))
