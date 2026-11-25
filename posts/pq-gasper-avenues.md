# PQ Gasper - Possible Avenues / Compromises

**Problem.** Based on [Shadow simulations we have been running](pq-gasper-on-gossipsub.md), it doesn't seem to me that we can disseminate ~1'600 PQ attestations per subnet in ~4 seconds, if we keep everything else equal. This would be needed if we want 16 subnets with 800k validators. See also Anton's simulations: https://github.com/Nashatyrev/jvm-libp2p/blob/pq-gasper/pq-gasper.md

This is a short list of possible changes that I think *might* make PQ Gasper work (either on their own, or combined).

> Note: I'm not saying any of these are good (quite the opposite in fact, to me it seems that doing PQ-DC seems preferable), this is purely intended to understand the trade-offs better.

---

## With LeanVM

1. **Delay vote inclusion:** Proposers of slot N include attestations from slot N-2, instead of N-1. Benefit: More time for proposers to obtain the aggregate. The critical path is now getting attestations to all nodes by t = 3s of the following slot for fork choice (so 12 seconds total, instead of 9 seconds)\
   *Cost:* manageable cost in spec changes, but also not a silver bullet
2. **Solo stakers only subscribe to subnets for aggregator duty.** Drop the default two-subnet subscription. Solo stakers can still provide aggregator duties though.\
   *Cost:* changes in security assumptions, given solo stakers won't be in the backbone anymore.
3. **Raise EIP-7870's floor and scale it per validator.** Raise the attester bandwidth floor, and make the recommendation grow with the number of validators a node runs, so large operators are budgeted for load in proportion to their stake.\
   *Cost:* a higher bar for solo stakers
4. **Fully new vote broadcast + new payload broadcast, e.g. on waggle** (first-class partial messages, EC broadcast, per-topic priority, etc.).\
   *Cost:* a new p2p stack and a hard-fork switch-over, **not clear if enough on its own.**
5. **Drop vote privacy: send attestations directly to ~128 aggregators.** A validator sends its vote point-to-point to its committee's aggregators (up to 128), with no gossip in between.\
   *Cost:* aggregators learn which IP runs which validator, not permissionless, changes security assumptions
6. **Rely on Builders to aggregate.** They already run well-provisioned infrastructure; validators send votes to them. See [the builders post](pq-gasper-builders.md).\
   *Cost:* vote inclusion and liveness depend on a few builders (vote censorship, incentives, not CROPS).
7. **Attester Cap:** lean harder on consolidation or validator capping to have fewer signatures.\
   *Cost:* Could worsen decentralization.
8. **Longer time to finality:** Fewer voters per slot aka slower FFG cadence.\
   *Cost:* Worse UX, also seems dangerous given insecurity of Gasper.
9. **Longer slots:** Go from 12 seconds to say 24 seconds.\
   *Cost:* Worse UX, costly on many levels
10. **Reduce number of Aggregators:** E.g., from 16 to 4.\
    *Cost:* Worse security, worse fairness.

## Without LeanVM

1. **Drastic Validator Cap:** We can probably add ~500 signatures per block (similar to PQ Goldfish requirement - +1MB per block). This means we would need a validator cap of ~16k to make PQ Gasper work without LeanVM.
2. **Longer time to finality:** 500 signatures per block, with 1M validators leads to > 10 hours time to finality.
