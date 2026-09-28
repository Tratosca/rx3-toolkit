// SPDX-License-Identifier: MPL-2.0
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const tick=async()=>{for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));};
const requests=[],nodes=[],gains=[];let blocked=true,release;
function packet(first){
 const data=new ArrayBuffer(8+4*16),view=new DataView(data);
 view.setUint32(0,first,true);view.setUint32(4,4,true);
 new Float32Array(data,8,8).set([.5,-.5,0,0,.4,-.2,.1,.2]);
 new Int16Array(data,40,8).fill(16384);new Int16Array(data,56,8).fill(8192);return data;
}
const context={currentTime:10,createGain(){const g={connect(){},disconnect(){},gain:{cancelScheduledValues(){},setValueAtTime(v){this.value=v;}}};gains.push(g);return g;},
 createBuffer(c,n,rate){const data=[new Float32Array(n),new Float32Array(n)];return{getChannelData:i=>data[i]};},
 createBufferSource(){const n={connect(g){this.gain=g;},disconnect(){},stop(){this.stopped=true;},start(time,offset){this.time=time;this.offset=offset;}};nodes.push(n);return n;}};
const window={};
vm.runInNewContext(fs.readFileSync('app/ui/web/stems-audio.js','utf8'),{window,AbortController,Map,Float32Array,Int16Array,DataView,fetch:async(url,options)=>{
 const first=Number(url.split('/').at(-1));requests.push(first);
 if(first===4 && blocked)await new Promise((resolve,reject)=>{release=resolve;options.signal.addEventListener('abort',()=>reject(new Error('aborted')));});
 return {ok:true,arrayBuffer:async()=>packet(first)};
}});
(async()=>{
 let errors=[];const info={binaryURL:'http://127.0.0.1/token/',frames:16,chunkFrames:4,channels:3,sampleRate:2,scales:[1.25,1],available:7};
 const audio=new window.RX3PreviewAudio(context,info,()=>{},e=>errors.push(e));
 await audio.ready;assert.equal(audio.loaded,4,'Ready after first segment while the next is blocked');
 assert.equal(audio.cache.get(0)[1].getChannelData(0)[0],.625,'Stored gain restored');
 assert.equal(audio.cache.get(0)[1].getChannelData(0)[1],0,'Source silence gates roles');
 audio.play(0);assert.equal(nodes.length,3);assert.ok(nodes.every(n=>n.time===10 && n.offset===0));
 audio.setMask(3);assert.equal(gains[2].gain.value,-1);assert.ok(nodes.every(n=>!n.stopped));
 context.currentTime=10.5;audio.pause();assert.equal(audio.current(),.5);
 audio.seek(5);audio.play(5);await tick();
 assert.ok(requests.includes(8),'Unloaded seek requested ahead of blocked sequential transfer');
 assert.equal(nodes[3].offset,1);assert.equal(audio.current(),5);
 blocked=false;release();await tick();assert.equal(audio.loaded,16);
 audio.pause();audio.play(0);
 const scheduled=nodes.slice(-12);assert.deepEqual(scheduled.map(n=>n.time),[10.5,10.5,10.5,12.5,12.5,12.5,14.5,14.5,14.5,16.5,16.5,16.5]);
 audio.close();assert.equal(audio.cache.size,0);assert.equal(errors.length,0);
 // Late transfers cannot revive a closed session.
 blocked=true;const second=new window.RX3PreviewAudio(context,info,()=>{},e=>errors.push(e));
 await second.ready;await tick();second.close();await tick();assert.equal(errors.length,0);
 console.log('Binary preview: early start, synchronized scheduling, gains, prioritized seek, pause and cancellation OK');
})().catch(e=>{console.error(e);process.exitCode=1;});
