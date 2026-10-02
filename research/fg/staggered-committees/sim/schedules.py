#!/usr/bin/env python3
"""
schedules.py -- Lane A of the staggered-FG-committees study (schedule, position,
composition, reward proxy, adversary). Companion to ../analysis/schedule.md.

Python 3 standard library only. Every random choice is drawn from random.Random
seeded with a fixed string, so the output is identical on every run. Every number
quoted in schedule.md is printed by this script (tables E1-E13).

    python3 sim/schedules.py            # full run (~1 min on a laptop)
    python3 sim/schedules.py --quick    # fewer trials, for development only

Tables: E1 steady-state rounds/height (C x L x p grid), E2 drop transients,
E3 flapping, E4 gap lemma, E5 stake models, E6 heavy-first / tail-light,
E7 per-validator stale/pivotal shares, E8 synthetic-registry composition,
E9 churn and exit-induced re-seating, E10 reward proxy, E11 era-boundary cost,
E12 adversary (consolidation targeting, seed grinding, VRF), E13 the
recommended schedule for every C.

No mainnet registry snapshot is available locally; E8 uses a synthetic registry.

MODEL (brief section 4, extended)
---------------------------------
* A round has T ticks; C of them are vote units (one per cohort). Unit model
  (default, as in the brief's planning sims): T = C, unit u = tick u. Q17 tick
  model (table E1c only): 4 s ticks, idle ticks where no unit starts
  (pipelined-units/README.md:24,57-62,146).
* Every validator has exactly one vote opportunity per round, at its seat
  (the unit its schedule assigns it in that round).
* At its seat, an online validator votes for the latest height it KNOWS, if it
  has not voted for that height yet. Heights justified at ticks <= t-L-1 are
  known at tick t (switch lag L, in ticks).
* A height is justified at the end of the first tick at which the stake that
  voted for it reaches 2/3 of total stake (mk spec has_quorum: support*3 >=
  total*2, mk-dc-beacon-chain.md:471-486). The next height starts immediately
  ("instant switch", mk spec :114-117).
* A vote for a height that is already justified ("stale") or a second vote for
  the same height ("redundant") does not help progress.
"""
import math
import random
import sys
import time
import bisect
from array import array
from collections import Counter, defaultdict

QUICK = "--quick" in sys.argv
T_START = time.time()

# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------

def pct(xs, q):
    """Linear-interpolated percentile, q in [0,1]."""
    if not xs:
        return float("nan")
    s = sorted(xs)
    k = (len(s) - 1) * q
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] + (s[c] - s[f]) * (k - f)


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def f3(x):
    if isinstance(x, str):
        return x
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    if isinstance(x, float) and math.isinf(x):
        return "inf"
    return f"{x:.3f}"


def f2(x):
    if isinstance(x, str):
        return x
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    if isinstance(x, float) and math.isinf(x):
        return "inf"
    return f"{x:.2f}"


def f1(x):
    if isinstance(x, str):
        return x
    if isinstance(x, float) and math.isinf(x):
        return "inf"
    return f"{x:.1f}"


def pc(x, d=2):
    """fraction -> percent string"""
    if isinstance(x, str):
        return x
    return f"{100 * x:.{d}f}%"


def table(tag, title, header, rows, note=None):
    print()
    print(f"#### {tag} — {title}")
    if note:
        for line in note.strip().splitlines():
            print(f"> {line}")
    print()
    print("| " + " | ".join(header) + " |")
    print("|" + "|".join(["---"] * len(header)) + "|")
    for r in rows:
        print("| " + " | ".join(str(x) for x in r) + " |")
    sys.stdout.flush()


