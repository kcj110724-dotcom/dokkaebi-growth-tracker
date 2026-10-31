"""Versioned, checksum-validated GitHub Releases updater for Dokkaebi Tracker.

Launcher code is never hot-replaced. User data and imported backgrounds are never
extracted from downloadable release archives. Standard library only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import urllib.request
import urllib.error
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

APP_ASSET = 'dokkaebi-app.zip'
ASSET_SHA = APP_ASSET + '.sha256'
MAX_ZIP = 65 * 1024 * 1024
MAX_UNCOMPRESSED = 160 * 1024 * 1024
MAX_FILES = 350
ALLOWED_HOSTS = {'github.com', 'api.github.com', 'objects.githubusercontent.com',
                 'release-assets.githubusercontent.com', 'github-releases.githubusercontent.com'}
VERSION_RE = re.compile(r'^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$')
SHA_RE = re.compile(r'^[0-9a-f]{64}$')
REPO_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}$')


def version_tuple(s):
    m = VERSION_RE.fullmatch(str(s))
    if not m:
        raise ValueError('버전은 v8.1.0 같은 숫자 세 부분으로 지정해야 해.')
    return tuple(map(int, m.groups()))


def canonical_version(s):
    return '.'.join(map(str,version_tuple(s)))


def repo_valid(repo):
    return bool(REPO_RE.fullmatch(repo.strip())) and not repo.endswith(('/.', '/..'))


def atomic_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class StrictRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def safe_url(url):
    u = urlparse(url)
    if u.scheme != 'https' or u.hostname not in ALLOWED_HOSTS or u.username or u.password:
        raise ValueError('허용되지 않은 다운로드 주소야: GitHub 공식 HTTPS만 허용해.')


def github_get(url, limit=MAX_ZIP, headers=None, on_progress=None):
    safe_url(url)
    opener = urllib.request.build_opener(StrictRedirect())
    req = urllib.request.Request(url, headers={
        'User-Agent':'DokkaebiGrowthLauncher/1.0',
        'Accept':'application/vnd.github+json',
        'X-GitHub-Api-Version':'2022-11-28',
        **(headers or {})})
    try:
        with opener.open(req, timeout=25) as resp:
            # Read in bounded chunks; report real byte progress when length is known.
            expected=int(resp.headers.get('Content-Length') or 0)
            chunks=[]
            received=0
            while True:
                chunk=resp.read(min(1024*256, limit + 1 - received))
                if not chunk:break
                received+=len(chunk)
                if received>limit:raise ValueError('업데이트 파일 크기가 허용 범위를 넘었어.')
                chunks.append(chunk)
                if on_progress:on_progress(received, expected)
            payload=b''.join(chunks)
    except urllib.error.HTTPError as ex:
        if ex.code == 404:
            raise RuntimeError('GitHub 저장소 또는 공개된 Release를 찾지 못했어. 저장소 주소와 배포 상태를 확인해 줘.') from ex
        if ex.code == 429 or (ex.code == 403 and ex.headers.get('X-RateLimit-Remaining') == '0'):
            raise RuntimeError('GitHub API 요청 한도를 초과했어. 잠시 뒤 다시 확인해 줘.') from ex
        if ex.code == 403:
            raise RuntimeError('GitHub 접근이 거부됐어. 저장소 공개 여부와 네트워크 접근 정책을 확인해 줘.') from ex
        raise
    except urllib.error.URLError as ex:
        raise RuntimeError('GitHub에 연결하지 못했어. 인터넷·DNS·프록시·인증서 설정을 확인해 줘. 업데이트 없음으로 판단하지 않았어.') from ex
    if len(payload)>limit:
        raise ValueError('업데이트 파일 크기가 허용 범위를 넘었어.')
    return payload


def get_latest_release(repo):
    if not repo_valid(repo):
        raise ValueError('GitHub 저장소를 소유자/저장소 형식으로 입력해 줘. 예: myname/dokkaebi-tracker')
    url = f'https://api.github.com/repos/{repo}/releases/latest'
    release = json.loads(github_get(url,limit=2*1024*1024))
    version = canonical_version(release.get('tag_name',''))
    assets = {a.get('name'):a for a in release.get('assets', []) if isinstance(a,dict)}
    if APP_ASSET not in assets:
        raise ValueError('최신 Release에 dokkaebi-app.zip 파일이 없어.')
    a = assets[APP_ASSET]
    if a.get('size',MAX_ZIP+1)>MAX_ZIP:
        raise ValueError('업데이트 압축 파일이 너무 커.')
    if not a.get('browser_download_url'):
        raise ValueError('다운로드 주소를 찾지 못했어.')
    # GitHub API digest is preferred, SHA sidecar is required as fallback.
    digest = a.get('digest') or ''
    if digest and not (digest.startswith('sha256:') and SHA_RE.fullmatch(digest[7:])):
        raise ValueError('GitHub API의 무결성 정보가 올바르지 않아.')
    sha_asset = assets.get(ASSET_SHA)
    if not digest and not sha_asset:
        raise ValueError('SHA-256 정보가 없어. Release에 .sha256 파일도 첨부해 줘.')
    return {'version':version,'notes':release.get('body','') or '',
            'url':a['browser_download_url'],
            'digest':digest[7:] if digest else '',
            'sha_url':sha_asset.get('browser_download_url','') if sha_asset else ''}


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def get_release_zip(info, on_progress=None):
    expected = info.get('digest','')
    if info.get('sha_url'):
        sha_text=github_get(info['sha_url'],limit=4096).decode('utf-8-sig').strip()
        token=sha_text.split()[0].lower() if sha_text else ''
        if not SHA_RE.fullmatch(token):
            raise ValueError('SHA-256 체크섬 파일 형식이 잘못됐어.')
        if expected and expected != token:
            raise ValueError('GitHub와 체크섬 파일의 해시가 달라. 업데이트를 중단했어.')
        expected=token
    if not expected:
        raise ValueError('다운로드 파일 검증에 필요한 SHA-256이 없어.')
    payload=github_get(info['url'],limit=MAX_ZIP,headers={'Accept':'application/octet-stream'},on_progress=on_progress)
    if sha256_bytes(payload) != expected:
        raise ValueError('다운로드한 업데이트 파일의 SHA-256이 일치하지 않아. 적용하지 않았어.')
    return payload


def validate_package(zf, required_version):
    infos=zf.infolist()
    if len(infos)>MAX_FILES:
        raise ValueError('압축 파일 내 항목이 너무 많아.')
    total=sum(i.file_size for i in infos)
    if total>MAX_UNCOMPRESSED:
        raise ValueError('압축 해제 후 크기가 너무 커.')
    seen=set()
    seen_folded=set()
    for i in infos:
        name=i.filename
        norm=PurePosixPath(name)
        if (name.startswith('/') or '\\' in name or ':' in name or '\x00' in name or
            '//' in name or str(norm) != name.rstrip('/') or
            any(c in ('.','..') for c in norm.parts) or norm.parts[0] not in ('app','manifest.json')):
            raise ValueError('압축 안에 안전하지 않은 경로가 있어.')
        if name in seen or name.casefold() in seen_folded:
            raise ValueError('압축 파일에 같은 경로가 중복됐어.')
        seen.add(name)
        seen_folded.add(name.casefold())
        if not i.is_dir() and (not name.startswith('app/') and name != 'manifest.json'):
            raise ValueError('업데이트 압축에는 앱 파일만 포함할 수 있어.')
        if ((i.external_attr>>16)&0o170000)==0o120000:
            raise ValueError('심볼릭 링크가 들어 있는 패키지는 허용하지 않아.')
        if i.file_size>55*1024*1024:
            raise ValueError('개별 파일이 너무 커.')
    if 'manifest.json' not in seen:
        raise ValueError('manifest.json이 없어.')
    manifest=json.loads(zf.read('manifest.json'))
    if not isinstance(manifest,dict) or canonical_version(manifest.get('version'))!=canonical_version(required_version):
        raise ValueError('Release 버전과 앱 패키지 버전이 달라.')
    if manifest.get('entrypoint')!='tracker.py':
        raise ValueError('허용되지 않은 앱 진입점이야.')
    files=manifest.get('files')
    if not isinstance(files,dict) or not files or len(files)>MAX_FILES:
        raise ValueError('파일 목록이 올바르지 않아.')
    paths={name[4:] for name in seen if name.startswith('app/') and not name.endswith('/')}
    if set(files)!=paths or 'tracker.py' not in files:
        raise ValueError('파일 목록과 압축 파일의 내용이 달라.')
    for rel,digest in files.items():
        if not isinstance(rel,str) or not isinstance(digest,str) or not SHA_RE.fullmatch(digest):
            raise ValueError('해시 또는 파일 경로가 올바르지 않아.')
        if sha256_bytes(zf.read('app/'+rel))!=digest:
            raise ValueError('압축 내부 파일의 SHA-256 검증에 실패했어: '+rel)
    return manifest


class Store:
    def __init__(self, root):
        self.root=Path(root).resolve()
        self.versions=self.root/'versions'
        self.data=self.root/'user_data'
        self.state_file=self.root/'launcher_state.json'
        self.settings_file=self.root/'launcher_settings.json'
        for p in (self.versions,self.data,self.data/'assets',self.root/'backups'):
            p.mkdir(parents=True,exist_ok=True)
        self._state_cache=self._load_json(self.state_file,{'current':'8.0.0','previous':[]})
        self._settings_cache=self._load_json(self.settings_file,{'repo':'','check_on_launch':False})

    @staticmethod
    def _load_json(file, default):
        try:
            obj=json.loads(file.read_text(encoding='utf-8'))
            return obj if isinstance(obj,dict) else default.copy()
        except (OSError,ValueError):return default.copy()

    @property
    def state(self):return self._state_cache.copy()

    @property
    def settings(self):return self._settings_cache.copy()

    def set_repo(self,repo):
        repo=repo.strip()
        if repo and not repo_valid(repo):
            raise ValueError('저장소를 GitHub 소유자/저장소 이름으로 입력해 줘.')
        self._settings_cache['repo']=repo
        atomic_json(self.settings_file,self._settings_cache)

    def current_dir(self):
        current=self._state_cache.get('current','8.0.0')
        return self.version_dir(current)

    def version_dir(self,version):
        version=canonical_version(version)
        canonical=self.versions/version
        legacy=self.versions/('v'+version)
        # Read compatibility only: never rename, merge or delete old folders.
        return canonical if (canonical/'tracker.py').is_file() or not (legacy/'tracker.py').is_file() else legacy

    def known_versions(self):
        return sorted({canonical_version(p.name) for p in self.versions.iterdir()
                       if p.is_dir() and VERSION_RE.fullmatch(p.name) and (p/'tracker.py').is_file()},
                      key=version_tuple)

    def set_current(self,version):
        version=canonical_version(version)
        if not (self.version_dir(version)/'tracker.py').is_file():
            raise ValueError('해당 버전의 프로그램 파일이 없어.')
        previous=[v for v in self._state_cache.get('previous',[]) if v!=version and VERSION_RE.fullmatch(str(v))]
        old=self._state_cache.get('current')
        if old and old!=version and old not in previous:
            previous.insert(0,old)
        state={'current':version,'previous':previous[:15]}
        atomic_json(self.state_file,state)
        self._state_cache=state

    def rollback(self):
        current=self._state_cache.get('current','')
        options=[v for v in self._state_cache.get('previous',[]) if v!=current and VERSION_RE.fullmatch(str(v)) and (self.version_dir(v)/'tracker.py').is_file()]
        if not options:
            raise ValueError('되돌릴 수 있는 이전 버전이 없어.')
        selected=options[0]
        new_prev=[v for v in self._state_cache.get('previous',[]) if v!=selected and v!=current]
        if current and current!=selected:new_prev.insert(0,current)
        state={'current':selected,'previous':new_prev}
        atomic_json(self.state_file,state)
        self._state_cache=state
        return selected

    def install_package(self,package_bytes,version):
        version=canonical_version(version)
        if len(package_bytes)>MAX_ZIP:
            raise ValueError('업데이트 파일이 너무 커.')
        import io
        with zipfile.ZipFile(io.BytesIO(package_bytes)) as zf:
            manifest=validate_package(zf,version)
            target=self.versions/version
            if target.exists():
                # Existing version must not be overwritten in place.
                for rel,digest in manifest['files'].items():
                    path=target/rel
                    if not path.is_file() or path.is_symlink() or sha256_bytes(path.read_bytes())!=digest:
                        raise ValueError('기존 버전 폴더의 파일 검증에 실패했어: '+rel)
                self.set_current(version)
                return version
            stage=self.versions/('.stage-'+uuid.uuid4().hex)
            stage.mkdir()
            try:
                for i in zf.infolist():
                    if not i.filename.startswith('app/') or i.is_dir():continue
                    rel=i.filename[4:]
                    out=stage/rel
                    out.parent.mkdir(parents=True,exist_ok=True)
                    with zf.open(i) as src, out.open('wb') as dst:
                        shutil.copyfileobj(src,dst)
                if not (stage/'tracker.py').is_file():
                    raise ValueError('진입점 파일을 찾지 못했어.')
                os.replace(stage,target)
            except BaseException:
                shutil.rmtree(stage,ignore_errors=True)
                raise
        self.set_current(version)
        return version

    def make_backup(self):
        from datetime import datetime
        date=datetime.now().strftime('%Y%m%d_%H%M%S')
        target=self.root/'backups'/('user_data_'+date+'.zip')
        with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for p in sorted(self.data.rglob('*')):
                if p.is_file():z.write(p,arcname=str(p.relative_to(self.data)))
        return target

    def import_legacy(self,folder):
        folder=Path(folder).resolve()
        if folder == self.current_dir() or not (folder/'tracker.py').is_file():
            raise ValueError('이전 버전의 tracker.py가 있는 폴더를 선택해 줘.')
        # Import only known user-generated files; never import executable code.
        keep=('config.json','combat_power.csv','stat_changes.csv','stat_snapshots.csv','stat_latest.json')
        backgrounds=('user_background.png','user_background.gif')
        done=[]
        backup=self.make_backup()
        for name in keep:
            old=folder/name
            new=self.data/name
            if old.is_file() and not new.exists():
                shutil.copy2(old,new);done.append(name)
        for name in backgrounds:
            old=folder/'assets'/name
            new=self.data/'assets'/name
            if old.is_file() and not new.exists():
                shutil.copy2(old,new);done.append('assets/'+name)
        return done,backup

    def fix_background(self,image):
        from PIL import Image
        selected=Path(image)
        with Image.open(selected) as im:
            if im.format not in ('PNG','JPEG','WEBP','BMP'):
                raise ValueError('고정 배경은 PNG, JPG, WEBP, BMP 이미지만 지원해.')
            if im.width*im.height>18_000_000:
                raise ValueError('이미지 해상도가 너무 커. 1800만 화소 이하를 사용해 줘.')
            dst=self.data/'assets'/'fixed_background.png'
            temp=dst.with_name('fixed_background.tmp.png')
            im.convert('RGB').save(temp,format='PNG',optimize=True)
            os.replace(temp,dst)
        # A previous GIF or custom image takes precedence in v8 app; preserve
        # those files but deactivate when the user explicitly fixes background.
        for ext in ('.gif','.png'):
            active=self.data/'assets'/('user_background'+ext)
            stored=self.data/'assets'/('user_background'+ext+'.disabled')
            if active.is_file():
                if stored.exists():stored=stored.with_name(stored.name+'.'+uuid.uuid4().hex[:6])
                active.rename(stored)
        return dst
