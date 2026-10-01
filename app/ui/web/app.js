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
  profiles: {},
  key: "",
  output: "",
  logo: null,
  keySyncRange: savedKeySyncRange(),
  keySyncMode: savedKeySyncMode(),
  keyMatchRules: savedKeyMatchRules(),
  browseColumn: savedBrowseColumn(),
};

function savedBrowseColumn() {
  try {
    var value=Number(window.localStorage.getItem("rx3.browseColumn"));
    if ([7,11,13,15].indexOf(value)>=0) return value;
  } catch (_) {}
  return 13;
}

function savedKeyMatchRules() {
  try {
    var raw=window.localStorage.getItem("rx3.keyMatchRules");
    var value=Number(raw);
    if(raw !== null && Number.isInteger(value) && value>=0 && value<=15) return value & 14;
  } catch (_) {}
  return 0;
}

function savedKeySyncMode() {
  try {
    var saved=window.localStorage.getItem("rx3.keySyncMode");
    if(saved==="identical" || saved==="harmonic")return saved;
  } catch (_) {}
  return "harmonic";
}

function savedKeySyncRange() {
  try {
    var value = Number(window.localStorage.getItem("rx3.keySyncRange"));
    if (Number.isInteger(value) && value >= 1 && value <= 12) return value;
  } catch (_) { /* Storage can be unavailable in a restricted webview. */ }
  return 1;
}

var poll = null;

/** Call one operation and surface its sentence rather than its stack. */
async function ask(operation) {
  var surface = window.pywebview && window.pywebview.api;
  var args = Array.prototype.slice.call(arguments, 1);
  var screen = operation.indexOf("samples_") === 0 ? "samples"
    : operation.indexOf("logo_") === 0 ? "logo"
    : operation.indexOf("stems_") === 0 ? "stems"
    : operation === "drive_report" || operation === "mod_remove" ? "drive"
    : operation.indexOf("mod_") === 0 ? "modules" : null;
  if (screen === "modules" && !document.getElementById("installation").hidden) screen = "installation";
  // Frequent audition and polling updates have their own, quieter status.
  if (/audition|job_|_hint$|^samples_draft_store$/.test(operation)) screen = null;
  if (screen) window.ui.begin(screen);
  var error = null;
  try {
    if (!surface || typeof surface[operation] !== "function") throw new Error(t("ui.unavailable"));
    var answer = await surface[operation].apply(surface, args);
    if (!answer) return null;
    if (answer.ok) return answer.value;
    error = answer.errorMessage || answer.error;
    if (error && error.key === "error.busy") openTasks();
    if (!screen) fail(error);
    return null;
  } catch (failure) {
    error = failure.message || String(failure);
    if (!screen) fail(error);
    return null;
  } finally {
    if (screen) window.ui.end(screen, error);
  }
}

// One strip for what the operator should read now. A failure stays until it is
// dismissed; a success says so in its own colour and goes away on its own.
var toastTimer = null;

function toast(sentence, tone) {
  var strip = document.getElementById("failure");
  document.getElementById("failure-text").dataset.tone = tone === "bad" ? "error" : "success";
  window.ui.messageContent(document.getElementById("failure-text"),sentence);
  strip.dataset.tone = tone;
  strip.setAttribute("role", tone === "good" ? "status" : "alert");
  strip.hidden = false;
  clearTimeout(toastTimer);
  if (tone === "good") toastTimer = setTimeout(function () { strip.hidden = true; }, 6000);
}

function fail(sentence) { toast(sentence, "bad"); }
function done(sentence) { toast(sentence, "good"); }

// The confirmation resolves before the original destructive operation runs.
async function confirmRemoval(title, body, action) {
  return window.ui.confirm({title:title, body:body, action:action});
}

/** A path, or the sentence that stands in for one, styled as what it is. */
function setPath(node, path, empty) {
  node.replaceChildren();
  if (path) {
    var details = el("details", "path-detail");
    details.append(el("summary", null, pathName(path)), el("span", "full-path", path));
    node.append(details);
  } else node.textContent = empty;
  node.classList.toggle("unset", !path);
  node.title = path || "";
}

