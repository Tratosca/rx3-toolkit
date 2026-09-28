# SPDX-License-Identifier: MPL-2.0
"""Native, offline UI acceptance fixture. Never imported by the application.

Run from the repository root with .venv/bin/python. Uses the installed pywebview,
production HTML/JS/CSS, read-only metadata and synthetic bridge replies. No real
key, media, network, drive probing, installations or destructive service calls.
"""
import ast
import copy
import base64
import json
import hashlib
import pathlib
import sys
import time
import traceback

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from app.ui.bridge import Bridge, idle_job, operations
import webview

OUTPUT = pathlib.Path(__file__).with_name('dj-verification.json')
DRIVE = '/UI-fixture/USB - Bibliotheque de demonstration - Destination avec un nom long'
SVG = 'data:image/svg+xml;base64,' + base64.b64encode(b'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200"><rect width="400" height="200" fill="white"/><text x="30" y="115" font-size="55" fill="black">RX3 TEST</text></svg>').decode()
SAFE = {'keyshift_preview', 'localization_catalogs', 'localization_language', 'mod_firmwares', 'mod_modules', 'mod_selection', 'samples_defaults', 'logo_limits', 'logo_canvases'}

class Fixture:
    def __init__(self):
        self._real = Bridge()
        self._calls = []
        self._assignments = {}
        self._sample_project = None
        self._mode = 'normal'
        self._wave_changed = False
        self._wave_pending = False
        self._wave_format = '3band'
        self._job = idle_job()
        self._fail = None
        self._installed = True
        self._key = False
        self._runtime_ready = False
        self._bank = 'Demo'
        self._bank_pads = [dict(present=True, path=f'/UI-fixture/pad{i}.wav', seconds=2.5, colour=c, name=f'Sample {i + 1}', mode=i % 4, gain=100) for i,c in enumerate(['#87A5FF','#E4A767','#9BD8C1','#C3ACE7']*2)]
    def _reply(self, name, args):
        self._calls.append({'operation':name,'args':args})
        if self._fail == name:
            self._fail = None
            return {'ok':False,'errorMessage':{'key':'error.directory','params':{'path':DRIVE}}}
        if name in SAFE: return getattr(self._real, name)(*args)
        if name == 'mod_key_hint': value = {'path':'/UI-fixture/retained-key' if self._key else '', 'kept':self._key,'bytes':250_000_000}
        elif name in ('pick_folder','pick_file'): value = {'path':DRIVE if name=='pick_folder' else '/UI-fixture/image.svg'}
        elif name == 'pick_files': value = {'paths':['/UI-fixture/audio.wav']}
        elif name == 'drive_report': value = dict(path=DRIVE,writable=True,mod=dict(installed=self._installed,unrecorded=False,firmware='1.20',modules=['samples','keyshift','stems'],loaded=['samples','stems'],disabled=[]),music=dict(present=True,tracks=2,playlists=1,unreadable=False),banks=[self._bank],activeBank=self._bank,capabilities={'shift_silence':'ready'})
        elif name == 'mod_remove': self._installed=False; value=['autoexec.bin']
        elif name == 'mod_key_forget': self._key=False; value={'removed':True}
        elif name == 'mod_key_fetch': self._key=True; value={'started':False}
        elif name == 'samples_draft_load': value={'project':copy.deepcopy(self._sample_project),'active':self._bank,'banks':[dict(name=self._bank,volume=50,shiftSilence=True,onDrive=True,settingsOk=True,pads=self._bank_pads)]}
        elif name == 'samples_draft_store': self._sample_project=copy.deepcopy(args[1]);value=True
        elif name == 'samples_draft_asset': value=args[0]
        elif name == 'samples_push':
            self._sample_project=copy.deepcopy(args[1])
            for entry in self._sample_project['entries']:
                entry['value']['onDrive']=True;entry['saved']=copy.deepcopy(entry['value'])
            self._sample_project['deleted']=[];self._sample_project['savedActive']=self._sample_project['active']
            self._job=dict(state='done',kind='samples',message={'key':'job.done'},progress=100,error='',result=None)
            value={'started':True}
        elif name == 'samples_read': value={'active':self._bank,'banks':[dict(name=self._bank,volume=50,shiftSilence=True,onDrive=True,settingsOk=True,pads=self._bank_pads)]}
        elif name == 'samples_analyse': value=[dict(accepted=True,path='/UI-fixture/audio.wav',name='UI sample.wav',seconds=2.5)]
        elif name == 'samples_activate': value=True
        elif name == 'samples_remove': value=True
        elif name == 'samples_audition': value={'audio':''}
        elif name == 'logo_open': value={'path':'/UI-fixture/image.svg','width':400,'height':200,'preview':SVG}
        elif name == 'logo_render': value={'canvas':SVG,'lightCanvas':SVG,'faint':False,'invertible':True}
        elif name == 'stems_runtime': value={'ready':self._runtime_ready,'managed':True,'summary':{'key':'stems.engineReady'},'accelerator':'auto','accelerators':[{'key':'auto','label':{'key':'accelerator.auto'}}]}
        elif name in ('stems_qualities','stems_choose'):
            if name=='stems_choose' and args[0]: self._mode=args[0]
            value={'mode':self._mode,'model':'UI fixture','accelerator':'auto','presets':[{'key':m,'label':{'key':f'quality.{m}.name'},'summary':{'key':f'quality.{m}.light'}} for m in ['quality','normal','quick']]}
        elif name == 'stems_cache': value={'bytes':1_048_576,'limit':4*1024**3}
        elif name == 'stems_library_status': value={'busy':False}
        elif name == 'stems_library': value={'source':DRIVE,'tracks':2,'playlists':[{'id':'1','name':'Demo','path':'Collection / Playlist avec un nom long','tracks':2,'missing':0}]}
        elif name == 'stems_waveform_status': value=[]
        elif name == 'stems_tracks': value=[{'id':str(i),'artist':'Artiste de demonstration','title':'Titre de verification '+str(i)} for i in [1,2]]
        elif name == 'stems_forecast': value={'summary':'2 tracks, 30 seconds (fixture)','roles':['vocals'],'refused':0,'blocked':None,'memory':[dict(artist='Artiste',title='Titre',status='ok',reason=None,total=16000000,message={'key':'stems.limitFits','params':{'size':{'key':'unit.mib','params':{'value':15.3}}}})]}
        elif name == 'stems_import_assign':
            if len(args)>1 and args[1] is not None: self._assignments=args[1]
            value=self._assignments
        elif name == 'stems_migration_status': value={'items':[{'id':'1','title':'Older track','artist':'Fixture','available':True}]}
        elif name == 'stems_migrate': value={'started':False}
        elif name == 'stems_wave_settings': value={'format':'all','changed':False,'confirmed':True,'items':[{'id':'1','available':True}] if self._wave_pending else []}
        elif name == 'stems_wave_choose': self._wave_format=args[1];self._wave_changed=False;value={'format':args[1]}
        elif name == 'stems_wave_convert': value={'started':True}
        elif name == 'stems_preview_open': value={'token':'fixture','frames':4410,'channels':3,'sampleRate':44100,'available':7,'peaks':[0.2,0.7,0.3,0.8]*80,'chunkFrames':4410}
        elif name == 'stems_preview_chunk': value={'first':0,'frames':4410,'pcm':[base64.b64encode(b'\0'*4410*8).decode()]*3}
        elif name == 'stems_preview_close': value=True
        elif name in ('stems_audition','stems_import_audition'): value={'available':15,'totalSeconds':60,'seconds':30,'start':args[3],'peaks':[0.2,0.7,0.3,0.8]*80,'audio':'','ramp':[],'rejected':[]}
        elif name in ('mod_build','samples_save','stems_start','stems_import_start','stems_install'):
            if name=='stems_install': self._runtime_ready=True
            kind={'mod_build':'mod','samples_save':'samples','stems_install':'runtime'}.get(name,'stems')
            self._job=dict(state='done',kind=kind,message={'key':'job.done'},progress=100,error='',result={'bytes':1024,'output':DRIVE} if kind=='mod' else {})
            value={'started':True}
        elif name == 'job_status': value=self._job
        elif name == 'job_cancel': self._job=dict(self._job,state='cancelled'); value=True
        elif name == 'reveal': value=True
        else: raise RuntimeError('Unhandled fixture operation: '+name)
        return {'ok':True,'value':value}

