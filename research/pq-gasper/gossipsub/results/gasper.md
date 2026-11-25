# Gasper timing: 32k PQ votes to 128 aggregators, and aggregates to a hidden proposer

Two questions for 12 s slots with Gasper's 4 s phases (vote at 4 s, aggregate
at 8 s, propose at 12 s), with post-quantum votes (leanSig, 3,272 B on the
wire) and real rust-libp2p in Shadow on EIP-7870 links:

1. **Votes:** are 4 s enough for all 32,768 votes of a slot (≈ 1.05M
   validators / 32) to reach **all 128 aggregators**?
2. **Aggregates:** how many 220 KiB aggregates can be pushed to the next
   proposer between 8 s and 12 s **without revealing which node is the
   proposer**?

Line-rate bounds are in [model.md](model.md) (`gasper()` in
[load_model.py](../model/load_model.py)). How to reproduce:
[sim/README.md](../sim/README.md). All runs use the patched Shadow (both 3.3
bugs fixed, see below).

## Answers

**Q1: yes, with margin under 1 s, if two conditions hold:**
- **The 128 aggregators have fast downlinks.** Each one receives 102 MiB
  in the 4 s window (214 Mbit/s). On 1 Gbit links all 128 held 100 % of the
  votes in every slot of every run. Aggregators on EIP-7870 attester links
  (50 Mbit/s down) are starved: in the run with 32 of them, they held
  0.6–2.6 % of votes at the deadline. Only the small home-node batches
  finished; the operators' 2 MiB batches were all still in flight.
- **No node uploads more than its link allows.** Every vote goes out 128
  times (409 KiB per validator per slot), so the bottleneck is the voters'
  upload, not the aggregators.
  - EIP-7870 attester link (25 Mbit/s up): fine up to ~512 validators per
    node (16 votes per slot: p99 2.5 s); at 1,024 validators the p99 is
    3.8 s and ~1 % of votes miss the deadline.
  - 15 Mbit/s "minimum tested" upload: 512 validators already reaches a
    p99 of 3.8 s.
  - 1 Gbit operator nodes carrying 16–22k validators each (200–270 MiB of
    upload per slot) set the pace. Aggregators held everything 2.4–2.9 s
    after voting started (p50) and 3.2–3.45 s at worst.
- With leanVM-XMSS votes (1.37 KiB) everything is ~2.4× lighter: all votes
  in by 2.9 s.

**Q2: about 120 aggregates for a builder-link proposer and 60 for a home
proposer if they are pushed to a decoy set; only ~8 if they are flooded to
every node.**

| how aggregates reach the proposer | proposer hidden among | 100 % held at 12 s, builder link (100 Mbit/s down) | home link (50 Mbit/s down) |
|---|---|---|---|
| pushed directly to 16 nodes, the proposer one of them | 16 nodes | **~120**: 64 all in 2.5 s; 128 → 99.5 % | **~60**: 32 all in 1.9 s; 64 → 99 % |
| flooded on a topic every node joins | every node | ≥ 32 (all 32 in 2.0 s) | **~8**: 8 → worst node 88 %; 16 → worst 56 %, mean 96 % |

- The proposer's downlink is the limit for direct pushes. Shadow reaches
  ~55 % of line rate (the bound is 222 and 111) because 128 concurrent TCP
  flows start in slow start in the same instant.
- Flooding hides the proposer best but makes every node carry every
  aggregate several times. Home nodes' 25 Mbit/s uplinks then throttle the
  whole mesh, so a home-staker proposer may miss most of them.
- A decoy set costs each aggregator 16 uploads of its 220 KiB (3.4 MiB,
  27 ms on 1 Gbit). Every decoy downloads as much as the proposer, so decoys
  need comparable links.

These are two parameter sweeps of the same simulator, not two projects:
Q1 changes the vote fan-out (128 recipients, batched votes), Q2 the proof
delivery (`--proofs decoy|flood`).

## Q1 setup