function el(tag, className, text) {
  var node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function pathName(path) { return String(path || "").replace(/[\\/]+$/, "").split(/[\\/]/).pop() || path; }
function decimalBytes(count) { return t("unit.mb", {value: window.i18n.number(Number(count || 0) / 1000000, {maximumFractionDigits:1})}); }
function destinationContext(node, destination, drive) {
  node.hidden = !destination || !drive || destination === drive;
  node.textContent = node.hidden ? "" : t("ui.destinationMismatch", {destination:pathName(destination), drive:pathName(drive)});
}
function refreshDriveLabel() {
  var node = document.getElementById("rail-drive");
  if (!state.drive) return;
  var icon = el("span","usb-symbol"); icon.setAttribute("aria-hidden","true");
  icon.innerHTML='<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M6 6V1h4v5M5 6h6v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2Z"/><path d="M7 2v2m2-2v2"/></svg>';
  node.replaceChildren(icon,el("strong", null, t("ui.driveSelected", {name:pathName(state.drive)})), el("small", null, t("ui.contents")));
  node.title = state.drive;
}
function bytes(count) { return window.i18n.bytes(count); }

var scrollPositions = {};
function show(name) {
  if (name === "installation") renderSummary();
  var previous = document.querySelector(".screen:not([hidden])");
  if (previous) scrollPositions[previous.id] = previous.querySelector(".screen-body").scrollTop;
  var tabs = document.querySelectorAll("nav button");
  for (var i = 0; i < tabs.length; i++) {
    var on = tabs[i].dataset.screen === name;
    tabs[i].setAttribute("aria-selected", String(on));
    tabs[i].tabIndex = on ? 0 : -1;
  }
  var screens = document.querySelectorAll(".screen");
  for (var j = 0; j < screens.length; j++) {
    screens[j].hidden = screens[j].id !== name;
  }
  document.getElementById("rail-drive").setAttribute("aria-current", name === "drive" ? "page" : "false");
  var current = document.getElementById(name);
  current.querySelector(".screen-body").scrollTop = scrollPositions[name] || 0;
  window.dispatchEvent(new CustomEvent("rx3screen", {detail:{name:name}}));
  var matchHelp=document.querySelector(".key-match-help");
  if(matchHelp) {if(name === "modules")matchHelp.refresh();else matchHelp.dismiss();}
  document.querySelectorAll("canvas[data-access]").forEach(function (canvas) {
    if(!window.rx3mock)return;
    if(canvas.closest(".screen")===current && canvas.closest("details").open)window.rx3mock.renderPadAccess(canvas,canvas.dataset.access);
    else window.rx3mock.stopPadAccess(canvas);
  });
}

// The drive ------------------------------------------------------------------

function displayModuleName(id) { return state.modules.some(function (item) { return item.id === id; }) ? moduleName(id) : id; }
function describe(report) {
  var rows = [];
  if (report.mod.installed && report.mod.unrecorded) {
    rows.push([t("drive.mod"), t("drive.modUnrecorded")]);
  } else if (report.mod.installed) {
    rows.push([t("drive.mod"), t("drive.modFirmware", {firmware: report.mod.firmware})]);
    rows.push([t("drive.modules"), report.mod.modules.map(displayModuleName).join(", ") || t("common.none")]);
  } else {
    rows.push([t("drive.mod"), t("drive.modNone")]);
  }
  rows.unshift([t("drive.music"), report.music.unreadable ? t("ui.musicUnreadable") : report.music.present
    ? t("drive.musicCount", {tracks: t("drive.trackCount", {count:report.music.tracks}), playlists: t("drive.playlistCount", {count:report.music.playlists})})
    : t("drive.musicNone") + " " + t("ui.musicExport")]);
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
  var remove = document.getElementById("drive-remove");
  remove.disabled = !report.mod.installed;
  remove.dataset.armed = "";
  remove.textContent = t("drive.removeMod");


}

async function useDrive(path) {
  if (window.rx3samples && window.rx3samples.beforeDrive && !(await window.rx3samples.beforeDrive(path))) return;
  var report = await ask("drive_report", path);
  if (!report) return;
  var firstDrive = !state.drive;
  state.drive = report.path;
  state.report = report;
  var context = document.getElementById("rail-drive");
  context.removeAttribute("data-t");
  refreshDriveLabel();
  context.title = report.path;
  var shown = document.getElementById("drive-path");
  // The placeholder is translated; a path is not, so it leaves the i18n pass.
  shown.removeAttribute("data-t");
  setPath(shown, report.path, "");
  if (!state.output) setOutput(report.path);
  describe(report);
  await selectDriveModules(report);
  renderSummary();
  if(firstDrive)show("modules");
  window.dispatchEvent(new CustomEvent("rx3drive", {detail: report}));
}

// Modules and the build -------------------------------------------------------

// Category presentation and ordering come from the module manifests.
var unfolded = {};

function moduleName(id) { return t("module." + id + ".name"); }

function selectable(id) {
  for (var i = 0; i < state.modules.length; i++) {
    if (state.modules[i].id === id) return state.modules[i].selectable;
  }
  return false;
}

/** The ticked modules that tick this one, so a box that ticked itself says why. */
function requiredBy(id) {
  var by = [];
  for (var i = 0; i < state.modules.length; i++) {
    var other = state.modules[i];
    if (other.id !== id && state.selected.indexOf(other.id) >= 0 && other.requires.indexOf(id) >= 0) {
      by.push(moduleName(other.id));
    }
  }
  return by;
}

function keyMatchIcon(colour) {
  var icon=document.createElement("img");
  icon.className="key-match-icon";
  icon.src="key-match-"+colour+".svg";
  icon.alt="";icon.width=28;icon.height=26;
  icon.setAttribute("aria-hidden","true");
  return icon;
}

function refreshKeyMatchPreview() {
  document.querySelectorAll('canvas[data-access="key-sync"]').forEach(function (canvas) { if(canvas.refreshKeyPreview)canvas.refreshKeyPreview(); });
  var help = document.querySelector(".key-match-help");
  if (help && help.refresh) help.refresh();
}

function keyMatchPreview() {
  var help=el("div","key-match-help");
  var preview=el("div","key-match-preview");
  preview.id="key-match-preview";preview.setAttribute("role","region");preview.setAttribute("aria-label",t("keyMatch.browserLabel"));
  var browser=el("canvas","key-match-browser");
  browser.setAttribute("role","img");
  browser.setAttribute("aria-label",t("keyMatch.browserLabel"));
  var transcript=el("div","visually-hidden");
  preview.append(browser,transcript);
  var request=0;
  async function show(visible) {
    var serial=++request;
    if(!visible) {
      if(window.rx3mock && window.rx3mock.stopBrowser)window.rx3mock.stopBrowser(browser);
      return;
    }
    var data=await ask("keyshift_preview",state.keySyncRange,state.keySyncMode,
      state.selected.indexOf("key-match")>=0?state.keyMatchRules:0);
    if(!data || serial!==request)return;
    transcript.replaceChildren();
    transcript.append(el("p",null,"MASTER · DECK 1 · "+data.master));
    data.rows.forEach(function (entry) {
      transcript.append(el("p",null,String(entry.number)+" · "+entry.key+(entry.colour ? " · "+t("keyMatch.match."+entry.colour):"")));
    });
    if (window.rx3mock) await window.rx3mock.renderBrowser(browser,data);
    if (serial!==request)return;

  }
  help.reveal=function () { return show(true); };
  help.dismiss=function () { return show(false); };
  help.refresh=function () {
    var guide=help.closest("details");
    if(guide && guide.open)return show(true);
  };
  help.append(preview);
  return help;
}

// Guides begin in HOT CUE and run automatically; reduced motion starts paused.
function addGuideSteps(details, canvas, prefix) {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) canvas.dataset.manualStep = "0";
  var caption = el("p", "guide-caption"), player = el("button", "guide-player");
  player.type="button";
  var indicator=el("span","guide-playback-indicator");indicator.setAttribute("aria-hidden","true");
  canvas.replaceWith(player);player.append(canvas,indicator);
  var feedbackTimer;
  canvas.updateGuideCaption = function (step) {
    var view = canvas.dataset.view === "touch" ? "touchStep" : "padStep";
    caption.textContent = t(prefix + "." + view + step);
  };
  function draw() {
    var paused = canvas.dataset.manualStep !== undefined;
    player.setAttribute("aria-label",t(paused ? "ui.guidePlay" : "ui.guidePause"));
    player.setAttribute("aria-pressed",String(paused));
    canvas.updateGuideCaption(Number(canvas.dataset.step || 0));
    if (details.open && window.rx3mock) window.rx3mock.renderPadAccess(canvas,canvas.dataset.access);
  }
  player.addEventListener("click",function () {
    var resume=canvas.dataset.manualStep !== undefined;
    if (resume) {
      canvas.dataset.startTime = canvas.dataset.manualTime || String(Number(canvas.dataset.manualStep)*5000);
      canvas.dataset.autoplay = "true";
      delete canvas.dataset.manualStep;delete canvas.dataset.manualTime;
    } else {
      canvas.dataset.manualStep = canvas.dataset.step || "0";
      canvas.dataset.manualTime = canvas.dataset.elapsed || "0";
    }
    indicator.innerHTML='<svg viewBox="0 0 24 24" width="36" height="36" fill="currentColor">'+(resume?'<path d="M7 3v18l15-9Z"/>':'<path d="M5 3h5v18H5zm9 0h5v18h-5Z"/>')+'</svg>';
    clearTimeout(feedbackTimer);indicator.classList.add("visible");
    feedbackTimer=setTimeout(function(){indicator.classList.remove("visible");},700);
    draw();
  });
  details.append(caption);
  canvas.refreshGuide = draw;
  draw();
}
function destinationGuide(screen, kind) {
  var details = el("details", "preview-disclosure"), canvas = el("canvas","sample-access-mock");
  details.append(el("summary",null,t("ui.onDeck"))); details.firstElementChild.dataset.t="ui.onDeck";
  canvas.dataset.access=kind;canvas.dataset.view="touch";canvas.setAttribute("role","img");
  setModulePreviewTabs(canvas);
  var prefix=kind === "stems" ? "stemAccess" : "sampleAccess";
  canvas.setAttribute("aria-label",t(prefix+".touchLabel"));canvas.dataset.tLabel=prefix+".touchLabel";
  details.append(canvas);addGuideSteps(details,canvas,prefix);
  details.addEventListener("toggle",function () {if(details.open){setModulePreviewTabs(canvas);window.rx3mock.renderPadAccess(canvas,kind);}else window.rx3mock.stopPadAccess(canvas);});
  document.querySelector("#"+screen+" .screen-content").append(details);
}

