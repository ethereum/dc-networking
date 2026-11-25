# Mainnet realism: perturbations, validation and calibration

Follow-up to [gossip-one-subnet.md](gossip-one-subnet.md), which passed on a clean network: 16 PQ subnets, EIP-7870
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
  queue drops are more frequent than mainnet's).

## 3. Medium check and handoff

**Medium check.** 512 hosts × 20 slots with every perturbation and PQ load does not fit this orb (16 cores,
31 GB). At 512 hosts the wbsim processes held 27 GB before the first PQ slot, and in slot 0's burst Shadow advanced
0.5 simulated seconds per 2 wall minutes while swapping. The check here is 256 hosts × 12 slots
(`runs/M2`, seed 2); see below. The 512 × 25 check is the first job on p2psims (about 20–30 min there).

M2_RESULT

**Calibrated flags** (on top of `run_lever.sh`'s base flags):

```sh
REAL="--sig-subnets 16 --one-subnet --peer-target 50 --warmup 30 --bg --net cities --access --jitter --loss
 --verify --slow-cpu-share 0.2 --scoring --client-mix --client-gs --peer-scale 0.25 --nat-share 0.3
 --churn-conn-life 1800 --churn-restart-per-day 0.143 --churn-leave 0.005 --churn-join 0.005"
runs/run_lever.sh R-m512-s1   512 25  46 $REAL --seed 1                 # medium check first
runs/run_lever.sh R-nopq-s1  2048 20  46 $REAL --no-pq --seed 1         # calibration at scale (BLS only)
runs/run_lever.sh R-pq-s1    2048 50  46 $REAL --seed 1                 # PQ one-subnet, everything on
runs/run_lever.sh R-pq-s2    2048 100 46 $REAL --seed 2
```

Defaults that are part of the calibration (no flag needed): block publish lognormal median 1.8 s, σ 0.45; duty
timing lognormal median 0.35 s, σ 0.8; verification µs pq 400, block 10,000, column 1,500/blob, attestation 600,
aggregate 2,500, sync contribution 2,000; 4 / 8 verification workers; 5.7 blobs; 823,366 validators.

**Memory.** wbsim used about 53 MB per host at `--peer-scale 0.25` before load, against 65 MB at 50 static peers in
the clean runs, and it grows under PQ load. Expect 2,048 hosts to need roughly 150–200 GB; measure it on the
512-host run (×4). If it does not fit, lower `--peer-scale` to 0.2. Keep 0.25 if possible: Prysm hosts already
drop to 18 peers.

**Analysis.** `python3 sim/realism_check.py runs/NAME` → `realism.json` (all sections above), and
`analyze.py --levers` as before. Under `--bg`, κ and after-deadline bytes include background traffic, so for PQ
completion use `realism.json` → `pq`, which also excludes node·slots whose host was offline. At 2,048 × 100 slots,
`--att-track 0.02` keeps the receipt logs small.

**Build.** Shadow 3.3.0 with `git apply sim/shadow-3.3-fixes.patch sim/shadow-3.3-jitter.patch`, then
`./setup build && ./setup install`. Rebuild wbsim (Cargo.toml gained the `ping` feature).

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
| Blocks | one per slot; 90 % via a relay (1 Gbit host), publish time lognormal, median 1.0 s, σ 0.52 (P5–P95 ≈ 0.45–2.4 s); size lognormal, median 70 kB | ethp2p observatory (2026-06): winning bid median 1,004 ms, P5–P95 483–2,680 ms; MEV block median 66.5 KiB; Probelab: 59.6 % of blocks 50–100 kB |
| Data columns | 128 column topics; blobs Poisson(5.7), max 21; sidecar 356 + 2,144 × blobs B, published 50 ms after the block; custody 4 (no validators), 8–128 by validators (32 ETH each) | 7-day average 5.70 blobs (Sep 2026); BPO2 max 21; consensus-specs das-core / validator.md |
| Attestations | 823,366 / 32 = 25,730 per slot, 240 B, 64 subnets, 4.0–4.3 s; each host joins 2 random subnets, all 64 at ≥ 64 validators | consensus-specs SingleAttestation; validators stake.fish 2026-10-22; Probelab: 7,385 of 8.2k nodes advertise 2 subnets, 759 all 64 |
| Aggregates, sync contributions | 1,024 × 495 B and 64 × 360 B per slot, 8.0–8.2 s | 64 committees × 16 target aggregators; SSZ sizes |
| Verification before forwarding | µs per signature: PQ 400, block 2,000, column 60 per blob, attestation 600, aggregate 2,500, sync contribution 2,000; 4 workers on home hosts, 8 on 1 Gbit; slow CPUs 3× on 20 % of home hosts | leanSig verify 193–393 µs on one M1 core (leanroadmap); DKKW Poseidon2 351 µs; BLS verify ~1.0–1.2 ms; client data-column gossip verify p95 9–14 ms. Batch verification (BLS) is modelled by the worker count. Slow-CPU share and factor are estimates |
| Peer scoring | Lighthouse `gossipsub_scoring_parameters.rs` (a376def): thresholds −4,000 / −8,000 / −16,000 / 100 / 5, topic weights block 0.5, aggregate 0.5, attestations 1/64 each, P3 mesh deliveries on, slow-peer penalty −10 (decay 0.1); PQ subnets scored like attestation subnets | client source; thresholds identical in Lighthouse, Prysm, Teku and Lodestar |
| Peer targets | Lighthouse 200 (52.6 %), Prysm 70 (20.8), Nimbus 160 (8.9), Teku 100 (7.8), Lodestar 200 (2.8), other 200 (7.0); inbound cap +10 %; scaled by `--peer-scale` to fit memory | client source; Probelab agent shares |
| Per-client gossipsub | Lighthouse/Grandine `network_load 3`: D 5/3/10, D_lazy 3, heartbeat 1 s, history 12/3; Nimbus flood publish, gossip_factor 0.05, D_out 3; Teku and Lodestar flood publish | client source |
| NAT | 30 % of home hosts: never returned by discovery, inbound refused | Heimbach et al. USENIX Sec '25: 16.5k IPs/day discovered vs 8.1k reachable (≤ 50 % undialable, upper bound); 30 % is an estimate. Cloud hosts are always dialable |
| Misbehaving peers | off by default; `--bad-share` publishes invalid aggregates, `--freeride-share` never forwards | no measured mainnet share |
