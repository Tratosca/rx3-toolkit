// SPDX-License-Identifier: MPL-2.0
// RX3 previews for artwork, sample pads and harmonic matching.
(function () {
  var t = window.i18n.t;
  var logo = null;
  var theme = "dark";
  var pads = [];
  var chosen = 0;
  var playing = [];

  function logoBounds(width, height) {
    var factor = Math.min(1, 864 / width, 386 / height);
    return {x: 640 - width * factor / 2, y: 284 - height * factor / 2,
            scale: factor};
  }

  function render(canvas, sampler) {
    var scale = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = 1280 * scale;
    canvas.height = 800 * scale;
    var p = canvas.getContext("2d");
    p.setTransform(scale, 0, 0, scale, 0, 0);
    var light = theme === "light";
    var style = getComputedStyle(canvas);
    function token(name) { return style.getPropertyValue("--mock-" + (light ? "light-" : "dark-") + name).trim(); }
    var bg = token("bg"), panel = token("panel"), inset = token("inset");
    var fg = token("fg"), muted = token("muted"), blue = token("blue");
    function box(x, y, w, h, fill, radius) {
      var r = Math.min(radius || 16, w / 2, h / 2);
      p.fillStyle = fill; p.beginPath();
      p.moveTo(x + r, y); p.arcTo(x+w, y, x+w, y+h, r);
      p.arcTo(x+w, y+h, x, y+h, r); p.arcTo(x, y+h, x, y, r);
      p.arcTo(x, y, x+w, y, r); p.closePath(); p.fill();
    }
    function text(value, x, y, size, color, align) {
      p.font = style.getPropertyValue("--weight-medium").trim() + " " + size + "px " + style.getPropertyValue("--font-ui").trim();
      p.fillStyle = color || fg; p.textAlign = align || "left";
      p.fillText(value, x, y);
    }
    function bar(x, y, w, color) { box(x, y, w, 7, color, 3); }
    box(0, 0, 1280, 800, bg, 32);
    box(20, 20, 1240, 45, panel, 14);
    text(t("mock.remain"), 38, 50, 20, muted);
    bar(292, 39, 550, inset);
    text(t("mock.product"), 1240, 50, 20, muted, "right");
    [0, 1].forEach(function (deck) {
      var y = 88 + deck * 213;
      box(20, y, 168, 194, panel);
      text(t("mock.deck", {number: deck + 1}), 38, y + 34, 20, blue);
      bar(38, y+62, 111, inset); bar(38, y+83, 83, inset);
      text(t("mock.tempo"), 38, y + 135, 24, muted);
      text(t("mock.emptyTime"), 38, y + 167, 20, muted);
    });
    box(1090, 88, 170, 322, panel);
    text(t("mock.fx"), 1175, 125, 20, muted, "center");
    box(1106, 146, 138, 62, inset, 12);
    text(t("mock.echo"), 1175, 184, 25, fg, "center");
    text(t("mock.select"), 1175, 245, 17, muted, "center");
    text(t("mock.channels"), 1175, 285, 27, fg, "center");
    text(t("mock.beat"), 1175, 369, 21, muted, "center");
    box(1090, 428, 170, 67, panel);
    text(t("mock.panels"), 1175, 470, 20, fg, "center");
    if (logo) {
      // Preserve the canvas dimensions and transparent margins in the export.
      var ratio = window.devicePixelRatio || 1;
      var width = logo.width / ratio, height = logo.height / ratio;
      var bounds = logoBounds(width, height);
      p.drawImage(logo, bounds.x, bounds.y, width * bounds.scale, height * bounds.scale);
    } else {
      text(t("mock.logo"), 638, 293, 60, muted, "center");
    }
    [0, 1].forEach(function (deck) {
      var origin = 20 + deck * 640;
      text(sampler ? t("mock.samples") : t("mock.cues"), origin + 300, 531, 19, muted, "center");
      for (var i = 0; i < 8; i++) {
        var pad = pads[i];
        var x = origin + (i % 4) * 155, y = 548 + Math.floor(i / 4) * 49;
        var colour = sampler && pad ? pad.colour : blue;
        box(x, y, 145, 39, panel, 11);
        if (sampler && playing.indexOf(i) >= 0) {
          box(x, y, 145, 39, colour, 11);
          box(x+4, y+4, 137, 31, inset, 8);
        } else if (sampler && chosen === i) {
          bar(x+14, y+30, 117, colour);
        }
        text(sampler ? String(i+1) : String.fromCharCode(65+i), x+72, y+25, 18, fg, "center");
      }
      box(origin, 652, 600, 126, panel);
      text(t("mock.deck", {number: deck + 1}), origin + 20, 683, 18, blue);
      text(t("mock.time"), origin + 20, 737, 40, fg);
      text(t("mock.tempo"), origin + 575, 730, 27, muted, "right");
      bar(origin + 20, 755, 555, inset);
    });
  }
  var matchIcons = {};
  function matchIcon(colour) {
    if (!matchIcons[colour]) matchIcons[colour] = new Promise(function (resolve) {
      var image = new Image();
      image.onload = function () { resolve(image); };
      image.onerror = function () { resolve(null); };
      image.src = "key-match-" + colour + ".svg";
    });
    return matchIcons[colour];
  }

  function stopBrowser(canvas) {
    if (canvas.browserFrame) cancelAnimationFrame(canvas.browserFrame);
    canvas.browserFrame = null;
    canvas.renderGeneration = (canvas.renderGeneration || 0) + 1;
  }

  async function renderBrowser(canvas, data) {
    stopBrowser(canvas);
    var generation = (canvas.renderGeneration || 0) + 1;
    canvas.renderGeneration = generation;
    var icons = await Promise.all(["green", "yellow", "orange", "red"].map(matchIcon));
    if (canvas.renderGeneration !== generation) return;
    var ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = 1280 * ratio; canvas.height = 800 * ratio;
    var p = canvas.getContext("2d"), style = getComputedStyle(canvas);
    p.setTransform(ratio, 0, 0, ratio, 0, 0);
    function token(name) { return style.getPropertyValue(name).trim(); }
    var bg=token("--mock-dark-bg"), panel=token("--mock-dark-panel"), inset=token("--mock-dark-inset");
    var fg=token("--mock-dark-fg"), muted=token("--mock-dark-muted"), blue=token("--mock-dark-blue");
    var selected=token("--mock-selection"), gold=token("--mock-wave-gold");
    function box(x,y,w,h,colour,radius) {
      var r=Math.min(radius || 0,w/2,h/2);
      p.fillStyle=colour;p.beginPath();p.moveTo(x+r,y);
      p.arcTo(x+w,y,x+w,y+h,r);p.arcTo(x+w,y+h,x,y+h,r);
      p.arcTo(x,y+h,x,y,r);p.arcTo(x,y,x+w,y,r);p.closePath();p.fill();
    }
    function text(value,x,y,size,colour,align,max) {
      p.font=token("--weight-medium")+" "+size+"px "+token("--font-ui");
      p.fillStyle=colour || fg;p.textAlign=align || "left";
      if(max) {
        while(value.length && p.measureText(value).width>max) value=value.slice(0,-2)+"…";
      }
      p.fillText(value,x,y);
    }
    function line(x,y,xx,yy,colour,width) {
      p.strokeStyle=colour;p.lineWidth=width || 2;p.beginPath();p.moveTo(x,y);p.lineTo(xx,yy);p.stroke();
    }
    function waveform(x,y,w,h,seed) {
      // Sparse breaks and uneven transients make the overview legible at 640 px.
      [blue,gold,fg].forEach(function (colour,band) {
        p.fillStyle=colour;
        for(var n=0;n<w;n+=2) {
          var position=n/w;
          var breakLevel=(position>.32&&position<.4)||(position>.72&&position<.75) ? .09 : 1;
          var beat=Math.pow(Math.abs(Math.sin(n*.54+seed)),6);
          var level=(.12+.34*Math.abs(Math.sin(n*.047+seed*2))+.5*beat)*breakLevel;
          var height=Math.max(1,h*level*[1,.65,.28][band]);
          p.fillRect(x+n,y+h-height,2,height);
        }
      });
      line(x,y+h,x+w,y+h,blue,1);
    }
    function bankIcon(x,y,colour) {
      p.strokeStyle=colour;p.lineWidth=2;
      p.strokeRect(x+6,y,24,22);p.strokeRect(x,y+6,24,22);
      line(x+12,y+13,x+12,y+25,colour,2);
      p.beginPath();p.arc(x+9,y+25,3,0,Math.PI*2);p.stroke();
    }
    box(0,0,1280,800,bg,32);
    box(16,16,1248,40,panel,10);
    box(28,27,12,17,fg,2);box(31,22,6,5,fg,1);
    text("USB 1",50,44,20);box(126,32,164,7,muted,3);
    text("00:49:03",1094,42,16,muted,"right");text("INFO",1242,43,18,fg,"right");
    box(16,66,82,622,inset,12);
    ["PLAYLIST","BANK 1","BANK 2","BANK 3","BANK 4"].forEach(function (name,index) {
      var y=70+index*76;
      if(index===1)box(20,y,74,70,selected,8);
      bankIcon(41,y+10,index===1?fg:blue);
      text(name,57,y+58,14,index<3?fg:muted,"center");
    });
    line(45,635,70,635,muted,2);p.strokeStyle=muted;p.strokeRect(49,639,17,23);
    line(54,632,62,632,muted,2);text("DELETE",57,680,13,muted,"center");

    box(108,66,1156,38,panel,8);
    text("PREVIEW",120,92,17,muted);text("#",371,92,17,muted);
    text("TRACK",422,92,17,muted);text("ARTIST",794,92,17,muted);text("KEY",1228,92,17,muted,"right");
    data.rows.forEach(function (entry,index) {
      var y=108+index*48, active=index===data.selected;
      box(108,y,1156,46,active?selected:index%2?panel:inset,5);
      waveform(120,y+6,194,32,index+1);
      // Album blocks use the same restrained geometric language as the Logo mock.
      box(326,y+6,34,34,panel,4);box(330,y+10,26,12,index%2?blue:muted,2);
      line(333,y+29,352,y+29,fg,2);
      text(String(index+1).padStart(3,"0"),370,y+31,21,active?fg:muted);
      p.globalAlpha=active?.75:.42;
      box(422,y+20,150+(index*47)%176,7,fg,3);
      box(794,y+20,active?100:76+(index*29)%70,7,fg,3);
      p.globalAlpha=1;
      if(active) {
        ["LOAD 1","LOAD 2"].forEach(function (label,i) {
          box(912+i*81,y+10,74,28,fg,3);text(label,949+i*81,y+30,16,bg,"center");
        });
      }
      if(entry.colour) {
        var icon=icons[["green","yellow","orange","red"].indexOf(entry.colour)];
        if(icon)p.drawImage(icon,1150,y+9,28,26);
      }
      text(entry.key,1245,y+31,23,fg,"right");
    });
    [0,1].forEach(function (deck) {
      var x=16+deck*632,y=704;
      box(x,y,616,80,panel,12);
      text("DECK "+(deck+1),x+12,y+20,15,deck?muted:gold);
      text("REMAIN",x+12,y+38,11,muted);
      text(deck?"1:07":"4:20",x+12,y+64,26);
      waveform(x+103,y+12,388,40,deck+4);
      for(var i=0;i<17;i++)line(x+103+i*24,y+57,x+103+i*24,y+62,muted,1);
      line(x+202,y+10,x+202,y+54,fg,2);
      box(x+103,y+70,deck?116:152,5,muted,2);
      box(x+506,y+7,100,65,deck?inset:gold,6);
      text(deck?"KEY":"MASTER",x+556,y+24,13,deck?muted:bg,"center");
      text(deck?data.source:data.master,x+556,y+59,36,deck?fg:bg,"center");
    });
    var base=document.createElement("canvas");
    base.width=canvas.width;base.height=canvas.height;
    base.getContext("2d").drawImage(canvas,0,0);
    var sequence=[{colour:"yellow",label:"keyMatch.boostTwo"},{colour:"orange",label:"keyMatch.boostSeven"},{colour:"red",label:"keyMatch.four"}];
    var start=null,lastPaint=-Infinity,lastStep=-1;
    var reduced=window.matchMedia("(prefers-reduced-motion: reduce)");
    function animate(now) {
      if(canvas.renderGeneration!==generation || !canvas.isConnected || canvas.closest("[hidden]")) {
        canvas.browserFrame=null;return;
      }
      if(start===null)start=now;
      var elapsed=now-start,step=Math.floor(elapsed/3000)%sequence.length;
      var phase=(elapsed%3000)/3000;
      if((!reduced.matches && now-lastPaint>=32) || step!==lastStep) {
        lastPaint=now;lastStep=step;
        p.drawImage(base,0,0,1280,800);
        var rule=sequence[step],index=data.rows.findIndex(function (entry) {return entry.colour===rule.colour;});
        if(index>=0) {
          var y=131+index*48,colour=token("--mock-match-"+rule.colour);
          var points=[[572,711],[572,694],[1104,694],[1104,y],[1136,y]];
          var lengths=[],total=0;
          for(var i=1;i<points.length;i++) {
            var length=Math.hypot(points[i][0]-points[i-1][0],points[i][1]-points[i-1][1]);
            lengths.push(length);total+=length;
          }
          var progress=reduced.matches?1:Math.min(1,phase/.28);
          progress=1-Math.pow(1-progress,3);
          var left=total*progress,tip=points[0],angle=-Math.PI/2;
          p.beginPath();p.moveTo(tip[0],tip[1]);
          for(var j=0;j<lengths.length && left>0;j++) {
            var fraction=Math.min(1,left/lengths[j]);
            var from=points[j],to=points[j+1];
            tip=[from[0]+(to[0]-from[0])*fraction,from[1]+(to[1]-from[1])*fraction];
            angle=Math.atan2(to[1]-from[1],to[0]-from[0]);
            p.lineTo(tip[0],tip[1]);left-=lengths[j];
          }
          p.lineCap="round";p.lineJoin="round";
          p.globalAlpha=reduced.matches?1:Math.min(1,(1-phase)/.1);
          p.strokeStyle=bg;p.lineWidth=12;p.stroke();
          p.strokeStyle=colour;p.lineWidth=7;p.stroke();
          if(progress>.02) {
            p.beginPath();p.moveTo(tip[0],tip[1]);
            p.lineTo(tip[0]-18*Math.cos(angle-.5),tip[1]-18*Math.sin(angle-.5));
            p.lineTo(tip[0]-18*Math.cos(angle+.5),tip[1]-18*Math.sin(angle+.5));
            p.closePath();p.fillStyle=colour;p.fill();
          }
          box(794,y-18,288,36,inset,8);
          text(t(rule.label),938,y+7,21,colour,"center");
          p.strokeStyle=colour;p.lineWidth=3;p.strokeRect(1145,y-19,112,40);
          p.globalAlpha=1;p.lineCap="butt";p.lineJoin="miter";
          canvas.dataset.transition=rule.colour;
        }
      }
      canvas.browserFrame=requestAnimationFrame(animate);
    }
    canvas.browserFrame=requestAnimationFrame(animate);

  }

  function stopPadAccess(canvas) {
    if(canvas.accessFrame)cancelAnimationFrame(canvas.accessFrame);
    canvas.accessFrame=null;
  }
  var GUIDE_STEP_MS=5000;
  function guideElapsed(canvas,now,start,reduced) {
    var elapsed=canvas.dataset.manualStep !== undefined ?
      (canvas.dataset.manualTime !== undefined ? Number(canvas.dataset.manualTime) : Number(canvas.dataset.manualStep)*GUIDE_STEP_MS+3300) :
      reduced ? 0 : Number(canvas.dataset.startTime || Number(canvas.dataset.startStep || 0)*GUIDE_STEP_MS)+now-start;
    canvas.dataset.elapsed=String(elapsed);
    return elapsed;
  }
  function renderPadAccess(canvas,kind) {
    if(canvas.dataset.view==="touch")return renderTouchAccess(canvas,kind);
    stopPadAccess(canvas);
    var stems=kind==="stems", reduced=window.matchMedia("(prefers-reduced-motion: reduce)").matches && canvas.dataset.autoplay !== "true";
    var scale=Math.min(window.devicePixelRatio || 1,2);
    canvas.width=960*scale;canvas.height=390*scale;
    var p=canvas.getContext("2d"),style=getComputedStyle(canvas);
    p.setTransform(scale,0,0,scale,0,0);
    function token(name) {return style.getPropertyValue("--mock-dark-"+name).trim();}
    var bg=token("bg"),panel=token("panel"),fg=token("fg"),muted=token("muted"),blue=token("blue");
    var colours=["#ff0000","#00ff00","#0000ff"];
    function box(x,y,w,h,color) {p.fillStyle=color;p.beginPath();p.roundRect(x,y,w,h,12);p.fill();}
    function text(value,x,y,size,color) {
      p.font="500 "+size+"px "+style.getPropertyValue("--font-ui").trim();
      p.fillStyle=color;p.textAlign="center";p.fillText(value,x,y);
    }
    var started=performance.now(),last=-1;
    function frame(now) {
      if(!canvas.isConnected || canvas.closest("[hidden]") || !canvas.closest("details").open) {stopPadAccess(canvas);return;}
      var step=Math.floor(guideElapsed(canvas,now,started,reduced)/GUIDE_STEP_MS)%5;
      if(step!==last) {
        last=step;canvas.dataset.step=String(step);
        if(canvas.updateGuideCaption)canvas.updateGuideCaption(step);
        box(0,0,960,390,bg);
        var native=step===0 || step===4,prepared=stems && !native;
        var slip=native?"#224aa0":"#78c8ff";
        box(75,144,250,78,panel);
        p.strokeStyle=slip;p.lineWidth=4;p.strokeRect(82,151,236,64);
        text(stems?(step===4?"HOT CUE":"SLIP LOOP"):"SAMPLES",200,194,28,slip);
        text(t(stems?"stemAccess.pads":"sampleAccess.touch"),200,302,26,fg);
        p.beginPath();p.moveTo(350,185);p.lineTo(432,185);p.lineTo(418,173);p.moveTo(432,185);p.lineTo(418,197);
        p.strokeStyle=slip;p.lineWidth=5;p.lineJoin="round";p.stroke();
        box(466,28,466,334,panel);
        text(native?"HOT CUE":stems?"SLIP LOOP":"SAMPLES",699,80,29,fg);
        var loops=["1/16","1/8","1/4","1/2","1","2","1/3","3/4"];
                for(var i=0;i<8;i++) {
          var x=487+(i%4)*109,y=110+Math.floor(i/4)*113;
          var stemPad=prepared && i>=4 && i<=6;
          var off=stemPad && (step===2 && i===5);
          var playing=!stems && (step===2 || step===3) && i===0;
          var colour=stemPad?colours[i-4]:slip;
          box(x,y,97,95,bg);
          p.strokeStyle=off?muted:colour;p.lineWidth=off?2:4;
          p.strokeRect(x+5,y+5,87,85);
          if(playing||(stemPad&&!off))box(x+10,y+10,77,75,colour);
          var label=stemPad?["INST","VOCAL","DRUMS"][i-4]:native?String.fromCharCode(65+i):stems?loops[i]:String(i+1);
          text(label,x+48,y+47,stemPad?17:27,off?muted:stemPad?(i===4||i===6?fg:bg):playing?bg:fg);
          text(stemPad?String(i+1):"",x+48,y+71,15,stemPad&&!off?(i===4||i===6?fg:bg):muted);
        }

      }
      if(!reduced && canvas.dataset.manualStep === undefined)canvas.accessFrame=requestAnimationFrame(frame);
    }
    frame(started);
  }

  function renderTouchAccess(canvas,kind) {
    stopPadAccess(canvas);
    var key=kind==="keyshift"||kind==="key-sync",sync=kind==="key-sync";
    var stems=kind==="stems",reduced=window.matchMedia("(prefers-reduced-motion: reduce)").matches && canvas.dataset.autoplay !== "true";
    var keyTab=canvas.dataset.keyTab==="1" || canvas.dataset.keyTab===undefined&&key;
    var stemsTab=canvas.dataset.stemsTab==="1" || canvas.dataset.stemsTab===undefined&&stems;
    var samplesTab=canvas.dataset.samplesTab==="1" || canvas.dataset.samplesTab===undefined&&kind==="samples";
    var ratio=Math.min(window.devicePixelRatio||1,2),style=getComputedStyle(canvas),height=stems||key?800:1120;
    canvas.width=1280*ratio;canvas.height=height*ratio;
    var p=canvas.getContext("2d");p.setTransform(ratio,0,0,ratio,0,0);
    function token(name) {return style.getPropertyValue("--mock-dark-"+name).trim();}
    var bg=token("bg"),panel=token("panel"),inset=token("inset"),fg=token("fg"),muted=token("muted"),blue="#78c8ff";
    function box(x,y,w,h,c) {p.fillStyle=c;p.fillRect(x,y,w,h);}
    function text(value,x,y,size,c,align) {
      p.font="500 "+size+"px "+style.getPropertyValue("--font-ui").trim();p.textAlign=align||"center";p.fillStyle=c||fg;p.fillText(value,x,y);
    }
    function finger(x,y,held) {
      p.beginPath();p.arc(x,y,held?20:15,0,Math.PI*2);p.strokeStyle=fg;p.lineWidth=4;p.stroke();
      p.beginPath();p.arc(x,y,5,0,Math.PI*2);p.fillStyle=fg;p.fill();
    }
    function wave(x,y,w,h,stemOnly) {
      for(var i=0;i<w;i+=5) {
        var amplitude=(.18+.82*Math.abs(Math.sin(i*.053)*Math.cos(i*.021)))*h;
        box(x+i,y-amplitude,3,amplitude*2,stemOnly?"#ff0000":"#1688eb");if(!stemOnly)box(x+i,y-amplitude*.55,3,amplitude*1.1,"#eac45d");
      }
    }
    var start=performance.now(),last=-100;
    function frame(now) {
      if(!canvas.isConnected||canvas.closest("[hidden]")||!canvas.closest("details").open) {stopPadAccess(canvas);return;}
      if(now-last>=33||reduced) {
        last=now;
        var elapsed=guideElapsed(canvas,now,start,reduced);
        var step=Math.floor(elapsed/GUIDE_STEP_MS)%5,phase=elapsed%GUIDE_STEP_MS/GUIDE_STEP_MS;
        var drag=Math.min(1,Math.max(0,(phase-.2)/.6));drag=1-Math.pow(1-drag,3);
        canvas.dataset.step=String(step);
        if(canvas.updateGuideCaption)canvas.updateGuideCaption(step);
        var opened=step>0 && step<4;
        box(0,0,1280,height,bg);
        box(10,9,172,32,panel);text("REMAIN",86,32,17,muted);box(198,22,432,5,inset);text("INFO",1224,32,21,muted);
        for(var deck=0;deck<2;deck++) {
          var y=57+deck*222;
          box(10,y,172,204,panel);text("DECK "+(deck+1),32,y+25,18,muted,"left");
          text("USB1",32,y+68,24,fg,"left");box(30,y+98,102,5,inset);box(30,y+129,77,5,inset);
          if(deck===0)wave(410,154,664,73,stems&&step===2);
        }
        box(409,48,2,442,fg);
        box(1090,57,180,295,panel);text("BEAT FX",1180,79,18,muted);
        box(1100,98,160,40,bg);text("ECHO",1180,126,26);
        text("CH SELECT",1180,158,15,muted);box(1100,168,160,35,bg);text("2",1180,194,24);
        text("120.0",1180,251,34);text("500 msec",1180,284,24);text("1 BEAT",1180,317,22,muted);
        box(1090,363,180,50,panel);
        if(keyTab||stemsTab) {
          if(keyTab) {
            if(key&&opened)box(1093,366,84,44,muted);
            text("KEY",1135,395,21,key&&opened?bg:muted);
          }
          if(stemsTab) {
            if(stems&&opened)box(1181,366,87,44,muted);
            text("STEMS",1225,395,21,stems&&opened?bg:fg);
          }
        } else {
          text("ZOOM",1135,395,19,blue);
          text("GRID",1225,395,19,muted);
        }
        box(1090,432,180,50,panel);
        if(samplesTab&& !stems&&!key&&opened)box(1093,435,84,44,muted);
        text(samplesTab?"SAMPLES":"STATUS",1137,462,18,samplesTab&& !stems&&!key&&opened?bg:fg);
        text("BEAT FX",1224,462,20,muted);
        box(10,495,1260,79,panel);
        if(key&&opened) {
          // rx3_pad_layout.h: deck origin 19, span 595, stride 640;
          // keyshift_row weights [2, 1] => 384 + 19 gap + 192 px.
          // Stepper ends are capped at 96 px, with 6 px inner gaps.
          var data=canvas.keyPreview||{source:"2A",master:"8A",shift:0,target:null};
          var applied=sync&&step>=2?data.shift:!sync&&step===2?1:0;
          var palette=[0xb7fc,0x8ffa,0xc7f8,0xa7f3,0xd7d4,0xb7ae,0xe734,0xd68e,0xf635,0xf50f,0xfd77,0xfbf1,0xf579,0xf3f6,0xe57d,0xd3fb,0xd57f,0xb3ff,0xc61f,0x9d3f,0xb73f,0x8edf,0xafff,0x7fff];
          function colour(index) {
            var c=palette[(index+24)%24];
            return "rgb("+Math.round((c>>11)*255/31)+","+Math.round(((c>>5)&63)*255/63)+","+Math.round((c&31)*255/31)+")";
          }
          for(var deck=0;deck<2;deck++) {
            var x=19+deck*640,y=521,shift=deck?applied:0;
            var source=deck?(sync?2:14):14,index=(source+14*shift+240)%24;
            var width=sync?384:595,centre=width-204;
            var parts=[[x,96,"-1"],[x+102,centre,String(Math.floor(index/2)+1)+"AB"[index%2]+(shift?" ("+(shift>0?"+":"")+shift+")":"")],[x+width-96,96,"+1"]];
            parts.forEach(function (part,i) {
              box(part[0],y,part[1],39,i===1?colour(index):inset);
              p.strokeStyle=muted;p.lineWidth=1;p.strokeRect(part[0],y,part[1],39);
              if(i!==1)box(part[0]+7,y+35,part[1]-14,3,colour(index+(i===0?-14:14)));
              text(part[2],part[0]+part[1]/2,y+26,23,i===1?bg:fg);
            });
            if(sync) {
              var actionable=deck===1&&step===1&&data.shift;
              var label=deck===0?"MASTER":actionable?"KEY SYNC "+(data.shift>0?"+":"")+data.shift:applied?(canvas.dataset.syncMode==="harmonic"?"KEY MATCH":"IDENTIQUE"):t("keySyncAccess.unavailable");
              if(actionable){p.strokeStyle=colour((source+14*data.shift+240)%24);p.lineWidth=2;p.strokeRect(x+403,y,192,39);}
              text(label,x+499,y+26,21,fg);
            }
          }
          if(step===2&&phase<.2&&(!sync||data.shift))finger(sync?1158:1206,548,false);
          if(step===3&&phase<.2&&!sync)finger(956,548,false);
        } else if(stems&&opened) {
          // Same per-deck role order as stems_display_order in the module.
          var labels=["INST","VOCAL","DRUMS"],colours=["#ff0000","#00ff00","#0000ff"];
          for(var deck=0;deck<2;deck++)for(var i=0;i<3;i++) {
            var x=19+deck*640+i*205,y=517,w=185,off=deck===0&&i===1&&step===2;
            var adjusting=deck===0&&i===1&&step===3,ink=i===0||i===2?fg:bg;
            var level=adjusting?Math.round(100-31*drag):100;
            box(x,y,w,39,off?inset:colours[i]);
            p.strokeStyle="#41474d";p.lineWidth=1;p.strokeRect(x,y,w,39);
            if(adjusting) {
              text("VOCAL",x+7,y+18,16,ink,"left");text(level+"%",x+w-7,y+18,16,ink,"right");
              box(x+8,y+30,w-16,6,"#30363c");box(x+8,y+30,(w-16)*level/100,6,bg);
              box(x+8+(w-16)*level/100-3,y+28,6,10,bg);
              finger(x+8+(w-16)*level/100,540,true);
            } else text(labels[i],x+w/2,y+26,23,off?fg:ink);
          }
          if(step===2)finger(316,540,false);
        } else if(!stems&&opened) {
          var value=step===3?Math.round(50+25*drag):50;
          box(20,517,1098,39,"#0088ee");box(28,533,1082,6,"#30363c");
          box(28,533,1082*value/100,6,fg);box(28+1082*value/100-3,530,6,12,fg);
          box(1137,517,123,39,inset);text("VOL "+value,1198,543,23,fg);
          if(step===3)finger(28+1082*value/100,540,true);

        } else {
          for(var deck=0;deck<2;deck++)for(var i=0;i<8;i++) {
            var x=10+deck*640+(i%4)*157,y=518+Math.floor(i/4)*30;box(x,y,148,20,panel);text(String.fromCharCode(65+i),x+74,y+16,15,muted);
          }
        }
        for(var deck=0;deck<2;deck++) {
          var dx=10+deck*640;
          box(dx,581,620,209,panel);text("DECK "+(deck+1),dx+48,608,18,muted);box(dx+110,601,340,6,inset);
          text("REMAIN",dx+194,652,16,muted);text(deck?"1:07":"4:20",dx+196,706,48);
          text("BPM",dx+560,652,17,muted);text(deck?"--":"128.0",dx+560,701,34);if(deck===0)wave(dx+100,747,508,25,stems&&step===2);
        }
        if(stems&&(step===0||step===4))finger(1224,388,false);
        if(key&&(step===0||step===4))finger(1135,388,false);
        if(!stems&&!key&&(step===0||step===4))finger(1137,462,false);
        if(!stems&&!key) {
          box(10,808,1260,302,panel);
          text(t("sampleAccess.physicalPads"),32,840,23,fg,"left");
          text(opened?"SAMPLES":"HOT CUE",1248,840,23,blue,"right");
          for(var i=0;i<8;i++) {
            var x=32+(i%4)*310,y=859+Math.floor(i/4)*120;
            var triggered=opened&&step===2&&i===0;
            box(x,y,286,104,inset);
            p.strokeStyle=triggered?fg:opened?blue:muted;p.lineWidth=triggered?5:2;p.strokeRect(x,y,286,104);
            box(x+8,y+8,270,7,opened?blue:muted);
            text(String(i+1),x+18,y+42,18,muted,"left");
            text(opened?t("sampleAccess.sample",{number:i+1}):String.fromCharCode(65+i),x+143,y+71,27,triggered?blue:fg);
            if(triggered)finger(x+235,y+66,false);
          }
        }
      }
      if(!reduced && canvas.dataset.manualStep === undefined)canvas.accessFrame=requestAnimationFrame(frame);
    }
    frame(start);
  }

  function draw() {
    document.querySelectorAll("canvas.rx3-mock").forEach(function (canvas) {
      render(canvas, canvas.dataset.preview === "samples");
    });
  }
  window.rx3mock = {
    renderPadAccess: renderPadAccess,
    stopPadAccess: stopPadAccess,
    renderBrowser: renderBrowser,
    stopBrowser: stopBrowser,
    logoBounds: logoBounds,
    setLogo: function (image, mode) { logo = image; theme = mode; draw(); },
    setPads: function (values, selected, active) {
      pads = values; chosen = selected; playing = active; draw();
    }
  };
  window.addEventListener("rx3language", draw);
  window.addEventListener("rx3theme", draw);
  draw();
})();
