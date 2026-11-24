---
title: PQ Gasper on gossipsub — Shadow simulations of one subnet
status: wip
date: 2026-11-24
provenance: agent
---

# PQ Gasper on gossipsub: Shadow simulations

PQ Gasper keeps today's Gasper consensus and replaces BLS attestations with post-quantum signatures. The studies here test whether gossipsub can carry those signatures, in Shadow, with real rust-libp2p nodes on a network calibrated against mainnet.

**Not at 1,600 signatures per subnet.** With 800k validators, PQ Gasper puts about 1,600 signatures per slot in each of 16 subnets. On 2,048 nodes, one such subnet fails for home nodes: in the worst slot only 23 % of 50/15 nodes and 53 % of 50/25 nodes hold every signature at 8 s. Every class passes up to 300 signatures per subnet per slot. The [post](../../../posts/pq-gasper-on-gossipsub.md) gives the short version with charts.

## Layout

- [posts/pq-gasper-on-gossipsub.md](../../../posts/pq-gasper-on-gossipsub.md): the post, in the repository's [posts/](../../../posts/README.md). `posts/charts/generate_charts.py` draws its two charts.
- [posts/pq-gasper-subnet-specs.md](../../../posts/pq-gasper-subnet-specs.md): the follow-up post, on the link a node needs to carry the subnet.
- [results/pq-gasper-one-subnet.md](results/pq-gasper-one-subnet.md): the study behind the post, with every run.
- [results/pq-gasper-subnet-specs.md](results/pq-gasper-subnet-specs.md) and [results/pq-gasper-subnet-specs-1024.md](results/pq-gasper-subnet-specs-1024.md): the follow-up study, on 2,048 and on 1,024 nodes, with every run. It varies the home links of the 1,600-signature subnet to find the link a node needs.
- [results/realism-calibration.md](results/realism-calibration.md): the network perturbations, each validated on its own, and their calibration against today's mainnet. Calibration on the later builds is in the Calibration section of [superseded/gossip-one-subnet-realistic.md](superseded/gossip-one-subnet-realistic.md).
- [results/gossipsub-scoring-by-client.md](results/gossipsub-scoring-by-client.md): how each client scores and drops slow peers, read from their source code.
- [sources.md](sources.md): the facts taken from leanVM, pq-aggregation-model, pqai27, Potuz's post and dc-networking.
- WB-PQ, the original proposal, where aggregators subscribe to a topic and receive its votes directly instead of by gossip (Wonderboom-style, close to the direct-to-aggregators avenue in the [PQ Gasper note](../README.md)): [DESIGN.md](DESIGN.md), [model/load_model.py](model/load_model.py) → [results/model.md](results/model.md), [results/gasper.md](results/gasper.md) and [results/sim.md](results/sim.md).
- [sim/](sim/README.md): the experiment generator, the wbsim node, the network perturbations, and the Shadow and gossipsub patches.
- [p2psims/](p2psims/README.md): the run and analysis scripts, per-run analysis outputs and the run registry from the machine that ran the simulations.
- [superseded/](superseded/README.md): superseded studies, post drafts and charts, and why each was superseded.

Not included: the raw runs (338 GB); the mainnet node crawl that the generator samples validator counts from, because it maps validators to nodes ([p2psims/README.md](p2psims/README.md) says how to check a replacement); binaries and build output; and the vendored gossipsub crate, which [sim/README.md](sim/README.md) rebuilds from the two patches.
