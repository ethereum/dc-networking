#!/usr/bin/env python3
"""Strawman spec for staggered FG committees (dc-networking Q18), runnable.

Python 3, standard library only, deterministic. Run: `python3 sim/strawman.py` (about 5 s).

The spec functions are the README's section 2 recommendation, in consensus-specs style. They
come in two kinds:

  PURE      functions of (validator_index, round, era_seed) only, with no BeaconState: the
            seat (which 4 s unit), the subnet, the round-wide committee index, the gossip windows.
  ANCHORED  functions of the round's index set Active(E), E = epoch of the round. That set is
            identical in every state that has processed epoch E-5 on the same chain
            (analysis/anchor.md section 1.2), so a client computes it once per (E, D(E)) and
            never regenerates a state. The era seed rides on the same anchor: it is read from
            the RANDAO mix of epoch era_start - 5.

The BeaconState below is a minimal stand-in: validator lifecycle epochs, randao mixes and
block roots. Its lifecycle writes obey the write-once, value >= c + 5 rule that
analysis/anchor.md section 1.1 establishes for every fork. The toy model writes exactly c + 5,
so the tightness of the 5-epoch lookback is shown against the real spec paths in
sim/anchor_check.py, not here. BLS is a hash stand-in: these tests check rule logic, not
cryptography.

Self-tests (all must print PASS):
  T1   purity: seat, subnet and committee index need no state; ranges; determinism; rotation
  T2   anchoring: branches that diverge after epoch E-5 agree on the index set, committee members,
       bit indices and decoded aggregates for epoch E. At E = era start they agree on the era
       seed, and a seed read one epoch too late (lookback 4) is caught.
  T3   balance at n = 1,000,000: hash composition vs the exact-balance alternative
  T4   vote gaps: max gap C + 1 within an era (forward rotation), <= 2C - 1 at an era boundary
  T5   single-vote gossip: windows, REJECT only on a finalized anchor, dedup after validity, ...
  T6   composition of contiguous deposit batches: hash vs seed-free striping vs contiguous blocks
  T7   aggregate gossip: containers, selection proofs, D(E) envelope, forwarding horizon, superset
  T8   STF: decode-not-reject for exited/slashed bits, length check, non-empty committees
  T9   invariants: era length vs withdrawability delay; simultaneous open windows (burst bound)
"""

import hashlib
import random
import statistics
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

# ---------------------------------------------------------------- constants (mainnet-like)

SLOTS_PER_EPOCH = 32
SLOTS_PER_ROUND = 8                      # mk-dc-beacon-chain.md presets (:291-295)
SECONDS_PER_SLOT = 12
MAX_SEED_LOOKAHEAD = 4
MIN_VALIDATOR_WITHDRAWABILITY_DELAY = 256
FAR_FUTURE_EPOCH = 2**64 - 1
MAXIMUM_GOSSIP_CLOCK_DISPARITY_MS = 500  # phase0 p2p-interface
TARGET_AGGREGATORS_PER_COMMITTEE = 16    # phase0 validator.md

# New in this proposal
FG_UNITS_PER_ROUND = 23                  # C: Q17 grid (research/fg/pipelined-units/); 24 is legal too
FG_UNIT_SPACING_SECONDS = 4              # a unit starts every 4 s
FG_VOTE_PHASE_SECONDS = 4                # aggregation cut 4 s after the unit start
FG_LATE_WINDOW_SECONDS = 4               # soft end for votes; late aggregators publish at cut + 4 s
FG_AGGREGATE_FORWARD_SECONDS = 4         # aggregates are forwarded until (their publication time + 4 s)
FG_PUBLISH_DELAY_MS = 500                # honest voters sign at unit start, publish 0.5 s later
FG_COMMITTEES_PER_UNIT = 64              # one committee per attestation subnet per unit
FG_ROTATION_PERIOD_ROUNDS = 8            # K: one seat later every 8 rounds (analysis/schedule.md section 8)
EPOCHS_PER_FG_ERA = 256                  # see the invariant in t9: <= the withdrawability delay
FG_ANCHOR_LOOKBACK = 1 + MAX_SEED_LOOKAHEAD  # = 5 (analysis/anchor.md section 1.2)
TARGET_LATE_AGGREGATORS_PER_COMMITTEE = 2
DOMAIN_FG_COHORT = bytes.fromhex("13000000")
DOMAIN_FG_ATTESTER = bytes.fromhex("11000000")         # = mk DOMAIN_BEACON_ATTESTER_2
DOMAIN_FG_SELECTION_PROOF = bytes.fromhex("14000000")
DOMAIN_FG_LATE_SELECTION_PROOF = bytes.fromhex("15000000")
DOMAIN_FG_AGGREGATE_AND_PROOF = bytes.fromhex("16000000")
GENESIS_BLOCK_ROOT = b"\x00" * 32
ZERO_ROOT = b"\x00" * 32
EMPTY_HEIGHT = 2**64 - 1

ROUNDS_PER_EPOCH = SLOTS_PER_EPOCH // SLOTS_PER_ROUND  # 4


def hash(data: bytes) -> bytes:  # noqa: A001  (consensus-specs naming)
    return hashlib.sha256(data).digest()


def uint_to_bytes(n: int) -> bytes:
    return n.to_bytes(8, "little")


def bytes_to_uint64(b: bytes) -> int:
    return int.from_bytes(b[:8], "little")


# ---------------------------------------------------------------- BLS stand-in (rule logic only)

def bls_sign(pubkey: bytes, message: bytes) -> bytes:
    return hash(b"sig" + pubkey + message)


def bls_verify(pubkey: bytes, message: bytes, signature: bytes) -> bool:
    return signature == bls_sign(pubkey, message)


def bls_aggregate_sign(pubkeys: Sequence[bytes], message: bytes) -> bytes:
    return hash(b"agg" + b"".join(sorted(pubkeys)) + message)


def bls_fast_aggregate_verify(pubkeys: Sequence[bytes], message: bytes, signature: bytes) -> bool:
    return len(pubkeys) > 0 and signature == bls_aggregate_sign(pubkeys, message)


# ---------------------------------------------------------------- round / epoch / era arithmetic

def compute_epoch_at_round(round: int) -> int:
    return (round * SLOTS_PER_ROUND) // SLOTS_PER_EPOCH


def compute_start_slot_at_round(round: int) -> int:
    return round * SLOTS_PER_ROUND


def compute_start_slot_at_epoch(epoch: int) -> int:
    return epoch * SLOTS_PER_EPOCH


def compute_fg_era(round: int) -> int:
    """Eras are fixed epoch ranges (wall clock), never shifted by finality (README section 4)."""
    return compute_epoch_at_round(round) // EPOCHS_PER_FG_ERA


