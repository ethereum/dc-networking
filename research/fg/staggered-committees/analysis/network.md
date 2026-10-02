---
title: Staggered FG committees — network lane (timing enforcement, sizing, aggregation, inclusion)
status: wip
date: 2026-10-02
provenance: agent
---

> **Provenance: agent.** Lane B of the three-lane staggered-committees study (2026-10-02). Yann has not yet reviewed it line by line. Every number is printed by [`../sim/sizing.py`](../sim/sizing.py) (sections S1–S9; run `python3 sim/sizing.py`) or carries a citation.

# Staggered FG committees — network lane

> **Superseded by the [README](../README.md) §2 where they differ** (red-team pass, 2026-10-02):
> - **No "active through the inclusion horizon" REJECT** (§2.3–2.4). Bits of validators that exit before inclusion are decoded and not counted (README §2, STF).
> - **The cohort is a function of the validator index** (era hash, or index mod C), not of a position in the index set (§2.2 `get_fg_duty`).
> - **Committees per unit are the constant 64.** §3.2's 128-member floor would make membership state-dependent, so it remains a devnet-only variant.
> - **Aggregate forwarding:** aggregates are forwarded only for 4 s after their publication time, not until the end of round r+1. Proposers may still include held aggregates until then.
> - **Burst bound:** the withheld-vote burst bound is 3β, not 2β, because the 9 s windows overlap (README §6).
> - **Slashing evidence:** §5.4's committee-sized slashing evidence is **withdrawn**, because it breaks accountable safety (README §7). Evidence keeps the 2^17 bound, with an optional compact form.
> - **Inclusion:** 8–16 attestations per round, not 8, once late +4 s supersets and hash imbalance are counted (README §7).
> - **REJECT guard:** deterministic gossip failures REJECT only when the node's D(E) is finalized locally (README §2).

## TL;DR

- **Switch lag L.** Under Mikhail's STF the next height is created by the block that carries the quorum, and that block *is* the new height's target (mk:950-954). A voter can therefore switch only after it has seen the including block.
  - On the Q17 grid, with voters signing at unit start, the quorum-completing unit at +0 / +4 / +8 s gives **L = 3 / 2 / 4 units**. That is 12 / 8 / 16 s of stale voting, and the round mean is 2.83 at C = 23.
  - A missed next block, or aggregates that miss it, adds 3 units (**L = 6 / 5 / 7**). On today's mainnet about 4 % of attestations miss the next slot. A block that is merely seen late (after +4 s) adds 1 unit.
  - **For the synthesis:** L = 3 is the representative row, 2–4 the typical band and 5–7 the tail. Of the tail, only L = 5 lies inside Lane A's 0..5 sweep.
  - One unit per slot (C = 8) gives L = 0 for a today-shaped unit and L = 1 for explainer Option 5.
- **Timing rule.**
  - Hard start: `[IGNORE]`, and the vote must never be queued for later.
  - Soft end on gossip: one unit (4 s) after the aggregation cut.
  - Two late aggregators per committee publish a superset at the soft end.
  - Aggregates propagate until the end of round r+1, which is Mikhail's inclusion horizon.
  - Windows cap an adversary's worst instantaneous burst at 2β units (0.67 units at β = 1/3). Without windows it is 7.67 units, and with an open-ended soft end 15.3 units.
- **Committee count.** Use one committee per subnet per unit, i.e. 64, floored at 128 members. Derive the subnet from the cohort's identity, not its position.
  - Mikhail's 2048 committees per round split 89/90 per unit at C = 23, which puts twice the load on 25 of the 64 subnets.
  - At V = 120k, 2048 committees make a third of all validators aggregators every round.
- **Per-node load.** The global aggregate topic dominates per-node FG bytes, not the subnets.
  - At V = 1M and C = 23 it is 75 % of 17.8 Mbit/s (κ = 7 duplicate model). Today's attestations cost 4.6 Mbit/s under the same model.
  - The levers are committees per unit, aggregators per committee and the 256-byte `CommitteeBits` (S2e).
- **Subnet churn per validator per day.**
  - Rotating only position: 0.
  - Era shuffle: 1.
  - Slide-by-1: 1.8 at 1M, 15 at 120k.
  - Per-epoch reshuffle: 225.
  - Per-round reshuffle: 900.
- **Inclusion.** Merge same-data aggregates per block. That gives 8 on-chain attestations per round, and they fit the 2^17-bit cap up to V = 1,004,885.
  - At 1M this costs the same bytes as full per-round aggregation, keeps the instant switch, and needs 8 PQ proofs per round instead of 23.
  - Height switches add about 1.2 data values per round.
  - Aggregators must aggregate both heights' data. Otherwise a 5 % minority finds no matching aggregator in 45 % of committees.
- **Slashing evidence** reaches 696 kB (per-unit aggregate) to 2.09 MB (per-block merged) per `AttesterSlashing2` at 1M. That is 1.39–4.18× the 488 KB that made EIP-7549 cut `MAX_ATTESTER_SLASHINGS` to 1. Evidence built from gossip aggregates is 11.2 kB.
- **"No committees, transport cap" (msg 1476): no.**
  - go-libp2p-pubsub keeps one FIFO queue per peer and has no prioritisation.
  - Under a 20 % cap, a round-start burst takes 35–70 s to drain.
  - Without partitioning, every aggregate carries a 125 kB bitfield.
- **Single-operator cohorts (msg 1497).**
  - Contiguous layouts put 32 % (batch of 1,000) to 93 % (batch of 10,000) of an operator's validators into committees it fills alone.
  - That is free batching, but it also means instant deanonymisation.
  - An honest minority with share h in a mixed committee loses its only honest aggregator with probability e^(−16h), i.e. 45 % at h = 5 %.
  - Strided or era-shuffled composition removes the effect.

## 0. Conventions and sources

