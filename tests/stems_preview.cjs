// SPDX-License-Identifier: MPL-2.0
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
class Element {
  constructor(tag){this.tag=tag;this.children=[];this.listeners={};this.dataset={};this.style={};this.value='0';}
  append(...nodes){this.children.push(...nodes)}
  setAttribute(key,value){this[key]=value}
  addEventListener(key,callback){this.listeners[key]=callback}
  getContext(){return {clearRect(){},fillRect(){}}}
  getBoundingClientRect(){return {left:0,width:800}}
}
let context, stopped=0, calls=[];
class AudioContext {
  constructor(options){assert.equal(options.sampleRate,44100);this.currentTime=100;context=this;}
  async resume(){}
  async decodeAudioData(){return {}}
  createBufferSource(){return {connect(){},disconnect(){},start(){},stop(){stopped++}}}
}
const events={};
const unity={gain:[1,1,1,1],start:[1,1,1,1],target:[1,1,1,1],cursor:256};
const window={AudioContext,i18n:{t:key=>key,number:value=>String(value)},
 addEventListener:(name,cb)=>{events[name]=cb},
 rx3:{async ask(method,...args){calls.push([method,...args]);return {audio:'AA==',available:15,totalSeconds:60,
  seconds:30,start:args[3],peaks:[0.2,0.4],initialState:unity,finalState:unity,ramp:[]}}}};
vm.runInNewContext(fs.readFileSync('app/ui/web/stems-listen.js','utf8'),{
 window,document:{createElement:tag=>new Element(tag)},requestAnimationFrame(){},
 atob:value=>Buffer.from(value,'base64').toString('binary'),Uint8Array,Map,Math,Number,JSON});
const tick=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 const parent=new Element('parent');window.rx3listen.attach(parent);
 events.rx3stemtrack({detail:{track:'7',drive:'/usb',files:{}}});await tick();
 const panel=parent.children[0];const play=panel.children.find(e=>e.tag==='button');
 await play.listeners.click();await tick();
 context.currentTime=102;
 const selections=panel.children.find(e=>e.children.some(c=>c.dataset.bit==='4'));
 selections.children.find(e=>e.dataset.bit==='4').listeners.click();await tick();
 assert.equal(stopped,1);
 const last=calls.at(-1);
 assert.equal(last[0],'stems_audition');assert.equal(last[3].mask,11);
 assert.equal(last[4],2);assert.equal(last[3].state.cursor,256);
 const seek=panel.children.find(e=>e.tag==='input');seek.value='41';seek.listeners.change();await tick();
 assert.equal(calls.at(-1)[4],41);
 events.rx3stemtrack({detail:{track:'8',drive:'/usb',files:{}}});await tick();
 assert.equal(calls.at(-1)[2],'8');assert.equal(calls.at(-1)[4],0);
})().catch(error=>{console.error(error);process.exitCode=1});
