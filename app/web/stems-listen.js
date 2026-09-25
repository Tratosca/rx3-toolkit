// SPDX-License-Identifier: MPL-2.0
// Audio reconstruction and ramp state arrive from Python. The browser only
// schedules the returned float WAV and carries its sample state across chunks.
(function () {
  var t = window.i18n.t;
  var track = "", drive = "", files = {}, origin = "drive";
  var position = 0, total = 0, mask = "original", available = 0;
  var context = null, voice = null, reply = null, started = 0, rampState = null;
  var generation = 0, loading = false, resumeIntent = false, cache = new Map(), root, canvas, buttons, status, play, seek;
  var modeButtons = [], labels = [[4,"stems.listenDrums"],[8,"stems.listenBass"],[1,"stems.listenRest"],[2,"stems.listenVocal"]];

  function node(tag, text) {
    var item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    return item;
  }

  function stop() {
    generation++;
    loading = false;
    if (voice && reply) {
      var frames = Math.min(Math.round(reply.seconds * 44100), Math.max(0, Math.floor((context.currentTime - started) * 44100)));
      position = reply.start + frames / 44100;
      rampState = reply.initialState;
      for (var entry of reply.ramp) if (entry[0] <= frames) rampState = entry[1];
      if (frames === Math.round(reply.seconds * 44100)) rampState = reply.finalState;
      voice.onended = null; voice.stop(); voice.disconnect(); voice = null;
    }
    draw();
  }

  function draw() {
    if (!root) return;
    var current = voice && reply ? reply.start + Math.min(reply.seconds, context.currentTime - started) : position;
    play.textContent = loading ? t("samples.hearLoading") : voice ? t("samples.hearStop") : t("samples.hearPlay");
    play.disabled = loading || !available;
    seek.max = String(total || 1); seek.value = String(current);
    status.textContent = !track ? t("stems.listenChoose") : loading ? t("samples.hearLoading") :
      !available ? t("stems.listenEmpty") : t("stems.listenPosition", {position:window.i18n.number(current,{maximumFractionDigits:2}),total:window.i18n.number(total,{maximumFractionDigits:2})});
    if (reply && reply.rejected && reply.rejected.length) status.textContent += " " + t("stems.listenReduced");
    for (var item of modeButtons) {
      item.button.textContent = t(item.key);
      item.button.setAttribute("aria-pressed", String(origin === item.origin));
      item.button.disabled = item.origin === "imported" && !files.vocals;
    }
    for (var button of buttons.children) {
      var bit = Number(button.dataset.bit);
      button.disabled = !available || (bit && !(available & bit));
      button.hidden = bit > 0 && !(available & bit);
      button.setAttribute("aria-pressed", String(bit ? !!((mask === "original" ? available : mask) & bit) : mask === "original"));
      button.textContent = t(bit === 1 && available === 3 ? "stems.listenInstrumental" : button.dataset.key);
    }
    var paint = canvas.getContext("2d");
    paint.clearRect(0,0,canvas.width,canvas.height);
    if (reply && reply.peaks && reply.peaks.length) {
      paint.fillStyle = "#6b9dd6";
      reply.peaks.forEach(function (peak,i) {
        var h = Math.min(1,peak) * (canvas.height - 4);
        paint.fillRect(i * canvas.width / reply.peaks.length, (canvas.height - h) / 2,
                       Math.max(1,canvas.width / reply.peaks.length), Math.max(1,h));
      });
      paint.fillStyle = "#e4ab61";
      var x = (current - reply.start) / reply.seconds * canvas.width;
      paint.fillRect(Math.max(0,Math.min(canvas.width-2,x)),0,2,canvas.height);
    }
    if (voice) requestAnimationFrame(draw);
  }

  async function load(playNow) {
    if (!track || (!drive && origin === "drive")) { draw(); return; }
    if (playNow) {
      context = context || new (window.AudioContext || window.webkitAudioContext)({sampleRate:44100});
      await context.resume();
    }
    var revision = ++generation;
    resumeIntent = playNow;
    loading = true; draw();
    var selection = {mask:mask, state:rampState};
    var args = [drive,track,selection,position,30];
    var method = origin === "imported" ? "stems_import_audition" : "stems_audition";
    var key = JSON.stringify([origin,args,files]);
    if (!cache.has(key)) {
      if (cache.size >= 4) cache.delete(cache.keys().next().value);
      cache.set(key,window.rx3.ask.apply(null,[method].concat(args)));
    }
    var answer = await cache.get(key);
    if (!answer) cache.delete(key);
    if (revision !== generation) return;
    loading = false;
    if (!answer) { draw(); return; }
    reply = answer; available = answer.available; total = answer.totalSeconds;
    if (playNow && answer.audio && answer.seconds > 0) {
      var bytes = Uint8Array.from(atob(answer.audio),function (c) { return c.charCodeAt(0); });
      var audio;
      try { audio = await context.decodeAudioData(bytes.buffer); }
      catch (error) { if (revision === generation) { status.textContent=t("stems.listenDecode"); } return; }
      if (revision !== generation) return;
      voice = context.createBufferSource(); voice.buffer = audio; voice.connect(context.destination);
      started = context.currentTime; voice.start();
      voice.onended = function () {
        voice.disconnect(); voice = null;
        position = answer.start + answer.seconds; rampState = answer.finalState;
        if (position + 1 / 44100 < total) load(true); else draw();
      };
    }
    draw();
  }

  function attach(parent) {
    root = node("section"); root.append(node("h2",t("stems.listenTitle")));
    var origins = node("div"); origins.className = "row";
    for (var item of [["drive","stems.listenDrive"],["imported","stems.listenImported"]]) {
      (function (which,key) {
        var button = node("button",t(key)); button.type = "button"; button.className = "btn small";
        button.addEventListener("click",function () { var playing=!!voice || (loading && resumeIntent); stop(); origin=which; rampState=null; load(playing); });
        origins.append(button); modeButtons.push({button:button,origin:which,key:key});
      })(item[0],item[1]);
    }
    root.append(origins);
    canvas = node("canvas"); canvas.width=800; canvas.height=120; canvas.style.width="100%";
    canvas.setAttribute("aria-label",t("stems.listenWave")); canvas.setAttribute("role","img");
    canvas.addEventListener("click",function (event) {
      if (!reply || !reply.seconds) return;
      var playing=!!voice || (loading && resumeIntent); stop();
      var bounds=canvas.getBoundingClientRect();
      position=reply.start + Math.max(0,Math.min(1,(event.clientX-bounds.left)/bounds.width))*reply.seconds;
      load(playing);
    });
    seek=node("input"); seek.type="range"; seek.min="0"; seek.step=String(1/44100);
    seek.setAttribute("aria-label",t("stems.listenSeek")); seek.style.width="100%";
    seek.addEventListener("change",function () { var value=Number(seek.value),playing=!!voice || (loading && resumeIntent); stop(); position=value; load(playing); });
    root.append(canvas,seek);
    buttons=node("div"); buttons.className="row";
    for (var item of [[0,"stems.listenOriginal"]].concat(labels)) {
      (function (bit,key) {
        var button=node("button",t(key)); button.type="button"; button.className="btn small";
        button.dataset.bit=String(bit); button.dataset.key=key;
        button.addEventListener("click",function () {
          var playing=!!voice || (loading && resumeIntent); stop();
          mask=bit ? (mask === "original" ? available : mask)^bit : "original";
          load(playing);
        });
        buttons.append(button);
      })(item[0],item[1]);
    }
    play=node("button"); play.type="button"; play.className="btn";
    play.addEventListener("click",function () { if (voice) stop(); else { if(position>=total) {position=0;rampState=null;} load(true); } });
    var refresh=node("button",t("common.refresh")); refresh.type="button"; refresh.className="btn small";
    refresh.addEventListener("click",function () { stop(); cache.clear(); rampState=null; mask="original"; load(false); });
    status=node("p"); status.setAttribute("aria-live","polite");
    root.append(buttons,play,refresh,status); parent.append(root); draw();
    window.addEventListener("rx3stemtrack",function (event) {
      stop(); track=event.detail.track; drive=event.detail.drive; files=event.detail.files || {};
      position=0; total=0; available=0; reply=null; mask="original"; rampState=null;
      if (!files.vocals) origin="drive";
      cache.clear(); load(false);
    });
    window.addEventListener("rx3language",draw);
  }
  window.rx3listen={attach:attach};
})();
