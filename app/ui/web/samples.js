// SPDX-License-Identifier: MPL-2.0
//
// The pad editor. It holds one bank in memory, compares it against what the
// drive last said, and writes nothing until the operator saves. Every limit it
// obeys arrives from samples_defaults(), so the deck's numbers are stated once,
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

  function drawGrid() {
    var grid = document.getElementById("pad-grid");
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
    tile.setAttribute("aria-selected", String(index === chosen));
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

  function drawInspector() {
    var panel = document.getElementById("inspector");
    panel.replaceChildren();
    var pad = bank.pads[chosen];

    panel.append(el("h2", null, t("samples.padTitle", {index: chosen + 1})));

    var sound = el("div", "row");
    sound.style.marginTop = "14px";
    var pick = el("button", "btn small", pad.source || pad.keep
      ? t("common.change") : t("samples.addSound"));
    pick.type = "button";
    pick.addEventListener("click", chooseSound);
    sound.append(pick);
    sound.append(el("span", "path num",
      pad.sourceName || (pad.keep ? t("samples.kept") : t("samples.empty"))));
    panel.append(sound);

    panel.append(field(t("samples.padName"), nameInput(pad)));
    panel.append(field(t("samples.colour"), colourRow(pad), t("samples.colourHint")));
    panel.append(field(t("samples.mode"), modeRow(pad), t(MODE_HINTS[pad.mode])));
    if (filled(pad)) panel.append(field(t("samples.trim"), trimRow(pad), t("samples.trimHint")));
    panel.append(field(t("samples.hear"), hearRow(pad), t("samples.hearHint")));
    panel.append(field(t("samples.gain"), gainRow(pad), t("samples.gainHint")));

    var clear = el("button", "btn small quiet", t("samples.clear"));
    clear.type = "button";
    clear.style.marginTop = "18px";
    clear.disabled = !filled(pad) && !pad.name;
    clear.addEventListener("click", function () {
      stopPad(pad);
      bank.pads[chosen] = blank(chosen);
      redraw();
    });
    panel.append(clear);
  }

  function field(label, control, hint) {
    var block = el("div");
    block.style.marginTop = "18px";
    block.append(el("label", null, label));
    control.style.marginTop = "8px";
    block.append(control);
    if (hint) {
      var note = el("p", "dim", hint);
      note.style.marginTop = "6px";
      block.append(note);
    }
    return block;
  }

  function nameInput(pad) {
    var input = document.createElement("input");
    input.type = "text";
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
    button.setAttribute("aria-label", colour);
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
    slider.min = "0";
    slider.max = String(limits.gainMax);
    slider.value = String(pad.gain);
    slider.style.maxWidth = "200px";
    var readout = el("span", "num", t("unit.percent", {value:pad.gain}));
    slider.addEventListener("input", function () {
      pad.gain = Number(slider.value);
      updateGains();
      readout.textContent = t("unit.percent", {value:pad.gain});
      state();
    });
    var reset = el("button", "btn small quiet", t("samples.gainReset"));
    reset.type = "button";
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
      control.type = "number"; control.min = "0"; control.step = "0.01";
      control.max = String(maximum); control.value = String(value);
      control.style.width = "90px";
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
    for (var i = 0; i < tiles.length; i++)
      tiles[i].setAttribute("aria-pressed", String(voices.has(bank.pads[i])));
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
    pill.textContent = !bank.onDrive ? t("samples.isNew")
      : unsaved ? t("samples.dirty") : t("samples.clean");
    pill.className = "pill " + (unsaved || !bank.onDrive ? "off" : "on");

    document.getElementById("bank-note").textContent =
      !bank.settingsOk ? t("samples.settingsBad")
      : unsaved ? t("samples.nothingYet") : "";
    document.getElementById("bank-activate").disabled =
      !bank.onDrive || unsaved || active === bank.name;
    document.getElementById("bank-delete").disabled = !bank.onDrive;

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
    for (var i = 0; i < banks.length; i++) {
      var option = document.createElement("option");
      option.value = option.textContent =
        banks[i].name + (banks[i].name === active ? " *" : "");
      option.value = banks[i].name;
      picker.append(option);
    }
    picker.hidden = !banks.length;
    picker.value = bank && bank.onDrive ? bank.name : "";
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
      pad.source = source.path;
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
    chosen = Math.min(at, limits.padCount - 1);
    redraw();
  }

  function payload() {
    return bank.pads.map(function (pad) {
      return {
        source: pad.source, keep: pad.keep && !pad.source,
        colour: pad.colour, name: pad.name, mode: pad.mode, gain: pad.gain,
        start: pad.start, duration: pad.seconds,
      };
    });
  }

  async function save() {
    var started = await window.rx3.ask("samples_save", drive, bank.name, payload(), {
      volume: bank.volume,
      shiftSilence: bank.shiftSilence,
      activate: !active || active === bank.name,
    });
    if (started) window.rx3.watchJob(reload);
  }

  async function reload(keepName) {
    stopAudition();
    audioCache.clear();
    if (!drive) return;
    var answer = await window.rx3.ask("samples_read", drive);
    if (!answer) return;
    banks = answer.banks;
    active = answer.active;
    var wanted = typeof keepName === "string" ? keepName : (bank ? bank.name : active);
    var found = null;
    for (var i = 0; i < banks.length; i++) if (banks[i].name === wanted) found = banks[i];
    if (!found && banks.length) found = banks[0];
    bank = found ? fromDrive(found) : emptyBank(freeName());
    saved = copy(bank);
    chosen = 0;
    document.getElementById("bank-name").value = bank.name;
    document.getElementById("bank-volume").value = bank.volume;
    document.getElementById("bank-volume-value").textContent = bank.volume;
    document.getElementById("shift-silence").checked = bank.shiftSilence;
    drawBankPicker();
    redraw();
  }

  function freeName() {
    for (var n = 1; ; n++) {
      var candidate = "bank" + n;
      var taken = false;
      for (var i = 0; i < banks.length; i++) if (banks[i].name === candidate) taken = true;
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
    document.getElementById("samples-simulate").addEventListener("change", function (event) {
      stopAudition(); simulate = event.target.checked; drawGrid();
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
      if (bank && dirty()) { event.preventDefault(); event.returnValue = ""; }
    });
    document.getElementById("bank-name").addEventListener("input", function (event) {
      bank.name = event.target.value;
      state();
    });
    document.getElementById("bank-pick").addEventListener("change", function (event) {
      if (dirty() && !window.confirm(t("samples.discard"))) { drawBankPicker(); return; }
      reload(event.target.value);
    });
    document.getElementById("bank-new").addEventListener("click", function () {
      if (dirty() && !window.confirm(t("samples.discard"))) return;
      stopAudition();
      bank = emptyBank(freeName());
      saved = null;
      chosen = 0;
      document.getElementById("bank-name").value = bank.name;
      document.getElementById("bank-volume").value = bank.volume;
      document.getElementById("bank-volume-value").textContent = bank.volume;
      document.getElementById("shift-silence").checked = false;
      redraw();
    });
    document.getElementById("bank-delete").addEventListener("click", async function () {
      if (!bank.onDrive) return;
      var gone = await window.rx3.ask("samples_remove", drive, bank.name);
      if (gone) reload(null);
    });
    document.getElementById("bank-volume").addEventListener("input", function (event) {
      bank.volume = Number(event.target.value);
      updateGains();
      document.getElementById("bank-volume-value").textContent = bank.volume;
      state();
    });
    document.getElementById("shift-silence").addEventListener("change", function (event) {
      bank.shiftSilence = event.target.checked;
      state();
    });
    document.getElementById("bank-save").addEventListener("click", save);
    document.getElementById("bank-activate").addEventListener("click", async function () {
      var done = await window.rx3.ask("samples_activate", drive, bank.name);
      if (done) reload(bank.name);
    });

    window.addEventListener("rx3drive", function (event) {
      drive = event.detail.path;
      capabilities = event.detail.capabilities || {};
      document.getElementById("samples-need-drive").hidden = true;
      document.getElementById("samples-editor").hidden = false;
      reload();
    });
    window.addEventListener("rx3language", function () {
      if (bank) redraw();
    });
  }

  async function start() {
    limits = await window.rx3.ask("samples_defaults");
    if (!limits) return;
    bank = emptyBank("bank1");
    saved = null;
    wire();
  }

  window.rx3samples = {start: start};
})();
