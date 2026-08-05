# SSZ and wire objects for decoupled consensus

Status: working PoC note, 2026-07-23.

This note answers three implementation questions:

1. What does each decoupled-consensus vote say?
2. How is it represented in SSZ?
3. What traffic and on-chain load should the PoC model?

The baseline here is the executable
[`simplex-healing`](https://github.com/fradamt/consensus-specs/tree/simplex-healing)
specification (`d8673c6`, 2026-07-13). The newer healing paper
(`height_filter_healing.tex`,
`860a1b0`, 2026-07-20) is used to identify semantic changes and open
theory-to-spec questions. The binding DC networking parameters remain in
[`requirements.md`](../design/requirements.md).

## Which vote streams exist?

The vetted DC requirements specify two kinds of traffic:

1. **AC / available-chain votes** from a small per-slot committee.
2. **FG / finality-gadget votes** from the full validator set, divided into
   pipelined subrounds.

The executable Simplex spec has the same two validator attestation types:

- `AvailableAttestation`, one per available-committee member per slot;
- `Attestation`, one per full-set validator per round.

Older AC notes explored merging Goldfish, payload availability, and finality
fields into one committee message. That is not the current baseline: a
512-member AC committee cannot replace the supermajority of the full active set
needed for finality.

## AC / Goldfish available vote

The executable containers are:

```python
class AvailableAttestationData(Container):
    slot: Slot
    payload_present: boolean
    beacon_block_root: Root

class AvailableAttestation(Container):
    aggregation_bits: Bitvector[AVAILABLE_COMMITTEE_SIZE]  # 512
    data: AvailableAttestationData
    signature: BLSSignature
```

Source:
[`beacon-chain.md`](https://github.com/fradamt/consensus-specs/blob/simplex-healing/specs/_features/simplex/beacon-chain.md#availableattestationdata).

Conceptually, Goldfish votes for a block head. On the wire it cannot safely be
an unqualified root: the signed object also needs time/duty context to prevent
replay. The current Gloas-flavoured executable design additionally carries the
payload-availability signal.

Exact uncompressed SSZ sizes:

| Object | Calculation | Bytes |
|---|---:|---:|
| `AvailableAttestationData` | `8 + 1 + 32` | 41 |
| `AvailableAttestation` | `64 + 41 + 96` | 201 |

The 512-bit aggregation vector is 64 bytes. Because it is fixed-size, an
individual one-hot message and a fully aggregated message have the same
serialized length.

## FG finality and stabilization vote

There is no separate "finality chain." The available chain, stabilization
gadget, and finality gadget all refer to checkpoints or blocks in the same
beacon block tree. The combined fork choice is:

```text
latest justified checkpoint
    -> stabilized prefix
        -> Goldfish available suffix
```

The public
[decoupled-consensus post](https://ethresear.ch/t/unblocking-faster-finality-with-decoupled-consensus/24527)
describes stabilization and finality as one gadget voting round.

The executable containers are:

```python
class Checkpoint(Container):
    slot: Slot
    root: Root

class AttestationData(Container):
    slot: Slot
    beacon_block_root: Root
    target: Checkpoint
    height: Height
    finality_target: Checkpoint
    finality_height: Height
```

The fields mean:

- `slot`: vote time and round context;
- `beacon_block_root`: the voter's latest stabilization head;
- `height + target`: the checkpoint proposed for justification;
- `finality_height + finality_target`: an optional commitment to finalize the
  latest justified checkpoint.

The three FG vote forms do not use an explicit `vote_kind` byte:

| Logical vote | Encoding |
|---|---|
| Target / justification | nonzero `target`, real `height` |
| Timeout | zero `target`, real `height` |
| Empty | zero `target`, `height == 0` |

No finality piggyback is encoded as a zero `finality_target` and
`FAR_FUTURE_HEIGHT`.

The individual Electra gossip envelope inherited by Simplex is:

```python
class SingleAttestation(Container):
    committee_index: CommitteeIndex
    attester_index: ValidatorIndex
    data: AttestationData
    signature: BLSSignature
```

Sources:
[`AttestationData`](https://github.com/fradamt/consensus-specs/blob/simplex-healing/specs/_features/simplex/beacon-chain.md#attestationdata)
and
[`SingleAttestation`](https://github.com/fradamt/consensus-specs/blob/simplex-healing/specs/electra/beacon-chain.md#singleattestation).

Exact uncompressed SSZ sizes:

| Object | Calculation | Bytes |
|---|---:|---:|
| `Checkpoint` | `8 + 32` | 40 |
| `AttestationData` | `8 + 32 + 40 + 8 + 40 + 8` | 136 |
| `SingleAttestation` | `8 + 8 + 136 + 96` | 248 |

Thus the DC requirement's "individual vote approximately 100 B" is not the
size of the current standard SSZ object. A BLS signature alone is 96 bytes.
Approximately 100 bytes per signer is plausible only for a compact batch that
sends common vote data once and then carries mostly signer positions and
signatures. That is a separate wire-format experiment.

### Deprecated minimal vote

An older, now-deprecated networking exploration used:

```python
class FinalityGadgetVote(Container):
    height: uint64
    block_root: Root
    vote_kind: uint8
    validator_index: ValidatorIndex
    signature: BLSSignature
```

Its size was `8 + 32 + 1 + 8 + 96 = 145` bytes. It represented the simpler
alphabet `Vote(B)`, `Vote(bottom)`, and `SecondVote(B)`. It is useful for
explaining the old approximately-100-byte assumption, but it lacks the latest
healing design's stabilization head, checkpoint slot, and finality piggyback.
It must not be used as the current PoC schema.

## Aggregate size and the 125 kB bitfield

BLS can aggregate many signatures on identical data into one 96-byte
signature. The verifier still needs to know exactly which validators signed:
their public keys and voting weights determine whether the threshold was
reached. Ethereum represents that set with a participation bitfield.

For one million validator seats:

```text
1,000,000 bits / 8 = 125,000 bytes = approximately 122.1 KiB
```

This is the participation bitmap for one complete full-set round, not one
validator's vote.

With ten 100,000-seat subrounds:

```text
100,000 bits / 8 = 12,500 bytes per subround
10 * 12,500      = 125,000 bytes per complete round
```

SSZ `Bitlist` serialization adds a termination bit. For one ideal 100,000-seat
subround with one common `AttestationData` value:

```text
fixed Attestation section                 248 bytes
aggregation Bitlist ceil((100000 + 1)/8) 12501 bytes
---------------------------------------------------
on-chain Attestation                     12749 bytes
```

The fixed section includes two four-byte offsets, the 136-byte data, the
96-byte aggregate signature, and the eight-byte mainnet committee bitvector.
The global `SignedAggregateAndProof` gossip wrapper adds 208 bytes, yielding
12,957 bytes before transport compression.

Ten ideal 100,000-seat on-chain aggregates therefore occupy 127,490 bytes
(about 124.5 KiB) across the complete round. The DC explainer's
"approximately 12.5 kB per subround" is the same calculation rounded to the
dominant bitfield.

An optional `HistoricalBlockProof` for an old, noncanonical target adds 904
bytes to an on-chain attestation.

### Fragmentation matters

Ordinary BLS fast aggregation combines signatures only when validators signed
identical `AttestationData`. Different:

- stabilization heads;
- justification targets;
- finality piggybacks; or
- slots

require separate `Attestation` aggregates. Each aggregate carries its own
bitfield and signature. The 12.5 kB estimate is therefore a good-path lower
bound for a subround whose voters largely agree. The PoC should measure
aggregate fragmentation under delayed, partitioned, and healing scenarios.

## Healing paper: SG pre-vote caveat

The latest LaTeX healing paper models an additional ordering step. After
Goldfish confirmation, validator `i` signs an SG (stabilization gadget) head
pre-vote:

```text
(validator i, round r, head B_i)
```

Its later FG message repeats the same round and head. The paper calls these two
copies of the same logical head vote. See
`Live latest head vote`
and the paper's `Round schedule and state processing` section.

This appeared in the repaired healing protocol on 2026-07-17 (`55e88cdc`) and
was updated in the canonical healing paper on 2026-07-18 (`e7785512`).

There is currently:

- no separate SG-pre-vote SSZ container in Francesco's executable spec;
- no third vote stream in the vetted DC networking requirements;
- an explicit open DC question about how healing affects networking and
  whether SG is on chain.

The executable spec instead uses `AttestationData.beacon_block_root` as the
network-received SG latest-head vote. A hypothetical direct encoding of the
paper's `(validator, round, head)` pre-vote would be 144 bytes with BLS, but
that number is an inference, not a specified Ethereum wire object.

For the baseline PoC, do not add a separate SG-pre-vote stream. Treat it as a
named experiment or theory-to-spec integration decision.

## PoC baseline

The networking PoC should initially model:

1. `AvailableAttestation` at 201 bytes from a 512-seat committee each slot.
2. `SingleAttestation` at 248 bytes from each scheduled FG validator.
3. Standard committee aggregation into the modified `Attestation`.
4. One aggregate-and-proof wrapper per published aggregate.
5. Vote-data disagreement and the resulting aggregate fragmentation.
6. Vote in slot `i`, aggregate in `i+1`, include in `i+2`, as specified in
   [`explainer.md`](../design/explainer.md).

Run compact batching and a separate healing SG pre-vote only as explicitly
labelled variants. This keeps the baseline aligned with both the conservative
"standard gossip vertical" decision and the executable specification while
making the unresolved healing traffic visible.
