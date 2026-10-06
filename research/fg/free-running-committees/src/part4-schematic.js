/* Part 4a: where each design picks its target, in the ideal model (no aggregation or inclusion
   delay, everyone online; time in rounds of 23 units). One tracked checkpoint per row shows
   pick -> first vote -> justified -> finalized. */
(function () {
  "use strict";
  var K = window.FRC;
  var ROUND_S = 92;

  // Declarative specs. segments: voting periods [a, b) by checkpoint; kind "timely" counts
  // toward the checkpoint's quorum, "extra" counts but is not needed, "stale" names a closed height.
  function heightsEvery(step, t0, t1) {
    var segs = [], picks = [], i = 0;
    for (var t = t0; t < t1 - 1e-9; t += step, i++) {
      segs.push({ a: t, b: Math.min(t + step, t1), kind: "timely", cp: i });
      picks.push({ t: t, cp: i });
    }
    return { segs: segs, picks: picks };
  }
  var SPECS = [
    (function () {
      var h = heightsEvery(2 / 3, 0, 10 / 3);
      return { id: "ex-instant", name: "Floating heights, instant switch", segs: h.segs, picks: h.picks,
        track: { pick: 4 / 3, first: 4 / 3, just: 2, fin: 8 / 3 }, lag: [4 / 3, 2], mean: 5 / 3,
        note: "entry = quorum block, voted at once" };
    })(),
    (function () {
      var segs = [], picks = [];
      for (var r = 0; r <= 3; r++) {
        segs.push({ a: r, b: Math.min(r + 2 / 3, 10 / 3), kind: "timely", cp: r });
        if (r + 2 / 3 < 10 / 3) segs.push({ a: r + 2 / 3, b: Math.min(r + 1, 10 / 3), kind: "stale", cp: r });
        picks.push({ t: r - 1 / 3, cp: r });
      }
      return { id: "ex-sticky", name: "Floating heights, sticky voters", segs: segs, picks: picks.filter(function (p) { return p.t >= 0; }),
        track: { pick: 2 / 3, first: 1, just: 5 / 3, fin: 8 / 3 }, lag: [2, 3], mean: 5 / 2,
        note: "same entry, first voted next round" };
    })(),
    (function () {
      var segs = [], picks = [];
      for (var r = 0; r <= 3; r++) {
        segs.push({ a: r, b: Math.min(r + 2 / 3, 10 / 3), kind: "timely", cp: r });
        if (r + 2 / 3 < 10 / 3) segs.push({ a: r + 2 / 3, b: Math.min(r + 1, 10 / 3), kind: "extra", cp: r });
        picks.push({ t: r, cp: r });
      }
      return { id: "round-target", name: "Round-aligned target", segs: segs, picks: picks,
        track: { pick: 1, first: 1, just: 5 / 3, fin: 8 / 3 }, lag: [5 / 3, 8 / 3], mean: 13 / 6,
        note: "head at the round start" };
    })(),
    (function () {
      var segs = [], picks = [];
      for (var r = 0; r <= 3; r++) {
        segs.push({ a: r, b: Math.min(r + 1, 10 / 3), kind: "timely", cp: r });
        picks.push({ t: r + 1 / 3, cp: r });
      }
      return { id: "px-sticky", name: "Prefix counting, sticky voters", segs: segs, picks: picks.filter(function (p) { return p.t <= 10 / 3; }),
        track: { pick: 4 / 3, first: 4 / 3, just: 2, fin: 8 / 3 }, lag: [4 / 3, 7 / 3], mean: 11 / 6,
        note: "votes name their head; J* deepens" };
    })(),
    { id: "rf", name: "Rolling FFG", continuous: true, segs: [{ a: 0, b: 10 / 3, kind: "timely", cp: 0 }], picks: [],
      track: { pick: 1, first: 1, just: 5 / 3, fin: 7 / 3 }, lag: [4 / 3, 4 / 3], mean: 4 / 3,
      note: "every unit is a checkpoint" }
  ];
  var COLOR = { "ex-instant": "var(--s1)", "ex-sticky": "var(--s2)", "round-target": "var(--s3)", "px-sticky": "var(--s4)", "rf": "var(--s5)" };

  function frac(v) {
    var table = [[1 / 3, "1/3"], [2 / 3, "2/3"], [1, "1"], [4 / 3, "4/3"], [5 / 3, "5/3"], [2, "2"], [13 / 6, "13/6"], [7 / 3, "7/3"], [5 / 2, "5/2"], [8 / 3, "8/3"], [3, "3"], [11 / 6, "11/6"]];
    for (var i = 0; i < table.length; i++) if (Math.abs(v - table[i][0]) < 1e-6) return table[i][1];
    return v.toFixed(2);
  }

  function init(host) {
    var specs = SPECS.slice();
    specs = specs.filter(Boolean);
    var W = 1000, L = 210, Rr = 200, rowH = 60, top = 30;
    var T1 = 10 / 3;
    var H = top + specs.length * rowH + 8;
    function x(t) { return L + t * (W - L - Rr) / T1; }
    var svg = K.svg("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "Ideal-model schematic: for each design, when checkpoints are picked, which votes count for them, and when one tracked checkpoint is justified and finalized." }, host);
    K.defs(svg);
    for (var r = 0; r <= 3; r++) {
      K.svg("line", { x1: x(r), x2: x(r), y1: 18, y2: H - 6, stroke: "var(--line-strong)", "stroke-dasharray": r ? "3 3" : null }, svg);
      K.text(svg, x(r), 13, "round " + r, { "text-anchor": "middle", class: "t-muted t-mono", "font-size": 10 });
    }
    K.text(svg, W - Rr + 16, 13, "lag of a block (ideal), rounds", { class: "t-muted", "font-size": 10.5 });
    specs.forEach(function (sp, i) {
      var y = top + i * rowH + 8;
      var col = COLOR[sp.id];
      K.text(svg, L - 12, y + 10, sp.name, { "text-anchor": "end", class: "t-strong", "font-size": 12 });
      K.text(svg, L - 12, y + 24, sp.note, { "text-anchor": "end", class: "t-muted", "font-size": 9.5 });
      // vote bars
      sp.segs.forEach(function (s) {
        var fill = s.kind === "stale" ? "url(#hatch-muted)" : col;
        var op = s.kind === "timely" ? (sp.continuous ? 0.75 : (s.cp % 2 ? 0.55 : 0.95)) : (s.kind === "extra" ? 0.28 : 1);
        var rct = K.svg("rect", { x: x(s.a) + 0.5, y: y, width: Math.max(1, x(s.b) - x(s.a) - 1), height: 12, rx: 2, fill: fill, opacity: op }, svg);
        K.hover(rct, [[s.kind === "stale" ? "Stale votes" : (s.kind === "extra" ? "Votes after the quorum" : "Votes that count"), ""],
          s.kind === "stale" ? "they name a height that already closed (still rewarded)" : (sp.continuous ? "each vote counts for every unit checkpoint in its window" : "for checkpoint picked at round " + frac(sp.picks[Math.min(s.cp, sp.picks.length - 1)] ? sp.picks[Math.min(s.cp, sp.picks.length - 1)].t : 0)),
          frac(s.a) + " → " + frac(s.b) + " rounds"]);
      });
      // picks
      sp.picks.forEach(function (p) {
        if (p.t < 0 || p.t > T1) return;
        K.svg("path", { d: "M" + x(p.t) + "," + (y - 9) + "l4,4l-4,4l-4,-4z", fill: "var(--surface)", stroke: col, "stroke-width": 1.4 }, svg);
      });
      // tracked checkpoint
      var tr = sp.track, yy = y + 26;
      K.svg("line", { x1: x(tr.pick), x2: x(tr.fin), y1: yy, y2: yy, stroke: "var(--ink-2)", "stroke-width": 1.2 }, svg);
      K.svg("path", { d: "M" + x(tr.pick) + "," + (yy - 5) + "l4,4l-4,4l-4,-4z", fill: col, stroke: "var(--surface)", "stroke-width": 1 }, svg);
      if (tr.first > tr.pick + 1e-9) {
        K.svg("line", { x1: x(tr.pick), x2: x(tr.first), y1: yy, y2: yy, stroke: "var(--adv)", "stroke-width": 2.4 }, svg);
        K.text(svg, (x(tr.pick) + x(tr.first)) / 2, yy + 13, "waits " + frac(tr.first - tr.pick), { "text-anchor": "middle", "font-size": 9.5, style: "fill: var(--adv); font-weight: 600" });
      }
      K.svg("rect", { x: x(tr.just) - 4, y: yy - 4, width: 8, height: 8, rx: 1.5, fill: "var(--just-fill)", stroke: "var(--just-line)", "stroke-width": 1.4 }, svg);
      K.svg("rect", { x: x(tr.fin) - 4, y: yy - 4, width: 8, height: 8, rx: 1.5, fill: "var(--fin)" }, svg);
      K.text(svg, x(tr.just), yy - 7, "J", { "text-anchor": "middle", class: "t-muted", "font-size": 9 });
      K.text(svg, x(tr.fin), yy - 7, "F", { "text-anchor": "middle", class: "t-muted", "font-size": 9 });
      K.text(svg, (x(Math.max(tr.first, tr.pick)) + x(tr.fin)) / 2, yy + 14, (sp.continuous ? "each block final after " : "target final after ") + frac(tr.fin - tr.pick) + " rounds", { "text-anchor": "middle", class: "t-mono", "font-size": 9.5 });
      // lag range
      var lx = W - Rr + 16;
      var lo = sp.lag[0], hi = sp.lag[1];
      K.text(svg, lx, y + 10, (Math.abs(hi - lo) < 1e-9 ? frac(lo) + " for every block" : frac(lo) + " to " + frac(hi)) , { class: "t-mono", "font-size": 11 });
      K.text(svg, lx, y + 25, "E = " + frac(sp.mean) + " ≈ " + Math.round(sp.mean * ROUND_S) + " s", { class: "t-strong t-mono", "font-size": 11 });
    });
  }

  window.FRCSchematic = { init: init, SPECS: SPECS };
})();
