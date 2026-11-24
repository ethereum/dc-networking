#!/usr/bin/env python3
"""Charts for ../pq-gasper-on-gossipsub.md.

Run from anywhere: python3 generate_charts.py  ->  single-subnet.svg and uplink.svg next to this script.

Each SVG holds a light and a dark palette and switches with prefers-color-scheme, so a plain Markdown image works on
GitHub and on HackMD; without CSS it falls back to the light palette. Palette from
research/clients/silver/generate_figures.py. Data: the "Load" table of ../../results/pq-gasper-one-subnet.md (2,048
nodes, one seed per load; the 1,600 run covers slots 2-14).
"""

from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent
FONT = "system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
WIDTH = 760

LIGHT = dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e", muted="#898781", grid="#e1e0d9",
             axis="#c3c2b7", border="rgba(11,11,11,0.10)", s1="#2a78d6", s2="#eb6834", s3="#9e9d95")
DARK = dict(surface="#1a1a19", ink="#f0efec", ink2="#c3c2b7", muted="#898781", grid="#2c2c2a",
            axis="#383835", border="rgba(255,255,255,0.10)", s1="#3987e5", s2="#d95926", s3="#77766f")

GASPER = 1600  # signatures per subnet per slot: ~25,000 per slot at 800k validators, over 16 subnets
LOADS = [200, 300, 400, 600, 800, 1600]

# label, link and node count, largest load passed, next load tested (failed), colour
CLASSES = [
    ("Home, no validators", "50/15 Mbit/s · 330 nodes", 300, 400, "s1"),
    ("Home stakers", "50/25 Mbit/s · 976 nodes", 400, 600, "s2"),
    ("1 Gbit nodes", "1 Gbit/s · 742 nodes", 800, 1600, "s3"),
]

# label, link, upload handed to TCP 4-8 s into the slot (% of the uplink, all traffic) at each load, passed, colour
UPLINK = [
    ("Home, no validators", "50/15 Mbit/s", [33.9, 45.9, 55.9, 71.6, 84.3, 114.9], [1, 1, 0, 0, 0, 0], "s1"),
    ("Home stakers", "50/25 Mbit/s", [22.6, 31.1, 38.5, 50.1, 59.1, 85.1], [1, 1, 1, 0, 0, 0], "s2"),
]


def paint(fill=None, stroke=None):
    """Light colours as attributes, for renderers without CSS; the classes switch both palettes."""
    out, cls = [], []
    if fill:
        out.append(f'fill="{LIGHT[fill]}"')
        cls.append(f"f-{fill}")
    if stroke:
        out.append(f'stroke="{LIGHT[stroke]}"')
        cls.append(f"k-{stroke}")
    return " ".join(out + [f'class="{" ".join(cls)}"'])


def text(x, y, s, size=13, fill="ink", weight=400, anchor="start"):
    w = f' font-weight="{weight}"' if weight != 400 else ""
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return f'<text x="{x:g}" y="{y:g}" font-size="{size}"{w}{a} {paint(fill)}>{escape(s)}</text>'


def line(x1, y1, x2, y2, stroke, width=1, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" stroke-width="{width}"{d} {paint(stroke=stroke)}/>'


def svg(height, title, desc, body):
    def rules(p):
        return "".join(f".f-{k}{{fill:{v}}}.k-{k}{{stroke:{v}}}" for k, v in p.items())

    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height}" width="{WIDTH}" height="{height}" '
        f'role="img" aria-labelledby="t d" font-family="{FONT}">',
        f'<title id="t">{escape(title)}</title>',
        f'<desc id="d">{escape(desc)}</desc>',
        f"<style>text{{font-variant-numeric:tabular-nums}}{rules(LIGHT)}"
        f"@media (prefers-color-scheme: dark){{{rules(DARK)}}}</style>",
        f'<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{height - 1}" rx="12" {paint("surface", "border")}/>',
        *body,
        "</svg>",
        "",
    ])


