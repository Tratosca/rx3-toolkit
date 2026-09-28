# SPDX-License-Identifier: MPL-2.0
"""Local sample projects and audio copies, separate from explicit USB export."""
import copy
import hashlib
import json
import os
import pathlib
import re
import shutil
import tempfile
import threading
import wave

from app.localization import LocalizedError
from app.samples import bank
from app.services import samples

LOCK = threading.RLock()


def root():
    return pathlib.Path.home() / '.rx3-toolbox' / 'sample-projects'


def project_file(drive):
    key = hashlib.sha256(str(pathlib.Path(drive).absolute()).encode()).hexdigest()
    return root() / (key + '.json')


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as out:
            temporary = pathlib.Path(out.name)
            json.dump(value, out, ensure_ascii=False, allow_nan=False)
            out.flush(); os.fsync(out.fileno())
        temporary.replace(path)
    finally:
        if temporary: temporary.unlink(missing_ok=True)


def asset(source):
    source = pathlib.Path(source).resolve(strict=True)
    folder = root() / 'audio'
    folder.mkdir(parents=True, exist_ok=True)
    if source.parent == folder.resolve():
        return str(source)
    with source.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    target = folder / (digest + source.suffix.lower())
    with LOCK:
        if not target.exists():
            temp = None
            try:
                with source.open('rb') as inp, tempfile.NamedTemporaryFile(dir=folder, delete=False) as out:
                    temp = pathlib.Path(out.name)
                    shutil.copyfileobj(inp, out);out.flush();os.fsync(out.fileno())
                with temp.open('rb') as stream:
                    if hashlib.file_digest(stream,'sha256').hexdigest() != digest:
                        raise ValueError('Sample source changed while copying')
                temp.replace(target)
            finally:
                if temp: temp.unlink(missing_ok=True)
    return str(target.resolve())


def validate(project, *, exporting=False):
    if not isinstance(project, dict) or project.get('version') != 1 or not isinstance(project.get('entries'),list):
        raise ValueError('Invalid sample project')
    if len(project['entries']) > 1024:
        raise ValueError('Too many sample banks')
    ids=set();names=set()
    for entry in project['entries']:
        identifier=entry['id'];value=entry['value']
        if not isinstance(identifier,str) or identifier in ids: raise ValueError('Duplicate bank identity')
        ids.add(identifier)
        if not isinstance(value['pads'],list) or len(value['pads'])!=bank.PAD_COUNT: raise ValueError('Invalid pads')
        if exporting:
            name=value['name']
            if not isinstance(name,str) or not re.fullmatch(bank.NAME_RULE,name) or name in names:
                raise LocalizedError('error.bankName')
            names.add(name)
            for pad in value['pads']:
                source=pad.get('source') or pad.get('audioPath') if pad.get('source') or pad.get('keep') else None
                if source and not pathlib.Path(source).is_file(): raise FileNotFoundError(source)
    if project.get('active') is not None and project['active'] not in ids: raise ValueError('Invalid active bank')


def store(drive, project):
    validate(project)
    with LOCK: atomic_json(project_file(drive),project)
    return True


def load(drive):
    with LOCK:
        path=project_file(drive)
        if path.exists():
            project=json.loads(path.read_text(encoding='utf-8'));validate(project)
            return {'project':project}
    inventory=samples.read(pathlib.Path(drive))
    banks=[]
    for name in inventory.names:
        described=samples.describe(pathlib.Path(drive),name)
        for pad in described['pads']:
            if pad['present']:
                pad['path']=asset(pad['path'])
                with wave.open(pad['path'],'rb') as audio: pad['seconds']=audio.getnframes()/audio.getframerate()
        banks.append(described)
    return {'project':None,'banks':banks,'active':inventory.active}


def push(drive, project, progress=lambda done,count:None):
    """Publish a frozen local snapshot; only acknowledge it after all writes."""
    drive=pathlib.Path(drive);validate(project,exporting=True)
    if not drive.is_dir(): raise LocalizedError('error.directory',path=str(drive))
    snapshot=copy.deepcopy(project)
    entries=snapshot['entries'];names={e['value']['name'] for e in entries}
    changed=[e for e in entries if e['value']!=e.get('saved')]
    count=max(1,len(changed)*bank.PAD_COUNT+len(snapshot.get('deleted',[]))+len(entries)+1);done=0
    progress(0,count)
    for entry in changed:
        value=entry['value']
        pads=[dict(source=p.get('source') or p.get('audioPath') if p.get('source') or p.get('keep') else None,
                   colour=p['colour'],name=p['name'],mode=p['mode'],gain=p['gain'],
                   start=p.get('start',0),duration=p['seconds']) for p in value['pads']]
        samples.save(drive,value['name'],pads,volume=value['volume'],shift_silence=value['shiftSilence'],activate=False,
                     progress=lambda n,total:progress(done+n,count))
        done+=bank.PAD_COUNT
    # Activate before removing a formerly active bank. Audio keeps playing on the RX3.
    selected=next((e for e in entries if e['id']==snapshot.get('active')),None)
    if selected: samples.activate(drive,selected['value']['name'])
    removals=set(snapshot.get('deleted',[]))
    removals.update(e['saved']['name'] for e in entries if e.get('saved') and e['saved']['name']!=e['value']['name'])
    for name in removals-names:
        if not re.fullmatch(bank.NAME_RULE,name): raise LocalizedError('error.bankName')
        if name in samples.read(drive).names: samples.remove(drive,name)
        done+=1;progress(done,count)
    for entry in entries:
        entry['value']['onDrive']=True;entry['value']['settingsOk']=True
        entry['saved']=copy.deepcopy(entry['value'])
    snapshot['deleted']=[];snapshot['savedActive']=snapshot.get('active')
    with LOCK:
        # Never erase edits from another session while this export was running.
        path=project_file(drive)
        current=json.loads(path.read_text()) if path.exists() else project
        if current==project: atomic_json(path,snapshot)
    progress(count,count)
    return snapshot
