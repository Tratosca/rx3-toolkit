// SPDX-License-Identifier: MPL-2.0
//
// Four hooks and no expression language. A screen marks what it wants
// translated with an attribute, and one pass over the document fills it in, so
// changing language redraws nothing and loses no state.

(function () {
  var language = "en";

  var catalogs = {};
  function normalize(code) {
    var base = String(code || "en").toLowerCase().replace("_", "-").split("-")[0];
    return catalogs[base] ? base : "en";
  }
  function number(value, options) {
    return new Intl.NumberFormat(language, options).format(value);
  }
  function t(key, vars) {
    vars = vars || {};
    var selected = catalogs[language] || {};
    var resolvedLocale = selected[key] === undefined ? "en" : language;
    var text = selected[key] === undefined ? (catalogs.en || {})[key] : selected[key];
    if (text === undefined) return key;
    if (typeof text === "object") {
      var category = new Intl.PluralRules(resolvedLocale).select(Number(vars.count));
      text = text[category] || text.other;
    }
    return text.replace(/\{(\w+)\}/g, function (whole, name) {
      if (!Object.prototype.hasOwnProperty.call(vars, name)) return whole;
      var value = vars[name];
      return typeof value === "number" ? number(value) : message(value);
    });
  }
  function message(value) {
    return value && typeof value === "object" && value.key
      ? t(value.key, value.params) : String(value == null ? "" : value);
  }
  function primary(value) {
    if (!value || typeof value !== "object" || !value.key) return message(value);
    if (value.key === "unit.mib" || value.key === "unit.kib") return bytes(Number(value.params.value) * (value.key === "unit.mib" ? 1048576 : 1024));
    var vars = Object.assign({},value.params || {});
    if (value.key === "stems.space") { vars.requiredSize=bytes(vars.required);vars.availableSize=bytes(vars.available); }
    var key=value.key+".summary";
    return t(key,vars) !== key ? t(key,vars) : message(value);
  }
  function bytes(count) {
    var unit = count >= 1e9 ? "unit.gb" : count >= 1e6 ? "unit.mb" : count >= 1000 ? "unit.kb" : "unit.bytes";
    var value = count >= 1e9 ? count / 1e9 : count >= 1e6 ? count / 1e6 : count >= 1000 ? count / 1000 : count;
    return t(unit, {value:number(value, {maximumFractionDigits:count >= 1e6 ? 1 : 0})});
  }
  async function load() {
    var answer = await window.pywebview.api.localization_catalogs();
    if (!answer.ok) throw new Error(answer.error);
    catalogs = answer.value;
    var saved;
    try { saved = localStorage.getItem("rx3.language"); } catch (_) {}
    setLanguage(saved || navigator.language);
  }

  var ATTRIBUTES = {
    "data-t-title": "title",
    "data-t-placeholder": "placeholder",
    "data-t-label": "aria-label",
  };

  function apply(root) {
    var node = root || document;
    var texts = node.querySelectorAll("[data-t]");
    for (var i = 0; i < texts.length; i++) {
      texts[i].textContent = t(texts[i].getAttribute("data-t"));
    }
    for (var name in ATTRIBUTES) {
      var marked = node.querySelectorAll("[" + name + "]");
      for (var j = 0; j < marked.length; j++) {
        marked[j].setAttribute(ATTRIBUTES[name], t(marked[j].getAttribute(name)));
      }
    }
  }

  function setLanguage(code) {
    language = normalize(code);
    try { localStorage.setItem("rx3.language", language); } catch (_) {}
    if (window.pywebview) window.pywebview.api.localization_language(language);
    document.documentElement.lang = language;
    apply(document);
    window.dispatchEvent(new CustomEvent("rx3language", { detail: language }));
  }

  function current() {
    return language;
  }

  function missing() {
    var gaps = [];
    Object.keys(catalogs).forEach(function (locale) {
      Object.keys(catalogs.en || {}).forEach(function (key) {
        if (catalogs[locale][key] === undefined) gaps.push(locale + ":" + key);
      });
    });
    return gaps;
  }
  window.i18n = {t:t, message:message, primary:primary, number:number, bytes:bytes, load:load,
    apply:apply, setLanguage:setLanguage, current:current, missing:missing};
})();