function moduleRelation(key, name, linked) {
  var line = el("em", "module-meta" + (linked ? " linked" : ""));
  var parts = t(key, {names: "\uFFFC"}).split("\uFFFC");
  line.append(parts[0], el("strong", null, name), parts[1] || "");
  return line;
}

function moduleTile(item) {
  var on = state.selected.indexOf(item.id) >= 0;
  var tile = el("label", "module");
  var box = document.createElement("input");
  box.type = "checkbox";
  box.setAttribute("role", "switch");
  box.checked = on;
  box.disabled = !item.selectable || Boolean(item.advanced && requiredBy(item.id).length);
  box.dataset.id = item.id;
  box.id = "module-toggle-" + item.id;
  box.addEventListener("change", onToggle);
  var text = el("span", "module-text");
  text.append(el("strong", null, moduleName(item.id)));
  var description = t("module." + item.id + ".description");
  if (["core","decoder-sleep"].includes(item.id)) {
    var explanation=el("details","module-technical");explanation.append(el("summary",null,t("ui.details")),el("p","dim",description));
  } else text.append(el("span", "muted", description));
  tile.append(text, box);
  if (!item.selectable) { box.hidden = true; text.append(el("span", "module-meta", t("ui.included"))); }
  if (explanation) {
    var wrapper = el("div", "module-config"); wrapper.append(tile, explanation); tile = wrapper;
  }
  if (item.profiles && item.profiles.length) {
    var group=el("div","module-config"), settings=el("div","module-settings");
    var label=el("label","field-label",t("modules.profile"));
    var select=document.createElement("select");
    select.id="module-profile-"+item.id;label.htmlFor=select.id;select.disabled=!on;
    var prompt=el("option",null,t("modules.chooseProfile"));prompt.value="";select.append(prompt);
    item.profiles.forEach(function(profile) {
      var option=el("option",null,profile);option.value=profile;select.append(option);
    });
    select.value=state.profiles[item.id] || "";
    select.addEventListener("change",function() {
      if(select.value)state.profiles[item.id]=select.value;else delete state.profiles[item.id];
      renderSummary();
    });
    settings.hidden=!on;settings.append(label,select);group.append(tile,settings);return group;
  }
  if (item.id === "browse-columns") {
    var group=el("div","module-config"), settings=el("div","module-settings");
    var label=el("label","field-label",t("browseColumn.field"));
    label.htmlFor="browse-column";
    var select=document.createElement("select");select.id="browse-column";select.disabled=!on;
    select.setAttribute("aria-describedby","browse-column-help");
    [[13,"bpm"],[15,"key"],[7,"artist"],[11,"time"]].forEach(function(field) {
      var option=el("option",null,t("browseColumn."+field[1]));option.value=String(field[0]);
      select.append(option);
    });
    select.value=String(state.browseColumn);
    select.addEventListener("change",function() {
      state.browseColumn=Number(select.value);
      try {window.localStorage.setItem("rx3.browseColumn",String(state.browseColumn));} catch (_) {}
    });
    var help=el("p","module-meta",t("browseColumn.help"));help.id="browse-column-help";
    settings.hidden=!on;settings.append(label,select,help);group.append(tile,settings);return group;
  }
  if (item.id === "key-sync") {
    var group = el("div", "module-config");
    var settings = el("div", "module-settings");
    var label = el("label", "field-label", t("keyshift.syncRange"));
    label.htmlFor = "key-sync-range";
    var select = document.createElement("select");
    select.id = "key-sync-range";
    select.disabled = !on;
    for (var n = 1; n <= 12; n++) {
      var option = el("option", null, t(n === 1 ? "keyshift.oneSemitone" : "keyshift.semitones", {count:n}));
      option.value = String(n);
      select.append(option);
    }
    select.value = String(state.keySyncRange);
    select.addEventListener("change", function () {
      state.keySyncRange = Number(select.value);
      try { window.localStorage.setItem("rx3.keySyncRange", String(state.keySyncRange)); } catch (_) {}
      refreshKeyMatchPreview();
    });

    var modeLabel=el("label", "field-label", t("keyshift.syncMode"));
    modeLabel.htmlFor="key-sync-mode";
    var mode=document.createElement("select");
    mode.id="key-sync-mode"; mode.disabled=!on;
    ["identical","harmonic"].forEach(function (value) {
      var option=el("option",null,t("keyshift.mode."+value));
      option.value=value; mode.append(option);
    });
    mode.value=state.keySyncMode;
    mode.addEventListener("change",function () {
      state.keySyncMode=mode.value;
      updateModeHelp();
      refreshKeyMatchPreview();
      try { window.localStorage.setItem("rx3.keySyncMode",mode.value); } catch (_) {}
    });
    var modeHelp=el("p","module-meta");
    modeHelp.id="key-sync-mode-help";
    modeHelp.setAttribute("aria-live","polite");
    function updateModeHelp() {
      modeHelp.textContent=t(state.keySyncMode==="identical" ? "keyshift.syncHelp" : "keyshift.modeHelp");
    }
    updateModeHelp();
    mode.setAttribute("aria-describedby",modeHelp.id);

    settings.append(modeLabel,mode,modeHelp,label,select);
    settings.hidden=!on;
    group.append(tile, settings, moduleTutorial(item));
    return group;
  }
  if (item.id === "key-match") {
    var group = el("div", "module-config");
    var settings = el("div", "module-settings");
    var matchSettings=el("div","key-match-settings");
    var matchHeading=el("div","key-match-heading");

    matchHeading.hidden=true;
    matchSettings.append(matchHeading);
    var native=el("label","key-match-rule key-match-native");
    var nativeCheck=document.createElement("input");
    nativeCheck.type="checkbox";nativeCheck.checked=true;nativeCheck.disabled=true;
    native.append(nativeCheck,keyMatchIcon("green"),el("span",null,t("keyMatch.native")));
    matchSettings.append(native);
    [[2,"boostTwo","yellow"],[4,"boostSeven","orange"],[8,"four","red"]].forEach(function(rule) {
      var label=el("label","key-match-rule");
      var option=document.createElement("input");
      option.id="key-match-rule-"+rule[0];
      option.type="checkbox"; option.checked=!!(state.keyMatchRules&rule[0]); option.disabled=!on;
      option.addEventListener("change",function() {
        state.keyMatchRules=option.checked ? state.keyMatchRules|rule[0] : state.keyMatchRules&~rule[0];
        try {window.localStorage.setItem("rx3.keyMatchRules",String(state.keyMatchRules));} catch (_) {}
        updateWarnings();refreshKeyMatchPreview();
      });
      var icon=keyMatchIcon(rule[2]);
      label.append(option,icon,el("span",null,t("keyMatch."+rule[1]))); matchSettings.append(label);
    });
    var caution=el("p","module-meta",t("keyMatch.rules"));
    var experimental=el("p","module-meta notice",t("keyMatch.help"));
    function updateWarnings() {
      caution.hidden=!state.keyMatchRules;
      experimental.hidden=!(state.keyMatchRules&8);
    }
    updateWarnings();matchSettings.append(caution,experimental);
    settings.append(matchSettings);
    settings.hidden=!on;
    var guide=el("details","module-guide harmonic-guide");
    guide.id="module-tutorial-key-match";
    guide.append(el("summary",null,t("ui.onDeck")),el("p",null,t("tutorial.harmonicHelp")),keyMatchPreview());
    var link=el("a","module-meta linked",t("keyMatch.guide"));
    link.href="https://mixedinkey.com/book/use-advanced-harmonic-mixing-techniques/";
    link.target="_blank";link.rel="noopener noreferrer";guide.append(link);
    guide.addEventListener("toggle",function () {var help=guide.querySelector(".key-match-help");if(guide.open)help.reveal();else help.dismiss();});
    group.append(tile, settings, guide);
    return group;
  }
  if (["samples","stems","now-playing","keyshift"].indexOf(item.id)>=0) {
    var group=el("div","module-config");group.append(tile,moduleTutorial(item));return group;
  }
  return tile;
}

