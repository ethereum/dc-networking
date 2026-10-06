/* Part 1: inside the slot. A committee every 4 s: 4 s vote + 4 s on-time aggregation, then a
   slot-synchronous IHAVE/IWANT window (+8..+10 s) and a final aggregation (+10..+12 s) that hands
   the next proposer the best aggregate. */
(function () {
  "use strict";
  var K = window.FRC;

  function incBlock(u) { return 12 * Math.ceil((4 * u + 8) / 12); }      // block time that carries unit u
  function comm(u) { return K.mod(u, K.C); }

  function init(root) {
    var holder = root.querySelector("[data-fig]");
    var ctl = root.querySelector("[data-controls]");
    var status = root.querySelector("[data-status]");
    var W = 1000, L = 150, R = 22, T0 = 78, T1 = 126;
    var U0 = 20, U1 = 29;
    var rowH = 31, top = 104;
    var H = top + (U1 - U0 + 1) * rowH + 10;
    function x(t) { return L + (t - T0) * (W - L - R) / (T1 - T0); }
    function cx(t) { return Math.max(x(T0), Math.min(x(T1), x(t))); }

    var svg = K.svg("svg", { viewBox: "0 0 " + W + " " + H, role: "img",
      "aria-label": "Gantt chart over slots 7 to 9. One committee starts every 4 seconds; each votes for 4 seconds and its aggregators publish for the next 4 seconds. In every slot, an IHAVE/IWANT pull window runs from +8 to +10 s and a final aggregation from +10 to +12 s, so the block at the slot boundary carries the best aggregate of exactly three committees. Committee 0 of round 1 starts at 92 s, in the unit the slot-aligned round leaves idle." }, holder);
    K.defs(svg);

    var gBands = K.svg("g", null, svg);
    var gAxis = K.svg("g", null, svg);
    var gRows = K.svg("g", null, svg);
    var gTop = K.svg("g", null, svg);

    // slot-synchronous bands: pull window and final aggregation, full height
    for (var s = 6; s <= 10; s++) {
      var ts = 12 * s;
      [[ts + 8, ts + 10, "var(--repair-soft)"], [ts + 10, ts + 12, "var(--agg-soft)"]].forEach(function (b) {
        var a = Math.max(b[0], T0), e = Math.min(b[1], T1);
        if (e <= a) return;
        K.svg("rect", { x: x(a), y: 70, width: x(e) - x(a), height: H - 70 - 6, fill: b[2], opacity: 0.55 }, gBands);
      });
    }
    // slot grid
    for (var t = 84; t <= 120; t += 4) {
      var isSlot = t % 12 === 0;
      K.svg("line", { x1: x(t), x2: x(t), y1: isSlot ? 40 : 70, y2: H - 6, stroke: isSlot ? "var(--line-strong)" : "var(--grid)", "stroke-width": 1 }, gAxis);
      if (!isSlot) K.text(gAxis, x(t), 67, "+" + (t % 12) + " s", { "text-anchor": "middle", class: "t-muted t-mono", "font-size": 10.5 });
    }
    for (s = 7; s <= 9; s++) {
      K.text(gAxis, x(12 * s + 6), 16, "slot " + s, { "text-anchor": "middle", class: "t-strong", "font-size": 12.5 });
    }
    // gossip-mode strip
    K.text(gAxis, L - 10, 52, "gossip", { "text-anchor": "end", class: "t-muted", "font-size": 11 });
    K.svg("rect", { x: x(T0), y: 43, width: x(T1) - x(T0), height: 11, fill: "var(--surface-2)", rx: 2 }, gAxis);
    for (s = 6; s <= 10; s++) {
      var pa = Math.max(12 * s + 8, T0), pe = Math.min(12 * s + 10, T1);
      if (pe > pa) K.svg("rect", { x: x(pa), y: 43, width: x(pe) - x(pa), height: 11, fill: "url(#hatch-repair)", rx: 2 }, gAxis);
    }
    [84, 96, 108].forEach(function (ts) { K.text(gAxis, x(ts + 4), 51.5, "push only", { "text-anchor": "middle", class: "t-muted", "font-size": 9.5 }); });

    // blocks at slot boundaries
    var blocks = [];
    [84, 96, 108, 120].forEach(function (tb) {
      var g = K.svg("g", { class: "blk", tabindex: 0 }, gTop);
      var p = K.svg("path", { d: K.blockPath(x(tb) - 8, 22, 16), fill: "var(--surface)", stroke: "var(--avail)", "stroke-width": 1.6 }, g);
      var carried = [tb / 4 - 4, tb / 4 - 3, tb / 4 - 2].map(comm);
      K.hover(g, [["Block of slot " + (tb / 12), "proposed at " + tb + " s"],
        "carries committees " + carried.join(", "),
        "(their on-time and final aggregates)"]);
      blocks.push({ t: tb, path: p });
    });

    // round boundary at 92 s (unit 23 = committee 0 of round 1)
    K.svg("line", { x1: x(92), x2: x(92), y1: 70, y2: H - 6, stroke: "var(--ink)", "stroke-width": 1.2, "stroke-dasharray": "3 3" }, gTop);
    K.text(gTop, x(92) + 5, 84, "round 1 begins: committee 0 (Q17 left this unit idle)", { class: "t-strong", "font-size": 11 });

    // rows
    var rows = [];
    for (var u = U0; u <= U1; u++) {
      var y = top + (u - U0) * rowH;
      var g = K.svg("g", { tabindex: 0, class: "urow" }, gRows);
      var k = comm(u), rnd = Math.floor(u / K.C);
      K.text(g, L - 10, y + 13, "committee " + k, { "text-anchor": "end", class: "t-strong", "font-size": 12 });
      K.text(g, L - 10, y + 25, "r" + rnd + " · u" + u + " · +" + (4 * K.offsetOf(u)) + " s", { "text-anchor": "end", class: "t-muted t-mono", "font-size": 9.5 });
      var tv = 4 * u, tb = incBlock(u);
      var segs = [];
      segs.push({ a: tv, b: tv + 4, y: y + 3, h: 12, fill: "var(--vote)", kind: "vote" });
      segs.push({ a: tv + 4, b: tv + 8, y: y + 3, h: 12, fill: "var(--agg)", kind: "agg" });
      if (tb - 4 > tv + 8) K.svg("line", { x1: cx(tv + 8), x2: cx(tb - 4), y1: y + 21, y2: y + 21, stroke: "var(--line-strong)", "stroke-dasharray": "2 3" }, g);
      segs.push({ a: tb - 4, b: tb - 2, y: y + 17, h: 8, fill: "url(#hatch-repair)", kind: "repair" });
      segs.push({ a: tb - 2, b: tb, y: y + 17, h: 8, fill: "url(#hatch-agg)", kind: "final" });
      var nodes = segs.map(function (sg) {
        var a = Math.max(sg.a, T0), b = Math.min(sg.b, T1);
        if (b <= a) return null;
        var r = K.svg("rect", { x: x(a) + 1, y: sg.y, width: Math.max(0, x(b) - x(a) - 2), height: sg.h, rx: 2.5, fill: sg.fill }, g);
        if (sg.kind === "repair" || sg.kind === "final") r.setAttribute("stroke", sg.kind === "repair" ? "var(--repair)" : "var(--agg)");
        return { seg: sg, node: r };
      }).filter(Boolean);
      // inclusion tick at the block
      if (tb <= T1) {
        K.svg("path", { d: "M" + x(tb) + "," + (y + 21) + "l-5,-4v8z", fill: "var(--avail)" }, g);
      }
      (function (u, k, tv, tb, rnd) {
        K.hover(g, [["Committee " + k, "(unit " + u + ", round " + rnd + ")"],
          "votes " + tv + "–" + (tv + 4) + " s (slot " + Math.floor(tv / 12) + " +" + (tv % 12) + " s), push only",
          "on-time aggregates published at " + (tv + 4) + " s, propagated by " + (tv + 8) + " s",
          "IHAVE/IWANT pull " + (tb - 4) + "–" + (tb - 2) + " s, final aggregate " + (tb - 2) + "–" + tb + " s",
          "included by the block of slot " + (tb / 12) + " (" + tb + " s)"]);
        g.addEventListener("pointerenter", function () { highlight(tb); });
        g.addEventListener("pointerleave", function () { highlight(null); });
        g.addEventListener("focus", function () { highlight(tb); });
        g.addEventListener("blur", function () { highlight(null); });
      })(u, k, tv, tb, rnd);
      rows.push({ u: u, g: g, nodes: nodes, tb: tb });
    }

    function highlight(tb) {
      rows.forEach(function (r) { r.g.style.opacity = tb === null || r.tb === tb ? 1 : 0.28; });
      blocks.forEach(function (b) { b.path.setAttribute("stroke-width", tb === b.t ? 3 : 1.6); });
    }

    // playhead
    var ph = K.svg("line", { y1: 40, y2: H - 6, stroke: "var(--ink)", "stroke-width": 1.5 }, gTop);
    var phDot = K.svg("circle", { r: 4, cy: 40, fill: "var(--ink)" }, gTop);

    function frame(t) {
      ph.setAttribute("x1", x(t)); ph.setAttribute("x2", x(t)); phDot.setAttribute("cx", x(t));
      rows.forEach(function (r) {
        r.nodes.forEach(function (n) {
          var on = t >= n.seg.a && t < n.seg.b;
          n.node.setAttribute("opacity", on ? 1 : (t >= n.seg.b ? 0.55 : 0.85));
          n.node.setAttribute("stroke-width", on ? 2 : (n.seg.kind === "repair" || n.seg.kind === "final" ? 0.8 : 0));
          if (on && (n.seg.kind === "vote" || n.seg.kind === "agg")) n.node.setAttribute("stroke", "var(--ink)");
          else if (n.seg.kind === "vote" || n.seg.kind === "agg") n.node.removeAttribute("stroke");
        });
      });
      blocks.forEach(function (b) {
        var landed = t >= b.t;
        b.path.setAttribute("fill", landed ? "var(--just-fill)" : "var(--surface)");
      });
      status.textContent = describe(t);
    }

    function describe(t) {
      var s = Math.floor(t / 12), off = t - 12 * s, uv = Math.floor(t / 4);
      var parts = ["t = " + t.toFixed(1) + " s · slot " + s + " +" + off.toFixed(1) + " s."];
      parts.push("Committee " + comm(uv) + " votes" + (uv % K.C === 0 ? " (first committee of round " + Math.floor(uv / K.C) + ")" : "") + ".");
      parts.push("Committee " + comm(uv - 1) + "'s aggregators propagate their on-time aggregates.");
      if (off >= 8 && off < 10) parts.push("IHAVE/IWANT window: nodes pull missing votes of committees " + [3 * s - 1, 3 * s, 3 * s + 1].map(comm).join(", ") + ".");
      else if (off >= 10) parts.push("Final aggregation: late aggregators publish best aggregates of committees " + [3 * s - 1, 3 * s, 3 * s + 1].map(comm).join(", ") + " for the block at " + (12 * s + 12) + " s.");
      else if (off < 1) parts.push("The block of slot " + s + " is proposed; it carries committees " + [3 * s - 4, 3 * s - 3, 3 * s - 2].map(comm).join(", ") + ".");
      return parts.join(" ");
    }

    K.player({ t0: T0, t1: T1, start: 90, speed: 4, controls: ctl, onFrame: frame, autoplay: true, observe: holder,
      speeds: [[1, "1×"], [4, "4×"], [10, "10×"]], label: "Time in seconds",
      format: function (t) { return "slot " + Math.floor(t / 12) + " +" + (t % 12).toFixed(1) + " s"; } });
  }

  window.FRCPart1 = { init: init };
})();
