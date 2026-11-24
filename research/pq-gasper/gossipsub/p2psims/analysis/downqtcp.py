#!/usr/bin/env python3
"""TCP view of delivery into home nodes, PQ Gasper subnet specs study (Nov 23; coordinator 14:2x): .amp-out/leafdiag.py
for any link classes. From the per-connection 'tcpd snap' lines (one per connection per 12 s bin, cumulative counters,
logged at the data sender) of a run on a '-log' Shadow wrapper (LNXBUF_LOG=1; run_lever.sh moves them to
shadow-tcpd.log.gz). Per path type, data sender class -> receiver class: data packets, retransmission timeouts and the
share Eifel found spurious (the ACK of the original came back after the timeout: a delay spike, not a loss),
retransmissions, and SRTT minus the configured RTT at the snapshots. Slots 2 to the last. Classes: '1G' for the 1 Gbit
hosts, the link (down/up) for the others, '-leaf' for non-forwarding hosts (--freeride-share).
usage: python3 -I .amp-out/downqtcp.py RUN"""
import collections, gzip, json, os, re, sys
import numpy as np

run = sys.argv[1] if os.path.isdir(sys.argv[1]) else f"runs/{sys.argv[1]}"
rj = json.load(open(f"{run}/run.json"))
S = rj["slots"]


def cls(n):
    c = "1G" if n["link"] == "cloud" else n["link"].replace("x", "/")
    return c + ("-leaf" if n.get("freeride") else "")


hostcls = {f"n{n['id']:04d}": cls(n) for n in rj["nodes"]}
ipcls = {n["ip"]: cls(n) for n in rj["nodes"]}
F = ["txdata", "timeouts", "spurious", "retx", "undone", "samples"]
RE = re.compile(r"\[(n\d{4}):[0-9.]+\] .*tcpd snap (0x[0-9a-f]+) bin (-?\d+) peer (\d+) .* srtt (\d+) .* cfgrtt (\d+)")
FRE = {k: re.compile(r" %s (\d+)" % k) for k in F}
last = {}
acc = collections.defaultdict(lambda: np.zeros(len(F)))
srtt = collections.defaultdict(list)
for line in gzip.open(f"{run}/shadow-tcpd.log.gz", "rt", errors="replace"):
    if "tcpd snap" not in line:
        continue
    m = RE.search(line)
    if not m:
        continue
    host, ptr, b, peer, sr, cr = m.group(1), m.group(2), int(m.group(3)), int(m.group(4)), int(m.group(5)), int(m.group(6))
    ip = ".".join(str((peer >> k) & 255) for k in (0, 8, 16, 24))
    key = (hostcls.get(host, "?"), ipcls.get(ip, "?"))
    v = np.array([int(FRE[k].search(line).group(1)) for k in F], dtype=float)
    p = last.get((host, ptr))
    last[(host, ptr)] = (b, v)
    if p is not None and 2 <= p[0] < S and b > p[0] and (v >= p[1]).all():
        acc[key] += v - p[1]  # counters of bins p[0] .. b-1 (mostly one slot)
    if 2 <= b < S and sr > 0:
        srtt[key].append(sr - cr)
homes = sorted({c for c in hostcls.values() if c != "1G" and not c.endswith("-leaf")}, key=lambda c: int(c.split("/")[0]))
order = ["1G", "1G-leaf"] + [x for c in homes for x in (c, c + "-leaf")]
print(f"== {os.path.basename(run)}: per path type (data sender -> receiver), slots 2-{S - 1}; per 1,000 data packets")
print(f"{'path':24s} {'data pkts':>11s} {'RTOs':>7s} {'spurious':>8s} {'(%)':>6s} {'retx':>7s} | SRTT-RTT ms p50/p90/p99")
for b in order[::-1]:  # paths into home nodes first
    for a in order:
        v = acc.get((a, b))
        if v is None or v[0] < 1000:
            continue
        d = np.array(srtt.get((a, b), [0]))
        print(f"{a + ' -> ' + b:24s} {v[0]:11.0f} {1000 * v[1] / v[0]:7.2f} {1000 * v[2] / v[0]:8.2f} {100 * v[2] / max(v[1], 1):6.1f} "
              f"{1000 * v[3] / v[0]:7.2f} | {np.percentile(d, 50):.0f} / {np.percentile(d, 90):.0f} / {np.percentile(d, 99):.0f}")
