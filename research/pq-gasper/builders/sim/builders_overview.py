"""Draw ../builders-overview.svg: the figure of ../README.md.

Two lanes that read left to right, and two finish lines.
- Regular path: 16 attestation subnets, 16 aggregation subnets, one global aggregation
  topic. Whether it delivers by block N+1 is open, hence the dashed arrow and the question
  mark. It does deliver by block N+2 (24 s), when the votes are included (pq spec @ 4c29678:
  two-slot inclusion delay).
- What we add: recent proposers, or their builders, take the raw votes and publish on a
  lightweight global topic. It delivers by block N+1 (12 s), which is what fork choice needs.
The lines are deadlines, not measurements, and the horizontal axis is not to scale.

Stdlib only, deterministic. Run: python3 builders_overview.py
"""
from pathlib import Path

W, H = 920, 290
INK, MUTE = "#1d2430", "#5c6675"
GREY, GREY_LINE, GREY_BG = "#6b7480", "#aab1bb", "#f1f3f5"
GREEN, GREEN_BG = "#3f7f2f", "#e6f2de"

o = []
a = o.append
a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
  'font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif">')
a('<title>The regular path delivers a slot of PQ Gasper votes by block N+2; the lightweight global topic we add delivers them by block N+1</title>')
a(f'<rect width="{W}" height="{H}" rx="10" fill="#ffffff"/>')
a('<defs>')
for name, col in (("g", GREY), ("n", GREEN)):
    a(f'<marker id="arr-{name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" markerHeight="6.5" '
      f'orient="auto"><path d="M0,0.8 L10,5 L0,9.2 z" fill="{col}"/></marker>')
a('</defs>')


def text(x, y, s, size=12, fill=INK, weight=None, anchor="start", spacing=None):
    w = f' font-weight="{weight}"' if weight else ""
    ls = f' letter-spacing="{spacing}"' if spacing else ""
    a(f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}"{w}{ls} text-anchor="{anchor}">{s}</text>')


def node(x, y, w, title, sub=None, added=False):
    fill, stroke, sw = (GREEN_BG, GREEN, 1.5) if added else (GREY_BG, GREY_LINE, 1.25)
    a(f'<rect x="{x}" y="{y}" width="{w}" height="{BH}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
    if sub:
        text(x + w / 2, y + BH / 2 - 2, title, 14, INK, 600, "middle")
        text(x + w / 2, y + BH / 2 + 15, sub, 12, MUTE, None, "middle")
    else:
        text(x + w / 2, y + BH / 2 + 5, title, 14, INK, 600, "middle")


def arrow(x1, x2, y, col, mk, dash=False):
    d = ' stroke-dasharray="5 4"' if dash else ""
    a(f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{col}" stroke-width="1.6"{d} marker-end="url(#arr-{mk})"/>')


# grid: three columns of boxes, a start line and two finish lines
X0, C1, C2, C3, F1, F2 = 44, 76, 284, 492, 766, 872
W1, W3, BH = 176, 212, 48
LANE_A, LANE_B = 100, 190
MID_A, MID_B = LANE_A + BH / 2, LANE_B + BH / 2
TOP, BOTTOM = 58, 250

# the regular path may or may not make block N+1 and does make block N+2; the added lane makes block N+1
arrow(C3 + W3 + 5, F1 - 13, MID_A, GREY, "g", dash=True)
arrow(F1 + 13, F2 - 2, MID_A, GREY, "g")
arrow(C3 + W3 + 5, F1 - 2, MID_B, GREEN, "n")

# start line and finish lines, with what each deadline is for
for x, name, when, col, purpose in ((X0, "votes", "3 s", GREY_LINE, None),
                                    (F1, "block N+1", "12 s", GREEN, "fork choice"),
                                    (F2, "block N+2", "24 s", GREY, "inclusion")):
    a(f'<line x1="{x}" y1="{TOP}" x2="{x}" y2="{BOTTOM}" stroke="{col}" stroke-width="{1.25 if purpose is None else 2}"/>')
    text(x, 28, name, 13, INK, 600, "middle")
    text(x, 45, when, 12, MUTE, None, "middle")
    if purpose:
        text(x, BOTTOM + 22, purpose, 12.5, col, 600, "middle")
# whether the regular path is in time for fork choice is the open question
a(f'<circle cx="{F1}" cy="{MID_A}" r="10.5" fill="#ffffff" stroke="{GREY}" stroke-width="1.5"/>')
text(F1, MID_A + 5, "?", 14, GREY, 700, "middle")

# lane 1: the regular path
text(C1, LANE_A - 11, "REGULAR PATH", 10.5, GREY, 700, spacing="0.7")
node(C1, LANE_A, W1, "16 attestation subnets")
node(C2, LANE_A, W1, "16 aggregation subnets")
node(C3, LANE_A, W3, "1 global aggregation topic")
arrow(X0, C1 - 6, MID_A, GREY, "g")
arrow(C1 + W1 + 5, C2 - 6, MID_A, GREY, "g")
arrow(C2 + W1 + 5, C3 - 6, MID_A, GREY, "g")

# lane 2: what we add
text(C2, LANE_B - 11, "WHAT WE ADD", 10.5, GREEN, 700, spacing="0.7")
node(C2, LANE_B, W1, "Recent proposers", "or their builders", added=True)
node(C3, LANE_B, W3, "Lightweight global topic", added=True)
a(f'<path d="M{C1 + W1 / 2},{LANE_A + BH + 5} V{MID_B} H{C2 - 6}" fill="none" stroke="{GREEN}" stroke-width="1.6" marker-end="url(#arr-n)"/>')
text(C1 + W1 / 2 - 9, MID_B - 9, "raw votes", 12, GREEN, None, "end")
arrow(C2 + W1 + 5, C3 - 6, MID_B, GREEN, "n")
a('</svg>')

out = Path(__file__).resolve().parent.parent / "builders-overview.svg"
out.write_text("\n".join(o) + "\n")
print(f"wrote {out.name}: {W} x {H}")
