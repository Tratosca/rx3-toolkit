#!/usr/bin/env python3
"""Read-only package/source comparison. Does not mount or execute the image."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import pycdlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.firmware.firmware_image import read_autoexec, autoexec_iso_metadata
from tests.test_hook_symbols import undefined_symbols, ALLOWED


def digest(data):
    return hashlib.sha256(data).hexdigest()


def audit(package, key, hook, report_sender, status_sender, metadata_server,
          bench_audio_budget_bytes=None):
    manifest=json.loads((package.parent/'rx3-mod-manifest.json').read_text())
    contents=package.read_bytes()
    if manifest['sha256']!=digest(contents) or manifest['bytes']!=len(contents):
        raise ValueError('Package does not match manifest')
    if manifest['firmware']!='1.19' or manifest['modules']!=['core','now-playing','position-diagnostic']:
        raise ValueError('Unexpected firmware or module selection')
    if bench_audio_budget_bytes is None:
        if (manifest.get('benchOnly') or manifest.get('benchAudioBudgetBytes') or
                manifest.get('benchAudioPaceNs')):
            raise ValueError('Bench image needs an explicit budget audit')
    elif not (manifest.get('benchOnly') is True and
              manifest.get('benchAudioBudgetBytes')==bench_audio_budget_bytes==128*1024*1024 and
              manifest.get('benchAudioPaceNs')==600000):
        raise ValueError('Unexpected bench audio budget')
    build_id=manifest.get('buildId')
    if not isinstance(build_id,str) or not re.fullmatch('[0-9a-f]{32}',build_id):
        raise ValueError('Missing or invalid build ID')
    plain=read_autoexec(package,key)
    if autoexec_iso_metadata(plain)!='UsbAuto': raise ValueError('Unexpected volume')
    expected={'/autoexec.sh':ROOT/'mod/autoexec.sh',
              '/modules/compatibility/module.sh':ROOT/'mod/compatibility.sh'}
    for name in ('module-api.sh','safe-mode.sh','volatile-guard.sh','startup-report.sh'):
        expected['/lib/'+name]=ROOT/'mod/lib'/name
    for name in manifest['modules']:
        folder=ROOT/'mod/modules'/name
        specification=json.loads((folder/'manifest.json').read_text())
        for row in specification['files']:
            expected['/modules/'+name+'/'+row['target']]=folder/row['source']
    expected['/modules/core/librx3_core.so']=hook
    expected['/lib/report-send']=report_sender
    expected['/lib/report-send-status']=status_sender
    expected['/lib/metadata-server']=metadata_server
    expected['/lib/build-id']=(build_id+'\n').encode('ascii')
    index=b'compatibility\ncore\nnow-playing\nposition-diagnostic\n'
    iso=pycdlib.PyCdlib();iso.open_fp(io.BytesIO(plain));seen={}
    try:
        for directory, dirs, files in iso.walk(rr_path='/'):
            for name in files:
                path=directory.rstrip('/')+'/'+name
                if path in seen: raise ValueError('Duplicate image path')
                data=io.BytesIO();iso.get_file_from_iso_fp(data,rr_path=path);data=data.getvalue()
                if path=='/modules/index': reference=index
                elif path in expected:
                    reference=expected[path]
                    if isinstance(reference,Path): reference=reference.read_bytes()
                else: raise ValueError('Unexpected image file: '+path)
                if data!=reference: raise ValueError('Source/build mismatch: '+path)
                if path in ('/lib/report-send','/lib/report-send-status',
                            '/lib/metadata-server') and iso.get_record(rr_path=path).rock_ridge.get_file_mode()&0o777!=0o755:
                    raise ValueError('Standalone transport is not executable')
                seen[path]={'bytes':len(data),'sha256':digest(data)}
    finally: iso.close()
    if set(seen)!=set(expected)|{'/modules/index'}: raise ValueError('Missing image file')
    imports=undefined_symbols(hook)
    if imports-ALLOWED: raise ValueError('Unexpected ARM imports: '+repr(imports-ALLOWED))
    result={'package_sha256':digest(contents),'firmware':manifest['firmware'],
            'modules':manifest['modules'],'files':seen,'unexpected_imports':[],
            'result':'exact source and independently built hook match; not hardware certification'}
    if bench_audio_budget_bytes is not None:
        result['bench_audio_budget_bytes']=bench_audio_budget_bytes
        result['bench_audio_pace_ns']=600000
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package',required=True,type=Path)
    p.add_argument('--key',required=True,type=Path)
    p.add_argument('--hook',type=Path,default=ROOT/'build/librx3_core.so')
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--report-sender',type=Path,default=ROOT/'build/report-send')
    p.add_argument('--status-sender',type=Path,default=ROOT/'build/report-send-status')
    p.add_argument('--metadata-server',type=Path,default=ROOT/'build/metadata-server')
    p.add_argument('--bench-audio-budget-bytes',type=int)
    a=p.parse_args()
    result=audit(a.package,a.key,a.hook,a.report_sender,a.status_sender,
                 a.metadata_server,a.bench_audio_budget_bytes)
    with a.output.open('x') as output: json.dump(result,output,indent=2);output.write('\n')
    print('PASS:',len(result['files']),'files match; no unexpected ARM imports')


if __name__=='__main__':main()
