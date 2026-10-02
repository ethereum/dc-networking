---
title: Staggered FG committees — index set, anchor and bit layout (Lane C, RQ4)
status: wip
date: 2026-10-02
provenance: agent
---

> **Provenance: agent** — 2026-10-02, Lane C of the staggered-committee study (RQ4, hypothesis H2), written by an agent from primary sources and [`../sim/anchor_check.py`](../sim/anchor_check.py); the text has not had a line-by-line review.

**Citation keys.** `cs:` = [consensus-specs](https://github.com/ethereum/consensus-specs) @ a7ab94b (2026-04-24), path under `specs/`. `DC:` = Mikhail Kalinin's DC state-transition draft, [`mkalinin/eth2.0-specs` `dc-feature` `specs/_features/decoupled-consensus/beacon-chain.md`](https://github.com/mkalinin/eth2.0-specs/blob/dc-feature/specs/_features/decoupled-consensus/beacon-chain.md), line numbers of the copy fetched 2026-10-02. `prysm:` = OffchainLabs/prysm @ 88ef966. `EIP-8061:` / `EIP-6914:` = `ethereum/EIPs` `EIPS/eip-*.md`. `R&D <channel>/<date>` = Eth R&D Discord archive day file (author, UTC time). `FF msg N` = FF-team chat, 2026-10-01/02, message N. `sim` = output of `python3 sim/anchor_check.py` (stdlib, deterministic, ~16 s); every in-sim number below is its output.

# Index set, anchor and bit layout

> **Superseded by the [README](../README.md) §2 where they differ** (red-team pass, 2026-10-02):
> - **Window check (§4):** "[REJECT] committees outside the cohorts allowed in this window" is a clock condition, so it is IGNORE.
> - **Subnet and signature checks:** REJECT only when D(E) is finalized locally, else IGNORE. Era seeds can differ across deep forks, and EIP-6914 reuse changes the index→pubkey map.
> - **Era seed:** it is the RANDAO mix of epoch era_start − 5. §3.1's "derived from D(first epoch of the era)" means read from the state at D, never the block root itself, which a proposer can grind.
> - **Cache:**
>   - a decoding cache entry is ~8 MB at 10⁶ (index list plus committee arrays), not 4 MB;
>   - a head that lags behind start(E−4) needs one epoch advance per branch and epoch.
> - **Slashing evidence:** §2.1's "identical for every option" stays true, and the README keeps full-size evidence. An earlier synthesis draft wrongly proposed bounding it.

## TL;DR

- **H2 is confirmed, in this precise form.** Every write to `activation_epoch` or `exit_epoch`, in every fork from phase0 to Gloas/Heze and in the DC draft, goes FAR_FUTURE → v with v ≥ c + 5 (c = current epoch at the write; §1.1). So `Active(E)` is final once `process_epoch` of epoch E − 5 has run (`state.slot ≥ compute_start_slot_at_epoch(E − 4)`), it is a function of **(E, D(E))** with **D(E) = root of the latest block at or before the last slot of epoch E − 5**, and both bounds are attained (sim). Refinements: the cache key needs E as well as D (empty epochs repeat D, sim); `slashed` is *not* delayed and `withdrawable_epoch` can be written twice — neither enters `Active`; EIP-6914 index reuse rewrites a record, but only > 65,792 epochs after the old validator's exit; genesis writes 0.
- **Recommended rule R** (the round-anchored form of O2): index set of round r = `Active(E)`, E = `compute_epoch_at_round(r)`; cache key (E, D(E)); membership = pure function `(validator_index, round) → (cohort, subnet)`; **bit position = rank of the index in its committee ∩ Active(E)**; aggregates carry `fg_dependent_root = D(E)` in the gossip envelope, not in signed data. Gossip validation needs one sorted index list per (E, D(E)) plus pubkeys — never a checkpoint state, never a regeneration. The STF reads `get_active_validator_indices(state, E)` from the including state, which is exact because E is the current or previous epoch.
- **Mikhail's current rule (O4, DC:856-873) is not branch-stable, and not even chain-stable.** sim: (a) different finality → 18 of the 20 rounds in the shared window have *no* state on one branch agreeing with any state on the other; (c) *identical* finality, registry length off by one through a postponed top-up (DC:1081-1083) → different layouts; (b) on a single chain, 21 of 53 rounds change layout inside their own inclusion window (DC:657-660), because the list moves on every registry append and every finality step past an exit epoch — aggregates formed before the change no longer decode after it. At n = 10⁶, one append moves the first member of 992 of the 2048 committees (sim). Two further spec issues: a "poison bit" (DC:714-718 rejects the whole aggregate when one voter exits between vote and inclusion) and an activation stall as written (§1.4).
- **Francesco's target rule (O2a, FF msg 1562-1608) is consistent.** `Active(epoch(T.slot))` is identical in every state descending from T, on every branch (sim) — so the worry in FF msg 1611-1612 does not apply to it. It falls short of R for four reasons: progress votes have no root (DC:723-749), the set is stale while the FG is stuck, it needs an explicit target-age bound to keep voters slashable, and its layout depends on the vote's target.
- **Numbers.** (1) For the round being voted on, D(E) is finalized whenever the finality lag is ≤ **129 slots** (25.8 min at 12 s, 21.5 min at 10 s). That always holds on a healthy DC chain (sim: 0 violations on the healthy branch). (2) Indexing by the full registry (O1) wastes **42.3 %** (2025-03) to **~50 %** (2025-08) of mainnet bits. (3) A cache entry is **4 B × n** (4 MB at 10⁶), and successive epochs differ by **≤ 93 indices** at 36M ETH under EIP-8061 churn. Prysm today holds 16 MB per shuffling entry and up to 32 entries (512 MB) under non-finality (sim).

## 1. H2 — who writes the lifecycle fields

### 1.1 Every writer

Grep of `specs/{phase0,…,gloas,heze,_features/*}` for assignments to the five fields, plus the DC draft. Capella, Fulu, Heze and `_features/eip8025` contain no writer.

| field(s) | writer | location | value written at current epoch c | enters Active(·)? |
|---|---|---|---|---|
| all four epochs = FAR_FUTURE, `slashed` = False | `get_validator_from_deposit` → `add_validator_to_registry` | cs:phase0/beacon-chain.md:2020-2043; cs:altair/beacon-chain.md:246-258, 556-567; cs:electra/beacon-chain.md:1575-1615 (callers 970, 1634); DC:1243-1258 | FAR_FUTURE | no: a new index is inactive at every epoch until an activation write |
| `activation_eligibility_epoch`, `activation_epoch` | `initialize_beacon_state_from_eth1` (genesis) | cs:phase0/beacon-chain.md:1309-1317 | GENESIS_EPOCH = 0, before any epoch is processed | yes: the genesis set |
| `activation_eligibility_epoch` | `process_registry_updates` | cs:phase0:1739-1740; cs:deneb:532-533; cs:electra:916-917 | c + 1 | no |
| `activation_eligibility_epoch` | `upgrade_to_electra`, only for validators with `activation_epoch == FAR_FUTURE` | cs:electra/fork.md:111-125 | reset to FAR_FUTURE | no |
| `activation_epoch` | `process_registry_updates`; guard `is_eligible_for_activation`: `activation_epoch == FAR_FUTURE` and eligibility ≤ finalized epoch (cs:phase0:721-730) | cs:phase0:1759-1761 (churn-capped queue); cs:deneb:553-555 (EIP-7514 cap); cs:electra:911, 924-925 (all eligible) | `compute_activation_exit_epoch(c)` = c + 1 + MAX_SEED_LOOKAHEAD = **c + 5** (cs:phase0:913-917, :266) | yes |
| `exit_epoch`, `withdrawable_epoch` | `initiate_validator_exit`; guard: returns if `exit_epoch ≠ FAR_FUTURE` (cs:phase0:1216-1217, cs:electra:723-724) | cs:phase0:1210-1228; cs:electra:717-731 via `compute_exit_epoch_and_update_churn` cs:electra:770-792 (EIP-8061:169-193: same, uncapped churn) | exit ≥ max(`earliest_exit_epoch`, **c + 5**); withdrawable = exit + 256 | yes |
| ↳ callers | voluntary exit | cs:phase0:2099-2115; cs:deneb:498-517; cs:electra:1706-1727; cs:gloas:1493-1505 | as above | |
| | ejection (`effective_balance ≤ EJECTION_BALANCE`) | cs:phase0:1742-1746; cs:deneb:535-539; cs:electra:918-923 | as above | |
| | EL full-exit request (EIP-7002) | cs:electra:1773-1777 | as above | |
| | `slash_validator` | cs:phase0:1243; cs:altair:468; cs:bellatrix:266; cs:electra:843 | as above | |
| `exit_epoch`, `withdrawable_epoch` of the source | `process_consolidation_request`; guard `exit_epoch == FAR_FUTURE` (cs:electra:1921-1922) | cs:electra:1932-1938 via `compute_consolidation_epoch_and_update_churn` cs:electra:798-824 | exit ≥ max(`earliest_consolidation_epoch`, **c + 5**); withdrawable = exit + 256 | yes |
| `slashed`, `withdrawable_epoch` | `slash_validator` (callers: proposer slashing cs:phase0:1964, cs:gloas:1657; attester slashing cs:phase0:1981; `process_attester_slashing_2` DC:1265-1278) | cs:phase0:1245-1248; cs:altair:470-473; cs:bellatrix:268-271; cs:electra:845-848 | `slashed = True` **at c, effective immediately**; withdrawable = max(withdrawable, c + 8192), raised again after the exit write — so `withdrawable_epoch` is not write-once | no (the exit goes through `initiate_validator_exit`) |
| whole record (all epochs back to FAR_FUTURE, `slashed` = False) | EIP-6914 `get_index_for_new_validator` + `set_or_append_list` | cs:_features/eip6914/beacon-chain.md:34, 43-48, 57-62; cs:altair:253-258 | only if c > withdrawable + SAFE_EPOCHS_TO_REUSE_INDEX (65,536) and balance = 0 | rewrites the past (§1.3) |
| `Builder.withdrawable_epoch` etc. | Gloas builders, a separate `state.builders` list | cs:gloas/beacon-chain.md:797-803, 1363-1392, 1426-1450; cs:gloas/fork.md:61-106 | c + 64 | no: not in `state.validators` |
| — | every `upgrade_to_*` copies `validators=pre.validators` | cs:altair/fork.md:87; bellatrix:73; capella:86; deneb:78; fulu:82; gloas:142; heze:72 | — | no change |

**The DC draft** adds three things, none of which writes `activation_epoch` or `exit_epoch`: (i) `process_pending_deposits` is gated on `state.finalized_slot` (DC:1062), which changes *when* registry entries appear; (ii) `add_validator_to_registry` routes through `get_index_for_new_validator`/`set_or_append_list` (DC:1246-1250) — the Altair default appends, EIP-6914 would reuse; (iii) `process_attester_slashing_2` → `slash_validator` (DC:1276). `process_round` writes only participation (DC:995-999) and `process_height_events` writes only height and finality fields (DC:950-988). So H2 holds for the DC draft as written. Two out-of-tree changes keep it as well: EIP-8061's exit churn keeps `compute_activation_exit_epoch` (EIP-8061:169-173), and the DC draft's `get_activation_churn_limit` (DC:1053) comes from EIP-8061:52-61.

### 1.2 The lemma, the dependency, the dependent root

**Lemma.** Exclude EIP-6914 reuse. Then any block or epoch transition processed at current epoch c that changes `activation_epoch` or `exit_epoch` of an index changes it from FAR_FUTURE to a value ≥ c + 5. *Proof:* table above. Each writer is guarded on FAR_FUTURE, and each value is `compute_activation_exit_epoch(c)` or a churn-queue epoch bounded below by it (cs:electra:771-773, 801-803).

**Consequence.** `is_active_validator(v, E) = activation_epoch ≤ E < exit_epoch` (cs:phase0:698-702). A FAR → v write with v ≥ c + 5 changes this predicate only for E ≥ v ≥ c + 5. Hence `Active(E)` can only be changed by writes at c ≤ E − 5. The last such moment is `process_epoch` for epoch E − 5. It runs inside `process_slots` on the step from the last slot of E − 5 (DC:933-945), with current epoch E − 5, so its activations land exactly on E. Inside it the order is registry updates (activations c + 5, ejections) → pending deposits (new FAR entries) → consolidations (balances) → effective balances (cs:gloas:864-884; DC:1006-1030). No later step writes these fields. The `if/elif` chain (cs:electra:914-925) never makes and activates a validator in one pass, and an entry appended by `process_pending_deposits` becomes eligible one epoch later at the earliest.

- **Fixed after:** `process_epoch(E − 5)`, i.e. in every state with `slot ≥ compute_start_slot_at_epoch(E − 4)`. A block at that slot has current epoch E − 4 and can no longer touch `Active(E)`.
- **Tight (sim):** an `activation_epoch` written at c = E0 − 1 with value c + 5, inside `process_epoch(E0 − 1)`; and a voluntary exit in a block at c with `exit_epoch = c + 5` (idle exit queue, cs:electra:771-773). Of 86 activation and 107 exit writes diffed across all branches, none violated the bound.
- **Dependent root:** `D(E) := get_block_root_at_slot(state, compute_start_slot_at_epoch(E − 4) − 1)`. This is the latest block at or before the last slot of E − 5. The state at `start(E − 4)` is `process_slots(post_state(D(E)), start(E − 4))`, which is deterministic. In Prysm terms it is `DependentRootForEpoch(head, E − 4)` (prysm:beacon-chain/forkchoice/doubly-linked-tree/forkchoice.go:816-836).
- **Today:** shuffling seeds come from the RANDAO mix of E − 2 (cs:phase0:1052-1059), so attester duties depend on the last slot of E − 2 (prysm:beacon-chain/rpc/core/duties.go:273-286). With no seed, the dependency moves back by three epochs.
- **Finalized when:** D(E) is finalized iff `start(E − 4) − 1 ≤ finalized_slot`, i.e. E ≤ epoch(finalized_slot + 1) + 4 (FFG form: E ≤ F + 4, as H2 states). For the round being voted on, a finality lag of ≤ 129 slots suffices. That is 25.8 min at 12 s and 21.5 min at 10 s (sim). On the healthy branch, D(E(current round)) was finalized at all 331 blocks; on the stalled branch it was not at 108 of 246 blocks — every block more than four epochs past the frozen finalized slot (sim).
- **Key is (E, D(E)), not D(E).** `process_epoch` still runs in empty epochs (activations, ejections), so consecutive epochs can share D but not the set. sim: 18 epoch pairs on the branch with four empty epochs. Prysm likewise keys shufflings by seed, which mixes in the epoch (prysm:beacon-chain/cache/committee.go:54-61).

### 1.3 Caveats

- **Genesis.** `activation_epoch = 0` is written before any processing (cs:phase0:1309-1317), and every later write is ≥ 5. So `Active(E ≤ 4)` is the genesis set and D(E < 5) := the genesis block root, as Prysm does for duties at epoch ≤ 1 (prysm:rpc/core/duties.go:274-276). sim checks this with ejections and activations running.
- **Fork upgrades.** Electra's reset touches only never-activated entries (cs:electra/fork.md:111-125). Gloas onboarding writes only `state.builders` (cs:gloas/fork.md:61-106, 194). The DC fork function is still TODO (DC:103) and must keep this property.
- **EIP-6914 index reuse** (FF msg 1609). Reuse needs `c > withdrawable + 65,536` (cs:_features/eip6914/beacon-chain.md:43-48), and `withdrawable ≥ exit + 256`. So an index active at E can be reused only at c > E + 65,792, and a state at epoch c computes `Active(E)` correctly for every E ≥ c − 65,792 — votes are at most two rounds old.
  - What does break: (i) far-past sets (sim: `Active(1650)` contains index 5 on A but not after reuse on D); (ii) **index → pubkey** (sim: index 5 has pubkey 5 on A, 2,000,000 on D).
  - Consequences: pubkey caches must be invalidated on reuse — EIP-6914 already invalidates `equivocating_indices` (cs:_features/eip6914/fork-choice.md:33-37) — and gossip must check membership before the signature. EIP-6914 chose the delay so that withdrawn-validator signatures cannot "poison" attestations (EIP-6914:53).
- **Builders (Gloas)** live in their own registry with `BuilderIndex` flagged by 2⁴⁰ (cs:gloas:129, 451-452). Their indices are reusable immediately (cs:gloas:1363-1367, note 1396-1401). They are never in `get_active_validator_indices`, so they are outside every FG index set.
- **Empty or checkpoint-style targets; no slot in `AttestationData2`** (DC:313-318). Two choices are consistent:
  - E from the round (R): the target is irrelevant to the set.
  - E = epoch of the target block's *own* slot (O2a): any state descending from T works. The node needs T in its fork-choice store (unknown → IGNORE), T's slot from the header, and the ancestor at `start(e_T − 4) − 1`. That is a store lookup, not a state.

  The inconsistent choice is "target root plus a later epoch". It needs T's state advanced through possibly empty epochs to `start(E − 4)` — the Nimbus Holesky path (§5). Progress votes (`target_pair.root = 0`, DC:723-749) leave only the round-based choice (FF msg 1617-1619).

### 1.4 Two DC-draft issues found on the way (not part of H2)

- **Activation stall as written.** DC:1008 drops `process_justification_and_finalization`, so `state.finalized_checkpoint` is never updated after the fork. Yet `is_eligible_for_activation` (cs:phase0:721-730) and `is_active_builder` (cs:gloas:458-468) still read it. As written, no validator and no builder that becomes eligible after the fork is ever activated. Fix: compare against `compute_epoch_at_slot(state.finalized_slot)`, as DC:1062 already does for deposits; the sim uses that.
- **Poison bit.** `is_valid_aggregation_bits` rejects the whole aggregate if any set bit is not active in the *including* state's epoch (DC:714-718). A validator exiting at E + 1 votes honestly in the last round of E, and its aggregate is then uninsertable in the first round of E + 1 (DC:657-660 allows it). sim: at the actual inclusion block the DC rule rejects; R decodes the bit and simply does not count it.

## 2. Index-set / anchor options

**Options.**
- **O1** — the full registry, positions from `validator_index`.
- **O2a** — `Active(epoch(T.slot))` (FF msg 1562-1608).
- **R** — `Active(epoch(round))` with the E − 5 dependent root (the round-anchored O2).
- **O3** — anchor = latest finalized F, carried in the attestation, set = active at F ∪ activation queue at F, STF accepts only anchor = its own latest finalized (FF msg 1639-1641).
- **O4** — the DC draft: `{i < len(validators) : exit_epoch > epoch(finalized_slot)}`, contiguous blocks with `+round` (DC:856-873).
- **O5** — a snapshot hours old (FF msg 1511).

### 2.1 What each party needs

| | gossip validation | STF | slashing evidence |
|---|---|---|---|
| O1 | membership and position are pure arithmetic, but filtering exited/withdrawn/never-active keys needs a per-index status lookup (state) | activity at the round's epoch | explicit `IndexedAttestation2.attesting_indices` (DC:323-329), pubkeys at those indices, `is_slashable_validator` now (cs:phase0:736-742) — **identical for every option, independent of the layout** |
| O2a | target block known (else IGNORE) + one set per (e_T, D(e_T)) found by store ancestry; no state | `epoch(state.target_slot / justified_slot)` (DC:462-464) → `get_active_validator_indices(state, e_T)` | same |
| **R** | **one sorted index list per (E, D(E))** from the node's own head state (computable 4 epochs ahead); aggregates name their D; no state, no regeneration | `get_active_validator_indices(state, E)` on the including state | same |
| O3 | cache keyed by the anchor in the message; V(F) needs the registry length at F (the F state, or a stored length) | anchor = latest finalized, plus `len(validators)` at F → a new state field | same; two votes differing only in anchor are not slashable (DC:493-520 compares heights/roots only) |
| O4 | `(len(validators), epoch(finalized_slot))` of the *including* state — not in the message, so effectively the head state of whoever includes the vote, i.e. the "ill-defined state" of FF msg 1514 | from its own state (designed for this) | same |
| O5 | one set per era keyed by (E_snap, D(E_snap)); D old → finalized unless the stall outlasts the lag | `get_active_validator_indices(state, E_snap)` (write-once fields) | same |

### 2.2 Behaviour

**O1 — full registry**
- *Dead bits:* 42.3 % on mainnet 2025-03-13 (1,822,582 entries, 1,051,655 active; R&D testnets/2025-03-13 jgm 15:37); ~50 % on 2025-08-22 (">2M … ~1M have exited"; R&D consensus-dev/2025-08-22 arnetheduck 19:08). The share keeps growing with exit-and-redeposit consolidation (R&D uncategorized/2025-10-31 greystroke 23:27; jgm 15:43 "~2MM validator list with only a few hundred thousand active"). sim (synthetic): 21.4 %.
- *New activations:* immediately — but so do dead keys, unless filtered.
- *Slashed voters:* in; the STF filters them.
- *Different finality:* the layout is identical; the bitlist bound is the registry length, which is branch-dependent.
- *Long non-finality:* no set needed; a per-branch status table for filtering.

**O2a — `Active(epoch(T.slot))`**
- *Dead bits:* exact at e_T, stale while the FG is stuck. sim, target stuck 12 epochs: 8 dead, 0 missing, because activations are finality-gated. Two targets in one round give two coordinate systems.
- *New activations:* only from the first target in an epoch ≥ activation; blocked while stuck (acceptable per FF msg 1597-1599, if exempted).
- *Slashed voters:* in until exit, not counted (DC:477-482).
- *Different finality:* identical given T — sim: all four branches, every state.
- *Long non-finality:* ≤ 1 set per distinct D among live targets (≤ 2 per branch, DC:668-677). Needs a target-age bound for slashability (§4).

**R — `Active(epoch(round))`, key (E, D(E))** — recommended
- *Dead bits:* none at the round's own epoch; slashed-but-not-yet-exited voters keep a bit.
- *New activations:* from `activation_epoch` itself.
- *Slashed voters:* in until exit, not counted (DC:477-482); gossip MAY IGNORE (§4).
- *Different finality:* identical while D(E) is shared — sim: through epoch e_T + 4, i.e. the 4 epochs (16 rounds) after the fork's epoch, across healthy/stalled/extra-exit/index-reuse branches. Afterwards the aggregate's D says which set to use.
- *Long non-finality:* ≤ 6 entries per viable branch with distinct D (E − 1 … E + 4), each 4 B × n. Successive entries differ by ≤ 93 indices/epoch (36M ETH, EIP-8061; sim), so delta-encode.

**O3 — finalized anchor in the attestation**
- *Dead bits:* active ∪ queue at F ∪ exited since F. sim: 0.00 % (healthy branch), 0.15 % (stalled).
- *New activations:* immediately — V(F) is a superset of everyone who can be active until the next finalization (FF msg 1641).
- *Slashed voters:* in, not counted.
- *Different finality:* different anchors, so a validator must sign twice (FF msg 1639). sim: 199 of 203 same-slot blocks of the two branches carry different anchors.
- *Long non-finality:* F frozen → 1 set. But in the healthy case the anchor churns: DC finalizes in ~2/3 of a round (DC:114-117). sim: every one of 52 rounds has an anchor change inside its inclusion window, so second copies are needed, and aggregates fragment per anchor.

**O4 — DC draft as written**
- *Dead bits:* active + pending + exited since F. sim: 0.00 % at the end of the healthy branch.
- *New activations:* a bit once in the registry, even before activation (rejected if set).
- *Slashed voters:* in, not counted.
- *Different finality:* differs (§2.3 a). Also differs with **identical** finality (§2.3 c).
- *Long non-finality:* F frozen → stable list, with dead bits growing with exits and ejections. In the healthy case, unstable on a single chain (§2.3 b, d).

**O5 — hours-old snapshot**
- *Dead bits:* ≤ 0.343 %/day (Electra) or 1.029 %/day (EIP-8061) of stake at 36M ETH and 12 s slots (×1.2 at 10 s); ≤ 3,860 / 11,580 indices at 32 ETH (sim).
- *New activations:* wait ≤ lag + era. ≤ 0.160 % of stake per day is locked out (1,800 indices at 32 ETH; sim) while still counted in `has_quorum`'s denominator (DC:483-485) — the objection of FF msg 1516-1519.
- *Slashed voters:* in until the next snapshot.
- *Different finality:* identical while the snapshot predates the fork.
- *Long non-finality:* 1–2 sets.

### 2.3 O4 counterexamples (sim, all inside the window where R provably agrees)

Setup: common chain to a target T in epoch e_T. Then four branches:
- **A** — one finalization per round, exits, a slashing, a consolidation, deposits, an EL exit.
- **B** — finality frozen at T, different exits, two slashings, six balance drains that end in ejections, a different consolidation, unprocessable deposits, four empty epochs.
- **C** — A plus one voluntary exit.
- **D** — A plus EIP-6914.

R gives one set and one layout per (branch, epoch/round), and identical sets and layouts on all six branch pairs for E ≤ e_T + 4. That is 14 epochs and 53 rounds, plus 768 layout comparisons for C ∈ {8, 11, 22, 23} with striping and era-hash composition.

- **(a) Different finality, A vs B.** In round 280034 (epoch e_T) the O4 list has 9,461 entries on A (finalized epoch e_T) against 9,463 on B (e_T − 1). Validator 1 sits at (committee, bit) (821, 4) on A but (834, 3) on B; R puts it at (52, 0) on both. In 18 of the 20 window rounds no state on A agrees with any state on B.
- **(b) One chain.** On A, 10 rounds change layout *inside* the round. Example: round 280033 between slots 2240268 and 2240269, when the finalized epoch reaches the exit epoch of two validators and the list shrinks from 9,463 to 9,461. 21 of 53 rounds change within their inclusion window. For R the count is 0 of 85.
- **(c) Identical finality, A vs C.** At slot 2240288 both branches have `finalized_slot` 2240279, but the registry has 12,007 vs 12,008 entries. The finalized queue held [top-up for v, new w] sized to the churn; on C v is exiting, so its top-up is postponed (DC:1081-1083) and w fits. The O4 list is 9,461 vs 9,462 and the layouts differ in 5 window rounds; R is equal for all of them.
- **(d) Across an epoch boundary.** For the last round of an epoch, the layout seen at the first block of the next epoch differs (registry 12,007 → 12,012). Votes for round r included in round r + 1 then decode to different validators.

At mainnet scale one append moves the first member of 992 of 2048 committees, and every later member of those committees shifts too (sim). FF msg 1505 argued that branches would have to be "off by a few epochs" for the set to differ. That holds for `Active(E)`, which is why R and O2a work. It does not hold for O4, whose list also depends on `len(validators)` and on the finalized epoch.

### 2.4 Verdict

**R.** It is as state-free as O5 but uses the round's own epoch: exact bits, no lockout of new validators, and branch-independence for any fork shallower than four epochs — every fork on a chain with finality lag ≤ 129 slots. Deeper forks are disambiguated explicitly. It avoids O3's per-round anchor churn and double signing, and O4's instability on a single chain.

What R gives up relative to O5 or a frozen F: under a long non-finality split (> 4 epochs), the two branches' sets genuinely differ — different exits and ejections — so an aggregate formed on B is decodable on A only if A holds B's set. A node that follows A loses nothing by IGNORE-ing it: A's STF accepts only A's own target and justified roots (DC:668-677), and DC heals through blocks and AC votes, not FG aggregates (FF msg 1559-1566).

O2a is a sound fallback if one insists on anchoring in the message. It needs a root in every vote (FF msg 1618-1619) and the age bound of §4.

## 3. Bit layout

### 3.1 Membership ≠ position

- **Membership** is a pure function `(validator_index, round) → (cohort, subnet)`; Lane A picks the actual schedule. Generic form: `cohort = (g(i) + ρ(r)) mod C`, `subnet = s(i) mod S`, with ρ(r) = (r // K) mod C (slow rotation) and either:
  - striping: g(i) = i mod C, s(i) = i // C; or
  - era-hash: (g, s) = hash(seed_era ‖ i). seed_era is derived from D(first epoch of the era), which is an ancestor of D(E) for every E in the era, so it rides on the same anchor. sim recomputes it from final states.

  Use the raw validator index, not the rank in the active set: a rank changes whenever anyone below it activates or exits (FF msg 1501, 1505).
- **Position** = rank of i in `[j ∈ Active(E) ascending : membership(j, r) = membership(i, r)]`. ρ only relabels *when* a group votes, never who is in it. So a validator's bit position is constant through all rounds of an epoch. It changes at an epoch boundary only if an index below it, in its own group, activates or exits — ≤ 93 such indices network-wide per epoch at 36M ETH under EIP-8061 churn (sim).

| layout | bits per committee | stable across rounds | stable across epochs | branch-independent | composition |
|---|---|---|---|---|---|
| DC draft: contiguous block `list[start_k + r … end_k + r)` (DC:870-872) | ≈ \|O4 list\| / 2048 | no — slides one position per round | no — every append / finality step shifts (992 of 2048 committees per append at 10⁶) | no (§2.3) | contiguous index runs = deposit batches = one operator per committee (H1b) |
| `index // C` over the full registry (O1) | registry / (C·S) | yes | yes | yes | striping |
| **rank in committee ∩ Active(E)** (R) | \|committee\| | **yes** | changes only around churned indices | **yes, given (E, D(E))** | striping or era-hash (Lane A) |

### 3.2 Spec functions

Presets: `FG_COHORTS_PER_ROUND` (C ∈ {8, 11, 22, 23}), `FG_SUBNETS_PER_COHORT` (S; Lane B), `FG_ROTATION_PERIOD_ROUNDS` (K; Lane A), with C · S ≤ `COMMITTEES_PER_ROUND` (DC:282) so that `committee_bits` (DC:245-251) indexes committees directly. Keep C a fork constant: deriving it from |Active| would make membership anchored rather than pure.

```python
FG_ANCHOR_LOOKBACK = 1 + MAX_SEED_LOOKAHEAD  # = 5


def get_fg_dependent_root(state: BeaconState, epoch: Epoch) -> Root:
    """
    Root of the latest block at or before the last slot of ``epoch - FG_ANCHOR_LOOKBACK``.
    ``get_active_validator_indices(state, epoch)`` is a function of ``(epoch, get_fg_dependent_root(state, epoch))``.
    """
    if epoch < FG_ANCHOR_LOOKBACK:
        return GENESIS_BLOCK_ROOT  # from the store, as the beacon API does for early duties
    return get_block_root_at_slot(state, Slot(compute_start_slot_at_epoch(Epoch(epoch - MAX_SEED_LOOKAHEAD)) - 1))


def get_fg_index_set(state: BeaconState, round: Round) -> Sequence[ValidatorIndex]:
    """
    Identical in every state descending from ``get_fg_dependent_root(state, epoch)`` with
    ``state.slot >= compute_start_slot_at_epoch(epoch - MAX_SEED_LOOKAHEAD)``.
    """
    epoch = compute_epoch_at_round(round)
    if epoch >= MAX_SEED_LOOKAHEAD:
        assert compute_start_slot_at_epoch(Epoch(epoch - MAX_SEED_LOOKAHEAD)) <= state.slot
    return get_active_validator_indices(state, epoch)


def get_fg_group(validator_index: ValidatorIndex, era_seed: Optional[Bytes32]) -> Tuple[uint64, uint64]:
    """Composition (Lane A): (group, subnet). Striping, or era-hash when a seed is given."""
    if era_seed is None:
        return (validator_index % FG_COHORTS_PER_ROUND,
                (validator_index // FG_COHORTS_PER_ROUND) % FG_SUBNETS_PER_COHORT)
    h = hash(era_seed + uint_to_bytes(validator_index))
    return (bytes_to_uint64(h[0:8]) % FG_COHORTS_PER_ROUND,
            bytes_to_uint64(h[8:16]) % FG_SUBNETS_PER_COHORT)


def get_fg_rotation(round: Round) -> uint64:
    """Position (Lane A): +1 unit every FG_ROTATION_PERIOD_ROUNDS rounds."""
    return (round // FG_ROTATION_PERIOD_ROUNDS) % FG_COHORTS_PER_ROUND


def get_fg_cohort(validator_index: ValidatorIndex, round: Round, era_seed: Optional[Bytes32] = None) -> uint64:
    """Unit of the round in which ``validator_index`` votes. Pure: no state."""
    group, _ = get_fg_group(validator_index, era_seed)
    return (group + get_fg_rotation(round)) % FG_COHORTS_PER_ROUND


def get_fg_committee_index(validator_index: ValidatorIndex, round: Round,
                           era_seed: Optional[Bytes32] = None) -> CommitteeIndex:
    _, subnet = get_fg_group(validator_index, era_seed)
    return CommitteeIndex(get_fg_cohort(validator_index, round, era_seed) * FG_SUBNETS_PER_COHORT + subnet)


def get_fg_cohort_members(state: BeaconState, round: Round, committee_index: CommitteeIndex) -> Sequence[ValidatorIndex]:
    """Ascending members of one (cohort, subnet) committee; bit k of its aggregation bits = members[k]."""
    era_seed = get_fg_era_seed(state, round)  # None under striping; else derived from D(era start)
    return [
        index for index in get_fg_index_set(state, round)
        if get_fg_committee_index(index, round, era_seed) == committee_index
    ]


def get_fg_bit_index(state: BeaconState, round: Round, validator_index: ValidatorIndex) -> uint64:
    era_seed = get_fg_era_seed(state, round)
    members = get_fg_cohort_members(state, round, get_fg_committee_index(validator_index, round, era_seed))
    return uint64(members.index(validator_index))  # raises if not in the index set


def get_fg_attesting_indices(state: BeaconState, attestation: Attestation) -> Set[ValidatorIndex]:
    """Replaces DC:878-897. Committees are concatenated in ascending committee_bits order (cs:electra:651-669)."""
    output: Set[ValidatorIndex] = set()
    offset = 0
    for committee_index in get_committee_indices(attestation.committee_bits):
        members = get_fg_cohort_members(state, attestation.data.round, committee_index)
        output |= {index for k, index in enumerate(members) if attestation.aggregation_bits[offset + k]}
        offset += len(members)
    assert len(attestation.aggregation_bits) == offset  # cs:electra:1533-1534; missing from DC:697-721
    return output


def get_fg_counted_indices(state: BeaconState, attestation: Attestation) -> Set[ValidatorIndex]:
    """Replaces the rejection at DC:714-718: bits of validators no longer active simply do not count."""
    epoch = get_current_epoch(state)
    return {i for i in get_fg_attesting_indices(state, attestation)
            if is_active_validator(state.validators[i], epoch) and not state.validators[i].slashed}
```

`process_attestation` (DC:1188-1216) keeps its data and signature checks. It uses `get_fg_attesting_indices` for the signature and `get_fg_counted_indices` for the flags. Clients compute the per-committee member lists once per (E, D(E)) by one pass over `Active(E)`; Lane B costs the bitfields at |committee| bits each.

## 4. Bounded-work gossip rules (R)

**Single vote** (`attester_index`, `data`, `signature`; the committee index follows from membership). Checks in cost order:

1. [IGNORE] `data.round` ∉ {current round, previous round} (± clock disparity; DC:657-660). Lane B adds the per-unit timing window and its REJECT/IGNORE split.
2. [REJECT] the topic's subnet ≠ the subnet derived from `get_fg_committee_index(attester_index, data.round)`. Pure.
3. [REJECT if D(E) is finalized locally, else IGNORE] `attester_index ∉ get_fg_index_set(·, data.round)`. The set comes from the node's own (E, D(E)) entry. While D(E) is finalized every honest node holds the same set, so REJECT is safe.
4. [IGNORE] `attester_index` is in the node's local equivocator set: valid slashing evidence seen on any branch. Evidence verifies on every branch that knows the pubkeys, so this is branch-free. Never REJECT, and never change the layout.
5. [IGNORE] already seen a vote for (`attester_index`, `data.round`). Lane A/B may refine this to per height (FF msg 1443).
6. [IGNORE] `data.target_pair.root ≠ 0` and the root is unknown, or does not descend from the local finalized block (cs:phase0/p2p-interface.md:1004-1009; prysm `--ignore-unviable-attestations`, config/features/flags.go:219-223). MAY queue. Under R the target never enters the index set, so an old target costs nothing.
7. [REJECT] signature invalid, using the pubkey of `attester_index` from the same entry that answered 3 (EIP-6914-safe).

**Aggregate.** The envelope gains `fg_dependent_root: Root`, signed by the aggregator but not part of `AttestationData2`; Lane B costs the extra 32 B per aggregate.

- [IGNORE] `fg_dependent_root` is not a cached D(E(data.round)): it is unknown, foreign without a held state, or older than the window. Never REJECT.
- [REJECT] aggregation-bits length ≠ Σ |members| over `committee_bits`.
- [REJECT] committees outside the cohorts allowed in this window (Lane B).
- [REJECT] aggregator not in its committee, or bad selection proof (Lane B).
- [REJECT] aggregate signature over the decoded pubkeys invalid.

Putting D in signed vote data instead costs +32 B per vote and fragments aggregation across anchors; not recommended.

**Target-age bound and slashability.** Under R the bound is implied. A voter in `Active(E)` has `exit_epoch > E`, so `withdrawable_epoch ≥ E + 257`, and it stays slashable (cs:phase0:736-742) for **≥ 256 epochs = 27.3 h** (12 s) after the round (sim) — whatever the target's age. Under O2a the bound must be explicit. A member of `Active(e_T)` is guaranteed slashable for `e_T + 257 − c` more epochs, so guaranteeing an evidence window of W epochs requires `c − e_T ≤ 257 − W`.

**Exited and slashed voters.** Exited voters are excluded by construction. Slashed voters stay in the layout until their exit epoch, which can be days later when the exit queue is long (EIP-8061:21 mentions > 40 days). They are filtered by the STF count (DC:477-482) and MAY be ignored in gossip (rule 4).

**Cached index sets under non-finality.**
- Own chain: ≤ 6 entries (E − 1 … E + 4). They are computed from the head state and are therefore never missing.
- Foreign D: opt-in, ≤ K per epoch, only for branches whose states the node already holds; everything else is IGNORE.
- Memory: 4 B × n per entry (0.48 / 2 / 4 MB at n = 120k / 500k / 1M; sim), and consecutive entries differ by ≤ 93 indices/epoch (sim).
- Today's Prysm, for comparison: 4 shuffling entries, growing to 32 after 4 epochs without finality (prysm:beacon-chain/cache/committee.go:23-30; blockchain/receive_block.go:38, 548-560), each holding shuffled + sorted indices (cache/committees.go:14-19; 16 MB at 10⁶, sim). On top of that, a checkpoint-state cache of 10 full states (cache/checkpoint_state.go:16-19).

**Validator-client `dependent_root`.** FG duties for epoch E — committee size, bit position, and an aggregator-selection modulus if Lane B keeps today's `len(committee)`-based one — depend on **D(E) = block root at slot `start(E − 4) − 1`**. They can be served from `start(E − 4)`, which is 4 epochs ahead (25.6 min at 12 s, against 1 epoch today; sim), and they are final once D(E) is finalized.

For E = current + 4, D(E) is the block root at `start(current) − 1`. That is the root VCs already track as the pre-Fulu proposer dependent root (prysm:rpc/core/duties.go:288-303). Under striping, cohort and subnet for any future round need no root at all.

## 5. Grounding: what R removes from the failure class

- **Prysm today.** `getAttPreState` (prysm:beacon-chain/blockchain/process_attestation_helpers.go:94-165) tries, in order:
  1. the head state, if the target is recent and its dependent root matches the head's (23-90). This is 6735c921f8, "Dependent root instead of target", and f938da99d9, which extends it to previous-epoch targets because "this guarantees that both seed and active validator indices are guaranteed to be the same at the checkpoint's epoch";
  2. the 10-entry checkpoint-state cache;
  3. the next-slot cache;
  4. a refusal for non-viable checkpoints (132-139);
  5. otherwise **state regeneration plus `process_slots` to the epoch start** (141-155).

  The spec's own fork choice does the same (cs:phase0/fork-choice.md:771-777, 893-907).
- **May 2023** (ethresearch 15871:34-36, 105-106, 114). Valid-but-old targets forced state recomputation to check committee membership. The devnet reproduction used Hydra nodes that attested with random unfinalized blocks advanced by skipped slots.
- **Holesky 2025.** Prysm saw identical attestation data with different committee lengths, i.e. `AttestationTargetState(data.Target)` returning different states (R&D consensus-dev/2025-03-10 radekkapka 16:49). Nimbus had a shuffling bug "when the block that's being voted for is far behind the target (>2 epochs) and we have to replay many empty slots" (arnetheduck 20:06). Both appeared only during chain splits (R&D consensus-dev/2025-03-11 radekkapka 10:03).
- **What R removes:**
  1. No seed, so the dependency moves from E − 2 to E − 5. Every fork shallower than four epochs shares the set, which covers every fork on a DC chain with finality lag ≤ 129 slots. Hydra-style votes on side branches cost a set lookup at most, and non-viable targets are IGNOREd at rule 6.
  2. No checkpoint state and no `process_slots` through empty epochs for validation. Sets come from the head state, four epochs ahead.
  3. Committee lengths are a pure function of (E, D(E)) and membership, so two nodes with the same key cannot disagree — the Holesky symptom.
  4. Aggregates name their key. A mismatch becomes IGNORE instead of misdecode → REJECT → peer-score loss (cf. the peer drops in 15871:70-76).
- **What remains:** STF processing of a block still needs its parent state, as it does today (FF msg 1503), and deep forks during long non-finality need one extra set per branch and epoch (~4 MB, deltas ≤ 93 indices). This is FF msg 1526's point: the trouble is the dependent state, not shuffling per se.

## 6. What `sim/anchor_check.py` checks

It is a scaled-down, line-cited transcription of the Electra/Gloas/DC lifecycle paths:
- exit and consolidation churn (EIP-8061 mode, matching DC:1053);
- `initiate_validator_exit`, `slash_validator`;
- the Electra `process_registry_updates`;
- the DC `process_pending_deposits` with postponement;
- `process_pending_consolidations`, effective-balance hysteresis;
- EIP-6914 `get_index_for_new_validator`.

The scenario is a 12,000-entry registry (9.06M ETH active, churn 256/276/138 ETH per epoch), evolved through epochs `E0 = 70,000 … E0 + 20` with the four branches of §2.3. The checks:
- H2, by diffing snapshots;
- R's invariance and cross-branch identity;
- O2a's identity and the FF msg 1589 variant's divergence;
- the four O4 counterexamples and the poison bit;
- EIP-6914 scope;
- the (E, D) keying;
- genesis.

It also prints the mainnet-scale arithmetic quoted above: churn at 36M ETH, O5 lag costs, O1 waste from the cited registry counts, cache sizes, and the finality-lag threshold. `RESULT: PASS`. The run is deterministic; repeated runs produce byte-identical output.

## Open issues

1. **Lane B:** the envelope field (+32 B per aggregate), and whether aggregator selection keeps a committee-size modulus, which would need (E, D(E)).
2. **Lane A:** raw-index striping lets an operator choose cohorts by deposit order, selective exits or consolidation-target choice (H3). Era-hash needs a seed fixed at or before D(era start). Heavy-first ordering by effective balance *as of the D(E) state* is anchored and hence state-free in this sense, but it reshuffles positions every epoch as balances move — to be costed against Barnabé's gain (FF msg 1498).
3. **DC draft fixes:**
   - `is_eligible_for_activation` / `is_active_builder` read the frozen `finalized_checkpoint` (§1.4);
   - the poison-bit rejection (DC:714-718);
   - the missing aggregation-bits length check;
   - the activation-churn helper comes from EIP-8061, not yet in the specs mirror.
4. **Slashed voters' dead bits** last for the whole exit queue. Removing them at layout level would need a recorded slash epoch, since `slashed` alone is not delayed. Not recommended unless mass-slashing scenarios matter for bitfield size.
5. **EIP-6914 adoption:** the voting window is safe, but every index-keyed client cache — pubkeys, the R set's pubkey view, equivocators — must be reuse-aware, and reuse is a branch-dependent event.
