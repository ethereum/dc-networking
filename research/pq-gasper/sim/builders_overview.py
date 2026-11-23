"""Draw ../builders-overview.svg: the figure of ../builders.md.

Top: the regular path with its topics (16 attestation subnets, 16 aggregation subnets, one
global aggregation topic), and the lightweight global topic the post adds, on which only
the proposers of the last W slots publish.
Bottom: when the last home node has slot N's votes, against the arrival of block N+1.

Stdlib only, deterministic. Run: python3 builders_overview.py
Times (seconds from the start of slot N):
- regular path: the first subnet proofs go out at 7.2 s (pq spec @ 4c29678), reach a
  global aggregator 0.6 s later, are merged in 0.37-1.33 s, and the full aggregate needs
  up to 4.55 s to reach the last home node: 12.7-13.7 s;
- lightweight topic: a relay with a builder's links and servers has the votes by
  3.84-4.38 s, proves the slot in 0.6-1.4 s, and its aggregate needs the same 4.55 s:
  9.0-10.4 s.
Network times are Anton Nashatyrev's simulation at 1M validators, proving times leanVM's
benchmarks @ 29077b733.
"""
from pathlib import Path

W, H = 1100, 480
INK, MUTE, GRID = "#1d2430", "#596372", "#e3e6ea"
GREY, GREY_BG = "#6b7480", "#eef0f3"
GREEN, GREEN_BG = "#3f7f2f", "#e4f0da"
RED = "#a3394a"

o = []
a = o.append
a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
  'font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif">')
a('<title>The regular path of PQ Gasper votes, and the lightweight global topic added to it</title>')
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


def arrow(x1, y1, x2, y2, col, mk, width=1.6, dash=False):
    d = ' stroke-dasharray="6 4"' if dash else ""
    a(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col}" stroke-width="{width}"{d} marker-end="url(#arr-{mk})"/>')


# ---- top: the topics ---------------------------------------------------------
ROW_A, ROW_B, BH = 36, 176, 88      # the regular path, what we add, box height
MID_A, MID_B = ROW_A + BH / 2, ROW_B + BH / 2


def topic(x, y, w, title, subs, fill, stroke, size=13):
    box(x, y, w, BH, fill, stroke)
    text(x + w / 2, y + 30, title, size, INK, 700, "middle")
    for i, s in enumerate(subs):
        text(x + w / 2, y + 51 + 16 * i, s, 11, MUTE, None, "middle")


text(168, ROW_A - 12, "Regular path", 12.5, GREY, 700)
topic(20, ROW_A, 120, "Slot N", ["24,648 votes", "cast by 3 s"], "#ffffff", INK, 15)
topic(168, ROW_A, 180, "16 attestation subnets", ["about 1,500 raw votes each", "EIP-7870 nodes join none"], GREY_BG, GREY)
topic(370, ROW_A, 180, "16 aggregation subnets", ["one proof per subnet", "209 KiB each"], GREY_BG, GREY)
topic(572, ROW_A, 210, "1 global aggregation topic", ["one merged proof per slot", "303 KiB"], GREY_BG, GREY)
arrow(144, MID_A, 162, MID_A, GREY, "g")
arrow(352, MID_A, 364, MID_A, GREY, "g")
arrow(554, MID_A, 566, MID_A, GREY, "g")

text(370, ROW_B - 10, "What we add", 12.5, GREEN, 700)
topic(370, ROW_B, 412, "Lightweight global topic",
      ["only the proposers of the last W slots publish (say 8)",
       "their own proof or their builder's, at most W per slot"], GREEN_BG, GREEN, 13.5)
# raw votes go down to the recent proposers, who prove the whole slot
a(f'<path d="M258,{ROW_A + BH + 4} V{MID_B} H364" fill="none" stroke="{GREEN}" stroke-width="1.6" marker-end="url(#arr-n)"/>')
text(250, MID_B - 24, "recent proposers, or their", 11, GREEN, 600, "end")
text(250, MID_B - 8, "builders, prove the whole slot", 11, GREEN, 600, "end")

EX, EW = 860, 220
box(EX, ROW_A, EW, ROW_B + BH - ROW_A, "#ffffff", INK)
cx = EX + EW / 2
text(cx, ROW_A + 36, "Every node", 15, INK, 700, "middle")
for i, s in enumerate(["needs slot N's votes", "before block N+1 arrives."]):
    text(cx, ROW_A + 64 + 18 * i, s, 12, INK, None, "middle")
for i, s in enumerate(["EIP-7870 nodes follow", "only these two topics."]):
    text(cx, ROW_A + 114 + 16 * i, s, 11.5, MUTE, None, "middle")
for i, s in enumerate(["Otherwise the boost of", "block N+1 is enough", "to orphan block N."]):
    text(cx, ROW_A + 168 + 17 * i, s, 12, RED, 600, "middle")
arrow(786, MID_A, EX - 6, MID_A, GREY, "g", 2, True)
text((782 + EX) / 2, MID_A - 9, "may be late", 11.5, GREY, 600, "middle")
arrow(786, MID_B, EX - 6, MID_B, GREEN, "n", 2)
text((782 + EX) / 2, MID_B - 9, "in time", 11.5, GREEN, 600, "middle")

# ---- bottom: when ------------------------------------------------------------
a(f'<line x1="12" y1="290" x2="{W - 12}" y2="290" stroke="{GRID}"/>')
T0, PX = 320, 50


def x(t):
    return T0 + t * PX


text(24, 316, "When the last home node has the votes", 13, INK, 700)
AX = 424
for t in range(0, 15):
    a(f'<line x1="{x(t)}" y1="328" x2="{x(t)}" y2="{AX}" stroke="{GRID}"/>')
for t in (0, 3, 6, 9, 12):
    text(x(t), AX + 16, f"{t} s", 12, MUTE, None, "middle")

ROWS = [
    (330, "Regular path", None, 7.2, 12.7, 13.7, GREY, GREY_BG,
     "subnet proofs at 7.2 s, merge, gossip", "12.7–13.7 s: too late"),
    (376, "Lightweight topic", "with a builder's links and servers", 3.0, 9.0, 10.4, GREEN, GREEN_BG,
     "votes at 3 s, one proof, then gossip", "9.0–10.4 s: at least 1.6 s to spare"),
]
for y, name, sub, t_from, t_a, t_b, col, bg, inside, verdict in ROWS:
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

a(f'<line x1="{x(12)}" y1="306" x2="{x(12)}" y2="{AX}" stroke="{RED}" stroke-width="1.8" stroke-dasharray="6 4"/>')
text(x(12) - 8, 316, "block N+1 arrives", 12, RED, 600, "end")
text(24, H - 14, "Times from Anton Nashatyrev's simulation (1M validators) and leanVM's benchmarks.", 11, MUTE)
a('</svg>')

out = Path(__file__).resolve().parent.parent / "builders-overview.svg"
out.write_text("\n".join(o) + "\n")
print(f"wrote {out.name}: {W} x {H}")
