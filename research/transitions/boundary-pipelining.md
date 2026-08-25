---
title: Boundary pipelining — does the justification dependency stall slot-0 votes?
status: wip
provenance: agent
---

> **Provenance: agent** — 2026-08-25, produced by a 5-agent workflow (spec
> reader over the simplex-healing spec + healing tex, BFT-precedent verifier,
> timing analyst, and two adversarial refuters at high effort). Spec claims
> carry file:line cites; verify before citing externally.

# Does the justification dependency break cross-boundary pipelining?

**Objection (Yann, 2026-08-25):** duty *assignment* can be given lookahead
([survey](survey.md)), but the vote's dependency on the previous height's
justification cannot — at slot 0 of a round, the vote seemingly has to wait
for the *on-chain processing* of the previous round's justification, so
voting cannot be pipelined across the boundary.

## Verdict

The premise is half-right and the conclusion doesn't follow. The current
design (simplex-healing spec + `height_filter_healing.tex`) **is**
state-gated — votes count only via block inclusion, and there is no
certificate object at all — but pipelining survives because the wait is
engineered at **round granularity** with an explicit boundary handoff:

- zero bubble for participation **p ≥ 16/21 ≈ 76.2%** (block-dependent) and
  **p ≥ 8/9 ≈ 88.9%** (robust even to a missed round-start block);
- below 76.2%, the cost is **one round of height latency, not a stall**:
  the new round harmlessly re-votes the old height (idempotent bits), and
  the height advances a round later;
- the tempting fix — gate on a network-observable certificate,
  CometBFT/HotStuff-style — is **the wrong mechanism for DC**: unnecessary
  in the common case, insufficient in the tail, and unsafe if extended
  beyond exact-target justification certificates (it breaks the
  accountable-safety proof; see below).

The real casualty is the **"vote in the previous slot" variant**: under the
round-freeze discipline it needs p ≥ 88.9% *and* a timely last-slot block —
effectively broken. Voting at slot 0, T = 4+X is fine.

## Ground truth: what the current spec actually gates on

(`ethereum/fradamt-consensus-specs/specs/_features/simplex/`, HEAD `5750e57`,
and `projects/finality-gadgets/height_filter_healing.tex`.)

1. **No certificate objects.** The state processes *included votes*:
   `advance_height` fires inside `process_justification_and_finalization`
   when `target_participation` / `timeouts` bitlists reach 2/3
   (`beacon-chain.md:1474–1487`); bitlists are populated only by
   `process_attestation` (`:2288–2295`). Certificates in the tex are
   *derived proofs*, not causal: "a certificate proves what cumulative
   included attestations already made the state machine do"
   (`height_filter_healing.tex:945–965`).
2. **Round-granularity freeze.** All eight cohorts freeze their FG fields
   (height, target, finality pair) at the round's first-slot deadline, from
   the selected head state advanced locally to the current slot
   (`validator.md`, `freeze_round_vote`; tex Def. *finality action state*,
   `:872–874`). A missed deadline does not authorize late reconstruction.
   So the boundary question arises **once per round**, not per slot.
3. **The handoff is explicitly engineered.** Heights "become due at round
   boundaries and advance when the due outcome is consumed after its
   one-slot operation-inclusion opportunity" (`beacon-chain.md:190–196`) —
   the last round's final-cohort votes get the *next round's first block*
   as an inclusion slot — and **an empty slot settles the advance**
   (`beacon-chain.md:1880–1886`; tex Lemma *empty-slot-noop*): once the
   quorum votes are included, no further block is needed.
4. **Heights are decoupled from rounds.** Participation bitlists persist
   across rounds until the height advances (`beacon-chain.md:1907–1914`); a
   validator frozen at the old height keeps casting valid, countable votes.
   A vote is never *invalidated* by the boundary — there is **no source
   field** in the vote at all (unlike Casper FFG), so no validity coupling.
5. **Caveat from the spec itself:** the executable round schedule and its
   timing/incentive proof are acknowledged open obligations
   (`beacon-chain.md:169–186`); the 8-cohort/aggregate/include timeline is a
   networking-layer construct that appears in no consensus source — the
   analysis below supplies exactly that missing timing argument.

## Timing arithmetic

Model: cohort k votes slot k at T=4+X; aggregates publish slot k+1, T=8s;
included in slot k+2 (block delivered δ ∈ {2,4} s). Round r starts slot 8;
its freeze deadline is slot 8, T≈4s. Quorum-completing cohort
k\* = ⌈16/(3p)⌉ − 1:

| participation p | k\* | quorum included by | state reads new height at | bubble |
|---|---|---|---|---|
| ≥ 8/9 ≈ 88.9% | 5 | slot 7 block (old round) | slot 8, T=0 — **empty-slot settlement, no block needed** | 0 |
| [16/21, 8/9) ≈ 76.2–88.9% | 6 | **slot 8 block = round-start block** | slot 8, T=δ ≈ 2–4 s — margin vs freeze = 4+X−δ, razor-thin at X=0 | 0 (block-dependent) |
| [2/3, 16/21) ≈ 66.7–76.2% | 7 | slot 9 block | after the round-r freeze | **1 round** of height latency (round r re-votes h−1, idempotently) |
| < 2/3 | — | quorum impossible | timeout/leak path (in-state by construction) | moot |

