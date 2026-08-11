# Specs

The DC networking spec itself is still to come. Until then, the reference
specification for the two vote streams is Francesco's executable Simplex
pyspec:

**[`fradamt/consensus-specs`, branch `simplex-healing`](https://github.com/fradamt/consensus-specs/tree/simplex-healing)**
— the finality gadget (fresh Simplex with height filter and timeouts) layered
on Gloas, replacing Casper FFG. Tip as of 2026-08-11: `5750e57` (2026-07-27).

| File | What it gives us |
|---|---|
| [`p2p-interface.md`](https://github.com/fradamt/consensus-specs/blob/simplex-healing/specs/_features/simplex/p2p-interface.md) | The wire layer: new global topic [`available_attestation`](https://github.com/fradamt/consensus-specs/blob/simplex-healing/specs/_features/simplex/p2p-interface.md#new-available_attestation) (AC votes, 512-to-all) and [modified `beacon_attestation_{subnet_id}`](https://github.com/fradamt/consensus-specs/blob/simplex-healing/specs/_features/simplex/p2p-interface.md#modified-beacon_attestation_subnet_id) (FG votes on committee subnets), plus gossip validation, `Seen` equivocation tracking, and Status v3 |
| [`beacon-chain.md`](https://github.com/fradamt/consensus-specs/blob/simplex-healing/specs/_features/simplex/beacon-chain.md) | SSZ containers (`AvailableAttestation`, the reworked `AttestationData`) and state transition — the byte accounting in [`../research/ssz.md`](../research/ssz.md) is derived from here |
| [`fork-choice.md`](https://github.com/fradamt/consensus-specs/blob/simplex-healing/specs/_features/simplex/fork-choice.md) | Height filter, anchor/grade layer, Goldfish descent, confirmation rule |
| [`validator.md`](https://github.com/fradamt/consensus-specs/blob/simplex-healing/specs/_features/simplex/validator.md) | Honest-validator duties: when each vote is produced, aggregation duty |
| [`configs/mainnet.yaml`](https://github.com/fradamt/consensus-specs/blob/simplex-healing/configs/mainnet.yaml) | `# Simplex` block — round schedule (`SLOTS_PER_ROUND`) and gadget constants |

Sibling branch
[`simplex-height-filter`](https://github.com/fradamt/consensus-specs/tree/simplex-height-filter)
is the height-filter base without the healing layer — a diff target, not an
ancestor of `simplex-healing`.

**Caveats for networking work.** The pyspec fixes vote *semantics* and vote
*objects*, not our delivery design: it inherits today's subnet/aggregator
propagation, whereas the DC proposal pipelines FG rounds across slots and
stretches the vote window over two slots (see
[`../design/explainer.md`](../design/explainer.md)). Where the two disagree,
[`../design/requirements.md`](../design/requirements.md) is binding for
networking parameters. The spec also trails the theory: the blessed protocol
document is `height_filter_healing.tex`.
