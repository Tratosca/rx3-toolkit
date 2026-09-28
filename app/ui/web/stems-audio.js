// SPDX-License-Identifier: MPL-2.0
// Bounded binary transfers; all roles share one Web Audio scheduling clock.
(function () {
  function PreviewAudio(context, info, changed, failed) {
    this.context=context;this.info=info;this.changed=changed;this.failed=failed;
    this.cache=new Map();this.pending=new Map();this.abort=new AbortController();
    this.closed=false;this.playing=false;this.ended=false;this.groups=[];this.frame=0;this.cursor=0;
    this.base=0;this.startTime=0;this.revision=0;this.loaded=0;this.mask=info.available;
    this.gains=Array.from({length:info.channels},()=>{
      var gain=context.createGain();gain.connect(context.destination);return gain;
    });
    this.setMask(info.available);
    this.ready=this.fetchSegment(0).then(()=>{
      if(!this.closed) this.prefetch();
    });
  }
  PreviewAudio.prototype.setMask=function(mask) {
    this.mask=mask;var residual=mask&1 ? 1 : 0, now=this.context.currentTime;
    this.gains.forEach(function(gain,index){
      gain.gain.cancelScheduledValues(now);
      gain.gain.setValueAtTime(index ? ((mask&(1<<index)) ? 1 : 0)-residual : residual,now);
    });
  };
  PreviewAudio.prototype.fetchSegment=function(first) {
    if(this.cache.has(first)) return Promise.resolve(this.cache.get(first));
    if(this.pending.has(first)) return this.pending.get(first);
    var self=this,info=this.info;
    var request=fetch(info.binaryURL+first,{signal:this.abort.signal,cache:"no-store",credentials:"omit"}).then(function(response){
      if(!response.ok) throw new Error("Preview audio expired");
      return response.arrayBuffer();
    }).then(function(data){
      if(self.closed) throw new Error("Preview closed");
      var header=new DataView(data),count=header.getUint32(4,true);
      if(header.getUint32(0,true)!==first || count!==Math.min(info.chunkFrames,info.frames-first) || data.byteLength!==8+count*(8+(info.channels-1)*4)) throw new Error("Invalid preview PCM");
      var original=new Float32Array(data,8,count*2),buffers=[],offset=8;
      for(var role=0;role<info.channels;role++) {
        var buffer=self.context.createBuffer(2,count,info.sampleRate);
        var left=buffer.getChannelData(0),right=buffer.getChannelData(1);
        var values=role ? new Int16Array(data,offset,count*2) : original;
        var scale=role ? info.scales[role-1] : 1;
        for(var i=0;i<count;i++) {
          var silent=role && original[i*2]===0 && original[i*2+1]===0;
          // Match the player's float32 multiplication before PCM conversion.
          left[i]=silent ? 0 : role ? Math.fround(values[i*2]*scale)/32768 : values[i*2];
          right[i]=silent ? 0 : role ? Math.fround(values[i*2+1]*scale)/32768 : values[i*2+1];
        }
        buffers.push(buffer);offset+=count*(role ? 4 : 8);
      }
      self.cache.set(first,buffers);self.loaded+=count;
      self.changed();return buffers;
    }).finally(function(){self.pending.delete(first);});
    this.pending.set(first,request);return request;
  };
  PreviewAudio.prototype.prefetch=async function() {
    try {
      for(var first=0;first<this.info.frames && !this.closed;first+=this.info.chunkFrames) await this.fetchSegment(first);
    } catch(error) {this.fail(error);}
  };
  PreviewAudio.prototype.fail=function(error) {
    if(this.closed || this.error) return;
    this.error=error;this.pause();this.failed(error);
  };
  PreviewAudio.prototype.current=function() {
    return (this.playing ? Math.min(this.cursor,this.base+Math.max(0,this.context.currentTime-this.startTime)*this.info.sampleRate) : this.frame)/this.info.sampleRate;
  };
  PreviewAudio.prototype.pause=function() {
    this.frame=Math.round(this.current()*this.info.sampleRate);this.playing=false;this.revision++;
    this.groups.forEach(function(group){group.forEach(function(voice){voice.onended=null;voice.stop();voice.disconnect();});});
    this.groups=[];
  };
  PreviewAudio.prototype.seek=function(seconds) {
    this.pause();this.frame=Math.min(this.info.frames,Math.max(0,Math.round(seconds*this.info.sampleRate)));
  };
  PreviewAudio.prototype.play=function(seconds) {
    this.pause();this.frame=Math.min(this.info.frames,Math.max(0,Math.round(seconds*this.info.sampleRate)));
    if(this.frame===this.info.frames) this.frame=0;
    this.ended=false;this.base=this.cursor=this.frame;this.startTime=this.context.currentTime;
    this.playing=true;this.pump();
  };
  PreviewAudio.prototype.pump=function() {
    if(!this.playing || this.closed || this.error) return;
    var self=this,info=this.info,revision=this.revision;
    while(this.cursor<info.frames) {
      var when=this.startTime+(this.cursor-this.base)/info.sampleRate;
      if(when>this.context.currentTime+6) break;
      var first=Math.floor(this.cursor/info.chunkFrames)*info.chunkFrames;
      if(!this.cache.has(first)) {
        this.fetchSegment(first).then(function(){if(revision===self.revision)self.pump();}).catch(function(error){self.fail(error);});
        break;
      }
      if(when<this.context.currentTime) {
        when=this.context.currentTime;
        this.startTime=when-(this.cursor-this.base)/info.sampleRate;
      }
      var offset=(this.cursor-first)/info.sampleRate;
      var group=this.cache.get(first).map(function(buffer,index){
        var voice=self.context.createBufferSource();voice.buffer=buffer;
        voice.connect(self.gains[index]);return voice;
      });
      this.groups.push(group);
      (function(scheduled){
        scheduled[0].onended=function(){
          if(revision!==self.revision) return;
          scheduled.forEach(function(voice){voice.disconnect();});
          self.groups=self.groups.filter(function(item){return item!==scheduled;});
          if(self.cursor===info.frames && !self.groups.length) {
            self.frame=info.frames;self.playing=false;self.ended=true;self.changed();
          } else {self.pump();self.changed();}
        };
      })(group);
      group.forEach(function(voice){voice.start(when,offset);});
      this.cursor=Math.min(first+info.chunkFrames,info.frames);
    }
    this.changed();
  };
  PreviewAudio.prototype.close=function() {
    if(this.closed) return;
    this.pause();this.closed=true;this.abort.abort();this.cache.clear();
    this.gains.forEach(function(gain){gain.disconnect();});
  };
  window.RX3PreviewAudio=PreviewAudio;
})();
