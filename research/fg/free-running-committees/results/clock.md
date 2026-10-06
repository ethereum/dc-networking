---
title: Free-running committee clock — clock lane (gaps, latency, fairness, pick-your-seat)
status: wip
date: 2026-10-06
provenance: agent
---

> **Provenance: agent.** This is the clock lane of the free-running-committees study that Yann commissioned on 2026-10-06. Yann has not reviewed it line by line. Ideas are credited by name:
> - **Francesco D'Amato:** `(index + round) mod C` (FF chat msg 1491).
> - **Mikhail Kalinin:** the instant switch and enforced windows. Also the end-of-round/start-of-round overlap that he wanted a rotation to avoid (msgs 1539, 1542).
> - **Yann:** pick-your-seat.
>
> The free-running committee clock (FRC) itself is evaluated as briefed. The chat archive does not record who proposed it. The model, the miss-rate placeholders and the reference numbers come from [Q18](../../staggered-committees/README.md), whose simulator is imported read-only. The grid comes from [Q17](../../pipelined-units/README.md).
>
> **Tags.**
> - **[sim]** = printed by `python3 sim/clock.py all`. It is stdlib-only and deterministic, takes about 6 s, and writes every number to [`clock.json`](clock.json).
> - **[calc]** = closed-form arithmetic, also printed.
> - **[derived]** = an argument from the model or the spec, not simulated.

# Free-running committee clock: clock lane

## TL;DR

- **What FRC is, model-wise.** FRC with C = 23 is Q18's *unit model* with fixed order, placed on the wall clock.
  - Q18's 0.696 / 0.826 / 1.130 rounds per height reproduce exactly. In seconds they are **64 / 76 / 104 s** [sim].
  - What is new here: seconds instead of rounds, and block-quantized vote inclusion.
- **Gap.** Every validator votes exactly every **92 s** (G = C) [sim].
  - The Q17 grid gives 96 s with fixed order. Rotations give up to 100 s on Q17 and 96 s on FRC.
  - The 4 s saved against Q17 is the idle tick being used. That costs **+4.35 % FG votes per second** (24/23) [calc].
  - At equal vote rate (C = 24, 96 s rounds) the gap equals Q17's [sim].
- **Latency.** In seconds, FRC is never slower than any Q17 variant: at most 0.1 s worse in one cell [sim].
  - In Q18's constant-lag model it gains 2.5–4 s per height at every participation level.
  - In the explicit-time model (votes counted only when a block includes them) it gains **8 s at p = 1 and 4 s at p = .8**. It gains **nothing at the 2/3 threshold**: 108 s for both FRC and Q17, or 96 s for both if the +0 s unit can see its slot's block before signing.
  - The cause [derived]: at the threshold a height ends with the block that carries the last cohort. That is 12·⌈(G+2)/3⌉ s, the same 108 s for G = 23, 24 and 25.
  - Only **C = 22** reaches 96 s under Q18's signing rule.
- **In-slot fairness comes for free.** Offsets cycle +0 → +8 → +4. The schedule is ε-fair (0.1 pp) after **0.21 h**, against 3.0 h for Q18's rotation (5.8 h with round-boundary penalties) [sim].
  - This holds **only if nothing is tied to round position**. With Q18's MISS_UNIT0/MISS_LAST kept, FRC is never fair: cohort 0 is biased by 0.93 pp forever [sim].
- **Blocks.** Every block carries exactly 3 units [sim]. On Q17, 12.5 % of blocks carry 2.
  - New cost: **8.7 % of FRC blocks carry votes of two rounds**, i.e. two `AttestationData` values. On-time Q17 has 0 % [sim].
- **Do not add an explicit rotation on top of FRC.** `(index + round) mod C` on FRC:
  - raises G to C+1;
  - costs +8–9 s per height at p = 1 and .7 in the explicit-time model;
  - stretches in-slot fairness from 0.21 h to **4.9 h**, because 23 + 1 ≡ 0 (mod 3) freezes each cohort's offset for up to 23 rounds [sim].

  It helps only if round-position penalties exist [sim].
- **Pick-your-seat (Yann).** Under FRC every seat has the same gap and the same offset mix, so honest validators have no timing reason to herd [sim].
  - The stale-vote concentration of round-locked regimes survives: one cohort casts 66 % stale votes at p = .8 in the explicit-time model [sim].
  - It is harmless only while stale votes earn previous-target credit (`mk:124-134`).
- **Without a cap (R1), the composition risks are open** [sim/calc]:
  - per-unit load up to 8.3×;
  - withheld-vote bursts as large as with no windows at all;
  - 27 % of the target seat's committees with no honest aggregator at β = ⅓;
  - 74 % of a 4-unit window owned.
- **A stake cap κ·S/C (R2) closes them while honest validators stay put.**
  - Load ≤ κ.
  - Burst 3(β+κ−1) units.
  - Aggregator-capture probability ≤ 5.5·10⁻⁵.
  - For a 10 % adversary, owning ⅓ of a seat takes 30–118 days instead of 9.5 (R1 with a churn limit) [calc].
  - Plain withholding is not worse when co-located; it is better (92 vs 108 s at β = ⅓) [sim].
- **Pick-your-seat removes** the era seed, grinding, the era-boundary cost and the era invariant.
  - **It needs:**
    - a 1-byte seat field (1 MB at 10⁶);
    - per-seat totals;
    - a ~69 B request;
    - a cap check on **every** inflow (seat change, deposit, top-up, consolidation target);
    - a count cap if validator sizes differ.
  - It is compatible with `Active(epoch(round))` if seat changes take effect at epoch ≥ c+5 and at a round boundary [derived].

## 0. Setup and sanity

**Clocks and schedules.** All schedules use equal stake, with cohort = validator index mod C.

