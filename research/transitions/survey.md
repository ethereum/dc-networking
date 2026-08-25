---
title: Cross-chain survey — epoch/height transition computation vs. vote timing
status: wip
provenance: agent
---

> **Provenance: agent** — compiled 2026-08-25 from primary sources (specs,
> client code, post-mortems) by research agents; per-chain claims carry their
> source links. Not yet reviewed line-by-line.

# How other chains schedule transition computation

Question ([README](README.md)): DC sends FG votes early in the slot (X→0, or
even the previous slot), leaving no time for epoch/height-transition
computation. Do other chains (a) leave a gap at the boundary, (b) freeze
inputs early (lookahead), (c) spread/defer the computation, or (d) precompute
speculatively — and what happened when they got it wrong?

## Comparison table

| Chain | Duty/leader inputs frozen | Boundary gap? | Heavy work spread? |
|---|---|---|---|
| Ethereum today | committees: 1 epoch (`MIN_SEED_LOOKAHEAD`); proposer: was 0, now 1+ epoch (EIP-7917) | no — clients precompute in slot-31 idle tail | partially — single-pass epoch processing (LH tree-states); 7917 adds boundary work for determinism |
| Polkadot | duties: 1 epoch (4 h); randomness: 2 epochs; election: done 4-6 h early | no — boundary block is O(n) copying; GRANDPA handoff gated on finality of boundary block | yes — election phased over hours, now on another chain; rewards lazy |
| Cardano | stake: 1 epoch (5 d); nonce: 36–48 h | no — schedule known days ahead | yes — reward "pulsing", boundary tick dispersed (8.1.1) |
| Solana | 1 full epoch (~2 d, `leader_schedule_slot_offset`) | no by design; de-facto slow first block pre-2024 | yes — SIMD-0118 partitioned rewards (4096 accts/block); EAH pinned to 25–75% of epoch |
| CometBFT/Cosmos | H+2 rule: set from block H active at H+2 (1-block mandatory lookahead) | no — atomic swap between heights | n/a (app-side; ADR-039 proposed epoching to amortize DKG) |
| Aptos | boundary applies queued changes; DKG for epoch e+1 runs *during* e | no — only set-*changes* freeze ≤30 s; tens-of-ms e2e overhead | yes — async two-phase reconfiguration (AIP-79) |
| Sui | stake/committee accumulate all epoch, apply in change-epoch tx; new committee pre-syncs state (READY) | **yes — deliberate pause**, "the only fully synchronous event"; ~100s of ms (Mysticeti) | partially — 4-step pipelined handoff (Sui Lutris) |
| Algorand | seed: 2 rounds; stake: 320 rounds (~15 min) | no boundary exists | n/a — O(1) per-round sortition |
| NEAR | 1 full epoch (set for T+1 fixed at end of T−1) | no — boundary is a pointer swap | yes — lookahead epoch = background provisioning window |
| Monad | n/a (execution, not duties) | no | yes — execution deferred D=3 blocks behind voting |
| Avalanche | epoched views (ACP-181, 2025): frozen per-epoch P-chain height | no | n/a |

## Cardano (Ouroboros Praos)