- 224 hosts: 128 aggregators (1 Gbit unless stated), 1 proposer, 95 voter
  nodes. Shadow memory limits the host count, so voter nodes are larger than
  on mainnet:
  - home nodes on EIP-7870 attester links (50/25 Mbit/s) with 4 votes per
    slot (128 validators) unless stated;
  - 1 Gbit operator nodes carrying the remaining ~32,600 votes: 48–86 nodes
    with 381–679 votes each (12–22k validators per node).
- A node signs all its validators' votes at one instant (4.0–4.5 s) and
  sends them to each aggregator as one message (`--batch-votes`), as
  clients do today. Same bytes as one message per vote.
- Deadline 8 s; 5 slots per run; seeds 1–3 for the base case.

### Base case and fewer, smaller operator nodes

| metric | q1-s1 | q1-s2 | q1-s3 | q1-ops-s1 |
|---|---|---|---|---|
| mode | direct | direct | direct | direct |
| profile / seed | eip7870-mix / 1 | eip7870-mix / 2 | eip7870-mix / 3 | eip7870-mix / 1 |
| hosts | 224 | 224 | 224 | 224 |
| subnets × votes per subnet | 1 × 32,768 | 1 × 32,768 | 1 × 32,768 | 1 × 32,768 |
| direct topics × recipients | 1 × 128 | 1 × 128 | 1 × 128 | 1 × 128 |
| slots analysed | 5 | 5 | 5 | 5 |
| vote latency p50/p90/p99/max (ms) | 2026/2405/2700/2973 | 1401/1916/2470/2746 | 1736/1977/2404/2800 | 1096/1418/2125/3612 |
| vote latency p99 by voter link (ms) | attester 721, cloud 2702 | attester 725, cloud 2470 | attester 717, cloud 2405 | attester 716, cloud 2125 |
| votes held at deadline: min / mean | 100.0% / 100.00% | 100.0% / 100.00% | 100.0% / 100.00% | 98.8% / 100.00% |
| aggregators with 100 % (of agg·slots) | 640/640 | 640/640 | 640/640 | 640/640 |
| time to 100 % of votes after vote start: p50 / max (s) | 2.86 / 3.45 | 2.36 / 3.22 | 2.42 / 3.27 | 1.87 / 5.84 |
| proposer: proofs per slot (min–max) | 2–2 | 2–2 | 2–2 | 2–2 |
| proposer: 1st / last proof after 1st emitted (s) | 0.38 / 0.60 | 0.43 / 0.95 | 0.51 / 0.95 | 0.39 / 0.60 |
| proofs | pull | pull | pull | pull |
| proofs emitted per slot | 128 | 128 | 128 | 128 |
| network bytes received in vote phase / slot | 13,088.8 MiB | 13,088.8 MiB | 13,088.8 MiB | 13,088.7 MiB |
| bytes received per needed vote byte (κ) | 1.00 | 1.00 | 1.00 | 1.00 |
| errors | 0 | 0 | 0 | 0 |

`q1-ops-s1` spreads the operator votes over 86 nodes (381 votes each). It is
faster on the median (1.9 s), but one aggregator in one slot missed one
node's 381 votes: that single connection took 5.6 s, then 3.6 s in the next
slot. One slow TCP flow out of 128 parallel ones is enough to miss the
deadline.

### Variants (seed 1)

