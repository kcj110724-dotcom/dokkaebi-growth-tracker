"""Build verified release assets from a reviewed request.

No account tokens in source; GitHub Actions injects an expiring GITHUB_TOKEN.
This never edits an existing published release, private records, or local user_data.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile

ROOT = Path.cwd()
OUT = ROOT / '.release-out'
MAX_MEMBERS = 500
MAX_UNPACKED = 100 * 1024 * 1024
NAME_BY_COMPONENT = {'tracker': 'dokkaebi-app.zip', 'launcher': 'dokkaebi-launcher.zip'}
TAG_PATTERN = re.compile(r'^(tracker|launcher)-v(\d+\.\d+\.\d+)$')
PRIVATE_NAMES = {'user_data', 'backups', 'config.json', 'combat_power.csv',
                 'stat_latest.json', 'stat_changes.csv', 'stat_snapshots.csv',
                 'user_background.png', 'user_background.gif', 'fixed_background.png'}


def safe_member(name):
    path = PurePosixPath(name)
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
                *(f'LPT{i}' for i in range(1, 10))}
    return (bool(name) and not name.startswith('/') and '\\' not in name and
            ':' not in name and '..' not in path.parts and str(path) == name and
            all(not any(ord(c) < 32 or c in '<>"|?*' for c in part) and
                not part.endswith((' ', '.')) and
                part.split('.')[0].upper() not in reserved for part in path.parts))


def fail(reason):
    raise SystemExit('Release blocked: ' + str(reason))


def get_sha(data):
    return hashlib.sha256(data).hexdigest()


def validate_zip(payload: bytes, version: str, component: str):
    import io
    if component == 'launcher':
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/launcher/launcher'))
        from unified_updater import validate_launcher_archive
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            if any(not safe_member(i.filename) for i in archive.infolist()):
                fail('unsafe Windows launcher ZIP member')
        validate_launcher_archive(payload, version)
        return
    if component != 'tracker':
        fail('unknown component')
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
            if (not safe_member(entry.filename) or entry.is_dir() or
                ((entry.external_attr >> 16) & 0o170000) == 0o120000):
                fail('unsafe ZIP member: ' + entry.filename)
            if any(part.casefold() in PRIVATE_NAMES for part in PurePosixPath(entry.filename).parts):
                fail('user data cannot be shipped in an update: ' + entry.filename)
        if component == 'tracker':
            try:
                manifest = json.loads(archive.read('manifest.json'))
            except Exception as error:
                fail('missing/invalid tracker manifest: ' + str(error))
            if (manifest.get('schema') != 1 or manifest.get('version') != version or
                manifest.get('entrypoint') != 'tracker.py' or 'app/tracker.py' not in names):
                fail('tracker version or entrypoint mismatch')
            entries = manifest.get('files')
            if not isinstance(entries, dict) or set(names) - {'manifest.json'} != set('app/' + p for p in entries):
                fail('tracker manifest/file list mismatch')
            for path, checksum in entries.items():
                if not isinstance(checksum, str) or not re.fullmatch(r'[0-9a-f]{64}', checksum):
                    fail('bad manifest checksum: ' + path)
                if get_sha(archive.read('app/' + path)) != checksum:
                    fail('tracker internal SHA mismatch: ' + path)


def load_request(value, root=ROOT):
    request_path = Path(value)
    if (not re.fullmatch(r'release-requests/[^/]+\.json', request_path.as_posix()) or
        not (root / request_path).is_file() or (root / request_path).is_symlink()):
        fail('unrecognized request path')
    obj = json.loads((root / request_path).read_text(encoding='utf-8'))
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
    notes = obj.get('notes', '')
    if not isinstance(notes, str) or len(notes) > 6000:
        fail('invalid release notes')
    return obj


def prepare(obj, artifact_dir=None, root=ROOT, out=OUT):
    tag, component, version = obj['tag'], obj['component'], obj['version']
    name, expected_sha = NAME_BY_COMPONENT[component], obj['sha256']
    mode = obj.get('mode', 'staged')
    if mode == 'staged':
        asset = root / 'release-payloads' / tag / name
        if not asset.is_file():
            fail('binary file not staged at ' + str(asset))
        payload = asset.read_bytes()
    elif mode == 'artifact' and artifact_dir is not None:
        artifact_dir = Path(artifact_dir)
        metadata = json.loads((artifact_dir / 'build-info.json').read_text(encoding='utf-8'))
        for key in ('component', 'version', 'tag', 'sha256', 'source_sha'):
            if metadata.get(key) != obj.get(key):
                fail('artifact/request mismatch: ' + key)
        if metadata.get('asset') != name:
            fail('artifact asset name mismatch')
        payload = (artifact_dir / name).read_bytes()
    else:
        fail('unsupported packaging mode: ' + str(mode))
    actual_sha = get_sha(payload)
    if actual_sha != expected_sha:
        fail('package SHA-256 mismatch')
    validate_zip(payload, version, component)
    out.mkdir(parents=True, exist_ok=True)
    (out/name).write_bytes(payload)
    (out/(name+'.sha256')).write_text(actual_sha + '  ' + name + '\n', encoding='utf-8')
    (out/'tag.txt').write_text(tag, encoding='utf-8')
    (out/'title.txt').write_text(obj['title'], encoding='utf-8')
    (out/'asset-name.txt').write_text(name, encoding='utf-8')
    notes = obj.get('notes', '')
    (out/'notes.md').write_text(notes or '# Dokkaebi Growth Tracker\n', encoding='utf-8')
    print('Release assets verified:', tag, actual_sha)


if __name__ == '__main__':
    if len(sys.argv) not in (2, 3):
        fail('usage: prepare_release.py REQUEST [ARTIFACT_DIR]')
    prepare(load_request(sys.argv[1]), sys.argv[2] if len(sys.argv) == 3 else None)
