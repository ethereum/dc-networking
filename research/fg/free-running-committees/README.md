---
title: Free-running FG committees — a committee every 4 s, rounds that slide across slots, seats you can pick
status: wip
date: 2026-10-06
provenance: agent
---

> **Provenance: agent.** Written 2026-10-06 by an agent from Yann's dictated ideas:
> - the free-running committee clock;
> - pick-your-seat;
> - the sticky-target concern from his 2026-10-05 discussion with Mikhail;
> - his sub-round design: 4 s vote + 4 s aggregation, an IHAVE/IWANT window at +8 s and a final aggregation at +10 s. Yann expects Sukun Tarachandani's devnet to implement it.
>
> Two simulation lanes run by agents produced the numbers: [`results/clock.md`](results/clock.md) and [`results/designs.md`](results/designs.md). A third agent red-teamed the text, and its 15 findings are folded in. Yann has not reviewed the text line by line.
>
> **Credits** (FF chat, by message id):
> - Francesco D'Amato: committees as load units (1472, 1485–1487) and `(index + round) mod C` (1491).
> - Mikhail Kalinin: the instant height switch (1532, 1535, 1541) and the end-of-round overlap concern (1539, 1542).
> - Anton Nashatyrev: the IHAVE share of FG traffic (1508, 1510, 1627), very late aggregators (1441), and the caveat that deferring IHAVE saves IWANT duplicates, not IHAVE volume (1630).
> - Builds on [Q17](../pipelined-units/README.md), [Q18](../staggered-committees/README.md), and the continuous-FG and prefix-consensus studies (`projects/ff/continuous-fg/`, `projects/ff/prefix-consensus/` in Yann's research vault, not in this repo).
>
> **Nonbinding.** It answers Q19 in [`open_questions.md`](../../open_questions.md) with a strawman, and does not modify `requirements.md`, Q17 or Q18.
>
> **Interactive version:** [`free-running-committees.html`](free-running-committees.html) (self-contained; open it locally). It has the figures referred to below.

# Free-running FG committees

## TL;DR

1. **The unit (sub-round design).** A committee starts every 4 s.
   - It votes for 4 s (push only), then aggregates for 4 s.
   - Once per slot, a 2 s IHAVE/IWANT window runs at +8 s, followed by a 2 s final aggregation at +10 s. The next proposer gets the best aggregate.
   - This needs Q18's vote windows to stay open until about +10.5 s.
2. **Francesco's `(index + round) mod C`**, on the DC draft's slot-aligned rounds, moves each cohort one unit later per round.
   - Gaps are 100 s.
   - Once per round, the cohort that wraps votes twice within 8 s. This is a one-cohort version of the overlap Mikhail wanted to avoid.
3. **Proposal: a free-running committee clock.** Committee = unit mod 23. A round is 23 units = 92 s ("eight slots minus one committee"), not tied to slots.
   - Every validator votes exactly every 92 s, and every block carries three committees.
   - In-slot positions rotate on their own (+0 → +8 → +4 s). No position function and no position seed is needed. Rotation is ε-fair in 13 min, provided the round boundary itself carries no penalty.
   - Composition still needs Q18's era hash, or capped seat choice.
   - Drawn on the slot grid, it is a rotation one unit *earlier* per 8 slots, with Q17's idle unit filled.
   - **The case is structural, not latency.** The latency gain is small and model-dependent: −8 s per height at p = 1 in the explicit-time model, none at 2/3.
   - **Cost:** +4.3 % FG traffic.
4. **Pick-your-seat.** On the free-running clock every seat has the same in-slot timing, so a seat only chooses *who you vote with*.
   - It is acceptable for load and liveness only with a stake cap **and** a count cap on every inflow.
   - Uncapped, an attacker can pack 8× a seat's load into one unit and burst 67 MB.
   - Even capped, seats drift over months towards whole seats held by one operator or an adversary. Choice trades the era re-draw's periodic reset for slowness.
5. **Extra: where targets come from.** With heights advancing at 2/3, *sticky* voters, who keep the old target for reward fairness, lock heights to rounds.
   - This costs **+50 s** of expected lag at p = 1 (174 → 224 s).
   - Near 2/3 it becomes a **cliff**: +111 s at p = 0.8, +220 s at p = 0.7.
   - Previous-target credit makes rewards fair without stickiness.
   - If round-aligned voting is required, pick the target at the round start. Prefix counting is faster (184 s), but its finalization is untested.
   - Rolling FFG is fastest and flat (168 s).

## 1. The unit: a committee every 4 s

**Terminology.** Here a **committee** is the group that votes in one unit; Q18 calls it a *cohort* or *seat*. On the wire each one splits into 64 subnet committees (Q18 §7).

Q17's unit stays: a committee votes for 4 s, then its aggregators publish and the aggregates spread for 4 s. A new unit starts every 4 s, so three committees start per 12 s slot, at +0, +4 and +8 s.

The sub-round design adds two things:
- **Push only inside the phases.** Votes and on-time aggregates travel by eager push, and FG topics emit no IHAVE gossip while a phase runs. Anton's simulations put ~99 % of GossipSub control traffic on IHAVEs for FG votes and aggregates: ≈ 30 % of a home node's traffic with 100 peers, and up to 250 Mbit/s of IHAVEs on a supernode.
- **One repair window per slot.**
  - At **+8 s**, four seconds before the slot ends, nodes run a single **2 s IHAVE/IWANT round** for the FG messages of the three committees the next block will carry.
  - At **+10 s** a few late aggregators publish the best aggregate they now hold, a superset of the on-time one. It reaches the next proposer by +12 s.
  - This is Q18's late aggregator and Anton's very-late aggregators, moved onto a fixed, slot-synchronous grid.

| phase | when | gossip |
|---|---|---|
| vote | unit start → +4 s | push |
| on-time aggregation | +4 → +8 s after the unit start | push |
| IHAVE/IWANT repair | +8 → +10 s of every slot | pull, one round |
| final aggregation | +10 → +12 s of every slot | push (supersets), best effort |
| inclusion | the block at +12 s | — |

On the free-running clock of §3, the block at the end of every slot carries exactly **three committees**, the ones that started at −4, +0 and +4 s. A vote cast at t lands in the first block at or after t + 8 s.

**What the repair window changes elsewhere**
- **Vote windows.** Under Q18's rules, the −4 s and +0 s committees' votes are already IGNOREd at +8 s, because the soft end is the unit start + 8.5 s. The repair window therefore extends the soft end to ≈ +10.5 s.
  - Four windows are then open at +8…+10 s, instead of three.
  - Q18's burst bound grows from 3β to **4β units**: 11.6 MB instead of 8.7 MB at β = ⅓ and 10⁶ validators. §4 has the seat-choice version.
- **Gossip.** "No IHAVE during the phases" needs per-topic IHAVE scheduling in the clients, a GossipSub change outside Q17's "only the round architecture is tuned".
  - Anton's caveat applies: deferring IHAVE mostly saves duplicate IWANTs, not IHAVE volume.
  - The IHAVE saving needs batching, or not advertising what push already delivered (IDONTWANT, partial messages).
- **Best effort.** The 2 s final hop is shorter than Q17's 4 s propagation budget (P1), so it is a best-effort improvement. The on-time aggregate stays the guaranteed path.

## 2. Francesco's rotation, on the slot grid

Francesco's point was that committees are a load unit, not a security unit. They therefore need no shuffle, only a fair deterministic map from (round, index) to committee. His simplest version is "index + round % number of committees", with the index taken in the active set.

On the DC draft's slot-aligned 8-slot rounds, with Q17's grid (23 units, the 24th idle), the formula moves every cohort **one unit later per round**:
- Most cohorts wait **100 s** between votes.
- Once per round, the cohort that wraps from the last seat to the first votes again **8 s** later. This is a one-cohort (1/23 of stake) version of the overlap Mikhail wanted to avoid; his example was the last quarter of a round voting again at the next round's start.
- Wall-clock numbers [sim, [`results/clock.md`](results/clock.md) X1–X2]:
  - 80 / 92 / 96 / 108 s per height at p = 1 / 0.9 / 0.8 / 0.67 (explicit-time model);
  - in-slot ε-fairness after 0.38 h.
- Q18 measured it at 0.727 rounds/height, against 0.696 for a fixed order (unit model). It recommended two changes:
  - the raw validator index instead of the active-set rank, which still applies;
  - a step every 8 rounds instead of every round, which the proposal below replaces unless the round boundary carries a penalty.

## 3. The proposal: let the clock run free

Keep the 4 s grid, but stop forcing rounds to start on a slot boundary. Number units from genesis, u = ⌊t / 4 s⌋, and let committee k = u mod 23 vote in unit u. A round is then just **23 consecutive units: 92 s, eight slots minus one committee**. The unit Q17 leaves idle becomes the first committee of the next round.

```python
C = 23                                   # committees (Q18 cohorts); coprime with UNITS_PER_SLOT = 3
def active_committee(u): return u % C    # the only duty function
def round_of(u):         return u // C   # accounting: rewards, the vote's round field, bit layout, inclusion window
def unit_start(u):       return GENESIS + 4 * u   # slot u // 3, in-slot offset 4 * (u % 3) s
def round_start(r):      return unit_start(C * r) # +0 / +8 / +4 s into its slot for r = 0 / 1 / 2 (mod 3)
# seat(v) in [0, C): Q18 era hash (default), the stripe v % C, or chosen (section 4)
def votes_in(v, u):      return u % C == seat(v)
```

What follows:
- **Every validator votes exactly every 92 s**, unless its seat changes (an era re-draw or a seat request).
  - The gap is always C units, the optimum in Q18's gap lemma.
  - No cohort waits C + 1 or 2C − 1 units, and none votes twice in a row, so the end-of-round overlap is gone by construction.
- **In-slot rotation is free.**
  - 23 is not a multiple of 3, so a committee's in-slot offset steps +0 → +8 → +4 s, one step per round, and repeats every 3 rounds (276 s).
  - In-slot effects even out within 0.21 h, against 3.0 h for Q18's rotation [sim].
  - **Caveat 1, round position:** this covers in-slot effects only. If the round boundary itself carried a penalty (a round-start freeze, a first-unit miss rate), the free-running clock would never even it out: 0.93 pp for one cohort under Q18's assumed rates. Q18's slow rotation on top (3.3 h) would then be the fix.
  - **Caveat 2, composition:** who shares a cohort is a separate axis, and it still needs Q18's era hash or capped seat choice (§4).
- **Every block carries three committees.** Q17's 2-vs-3 unevenness ("Problem 1": 12.5 % of blocks carry two) disappears.
- **The round boundary drifts 4 s earlier per 96 s of slot time.** Two rounds out of three start mid-slot. The round stays as accounting, and nothing has to happen when a round starts.
- **Cost:** no idle unit, so FG traffic per second rises by 24/23 (+4.3 %) at the same per-unit load. Q17's once-per-round 4 s breather is gone.

**Schedules on the wall clock** [sim, [`results/clock.md`](results/clock.md)]. Seconds per height use the explicit-time model: a vote cast at t lands in the block at 12·⌈(t+8)/12⌉ s, the quorum block is visible 1 s after its slot start, and offline sets are random as in Q18. The constant-lag model (X2b) also puts the free-running clock first, but orders the others differently.

| schedule | vote gap | blocks with 2 committees | in-slot ε-fair after | s/height p = 1 | 0.9 | 0.8 | 0.67 |
|---|---|---|---|---|---|---|---|
| a · Q17 grid, fixed order | 96 s | 12.5 % | never (0.80 pp) | 80 | 84 | 96 | 108 |
| b · Q17 + Francesco (+1/round) | 8–100 s | 12.5 % | 0.38 h | 80 | 92 | 96 | 108 |
| c · Q17 + Q18 (+1 per 8 rounds) | 8–100 s | 12.5 % | 3.0 h | 80 | 85 | 96 | 108 |
| **d · free-running clock** | **92 s** | **0** | **0.21 h** | **72** | **84** | **92** | **108** |
| e · free-running + (index + round) | 4–96 s | 0 | 4.9 h | 81 | 84 | 96 | 108 |

**Do not sell this on latency.**
- **At the 2/3 threshold every schedule takes 108 s.** A height ends with the block carrying its last needed committee, at 12·⌈(G+2)/3⌉ s, which is 108 s for G = 23, 24 and 25 [derived].
- **The −8 s at p = 1 depends on the model.** It disappears if the +0 s committee can see its slot's block before signing: both clocks then take 72 s, and 96 s at the threshold. A free-running clock with C = 24, which adds no traffic, also reaches 72 s at p = 1.
- **The −4 s at p = 0.8 comes from the random offline sets.** With offline stake spread evenly, both clocks give 96 s (`sim/check_frc.py`).
- **The robust wins are structural:** a constant gap, no double vote, identical blocks, and in-slot rotation for free.
- **New minor cost:** 8.7 % of blocks carry votes of two rounds, which cannot share one aggregate.

**Is this what Francesco meant?** Not as written. The chat does not record who first suggested letting rounds drift, and Francesco's formula on the DC draft's slot-aligned rounds is the forward rotation of §2. The precise relation:
- **On the slot-aligned grid** the free-running clock is also a rotation. Position j of 96 s window R holds cohort (j + R) mod 23: every cohort moves one unit **earlier** per 96 s, and all 24 positions are used.
- **Why Q18's objection does not apply.** Q18 rejected the backward direction (2.0 rounds/height near 2/3) because inside fixed 23-unit rounds the wrapping cohort waits 2C − 1 units. Filling the idle unit removes the wrap: that cohort votes as the next round's first committee.
- **In short:** Francesco's formula rotates the cohorts through the round. The free-running clock keeps the order fixed and rotates the round through the slots.
- **Combining them hurts** (row e). Adding `(index + round)` on top stretches the gap to C + 1, brings back a double vote 4 s apart, and slows in-slot fairness to 4.9 h, because 24 ≡ 0 (mod 3). If round-position penalties exist, add Q18's slow rotation instead (3.3 h).

**Spec changes**
- **Rounds.**
  - Define `compute_round_at_unit`, `compute_round_at_slot` (the round of the slot's first unit), and the round's start slot and offset.
  - The vote keeps `round`, because seat, bit layout and inclusion window are functions of it (Q18 §10).
- **Inclusion.** "Current or previous round" now counts in units. The block of slot s carries units 3s−4 … 3s−2, which can straddle a round boundary.
- **Epochs and eras.**
  - An epoch holds 96/23 ≈ 4.17 rounds, and 22.9 % of rounds straddle an epoch. `Active(epoch(round))` uses the epoch of the round's first unit.
  - If the era hash stays, eras must snap to rounds: 256 epochs = 1,068.5 rounds, so use 1,056 rounds (253 epochs) to keep Q18's invariant (era ≤ 256 epochs).
- **C coprime with the units per slot.** gcd(C, 3) = 1, so C ∈ {22, 23, 25, 26, …}. With 10 s quick slots and 2 units per slot, C must be odd. C = 24 freezes every committee's in-slot offset.
- **Round position must stay neutral.** Two asymmetries remain:
  - the inclusion window gives the last seat 88 s and the first seat 176 s, both ample;
  - a design that picks targets at round starts (§5) picks "the head at the round's first unit", mid-slot two rounds out of three.

  Any round-start freeze would bring back a first-unit penalty that the free-running clock cannot even out.

## 4. Pick your seat

Once the active committee index alone decides when a seat votes, a seat (a Q18 cohort; 64 subnet committees on the wire) can be any public number in [0, 23).

- **Default seat:** Q18's era hash, or the seed-free stripe v mod 23.
- **Choice:**
  - an `fg_seat` field, set by an EL-triggered request (like EIP-7002 and EIP-7251 requests);
  - churn-limited, and effective at an era boundary, or at any round boundary at least 5 epochs ahead.
- **Caps:**
  - A request is refused or queued if it would push a seat above κ · S/23 of stake (κ ≈ 1.05), **or** above a validator-count cap.
  - A stake cap alone bounds message load only for similar validator sizes: 32 ETH validators carry 64× the messages of the same stake in 2048 ETH ones.
- **Subnets within a seat:** must be specified too, as a stripe of the index (no seed) or Q18's era hash (keeps the seed).
  - An operator gets local aggregation only if it fills a whole seat (≈ 4.3 % of stake) or also chooses its subnets.

Under the free-running clock no seat is better for **in-slot timing**: every seat has the same 92 s gap and passes through all offsets every 3 rounds. A choice is about **who you vote with** (Yann's "Binance committee" question, msg 1497).

Relative-order effects remain: at p = 0.8, two thirds of one cohort's votes can go stale. Previous-target credit has to neutralise that.

**What can go wrong, and why the caps must cover every inflow** [sim, [`results/clock.md`](results/clock.md) §7, at 10⁶ validators]. Seat composition is not an FG security unit (Q18 §8), so these are load, liveness and partial-tally effects. Capped figures use κ = 1.1, which is conservative against the proposed 1.05.

- **Load.** Without caps:
  - operators co-locating put 2.2–4.2× a seat's normal load into one unit;
  - a herd or an attacker puts 7.6–8.3×, up to 72.5 MB in one 4 s unit;
  - heights at p = 1 slow from 72 s to 79–92 s.

  A stake cap plus a count cap keeps every seat near κ.
- **Bursts.** With hashed seats, Q18's windows cap a withheld-then-released burst at 3β units (8.7 MB at β = ⅓), or 4β (11.6 MB) once §1's repair window extends the soft end.
  - Whole consecutive seats allow min(βC, 3κ) units: **26–29 MB**. With the repair window, min(βC, 4κ): **35–38 MB**.
  - Uncapped: βC = 7.67 units (66.7 MB), as if there were no windows.
  - If honest validators already fill the seats, the cap leaves ≈ 1.3 units.
- **Honest minorities.**
  - Uncapped, at β = ⅓ an attacker can dilute a seat so that 27 % of its committees have no honest aggregator. With the cap this is ≤ 5.5·10⁻⁵.
  - A seat filled 100 % by one operator harms nobody, but deanonymises that operator.
  - A seat filled 95 % by one operator leaves 45 % of its committees without an aggregator from the 5 % minority.
- **Partial tallies.** The adversary's largest share of any 4 consecutive units at β = ⅓ is:
  - 33.6 % with default striped seats;
  - 39 % with the cap;
  - 74 % uncapped;
  - 100 % with whole seats.

  This matters only to a gadget that reads partial tallies (an SG, a fast confirmation).
- **Capture speed.** Going from 10 % of stake to ⅓ of a seat takes:
  - 9.5 days uncapped (churn-limited);
  - 118 days (Electra churn) or 30 days (EIP-8061) with κ = 1.1;
  - 8.3 / 4.4 days under Q18's fixed striping.

  The capped figures assume honest validators never move, which is exactly what seat choice invites. Q18's era re-draw resets composition every 27 h instead.
- **Withholding is not worse.** Whole silent seats cost 92 s per height at β = ⅓, against 108 s when the stake is spread: the dead arc absorbs the post-switch lag.
- **Relative order.** The order of seats never changes, so in round-locked regimes the same cohorts cast the stale votes: up to 67 % of one cohort's votes at p = 0.8. A rotation cannot spread this on the free-running clock. Previous-target credit (`mk:124-134`) keeps it reward-neutral.

**The trade against Q18's era hash.** A striped default with capped choice needs no seed, no era-boundary delay and no era invariant. It loses the periodic reset: composition becomes slow to capture instead of being re-drawn. Choice is also strictly more power than grinding ever gave.

**Needs:**
- a 1-byte seat field (1 MB at 10⁶ validators);
- per-seat stake and count totals;
- a ~69-byte EIP-7685 request;
- both caps on every inflow, including consolidation targets and top-ups;
- a subnet rule.

It is compatible with `Active(epoch(round))` if a change takes effect at epoch ≥ c + 5 and on a round boundary. A state-held seat can differ across forks: that is fine for the height FG, but not for a continuous FG whose slashing reads a validator's tick.

> **Verdict.** Pick-your-seat is acceptable **for load and liveness** with a stake cap and a count cap on every inflow; FG safety is not the question. Even capped, seats drift over months towards whole seats held by one operator or an adversary. Keep Q18's era hash as the default, and revisit seat choice before any SG or fast-confirmation rule reads partial tallies.

## 5. Extra: where targets come from, and what it costs

**The question** (Yann, from a discussion with Mikhail on 2026-10-05). Suppose a height advances once 2/3 have voted, with no prefix consensus or Rolling FFG.
- The next height's target is fixed at that instant: the block that completed the quorum, the height's *entry*.
- Yann's team favours keeping the old target for the rest of the round, for reward fairness. Then the entry is first voted in the next round.
- By then it is already old (a third of a round in the ideal model), and latency grows.

The five designs run on the free-running clock with §1's timing. They differ only in where the target comes from and when voters switch.

| design | target of the next checkpoint | voters switch |
|---|---|---|
| floating heights, instant switch (Mikhail) | block completing the 2/3 quorum (entry) | at once; previous-target votes keep credit |
| floating heights, sticky voters | the same entry | at their next round |
| round-aligned target (control) | head at the round start | at round starts |
| prefix counting, sticky voters | none fixed: votes name their head; the round justifies the deepest block 2/3 of its votes extend | at round starts |
| Rolling FFG | every unit is a checkpoint (δ-deep block) | — |

**Expected lag, block birth → finalized** [sim, [`results/designs.md`](results/designs.md); head-sourced voters, honest runs; difference to the instant switch in brackets]:

| design | p = 1 | 0.9 | 0.8 | 0.7 | ideal (rounds) |
|---|---|---|---|---|---|
| instant switch | 174 s (1.89 rounds) | 204 | 234 | 234 | 5/3 |
| **sticky voters** | **224 [+50]** | 224 [+20] | **345 [+111]** | **454 [+220]** | 5/2 |
| round-aligned target | 212 [+38] | 220 [+16] | 232 [−2] | 324 [+90] | 13/6 |
| prefix, sticky voters | 184 [+10] | 201 [−3] | 225 [−9] | 324 [+90] | 11/6 |
| Rolling FFG δ = 1 (δ = 0) | 168 (156) | 192 (180) | 204 (192) | 216 (204) | 4/3 |

DC today in the ideal model is 5/2 rounds: 230 s at 92 s rounds, or 240 s at DC's 96 s rounds. That is a closed form, not comparable to the simulated rows.

Decomposition at p = 1 (to inclusion + inclusion → justified + justified → finalized):
- instant switch: 30 + 72 + 72 s;
- sticky voters: 40 + 92 + 92 s;
- round-aligned target: 48 + 72 + 92 s;
- prefix, sticky voters: 4 + 91 + 89 s;
- Rolling FFG: 24 + 72 + 72 s.

1. **Sticky voters give back what floating heights buy.**
   - Heights lock to one per round: 174 → 224 s at p = 1.
   - In the ideal model this is 5/3 → 5/2 rounds, exactly DC today's terms.
   - Stale votes rise from 11 % to 26 % of honest votes.
2. **Near 2/3 it is a cliff.**
   - Once the quorum block lands after the next round's first unit, that round re-votes a closed height: +111 s at p = 0.8, +220 s at 0.7.
   - Confirmed-block voters see the quorum ~17 s later and fall off already at p = 1 (283 s).
   - 20 % sticky stake suffices to lock heights to rounds at p = 1.
3. **"Picked deep" is mild at full participation and real near 2/3.**
   - The entry is 20 s old at its first sticky vote at p = 1, because the 8 s aggregation already puts the quorum 68–76 s into the round. It is 48 s old at p = 0.8 and 88 s at 0.7.
   - Even at p = 1 the cost is the full round between pick and justification (92 s instead of 72 s), paid again before finality.
   - Target age at pick / first vote / justification / finalization (s):
     - instant: 0 / 4 / 72 / 144;
     - sticky: 0 / 20 / 92 / 184;
     - round-aligned: 8 / 8 / 80 / 172;
     - prefix: 4 / 4 / 72 / 144;
     - Rolling FFG: 28 / 28 / 100 / 168.
4. **For round-aligned voting, pick the target at the round start, or count by prefix.**
   - Round-aligned targets avoid the cliff at 0.8 (232 s).
   - Prefix counting is within +10 s of the instant switch at p = 1 and slightly faster at 0.9–0.8. At p = 1 its justified block keeps deepening for 20 s after the first quorum (16 / 12 s at 0.9 / 0.8).
   - Both break at p = 0.7 with k = 1 finalization: 324 s mean, max 456 s, and they never finalize with confirmed-block sources.
   - A Gasper-style variant (source pinned at the round start, k ≤ 2) was simulated for the round-aligned target only. It gives 328 s mean (max 372 s; 344 s with confirmed-block sources) and costs +29 s at p = 0.8. For prefix counting it is untested.
5. **Rolling FFG is fastest at every p.** Its lag is flat and no vote is stale. Its ideal 20 % gain shrinks to 3–13 % because it pays the 8 s aggregation in both phases.

> **Recommendation.** Keep the instant switch and get reward fairness from previous-target credit (Q18 §3): stickiness is the most expensive way to make rewards fair. It is also the natural fit on the free-running clock, where nothing has to happen when a round starts. If round-aligned voting is still wanted, use the round-aligned target with Gasper-style k ≤ 2, which is simulated and has no cliff. Prefix counting is faster, but its round-aligned finalization breaks at p = 0.7, and its k ≤ 2 variant and its safety are untested.

**Not modelled:**
- AC forks and entry splits, timeouts and the R1–R3 races, and missed slots. See the prefix-consensus study for those worst cases; Rolling FFG is immune to R1–R3.
- Safety of the prefix design's k = 1 finalization: it is only a timing model.

## 6. Method, reproduction, open questions

- **Clock lane:** `python3 sim/clock.py all` (~6 s) → [`results/clock.md`](results/clock.md), `results/clock.json`.
  - It reuses Q18's simulator for the constant-lag model and reproduces Q18 exactly: 0.696 / 0.826 / 1.130 rounds/height.
  - It adds the explicit-time model of §1, with 40·C validators and Q18's random offline sets.
- **Design lane:** `python3 sim/designs.py all` (~70 s); `traces` writes `results/traces.json` → [`results/designs.md`](results/designs.md).
  - It copies the prefix-consensus simulator with 92 s rounds and three new engines.
  - It reproduces the prefix study byte for byte at C = 24.
  - Its ideal-model runs match the closed forms 5/3, 5/2, 13/6, 11/6 and 4/3.
- **Independent check:** `python3 sim/check_frc.py` (~1 min), with offline stake spread evenly.
  - It reproduces the gaps, the committees per block and the explicit-time seconds per height: 72 / 84 / 96 / 96 / 108 s at p = 1 / 0.9 / 0.8 / 0.7 / 0.67.
  - It agrees with the clock lane at p = 1, 0.9 and 0.67. At 0.8 / 0.7 the clock lane's random offline sets average shorter and longer heights (92 / 98.2 s).
- **Page:** `python3 build.py` → `free-running-committees.html`.

**Open questions**
1. **The +8 s pull window, measured on the devnet.** What share of votes is still missing at +8 s per offset? Does one 2 s IHAVE/IWANT round recover them? Does per-topic IHAVE scheduling actually cut IHAVE volume (Anton's msg 1630)?
2. **When can the +0 s committee sign?** Seeing its slot's block first moves the threshold from 108 to 96 s on both clocks, and erases the p = 1 gap between them.
3. **Rewards.** The instant switch with previous-target credit, or sticky voting (§5)?
4. **Pick-your-seat.** Whether to allow it before an SG or fast-confirmation rule exists, κ, the count cap, and its interaction with consolidations and top-ups.
5. **10 s quick slots.** Redraw the grid. With 2 units per slot, C must be odd.
6. **Rounds straddle epochs (22.9 %) and blocks (8.7 %).** Check reward accounting, the inclusion window and the per-block merge.
7. **Francesco's later messages.** The local FF-chat copy ends on 2026-10-02. If the rotation idea was refined after that, re-read.

## Files

- `README.md`: this note.
- `free-running-committees.html`: the interactive page, built by `python3 build.py` from `src/` and `results/*.json`.
- `sim/clock.py` → `results/clock.md`, `results/clock.json`: schedules and seat rules; imports [`../staggered-committees/sim/schedules.py`](../staggered-committees/sim/schedules.py).
- `sim/designs.py` → `results/designs.md`, `results/traces.json`: design latency on the free-running clock; extends the prefix-consensus simulator.
- `sim/check_frc.py`: the independent cross-check.
- `results/ideal.json`: ideal-model lags for Figure 7.
