#!/usr/bin/env python3
"""Generate the README animation for dc-networking (light + dark SVG).

One loop = one 8-slot finality-gadget round in decoupled consensus:
  - each slot, a new block joins the available chain (pulse at the head);
  - a small sampled committee (flashing dots) confirms the head — the block
    gains a "confirmed" losange (AC head vote); committees are small
    (512-ish) next to cohorts (tens of thousands), so 4 dots vs 12-dot
    cohorts;
  - one of 8 validator cohorts lights up and casts its finality vote on the
    round's fixed target: block 3, the highest confirmed block when the
    round began (beam);
  - nothing is justified mid-round: once all 8 cohorts have voted, the
    target and its prefix (blocks 1-3) are justified together (dark fill +
    ring, cascading); the round's own blocks stay merely confirmed, and
    the round resets.

Pure CSS animations inside the SVG (opacity/transform only), so it plays
when embedded in a GitHub README via <img>; honors prefers-reduced-motion
(static frame = end of round). No JavaScript, no SMIL.

Regenerate:  python3 assets/generate_animation.py
"""

import os
import random

# ---- timing (seconds) -------------------------------------------------
P = 11.0            # loop period
SLOT = 1.2          # slot duration; 8 slots = 9.6 s, then finalize + hold
NS = 8              # slots per round = cohorts

# ---- geometry ----------------------------------------------------------
W, H = 460, 152
X0, PITCH, BLK = 10, 40, 14   # chain: first block x, pitch, block size
CHAIN_Y = 22                  # block rect top
CY = CHAIN_Y + BLK / 2        # chain centerline
TGT = 2                       # index of the round's target/checkpoint block
COLX = [34 + k * 56 for k in range(NS)]      # cohort cluster centers
ROWY = [68, 79, 90]                          # 3 rows x 4 cols per cohort
DOTR = 2.9

PALETTES = {
    "": dict(ink="#1A2C29", muted="#5C6F6A", accent="#1F6F63", hair="#D9E2DD"),
    "-dark": dict(ink="#E5ECE8", muted="#93A69E", accent="#A9CBB9", hair="#2B3833"),
}

def bx(i):        # block group x
    return X0 + i * PITCH

def bcx(i):       # block center x
    return bx(i) + BLK / 2

def pc(t):        # seconds -> percent of period
    return round(t / P * 100, 2)

# validator dots: cohort k -> 12 dots (4 cols x 3 rows). Cohorts are big;
# the per-slot sampled AC committee is small (4 dots from the whole field).
DOTS = [(k, COLX[k] + dx, y) for k in range(NS)
        for dx in (-13.5, -4.5, 4.5, 13.5) for y in ROWY]

# per-slot sampled committees (deterministic; seed = the dc ethresearch topic id)
rng = random.Random(24527)
COMMITTEES = [rng.sample(range(len(DOTS)), 4) for _ in range(NS)]


def keyframes_appear(name, t0, fade=0.3):
    a, b = pc(t0), pc(t0 + fade)
    return (f"@keyframes {name} {{ 0%, {a}% {{ opacity: 0 }} "
            f"{b}% {{ opacity: 1 }} 100% {{ opacity: 1 }} }}")


def keyframes_flash(name, t0, t1, peak=1.0, ramp=0.12):
    a, m, b = pc(t0), pc(t0 + ramp), pc(t1)
    return (f"@keyframes {name} {{ 0%, {a}% {{ opacity: 0 }} "
            f"{m}% {{ opacity: {peak} }} {b}%, 100% {{ opacity: 0 }} }}")


def keyframes_pulse(name, t0):
    a, m, b = pc(t0), pc(t0 + 0.05), pc(t0 + 0.62)
    return (f"@keyframes {name} {{ 0%, {a}% {{ opacity: 0; transform: scale(0.35) }} "
            f"{m}% {{ opacity: 0.75 }} "
            f"{b}%, 100% {{ opacity: 0; transform: scale(1.7) }} }}")


def keyframes_pop(name, t0, dur=0.35):
    a, b = pc(t0), pc(t0 + dur)
    return (f"@keyframes {name} {{ 0%, {a}% {{ opacity: 0; transform: scale(0); "
            f"animation-timing-function: cubic-bezier(0.2, 0.8, 0.3, 1.3) }} "
            f"{b}% {{ opacity: 1; transform: scale(1) }} "
            f"100% {{ opacity: 1; transform: scale(1) }} }}")


