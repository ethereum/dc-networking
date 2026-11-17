"""Aggregator selection under PQ Gasper: VRF lottery vs exactly-k public (RANDAO) draw.

Stdlib only, deterministic. Prints every number quoted in ../aggregator-selection.md.

Model: V validators, 16 subnets (= committees) per slot, 32 slots per epoch,
n = V / 512 members per committee. An aggregate that never appears loses its
committee's votes for good (no fallback path). Finality needs > 2/3 of stake
included per epoch.
"""
from math import exp, log, ceil

V = 800_000                      # pq-gasper/README: 16 subnets, ~1,600 per subnet
SUBNETS, SLOTS = 16, 32
CS_PER_EPOCH = SUBNETS * SLOTS   # 512 committee-slots per epoch
n = V / CS_PER_EPOCH             # ~1,563 members per committee
PROOF_KIB = 209                  # leanVM leaf aggregate, benchmarks.json @ 035eff47a


def vrf_empty(k, frac=1.0):
    """P(no aggregator among a `frac` share of the committee), lottery target k."""
    return (1 - k / n) ** (frac * n)


def finality_halt_beta(q_of_beta):
    """Smallest adversarial stake beta with (1-beta)(1-q(beta)) < 2/3 (bisection)."""
    lo, hi = 0.0, 1 / 3
    for _ in range(60):
        mid = (lo + hi) / 2
        if (1 - mid) * (1 - q_of_beta(mid)) < 2 / 3:
            hi = mid
        else:
            lo = mid
    return hi


def needed_q(beta):
    """Share of honest committee-slots to suppress so included stake < 2/3."""
    return max(0.0, 1 - 2 / (3 * (1 - beta)))


def public_d(k, beta):
    """Floodable share d of honest stake at which an exactly-k public draw halts finality."""
    x = needed_q(beta) ** (1 / k)          # need (beta + (1-beta) d)^k >= q
    return max(0.0, (x - beta) / (1 - beta))


def vrf_d(k, beta):
    """Real-time-detectable share d' at which a target-k lottery halts finality."""
    q = needed_q(beta)
    if q == 0:
        return 0.0
    return max(0.0, 1 - (-log(q)) / (k * (1 - beta)))


def distinct_machines(sizes):
    """E[# machines hosting >= 1 member of one committee]; sizes = validators per machine."""
    return sum(1 - (1 - v / V) ** n for v in sizes)


def heimbach_shape(machines):
    """Validators-per-machine shape from Heimbach et al. (USENIX Sec '25): 27 % host 1,
    >50 % host <= 4, 11 % host > 100. Big machines split 50/50 into 300 and the rest
    (round-number splits) so that totals match V."""
    a, b, c = int(0.27 * machines), int(0.25 * machines), int(0.37 * machines)
    big = machines - a - b - c
    small_total = a * 1 + b * 3 + c * 30
    rest = V - small_total
    half = big // 2
    big_large = (rest - half * 300) / (big - half)
    return [1] * a + [3] * b + [30] * c + [300] * half + [big_large] * (big - half)


if __name__ == "__main__":
    print(f"V={V:,}  n per committee = {n:,.0f}  committee-slots per epoch = {CS_PER_EPOCH}")
    print("\n# Bandwidth of the aggregate layer (one copy)")
    for k in (16, 4):
        mib = SUBNETS * k * PROOF_KIB / 1024
        print(f"k={k:2}: {SUBNETS*k:3} aggregates/slot = {mib:5.1f} MiB/slot = {mib*8*1.048576/12:5.1f} Mbit/s")

    print("\n# Benign: P(committee-slot has no aggregator)  [per epoch]")
    for k in (16, 8, 4):
        p = vrf_empty(k)
        print(f"VRF  k={k:2}: {p:.2e}  [{p*CS_PER_EPOCH:.3g}]")
    print("RANDAO exact-k: 0 by construction")

    print("\n# Byzantine stake beta=1/3 withholds: P(no honest aggregator)  [per epoch]")
    beta = 1 / 3
    for k in (16, 4):
        p = vrf_empty(k, 1 - beta)
        print(f"VRF    k={k:2}: {p:.2e}  [{p*CS_PER_EPOCH:.3g}]")
    for k in (16, 4):
        p = beta ** k
        print(f"RANDAO k={k:2}: {p:.2e}  [{p*CS_PER_EPOCH:.3g}]")
    p = beta ** 4 * vrf_empty(4, 1 - beta)
    print(f"hybrid 4 public + VRF backups k_b=4: {p:.2e}  [{p*CS_PER_EPOCH:.3g}]")

    # RANDAO grinding: tail proposers pick the best of 2^k seeds for the next draw.
    from math import comb
    p, m = beta ** 4, CS_PER_EPOCH
    cdf, acc = [], 0.0
    for x in range(m + 1):
        acc += comb(m, x) * p ** x * (1 - p) ** (m - x)
        cdf.append(min(acc, 1.0))
    for k in (1, 2, 4, 5):
        seeds = 2 ** k
        e_max = sum(1 - cdf[x] ** seeds for x in range(m))
        print(f"draw-4, best of 2^{k} seeds: E[captured committee-slots/epoch] = {e_max:.1f}")

    print("\n# Stake that halts finality by withholding alone (no DoS)")
    print(f"VRF    k=16: {finality_halt_beta(lambda b: vrf_empty(16, 1-b)):.4f}")
    print(f"VRF    k= 4: {finality_halt_beta(lambda b: vrf_empty(4, 1-b)):.4f}")
    print(f"RANDAO k= 4: {finality_halt_beta(lambda b: b**4):.4f}")
    print(f"RANDAO k=16: {finality_halt_beta(lambda b: b**16):.4f}")

    print("\n# Machines to flood (perfect map, zero stake)")
    need = ceil(CS_PER_EPOCH * needed_q(0) + 1e-9)
    for k in (4, 16):
        print(f"public k={k:2}: per committee {k}, per slot {SUBNETS*k}, "
              f"finality halt {need} committee-slots/epoch -> {need*k} machine-slots/epoch, "
              f"{need*k/SLOTS:.1f} concurrent")

    print("\n# Machines hosting one committee (blind attacker vs private lottery)")
    for N in (5_000, 8_000, 10_000):
        print(f"heavy-tailed, {N:>6,} validator machines: {distinct_machines(heimbach_shape(N)):6.0f}")
    for N in (5_000, 8_000):
        print(f"uniform,      {N:>6,} validator machines: {distinct_machines([V/N]*N):6.0f}")

    print("\n# Finality-halt threshold: floodable share of honest stake")
    print("beta   public-4  public-8  public-16  VRF-16(real-time)  VRF-4(real-time)")
    for b in (0.0, 0.1, 0.2, 0.25, 0.3):
        print(f"{b:4.2f}   {public_d(4,b):7.3f}  {public_d(8,b):7.3f}  {public_d(16,b):8.3f}"
              f"  {vrf_d(16,b):16.3f}  {vrf_d(4,b):15.3f}")
