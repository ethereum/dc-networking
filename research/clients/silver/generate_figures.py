#!/usr/bin/env python3
"""Figures for the Silver gossipsub note, in light and dark variants.

Run from anywhere: python3 generate_figures.py  ->  figures/*.svg
Palette: the validated reference categorical slots 1-3 (blue, orange, aqua),
stepped separately for the light and dark surfaces.
"""

from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent / "figures"
FONT = "system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
WIDTH = 760

THEMES = {
    "light": dict(surface="#fcfcfb", panel="#f3f2ee", ink="#0b0b0b", ink2="#52514e",
                  muted="#898781", grid="#e1e0d9", axis="#c3c2b7",
                  border="rgba(11,11,11,0.10)",
                  s1="#2a78d6", s2="#eb6834", s3="#1baf7a"),
    "dark": dict(surface="#1a1a19", panel="#242422", ink="#f0efec", ink2="#c3c2b7",
                 muted="#898781", grid="#2c2c2a", axis="#383835",
                 border="rgba(255,255,255,0.10)",
                 s1="#3987e5", s2="#d95926", s3="#199e70"),
}


def text(x, y, s, size=12, fill="ink", weight=400, anchor="start", t=None, extra=""):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" '
            f'fill="{t[fill]}" text-anchor="{anchor}"{extra}>{escape(s)}</text>')


def svg(height, title, desc, body, t):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height}" '
            f'width="{WIDTH}" height="{height}" role="img" aria-labelledby="t d">\n'
            f'<title id="t">{escape(title)}</title>\n<desc id="d">{escape(desc)}</desc>\n'
            f'<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{height - 1}" rx="12" '
            f'fill="{t["surface"]}" stroke="{t["border"]}"/>\n'
            f'<g font-family="{FONT}">\n' + "\n".join(body) + "\n</g>\n</svg>\n")


def legend(items, y, t):
    """items: (kind, colour key, label); kind is 'square', 'dot', 'ring' or 'arrow'."""
    out, x = [], 24
    for kind, key, label in items:
        if kind == "square":
            out.append(f'<rect x="{x}" y="{y - 9}" width="10" height="10" rx="3" fill="{t[key]}"/>')
        elif kind == "dot":
            out.append(f'<circle cx="{x + 5}" cy="{y - 4}" r="5" fill="{t[key]}"/>')
        elif kind == "ring":
            out.append(f'<circle cx="{x + 5}" cy="{y - 4}" r="4.5" fill="none" '
                       f'stroke="{t["muted"]}" stroke-width="1.5"/>')
        elif kind == "arrow":
            out.append(text(x + 5, y, "↗", 13, "ink2", 600, "middle", t))
        out.append(text(x + 16, y, label, 12, "ink2", t=t))
        x += 16 + 6.4 * len(label) + 26
    return out


# ── Figure 1: what an over-subscribed mesh keeps ──────────────────────────────

def mesh_trim(t):
    body = [
        text(24, 34, "Over-subscribed mesh: what survives a trim", 15, "ink", 600, t=t),
        text(24, 54, "D = 8, D_high = 12. Each dot is a mesh peer, highest score on the left.",
             12, "ink2", t=t),
    ]
    body += legend([("dot", "s1", "kept: highest score"), ("dot", "s3", "kept: at random"),
                    ("ring", None, "pruned"), ("arrow", None, "outbound (we dialed it)")], 82, t)

    def panel(y, heading, rule, kinds, outbound, caption, graft, graft_detail):
        rows = [f'<rect x="16" y="{y}" width="{WIDTH - 32}" height="136" rx="10" '
                f'fill="{t["panel"]}"/>',
                text(32, y + 26, heading, 13, "ink", 600, t=t),
                text(32, y + 47, rule, 12, "ink2", t=t)]
        cy = y + 92
        for i, kind in enumerate(kinds):
            cx = 44 + 30 * i
            if kind == "pruned":
                rows.append(f'<circle cx="{cx}" cy="{cy}" r="8.5" fill="none" '
                            f'stroke="{t["muted"]}" stroke-width="1.5"/>')
            else:
                rows.append(f'<circle cx="{cx}" cy="{cy}" r="9" fill="{t[kind]}" '
                            f'stroke="{t["panel"]}" stroke-width="2"/>')
            if i in outbound:
                rows.append(text(cx + 9, cy - 10, "↗", 12, "ink2", 600, "middle", t))
        rows.append(text(32, cy + 32, caption, 11.5, "muted", t=t))
        rows.append(text(470, cy - 6, graft, 12.5, "ink", 600, t=t))
        rows.append(text(470, cy + 13, graft_detail, 12, "ink2", t=t))
        return rows

    v11 = ["s1"] * 4 + ["pruned", "s3"] * 4
    body += panel(98, "gossipsub v1.1 spec, as implemented by go-libp2p and rust-libp2p",
                  "Trim at 12 peers: keep the 4 best by score, 4 at random, at least 2 outbound.",
                  v11, {1, 9}, "12 peers → 8 kept",
                  "GRAFT from an inbound peer at ≥ 12", "refused; an outbound peer may still join")
    silver = ["s1"] * 8 + ["pruned"] * 5
    body += panel(248, "Silver",
                  "Trim only above 12: keep the 8 best by topic-local score. No random share, "
                  "no outbound quota.",
                  silver, set(), "13 peers → 8 kept; a mesh of exactly 12 is never trimmed",
                  "GRAFT at ≥ 12 peers", "accepted if score ≥ 0 and not backed off")
    title = "Over-subscribed mesh: what survives a trim"
    desc = ("Two panels. gossipsub v1.1 (go-libp2p, rust-libp2p): a mesh of 12 is trimmed to 8, "
            "keeping 4 peers by score, 4 at random and at least 2 outbound; inbound GRAFTs at 12 "
            "are refused. Silver: only a mesh above 12 is trimmed, to the 8 best by topic-local "
            "score, with no random share and no outbound quota; GRAFTs at 12 are accepted.")
    return svg(400, title, desc, body, t)