| key | clock | position rule | round |
|---|---|---|---|
| a | Q17 grid: 24 ticks of 4 s per slot-aligned 8-slot round, tick 23 idle (Q17 README:57-62) | fixed | 96 s |
| b | Q17 grid | Francesco's `(index + round) mod C`: +1 seat per round | 96 s |
| c | Q17 grid | Q18's recommendation: +1 seat every 8 rounds | 96 s |
| d | **FRC C = 23**: unit u at 4u s, cohort u mod 23, no idle tick | fixed (k(u) = u mod C) | 92 s |
| e | FRC C = 23 | `(index + round) mod C` on top | 92 s |
| f22 / f24 / f25 | FRC C = 22 / 24 / 25 | fixed | 88 / 96 / 100 s |
| x23 / x24 (extra) | FRC C = 23 / 24 | +1 seat every 8 rounds | 92 / 96 s |

**Models.**
- **Constant lag.** This is Q18's model (`schedules.py:22-38`).
  - A voter at tick t knows the heights justified at ticks ≤ t−L−1.
  - A height is justified at the end of the tick at which 2/3 of stake has voted for it.
  - Instant switch: the next height starts immediately.
- **Explicit time** (new). It encodes the brief's rule.
  - A vote cast at unit start t lands in the block at 12·⌈(t+8)/12⌉ s. This is Q17's "published at t+4, landed by t+8, included by the next block" (Q17 README:57,64).
  - A block counts all included votes for the state's current height, then justifies the height if the tally reaches 2/3. Justification runs after block processing (Mikhail, msg 1537).
  - The quorum block is visible at +1 s, so a unit starting at the block's own slot start still votes the old height. Q18 voters sign at the unit start (Q18 README:238).
  - Lane B's lag of 3 / 2 / 4 units for a quorum completed at the +0 / +4 / +8 s unit falls out of the model [sim].
- **Sensitivity "+0 s sees its block".** The +0 s unit waits for its slot's block before signing. The lag becomes 2 / 1 / 3 [sim].

**Statistical setup.** As in Q18 E1a:
- n = 40·C validators, 320 rounds, the first 20 discarded;
- random offline sets drawn with Q18's `offline_set`;
- for p < 1, 10 offline sets per p, paired across schedules with the same C.

The simulators work at cohort level. This is exact here: composition is fixed and offline validators never return, so all online members of a cohort share one voting history.

**X0. Sanity** [sim]:

| p | L | Q18 published (README:259) | Q18 `schedules.py` re-run | `clock.py` | under FRC |
|---|---|---|---|---|---|
| 1 | 0 | 0.696 | 0.696 | 0.696 | 64.0 s |
| 1 | 3 | 0.826 | 0.826 | 0.826 | 76.0 s |
| .67 | 3 | 1.130 | 1.130 | 1.130 | 104.0 s |

Further checks:
- The cohort-level simulator matches Q18's per-validator `simulate()` tick for tick in **30/30** runs. These cover both clocks, p ∈ {1, .67}, L ∈ {0, 3} and a drop event.
- The explicit-time lag by completing-unit offset is exactly {+0 s: 3, +4 s: 2, +8 s: 4} over every schedule and p, and {2, 1, 3} in the sensitivity variant.

*Reading.* FRC with C = 23 is literally Q18's unit model with fixed order. All of Q18's unit-model results for fixed order therefore hold for FRC, measured in FRC rounds. Everything below is about what the wall clock and the block grid add.

## 1. Vote gaps (metric 1) — X1

| key | schedule | gap min / mean / max (s) | G (ticks) | back-to-back votes per round | L+G at L=3 (s) | explicit-time height at exact threshold (s): default / +0 s sees block |
|---|---|---|---|---|---|---|
| a | Q17 fixed | 96 / 96 / 96 | 24 (C+1) | 0 | 108 | 108 / 96–108 |
| b | Q17 + (index+round) | **8** / 96 / 100 | 25 (C+2) | **1.00** | 112 | 108 / 96–108 |
| c | Q17 + Q18 rec | 8 / 96 / 100 | 25 (C+2) | 0.12 | 112 | 108 / 96–108 |
| **d** | **FRC C=23** | **92 / 92 / 92** | **23 (C)** | **0** | **104** | **108 / 96** |
| e | FRC + (index+round) | **4** / 92 / 96 | 24 (C+1) | 1.00 | 108 | 108 / 96–108 |
| f22 | FRC C=22 | 88 / 88 / 88 | 22 (C) | 0 | 100 | **96 / 96** |
| f24 | FRC C=24 | 96 / 96 / 96 | 24 (C) | 0 | 108 | 108 / 108 |
| f25 | FRC C=25 | 100 / 100 / 100 | 25 (C) | 0 | 112 | 108 / 108 |
| x23 | FRC + Q18 rec | 4 / 92 / 96 | 24 (C+1) | 0.12 | 108 | 108 / 96–108 |
| x24 | FRC C=24 + Q18 rec | 4 / 96 / 100 | 25 (C+1) | 0.12 | 112 | 108 / 108 |

Gap distributions [sim]:
- b: 8 s for 4.3 % of gaps, 100 s for 95.7 %.
- c: 8 s for 0.5 %, 96 s for 87.6 %, 100 s for 11.9 %.
- e: 4 s for 4.3 %, 96 s for 95.7 %.

Q18's `gap_stats` gives the same G for every C = 23 schedule.

*Reading.*
- **Gap.** FRC gives every validator exactly C units between votes [sim], the minimum for one vote per C units.
  - On the Q17 grid the idle tick makes fixed order G = 24 ticks (96 s).
  - A rotation adds one more tick for the wrap cohort and makes it vote twice in a row: 8 s apart on Q17, 4 s on FRC [sim].
- **Mikhail's overlap.** That back-to-back pair is the overlap Mikhail asked a rotation to avoid. Msg 1539: "voters at the beginning of a round won't overlap with voters at the end of a round". Msg 1542: "you don't want the next round to start with the same 1/4 voting".
  - Under `(index + round) mod C` exactly one cohort per round (1/23 of stake) votes at the end of round r and again at the start of r+1.
  - Its second vote is redundant unless a height was justified in those 4–8 s, so its useful gap is C+1 units or more [derived].
  - Fixed order, on either clock, has no such cohort.