| metric | q1-av16-s1 | q1-av32-s1 | q1-min-av16-s1 | q1-mixagg-s1 | q1-xmss-s1 |
|---|---|---|---|---|---|
| mode | direct | direct | direct | direct | direct |
| profile / seed | eip7870-mix / 1 | eip7870-mix / 1 | eip7870-min / 1 | eip7870-mix / 1 | eip7870-mix / 1 |
| hosts | 224 | 224 | 224 | 224 | 224 |
| subnets × votes per subnet | 1 × 32,768 | 1 × 32,768 | 1 × 32,768 | 1 × 32,768 | 1 × 32,768 |
| direct topics × recipients | 1 × 128 | 1 × 128 | 1 × 128 | 1 × 128 | 1 × 128 |
| slots analysed | 5 | 5 | 5 | 5 | 5 |
| vote latency p50/p90/p99/max (ms) | 1998/2366/2683/2958 | 1975/2328/2904/3989 | 2004/2373/2838/3934 | 1573/1913/2538/3569 | 915/1225/2165/2406 |
| vote latency p99 by voter link (ms) | attester 2498, cloud 2684 | attester 3783, cloud 2665 | attester-15up 3774, cloud 2675 | attester 1114, cloud 2539 | attester 444, cloud 2165 |
| votes held at deadline: min / mean | 100.0% / 100.00% | 96.1% / 99.15% | 98.3% / 99.91% | 0.6% / 75.15% | 100.0% / 100.00% |
| aggregators with 100 % (of agg·slots) | 640/640 | 640/640 | 640/640 | 480/640 | 640/640 |
| time to 100 % of votes after vote start: p50 / max (s) | 2.82 / 3.44 | 4.33 / 5.42 | 3.69 / 4.84 | 2.34 / 3.21 | 1.60 / 2.90 |
| proposer: proofs per slot (min–max) | 2–2 | 2–2 | 2–2 | 2–2 | 2–2 |
| proposer: 1st / last proof after 1st emitted (s) | 0.39 / 0.60 | 0.39 / 0.60 | 0.39 / 0.60 | 0.47 / 0.74 | 0.39 / 0.57 |
| proofs | pull | pull | pull | pull | pull |
| proofs emitted per slot | 128 | 128 | 128 | 128 | 128 |
| network bytes received in vote phase / slot | 13,088.8 MiB | 12,980.4 MiB | 13,078.8 MiB | 10,988.7 MiB | 5,464.8 MiB |
| bytes received per needed vote byte (κ) | 1.00 | 0.99 | 1.00 | 0.84 | 1.00 |
| errors | 0 | 0 | 0 | 2772 | 0 |

- `q1-av16`, `q1-av32`: home nodes with 16 and 32 votes per slot (512 and
  1,024 validators). 32 votes are 13 MiB per slot at 25 Mbit/s, 4.3 s:
  aggregators held 99.15 % on average at the deadline, the worst 96.1 %.
- `q1-min-av16`: 16 votes per slot at 15 Mbit/s upload: p99 3.8 s, worst
  aggregator 98.3 %.
- `q1-mixagg`: 32 of the 128 aggregators at attester limits (50/25). They
  never get the 102 MiB in time. The errors are vote requests to them timing
  out after 20 s.
- `q1-xmss`: leanVM-XMSS votes (1,198 + 168 B).

**Per-node bytes per slot (mean), vote phase [0 s, 8 s) and proof phase [8 s, 12 s)**

| run | node class | votes rx | votes tx | proofs rx | proofs tx |
|---|---|---|---|---|---|
| q1-s1 | aggregator | 102.25 MiB | 0.00 MiB | 0.00 MiB | 0.00 MiB |
| q1-s1 | proposer | 0.00 MiB | 0.00 MiB | 0.44 MiB | 0.00 MiB |
| q1-s1 | voter-attester | 0.00 MiB | 1.60 MiB | 0.00 MiB | 0.00 MiB |
| q1-s1 | voter-cloud | 0.00 MiB | 271.11 MiB | 0.00 MiB | 0.00 MiB |
| q1-s2 | aggregator | 102.25 MiB | 0.00 MiB | 0.00 MiB | 0.00 MiB |
| q1-s2 | proposer | 0.00 MiB | 0.00 MiB | 0.44 MiB | 0.00 MiB |
| q1-s2 | voter-attester | 0.00 MiB | 1.60 MiB | 0.00 MiB | 0.00 MiB |
| q1-s2 | voter-cloud | 0.00 MiB | 203.73 MiB | 0.00 MiB | 0.00 MiB |
| q1-s3 | aggregator | 102.25 MiB | 0.00 MiB | 0.00 MiB | 0.00 MiB |
| q1-s3 | proposer | 0.00 MiB | 0.00 MiB | 0.44 MiB | 0.00 MiB |
| q1-s3 | voter-attester | 0.00 MiB | 1.60 MiB | 0.00 MiB | 0.00 MiB |
| q1-s3 | voter-cloud | 0.00 MiB | 213.67 MiB | 0.00 MiB | 0.00 MiB |
| q1-ops-s1 | aggregator | 102.25 MiB | 0.00 MiB | 0.00 MiB | 0.00 MiB |
| q1-ops-s1 | proposer | 0.00 MiB | 0.00 MiB | 0.44 MiB | 0.00 MiB |
| q1-ops-s1 | voter-attester | 0.00 MiB | 1.60 MiB | 0.00 MiB | 0.00 MiB |
| q1-ops-s1 | voter-cloud | 0.00 MiB | 152.02 MiB | 0.00 MiB | 0.00 MiB |

