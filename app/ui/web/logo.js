// SPDX-License-Identifier: MPL-2.0
//
// The logo framer. The drag runs here because the encoder is a per-pixel loop
// in Python that costs about 700 ms for the largest pane, which is a slideshow
// rather than a drag. So this draws the artwork exactly where Python would put
// it, and asks Python for the truth once the pointer stops.
//
// The placement below is the same arithmetic as container.placement, and a test
// lifts it out of this file and runs it against the Python for a sweep of
// sizes, zooms and offsets. Every number it obeys arrives from the bridge, so
// this holds the formula and not one constant of its own.

(function () {
  var t = window.i18n.t;

  // PLACEMENT BEGIN
  function roundHalfUp(value) {
    return value >= 0 ? Math.floor(value + 0.5) : Math.ceil(value - 0.5);
  }

  function placement(artWidth, artHeight, ink, frame, limits) {
    if (artWidth < 1 || artHeight < 1) return null;
    var wide = ink.width / artWidth;
    var tall = ink.height / artHeight;
    var fit = frame.mode === "cover" ? Math.max(wide, tall) : Math.min(wide, tall);
    var scale = fit * Math.min(limits.zoomMax, Math.max(limits.zoomMin, frame.zoom));
    var width = Math.max(1, roundHalfUp(artWidth * scale));
    var height = Math.max(1, roundHalfUp(artHeight * scale));

    function room(drawn, limit, offset) {
      var centred = roundHalfUp((limit - drawn) / 2) + roundHalfUp(offset);
      var visible = Math.min(limits.minVisible, drawn, limit);
      return Math.min(limit - visible, Math.max(visible - drawn, centred));
    }

    return {
      x: room(width, ink.width, frame.offsetX),
      y: room(height, ink.height, frame.offsetY),
      width: width,
      height: height,
    };
  }
  // PLACEMENT END

  var limits = null;
  var panes = [];
  var pane = null;
  var art = null;          // {path, width, height, preview}
  var bitmap = null;
  var frame = {mode: "contain", zoom: 1, offsetX: 0, offsetY: 0};
  var theme = "dark";
  // Whether a light screen gets the artwork's greys inverted. On by default,
  // which is what every logo got before this was a choice.
  var invertLight = true;
  var truth = null;        // what Python last said
  var pending = null;
  var revision = 0;
  var exact = null;

  function ink() {
    return {width: pane.inkWidth, height: pane.inkHeight};
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // Drawing --------------------------------------------------------------------

  function draw() {
    var canvas = document.getElementById("logo-canvas");
    var ratio = window.devicePixelRatio || 1;
    canvas.width = pane.canvasWidth * ratio;
    canvas.height = pane.canvasHeight * ratio;
    canvas.style.aspectRatio = pane.canvasWidth + " / " + pane.canvasHeight;
    var pen = canvas.getContext("2d");
    pen.setTransform(ratio, 0, 0, ratio, 0, 0);
    pen.clearRect(0, 0, pane.canvasWidth, pane.canvasHeight);

    // The margin the player samples to decide the pane is finished. Artwork
    // never reaches it, so the frame shows where it stops.
    pen.strokeStyle = getComputedStyle(canvas).getPropertyValue(theme === "dark" ? "--logo-dark-guide" : "--logo-light-guide").trim();
    pen.setLineDash([4, 4]);
    pen.strokeRect(pane.inkOriginX + 0.5, pane.inkOriginY + 0.5,
                   pane.inkWidth - 1, pane.inkHeight - 1);
    pen.setLineDash([]);

    if (exact) {
      pen.drawImage(theme === "light" ? exact.light : exact.dark, 0, 0);
      if (window.rx3mock) window.rx3mock.setLogo(canvas, theme);
      return;
    }
    if (!bitmap) {
      if (window.rx3mock) window.rx3mock.setLogo(null, theme);
      return;
    }
    var box = placement(art.width, art.height, ink(), frame, limits);
    if (!box) return;
    pen.save();
    pen.beginPath();
    pen.rect(pane.inkOriginX, pane.inkOriginY, pane.inkWidth, pane.inkHeight);
    pen.clip();
    if (theme === "light" && invertLight) {
      // The deck inverts the greys of the artwork for a light screen. This is
      // the shape of that, not the pixels: Python decides what is grey.
      pen.filter = "invert(1)";
    }
    pen.drawImage(bitmap, pane.inkOriginX + box.x, pane.inkOriginY + box.y,
                  box.width, box.height);
    pen.restore();
    if (window.rx3mock) window.rx3mock.setLogo(canvas, theme);
  }

  function notes() {
    var panel = document.getElementById("logo-notes");
    panel.replaceChildren();
    document.getElementById("logo-empty").hidden = Boolean(art);
    document.getElementById("logo-controls").disabled = !art;
    var pick = document.getElementById("logo-pick"); pick.className = art ? "btn" : "btn primary";
    pick.removeAttribute("data-t"); pick.textContent = t(art ? "logo.changeImage" : "logo.choose");
    if (!art) return;
    var box = placement(art.width, art.height, ink(), frame, limits);
    if (box) {
      var dimensions = el("details"); dimensions.append(el("summary",null,t("ui.details")));
      dimensions.append(el("p", "dim num", t("logo.size", {
        width: box.width, height: box.height,
        canvasWidth: pane.canvasWidth, canvasHeight: pane.canvasHeight,
      }))); panel.append(dimensions);
    }
    if (truth && truth.faint) panel.append(el("p", "note warn", t("logo.faint")));
    // Artwork with no grey to invert looks the same either way, so the choice
    // is only offered when it changes something.
    if (truth && !truth.invertible) panel.append(el("p", "note", t("logo.sameInLight")));

  }

  /** The two choices the framing card offers, pressed where they stand. */
  function marks() {
    var panesRow = document.getElementById("logo-pane").children;
    for (var i = 0; i < panesRow.length; i++) {
      panesRow[i].setAttribute("aria-pressed", String(pane && panesRow[i].dataset.pane === pane.name));
    }
    var invert = document.getElementById("logo-invert");
    invert.checked = invertLight;
    document.getElementById("logo-invert-row").hidden = !(art && truth && truth.invertible);
    document.getElementById("logo-invert-hint").textContent =
      t(invertLight ? "logo.invertOnHint" : "logo.invertOffHint");
    document.getElementById("logo-fit").setAttribute("aria-pressed", String(frame.mode === "contain"));
    document.getElementById("logo-fill").setAttribute("aria-pressed", String(frame.mode === "cover"));
    document.getElementById("logo-theme-dark").setAttribute("aria-pressed", String(theme === "dark"));
    document.getElementById("logo-theme-light").setAttribute("aria-pressed", String(theme === "light"));
  }

  function zoomBox() {
    marks();
    document.getElementById("logo-zoom").value = String(Math.round(
      ((frame.zoom - limits.zoomMin) / (limits.zoomMax - limits.zoomMin)) * 1000));
    document.getElementById("logo-zoom-value").textContent = t("unit.zoom", {value:window.i18n.number(frame.zoom, {maximumFractionDigits:1})});
  }

  function refresh() {
    revision += 1;
    exact = null;
    draw();
    notes();
    zoomBox();
    publish();
    settle();
  }

  /** Ask Python for the truth, once the operator has stopped moving. */
  function settle() {
    if (!art) return;
    if (pending) clearTimeout(pending);
    var requested = revision;
    var requestFrame = Object.assign({invertLight: invertLight}, frame);
    pending = setTimeout(async function () {
      pending = null;
      var answer = await window.rx3.ask("logo_render", art.path, pane.name, requestFrame);
      if (!answer || requested !== revision) return;
      function load(url) {
        return new Promise(function (resolve, reject) {
          var image = new Image(); image.onload = function () { resolve(image); };
          image.onerror = reject; image.src = url;
        });
      }
      try {
        var pictures = await Promise.all([load(answer.canvas), load(answer.lightCanvas)]);
        if (requested !== revision) return;
        truth = answer; exact = {dark: pictures[0], light: pictures[1]};
        draw(); notes(); marks();
      } catch (error) { window.rx3.fail(String(error)); }
    }, 200);
  }

  /** What the build needs to draw the same thing. */
  function publish() {
    try {
      if (art) localStorage.setItem("rx3.logo", JSON.stringify({
        path: art.path, canvas: pane.name, frame: frame, invertLight: invertLight
      }));
      else localStorage.removeItem("rx3.logo");
    } catch (_) { /* The editor still works when local storage is unavailable. */ }
    window.dispatchEvent(new CustomEvent("rx3logo", {detail: art ? {
      path: art.path, canvas: pane.name, mode: frame.mode,
      zoom: frame.zoom, offsetX: frame.offsetX, offsetY: frame.offsetY,
      invertLight: invertLight,
    } : null}));
  }

  // Moving ----------------------------------------------------------------------

  function mockPoint(canvas, clientX, clientY) {
    var rect = canvas.getBoundingClientRect();
    var box = window.rx3mock.logoBounds(pane.canvasWidth, pane.canvasHeight);
    return {
      x: ((clientX - rect.left) * 1280 / rect.width - box.x) / box.scale - pane.inkOriginX,
      y: ((clientY - rect.top) * 800 / rect.height - box.y) / box.scale - pane.inkOriginY,
    };
  }

  function drag(canvas) {
    var from = null;
    canvas.addEventListener("pointerdown", function (event) {
      if (!bitmap) return;
      if (event.button !== 0) return;
      var point = mockPoint(canvas, event.clientX, event.clientY);
      var box = placement(art.width, art.height, ink(), frame, limits);
      if (point.x < Math.max(0, box.x) || point.x > Math.min(pane.inkWidth, box.x + box.width) ||
          point.y < Math.max(0, box.y) || point.y > Math.min(pane.inkHeight, box.y + box.height)) return;
      event.preventDefault();
      from = {x: point.x, y: point.y, offsetX: frame.offsetX, offsetY: frame.offsetY};
      canvas.classList.add("dragging");
      canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener("pointermove", function (event) {
      if (!from) return;
      var point = mockPoint(canvas, event.clientX, event.clientY);
      frame.offsetX = from.offsetX + point.x - from.x;
      frame.offsetY = from.offsetY + point.y - from.y;
      refresh();
    });
    function release(event) {
      if (!from) return;
      from = null;
      canvas.classList.remove("dragging");
      if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    }
    canvas.addEventListener("pointerup", release);
    canvas.addEventListener("pointercancel", release);

    canvas.addEventListener("wheel", function (event) {
      if (!bitmap || document.activeElement !== canvas) return;
      event.preventDefault();
      var before = placement(art.width, art.height, ink(), frame, limits);
      var wanted = frame.zoom * Math.exp(-event.deltaY * 0.0012);
      frame.zoom = Math.min(limits.zoomMax, Math.max(limits.zoomMin, wanted));
      var after = placement(art.width, art.height, ink(), frame, limits);
      if (before && after) {
        // Keep the point under the pointer where it is, so zooming feels like
        // moving the paper rather than resizing it from the middle.
        var point = mockPoint(canvas, event.clientX, event.clientY);
        var atX = point.x, atY = point.y;
        var uX = before.width ? (atX - before.x) / before.width : 0.5;
        var uY = before.height ? (atY - before.y) / before.height : 0.5;
        frame.offsetX += (after.width - before.width) * (0.5 - uX);
        frame.offsetY += (after.height - before.height) * (0.5 - uY);
      }
      refresh();
    }, {passive: false});
  }

  // Doing ------------------------------------------------------------------------

  async function choose() {
    var picked = await window.rx3.ask("pick_file", "image", "");
    if (!picked || !picked.path) return;
    var opened = await window.rx3.ask("logo_open", picked.path);
    if (!opened) return;
    art = opened;
    truth = null;
    frame = {mode: "contain", zoom: 1, offsetX: 0, offsetY: 0};
    var loaded = new Image();
    bitmap = loaded;
    loaded.onload = function () {
      if (bitmap !== loaded) return;
      document.getElementById("logo-pick").textContent = t("logo.changeImage");
      refresh();
    };
    loaded.onerror = function () { window.rx3.fail(t("ui.imageError")); };
    loaded.src = opened.preview;
  }

  /** One button per pane, named for a DJ and sized for whoever checks. */
  function drawPanes() {
    var row = document.getElementById("logo-pane");
    row.replaceChildren();
    for (var i = 0; i < panes.length; i++) {
      var named = t("logo.pane." + panes[i].name);
      var button = el("button", "btn small", named === "logo.pane." + panes[i].name ? panes[i].name : named);
      button.type = "button";
      button.dataset.pane = panes[i].name;
      var silhouette = el("span", "logo-zone"); silhouette.setAttribute("aria-hidden","true"); silhouette.dataset.pane=panes[i].name; button.append(silhouette);
      button.addEventListener("click", function (event) {
        var wanted = event.currentTarget.dataset.pane;
        for (var j = 0; j < panes.length; j++) if (panes[j].name === wanted) pane = panes[j];
        refresh();
      });
      row.append(button);
    }
    marks();
  }

  function wire() {
    var canvas = document.getElementById("logo-mock");
    drag(canvas);
    canvas.addEventListener("keydown", function (event) {
      if (!bitmap || ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].indexOf(event.key) < 0) return;
      event.preventDefault();
      var step = event.shiftKey ? 10 : 1;
      if (event.key === "ArrowLeft") frame.offsetX -= step;
      if (event.key === "ArrowRight") frame.offsetX += step;
      if (event.key === "ArrowUp") frame.offsetY -= step;
      if (event.key === "ArrowDown") frame.offsetY += step;
      refresh();
    });
    document.getElementById("logo-pick").addEventListener("click", choose);
    document.getElementById("logo-invert").addEventListener("change", function (event) {
      invertLight = event.target.checked;
      // Show what the choice does: it only shows on a light screen.
      theme = "light";
      refresh();
    });
    document.getElementById("logo-zoom").addEventListener("input", function (event) {
      var span = limits.zoomMax - limits.zoomMin;
      frame.zoom = limits.zoomMin + (Number(event.target.value) / 1000) * span;
      refresh();
    });
    document.getElementById("logo-fit").addEventListener("click", function () {
      frame.mode = "contain";
      frame.zoom = 1;
      refresh();
    });
    document.getElementById("logo-fill").addEventListener("click", function () {
      frame.mode = "cover";
      frame.zoom = 1;
      refresh();
    });
    document.getElementById("logo-reset").addEventListener("click", function () {
      frame.offsetX = 0;
      frame.offsetY = 0;
      refresh();
    });
    document.getElementById("logo-theme-dark").addEventListener("click", function () {
      theme = "dark";
      marks();
      draw();
    });
    document.getElementById("logo-theme-light").addEventListener("click", function () {
      theme = "light";
      marks();
      draw();
    });
    window.addEventListener("rx3language", function () {
      if (art) document.getElementById("logo-pick").textContent = t("logo.changeImage");
      if (art) notes();
      if (panes.length) drawPanes();
      if (limits) zoomBox();
    });
  }

  async function start() {
    limits = await window.rx3.ask("logo_limits");
    panes = (await window.rx3.ask("logo_canvases")) || [];
    if (!limits || !panes.length) return;
    pane = panes[0];
    drawPanes();
    wire();
    draw();
    zoomBox();
    var remembered;
    try { remembered = JSON.parse(localStorage.getItem("rx3.logo") || "null"); } catch (_) {}
    if (remembered && remembered.path && remembered.frame) {
      var restored = await window.rx3.ask("logo_open", remembered.path);
      if (restored) {
        art = restored;
        pane = panes.find(function (item) { return item.name === remembered.canvas; }) || panes[0];
        frame = remembered.frame;
        invertLight = remembered.invertLight !== false;
        bitmap = new Image();
        bitmap.onload = function () {
          document.getElementById("logo-pick").textContent = t("logo.changeImage");
          refresh();
        };
        bitmap.src = art.preview;
      }
    }
  }

  window.rx3logo = {start: start, placement: placement};
})();
