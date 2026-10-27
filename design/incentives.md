---
title: Incentives
---

# Incentives proposal

*Draft, 2026-10-20. Split out of [properties.md](../properties.md) on 2026-10-27.*

One proposal that covers several of the [networking properties](../properties.md):
fair rewards for validators, fair rewards for proposers, using the whole round,
and enabling a safety gadget. It is meant to counter
[conclusion 1](../properties.md#conclusions): prioritization alone gives very
uneven rewards.

## Proposal

- Validators are rewarded for **at most one vote per epoch**.
- Proposer rewards are **capped per proposal**, at about the proposer's share of
  the slow path (or slightly more). If the slow path takes S slots, one
  proposal pays for at most about V/S votes.

## What this should give us

- Big stakers can't earn much more per proposal than home stakers, so there's
  little gain from aggregating your own votes.
- Towards the end of an epoch, the only votes still paying are the ones nobody
  has included yet, often home stakers'. They become the most valuable votes to
  include, so forgotten votes get picked up at the end of a round.
- Epochs end up with close to 100 % of votes, which is what a safety gadget
  needs.

## Open

- How this fits rounds shorter than an epoch, i.e. what keeps validators
  voting every round if only one vote per epoch is paid.
