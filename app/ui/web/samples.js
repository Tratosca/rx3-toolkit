// SPDX-License-Identifier: MPL-2.0
//
// The pad editor autosaves local projects; only an explicit export writes USB.
// Every limit it obeys arrives from samples_defaults(), so the deck's numbers are stated once,
// in Python, beside the code that enforces them.

(function () {
  var t = window.i18n.t;

  var limits = null;
  var drive = null;
  var capabilities = {};
  var banks = [];
  var active = null;
  var bank = null;      // what is being edited
  var saved = null;     // the same bank as the drive last described it
  var project=null, entry=null, persisting=null, pending=null, persisted="", localError=false, pushing=false, switching=false;
  function draftKey(path){return "rx3.samples.draft:"+path;}
  function projectDirty(){return project && (project.deleted.length || project.active!==project.savedActive || project.entries.some(e=>JSON.stringify(e.value)!==JSON.stringify(e.saved)));}
  function stash(){
    if(!project || !drive || switching || pushing)return;
    var text=JSON.stringify(project);
    if(text===persisted)return;
    try{localStorage.setItem(draftKey(drive),text);}catch(error){}
    pending={path:drive,text:text};localError=false;
    if(!persisting) persisting=drain();
  }
  async function drain(){
    while(pending){
      var item=pending;pending=null;
      var ok=await window.rx3.ask("samples_draft_store",item.path,JSON.parse(item.text));
      if(!ok){localError=true;pending=null;break;}
      if(item.path===drive)persisted=item.text;
      try{if(localStorage.getItem(draftKey(item.path))===item.text)localStorage.removeItem(draftKey(item.path));}catch(error){}
    }
    persisting=null;drawSync();
  }
  async function flush(){stash();if(persisting)await persisting;return !localError;}
  function drawSync(){
    var warning=document.getElementById("samples-sync");
    var unsent=projectDirty();
    warning.hidden=!project;
    warning.textContent=t(localError ? "samples.localError" : persisting ? "samples.localSaving" : unsent ? "samples.localOnly" : "samples.synced");
    warning.className="notice"+(unsent || localError ? " warn" : "");
    document.getElementById("samples-local-retry").hidden=!localError;
    document.getElementById("bank-save").disabled=!drive || !unsent || !!persisting || localError || pushing;
    document.getElementById("samples-editor").inert=pushing || switching;
    var tag=document.getElementById("tag-samples");tag.hidden=!unsent;tag.textContent=t("samples.pendingTag");tag.title=t("samples.localOnly");
  }
  function chooseEntry(id){
    stopAudition();audioCache.clear();
    entry=project.entries.find(e=>e.id===id)||project.entries[0];
    if(!entry){entry={id:String(Date.now())+"-"+Math.random(),value:emptyBank(freeName()),saved:null};project.entries.push(entry);project.active=entry.id;}
    bank=entry.value;saved=entry.saved;project.selected=entry.id;
    banks=project.entries.map(e=>e.value);
    var selected=project.entries.find(e=>e.id===project.active);active=selected ? selected.value.name : null;
    chosen=0;
    document.getElementById("bank-name").value=bank.name;
    document.getElementById("bank-volume").value=bank.volume;
    document.getElementById("bank-volume-value").textContent=t("unit.percent",{value:bank.volume});
    document.getElementById("shift-silence").checked=bank.shiftSilence;
    drawBankPicker();redraw();
  }
  var simulate = false;
  var chosen = 0;       // which pad the inspector is showing

  var MODE_KEYS = ["samples.modeOnce", "samples.modeHold", "samples.modeLoop",
                   "samples.modeLatch"];
  var MODE_HINTS = ["samples.modeOnceHint", "samples.modeHoldHint",
                    "samples.modeLoopHint", "samples.modeLatchHint"];

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function blank(index) {
    return {
      source: null, audioPath: null, sourceName: "", keep: false, present: false, seconds: 0,
      start: 0, sourceSeconds: 0,
      colour: limits.colours[index], name: "", mode: 0, gain: limits.gainUnity,
    };
  }

  function emptyBank(name) {
    var pads = [];
    for (var i = 0; i < limits.padCount; i++) pads.push(blank(i));
    return {
      name: name, volume: limits.volumeDefault, shiftSilence: false,
      pads: pads, onDrive: false, settingsOk: true,
    };
  }

  /** One bank as the drive described it, in the shape the editor edits. */
  function fromDrive(described) {
    var pads = described.pads.map(function (pad) {
      return {
        source: null, audioPath: pad.path, sourceName: "", keep: pad.present, present: pad.present,
        start: 0, sourceSeconds: pad.seconds,
        seconds: pad.seconds, colour: pad.colour, name: pad.name, mode: pad.mode,
        gain: pad.gain,
      };
    });
    return {
      name: described.name, volume: described.volume,
      shiftSilence: described.shiftSilence, pads: pads,
      onDrive: true, settingsOk: described.settingsOk,
    };
  }

  function copy(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function dirty() {
    return !saved || JSON.stringify(bank) !== JSON.stringify(saved);
  }

  function filled(pad) {
    return Boolean(pad.source) || pad.keep;
  }

  function usedBytes() {
    var total = 0;
    for (var i = 0; i < bank.pads.length; i++) {
      var pad = bank.pads[i];
      if (filled(pad)) total += Math.round(pad.seconds * 44100) * 4;
    }
    return total;
  }

  function readable(count) { return window.i18n.bytes(count); }

  // Drawing -------------------------------------------------------------------

  function drawGrid() { if (window.ui) window.ui.preserve(drawGridContent); else drawGridContent(); }
  function drawGridContent() {
    var grid = document.getElementById("pad-grid");
    grid.setAttribute("role", simulate ? "group" : "radiogroup");
    grid.replaceChildren();
    for (var i = 0; i < bank.pads.length; i++) {
      grid.append(drawPad(i));
    }
    updatePlaying();
    document.getElementById("bank-size").textContent =
      readable(usedBytes()) + " / " + readable(limits.bankMaxBytes);
  }

  function drawPad(index) {
    var pad = bank.pads[index];
    var tile = el("button", "pad" + (filled(pad) ? "" : " empty"));
    tile.type = "button";
    tile.id = "sample-pad-" + index;
    if (!simulate) {
      tile.setAttribute("role", "radio");
      tile.setAttribute("aria-checked", String(index === chosen));
      tile.tabIndex = index === chosen ? 0 : -1;
    }
    tile.addEventListener("keydown", function (event) {
      if (simulate && pad.mode === 1 && [" ", "Enter"].includes(event.key) && !event.repeat) {
        event.preventDefault(); hear(pad, true);
      } else if (!simulate && ["ArrowLeft","ArrowRight","ArrowUp","ArrowDown","Home","End"].includes(event.key)) {
        event.preventDefault();
        var offset = event.key === "ArrowLeft" ? -1 : event.key === "ArrowRight" ? 1 : event.key === "ArrowUp" ? -4 : 4;
        chosen = event.key === "Home" ? 0 : event.key === "End" ? bank.pads.length - 1 : (index + offset + bank.pads.length) % bank.pads.length;
        stopAudition(); drawGrid(); drawInspector();
        document.getElementById("sample-pad-" + chosen).focus({preventScroll:true});
      }
    });
    tile.addEventListener("keyup", function (event) {
      if (simulate && pad.mode === 1 && [" ", "Enter"].includes(event.key)) { event.preventDefault(); stopPad(pad); }
    });
    tile.addEventListener("blur", function () { if (simulate && pad.mode === 1) stopPad(pad); });
    tile.style.setProperty("--pad-colour", pad.colour);
    tile.addEventListener("pointerdown", function (event) {
      if (simulate && pad.mode === 1) {
        tile.setPointerCapture(event.pointerId); hear(pad, true);
      }
    });
    tile.addEventListener("pointerup", function () { if (simulate && pad.mode === 1) stopPad(pad); });
    tile.addEventListener("pointercancel", function () { if (simulate && pad.mode === 1) stopPad(pad); });
    tile.addEventListener("click", function () {
      if (simulate) { if (pad.mode !== 1) hear(pad, false); return; }
      stopAudition(); chosen = index; drawGrid(); drawInspector();
      if (!filled(pad)) {
        var inspector = document.getElementById("inspector"), picker = document.getElementById("sample-pick");
        if (inspector.scrollIntoView) inspector.scrollIntoView({block:"nearest"});
        if (picker.focus) picker.focus({preventScroll:true});
      }
    });

    tile.append(el("span", "index", String(index + 1)));
    tile.append(el("span", "label",
      pad.name || pad.sourceName || (filled(pad) ? t("samples.kept") : t("samples.empty"))));
    if (filled(pad)) {
      var meter = el("span", "meter");
      var fill = el("span");
      fill.style.width = Math.max(4, Math.min(100, (pad.seconds / limits.maxSeconds) * 100)) + "%";
      meter.append(fill);
      tile.append(meter);
      tile.append(el("span", "dim num", t("samples.seconds", {seconds: window.i18n.number(pad.seconds, {minimumFractionDigits:1, maximumFractionDigits:1})})));
      if (pad.mode) tile.append(el("span", "badge", t(MODE_KEYS[pad.mode])));
    } else {
      tile.append(el("span", "dim", t("samples.addSound")));
    }
    return tile;
  }

  function drawInspector() { if (window.ui) window.ui.preserve(drawInspectorContent); else drawInspectorContent(); }
  function drawInspectorContent() {
    var panel = document.getElementById("inspector");
    panelField = 0;
    panel.replaceChildren();
    var pad = bank.pads[chosen];

    panel.append(el("h2", null, t("samples.padTitle", {index: chosen + 1})));

    var sound = el("div", "row");
    sound.style.marginTop = "var(--s4)";
    var pick = el("button", "btn small", pad.source || pad.keep
      ? t("common.change") : t("samples.addSound"));
    pick.type = "button";
    pick.id = "sample-pick";
    pick.addEventListener("click", chooseSound);
    sound.append(pick);
    sound.append(el("span", "path num" + (pad.sourceName ? "" : " unset"),
      pad.sourceName || (pad.keep ? t("samples.kept") : t("samples.empty"))));
    panel.append(sound);

    var excerpt = el("div","excerpt-controls");
    if (filled(pad)) excerpt.append(field(t("samples.trim"), trimRow(pad), t("ui.excerptStart") + ". " + t("samples.trimHint")));
    excerpt.append(field(t("samples.hear"), hearRow(pad), t("samples.hearHint"))); panel.append(excerpt);
    panel.append(field(t("samples.mode"), modeRow(pad), t(MODE_HINTS[pad.mode])));
    panel.append(field(t("samples.padName"), nameInput(pad)));
    panel.append(field(t("samples.colour"), colourRow(pad), t("samples.colourHint")));
    panel.append(field(t("samples.gain"), gainRow(pad), t("samples.gainHint")));

    var clear = el("button", "btn small quiet", t("samples.clear"));
    clear.type = "button";
    clear.id = "sample-clear";
    clear.style.marginTop = "var(--s5)";
    clear.disabled = !filled(pad) && !pad.name;
    clear.addEventListener("click", function () {
      stopPad(pad);
      bank.pads[chosen] = blank(chosen);
      redraw();
    });
    panel.append(clear);
  }

  var panelField = 0;
  function field(label, control, hint) {
    panelField++;
    var block = el("div");
    block.style.marginTop = "var(--s5)";
    block.className = "form-field";
    var caption = el("label", null, label);
    function firstInput(node) {
      if (/^(INPUT|SELECT)$/.test(node.tagName) && node.type !== "color") return node;
      for (var child of node.children || []) { var found = firstInput(child); if (found) return found; }
      return null;
    }
    var input = firstInput(control);
    if (input) {
      if (!input.id) input.id = "sample-field-" + panelField;
      caption.htmlFor = input.id;
    } else {
      caption.id = "sample-label-" + panelField;
      control.setAttribute("role", "group");
      control.setAttribute("aria-labelledby", caption.id);
    }
    block.append(caption);
    control.style.marginTop = "var(--s2)";
    block.append(control);
    if (hint) {
      var note = el("p", "dim", hint);
      note.style.marginTop = "var(--s2)";
      note.id = "sample-help-" + panelField;
      (input || control).setAttribute("aria-describedby", note.id);
      block.append(note);
    }
    return block;
  }

  function nameInput(pad) {
    var input = document.createElement("input");
    input.type = "text";
    input.id = "sample-name";
    input.value = pad.name;
    input.maxLength = limits.nameMaxChars;
    input.placeholder = t("samples.padNamePlaceholder");
    input.style.width = "100%";
    input.addEventListener("input", function () {
      pad.name = input.value;
      drawGrid();
      state();
    });
    return input;
  }

  function colourRow(pad) {
    var row = el("div", "swatches");
    for (var i = 0; i < limits.colours.length; i++) {
      row.append(swatch(pad, limits.colours[i]));
    }
    var custom = document.createElement("input");
    custom.type = "color";
    custom.id = "sample-color";
    custom.value = pad.colour;
    custom.setAttribute("aria-label", t("samples.colourOther"));
    custom.addEventListener("input", function () {
      pad.colour = custom.value.toUpperCase();
      redraw();
    });
    row.append(custom);
    return row;
  }

  function swatch(pad, colour) {
    var button = el("button", "swatch");
    button.type = "button";
    button.style.background = colour;
    button.setAttribute("aria-pressed", String(pad.colour.toUpperCase() === colour));
    button.setAttribute("data-focus", "swatch-" + colour);
    button.setAttribute("aria-label", t("ui.colorValue", {color:colour}));
    button.addEventListener("click", function () {
      pad.colour = colour;
      redraw();
    });
    return button;
  }

  function gainRow(pad) {
    var row = el("div", "row");
    var slider = document.createElement("input");
    slider.type = "range";
    slider.id = "sample-gain";
    slider.min = "0";
    slider.max = String(limits.gainMax);
    slider.value = String(pad.gain);
    slider.style.maxWidth = "var(--range-width)";
    var readout = el("span", "num", t("unit.percent", {value:pad.gain}));
    slider.addEventListener("input", function () {
      pad.gain = Number(slider.value);
      updateGains();
      readout.textContent = t("unit.percent", {value:pad.gain});
      state();
    });
    var reset = el("button", "btn small quiet", t("samples.gainReset"));
    reset.type = "button";
    reset.id = "sample-gain-reset";
    reset.addEventListener("click", function () {
      pad.gain = limits.gainUnity;
      redraw();
    });
    row.append(slider, readout, reset);
    return row;
  }

  function trimRow(pad) {
    var row = el("div", "row");
    function input(label, value, maximum, change) {
      var wrapper = el("label", null, label + " ");
      var control = document.createElement("input");
      control.id = "sample-trim-" + row.children.length;
      control.type = "number"; control.min = "0"; control.step = "0.01";
      control.max = String(maximum); control.value = String(value);
      control.style.width = "var(--number-width)";
      control.addEventListener("change", function () {
        var number = Number(control.value);
        if (!Number.isFinite(number)) return;
        stopAudition();
        if (!pad.source) { pad.source = pad.audioPath; pad.keep = false; }
        change(number); redraw();
      });
      wrapper.append(control); row.append(wrapper);
    }
    input(t("samples.start"), pad.start, pad.sourceSeconds, function (value) {
      pad.start = Math.max(0, Math.min(pad.sourceSeconds - 1 / 44100, value));
      pad.seconds = Math.min(pad.seconds, pad.sourceSeconds - pad.start);
    });
    input(t("samples.duration"), pad.seconds, limits.maxSeconds, function (value) {
      pad.seconds = Math.max(1 / 44100, Math.min(limits.maxSeconds,
        pad.sourceSeconds - pad.start, value));
    });
    return row;
  }

  var voices = new Map();
  var audioContext = null;
  var audioCache = new Map();
  function preparedAudio(pad) {
    var args = [pad.source || pad.audioPath, pad.start, pad.source ? pad.seconds : null];
    var key = JSON.stringify(args);
    if (!audioCache.has(key)) {
      if (audioCache.size >= 16) audioCache.delete(audioCache.keys().next().value);
      var pending = window.rx3.ask("samples_audition", args[0], args[1], args[2]);
      audioCache.set(key, pending);
      pending.then(function (answer) { if (!answer) audioCache.delete(key); },
        function () { audioCache.delete(key); });
    }
    return audioCache.get(key);
  }

  function updatePlaying() {
    if (!bank) return;
    if (window.rx3mock) window.rx3mock.setPads(bank.pads, chosen,
      bank.pads.map(function (pad, i) { return voices.has(pad) ? i : -1; }));
    var tiles = document.getElementById("pad-grid").children;
    for (var i = 0; i < tiles.length; i++) {
      tiles[i].setAttribute("data-playing", String(voices.has(bank.pads[i])));
      if (simulate) {
        tiles[i].setAttribute("aria-pressed", String(voices.has(bank.pads[i])));
        tiles[i].setAttribute("aria-label", t("samples.padTitle",{index:i+1}) + " · " + (bank.pads[i].name || t("samples.empty")) + (voices.has(bank.pads[i]) ? " · " + t("ui.playing") : ""));
      }
      else if (tiles[i].removeAttribute) tiles[i].removeAttribute("aria-pressed");
    }
  }

  function stopPad(pad) {
    var voice = voices.get(pad);
    if (!voice) return;
    voices.delete(pad);
    updatePlaying();
    if (voice.source) { voice.source.stop(); voice.source.disconnect(); }
    if (voice.gain) voice.gain.disconnect();
  }

  function stopAudition() {
    Array.from(voices.keys()).forEach(stopPad);
  }

  function playing(pad) { return voices.has(pad || bank.pads[chosen]); }

  async function hear(pad, held) {
    if (!(pad.source || pad.audioPath)) return;
    if (playing(pad) && (pad.mode === 2 || pad.mode === 3)) {
      stopPad(pad); if (!simulate) drawInspector(); return;
    }
    // Reserve pending voices too: conversion must not let rapid presses
    // exceed the hardware ceiling before their audio has started.
    if (!playing(pad) && voices.size >= limits.maxVoices) {
      window.rx3.fail(t("samples.voiceLimit", {count: limits.maxVoices}));
      return;
    }
    stopPad(pad);
    var voice = {held: held, mode: pad.mode};
    voices.set(pad, voice);
    updatePlaying();
    try {
      var AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!audioContext) audioContext = new AudioContextClass({sampleRate: 44100});
      await audioContext.resume();
      var heard = await preparedAudio(pad);
      if (!heard || voices.get(pad) !== voice) {
        if (voices.get(pad) === voice) stopPad(pad);
        return;
      }
      var bytes = Uint8Array.from(window.atob(heard.audio), function (c) { return c.charCodeAt(0); });
      var buffer = await audioContext.decodeAudioData(bytes.buffer);
      // Decoding is asynchronous too: a released hold must never start late.
      if (voices.get(pad) !== voice) return;
      if (pad.mode === 2) {
        // Match the runtime's 32-frame splice ramp at 44.1 kHz. Account for
        // contexts that resample to the device rate despite the requested rate.
        var ramp = Math.round(32 * buffer.sampleRate / 44100);
        if (buffer.length >= Math.round(128 * buffer.sampleRate / 44100)) {
          for (var channel = 0; channel < buffer.numberOfChannels; channel++) {
            var pcm = buffer.getChannelData(channel);
            for (var frame = 0; frame < ramp; frame++) {
              var edge = (frame + 1) / ramp;
              pcm[frame] *= edge; pcm[pcm.length - 1 - frame] *= edge;
            }
          }
        }
      }
      voice.source = audioContext.createBufferSource();
      voice.source.buffer = buffer;
      voice.source.loop = pad.mode === 2;
      voice.gain = audioContext.createGain();
      voice.gain.gain.value = pad.gain / 100 * Math.pow(bank.volume / 100, 2) * 0.5;
      voice.source.connect(voice.gain); voice.gain.connect(audioContext.destination);
      voice.source.onended = function () {
        if (voices.get(pad) === voice) { stopPad(pad); if (!simulate) drawInspector(); }
      };
      voice.source.start();
      if (!held && !simulate) drawInspector();
    } catch (error) {
      if (voices.get(pad) === voice) { stopPad(pad); window.rx3.fail(String(error)); }
    }
  }

  function updateGains() {
    voices.forEach(function (voice, pad) {
      if (voice.gain) voice.gain.gain.value = pad.gain / 100 * Math.pow(bank.volume / 100, 2) * 0.5;
    });
  }

  function hearRow(pad) {
    var row = el("div", "row");
    var button = el("button", "btn small",
      playing(pad) && (pad.mode === 2 || pad.mode === 3) ? t("samples.hearStop") : t("samples.hearPlay"));
    button.type = "button";
    button.id = "sample-audition";
    button.disabled = !(pad.source || pad.audioPath);
    if (pad.mode === 1) {
      button.addEventListener("pointerdown", function (event) {
        button.setPointerCapture(event.pointerId); hear(pad, true);
      });
      button.addEventListener("keydown", function (event) {
        if ((event.key === " " || event.key === "Enter") && !event.repeat) {
          event.preventDefault(); hear(pad, true);
        }
      });
      button.addEventListener("keyup", function () { stopAudition(); drawInspector(); });
    } else {
      button.addEventListener("click", function () { hear(pad, false); });
    }
    row.append(button);
    return row;
  }

  function modeRow(pad) {
    var row = el("div", "modes");
    for (var mode = 0; mode < MODE_KEYS.length; mode++) {
      row.append(modeButton(pad, mode));
    }
    return row;
  }

  function modeButton(pad, mode) {
    var button = el("button", null, t(MODE_KEYS[mode]));
    button.type = "button";
    button.id = "sample-mode-" + mode;
    button.setAttribute("aria-pressed", String(pad.mode === mode));
    button.addEventListener("click", function () {
      stopAudition();
      pad.mode = mode;
      redraw();
    });
    return button;
  }

  function state() {
    var pill = document.getElementById("bank-state");
    var unsaved = dirty();
    pill.textContent=t(unsaved ? "samples.isNew" : "samples.clean");
    pill.className="pill "+(unsaved ? "off" : "on");
    document.getElementById("bank-note").textContent=!bank.settingsOk ? t("samples.settingsBad") : "";
    document.getElementById("bank-activate").disabled=!entry || project.active===entry.id;
    document.getElementById("bank-delete").disabled=!entry;
    document.getElementById("bank-active").textContent=active ? t("ui.activeBank",{name:active}) : "";
    stash();drawSync();

    var shift = document.getElementById("cap-shift");
    var known = capabilities.shift_silence === "ready";
    shift.textContent = known ? t("samples.capOn") : t("samples.capUnknown");
    shift.className = "pill " + (known ? "on" : "");
  }

  function redraw() {
    drawGrid();
    drawInspector();
    state();
  }

  function drawBankPicker() {
    var picker = document.getElementById("bank-pick");
    picker.replaceChildren();
    if(!project)return;
    project.entries.forEach(function(item){
      var option=document.createElement("option");option.value=item.id;
      option.textContent=item.value.name+(item.id===project.active ? t("ui.activeSuffix") : "");picker.append(option);
    });
    picker.hidden=!project.entries.length;
    picker.value=entry ? entry.id : "";
  }

  // Doing ---------------------------------------------------------------------

  async function chooseSound() {
    var picked = await window.rx3.ask("pick_files", "audio", "");
    if (!picked || !picked.paths.length) return;
    var measured = await window.rx3.ask("samples_analyse", picked.paths);
    if (!measured) return;
    var at = chosen;
    for (var i = 0; i < measured.length && at < limits.padCount; i++) {
      var source = measured[i];
      if (!source.accepted) {
        window.rx3.fail(t("samples.tooLong", {name: source.name, refusal: window.i18n.message(source.refusal)}));
        continue;
      }
      var pad = bank.pads[at];
      stopAudition();
      var local=await window.rx3.ask("samples_draft_asset",source.path);
      if(!local)continue;
      pad.source = local;
      pad.audioPath = null;
      pad.start = 0;
      pad.sourceSeconds = source.seconds;
      pad.sourceName = source.name;
      pad.seconds = Math.min(source.seconds, limits.maxSeconds);
      pad.keep = false;
      pad.present = true;
      if (!pad.name) pad.name = source.name.replace(/\.[^.]+$/, "").slice(0, limits.nameMaxChars);
      pad.gain = limits.gainUnity;
      at += 1;
    }
    var first = chosen;
    redraw();
    if (at > first) document.getElementById("bank-note").textContent = t(at-first === 1 ? "ui.sampleAdded" : "ui.samplesAdded", {first:first+1,last:at});
  }

  async function save() {
    if(pushing || !project || !(await flush()))return;
    if(pushing)return;
    pushing=true;drawSync();
    var started=await window.rx3.ask("samples_push",drive,copy(project));
    if(!started){pushing=false;drawSync();return;}
    window.rx3.watchJob(async function(result){
      pushing=false;
      // Failure/cancellation keeps the local project and its pending USB state.
      if(result && result.state && result.state!=="done"){drawSync();return;}
      await reload();
    });
  }

  async function reload() {
    var path=drive;switching=true;drawSync();
    var answer=await window.rx3.ask("samples_draft_load",path);
    if(path!==drive)return;
    switching=false;
    if(!answer){drawSync();return;}
    project=answer.project;
    var recovered=null;
    try{recovered=JSON.parse(localStorage.getItem(draftKey(path))||"null");}catch(error){}
    if(recovered)project=recovered;
    if(!project){
      project={version:1,entries:[],active:null,savedActive:null,deleted:[],selected:null};
      (answer.banks||[]).forEach(function(described,index){
        var value=fromDrive(described),id="bank-"+index;
        project.entries.push({id:id,value:value,saved:copy(value)});
        if(described.name===answer.active)project.active=project.savedActive=id;
      });
    }
    persisted=answer.project && !recovered ? JSON.stringify(answer.project) : "";
    localError=false;chooseEntry(project.selected||project.active);
  }

  function freeName() {
    for (var n = 1; ; n++) {
      var candidate = t("ui.bankDefault", {count:n});
      var taken = false;
      for (var i = 0; project && i < project.entries.length; i++) if (project.entries[i].value.name === candidate) taken = true;
      if (!taken) return candidate;
    }
  }

  // Wiring ---------------------------------------------------------------------

  function wire() {
    function releaseHeld() {
      if (simulate) return;
      voices.forEach(function (voice, pad) { if (voice.held) stopPad(pad); });
      if (!simulate) drawInspector();
    }
    window.addEventListener("pointerup", releaseHeld);
    window.addEventListener("pointercancel", releaseHeld);
    window.addEventListener("blur", stopAudition);
    function setPadMode(play) {
      stopAudition(); simulate=play; document.getElementById("samples-simulate").checked=play;
      document.getElementById("samples-edit").setAttribute("aria-pressed",String(!play));
      document.getElementById("samples-play").setAttribute("aria-pressed",String(play)); drawGrid();
    }
    document.getElementById("samples-edit").addEventListener("click",function () {setPadMode(false);});
    document.getElementById("samples-play").addEventListener("click",function () {setPadMode(true);});
    window.addEventListener("rx3selection",function(event) {
      var report=event.detail.report, present=report && report.mod && report.mod.modules.includes("samples");
      document.getElementById("samples-module-note").textContent=t(present ? "ui.samplesInstalled" : "ui.samplesModule") + (event.detail.selected.includes("samples") ? " " + t("ui.samplesSelected") : "");
      document.getElementById("samples-modules").hidden=present;
    });
    document.getElementById("samples-simulate").addEventListener("change", function (event) {
      setPadMode(event.target.checked);
    });
    document.getElementById("samples-stop").addEventListener("click", function () {
      stopAudition(); drawInspector();
    });
    window.addEventListener("keydown", function (event) {
      if (!simulate || !bank || document.getElementById("samples").hidden || event.repeat) return;
      if (event.key === "Escape" || (event.key === "Shift" && bank.shiftSilence)) { stopAudition(); return; }
      if (/SELECT|TEXTAREA/.test(event.target.tagName) ||
          (event.target.tagName === "INPUT" && event.target.type !== "checkbox")) return;
      var number = Number(event.key);
      if (number >= 1 && number <= limits.padCount && Number.isInteger(number)) {
        event.preventDefault(); var pad = bank.pads[number - 1]; hear(pad, pad.mode === 1);
      }
    });
    window.addEventListener("keyup", function (event) {
      var number = Number(event.key);
      if (simulate && bank && number >= 1 && number <= limits.padCount && Number.isInteger(number)) {
        var pad = bank.pads[number - 1]; if (pad.mode === 1) stopPad(pad);
      }
    });
    window.addEventListener("beforeunload", function (event) {
      if (persisting || localError) { event.preventDefault(); event.returnValue = ""; }
    });
    document.getElementById("bank-name").addEventListener("input", function (event) {
      bank.name = event.target.value;
      if(project.active===entry.id)active=bank.name;
      drawBankPicker();state();
    });
    document.getElementById("bank-pick").addEventListener("change", async function (event) {
      chooseEntry(event.target.value);
    });
    document.getElementById("bank-new").addEventListener("click", function () {
      var id=String(Date.now())+"-"+Math.random();
      project.entries.push({id:id,value:emptyBank(freeName()),saved:null});
      chooseEntry(id);
    });
    document.getElementById("bank-delete").addEventListener("click", async function () {
      if(!entry)return;
      if(!(await window.rx3.confirm(t("ui.deleteBankTitle"),t("samples.deleteLocalBody",{name:bank.name}),t("common.remove"))))return;
      if(entry.saved)project.deleted.push(entry.saved.name);
      project.entries=project.entries.filter(e=>e!==entry);
      if(project.active===entry.id)project.active=project.entries.length ? project.entries[0].id : null;
      banks=project.entries.map(e=>e.value);chooseEntry(null);
    });
    document.getElementById("bank-volume").addEventListener("input", function (event) {
      bank.volume = Number(event.target.value);
      updateGains();
      document.getElementById("bank-volume-value").textContent = t("unit.percent",{value:bank.volume});
      state();
    });
    document.getElementById("shift-silence").addEventListener("change", function (event) {
      bank.shiftSilence = event.target.checked;
      state();
    });
    document.getElementById("bank-save").addEventListener("click", save);
    document.getElementById("samples-local-retry").addEventListener("click",flush);
    document.getElementById("bank-activate").addEventListener("click", async function () {
      project.active=entry.id;active=bank.name;drawBankPicker();state();
    });

    window.addEventListener("rx3jobfinished",function(event){
      if(pushing && event.detail.kind==="samples" && event.detail.state!=="done") {pushing=false;drawSync();}
    });
    window.addEventListener("rx3drive", function (event) {
      drive = event.detail.path;
      capabilities = event.detail.capabilities || {};
      document.getElementById("samples-need-drive").hidden = true;
      document.getElementById("samples-editor").hidden = false;
      reload();
    });
    window.addEventListener("rx3language", function () {
      if (bank) {drawBankPicker();redraw();}
    });
  }

  async function start() {
    limits = await window.rx3.ask("samples_defaults");
    if (!limits) return;
    bank = emptyBank(t("ui.bankDefault", {count:1}));
    saved = null;
    wire();
  }

  window.rx3samples = {
    summary:function(){return bank ? {name:bank.name,count:bank.pads.filter(filled).length,saved:!projectDirty(),drive:drive} : null;},
    start:start,
    beforeDrive:async function(){return !pushing && (!drive || await flush());}
  };
})();
