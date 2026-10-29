"""Deterministic source ZIP in the existing launcher's manifest/app layout.

This is a Windows Python payload, not a newly invented EXE installer. Runtime
and dependency installation remain the existing launcher's responsibility.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

from prepare_release import NAME_BY_COMPONENT, validate_zip

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = (
    'CHANGELOG_0.0.1.txt', 'assets/dashboard_art.png',
    'assets/dashboard_character.png', 'legacy_tracker/assets/app_icon.png',
    'legacy_tracker/assets/brand_logo.png',
    'legacy_tracker/assets/fantasy_background.jpg',
    'legacy_tracker/capture_v8.py', 'legacy_tracker/core_v5.py',
    'legacy_tracker/gif_v7.py', 'legacy_tracker/ocr_utils.py',
    'legacy_tracker/requirements.txt', 'legacy_tracker/tracker.py',
    'legacy_tracker/tracker_v8.py', 'legacy_tracker/ui_v6.py',
    'legacy_tracker/ui_v9.py', 'requirements.txt', 'tracker.py',
)


def build(component, source_sha, output, root=ROOT):
    if component != 'tracker':
        raise ValueError('Launcher v0.0.2 source and packaging contract are missing; no substitute will be built')
    if not re.fullmatch(r'[0-9a-f]{40}', source_sha):
        raise ValueError('A full source commit SHA is required')
    config = json.loads((root / 'release-config' / 'tracker.json').read_text(encoding='utf-8'))
    version = config['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Invalid component version')
    if (config['source'], config['entrypoint'], config['asset'], config['component']) != (
            'src/tracker', 'tracker.py', NAME_BY_COMPONENT[component], component):
        raise ValueError('Existing tracker packaging contract must be preserved')
    source = root / config['source']
    files = {}
    # Explicit allowlist prevents local settings, records, logs and imported art
    # from accidentally becoming public release assets.
    for relative in SOURCE_FILES:
        path = source / relative
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('Symlinks cannot be packaged: ' + relative)
        files[relative] = path.read_bytes()
        if relative.endswith('.py'):
            compile(files[relative], relative, 'exec')
    manifest = {'schema': 1, 'version': version, 'entrypoint': config['entrypoint'],
                'files': {p: hashlib.sha256(b).hexdigest() for p, b in sorted(files.items())}}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    asset = output / config['asset']
    members = {'manifest.json': json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')}
    members.update({'app/' + p: b for p, b in files.items()})
    with zipfile.ZipFile(asset, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(members.items()):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compresslevel=9)
    payload = asset.read_bytes()
    validate_zip(payload, version, component)
    digest = hashlib.sha256(payload).hexdigest()
    (output / (asset.name + '.sha256')).write_text(digest + '  ' + asset.name + '\n', encoding='utf-8')
    metadata = {'component': component, 'version': version, 'tag': component + '-v' + version,
                'source_sha': source_sha, 'sha256': digest, 'asset': asset.name,
                'format': 'existing-python-manifest-v1'}
    (output / 'build-info.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    return metadata


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--component', choices=NAME_BY_COMPONENT, default='tracker')
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--output', default='dist/tracker')
    args = parser.parse_args()
    print(json.dumps(build(args.component, args.source_sha, args.output), indent=2))
