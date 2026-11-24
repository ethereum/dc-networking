---
title: PQ Gasper — research notes
status: wip
date: 2026-11-24
provenance: agent
---

# PQ Gasper

PQ Gasper keeps today's Gasper consensus and replaces BLS attestations with post-quantum signatures. Start with Yann's [possible avenues and compromises](../../posts/pq-gasper-avenues.md), which was this page until 2026-11-24 and is now in [`posts/`](../../posts/README.md) with the other write-ups.

- [design.md](design.md): how the current spec works, read from the `pq` branch of consensus-specs.
- [aggregator-selection.md](aggregator-selection.md): 4 RANDAO-drawn aggregators against a VRF lottery, for the avenue "Reduce number of Aggregators". Its scripts are in [`sim/`](sim/).
- [gossipsub/](gossipsub/README.md): Shadow simulations of one PQ Gasper subnet, behind the posts [Can PQ Gasper run on gossipsub?](../../posts/pq-gasper-on-gossipsub.md) and [What a node needs to carry one PQ Gasper subnet](../../posts/pq-gasper-subnet-specs.md).
- [builders/sim/](builders/sim/): the scripts behind [Emergency PQ Consensus Could Rely on Builders](../../posts/pq-gasper-builders.md).
