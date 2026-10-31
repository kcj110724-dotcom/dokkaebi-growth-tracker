"""One-time host-only transition. Default inspect is read-only; close apps first.

No version folders, runtime, settings, records, or entry BAT/VBS are changed.
Keep the backup outside the installation. Never extract this package over it.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import uuid

OLD_HOST = '84b0026111980ac2ed9c2c4e4286eb8c2536d2d116f05a569c219247358c85db'
PREVIOUS_HOST = '5b340c1fd9b6a8220e3832de627f9359b8e2c4d3a68c88f9e08584dfc216ad55'
ALLOWED_OLD_HOSTS = (OLD_HOST, PREVIOUS_HOST)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def checked(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
            raise ValueError('Links/junctions are not supported')
    return path.resolve()


def replace(path, data):
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temp.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def inspect(root, package):
    root, package = checked(root), checked(package)
    host = checked(root / 'launch_host.pyw')
    manifest = json.loads((package / 'transition.json').read_text(encoding='utf-8'))
    if manifest.get('schema') != 1 or manifest.get('old_sha256') != OLD_HOST:
        raise ValueError('Unrecognized transition policy')
    payload = checked(package / 'launch_host.pyw').read_bytes()
    if digest(payload) != manifest['new_sha256']:
        raise ValueError('Host payload SHA-256 mismatch')
    compile(payload, 'launch_host.pyw', 'exec')
    state = json.loads(checked(root / 'launcher_runtime.json').read_text(encoding='utf-8'))
    if state.get('current') not in ('0.0.1', '0.0.3', '0.0.4') or state.get('pending'):
        raise ValueError('Requires stable 0.0.1; pending updates need recovery first')
    if not checked(root / 'launcher_versions' / state['current'] / 'launcher.pyw').is_file():
        raise ValueError('Missing previous launcher entry')
    current = digest(host.read_bytes())
    if current not in (*ALLOWED_OLD_HOSTS, manifest['new_sha256']):
        raise ValueError('Unknown installed host; refusing overwrite')
    return root, payload, current


def apply(root, package, backup):
    root, payload, current = inspect(root, package)
    if current == digest(payload):
        return 'already applied; no writes'
    backup = checked(backup)
    if backup == root or backup.is_relative_to(root) or root.is_relative_to(backup):
        raise ValueError('Use a separate backup directory outside the installation')
    # mkdir without exist_ok: never overwrite a previous backup or receipt.
    backup.mkdir(parents=False)
    host = root / 'launch_host.pyw'
    original = host.read_bytes()
    if digest(original) not in ALLOWED_OLD_HOSTS:
        raise ValueError('Host changed during preflight')
    with (backup / 'launch_host.pyw').open('xb') as stream:
        stream.write(original)
        stream.flush()
        os.fsync(stream.fileno())
    receipt = {'schema':1, 'root':str(root), 'old_sha256':digest(original),
               'new_sha256':digest(payload)}
    replace(backup / 'receipt.json', json.dumps(receipt, indent=2).encode())
    try:
        replace(host, payload)
        if digest(host.read_bytes()) != digest(payload):
            raise ValueError('Post-install verification failed')
    except BaseException:
        # If the atomic swap occurred, restore the verified original. If recovery
        # itself fails, retain the backup/receipt for explicit rollback.
        if host.exists() and digest(host.read_bytes()) == digest(payload):
            replace(host, original)
        raise
    return 'applied; original host and receipt retained'


def rollback(root, backup):
    root, backup = checked(root), checked(backup)
    receipt = json.loads(checked(backup / 'receipt.json').read_text(encoding='utf-8'))
    if receipt.get('schema') != 1 or checked(receipt['root']) != root:
        raise ValueError('Backup belongs to a different installation')
    original = checked(backup / 'launch_host.pyw').read_bytes()
    if receipt.get('old_sha256') not in ALLOWED_OLD_HOSTS or digest(original) != receipt.get('old_sha256'):
        raise ValueError('Backup SHA-256 mismatch')
    host = checked(root / 'launch_host.pyw')
    current = digest(host.read_bytes())
    if current == digest(original):
        return 'already restored; no writes'
    if current != receipt['new_sha256']:
        raise ValueError('Host modified since transition; refusing overwrite')
    replace(host, original)
    if digest(host.read_bytes()) != digest(original):
        raise ValueError('Rollback verification failed; retain backup')
    return 'restored host only; runtime and user data unchanged'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['inspect','apply','rollback'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--package', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--apps-closed', action='store_true', help='Confirm launcher/tracker are closed')
    args = parser.parse_args()
    if args.action == 'inspect':
        root, payload, current = inspect(args.root, args.package)
        print(json.dumps({'installed_sha256':current, 'candidate_sha256':digest(payload), 'writes':False}))
    else:
        if not args.apps_closed or not args.backup:
            parser.error('apply/rollback require --apps-closed and --backup')
        print(apply(args.root, args.package, args.backup) if args.action == 'apply'
              else rollback(args.root, args.backup))
