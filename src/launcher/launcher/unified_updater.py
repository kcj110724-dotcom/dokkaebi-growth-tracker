"""Version-separated GitHub Releases discovery and launcher-side-by-side updater.

Public releases: tracker-v0.0.1 (growth tracker), launcher-v0.0.1 (launcher).
The stable launch_host.pyw is intentionally NOT included in remote releases.
"""
from __future__ import annotations
import hashlib
import io
import json
import os
import re
import shutil
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from update_engine import (github_get, get_release_zip, version_tuple,
                           repo_valid, atomic_json, SHA_RE)

LAUNCHER_ARCHIVE='dokkaebi-launcher.zip'
LAUNCHER_SHA=LAUNCHER_ARCHIVE+'.sha256'
MAX_ARCHIVE=40*1024*1024
MAX_EXPANDED=130*1024*1024
MAX_ENTRY=20*1024*1024
MAX_ITEMS=160
APP_TAG=re.compile(r'^tracker-v\d+\.\d+\.\d+$')
LAUNCHER_TAG=re.compile(r'^launcher-v\d+\.\d+\.\d+$')
LAUNCHER_VERSION='0.0.0'

# Explicit reset policy v1: 8.x/9.x belong to the legacy epoch of EACH
# component. Tagged 0.x starts the successor epoch. 8/9 remain reserved;
# returning to them is a manual rollback, never an automatic update.
def release_order(kind,version):
    if kind not in ('app','launcher'):
        raise ValueError('Unknown update component')
    number=version_tuple(version)
    return (0 if number[0] in (8,9) else 1, number)


def is_update(info,kind,current):
    if kind not in ('app','launcher') or info.get('kind')!=kind:return False
    prefix='tracker-v' if kind=='app' else 'launcher-v'
    version=info.get('version','')
    if info.get('tag')!=prefix+version:return False
    return release_order(kind,version)>release_order(kind,current)


def active_launcher_version(root):
    path=Path(root)/'launcher_runtime.json'
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        return '.'.join(map(str,version_tuple(data.get('current','0.0.0'))))
    except (OSError,ValueError,TypeError,KeyError):
        return LAUNCHER_VERSION


def _release_item(release, kind):
    if not isinstance(release,dict) or release.get('draft') or release.get('prerelease'):
        return None
    tag=release.get('tag_name','')
    if kind=='launcher':
        if not LAUNCHER_TAG.fullmatch(tag):return None
        ver=tag[len('launcher-v'):]
        zipname=LAUNCHER_ARCHIVE
        shaname=LAUNCHER_SHA
    else:
        if not APP_TAG.fullmatch(tag):return None
        ver=tag[len('tracker-v'):] 
        zipname='dokkaebi-app.zip'
        shaname=zipname+'.sha256'
    version_tuple(ver)
    assets={a.get('name'):a for a in release.get('assets',[]) if isinstance(a,dict)}
    package=assets.get(zipname)
    sha=assets.get(shaname)
    if not package or not sha:
        # Requiring both for every release prevents partial upload recognition.
        return None
    url=package.get('browser_download_url','')
    sha_url=sha.get('browser_download_url','')
    digest=package.get('digest') or ''
    if not url or not sha_url or not digest.startswith('sha256:') or not SHA_RE.fullmatch(digest[7:]):
        return None
    size=package.get('size',0)
    if not isinstance(size,int) or not 0<size<=(MAX_ARCHIVE if kind=='launcher' else 65*1024*1024):
        return None
    return {'kind':kind,'version':ver,'notes':release.get('body',''),
            'url':url,'sha_url':sha_url,'digest':digest[7:], 'tag':tag}


def get_available_releases(repo):
    if not repo_valid(repo):
        raise ValueError('GitHub 저장소 주소 형식을 확인해 줘 (사용자/저장소).')
    # GitHub sorts releases by published date, not version. Pick the highest matching version.
    url=f'https://api.github.com/repos/{repo}/releases?per_page=100'
    data=json.loads(github_get(url,limit=4*1024*1024))
    if not isinstance(data,list):raise ValueError('GitHub Release 응답이 올바르지 않아.')
    result={'app':None,'launcher':None}
    for rel in data:
        for kind in ('app','launcher'):
            item=_release_item(rel,kind)
            if item and (result[kind] is None or release_order(kind,item['version'])>release_order(kind,result[kind]['version'])):
                result[kind]=item
    return result


def _filename_ok(path):
    if not isinstance(path,str) or not path or path.startswith('/') or '\\' in path or ':' in path or '\x00' in path:
        return False
    pure=PurePosixPath(path)
    if str(pure)!=path or any(p in ('','..','.') for p in pure.parts):return False
    if path=='launcher.pyw':return True
    if path in ('launcher/update_engine.py','launcher/unified_updater.py'):return True
    if path.startswith('assets/') and len(pure.parts)>=2:
        return path.lower().endswith(('.png','.jpg','.jpeg','.gif','.ico','.mp4','.webp'))
    return False


