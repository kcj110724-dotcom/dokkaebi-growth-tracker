"""Download a pinned Actions artifact using existing Git credentials in memory.

For isolated review only. No credentials or signed URLs are written to disk/logs.
Redirect authorization is intentionally not forwarded to artifact storage.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.parse
import urllib.request

REPO = 'kcj110724-dotcom/dokkaebi-growth-tracker'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def download(pin, git, destination, progress=None):
    result = subprocess.run([git, 'credential', 'fill'],
        input='protocol=https\nhost=github.com\n\n', text=True,
        capture_output=True, timeout=60)
    credentials = dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
    token = credentials.get('password')
    if result.returncode or not token:
        raise RuntimeError('Existing GitHub credential unavailable; sign in normally first')
    api = f'https://api.github.com/repos/{REPO}/actions/artifacts/{pin["id"]}'
    headers = {'Authorization':'Bearer '+token, 'Accept':'application/vnd.github+json',
               'User-Agent':'Dokkaebi-Isolated-Artifact-Review'}
    with urllib.request.urlopen(urllib.request.Request(api, headers=headers), timeout=30) as response:
        metadata = json.load(response)
    if (metadata['digest'] != pin['digest'] or metadata['expired'] or
        metadata['workflow_run']['head_sha'] != pin['source_sha'] or
        metadata['workflow_run']['id'] != pin['run_id']):
        raise ValueError('Artifact provenance mismatch')
    request = urllib.request.Request(api+'/zip', headers=headers)
    try:
        urllib.request.build_opener(NoRedirect()).open(request, timeout=30)
        raise ValueError('Expected authenticated artifact storage redirect')
    except urllib.error.HTTPError as error:
        if error.code != 302:
            raise RuntimeError('Artifact access denied, HTTP '+str(error.code)) from None
        location = error.headers['Location']
    parsed = urllib.parse.urlparse(location)
    if parsed.scheme != 'https' or parsed.username or not parsed.hostname:
        raise ValueError('Invalid storage redirect')
    # This URL came from authenticated GitHub API, never a user-supplied manifest.
    # No Authorization header is included on this separate storage request.
    chunks = []
    size = 0
    with urllib.request.urlopen(location, timeout=60) as response:
        while True:
            chunk = response.read(262144)
            if not chunk:break
            size += len(chunk)
            if size > 70*1024*1024:raise ValueError('Artifact too large')
            chunks.append(chunk)
            if progress:progress(size,metadata['size_in_bytes'])
    data = b''.join(chunks)
    if 'sha256:'+hashlib.sha256(data).hexdigest() != pin['digest']:
        raise ValueError('Artifact archive SHA-256 mismatch')
    Path(destination).write_bytes(data)
    return data


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pins', type=Path, required=True)
    parser.add_argument('--git', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for pin in json.loads(args.pins.read_text()):
        data = download(pin, args.git, args.output / (pin['component']+'.zip'))
        print(pin['component'], len(data), hashlib.sha256(data).hexdigest())
