// SPDX-License-Identifier: MPL-2.0
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
class Element {
 constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.events={};this.style={setProperty(){}};this.dataset={};}
 append(...items){this.children.push(...items)}replaceChildren(...items){this.children=items}setAttribute(){}setPointerCapture(){}
 addEventListener(name,fn){(this.events[name]||=[]).push(fn)}
 async send(name,event={}){for(const fn of this.events[name]||[])await fn({target:this,preventDefault(){},...event})}
}
const elements=new Map(),get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id)};
const document={getElementById:get,createElement:tag=>new Element(tag)};
const window=new Element();window.i18n={t:(key,p)=>key==='ui.bankDefault'?'Bank-'+p.count:key,number:String,bytes:String};
const storage=new Map(),localStorage={getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)};
const saved=new Map(),calls=[];let failed=false,done;
const clone=x=>JSON.parse(JSON.stringify(x));
window.rx3={confirm:async()=>true,watchJob:fn=>{done=fn},ask:async(op,...args)=>{
 calls.push([op,...clone(args)]);
 if(op==='samples_defaults')return {padCount:8,maxVoices:4,colours:Array(8).fill('#FFFFFF'),gainUnity:100,volumeDefault:50,maxSeconds:8,bankMaxBytes:16777216};
 if(op==='samples_draft_load')return {project:clone(saved.get(args[0])||null),banks:[],active:null};
 if(op==='samples_draft_store'){if(failed)return null;saved.set(args[0],clone(args[1]));return true;}
 if(op==='samples_push'){
  const p=clone(args[1]);for(const e of p.entries){e.value.onDrive=true;e.saved=clone(e.value)}p.deleted=[];p.savedActive=p.active;saved.set(args[0],p);return {started:true};
 }
 throw Error(op);
}};
vm.runInNewContext(fs.readFileSync('app/ui/web/samples.js','utf8'),{window,document,localStorage,Map,Number,Array,Uint8Array});
const tick=async()=>{for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r))};
(async()=>{
 await window.rx3samples.start();await window.send('rx3drive',{detail:{path:'/usb'}});await tick();
 get('bank-name').value='First';await get('bank-name').send('input');await tick();
 await get('bank-new').send('click');await tick();
 get('bank-name').value='Second';await get('bank-name').send('input');await tick();
 let p=saved.get('/usb');assert.equal(p.entries.length,2);assert.equal(p.entries[0].value.name,'First');
 await get('bank-activate').send('click');await tick();assert.equal(saved.get('/usb').active,p.entries[1].id);
 assert.ok(!calls.some(c=>['samples_push','samples_save','samples_activate','samples_remove'].includes(c[0])),'No USB writes while editing');
 get('bank-pick').value=p.entries[0].id;await get('bank-pick').send('change');await tick();assert.equal(get('bank-name').value,'First');
 assert.equal(get('samples-sync').textContent,'samples.localOnly');assert.equal(get('tag-samples').hidden,false);
 assert.equal(await window.rx3samples.beforeDrive(),true);
 await window.send('rx3drive',{detail:{path:'/other'}});await tick();
 await window.send('rx3drive',{detail:{path:'/usb'}});await tick();assert.equal(get('bank-name').value,'First','Local draft restored');
 await get('bank-save').send('click');assert.equal(calls.filter(c=>c[0]==='samples_push').length,1);
 assert.equal(get('samples-editor').inert,true);
 await done({state:'done'});await tick();assert.equal(get('samples-sync').textContent,'samples.synced');assert.equal(get('tag-samples').hidden,true);
 await get('bank-delete').send('click');await tick();assert.equal(saved.get('/usb').deleted[0],'First');
 assert.equal(calls.filter(c=>c[0]==='samples_push').length,1,'Deletion also waits for export');
 failed=true;get('bank-name').value='Unsent';await get('bank-name').send('input');await tick();
 assert.equal(get('samples-sync').textContent,'samples.localError');assert.equal(await window.rx3samples.beforeDrive(),false);
 assert.ok(storage.size,'Immediate browser recovery copy survives backend error');
 failed=false;await get('samples-local-retry').send('click');await tick();assert.equal(get('samples-sync').textContent,'samples.localOnly');
 await get('bank-save').send('click');await window.send('rx3jobfinished',{detail:{kind:'samples',state:'failed'}});assert.equal(get('samples-editor').inert,false);
 console.log('Samples local projects: multiple banks, deferred USB export, activation, restart, deletion and failed autosave OK');
})().catch(e=>{console.error(e);process.exitCode=1});