def validate_launcher_archive(data, version):
    if len(data)>MAX_ARCHIVE:raise ValueError('런처 업데이트 파일이 지나치게 커.')
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        entries=zf.infolist()
        if len(entries)>MAX_ITEMS:raise ValueError('런처 ZIP에 파일이 너무 많아.')
        if sum(i.file_size for i in entries)>MAX_EXPANDED:raise ValueError('런처 ZIP 압축 해제 용량 초과.')
        names=[]; seen=set()
        for info in entries:
            name=info.filename
            if name.endswith('/'):
                # archive builder doesn't add explicit directory records
                raise ValueError('허용되지 않은 폴더 엔트리가 있어.')
            if name not in ('manifest.json',) and not _filename_ok(name):
                raise ValueError('허용되지 않은 런처 파일 경로: '+name)
            if name.casefold() in seen:raise ValueError('중복된 파일 이름이 있어.')
            seen.add(name.casefold())
            mode=(info.external_attr>>16)&0o170000
            if mode in (0o120000,0o060000,0o020000):raise ValueError('특수 파일은 설치할 수 없어.')
            if info.file_size>MAX_ENTRY:raise ValueError('개별 파일 제한 초과.')
            names.append(name)
        if 'manifest.json' not in names:raise ValueError('manifest.json 누락.')
        manifest=json.loads(zf.read('manifest.json'))
        if not isinstance(manifest,dict) or manifest.get('kind')!='launcher' or manifest.get('entrypoint')!='launcher.pyw':
            raise ValueError('런처 업데이트 manifest 형식 오류.')
        if version_tuple(manifest.get('version',''))!=version_tuple(version):
            raise ValueError('GitHub 태그와 업데이트 버전이 달라.')
        files=manifest.get('files',None)
        if not isinstance(files,dict) or set(files)!=(set(names)-{'manifest.json'}):
            raise ValueError('manifest 파일 목록 불일치.')
        if not {'launcher.pyw','launcher/update_engine.py','launcher/unified_updater.py'}<=set(files):
            raise ValueError('런처 필수 파일이 빠져 있어.')
        for name,digest in files.items():
            if not _filename_ok(name) or not isinstance(digest,str) or not SHA_RE.fullmatch(digest):
                raise ValueError('파일 체크섬 항목이 올바르지 않아.')
            if hashlib.sha256(zf.read(name)).hexdigest()!=digest:
                raise ValueError('런처 내부 체크섬이 달라: '+name)
        return files


class LauncherManager:
    def __init__(self, root):
        self.root=Path(root).resolve()
        self.state_path=self.root/'launcher_runtime.json'
        self.versions=self.root/'launcher_versions'
        self.versions.mkdir(parents=True,exist_ok=True)

    def read(self):
        try:
            obj=json.loads(self.state_path.read_text(encoding='utf-8'))
            if isinstance(obj,dict) and version_tuple(obj.get('current','0.0.0')):
                return obj
        except (OSError,ValueError,TypeError,KeyError):pass
        return {'current':'0.0.0','previous':[]}

    def active(self):return self.read()['current']

    def entry(self, version=None):
        version=version or self.active()
        version='.'.join(map(str,version_tuple(version)))
        if version=='0.0.0':return self.root/'launcher.pyw'
        canonical=self.versions/version/'launcher.pyw'
        legacy=self.versions/('v'+version)/'launcher.pyw'
        return canonical if canonical.is_file() or not legacy.is_file() else legacy

    def install(self, package:bytes, version:str):
        version='.'.join(map(str,version_tuple(version)))
        files=validate_launcher_archive(package,version)
        target=self.versions/version
        if target.exists():
            # A previously installed version may have been modified on disk:
            # refuse activation unless every file matches verified package.
            for rel,digest in files.items():
                p=target/rel
                if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
                    raise ValueError('기존 런처 폴더가 변경됐어. 자동 적용을 중단했어.')
        else:
            stage=self.versions/('.stage-'+uuid.uuid4().hex)
            try:
                stage.mkdir()
                with zipfile.ZipFile(io.BytesIO(package)) as z:
                    for rel in files:
                        out=stage/rel
                        out.parent.mkdir(parents=True,exist_ok=True)
                        with z.open(rel) as source, out.open('wb') as dest:
                            shutil.copyfileobj(source,dest)
                # Syntax check without executing downloaded Python code.
                for rel in ('launcher.pyw','launcher/update_engine.py','launcher/unified_updater.py'):
                    compile((stage/rel).read_text(encoding='utf-8'),str(stage/rel),'exec')
                os.replace(stage,target)
            finally:
                if stage.exists():shutil.rmtree(stage,ignore_errors=True)
        state=self.read()
        prev=[v for v in state.get('previous',[]) if v!=version and isinstance(v,str)]
        old=state['current']
        if old!=version:
            prev.insert(0,old)
        state={'current':version,'previous':prev[:10],
               'pending':{'version':version,'attempts':0}}
        atomic_json(self.state_path,state)
        return version

    def confirm_healthy(self):
        state=self.read()
        pending=state.get('pending')
        if isinstance(pending,dict) and pending.get('version')==state.get('current'):
            state.pop('pending',None)
            atomic_json(self.state_path,state)

    def rollback(self):
        state=self.read()
        current=state['current']
        alternatives=[x for x in state.get('previous',[]) if x!=current and isinstance(x,str)
                      and re.fullmatch(r'\d+\.\d+\.\d+',x) and self.entry(x).is_file()]
        if not alternatives:raise ValueError('복구 가능한 이전 런처 버전이 없어.')
        selected=alternatives[0]
        previous=[x for x in state.get('previous',[]) if x not in (selected,current)]
        previous.insert(0,current)
        atomic_json(self.state_path,{'current':selected,'previous':previous[:10]})
        return selected
