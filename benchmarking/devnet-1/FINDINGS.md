# Devnet 1: measured findings

The comparison site is ready locally at <http://127.0.0.1:8766> (start with
`python3 serve.py`). The comparison covers three configurations. It does **not** support an unconditional “all good” conclusion.

**Corrected to use transaction-loaded windows:** the previous spread window
(slots 50–291) contained only empty payloads. The first regenesis window
(109–132) was also empty. The previous 34.1% traffic comparison is superseded;
its windows and metrics remain in [the saved pre-check result](results/pre-load-comparison.json).

**Main tradeoff:** on matched nodes 1, 2 and 202, partial attestations reduce
estimated received GossipSub RPC traffic by **42.8%** and queued-to-send traffic by
**44.0%**, while the mean of node-level FFG validation-delay p99s rises
from **146.7 ms to 1,177.7 ms**. The changes are observed between successive
capture periods, not an isolated causal estimate or a repeated experiment.

## Captured configurations and comparison windows

| Run | Default common loaded slots | Duration |
| --- | --- | --- |
| 2: Spread | 333–379 | 9.4 min |
| 3: Partial attestations | 580–643, 684–707 | 17.6 min |
| 4: Staggered committees | 251–274, 284–370 | 22.2 min |

Run 3 excludes the 16:56–17:26 UTC rolling restart. Run 4 corresponds to the
archive's "run2-genesis-1930" and uses a separate chain identity.

### Transaction and payload-load evidence

The archived execution blocks place the first transactions at slot
308, **16:31:41 UTC**.
The loaded spread capture starts five minutes later, at slot 333. After
regenesis, slot 132 is still empty and slot 251 is the first captured loaded
slot. The exact second-genesis load-start time is inside a capture gap.

The gate requires transactions and an actual logged payload size of at least
32 KiB for 16 consecutive captured slots on every matched node.
It then retains **every** later common steady slot. All later observed payloads
are checked; a return to empty/small payloads would fail the build. Documented
missed slot 608 stays in Run 3, avoiding a success-only selection.

| Run | UTC windows on 8 October 2026 (end exclusive) | Transactions per payload, min / median / max | Actual payload KiB, min / median / max | Payload slots / selected slots |
| --- | --- | ---: | ---: | ---: |
| 2 | 16:36:41–16:46:05 | 93 / 101 / 110 | 59.8 / 66.1 / 74.5 | 47 / 47 |
| 3 | 17:26:05–17:38:53; 17:46:53–17:51:41 | 81 / 99 / 194 | 53.8 / 64.4 / 122.4 | 87 / 88 |
| 4 | 20:20:12–20:25:00; 20:26:48–20:44:12 | 82 / 87 / 97 | 49.8 / 54.6 / 60.0 | 111 / 111 |

These sizes are the actual `payload.SizeSSZ()` values in Prysm's
`Payload received` logs, not the relative-size model. They exclude the envelope
and blob sidecars. The 2,611 raw payload records reduce to
2,584 unique node/payload observations; repeated imports are deduplicated.
All sampled nodes agree on transaction counts, size, gas, blobs and logged root.
An independent execution export cross-check agrees on transaction counts and
gas for 1,948 node/payload observations across
544 distinct first-genesis slots. Execution RLP block sizes and payload SSZ sizes
are different encodings and are not equated.

The overview includes **Execution payload (applied)** in recorded events and
relative size, with median payload size and transactions beside each run.
Observed timing is the logged processing entry; applied timing is the application
log timestamp. Repeated imports are counted once, and local or fetched payloads
are included. The [payload-profile reconciliation](results/payload-profile-validation.json)
checks every count, size and time bin against the audited payload reduction.
These application records are never added to the independent RPC counters.

The first pane defaults to logged GossipSub bandwidth in KiB/s per node,
with time along the horizontal axis and topic colors stacked in aligned panels
for all three runs. Raw 100 ms bins are shown without Gaussian smoothing.
The topic layers reconcile to the existing RPC totals; the original three-run
overlay remains selectable. See [topic bandwidth checks](results/topic-bandwidth-validation.json).
The relative-size view remains available: columns use their logged cell counts
and beacon blocks use explicitly marked conservative SSZ lower bounds.
Raw bins are its default too; optional 150 ms smoothing preserves their sum. [Object sizing](results/size-model-audit.json) and
[overview checks](results/object-overview-validation.json) document the new
weights; event counts, timestamps, RPC totals and FFG delay statistics are unchanged.

