"""Opt-in, host-only crash recovery upgrade for an already verified installation.

Run OUTSIDE the installation. Neither this utility nor its rollback procedure
modifies launcher versions, records, settings, background files or update tags.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

KNOWN_HOST = '5b340c1fd9b6a8220e3832de627f9359b8e2c4d3a68c88f9e08584dfc216ad55'
NEW_HOST = '0298a5b45511429931075480f6b976edeeb51b7d38c36fac931f8d833b4dae29'
PACKAGE = Path(__file__).resolve().parents[1]


def checked(path):
    path=Path(path).absolute()
    for item in (path, *path.parents):
        if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
            raise ValueError('Symlink/junction path is not allowed')
    return path.resolve()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_replace(path,data):
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with tmp.open('xb') as fd:
            fd.write(data);fd.flush();os.fsync(fd.fileno())
        os.replace(tmp,path)
    finally:
        tmp.unlink(missing_ok=True)


def inspect(root):
    root=checked(root)
    target=checked(root/'launch_host.pyw')
    payload=checked(PACKAGE/'src/bootstrap/launch_host.pyw').read_bytes()
    if digest(payload)!=NEW_HOST:
        raise ValueError('This package host does not match the approved SHA256')
    compile(payload,'launch_host.pyw','exec')
    if not target.is_file():raise ValueError('Unknown installation: host not found')
    current=digest(target.read_bytes())
    if current not in (KNOWN_HOST,NEW_HOST):
        raise ValueError('Unknown existing host: refusing to overwrite')
    runtime_path=checked(root/'launcher_runtime.json')
    runtime=json.loads(runtime_path.read_text(encoding='utf-8'))
    if runtime.get('current') not in ('0.0.1','0.0.3') or runtime.get('pending'):
        raise ValueError('Requires stable 0.0.1/0.0.3; resolve pending updates first')
    version=runtime['current']
    if not (root/'launcher_versions'/version/'launcher.pyw').is_file():
        raise ValueError('Active launcher entry missing')
    return root,payload,current


def validate_backup(root,backup):
    backup=checked(backup)
    if backup==root or backup.is_relative_to(root) or root.is_relative_to(backup):
        raise ValueError('Backup must be in a separate directory outside the installation')
    if not backup.parent.is_dir() or backup.exists():
        raise ValueError('Backup parent must exist; backup directory must not exist')
    return backup


def apply(root,backup):
    root,payload,current=inspect(root)
    if current==NEW_HOST:return 'Already installed; no changes'
    backup=validate_backup(root,backup)
    backup.mkdir()
    existing=(root/'launch_host.pyw').read_bytes()
    if digest(existing)!=KNOWN_HOST:raise ValueError('Host changed; refusing to install')
    with (backup/'launch_host.pyw').open('xb') as fd:
        fd.write(existing);fd.flush();os.fsync(fd.fileno())
    receipt={'schema':1,'root':str(root),'previous_sha256':KNOWN_HOST,
             'installed_sha256':NEW_HOST}
    safe_replace(backup/'receipt.json',json.dumps(receipt,indent=2).encode())
    try:
        safe_replace(root/'launch_host.pyw',payload)
        if digest((root/'launch_host.pyw').read_bytes())!=NEW_HOST:
            raise ValueError('Post-install hash mismatch')
    except BaseException:
        if digest((root/'launch_host.pyw').read_bytes())==NEW_HOST:
            safe_replace(root/'launch_host.pyw',existing)
        raise
    return 'Host-only upgrade complete; original saved outside installation'


def rollback(root,backup):
    root=checked(root);backup=checked(backup)
    info=json.loads(checked(backup/'receipt.json').read_text(encoding='utf-8'))
    if info.get('schema')!=1 or checked(info.get('root',''))!=root:
        raise ValueError('Backup receipt does not match this installation')
    original=checked(backup/'launch_host.pyw').read_bytes()
    if info.get('previous_sha256')!=KNOWN_HOST or digest(original)!=KNOWN_HOST:
        raise ValueError('Original backup host SHA256 mismatch')
    host=checked(root/'launch_host.pyw')
    installed=digest(host.read_bytes())
    if installed==KNOWN_HOST:return 'Already rolled back; no changes'
    if info.get('installed_sha256')!=NEW_HOST or installed!=NEW_HOST:
        raise ValueError('Installed host modified; refusing rollback overwrite')
    safe_replace(host,original)
    if digest(host.read_bytes())!=KNOWN_HOST:
        raise ValueError('Rollback verification failed; keep backup')
    return 'Previous host restored; records/settings/versions unchanged'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('inspect','apply','rollback'))
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--backup',type=Path)
    parser.add_argument('--apps-closed',action='store_true')
    args=parser.parse_args()
    if args.action=='inspect':
        _,_,current=inspect(args.root)
        print(json.dumps({'existing_sha256':current,'candidate_sha256':NEW_HOST,'writes':False}))
    else:
        if not args.apps_closed or args.backup is None:
            parser.error('apply/rollback require --apps-closed and --backup')
        print(apply(args.root,args.backup) if args.action=='apply' else rollback(args.root,args.backup))


if __name__=='__main__':main()
