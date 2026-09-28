// SPDX-License-Identifier: MPL-2.0
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.listeners={};this.dataset={};this.style={};}
 append(...nodes){this.children.push(...nodes)}
 setAttribute(key,value){this[key]=value}
 addEventListener(key,callback){this.listeners[key]=callback}
 closest(){return null}
 contains(target){return this===target || this.children.some(c=>c.contains(target))}
 getContext(){return {clearRect(){},fillRect(){},drawImage(){}}}
 getBoundingClientRect(){return {left:0,width:800}}
}
let context,stopped=0,calls=[],sources=[],gainNodes=[],workerCount=0;
class AudioContext {
 constructor(options){assert.equal(options.sampleRate,44100);assert.equal(options.latencyHint,"interactive");this.currentTime=100;this.state="running";context=this;}
 async resume(){}
 createBuffer(channels,frames,rate){assert.equal(rate,44100);const data=[new Float32Array(frames),new Float32Array(frames)];return {getChannelData:i=>data[i]};}
 createBufferSource(){const source={connect(){},disconnect(){},start(time,offset){this.time=time;this.offset=offset},stop(){stopped++}};sources.push(source);return source;}
 createGain(){const node={connect(){},disconnect(){},gain:{value:1,cancelScheduledValues(){},setValueAtTime(v){this.value=v},linearRampToValueAtTime(v){this.value=v}}};gainNodes.push(node);return node;}
}
class Worker {
 constructor(){workerCount++;this.alive=true;const owner=this;this.scope={postMessage(data){setImmediate(()=>{if(owner.alive&&owner.onmessage)owner.onmessage({data});});}};vm.runInNewContext(fs.readFileSync('app/ui/web/stems-wave-worker.js','utf8'),{self:this.scope,Float32Array});}
 postMessage(data){this.scope.onmessage({data});}
 terminate(){this.alive=false;}
}
const events={},pcm=Buffer.from(new Float32Array(44100*2).buffer).toString('base64');
let slowResolve, packedRelease, binaryRelease;
const window={AudioContext,i18n:{t:key=>key},addEventListener:(name,cb)=>events[name]=cb,
 rx3:{async ask(method,...args){calls.push([method,...args]);
  if(method==='stems_preview_open') {
   const result={token:args[1],frames:44100,channels:3,sampleRate:44100,available:7,peaks:[0.2,0.4]};
   if(args[1]==='packed') {result.frames=44100*30;result.waveforms=Object.fromEntries([1,2,3,4,5,6,7].map(m=>[m,Buffer.from([31,255,124,100,60,20]).toString('base64')]));}
   if(args[1].startsWith('single-')) {
    const style=args[1].slice(7),format={blue:'PWV3',rgb:'PWV5','3band':'PWV7'}[style],bytes={blue:[31],rgb:[255,124],'3band':[100,60,20]}[style];
    result.waveformFormat=format;result.waveforms=Object.fromEntries([1,2,3,4,5,6,7].map(m=>[m,Buffer.from(bytes).toString('base64')]));
   }
   if(args[1]==='binary') {
    result.frames=44100*8;result.chunkFrames=44100*2;result.binaryURL='http://127.0.0.1/token/';result.scales=[1.25,1];
    result.waveforms=Object.fromEntries([1,2,3,4,5,6,7].map(m=>[m,Buffer.from([31,255,124,100,60,20]).toString('base64')]));
   }
   if(args[1]==='slow')return new Promise(resolve=>slowResolve=()=>resolve(result));
   return result;
  }
  if(method==='stems_preview_chunk') {const frames=args[0]==='packed'?44100*30:44100;const block=frames===44100?pcm:Buffer.alloc(frames*8).toString('base64');const result={first:0,frames,pcm:[block,block,block]};if(args[0]==='packed')return new Promise(resolve=>packedRelease=()=>resolve(result));return result;}
  if(method==='stems_preview_close')return true;
  throw new Error(method);
 }}};
