#!/usr/bin/env python3
"""designs.py -- FG target-picking designs on the free-running committee clock (FRC).

A copy of projects/ff/prefix-consensus/sim/prefix_sim.py (never modified) with one fix: a round is
C units (P.round_s = C * unit_s), so C = 23 gives 92 s rounds that are not slot-aligned. The
original EX / PX / RF engines and their tables (sanity, s0, s1, s2, s3) are kept unchanged and
still reproduce prefix_sim's output byte for byte at C = 24. The FRC study (2026-10-06) adds
instrumented engines below the "FRC study" marker:

  ex-instant    floating heights, instant switch (EX(2R), Mikhail's draft)
  ex-sticky     same state machine; a voter of round r votes the state of the block visible at
                round r's first unit for the whole round
  round-target  checkpoint of round r = head visible at unit 23r; FFG source/target, k = 1
  px-sticky     prefix counting per round: votes name the head at vote time; J*_r = deepest block
                with 2/3 of round r's votes at or after it; k = 1 prefix finalization
  rf            Rolling FFG (F1)+(F2'), boundaries delta slots deep

`python3 sim/designs.py all` prints every table of results/designs.md;
`python3 sim/designs.py traces` writes results/traces.json.

Original prefix_sim.py docstring:

Designs
  EX(dt)  exact entry target (rewrite.tex section 4, Lean ChainState, Mikhail's DC draft).
          A height pair counts iff it names the chain's current entry T_h. A progress quorum is
          consumed only by a block with slot >= T_h.slot + dt (dt = 0: Mikhail's draft;
          dt = 16 slots = 2R: rewrite.tex).
  PX(dt)  in-height prefix justification (prefix_height_filter_and_timeouts.tex). The target is
          the voter's source block; it counts iff it is a strict ancestor of the including block
          and lies in the current height interval. J* = deepest T with >= 2/3 of targets >= T.
          Finality pairs are exact (h_j, J) as in EX; the finalize gate is not modelled.
  RF      Rolling FFG with (F1)+(F2') (projects/ff/continuous-fg/README.md section 3). Positions
          are units, per-validator windows, boundaries rf_delta slots deep, on-chain counting.

Deterministic, stdlib only. `python3 prefix_sim.py all` prints every table of REPORT.md.
"""
import argparse
import bisect
import json
import os
from math import gcd
from collections import defaultdict
from dataclasses import dataclass, replace

W0 = 10_000  # integer stake per cohort, so 2/3 quorum checks are exact


