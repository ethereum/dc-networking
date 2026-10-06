#!/usr/bin/env python3
"""check_frc.py -- independent cross-check of the free-running committee clock (orchestrating agent).

Schedules: Q17 grid fixed / + (index+round) / + Q18 slow rotation, free-running C=23, free-running + (index+round).
Prints vote gaps, committees per block, and seconds per height in the explicit-time model with
offline stake spread evenly over cohorts (a vote cast at t lands in the block at 12*ceil((t+8)/12);
the quorum block is visible 1 s after its slot start; instant switch). Stdlib only, deterministic, ~1 min.
Compare: results/clock.md X1, X3 and X2c (which uses random offline sets instead).
"""
import math, statistics as st
C = 23
def sched(name):
    # returns function unit -> cohort (or None if idle)
    if name == 'frc':
        return lambda u: u % C
    if name == 'q17_fixed':
        return lambda u: None if u % 24 == 23 else (u % 24)
    if name == 'q17_fran':
        def f(u):
            R, j = divmod(u, 24)
            return None if j == 23 else (j - R) % C
        return f
    if name == 'q17_q18':   # +1 every 8 rounds
        def f(u):
            R, j = divmod(u, 24)
            return None if j == 23 else (j - R // 8) % C
        return f
    if name == 'frc_fran':  # 23-unit rounds with +1/round on top
        def f(u):
            r, k = divmod(u, C)
            return (k - r) % C
        return f

def gaps(name, N=24*23*3):
    f = sched(name); last = {}; g = []
    for u in range(N):
        c = f(u)
        if c is None: continue
        if c in last: g.append(4*(u-last[c]))
        last[c] = u
    return min(g), st.mean(g), max(g)

def per_block(name, N=24*23*3):
    f = sched(name); cnt = {}
    for u in range(N):
        if f(u) is None: continue
        b = math.ceil((4*u+8)/12)
        cnt[b] = cnt.get(b,0)+1
    vals = list(cnt.values())[5:-5]
    return {k: vals.count(k) for k in sorted(set(vals))}

def heights(name, p, N=24*23*40, vis=1.0, burn=24*23*4):
    f = sched(name)
    need = 2/3
    w = p / C
    h = 0; last_vote_h = {}; tally = 0.0
    switch_visible = -1e9   # time from which voters see height h
    pending = {}  # block index -> list of (height named, weight)
    jt = []
    cur_known = 0
    known_at = [(-1e9, 0)]  # (time visible, height)
    def height_known(t):
        # latest height whose start is visible at t
        hh = 0
        for tv, hv in known_at[::-1]:
            if tv <= t: return hv
        return 0
    nb = 0
    for u in range(N):
        t = 4*u
        # process blocks with time <= t (block at 12b)
        while 12*nb <= t:
            for (hn, ww) in pending.pop(nb, []):
                if hn == h:
                    tally += ww
            if tally >= need - 1e-12:
                jt.append(12*nb); h += 1; tally = 0.0
                known_at.append((12*nb + vis, h))
                # votes already pending naming h-1 are wasted
            nb += 1
        c = f(u)
        if c is None: continue
        hk = height_known(t)
        if last_vote_h.get(c, -1) >= hk: continue
        last_vote_h[c] = hk
        b = math.ceil((t+8)/12)
        pending.setdefault(b, []).append((hk, w))
    d = [b - a for a, b in zip(jt, jt[1:]) if a >= 4*burn]
    return st.mean(d), sorted(d)[int(0.95*len(d))], max(d)

for name in ['q17_fixed','q17_fran','q17_q18','frc','frc_fran']:
    print(name, 'gaps(min,mean,max) s =', gaps(name), 'units/block', per_block(name))
for p in [1.0, 0.9, 0.8, 0.7, 0.67]:
    row = []
    for name in ['q17_fixed','q17_fran','q17_q18','frc','frc_fran']:
        m, p95, mx = heights(name, p)
        row.append(f"{name}:{m:.1f}/{p95}/{mx}")
    print('p=',p, ' | '.join(row))
