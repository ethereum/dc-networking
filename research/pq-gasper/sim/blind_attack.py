"""Blind attacker vs secret aggregators: how many must it flood to kill them all?

Stdlib only, deterministic (fixed seed). Prints the numbers quoted in the
"Blind attacker" section of ../aggregator-selection.md.

One committee (one subnet, one slot) of N members. The attacker knows the
committee (public) and every member's machine (a validator -> IP map), but
not which members aggregate. It floods some members' machines for the
aggregation window and wins if every aggregator is flooded.

Selection rules:
  secret-k   exactly k aggregators, a uniform random k-subset nobody else
             can see (would need a secret exact election, SSLE-style)
  lottery-k  each member aggregates independently with p = 1 / (N // k),
             today's is_aggregator() rule with a PQ VRF in place of BLS

Flooding m members, chosen blind:
  P_kill(secret-k)  = C(m, k) / C(N, k)          (~ (m/N)^k)
  P_kill(lottery-k) = (1 - p)^(N - m)            (~ e^(-k (1 - m/N)))
Mean members to flood until every aggregator is hit (random order):
  secret-k:  k (N + 1) / (k + 1)
  lottery-k: N - (1 - p)(1 - (1 - p)^N) / p
"""
import bisect
import random

V = 800_000          # validators (pq-gasper/README: 16 subnets x ~1,600)
N = 1_563            # members per committee = V / (16 subnets x 32 slots), rounded
TARGETS = (0.5, 0.9, 0.99)
SEED, RUNS = 1, 300


def secret_kill(m, k):
    if m < k:
        return 0.0
    p = 1.0
    for i in range(k):
        p *= (m - i) / (N - i)
    return p


def lottery_kill(m, k):
    p = 1 / max(1, N // k)
    return (1 - p) ** (N - m)


RULES = [("secret-4", secret_kill, 4), ("lottery-4", lottery_kill, 4),
         ("secret-16", secret_kill, 16), ("lottery-16", lottery_kill, 16)]


def members_needed(kill, k, target):
    """Fewest members flooded (blind) with P_kill >= target."""
    for m in range(N + 1):
        if kill(m, k) >= target - 1e-12:
            return m
    return N


def members_mean(kill, k):
    """E[members flooded, in random order, until all aggregators are hit]."""
    return sum(1 - kill(m, k) for m in range(N))


# --- Machines -----------------------------------------------------------------

def split(total, machines):
    """`machines` integer sizes summing to `total`, as even as possible."""
    q, r = divmod(total, machines)
    return [q + 1] * r + [q] * (machines - r)


def scenario(name, machines=8_000):
    """Validators per machine (ints summing to V)."""
    if name == "even":                       # upper bound: no concentration
        return split(V, machines)
    # Heimbach et al. (USENIX Sec '25): 27 % of machines host 1 validator,
    # >50 % host <= 4, 11 % host > 100 (half of those at 300, the rest larger).
    ones, threes = round(0.27 * machines), round(0.25 * machines)
    bigs = round(0.11 * machines)
    mids = machines - ones - threes - bigs
    mid = 30 if name == "heimbach" else 8    # "super96": only ~4 % of stake off big machines
    small = [1] * ones + [3] * threes + [mid] * mids
    rest = V - sum(small) - (bigs // 2) * 300
    return small + [300] * (bigs // 2) + split(rest, bigs - bigs // 2)


SCENARIOS = [
    ("heimbach", 5_000, "Heimbach shape, 5,000 validator machines"),
    ("heimbach", 8_000, "Heimbach shape, 8,000 validator machines"),
    ("heimbach", 10_000, "Heimbach shape, 10,000 validator machines"),
    ("super96", 8_000, "8,000 machines, small ones hold only ~4 % of stake (27 Oct call)"),
    ("even", 8_000, "even spread, 100 validators on each of 8,000 machines"),
]


def committee_counts(cum, rng):
    """Committee members per machine, most-loaded first (the attacker's order)."""
    counts = {}
    for x in rng.sample(range(V), N):
        j = bisect.bisect_right(cum, x)
        counts[j] = counts.get(j, 0) + 1
    return sorted(counts.values(), reverse=True)


def machines_needed(counts, kill, k, target):
    covered = 0
    if kill(0, k) >= target:
        return 0
    for used, x in enumerate(counts, 1):
        covered += x
        if kill(covered, k) >= target - 1e-12:
            return used
    return len(counts)


def machines_mean(counts, kill, k):
    total, covered = 1 - kill(0, k), 0
    for x in counts[:-1]:
        covered += x
        total += 1 - kill(covered, k)
    return total


def median(xs):
    s = sorted(xs)
    return s[len(s) // 2]


if __name__ == "__main__":
    print(f"One committee: N = {N:,} members; public draw-k needs exactly k floods.\n")
    print("# Members to flood, blind (exact)")
    print(f"{'rule':<11}" + "".join(f"{'P>=' + format(t, '.0%'):>9}" for t in TARGETS) + f"{'mean':>9}")
    for name, kill, k in RULES:
        row = "".join(f"{members_needed(kill, k, t):>9,}" for t in TARGETS)
        print(f"{name:<11}{row}{members_mean(kill, k):>9,.0f}")

    print("\n# Same, as a share of the committee, and members the attacker may leave alone")
    for name, kill, k in RULES:
        cells = []
        for t in TARGETS:
            m = members_needed(kill, k, t)
            cells.append(f"{m / N:6.1%} (spare {N - m:>3})")
        print(f"{name:<11}" + "  ".join(cells))

    per = 0.9 ** (1 / 16)
    print(f"\n# All 16 subnets of a slot at P>=90% (each subnet P>={per:.4f}): spare members per subnet")
    for name, kill, k in RULES:
        print(f"{name:<11}{N - members_needed(kill, k, per):>4}")

    print("\n# P(kill) when flooding a share f of the committee")
    print(f"{'f':>5}" + "".join(f"{name:>12}" for name, _, _ in RULES))
    for f in (0.25, 0.5, 0.75, 0.9, 0.95, 0.99):
        m = round(f * N)
        print(f"{f:>5.0%}" + "".join(f"{kill(m, k):>12.2e}" for _, kill, k in RULES))

    print("\n# Machines to flood, blind, most-loaded first "
          f"(median over {RUNS} random committees; mean = expected machines)")
    for key, machines, label in SCENARIOS:
        sizes = scenario(key, machines)
        assert sum(sizes) == V
        cum, acc = [], 0
        for s in sizes:
            acc += s
            cum.append(acc)
        rng = random.Random(SEED)
        comms = [committee_counts(cum, rng) for _ in range(RUNS)]
        hosts = median([len(c) for c in comms])
        big_share = sum(x for x in sizes if x > 100) / V
        print(f"\n{label} ({big_share:.0%} of stake on machines > 100)"
              f"\n  machines hosting >= 1 member: {hosts}")
        for name, kill, k in RULES:
            cells = "".join(f"{median([machines_needed(c, kill, k, t) for c in comms]):>9,}"
                            for t in TARGETS)
            mean = sum(machines_mean(c, kill, k) for c in comms) / RUNS
            print(f"  {name:<11}{cells}{mean:>9,.0f}")
