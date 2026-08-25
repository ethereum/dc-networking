---
title: Transition timing — epoch/height computation vs. early FG votes
status: wip
---

# Transition timing (epoch / height) vs. early FG votes

*Project started 2026-08-25.*

## Problem

In the current design ([explainer](../../design/explainer.md),
[requirements](../../design/requirements.md)), FG votes are sent early in the
assigned slot — T = 4s + X with X ∈ [0, 8]s, and variants push the vote even
earlier (start of slot, or the tail of the previous slot). Duty assignment
(subround slot, committee/subnet, aggregation duty — and the resulting peer /
subnet subscriptions) is computed "at the epoch transition".

That leaves little or no time between the transition and the first duties that
depend on it: if the boundary computation needs the last block (or the last
votes) of the previous epoch/height, and the first cohort votes at T ≈ 0–4s of
the first slot, the available window is ~one block-propagation delay — or
negative, if votes start in the previous slot. Worse, the FG height cadence is
not slot-aligned: checkpoints can finalize mid-epoch (commonly slot 17/25), so
"height transition" work can be triggered at arbitrary points
([explainer, open checkbox](../../design/explainer.md)).

## Candidate resolutions

1. **Gap slot** — keep the first slot of each epoch/height free of FG duties
   and split the round's cohorts over the remaining 7 slots (costs ~14% more
   per-slot vote volume at 8-slot rounds; interacts with the 4-slot stretch
   goal, where the loss is 33%).
2. **Compute earlier (lookahead)** — define duties so their inputs are frozen
   ≥1 slot (or ≥1 epoch) before they are needed: seed/validator-set snapshots
   from an older state, so the boundary itself computes nothing on the vote's
   critical path.
3. **Compute later / spread (deferral)** — take the heavy bookkeeping
   (rewards, balance updates) off the critical path entirely and amortize it
   over the following slots; only the minimal duty-relevant state is needed at
   the boundary.
4. **Compute in parallel (precompute)** — client-side: run the transition
   speculatively on the pre-state before the boundary (state-advance style),
   patch if a late block changes the inputs.

These are not exclusive; 2–4 compose.

## This project

Survey how other chains schedule epoch/era/session/height-boundary computation
relative to their vote/leader schedule — who uses lookahead snapshots, who
pauses at the boundary, who spreads the computation, and what went wrong when
they didn't. Distill lessons for the DC FG round design.

- [survey.md](survey.md) — per-chain findings + synthesis (start here).
- [boundary-pipelining.md](boundary-pipelining.md) — follow-up (2026-08-25):
  does the justification dependency stall slot-0 votes? Verdict: no bubble
  for p ≥ 76.2%, one-round latency below; certificate-gating is the wrong
  fix; "vote in the previous slot" is effectively broken.

Related: open question Q16 in [open_questions.md](../open_questions.md).
