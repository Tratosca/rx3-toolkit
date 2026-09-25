// SPDX-License-Identifier: MPL-2.0
// Exercise the actual UI event handlers with a controllable audio/bridge clock.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor(tag = 'div') { this.tagName = tag.toUpperCase(); this.children = []; this.events = {}; this.style = {setProperty(){}}; this.hidden = false; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
  setAttribute() {}
  setPointerCapture() {}
  addEventListener(name, callback) { (this.events[name] ||= []).push(callback); }
  async send(name, event = {}) { for (const fn of this.events[name] || []) await fn({target:this, preventDefault(){}, ...event}); }
}
const elements = new Map();
const document = {createElement: tag => new Element(tag), getElementById(id) {
  if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id);
}};
const window = new Element();
window.confirm = () => true;
window.i18n = {t: key => key, number: String, bytes: String};
const played = [], gains = [], failures = [];
let decoded = null;
class AudioContext {
  destination = {};
  async resume() {}
  async decodeAudioData() {
    if (decoded) await decoded;
    const pcm = new Float32Array(128).fill(1);
    return {sampleRate:44100, length:128, numberOfChannels:1, getChannelData:() => pcm};
  }
  createBufferSource() { return {
    paused:true, connect(){}, disconnect(){},
    start(){this.paused=false; played.push(this);}, stop(){this.paused=true;}
  }; }
  createGain() { const gain = {gain:{value:1}, connect(){}, disconnect(){}}; gains.push(gain); return gain; }
}
window.atob = text => Buffer.from(text, 'base64').toString('binary');
window.AudioContext = AudioContext;
let deferred = null;
const pads = Array.from({length:8}, (_, i) => ({present:true, path:`/bank/${i+1}.wav`, seconds:1, colour:'#FFFFFF', name:`Pad ${i+1}`, mode:i % 4, gain:i === 0 ? 0 : 150}));
window.rx3 = {
  fail: message => { failures.push(message); },
  async ask(operation) {
    if (operation === 'samples_defaults') return {padCount:8, maxVoices:4, colours:Array(8).fill('#FFFFFF'), gainUnity:100, volumeDefault:50, maxSeconds:8, bankMaxBytes:16777216};
    if (operation === 'samples_read') return {active:'live', banks:[{name:'live', pads, volume:50, shiftSilence:true, settingsOk:true}]};
    if (operation === 'samples_audition') return deferred ? await deferred : {audio:'AA=='};
    throw Error(operation);
  }
};
vm.runInNewContext(fs.readFileSync('app/ui/web/samples.js', 'utf8'), {window, document, Map, Number, Array, Uint8Array});
const flush = () => new Promise(resolve => setImmediate(resolve));
const key = (key, type = 'keydown') => window.send(type, {key, target:new Element(), repeat:false});
(async () => {
  await window.rx3samples.start();
  await window.send('rx3drive', {detail:{path:'/bank'}}); await flush();
  const toggle = document.getElementById('samples-simulate'); toggle.checked = true;
  await toggle.send('change');
  await key('1'); await flush();
  assert.equal(played.length, 1, 'a saved pad can be heard');
  assert.equal(gains.at(-1).gain.value, 0, 'zero pad gain remains silent');
  await key('3'); await flush();
  assert.equal(played.length, 2);
  assert.equal(played[0].paused, false, 'a second pad does not stop the first');
  assert.equal(played[1].loop, true);
  assert.equal(played[1].buffer.getChannelData(0)[0], 1/32);
  assert.equal(played[1].buffer.getChannelData(0)[127], 1/32);
  assert.equal(played[1].buffer.getChannelData(0)[31], 1);
  assert.equal(played[0].buffer.getChannelData(0)[0], 1, 'one-shots stay unchanged');
  assert.equal(gains.at(-1).gain.value, 0.1875, 'pad trim and squared bank gain match the runtime');
  await key('3'); assert.equal(played[1].paused, true, 'second press stops loop');
  await key('4'); await flush(); assert.equal(played.at(-1).loop, false);
  await key('4'); assert.equal(played.at(-1).paused, true, 'latch stops without looping');
  let resolve;
  deferred = new Promise(done => { resolve = done; });
  const before = played.length;
  await key('2'); await flush(); await key('2', 'keyup');
  resolve({audio:'AA=='}); await flush();
  assert.equal(played.length, before, 'release during conversion cancels held playback');
  deferred = null;
  await key('2'); await flush(); assert.equal(played.at(-1).paused, false);
  await key('2', 'keyup'); assert.equal(played.at(-1).paused, true);
  await key('Escape'); assert.ok(played.every(audio => audio.paused));
  const beforeDecode = played.length;
  decoded = new Promise(done => { resolve = done; });
  await key('2'); await flush(); await key('2', 'keyup');
  resolve(); await flush(); decoded = null;
  assert.equal(played.length, beforeDecode, 'release during decoding cancels held playback');
  await key('3'); await flush(); await key('Shift');
  assert.ok(played.every(audio => audio.paused), 'SHIFT alone silences every voice');
  // Pending conversion reserves the shared four-voice budget across modes.
  deferred = new Promise(done => { resolve = done; });
  const cappedBefore = played.length;
  for (const n of ['5', '6', '7', '8']) await key(n);
  await key('1'); await flush();
  assert.deepEqual(failures, ['samples.voiceLimit']);
  resolve({audio:'AA=='}); await flush(); deferred = null;
  assert.equal(played.length, cappedBefore + 4);
  await key('5'); await flush(); // one-shot retrigger at the ceiling
  assert.equal(played.length, cappedBefore + 5);
  await key('7'); // stop loop, freeing one slot
  await key('1'); await flush();
  assert.equal(played.length, cappedBefore + 6);
  assert.equal(failures.length, 1);
  await key('Escape');
  console.log('sample preview: saved pads, polyphony, modes, gain and delayed release passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
