// SPDX-License-Identifier: MPL-2.0
// Decode once; transport and stem gains stay local to the audio clock.
(function () {
  var t = window.i18n.t;
  var root, canvas, buttons, status, play, context, waveStyle, worker;
  var waves={}, styleName="3band", wavePaint=null, paintKey="", wantingPlay=false, transportRevision=0, cancelAnalysis=null;
  var storedStyle=null;
  var packedWaves={}, zoom=1, viewStart=0, layers={}, layerView="";
  var buffers = [], voices = [], gains = [], streaming=null, streamInfo=null;
  function bytes(encoded) {
    var binary=atob(encoded), result=new Uint8Array(binary.length);
    for(var i=0;i<binary.length;i++)result[i]=binary.charCodeAt(i);
    return result;
  }
  function releaseStream() {
    if(streaming){streaming.close();streaming=null;}
    if(streamInfo){window.rx3.ask("stems_preview_close",streamInfo.token);streamInfo=null;}
  }
  function viewLength() {return total/zoom;}
  var available = 0, mask = 0, total = 0, position = 0, started = 0;
  var generation = 0, loading = false, percent = 0, animation = null, identity = "", failure = false;
  var labels = [[1,"stems.listenRest"],[2,"stems.listenVocal"],[4,"stems.listenDrums"]];
  function node(tag, text) {
    var item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    return item;
  }
  function clock(value) { var seconds=Math.max(0,Math.floor(value||0)); return Math.floor(seconds/60)+":"+String(seconds%60).padStart(2,"0"); }
  function current() { if(streaming) return streaming.current(); return voices.length ? Math.min(total,position+context.currentTime-started) : position; }
  function pause() {
    wantingPlay=false;transportRevision++;
    position=current();
    if(streaming) streaming.pause();
    voices.forEach(function (voice) { voice.onended=null;voice.stop();voice.disconnect(); });
    gains.forEach(function (gain) { gain.disconnect(); });
    voices=[];gains=[];
    if(animation!==null) { cancelAnimationFrame(animation);animation=null; }
    draw();
  }
  function applyGains() {
    if (!context) return;
    if(streaming) {streaming.setMask(mask);return;}
    var residual=mask&1 ? 1 : 0, now=context.currentTime;
    gains.forEach(function (gain,index) {
      var value=index ? ((mask & (1<<index)) ? 1 : 0)-residual : residual;
      gain.gain.cancelScheduledValues(now);
      gain.gain.setValueAtTime(value,now);
    });
  }
  function start() {
    if (loading || (!streaming && !buffers.length) || !available) return;
    wantingPlay=true;
    var revision=++transportRevision;
    function begin() {
      if(revision!==transportRevision || !wantingPlay || voices.length) return;
      if(position>=total) position=0;
      if(streaming) {streaming.play(position);draw();return;}
      started=context.currentTime;
      buffers.forEach(function (buffer) {
        var voice=context.createBufferSource(), gain=context.createGain();
        voice.buffer=buffer;voice.connect(gain);gain.connect(context.destination);
        voices.push(voice);gains.push(gain);
      });
      applyGains();
      voices[0].onended=function () { pause();position=total;draw(); };
      voices.forEach(function (voice) { voice.start(started,position); });
      draw();
    }
    // A running audio context needs no async hop on play or seek.
    if(context.state==='running') begin();
    else context.resume().then(begin).catch(function(){wantingPlay=false;failure=true;draw();});
    draw();
  }
  function seek(value) {
    if(loading || (!streaming && !buffers.length)) return;
    var playing=wantingPlay;pause();position=Math.max(0,Math.min(total,value));
    if(streaming)streaming.seek(position);
    if(playing) start();else draw();
  }
  function draw() {
    if(!root) return;
    var value=current(), playing=wantingPlay;
    var length=viewLength();
    if(total && (value<viewStart || (value>=viewStart+length && value<total))) {
      // Page at the right edge; the final page may end with empty space.
      viewStart=value<viewStart ? Math.floor(value/length)*length : viewStart+Math.floor((value-viewStart)/length)*length;
    }
    canvas.dataset.viewStart=String(viewStart);
    canvas.dataset.viewSeconds=String(length);
    play.disabled=loading || !available;
    if(waveStyle) Array.from(waveStyle.children).forEach(function(option){option.disabled=!!storedStyle && option.value!==storedStyle;});
    play.setAttribute("aria-label",t(playing ? "stems.listenPause" : "stems.listenPlay"));
    play.title=t(playing ? "stems.listenPause" : "stems.listenPlay");
    play.innerHTML='<svg aria-hidden="true" viewBox="0 0 16 16" width="18" height="18" fill="currentColor">'+(playing ? '<path d="M3 2h4v12H3zm6 0h4v12H9z"/>' : '<path d="M4 2v12l10-6Z"/>')+'</svg>';
    status.textContent=loading ? t("stems.previewLoading",{percent:percent}) : failure ? t("stems.listenDecode") : !available ? t("stems.listenEmpty") : t("stems.listenPosition",{position:clock(value),total:clock(total)});
    canvas.setAttribute("aria-label",t("stems.listenSeek"));
    canvas.setAttribute("aria-valuemax",String(total));canvas.setAttribute("aria-valuenow",String(value));
    canvas.setAttribute("aria-valuetext",clock(value)+" / "+clock(total));
    canvas.setAttribute("aria-disabled",String(loading || !available));
    for(var button of buttons.children) {
      var bit=Number(button.dataset.bit);
      button.disabled=!available || (loading && !packedWaves[available]);
      button.hidden=bit>0 && !(available&bit);
      button.setAttribute("aria-pressed",String(bit ? !!(mask&bit) : mask===available));
      button.textContent=t(bit===1 && available===3 ? "stems.listenInstrumental" : button.dataset.key);
    }
    var paint=canvas.getContext("2d"), style=typeof getComputedStyle==="function" ? getComputedStyle(canvas) : null;
    function colour(key) { return style ? style.getPropertyValue(key).trim() : "currentColor"; }
    var viewKey=styleName+":"+colour("--surface")+":"+identity+":"+zoom+":"+viewStart;
    if(viewKey!==layerView) {layers={};layerView=viewKey;}
    var key=mask+":"+viewKey;
    if(layers[mask]) {wavePaint=layers[mask];paintKey=key;}
    if(!wavePaint || paintKey!==key) {
      wavePaint=document.createElement("canvas");wavePaint.width=canvas.width;wavePaint.height=canvas.height;
      var layer=wavePaint.getContext("2d"), packed=packedWaves[mask], data=waves[mask] || [];
      var columns=packed ? packed.length/6 : data.length/4;
      function bar(x,width,height,ink) {
        if(height<=0)return;
        layer.fillStyle=ink;layer.fillRect(x,(canvas.height-height)/2,width,height);
      }
      // Aggregate into visible pixels: a whole-track view retains brief peaks.
      var first=total ? viewStart/total*columns : 0, span=columns/zoom;
      for(var x=0;x<canvas.width && columns;x++) {
        var from=Math.floor(first+x*span/canvas.width),to=Math.min(columns,Math.max(from+1,Math.ceil(first+(x+1)*span/canvas.width)));
        var amp=0,lo=0,mi=0,hi=0,rgb=0,shade=0;
        for(var i=from;i<to;i++) {
          if(packed) {
            var at=i*6, word=packed[at+1]*256+packed[at+2];
            var level=styleName==='blue' ? (packed[at]&31)/31 : ((word>>2)&31)/31;
            if(level>=amp) {amp=level;rgb=word;shade=packed[at]>>5;}
            lo=Math.max(lo,packed[at+3]/128);mi=Math.max(mi,packed[at+4]/128);hi=Math.max(hi,packed[at+5]/128);
          } else {
            amp=Math.max(amp,data[i*4]);lo=Math.max(lo,data[i*4+1]);mi=Math.max(mi,data[i*4+2]);hi=Math.max(hi,data[i*4+3]);
          }
        }
        var height=Math.min(1,amp)*(canvas.height-4),peak=Math.max(lo,mi,hi,.00001);
        if(styleName==='3band') {
          if(packed) {
            // PWV7 bands overlap; sort the layers without adding envelopes.
            [[lo,"#1688eb"],[mi,"#eac45d"],[hi,"#f4f7ff"]].sort(function(a,b){return b[0]-a[0];}).forEach(function(b){bar(x,1,Math.min(1,b[0])*(canvas.height-4),b[1]);});
          } else {
            var sum=lo+mi+hi;bar(x,1,height,"#1688eb");
            bar(x,1,sum?height*(mi+hi)/sum:0,"#eac45d");bar(x,1,sum?height*hi/sum:0,"#f4f7ff");
          }
        } else if(styleName==='rgb') bar(x,1,height,"rgb("+(packed ? [((rgb>>13)&7)*255/7,((rgb>>10)&7)*255/7,((rgb>>7)&7)*255/7] : [lo,mi,hi].map(function(v){return 255*v/peak;})).map(Math.round).join(",")+")");
        else bar(x,1,height,"rgb(40,"+Math.round(packed ? 100+140*shade/7 : 100+140*(mi+hi)/(lo+mi+hi||1))+",255)");
      }
      layers[mask]=wavePaint;paintKey=key;
    }
    paint.clearRect(0,0,canvas.width,canvas.height);paint.drawImage(wavePaint,0,0);
    if(total && value>=viewStart && value<=viewStart+viewLength()) { paint.fillStyle=colour("--warning");paint.fillRect(Math.min(canvas.width-2,(value-viewStart)/viewLength()*canvas.width),0,2,canvas.height); }
    if(playing && animation===null) animation=requestAnimationFrame(function () {animation=null;draw();});
  }
  async function load(detail) {
    var next=JSON.stringify([detail.track,detail.drive]);
    if(next===identity && !detail.refresh) return;
    identity=next;var revision=++generation;
    pause();
    releaseStream();
    if(cancelAnalysis){cancelAnalysis();cancelAnalysis=null;}if(worker){worker.terminate();worker=null;}waves={};packedWaves={};storedStyle=null;layers={};zoom=1;viewStart=0;wavePaint=null;buffers=[];available=0;position=0;total=0;failure=false;loading=false;
    if(!detail.track || !detail.drive) {draw();return;}
    loading=true;percent=0;draw();
    var info=null;
    try {
      info=await window.rx3.ask("stems_preview_open",detail.drive,detail.track,false);
      if(revision!==generation || !info || !info.available) return;
      context=context || new (window.AudioContext || window.webkitAudioContext)({sampleRate:44100,latencyHint:"interactive"});
      total=info.frames/info.sampleRate;available=info.available;mask=available;
      if(info.waveforms) {
        storedStyle={PWV3:"blue",PWV5:"rgb",PWV7:"3band"}[info.waveformFormat] || null;
        if(storedStyle){styleName=storedStyle;waveStyle.value=styleName;}
        Object.keys(info.waveforms).forEach(function(key){
          var data=bytes(info.waveforms[key]);
          if(storedStyle) {
            var stride={blue:1,rgb:2,"3band":3}[storedStyle], expanded=new Uint8Array(data.length/stride*6);
            var offset={blue:0,rgb:1,"3band":3}[storedStyle];
            for(var i=0;i<data.length/stride;i++)for(var j=0;j<stride;j++)expanded[i*6+offset+j]=data[i*stride+j];
            data=expanded;
          }
          packedWaves[key]=data;
        });
        mask=info.available;layers={};wavePaint=null;draw();
      }
      if(info.binaryURL) {
        streamInfo=info;
        var audio=new window.RX3PreviewAudio(context,info,function(){
          if(revision!==generation)return;
          percent=Math.round(audio.loaded/info.frames*100);
          if(wantingPlay && audio.ended){wantingPlay=false;position=audio.current();}
          draw();
        },function(){if(revision===generation){failure=true;available=0;wantingPlay=false;releaseStream();draw();}});
        streaming=audio;audio.setMask(mask);
        await audio.ready;
        if(revision!==generation)return;
        loading=false;draw();return;
      }
      var analysisWorker=null;
      if(!info.waveforms) {
        analysisWorker=new Worker("stems-wave-worker.js");worker=analysisWorker;
        analysisWorker.postMessage({type:"init",frames:info.frames,rate:info.sampleRate,channels:info.channels});
      }
      function analyze(pcm) {
        return new Promise(function(resolve,reject) {
          cancelAnalysis=function(){reject(new Error("superseded"));};
          analysisWorker.onmessage=function(event){cancelAnalysis=null;resolve(event.data);};
          analysisWorker.onerror=function(){reject(new Error("waveform analysis"));};
          analysisWorker.postMessage({type:"chunk",pcm:pcm},pcm);
        });
      }
      var loaded=[];
      for(var i=0;i<info.channels;i++) loaded.push(context.createBuffer(2,info.frames,info.sampleRate));
      for(var first=0;first<info.frames;) {
        var chunk=await window.rx3.ask("stems_preview_chunk",info.token,first);
        if(revision!==generation) return;
        if(!chunk) throw new Error("preview expired");
        if(chunk.first!==first || chunk.frames<=0 || first+chunk.frames>info.frames || chunk.pcm.length!==loaded.length) throw new Error("preview chunk");
        var analysisPCM=[];
        chunk.pcm.forEach(function (encoded,index) {
          var values=new Float32Array(bytes(encoded).buffer);
          if(values.length!==chunk.frames*2) throw new Error("preview length");
          var left=loaded[index].getChannelData(0),right=loaded[index].getChannelData(1);
          for(var j=0;j<chunk.frames;j++) {left[first+j]=values[j*2];right[first+j]=values[j*2+1];}
          analysisPCM.push(values.buffer);
        });
        if(analysisWorker) {
          var analyzed=await analyze(analysisPCM);
          if(revision!==generation)return;
          if(analyzed.type==="complete") {waves=analyzed.waves;layers={};wavePaint=null;}
        }
        first+=chunk.frames;percent=Math.round(first/info.frames*100);draw();
      }
      if(revision!==generation) return;
      buffers=loaded;
    } catch(error) {
      if(revision===generation) {failure=true;available=0;buffers=[];releaseStream();}
    } finally {
      if(analysisWorker) {analysisWorker.terminate();if(worker===analysisWorker){worker=null;cancelAnalysis=null;}}
      if(info && info.token && streamInfo!==info) window.rx3.ask("stems_preview_close",info.token);
      if(revision===generation) {loading=false;draw();}
    }
  }
  function attach(parent) {
    root=parent;
    var title=node("h2",t("stems.listenTitle"));title.dataset.t="stems.listenTitle";root.append(title);
    var panel=node("div");panel.className="listen";
    canvas=node("canvas");canvas.width=1600;canvas.height=192;canvas.tabIndex=0;
    canvas.setAttribute("role","slider");canvas.setAttribute("aria-valuemin","0");
    canvas.addEventListener("click",function (event) {var bounds=canvas.getBoundingClientRect();seek(viewStart+(event.clientX-bounds.left)/bounds.width*viewLength());});
    canvas.addEventListener("wheel",function(event) {
      if(!total)return;
      event.preventDefault();
      var bounds=canvas.getBoundingClientRect(),fraction=Math.max(0,Math.min(1,(event.clientX-bounds.left)/bounds.width));
      var anchor=viewStart+fraction*viewLength();
      // User-defined RX3 range: whole track through a ten-second window.
      var maximum=Math.max(1,total/10);
      zoom=Math.max(1,Math.min(maximum,zoom*Math.pow(2,-event.deltaY*(event.deltaMode===1?16:1)/400)));
      viewStart=Math.max(0,Math.min(total-viewLength(),anchor-fraction*viewLength()));
      // Zoom cannot leave the playback cursor outside the visible page.
      var cursor=current();
      if(cursor<viewStart || cursor>=viewStart+viewLength())viewStart=cursor===total ? Math.max(0,total-viewLength()) : Math.floor(cursor/viewLength())*viewLength();
      draw();
    },{passive:false});
    canvas.addEventListener("keydown",function (event) {
      var values={ArrowLeft:current()-5,ArrowRight:current()+5,Home:0,End:total};
      if(event.key in values) {event.preventDefault();seek(values[event.key]);}
    });
    var wave=node("div");wave.className="wave";wave.append(canvas);
    buttons=node("div");buttons.className="stem-controls";
    [[0,"stems.listenOriginal"]].concat(labels).forEach(function (item) {
      var button=node("button",t(item[1]));button.type="button";button.className="btn small";button.dataset.bit=String(item[0]);button.dataset.key=item[1];
      function toggle() {if(button.disabled)return;mask=item[0] ? mask^item[0] : available;applyGains();draw();}
      button.addEventListener("pointerdown",function(event){if(event.button===0){event.preventDefault();toggle();}});
      button.addEventListener("click",function(event){if(!event || !event.detail)toggle();});buttons.append(button);
    });
    play=node("button");play.type="button";play.className="btn primary";
    function togglePlay() {if(play.disabled)return;if(wantingPlay)pause();else start();}
    play.addEventListener("pointerdown",function(event){if(event.button===0){event.preventDefault();togglePlay();}});
    play.addEventListener("click",function(event){if(!event || !event.detail)togglePlay();});
    status=node("p");status.className="status";status.setAttribute("role","status");
    var transport=node("div");transport.className="transport";transport.append(play,status);
    var appearance=node("div");appearance.className="row";
    var appearanceLabel=node("label",t("stems.waveStyle"));appearanceLabel.htmlFor="stems-wave-style";appearanceLabel.dataset.t="stems.waveStyle";
    waveStyle=node("select");waveStyle.id="stems-wave-style";
    [["3band","3Band"],["blue","Blue"],["rgb","RGB"]].forEach(function(item){var option=node("option",item[1]);option.value=item[0];waveStyle.append(option);});
    try {styleName=localStorage.getItem("rx3-stems-wave-style") || "3band";}catch(error){}
    if(!["3band","blue","rgb"].includes(styleName))styleName="3band";
    waveStyle.value=styleName;
    waveStyle.addEventListener("change",function(){styleName=waveStyle.value;try{localStorage.setItem("rx3-stems-wave-style",styleName);}catch(error){}draw();});
    appearance.append(appearanceLabel,waveStyle);
    panel.append(appearance,wave,buttons,transport);root.append(panel);draw();
    window.addEventListener("keydown",function(event) {
      if(event.code!=="Space" && event.key!==" ")return;
      if(event.altKey || event.ctrlKey || event.metaKey || event.shiftKey)return;
      if(root.closest("[hidden]") || document.querySelector("dialog[open]"))return;
      var target=event.target;
      if(target && (target.isContentEditable || target.closest("input,textarea,select,[contenteditable=true]")))return;
      // Space retains its native action on unrelated buttons and controls.
      if(target && target.closest("button,summary,a,[role=button]") && !root.contains(target))return;
      event.preventDefault();
      if(!event.repeat)togglePlay();
    });
    window.addEventListener("beforeunload",releaseStream);
    window.addEventListener("rx3stemtrack",function (event) {load(event.detail);});
    window.addEventListener("rx3language",draw);window.addEventListener("rx3theme",draw);
  }
  window.rx3listen={attach:attach};
})();
