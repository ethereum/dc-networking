# WB-PQ: direct-delivery vote aggregation for post-quantum signatures

A gossipsub alternative for finality votes once BLS is replaced by hash-based
(leanSig / XMSS) signatures. It follows **Wonderboom**
([arXiv:2602.06655](https://arxiv.org/abs/2602.06655)): votes travel
point-to-point along an aggregation tree, not through gossip meshes. It adds
one twist: **anyone can subscribe to a topic and become a direct recipient of
its votes.**

Context: [ethereum/dc-networking](https://github.com/ethereum/dc-networking)
(requirements, the PQ-forwardness item Q8, and Yann's broker "Idea 1"), and
[EIP-8292](https://eips.ethereum.org/EIPS/eip-8292) (PQ aggregator role, leanVM
proof sizes and proving times).

## Why not gossipsub for PQ votes

| | BLS today | leanSig (PQ) |
|---|---|---|
| single vote on the wire | ~264 B | ~3.2 KiB (12×) |
| aggregate | 96 B signature + bitfield | 185–230 KiB leanVM proof (~2,000×) |
| aggregation | point addition, ~free | proving, ~270 sigs/s on 8 cores |

Gossipsub costs scale with **message size × mesh duplicates × subscribers**:

- Every vote reaches every one of the ~312 subnet members, several times each.
  In Shadow, a member of one 312-member subnet on links that keep up
  (symmetric 50 Mbit/s) received ≈ 6.7 bytes per vote byte it needed
  (duplicates plus control traffic, despite IDONTWANT; see
  [results/sim.md](results/sim.md)). The direct mode measured 1.02.
- A mainnet node is in 2 subnets. With PQ votes that is ~16 MiB each way per
  slot, mostly in the second after voting. On EIP-7870 attester links
  (50/25 Mbit/s) this saturates the uplink: rust-libp2p drops ~2,300 queued
  forwards per node per slot, the vote p99 rises to 2.3–2.6 s, and
  0.1–0.2 % of votes miss the aggregation deadline. At the 8-slot cadence
  gossip loses 16 % of the votes aggregators need.
- Today 16 aggregators per committee gossip their aggregates to *all* nodes.
  With PQ proofs that is 64 × 16 × 220 KiB ≈ 220 MiB per slot to every node
  before duplicates (1.4 GiB with them). That is infeasible even with one
  aggregate per committee: 92 MiB per slot to every node.

PQ needs two things gossip does not give: few copies of each vote, and proofs
that move up a tree instead of being flooded.

## Protocol

### Roles (per slot, all derived from the epoch's shuffling)

| role | who | does |
|---|---|---|
| **voter** | every validator, once per round | signs one leanSig vote, sends it directly to K subscribers of its topic |
| **leaf aggregator** | any node that **subscribed** to the topic | collects votes, proves one leaf aggregate per message, announces it upward |
| **internal aggregator** | any node subscribed to a tree node | pulls the best + one random child aggregate per child, folds 8 → 1 recursively |
| **proposer** (or a top-level aggregation builder) | next proposer | pulls best + random per top child, folds into the block proof |

### Topics and subscriptions

- Validators voting in slot *s* are split into **T topics** (committees) of
  ~400 votes each. Membership is shuffled per epoch, as committees are today.
- A node **subscribes** to topic indices by publishing a signed
  `Subscription{node_id, quic_addr, topic_bitfield, epoch, validator_index, sig}`
  on a global low-rate registry topic, once per epoch. It is ≈ 3.3 KiB. With
  ~2,000 subscribers that is ~6.5 MiB per epoch for every node (≈ 17 KiB/s).
- A subscription must be **backed by a validator key** (one record per
  validator index). Sybil subscribers then cost stake, and records can be
  rate-limited and slashed or ignored if they misbehave.
- Super-aggregators (cf. PeerDAS super-nodes, EIP-8292 super-aggregators) may
  subscribe to every topic.

### Vote delivery: the step that replaces the subnet

1. Duties are known one epoch ahead, so a voter's node pre-opens QUIC
   connections to its K recipients.
2. The voter picks **K = 16 recipients** among the topic's subscribers by
   rendezvous hashing (highest `H(validator_index, slot, subscriber_id)`):
   - deterministic and auditable, so an aggregator can't attract votes
     without registering;
   - load spreads evenly over subscribers;
   - adding more subscribers doesn't raise the voter's upload: there are
     never more than K copies.
3. The voter sends its 3.2 KiB vote to all K at once, one hop. A node
   subscribed to its own validators' topic includes itself.

Why K is capped instead of "send to all subscribers": open subscription would
let anyone inflate every voter's upload. With K = 16, the vote is censored
only if all 16 recipients are adversarial: 2.3 × 10⁻⁸ when ⅓ of subscribers
are adversarial (table below).

### Tree aggregation (Wonderboom, PQ-adapted)

```
 slot s, 800k validators / 32 slots = 25,000 votes

 25,000 voters ──(K=16 direct, 3.2 KiB)──▶ 64 topics × 16 leaf aggregators
                                              │ prove 391 sigs → 220 KiB proof
                                              │ announce (bitfield, ~100 B)
                                              ▼
                       8 groups × 16 internal aggregators   (pull best + random per child)
                                              │ fold 8 → 1 (3 × 0.3 s recursion)
                                              ▼
                                  proposer of slot s+1      (pull best + random per group)
                                              │ fold 8 → 1 → block proof ≈ 256 KiB
                                              ▼
                              block / global topic (one proof per slot)
```

- **Announce-then-pull.** Children push a tiny announcement (participation
  count + bitfield hash). Each parent pulls only the **largest** aggregate and
  **one random** one per child. That is Wonderboom's censorship rule, and it
  cuts parent downloads from 16 to 2 proofs per child (3.4 MiB instead of
  28 MiB per slot).
- Only **one proof per slot** goes on a broadcast topic, instead of
  64 × 16 today.
- The same tree works for BLS. BLS just makes the proving steps free, which
  fits the "don't foreclose multi-stage aggregation" requirement.

### Timeline inside a 12 s slot (vote at 4 s, as attestations today)

| t (s) | step | source of the number |
|---|---|---|
| 4.0–4.5 | votes leave (0.5 s jitter) | — |
| ≤ 5.0 | all 391 votes held by all 16 leaf aggregators | Shadow (EIP-7870 links): 100 % within 0.93 s of the first vote (1.16 s at 8 slots) |
| 6.0 | leaf cut-off (2 s after voting; 1 s of slack) | — |
| 7.4 | leaf proof ready (391 sigs at 270 sigs/s, 8 cores) | EIP-8292 |
| 8.6 | internal aggregators hold best + random per child | Shadow: all 16 proofs of 8 children 1.1–1.4 s after the first is emitted, on a 100/50 link |
| 9.5 | internal fold 8 → 1 | leanVM 2-to-1 recursion 0.3 s × 3 levels |
| 10.7 | proposer of s+1 holds best + random per group | as above |
| 11.6 | block proof ready, included at slot s+1 | — |

So aggregation completes within one slot, matching Wonderboom's single-slot
aggregation. Under Decoupled Consensus (vote in *i*, aggregate in *i+1*,
include in *i+2*) there is a full extra slot of slack.

## Example system: 800k validators, 32 slots

| parameter | value |
|---|---|
| validators V / nodes P | 800,000 / 10,000 |
| votes per slot | 25,000 (each validator votes once per 32-slot epoch) |
| topics per slot | 64 → 391 votes per topic |
| vote | leanSig 3,104 B + 168 B data/framing = 3,272 B |
| K recipients per vote / subscribers per topic | 16 / ≥ 16 |
| tree | 64 leaves → 8 internal → proposer (3 network hops vote → block proof) |
| leaf proof / block proof | 220 KiB / 256 KiB |
| aggregator subscriptions needed | 64 × 16 = 1,024 (e.g. 250 8-core boxes with ~4 topics each) |

## Load: is it feasible?

Full parametric tables: [results/model.md](results/model.md)
(`python3 model/load_model.py`). Highlights for leanSig at 800k / 32 slots:

| node | WB-PQ direct | gossipsub, same PQ votes |
|---|---|---|
| solo voter (1 validator) | **51 KiB upload once per epoch** | relays its 2 subnets every slot: **16 MiB per slot each way** (5.5 s of a 25 Mbit/s EIP-7870 attester uplink; Shadow: link saturates, forwards dropped) |
| 1,000-validator node | 1.6 MiB per slot upload (6.5 Mbit/s over 2 s) | the same 16 MiB per slot for its 2 subnets, plus publishing |
| leaf aggregator (1 topic) | 1.2 MiB down per slot (2.6 Mbit/s); 1.4 s of proving on 8 cores | n/a |
| internal aggregator / proposer | 3.4 MiB down per slot (14 Mbit/s over 2 s) + 0.9 s of folding | every node: aggregate topic 92 MiB (1 per committee) to 1.4 GiB (16 per committee) per slot |
| super-aggregator (all 64 topics) | 78 MiB down per slot (164 Mbit/s over 4 s). Proving everything takes ~21 s on one fast box, so it must prove a subset | n/a |
| every node | 1.7 MiB (the one block proof, gossiped) | — |
| **network-wide vote bytes per slot** | **1.2 GiB** | **160 GiB (≈ 128× more)** |

Verdict, for **800k validators and 32-slot rounds**:

- **Bandwidth is not the bottleneck** for anyone. Solo stakers go from
  relaying ~16 MiB per slot, more than an EIP-7870 attester link carries in
  time, to uploading 51 KiB per epoch.
- **Proving is the bottleneck.** 25,000 sigs per slot × 16 redundant
  provers ≈ 33,000 sig-proofs per second network-wide. That is ~250 8-core
  aggregator machines (or ~56 fast ones), i.e. 2.5 % of nodes. K = 8 halves
  this, at 1.5 × 10⁻⁴ censorship risk under a ⅓ Sybil share.
- **Connections are the engineering risk**, as Yann's notes said:
  - Over an epoch a leaf aggregator hears from ~400 voters per slot, out of
    up to several thousand distinct nodes. QUIC with session resumption and
    pre-dialing makes this manageable for server-class aggregators.
  - A solo node needs only 16 short-lived connections per epoch.
- **8-slot rounds (DC target):** 100k votes per slot and 256 topics. Per-role
  loads stay the same; you need 4× the aggregator subscriptions (~1,000
  8-core boxes). A 1,000-validator node uploads 26 Mbit/s for 2 s. Gossipsub
  at this cadence would push 65 MiB per slot through every node in 2 subnets,
  22 s of a 25 Mbit/s uplink per 12 s slot. In Shadow, gossip at this cadence
  left 16 % of the needed votes missing at the deadline; direct delivery
  still reached every recipient with a p99 of 423 ms.

### Censorship (all K recipients adversarial)

| K | adversarial share | P(vote censored) | censored votes per 800k |
|---|---|---|---|
| 8 | 10 % | 1.0e-08 | 0.008 |
| 8 | 33 % | 1.5e-04 | 122 |
| 16 | 10 % | 1.0e-16 | ~0 |
| 16 | 33 % | 2.3e-08 | 0.02 |

At the tree levels the Wonderboom rule (best + random aggregate) bounds what
a malicious internal aggregator can drop. Votes left out of one slot's tree
can still be included later in the round (dc-networking "uses the whole
round" property).

## Simulation

Shadow 3.3 (with two bug fixes: upload limits and a TCP write stall, see
[sim/README.md](sim/README.md)) and
real rust-libp2p (TCP + noise + yamux): gossipsub with Ethereum parameters vs.
WB-PQ direct delivery. It models what one mainnet node sees: 2 subnets of
~312 members each, on EIP-7870 links (80 % of voters at 50/25 Mbit/s, the
proposer at 100/50). Five slots per run, three topology seeds. Full results:
[results/sim.md](results/sim.md).

| 32-slot round, 2 subnets × 391 votes | gossipsub votes | WB-PQ direct |
|---|---|---|
| bytes received per needed vote byte | **4.2**, because saturated queues drop forwards (5.9 with one subnet; 6.7 when links keep up) | **1.02** |
| subnet vote traffic per slot (312 nodes) | 3.1 GiB | 40 MiB (≈ 80× less) |
| attester-link voter, per slot | 10.1 MiB in + 9.4 MiB out | 0.14 MiB out |
| vote latency p99 / max | 2.3–2.6 s / 3.6–3.8 s (one subnet: 1.1 s / 1.4 s) | 0.42 s / 0.44 s (cold dial: 0.98 s / 1.87 s) |
| votes missing at the deadline | 0.10–0.20 % | 0 |
| proofs | flooding all 32 proofs adds 11–18 MiB per node, spills into the next slot and leaves 8–10 % of votes missing | 0.86 MiB per slot, proposer only |

| 8-slot round, 2 subnets × 1,560 votes | gossipsub votes | WB-PQ direct (8 topics × 16) |
|---|---|---|
| votes missing at the deadline | **16 %** (worst aggregator held 20–25 %) | **0** |
| vote latency p99 | 3.4–3.5 s | 0.43 s |
| internal aggregator (proposer) holds all 16 pulled proofs | – | 1.1–1.4 s after the first is emitted |

The load model uses κ = 6.7, the value measured where links keep up
(`kappa`). On EIP-7870 links the network cannot carry that, and the excess
shows up as dropped, late and missing votes rather than bytes.

## Gasper timing: 32k votes to 128 aggregators, aggregates to a hidden proposer

Shadow with real rust-libp2p, EIP-7870 links, 12 s slots, Gasper phases.
Details: [results/gasper.md](results/gasper.md).

- **Can every one of 32,768 leanSig votes reach all 128 aggregators in 4 s?**
  Yes, with under 1 s of margin, if the aggregators have fast downlinks.
  - Each aggregator downloads 102 MiB in the window (214 Mbit/s). On 1 Gbit
    all 128 had every vote 2.4–2.9 s after voting started (p50), 3.45 s at
    worst. On 50 Mbit/s attester links they had under 3 %.
  - The fan-out of 128 makes the voters' upload the limit: 409 KiB per
    validator per slot. A 25 Mbit/s home node manages ~512 validators (p99
    2.5 s); at 1,024 validators ~1 % of votes miss the deadline.
- **How many 220 KiB aggregates reach the next proposer in 4 s without
  revealing it?**
  - Pushed to a 16-node decoy set that includes the proposer: ~120 for a
    100 Mbit/s builder link, ~60 for a 50 Mbit/s home link.
  - Flooded to every node: ~8. With 16, the worst home node held 56 % at
    the deadline.

## Open questions

- **Subscription registry**: gossip topic vs. ENR field vs. on-chain; how fast
  new subscriptions take effect; minimum stake per subscription.
- **Connection management** at leaf aggregators (thousands of distinct voters
  per epoch); QUIC 0-RTT; whether voters should relay through a few
  long-lived peers instead.
- **Privacy**: direct sends reveal which node hosts which validator to K
  aggregators per vote, no worse than today's subnet fingerprinting (accepted
  for phase 1 in requirements.md), but more targeted.
- **Proving redundancy** (S = 16 provers per topic) vs. censorship resilience;
  incentives for aggregators (EIP-8292 leaves this open too).
- **DoS**: aggregators must verify leanSigs (~100 µs each) before proving;
  rate-limit per connection and per validator index.