var moduleGuides = {};
function setModulePreviewTabs(canvas) {
  var kind=canvas.dataset.access;
  canvas.dataset.keyTab=state.selected.indexOf("keyshift")>=0 || kind==="keyshift" || kind==="key-sync" ? "1":"0";
  canvas.dataset.stemsTab=state.selected.indexOf("stems")>=0 || kind==="stems" ? "1":"0";
  canvas.dataset.samplesTab=state.selected.indexOf("samples")>=0 || kind==="samples" ? "1":"0";
}
function moduleTutorial(item) {
    var locale=window.i18n.current ? window.i18n.current() : "";
    if(moduleGuides[item.id] && moduleGuides[item.id].dataset.locale===locale) return moduleGuides[item.id];
    var details=el("details","module-guide");
    details.id="module-tutorial-"+item.id;details.dataset.locale=locale;
    details.append(el("summary",null,t(item.id === "samples" ? "sampleAccess.title" : item.id === "stems" ? "stemAccess.title" : "nowPlaying.usage")));
    if (item.id === "keyshift" || item.id === "key-sync") {
      var prefix=item.id === "keyshift" ? "keyShiftAccess" : "keySyncAccess";
      details.firstElementChild.textContent=t("ui.onDeck");
      var canvas=el("canvas","sample-access-mock");
      canvas.dataset.access=item.id;canvas.dataset.view="touch";
      setModulePreviewTabs(canvas);
      canvas.setAttribute("role","img");canvas.setAttribute("aria-label",t(prefix+".label"));
      details.append(canvas);addGuideSteps(details,canvas,prefix);
      var request=0;
      canvas.refreshKeyPreview=async function () {
        if(!details.open)return;
        var serial=++request;
        if(item.id === "key-sync") {
          var data=await ask("keyshift_preview",state.keySyncRange,state.keySyncMode,
            state.selected.indexOf("key-match")>=0?state.keyMatchRules:0);
          if(!data || serial!==request || !details.open)return;
          canvas.keyPreview=data;canvas.dataset.syncMode=state.keySyncMode;
        }
        if(window.rx3mock)window.rx3mock.renderPadAccess(canvas,item.id);
      };
      details.addEventListener("toggle",function () {
        if(details.open)canvas.refreshKeyPreview();
        else {request++;if(window.rx3mock)window.rx3mock.stopPadAccess(canvas);}
      });
    } else if (item.id === "samples" || item.id === "stems") {
      var prefix=item.id === "stems" ? "stemAccess" : "sampleAccess";
      var canvas=el("canvas","sample-access-mock");
      canvas.setAttribute("role","img");
      canvas.dataset.access=item.id;
      setModulePreviewTabs(canvas);
      canvas.setAttribute("aria-label",t(prefix+".label"));
      if (item.id === "samples") {
        canvas.dataset.view="touch";
        canvas.setAttribute("aria-label",t(prefix+".touchLabel"));
        details.append(canvas);
      } else {
      var views=el("div","row tight");
      views.setAttribute("role","group");
      ["pads","touch"].forEach(function (view) {
        var choice=el("button","btn small",t(prefix+"."+view));
        choice.type="button";choice.dataset.view=view;
        choice.setAttribute("aria-pressed",String(view==="pads"));
        choice.addEventListener("click",function () {
          canvas.dataset.view=view;
          canvas.setAttribute("aria-label",t(prefix+(view==="touch"?".touchLabel":".label")));
          Array.prototype.forEach.call(views.children,function (button) {
            button.setAttribute("aria-pressed",String(button===choice));
          });
          if(window.rx3mock)window.rx3mock.renderPadAccess(canvas,canvas.dataset.access);
        });
        views.append(choice);
      });
      details.append(views,canvas);
      }
      addGuideSteps(details,canvas,prefix);
      details.addEventListener("toggle",function () {
        if(window.rx3mock) {
          if(details.open)window.rx3mock.renderPadAccess(canvas,canvas.dataset.access);
          else window.rx3mock.stopPadAccess(canvas);
        }
      });
    } else {
      details.open=false;
      var steps=el("ol","module-steps");
      steps.append(el("li",null,t("nowPlaying.connect")));
      var receiver=el("li",null,t("nowPlaying.receive"));
      receiver.append(el("code","module-command","python3 scripts/now_playing.py"));
      steps.append(receiver,el("li",null,t("nowPlaying.overlay")));
      details.append(steps,el("p",null,t("nowPlaying.integration")));
    }
    details.open=false;
    moduleGuides[item.id]=details;
    return details;
}