def operation(name):
    def call(self, *args): return self._reply(name,args)
    call.__name__=name
    return call
for name in operations(Bridge()): setattr(Fixture,name,operation(name))
api=Fixture()
window=webview.create_window('Toolkit UI verification - synthetic data', (ROOT/'app/ui/web/index.html').as_uri(), js_api=api, width=880, height=560, min_size=(880,560))
source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'app/ui/web').iterdir() if p.suffix in ['.js','.css','.html']}
results={'sourceHashes':source_hashes,'fixture':True,'renderer':'pywebview native','page':'file://app/ui/web/index.html','matrix':[],'checks':[]}

def js(source): return window.evaluate_js(source)
def wait(expression, timeout=15):
    limit=time.monotonic()+timeout
    while time.monotonic()<limit:
        try:
            if js(expression): return
        except Exception: pass
        time.sleep(.05)
    raise AssertionError('Timed out: '+expression)
def action(source):
    js('window.__testDone=false; window.__testError=null; (async()=>{'+source+'})().then(()=>{window.__testDone=true}).catch(e=>{window.__testError=String(e);window.__testDone=true});')
    wait('window.__testDone')
    error=js('window.__testError')
    if error: raise AssertionError(error)
def check(name, value):
    results['checks'].append({'name':name,'passed':bool(value)})
    if not value: raise AssertionError(name)

