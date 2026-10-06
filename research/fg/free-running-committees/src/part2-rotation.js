/* Part 2: Francesco's (index + round) mod C on slot-aligned rounds vs the free-running clock.
   Cells are coloured by in-slot offset (+0 / +4 / +8 s); a selected cohort is traced in time order. */
(function () {
  "use strict";
  var K = window.FRC;
  var C = 23, ROWS = 8;

  // Each mode returns, for row R and column j, the cohort (or -1 for an idle cell) and the global
  // unit index (4 s grid since genesis), plus how many columns the row has.
  var MODES = {
    francesco: {
      label: "Francesco · (index + round) mod 23 · slot-aligned rounds",
      cols: 24,
      cell: function (R, j) { return j === 23 ? { c: -1, u: 24 * R + j } : { c: K.mod(j - R, C), u: 24 * R + j }; },
      rowLabel: function (R) { return "round " + R; },
      rowSub: function (R) { return (96 * R) + " s"; }
    },
    frc: {
      label: "Free-running · cohort = unit mod 23 · drawn on the same 8-slot grid",
      cols: 24,
      cell: function (R, j) { return { c: K.mod(24 * R + j, C), u: 24 * R + j }; },
      rowLabel: function (R) { return "slots " + (8 * R) + "–" + (8 * R + 7); },
      rowSub: function (R) { return (96 * R) + " s"; }
    },
    frcRound: {
      label: "Free-running · one row per 92 s round",
      cols: 23,
      cell: function (r, k) { return { c: k, u: 23 * r + k }; },
      rowLabel: function (r) { return "round " + r; },
      rowSub: function (r) { return (92 * r) + " s"; }
    }
  };

  function votesOf(mode, c, nRows) {
    // global units at which cohort c votes, over nRows rows, in time order
    var m = MODES[mode], out = [];
    for (var R = 0; R < nRows; R++) for (var j = 0; j < m.cols; j++) {
      var cell = m.cell(R, j);
      if (cell.c === c) out.push(cell.u);
    }
    return out.sort(function (a, b) { return a - b; });
  }
  function gaps(us) { var g = []; for (var i = 1; i < us.length; i++) g.push(4 * (us[i] - us[i - 1])); return g; }

  function init(root) {
    var holder = root.querySelector("[data-fig]");
    var segHost = root.querySelector("[data-modes]");
    var readout = root.querySelector("[data-readout]");
    var stripHost = root.querySelector("[data-strip]");
    var mode = "francesco", sel = 22;

    var seg = K.el("div", { class: "seg", role: "group", "aria-label": "Schedule" }, segHost);
    [["francesco", "Francesco, slot-aligned"], ["frc", "Free-running, slot view"], ["frcRound", "Free-running, round view"]].forEach(function (mdef) {
      var b = K.el("button", { type: "button", "aria-pressed": String(mdef[0] === mode) }, seg, mdef[1]);
      b.addEventListener("click", function () {
        mode = mdef[0];
        Array.prototype.forEach.call(seg.children, function (c) { c.setAttribute("aria-pressed", "false"); });
        b.setAttribute("aria-pressed", "true");
        draw();
      });
    });

    var W = 1000, L = 112, cw = 35.5, ch = 30, top = 44;
    function draw() {
      K.clear(holder);
      var m = MODES[mode];
      var H = top + ROWS * ch + 26;
      var svg = K.svg("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": m.label + ". Rows are rounds, columns are 4-second units; each cell names the committee voting in it and is shaded by its in-slot offset." }, holder);
      K.defs(svg);
      // column header: slots (only meaningful for slot-aligned grids)
      if (mode !== "frcRound") {
        for (var s = 0; s < 8; s++) {
          K.text(svg, L + (3 * s + 1.5) * cw, 16, "slot " + s, { "text-anchor": "middle", class: "t-muted", "font-size": 11 });
          K.svg("line", { x1: L + 3 * s * cw, x2: L + 3 * s * cw, y1: 22, y2: top + ROWS * ch, stroke: "var(--line-strong)" }, svg);
        }
        K.svg("line", { x1: L + 24 * cw, x2: L + 24 * cw, y1: 22, y2: top + ROWS * ch, stroke: "var(--line-strong)" }, svg);
        for (var j = 0; j < 24; j++) K.text(svg, L + (j + 0.5) * cw, 36, "+" + (4 * (j % 3)), { "text-anchor": "middle", class: "t-muted t-mono", "font-size": 9.5 });
      } else {
        for (var k = 0; k < 23; k++) K.text(svg, L + (k + 0.5) * cw, 36, String(k), { "text-anchor": "middle", class: "t-muted t-mono", "font-size": 9.5 });
        K.text(svg, L, 16, "committee index k (fixed order); slot boundaries (dark ticks) drift 4 s earlier every round", { class: "t-muted", "font-size": 11 });
      }
      var centers = [];
      for (var R = 0; R < ROWS; R++) {
        var y = top + R * ch;
        K.text(svg, L - 10, y + 13, m.rowLabel(R), { "text-anchor": "end", class: "t-strong", "font-size": 11.5 });
        K.text(svg, L - 10, y + 25, m.rowSub(R), { "text-anchor": "end", class: "t-muted t-mono", "font-size": 9.5 });
        for (var jj = 0; jj < m.cols; jj++) {
          var cell = m.cell(R, jj);
          var x0 = L + jj * cw;
          var off = K.offsetOf(cell.u);
          var g = K.svg("g", null, svg);
          var fill = cell.c < 0 ? "url(#hatch-idle)" : "var(--off" + off + ")";
          var rect = K.svg("rect", { x: x0 + 1, y: y + 1, width: cw - 2, height: ch - 2, rx: 3, fill: fill }, g);
          if (cell.c >= 0) {
            var isSel = cell.c === sel;
            K.text(g, x0 + cw / 2, y + ch / 2 + 4, String(cell.c), { "text-anchor": "middle", "font-size": 11.5,
              style: "fill: var(--off-ink" + off + "); font-weight:" + (isSel ? 700 : 450) });
            if (isSel) {
              rect.setAttribute("stroke", "var(--ink)"); rect.setAttribute("stroke-width", 2.2);
              centers.push({ u: cell.u, x: x0 + cw / 2, y: y + ch / 2 });
            }
            g.style.cursor = "pointer";
            (function (cell, R, jj) {
              K.hover(g, [["Committee " + cell.c, "unit " + cell.u],
                "t = " + (4 * cell.u) + " s · slot " + Math.floor(cell.u / 3) + " +" + (4 * K.offsetOf(cell.u)) + " s",
                "click to trace this committee"]);
              g.addEventListener("click", function () { sel = cell.c; draw(); });
            })(cell, R, jj);
          } else {
            K.hover(g, ["Idle unit: its aggregate would land in the next round, so Q17 drops it"]);
          }
          // round boundary (free-running, slot view): unit index divisible by 23
          if (mode === "frc" && cell.u % 23 === 0) {
            K.svg("line", { x1: x0 + 0.5, x2: x0 + 0.5, y1: y - 2, y2: y + ch + 2, stroke: "var(--ink)", "stroke-width": 2.4 }, svg);
          }
          // slot boundary (free-running, round view)
          if (mode === "frcRound" && cell.u % 3 === 0) {
            K.svg("line", { x1: x0 + 0.5, x2: x0 + 0.5, y1: y + 1, y2: y + ch - 1, stroke: "var(--ink)", "stroke-width": 2 }, svg);
          }
        }
      }
      // trace the selected cohort in time order
      centers.sort(function (a, b) { return a.u - b.u; });
      if (centers.length > 1) {
        var d = centers.map(function (p, i) { return (i ? "L" : "M") + p.x + "," + p.y; }).join("");
        K.svg("path", { d: d, fill: "none", stroke: "var(--ink)", "stroke-width": 1.4, "stroke-dasharray": "4 3", opacity: 0.75, "pointer-events": "none" }, svg);
      }
      // legend row under the grid
      var ly = top + ROWS * ch + 18;
      [["var(--off0)", "+0 s"], ["var(--off1)", "+4 s"], ["var(--off2)", "+8 s"]].forEach(function (lg, i) {
        K.svg("rect", { x: L + i * 70, y: ly - 9, width: 14, height: 10, rx: 2, fill: lg[0], stroke: "var(--line-strong)" }, svg);
        K.text(svg, L + i * 70 + 19, ly, lg[1], { class: "t-muted", "font-size": 11 });
      });
      var extra = mode === "francesco" ? "hatched = idle unit" : (mode === "frc" ? "thick bar = a round begins (committee 0)" : "thick tick = a slot begins");
      if (mode === "francesco") K.svg("rect", { x: L + 222, y: ly - 9, width: 14, height: 10, rx: 2, fill: "url(#hatch-idle)" }, svg);
      K.text(svg, L + (mode === "francesco" ? 241 : 222), ly, extra, { class: "t-muted", "font-size": 11 });
      K.text(svg, W - 8, ly, "click a cell to trace a committee", { "text-anchor": "end", class: "t-muted", "font-size": 11 });

      updateReadout();
    }

    function updateReadout() {
      var nR = 23 * 3;   // a full cycle for every schedule shown here
      var fr = gaps(votesOf("francesco", sel, nR)), fc = gaps(votesOf("frcRound", sel, nR));
      function st(g) { return { min: Math.min.apply(null, g), max: Math.max.apply(null, g), mean: g.reduce(function (a, b) { return a + b; }, 0) / g.length }; }
      var a = st(fr), b = st(fc);
      // all-cohort extremes
      var allMin = 1e9, allMax = 0;
      for (var c = 0; c < C; c++) { var g = gaps(votesOf("francesco", c, nR)); allMin = Math.min(allMin, Math.min.apply(null, g)); allMax = Math.max(allMax, Math.max.apply(null, g)); }
      K.clear(readout);
      var p = K.el("p", { class: "small" }, readout);
      p.appendChild(document.createTextNode("Committee " + sel + " over 69 rounds: "));
      K.el("b", null, p, "Francesco: gaps " + a.min + "–" + a.max + " s (mean " + a.mean.toFixed(1) + " s)");
      p.appendChild(document.createTextNode("; "));
      K.el("b", null, p, "free-running: every gap " + b.min + " s");
      p.appendChild(document.createTextNode(". Across all committees, Francesco's slot-aligned rotation ranges from " + allMin + " s (the committee that wraps from the last seat to the first votes twice within " + allMin + " s) to " + allMax + " s."));
      drawStrip();
    }

    function drawStrip() {
      K.clear(stripHost);
      var W2 = 1000, L2 = 112, T = 8 * 96;
      var svg = K.svg("svg", { viewBox: "0 0 " + W2 + " 92", role: "img", "aria-label": "Absolute vote times of the selected committee under both schedules over 768 seconds." }, stripHost);
      function x(t) { return L2 + t * (W2 - L2 - 12) / T; }
      for (var t = 0; t <= T; t += 96) {
        K.svg("line", { x1: x(t), x2: x(t), y1: 6, y2: 78, stroke: "var(--grid)" }, svg);
        K.text(svg, x(t), 90, t + " s", { "text-anchor": "middle", class: "t-muted t-mono", "font-size": 9.5 });
      }
      [["francesco", "Francesco", 22, "var(--agg)"], ["frcRound", "free-running", 56, "var(--vote)"]].forEach(function (row) {
        K.text(svg, L2 - 10, row[2] + 4, row[1], { "text-anchor": "end", class: "t-strong", "font-size": 11.5 });
        K.svg("line", { x1: x(0), x2: x(T), y1: row[2], y2: row[2], stroke: "var(--line)" }, svg);
        var us = votesOf(row[0], sel, 9).filter(function (u) { return 4 * u <= T; });
        us.forEach(function (u, i) {
          K.svg("rect", { x: x(4 * u) - 1.5, y: row[2] - 9, width: 3, height: 18, rx: 1.5, fill: row[3] }, svg);
          if (i > 0) {
            var gp = 4 * (u - us[i - 1]);
            K.text(svg, (x(4 * u) + x(4 * us[i - 1])) / 2, row[2] - 12, gp + " s", { "text-anchor": "middle", class: "t-mono", "font-size": 10, style: gp < 40 ? "fill: var(--adv); font-weight:700" : "" });
          }
        });
      });
    }

    draw();
  }

  window.FRCPart2 = { init: init, votesOf: votesOf, gaps: gaps };
})();
