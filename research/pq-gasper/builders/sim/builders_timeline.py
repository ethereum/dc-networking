"""Draw ../builders-timeline.svg: one slot of PQ Gasper votes, with and without builders.

Stdlib only, deterministic. Run: python3 builders_timeline.py

Each bar is (start, end in the fast case, end in the slow case, kind, label, label position).
Times are seconds from the start of slot N. Sources (see posts/pq-gasper-builders.md):
- deadlines: Gloas, votes due at 25 % and aggregates at 50 % of a 12 s slot;
- network: Anton Nashatyrev's simulation (1M validators, 16 subnets, mesh degree 8, home
  50/25 nodes off the vote subnets). Votes sent at 3.0 s reach 10 Gbit/s pools by 3.84 s
  (p99) / 4.38 s (max) and 100/50 home nodes by 6.67 s (max). A ~260 KiB aggregate
  reaches pools 0.6 s (p99) after it is published and the last 50/25 home node after
  4.55 s. Today's 789k validators and mesh degree 4 are a little faster (last node 3.86 s);
- proving: leanVM benchmarks @ 29077b733, all threads, 32-core EPYC 9355P to 8-core
  Ryzen (EIP-7870's attester class): subnet proof 0.24-1.12 s, 16 -> 1 merge 0.37-1.33 s.
  The builder's fast case is 16 EPYC servers, one per subnet (0.24 s, then a 0.37 s
  merge). Its slow case is one such server proving 16 subnets at 4 threads each (1.08 s,
  then 0.37 s); contention between the 16 proofs is not benchmarked;
- block: ethPandaOps, released at 0.51-1.45 s (today's timing, before ePBS), then
  132 + 0.93/KB ms (p50) to 655 + 3.66/KB ms (p99) to spread, extrapolated to ~313 KiB.
"""
from pathlib import Path

X0, PX, W, H, AXIS_Y = 210, 48, 1100, 470, 418
DEADLINES = [(3, "votes due"), (6, "aggregates due"), (12, "next block"), (15, "next votes due")]
LANES = [
    (84, "Spec today", ["the network aggregates:", "4 aggregators per subnet,", "the next proposer merges"], [
        (3.0, 3.84, 6.67, "net", "votes reach the aggregators: by 3.8 s (10 Gbit/s pool) to 6.7 s (100/50 home)", "right"),
        (3.84, 4.08, 7.79, "cpu", "prove ~1.5k votes → 1 proof: 0.24–1.1 s; the slow case misses 6 s", "right"),
        (6.0, 6.6, 10.55, "net", "16+ × 209 KiB reach every node: up to +4.6 s", "right"),
        (6.6, 6.97, 11.88, "cpu", "proposer merges 16 → 1: 0.4–1.3 s", "right"),
        (12.0, 12.94, 15.28, "net", "block N+1 carries the 303 KiB proof: 0.9–3.3 s", "left"),
    ]),
    (252, "Builders aggregate", ["builders sit on all 16 subnets,", "prove the whole slot and", "publish one aggregate"], [
        (3.0, 3.84, 4.38, "net", "votes reach builders on all 16 subnets: by 3.8–4.4 s at 10 Gbit/s", "right"),
        (3.84, 4.45, 5.82, "cpu", "16 subnet proofs, then merge: 0.6 s on 16 servers, 1.4 s on one", "right"),
        (4.45, 5.05, 10.37, "net", "one 303 KiB aggregate reaches every node", "right"),
        (6.0, 6.0, 12.0, "slack", "spare: 6.0–7.4 s for late votes", "in"),
        (12.0, 12.94, 15.28, "net", "block N+1: same proof, nothing left to merge", "left"),
    ]),
]
C = dict(net="#2f6db5", net_bg="#dce8f7", cpu="#c0601a", cpu_bg="#fbe3cf", slack="#4f8a2e",
         slack_bg="#e4f0da", ink="#1d2430", mute="#596372", grid="#e3e6ea", dead="#a3394a",
         panel="#f3f5f8")


def x(t):
    return X0 + t * PX


o = []
a = o.append
a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
  'font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif">')
a('<title>One slot of PQ Gasper votes: the network aggregates vs builders aggregate</title>')
a(f'<rect width="{W}" height="{H}" rx="10" fill="#ffffff"/>')
a('<defs><pattern id="hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
  f'<rect width="7" height="7" fill="{C["slack_bg"]}"/><line x1="0" y1="0" x2="0" y2="7" '
  f'stroke="{C["slack"]}" stroke-width="1.4" opacity="0.35"/></pattern></defs>')