METRICS = r'''(()=>{
 const visible=e=>!!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
 const screen=document.querySelector('dialog[open]') || document.querySelector('.screen:not([hidden])');
 const body=screen.querySelector('.screen-body') || screen;
 const overflow=[...screen.querySelectorAll('*')].filter(visible).filter(e=>{
  const r=e.getBoundingClientRect();return r.right>innerWidth+1 || r.left<0 || (e.scrollWidth>e.clientWidth+1 && ['BUTTON','SELECT','INPUT'].includes(e.tagName));
 }).map(e=>({id:e.id,tag:e.tagName,cls:e.className,width:e.clientWidth,scroll:e.scrollWidth}));
 const targets=[...screen.querySelectorAll('button,input,select,summary')].filter(visible).filter(e=>!e.disabled).map(e=>{
  const label=e.tagName==='INPUT'&&e.type==='checkbox' ? e.closest('label') : null;
  const r=(label||e).getBoundingClientRect();return {id:e.id,tag:e.tagName,width:r.width,height:r.height};
 }).filter(r=>r.width<27.9||r.height<27.9);
 const names=[...screen.querySelectorAll('input,select')].filter(visible).filter(e=>!e.getAttribute('aria-label')&&!e.getAttribute('aria-labelledby')&&!(e.labels&&e.labels.length)).map(e=>e.id);
 const text=[...screen.querySelectorAll('button,label,h1,h2,p')].filter(visible).filter(e=>/^(ui|quality|stems|samples)\.[a-zA-Z]/.test(e.textContent.trim())).map(e=>e.textContent);
 return {width:innerWidth,height:innerHeight,screen:screen.id,language:i18n.current(),theme:document.documentElement.dataset.theme,overflow,smallTargets:targets,unlabeled:names,unresolved:text,horizontal:body.scrollWidth>body.clientWidth+1};
})()'''

