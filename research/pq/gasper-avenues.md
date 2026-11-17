---
title: pqGasper — avenues for the vote path
status: wip
provenance: agent
---

# pqGasper: avenues

> **Scope: pqGasper, not DC.** Today's Gasper (per-slot attesting committees
> over 64 attestation subnets, aggregation as today) with hash-based
> post-quantum signatures. Nothing here assumes decoupled consensus.
>
> *Moved into `research/pq/` on 2026-11-17. The avenues apply to PQ-DC as
> well, at 4× the per-slot volume of an 8-slot round ([README](README.md)).*

**Problem.** A hash-based PQ signature is kilobytes, not BLS's 96 B, and
aggregates only through a SNARK, so every attestation subnet carries a far
heavier vote stream. Today every node relays two subnets of it by default
(`SUBNETS_PER_NODE = 2`, consensus-specs `specs/phase0/p2p-interface.md`) on
an [EIP-7870](https://eips.ethereum.org/EIPS/eip-7870) attester budget of
50 / 25 Mbps.

**Assumed already in:** bundled attestations
([EIP-8334](../../personal/sukun/eip-8334.html)). They trim the shared
`AttestationData` and per-message overhead, but the signature bytes stay.

## Avenues

1. **New vote broadcast + new payload broadcast, e.g. on
   [Waggle](https://github.com/libp2p/specs/pull/732)** (no fixed mesh,
   first-class partial messages, EC broadcast, per-topic priority). Votes and
   payloads both leave GossipSub, so payloads stop competing with votes for
   the same uplink. *Cost:* a new p2p stack and a hard-fork switch-over.
2. **Subnets only for aggregators.** Drop the default two-subnet
   subscription: a node joins a subnet only while one of its validators has
   aggregation duty. Solo stakers otherwise just publish their own vote
   (fanout) and never relay subnet traffic. *Open:* who keeps a subnet's
   backbone and discovery alive, and how Sybil-resistant thin subnets are.
3. **Raise EIP-7870's floor and scale it per validator.** Raise the attester
   bandwidth floor, and make the recommendation grow with the number of
   validators a node runs, so large operators are budgeted for load in
   proportion to their stake. *Cost:* a higher bar for solo stakers, and
   7870 is a recommendation that nothing enforces.
4. **Builders aggregate.** Hand the aggregation duty to builders, who already
   run well-provisioned infrastructure; validators send votes to them.
   *Cost:* vote inclusion and liveness depend on a few builders (vote
   censorship, incentives).
5. **Drop vote privacy: send direct to ≤ 128 aggregators.** A validator sends
   its vote point-to-point to its committee's aggregators (up to 128), with
   no gossip in between. *Cost:* aggregators learn which IP runs which
   validator. Cf. P4 in [`open_questions.md`](../open_questions.md).

## Other avenues (flagged, not worked out)

- **Fewer signatures:** lean harder on consolidation (EIP-7251). Vote count
  scales with validator count, not stake.
- **Smaller signatures:** tune the hash-based scheme for size over
  verification cost.
- **Fewer voters per slot or a slower FFG cadence:** this changes the
  consensus rather than the network. It is DC's route, so out of scope here.