def chunk_bounds(n, C):
    return [(u * n) // C for u in range(C + 1)]


# ----------------------------------------------------------------------------
# schedule families
# ----------------------------------------------------------------------------
# A schedule maps round r -> members(r): a list of C lists (seat order) of
# validator ids. Ids 0..n-1 are positions in the index list (latency sims use a
# gap-free registry with equal or iid stake; composition sims, E8, use a
# realistic registry).

class Sched:
    state_free = True   # membership is a pure function of (index list, round[, old seed])
    name = "?"

    def __init__(self, n, C, seed="s"):
        self.n, self.C, self.seed = n, C, seed

    def members(self, r):
        raise NotImplementedError

    def seats(self, r):
        s = [0] * self.n
        for u, lst in enumerate(self.members(r)):
            for v in lst:
                s[v] = u
        return s


class Rotating(Sched):
    """Striping composition: cohort c = {v : v mod C == c}, fixed forever.
    Cohort c sits at seat (c + shift(r)) mod C.
      fixed:            shift = 0
      +1 per round:     shift = r
      -1 per round:     shift = -r        (direction of mk's slide, at one unit/round)
      slow +1 every K:  shift = r // K
      slow -1 every K:  shift = -(r // K)
    """

    def __init__(self, n, C, shift, name):
        super().__init__(n, C)
        self.base = [list(range(c, n, C)) for c in range(C)]
        self.shift = shift
        self.name = name

    def members(self, r):
        s = self.shift(r) % self.C
        C, b = self.C, self.base
        return [b[(u - s) % C] for u in range(C)]


class StaggeredSlow(Sched):
    """+1 every K rounds, phase-staggered: validator v (cohort v mod C, phase
    (v // C) mod K) moves at rounds r with (r + phase) % K == 0, so 1/K of every
    cohort moves each round; seat counts stay exactly balanced."""

    def __init__(self, n, C, K, name):
        super().__init__(n, C)
        self.K = K
        self.name = name

    def members(self, r):
        n, C, K = self.n, self.C, self.K
        mem = [[] for _ in range(C)]
        for v in range(n):
            mem[(v % C + (r + (v // C) % K) // K) % C].append(v)
        return mem


class Mikhail(Sched):
    """mk-dc-beacon-chain.md:853-873: committee k = list positions
    [start_k, end_k) read at offset +round (indices[(i + round) % len]); committees
    map to units in order (the spec has no committee->unit map; assumed
    contiguous, unit(k) = k*C // COMMITTEES_PER_ROUND). Validator at position j
    sits in unit floor(((j - s*r) mod n) * C / n): it slides to EARLIER seats by
    s positions per round ("shifts the validator set left by 1", :151-153)."""

    def __init__(self, n, C, s, name):
        super().__init__(n, C)
        self.s = s
        self.name = name
        self.b = chunk_bounds(n, C)

    def members(self, r):
        n, C, b = self.n, self.C, self.b
        off = (self.s * r) % n
        mem = []
        for u in range(C):
            lo, hi = b[u] + off, b[u + 1] + off
            if hi <= n:
                mem.append(list(range(lo, hi)))
            elif lo >= n:
                mem.append(list(range(lo - n, hi - n)))
            else:
                mem.append(list(range(lo, n)) + list(range(0, hi - n)))
        return mem


class BlockShuffle(Sched):
    """Fresh uniformly random balanced partition every P rounds (contiguous
    chunks of a seeded permutation, like compute_committee). P=4 = per-epoch
    reshuffle, the fradamt Simplex status quo at 8-slot rounds
    (simplex/beacon-chain.md:1186-1207, validator.md:222-226); P=1 = per round."""

    def __init__(self, n, C, P, name, seed="bs"):
        super().__init__(n, C, seed)
        self.P = P
        self.name = name
        self._cache = (None, None)

    def members(self, r):
        blk = r // self.P
        if self._cache[0] != blk:
            rng = random.Random(f"{self.seed}-{self.name}-{blk}")
            perm = list(range(self.n))
            rng.shuffle(perm)
            b = chunk_bounds(self.n, self.C)
            self._cache = (blk, [perm[b[u]:b[u + 1]] for u in range(self.C)])
        return self._cache[1]


class VRF(Sched):
    """Secret per-round lottery: each validator's seat is an independent uniform
    draw (multinomial cohort sizes). Same latency as a per-round reshuffle plus
    unbalanced cohorts; modelled only for latency/load, not for its secrecy."""
    state_free = False

    def __init__(self, n, C, name, seed="vrf"):
        super().__init__(n, C, seed)
        self.name = name

    def members(self, r):
        rng = random.Random(f"{self.seed}-{r}")
        mem = [[] for _ in range(self.C)]
        C = self.C
        for v in range(self.n):
            mem[rng.randrange(C)].append(v)
        return mem


class EraSlow(Sched):
    """H1b candidate. COMPOSITION: cohort c of era e = a seeded shuffle of the
    index list, striped (perm_e[c::C]); new seed every E rounds. POSITION:
    cohort c sits at seat (c + r // K) mod C (slow + rotation, global clock)."""

    def __init__(self, n, C, E, K, name, seed="era"):
        super().__init__(n, C, seed)
        self.E, self.K = E, K
        self.name = name
        self._cache = (None, None)

    def cohorts(self, e):
        if self._cache[0] != e:
            rng = random.Random(f"{self.seed}-{e}")
            perm = list(range(self.n))
            rng.shuffle(perm)
            self._cache = (e, [perm[c::self.C] for c in range(self.C)])
        return self._cache[1]

    def members(self, r):
        coh = self.cohorts(r // self.E)
        s = (r // self.K) % self.C
        C = self.C
        return [coh[(u - s) % C] for u in range(C)]


class Spiral(Sched):
    """Vorbit spiral finality (ethresearch 20464:169-173): reshuffle every P
    rounds, but a validator may move at most s seats LATER (it may move earlier
    arbitrarily). Implemented as a fill-from-the-back balanced draw. The
    transition matrix is doubly stochastic, so seats mix to uniform. NOT a pure
    function of (index, round): seat at block b depends on seat at block b-1."""
    state_free = False

    def __init__(self, n, C, s, P, name, R, seed="spiral"):
        super().__init__(n, C, seed)
        self.s, self.P = s, P
        self.name = name
        rng = random.Random(f"{seed}-{s}-{P}")
        seats = [v % C for v in range(n)]
        self.blocks = [self._to_mem(seats)]
        for _ in range(R // P + 2):
            seats = self._step(seats, rng)
            self.blocks.append(self._to_mem(seats))

    def _to_mem(self, seats):
        mem = [[] for _ in range(self.C)]
        for v, u in enumerate(seats):
            mem[u].append(v)
        return mem

    def _step(self, old, rng):
        n, C, s = self.n, self.C, self.s
        b = chunk_bounds(n, C)
        by_old = [[] for _ in range(C)]
        for v, u in enumerate(old):
            by_old[u].append(v)
        new = [0] * n
        pool = []
        for u in range(max(0, C - 1 - s), C):
            pool.extend(by_old[u])
        for j in range(C - 1, -1, -1):
            if j < C - 1 and j - s >= 0:
                pool.extend(by_old[j - s])
            for _ in range(b[j + 1] - b[j]):
                i = rng.randrange(len(pool))
                pool[i], pool[-1] = pool[-1], pool[i]
                new[pool.pop()] = j
        return new

    def members(self, r):
        return self.blocks[r // self.P]


class HeavyFirst(Sched):
    """Barnabe msg 1498: higher-balance validators vote earlier. Fixed order by
    effective balance (descending), count-balanced units. Reads balances, so it
    violates the state-free guard-rail; reference only."""
    state_free = False

    def __init__(self, n, C, stake, name):
        super().__init__(n, C)
        order = sorted(range(n), key=lambda v: (-stake[v], v))
        b = chunk_bounds(n, C)
        self.mem = [order[b[u]:b[u + 1]] for u in range(C)]
        self.name = name

    def members(self, r):
        return self.mem


class TailLight(Sched):
    """Pattern note fg-vote-dissemination.md:440-477: the last unit carries only
    a fraction w of the round's weight (equal stake: of the validators); the
    assignment is re-randomised every round (:474-477). Reference only."""
    state_free = False

    def __init__(self, n, C, w, name, seed="tail"):
        super().__init__(n, C, seed)
        self.w = w
        self.name = name
        last = int(round(w * n))
        rest = n - last
        self.sizes = [(rest * (u + 1)) // (C - 1) - (rest * u) // (C - 1) for u in range(C - 1)] + [last]

    def members(self, r):
        rng = random.Random(f"{self.seed}-{r}")
        perm = list(range(self.n))
        rng.shuffle(perm)
        mem, i = [], 0
        for sz in self.sizes:
            mem.append(perm[i:i + sz])
            i += sz
        return mem


def schedule_zoo(n, C, R, stake=None, era_E=100):
    """The families of the brief, in table order."""
    z = [
        Rotating(n, C, lambda r: 0, "fixed v mod C"),
        Rotating(n, C, lambda r: r, "+1 / round"),
        Rotating(n, C, lambda r: -r, "-1 / round"),
    ]
    for K in (5, 8, 10, 30, 100):
        z.append(Rotating(n, C, (lambda K: (lambda r: r // K))(K), f"slow +1 / {K}r"))
    z.append(Rotating(n, C, lambda r: -(r // 10), "slow -1 / 10r"))
    z.append(StaggeredSlow(n, C, 10, "slow +1 / 10r, staggered"))
    z.append(Mikhail(n, C, 1, "mk slide s=1"))
    z.append(Mikhail(n, C, n // C, "mk slide s=n/C"))
    z.append(BlockShuffle(n, C, 4, "epoch reshuffle (4r)"))
    z.append(BlockShuffle(n, C, 1, "round reshuffle"))
    z.append(VRF(n, C, "VRF lottery / round"))
    z.append(EraSlow(n, C, era_E, 10, f"era({era_E}r) + slow +1/10r"))
    z.append(Spiral(n, C, 1, 4, "spiral s=1 / epoch", R))
    z.append(Spiral(n, C, 2, 4, "spiral s=2 / epoch", R))
    return z


# ----------------------------------------------------------------------------
# latency simulator
# ----------------------------------------------------------------------------

def unit_ticks(C, model="unit"):
    """(T, tick->unit list). Unit model: T = C. Q17 tick model: 4 s ticks."""
    if model == "unit":
        return C, list(range(C))
    if C == 23:      # 8 slots x 3 units - 1, idle tick at [92,96) s (README:24,57-62)
        return 24, list(range(23)) + [-1]
    if C == 22:      # grid shifted by 4 s: units at +4..+88 s (README:146)
        return 24, [-1] + list(range(22)) + [-1]
    if C == 11:      # 4-slot stretch round: 4 x 3 - 1 units, 48 s (README:98, brief)
        return 12, list(range(11)) + [-1]
    if C == 8:       # one unit per 12 s slot (explainer Option 5)
        return 8, list(range(8))
    raise ValueError(C)


def simulate(sched, stake, L, R, events, T=None, utick=None, seat_stats=False):
    """Run R rounds. events = [(tick, online_bytearray), ...] sorted, events[0][0]==0.
    Returns (justification ticks, pivotal-unit counts, seat stats or None)."""
    n = len(stake)
    total = sum(stake)
    q2 = 2 * total
    C = sched.C
    if T is None:
        T, utick = C, list(range(C))
    last = [-1] * n
    ev = events
    ei = 1
    on = ev[0][1]
    nev = len(ev)
    cur = 0
    acc = 0
    lastj = -10 ** 9
    jt = []
    piv = [0] * C
    # per-validator outcome counters: timely, stale, redundant, missed, pivotal (voted timely in the
    # unit that completed the quorum)
    st = [[0] * n for _ in range(5)] if seat_stats else None
    for r in range(R):
        mem = sched.members(r)
        base = r * T
        for k in range(T):
            u = utick[k]
            if u < 0:
                continue
            t = base + k
            while ei < nev and ev[ei][0] <= t:
                on = ev[ei][1]
                ei += 1
            lst = mem[u]
            if not seat_stats:
                if lastj <= t - L - 1:
                    for v in lst:
                        if on[v] and last[v] < cur:
                            last[v] = cur
                            acc += stake[v]
                else:
                    kn = cur - 1
                    for v in lst:
                        if on[v] and last[v] < kn:
                            last[v] = kn
            else:
                tim, sta, red, mis, pvv = st
                kn = cur if lastj <= t - L - 1 else cur - 1
                timely_here = []
                for v in lst:
                    if not on[v]:
                        mis[v] += 1
                    elif last[v] >= kn:
                        red[v] += 1
                    else:
                        last[v] = kn
                        if kn == cur:
                            acc += stake[v]
                            tim[v] += 1
                            timely_here.append(v)
                        else:
                            sta[v] += 1
            if acc * 3 >= q2:
                jt.append(t)
                lastj = t
                cur += 1
                acc = 0
                piv[u] += 1
                if seat_stats:
                    for v in timely_here:
                        st[4][v] += 1
    return jt, piv, st


def durations(jt, from_tick=0, to_tick=None):
    """Durations (ticks) of heights justified in (from_tick, to_tick]."""
    out = []
    for i in range(1, len(jt)):
        if jt[i - 1] >= from_tick and (to_tick is None or jt[i] <= to_tick):
            out.append(jt[i] - jt[i - 1])
    return out


def offline_set(stake, p, rng, exact=False):
    """Random offline set leaving >= p of stake online (exact: online = quorum)."""
    n = len(stake)
    total = sum(stake)
    order = list(range(n))
    rng.shuffle(order)
    off = bytearray(n)
    if exact:
        need_on = -(-2 * total // 3)          # ceil(2/3 S)
        budget = total - need_on
    else:
        budget = int(math.floor((1 - p) * total + 1e-9))
        # never go below quorum
        budget = min(budget, total - (-(-2 * total // 3)))
    used = 0
    for v in order:
        if used + stake[v] <= budget:
            off[v] = 1
            used += stake[v]
    return off


def flags_from_off(off):
    return bytearray(1 - x for x in off)


# ----------------------------------------------------------------------------
# gap statistics (gap lemma)
# ----------------------------------------------------------------------------

def gap_stats(sched, R, stake, delta_frac, T=None, utick=None):
    """G = max over validators and consecutive rounds of the tick distance
    between consecutive vote opportunities. G_delta = the smallest g such that,
    at every round boundary, validators with gap > g hold <= delta_frac of stake."""
    C = sched.C
    if T is None:
        T, utick = C, list(range(C))
    tick_of = [None] * C
    for k, u in enumerate(utick):
        if u >= 0:
            tick_of[u] = k
    total = sum(stake)
    budget = delta_frac * total
    G = 0
    Gd = 0
    prev = sched.seats(0)
    for r in range(1, R):
        nxt = sched.seats(r)
        by_gap = defaultdict(int)
        gmax = 0
        for v in range(sched.n):
            g = T - tick_of[prev[v]] + tick_of[nxt[v]]
            by_gap[g] += stake[v]
            if g > gmax:
                gmax = g
        G = max(G, gmax)
        # smallest g with stake(gap > g) <= budget
        acc = 0
        gd = gmax
        for g in sorted(by_gap, reverse=True):
            if acc + by_gap[g] > budget:
                gd = g
                break
            acc += by_gap[g]
            gd = g - 1
        Gd = max(Gd, gd)
        prev = nxt
    return G, Gd


# ----------------------------------------------------------------------------
# stake models
# ----------------------------------------------------------------------------

def phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def clipped_lognormal_mean(mu, sigma, lo=32.0, hi=2048.0):
    a = (math.log(lo) - mu) / sigma
    b = (math.log(hi) - mu) / sigma
    mid = math.exp(mu + sigma * sigma / 2) * (phi(b - sigma) - phi(a - sigma))
    return lo * phi(a) + hi * (1 - phi(b)) + mid


def calibrate_0x02(median=238.0, target_mean=603.0):
    """'0x02-like' stake mix (brief: mean ~603, median ~238 ETH): lognormal with
    median 238 clipped to [32, 2048]; sigma by bisection on the clipped mean."""
    mu = math.log(median)
    lo, hi = 0.1, 6.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if clipped_lognormal_mean(mu, mid) < target_mean:
            lo = mid
        else:
            hi = mid
    sigma = (lo + hi) / 2
    a = (math.log(32) - mu) / sigma
    b = (math.log(2048) - mu) / sigma
    return mu, sigma, phi(a), 1 - phi(b)


MU02, SIG02, P32_02, P2048_02 = calibrate_0x02()


def stake_vector(n, model, rng):
    if model == "equal":
        return [32] * n
    if model == "0x02-like":
        out = []
        for _ in range(n):
            x = math.exp(MU02 + SIG02 * rng.gauss(0, 1))
            out.append(int(round(min(2048.0, max(32.0, x)))))
        return out
    if model == "1.5% hold ~50%":
        heavy = set(rng.sample(range(n), int(round(0.015 * n))))
        return [2048 if v in heavy else 32 for v in range(n)]
    raise ValueError(model)


STAKE_MODELS = ["equal", "0x02-like", "1.5% hold ~50%"]


# ----------------------------------------------------------------------------
# experiment helpers
# ----------------------------------------------------------------------------

def steady(sched, stake, L, R, p, seed, burn=20, T=None, utick=None, exact=False):
    """Steady-state height durations (rounds) at participation p."""
    n = len(stake)
    if T is None:
        T, utick = sched.C, list(range(sched.C))
    rng = random.Random(f"steady-{seed}")
    if p >= 1.0 and not exact:
        flags = bytearray([1] * n)
    else:
        flags = flags_from_off(offline_set(stake, p, rng, exact=exact))
    jt, piv, _ = simulate(sched, stake, L, R, [(0, flags)], T=T, utick=utick)
    D = durations(jt, from_tick=burn * T)
    return [d / T for d in D]


def subset_zoo(n, C, R):
    names = ["fixed v mod C", "+1 / round", "-1 / round", "slow +1 / 10r", "mk slide s=1",
             "mk slide s=n/C", "epoch reshuffle (4r)", "round reshuffle", "era(100r) + slow +1/10r",
             "spiral s=1 / epoch"]
    z = {s.name: s for s in schedule_zoo(n, C, R)}
    return [z[k] for k in names]


# ----------------------------------------------------------------------------
# E1  steady-state rounds/height
# ----------------------------------------------------------------------------

def e1():
    C = 23
    n = 40 * C
    R = 200 if QUICK else 320
    stake = [1] * n
    zoo = schedule_zoo(n, C, R)
    Ls = [0, 1, 2, 3, 4, 5]
    ps = [1.0, 0.9, 0.8, 0.7, 0.67]
    res = {}
    for sch in zoo:
        for p in ps:
            for L in Ls:
                D = steady(sch, stake, L, R, p, seed=f"e1-{p}")
                res[(sch.name, p, L)] = (mean(D), pct(D, 0.95))
    for p in ps:
        rows = []
        for sch in zoo:
            rows.append([sch.name + ("" if sch.state_free else " (*)")] +
                        [f"{f3(res[(sch.name, p, L)][0])} ({f2(res[(sch.name, p, L)][1])})" for L in Ls])
        table("E1a", f"rounds/height, mean (p95), C=23, unit model, participation p={p}",
              ["schedule"] + [f"L={L}" for L in Ls], rows,
              note=f"n={n} equal-stake validators, {R} rounds, first 20 discarded. (*) = not a pure "
                   "function of (index, round[, seed]). era = 100 rounds here (a short era; the daily "
                   "era cost is E11).")
    # other C
    for C2 in (8, 11, 22):
        n2 = (100 if C2 <= 11 else 40) * C2
        stake2 = [1] * n2
        rows = []
        for sch in subset_zoo(n2, C2, R):
            row = [sch.name]
            for p in (1.0, 0.67):
                for L in (0, 3, 5):
                    D = steady(sch, stake2, L, R, p, seed=f"e1-{C2}-{p}")
                    row.append(f"{f3(mean(D))} ({f2(pct(D, .95))})")
            rows.append(row)
        table("E1b", f"rounds/height, mean (p95), C={C2}, unit model",
              ["schedule", "p=1 L=0", "p=1 L=3", "p=1 L=5", "p=.67 L=0", "p=.67 L=3", "p=.67 L=5"], rows,
              note=f"n={n2}. C=8: one unit per 12 s slot (explainer Option 5); C=11: 4-slot stretch; "
                   "C=22: Q17 grid shifted by 4 s (README:146).")
    return res


def e1c():
    """Q17 tick model (idle ticks) and mk slide at a realistic slide rate."""
    rows = []
    R = 200 if QUICK else 300
    for C in (23, 22, 11):
        T, ut = unit_ticks(C, "q17")
        n = 40 * C
        stake = [1] * n
        z = {s.name: s for s in schedule_zoo(n, C, R)}
        for name in ("fixed v mod C", "slow +1 / 10r", "mk slide s=1", "epoch reshuffle (4r)",
                     "era(100r) + slow +1/10r"):
            row = [f"C={C} ({T} ticks)", name]
            for p in (1.0, 0.67):
                for L in (0, 3):
                    D = steady(z[name], stake, L, R, p, seed=f"e1c-{C}-{p}", T=T, utick=ut)
                    row.append(f"{f3(mean(D))} ({f2(max(D))})")
            rows.append(row)
    table("E1c", "Q17 tick model: rounds/height, mean (max), lag L in 4 s ticks (idle ticks count as time)",
          ["grid", "schedule", "p=1 L=0", "p=1 L=3", "p=.67 L=0", "p=.67 L=3"], rows,
          note="C=23: idle tick [92,96) s; C=22: idle ticks [0,4) and [92,96) s; C=11: 48 s round, idle "
               "[44,48) s (pipelined-units/README.md:24,57-62,146).")
    # mk slide at realistic rate: n/C = 1000 per unit (mainnet is 43k per unit at 1M, i.e. slower still)
    C = 23
    n = 1000 * C
    stake = [1] * n
    R2 = 60 if QUICK else 120
    rows = []
    for sch in (Rotating(n, C, lambda r: 0, "fixed v mod C"), Mikhail(n, C, 1, "mk slide s=1"),
                Mikhail(n, C, n // C, "mk slide s=n/C")):
        row = [sch.name]
        for p in (1.0, 0.67):
            for L in (0, 3):
                D = steady(sch, stake, L, R2, p, seed=f"e1d-{p}", burn=10)
                row.append(f"{f3(mean(D))} ({f2(max(D))})")
        rows.append(row)
    table("E1d", f"mk slide at n={n} (1000 validators per unit), C=23: rounds/height mean (max)",
          ["schedule", "p=1 L=0", "p=1 L=3", "p=.67 L=0", "p=.67 L=3"], rows,
          note=f"{R2} rounds. With s=1 only C validators change unit per round and one wraps from unit 0 "
               "to unit C-1; at mainnet scale (n/C = 43,478 at 10^6) that is 1e-6 of stake per round.")


# ----------------------------------------------------------------------------
# E2  transients after a sudden drop; E3 flapping
# ----------------------------------------------------------------------------

def drop_trials(sch, stake, L, trials, p_drop=0.67, correlated=None):
    C = sch.C
    n = len(stake)
    first3, win8 = [], []
    for trial in range(trials):
        rng = random.Random(f"drop-{trial}")
        rd = rng.randrange(6, 10)
        td = rd * C + rng.randrange(C)
        if correlated is None:
            off = offline_set(stake, p_drop, rng)
        else:
            off = correlated(rng)
        ev = [(0, bytearray([1] * n)), (td, flags_from_off(off))]
        jt, _, _ = simulate(sch, stake, L, td // C + 10, ev)
        Ds = [(jt[i] - jt[i - 1]) / C for i in range(1, len(jt)) if td < jt[i] <= td + 8 * C]
        first3.append(max(Ds[:3]))
        win8.append(max(Ds))
    return first3, win8


def e2():
    C = 23
    n = 40 * C
    stake = [1] * n
    trials = 20 if QUICK else 60
    zoo = schedule_zoo(n, C, 40)
    rows = []
    for sch in zoo:
        row = [sch.name]
        for L in (0, 3, 5):
            a, b = drop_trials(sch, stake, L, trials)
            row.append(f"{f2(pct(a, .5))}/{f2(pct(a, .95))}/{f2(max(a))} [{f2(max(b))}]")
        rows.append(row)
    table("E2a", f"sudden drop 100% -> 67% at a random phase, C=23: worst of the first 3 heights after the drop, "
                 f"median/p95/max over {trials} trials [max over the 8 rounds after the drop]",
          ["schedule", "L=0", "L=3", "L=5"], rows,
          note="Rounds. Drop tick uniform over rounds 6-9 and all 23 units; offline set uniform random.")
    rows = []
    for C2 in (8, 11, 22):
        n2 = (100 if C2 <= 11 else 40) * C2
        stake2 = [1] * n2
        for sch in subset_zoo(n2, C2, 40):
            a, b = drop_trials(sch, stake2, 3, trials)
            rows.append([f"C={C2}", sch.name, f"{f2(pct(a, .5))}/{f2(pct(a, .95))}/{f2(max(a))}", f2(max(b))])
    table("E2b", "sudden drop to 67%, L=3, other C: first-3-heights worst median/p95/max, and 8-round max",
          ["C", "schedule", "first 3 heights", "8-round max"], rows)


def e2c():
    """Correlated outage: one contiguous index range (an operator's deposit batches) goes dark."""
    C = 23
    n = 40 * C
    stake = [1] * n
    trials = 20 if QUICK else 60
    rows = []
    for frac in (0.20, 0.33):
        def corr(rng, frac=frac):
            k = int(frac * n)
            start = rng.randrange(n)
            off = bytearray(n)
            for i in range(k):
                off[(start + i) % n] = 1
            return off
        for sch in (Rotating(n, C, lambda r: 0, "fixed v mod C"), Rotating(n, C, lambda r: r // 10, "slow +1 / 10r"),
                    Mikhail(n, C, 1, "mk slide s=1"), BlockShuffle(n, C, 4, "epoch reshuffle (4r)")):
            pdrop = 1 - frac
            # steady state after a contiguous outage
            Ds = []
            for trial in range(trials // 3):
                rng = random.Random(f"corr-{frac}-{trial}")
                off = corr(rng)
                jt, _, _ = simulate(sch, stake, 3, 60, [(0, flags_from_off(off))])
                Ds += [d / C for d in durations(jt, from_tick=10 * C)]
            Dr = []
            for trial in range(trials // 3):
                rng = random.Random(f"rand-{frac}-{trial}")
                off = offline_set(stake, pdrop, rng)
                jt, _, _ = simulate(sch, stake, 3, 60, [(0, flags_from_off(off))])
                Dr += [d / C for d in durations(jt, from_tick=10 * C)]
            rows.append([f"{int(frac * 100)}% offline", sch.name, f"{f3(mean(Dr))} / {f2(max(Dr))}",
                         f"{f3(mean(Ds))} / {f2(max(Ds))}"])
    table("E2c", "outage shape, C=23, L=3: rounds/height mean / max, random vs contiguous-index outage",
          ["outage", "schedule", "random validators", "one contiguous index range"], rows,
          note="A contiguous index range models one operator's deposit batches going dark. Striping spreads it over "
               "all units; contiguous blocks (mk) put it into 4-8 adjacent units.")


def e3():
    C = 23
    n = 40 * C
    stake = [1] * n
    R = 120 if QUICK else 200
    rows = []
    for X in (1, 4):
        for sch in subset_zoo(n, C, R):
            Ds = []
            for trial in range(3 if QUICK else 6):
                rng = random.Random(f"flap-{X}-{trial}")
                F = offline_set(stake, 0.67, rng)
                ph = rng.randrange(C)
                ev = [(0, bytearray([1] * n))]
                t = 10 * C + ph
                k = 0
                while t < R * C:
                    ev.append((t, flags_from_off(F) if k % 2 == 0 else bytearray([1] * n)))
                    t += X * C
                    k += 1
                jt, _, _ = simulate(sch, stake, 3, R, ev)
                Ds += [d / C for d in durations(jt, from_tick=10 * C)]
            rows.append([f"{X} round(s)", sch.name, f3(mean(Ds)), f2(pct(Ds, .95)), f2(max(Ds))])
    table("E3", "flapping participation (one fixed 33% set alternates offline/online every X rounds), C=23, L=3",
          ["half-period", "schedule", "mean", "p95", "max"], rows)


# ----------------------------------------------------------------------------
# E4  gap lemma check
# ----------------------------------------------------------------------------

G_FORMULA = {
    "fixed v mod C": "C", "+1 / round": "C+1", "-1 / round": "2C-1", "slow +1 / 5r": "C+1", "slow +1 / 8r": "C+1",
    "slow +1 / 10r": "C+1", "slow +1 / 30r": "C+1", "slow +1 / 100r": "C+1", "slow -1 / 10r": "2C-1",
    "slow +1 / 10r, staggered": "C+1", "mk slide s=1": "2C-1 (1/n of stake)", "mk slide s=n/C": "2C-1",
    "epoch reshuffle (4r)": "2C-1", "round reshuffle": "2C-1", "VRF lottery / round": "2C-1",
    "era(100r) + slow +1/10r": "2C-1 at era, C+1 at K", "spiral s=1 / epoch": "C+1", "spiral s=2 / epoch": "C+2",
}


def e4():
    C = 23
    n = 40 * C
    stake = [1] * n
    R = 120 if QUICK else 240
    seeds = 3 if QUICK else 8
    trials = 10 if QUICK else 40
    rows = []
    for sch in schedule_zoo(n, C, max(R, 60)):
        rng = random.Random("steady-e4-0.67")
        off = offline_set(stake, 0.67, rng)
        on_stake = sum(stake[v] for v in range(n) if not off[v])
        q = -(-2 * n // 3)
        delta = (on_stake - q) / n
        G, Gd = gap_stats(sch, min(R, 200), stake, delta)
        row = [sch.name, G_FORMULA[sch.name], G, Gd]
        ok = True
        for L in (0, 3):
            mx_exact = 0
            mx_67 = 0
            for s in range(seeds):
                D = steady(sch, stake, L, R, 0.0, seed=f"e4x-{s}", exact=True, burn=5)
                mx_exact = max(mx_exact, int(round(max(D) * C)))
                D2 = steady(sch, stake, L, R, 0.67, seed=f"e4-{s}", burn=5)
                mx_67 = max(mx_67, int(round(max(D2) * C)))
            # drops from 100% to exactly the quorum at random phases (transients reach the bound)
            for trial in range(trials):
                rng = random.Random(f"e4drop-{trial}")
                td = rng.randrange(6, 10) * C + rng.randrange(C)
                offx = offline_set(stake, 0.0, rng, exact=True)
                jt, _, _ = simulate(sch, stake, L, td // C + 8, [(0, bytearray([1] * n)), (td, flags_from_off(offx))])
                Ds = [jt[i] - jt[i - 1] for i in range(1, len(jt)) if jt[i] > td]
                if Ds:
                    mx_exact = max(mx_exact, max(Ds))
            ok = ok and mx_exact <= L + G
            row += [f"{mx_exact} <= {L + G}", f"{mx_67} vs {L + Gd}"]
        row.append("yes" if ok else "NO")
        rows.append(row)
    table("E4", "gap lemma: D_h <= L + G ticks. Worst height observed at exact-threshold participation (steady "
                "state + drops at random phases) and at p=0.67 (vs L + G_delta)",
          ["schedule", "G (formula)", "G measured", "G_delta @.67", "L=0 exact", "L=0 p=.67",
           "L=3 exact", "L=3 p=.67", "bound holds"], rows,
          note=f"C=23 unit model, n={n}; {seeds} steady-state offline sets and {trials} drops per cell. "
               "G_delta = effective gap when the slack delta = (online - quorum)/S may be missing.")


# ----------------------------------------------------------------------------
# E5  stake models; E6 heavy-first / tail-light references
# ----------------------------------------------------------------------------

def e5():
    C = 23
    n = 200 * C
    R = 120 if QUICK else 200
    rows = []
    for model in STAKE_MODELS:
        stake = stake_vector(n, model, random.Random(f"stake-{model}"))
        S = sum(stake)
        unit_cv = None
        scheds = [Rotating(n, C, lambda r: 0, "fixed v mod C"), Rotating(n, C, lambda r: r // 10, "slow +1 / 10r"),
                  Mikhail(n, C, 1, "mk slide s=1"), BlockShuffle(n, C, 4, "epoch reshuffle (4r)"),
                  EraSlow(n, C, 100, 10, "era(100r) + slow +1/10r"), HeavyFirst(n, C, stake, "heavy-first (*)")]
        for sch in scheds:
            m0 = sch.members(0)
            us = [sum(stake[v] for v in lst) / (S / C) for lst in m0]
            row = [model, sch.name, f"{min(us):.2f}-{max(us):.2f}"]
            for p in (1.0, 0.8, 0.67):
                D = steady(sch, stake, 3, R, p, seed=f"e5-{model}-{p}")
                row.append(f"{f3(mean(D))} ({f2(pct(D, .95))})")
            rows.append(row)
    table("E5", "stake models, C=23, L=3: rounds/height mean (p95); unit stake range (round 0, relative to S/C)",
          ["stake model", "schedule", "unit stake min-max", "p=1", "p=.8", "p=.67"], rows,
          note=f"n={n}. 0x02-like = lognormal, median 238 ETH, clipped to [32, 2048], sigma={SIG02:.3f} "
               f"(calibrated to mean 603; {pc(P32_02, 1)} at 32 ETH, {pc(P2048_02, 1)} at 2048 ETH). "
               "'1.5% hold ~50%' = 1.5% at 2048 ETH, the rest at 32 (49.4% of stake).")


def time_to_first(sch, stake):
    """Units from a round-aligned start (everyone fresh) to the first justification, L irrelevant."""
    jt, _, _ = simulate(sch, stake, 0, 2, [(0, bytearray([1] * len(stake)))])
    return jt[0] + 1 if jt else float("inf")


def simulate_timing_adv(sched, stake, adv, L, R, target_unit):
    """Adversary set `adv` withholds its FG votes and releases all of them (e.g. via
    its own proposal; the STF has no unit check, mk spec :1188-1215) at the START
    of the tick of `target_unit` whenever that completes a quorum, so that unit's
    honest votes land on the already-justified height. target_unit=None: the
    adversary never votes (plain withholding baseline)."""
    n = len(stake)
    total = sum(stake)
    q2 = 2 * total
    C = sched.C
    last = [-1] * n
    cur = 0
    acc = 0
    lastj = -10 ** 9
    jt = []
    adv_fresh = sum(stake[v] for v in adv)
    advl = list(adv)
    for r in range(R):
        mem = sched.members(r)
        for u in range(C):
            t = r * C + u
            if (target_unit is not None and u == target_unit and lastj <= t - L - 1
                    and (acc + adv_fresh) * 3 >= q2 and adv_fresh > 0):
                acc += adv_fresh
                for v in advl:
                    last[v] = cur
                adv_fresh = 0
            known = cur if lastj <= t - L - 1 else cur - 1
            for v in mem[u]:
                if v in adv:
                    continue
                if last[v] < known:
                    last[v] = known
                    if known == cur:
                        acc += stake[v]
            if acc * 3 >= q2:
                jt.append(t)
                lastj = t
                cur += 1
                acc = 0
                adv_fresh = sum(stake[v] for v in advl if last[v] < cur)
    return jt


def e6():
    rows = []
    R = 120 if QUICK else 200
    for C in (8, 23):
        n = 100 * C
        stake = stake_vector(n, "1.5% hold ~50%", random.Random(f"hf-{C}"))
        scheds = [Rotating(n, C, lambda r: 0, "fixed v mod C"), Rotating(n, C, lambda r: r // 10, "slow +1 / 10r"),
                  BlockShuffle(n, C, 1, "round reshuffle"), HeavyFirst(n, C, stake, "heavy-first (*)")]
        for sch in scheds:
            m0 = sch.members(0)
            S = sum(stake)
            u0 = sum(stake[v] for v in m0[0]) / S
            row = [f"C={C}", sch.name, pc(u0, 1), time_to_first(sch, stake)]
            for L in (0, 1, 3):
                D = steady(sch, stake, L, R, 1.0, seed=f"e6-{C}")
                row.append(f3(mean(D)))
            D = steady(sch, stake, 3, R, 0.8, seed=f"e6b-{C}")
            row.append(f3(mean(D)))
            # timing adversary: 10% of stake (random validators), releases right before unit 0
            rng = random.Random(f"adv-{C}")
            order = list(range(n))
            rng.shuffle(order)
            adv, acc_s = set(), 0
            for v in order:
                if acc_s + stake[v] <= 0.10 * S:
                    adv.add(v)
                    acc_s += stake[v]
            for tu in (None, 0):
                jt = simulate_timing_adv(sch, stake, adv, 1, R, tu)
                D = [d / C for d in durations(jt, from_tick=20 * C)]
                row.append(f3(mean(D)) if D else "stall")
            row[-1] = "= withhold" if row[-1] == row[-2] else row[-1]
            rows.append(row)
    table("E6a", "heavy-first reference ('1.5% hold ~50%' stake): first-height latency vs instant-switch "
                 "steady state",
          ["C", "schedule", "unit-0 stake", "units to 1st quorum (round-aligned start)", "p=1 L=0", "p=1 L=1",
           "p=1 L=3", "p=.8 L=3", "10% withholds, L=1", "10% timing game, L=1"], rows,
          note="Rounds/height means. Withholds: a random 10% of stake never votes. Timing game: the same 10% "
               "withholds, then releases all its votes at the start of unit 0 whenever that completes a quorum, "
               "so unit 0's honest votes land on the already-justified height.")
    # tail-light (equal stake, C=8)
    rows = []
    C = 8
    n = 100 * C
    stake = [1] * n
    for sch in (Rotating(n, C, lambda r: 0, "fixed v mod C"), BlockShuffle(n, C, 1, "round reshuffle"),
                TailLight(n, C, 1 / 16, "tail-light w=1/16, per-round (*)"),
                TailLight(n, C, 1 / 32, "tail-light w=1/32, per-round (*)")):
        row = [sch.name]
        for p, L in ((1.0, 0), (1.0, 3), (0.8, 3), (0.67, 3)):
            D = steady(sch, stake, L, R, p, seed=f"tl-{p}")
            row.append(f"{f3(mean(D))} ({f2(max(D))})")
        rows.append(row)
    table("E6b", "tail-light reference (pattern note :440-477), C=8, equal stake: rounds/height mean (max)",
          ["schedule", "p=1 L=0", "p=1 L=3", "p=.8 L=3", "p=.67 L=3"], rows)


# ----------------------------------------------------------------------------
# E7  seat effects under the instant switch (stale votes, pivotality)
# ----------------------------------------------------------------------------

def e7():
    C = 23
    n = 40 * C
    stake = [1] * n
    R = 200 if QUICK else 690          # 690 rounds = 3 full cycles of slow +1/10r
    rows = []
    for sch in (Rotating(n, C, lambda r: 0, "fixed v mod C"), Rotating(n, C, lambda r: r // 10, "slow +1 / 10r"),
                Mikhail(n, C, 1, "mk slide s=1"), EraSlow(n, C, 100, 10, "era(100r) + slow +1/10r"),
                BlockShuffle(n, C, 4, "epoch reshuffle (4r)"), BlockShuffle(n, C, 1, "round reshuffle")):
        for p in (1.0, 0.8):
            for L in (0, 3):
                rng = random.Random(f"e7-{p}")
                off = bytearray(n) if p >= 1 else offline_set(stake, p, rng)
                flags = flags_from_off(off)
                jt, piv, st = simulate(sch, stake, L, R, [(0, flags)], seat_stats=True)
                tim, sta, red, mis, pvv = st
                on_v = [v for v in range(n) if not off[v]]
                votes = [tim[v] + sta[v] + red[v] for v in on_v]
                stale = [sta[v] / votes[i] for i, v in enumerate(on_v)]
                redu = [red[v] / votes[i] for i, v in enumerate(on_v)]
                pivs = [pvv[v] / votes[i] for i, v in enumerate(on_v)]
                rows.append([sch.name, p, L, f"{pc(min(stale), 1)} / {pc(mean(stale), 1)} / {pc(max(stale), 1)}",
                             f"{pc(min(redu), 1)} / {pc(max(redu), 1)}",
                             f"{pc(min(pivs), 1)} / {pc(mean(pivs), 1)} / {pc(max(pivs), 1)}"])
    table("E7", f"per-validator vote outcomes under the instant switch over {R} rounds (= {R * 96 / 3600:.1f} h), C=23",
          ["schedule", "p", "L", "stale share min / mean / max", "redundant share min / max",
           "votes in the pivotal unit min / mean / max"], rows,
          note="Over online validators. stale = vote for a height justified within the lag (Mikhail's spec still "
               "credits it as previous-target round participation, mk :124-128, :1202-1214); redundant = already "
               "voted for the height it knows (re-vote of the same target, not slashable, mk :506-520).")


# ----------------------------------------------------------------------------
# E8  registry / composition
# ----------------------------------------------------------------------------
# No mainnet registry snapshot is available locally, so the registry is
# synthetic: M operators with Zipf(1) sizes (cf. the Zipfian staking sets of
# ethresearch 20464:31-53), each depositing in contiguous index batches of
# uniform size in [1, min(1000, size/10)], batches interleaved in random order;
# 15% of batches exited as a whole plus 5% individual exits; an activation
# queue of 1% of the active count appended at the end (pending entries).

ACTIVE, EXITED, PENDING = 0, 1, 2
COMMITTEES_PER_ROUND = 2048          # mk spec :282


def make_registry(n_active, M=20000, batch_exit=0.15, ind_exit=0.05, pending_frac=0.01):
    rng = random.Random(f"registry-{n_active}")
    keep = (1 - batch_exit) * (1 - ind_exit)
    n_live = int(round(n_active / keep))
    H = sum(1.0 / i for i in range(1, M + 1))
    sizes = [max(1, int(round(n_live / (H * i)))) for i in range(1, M + 1)]
    batches = []
    for op, sz in enumerate(sizes):
        B = max(1, min(1000, sz // 10))
        rem = sz
        while rem > 0:
            b = min(rem, rng.randint(1, B))
            batches.append((op, b))
            rem -= b
    rng.shuffle(batches)
    nb = len(batches)
    ex = set(rng.sample(range(nb), int(batch_exit * nb)))
    op_of = array("i")
    status = bytearray()
    for bi, (op, b) in enumerate(batches):
        whole = bi in ex
        for _ in range(b):
            op_of.append(op)
            status.append(EXITED if (whole or rng.random() < ind_exit) else ACTIVE)
    n_pend = int(pending_frac * n_active)
    cum = []
    s = 0
    for z in sizes:
        s += z
        cum.append(s)
    while n_pend > 0:
        op = bisect.bisect_left(cum, rng.random() * cum[-1])
        b = min(n_pend, rng.randint(1, max(1, min(1000, sizes[op] // 10))))
        for _ in range(b):
            op_of.append(op)
            status.append(PENDING)
        n_pend -= b
    return op_of, status, sizes


def registry_stakes(op_of, status, sizes, models):
    """Stake per registry entry (0 unless ACTIVE) for each stake model."""
    n_reg = len(status)
    act = [i for i in range(n_reg) if status[i] == ACTIVE]
    out = {}
    for model in models:
        rng = random.Random(f"regstake-{model}-{n_reg}")
        st = array("i", [0]) * n_reg
        if model == "equal":
            for i in act:
                st[i] = 32
        elif model == "0x02-like":
            for i in act:
                x = math.exp(MU02 + SIG02 * rng.gauss(0, 1))
                st[i] = int(round(min(2048.0, max(32.0, x))))
        elif model == "1.5% hold ~50% (iid)":
            heavy = set(rng.sample(act, int(round(0.015 * len(act)))))
            for i in act:
                st[i] = 2048 if i in heavy else 32
        elif model == "1.5% hold ~50% (big operators)":
            big = [i for i in act if sizes[op_of[i]] >= 1000]
            heavy = set(rng.sample(big, min(len(big), int(round(0.015 * len(act))))))
            for i in act:
                st[i] = 2048 if i in heavy else 32
        out[model] = st
    return out


def compose(rule, op_of, status, C, seed="era-0"):
    """Units (seat order at round 0) and committees for a composition rule."""
    n_reg = len(status)
    non_exited = [i for i in range(n_reg) if status[i] != EXITED]       # mk list incl. pending (:862-868)
    active = [i for i in range(n_reg) if status[i] == ACTIVE]
    if rule in ("stripe_raw", "stripe2"):
        units = [[] for _ in range(C)]
        for i in non_exited:
            units[i % C].append(i)
    elif rule == "stripe_pos":
        units = [active[c::C] for c in range(C)]
    elif rule == "contig":
        b = chunk_bounds(len(non_exited), C)
        units = [non_exited[b[u]:b[u + 1]] for u in range(C)]
    elif rule == "shuffle":
        perm = non_exited[:]
        random.Random(seed).shuffle(perm)
        units = [perm[c::C] for c in range(C)]
    else:
        raise ValueError(rule)
    cpu = [0] * C
    for k in range(COMMITTEES_PER_ROUND):
        cpu[(k * C) // COMMITTEES_PER_ROUND] += 1
    comms = []
    for u in range(C):
        m, k = units[u], cpu[u]
        if rule == "stripe2":
            for j in range(k):
                comms.append(m[j::k])
        else:
            bb = chunk_bounds(len(m), k)
            for j in range(k):
                comms.append(m[bb[j]:bb[j + 1]])
    return units, comms, non_exited


def top_share(d, total):
    return (max(d.values()) / total) if d and total else 0.0


def comp_metrics(units, comms, op_of, status, stakes, C, kwin=4):
    out = {}
    cnt = [sum(1 for i in m if status[i] == ACTIVE) for m in units]
    mc = sum(cnt) / C
    out["count"] = (min(cnt) / mc, max(cnt) / mc)
    for model, st in stakes.items():
        us = [sum(st[i] for i in m) for m in units]
        ms = sum(us) / C
        per = []
        for m in units:
            d = defaultdict(int)
            for i in m:
                if st[i]:
                    d[op_of[i]] += st[i]
            per.append(d)
        tops = [top_share(per[u], us[u]) for u in range(C)]
        ut = max(range(C), key=lambda u: tops[u])
        wtops = []
        for u in range(C):
            d = defaultdict(int)
            tot = 0
            for j in range(kwin):
                dd = per[(u + j) % C]
                tot += us[(u + j) % C]
                for k2, v in dd.items():
                    d[k2] += v
            wtops.append(top_share(d, tot))
        gl = defaultdict(int)
        for d in per:
            for k2, v in d.items():
                gl[k2] += v
        out[model] = dict(stake=(min(us) / ms, max(us) / ms), top_unit=max(tops), top_unit_idx=ut,
                          top_unit_op=max(per[ut], key=per[ut].get), top_win=max(wtops),
                          top_global=top_share(gl, sum(us)))
    # committees (by count of active members)
    c50 = c90 = c100 = 0
    nc = 0
    for m in comms:
        cc = Counter(op_of[i] for i in m if status[i] == ACTIVE)
        tot = sum(cc.values())
        if not tot:
            continue
        nc += 1
        sh = max(cc.values()) / tot
        c50 += sh >= 0.5
        c90 += sh >= 0.9
        c100 += sh >= 1.0
    out["comm"] = (c50 / nc, c90 / nc, c100 / nc, nc)
    # DoS duty cycle: units needed to cover 90% of each of the 3 largest operators' validators
    opc = Counter(op_of[i] for m in units for i in m if status[i] == ACTIVE)
    duty = []
    for op, tot in opc.most_common(3):
        per_u = sorted((sum(1 for i in m if status[i] == ACTIVE and op_of[i] == op) for m in units), reverse=True)
        acc = 0
        for k, x in enumerate(per_u):
            acc += x
            if acc >= 0.9 * tot:
                duty.append(k + 1)
                break
    out["duty"] = duty
    return out


def persistence_contig(non_exited, op_of, st, C, op, u0, window_units=1, max_rounds=None):
    """mk slide s=1: unit u at round r covers list positions [b_u + r, b_{u+window} + r).
    Rounds until operator op's stake share in it halves."""
    N = len(non_exited)
    b = chunk_bounds(N, C)
    lo, hi = b[u0], b[min(C, u0 + window_units)]
    so = sum(st[non_exited[j]] for j in range(lo, hi) if op_of[non_exited[j]] == op)
    tt = sum(st[non_exited[j]] for j in range(lo, hi))
    s0 = so / tt if tt else 0
    if max_rounds is None:
        max_rounds = N
    for r in range(max_rounds):
        i_out = non_exited[(lo + r) % N]
        i_in = non_exited[(hi + r) % N]
        tt += st[i_in] - st[i_out]
        if op_of[i_out] == op:
            so -= st[i_out]
        if op_of[i_in] == op:
            so += st[i_in]
        if tt and so / tt < s0 / 2:
            return r + 1, s0
    return float("inf"), s0


def e8():
    sizes_n = (120_000, 300_000) if QUICK else (120_000, 500_000, 1_000_000)
    models = ["equal", "0x02-like", "1.5% hold ~50% (big operators)"]
    rows_bal, rows_conc, rows_comm, rows_pers = [], [], [], []
    for nA in sizes_n:
        t0 = time.time()
        op_of, status, sizes = make_registry(nA)
        stakes = registry_stakes(op_of, status, sizes, models if nA == sizes_n[-1] else ["equal"])
        n_act = sum(1 for x in status if x == ACTIVE)
        n_ex = sum(1 for x in status if x == EXITED)
        n_pe = sum(1 for x in status if x == PENDING)
        topop = max(sizes) / sum(sizes)
        for C in ((8, 23) if nA == sizes_n[-1] else (23,)):
            for rule, label in (("stripe_raw", "stripe: index mod C"),
                                ("stripe2", "stripe + striped committees"),
                                ("stripe_pos", "stripe: active-list position mod C"),
                                ("contig", "mk contiguous blocks"),
                                ("shuffle", "seeded shuffle (era/epoch)")):
                units, comms, nonex = compose(rule, op_of, status, C)
                m = comp_metrics(units, comms, op_of, status, stakes, C)
                if rule != "stripe2":
                    rows_bal.append([f"{nA:,}", C, label, f"{m['count'][0]:.3f}-{m['count'][1]:.3f}"] +
                                    [f"{m[k]['stake'][0]:.3f}-{m[k]['stake'][1]:.3f}" if k in m else "" for k in models])
                    rows_conc.append([f"{nA:,}", C, label] +
                                     [f"{pc(m[k]['top_unit'], 1)} / {pc(m[k]['top_win'], 1)} (global {pc(m[k]['top_global'], 1)})"
                                      if k in m else "" for k in models] + [", ".join(str(x) for x in m["duty"])])
                rows_comm.append([f"{nA:,}", C, label, m["comm"][3], pc(m["comm"][0], 1), pc(m["comm"][1], 1),
                                  pc(m["comm"][2], 1)])
                if rule == "contig" and C == 23:
                    for k in models:
                        if k not in m:
                            continue
                        op, u0 = m[k]["top_unit_op"], m[k]["top_unit_idx"]
                        p1, s1 = persistence_contig(nonex, op_of, stakes[k], C, op, u0, 1)
                        rows_pers.append([f"{nA:,}", k, pc(s1, 1), f"{p1:,}", f"{p1 * 96 / 86400:.1f}"])
        print(f"[E8 n={nA:,}: registry {len(status):,} entries ({n_act:,} active, {n_ex:,} exited, {n_pe:,} pending); "
              f"largest operator {pc(topop, 1)} of deposits; {time.time() - t0:.1f}s]")
    table("E8a", "cohort balance: active count and stake per unit, min-max relative to the mean",
          ["n active", "C", "composition", "count"] + [f"stake: {k}" for k in models], rows_bal,
          note="Synthetic registry (no mainnet snapshot locally): Zipf(1) operator sizes over 20,000 operators, "
               "contiguous deposit batches, 15% batch exits + 5% individual exits, 1% pending at the end.")
    table("E8b", "largest single-operator stake share in one unit / in any window of 4 consecutive units; "
                 "units needed to cover 90% of each of the 3 largest operators",
          ["n active", "C", "composition"] + models + ["DoS duty: units covering 90% of top-3 ops"], rows_conc,
          note="Seat order of round 0. A pure rotation (fixed, +-1, slow +1/K) never changes these numbers.")
    table("E8c", f"committees ({COMMITTEES_PER_ROUND} per round, mk spec :282): share with one operator holding >=50% / >=90% / 100% of active members",
          ["n active", "C", "composition", "committees", ">=50%", ">=90%", "100%"], rows_comm)
    table("E8d", "persistence under mk's slide (s=1): rounds until the top (operator, unit) stake share halves",
          ["n active", "stake model", "initial share", "rounds", "days (96 s rounds)"], rows_pers,
          note="Fixed striping and rotations: forever. Seeded shuffle: one era (or epoch).")


# ----------------------------------------------------------------------------
# E9  membership churn and exit-induced re-seating
# ----------------------------------------------------------------------------

class ExitShift(Sched):
    """Index list that loses x entries per round at uniformly random places
    (exits, consolidation sources). Remaining validators keep their order;
    everyone behind a removed entry moves one list position earlier. Removed
    entries are zero-stake placeholders, so total stake stays constant.
      'pos'   seat = pos mod C                      (striping by active-set position)
      'pos+r' seat = (pos + r) mod C                (Francesco msg 1491)
      'mk'    seat = contiguous block of ((pos - r) mod N), N = current list length
      'pos+r/2048' committee = (pos + r) mod 2048, units = contiguous committee ranges (the
              other reading of msg 1491: a +1-committee rotation, i.e. +1 unit every 2048/C rounds)
      'raw'   seat = (validator index + r//10) mod C (index fixed; exits do not move anyone)"""

    def __init__(self, n, C, x, rule, name, R, seed="exits"):
        super().__init__(n, C, seed)
        rng = random.Random(f"{seed}-{x}-{rule}-{n}")
        G0 = x * R + 2 * C
        gb = [0] * (n + 1)
        ghosts = [rng.randrange(n + 1) for _ in range(G0)]
        for s in ghosts:
            gb[s] += 1
        rng.shuffle(ghosts)
        self.rule, self.name, self.x = rule, name, x
        self.pos = []
        for r in range(R + 1):
            pos = [0] * n
            acc = 0
            for k in range(n):
                acc += gb[k]
                pos[k] = k + acc
            self.pos.append((pos, n + sum(gb)))
            for _ in range(x):
                gb[ghosts.pop()] -= 1

    def members(self, r):
        n, C = self.n, self.C
        pos, N = self.pos[r]
        mem = [[] for _ in range(C)]
        if self.rule == "pos":
            for v in range(n):
                mem[pos[v] % C].append(v)
        elif self.rule == "pos+r":
            for v in range(n):
                mem[(pos[v] + r) % C].append(v)
        elif self.rule == "mk":
            for v in range(n):
                mem[(((pos[v] - r) % N) * C) // N].append(v)
        elif self.rule == "pos+r/2048":
            K2 = COMMITTEES_PER_ROUND
            for v in range(n):
                mem[(((pos[v] + r) % K2) * C) // K2].append(v)
        else:
            for v in range(n):
                mem[(v + r // 10) % C].append(v)
        return mem


def e9():
    # (a) churn per rotation step, closed form at n = 1e6
    n, C, K, E = 1_000_000, 23, 10, 1024
    rows = [
        ["fixed v mod C", "0", "0", "0"],
        ["+1 / round", "100%", "0 (committee follows its cohort)", "0"],
        [f"slow +1 / {K}r", f"100% every {K} rounds ({pc(1 / K, 0)} avg)", "0", "0"],
        [f"slow +1 / {K}r, staggered", f"{pc(1 / K, 0)} per round", "0", f"{pc(1 / K, 0)} per round"],
        ["mk slide s=1", pc(C / n, 4), pc(COMMITTEES_PER_ROUND / n, 3), pc(COMMITTEES_PER_ROUND / n, 3)],
        ["epoch reshuffle (4r)", "100% every 4 rounds", "100% every 4 rounds", "100% every 4 rounds"],
        ["round reshuffle / VRF", "100%", "100%", "100%"],
        [f"era({E}r) + slow +1/{K}r", f"100% every {K} rounds; 100% at era", f"100% per era ({pc(1 / E, 2)} avg)",
         f"100% per era ({pc(1 / E, 2)} avg)"],
        ["stripe by active-list position, per exit", "~50% (everyone behind it)", "~50%", "~50%"],
    ]
    table("E9a", "membership churn per round step at n=10^6, C=23 (fraction of validators that change ...)",
          ["schedule", "seat (unit)", "committee / subnet", "co-members"], rows,
          note="mk s=1: per round one validator per unit boundary changes unit (C) and one per committee boundary "
               f"changes committee ({COMMITTEES_PER_ROUND}); a validator changes committee every ~n/2048 = 488 "
               "rounds (13 h) and unit every n/C = 43,478 rounds (48 days).")
    # (b) latency with list-shifting exits
    C = 23
    n = 8192
    R = 120 if QUICK else 240
    stake = [1] * n
    rows = []
    for rule, label in (("raw", "stripe: index mod C, slow +1/10r"), ("pos", "stripe: active-list position mod C"),
                        ("pos+r", "(position + round) mod C (msg 1491, C units)"),
                        ("pos+r/2048", "(position + round) mod 2048 committees (msg 1491, other reading)"),
                        ("mk", "mk contiguous slide s=1")):
        for x in (0, 2, 8):
            sch = ExitShift(n, C, x, rule, label, R)
            row = [label, x]
            for p in (1.0, 0.67):
                D = steady(sch, stake, 3, R, p, seed=f"e9-{p}")
                row.append(f"{f3(mean(D))} / {f2(pct(D, .95))} / {f2(max(D))}")
            rows.append(row)
    table("E9b", "exits re-seat everyone behind them under position-based striping: rounds/height mean / p95 / max, "
                 "C=23, L=3",
          ["schedule", "list removals per round", "p=1", "p=.67"], rows,
          note="n=8192 (2048 committees of 4). Electra at S=36M: exit churn 256 ETH/epoch and consolidation churn "
               "~293 ETH/epoch (EIP-8061:218-221), i.e. ~2 + ~2 removals of 32-ETH entries per 8-slot round when "
               "queues are full; EIP-8061 raises this to ~8.6 + ~4.3 (EIP-8061:231-235). Under the 2048-committee "
               "reading every validator behind a removal changes committee (subnet churn ~50% per removal) even "
               "though few change unit.")


# ----------------------------------------------------------------------------
# E10  reward proxy
# ----------------------------------------------------------------------------
# ASSUMED per-seat miss probabilities (Q17 frames the per-offset miss rate as an
# experiment, pipelined-units/README.md:154; these are placeholders):
MISS_BASE = {0: 0.020,   # +0 s unit: vote phase overlaps block/payload propagation (README:68,89)
             1: 0.010,   # +4 s unit: aggregate published at +8 s, today's 4 s inclusion margin (README:64)
             2: 0.005}   # +8 s unit: clean vote phase, 12 s publication-to-proposal margin (README:64)
MISS_UNIT0 = 0.010       # round's first unit votes before the round's first block has propagated (README:146)
MISS_LAST = 0.005        # last unit lands at the round end, included as a previous-round vote (README:57; mk :657-660)
S_TOTAL = 36_000_000     # ETH, EIP-8061:218
W_FG = 40 / 64           # assumption: FG votes inherit today's source+target weight (altair beacon-chain.md:84-85,89)
W_PROP = 8 / 64          # PROPOSER_WEIGHT / WEIGHT_DENOMINATOR (altair beacon-chain.md:88-89)


def miss_rates(C):
    m = []
    for u in range(C):
        if C == 8:
            x = 0.010
        elif C == 22:
            x = MISS_BASE[(u + 1) % 3]
        else:
            x = MISS_BASE[u % 3]
        if u == 0:
            x += MISS_UNIT0
        if u == C - 1:
            x += MISS_LAST
        m.append(x)
    return m


def periodic_excursion(seq):
    """For a periodic zero-mean sequence: max window sum magnitude = max prefix - min prefix."""
    P = 0
    mx = mn = 0
    for x in seq:
        P += x
        mx = max(mx, P)
        mn = min(mn, P)
    return mx - mn


class BlockSeq:
    """Seat of cohort c at round r = (c + d * (r // B)) mod C: fixed (d=0), +1 per round (d=1, B=1),
    slow +1 every K (d=1, B=K), mk slide s=1 (d=-1, B=n/C). F(c, x) = sum of m over rounds [0, x)."""

    def __init__(self, C, m, d, B):
        self.C, self.m, self.d, self.B = C, m, d, B
        self.mbar = sum(m) / C
        self.P = C * B if d else B
        self.cb = []
        for c in range(C):
            acc, row = 0.0, [0.0]
            for k in range(2 * C):
                acc += B * m[(c + d * k) % C]
                row.append(acc)
            self.cb.append(row)

    def seat(self, c, r):
        return (c + self.d * (r // self.B)) % self.C

    def F(self, c, x):
        if self.d == 0:
            return x * self.m[c]
        P = self.P
        full, x = divmod(x, P)
        k, rem = divmod(x, self.B)
        return full * P * self.mbar + self.cb[c][k] + rem * self.m[(c + self.d * k) % self.C]

    def worst_dev(self, H):
        """max over cohorts and start rounds of |mean over [r0, r0+H) - mbar|; the sum is piecewise linear in
        r0 with breakpoints at block boundaries, so it suffices to test r0 in {kB, kB - H}."""
        best = 0.0
        C, B, P = self.C, self.B, self.P
        cands = set()
        for k in range(max(1, P // B) + 1):
            cands.add((k * B) % P)
            cands.add((k * B - H) % P)
        for c in range(C):
            for r0 in cands:
                tot = self.F(c, r0 + H) - self.F(c, r0)
                best = max(best, abs(tot / H - self.mbar))
        return best

    def eps_horizon(self, eps):
        if self.d == 0:
            return float("inf")
        seq = [self.B * (self.m[(self.d * k) % self.C] - self.mbar) for k in range(self.C)]
        # excursion over block granularity (window sums are linear inside blocks, so block-level is exact)
        return periodic_excursion(seq) / eps


def e10():
    rows_assume = []
    for C in (23, 11, 8):
        m = miss_rates(C)
        rows_assume.append([C, ", ".join(f"{100 * x:.1f}" for x in m), pc(sum(m) / C, 2), pc(max(m) - min(m), 1)])
    table("E10a", "ASSUMED per-seat miss rates (%), seat order u0..u(C-1)",
          ["C", "miss rate per seat (%)", "mean", "max-min spread"], rows_assume,
          note="+0 s units 2.0%, +4 s 1.0%, +8 s 0.5%; +1.0% on the round's first unit; +0.5% on the last unit. "
               "Placeholders for the Q17 experiment (pipelined-units/README.md:154); every deviation below scales "
               "linearly with the spread.")
    C = 23
    m = miss_rates(C)
    mbar = sum(m) / C
    sig = math.sqrt(sum((x - mbar) ** 2 for x in m) / C)
    eps = 0.001
    hours = {"1 h": 37, "1 day": 900, "1 week": 6300, "1 year": 328_500}
    n_main = 1_000_000
    K = 10
    E = 1024
    Z99 = 2.576   # 99th percentile of |N(0,1)|
    fams = [("fixed v mod C", 0, 1), ("+1 / round", 1, 1), ("slow +1 / 5r", 1, 5), ("slow +1 / 8r", 1, 8),
            ("slow +1 / 10r", 1, 10), ("slow +1 / 30r", 1, 30), ("slow +1 / 100r", 1, 100),
            ("mk slide s=1 (n=10^6)", -1, n_main // C), ("mk slide s=1 (n=1.2x10^5)", -1, 120_000 // C)]
    rows = []
    for name, d, B in fams:
        bs = BlockSeq(C, m, d, B)
        devs = [bs.worst_dev(H) for H in hours.values()]
        h0 = bs.eps_horizon(eps)
        rows.append([name] + [f"{pc(x, 3)} ({pc(W_FG * x, 3)})" for x in devs] +
                    ["never" if math.isinf(h0) else f"{h0:,.0f} r = {h0 * 96 / 3600:,.1f} h"])
    for name, P in (("epoch reshuffle (4r) [p99]", 4), ("round reshuffle / VRF [p99]", 1)):
        devs = [Z99 * sig * math.sqrt(P / H) for H in hours.values()]
        h0 = P * (Z99 * sig / eps) ** 2
        rows.append([name] + [f"{pc(x, 3)} ({pc(W_FG * x, 3)})" for x in devs] + [f"{h0:,.0f} r = {h0 * 96 / 3600:,.1f} h"])
    # era + slow: exact per-era block sums, random base per era, random start; p99 over 4000 validators
    bsK = BlockSeq(C, m, 1, K)
    rng = random.Random("e10-era")
    vals = {k: [] for k in hours}
    for _ in range(4000 if not QUICK else 800):
        r0 = rng.randrange(E)
        for k, H in hours.items():
            tot, r = 0.0, r0
            end = r0 + H
            while r < end:
                e_end = (r // E + 1) * E
                b = min(end, e_end)
                c = rng.randrange(C)
                tot += bsK.F(c, b) - bsK.F(c, r)
                r = b
            vals[k].append(abs(tot / H - mbar))
    devs = [pct(vals[k], 0.99) for k in hours]
    rows.append([f"era({E}r) + slow +1/{K}r [p99]"] + [f"{pc(x, 3)} ({pc(W_FG * x, 3)})" for x in devs] +
                [f"{bsK.eps_horizon(eps):,.0f} r within an era (as slow +1/{K}r)"])
    table("E10b", "seat-induced deviation of a validator's FG vote-success rate from the mean, by horizon "
                  f"(C=23; time to eps-fair = deviation <= {eps * 100:.1f} pp for every longer horizon)",
          ["schedule", "1 h", "1 day", "1 week", "1 year", "time to eps-fair"],
          rows,
          note="Cells: deviation of the FG vote-success rate (in parentheses: as a share of total CL reward, "
               "W_FG = 40/64, an assumption). Deterministic schedules: worst validator. Random: 99th percentile of "
               "|deviation|. Exact fairness (deviation 0) every K*C rounds for slow +1/K.")
    rows = []
    for k, H in hours.items():
        out = [k]
        for b in (32, 2048):
            lam = H * 8 * b / S_TOTAL
            out.append(f"{pc(W_PROP / math.sqrt(lam), 1)} (lambda={lam:.3g})")
        out.append(pc(W_FG * (max(m) - mbar), 2))
        rows.append(out)
    table("E10c", "proposer-lottery noise vs seat bias: relative std of a validator's total CL reward from the "
                  "proposer lottery, against the fixed-seat bias of the worst seat",
          ["horizon", "proposer lottery, 32 ETH", "proposer lottery, 2048 ETH", "fixed worst seat (any horizon)"],
          rows,
          note=f"lambda = expected proposals = horizon slots x balance / S, S = {S_TOTAL / 1e6:.0f}M ETH; "
               "CL proposer reward only (EL fees/MEV add more variance). The lottery averages out as 1/sqrt(horizon); "
               "a fixed seat's bias does not.")


# ----------------------------------------------------------------------------
# E11  cost of an era boundary
# ----------------------------------------------------------------------------

def e11():
    C = 23
    n = 40 * C
    stake = [1] * n
    trials = 20 if QUICK else 60
    R = 50
    rb = 30
    rows = []
    for p in (1.0, 0.67):
        for L in (0, 3):
            delays, worst = [], []
            for trial in range(trials):
                A = EraSlow(n, C, rb, 10, "A", seed=f"e11-{trial}")
                B = EraSlow(n, C, 10 ** 9, 10, "B", seed=f"e11-{trial}")
                rng = random.Random(f"e11-{trial}-{p}")
                flags = bytearray([1] * n) if p >= 1 else flags_from_off(offline_set(stake, p, rng))
                ja, _, _ = simulate(A, stake, L, R, [(0, flags)])
                jb, _, _ = simulate(B, stake, L, R, [(0, flags)])
                idx = next(i for i, t in enumerate(jb) if t >= (rb + 6) * C)
                delays.append((ja[idx] - jb[idx]) / C if idx < len(ja) else float("nan"))
                worst.append(max((ja[i] - ja[i - 1]) / C for i in range(1, len(ja))
                                 if (rb - 2) * C <= ja[i] <= (rb + 4) * C))
            rows.append([p, L, f2(mean(delays)), f2(pct(delays, .95)), f2(max(delays)), f2(max(worst)),
                         pc(mean(delays) / 900, 3), pc(mean(delays) / 1024, 3)])
    table("E11", "cost of one era boundary (composition reshuffle under era + slow +1/10r), C=23",
          ["p", "L", "delay mean (rounds)", "p95", "max", "worst height near boundary (rounds)",
           "overhead, era = 900 r (1 day)", "overhead, era = 1024 r (256 epochs)"], rows,
          note=f"Delay = lag of the first height justified >= 6 rounds after the boundary versus the same run "
               f"without the boundary; {trials} paired trials.")


# ----------------------------------------------------------------------------
# E12  adversary
# ----------------------------------------------------------------------------

def e12():
    S = S_TOTAL
    churn = {"Electra": (S // 65536) - 256, "EIP-8061": S // 65536}   # ETH/epoch (EIP-8061:221,235)
    rows = []
    beta = 0.10
    for C in (23, 8):
        coh = S / C
        for X in (0.25, 1 / 3, 0.5, 2 / 3):
            bmin = X / ((1 - X) * C + X)
            A = X / (1 - X) * (1 - beta) * coh
            dlt = max(0.0, A - beta * coh)
            ok = A <= beta * S
            row = [C, pc(X, 0), pc(bmin, 1)]
            for k in ("Electra", "EIP-8061"):
                row.append(f"{dlt / (churn[k] * 225):.1f}" if ok else "infeasible")
            row.append(f"{256 * 256 / coh * 100:.1f} pp")
            rows.append(row)
    table("E12a", f"days for a {pc(beta, 0)} adversary to own X of one cohort's stake by choosing consolidation "
                  "targets inside it (fixed composition: striping, contiguous blocks, or any rotation)",
          ["C", "target share X", "min adversary stake", f"days, Electra ({churn['Electra']} ETH/epoch)",
           f"days, EIP-8061 ({churn['EIP-8061']} ETH/epoch)", "era shuffle: max top-up gain per 256-epoch era"],
          rows,
          note=f"S = {S / 1e6:.0f}M ETH (EIP-8061:218); the adversary starts with share beta in every cohort and "
               "monopolises the consolidation churn (electra beacon-chain.md:631-633,798-825). Under a seeded era "
               "shuffle with era <= 256 epochs a consolidation cannot land inside the era it was aimed at "
               "(withdrawable = exit + 256 epochs, electra :1936-1938, :1068-1069); deposits/top-ups stay capped at "
               "256 ETH/epoch (EIP-8061:234), the last column.")
    # era-shuffle concentration and seed grinding
    rows = []
    rng = random.Random("grind")
    trials = 100 if QUICK else 300
    for C in (23,):
        for beta, s in ((0.05, 32), (0.05, 2048), (0.20, 32), (0.20, 2048)):
            m = beta * S / s
            mu = m / C
            sd = math.sqrt(m / C * (1 - 1 / C))
            O = (1 - beta) * S / C
            row = [C, pc(beta, 0), s, f"{m:,.0f}"]
            for k in (0, 4, 8):
                best = []
                for _ in range(trials):
                    mx = 0.0
                    for _seed in range(2 ** k):
                        for _c in range(C):
                            a = max(0.0, mu + sd * rng.gauss(0, 1))
                            mx = max(mx, a)
                    best.append(mx * s / (mx * s + O))
                row.append(pc(mean(best), 2))
            rows.append(row)
    table("E12b", "seeded era shuffle: adversary's largest share in any cohort, honest seed vs best of 2^k grindable seeds",
          ["C", "adversary stake", "validator size (ETH)", "validators", "k=0", "k=4", "k=8"], rows,
          note=f"Normal approximation to the multinomial; mean over {trials} draws. k = number of RANDAO bits the "
               "adversary controls (last-revealer withholding).")
    # VRF cohort-size variance
    rows = []
    for n in (1_000_000, 100_000, 10_000):
        for C in (8, 23):
            mu = n / C
            sd = math.sqrt(n / C * (1 - 1 / C))
            mx = []
            r2 = random.Random(f"vrf-{n}-{C}")
            for _ in range(500):
                mx.append(max(mu + sd * r2.gauss(0, 1) for _ in range(C)))
            rows.append([f"{n:,}", C, f"{mu:,.0f}", f"+{pc(mean(mx) / mu - 1, 1)}"])
    table("E12c", "VRF lottery (multinomial seats): expected largest cohort above the mean",
          ["n", "C", "mean cohort", "largest cohort"], rows)


# ----------------------------------------------------------------------------
# E13  the recommended schedule, all C
# ----------------------------------------------------------------------------

def e13():
    """Recommended: composition = striped seeded shuffle per era of 1024 rounds (256 epochs);
    position = + rotation by one unit every K = 8 rounds (2 epochs)."""
    K, E = 8, 1024
    trials = 20 if QUICK else 60
    R = 200 if QUICK else 320
    rows = []
    for C in (23, 22, 11, 8):
        n = (40 if C >= 22 else 100) * C
        stake = [1] * n
        round_s = 48 if C == 11 else 96
        m = miss_rates(C)
        cands = [Rotating(n, C, lambda r: 0, "fixed v mod C"), Mikhail(n, C, 1, "mk slide s=1"),
                 BlockShuffle(n, C, 4, "epoch reshuffle (4r)"), EraSlow(n, C, E, K, f"RECOMMENDED era({E}r) + slow +1/{K}r")]
        for sch in cands:
            row = [C, sch.name]
            for p, L in ((1.0, 0), (1.0, 3), (0.67, 3)):
                D = steady(sch, stake, L, R, p, seed=f"e13-{C}-{p}")
                row.append(f"{f3(mean(D))} ({f2(max(D))})")
            a, b = drop_trials(sch, stake, 3, trials)
            row.append(f"{f2(pct(a, .5))}/{f2(max(a))}")
            if sch.name.startswith("fixed"):
                bs = BlockSeq(C, m, 0, 1)
            elif sch.name.startswith("mk"):
                bs = BlockSeq(C, m, -1, 1_000_000 // C)
            elif sch.name.startswith("RECOMMENDED"):
                bs = BlockSeq(C, m, 1, K)
            else:
                bs = None
            if bs is None:
                sig = math.sqrt(sum((x - sum(m) / C) ** 2 for x in m) / C)
                h0 = 4 * (2.576 * sig / 0.001) ** 2
            else:
                h0 = bs.eps_horizon(0.001)
            row.append("never" if math.isinf(h0) else f"{h0 * round_s / 3600:,.1f} h")
            rows.append(row)
        # era-boundary cost for the recommended parameters (paired runs, boundary at round 30)
        dl = []
        for trial in range(trials):
            A = EraSlow(n, C, 30, K, "A", seed=f"e13b-{C}-{trial}")
            B = EraSlow(n, C, 10 ** 9, K, "B", seed=f"e13b-{C}-{trial}")
            rng = random.Random(f"e13b-{C}-{trial}")
            flags = flags_from_off(offline_set(stake, 0.67, rng))
            ja, _, _ = simulate(A, stake, 3, 50, [(0, flags)])
            jb, _, _ = simulate(B, stake, 3, 50, [(0, flags)])
            idx = next(i for i, t in enumerate(jb) if t >= 36 * C)
            dl.append((ja[idx] - jb[idx]) / C)
        rows.append([C, f"  era boundary cost (p=.67, L=3)", f"mean delay {f2(mean(dl))} r, max {f2(max(dl))} r",
                     f"= {pc(mean(dl) / E, 3)} of an era", "", "", ""])
    table("E13", "recommended schedule vs Mikhail's slide, fixed order and the per-epoch reshuffle, every C",
          ["C", "schedule", "p=1 L=0", "p=1 L=3", "p=.67 L=3", "drop to 67%, L=3: median/max", "eps-fair (0.1 pp)"],
          rows,
          note="Rounds/height mean (max). Unit model. eps-fair uses the assumed miss rates of E10a; mk slide evaluated "
               "at n=10^6; reshuffle = p99 over validators.")


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------

def main():
    print(f"# schedules.py output ({'QUICK' if QUICK else 'full'} run)")
    print(f"0x02-like calibration: mu=ln(238), sigma={SIG02:.4f}, mean "
          f"{clipped_lognormal_mean(MU02, SIG02):.1f} ETH, {pc(P32_02, 1)} at 32 ETH, {pc(P2048_02, 1)} at 2048 ETH")
    for f in (e1, e1c, e2, e2c, e3, e4, e5, e6, e7, e8, e9, e10, e11, e12, e13):
        t0 = time.time()
        f()
        print(f"\n[{f.__name__}: {time.time() - t0:.1f}s, total {time.time() - T_START:.1f}s]")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
