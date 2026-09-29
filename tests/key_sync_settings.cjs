// SPDX-License-Identifier: MPL-2.0
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {execFileSync}=require('node:child_process');
const python = process.env.RX3_TEST_PYTHON || 'python3';
class Element {
  constructor(tag='div') { this.tagName=tag; this.children=[]; this.dataset={}; this.events={}; this.attributes={}; }
  append(...items) { this.children.push(...items); for(const item of items)if(item && typeof item==='object')item.parentNode=this; }
  replaceWith(node) { const parent=this.parentNode;if(parent){parent.children[parent.children.indexOf(this)]=node;node.parentNode=parent;} }
  closest(tag) { for(let node=this.parentNode;node;node=node.parentNode)if(node.tagName===tag)return node;return null; }
  replaceChildren(...items) { this.children=[...items]; }
  get firstElementChild() { return this.children[0]; }
  querySelectorAll(selector) { return selector === '.module-meta' ? this.children.filter(child=>(child.className||'').includes('module-meta')) : []; }
  setAttribute(name,value) { this.attributes[name]=value; }
  close() {this.open=false;}
  showModal() {this.open=true;}
  focus() {}
  addEventListener(name, callback) { this.events[name]=callback; }
}
const storage=new Map();
function load() {
  const elements=new Map();
  const document={createElement:tag=>new Element(tag), querySelectorAll:()=>[], querySelector:()=>new Element(), getElementById(id) {
    if (!elements.has(id)) elements.set(id,new Element()); return elements.get(id);
  }};
  const window=new Element();
  window.i18n={t:key=>key};
  window.matchMedia=()=>({matches:false});
  window.rx3mock={renderBrowser:async(canvas,data)=>{canvas.previewData=data;}};
  window.localStorage={getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value)};
  const context=vm.createContext({window,document,console,setTimeout,clearTimeout,navigator:{language:"en"}});
  vm.runInContext(fs.readFileSync('app/ui/web/app.js','utf8'),context);
  context.ask=async (name,...args)=>{
    assert.equal(name,'keyshift_preview');
    return JSON.parse(execFileSync(python,['-c',
      'import json,sys;from app.services.keyshift import preview;print(json.dumps(preview(*json.loads(sys.argv[1]))))',JSON.stringify(args)],{encoding:'utf8'}));
  };
  return context;
}
function find(node,id) {
 if(node.id===id)return node;
 for(const child of node.children||[]) {const hit=find(child,id);if(hit)return hit;}
}
(async()=>{
const item={id:'key-sync',requires:[],conflicts:[],selectable:true};
const matchItem={id:'key-match',requires:['core'],conflicts:[],selectable:true};
let ui=load();ui.state.modules=[item,matchItem];ui.state.selected=['key-sync','key-match'];
assert.equal(ui.state.keySyncRange,1);assert.equal(ui.state.keySyncMode,'harmonic');assert.equal(ui.state.keyMatchRules,0);
let tile=ui.moduleTile(item),settings=tile.children[1];
let matchTile=ui.moduleTile(matchItem);
assert.equal(matchTile.children[1].children[0].className,'key-match-settings');
assert.equal(find(tile,'key-match-rule-2'),undefined);
let range=find(tile,'key-sync-range'),mode=find(tile,'key-sync-mode'),description=find(tile,'key-sync-mode-help');
assert.equal(range.value,'1');assert.equal(range.children.length,12);
assert.equal(description.textContent,'keyshift.modeHelp');
mode.value='identical';mode.events.change();assert.equal(description.textContent,'keyshift.syncHelp');
assert.equal(load().state.keySyncMode,'identical','saved mode survives new defaults');
mode.value='harmonic';mode.events.change();
range.value='3';range.events.change();assert.equal(load().state.keySyncRange,3);
range.value='1';range.events.change();
const match=matchTile.children[1].children[0],heading=match.children[0],native=match.children[1];
assert.equal(native.children[0].checked,true);assert.equal(native.children[0].disabled,true);
assert.equal(native.children[1].src,'key-match-green.svg');
const help=ui.keyMatchPreview(),preview=help.children[0];
const guide=new Element('details');guide.open=true;guide.append(help);
await help.reveal();
const browser=preview.children[0],transcript=preview.children[1];
assert.equal(browser.tagName,'canvas');
assert.equal(browser.previewData.master,'8A');
assert.equal(browser.previewData.rows.length,12);assert.equal(browser.previewData.rows[2].key,'2A');
assert.deepEqual([...new Set(browser.previewData.rows.map(row=>row.colour))].sort(),[null,'green','yellow','orange','red'].sort());
assert.ok(browser.previewData.rows.every(row=>!('title' in row)));
assert.equal(transcript.children.length,13);
assert.ok(transcript.children.some(line=>line.textContent.includes('2A')));
assert.equal(browser.previewData.shift,1);
mode.value='identical';mode.events.change();await help.refresh();assert.equal(browser.previewData.shift,0);
range.value='6';range.events.change();await help.refresh();assert.equal(browser.previewData.shift,6);
mode.value='harmonic';mode.events.change();
for(const [index,colour] of ['yellow','orange','red'].entries()) {
 const row=match.children[index+2],input=row.children[0],icon=row.children[1];
 assert.equal(input.checked,false);assert.equal(icon.src,'key-match-'+colour+'.svg');assert.ok(fs.existsSync('app/ui/web/'+icon.src));
}
assert.equal(match.children[5].hidden,true);assert.equal(match.children[6].hidden,true);
const boost=find(matchTile,'key-match-rule-2');boost.checked=true;boost.events.change();await help.refresh();
assert.equal(match.children[5].hidden,false);assert.equal(match.children[6].hidden,true);
assert.equal(browser.previewData.rows[3].colour,'yellow');
const four=find(matchTile,'key-match-rule-8');four.checked=true;four.events.change();await help.refresh();
assert.equal(match.children[6].hidden,false);assert.equal(load().state.keyMatchRules,10);
await help.dismiss();guide.open=false;
const previousData=browser.previewData;await help.refresh();assert.equal(browser.previewData,previousData);
guide.open=true;await help.reveal();
ui.state.selected=[];tile=ui.moduleTile(item);
assert.equal(find(tile,'key-sync-range').disabled,true);assert.equal(find(tile,'key-sync-mode').disabled,true);
assert.equal(find(ui.moduleTile(matchItem),'key-match-rule-2').disabled,true);
ui.state.selected=['key-match'];await help.refresh();
assert.equal(find(ui.moduleTile(matchItem),'key-match-rule-2').disabled,false);
for(let saved=0;saved<16;saved++) {storage.set('rx3.keyMatchRules',String(saved));assert.equal(load().state.keyMatchRules,saved&14);}
for(const invalid of ['-1','16','oops','1.5']) {storage.set('rx3.keyMatchRules',invalid);assert.equal(load().state.keyMatchRules,0);}
for(const invalid of ['0','13','oops','1.5']) {storage.set('rx3.keySyncRange',invalid);assert.equal(load().state.keySyncRange,1);}
storage.set('rx3.keySyncMode','bad');assert.equal(load().state.keySyncMode,'harmonic');

const browseItem={id:'browse-columns',requires:[],conflicts:[],selectable:true};
ui=load();ui.state.modules=[browseItem];ui.state.selected=['browse-columns'];
assert.equal(ui.state.browseColumn,13);
let browseSelect=ui.moduleTile(browseItem).children[1].children[1];
assert.equal(browseSelect.children.length,4);assert.equal(browseSelect.disabled,false);
browseSelect.value='15';browseSelect.events.change();
assert.equal(ui.state.browseColumn,15);assert.equal(load().state.browseColumn,15);
assert.deepEqual(Array.from(ui.state.selected),['browse-columns']);
ui.state.selected=[];assert.equal(ui.moduleTile(browseItem).children[1].children[1].disabled,true);
for(const invalid of ['0','14','oops','1.5']) {
 storage.set('rx3.browseColumn',invalid);assert.equal(load().state.browseColumn,13);
}

{
  const profiled={id:'native-wifi',requires:[],conflicts:[],selectable:true,profiles:['rtl8188cu','rtl8192cu']};
  ui=load();ui.t=(key)=>key;ui.renderSummary=()=>{};
  ui.state.modules=[profiled];ui.state.selected=['native-wifi'];
  const group=ui.moduleTile(profiled),select=group.children[1].children[1];
  assert.equal(select.children.length,3);assert.equal(select.value,'');
  select.value='rtl8192cu';select.events.change();
  assert.equal(ui.state.profiles['native-wifi'],'rtl8192cu');

  ui.state.key='chosen-key';ui.state.output='/fixture/USB';
  let request;ui.ask=async (...args)=>{request=args;return {started:true};};ui.watchJob=()=>{};
  await ui.startBuild();
  assert.deepEqual(Object.entries(request[10]),[['native-wifi','rtl8192cu']]);
}

{
  ui=load();
  ui.state.modules=[item,{id:'core',selectable:false},{id:'key-match',selectable:true}];
  ui.state.selected=['core','key-match','key-sync'];
  ui.state.key='chosen-key';ui.state.output='/fixture/USB';
  let request;
  ui.ask=async (...args)=>{request=args;return {started:true};};
  ui.renderSummary=()=>{};ui.watchJob=()=>{};
  await ui.startBuild();
  assert.equal(request[0],'mod_build');
  assert.deepEqual(Array.from(request[2]),['key-match','key-sync'],'build receives the visible module; dependencies are resolved by the backend');
}

for (const language of ['en', 'fr']) {
  const context=load();
  const catalog=JSON.parse(fs.readFileSync('app/localization/'+language+'.json','utf8'));
  context.t=(key,params={})=>catalog[key].replace(/\{(\w+)\}/g,(_,name)=>params[name]);
  const relation=context.moduleRelation('modules.needs','<Test & module>',false);
  assert.equal(relation.tagName,'em');
  assert.equal(relation.children[1].tagName,'strong');
  assert.equal(relation.children[1].textContent,'<Test & module>');
  assert.equal(relation.children[0]+relation.children[1].textContent+relation.children[2],
    catalog['modules.needs'].replace('{names}','<Test & module>'));
}

// Real manifests and the bridge drive categories and both UI languages.
{
  const data=JSON.parse(execFileSync(python,['-c',
    "import json;from app.localization import catalogs;from app.ui.bridge import Bridge;print(json.dumps({'catalogs':catalogs(),'modules':Bridge().mod_modules('1.19')['value']}))"],{encoding:'utf8'}));
  for (const language of ['en','fr']) {
    ui=load();ui.renderSummary=()=>{};ui.state.modules=data.modules;
    ui.t=(key,params={})=>{
      let text=data.catalogs[language][key];assert.notEqual(text,undefined,key);
      if(typeof text==='object')text=text.other;
      return text.replace(/\{(\w+)\}/g,(_,name)=>params[name]);
    };
    ui.renderModuleContent();
    const allGroups=ui.document.getElementById('module-list').children;
    const groups=allGroups.filter(group=>group.id!=='modules-advanced');
    assert.deepEqual(Array.from(groups,group=>group.dataset.category),
      ['beatjump','harmonic-mixing','samples','stems','screen','streaming','diagnostics']);
    for(const group of groups) {
      const module=data.modules.find(item=>item.category===group.dataset.category);
      assert.equal(group.children[0].children[0].children[0].textContent,module.categoryUi.name[language]);
    }
    assert.ok(find(groups[1],'module-toggle-keyshift'));
    assert.ok(find(groups[1],'module-toggle-key-match'));
    assert.ok(find(groups[1],'key-match-rule-2'));
    assert.ok(find(groups[2],'module-toggle-samples'));
    assert.equal(allGroups.some(group=>group.id==='modules-advanced'),false);
    assert.equal(find(ui.document.getElementById('module-list'),'module-toggle-core'),undefined);
    assert.equal(find(ui.document.getElementById('module-list'),'module-toggle-decoder-sleep'),undefined);

  }
}

// Installed modules replace desktop defaults, including their dependencies.
ui=load();ui.state.firmware='1.19';
ui.state.modules=[{id:'core',selectable:false},{id:'keyshift',selectable:true},{id:'stems',selectable:true}];
ui.renderModules=()=>{};
ui.ask=async(name,firmware,selected,id,on)=>{
 assert.equal(name,'mod_selection');assert.equal(firmware,'1.19');assert.equal(on,true);
 return [...new Set([...selected,'core',id])];
};
ui.state.selected=['core','stems'];
await ui.selectDriveModules({mod:{installed:true,modules:['core','keyshift','future-module'],loaded:['stems']}});
assert.deepEqual([...ui.state.selected],['core','keyshift']);
await ui.selectDriveModules({mod:{installed:true,modules:['core','stems']}});
assert.deepEqual([...ui.state.selected],['core','stems']);
await ui.selectDriveModules({mod:{installed:true,unrecorded:true,modules:[],loaded:['keyshift']}});
assert.deepEqual([...ui.state.selected],['core','stems']);
await ui.selectDriveModules({mod:{installed:false,modules:[]}});
assert.deepEqual([...ui.state.selected],[]);
await ui.selectDriveModules({mod:{installed:true,modules:[]}});
assert.deepEqual([...ui.state.selected],[]);

console.log("Transposition UI and preview checks passed");
})().catch(error=>{console.error(error);process.exitCode=1;});
