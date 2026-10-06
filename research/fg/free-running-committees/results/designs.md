---
type: draft
status: wip
date: 2026-10-06
provenance: agent
related:
  - ../../staggered-committees/README.md
  - ../sim/designs.py
---

> **Provenance: agent.** This is the design-latency lane of the free-running-committees study (2026-10-06). Yann commissioned it after his discussion with Mikhail Kalinin about the instant height switch. Yann has not reviewed it line by line.
>
> All numbers come from [`sim/designs.py`](../sim/designs.py), which is deterministic and stdlib-only. It is a copy of the prefix-consensus simulator (`projects/ff/prefix-consensus/sim/prefix_sim.py` in the research vault, left unmodified) with instrumented engines added.
>
> **Tags:**
> - **[sim]:** `python3 sim/designs.py all`.
> - **[calc]:** arithmetic on the schedule.
> - **[derived]:** a closed form argued here or in the vault's `projects/ff/continuous-fg/README.md` §4.

# Where the FG target is picked: latency on the free-running committee clock

## Answer

The drawback is real. On this clock it erases most of what floating heights buy.

**Sticky voting.** With sticky voters, the entry fixed at the quorum is first voted at the next round's first unit, when it is already 20 s old (p = 1). Heights then lock to one per round, and E[lag] falls back to DC-today latency:
- ideal model: 5/3 → 5/2 rounds [derived, sim];
- free-running committee clock (FRC), full participation: 174 → 224 s (+50 s, +29 %) [sim].

**Near the 2/3 threshold it becomes a cliff:** +111 s at p = 0.8 and +220 s at p = 0.7. There, the block that completes round r's quorum appears only after round r+1 has begun, so round r+1 re-votes a closed height [calc, sim]. Partial stickiness does not help either: 20 % sticky stake already locks heights to rounds at p = 1.