Sensitivities: margins move 1:1 with X (each second of vote delay buys a
second); a missed round-start block demotes the 76.2–88.9% band to the
one-round-latency outcome; certificate-gating would improve only the
(k\*=7, X≥4) cell — see below for why it isn't worth it.

### The earlier-vote ladder (answers the original transition-timing question)

| vote time of the round's first cohort | zero-bubble requirement |
|---|---|
| slot 0, T = 4+X (current design) | p ≥ 76.2% (block-dep.) / p ≥ 88.9% (robust) |
| slot 0, T = 0 | p ≥ 88.9% (round-start block can no longer help) |
| previous slot (slot −1) | p ≥ 88.9% **and** timely slot-7 block — effectively broken |

## Why "gate on a network certificate" is the wrong fix

(This corrects the recommendation sketched in [survey.md](survey.md)'s
handoff section.) Three findings from the adversarial pass:

1. **Unnecessary in the common case.** The zero bubble at p ≥ 76.2% is
   achieved *by* on-chain processing (round-start block + empty-slot
   settlement). Early certificate observation buys nothing, because the new
   height's **target is the chain's first block at that height** — typically
   the round-start block itself (`height_filter_healing.tex:1029–1041`).
   You cannot cast a fresh target vote before the target exists, however
   early you saw the certificate.
2. **Insufficient in the tail.** In the k\*=7 band the certificate is
   observable at slot 8, T=8s — after the freeze deadline anyway unless
   X ≥ 4. And an observability-triggered round extension is state-gating in
   disguise: "no cert seen by deadline" is a negative event that is not
   common knowledge; nodes desynchronize on the round schedule unless the
   trigger is serialized (on-chain or an explicit timeout certificate).
3. **Unsafe beyond exact-target JCs.** The cross-height branch of the
   accountable-safety proof (tex Lemma *past-finalized*, `:1092–1137`) is
   load-bearing on inclusion-relativity: a target vote sets the progress bit
   only on chains where the finalized block is an ancestor of the including
   block's parent (`:487–503`). Make progress/timeout quorums
   network-consumable and an adversary can harvest honest height-h votes for
   C, replay them as a chain-agnostic progress certificate on a branch *not*
   containing C, and reach conflicting finalization **with zero slashable
   weight**. Inclusion is not bookkeeping there — it is the safety proof.
   Likewise, "inclusion as a trailing reward record" is false in this state
   machine: the finality tally P is counted on-chain against the prestate's
   latest unfinalized justification (`:474–478`, `:614–616`), so justification
   inclusion is a *prerequisite for counting FIN-votes* at the next height;
   late/batched inclusion shrinks the countable window (reset-P rule) toward
   systematic finality skips.

## BFT precedent, correctly read

No production BFT gates next-height *voting* on on-chain processing —
Tendermint starts H+1 on 2/3 precommits as messages; HotStuff carries the QC
inside the next proposal; GRANDPA rounds advance on "completability" of the
local vote set. **But in every one of them the on-chain record is mandatory
and exactly one block behind** (LastCommit is a validity condition of block
H+1; a proposal without its QC is invalid; GRANDPA pairs sparse
justifications with an enshrined catch-up/warp-sync layer). DC's
slot-(k+2) inclusion + one-slot spillover *is* that pattern. The cautionary
counter-model is Casper FFG: state-gated source at **epoch** granularity
with a source-equality validity condition — which is why justification can
land an epoch late. DC dodges FFG's sharp edges by having no source field,
idempotent per-validator bits, and round (not epoch) granularity.

## Open items

1. **Razor-thin k\*=6 margin** (4+X−δ at the round-start block): consider
   whether the round-start freeze deadline should sit later than T=4s, or
   whether X ≥ 2–4 s should be the recommended operating point; benchmark in
   the Shadow PoC ([poc.md](../../poc/poc.md)).
2. **Boundary griefing lever → Q15**: delaying (not censoring) the final
   cohort's aggregates by a few non-slashable seconds converts, at the
   boundary only, into loss of the first cohort's fresh-height weight
   (≤ 12.5%; bounded, non-cascading for p ≥ 76.2%).
3. **Participation floor as a networking requirement**: one-round-per-height
   justification needs ≥ 76.2% of stake's votes *delivered and included* by
   the boundary — a delivered-participation target for
   [requirements.md](../../design/requirements.md) ("networking must not be
   the binding fault bound").
4. **Slashability reconciliation with fradamt**: `height_filter_healing.tex`
   E1/E2 (`:505–520`) slash plain target votes; the "only FIN-VOTEs are
   slashable" rule is Majorum's. Which applies to DC's FG matters for how
   much authority derived certificates can ever carry.
5. **The spec's own open timing obligation** (`beacon-chain.md:169–186`):
   this note's arithmetic is an input to that proof, not a substitute.
