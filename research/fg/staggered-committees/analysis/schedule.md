---
title: Staggered FG committees — Lane A: schedule, seat position, composition, adversary
status: wip
date: 2026-10-02
provenance: agent
---

> **Provenance: agent** — 2026-10-02, Lane A of a three-lane agent study (schedule, position, composition, reward proxy, adversary). Every number is printed by [`../sim/schedules.py`](../sim/schedules.py) (stdlib, deterministic, ~1 min); tags E1a–E13 name its tables. Not yet reviewed line by line. FF-team chat messages are cited by id (`msg NNNN`); Yann cleared using the chat in this public write-up (2026-10-02). "The brief" is the shared lane setup summarised in [README Appendix A](../README.md#appendix-a-study-setup).
>
> **Superseded by the [README](../README.md) where they differ** (red-team pass, 2026-10-02):
> - **Composition:** the README uses the **era hash of the validator index**, not the striped shuffle of §8. The hash covers mid-era activations and needs no list (README §4). The shuffle remains the exact-balance alternative.
> - **Gap lemma (§3):** the bounds assume an honest includer. README §8 gives the adversarial bound L_max + 3k + G (+ G per split) and the progress-vote rule. The schedule ranking is unchanged.
> - **New deposits (§7.1):** "useless under an era shuffle" holds only through the shared 256 ETH/epoch `pending_deposits` cap, because placeholder deposits can be aimed at a cohort once the seed is known. The ≤ +4.2 pp bound stands.
> - **Grinding (E12b):** the k = 8 row is a stress case (probability β^8 per era).
> - **Subnets (§8):** "aligned with `EPOCHS_PER_SUBNET_SUBSCRIPTION`" means the same period only. The backbone rotation is staggered per node, while the era flips for everyone at once (README §4).

# Staggered FG committees — who votes when, and with whom (Lane A)

## TL;DR

- **Position: keep the order fixed and rotate it slowly *forward*.** Fixed order is latency-optimal. Moving every cohort one unit *later* every 8 rounds costs 0.4% at full participation: 0.699 vs 0.696 rounds/height at C=23, L=0 (E1a). Its worst case is one unit more (1.17 vs 1.13 rounds after a drop to 67%, L=3, E2a). Moving *earlier* by a whole unit (the −1 direction, or Mikhail's slide at s = n/C) makes the wrapping cohort wait 2C−1 units, which gives 2.00 rounds/height at 67% participation (E1a). Reshuffles cost 2.6–13% at full participation with L=0, up to 19% at L=3, and up to ~2 rounds near the threshold (E1a, E2a). That covers the per-epoch reshuffle of the fradamt status quo, per-round reshuffles and a VRF.
- **Gap lemma.** Assume ≥ 2/3 honest stake is online and on one branch. Then a height that starts at tick t is justified by t + L + G, where G is the largest gap between a validator's consecutive vote opportunities. G is C for fixed order, C+1 for the forward rotation, and 2C−1 for the −1 rotation and for every reshuffle (§3). E4 checks the bound for 18 schedules; it holds in every case and is attained, or missed by one tick.
- **Safety-neutral.** Neither `has_quorum` nor the slashing predicate reads the schedule, so every schedule is equally safe (§4). The schedule only moves liveness (through G), incentives and griefing. It stops being neutral once a gadget counts per-unit tallies; the SG is still a TODO.
- **Composition is a separate axis from position.** A rotation never changes who shares a cohort.
  - Mikhail's contiguous blocks keep deposit batches together. At 10⁶ validators the largest operator holds 18.4% of one unit against 9.4% overall, 6.5% of committees are single-operator, and the clustering persists for ~31 days (E8b–d).
  - Striping by raw index, or by a seeded shuffle, matches the global share and leaves 0% single-operator committees.
  - Striping by *active-set position* is a trap: every exit re-seats everyone behind it. At 2 exits/round this gives 1.99 rounds/height at 67% participation (E9b).
- **Seat effects are real but small, and an hours-long rotation fixes the absolute ones.**
  - With *assumed* per-offset miss rates of 0.5–3%, the worst fixed seat is 1.74 pp below average. That is 1.09% of CL reward, and it never averages out (E10b).
  - Mikhail's slide keeps a validator's seat for 48 days at 10⁶, so it reaches ε-fairness only after 3.6 years. The forward rotation every 8 rounds reaches ε-fairness (0.1 pp) after 5.8 h.
  - Proposer-lottery noise is far larger up to a week: 59% of reward at 1 week for a 32-ETH validator (E10c).
  - Relative-order effects are not fixed by rotation. For example, in round-locked regimes the same validators cast stale votes every round (E7). Mikhail's spec neutralises this by crediting previous-target votes.
- **Adversary.** Public deterministic cohorts give no FG-safety lever.
  - Under any fixed composition, a 10% adversary can own ⅓ of a C=23 cohort within 8.3 days (Electra churn) or 4.4 days (EIP-8061) by choosing consolidation targets (E12a).
  - A seeded 256-epoch era shuffle removes that lever: the gain is at most +4.2 pp per era via top-ups. Grinding 8 seed bits moves a 5% adversary's best cohort share from 6.45% to 7.70% when it runs 2048-ETH validators (E12b).
  - A secret VRF is worse on every FG axis.
- **Recommendation:** seat(v, r) = (c_e(v) + ⌊r/8⌋) mod C.
  - c_e(v) is v's rank in a seeded shuffle of era e's index list, taken mod C. An era is 256 epochs (1024 rounds ≈ 27 h). The seed and the list come from Lane C's anchor.
  - Committees are chunks of the shuffled cohort, and subnets stay fixed for the whole era.
  - Result: 0.699, 0.829 and 1.136 rounds/height at (p=1, L=0), (p=1, L=3) and (p=.67, L=3). It is ε-fair after 5.8 h. Each era boundary costs one 0.48-round delay, i.e. 0.047% (E13).
  - Seed-free fallback: c(v) = validator index mod C, with striped committees.

## Verdicts

| | Verdict | Key numbers |
|---|---|---|
| **H1** (state-free, slow + rotation, reshuffles/VRF worse, no safety gain) | **Confirmed, with a direction rule.** The rotation rate K barely matters for latency. The direction matters a lot: only steps to later seats keep G ≤ C+1. | slow +1/8r: 0.699 / 0.829 / 1.136 vs fixed 0.696 / 0.826 / 1.130 (E1a). Epoch reshuffle 0.714 / 0.842 / 1.332; round reshuffle 0.789 / 0.984 / 1.886; VRF 0.787 / 0.980 / 1.892 (same three columns: p=1 L=0, p=1 L=3, p=.67 L=3). −1 rotation: 2.000 at p=.67, L ≥ 1. Safety: §4. |
| **H1b** (composition ≠ position; contiguous blocks cluster; era-shuffle + slow rotation) | **Confirmed.** An era boundary costs a single sub-round delay, once. | Top-operator unit share: mk contiguous 18.4% (1M) / 31.2% (120k), stripe 9.5%, shuffle 9.6%, global 9.4–9.5% (E8b). Single-operator committees: 6.5% vs 0% (E8c). Era boundary: +0.04 rounds at p=1, one 0.48-round delay at p=.67 (L=3); ≤ 0.05% per era (E11). |
| **H3** (no FG-safety lever; residual levers bounded; secret VRF not preferable) | **Confirmed, but "comparable to random cohorts" holds only if composition is re-randomised.** Under fixed composition an adversary builds a large cohort share within days, and honest operators already cluster under contiguous blocks. | ⅓ of a C=23 cohort in 8.3 d (Electra) / 4.4 d (EIP-8061); ⅔ in 40 / 21.5 d (E12a). Under an era shuffle: ≤ +4.2 pp per era; grinding 8 bits adds ≤ 1.3 pp (5%) or 2.1 pp (20%) (E12b). |
| **H4** (seat effects real but small; hours of rotation fix them) | **Partly confirmed.** Absolute-seat effects (offset, unit 0, spill-over) are real, small and fixed by the rotation within ~6 h. Relative-order effects (stale votes, pivotality) concentrate in round-locked regimes and are *not* fixed by rotation; reward design must neutralise them, and Mikhail's spec does. | Fixed worst seat −1.74 pp of FG reward forever. mk slide: ε-fair after 3.6 y. Slow +1/8r: 5.8 h (E10b). Stale share 15.7–15.9% for every validator at p=1, but 0–100% under fixed order at p=.8, L=3, and still 37% max after 3 rotation cycles (E7). |

## 1. Model and schedule families

**Model.** The brief's model (§4) is kept: one vote per validator per round, cast at its seat, for the latest height it knows, if it has not voted for that height yet. Votes are 2/3 stake-weighted, and the new height starts immediately ([mk-dc-beacon-chain.md:114-117, 471-486, 970-988](https://github.com/mkalinin/eth2.0-specs/blob/dc-feature/specs/_features/decoupled-consensus/beacon-chain.md); line numbers refer to the copy fetched on 2026-10-02). L is the number of ticks between a justification and the first voters who see it.

- **Unit model** (default, T = C ticks per round): reproduces the brief's planning table, exactly for fixed order and +1/round and within 0.014 for the reshuffles (different seeds). Fixed order gives 0.696 / 0.826 / 0.913 at L = 0/3/5; per-epoch reshuffle 0.714 / 0.842 / 0.934; per-round reshuffle 0.789 / 0.984 / 1.000 (E1a).
- **Q17 tick model** (E1c): 4 s ticks, with idle ticks where the [pipelined-units grid](../../pipelined-units/README.md) starts no unit (:24, 57-62, 146). The results move by ≤ 0.008 rounds/height.
- **L is a parameter here.** Lane B owns its realistic range; the synthesis should read E1a at that range. Under Q17's inclusion timing (README:64), L depends on the offset of the pivotal unit.

**Families** (n validators at list positions 0..n−1; "state-free" means a pure function of the index list, the round and possibly an old seed):

| Family | Seat of v in round r | State-free | Composition changes? |
|---|---|---|---|
| fixed stripe | v mod C | yes | never |
| ±1 / round | (v ± r) mod C | yes | never |
| slow +1 every K | (v + ⌊r/K⌋) mod C, K ∈ {5, 8, 10, 30, 100} | yes | never |
| slow +1 / K, staggered | 1/K of each cohort moves per round | yes | sub-cohorts recombine |
| mk slide, s ∈ {1, n/C} | contiguous block of (j − s·r) mod n ([mk :853-873](https://github.com/mkalinin/eth2.0-specs/blob/dc-feature/specs/_features/decoupled-consensus/beacon-chain.md)) | yes (finalized-epoch list) | ~never (one validator per boundary per round) |
| per-epoch reshuffle | fresh seeded balanced partition every 4 rounds (fradamt `simplex/beacon-chain.md:1186-1207`, `validator.md:222-226`) | needs the epoch seed | every epoch |
| per-round reshuffle / VRF lottery | fresh partition / independent uniform seat every round | seed / secret | every round |
| era + slow +1 | (c_e(v) + ⌊r/K⌋) mod C, c_e = striped seeded shuffle per era | yes, given the era table | every era |
| Vorbit spiral, s ∈ {1, 2} | per-epoch reshuffle with new seat ≤ old seat + s ([20464:169-173](https://ethresear.ch/t/vorbit-ssf-with-circular-and-spiral-finality-validator-selection-and-distribution/20464)) | **no** (Markov in the previous seat) | every epoch |
| heavy-first (reference) | fixed order by effective balance (msg 1498) | **no** (reads balances) | never |
| tail-light (reference) | last unit at weight w, re-randomised per round (pattern note `fg-vote-dissemination.md:467-477`, local draft) | **no** | every round |

Mikhail's spec gives no committee→unit map ([mk :853-873](https://github.com/mkalinin/eth2.0-specs/blob/dc-feature/specs/_features/decoupled-consensus/beacon-chain.md) defines committees per round only). I assume committee k sits in unit ⌊k·C/2048⌋. Under that map his `indices[(i + round) % len]` moves the validator at list position j to *earlier* units as r grows, which is the direction of his "shift left by 1" (:151-153).

## 2. Latency (RQ1)

C = 23, unit model; mean rounds/height with p95 in parentheses (E1a), and the worst of the first three heights after a drop from 100% to 67% at a random phase, median / p95 / max over 60 trials (E2a):

| Schedule | p=1, L=0 | p=1, L=3 | p=.67, L=3 | drop→67%, L=0 | drop→67%, L=3 |
|---|---|---|---|---|---|
| fixed v mod C | 0.696 (0.70) | 0.826 (0.83) | 1.130 (1.13) | 1.00 / 1.00 / 1.00 | 1.13 / 1.13 / 1.13 |
| +1 / round | 0.727 (0.74) | 0.857 (0.87) | 1.167 (1.17) | 1.04 / 1.04 / 1.04 | 1.17 / 1.17 / 1.17 |
| −1 / round | 0.696 (0.70) | 0.826 (0.83) | **2.000** (2.00) | 1.48 / 1.87 / 1.91 | 2.00 / 2.00 / 2.09 |
| slow +1 / 8r | 0.699 (0.74) | 0.829 (0.87) | 1.136 (1.17) | 1.02 / 1.04 / 1.04 | 1.13 / 1.17 / 1.17 |
| slow +1 / 10r | 0.698 (0.70) | 0.829 (0.87) | 1.135 (1.17) | 1.00 / 1.04 / 1.04 | 1.13 / 1.17 / 1.17 |
| slow +1 / 10r, staggered | 0.696 (0.70) | 0.826 (0.83) | 1.142 (1.17) | 1.00 / 1.04 / 1.04 | 1.13 / 1.17 / 1.17 |
| slow −1 / 10r | 0.696 (0.70) | 0.826 (0.83) | 1.246 (2.09)ᵃ | 1.00 / 1.83 / 1.91 | 1.13 / 1.96 / 2.04 |
| mk slide s=1 | 0.696 (0.70) | 0.826 (0.83) | 1.130 (1.13) | 1.00 / 1.00 / 1.00 | 1.13 / 1.13 / 1.13 |
| mk slide s=n/C | 0.696 (0.70) | 0.826 (0.83) | **2.000** (2.00) | 1.48 / 1.87 / 1.91 | 2.00 / 2.00 / 2.09 |
| epoch reshuffle (4r) | 0.714 (0.83) | 0.842 (0.96) | 1.332 (1.74) | 1.46 / 1.83 / 1.87 | 1.39 / 1.83 / 1.96 |
| round reshuffle | 0.789 (0.87) | 0.984 (1.00) | 1.886 (2.04) | 1.43 / 1.78 / 1.87 | 1.96 / 2.04 / 2.09 |
| VRF lottery / round | 0.787 (0.91) | 0.980 (1.04) | 1.892 (2.04) | 1.39 / 1.66 / 1.83 | 2.00 / 2.04 / 2.04 |
| era(100r) + slow +1/10r | 0.699 (0.74) | 0.830 (0.87) | 1.136 (1.17) | 1.00 / 1.04 / 1.04 | 1.13 / 1.17 / 1.17 |
| spiral s=1 / epoch | 0.696 (0.70) | 0.826 (0.83) | 1.143 (1.17) | 1.04 / 1.04 / 1.04 | 1.17 / 1.17 / 1.17 |

ᵃ The mean is diluted because the slow −1 rotation hits 2-round heights (p95 2.09) only at its K = 10 boundaries.

Findings:

1. **Fixed order is optimal; forward rotation is nearly free.** The per-height cost is the quorum ⌈2C/3⌉ units plus L. A + step makes the cohort that ended round r start round r+1, so its vote is redundant for one unit. That is exactly the "low overlap" concern of [mk :138-140](https://github.com/mkalinin/eth2.0-specs/blob/dc-feature/specs/_features/decoupled-consensus/beacon-chain.md) (msgs 1539, 1542). It costs 0.031 rounds/height when paid every round, and 1/K of that when K > 1.
2. **Direction matters more than rate.** At a −1 step the cohort in seat 0 goes to seat C−1, so its gap is 2C−1 units. At 67% participation every online validator is needed, so heights take ~2 rounds whenever a whole cohort wraps. This applies to the −1 rotation and to mk with s = n/C. With s = 1 only 1/n of stake wraps per round. That is below any realistic slack, so mk's s=1 equals fixed order (E1d: identical at n = 23,000).
3. **Reshuffles cost at every participation level.** Redundant votes are the mechanism: under a per-round reshuffle 20–26% of a validator's votes repeat a height it already voted for (p=1, L=3; E7). Near the threshold, the boundary validators with gaps up to 2C−1 dominate. This confirms msg 1547's "almost two rounds" for reshuffles. msg 1553's "~1.5 rounds" lies between the fixed order (1.13) and reshuffles (≤ 2.09).
4. **Other C behave the same way** (E1b, E2b, E13). The +1 step costs more at small C: C=8 slow +1/8r gives 0.762 vs 0.750 at L=0, because the wrapping cohort is ⅛ of stake. Lags are in units of the schedule, so at C=8 (12 s units) L=3 means 36 s.
5. **Flapping** (E3: a fixed 33% set goes offline every other round, or for 4 rounds at a time). Fixed order, mk s=1 and slow rotation stay at 0.96 rounds/height mean, max 1.13–1.17. With 4-round flaps, the −1 rotation and the reshuffles reach max 2.00–2.09. The era run reaches 2.04 when a boundary coincides with a flap.
6. **Correlated outage** (E2c): one operator's contiguous index range going dark is no worse than a random outage under any schedule.

## 3. The gap lemma

**Lemma.** Fix a schedule σ. Let G(σ) be the maximum, over validators and rounds, of the tick distance between a validator's consecutive vote opportunities. Assume:

- (i) honest online validators hold ≥ 2/3 of total stake;
- (ii) they agree on the target of each height (one branch, i.e. after the AC has converged);
- (iii) each votes at every opportunity for the latest height it knows, unless it has already voted for it;
- (iv) a height justified at tick t is known to all of them from tick t+L+1.

If height h−1 is justified at tick t, then h is justified by tick t + L + G.

*Proof sketch.* From tick t+L+1, every honest online validator knows h. It knows a higher height only if h is already justified. The window [t+L+1, t+L+G] has G ticks, and consecutive opportunities are at most G apart, so every validator has an opportunity inside it. At that opportunity the validator either votes for h, or h is already justified. It cannot have voted for h earlier, because before t+L+1 it did not know h. So by the end of the window either h is justified or ≥ 2/3 of stake has voted for (h, target), which is a quorum (`has_quorum`, [mk :471-486](https://github.com/mkalinin/eth2.0-specs/blob/dc-feature/specs/_features/decoupled-consensus/beacon-chain.md)). ∎

**Refinement.** Suppose the honest online stake exceeds the quorum by δ·S. Replace G by G_δ, the smallest g ≥ C such that at every round boundary the validators whose gap exceeds g hold ≤ δ·S. Each vote opportunity falls in a distinct round, so a validator misses a window of g ≥ C ticks only if one of its gaps contains the window. All such gaps straddle the same round boundary, so the missing stake is ≤ δ·S and the argument goes through.

**G per family**, in units (unit model):

- **fixed:** C.
- **+1 every K:** C+1 at rotation boundaries (seat u → u+1), otherwise C. The wrapping cohort's gap of 1 does not matter for G.
- **−1 every K:** 2C−1 for the cohort that wraps from seat 0 to seat C−1, which is 1/C of stake.
- **mk slide by s:** 2C−1, carried by only s/n of stake per round. So G_δ = C for every δ ≥ s/n.
- **any reshuffle (epoch, round, VRF, era boundary):** C + u′ − u ∈ [1, 2C−1], so G = 2C−1. With independent uniform seats the stake with gap > 2C−1−x is ≈ x²/2C², so G_δ ≈ 2C − 1 − C√(2δ).
- **spiral(s):** C + s.

**The simulations match** (E4, C = 23, n = 920; the worst height is measured at exact-threshold participation, in steady state and after 40 random-phase drops):

| Schedule | G formula | G measured | worst height, L=0 (bound) | worst height, L=3 (bound) | at p=.67: worst vs L+G_δ (L=3) |
|---|---|---|---|---|---|
| fixed | C | 23 | 23 (23) | 26 (26) | 26 vs 26 |
| +1/round, slow +1/K (any K), staggered | C+1 | 24 | 23–24 (24) | 27 (27) | 27 vs 27 |
| −1/round, slow −1/10r | 2C−1 | 45 | 45 (45) | 47–48 (48) | 46–48 vs 48 |
| mk s=1 | 2C−1 on 1/n | 45 | 45 (45) | 48 (48) | **26 vs 26** (G_δ = 23) |
| epoch / round reshuffle, VRF | 2C−1 | 45 | 42–45 (45) | 48 (48) | 40–48 vs 48 |
| spiral s=1 / s=2 | C+1 / C+2 | 24 / 25 | 24 / 25 | 27 / 28 | 27 / 28 vs 27 / 28 |

The bound holds everywhere. At L=3 it is attained, or missed by one tick, for every family. In rounds, the worst height at threshold participation is (L+G)/C. At C=23, L=3 that is 1.13 (fixed), 1.17 (forward rotation) and 2.09 (−1 or reshuffle). mk's slide reaches 2C−1 only at exactly zero slack, where one wrapping validator per round matters. At 67% participation (3,300 validators of slack at 10⁶) it behaves like fixed order.

## 4. Safety neutrality for the height FG

**Proposition.** For the Simplex-style height FG of Mikhail's spec, safety (no two conflicting justified or finalized pairs unless ≥ 1/3 of stake is slashable) holds for every schedule, including adversarially chosen ones.

*Argument.*

1. Justification and finalization count `height_participation` flags with a full-active-set, live-balance quorum ([mk :471-486, 970-988](https://github.com/mkalinin/eth2.0-specs/blob/dc-feature/specs/_features/decoupled-consensus/beacon-chain.md)). `process_attestation` sets a flag for any attestation that passes three checks (:1188-1215):
   - `is_valid_attestation_data`: current or previous round, matching pairs (:650-695);
   - `is_valid_aggregation_bits` (:697-721);
   - the BLS check on the indexed attestation (:767-790).

   None of these reads the unit, the timing or the cohort composition.
2. The slashing predicate looks only at `finalize_pair` and `target_pair`, never at `round` or the committee (:493-520). Quorum intersection therefore yields ≥ 1/3 of stake with conflicting signed pairs, whoever sat where.
3. The only schedule-dependent STF step maps bits to validators (`get_beacon_committee(state, data.round, k)`, :853-873). A wrong mapping makes the aggregate signature fail. It cannot attribute a signature to a validator that did not sign. So the schedule enters only liveness (§3) and incentives (§5).

**Comparison with Rolling FFG.** In the user's continuous-FG model the schedule *does* enter the count rule: a vote counts for position q only at `nextTick v q`. Safety there needs `CountRule.MonotoneOn` (`projects/ff/continuous-fg/lean/RollingFFG/Model/Schedule.lean:94-99`), which is proved for every schedule (`Proof/Schedule.lean:48-55`). The height FG needs not even that, because its count rule, "a vote for (h, B) counts for (h, B)", has no time index.

**Where it is not neutral:**

- (a) Any gadget that reads *partial* tallies, such as an SG ([mk :104](https://github.com/mkalinin/eth2.0-specs/blob/dc-feature/specs/_features/decoupled-consensus/beacon-chain.md), still a TODO) or a fast-confirmation rule over the last k units. It turns cohorts back into a security unit, so composition matters (msg 1488; §7).
- (b) Rolling-FFG-style per-window accountability. Across a reshuffle a window can stretch to ~2 passes (continuous-fg `README.md:565-569`; the same 2C−1).
- (c) Index-set disagreement between branches. Bitfields then mean different sets, which is a liveness issue only; it is Lane C's anchor question.
- (d) Rewards and inactivity, which are attached to rounds (mk :124-134). They are incentives, not safety (§5).

## 5. Does the seat matter? (RQ2, H4)

**Reward proxy.** A vote is either:

- **timely:** it counts for the current height;
- **stale:** it is for a height that was justified within the lag;
- **redundant:** a re-vote of a height already voted for;
- **missed.**

Under Mikhail's spec, stale votes earn round participation as previous-target votes (mk :124-128, :1202-1214). Redundant re-votes of the same target are not slashable (:506-520), and height participation covers validators who already contributed (:130-134). So only *missed* votes cost reward as specified. The per-seat miss rates below are **assumptions**: Q17 frames them as an experiment (README:154), so only their spread matters.

| Seat class (C = 23) | Assumed miss rate | Rationale |
|---|---|---|
| +0 s units | 2.0% | the vote phase overlaps block/payload propagation (README:68, 89) |
| +4 s units | 1.0% | today's 4 s publication-to-proposal margin (README:64) |
| +8 s units | 0.5% | clean vote phase, 12 s margin (README:64) |
| unit 0 (extra) | +1.0% | votes before the round's first block has propagated (README:146) |
| last unit (extra) | +0.5% | lands at the round end and is included next round as a previous-round vote (README:57; mk :657-660) |
| idle [92, 96) s | n/a | no voters; latency effect ≤ 0.008 rounds/height (E1c) |

This gives a mean of 1.26% and a spread of 2.5 pp (E10a). The worst fixed seat (unit 0, 3.0%) sits 1.74 pp below the mean.

**Seat-induced deviation of a validator's FG vote-success rate.** The worst validator is shown for deterministic schedules and p99 for random ones. Parentheses give the share of total CL reward with W_FG = 40/64, an assumption that FG votes inherit today's source + target weights (`consensus-specs/specs/altair/beacon-chain.md:84-89`). Source: E10b.

| Schedule | 1 h | 1 day | 1 week | 1 year | ε-fair (≤ 0.1 pp from then on) |
|---|---|---|---|---|---|
| fixed v mod C | 1.74% (1.09%) | 1.74% | 1.74% | 1.74% | never |
| slow +1 / 8r | 0.43% (0.27%) | 0.021% | 0.003% | 0.000% | 217 rounds = 5.8 h (exact every 184 r = 4.9 h) |
| slow +1 / 10r | 0.69% | 0.022% | 0.003% | 0.000% | 272 r = 7.2 h |
| slow +1 / 100r | 1.74% | 0.24% | 0.039% | 0.001% | 72.5 h |
| mk slide s=1, n = 10⁶ | 1.74% | 1.74% | 1.74% | 0.23% | 31,506 h = 3.6 years |
| mk slide s=1, n = 1.2·10⁵ | 1.74% | 1.74% | 1.48% | 0.04% | 3,780 h = 158 days |
| epoch reshuffle [p99] | 0.60% | 0.12% | 0.046% | 0.006% | 35.2 h |
| round reshuffle / VRF [p99] | 0.30% | 0.061% | 0.023% | 0.003% | 8.8 h |
| era(1024r) + slow +1/10r [p99] | 0.66% | 0.033% | 0.011% | 0.002% | 7.2 h within an era |

**Against the proposer lottery.** E10c gives the relative std of total CL reward from proposing, with S = 36M ETH (EIP-8061:218) and W_prop = 8/64 (`altair/beacon-chain.md:88-89`). It counts the CL reward only; EL fees add more variance.

| Horizon | 32 ETH | 2048 ETH | fixed worst seat |
|---|---|---|---|
| 1 h | 771% | 96% | 1.09% |
| 1 day | 156% | 19.5% | 1.09% |
| 1 week | 59% | 7.4% | 1.09% |
| 1 year | 8.2% | **1.0%** | **1.09%** |

The seat bias is two orders of magnitude below lottery noise up to a week. Unlike the noise, it is systematic. For consolidated 2048-ETH validators a fixed seat costs slightly more than a year of proposer variance (1.09% vs 1.0%), which settles H4's fairness question in favour of rotating. Deterministic rotation is also fairer than random reshuffles at every horizon. The worst validator under slow +1/8r is fairer than the p99 validator under a per-epoch reshuffle (ε-fair after 5.8 h vs 35.2 h). A rotation repays exactly every K·C rounds, whereas a reshuffle averages out only as 1/√T. Randomisation is therefore not needed for *position* fairness (msg 1478's property 3); a slow deterministic rotation does it better.

**Relative-order effects (E7, per validator over 690 rounds ≈ 18.4 h, C=23):**

- *At full participation* every validator casts the same share of stale votes: 15.7–15.9% under fixed order at L=3. Votes in the pivotal unit are also uniform at 5.2–5.4%. A height takes ⌈2C/3⌉ + L = 19 units, which is coprime with 23, so the justification point visits every seat.
- *In round-locked regimes* a height takes exactly one round: E1a shows 1.000 at p=.8, L=3. The justification lands at the same point of the cohort sequence every round, so the *same validators* are stale (and pivotal) every time: 0–100% under fixed order. A rotation moves every cohort together, and the lock moves with them, so it does not help: the maximum is still 37.0% after three full cycles of slow +1/10r. Composition reshuffles average the effect only over eras: era(100r) gives 28.8% max after 7 eras, per-epoch 22.0%, per-round 16.5%.
- **Consequence:** the schedule cannot remove relative-order bias cheaply; the reward function must. Mikhail's spec already credits stale votes as previous-target votes (:124-128) and keeps height participation across rounds (:130-134). Keep that property when rewards are written (msg 1546 makes the same point).

**H4 seat effects, one by one:**

| Effect | Size | Fixed by |
|---|---|---|
| per-offset miss on the +0/+4/+8 s grid | spread 2.5 pp (assumed) → 1.74 pp worst seat | rotation in 5.8 h (K=8) |
| unit 0 | +1.0 pp assumed | rotation |
| votes spilling over the round end | +0.5 pp assumed; accepted next round (mk :657-660) | rotation |
| end-of-round 4 s gap | ≤ 0.008 rounds/height (E1c); no voters | n/a |
| stale-height votes under the instant switch | uniform at p=1; concentrated in round-locked regimes | reward design (credit previous target), not schedule |
| pivotality | same as stale | same |

## 6. Composition (H1b)

The synthetic registry (E8) is built as follows; **no mainnet registry snapshot exists locally** (the only beacon DB in the vault is a local Kurtosis devnet):

- 20,000 operators with Zipf(1) sizes (cf. [20464:31-53](https://ethresear.ch/t/vorbit-ssf-with-circular-and-spiral-finality-validator-selection-and-distribution/20464)). The largest is 9.5% of deposits.
- Contiguous deposit batches of 1 to min(1000, size/10) validators, interleaved in random order.
- 15% of batches exit whole, plus 5% individual exits.
- 1% pending entries at the end.

Three stake mixes:

- **equal:** 32 ETH each.
- **0x02-like:** a lognormal with median 238 ETH, clipped to [32, 2048], with σ = 1.994 calibrated to a mean of 603. This puts 15.7% at 32 ETH and 14.0% at 2048 ETH.
- **"1.5% hold ~50%":** the 2048-ETH validators drawn from operators with ≥ 1000 validators, i.e. big operators consolidate.

At n = 10⁶ active and C = 23:

| Composition | unit count min–max | top operator: one unit / 4-unit window (global) — equal stake | same, big-operator consolidation | committees ≥ 90% / 100% one operator | persists |
|---|---|---|---|---|---|
| stripe: validator index mod C | 0.998–1.002 | 9.5% / 9.4% (9.4%) | 15.5% / 14.3% (13.5%) | 0.0% / 0.0% | forever |
| stripe + striped committees | same | same | same | 0.0% / 0.0% | forever |
| stripe: active-set position mod C | 1.000–1.000 | 9.4% / 9.4% | 15.6% / 14.2% | 0.0% / 0.0% | until the next exit (below) |
| **mk contiguous blocks** | **0.780**–1.010 | **18.4%** / 12.5% | **25.8%** / 17.8% | **10.3% / 6.5%** | **28,386 rounds = 31.5 days** |
| seeded shuffle (era/epoch) | 0.999–1.001 | 9.6% / 9.5% | 15.0% / 14.0% | 0.0% / 0.0% | one era |

Sources: E8a–d. At n = 1.2·10⁵ (devnet scale), mk's contiguous blocks give 31.2% for the top operator, 20.9% fully single-operator committees, and persistence of 8.5 days.

- **Rotations never change composition.** E8 is evaluated at round 0, and every pure rotation leaves the table unchanged. `v mod C` keeps residue classes together forever, as H1b says.
- **Contiguous blocks cluster deposit batches**, as `deprecated/designs/design_a.md:57` warns. Note that its claim is wrong for `index mod C`, which spreads batches (E8b), and right for `index // size`.
- **The unit-count imbalance under mk** (0.780) comes from the pending activation queue at the end of the list: mk's list keeps every entry with `exit_epoch > finalized_epoch` (mk :862-868), and pending entries hold seats but cannot vote (:714-718).
- **Position-based striping breaks under exits** (E9b, n = 8192, C = 23, L = 3). Every list removal (an exit or a consolidation source) moves everyone behind it one unit earlier, and 1/C of them wrap to the end.
  - Striping by active-set position: 2 removals/round take p=.67 from 1.130 to 1.991 rounds/height. Electra at S = 36M has ~2 exit plus ~2 consolidation removals per round when queues are full (EIP-8061:218-221); EIP-8061 has ~8.6 + 4.3 (:231-235).
  - msg 1491's `(index_in_active_set + round) % C`, read with C *units*: 1.824 at 2 removals/round.
  - The same formula read with `% 2048` *committees* is a slow rotation (+1 unit every ~89 rounds): it stays at 1.130. But every removal changes the committee (and subnet) of everyone behind it.
  - Raw-index striping and mk's contiguous blocks are immune: 1.130–1.134.
- **Membership churn per round step at 10⁶** (E9a):
  - fixed: 0;
  - slow +1/K: all seats move every K rounds, committees and subnets 0;
  - mk s=1: 0.0023% of seats and 0.205% of committees per round, so a validator changes committee every ~13 h and unit every ~48 days;
  - per-epoch reshuffle: 100% every 4 rounds;
  - era: 100% once per era.

  Rotating only the time slot while keeping committees and subnets for an era matches the "long-lived backbone, rotate only the assignment" rule (`research/transitions/survey.md:414-420`) and `EPOCHS_PER_SUBNET_SUBSCRIPTION = 256` (`consensus-specs/specs/phase0/p2p-interface.md:229`).

**Era boundary cost** (E11, C=23, 60 paired trials): +0.04 rounds at p=1, L=3. At p=.67 there is one delay of 0.48 rounds, with the worst height near the boundary at 1.65 rounds. That is 0.047% of a 1024-round era. Vorbit's circular finality has the same structure: degradation only at era boundaries, average C + (C−1)/(2E_era) ([20464:153-167](https://ethresear.ch/t/vorbit-ssf-with-circular-and-spiral-finality-validator-selection-and-distribution/20464)). A spiral boundary (:169-173) would cap the boundary gap at C+s, but it is not a pure function of (index, round). At this cost it is not worth the state.

## 7. Adversary (RQ3, H3)

The adversary holds β < ⅓ of stake. It can time deposits, choose consolidation targets, withhold or release votes (including via its own proposals, since the STF has no unit check: mk :1188-1215), DoS nodes it has deanonymised, and grind k RANDAO bits.

**1. Concentration by choosing consolidation targets.** EIP-7251 keeps the target's index:

- the source exits (`electra/beacon-chain.md:1933-1938`);
- its balance moves to the target only once the source is withdrawable, i.e. exit + 256 epochs (:1068-1069, `phase0/beacon-chain.md:338`);
- the churn is shared: Electra C_cons = S/2¹⁶ − 256 = 293 ETH/epoch, EIP-8061 549 ETH/epoch at S = 36M (`electra/beacon-chain.md:608-633`; EIP-8061:218-235).

Under **any fixed composition** (striping, contiguous blocks, any pure rotation) the adversary picks targets inside one cohort. E12a gives the days for β = 10%, monopolising the churn (competition only slows it):

| C | target share of one cohort | minimum β | Electra | EIP-8061 |
|---|---|---|---|---|
| 23 | 25% | 1.4% | 4.7 d | 2.5 d |
| 23 | 33% | 2.1% | 8.3 d | 4.4 d |
| 23 | 50% | 4.2% | 19.0 d | 10.1 d |
| 23 | 67% | 8.0% | 40.4 d | 21.5 d |
| 8 | 33% | 5.9% | 23.9 d | 12.8 d |

Under a **seeded era shuffle with era ≤ 256 epochs** whose seed is revealed ≤ 5 epochs before the era starts, a consolidation aimed at an era lands after the era has ended. The remaining lever is top-ups through the deposit churn, which stays capped at 256 ETH/epoch (EIP-8061:234): at most +4.2 pp of a C=23 cohort per era (1.5 pp at C=8). Placing new deposits at chosen indices (msgs 1486, 1488) runs through the same 256 ETH/epoch, so under a fixed composition it is a slower route than consolidation, and under an era shuffle it is useless.

**2. What concentration buys:**

| Lever | Effect on the height FG | Bound / evidence |
|---|---|---|
| FG safety | none | §4 |
| plain withholding | the same delay wherever the stake sits | gap lemma; E6a "10% withholds" (fixed C=23: 0.800 vs 0.750 honest at L=1) |
| pivotal withholding to split views under asynchrony (msg 1529) | Each branch's target is its justifying block (`advance_height`, mk :950-954). Votes split between the two targets until the AC converges. This is liveness, not safety. Any adversary with stake above the slack can do it through its own proposal; concentration does not enlarge it. | after GST: ≤ L+G per height (§3) |
| timing games | Every justification already wastes the L units after it. With balanced units, release timing cannot waste more, and a release aimed at unit 0 was never better than plain withholding in any schedule tested (E6a). Offset-dependent lag (README:64) would let it pick the longest-lag offset: ≤ 1 unit per height. | E6a |
| "SG manipulation" over consecutive cohorts (msg 1488) | Undefined until the SG exists. The relevant number is the largest share over k consecutive units. | 4-unit window: mk 12.5–17.8% vs stripe/shuffle 9.4–14.3% at 10⁶ (E8b); a fixed composition can be pushed to the E12a numbers |
| targeted DoS of a predictable cohort | Equivalent to that stake being offline for a round. Below the threshold there is no effect; at the threshold, +1 round (gap lemma). Every public schedule exposes this, including today's RANDAO committees. Composition hardly changes the attack's duty cycle: a top operator's validators span 21 of 23 units under striping and 16–19 under mk at 10⁶ (E8b). | E8b |
| private aggregation by a single-operator committee (msg 1497) | Benign for the FG (its own votes, zero subnet traffic). The risk is mixed committees with a dominant operator: it likely holds every aggregator seat under the balance-weighted lottery (EIP-7251:626) and can drop the minority's votes (Q15 griefing). | mk: 10.3% of committees ≥ 90% one operator, 6.5% fully single-operator (10⁶); stripe-with-striped-committees and shuffle: 0% (E8c) |

**3. Is a secret VRF better? No.** It hurts on every FG axis:

- **latency** equals a per-round reshuffle: 0.787 / 0.980 / 1.892 vs fixed 0.696 / 0.826 / 1.130 (E1a);
- **no globally known assignment**, so no small bitvectors (msg 1478, property 1); this is Lane C's layout question;
- **per-vote eligibility proofs** in gossip (`design/explainer.md:41`);
- **cohort-size variance:** the largest cohort is +0.9% at 10⁶ and +9.2% at 10⁴ (E12c);
- **it lets a validator hide an earlier duty**, which breaks Rolling-FFG-style window accountability (continuous-fg `README.md:562-564`).

All it buys is hiding who votes when from a DoS attacker. The FG does not need that, because it needs no per-cohort liveness. Whether the AC needs it is a separate question (msg 1622; out of scope).

**4. Grinding the era seed** (E12b, C = 23). An adversary that controls k RANDAO bits picks the best of 2^k compositions:

| Adversary | k = 0 | k = 4 | k = 8 |
|---|---|---|---|
| 5%, 32-ETH validators | 5.18% | 5.28% | 5.35% |
| 5%, 2048-ETH validators | 6.45% | 7.15% | 7.70% |
| 20%, 2048-ETH validators | 22.35% | 23.53% | 24.48% |

This is bounded, and it buys nothing for FG safety. The seed must still be frozen ≥ 1 era ahead and predate the stake snapshot, i.e. stake before seed before duties (`research/transitions/survey.md:398-413`).

## 8. Recommended schedule

```
era        e(v, r)  = era of the anchor Lane C picks for the vote; one era = 256 epochs = 1024 rounds (~27.3 h)
list       I_e      = Lane C's index set for that anchor (frozen for the era)
seed       s_e      = seed from the same anchor, fixed >= 5 epochs before the era starts
cohort     c_e(v)   = rank_e(v) mod C,   rank_e = position of v in shuffle(I_e, s_e)  (compute_shuffled_index)
committee  k_e(v)   = j-th chunk of cohort c_e in shuffled order, 2048/C committees per cohort; subnet fixed per era
seat       seat(v,r) = (c_e(v) + floor(r / 8)) mod C          # forward rotation: one unit LATER every 8 rounds
gossip     a round-r vote is valid only in seat(v, r)'s window (Lane B's timing rule)
```

- **Direction +, K = 8.** A step every 2 epochs means the counter is ⌊epoch/2⌋. The cycle K·C is 184 rounds = 4.9 h at C=23, 88 rounds (48 s each) = 1.2 h at C=11, and 64 rounds = 1.7 h at C=8. Any K ≥ 8 costs ≤ 0.5% at full participation, and K = 5 costs 0.9% (0.702, E1a). The worst case near the threshold is the same C+1 for every K, so beyond that K only trades the fairness horizon.
- **Composition by striped shuffle.** It gives exact count balance (±1), operator shares at the global level, 0% single-operator committees, and immunity to exits within an era.
- **Era = 256 epochs.** It is aligned with `EPOCHS_PER_SUBNET_SUBSCRIPTION` and no longer than `MIN_VALIDATOR_WITHDRAWABILITY_DELAY`, so consolidations cannot be aimed at a known era.
- **The era must be keyed to the anchor, not to wall-clock time.** Then every state that agrees on the anchor agrees on the table, so gossip validation needs only the message and one cached table (the client requirement of msg 1527). Assignment then depends on *which* checkpoint is voted on, never on *when* the previous one finalized (`survey.md:411-413`).

| Recommended, C = | p=1 L=0 | p=1 L=3 | p=.67 L=3 | drop→67%, L=3 (median/max) | ε-fair | era boundary (p=.67, L=3) |
|---|---|---|---|---|---|---|
| 23 | 0.699 (fixed 0.696) | 0.829 (0.826) | 1.136 (1.130) | 1.15 / 1.17 (1.13 / 1.13) | 5.8 h | 0.48 r once (0.047%) |
| 22 | 0.686 (0.682) | 0.822 (0.818) | 1.143 (1.136) | 1.16 / 1.18 | 4.0 h | 0.32 r (0.031%) |
| 11 | 0.727 (0.727) | 1.000 (1.000) | 1.284 (1.273) | 1.27 / 1.36 | 2.6 h | 0.55 r (0.053%) |
| 8 | 0.762 (0.750) | 1.143 (1.125) | 1.391 (1.375) | 1.38 / 1.50 | 2.4 h | 0.87 r (0.085%) |

E13 also shows Mikhail's slide and the per-epoch reshuffle for every C.

**Seed-free fallback.** Use c(v) = *validator index* mod C, never the active-set position (E9b). Stripe the committees inside the cohort (the j-th committee holds the members with ⌊v/C⌋ ≡ j mod 2048/C), and keep the same forward rotation. This gives the same latency and honest-case balance (E8b/c) and zero subnet churn, but it accepts adaptive concentration within days (E12a).

## 9. Mikhail's current rotation, and the per-epoch status quo

**Mikhail's spec: contiguous blocks of the finalized-epoch list, slid left by one validator per round** ([mk :148-171, 853-873](https://github.com/mkalinin/eth2.0-specs/blob/dc-feature/specs/_features/decoupled-consensus/beacon-chain.md)):

| Aspect | Result |
|---|---|
| latency | identical to fixed order: 0.696 / 0.826 / 1.130 (E1a, E1d); G_δ = C (E4) |
| "low overlap" (:138-140) | satisfied, as it is by any fixed order. A unit-sized −1 step would pay 2 rounds at the threshold (s = n/C rows) |
| position fairness | a validator changes unit every n/C rounds (48 days at 10⁶), so ε-fairness takes 3.6 years (158 days at 1.2·10⁵) (E10b). In practice this is a fixed seat |
| composition | contiguous batches: largest operator 18.4% of a unit at 10⁶ (31.2% at 1.2·10⁵) vs 9.4% overall; 10.3% of committees ≥ 90% one operator; persists ~31 days (E8b–d) |
| index list | includes pending entries, so the last unit has 22% fewer voters (E8a); exits are harmless (E9b) |
| p2p churn | 0.2% of validators change committee per round (E9a) |
| verdict | Keep the anchor idea and the state-light design. Replace contiguous blocks with a striped shuffle per era, and speed the positional rotation up to one unit per 8 rounds in the **+** direction. |

**The per-epoch reshuffle** of the fradamt Simplex spec repeats the epoch's shuffle in each round (`simplex/validator.md:222-226`). With 8-slot rounds that is a reshuffle every 4 rounds; with its mainnet `SLOTS_PER_ROUND = 32` it is per round.

| Aspect | Result |
|---|---|
| latency | +2.6% at p=1, L=0 (0.714 vs 0.696) and +1.9% at L=3 (p95 0.96 vs 0.83). At p=.67, L=3: 1.332 mean, p95 1.74 vs 1.130. Drop transient up to 1.96–2.00 rounds (E1a, E2a) |
| fairness | ε-fair only after 35.2 h (p99), versus 5.8 h for slow +1/8r (E10b) |
| composition | fair, but re-randomising it every epoch is unnecessary (E8) |
| state | gossip resolves committees via a checkpoint state (`simplex/p2p-interface.md:768-783`), so it needs the epoch's seed and shuffle. This is exactly the client pain point (msgs 1500-1501, 1514, 1527) |
| churn | 100% every 4 rounds (E9a) |
| verdict | dominated by the recommendation on every axis |

## 10. Heavy-first, assessed honestly (msg 1498)

Heavy-first means higher-balance validators vote earlier.

- **The intuition is right for a round-aligned FG.** From a round-aligned start, quorum arrives after 3 units instead of 6 (C=8) and after 9 instead of 14 (C=23), with the "1.5% hold ~50%" mix (E6a).
- **Under the instant switch it is worse.** The heavy cohort holds 50–55% of stake, so every quorum needs it, and it votes once per round. Throughput is pinned at exactly **1.000 rounds/height** at every L and at p=1 and .8. Balanced orders achieve 0.69–0.83 (E5, E6a).
  - It wins only where balanced orders are already slower than one round per height (C=8, p=.8, L=3: 1.000 vs 1.250).
  - Near the threshold it is roughly even (1.099–1.130 vs 1.130 at p=.67).
- **It concentrates liveness on 1.5% of validators.** Unit stake reaches 11.7× the mean with the 1.5% mix and 3.25× with the 0x02-like mix (E5), so a DoS on a few heavy operators costs a round.
- **It reads balances**, so balance changes re-seat validators and it fails the state-free guard-rail.
- **No state-free variant keeps the gain.** A deterministic order by validator index is not ordered by balance.
- **Verdict: reject** for the decoupled FG.

**Tail-light** (pattern note :467-477): re-randomising every round imports the per-round reshuffle's cost. At C=8 it gives 0.806 vs 0.750 at p=1, L=0, and 2.000 vs 1.375 at p=.67, L=3 (E6b). Its benefit is boundary-block independence for a round-boundary freeze (:440-466), which the instant switch does not have. **Not needed.**

## 11. Open issues

1. **L and round-locking.** Lane B's L range decides where the round-locked regimes sit (heights of exactly 1 round, e.g. p=.8 at L=3); that is where relative-order bias concentrates (§5). The synthesis should read E1a and E7 at Lane B's L. Offset-dependent lag (2–4 units under README:64's inclusion timing) has not been modelled.
2. **SG / fast confirmation.** Any partial-tally gadget makes composition a security unit again (§4a). Re-run E8b's window shares against its actual window once the SG is specified.
3. **Reward design.** Previous-target crediting (mk :124-128) is what keeps stale votes reward-neutral. If a later reward function pays timely votes more, fixed relative order becomes unfair in round-locked regimes, and only composition reshuffles help, at the era timescale (E7).
4. **Activations mid-era.** Validators that are not in I_e need a seat until the next era, for example the fallback rule. This belongs with Lane C's anchor and activation handling (msgs 1516-1519, 1615).
5. **Committee → unit map.** Mikhail's spec has none. The analysis assumed contiguous committee ranges per unit; the recommendation defines the map explicitly.
6. **Miss rates are placeholders.** Q17's per-offset experiment (README:154) sets the real spread. The ε-fair times scale linearly with the spread and the conclusions do not depend on it.
7. **Synthetic registry.** E8 uses Zipf operators and random batches. A mainnet registry snapshot should replace it before the composition numbers are quoted externally.
8. **10 s slots (msg 1623).** The rotation period in hours scales with the round length. The Q17 grid would need redrawing, which is Lane B's job.
