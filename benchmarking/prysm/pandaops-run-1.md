# pandaops cluster run 1 — scenario (planned 2026-09-04)

First large-scale run of the [decoupled-casper Prysm fork](prysm.md) outside
Shadow: a 1000-node Kurtosis network operated by pandaops. Scheduling left
room for a **single configuration**, so the config is chosen to mimic mainnet
load per subnet with a ~25% buffer, and to 4x the aggregate load on the
global topic. Designed by Sukun, reviewed by Yann.

## Topology

| | value |
|---|---|
| nodes | 1000 (~1/8 of mainnet's ~10k beacon nodes), set up by pandaops |
| validators | 120,000 (~1/8 of mainnet) |
| supernodes | 200 nodes x 596 validators = 119,200 |
| solo stakers | 800 nodes x 1 validator = 800 |
| subnets = committees | 6 (one committee per subnet, as on mainnet) |
| nodes per subnet (expected) | ~467 = 200 supernodes (subscribed to all subnets) + 800 x 2 / 6 ≈ 267 solo stakers |
| round length | 8 slots |
| attesters per committee | 120,000 / 8 / 6 = 2500 |
| aggregators per committee | ~64: 2500 / 64 ≈ 39, so a validator aggregates when its selection proof ≡ 0 mod 39 |
| aggregate size | ~760 B (313 B bitlist for 2500 bits + data, 3 x 96 B sigs, committee bits, index) |
| aggregates per slot | 64 x 6 = 384, ~0.3 MB on the global topic |
| raw attestations per slot | 6 x 2500 = 15k (2500 per subnet) |
| run length | 2 h |

Extra load Sukun added on top of the FG votes: the 512 AC (availability)
votes per slot, dummy bytes standing in for VRF selection proofs, and
goldfish view merge.

## Why these numbers

- **Validators are a function of subnet size, subnets a function of node
  count.** Mainnet DC target is 2000 attesters per committee (1m / 8 slots /
  64 committees); 2500 is that plus 25%. With 1000 nodes, 6 subnets keeps each
  subnet at least as populated as a mainnet subnet.
- **4x aggregators.** Mainnet would run 16 aggregators per committee
  (`TARGET_AGGREGATORS_PER_COMMITTEE`), i.e. 16 x 64 = 1024 aggregates per
  slot, ~0.7 MB. The sim uses 64 to stress the global topic under imperfect
  network conditions.
- **Supernodes are in every subnet.** On mainnet, nodes subscribe to
  aggregator duties two epochs ahead. A supernode with ~500 validators
  expects ~1 validator per 2000-seat committee and a 16/2000 aggregator
  chance, so ~0.5 aggregator duties per slot, ~16 per epoch, ~32 live
  subscriptions. That gives roughly 500 supernodes + 250 home nodes per
  mainnet subnet. The sim has 200 supernodes + ~267 home nodes per subnet:
  fewer supernodes than mainnet, and left as is (this happens on mainnet too).

## Reference points

| | mainnet today | DC target (mainnet) | this run |
|---|---|---|---|
| validators / nodes | 1m / 10k | 1m / 10k | 120k / 1000 |
| committees = subnets | 64 | 64 | 6 |
| slots to finality | 32 | 8 | 8 |
| attesters per committee | 500 | 2000 | 2500 |
| aggregators per committee | 16 | 16 | 64 |
| aggregate size | ~510 B | ~700 B | ~760 B |
| aggregates per slot | 1024 | 1024 (~0.7 MB) | 384 (~0.3 MB) |
| raw attestations per slot | 32k | 128k | 15k |
| per subnet | 500 | 2000 | 2500 |

## Run plan and open items

- Run for 2 hours. Log volume is the main risk; if nodes deteriorate as logs
  grow, cut early and use the first part.
- Metrics: everything needed is logged; extraction scripting still to be
  written (Sukun). Perfect metrics matter less since parameters won't change
  between runs.
- Success bar: if this works out of the box (no partial messages etc.), it
  gives good confidence that the 4x finality improvement is networking-feasible.
  More sims will follow with the subnet-subscription model above rethought.
- Shadow run in parallel to confirm the setup before the cluster run.
