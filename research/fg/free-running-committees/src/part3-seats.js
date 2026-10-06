/* Part 3: pick your seat. Validators choose a committee index k in [0, 23); the active committee
   index k(t) = floor(t/4) mod 23 alone decides when a seat votes. The ring shows each seat's stake
   (by chooser) against a per-seat cap, the sweeping hand, and the slot grid that turns under it. */
(function () {
  "use strict";
  var K = window.FRC;
  var C = 23;

  // stake shares are in units of S/C (one "seat's worth"); cap = kappa seats' worth
  var SCEN = {
    spread: {
      label: "Default (hashed)",
      note: "Seats are assigned by hash until a validator asks for a seat: every seat holds about 1/23 of the stake, and each large operator is spread thinly over all seats.",
      seats: function () {
        var out = [];
        for (var k = 0; k < C; k++) out.push([["A", 0.094], ["B", 0.05], ["small", 0.856 + 0.03 * Math.sin(k * 2.1)]]);
        return out;
      }
    },
    colocate: {
      label: "Operators co-locate",
      note: "Operator A (9.4 % of stake) packs its validators into seats 3–5 and operator B (5 %) into seats 14–15. Where an operator fills a whole seat, its committees aggregate locally (and reveal who it is). Everyone else stays spread out, and no seat exceeds the cap.",
      seats: function () {
        var out = [];
        for (var k = 0; k < C; k++) {
          var s = [];
          if (k === 3 || k === 4) s.push(["A", 1.0]);
          else if (k === 5) s.push(["A", 0.162], ["small", 0.86]);
          else if (k === 14) s.push(["B", 1.0]);
          else if (k === 15) s.push(["B", 0.15], ["small", 0.87]);
          else s.push(["small", 0.945 + 0.03 * Math.sin(k * 1.7)]);
          out.push(s);
        }
        return out;
      }
    },
    adversary: {
      label: "Adversary takes a block",
      note: "An adversary with 30 % of stake fills seats 8–14 up to the cap. Any 4 consecutive units inside that block are 100 % adversarial, against about a third with default seats. That matters only to a gadget that reads partial tallies (an SG, or a fast confirmation over the last few units). Withholding the block is just being offline; releasing it at once is bounded by the vote windows.",
      seats: function () {
        var out = [];
        for (var k = 0; k < C; k++) {
          if (k >= 8 && k <= 14) out.push([["adv", 0.986]]);
          else out.push([["A", 0.094], ["small", 0.906 + 0.02 * Math.cos(k)]]);
        }
        return out;
      }
    },
    herd: {
      label: "Everyone wants seat 0",
      note: "Demand for seat 0 is five times the cap. The cap admits up to 1.05 seats' worth of stake, and the remaining requests are refused (or wait for room) without moving anyone else. Under the free-running clock no seat is better for in-slot timing, so this only happens if a default or a bug sends everyone to the same index. A count cap is needed as well: the stake cap alone lets a seat fill with many small validators.",
      seats: function () {
        var out = [];
        for (var k = 0; k < C; k++) out.push(k === 0 ? [["small", 1.05]] : [["small", 0.9977]]);
        return out;
      },
      overflow: { seat: 0, demand: 5.0 }
    }
  };
  var KAPPA = 1.05;
  var COLORS = { A: "var(--s1)", B: "var(--s3)", small: "var(--line-strong)", adv: "url(#hatch-adv)" };
  var NAMES = { A: "operator A", B: "operator B", small: "other validators", adv: "adversary" };

  function init(root) {
    var holder = root.querySelector("[data-fig]");
    var ctl = root.querySelector("[data-controls]");
    var scenHost = root.querySelector("[data-scen]");
    var note = root.querySelector("[data-note]");
    var panel = root.querySelector("[data-panel]");
    var scen = "spread", mine = 9;

    var seg = K.el("div", { class: "seg", role: "group", "aria-label": "Seat choices" }, scenHost);
    Object.keys(SCEN).forEach(function (key) {
      var b = K.el("button", { type: "button", "aria-pressed": String(key === scen) }, seg, SCEN[key].label);
      b.addEventListener("click", function () {
        scen = key;
        Array.prototype.forEach.call(seg.children, function (c) { c.setAttribute("aria-pressed", "false"); });
        b.setAttribute("aria-pressed", "true");
        drawStatic(); player.redraw();
      });
    });

    var S = 560, cx = S / 2, cy = S / 2, r0 = 92, r1 = 206, rLab = 224, rSlot0 = 240, rSlot1 = 252;
    var th = 2 * Math.PI / C;
    function ang(k) { return -Math.PI / 2 + k * th; }
    function pol(r, a) { return [cx + r * Math.cos(a), cy + r * Math.sin(a)]; }
    function wedge(ra, rb, a0, a1) {
      var p0 = pol(ra, a0), p1 = pol(rb, a0), p2 = pol(rb, a1), p3 = pol(ra, a1);
      return "M" + p0 + "L" + p1 + "A" + rb + "," + rb + " 0 0 1 " + p2 + "L" + p3 + "A" + ra + "," + ra + " 0 0 0 " + p0 + "Z";
    }

    var svg = K.svg("svg", { viewBox: "0 0 " + S + " " + S, role: "img", "aria-label": "Ring of 23 seats. A hand points at the active committee index, floor(t/4) mod 23, and moves one seat every 4 seconds. Bars show each seat's stake by chooser against a per-seat cap; an outer track marks where slots begin during the current lap." }, holder);
    K.defs(svg);
    var gStatic = K.svg("g", null, svg);
    var gSlots = K.svg("g", null, svg);
    var gDyn = K.svg("g", null, svg);

    var wedges = [];
    function drawStatic() {
      K.clear(gStatic); wedges = [];
      var seats = SCEN[scen].seats();
      note.textContent = SCEN[scen].note;
      // cap ring
      var capR = r0 + (r1 - r0) * (KAPPA / 1.25);
      for (var k = 0; k < C; k++) {
        var a0 = ang(k) + 0.012, a1 = ang(k + 1) - 0.012;
        var g = K.svg("g", { tabindex: 0, class: "seat" }, gStatic);
        var bg = K.svg("path", { d: wedge(r0, r1, a0, a1), fill: "var(--surface-2)", stroke: "var(--line)", "stroke-width": 1 }, g);
        var acc = 0;
        seats[k].forEach(function (part) {
          var ra = r0 + (r1 - r0) * (acc / 1.25), rb = r0 + (r1 - r0) * ((acc + part[1]) / 1.25);
          K.svg("path", { d: wedge(ra, Math.min(rb, r1), a0 + 0.01, a1 - 0.01), fill: COLORS[part[0]] }, g);
          acc += part[1];
        });
        var mid = (ang(k) + ang(k + 1)) / 2;
        var lp = pol(rLab, mid);
        K.text(g, lp[0], lp[1] + 4, String(k), { "text-anchor": "middle", class: "t-mono", "font-size": 11.5, style: "font-weight:600" });
        (function (k, parts) {
          K.hover(g, function () {
            var tot = parts.reduce(function (s, p) { return s + p[1]; }, 0);
            var lines = [["Seat " + k, "· " + (100 * tot / C).toFixed(2) + " % of stake (cap " + (100 * KAPPA / C).toFixed(2) + " %)"]];
            parts.forEach(function (p) { lines.push(NAMES[p[0]] + ": " + (100 * p[1] / C).toFixed(2) + " % of stake"); });
            lines.push("click to make it your seat");
            return lines;
          });
          g.addEventListener("click", function () { mine = k; drawStatic(); player.redraw(); });
          g.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { mine = k; drawStatic(); player.redraw(); } });
        })(k, seats[k]);
        if (k === mine) {
          K.svg("path", { d: wedge(r0 - 6, r1 + 2, a0, a1), fill: "none", stroke: "var(--ink)", "stroke-width": 2.4, "pointer-events": "none" }, g);
        }
        wedges.push({ k: k, bg: bg });
      }
      // cap circle
      K.svg("circle", { cx: cx, cy: cy, r: capR, fill: "none", stroke: "var(--ink-2)", "stroke-width": 1, "stroke-dasharray": "3 3", "pointer-events": "none" }, gStatic);
      var cp = pol(capR + 2, ang(C) - 0.06);
      K.text(gStatic, cp[0] + 4, cp[1] - 4, "cap", { class: "t-muted", "font-size": 10 });
      var ov = SCEN[scen].overflow;
      if (ov) {
        var a0o = ang(ov.seat) + 0.02, a1o = ang(ov.seat + 1) - 0.02;
        K.svg("path", { d: wedge(r1 + 2, r1 + 2 + 12, a0o, a1o), fill: "url(#hatch-muted)", stroke: "var(--line-strong)", "stroke-dasharray": "2 2" }, gStatic);
        var tp = pol(r1 + 40, (ang(ov.seat) + ang(ov.seat + 1)) / 2);
        K.text(gStatic, tp[0] + 26, tp[1] + 6, "4× the cap refused", { "text-anchor": "start", class: "t-muted", "font-size": 10.5 });
      }
    }

    // dynamic layer: hand, active wedge, centre readout
    var hand = K.svg("line", { stroke: "var(--ink)", "stroke-width": 2.4, "stroke-linecap": "round" }, gDyn);
    var hub = K.svg("circle", { r: 4.5, fill: "var(--ink)" }, gDyn);
    var actOutline = K.svg("path", { fill: "none", stroke: "var(--vote)", "stroke-width": 3, "pointer-events": "none" }, gDyn);
    var tK = K.text(gDyn, cx, cy - 18, "", { "text-anchor": "middle", "font-size": 30, style: "font-weight:650; fill: var(--ink)" });
    var tSub = K.text(gDyn, cx, cy + 6, "", { "text-anchor": "middle", class: "t-muted", "font-size": 11 });
    var tSub2 = K.text(gDyn, cx, cy + 22, "", { "text-anchor": "middle", class: "t-muted t-mono", "font-size": 10.5 });
    K.text(gDyn, cx, cy - 46, "active committee", { "text-anchor": "middle", class: "t-muted", "font-size": 10.5 });

    function drawSlots(lap) {
      K.clear(gSlots);
      K.svg("circle", { cx: cx, cy: cy, r: (rSlot0 + rSlot1) / 2, fill: "none", stroke: "var(--surface-2)", "stroke-width": rSlot1 - rSlot0 }, gSlots);
      for (var k = 0; k < C; k++) {
        var u = C * lap + k;
        if (u % 3 === 0) {
          var a = ang(k), p0 = pol(rSlot0 - 2, a), p1 = pol(rSlot1 + 2, a);
          K.svg("line", { x1: p0[0], y1: p0[1], x2: p1[0], y2: p1[1], stroke: "var(--ink)", "stroke-width": 2 }, gSlots);
        }
      }
      var lt = pol(rSlot1 + 14, ang(0) - 0.05);
      K.text(gSlots, lt[0] - 6, lt[1] - 6, "slot starts, round " + lap, { "text-anchor": "end", class: "t-muted", "font-size": 10.5 });
    }

    var lastLap = -1;
    function frame(t) {
      var u = Math.floor(t / 4), k = K.mod(u, C), lap = Math.floor(u / C);
      var frac = (t / 4) - u;
      var a = ang(k) + th * (0.5 + 0.0 * frac);
      var p = pol(r1 + 8, a), q = pol(r0 - 14, a);
      hand.setAttribute("x1", q[0]); hand.setAttribute("y1", q[1]); hand.setAttribute("x2", p[0]); hand.setAttribute("y2", p[1]);
      hub.setAttribute("cx", q[0]); hub.setAttribute("cy", q[1]);
      actOutline.setAttribute("d", wedge(r0, r1, ang(k) + 0.012, ang(k + 1) - 0.012));
      tK.textContent = "k = " + k;
      tSub.textContent = "unit " + u + " · round " + lap;
      tSub2.textContent = "slot " + Math.floor(u / 3) + " +" + (4 * K.offsetOf(u)) + " s";
      if (lap !== lastLap) { drawSlots(lap); lastLap = lap; }
      // side panel
      K.clear(panel);
      var h = K.el("p", { class: "small" }, panel);
      K.el("b", null, h, "Your seat: " + mine + ". ");
      h.appendChild(document.createTextNode("It votes whenever the active index equals " + mine + ": every 92 s, with no state lookup beyond the seat itself."));
      var tbl = K.el("table", { class: "data" }, panel);
      var thead = K.el("tr", null, K.el("thead", null, tbl));
      ["round", "vote at", "slot", "in-slot"].forEach(function (c, i) { K.el("th", { class: i ? "num" : "" }, thead, c); });
      var tb = K.el("tbody", null, tbl);
      var first = C * lap + mine;
      if (first < u) first += C;
      for (var i = 0; i < 4; i++) {
        var uu = first + C * i;
        var tr = K.el("tr", { class: i === 0 ? "hl" : "" }, tb);
        K.el("td", null, tr, String(Math.floor(uu / C)));
        K.el("td", { class: "num" }, tr, (4 * uu) + " s");
        K.el("td", { class: "num" }, tr, String(Math.floor(uu / 3)));
        K.el("td", { class: "num" }, tr, "+" + (4 * K.offsetOf(uu)) + " s");
      }
      K.el("p", { class: "small muted" }, panel, "The in-slot offset cycles +0 → +8 → +4 s, one step per round, because 23 is not a multiple of 3. Every seat sees each offset once every 3 rounds (276 s).");
    }

    drawStatic();
    var player = K.player({ t0: 0, t1: 3 * 92 * 4, start: 3 * 92 + 34, speed: 8, controls: ctl, onFrame: frame, autoplay: true, observe: holder,
      speeds: [[2, "2×"], [8, "8×"], [24, "24×"]], label: "Time in seconds",
      format: function (t) { return Math.floor(t) + " s"; } });
  }

  window.FRCPart3 = { init: init };
})();
