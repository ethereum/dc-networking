#!/usr/bin/env python3
"""Does each per-slot series level off? For every line "LABEL [v, v, ...]" in the given analysis outputs (pqdiag
--per-slot, p3split, pqsum) that holds one number per slot: means over slot blocks and the least-squares slope over
the last 20 slots (per 10 slots, and as % of that window's mean). A list of S values starts at slot 0, one of S - 2
values at slot 2 (S = the run's slots). Lists of tuples or other lengths are skipped. Section headers are echoed.
usage: levels.py RUN FILE[,FILE...] [SUBSTRING ...]   (only series whose label or header contains a substring)"""
import ast, json, re, sys
import numpy as np

run, files, pats = sys.argv[1], sys.argv[2].split(","), sys.argv[3:]
S = json.load(open(f"runs/{run}/run.json"))["slots"]
blocks = [(2, 15), (16, 29), (30, 39), (40, S - 1)] if S >= 50 else [(2, 15), (16, S - 1)]
print(f"{run}: {S} slots; block means " + " | ".join(f"{a}-{b}" for a, b in blocks)
      + f" ; slope over slots {S - 20}-{S - 1} per 10 slots (% of window mean)")
for f in files:
    hdr, shown = "", None
    print(f"== {f}")
    for line in open(f):
        m = re.match(r"\s*(.*?)\s*(\[[^\[\]]*\])\s*$", line.rstrip())
        if not m:
            if line.strip() and "[" not in line:
                hdr = line.strip()[:90]
            continue
        if pats and not any(p in m.group(1) or p in hdr for p in pats):
            continue
        try:
            v = ast.literal_eval(m.group(2))
        except (ValueError, SyntaxError):
            continue
        s0 = {S: 0, S - 2: 2}.get(len(v))
        if s0 is None or not all(x is None or isinstance(x, (int, float)) for x in v):
            continue
        d = {s0 + k: x for k, x in enumerate(v) if x is not None}
        bm = [np.mean([d[s] for s in range(a, b + 1) if s in d]) if any(s in d for s in range(a, b + 1))
              else float("nan") for a, b in blocks]
        w = np.array([(s, d[s]) for s in range(S - 20, S) if s in d])
        k = np.polyfit(w[:, 0], w[:, 1], 1)[0] * 10 if len(w) >= 3 else float("nan")
        rel = 100 * k / abs(w[:, 1].mean()) if len(w) >= 3 and w[:, 1].mean() else float("nan")
        if hdr != shown:
            print(f" {hdr}")
            shown = hdr
        print(f"   {m.group(1)[:30]:30s} " + " | ".join(f"{b:9.4g}" for b in bm) + f" ; {k:+.3g} ({rel:+.1f} %)")
