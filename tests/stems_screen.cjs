// SPDX-License-Identifier: MPL-2.0
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor(tag = '') { this.tagName = tag.toUpperCase(); this.children = []; this.events = {}; this.dataset = {}; this.attributes = {}; this.value = ''; }
  append(...items) { this.children.push(...items); if (this.tagName === 'SELECT' && !this.value && items.length) this.value = items[0].value; }
  insertBefore(item, before) { const at=this.children.indexOf(before); this.children.splice(at<0?this.children.length:at,0,item); }
  replaceChildren(...items) { this.children = items; }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(key, callback) { this.events[key] = callback; }
  querySelectorAll(tag) { return this.children.flatMap(child => [...(child.tagName === tag.toUpperCase() ? [child] : []), ...child.querySelectorAll(tag)]); }
  showModal(){this.open=true;}
  close(){this.open=false;}
  get options() { return this.children; }
  get firstElementChild() { return this.children[0]; }
}

(async () => {
  const nodes = new Map();
  // Only permit IDs present in the real screen.
  for (const match of fs.readFileSync('app/ui/web/index.html', 'utf8').matchAll(/id="([^"]+)"/g))
    nodes.set(match[1], new Element());
  const id = key => { assert.ok(nodes.has(key), key); return nodes.get(key); };
  id('playlist').tagName = id('stem-track').tagName = 'SELECT';
  id('library-warning').append(new Element());
  const requests = [];
  const events={};let older=[],wavePending=false;
  let drive="/output",shownDrive=0;
  const quality = {mode: 'normal', accelerator: 'cpu', drumsBlocked: null,
    overcue: {ready:true, message:'experimental'},
    presets: ['quick', 'normal', 'quality'].map(key => ({key, label: key, summary: key}))};
  const window = {
    i18n: {t: (key,args) => key === 'stems.overcueStorage' ? String(args.mb) : key, message: value => value, bytes: String, number: String},
    ui: {preserve: callback => callback()},
    rx3listen: {attach() {}}, addEventListener(name,fn) {events[name]=fn;}, dispatchEvent() {},
    rx3: {
      watchJob() {}, selectedDrive() { return drive; }, showDrive(){shownDrive++;},
      setPath(element, path, fallback) { element.textContent = path || fallback; },
      async ask(method, ...args) {
        requests.push([method, ...args]);
        if (method === 'stems_qualities' || method === 'stems_choose') return quality;
        if (method === 'stems_runtime') return {ready: true, summary: 'ready', accelerators: [{key: 'cpu', label: 'CPU'}]};
        if (method === 'stems_library_status') return {busy: false};
        if (method === 'stems_cache') return {limit: 0, bytes: 0};
        if (method === 'pick_file') return {path: '/library.xml'};
        if (method === 'pick_folder') return {path: '/output'};
        if (method === 'stems_library') return {source: '/library.xml', tracks: 2, playlists: [{id: 'p', name: 'List', tracks: 2}]};
        if (method === 'stems_tracks') return [{id: 'one', title: 'One', artist: ''}, {id: 'two', title: 'Two', artist: ''}];
        if (method === 'stems_wave_settings') return {items:wavePending?[{id:'one',available:true},{id:'missing',available:false}]:[]};
        if (method === 'stems_wave_convert')return {started:true};
        if (method === 'stems_migration_status') return {items:older};
        if (method === 'stems_forecast') return {summary: '', memory: [], overcueStorage:{bytes:75000000,unknown:0}};
        if (method === 'stems_waveform_status') return [{id: 'one', title: 'One', status: 'pending'}, {id: 'two', title: 'Two', status: 'ready'}];
        if (method === 'stems_waveforms_start' || method === 'stems_start') return {started: true};
        throw new Error(method);
      },
    },
  };
  const context = vm.createContext({window, document: {addEventListener(){},querySelector(){return null;},createElement: tag => new Element(tag), getElementById: id}, CustomEvent: class {}});
  vm.runInContext(fs.readFileSync('app/ui/web/stems.js', 'utf8'), context);
  await window.rx3stems.start();
  assert.equal(nodes.has('stem-import-slots'),false);
  assert.equal(nodes.has('roles-row'),false);
  assert.equal(nodes.has('quality-row'),false);
  assert.equal(nodes.has('stems-preparation'),false);
  await id('library-drive').events.click();
  assert.ok(requests.some(r=>r[0]==='stems_library' && r[1]==='/output'));
  assert.ok(!requests.some(r=>r[0]==='pick_folder'));
  drive='';await id('library-drive').events.click();assert.equal(shownDrive,1);
  drive='/output';
  await id('library-file').events.click();
  await new Promise(resolve => setImmediate(resolve));
  await id('stems-start').events.click();
  assert.equal(requests.at(-1)[0], 'stems_start');
  assert.equal(requests.at(-1)[4], true);
  assert.equal(requests.at(-1)[5], false);
  assert.equal(id('stems-overcue-storage').textContent, '75');
  id('stems-overcue').checked=true;
  await id('stems-overcue').events.change();
  await id('stems-start').events.click();
  assert.equal(requests.at(-1)[5], true);
  quality.overcue.ready=false;
  await id('stems-overcue').events.change();
  assert.equal(id('stems-start').disabled,true);
  id('stems-overcue').checked=false;quality.overcue.ready=true;
  await id('stems-overcue').events.change();
  assert.equal(requests.at(-1)[2], '/output');
  assert.deepEqual(Array.from(requests.at(-1)[3]), ['vocals','drums']);
  for(const key of ['stems-legacy-warning','stems-migration-dialog','wave-format-dialog','wave-format-open'])
    assert.equal(nodes.has(key),false,key+' removed from the unified flow');
  events.rx3drive({detail:{path:'/new',music:{present:true}}});
  await new Promise(resolve=>setImmediate(resolve));
  events.rx3language();await new Promise(resolve=>setImmediate(resolve));
  await id('stems-start').events.click();
  assert.equal(requests.at(-1)[2],'/new');
  assert.deepEqual(Array.from(requests.at(-1)[3]),['vocals','drums']);
  assert.ok(!requests.some(r=>['stems_migration_status','stems_migrate','stems_wave_settings','stems_wave_convert'].includes(r[0])));
  console.log('Stems screen, shared USB selection and removed import: OK');
})().catch(error => { console.error(error); process.exitCode = 1; });