def build(pal):
    ink, muted, accent, hair = pal["ink"], pal["muted"], pal["accent"], pal["hair"]
    css, body = [], []

    # ---- base styles (also the reduced-motion static frame) ----
    css.append(f"""
  .lnk {{ stroke: {hair}; stroke-width: 1.4; }}
  .blk rect {{ fill: none; stroke: {muted}; stroke-width: 1.4; }}
  .tgt rect {{ stroke: {accent}; fill: {accent}; fill-opacity: 0.18; }}
  .fnl rect {{ fill: {ink}; stroke: {ink}; }}
  .ring {{ fill: none; stroke: {accent}; stroke-width: 1.3; }}
  .loz {{ fill: {accent}; transform-box: fill-box; transform-origin: center; }}
  .pulse {{ fill: none; stroke: {accent}; stroke-width: 1.5; opacity: 0;
           transform-box: fill-box; transform-origin: center; }}
  .dot {{ fill: none; stroke: {muted}; stroke-width: 1.2; }}
  .cvote {{ fill: {accent}; opacity: 0; }}
  .cline {{ stroke: {accent}; stroke-width: 1; opacity: 0; }}
  .beam {{ stroke: {accent}; stroke-width: 1.2; opacity: 0; }}
  .fin rect {{ fill: {ink}; stroke: {ink}; }}
  .cap {{ font-family: "Avenir Next", Avenir, "Segoe UI", system-ui, sans-serif;
         font-size: 7px; font-weight: 600; letter-spacing: 0.9px; fill: {muted}; }}""")

    anims = [".rnd { animation: rfade 11s linear infinite; }"]
    frames = [("@keyframes rfade { 0%, 96% { opacity: 1 } "
               "99.6%, 100% { opacity: 0 } }")]

    round_parts = []

    # ---- chain -----------------------------------------------------------
    static_blocks = []
    for i in (0, 1):  # confirmed prefix — not finalized yet
        static_blocks.append(
            f'<g class="blk"><line class="lnk" x1="{bx(i)+BLK}" y1="{CY}" x2="{bx(i+1)}" y2="{CY}"/>'
            f'<rect x="{bx(i)}" y="{CHAIN_Y}" width="{BLK}" height="{BLK}" rx="1.5"/></g>')
        static_blocks.append(
            f'<path class="loz" d="M{bcx(i)} 8l4.5 4.5-4.5 4.5-4.5-4.5z"/>')
    static_blocks.append(  # the round's target (tinted), confirmed as well
        f'<g class="blk tgt"><rect x="{bx(TGT)}" y="{CHAIN_Y}" width="{BLK}" height="{BLK}" rx="1.5"/></g>'
        f'<path class="loz" d="M{bcx(TGT)} 8l4.5 4.5-4.5 4.5-4.5-4.5z"/>')

    for k in range(1, NS + 1):        # heads appearing in slots 1..8
        i = TGT + k
        t0 = (k - 1) * SLOT
        frames.append(keyframes_appear(f"app{k}", t0 if k > 1 else 0.02, 0.22))
        frames.append(keyframes_pulse(f"pul{k}", t0 + 0.05))
        frames.append(keyframes_pop(f"loz{k}", t0 + 0.70))
        anims += [
            f".b{k} {{ animation: app{k} 11s linear infinite; }}",
            f".p{k} {{ animation: pul{k} 11s linear infinite; }}",
            f".z{k} {{ animation: loz{k} 11s linear infinite; }}",
        ]
        round_parts.append(
            f'<g class="blk b{k}">'
            f'<line class="lnk" x1="{bx(i-1)+BLK}" y1="{CY}" x2="{bx(i)}" y2="{CY}"/>'
            f'<rect x="{bx(i)}" y="{CHAIN_Y}" width="{BLK}" height="{BLK}" rx="1.5"/></g>')
        round_parts.append(
            f'<circle class="pulse p{k}" cx="{bcx(i)}" cy="{CY}" r="9"/>')
        round_parts.append(
            f'<path class="loz z{k}" d="M{bcx(i)} 8l4.5 4.5-4.5 4.5-4.5-4.5z"/>')

    # ---- votes per slot ----------------------------------------------------
    for k in range(1, NS + 1):
        i = TGT + k
        t0 = (k - 1) * SLOT
        frames.append(keyframes_flash(f"com{k}", t0 + 0.18, t0 + 0.72))
        frames.append(keyframes_flash(f"cln{k}", t0 + 0.20, t0 + 0.66, peak=0.4))
        frames.append(keyframes_appear(f"coh{k}", t0 + 0.45, 0.35))
        frames.append(keyframes_flash(f"bem{k}", t0 + 0.38, t0 + 1.05, peak=0.5))
        anims += [
            f".f{k} {{ animation: com{k} 11s linear infinite; }}",
            f".e{k} {{ animation: cln{k} 11s linear infinite; }}",
            f".c{k} {{ animation: coh{k} 11s linear infinite; }}",
            f".m{k} {{ animation: bem{k} 11s linear infinite; }}",
        ]
        # committee flash + vote arrows to the new head
        for d in COMMITTEES[k - 1]:
            _, x, y = DOTS[d]
            round_parts.append(
                f'<line class="cline e{k}" x1="{x}" y1="{y}" x2="{bcx(i)}" y2="{CHAIN_Y+BLK+2}" marker-end="url(#ah)"/>')
            round_parts.append(f'<circle class="cvote f{k}" cx="{x}" cy="{y}" r="{DOTR}"/>')
        # cohort k casts its finality vote on the round's fixed target
        round_parts.append(
            f'<line class="beam m{k}" x1="{COLX[k-1]}" y1="63" x2="{bcx(TGT)}" y2="{CHAIN_Y+BLK+2}" marker-end="url(#ah)"/>')
        for kk, x, y in DOTS:
            if kk == k - 1:
                round_parts.append(f'<circle class="cvote c{k}" cx="{x}" cy="{y}" r="{DOTR}"/>')

    # ---- justification -----------------------------------------------------
    # nothing is justified mid-round; once all 8 cohorts have voted, the
    # target and its prefix (blocks 0..TGT) are justified together,
    # cascading. The round's own blocks stay merely confirmed.
    t_fin = NS * SLOT
    for i in range(0, TGT + 1):
        frames.append(keyframes_appear(f"fin{i}", t_fin + i * 0.06, 0.3))
        anims.append(f".g{i} {{ animation: fin{i} 11s linear infinite; }}")
        round_parts.append(
            f'<g class="fin g{i}"><rect x="{bx(i)}" y="{CHAIN_Y}" width="{BLK}" height="{BLK}" rx="1.5"/>'
            f'<circle class="ring" cx="{bcx(i)}" cy="{CY}" r="10.5"/></g>')

    # ---- legend (static) ---------------------------------------------------
    items = [
        ("avail", "AVAILABLE"),
        ("conf", "CONFIRMED · COMMITTEE VOTE"),
        ("coh", "COHORT · FG VOTE"),
        ("final", "JUSTIFIED"),
    ]
    char_w, sw, gap_in, gap_out, y = 4.75, 11, 7, 18, 140
    total = sum(sw + gap_in + len(t) * char_w for _, t in items) + gap_out * (len(items) - 1)
    x = (W - total) / 2
    legend = []
    for kind, label in items:
        cyl = y - 4
        if kind == "avail":
            legend.append(f'<rect x="{x}" y="{cyl-5.5}" width="{sw}" height="{sw}" rx="1.5" fill="none" stroke="{muted}" stroke-width="1.3"/>')
        elif kind == "conf":
            legend.append(f'<path d="M{x+sw/2} {cyl-3.5}l3.5 3.5-3.5 3.5-3.5-3.5z" fill="{accent}"/>')
        elif kind == "coh":
            legend.append(f'<circle cx="{x+sw/2}" cy="{cyl}" r="3.4" fill="{accent}"/>')
        else:
            legend.append(f'<rect x="{x}" y="{cyl-5.5}" width="{sw}" height="{sw}" rx="1.5" fill="{ink}"/>')
            legend.append(f'<circle cx="{x+sw/2}" cy="{cyl}" r="6.8" fill="none" stroke="{accent}" stroke-width="1.2"/>')
        legend.append(f'<text class="cap" x="{x+sw+gap_in}" y="{y}">{label}</text>')
        x += sw + gap_in + len(label) * char_w + gap_out

    css.append("\n  @media (prefers-reduced-motion: no-preference) {\n    "
               + "\n    ".join(anims + frames) + "\n  }")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}">
  <desc>Decoupled consensus, one finality-gadget round: each slot a new block
  joins the available chain and a sampled committee confirms the head; one of
  eight validator cohorts casts its finality vote on the target checkpoint;
  after eight slots the checkpoint finalizes.</desc>
  <style>{''.join(css)}
  </style>
  <defs>
    <marker id="ah" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5"
            markerHeight="5" orient="auto-start-reverse">
      <path d="M0 0L8 4L0 8z" fill="{accent}"/>
    </marker>
  </defs>
  {''.join(static_blocks)}
  {''.join(f'<circle class="dot" cx="{x}" cy="{y}" r="{DOTR}"/>' for _, x, y in DOTS)}
  <g class="rnd">
    {''.join(round_parts)}
  </g>
  {''.join(legend)}
</svg>
"""


here = os.path.dirname(os.path.abspath(__file__))
for suffix, pal in PALETTES.items():
    path = os.path.join(here, f"dc-animation{suffix}.svg")
    with open(path, "w") as f:
        f.write(build(pal))
    print(f"wrote {path}")
