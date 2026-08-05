# AC Slot Structure — v2 (compact)

A one-page, visually-oriented companion to `slot_structure.md`. Same content, single-timeline layout. Defer to the full doc for arithmetic, open questions, and citations.

---

## The slot at a glance

```
   ┌─────────┐   ┌──────────┐   ┌──────────────┐   ┌─────────┐
   │ PROPOSE │   │   VOTE   │   │ FAST-CONFIRM │   │ FREEZE  │
   └────┬────┘   └─────┬────┘   └──────┬───────┘   └────┬────┘
        │              │               │                │
   ─────┴──────────────┴───────────────┴────────────────┴──────▶
       0Δ              Δ              2Δ              3Δ        4Δ
                                                                (= 0Δ of n+1)

   block          AC heartbeat    3/4 local quorum    view cutoff
   + builder bid  + payload       + IL for slot n+1   (slot n+1 has Δ
                    reveal        + PTC bit folded     to catch late votes)

  legend  ·  plain = Goldfish  ·  +builder/+payload/+PTC = ePBS  ·  +IL = FOCIL
```

Δ = 250 ms target ⇒ slot = 4Δ = **1 s** (1.25 s acceptable at 300 ms p99 RTT).

---

## Reading the diagram

- **Spine.** Four phases, one per Δ. The spine is pure Goldfish: PROPOSE → VOTE → FAST-CONFIRM → FREEZE. Same names as `../deprecated/design_space.md`; same boundaries `Decoupled consensus.md` Appendix §Confirmation rule uses for the fast-confirm proof.
- **Hooks.** Each `+` line is a non-Goldfish role tapping into the same phase. ePBS at PROPOSE / VOTE / FAST-CONFIRM (bid / reveal / PTC bit); FOCIL at FAST-CONFIRM (slot *n* publishes IL for slot *n+1*). No standalone phase for either — saves a wire round per slot.
- **Heartbeat = AC-committee attestation.** k = 512 validators (VRF per slot, `Decoupled consensus.md` Appendix §Goldfish committee selection) fire one `ACAttestation` at T=Δ. Off-committee validators emit nothing AC-side. The attestation carries (per `spec_notes.md` §Voting + this doc):

   ```
   ACAttestation {
       Target             : Checkpoint(slot, root)   # FG, spec_notes.md
       finalize_target    : Root          (optional) # FG, spec_notes.md
       finalize_height    : uint64        (optional) # FG, spec_notes.md
       goldfish_target    : Root                     # added here
       ptc_payload_timely : bool                     # added here
   }
   ```

   One BLS signature, one wire message. Only `finalize_*` is slashable.
- **View-merge.** Vote at Δ, propagate to 3Δ (2Δ budget), proposer of slot *n+1* gets one extra Δ to scoop late votes via `from_block`. The 3Δ freeze cutoff / 4Δ slot is necessary and sufficient at Δ = 250 ms.
- **FG round = `SLOTS_PER_ROUND` slots.** Tentative 32 ⇒ 32 s round at 1 s slots. Per-round FG vote accumulator advances in-state (`spec_notes.md` §Beacon State).

---

## Wire delta (one line)

Drop `ptc_attestation` (folded into `ac_attestation`); tighten `execution_payload` reveal deadline to T_VOTE; collapse 64 `beacon_attestation_{subnet_id}` topics into one `ac_attestation`; add `focil_inclusion_list`; `SECONDS_PER_SLOT: 1`.

---

## What this version omits

Everything else lives in `slot_structure.md`: parameters table, role-by-role phase semantics, committee selection details, ePBS / FOCIL integration arguments, view-merge derivation, open questions. v2 is for fast onboarding; v1 is the working spec.
