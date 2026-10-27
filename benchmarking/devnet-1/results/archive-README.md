# dc-devnet-1 archive

Genesis 2026-10-08 15:30:05 UTC. 500 nodes (200 supernodes x 200 validators, 300 home x 1).
Image `sukunrt-decoupled-casper-6c026c4`. Times are UTC.

Partial attestations (`--partial-attestations`): rolling restart 16:56-17:26. Before 16:56: no partial.

## Pre-partial

| Folder | Contents |
|---|---|
| `prysm-geth-{1,2,200,202}/` | ClickHouse export 15:55:30-16:00:30. Incomplete (Vector throttle 20k lines/min). |
| `full/` | Docker logs 15:55:30-16:00:30, nodes 1, 2, 200, 202. |
| `full-1559-1619/` | Docker logs 15:59:20-16:19:20, nodes 1, 2, 35, 50, 200, 201, 202, 305, 405. |
| `full-start-1628/` | Docker logs container start to 16:28:30 (gz), 16 nodes. `network-config/` (no mnemonics). |
| `full-1636-1641/`, `full-1641-1646/` | Docker logs, nodes 1, 2, 200, 202. |
| `node-355-start-1646/` | Node 355 to 16:46. Stuck at slot 307 (envelope for slot 307 ignored, early by ~30 ms). |
| `full-1706-1711/` | Mixed (rollout in progress). Node 2 beacon empty, node 202 pre-partial. |

## Post-partial (`post-partial/`)

| Folder | Contents |
|---|---|
| `prysm-geth-*/` | Docker logs from each node restart to 17:14:01. Rollout not complete. |
| `full-1718-1723/` | Nodes 1, 2, 200, 202. 402/500 nodes on partial. |
| `full-1733-1738/` | Nodes 1, 2, 200, 202. 500/500 nodes on partial. |
| `full-1746-1751/` | Nodes 1, 2, 201, 202. 500/500 nodes on partial. |
| `full-start-1739/` | 15 nodes, container start (16:56-17:19) to 17:39:04: beacon, validator, execution, snooper-engine, brakebear logs (gz), local Prometheus TSDB, configs, CLI args. |
| `full-start-1739/chain/` | Node 1: all beacon blocks 0-653 (API), geth blocks 0-633 with txs, beacon DB (live copy, may be inconsistent). |
| `full-start-1739/pprof/` | Nodes 1, 305: heap, allocs, goroutine, cpu 30 s. |

## Gaps

- 16:28:30 to each node's restart: Docker logs lost (containers recreated). ClickHouse has a partial copy.
- Nodes 98, 99: beacon recreated after genesis, stuck. Not archived after 16:28.
- Prometheus TSDB for nodes 2 and 305: WAL changed during tar.
- Missed slots: 1-9, 34, 57, 84, 458, 485, 542 (rollout), 608.

## Run 2 (`run2-genesis-1930/`)

New genesis 2026-10-08 19:30:00 UTC, same machines. 80,400 validators (100 x 800, 400 x 1).
`ATTESTATION_SUBNET_COUNT` 4, `TARGET_COMMITTEE_SIZE` 2500, `TARGET_AGGREGATORS_PER_COMMITTEE` 128,
`SUBNETS_PER_NODE` 2. X=3. No `--partial-attestations`. Image `6c026c4`.

| Folder | Contents |
|---|---|
| `full-1951-1956/` | Beacon and validator logs, nodes 1, 2, 201, 202. |
| `full-2020-2025/` | Beacon and validator logs, nodes 1, 2, 201, 202. |
| `full-2026-2036/` | Beacon and validator logs, nodes 1, 2, 201, 202. |
| `full-2034-2044/` | Beacon and validator logs, nodes 1, 2, 35, 50, 200, 201, 202, 305, 376, 405. Node 376 stuck at slot 316, 0 peers. |
