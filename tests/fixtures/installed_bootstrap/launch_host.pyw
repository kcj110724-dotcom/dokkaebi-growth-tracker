"""Stable launcher entry point. Remote releases never modify this file.

Versions reside in launcher_versions/<semver>/; user_data and settings stay in
project root. If the newly installed launcher crashes before acknowledging its
startup, a subsequent launch automatically selects the previous known version.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STATE=ROOT/'launcher_runtime.json'

def load():
    try:
        obj=json.loads(STATE.read_text(encoding='utf-8'))
        return obj if isinstance(obj,dict) else {'current':'0.0.0','previous':[]}
    except (OSError,ValueError):return {'current':'0.0.0','previous':[]}

def save(state):
    from launcher.update_engine import atomic_json
    atomic_json(STATE,state)

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
                      (ROOT/'launcher_versions'/x/'launcher.pyw').is_file()),'0.0.0')
        state={'current':current,'previous':list(dict.fromkeys([state.get('current','0.0.0')]+[x for x in prev if x!=current]))[:10]}
        save(state)
    if current!='0.0.0' and not (ROOT/'launcher_versions'/current/'launcher.pyw').is_file():
        current='0.0.0'
        state['current']=current
        state.pop('pending',None)
        save(state)
    entry=(ROOT/'launcher.pyw') if current=='0.0.0' else (ROOT/'launcher_versions'/current/'launcher.pyw')
    if isinstance(state.get('pending'),dict) and state['pending'].get('version')==current:
        state['pending']['attempts']=int(state['pending'].get('attempts',0))+1
        save(state)
    executable=sys.executable
    if os.name=='nt' and executable.lower().endswith('python.exe'):
        pythonw=Path(executable).with_name('pythonw.exe')
        if pythonw.is_file():executable=str(pythonw)
    # Use a child GUI interpreter so the host can exit; no open console window.
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    subprocess.Popen([executable,str(entry)],cwd=str(ROOT),creationflags=flags,
                     env={**os.environ,'DOKKAEBI_LAUNCHER_ROOT':str(ROOT)})

if __name__=='__main__':main()
