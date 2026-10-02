---
title: Staggered FG committees — who votes when, who votes together, and what it takes to validate
status: wip
date: 2026-10-02
provenance: agent
---

> **Provenance: agent.** Written 2026-10-02 by an agent study that Yann commissioned after the FF design discussion of 2026-10-01/02 on staggered committees. Three lanes (schedule, network, anchor) did the work, two red-team reviewers checked it ([Appendix B](#appendix-b-red-team-findings-and-resolutions)), and this note is the synthesis. Yann has not reviewed the text line by line. The design ideas come from that discussion and are credited by name:
> - Francesco D'Amato: committees as load units, deterministic rotation, the target-epoch index set.
> - Mikhail Kalinin: enforced windows, the instant height switch, the DC state-transition draft.
> - Potuz and Terence Tsao: state-free p2p validation as a hard requirement.
> - Roberto Saltini: the anchor carried in the vote.
> - Barnabé Monnot: heavy-first ordering.
> - Anton Nashatyrev: traffic simulations.
> - Yann: the three properties, and the operator-concentration and single-operator-committee concerns.
>
> **Nonbinding.** This answers [Q18](../../open_questions.md) with a concrete strawman. It does not modify [`requirements.md`](../../../design/requirements.md), the [explainer](../../../design/explainer.md) or [Q17](../pipelined-units/README.md). Where a lane note differs from this README, the README is normative (each lane note lists what it supersedes).

# Staggered FG committees

## TL;DR

Under decoupled consensus (DC), every validator casts one finality-gadget (FG) vote per round, in one 4 s **unit** (Q17 grid: 23 units per 8-slot round). Heights justify as soon as 2/3 of stake agrees, and voters switch to the next height immediately.

The thread's premise holds. **Committees are not a security unit** (FF chat, 2026-10-01). They exist for load, bitfield size and timing enforcement. Each design question then has a clear answer:

1. **Position (who votes when).**
   - Use a public, deterministic seat. Each cohort moves **one unit *later* every 8 rounds**: `seat = (cohort + ⌊round/8⌋) mod C`.
   - Fixed order is latency-optimal, and this rotation costs **0.4%** of that (0.699 vs 0.696 rounds/height at full participation).
   - **Direction matters.** Moving cohorts *earlier* (the direction of the DC draft's shift) or reshuffling gives one cohort a gap of 2C−1 units. That means **~2 rounds per height near the 2/3 threshold**, against 1.13–1.17 for fixed order or forward rotation.
   - The rotation is ε-fair after **5.8 h**. A fixed seat is 1.74 pp worse forever, and the draft's one-validator slide takes 3.6 years to even out.
2. **Composition (who votes together).**
   - Re-draw who shares a cohort and a subnet **once per era of 256 epochs (~27 h)**, as a hash of an era seed and the validator index.
   - The seed is the RANDAO mix of epoch (era start − 5), revealed ~4 epochs ahead. Era boundaries sit at fixed epochs; they never wait for finality.
   - This is required, not a nicety. A rotation never changes composition. Under any *fixed* composition, a 10% adversary can own ⅓ of a cohort in **4–8 days** by choosing consolidation targets. Contiguous index blocks (the DC draft) already give the largest operator **18.4%** of a unit, against 9.4% overall, and leave **6.5%** of committees single-operator.
   - **Invariant (zero slack today):** `EPOCHS_PER_FG_ERA + 5 ≤ 5 + MIN_VALIDATOR_WITHDRAWABILITY_DELAY` (261 ≤ 261).
   - An era boundary costs one ~0.5-round delay per day (0.05%).
3. **Index set and anchor (what bits mean, and what state validates them).**
   - Use **`Active(epoch(round))`**. It is fixed once epoch E−5 has been processed, so it can be cached by `(E, D(E))`, where D(E) is the last block at or before the end of epoch E−5.
   - That root is finalized whenever finality lags by ≤ 129 slots (25.8 min). **Gossip never needs a checkpoint state and never regenerates one per message.**
   - Aggregates name their D(E) (+32 B, signed by the aggregator).
   - Single votes are checked against the node's own (E, D(E)) entry. A deterministic failure is REJECTed only when that anchor is finalized locally, and IGNOREd otherwise.
   - The DC draft's finalized-anchored list shifts bit layouts inside a round's own inclusion window, in **21 of 53 rounds** of a single-chain simulation.
4. **Enforcement.**
   - **Hard start:** a vote before its unit is IGNOREd and must not be held for later acceptance. go-libp2p-pubsub marks it seen before validation, so it is lost at that peer.
   - **Soft end:** 4 s after the aggregation cut, with two late aggregators per committee.
   - Aggregates are forwarded for 4 s after their publication time. Proposers may still include them until the end of round r+1.
   - Honest voters sign at the unit start and **publish 0.5 s later**. Then a receiver whose clock runs up to ~1 s slow still accepts them.
   - Windows overlap, so a withheld-vote burst is ≤ **3β units** (1.0 unit at β = ⅓), against 7.67 units without windows.
   - Honest random timing and a transport bandwidth cap are not substitutes.
5. **Sizing and inclusion.**
   - Use **64 committees per unit, one per subnet**, with the subnet fixed by composition. Rotation then causes **zero subnet churn**, against 225 reassignments per validator per day for a per-epoch shuffle.
   - Proposers **merge same-data aggregates per block**: **8–16 on-chain attestations per round**. It is 8 when a block's three units fit the 2^17-bit cap. Late +4 s aggregates and hash imbalance push some blocks to two. The instant switch is kept.
   - Aggregators cover both heights' data at a switch.
   - **Slashing evidence keeps full size.** Committee-sized evidence would break accountable safety; see §7.
6. **What it buys the clients.** In this design, a vote cannot force a state regeneration just to check membership — the failure behind the May 2023 finality incidents. The design has no per-epoch seed shuffle and no head-state dependency, and committee lengths are a pure function of a key carried in the message. A decoding cache entry is ~8 MB at 10⁶ validators and changes by ≤ 93 indices per epoch, with at most 6 entries per chain. Prysm today holds 16 MB per entry, and up to 512 MB under non-finality.
7. **Fixes for the DC draft found on the way** (§9):
   - activations stall after the fork, because `finalized_checkpoint` is frozen;
   - one exiting voter rejects a whole aggregate;
   - target pairs are validated component-wise rather than as pairs;
   - the stored target root is not a block root;
   - C does not divide `COMMITTEES_PER_ROUND = 2048`;
   - evidence can reach 2.10 MB.

**Reproduce** (all stdlib-only and deterministic):
- `python3 sim/strawman.py`: 50 spec self-tests, ~6 s;
- `python3 sim/schedules.py`: latency, fairness, composition and adversary, ~60 s;
- `python3 sim/sizing.py`: lag, bytes and churn, < 1 s;
- `python3 sim/anchor_check.py`: index-set invariance across branches, ~15 s.

## 1. The question

The FG of decoupled consensus is voted by the full validator set, once per round of 8 slots, in staggered units. Q17 fixes the grid: a unit is 4 s of voting plus 4 s of aggregation, a unit starts every 4 s, and there are 23 per round.

Votes are `(round, finalize_pair, target_pair)` ([Mikhail's draft](https://github.com/mkalinin/eth2.0-specs/blob/dc-feature/specs/_features/decoupled-consensus/beacon-chain.md), `mk:311-318`). A height is justified when 2/3 of stake votes for it. Votes enter the fork choice only through blocks (Francesco, FF chat 2026-10-01).

The FG safety argument never looks at committees ([§8](#8-safety-and-liveness)). Committees serve three purposes:

- **load:** a 4 s unit must carry a bounded number of messages;
- **small bitfields** for aggregation and inclusion;
- **enforceable timing:** a gossip check that a vote sits in its window.

That splits the design into separable axes:

| Axis | Question | Who cares |
|---|---|---|
| Position | which unit a validator votes in, and how that changes | latency at the threshold, seat fairness |
| Composition | who shares a cohort, committee and subnet | operator clustering, adaptive concentration, censorship of honest minorities, deanonymisation |
| Index set / anchor | which validators the bitfield positions refer to, and which state determines it | client robustness (the "#1 non-finality pain point", Terence and Potuz), branch independence |
| Enforcement | what gossip accepts when | bursts, griefing, honest clock skew |
| Inclusion | how unit aggregates reach blocks | bytes, instant switch, PQ proof count, slashing evidence |

The lane reports go deeper:
- [`analysis/schedule.md`](analysis/schedule.md): position, composition and adversary (Lane A);
- [`analysis/network.md`](analysis/network.md): enforcement, sizing and inclusion (Lane B);
- [`analysis/anchor.md`](analysis/anchor.md): the index set and anchor (Lane C).

[Appendix A](#appendix-a-study-setup) gives the study setup.

## 2. Recommendation: the strawman

The spec text below is a condensed copy of [`sim/strawman.py`](sim/strawman.py), which runs. Its self-tests T1–T9 exercise the pure and anchored functions, both gossip validators, the STF decoding and the invariants. BLS is a hash stand-in there, so the tests check rule logic, not cryptography.

**Constants**

| Name | Value | Why |
|---|---|---|
| `FG_UNITS_PER_ROUND` (C) | 23 | Q17 grid. A 24th unit is legal under the previous-round inclusion rule (network §2.5); that is Q17's call. |
| `FG_COMMITTEES_PER_UNIT` | 64 | one committee per attestation subnet per unit, constant so that membership stays pure. Devnets below ~190k validators get small committees, which only matters for the aggregator modulus. |
| `FG_ROTATION_PERIOD_ROUNDS` (K) | 8 | 0.4% latency cost; ε-fair in 5.8 h (schedule §5, §8) |
| `EPOCHS_PER_FG_ERA` | 256 | the largest era that satisfies the invariant below |
| `FG_ANCHOR_LOOKBACK` | 5 = 1 + `MAX_SEED_LOOKAHEAD` | `Active(E)` is fixed after epoch E−5 (anchor §1.2) |
| `FG_PUBLISH_DELAY_MS` | 500 | honest voters publish 0.5 s after the unit start (§6) |
| `FG_LATE_WINDOW_SECONDS` | 4 | the vote soft end, and the late-aggregator publication offset |
| `FG_AGGREGATE_FORWARD_SECONDS` | 4 | how long after its publication time an aggregate is still forwarded |
| `TARGET_LATE_AGGREGATORS_PER_COMMITTEE` | 2 | late supersets (network §2.4) |

```python
# Invariant: a consolidation requested after the seed is known cannot move stake inside that era.
assert EPOCHS_PER_FG_ERA + FG_ANCHOR_LOOKBACK <= 1 + MAX_SEED_LOOKAHEAD + MIN_VALIDATOR_WITHDRAWABILITY_DELAY
```

**Containers**

```python
class SingleAttestation2(Container):        # gossip vote; NO committee_index: the committee is derived,
    attester_index: ValidatorIndex          # so an unsigned field cannot be relabelled to win dedup
    data: AttestationData2                  # (round, finalize_pair, target_pair), mk:311-318
    signature: BLSSignature

class AggregateAndProof2(Container):
    aggregator_index: ValidatorIndex
    aggregate: Attestation                  # exactly one committee bit on gossip
    selection_proof: BLSSignature           # over the round, under DOMAIN_FG_(LATE_)SELECTION_PROOF
    is_late: boolean
    fg_dependent_root: Root                 # D(E) the bitfield is relative to; signed below

class SignedAggregateAndProof2(Container):
    message: AggregateAndProof2
    signature: BLSSignature                 # aggregator's signature over message
```

**Pure functions.** These need no `BeaconState`, only the era seed (32 B per era):

```python
def compute_fg_group(validator_index, era_seed) -> Tuple[cohort, subnet]:
    if era_seed is None:                                   # seed-free fallback
        return (validator_index % C, (validator_index // C) % FG_COMMITTEES_PER_UNIT)
    h = hash(era_seed + uint_to_bytes(validator_index))
    return (bytes_to_uint64(h[0:8]) % C, bytes_to_uint64(h[8:16]) % FG_COMMITTEES_PER_UNIT)

def compute_fg_rotation(round) -> uint64:                  # one seat LATER every K rounds
    return (round // FG_ROTATION_PERIOD_ROUNDS) % C

def compute_fg_seat(validator_index, round, era_seed) -> uint64:
    cohort, _ = compute_fg_group(validator_index, era_seed)
    return (cohort + compute_fg_rotation(round)) % C

def compute_fg_committee_index(validator_index, round, era_seed) -> CommitteeIndex:
    # seat-major, so the units landing in one block occupy a contiguous committee_bits range
    return compute_fg_seat(validator_index, round, era_seed) * FG_COMMITTEES_PER_UNIT \
         + compute_fg_group(validator_index, era_seed)[1]

def compute_fg_era(round) -> uint64:                       # fixed epoch ranges; never shifted by finality
    return compute_epoch_at_round(round) // EPOCHS_PER_FG_ERA
```

**Anchored functions.** These need only the cached `(E, D(E))` entry:

```python
def get_fg_dependent_root(state, epoch) -> Root:           # D(E)
    if epoch < FG_ANCHOR_LOOKBACK:
        return GENESIS_BLOCK_ROOT
    return get_block_root_at_slot(state, compute_start_slot_at_epoch(epoch - MAX_SEED_LOOKAHEAD) - 1)

def get_fg_era_seed(state, era) -> Bytes32:                # rides on D(era start)
    mix_epoch = era * EPOCHS_PER_FG_ERA - FG_ANCHOR_LOOKBACK
    if mix_epoch < 0:
        return hash(DOMAIN_FG_COHORT + uint_to_bytes(era) + Bytes32())
    assert get_current_epoch(state) > mix_epoch            # never serve duties from a partial mix
    return hash(DOMAIN_FG_COHORT + uint_to_bytes(era) + get_randao_mix(state, mix_epoch))

def get_fg_index_set(state, round) -> Sequence[ValidatorIndex]:   # Active(E)
    epoch = compute_epoch_at_round(round)
    if epoch >= FG_ANCHOR_LOOKBACK:
        assert compute_start_slot_at_epoch(epoch - MAX_SEED_LOOKAHEAD) <= state.slot
    return get_active_validator_indices(state, epoch)

def get_fg_committee_members(state, round, committee_index) -> Sequence[ValidatorIndex]:
    era_seed = get_fg_era_seed(state, compute_fg_era(round))
    return [i for i in get_fg_index_set(state, round)          # ascending; bit k = members[k]
            if compute_fg_committee_index(i, round, era_seed) == committee_index]

def get_fg_attesting_indices(state, attestation) -> Set[ValidatorIndex]:
    output, offset = set(), 0
    for committee_index in get_committee_indices(attestation.committee_bits):   # ascending
        members = get_fg_committee_members(state, attestation.data.round, committee_index)
        assert len(members) > 0                                                 # mk:712-713
        output |= {i for k, i in enumerate(members) if attestation.aggregation_bits[offset + k]}
        offset += len(members)
    assert len(attestation.aggregation_bits) == offset     # length check, missing in mk:697-721
    return output

def get_fg_counted_indices(state, attestation) -> Set[ValidatorIndex]:
    # decode, then do not count inactive or slashed bits (replaces the reject at mk:714-718)
    epoch = get_current_epoch(state)
    return {i for i in get_fg_attesting_indices(state, attestation)
            if is_active_validator(state.validators[i], epoch) and not state.validators[i].slashed}
```

**Gossip, `beacon_attestation_{subnet_id}`** (`SingleAttestation2`). This list is normative and supersedes the lane lists. "Det" marks a deterministic failure: REJECT if the node's D(E) is finalized locally, else IGNORE. That covers era seeds or sets that differ across branches, and EIP-6914 reuse.

1. _[IGNORE]_ `data.round` ∉ [round(now − disparity) − 1, round(now + disparity)].
2. _[IGNORE]_ No local (E, D(E)) entry for `data.round` yet (MAY queue until computed).
3. _[Det]_ `attester_index` ∉ `Active(E)`.
4. _[Det]_ The topic subnet ≠ `compute_fg_group(attester_index, era_seed)[1]`.
5. _[REJECT]_ `target_pair` and `finalize_pair` are both `(EMPTY_HEIGHT, Root())` (`mk:663-666`).
6. _[IGNORE]_ **Hard start:** `now + disparity < unit_start(round, seat)`. The vote must not be held for later acceptance.
7. _[IGNORE]_ **Soft end:** `now > unit_start + FG_VOTE_PHASE + FG_LATE_WINDOW + disparity`.
8. _[IGNORE]_ A *valid* vote for `(attester_index, data.round)` has already been seen.
9. _[IGNORE]_ `attester_index` is a known equivocator (valid slashing evidence seen on any branch).
10. _[REJECT]_ The target root is a known-invalid block. _[IGNORE]_ The target root is unknown: MAY keep it for local aggregation once the block arrives, but do not forward it. Under the instant switch, fresh votes race their target block.
11. _[Det]_ The signature is invalid (pubkey from the same cache entry). Only after it passes is `(attester_index, data.round)` recorded as seen.

**Gossip, `beacon_aggregate_and_proof`** (`SignedAggregateAndProof2`). The node decodes only against an entry it holds for exactly the named D(E).

1. _[IGNORE]_ `fg_dependent_root` is not a local entry for `aggregate.data.round` (unknown or foreign).
2. _[REJECT]_ Not exactly one committee bit, or the committee index ≥ C × 64.
3. _[IGNORE]_ **Hard start:** `now + disparity < publish`, where `publish = cut` for on-time aggregators and `cut + FG_LATE_WINDOW` for late ones.
4. _[IGNORE]_ **Forwarding horizon:** `now > publish + FG_AGGREGATE_FORWARD + disparity`. Proposers MAY still include what they hold until the end of round r+1 (`mk:657-660`).
5. _[Det]_ `len(aggregation_bits)` ≠ the committee size, or no bit is set.
6. _[Det]_ The aggregator is not in the committee, or `selection_proof` is invalid or does not select it. The modulus is `max(1, len(committee) // TARGET_AGGREGATORS_PER_COMMITTEE)`, or `// TARGET_LATE_AGGREGATORS_PER_COMMITTEE` when `is_late`.
7. _[IGNORE]_ A valid aggregate with a superset of these bits has been seen for `(fg_dependent_root, hash_tree_root(data), committee_index)`.
8. _[IGNORE]_ The aggregator has already published for `(round, hash_tree_root(data))`, or for two data values this round.
9. _[Det]_ The aggregator signature over the message is invalid, or the aggregate signature over the decoded pubkeys is invalid.

**Honest behaviour (validator guide).**
- **Voters.** Sign at `unit_start` with the head state at that instant, and publish at `unit_start + FG_PUBLISH_DELAY_MS`. Vote for the head state's current height unless that state's `height_participation` already counts you. If you signed a *different* target root for this height (the includer equivocated, §8), vote progress `(h, Root())` rather than switching roots, which would be slashable.
- **On-time aggregators** publish at the cut, one aggregate per distinct data value they saw (at most 2: current and previous height).
- **Late aggregators** publish at cut + 4 s, and only if they hold votes outside the best on-time aggregate. Their aggregate is a strict superset of it.
- **Proposers** merge same-data aggregates of the units that land in their block into one attestation via seat-major `committee_bits`.

**STF.**
- `process_attestation` decodes bits with `get_fg_committee_members` and counts `get_fg_counted_indices`.
- It adds the aggregation-bits length check and the non-empty committee check.
- It keeps the current-or-previous round inclusion rule (`mk:657-660`) and the previous-target credit (`mk:124-134`). The latter is what keeps stale votes reward-neutral (§3).
- **Slashing evidence keeps the full `MAX_VALIDATORS_PER_AGGREGATE` bound** (§7). A compact encoding is optional.

**Validator duties.** Seat and subnet for era e are derivable from the RANDAO mix of epoch era_start − 5 plus a hash, from epoch era_start − 4 (~25 min ahead). The beacon API already serves the mix. Bit positions and committee lengths for epoch E are fixed from `start(E−4)` (25.6 min ahead, against 6.4 min today), and the committee length sets the aggregator modulus. They need **a new beacon-API endpoint** serving `Active(E)`-derived committee sizes (or member lists), with `dependent_root = block root at start(E−4) − 1`. The seed-free fallback needs no root at all for seat and subnet.

## 3. Position: why "one unit later every 8 rounds"

The model is Mikhail's instant switch. Every validator votes once per round, in its unit, for the latest height it knows, unless it has already voted for that height. The switch lag L is the number of units before voters see a new height. Lane B traces it on the Q17 grid at **L = 3 / 2 / 4** for a quorum completed at the +0 / +4 / +8 s unit (mean 2.8), with a 5–7 tail when the next block is missed (~4% of the time today).

**Rounds per height, C = 23** (schedule E1a, E2a, E13):

| Schedule | p = 1, L = 0 | p = 1, L = 3 | p = .67, L = 3 | drop to 67%, L = 3: median / p95 / max |
|---|---|---|---|---|
| fixed order | 0.696 | 0.826 | 1.130 | 1.13 / 1.13 / 1.13 |
| **recommended: era hash + 1 unit later every 8 rounds** | **0.699** | **0.829** | **1.136** | **1.15 / — / 1.17** (E13) |
| +1 unit every round (≈ Francesco's `(index + round) % C`) | 0.727 | 0.857 | 1.167 | 1.17 / 1.17 / 1.17 |
| −1 unit every round (whole-unit shift toward earlier seats) | 0.696 | 0.826 | **2.000** | 2.00 / 2.00 / 2.09 |
| DC draft: slide one validator per round, toward earlier seats | 0.696 | 0.826 | 1.130 | 1.13 / 1.13 / 1.13 |
| per-epoch reshuffle (fradamt Simplex spec, every 4 rounds) | 0.714 | 0.842 | 1.332 | 1.39 / 1.83 / 1.96 |
| per-round reshuffle | 0.789 | 0.984 | 1.886 | 1.96 / 2.04 / 2.09 |
| VRF lottery per round | 0.787 | 0.980 | 1.892 | 2.00 / 2.04 / 2.04 |

- **Why.** The gap lemma (schedule §3): with ≥ 2/3 honest stake online, on one branch, and an honest includer, a height is justified within **L + G** units of the previous one. G is the longest gap between a validator's consecutive vote opportunities.
  - G = C for fixed order, and C + 1 for forward rotation (the cohort that wraps to the front costs one redundant unit).
  - G = **2C − 1** for a backward step and for every reshuffle. The cohort moving from the first seat to the last waits almost two rounds, and at the threshold everyone is needed.
  - The bound holds in all 18 simulated schedules. It is attained, or missed by one tick, for every family except the era run, whose boundary is rare.
  - This is the "almost two rounds at 67%" concern (Yann) and the "≈1.5 rounds" estimate (Mikhail): reshuffles pay it, forward rotation does not.
  - The DC draft's one-validator slide is latency-neutral only because one validator per round is below any slack.
  - §8 extends the bound to adversarial includers. The ranking does not change.
- **The rate barely matters; the direction does.** Any K ≥ 8 costs ≤ 0.5%. Near the threshold the worst case is C + 1 for every K, so K only trades the fairness horizon.
- **Fairness: a deterministic rotation beats randomness.** With assumed per-offset miss rates of 0.5–3%, the worst *fixed* seat loses 1.74 pp of FG vote success forever: 1.09% of CL reward, slightly more than a year of proposer-lottery noise for a 2048-ETH validator (schedule E10b–c).
  - The recommended rotation is ε-fair (≤ 0.1 pp) after **5.8 h**.
  - A per-epoch reshuffle takes 35 h at p99, and a per-round reshuffle 8.8 h.
  - The DC draft's slide moves a validator one unit every ~48 days at 10⁶, so it takes 3.6 years.
  - Randomness is therefore not needed for *position* fairness (Yann's property 3). It is needed for *composition* (§4).
- **What rotation does not fix.** When heights lock to rounds (one height per round, e.g. at p = .8, L = 3), the same validators cast the stale votes every round. A rotation moves them all together (schedule E7). The reward function has to neutralise that. The DC draft already does: current-target and previous-target votes get identical round flags (`mk:124-134, 1199-1214`). Keep that in the rewards spec: if timely votes ever pay more, voters herd to the +8 s units and the late aggregators become the bottleneck.
- **Rejected.**
  - **Active-set position as the index.** Every exit re-seats everyone behind it, giving 1.99 rounds/height at 2 exits/round (schedule E9b). Use the raw validator index.
  - **Heavy-first ordering** (Barnabé). It is pinned at exactly 1.000 rounds/height under the instant switch, because the heavy cohort must be in every quorum and votes once per round. It reads balances. It concentrates liveness on ~1.5% of validators (schedule §10).

## 4. Composition: why an era hash

- **A rotation never changes who shares a cohort.** Each composition rule creates its own risks:
  - **Contiguous index blocks** (the DC draft, `mk:870-872`) keep deposit batches together. At 10⁶ validators:
    - the largest operator holds 18.4% of one unit against 9.4% overall;
    - 10.3% of committees are ≥ 90% one operator and 6.5% fully single-operator;
    - the clustering persists ~31 days (schedule E8b–d).

    A single-operator committee is free batching, but it hurts honest neighbours: in a mixed committee the operator holds most aggregator seats, so an honest minority with share h loses all its aggregators with probability ≈ e^(−16h), i.e. 45% at h = 5%. It is also exact deanonymisation in one observation (network §7). This is Yann's "Binance committee" question, and the answer is: good for traffic, bad for everyone sharing the committee.
  - **Striping by validator index** spreads batches. A 1,000-index batch touches all 23 cohorts, at ≤ 4.4% each, or ≤ 5.3% under the era hash (strawman T6). But it is fixed forever. An adversary chooses consolidation targets (EIP-7251 keeps the target's index) inside one cohort and reaches ⅓ of a C = 23 cohort in **8.3 days** (Electra churn) or **4.4 days** (EIP-8061) at 10% stake (schedule E12a).
  - **Era re-draw** (recommended):
    - Consolidations cannot be aimed. A request processed in epoch era_start − 5, when the seed becomes known, exits at ≥ c + 5 and becomes withdrawable 256 epochs later. Its balance counts from era_start + 256, which is the next era.
    - That is exactly the invariant of §2, with zero slack. **Shortening `MIN_VALIDATOR_WITHDRAWABILITY_DELAY`, which fast finality invites, must shorten the era with it.** Making the era boundary wait for finality would break it too, and it would hand control of the boundary to whoever stalls finality.
    - The remaining lever is top-ups and new deposits (including 1-ETH placeholder indices aimed at a cohort once the seed is known). They share `pending_deposits` at 256 ETH/epoch, unchanged by EIP-8061. That is ≤ +4.1 pp of a C = 23 cohort per era at 36M ETH staked, scaling with C/S.
    - Grinding: a k-slot tail of the seed epoch picks the best of 2^k compositions. At k = 8, a stress case (probability β^8 per era), a 5% adversary running 2048-ETH validators moves from 6.45% to 7.70% of its best cohort (schedule E12b).
    - Time-averaged exposure equals today's per-epoch seed. The target epoch, however, is fixed and known, as for sync committees.
- **Why a hash of the validator index, not the exact-balance shuffle.** Lane A proposes a striped seeded shuffle of the era's index list, which balances cohorts to ±1. The hash variant does four things the shuffle cannot:
  - it covers validators activated mid-era with no extra rule (Lane A's open issue 4);
  - it never re-seats anyone on exits or index reuse (EIP-6914 reuses the lowest free index, which behaves like an append);
  - gossip checks membership from one 32-byte seed rather than an n-entry table;
  - it removes a lever the shuffle has: if the shuffled list and the seed both close at era_start − 5, a tail proposer can include exits to re-rank the list, which gives extra grinding bits.

  Its cost is binomial imbalance: cohorts ±1.1% and committees −13% / +16% around 679 members at 10⁶ (strawman T3). If exact balance turns out to matter — for example the 2^17 cap, where 2 of 23 three-unit merges exceed it by < 0.2% at 10⁶ — switch to the shuffle and add a fallback seat for mid-era activations.
- **Era boundary.** A full re-draw gives some validators a gap of up to 2C−1 once per era: 44% wait longer than C + 1 at the boundary (strawman T4). That is one ~0.48-round delay at p = .67, or 0.047% of an era (schedule E11). It is Vorbit's "circular finality" (ethresearch 20464 §4.1), applied to rounds.
  - The flip also moves every duty subnet in the same epoch. The per-node backbone rotation, by contrast, is staggered (`node_offset`, phase0 p2p-interface :1736-1738).
  - So nodes pre-subscribe to their next-era subnets during the 4-epoch lead.
  - A per-validator staggered re-draw would remove both the boundary delay and the subscription burst. But it extends some assignments past 256 epochs, so it needs a correspondingly shorter era to keep the invariant (open issue).
- **Seed-free fallback:** `cohort = validator_index mod C`, `subnet = (validator_index // C) mod 64`. Seat, window and subnet need no state and no seed. It gives the same latency and honest-case balance and no single-operator committees, but it accepts adaptive concentration within days. That is acceptable only while no gadget reads per-unit tallies (§8).

## 5. Index set and anchor: why `Active(epoch(round))`

**The lemma** (anchor §1).
- Every writer of `activation_epoch` or `exit_epoch`, from phase0 to Gloas/Heze, in EIP-8061 and in the DC draft, moves FAR_FUTURE to a value ≥ c + 5, where c is the current epoch.
- So `Active(E)` is final once `process_epoch(E−5)` has run. It is a function of `(E, D(E))`, with D(E) the root of the latest block at or before the last slot of epoch E−5.
- The bound is tight against the real spec paths (anchor sim). Strawman T2 confirms the invariance, and that it catches a mis-set seed lookback.
- The key needs E as well as D, because empty epochs repeat D while the set still changes.
- Caveats:
  - `slashed` takes effect at once but does not enter `Active`;
  - EIP-6914 index reuse rewrites only records > 65,792 epochs old, but index→pubkey caches must become reuse-aware;
  - genesis writes epoch 0;
  - Gloas builders live in a separate registry, and Gloas processes execution requests in the child block, so the lemma holds there too.

**The options compared** (anchor §2; network §5.3, §8):

| Option | Gossip needs | Weakness |
|---|---|---|
| **R: `Active(epoch(round))`, key (E, D(E))** | one sorted index list per (E, D(E)), computed from the node's own head chain 4 epochs ahead, plus per-committee member arrays (~8 MB per decoding entry at 10⁶; ≤ 6 per chain) | deep forks (> 4 epochs) during long non-finality need one extra entry per branch and epoch; IGNORE suffices, since a node's STF only accepts its own targets |
| Francesco's `Active(epoch(target.slot))` | the target block plus a store lookup of its ancestor | consistent across branches (the worry that finality might differ does not apply to it), but progress votes have no root; the set is stale while the FG is stuck; it needs an explicit target-age bound to keep voters slashable; the layout depends on the vote's target |
| DC draft: registry minus exits at the state's finalized epoch | the *including* state's `len(validators)` and finalized epoch, i.e. the ill-defined state of the thread | not branch-stable, not even chain-stable: 21 of 53 rounds change layout inside their inclusion window, and one registry append moves the first member of 992 of 2048 committees |
| Roberto's finalized anchor in the vote | a cache per anchor plus the registry length at F | DC finalizes about every ⅔ round, so the anchor changes inside the inclusion window of every round in the sim; second copies are signed and aggregates fragment |
| snapshot hours old | one set per era | new validators locked out for hours while still in the quorum denominator |
| full registry | arithmetic only | 42.3% (2025-03) to ~50% (2025-08) of mainnet bits are dead |

**What R removes from the failure class** that produced the May 2023 incidents (ethresearch 15871) and the Holesky 2025 shuffling bugs:
- There is no per-epoch shuffle seed. The era seed is read at ≤ E−5, the same dependency class as `Active(E)`, so the dependency moves from E−2 to E−5. Every fork shallower than four epochs shares the set. That covers every fork on a chain whose finality lags by ≤ 129 slots.
- Validation never regenerates a state per message. If the head lags behind start(E−4), the node advances its head state through `process_epoch(E−5)` once per branch and epoch, as Prysm's head-state path already does.
- Committee lengths are a pure function of the key, so two nodes with the same key cannot disagree; that was the Holesky symptom.
- Aggregates name their key, so a mismatch becomes IGNORE rather than misdecode → REJECT → peer-score loss.

Red team (ii) checked all five branches of Prysm's `getAttPreState` (`process_attestation_helpers.go:94-165`); none is needed. What remains is what Mikhail pointed out: block processing still needs the parent state, and the trouble was always the dependent state, not shuffling per se.

**Edge cases from the thread:**
- **Empty or progress targets:** irrelevant to R, since the set does not depend on the target.
- **New activations:** they vote from their activation epoch.
- **Slashed voters:** they keep their bit until exit; it is not counted, and gossip IGNOREs known equivocators.
- **Exits within the inclusion horizon:** decoded and not counted, which fixes the poison bit.
- **Slashability:** an R voter stays slashable for ≥ 256 epochs (27.3 h) after its round.

## 6. Enforcement: hard start, soft end

- **Why enforce at all** (Mikhail). Without windows, an adversary with stake share β can put β·C units' worth of *valid* votes into one instant. At β = ⅓ and V = 10⁶ that is 7.67 units, or 66.7 MB. Every honest node then forwards it through the single per-peer FIFO that also carries blocks and blobs; go-libp2p-pubsub has no prioritisation (network §2.5).
  - Honest timing is not independent either: voters react to the same block arrival.
- **With windows the burst is ≤ 3β units.** A unit's window spans 9 s including the ±0.5 s disparity, units start every 4 s, and three windows are open at once 25% of the time (strawman T9). That is 1.0 unit, or ~8.7 MB at 10⁶, for β = ⅓.
  - An open-ended soft end would re-open a 15.3-unit burst, which is worse than no windows.
  - Aggregates need their own horizon: the superset rule does not deduplicate *disjoint* aggregates, so an adversary holding ~5 of 16 aggregator seats could otherwise hoard and release a round's worth at once. Forward them only for 4 s after their publication time; proposers keep including what they hold until the end of round r+1.
- **Hard start.** A vote early by more than the 500 ms disparity is IGNOREd.
  - go-libp2p-pubsub marks a message as seen *before* the topic validators run (`validation.go:322-329`, v0.14.0, verified). An early vote is therefore burned at that peer for `seen_ttl`.
  - Holding early votes in an async validator and accepting them at the window start would recreate the start-of-window spike, so clients must not do that.
  - The sharp edge cuts both ways. A vote published exactly at the unit start would be burned by receivers whose clocks run more than ~0.5 s slow. Hence honest voters **publish 0.5 s after the unit start**, which tolerates receivers ~1 s slow (strawman T5).
- **Soft end: one unit (4 s) after the cut.** Late aggregates then still land in the same block for the +0 and +8 units. Votes later than that are lost for the round. The validator votes again next round, and height participation carries over while the height stalls.
  - Late votes go to the late aggregators, not straight to the proposer. CL req/resp has no push method, a direct path would expose the proposer just before its slot, and it bypasses deduplication and scoring.
- **"No committees, rate-limit attestations instead"** (Mikhail's alternative): no, as a replacement.
  - GossipSub has one queue per peer and no prioritisation.
  - Even under a 20% share, a round-start burst takes 5–70 s to drain, depending on link speed and duplication.
  - An unpartitioned aggregate carries 125 kB of bitfield.

  A per-topic cap is still worth adding *on top* of windows, as a backstop for blocks and blobs (network §6).

## 7. Sizing, subnets, inclusion

- **Committees.** Use one per subnet per unit: 64.
  - The DC draft's constant 2048 committees per round give 89.04 per unit at C = 23 (C does not divide 2048), leaving 25 of 64 subnets doubly loaded.
  - At 120k validators, 2048 committees make a third of all validators aggregators every round (network §3.2).
  - **Subnet = composition, not position.** Rotation then never moves anyone between subnets (strawman T1).

**Duty-subnet reassignments per validator per day** (network §4):

| Rule | Reassignments/day |
|---|---|
| rotation with subnet tied to composition | **0** |
| era re-draw | 1, simultaneous for all; pre-subscribe during the 4-epoch lead |
| DC draft slide (at 10⁶) | 1.8 |
| per-epoch reshuffle | 225 |
| per-round reshuffle | 900 |

- **Per-node load.** On the Q17 grid the **global aggregate topic dominates**: 75% of 17.8 Mbit/s per node at 10⁶ and C = 23, against 4.6 Mbit/s for today's attestations under the same duplicate model (network §3.3). This concerns Q17's parameters more than the assignment rule. The aggregate topic alone falls from 13.4 to 2.8 Mbit/s with 32 committees per unit, 8 aggregators and a `Bitvector[64]` in place of `CommitteeBits[2048]`. These are model values, to be measured first.
- **A secret VRF duty** (the explainer's current proposal) needs a proof in every vote: +96 B (+48%) and one more BLS verification per vote. A public schedule answers the explainer's open item, "does an attester have to prove that it is allowed to propagate in its subround": no, the check is a pure function.
- **Inclusion: per-block merge** (network §5.1).
  - Proposers merge the same-data aggregates of the 2–3 units landing in their block into one attestation. That keeps the instant switch.
  - It gives **8 attestations per round** when the merged units fit the 2^17-bit `MAX_VALIDATORS_PER_AGGREGATE`.
  - At 10⁶ two effects add a second attestation to some blocks:
    - the late supersets of +4 s units land one block later, and merging them with the next three units needs ~174k bits;
    - hash imbalance pushes 2 of 23 three-unit merges just over the cap (strawman T3).

    Plan for **8–16 attestations, and as many PQ proofs, per round**.
  - A single aggregate per round (Francesco's PQ-friendly option) saves ≤ 6.7 kB per round at 10⁶. It gives up the instant switch, and at 10⁶ still needs 8 attestations under the cap.
- **Height switches split data.** At a switch the first fresh unit splits by its late-seeing minority, about 1.2 extra data values per round. If aggregators keep only their own data (today's rule), a 5% minority finds no matching aggregator in 45% of committees. So **aggregators aggregate every data value they saw (≤ 2)**, and deduplication is keyed per data root (network §5.2). These stale votes are exactly the ones that must stay rewarded.
- **Slashing evidence must keep full size.** An earlier draft of this note proposed bounding `IndexedAttestation2` to committee size. Red team (i) showed that this **breaks accountable safety**:
  - Counted votes never have to cross gossip. An adversarial proposer can put its own validators' votes straight into its block, merged across up to 1,472 committees, and a BLS aggregate cannot be split back into committees.
  - Gossip dedup on (attester, round) drops same-round equivocations.
  - Slashers on one branch never hold the other branch's aggregates, because foreign D(E) is IGNOREd.

  The fix:
  - Keep evidence at `MAX_VALIDATORS_PER_AGGREGATE` = 2^17 indices: up to **2.10 MB per `AttesterSlashing2`** (2.09 MB for a per-block merge), one per block. That is about 4× the 488 KB that made EIP-7549 cut `MAX_ATTESTER_SLASHINGS` to 1.
  - Optionally add a **compact form**: the on-chain bitfield plus round and D(E), decoded by the STF. It is ~125 kB per side at 10⁶ and works whenever both conflicting attestations decode on the including chain, i.e. when they share D(E). R is what makes this possible.
  - Committee-sized evidence from gossip aggregates is only an optimisation.

## 8. Safety and liveness

- **Safety-neutral** (schedule §4; confirmed by red team (i)). Justification and finalization count `height_participation` flags with a full-active-set, live-balance quorum (`mk:471-486`). The slashing predicate compares only `finalize_pair` and `target_pair` (`mk:493-520`). Neither reads the unit, the timing or the composition.
  - A wrong bit mapping makes the aggregate signature fail. It cannot credit a validator that did not sign.
  - Previous-round votes decode with `Active(epoch(r))` from the including state.
  - So every schedule is equally safe, *provided evidence for every on-chain attestation stays submittable* (§7). Position and composition only move liveness, incentives and griefing.
  - For continuous-FG variants the same holds via `CountRule.MonotoneOn` (`projects/ff/continuous-fg/lean/RollingFFG/Model/Schedule.lean`).
- **Liveness, honest includer.** Heights advance only inside blocks (`mk:926, 969-988`), so the bound uses the worst offset's lag L_max = 4. That gives **(L_max + G)/C = 1.22 rounds per height** for the recommendation at C = 23, against 1.17 at L = 3.
- **Liveness, adversarial includers.**
  - Each adversarial or missed proposer after the cut adds 3 units: 1.35 rounds with one missed block. The expected run is β/(1−β) = 0.5 slots at β = ⅓.
  - An adversarial includer can also *equivocate* the block that completes the quorum. That block becomes the target of h+1 (`mk:950-954`), so h+1 splits without any asynchrony. Votes for the other root are invalid on each branch (`mk:668-672`), and switching roots would be slashable (`mk:513-519`).
  - The validator rule of §2 therefore matters: "vote unless the head state's `height_participation` counts you; if you signed another root for this height, vote progress `(h, 0)`". Read literally, "unless you already voted" would stall forever. Back-off (Francesco: "no need to attest every round") is safe only under this reading.
  - Cost: up to one extra G on roughly β of heights, and those heights only progress, without justifying.
  - So quote liveness as **L_max + 3k + G (+ G per split)**, with k the adversarial proposers in a row. The schedule ranking of §3 is unchanged, because every term except G is schedule-independent.
- **Splitting views by withholding** (Mikhail's question) is the same kind of liveness cost, bounded as above once the AC has converged. Concentrating stake does not enlarge it.
- **Where neutrality ends.** Any gadget that reads *partial* tallies — a stabilization gadget, or a fast-confirmation rule over the last k units — turns cohorts back into a security unit (Yann's SG concern). Composition then matters, and the era re-draw is the defence. Re-run the window-share numbers (schedule E8b: top operator's share of 4 consecutive units, 12.5–17.8% under contiguous blocks vs 9.4–14.3% striped or shuffled) once the SG is specified.

## 9. What changes

**DC state-transition draft** (Mikhail; `mk:` line numbers in the copy fetched 2026-10-02; every reference was re-checked by red team (ii)):

| # | Item | Fix |
|---|---|---|
| 1 | Committees are contiguous blocks of `exit_epoch > finalized` sliding one validator per round (`mk:853-873`) | §2 functions: era-hash composition, forward rotation every 8 rounds, `Active(epoch(round))` index set |
| 2 | **Activation stall.** `process_justification_and_finalization` is dropped (`mk:1008`), so `finalized_checkpoint` is never written. Yet `is_eligible_for_activation` (phase0 :727), `is_active_builder` (gloas :465) and `get_finality_delay` (phase0 :1559) still read it. No validator that becomes eligible after the fork activates | read `compute_epoch_at_slot(state.finalized_slot)`, as `mk:1062` already does for deposits |
| 3 | **Poison bit.** `is_valid_aggregation_bits` rejects the whole aggregate if one voter is inactive at inclusion (`mk:714-718`) | decode and do not count (`get_fg_counted_indices`) |
| 4 | Aggregation-bits length is not checked (`mk:697-721`) | add the Electra length check |
| 5 | **Pairs are validated component-wise.** `is_valid_attestation_data` checks target root and target height separately (`mk:668-677`), so a root of one pair can come with the height of the other | validate `(height, root)` as a pair |
| 6 | **Target root ≠ block root.** `advance_height` hashes `latest_block_header` while its `state_root` is still zero (`mk:950-954`). Using the real block root inside `advance_height` would be circular, because the state root commits to it | fill the root in at the next `process_slot`, as `latest_block_header.state_root` is, or define the lookup explicitly |
| 7 | C does not divide `COMMITTEES_PER_ROUND = 2048`, and `CommitteeBits[2048]` is 256 B per aggregate | C × 64 committees; a single committee index on gossip |
| 8 | `IndexedAttestation2` up to 131,072 indices (`mk:105-106` TODO) | keep the full bound (§7); optionally add the compact form |
| 9 | No committee→unit map and no p2p or validator section | §2 |

**fradamt executable Simplex spec.** The epoch shuffle is repeated per round and gossip resolves committees through a checkpoint state (`simplex/beacon-chain.md:1164-1207`, `p2p-interface.md:759-783`). This design dominates it on latency near the threshold (1.136 vs 1.332 rounds/height), fairness (5.8 h vs 35 h), churn (0 vs 225/day) and state needs.

**Explainer** (`design/explainer.md:21-27`). It proposes a per-epoch VRF for sub-round, subnet and aggregator. Replace it with the public schedule. Aggregator selection stays a self-selection lottery over the committee. *Not edited here.*

**Pattern note** (`design/pattern-exploration/fg-vote-dissemination.md`, uncommitted). Its per-round re-randomisation of "tail-light" cohorts pays the reshuffle cost (C = 8: 2.000 vs 1.375 rounds/height at p = .67). Ex-ante fairness comes cheaper from the rotation (§3). Its requirement that cohorts have "concentration and grinding bounds" on signer count and balance is met by the era re-draw (§4).

## 10. The thread's questions, answered

| Question (FF chat, 2026-10-01/02) | Answer |
|---|---|
| Do we need explicit committees to stagger? (Francesco) | We need a **globally known partition with enforced windows**: for gossip enforcement, small bitfields and subnets. It need not be shuffled, and it is not a security unit (§1, §6) |
| Shuffled, or a simple partition? What does randomising buy? (Francesco) | Position: a simple deterministic forward rotation, which is fairer and faster than random. Composition: re-drawn once per era, because a fixed one can be captured by consolidation targeting in days and contiguous blocks cluster operators (§3, §4) |
| Partition to shrink attestations and enforce staggering; is honest random timing brittle? (Mikhail) | Yes and yes: the hard start and soft end cap bursts at 3β units, against 7.67 without windows (§6) |
| Are some places in the round better than others? (Mikhail) | Yes. Absolute seats differ by ~1.7 pp under assumed miss rates, fixed by rotation within 5.8 h. Relative-order effects (stale votes) need equal credit for previous-target votes, which the draft already gives (§3) |
| Yann's three properties | (1) yes, a public deterministic assignment; (2) yes, enforced windows; (3) randomness is not needed for position, but is needed for composition, once per era (§3, §4) |
| `(index + round) % C` with the index in the active set (Francesco) | Two changes: the raw validator index (active-set ranks re-seat everyone on each exit: 1.82–1.99 rounds/height) and +1 every 8 rounds rather than every round (0.699 vs 0.727) (§3) |
| Adversary concentrating across consecutive committees vs the SG (Yann) | No FG-safety lever. It matters once a gadget reads partial tallies; the era re-draw bounds it (§4, §8) |
| A committee of only Binance validators? (Yann) | Under contiguous blocks this is common (6.5% of committees). Good for traffic, bad for honest minorities in mixed committees (e^(−16h) censorship) and for privacy. The era hash removes it (§4) |
| Consolidated validators vote earlier? (Barnabé) | No. Under the instant switch it pins throughput at 1.000 rounds/height and needs balances (§3) |
| Reuse p2p committees on chain; all at once or over time? (Mikhail, Francesco) | Reuse them, seat-major. Proposers merge per block: 8–16 attestations per round, with the instant switch kept. Evidence stays full size (§7) |
| State-independent p2p validation (Potuz, Terence) | `Active(epoch(round))`, cached by (E, D(E)), finalized at ≤ 129 slots of finality lag; aggregates name D; no per-message regeneration (§5) |
| Which index set: active at the target epoch, registry minus exits at finality, the finalized anchor plus queue, an old snapshot? (Francesco, Mikhail, Roberto) | All compared in §5. R is recommended; Francesco's target rule is the consistent runner-up; the draft's rule is unstable on a single chain |
| Empty target, slashed voters, new activations, index reuse (Roberto, Terence) | §5 edge cases |
| Instant switch with low end/start overlap (Mikhail) | Forward rotation: the overlap costs 1/K of a unit per round. A whole-unit backward shift costs 2 rounds at the threshold (§3) |
| Two rounds per height at 67%? (Yann, Mikhail) | Only for reshuffles and backward shifts (2C−1 gaps). 1.13–1.17 rounds for fixed order and forward rotation with honest includers; 1.22 at the worst-offset lag (§3, §8) |
| STF must know who voted at this height in an earlier round (Terence) | Already in the draft (`height_participation`). This design adds **no state fields**: the seed comes from `randao_mixes`, the set from the registry |
| Keep `round` in the vote? (Mikhail, Francesco) | Yes. The seat, the committee layout and the inclusion window are functions of the round |
| Withholding a small fraction to split views during asynchrony? (Mikhail) | Liveness only. The sharper version is an includer equivocating the quorum block, bounded by L_max + 3k + G plus G per split under the progress-vote rule (§8) |

## 11. Interaction notes (out of scope)

- **AC / Goldfish committee selection.** The draft elects a 1,024-seat balance-weighted committee per slot (`mk:540-552`; "can be replaced with VRF selection", `mk:193`). Unlike FG cohorts, these committees *are* a sampling-security unit, so their randomness and secrecy trade-offs (Mikhail's confirmation-safety point) are a separate question.
  - Two observations carry over. Their p2p validation has the same anchor problem, and a seed read at ≤ E−5 has the same dependency class as `Active(E)`.
  - Reusing FG cohorts for the AC would not work, because AC committees need fresh randomness every slot.
- **Rewards and state fields.** Keep four properties when rewards are written:
  - current-target and previous-target votes earn identical round credit, which neutralises relative-order bias and prevents herding to late units (§3);
  - height participation carries over while a height stalls (`mk:130-134`);
  - stale votes split at a switch stay includable (§7);
  - the progress-vote rule after an includer equivocates (§8).

  The schedule itself needs no new state.

## 12. Open issues

1. **Measure before quoting.**
   - per-offset miss rates (the fairness numbers scale linearly with them);
   - κ and IHAVE on the global aggregate topic;
   - the late-vote distribution against the 4 s soft end;
   - receiver clock skew against the 0.5 s publish delay.
2. **A mainnet registry snapshot.** Operator batches, dead entries and consolidation patterns would replace the synthetic Zipf registry before the composition numbers are cited externally.
3. **SG / fast confirmation.** Re-run the window-share analysis against the actual gadget once it is specified.
4. **The era seed under long non-finality.** Era boundaries stay at fixed epochs; they must not wait for finality (§4). If finality lags by more than ~4 epochs at a boundary, branches can disagree on the seed. Votes are then IGNOREd across branches, which is safe under the Det rules, but subnets diverge too. Quantify the healing cost.
5. **Slashing-evidence size.** Full-size evidence is up to 2.10 MB, one per block. Specify the compact form, and decide whether merged attestations should be capped below 2^17 to bound evidence.
6. **The era invariant has zero slack.** Any proposal to shorten `MIN_VALIDATOR_WITHDRAWABILITY_DELAY` must shorten `EPOCHS_PER_FG_ERA` with it. A staggered per-validator re-draw needs the same check.
7. **Exact vs hash balance.** Revisit if the 2^17 cap binds near V ≈ 10⁶ (§4, §7).
8. **10 s quick slots** (CFI'd for H*). The Q17 grid needs redrawing (2 units per slot gives C = 15 and L = 2 / 3), and the rotation period in hours scales with it.
9. **Beacon API.** An endpoint for `Active(E)`-derived committee sizes, the FG duty `dependent_root`, and reorg signalling for D(curr) through D(curr+2). Head events expose only D(curr+3) and D(curr+4) today.
10. **The rewards spec** must keep the four properties of §11.
11. **The DC-draft fixes** of §9 go to Mikhail.

## Appendix A. Study setup

- **Model** (schedule §1): one vote per validator per round, at its seat, for the latest height it knows, if it has not voted for it yet. The quorum is 2/3 of stake, with the instant switch and a lag of L units. Scenarios: C ∈ {8, 11, 22, 23}, L ∈ 0..5, p ∈ {1, .9, .8, .7, .67}, sudden drops and flapping. Registries are synthetic with Zipf operators and contiguous deposit batches, under three stake mixes.
- **Hypotheses and verdicts:**
  - **H1** (state-free slow forward rotation is best; reshuffles and VRFs are worse and buy no safety): **confirmed, with a direction rule**.
  - **H1b** (composition ≠ position; contiguous blocks cluster; re-draw per era): **confirmed**. The era length is pinned by the withdrawability-delay invariant.
  - **H2** (`Active(E)` fixed after E−5): **confirmed and sharpened**. The key is (E, D(E)), and the bound is tight.
  - **H3** (no FG-safety lever; residual levers bounded): **confirmed for safety, provided slashing evidence stays full size**. "Bounded" needs composition re-randomised.
  - **H4** (seat effects small, fixed by rotation): **partly confirmed**. Relative-order effects need reward design.
- **Lanes:**
  - A, schedule, by the consensus-protocol agent: [`analysis/schedule.md`](analysis/schedule.md) and [`sim/schedules.py`](sim/schedules.py);
  - B, network, by the p2p agent: [`analysis/network.md`](analysis/network.md) and [`sim/sizing.py`](sim/sizing.py);
  - C, anchor: [`analysis/anchor.md`](analysis/anchor.md) and [`sim/anchor_check.py`](sim/anchor_check.py);
  - synthesis and strawman: this note and [`sim/strawman.py`](sim/strawman.py);
  - red team: two independent reviewers, adversarial/economic and client/spec (Appendix B).
- **Sources.** Mikhail's DC draft (fetched 2026-10-02), consensus-specs @ a7ab94b, the fradamt Simplex spec, Prysm @ 88ef966, go-libp2p-pubsub v0.14.0, the ethresearch and Eth R&D Discord mirrors, and the FF design chat of 2026-10-01/02. The lane notes cite chat messages by id.
- **Lane-note conventions.** "The brief" in the lane notes is the shared setup this appendix summarises. "Brief §4" is the planning-sim table, reproduced as schedule E1a.

## Appendix B. Red-team findings and resolutions

| Finding | Severity | Resolution |
|---|---|---|
| Committee-sized slashing evidence breaks accountable safety (on-chain votes need not cross gossip; merged BLS aggregates cannot be split) | critical | Withdrawn. Full-size evidence is kept, with an optional compact form (§7) |
| Subnet and membership REJECT depend on the era seed and set, which differ across deep forks | major | REJECT only on a locally finalized anchor, else IGNORE (§2, strawman T5) |
| Era length has zero slack against the withdrawability delay; waiting for finality breaks it | major | Invariant asserted (§2, T9); boundaries at fixed epochs (§4) |
| Gap lemma assumes an honest includer and an unwritten re-vote rule | major | Bound qualified: L_max + 3k + G (+ G per split). Validator rule specified (§2, §8) |
| Lane gossip lists contradict §2 (horizon REJECTs, a clock-based REJECT, a 128-member floor) | major | §2 is normative; the lane notes mark what they supersede |
| No message containers or aggregate rules (unsigned `committee_index` relabel) | major | `SingleAttestation2` without `committee_index`; full aggregate list with a signed `fg_dependent_root` and selection proofs (§2, T7) |
| "8 attestations per round" does not hold with late +4 s supersets and hash imbalance | major | Restated as 8–16 (§7) |
| Burst bound is 3β, not 2β; disjoint aggregates are not deduplicated | minor | 3β (T9); aggregate forwarding horizon of 4 s (§6) |
| Hard start burns on-time votes at slow-clock receivers | minor | Publish at unit start + 0.5 s (§2, §6, T5) |
| Dedup must insert only after validity; unknown targets race the block; missing rules (empty pairs, invalid target, equivocators, no local set) | minor | All in §2's list (T5) |
| Cache entry ~8 MB, not 4 MB; head-lag needs one epoch advance per branch | minor | Corrected (§5) |
| VC duties need a new beacon-API endpoint | minor | Open issue 9 |
| Self-tests did not exercise aggregates, STF or the seed lookback | minor | T2 mutation check, T7, T8 and T9 added |
| DC-draft table: `get_finality_delay`, pair validation, circular root fix, "C does not divide 2048" | minor | §9 updated |
| Numbers: recommended drop median 1.15 (E13), 2.10 MB at the cap, "attained for all 18", backbone alignment | minor | Corrected |
| Seed revealed ~4 epochs ahead; tail-grinding bound; hash vs shuffle; reward neutrality; concentration bound | ok | Confirmed |

## Files

- `README.md`: this synthesis.
- `analysis/schedule.md`, `analysis/network.md`, `analysis/anchor.md`: the lane reports.
- `sim/strawman.py`: the runnable strawman spec and self-tests.
- `sim/schedules.py`, `sim/sizing.py`, `sim/anchor_check.py`: the lane simulations.
