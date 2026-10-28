"""Build verified release assets from a reviewed request.

No account tokens in source; GitHub Actions injects an expiring GITHUB_TOKEN.
This never edits an existing published release, private records, or local user_data.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path.cwd()
OUT = ROOT / '.release-out'
MAX_MEMBERS = 500
MAX_UNPACKED = 100 * 1024 * 1024
NAME_BY_COMPONENT = {'tracker': 'dokkaebi-app.zip', 'launcher': 'dokkaebi-launcher.zip'}
TAG_PATTERN = re.compile(r'^(tracker|launcher)-v(\d+\.\d+\.\d+)$')


def fail(reason):
    raise SystemExit('Release blocked: ' + str(reason))


def get_sha(data):
    return hashlib.sha256(data).hexdigest()


def validate_zip(payload: bytes, version: str, component: str):
    import io
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_MEMBERS:
            fail('too many files')
        if sum(i.file_size for i in infos) > MAX_UNPACKED:
            fail('unpacked payload too large')
        names = [i.filename for i in infos]
        if len(set(n.casefold() for n in names)) != len(names):
            fail('duplicate case-insensitive ZIP member')
        for entry in infos:
            path = PurePosixPath(entry.filename)
            if (entry.filename.startswith('/') or '\\' in entry.filename or ':' in entry.filename or
                '..' in path.parts or str(path) != entry.filename or
                ((entry.external_attr >> 16) & 0o170000) == 0o120000):
                fail('unsafe ZIP member: ' + entry.filename)
        if component == 'tracker':
            try:
                manifest = json.loads(archive.read('manifest.json'))
            except Exception as error:
                fail('missing/invalid tracker manifest: ' + str(error))
            if manifest.get('version') != version or manifest.get('entrypoint') != 'tracker.py':
                fail('tracker version or entrypoint mismatch')
            entries = manifest.get('files')
            if not isinstance(entries, dict) or set(names) - {'manifest.json'} != set('app/' + p for p in entries):
                fail('tracker manifest/file list mismatch')
            for path, checksum in entries.items():
                if not re.fullmatch(r'[0-9a-f]{64}', checksum or ''):
                    fail('bad manifest checksum: ' + path)
                if get_sha(archive.read('app/' + path)) != checksum:
                    fail('tracker internal SHA mismatch: ' + path)


def main():
    if len(sys.argv) != 2:
        fail('exactly one release request required')
    request_path = Path(sys.argv[1])
    if (not re.fullmatch(r'release-requests/[^/]+\.json', request_path.as_posix()) or
        not request_path.is_file()):
        fail('unrecognized request path')
    obj = json.loads(request_path.read_text(encoding='utf-8'))
    if obj.get('approved') is not True:
        fail('release not explicitly approved')
    tag = obj.get('tag', '')
    match = TAG_PATTERN.fullmatch(tag)
    if not match:
        fail('invalid tag format')
    component, version = match.groups()
    name = NAME_BY_COMPONENT[component]
    if obj.get('version') != version or obj.get('component') != component:
        fail('request version/component mismatch')
    expected_sha = obj.get('sha256', '')
    if not re.fullmatch(r'[0-9a-f]{64}', expected_sha):
        fail('expected SHA-256 must be pinned in approved request')
    if not re.fullmatch(r'[\w .가-힣()\-]{5,120}', obj.get('title', '')):
        fail('invalid release title')
    mode = obj.get('mode', 'staged')
    if mode == 'staged':
        asset = ROOT / 'release-payloads' / tag / name
        if not asset.is_file():
            fail('binary file not staged at ' + str(asset))
        payload = asset.read_bytes()
    else:
        fail('unsupported packaging mode: ' + str(mode))
    actual_sha = get_sha(payload)
    if actual_sha != expected_sha:
        fail('package SHA-256 mismatch')
    validate_zip(payload, version, component)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/name).write_bytes(payload)
    (OUT/(name+'.sha256')).write_text(actual_sha + '  ' + name + '\n', encoding='utf-8')
    (OUT/'tag.txt').write_text(tag, encoding='utf-8')
    (OUT/'title.txt').write_text(obj['title'], encoding='utf-8')
    (OUT/'asset-name.txt').write_text(name, encoding='utf-8')
    notes = obj.get('notes', '')
    if not isinstance(notes, str) or len(notes) > 6000:
        fail('invalid release notes')
    (OUT/'notes.md').write_text(notes or '# Dokkaebi Growth Tracker\n', encoding='utf-8')
    print('Release assets verified:', tag, actual_sha)


if __name__ == '__main__':
    main()