**Reward fairness does not need stickiness.** The instant switch with previous-target credit already pays stale votes ([staggered-committees §3](../../staggered-committees/README.md#3-position-why-one-unit-later-every-8-rounds)).

**If round-aligned voting is wanted anyway:**
- Pick the target at the round start, not at the quorum.
- Count by prefix: px-sticky is within +10 s of the instant switch at p = 1 and slightly faster at p = 0.9–0.8, and every vote counts.
- Its round-aligned FFG finality still breaks at p = 0.7.

**Rolling FFG** is the fastest design at every p, has a flat lag, and has no round boundary to fall off.

## Findings

1. **Sticky voting reproduces DC today's decomposition** [derived, sim].
   - **Mechanism.** The entry is picked at the quorum, at age 0, but first voted one round later. Justification therefore lands a full round after the pick, and the finality pairs a round after that.
   - **Ideal model.** 1/3 + 2/3 + 2/3 = 5/3 becomes 1/2 + 1 + 1 = 5/2, exactly DC today's terms.
   - **FRC at p = 1.** 30 + 72 + 72 = 174 s becomes 40 + 92 + 92 = 224 s. Stale votes rise from 11 % of honest votes to 26 %.
   - **Why the FRC penalty is smaller than ideal** (+50 s instead of 5/6 round = 77 s): the 8 s aggregation pushes the quorum 68–76 s into the 92 s round, so only the last ~20 s of each round are wasted.
2. **The sticky penalty is a cliff at the round boundary** [calc, sim].
   - **Where the quorum lands.** The quorum needs k = 16 / 18 / 20 / 22 online cohorts at p = 1 / 0.9 / 0.8 / 0.7, and its block lands 68–100 s into the round.
   - **What happens after 92 s.** Once that block lands at or after 92 s, the next round votes the closed height.
     - p = 0.8: one phase in three is hit, giving 1.51 rounds per height and 345 s.
     - p = 0.7: every phase is hit, giving 2.00 rounds per height and 454 s.
   - **Conf-sourced voters** see the quorum about 17 s later than head-sourced ones. The cliff then already bites at p = 1 (1.49 rounds per height, 283 s).
   - **Mixed voters.** At p = 1 a 5 % sticky share costs +17 s, and a 20 % share costs the full +50 s.
3. **Picking the target at the round start removes the cliff; prefix counting recovers most of the remaining gap** [sim, derived].
   - **round-target** takes the FFG checkpoint from the head at the round's first unit. It sits at 13/6 in the ideal model and 212 s on the FRC.
     - It is only 12 s better than ex-sticky at p = 1.
     - It never wastes a round: 232 s against 345 s at p = 0.8.
   - **px-sticky** is round-aligned too, and its first-quorum J* is that same block (or one later).
     - J* then deepens by 20 s (1.67 slots) at p = 1, by 16 s / 12 s / 0 s at p = 0.9 / 0.8 / 0.7.
     - That deepening is worth −28 s against round-target (184 against 212 s; 11/6 against 13/6 in the ideal model).
     - It matches the instant switch at p = 0.9–0.8 (−3 / −9 s), with 100 % of votes counted for their round.
4. **Round-aligned FFG finality breaks near 2/3** [sim].
   - **Mechanism.** If round r's quorum becomes visible only after round r+1 has begun, the first 1–3 units of round r+1 carry a stale source (5–7 units for conf voters). At p = 0.7 a k = 1 link needs 22 of the 23 cohorts.
   - **Result.** round-target and px-sticky then finalize directly only one round in three: 324 s mean, 456 s max. In conf mode at p = 0.7 they *never* finalize, although every round justifies.
   - **Gasper's remedy.** Pinning the source at the round start and adding k ≤ 2 bounds this at 328 s (max 372 s), but costs +29 s at p = 0.8.
   - **No round boundary, no cliff.** Floating heights and Rolling FFG degrade smoothly.
5. **Rolling FFG is fastest at every p, and its lag is flat** [sim].
   - **Lag.** At δ = 1 it is 168 / 192 / 204 / 216 s for p = 1 / 0.9 / 0.8 / 0.7; at δ = 0, 156 / 180 / 192 / 204 s.
   - **Time to inclusion** is the δ boundary, 12(δ+1) s. min = max, and no vote is stale.
   - **Gain over floating heights.** The ideal −20 % shrinks to −3 % … −13 % (δ = 1), because RF pays the 8 s aggregation in both phases.
   - **Consistency.** This agrees with the prefix study at C = 24, whose seconds are identical.

## Headline [sim]

| design (head mode) | p = 1.0 | p = 0.9 | p = 0.8 | p = 0.7 | ideal closed form |
|---|---|---|---|---|---|
| ex-instant | 174 s (1.89) | 204 s (2.22) | 234 s (2.54) | 234 s (2.54) | 5/3 = 1.67 |
| ex-sticky | 224 s (2.43) [+50] | 224 s (2.43) [+20] | 345 s (3.75) [+111] | 454 s (4.93) [+220] | 5/2 = 2.50 |
| round-target | 212 s (2.30) [+38] | 220 s (2.39) [+16] | 232 s (2.52) [-2] | 324 s (3.52) [+90] | 13/6 = 2.17 |
| px-sticky | 184 s (2.00) [+10] | 201 s (2.18) [-3] | 225 s (2.44) [-9] | 324 s (3.52) [+90] | 11/6 = 1.83 |
| rf δ=1 | 168 s (1.83) [-6] | 192 s (2.09) [-12] | 204 s (2.22) [-30] | 216 s (2.35) [-18] | 4/3 = 1.33 |
| rf δ=0 | 156 s (1.70) [-18] | 180 s (1.96) [-24] | 192 s (2.09) [-42] | 204 s (2.22) [-30] | 4/3 = 1.33 |
| DC today (closed form, ideal) | 230 s (2.50) | 230 s (2.50) | 230 s (2.50) | 230 s (2.50) | 5/2 = 2.50 |

(E[lag] over a uniformly random block; [±s] = difference to ex-instant at the same p.)

## 1. Model

**Substrate: the free-running committee clock (FRC).**
- **Time.**
  - Slots are 12 s. FG units are 4 s, three per slot (+0 / +4 / +8 s); unit u starts at 4u s.
  - Cohort u mod 23 votes in unit u.
  - A round is 23 units = 92 s and is not slot-aligned. The schedule repeats every 3 rounds (23 slots).
- **Inclusion.**
  - A unit has a 4 s vote phase and a 4 s on-time aggregation.
  - Each slot also has an IHAVE/IWANT repair window at +8..+10 s and a final aggregation at +10..+12 s.
  - So a vote cast at t lands in the block of slot ⌈(t+8)/12⌉, and the block of slot j carries units 3j−4 .. 3j−2.
- **Blocks.** One per slot, never missed, visible 1 s after proposal.
- **Voter source.**
  - head: the latest visible block.
  - conf (sensitivity rows): the block of slot s−1, from t_s + 6 s on.
- **Quorum.** 2/3 of total stake, with integer weights so the checks are exact. Online honest stake p is spread uniformly over cohorts, so a quorum needs k = 16 / 18 / 20 / 22 cohorts at p = 1 / 0.9 / 0.8 / 0.7.
- **Fix to the copied simulator.**
  - P.round_s = C × unit_s (92 s), P.spr is fractional, and a run has ⌈rounds × 92 / 12⌉ slots.
  - At C = 24 the original tables reproduce byte for byte (§2).

**Designs.**

| id | where and when the target is picked | what a vote counts for | finalization |
|---|---|---|---|
| ex-instant | Entry = the block whose votes complete the previous height's 2/3 quorum. Voters switch at their next unit | a height pair counts iff it names the chain's current entry (prefix_sim EX(2R) = `rewrite.tex` §4; previous-target votes keep reward credit) | finality pairs (h_j, J) need 2/3 before the next justification resets them |
| ex-sticky | Same entry and state machine. A round-r voter votes the (finality pair, height pair) of the block visible at unit 23r for the whole round | same; votes for a closed height are *stale* for counting and keep reward credit | same |
| round-target | Checkpoint cp_r = the head visible at unit 23r | FFG vote (source = latest justified round < r in the voter's view, target = cp_r); cp_r is justified at 2/3 | k = 1: cp_{r−1} is final once 2/3 of round-r votes with source cp_{r−1} have landed. Sensitivity row: the source is pinned at unit 23r and k ≤ 2 is added (Gasper) |
| px-sticky | Each vote names the voter's head, floored at the last block before round r. J*_r = the deepest block with 2/3 of round r's landed votes at or after it; it is recomputed per block and is final at the round's last inclusion | every round-r vote counts for round r | prefix, k = 1: finalize the deepest X such that 2/3 of round r+1's votes carry a round-r source ⪰ X; the source is the round-r J* known on the voter's view |
| rf | Every unit is a position; its target is the last block with slot < slot(u) − δ | per-validator window (previous own tick, τ] | (F1) + (F2′) (vault `projects/ff/continuous-fg/README.md` §3); δ ∈ {0, 1, 2}, default 1 |

The reference rows are closed forms from continuous-fg §4: DC today 5/2 and CHAIN-FG 7/6.

**Metrics.** For each block b, born at 12b s:
- **pick(b)** is the first time a target ⪰ b is picked:
  - heights: the proposal of the first entry ⪰ b;
  - round-target: the round's first unit;
  - px and rf: the first counted vote naming a block ⪰ b.
- **just(b) and fin(b)** are the first times b or a descendant is justified or finalized.

The three columns are E[pick − birth], E[just − pick] and E[fin − just]. They telescope to E[lag].

How the averages are taken:
- Expectations are over blocks, after 6 rounds of burn-in, across 28 whole substrate periods (644 blocks of a 100-round run). At 250 rounds the means move by less than 0.1 s.
- Births are discrete. A block that is itself an entry waits 0, so a pick every H seconds gives E[time to inclusion] = (H − 12)/2, not H/2.
- For px and rf, the pick is the next unit's vote: 4 s, or 12(δ+1) s for rf's δ-boundary. Their wait for the 2/3 quantile shows up in inclusion → justified.

**Target age** is the time since the target block's proposal, measured at four events: its pick, its first vote, its checkpoint's own justification, and the first finalization of the block or a descendant.

## 2. Sanity [sim]

| check | result |
|---|---|
| prefix_sim S0 table (C = 24) reproduced byte for byte by this copy | yes |
| ex-instant engine = prefix_sim run_heights(EX(2R)) per-block lags, 8 FRC configs | yes |
| rf engine = prefix_sim run_rf per-block lags, 24 FRC configs | yes |
| px-sticky final J*_r = prefix_sim round-close PX J_r (p = 1, head), all rounds | yes |

**Ideal model** (one block per 4 s unit, no aggregation or visibility delay, full participation). At C = 230 every design converges to its closed form, term by term:

| design | C | E[time to inclusion] | inclusion → justified | justified → finalized | **E[lag]** | min / max | closed form (continuum) |
|---|---|---|---|---|---|---|---|
| ex-instant | 23 | 0.326 | 0.696 | 0.696 | **1.717** | 1.391 / 2.043 | 1/3 + 2/3 + 2/3 = 5/3 = 1.667 |
| ex-instant | 230 | 0.334 | 0.670 | 0.670 | **1.673** | 1.339 / 2.004 | 1/3 + 2/3 + 2/3 = 5/3 = 1.667 |
| ex-sticky | 23 | 0.478 | 1.000 | 1.000 | **2.478** | 2.000 / 2.957 | 1/2 + 1/1 + 1/1 = 5/2 = 2.500 |
| ex-sticky | 230 | 0.498 | 1.000 | 1.000 | **2.498** | 2.000 / 2.996 | 1/2 + 1/1 + 1/1 = 5/2 = 2.500 |
| round-target | 23 | 0.522 | 0.652 | 1.000 | **2.174** | 1.696 / 2.652 | 1/2 + 2/3 + 1/1 = 13/6 = 2.167 |
| round-target | 230 | 0.502 | 0.665 | 1.000 | **2.167** | 1.670 / 2.665 | 1/2 + 2/3 + 1/1 = 13/6 = 2.167 |
| px-sticky | 23 | 0.043 | 0.879 | 0.947 | **1.870** | 1.391 / 2.348 | 0/1 + 8/9 + 17/18 = 11/6 = 1.833 |
| px-sticky | 230 | 0.004 | 0.888 | 0.945 | **1.837** | 1.339 / 2.335 | 0/1 + 8/9 + 17/18 = 11/6 = 1.833 |
| rf δ=0 | 23 | 0.043 | 0.652 | 0.696 | **1.391** | 1.391 / 1.391 | 0/1 + 2/3 + 2/3 = 4/3 = 1.333 |
| rf δ=0 | 230 | 0.004 | 0.665 | 0.670 | **1.339** | 1.339 / 1.339 | 0/1 + 2/3 + 2/3 = 4/3 = 1.333 |

Closed forms. Rounds are the unit; a block is born uniformly at x ∈ [0, 1) of its round.
- **ex-instant** = floating heights, 1/3 + 2/3 + 2/3 = 5/3 (continuous-fg §4).
- **ex-sticky** [derived]. The entry is picked at x = 2/3 and voted from the next round's start. It is justified at 2/3 of that round, one round after the pick, and finalized one round later: 1/2 + 1 + 1 = 5/2. These are the same terms as DC today.
- **round-target** = round-aligned heights with staggered votes, 1/2 + 2/3 + 1 = 13/6 (continuous-fg §4).
- **px-sticky** [derived].
  - J*_r is the head at x = 1/3. At the first quorum (x = 2/3) J* is the round-start block; it deepens with each later vote and reaches the x = 1/3 block at the round's end.
  - A block at x ≤ 1/3 is justified at 2/3 + x. One at x > 1/3 waits for round r+1's first quorum, at 5/3. Round r's blocks are finalized at 5/3 (x ≤ 1/3) or 8/3 (x > 1/3).
  - Terms: 0 + 8/9 + 17/18, so E[lag] = ∫₀^{1/3}(5/3 − x)dx + ∫_{1/3}^1(8/3 − x)dx = 11/6.
- **rf** = Rolling FFG, ≈ 0 + 2/3 + 2/3 = 4/3 (continuous-fg §3). At C = 23 it is 32/23 = 1.391 from rounding.

## 3. Latency by participation [sim]

Head mode is the default; "· conf" rows take the voter's source from the confirmed block. Times are in seconds, with rounds of 92 s in brackets.

### p = 1.0 (online honest stake; seconds, with rounds of 92 s in brackets) [sim]

| design | target picked | E[time to inclusion] | inclusion → justified | justified → finalized | **E[lag]** | min | p95 | max | ideal closed form (rounds) |
|---|---|---|---|---|---|---|---|---|---|
| ex-instant | quorum block; voted from the next unit | 30 s (0.33) | 72 s (0.78) | 72 s (0.78) | **174 s (1.89)** | 144 s (1.57) | 204 s (2.22) | 204 s (2.22) | 5/3 = 1.67 |
| ex-sticky | quorum block; voted from the next round | 40 s (0.44) | 92 s (1.00) | 92 s (1.00) | **224 s (2.43)** | 180 s (1.96) | 264 s (2.87) | 264 s (2.87) | 5/2 = 2.50 |
| round-target | head at the round's first unit | 48 s (0.52) | 72 s (0.78) | 92 s (1.00) | **212 s (2.30)** | 168 s (1.83) | 252 s (2.74) | 252 s (2.74) | 13/6 = 2.17 |
| round-target (Gasper: pinned source, k ≤ 2) | as round-target; source pinned at the round's first unit | 48 s (0.52) | 72 s (0.78) | 92 s (1.00) | **212 s (2.30)** | 168 s (1.83) | 252 s (2.74) | 252 s (2.74) | 13/6 = 2.17 |
| px-sticky | head at each vote; J*_r = 2/3-quantile | 4 s (0.04) | 91 s (0.99) | 89 s (0.96) | **184 s (2.00)** | 144 s (1.57) | 228 s (2.48) | 228 s (2.48) | 11/6 = 1.83 |
| rf δ=0 | last block with slot < slot(u) − δ | 12 s (0.13) | 72 s (0.78) | 72 s (0.78) | **156 s (1.70)** | 156 s (1.70) | 156 s (1.70) | 156 s (1.70) | 4/3 = 1.33 |
| rf δ=1 | last block with slot < slot(u) − δ | 24 s (0.26) | 72 s (0.78) | 72 s (0.78) | **168 s (1.83)** | 168 s (1.83) | 168 s (1.83) | 168 s (1.83) | 4/3 = 1.33 |
| rf δ=2 | last block with slot < slot(u) − δ | 36 s (0.39) | 72 s (0.78) | 72 s (0.78) | **180 s (1.96)** | 180 s (1.96) | 180 s (1.96) | 180 s (1.96) | 4/3 = 1.33 |
| ex-instant · conf | quorum block; voted from the next unit | 42 s (0.46) | 96 s (1.04) | 72 s (0.78) | **210 s (2.28)** | 168 s (1.83) | 252 s (2.74) | 252 s (2.74) | 5/3 = 1.67 |
| ex-sticky · conf | quorum block; voted from the next round | 69 s (0.75) | 125 s (1.36) | 88 s (0.96) | **283 s (3.07)** | 180 s (1.96) | 348 s (3.78) | 360 s (3.91) | 5/2 = 2.50 |
| round-target · conf | head at the round's first unit | 64 s (0.70) | 72 s (0.78) | 96 s (1.04) | **232 s (2.52)** | 192 s (2.09) | 276 s (3.00) | 276 s (3.00) | 13/6 = 2.17 |
| round-target (Gasper: pinned source, k ≤ 2) · conf | as round-target; source pinned at the round's first unit | 64 s (0.70) | 72 s (0.78) | 125 s (1.36) | **261 s (2.84)** | 192 s (2.09) | 348 s (3.78) | 360 s (3.91) | 13/6 = 2.17 |
| px-sticky · conf | head at each vote; J*_r = 2/3-quantile | 18 s (0.20) | 93 s (1.02) | 99 s (1.07) | **210 s (2.29)** | 168 s (1.83) | 252 s (2.74) | 252 s (2.74) | 11/6 = 1.83 |
| rf δ=1 · conf | last block with slot < slot(u) − δ | 24 s (0.26) | 72 s (0.78) | 96 s (1.04) | **192 s (2.09)** | 192 s (2.09) | 192 s (2.09) | 192 s (2.09) | 4/3 = 1.33 |
| rf δ=2 · conf | last block with slot < slot(u) − δ | 36 s (0.39) | 72 s (0.78) | 96 s (1.04) | **204 s (2.22)** | 204 s (2.22) | 204 s (2.22) | 204 s (2.22) | 4/3 = 1.33 |
| DC today (closed form, ideal) | entry fixed by the previous round's quorum; everyone attests once per round at a_r | 46 s (0.50) | 92 s (1.00) | 92 s (1.00) | **230 s (2.50)** | — | — | — | 5/2 [derived] |
| CHAIN-FG (closed form, ideal; not deployable) | window-aligned; the first quorum already finalizes | 46 s (0.50) | 61 s (0.67) | 0 s (0.00) | **107 s (1.17)** | — | — | — | 7/6 [derived] |

### p = 0.9 (online honest stake; seconds, with rounds of 92 s in brackets) [sim]

| design | target picked | E[time to inclusion] | inclusion → justified | justified → finalized | **E[lag]** | min | p95 | max | ideal closed form (rounds) |
|---|---|---|---|---|---|---|---|---|---|
| ex-instant | quorum block; voted from the next unit | 36 s (0.39) | 84 s (0.91) | 84 s (0.91) | **204 s (2.22)** | 168 s (1.83) | 240 s (2.61) | 240 s (2.61) | 5/3 = 1.67 |
| ex-sticky | quorum block; voted from the next round | 40 s (0.44) | 92 s (1.00) | 92 s (1.00) | **224 s (2.43)** | 180 s (1.96) | 264 s (2.87) | 264 s (2.87) | 5/2 = 2.50 |
| round-target | head at the round's first unit | 48 s (0.52) | 80 s (0.87) | 92 s (1.00) | **220 s (2.39)** | 180 s (1.96) | 264 s (2.87) | 264 s (2.87) | 13/6 = 2.17 |
| round-target (Gasper: pinned source, k ≤ 2) | as round-target; source pinned at the round's first unit | 48 s (0.52) | 80 s (0.87) | 92 s (1.00) | **220 s (2.39)** | 180 s (1.96) | 264 s (2.87) | 264 s (2.87) | 13/6 = 2.17 |
| px-sticky | head at each vote; J*_r = 2/3-quantile | 4 s (0.04) | 107 s (1.16) | 90 s (0.98) | **201 s (2.18)** | 168 s (1.83) | 240 s (2.61) | 240 s (2.61) | 11/6 = 1.83 |
| rf δ=0 | last block with slot < slot(u) − δ | 12 s (0.13) | 84 s (0.91) | 84 s (0.91) | **180 s (1.96)** | 180 s (1.96) | 180 s (1.96) | 180 s (1.96) | 4/3 = 1.33 |
| rf δ=1 | last block with slot < slot(u) − δ | 24 s (0.26) | 84 s (0.91) | 84 s (0.91) | **192 s (2.09)** | 192 s (2.09) | 192 s (2.09) | 192 s (2.09) | 4/3 = 1.33 |
| rf δ=2 | last block with slot < slot(u) − δ | 36 s (0.39) | 84 s (0.91) | 84 s (0.91) | **204 s (2.22)** | 204 s (2.22) | 204 s (2.22) | 204 s (2.22) | 4/3 = 1.33 |
| ex-instant · conf | quorum block; voted from the next unit | 42 s (0.46) | 96 s (1.04) | 84 s (0.91) | **222 s (2.41)** | 180 s (1.96) | 264 s (2.87) | 264 s (2.87) | 5/3 = 1.67 |
| ex-sticky · conf | quorum block; voted from the next round | 86 s (0.94) | 184 s (2.00) | 92 s (1.00) | **362 s (3.94)** | 276 s (3.00) | 444 s (4.83) | 456 s (4.96) | 5/2 = 2.50 |
| round-target · conf | head at the round's first unit | 64 s (0.70) | 80 s (0.87) | 96 s (1.04) | **240 s (2.61)** | 192 s (2.09) | 276 s (3.00) | 288 s (3.13) | 13/6 = 2.17 |
| round-target (Gasper: pinned source, k ≤ 2) · conf | as round-target; source pinned at the round's first unit | 64 s (0.70) | 80 s (0.87) | 184 s (2.00) | **328 s (3.57)** | 288 s (3.13) | 372 s (4.04) | 372 s (4.04) | 13/6 = 2.17 |
| px-sticky · conf | head at each vote; J*_r = 2/3-quantile | 18 s (0.20) | 106 s (1.16) | 99 s (1.08) | **224 s (2.43)** | 180 s (1.96) | 264 s (2.87) | 264 s (2.87) | 11/6 = 1.83 |
| rf δ=1 · conf | last block with slot < slot(u) − δ | 24 s (0.26) | 84 s (0.91) | 96 s (1.04) | **204 s (2.22)** | 204 s (2.22) | 204 s (2.22) | 204 s (2.22) | 4/3 = 1.33 |
| rf δ=2 · conf | last block with slot < slot(u) − δ | 36 s (0.39) | 84 s (0.91) | 96 s (1.04) | **216 s (2.35)** | 216 s (2.35) | 216 s (2.35) | 216 s (2.35) | 4/3 = 1.33 |
| DC today (closed form, ideal) | entry fixed by the previous round's quorum; everyone attests once per round at a_r | 46 s (0.50) | 92 s (1.00) | 92 s (1.00) | **230 s (2.50)** | — | — | — | 5/2 [derived] |
| CHAIN-FG (closed form, ideal; not deployable) | window-aligned; the first quorum already finalizes | 46 s (0.50) | 61 s (0.67) | 0 s (0.00) | **107 s (1.17)** | — | — | — | 7/6 [derived] |

### p = 0.8 (online honest stake; seconds, with rounds of 92 s in brackets) [sim]

| design | target picked | E[time to inclusion] | inclusion → justified | justified → finalized | **E[lag]** | min | p95 | max | ideal closed form (rounds) |
|---|---|---|---|---|---|---|---|---|---|
| ex-instant | quorum block; voted from the next unit | 42 s (0.46) | 96 s (1.04) | 96 s (1.04) | **234 s (2.54)** | 192 s (2.09) | 276 s (3.00) | 276 s (3.00) | 5/3 = 1.67 |
| ex-sticky | quorum block; voted from the next round | 69 s (0.75) | 125 s (1.36) | 151 s (1.64) | **345 s (3.75)** | 276 s (3.00) | 432 s (4.70) | 444 s (4.83) | 5/2 = 2.50 |
| round-target | head at the round's first unit | 48 s (0.52) | 88 s (0.96) | 96 s (1.04) | **232 s (2.52)** | 192 s (2.09) | 276 s (3.00) | 276 s (3.00) | 13/6 = 2.17 |
| round-target (Gasper: pinned source, k ≤ 2) | as round-target; source pinned at the round's first unit | 48 s (0.52) | 88 s (0.96) | 125 s (1.36) | **261 s (2.84)** | 192 s (2.09) | 348 s (3.78) | 360 s (3.91) | 13/6 = 2.17 |
| px-sticky | head at each vote; J*_r = 2/3-quantile | 4 s (0.04) | 122 s (1.32) | 99 s (1.08) | **225 s (2.44)** | 192 s (2.09) | 264 s (2.87) | 264 s (2.87) | 11/6 = 1.83 |
| rf δ=0 | last block with slot < slot(u) − δ | 12 s (0.13) | 84 s (0.91) | 96 s (1.04) | **192 s (2.09)** | 192 s (2.09) | 192 s (2.09) | 192 s (2.09) | 4/3 = 1.33 |
| rf δ=1 | last block with slot < slot(u) − δ | 24 s (0.26) | 84 s (0.91) | 96 s (1.04) | **204 s (2.22)** | 204 s (2.22) | 204 s (2.22) | 204 s (2.22) | 4/3 = 1.33 |
| rf δ=2 | last block with slot < slot(u) − δ | 36 s (0.39) | 84 s (0.91) | 96 s (1.04) | **216 s (2.35)** | 216 s (2.35) | 216 s (2.35) | 216 s (2.35) | 4/3 = 1.33 |
| ex-instant · conf | quorum block; voted from the next unit | 48 s (0.52) | 108 s (1.17) | 96 s (1.04) | **252 s (2.74)** | 204 s (2.22) | 300 s (3.26) | 300 s (3.26) | 5/3 = 1.67 |
| ex-sticky · conf | quorum block; voted from the next round | 86 s (0.94) | 184 s (2.00) | 123 s (1.34) | **393 s (4.28)** | 276 s (3.00) | 516 s (5.61) | 540 s (5.87) | 5/2 = 2.50 |
| round-target · conf | head at the round's first unit | 64 s (0.70) | 88 s (0.95) | 196 s (2.13) | **348 s (3.78)** | 216 s (2.35) | 468 s (5.09) | 480 s (5.22) | 13/6 = 2.17 |
| round-target (Gasper: pinned source, k ≤ 2) · conf | as round-target; source pinned at the round's first unit | 64 s (0.70) | 88 s (0.95) | 184 s (2.00) | **336 s (3.65)** | 288 s (3.13) | 372 s (4.04) | 384 s (4.17) | 13/6 = 2.17 |
| px-sticky · conf | head at each vote; J*_r = 2/3-quantile | 18 s (0.20) | 118 s (1.28) | 200 s (2.17) | **336 s (3.65)** | 204 s (2.22) | 456 s (4.96) | 468 s (5.09) | 11/6 = 1.83 |
| rf δ=1 · conf | last block with slot < slot(u) − δ | 24 s (0.26) | 84 s (0.91) | 108 s (1.17) | **216 s (2.35)** | 216 s (2.35) | 216 s (2.35) | 216 s (2.35) | 4/3 = 1.33 |
| rf δ=2 · conf | last block with slot < slot(u) − δ | 36 s (0.39) | 84 s (0.91) | 108 s (1.17) | **228 s (2.48)** | 228 s (2.48) | 228 s (2.48) | 228 s (2.48) | 4/3 = 1.33 |
| DC today (closed form, ideal) | entry fixed by the previous round's quorum; everyone attests once per round at a_r | 46 s (0.50) | 92 s (1.00) | 92 s (1.00) | **230 s (2.50)** | — | — | — | 5/2 [derived] |
| CHAIN-FG (closed form, ideal; not deployable) | window-aligned; the first quorum already finalizes | 46 s (0.50) | 61 s (0.67) | 0 s (0.00) | **107 s (1.17)** | — | — | — | 7/6 [derived] |

### p = 0.7 (online honest stake; seconds, with rounds of 92 s in brackets) [sim]

| design | target picked | E[time to inclusion] | inclusion → justified | justified → finalized | **E[lag]** | min | p95 | max | ideal closed form (rounds) |
|---|---|---|---|---|---|---|---|---|---|
| ex-instant | quorum block; voted from the next unit | 42 s (0.45) | 96 s (1.04) | 96 s (1.04) | **234 s (2.54)** | 192 s (2.09) | 276 s (3.00) | 276 s (3.00) | 5/3 = 1.67 |
| ex-sticky | quorum block; voted from the next round | 86 s (0.94) | 184 s (2.00) | 184 s (2.00) | **454 s (4.93)** | 360 s (3.91) | 540 s (5.87) | 540 s (5.87) | 5/2 = 2.50 |
| round-target | head at the round's first unit | 48 s (0.52) | 96 s (1.04) | 180 s (1.96) | **324 s (3.52)** | 192 s (2.09) | 444 s (4.83) | 456 s (4.96) | 13/6 = 2.17 |
| round-target (Gasper: pinned source, k ≤ 2) | as round-target; source pinned at the round's first unit | 48 s (0.52) | 96 s (1.04) | 184 s (2.00) | **328 s (3.57)** | 288 s (3.13) | 372 s (4.04) | 372 s (4.04) | 13/6 = 2.17 |
| px-sticky | head at each vote; J*_r = 2/3-quantile | 4 s (0.04) | 136 s (1.48) | 184 s (2.00) | **324 s (3.52)** | 192 s (2.09) | 444 s (4.83) | 456 s (4.96) | 11/6 = 1.83 |
| rf δ=0 | last block with slot < slot(u) − δ | 12 s (0.13) | 96 s (1.04) | 96 s (1.04) | **204 s (2.22)** | 204 s (2.22) | 204 s (2.22) | 204 s (2.22) | 4/3 = 1.33 |
| rf δ=1 | last block with slot < slot(u) − δ | 24 s (0.26) | 96 s (1.04) | 96 s (1.04) | **216 s (2.35)** | 216 s (2.35) | 216 s (2.35) | 216 s (2.35) | 4/3 = 1.33 |
| rf δ=2 | last block with slot < slot(u) − δ | 36 s (0.39) | 96 s (1.04) | 96 s (1.04) | **228 s (2.48)** | 228 s (2.48) | 228 s (2.48) | 228 s (2.48) | 4/3 = 1.33 |
| ex-instant · conf | quorum block; voted from the next unit | 54 s (0.58) | 120 s (1.30) | 96 s (1.04) | **270 s (2.93)** | 216 s (2.35) | 324 s (3.52) | 324 s (3.52) | 5/3 = 1.67 |
| ex-sticky · conf | quorum block; voted from the next round | 86 s (0.94) | 184 s (2.00) | 184 s (2.00) | **454 s (4.93)** | 360 s (3.91) | 540 s (5.87) | 540 s (5.87) | 5/2 = 2.50 |
| round-target · conf | head at the round's first unit | — | — | — | **never finalizes** (justifies every round; k = 1 links split by stale sources) | — | — | — | 13/6 = 2.17 |
| round-target (Gasper: pinned source, k ≤ 2) · conf | as round-target; source pinned at the round's first unit | 64 s (0.70) | 96 s (1.05) | 184 s (2.00) | **344 s (3.74)** | 300 s (3.26) | 384 s (4.17) | 384 s (4.17) | 13/6 = 2.17 |
| px-sticky · conf | head at each vote; J*_r = 2/3-quantile | — | — | — | **never finalizes** (justifies every round; k = 1 links split by stale sources) | — | — | — | 11/6 = 1.83 |
| rf δ=1 · conf | last block with slot < slot(u) − δ | 24 s (0.26) | 96 s (1.04) | 120 s (1.30) | **240 s (2.61)** | 240 s (2.61) | 240 s (2.61) | 240 s (2.61) | 4/3 = 1.33 |
| rf δ=2 · conf | last block with slot < slot(u) − δ | 36 s (0.39) | 96 s (1.04) | 120 s (1.30) | **252 s (2.74)** | 252 s (2.74) | 252 s (2.74) | 252 s (2.74) | 4/3 = 1.33 |
| DC today (closed form, ideal) | entry fixed by the previous round's quorum; everyone attests once per round at a_r | 46 s (0.50) | 92 s (1.00) | 92 s (1.00) | **230 s (2.50)** | — | — | — | 5/2 [derived] |
| CHAIN-FG (closed form, ideal; not deployable) | window-aligned; the first quorum already finalizes | 46 s (0.50) | 61 s (0.67) | 0 s (0.00) | **107 s (1.17)** | — | — | — | 7/6 [derived] |

Reading notes.
- **ex-instant at p = 0.8 and p = 0.7 is identical** (rounds per height 1.04). Three units land per block, so both quorums complete in the block 8 slots after the switch.
- **round-target equals its Gasper variant at p ≥ 0.9.** Every round-(r+1) voter already sees cp_r justified.
- **The conf rows add 0–7 stale-source units per round** (§5.1). This hits ex-sticky first, then the round-aligned FFG finality.

## 4. Target depth [sim]

Mean age of the target block, in seconds, at each event. Ages are taken over checkpoints whose target lies in the measurement window. "Rounds per height" applies to the height designs.

The vote columns split the honest votes, weighted by stake, into:
- **timely:** counted toward the target it names;
- **stale:** names a height that is already closed (keeps reward credit);
- **redundant:** already counted, so it backs off.

### p = 1.0, head mode [sim]

| design | age at pick | age at first vote | age at justification | age at finalization | rounds per height | honest votes: timely / stale / redundant |
|---|---|---|---|---|---|---|
| ex-instant | 0 s | 4 s | 72 s | 144 s | 0.78 | 89 / 11 / 0 % |
| ex-sticky | 0 s | 20 s | 92 s | 184 s | 1.00 | 74 / 26 / 0 % |
| round-target | 8 s | 8 s | 80 s | 172 s | 1 (round-aligned) | 100 / 0 / 0 % |
| px-sticky | 4 s | 4 s | 72 s | 144 s | 1 (round-aligned) | 100 / 0 / 0 % |
| rf δ=1 | 28 s | 28 s | 100 s | 168 s | 1/23 (a position per unit) | 100 / 0 / 0 % |

### p = 0.9, head mode [sim]

| design | age at pick | age at first vote | age at justification | age at finalization | rounds per height | honest votes: timely / stale / redundant |
|---|---|---|---|---|---|---|
| ex-instant | 0 s | 4 s | 84 s | 168 s | 0.91 | 90 / 10 / 0 % |
| ex-sticky | 0 s | 12 s | 92 s | 184 s | 1.00 | 83 / 17 / 0 % |
| round-target | 8 s | 8 s | 88 s | 180 s | 1 (round-aligned) | 100 / 0 / 0 % |
| px-sticky | 4 s | 4 s | 84 s | 168 s | 1 (round-aligned) | 100 / 0 / 0 % |
| rf δ=1 | 28 s | 28 s | 108 s | 192 s | 1/23 (a position per unit) | 100 / 0 / 0 % |

### p = 0.8, head mode [sim]

| design | age at pick | age at first vote | age at justification | age at finalization | rounds per height | honest votes: timely / stale / redundant |
|---|---|---|---|---|---|---|
| ex-instant | 0 s | 4 s | 96 s | 192 s | 1.04 | 92 / 4 / 4 % |
| ex-sticky | 0 s | 48 s | 138 s | 276 s | 1.51 | 62 / 10 / 28 % |
| round-target | 8 s | 8 s | 96 s | 192 s | 1 (round-aligned) | 100 / 0 / 0 % |
| px-sticky | 4 s | 4 s | 96 s | 216 s | 1 (round-aligned) | 100 / 0 / 0 % |
| rf δ=1 | 28 s | 28 s | 116 s | 204 s | 1/23 (a position per unit) | 100 / 0 / 0 % |

### p = 0.7, head mode [sim]

| design | age at pick | age at first vote | age at justification | age at finalization | rounds per height | honest votes: timely / stale / redundant |
|---|---|---|---|---|---|---|
| ex-instant | 0 s | 4 s | 96 s | 192 s | 1.04 | 92 / 4 / 4 % |
| ex-sticky | 0 s | 88 s | 184 s | 368 s | 2.00 | 49 / 7 / 43 % |
| round-target | 8 s | 8 s | 104 s | 288 s | 1 (round-aligned) | 100 / 0 / 0 % |
| px-sticky | 4 s | 4 s | 100 s | 284 s | 1 (round-aligned) | 100 / 0 / 0 % |
| rf δ=1 | 28 s | 28 s | 124 s | 216 s | 1/23 (a position per unit) | 100 / 0 / 0 % |

How to read the ages:
- **Yann's "already deep".** Under sticky voting the entry is 20 s old at its first vote at p = 1, and 12 / 48 / 88 s at p = 0.9 / 0.8 / 0.7. It is justified at age 92 s, against 72 s with the instant switch.
- **A late pick is not the cost by itself.** round-target picks an 8 s old head and still trails px-sticky. The cost is how long the picked target then waits.

## 5. Mechanisms

### 5.1 The round boundary [calc]

When does the block completing round r's quorum become visible, relative to round r+1's first unit (no missed slots)?

| p | cohorts needed k | k-th unit starts | quorum block at (s into round r; phase r mod 3 = 0 / 1 / 2) | visible to head voters before round r+1? | round-(r+1) units cast before it is visible: head / conf |
|---|---|---|---|---|---|
| 1.0 | 16 | 60 s | 72 s / 76 s / 68 s | yes / yes / yes | 0 / 0 / 0 ; 0 / 1 / 0 |
| 0.9 | 18 | 68 s | 84 s / 76 s / 80 s | yes / yes / yes | 0 / 0 / 0 ; 3 / 1 / 2 |
| 0.8 | 20 | 76 s | 84 s / 88 s / 92 s | yes / yes / no | 0 / 0 / 1 ; 3 / 4 / 5 |
| 0.7 | 22 | 84 s | 96 s / 100 s / 92 s | no / no / no | 2 / 3 / 1 ; 6 / 7 / 5 |

The margins:
- **ex-sticky** wastes round r+1 whenever this is "no".
- **round-target and px-sticky** lose a k = 1 link whenever more than 23 − k units of round r+1 are early.
- **The margin is small.** At p = 1 it is 15–23 s, about one slot of headroom. At p = 0.9 it is 7–15 s, so one missed slot at the wrong moment already pushes a round over [calc].

### 5.2 How far J* deepens after the first quorum (px-sticky) [sim]

| p | J* age at the first quorum | deepening after the first quorum: mean (max) | J*_r final finalized directly | stale-source units per round | round-target: finalized directly, stale-source units |
|---|---|---|---|---|---|
| 1.0 | 72 s | 1.67 slots = 20 s (2 slots) | 100 % | 0.00 | 100 %, 0.00 |
| 0.9 | 84 s | 1.33 slots = 16 s (2 slots) | 100 % | 0.00 | 100 %, 0.00 |
| 0.8 | 96 s | 1.00 slots = 12 s (1 slots) | 67 % | 0.33 | 100 %, 0.33 |
| 0.7 | 100 s | 0.00 slots = 0 s (0 slots) | 33 % | 2.00 | 33 %, 2.00 |

- **Size of the deepening.** In the ideal model J* deepens by C − ⌈2C/(3p)⌉ units, i.e. 28 s at p = 1. On the FRC it is 20 s, because votes land three units per block and targets are 12 s blocks.
- **Where the deepening goes.** It happens entirely between the first quorum and the round's last inclusion. It is the main difference between px-sticky and round-target.
- **The finality column.** "J*_r final finalized directly" falls below 100 % for two reasons:
  - stale sources (§5.1);
  - early round-(r+1) voters whose source is a not-yet-final J*_r. They finalize a block one or two shallower first.

### 5.3 Mixed voters: a share σ of honest stake sticky, the rest instant [sim]

E[lag]; rounds per height; stale share of honest votes.

| σ (sticky share) | p = 1.0 | p = 0.9 | p = 0.8 | p = 0.7 |
|---|---|---|---|---|
| 0.0 (ex-instant) | 174 s (1.89); 0.78 r/h; 11 % stale | 204 s (2.22); 0.91 r/h; 10 % stale | 234 s (2.54); 1.04 r/h; 4 % stale | 234 s (2.54); 1.04 r/h; 4 % stale |
| 0.05 | 191 s (2.08); 0.86 r/h; 13 % stale | 204 s (2.22); 0.91 r/h; 12 % stale | 234 s (2.54); 1.04 r/h; 7 % stale | 259 s (2.82); 1.15 r/h; 2 % stale |
| 0.1 | 197 s (2.14); 0.88 r/h; 16 % stale | 204 s (2.22); 0.91 r/h; 15 % stale | 234 s (2.54); 1.04 r/h; 9 % stale | 289 s (3.14); 1.29 r/h; 2 % stale |
| 0.15 | 201 s (2.18); 0.90 r/h; 19 % stale | 224 s (2.43); 1.00 r/h; 15 % stale | 236 s (2.56); 1.05 r/h; 10 % stale | 341 s (3.70); 1.49 r/h; 2 % stale |
| 0.2 | 224 s (2.43); 1.00 r/h; 23 % stale | 224 s (2.44); 1.00 r/h; 15 % stale | 240 s (2.61); 1.07 r/h; 9 % stale | 342 s (3.72); 1.51 r/h; 2 % stale |
| 0.25 | 224 s (2.43); 1.00 r/h; 23 % stale | 224 s (2.44); 1.00 r/h; 15 % stale | 245 s (2.67); 1.09 r/h; 9 % stale | 342 s (3.72); 1.51 r/h; 3 % stale |
| 0.5 | 224 s (2.43); 1.00 r/h; 25 % stale | 224 s (2.43); 1.00 r/h; 16 % stale | 270 s (2.93); 1.20 r/h; 8 % stale | 345 s (3.75); 1.51 r/h; 6 % stale |
| 1.0 (ex-sticky) | 224 s (2.43); 1.00 r/h; 26 % stale | 224 s (2.43); 1.00 r/h; 17 % stale | 345 s (3.75); 1.51 r/h; 10 % stale | 454 s (4.93); 2.00 r/h; 7 % stale |

- **Why the lock.** Sticky stake joins a height only at the round start, which pins the switch to a fixed phase.
- **When it sets in.** Once the instant voters alone can no longer reach 2/3 before that phase comes round again, heights lock to one per round: between σ = 0.15 and 0.2 at p = 1, and between 0.1 and 0.15 at p = 0.9.
- **What the lock costs.** The lag then equals the fully sticky value whatever the phase: about 40 + 92 + 92 s.
- **Below p = 0.9.** At p = 0.8 the instant switch already needs more than a round per height, so σ degrades it gradually (σ = 0.5: +36 s). At p = 0.7 a 5 % sticky share already costs +25 s, and 15 % costs +107 s.

## 6. Not modelled

- **Adversarial behaviour of any kind.** None of the following is simulated:
  - entry splits and AC forks (R3);
  - timeout racing (R1);
  - finality overtaking (R2);
  - adversarial includers, withholding, and late-aggregate games.

  For the adversarial worst cases of EX, PX and RF on the same simulator family (C = 24), see `projects/ff/prefix-consensus/README.md` (TL;DR item 2) and `projects/ff/prefix-consensus/sim/REPORT.md` §5–6 in the research vault. Sticky voting was not part of that study.
- **The cliff of §5.1 is an honest-case effect.** Anything that delays the quorum block by a slot moves it to higher participation.
- **Network imperfections.** Missed slots, jitter, aggregation failures and the late-aggregator path are absent. Every vote lands in its scheduled block, and there is no carry-over into later blocks.
- **Protocol machinery.** None of the following is modelled:
  - rewards (stale votes are only labelled);
  - the leak, healing, the stabilization gadget and nonjustifiable heights;
  - timeouts (an honest run never needs δ_t);
  - forward rotation (rot_K = 0) and era re-draws.
- **Safety.** The accountable safety of px-sticky's prefix finalization rule (k = 1 over a quantile of sources) has not been checked; it is a timing model. round-target is plain FFG.

## 7. Files and reproduction

- [`sim/designs.py`](../sim/designs.py) is the simulator. Above its "FRC study" marker it is prefix_sim.py with the round-length fix; below it are the instrumented engines (`run_ex`, `run_rt`, `run_pxs`, `run_rf2`), the metrics, the tables and the traces.
- [`results/traces.json`](traces.json) holds the event traces for the visualization:
  - p = 1.0 and p = 0.8, head mode, rf at δ = 1;
  - window = rounds 12–17, t = 1104–1656 s, after a 6-round burn-in;
  - `checkpoints[].finalized_at` is the first time the target block or a descendant finalized;
  - `units[].kind` describes the cohort's online honest stake. A redundant or abstaining unit casts nothing, and its `lands_slot` is the block its aggregate would have used.

```
cd projects/dc/networking/research/fg/free-running-committees
python3 sim/designs.py all      # every table in this note, ~70 s
python3 sim/designs.py traces   # results/traces.json, < 1 s
python3 sim/designs.py s0       # prefix_sim's S0 table at C = 24, byte-identical
```
