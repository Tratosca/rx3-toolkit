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
  }

  async function forecast() {
    var picker = id("playlist");
    if (!library || !picker.value) return;
    var answer = await window.rx3.ask("stems_forecast", picker.value);
    id("forecast").textContent = answer ? window.i18n.message(answer.summary) : "";
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
    id("stems-start").disabled =
      libraryBlocked || !machine || !machine.ready || !library || !output;
  }

  function setOutput(path) {
    output = path || "";
    id("stems-output").textContent = output || t("common.none");
    note();
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

  function wire() {
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
    id("playlist").addEventListener("change", forecast);
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
    drawMachine();
    drawQuality();
    drawRoles();
    setOutput("");
  }

  window.rx3stems = {start: start};
})();
