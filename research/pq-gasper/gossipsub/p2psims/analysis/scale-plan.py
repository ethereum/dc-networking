# Projected peak RSS (GiB, shadow + all wbsim, as in runs/memlog.txt) of the queued PQ runs at each peer scale with
# the fixed binary, from the 512 x 4 x1.0 fixed-build probe.
# usage: python3 .amp-out/scale-plan.py [--probe-peak GIB] [--probe-conns N]   (defaults: from runs/P512-ps100-fx-s1)
#
# Model, fitted on old-build runs on this machine (Nov 6-7):
#   peak(H hosts, scale s, stop T) = H * f(H) * b(s) + H / 2048 * g(s, T)
#   b(s)    per-host RSS at sim 78 s of a 512-host x 4-slot PQ run. b(1.0) = probe peak / 512. b(0.25) = P512-ps025 (old)
#           minus the eager-queue saving at x0.25, the saving per connection being (P512-ps100 - probe) / its connections.
#           Linear in s in between (connections scale with s).
#   f(H)    per-host RSS at H hosts relative to 512 hosts: R6-pq-s1 (2,048 hosts) at sim 78 over 4 x P512-ps025 peak,
#           both x0.25 old build; log-linear in H.
#   g(s, T) growth from sim 78 to T at 2,048 hosts, from the no-PQ runs R-nopq-s1 (x0.25) and R-nopq-ps100-s1 (x1.0),
#           extended past their last point with the slope of their last 100 simulated seconds; linear in s.
#           Assumes the fixed build grows like the old one.
import argparse, json, math, re
from collections import defaultdict

ap = argparse.ArgumentParser()
ap.add_argument("--probe", default="P512-ps100-fx-s1")
ap.add_argument("--probe-peak", type=float)
ap.add_argument("--probe-conns", type=float)
ap.add_argument("--limit", type=float, default=225.0)
a = ap.parse_args()

curves = defaultdict(dict)  # run -> sim -> max RSS
for line in open("runs/memlog.txt"):
    m = re.match(r"\S+ (\S+) sim=(\d+)s rss=([\d.]+)GB", line)
    if m:
        c = curves[m.group(1)]
        s = int(m.group(2))
        c[s] = max(c.get(s, 0.0), float(m.group(3)))


def at(run, t):
    pts = sorted(curves[run].items())
    top = max(range(len(pts)), key=lambda i: pts[i][1])
    pts = pts[:top + 1]  # drop the shutdown samples after the peak, when the wbsim processes exit
    if t >= pts[-1][0]:  # extend with the slope of the last 100 simulated seconds
        x1, y1 = pts[-1]
        x0, y0 = next(p for p in reversed(pts) if p[0] <= x1 - 100)
        return y1 + (y1 - y0) / (x1 - x0) * (t - x1)
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= t <= x1:
            return y0 + (y1 - y0) * (t - x0) / max(x1 - x0, 1)
    return pts[0][1]


def peak(run):
    return max(curves[run].values())


def conns(run):
    r = json.load(open(f"runs/{run}/realism.json"))
    nodes = json.load(open(f"runs/{run}/run.json"))["nodes"]
    n = defaultdict(int)
    for nd in nodes:
        n[nd["link"]] += 1
    return sum(r["peers"][f"link:{c}"]["conns"]["mean"] * k for c, k in n.items()) / len(nodes)


X = a.probe_peak if a.probe_peak is not None else peak(a.probe)
cx = a.probe_conns if a.probe_conns is not None else conns(a.probe)
p25, p100 = peak("P512-ps025"), peak("P512-ps100")
c25, c100 = conns("P512-ps025"), conns("P512-ps100")
saving = (p100 - X) / (512 * c100)  # GiB per connection
b = {1.0: X / 512, 0.25: (p25 - saving * 512 * c25) / 512}
f2048 = at("R6-pq-s1", 78) / (4 * p25)
f = lambda H: 1 + (f2048 - 1) * math.log2(H / 512) / 2
g25 = lambda T: at("R-nopq-s1", T) - at("R-nopq-s1", 78)
g100 = lambda T: at("R-nopq-ps100-s1", T) - at("R-nopq-ps100-s1", 78)


def proj(H, s, T):
    bs = b[0.25] + (s - 0.25) / 0.75 * (b[1.0] - b[0.25])
    gs = g25(T) + (s - 0.25) / 0.75 * (g100(T) - g25(T))
    return H * f(H) * bs + H / 2048 * gs


print(f"probe peak {X:.1f} GiB at {cx:.0f} connections per host; old build x1.0 {p100:.1f} GiB ({c100:.0f}), "
      f"x0.25 {p25:.1f} GiB ({c25:.0f})")
print(f"eager-queue saving {saving * 1024:.2f} MiB per connection; per-host at sim 78: x1.0 {b[1.0] * 1024:.0f} MiB, "
      f"x0.25 {b[0.25] * 1024:.0f} MiB; f(2048) {f2048:.3f}")
print(f"check, old build: R6-pq-s1 projected {2048 * f(2048) * p25 / 512 + g25(112):.1f} GiB at sim 112, "
      f"measured {peak('R6-pq-s1'):.1f} (max so far)")
for name, H, T in (("L 1,024 x 50 (stop 640 s)", 1024, 640), ("R6 2,048 x 6 (stop 112 s)", 2048, 112)):
    row = {s: proj(H, s, T) for s in (1.0, 0.75, 0.5, 0.25)}
    best = next((s for s in (1.0, 0.75, 0.5, 0.25) if row[s] <= a.limit), None)
    print(f"{name}: " + ", ".join(f"x{s}: {v:.0f} GiB" for s, v in row.items()) + f" -> highest scale <= {a.limit:.0f} GiB: x{best}")
