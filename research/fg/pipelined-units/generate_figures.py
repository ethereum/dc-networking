#!/usr/bin/env python3
"""Figures for research/fg/pipelined-units/README.md.

Every figure is authored here as an Excalidraw scene and written to
excalidraw/<name>.excalidraw (editable in the VS Code Excalidraw extension or on
excalidraw.com), then rendered to figures/<name>.svg by the small renderer at
the bottom of this file. The .excalidraw files are therefore the source of
truth and the SVGs are derived. One figure is repurposed from the existing
research/ac/fg_slot_structure_current.excalidraw: its AC bands are kept and
its FG network band is swapped for the pipelined units.

Colours follow the existing Excalidraw diagrams (Open Color palette, Nunito
text, #243447 ink, #94a3b8 muted, #e9ecef bands at 10 % opacity). The one
deliberate change: aggregation phases are orange (#e8590c) instead of the
grape (#9c36b5) used in fg_slot_structure_current, because blue/grape is
indistinguishable under deuteranopia (OKLab dE 2.8) while blue/orange is not
(dE 24). Vote phases keep the blue (#1971c2) of the existing FG arrows.

Stdlib only. Regenerate everything:

    python3 research/fg/pipelined-units/generate_figures.py

Add --png to also rasterise the SVGs with Inkscape (if installed at the
usual macOS location) into figures/png/ for HackMD uploads.
"""

import json
import math
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EXC_DIR = os.path.join(HERE, "excalidraw")
FIG_DIR = os.path.join(HERE, "figures")
PNG_DIR = os.path.join(FIG_DIR, "png")
SOURCE_FIG = os.path.join(HERE, "..", "..", "ac", "fg_slot_structure_current.excalidraw")