## Q2 setup

- 312 hosts, EIP-7870 mix (80 % of non-aggregators at 50/25 Mbit/s, 20 % at
  1 Gbit); N aggregators on 1 Gbit, each with a 220 KiB aggregate ready at
  8.0 s; deadline 12 s (next slot). 3 slots per run.
- `decoy`: every aggregator pushes its aggregate to the same 16 nodes,
  the proposer and 15 random others. Proposer on a builder link (100/50) or
  a home link (`decoyhome`, 50/25).
- `flood`: aggregates gossiped on a topic all 312 nodes join (Ethereum
  gossipsub parameters). The proposer could be any node, so the table reports
  every node by link. N = 64 did not fit in 31 GB of memory.

### Decoy push

| metric | q2-decoy-n16 | q2-decoy-n32 | q2-decoy-n64 | q2-decoy-n128 | q2-decoy-n192 | q2-decoyhome-n16 | q2-decoyhome-n32 | q2-decoyhome-n64 | q2-decoyhome-n128 | q2-decoyhome-n192 |
|---|---|---|---|---|---|---|---|---|---|---|
| mode | direct | direct | direct | direct | direct | direct | direct | direct | direct | direct |
| profile / seed | eip7870-mix / 1 | eip7870-mix / 1 | eip7870-mix / 1 | eip7870-mix / 1 | eip7870-mix / 1 | eip7870-mix / 1 | eip7870-mix / 1 | eip7870-mix / 1 | eip7870-mix / 1 | eip7870-mix / 1 |
| hosts | 312 | 312 | 312 | 312 | 312 | 312 | 312 | 312 | 312 | 312 |
| subnets × votes per subnet | 1 × 384 | 1 × 384 | 1 × 384 | 1 × 384 | 1 × 384 | 1 × 384 | 1 × 384 | 1 × 384 | 1 × 384 | 1 × 384 |
| direct topics × recipients | 1 × 16 | 1 × 32 | 1 × 64 | 1 × 128 | 1 × 192 | 1 × 16 | 1 × 32 | 1 × 64 | 1 × 128 | 1 × 192 |
| slots analysed | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 |
| vote latency p50/p90/p99/max (ms) | 121/280/426/439 | 127/284/426/449 | 146/300/437/485 | 195/361/483/3476 | 270/564/997/3914 | 121/280/426/439 | 127/284/426/449 | 146/300/437/485 | 195/361/483/2020 | 270/565/1027/3911 |
| vote latency p99 by voter link (ms) | attester 427, cloud 420 | attester 429, cloud 420 | attester 441, cloud 420 | attester 493, cloud 421 | attester 1414, cloud 421 | attester 427, cloud 420 | attester 429, cloud 420 | attester 441, cloud 420 | attester 493, cloud 421 | attester 1443, cloud 421 |
| votes held at deadline: min / mean | 100.0% / 100.00% | 100.0% / 100.00% | 100.0% / 100.00% | 99.0% / 99.99% | 97.1% / 99.81% | 100.0% / 100.00% | 100.0% / 100.00% | 100.0% / 100.00% | 99.0% / 99.99% | 96.6% / 99.83% |
| aggregators with 100 % (of agg·slots) | 48/48 | 96/96 | 192/192 | 376/384 | 535/576 | 48/48 | 96/96 | 192/192 | 376/384 | 546/576 |
| time to 100 % of votes after vote start: p50 / max (s) | 0.90 / 0.93 | 0.80 / 0.93 | 0.82 / 0.95 | 0.96 / 3.88 | 1.77 / 10.45 | 0.90 / 0.93 | 0.80 / 0.93 | 0.82 / 0.95 | 0.95 / 2.21 | 1.68 / 9.58 |
| proposer: proofs per slot (min–max) | 16–16 | 32–32 | 64–64 | 128–128 | 189–192 | 16–16 | 32–32 | 64–64 | 85–128 | 22–190 |
| proposer: 1st / last proof after 1st emitted (s) | 0.07 / 0.54 | 0.07 / 1.18 | 0.17 / 2.50 | 0.23 / 4.12 | 0.20 / 4.95 | 0.08 / 1.49 | 0.10 / 1.88 | 0.28 / 4.14 | 0.37 / 6.88 | 0.52 / 10.65 |
| proofs | decoy (16 decoys) | decoy (16 decoys) | decoy (16 decoys) | decoy (16 decoys) | decoy (16 decoys) | decoy (16 decoys) | decoy (16 decoys) | decoy (16 decoys) | decoy (16 decoys) | decoy (16 decoys) |
| proofs emitted per slot | 16 | 32 | 64 | 128 | 192 | 16 | 32 | 64 | 128 | 192 |
| proposer: share of proofs held at slot end, min / mean | 100% / 100.0% | 100% / 100.0% | 100% / 100.0% | 99% / 99.5% | 75% / 85.6% | 100% / 100.0% | 100% / 100.0% | 98% / 99.0% | 22% / 28.9% | 10% / 10.8% |
| network bytes received in vote phase / slot | 19.6 MiB | 39.2 MiB | 78.6 MiB | 219.1 MiB | 409.9 MiB | 19.6 MiB | 39.2 MiB | 78.6 MiB | 224.0 MiB | 423.8 MiB |
| bytes received per needed vote byte (κ) | 1.02 | 1.02 | 1.02 | 1.43 | 1.78 | 1.02 | 1.02 | 1.03 | 1.46 | 1.84 |
| errors | 0 | 0 | 0 | 29 | 54 | 0 | 0 | 0 | 29 | 40 |

