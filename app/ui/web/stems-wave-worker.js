// SPDX-License-Identifier: MPL-2.0
// Bounded overview analysis, off the UI/audio thread. Each mask is analyzed
// from signed PCM/bands: envelopes are never added to guess a mixed waveform.
(function () {
  function filter(frequency, high, rate) {
    var w=2*Math.PI*frequency/rate,c=Math.cos(w),a=Math.sin(w)/Math.sqrt(2),d=1+a;
    var b0=(high?1+c:1-c)/2/d,b1=(high?-(1+c):1-c)/d,a1=-2*c/d,a2=(1-a)/d;
    var x1=0,x2=0,y1=0,y2=0;
    return function(x) {var y=b0*x+b1*x1+b0*x2-a1*y1-a2*y2;x2=x1;x1=x;y2=y1;y1=y;return y;};
  }
  var states, waves, frames, rate, count, received;
  self.onmessage=function(event) {
    var data=event.data;
    if(data.type==='init') {
      frames=data.frames;rate=data.rate;count=Math.min(Math.ceil(frames/rate*150),frames);received=0;waves={};
      for(var mask=1;mask<(1<<data.channels);mask++) waves[mask]=new Float32Array(count*4);
      states=Array.from({length:data.channels},function(){return [filter(300,false,rate),filter(250,true,rate),filter(1200,false,rate),filter(3000,true,rate),filter(9000,false,rate)];});
      return;
    }
    if(data.type!=='chunk')return;
    var pcm=data.pcm.map(function(b){return new Float32Array(b);}),n=pcm[0].length/2;
    var bands=states.map(function(){return [0,0,0];});
    for(var i=0;i<n;i++) {
      var at=Math.min(count-1,Math.floor((received+i)*count/frames))*4;
      for(var ch=0;ch<pcm.length;ch++) {
        var left=pcm[ch][i*2],right=pcm[ch][i*2+1];
        var mono=Math.abs(Math.abs(left)-Math.abs(right))<.001 ? (Math.abs(left)>Math.abs(right)?left:right):(left+right)/2;
        var f=states[ch];bands[ch][0]=f[0](mono);bands[ch][1]=f[2](f[1](mono));bands[ch][2]=f[4](f[3](mono));
      }
      for(var m=1;m<(1<<pcm.length);m++) {
        var residual=m&1?1:0,l=residual*pcm[0][i*2],r=residual*pcm[0][i*2+1];
        var low=residual*bands[0][0],mid=residual*bands[0][1],high=residual*bands[0][2];
        for(var ch=1;ch<pcm.length;ch++) {
          var gain=((m&(1<<ch))?1:0)-residual;
          l+=gain*pcm[ch][i*2];r+=gain*pcm[ch][i*2+1];
          low+=gain*bands[ch][0];mid+=gain*bands[ch][1];high+=gain*bands[ch][2];
        }
        var wave=waves[m];wave[at]=Math.max(wave[at],Math.abs(l),Math.abs(r));
        wave[at+1]=Math.max(wave[at+1],Math.abs(low));wave[at+2]=Math.max(wave[at+2],Math.abs(mid));wave[at+3]=Math.max(wave[at+3],Math.abs(high));
      }
    }
    received+=n;
    if(received===frames)self.postMessage({type:'complete',waves:waves},Object.values(waves).map(function(a){return a.buffer;}));
    else self.postMessage({type:'ready'});
  };
})();
