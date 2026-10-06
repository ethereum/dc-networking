/* Part 4 (extra): where each FG design picks its target, and what that does to finality.
   Data: window.FRC_TRACES (results/traces.json, written by sim/designs.py traces).
   Each lane: the unit vote stream (coloured by the checkpoint each vote counts for) over a
   finality.watch-style chain (available -> justified -> finalized), on one shared playhead. */
(function () {
  "use strict";
  var K = window.FRC;
  var ORDER = ["ex-instant", "ex-sticky", "round-target", "px-sticky", "rf"];
  var COLOR = { "ex-instant": "var(--s1)", "ex-sticky": "var(--s2)", "round-target": "var(--s3)", "px-sticky": "var(--s4)", "rf": "var(--s5)" };
  var SHORT = { "ex-instant": "Floating heights, instant switch", "ex-sticky": "Floating heights, sticky voters",
    "round-target": "Round-aligned target", "px-sticky": "Prefix counting, sticky voters", "rf": "Rolling FFG" };
  var LAB = { "ex-instant": "instant switch", "ex-sticky": "sticky voters", "round-target": "round-aligned target", "px-sticky": "prefix, sticky", "rf": "Rolling FFG" };

  function init(root) {
    var data = window.FRC_TRACES;
    var host = root.querySelector("[data-lanes]");
    var ctl = root.querySelector("[data-controls]");
    var pHost = root.querySelector("[data-p]");
    var lagHost = root.querySelector("[data-lagchart]");
    var sumHost = root.querySelector("[data-summary]");
    if (!data || !data.runs || !data.runs.length) {
      K.el("p", { class: "muted" }, host, "Trace data missing: run python3 sim/designs.py traces, then build.py.");
      return;
    }
    var runIdx = 0;
    var seg = K.el("div", { class: "seg", role: "group", "aria-label": "Participation" }, pHost);
    data.runs.forEach(function (run, i) {
      var b = K.el("button", { type: "button", "aria-pressed": String(i === runIdx) }, seg, "p = " + run.p.toFixed(1));
      b.addEventListener("click", function () {
        runIdx = i;
        Array.prototype.forEach.call(seg.children, function (c) { c.setAttribute("aria-pressed", "false"); });
        b.setAttribute("aria-pressed", "true");
        build();
      });
    });

    var lanes = [], player = null, run = null;
    var W = 1000, L = 8, R = 8;

    function build() {
      run = data.runs[runIdx];
      K.clear(host); lanes = [];
      var t0 = run.t0, t1 = run.t1;
      function x(t) { return L + (t - t0) * (W - L - R) / (t1 - t0); }
      ORDER.forEach(function (id) {
        var d = run.designs[id];
        if (!d) return;
        var lane = K.el("div", { class: "lane" }, host);
        var head = K.el("div", { class: "lane-head" }, lane);
        var sw = K.el("span", { class: "sw", style: "background:" + COLOR[id] }, head);
        K.el("b", null, head, SHORT[id] + (id === "rf" ? " (δ = 1)" : ""));
        K.el("span", { class: "chip" }, head, "E[lag] " + Math.round(d.lag.mean) + " s · " + Math.round(d.lag.min) + "–" + Math.round(d.lag.max) + " s");
        var live = K.el("span", { class: "readout lane-live" }, head, "");
        K.el("div", { class: "lane-rule small muted" }, lane, d.target_rule || "");
        var H = 92;
        var svg = K.svg("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": (d.label || id) + ": vote stream and chain finality over " + Math.round(t1 - t0) + " seconds." }, K.el("div", { class: "scroll-x" }, lane));
        K.defs(svg);
        // round boundaries (92 s) and slot ticks
        var rs = run.round_s || data.meta.round_s || 92;
        for (var tr = Math.ceil(t0 / rs) * rs; tr <= t1; tr += rs) {
          K.svg("line", { x1: x(tr), x2: x(tr), y1: 2, y2: H - 14, stroke: "var(--line-strong)", "stroke-dasharray": "3 3" }, svg);
          K.text(svg, x(tr) + 3, H - 3, "round " + Math.round(tr / rs), { class: "t-muted t-mono", "font-size": 9.5 });
        }
        // vote stream
        var cw = (x(t0 + 4) - x(t0));
        var units = d.units.map(function (u) {
          var fill, op = 1;
          if (u.kind === "timely") {
            fill = COLOR[id];
            if (id !== "rf" && u.checkpoint !== null && u.checkpoint % 2 === 1) op = 0.55;
          } else if (u.kind === "stale") fill = "url(#hatch-muted)";
          else if (u.kind === "redundant") { fill = "var(--line)"; }
          else fill = "var(--surface-2)";
          var r = K.svg("rect", { x: x(u.t) + 0.5, y: 8, width: Math.max(1, cw - 1), height: 14, rx: 1.5, fill: fill, opacity: op }, svg);
          K.hover(r, [["Unit " + u.u, "· committee " + u.cohort + " · round " + u.round],
            u.kind + (u.checkpoint !== null && u.checkpoint !== undefined ? " vote for checkpoint " + u.checkpoint : "") +
            (u.target_slot !== null && u.target_slot !== undefined ? " (target: block of slot " + u.target_slot + ")" : ""),
            "lands in the block of slot " + u.lands_slot]);
          return { u: u, node: r, op: op };
        });
        K.text(svg, x(t0) + 2, 6, "", {});
        // chain
        var bs = 13;
        var blocks = d.blocks.map(function (b) {
          var g = K.svg("g", null, svg);
          var p = K.svg("path", { d: K.blockPath(x(b.t) - bs / 2, 40, bs), fill: "var(--surface)", stroke: "var(--avail)", "stroke-width": 1.4 }, g);
          K.hover(g, function () {
            return [["Block of slot " + b.slot, "(" + b.t + " s)"],
              "justified " + (b.justified_at !== null ? "at " + Math.round(b.justified_at) + " s (+" + Math.round(b.justified_at - b.t) + " s)" : "after the window"),
              "finalized " + (b.finalized_at !== null ? "at " + Math.round(b.finalized_at) + " s (+" + Math.round(b.finalized_at - b.t) + " s)" : "after the window")];
          });
          return { b: b, p: p, g: g };
        });
        // checkpoint markers (diamond above its target block)
        var cps = (d.checkpoints || []).filter(function (c) { return c.target_slot !== null && c.target_slot * 12 >= t0 && c.target_slot * 12 <= t1; });
        var dense = cps.length > 30;
        var cpNodes = cps.map(function (c) {
          var cxp = x(c.target_slot * 12);
          var m = K.svg("path", { d: "M" + cxp + "," + 29 + "l4,4l-4,4l-4,-4z", fill: "var(--surface)", stroke: COLOR[id], "stroke-width": 1.4, opacity: 0 }, svg);
          if (!dense) K.hover(m, [["Checkpoint " + c.id, "target = block of slot " + c.target_slot],
            "picked " + (c.picked_at !== null ? Math.round(c.picked_at) + " s" : "—") + " · first vote " + (c.first_vote_at !== null ? Math.round(c.first_vote_at) + " s" : "—"),
            "justified " + (c.justified_at !== null ? Math.round(c.justified_at) + " s" : "—") + " · finalized " + (c.finalized_at !== null ? Math.round(c.finalized_at) + " s" : "—")]);
          return { c: c, node: m };
        });
        var ph = K.svg("line", { y1: 2, y2: H - 14, stroke: "var(--ink)", "stroke-width": 1.4, "pointer-events": "none" }, svg);
        lanes.push({ id: id, d: d, units: units, blocks: blocks, cps: cpNodes, ph: ph, live: live, x: x, dense: dense });
      });

      drawLagChart();
      drawSummary();

      K.clear(ctl);
      player = K.player({ t0: t0, t1: t1, start: t0 + 0.42 * (t1 - t0), speed: 12, controls: ctl, onFrame: frame, autoplay: true, observe: host,
        speeds: [[4, "4×"], [12, "12×"], [30, "30×"]], label: "Time in seconds",
        format: function (t) { return Math.round(t) + " s"; } });
    }

    function frame(t) {
      lanes.forEach(function (ln) {
        ln.ph.setAttribute("x1", ln.x(t)); ln.ph.setAttribute("x2", ln.x(t));
        ln.units.forEach(function (o) { o.node.setAttribute("opacity", o.u.t <= t ? o.op : o.op * 0.22); });
        var finHead = null, jHead = null;
        ln.blocks.forEach(function (o) {
          var b = o.b, st;
          if (b.t > t) st = "future";
          else if (b.finalized_at !== null && b.finalized_at <= t) st = "fin";
          else if (b.justified_at !== null && b.justified_at <= t) st = "just";
          else st = "avail";
          if (st === "fin") finHead = b; if (st === "fin" || st === "just") jHead = jHead && jHead.slot > b.slot ? jHead : b;
          o.p.setAttribute("fill", st === "fin" ? "var(--fin)" : st === "just" ? "var(--just-fill)" : "var(--surface)");
          o.p.setAttribute("stroke", st === "fin" ? "var(--fin)" : st === "just" ? "var(--just-line)" : "var(--avail)");
          o.g.setAttribute("opacity", st === "future" ? 0.18 : 1);
        });
        ln.cps.forEach(function (o) {
          var c = o.c;
          var vis = c.picked_at !== null ? c.picked_at <= t : (c.first_vote_at !== null && c.first_vote_at <= t);
          o.node.setAttribute("opacity", vis ? (ln.dense ? 0.55 : 1) : 0);
          o.node.setAttribute("fill", c.finalized_at !== null && c.finalized_at <= t ? "var(--fin)" : (c.justified_at !== null && c.justified_at <= t ? "var(--just-fill)" : "var(--surface)"));
        });
        ln.live.textContent = finHead ? "finalized head is " + Math.round(t - finHead.t) + " s old" : "";
      });
    }

    /* lag by birth time: one line per design */
    function drawLagChart() {
      K.clear(lagHost);
      var W2 = 1000, H2 = 270, Lm = 54, Rm = 196, Tm = 14, Bm = 34;
      var t0 = run.t0, t1 = run.t1;
      var ymax = 0, ymin = 1e9;
      ORDER.forEach(function (id) { var d = run.designs[id]; if (d) d.lag.by_birth.forEach(function (p) { ymax = Math.max(ymax, p[1]); ymin = Math.min(ymin, p[1]); }); });
      ymax = Math.ceil(ymax / 50) * 50; ymin = Math.max(0, Math.floor(ymin / 50) * 50 - 50);
      function x(t) { return Lm + (t - t0) * (W2 - Lm - Rm) / (t1 - t0); }
      function y(v) { return Tm + (1 - (v - ymin) / (ymax - ymin)) * (H2 - Tm - Bm); }
      var svg = K.svg("svg", { viewBox: "0 0 " + W2 + " " + H2, role: "img", "aria-label": "Finality lag of each block against its birth time, one line per design." }, lagHost);
      for (var v = ymin; v <= ymax; v += 50) {
        K.svg("line", { x1: Lm, x2: W2 - Rm, y1: y(v), y2: y(v), stroke: "var(--grid)" }, svg);
        K.text(svg, Lm - 8, y(v) + 4, v + " s", { "text-anchor": "end", class: "t-muted t-mono", "font-size": 10 });
      }
      var rs = run.round_s || data.meta.round_s || 92;
      for (var tr = Math.ceil(t0 / rs) * rs; tr <= t1; tr += rs) K.text(svg, x(tr), H2 - 14, Math.round(tr) + " s", { "text-anchor": "middle", class: "t-muted t-mono", "font-size": 10 });
      K.text(svg, (Lm + W2 - Rm) / 2, H2 - 1, "block birth time (round boundaries every " + rs + " s)", { "text-anchor": "middle", class: "t-muted", "font-size": 11 });
      var ends = [];
      ORDER.forEach(function (id) {
        var d = run.designs[id]; if (!d) return;
        var pts = d.lag.by_birth.filter(function (p) { return p[0] >= t0 && p[0] <= t1; });
        if (!pts.length) return;
        var path = pts.map(function (p, i) { return (i ? "L" : "M") + x(p[0]).toFixed(1) + "," + y(p[1]).toFixed(1); }).join("");
        K.svg("path", { d: path, fill: "none", stroke: COLOR[id], "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
        var last = pts[pts.length - 1];
        // dashed tick at the expected value, at the right edge
        K.svg("line", { x1: W2 - Rm - 18, x2: W2 - Rm + 2, y1: y(d.lag.mean), y2: y(d.lag.mean), stroke: COLOR[id], "stroke-width": 2, "stroke-dasharray": "3 2" }, svg);
        ends.push({ id: id, y: y(d.lag.mean), x: x(last[0]), mean: d.lag.mean });
      });
      // direct labels at the right, ordered by mean, with leader lines
      ends.sort(function (a, b) { return a.y - b.y; });
      var minGap = 17, prev = -1e9;
      ends.forEach(function (e) { e.ly = Math.max(e.y, prev + minGap); prev = e.ly; });
      ends.forEach(function (e) {
        K.svg("line", { x1: W2 - Rm + 4, x2: W2 - Rm + 14, y1: e.y, y2: e.ly, stroke: COLOR[e.id], "stroke-width": 1.5 }, svg);
        K.text(svg, W2 - Rm + 18, e.ly + 4, LAB[e.id] + " · E = " + Math.round(e.mean) + " s", { "font-size": 11 });
      });
      // crosshair
      var hair = K.svg("line", { y1: Tm, y2: H2 - Bm, stroke: "var(--ink)", "stroke-width": 1, opacity: 0 }, svg);
      var hit = K.svg("rect", { x: Lm, y: Tm, width: W2 - Lm - Rm, height: H2 - Tm - Bm, fill: "transparent" }, svg);
      hit.addEventListener("pointermove", function (ev) {
        var pt = svg.createSVGPoint(); pt.x = ev.clientX; pt.y = ev.clientY;
        var loc = pt.matrixTransform(svg.getScreenCTM().inverse());
        var t = t0 + (loc.x - Lm) * (t1 - t0) / (W2 - Lm - Rm);
        hair.setAttribute("x1", loc.x); hair.setAttribute("x2", loc.x); hair.setAttribute("opacity", 0.5);
        var lines = [["born at " + Math.round(t) + " s", ""]];
        ORDER.forEach(function (id) {
          var d = run.designs[id]; if (!d) return;
          var best = null;
          d.lag.by_birth.forEach(function (p) { if (best === null || Math.abs(p[0] - t) < Math.abs(best[0] - t)) best = p; });
          if (best) lines.push([Math.round(best[1]) + " s", SHORT[id]]);
        });
        K.tip(lines, ev);
      });
      hit.addEventListener("pointerleave", function () { hair.setAttribute("opacity", 0); K.untip(); });
    }

    /* best / expected / worst: range bars per design */
    function drawSummary() {
      K.clear(sumHost);
      var ideal = (window.FRC_IDEAL || {});
      var W3 = 1000, rowH = 34, Lm = 250, Rm = 30, Tm = 26;
      var ids = ORDER.filter(function (id) { return run.designs[id]; });
      var H3 = Tm + ids.length * rowH + 30;
      var xmax = 0, xmin = 1e9;
      ids.forEach(function (id) { xmax = Math.max(xmax, run.designs[id].lag.max); xmin = Math.min(xmin, run.designs[id].lag.min, ideal[id] || 1e9); });
      xmax = Math.ceil(xmax / 50) * 50 + 50; xmin = Math.max(0, Math.floor(xmin / 50) * 50);
      function x(v) { return Lm + (v - xmin) / (xmax - xmin) * (W3 - Lm - Rm); }
      var svg = K.svg("svg", { viewBox: "0 0 " + W3 + " " + H3, role: "img", "aria-label": "Best, expected and worst finality lag per design." }, sumHost);
      for (var v = xmin; v <= xmax; v += 50) {
        K.svg("line", { x1: x(v), x2: x(v), y1: Tm - 6, y2: H3 - 24, stroke: "var(--grid)" }, svg);
        K.text(svg, x(v), H3 - 8, v + " s", { "text-anchor": "middle", class: "t-muted t-mono", "font-size": 10 });
      }
      K.text(svg, Lm, 12, "block birth → finalized: bar = best to worst, dot = expected, tick = p95, ◇ = ideal model", { class: "t-muted", "font-size": 11 });
      ids.forEach(function (id, i) {
        var d = run.designs[id], yc = Tm + i * rowH + rowH / 2;
        K.svg("rect", { x: 0, y: yc - rowH / 2 + 2, width: W3, height: rowH - 4, fill: i % 2 ? "transparent" : "var(--surface-2)", opacity: 0.5 }, svg);
        K.text(svg, Lm - 12, yc + 4, SHORT[id], { "text-anchor": "end", "font-size": 12.5, class: "t-strong" });
        K.svg("rect", { x: x(d.lag.min), y: yc - 5, width: Math.max(2, x(d.lag.max) - x(d.lag.min)), height: 10, rx: 4, fill: COLOR[id], opacity: 0.35 }, svg);
        K.svg("line", { x1: x(d.lag.p95), x2: x(d.lag.p95), y1: yc - 8, y2: yc + 8, stroke: COLOR[id], "stroke-width": 2 }, svg);
        var dot = K.svg("circle", { cx: x(d.lag.mean), cy: yc, r: 5.5, fill: COLOR[id], stroke: "var(--surface)", "stroke-width": 2 }, svg);
        K.text(svg, x(d.lag.max) + 8, yc + 4, Math.round(d.lag.mean) + " s", { "font-size": 11.5, class: "t-mono" });
        if (ideal[id]) K.svg("path", { d: "M" + x(ideal[id]) + "," + (yc - 6) + "l5,6l-5,6l-5,-6z", fill: "none", stroke: "var(--ink)", "stroke-width": 1.2 }, svg);
        var hitR = K.svg("rect", { x: Lm, y: yc - rowH / 2 + 2, width: W3 - Lm - Rm, height: rowH - 4, fill: "transparent" }, svg);
        K.hover(hitR, [[Math.round(d.lag.mean) + " s", "expected · " + SHORT[id]],
          "best " + Math.round(d.lag.min) + " s · p95 " + Math.round(d.lag.p95) + " s · worst " + Math.round(d.lag.max) + " s",
          "to inclusion " + Math.round(d.decomp.to_inclusion) + " s + to justified " + Math.round(d.decomp.incl_to_just) + " s + to finalized " + Math.round(d.decomp.just_to_final) + " s"]);
      });
      // table view: every number reachable without hovering
      var rs = run.round_s || data.meta.round_s || 92;
      var wrap = K.el("div", { class: "tbl-wrap" }, sumHost);
      var tbl = K.el("table", { class: "data" }, wrap);
      K.el("caption", null, tbl, "Lag from block birth to finalization at p = " + run.p.toFixed(1) + " (seconds; rounds of " + rs + " s in brackets).");
      var hr = K.el("tr", null, K.el("thead", null, tbl));
      [["design", ""], ["E[time to inclusion]", "num"], ["→ justified", "num"], ["→ finalized", "num"], ["expected", "num"], ["best", "num"], ["p95", "num"], ["worst", "num"], ["ideal", "num"]].forEach(function (h) { K.el("th", { class: h[1] }, hr, h[0]); });
      var tb = K.el("tbody", null, tbl);
      ids.forEach(function (id) {
        var d = run.designs[id], tr = K.el("tr", null, tb);
        var td = K.el("td", null, tr);
        K.el("span", { class: "sw", style: "background:" + COLOR[id] + ";margin-right:6px" }, td);
        td.appendChild(document.createTextNode(SHORT[id]));
        [d.decomp.to_inclusion, d.decomp.incl_to_just, d.decomp.just_to_final].forEach(function (v) { K.el("td", { class: "num" }, tr, Math.round(v) + " s"); });
        [d.lag.mean, d.lag.min, d.lag.p95, d.lag.max].forEach(function (v) { K.el("td", { class: "num" }, tr, Math.round(v) + " s (" + (v / rs).toFixed(2) + ")"); });
        K.el("td", { class: "num" }, tr, ideal[id] ? Math.round(ideal[id]) + " s" : "—");
      });
    }

    build();
  }

  window.FRCPart4 = { init: init };
})();