The errors at N ≥ 128 are pushes to 50 Mbit/s decoys timing out after 20 s:
the decoys get the same flood as the proposer.

### Flood to every node

| metric | q2-flood-n8 | q2-flood-n16 | q2-flood-n32 |
|---|---|---|---|
| mode | direct | direct | direct |
| profile / seed | eip7870-mix / 1 | eip7870-mix / 1 | eip7870-mix / 1 |
| hosts | 312 | 312 | 312 |
| subnets × votes per subnet | 1 × 384 | 1 × 384 | 1 × 384 |
| direct topics × recipients | 1 × 8 | 1 × 16 | 1 × 32 |
| slots analysed | 3 | 3 | 3 |
| vote latency p50/p90/p99/max (ms) | 120/273/423/425 | 121/280/426/440 | 131/300/779/2738 |
| vote latency p99 by voter link (ms) | attester 424, cloud 420 | attester 427, cloud 420 | attester 897, cloud 420 |
| votes held at deadline: min / mean | 100.0% / 100.00% | 100.0% / 100.00% | 100.0% / 100.00% |
| aggregators with 100 % (of agg·slots) | 24/24 | 48/48 | 96/96 |
| time to 100 % of votes after vote start: p50 / max (s) | 0.88 / 0.91 | 0.90 / 0.93 | 0.93 / 2.84 |
| proposer: proofs per slot (min–max) | 8–8 | 16–16 | 32–32 |
| proposer: 1st / last proof after 1st emitted (s) | 0.18 / 0.55 | 0.24 / 1.65 | 0.14 / 1.97 |
| proofs | flood | flood | flood |
| proofs emitted per slot | 8 | 16 | 32 |
| proposer: share of proofs held at slot end, min / mean | 100% / 100.0% | 100% / 100.0% | 100% / 100.0% |
| any node: share of proofs held at slot end, min / mean, by link | attester 88% / 99.9%, builder 100% / 100.0%, cloud 100% / 100.0% | attester 56% / 95.7%, builder 100% / 100.0%, cloud 100% / 100.0% | attester 41% / 78.6%, builder 100% / 100.0%, cloud 97% / 100.0% |
| network bytes received in vote phase / slot | 34.2 MiB | 290.8 MiB | 926.3 MiB |
| bytes received per needed vote byte (κ) | 3.57 | 15.17 | 24.16 |
| errors | 0 | 0 | 0 |

