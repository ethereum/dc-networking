"""Draw ../builders-overview.svg: the figure of the short post in ../builders.md.

Top: who gets slot N's votes to every node (regular path, option 1, option 2).
Bottom: when the last home node has them, against the arrival of block N+1.

Stdlib only, deterministic. Run: python3 builders_overview.py
With --suggested it writes ../builders-overview-suggested.svg instead, the figure of the
suggested short version: builders publish to protect their own blocks, and the box on the
right no longer gives a 40 % threshold (that only holds against the boost alone).
Times (seconds from the start of slot N), see ../builders.md:
- regular path: the first subnet proofs go out at 7.2 s (pq spec @ 4c29678), reach a
  global aggregator 0.6 s later, are merged in 0.37-1.33 s, and the full aggregate needs
  up to 4.55 s to reach the last home node: 12.7-13.7 s;
- a relay (builder or recent proposer) has the votes by 3.84-4.38 s, proves the slot in
  0.6-1.4 s, and its aggregate needs the same 4.55 s: 9.0-10.4 s.
Network times are Anton Nashatyrev's simulation at 1M validators, proving times leanVM's
benchmarks @ 29077b733.
"""
import sys
from pathlib import Path

SUGGESTED = "--suggested" in sys.argv
W, H = 1100, 500
INK, MUTE, GRID = "#1d2430", "#596372", "#e3e6ea"
GREY, GREY_BG = "#6b7480", "#eef0f3"
BLUE, BLUE_BG = "#2f6db5", "#dce8f7"
GREEN, GREEN_BG = "#3f7f2f", "#e4f0da"
RED, RED_BG = "#a3394a", "#f6dde1"

o = []
a = o.append
a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
  'font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif">')
a('<title>Who gets a slot of PQ Gasper votes to every node, and when</title>')
a(f'<rect width="{W}" height="{H}" rx="10" fill="#ffffff"/>')
a('<defs>')
for name, col in (("g", GREY), ("b", BLUE), ("n", GREEN)):
    a(f'<marker id="arr-{name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
      f'orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{col}"/></marker>')
a('</defs>')


def text(x, y, s, size=12, fill=INK, weight=None, anchor="start"):
    w = f' font-weight="{weight}"' if weight else ""
    a(f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}"{w} text-anchor="{anchor}">{s}</text>')


