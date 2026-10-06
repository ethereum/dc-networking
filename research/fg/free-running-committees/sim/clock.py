#!/usr/bin/env python3
"""
clock.py -- clock lane of the free-running-committees study.

Evaluates the FREE-RUNNING COMMITTEE CLOCK (FRC): FG units of 4 s, three per 12 s
slot; unit u (global, since genesis) starts at t = 4u s; cohort k votes in every
unit with u = k (mod C); a round is C consecutive units (92 s at C = 23) and is
pure accounting. Contrast schedules a-f of the brief and the pick-your-seat rules
R0/R1/R2 (Yann's addition).

Python 3 standard library only, deterministic (every random draw comes from
random.Random seeded with a fixed string). Imports Q18's Lane-A simulator
(../../staggered-committees/sim/schedules.py) and never modifies it.

    python3 sim/clock.py all            # every table + results/clock.json (< 2 min)
    python3 sim/clock.py latency gaps   # a subset (names: sanity gaps latency drops
                                        # blocks fairness offsets order seats)

MODELS
------
* Constant-lag model = Q18's model (schedules.py:22-38): a voter at tick t knows
  heights justified at ticks <= t-L-1; a height is justified at the end of the
  tick at which 2/3 of stake has voted for it; instant switch. Ticks are 4 s.
  The Q17 grid has 24 ticks per 96 s round with tick 23 idle
  (schedules.py:403-415); FRC has C ticks per round and no idle tick.
* Explicit-time model (new here): a vote cast at unit start t lands in the block
  at 12*ceil((t+8)/12) s (Q17: published at t+4, landed by t+8, included by the
  first block at or after it, pipelined-units/README.md:57,64). A block counts
  every included vote for the state's current height, then justifies if the
  tally reaches 2/3 (justification after block processing, FF chat msg 1537).
  The quorum block is visible 1 s after its slot start: units starting before
  that vote the old height. Optionally a fraction of blocks is missed (votes
  roll to the next block).
* Equal stake, cohort = validator index mod C, n = 40*C validators, random
  offline sets drawn with Q18's offline_set (schedules.py:501-520), exactly as
  Q18 E1a, so the unit-model numbers reproduce Q18 (table X0).
* Because composition is fixed and offline validators never come back, every
  online member of a cohort has the same voting history; the simulators here
  therefore run at cohort level. They are checked tick-for-tick against Q18's
  per-validator simulate() (table X0).
"""
import json
import math
import os
import random
import sys
import time
from collections import Counter

sys.dont_write_bytecode = True     # never leave __pycache__ in the Q18 directory (read-only for this lane)
HERE = os.path.dirname(os.path.abspath(__file__))
Q18_SIM = os.path.normpath(os.path.join(HERE, "..", "..", "staggered-committees", "sim"))
sys.path.insert(0, Q18_SIM)
import schedules as S18  # noqa: E402  Q18 Lane A (schedules.py), imported read-only

RESULTS = os.path.normpath(os.path.join(HERE, "..", "results"))
T0 = time.time()

UNIT_S = 4                 # unit spacing (Q17)
SLOT_S = 12
EPOCH_S = 384
EPS = 0.001                # 0.1 pp fairness target (Q18 E10b)
PS = [1.0, 0.9, 0.8, 0.7, 0.67]
NSEEDS = 10                # offline sets per participation level (Q18 E1a used 1)
R_STEADY = 320             # rounds per run, first 20 discarded (Q18 E1a)
BURN = 20
NPER = 40                  # validators per cohort (Q18 E1a: n = 40*C)
V_MAIN = 1_000_000         # mainnet-scale validator count for byte/load numbers
SINGLE_DC_B = 200          # B per DC single vote (Q18 sizing.py:45, network.md:171)
AGG_PER_COMMITTEE = 16     # TARGET_AGGREGATORS_PER_COMMITTEE (Q18 README:294)
COMMITTEES_PER_UNIT = 64   # Q18 README:109
S_ETH = 36_000_000         # total stake, EIP-8061 (eip-8061.md:220)
CHURN = {                  # ETH/epoch at S = 36M (eip-8061.md:222-235)
    "Electra": {"exit": 256, "activation": 256, "consolidation": 293},
    "EIP-8061": {"exit": 1098, "activation": 256, "consolidation": 549},
}
EPOCHS_PER_DAY = 225

OUT = {"meta": {}, "schedules": {}, "seat_rules": {}, "checks": {}}


def r4(x):
    if isinstance(x, float):
        if math.isinf(x) or math.isnan(x):
            return None
        return round(x, 4)
    return x


def summ_s(D):
    """durations in seconds -> dict mean/p95/max (s)."""
    if not D:
        return {"mean_s": None, "p95_s": None, "max_s": None, "n": 0}
    return {"mean_s": r4(S18.mean(D)), "p95_s": r4(S18.pct(D, 0.95)), "max_s": r4(float(max(D))), "n": len(D)}


def fmt_s(d):
    if d["mean_s"] is None:
        return "n/a"
    return f"{d['mean_s']:.1f} / {d['p95_s']:.0f} / {d['max_s']:.0f}"


# ----------------------------------------------------------------------------
# schedules: a clock (Q17 grid or FRC) plus a position rule
# ----------------------------------------------------------------------------

def SH0(r):
    return 0


def SHR(r):
    return r


def SH8(r):
    return r // 8


SHIFT_DESC = {"0": "fixed order", "r": "(index + round) mod C, +1 seat per round",
              "r//8": "+1 seat every 8 rounds (Q18 recommendation)"}
SHIFT_FN = {"0": SH0, "r": SHR, "r//8": SH8}


class Sched2:
    """clock 'q17': 24 ticks per slot-aligned 96 s round, ticks 0..22 are seats, tick 23 idle
    (Q17 README:24,57-62; Q18 schedules.py:407-408). clock 'frc': C ticks per round, tick k =
    seat k, no idle tick; round r starts at 4*C*r s. Position rule: cohort c (= index mod C)
    sits at seat (c + shift(r)) mod C."""

    def __init__(self, key, name, clock, C, tag):
        self.key, self.name, self.clock, self.C, self.tag = key, name, clock, C, tag
        self.shift = SHIFT_FN[tag]
        if clock == "q17":
            self.T, self.utick = S18.unit_ticks(C, "q17")
        else:
            self.T, self.utick = C, list(range(C))
        self.round_s = UNIT_S * self.T
        self.tick_of = [None] * C
        for k, u in enumerate(self.utick):
            if u >= 0:
                self.tick_of[u] = k
        self.pos_period = {"0": 1, "r": C, "r//8": 8 * C}[tag]

    def seat(self, c, r):
        return (c + self.shift(r)) % self.C

    def vote_tick(self, c, r):
        return r * self.T + self.tick_of[self.seat(c, r)]

    def q18(self, n):
        return S18.Rotating(n, self.C, self.shift, self.name)


def make_schedules():
    return [
        Sched2("a", "Q17 grid, fixed order", "q17", 23, "0"),
        Sched2("b", "Q17 grid + (index + round) mod C", "q17", 23, "r"),
        Sched2("c", "Q17 grid + Q18 rec (+1 seat / 8 rounds)", "q17", 23, "r//8"),
        Sched2("d", "FRC C=23", "frc", 23, "0"),
        Sched2("e", "FRC C=23 + (index + round) mod C", "frc", 23, "r"),
        Sched2("f22", "FRC C=22", "frc", 22, "0"),
        Sched2("f24", "FRC C=24", "frc", 24, "0"),
        Sched2("f25", "FRC C=25", "frc", 25, "0"),
        Sched2("x23", "FRC C=23 + (+1 seat / 8 rounds) [extra]", "frc", 23, "r//8"),
        Sched2("x24", "FRC C=24 + (+1 seat / 8 rounds) [extra]", "frc", 24, "r//8"),
    ]


SCHEDS = make_schedules()
SK = {s.key: s for s in SCHEDS}


# ----------------------------------------------------------------------------
# cohort-level simulators
# ----------------------------------------------------------------------------

def sim_lag(sch, wev, S, L, R, stats=False):
    """Constant-lag model, cohort level. Replica of S18.simulate (schedules.py:418-489):
    identical justification ticks (checked in X0). wev = [(tick, per-cohort online stake), ...]."""
    T, ut, C, shift = sch.T, sch.utick, sch.C, sch.shift
    G = len(wev[0][1])
    last = [-1] * G
    ei, nev = 1, len(wev)
    w = wev[0][1]
    cur = acc = 0
    lastj = -10 ** 9
    q2 = 2 * S
    jt = []
    if stats:
        tim, sta, red, piv = [0] * G, [0] * G, [0] * G, [0] * G
    for r in range(R):
        sh = shift(r)
        base = r * T
        for k in range(T):
            u = ut[k]
            if u < 0:
                continue
            t = base + k
            while ei < nev and wev[ei][0] <= t:
                w = wev[ei][1]
                ei += 1
            c = (u - sh) % C
            wc = w[c]
            timely = False
            if wc:
                kn = cur if lastj <= t - L - 1 else cur - 1
                if last[c] < kn:
                    last[c] = kn
                    if kn == cur:
                        acc += wc
                        timely = True
                        if stats:
                            tim[c] += 1
                    elif stats:
                        sta[c] += 1
                elif stats:
                    red[c] += 1
            if 3 * acc >= q2:
                jt.append(t)
                lastj = t
                cur += 1
                acc = 0
                if stats and timely:
                    piv[c] += 1
    return jt, ((tim, sta, red, piv) if stats else None)


