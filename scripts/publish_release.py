"""Publish exactly the reviewed artifact after the GitHub Environment approval."""
import argparse
import os
from pathlib import Path
import subprocess
import hashlib
import json
import zipfile

from prepare_release import NAME_BY_COMPONENT, prepare
from release_gate import gate


def prepare_transition(obj, directory=Path('approved-bootstrap'), out=Path('.release-out')):
    name='dokkaebi-host-transition.zip'
    payload=(directory/name).read_bytes()
    digest=hashlib.sha256(payload).hexdigest()
    metadata=json.loads((directory/'transition-build-info.json').read_text(encoding='utf-8'))
    if (digest!=obj.get('host_transition_sha256') or metadata.get('archive_sha256')!=digest or
        metadata.get('source_sha')!=obj['source_sha'] or
        (directory/(name+'.sha256')).read_text(encoding='utf-8-sig').split()[0]!=digest):
        raise ValueError('Host transition approval/provenance mismatch')
    with zipfile.ZipFile(directory/name) as archive:
        names=archive.namelist()
        if len(names)!=4 or set(names)!={'host_transition.py','launch_host.pyw','transition.json','README.md'}:
            raise ValueError('Unexpected host transition members')
        manifest=json.loads(archive.read('transition.json'))
        if (manifest.get('source_sha')!=obj['source_sha'] or
            manifest.get('new_sha256')!=hashlib.sha256(archive.read('launch_host.pyw')).hexdigest()):
            raise ValueError('Host transition manifest mismatch')
    out.mkdir(parents=True,exist_ok=True)
    (out/name).write_bytes(payload)
    (out/(name+'.sha256')).write_text(digest+'  '+name+'\n',encoding='utf-8')


def publish(obj, repository, run=subprocess.run):
    tag, name = obj['tag'], NAME_BY_COMPONENT[obj['component']]
    # Atomic ref creation rejects an existing tag (even without a Release) and
    # binds it to the reviewed commit. Never move or overwrite a remote tag.
    run(['gh', 'api', '--method', 'POST', f'repos/{repository}/git/refs',
         '-f', 'ref=refs/tags/' + tag, '-f', 'sha=' + obj['source_sha']], check=True)
    run(['gh', 'release', 'create', tag, '--repo', repository,
         '--target', obj['source_sha'], '--title', obj['title'],
         '--notes-file', '.release-out/notes.md', '--verify-tag', '--draft', '--latest=false'], check=True)
    assets=['.release-out/'+name,'.release-out/'+name+'.sha256']
    if obj['component']=='launcher':
        assets += ['.release-out/dokkaebi-host-transition.zip', '.release-out/dokkaebi-host-transition.zip.sha256']
    run(['gh', 'release', 'upload', tag, *assets, '--repo', repository], check=True)
    run(['gh', 'release', 'edit', tag, '--repo', repository, '--draft=false',
         '--latest=' + str(obj['latest']).lower()], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request')
    parser.add_argument('artifact_dir', type=Path)
    args = parser.parse_args()
    obj = gate(args.request)
    prepare(obj, args.artifact_dir)
    if obj['component']=='launcher':prepare_transition(obj)
    publish(obj, os.environ['GITHUB_REPOSITORY'])
