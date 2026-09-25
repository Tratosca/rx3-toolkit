// SPDX-License-Identifier: MPL-2.0
// Deliberately schematic: layout context, never a firmware screenshot.
(function () {
  var t = window.i18n.t;
  var logo = null;
  var theme = "dark";
  var pads = [];
  var chosen = 0;
  var playing = [];

  function logoBounds(width, height) {
    var factor = Math.min(1, 864 / width, 386 / height);
    return {x: 640 - width * factor / 2, y: 284 - height * factor / 2,
            scale: factor};
  }

  function render(canvas, sampler) {
    var scale = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = 1280 * scale;
    canvas.height = 800 * scale;
    var p = canvas.getContext("2d");
    p.setTransform(scale, 0, 0, scale, 0, 0);
    var light = theme === "light";
    var bg = light ? "#eef0f3" : "#11151c";
    var panel = light ? "#dce1e8" : "#202733";
    var inset = light ? "#f9fafb" : "#171c25";
    var fg = light ? "#202734" : "#edf1f7";
    var muted = light ? "#586475" : "#a7b2c4";
    var blue = light ? "#265fab" : "#7ab6ff";
    function box(x, y, w, h, fill, radius) {
      var r = Math.min(radius || 16, w / 2, h / 2);
      p.fillStyle = fill; p.beginPath();
      p.moveTo(x + r, y); p.arcTo(x+w, y, x+w, y+h, r);
      p.arcTo(x+w, y+h, x, y+h, r); p.arcTo(x, y+h, x, y, r);
      p.arcTo(x, y, x+w, y, r); p.closePath(); p.fill();
    }
    function text(value, x, y, size, color, align) {
      p.font = "500 " + size + "px -apple-system, BlinkMacSystemFont, sans-serif";
      p.fillStyle = color || fg; p.textAlign = align || "left";
      p.fillText(value, x, y);
    }
    function bar(x, y, w, color) { box(x, y, w, 7, color, 3); }
    box(0, 0, 1280, 800, bg, 32);
    box(20, 20, 1240, 45, panel, 14);
    text(t("mock.remain"), 38, 50, 20, muted);
    bar(292, 39, 550, inset);
    text(t("mock.product"), 1240, 50, 20, muted, "right");
    [0, 1].forEach(function (deck) {
      var y = 88 + deck * 213;
      box(20, y, 168, 194, panel);
      text(t("mock.deck", {number: deck + 1}), 38, y + 34, 20, blue);
      bar(38, y+62, 111, inset); bar(38, y+83, 83, inset);
      text(t("mock.tempo"), 38, y + 135, 24, muted);
      text(t("mock.emptyTime"), 38, y + 167, 20, muted);
    });
    box(1090, 88, 170, 322, panel);
    text(t("mock.fx"), 1175, 125, 20, muted, "center");
    box(1106, 146, 138, 62, inset, 12);
    text(t("mock.echo"), 1175, 184, 25, fg, "center");
    text(t("mock.select"), 1175, 245, 17, muted, "center");
    text(t("mock.channels"), 1175, 285, 27, fg, "center");
    text(t("mock.beat"), 1175, 369, 21, muted, "center");
    box(1090, 428, 170, 67, panel);
    text(t("mock.panels"), 1175, 470, 20, fg, "center");
    if (logo) {
      // Preserve the canvas dimensions and transparent margins in the export.
      var ratio = window.devicePixelRatio || 1;
      var width = logo.width / ratio, height = logo.height / ratio;
      var bounds = logoBounds(width, height);
      p.drawImage(logo, bounds.x, bounds.y, width * bounds.scale, height * bounds.scale);
    } else {
      text(t("mock.logo"), 638, 293, 60, muted, "center");
    }
    [0, 1].forEach(function (deck) {
      var origin = 20 + deck * 640;
      text(sampler ? t("mock.samples") : t("mock.cues"), origin + 300, 531, 19, muted, "center");
      for (var i = 0; i < 8; i++) {
        var pad = pads[i];
        var x = origin + (i % 4) * 155, y = 548 + Math.floor(i / 4) * 49;
        var colour = sampler && pad ? pad.colour : blue;
        box(x, y, 145, 39, panel, 11);
        if (sampler && playing.indexOf(i) >= 0) {
          box(x, y, 145, 39, colour, 11);
          box(x+4, y+4, 137, 31, inset, 8);
        } else if (sampler && chosen === i) {
          bar(x+14, y+30, 117, colour);
        }
        text(sampler ? String(i+1) : String.fromCharCode(65+i), x+72, y+25, 18, fg, "center");
      }
      box(origin, 652, 600, 126, panel);
      text(t("mock.deck", {number: deck + 1}), origin + 20, 683, 18, blue);
      text(t("mock.time"), origin + 20, 737, 40, fg);
      text(t("mock.tempo"), origin + 575, 730, 27, muted, "right");
      bar(origin + 20, 755, 555, inset);
    });
  }
  function draw() {
    document.querySelectorAll("canvas.rx3-mock").forEach(function (canvas) {
      render(canvas, canvas.dataset.preview === "samples");
    });
  }
  window.rx3mock = {
    logoBounds: logoBounds,
    setLogo: function (image, mode) { logo = image; theme = mode; draw(); },
    setPads: function (values, selected, active) {
      pads = values; chosen = selected; playing = active; draw();
    }
  };
  window.addEventListener("rx3language", draw);
  draw();
})();
