// SPDX-License-Identifier: MPL-2.0
//
// Separation. The long work belongs to the job slot, the same one the build
// uses, so two things that would both write the same drive cannot run at once
// and cancelling means one thing wherever it is pressed.

(function () {
  var t = window.i18n.t;

  var libraryBlocked = true;
  var machine = null;
  var library = null;
  var quality = null;
  var output = "";
  var selectedDrive = "";
  var previewTrack = "";
  var trackRequest = 0;
  var libraryRequest = 0;
  var forecastRequest = 0;
  var overcueStorage = null;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function id(name) {
    return document.getElementById(name);
  }

  // Drawing --------------------------------------------------------------------

  function drawMachine() {
    if (!machine) return;
    id("runtime-summary").textContent = t(machine.ready ? "ui.runtimeReady" : "stems.needRuntime");
    var runtime = id("stems-runtime"), content = runtime.parentElement;
    if (content) {
      if (!machine.ready) content.insertBefore(runtime,content.querySelector(".card"));
      else content.append(runtime);
    }
    var pill = id("runtime-state");
    pill.textContent = machine.ready ? t("stems.ready") : t("stems.notReady");
    pill.className = "pill " + (machine.ready ? "on" : "off");
    id("runtime-install").textContent = machine.ready ? t("stems.reinstall") : t("stems.install");

    var picker = id("accelerator");
    picker.replaceChildren();
    for (var i = 0; i < machine.accelerators.length; i++) {
      var option = document.createElement("option");
      option.value = machine.accelerators[i].key;
      var labels = {auto:"ui.acceleratorAuto",cpu:"ui.acceleratorCpu",metal:"ui.acceleratorMetal",mps:"ui.acceleratorMetal",cuda:"ui.acceleratorCuda",rocm:"ui.acceleratorRocm",directml:"ui.acceleratorDirectml"};
      option.textContent = labels[option.value] ? t(labels[option.value]) : window.i18n.message(machine.accelerators[i].label);
      picker.append(option);
    }
    if (machine.accelerator) picker.value = machine.accelerator;
    else if (quality) picker.value = quality.accelerator;
  }

  function selectedRoles() { return ["vocals", "drums"]; }

  function drawPolicy() {
    var blocked = drumsBlocked();
    var warning = id("roles-warning");
    warning.hidden = !blocked;
    warning.textContent = blocked ? window.i18n.message(blocked) : "";
    drawOvercue();
  }

  function drawOvercue() {
    var capability = quality && quality.overcue;
    id("stems-overcue").disabled = !capability || !capability.ready;
    var unavailable = capability && !capability.ready;
    id("stems-overcue-status").hidden = !unavailable;
    id("stems-overcue-status").textContent = unavailable ? window.i18n.message(capability.message) : "";
    var known = overcueStorage && !overcueStorage.unknown;
    id("stems-overcue-storage").textContent = known
      ? t("stems.overcueStorage", {mb:window.i18n.number(Math.ceil(overcueStorage.bytes / 1000000))})
      : t("stems.overcueStorageUnknown");
  }

  function drumsBlocked() { return quality && quality.drumsBlocked; }

  function drawPlaylists() {
    var row = id("playlist-row");
    if (!library) {
      row.hidden = true;
      return;
    }
    row.hidden = false;
    var picker = id("playlist");
    var selected = picker.value;
    picker.replaceChildren();
    for (var i = 0; i < library.playlists.length; i++) {
      var item = library.playlists[i];
      var option = document.createElement("option");
      option.value = item.id;
      option.textContent = t("stems.playlistOption", {name:item.path || item.name,
        tracks:t("drive.trackCount", {count:item.tracks})}) +
        (item.missing ? " - " + t("stems.missing", {count:item.missing}) : "");
      picker.append(option);
    }
    if (selected) picker.value = selected;
    forecast();
    drawTracks();
    drawWaveforms();
  }

  async function forecast() {
    var request = ++forecastRequest;
    overcueStorage = null;
    drawOvercue();
    var picker = id("playlist");
    if (!library || !picker.value) return;
    var wanted = selectedRoles();
    var answer = await window.rx3.ask("stems_forecast", picker.value, wanted, true);
    if (request !== forecastRequest) return;
    var table = id("stems-memory");
    table.replaceChildren();
    if (!answer) return;
    overcueStorage = answer.overcueStorage || null;
    drawOvercue();
    if (answer.refused)
      table.append(el("p", "notice", t("stems.forecastRefused", {count: answer.refused})));
    for (var track of answer.memory || []) {
      // A certain refusal stands out; a risk or a pending check is a note.
      var kind = track.status === "refused" ? "notice" :
        track.status === "shared" || track.status === "near" ? "note" : "dim";
      var line = el("p", kind, t("stems.trackNotice", {
        name: track.artist ? track.artist + " - " + track.title : track.title,
        detail: track.message}));
      line.dataset.status = track.status;
      if (track.status === "refused" || track.status === "near" || track.status === "shared") table.append(line);
    }
  }

  function drawLibraryGuard() {
    var warning = id("library-warning");
    warning.hidden = !libraryBlocked;
    warning.firstElementChild.textContent = t("stems.libraryBusy");
    id("library-recheck").textContent = t("stems.recheck");
    id("library-drive").disabled = libraryBlocked;
    id("library-file").disabled = libraryBlocked;
  }

  async function checkLibrary() {
    var status = await window.rx3.ask("stems_library_status");
    libraryBlocked = !status || status.busy;
    drawLibraryGuard();
    note();
    return !libraryBlocked;
  }

  function note() {
    id("stems-note").textContent =
      !machine || !machine.ready ? t("stems.needRuntime")
      : !library ? ""
      : !id("playlist").value ? t("ui.noTracks")
      : !output ? t("stems.needOutput")
      : t("stems.longRun");
    id("stems-note").hidden = !id("stems-note").textContent;
    id("stems-start").disabled =
      libraryBlocked || !machine || !machine.ready || !library || !id("playlist").value || !output ||
      Boolean(drumsBlocked()) || (id("stems-overcue").checked && !(quality && quality.overcue && quality.overcue.ready));
  }

  function setOutput(path) {
    output = path || "";
    drawWaveforms();
    note();
  }

  // Doing ------------------------------------------------------------------------

  async function openLibrary(path) {
    var request=++libraryRequest;
    if (!path || !(await checkLibrary()) || request!==libraryRequest) return;
    var answer = await window.rx3.ask("stems_library", path);
    if(request!==libraryRequest)return;
    if (!answer) { await checkLibrary(); return; }
    library = answer;
    drawLibraryPath();
    id("stems-listen").hidden = false;
    id("stems-track-picker").hidden = false;
    drawPlaylists();
    note();
  }

  function drawLibraryPath() {
    if (!library) return;
    id("library-count").textContent = t("drive.trackCount", {count: library.tracks});
  }

  async function refreshMachine() {
    machine = await window.rx3.ask("stems_runtime");
    // Refresh capability after installing the preparation engine.
    quality = await window.rx3.ask("stems_qualities", selectedRoles()) || quality;
    drawMachine();
    drawPolicy();
    note();
  }

  async function drawCache() {
    var state = await window.rx3.ask("stems_cache");
    if (!state) return;
    var row = id("stems-cache");
    row.replaceChildren();
    var label = el("label", null, t("stems.cacheLimit"));
    label.htmlFor = "stems-cache-limit";
    var size = el("input");
    size.id = "stems-cache-limit";
    size.type = "number"; size.min = "0"; size.max = String(1024 * Math.pow(1024, 3) / 1e9); size.step = "any";
    size.value = String(state.limit / 1e9);
    size.addEventListener("change", async function () {
      var value = Number(size.value);
      if (!Number.isFinite(value) || value < 0 || value > 1024 * Math.pow(1024, 3) / 1e9) return;
      await window.rx3.ask("stems_cache", Math.round(value * 1e9), false);
      drawCache();
    });
    var clear = el("button", "btn small quiet", t("stems.cacheClear"));
    clear.type = "button";
    clear.disabled = !state.bytes;
    clear.addEventListener("click", async function () {
      if (!(await window.rx3.confirm(t("ui.clearCacheTitle"), t("ui.clearCacheBody"), t("stems.cacheClear")))) return;
      await window.rx3.ask("stems_cache", null, true); drawCache();
    });
    row.append(label, size, el("span", "dim num", window.i18n.bytes(state.bytes)), clear);
  }

  function drawWaveforms(refresh) {
    window.dispatchEvent(new CustomEvent("rx3stemtrack", {detail:{track:previewTrack, drive:output, origin:"drive", refresh:refresh===true}}));
  }

  async function drawTracks() {
    var request = ++trackRequest;
    var tracks = library ? await window.rx3.ask("stems_tracks", id("playlist").value) : [];
    if (request !== trackRequest) return;
    var picker = id("stem-track");
    picker.replaceChildren();
    for (var track of tracks || []) {
      var option = el("option", null, track.artist + " - " + track.title);
      option.value = track.id; picker.append(option);
    }
    if (Array.from(picker.options).some(function (item) { return item.value === previewTrack; })) picker.value = previewTrack;
    await selectTrack();
  }

  function selectTrack() {
    previewTrack = id("stem-track").value;
    drawWaveforms();
    note();
  }

  function wire() {
    id("stems-overcue").addEventListener("change", note);
    window.addEventListener("rx3jobfinished", function (event) {
      if (event.detail.kind === "stems") drawWaveforms(true);
    });
    id("stem-track").addEventListener("change", selectTrack);
    window.rx3listen.attach(id("stems-listen"));
    id("stems-listen").insertBefore(id("stems-track-picker"), id("stems-listen").children[1]);
    id("library-recheck").addEventListener("click", checkLibrary);
    id("library-drive").addEventListener("click", async function () {
      var drive = window.rx3.selectedDrive();
      if (drive) await openLibrary(drive);
      else window.rx3.showDrive();
    });
    id("library-file").addEventListener("click", async function () {
      var picked = await window.rx3.ask("pick_file", "library", "");
      if (picked) openLibrary(picked.path);
    });
    id("playlist").addEventListener("change", function () { forecast(); drawTracks(); drawWaveforms(); });
    id("accelerator").addEventListener("change", async function (event) {
      var answer = await window.rx3.ask("stems_choose", null, event.target.value, selectedRoles());
      if (answer) {
        quality = answer;
        drawPolicy();
        note();
      }
    });
    id("runtime-install").addEventListener("click", async function () {
      var started = await window.rx3.ask("stems_install", id("accelerator").value);
      if (started) window.rx3.watchJob(refreshMachine);
    });
    id("stems-start").addEventListener("click", async function () {
      if (!(await checkLibrary())) return;
      var wanted = selectedRoles();
      var started = await window.rx3.ask(
        "stems_start", id("playlist").value, output, wanted, true, Boolean(id("stems-overcue").checked));
      if (started) window.rx3.watchJob(drawWaveforms);
      else await checkLibrary();
    });

    // A drive that carries an export is the ordinary source, so offer it.
    window.addEventListener("rx3drive", function (event) {
      var changed=selectedDrive!==event.detail.path;
      if(changed) {
        ++forecastRequest;overcueStorage=null;drawOvercue();
        ++libraryRequest;++trackRequest;
        library=null;previewTrack="";
        id("library-count").textContent="";id("playlist").replaceChildren();id("stem-track").replaceChildren();
        id("playlist-row").hidden=true;
      }
      selectedDrive=event.detail.path;
      setOutput(selectedDrive);
      if(event.detail.music && event.detail.music.present && (!library || changed))openLibrary(selectedDrive);
    });
    window.addEventListener("rx3language", function () {
      drawWaveforms();
      drawCache();
      drawLibraryGuard();
      drawMachine();
      drawPolicy();
      drawPlaylists();
      setOutput(output);
      drawLibraryPath();
      note();
    });
  }

  async function start() {
    quality = await window.rx3.ask("stems_qualities", selectedRoles());
    machine = await window.rx3.ask("stems_runtime");
    wire();
    await checkLibrary();
    await drawCache();
    drawMachine();
    drawPolicy();
    setOutput(window.rx3.selectedDrive());
  }

  window.rx3stems = {start:start, summary:function () { return {source:library && library.source, output:output, quality:quality && quality.mode}; }};
})();
