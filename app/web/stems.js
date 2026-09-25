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
  var importTrack = "";
  var importFiles = {};
  var importReport = null;
  var trackRequest = 0;
  var roles = {vocals: true, drums: false, bass: false};

  var ROLE_KEYS = [
    ["vocals", "stems.roleVocals"],
    ["drums", "stems.roleDrums"],
    ["bass", "stems.roleBass"],
  ];

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
    id("runtime-summary").textContent = window.i18n.message(machine.summary);
    var pill = id("runtime-state");
    pill.textContent = machine.ready ? t("stems.ready") : t("stems.notReady");
    pill.className = "pill " + (machine.ready ? "on" : "off");
    id("runtime-install").textContent = machine.ready ? t("stems.reinstall") : t("stems.install");

    var picker = id("accelerator");
    picker.replaceChildren();
    for (var i = 0; i < machine.accelerators.length; i++) {
      var option = document.createElement("option");
      option.value = machine.accelerators[i].key;
      option.textContent = window.i18n.message(machine.accelerators[i].label);
      picker.append(option);
    }
    if (machine.accelerator) picker.value = machine.accelerator;
    else if (quality) picker.value = quality.accelerator;
  }

  function drawQuality() {
    if (!quality) return;
    var row = id("quality-row");
    row.replaceChildren();
    for (var i = 0; i < quality.presets.length; i++) {
      row.append(presetButton(quality.presets[i]));
    }
    var current = null;
    for (var j = 0; j < quality.presets.length; j++) {
      if (quality.presets[j].key === quality.mode) current = quality.presets[j];
    }
    id("quality-summary").textContent = current ? window.i18n.message(current.summary) : quality.model;
  }

  function presetButton(item) {
    var button = el("button", null, window.i18n.message(item.label));
    button.type = "button";
    button.setAttribute("aria-pressed", String(item.key === quality.mode));
    button.addEventListener("click", async function () {
      var answer = await window.rx3.ask("stems_choose", item.key, null);
      if (answer) {
        quality = answer;
        drawQuality();
      }
    });
    return button;
  }

  function drawRoles() {
    var row = id("roles-row");
    row.replaceChildren();
    for (var i = 0; i < ROLE_KEYS.length; i++) {
      row.append(roleBox(ROLE_KEYS[i][0], t(ROLE_KEYS[i][1])));
    }
    row.append(el("span", "dim", t("stems.vocalAlways")));
  }

  function roleBox(role, label) {
    var wrap = el("label", "row tight");
    var box = document.createElement("input");
    box.type = "checkbox";
    box.checked = roles[role];
    // The deck reads a vocal file, so a run without one produces nothing it
    // can use. The job would force it back on anyway; saying so is kinder.
    box.disabled = role === "vocals";
    box.addEventListener("change", function () {
      roles[role] = box.checked;
      if (role === "bass" && box.checked) roles.drums = true;
      if (role === "drums" && !box.checked) roles.bass = false;
      drawRoles(); forecast();
    });
    wrap.append(box, el("span", null, label));
    return wrap;
  }

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
  }

  async function forecast() {
    var picker = id("playlist");
    if (!library || !picker.value) return;
    var wanted = Object.keys(roles).filter(function (role) { return roles[role]; });
    var answer = await window.rx3.ask("stems_forecast", picker.value, wanted);
    id("forecast").textContent = answer ? window.i18n.message(answer.summary) : "";
    var table = id("stems-memory");
    table.replaceChildren();
    if (!answer) return;
    for (var track of answer.memory || []) {
      var size = track.total === null ? t("stems.sizeUnknown") :
        t("stems.trackSize", {role: window.i18n.bytes(track.perRole), total: window.i18n.bytes(track.total)});
      table.append(el("p", track.warning ? "notice" : "dim",
        track.artist + " - " + track.title + ": " + size +
        (track.warning ? " " + t("stems.memoryWarning", {limit:window.i18n.bytes(answer.memoryWarningBytes)}) : "")));
    }
  }

  function drawLibraryGuard() {
    var warning = id("library-warning");
    warning.hidden = !libraryBlocked;
    warning.firstElementChild.textContent = t("stems.libraryBusy");
    warning.lastElementChild.textContent = t("stems.recheck");
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
      : !library ? t("stems.needMusic")
      : !output ? t("stems.needOutput")
      : t("stems.longRun");
    if (id("stem-import-run")) id("stem-import-run").disabled = libraryBlocked || !importTrack || !output || !importFiles.vocals;
    id("stems-start").disabled =
      libraryBlocked || !machine || !machine.ready || !library || !output;
  }

  function setOutput(path) {
    output = path || "";
    id("stems-output").textContent = output || t("common.none");
    note();
    window.dispatchEvent(new CustomEvent("rx3stemtrack", {detail:{track:importTrack, drive:output, files:importFiles}}));
  }

  // Doing ------------------------------------------------------------------------

  async function openLibrary(path) {
    if (!path || !(await checkLibrary())) return;
    var answer = await window.rx3.ask("stems_library", path);
    if (!answer) { await checkLibrary(); return; }
    library = answer;
    id("library-path").textContent =
      answer.source + "  " + t("drive.trackCount", {count: answer.tracks});
    drawPlaylists();
    note();
  }

  async function refreshMachine() {
    machine = await window.rx3.ask("stems_runtime");
    drawMachine();
    note();
  }

  async function drawCache() {
    var state = await window.rx3.ask("stems_cache");
    if (!state) return;
    var row = id("stems-cache");
    row.replaceChildren();
    var label = el("label", null, t("stems.cacheLimit"));
    var size = el("input");
    size.type = "number"; size.min = "0"; size.max = "1024"; size.step = "0.25";
    size.value = String(state.limit / Math.pow(1024, 3));
    label.append(size);
    size.addEventListener("change", async function () {
      var value = Number(size.value);
      if (!Number.isFinite(value) || value < 0 || value > 1024) return;
      await window.rx3.ask("stems_cache", Math.round(value * Math.pow(1024, 3)), false);
      drawCache();
    });
    var clear = el("button", "btn small", t("stems.cacheClear"));
    clear.type = "button";
    clear.addEventListener("click", async function () {
      await window.rx3.ask("stems_cache", null, true); drawCache();
    });
    row.append(label, el("span", "dim", window.i18n.bytes(state.bytes)), clear);
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
    if (Array.from(picker.options).some(function (item) { return item.value === importTrack; })) picker.value = importTrack;
    await selectTrack();
  }

  async function selectTrack() {
    importTrack = id("stem-track").value;
    importReport = null;
    var selected = importTrack;
    var files = selected ? await window.rx3.ask("stems_import_assign", selected, null) || {} : {};
    if (selected !== importTrack) return;
    importFiles = files;
    drawImport(); note();
    window.dispatchEvent(new CustomEvent("rx3stemtrack", {detail:{track:importTrack, drive:output, files:importFiles}}));
  }

  async function assignImport(role, path) {
    if (!importTrack) return;
    var values = Object.assign({}, importFiles);
    if (path) values[role] = path; else delete values[role];
    var selected = importTrack;
    var result = await window.rx3.ask("stems_import_assign", selected, values);
    if (selected !== importTrack) return;
    if (result) { importFiles = result; importReport = null; drawImport(); note(); }
    window.dispatchEvent(new CustomEvent("rx3stemtrack", {detail:{track:importTrack, drive:output, files:importFiles}}));
  }

  function drawImport() {
    var slots = id("stem-import-slots");
    slots.replaceChildren();
    for (var item of ROLE_KEYS) {
      (function (role, caption) {
        var row = el("div", "row");
        var choose = el("button", "btn small", caption);
        choose.type = "button"; choose.disabled = !importTrack;
        choose.addEventListener("click", async function () {
          var selected = await window.rx3.ask("pick_files", "stem", "");
          if (selected && selected.paths.length === 1) assignImport(role, selected.paths[0]);
        });
        // Some webview backends expose the native path on dropped files. On
        // others the picker remains the supported path-preserving operation.
        row.addEventListener("dragover", function (event) { event.preventDefault(); });
        row.addEventListener("drop", function (event) {
          event.preventDefault();
          var files = event.dataTransfer.files;
          if (files.length === 1 && (files[0].pywebviewFullPath || files[0].path))
            assignImport(role, files[0].pywebviewFullPath || files[0].path);
          else id("stem-import-report").textContent = t("stems.importUsePicker");
        });
        var clear = el("button", "btn small", t("samples.clear"));
        clear.type = "button"; clear.disabled = !importFiles[role];
        clear.addEventListener("click", function () { assignImport(role, ""); });
        row.append(choose, el("span", "path", importFiles[role] || t("common.none")), clear);
        slots.append(row);
      })(item[0], t(item[1]));
    }
    var reports = [t("stems.importHeuristic")];
    if (importReport) {
      for (var role in importReport.roles) {
        var check = importReport.roles[role];
        reports.push(t("stems.importResult", {role:t(ROLE_KEYS.find(function (item) { return item[0] === role; })[1]),
          ms:window.i18n.number(check.milliseconds, {maximumFractionDigits:3}),
          head:check.trimStart, tail:check.trimEnd,
          gain:window.i18n.number(check.gainEstimate, {maximumFractionDigits:4})}));
      }
      if (importReport.residualEnergyRatio !== null)
        reports.push(t("stems.importResidual", {ratio:window.i18n.number(importReport.residualEnergyRatio, {maximumFractionDigits:4})}));
    }
    id("stem-import-report").textContent = reports.join("\n");
  }

  function wire() {
    var manual = el("section");
    manual.append(el("h2", null, t("stems.importTitle")));
    var picker = el("select"); picker.id = "stem-track";
    picker.setAttribute("aria-label", t("stems.importTrackLabel"));
    picker.addEventListener("change", selectTrack);
    var slots = el("div"); slots.id = "stem-import-slots";
    var run = el("button", "btn", t("stems.importRun"));
    run.id = "stem-import-run"; run.type = "button";
    run.addEventListener("click", async function () {
      if (!(await checkLibrary())) return;
      var selected = importTrack;
      var answer = await window.rx3.ask("stems_import_start", selected, output);
      if (answer) window.rx3.watchJob(function (job) {
        if (selected === importTrack && job.result && job.result.imported) {
          importReport = job.result.imported.checks; drawImport();
          window.dispatchEvent(new CustomEvent("rx3stemtrack", {detail:{track:importTrack, drive:output, files:importFiles}}));
        }
      });
    });
    var report = el("p", "dim"); report.id = "stem-import-report";
    report.style.whiteSpace = "pre-line";
    manual.append(picker, slots, run, report);
    id("stems-note").after(manual);
    window.rx3listen.attach(manual);
    var memory = el("div");
    memory.id = "stems-memory";
    id("forecast").after(memory);
    var cacheRow = el("div", "row");
    cacheRow.id = "stems-cache";
    id("roles-row").after(cacheRow);
    var warning = el("div", "notice");
    warning.id = "library-warning";
    warning.setAttribute("role", "alert");
    var again = el("button", "btn small");
    again.type = "button";
    again.addEventListener("click", checkLibrary);
    warning.append(el("p"), again);
    id("stems-note").before(warning);
    id("library-drive").addEventListener("click", async function () {
      var picked = await window.rx3.ask("pick_folder", "");
      if (picked) openLibrary(picked.path);
    });
    id("library-file").addEventListener("click", async function () {
      var picked = await window.rx3.ask("pick_file", "library", "");
      if (picked) openLibrary(picked.path);
    });
    id("playlist").addEventListener("change", function () { forecast(); drawTracks(); });
    id("stems-output-choose").addEventListener("click", async function () {
      var picked = await window.rx3.ask("pick_folder", output);
      if (picked && picked.path) setOutput(picked.path);
    });
    id("accelerator").addEventListener("change", async function (event) {
      var answer = await window.rx3.ask("stems_choose", null, event.target.value);
      if (answer) {
        quality = answer;
        drawQuality();
      }
    });
    id("runtime-install").addEventListener("click", async function () {
      var started = await window.rx3.ask("stems_install", id("accelerator").value);
      if (started) window.rx3.watchJob(refreshMachine);
    });
    id("stems-start").addEventListener("click", async function () {
      if (!(await checkLibrary())) return;
      var wanted = [];
      for (var role in roles) if (roles[role]) wanted.push(role);
      var started = await window.rx3.ask(
        "stems_start", id("playlist").value, output, wanted);
      if (started) window.rx3.watchJob(null);
      else await checkLibrary();
    });

    // A drive that carries an export is the ordinary source, so offer it.
    window.addEventListener("rx3drive", function (event) {
      if (event.detail.music && event.detail.music.present && !library) {
        openLibrary(event.detail.path);
      }
      if (!output) setOutput(event.detail.path);
    });
    window.addEventListener("rx3language", function () {
      drawImport();
      drawCache();
      drawLibraryGuard();
      drawMachine();
      drawQuality();
      drawRoles();
      drawPlaylists();
      setOutput(output);
      if (library) id("library-path").textContent = library.source + "  " + t("drive.trackCount", {count:library.tracks});
      note();
    });
  }

  async function start() {
    quality = await window.rx3.ask("stems_qualities");
    machine = await window.rx3.ask("stems_runtime");
    wire();
    await checkLibrary();
    await drawCache();
    drawImport();
    drawMachine();
    drawQuality();
    drawRoles();
    setOutput("");
  }

  window.rx3stems = {start: start};
})();