const sandbox={Worker,window,document:{createElement:tag=>new Element(tag),querySelector(){return null}},requestAnimationFrame(){return 1},cancelAnimationFrame(){},atob:value=>Buffer.from(value,'base64').toString('binary'),Uint8Array,Float32Array,Int16Array,DataView,AbortController,Map,
 fetch:async(url)=>{
  const first=Number(url.split('/').at(-1)),count=44100*2;
  if(first===44100*6)await new Promise(resolve=>binaryRelease=resolve);
  const data=new ArrayBuffer(8+count*16),header=new DataView(data);header.setUint32(0,first,true);header.setUint32(4,count,true);
  return {ok:true,arrayBuffer:async()=>data};
 }};
vm.runInNewContext(fs.readFileSync('app/ui/web/stems-audio.js','utf8'),sandbox);
vm.runInNewContext(fs.readFileSync('app/ui/web/stems-listen.js','utf8'),sandbox);
const tick=async()=>{for(let i=0;i<5;i++)await new Promise(resolve=>setImmediate(resolve));};
const find=(node,test)=>{for(const child of node.children||[]){if(test(child))return child;const deeper=find(child,test);if(deeper)return deeper;}return null;};
const track=id=>events.rx3stemtrack({detail:{track:id,drive:'/usb',files:{},origin:'drive'}});
(async()=>{
 const parent=new Element('parent');window.rx3listen.attach(parent);track('7');await tick();
 const play=find(parent,e=>e.tag==='button'&&e.className==='btn primary'),wave=find(parent,e=>e.tag==='canvas');
 assert.equal(play.disabled,false);assert.equal(wave['aria-valuemax'],'1');assert.equal(find(parent,e=>e.tag==='input'),null);
 play.listeners.click();assert.equal(sources.length,3,'Running context starts synchronously');await tick();
 assert.ok(sources.every(s=>s.time===100 && s.offset===0));
 const styles=find(parent,e=>e.tag==='select');assert.equal(styles.children.length,3);styles.value='rgb';styles.listeners.change();
 const count=calls.length;context.currentTime=100.25;
 find(parent,e=>e.dataset.bit==='4').listeners.click();
 assert.equal(stopped,0,'Stem toggle never stops transport');assert.equal(calls.length,count,'Stem toggle does not call Python');
 assert.equal(gainNodes.at(-1).gain.value,-1,'Disabled drums are subtracted from source');
 wave.listeners.click({clientX:600});await tick();
 assert.equal(calls.length,count,'Seeking uses resident PCM');assert.equal(sources.at(-1).offset,.75);
 context.currentTime=100.35;play.listeners.click();assert.equal(play['aria-label'],'stems.listenPlay');
 play.listeners.click();await tick();assert.ok(Math.abs(sources.at(-1).offset-.85)<1e-8,'Pause preserves playback position');
 assert.equal(play['aria-label'],'stems.listenPause');
 play.listeners.click();
 context.state='suspended';let resumed;context.resume=()=>new Promise(resolve=>resumed=resolve);
 const before=sources.length;play.listeners.click();play.listeners.click();resumed();await tick();
 assert.equal(sources.length,before,'Pause during resume cancels pending playback');
 context.state='running';
 track('slow');await tick();track('8');await tick();slowResolve();await tick();
 assert.equal(play.disabled,false,'Stale response cannot clear the newer preview');
 assert.ok(!calls.some(c=>c[0]==='stems_preview_chunk'&&c[1]==='slow'));
 assert.ok(calls.some(c=>c[0]==='stems_preview_close'&&c[1]==='slow'));
 const workersBefore=workerCount;track('packed');await tick();
 assert.equal(play.disabled,true,'Playback waits for resident PCM');
 const loadingVocal=find(parent,e=>e.dataset.bit==='2');
 assert.equal(loadingVocal.disabled,false,'Embedded waveform selections work before audio transfer finishes');
 loadingVocal.listeners.click();
 packedRelease();await tick();
 assert.equal(loadingVocal['aria-pressed'],'false','Loading completion preserves the waveform selection');
 assert.equal(workerCount,workersBefore,'Embedded waveforms bypass PCM analysis entirely');
 assert.equal(play.disabled,false);
 const beforeZoom=calls.length;
 wave.listeners.wheel({clientX:400,deltaY:-100000,deltaMode:0,preventDefault(){}});
 wave.listeners.click({clientX:0});play.listeners.click();
 assert.equal(sources.at(-1).offset,0,'Zoom keeps the current playback cursor visible');
 assert.equal(wave.dataset.viewSeconds,'10');
 context.currentTime+=10;events.rx3theme();
 assert.equal(wave.dataset.viewStart,'10','Right-edge crossing advances one full page');
 context.currentTime+=10;events.rx3theme();
 assert.equal(wave.dataset.viewStart,'20','Following page starts with the cursor at the left');
 play.listeners.click();
 wave.listeners.wheel({clientX:400,deltaY:100000,deltaMode:0,preventDefault(){}});
 wave.listeners.click({clientX:600});play.listeners.click();
 assert.equal(sources.at(-1).offset,22.5,'Maximum zoom-out restores the whole track');
 const vocal=find(parent,e=>e.dataset.bit==='2'),beforeGain=gainNodes.at(-2).gain.value;
 vocal.listeners.pointerdown({button:0,preventDefault(){}});
 assert.notEqual(gainNodes.at(-2).gain.value,beforeGain,'Gain changes on pointerdown, before mouse release');
 const changedGain=gainNodes.at(-2).gain.value;
 vocal.listeners.click({detail:1});assert.equal(gainNodes.at(-2).gain.value,changedGain,'Pointer click does not toggle twice');
 assert.equal(calls.length,beforeZoom,'Zoom, seek and toggles never request audio again');
 const space={code:'Space',target:wave,preventDefault(){this.prevented=true}};
 events.keydown(space);assert.equal(play['aria-label'],'stems.listenPlay');assert.equal(space.prevented,true);
 events.keydown({...space,repeat:true});assert.equal(play['aria-label'],'stems.listenPlay','Holding Space does not repeat');
 events.keydown(space);assert.equal(play['aria-label'],'stems.listenPause');
 events.keydown({...space,target:{isContentEditable:true}});assert.equal(play['aria-label'],'stems.listenPause','Typing does not control transport');
 for(const style of ['blue','rgb','3band']) {
  const count=workerCount;track('single-'+style);await tick();
  assert.equal(styles.value,style);assert.equal(play.disabled,false);assert.equal(workerCount,count);
  assert.equal(styles.children.filter(o=>o.disabled).length,2,'Only the prepared format is selectable');
 }
 track('binary');await tick();
 assert.equal(play.disabled,false,'First binary segment enables playback while last segment is blocked');
 assert.ok(!calls.some(c=>c[0]==='stems_preview_chunk'&&c[1]==='binary'),'No Base64 audio bridge calls');
 wave.listeners.click({clientX:100});assert.equal(wave['aria-valuenow'],'1','Paused seek updates cursor');
 play.listeners.click();assert.equal(play['aria-label'],'stems.listenPause');
 context.currentTime+=.25;play.listeners.click();assert.equal(wave['aria-valuenow'],'1.25');
 play.listeners.click();const beforeBinaryToggle=stopped;
 find(parent,e=>e.dataset.bit==='4').listeners.click();assert.equal(stopped,beforeBinaryToggle);
 assert.equal(gainNodes.at(-1).gain.value,-1,'Streaming toggles share persistent gains');
 play.listeners.click();binaryRelease();await tick();
 track('single-blue');await tick();
 assert.ok(calls.some(c=>c[0]==='stems_preview_close'&&c[1]==='binary'),'Changing track releases streaming session');
 console.log('Local stem gains, full-track seek, pause and stale response: OK');
})().catch(error=>{console.error(error);process.exitCode=1});
