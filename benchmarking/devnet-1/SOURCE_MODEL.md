# What the instruments measure

This analysis pins Sukun's Prysm at
`6c026c484c05c256c7858e9f4a1e8580dd898dbe`. The first-genesis beacon and validator
startup logs name this exact build. Regenesis is identified as `6c026c4` by the
archive README; its startup/config files are not present. The separate checkout
is `.sources/prysm`.

The tracing dependency is `github.com/sukunrt/go-gossipsub-trace v0.0.2`, pinned
by Prysm's `go.mod`, downloaded at
`34fd981da89c00b24832e3cf1517fe56739dea58` into `.sources/go-gossipsub-trace`.
No running client was changed and neither checkout was compiled for this analysis.

## The three compared configurations

The comparison retains the established run labels. The archive calls the
regenesis experiment **Run 2**; the website calls it **Run 4**.

| Run | Archived evidence | Interpretation |
| --- | --- | --- |
| 2: spread | `full-start-1628` contains CLI, config and startup logs. | 40,300 validators, 200 supernodes × 200 validators, 300 home nodes × 1; two subnets. |
| 3: spread + partial | `post-partial/full-start-1739` contains CLI snapshots and logs. README records a rolling restart from 16:56–17:26 UTC. | Same chain/topology. Only slots starting after completion enter steady comparisons. |
| 4: X=3, regenesis | `run2-genesis-1930`; README describes the configuration. No equivalent CLI/config snapshot. | 80,400 validators, 100 supernodes × 800, 400 home nodes × 1; four subnets. Partial disabled. Node 200 is now a home node. |

All slots are 12 s; rounds contain 8 slots. Genesis is 15:30:05 UTC for the
first chain and 19:30:00 UTC for regenesis, on 2026-10-08.

The slot-start flag is already always effective from Heze. With spread and
the configured 9 s aggregate due time, the implementation divides the
committee into seven groups sent at 0, 1, …, 6 s, plus up to 200 ms jitter.
At X≥2, the spread flag is ignored. X=3 schedules committee batches at
0, 3 and 6 s, with aggregation at 3, 6 and 9 s.

X also overrides the committee count: X × subnet count = 12 committees per
slot after regenesis, regardless of the nominal target committee size 2500.
Thus committee lengths are 837 or 838, compared with 2518 or 2519 before
regenesis. These are implementation-derived schedule sizes, not counts of
successfully participating validators.

