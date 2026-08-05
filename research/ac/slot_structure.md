# AC Slot Structure — Goldfish + view-merge, with ePBS / FOCIL / heartbeat

**Scope.** AC-slot phases, deadlines, in-slot message budget. Picks up the "new document in progress" Yann flagged in `../deprecated/design_space.md` (Jan 2026), and addresses open question P1 (`open_questions.md`): *"How does Goldfish view-merge change slot duration and structure (together with ePBS & FOCIL)?"*

The FG round is referenced, not specified: heartbeat votes ride `ACAttestation`s of AC-committee members, and `SLOTS_PER_ROUND` ties round to slot, but FG-round internals (vote kinds, notarization/finalization, healing) belong in `fg/`.

**Cites used throughout** (no restatement; pin to section):
- `projects/dc/consensus/Decoupled consensus.md` — §Goldfish, §View-merge with equivocations, Appendix §Confirmation rule, Appendix §Goldfish committee selection (VRF).
- `projects/dc/consensus/spec_notes.md` — §Overview (clocks), §Voting (attestation schema), §Accountable liveness; (only FIN-VOTE-side fields are slashable).
- `../deprecated/design_space.md` (AC vote = k-to-all, k ∈ [256, 2048]; FG vote = all-to-all; ~250 ms Δ; ~1 s slot).
- ePBS Gloas (proposer-bid → builder-reveal → PTC → aggregate); FOCIL (per-slot IL committee, fork-choice-enforced).

---

## 1. TL;DR

One slot = **4Δ** wall-clock (Δ = 250 ms ⇒ **1 s slot**; 1.25 s acceptable at 300 ms p99 RTT). The slot is layered, not stretched: Goldfish, ePBS, and FOCIL share the same four phase boundaries.

```
   T=0Δ          T=Δ            T=2Δ            T=3Δ          T=4Δ
   PROPOSE       VOTE           FAST-CONFIRM    FREEZE        (= 0Δ of n+1)
   block         AC-cmte vote   payload-timely  view cutoff
   builder bid   builder reveal IL for slot n+1
```

**Heartbeat = AC-committee member's `ACAttestation`** at T=Δ. AC committee size k ∈ [256, 2048] (target 512), VRF-selected per slot per `Decoupled consensus.md` Appendix §Goldfish committee selection (VRF). Other N−k validators emit no AC-side message in slot n; their FG vote (all-to-all per `../deprecated/design_space.md`) is dispatched separately by the FG p2p layer (`../deprecated/designs/`).

