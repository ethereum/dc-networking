"""What a pqGasper attestation aggregate is worth to the proposer that includes it.

Stdlib only, deterministic. Prints every reward number quoted in ../builders.md.
The bid statistics are constants, measured once from the relay data APIs.

Spec (consensus-specs `pq` branch @ ee867e9, built on Gloas; Altair reward weights):
- base reward per increment = EFFECTIVE_BALANCE_INCREMENT * BASE_REWARD_FACTOR
  // isqrt(total active balance), BASE_REWARD_FACTOR = 64.
- An included vote sets up to three flags: source (weight 14, inclusion delay <= 5),
  target (26, any time while its epoch is current or previous), head (14, inclusion
  delay == 1, i.e. only in the very next block). WEIGHT_DENOMINATOR = 64.
- The proposer earns base_reward * weight / 448 for every newly set flag
  (448 = (64 - 8) * 64 / 8), which is exactly 1/7 of what the attester earns.
- PQ removes sync committees, so attestation inclusion is the proposer's whole
  consensus-layer reward (bar slashings).

Defaults: 44.2 M ETH active effective balance and 788,728 active validators (mainnet,
epoch 489,939, 2026-11-18), and the builder payments of the 7 days before that
(46,784 MEV-Boost blocks, relay data APIs).

Usage: python3 builder_rewards.py [total_active_balance_eth] [participation]
"""
import sys
from math import isqrt

GWEI = 10**9
SLOTS_PER_EPOCH = 32
SUBNETS = 16                      # ATTESTATION_SUBNET_COUNT_PQ = committees per slot
W_SOURCE, W_TARGET, W_HEAD = 14, 26, 14
W_DENOM, W_PROPOSER = 64, 8
PROPOSER_DENOM = (W_DENOM - W_PROPOSER) * W_DENOM // W_PROPOSER   # 448
EPOCHS_PER_DAY = 225

T_ETH = float(sys.argv[1]) if len(sys.argv) > 1 else 44_200_000
V = 788_728                       # active validators
BID_MEDIAN, BID_P75, BID_P90, BID_MEAN = 0.0089, 0.0146, 0.0288, 0.0316   # ETH per block
BIDS_BELOW_SLOT, BIDS_BELOW_HEAD = 0.948, 0.706   # share of winning bids below 0.0506 / 0.0131 ETH
PART = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0


def eth(gwei):
    return gwei / GWEI


b = GWEI * 64 // isqrt(int(T_ETH * GWEI))          # gwei per 1-ETH increment per epoch
slot_increments = T_ETH / SLOTS_PER_EPOCH * PART     # attesting ETH per slot


def proposer_value(increments, weights=W_SOURCE + W_TARGET + W_HEAD):
    """Gwei the proposer earns for including votes worth `increments` ETH."""
    return increments * b * weights / PROPOSER_DENOM


full = proposer_value(slot_increments)
head = proposer_value(slot_increments, W_HEAD)
src = proposer_value(slot_increments, W_SOURCE)
tgt = proposer_value(slot_increments, W_TARGET)
attesters = slot_increments * b * (W_SOURCE + W_TARGET + W_HEAD) / W_DENOM

print(f"total active balance            {T_ETH/1e6:.1f} M ETH, participation {PART:.0%}")
print(f"base reward per increment       {b} gwei per ETH per epoch")
print(f"attesters' maximum reward       {eth(T_ETH * b * 54 / 64) * EPOCHS_PER_DAY * 365.25 / T_ETH:.2%} APR")
print(f"votes per slot / per subnet     {V / SLOTS_PER_EPOCH:,.0f} / {V / SLOTS_PER_EPOCH / SUBNETS:,.0f}")
print()
print("Value to the proposer of including one slot's votes (all three flags):")
print(f"  full slot aggregate           {eth(full):.4f} ETH")
print(f"    of which head               {eth(head):.4f} ETH  (lost unless in the very next block)")
print(f"    of which source             {eth(src):.4f} ETH  (lost after 5 slots)")
print(f"    of which target             {eth(tgt):.4f} ETH  (kept while the epoch is current or previous)")
print(f"  one subnet aggregate (1/16)   {eth(full / SUBNETS):.5f} ETH")
print(f"  one 32 ETH validator's vote   {proposer_value(32):,.0f} gwei = {eth(proposer_value(32)):.2e} ETH")
print(f"  one 2048 ETH validator's vote {proposer_value(2048):,.0f} gwei = {eth(proposer_value(2048)):.2e} ETH")
print(f"  attesters' own reward, slot   {eth(attesters):.4f} ETH  (= 7x the proposer's)")
print()
print("Against what builders pay proposers (winning MEV-Boost bids, 7 days):")
for name, bid in (("median", BID_MEDIAN), ("p75", BID_P75), ("p90", BID_P90), ("mean", BID_MEAN)):
    print(f"  {name:6s} bid {bid:.4f} ETH        slot's votes = {eth(full) / bid:4.1f}x, head credit alone = {eth(head) / bid:4.1f}x")
print(f"  winning bids below the slot's votes: {BIDS_BELOW_SLOT:.0%}; below head credit alone: {BIDS_BELOW_HEAD:.0%}")
print(f"  votes missing from an aggregate that cost as much as the median bid: {BID_MEDIAN / eth(full):.0%} of the slot")
print()
print("Local fallback: a proposer that merges only the subnets it is on")
for k in (0, 1, 2, 4, 8, 16):
    print(f"  on {k:2d} of 16 subnets           {eth(full * k / SUBNETS):.4f} ETH  ({k/SUBNETS:.0%})")
print()
print("Cost to a winning builder of leaving votes out of its aggregate (vs a rival that includes them):")
for f in (0.01, 0.10, 1 / 3, 0.5):
    print(f"  drop {f:5.1%} of the slot          {eth(full * f):.4f} ETH per slot")
per_epoch = full * (1 / 3) * SLOTS_PER_EPOCH
print(f"  drop 1/3 in every slot           {eth(per_epoch):.3f} ETH per epoch, {eth(per_epoch) * EPOCHS_PER_DAY:.0f} ETH per day")
print("  (finality-relevant target credit can still be included by any block in the")
print("   epoch window, so a censor must also win, or starve, all of those blocks)")