Loaded does not mean identical workload: transaction counts, gas, payload sizes
and blob counts still differ. Run 4 has smaller median payloads as well as the
topology changes below. Devnet 0 stays optional historical context; its notes
report no time to start Spamoor before the crash, so its curve is not certified
as a transaction-loaded comparison.

## Matched three-node measurements

Each entry below is an equal-weight mean across two supernodes (1, 2) and one
home node (202), normalized within each node's common complete capture.
Node 201 has no loaded spread capture; node 200 changes role at regenesis.
The same three nodes are used for every configuration. The single home node
does not establish variability across home nodes.
RPC numbers are KiB/s (1024 bytes); they estimate encoded RPC frames, not complete
wire bandwidth. Queued sending is not proof of delivery.

| Measurement | Run 2: spread | Run 3: partial | Run 4: X=3 |
| --- | ---: | ---: | ---: |
| Received RPC estimate, KiB/s | 1,926.2 | 1,101.0 | 2,496.8 |
| Queued-send RPC estimate, KiB/s | 1,771.3 | 991.3 | 2,239.5 |
| Received FFG success records / slot / node | 4,997.3 | 5,018.6 | 8,308.2 |
| Mean node FFG observed p99 bin lower edge, s | 6.40 | 6.40 | 7.13 |
| Mean node FFG decision-delay p99, ms | 146.7 | 1,177.7 | 285.7 |
| FFG successes delivered via bundles, % | 0.0000 | 99.9998 | 0.0000 |

The observed-arrival statistic has 100 ms bin resolution. Decision delays use
the exact integer-ms paired fields, "decidedMs − arrivedMs", on successful FFG
validation records. They include queue/wait time and are not a CPU benchmark.
These are means of node percentiles, **not** a pooled p99 of all events.

The delay clocks begin at different stages: the classic validation callback
versus the bundle RPC handler before decode/queue/dispatch. Their difference
does not isolate a network propagation change; see [the source model](SOURCE_MODEL.md).

The partial-transport switch is clearly present: almost every successful FFG
record in Run 3 arrives through a bundle; no such records occur in Runs 2 or 4.

### Variation across nodes

| Node | Role | Run 2 received KiB/s / delay p99 ms | Run 3 received KiB/s / delay p99 ms | Run 4 received KiB/s / delay p99 ms |
| --- | --- | ---: | ---: | ---: |
| 1 | Super | 1,956.2 / 178 | 1,195.3 / 1,834 | 2,936.2 / 633 |
| 2 | Super | 2,137.1 / 121 | 1,281.2 / 777 | 3,176.1 / 130 |
| 202 | Home | 1,685.4 / 141 | 826.6 / 922 | 1,378.2 / 94 |

The delay increase is uneven across nodes. Node 1 reaches 1,834 ms p99 with
partials, node 2 reaches 777 ms, and node 202 reaches 922 ms. An average alone
would hide this difference. About 0.248% of node 1's successful FFG decisions in the
partial steady window occur after 9 s relative to their object slot. This
does not by itself prove an aggregation failure: a committee's full lifecycle
and inclusion are different measurements.

### Where the received bytes go

| RPC category, KiB/s | Run 2 | Run 3 | Run 4 |
| --- | ---: | ---: | ---: |
| Published messages | 1,400.2 | 469.3 | 1,972.0 |
| Partial-message extension | 0.0 | 529.4 | 0.0 |
| Control messages | 517.9 | 99.9 | 513.3 |
| RPC framing | 8.2 | 2.5 | 11.6 |
| Other | 0.0 | 0.0 | 0.0 |

Run 3's control-byte estimate falls by 80.7%. The partial extension costs are
already included in its total. Topic totals and "pm_*" subtotals are never
added a second time. Repeated copies to/from peers remain included in RPC traffic.