def sim_time(sch, wev, S, R, stats=False, miss=0.0, miss_seed="miss", see0=False):
    """Explicit-time model, cohort level. Global tick j = 4 s; blocks at ticks j = 0 mod 3.
    A unit at tick j delivers into the block at tick 3*ceil((j+2)/3) (= 12*ceil((t+8)/12) s).
    Visibility: a block justified at tick b is known to units at ticks > b (visible at +1 s, the
    +0 s unit has already signed; Q18 README:238 signs at unit start). see0=True is the sensitivity
    variant in which the +0 s unit waits for its slot's block (units at ticks >= b know it).
    Returns (justification block ticks, lags, stats); lag = number of ticks after the completing unit whose
    units still vote the old height (Lane B's L): block - completing tick, minus 1 under see0."""
    T, ut, C, shift = sch.T, sch.utick, sch.C, sch.shift
    G = len(wev[0][1])
    last = [-1] * G
    ei, nev = 1, len(wev)
    w = wev[0][1]
    cur = acc = known = 0
    q2 = 2 * S
    jt, lags = [], []
    pend = {}
    rngm = random.Random(miss_seed) if miss > 0 else None
    tim, sta, red, piv = ([0] * G, [0] * G, [0] * G, [0] * G) if stats else (None, None, None, None)

    def block(j):
        nonlocal cur, acc, known
        missed = rngm is not None and rngm.random() < miss
        batch = pend.pop(j, None)
        if batch is None:
            return
        if missed:
            pend[j + 3] = batch + pend.get(j + 3, [])
            return
        comp = None
        for (h, wc, c, jj) in batch:
            if h == cur:
                acc += wc
                if stats:
                    tim[c] += 1
                if comp is None and 3 * acc >= q2:
                    comp = (c, jj)
            elif stats:
                sta[c] += 1
        if comp is not None:
            jt.append(j)
            lags.append(j - comp[1] - (1 if see0 else 0))      # ticks after the completing unit voting the old height
            cur += 1
            acc = 0
            if stats:
                piv[comp[0]] += 1
            known = cur

    for j in range(R * T):
        if see0 and j % 3 == 0:
            block(j)
        r, k = divmod(j, T)
        u = ut[k]
        if u >= 0:
            while ei < nev and wev[ei][0] <= j:
                w = wev[ei][1]
                ei += 1
            c = (u - shift(r)) % C
            wc = w[c]
            if wc:
                if last[c] < known:
                    last[c] = known
                    bt = 3 * ((j + 4) // 3)
                    lst = pend.get(bt)
                    if lst is None:
                        pend[bt] = [(known, wc, c, j)]
                    else:
                        lst.append((known, wc, c, j))
                elif stats:
                    red[c] += 1
        if not see0 and j % 3 == 0:
            block(j)
    return jt, lags, ((tim, sta, red, piv) if stats else None)


def durations(jt, from_tick):
    return [jt[i] - jt[i - 1] for i in range(1, len(jt)) if jt[i - 1] >= from_tick]


def cohort_w(off, C):
    w = [0] * C
    for v, o in enumerate(off):
        if not o:
            w[v % C] += 1
    return w


_OFF_CACHE = {}


def offline_w(C, p, seed):
    key = (C, p, seed)
    if key not in _OFF_CACHE:
        n = NPER * C
        if p >= 1.0:
            _OFF_CACHE[key] = [NPER] * C
        else:
            off = S18.offline_set([1] * n, p, random.Random(seed))
            _OFF_CACHE[key] = cohort_w(off, C)
    return _OFF_CACHE[key]


def run_model(sch, model, w, S, R, L=3, miss=0.0, miss_seed="m"):
    if model == "lag":
        jt, _ = sim_lag(sch, [(0, w)], S, L, R)
        return jt, None
    jt, lags, _ = sim_time(sch, [(0, w)], S, R, miss=miss, miss_seed=miss_seed, see0=(model == "time0"))
    return jt, lags


# ----------------------------------------------------------------------------
# X0  sanity: reproduce Q18 and validate the cohort-level simulator
# ----------------------------------------------------------------------------

def x0_sanity():
    C, n = 23, 920
    stake = [1] * n
    fixed = S18.Rotating(n, C, SH0, "fixed v mod C")
    rows, ok_all = [], True
    want = {(1.0, 0): 0.696, (1.0, 3): 0.826, (0.67, 3): 1.130}
    repro = {}
    for (p, L), q in want.items():
        D = S18.steady(fixed, stake, L, R_STEADY, p, seed=f"e1-{p}")
        m18 = S18.mean(D)
        # same offline set through the cohort-level simulator on the FRC clock
        if p >= 1:
            w = [NPER] * C
        else:
            w = cohort_w(S18.offline_set(stake, p, random.Random(f"steady-e1-{p}")), C)
        jt, _ = sim_lag(SK["d"], [(0, w)], n, L, R_STEADY)
        mine = S18.mean([d / C for d in durations(jt, BURN * C)])
        ok = abs(m18 - q) < 0.0005 and abs(mine - m18) < 1e-12
        ok_all &= ok
        repro[f"p={p},L={L}"] = {"q18_published": q, "q18_rerun": r4(m18), "clock_py": r4(mine)}
        rows.append([p, L, f"{q:.3f}", f"{m18:.3f}", f"{mine:.3f}", f"{m18 * 92:.1f} s", "yes" if ok else "NO"])
    S18.table("X0a", "sanity: Q18 E1a fixed order in the unit model = FRC C=23 in the constant-lag model",
              ["p", "L", "Q18 published (README:259)", "Q18 schedules.py re-run", "clock.py cohort sim",
               "= seconds/height under FRC (x 92 s)", "match"], rows,
              note="Same n=920, R=320, burn 20, offline seed 'steady-e1-{p}' as Q18 E1a.")
    # tick-for-tick validation against S18.simulate on both clocks, with and without a drop event
    checks, ok_n = 0, 0
    for key in ("a", "b", "c", "d", "e", "x23"):
        sch = SK[key]
        q = sch.q18(n)
        T, ut = (sch.T, sch.utick)
        for p in (1.0, 0.67):
            flags = bytearray([1] * n) if p >= 1 else S18.flags_from_off(
                S18.offline_set(stake, p, random.Random(f"val-{key}-{p}")))
            w = [sum(flags[v] for v in range(c, n, C)) for c in range(C)]
            for L in (0, 3):
                jq, _, _ = S18.simulate(q, stake, L, 60, [(0, flags)], T=T, utick=ut)
                jm, _ = sim_lag(sch, [(0, w)], n, L, 60)
                checks += 1
                ok_n += jq == jm
        # drop event
        rng = random.Random(f"valdrop-{key}")
        td = 7 * T + rng.randrange(T)
        off = S18.offline_set(stake, 0.67, rng)
        fl = S18.flags_from_off(off)
        jq, _, _ = S18.simulate(q, stake, 3, 20, [(0, bytearray([1] * n)), (td, fl)], T=T, utick=ut)
        jm, _ = sim_lag(sch, [(0, [NPER] * C), (td, cohort_w(off, C))], n, 3, 20)
        checks += 1
        ok_n += jq == jm
    print(f"\nX0b: cohort-level sim_lag vs Q18 per-validator simulate(): {ok_n}/{checks} runs with identical "
          f"justification ticks (Q17 grid and FRC clocks, p in {{1, .67}}, L in {{0, 3}}, plus a drop event)")
    ok_all &= ok_n == checks
    # explicit-time lag by completing-unit offset (Lane B: L = 3/2/4 for +0/+4/+8), over every schedule and p
    lagmap = {}
    for see0, want_l in ((False, {0: 3, 1: 2, 2: 4}), (True, {0: 2, 1: 1, 2: 3})):
        by_off = {0: set(), 1: set(), 2: set()}
        for sch in SCHEDS:
            for p in PS:
                w = offline_w(sch.C, p, "p1" if p >= 1 else f"clk-steady-{p}-0")
                jt, lags, _ = sim_time(sch, [(0, w)], NPER * sch.C, 120, see0=see0)
                for b, lg in zip(jt, lags):
                    by_off[(b - lg - (1 if see0 else 0)) % 3].add(lg)
        m = {o: sorted(v) for o, v in by_off.items()}
        lag_ok = all(m[o] == [want_l[o]] for o in m)
        ok_all &= lag_ok
        lagmap["see0" if see0 else "default"] = {"+0": m[0], "+4": m[1], "+8": m[2]}
        print(f"X0c{'2' if see0 else '1'}: explicit-time model{' (+0 s unit sees its slot block)' if see0 else ''}, "
              f"lag (ticks after the completing unit that still vote the old height) by the completing unit's "
              f"offset, all schedules and p: +0 s -> {m[0]}, +4 s -> {m[1]}, +8 s -> {m[2]} (expected "
              f"{want_l[0]} / {want_l[1]} / {want_l[2]}{'; Lane B' if not see0 else ''}) -> "
              f"{'match' if lag_ok else 'MISMATCH'}")
    OUT["checks"]["sanity"] = {"q18_reproduction": repro, "validation_runs_identical": f"{ok_n}/{checks}",
                               "explicit_lag_by_offset": lagmap, "all_ok": ok_all}
    if not ok_all:
        print("!! SANITY FAILED")
    return ok_all


# ----------------------------------------------------------------------------
# X1  vote gaps (metric 1)
# ----------------------------------------------------------------------------

def threshold_range(sch, see0):
    """Exact-threshold height duration (s) in the explicit-time model, min and max over block phases."""
    lo, hi = 10 ** 9, 0
    P = sch.pos_period * 3 // math.gcd(sch.pos_period, 3) * sch.T      # ticks; covers every phase
    for b in range(0, P + 3, 3):
        f = b if see0 else b + 1
        seen = set()
        t = f
        while len(seen) < sch.C:
            r, k = divmod(t, sch.T)
            u = sch.utick[k]
            if u >= 0:
                seen.add((u - sch.shift(r)) % sch.C)
            t += 1
        last = t - 1
        dur = 3 * ((last + 4) // 3) - b
        lo, hi = min(lo, dur), max(hi, dur)
    return [lo * UNIT_S, hi * UNIT_S]


def x1_gaps():
    R = 1104                      # multiple of 3, 23, 24, 8*23 periods
    rows = []
    for sch in SCHEDS:
        g = Counter()
        short = 0
        for c in range(sch.C):
            prev = sch.vote_tick(c, 0)
            for r in range(1, R):
                t = sch.vote_tick(c, r)
                g[t - prev] += 1
                if t - prev <= 2:
                    short += 1
                prev = t
        tot = sum(g.values())
        gs = sorted(g)
        mn, mx = gs[0], gs[-1]
        mean_t = sum(k * v for k, v in g.items()) / tot
        hist = {str(k * UNIT_S): r4(v / tot) for k, v in sorted(g.items())}
        G18 = None
        if sch.C == 23:
            G18, _ = S18.gap_stats(sch.q18(NPER * 23), 200, [1] * (NPER * 23), 0.0, T=sch.T, utick=sch.utick)
        bq = threshold_range(sch, see0=False)
        bq0 = threshold_range(sch, see0=True)
        d = {"min_s": mn * UNIT_S, "mean_s": r4(mean_t * UNIT_S), "max_s": mx * UNIT_S,
             "G_ticks": mx, "G_rounds": r4(mx / sch.T), "hist_s": hist,
             "overlap_votes_per_round": r4(short / (R - 1)),
             "gap_lemma_bound_L3_s": (3 + mx) * UNIT_S,
             "threshold_explicit_s_min_max": bq, "threshold_explicit_see0_s_min_max": bq0}
        OUT["schedules"].setdefault(sch.key, {})["gaps"] = d
        rows.append([sch.key, sch.name, sch.round_s, mn * UNIT_S, f"{mean_t * UNIT_S:.2f}", mx * UNIT_S,
                     f"{mx} ({'C' if mx == sch.C else 'C+%d' % (mx - sch.C)})" + (f" [Q18 gap_stats: {G18}]" if G18 is not None else ""),
                     ", ".join(f"{k * UNIT_S}s:{100 * v / tot:.1f}%" for k, v in sorted(g.items())),
                     f"{short / (R - 1):.3f}", (3 + mx) * UNIT_S, "%d-%d" % tuple(bq), "%d-%d" % tuple(bq0)])
    S18.table("X1", "per-validator vote gaps (equal stake, cohort = index mod C), over 1104 rounds",
              ["key", "schedule", "round (s)", "min gap (s)", "mean (s)", "max (s)", "G (ticks)",
               "gap distribution", "votes <= 8 s after the previous one, per round (cohorts)",
               "gap-lemma bound L+G, L=3 (s)", "explicit-time height at exact threshold, min-max over block phases (s)",
               "same, +0 s unit sees its block (s)"], rows,
              note="Ticks are 4 s; the Q17 idle tick counts as time. 'Votes <= 8 s after the previous' are the wrap "
                   "cohort's back-to-back votes (Mikhail's overlap, FF chat msgs 1539/1542). Exact-threshold height in the "
                   "explicit-time model (every online cohort needed, honest includer): from a quorum block at tick b the "
                   "first fresh unit is b+1 (b if the +0 s unit sees the block); the height ends at the block that carries "
                   "the last cohort to vote after it, 3*ceil((t_last+2)/3). Range over every block phase b.")


# ----------------------------------------------------------------------------
# X2  seconds per height (metric 2)
# ----------------------------------------------------------------------------

def steady_ticks(sch, model, p, L=3, miss=0.0):
    C = sch.C
    S = NPER * C
    seeds = ["p1"] if p >= 1 else [f"clk-steady-{p}-{i}" for i in range(NSEEDS)]
    D, lags = [], []
    for sd in seeds:
        w = offline_w(C, p, sd)
        jt, lg = run_model(sch, model, w, S, R_STEADY, L=L, miss=miss, miss_seed=f"miss-{sd}")
        D += durations(jt, BURN * sch.T)
        if lg:
            lags += [x for b, x in zip(jt, lg) if b >= BURN * sch.T]
    return D, lags


def x2_latency():
    rows_by_model = {"lag0": [], "lag3": [], "time": [], "time0": []}
    lagrows = []
    for sch in SCHEDS:
        lat = {}
        for mname, model, L in (("lag0", "lag", 0), ("lag3", "lag", 3), ("time", "time", None),
                                ("time0", "time0", None)):
            lat[mname] = {}
            cells = []
            for p in PS:
                D, lags = steady_ticks(sch, model, p, L=L if L is not None else 3)
                Ds = [d * UNIT_S for d in D]
                s = summ_s(Ds)
                s["mean_rounds"] = r4(S18.mean(D) / sch.T)
                if model in ("time", "time0"):
                    lc = Counter(lags)
                    s["lag_dist"] = {str(k): r4(v / len(lags)) for k, v in sorted(lc.items())}
                    s["mean_lag_ticks"] = r4(S18.mean(lags))
                lat[mname][str(p)] = s
                cells.append(f"{fmt_s(s)} ({s['mean_rounds']:.3f} r)")
            rows_by_model[mname].append([sch.key, sch.name, sch.round_s] + cells)
        # missed-block sensitivity (time model, 4% of blocks missed)
        lat["time_miss4"] = {}
        for p in (1.0, 0.67):
            D, _ = steady_ticks(sch, "time", p, miss=0.04)
            s = summ_s([d * UNIT_S for d in D])
            s["mean_rounds"] = r4(S18.mean(D) / sch.T)
            lat["time_miss4"][str(p)] = s
        OUT["schedules"].setdefault(sch.key, {})["latency"] = lat
        lagrows.append([sch.key, sch.name] + [
            f"{lat['time'][str(p)]['mean_lag_ticks']:.2f} " + "{" + ", ".join(
                f"{k}:{100 * v:.0f}%" for k, v in lat['time'][str(p)]['lag_dist'].items()) + "}" for p in (1.0, 0.8, 0.67)]
            + [fmt_s(lat["time_miss4"]["1.0"]), fmt_s(lat["time_miss4"]["0.67"])])
    hdr = ["key", "schedule", "round (s)"] + [f"p={p}" for p in PS]
    note = (f"Seconds per height mean / p95 / max (in parentheses: mean in rounds of that schedule's own length). "
            f"n = 40*C equal-stake validators, {R_STEADY} rounds, first {BURN} discarded; p < 1: {NSEEDS} offline sets "
            f"per p, identical across schedules with the same C.")
    S18.table("X2a", "steady state, constant-lag model L=0 (Q18 unit/tick model)", hdr, rows_by_model["lag0"], note=note)
    S18.table("X2b", "steady state, constant-lag model L=3 (Q18's headline lag)", hdr, rows_by_model["lag3"], note=note)
    S18.table("X2c", "steady state, EXPLICIT-TIME model (vote at t lands in block 12*ceil((t+8)/12); quorum block "
                     "visible at +1 s)", hdr, rows_by_model["time"], note=note)
    S18.table("X2c2", "SENSITIVITY, explicit-time model in which the +0 s unit sees its slot's block before signing "
                      "(lag 2/1/3 instead of 3/2/4)", hdr, rows_by_model["time0"], note=note)
    S18.table("X2d", "explicit-time model: realized lag (ticks from completing unit to quorum block) and 4%-missed-block "
                     "sensitivity",
              ["key", "schedule", "mean lag {dist} p=1", "p=.8", "p=.67", "4% missed blocks: s/height p=1",
               "4% missed: p=.67"], lagrows,
              note="Lag 2/3/4 = completing unit at +4/+0/+8 s of its slot (Lane B's L = 2/3/4). Missed blocks: each "
                   "block independently missed with prob. 0.04 (Lane B's ~4% today); its votes roll to the next block.")


def x2_drops():
    trials = 60
    rows = []
    C, n = 23, 920
    stake = [1] * n
    for key in ("a", "b", "c", "d", "e"):
        sch = SK[key]
        T = sch.T
        res = {}
        cells = []
        for model in ("lag", "time", "time0"):
            first3, win8 = [], []
            for trial in range(trials):
                rt = random.Random(f"clk-drop-t-{trial}")
                td = int(math.ceil(rt.uniform(600.0, 900.0) / UNIT_S))     # same instant (s) for every schedule
                off = S18.offline_set(stake, 0.67, random.Random(f"clk-drop-off-{trial}"))
                wev = [(0, [NPER] * C), (td, cohort_w(off, C))]
                R = td // T + 12
                if model == "lag":
                    jt, _ = sim_lag(sch, wev, n, 3, R)
                else:
                    jt, _, _ = sim_time(sch, wev, n, R, see0=(model == "time0"))
                Ds = [(jt[i] - jt[i - 1]) * UNIT_S for i in range(1, len(jt)) if td < jt[i] <= td + 192]
                first3.append(max(Ds[:3]))
                win8.append(max(Ds))
            res["lag3" if model == "lag" else model] = {
                "first3_median_s": r4(S18.pct(first3, 0.5)), "first3_p95_s": r4(S18.pct(first3, 0.95)),
                "first3_max_s": r4(float(max(first3))), "max_768s_window_s": r4(float(max(win8)))}
            cells.append(f"{S18.pct(first3, .5):.0f} / {S18.pct(first3, .95):.0f} / {max(first3):.0f} [{max(win8):.0f}]")
        OUT["schedules"].setdefault(key, {})["drop_to_67"] = res
        rows.append([key, sch.name] + cells)
    S18.table("X2e", f"sudden drop 100% -> 67% at a random instant (600-900 s): worst of the first 3 heights after the "
                     f"drop, median / p95 / max over {trials} trials [max over the 768 s after the drop], seconds",
              ["key", "schedule", "constant lag L=3", "explicit-time", "explicit-time, +0 s unit sees its block"], rows,
              note="Paired: same drop instant (s) and same offline set for every schedule (all C = 23, n = 920).")


# ----------------------------------------------------------------------------
# X3  units landing per block (metric 3)
# ----------------------------------------------------------------------------

def x3_blocks():
    rows = []
    clocks = [("Q17 grid (C=23)", "q17", 23)] + [(f"FRC C={C}", "frc", C) for C in (22, 23, 24, 25)]
    for label, clock, C in clocks:
        if clock == "q17":
            T, ut = S18.unit_ticks(23, "q17")
        else:
            T, ut = C, list(range(C))
        N = 3 * 8 * 23 * 24 * 25        # ticks; multiple of every period here
        on, rounds_on, late_u, rounds_late = Counter(), {}, Counter(), {}
        for j in range(N):
            if ut[j % T] < 0:
                continue
            r = j // T
            b = 3 * ((j + 4) // 3)
            on[b] += 1
            rounds_on.setdefault(b, set()).add(r)
            late_u[b] += 1
            rounds_late.setdefault(b, set()).add(r)
            if j % 3 == 1:                       # +4 s unit: late superset lands one block later
                late_u[b + 3] += 1
                rounds_late.setdefault(b + 3, set()).add(r)
        blocks = range(30, N - 30, 3)
        nb = len(blocks)
        d_on = Counter(on[b] for b in blocks)
        d_late = Counter(late_u[b] for b in blocks)
        d_r_on = Counter(len(rounds_on.get(b, ())) for b in blocks)
        d_r_late = Counter(len(rounds_late.get(b, ())) for b in blocks)
        f = lambda dd: {str(k): r4(v / nb) for k, v in sorted(dd.items())}
        rec = {"on_time_units": f(d_on), "with_late_superset": f(d_late), "rounds_on_time": f(d_r_on),
               "rounds_with_late": f(d_r_late), "mean_on_time_units": r4(sum(k * v for k, v in d_on.items()) / nb)}
        OUT.setdefault("blocks", {})[label] = rec
        fm = lambda dd: ", ".join(f"{k}: {100 * v / nb:.1f}%" for k, v in sorted(dd.items()))
        rows.append([label, fm(d_on), f"{rec['mean_on_time_units']:.3f}", fm(d_late), fm(d_r_on), fm(d_r_late)])
    S18.table("X3", "FG units landing per block (on-time aggregates; with the late +4 s superset, Q18 README:396-398)",
              ["clock", "on-time units per block", "mean", "with late supersets", "distinct rounds per block (on-time)",
               "distinct rounds (with late)"], rows,
              note="On-time: a vote at t lands in the block at 12*ceil((t+8)/12). Late aggregators publish at cut + 4 s "
                   "(Q18 README:240); only the +4 s unit's late superset misses its on-time block. Two rounds in one "
                   "block means two AttestationData values (the round is in the vote), i.e. no single per-block merge.")


# ----------------------------------------------------------------------------
# X4  in-slot exposure and fairness horizon (metric 4)
# ----------------------------------------------------------------------------

def miss_seq(sch, c, P, pen):
    out = []
    for r in range(P):
        j = sch.vote_tick(c, r)
        s = sch.seat(c, r)
        x = S18.MISS_BASE[j % 3]
        if pen:
            if s == 0:
                x += S18.MISS_UNIT0
            if s == sch.C - 1:
                x += S18.MISS_LAST
        out.append(x)
    return out


def fairness(sch, pen):
    P = sch.pos_period * 3 // math.gcd(sch.pos_period, 3)
    seqs = [miss_seq(sch, c, P, pen) for c in range(sch.C)]
    means = [sum(s) / P for s in seqs]
    mbar = sum(means) / sch.C
    bias = max(abs(m - mbar) for m in means)
    res = {"period_rounds": P, "mean_miss": r4(mbar), "permanent_bias_pp": r4(100 * bias)}
    if bias > 1e-12:
        res["eps_horizon_rounds"] = None
        res["eps_horizon_h"] = None
    else:
        E = max(S18.periodic_excursion([x - mbar for x in s]) for s in seqs)
        res["eps_horizon_rounds"] = r4(E / EPS)
        res["eps_horizon_h"] = r4(E / EPS * sch.round_s / 3600)
    # exact worst deviation at fixed horizons (any start round)
    for label, secs in (("1h", 3600), ("1d", 86400)):
        H0 = int(round(secs / sch.round_s))
        worst = 0.0
        for s in seqs:
            pre = [0.0]
            for x in s:
                pre.append(pre[-1] + x)
            tot = pre[-1]

            def F(x):
                q, m = divmod(x, P)
                return q * tot + pre[m]
            for H in (H0, H0 + 1, H0 + 2):          # every residue of the 3-round in-slot cycle
                for r0 in range(P):
                    worst = max(worst, abs((F(r0 + H) - F(r0)) / H - mbar))
        res[f"worst_dev_{label}_pp"] = r4(100 * worst)
    return res


def inslot_exposure(sch):
    """worst share of a cohort's votes at the +0 s offset over 1 h windows (target 1/3)."""
    P = sch.pos_period * 3 // math.gcd(sch.pos_period, 3)
    H0 = int(round(3600 / sch.round_s))
    lo, hi = 1.0, 0.0
    for c in range(sch.C):
        ind = [1.0 if sch.vote_tick(c, r) % 3 == 0 else 0.0 for r in range(P)]
        pre = [0.0]
        for x in ind:
            pre.append(pre[-1] + x)
        tot = pre[-1]
        for H in (H0, H0 + 1, H0 + 2):
            for r0 in range(P):
                q1, m1 = divmod(r0 + H, P)
                q0, m0 = divmod(r0, P)
                v = (q1 * tot + pre[m1] - q0 * tot - pre[m0]) / H
                lo, hi = min(lo, v), max(hi, v)
    return lo, hi


def x4_fairness():
    rows = []
    for sch in SCHEDS:
        a = fairness(sch, pen=False)
        b = fairness(sch, pen=True)
        lo, hi = inslot_exposure(sch)
        OUT["schedules"].setdefault(sch.key, {})["fairness"] = {
            "in_slot_only": a, "with_round_boundary_penalties": b,
            "plus0_share_1h_min": r4(lo), "plus0_share_1h_max": r4(hi)}

        def cell(x):
            if x["eps_horizon_h"] is None:
                return f"never (bias {x['permanent_bias_pp']:.2f} pp)"
            return f"{x['eps_horizon_h']:.2f} h ({x['eps_horizon_rounds']:.0f} r)"
        rows.append([sch.key, sch.name, f"{100 * lo:.1f}-{100 * hi:.1f}%", cell(a),
                     f"{a['worst_dev_1h_pp']:.3f} / {a['worst_dev_1d_pp']:.4f}", cell(b),
                     f"{b['worst_dev_1h_pp']:.3f} / {b['worst_dev_1d_pp']:.4f}"])
    S18.table("X4", "in-slot exposure and time to eps-fair (eps = 0.1 pp) under Q18's ASSUMED miss rates",
              ["key", "schedule", "+0 s share of a cohort's votes over any 1 h (min-max)",
               "eps-fair, MISS_BASE only", "worst dev. 1 h / 1 day (pp)",
               "eps-fair, + MISS_UNIT0 (seat 0) + MISS_LAST (seat C-1)", "worst dev. 1 h / 1 day (pp)"], rows,
              note="MISS_BASE: +0/+4/+8 s units 2.0/1.0/0.5%; MISS_UNIT0 +1.0% on the round's first seat; MISS_LAST +0.5% "
                   "on its last seat (schedules.py:1463-1467, placeholders). Horizon = excursion / eps, as Q18 E10b. "
                   "Q18 reference: Q17 + rec with penalties = 5.8 h; fixed seat = 1.74 pp forever. 1 h / 1 day windows are "
                   "taken at lengths H, H+1, H+2 rounds so that the 3-round in-slot cycle cannot hide a deviation.")


# ----------------------------------------------------------------------------
# X5  round-start offsets, alignment, traffic (metric 5)
# ----------------------------------------------------------------------------

def x5_offsets():
    rows = []
    rec = {}
    for label, C, step, slot in (("Q17 grid (8-slot round)", 23, None, 12), ("FRC C=22", 22, 4, 12),
                                 ("FRC C=23", 23, 4, 12), ("FRC C=24", 24, 4, 12), ("FRC C=25", 25, 4, 12),
                                 ("10 s slots, FRC C=15 (2 units/slot)", 15, 5, 10),
                                 ("10 s slots, FRC C=16 (2 units/slot)", 16, 5, 10)):
        if step is None:
            rl = 96
        else:
            rl = step * C
        m = slot // (step or 4)
        offs = [(rl * r) % slot for r in range(6)]
        cyc = []
        for o in offs:
            if o in cyc:
                break
            cyc.append(o)
        mid = sum(1 for r in range(len(cyc) * 10) if (rl * r) % slot) / (len(cyc) * 10)
        ep_align = next(r for r in range(1, 10 ** 5) if (rl * r) % (32 * slot) == 0)
        ep_len = 32 * slot
        straddle = sum(1 for r in range(ep_align)
                       if (rl * r) // ep_len != (rl * (r + 1) - 1) // ep_len) / ep_align
        auto = (math.gcd(C, m) == 1) if step else False
        vote_rate = 96 / rl if slot == 12 else None
        rows.append([label, rl, " -> ".join(f"+{o}" for o in cyc), f"{100 * mid:.1f}%", ep_align, f"{100 * straddle:.1f}%",
                     "yes, period %d rounds" % m if auto else "no",
                     f"{vote_rate:.4f}" if vote_rate else "n/a", f"{23 / C:.3f}" if slot == 12 else "n/a"])
        rec[label] = {"round_s": rl, "round_start_offset_cycle_s": cyc, "mid_slot_fraction": r4(mid),
                      "rounds_until_round_and_epoch_boundaries_coincide": ep_align,
                      "rounds_straddling_an_epoch_boundary": r4(straddle),
                      "automatic_in_slot_rotation": auto, "fg_vote_rate_vs_q17": r4(vote_rate) if vote_rate else None,
                      "per_unit_load_vs_c23": r4(23 / C) if slot == 12 else None}
    OUT["offsets"] = rec
    S18.table("X5", "round-start offsets, alignment and FG traffic",
              ["clock", "round (s)", "round-start in-slot offset cycle (s)", "round boundaries mid-slot",
               "rounds until a round boundary is also an epoch boundary", "rounds containing an epoch boundary",
               "automatic in-slot rotation (gcd(C, units/slot) = 1)",
               "FG votes per second vs Q17", "per-unit load vs C=23"], rows,
              note="FRC round r starts at 4*C*r s. Q17 rounds are slot- and epoch-aligned (4 per epoch). 10 s slots: 2 units "
                   "per slot at 5 s spacing (Q18 open issue 8), so the in-slot rotation needs C odd.")


# ----------------------------------------------------------------------------
# X6  relative-order effects (Q18 E7) under FRC
# ----------------------------------------------------------------------------

def x6_order():
    """Q18 E7 under FRC: per-cohort stale shares; p=.8 over Q18's seed plus 9 more offline sets."""
    R = 690
    C, n = 23, 920
    rows = []
    seeds08 = ["e7-0.8"] + [f"clk-e7-0.8-{i}" for i in range(9)]
    for key in ("a", "c", "d", "e", "x23"):
        sch = SK[key]
        for model in ("lag", "time"):
            cells = []
            rec = {}
            for p, seeds in ((1.0, [None]), (0.8, seeds08)):
                mx_list, lock_list, first = [], [], None
                for sd in seeds:
                    w = [NPER] * C if sd is None else cohort_w(S18.offline_set([1] * n, p, random.Random(sd)), C)
                    if model == "lag":
                        jt, st = sim_lag(sch, [(0, w)], n, 3, R, stats=True)
                    else:
                        jt, _, st = sim_time(sch, [(0, w)], n, R, stats=True)
                    tim, sta, red, piv = st
                    on = [c for c in range(C) if w[c]]
                    stale = [sta[c] / (tim[c] + sta[c] + red[c]) for c in on]
                    D = durations(jt, BURN * sch.T)
                    lock = sum(1 for d in D if d == sch.T) / len(D)
                    mx_list.append(max(stale))
                    lock_list.append(lock)
                    if first is None:
                        first = (min(stale), S18.mean(stale), max(stale), lock)
                rec[f"p={p}"] = {"stale_min_first_seed": r4(first[0]), "stale_mean_first_seed": r4(first[1]),
                                 "stale_max_first_seed": r4(first[2]), "heights_exactly_one_round_first_seed": r4(first[3]),
                                 "max_stale_over_seeds_median": r4(S18.pct(mx_list, 0.5)),
                                 "max_stale_over_seeds_max": r4(max(mx_list)),
                                 "heights_exactly_one_round_median": r4(S18.pct(lock_list, 0.5)), "seeds": len(seeds)}
                cells.append(f"{100 * first[0]:.1f} / {100 * first[1]:.1f} / {100 * first[2]:.1f}% ({100 * first[3]:.0f}%)")
                if p < 1:
                    cells.append(f"{100 * S18.pct(mx_list, 0.5):.1f} / {100 * max(mx_list):.1f}% "
                                 f"({100 * S18.pct(lock_list, 0.5):.0f}%)")
            OUT["schedules"].setdefault(key, {}).setdefault("order_effects", {})[
                "lag3" if model == "lag" else "time"] = rec
            rows.append([key, sch.name, "L=3" if model == "lag" else "explicit"] + cells)
    S18.table("X6", "relative-order effects (Q18 E7) over 690 rounds: share of a cohort's votes that are stale",
              ["key", "schedule", "model", "p=1: min / mean / max (heights of exactly 1 round)",
               "p=.8, Q18 seed e7-0.8: min / mean / max (exactly 1 round)",
               "p=.8, 10 offline sets: largest cohort stale share, median / max (median exactly-1-round share)"], rows,
              note="Stale = vote for a height already justified when the vote is counted (credited as previous target, "
                   "mk :124-128). n = 920. In the explicit-time model durations are multiples of 3 ticks, so an FRC "
                   "height can never last exactly one 23-tick round.")


# ----------------------------------------------------------------------------
# P  pick-your-seat (Yann): R0 / R1 / R2
# ----------------------------------------------------------------------------

def zipf_sizes(total=V_MAIN, M=20000):
    """Operator sizes (validators), Zipf(1) over M operators like Q18 E8 (schedules.py:1104-1117)."""
    H = sum(1.0 / i for i in range(1, M + 1))
    s = [max(1, int(round(total / (H * i)))) for i in range(1, M + 1)]
    return s


def loads_stripe(V, C):
    return [V // C + (1 if k < V % C else 0) for k in range(C)]


def loads_random(V, C, seed):
    rng = random.Random(seed)
    L = [0] * C
    for _ in range(V):
        L[rng.randrange(C)] += 1
    return L


def loads_ops_random(sizes, C, seed):
    rng = random.Random(seed)
    L = [0] * C
    for s in sizes:
        L[rng.randrange(C)] += s
    return L


def loads_ops_greedy(sizes, C, cap=None):
    """Largest operator first into the least-loaded seat; with a cap, split an operator over seats."""
    L = [0] * C
    for s in sorted(sizes, reverse=True):
        rem = s
        while rem > 0:
            k = min(range(C), key=lambda i: (L[i], i))
            room = rem if cap is None else min(rem, cap - L[k])
            if room <= 0:
                raise RuntimeError("cap too small")
            L[k] += room
            rem -= room
    return L


def seat_latency(loads, p, model, R=R_STEADY):
    """FRC C=len(loads), fixed seats, per-seat online stake = round(p * load)."""
    C = len(loads)
    sch = Sched2("tmp", "FRC", "frc", C, "0")
    S = sum(loads)
    w = [int(round(p * x)) for x in loads]
    if 3 * sum(w) < 2 * S:
        return None
    jt, _ = run_model(sch, model, w, S, R, L=3)
    D = durations(jt, BURN * C)
    return summ_s([d * UNIT_S for d in D])


def p_a_loads():
    C = 23
    V = V_MAIN
    sizes = zipf_sizes(V)
    Vz = sum(sizes)
    cfgs = []
    cfgs.append(("R0 stripe (index mod C)", "R0", loads_stripe(V, C)))
    cfgs.append(("R0 era hash / R1 uniform random choice", "R0/R1", loads_random(V, C, "pys-uniform")))
    cfgs.append(("R1 operators co-locate, random seat (Zipf, 20k ops)", "R1", loads_ops_random(sizes, C, "pys-ops")))
    cfgs.append(("R1 operators co-locate, least-loaded seat", "R1", loads_ops_greedy(sizes, C)))
    herd = int(0.30 * V)
    L = loads_stripe(V - herd, C)
    L[0] += herd
    cfgs.append(("R1 30% of stake herds to one default seat", "R1", L))
    for beta in (0.10, 1 / 3):
        L = loads_stripe(V - int(beta * V), C)
        L[0] += int(beta * V)
        cfgs.append((f"R1 adversary beta={beta:.2f} piles into one seat", "R1", L))
    for kappa in (1.0, 1.05, 1.1):
        cap = int(math.ceil(kappa * Vz / C))
        cfgs.append((f"R2 kappa={kappa:.2f}: operators co-locate greedily under the cap", f"R2 k={kappa}",
                     loads_ops_greedy(sizes, C, cap=cap)))
    rows = []
    rec = {}
    for name, rule, Ls in cfgs:
        mean_l = sum(Ls) / C
        mx = max(Ls) / mean_l
        top_mb = max(Ls) * SINGLE_DC_B / 1e6
        cells = []
        r = {"max_over_mean": r4(mx), "max_unit_MB": r4(top_mb), "rule": rule}
        for p in (1.0, 0.67):
            for model in ("time", "lag"):
                s = seat_latency(Ls, p, model)
                r[f"p={p},{'time' if model == 'time' else 'lag3'}"] = s
                cells.append(fmt_s(s) if s else "n/a")
        rec[name] = r
        rows.append([name, f"{mx:.3f}x", f"{top_mb:.1f} MB"] + cells)
    mxs = sorted(max(loads_ops_random(sizes, C, f"pys-ops-{i}")) / (Vz / C) for i in range(20))
    rec["R1 operators co-locate, random seat (Zipf, 20k ops)"]["max_over_mean_20_seeds_median_max"] = [
        r4(S18.pct(mxs, 0.5)), r4(mxs[-1])]
    OUT["seat_rules"]["load_imbalance"] = rec
    print(f"\nPa note: operators co-locating in uniformly random seats, max seat / mean over 20 seeds: median "
          f"{S18.pct(mxs, 0.5):.2f}x, max {mxs[-1]:.2f}x (largest operator alone = {max(sizes) / (Vz / C):.2f} seats).")
    S18.table("Pa", "pick-your-seat (a): seat load imbalance at 10^6 validators and its latency effect (FRC C=23)",
              ["configuration", "max seat / mean", "largest unit's single votes", "p=1 explicit (s: mean/p95/max)",
               "p=1 L=3", "p=.67 explicit", "p=.67 L=3"], rows,
              note=f"Equal-stake validators (load = count = stake). Zipf(1) operators as Q18 E8 (largest {max(sizes) / Vz:.1%} "
                   f"of validators). Offline at p=.67: the same fraction of every seat. {SINGLE_DC_B} B per single vote "
                   "(Q18 sizing.py:45): 8.70 MB per balanced unit.")


def sim_adv(loads_h, loads_a, S, R, model, policy, L=3):
    """FRC C=len(loads), seat s holds honest online stake loads_h[s] and adversary stake loads_a[s].
    policy 'withhold': the adversary never votes; 'pivotal': its part of a seat votes only if that completes the
    quorum (given everything cast so far); 'edge': as pivotal, but only at the last adversarial seat before an
    honest-only seat (aims the post-switch lag at honest seats). Returns justification ticks."""
    C = len(loads_h)
    q2 = 2 * S
    lastH, lastA = [-1] * C, [-1] * C
    cur = acc = 0
    jt = []
    edge = [loads_a[s] > 0 and loads_a[(s + 1) % C] == 0 for s in range(C)]
    if model == "lag":
        lastj = -10 ** 9
        for t in range(R * C):
            s = t % C
            kn = cur if lastj <= t - L - 1 else cur - 1
            hv = 0
            if loads_h[s] and lastH[s] < kn:
                lastH[s] = kn
                if kn == cur:
                    hv = loads_h[s]
            a = loads_a[s]
            if a and policy != "withhold" and kn == cur and lastA[s] < cur:
                piv = 3 * (acc + hv) < q2 <= 3 * (acc + hv + a)
                if piv and (policy == "pivotal" or edge[s]):
                    lastA[s] = cur
                    hv += a
            acc += hv
            if 3 * acc >= q2:
                jt.append(t)
                lastj = t
                cur += 1
                acc = 0
        return jt
    # explicit-time
    pend = {}
    pend_cur = 0
    known = 0
    for j in range(R * C):
        s = j % C
        bt = 3 * ((j + 4) // 3)
        hv = 0
        if loads_h[s] and lastH[s] < known:
            lastH[s] = known
            hv = loads_h[s]
        a = loads_a[s]
        if a and policy != "withhold" and lastA[s] < known:
            piv = 3 * (acc + pend_cur + hv) < q2 <= 3 * (acc + pend_cur + hv + a)
            if piv and (policy == "pivotal" or edge[s]):
                lastA[s] = known
                hv += a
        if hv:
            pend.setdefault(bt, []).append((known, hv))
            pend_cur += hv
        if j % 3 == 0:
            batch = pend.pop(j, None)
            if batch is None:
                continue
            for (h, x) in batch:
                if h == cur:
                    acc += x
                    pend_cur -= x
            if 3 * acc >= q2:
                jt.append(j)
                cur += 1
                acc = 0
                pend_cur = sum(x for lst in pend.values() for (h, x) in lst if h == cur)
                known = cur
    return jt


def p_b_withhold():
    C = 23
    per = 300                       # stake units per seat; S = 6900 (divisible by 3)
    S = per * C
    rows = []
    rec = {}
    for beta_label, beta_num, beta_den in (("0.10", 1, 10), ("0.20", 1, 5), ("1/3", 1, 3)):
        A = S * beta_num // beta_den
        # spread: every seat loses the same share
        spread_a = [A // C + (1 if k < A % C else 0) for k in range(C)]
        spread_h = [per - x for x in spread_a]
        # co-located whole seats: adversary fills seats 0.. completely, honest hold the rest (balanced loads)
        col_a = [0] * C
        rem = A
        for k in range(C):
            x = min(per, rem)
            col_a[k] = x
            rem -= x
        col_h = [per - x for x in col_a]
        for place, hh, aa in (("spread (R0, or R1/R2 with honest seats unchanged)", spread_h, spread_a),
                              ("co-located whole seats (land grab / R2 long run)", col_h, col_a)):
            for policy in ("withhold", "pivotal", "edge"):
                if policy == "edge" and place.startswith("spread"):
                    continue
                cells = []
                r = {}
                for model in ("time", "lag"):
                    jt = sim_adv(hh, aa, S, R_STEADY, model, policy)
                    D = [d * UNIT_S for d in durations(jt, BURN * C)]
                    s = summ_s(D)
                    r["time" if model == "time" else "lag3"] = s
                    cells.append(fmt_s(s))
                rec[f"beta={beta_label}|{place.split(' (')[0]}|{policy}"] = r
                rows.append([beta_label, place, policy] + cells)
    OUT["seat_rules"]["withholding"] = rec
    S18.table("Pb", "pick-your-seat (b): adversary beta withholds (or votes only when pivotal), spread vs co-located; "
                    "FRC C=23, seconds/height mean / p95 / max",
              ["beta", "placement", "adversary policy", "explicit-time", "constant lag L=3"], rows,
              note="Balanced seat loads; honest validators always vote. withhold = never votes; pivotal = votes only when its "
                   "part of the seat completes the quorum; edge = pivotal, but only at the last adversarial seat before an "
                   "honest arc (aims the post-switch lag at honest seats). Plain withholding depends only on where the "
                   "HONEST stake sits, so R1/R2 with honest validators left in place equal the spread row.")


def p_cdef_calcs():
    C = 23
    unit_mb = V_MAIN / C * SINGLE_DC_B / 1e6
    out = {"unit_MB_at_1e6": r4(unit_mb)}
    # (c) burst bound
    rows = []
    burst = {}
    for bl, beta in (("0.10", 0.10), ("0.20", 0.20), ("1/3", 1 / 3)):
        no_win = beta * C
        r0 = 3 * beta
        r1 = beta * C                                   # no cap: all its stake fits in 3 seats' windows
        r2 = {k: min(beta * C, 3 * (beta + k - 1)) for k in (1.0, 1.05, 1.1)}
        lr = {k: min(beta * C, 3 * k) for k in (1.0, 1.05, 1.1)}
        burst[bl] = {"no_windows_units": r4(no_win), "R0_units": r4(r0), "R1_no_cap_units": r4(r1),
                     "R2_static_units": {str(k): r4(v) for k, v in r2.items()},
                     "R2_long_run_units": {str(k): r4(v) for k, v in lr.items()}}
        f = lambda u: f"{u:.2f} u = {u * unit_mb:.1f} MB"
        rows.append([bl, f(no_win), f(r0), f(r1), f(r2[1.1]), f(lr[1.0]), f(lr[1.1])])
    out["burst"] = burst
    S18.table("Pc", "pick-your-seat (c): worst withheld-vote burst one instant can carry (3 windows open, Q18 strawman T9)",
              ["beta", "no windows (Q18: beta*C)", "R0 windows (Q18: 3*beta)", "R1 no cap (all stake in 3 seats)",
               "R2 kappa=1.1, honest seats unchanged: 3(beta+kappa-1)", "whole seats, kappa=1: min(beta*C, 3)",
               "whole seats, kappa=1.1: min(beta*C, 3.3)"], rows,
              note=f"Units of one balanced unit (V/C single votes); MB at V = 10^6, {SINGLE_DC_B} B per vote "
                   f"= {unit_mb:.2f} MB per unit (Q18 network.md:271). Equal-size validators; with a stake cap and "
                   "32-ETH adversarial validators among consolidated honest ones, count-based load can exceed the "
                   "stake share (see clock.md).")
    # (d) aggregator capture
    csize = V_MAIN / C / COMMITTEES_PER_UNIT

    def p_none(h):
        return (1 - AGG_PER_COMMITTEE / csize) ** (h * csize)
    rows = []
    agg = {}
    for bl, beta in (("0.10", 0.10), ("0.20", 0.20), ("1/3", 1 / 3)):
        hs = {"R0 (adversary spread)": 1 - beta,
              "R1, all adversary stake into one seat": (1 - beta) / (1 - beta + beta * C),
              "R2 kappa=1.05, honest unchanged": (1 - beta) / 1.05,
              "R2 kappa=1.1, honest unchanged": (1 - beta) / 1.1}
        agg[bl] = {k: {"honest_share": r4(h), "p_no_honest_aggregator": float(f"{p_none(h):.3g}")} for k, h in hs.items()}
        rows.append([bl] + [f"h={h:.3f}: {p_none(h):.2g}" for h in hs.values()])
    op = {f"{int(100 * (1 - h))}% one operator": float(f"{p_none(h):.3g}") for h in (0.02, 0.05, 0.10, 0.20, 0.30)}
    out["aggregator_capture"] = {"committee_size": r4(csize), "by_rule": agg, "mixed_seat_by_operator_share": op}
    S18.table("Pd", "pick-your-seat (d): P(no honest on-time aggregator in a committee) = (1-16/|c|)^(h|c|) ~ e^(-16h)",
              ["beta", "R0 (adversary spread)", "R1: adversary piles into one seat",
               "R2 kappa=1.05 (honest stay)", "R2 kappa=1.1 (honest stay)"], rows,
              note=f"|c| = {csize:.0f} (10^6 / 23 / 64). Mixed seat where one operator holds 98/95/90/80/70%: "
                   + ", ".join(f"{k}: {v:.2g}" for k, v in op.items()) + ". A seat filled 100% by one operator has no "
                   "honest minority to censor.")
    # (e) window share, k = 4 consecutive units
    rows = []
    win = {}
    for bl, beta in (("0.10", 0.10), ("0.20", 0.20), ("1/3", 1 / 3)):
        rng = random.Random(f"pys-win-{bl}")
        adv = rng.sample(range(V_MAIN), int(beta * V_MAIN))
        cnt = [0] * C
        for v in adv:
            cnt[v % C] += 1
        tot = loads_stripe(V_MAIN, C)
        r0 = max(sum(cnt[(u + i) % C] for i in range(4)) / sum(tot[(u + i) % C] for i in range(4)) for u in range(C))
        r1 = beta * C / (beta * C + 4 * (1 - beta))
        r2 = {k: (beta + k - 1) / k for k in (1.0, 1.05, 1.1)}
        lr = min(1.0, beta * C / 4)
        win[bl] = {"R0_striped_random_adversary": r4(r0), "R1_all_into_4_seats": r4(r1),
                   "R2_static": {str(k): r4(v) for k, v in r2.items()}, "whole_seats_long_run": r4(lr)}
        rows.append([bl, f"{100 * r0:.2f}%", f"{100 * r1:.1f}%", f"{100 * r2[1.0]:.1f} / {100 * r2[1.05]:.1f} / "
                     f"{100 * r2[1.1]:.1f}%", f"{100 * lr:.1f}%"])
    out["window_share_k4"] = win
    S18.table("Pe", "pick-your-seat (e): largest adversary share over any 4 consecutive units",
              ["beta", "R0 striped, random indices (10^6, seeded)", "R1, honest stay, all adversary stake in 4 seats",
               "R2 kappa = 1 / 1.05 / 1.1, honest stay", "whole seats (land grab / R2 long run)"], rows,
              note="Q18 E8b reference (top Zipf operator, 9.4% global): 9.4-14.3% striped/shuffled, 12.5-17.8% contiguous.")
    # R2 capture time (front-running upper bound on the adversary's speed)
    rows = []
    cap = {}
    sigma = 256.0     # seat-change churn, ETH/epoch (assumption: like the activation/exit churn)
    seat = S_ETH / C
    for bl, beta in (("0.10", 0.10), ("0.20", 0.20), ("1/3", 1 / 3)):
        for X in (1 / 3, 1 / 2, 2 / 3, 0.9):
            row = [bl, f"{X:.2f}"]
            # R1 (no cap): move A - beta*S/C into one seat at sigma ETH/epoch; A = X/(1-X) * (1-beta) S/C
            A = X / (1 - X) * (1 - beta) * seat
            need = A - beta * seat
            r1_days = max(0.0, need) / sigma / EPOCHS_PER_DAY if A <= beta * S_ETH else float("inf")
            row.append(f"{r1_days:.1f} d" if math.isfinite(r1_days) else "infeasible")
            cap[f"{bl}|{X:.2f}|R1_sigma256"] = r4(r1_days) if math.isfinite(r1_days) else None
            for kappa in (1.0, 1.1):
                slack_share = (beta + kappa - 1) / kappa
                if X <= slack_share:
                    t_days = (kappa - 1) * seat / sigma / EPOCHS_PER_DAY * (X - beta) / max(1e-12, slack_share - beta)
                    cells = [t_days, t_days]
                else:
                    t_slack = (kappa - 1) * seat / sigma / EPOCHS_PER_DAY
                    cells = []
                    for ch in ("Electra", "EIP-8061"):
                        x = CHURN[ch]["exit"]
                        tau = (1 - beta) * S_ETH / x / EPOCHS_PER_DAY        # days
                        cells.append(t_slack + tau * math.log((1 - beta) / (kappa * (1 - X))))
                for ch, v in zip(("Electra", "EIP-8061"), cells):
                    cap[f"{bl}|{X:.2f}|R2_k{kappa}|{ch}"] = r4(v)
                row.append(f"{cells[0]:.0f} / {cells[1]:.0f} d")
            rows.append(row)
    out["r2_capture_days"] = cap
    S18.table("Pf", "pick-your-seat: days for a beta adversary to own share X of one seat (upper bound on its speed)",
              ["beta", "X", "R1 (no cap), seat-change churn 256 ETH/epoch",
               "R2 kappa=1.0: Electra / EIP-8061 exits", "R2 kappa=1.1: Electra / EIP-8061 exits"], rows,
              note="S = 36M ETH. R2: the cap slack (kappa-1)S/C is filled at 256 ETH/epoch, then honest exits at the full "
                   "exit churn (256 / 1098 ETH/epoch, eip-8061.md:222-235), all honest and uniform over seats, free room "
                   "that the adversary takes before honest deposits (front-running): t = tau*ln((1-beta)/(kappa(1-X))), "
                   "tau = (1-beta)S/exit churn. Requires the cap on EVERY inflow (seat change, deposit, top-up, "
                   "consolidation target). Q18 E12a reference (fixed composition, consolidation targeting, beta = 0.1, "
                   "X = 1/3): 8.3 d Electra / 4.4 d EIP-8061; era hash: not aimable.")
    # (f) state / request accounting
    f_rec = {"seat_field_bytes_per_validator": 1, "seat_field_MB_at_1e6": 1.0,
             "per_seat_totals_bytes": 8 * C, "cache_entry_increase_MB_at_1e6": 1.0,
             "seat_change_request_bytes": 20 + 48 + 1,
             "eip7251_consolidation_request_bytes": 20 + 48 + 48,
             "epochs_to_move_one_seat_at_256": r4(seat / sigma), "days_to_move_one_seat_at_256": r4(seat / sigma / EPOCHS_PER_DAY)}
    out["state"] = f_rec
    print(f"\nPg (f) state: seat field 1 B/validator (C <= 256) = 1 MB at 10^6; per-seat stake totals {8 * C} B; "
          f"seat-change request ~{20 + 48 + 1} B (source address + pubkey + seat; cf. EIP-7251 request 116 B); "
          f"moving one seat's worth ({seat / 1e6:.2f}M ETH) at 256 ETH/epoch takes {seat / sigma:,.0f} epochs = "
          f"{seat / sigma / EPOCHS_PER_DAY:.0f} days.")
    OUT["seat_rules"]["calcs"] = out


# ----------------------------------------------------------------------------
# machine-readable summaries for the web page (built from the numbers above)
# ----------------------------------------------------------------------------

CLOCK_OF = {"a": "Q17 grid (C=23)", "b": "Q17 grid (C=23)", "c": "Q17 grid (C=23)", "d": "FRC C=23", "e": "FRC C=23",
            "f22": "FRC C=22", "f24": "FRC C=24", "f25": "FRC C=25", "x23": "FRC C=23", "x24": "FRC C=24"}


def summaries():
    sch_out = OUT["schedules"]
    for k, lab in CLOCK_OF.items():
        if "blocks" in OUT and lab in OUT["blocks"]:
            sch_out.setdefault(k, {})["units_per_block"] = OUT["blocks"][lab]
    calc = OUT["seat_rules"].get("calcs", {})
    li = OUT["seat_rules"].get("load_imbalance", {})
    by = {}
    for rule, kappa in (("R0", None), ("R1", None), ("R2_k1.00", 1.0), ("R2_k1.05", 1.05), ("R2_k1.10", 1.1)):
        r = {}
        for bl in ("0.10", "0.20", "1/3"):
            bu = calc["burst"][bl]
            ag = calc["aggregator_capture"]["by_rule"][bl]
            wi = calc["window_share_k4"][bl]
            if rule == "R0":
                burst, agg, win = bu["R0_units"], ag["R0 (adversary spread)"], wi["R0_striped_random_adversary"]
            elif rule == "R1":
                burst, agg, win = bu["R1_no_cap_units"], ag["R1, all adversary stake into one seat"], wi["R1_all_into_4_seats"]
            else:
                burst = bu["R2_static_units"][str(kappa)]
                agg = {1.0: {"honest_share": r4(1 - (1 / 3 if bl == "1/3" else float(bl))),
                             "p_no_honest_aggregator": ag["R0 (adversary spread)"]["p_no_honest_aggregator"]},
                       1.05: ag["R2 kappa=1.05, honest unchanged"], 1.1: ag["R2 kappa=1.1, honest unchanged"]}[kappa]
                win = wi["R2_static"][str(kappa)]
            r[bl] = {"burst_units": burst, "burst_MB_at_1e6": r4(burst * calc["unit_MB_at_1e6"]),
                     "aggregator_capture": agg, "window_share_k4": win}
            if rule.startswith("R2"):
                r[bl]["long_run_whole_seats"] = {"burst_units": bu["R2_long_run_units"][str(kappa)],
                                                 "window_share_k4": wi["whole_seats_long_run"]}
                r[bl]["capture_days"] = {k2: v for k2, v in calc["r2_capture_days"].items()
                                         if k2.startswith(bl + "|") and f"R2_k{kappa}|" in k2}
            if rule == "R1":
                r[bl]["capture_days"] = {k2: v for k2, v in calc["r2_capture_days"].items()
                                         if k2.startswith(bl + "|") and "R1_" in k2}
        if rule.startswith("R2"):
            r["load"] = {n: v for n, v in li.items() if v["rule"] == f"R2 k={kappa}"}
        else:
            r["load"] = {n: v for n, v in li.items() if v["rule"].startswith(rule)}
        by[rule] = r
    OUT["seat_rules"]["by_rule"] = by
    # verdicts on the claimed consequences, numbers pulled from the tables above
    L = lambda k, m, p: sch_out[k]["latency"][m][p]["mean_s"]
    g = lambda k: sch_out[k]["gaps"]
    f = lambda k, v: sch_out[k]["fairness"][v]
    OUT["verdicts"] = [
        {"claim": "every cohort votes exactly every 92 s (G = C)",
         "verdict": "true", "evidence": f"FRC gap {g('d')['min_s']}-{g('d')['max_s']} s; Q17 fixed {g('a')['max_s']} s; "
                                        f"+rotation max {g('c')['max_s']} s (Q17) / {g('e')['max_s']} s (FRC)"},
        {"claim": "G = C is the gap-lemma optimum and buys latency",
         "verdict": "true in the constant-lag model, not at the threshold in the explicit-time model",
         "evidence": f"p=.67 L=3: FRC {L('d', 'lag3', '0.67')} s vs Q17 {L('a', 'lag3', '0.67')} s; explicit: "
                     f"{L('d', 'time', '0.67')} vs {L('a', 'time', '0.67')} s (+0 s sees block: {L('d', 'time0', '0.67')} vs "
                     f"{L('a', 'time0', '0.67')} s); p=1 explicit {L('d', 'time', '1.0')} vs {L('a', 'time', '1.0')} s"},
        {"claim": "in-slot offset cycles +0 -> +8 -> +4, exact in-slot fairness every 3 rounds without rotation",
         "verdict": "true for in-slot effects; false if any round-position effect exists",
         "evidence": f"eps-fair {f('d', 'in_slot_only')['eps_horizon_h']} h vs Q18 rec "
                     f"{f('c', 'with_round_boundary_penalties')['eps_horizon_h']} h; with MISS_UNIT0/MISS_LAST: FRC never "
                     f"(bias {f('d', 'with_round_boundary_penalties')['permanent_bias_pp']} pp)"},
        {"claim": "every block carries exactly 3 units",
         "verdict": "true (on-time); 8.7% of blocks carry two rounds' data",
         "evidence": f"FRC {OUT['blocks']['FRC C=23']['on_time_units']}, Q17 {OUT['blocks']['Q17 grid (C=23)']['on_time_units']}"},
        {"claim": "no round-first/round-last special seat under the instant switch",
         "verdict": "true iff nothing reads the round except accounting; a round-start freeze would make it worse",
         "evidence": "round starts mid-slot 2 of 3 rounds (X5)"},
        {"claim": "FG vote traffic per second +24/23",
         "verdict": "true", "evidence": f"{OUT['offsets']['FRC C=23']['fg_vote_rate_vs_q17']} x Q17"},
        {"claim": "an explicit rotation on top of FRC only hurts",
         "verdict": "true (gap, latency, in-slot fairness); it only helps if round-position penalties exist",
         "evidence": f"G {g('e')['G_ticks']} vs {g('d')['G_ticks']} ticks; eps-fair {f('e', 'in_slot_only')['eps_horizon_h']} h "
                     f"vs {f('d', 'in_slot_only')['eps_horizon_h']} h"},
    ]


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------

SECTIONS = {
    "sanity": x0_sanity, "gaps": x1_gaps, "latency": x2_latency, "drops": x2_drops, "blocks": x3_blocks,
    "fairness": x4_fairness, "offsets": x5_offsets, "order": x6_order,
    "seats": lambda: (p_a_loads(), p_b_withhold(), p_cdef_calcs()),
}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        print(__doc__)
        return
    names = list(SECTIONS) if "all" in args else args
    print(f"# clock.py output ({', '.join(names)})")
    OUT["meta"] = {"generator": "sim/clock.py", "q18_simulator": "../staggered-committees/sim/schedules.py",
                   "unit_s": UNIT_S, "slot_s": SLOT_S, "n_per_cohort": NPER, "rounds": R_STEADY, "burn": BURN,
                   "offline_sets_per_p": NSEEDS, "ps": PS,
                   "schedules": {s.key: {"name": s.name, "clock": s.clock, "C": s.C, "position_rule": SHIFT_DESC[s.tag],
                                         "round_s": s.round_s} for s in SCHEDS}}
    for nm in names:
        t0 = time.time()
        SECTIONS[nm]()
        print(f"\n[{nm}: {time.time() - t0:.1f}s, total {time.time() - T0:.1f}s]")
        sys.stdout.flush()
    if "all" in args:
        summaries()
        os.makedirs(RESULTS, exist_ok=True)
        path = os.path.join(RESULTS, "clock.json")
        with open(path, "w") as fh:
            json.dump(OUT, fh, indent=1, sort_keys=True)
            fh.write("\n")
        print(f"\nwrote {os.path.relpath(path, os.path.join(HERE, '..'))}")


if __name__ == "__main__":
    main()
