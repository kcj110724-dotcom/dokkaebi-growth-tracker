"""Windows full launcher test on a disposable installation copy only.

Runs actual GUI children through the fixed host. Faults alter copied entrypoints
only. Set --observe-seconds to allow desktop visual inspection of the first GUI.
No release publication, source installation writes, or private data output.
"""
import argparse
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
from build_package import build
from check_installed_transition import hashes

ROOT = Path(__file__).resolve().parents[1]


def run(source, sha, observe):
    source = source.resolve()
    if any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) for p in source.rglob('*')):
        raise ValueError('Review installation links first')
    baseline = hashes(source)
    results = {'source_sha': sha, 'original_files': len(baseline), 'checks': {}}
    children = []
    scratch = ROOT / 'dist'
    scratch.mkdir(exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix='full-launcher-', dir=scratch) as folder:
            root = Path(folder) / 'installation'
            shutil.copytree(source, root)
            shutil.copyfile(ROOT / 'src/bootstrap/launch_host.pyw', root / 'launch_host.pyw')
            sys.path.insert(0, str(root / 'launcher_versions/0.0.1/launcher'))
            import unified_updater as updater
            manager = updater.LauncherManager(root)
            assert manager.active() == '0.0.1'
            meta = build('launcher', sha, Path(folder) / 'package')
            payload = (Path(folder) / 'package/dokkaebi-launcher.zip').read_bytes()
            results['package_sha256'] = meta['sha256']
            candidate = meta['version']
            manager.install(payload, candidate)
            loader = importlib.machinery.SourceFileLoader('full_test_host', str(root / 'launch_host.pyw'))
            spec = importlib.util.spec_from_loader(loader.name, loader)
            host = importlib.util.module_from_spec(spec)
            loader.exec_module(host)
            original_popen = subprocess.Popen

            def spawn(args, **kwargs):
                # Preserve real host executable, cwd, entrypoint and environment.
                process = original_popen(args, **kwargs)
                children.append(process)
                return process

            def launch():
                with patch.object(host.subprocess, 'Popen', side_effect=spawn):
                    host.main()
                return children[-1]

            def stop(process):
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=15)

            def healthy(process, expected):
                end = time.monotonic() + 30
                while time.monotonic() < end:
                    if process.poll() is not None:
                        raise AssertionError('GUI child exited before healthy')
                    state = host.load()
                    if state['current'] == expected and 'pending' not in state:
                        time.sleep(2)
                        assert process.poll() is None
                        return
                    time.sleep(.1)
                raise AssertionError('GUI did not acknowledge healthy within 30 seconds')

            try:
                process = launch()
                healthy(process, candidate)
                results['checks']['full_gui_healthy'] = True
                print(json.dumps({'phase': 'UI_READY', 'pid': process.pid, 'version': candidate}), flush=True)
                time.sleep(observe)
                stop(process)
                process = launch()
                healthy(process, candidate)
                results['checks']['kill_after_healthy'] = 'current retained by design; no automatic rollback'
                stop(process)
                entry = root / 'launcher_versions' / candidate / 'launcher.pyw'
                original = entry.read_bytes()
                for label, fault in [('startup_failure', b'raise SystemExit(7)\n'),
                                     ('kill_before_healthy', b'import time; time.sleep(30)\n')]:
                    # Re-activate verified unmodified payload, then inject copy-only fault.
                    entry.write_bytes(original)
                    manager.install(payload, candidate)
                    entry.write_bytes(fault)
                    process = launch()
                    if label == 'startup_failure':
                        assert process.wait(timeout=15) == 7
                    else:
                        time.sleep(.3)
                        stop(process)
                    assert host.load()['pending']['attempts'] == 1
                    entry.write_bytes(original)
                    process = launch()
                    healthy(process, '0.0.1')
                    results['checks'][label] = 'next host invocation restored real 0.0.1 GUI'
                    stop(process)
                after = hashes(root)
                exclusions = {'launch_host.pyw', 'launcher_runtime.json'}
                changed = [name for name, digest in baseline.items()
                           if name not in exclusions and after.get(name) != digest]
                results['preserved_existing_files'] = len(baseline) - len(exclusions) - len(changed)
                # Only filenames, never record/settings contents. Keep output local.
                results['changed_existing_paths'] = changed
                results['all_existing_data_settings_preserved'] = not changed
            finally:
                for process in children:
                    stop(process)
    finally:
        results['original_unchanged'] = hashes(source) == baseline
        (scratch / 'full-launcher-result.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        assert results['original_unchanged']
    print(json.dumps(results, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installation', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--observe-seconds', type=int, default=0)
    args = parser.parse_args()
    run(args.installation, args.source_sha, args.observe_seconds)
