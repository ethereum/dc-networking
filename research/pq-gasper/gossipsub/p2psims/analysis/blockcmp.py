#!/usr/bin/env python3
"""Loss-model check: compare two runs with the same background schedule (same seed: same block publishers, publish
times and sizes) on the same blocks. Per block (slots >= 2) and pooled: first-seen from slot start p50/p90/p99 and from
publish p50/p95/p99 over all online subscribers except the publisher (realism_check.py's rule), and the paired per-host
difference B - A. Also tracked attestations after the 4 s mark p50/p95/p99 and missing.
usage: blockcmp.py RUN_A RUN_B"""
import glob, json, os, sys
from multiprocessing import Pool

import numpy as np

runs = [a if os.path.isdir(a) else f"runs/{a}" for a in sys.argv[1:3]]
K_BLOCK, K_ATT = 1, 3  # perturb.KINDS = ["pq", "block", "col", "att", ...]


def load(run):
    return json.load(open(f"{run}/run.json")), json.load(open(f"{run}/bg.json"))


(ca, ba), (cb, bb) = load(runs[0]), load(runs[1])
assert ba == bb, "background schedules differ: not the same blocks"
assert [n["topics"] for n in ca["nodes"]] == [n["topics"] for n in cb["nodes"]], "node topics differ"
bg, nodes, t0 = ba, ca["nodes"], ca["first_slot_s"]
S = len(bg)
want = {s: {k for k, m in enumerate(bg[s]) if m[5] and m[4] in (K_BLOCK, K_ATT)} for s in range(2, S)}


def host(fn):
    out = {}
    for line in open(fn):
        if '"ev":"rxbg"' not in line:
            continue
        e = json.loads(line)
        s = e["slot"]
        if s in want:
            w = want[s]
            out[s] = {k: ms for k, ms in e["r"] if k in w}
    return int(fn.split("/n")[-1].split("/")[0]), out


def rx(run):
    with Pool(8) as pool:
        return dict(pool.map(host, sorted(glob.glob(f"{run}/shadow.data/hosts/n*/wbsim.*.stdout")), chunksize=16))


R = [rx(r) for r in runs]


def offline(i, s, cfg):
    return any(x < t0 + 12 * (s + 1) and y > t0 + 12 * s for x, y in cfg["nodes"][i].get("offline", []))


subs = {}
for i, nd in enumerate(nodes):
    for t in nd["topics"]:
        subs.setdefault(t, []).append(i)
q = lambda xs, ps: " / ".join(f"{v:.2f}" for v in np.percentile(xs, ps)) if len(xs) else "-"
print(f"A = {os.path.basename(runs[0])} (loss_scale {ca.get('loss_scale')}), "
      f"B = {os.path.basename(runs[1])} (loss_scale {cb.get('loss_scale')}); same blocks: yes")
pool_start, pool_pub, pool_d = [[], []], [[], []], []
for s in range(2, S):
    for k, m in enumerate(bg[s]):
        if m[4] != K_BLOCK or not m[5]:
            continue
        pub, off = m[0], m[1]
        st, pb, miss = [[], []], [[], []], [0, 0]
        d = []
        for i in subs[m[2]]:
            if i == pub:
                continue
            got = []
            for j, (r, c) in enumerate(zip(R, (ca, cb))):
                if offline(i, s, c):
                    got.append(None)
                    continue
                ms = r.get(i, {}).get(s, {}).get(k)
                got.append(ms)
                if ms is None:
                    miss[j] += 1
                else:
                    st[j].append(ms / 1e3)
                    pb[j].append((ms - off) / 1e3)
            if got[0] is not None and got[1] is not None:
                d.append((got[1] - got[0]) / 1e3)
        n = nodes[pub]
        print(f"slot {s} block: publisher {pub} ({n.get('client')}, {n['city']}), published {off / 1e3:.2f} s, "
              f"{m[3] / 1e3:.0f} kB")
        for j in (0, 1):
            print(f"  {'AB'[j]}: from slot start p50/p90/p99 {q(st[j], (50, 90, 99))} s; from publish p50/p95/p99 "
                  f"{q(pb[j], (50, 95, 99))} s; missing {miss[j]}")
            pool_start[j] += st[j]
            pool_pub[j] += pb[j]
        print(f"  B - A per host: p10/p50/p90/p99 {q(d, (10, 50, 90, 99))} s (n={len(d)})")
        pool_d += d
print("pooled over these blocks:")
for j in (0, 1):
    print(f"  {'AB'[j]}: from slot start p50/p90/p99 {q(pool_start[j], (50, 90, 99))} s; "
          f"from publish p50/p95/p99 {q(pool_pub[j], (50, 95, 99))} s")
print(f"  B - A per host: p10/p50/p90/p99 {q(pool_d, (10, 50, 90, 99))} s")
for j, (r, c) in enumerate(zip(R, (ca, cb))):
    xs, miss = [], 0
    for s in range(2, S):
        for k, m in enumerate(bg[s]):
            if m[4] != K_ATT or not m[5]:
                continue
            for i in subs[m[2]]:
                if i == m[0] or offline(i, s, c):
                    continue
                ms = r.get(i, {}).get(s, {}).get(k)
                if ms is None:
                    miss += 1
                else:
                    xs.append(ms / 1e3 - 4.0)
    print(f"  {'AB'[j]}: attestations after the 4 s mark p50/p95/p99 {q(xs, (50, 95, 99))} s; missing {miss} of "
          f"{len(xs) + miss}")
