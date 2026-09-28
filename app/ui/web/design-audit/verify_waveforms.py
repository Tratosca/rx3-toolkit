# SPDX-License-Identifier: MPL-2.0
"""Focused native acceptance check; synthetic bridge, no USB writes."""
import json
import pathlib
import runpy
import traceback

fixture = runpy.run_path(str(pathlib.Path(__file__).with_name('verify_ui.py')))
api, window = fixture['api'], fixture['window']
js, wait, action = (fixture[name] for name in ('js', 'wait', 'action'))

def verify():
    report = {'checks': [], 'matrix': []}
    def check(name, value):
        report['checks'].append({'name': name, 'passed': bool(value)})
        assert value, name
    try:
        wait('typeof ready!=="undefined" && ready')
        action('await useDrive('+json.dumps(fixture['DRIVE'])+');')
        js('document.querySelectorAll("dialog[open]").forEach(d=>d.close());show("stems");')
        wait('document.getElementById("wave-format-count").textContent.length>0')
        check('Complete drive has no automatic prompt', js('!document.getElementById("wave-format-dialog").open'))
        js('show("modules");')
        api._wave_pending = True
        action('await useDrive('+json.dumps(fixture['DRIVE'])+');')
        check('USB outside Stems has no waveform prompt', js('!document.getElementById("wave-format-dialog").open'))
        js('document.querySelectorAll("dialog[open]").forEach(d=>d.close());show("stems");')
        wait('document.getElementById("wave-format-dialog").open')
        check('No format picker', js('!document.getElementById("wave-format-choice") && !document.getElementById("wave-format-convert").disabled'))
        for language in ('fr', 'en'):
            for theme in ('light', 'dark'):
                js('i18n.setLanguage('+json.dumps(language)+');ui.theme('+json.dumps(theme)+');')
                metrics = js(fixture['METRICS'])
                report['matrix'].append(metrics)
                check(language+' '+theme+' fits', not any(metrics[k] for k in ('horizontal','overflow','unresolved','unlabeled')))
        js('document.getElementById("wave-format-convert").click();')
        wait('!document.getElementById("wave-format-dialog").open')
        calls = [c for c in api._calls if c['operation']=='stems_wave_convert']
        check('Completion sends only the selected drive', len(calls)==1 and calls[0]['args']==(fixture['DRIVE'],))
        api._wave_pending=False
        js('document.getElementById("wave-format-open").click();')
        wait('document.getElementById("wave-format-dialog").open')
        check('Zero tracks shows only OK', js('!document.getElementById("wave-format-ok").hidden && document.getElementById("wave-format-convert").hidden && document.getElementById("wave-format-later").hidden'))
        report['status']='passed'
    except Exception:
        report['status']='failed'
        report['error']=traceback.format_exc()
    finally:
        pathlib.Path(__file__).with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report),flush=True)
        window.destroy()

if __name__=='__main__': fixture['webview'].start(verify,private_mode=True)
