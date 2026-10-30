"""Build review-only host transition archive; never deploy or publish."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile
from host_transition import OLD_HOST

ROOT = Path(__file__).resolve().parents[1]


def build(source_sha, output):
    if not re.fullmatch('[0-9a-f]{40}', source_sha):
        raise ValueError('Full source commit required')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    host = (ROOT / 'src/bootstrap/launch_host.pyw').read_bytes()
    manifest = {'schema':1, 'source_sha':source_sha, 'old_sha256':OLD_HOST,
                'new_sha256':hashlib.sha256(host).hexdigest()}
    files = {'launch_host.pyw':host,
             'host_transition.py':(ROOT / 'scripts/host_transition.py').read_bytes(),
             'transition.json':json.dumps(manifest, indent=2).encode(),
             'README.md':(ROOT / 'docs/HOST_TRANSITION.md').read_bytes()}
    target = output / 'dokkaebi-host-transition.zip'
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2020,1,1,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.zip.sha256').write_text(digest+'  '+target.name+'\n', encoding='utf-8')
    (output / 'transition-build-info.json').write_text(json.dumps({**manifest, 'archive_sha256':digest}, indent=2), encoding='utf-8')
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--output', default='dist/bootstrap')
    args = parser.parse_args()
    print(build(args.source_sha, args.output))