## Why Run 4 is not a clean X=3 versus X=1 experiment

Regenesis changes 40,300 validators to 80,400; 200 supernodes × 200 validators
to 100 × 800; two attestation subnets to four; and the committee schedule to
12 committees per slot. It disables partial attestations. The spread flag is
ignored by this code when X≥2. Node 200 changes from super to home and is not
in the matched cohort. First-genesis CLI/config snapshots are present; the
regenesis configuration has only README evidence plus corroborating behavior.

In the matched supers, mean received RPC estimates are 3,056.1 KiB/s; in
the matched home node 202 they are 1,378.2 KiB/s. Compare these separately rather
than interpreting the three-node average as the mean over the network's new
100-super/400-home population. No result here isolates the causal effect of X.

## Progress and operational concerns

- The matched nodes record block imports and progressing finalized slots in all
  three steady datasets. Logged finalized-slot lag has median 19–20 slots and
  maximum 23 slots in these samples. This is bounded progress evidence, not
  verification of agreement or safety across the network.
- The three matched nodes have no import for slot 608 in the partial
  comparison, a missed slot documented by the archive author. It stays in
  the loaded-window denominator. Every selected spread and X=3 comparison
  slot has an import on these three nodes.
- The archive author reports stuck nodes 98, 99, 355, and regenesis node 376.
  Import logs alone cannot confirm recovery of a head stuck on a payload;
  some of those nodes log later block imports. Node 376's final peer samples
  are explicitly zero. The website presents peer counts and import milestones
  separately rather than declaring nodes healthy from imports alone.
- No replay of finalization/safety, CPU profile analysis, execution correctness
  audit or network-wide health certification was performed. Archived live DB
  and Prometheus snapshots have documented consistency caveats and remain packed.

For a clean follow-up, retain the same topology/validator allocation and
instrumented cohort, archive effective CLI/config at every transition, and
repeat each steady configuration. For partials,
investigate the per-node validation queue/tail before treating traffic savings
as an unqualified improvement.

## Data handling and validation

- Input: 1.549 GB compressed; 597 members inventoried.
  Approximately 28.3 GB of beacon/validator log text was inspected as streams,
  including redundant copies. No archive directory was expanded on disk.
- 73 non-overlapping source members; 85,056,534 source lines;
  49,613,913 observed events and 49,520,723 accepted events
  before steady/cohort filters; zero matched-record parser failures.
- Throttled ClickHouse copies, overlapping intervals and partial boundary slots
  cannot inflate the quantitative comparison. Missing capture/tracer coverage
  is not filled with invented events or zero-bandwidth samples.
- Cache counts, byte-component conservation, full-slot ownership, and all 8,310
  block clock anchors were checked. The independent raw-reader reproduces
  observed/accepted FFG bins for slots 350, 620 and 300 (one per configuration)
  and their received-RPC integrals. This is a three-sample cross-check, not a
  second independent full ingestion.
- Block logger versus elapsed-field residual has p99 9.87 ms and maximum
  44.05 ms; five anchors exceed 10 ms. The source samples elapsed time before
  assembling the log record, so these are not simultaneous clocks. They remain
  within the 100 ms plotting resolution; explicit FFG decision fields do not
  use this proxy.
- Outer gzip CRC passes and the final archive SHA-256 matches the initial hash:
  `fb58d86cf3d86e5a08eba936b22d8e6d53d9d08dda1919a5805be135b199a7d1`.
- Python ingestion tests, Node statistics tests, and the real application's
  automated DOM harness pass. HTTP endpoints are checked separately. Visual
  browser QA was blocked because computer-use access to Firefox was not approved.

Evidence: [archive notes](results/archive-README.md), [manifest](results/source-manifest.json),
[source selection](results/source-selection.json), [audit](results/audit.json),
[independent verification](results/verification.json), [UI checks](results/site-validation.json),
[load validation](results/load-validation.json), [per-slot payload evidence](results/payload-observations.json),
[machine-readable metrics](results/metrics.json), and [source semantics](SOURCE_MODEL.md).
