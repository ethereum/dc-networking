"""Draw ../builders-flow.svg: who carries a slot's votes, with and without builders.

Stdlib only, deterministic. Run: python3 builders_flow.py
Numbers are those of ../README.md: 788,728 validators (24,648 votes per slot, ~1,540
per subnet), leanVM proofs of 209 KiB per subnet and 303 KiB per slot, leanVM merge
times, and Anton Nashatyrev's 12.6 ms verification time.
"""
from pathlib import Path

W, H = 1100, 404
BW, BH = 190, 58
CX = [110, 400, 705, 995]                      # box centres
INK, MUTE, LINE, PANEL = "#1d2430", "#596372", "#8b95a1", "#f3f5f8"
BLUE, BLUE_BG = "#2f6db5", "#dce8f7"

o = []
a = o.append
a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
  'font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif">')
a('<title>Who carries a slot of PQ Gasper votes: the spec today vs builders aggregate</title>')
a(f'<rect width="{W}" height="{H}" rx="10" fill="#ffffff"/>')
a(f'<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
  f'<path d="M0,0 L10,5 L0,10 z" fill="{LINE}"/></marker></defs>')


def box(cx, y, title, sub, fill=PANEL, stroke=LINE, dash=False, h=BH):
    d = ' stroke-dasharray="5 4"' if dash else ""
    a(f'<rect x="{cx - BW / 2}" y="{y}" width="{BW}" height="{h}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1.4"{d}/>')
    a(f'<text x="{cx}" y="{y + h / 2 - 4}" text-anchor="middle" font-size="13" font-weight="700" fill="{INK}">{title}</text>')
    a(f'<text x="{cx}" y="{y + h / 2 + 13}" text-anchor="middle" font-size="11" fill="{MUTE}">{sub}</text>')


def arrow(i, y, top, bottom):
    """Arrow from box i to box i+1 at height y, with a two-line label above it."""
    x1, x2 = CX[i] + BW / 2 + 6, CX[i + 1] - BW / 2 - 6
    mid = (x1 + x2) / 2
    a(f'<text x="{mid}" y="{y - 20}" text-anchor="middle" font-size="12" font-weight="600" fill="{INK}">{top}</text>')
    a(f'<text x="{mid}" y="{y - 6}" text-anchor="middle" font-size="11" fill="{MUTE}">{bottom}</text>')
    a(f'<line x1="{x1}" y1="{y + 6}" x2="{x2}" y2="{y + 6}" stroke="{LINE}" stroke-width="1.6" marker-end="url(#arr)"/>')


def row(y, title, tier, tier_sub, tier_style, subnets_sub, proofs, proofs_sub, proposer_sub, node_sub):
    a(f'<text x="15" y="{y - 16}" font-size="14" font-weight="700" fill="{INK}">{title}</text>')
    m = y + BH / 2
    box(CX[0], y, "24,648 attesters", "one 2.5 KB vote each")
    arrow(0, m, "16 subnets", subnets_sub)
    box(CX[1], y, tier, tier_sub, **tier_style)
    arrow(1, m, proofs, proofs_sub)
    box(CX[2], y, "next proposer", proposer_sub)
    arrow(2, m, "block with", "303 KiB proof")
    box(CX[3], y, "every node", node_sub)


row(76, "Spec today", "64 aggregators", "4 per subnet × 1,540 votes", {},
    "every node on 2", "16–64 proofs", "209 KiB each", "merges 16 proofs: 0.4–1.3 s",
    "also gets the 16–64 proofs")
a(f'<line x1="12" y1="172" x2="{W - 12}" y2="172" stroke="#e3e6ea"/>')
row(228, "Builders aggregate", "builders", "prove 16 subnets, then merge",
    dict(fill=BLUE_BG, stroke=BLUE), "big nodes only", "1 aggregate", "303 KiB",
    "verifies one proof: ~13 ms", "also gets the 1 aggregate")

# fallback: the spec's aggregators, as backup
fy, fh = 318, 52
box(CX[1], fy, "aggregators as backup", "publish only what adds votes", fill="#ffffff", dash=True, h=fh)
x1, ym, x2 = CX[1] + BW / 2 + 6, fy + fh / 2, CX[2]
a(f'<path d="M{x1},{ym} L{x2},{ym} L{x2},{228 + BH + 8}" fill="none" stroke="{LINE}" stroke-width="1.6" '
  f'stroke-dasharray="5 4" marker-end="url(#arr)"/>')
a(f'<text x="{x1 + 8}" y="{ym + 18}" font-size="11" fill="{MUTE}">'
  'a proposer left with k of the 16 subnets merges them and earns k/16</text>')
a('</svg>')

out = Path(__file__).resolve().parent.parent / "builders-flow.svg"
out.write_text("\n".join(o) + "\n")
print(f"wrote {out.name}: {W} x {H}")
