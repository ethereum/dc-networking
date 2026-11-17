---
title: PQ decoupled consensus — networking starting point
status: wip
date: 2026-11-17
provenance: agent
---

> **Provenance: agent.** Written 2026-11-17 by an agent from the sources Yann collected, with the leanVM numbers re-read from upstream on that date. Yann has not reviewed the text line by line. The arithmetic below is back-of-envelope: one copy per message unless stated, signature bytes only, no headers.

# PQ decoupled consensus: networking

## The decision

- [ACDC #191](https://forkcast.org/calls/acdc/191) (2026-11-12, [ethereum/pm#2291](https://github.com/ethereum/pm/issues/2291)) recorded: "BLS decoupled Consensus is dead; DC work must proceed as PQ-DC only". Shipping BLS DC first and moving to PQ later is no longer an option.
- Still open from the same call:
  - PQ-DC vs PQ Gasper. Ben Edgington suggested PQ Gasper as a quick-deploy fallback and PQ-DC as the primary path. Ansgar Dietrichs mapped the choice to urgency: PQ-DC at "DEFCON 3", a choice between the two at "DEFCON 2".
  - Signature aggregation needs hard evidence either way (Francesco), and several participants named networking the biggest unknown.
- For this repo: there is no BLS phase. BLS-era material moved to [`bls/`](../../bls/README.md).

## Sources

- **leanXMSS** ([leanVM `doc/lean_xmss/main.tex`](https://github.com/leanEthereum/leanVM/blob/main/doc/lean_xmss/main.tex), parameters not final):
  - 2,404 B signature (a 4 B leaf index plus two 1,200 B layers) and a 32 B public key. That is 25× a 96 B BLS signature.
  - Stateful: "a leaf index may sign only one message". A key has 2^32 leaf indices, and the cost section budgets them per 12-second slot.
- **leanVM benchmarks** ([leanethereum.github.io/leanVM](https://leanethereum.github.io/leanVM/), `benchmarks.json` at commit `035eff47a`, read 2026-11-17):
  - Workload: PQ Gasper. 16 subnets × 1,400 leanXMSS per slot, so 716,800 validators = 32 slots × 16 × 1,400.
  - Aggregation (one proof per subnet): 209 KiB, 0.36 s on a 32-core EPYC 9355P to 1.45 s on an 8-core Ryzen 7 PRO 8700GE.
  - Recursion 16 → 1 (one proof per slot): 303 KiB, 0.38–1.52 s on the same machines.
  - These move between commits. An earlier snapshot read 248 / 358 KiB and 0.40–1.57 / 0.43–1.69 s, so cite with the commit.
- **Barnabé Monnot's [pq-aggregation-model](https://github.com/barnabemonnot/pq-aggregation-model)** (v2):
  - Gossip load per node = subnets joined × signatures per subnet × (signature + overhead) × copies.
  - Defaults: 1M validators, 8,000 nodes, 2 backbone subnets, 1.2 KiB signatures, 2 copies. The 1.2 KiB default is an older leanXMSS size; today's is 2,404 B. Our runs of the model counted 4–5 copies per message.
  - Calibrated on Sukun's DC simulation ([P2P call #10](https://forkcast.org/calls/p2p/010)): 500 nodes, 64 subnets, 2,500 votes per subnet, 2 subnets per node, no IDONTWANT. Home nodes peaked at ~40 Mbit/s on 25 Mbit/s links. That run carried **BLS-sized** votes (four bundled attestations: 960 B, or 552 B with EIP-8334).
- **[pqai27](https://ethlabs.org/writings/pqai27.html)** (Ethlabs): PQ decoupled consensus vs PQ Gasper is "the biggest open question"; Gasper is "plausibly the easier change".
- **[Potuz](https://www.potuz.net/posts/pq/)**:
  - Gasper broadcasts ~30K attestations per slot, with 2 KB or 1.2 KB signatures.
  - 300 KB aggregates; 2–3 s final recursion.
  - "We need POCs on the CL right now to see whether gossipsub is even viable".
- **[Decoupled consensus](https://ethresear.ch/t/unblocking-faster-finality-with-decoupled-consensus/24527)**: a 512-member committee per slot; finality votes off the critical path.
- **This repo**: finality votes in 4 s + 4 s units sized like today's attestation slot ([Q17](../fg/pipelined-units/README.md)).
- **Also from ACDC #191**: Kamil Salakhiev's simulations keep 12-second slots with PQ signatures. Csaba offered help on p2p and pointed to [SEACAST](https://notes.ethereum.org/@cskiraly/seacast) for large-message propagation.

## Arithmetic

Signatures per slot = V / round length in slots. An 8-slot round carries **4×** what Gasper's 32-slot epoch carries.

| Schedule | V | Signatures per slot | Leaf proofs (1,400 each) | Recursion levels (≤ 16 children) | Signature bytes per slot, network-wide |
|---|---:|---:|---:|---:|---:|
| PQ Gasper, 32-slot epoch | 716,800 | 22,400 | 16 | 1 | 54 MB |
| PQ-DC, 8-slot round | 716,800 | 89,600 | 64 | 2 | 215 MB |
| PQ-DC, 4-slot round | 716,800 | 179,200 | 128 | 2 | 431 MB |
| PQ Gasper, 32-slot epoch | 1,000,000 | 31,250 | 23 | 2 | 75 MB |
| PQ-DC, 8-slot round | 1,000,000 | 125,000 | 90 | 2 | 301 MB |
| PQ-DC, 4-slot round | 1,000,000 | 250,000 | 179 | 2 | 601 MB |

What follows from it:

1. **Per node, the subnet count decides.**
   - Barnabé's formula with 2 subnets joined, 2,404 B and 4–5 copies (signature bytes only):
     - PQ-DC at 716,800 on 64 subnets puts 1,400 votes in each subnet per slot, the subnet size of leanVM's benchmark. That is about 18–22 Mbit/s received per node.
     - On 16 subnets it would be 72–90 Mbit/s.
   - More subnets move the cost from gossip to aggregation: 64 leaf proofs per slot instead of 16.
   - Compare EIP-7870's 50 / 25 Mbit/s attester budget, and Sukun's BLS run, which already peaked at ~40 Mbit/s.
2. **Leaf proofs cannot all go global.**
   - 64 leaf proofs × 209 KiB = 13 MiB per slot: 9 Mbit/s per copy, 37–46 Mbit/s at 4–5 copies.
   - A recursion tier has to sit between the subnets and the global topic (64 → 4 → 1). The global topic then carries one ~303 KiB proof per slot.
   - This reopens the settled "one aggregation layer" ([open questions](../open_questions.md), 2026-07-20).
3. **Proving vs the 4 s aggregation phase.**
   - At Q17's parity a unit carries V/32 votes, i.e. one PQ Gasper slot, so leanVM's benchmark is per unit (16 leaf proofs, then 16 → 1), three times per slot.
   - A leaf proof plus one recursion step takes 0.75 s (32-core EPYC) to 2.97 s (8-core Ryzen); a second recursion level brings it to 1.13–4.48 s. This is before the ~300 KiB proof propagates.
   - Q17's 4 s aggregation phase is tight on the slower machines, and Q19's 2 s final aggregation does not fit them.
4. **AC votes are no longer near-free.** 512 × 2,404 B ≈ 1.2 MB per slot, sent 512-to-all: 3.3–4.1 Mbit/s per node at 4–5 copies.
5. **XMSS is stateful.**
   - A leaf index signs one message, and the scheme budgets one index per 12-second slot. A validator with an AC vote and an FG vote in the same slot needs two indices or one combined message.
   - leanVM's aggregation groups XMSS claims by (leaf index, message) (code at `9c7d783`, October 2026), so one unit's voters should share an index.
6. **No BLS machinery.**
   - BLS selection proofs (the aggregator lottery), RANDAO reveals and VRF duties all go.
   - Q18's public schedule already needs no per-vote proof. The aggregator lottery and the randomness source still need PQ replacements ([ethresear.ch/t/24906](https://ethresear.ch/t/24906)).

## What changed in this repo

- [`bls/`](../../bls/README.md) holds the BLS-era explainer, the SSZ byte accounting and the early FG notes.
- Q17–Q19 keep their schedule logic. The parts that assume BLS are flagged at the top of each note.
- [`requirements.md`](../../design/requirements.md) is next: votes & crypto, aggregation, PQ-forwardness.
- [`properties.md`](../../properties.md) drops the I\*/J\* split.
- [`../pq-gasper/`](../pq-gasper/README.md): the PQ Gasper alternative, avenues and compromises. Several apply to PQ-DC too, at 4× the per-slot volume.
- All [benchmarking](../../benchmarking/) runs so far carry BLS votes.

## Open questions

Tracked as Q20–Q25 in [`open_questions.md`](../open_questions.md):

- **Q20** per-node gossip load
- **Q21** aggregation tree
- **Q22** PQ-DC vs PQ Gasper volume
- **Q23** XMSS key-index budget
- **Q24** duties without BLS
- **Q25** on-chain objects and slashing evidence