top = 52
a(f'<rect x="{x(0)}" y="12" width="{12 * PX}" height="24" rx="5" fill="{C["panel"]}"/>')
a(f'<text x="{x(6)}" y="29" text-anchor="middle" font-size="13" font-weight="600" fill="{C["ink"]}">slot N: the votes are cast</text>')
a(f'<rect x="{x(12) + 3}" y="12" width="{3.6 * PX - 3:.0f}" height="24" rx="5" fill="{C["panel"]}"/>')
a(f'<text x="{x(13.8)}" y="29" text-anchor="middle" font-size="13" font-weight="600" fill="{C["ink"]}">slot N+1</text>')
for t in range(16):
    a(f'<line x1="{x(t)}" y1="{top}" x2="{x(t)}" y2="{AXIS_Y}" stroke="{C["grid"]}"/>')
for t in range(0, 16, 3):
    lab = f"{t} s" if t < 12 else ("12 s = 0" if t == 12 else "15 s = 3")
    a(f'<text x="{x(t)}" y="{AXIS_Y + 17}" text-anchor="middle" font-size="12" fill="{C["mute"]}">{lab}</text>')
for t, lab in DEADLINES:
    a(f'<line x1="{x(t)}" y1="{top - 6}" x2="{x(t)}" y2="{AXIS_Y}" stroke="{C["dead"]}" stroke-width="1.5" stroke-dasharray="5 4"/>')
    a(f'<text x="{x(t) + 4}" y="{top + 5}" font-size="11" font-weight="600" fill="{C["dead"]}">{lab}</text>')
for y0, title, sub, bars in LANES:
    a(f'<line x1="12" y1="{y0 - 14}" x2="{W - 12}" y2="{y0 - 14}" stroke="{C["grid"]}"/>')
    a(f'<text x="16" y="{y0 + 6}" font-size="14" font-weight="700" fill="{C["ink"]}">{title}</text>')
    for i, s in enumerate(sub):
        a(f'<text x="16" y="{y0 + 25 + 15 * i}" font-size="12" fill="{C["mute"]}">{s}</text>')
    for r, (t0, tf, ts, kind, label, pos) in enumerate(bars):
        y = y0 + 26 * r - 8
        if kind == "slack":
            a(f'<rect x="{x(t0):.1f}" y="{y}" width="{(ts - t0) * PX:.1f}" height="20" rx="4" fill="url(#hatch)" stroke="{C["slack"]}" stroke-width="1.2"/>')
        else:
            fg, bg = C[kind], C[kind + "_bg"]
            a(f'<rect x="{x(t0):.1f}" y="{y}" width="{(ts - t0) * PX:.1f}" height="20" rx="4" fill="{bg}" stroke="{fg}" stroke-dasharray="3 2"/>')
            a(f'<rect x="{x(t0):.1f}" y="{y}" width="{(tf - t0) * PX:.1f}" height="20" rx="4" fill="{fg}"/>')
        if pos == "right":
            # keep the label clear of a deadline line that sits just after the bar
            lx = x(ts) + 6
            for t, _ in DEADLINES:
                if 0 <= x(t) - x(ts) < 14:
                    lx = x(t) + 6
            a(f'<text x="{lx:.1f}" y="{y + 14}" font-size="12" fill="{C["ink"]}">{label}</text>')
        elif pos == "left":
            a(f'<text x="{x(t0) - 6:.1f}" y="{y + 14}" text-anchor="end" font-size="12" fill="{C["ink"]}">{label}</text>')
        else:
            a(f'<text x="{x((t0 + ts) / 2):.1f}" y="{y + 14}" text-anchor="middle" font-size="12" font-weight="600" fill="{C["slack"]}">{label}</text>')
ly, lx = H - 18, 16
for kind, lab in (("net", "network"), ("cpu", "proving (leanVM)"), ("slack", "spare time")):
    fill = "url(#hatch)" if kind == "slack" else C[kind]
    a(f'<rect x="{lx}" y="{ly - 12}" width="22" height="14" rx="3" fill="{fill}" stroke="{C[kind]}"/>')
    a(f'<text x="{lx + 28}" y="{ly}" font-size="12" fill="{C["mute"]}">{lab}</text>')
    lx += 50 + 7 * len(lab)
a(f'<rect x="{lx}" y="{ly - 12}" width="22" height="14" rx="3" fill="{C["net_bg"]}" stroke="{C["net"]}" stroke-dasharray="3 2"/>')
a(f'<text x="{lx + 28}" y="{ly}" font-size="12" fill="{C["mute"]}">solid: fast case, pale: slow case</text>')
a(f'<text x="{W - 16}" y="{ly}" text-anchor="end" font-size="11" fill="{C["mute"]}">12 s Gloas slot, network times at 1M validators. Sources: posts/pq-gasper-builders.md</text>')
a('</svg>')

out = Path(__file__).resolve().parent.parent / "builders-timeline.svg"
out.write_text("\n".join(o) + "\n")
print(f"wrote {out.name}: {W} x {H}")