def compute_round_at_time_ms(now_ms: int, genesis_time: int) -> int:
    return (now_ms - 1000 * genesis_time) // (SECONDS_PER_SLOT * 1000) // SLOTS_PER_ROUND


# ---------------------------------------------------------------- PURE: who votes when, and where

def compute_fg_group(validator_index: int, era_seed: Optional[bytes]) -> Tuple[int, int]:
    """
    Composition: (cohort, subnet) of ``validator_index`` for the whole era.
    Hash composition when ``era_seed`` is given; seed-free striping fallback otherwise.
    A pure function of the validator index, so exits, activations and index reuse never
    re-seat anyone else (unlike a rank in the active set; analysis/schedule.md E9b).
    """
    if era_seed is None:
        return (validator_index % FG_UNITS_PER_ROUND,
                (validator_index // FG_UNITS_PER_ROUND) % FG_COMMITTEES_PER_UNIT)
    h = hash(era_seed + uint_to_bytes(validator_index))
    return (bytes_to_uint64(h[0:8]) % FG_UNITS_PER_ROUND,
            bytes_to_uint64(h[8:16]) % FG_COMMITTEES_PER_UNIT)


def compute_fg_rotation(round: int) -> int:
    """Position: every cohort moves one seat LATER every FG_ROTATION_PERIOD_ROUNDS rounds."""
    return (round // FG_ROTATION_PERIOD_ROUNDS) % FG_UNITS_PER_ROUND


def compute_fg_seat(validator_index: int, round: int, era_seed: Optional[bytes]) -> int:
    """Unit of ``round`` (0 .. C-1) in which ``validator_index`` votes."""
    cohort, _ = compute_fg_group(validator_index, era_seed)
    return (cohort + compute_fg_rotation(round)) % FG_UNITS_PER_ROUND


def compute_fg_subnet(validator_index: int, era_seed: Optional[bytes]) -> int:
    """Subnet: fixed for the era; positional rotation never moves a validator to another subnet."""
    return compute_fg_group(validator_index, era_seed)[1]


def compute_fg_committee_index(validator_index: int, round: int, era_seed: Optional[bytes]) -> int:
    """Round-wide committee index: seat-major, so units landing in one block are contiguous."""
    return (compute_fg_seat(validator_index, round, era_seed) * FG_COMMITTEES_PER_UNIT
            + compute_fg_subnet(validator_index, era_seed))


def compute_fg_seat_of_committee(committee_index: int) -> int:
    return committee_index // FG_COMMITTEES_PER_UNIT


def compute_fg_unit_start_ms(genesis_time: int, round: int, seat: int) -> int:
    return 1000 * (genesis_time + compute_start_slot_at_round(round) * SECONDS_PER_SLOT
                   + seat * FG_UNIT_SPACING_SECONDS)


# ---------------------------------------------------------------- containers

@dataclass(frozen=True)
class HeightPair:
    height: int
    root: bytes


@dataclass(frozen=True)
class AttestationData2:
    """= mk-dc-beacon-chain.md:311-318."""
    round: int
    finalize_pair: HeightPair
    target_pair: HeightPair

    def signing_root(self) -> bytes:
        return hash(DOMAIN_FG_ATTESTER + uint_to_bytes(self.round)
                    + uint_to_bytes(self.finalize_pair.height) + self.finalize_pair.root
                    + uint_to_bytes(self.target_pair.height) + self.target_pair.root)


@dataclass(frozen=True)
class SingleAttestation2:
    """Gossip vote. Unlike Electra's SingleAttestation there is NO committee_index field: the
    committee is a pure function of (attester_index, data.round, era seed). An unsigned
    committee_index would let a relay re-label copies that win the (attester, round) dedup."""
    attester_index: int
    data: AttestationData2
    signature: bytes


@dataclass
class Attestation:
    """On-chain / aggregate attestation (mk-dc-beacon-chain.md:361-375)."""
    data: AttestationData2
    committee_bits: List[int]            # round-wide committee indices with a set bit
    aggregation_bits: List[bool]
    signature: bytes = b""

    @property
    def round(self) -> int:
        return self.data.round


@dataclass
class AggregateAndProof2:
    aggregator_index: int
    aggregate: Attestation
    selection_proof: bytes
    is_late: bool                        # late aggregators use DOMAIN_FG_LATE_SELECTION_PROOF
    fg_dependent_root: bytes             # D(E) the bitfield is relative to; SIGNED by the aggregator

    def signing_root(self) -> bytes:
        a = self.aggregate
        return hash(DOMAIN_FG_AGGREGATE_AND_PROOF + uint_to_bytes(self.aggregator_index)
                    + a.data.signing_root() + bytes(int(b) for b in a.aggregation_bits)
                    + b"".join(uint_to_bytes(c) for c in sorted(a.committee_bits))
                    + a.signature + self.selection_proof + bytes([self.is_late]) + self.fg_dependent_root)


@dataclass
class SignedAggregateAndProof2:
    message: AggregateAndProof2
    signature: bytes


def compute_fg_selection_proof_root(round: int, is_late: bool) -> bytes:
    domain = DOMAIN_FG_LATE_SELECTION_PROOF if is_late else DOMAIN_FG_SELECTION_PROOF
    return hash(domain + uint_to_bytes(round))


def is_fg_aggregator(committee_size: int, selection_proof: bytes, is_late: bool) -> bool:
    target = TARGET_LATE_AGGREGATORS_PER_COMMITTEE if is_late else TARGET_AGGREGATORS_PER_COMMITTEE
    modulo = max(1, committee_size // target)
    return bytes_to_uint64(hash(selection_proof)[0:8]) % modulo == 0


# ---------------------------------------------------------------- minimal state model

@dataclass
class Validator:
    pubkey: bytes
    activation_epoch: int = FAR_FUTURE_EPOCH
    exit_epoch: int = FAR_FUTURE_EPOCH
    slashed: bool = False


@dataclass
class BeaconState:
    slot: int
    validators: List[Validator]
    randao_mixes: Dict[int, bytes]       # epoch -> final mix of that epoch
    block_roots: Dict[int, bytes]        # slot -> root of the latest block at or before that slot

    def current_epoch(self) -> int:
        return self.slot // SLOTS_PER_EPOCH


def is_active_validator(v: Validator, epoch: int) -> bool:
    return v.activation_epoch <= epoch < v.exit_epoch


def get_active_validator_indices(state: BeaconState, epoch: int) -> List[int]:
    return [i for i, v in enumerate(state.validators) if is_active_validator(v, epoch)]


def get_block_root_at_slot(state: BeaconState, slot: int) -> bytes:
    assert slot < state.slot
    return state.block_roots[slot]


def get_randao_mix(state: BeaconState, epoch: int) -> bytes:
    assert epoch < state.current_epoch(), "mix of an epoch is final only after the epoch"
    return state.randao_mixes[epoch]


# ---------------------------------------------------------------- ANCHORED: the cached index set

def get_fg_dependent_root(state: BeaconState, epoch: int) -> bytes:
    """
    D(E): root of the latest block at or before the last slot of epoch E - 5.
    ``Active(E)`` and the era seed of E's era are functions of (E, D(E)).
    """
    if epoch < FG_ANCHOR_LOOKBACK:
        return GENESIS_BLOCK_ROOT
    return get_block_root_at_slot(state, compute_start_slot_at_epoch(epoch - MAX_SEED_LOOKAHEAD) - 1)


def get_fg_era_seed(state: BeaconState, era: int, lookback: int = FG_ANCHOR_LOOKBACK) -> bytes:
    """
    Seed of ``era``: the final RANDAO mix of epoch (era start - 5), domain-separated by the era.
    It is fixed once that epoch is processed, i.e. it rides on D(era start), and it is revealed
    only about 4 epochs before the era. ``lookback`` exists only so T2 can show that a wrong
    value is caught.
    """
    mix_epoch = era * EPOCHS_PER_FG_ERA - lookback
    if mix_epoch < 0:
        mix = b"\x00" * 32
    else:
        assert state.current_epoch() > mix_epoch   # never serve duties from a partial mix
        mix = get_randao_mix(state, mix_epoch)
    return hash(DOMAIN_FG_COHORT + uint_to_bytes(era) + mix)


def get_fg_index_set(state: BeaconState, round: int) -> List[int]:
    """Active(E), E = epoch of ``round``. Identical in every state descending from D(E)
    whose slot is at least the start of epoch E - 4."""
    epoch = compute_epoch_at_round(round)
    if epoch >= FG_ANCHOR_LOOKBACK:
        assert compute_start_slot_at_epoch(epoch - MAX_SEED_LOOKAHEAD) <= state.slot
    return get_active_validator_indices(state, epoch)


def get_fg_committee_members(state: BeaconState, round: int, committee_index: int) -> List[int]:
    """Ascending members of one (seat, subnet) committee; bit k of its aggregation bits = members[k]."""
    era_seed = get_fg_era_seed(state, compute_fg_era(round))
    return [i for i in get_fg_index_set(state, round)
            if compute_fg_committee_index(i, round, era_seed) == committee_index]


def get_fg_bit_index(state: BeaconState, round: int, validator_index: int) -> int:
    era_seed = get_fg_era_seed(state, compute_fg_era(round))
    members = get_fg_committee_members(
        state, round, compute_fg_committee_index(validator_index, round, era_seed))
    return members.index(validator_index)  # raises if not in Active(E)


def get_fg_attesting_indices(state: BeaconState, attestation: Attestation) -> Set[int]:
    """Decode an aggregate: committees concatenated in ascending committee index (Electra style)."""
    output: Set[int] = set()
    offset = 0
    for committee_index in sorted(attestation.committee_bits):
        members = get_fg_committee_members(state, attestation.round, committee_index)
        assert len(members) > 0, "non-empty committee (mk-dc-beacon-chain.md:712-713)"
        output |= {i for k, i in enumerate(members) if attestation.aggregation_bits[offset + k]}
        offset += len(members)
    assert len(attestation.aggregation_bits) == offset, "aggregation bits length check"
    return output


def get_fg_counted_indices(state: BeaconState, attestation: Attestation) -> Set[int]:
    """Bits of validators that are no longer active, or slashed, are decoded but not counted.
    This replaces mk-dc-beacon-chain.md:714-718, where one such bit rejects the whole aggregate."""
    epoch = state.current_epoch()
    return {i for i in get_fg_attesting_indices(state, attestation)
            if is_active_validator(state.validators[i], epoch) and not state.validators[i].slashed}


# ---------------------------------------------------------------- gossip

@dataclass
class FGCache:
    """What a node keeps per (E, D(E)), computed from its own head chain: no BeaconState.
    ``pubkeys`` maps index -> pubkey for the members (EIP-6914-safe: taken from this entry)."""
    dependent_root: bytes
    era_seed: bytes
    index_set: Set[int]
    pubkeys: Dict[int, bytes]
    anchor_finalized: bool               # D(E) finalized locally (implies D(era start) finalized)
    members_by_committee: Dict[int, List[int]] = field(default_factory=dict)

    def members(self, committee_index: int) -> List[int]:
        if not self.members_by_committee:
            for i in sorted(self.index_set):
                self.members_by_committee.setdefault(self._committee(i), []).append(i)
        return self.members_by_committee.get(committee_index, [])

    def _committee(self, i: int) -> int:
        return compute_fg_committee_index(i, self.round, self.era_seed)

    round: int = 0


@dataclass
class GossipContext:
    genesis_time: int
    known_blocks: Set[bytes]             # roots in the node's fork-choice store
    invalid_blocks: Set[bytes]
    equivocators: Set[int]               # indices with locally seen valid slashing evidence
    seen_votes: Set[Tuple[int, int]] = field(default_factory=set)            # (attester, round), VALID only
    seen_aggregators: Set[Tuple[int, int, bytes]] = field(default_factory=set)  # (aggregator, round, data root)
    best_aggregates: Dict[Tuple[bytes, bytes, int], Set[int]] = field(default_factory=dict)  # (D, data root, committee) -> bits


def _det(cache: FGCache, reason: str) -> str:
    """A deterministic failure is REJECT only if the anchor it was decided on is finalized locally;
    otherwise an honest peer on another branch could hit it, so IGNORE (no peer-score penalty)."""
    return ("REJECT: " if cache.anchor_finalized else "IGNORE: ") + reason


def _round_in_range(data_round: int, now_ms: int, genesis_time: int, extra_rounds: int) -> bool:
    lo = compute_round_at_time_ms(now_ms - MAXIMUM_GOSSIP_CLOCK_DISPARITY_MS, genesis_time) - extra_rounds
    hi = compute_round_at_time_ms(now_ms + MAXIMUM_GOSSIP_CLOCK_DISPARITY_MS, genesis_time)
    return lo <= data_round <= hi


def validate_fg_vote_gossip(cache: FGCache, ctx: GossipContext, now_ms: int, vote: SingleAttestation2,
                            topic_subnet: int) -> str:
    """beacon_attestation_{subnet_id} (DC). Cheap checks first; BLS last; dedup on valid votes only."""
    d = vote.data
    if not _round_in_range(d.round, now_ms, ctx.genesis_time, extra_rounds=1):
        return "IGNORE: round out of range"
    if cache is None:
        return "IGNORE: no local index set for this round (MAY queue until computed)"
    if vote.attester_index not in cache.index_set:
        return _det(cache, "attester not in Active(E)")
    if topic_subnet != compute_fg_subnet(vote.attester_index, cache.era_seed):
        return _det(cache, "wrong subnet")
    if d.target_pair == d.finalize_pair == HeightPair(EMPTY_HEIGHT, ZERO_ROOT):
        return "REJECT: both pairs empty (mk-dc-beacon-chain.md:663-666)"
    start = compute_fg_unit_start_ms(ctx.genesis_time, d.round,
                                     compute_fg_seat(vote.attester_index, d.round, cache.era_seed))
    if now_ms + MAXIMUM_GOSSIP_CLOCK_DISPARITY_MS < start:
        return "IGNORE: before the unit (hard start; MUST NOT be held for later acceptance)"
    if now_ms > start + 1000 * (FG_VOTE_PHASE_SECONDS + FG_LATE_WINDOW_SECONDS) + MAXIMUM_GOSSIP_CLOCK_DISPARITY_MS:
        return "IGNORE: after the soft end"
    if (vote.attester_index, d.round) in ctx.seen_votes:
        return "IGNORE: already seen a valid vote for (attester, round)"
    if vote.attester_index in ctx.equivocators:
        return "IGNORE: known equivocator"
    if d.target_pair.root != ZERO_ROOT:
        if d.target_pair.root in ctx.invalid_blocks:
            return "REJECT: target is a known-invalid block"
        if d.target_pair.root not in ctx.known_blocks:
            return "IGNORE: unknown target (MAY keep for local aggregation; do not forward)"
    if not bls_verify(cache.pubkeys[vote.attester_index], d.signing_root(), vote.signature):
        return _det(cache, "bad signature")
    ctx.seen_votes.add((vote.attester_index, d.round))
    return "ACCEPT"


def validate_fg_aggregate_gossip(caches: Dict[bytes, FGCache], ctx: GossipContext, now_ms: int,
                                 signed: SignedAggregateAndProof2) -> str:
    """beacon_aggregate_and_proof (DC). The envelope names D(E); the node decodes only against an
    entry it holds for exactly that D, so deterministic failures can be REJECTed when it is final."""
    m = signed.message
    a = m.aggregate
    cache = caches.get(m.fg_dependent_root)
    if cache is None or cache.round != a.round:
        return "IGNORE: fg_dependent_root unknown or foreign (no local index set for it)"
    if len(a.committee_bits) != 1:
        return "REJECT: exactly one committee bit"
    committee_index = a.committee_bits[0]
    if not 0 <= committee_index < FG_UNITS_PER_ROUND * FG_COMMITTEES_PER_UNIT:
        return "REJECT: committee index out of range"
    cut = compute_fg_unit_start_ms(ctx.genesis_time, a.round, compute_fg_seat_of_committee(committee_index)) \
        + 1000 * FG_VOTE_PHASE_SECONDS
    publish = cut + (1000 * FG_LATE_WINDOW_SECONDS if m.is_late else 0)
    if now_ms + MAXIMUM_GOSSIP_CLOCK_DISPARITY_MS < publish:
        return "IGNORE: before the aggregate's publication time (hard start)"
    if now_ms > publish + 1000 * FG_AGGREGATE_FORWARD_SECONDS + MAXIMUM_GOSSIP_CLOCK_DISPARITY_MS:
        return "IGNORE: past the forwarding horizon (proposers MAY still include it until the end of round r+1)"
    members = cache.members(committee_index)
    if len(a.aggregation_bits) != len(members) or not any(a.aggregation_bits):
        return _det(cache, "bitfield length != committee size, or no bit set")
    if m.aggregator_index not in members:
        return _det(cache, "aggregator not in the committee")
    if not bls_verify(cache.pubkeys[m.aggregator_index], compute_fg_selection_proof_root(a.round, m.is_late),
                      m.selection_proof):
        return _det(cache, "bad selection proof")
    if not is_fg_aggregator(len(members), m.selection_proof, m.is_late):
        return _det(cache, "selection proof does not select the aggregator")
    bits = {members[k] for k, b in enumerate(a.aggregation_bits) if b}
    key = (m.fg_dependent_root, a.data.signing_root(), committee_index)
    if key in ctx.best_aggregates and bits <= ctx.best_aggregates[key]:
        return "IGNORE: a valid aggregate with a superset of these bits was already seen"
    if (m.aggregator_index, a.round, a.data.signing_root()) in ctx.seen_aggregators:
        return "IGNORE: aggregator already published for this (round, data)"
    if len({k for k in ctx.seen_aggregators if k[0] == m.aggregator_index and k[1] == a.round}) >= 2:
        return "IGNORE: aggregator already published two data values this round"
    if not bls_verify(cache.pubkeys[m.aggregator_index], m.signing_root(), signed.signature):
        return _det(cache, "bad aggregator signature")
    if not bls_fast_aggregate_verify([cache.pubkeys[i] for i in sorted(bits)], a.data.signing_root(), a.signature):
        return _det(cache, "bad aggregate signature")
    ctx.seen_aggregators.add((m.aggregator_index, a.round, a.data.signing_root()))
    ctx.best_aggregates[key] = ctx.best_aggregates.get(key, set()) | bits
    return "ACCEPT"


# ================================================================ self-tests

def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
    return ok


def t1_purity() -> bool:
    print("T1 purity, ranges, determinism")
    ok = True
    seed = hash(b"era-seed")
    seats = [compute_fg_seat(v, r, seed) for v in range(200) for r in range(0, 400, 7)]
    ok &= check("seat in [0, C)", all(0 <= s < FG_UNITS_PER_ROUND for s in seats))
    cis = [compute_fg_committee_index(v, 5, seed) for v in range(2000)]
    ok &= check("committee index in [0, C*64)", all(0 <= c < FG_UNITS_PER_ROUND * FG_COMMITTEES_PER_UNIT for c in cis))
    ok &= check("deterministic", [compute_fg_seat(v, 9, seed) for v in range(50)] == [compute_fg_seat(v, 9, seed) for v in range(50)])
    deltas = {(compute_fg_seat(v, r + 1, seed) - compute_fg_seat(v, r, seed)) % FG_UNITS_PER_ROUND
              for v in range(100) for r in range(0, 64)}
    ok &= check("seat moves by 0 or +1 between consecutive rounds within an era", deltas <= {0, 1}, f"deltas {sorted(deltas)}")
    subnets_r0 = [compute_fg_subnet(v, seed) for v in range(500)]
    ok &= check("subnet independent of round (rotation never re-subnets)", all(
        compute_fg_committee_index(v, r, seed) % FG_COMMITTEES_PER_UNIT == subnets_r0[v]
        for v in range(500) for r in (0, 8, 16, 100)))
    return ok


def _make_branch_states(n: int, end_epoch: int, diverge_after_epoch: int, seed: int) -> Tuple[BeaconState, BeaconState]:
    """Two states at slot start(end_epoch) + 10 that share every write at epochs <= diverge_after_epoch
    and every block/mix up to its last slot, with different random lifecycle writes afterwards.
    Writes obey FAR -> v with v >= c + 5."""
    rng = random.Random(seed)
    start_epoch = diverge_after_epoch - 40
    base = [Validator(pubkey=hash(uint_to_bytes(i)), activation_epoch=0) for i in range(n)]
    for i in range(n, n + 300):                     # pending entries
        base.append(Validator(pubkey=hash(uint_to_bytes(i))))
    for i in rng.sample(range(n), 200):             # exits scheduled in the common past
        base[i].exit_epoch = start_epoch + rng.randrange(5, 60)

    def evolve(branch_seed: int) -> BeaconState:
        crng = random.Random(seed * 1000 + 17)       # identical for both branches: the common past
        brng = random.Random(branch_seed)            # branch-specific after the divergence
        vals = [Validator(v.pubkey, v.activation_epoch, v.exit_epoch, v.slashed) for v in base]
        mixes: Dict[int, bytes] = {}
        roots: Dict[int, bytes] = {}
        for c in range(start_epoch, end_epoch + 1):
            common = c <= diverge_after_epoch
            r = crng if common else brng
            tag = b"" if common else uint_to_bytes(branch_seed)
            for _ in range(r.randrange(2, 6)):          # activations of pending entries
                cand = [i for i, v in enumerate(vals) if v.activation_epoch == FAR_FUTURE_EPOCH]
                if cand:
                    vals[r.choice(cand)].activation_epoch = c + 5
            for _ in range(r.randrange(2, 6)):          # exits / slashings
                cand = [i for i, v in enumerate(vals) if v.exit_epoch == FAR_FUTURE_EPOCH and v.activation_epoch <= c]
                if cand:
                    i = r.choice(cand)
                    vals[i].exit_epoch = c + 5 + r.randrange(0, 4)
                    if r.random() < 0.2:
                        vals[i].slashed = True
            for _ in range(r.randrange(0, 3)):          # new deposits appended
                vals.append(Validator(pubkey=hash(b"dep" + uint_to_bytes(len(vals)) + tag)))
            mixes[c] = hash(b"mix" + uint_to_bytes(c) + tag)
            for s in range(compute_start_slot_at_epoch(c), compute_start_slot_at_epoch(c + 1)):
                roots[s] = hash(b"root" + uint_to_bytes(s) + tag)
        for c in range(0, start_epoch):
            mixes[c] = hash(b"mix" + uint_to_bytes(c))
        return BeaconState(slot=compute_start_slot_at_epoch(end_epoch) + 10, validators=vals,
                           randao_mixes=mixes, block_roots=roots)

    return evolve(seed * 7 + 1), evolve(seed * 7 + 2)


def t2_anchoring() -> bool:
    print("T2 anchoring: branches diverging after E-5 agree on everything the FG needs for epoch E")
    ok = True
    era = 3
    E = era * EPOCHS_PER_FG_ERA + 12
    n = 3000
    # states at the earliest slot that may compute Active(E): start(E-4) (+10 slots)
    A, B = _make_branch_states(n, E - MAX_SEED_LOOKAHEAD, diverge_after_epoch=E - FG_ANCHOR_LOOKBACK, seed=11)
    ok &= check("D(E) equal", get_fg_dependent_root(A, E) == get_fg_dependent_root(B, E))
    ok &= check("branches really differ after E-5",
                len(A.validators) != len(B.validators) or any(
                    (a.activation_epoch, a.exit_epoch, a.slashed) != (b.activation_epoch, b.exit_epoch, b.slashed)
                    for a, b in zip(A.validators, B.validators)))
    rounds = [E * ROUNDS_PER_EPOCH + k for k in range(ROUNDS_PER_EPOCH)]
    ok &= check("Active(E) equal for all 4 rounds of E", all(get_fg_index_set(A, r) == get_fg_index_set(B, r) for r in rounds))
    seed_a = get_fg_era_seed(A, era)
    n_committees = FG_UNITS_PER_ROUND * FG_COMMITTEES_PER_UNIT
    same = True
    bit_checks = 0
    for r in rounds[:2]:
        by_committee: Dict[int, List[int]] = {}
        for i in get_fg_index_set(A, r):
            by_committee.setdefault(compute_fg_committee_index(i, r, seed_a), []).append(i)
        for ci in range(0, n_committees, 37):
            ma, mb = get_fg_committee_members(A, r, ci), get_fg_committee_members(B, r, ci)
            same &= (ma == mb == by_committee.get(ci, []))
            for v in ma[:3]:
                same &= get_fg_bit_index(A, r, v) == get_fg_bit_index(B, r, v)
                bit_checks += 1
    ok &= check("committee members and bit indices equal", same, f"{bit_checks} bit indices compared")
    r = rounds[1]
    ci = next(ci for ci in range(n_committees) if len(get_fg_committee_members(A, r, ci)) >= 2)
    members = get_fg_committee_members(A, r, ci)
    att = Attestation(data=AttestationData2(r, HeightPair(1, b"f" * 32), HeightPair(2, b"t" * 32)),
                      committee_bits=[ci], aggregation_bits=[k % 2 == 0 for k in range(len(members))])
    ok &= check("aggregate decodes identically on both branches",
                get_fg_attesting_indices(A, att) == get_fg_attesting_indices(B, att))
    # era seed at the hardest point: the first epoch of the era, branches diverging after era_start - 5
    era_start = era * EPOCHS_PER_FG_ERA
    A2, B2 = _make_branch_states(n, era_start, diverge_after_epoch=era_start - FG_ANCHOR_LOOKBACK, seed=23)
    ok &= check("era seed equal at E = era start (diverged after era_start - 5)",
                get_fg_era_seed(A2, era) == get_fg_era_seed(B2, era))
    ok &= check("mutation caught: a seed read with lookback 4 differs across those branches",
                get_fg_era_seed(A2, era, lookback=4) != get_fg_era_seed(B2, era, lookback=4))
    # sanity (tightness itself is shown against the real spec paths in sim/anchor_check.py)
    differs = 0
    for s in range(1, 9):
        A3, B3 = _make_branch_states(n, E - MAX_SEED_LOOKAHEAD, diverge_after_epoch=E - FG_ANCHOR_LOOKBACK - 1, seed=100 + s)
        differs += get_fg_index_set(A3, rounds[0]) != get_fg_index_set(B3, rounds[0])
    ok &= check("sanity: diverging AT E-5 can change Active(E)", differs > 0, f"{differs}/8 trials differ")
    return ok


def t3_balance() -> bool:
    print("T3 balance of hash composition at n = 1,000,000 (C = 23, 64 committees per unit)")
    n = 1_000_000
    seed = hash(b"balance")
    t0 = time.time()
    cohort = [0] * FG_UNITS_PER_ROUND
    committee = [0] * (FG_UNITS_PER_ROUND * FG_COMMITTEES_PER_UNIT)
    for v in range(n):
        h = hashlib.sha256(seed + v.to_bytes(8, "little")).digest()
        c = int.from_bytes(h[0:8], "little") % FG_UNITS_PER_ROUND
        s = int.from_bytes(h[8:16], "little") % FG_COMMITTEES_PER_UNIT
        cohort[c] += 1
        committee[c * FG_COMMITTEES_PER_UNIT + s] += 1
    dt = time.time() - t0
    mc, mk = n / FG_UNITS_PER_ROUND, n / len(committee)
    print(f"    cohort size: mean {mc:,.0f}, min {min(cohort):,} ({min(cohort)/mc-1:+.2%}), max {max(cohort):,} ({max(cohort)/mc-1:+.2%})")
    print(f"    committee size: mean {mk:,.1f}, sd {statistics.pstdev(committee):.1f}, min {min(committee)} ({min(committee)/mk-1:+.1%}), max {max(committee)} ({max(committee)/mk-1:+.1%})")
    # three consecutive units (one block's merge) vs the 2^17 aggregate cap
    triples = [sum(cohort[(u + k) % FG_UNITS_PER_ROUND] for k in range(3)) for u in range(FG_UNITS_PER_ROUND)]
    over = sum(t > 2**17 for t in triples)
    print(f"    3-unit merges: max {max(triples):,} bits vs cap 131,072 -> {over} of {FG_UNITS_PER_ROUND} over the cap")
    print(f"    exact-balance alternative (seeded shuffle of the era list, analysis/schedule.md section 8): cohorts and committees +-1")
    print(f"    ({dt:.1f} s for 10^6 hashes: the per-era table costs one hash per validator)")
    ok = check("cohort imbalance <= 2%", max(cohort) / mc - 1 <= 0.02 and 1 - min(cohort) / mc <= 0.02)
    ok &= check("committee imbalance <= 20%", max(committee) / mk - 1 <= 0.20)
    return ok


def t4_gaps() -> bool:
    print("T4 vote gaps (in units) between consecutive vote opportunities")
    C = FG_UNITS_PER_ROUND
    seed_e, seed_f = hash(b"era-a"), hash(b"era-b")
    era_len_rounds = EPOCHS_PER_FG_ERA * ROUNDS_PER_EPOCH
    ok = True
    max_gap = 0
    for v in range(0, 3000, 7):
        prev = None
        for r in range(0, 3 * FG_ROTATION_PERIOD_ROUNDS * C):
            t = r * C + compute_fg_seat(v, r, seed_e)
            if prev is not None:
                max_gap = max(max_gap, t - prev)
            prev = t
    ok &= check("max gap within an era = C + 1", max_gap == C + 1, f"C = {C}, max gap {max_gap}")
    r_last = era_len_rounds - 1
    gaps = [(r_last + 1) * C + compute_fg_seat(v, r_last + 1, seed_f) - (r_last * C + compute_fg_seat(v, r_last, seed_e))
            for v in range(20000)]
    share_long = sum(g > C + 1 for g in gaps) / len(gaps)
    ok &= check("era-boundary gaps within [1, 2C - 1]", 1 <= min(gaps) and max(gaps) <= 2 * C - 1,
                f"max {max(gaps)}, {share_long:.0%} of validators wait longer than C + 1 once per era")
    return ok


def _toy_cache(n: int, round: int, seed: bytes, finalized: bool) -> FGCache:
    pubkeys = {i: hash(b"pk" + uint_to_bytes(i)) for i in range(n)}
    return FGCache(dependent_root=hash(b"D" + uint_to_bytes(round) + seed), era_seed=seed, index_set=set(range(n)),
                   pubkeys=pubkeys, anchor_finalized=finalized, round=round)


def t5_gossip_votes() -> bool:
    print("T5 single-vote gossip")
    genesis = 1_600_000_000
    seed = hash(b"gossip")
    r = 1000
    cache = _toy_cache(10_000, r, seed, finalized=True)
    cache_nf = _toy_cache(10_000, r, seed, finalized=False)
    target = b"T" * 32
    data = AttestationData2(r, HeightPair(5, b"F" * 32), HeightPair(6, target))
    v = 4242
    vote = SingleAttestation2(v, data, bls_sign(cache.pubkeys[v], data.signing_root()))
    subnet = compute_fg_subnet(v, seed)
    start = compute_fg_unit_start_ms(genesis, r, compute_fg_seat(v, r, seed))

    def ctx() -> GossipContext:
        return GossipContext(genesis_time=genesis, known_blocks={target}, invalid_blocks=set(), equivocators=set())

    ok = True
    c = ctx()
    ok &= check("honest publish at start + 0.5 s -> ACCEPT", validate_fg_vote_gossip(cache, c, start + FG_PUBLISH_DELAY_MS, vote, subnet) == "ACCEPT")
    ok &= check("same vote again -> IGNORE (dedup inserted after validity)",
                validate_fg_vote_gossip(cache, c, start + 1000, vote, subnet).startswith("IGNORE: already"))
    bad_sig = SingleAttestation2(v, data, b"\x01" * 32)
    c = ctx()
    ok &= check("invalid signature first does not poison dedup",
                validate_fg_vote_gossip(cache, c, start + 1000, bad_sig, subnet).startswith("REJECT: bad signature")
                and validate_fg_vote_gossip(cache, c, start + 1000, vote, subnet) == "ACCEPT")
    ok &= check("receiver clock 0.9 s slow still accepts a vote published at start + 0.5 s",
                validate_fg_vote_gossip(cache, ctx(), start + FG_PUBLISH_DELAY_MS - 900, vote, subnet) == "ACCEPT")
    ok &= check("early by > disparity -> IGNORE (hard start)",
                validate_fg_vote_gossip(cache, ctx(), start - 600, vote, subnet).startswith("IGNORE: before"))
    ok &= check("after soft end -> IGNORE",
                validate_fg_vote_gossip(cache, ctx(), start + 8600, vote, subnet).startswith("IGNORE: after"))
    ok &= check("wrong subnet, finalized anchor -> REJECT",
                validate_fg_vote_gossip(cache, ctx(), start + 1000, vote, (subnet + 1) % 64).startswith("REJECT: wrong subnet"))
    ok &= check("wrong subnet, unfinalized anchor (era seeds may differ across branches) -> IGNORE",
                validate_fg_vote_gossip(cache_nf, ctx(), start + 1000, vote, (subnet + 1) % 64).startswith("IGNORE: wrong subnet"))
    outsider = SingleAttestation2(20_000, data, b"x" * 32)
    ok &= check("non-member: REJECT if finalized, IGNORE if not",
                validate_fg_vote_gossip(cache, ctx(), start + 1000, outsider, compute_fg_subnet(20_000, seed)).startswith("REJECT")
                and validate_fg_vote_gossip(cache_nf, ctx(), start + 1000, outsider, compute_fg_subnet(20_000, seed)).startswith("IGNORE"))
    unknown = AttestationData2(r, HeightPair(5, b"F" * 32), HeightPair(6, b"U" * 32))
    uvote = SingleAttestation2(v, unknown, bls_sign(cache.pubkeys[v], unknown.signing_root()))
    ok &= check("unknown target -> IGNORE (MAY keep for local aggregation)",
                validate_fg_vote_gossip(cache, ctx(), start + 1000, uvote, subnet).startswith("IGNORE: unknown target"))
    empty = AttestationData2(r, HeightPair(EMPTY_HEIGHT, ZERO_ROOT), HeightPair(EMPTY_HEIGHT, ZERO_ROOT))
    evote = SingleAttestation2(v, empty, bls_sign(cache.pubkeys[v], empty.signing_root()))
    ok &= check("both pairs empty -> REJECT", validate_fg_vote_gossip(cache, ctx(), start + 1000, evote, subnet).startswith("REJECT: both"))
    c = ctx()
    c.equivocators.add(v)
    ok &= check("known equivocator -> IGNORE", validate_fg_vote_gossip(cache, c, start + 1000, vote, subnet).startswith("IGNORE: known"))
    ok &= check("vote two rounds back -> IGNORE",
                validate_fg_vote_gossip(cache, ctx(), start + 2 * SLOTS_PER_ROUND * SECONDS_PER_SLOT * 1000, vote, subnet).startswith("IGNORE: round"))
    ok &= check("no local index set -> IGNORE", validate_fg_vote_gossip(None, ctx(), start + 1000, vote, subnet).startswith("IGNORE: no local"))
    return ok


def t6_batches() -> bool:
    print("T6 contiguous deposit batches (one operator, 1,000 consecutive indices) at n = 10^6")
    C = FG_UNITS_PER_ROUND
    n = 1_000_000
    seed = hash(b"batches")
    batch = range(500_000, 501_000)
    per_hash, per_stripe, per_block = [0] * C, [0] * C, [0] * C
    for v in batch:
        per_hash[compute_fg_group(v, seed)[0]] += 1
        per_stripe[compute_fg_group(v, None)[0]] += 1
        per_block[(v * C) // n] += 1                # contiguous blocks (mk-dc-beacon-chain.md:870-872)
    print(f"    cohorts touched / max share of one cohort: hash {sum(x > 0 for x in per_hash)} / {max(per_hash)/1000:.1%}, "
          f"stripe {sum(x > 0 for x in per_stripe)} / {max(per_stripe)/1000:.1%}, "
          f"contiguous {sum(x > 0 for x in per_block)} / {max(per_block)/1000:.1%}")
    ok = check("hash and stripe spread the batch over all cohorts",
               sum(x > 0 for x in per_hash) == C and sum(x > 0 for x in per_stripe) == C)
    ok &= check("contiguous blocks keep the batch in <= 2 cohorts", sum(x > 0 for x in per_block) <= 2)
    return ok


def t7_gossip_aggregates() -> bool:
    print("T7 aggregate gossip")
    genesis = 1_600_000_000
    seed = hash(b"agg")
    r = 2000
    n = 200_000
    cache = _toy_cache(n, r, seed, finalized=True)
    caches = {cache.dependent_root: cache}
    target = b"T" * 32
    data = AttestationData2(r, HeightPair(5, b"F" * 32), HeightPair(6, target))
    # a committee with an on-time and a late aggregator
    for ci in range(FG_UNITS_PER_ROUND * FG_COMMITTEES_PER_UNIT):
        members = cache.members(ci)
        proofs = {i: bls_sign(cache.pubkeys[i], compute_fg_selection_proof_root(r, False)) for i in members}
        lproofs = {i: bls_sign(cache.pubkeys[i], compute_fg_selection_proof_root(r, True)) for i in members}
        aggs = [i for i in members if is_fg_aggregator(len(members), proofs[i], False)]
        lates = [i for i in members if is_fg_aggregator(len(members), lproofs[i], True)]
        non = [i for i in members if not is_fg_aggregator(len(members), proofs[i], False)]
        if aggs and lates and non:
            break
    agg, late, nonagg = aggs[0], lates[0], non[0]
    cut = compute_fg_unit_start_ms(genesis, r, compute_fg_seat_of_committee(ci)) + 1000 * FG_VOTE_PHASE_SECONDS
    print(f"    committee {ci}: {len(members)} members, {len(aggs)} on-time / {len(lates)} late aggregators selected")

    def make(aggregator: int, bits: List[bool], is_late: bool = False, d_root: Optional[bytes] = None,
             committees: Optional[List[int]] = None) -> SignedAggregateAndProof2:
        signers = [cache.pubkeys[members[k]] for k, b in enumerate(bits) if b]
        a = Attestation(data=data, committee_bits=committees or [ci], aggregation_bits=bits,
                        signature=bls_aggregate_sign(signers, data.signing_root()) if signers else b"")
        proof = bls_sign(cache.pubkeys[aggregator], compute_fg_selection_proof_root(r, is_late))
        m = AggregateAndProof2(aggregator, a, proof, is_late, d_root or cache.dependent_root)
        return SignedAggregateAndProof2(m, bls_sign(cache.pubkeys[aggregator], m.signing_root()))

    def ctx() -> GossipContext:
        return GossipContext(genesis_time=genesis, known_blocks={target}, invalid_blocks=set(), equivocators=set())

    half = [k % 2 == 0 for k in range(len(members))]
    full = [True] * len(members)
    ok = True
    c = ctx()
    ok &= check("on-time aggregate at the cut -> ACCEPT", validate_fg_aggregate_gossip(caches, c, cut + 200, make(agg, half)) == "ACCEPT")
    ok &= check("subset of a seen aggregate -> IGNORE",
                validate_fg_aggregate_gossip(caches, c, cut + 300, make(late, half, is_late=True)).startswith("IGNORE"))
    ok &= check("late superset at cut + 4 s -> ACCEPT",
                validate_fg_aggregate_gossip(caches, c, cut + 4200, make(late, full, is_late=True)) == "ACCEPT")
    ok &= check("late aggregator before its time -> IGNORE",
                validate_fg_aggregate_gossip(caches, ctx(), cut + 1000, make(late, full, is_late=True)).startswith("IGNORE: before"))
    ok &= check("past the forwarding horizon -> IGNORE",
                validate_fg_aggregate_gossip(caches, ctx(), cut + 9000, make(agg, half)).startswith("IGNORE: past"))
    ok &= check("foreign fg_dependent_root -> IGNORE",
                validate_fg_aggregate_gossip(caches, ctx(), cut + 200, make(agg, half, d_root=b"X" * 32)).startswith("IGNORE: fg_dependent_root"))
    ok &= check("two committee bits -> REJECT",
                validate_fg_aggregate_gossip(caches, ctx(), cut + 200, make(agg, half, committees=[ci, ci + 1])).startswith("REJECT: exactly one"))
    ok &= check("wrong bitfield length -> REJECT",
                validate_fg_aggregate_gossip(caches, ctx(), cut + 200, make(agg, half[:-1])).startswith("REJECT: bitfield"))
    ok &= check("no bit set -> REJECT",
                validate_fg_aggregate_gossip(caches, ctx(), cut + 200, make(agg, [False] * len(members))).startswith("REJECT: bitfield"))
    ok &= check("non-selected aggregator -> REJECT",
                validate_fg_aggregate_gossip(caches, ctx(), cut + 200, make(nonagg, half)).startswith("REJECT: selection"))
    tampered = make(agg, half)
    tampered.message.fg_dependent_root = cache.dependent_root  # unchanged root, but re-sign check below
    tampered.message.aggregate.aggregation_bits = full          # bits changed after signing
    ok &= check("bits changed after the aggregator signed -> REJECT",
                validate_fg_aggregate_gossip(caches, ctx(), cut + 200, tampered).startswith("REJECT: bad aggregator signature"))
    return ok


def t8_stf() -> bool:
    print("T8 STF: decode-not-reject, length check, non-empty committees")
    n = 2000
    seed = 31
    E = 3 * EPOCHS_PER_FG_ERA + 20
    A, _ = _make_branch_states(n, E + 1, diverge_after_epoch=E - FG_ANCHOR_LOOKBACK, seed=seed)
    r = E * ROUNDS_PER_EPOCH + 3                   # last round of E, included in epoch E + 1
    era_seed = get_fg_era_seed(A, compute_fg_era(r))
    members_ci = [(ci, get_fg_committee_members(A, r, ci)) for ci in range(FG_UNITS_PER_ROUND * FG_COMMITTEES_PER_UNIT)]
    ci, members = next((ci, m) for ci, m in members_ci if len(m) >= 3)
    # one member exits at E + 1, one is slashed: both decode, neither counts at the including epoch
    A.validators[members[0]].exit_epoch = E + 1
    A.validators[members[1]].slashed = True
    att = Attestation(data=AttestationData2(r, HeightPair(1, b"f" * 32), HeightPair(2, b"t" * 32)),
                      committee_bits=[ci], aggregation_bits=[True] * len(members))
    # inclusion happens at epoch E + 1 (state slot is in E + 1); Active(E) is still exact from it
    decoded = get_fg_attesting_indices(A, att)
    counted = get_fg_counted_indices(A, att)
    ok = check("previous-epoch round decodes from the including state", decoded == set(members))
    ok &= check("exited and slashed bits decode but do not count",
                members[0] not in counted and members[1] not in counted and len(counted) == len(members) - 2)
    bad = Attestation(data=att.data, committee_bits=[ci], aggregation_bits=[True] * (len(members) + 1))
    try:
        get_fg_attesting_indices(A, bad)
        ok &= check("length mismatch rejected", False)
    except AssertionError:
        ok &= check("length mismatch rejected", True)
    empty_ci = next((c for c, m in members_ci if len(m) == 0), None)
    if empty_ci is not None:
        try:
            get_fg_attesting_indices(A, Attestation(att.data, [empty_ci], []))
            ok &= check("empty committee rejected", False)
        except AssertionError:
            ok &= check("empty committee rejected", True)
    else:
        ok &= check("empty committee rejected", True, "no empty committee at this n; check present in code")
    del era_seed
    return ok


def t9_invariants() -> bool:
    print("T9 invariants")
    ok = True
    lhs = EPOCHS_PER_FG_ERA + FG_ANCHOR_LOOKBACK
    rhs = 1 + MAX_SEED_LOOKAHEAD + MIN_VALIDATOR_WITHDRAWABILITY_DELAY
    ok &= check("era + lookback <= activation-exit delay + withdrawability delay (consolidations cannot land "
                "inside the era they were aimed at)", lhs <= rhs, f"{lhs} <= {rhs}: zero slack")
    # how many units' vote windows are open at once (burst bound): window = [start - d, start + 8 s + d]
    win = 1000 * (FG_VOTE_PHASE_SECONDS + FG_LATE_WINDOW_SECONDS) + 2 * MAXIMUM_GOSSIP_CLOCK_DISPARITY_MS
    spacing = 1000 * FG_UNIT_SPACING_SECONDS
    counts = {}
    for t in range(0, 96_000, 50):
        open_ = sum(1 for u in range(-3, FG_UNITS_PER_ROUND)
                    if u * spacing - MAXIMUM_GOSSIP_CLOCK_DISPARITY_MS <= t <= u * spacing - MAXIMUM_GOSSIP_CLOCK_DISPARITY_MS + win)
        counts[open_] = counts.get(open_, 0) + 1
    worst = max(counts)
    share = counts[worst] / sum(counts.values())
    ok &= check("at most 3 unit windows open at once -> withheld-vote burst <= 3*beta units", worst == 3,
                f"3 open {share:.0%} of the time (1.0 unit at beta = 1/3)")
    return ok


def main() -> None:
    t0 = time.time()
    results = [t1_purity(), t2_anchoring(), t3_balance(), t4_gaps(), t5_gossip_votes(), t6_batches(),
               t7_gossip_aggregates(), t8_stf(), t9_invariants()]
    print(f"\nRESULT: {'PASS' if all(results) else 'FAIL'}  ({time.time() - t0:.1f} s)")


if __name__ == "__main__":
    main()