def single_subnet():
    x0, x1 = 216, 600            # plot, 0 to 1,600 signatures per subnet per slot
    col_pass, col_fail = 672, 736  # right edges of the two number columns
    head, top, step = 36, 72, 52  # header baseline, first row's centre, row spacing
    axis_y = top + step * (len(CLASSES) - 1) + 34

    def x(v):
        return x0 + (x1 - x0) * v / GASPER

    body = [text(x1 - 8, head, "One PQ Gasper subnet", 12, "ink2", anchor="end"),
            text(col_pass, head, "passed", 12, "ink2", anchor="end"),
            text(col_fail, head, "failed", 12, "muted", anchor="end")]
    body += [line(x(v), head + 12, x(v), axis_y, "grid") for v in (400, 800, 1200)]
    body.append(line(x1, head - 12, x1, axis_y, "ink2", 1.5, "4 3"))
    for i, (name, sub, ok, bad, c) in enumerate(CLASSES):
        cy = top + step * i
        body += [
            text(24, cy - 2, name, 14, "ink", 600),
            text(24, cy + 15, sub, 12, "ink2"),
            f'<rect x="{x(ok):g}" y="{cy - 9}" width="{x(bad) - x(ok):g}" height="18" fill-opacity="0.2" '
            f'stroke-width="1.25" stroke-dasharray="3 2" {paint(c, c)}/>',
            f'<rect x="{x0}" y="{cy - 9}" width="{x(ok) - x0:g}" height="18" {paint(c)}/>',
            text(col_pass, cy + 5, f"{ok:,}", 14, "ink", 600, "end"),
            text(col_fail, cy + 5, f"{bad:,}", 14, "muted", anchor="end"),
        ]
    body.append(line(x0, axis_y, x1, axis_y, "axis"))
    body += [text(x(v), axis_y + 18, f"{v:,}", 12, "muted", anchor="start" if v == 0 else "middle")
             for v in (0, 400, 800, 1200, 1600)]
    body.append(text(x0, axis_y + 40, "Signatures per subnet per slot", 12.5, "ink2"))
    desc = ("Horizontal bars, signatures per subnet per slot, against the 1,600 of one PQ Gasper subnet. "
            + "; ".join(f"{n} ({s}): passed {ok:,}, failed {bad:,}" for n, s, ok, bad, _ in CLASSES) + ".")
    return svg(axis_y + 58, "Largest load each class passed, and the next load tested, which failed", desc, body)


def uplink():
    x0, x1, y_top, y0, vmax = 64, 556, 64, 286, 125  # plot box; y axis 0 to 125 % of the uplink

    def x(v):
        return x0 + (x1 - x0) * v / GASPER

    def y(v):
        return y0 - (y0 - y_top) * v / vmax

    lx = 604
    body = [
        text(24, 34, "Upload 4–8 s into the slot, as a share of the uplink", 13, "ink2"),
        f'<circle cx="{lx}" cy="30" r="5" {paint("ink2")}/>',
        text(lx + 11, 34, "passed", 12.5, "ink2"),
        f'<circle cx="{lx + 74}" cy="30" r="4.25" stroke-width="1.75" {paint("surface", "ink2")}/>',
        text(lx + 85, 34, "failed", 12.5, "ink2"),
        line(x0, y0, x1, y0, "axis"),
    ]
    for v, note in ((50, "half the uplink"), (100, "full uplink")):
        body += [line(x0, y(v), x1, y(v), "muted", 1, "4 3"), text(x0 + 6, y(v) - 7, note, 12, "muted")]
    body += [text(x0 - 8, y(v) + 4, f"{v} %", 12, "muted", anchor="end") for v in (0, 50, 100)]
    body += [text(x(v), y0 + 18, f"{v:,}", 12, "muted", anchor="middle") for v in (0, 400, 800, 1200, 1600)]
    body.append(text((x0 + x1) / 2, y0 + 40, "Signatures per subnet per slot", 12.5, "ink2", anchor="middle"))
    for name, sub, up, ok, c in UPLINK:
        pts = " ".join(f"{x(n):g},{y(u):g}" for n, u in zip(LOADS, up))
        body.append(f'<polyline points="{pts}" fill="none" stroke-width="2.5" stroke-linejoin="round" '
                    f'{paint(stroke=c)}/>')
        for n, u, p in zip(LOADS, up, ok):
            body.append(f'<circle cx="{x(n):g}" cy="{y(u):g}" r="5" {paint(c)}/>' if p else
                        f'<circle cx="{x(n):g}" cy="{y(u):g}" r="4.25" stroke-width="2" {paint("surface", c)}/>')
        body += [text(x1 + 14, y(up[-1]) + 1, name, 13, c, 600), text(x1 + 14, y(up[-1]) + 17, sub, 12, "ink2")]
    desc = ("Lines of mean upload 4–8 s into the slot, as a share of the uplink, against signatures per subnet per slot "
            f"({', '.join(f'{n:,}' for n in LOADS)}). "
            + "; ".join(f"{n} ({s}): " + ", ".join(f"{u:g} %" for u in up)
                        + f", passed up to {LOADS[ok.index(0) - 1]:,}" for n, s, up, ok, _ in UPLINK) + ".")
    return svg(y0 + 58, "Home nodes fail once their mean upload reaches about half the uplink", desc, body)


def main():
    for name, build in (("single-subnet", single_subnet), ("uplink", uplink)):
        (OUT / f"{name}.svg").write_text(build())
        print("wrote", OUT / f"{name}.svg")


if __name__ == "__main__":
    main()