**Boundary computation.** The `NEWEPOCH`/`TICK` transition rotates the three
stake snapshots (**mark → set → go**), *applies* the pre-computed reward
update, processes pool retirements/parameter updates, and aggregates per-pool
stake (`calculatePoolDistr`). The ledger team's own tracker states the design
principle: *"Large computations on the epoch boundary are problematic and have
in the past led to delayed block production in new epochs"*
([cardano-ledger #3034](https://github.com/IntersectMBO/cardano-ledger/issues/3034)).

**Input freeze & lookahead.** Leader eligibility for epoch N uses the stake
snapshot frozen at the start of epoch N−1 — one full epoch (5 days) ahead
(snapshot at boundary e/e+1 → leader election in e+2, rewards in e+3). The
epoch nonce stops evolving one *stability window* before the epoch: 3k/f =
129,600 slots = 36 h historically, moved to 4k/f = 48 h in Conway
([ouroboros-consensus PR #927](https://github.com/IntersectMBO/ouroboros-consensus/pull/927)).
Every SPO computes its full private leader schedule for epoch N **1.5–2 days
before N starts** (`cncli leaderlog --ledger-set next` is routine practice).

**Critical path & gaps.** Protocol-wise nothing at the boundary gates block
production — header validation is *forecastable* a stability window ahead.
The gaps were purely implementation: the synchronous boundary tick stalled
nodes seconds-to-minutes → missed slot-leader checks at boundaries.

**Spreading & precompute.** Rewards for epoch e are computed *during* e+1.
Originally a monolithic job starting at epoch+48h; re-engineered (~node
1.26.1, Mar 2021) as a **pulser** (`PulsingRewUpdate`): chunked and
interleaved with normal block processing, finishing before the next boundary
where the result is merely applied
([cardano-node #2205](https://github.com/input-output-hk/cardano-node/issues/2205)).
Node 8.1.1 (Jun 2023) additionally "disperses epoch boundary computations
throughout the entire epoch."

**Incidents.**
- Dec 2020: monolithic reward calc start froze the whole network ~2.5 min;
  blocks scheduled in the window were lost; fixed in 1.21.1, regressed in
  1.23.0 ([#2205](https://github.com/input-output-hk/cardano-node/issues/2205),
  [#2408](https://github.com/IntersectMBO/cardano-node/issues/2408)).
- Oct 2021: even *after* pulsing, incremental chunks on the node's hot path
  caused missed leader checks and ~24 h elevated propagation delay (GC spikes)
  ([#3167](https://github.com/IntersectMBO/cardano-node/issues/3167),
  [#3392](https://github.com/input-output-hk/cardano-node/issues/3392)) —
  amortization helps only if the work also stays off the critical thread.
- Boundary missed slots remained SPO folklore until the 8.x dispersal work
  ([#2526](https://github.com/IntersectMBO/cardano-node/issues/2526)).

## Solana

**Boundary computation.** First bank of the epoch: new leader schedule (cheap,
inputs frozen an epoch earlier), stake activations/deactivations, vote-account
rewards (~1.5k accounts); pre-2024 also **all ~550k stake-account rewards in
that one block**.

**Input freeze & lookahead.** Leader schedule for epoch N is computed from the
bank state at the start of epoch N−1: `DEFAULT_LEADER_SCHEDULE_SLOT_OFFSET =
432_000` slots = exactly one full epoch (~2 days)
([Agave leader-rotation docs](https://docs.anza.xyz/consensus/leader-rotation)).
All 432,000 slot assignments are public a whole epoch ahead. Stake changes
take effect only at boundaries with warmup/cooldown capped at **9%/epoch** —
explicitly so the epoch-ahead schedule stays valid, plus a security argument:
the active set is sampled over a long window across many leaders so no single
leader can bias it by censoring vote transactions.

**Critical path & gaps.** No duty recomputation at the boundary; the gap was
the first block's O(all stake accounts) reward writes — a documented
skip-rate hotspot every ~2 days
([SIMD-0118 motivation](https://github.com/solana-foundation/solana-improvement-documents/blob/main/proposals/0118-partitioned-epoch-reward-distribution.md)).

**Spreading & precompute.**
- **SIMD-0118 partitioned epoch rewards** (mainnet epoch 707, late 2024):
  block 1 computes and schedules; from block 2, **4,096 stake rewards per
  block** over M blocks (≤10% of the epoch), tracked by an `EpochRewards`
  sysvar; stake mutations frozen during distribution.
- **Epoch Accounts Hash**: the once-per-epoch full accounts hash (~15 s) is
  deliberately scheduled to run from 25% to 75% of the epoch — *"Do not start
  the EAH calculation at the beginning of an epoch, as the beginning of an
  epoch is already a time of contention and stress"*
  ([EAH proposal](https://docs.anza.xyz/implemented-proposals/epoch_accounts_hash)).

**Voting across the boundary.** Tower BFT votes are ordinary on-chain
transactions; no protocol pause at boundaries — but since votes land only in
blocks, the slow first block *de facto* delayed vote landing at every
boundary. SIMD-0118 removed exactly that coupling of consensus liveness to
boundary-block compute.

## Polkadot (BABE + GRANDPA)

*The closest structural analogue: GRANDPA is a decoupled finality gadget
running beside BABE block production. Slots 6 s; epoch = session = 4 h;
era = 6 sessions = 24 h.*

**Input freeze & lookahead — everything is pipelined ≥1 period.**
- BABE randomness for epoch N: inputs frozen at end of epoch N−2, public at
  start of N−1 ("randomness from two epochs ago", `frame/babe/randomness.rs`).
- BABE authorities + leadership for epoch N: announced in the **first block of
  epoch N−1** (`NextEpochDescriptor` digest) — a full epoch (4 h) ahead.
- Session keys (`set_keys`): active in the session after next.
- Era validator set: nomination snapshot frozen ~6 h before the era; the NPoS
  election (Phragmén) runs signed phase (1 h) → unsigned phase (1 h) →
  `elect()` at the start of the *last* session — done 4 h before activation,
  then queued. Since Nov 2025 the election is multi-block and runs on Asset
  Hub, off the relay chain entirely.
- Sassafras/SAFROLE: tickets for epoch N generated in N−2, on-chain in N−1,
  frozen ≥100 slots (10 min) before the boundary ("epoch tail", RFC-0026) —
  even the anonymous-leader design inserts a deliberate dead zone between
  input freeze and duty start.

**Boundary computation.** The boundary block does O(validators) copying and
one hash chain — trivially cheap. Reward payouts are lazy (pull-based
transactions). Nothing a validator needs at slot 0 of epoch N is computed at
the N−1/N boundary.

**GRANDPA authority handoff — on the gadget's own clock.** The session
boundary block schedules the authority change with delay 0, but it *activates
only when that block is finalized*: "pending changes are applied after a delay
of *finalized* blocks" (`sp_consensus_grandpa::ConsensusLog`), with a client
voting rule forbidding votes past the activation point until it's final.
Votes are domain-separated by (message, round, **set_id**), so old/new-set
votes are unmixable; the new set picks up from the handoff block, in-flight
old rounds beyond it are pruned. Happy path: ~1 finalization round (~12-18 s),
invisible. Failure mode: the handoff is finality-gated, so a finality stall
self-extends across the boundary — the escape hatch is `on_stalled` +
**forced changes** (delay counted in *imported* blocks). Block production
never waits: BABE produces straight through any GRANDPA stall.

**Networking notice.** The parachain grid topology (O(√n)) is recomputed per
session from data known a session ahead, and gossip-support **pre-connects to
next-session authorities ~4 h early**. GRANDPA itself needs no topology
change at handoff (all authorities gossip all votes on one protocol; the set
swap propagates as a single set-id). Even with 4 h of notice, *newly
activated* validators demonstrably miss votes in their first minutes because
connections aren't warm (polkadot-sdk #11338).

**Incidents.**
- **Kusama era-boundary stalls (2020)** — the canonical one: on-chain
  Phragmén at era end blew the ~2 s execution budget; "validators were
  seemingly missing their slots." Fix: off-chain workers (substrate #4517, at
  the cost of freezing nominations in the last epoch), then the multi-phase
  election, then off-chain-chain entirely. Boundary-synchronous
  O(validators×nominators) work collides with slot deadlines — every fix
  bought more lookahead/spreading, never a faster boundary.
- **Polkadot finality lag (2024-09-17)**: PVF recompilation after a runtime
  upgrade — all-validators-simultaneous compute spikes surface as finality
  lag even without an epoch boundary.
- Kusama 2024-02-15: ~1 h GRANDPA stall (dispute logic) while BABE kept
  producing — the decoupling works as designed.

## CometBFT / Cosmos

**No epochs; a mandatory one-block lookahead.** The app returns
`validator_updates` from `FinalizeBlock` every height, but the ABCI rule is:
updates returned after block H **take effect at H+2**
([ABCI++ app requirements](https://github.com/cometbft/cometbft/blob/main/spec/abci/abci%2B%2B_app_requirements.md)).
Structural reason: the header carries `ValidatorsHash` *and*
`NextValidatorsHash`; H's execution results are known only after H commits, so
the earliest header committing to the new set is H+1's next-hash → active at
H+2. Designed for light clients (a signed header alone proves the next
signing set), with the side effect that matters here: **when a node enters
height H+1, the full voting roster and proposer are already fixed and locally
known. Duty assignment is never computed inside the height that uses it.**
No pause, ever, for set changes; run since genesis-era Tendermint across
thousands of chains without incident.

**ADR-039 epoched staking** (proposed, unmerged; Babylon implemented its own):
buffer staking updates into epochs to amortize per-set-change work (DKG, IBC
proof size) — and explicitly pipelined: "when we are in epoch N, the epoch
N+1 weights [are] to be fixed", so the DKG for N+1 runs during N.

## Aptos (DiemBFT/Jolteon)

**Epoch change as a self-certifying handoff; heavy work moved off the
boundary.** Epochs (2 h) end with a reconfiguration transaction; per LibraBFT,
blocks extending it carry no payload — a protocol-blessed *payload-free*
suffix (dead capacity, not dead time). Everyone follows via the
`EpochChangeProof`: a chain of 2f+1-signed epoch-final LedgerInfos each
carrying the next validator set — new validators, laggards, light clients
ratchet with no out-of-band trust.

When on-chain randomness (AIP-79) made the boundary *heavier* — a
whole-committee weighted-PVSS DKG for the next epoch's keys — Aptos made
reconfiguration **asynchronous/two-phase** instead of pausing: "If the DKG
starts after the epoch change, it is too late." `try_start` freezes
*validator-set changes* (≤30 s input freeze) and the epoch-e committee runs
the DKG off-chain **while the old epoch keeps processing transactions**; only
then does `finish` enter the new epoch
([reconfiguration_with_dkg.move](https://github.com/aptos-labs/aptos-core/blob/main/aptos-move/framework/aptos-framework/sources/reconfiguration_with_dkg.move)).
Measured cost of the heaviest known boundary work: "tens of milliseconds" of
e2e latency. **Freeze inputs, not consensus.**

## Sui (Narwhal/Bullshark → Mysticeti)

**The one deliberate boundary pause — cheap median, expensive tail.** Epochs
~24 h; the boundary batches everything (drain transactions/checkpoints,
distribute rewards, apply stake + committee change, optional protocol-version
flip, DKG) and is, per Sui's own docs, **"the only fully synchronous event in
the network."** The pause is forced not by rewards math but by the
consensusless fast path: owned-object locks drop across epochs, so every
fast-path effect must provably land before the old committee lets go (2f+1
End-of-Epoch attestations). Sui Lutris pipelines the handoff (stake fixed S
checkpoints early; the *next* committee pre-syncs state and signals READY
before taking over) to get the pause down to "a few seconds"
(Bullshark) / "a few hundred milliseconds" (Mysticeti), hidden by automatic
client retries.

**Incidents — tail risk concentrates at the synchronous point.** Nov 2024
(first mainnet outage, ~2.5 h): a crash armed by a protocol-version flip,
which activates at epoch boundaries — simultaneously on every validator.
May 2026 (~16 h across three halts): a **scheduled epoch change failed to
complete** (DKG failure verdict never persisted); recovery required shipping
a coordinated force-close-the-epoch mechanism
([post-mortem](https://www.sui.io/blog/sui-mainnet-halts-resolved-after-major-upgrade)).
A synchronous boundary turns bookkeeping bugs into full-network downtime.

## Algorand

**No epochs — lookback kills the boundary.** Every round r independently
derives its committees via VRF sortition from deliberately *old* inputs:
seed from round r−2 (`SeedLookback`, with a 160-round-old digest injected
every `SeedRefreshInterval`=80 rounds), and stake/keys from round r−320
(`BalanceLookback = 2·δ_s·δ_r`;
[abft-parameters.md](https://github.com/algorandfoundation/specs/blob/master/src/abft/abft-parameters.md),
`agreement/selector.go`, `config/consensus.go`). Selection is a lazily
evaluated pure function of long-finalized state: one VRF evaluation per
round/step per participant, O(1) per message; nobody ever materializes "the
committee" — membership is revealed by the vote's VRF proof, verified against
320-round-old state. **Every round has ~15 min of lookahead, permanently, by
construction.**

**Ordering discipline.** Balance round (r−320) strictly predates every input
to the seed (r−160 digest, r−2 chain) — stake is committed before the
randomness is revealed, so seeing/influencing the seed grants no
stake-grinding advantage (Gilad et al. SOSP'17, §5.2-5.3). The lookback is
also weak-synchrony insurance: the window is sized to straddle an honest
block, keeping the seed unpredictable under adversarial network control.

**Cost.** Stake changes / participation-key registrations take 320 rounds
(~15 min) to affect consensus — the paper flags the nothing-at-stake tension
of long lookbacks; Ethereum's activation/exit queues are already far longer.

## NEAR

**One full epoch of lookahead as a provisioning window.** At the last block
of epoch T, `EpochManager` computes `EpochInfo` for epoch **T+2** — i.e.
epoch T+1's validator set was fixed at the end of T−1
([nomicon EpochManager](https://nomicon.io/BlockchainLayer/EpochManager/)).
The stated rationale is exactly the DC concern: validators get a full epoch
(43,200 blocks, ~7-12 h) "to prepare for block production and validation
(they have to download the state of shards etc)" — heavy per-validator prep
runs in the background while the current epoch's consensus proceeds.

**O(1) duty lookup by contract.** `EpochInfo` contains precomputed
height→block-producer and (height, shard)→chunk-producer maps; the protocol
*requires* constant-time duty lookup (`sha256(epoch_seed ‖ height)` into a
Vose alias-method sampler). The boundary is a pointer swap; no gap slots
exist or are needed.

## Monad

**Deferred (asynchronous) execution — vote now, compute later.** MonadBFT
reaches consensus on transaction *ordering* only; execution lags consensus by
**D = 3 blocks**, and block N carries the merkle root of block N−3's state
(delayed merkle root;
[Monad docs](https://docs.monad.xyz/monad-arch/consensus/asynchronous-execution)).
The vote critical path contains only cheap checks (signatures, availability,
stateless validity); all heavy computation is pipelined behind the votes with
a full block time of budget, reconciled by a bounded-lag equality check.
Voting never waits for computing.

## Avalanche (brief)

The P-chain historically had *no* epochs — every block could shift the
validator set, making validator-set lookups a moving target. **ACP-181
"P-Chain Epoched Views"** (Granite upgrade, mainnet Nov 2025) retrofits
epochs with a frozen Epoch P-Chain Height precisely so "when a block is
built, the validator set to be used for the next block is known." Even a
chain designed around continuous validator churn converged on
freeze-the-inputs.

## Ethereum today (baseline)

*(all refs relative to the workspace mirrors: consensus-specs, EIPs, prysm,
ethresearch corpus)*

**Protocol lookahead.** `MIN_SEED_LOOKAHEAD = 1`, `MAX_SEED_LOOKAHEAD = 4`
(`specs/phase0/beacon-chain.md:265-266`). `get_seed` for epoch N hashes the
RANDAO mix as of the end of epoch N−2 (`beacon-chain.md:1052-1059`), and
activations/exits take effect no earlier than N+1+`MAX_SEED_LOOKAHEAD`
(`beacon-chain.md:913-918`), so **attestation committees for epoch N are fully
computable from any state in epoch N−1 — a guaranteed 32-slot lookahead**.
The validator guide says so explicitly and tells validators to fetch next-epoch
assignments at each epoch start and spend the whole epoch finding peers on the
target subnets (`specs/phase0/validator.md:325-360`). Proposing was the
exception: `is_proposer` needs the state of the slot in question, and "at the
epoch boundaries, the validator must run an epoch transition" to check slot-0
proposal duty (`validator.md:307-320`).

**EIP-7917 (deterministic proposer lookahead, Final, in Fulu).** Closes that
exception: `proposer_lookahead` vector in the state, computed inside
`process_epoch` for epoch current+2; `get_beacon_proposer_index` becomes a
lookup (`EIPS/eip-7917.md:36-100`; `specs/fulu/beacon-chain.md:181,264-313`).
It *knowingly adds* boundary computation in exchange for slot-time determinism
(`eip-7917.md:115-117`). EIP-8045 (exclude slashed proposers) is only possible
because 7917 froze the schedule; EIP-8333 re-anchors FFG checkpoints to the
pre-boundary root — the same "anchor to values known before the boundary" move.

**Client precompute (Prysm's next-slot cache).** `UpdateNextSlotCache` copies
the head state and runs `ProcessSlots(slot+1)` — which includes
`ProcessEpoch` when crossing the boundary — (a) immediately after importing a
block (`process_block_helpers.go:183-199`) and (b) at T≈4s of an empty slot
via `lateBlockTasks` (`process_block.go:1178-1198`). So the full epoch
transition executes in slot 31's idle tail; slot-0 block validation, proposal,
and attestation target lookup all read the pre-advanced state
(`transition_no_verify_sig.go:67,154`). **At T=0 of the new epoch everything
is a cache lookup.**

**Empirical boundary pressure.** Slot 0 of an epoch is orphaned ~7× more than
baseline (1.17% vs 0.16%), but 21 months of data attribute the excess to slow
*locally-built* blocks at a few operators, not to transition compute — i.e.
residual engineering, not a protocol floor (ethresearch 25338; second-slot
cascade analysis in 16333). Sigma Prime's single-pass epoch processing
(ethresearch 17359, formally verified, Lighthouse `tree-states`) cuts the
transition to near one O(n) pass; Orbit-SSF notes (20943) generalize the
"precompute during idle periods" pattern to per-slot transitions; the lean
chain (25369) removes the burden via staker-side ZK-proven state.

## Synthesis — mapping to DC's options

**The uniform pattern across all eleven systems:** *nobody computes duties at
the boundary that first uses them, and nobody inserts a gap in voting to buy
computation time.* The universal architecture is a pipeline:

> **freeze inputs ≥1 period early → compute in the background during the
> previous period → activate at the boundary as a pointer swap.**

Lookahead distances chosen in practice: 1 block (CometBFT H+2), 32 slots
(Ethereum committees), 320 rounds ≈ 15 min (Algorand), 4 h (Polkadot
duties), ~2 d (Solana leader schedule), 5 d (Cardano stake). Where heavy work
*did* sit on the boundary, it broke block production in exactly the way DC
fears — Cardano's 2.5-min network freeze, Solana's per-epoch skip-rate
hotspot, Kusama's era-end missed slots — and every fix was more
lookahead/spreading, never a faster boundary.

### Option 1 — gap slot (empty first slot, votes in 7 slots)

**Weakest support in the corpus.** The only deliberate boundary pause is
Sui's, and (a) it is forced by fast-path lock semantics, not computation;
(b) both of Sui's major outages concentrated at exactly that synchronous
point; (c) Sui works hard to shrink it (pipelined handoff, pre-synced next
committee) rather than institutionalize it. Diem's payload-free
reconfiguration suffix is precedent for a protocol-blessed empty *region*,
but it empties payload, not votes. For DC the gap costs 8/7 ≈ +14% per-slot
vote volume at 8-slot rounds and +33% at the 4-slot stretch goal, adds a
special-cased slot (a bug-concentration point per the Sui lesson), and buys
time the lookahead pattern gets for free. **Not recommended as a computation
fix.** If a gap-like structure is ever wanted, use it for *handoff
semantics* (see GRANDPA below), and define it end-to-end as scheduled
absence, not lateness.

### Option 2 — compute earlier (lookahead by construction) ✅ primary

This is what everyone does, and it should be a **protocol guarantee, not a
client heroic**. Concretely for DC:

- **Duties for round/height h derive from (validator set, seed) frozen at
  least one full round (8 slots) before h's first vote** — so every validator
  computes its subround/subnet/aggregator assignment during round h−1,
  and the "transition computation" at the boundary is a lookup.
- **Order the freezes Algorand-style: stake before seed before duties.** The
  stake snapshot must strictly predate every input to the randomness, or the
  seed becomes a stake-grinding target. Ethereum's
  `MIN_SEED_LOOKAHEAD`/`MAX_SEED_LOOKAHEAD` pair already implements this
  discipline; DC's VRF (open question Q7, RANDAO vs VRF) inherits the same
  requirement.
- **This dissolves the mid-epoch-finalization problem** (explainer checkbox:
  checkpoints finalize at slot 17/25). If duty inputs depend only on state
  ≥1 round old, it does not matter *when* height h finalizes — duties for
  h+1 are computable throughout h, whatever h's outcome. The rule is: duty
  assignment must be a function of *which* checkpoint is being voted on,
  never of *when* the previous one finalized.
- **Networking needs the lookahead even more than the CPU does.** Polkadot
  pre-connects to next-session authorities 4 h early and still sees
  newly-activated validators miss votes on cold connections; Ethereum's
  validator guide budgets a full epoch for finding subnet peers. One round of
  duty lookahead is the *minimum* for subnet pre-subscription; keeping
  backbone subnet membership long-lived (à la `SUBNETS_PER_NODE`) and
  rotating only the assignment on top is the cheaper structure.

### Option 3 — compute later / spread (deferral) ✅ for bookkeeping

The heavy per-validator bookkeeping (FG reward accounting, balance updates)
must never share the vote critical path. Prior art: Cardano's reward
"pulser", Solana's SIMD-0118 (4,096 accounts/block), Solana's EAH pinned to
the 25–75% window of the epoch ("the beginning of an epoch is already a time
of contention and stress"), Monad's D=3 deferred execution. Two cautions:
Cardano #3392 shows amortization *on the hot thread* still misses slots —
spreading must come with thread/process isolation; and rewards can lag
finality by a full period without harm (Cardano pays epoch e's rewards in
e+2).

### Option 4 — compute in parallel (speculative precompute) ✅ already real

Prysm's next-slot cache runs the full epoch transition in slot 31's idle tail
(T+4s of an empty slot, or right after block import); at T=0 of the new epoch
everything is a lookup. This works today and transfers directly to DC — but
it is a client mitigation with no protocol guarantee. EIP-7917 shows the
enshrinement move: when determinism matters (here: aggregator schedules,
committee roots), put the precomputed lookahead object *in the state* and
accept the boundary-time cost of maintaining it, which the precompute pattern
then absorbs.

### The one genuinely transition-coupled object: the FG handoff

Lookahead covers duty *assignment*. What cannot be looked ahead is the FG's
own progress — which height is being voted on, and the source/justified
checkpoint. GRANDPA is the direct precedent: the new authority set activates when
the gadget *finalizes the boundary block* (not at a wall-clock boundary),
votes are domain-separated by set_id so old/new rounds can't mix, and a
stall self-extends across the handoff unless there's an escape hatch
(forced changes; cf. Sui's retrofitted force-close). DC's healing/back-off
design (Q6, Q9) should treat "boundary-time finality lag" as the same
failure class.

> **Update 2026-08-25:** the follow-up analysis in
> [boundary-pipelining.md](boundary-pipelining.md) shows the current
> simplex-healing spec already engineers this handoff at *round* granularity
> (state-gated counting, one-slot inclusion spillover, empty-slot
> settlement), and that importing network-consumable certificates beyond
> exact-target JCs would break the accountable-safety proof. Read that note
> before acting on the GRANDPA analogy here.

### Recommendation

Adopt **2 + 3 + 4 together; drop the gap slot**: duty inputs frozen ≥1 round
ahead as a protocol rule (with the stake→seed→duties ordering), reward/state
bookkeeping spread off the critical path, client-side speculative transition
in the idle tail as today. The "negative time" problem is an artifact of
computing duties at the boundary that first uses them — a design point for
which this survey found no precedent in any production chain.
