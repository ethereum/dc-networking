"""Draw ../builders-overview.svg: the figure of ../builders.md.

Top: the regular path with its topics (16 attestation subnets, 16 aggregation subnets, one
global aggregation topic), and under it what the post adds: recent proposers, or their
builders, publish on a lightweight global topic.
Bottom: the two deadlines, and nothing measured. Fork choice needs slot N's votes before
block N+1 (12 s), which is what the lightweight topic is for. Inclusion needs them before
block N+2 (24 s, pq spec @ 4c29678: votes are included two slots later), which is all the
regular path has to meet.

Stdlib only, deterministic. Run: python3 builders_overview.py
"""
from pathlib import Path

W, H = 1100, 396
INK, MUTE, GRID = "#1d2430", "#596372", "#e3e6ea"
GREY, GREY_BG = "#6b7480", "#eef0f3"
GREEN, GREEN_BG = "#3f7f2f", "#e4f0da"

o = []
a = o.append
a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
  'font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif">')
a('<title>The regular path of PQ Gasper votes, the lightweight global topic added to it, and their deadlines</title>')
a(f'<rect width="{W}" height="{H}" rx="10" fill="#ffffff"/>')
a('<defs>')
for name, col in (("g", GREY), ("n", GREEN)):
    a(f'<marker id="arr-{name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
      f'orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{col}"/></marker>')
a('</defs>')


def text(x, y, s, size=12, fill=INK, weight=None, anchor="start"):
    w = f' font-weight="{weight}"' if weight else ""
    a(f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}"{w} text-anchor="{anchor}">{s}</text>')


def box(x, y, w, h, fill, stroke):
    a(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')


def arrow(x1, y1, x2, y2, col, mk, width=1.6):
    a(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col}" stroke-width="{width}" marker-end="url(#arr-{mk})"/>')


# ---- top: the topics ---------------------------------------------------------
ROW_A, ROW_B, BH = 40, 150, 60      # the regular path, what we add, box height
MID_A, MID_B = ROW_A + BH / 2, ROW_B + BH / 2


def node(x, y, w, title, sub, fill, stroke, h=BH, size=13):
    box(x, y, w, h, fill, stroke)
    if sub:
        text(x + w / 2, y + h / 2 - 3, title, size, INK, 700, "middle")
        text(x + w / 2, y + h / 2 + 15, sub, 11.5, MUTE, None, "middle")
    else:
        text(x + w / 2, y + h / 2 + 5, title, size, INK, 700, "middle")


text(168, ROW_A - 12, "Regular path", 12.5, GREY, 700)
node(20, ROW_A, 120, "Slot N votes", None, "#ffffff", INK)
node(168, ROW_A, 180, "16 attestation subnets", None, GREY_BG, GREY)
node(370, ROW_A, 180, "16 aggregation subnets", None, GREY_BG, GREY)
node(572, ROW_A, 210, "1 global aggregation topic", None, GREY_BG, GREY)
arrow(144, MID_A, 162, MID_A, GREY, "g")
arrow(352, MID_A, 364, MID_A, GREY, "g")
arrow(554, MID_A, 566, MID_A, GREY, "g")

text(370, ROW_B - 12, "What we add", 12.5, GREEN, 700)
node(370, ROW_B, 180, "Recent proposers", "or their builders", GREEN_BG, GREEN)
node(572, ROW_B, 210, "Lightweight global topic", None, GREEN_BG, GREEN)
a(f'<path d="M258,{ROW_A + BH + 4} V{MID_B} H364" fill="none" stroke="{GREEN}" stroke-width="1.6" marker-end="url(#arr-n)"/>')
arrow(554, MID_B, 566, MID_B, GREEN, "n")

EX, EW = 860, 220
node(EX, ROW_A, EW, "Every node", None, "#ffffff", INK, ROW_B + BH - ROW_A, 15)
arrow(786, MID_A, EX - 6, MID_A, GREY, "g", 2)
arrow(786, MID_B, EX - 6, MID_B, GREEN, "n", 2)

# ---- bottom: the deadlines ---------------------------------------------------
a(f'<line x1="12" y1="240" x2="{W - 12}" y2="240" stroke="{GRID}"/>')
T0, T1 = 60, 1040


def x(t):
    return T0 + t * (T1 - T0) / 24


text(24, 266, "Deadlines", 13, INK, 700)
AX = 346
BARS = [
    (284, 12, GREEN, GREEN_BG, "Lightweight topic: fork choice", (3 + 12) / 2),
    (312, 24, GREY, GREY_BG, "Regular path: inclusion", (12 + 24) / 2),
]
for y, t_end, col, bg, label, t_label in BARS:
    a(f'<rect x="{x(3):.1f}" y="{y}" width="{x(t_end) - x(3):.1f}" height="22" rx="4" fill="{bg}"/>')
    a(f'<line x1="{x(t_end):.1f}" y1="{y - 6}" x2="{x(t_end):.1f}" y2="{AX}" stroke="{col}" stroke-width="2.5"/>')
    text(f"{x(t_label):.1f}", y + 15, label, 12, col, 600, "middle")

a(f'<line x1="{x(0)}" y1="{AX}" x2="{x(24)}" y2="{AX}" stroke="{MUTE}" stroke-width="1.2"/>')
for t, event in ((0, "block N"), (3, "votes"), (12, "block N+1"), (24, "block N+2")):
    a(f'<line x1="{x(t):.1f}" y1="{AX - 5}" x2="{x(t):.1f}" y2="{AX + 5}" stroke="{MUTE}" stroke-width="1.2"/>')
    text(f"{x(t):.1f}", AX + 21, f"{t} s", 12, INK, 600, "middle")
    text(f"{x(t):.1f}", AX + 37, event, 11.5, MUTE, None, "middle")
a('</svg>')

out = Path(__file__).resolve().parent.parent / "builders-overview.svg"
out.write_text("\n".join(o) + "\n")
print(f"wrote {out.name}: {W} x {H}")
