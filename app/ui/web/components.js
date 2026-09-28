// SPDX-License-Identifier: MPL-2.0
// Presentation helpers only. Python remains the authority for product state.
(function () {
  var preference = "system", media = window.matchMedia("(prefers-color-scheme: dark)");
  try { preference = localStorage.getItem("rx3.theme") || "system"; } catch (_) {}
  if (!["system", "light", "dark"].includes(preference)) preference = "system";
  function theme(value) {
    preference = value;
    document.documentElement.dataset.theme = value === "system" ? (media.matches ? "dark" : "light") : value;
    document.documentElement.dataset.appearance = value;
    document.querySelectorAll("[data-theme-choice]").forEach(function (button) {
      button.setAttribute("aria-pressed", String(button.dataset.themeChoice === value));
    });
    window.dispatchEvent(new CustomEvent("rx3theme"));
  }
  theme(preference);
  media.addEventListener("change", function () { if (preference === "system") theme(preference); });
  function t(key, params) { return window.i18n.t(key, params); }
  function preserve(action) {
    var active = document.activeElement;
    var key = active && (active.id || active.dataset.focus);
    var selection = active && typeof active.selectionStart === "number" ? [active.selectionStart, active.selectionEnd] : null;
    action();
    if (!key || document.contains(active)) return;
    var next = document.getElementById(key) || Array.from(document.querySelectorAll("[data-focus]")).find(function (node) { return node.dataset.focus === key; });
    if (next) {
      next.focus({preventScroll: true});
      if (selection && next.setSelectionRange) next.setSelectionRange(selection[0], selection[1]);
    }
  }
  var confirming = false;
  async function confirm(options) {
    if (confirming) return false;
    confirming = true;
    var dialog = document.getElementById("confirmation"), opener = document.activeElement;
    document.getElementById("confirmation-title").textContent = options.title;
    document.getElementById("confirmation-body").textContent = options.body;
    var accept = document.getElementById("confirmation-accept");
    accept.textContent = options.action;
    accept.className = options.destructive === false ? "btn primary" : "btn harm";
    dialog.returnValue = "cancel";
    return new Promise(function (resolve) {
      function closed() {
        dialog.removeEventListener("close", closed);
        confirming = false;
        if (opener && document.contains(opener)) opener.focus({preventScroll: true});
        resolve(dialog.returnValue === "accept");
      }
      dialog.addEventListener("close", closed);
      dialog.showModal();
      document.getElementById("confirmation-cancel").focus();
    });
  }
  function messageContent(node, value) {
    node.replaceChildren();
    node.append(document.createTextNode(window.i18n.primary(value)));
    if (typeof value === "string" && value && node.dataset.tone === "error") {
      var detail=document.createElement("details"), title=document.createElement("summary"), body=document.createElement("p");
      node.textContent=t("ui.rawError");title.textContent=t("ui.details");body.textContent=value;detail.append(title,body);node.append(detail);
    }
    if (value && value.key) {
      var key = value.key + ".details", translated = t(key, value.params);
      if (value.key === "stems.space") { translated=window.i18n.message(value); }
      if (translated !== key) {
        var detail = document.createElement("details"), title = document.createElement("summary"), body = document.createElement("p");
        title.textContent = t("ui.details"); body.textContent = translated; detail.append(title,body); node.append(detail);
      }
      if (value.key === "error.busy") {
        var button=document.createElement("button");button.className="btn small";button.textContent=t("ui.currentTask");
        button.addEventListener("click",function () {document.getElementById("job-message").focus();});node.append(button);
      }
    }
  }
  var tasks = {}, failures = {};
  function status(screen, text, tone) {
    var node = document.querySelector("#" + screen + " .screen-state");
    if (!node) return;
    node.dataset.tone = tone || "neutral";
    messageContent(node, text || "");
    node.hidden = !text;
    node.setAttribute("role", tone === "error" ? "alert" : "status");
  }
  function begin(screen) {
    tasks[screen] = (tasks[screen] || 0) + 1;
    failures[screen] = null;
  }
  function end(screen, error) {
    tasks[screen] = Math.max(0, (tasks[screen] || 1) - 1);
    if (error) failures[screen] = error;
    if (failures[screen]) status(screen, failures[screen], "error");
    else if (!tasks[screen]) status(screen, "");
  }
  function announce(screen, sentence) { status(screen, sentence, "success"); }
  function fieldGroup(group, label) {
    group.setAttribute("role", "group");
    group.setAttribute("aria-label", label);
  }
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-theme-choice]").forEach(function (button) {
      button.addEventListener("click", function () {
        theme(button.dataset.themeChoice);
        try { localStorage.setItem("rx3.theme", preference); }
        catch (_) { announce("settings", t("ui.preferenceSession")); }
      });
    });
    theme(preference);
    document.getElementById("confirmation-cancel").addEventListener("click", function () { document.getElementById("confirmation").close("cancel"); });
    document.getElementById("confirmation-accept").addEventListener("click", function () { document.getElementById("confirmation").close("accept"); });
    document.addEventListener("click", function (event) {
      var target = event.target.closest("[data-go]");
      if (target) { window.show(target.dataset.go); (document.getElementById("tab-" + target.dataset.go) || document.getElementById("drive-title")).focus(); }
    });
    document.addEventListener("keydown", function (event) {
      var target = event.target.closest(".segmented button, .modes button");
      if (!target || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      var choices = Array.from(target.parentElement.querySelectorAll("button:not(:disabled)"));
      if (!choices.length) return;
      var index = choices.indexOf(target);
      index = event.key === "Home" ? 0 : event.key === "End" ? choices.length - 1 : (index + (event.key === "ArrowLeft" ? -1 : 1) + choices.length) % choices.length;
      event.preventDefault(); choices[index].focus();
    });
    // Expose full paths to keyboard and pointer users without truncation.
    document.querySelectorAll("details.path-detail").forEach(function (detail) {
      detail.addEventListener("toggle", function () { if (detail.open) detail.scrollIntoView({block:"nearest"}); });
    });
  });
  window.addEventListener("rx3language", function () { theme(preference); });
  window.ui = {messageContent:messageContent, theme:theme, preserve:preserve, confirm:confirm, begin:begin, end:end, status:status, announce:announce, fieldGroup:fieldGroup};
})();