def box(x, y, w, h, fill, stroke, dash=False):
    d = ' stroke-dasharray="6 4"' if dash else ""
    a(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{fill}" stroke="{stroke}" stroke-width="1.5"{d}/>')


# ---- top: who relays -------------------------------------------------------
LX, LY, LW, LH = 24, 110, 196, 100
box(LX, LY, LW, LH, "#ffffff", INK)
text(LX + LW / 2, LY + 32, "Slot N", 15, INK, 700, "middle")
text(LX + LW / 2, LY + 54, "24,648 votes, cast by 3 s", 12, MUTE, None, "middle")
text(LX + LW / 2, LY + 72, "on 16 attestation subnets", 12, MUTE, None, "middle")

RX, RW, RH = 320, 350, 76
if SUGGESTED:
    BUILDERS_DO, BUILDERS_SEND = "publish it to protect their own blocks", "the full aggregate"
else:
    BUILDERS_DO, BUILDERS_SEND = "the full aggregate goes with their offer", "a good enough view"
RELAYS = [
    (28, "Regular path", ["subnet aggregators prove, global aggregators merge",
                          "open to anyone, as far as its machine allows"], GREY, GREY_BG, "g", True, "may be late"),
    (122, "Option 1: builders", ["sit on all 16 subnets and prove the whole slot",
                                 BUILDERS_DO], BLUE, BLUE_BG, "b", False, BUILDERS_SEND),
    (216, "Option 2: the last W proposers (say 8)", ["any of them that can aggregate may publish",
                                                     "one honest one is enough"], GREEN, GREEN_BG, "n", False, "full or partial"),
]
EX, EY, EW, EH = 800, 28, 276, 264
for y, title, subs, col, bg, mk, dash, lab in RELAYS:
    box(RX, y, RW, RH, bg, col, dash)
    text(RX + RW / 2, y + 26, title, 13.5, INK, 700, "middle")
    for i, s in enumerate(subs):
        text(RX + RW / 2, y + 45 + 16 * i, s, 11.5, MUTE, None, "middle")
    my = y + RH / 2
    d = ' stroke-dasharray="6 4"' if dash else ""
    # votes in, aggregate out
    a(f'<line x1="{LX + LW + 4}" y1="{LY + LH / 2}" x2="{RX - 6}" y2="{my}" stroke="{col}" stroke-width="1.6"{d} marker-end="url(#arr-{mk})"/>')
    a(f'<line x1="{RX + RW + 6}" y1="{my}" x2="{EX - 6}" y2="{my}" stroke="{col}" stroke-width="2"{d} marker-end="url(#arr-{mk})"/>')
    text((RX + RW + EX) / 2, my - 9, lab, 11.5, col, 600, "middle")

box(EX, EY, EW, EH, "#ffffff", INK)
cx = EX + EW / 2
text(cx, EY + 40, "Every node", 15, INK, 700, "middle")
if SUGGESTED:
    NEEDS, MUTED, NEEDS_Y = ["needs slot N's votes", "before block N+1 arrives,",
                             "from someone other than", "its proposer."], None, EY + 77
    OTHERWISE = ["Otherwise the boost of block N+1", "is enough to orphan block N."]
else:
    NEEDS, MUTED, NEEDS_Y = ["needs over 40 % of slot N's votes", "(7 to 10 of the 16 subnets)",
                             "before block N+1 arrives,", "from someone other than", "its proposer."], 1, EY + 68
    OTHERWISE = ["Otherwise the 40 % boost of block N+1", "is enough to orphan block N."]
for i, s in enumerate(NEEDS):
    text(cx, NEEDS_Y + 18 * i, s, 12, MUTE if i == MUTED else INK, None, "middle")
for i, s in enumerate(OTHERWISE):
    text(cx, EY + 190 + 17 * i, s, 12, RED, 600, "middle")

# ---- bottom: when ------------------------------------------------------------
a(f'<line x1="12" y1="312" x2="{W - 12}" y2="312" stroke="{GRID}"/>')
T0, PX = 320, 50


def x(t):
    return T0 + t * PX


text(24, 338, "When the last home node has the votes", 13, INK, 700)
AX = 446
for t in range(0, 15):
    a(f'<line x1="{x(t)}" y1="350" x2="{x(t)}" y2="{AX}" stroke="{GRID}"/>')
for t in (0, 3, 6, 9, 12):
    text(x(t), AX + 16, f"{t} s", 12, MUTE, None, "middle")

ROWS = [
    (352, "Regular path", None, 7.2, 12.7, 13.7, GREY, GREY_BG,
     "subnet proofs at 7.2 s, merge, gossip", "12.7–13.7 s: too late", "end"),
    (398, "Option 1 or 2", "same timing, different sender", 3.0, 9.0, 10.4, GREEN, GREEN_BG,
     "votes at 3 s, one proof, then gossip", "9.0–10.4 s: at least 1.6 s to spare", "middle"),
]
for y, name, sub, t_from, t_a, t_b, col, bg, inside, verdict, anchor in ROWS:
    text(24, y + 14, name, 12.5, INK, 700)
    if sub:
        text(24, y + 29, sub, 11, MUTE)
    a(f'<rect x="{x(t_from):.1f}" y="{y}" width="{(t_a - t_from) * PX:.1f}" height="18" rx="4" fill="{bg}"/>')
    text((x(t_from) + x(t_a)) / 2, y + 13, inside, 11, MUTE, None, "middle")
    if t_b > 12:      # arrives after block N+1: too late for fork choice
        a(f'<rect x="{x(t_a):.1f}" y="{y}" width="{(t_b - t_a) * PX:.1f}" height="18" rx="4" fill="{RED}"/>')
        text(x(12) + 8, y + 33, verdict, 12, RED, 600, "start")
    else:
        a(f'<rect x="{x(t_a):.1f}" y="{y}" width="{(t_b - t_a) * PX:.1f}" height="18" rx="4" fill="{col}"/>')
        text((x(t_a) + x(t_b)) / 2, y + 33, verdict, 12, col, 600, "middle")

a(f'<line x1="{x(12)}" y1="328" x2="{x(12)}" y2="{AX}" stroke="{RED}" stroke-width="1.8" stroke-dasharray="6 4"/>')
text(x(12) - 8, 338, "block N+1 arrives", 12, RED, 600, "end")
text(24, H - 14, "Times from Anton Nashatyrev's simulation (1M validators) and leanVM's benchmarks.", 11, MUTE)
a('</svg>')

out = Path(__file__).resolve().parent.parent / ("builders-overview-suggested.svg" if SUGGESTED else "builders-overview.svg")
out.write_text("\n".join(o) + "\n")
print(f"wrote {out.name}: {W} x {H}")
