/* Reproduce the written comparison directly from the website's data/statistics. */
const fs=require('fs'),path=require('path'),vm=require('vm');
const ROOT=path.resolve(__dirname,'..');global.window={};
vm.runInThisContext(fs.readFileSync(path.join(ROOT,'web/data.js'),'utf8'));
const D=window.DEVNET_DATA,S=require('../web/stats.js');
const runs=D.runs.filter(r=>!r.historical),fmt=(n,d=1)=>n==null?'unavailable':n.toLocaleString('en-US',{maximumFractionDigits:d,minimumFractionDigits:d});
const metrics=runs.map(r=>({run:r.id,number:r.number,slots:r.default_slots.length,slot_ranges:r.default_ranges,matched_nodes:r.matched_nodes,load:r.load,all:S.metrics(r,'all'),super:S.metrics(r,'super'),home:S.metrics(r,'home'),nodes:S.cohort(r).map(n=>({node:n.id,rpc_received_kib_s:S.rpcRate(n,'recv'),ffg_decision_delay_p99_ms:S.quantile(S.delayHist(n),.99),last_peer_sample:n.health.last_peer_sample,blocks:n.blocks})),rpc_received_parts_kib_s:Array.from({length:6},(_,i)=>S.mean(S.cohort(r).map(n=>{const rows=n.network.filter(x=>x[0]==='all'&&x[1]==='recv');return rows.reduce((s,x)=>s+x[3+i],0)/rows.reduce((s,x)=>s+x[9],0)*1000/1024;})))}));
const [spread,partial,staggered]=metrics,drop=(a,b)=>(1-b/a)*100;
const report=`# Devnet 1: measured findings

The comparison site is ready locally at <http://127.0.0.1:8766> (start with
\`python3 serve.py\`). The comparison covers three configurations. It does **not** support an unconditional “all good” conclusion.

**Corrected to use transaction-loaded windows:** the previous spread window
(slots 50–291) contained only empty payloads. The first regenesis window
(109–132) was also empty. The previous 34.1% traffic comparison is superseded;
its windows and metrics remain in [the saved pre-check result](results/pre-load-comparison.json).

**Main tradeoff:** on matched nodes 1, 2 and 202, partial attestations reduce
estimated received GossipSub RPC traffic by **${fmt(drop(spread.all.recv,partial.all.recv))}%** and queued-to-send traffic by
**${fmt(drop(spread.all.send,partial.all.send))}%**, while the mean of node-level FFG validation-delay p99s rises
from **${fmt(spread.all.decision)} ms to ${fmt(partial.all.decision)} ms**. The changes are observed between successive
capture periods, not an isolated causal estimate or a repeated experiment.

## Captured configurations and comparison windows

| Run | Default common loaded slots | Duration |
| --- | --- | --- |
${runs.map(r=>`| ${r.number}: ${r.title} | ${r.default_ranges.map(([a,b])=>a+'–'+b).join(', ')} | ${fmt(r.default_slots.length*12/60)} min |`).join('\n')}

Run 3 excludes the 16:56–17:26 UTC rolling restart. Run 4 corresponds to the
archive's \"run2-genesis-1930\" and uses a separate chain identity.

### Transaction and payload-load evidence

The archived execution blocks place the first transactions at slot
${D.load_validation.first_genesis_first_transaction_slot}, **${D.load_validation.first_genesis_first_transaction_utc.slice(11,19)} UTC**.
The loaded spread capture starts five minutes later, at slot 333. After
regenesis, slot 132 is still empty and slot 251 is the first captured loaded
slot. The exact second-genesis load-start time is inside a capture gap.

The gate requires transactions and an actual logged payload size of at least
${D.load_validation.policy.min_payload_bytes/1024} KiB for ${D.load_validation.policy.consecutive_confirmation_slots} consecutive captured slots on every matched node.
It then retains **every** later common steady slot. All later observed payloads
are checked; a return to empty/small payloads would fail the build. Documented
missed slot 608 stays in Run 3, avoiding a success-only selection.

| Run | UTC windows on 8 October 2026 (end exclusive) | Transactions per payload, min / median / max | Actual payload KiB, min / median / max | Payload slots / selected slots |
| --- | --- | ---: | ---: | ---: |
${runs.map(r=>{const l=r.load,span=(x,k=1)=>[x.min,x.median,x.max].map(v=>fmt(v/k,k===1?0:1)).join(' / ');return `| ${r.number} | ${l.utc_windows.map(([a,b])=>a.slice(11,19)+'–'+b.slice(11,19)).join('; ')} | ${span(l.tx_count)} | ${span(l.payload_bytes,1024)} | ${l.confirmed_payload_slots} / ${r.default_slots.length} |`;}).join('\n')}

These sizes are the actual \`payload.SizeSSZ()\` values in Prysm's
\`Payload received\` logs, not the relative-size model. They exclude the envelope
and blob sidecars. The ${fmt(D.load_validation.raw_payload_records,0)} raw payload records reduce to
${fmt(D.load_validation.unique_node_payload_records,0)} unique node/payload observations; repeated imports are deduplicated.
All sampled nodes agree on transaction counts, size, gas, blobs and logged root.
An independent execution export cross-check agrees on transaction counts and
gas for ${fmt(D.load_validation.execution_checked_node_payloads,0)} node/payload observations across
${fmt(D.load_validation.execution_checked_slots,0)} distinct first-genesis slots. Execution RLP block sizes and payload SSZ sizes
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
| Received RPC estimate, KiB/s | ${metrics.map(m=>fmt(m.all.recv)).join(' | ')} |
| Queued-send RPC estimate, KiB/s | ${metrics.map(m=>fmt(m.all.send)).join(' | ')} |
| Received FFG success records / slot / node | ${metrics.map(m=>fmt(m.all.ffg)).join(' | ')} |
| Mean node FFG observed p99 bin lower edge, s | ${metrics.map(m=>fmt(m.all.arrival/1000,2)).join(' | ')} |
| Mean node FFG decision-delay p99, ms | ${metrics.map(m=>fmt(m.all.decision)).join(' | ')} |
| FFG successes delivered via bundles, % | ${metrics.map(m=>fmt(m.all.bundle,4)).join(' | ')} |

The observed-arrival statistic has 100 ms bin resolution. Decision delays use
the exact integer-ms paired fields, \"decidedMs − arrivedMs\", on successful FFG
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
${D.matched_nodes.map(id=>`| ${id} | ${id<200?'Super':'Home'} | ${metrics.map(m=>{const n=m.nodes.find(n=>n.node===id);return fmt(n.rpc_received_kib_s)+' / '+fmt(n.ffg_decision_delay_p99_ms,0);}).join(' | ')} |`).join('\n')}

The delay increase is uneven across nodes. Node 1 reaches 1,834 ms p99 with
partials, node 2 reaches 777 ms, and node 202 reaches 922 ms. An average alone
would hide this difference. About 0.248% of node 1's successful FFG decisions in the
partial steady window occur after 9 s relative to their object slot. This
does not by itself prove an aggregation failure: a committee's full lifecycle
and inclusion are different measurements.

### Where the received bytes go

| RPC category, KiB/s | Run 2 | Run 3 | Run 4 |
| --- | ---: | ---: | ---: |
${['Published messages','Partial-message extension','Control messages','RPC framing','Other'].map((label,i)=>`| ${label} | ${metrics.map(m=>fmt(m.rpc_received_parts_kib_s[i+1])).join(' | ')} |`).join('\n')}

Run 3's control-byte estimate falls by ${fmt(drop(spread.rpc_received_parts_kib_s[3],partial.rpc_received_parts_kib_s[3]))}%. The partial extension costs are
already included in its total. Topic totals and \"pm_*\" subtotals are never
added a second time. Repeated copies to/from peers remain included in RPC traffic.

## Why Run 4 is not a clean X=3 versus X=1 experiment

Regenesis changes 40,300 validators to 80,400; 200 supernodes × 200 validators
to 100 × 800; two attestation subnets to four; and the committee schedule to
12 committees per slot. It disables partial attestations. The spread flag is
ignored by this code when X≥2. Node 200 changes from super to home and is not
in the matched cohort. First-genesis CLI/config snapshots are present; the
regenesis configuration has only README evidence plus corroborating behavior.

In the matched supers, mean received RPC estimates are ${fmt(staggered.super.recv)} KiB/s; in
the matched home node 202 they are ${fmt(staggered.home.recv)} KiB/s. Compare these separately rather
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

- Input: ${fmt(D.quality.archive_bytes/1e9,3)} GB compressed; 597 members inventoried.
  Approximately 28.3 GB of beacon/validator log text was inspected as streams,
  including redundant copies. No archive directory was expanded on disk.
- ${D.quality.selected_members} non-overlapping source members; ${fmt(D.quality.audit.lines,0)} source lines;
  ${fmt(D.quality.audit.observed_events,0)} observed events and ${fmt(D.quality.audit.accepted_events,0)} accepted events
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
  \`${D.quality.archive_sha256}\`.
- Python ingestion tests, Node statistics tests, and the real application's
  automated DOM harness pass. HTTP endpoints are checked separately. Visual
  browser QA was blocked because computer-use access to Firefox was not approved.

Evidence: [archive notes](results/archive-README.md), [manifest](results/source-manifest.json),
[source selection](results/source-selection.json), [audit](results/audit.json),
[independent verification](results/verification.json), [UI checks](results/site-validation.json),
[load validation](results/load-validation.json), [per-slot payload evidence](results/payload-observations.json),
[machine-readable metrics](results/metrics.json), and [source semantics](SOURCE_MODEL.md).
`;
fs.writeFileSync(path.join(ROOT,'FINDINGS.md'),report);
fs.writeFileSync(path.join(ROOT,'results/metrics.json'),JSON.stringify(metrics,null,2)+'\n');
console.log('Wrote FINDINGS.md and results/metrics.json');
