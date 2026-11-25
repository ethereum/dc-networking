# Mainnet realism: perturbations, validation and calibration

Follow-up to [gossip-one-subnet.md](../superseded/gossip-one-subnet.md), which passed on a clean network: 16 PQ subnets, EIP-7870
hosts join their own subnet only, 1 Gbit hosts join all 16, unmodified mainnet gossipsub, emergent peering, 4 s
deadline. This report adds perturbations that make the network look like today's mainnet. Each one has its own flag,
and each is validated on its own. All of them are calibrated together against today's BLS load.

Code (uncommitted): `sim/perturb.py` (flags and generation), `sim/realism_check.py` (validation and calibration
report), `sim/wbsim/src/main.rs` (the node side), `sim/gen_config.py` (hook), and `sim/shadow-3.3-jitter.patch`
(a third Shadow patch). Flag reference: [sim/README.md](../sim/README.md#mainnet-realism-perturbations-simperturbpy).

<!-- RESULTS -->

## 1. Validation: one perturbation at a time

128 hosts, 4–6 slots, the PQ one-subnet scenario (800k validators, 2,000 × 3,072 B, 16 subnets) with exactly one
perturbation on. Runs `runs/V-*`, script `runs/validate.sh`. Some values are exaggerated so the effect is
measurable in a few slots; these are marked.

| run | perturbation | evidence it took effect | PQ complete at 4 s (per class) |
|---|---|---|---|
| `V-base` | none (control) | – | 100 / 100 / 100 % (50x15 / 50x25 / 1 Gbit); p99 1.05 / 0.50 / 0.36 s |
| `V-rtt` | `--net cities --access --jitter`, ping every 2 s | 7,026 host pairs, 257k pings. Measured RTT ÷ configured mean (path + access + jitter): median 0.99, p10–p90 0.95–1.01. Minimum ÷ configured base: median 1.00. Per continent pair, measured vs configured median: EU–EU 36.7 / 36.6 ms, NA–NA 31.1 / 31.0, EU–NA 112.9 / 119.6, AS–NA 198.1 / 204.6, AS–EU 252.7 / 261.6 | 100 / 100 / 100 % |
| `V-loss10` | `--loss --loss-scale 10` (exaggerated), pcap on 7 hosts | pcap: 0.95 % of data packets between captured hosts lost, against 0.89 % configured; TCP retransmissions 1.24 % of 368k data packets | 88 / 89 / 78 %; 1 Gbit p99 5.4 s |
| `V-loss` | `--loss` (sourced values) | retransmissions 0.11 % of 667k data packets (configured path loss 0.1–0.25 %); too few packets between captured hosts (563) for a direct count | 100 / 100 / **98.2 %**: one 1 Gbit host in Seoul missed in 3 of 4 slots (see below) |
| `V-churn` | 1,500 restarts / node / day, 5 % leave, 5 % join, 10-min connections (all exaggerated) | 97 offline and 35 online transitions; 357 connections churned; 8,202 mesh removals on disconnect; restarted hosts back to 6–9 mesh peers (94–130 for 1 Gbit hosts over 16 subnets) 1–11 s after returning; 1,640 signatures never published (validator offline) | 100 / 100 / 100 % of online node·slots (372 offline node·slots excluded) |
| `V-bg` | `--bg` | per home node and slot: aggregates 3.2–3.8 MB, attestations 1.2 MB, blocks 0.54 MB, columns 0.24–0.49 MB, sync 0.17 MB received; total home rx 5.8–6.9 Mbit/s with PQ; copies per unique message 5.9–6.8 | 100 / 100 / 100 %; p99 0.92 / 0.51 / 0.45 s |
| `V-verify2` | `--verify`, 30 % of home hosts 3× slower | mean delay before forwarding 0.40–0.42 ms (configured 0.40), 1.21 ms on slow CPUs (configured 1.20); max 2.6–7 ms | 100 / 100 / 100 % |
| `V-verify2x` | stress control: 4 ms per PQ signature, 1 worker | 1 Gbit hosts (7,800 messages each) wait 3.0 s on average before forwarding, max 6.6 s | 99 / 91 / **0 %** – the delay is on the forwarding path |
| `V-score` | `--bg --scoring`, 3 % of hosts publish 5 invalid aggregates per slot | scores active (min −18,859). Mesh links to the 4 bad hosts: 498 → 15 by slot 4 (97 % evicted). Also: honest peers with negative score 0 → 2,346 entries by slot 4 and mesh links −45 % (Lighthouse's slow-peer penalty, see below) | 100 / 100 / 100 % |
| `V-nat` | `--client-mix --peer-scale 0.25 --nat-share 0.4` | connections by client track the scaled targets (Lighthouse 50, Nimbus 40, Teku 25, Prysm 18); 34 NAT hosts were never dialled (0 inbound refused, vs 1,225 at the inbound cap elsewhere) and dial 2.7× as often | 99.2–100 % per slot; 1 Gbit 99.5 % |
| `V-free` | 10 % never forward | after the fix: 13 free-riders sent 20 messages each over the run (only their own publishes) vs 5,072 for other home hosts; their 4.4 MB upload is control traffic | 100 / 100 / 100 % |

Two problems found and fixed during validation:

- **Self-origin penalty.** With anonymous messages, rust-libp2p 0.49 treats any copy of a node's own message that
  a peer echoes back as an invalid "SelfOrigin" delivery (P4, −157.5 × count²). Honest peers were graylisted
  within a slot. Lighthouse sets `allow_self_origin(true)` (config.rs L528), and wbsim now does too, for every run.
  Unscored runs only lose a debug drop.
- **Free-riders still forwarded** in their home topic (the hybrid-leaf rule in wbsim); fixed in `perturb.py`.

Two effects that are real, not bugs:

- **Lighthouse's slow-peer penalty.** It is −10 per message that rust-libp2p fails to send to a peer, from a
  full or timed-out queue, and it decays by 90 % per slot. Under PQ load, a node's own congested uplink drops
  forwards and blames the peer. Honest peers go negative, and the heartbeat prunes them from the mesh. At 64 hosts
  with scoring alone, 50–75 of ~3,200 connections fell below the gossip threshold in each slot. PQ completion
  was unaffected, but the mesh thins.
- **Loss on long, fast paths.** At sourced loss rates, one 1 Gbit host in Seoul, whose mesh peers are mostly
  200–235 ms away, received 7–29 signatures 0.05–0.5 s after the deadline in 3 of 4 slots. Shadow uses TCP Reno
  (SACK, 200 ms minimum RTO). Linux defaults to CUBIC, which recovers faster on high-BDP paths, so this is likely
  pessimistic.



## 2. Calibration: today's BLS load against mainnet

No PQ signatures (`--no-pq`). All perturbations are on at their sourced values: background traffic, cities, access
links, jitter, loss, verification, slow CPUs, scoring, client mix, NAT 30 % and churn. 256 hosts, 6 slots, statistics
over slots ≥ 2. Peer targets are scaled by 0.3 to fit 31 GB (`--peer-scale 0.3`: Lighthouse 60, Nimbus 48, Teku
30, Prysm 21). Runs `runs/C1`–`C3`, script `runs/calibrate.sh` / `runs/stage3.sh`.

Tolerance: ±20 % on medians and ±30 % on p90/p95 for propagation; ±30 % on duplicates and bandwidth. Tails need
many blocks: with 4 analysed blocks per run, block p90/p99 are indicative only.

| metric | mainnet target (source) | C1 | C2 | **C3 (final)** | verdict |
|---|---|---|---|---|---|
| block first-seen from slot start, p50 / p90 / p99 | 2.06 / 3.51 / 4.52 s (Xatu sentries via Probelab, 2026-11-05) | 1.12 / 1.41 / 1.50 | 1.32 / 1.57 / 1.74 | **2.16 / 2.62 / 2.80** | p50 matches (+5 %); tail too short (−25 %, −38 %) |
| block, from publish, p50 / p95 | relay-publish P95 816 ms (ethresear.ch 23016); bid-corrected median 504 ms, P95 1,484 ms (incl. the relay hop) | 0.10 / 0.20 | 0.16 / 0.32 | **0.16 / 0.34** | about 2× too fast at the tail |
| attestation arrival after the 4 s mark, p50 / p95 | mean 0.83 s, per-subnet P95 1.96 s (ethresear.ch 23016, missed slots) | 0.67 / 2.33 (p99 6.4) | 0.82 / 2.44 | **0.80 / 1.88** | matches (−4 %, −4 %) |
| aggregate arrival after 8 s, p50 / p95 | p50 ≈ 0 / p95 2.5 s (unofficial Xatu analysis, low confidence) | 0.34 / 1.43 | 0.55 / 1.76 | **0.55 / 1.75** | within the (weak) target |
| data column from slot start, p50 / p95 | 1.78 / 3.2 s (unofficial Xatu analysis) | 1.18 / 1.56 | 1.40 / 1.88 | **2.32 / 2.76** | p50 +30 %, p95 −14 %: columns follow our block, on mainnet they lead it |
| duplicates per block (copies − 1) | median 3, p90 6 (Probelab Hermes) | 4.4 | 3.9 | **3.7 (mean)** | matches (mean vs median) |
| duplicates per attestation | median 2, p90 4 | 1.3 | 1.2 | **1.2 (mean)** | −40 %: attestation meshes too thin (see below) |
| home-node gossip bytes received, block + attestation + column topics | ~163 kB/s in (Hermes, these topics only) | – | – | **122 kB/s** (50/25 hosts) | −25 %, within tolerance |
| home-node total rx / tx (all topics incl. aggregates) | validating node 15–20 Mb/s peaks at 10 blobs (Fusaka devnet, ethPandaOps) | 3.3 / 2.9 Mbit/s | 3.6 / 3.2 | **3.6 / 3.2 Mbit/s mean** | consistent with 5.7 blobs (not peak) |
| connections per node | 50–100 measured (2023); defaults 70–200 | scaled targets ×0.3 | same | **Lighthouse 60, Prysm 24, Teku 32, Nimbus 49** | deliberately scaled (memory) |
| mesh per topic | D = 8 (Lighthouse 5) | block 6–9, att 3–4 | same | **block 6.7–9.0, column 3.9–6.4, attestation 2.4–4.7** | attestation and column meshes below D_low |

Iterations:

- **C1 → C2.** Validator-client duty timing. Attestations, aggregates and sync contributions now go out after a
  lognormal delay (median 0.35 s, σ 0.8, cap 3.5 s) instead of uniformly over 0.3 s. Block and column verification
  went from 2 ms and 60 µs/blob to 10 ms and 1.5 ms/blob (client data-column verify p95 9–14 ms). Attestation p99
  fell from 6.4 s to 4.7 s and the p50 moved onto target.
- **C2 → C3.** The block publish time was fitted: lognormal median 1.0 → 1.8 s, σ 0.52 → 0.45. The winning-bid time
  (median 1.0 s) is not the time the block hits gossip, which also includes the proposer → relay → publish round
  trip. This is a fit to Xatu first-seen, not an independent source.

What did not match, and why:

- **Block tail.** Our blocks reach every node 0.34 s after publish at p95. Mainnet takes 0.8 s from relay
  publish. Part of the gap is network size: 256 hosts are about 3 gossip hops deep, 2,048 about 4, and mainnet
  (~10k nodes, D 5–8) about 5. The rest is client-side block handling that we model as 10 ms. Expect the 2,048-host
  runs to be closer, but still optimistic for blocks. This matters little for PQ, whose window starts at 4 s.
- **Attestation subnets at small scale.** At 256 hosts an attestation subnet has 19–30 subscribers; on mainnet it has
  ~250 plus ~760 all-subnet nodes. Meshes sit below D_low, duplicates are low, and 5–8 % of tracked attestations never
  reached hosts subscribed to all 64 subnets (1.3 % for 2-subnet hosts). This is a scale artifact, not a calibration
  value. At 2,048 hosts subnets have ~150–250 subscribers.
- **Lighthouse's slow-peer penalty** pushes 2,000+ of ~30,000 peer entries negative per slot and thins meshes by
  ~30 % over 6 slots (mesh links 40.8k → 28.9k). That matches the client's code, but mainnet has not been shown to
  behave this way. Watch it in the long runs: if meshes keep shrinking past slot 10, it is a modelling problem (our
  queue drops are more frequent than mainnet's). At 2,048 hosts it depends on the peer count (below).

### At 2,048 hosts (p2psims)

Runs `R-nopq-ps100-s1` (`--peer-scale 1.0`, the client defaults) and `R-nopq-s1` (`--peer-scale 0.25`): 2,048 hosts
× 20 slots, `--no-pq`, every perturbation at the C3 values, seed 1. Same tolerance as above.

| metric | mainnet target | ×1.0 | ×0.25 | verdict (×1.0) |
|---|---|---|---|---|
| block first-seen from slot start, p50 / p90 / p99 | 2.06 / 3.51 / 4.52 s | 1.84 / 2.88 / 4.48 | 1.82 / 2.88 / 4.47 | **matches** (−11 %, −18 %, −1 %) |
| block from publish, p50 / p95 | relay-publish P95 0.82 s | 0.22 / 0.37 | 0.22 / 0.41 | still ~2× fast after publish; the fitted publish time absorbs it |
| attestation after the 4 s mark, p50 / p95 / p99 | 0.83 / 1.96 / – s | 0.94 / 1.93 / 2.94 | 0.95 / 2.21 / 4.06 | **matches** (+13 %, −2 %) |
| tracked attestations never received, 2-subnet / all-64 hosts | – | 0.04 % / 1.36 % | 0.52 % / 4.86 % | – |
| duplicates per block / attestation / column (mean) | median 3 / 2 / – | 3.74 / 2.17 / 3.36 | 3.34 / 1.11 / 1.98 | **matches** (+25 %, +9 %); ×0.25 attestations −45 % |
| data column from slot start, p50 / p95 | 1.78 / 3.2 s | 1.85 / 4.41 | 1.86 / 4.37 | p50 matches; **p95 +38 %, outside** |
| home block + attestation + column rx (50/25) | ~163 kB/s | 142 kB/s | 102 kB/s | **matches** (−13 %); ×0.25 −37 % |
| mesh links, slot 0 → 19 | – | 377k → 380k | 358k → 260k | stable at ×1.0; −27 % at ×0.25 |

- **Host count sets the block tail.** At 2,048 hosts block p90 and p99 match at either peer scale (C3 at 256
  hosts: 2.62 / 2.80 s). Propagation after publish is still about twice mainnet's, so the fitted publish time
  (median 1.8 s) carries part of the real network delay. That matters little for PQ, whose window starts at 4 s.
- **Peer count sets attestation duplicates, misses and mesh stability.** With the client defaults they match
  mainnet and the slow-peer penalty no longer thins meshes. At ×0.25 they don't: attestation meshes are thin, hosts
  on all 64 subnets miss 4.9 % of tracked attestations, and mesh links fall 27 % over 20 slots.
- **The column tail is long because only the proposer publishes columns.** On mainnet a node that already has the
  blobs in its execution client's mempool (`engine_getBlobsV2`) builds and publishes columns as soon as it has
  the block, so columns arrive before the block. The model has no such path, and no flag tunes it. It is pessimistic
  for PQ: the column tail overlaps the 4 s PQ window.
- **Forward-queue timeouts are aggregate bursts, not a TCP artifact.** Without PQ, home hosts fail 700–1,100
  forwards per slot (p2psims), all as queue timeouts. In the local runs, failed forwards per home host per slot
  are 17–42 with PQ alone (`V-base`), 635–1,343 with background traffic (`V-bg`) and 790–860 in C3 (no PQ).
  In C3, 95 % are logged 10–12 s into the slot, one 1 s timeout plus a heartbeat after the aggregate burst. A home
  host forwards each of the 1,024 aggregates (495 B, below the 1,000 B IDONTWANT threshold) to D − 1 mesh peers
  within about a second. That is 2–4 MB, more than a 25 or 15 Mbit/s uplink sends within the 1 s forward-queue
  timeout. Lighthouse leaves the rust-libp2p defaults in place (forward 1 s, publish 5 s, 5,000 per queue), so a
  Lighthouse node on that uplink would drop them too. Loss adds little on home hosts (`V-loss`: 82–102 per slot).
  It is the main cause on 1 Gbit hosts (4,772 vs 132), where Shadow's Reno recovers slowly on 200 ms paths, likely
  more than Linux's CUBIC would. Mainnet's EIP-7870 uplink of 25 Mbit/s is a floor, and no mainnet measurement of
  these drops exists.

## 3. Medium check and handoff

**Medium check.** 512 hosts × 20 slots with every perturbation and PQ load does not fit this orb (16 cores,
31 GB). At 512 hosts the wbsim processes held 27 GB before the first PQ slot, and in slot 0's burst Shadow advanced
0.5 simulated seconds per 2 wall minutes while swapping. The check here is 256 hosts × 12 slots
(`runs/M2`, seed 2); see below. The 512 × 25 check is the first job on p2psims (about 20–30 min there).

M2_RESULT

**512-host probes on p2psims** (full REAL flags, seed 1, 4 slots; R-m512-s1 at 25 slots was dropped to try real
peer targets once Yann allowed 402 GiB):

| | `--peer-scale 0.25` | `--peer-scale 1.0` (client defaults: LH 200, Prysm 72, Nimbus 160, Teku 101) |
|---|---|---|
| PQ complete per slot | 97.5 / 99.2 / 98.4 / 97.5 % | 99.2 / 100 / 99.8 / 99.8 % |
| by class 50x15 / 50x25 / 1 Gbit | 99.7 / 100 / **94.9 %** | 99.7 / 100 / 99.3 % |
| PQ p99 latency 50x15 / 50x25 / 1 Gbit | 0.93 / 0.64 / 1.50 s | 0.76 / 0.45 / 0.57 s |
| block p50 / p90 / p99 from slot start | 2.05 / 2.22 / 2.30 s | 2.05 / 2.22 / 2.30 s |
| attestation p50 / p95, missing | 5.08 / 6.22 s, 2.5 % | 5.03 / 6.08 s, 0.9 % |
| mesh links slot 0 → 3 | 110k → 73k (−34 %) | 118k → 109k (−7 %, recovers) |
| peak RSS (Shadow + wbsim) | 40 GiB (78 MB/host) | 84 GiB (164 MB/host) |

- **Use real peer targets.** The scaled targets are pessimistic: the 1 Gbit class misses 5 % of node·slots, and
  meshes shrink because each node has fewer peers to replace the ones its slow-peer penalty prunes. At
  `--peer-scale 1.0` meshes recover. The number of negatively scored peers still grows (9.4k by slot 3). The
  2,048-host calibration in section 2 shows the same split.
- **Block tail.** Short at 512 hosts (p90 2.22 vs 3.51 s) but within tolerance at 2,048 (2.88 s), so host count
  sets it. `--block-pub-sigma` stays at 0.45.

**Memory at 2,048 hosts** (p2psims, peak RSS of Shadow plus every wbsim):

| run | peak |
|---|---|
| no PQ, 20 slots, `--peer-scale 0.25` | 196 GiB |
| no PQ, 20 slots, `--peer-scale 1.0` | 382 GiB |
| with PQ (×0.25) | a flat 44–48 GiB above the no-PQ curve; ~11 GiB of it is the 50-slot PQ schedule that every node parsed from run.json |
| 2,048 × 50 PQ slots | does not fit in 256 GB; it also took 43 wall minutes per slot, so `R-pq-s1` was stopped at sim 87 s |

The earlier estimate of 150–200 GB for 2,048 hosts was low. Two fixes cut memory without changing any simulated
behaviour:

- **Gossipsub forward queue.** Most of the ~0.55 MB per connection that p2psims measured is libp2p-gossipsub
  0.49.5 allocating each peer's 2,500-slot forward/IHAVE queue up front. `sim/gossipsub-0.49.5-lazy-queue.patch`
  grows the queue on demand with the same cap (see sim/README.md). A/B at 64 hosts × 2 slots with every
  perturbation and PQ at `--peer-scale 1.0` (~60 peers per host, seed 3, `runs/AB-orig` vs `runs/AB-lazy`): the
  wbsim processes held 3.30 vs 1.20 GiB at the start of slot 0 and 4.22 vs 2.15 GiB (RSS + swap) inside slot 1's
  PQ burst, so 33–34 MiB less per host, or 0.56 MiB per connection. At 2,048 hosts that is ~45 GiB at ×0.25
  (~40 peers per host) and ~180 GiB at ×1.0 (~160 peers). Behaviour is unchanged. With Shadow's
  `model_unblocked_syscall_latency` off (`runs/AB2-*`, 64 hosts × 1 slot), every node's event log is
  byte-identical between the two builds, through 160,855 queue-full drops and 66,082 queue timeouts. With it on,
  as in all study runs, the traces diverge after warm-up like a change of seed: PQ 100 / 100 % vs 98.4 / 100 %
  per slot, and failed forwards per home host 650–900 vs 480–930. The likely reason is that the stock build makes
  an extra allocation syscall per connection, and Shadow charges each syscall a little simulated time.
- **sched.json.** In every perturbation run, nodes read their publishes from `pubs/`, and wbsim never reads `sched`
  then. gen_config.py now writes the PQ schedule to `<run>/sched.json` and leaves `sched: []` in run.json.
  analyze.py and realism_check.py read it through `analyze.read_cfg`. realism.json and `analyze.py --levers` are
  byte-identical on `V-churn` and `V-bg` with the schedule moved. This saves ~5.6 MB per host at 50 slots.

With both fixes, `--peer-scale 1.0` at 2,048 hosts should peak near 200 GiB without PQ and ~240 GiB with 6 PQ
slots (382 − 180, plus the PQ offset less the schedule). That is an extrapolation; a 512 × 4 probe at ×1.0 should
peak near 40 GiB instead of 84 if it holds. p2psims is meanwhile running ×0.25: 2,048 × 6-slot PQ cells
(~211 GiB, ~5 h each) and 1,024 × 50 slots for the slot-after-slot trend.

**Calibrated flags** (on top of `run_lever.sh`'s base flags):

```sh
REAL="--sig-subnets 16 --one-subnet --peer-target 50 --warmup 30 --bg --net cities --access --jitter --loss
 --verify --slow-cpu-share 0.2 --scoring --client-mix --client-gs --nat-share 0.3
 --churn-conn-life 1800 --churn-restart-per-day 0.143 --churn-leave 0.005 --churn-join 0.005"
runs/run_lever.sh R-nopq-ps100-s1 2048 20 46 $REAL --peer-scale 1.0 --no-pq --seed 1   # calibration (done)
runs/run_lever.sh R6-pq-s1        2048  6 46 $REAL --peer-scale 0.25 --seed 1          # PQ cell (running)
# with the lazy-queue build: --peer-scale 1.0 for the PQ cells once the 512 x 4 probe confirms the memory
```

Defaults that are part of the calibration (no flag needed): block publish lognormal median 1.8 s, σ 0.45; duty
timing lognormal median 0.35 s, σ 0.8; verification µs pq 400, block 10,000, column 1,500/blob, attestation 600,
aggregate 2,500, sync contribution 2,000; 4 / 8 verification workers; 5.7 blobs; 823,366 validators.

**Analysis.** `python3 sim/realism_check.py runs/NAME` → `realism.json` (all sections above), and
`analyze.py --levers` as before. Under `--bg`, κ and after-deadline bytes include background traffic, so for PQ
completion use `realism.json` → `pq`, which also excludes node·slots whose host was offline. analyze.py's
`tail_MiB` (bytes received 8–12 s) is then mostly aggregates; p2psims measures the PQ backlog as PQ-topic bytes
received 8–16 s into the slot. The tick counter `f_forward` counts forwards that failed (queue full or timed out),
not forwards sent. At 2,048 × 100 slots, `--att-track 0.02` keeps the receipt logs small.

**Build.** Shadow 3.3.0 with `git apply sim/shadow-3.3-fixes.patch sim/shadow-3.3-jitter.patch`, then
`./setup build && ./setup install`. wbsim needs the patched gossipsub crate in `sim/wbsim/gossipsub` (three
commands in sim/README.md), then `cargo build --release`.

## Values and sources

Fetched 2026-11-05/06 unless noted. "Estimate" marks values with no direct measurement.

| perturbation | value used | source |
|---|---|---|
| Node geography | 12 cities: us-east 27.7 %, us-west 7.5, fra 19.5, par 7.0, lon 6.5, hel 6.3, ams 5.5, tyo 5.5, sin 5.0, sel 2.0, syd 1.9, gru 2.0 | Probelab country shares of ~8.2k dialable CL nodes (US 31.4, DE 15.5, FI 6.3, FR 5.3, JP 4.5, GB 4.2, CA 3.8, SG 3.6, NL 3.3, AU 1.9); US east:west 1,964:607 by city; the 20 % "other" spread to the nearest hub per continent shares in arXiv 2511.15388 |
| Backbone RTT | WonderNetwork average pings between city pairs (e.g. NYC–LON 70, FRA–SIN 157, LON–TYO 242, SIN–SYD 92 ms); 22 of 66 pairs estimated from neighbouring measured pairs (marked in `perturb.py`); 2 ms within a metro | wondernetwork.com/pings |
| Access latency (home hosts) | fiber 45 % / cable 33 % / DSL 22 %, one-way 4 / 8 / 13 ms | FCC MBA 13th report (2022 data): median idle RTT fiber 7–14, cable 12–24, DSL 23–34 ms; shares from OECD fixed broadband by technology (rounded) |
| Jitter | exponential extra delay per packet, mean 0.5 / 1.5 / 2.5 ms one-way on fiber / cable / DSL access, 0.3 ms per backbone hop; FIFO per destination so TCP sees no reordering | WonderNetwork mdev 0.6–2.3 ms on long backbone paths; residential 1–5 ms is an estimate (FCC publishes none) |
| Packet loss | access 0.05 / 0.1 / 0.25 % per direction (fiber / cable / DSL); backbone 0.01 % within a continent, 0.05 % between | FCC MBA 12th: "packet loss of a few tenths of a percent is common", ≥ 1 % only for 0–4 % of subscribers; ThousandEyes: inter-region cloud loss < 0.1 %. Per-direction split is an estimate |
| Connection churn | mean connection lifetime 30 min after warm-up; the peer manager refills every 5 s while below target | Probelab Hermes (Holesky 2024): 10 % of connections last ~4 min, 10 % 5 min–1.6 h. Estimate for a non-monitoring node |
| Restarts | 1 per node per 7 days, down 30–90 s, all gossipsub and peer state lost | 36 Coins (arXiv 2511.15388): ~80 % daily retention, < 50 % of IPs up 16 days straight; restart every 2–4 weeks is an estimate. A 50–100-slot run sees ~1 % of hosts restart |
| Leaves / joins | 0.5 % of hosts each per run | estimate from ~5–7 %/day node turnover (EL discv4, ETH Zürich 2023) |
| Blocks | one per slot; 90 % via a relay (1 Gbit host), publish time lognormal, median 1.8 s, σ 0.45 (fitted in C2 → C3; P5–P95 ≈ 0.9–3.8 s); size lognormal, median 70 kB | ethp2p observatory (2026-06): winning bid median 1,004 ms, P5–P95 483–2,680 ms, plus the proposer → relay → publish round trip; fitted to Xatu first-seen. MEV block median 66.5 KiB; Probelab: 59.6 % of blocks 50–100 kB |
| Data columns | 128 column topics; blobs Poisson(5.7), max 21; sidecar 356 + 2,144 × blobs B, published 50 ms after the block; custody 4 (no validators), 8–128 by validators (32 ETH each) | 7-day average 5.70 blobs (Sep 2026); BPO2 max 21; consensus-specs das-core / validator.md |
| Attestations | 823,366 / 32 = 25,730 per slot, 240 B, 64 subnets, 4.0–4.3 s; each host joins 2 random subnets, all 64 at ≥ 64 validators | consensus-specs SingleAttestation; validators stake.fish 2026-10-22; Probelab: 7,385 of 8.2k nodes advertise 2 subnets, 759 all 64 |
| Aggregates, sync contributions | 1,024 × 495 B and 64 × 360 B per slot, 8.0–8.2 s | 64 committees × 16 target aggregators; SSZ sizes |
| Verification before forwarding | µs per signature: PQ 400, block 10,000, column 1,500 per blob, attestation 600, aggregate 2,500, sync contribution 2,000; 4 workers on home hosts, 8 on 1 Gbit; slow CPUs 3× on 20 % of home hosts | leanSig verify 193–393 µs on one M1 core (leanroadmap); DKKW Poseidon2 351 µs; BLS verify ~1.0–1.2 ms; client data-column gossip verify p95 9–14 ms. Batch verification (BLS) is modelled by the worker count. Slow-CPU share and factor are estimates |
| Peer scoring | Lighthouse `gossipsub_scoring_parameters.rs` (a376def): thresholds −4,000 / −8,000 / −16,000 / 100 / 5, topic weights block 0.5, aggregate 0.5, attestations 1/64 each, P3 mesh deliveries on, slow-peer penalty −10 (decay 0.1); PQ subnets scored like attestation subnets | client source; thresholds identical in Lighthouse, Prysm, Teku and Lodestar |
| Peer targets | Lighthouse 200 (52.6 %), Prysm 70 (20.8), Nimbus 160 (8.9), Teku 100 (7.8), Lodestar 200 (2.8), other 200 (7.0); inbound cap +10 %; scaled by `--peer-scale` to fit memory | client source; Probelab agent shares |
| Per-client gossipsub | Lighthouse/Grandine `network_load 3`: D 5/3/10, D_lazy 3, heartbeat 1 s, history 12/3; Nimbus flood publish, gossip_factor 0.05, D_out 3; Teku and Lodestar flood publish | client source |
| NAT | 30 % of home hosts: never returned by discovery, inbound refused | Heimbach et al. USENIX Sec '25: 16.5k IPs/day discovered vs 8.1k reachable (≤ 50 % undialable, upper bound); 30 % is an estimate. Cloud hosts are always dialable |
| Misbehaving peers | off by default; `--bad-share` publishes invalid aggregates, `--freeride-share` never forwards | no measured mainnet share |
