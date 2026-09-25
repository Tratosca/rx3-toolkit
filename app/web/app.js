// SPDX-License-Identifier: MPL-2.0
//
// Everything the interface knows about the toolkit arrives through one object
// the shell exposes. There is no other path, which is what keeps the screens
// free of any rule about how the work is done.
//
// Progress is polled rather than pushed. The window is only asked for a file
// chooser; nothing on the Python side draws, so nothing there needs the page
// to exist before it can report where it has got to.

var t = window.i18n.t;

var state = {
  drive: null,
  report: null,
  firmware: null,
  modules: [],
  selected: [],
  key: "",
  output: "",
  logo: null,
};

var poll = null;

/** Call one operation and surface its sentence rather than its stack. */
async function ask(operation) {
  var surface = window.pywebview && window.pywebview.api;
  if (!surface) return null;
  var args = Array.prototype.slice.call(arguments, 1);
  var answer = await surface[operation].apply(surface, args);
  if (!answer) return null;
  if (answer.ok) return answer.value;
  fail(answer.errorMessage || answer.error);
  return null;
}

function fail(sentence) {
  document.getElementById("failure-text").textContent = window.i18n.message(sentence);
  document.getElementById("failure").hidden = false;
}

function el(tag, className, text) {
  var node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function bytes(count) { return window.i18n.bytes(count); }

function show(name) {
  var tabs = document.querySelectorAll("nav button");
  for (var i = 0; i < tabs.length; i++) {
    tabs[i].setAttribute("aria-selected", String(tabs[i].dataset.screen === name));
  }
  var screens = document.querySelectorAll(".screen");
  for (var j = 0; j < screens.length; j++) {
    screens[j].hidden = screens[j].id !== name;
  }
}

// The drive ------------------------------------------------------------------

function describe(report) {
  var rows = [];
  if (report.mod.installed && report.mod.unrecorded) {
    rows.push([t("drive.mod"), t("drive.modUnrecorded")]);
  } else if (report.mod.installed) {
    rows.push([t("drive.mod"), t("drive.modFirmware", {firmware: report.mod.firmware})]);
    rows.push([t("drive.modules"), report.mod.modules.join(", ") || t("common.none")]);
  } else {
    rows.push([t("drive.mod"), t("drive.modNone")]);
  }
  if (report.mod.loaded.length) rows.push([t("drive.lastRun"), report.mod.loaded.join(", ")]);
  if (report.mod.disabled.length) rows.push([t("drive.refused"), report.mod.disabled.join(", ")]);
  rows.push([t("drive.music"), report.music.present
    ? t("drive.musicCount", {tracks: t("drive.trackCount", {count:report.music.tracks}), playlists: t("drive.playlistCount", {count:report.music.playlists})})
    : t("drive.musicNone")]);
  rows.push([t("drive.banks"), report.banks.length
    ? report.banks.join(", ") + (report.activeBank
        ? " (" + t("drive.bankActive", {name: report.activeBank}) + ")" : "")
    : t("common.none")]);
  if (!report.writable) rows.push([t("drive.warning"), t("drive.readonly")]);

  var summary = document.getElementById("drive-summary");
  summary.replaceChildren();
  for (var i = 0; i < rows.length; i++) {
    summary.append(el("dt", null, rows[i][0]), el("dd", null, rows[i][1]));
  }
  summary.hidden = false;
  document.getElementById("drive-actions").hidden = false;
  document.getElementById("drive-remove").disabled = !report.mod.installed;

  var tag = document.getElementById("tag-drive");
  tag.textContent = report.mod.installed ? t("common.on") : "";
  tag.dataset.state = report.mod.installed ? "on" : "";
  tag.hidden = !report.mod.installed;
}

async function useDrive(path) {
  var report = await ask("drive_report", path);
  if (!report) return;
  state.drive = report.path;
  state.report = report;
  document.getElementById("drive-path").textContent = report.path;
  if (!state.output) setOutput(report.path);
  describe(report);
  window.dispatchEvent(new CustomEvent("rx3drive", {detail: report}));
}

// Modules and the build -------------------------------------------------------

function renderModules() {
  var list = document.getElementById("module-list");
  list.replaceChildren();
  for (var i = 0; i < state.modules.length; i++) {
    var item = state.modules[i];
    if (!item.selectable) continue;
    var li = el("li", "inner");
    var head = el("label", "row");
    var box = document.createElement("input");
    box.type = "checkbox";
    box.checked = state.selected.indexOf(item.id) >= 0;
    box.dataset.id = item.id;
    box.addEventListener("change", onToggle);
    head.append(box, el("strong", null, t("module." + item.id + ".name")));
    li.append(head, el("p", "muted", t("module." + item.id + ".description")));
    if (item.requires.length) {
      li.append(el("p", "dim", t("modules.needs", {names: item.requires.join(", ")})));
    }
    if (item.conflicts.length) {
      li.append(el("p", "dim", t("modules.clashes", {names: item.conflicts.join(", ")})));
    }
    list.append(li);
  }
  var note = document.getElementById("build-note");
  note.textContent = !state.selected.length ? t("modules.nothing")
    : state.logo && state.selected.indexOf("logo") >= 0 ? t("modules.withLogo") : "";
}

async function onToggle(event) {
  var box = event.target;
  var chosen = await ask(
    "mod_selection", state.firmware, state.selected, box.dataset.id, box.checked);
  if (!chosen) return;
  state.selected = chosen;
  renderModules();
}

async function loadModules() {
  var modules = await ask("mod_modules", state.firmware);
  if (!modules) return;
  state.modules = modules;
  var wanted = [];
  for (var i = 0; i < modules.length; i++) {
    if (modules[i].selectable && modules[i].default) wanted.push(modules[i].id);
  }
  state.selected = [];
  for (var j = 0; j < wanted.length; j++) {
    state.selected = (await ask(
      "mod_selection", state.firmware, state.selected, wanted[j], true)) || state.selected;
  }
  renderModules();
}

function setKey(path) {
  state.key = path || "";
  document.getElementById("key-path").textContent = state.key || t("common.none");
}

function setOutput(path) {
  state.output = path || "";
  document.getElementById("output-path").textContent = state.output || t("common.none");
}

async function startBuild() {
  var started = await ask(
    "mod_build", state.firmware, state.selected, state.key, state.output, state.logo);
  if (started) watchJob();
}

// The job strip ---------------------------------------------------------------

var whenDone = null;

function watchJob(onDone) {
  if (onDone) whenDone = onDone;
  if (poll) return;
  poll = setInterval(readJob, 200);
  readJob();
}

async function readJob() {
  var job = await ask("job_status");
  if (!job) return;
  var strip = document.getElementById("job");
  if (job.state === "idle") {
    strip.hidden = true;
    clearInterval(poll);
    poll = null;
    return;
  }
  strip.hidden = false;
  var running = job.state === "running";
  document.getElementById("job-message").textContent =
    running ? window.i18n.message(job.message)
    : job.state === "done" ? t("job.done")
    : job.state === "cancelled" ? t("job.cancelled") : t("job.failed");
  document.getElementById("job-detail").textContent =
    window.i18n.message(job.error) || (job.result ? describeResult(job) : running ? "" : window.i18n.message(job.message));
  document.getElementById("job-cancel").hidden = !running;
  var bar = document.getElementById("job-bar");
  bar.dataset.indeterminate = String(running && job.progress === null);
  bar.firstElementChild.style.width =
    (running ? (job.progress === null ? 40 : job.progress) : 100) + "%";
  if (!running) {
    clearInterval(poll);
    poll = null;
    var finished = whenDone;
    whenDone = null;
    if (job.state === "done" && finished) finished(job);
    if (job.kind === "mod" && job.state === "done" && state.drive) useDrive(state.drive);
  }
}

function describeResult(job) {
  if (job.kind === "stems" && job.result) {
    var errors = (job.result.errors || []).map(function (item) {
      return item.track + ": " + window.i18n.message(item.error);
    });
    return errors.concat((job.result.notices || []).map(window.i18n.message)).join("\n");
  }
  if (job.kind !== "mod" || !job.result) return "";
  return t("modules.built", {bytes: bytes(job.result.bytes), path: job.result.output});
}

// Wiring -----------------------------------------------------------------------

async function boot() {
  var firmwares = await ask("mod_firmwares");
  var select = document.getElementById("firmware");
  select.replaceChildren();
  for (var i = 0; i < (firmwares || []).length; i++) {
    var option = document.createElement("option");
    option.value = option.textContent = firmwares[i];
    select.append(option);
  }
  state.firmware = (firmwares && firmwares[0]) || null;
  if (state.firmware) await loadModules();

  var hint = await ask("mod_key_hint");
  setKey(hint ? hint.path : "");
  setOutput("");
  readJob();
}

function wire() {
  var tabs = document.querySelectorAll("nav button");
  for (var i = 0; i < tabs.length; i++) {
    tabs[i].addEventListener("click", function (event) {
      show(event.currentTarget.dataset.screen);
    });
  }

  document.getElementById("failure-close").addEventListener("click", function () {
    document.getElementById("failure").hidden = true;
  });

  document.getElementById("drive-choose").addEventListener("click", async function () {
    var chosen = await ask("pick_folder", state.drive || "");
    if (chosen && chosen.path) useDrive(chosen.path);
  });
  document.getElementById("drive-refresh").addEventListener("click", function () {
    if (state.drive) useDrive(state.drive);
  });
  document.getElementById("drive-remove").addEventListener("click", async function () {
    if (!state.drive) return;
    var removed = await ask("mod_remove", state.drive);
    if (removed) {
      fail(t("drive.removed", {count: removed.length}));
      useDrive(state.drive);
    }
  });

  document.getElementById("firmware").addEventListener("change", function (event) {
    state.firmware = event.target.value;
    loadModules();
  });
  document.getElementById("key-choose").addEventListener("click", async function () {
    var chosen = await ask("pick_file", "key", state.key || "");
    if (chosen && chosen.path) setKey(chosen.path);
  });
  document.getElementById("output-choose").addEventListener("click", async function () {
    var chosen = await ask("pick_folder", state.output || "");
    if (chosen && chosen.path) setOutput(chosen.path);
  });
  document.getElementById("build").addEventListener("click", startBuild);
  document.getElementById("job-cancel").addEventListener("click", function () {
    ask("job_cancel");
  });

  var buttons = document.querySelectorAll("#language-row button");
  for (var j = 0; j < buttons.length; j++) {
    buttons[j].addEventListener("click", function (event) {
      window.i18n.setLanguage(event.currentTarget.dataset.language);
    });
  }

  // The framing the logo screen settled on is what the build draws.
  window.addEventListener("rx3logo", function (event) {
    state.logo = event.detail;
    renderModules();
  });

  // Anything drawn from a string has to be drawn again in the new language.
  window.addEventListener("rx3language", function () {
    renderModules();
    if (state.report) describe(state.report);
    setKey(state.key);
    setOutput(state.output);
    readJob();
  });
}

// One entry point for the screens that live in their own file. Everything they
// need from Python goes through the same wrapper the rest of the page uses, so
// a failure is shown the same way wherever it comes from.
window.rx3 = {
  ask: ask, fail: fail, watchJob: watchJob, bytes: bytes,
  // The logo screen says whether its artwork would actually be built in, and
  // only the modules screen knows what is ticked.
  logoTicked: function () { return state.selected.indexOf("logo") >= 0; },
};

wire();
window.addEventListener("pywebviewready", async function () {
  await window.i18n.load();
  await boot();
  await window.rx3samples.start();
  await window.rx3logo.start();
  await window.rx3stems.start();
});
