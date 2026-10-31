"""Stable launcher entry point. Remote releases never modify this file.

Versions reside in launcher_versions/<semver>/; user_data and settings stay in
project root. A failed startup still rolls back on the following launch.
A nonzero exit *after* a healthy acknowledgement also selects the prior
launcher version without touching tracker or personal data. The user restarts
manually; automatic relaunch is intentionally avoided to prevent crash loops.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STATE=ROOT/'launcher_runtime.json'

def load():
    try:
        obj=json.loads(STATE.read_text(encoding='utf-8'))
        return obj if isinstance(obj,dict) else {'current':'0.0.0','previous':[]}
    except (OSError,ValueError):return {'current':'0.0.0','previous':[]}

def save(state):
    # The stable host must not import launcher: Windows resolves launcher.pyw
    # before the same-named namespace directory. Remain independent of payloads.
    temp=STATE.with_name(STATE.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(temp,STATE)
    finally:
        temp.unlink(missing_ok=True)


def entry_for(version):
    if version=='0.0.0':return ROOT/'launcher.pyw'
    canonical=ROOT/'launcher_versions'/version/'launcher.pyw'
    legacy=ROOT/'launcher_versions'/('v'+version)/'launcher.pyw'
    return canonical if canonical.is_file() or not legacy.is_file() else legacy


def rollback_crashed_session(version, session):
    """Rollback only the matching healthy session, never an in-flight upgrade.

    A child may have installed a newer launcher or another host may have
    started meanwhile; both cases must leave the current version alone.
    """
    state=load()
    if state.get('current')!=version or state.get('host_session')!=session:
        return False
    # A pending acknowledgement means startup recovery is governed by main().
    if state.get('pending') is not None:
        return False
    previous=state.get('previous',[])
    if not isinstance(previous,list):
        return False
    import re
    previous=[v for v in previous if isinstance(v,str) and
              re.fullmatch(r'\d+\.\d+\.\d+',v)]
    target=next((v for v in previous if v!=version and
                 (v=='0.0.0' or entry_for(v).is_file())),None)
    if target is None:
        return False
    state['current']=target
    state['previous']=list(dict.fromkeys([version]+[v for v in previous if v!=target]))[:10]
    state.pop('host_session',None)
    save(state)
    return True


def main():
    state=load()
    current=state.get('current','0.0.0')
    prev=state.get('previous',[])
    if not isinstance(current,str) or not __import__('re').fullmatch(r'\d+\.\d+\.\d+',current):current='0.0.0'
    if not isinstance(prev,list):prev=[]
    prev=[p for p in prev if isinstance(p,str) and __import__('re').fullmatch(r'\d+\.\d+\.\d+',p)]
    pending=state.get('pending')
    if isinstance(pending,dict) and pending.get('version')==current and pending.get('attempts',0)>=1:
        # A prior startup did not reach launcher's ready acknowledgement.
        current=next((x for x in prev if x=='0.0.0' or
                      entry_for(x).is_file()),'0.0.0')
        state={'current':current,'previous':list(dict.fromkeys([state.get('current','0.0.0')]+[x for x in prev if x!=current]))[:10]}
        save(state)
    if current!='0.0.0' and not entry_for(current).is_file():
        current='0.0.0'
        state['current']=current
        state.pop('pending',None)
        save(state)
    entry=entry_for(current)
    if isinstance(state.get('pending'),dict) and state['pending'].get('version')==current:
        state['pending']['attempts']=int(state['pending'].get('attempts',0))+1
    # The token prevents a crashed older window from rolling back a newer
    # launch or changing a version the updater activated while it was open.
    session=uuid.uuid4().hex
    state['host_session']=session
    save(state)
    executable=sys.executable
    if os.name=='nt' and executable.lower().endswith('python.exe'):
        pythonw=Path(executable).with_name('pythonw.exe')
        if pythonw.is_file():executable=str(pythonw)
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    process=subprocess.Popen([executable,str(entry)],cwd=str(ROOT),creationflags=flags,
                             env={**os.environ,'DOKKAEBI_LAUNCHER_ROOT':str(ROOT)})
    # Keep this (normally hidden) host alive to observe the child exit code.
    # The existing VBS launcher stays silent; the BAT developer entry remains
    # attached to its console until the GUI exits.
    if current!='0.0.0':
        try:
            exit_code=process.wait()
        except (OSError,ValueError):
            return
        if exit_code != 0:
            rollback_crashed_session(current,session)

if __name__=='__main__':main()