- **Notation.** V = validators, P = peers (`design/requirements.md:25-29`); the brief's n is V. C = units per round. A unit is 4 s of voting plus 4 s of aggregation on the Q17 grid (`research/fg/pipelined-units/README.md:23-24, :57-64`).
- **Source keys.**
  - **mk:N** is line N of Mikhail's draft [`_features/decoupled-consensus/beacon-chain.md`](https://github.com/mkalinin/eth2.0-specs/blob/dc-feature/specs/_features/decoupled-consensus/beacon-chain.md), fetched 2026-10-02.
  - **msg N** is an FF-team chat message id.
  - Spec references are to consensus-specs `a7ab94b`, go-libp2p-pubsub `v0.14.0` and Prysm `88ef96684e`.
  - **ethresearch N:L** is line L of thread N in the vault's forum mirror.
  - **README:N** is `research/fg/pipelined-units/README.md` (Q17).
  - **brief §N** is the shared lane brief of 2026-10-02, which is not in this repo; [README Appendix A](../README.md#appendix-a-study-setup) summarises it. Its §4 rounds-per-height figures are Lane A's preliminary planning sims, reproduced as E1a in `analysis/schedule.md`.
- **Definition of L** (as in brief §4). L is the number of units strictly between the unit whose votes complete the quorum and the first unit whose voters sign for the new height. L = 0 means the very next unit votes fresh.
- **Gossip byte model (S2d).** These are model bounds, not measurements (open issue 1).
  - Every FG message is below the 1 KiB IDONTWANT threshold (go-libp2p-pubsub `gossipsub.go:75`), so IDONTWANT never fires.
  - With eager push, each non-origin node forwards once to its D − 1 non-source mesh peers. A subscribed node therefore receives κ ≈ D − 1 = 7 copies on average; κ = 1 is the floor.
  - IHAVE: each 0.7 s heartbeat, a node advertises the ids of the last `mcache_gossip` = 3 windows to max(D_lazy, ⌊0.25 × non-mesh topic peers⌋) peers (`gossipsub.go:52-54, :1853-1864`). Prysm keeps those defaults (`beacon-chain/p2p/pubsub.go:212-222`).
  - With 20-byte message ids (`specs/altair/p2p-interface.md:159-166`) that is 1,380 B per message on a global topic with 100 peers, and 240 B per message on a subnet with 12 topic peers.

## 1. Switch lag L (RQ5)

### 1.1 Trace

For a unit starting at s (Q17 grid; "P1" means voters sign at s, README:32):

1. Voters vote in [s, s+4). Aggregators publish at s+4, and the aggregates have propagated ("landed") by s+8 (README:57).
2. The first block proposed at or after the landing includes them. The landing-to-proposal margin is 8 / 4 / 12 s for units at +0 / +4 / +8 (README:64). The +4 unit's 4 s is tighter than Gloas's own 6 s aggregate-to-block margin (`specs/gloas/validator.md:42`; S2c).
3. `process_height_events` runs in that block's STF (mk:926, :969-988). `advance_height` makes that very block the target of h+1 (mk:950-954).
4. Voters see the block δ_b later.
   - The protocol budget is ≤ 3 s under Gloas (`ATTESTATION_DUE_BPS_GLOAS`, `specs/gloas/validator.md:41`).
   - On mainnet, 95 % of block+blob bundles arrived inside the old 4 s deadline (ethresearch 21096:162), with maximum arrival times reaching almost 12 s (ethresearch 19982:91).
5. The first unit whose signing time is at or after block arrival votes for h+1.

Because the target of h+1 is the including block itself, no voter can switch early on seeing the aggregates land. An "off-chain switch" would need a different STF, in which the vote names its own target and is accepted once h is justified. That is a decision for the STF owners, not the network.

### 1.2 Result (S1)

| quorum unit offset | lands | included by | **L (P1)** | stale window | L, +0 units wait for block | L, off-chain switch | L, next block missed | L, block seen after +4 s |
|---|---|---|---|---|---|---|---|---|
| +0 s | +8 s | next slot | **3** | 12 s | 2 | 1 | 6 | 4 |
| +4 s | +12 s | next slot | **2** | 8 s | 1 | 1 | 5 | 3 |
| +8 s | +16 s | slot after next | **4** | 16 s | 3 | 1 | 7 | 5 |
| round mean, C = 23 (all units) | | | **2.83** | | 1.83 | 0.96 | 5.70 | 3.83 |

- **Round boundary.** Q17 has no 24th unit, so the last units have one fewer stale unit after them. u20 (+8) has L = 3, u21 (+0) L = 2, and u22 (+4) L = 1.
- **Other grids.** C = 22 (grid shifted by 4 s, README:146) and C = 11 (4-slot round) have the same interior values. Their round means are 2.68 and 2.64.
  - At C = 11 the stale units are **24 %** of the round, against 12.3 % at C = 23. The 4-slot stretch goal keeps L constant in units but halves C.
  - With 10 s quick slots (CFI'd for H*, msg 1623) and two units per slot at +0/+5 s (C = 15), L = 2 / 3 and the mean is 2.33.
- **One unit per slot (C = 8).**
  - A today-shaped unit (vote on block arrival, aggregate at 50 % of the slot, land by the next slot) gives **L = 0**, or 1 after a missed block.
  - Explainer Option 5 (vote in slot i, aggregate in i+1, include in i+2; `design/requirements.md:62-65`) gives **L = 1**, or 2.
- **Tail weight.** 95.85 % of mainnet attestations are included in the next slot and about 1.2 % in the slot after (ethresearch 20020:95-96). The +3 step therefore has roughly 4 % weight.
- **Letting +0 units wait for the block** saves one unit but breaks P1. Those votes get about 1 s instead of 4 s before the cut, because δ_b is budgeted at 3 s. The +0 unit's votes also split into two data values (§5.2).

**Reading.** In wall-clock time the stale window is set by the block pipeline (aggregation cut → next block → arrival). It is 8–16 s whatever the unit length; finer units simply fit more units into it. As a share of the round's units, L/C is the same for Q17 (12.3 %) and Option 5 (12.5 %). Today-shaped C = 8 reaches 0 %, but it pays with 4× today's per-slot vote load in a single window (S2b).

### 1.3 Range handed to the synthesis

- **Representative: L = 3** (round mean 2.8). Band: **L ∈ {2, 3, 4}** depending on the quorum unit's offset; Lane A should weight these by where its quorums complete.
- **Tail: L ∈ {5, 6, 7}** when the next block is missed or the aggregates miss it (about 4 % of mainnet attestations). Lane A's L = 5 row is only a lower bound for this tail. A block seen after +4 s gives L ∈ {3, 4, 5}.
- **Variants.** If +0 units wait for the block, subtract 1 (mean 1.83). With an off-chain-switch STF, L ≈ 1. With one unit per slot, L ∈ {0, 1}.

## 2. Timing-window rule (RQ5)

### 2.1 Requirements

- **Hard start.** A vote published before its window opens is dropped at the first hop. This is how staggering is enforced (msgs 1466, 1477).
- **Soft end.** Late votes keep a path when the network struggles. That is the resilience half of msgs 1424/1429; msg 1430 gives blob spikes as the example. Sukun estimates that about 20 % of mainnet publishes late (`meetings/2026-09-22.md:52`).
- **The soft end must be bounded on gossip.** Otherwise an adversary can withhold votes and release them all at once (§2.5).
- **State-free membership.** Gossip checks membership from (validator_index, round) plus a cached index set. That set must be fixed by the round alone: not by the target, and not by the finalized checkpoint (§8 flag 5). Lane C owns its definition. This is what client developers asked for: "p2p validation becomes a pure function of the message plus a cached set" (msg 1527; also msgs 1501, 1514).

### 2.2 Constants and helpers (placeholders; values per Lanes A/C)

```python
UNITS_PER_ROUND = 23                       # C (Lane A)
UNIT_SPACING_MS = SLOT_DURATION_MS // 3    # 4000
FG_VOTE_PHASE_MS = 4000                    # aggregation cut (README:23)
FG_LATE_WINDOW_MS = 4000                   # soft end on gossip = one unit spacing (S1b)
TARGET_LATE_AGGREGATORS_PER_COMMITTEE = 2  # msg 1441
MAX_FG_AGGREGATE_DATA_PER_AGGREGATOR = 2   # current and previous height (5.2)

class FGDuty(Container):
    unit: uint64                       # position of the validator's cohort in this round (Lane A)
    committee_index: CommitteeIndex    # round-wide index = unit * committees_per_unit + j (3.2)
    subnet_id: SubnetID                # compute_fg_subnet(cohort, j, ...): tied to cohort identity (3.2, 4)
    position: uint64                   # bit index inside the committee

def get_fg_index_set(round: Round) -> FGIndexSet:
    """Lane C. Cached; identical in every state that processed the epoch it is pinned to.
    Per position: validator_index, pubkey, activation_epoch, exit_epoch."""

def get_fg_duty(index_set: FGIndexSet, validator_index: ValidatorIndex, round: Round) -> Optional[FGDuty]:
    """Pure in (index_set, validator_index, round); cohort = f(position, round) per Lane A."""

def compute_unit_start_ms(genesis_time: uint64, round: Round, unit: uint64) -> uint64:
    return (genesis_time * 1000
            + compute_start_slot_at_round(round) * SLOT_DURATION_MS
            + unit * UNIT_SPACING_MS)

def is_active_through_inclusion_horizon(entry: FGIndexEntry, round: Round) -> bool:
    # mk:714-718 rejects an on-chain attestation if any set bit belongs to a validator that is inactive
    # at the including block's epoch; inclusion is allowed until the end of round + 1 (mk:657-660).
    first = compute_epoch_at_round(round)
    last = compute_epoch_at_slot(Slot(compute_start_slot_at_round(Round(round + 2)) - 1))
    return entry.activation_epoch <= first and entry.exit_epoch > last
```

`activation_epoch` and `exit_epoch` are written once, at least `1 + MAX_SEED_LOOKAHEAD` epochs ahead (`specs/phase0/beacon-chain.md:913-917`). The inclusion horizon is at most 2 rounds (16 slots). A cache up to 4 epochs behind the head therefore answers `is_active_through_inclusion_horizon` deterministically.

### 2.3 `beacon_attestation_{subnet_id}` (DC)

The topic carries `SingleAttestation` with `data: AttestationData2`, which is 200 B (8 + 8 + 88 + 96). Electra's `SingleAttestation` is 240 B (`specs/electra/beacon-chain.md:309-313`). Define `data = attestation.data`, `index_set = get_fg_index_set(data.round)`, `duty = get_fg_duty(index_set, attestation.attester_index, data.round)` and `start = compute_unit_start_ms(genesis_time, data.round, duty.unit)`. The checks run from cheap to BLS:

- _[IGNORE]_ `index_set` is available locally. The vote MAY be queued until it is; Lane C fixes how far ahead the set is known.
- _[REJECT]_ The attester has an FG duty this round (`duty is not None`) and claims its own committee (`attestation.committee_index == duty.committee_index`).
- _[REJECT]_ The vote is on its subnet: `subnet_id == duty.subnet_id`.
- _[REJECT]_ The attester stays active through the inclusion horizon: `is_active_through_inclusion_horizon(index_set[duty.position], data.round)`.
- _[IGNORE]_ **Hard start:** `current_time_ms + MAXIMUM_GOSSIP_CLOCK_DISPARITY >= start`. The vote MUST NOT be queued for later forwarding. This deliberately departs from phase0's "MAY be queued" (`specs/phase0/p2p-interface.md:651-652`).
- _[IGNORE]_ **Soft end:** `current_time_ms <= start + FG_VOTE_PHASE_MS + FG_LATE_WINDOW_MS + MAXIMUM_GOSSIP_CLOCK_DISPARITY`.
- _[IGNORE]_ No other valid vote has been seen for `(attestation.attester_index, data.round)`. This replaces the per-target-epoch key of `specs/phase0/p2p-interface.md:979-982`.
- _[REJECT]_ The signature is valid under `DOMAIN_BEACON_ATTESTER_2` at `compute_epoch_at_round(data.round)` (mk:786-789). The pubkey comes from `index_set`.
- _[IGNORE]_ The target is known: either `data.target_pair.root == Root()` (a progress vote, mk:736), or the node has imported the block that defines the root (§8 flag 1).
- Clients MAY also _[IGNORE]_ votes whose `target_pair.height` is below their head's `justified_pair.height`, because such votes cannot be included on their chain (mk:668-677). This is the only use of head state, and it is never a REJECT.

### 2.4 `beacon_aggregate_and_proof` (DC)

Define `aggregate = signed_aggregate_and_proof.message.aggregate`, `data = aggregate.data`, `committee_index = get_committee_indices(aggregate.committee_bits)[0]`, `committee = get_fg_committee(index_set, data.round, committee_index)` and `cut = compute_unit_start_ms(genesis_time, data.round, unit_of(committee_index)) + FG_VOTE_PHASE_MS`.

- _[REJECT]_ Exactly one committee bit is set (as in `specs/electra/p2p-interface.md:120-121`), and `committee_index < get_committee_count_per_round(index_set)`.
- _[IGNORE]_ `index_set` is available locally.
- _[REJECT]_ `len(aggregate.aggregation_bits) == len(committee)`, at least one bit is set, and every set bit belongs to a validator active through the inclusion horizon. A single inactive bit invalidates the whole on-chain attestation (mk:714-718).
- _[IGNORE]_ **Hard start:** `current_time_ms + MAXIMUM_GOSSIP_CLOCK_DISPARITY >= cut` for an on-time aggregator, and `>= cut + FG_LATE_WINDOW_MS` for a late aggregator. The aggregate MUST NOT be queued.
- _[IGNORE]_ **Inclusion horizon:** `current_time_ms <= genesis_time * 1000 + compute_start_slot_at_round(Round(data.round + 2)) * SLOT_DURATION_MS + MAXIMUM_GOSSIP_CLOCK_DISPARITY`. This is Mikhail's current-or-previous-round rule (mk:657-660), and it needs only genesis time.
- _[IGNORE]_ No valid aggregate with a superset of these bits has been seen for `hash_tree_root(data)` (`specs/phase0/p2p-interface.md:672-677`).
- _[IGNORE]_ This is the aggregator's first aggregate for `(data.round, hash_tree_root(data))`, and fewer than `MAX_FG_AGGREGATE_DATA_PER_AGGREGATOR` data roots have already been seen from it in `data.round`. This replaces `specs/phase0/p2p-interface.md:679-683`.
- _[REJECT]_ The aggregator is in `committee`, and its selection proof selects it. Selection uses `is_fg_aggregator`, or `is_fg_late_aggregator` under a separate domain. The proof signs `data.round`, the analogue of `get_slot_signature` (`specs/phase0/validator.md:726-738`).
- _[REJECT]_ The selection proof, the aggregator signature and the aggregate signature are all valid.
- _[IGNORE]_ The target is known (as for votes).

**State read by §2.3–2.4** (input to Lane C's table):
- Genesis time and the local clock, for every timing condition.
- The round's cached index set (positions, pubkeys, activation and exit epochs), for membership, subnet, activity and signatures.
- The seen caches.
- The block DB, for "target known".
- The node's own head state, only for the optional IGNORE filter.

**Honest behaviour (validator-guide side).**
- Voters sign and publish at `start`, using the head state at that instant (P1).
- On-time aggregators publish at `cut` one aggregate per distinct data value they saw (at most 2), not only for their own data (`specs/phase0/validator.md:745-747`; §5.2).
- Late aggregators publish at `cut + FG_LATE_WINDOW_MS`, and only if they hold votes that are not in the best on-time aggregate. They BLS-add those signatures to that aggregate, whose signer set is disjoint from them. The result is a strict superset, and the superset rule drops every other copy.

### 2.5 Rationale

- **IGNORE, not REJECT, for clock conditions.** This is the spec's convention for timing ranges (`specs/phase0/p2p-interface.md:651-656`). A REJECT would give honest peers with skewed clocks invalid-message penalties and get them pruned from meshes. That is exactly the brittleness `MAXIMUM_GOSSIP_CLOCK_DISPARITY` exists to prevent (`specs/phase0/p2p-interface.md:2083-2097`). REJECT is kept for what the cached set decides deterministically: membership, subnet, activity and signatures.
- **Disparity on both ends,** as in `is_within_slot_range` (`specs/phase0/p2p-interface.md:318-335`). The 500 ms allowance (`specs/phase0/p2p-interface.md:231`) is 12.5 % of a 4 s window. Sukun proposed using exactly that allowance (`meetings/2026-09-22.md:70`).
- **An early vote is a lost vote, so it must not be queued.** go-libp2p-pubsub marks a message id as seen *before* topic validators run (`validation.go:322-329`).
  - An IGNOREd early vote is therefore burned at that peer for `seen_ttl` = 768 s (`specs/phase0/p2p-interface.md:449-450`; Prysm `pubsub.go:226-229`).
  - The hard start is sharp in practice: a validator whose clock runs more than 500 ms fast loses its vote.
  - Queueing early votes and releasing them at the window start, as today's "MAY be queued" allows, would recreate the spike at the start. It is therefore forbidden.
- **Late window W = one unit (4 s)** (S1b).
  - With W = 4 s, late aggregates land in the same block as the on-time ones for +0 and +8 units, and one block later for +4 units.
  - With W = 8 s, the +0 units also slip a block.
  - W also sets the adversarial withhold-and-release bound, β(W + 1) units (S6).
- **Late votes go to a catch-all aggregate, not directly to the proposer.** A direct path is rejected for four reasons:
  - CL req/resp has no push method.
  - It would make the proposer's node discoverable just before its slot, which invites DoS.
  - It bypasses gossip deduplication and peer scoring.
  - It loads per-vote BLS verification onto the proposer while it builds its block.

  Votes later than the soft end are lost for that round. The validator votes again next round, and height participation carries over while the height stalls (mk:130-134).
- **Interaction with the current-or-previous-round rule** (mk:657-660).
  - Aggregates may propagate as long as the STF accepts them. Single votes may not: after the late aggregation nothing on gossip consumes them.
  - The rule makes a **24th unit legal**: its aggregates land in round r+1, and `data.round = r` still counts as the previous round. That removes Q17's 4 s end-of-round gap (README:57). It also answers Mikhail's question on the 2026-09-22 call (`meetings/2026-09-22.md:70`).
  - A stale vote stays includable only while its target is the state's target or justified pair (mk:668-677). After a second height advance it becomes invalid. Its effective horizon is therefore the earlier of the end of round r+1 and two height advances.
  - Deduplication on `(attester, round)` stops a stale voter from re-voting for the new height in the same round. A height switch therefore cannot trigger a burst of L units' worth of re-votes. This also matches Lane A's one-vote-per-round model.
  - If Lane C adopts an anchor carried in the vote and allows re-votes (msg 1639), the key becomes `(attester, round, anchor)` with at most 2 anchors. Re-votes must then be confined to a window; otherwise every anchor change re-sends all units in flight.
- **Why honest random timing is not enough** (msgs 1466, 1480; S6).
  - Without windows, an adversary with stake share β can place β·C units of *valid* votes into one instant: 7.67 units, or 66.7 MB, at V = 1M and β = 1/3.
  - Honest nodes must forward them into the same per-peer FIFO that carries blocks and blobs. go-libp2p-pubsub has one outbound queue per peer, 32 RPCs deep by default (`pubsub.go:468`), and drops when it is full (`gossipsub.go:1400-1411`). Its only urgent lane is IDONTWANT (`gossipsub.go:738`; `rpc_queue.go:16-40`).
  - The hard start keeps an early burst on the adversary's own links, because no honest node forwards it.
  - A one-unit soft end caps a withheld-then-released burst at 2β units (0.67 units at β = 1/3).
  - An open-ended soft end, reaching to the STF horizon, re-opens a 2βC = 15.3-unit burst, which is worse than no windows.
  - Honest timing is not independent either. Voters react to the same block arrival, and they have a reason to wait when Goldfish confirmation is uncertain (msg 1426).

## 3. Sizing (RQ5)

### 3.1 Load per unit vs today's slot (S2a, S2b)

**Today**, Electra sizes (S2a):

| V | attesters/slot | committees × size | aggregates/slot | vote bytes/slot | aggregate bytes/slot |
|---|---|---|---|---|---|
| 120k | 3,750 | 29 × 129 | 464 | 900 kB | 214 kB |
| 500k | 15,625 | 64 × 244 | 1,024 | 3.75 MB | 486 kB |
| 1M | 31,250 | 64 × 488 | 1,024 | 7.50 MB | 518 kB |

**DC**, one committee per subnet per unit (rule A64), 200 B votes, aggregates of 208 + 444 + bitfield bytes (S2b; this is the worst case where every aggregator publishes, msg 1425):

| V | C | voters/unit (× today's slot) | committee | votes/unit/subnet | votes/unit, all subnets | aggregates/unit (bytes) | votes/slot | aggregates/slot |
|---|---|---|---|---|---|---|---|---|
| 120k | 8 | 15,000 (4.00×) | 234 | 46.9 kB | 3.00 MB | 1,024 (698 kB) | 3.00 MB | 698 kB |
| 120k | 11 | 10,909 (2.91×) | 171 | 34.1 kB | 2.18 MB | 1,024 (690 kB) | 6.00 MB | 1.90 MB |
| 120k | 22 | 5,455 (1.45×) | 85 | 17.0 kB | 1.09 MB | 1,024 (679 kB) | 3.00 MB | 1.87 MB |
| 120k | 23 | 5,217 (1.39×) | 82 | 16.3 kB | 1.04 MB | 1,024 (679 kB) | 3.00 MB | 1.95 MB |
| 500k | 8 | 62,500 (4.00×) | 977 | 195.3 kB | 12.50 MB | 1,024 (794 kB) | 12.50 MB | 794 kB |
| 500k | 11 | 45,455 (2.91×) | 710 | 142.0 kB | 9.09 MB | 1,024 (759 kB) | 25.00 MB | 2.09 MB |
| 500k | 22 | 22,727 (1.45×) | 355 | 71.0 kB | 4.55 MB | 1,024 (714 kB) | 12.50 MB | 1.96 MB |
| 500k | 23 | 21,739 (1.39×) | 340 | 67.9 kB | 4.35 MB | 1,024 (712 kB) | 12.50 MB | 2.05 MB |
| 1M | 8 | 125,000 (4.00×) | 1,953 | 390.6 kB | 25.00 MB | 1,024 (919 kB) | 25.00 MB | 919 kB |
| 1M | 11 | 90,909 (2.91×) | 1,420 | 284.1 kB | 18.18 MB | 1,024 (850 kB) | 50.00 MB | 2.34 MB |
| 1M | 22 | 45,455 (1.45×) | 710 | 142.0 kB | 9.09 MB | 1,024 (759 kB) | 25.00 MB | 2.09 MB |
| 1M | 23 | 43,478 (1.39×) | 679 | 135.9 kB | 8.70 MB | 1,024 (755 kB) | 25.00 MB | 2.17 MB |

- The vote load per slot depends only on the round length: V/8 for 8-slot rounds, V/4 for 4-slot rounds. C only sets how concentrated it is inside a 4 s window (32/C × today's slot).
- Aggregates per slot at C = 23 are 4.2× today's at 1M (2.17 MB vs 518 kB) and 9.1× at 120k (1.95 MB vs 214 kB). This is Anton's concern in msgs 1402–1403 and 1435.

### 3.2 Committees per unit and the subnet map (S2c)

- **2048 per round (mk:282) does not divide C.** It gives 89.04 committees per unit at C = 23, 93.09 at C = 22 and 186.18 at C = 11.
  - At C = 23, keeping 2048 means one unit has 90 committees and 22 units have 89. Inside a unit, 25 subnets then carry two committees and 39 carry one: a 2:1 load imbalance.
  - At C = 11, 58 subnets carry 3 committees and 6 carry 2.
- **2048 also ignores V.** At 120k, committees have 58.6 members and the `is_aggregator` modulo is 3 (`specs/phase0/validator.md:737`). A third of all validators would aggregate every round, and the network carries 32,768 aggregates per round at every V. Rule A64 gives 23,552 at C = 23 and 8,192 at C = 8.
- **Recommendation: rule A.**

```python
def get_committee_count_per_unit(index_set_size: uint64) -> uint64:
    # mirrors get_committee_count_per_slot (phase0/beacon-chain.md:1065); since committees are no longer
    # a security unit (mk:144-146) the TARGET_COMMITTEE_SIZE floor is now a load floor
    return max(1, min(ATTESTATION_SUBNET_COUNT,
                      index_set_size // UNITS_PER_ROUND // TARGET_COMMITTEE_SIZE))

# CommitteeBits length: 1472 bits = 184 B at C = 23 (vs 2048 bits = 256 B)
COMMITTEES_PER_ROUND = UNITS_PER_ROUND * ATTESTATION_SUBNET_COUNT

def compute_fg_subnet(cohort: uint64, j: uint64, committees_per_unit: uint64) -> SubnetID:
    # keyed by the cohort's identity (composition), not by its position in the round,
    # so positional rotation never moves a validator to another subnet
    return SubnetID((cohort * committees_per_unit + j) % ATTESTATION_SUBNET_COUNT)

# round-wide committee index (CommitteeBits / aggregation-bit order) = unit * committees_per_unit + j,
# so the 2-3 units landing in one block occupy a contiguous CommitteeBits range (5.1)
```

- The rule reaches 64 committees per unit once V ≥ C × 64 × 128, i.e. 188,416 at C = 23 and 65,536 at C = 8.
- Below that it shrinks committees per unit instead of committee size. At 120k and C = 23 it gives 40 committees of 130, i.e. 640 aggregates per unit instead of 1,024 (S2c).

### 3.3 Per-node bytes (S2d, S2e)

Per-node received FG traffic, with 2 backbone subnets plus the global aggregate topic, κ = 7 plus IHAVE:

| V | C = 8 (12 s unit) | C = 11 | C = 22 | C = 23 | today (per 12 s slot) |
|---|---|---|---|---|---|
| 120k | 4.7 Mbit/s (aggregates 89 %) | 13.6 (92 %) | 12.9 (96 %) | 12.9 (96 %) | 1.8 Mbit/s |
| 500k | 6.8 (69 %) | 18.1 (74 %) | 15.1 (85 %) | 15.0 (85 %) | 3.8 |
| 1M | 9.5 (55 %) | 24.0 (61 %) | 18.1 (74 %) | 17.8 (75 %) | 4.6 |

- **The global aggregate topic is the dominant per-node FG cost on the Q17 grid.** It receives 1,024 aggregates every 4 s, and each is under 1 KiB, so they draw the full κ and 1,380 B of IHAVE apiece.
  - This matches Anton's simulation: the IHAVEs for FG votes and aggregates alone were roughly 30 % of all traffic on a 100-peer home node (msgs 1508, 1627).
  - The C = 8 column averages over a 12 s unit, but its votes still arrive in a burst bounded by the attestation deadline (3 s under Gloas, `specs/gloas/validator.md:41`).
- **All-subnet supernodes** receive 122 Mbit/s of votes alone at V = 1M, C = 23 and κ = 7 (compare 250 Mbit/s of IHAVE on supernodes, msg 1510).
- **Levers on the aggregate topic** at V = 1M, C = 23 (S2e). The aggregate topic alone costs 13.4 Mbit/s. It falls to:
  - 9.8 Mbit/s with `Bitvector[64]` instead of `CommitteeBits[2048]`. This is raw SSZ: Snappy compresses the zero run, so the real gain is smaller and was not measured.
  - 6.7 Mbit/s with 8 aggregators per committee.
  - 2.8 Mbit/s with 32 committees per unit, 8 aggregators and `Bitvector[64]`.
- The aggregator count and per-unit committee count are parameters the brief fixes as today's (64 × 16). They are flagged here because they matter more than the cohort map does.

## 4. Cohort→subnet mapping and churn (RQ5)

The backbone stays as it is: 2 subnets per node, chosen by node id and rotated every 256 epochs, i.e. 27.3 h (`specs/phase0/p2p-interface.md:229, :1724-1750`). Only the duty assignment rotates on top of it (`research/transitions/survey.md:414-420`).

| candidate | duty-subnet reassignments per validator per day | lookahead before a change |
|---|---|---|
| position rotates (any K), subnet = f(cohort identity) | **0** | n/a |
| era-shuffled composition (daily) | **1** | the era boundary is known in advance |
| Mikhail slide-by-1 (subnet = committee mod 64) | 15.4 at 120k (every 1.6 h), 3.7 at 500k (6.5 h), **1.8 at 1M (13.0 h)** | deterministic |
| per-epoch reshuffle (every 4 rounds; fradamt spec) | 225 | about 1 epoch if seeded one epoch back |
| per-round reshuffle | 900 | at most 1 round (96 s) |

- **Aggregator duty churns regardless of the mapping**, because selection happens every round with probability 16/c. That is 21 duties per validator per day at 1M (A64, C = 23), 42 at 500k and 177 at 120k.
  - Each duty means GRAFT/PRUNE on the duty subnet unless the node keeps that subnet subscribed.
  - Keeping one extra subnet costs 1.90 Mbit/s at κ = 7 (plus 0.33 Mbit/s IHAVE) at 1M, against 0.55 Mbit/s for a subnet today, because every DC subnet is busy in every unit.
  - So persistent subscription only makes sense for small nodes, and only with stable subnets.
- **Slide-by-1 changes a validator's unit only every V/C rounds,** i.e. every 48 days at 1M. It is the slowest possible positional rotation, which is Lane A's fairness question.
- **A per-round reshuffle leaves at most 96 s to find peers on a new subnet.** Today's validator guide budgets an epoch for that (`specs/phase0/validator.md:335-360`; `research/transitions/survey.md:416-418`).
- **Privacy.** A stable validator→subnet map makes the subnet-fingerprinting surface static. That is accepted in phase 1 (`design/requirements.md:76-79`), but flagged here.
- **A secret VRF duty** (`design/explainer.md:21`) needs a proof in every vote (the open item at `design/explainer.md:41`). That adds 96 B, i.e. 48 % of a 200 B vote, plus one more BLS verification per vote. A public deterministic map needs no proof.

## 5. Aggregation and inclusion (RQ6)

### 5.1 Inclusion granularity (S3)

On-chain cost per round, one data value per unit:

| V | per-unit (C = 23): #, bytes | per-block merge: #, max bits per attestation | full per-round: #, bytes |
|---|---|---|---|
| 120k | 23, 25.3 kB | 8, 15,652 | 1, 15.4 kB |
| 500k | 23, 72.8 kB | 8, 65,217 | 4, 64.3 kB |
| 1M | 23, 135.3 kB | 8, 130,435 (≤ 131,072) | 8, 128.6 kB |

- **BLS.** The largest byte gap between the three options is 6.7 kB per round at 1M, 8.5 kB at 500k and 9.9 kB at 120k. That sits on top of the V/8 participation bits every option needs (125.0 / 62.5 / 15.0 kB). Pairing checks run 23 vs 8 vs 1–8 per round, which is negligible next to the V public-key additions every option needs.
- **Full per-round aggregation** (msg 1494) advances heights at most once per round, so it gives up the instant switch. At 1M it still needs 8 attestations, because of `MAX_VALIDATORS_PER_AGGREGATE` = 2^17 (mk:283). Msg 1496 makes the same point for 8-slot rounds.
- **Per-block merge.** The proposer merges same-data aggregates from the 2–3 units that land in its block into one attestation via round-wide `CommitteeBits` (mk:245-251), in the style of EIP-7549. It keeps the instant switch, uses 8 attestations per round, and leaves room for fragmentation within the 8-attestation block budget (mk:1164).
  - The limit: three Q17 units fit 2^17 bits only up to V = 1,004,885. C = 22 at 1M needs a second attestation in full blocks, and C = 8 per-unit attestations break above V = 1,048,576.
- **PQ** (msgs 1494, 1496): proofs per round are 23 (per-unit), 8 (per-block) or 1 (per-round).
  - Per-block merging costs two 2-to-1 recursions per block, at 0.29 s each (msg 1399). It is the smallest proof count that keeps the instant switch.
  - Proof sizes are not in the local corpus (open issue 5).

### 5.2 Target fragmentation at height boundaries (S3b)

- **Normally one data value per unit.** A unit has one round, one target pair and one finalize pair (mk:311-318). All h+1 voters on one branch name the same target, the including block (§1.1).
- **At a switch under P1,** the stale units are uniformly stale. Only the first fresh unit (+4 after the block) splits, and only by its minority that saw the block late (about 5 %, ethresearch 21096:162). With "wait", the +0 unit splits as well.
- **Cost:**
  - 1/(0.826–0.857) = 1.17–1.21 extra data values per round. The 0.826–0.857 rounds per height are the brief's §4 values at L = 3 for the fixed through +1-per-round schedules.
  - That is +5 % on-chain attestations (per-unit inclusion) and up to 1,195–1,240 extra gossip aggregates per round (+5 % of 23,552).
- **The bigger risk is losing the minority.**
  - Aggregators aggregate only their own data (`specs/phase0/validator.md:745-747`), and gossip accepts one aggregate per aggregator (`specs/phase0/p2p-interface.md:679-683`).
  - A minority with share μ of a committee then finds no matching aggregator with probability ≈ e^(−16μ): 0.73 at 2 %, 0.45 at 5 %, 0.20 at 10 %.
  - Fix: aggregators aggregate every data value (at most 2), and gossip deduplication is keyed per data root (§2.4). These stale votes are exactly the ones Yann wants rewarded (msg 1546).
- **Other sources of extra data values:**
  - forks, where target roots differ by branch (msg 1558);
  - previous-round late aggregates, whose `data.round` differs;
  - progress votes with root 0.

  With per-unit attestations these approach the 8-per-block cap. Per-block merging needs only one attestation per distinct data value.

### 5.3 Bit layouts Lane C may choose (S4)

Inputs:
- At most 8 exits per epoch: the 256 ETH exit churn divided by 32 ETH (`specs/electra/beacon-chain.md:621-625`, `configs/mainnet.yaml:129`).
- At most about 64 registry entries awaiting activation in steady state.
- Never-eligible sub-32-ETH entries add to Mikhail's set forever; their mainnet count is unknown.

| layout | bits per round | V = 1M | V = 120k | state-free? |
|---|---|---|---|---|
| active at epoch e (msg 1562) | V | 125.0 kB | 15.0 kB | yes, with a per-epoch cache |
| Mikhail: `exit_epoch > finalized` (mk:862-868) | V + exits since finalized + pending | +0.008 % healthy; +1.27 % after 1 week of non-finality | +0.067 %; +10.6 % | cache, but it shifts when finality moves (§8 flag 5) |
| raw `validator_index`, no set | R (registry length) | +25 / +50 / +100 % for R = 1.25 / 1.5 / 2 V | same | yes, but with holes and uneven units |

- **Contiguous vs strided blocks.** Both carry the same number of bits, and both need each validator's position (its rank in the set). An O(1) position array costs 4 MB at 1M and 480 kB at 120k. The differences:
  - Contiguous layouts cluster holes and operators. One operator going offline leaves a whole committee near-empty, and single-operator committees appear (§7). Strided layouts spread both.
  - Slide-by-1 changes each contiguous committee by one member at each edge every round.
  - Snappy compresses contiguous zero runs better (not measured).

### 5.4 Slashing evidence (S5)

`AttesterSlashing2` size, depending on which aggregate the slasher holds:

| what the slasher holds | k per side | V = 1M, C = 23 | V = 1M, C = 8 |
|---|---|---|---|
| single votes | 1 | 400 B | 400 B |
| gossip aggregate (one committee) | c | 11.2 kB | 31.6 kB |
| on-chain per-unit attestation | V/C | 696.0 kB | 2.00 MB |
| on-chain per-block merged attestation | 3V/C | 2.09 MB | 2.00 MB |
| cap (mk:283) | 131,072 | 2.10 MB | 2.10 MB |

- EIP-7549:64 quotes 488 KB (320 KB after Snappy) per `AttesterSlashing` at 1M. That alone cut `MAX_ATTESTER_SLASHINGS` to 1.
- DC evidence is 1.39× that (per-unit) to 4.18× (per-block). One `AttesterSlashing2` is allowed per block (mk:1169); this is mk:105-106's TODO.
- **Recommendation:** bound `IndexedAttestation2` to committee-sized evidence. Slashers keep the gossip aggregates, which every node sees on the global topic. Evidence is then at most 11.2 kB at 1M/C = 23.

## 6. "No committees, transport rate limit" (msg 1476)

- **There is no prioritisation to build on** (msgs 1432–1433; README:138).
  - go-libp2p-pubsub v0.14.0 has one FIFO per peer, and only IDONTWANT is urgent (§2.5).
  - A per-topic bandwidth share would need a new scheduler at every hop.
  - Transport-level priorities only work within one connection (README:111; `meetings/2026-09-22.md:74`).
- **Even with a 20 % share, a round-start burst drains slowly** (S9). At V = 1M, all votes at round start put 6.25 MB (κ = 1) to 43.75 MB (κ = 7) on a node's two subnets.
  - Draining takes 10–70 s on a 25 Mbit/s link and 5–35 s on 50 Mbit/s.
  - The aggregation cut therefore moves tens of seconds into the round, and heights can no longer progress within two-thirds of a round (mk:116-117).
  - Behind drop-on-full queues, the backlog becomes lost votes rather than late ones.
- **Without any partition,** each aggregate carries V bits = 125 kB (msg 1457), and every node receives the full 200 MB-per-round vote firehose.
- **A cap protects blocks from votes, but not honest votes from adversarial ones.** A FIFO has no per-origin fairness, so an adversary's round-start burst fills the cap first.
- Anton's simulation already found overlapping committees "a no go picture. At least without prioritization" (msg 1403). All-at-once voting is the limit case of overlap.
- **Verdict: no, as a replacement for windows.** A per-topic cap is still worth adding *on top of* windows, as a backstop for block and blob propagation, following Mikhail's priority order (msg 1433).

## 7. Single-operator cohorts (msg 1497)

- **Mechanism.** An operator that holds an entire committee also holds all of its aggregators. It can aggregate locally and publish a single aggregate, so that committee causes zero subnet traffic. This is EIP-8243-style batching at source, for free.
- **Likelihood** (S8). Expected share of an operator's batch that lands in committees it fills alone:

  | layout | c (setting) | batch of 100 | batch of 1,000 | batch of 10,000 |
  |---|---|---|---|---|
  | contiguous (Mikhail, mk:870-872) | 679 (V = 1M, C = 23) | 0 % | 32 % | 93 % |
  | contiguous | 488 | 0 % | 51 % | 95 % |
  | contiguous | 82 (120k) | 19 % | 92 % | 99 % |
  | strided | any | 0 % | 0 % | 0 % |

- **Traffic effect.** Each such committee saves c × 200 B of unique subnet traffic per unit (κ copies on the wire). The aggregate topic is unchanged: one aggregate instead of up to 16 identical ones, which the superset rule already deduplicates.
- **Aggregate censorship.** In a mixed committee the operator holds most of the aggregators.
  - P(no honest aggregator | honest share h) = (1 − 16/c)^(hc) ≈ e^(−16h): 0.85 at h = 1 %, 0.45 at 5 %, 0.20 at 10 %, 0.018 at 25 %.
  - Contiguous layouts create such committees at every batch edge. The operator can then drop the minority's votes. That costs the minority rewards, and liveness too if the quorum is tight.
  - Late aggregators are drawn from the same committee, so they do not help.
- **Deanonymisation.** A committee whose votes never appear on its subnet, but whose full aggregate appears first from one peer, maps the whole committee to that node in one observation. The subnet fingerprinting of Heimbach, Vonlanthen et al. needs many epochs to do the same (`design/requirements.md:76-79`). Phase 1 accepts deanonymisation, but this mapping is exact and free.
- **Targeted DoS.** The schedule is public and deterministic, so the node hosting a whole committee can be flooded during its known 4 s unit. Contiguous composition concentrates an operator's stake into a few known windows; strided or era-shuffled composition spreads it over the round.
- **Verdict: good for traffic, bad for honest neighbours and for privacy.** Composition decides it, not position (H1b). Strided or era-shuffled composition removes single-operator committees without changing the schedule.

## 8. Flags for the STF draft and for Lane C

1. **The target root is not a block root.** `advance_height` hashes `latest_block_header` while its `state_root` is still zero (mk:926, :950-954). `process_block_header` zeroes that field (`specs/phase0/beacon-chain.md:1885`), and `process_slot` fills it in only at the next slot (`:1396-1399`). Gossip's "target known" lookup therefore needs a map from this header root to the block.
2. **`CommitteeBits[2048]` costs 256 B** in every gossip aggregate and every on-chain attestation (mk:245-251). That is 248 B more than Electra's 8 B, and raises the aggregate topic from 9.8 to 13.4 Mbit/s raw at 1M/C = 23 (S2e). Use per-unit indexing on gossip, or size the field C × 64.
3. **`COMMITTEES_PER_ROUND = 2048` is a constant** (mk:282); see §3.2.
4. **`is_valid_aggregation_bits` rejects bits of inactive validators** (mk:714-718). One vote from a validator that exits within the inclusion horizon poisons the whole aggregate. Either do not count such bits, as is already done for slashed validators (msg 1522; mk:479-482), or enforce activity through the horizon in gossip (§2.3).
5. **The finalized-anchored index set moves under in-flight aggregates** (mk:862-868).
   - Whenever the finalized epoch passes a validator's exit epoch, positions shift and committee boundaries move (mk:870-872). Aggregates built under the old set then fail `FastAggregateVerify` under the new one.
   - Exits take effect at epoch boundaries, up to 8 per epoch (§5.3). An epoch is 4 rounds (32 / 8 slots), so finality that advances about once per round crosses an epoch boundary about every 4 rounds. Each crossing that passes an exit epoch triggers the shift.
   - Pin the set by round (H2), or carry the anchor in the vote (msg 1639).
   - The window that gossip enforces must likewise depend on the round only. If it is anchored to the target, a voter near a set boundary can choose between two windows by choosing which target to vote for.
6. **`MAX_VALIDATORS_PER_AGGREGATE` = 2^17** (mk:283) fits exactly one 8-slot unit at V = 2^20, and three Q17 units at V ≈ 1.0M (§5.1).
7. **`MAX_ATTESTATIONS_ELECTRA` = 8 per block is reused** (mk:1164). Per-block merging is needed once fragmentation appears.
8. **Slashing evidence** (mk:105-106): see §5.4.
9. **The draft has no committee→unit map and no p2p section** (brief §3). §2 therefore assumes the `get_fg_duty` that Lanes A and C define.

## 9. Hypotheses (network side) and open issues

- **H1 — supported on the network side.**
  - The gossip conditions in §2 are state-free once the set is pinned by round and the duty map is pure.
  - Positional rotation with subnet = f(cohort identity) causes zero duty-subnet churn.
  - A per-round reshuffle costs 900 reassignments per validator per day, with at most 96 s of lookahead.
  - VRF duties cost +96 B and one more BLS verification per vote.
- **H1b — supported.** Composition matters for the network even though it does not matter for FG safety. Contiguous blocks create single-operator committees, aggregate censorship and instant deanonymisation (§7). Strided or era-shuffled composition fixes all three for one subnet reassignment per validator per era.
- **H3 — partly refuted on the network side.** Under contiguous composition the residual levers are not small: an exact node map for an operator's committees, e^(−16h) censorship of honest minorities, and DoS of a known node in a known 4 s window. Under strided or era-shuffled composition they are bounded, as H3 claims. FG safety itself is Lane A's question.
- **H4 — confirmed and quantified.**
  - Per offset, the landing-to-proposal margin is 8 / 4 / 12 s; the +4 unit is tighter than Gloas's own 6 s.
  - L by offset is 3 / 2 / 4, and the last units have L lower by 1.
  - Under Mikhail's previous-round rule the end-of-round gap can be removed with a 24th unit.
  - At the 4-slot stretch goal (C = 11), stale votes double to 24 % of the round.

**Open issues.**
1. κ and the IHAVE figures come from a model (eager push with go-libp2p defaults). They should be measured with Q17's experiments (README:152-154), the global-topic aggregates first.
2. The late-vote distribution needs measuring against W = 4 s: the roughly 20 % of mainnet that publishes late (`meetings/2026-09-22.md:52`), including DVT ceremonies.
3. The mainnet registry composition (R/V, and the number of never-eligible entries) is needed to cost §5.3's raw-index and Mikhail-set layouts.
4. The mainnet distribution of operator batch sizes is needed to turn §7 into a mainnet estimate.
5. PQ aggregate-proof sizes are needed for §5.1.
6. The 3-units-per-slot grid breaks under 10 s quick slots. The 2-units-per-slot variant gives L = 2 / 3 (S1); Lane A owns that schedule.
