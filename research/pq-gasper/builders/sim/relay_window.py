"""Who may relay a slot's votes: arithmetic behind option 2 of the builders post (posts/pq-gasper-builders.md).

Stdlib only, deterministic. Nothing here is proved; it is back-of-envelope.

Model. One committee (weight 1) votes per slot, and a new block carries a 40 % boost.
A node off the attestation subnets sees a slot's votes only through published
aggregates. The proposers of the last W slots may publish. An honest block N is
proposed at slot 0 by a proposer that can aggregate, so the honest votes of slots
0 .. W-1 get published. Adversarial proposers follow, publish their own votes for a
competing branch built on N's parent, and hide the honest votes of later slots.
The run succeeds at the first slot whose honest committee sees the competing branch,
with the boost, ahead of N.
"""
BOOST = 0.4


def run_needed(beta, W, kmax=400):
    for j in range(1, kmax + 1):
        visible_n = (1 - beta) * min(j, W)   # honest votes of slots 0 .. min(j, W) - 1
        alt = (j - 1) * beta + BOOST          # adversarial votes of slots 1 .. j-1, plus the boost
        if alt > visible_n + 1e-12:
            return j
    return None


print("Adversarial proposers needed in a row after an honest block (share of honest blocks)")
print("stake    W=1            W=2            W=4            W=8             W=32")
for beta in (0.20, 0.25, 0.30, 1 / 3):
    cells = []
    for W in (1, 2, 4, 8, 32):
        k = run_needed(beta, W)
        cells.append(f"{k:>3} ({beta ** k:7.1e})")
    print(f"{beta:5.1%}  " + "  ".join(cells))
print("W = 1: only the block's own proposer relays. With every honest vote visible,")
print("N has j(1-beta) against (j-1)beta + 0.4 after j slots and is never overtaken below half the stake.")
print()

FULL, SUBNET = 303, 209        # KiB: full-slot aggregate, one subnet's proof (leanVM @ 29077b733)
print("Worst-case extra traffic per slot, one copy:")
for W in (8, 32):
    print(f"  last {W:2d} proposers, one full-slot aggregate each:  {W * FULL / 1024:5.1f} MiB")
print(f"  pq spec, 4 aggregators x 16 subnets:               {64 * SUBNET / 1024:5.1f} MiB")
step = 0.05
print(f"  anyone may publish, each adding {step:.0%} of a committee: {16 / step * SUBNET / 1024:5.1f} MiB")