# --- schedule parameters -----------------------------------------------------
SLOT = 12          # s
SLOTS = 8          # slots per round
VOTE = 4           # s, vote phase of a unit
AGG = 4            # s, aggregation phase of a unit
UNIT = VOTE + AGG  # 8 s
ROUND = SLOT * SLOTS  # 96 s
UNITS = [(i, 4 * i, 4 * i + VOTE, 4 * i + UNIT)
         for i in range(ROUND // 4) if 4 * i + UNIT <= ROUND]   # 23 units
assert len(UNITS) == 23
TODAY_UNITS = 32   # one attestation slot per validator per 32-slot epoch

# --- palette (Open Color, as in the existing diagrams) ------------------------
INK = "#243447"
MUTED = "#94a3b8"
RULE = "#334155"
BAND = "#e9ecef"
NOTE = "#1e1e1e"
WHITE = "#ffffff"
VOTE_C, VOTE_BG = "#1971c2", "#a5d8ff"
AGG_C, AGG_BG = "#e8590c", "#ffd8a8"
BLOCK_C, BLOCK_BG = "#e9b949", "#ffec99"
DROP_C = "#e03131"
OK_C = "#099268"

FONT_MAIN = 6   # Nunito
FONT_HAND = 5   # Excalifont (margin commentary only)
LINE_HEIGHT = 1.35
CHAR_W = 0.56   # average glyph width / font size, for text boxes

rng = random.Random(24527)  # deterministic seeds/nonces; 24527 = dc ethresearch topic id
STAMP = 1790000000000


# =============================================================================
# Scene builder (writes Excalidraw JSON)
# =============================================================================
class Scene:
    def __init__(self, name):
        self.name = name
        self.els = []
        self.n = 0

    def _id(self):
        self.n += 1
        return f"{self.name}-{self.n:04d}"

    def _base(self, type_, x, y, w, h, stroke=INK, bg="transparent", fill="solid",
              sw=1, style="solid", rough=1, opacity=100, roundness=None):
        return {
            "id": self._id(), "type": type_,
            "x": float(x), "y": float(y), "width": float(w), "height": float(h),
            "angle": 0,
            "strokeColor": stroke, "backgroundColor": bg, "fillStyle": fill,
            "strokeWidth": sw, "strokeStyle": style, "roughness": rough,
            "opacity": opacity, "groupIds": [], "frameId": None,
            "roundness": roundness,
            "seed": rng.randint(1, 2**31 - 1), "version": 1,
            "versionNonce": rng.randint(1, 2**31 - 1), "isDeleted": False,
            "boundElements": [], "updated": STAMP, "link": None, "locked": False,
        }

    def add(self, e):
        self.els.append(e)
        return e

    # shapes -----------------------------------------------------------------
    def rect(self, x, y, w, h, stroke=INK, bg="transparent", fill="solid", sw=1,
             style="solid", rough=1, opacity=100, rounded=True, label=None,
             label_color=None, size=14, family=FONT_MAIN):
        e = self.add(self._base("rectangle", x, y, w, h, stroke, bg, fill, sw, style,
                                rough, opacity, {"type": 3} if rounded else None))
        if label is not None:
            self.bound_label(e, label, label_color or stroke, size, family)
        return e

    def ellipse(self, x, y, w, h, stroke=INK, bg="transparent", fill="solid", sw=1,
                style="solid", rough=1, opacity=100, label=None, label_color=None,
                size=12, family=FONT_MAIN):
        e = self.add(self._base("ellipse", x, y, w, h, stroke, bg, fill, sw, style,
                                rough, opacity, {"type": 2}))
        if label is not None:
            self.bound_label(e, label, label_color or stroke, size, family)
        return e

    def _text_el(self, x, y, s, size, color, align, family, container=None):
        lines = s.split("\n")
        w = max(len(l) for l in lines) * size * CHAR_W
        h = len(lines) * size * LINE_HEIGHT
        e = self._base("text", x, y, w, h, color, "transparent", "solid", 1, "solid", 1, 100, None)
        e.update({
            "text": s, "fontSize": size, "fontFamily": family, "textAlign": align,
            "verticalAlign": "middle" if container else "top",
            "containerId": container["id"] if container else None,
            "originalText": s, "autoResize": True, "lineHeight": LINE_HEIGHT,
        })
        return e

    def text(self, x, y, s, size=14, color=INK, align="left", family=FONT_MAIN):
        """Free text. x is the left edge (align=left), the centre (center) or the right edge (right)."""
        e = self._text_el(x, y, s, size, color, align, family)
        if align == "center":
            e["x"] = x - e["width"] / 2
        elif align == "right":
            e["x"] = x - e["width"]
        return self.add(e)

    def bound_label(self, container, s, color, size, family=FONT_MAIN):
        e = self._text_el(0, 0, s, size, color, "center", family, container)
        e["x"] = container["x"] + (container["width"] - e["width"]) / 2
        e["y"] = container["y"] + (container["height"] - e["height"]) / 2
        container["boundElements"].append({"type": "text", "id": e["id"]})
        return self.add(e)

    def _linear(self, type_, pts, stroke, sw, style, rough, opacity, roundness,
                start=None, end=None):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0, y0 = pts[0]
        e = self._base(type_, x0, y0, max(xs) - min(xs), max(ys) - min(ys), stroke,
                       "transparent", "solid", sw, style, rough, opacity, roundness)
        e.update({
            "points": [[float(px - x0), float(py - y0)] for px, py in pts],
            "lastCommittedPoint": None, "startBinding": None, "endBinding": None,
            "startArrowhead": start, "endArrowhead": end,
        })
        return self.add(e)

    def line(self, pts, stroke=RULE, sw=2, style="solid", opacity=100, smooth=False):
        return self._linear("line", pts, stroke, sw, style, 0, opacity,
                            {"type": 2} if smooth else None)

    def arrow(self, pts, stroke=INK, sw=5, style="solid", opacity=100, start=None,
              end="arrow"):
        return self._linear("arrow", pts, stroke, sw, style, 0, opacity, {"type": 2},
                            start, end)

    # convenience --------------------------------------------------------------
    def phase_bar(self, x, y, w, h, color, label=None, size=12, opacity=100,
                  style="solid", bg=None, label_color=WHITE, fill="solid"):
        return self.rect(x, y, w, h, stroke=color, bg=bg or color, fill=fill, sw=1,
                         style=style, opacity=opacity, label=label,
                         label_color=label_color, size=size)

    def unit(self, tl, t, y, h=24, label=None, size=11, opacity=100, vote_label=None,
             agg_label=None):
        """One 4 s + 4 s unit starting at time t (seconds) on timeline tl."""
        self.phase_bar(tl.x(t) + 1, y, tl.w(VOTE) - 2, h, VOTE_C,
                       label=label if vote_label is None else vote_label,
                       size=size, opacity=opacity)
        self.phase_bar(tl.x(t + VOTE) + 1, y, tl.w(AGG) - 2, h, AGG_C, label=agg_label,
                       size=size, opacity=opacity)

    def dump(self):
        return {
            "type": "excalidraw", "version": 2,
            "source": "https://marketplace.visualstudio.com/items?itemName=pomdtr.excalidraw-editor",
            "elements": self.els,
            "appState": {"gridSize": 20, "gridStep": 5, "gridModeEnabled": False,
                         "viewBackgroundColor": WHITE},
            "files": {},
        }


class TL:
    """Seconds -> pixels."""
    def __init__(self, x0, pxs):
        self.x0, self.pxs = x0, pxs

    def x(self, t):
        return self.x0 + t * self.pxs

    def w(self, dt):
        return dt * self.pxs


def slot_grid(sc, tl, y0, y1, slots=SLOTS, guides=(4, 8), label_y=None, time_y=None,
              slot_names=True, guide_opacity=60):
    for s in range(slots + 1):
        sc.line([(tl.x(s * SLOT), y0), (tl.x(s * SLOT), y1)], RULE, 2)
        if time_y is not None:
            sc.text(tl.x(s * SLOT), time_y, f"{s * SLOT} s", 12, MUTED, "center")
    for s in range(slots):
        for g in guides:
            sc.line([(tl.x(s * SLOT + g), y0), (tl.x(s * SLOT + g), y1)], MUTED, 1,
                    "dashed", guide_opacity)
        if slot_names and label_y is not None:
            sc.text(tl.x(s * SLOT + SLOT / 2), label_y, f"slot {s}", 14, INK, "center")


def band(sc, x, y, w, h, label, label_color=MUTED, size=12):
    r = sc.rect(x, y, w, h, stroke=INK, bg=BAND, fill="solid", sw=1, rough=2, opacity=10)
    sc.text(x + 10, y + 6, label, size, label_color)
    return r


def note_box(sc, x, y, w, s, size=13, stroke=INK, color=INK, pad=10):
    lines = s.split("\n")
    h = len(lines) * size * LINE_HEIGHT + 2 * pad
    sc.rect(x, y, w, h, stroke=stroke, bg=WHITE, fill="solid", sw=1, rough=1)
    sc.text(x + pad, y + pad, s, size, color)
    return h


# =============================================================================
# Figures
# =============================================================================
def fig_unit_today():
    sc = Scene("unit-today")
    tl = TL(150, 80)
    sc.text(tl.x(0), 30, "Today's attestation pipeline: one 8-second unit per 12-second slot", 22)
    sc.text(tl.x(0), 62, "mainnet, 12 s slots · V/32 of the validators attest per slot · 64 subnets · 16 aggregators per committee", 13, MUTED)

    ax = 130
    sc.line([(tl.x(0), ax), (tl.x(12), ax)], RULE, 2)
    for t, lab, al, dx in [(0, "0 s", "left", 8), (4, "4 s", "center", 0), (8, "8 s", "center", 0), (12, "12 s", "right", -8)]:
        sc.line([(tl.x(t), ax - 6), (tl.x(t), ax + 6)], RULE, 2)
        sc.text(tl.x(t) + dx, ax + 10, lab, 13, INK, al)
    for t, lab, c in [(4, "attestation deadline", VOTE_C), (8, "aggregators publish", AGG_C),
                      (12, "next block proposed", BLOCK_C)]:
        sc.ellipse(tl.x(t) - 6, ax - 6, 12, 12, stroke=NOTE, bg=c)
        sc.text(tl.x(t), ax - 34, lab, 12, INK, "center")
    sc.line([(tl.x(0), ax), (tl.x(0), 400)], RULE, 2)
    sc.line([(tl.x(12), ax), (tl.x(12), 400)], RULE, 2)
    for g in (4, 8):
        sc.line([(tl.x(g), ax + 30), (tl.x(g), 400)], MUTED, 1, "dashed", 70)

    band(sc, tl.x(0) - 20, 165, tl.w(12) + 40, 235, "network")

    y = 205
    sc.arrow([(tl.x(0), y), (tl.x(4), y)], BLOCK_C, 5)
    sc.text(tl.x(0.15), y + 10, "beacon block propagates", 13)

    y = 265
    sc.arrow([(tl.x(4), y), (tl.x(8), y)], VOTE_C, 5)
    sc.ellipse(tl.x(5.05), y - 44, 150, 30, stroke=VOTE_C, bg=VOTE_BG, label="V/32 voters", size=12)
    sc.text(tl.x(4.15), y + 10, "attestations: voter → subnet → aggregators", 13)

    y = 330
    sc.arrow([(tl.x(8), y), (tl.x(12), y)], AGG_C, 5)
    sc.ellipse(tl.x(9.05), y - 44, 150, 30, stroke=AGG_C, bg=AGG_BG, label="16-to-all per committee", size=12)
    sc.text(tl.x(8.15), y + 10, "aggregates: aggregator → global topic → everyone", 13)

    y = 430
    sc.arrow([(tl.x(4), y), (tl.x(12), y)], INK, 2, start="arrow", end="arrow")
    sc.text(tl.x(8), y + 10, "the unit: 4 s vote + 4 s aggregation = 8 s, ending at the next block proposal", 14, INK, "center")
    return sc


def fig_unit_anatomy():
    sc = Scene("unit-anatomy")
    tl = TL(120, 100)
    sc.text(tl.x(0), 30, "The unit, and the three principles it is built under", 22)

    y, h = 90, 56
    sc.phase_bar(tl.x(0), y, tl.w(4) - 2, h, VOTE_C, "VOTE · 4 s", size=18)
    sc.phase_bar(tl.x(4) + 2, y, tl.w(4) - 2, h, AGG_C, "AGGREGATE · 4 s", size=18)
    for t in (0, 4, 8):
        sc.line([(tl.x(t), y + h + 4), (tl.x(t), y + h + 14)], RULE, 2)
        sc.text(tl.x(t), y + h + 18, f"{t} s", 13, INK, "center")

    sc.text(tl.x(0), y + h + 46, "voters sign the FG vote and gossip it on their subnet;\naggregators collect for a full 4 s — as today", 13)
    sc.text(tl.x(4) + 6, y + h + 46, "aggregators publish on the global topic;\nevery node — incl. the next proposer — receives them", 13)

    y2 = 250
    w = 262
    boxes = [
        ("P1 · at least 4 s before aggregation",
         "every voter, wherever it sits on the globe,\nkeeps the propagation budget it has today\n(geo-fairness); no phase is shortened", VOTE_C),
        ("P2 · GossipSub, as today",
         "subnets feeding aggregators, aggregates on\na global topic; no new transport in the\ncritical path", OK_C),
        ("P3 · only the round schedule changes",
         "no further optimisation yet — bundling, PoV,\npoint-to-point-to-aggregators etc. layer on later\nwithout touching the unit", AGG_C),
    ]
    for i, (title, body, c) in enumerate(boxes):
        x = tl.x(0) + i * (w + 12)
        sc.rect(x, y2, w, 118, stroke=c, bg=WHITE, fill="solid", sw=2)
        sc.text(x + 12, y2 + 10, title, 14, c)
        sc.text(x + 12, y2 + 36, body, 12, INK)
    return sc


def fig_round():
    sc = Scene("round-23-units")
    tl = TL(180, 12)
    sc.text(tl.x(0), 24, "One 8-slot round = 23 units: three start in every slot, two in the last", 22)
    sc.text(tl.x(0), 56, "each unit is 4 s vote (blue) + 4 s aggregation (orange); units start every 4 s; a unit must finish inside the round", 13, MUTED)

    top, bot = 96, 452
    slot_grid(sc, tl, top, bot, label_y=100, time_y=80)
    sc.line([(tl.x(0), top - 4), (tl.x(0), bot + 4)], INK, 3)
    sc.line([(tl.x(96), top - 4), (tl.x(96), bot + 4)], INK, 3)
    sc.text(tl.x(0) - 8, bot + 8, "round start", 12, INK, "right")
    sc.text(tl.x(96) + 8, bot + 8, "round end", 12, INK)

    # blocks row
    yb = 140
    sc.text(tl.x(0) - 12, yb - 8, "blocks", 12, MUTED, "right")
    for s in range(SLOTS):
        sc.arrow([(tl.x(s * SLOT), yb), (tl.x(s * SLOT + 4), yb)], BLOCK_C, 4)

    # unit lanes by start offset within the slot
    lane_y = {0: 178, 4: 232, 8: 286}
    for off, y in lane_y.items():
        sc.text(tl.x(0) - 12, y + 4, f"units starting at +{off} s", 12, INK, "right")
    for i, st, ve, ae in UNITS:
        sc.unit(tl, st, lane_y[st % SLOT], h=26, label=f"u{i}", size=11)
    # the dropped 24th unit
    yg = lane_y[8]
    sc.rect(tl.x(92) + 1, yg, tl.w(8) - 2, 26, stroke=DROP_C, bg="transparent", sw=2,
            style="dashed", label="u23 — dropped", label_color=DROP_C, size=11)
    sc.text(tl.x(100) + 8, yg + 5, "would end 4 s into the next round", 12, DROP_C)

    # landings
    yl = 350
    sc.text(tl.x(0) - 12, yl - 6, "aggregates land", 12, MUTED, "right")
    sc.line([(tl.x(0), yl), (tl.x(96), yl)], MUTED, 1)
    for i, st, ve, ae in UNITS:
        sc.ellipse(tl.x(ae) - 5, yl - 5, 10, 10, stroke=AGG_C, bg=AGG_C)

    yc1, yc2 = 385, 418
    sc.text(tl.x(0) - 12, yc1 - 2, "landings per slot", 12, MUTED, "right")
    sc.text(tl.x(0) - 12, yc2 - 2, "units starting per slot", 12, MUTED, "right")
    for s in range(SLOTS):
        land = sum(1 for _, _, _, ae in UNITS if (ae - 1) // SLOT == s)
        start = sum(1 for _, st, _, _ in UNITS if st // SLOT == s)
        sc.text(tl.x(s * SLOT + 6), yc1 - 8, str(land), 18, AGG_C if land == 2 else INK, "center")
        sc.text(tl.x(s * SLOT + 6), yc2 - 8, str(start), 18, VOTE_C if start == 2 else INK, "center")

    sc.text(tl.x(48), bot + 40,
            f"Σ = 8 × 3 − 1 = {len(UNITS)} units per round (one full validator pass)  ·  today: {TODAY_UNITS} attestation slots per pass  ·  −{100 * (1 - len(UNITS) / TODAY_UNITS):.1f} %",
            15, INK, "center")
    return sc


def fig_slot_zoom():
    sc = Scene("slot-zoom")
    tl = TL(230, 78)
    sc.text(tl.x(0), 24, "Inside a slot: today one phase at a time, pipelined units two phases at a time", 22)

    def axis(y):
        sc.line([(tl.x(0), y), (tl.x(12), y)], RULE, 2)
        for t in (0, 4, 8, 12):
            sc.line([(tl.x(t), y - 5), (tl.x(t), y + 5)], RULE, 2)
            sc.text(tl.x(t), y + 8, f"{t} s", 12, INK, "center")

    # panel A: today
    yA = 80
    sc.text(tl.x(0), yA, "today's slot (mainnet)", 15, INK)
    axis(yA + 30)
    y = yA + 62
    sc.phase_bar(tl.x(0) + 1, y, tl.w(4) - 2, 30, BLOCK_C, "block", size=13, label_color=INK)
    sc.phase_bar(tl.x(4) + 1, y, tl.w(4) - 2, 30, VOTE_C, "attest (V/32)", size=13)
    sc.phase_bar(tl.x(8) + 1, y, tl.w(4) - 2, 30, AGG_C, "aggregate", size=13)
    sc.text(tl.x(12) + 14, y + 7, "one phase in flight at a time", 13, MUTED)

    # panel B: pipelined units, interior slot s
    yB = 235
    sc.text(tl.x(0), yB, "pipelined units — an interior slot s of the round (units u(3s−1) … u(3s+2) touch it)", 15, INK)
    axis(yB + 30)
    rows = [("block", yB + 62), ("vote phases", yB + 112), ("aggregation phases", yB + 162)]
    for name, y in rows:
        sc.text(tl.x(0) - 14, y + 7, name, 13, INK, "right")
    yblk, yv, ya = rows[0][1], rows[1][1], rows[2][1]
    sc.phase_bar(tl.x(0) + 1, yblk, tl.w(4) - 2, 30, BLOCK_C, "block", size=13, label_color=INK)
    for k, (lab) in enumerate(["u(3s)", "u(3s+1)", "u(3s+2)"]):
        sc.phase_bar(tl.x(4 * k) + 1, yv, tl.w(4) - 2, 30, VOTE_C, f"{lab} vote", size=13)
    for k, (lab) in enumerate(["u(3s−1)", "u(3s)", "u(3s+1)"]):
        sc.phase_bar(tl.x(4 * k) + 1, ya, tl.w(4) - 2, 30, AGG_C, f"{lab} aggregate", size=13)
    for t in (4, 8, 12):
        sc.line([(tl.x(t), ya + 30), (tl.x(t), ya + 58)], AGG_C, 2, "dashed")
    sc.ellipse(tl.x(4) - 6, ya + 56, 12, 12, stroke=AGG_C, bg=AGG_C)
    sc.ellipse(tl.x(8) - 6, ya + 56, 12, 12, stroke=AGG_C, bg=AGG_C)
    sc.ellipse(tl.x(12) - 6, ya + 56, 12, 12, stroke=AGG_C, bg=AGG_C)
    sc.text(tl.x(4), ya + 74, "u(3s−1) lands", 12, INK, "center")
    sc.text(tl.x(8), ya + 74, "u(3s) lands", 12, INK, "center")
    sc.text(tl.x(12), ya + 74, "u(3s+1) lands = next block", 12, INK, "center")

    x = tl.x(12) + 20
    note_box(sc, x, yv - 8, 330,
             "at any instant one vote phase and one\naggregation phase are in flight — plus the\nblock in the first third of the slot\n\nslot 0 of a round has no u(−1): its\naggregation row starts empty → only\n2 landings instead of 3", 12)
    return sc


def fig_load_parity():
    sc = Scene("load-parity")
    x0 = 60
    sc.text(x0, 24, "Unit-size parity: 23 units per validator pass instead of 32", 22)

    # cell rows
    cw, gap = 30, 3
    y1, y2 = 90, 150
    sc.text(x0, y1 - 24, f"today — one pass of the validator set takes 32 slots → 32 units of V/32 each", 13, INK)
    for i in range(TODAY_UNITS):
        sc.rect(x0 + i * (cw + gap), y1, cw, 26, stroke=VOTE_C, bg=VOTE_BG, fill="solid")
    sc.text(x0, y2 - 24, f"pipelined — one pass = one 8-slot round → 23 units of V′/23 each", 13, INK)
    for i in range(len(UNITS)):
        sc.rect(x0 + i * (cw + gap), y2, cw, 26, stroke=VOTE_C, bg=VOTE_C, fill="solid")
    xa = x0 + len(UNITS) * (cw + gap)
    xb = x0 + TODAY_UNITS * (cw + gap) - gap
    sc.arrow([(xa, y2 + 13), (xb, y2 + 13)], INK, 2, start="arrow", end="arrow")
    sc.text((xa + xb) / 2, y2 + 24, f"9 fewer units = −{100 * (1 - len(UNITS) / TODAY_UNITS):.1f} %", 13, INK, "center")

    # chart: per-unit size relative to today vs validator-set reduction
    cx0, cy0, cw_, ch = x0 + 70, 480, 560, 240   # origin bottom-left
    def X(r):   # r in [0, 0.5]
        return cx0 + r / 0.5 * cw_
    def Y(v):   # v in [0.6, 1.5]
        return cy0 - (v - 0.6) / 0.9 * ch
    sc.text(x0, 205, "per-unit size relative to today's unit — (V′/23) / (V/32) — as the validator set shrinks", 15, INK)
    sc.line([(cx0, cy0), (cx0 + cw_, cy0)], MUTED, 1)
    sc.line([(cx0, cy0), (cx0, cy0 - ch)], MUTED, 1)
    for r in (0, 0.1, 0.2, 0.3, 0.4, 0.5):
        sc.line([(X(r), cy0), (X(r), cy0 + 5)], MUTED, 1)
        sc.text(X(r), cy0 + 9, f"{int(r * 100)} %", 12, INK, "center")
    for v in (0.6, 0.8, 1.0, 1.2, 1.4):
        sc.line([(cx0 - 5, Y(v)), (cx0, Y(v))], MUTED, 1)
        sc.text(cx0 - 10, Y(v) - 8, f"{v:.1f}×", 12, INK, "right")
    sc.text(X(0.25), cy0 + 30, "validators removed by consolidation (1 − V′/V)", 13, INK, "center")
    # reference line at 1.0
    sc.line([(cx0, Y(1.0)), (cx0 + cw_, Y(1.0))], INK, 1, "dashed")
    sc.text(cx0 + cw_ + 8, Y(1.0) - 8, "today's unit (V/32)", 12, INK)
    # the line
    f = lambda r: (TODAY_UNITS / len(UNITS)) * (1 - r)
    pts = [(X(r / 100), Y(f(r / 100))) for r in range(0, 51, 5)]
    sc.line(pts, VOTE_C, 3)
    r_star = 1 - len(UNITS) / TODAY_UNITS
    sc.line([(X(r_star), cy0), (X(r_star), Y(1.0))], AGG_C, 2, "dashed")
    sc.ellipse(X(r_star) - 6, Y(1.0) - 6, 12, 12, stroke=AGG_C, bg=WHITE, sw=2)
    sc.text(X(r_star) + 12, Y(1.0) - 46, f"parity at {100 * r_star:.1f} % fewer validators\n(V′ = 23/32 · V = {len(UNITS) / TODAY_UNITS:.4f} V)", 13, AGG_C)
    sc.text(X(0.03), Y(f(0)) - 30, f"no consolidation: each unit is {TODAY_UNITS / len(UNITS):.2f}× today's", 12, INK)
    sc.text(x0, cy0 + 56, "the same threshold applies to any per-vote wire reduction, e.g. bundled propagation (EIP-8334) — what matters is messages per unit, not validators per unit", 12, MUTED)
    return sc


def fig_late_aggregates():
    sc = Scene("late-aggregates")
    tl = TL(230, 78)
    sc.text(tl.x(0), 24, "Open problem 2: votes that miss their unit's cut, and the end-of-slot catch-all question", 22)

    ax = 90
    sc.line([(tl.x(0), ax), (tl.x(12), ax)], RULE, 2)
    for t in (0, 4, 8, 12):
        sc.line([(tl.x(t), ax - 5), (tl.x(t), ax + 5)], RULE, 2)
        sc.text(tl.x(t), ax + 8, f"{t} s", 12, INK, "center")
    sc.text(tl.x(12) + 14, ax - 8, "interior slot s", 13, MUTED)

    yv, ya = 140, 205
    sc.text(tl.x(0) - 14, yv + 7, "vote phases", 13, INK, "right")
    sc.text(tl.x(0) - 14, ya + 7, "aggregates published", 13, INK, "right")
    for k, lab in enumerate(["u(3s)", "u(3s+1)", "u(3s+2)"]):
        sc.phase_bar(tl.x(4 * k) + 1, yv, tl.w(4) - 2, 30, VOTE_C, f"{lab} vote", size=13)
    for k, lab in enumerate(["u(3s−1)", "u(3s)", "u(3s+1)"]):
        sc.line([(tl.x(4 * k), yv - 10), (tl.x(4 * k), ya + 40)], AGG_C, 2, "dashed")
        sc.ellipse(tl.x(4 * k) - 9, ya + 6, 18, 18, stroke=AGG_C, bg=AGG_C)
        sc.text(tl.x(4 * k) + 14, ya + 6, f"{lab} — scheduled", 12, INK)
    # late votes: dots after each cut
    for k in range(3):
        for j in range(3):
            sc.ellipse(tl.x(4 * k) + 10 + j * 14, yv - 12, 9, 9, stroke=VOTE_C, bg=WHITE, sw=2)
    sc.text(tl.x(0) + 62, yv - 28, "late votes (stragglers) arrive after their unit's aggregators have published", 12, VOTE_C)

    # the catch-all question
    sc.rect(tl.x(11.2), ya, tl.w(0.8), 30, stroke=AGG_C, bg=AGG_BG, fill="hachure", sw=2,
            style="dashed", label="?", label_color=AGG_C, size=18)
    sc.text(tl.x(12) + 14, ya + 6, "a catch-all aggregate at the end of the slot?", 13, AGG_C)

    y = 290
    note_box(sc, tl.x(0), y, 430,
             "who would produce it?\n· the proposer / builder, from the late votes it saw\n· every node, by local reconstruction of what it saw\n· nobody — honest nodes reject late aggregates,\n  stragglers' votes are simply lost for this round", 13)
    note_box(sc, tl.x(0) + 450, y, 476,
             "risk: a build-up of aggregates toward the slot end\nscheduled 3 per slot + catch-alls + duplicates → the\nverification and forwarding load piles up exactly where\nthe next block is being built and propagated\n(today's devnet already shows late votes, not late aggregates)", 13,
             stroke=DROP_C)
    return sc


def fig_committee_size():
    sc = Scene("committee-size")
    ox, oy, W, H = 200, 420, 620, 280   # origin bottom-left of plot
    sc.text(60, 24, "Central open question: how large should a unit's committees (subnets) be under bundled GossipSub propagation?", 20)
    sc.text(60, 54, "schematic — no measured curve yet; the whole point is to benchmark this", 13, MUTED)

    sc.line([(ox, oy), (ox + W, oy)], MUTED, 1)
    sc.line([(ox, oy), (ox, oy - H)], MUTED, 1)
    sc.text(ox + W / 2, oy + 12, "validators per committee (subnet) of a unit  →", 13, INK, "center")
    sc.text(ox - 12, oy - H - 30, "vote → published-aggregate latency, tail (schematic)", 12, MUTED, "right")

    def P(u, v):  # u,v in [0,1]
        return (ox + u * W, oy - v * H)

    bund = [(u, 0.62 * math.exp(-u * 4.5) + 0.06) for u in [i / 20 for i in range(21)]]
    queue = [(u, 0.05 + 0.75 * u ** 2.2) for u in [i / 20 for i in range(21)]]
    total = [(u, b + q) for (u, b), (_, q) in zip(bund, queue)]
    sc.line([P(u, v) for u, v in bund], VOTE_C, 2, smooth=True)
    sc.line([P(u, v) for u, v in queue], AGG_C, 2, smooth=True)
    sc.line([P(u, v) for u, v in total], INK, 3, smooth=True)
    umin = min(total, key=lambda p: p[1])
    px, py = P(*umin)
    sc.ellipse(px - 8, py - 8, 16, 16, stroke=INK, bg=WHITE, sw=2)
    sc.text(px, py - 34, "sweet spot? unknown", 13, INK, "center")

    # direct labels at curve ends
    sc.text(P(1, bund[-1][1])[0] + 8, P(1, bund[-1][1])[1] - 8, "bundling gain forgone", 12, VOTE_C)
    sc.text(P(1, queue[-1][1])[0] + 8, P(1, queue[-1][1])[1] - 8, "queueing + control traffic", 12, AGG_C)
    sc.text(P(1, total[-1][1])[0] + 8, P(1, total[-1][1])[1] - 8, "combined latency", 12, INK)

    note_box(sc, 60, oy + 50, 420,
             "too small\n· fewer votes per bundle → little gain from\n  bundled propagation (EIP-8334)\n· more subnets and aggregators to run per unit", 12, stroke=VOTE_C)
    note_box(sc, 500, oy + 50, 480,
             "too large\n· per-subnet message rate → queueing delays\n· more IHAVE / IWANT control messages per node\n· validation backlog behind the previous unit's\n  aggregates and the block — GossipSub has no\n  message prioritisation", 12, stroke=AGG_C)
    return sc


def fig_schedule_comparison():
    sc = Scene("schedule-comparison")
    tl = TL(300, 12)
    sc.text(tl.x(0), 24, "Three schedules over one 8-slot round: mainnet today, the current DC proposal, pipelined units", 22)
    top, bot = 84, 470
    slot_grid(sc, tl, top, bot, label_y=88, time_y=68, guides=(4, 8), guide_opacity=35)
    sc.text(tl.x(96) + 8, 88, "next round →", 12, MUTED)

    # Row A: mainnet today
    yA = 130
    sc.text(tl.x(0) - 14, yA - 4, "mainnet today", 15, INK, "right")
    sc.text(tl.x(0) - 14, yA + 18, "1 unit / slot · V/32 per unit\n4 s vote · 4 s aggregation\nfull pass = 32 slots (one epoch)", 11, MUTED, "right")
    for s in range(SLOTS):
        sc.unit(tl, s * SLOT + 4, yA, h=22)

    # Row B: current DC proposal (explainer Option 5, X = 0)
    yB = 215
    sc.text(tl.x(0) - 14, yB - 4, "current DC proposal", 15, INK, "right")
    sc.text(tl.x(0) - 14, yB + 18, "explainer Option 5, X = 0\n1 cohort / slot · V/8 per cohort\n16 s vote · 4 s aggregation\ninclude at slot i+2", 11, MUTED, "right")
    for k in range(SLOTS):
        y = yB + (k % 2) * 28
        v0, v1 = k * SLOT + 4, (k + 1) * SLOT + 8
        a1 = v1 + 4
        op = 100 if a1 <= ROUND else 45
        sc.phase_bar(tl.x(v0) + 1, y, tl.w(v1 - v0) - 2, 22, VOTE_C, f"cohort {k} vote", size=11, opacity=op)
        sc.phase_bar(tl.x(v1) + 1, y, tl.w(4) - 2, 22, AGG_C, opacity=op)
    sc.text(tl.x(96) + 8, yB + 62, "cohort 7 aggregates in the next\nround; cohorts 6–7 are included there", 11, MUTED)

    # Row C: pipelined units
    yC = 330
    sc.text(tl.x(0) - 14, yC - 4, "pipelined units", 15, INK, "right")
    sc.text(tl.x(0) - 14, yC + 18, "3 units / slot (2 in the last) · V′/23 per unit\n4 s vote · 4 s aggregation\nall 23 units finish inside the round", 11, MUTED, "right")
    for i, st, ve, ae in UNITS:
        sc.unit(tl, st, yC + ((st % SLOT) // 4) * 24, h=20)

    sc.text(tl.x(48), bot + 16,
            "same 4 s vote and 4 s aggregation budgets as today in the pipelined row; the current proposal buys a 16 s vote window at the price of V/8 cohorts and a tally that completes one to two slots into the next round",
            12, MUTED, "center")
    return sc


def fig_repurposed():
    """Take the explainer figure and swap its FG network band for pipelined units."""
    with open(SOURCE_FIG) as f:
        src = json.load(f)
    keep = [e for e in src["elements"] if not e.get("isDeleted") and e["y"] < 640]
    for e in keep:  # fix the source's "hearbeat" typo in this copy only
        if e["type"] == "text" and "hearbeat" in e["text"]:
            e["text"] = e["text"].replace("hearbeat", "heartbeat")
            e["originalText"] = e["text"]
    sc = Scene("pipelined-units")
    sc.els = keep
    # geometry of the source drawing: two slots of 593.5 px starting at x = 55.087
    X0, SW = 55.08705814667745, 593.4560975609756
    pxs = SW / SLOT
    tl = TL(X0, pxs)
    y0, hgt = 659.8, 182.3
    band_x, band_w = -51.5, 1393.7
    sc.rect(band_x, y0, band_w, hgt, stroke=INK, bg=BAND, fill="solid", sw=1, rough=2, opacity=10)
    sc.text(band_x + 23.4, y0 + 12, "network", 9.5, MUTED)

    lanes = {0: y0 + 42, 4: y0 + 80, 8: y0 + 118}
    right_edge = band_x + band_w - 8
    # units touching the two shown slots (slot i = [0,12), slot i+1 = [12,24))
    for st in range(-4, 24, 4):
        y = lanes[st % SLOT]
        for (t0, t1, col) in [(st, st + VOTE, VOTE_C), (st + VOTE, st + UNIT, AGG_C)]:
            xa, xb = tl.x(t0), tl.x(t1)
            fade = xa < X0 or xb > X0 + 2 * SW
            xa_c, xb_c = max(xa, X0 - 30), min(xb, right_edge)
            if xb_c - xa_c < 20:
                continue
            sc.arrow([(xa_c, y), (xb_c, y)], col, 5, opacity=50 if fade else 100,
                     end="arrow" if xb <= right_edge else None)
    for k, st in enumerate((0, 4, 8)):
        sc.text(tl.x(st) + 4, lanes[st] + 8, f"u(3i+{k})" if k else "u(3i)", 9.5, INK)
    sc.text(tl.x(SLOT) + 4, lanes[0] + 8, "u(3i+3)", 9.5, INK)
    sc.ellipse(tl.x(1.0), lanes[0] - 34, 120, 30, stroke=VOTE_C, bg=VOTE_BG, fill="hachure",
               opacity=80, label="V′/23 → aggregators", size=9.5)
    sc.ellipse(tl.x(5.0), lanes[0] - 34, 80, 30, stroke=AGG_C, bg=AGG_BG, fill="hachure",
               opacity=80, label="16-to-all", size=9.5)
    sc.text(1379.2, y0 + 0.5,
            "units of 4 s vote\n+ 4 s aggregation,\n3 per slot\n= today's unit size\n(after consolidation)\n− uneven rewards", 16, NOTE, family=FONT_HAND)
    return sc


# =============================================================================
# Excalidraw -> SVG renderer (rectangle / ellipse / line / arrow / text)
# =============================================================================
FONT_STACK = {
    1: '"Virgil", "Segoe Print", "Bradley Hand", cursive',
    2: 'Helvetica, Arial, sans-serif',
    3: '"Cascadia", "SF Mono", Menlo, monospace',
    5: '"Excalifont", "Segoe Print", "Bradley Hand", "Comic Sans MS", cursive',
    6: 'Nunito, "Avenir Next", "Segoe UI", Helvetica, Arial, sans-serif',
}


def _esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _fmt(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _corner_radius(e):
    r = e.get("roundness")
    if not r:
        return 0
    m = min(e["width"], e["height"])
    if r.get("type") == 3:
        return m * 0.25 if m <= 128 else 32
    return m * 0.25 if m <= 128 else 32


def _dash(e):
    sw = e.get("strokeWidth", 1)
    st = e.get("strokeStyle", "solid")
    if st == "dashed":
        return f' stroke-dasharray="{8} {8 + sw}"'
    if st == "dotted":
        return f' stroke-dasharray="{1.5} {6 + sw}"'
    return ""


def _fill_attr(e, patterns):
    bg = e.get("backgroundColor", "transparent")
    if bg in ("transparent", None, ""):
        return 'fill="none"'
    fs = e.get("fillStyle", "solid")
    if fs in ("hachure", "cross-hatch", "zigzag"):
        key = (fs, bg)
        pid = patterns.setdefault(key, f"p{len(patterns)}")
        return f'fill="url(#{pid})"'
    return f'fill="{bg}"'


def _text_lines(e):
    return e["text"].split("\n")


def _catmull_rom_path(pts):
    if len(pts) < 3:
        return "M " + " L ".join(f"{_fmt(x)} {_fmt(y)}" for x, y in pts)
    d = [f"M {_fmt(pts[0][0])} {_fmt(pts[0][1])}"]
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i > 0 else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(f"C {_fmt(c1[0])} {_fmt(c1[1])} {_fmt(c2[0])} {_fmt(c2[1])} {_fmt(p2[0])} {_fmt(p2[1])}")
    return " ".join(d)


def _arrowhead(tip, prev, kind, sw, color):
    if not kind:
        return ""
    dx, dy = tip[0] - prev[0], tip[1] - prev[1]
    L = math.hypot(dx, dy) or 1
    ux, uy = dx / L, dy / L
    size = min(30, L / 2) if sw >= 4 else min(20 + 2 * sw, L / 2)
    ang = math.radians(22 if kind == "arrow" else 27)
    out = []
    for s in (1, -1):
        px = tip[0] - size * (ux * math.cos(ang) - s * uy * math.sin(ang))
        py = tip[1] - size * (uy * math.cos(ang) + s * ux * math.sin(ang))
        out.append((px, py))
    if kind == "triangle":
        return (f'<polygon points="{_fmt(tip[0])},{_fmt(tip[1])} {_fmt(out[0][0])},{_fmt(out[0][1])} '
                f'{_fmt(out[1][0])},{_fmt(out[1][1])}" fill="{color}" stroke="{color}" stroke-width="{sw}" stroke-linejoin="round"/>')
    return (f'<polyline points="{_fmt(out[0][0])},{_fmt(out[0][1])} {_fmt(tip[0])},{_fmt(tip[1])} '
            f'{_fmt(out[1][0])},{_fmt(out[1][1])}" fill="none" stroke="{color}" stroke-width="{sw}" '
            f'stroke-linecap="round" stroke-linejoin="round"/>')


def render_svg(doc, pad=28):
    els = [e for e in doc["elements"] if not e.get("isDeleted")]
    by_id = {e["id"]: e for e in els}
    xs, ys = [], []
    for e in els:
        if e["type"] in ("line", "arrow"):
            for px, py in e["points"]:
                xs.append(e["x"] + px)
                ys.append(e["y"] + py)
        else:
            xs += [e["x"], e["x"] + e["width"]]
            ys += [e["y"], e["y"] + e["height"]]
    minx, maxx, miny, maxy = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
    W, H = maxx - minx, maxy - miny
    bgc = doc.get("appState", {}).get("viewBackgroundColor", WHITE)
    patterns = {}
    body = []
    for e in els:
        op = e.get("opacity", 100) / 100
        g_open = f'<g opacity="{_fmt(op)}">' if op < 1 else "<g>"
        t = e["type"]
        sc_ = e.get("strokeColor", INK)
        sw = e.get("strokeWidth", 1)
        if t == "rectangle":
            r = _corner_radius(e)
            body.append(f'{g_open}<rect x="{_fmt(e["x"])}" y="{_fmt(e["y"])}" width="{_fmt(e["width"])}" '
                        f'height="{_fmt(e["height"])}" rx="{_fmt(r)}" {_fill_attr(e, patterns)} stroke="{sc_}" '
                        f'stroke-width="{sw}"{_dash(e)}/></g>')
        elif t == "ellipse":
            body.append(f'{g_open}<ellipse cx="{_fmt(e["x"] + e["width"] / 2)}" cy="{_fmt(e["y"] + e["height"] / 2)}" '
                        f'rx="{_fmt(e["width"] / 2)}" ry="{_fmt(e["height"] / 2)}" {_fill_attr(e, patterns)} '
                        f'stroke="{sc_}" stroke-width="{sw}"{_dash(e)}/></g>')
        elif t in ("line", "arrow"):
            pts = [(e["x"] + px, e["y"] + py) for px, py in e["points"]]
            smooth = bool(e.get("roundness")) and len(pts) > 2
            if smooth:
                path = f'<path d="{_catmull_rom_path(pts)}" fill="none" stroke="{sc_}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"{_dash(e)}/>'
            else:
                path = (f'<polyline points="{" ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in pts)}" fill="none" '
                        f'stroke="{sc_}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"{_dash(e)}/>')
            heads = ""
            if t == "arrow" and len(pts) >= 2:
                heads += _arrowhead(pts[-1], pts[-2], e.get("endArrowhead"), sw, sc_)
                heads += _arrowhead(pts[0], pts[1], e.get("startArrowhead"), sw, sc_)
            body.append(f"{g_open}{path}{heads}</g>")
        elif t == "text":
            lines = _text_lines(e)
            fs = e.get("fontSize", 16)
            lh = fs * e.get("lineHeight", LINE_HEIGHT)
            fam = FONT_STACK.get(e.get("fontFamily", 6), FONT_STACK[6])
            align = e.get("textAlign", "left")
            cont = by_id.get(e.get("containerId")) if e.get("containerId") else None
            if cont:
                cx = cont["x"] + cont["width"] / 2
                top = cont["y"] + (cont["height"] - len(lines) * lh) / 2
                anchor = "middle"
            else:
                top = e["y"]
                if align == "center":
                    cx, anchor = e["x"] + e["width"] / 2, "middle"
                elif align == "right":
                    cx, anchor = e["x"] + e["width"], "end"
                else:
                    cx, anchor = e["x"], "start"
            spans = "".join(
                f'<text x="{_fmt(cx)}" y="{_fmt(top + lh * (i + 0.5))}" text-anchor="{anchor}" '
                f'dominant-baseline="central" font-family=\'{fam}\' font-size="{_fmt(fs)}" fill="{sc_}">{_esc(l)}</text>'
                for i, l in enumerate(lines))
            body.append(f"{g_open}{spans}</g>")
    defs = []
    for (fs, color), pid in patterns.items():
        lines = '<path d="M-2,2 l4,-4 M0,8 l8,-8 M6,10 l4,-4"'
        cross = ' M-2,6 l4,4 M0,0 l8,8 M6,-2 l4,4' if fs == "cross-hatch" else ""
        defs.append(f'<pattern id="{pid}" patternUnits="userSpaceOnUse" width="8" height="8">'
                    f'<path d="M-2,2 l4,-4 M0,8 l8,-8 M6,10 l4,-4{cross}" stroke="{color}" stroke-width="1.2" fill="none"/></pattern>')
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{_fmt(minx)} {_fmt(miny)} {_fmt(W)} {_fmt(H)}" '
           f'width="{_fmt(W)}" height="{_fmt(H)}" font-family=\'{FONT_STACK[6]}\'>']
    if defs:
        svg.append("<defs>" + "".join(defs) + "</defs>")
    svg.append(f'<rect x="{_fmt(minx)}" y="{_fmt(miny)}" width="{_fmt(W)}" height="{_fmt(H)}" fill="{bgc}"/>')
    svg += body
    svg.append("</svg>")
    return "\n".join(svg)


# =============================================================================
def main(argv):
    os.makedirs(EXC_DIR, exist_ok=True)
    os.makedirs(FIG_DIR, exist_ok=True)
    figures = [
        ("01-unit-today", fig_unit_today),
        ("02-unit-anatomy", fig_unit_anatomy),
        ("03-round-23-units", fig_round),
        ("04-slot-zoom", fig_slot_zoom),
        ("05-load-parity", fig_load_parity),
        ("06-late-aggregates", fig_late_aggregates),
        ("07-committee-size", fig_committee_size),
        ("08-schedule-comparison", fig_schedule_comparison),
        ("09-fg-slot-structure-pipelined-units", fig_repurposed),
    ]
    written = []
    for name, fn in figures:
        doc = fn().dump()
        exc_path = os.path.join(EXC_DIR, f"{name}.excalidraw")
        with open(exc_path, "w") as f:
            json.dump(doc, f, indent=1, ensure_ascii=False)
            f.write("\n")
        svg_path = os.path.join(FIG_DIR, f"{name}.svg")
        with open(svg_path, "w") as f:
            f.write(render_svg(doc))
        written.append(svg_path)
        print(f"wrote {os.path.relpath(exc_path, HERE)}  ({len(doc['elements'])} elements) -> {os.path.relpath(svg_path, HERE)}")
    # also render the untouched source figure, for side-by-side reading
    with open(SOURCE_FIG) as f:
        src = json.load(f)
    src["elements"] = [e for e in src["elements"] if not (e["type"] == "arrow" and e["x"] > 1560)]
    p = os.path.join(FIG_DIR, "00-fg-slot-structure-current.svg")
    with open(p, "w") as f:
        f.write(render_svg(src))
    written.append(p)
    print(f"wrote {os.path.relpath(p, HERE)} (render of ../ac/fg_slot_structure_current.excalidraw)")

    if "--png" in argv:
        ink = "/Applications/Inkscape.app/Contents/MacOS/inkscape"
        if not os.path.exists(ink):
            print("inkscape not found; skipping PNG export")
            return
        os.makedirs(PNG_DIR, exist_ok=True)
        for svg_path in written:
            png_path = os.path.join(PNG_DIR, os.path.basename(svg_path)[:-4] + ".png")
            subprocess.run([ink, "--export-type=png", f"--export-filename={png_path}",
                            "--export-width=1600", svg_path],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            print(f"wrote {os.path.relpath(png_path, HERE)}")


if __name__ == "__main__":
    main(sys.argv[1:])