function renderModules() {
  window.ui.preserve(renderModuleContent);
  document.querySelectorAll('canvas[data-access]').forEach(function (canvas) {
    setModulePreviewTabs(canvas);
    if(canvas.closest("details") && canvas.closest("details").open && window.rx3mock)
      window.rx3mock.renderPadAccess(canvas,canvas.dataset.access);
  });
  document.querySelectorAll('canvas[data-access="key-sync"]').forEach(function (canvas) {
    if(canvas.refreshKeyPreview)canvas.refreshKeyPreview();
  });
}
function renderModuleContent() {
  var list = document.getElementById("module-list");
  var performanceTradeoff = document.getElementById("modules-performance-tradeoff");
  performanceTradeoff.hidden = state.selected.indexOf("keyshift") < 0 && state.selected.indexOf("stems") < 0;
  var oldPreview=document.querySelector(".key-match-help");
  if(oldPreview && oldPreview.dismiss) oldPreview.dismiss();
  list.replaceChildren();
  var categories = [];
  state.modules.forEach(function (item) {
    if (item.selectable && !item.advanced && item.categoryUi && !categories.some(function (category) { return category.id === item.category; })) {
      categories.push(item.categoryUi);
    }
  });
  categories.sort(function (a, b) { return a.order - b.order || a.id.localeCompare(b.id); });
  for (var c = 0; c < categories.length; c++) {
    var metadata = categories[c];
    var category = metadata.id;
    var members = state.modules.filter(function (item) {
      return item.selectable && !item.advanced && item.category === category;
    });
    if (!members.length) continue;
    var ticked = members.filter(function (item) { return state.selected.indexOf(item.id) >= 0; }).length;

    var section = el(metadata.collapsed ? "details" : "section", "category");
    section.dataset.category = category;
    var head = el(section.tagName === "DETAILS" ? "summary" : "header", "category-head");
    var titles = el("div");
    titles.append(el("h2", null, t("modules.category." + category)));
    if (metadata.description) titles.append(el("p", "dim", t("modules.category." + category + "Hint")));
    head.append(titles);
    section.append(head);
    if (section.tagName === "DETAILS") {
      section.open = Boolean(ticked) || Boolean(unfolded[category]);
      section.addEventListener("toggle", function (event) {
        unfolded[event.currentTarget.dataset.category] = event.currentTarget.open;
      });
    }

    var grid = el("div", "module-grid");
    for (var i = 0; i < members.length; i++) grid.append(moduleTile(members[i]));
    section.append(grid);
    list.append(section);
  }
  renderSummary();
}

function renderPreparationSummary() {
  var rows = [[t("nav.logo"), state.selected.indexOf("logo") < 0 ? t("install.moduleOff") : state.logo ? pathName(state.logo.path) + " · " + t("install.logoReady") : t("install.logoEmpty")]];
  if (state.report) rows.push([t("drive.banks"), state.report.banks.join(", ") || t("common.none")]);
  var samples = window.rx3samples && window.rx3samples.summary ? window.rx3samples.summary() : null;
  rows.push([t("nav.samples"), samples && samples.count ? t("install.bank", {name:samples.name, count:samples.count}) + " · " + t(samples.saved ? "install.saved" : "install.unsaved") : t("install.noBank")]);
  if (samples && samples.drive) rows.push([t("install.samplesDrive"), samples.drive]);
  var stems = window.rx3stems && window.rx3stems.summary ? window.rx3stems.summary() : null;
  rows.push([t("nav.stems"), stems && stems.source ? stems.source : t("install.noSource")]);
  if (stems && stems.output) rows.push([t("install.stemsOutput"), stems.output]);
  if (stems && stems.quality) rows.push([t("stems.quality"), t("ui.quality." + stems.quality)]);
  var target = document.getElementById("installation-assets");
  target.replaceChildren();
  rows.forEach(function (row) { target.append(el("dt", null, row[0]), el("dd", "path", row[1])); });
}

function renderSummary() {
  // In the list's own order, not in the order the switches were pressed.
  var selected = state.modules.filter(function (item) {
    return item.selectable && state.selected.indexOf(item.id) >= 0;
  });
  var names = state.modules.filter(function (item) { return state.selected.indexOf(item.id) >= 0; })
    .map(function (item) { return moduleName(item.id); });
  document.getElementById("summary-count").textContent = t("modules.selectedCount", {count: names.length});
  var chips = document.getElementById("summary-chips");
  chips.replaceChildren();
  for (var i = 0; i < names.length; i++) chips.append(el("li", null, names[i]));

  var note = document.getElementById("build-note");
  var missingProfile=selected.some(function(item) {
    return item.profiles && item.profiles.length && !state.profiles[item.id];
  });
  note.textContent = !selected.length ? t("modules.nothing")
    : !state.output ? t("modules.needOutput")
    : missingProfile ? t("modules.chooseProfile")
    : state.logo && state.selected.indexOf("logo") >= 0 ? t("modules.withLogo") : "";
  document.getElementById("installation-confirm").disabled = !selected.length || !state.output || missingProfile;
  document.getElementById("installation-confirm").textContent = t(state.key ? "modules.build" : "install.continue");
  document.getElementById("installation-step").textContent = state.key ? t("install.ready") : t("install.first");
  renderPreparationSummary();
  destinationContext(document.getElementById("output-mismatch"),state.output,state.drive);
  window.dispatchEvent(new CustomEvent("rx3selection", {detail:{selected:state.selected,report:state.report}}));
}

