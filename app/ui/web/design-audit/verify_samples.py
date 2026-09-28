# SPDX-License-Identifier: MPL-2.0
"""Native Samples-only acceptance; synthetic drives and in-memory draft storage."""
import json
import pathlib
import runpy
import traceback

fixture=runpy.run_path(str(pathlib.Path(__file__).with_name('verify_ui.py')))
window=fixture['window'];api=fixture['api'];js=fixture['js'];wait=fixture['wait'];action=fixture['action']
report={'fixture':True,'checks':[],'matrix':[]}
def check(label,value):
    assert value,label
    report['checks'].append(label)
def verify():
    try:
        wait('typeof ready!=="undefined" && ready')
        action('await useDrive('+json.dumps(fixture['DRIVE'])+');show("samples");')
        wait('document.getElementById("sample-name")!==null')
        js('window.__errors=[];window.addEventListener("error",e=>__errors.push(e.message));window.addEventListener("unhandledrejection",e=>__errors.push(String(e.reason)));')
        check('Technical group removed',js('!document.getElementById("modules-advanced")'))
        js('document.getElementById("sample-name").value="Local sample";document.getElementById("sample-name").dispatchEvent(new Event("input"));document.getElementById("bank-new").click();')
        wait('document.getElementById("bank-pick").options.length===2 && !document.getElementById("bank-save").disabled')
        check('Creation stays local',not any(c['operation'] in ('samples_push','samples_save','samples_remove','samples_activate') for c in api._calls))
        js('document.getElementById("bank-activate").click();var p=document.getElementById("bank-pick");p.value=p.options[0].value;p.dispatchEvent(new Event("change"));')
        wait('document.getElementById("samples-sync").textContent===t("samples.localOnly")')
        check('Bank switch retains edits',js('document.getElementById("sample-name").value==="Local sample"'))
        check('Pending badge visible',js('!document.getElementById("tag-samples").hidden'))
        for language in ('fr','en'):
            for theme in ('light','dark'):
                for width in (880,1180):
                    window.resize(width,820)
                    action('await i18n.setLanguage('+json.dumps(language)+');ui.theme('+json.dumps(theme)+');')
                    report['matrix'].append(js(fixture['METRICS']))
        js('document.getElementById("bank-save").click();')
        wait('poll===null && document.getElementById("samples-sync").textContent===t("samples.synced")')
        exported=next(c for c in reversed(api._calls) if c['operation']=='samples_push')['args'][1]
        check('Explicit export includes both banks',len(exported['entries'])==2)
        check('Active selection exported',exported['active']==exported['entries'][1]['id'])
        check('Pending badge cleared after success',js('document.getElementById("tag-samples").hidden'))
        check('No overflow or unresolved labels',not any(m['horizontal'] or m['overflow'] or m['unresolved'] or m['unlabeled'] for m in report['matrix']))
        check('No browser errors',not js('window.__errors'))
        report['status']='complete'
    except Exception:
        report['status']='failed';report['error']=traceback.format_exc()
    finally:
        pathlib.Path(__file__).with_name('samples-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'status':report['status'],'checks':len(report['checks']),'configurations':len(report['matrix']),'error':report.get('error')},indent=2),flush=True)
        window.destroy()
fixture['webview'].start(verify,private_mode=True)
