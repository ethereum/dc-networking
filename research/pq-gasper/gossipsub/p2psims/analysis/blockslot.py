#!/usr/bin/env python3
"""Per-slot block first-seen from publish (p50 / p95, s) for runs/NAME ..., computed as realism_check.sec_prop does
(slots >= 2; subscribers other than the publisher; node-slots offline in the slot excluded; missing deliveries left out).
Usage: python3 -I .amp-out/blockslot.py NAME [NAME ...]"""
import glob
import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, "/home/yann/p2p-ministry-gossip2000/repo/sim")
import perturb  # noqa: E402
from analyze import read_cfg  # noqa: E402

KID = perturb.KINDS.index("block")
for name in sys.argv[1:]:
    run = name if os.path.isdir(name) else os.path.join("runs", name)
    cfg = read_cfg(run)
    bg = json.load(open(os.path.join(run, "bg.json")))
    t0, nodes = cfg["first_slot_s"], cfg["nodes"]
    subs = defaultdict(list)
    for i, nd in enumerate(nodes):
        for t in nd["topics"]:
            subs[t].append(i)
    offl = lambda i, s: any(x < t0 + 12 * (s + 1) and y > t0 + 12 * s for x, y in nodes[i].get("offline", []))
    blocks = {s: [(k, m) for k, m in enumerate(msgs) if m[4] == KID and m[5]] for s, msgs in enumerate(bg) if s >= 2}
    keys = {s: {k for k, _ in v} for s, v in blocks.items()}
    rx = defaultdict(dict)  # (slot, node) -> {block index: ms from slot start}
    for f in glob.glob(os.path.join(run, "shadow.data/hosts/*/wbsim.*.stdout")):
        for line in open(f):
            if not line.startswith('{"ev":"rxbg"'):
                continue
            e = json.loads(line)
            ks = keys.get(e["slot"])
            if ks:
                rx[(e["slot"], e["node"])] = {k: ms for k, ms in e["r"] if k in ks}
    p50, p95, n, miss = [], [], [], []
    for s in sorted(blocks):
        d, mi = [], 0
        for k, m in blocks[s]:
            for i in subs[m[2]]:
                if i == m[0] or (nodes[i].get("offline") and offl(i, s)):
                    continue
                ms = rx.get((s, i), {}).get(k)
                if ms is None:
                    mi += 1
                else:
                    d.append((ms - m[1]) / 1e3)
        p50.append(round(float(np.percentile(d, 50)), 3) if d else None)
        p95.append(round(float(np.percentile(d, 95)), 3) if d else None)
        n.append(len(d))
        miss.append(mi)
    first = min(blocks)
    print(f"== {name}: block first-seen from publish per slot {first}-{max(blocks)} (s)")
    print("  p95 " + " ".join(f"{x:.2f}" if x is not None else "-" for x in p95))
    print("  p50 " + " ".join(f"{x:.2f}" if x is not None else "-" for x in p50))
    print(f"  deliveries per slot {min(n)}-{max(n)}, missing {sum(miss)}")