Source: [flags](https://github.com/sukunrt/prysm/blob/6c026c484c05c256c7858e9f4a1e8580dd898dbe/config/features/flags.go),
[vote submission](https://github.com/sukunrt/prysm/blob/6c026c484c05c256c7858e9f4a1e8580dd898dbe/validator/client/attest.go),
[timing helpers](https://github.com/sukunrt/prysm/blob/6c026c484c05c256c7858e9f4a1e8580dd898dbe/validator/client/wait_helpers.go),
[aggregation](https://github.com/sukunrt/prysm/blob/6c026c484c05c256c7858e9f4a1e8580dd898dbe/validator/client/aggregate.go),
[committee count](https://github.com/sukunrt/prysm/blob/6c026c484c05c256c7858e9f4a1e8580dd898dbe/beacon-chain/core/helpers/beacon_committee.go).

## Vote lifecycle and timing

`arrivedMs` is relative to the object's slot and records entry into the available
validation path. It is not a packet receive timestamp common to every object.
Classic FFG records start at the validation callback; bundled FFG records start
at the partial RPC handler before its decode/queue/dispatch stages. Their paired
delays therefore cover different stages and do not isolate a propagation change.
FFG success rows now contain `decidedMs`, `transport=gossip|bundle`, `dataRoot`
and sender. The difference `decidedMs − arrivedMs` is a logged validation-path
delay, including waits; it is neither pure CPU time nor network propagation.
FFG records are emitted after validation succeeds: this is a conditional sample,
not all arriving or invalid votes.

AC (`Goldfish vote`) can be queued before its block is available. Original
non-replay observations and successful decisions are separate projections.
For each node, object slot, block root and validator, the importer retains the
earliest original observation and earliest successful acceptance. Replay
`arrivedMs` is a retry-entry time and is never used as the original arrival.
A validator can hold multiple of the 512 AC seats; `seats=2` with one validator
is a valid single message. The analysis preserves both message and seat counts.
De-duplication occurs within each selected member; whole-slot source ownership
prevents overlapping captures. Boundary-spanning orphan lifecycles remain
audited, not synthesized.

Successful FFG aggregate/PTC records do not have the new explicit decision
timestamp. Their accepted projection uses the node logger's timestamp, at
10 ms resolution for the colored logger. Ignored FFG aggregates have
`outcome=ignored` and are kept out of accepted/observed-success curves, with a
separate selectable view. Their byte cost is already in the RPC instrument.

Block and payload times are processing/import milestones. No chart proves
agreement of finalized chains. Block import gaps are node observations; they
are not automatically network-wide missed slots.

Source: [vote ledger](https://github.com/sukunrt/prysm/blob/6c026c484c05c256c7858e9f4a1e8580dd898dbe/beacon-chain/sync/vote_ledger.go),
[pending queue](https://github.com/sukunrt/prysm/blob/6c026c484c05c256c7858e9f4a1e8580dd898dbe/beacon-chain/sync/pending_attestations_queue.go),
[AC seat mapping](https://github.com/sukunrt/prysm/blob/6c026c484c05c256c7858e9f4a1e8580dd898dbe/decoupled/available_attestation_committee.go),
[bundle processing](https://github.com/sukunrt/prysm/blob/6c026c484c05c256c7858e9f4a1e8580dd898dbe/beacon-chain/p2p/partialattestationbroadcaster/partial.go).

## Payload load from actual logs

`logPayloadEnvelope` emits `Payload received` after applying an execution
payload envelope. It records `txCount = len(txs)`, `payloadBytes =
payload.SizeSSZ()`, `gasUsed`, and the committed `blobCount`, along with the
object slot and logged block-root prefix. All delivery paths reach this
function, including initial sync and the proposer's own publish. Repeated
imports must therefore be deduplicated rather than treated as independent
blocks or as network traffic. These are successfully applied payloads, not
every received envelope or a record of Spamoor's launch time.

`analysis/payload_load.py` keeps those actual fields for the four instrumented
nodes, retaining source hashes and canonical capture ownership. The builder
uses the same three nodes with loaded coverage across every run: 1, 2 and 202.
Their transaction counts, payload sizes, gas, blobs and logged roots agree
where samples overlap. Node 1's execution-block export independently confirms
first-genesis transaction counts and gas. Its RLP block size is retained as a
different quantity and is never equated to SSZ payload size.

The comparison gate and exact windows are documented in [README.md](README.md)
and [the load audit](results/load-validation.json). The 32 KiB threshold and
16-slot confirmation are explicit analysis choices, not protocol parameters
or a claim that load rates were identical. Missed slot 608 stays in the
comparison; the window is not filtered down to successful payload slots.
Payload bytes exclude the signed envelope and blob sidecars. The overview now
includes a separate **Execution payload (applied)** object, populated from these
audited records. Observed timing uses `arrivedMs` at processing entry; applied
timing uses the logger timestamp after application (about 10 ms resolution).
Repeated imports of a slot/root use the earliest processing-entry record. Local
proposals and fetched payloads are included because this logger does not identify
a gossip-only origin. The relative-size view uses actual payload SSZ bytes divided
by 240, without assigning a size to the surrounding envelope or blob sidecars.
These application records are never added to the independent RPC-byte counters.

Source: [payload logging at the pinned commit](https://github.com/sukunrt/prysm/blob/6c026c484c05c256c7858e9f4a1e8580dd898dbe/beacon-chain/blockchain/receive_execution_payload_envelope.go#L196).

## Network byte instruments, kept separate

1. **GossipSub RPC estimates.** `gossipsub bandwidth` reports interval deltas
   for received, queued-to-send and dropped RPCs. Sizes are re-encoded protobuf
   RPC size plus unsigned-varint length prefix. They include copies, control
   traffic and partial-message extensions. They exclude transport, encryption,
   multiplexing and retransmission overhead, and frames rejected before the
   hook. Sending is a queue milestone, not confirmed delivery. Dropped bytes
   are never added to sent bytes.
2. **Topic attribution.** Topic records partition the same totals and are never
   added to them. IWANT/IDONTWANT attribution relies on an expiring ID-to-topic
   cache; shared and unassigned bytes remain unattributed. `pm_*` fields are
   subsets of `partial_bytes`, not extra traffic. The importer verifies that
   published, partial, control, overhead and other bytes sum to each total.
3. **P2P host counters.** `P2P bandwidth` contains cumulative libp2p counters and
   separate attestation-family subcounters. Differences are computed only
   within one source and continuous intervals, excluding resets/gaps. These
   are available in reductions/summary JSON and do not get added to RPC bytes.

The 100 ms traffic plots distribute each report's bytes proportionally over its
actual `interval_ms`; they do not reconstruct individual packet times. Topic
rates use all-topic tracer exposure, avoiding a bias from omitted idle topic
records. Topic slot totals in the audit detail use report-end allocation and
are not the high-resolution plotting source. The bandwidth overview aligns each
topic row to its preceding all-topic report (same `interval_ms`). The pinned
tracer takes one atomic snapshot, then logs the total before its topic rows;
using each topic logger timestamp separately would shift some bytes between
adjacent bins. The original reduction is preserved, while the new topic plots
use this corrected alignment. All-topic curves and overall RPC metrics stay
unchanged.

Source: [tracer measurement semantics](https://github.com/sukunrt/go-gossipsub-trace/blob/34fd981da89c00b24832e3cf1517fe56739dea58/README.md),
[tracer implementation](https://github.com/sukunrt/go-gossipsub-trace/blob/34fd981da89c00b24832e3cf1517fe56739dea58/tracer.go),
[Prysm host counters](https://github.com/sukunrt/prysm/blob/6c026c484c05c256c7858e9f4a1e8580dd898dbe/beacon-chain/p2p/monitoring.go).

## SSZ model versus devnet 0

The original devnet-0 reducer is kept. Its existing schema-3 reduction is
imported as historical context with its original size and timing assumptions;
no RPC-byte comparison is invented for it.

| Object | Devnet 1 accounting |
| --- | --- |
| Single FFG vote | 240 uncompressed SSZ bytes, including a logical vote delivered through a bundle |
| AC | 205 fixed bytes + scratch bytes. First genesis config sets 100 → 305 bytes. Regenesis uses only the 205-byte structural lower bound because its config snapshot is missing. |
| Gossip FFG aggregate | 100 + 108 + 236 + committee bitlist length, including delimiter: 759 bytes before regenesis; 549 after. |
| PTC | 146 bytes |
| Execution payload (applied) | Actual logged `payloadBytes` SSZ size; excludes envelope and blob sidecars. Available for the four nodes in the payload audit. |
| Data columns | For the matched nodes: 56 + 2096 × logged cell count. Full Gloas sidecar object size, irrespective of a partial transport path. |
| Beacon blocks | For the matched nodes: ≥924 bytes plus conservative weights for logged list counts; not the 208-byte standalone header. |
| Historical payload envelopes | Original devnet-0 model retained: logged payload size plus a conservative signed-envelope overhead. |

AC's former devnet-0 weight of 201 bytes cannot be reused for this revision.
Likewise a bundled FFG vote's 240-byte logical size is not its incremental
network cost. Modeled SSZ volume and measured RPC estimates answer different
questions and must not be added together.

Source: generated SSZ files under
[proto/prysm/v1alpha1](https://github.com/sukunrt/prysm/tree/6c026c484c05c256c7858e9f4a1e8580dd898dbe/proto/prysm/v1alpha1),
and scratch generation in
[attester.go](https://github.com/sukunrt/prysm/blob/6c026c484c05c256c7858e9f4a1e8580dd898dbe/beacon-chain/rpc/prysm/v1alpha1/validator/attester.go).

## Payload and Goldfish reception CDFs

The comparison View selector offers **Payload reception · CDF** and
**Goldfish votes · CDF**, each overlaying the three runs. These reuse the
existing loaded-window event profiles; no raw logs are read again.

Each node's CDF is normalized by its count of recorded observations, then node
CDFs are averaged with equal weight. The X axis is seconds after the object's
slot start; Y is cumulative percentage. Steps use the upper edges of the raw
100 ms bins, without smoothing. Events before zero contribute at zero; events
after 12 s remain in the denominator. Missing observations are excluded, and a
node with no observations has no CDF. These curves do not estimate the fraction
of expected validators or payloads received. Bands describe the same node sample
as other views; percentage bounds stay within 0–100.

Payload observations are deduplicated successful application records, using
processing-entry `arrivedMs`. They include local proposals and fetched payloads:
this is a reception proxy, not a packet-arrival measurement. The documented
missed slot 608 contributes no payload observation. The three runs have 47, 87,
and 111 payload observations per matched node, respectively. Devnet 0 does not
have this payload instrumentation and has no comparable payload CDF.

Goldfish uses the first non-replay observation per deduplicated vote lifecycle,
including queued votes, and excludes local production. Each recorded vote counts
once regardless of how many committee seats it carries. The CDF ignores the
separate Accepted/Applied, FFG transport, object-size and smoothing selectors.
CSV exports include the time threshold, percentages and per-node sample counts.

## Object layers in the overview

The first pane defaults to logged GossipSub RPC bandwidth in KiB/s per node,
stacked by topic with one panel per run and a shared vertical scale. Time stays
on the horizontal axis. Raw 100 ms bins are displayed as steps, without Gaussian
smoothing. The existing three-run overlay remains under Display.

`analysis/topic_bandwidth.py` streams the selected matched-node sources directly
from the packed archive and verifies their expanded hashes. It retains topic
counters only in the already-verified loaded windows. Topic layers sum to the
original all-topic RPC counters in every bin and direction; all-topic exposure
is the denominator for every topic. Other topics and unassigned control share
the gray layer. The report at `results/topic-bandwidth-validation.json` checks
this partition and reconciles the existing all-topic profiles, allowing
only their original five-decimal per-slot cache rounding. Topic-only curves
use the corrected report alignment described above. Application-log SSZ
sizes are never substituted for these RPC counters.

The relative SSZ size view remains selectable. One unit is one 240-byte FFG vote.
Raw bins are the default there too. Its optional 150 ms Gaussian redistributes
bin values with boundary normalization, preserving their sum; both raw and
displayed values are exported.
The plot covers 0–12 s; late events remain in the reduction but outside the plot.
These are successfully recorded/processed logical objects, not outgoing traffic,
GossipSub control traffic, or the compressed size of bundled signatures.

`analysis/object_sizes.py` streams the selected logs for nodes 1, 2 and 202,
verifies their expanded hashes, and keeps only missing size metadata in
[the compact evidence](results/size-observations.json.gz). No archive member is
extracted. Column records log their cell count; the pinned Gloas SSZ schema is
56 fixed bytes + 2048 bytes per cell + 48 bytes per KZG proof. The validated
column wrapper guarantees matching cell/proof counts.

For blocks, the pinned signed block, body, bid and empty requests total at least
924 bytes. Unique node/slot block-transition joins add 241 bytes per included
attestation (minimum bitlist), 48 per blob commitment, 416 per proposer slashing
and 112 per voluntary exit. Missing or ambiguous joins use the 924-byte floor.
Unlogged lists and full attestation bitlist lengths are not guessed. These yellow
bands are marked **≥**. Regenesis Goldfish weights also remain structural lower
bounds because the scratch-space configuration was not archived. Other captured
nodes keep their previous unmodeled column/block markers.

The [sizing audit](results/size-model-audit.json) records source hashes and formulas;
[overview reconciliation](results/object-overview-validation.json) checks complete
size coverage in the matched cohort and unchanged event counts, clocks and RPCs.
Source: [Gloas SSZ definitions](https://github.com/sukunrt/prysm/blob/6c026c484c05c256c7858e9f4a1e8580dd898dbe/proto/prysm/v1alpha1/gloas.ssz.go),
[execution-request SSZ](https://github.com/sukunrt/prysm/blob/6c026c484c05c256c7858e9f4a1e8580dd898dbe/proto/engine/v1/engine.ssz.go),
[column logging](https://github.com/sukunrt/prysm/blob/6c026c484c05c256c7858e9f4a1e8580dd898dbe/beacon-chain/sync/vote_ledger.go),
[block logging](https://github.com/sukunrt/prysm/blob/6c026c484c05c256c7858e9f4a1e8580dd898dbe/beacon-chain/blockchain/log_helpers.go).