# ── Figure 2: Silver's traffic numbers vs the 2 Gbit/s claim ─────────────────

MIB_TO_GBIT = 1024 * 1024 * 8 / 1e9
COLUMN_BYTES = 8 + 3 * 4 + 208 + 4 * 32 + 21 * (2048 + 48 + 48)  # Fulu sidecar, 21 blobs
BLOCK_COLUMN_BYTES = 128 * COLUMN_BYTES


def column_burst(mesh, window_s):
    return BLOCK_COLUMN_BYTES * (mesh - 1) * 8 / window_s / 1e9


ROWS = [
    ("s1", "Mainnet supernode, average each way", 0.10),
    ("s1", "Mainnet supernode, bursts", 0.50),
    ("s1", "Announcement snapshot, p2p in", 28.68 * MIB_TO_GBIT),
    ("s1", "Announcement snapshot, p2p out", 46.96 * MIB_TO_GBIT),
    ("s2", "Claimed: up to 2 Gbit/s of gossip", 2.00),
    ("s3", "Column burst in 1 s, 8-peer mesh", column_burst(8, 1.0)),
    ("s3", "Column burst in 0.25 s, 8-peer mesh", column_burst(8, 0.25)),
    ("s3", "Column burst in 0.25 s, 12-peer mesh", column_burst(12, 0.25)),
]


def bar(x, y, w, h, fill, r=4):
    r = min(r, w / 2)
    return (f'<path d="M{x:.1f},{y:.1f} h{w - r:.1f} a{r},{r} 0 0 1 {r},{r} v{h - 2 * r:.1f} '
            f'a{r},{r} 0 0 1 {-r},{r} h{-(w - r):.1f} z" fill="{fill}"/>')


def bandwidth(t):
    body = [
        text(24, 34, "Gossip traffic: Silver's own numbers vs the 2 Gbit/s claim", 15, "ink", 600,
             t=t),
        text(24, 54, "Gbit/s. Estimates are a supernode's outbound data-column burst at 21 blobs "
             "per block.", 12, "ink2", t=t),
    ]
    body += legend([("square", "s1", "Silver's own measurements"),
                    ("square", "s2", "Claimed capacity"),
                    ("square", "s3", "Back-of-envelope estimate")], 82, t)

    x0, px_per_gbit, top, row_h, bar_h = 316, 172.0, 106, 28, 14
    ys, y, previous = [], top, None
    for key, _, _ in ROWS:
        if previous is not None and key != previous:
            y += 12
        ys.append(y)
        y += row_h
        previous = key
    bottom = y - row_h + bar_h + 8

    for v in (0.5, 1.0, 1.5, 2.0):
        gx = x0 + v * px_per_gbit
        body.append(f'<line x1="{gx:.1f}" y1="{top - 8}" x2="{gx:.1f}" y2="{bottom}" '
                    f'stroke="{t["grid"]}" stroke-width="1"/>')
    for (key, label, value), ry in zip(ROWS, ys):
        w = value * px_per_gbit
        body.append(bar(x0, ry, w, bar_h, t[key]))
        body.append(text(x0 - 12, ry + 11, label, 12.5, "ink", anchor="end", t=t))
        # The surface-coloured halo keeps gridlines from running through the value.
        body.append(text(x0 + w + 7, ry + 11, f"{value:.2f}", 12, "ink2", t=t,
                         extra=f' font-variant-numeric="tabular-nums" stroke="{t["surface"]}" '
                               'stroke-width="4" stroke-linejoin="round" paint-order="stroke"'))
    body.append(f'<line x1="{x0}" y1="{top - 8}" x2="{x0}" y2="{bottom}" '
                f'stroke="{t["axis"]}" stroke-width="1"/>')
    for v in (0.0, 0.5, 1.0, 1.5, 2.0):
        body.append(text(x0 + v * px_per_gbit, bottom + 18, f"{v:.1f}", 11.5, "muted", 400,
                         "middle", t))
    body.append(text(x0 + 2.25 * px_per_gbit, bottom + 18, "Gbit/s", 11.5, "muted", 400,
                     "start", t))
    notes = ["README figures are approximate. Snapshot: tile-flow image in the 29 Oct 2026 "
             "announcement (28.68 / 46.96 MiB/s).",
             f"Estimates: 128 columns × {COLUMN_BYTES / 1000:.1f} kB per block, each forwarded "
             "to every other mesh member, before IDONTWANT savings."]
    for i, note in enumerate(notes):
        body.append(text(24, bottom + 48 + 16 * i, note, 11, "muted", t=t))
    height = int(bottom + 48 + 16 * len(notes) + 10)
    title = "Gossip traffic: Silver's own numbers vs the 2 Gbit/s claim"
    desc = "; ".join(f"{label}: {value:.2f} Gbit/s" for _, label, value in ROWS)
    return svg(height, title, desc, body, t)


def main():
    OUT.mkdir(exist_ok=True)
    for name, build in (("mesh-trim", mesh_trim), ("bandwidth", bandwidth)):
        for theme, tokens in THEMES.items():
            suffix = "" if theme == "light" else "-dark"
            (OUT / f"{name}{suffix}.svg").write_text(build(tokens))
    print("column sidecar bytes:", COLUMN_BYTES)
    for _, label, value in ROWS:
        print(f"  {label}: {value:.3f} Gbit/s")


if __name__ == "__main__":
    main()
