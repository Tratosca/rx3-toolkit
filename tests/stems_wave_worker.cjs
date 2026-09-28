// SPDX-License-Identifier: MPL-2.0
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
function analyze(split){
 const messages=[],self={postMessage(data){messages.push(data);}};
 vm.runInNewContext(fs.readFileSync('app/ui/web/stems-wave-worker.js','utf8'),{self,Float32Array});
 const frames=4410,pcm=new Float32Array(frames*2);
 for(let i=0;i<frames;i++)pcm[i*2]=pcm[i*2+1]=.5*Math.sin(i*2*Math.PI*100/44100);
 self.onmessage({data:{type:'init',frames,rate:44100,channels:2}});
 for(let first=0;first<frames;first+=split){const piece=pcm.slice(first*2,Math.min(frames,first+split)*2);self.onmessage({data:{type:'chunk',pcm:[piece.buffer,piece.slice().buffer]}});}
 return messages.at(-1).waves;
}
const whole=analyze(4410),chunks=analyze(735);
assert.ok(whole[1].every(x=>x===0),'Identical vocals cancel the instrumental, including all frequency bands');
assert.ok(whole[2].some(x=>x>0));assert.deepEqual(whole[2],whole[3],'All stems reconstruct the source');
for(const mask of [1,2,3])assert.deepEqual(whole[mask],chunks[mask],'Chunk boundaries preserve filter state and timeline');
let low=0,high=0;for(let i=0;i<whole[2].length;i+=4){low+=whole[2][i+1];high+=whole[2][i+3];}
assert.ok(low>high*10,'Low tone belongs in the low-frequency band');
console.log('Waveforms: cancellation, selected mix, bands and chunk continuity OK');
