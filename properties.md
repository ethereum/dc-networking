---
title: Properties
---

# Networking properties for PQ decoupled consensus

*Draft, 2026-10-20. The I\*/J\* split was dropped on 2026-11-17, after
[ACDC #191](https://forkcast.org/calls/acdc/191) dropped BLS decoupled
consensus.*

What we want from the p2p layer. DC now ships with post-quantum signatures
from the start: votes are hash-based signatures of a few kilobytes, and
aggregation is proof-based and multi-stage ([`research/pq/`](research/pq/README.md)).
There is no BLS phase to keep light and no later PQ fork to stay compatible
with.

## Ground rules

- **Small networking change.** DC is already a big consensus change, so
  networking shouldn't become the critical path.
  - Was: the conservative delta, today's gossip path and one aggregation
    layer ([settled](research/open_questions.md) 2026-07-20). Under PQ one
    layer doesn't carry the load: leaf proofs need a recursion tier before
    the global topic ([Q21](research/open_questions.md)), and whether
    GossipSub carries kilobyte votes at DC volume is open
    ([Q20](research/open_questions.md)).
  - Open: how much of today's pipeline (subnets → aggregators → global
    aggregate topic) survives.
- **PQ from day one.** Every vote and every aggregate is post-quantum.
  - No BLS dependencies: selection proofs, RANDAO reveals, VRF duties
    ([Q24](research/open_questions.md)).
  - Multi-stage aggregation is required, not just "not foreclosed"
    ([Q21](research/open_questions.md)).
  - Proposal (unchanged): bitlists that cover exactly 1/8 of the validator
    set, one slot's worth with 8-slot rounds. That's about 16 KB at ~1M
    validators. What sits next to a proof is open
    ([Q25](research/open_questions.md)).

## Needed

- **Low fork dependence of bitlists.** Forks and reorgs shouldn't force us to
  redo RANDAO, committee assignment and bitlists. Ideally many forks share the
  same bitlist for a long time, so gossip validation never needs a state
  regeneration.
  - Proposal: bitlists change at most about once a day. New validators are
    added only at finality, and exited validators keep their bit, left unset,
    until the next daily update. Activations already wait for finality today
    (phase0 `is_eligible_for_activation`). Alternative: Q18's
    `Active(epoch(round))`.
- **Fair vote timing.** A validator should not be forced to send at a bad
  time, e.g. right before a deadline. This is the same as fairness across
  geolocations and being friendly to home stakers.
  - Proposal: rotate each validator's send time across the slot
    ([Q18](research/fg/staggered-committees/README.md),
    [Q19](research/fg/free-running-committees/README.md)).
- **Fair rewards for validators.** Rewards shouldn't depend on location or on
  which unit you vote in.
  - Proposal: reward one vote per epoch ([incentives](design/incentives.md)).
- **Fair rewards for proposers.** A home staker's proposal should earn about
  as much as a big operator's. It's unfair if most of the rewards stay among
  the big stakers because they aggregate their own votes.
  - Proposal: cap inclusion rewards per proposal ([incentives](design/incentives.md)).
- **Uses the whole round.** Votes that arrive late should still count and
  still pay until the round ends. Then slow validators aren't wasted and
  participation gets close to 100 %.
  - Proposal: late aggregates includable until the round ends; rewards that
    make missing votes valuable ([incentives](design/incentives.md)).
- **Degrades gracefully.** Under bad network conditions we should slow down,
  not stall.
  - Proposal: back-off ([Q9](research/open_questions.md)): fall back to
    about one epoch to finality, much faster otherwise.
- **Reliable.** Votes still make it on chain when the network is degraded:
  slow, lossy or partly partitioned. Not full asynchrony, just tolerance.
  - Open. Related: late votes ([Q17](research/fg/pipelined-units/README.md),
    problem 2); aggregating only at the end of the slot gives aggregators
    longer to collect (Q17, figure 3).

## Also needed

*Were "nice in I\*, needed in J\*". With PQ from day one they count as
needed; to re-tier together.*

- **Fast progress in good conditions.** When most votes arrive early,
  finality should follow quickly. This also keeps the door open for
  fast/slow-path designs.
  - Proposal: count a height as soon as 2/3 is in; don't wait for the end of
    the round.
- **Enables a safety gadget.** A safety gadget needs close to 100 % of votes
  to work. We want epochs where almost every vote lands.
  - Proposal: follows from the [incentives](design/incentives.md).
- **Anonymity enhancing.** Today a validator can be found by the subnets it
  sends to ([Heimbach et al.](https://arxiv.org/abs/2409.04366)). If a node
  only sends in subnets it is subscribed to anyway, its own votes look like
  relaying. It also reduces subnet churn.
  - Proposal: validators stay in the same committee and subnet. Committees
    move across slots but are not shuffled across subnets (Q18: zero subnet
    churn).
- **Enables aggregation builders.** We already accept PBS. Same model here: a
  market of aggregation builders, so any proposer can always get a bid for the
  best aggregate. Aggregation is expensive under PQ: leaf proofs and
  recursion ([`research/pq/`](research/pq/README.md)).
  - Open. Related: [Q12](research/open_questions.md) (optimistic
    aggregation through brokers).

## Conclusions

1. **Prioritization alone gives very uneven rewards.** When a vote can go
   into any of several blocks and proposers just prioritize what they
   include, big operators can choose which blocks carry their votes, e.g.
   only the ones they propose. They collect much more of the rewards and
   grief the other proposers, who have fewer votes left to include. The
   [incentives proposal](design/incentives.md) is meant to counter this.

## Other properties to look at

Not in the list yet, but they are written down elsewhere:

- Low client load, tracked separately for validators and non-validator nodes.
  Networking must not be the binding fault bound ([requirements](design/requirements.md#load)).
- Griefing resistance: lazy aggregators, spam, votes timed at phase boundaries
  ([Q15](research/open_questions.md)).
- Time for epoch/height transitions when votes start early
  ([Q16](research/open_questions.md), [transitions/](research/transitions/README.md)).
- Transition from today's pipeline ([Q14](research/open_questions.md)).
- Orbit SSF goals: solo-staking viability, validator capping
  ([ethresear.ch/t/19928](https://ethresear.ch/t/19928)).

## References

- [requirements.md](design/requirements.md), [incentives.md](design/incentives.md), [open_questions.md](research/open_questions.md)
- PQ-DC: [research/pq/](research/pq/README.md), [ACDC #191](https://forkcast.org/calls/acdc/191)
- Q17 [pipelined units](research/fg/pipelined-units/README.md), Q18 [staggered committees](research/fg/staggered-committees/README.md), Q19 [free-running committees](research/fg/free-running-committees/README.md)
- [2026-10-06 meeting](meetings/2026-10-06.md): keep anchoring the bitfield at finality
- Decoupled consensus: [ethresear.ch/t/24527](https://ethresear.ch/t/24527)
- Validator deanonymization: Heimbach, Vonlanthen et al., USENIX Security '25 ([arXiv:2409.04366](https://arxiv.org/abs/2409.04366)), [ethresear.ch/t/20463](https://ethresear.ch/t/20463)
- 8192 signatures per slot: [ethresear.ch/t/17989](https://ethresear.ch/t/17989)
- PQ replacement for RANDAO: [ethresear.ch/t/24906](https://ethresear.ch/t/24906)