async function onToggle(event) {
  var box = event.target;
  var chosen = await ask(
    "mod_selection", state.firmware, state.selected, box.dataset.id, box.checked);
  if (!chosen) { box.checked = state.selected.indexOf(box.dataset.id) >= 0; return; }
  state.selected = chosen;
  renderModules();
}

async function loadModules() {
  var modules = await ask("mod_modules", state.firmware);
  if (!modules) return;
  state.modules = modules;
  Object.keys(state.profiles).forEach(function(id) {
    var item=modules.find(function(module){return module.id===id;});
    if(!item || item.profiles.indexOf(state.profiles[id])<0)delete state.profiles[id];
  });
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

async function selectDriveModules(report) {
  // The build manifest records what is installed; old runtime logs can refer
  // to a previous image and must not supply the checkbox selection.
  if (!report.mod || report.mod.unrecorded) return;
  if (!report.mod.installed) {
    state.selected = [];
    renderModules();
    return;
  }
  var wanted = report.mod.modules || [], chosen = [];
  for (var i = 0; i < wanted.length; i++) {
    if (!selectable(wanted[i])) continue;
    var next = await ask("mod_selection", state.firmware, chosen, wanted[i], true);
    if (!next) return;
    chosen = next;
  }
  state.selected = chosen;
  renderModules();
}

var keySource = null;

function setKey(path) {
  state.key = path || "";
  setPath(document.getElementById("key-path"), state.key, t("common.none"));
  var kept = keySource && keySource.kept && state.key === keySource.path;
  document.getElementById("key-state").textContent = state.key ? t(kept ? "ui.keyAvailable" : "ui.fileSelected") : t("modules.needKey");
  document.getElementById("key-recover").hidden = !state.key;
  document.getElementById("key-fetch").hidden = Boolean(state.key);
  var forget = document.getElementById("key-forget");
  forget.hidden = !kept;
  forget.dataset.armed = "";
  forget.textContent = t("modules.keyForget");
  document.getElementById("key-note").textContent = state.key ? ""
    : keySource ? t("modules.keyFetchNote", {bytes: decimalBytes(keySource.bytes)}) : "";
  renderSummary();
}

// The terms come before any download, every time one is about to start. The
// box unlocks only once the text has been scrolled to its end; Python checks
// the answer again, so the page is not the only lock.
function openTerms() {
  var dialog = document.getElementById("terms");
  document.getElementById("terms-size").textContent = keySource ? t("modules.keyFetchNote", {bytes:decimalBytes(keySource.bytes)}) : "";
  var body = document.getElementById("terms-body");
  var box = document.getElementById("terms-accept");
  box.checked = false;
  box.disabled = true;
  document.getElementById("terms-download").disabled = true;
  document.getElementById("terms-hint").hidden = false;
  if (!dialog.open) dialog.showModal();
  body.focus({preventScroll: true});
  // Measured once the dialog has been laid out: before that every height is
  // zero, which reads as "already at the end" and would unlock the box.
  requestAnimationFrame(function () {
    body.scrollTop = 0;
    termsScrolled();
  });
}

function termsScrolled() {
  var body = document.getElementById("terms-body");
  if (!body.scrollHeight || !body.clientHeight) return;
  // Two pixels of slack: fractional scaling rarely lands exactly on the end.
  if (body.scrollTop + body.clientHeight < body.scrollHeight - 2) return;
  document.getElementById("terms-accept").disabled = false;
  document.getElementById("terms-hint").hidden = true;
}

async function fetchKey() {
  var accepted = document.getElementById("terms-accept").checked;
  document.getElementById("terms").close();
  if (!accepted) return;
  var started = await ask("mod_key_fetch", true);
  if (!started) return;
  if (!started.started) { await useKeySource(); openInstallation(); return; }
  watchJob(async function () { await useKeySource(); openInstallation(); });
}

async function forgetKey(event) {
  if (!(await confirmRemoval(t("ui.forgetKeyTitle"), t("ui.forgetKeyBody"), t("modules.keyForget")))) return;
  var answer = await ask("mod_key_forget");
  if (!answer) return;
  await useKeySource();
  done(t("modules.keyForgotten"));
}

async function useKeySource() {
  keySource = await ask("mod_key_hint");
  setKey(keySource ? keySource.path : "");
}

function setOutput(path) {
  state.output = path || "";
  setPath(document.getElementById("output-path"), state.output, t("common.none"));
  renderSummary();
}

function openInstallation() {
  renderSummary();
  show("installation");
  document.getElementById(state.output ? "installation-confirm" : "output-choose").focus();
}
async function startBuild() {
  if (!state.output) return openInstallation();
  if (!state.key) return openTerms();
  var button = document.getElementById("installation-confirm");
  button.disabled = true;
  var profiles={};
  state.selected.forEach(function(id) {if(state.profiles[id])profiles[id]=state.profiles[id];});
  var started = await ask(
    "mod_build", state.firmware, state.selected.filter(selectable), state.key, state.output, state.logo, state.keySyncRange, state.keySyncMode, state.keyMatchRules, state.browseColumn, profiles);
  renderSummary();
  if (started) watchJob();
}

// The job strip ---------------------------------------------------------------

var whenDone = null;
var jobDismissed = false;
var completedJob = "";
function openTasks() {
  var dialog=document.getElementById("tasks-dialog");
  document.getElementById("tasks-content").append(document.getElementById("job"));
  if(!dialog.open)dialog.showModal();
  if(!poll)poll=setInterval(readJob,200);
  readJob();
}
function restoreJobStrip() {
  var strip=document.getElementById("job");
  document.getElementById("job-anchor").after(strip);
  strip.hidden=jobDismissed || strip.dataset.state==="idle";
}


function watchJob(onDone) {
  if (onDone) whenDone = onDone;
  jobDismissed = false;
  if (poll) return;
  poll = setInterval(readJob, 200);
  readJob();
}

async function readJob() {
  var job = await ask("job_status");
  if (!job) return;
  var strip = document.getElementById("job");
  document.getElementById("tasks-count").hidden=job.state!=="running";
  document.getElementById("tasks-running").hidden=job.state!=="running";
  document.getElementById("tasks-open").dataset.running=String(job.state==="running");
  document.getElementById("tasks-empty").hidden=job.state!=="idle";
  if (job.state === "idle") {
    strip.hidden = true;strip.dataset.state="idle";
    clearInterval(poll);
    poll = null;
    return;
  }
  strip.hidden = jobDismissed && !document.getElementById("tasks-dialog").open;
  var running = job.state === "running";
  var jobMessage =
    running ? window.i18n.message(job.message)
    : job.state === "done" ? t("job.done")
    : job.state === "cancelled" ? t("job.cancelled") : t("job.failed");
  if (job.kind === "stems" && job.state === "done" && job.result) {
    var ready = (Number.isFinite(job.result.migrated) ? job.result.migrated : job.result.imported ? 1 : (job.result.waveforms || job.result.results || []).length), failed = (job.result.errors || []).length;
    jobMessage = t("stems.resultReady", {count:ready}) + (failed ? " · " + t("stems.resultFailed", {count:failed}) : "");
  }
  if (job.kind === "key" && job.state === "done") jobMessage = t("modules.keyFetched");
  if (job.kind === "key" && job.state === "cancelled") jobMessage = t("ui.keyCancelled");
  if (document.getElementById("job-message").textContent !== jobMessage) document.getElementById("job-message").textContent = jobMessage;
  document.getElementById("job-detail").textContent =
    window.i18n.primary(job.error) || (job.result ? describeResult(job) : running ? "" : window.i18n.message(job.message));
  if (running && job.kind === "stems" && job.detail) {
    document.getElementById("job-detail").textContent =
      job.detail.migration ? t("stems.migrationProgress", {position:job.detail.position,total:job.detail.total,percent:window.i18n.number(job.detail.trackProgress || 0)}) :
      (job.detail.current || "") + " - " + window.i18n.message(job.detail.stage) +
      " " + window.i18n.number(job.detail.trackProgress || 0) + "%";
  }
  var diagnostic = document.getElementById("job-diagnostics");
  diagnostic.textContent = window.i18n.message(job.error);
  if (job.result) {
    diagnostic.textContent += "\n" + describeResult(job);
    if (job.kind === "key") diagnostic.textContent += "\n" + job.result.path;
    if (job.kind === "mod") diagnostic.textContent += "\n" + bytes(job.result.bytes);
  }
  document.getElementById("job-details").hidden = !diagnostic.textContent.trim();
  if (job.kind === "stems" && !running) document.getElementById("job-detail").textContent = "";
  if (running && job.kind === "key" && job.detail) document.getElementById("job-detail").textContent = job.progress !== null && job.detail.total ? t("ui.transfer", {done:decimalBytes(job.detail.done),total:decimalBytes(job.detail.total)}) : "";
  var retry = document.getElementById("job-retry"); retry.hidden = job.kind !== "key" || running || job.state === "done";
  var next = document.getElementById("job-next"); next.hidden = running || job.state !== "done" || !["key","stems"].includes(job.kind);
  next.textContent = t(job.kind === "key" ? "install.resume" : "ui.listenStems"); next.dataset.destination = job.kind;
  document.getElementById("job-cancel").hidden = !running;
  strip.dataset.state = job.state;
  var bar = document.getElementById("job-bar");
  bar.hidden = !running && job.state !== "done";
  if (running && job.progress === null) bar.removeAttribute("aria-valuenow");
  else bar.setAttribute("aria-valuenow", String(running ? job.progress : 100));
  bar.dataset.indeterminate = String(running && job.progress === null);
  bar.firstElementChild.style.width =
    (running ? (job.progress === null ? 40 : job.progress) : 100) + "%";
  if (!running) {
    clearInterval(poll);
    poll = null;
    var completion=JSON.stringify([job.startedAt,job.kind,job.state]);
    if(completedJob===completion)return;
    completedJob=completion;
    var finished = whenDone;
    whenDone = null;
    if (job.state === "done" && finished) finished(job);
    window.dispatchEvent(new CustomEvent("rx3jobfinished", {detail: job}));
    if (job.kind === "mod" && job.state === "done" && state.drive) useDrive(state.drive);
  }
}

function describeResult(job) {
  if (job.kind === "stems" && job.result) {
    var lines = [];
    var ready = (Number.isFinite(job.result.migrated) ? job.result.migrated : job.result.imported ? 1 : (job.result.waveforms || job.result.results || []).length), failed = (job.result.errors || []).length;
    if (ready) lines.push(t(job.result.waveforms ? "stems.waveResultReady" : "stems.resultReady", {count: ready}));
    if (failed) lines.push(t("stems.resultFailed", {count: failed}));
    var errors = (job.result.errors || []).map(function (item) {
      return t("stems.trackNotice", {name: item.track, detail: item.error});
    });
    return lines.concat(errors, (job.result.notices || []).map(window.i18n.message)).join("\n");
  }
  if (job.kind === "key" && job.result) return t("modules.keyFetched", {path: job.result.path});
  if (job.kind !== "mod" || !job.result) return "";
  return t("modules.built", {bytes: bytes(job.result.bytes), path: job.result.output});
}

// Wiring -----------------------------------------------------------------------

async function boot() {
  var firmwares = await ask("mod_firmwares");
  // Both supported versions share the same modules and GUI addresses.
  // Keep one build target internally; the UI shows compatibility, not a choice.
  document.getElementById("firmware").textContent = (firmwares || []).join(" / ");
  state.firmware = (firmwares && firmwares[0]) || null;
  if (state.firmware) await loadModules();

  await useKeySource();
  setOutput("");
  await readJob();

}

function wire() {
  var tabs = Array.prototype.slice.call(document.querySelectorAll("nav button"));
  for (var i = 0; i < tabs.length; i++) {
    tabs[i].addEventListener("click", function (event) {
      show(event.currentTarget.dataset.screen);
    });
  }
  // A vertical tab list: the arrows move between tabs, Home and End jump.
  document.querySelector("nav").addEventListener("keydown", function (event) {
    var at = tabs.indexOf(document.activeElement);
    if (at < 0) return;
    var to = event.key === "ArrowDown" ? (at + 1) % tabs.length
      : event.key === "ArrowUp" ? (at - 1 + tabs.length) % tabs.length
      : event.key === "Home" ? 0
      : event.key === "End" ? tabs.length - 1 : -1;
    if (to < 0) return;
    event.preventDefault();
    tabs[to].focus();
    show(tabs[to].dataset.screen);
  });

  document.getElementById("failure-close").addEventListener("click", function () {
    document.getElementById("failure").hidden = true;
  });

  async function chooseDrive() {
    var chosen = await ask("pick_folder", state.drive || "");
    if (chosen && chosen.path) useDrive(chosen.path);
  }
  document.getElementById("drive-choose").addEventListener("click", chooseDrive);
  document.getElementById("samples-choose-drive").addEventListener("click", function () {
    show("drive");
    document.getElementById("drive-choose").focus();
  });
  document.getElementById("drive-refresh").addEventListener("click", function () {
    if (state.drive) useDrive(state.drive);
  });
  document.getElementById("drive-remove").addEventListener("click", async function (event) {
    if (!state.drive) return;
    if (!(await confirmRemoval(t("ui.removeDriveTitle"), t("ui.removeDriveBody", {path:state.drive}), t("drive.removeMod")))) return;
    var removed = await ask("mod_remove", state.drive);
    if (removed) {
      done(t("drive.removed", {count: removed.length}));
      useDrive(state.drive);
    }
  });

  document.getElementById("key-choose").addEventListener("click", async function () {
    var chosen = await ask("pick_file", "key", state.key || "");
    if (chosen && chosen.path) setKey(chosen.path);
  });
  document.getElementById("key-fetch").addEventListener("click", openTerms);
  document.getElementById("key-recover").addEventListener("click", openTerms);
  document.getElementById("job-retry").addEventListener("click", function () {document.getElementById("tasks-dialog").close();openTerms();});
  document.getElementById("job-next").addEventListener("click", function (event) {
    document.getElementById("tasks-dialog").close();
    if (event.currentTarget.dataset.destination === "key") { openInstallation(); }
    else { show("stems"); document.getElementById("stems-listen").scrollIntoView({block:"nearest"}); document.getElementById("stem-track").focus(); }
  });
  document.getElementById("installation-confirm").addEventListener("click", startBuild);
  document.getElementById("key-forget").addEventListener("click", forgetKey);
  document.getElementById("terms-body").addEventListener("scroll", termsScrolled);
  document.getElementById("terms-accept").addEventListener("change", function (event) {
    document.getElementById("terms-download").disabled = !event.target.checked;
  });
  document.getElementById("terms-cancel").addEventListener("click", function () {
    document.getElementById("terms").close();
  });
  document.getElementById("terms-download").addEventListener("click", fetchKey);
  document.getElementById("output-choose").addEventListener("click", async function () {
    var chosen = await ask("pick_folder", state.output || "");
    if (chosen && chosen.path) setOutput(chosen.path);
  });
  document.getElementById("tasks-open").addEventListener("click",openTasks);
  document.getElementById("tasks-close").addEventListener("click",function(){document.getElementById("tasks-dialog").close();});
  document.getElementById("tasks-dialog").addEventListener("close",restoreJobStrip);
  document.getElementById("job-close").addEventListener("click", function () {
    jobDismissed = true;
    if(document.getElementById("tasks-dialog").open)document.getElementById("tasks-dialog").close();
    document.getElementById("job").hidden = true;
  });
  document.getElementById("job-cancel").addEventListener("click", async function (event) {
    var button = event.currentTarget;
    button.disabled = true;
    var accepted = await ask("job_cancel");
    button.disabled = false;
    if (accepted !== null) done(t(accepted ? "ui.cancelRequested" : "ui.cancelUnavailable"));
  });

  var buttons = document.querySelectorAll("#language-row button, #terms-language button");
  for (var j = 0; j < buttons.length; j++) {
    buttons[j].addEventListener("click", function (event) {
      window.i18n.setLanguage(event.currentTarget.dataset.language);
    });
  }
  function markLanguage() {
    for (var k = 0; k < buttons.length; k++) {
      buttons[k].setAttribute("aria-pressed",
        String(buttons[k].dataset.language === window.i18n.current()));
    }
  }

  // The framing the logo screen settled on is what the build draws.
  window.addEventListener("rx3logo", async function (event) {
    var previous = state.logo;
    state.logo = event.detail;
    if (state.logo && (!previous || previous.path !== state.logo.path) && state.selected.indexOf("logo") < 0) await window.rx3.tick("logo");
    renderModules();
  });

  // Anything drawn from a string has to be drawn again in the new language.
  window.addEventListener("rx3language", function () {
    markLanguage();
    document.querySelectorAll("canvas[data-access]").forEach(function (canvas) {if(canvas.refreshGuide)canvas.refreshGuide();});
    renderModules();
    if (state.report) { describe(state.report); refreshDriveLabel(); }
    if (document.getElementById("terms").open) openTerms();
    setKey(state.key);
    setOutput(state.output);
    readJob();
  });
}

// One entry point for the screens that live in their own file. Everything they
// need from Python goes through the same wrapper the rest of the page uses, so
// a failure is shown the same way wherever it comes from.
window.rx3 = {
  ask: ask, fail: fail, done: done, confirm: confirmRemoval, setPath: setPath,
  watchJob: watchJob, bytes: bytes, pathName:pathName, destinationContext:destinationContext,
  useDrive: useDrive,
  showDrive: function () { show("drive"); },
  selectedDrive: function () { return state.drive; },
  // The logo screen says whether its artwork would actually be built in, and
  // only the modules screen knows what is ticked.
  logoTicked: function () { return state.selected.indexOf("logo") >= 0; },
  // Tick a module from another screen, through the same rules as its switch.
  tick: async function (id) {
    var chosen = await ask("mod_selection", state.firmware, state.selected, id, true);
    if (!chosen) return false;
    state.selected = chosen;
    renderModules();
    return true;
  },
};

function startupText(failed) {
  var french = /^fr/i.test(navigator.language || "");
  return failed ? (french ? "L’application n’a pas pu terminer le chargement. Cliquez sur Réessayer." : "The app could not finish loading. Click Try again.") : (french ? "Ouverture de l’application…" : "Opening the app…");
}
document.getElementById("connection-message").textContent = startupText(false);
document.getElementById("connection-retry").textContent = /^fr/i.test(navigator.language || "") ? "Réessayer" : "Try again";
wire();
var starting = false, ready = false;
async function connect() {
  if (starting || ready) return;
  starting = true;
  var panel = document.getElementById("connection");
  var retry = document.getElementById("connection-retry");
  retry.hidden = true;
  try {
    if (!window.pywebview || !window.pywebview.api) throw new Error("bridge unavailable");
    await window.i18n.load();
    await boot();
    await window.rx3samples.start();
    await window.rx3logo.start();
    await window.rx3stems.start();

    show("drive");
    ready = true;
    panel.hidden = true;
  } catch (_) {
    document.getElementById("connection-message").textContent = t("ui.unavailable") === "ui.unavailable" ? startupText(true) : t("ui.unavailable");
    retry.hidden = false;
    panel.hidden = false;
  } finally { starting = false; }
}
document.getElementById("connection-retry").addEventListener("click", connect);
window.addEventListener("pywebviewready", connect);
// A missing transport must not leave a blank page or an endless spinner.
setTimeout(function () {
  if (!ready && !starting) {
    var message = document.getElementById("connection-message");
    message.textContent = t("ui.unavailable") === "ui.unavailable" ? startupText(true) : t("ui.unavailable");
    document.getElementById("connection-retry").hidden = false;
  }
}, 8000);
