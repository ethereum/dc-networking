#!/usr/bin/env python3
"""On-wire upload/download rate of the hosts captured with gen_config.py --pcap.

    python3 sim/pcap_rate.py runs/<run>

For each captured host: its link caps, and the highest rate over any 0.1 s, 0.5 s and
1 s window (IP packet bytes, headers included), each direction. The app-level byte
counters in wbsim count writes into the socket buffer, which can run ahead of the link;
the pcap shows what Shadow actually put on the wire.
"""

import glob
import json
import os
import struct
import sys
from collections import defaultdict

UNITS = {"Mbit": 1e6, "Gbit": 1e9}


def packets(path):
    with open(path, "rb") as f:
        gh = f.read(24)
        magic = struct.unpack("<I", gh[:4])[0]
        nano = magic == 0xA1B23C4D
        link = struct.unpack("<I", gh[20:24])[0]
        off = 14 if link == 1 else 0  # Ethernet or raw IP
        while True:
            h = f.read(16)
            if len(h) < 16:
                return
            sec, frac, incl, orig = struct.unpack("<IIII", h)
            data = f.read(incl)
            if len(data) < off + 20:
                continue
            ip = data[off:off + 20]
            yield sec + frac / (1e9 if nano else 1e6), orig - off, ip[12:16], ip[16:20]


def peak(bins, width, step):
    """Highest bits/s over any window of `width` s, from per-`step` byte bins."""
    k = max(1, round(width / step))
    keys = sorted(bins)
    if not keys:
        return 0.0
    lo, hi = keys[0], keys[-1]
    arr = [bins.get(i, 0) for i in range(lo, hi + 1)]
    best, acc = 0, sum(arr[:k])
    best = acc
    for i in range(k, len(arr)):
        acc += arr[i] - arr[i - k]
        best = max(best, acc)
    return best * 8 / width


def main(run):
    cfg = json.load(open(os.path.join(run, "run.json")))
    t_start = cfg["first_slot_s"]
    t_end = t_start + cfg["slots"] * cfg["slot_s"]
    print("| host | link | cap down/up (Mbit/s) | up peak 0.1 s / 0.5 s / 1 s (Mbit/s) | up mean over slots | "
          "down peak 0.1 s / 0.5 s / 1 s | down mean over slots |")
    print("|---|---|---|---|---|---|---|")
    step = 0.01
    for p in sorted(glob.glob(os.path.join(run, "shadow.data/hosts/*/eth0.pcap"))):
        name = p.split("/")[-2]
        node = cfg["nodes"][int(name[1:])]
        me = bytes(int(x) for x in node["ip"].split("."))
        up, down = defaultdict(int), defaultdict(int)
        tot = [0, 0]
        for t, n, src, dst in packets(p):
            t -= 946684800 if t > 946684800 else 0
            if not t_start <= t < t_end:
                continue
            b = int(t / step)
            if src == me:
                up[b] += n
                tot[0] += n
            elif dst == me:
                down[b] += n
                tot[1] += n
        cap = [float(node[k].split()[0]) * UNITS[node[k].split()[1]] / 1e6 for k in ("down", "up")]
        f = lambda bins: " / ".join(f"{peak(bins, w, step) / 1e6:.2f}" for w in (0.1, 0.5, 1.0))
        dur = t_end - t_start
        print(f"| {name} | {node['link']} | {cap[0]:.0f}/{cap[1]:.0f} | {f(up)} | {tot[0] * 8 / dur / 1e6:.2f} | "
              f"{f(down)} | {tot[1] * 8 / dur / 1e6:.2f} |")


if __name__ == "__main__":
    main(sys.argv[1])