def cdiv(a, b):
    return -(-a // b)


@dataclass(frozen=True)
class P:
    C: int = 24            # units (= cohorts) per round
    ups: int = 3           # units per slot
    unit_s: int = 4        # seconds per unit
    agg: int = 8           # a vote cast at time t lands in the first block at or after t + agg
    vis: int = 1           # a block is visible vis s after its proposal (0 = next event)
    conf: int = 6          # the block of slot s-1 is confirmed at t_s + conf
    mode: str = "head"     # voter source block: "head" or "conf"
    rounds: int = 40
    rot_K: int = 0         # forward rotation: one seat later every rot_K rounds (0 = fixed)
    p: float = 1.0         # online honest stake (fraction of total)
    beta: float = 0.0      # adversarial stake: votes timeouts at every height (EX/PX)
    pack: bool = False     # adversary packs all its timeouts into the block after a switch
    split_k: int = 0       # EX/PX: equivocate the justifying block of every k-th height
    split_r: int = 1       # the AC resolves to E1 after r slots
    split_x: float = 0.0   # share of each unit's honest stake that sees E2 in the window
    conf_fail: bool = False  # conf mode: the split survives confirmation
    dt: int = 16           # timeout delay in slots (EX/PX)
    rf_delta: int = 2      # RF boundary lag in slots
    rf_ancestry: bool = True  # RF: an off-chain target still counts for its common prefix

    @property
    def slot_s(self):
        return self.unit_s * self.ups

    @property
    def round_s(self):                 # FRC fix: a round is C units (92 s at C = 23), not slot-aligned
        return self.C * self.unit_s

    @property
    def spr(self):                     # slots per round, a float when ups does not divide C
        return self.round_s / self.slot_s

    @property
    def slots(self):                   # simulated slots
        return cdiv(self.rounds * self.round_s, self.slot_s)


IDEAL = P(ups=1, unit_s=4, agg=0, vis=0, conf=0)   # one block per unit, no delays


# ----------------------------------------------------------------------------- common pieces
def make_validators(pp):
    vals = []                       # (vid, cohort, weight, kind)
    for c in range(pp.C):
        hon = round(pp.p * W0)
        b = round(pp.split_x * hon)
        for kind, w in (("A", hon - b), ("B", b), ("adv", round(pp.beta * W0))):
            if w > 0:
                vals.append((len(vals), c, w, kind))
    return vals, pp.C * W0


def quorum(w, total):
    return 3 * w >= 2 * total


def offset(pp, r):
    return (r // pp.rot_K) % pp.C if pp.rot_K else 0


def cohort_at(pp, tau):
    r, k = divmod(tau, pp.C)
    return (k - offset(pp, r)) % pp.C


def prev_tick(pp, c, tau):
    r = tau // pp.C
    if r == 0:
        return tau - pp.C
    return (r - 1) * pp.C + (c + offset(pp, r - 1)) % pp.C


def head_slot(pp, t):
    return max(0, (t - max(pp.vis, 1)) // pp.slot_s)


def conf_slot(pp, t):
    return max(0, (t - max(pp.conf, 1)) // pp.slot_s - 1)


def land(pp, t):
    return cdiv(t + pp.agg, pp.slot_s)


def e2_id(s):
    return -(s + 1)


def e2_slot(b):
    return -b - 1


def anc(a, b):
    """a is an ancestor of (or equal to) b; canonical ids are slots, E2 ids are negative."""
    if a >= 0 and b >= 0:
        return a <= b
    if a >= 0:
        return a <= e2_slot(b) - 1
    return a == b


class Splits:
    """Equivocated slots: E2 is visible to the B group inside [lo, hi)."""

    def __init__(self, pp):
        self.pp, self.win = pp, []

    def add(self, s):
        pp = self.pp
        if pp.mode == "head":
            lo = s * pp.slot_s + max(pp.vis, 1)
        elif pp.conf_fail:
            lo = (s + 1) * pp.slot_s + max(pp.conf, 1)
        else:
            return False
        self.win.append((lo, lo + pp.split_r * pp.slot_s, e2_id(s)))
        return True

    def e2_for(self, t):
        for lo, hi, eid in self.win:
            if lo <= t < hi:
                return eid
        return None


def ticks_of_slot(pp, s):
    for j in range(pp.ups):
        tau = s * pp.ups + j
        yield tau, tau * pp.unit_s, j


def block_lags(pp, fin_of_block, nslots):
    warm, tail = cdiv(6 * pp.round_s, pp.slot_s), cdiv(8 * pp.round_s, pp.slot_s)
    lags, unfin = [], 0
    for b in range(warm, nslots - tail):
        f = fin_of_block(b)
        if f is None:
            unfin += 1
        else:
            lags.append((f - b * pp.slot_s) / pp.round_s)
    return lags, unfin


def summary(xs):
    if not xs:
        return dict(mean=float("nan"), p95=float("nan"), max=float("nan"), min=float("nan"))
    ys = sorted(xs)
    return dict(mean=sum(ys) / len(ys), p95=ys[min(len(ys) - 1, int(0.95 * len(ys)))],
                max=ys[-1], min=ys[0])


# ----------------------------------------------------------------------------- EX / PX engine
def genesis_state():
    return dict(h=1, E=0, sh=0, J=0, hj=0, F=0, hF=0, tgt={}, prog=frozenset(), fin=frozenset())


def transition(pp, design, st, votes, s, W, total, ev, t):
    """One block at slot s: fold the votes, then the height events (rewrite.tex section 4)."""
    tgt, prog, fin = dict(st["tgt"]), set(st["prog"]), set(st["fin"])
    for vid, h, T, to, hf, Jf in votes:
        if st["hj"] > st["hF"] and hf == st["hj"] and Jf == st["J"]:
            fin.add(vid)                                  # finality pair folded regardless
        if h is None or h != st["h"]:
            continue
        if design == "EX":
            if T == st["E"]:                              # names the chain's own entry
                prog.add(vid)
                if not to:
                    tgt[vid] = T
        else:                                             # PX: fresh prefix target
            if to:
                prog.add(vid)
            elif T is not None and T >= 0 and st["sh"] <= T < s:
                tgt.setdefault(vid, T)                    # first target wins (E1)
                prog.add(vid)
    st = dict(st, tgt=tgt, prog=prog, fin=fin)
    if st["hj"] > st["hF"] and quorum(sum(W[v] for v in fin), total):
        st["F"], st["hF"] = st["J"], st["hj"]
        ev.append(("F", t, st["F"]))
    jstar = None
    if design == "EX":
        if quorum(sum(W[v] for v in tgt), total):
            jstar = st["E"]
    else:
        acc = 0
        for v, T in sorted(tgt.items(), key=lambda kv: -kv[1]):
            acc += W[v]
            if quorum(acc, total):
                jstar = T
                break
    if jstar is not None:
        st.update(J=jstar, hj=st["h"], fin=set())
        ev.append(("J", t, st["h"], jstar, st["E"]))
        st.update(h=st["h"] + 1, E=s, sh=s, tgt={}, prog=set())
    elif quorum(sum(W[v] for v in prog), total) and s >= st["sh"] + pp.dt:
        ev.append(("P", t, st["h"]))
        st.update(h=st["h"] + 1, E=s, sh=s, tgt={}, prog=set())
    return st


def run_heights(pp, design):
    vals, total = make_validators(pp)
    W = {v[0]: v[2] for v in vals}
    by_cohort = defaultdict(list)
    for vid, c, w, kind in vals:
        by_cohort[c].append((vid, kind))
    adv = [v[0] for v in vals if v[3] == "adv"]
    S = pp.slots
    states, e2 = {0: genesis_state()}, {}
    lam = {v[0]: dict(target={}, timeout={}, lock={}) for v in vals}
    landing, ev = defaultdict(list), []
    splits, split_log = Splits(pp), []

    def state(b):
        return states[b] if b >= 0 else e2[b]

    def decide(vid, kind, t):
        hs = head_slot(pp, t)
        src = hs if pp.mode == "head" else conf_slot(pp, t)
        head = hs
        if kind == "B":
            eid = splits.e2_for(t)
            if eid is not None:
                src = head = eid
        st, H = state(src), state(head)
        if kind == "adv":
            if pp.pack:
                return None
            return (vid, st["h"], st["E"] if design == "EX" else None, True, None, None)
        L = lam[vid]
        if vid in st["prog"] and not (H["hj"] > H["hF"] and vid not in H["fin"]):
            return None                                   # back-off: already counted
        fp = None
        hj, J, hF = H["hj"], H["J"], H["hF"]
        pt = L["target"].get(hj)
        # EX (E1): a finality pair (h, J) conflicts with any other target at h.
        # PX: justify T and finalize D <= T at one height is allowed (Roberto's E1-E3).
        ok_t = pt in (None, J) if design == "EX" else (pt is None or anc(J, pt))
        if hj > hF and ok_t and not L["timeout"].get(hj) and L["lock"].get(hj) in (None, J):
            fp = (hj, J)
        hc = st["h"]
        T = st["E"] if design == "EX" else src
        lock = fp[1] if fp and fp[0] == hc else L["lock"].get(hc)
        prev = L["target"].get(hc)
        if design == "PX" and fp and fp[0] == hc:
            hp = None                                     # finalize only (keeps D <= target)
        elif L["timeout"].get(hc):
            hp = (hc, T, True)
        elif lock is not None and design == "EX":
            hp = (hc, T, False) if lock == T else None
        elif prev is not None:
            if design == "EX":
                hp = (hc, T, prev != T)
            else:                                         # re-send if still fresh on source
                ok = prev >= 0 and st["sh"] <= prev and (src < 0 or prev <= src)
                hp = (hc, prev, False) if ok else (hc, None, True)
        else:
            hp = (hc, T, False)
        if fp:
            L["lock"][fp[0]] = fp[1]
        if hp:
            if hp[2]:
                L["timeout"][hp[0]] = True
            elif L["target"].get(hp[0]) is None:
                L["target"][hp[0]] = hp[1]
        if hp is None and fp is None:
            return None
        return (vid, hp[0] if hp else None, hp[1] if hp else None, hp[2] if hp else False,
                fp[0] if fp else None, fp[1] if fp else None)

    def vote_tick(tau, t):
        for vid, kind in by_cohort[cohort_at(pp, tau)]:
            v = decide(vid, kind, t)
            if v:
                landing[land(pp, t)].append(v)

    for s in range(1, S + 1):
        for tau, t, j in ticks_of_slot(pp, s):
            if j == 0:
                vote_tick(tau, t)
        t0 = s * pp.slot_s
        before = states[s - 1]
        n0 = len(ev)
        st = transition(pp, design, before, landing.pop(s, []), s, W, total, ev, t0)
        states[s] = st
        if pp.pack and st["h"] > before["h"]:
            for vid in adv:
                landing[s + 1].append((vid, st["h"], s if design == "EX" else None, True,
                                       None, None))
        justified_now = [e for e in ev[n0:] if e[0] == "J"]
        if pp.split_k and justified_now and justified_now[0][2] % pp.split_k == 0:
            if splits.add(s):
                e2[e2_id(s)] = dict(st, E=e2_id(s))
                split_log.append((s, st["h"]))
        for tau, t, j in ticks_of_slot(pp, s):
            if j > 0:
                vote_tick(tau, t)

    fins = [(t, F) for (k, t, F, *_) in ev if k == "F"]
    ftimes, fslots = [f[0] for f in fins], [f[1] for f in fins]

    def fin_of_block(b):
        i = bisect.bisect_left(fslots, b)
        return ftimes[i] if i < len(fslots) else None

    lags, unfin = block_lags(pp, fin_of_block, S)
    warm_t, end_t = 6 * pp.round_s, (pp.rounds - 8) * pp.round_s
    adv_ev = [e for e in ev if e[0] in ("J", "P") and warm_t <= e[1] < end_t]
    jev = [e for e in adv_ev if e[0] == "J"]
    times = [e[1] for e in adv_ev]
    rph = (times[-1] - times[0]) / (len(times) - 1) / pp.round_s if len(times) > 1 else float("nan")
    ages = [(e[1] - e[3] * pp.slot_s) / pp.round_s for e in jev]
    locked = []
    for s, h1 in split_log:
        if s > (pp.rounds - 8) * pp.spr:                  # outcome not observable before the end
            continue
        w = sum(W[v] for v in W if lam[v]["target"].get(h1) == e2_id(s))
        just = any(e[0] == "J" and e[2] == h1 for e in ev)
        locked.append((w / total, just))
    fset = set(fslots)
    fskip = sum(1 for e in jev if e[3] not in fset)       # J finalized only as an ancestor
    return dict(lags=lags, unfin=unfin, rph=rph, jfrac=len(jev) / len(adv_ev) if adv_ev else 0.0,
                age=summary(ages), F_end=states[S]["F"], S=S, split_slots=[s for s, _ in split_log],
                locked=locked, fskip=fskip, njust=len(jev))


def run_heights_round(pp, design):
    """Round-aligned close: height r targets the last block before round r (Gasper-style
    boundary); every vote of round r counts; events fire once, at the block where the last
    vote of the round lands; J_r finalizes at the next close. Full participation, no faults."""
    S = pp.slots
    close = {}
    jslot = {}
    for r in range(1, pp.rounds - 1):
        E = cdiv(r * pp.round_s, pp.slot_s) - 1      # last block before round r
        last_t = ((r + 1) * pp.C - 1) * pp.unit_s
        close[r] = land(pp, last_t) * pp.slot_s
        targets = []
        for tau in range(r * pp.C, (r + 1) * pp.C):
            t = tau * pp.unit_s
            src = head_slot(pp, t) if pp.mode == "head" else conf_slot(pp, t)
            targets.append(max(E, src) if design == "PX" else E)
        targets.sort(reverse=True)
        need = cdiv(2 * pp.C, 3)
        jslot[r] = targets[need - 1]
    fin = sorted((close[r + 1], jslot[r]) for r in jslot if r + 1 in close)
    ftimes, fslots = [f[0] for f in fin], [f[1] for f in fin]

    def fin_of_block(b):
        i = bisect.bisect_left(fslots, b)
        return ftimes[i] if i < len(fslots) else None

    lags, unfin = block_lags(pp, fin_of_block, S)
    ages = [(close[r] - jslot[r] * pp.slot_s) / pp.round_s for r in jslot]
    return dict(lags=lags, unfin=unfin, rph=1.0, jfrac=1.0, age=summary(ages))


# ----------------------------------------------------------------------------- RF engine
def run_rf(pp, split_slots=()):
    vals, total = make_validators(pp)
    W = {v[0]: v[2] for v in vals}
    coh = {v[0]: v[1] for v in vals}
    by_cohort = defaultdict(list)
    for vid, c, w, kind in vals:
        if kind != "adv":                                 # the adversary abstains in RF
            by_cohort[c].append((vid, kind))
    S = pp.slots
    d = pp.rf_delta
    splits = Splits(pp)
    split_set = set(split_slots)

    def X(q):                                             # boundary: last block with slot < X
        return q // pp.ups - d

    def supports(T, q):                                   # bd_q(T) == bd_q(canonical)
        x = X(q)
        if x <= 0:
            return True
        if T >= 0:
            return T >= x - 1
        return pp.rf_ancestry and x <= e2_slot(T)

    justified = {0: 0}
    known = {0: 0}                                        # max justified position after block s
    tally = defaultdict(int)
    lockw = defaultdict(lambda: defaultdict(int))         # p -> p* -> (F2') lock weight
    allv = defaultdict(lambda: defaultdict(int))          # q -> (src, T) -> weight
    fin_time = {}
    landing = defaultdict(list)
    pend = []                                             # justified, not yet finalized

    def decide(vid, kind, tau, t):
        hs = head_slot(pp, t)
        src = hs if pp.mode == "head" else conf_slot(pp, t)
        if kind == "B":
            eid = splits.e2_for(t)
            if eid is not None:
                src = eid
        k = known[src if src >= 0 else e2_slot(src)]
        x = X(tau)
        if src >= 0:
            T = min(src, max(0, x - 1))
        else:
            T = src if x - 1 >= e2_slot(src) else max(0, x - 1)
        return (vid, tau, T, k)

    for s in range(1, S + 1):
        t0 = s * pp.slot_s
        for tau, t, j in ticks_of_slot(pp, s):
            if j == 0:
                for vid, kind in by_cohort[cohort_at(pp, tau)]:
                    landing[land(pp, t)].append(decide(vid, kind, tau, t))
        newly = []
        for vid, tau, T, src in landing.pop(s, []):
            lo = prev_tick(pp, coh[vid], tau)
            for q in range(max(1, lo + 1), tau + 1):
                allv[q][(src, T)] += W[vid]
                # (F2'): a vote counting for q with source >= p and bd_p(T) = B is a lock for p.
                for p in pend:
                    if p >= q or p > src:
                        break
                    if supports(T, p):
                        lockw[p][q] += W[vid]
                if q not in justified and src < q and supports(T, q):
                    tally[q] += W[vid]
                    if quorum(tally[q], total):
                        justified[q] = t0
                        newly.append(q)
        for q in newly:                                   # locks cast before q joined pend
            for q2 in range(q + 1, q + 2 * pp.C + 1):
                for (src, T), w in allv[q2].items():
                    if src >= q and supports(T, q):
                        lockw[q][q2] += w
            bisect.insort(pend, q)
        known[s] = max(justified)
        done = []
        for p in pend:
            p2 = p + 1
            while p2 in justified and p2 <= p + 2 * pp.C:
                if quorum(lockw[p][p2], total):
                    fin_time[p] = t0
                    done.append(p)
                    break
                p2 += 1
        for p in done:
            pend.remove(p)
            lockw.pop(p, None)
        if s in split_set:
            splits.add(s)
        for tau, t, j in ticks_of_slot(pp, s):
            if j > 0:
                for vid, kind in by_cohort[cohort_at(pp, tau)]:
                    landing[land(pp, t)].append(decide(vid, kind, tau, t))

    best = defaultdict(lambda: None)
    for p, ft in fin_time.items():
        b = max(0, X(p) - 1)
        if best[b] is None or ft < best[b]:
            best[b] = ft
    suf, cur = {}, None
    for b in range(S, -1, -1):
        if best[b] is not None and (cur is None or best[b] < cur):
            cur = best[b]
        suf[b] = cur
    lags, unfin = block_lags(pp, lambda b: suf.get(b), S)
    warm, end = 6 * pp.C, (pp.rounds - 8) * pp.C
    jd = [(justified[q] - q * pp.unit_s) / pp.round_s for q in range(warm, end) if q in justified]
    ages = [(justified[q] - max(0, X(q) - 1) * pp.slot_s) / pp.round_s
            for q in range(warm, end) if q in justified]
    gaps = sum(1 for q in range(warm, end) if q not in justified)
    return dict(lags=lags, unfin=unfin, jdelay=summary(jd), age=summary(ages), gaps=gaps,
                jfrac=1 - gaps / max(1, end - warm))


# ----------------------------------------------------------------------------- reporting
def fmt(x, nd=2):
    return "—" if x != x else f"{x:.{nd}f}"


def lagrow(name, r):
    s = summary(r["lags"])
    return (f"| {name} | {fmt(s['min'])} | {fmt(s['mean'])} | {fmt(s['p95'])} | {fmt(s['max'])} "
            f"| {fmt(r.get('rph', float('nan')))} | {fmt(r['age']['mean'])} | {r['unfin']} |")


LAGHDR = ("| design | lag min | lag mean | lag p95 | lag max | rounds/height | J age at "
          "justification | unfinalized |\n|---|---|---|---|---|---|---|---|")


def sanity():
    print("### Sanity (ideal: one block per unit, no delays)\n")
    print(LAGHDR)
    for C, vis in ((24, 0), (23, 0), (23, 13)):
        pp = replace(IDEAL, C=C, vis=vis)
        print(lagrow(f"EX(2R) C={C} vis={vis}s", run_heights(pp, "EX")))
    for C in (24, 23):
        pp = replace(IDEAL, C=C, rf_delta=0)
        r = run_rf(pp)
        print(lagrow(f"RF δ=0 C={C}", dict(r, rph=float("nan"))))
    print()


def s0():
    print("### S0 — honest, full participation (C = 24, 3 units/slot, lags in rounds)\n")
    print(LAGHDR)
    for mode in ("head", "conf"):
        base = replace(P(), mode=mode)
        for name, design in (("EX(2R)", "EX"), ("PX(2R)", "PX")):
            print(lagrow(f"{name} {mode}", run_heights(base, design)))
        for d in ((0, 1, 2) if mode == "head" else (2, 3)):
            r = run_rf(replace(base, rf_delta=d))
            print(lagrow(f"RF δ={d} {mode}", dict(r, rph=float("nan"))))
        for name, design in (("EX round-close", "EX"), ("PX round-close", "PX")):
            print(lagrow(f"{name} {mode}", run_heights_round(base, design)))
    print()


def s1():
    print("### S1 — participation p (head mode)\n")
    print(LAGHDR)
    for p in (0.8, 0.7):
        base = replace(P(), p=p)
        for name, design in (("EX(2R)", "EX"), ("PX(2R)", "PX")):
            print(lagrow(f"{name} p={p}", run_heights(base, design)))
        r = run_rf(replace(base, rf_delta=2))
        print(lagrow(f"RF δ=2 p={p}", dict(r, rph=float("nan"))))
    print()


def s2():
    print("### S2 — entry split (every 5th justified height's justifying block equivocated)\n")
    print("| setting | design | splits | locked honest stake / split | h+1 justified | J finalized "
          "only as ancestor | lag mean (no split → split) | lag max (no split → split) | RF gaps "
          "|\n|---|---|---|---|---|---|---|---|---|")
    for mode, cf in (("head", False), ("conf", True)):
        for p in (1.0, 0.8, 0.72):
            for r_, x in ((1, 0.5), (2, 0.3), (2, 0.5), (4, 0.5)):
                base = replace(P(), mode=mode, p=p, rounds=60)
                sp = replace(base, split_k=5, split_r=r_, split_x=x, conf_fail=cf)
                tag = f"{mode}{' conf-fail' if cf else ''} p={p} r={r_} x={x}"
                for name, design in (("EX(2R)", "EX"), ("PX(2R)", "PX")):
                    b0 = run_heights(replace(base, split_x=x), design)
                    b1 = run_heights(sp, design)
                    s0_, s1_ = summary(b0["lags"]), summary(b1["lags"])
                    lk = b1["locked"]
                    lkm = sum(a for a, _ in lk) / len(lk) if lk else 0
                    jn = sum(1 for _, j in lk if j)
                    print(f"| {tag} | {name} | {len(lk)} | {lkm:.3f} | {jn}/{len(lk)} | "
                          f"{b0['fskip']} → {b1['fskip']} of {b1['njust']} | "
                          f"{fmt(s0_['mean'])} → {fmt(s1_['mean'])} | {fmt(s0_['max'])} → "
                          f"{fmt(s1_['max'])} | — |")
                    if name == "EX(2R)":
                        slots = b1["split_slots"]
                for d in ((0, 2) if mode == "head" else (2,)):
                    rb = replace(base, split_x=x, rf_delta=d)
                    a0 = run_rf(rb)
                    a1 = run_rf(replace(rb, split_r=r_, conf_fail=cf), split_slots=slots)
                    s0_, s1_ = summary(a0["lags"]), summary(a1["lags"])
                    print(f"| {tag} | RF δ={d} | {len(slots)} | — | — | — | {fmt(s0_['mean'])} → "
                          f"{fmt(s1_['mean'])} | {fmt(s0_['max'])} → {fmt(s1_['max'])} | "
                          f"{a0['gaps']} → {a1['gaps']} |")
    print("\n(conf mode without a confirmation failure has no split: identical to its baseline.)\n")


def s3():
    print("### S3 — timeout racing (adversary β votes timeouts at every height; honest 1−β)\n")
    print("| β | packing | EX(0) just. / fin. | PX(0) just. / fin. | EX(2R) just. / lag mean "
          "/ rounds per height | PX(2R) just. / lag mean | RF (p = 1−β) lag mean / max |\n"
          "|---|---|---|---|---|---|---|")
    for beta in (0.05, 0.1, 0.15, 0.2, 0.25, 0.3):
        rf = run_rf(replace(P(), p=1 - beta, rf_delta=2))
        rs = summary(rf["lags"])
        for pack in (False, True):
            cells = []
            for dt in (0, 16):
                for design in ("EX", "PX"):
                    pp = replace(P(), p=1 - beta, beta=beta, pack=pack, dt=dt)
                    r = run_heights(pp, design)
                    if dt == 0:
                        cells.append(f"{r['jfrac']:.2f} / {r['F_end'] / r['S']:.2f}")
                    else:
                        m = summary(r["lags"])["mean"]
                        extra = f" / {fmt(r['rph'])}" if design == "EX" else ""
                        cells.append(f"{r['jfrac']:.2f} / {fmt(m)}{extra}")
            print(f"| {beta} | {'packed' if pack else 'own units'} | " + " | ".join(cells) +
                  f" | {fmt(rs['mean'])} / {fmt(rs['max'])} |")
    print("\n(just. = share of height advances that justified; fin. = finalized slot at the end "
          "/ simulated slots; lags in rounds.)\n")
    print("#### S3b — halting threshold of EX(0) vs. grid alignment (own-unit timing)\n")
    print("| offline stake | smallest β (step 0.01) with zero justified heights | justified share "
          "at β = 0.02 / 0.05 / 0.10 |\n|---|---|---|")
    for off in (0.0, 0.03, 0.05, 0.1, 0.15):
        def jf(beta):
            return run_heights(replace(P(), p=1 - off - beta, beta=beta, dt=0, rounds=24),
                               "EX")["jfrac"]
        stop = next((b / 100 for b in range(1, 31) if jf(b / 100) == 0.0), None)
        print(f"| {off} | {stop if stop is not None else '> 0.30'} | "
              f"{jf(0.02):.2f} / {jf(0.05):.2f} / {jf(0.10):.2f} |")
    print()


# ============================================================================= FRC study
# Free-running committee clock (FRC), 2026-10-06. Unit u starts at 4u s; cohort u mod C votes in
# it; three units per 12 s slot; a round is C = 23 units = 92 s and is not slot-aligned. A vote
# cast at t lands in the block of slot ceil((t + 8)/12); blocks are visible 1 s after proposal.
# Every engine below returns the same record: per-block first-event times (pick, justified,
# finalized; "the block or a descendant"), per-checkpoint records and per-unit records.

FRC = P(C=23, ups=3, unit_s=4, agg=8, vis=1, conf=6, mode="head", rounds=100)
IDEAL23 = replace(IDEAL, C=23, rounds=60)
PS = (1.0, 0.9, 0.8, 0.7)
KINDS = ("timely", "stale", "redundant", "abstain")


def measure_window(pp):
    """Blocks [lo, hi): 6 rounds of burn-in, then whole substrate periods (23 slots = 3 rounds on
    the FRC), ending >= 8 rounds before the end of the run so every measured block finalizes."""
    per = pp.round_s // gcd(pp.round_s, pp.slot_s)
    lo = cdiv(6 * pp.round_s, pp.slot_s)
    hi_max = pp.slots - cdiv(8 * pp.round_s, pp.slot_s)
    return lo, lo + max(1, (hi_max - lo) // per) * per


def cover(events, S):
    """first[b] = earliest t over events (t, slot) with slot >= b: the block or a descendant."""
    best = [None] * (S + 1)
    for t, b in events:
        if b is not None and 0 <= b <= S and (best[b] is None or t < best[b]):
            best[b] = t
    out, cur = [None] * (S + 1), None
    for b in range(S, -1, -1):
        if best[b] is not None and (cur is None or best[b] < cur):
            cur = best[b]
        out[b] = cur
    return out


def finish(pp, design, pick_ev, just_ev, fin_ev, cps, units, kinds, info):
    S = pp.slots
    res = dict(pp=pp, design=design, pick=cover(pick_ev, S), just=cover(just_ev, S),
               fin=cover(fin_ev, S), cps=cps, units=units, kinds=dict(kinds), info=info)
    for c in cps:                      # first time the target block or a descendant finalized
        c["finalized_at"] = res["fin"][c["target_slot"]]
    return res


def in_window(pp, t):
    lo, hi = measure_window(pp)
    return lo * pp.slot_s <= t < hi * pp.slot_s


def unit_rec(pp, tau, t, kind, cp, tslot):
    return dict(u=tau, t=float(t), cohort=cohort_at(pp, tau), round=tau // pp.C, kind=kind,
                checkpoint=cp, target_slot=tslot, lands_slot=land(pp, t))


# ----------------------------------------------------------------------------- ex-instant / ex-sticky
def ex_status(v, st):
    """What a landed EX vote does in the block that includes it (pre-state st)."""
    vid, h, T, to, hf, Jf = v
    if h is None:
        return "redundant"                                # finality pair only
    if h != st["h"] or T != st["E"]:
        return "stale"                                    # names a closed height / old entry
    if to:
        return "timeout"
    return "redundant" if vid in st["tgt"] else "timely"


def run_ex(pp, sigma=0.0):
    """EX(dt) of run_heights with honest voters only. A share sigma of every cohort's online stake
    is sticky: in round r it takes its (finalize pair, height pair) from the block visible at
    round r's first unit; the rest switches instantly (head or confirmed block at vote time)."""
    vals = []
    for c in range(pp.C):
        hon = round(pp.p * W0)
        ws = round(sigma * hon)
        for kind, w in (("A", hon - ws), ("S", ws)):
            if w > 0:
                vals.append((len(vals), c, w, kind))
    total = pp.C * W0
    W = {v[0]: v[2] for v in vals}
    by_cohort = defaultdict(list)
    for vid, c, w, kind in vals:
        by_cohort[c].append((vid, kind))
    single = all(len(by_cohort[c]) == 1 for c in range(pp.C))
    S = pp.slots
    states = {0: genesis_state()}
    lam = {v[0]: dict(target={}, timeout={}, lock={}) for v in vals}
    landing, ev = defaultdict(list), []
    units, kinds, first_vote = {}, defaultdict(int), {}

    def decide(vid, kind, tau, t):
        tv = (tau // pp.C) * pp.round_s if kind == "S" else t
        hs = head_slot(pp, tv)
        src = hs if pp.mode == "head" else conf_slot(pp, tv)
        st, H = states[src], states[hs]
        L = lam[vid]
        if vid in st["prog"] and not (H["hj"] > H["hF"] and vid not in H["fin"]):
            return None, st                               # back-off: already counted
        fp = None
        hj, J, hF = H["hj"], H["J"], H["hF"]
        pt = L["target"].get(hj)
        if hj > hF and pt in (None, J) and not L["timeout"].get(hj) and \
                L["lock"].get(hj) in (None, J):
            fp = (hj, J)
        hc, T = st["h"], st["E"]
        lock = fp[1] if fp and fp[0] == hc else L["lock"].get(hc)
        prev = L["target"].get(hc)
        if L["timeout"].get(hc):
            hp = (hc, T, True)
        elif lock is not None:
            hp = (hc, T, False) if lock == T else None
        elif prev is not None:
            hp = (hc, T, prev != T)
        else:
            hp = (hc, T, False)
        if fp:
            L["lock"][fp[0]] = fp[1]
        if hp:
            if hp[2]:
                L["timeout"][hp[0]] = True
            elif L["target"].get(hp[0]) is None:
                L["target"][hp[0]] = hp[1]
        if hp is None and fp is None:
            return None, st
        return (vid, hp[0] if hp else None, hp[1] if hp else None, hp[2] if hp else False,
                fp[0] if fp else None, fp[1] if fp else None), st

    def note(tau, t, vid, kind, h, T):
        if in_window(pp, t):
            kinds[kind] += W[vid]
        if single:
            units[tau] = unit_rec(pp, tau, t, kind, h, T)

    def vote_tick(tau, t):
        for vid, kind in by_cohort[cohort_at(pp, tau)]:
            v, st = decide(vid, kind, tau, t)
            if v is None:
                note(tau, t, vid, "redundant" if vid in st["prog"] else "abstain", st["h"], st["E"])
                continue
            if v[1] is not None:
                first_vote.setdefault(v[1], t)
            landing[land(pp, t)].append((v, tau, t))

    for s in range(1, S + 1):
        for tau, t, j in ticks_of_slot(pp, s):
            if j == 0:
                vote_tick(tau, t)
        before = states[s - 1]
        got = landing.pop(s, [])
        for v, tau, t in got:
            note(tau, t, v[0], ex_status(v, before), v[1], v[2])
        states[s] = transition(pp, "EX", before, [v for v, _, _ in got], s, W, total, ev,
                               s * pp.slot_s)
        for tau, t, j in ticks_of_slot(pp, s):
            if j > 0:
                vote_tick(tau, t)

    entry, picks = {1: 0}, [(0, 0)]
    for s in range(1, S + 1):
        if states[s]["h"] != states[s - 1]["h"]:
            entry[states[s]["h"]] = s
            picks.append((s * pp.slot_s, s))
    jt = {e[2]: e[1] for e in ev if e[0] == "J"}
    cps = [dict(id=h, target_slot=E, picked_at=float(E * pp.slot_s),
                first_vote_at=None if h not in first_vote else float(first_vote[h]),
                justified_at=None if h not in jt else float(jt[h]))
           for h, E in sorted(entry.items())]
    jw = sorted(t for t in jt.values() if in_window(pp, t))
    rph = (jw[-1] - jw[0]) / (len(jw) - 1) / pp.round_s if len(jw) > 1 else float("nan")
    name = "ex-instant" if sigma == 0 else "ex-sticky" if sigma == 1 else f"ex σ={sigma}"
    return finish(pp, name, picks, [(e[1], e[3]) for e in ev if e[0] == "J"],
                  [(e[1], e[2]) for e in ev if e[0] == "F"], cps, units, kinds,
                  dict(rph=rph, progress=sum(1 for e in ev if e[0] == "P")))


# ----------------------------------------------------------------------------- round-target
def run_rt(pp, gasper=False):
    """Casper FFG with staggered votes: the checkpoint of round r is the head (or confirmed block)
    visible at round r's first unit; round-r votes name (source = latest justified round < r in
    the voter's view, target = cp_r); cp_r is justified at 2/3; cp_{r-1} is finalized when 2/3 of
    round-r votes with source r-1 have landed (k = 1).
    gasper=True (sensitivity): the source is pinned to the view at round r's first unit, as
    Gasper's current_justified_checkpoint is per epoch, and k = 2 finalization is added
    (cp_{r-2} final when cp_{r-1} is justified and 2/3 of round-r votes have source r-2)."""
    hon, total = round(pp.p * W0), pp.C * W0
    S = pp.slots
    cp, picked, first_vote = {0: 0}, {0: 0}, {}
    jt, ft = {0: 0}, {0: 0}
    known = [0] * (S + 1)                                 # latest justified round after block s
    tally, link = defaultdict(int), defaultdict(int)
    landing = defaultdict(list)
    units, kinds = {}, defaultdict(int)
    old_src = defaultdict(int)                            # round -> votes with source < r - 1

    def vote(tau, t):
        r = tau // pp.C
        if r == 0:
            return                                        # round 0 = genesis checkpoint
        if r not in cp:
            tr = r * pp.round_s
            cp[r] = head_slot(pp, tr) if pp.mode == "head" else conf_slot(pp, tr)
            picked[r] = tr
        tv = r * pp.round_s if gasper else t
        vs = head_slot(pp, tv) if pp.mode == "head" else conf_slot(pp, tv)
        src = min(known[vs], r - 1)
        if src < r - 1:
            old_src[r] += 1
        first_vote.setdefault(r, t)
        landing[land(pp, t)].append((r, src))
        if in_window(pp, t):
            kinds["timely"] += hon
        units[tau] = unit_rec(pp, tau, t, "timely", r, cp[r])

    for s in range(1, S + 1):
        for tau, t, j in ticks_of_slot(pp, s):
            if j == 0:
                vote(tau, t)
        t0 = s * pp.slot_s
        for r, src in landing.pop(s, []):
            tally[r] += hon
            link[(src, r)] += hon
            if r not in jt and quorum(tally[r], total):
                jt[r] = t0
            if src == r - 1 and src not in ft and quorum(link[(src, r)], total):
                ft[src] = t0
        if gasper:                                        # k = 2: cp_{r-1} justified in between
            for (src, r), w in link.items():
                if src == r - 2 and src not in ft and r - 1 in jt and quorum(w, total):
                    ft[src] = t0
        known[s] = max(jt)
        for tau, t, j in ticks_of_slot(pp, s):
            if j > 0:
                vote(tau, t)
    assert all(r - 1 in jt for r in jt if r > 0), "rounds justified out of order"
    cps = [dict(id=r, target_slot=cp[r], picked_at=float(picked[r]),
                first_vote_at=None if r not in first_vote else float(first_vote[r]),
                justified_at=None if r not in jt else float(jt[r])) for r in sorted(cp)]
    lo, hi = measure_window(pp)
    rr = [r for r in cp if lo <= cp[r] < hi]
    info = dict(direct=sum(1 for r in rr if r in ft) / max(1, len(rr)),
                old_src=sum(old_src[r] for r in rr) / max(1, len(rr)))
    return finish(pp, "round-target (Gasper)" if gasper else "round-target",
                  [(picked[r], cp[r]) for r in cp],
                  [(jt[r], cp[r]) for r in jt], [(ft[r], cp[r]) for r in ft], cps, units,
                  kinds, info)


# ----------------------------------------------------------------------------- px-sticky
def run_pxs(pp):
    """Prefix counting with round-aligned (sticky) heights. A round-r vote names the voter's head
    (or confirmed block) at vote time, floored at E_r = the last block before round r. J*_r = the
    deepest block with 2/3 of round r's landed votes at or after it, recomputed per block and
    final at the round's last inclusion. Each vote also carries its source = the round-(r-1) J*
    known on its view (else an older round's). The deepest block X with 2/3 of round r's votes
    carrying round-(r-1) sources at or after X is finalized (k = 1, prefix)."""
    hon, total = round(pp.p * W0), pp.C * W0
    S = pp.slots
    tw = defaultdict(lambda: defaultdict(int))            # round -> target slot -> weight
    sw = defaultdict(lambda: defaultdict(int))            # round -> source slot -> weight
    jh, jk = {0: [(0, 0)]}, {0: [0]}                      # round -> [(block, J*)] as J* deepens
    fstar = {}
    jev, fev, picks = [(0, 0)], [(0, 0)], []
    landing = defaultdict(list)
    units, kinds = {}, defaultdict(int)
    old_src = defaultdict(int)

    def jstar_at(r, vs):
        ks = jk.get(r)
        if not ks:
            return None
        i = bisect.bisect_right(ks, vs)
        return jh[r][i - 1][1] if i else None

    def quantile(dist):
        acc = 0
        for x in sorted(dist, reverse=True):
            acc += dist[x]
            if quorum(acc, total):
                return x
        return None

    def vote(tau, t):
        r = tau // pp.C
        if r == 0:
            return
        vs = head_slot(pp, t) if pp.mode == "head" else conf_slot(pp, t)
        T = max(cdiv(r * pp.round_s, pp.slot_s) - 1, vs)
        sr = r - 1
        sJ = jstar_at(sr, vs)
        while sJ is None:
            sr -= 1
            sJ = jstar_at(sr, vs)
        if sr < r - 1:
            old_src[r] += 1
        picks.append((t, T))
        landing[land(pp, t)].append((r, T, sr, sJ))
        if in_window(pp, t):
            kinds["timely"] += hon
        units[tau] = unit_rec(pp, tau, t, "timely", r, T)

    for s in range(1, S + 1):
        for tau, t, j in ticks_of_slot(pp, s):
            if j == 0:
                vote(tau, t)
        t0 = s * pp.slot_s
        touched = set()
        for r, T, sr, sJ in landing.pop(s, []):
            tw[r][T] += hon
            if sr == r - 1:
                sw[r][sJ] += hon
            touched.add(r)
        for r in sorted(touched):
            J = quantile(tw[r])
            if J is not None and (r not in jh or J > jh[r][-1][1]):
                jh.setdefault(r, []).append((s, J))
                jk.setdefault(r, []).append(s)
                jev.append((t0, J))
            F = quantile(sw[r])
            if F is not None and F > fstar.get(r - 1, -1):
                fstar[r - 1] = F
                fev.append((t0, F))
        for tau, t, j in ticks_of_slot(pp, s):
            if j > 0:
                vote(tau, t)

    pick_t = [t for t, _ in picks]
    pick_T = [T for _, T in picks]
    cps, deep = [], []
    lo, hi = measure_window(pp)
    for r in sorted(jh):
        if r == 0:
            continue
        (s1, J1), (s2, J2) = jh[r][0], jh[r][-1]
        i = bisect.bisect_left(pick_T, J2)
        tp = float(pick_t[i]) if i < len(pick_t) else None
        cps.append(dict(id=r, target_slot=J2, picked_at=tp, first_vote_at=tp,
                        justified_at=float(s2 * pp.slot_s), first_quorum_at=float(s1 * pp.slot_s),
                        first_quorum_slot=J1))
        if lo <= J2 < hi:
            deep.append((J2 - J1, (s2 - s1) * pp.slot_s, s1 * pp.slot_s - J1 * pp.slot_s,
                         r in fstar and fstar[r] == J2))
    n = max(1, len(deep))
    info = dict(deepen_slots=sum(d[0] for d in deep) / n, deepen_s=sum(d[1] for d in deep) / n,
                age_first_q=sum(d[2] for d in deep) / n, direct=sum(d[3] for d in deep) / n,
                deepen_max=max((d[0] for d in deep), default=0),
                old_src=sum(old_src[c["id"]] for c in cps if lo <= c["target_slot"] < hi) / n)
    return finish(pp, "px-sticky", picks, jev, fev, cps, units, kinds, info)


# ----------------------------------------------------------------------------- rf (instrumented)
def run_rf2(pp):
    """run_rf (honest only, no splits) with per-block / per-position / per-unit records."""
    vals, total = make_validators(pp)
    W = {v[0]: v[2] for v in vals}
    coh = {v[0]: v[1] for v in vals}
    by_cohort = defaultdict(list)
    for vid, c, w, kind in vals:
        if kind != "adv":
            by_cohort[c].append((vid, kind))
    S = pp.slots
    d = pp.rf_delta

    def X(q):
        return q // pp.ups - d

    def supports(T, q):
        x = X(q)
        return True if x <= 0 else T >= x - 1

    justified, known = {0: 0}, {0: 0}
    tally = defaultdict(int)
    lockw = defaultdict(lambda: defaultdict(int))
    allv = defaultdict(lambda: defaultdict(int))
    fin_time, landing, pend = {}, defaultdict(list), []
    picks, units, kinds = [], {}, defaultdict(int)

    def decide(vid, tau, t):
        hs = head_slot(pp, t)
        src = hs if pp.mode == "head" else conf_slot(pp, t)
        T = min(src, max(0, X(tau) - 1))
        picks.append((t, T))
        if in_window(pp, t):
            kinds["timely"] += W[vid]
        units[tau] = unit_rec(pp, tau, t, "timely", tau, T)
        return (vid, tau, T, known[src])

    for s in range(1, S + 1):
        t0 = s * pp.slot_s
        for tau, t, j in ticks_of_slot(pp, s):
            if j == 0:
                for vid, kind in by_cohort[cohort_at(pp, tau)]:
                    landing[land(pp, t)].append(decide(vid, tau, t))
        newly = []
        for vid, tau, T, src in landing.pop(s, []):
            lo_ = prev_tick(pp, coh[vid], tau)
            for q in range(max(1, lo_ + 1), tau + 1):
                allv[q][(src, T)] += W[vid]
                for p in pend:
                    if p >= q or p > src:
                        break
                    if supports(T, p):
                        lockw[p][q] += W[vid]
                if q not in justified and src < q and supports(T, q):
                    tally[q] += W[vid]
                    if quorum(tally[q], total):
                        justified[q] = t0
                        newly.append(q)
        for q in newly:
            for q2 in range(q + 1, q + 2 * pp.C + 1):
                for (src, T), w in allv[q2].items():
                    if src >= q and supports(T, q):
                        lockw[q][q2] += w
            bisect.insort(pend, q)
        known[s] = max(justified)
        done = []
        for p in pend:
            p2 = p + 1
            while p2 in justified and p2 <= p + 2 * pp.C:
                if quorum(lockw[p][p2], total):
                    fin_time[p] = t0
                    done.append(p)
                    break
                p2 += 1
        for p in done:
            pend.remove(p)
            lockw.pop(p, None)
        for tau, t, j in ticks_of_slot(pp, s):
            if j > 0:
                for vid, kind in by_cohort[cohort_at(pp, tau)]:
                    landing[land(pp, t)].append(decide(vid, tau, t))

    bd = lambda q: max(0, X(q) - 1)
    last = S * pp.ups
    cps = [dict(id=q, target_slot=bd(q), picked_at=float(q * pp.unit_s),
                first_vote_at=float(q * pp.unit_s),
                justified_at=None if q not in justified else float(justified[q]))
           for q in range(pp.ups, last)]
    lo, hi = measure_window(pp)
    gaps = sum(1 for q in range(lo * pp.ups, hi * pp.ups) if q not in justified)
    return finish(pp, f"rf δ={d}", picks, [(justified[q], bd(q)) for q in justified],
                  [(fin_time[p], bd(p)) for p in fin_time], cps, units, kinds, dict(gaps=gaps))


# ----------------------------------------------------------------------------- dispatch + metrics
DESIGNS = ("ex-instant", "ex-sticky", "round-target", "px-sticky", "rf")

TARGET_RULE = {
    "ex-instant": "Entry of the next height = the block whose votes complete the 2/3 quorum, fixed "
                  "in that block; voters switch at their next unit.",
    "ex-sticky": "Same entry, fixed in the quorum block; voters keep the state seen at the round's "
                 "first unit, so the entry is first voted in the next round.",
    "round-target": "Checkpoint of round r = the head visible at the round's first unit (unit 23r); "
                    "every round-r vote names it.",
    "px-sticky": "Each vote names the voter's head at vote time; round r justifies the deepest "
                 "block with 2/3 of round r's votes at or after it, final at the round's last "
                 "inclusion.",
    "rf": "Every unit is a position; its target is the last block with slot < slot(unit) - δ "
          "(δ = 1).",
}

LABEL = {
    "ex-instant": "Floating heights, instant switch (Mikhail's draft)",
    "ex-sticky": "Floating heights, sticky voters (round-start state)",
    "round-target": "Round-aligned target (Casper FFG, staggered votes)",
    "px-sticky": "Prefix counting, round-aligned heights",
    "rf": "Rolling FFG (δ = 1)",
}

PICK_SHORT = {
    "ex-instant": "quorum block; voted from the next unit",
    "ex-sticky": "quorum block; voted from the next round",
    "round-target": "head at the round's first unit",
    "px-sticky": "head at each vote; J*_r = 2/3-quantile",
    "rf": "last block with slot < slot(u) − δ",
}

CLOSED = {   # ideal model: (to inclusion, inclusion -> justified, justified -> finalized), rounds
    "ex-instant": ((1, 3), (2, 3), (2, 3), "5/3"),
    "ex-sticky": ((1, 2), (1, 1), (1, 1), "5/2"),
    "round-target": ((1, 2), (2, 3), (1, 1), "13/6"),
    "px-sticky": ((0, 1), (8, 9), (17, 18), "11/6"),
    "rf": ((0, 1), (2, 3), (2, 3), "4/3"),
}


def run_design(pp, design, delta=1):
    if design == "ex-instant":
        return run_ex(pp, 0.0)
    if design == "ex-sticky":
        return run_ex(pp, 1.0)
    if design == "round-target":
        return run_rt(pp)
    if design == "px-sticky":
        return run_pxs(pp)
    if design == "rf":
        return run_rf2(replace(pp, rf_delta=delta))
    raise ValueError(design)


def stats(res):
    pp = res["pp"]
    lo, hi = measure_window(pp)
    L, D1, D2, D3, unfin, bad = [], [], [], [], 0, 0
    for b in range(lo, hi):
        tb = b * pp.slot_s
        pk, js, fn = res["pick"][b], res["just"][b], res["fin"][b]
        if fn is None or js is None or pk is None:
            unfin += 1
            continue
        if not (tb <= pk <= js <= fn):
            bad += 1
        L.append(fn - tb)
        D1.append(pk - tb)
        D2.append(js - pk)
        D3.append(fn - js)
    m = lambda xs: sum(xs) / len(xs) if xs else float("nan")
    return dict(lag=summary(L), to_incl=m(D1), incl_just=m(D2), just_fin=m(D3), n=len(L),
                unfin=unfin, bad=bad, lags=L)


def depth(res):
    """Mean target age (s) at pick / first vote / justification / finalization over the
    checkpoints whose target lies in the measurement window."""
    pp = res["pp"]
    lo, hi = measure_window(pp)
    rows = [c for c in res["cps"] if lo <= c["target_slot"] < hi]

    def age(key):
        xs = [c[key] - c["target_slot"] * pp.slot_s for c in rows if c.get(key) is not None]
        return sum(xs) / len(xs) if xs else float("nan")
    return dict(pick=age("picked_at"), vote=age("first_vote_at"), just=age("justified_at"),
                fin=age("finalized_at"), n=len(rows))


def kind_share(res):
    tot = sum(res["kinds"].values())
    return {k: res["kinds"].get(k, 0) / tot if tot else float("nan") for k in KINDS}


# ----------------------------------------------------------------------------- FRC reporting
ORIG_ALL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "..",
                        "..", "ff", "prefix-consensus", "sim", "all_output.md")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")


def fs(x, R=92):
    """seconds and rounds of R s"""
    return "—" if x is None or x != x else f"{x:.0f} s ({x / R:.2f})"


def frac(t):
    a, b = t
    return a / b


def closed_cell(d):
    c = CLOSED[d]
    return f"{c[3]} = {frac(c[0]) + frac(c[1]) + frac(c[2]):.2f}"


def row_name(d, mode, delta, gasper=False):
    n = f"rf δ={delta}" if d == "rf" else d
    if gasper:
        n += " (Gasper: pinned source, k ≤ 2)"
    return n + ("" if mode == "head" else " · conf")


def lagline(name, pick, res, R, closed):
    s = stats(res)
    assert s["bad"] == 0, (name, s["bad"])
    if s["n"] == 0:                                       # nothing in the window finalizes
        return (f"| {name} | {pick} | — | — | — | **never finalizes** (justifies every round; "
                f"k = 1 links split by stale sources) | — | — | — | {closed} |")
    assert s["unfin"] == 0, (name, s["unfin"])
    L = s["lag"]
    return (f"| {name} | {pick} | {fs(s['to_incl'], R)} | {fs(s['incl_just'], R)} | "
            f"{fs(s['just_fin'], R)} | **{fs(L['mean'], R)}** | {fs(L['min'], R)} | "
            f"{fs(L['p95'], R)} | {fs(L['max'], R)} | {closed} |")


LAG_HDR = ("| design | target picked | E[time to inclusion] | inclusion → justified | justified → "
           "finalized | **E[lag]** | min | p95 | max | ideal closed form (rounds) |\n"
           "|---|---|---|---|---|---|---|---|---|---|")


def frc_table(p):
    R = FRC.round_s
    print(f"#### p = {p} (online honest stake; seconds, with rounds of {R} s in brackets) [sim]\n")
    print(LAG_HDR)
    for mode in ("head", "conf"):
        pm = replace(FRC, p=p, mode=mode)
        for d in DESIGNS:
            deltas = ((0, 1, 2) if mode == "head" else (1, 2)) if d == "rf" else (None,)
            for delta in deltas:
                res = run_design(pm, d, delta)
                print(lagline(row_name(d, mode, delta), PICK_SHORT[d], res, R, closed_cell(d)))
            if d == "round-target":
                res = run_rt(pm, gasper=True)
                print(lagline(row_name(d, mode, None, True), "as round-target; source pinned "
                              "at the round's first unit", res, R, closed_cell(d)))
    for name, pk, c in (("DC today (closed form, ideal)", "entry fixed by the previous round's "
                         "quorum; everyone attests once per round at a_r",
                         ((1, 2), (1, 1), (1, 1), "5/2")),
                        ("CHAIN-FG (closed form, ideal; not deployable)", "window-aligned; the "
                         "first quorum already finalizes", ((1, 2), (2, 3), (0, 1), "7/6"))):
        a, b, e = frac(c[0]) * R, frac(c[1]) * R, frac(c[2]) * R
        print(f"| {name} | {pk} | {fs(a, R)} | "
              f"{fs(b, R)} | {fs(e, R)} | **{fs(a + b + e, R)}** | — | — | — | {c[3]} [derived] |")
    print()


def depth_table(p):
    R = FRC.round_s
    print(f"#### p = {p}, head mode [sim]\n")
    print("| design | age at pick | age at first vote | age at justification | age at finalization "
          "| rounds per height | honest votes: timely / stale / redundant |\n"
          "|---|---|---|---|---|---|---|")
    pm = replace(FRC, p=p)
    for d in DESIGNS:
        res = run_design(pm, d, 1)
        dp, ks = depth(res), kind_share(res)
        rph = res["info"].get("rph")
        rph = f"{rph:.2f}" if rph is not None else ("1 (round-aligned)" if d in ("round-target", "px-sticky")
                                                    else "1/23 (a position per unit)")
        print(f"| {row_name(d, 'head', 1 if d == 'rf' else None)} | {dp['pick']:.0f} s | "
              f"{dp['vote']:.0f} s | {dp['just']:.0f} s | {dp['fin']:.0f} s | {rph} | "
              f"{100 * ks['timely']:.0f} / {100 * ks['stale']:.0f} / {100 * ks['redundant']:.0f} % |")
    print()


def px_table():
    print("| p | J* age at the first quorum | deepening after the first quorum: mean (max) | "
          "J*_r final finalized directly | stale-source units per round | round-target: "
          "finalized directly, stale-source units |\n|---|---|---|---|---|---|")
    for p in PS:
        pm = replace(FRC, p=p)
        i, j = run_pxs(pm)["info"], run_rt(pm)["info"]
        print(f"| {p} | {i['age_first_q']:.0f} s | {i['deepen_slots']:.2f} slots = {i['deepen_s']:.0f} s "
              f"({i['deepen_max']} slots) | {100 * i['direct']:.0f} % | {i['old_src']:.2f} | "
              f"{100 * j['direct']:.0f} %, {j['old_src']:.2f} |")
    print()


def sigma_table():
    R = FRC.round_s
    sig = (0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.5, 1.0)
    print("| σ (sticky share) | " + " | ".join(f"p = {p}" for p in PS) + " |\n|---|" +
          "---|" * len(PS))
    for sg in sig:
        cells = []
        for p in PS:
            res = run_ex(replace(FRC, p=p), sg)
            st, ks = stats(res), kind_share(res)
            cells.append(f"{fs(st['lag']['mean'], R)}; {res['info']['rph']:.2f} r/h; "
                         f"{100 * ks['stale']:.0f} % stale")
        tag = " (ex-instant)" if sg == 0 else " (ex-sticky)" if sg == 1 else ""
        print(f"| {sg}{tag} | " + " | ".join(cells) + " |")
    print()


def ideal_table():
    print("| design | C | E[time to inclusion] | inclusion → justified | justified → finalized | "
          "**E[lag]** | min / max | closed form (continuum) |\n|---|---|---|---|---|---|---|---|")
    for d in DESIGNS:
        for C in (23, 230):
            pp = replace(IDEAL, C=C, rounds=60 if C == 23 else 24)
            res = run_design(pp, d, 0)
            s = stats(res)
            assert s["bad"] == 0 and s["unfin"] == 0
            R = pp.round_s
            c = CLOSED[d]
            cf = (f"{c[0][0]}/{c[0][1]} + {c[1][0]}/{c[1][1]} + {c[2][0]}/{c[2][1]} = {c[3]} = "
                  f"{frac(c[0]) + frac(c[1]) + frac(c[2]):.3f}")
            print(f"| {d if d != 'rf' else 'rf δ=0'} | {C} | {s['to_incl'] / R:.3f} | {s['incl_just'] / R:.3f} | "
                  f"{s['just_fin'] / R:.3f} | **{s['lag']['mean'] / R:.3f}** | "
                  f"{s['lag']['min'] / R:.3f} / {s['lag']['max'] / R:.3f} | {cf} |")
    print("\n(Ideal: one block per 4 s unit, no aggregation or visibility delay, full participation; "
          "rounds of C units. Block births are discrete, so C = 23 carries rounding; C = 230 "
          "approaches the continuum.)\n")


def checks():
    """Reproduction and engine cross-checks."""
    print("| check | result |\n|---|---|")
    out = []
    try:
        orig = open(ORIG_ALL).read()
        i, j = orig.index("### S0"), orig.index("### S1")
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            s0()
        out.append(("prefix_sim S0 table (C = 24) reproduced byte for byte by this copy",
                    buf.getvalue() == orig[i:j]))
    except OSError:
        out.append(("prefix_sim S0 table (C = 24): original all_output.md not found", None))
    n_ex = n_rf = 0
    ok_ex = ok_rf = True
    for mode in ("head", "conf"):
        for p in PS:
            pp = replace(FRC, p=p, mode=mode)
            r = run_ex(pp, 0.0)
            ok_ex &= run_heights(pp, "EX")["lags"] == block_lags(pp, lambda b: r["fin"][b], pp.slots)[0]
            n_ex += 1
            for d in (0, 1, 2):
                q = replace(pp, rf_delta=d)
                r2 = run_rf2(q)
                ok_rf &= run_rf(q)["lags"] == block_lags(q, lambda b: r2["fin"][b], q.slots)[0]
                n_rf += 1
    out.append((f"ex-instant engine = prefix_sim run_heights(EX(2R)) per-block lags, {n_ex} FRC configs", ok_ex))
    out.append((f"rf engine = prefix_sim run_rf per-block lags, {n_rf} FRC configs", ok_rf))
    pp = FRC
    jslot = {}
    for r in range(2, pp.rounds - 1):
        E = cdiv(r * pp.round_s, pp.slot_s) - 1
        tg = sorted((max(E, head_slot(pp, tau * pp.unit_s)) for tau in range(r * pp.C, (r + 1) * pp.C)),
                    reverse=True)
        jslot[r] = tg[cdiv(2 * pp.C, 3) - 1]
    mine = {c["id"]: c["target_slot"] for c in run_pxs(pp)["cps"]}
    out.append(("px-sticky final J*_r = prefix_sim round-close PX J_r (p = 1, head), all rounds",
                all(mine.get(r) == jslot[r] for r in jslot)))
    for name, ok in out:
        print(f"| {name} | {'yes' if ok else ('n/a' if ok is None else '**NO**')} |")
    print()


def headline():
    R = FRC.round_s
    rows = [("ex-instant", None), ("ex-sticky", None), ("round-target", None), ("px-sticky", None),
            ("rf", 1), ("rf", 0)]
    print("| design (head mode) | " + " | ".join(f"p = {p}" for p in PS) +
          " | ideal closed form |\n|---|" + "---|" * (len(PS) + 1))
    base = {}
    for d, delta in rows:
        cells = []
        for p in PS:
            st = stats(run_design(replace(FRC, p=p), d, delta))
            m_ = st["lag"]["mean"]
            if d == "ex-instant":
                base[p] = m_
            cells.append(fs(m_, R) + ("" if d == "ex-instant" else f" [{m_ - base[p]:+.0f}]"))
        print(f"| {row_name(d, 'head', delta)} | " + " | ".join(cells) + f" | {closed_cell(d)} |")
    print(f"| DC today (closed form, ideal) | " + " | ".join(fs(2.5 * R, R) for _ in PS) +
          " | 5/2 = 2.50 |\n")
    print("(E[lag] over a uniformly random block; [±s] = difference to ex-instant at the same p.)\n")


def needed_cohorts(pp):
    hon = round(pp.p * W0)
    return next(k for k in range(1, pp.C + 1) if quorum(k * hon, pp.C * W0))


def margin_table():
    """When is round r's 2/3 quorum visible, relative to round r+1's first unit?"""
    print("| p | cohorts needed k | k-th unit starts | quorum block at (s into round r; phase r mod 3 "
          "= 0 / 1 / 2) | visible to head voters before round r+1? | round-(r+1) units cast "
          "before it is visible: head / conf |\n|---|---|---|---|---|---|")
    for p in PS:
        pp = replace(FRC, p=p)
        k = needed_cohorts(pp)
        lands, vis, nh, nc = [], [], [], []
        for r in (3, 4, 5):
            t_k = (r * pp.C + k - 1) * pp.unit_s
            qs = land(pp, t_k)
            off = qs * pp.slot_s - r * pp.round_s
            lands.append(off)
            th, tc = qs * pp.slot_s + max(pp.vis, 1), (qs + 1) * pp.slot_s + pp.conf
            nxt = (r + 1) * pp.C
            nh.append(sum(1 for u in range(nxt, nxt + pp.C) if u * pp.unit_s < th))
            nc.append(sum(1 for u in range(nxt, nxt + pp.C) if u * pp.unit_s < tc))
            vis.append("yes" if nh[-1] == 0 else "no")
        print(f"| {p} | {k} | {4 * (k - 1)} s | {' / '.join(f'{x} s' for x in lands)} | "
              f"{' / '.join(vis)} | {' / '.join(map(str, nh))} ; {' / '.join(map(str, nc))} |")
    print()


def frc_all():
    print("### Headline: E[lag], head mode [sim]\n")
    headline()
    print("### Checks\n")
    checks()
    print("### Ideal model vs closed forms [sim vs derived]\n")
    ideal_table()
    print("### FRC latency, all designs\n")
    for p in PS:
        frc_table(p)
    print("### Target depth (mean target age, s)\n")
    for p in PS:
        depth_table(p)
    print("### Round boundary: when round r's quorum becomes visible [calc]\n")
    margin_table()
    print("### px-sticky: how far J* deepens after the first quorum [sim]\n")
    px_table()
    print("### Mixed voters: share σ of honest stake sticky, the rest instant (E[lag]; rounds per "
          "height; stale share of honest votes) [sim]\n")
    sigma_table()


# ----------------------------------------------------------------------------- traces
def r3(x):
    return None if x is None else round(float(x), 3)


def traces(path=None):
    path = path or os.path.join(OUT_DIR, "traces.json")
    pp0 = FRC
    t0 = 12 * pp0.round_s                                  # round 12 starts on slot 92 (t = 1104 s)
    t1 = t0 + 6 * pp0.round_s
    assert t0 % pp0.slot_s == 0 and t1 % pp0.slot_s == 0
    lo, hi = measure_window(pp0)
    assert lo * pp0.slot_s <= t0 and t1 <= hi * pp0.slot_s
    out = {"meta": {"C": pp0.C, "unit_s": pp0.unit_s, "slot_s": pp0.slot_s, "round_s": pp0.round_s,
                    "agg_s": pp0.agg, "vis_s": pp0.vis, "mode": pp0.mode}, "runs": []}
    for p in (1.0, 0.8):
        pp = replace(FRC, p=p)
        designs = {}
        for d in DESIGNS:
            res = run_design(pp, d, 1)
            st = stats(res)
            b0, b1 = t0 // pp.slot_s, t1 // pp.slot_s
            units = [dict(u, t=r3(u["t"])) for _, u in sorted(res["units"].items())
                     if t0 <= u["t"] < t1]
            blocks = [dict(slot=b, t=r3(b * pp.slot_s), justified_at=r3(res["just"][b]),
                           finalized_at=r3(res["fin"][b])) for b in range(b0, b1)]
            cps = []
            for c in res["cps"]:
                start = min(c["target_slot"] * pp.slot_s,
                            c["picked_at"] if c["picked_at"] is not None else float("inf"))
                end = c["finalized_at"] if c["finalized_at"] is not None else float("inf")
                if start < t1 and end >= t0:
                    cps.append({k: (r3(c[k]) if k.endswith("_at") else c[k])
                                for k in ("id", "target_slot", "picked_at", "first_vote_at",
                                          "justified_at", "finalized_at")})
            L = st["lag"]
            designs[d] = {
                "label": LABEL[d], "target_rule": TARGET_RULE[d], "units": units, "blocks": blocks,
                "checkpoints": cps,
                "lag": {"min": r3(L["min"]), "mean": r3(L["mean"]), "p95": r3(L["p95"]),
                        "max": r3(L["max"]),
                        "by_birth": [[r3(b * pp.slot_s), r3(res["fin"][b] - b * pp.slot_s)]
                                     for b in range(b0, b1)]},
                "decomp": {"to_inclusion": r3(st["to_incl"]), "incl_to_just": r3(st["incl_just"]),
                           "just_to_final": r3(st["just_fin"])}}
        out["runs"].append({"p": p, "t0": t0, "t1": t1, "designs": designs})
    with open(path, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {os.path.relpath(path)} ({os.path.getsize(path) / 1024:.0f} KiB)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("what", choices=["all", "traces", "headline", "checks", "ideal", "frc",
                                     "depth", "margin", "px", "sigma", "sanity", "s0", "s1", "s2",
                                     "s3"])
    a = ap.parse_args()
    legacy = dict(sanity=sanity, s0=s0, s1=s1, s2=s2, s3=s3)
    fns = dict(checks=checks, ideal=ideal_table, frc=lambda: [frc_table(p) for p in PS],
               depth=lambda: [depth_table(p) for p in PS], px=px_table, sigma=sigma_table,
               traces=traces, headline=headline, margin=margin_table, all=frc_all)
    (legacy.get(a.what) or fns[a.what])()


if __name__ == "__main__":
    main()
