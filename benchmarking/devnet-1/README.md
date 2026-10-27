# Devnet 1 comparison

Reproducible comparison of the 2026-10-08 Devnet 1 archive, read without
extracting it. The dashboard is hosted on OpenAI Sites:
<https://dc-devnet-1-comparison.citrusvole32.chatgpt.site>.

Open the website:

```sh
cd benchmarking/devnet-1
python3 serve.py
```

Visit <http://127.0.0.1:8766>. `web/index.html` also opens the comparison overview
directly from disk; slot detail needs HTTP. Everything runs locally. No assets,
fonts or analytics load from another service. The dashboard data (`web/`
reductions and `data/`) is not in Git: build it with the steps under
[Reproduce](#reproduce). [PUBLISHING.md](PUBLISHING.md) covers the hosted copy.

The interface provides matched super/home comparisons, Observed and Accepted
timing, ignored aggregates, classic/bundle FFG filters, relative SSZ volume,
GossipSub RPC traffic, payload-reception and Goldfish-vote CDFs, FFG decision-delay
CDFs, node ranges/descriptive intervals,
single-slot inspection, CSV exports, and capture/health/provenance tables.
Devnet 0 is optional historical context with its original instrumentation.
The first pane opens on topic-stacked RPC bandwidth (KiB/s per node), using
raw 100 ms bins. Display → Run totals overlays the three runs. Relative SSZ
object sizes remain a separate view. Topic counters and validation can be
regenerated with `python3 analysis/topic_bandwidth.py`, which streams the packed
archive without extracting it.

Read [FINDINGS.md](FINDINGS.md) for measured results and limitations,
[SOURCE_MODEL.md](SOURCE_MODEL.md) for the pinned instrumentation semantics,
and [the archive's original notes](results/archive-README.md) for run provenance.

## Reproduce

Python 3.11+ and its standard library suffice. Node is needed only for UI-statistic
tests. By default the archive is discovered in a `devnet-1.nosync/` folder next
to the repository checkout.

```sh
python3 analysis/inventory.py
python3 analysis/ingest.py
python3 analysis/payload_load.py
python3 analysis/object_sizes.py
python3 analysis/build_site.py
python3 analysis/verify_payload_profiles.py
python3 analysis/verify_object_overview.py
python3 -m unittest discover -s analysis -p 'test_*.py'
node --test analysis/test_stats.cjs
node analysis/test_app.cjs
python3 analysis/verify.py
node analysis/report.cjs
```

`inventory.py --archive /absolute/path/archive.tar.gz` selects another location
for the **same capture format**. Dataset identity, genesi, schedules and phase
boundaries are explicit in the adapter; this is not a generic Ethereum parser.
Do not reuse it for another devnet without checking those assumptions.

Inventory reads tar members and nested gzip log streams in bounded chunks.
Ingestion streams one selected member at a time and stores only reductions.
No `extract`/`extractall` call, raw-log copy, Prometheus unpacking, beacon DB
copy, or execution DB export is performed. Metadata extraction is limited to
the archive README, hashes, time bounds and relevant configuration fields.
The 1.55 GB compressed archive contains about 28.3 GB of log text, including
overlapping copies; those bytes are never materialized on disk.

Each full node/wall-clock slot has exactly one owner. Complete start-to-end
captures take precedence, followed by longer Docker windows. The throttled
ClickHouse copies at the archive root are excluded. Partial boundary slots are
excluded rather than treated as complete. Slots 0–49 and rollout slots are
excluded from the steady comparison. The comparison additionally starts only
after logged transaction counts and actual payload sizes verify sustained load
(see the workload policy below). Warm-up slots remain in per-node detail;
rollout records remain in the per-member caches and audit, outside the website's
steady datasets. AC lifecycles are reduced within a member; possible
orphans at source boundaries are counted in the audit.

`.cache` keys contain the member SHA-256, parser hash, source name and selected
slots. Interrupted ingestion resumes completed members. `--force` reprocesses
all selected inputs. Source and archive hashes are checked; the original archive
must remain unchanged. For any code change that affects the format, regenerate
the website from the matching caches. `--allow-incomplete` is a development-only
preview and prominently marks the site provisional.

## Files

| Path | Purpose |
| --- | --- |
| `analysis/inventory.py`, `ingest.py`, `build_site.py` | Reproducible streaming pipeline |
| `web/` | Local comparison site and lazy per-node detail |
| `results/source-manifest.json` | Archive/member hashes, coverage, selected config evidence |
| `results/source-selection.json` | Source ownership and parser fingerprint |
| `results/audit.json` | Accounting, excluded records, errors and warnings by member |
| `results/summary.json` | Run identity, default windows, quality summary |
| `analysis/payload_load.py`, `results/payload-observations.json` | Streamed actual transaction counts, SSZ payload sizes and independent execution-block evidence |
| `results/load-validation.json` | Loaded-window selection, per-slot evidence, cross-checks and cohort justification |
| `results/pre-load-comparison.json` | Superseded windows and metrics from before the load audit |
| `.cache/` | Compressed per-member reductions, not raw logs |
| `.sources/prysm` | Separate detached checkout of `6c026c4` |
| `.sources/go-gossipsub-trace` | Exact v0.0.2 tracer dependency |

Source checkout setup, if rebuilding elsewhere:

```sh
git clone https://github.com/sukunrt/prysm.git .sources/prysm
git -C .sources/prysm checkout --detach 6c026c484c05c256c7858e9f4a1e8580dd898dbe
git clone --depth 1 --branch v0.0.2 https://github.com/sukunrt/go-gossipsub-trace.git .sources/go-gossipsub-trace
```

Only the pinned Prysm version and its instrumentation dependency are
downloaded; the Dora/genesis-generator IDs are kept as context, not asserted
as observed deployed versions without runtime evidence.

## Comparison boundaries

Runs 2 and 3 share a genesis and topology, with rolling-deployment periods
excluded. Run 4 is the
archive's `run2-genesis-1930`; it also doubles validators, changes validator
allocation and subnet count, and turns partial attestations off. This is not
a controlled one-flag A/B experiment.

The default cohort is nodes 1, 2 (super) and 202 (home), which retain roles
across regenesis. Node 201 has no captured loaded spread window; node 200 changes
role. Each run uses its own intersection of fully captured loaded slots for
the same three nodes. Node means receive equal weight. Bands across two or
three nodes are descriptive; the one-home-node view cannot establish variation
among home nodes. They do not establish uncertainty across 500 network nodes
or repeated experimental runs. Quantiles of arrival bins have
100 ms resolution; paired FFG decision-delay quantiles retain integer ms.

## Transaction and payload-load policy

The first spread comparison (slots 50–291) contained only empty payloads, and
regenesis slots 109–132 were empty too. Those periods remain in detail but are
excluded from the comparison. The previous 34.1% traffic result is superseded.

`payload_load.py` streams selected beacon members for nodes 1, 2, 201 and 202,
retaining only `Payload received` fields. It also streams the node-1 execution
block JSON export and cross-checks transaction counts and gas used; no raw
transaction data is stored. Repeated payload imports are deduplicated. Actual
`payloadBytes` is the actual SSZ execution-payload size from the log, distinct
from execution RLP block size or network wire bytes. The overview and slot detail
include **Execution payload (applied)** in message counts and relative size; the
latter divides the logged SSZ bytes by the 240-byte FFG reference. Payload entry
and application-log times are separate projections of successful applications,
including local and fetched payloads. Repeated imports are counted once. The
join reuses the small audited payload reduction; it never expands the archive.

The builder requires 16 consecutive common full slots with transactions and
payloads of at least 32 KiB on every matched node. This threshold separates
empty payloads (~839 bytes) from all observed loaded payloads (at least 50,978
bytes in the selected windows). It then retains **every** later common steady
slot; subsequent empty/small observations, conflicting values, or unexplained
missing payloads fail the build. Documented missed slot 608 remains included.
This selects a time window rather than discarding individual bad slots.

The resulting ranges are 333–379 (spread), 580–643 and 684–707 (partials),
and 251–274 and 284–370 (regenesis). The first-genesis transaction start is
slot 308 / 16:31:41 UTC, independently shown by execution blocks. Regenesis
transaction onset is inside a capture gap; slot 251 is the first captured
loaded slot, not a known launch time. Exact UTC windows and size distributions
are displayed on the website and recorded in `results/load-validation.json`.

Workload presence is verified; identical workload is not. Transaction counts,
gas, payload sizes and blobs still vary. Devnet 0 is optional historical
context with unverified load; its notes say Spamoor had not started before
the crash. It is not presented as a loaded-run control.

The first comparison pane opens with **Relative object size → Object layers**,
one stacked chart per run on a common scale. Colors identify FFG, Goldfish,
aggregates, PTC, columns, beacon blocks and execution payloads. Choose raw bins
or 150 ms smoothing; the CSV includes both. **Run totals → overlay** restores
the cross-run lines and node bands. Block weights are marked lower bounds.
See [SOURCE_MODEL.md](SOURCE_MODEL.md) for formulas and transport distinctions.
