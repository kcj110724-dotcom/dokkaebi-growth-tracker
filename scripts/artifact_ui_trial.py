"""Isolated actual-artifact GUI trial. Never points the product at test releases.

Copies the supplied installation, applies verified downloaded bootstrap, and
overrides discovery/download only in this disposable old-launcher process.
Use UI to install and restart. Actual host/child run, with a lifetime wrapper.
"""
import argparse
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from unittest.mock import patch
from check_installed_transition import hashes
from download_review_artifact import download
import host_transition

ROOT = Path(__file__).resolve().parents[1]


def members(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or len(names)>20 or any('/' in n or '\\' in n for n in names):
            raise ValueError('Unexpected artifact layout')
        if sum(x.file_size for x in archive.infolist())>80*1024*1024:raise ValueError('Expanded artifact too large')
        return {name:archive.read(name) for name in names}


def verify_payload(data, pin):
    if 'sha256:'+hashlib.sha256(data).hexdigest()!=pin['digest']:raise ValueError('Outer digest mismatch')
    files=members(data)
    info=json.loads(files['build-info.json'])
    payload=files['dokkaebi-launcher.zip']
    sha=hashlib.sha256(payload).hexdigest()
    if (info['source_sha']!=pin['source_sha'] or info['component']!='launcher' or
        info['sha256']!=sha or files['dokkaebi-launcher.zip.sha256'].decode('utf-8-sig').split()[0]!=sha):
        raise ValueError('Payload metadata mismatch')
    return files, info


def run(args):
    source=host_transition.checked(args.installation)
    if any(p.is_symlink() or p.is_junction() for p in source.rglob('*')):raise ValueError('Installation links')
    before=hashes(source)
    pins=json.loads((ROOT/'scripts/artifact_review_pins.json').read_text())
    bootstrap, launcher=next(p for p in pins if p['component']=='bootstrap'),next(p for p in pins if p['component']=='launcher')
    outer=(args.artifacts/'bootstrap.zip').read_bytes()
    if 'sha256:'+hashlib.sha256(outer).hexdigest()!=bootstrap['digest']:raise ValueError('Bootstrap outer digest')
    bundle=members(outer)
    inner=bundle['dokkaebi-host-transition.zip']
    if hashlib.sha256(inner).hexdigest()!=bundle['dokkaebi-host-transition.zip.sha256'].decode('utf-8-sig').split()[0]:raise ValueError('Transition digest')
    initial, info=verify_payload((args.artifacts/'launcher.zip').read_bytes(), launcher)
    output=ROOT/('dist/artifact-ui-'+args.fault+'-result.json')
    results={'run_id':launcher['run_id'],'source_sha':launcher['source_sha'],
             'launcher_artifact_sha256':launcher['digest'],'payload_sha256':info['sha256'], 'fault':args.fault}
    host_process=None
    with tempfile.TemporaryDirectory(prefix='artifact-ui-',dir=ROOT/'dist') as temp:
        base=Path(temp).resolve(); root=base/'installation'
        shutil.copytree(source,root)
        package=base/'transition';package.mkdir()
        content=members(inner)
        if set(content)!={'host_transition.py','transition.json','README.md','launch_host.pyw'}:raise ValueError('Transition entries')
        if json.loads(content['transition.json'])['source_sha']!=launcher['source_sha']:raise ValueError('Bootstrap source')
        for name,data in content.items():(package/name).write_bytes(data)
        host_transition.apply(root,package,base/'backup')
        os.environ['DOKKAEBI_LAUNCHER_ROOT']=str(root)
        loader=importlib.machinery.SourceFileLoader('trial_launcher',str(root/'launcher_versions/0.0.1/launcher.pyw'))
        spec=importlib.util.spec_from_loader(loader.name,loader); module=importlib.util.module_from_spec(spec);loader.exec_module(module)
        import update_engine
        import unified_updater
        unified_updater.validate_launcher_archive(initial['dokkaebi-launcher.zip'], info['version'])
        release={'kind':'launcher','version':info['version'],'tag':'launcher-v'+info['version'],
                 'notes':'격리된 Actions artifact 검증', 'url':'https://github.com/isolated/payload',
                 'sha_url':'https://github.com/isolated/hash','digest':info['sha256']}
        module.get_available_releases=lambda repo:{'app':None,'launcher':release}
        original_download=module.get_release_zip
        def supply(release,on_progress=None):
            def progress(done,total):
                if on_progress:on_progress(done,total)
                if args.fault=='interrupted' and done>=262144:raise OSError('Injected transfer interruption')
            data=download(launcher,args.git,base/'download.zip',progress)
            files, metadata=verify_payload(data,launcher)
            payload=files['dokkaebi-launcher.zip']
            if args.fault=='corrupt':payload=payload[:-1]+bytes([payload[-1]^1])
            try:
                with patch.object(update_engine,'github_get',side_effect=[files['dokkaebi-launcher.zip.sha256'],payload]):
                    verified=original_download(release,on_progress=on_progress)
            except ValueError:
                results['payload_hash_rejected']=True
                raise
            results['actual_download_and_hash_verified']=True
            return verified
        module.get_release_zip=supply
        # Record actual restarted child and bound its lifetime, without replacing
        # its UI or host behavior. The wrapper executes the exact installed host.
        wrapper=base/'host_observer.py'
        wrapper.write_text('''import json, pathlib, runpy, subprocess, sys, time
base=pathlib.Path(__file__).parent
original=subprocess.Popen
children=[]
def spawn(*a,**kw):
 p=original(*a,**kw);children.append(p);return p
subprocess.Popen=spawn
try:
 runpy.run_path(str(base/'installation/launch_host.pyw'),run_name='__main__')
 (base/'child.json').write_text(json.dumps({'pid':children[-1].pid}))
 for i in range(600):
  if (base/'finish').exists() or children[-1].poll() is not None:break
  time.sleep(.1)
finally:
 for p in children:
  if p.poll() is None:p.terminate()
  p.wait(timeout=15)
''',encoding='utf-8')
        real_popen=subprocess.Popen
        def launch(args_,**kwargs):
            nonlocal host_process
            if Path(args_[0]).resolve()==Path(args.git).resolve():
                return real_popen(args_,**kwargs)
            if Path(args_[1]).resolve()!=root/'launch_host.pyw':raise ValueError('Unexpected subprocess in trial')
            if args.fault=='startup':
                entry=root/'launcher_versions'/info['version']/'launcher.pyw'
                entry.write_text('raise SystemExit(7)\n')
            host_process=real_popen([sys.executable,str(wrapper)],**kwargs)
            return host_process
        try:
            tk=module.tk.Tk(); app=module.Launcher(tk)
            results['ui_stages']=[]
            def observe():
                stage=app.modal or 'home'
                if not results['ui_stages'] or results['ui_stages'][-1]!=stage:
                    results['ui_stages'].append(stage)
                    print('UI_STAGE: '+stage,flush=True)
                tk.after(100,observe)
            tk.after(100,observe)
            # Avoid indefinite orphaned test UI if desktop control is interrupted.
            tk.after(180000,tk.destroy)
            with patch.object(module.subprocess,'Popen',side_effect=launch):
                print('UI_READY: isolated 0.0.1 discovery',flush=True)
                tk.mainloop()
            state_path=root/'launcher_runtime.json'
            if host_process:
                deadline=time.monotonic()+25
                while time.monotonic()<deadline:
                    state=json.loads(state_path.read_text())
                    if args.fault=='startup' and host_process.poll() is not None:break
                    if state['current']==info['version'] and 'pending' not in state:
                        results['restart_healthy']=True; print('RESTART_HEALTHY',flush=True);break
                    time.sleep(.1)
                if args.fault=='startup':
                    host_process.wait(timeout=15)
                    host_process=real_popen([sys.executable,str(wrapper)],cwd=root,env={**os.environ,'DOKKAEBI_LAUNCHER_ROOT':str(root)})
                    time.sleep(4)
                    results['startup_rollback']=(json.loads(state_path.read_text())['current']=='0.0.1'
                                                 and host_process.poll() is None)
                time.sleep(12)
            else:
                results['no_activation']=json.loads(state_path.read_text())['current']=='0.0.1'
                results['stopped_before_restart']=not results['no_activation']
        finally:
            (base/'finish').touch()
            if host_process:host_process.wait(timeout=20)
            after=hashes(root)
            results['preserved']=all(after.get(n)==h for n,h in before.items() if n not in {'launch_host.pyw','launcher_runtime.json'})
            results['original_unchanged']=hashes(source)==before
            output.write_text(json.dumps(results,indent=2),encoding='utf-8')
            print(json.dumps(results,indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installation',type=Path,required=True)
    parser.add_argument('--artifacts',type=Path,default=ROOT/'dist/online-artifacts')
    parser.add_argument('--git',required=True)
    parser.add_argument('--fault',choices=['none','corrupt','interrupted','startup'],default='none')
    run(parser.parse_args())