**Per-node bytes per slot (mean)**

| run | node class | votes rx | votes tx | proofs rx | proofs tx |
|---|---|---|---|---|---|
| q2-flood-n8 | aggregator | 1.22 MiB | 0.07 MiB | 7.93 MiB | 31.32 MiB |
| q2-flood-n8 | proposer | 0.07 MiB | 0.00 MiB | 10.33 MiB | 7.25 MiB |
| q2-flood-n8 | voter-attester | 0.10 MiB | 0.05 MiB | 8.61 MiB | 7.74 MiB |
| q2-flood-n8 | voter-cloud | 0.02 MiB | 0.03 MiB | 7.61 MiB | 8.78 MiB |
| q2-flood-n16 | aggregator | 1.56 MiB | 0.21 MiB | 13.49 MiB | 34.62 MiB |
| q2-flood-n16 | proposer | 0.86 MiB | 0.01 MiB | 18.48 MiB | 9.84 MiB |
| q2-flood-n16 | voter-attester | 1.09 MiB | 0.45 MiB | 10.84 MiB | 11.33 MiB |
| q2-flood-n16 | voter-cloud | 0.27 MiB | 0.08 MiB | 13.02 MiB | 13.19 MiB |
| q2-flood-n32 | aggregator | 2.94 MiB | 0.20 MiB | 20.55 MiB | 32.30 MiB |
| q2-flood-n32 | proposer | 1.70 MiB | 0.00 MiB | 23.32 MiB | 14.76 MiB |
| q2-flood-n32 | voter-attester | 3.37 MiB | 2.50 MiB | 11.18 MiB | 13.86 MiB |
| q2-flood-n32 | voter-cloud | 1.69 MiB | 0.18 MiB | 21.98 MiB | 21.40 MiB |

## Shadow fixes these runs depend on

Shadow 3.3.0 has two bugs that affect this workload. Both are patched in
[sim/shadow-3.3-fixes.patch](../sim/shadow-3.3-fixes.patch):

1. **Host upload limits are ignored.** `sim_config.rs` builds
   `bandwidth_up_bits` from `bandwidth_down`, so every host uploads at its
   download rate. A 2-host check (50 down / 15 up) moved 6.7 MB in 1.1 s
   before the fix and 3.7 s after. Already fixed on Shadow main.
2. **65,535-byte send cap** that stalls tokio writers (proof-pull hang; see
   [sim/README.md](../sim/README.md#shadow-needs-two-patches)).

## Limits

- Fewer, larger voter nodes than mainnet (Shadow memory). Mainnet has ~10k
  nodes with ~100 validators each on average, which spreads the upload; the
  operator-node results here are pessimistic.
- Verification and proving are not modelled: an aggregator that must verify
  32,768 leanSigs (~3 s at 100 µs each on one core) needs several cores.
- No packet loss.
- The decoy set is given. Forming it without leaking the proposer is a
  protocol question this simulation does not answer. A relay hop
  (aggregator → relay → proposer) would add one RTT plus the same transfer
  again.
