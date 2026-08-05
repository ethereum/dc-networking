---
title: Requirements
---

# Requirements — Fast Finality Networking (dc-voting)

The binding parameter envelope for the design, benchmarking, and PoC efforts.
All three cite this file rather than carrying their own copies of parameters.
Open items are marked with their number in [open_questions.md](../research/open_questions.md);
narrative context lives in [explainer.md](explainer.md); the PoC plan and
milestones in [poc.md](../poc/poc.md).

*Vetted line-by-line by Yann, 2026-07-20. Changes to this file are decisions —
date them.*

## Scope

Two workstreams (see [open_questions.md](../research/open_questions.md)):
**P1** — design of the AC slot / heartbeat-vote delivery;
**P2** — design of the FG voting round over the full validator set (the volume
problem this project exists to solve).

## Actors & scale

- $V$ = validators (signers): design for the $10^6 \to 10^4$ consolidation
  trajectory; the design must work across the whole range.
- $P$ = peers/nodes: $\sim 10^4$, roughly stable.
- Never conflate the two ($V$ drives signing/aggregation volume, $P$ drives
  topology); don't write "$N$".

## Round & timing

- A **round** = one full voting pass of the validator set. A **subround** =
  the voting window of one cohort (a part of the validator set); subrounds are
  pipelined across slots.
- Budget: **8-slot rounds are OK** (~96 s at 12 s slots); **4-slot rounds are
  a stretch goal**, not necessary. In [poc.md](../poc/poc.md) milestone terms: a 4×
  (8-slot) or 8× (4-slot) reduction of today's 32-slot per-validator voting
  cadence.
- Invariant: a subround's votes are **aggregated in the next slot**; the
  vote-start offset X ∈ [0 s, 8 s] within the assigned slot is a tunable
  (latency ↔ healing/robustness).
- Target selection: highest confirmed AC block at T = 4 s + X of the assigned
  slot. *When* the target counts as decided w.r.t. Decoupled Consensus is open
  (Q3).

## Votes & crypto

- **2 vote kinds per height: AC (available chain) votes and FG (finality
  gadget) votes.** The FG vote has a 3-type message alphabet
  (`Vote(B)`, `Vote(⊥)`, `SecondVote(B)`) — a validator casts *one* FG vote
  per height.
- AC votes come from a small committee (PTC-vote-like delivery; P1). FG votes
  come from the **full validator set** (P2).
- Phase-1 wire format: BLS12-381; individual vote ≈ 100 B; aggregates slightly
  larger (participation bitfield).
- Accountability is asymmetric: **only FG (finality) votes are slashable**;
  AC votes are not. Never argue from slashing for non-slashable votes.

## Aggregation

- Aggregation is **required** — votes must land on chain.
- Brokers = aggregators; per-round selection in the style of today's
  `is_aggregator()`. The randomness source (RANDAO vs. VRF) is open (Q7).
- The proposer merges published aggregates at slot *i+2* (vote in slot *i*,
  aggregate in *i+1*, include in *i+2*).

## PQ-forwardness

- Phase 1 ships BLS, but the design must **not foreclose multi-stage /
  more flexible aggregation** — PQ will be multi-stage (Q8, hi), and the
  back-off mechanism (Q9) points the same direction.

## Privacy

- Phase 1 is explicitly **non-private**: the subnet-fingerprinting deanon
  surface (Heimbach, Vonlanthen et al., USENIX Security '25,
  arXiv:2409.04366) is accepted. Privacy improvements are future work
  (Q13, P3).

## Load

- **Low client load is a hard constraint**, tracked *separately* for
  validators and non-validator nodes.
- Networking must not be the binding fault bound: honest-vote delivery should
  survive at least the finality gadget's own Byzantine tolerance.
