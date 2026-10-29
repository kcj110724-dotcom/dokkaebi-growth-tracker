"""Publish exactly the reviewed artifact after the GitHub Environment approval."""
import argparse
import os
from pathlib import Path
import subprocess

from prepare_release import NAME_BY_COMPONENT, prepare
from release_gate import gate


def publish(obj, repository, run=subprocess.run):
    tag, name = obj['tag'], NAME_BY_COMPONENT[obj['component']]
    # Atomic ref creation rejects an existing tag (even without a Release) and
    # binds it to the reviewed commit. Never move or overwrite a remote tag.
    run(['gh', 'api', '--method', 'POST', f'repos/{repository}/git/refs',
         '-f', 'ref=refs/tags/' + tag, '-f', 'sha=' + obj['source_sha']], check=True)
    run(['gh', 'release', 'create', tag, '--repo', repository,
         '--target', obj['source_sha'], '--title', obj['title'],
         '--notes-file', '.release-out/notes.md', '--verify-tag', '--draft', '--latest=false'], check=True)
    run(['gh', 'release', 'upload', tag, '.release-out/' + name,
         '.release-out/' + name + '.sha256', '--repo', repository], check=True)
    run(['gh', 'release', 'edit', tag, '--repo', repository, '--draft=false',
         '--latest=' + str(obj['latest']).lower()], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request')
    parser.add_argument('artifact_dir', type=Path)
    args = parser.parse_args()
    obj = gate(args.request)
    prepare(obj, args.artifact_dir)
    publish(obj, os.environ['GITHUB_REPOSITORY'])