def verify():
    try:
        wait('typeof ready!=="undefined" && ready')
        js('window.__errors=[]; window.addEventListener("error",e=>__errors.push(e.message)); window.addEventListener("unhandledrejection",e=>__errors.push(String(e.reason))); ')
        check('Both language catalogs are complete',js('i18n.missing().length===0'))
        check('Modules has no install button',js('!document.getElementById("build")'))
        check('USB history and technical details removed',js('!document.getElementById("drive-history") && !document.querySelector("#drive-actions details")'))
        check('No encryption prompt on startup',js('!document.querySelector("dialog[open]")'))
        js('document.getElementById("tab-installation").click();')
        check('Install opens destination choice without a key',js('!document.getElementById("installation").hidden && document.getElementById("installation-confirm").disabled'))
        js('show("modules");')
        check('Every checked module appears in recap',js('document.querySelectorAll("#summary-chips li").length===state.modules.filter(m=>state.selected.includes(m.id)).length'))
        check('Recap covers logo samples and stems',js('document.querySelectorAll("#installation-assets dt").length>=3'))
        check('Empty USB control keeps a readable width',js('document.getElementById("rail-drive").getBoundingClientRect().height < 90'))
        check('Logo framing disabled before choosing artwork',js('document.getElementById("logo-controls").disabled'))
        check('Missing preparation tools appear before music',js('document.querySelector("#stems .screen-content > .card").id==="stems-runtime"'))
        js('document.getElementById("runtime-install").click();')
        wait('document.getElementById("runtime-state").textContent===t("stems.ready") && poll===null')
        check('Installation fixture returns to preparation',js('document.querySelector("#stems .screen-content > .card").id!=="stems-runtime"'))
        js('openTerms();i18n.setLanguage("fr");')
        check('Changing legal language resets consent',js('!document.getElementById("terms-accept").checked && document.getElementById("terms-download").disabled'))
        js('document.getElementById("terms-cancel").click();')
        check('Later does not fetch a key',not any(c['operation']=='mod_key_fetch' for c in api._calls))
        action('setKey("/UI-fixture/manual.key");')
        check('Manual key is not claimed as validated',js('document.getElementById("key-state").textContent===t("ui.fileSelected") && document.getElementById("key-forget").hidden && !document.getElementById("key-recover").hidden'))
        action('setKey("");')
        check('Tutorial menu removed',js('!document.getElementById("tab-tutorial") && !document.getElementById("tutorial")'))
        check('First installation is inside installation',js('document.getElementById("installation").contains(document.getElementById("tutorial-start"))'))
        check('Emergency instructions are permanent and offer renaming',js('!document.querySelector(".emergency-help").closest("details") && t("ui.restoreSteps").includes("autoexec.bin.disabled")'))
        check('Associated modules section removed',js('!document.querySelector(".module-relations") && !document.getElementById("modules").textContent.includes(t("ui.dependencies"))'))
        js('show("modules");document.getElementById("module-tutorial-samples").open=true;document.querySelector("#module-tutorial-samples .guide-player").click();')
        check('Module tutorial can pause',js('document.querySelector("#module-tutorial-samples canvas").dataset.manualStep!==undefined'))
        frozen=js('document.querySelector("#module-tutorial-samples canvas").dataset.manualStep')
        js('renderModules();')
        check('Module tutorial pause survives rendering',js('document.querySelector("#module-tutorial-samples canvas").dataset.manualStep')==frozen)
        js('document.querySelector("#module-tutorial-samples .guide-player").click();')
        check('Module tutorial resumes automatically',js('document.querySelector("#module-tutorial-samples canvas").dataset.manualStep===undefined'))
        window.show()
        js('document.querySelector("#module-tutorial-samples canvas").scrollIntoView({block:"center"});')
        wait('document.querySelector("#module-tutorial-samples canvas").dataset.step!=='+json.dumps(frozen))
        check('Module tutorial advances automatically',True)
        # Save the actual canvas frames for local visual inspection.
        for kind in ('samples','stems'):
            js('document.getElementById("module-tutorial-'+kind+'").open=true;')
            for view in (('touch',) if kind == 'samples' else ('pads','touch')):
                for step in (0,1,2,4):
                    encoded=js('(function(){var c=document.querySelector("#module-tutorial-'+kind+' canvas");c.dataset.view="'+view+'";delete c.dataset.manualTime;c.dataset.manualStep="'+str(step)+'";rx3mock.renderPadAccess(c,"'+kind+'");return c.toDataURL("image/png").split(",")[1];})()')
                    pathlib.Path('/tmp/rx3-guide-'+kind+'-'+view+'-'+str(step)+'.png').write_bytes(base64.b64decode(encoded))
            js('document.getElementById("module-tutorial-'+kind+'").open=false;')
        js('document.getElementById("module-tutorial-samples").open=false;document.getElementById("module-tutorial-key-match").open=true;')
        wait('!document.getElementById("key-match-preview").hidden')
        check('Harmonic mock has no reveal button',js('!document.querySelector(".key-match-info") && !document.querySelector(".key-match-demo")'))
        check('Harmonic mock stays inline',js('getComputedStyle(document.getElementById("key-match-preview")).position==="static"'))
        js('document.getElementById("module-tutorial-key-match").open=false;')
        # No source file or real key is ever read by the fixture chooser.
        action('await useDrive('+json.dumps(DRIVE)+');')
        wait('document.getElementById("stems-legacy-warning").open')
        js('document.getElementById("stems-legacy-later").click();')
        wait('document.getElementById("pad-grid").children.length===8 && document.getElementById("stem-track").options.length===2')
        check('USB identity remains visible',js('document.getElementById("rail-drive").textContent.includes(pathName(state.drive))'))
        action('setOutput("/UI-fixture/Other destination");await useDrive('+json.dumps(DRIVE)+');')
        wait('document.getElementById("stems-legacy-warning").open')
        js('document.getElementById("stems-legacy-later").click();')
        check('Drive refresh preserves and explains different destination',js('state.output==="/UI-fixture/Other destination" && !document.getElementById("output-mismatch").hidden'))
        action('setOutput('+json.dumps(DRIVE)+');')
        check('Listening is available from preparation',js('!document.getElementById("stems-listen").closest("#stems-import-view") && !document.getElementById("stems-listen").hidden'))
        js('show("samples");document.getElementById("sample-pick").click();')
        wait('document.querySelector("#inspector h2").textContent===t("samples.padTitle",{index:1}) && document.getElementById("bank-note").textContent===t("ui.sampleAdded",{first:1})')
        check('Adding a sample keeps the filled pad selected',js('document.getElementById("sample-pad-0").getAttribute("aria-checked")==="true"'))
        js('document.getElementById("bank-save").click();')
        wait('poll===null && document.getElementById("bank-state").textContent===t("samples.clean")')
        js('show("logo"); document.getElementById("logo-pick").click();')
        wait('state.logo && state.selected.includes("logo") && document.getElementById("logo-invert-row").hidden===false')
        check('Choosing artwork enables Logo automatically',js('state.selected.includes("logo") && !document.getElementById("logo-next") && !document.getElementById("logo-continue")'))
        check('Hardware tutorials live with their modules',js('document.querySelectorAll("#modules .module-guide").length===4'))
        js('show("stems");document.querySelector("#roles-row button:last-child").click();')
        wait('document.querySelector("#roles-row button:last-child").getAttribute("aria-pressed")==="true" && !document.querySelector("#roles-row button:last-child").disabled')
        check('Selected stem format is visually distinct',js('(function(){var b=document.querySelectorAll("#roles-row button");return getComputedStyle(b[0]).backgroundColor!==getComputedStyle(b[1]).backgroundColor;})()'))
        js('document.querySelector("#roles-row button:first-child").click();')
        wait('document.querySelector("#roles-row button:first-child").getAttribute("aria-pressed")==="true" && !document.querySelector("#roles-row button:first-child").disabled')
        check('Preview contains the track picker',js('document.getElementById("stems-listen").contains(document.getElementById("stem-track"))'))
        check('No output chooser or waveform option in Stems',js('!document.getElementById("stems-output-choose") && !document.getElementById("stems-waveforms")'))
        if '--flows-only' in sys.argv:
            previous=json.loads(OUTPUT.read_text())
            if previous.get('sourceHashes'): assert previous['sourceHashes']==source_hashes, 'UI changed since the retained render matrix'
            results['matrix']=previous['matrix']
            results['matrixReusedFromPreviousConfirmation']=True
        for width,height in ([] if '--flows-only' in sys.argv else [(880,560),(1180,820),(1440,900)]):
            window.resize(width,height)
            wait(f'innerWidth==={width}')
            for language in ['fr','en']:
                js('i18n.setLanguage('+json.dumps(language)+');')
                time.sleep(.25)
                for theme in ['light','dark']:
                    js('ui.theme('+json.dumps(theme)+');')
                    for screen in ['drive','modules','samples','logo','stems','installation','settings']:
                        js('show('+json.dumps(screen)+');')
                        time.sleep(.06)
                        results['matrix'].append(dict(requested=[width,height],**js(METRICS)))
                        if screen=='modules':
                            check('Sidebar fits with Tutorial '+str(width)+' '+language+' '+theme,js('Array.from(document.querySelectorAll("#rail button")).every(e=>{const r=e.getBoundingClientRect();return r.top>=0 && r.bottom<=innerHeight+1 && r.height>=28;})'))
                            check('Module category content is not clipped '+str(width)+' '+language+' '+theme,js('Array.from(document.querySelectorAll("#module-list > .category")).filter(e=>e.tagName!=="DETAILS" || e.open).every(e=>e.scrollHeight<=e.clientHeight+1)'))
                            check('Module options remain visible '+str(width)+' '+language+' '+theme,js('Array.from(document.querySelectorAll("#module-list .module input")).filter(e=>!e.hidden && !e.closest("details:not([open])")).every(e=>{const r=e.getBoundingClientRect(),c=e.closest(".category").getBoundingClientRect();return r.height>0 && r.top>=c.top && r.bottom<=c.bottom;})'))
                    js('show("modules");')
                    for module in ['samples','stems','key-match','now-playing']:
                        js('(()=>{const d=document.getElementById("module-tutorial-'+module+'");const c=d.closest(".category");if(c.tagName==="DETAILS")c.open=true;d.open=true;})()')
                        time.sleep(.08)
                        results['matrix'].append(dict(requested=[width,height],variant='module-guide-'+module,**js(METRICS)))
                        js('document.getElementById("module-tutorial-'+module+'").open=false;')
                    js('show("stems");document.getElementById("stems-migration-dialog").showModal();')
                    time.sleep(.05)
                    results['matrix'].append(dict(requested=[width,height],variant='migration',**js(METRICS)))
                    js('document.getElementById("stems-migration-close").click();')
                    js('show("modules");openInstallation();')
                    check('Install confirmation stays in view '+str(width)+' '+language+' '+theme,js('(()=>{const r=document.getElementById("installation-confirm").getBoundingClientRect();return r.top>=0 && r.bottom<=innerHeight;})()'))
                    js('document.getElementById("installation-options").open=true;')
                    results['matrix'].append(dict(requested=[width,height],variant='installation-options',**js(METRICS)))
                    js('document.getElementById("installation-options").open=false;show("modules");')
        # Key failure, cancellation and completion use only fixture state.
        for state_name in ['failed','cancelled','done']:
            api._job=dict(state=state_name,kind='key',message={'key':'job.done'},progress=100,error={'key':'error.keyNetwork','params':{'name':'fixture.zip','reason':'offline fixture'}} if state_name=='failed' else '',result={'path':'/UI-fixture/key'} if state_name=='done' else None)
            action('await readJob();')
            check('Key result '+state_name,js('document.getElementById("job-retry").hidden')==(state_name=='done'))
            if state_name=='cancelled': check('Cancelled job has no full progress bar',js('document.getElementById("job-bar").hidden'))
            if state_name=='failed': check('Key error retains its diagnostic data',js('document.getElementById("job-diagnostics").textContent.includes("fixture.zip") && document.getElementById("job-diagnostics").textContent.includes("offline fixture")'))
        check('Key success never writes USB automatically',not any(c['operation']=='mod_build' for c in api._calls))
        api._job=dict(state='running',kind='key',message={'key':'job.keyDownload','params':{'part':1,'count':2}},progress=25,error='',result=None,detail={'done':25000000,'total':100000000})
        action('await readJob();')
        check('Key download uses decimal MB from real counters',js('document.getElementById("job-detail").textContent.includes(decimalBytes(25000000)) && document.getElementById("job-detail").textContent.includes(decimalBytes(100000000))'))
        js('document.getElementById("job-close").click();')
        action('await readJob();')
        check('Closing progress survives polling without cancelling',js('document.getElementById("job").hidden && jobDismissed'))
        check('Running task has a persistent badge',js('!document.getElementById("tasks-count").hidden'))
        js('document.getElementById("tasks-open").click();')
        wait('document.getElementById("tasks-dialog").open && !document.getElementById("job").hidden')
        check('Tasks panel reuses live progress and cancellation',js('document.getElementById("tasks-content").contains(document.getElementById("job")) && !document.getElementById("job-cancel").hidden'))
        js('document.getElementById("tasks-close").click();')
        wait('!document.getElementById("tasks-dialog").open && document.getElementById("job").hidden')
        check('Closing the panel restores the hidden strip',js('document.getElementById("job").parentElement===document.body'))

        js('watchJob();')
        wait('!document.getElementById("job").hidden')
        check('Next operation can show progress again',True)

        api._job=idle_job();action('await readJob();')
        # Contrast uses the final computed theme tokens on their intended surfaces.
        results['contrast']=[]
        def luminance(value):
            rgb=[int(value.lstrip('#')[i:i+2],16)/255 for i in (0,2,4)]
            linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb]
            return sum(v*w for v,w in zip(linear,[.2126,.7152,.0722]))
        for theme in ['light','dark']:
            js('ui.theme('+json.dumps(theme)+');')
            palette=js("Object.fromEntries(['text','muted','body','canvas','sidebar','raised','accent-soft','accent','on-accent','good','good-soft','warning','warning-soft','danger','danger-soft','danger-fill','on-danger','focus'].map(n=>[n,getComputedStyle(document.documentElement).getPropertyValue('--'+n).trim()]))")
            pairs=[(fg,bg) for fg in ['text','muted'] for bg in ['body','canvas','sidebar','raised','accent-soft']]+[('on-accent','accent'),('good','good-soft'),('warning','warning-soft'),('danger','danger-soft'),('on-danger','danger-fill')]
            for fg,bg in pairs:
                x,y=sorted([luminance(palette[fg]),luminance(palette[bg])])
                ratio=(y+.05)/(x+.05)
                results['contrast'].append(dict(theme=theme,foreground=fg,background=bg,ratio=round(ratio,3),passed=ratio>=4.5))
        check('Text contrast on designed surfaces',all(x['passed'] for x in results['contrast']))
        check('156 rendered configurations including module tutorials',len(results['matrix'])==156)
        # Mod selection preserves keyboard focus across dependent re-rendering.
        js('show("modules");document.querySelector("#module-list input").focus();window.__focusId=document.activeElement.id;document.activeElement.click();')
        wait('document.activeElement.id===window.__focusId')
        check('Module focus survives selection',js('document.activeElement.id===window.__focusId'))
        # A destructive operation is never sent on open or cancel.
        js('show("drive");document.getElementById("drive-remove").focus();document.getElementById("drive-remove").click();')
        wait('document.getElementById("confirmation").open')
        check('Destructive default focus is Cancel',js('document.activeElement.id==="confirmation-cancel"'))
        check('No deletion before confirmation',not any(c['operation']=='mod_remove' for c in api._calls))
        js('document.getElementById("confirmation-cancel").click();')
        wait('!document.getElementById("confirmation").open')
        check('Cancel preserves deletion boundary',not any(c['operation']=='mod_remove' for c in api._calls))
        check('Dialog restores invoking focus',js('document.activeElement.id==="drive-remove"'))
        # Verify progress semantics for determinate and indeterminate jobs.
        for progress in [23,None]:
            api._job=dict(state='running',kind='stems',message={'key':'job.separate'},progress=progress,error='',result=None,detail={})
            action('await readJob();')
            check('Progress '+str(progress),js('document.getElementById("job-bar").getAttribute("aria-valuenow")')==('23' if progress==23 else None))
        api._job=idle_job();action('await readJob();')
        # Structured transport failures remain local and recoverable.
        api._fail='drive_report';action('await useDrive('+json.dumps(DRIVE)+');')
        check('Drive error is inline',js('document.querySelector("#drive .screen-state").dataset.tone==="error"'))
        action('await useDrive('+json.dumps(DRIVE)+');')
        wait('document.getElementById("stems-legacy-warning").open')
        js('document.getElementById("stems-legacy-later").click();')
        check('Drive retry recovers',js('document.querySelector("#drive .screen-state").hidden'))
        js('document.getElementById("failure").hidden=true;')
        # Exercise destructive acceptance only against synthetic callbacks.
        js('document.getElementById("drive-remove").click();')
        wait('document.getElementById("confirmation").open')
        js('document.getElementById("confirmation-accept").click();')
        wait('document.getElementById("drive-remove").disabled')
        check('Confirmed deletion sent once',sum(c['operation']=='mod_remove' for c in api._calls)==1)
        # Retained key deletion keeps the same zero-argument operation.
        api._key=True; action('await useKeySource();show("modules");')
        js('openInstallation();document.getElementById("installation-options").open=true;document.getElementById("key-forget").click();')
        wait('document.getElementById("confirmation").open')
        check('No key deletion before confirmation',not any(c['operation']=='mod_key_forget' for c in api._calls))
        js('document.getElementById("confirmation-accept").click();')
        wait('state.key===""')
        check('Confirmed key deletion has no arguments',next(c for c in api._calls if c['operation']=='mod_key_forget')['args']==())
        # Consent gating is checked in the isolated fixture, with no network.
        js('document.getElementById("installation-options").open=false;document.getElementById("installation-confirm").click();')
        check('Installation leads to consent when needed',js('document.getElementById("terms").open'))
        check('Consent is unchecked and download disabled',js('!document.getElementById("terms-accept").checked && document.getElementById("terms-download").disabled'))
        js('document.getElementById("terms-body").scrollTop=document.getElementById("terms-body").scrollHeight;termsScrolled();')
        check('Consent becomes available only after scrolling',js('!document.getElementById("terms-accept").disabled'))
        js('document.getElementById("terms-accept").checked=true;document.getElementById("terms-accept").dispatchEvent(new Event("change"));document.getElementById("terms-download").click();')
        wait('state.key!=="" && !document.getElementById("installation").hidden')
        check('Retrieved key returns to installation confirmation',js('document.getElementById("installation-confirm").textContent===t("modules.build")'))
        check('Retrieval alone does not install',not any(c['operation']=='mod_build' for c in api._calls))
        check('Fetch receives explicit true',next(c for c in api._calls if c['operation']=='mod_key_fetch')['args']==(True,))
        action('await rx3.tick("logo");await startBuild();')
        build=next(c for c in api._calls if c['operation']=='mod_build')
        check('Build keeps all nine positional arguments',len(build['args'])==9 and build['args'][3]==DRIVE and set(build['args'][4])=={'path','canvas','mode','zoom','offsetX','offsetY','invertLight'})
        wait('poll===null')
        # Bank switches retain local edits; only explicit export writes USB.
        js('show("samples");document.getElementById("sample-name").value="Edited sample";document.getElementById("sample-name").dispatchEvent(new Event("input"));document.getElementById("bank-new").click();')
        wait('document.getElementById("bank-pick").options.length===2 && !document.getElementById("bank-save").disabled')
        check('New bank does not discard local work',js('!document.getElementById("confirmation").open'))
        js('var p=document.getElementById("bank-pick");p.value=p.options[0].value;p.dispatchEvent(new Event("change"));')
        check('Previous bank edits survive navigation',js('document.getElementById("sample-name").value==="Edited sample"'))
        wait('!document.getElementById("bank-save").disabled')
        check('Pending USB changes are explicit',js('document.getElementById("samples-sync").textContent===t("samples.localOnly")'))
        js('document.getElementById("bank-save").click();')
        wait('poll===null && document.getElementById("samples-sync").textContent===t("samples.synced")')
        saved=next(c for c in reversed(api._calls) if c['operation']=='samples_push')
        check('Export sends every local bank',len(saved['args'])==2 and len(saved['args'][1]['entries'])==2)
        check('Technical module group removed',js('!document.getElementById("modules-advanced")'))
        js('show("stems");')
        check('Manual stem import removed',js('!document.getElementById("stems-view-import") && !document.getElementById("stem-import-slots")'))
        check('Quality details removed',js('!document.getElementById("quality-detail")'))
        check('Standalone legacy button removed',js('!document.getElementById("stems-migration")'))
        js('document.getElementById("stems-migration-dialog").showModal();document.getElementById("stems-migration-all").click();')
        check('Older stems use a dedicated dialog',js('document.getElementById("stems-migration-dialog").open'))
        js('document.getElementById("stems-migration-close").click();')
        check('Migration selection enables both actions',js('!document.getElementById("stems-migrate").disabled && !document.getElementById("stems-migrate-drums").disabled'))
        check('Waveform styles available',js('document.getElementById("stems-wave-style").options.length===3'))
        wait('!document.querySelector("#stems-listen .transport button").disabled')
        check('Local waveform worker completes and enables preview',True)
        api._wave_pending=True
        js('window.dispatchEvent(new CustomEvent("rx3drive",{detail:{path:state.drive,music:{present:true}}}));')
        wait('document.getElementById("stems-legacy-warning").open')
        js('document.getElementById("stems-legacy-later").click();')
        wait('document.getElementById("wave-format-dialog").open')
        check('Older waveforms can be completed without a format choice',js('!document.getElementById("wave-format-choice") && !document.getElementById("wave-format-convert").disabled'))
        for language in ('fr','en'):
            js('i18n.setLanguage('+json.dumps(language)+');')
            results['matrix'].append(js(METRICS))
        before=sum(c['operation']=='stems_wave_convert' for c in api._calls)
        js('document.getElementById("wave-format-later").click();')
        check('Postponing waveform conversion writes nothing',sum(c['operation']=='stems_wave_convert' for c in api._calls)==before)

        check('No horizontal overflow',not any(x['horizontal'] or x['overflow'] for x in results['matrix']))
        check('Minimum hit targets',not any(x['smallTargets'] for x in results['matrix']))
        check('All visible form controls labeled',not any(x['unlabeled'] for x in results['matrix']))
        check('All displayed keys resolved',not any(x['unresolved'] for x in results['matrix']))
        check('No uncaught browser errors',not js('window.__errors'))
        results['browserErrors']=js('window.__errors')
        results['calls']=api._calls
        results['status']='complete'
    except Exception:
        results['status']='failed'; results['error']=traceback.format_exc(); results['calls']=api._calls; results['browserErrors']=js('window.__errors')
    finally:
        OUTPUT.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'status':results['status'],'configurations':len(results['matrix']),'findings':sum(len(x['overflow'])+len(x['smallTargets'])+len(x['unlabeled'])+len(x['unresolved'])+int(x['horizontal']) for x in results['matrix']),'error':results.get('error')},indent=2),flush=True)
        # Leave the synthetic window available for visual review.
        window.resize(880,560)
        js('i18n.setLanguage("fr");ui.theme("dark");show("modules");')

if __name__=='__main__': webview.start(verify,private_mode=True)
