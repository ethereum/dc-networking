/* kit.js: shared helpers for the free-running committees page (no dependencies). */
(function () {
  "use strict";
  var NS = "http://www.w3.org/2000/svg";

  var K = {
    C: 23,          // committees (cohorts) per round
    UNIT: 4,        // seconds per unit
    SLOT: 12,       // seconds per slot
    UPS: 3,         // units per slot
    ROUND_FRC: 92,  // free-running round: 23 units
    ROUND_Q17: 96   // slot-aligned round: 8 slots
  };

  /* --- DOM / SVG ------------------------------------------------------------------------- */
  K.svg = function (tag, attrs, parent) {
    var el = document.createElementNS(NS, tag);
    if (attrs) for (var k in attrs) if (attrs[k] !== null && attrs[k] !== undefined) el.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(el);
    return el;
  };
  K.text = function (parent, x, y, str, attrs) {
    var a = attrs || {};
    a.x = x; a.y = y;
    var t = K.svg("text", a, parent);
    t.textContent = str;
    return t;
  };
  K.el = function (tag, attrs, parent, text) {
    var el = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      if (k === "class") el.className = attrs[k];
      else if (attrs[k] !== null && attrs[k] !== undefined) el.setAttribute(k, attrs[k]);
    }
    if (text !== undefined) el.textContent = text;
    if (parent) parent.appendChild(el);
    return el;
  };
  K.clear = function (el) { while (el.firstChild) el.removeChild(el.firstChild); };
  K.css = function (name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  };

  /* hatch patterns, one per colour token; referenced as url(#hatch-<name>) */
  K.defs = function (svgRoot) {
    var defs = K.svg("defs", null, svgRoot);
    [["repair", "var(--repair)"], ["agg", "var(--agg)"], ["idle", "var(--idle)"], ["muted", "var(--line-strong)"],
     ["adv", "var(--adv)"], ["vote", "var(--vote)"]].forEach(function (p) {
      var pat = K.svg("pattern", { id: "hatch-" + p[0], patternUnits: "userSpaceOnUse", width: 6, height: 6, patternTransform: "rotate(45)" }, defs);
      K.svg("rect", { width: 6, height: 6, fill: "var(--surface)" }, pat);
      K.svg("rect", { width: 2.4, height: 6, fill: p[1] }, pat);
    });
    return defs;
  };

  /* --- tooltip ---------------------------------------------------------------------------- */
  var tip = null;
  K.tip = function (html, ev) {
    if (!tip) { tip = K.el("div", { class: "tip", role: "status" }, document.body); }
    K.clear(tip);
    html.forEach(function (line, i) {
      var row = K.el("div", null, tip);
      if (typeof line === "string") row.textContent = line;
      else { var b = K.el("b", null, row, line[0]); if (line[1]) row.appendChild(document.createTextNode(" " + line[1])); }
    });
    var x = ev.clientX + 14, y = ev.clientY + 14;
    tip.classList.add("on");
    var r = tip.getBoundingClientRect();
    if (x + r.width > window.innerWidth - 8) x = ev.clientX - r.width - 14;
    if (y + r.height > window.innerHeight - 8) y = ev.clientY - r.height - 14;
    tip.style.left = Math.max(8, x) + "px";
    tip.style.top = Math.max(8, y) + "px";
  };
  K.untip = function () { if (tip) tip.classList.remove("on"); };
  K.hover = function (node, lines) {
    node.addEventListener("pointermove", function (ev) { K.tip(typeof lines === "function" ? lines() : lines, ev); });
    node.addEventListener("pointerleave", K.untip);
  };

  /* --- player: drives a time value with play / pause / scrub ------------------------------ */
  K.reducedMotion = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : { matches: false };
  K.player = function (opts) {
    // opts: { t0, t1, speed (sim s per real s), onFrame(t), controls: element, loop, label }
    var t = opts.start !== undefined ? opts.start : opts.t0;
    var playing = false, last = null, raf = null, speed = opts.speed || 4;
    var ctl = opts.controls;
    var btn = K.el("button", { class: "btn", type: "button", "aria-label": "Play" }, ctl, "▶ Play");
    var range = K.el("input", { type: "range", class: "scrub", min: opts.t0, max: opts.t1, step: 0.1, value: t, "aria-label": opts.label || "Time" }, ctl);
    var spd = K.el("div", { class: "seg", role: "group", "aria-label": "Speed" }, ctl);
    (opts.speeds || [[1, "1×"], [4, "4×"], [12, "12×"]]).forEach(function (s) {
      var b = K.el("button", { type: "button", "aria-pressed": String(s[0] === speed) }, spd, s[1]);
      b.addEventListener("click", function () {
        speed = s[0];
        Array.prototype.forEach.call(spd.children, function (c) { c.setAttribute("aria-pressed", "false"); });
        b.setAttribute("aria-pressed", "true");
      });
    });
    var out = K.el("span", { class: "readout" }, ctl);
    function draw() { range.value = t; out.textContent = opts.format ? opts.format(t) : t.toFixed(1) + " s"; opts.onFrame(t); }
    function step(ts) {
      if (!playing) return;
      if (last !== null) {
        t += (ts - last) / 1000 * speed;
        if (t > opts.t1) { if (opts.loop === false) { t = opts.t1; pause(); } else t = opts.t0 + (t - opts.t1); }
      }
      last = ts;
      draw();
      raf = requestAnimationFrame(step);
    }
    function play() { if (playing) return; playing = true; last = null; btn.textContent = "❚❚ Pause"; btn.setAttribute("aria-label", "Pause"); raf = requestAnimationFrame(step); }
    function pause() { playing = false; btn.textContent = "▶ Play"; btn.setAttribute("aria-label", "Play"); if (raf) cancelAnimationFrame(raf); }
    btn.addEventListener("click", function () { playing ? pause() : play(); });
    range.addEventListener("input", function () { t = parseFloat(range.value); draw(); });
    document.addEventListener("visibilitychange", function () { if (document.hidden) pause(); });
    draw();
    // autoplay when visible, unless reduced motion
    if (opts.autoplay && !K.reducedMotion.matches && "IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (es) {
        es.forEach(function (e) { if (e.isIntersecting) { play(); io.disconnect(); } });
      }, { threshold: 0.35 });
      io.observe(opts.observe || ctl);
    }
    return { set: function (v) { t = v; draw(); }, get: function () { return t; }, play: play, pause: pause, redraw: draw };
  };

  /* finality.watch block face: corners 3 / 8 / 3 / 8 (tl, tr, br, bl), scaled to size s */
  K.blockPath = function (x, y, s) {
    var a = s * 3 / 18, b = s * 8 / 18;
    return "M" + (x + a) + "," + y + "H" + (x + s - b) + "Q" + (x + s) + "," + y + " " + (x + s) + "," + (y + b) +
      "V" + (y + s - a) + "Q" + (x + s) + "," + (y + s) + " " + (x + s - a) + "," + (y + s) +
      "H" + (x + b) + "Q" + x + "," + (y + s) + " " + x + "," + (y + s - b) + "V" + (y + a) + "Q" + x + "," + y + " " + (x + a) + "," + y + "Z";
  };

  /* --- formatting -------------------------------------------------------------------------- */
  K.fmtS = function (s, d) { return (Math.round(s * Math.pow(10, d || 0)) / Math.pow(10, d || 0)).toFixed(d || 0) + " s"; };
  K.slotOf = function (t) { return Math.floor(t / K.SLOT); };
  K.offsetOf = function (u) { return ((u % 3) + 3) % 3; };      // 0, 1, 2 -> +0, +4, +8 s
  K.mod = function (a, n) { return ((a % n) + n) % n; };

  window.FRC = K;
})();
