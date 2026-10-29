"""Fail-closed release policy, shared by preflight and protected publish job."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from prepare_release import ROOT, fail, load_request


def gh_json(endpoint):
    return json.loads(subprocess.check_output(['gh', 'api', endpoint], text=True, encoding='utf-8'))


def check_request(obj, compatibility):
    if obj.get('mode') != 'artifact':
        fail('new releases must use a tested source-build artifact, not legacy staged ZIPs')
    if not re.fullmatch(r'[0-9a-f]{40}', obj.get('source_sha', '')):
        fail('full source SHA required')
    if type(obj.get('build_run_id')) is not int or obj['build_run_id'] <= 0:
        fail('positive build run ID required')
    if type(obj.get('latest')) is not bool:
        fail('explicit latest policy required after launcher discovery has been verified')
    if (compatibility.get('status') != 'verified' or
        not compatibility.get('evidence') or
        not all(isinstance(p, str) and p for p in compatibility['evidence'])):
        fail('real launcher compatibility/rollback/data-preservation evidence is still missing')


def check_environment(environment, owner):
    reviewers = [r for rule in environment.get('protection_rules', [])
                 if rule.get('type') == 'required_reviewers' for r in rule.get('reviewers', [])]
    if not any(r.get('type') == 'User' and
               r.get('reviewer', {}).get('login', '').casefold() == owner.casefold() for r in reviewers):
        fail('production-release environment must require the repository owner as reviewer')
    # An additional reviewer could approve instead of the owner (GitHub uses OR).
    if len(reviewers) != 1:
        fail('production-release must have the owner as its sole required reviewer')


def check_run(run, obj, repository):
    if (run.get('status') != 'completed' or run.get('conclusion') != 'success' or
        run.get('head_sha') != obj['source_sha'] or
        run.get('event') not in ('push', 'workflow_dispatch') or
        run.get('path') != '.github/workflows/build.yml' or
        run.get('head_repository', {}).get('full_name') != repository):
        fail('build must be a successful same-repository source build for the approved commit')


def gate(request, root=ROOT):
    if os.environ.get('GITHUB_REF') != 'refs/heads/main':
        fail('publishing workflow must run from main')
    repository = os.environ['GITHUB_REPOSITORY']
    owner = repository.split('/')[0]
    obj = load_request(request, root)
    compatibility = json.loads((root / 'release-config/compatibility.json').read_text(encoding='utf-8'))
    check_request(obj, compatibility)
    for evidence in compatibility['evidence']:
        path = (root / evidence).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            fail('missing compatibility evidence file: ' + evidence)
    check_environment(gh_json(f'repos/{repository}/environments/production-release'), owner)
    check_run(gh_json(f'repos/{repository}/actions/runs/{obj["build_run_id"]}'), obj, repository)
    # Reject commits absent from approved main history. Do not use moving main as
    # the release target: publish_release pins obj['source_sha'] instead.
    subprocess.run(['git', 'merge-base', '--is-ancestor', obj['source_sha'], 'HEAD'], check=True)
    return obj


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request')
    args = parser.parse_args()
    obj = gate(args.request)
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
        output.write(f'run_id={obj["build_run_id"]}\n')
        output.write(f'artifact=windows-{obj["component"]}-{obj["source_sha"]}\n')