- **The gap is not the latency.** In the explicit-time model at the threshold, the next height's first fresh unit is the tick after the quorum block. The height ends with the block carrying the last cohort, at 12·⌈(G+2)/3⌉ s [derived].
  - That is 108 s for G ∈ {23, 24, 25}, i.e. for every C = 23 schedule including the rotations.
  - Only G ≤ 22 gives 96 s.
  - If the +0 s unit sees its block, FRC C = 23 gets 96 s. Q17 gets 96–108 s depending on where its idle tick falls, and its steady state locks into 96 s (§2).

## 2. Seconds per height (metric 2) — X2

The tables give the mean in seconds. Where p95/max differ from the mean they are shown in parentheses. Rounds are in `clock.json`.

**X2b. Constant lag L = 3** (Q18's headline lag) [sim]:

| key | schedule | p=1 | p=.9 | p=.8 | p=.7 | p=.67 |
|---|---|---|---|---|---|---|
| a | Q17 fixed | 78.5 (80/80) | 85.8 (88/88) | 96 | 104.2 (108/108) | 108 |
| b | Q17 + (index+round) | 81.6 (84/84) | 89.4 (92/92) | 96 (100/100) | 107.2 (112/112) | 112 |
| c | Q17 + Q18 rec | 79.2 (84/84) | 86.2 (92/92) | 96 (96/100) | 104.6 (108/112) | 108 (112/112) |
| **d** | **FRC C=23** | **76** | **82.7** (84/84) | **92** | **100.5** (104/104) | **104** |
| e | FRC + (index+round) | 78.9 (80/80) | 85.9 (88/88) | 92 (96/96) | 104.5 (108/108) | 107.3 (108/108) |
| f22 | FRC C=22 | 72 | 80 | 88 | 97.1 (100/100) | 100 |
| f24 | FRC C=24 | 76 | 84 | 96 | 104.1 (104/108) | 108 |
| f25 | FRC C=25 | 80 | 88 | 100 | 108.1 (108/112) | 112 |

The L = 0 table (X2a) shows the same ranking. FRC gives 64.0 s at p = 1 (Q17 fixed: 66.8) and 92 s at p = .67 (Q17: 96).

**X2c. Explicit-time model** [sim]:

| key | schedule | p=1 | p=.9 | p=.8 | p=.7 | p=.67 |
|---|---|---|---|---|---|---|
| a | Q17 fixed | 80 (84/84) | 84 | 96 | 99.3 (108/108) | 108 |
| b | Q17 + (index+round) | 80 (84/84) | 92.1 (96/96) | 96 | 102.7 (108/108) | 108 |
| c | Q17 + Q18 rec | 80 (84/84) | 84.9 (96/96) | 96 | 98.1 (108/108) | 108 |
| **d** | **FRC C=23** | **72** | **84** | **92** (96/96) | **98.2** (108/108) | **108** |
| e | FRC + (index+round) | 81.2 (84/84) | 84 | 95.9 (96/96) | 106.5 (108/108) | 108 |
| f22 | FRC C=22 | 72 | 84 | 84 | 96 | **96** |
| f24 | FRC C=24 | 72 | 84 | 96 | 108 | 108 |
| f25 | FRC C=25 | 84 | 84 | 96 | 108 | 108 |

**X2c2. Sensitivity: the +0 s unit sees its slot's block** [sim]:

| key | schedule | p=1 | p=.9 | p=.8 | p=.7 | p=.67 |
|---|---|---|---|---|---|---|
| a | Q17 fixed | 72 | 83.1 (84/84) | 96 | 96 | 96 |
| b | Q17 + (index+round) | 80 (84/84) | 82.6 (84/84) | 96 | 96 | 96 |
| c | Q17 + Q18 rec | 73.1 (84/84) | 82.5 (84/84) | 95.8 (96/96) | 96 | 96 |
| **d** | **FRC C=23** | **72** | **79.5** (84/84) | **84** | **96** | **96** |
| e | FRC + (index+round) | 72 | 82.9 (84/84) | 92 (96/96) | 96.1 (96/108) | 107.3 (108/108) |
| f22 | FRC C=22 | 72 | 72 | 84 | 96 | 96 |
| f24 | FRC C=24 | 72 | 84 | 96 | 96 | 108 |

**X2e. Sudden drop 100 % → 67 %** at a random instant in 600–900 s, paired across schedules, 60 trials. Each cell gives the worst of the first 3 heights after the drop as median / max, then the worst height in the 768 s after the drop [sim]:

| key | constant lag L=3 | explicit-time | explicit-time, +0 s sees block |
|---|---|---|---|
| a | 108 / 108 [108] | 108 / 108 [108] | 108 / 108 [108] |
| b | 112 / 112 [112] | 108 / 108 [108] | 108 / 108 [108] |
| d | **104** / 104 [104] | 108 / 108 [108] | **96** / 96 [96] |

The other variants:
- c gives 108 / 112 [112] in the lag model and 108 elsewhere.
- e gives 108 everywhere.

*Readings.*
- **Constant lag (X2b).** FRC's 4 s shorter gap shows up as −2.5 to −4 s per height at every p. This is the ~4 % that 92-s rounds predict.
- **Explicit time (X2c).** The block grid quantizes heights to multiples of 12 s. FRC gains −8 s at p = 1 (it locks into an 18-tick cycle with lag 2), 0 at p = .9, −4 s at p = .8 and ≈ −1 s at p = .7. It ties at the threshold.
  - The threshold tie is structural: the last needed cohort lands in the block at 12·⌈(G+2)/3⌉ s for both clocks (X1).
  - Measured in rounds, FRC even looks worse at the threshold: 1.174 vs 1.125 rounds. That is why this note reports seconds.
- **Sensitivity (X2c2).** Moving the +0 s unit's view by one tick moves both clocks to 96 s at the threshold. Q17 gets there by locking its quorum onto the round-start block, which is exactly Q17's "the round closes inside the round" (Q17 README:96).
  - FRC gains −12 s at p = .8 and −3.6 s at p = .9.
- **Missed blocks.** At 4 % missed blocks (X2d) FRC keeps its p = 1 lead: 72.4 vs 80.5 s mean, max 84 vs 96. All C = 23 schedules give 108.5 s at p = .67, with a max of 144 s [sim].
- **Drops (X2e).** The drop transient follows the steady state. FRC is −4 s with constant lag, ties in the explicit-time model, and is −12 s in the sensitivity variant.
- **Overall.** FRC's latency case is real but modest. It is strongest at full participation, and zero at the threshold under Q18's signing rule.

## 3. Units per block (metric 3) — X3

| clock | on-time units per block | mean | with late +4 s supersets | blocks carrying two rounds: on-time / with late |
|---|---|---|---|---|
| Q17 grid | 2: 12.5 %, 3: 87.5 % | 2.875 | 3: 12.5 %, 4: 87.5 % | 0 % / 12.5 % |
| FRC C=22 | 3: 100 % | 3.000 | 4: 100 % | 9.1 % / 13.6 % |
| **FRC C=23** | **3: 100 %** | **3.000** | **4: 100 %** | **8.7 % / 13.0 %** |
| FRC C=24 | 3: 100 % | 3.000 | 4: 100 % | 12.5 % / 12.5 % |
| FRC C=25 | 3: 100 % | 3.000 | 4: 100 % | 8.0 % / 12.0 % |

*Reading.* The brief's arithmetic is right [sim]:
- A vote at t lands in the first block at or after t+8 s.
- The block at 12k carries the units starting at 12k−16, 12k−12 and 12k−8.
- So every FRC block carries exactly three units. Q17 has one 2-unit block per round, which is Q17's Problem 1.

With Q18's late aggregators (published at cut + 4 s), the +4 s unit's superset spills into the next block, so every FRC block carries 3 + 1 aggregates.

The price is that **2 of every 3 round boundaries fall inside a block's 3-unit group**. Those blocks carry votes of two rounds, i.e. two `AttestationData`, so Q18's per-block merge (Q18 README:53, §7) needs two attestations there. That is 8.7 % of blocks on-time against 0 % on Q17. Counting late supersets the two grids are equal: 13.0 % vs 12.5 %.

## 4. In-slot exposure and fairness (metric 4) — X4

Q18's miss rates are **assumed placeholders** (`schedules.py:1463-1467`): +0 / +4 / +8 s units miss 2.0 / 1.0 / 0.5 %. "Penalties" adds +1.0 % on the round's first seat (MISS_UNIT0) and +0.5 % on its last seat (MISS_LAST).

The ε-horizon is excursion / ε, as in Q18 E10b. The 1 h and 1 day windows are taken at lengths H, H+1 and H+2 rounds, so that the 3-round cycle cannot hide a deviation [sim].

| key | schedule | +0 s share of a cohort's votes over any 1 h | ε-fair, in-slot only | worst dev. ≥1 h / ≥1 d (pp) | ε-fair, + penalties | worst dev. ≥1 h (pp) |
|---|---|---|---|---|---|---|
| a | Q17 fixed | 0–100 % | never (0.80 pp) | 0.80 / 0.80 | never (1.74 pp) | 1.74 |
| b | Q17 + (index+round) | 32.5–36.8 % | 0.38 h | 0.033 / 0.0016 | 0.72 h | 0.061 |
| c | Q17 + Q18 rec | 20.0–42.1 % | 3.01 h | 0.196 / 0.0090 | **5.80 h** | 0.397 |
| **d** | **FRC C=23** | **31.7–35.0 %** | **0.21 h** | **0.021 / 0.0009** | **never (0.93 pp)** | 0.956 |
| e | FRC + (index+round) | 0.0–59.0 % | 4.90 h | 0.462 / 0.0200 | 5.09 h | 0.475 |
| f22 / f25 | FRC C=22 / 25 | 31.7–34.9 / 31.6–35.1 % | 0.20 / 0.23 h | ≈ 0.02 / 0.001 | never (0.93 / 0.94 pp) | ≈ 0.96 |
| f24 | FRC C=24 | 0–100 % | never (0.83 pp) | 0.83 | never (1.77 pp) | 1.77 |
| x23 | FRC + Q18 rec | 29.3–37.5 % | 0.64 h | 0.058 / 0.0027 | 3.34 h | 0.293 |

*Reading.* The table reproduces Q18 for its own schedules [sim]: 5.80 h for its recommendation, 1.74 pp for a fixed seat.

**FRC's offset cycle.** FRC moves every cohort through +0 → +8 → +4 [sim]: cohort k votes at u = k + 23r, and 23 ≡ 2 (mod 3).
- Per-offset effects therefore average out exactly every 3 rounds (276 s).
- That reaches ε-fairness in **0.21 h (8 rounds)**, 14× faster than Q18's rotation on the same placeholders, without any rotation function.

**What it does not fix.** Anything tied to the round *position*.
- With MISS_UNIT0 and MISS_LAST kept, they sit on seats 0 and C−1. Under FRC's fixed order those are the same cohorts forever: 0.93 pp, never fair.
- Q18's slow rotation on top of FRC (x23) restores fairness in 3.34 h at the cost of G = C+1.

**Per C.**
- C = 24 has **no** automatic rotation: 24 ≡ 0 (mod 3).
- C = 22 and C = 25 rotate in the other direction (+0 → +4 → +8) and are equally fast.
- `(index + round) mod C` on FRC cancels the automatic rotation, since 24 ≡ 0 (mod 3). Offsets then stay frozen for up to 23 rounds: 4.90 h.

## 5. Round starts, alignment, traffic (metric 5) — X5

| clock | round (s) | round-start offset cycle | round boundaries mid-slot | round = epoch boundary every | rounds containing an epoch boundary | automatic in-slot rotation | FG votes/s vs Q17 | per-unit load vs C=23 |
|---|---|---|---|---|---|---|---|---|
| Q17 grid | 96 | +0 | 0 % | 4 rounds | 0 % | no | 1.000 | 1.000 |
| FRC C=22 | 88 | +0 → +4 → +8 | 66.7 % | 48 rounds | 20.8 % | yes, period 3 | 1.091 | 1.045 |
| **FRC C=23** | **92** | **+0 → +8 → +4** | **66.7 %** | **96 rounds (23 epochs)** | **22.9 %** | **yes, period 3** | **1.0435** | **1.000** |
| FRC C=24 | 96 | +0 | 0 % | 4 rounds | 0 % | **no** | 1.000 | 0.958 |
| FRC C=25 | 100 | +0 → +4 → +8 | 66.7 % | 96 rounds | 25.0 % | yes, period 3 | 0.960 | 0.920 |
| 10 s slots, C=15 | 75 | +0 → +5 | 50 % | 64 rounds | 21.9 % | yes, period 2 | — | — |
| 10 s slots, C=16 | 80 | +0 | 0 % | 4 rounds | 0 % | no | — | — |

*Reading.*
- **Round starts and traffic.** FRC C = 23 rounds start at +0, +8, +4 s, repeating, so two of every three round boundaries are mid-slot [calc]. FG vote traffic rises by exactly 24/23 [calc]; the per-unit load and the per-instant peak are unchanged.
- **The rotation rule** is gcd(C, units per slot) = 1 [calc]:
  - with 3 units per slot, C ≢ 0 (mod 3);
  - with 10 s slots and 2 units per slot, C must be odd (C = 15 rotates with period 2; C = 16 does not).
- **Epochs.** 22.9 % of FRC rounds contain an epoch boundary [calc]. Every function of `epoch(round)` must therefore be evaluated at the round's start, e.g. start slot ⌊23r/3⌋. This covers Q18's `Active(epoch(round))`, the seat and the era.
- **Era length.** Q18's 256-epoch era is 1,068.5 FRC rounds, so it must snap to rounds. A **1,056-round era** is 253 epochs and 11 × 96 rounds [calc]. It keeps Q18's invariant (era ≤ 256 epochs) and aligns era, epoch and round boundaries.

## 6. Verdicts on the claimed consequences

1. **"Every cohort votes exactly every 92 s; G = C is the gap-lemma optimum, versus C+1 or worse with a rotation"**: **true as a gap statement** [sim].
   - FRC gives 92 s. Q17 fixed gives 96 s, Q17 with a rotation up to 100 s, and FRC with a rotation 96 s.
   - Two qualifications:
     - The 4 s gain over Q17 fixed is bought with +4.35 % FG traffic [calc].
     - At the 2/3 threshold in the explicit-time model it buys **no** latency, because block quantization absorbs it [sim, derived]. The latency gains are −8 s at p = 1 and −4 s at p = .8 (explicit), and −2.5 to −4 s everywhere with constant lag [sim].
2. **"In-slot offset cycles +0 → +8 → +4 with period 3 because gcd(C, 3) = 1, so in-slot fairness is exact every 3 rounds without any rotation"**: **true** [sim]. FRC is ε-fair in 0.21 h, against 3.0 h for Q18's rotation.
   - It holds only for effects that depend on the in-slot offset, and only for C ≢ 0 (mod 3). C = 24 gets none.
3. **"Every block carries exactly 3 units"**: **true**, on-time [sim]. Q17 has a 2-unit block once per round.
   - New: 8.7 % of FRC blocks mix two rounds (0 % on Q17 on-time) [sim].
4. **"No round-first/round-last special seat exists operationally under the instant switch"**: **true iff the round is pure accounting** [derived].
   - Under the instant switch the round feeds dedup, the inclusion window (`mk:657-660`), round credit and `Active(epoch(round))`. Only the inclusion window depends on seat position, and the last seat still has 88 s (7 blocks) against 176 s for the first [calc].
   - **MISS_UNIT0** returns with any round-start dependency, such as the round-granularity freeze of the fradamt Simplex spec ("all cohorts freeze their FG fields at the round's first-slot deadline", boundary-pipelining.md:56-58).
     - It would be *worse* under FRC: in 2 of 3 rounds the round's first unit (and at a +4 s start, the first two) votes before any block of that round exists [calc].
     - It would also stick to cohort 0 forever (0.93 pp) [sim].
   - **MISS_LAST** returns only if previous-round inclusion is discounted [derived].
5. **"FG vote traffic per second rises by 24/23"**: **true**: ×1.0435 votes per second and 3.000 vs 2.875 units per block [calc/sim].
6. **"An explicit rotation on top of FRC only hurts"**: **true**, unless round-position penalties exist [sim].
   - It costs G = C+1 and +8–9 s at p = 1 and .7 (explicit).
   - In-slot fairness falls to 4.9 h.
   - It creates Mikhail's overlap for 1/23 of stake every round.
   - If penalties exist, Q18's slow rotation on top (x23: 3.34 h) is the cheaper fix.
7. **C ∈ {22, 24, 25}** [sim]:
   - 22 and 25 rotate offsets; 24 does not.
   - Under Q18's signing rule, 22 is the only C with a threshold gain (96 vs 108 s), at +9.1 % traffic and +4.5 % per-unit load.
   - 10 s slots need C odd.

## 7. Pick-your-seat (Yann)

**Rules modelled.** Every validator owns a seat k ∈ [0, C) and votes at the units u ≡ k (mod C). The schedule is a pure function of time, with no seed.

| rule | description |
|---|---|
| **R0** | no choice: striping by validator index mod C, or Q18's era hash |
| **R1** | free choice, no cap |
| **R2** | free choice with a per-seat stake cap κ·S/C, κ ∈ {1.0, 1.05, 1.1}; changes take effect at an era boundary and are churn-limited (assumed 256 ETH/epoch) |

### 7.1 What FRC changes for herding — X6

Under FRC every seat has the same gap (92 s) and the same offset mix every 3 rounds (X1, X4). No seat is better than another for timing, so honest validators have no timing reason to herd [sim]. That leaves relative-order effects (Q18 E7, README:281).

| key | schedule | model | p=1: stale share min / mean / max | p=.8 (Q18 seed): min / mean / max (heights of exactly 1 round) | p=.8, 10 offline sets: largest cohort stale share, median / max |
|---|---|---|---|---|---|
| a | Q17 fixed | L=3 | 11.0 / 15.0 / 22.3 % | 0 / 13.0 / **100 %** (100 %) | 100 / 100 % |
| a | Q17 fixed | explicit | 0 / 9.6 / 20.0 % | 0 / 8.7 / **100 %** (100 %) | 100 / 100 % |
| c | Q17 + Q18 rec | explicit | 8.7 / 9.5 / 10.2 % | 7.0 / 8.7 / 9.3 % (100 %) | 9.3 / 9.3 % |
| d | **FRC** | L=3 | 15.7 / 15.8 / 15.9 % | 0 / 13.0 / **100 %** (100 %) | 100 / 100 % |
| d | **FRC** | explicit | 11.0 / 11.1 / 11.2 % | 0 / 5.8 / **66.2 %** (0 %) | **66.4 / 66.8 %** |
| e | FRC + (index+round) | explicit | 9.1 / 9.3 / 9.3 % | 0 / 8.0 / 12.8 % (0 %) | 12.8 / 12.8 % |
| x23 | FRC + Q18 rec | explicit | 10.7 / 10.9 / 11.2 % | 0 / 6.0 / 65.5 % (0 %) | 65.5 / 65.7 % |

*Reading.* **Yes, the E7 lock still happens under FRC.**
- **Constant lag, p = .8, L = 3.** FRC is identical to Q18 E7: heights take exactly one round and the same cohorts cast 100 % stale votes [sim].
- **Explicit-time model.** Heights are multiples of 3 ticks, so an FRC height can never last exactly one 23-tick round. The lock becomes a 3-round cycle (durations 21/24/24 ticks). The largest cohort stale share is still **66 %** over 10 offline sets, against 100 % on the Q17 grid [sim].
- **Rotations.** The lock *follows the cohorts* on FRC, so a slow rotation does not spread it (x23: 65.5 %). On the Q17 grid it is pinned to round positions, here seats 20–21, and the same rotation spreads it to 9.3 % [sim, traced].
- **So** relative-order bias under FRC can only be neutralised in the reward function. The DC draft's previous-target credit already does that (`mk:124-134`, Q18 README:281). With it, pick-your-seat gives honest validators no reason to move. Without it, validators would herd away from the seats that happen to be stale, and the lock would move with them.

### 7.2 (a) Load imbalance and its latency effect — Pa

These runs use 10⁶ equal-size validators on FRC C = 23 and Zipf(1) operators as in Q18 E8; the largest operator holds 9.5 % = 2.19 seats' worth. Offline at p = .67 is the same fraction of every seat. One balanced unit is 8.70 MB of single votes (Q18 network.md:271) [sim].

| configuration | max seat / mean | largest unit | p=1 explicit / L=3 (s) | p=.67 explicit / L=3 (s) |
|---|---|---|---|---|
| R0 stripe | 1.000× | 8.7 MB | 72 / 76 | 108 / 104 |
| R0 era hash, or R1 uniform random choice | 1.006× | 8.7 MB | 72 / 76 | 108 / 104 |
| R1 operators co-locate, random seat | 2.90× (20 seeds: median 3.07×, max 4.18×) | 25.2 MB | 78.9 / 76.6 | 108 / 104 |
| R1 operators co-locate, least-loaded seat | 2.20× | 19.1 MB | 78.8 / 75.3 | 108 / 104 |
| R1, 30 % of stake keeps one client-default seat | 7.60× | 66.1 MB | 92 / 92 | 108 / 104 |
| R1 adversary β=⅓ piles into one seat | 8.33× | 72.5 MB | 92 / 92 | 108 / 104 |
| R2 κ=1.0 / 1.05 / 1.1, operators co-locate under the cap | 1.00 / 1.05 / 1.10× | 8.7 / 9.1 / 9.6 MB | 72 / 76 | 108 / 104 |

*Reading.* Without a cap, operators that co-locate for batching produce 2–4× seat loads, and a herd or an attacker produces 8×. That means 19–72 MB of single votes in one 4 s unit [sim].

**Latency.** The latency effect is bounded and only at high participation.
- A dominant seat pins throughput at one height per round: 92 vs 72 s. This is Q18's heavy-first effect.
- At p = .67 nothing changes, because every online validator is needed wherever it sits.

**The cap.** κ·S/C bounds the load at κ. Two requirements follow [derived]:
- The **default seat must be R0** (index mod C), or a client default herds.
- A stake cap bounds message load only if validator sizes are bounded. With 32-ETH and 2048-ETH validators mixed, a seat at the stake cap can hold many times the average count. R2 needs a **count cap** next to the stake cap.

### 7.3 (b) Withholding: co-located vs spread — Pb

| β | placement | withhold: explicit / L=3 (s) | votes only when pivotal | "edge" (pivotal only at the arc end) |
|---|---|---|---|---|
| 0.10 | spread | 84 / 84 | 84 / 80 | — |
| 0.10 | co-located whole seats | 82.8 / 82.3 | 81.2 / 82.3 | 82.8 / 82.3 |
| 0.20 | spread | 96 / 92 | 84 / 88 | — |
| 0.20 | co-located whole seats | 92 / 92 | 92 / 92 | 92 / 92 |
| ⅓ | spread | **108 / 104** | 108 / 104 | — |
| ⅓ | co-located whole seats | **92 / 92** | 92 / 92 | 92 / 92 |

The p95 and max are ≤ 108 s in every row [sim].

*Reading.* Plain withholding depends only on where the *honest* stake sits. R1 and R2 with honest validators left in place therefore equal the spread rows [derived].

**Co-location helps liveness.** When the adversary owns whole consecutive seats (after a launch-time land grab or long-run turnover, §7.6), its dead arc absorbs the post-switch lag, so no honest vote goes stale. At β = ⅓ heights take one round on average, 92 s against 108 s spread [sim]. The constant-lag model gives exactly 23 ticks; the explicit-time model gives 84/96/96 s.

**Pivotal release does not help the attacker.** The two pivotal-release heuristics never made co-location worse. They are heuristics, not an optimal adversary.

**The bound.** The gap-lemma bound 12·⌈(G+2)/3⌉ = 108 s (explicit, honest includer) uses only honest validators' gaps, and seat choice does not change those [derived]. So co-location cannot push a withholding adversary past it. Q18's adversarial-includer terms (L_max + 3k + G, Q18 §8) are unchanged.

### 7.4 (c) Burst bound — Pc

Q18 §6: windows overlap, so at most 3 units' windows are open at once. The burst is ≤ 3β units, 1.0 unit at β = ⅓ (Q18 README:49, 358).

Units are one balanced unit (V/C single votes); MB are at V = 10⁶ with 200 B per vote, i.e. 8.70 MB per unit. The honest unit load comes on top [calc]:

| β | no windows (β·C) | R0 (3β) | R1, no cap, honest stay (all stake in 3 seats) | R2 κ=1.1, honest stay: 3(β+κ−1) | whole seats κ=1: min(βC, 3) | whole seats κ=1.1 |
|---|---|---|---|---|---|---|
| 0.10 | 2.30 u = 20.0 MB | 0.30 u = 2.6 MB | 2.30 u = 20.0 MB | 0.60 u = 5.2 MB | 2.30 u = 20.0 MB | 2.30 u = 20.0 MB |
| 0.20 | 4.60 u = 40.0 MB | 0.60 u = 5.2 MB | 4.60 u = 40.0 MB | 0.90 u = 7.8 MB | 3.00 u = 26.1 MB | 3.30 u = 28.7 MB |
| ⅓ | 7.67 u = 66.7 MB | 1.00 u = 8.7 MB | 7.67 u = 66.7 MB | 1.30 u = 11.3 MB | **3.00 u = 26.1 MB** | **3.30 u = 28.7 MB** |

*Reading.* The brief's arithmetic is right **for whole seats**: the bound becomes min(βC, 3κ) units, i.e. 3κ/C of stake once β ≥ 3κ/C (0.13 at κ = 1, 0.143 at κ = 1.1). At β = ⅓ that is **26.1 MB** (κ = 1) or **28.7 MB** (κ = 1.1), against 8.7 MB under R0 [calc].

**Two corrections.**
- *Without* a cap (R1), the adversary does not need honest seats to empty. It can pack all its stake into three consecutive seats, and the burst becomes β·C units: exactly the no-window figure, 66.7 MB [calc]. Under R1, windows buy nothing against a co-locating attacker.
- At β = 0.1 even the whole-seat case is 2.3 units, i.e. all of its stake. Windows give a 7.67× reduction under R0 and none under co-location [calc].

### 7.5 (d) Aggregator capture — Pd

The quantity is P(no honest on-time aggregator in a committee) = (1 − 16/|c|)^(h·|c|) ≈ e^(−16h), with |c| = 679 (10⁶/23/64) and h the honest share by count (Q18 README:294) [calc]:

| β | R0 (adversary spread) | R1: adversary piles all stake into one seat | R2 κ=1.05, honest stay | R2 κ=1.1, honest stay |
|---|---|---|---|---|
| 0.10 | h=.90: 4.7·10⁻⁷ | h=.28: **1.1 %** | h=.86: 9.4·10⁻⁷ | h=.82: 1.8·10⁻⁶ |
| 0.20 | h=.80: 2.4·10⁻⁶ | h=.15: **9.1 %** | h=.76: 4.4·10⁻⁶ | h=.73: 7.7·10⁻⁶ |
| ⅓ | h=.67: 2.1·10⁻⁵ | h=.08: **27 %** | h=.64: 3.4·10⁻⁵ | h=.61: 5.5·10⁻⁵ |

The same probability for a mixed seat by the dominant operator's share: 98 % → 72 %, 95 % → 45 %, 90 % → 20 %, 80 % → 3.9 %, 70 % → 0.8 % [calc].

*Reading.* **An operator that fills a seat entirely hurts no one.** There is no honest minority to censor, only self-deanonymisation. **The danger is filling a seat *almost* entirely.**
- R1 lets an attacker dilute any seat's honest validators to h = (1−β)/(1−β+βC), which leaves 27 % of that seat's committees without an honest aggregator at β = ⅓ [calc].
- R2's cap keeps h ≥ (1−β)/κ while honest validators stay put [calc]. The exposure returns only as honest validators leave the seat (§7.6). Victims can then escape by requesting a seat change, if clients detect the situation.

### 7.6 (e) Partial-tally window share, and how fast capture happens — Pe, Pf

Largest adversary share over any 4 consecutive units [sim/calc]:

| β | R0 striped, random indices (10⁶) | R1, honest stay (all stake in 4 seats) | R2 κ = 1 / 1.05 / 1.1, honest stay | whole seats (land grab / R2 long run) |
|---|---|---|---|---|
| 0.10 | 10.15 % | 39.0 % | 10.0 / 14.3 / 18.2 % | 57.5 % |
| 0.20 | 20.11 % | 59.0 % | 20.0 / 23.8 / 27.3 % | 100 % |
| ⅓ | 33.64 % | 74.2 % | 33.3 / 36.5 / 39.4 % | 100 % |

Q18 E8b gives the top Zipf operator's share (9.4 % global) for reference: 9.4–14.3 % striped or shuffled, 12.5–17.8 % with contiguous blocks.

**Days for a β adversary to own share X of one seat** [calc]. These are upper bounds on its speed:
- R1 as defined (no churn limit) is immediate at the next processing step. The R1 column below adds a 256 ETH/epoch seat-change churn.
- R2 first fills the cap slack at 256 ETH/epoch. Honest exits then run at the full exit churn: Electra 256, EIP-8061 1,098 ETH/epoch (eip-8061.md:220-235).
- All exits are assumed honest and uniform over seats. The adversary claims freed room before honest deposits: t = τ·ln((1−β)/(κ(1−X))), with τ = (1−β)S/(exit churn).

| β | X | R1 + 256 ETH/epoch churn | R2 κ=1.0: Electra / EIP-8061 | R2 κ=1.1: Electra / EIP-8061 |
|---|---|---|---|---|
| 0.10 | ⅓ | 9.5 d | 169 / 39 d | 118 / 30 d |
| 0.10 | ½ | 21.7 d | 331 / 77 d | 280 / 67 d |
| 0.20 | ⅓ | 5.4 d | 91 / 21 d | 46 / 13 d |
| ⅓ | ½ | 9.1 d | 120 / 28 d | 83 / 21 d |
| ⅓ | ⅔ | 27.2 d | 289 / 67 d | 252 / 61 d |
| ⅓ | 0.9 | 154 d | 790 / 184 d | 753 / 178 d |

Q18 E12a gives the references:
- Fixed composition with consolidation targeting: β = 0.1 reaches X = ⅓ in 8.3 d (Electra) or 4.4 d (EIP-8061).
- Era hash: not aimable.

*Reading.* **R2 static.** R2 makes the partial-tally share and the burst depend on κ while honest validators stay: +3–8 pp over R0 at κ = 1.05–1.1 [calc].

**R2 long run.** It drifts toward whole seats, on a timescale of the honest exit flow. Reaching X ≥ ½ takes 21–184 days under EIP-8061 exits and 83–790 days under Electra exits [calc]. This presumes the cap binds **every inflow**. If consolidation targets or top-ups bypass it, E12a's 4–8-day route reopens [derived].

**Spec levers.** The ordering is a spec choice: whether deposits or seat changes are processed first decides whether the adversary or honest deposits get freed room. Processing deposits first slows capture to the net outflow [derived].

**When it matters.** All of this matters only if a gadget reads partial tallies (Q18 README:428). The height FG stays schedule-neutral (Q18 §8).

### 7.7 (f) What pick-your-seat removes and what it needs

**Removes** [derived]:
- the era seed and its RANDAO dependency, including Q18 open issue 4 (seed under long non-finality);
- seed grinding (E12b), although direct choice is strictly more power than grinding and only the cap bounds it;
- the era-boundary re-draw: ~0.48 rounds at p = .67 per era (E11), 44 % of validators waiting > C+1 at the boundary, and a simultaneous subnet flip;
- the era invariant `EPOCHS_PER_FG_ERA + 5 ≤ 5 + MIN_VALIDATOR_WITHDRAWABILITY_DELAY`, because nothing random remains to aim at.

Like index mod C and the hash, it never re-seats anyone on exits.

**Needs:**
- **State.** A seat field of 1 B per validator, 1 MB at 10⁶, ideally a separate list so that `Validator` roots do not change. Per-seat stake totals, 8·C = 184 B. A pending seat-change queue [calc].
- **Request.** An EIP-7685 request type with a predeploy and fee, like EIP-7002 (20 + 48 + 8 = 76 B, eip-7002.md:61-63) and EIP-7251 (116 B, eip-7251.md:59-61). The seat request is ~69 B: source address, pubkey, seat. It is authorised by the withdrawal credential. A CL-signed operation, like an exit, would instead let the operator choose; that is the party with the timing interest [derived].
- **Cap check on every inflow.**
  - Seat changes.
  - New activations: default seat = index mod C if it has room, else the least-loaded seat.
  - Top-ups.
  - Consolidations: the source's balance enters the target's seat.

  Plus a count cap, and churn-limited, era-gated processing [derived].
- **Anchor compatibility.** Q18's lemma says `Active(E)` is final once epoch E−5 is processed. It extends to seats if a change processed in epoch c takes effect at epoch ≥ c+5 (`compute_activation_exit_epoch`) and **at a round boundary**. Use seat(v, r) = the seat effective at epoch(start of r). Otherwise, with 22.9 % of FRC rounds straddling an epoch, a mover could vote twice or not at all in one round.
  - The (E, D(E)) cache entry then carries the seat field (+1 MB at 10⁶). Gossip stays state-free [derived].
  - A mover sees one gap between 1 and 2C−1 units. Only movers are affected, and they are churn-limited.
- **Caveat.** A state-held seat is as chain-dependent as Q18's era seed: forks that process different seat changes disagree beyond the c+5 lookahead.
  - This is harmless for the height FG, which is schedule-neutral (Q18 §8).
  - A continuous FG whose slashing condition reads a validator's tick would need a fork-independent seat. Only R0 index mod C provides that [derived].

**Bottom line.** FRC makes seat *timing* uniform, so pick-your-seat costs no timing fairness. Self-chosen *composition* is a different matter: it is safe only with a stake-and-count cap on every inflow, a striped default, and era-gated, churn-limited changes.
- Even then it converges, over months, to what a partial-tally gadget would least like: whole seats owned by the adversary or by single operators.
- R0 under FRC (index mod C with a fork-independent default) keeps every number in the R0 columns at zero extra state.

## 8. Caveats and open issues

1. **The visibility of the quorum block decides the threshold numbers** (X2c vs X2c2): 108 vs 96 s. The FRC-vs-Q17 tie holds either way. Measure when the +0 s unit can sign relative to block arrival.
2. **Miss rates are Q18's placeholders.** All fairness numbers scale linearly with the spread between them.
3. **Finite-size slack.** p = .67 at n = 40·C leaves 3 validators of slack, as in Q18. At the exact threshold every schedule is deterministic (mean = p95 = max).
4. **The explicit-time model omits** late votes, aggregation failures and adversarial includers; the only miss process is the 4 %-missed-block sensitivity.
5. **Pick-your-seat inputs are rough.** The Zipf operators are synthetic. The R2 capture times assume a saturated exit churn and front-running, so they are upper bounds on the adversary's speed. The pivotal adversaries are heuristics.
6. **Not modelled.** Count-vs-stake load under heterogeneous validator sizes, and honest operators co-locating over time (which empties seats for an adversary).

## Files

- [`../sim/clock.py`](../sim/clock.py). Run `python3 sim/clock.py all` to print every table above (X0–X6, Pa–Pg) and write [`clock.json`](clock.json). The JSON holds, per schedule:
  - gap stats;
  - seconds per height by p and model, with lag distributions;
  - the drop transient;
  - units per block;
  - fairness.

  It also holds the per-rule risk numbers under `seat_rules.by_rule` and the verdicts.
- It imports `../../staggered-committees/sim/schedules.py` read-only and writes no bytecode there.