**`ACAttestation` carries** (`spec_notes.md` §Voting schema + this doc's additions):
- `Target: Checkpoint(slot, root)` — FG target for current round (spec_notes.md).
- `finalize_target: Root`, `finalize_height: uint64` — optional FG finalize piggyback (spec_notes.md).
- `goldfish_target: Root` — canonical head per Goldfish fork-choice. *Added here.*
- `ptc_payload_timely: bool` — 1 bit, PTC role folded in. *Added here.*

One BLS signature, one wire message. Slashing scope unchanged: only the `finalize_*` fields (FIN-VOTE) are slashable; `Target` / `goldfish_target` / `ptc_payload_timely` are not.

**FG round** = `SLOTS_PER_ROUND` consecutive AC slots (tentative 32 ⇒ 32 s round at 1 s slots). Round boundary = slot boundary; round progression is in-state (`spec_notes.md` §Beacon State: height processing).

---

## 2. Parameters

| Param | Value | Range | Notes |
|---|---|---|---|
| `Δ` | 250 ms | 150–400 ms | `../deprecated/design_space.md` |
| `SLOT_DURATION = 4·Δ` | **1.0 s** | 0.75 s (3Δ, no fast-confirm) – 1.25 s (4·312 ms or 5·250 ms, p99 tail) | this doc |
| `T_PROPOSE / T_VOTE / T_CONFIRM / T_FREEZE` | 0 / 1 / 2 / 3 · Δ | — | this doc |
| `AC_COMMITTEE_SIZE` (renames `TARGET_COMMITTEE_SIZE`) | 512 | 256–2048 | independent of N; sampled fresh per slot |
| `FAST_CONFIRM_THRESHOLD` | 3/4 + ε | exact 3/4 of `AC_COMMITTEE_SIZE` | `Decoupled consensus.md` Appendix §Confirmation rule; ε for committee-size variance |
| `EPBS_REVEAL_DEADLINE` | T_VOTE | — | miss ⇒ `ptc_payload_timely = 0` |
| `FOCIL_IL_PUBLISH` | T_CONFIRM of slot *n* (publishes IL for slot *n+1*) | T_CONFIRM – T_FREEZE | gives slot *n+1* proposer Δ to receive |
| `SLOTS_PER_ROUND` | 32 (tentative) | fork-tunable | locked once `fg/` is specced; derived from FG-round budget ÷ `SLOT_DURATION` |

Timing is parameterized by `Δ`; `AC_COMMITTEE_SIZE` and `SLOTS_PER_ROUND` are independent axes.

---

## 3. Slot timeline (phase × role)

| Phase | Goldfish | ePBS | FOCIL |
|---|---|---|---|
| **0Δ — PROPOSE** | Slot-*n* proposer publishes block with view-merged slot-*(n−1)* AC votes and the current FG round-*r* `Target` accumulator. | Block carries `ExecutionPayloadHeader` (builder bid, no payload yet). | Block extends with txs from IL received at T_CONFIRM of slot *n−1*; omitting IL ⇒ filtered by `get_head`. |
| **Δ — VOTE** | AC committee (k=512, VRF) fires one `ACAttestation` each. Pattern: k-to-all. Carries the four fields in §1. | Builder reveals execution payload by this deadline; miss ⇒ committee sets `ptc_payload_timely = 0`. | — |
| **2Δ — FAST-CONFIRM** | Local-only: if ≥ `FAST_CONFIRM_THRESHOLD` votes seen on head, fast-confirm. No wire message. See `Decoupled consensus.md` Appendix §Confirmation rule. | PTC bit already in `ACAttestation` from T=Δ; aggregated off-the-wire by next proposer. No separate PTC topic. | IL committee for slot *n+1* publishes on `focil_inclusion_list`. |
| **3Δ — FREEZE** | View cutoff for slot-*n* vote tally. Late votes only enter via `from_block` at slot-*n+1* proposer (one more Δ). Equivocator-handling rules from `Decoupled consensus.md` §View-merge with equivocations apply unchanged. | — | — |

**Heartbeat semantics.** Validators on the AC committee for slot *n* emit exactly one `ACAttestation`; off-committee validators emit nothing AC-side that slot — their FG vote goes through the FG p2p layer (`../deprecated/designs/`) once per round, not once per slot. Inactivity-leak accounting (`spec_notes.md` §Accountable liveness) keys on FG-vote presence per round, so an unlucky validator that doesn't land on an AC committee in a given round is not penalized.

**View-merge guarantee (the 3Δ-budget argument — new to this doc).** Votes fired at T_VOTE = Δ have 2Δ until T_FREEZE = 3Δ to propagate to all honest committee members. The slot-*n+1* proposer keeps updating its vote record until T_PROPOSE = 4Δ — one extra Δ to catch late arrivals, then including them in its block (where other nodes accept them via `from_block`). The standard Goldfish synchrony property (`Decoupled consensus.md` §Goldfish: under synchrony, an honest proposer's block is voted by all honest committee members) holds iff slot ≥ 4Δ. The freeze cutoff at 3Δ is the load-bearing piece; FG `Target` votes inherit the same property because they ride inside `ACAttestation`.

---

## 4. AC committee selection

VRF-keyed, stake-proportional with remainder-random, as specified verbatim in `Decoupled consensus.md` Appendix §Goldfish committee selection (VRF). This doc renames `TARGET_COMMITTEE_SIZE` → `AC_COMMITTEE_SIZE`; the function is otherwise identical.

`AC_COMMITTEE_SIZE = 512` is a target, not a function of N. The committee is sampled fresh per slot — no requirement that every active validator land on an AC committee in every round. FG vote dissemination is what scales with N, and it lives in the FG p2p layer.

Secrecy follows the existing Eth aggregator-selection model: committee membership is revealed only when the validator emits `ACAttestation` at T=Δ, protecting against adaptive bribing / DoS through T_VOTE − ε.

---

## 5. FOCIL integration

IL committee for slot *n+1* fires at `T_CONFIRM` of slot *n* on `focil_inclusion_list`. Slot-*n+1* proposer has Δ to receive — sufficient under the 250 ms model; if Δ stretches past 300 ms, move publish earlier (T_VOTE of *n*) to preserve ≥ Δ propagation.

**Committee disjoint vs shared.** Disjoint (separate VRF roll from AC committee) is cleaner; shared (AC-committee members for slot *n* also publish IL at T_CONFIRM) saves one VRF roll per slot. Bandwidth delta if disjoint: ≈ `AC_COMMITTEE_SIZE · 96 B = 50 kB / slot`. Open question — see §8 Q4.

Fork-choice enforcement is fork-choice-level; no slot-timing change here.

---

## 6. ePBS integration

| ePBS phase | This-doc phase |
|---|---|
| Proposer bid | T_PROPOSE — block carries `ExecutionPayloadHeader`, not payload |
| Builder reveal | T_VOTE — deadline for `ptc_payload_timely = 1` |
| PTC vote | T_CONFIRM — **no new wire message**; bit rides `ACAttestation` from T=Δ |
| Aggregate | Next proposer's view-merge at T_PROPOSE of *n+1* |

**PTC absorption into AC committee.** Both are per-slot, similar size (PTC ~512 in Gloas; `AC_COMMITTEE_SIZE = 512`), observe the same fact (payload-on-time) by the same deadline. Folding the bit into `ACAttestation` saves one gossip topic per slot — material at 1 s slot scale. The cost: Gloas's committee-separation argument (independent committees ⇒ adaptive-bribing resistance) is sacrificed. Whether the merged committee preserves the security argument is open (§8 Q3).

Builder-reveal failure: aggregated `ptc_payload_timely = 0` quorum < threshold ⇒ next proposer drops the unrevealed payload (standard ePBS reorg).

---

## 7. Wire delta vs current Gloas

Drop `ptc_attestation` (folded into `ac_attestation`). Tighten the `execution_payload` reveal deadline to T_VOTE. Replace 64 `beacon_attestation_{subnet_id}` topics with one `ac_attestation` topic carrying the merged Goldfish + FG + PTC vote (committee-side; full-validator FG dissemination is on the FG p2p layer). Add `focil_inclusion_list`. `SECONDS_PER_SLOT: 1` (was 12); `MAX_ATTESTATIONS_PER_BLOCK` scales with `SLOTS_PER_ROUND`.

---

## 8. Open questions

1. **Δ tail.** p99 wide-area RTT ≈ 300 ms ⇒ 4Δ = 1.2 s. Either accept a 1.25 s slot (4·312 ms or 5·250 ms) or accept that p99-tail validators occasionally miss FAST-CONFIRM. Prefer the former.
2. **Fast-confirm threshold ε.** Goldfish appendix uses 3/4; the "+ ε" needs a Hoeffding tail bound once `AC_COMMITTEE_SIZE` is fixed, parallel to today's sync-committee thresholding. *TODO doc:* a `notes/` write-up.
3. **PTC-AC merge safety.** §6 is a tradeoff, not a decision — the merge gives up Gloas's independent-committee adaptive-bribing resistance. Needs a formal argument before this becomes a spec PR. *TODO doc:* a `notes/` write-up.
4. **FOCIL committee disjointness.** ≈ 50 kB / slot bandwidth cost if disjoint (§5); the real tradeoff is adversary-model coupling, not bandwidth. Decide before the FOCIL fork.
5. **Builder-reveal pre-emption.** Honest committee members MUST wait until T_VOTE wall-clock to fire `ACAttestation`, even if payload arrived earlier — otherwise propagation drops below 2Δ and view-merge breaks. Make explicit in spec text.
6. **`SLOTS_PER_ROUND` rotation at fork boundary.** Every node must agree on the last slot of the pre-fork round. Solvable with a `ROUND_BOUNDARY_FORK_EPOCH` constant.
7. **Missed-proposer slots.** Missed-proposer rate scales with `1 / SLOT_DURATION`; view-merge still works (next proposer merges the missed-slot view), but heartbeat-presence statistics should not blame the missing-slot's committee.
