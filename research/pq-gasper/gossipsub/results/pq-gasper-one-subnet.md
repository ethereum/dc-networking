# One PQ Gasper subnet: 1,600 signatures per subnet per slot, every node must hold all of them at 8.0 s (2,048 hosts, Shadow)

Status: final, Nov 17 2026, 20:3x CET. Twelve runs, listed in the overview table.
Machine: p2psims. Working notes, with every number and run: `.amp-out/results-notes.md` there (section "PQ Gasper
one-subnet study").

## Question

PQ Gasper splits each slot's signatures over 16 attestation subnets: 800k validators / 32 slots / 16 subnets ≈ 1,600
signatures per subnet per slot. Can gossipsub deliver one such subnet when every simulated node subscribes to it, and
every node, whatever its link (50/15, 50/25 or 1 Gbit), must hold **all 1,600 signatures of the slot at 8.0 s**? The
signatures go out 4.0–4.5 s into the slot, so the window is 3.5–4 s.

This is the test the earlier studies did not run. The 16-subnet runs in `gossip-one-subnet-realistic.md` split 2,000
signatures per slot over 16 subnets (125 per subnet), so a home staker received about 125 per slot. The first study
did run one topic of 2,000 (`gossip-2000.md`, `gossip-consolidation.md`), but on a clean network with Shadow's
original Reno TCP.

**Pass rule** (as before): from slot 2, at least 99 % of the nodes of each link class hold every signature of the slot
at 8.0 s, in every slot, and late first deliveries (signatures first received after the deadline) do not build up.
Per-signature misses are reported alongside.

## Verdict

- **One subnet of 1,600 signatures per subnet per slot does not work for home nodes.** At 2,048 hosts with packet
  loss, churn, NAT and slow CPUs, 23–35 % of 50/15 nodes and 53–58 % of 50/25 nodes hold all 1,600 at 8.0 s in a slot,
  against the 99 % bar, and they miss 12.8 % and 4.1 % of the signatures. 1 Gbit nodes miss the bar only in slot 2
  (98.9 %) and pass from slot 3. 2,048 hosts is the largest network that fits the memory budget; at 1,600 signatures
  the run reached the 235 GiB cap after slot 14.
- **It works for every class up to 300 signatures per subnet per slot**, about a fifth of the load:

  | Signatures per subnet per slot (every class must hold all at 8.0 s) | 200 | 300 | 400 | 600 | 800 | 1,600 |
  |---|---|---|---|---|---|---|
  | 50/15 (worst slot) | pass (100 %) | pass (99.1 %) | fail, just (98.5 %) | fail (90.3 %) | fail (77.9 %) | fail (23.3 %) |
  | 50/25 | pass (100 %) | pass (99.7 %) | pass (99.1 %) | fail (95.5 %) | fail (90.8 %) | fail (53.3 %) |
  | 1 Gbit | pass (100 %) | pass (100 %) | pass (100 %) | pass (99.9 %) | pass (99.6 %) | fail, just (98.9 %, slot 2 only) |
  | Signatures missing at 8.0 s, 50/15 / 50/25 / 1 Gbit | 0 / 0 / 0 | 0.012 / 0.004 / 0 % | 0.046 / 0.025 / 0 % | 0.40 / 0.19 / 0 % | 1.3 / 0.58 / 0.002 % | 12.8 / 4.1 / 0.020 % |

  The boundary lies between 300 and 400 signatures per subnet per slot for 50/15 nodes (0.72–0.96 MB per slot; at 300
  their worst slot has 3 of 330 nodes incomplete, the most the rule allows), between 400 and 600 for 50/25 nodes
  (0.96–1.44 MB) and at about 1,600 for 1 Gbit nodes. A home class starts to fail once the subnet takes about half of
  its uplink over 4–8 s: 50/15 nodes pass at 46 % and fail at 56 %, 50/25 nodes pass at 39 % and fail at 50 %. In the
  first second after publication even a passing class hands its uplink about as much as it carries (50/15 at 300:
  126 %; 50/25 at 400: 101 %). Late first deliveries do not build up in any run.
- **The cause is the home node's own uplink, not its downlink.** Forwarding the subnet to its mesh peers needs more
  than the uplink holds (at 1,600, a 50/15 node hands 115 % of its 15 Mbit/s to TCP over 4–8 s), while its download
  averages 41–50 %. Its TCP ACKs, and its IWANTs, wait behind that data, so the paths into it slow down and time out,
  and the nodes sending to it drop forwards that waited 1 s in their queues. In a diagnostic run where 30 % of hosts
  never forward, home nodes that only receive miss 3–8× fewer signatures on the same links (50/15: 2.2 instead of
  17.3 %), and 1 Gbit senders reach them with 0.4 instead of 12.9 TCP timeouts per 1,000 packets and a median RTT
  inflation of 7 instead of 44 ms. Mesh peers that drop forwards because they are saturated themselves are the smaller
  part. So the levers that help cut the home node's own upload in the 4–8 s window.
- **Near the boundary, the misses fall on DSL home nodes.** At 300 and 400, DSL hosts, about a fifth of home hosts,
  hold 73–92 % of the incomplete home node-slots. Their access links lose the most packets (0.25 % each way), and all
  of them are complete once packet loss, churn, NAT and slow CPUs are off; NAT makes no difference and slow CPUs little.
- **No other lever comes near rescuing 1,600** (one change at a time against the runs above):

  | Lever | Signatures per subnet per slot | Effect on home nodes |
  |---|---|---|
  | 80 % of hosts on 1 Gbit instead of 36 % | 1,600 | No rescue: worst slots stay at 23 % (50/15) and 53 % (50/25); signatures missing fall about 40 % |
  | No packet loss, churn, NAT or slow CPUs | 400 | 50/15 passes (worst slot 99.4 %); fiber home nodes suggest each home boundary moves up one load step (inferred) |
  | TCP without slow start after idle | 400 | 50/15 passes by the rule's last node (3 of 330); signatures missing fall about 3× |
  | 512 hosts instead of 2,048 | 400 | Same verdict (50/15 fails by 1 of 86); signatures missing halve, so a larger network likely does slightly worse |
  | Today's BLS attestations kept | 300 | 50/15 fails in slot 2 only (98.8 %, 4 of 330); signatures missing double; home BLS attestations missing at 8.0 s rise from 0.007 to 0.063 % (50/15) |

  A larger 1 Gbit share does not cut a home node's own forwarding duty, and removing the perturbations cannot fit a
  50/15 node's 115 % into its uplink: the first study's clean network (no loss, churn or scoring) failed home nodes at
  2.5–3.1 MB per slot too, less than the 3.84 MB of 1,600 signatures here.
- **800 signatures of 2.4 kB stand in for 1,600 of about 1.2 kB** (the smaller signature Potuz mentions), with the same
  bytes per slot. That option fails for both home classes too (worst slot 77.9 % and 90.8 %), and by slightly more: its
  99 extra messages per slot add about 0.3 MB of control traffic per node in the 4–8 s window, while verifying twice as
  many signatures should not matter. The message count changes the margin, not the verdict.

## Setup

- **Load:** one PQ topic, 1,600 signatures per slot (lever runs: 800, 600, 400, 300 or 200 per slot) of 2,404 B (one leanXMSS
  signature). Each slot draws its signers at random, with replacement, in proportion to each host's validators. A
  publisher bundles its own signatures into messages of up to 16 (`--batch 16`), sent when its last signature of the
  bundle is ready, at 4 s + U[0, 0.5 s). At 2,048 hosts that is 302 messages and 3.84 MB per slot. 97.6 % of the
  signatures come from 1 Gbit hosts, because the hosts with more than 8 validators hold most validators. Churn loses
  0–4 signatures per slot (publisher offline).
- **Every node subscribes to the topic and needs every signature**, its own excepted. Deadline 8.0 s after slot start.
- **Hosts and links:** 2,048 hosts sampled from the mainnet crawl `data/f9ba162f-nodes.csv` (126,255 validators on
  1,639 of them). Hosts with more than 8 validators, plus 20 % of the rest, have 1 Gbit (742 hosts, 36 %). The others
  keep EIP-7870 links: 50/25 Mbit/s with validators (976 hosts) and 50/15 without (330 hosts).
- **Gossipsub:** rust-libp2p 0.49.5 nodes with each client's default parameters and peer targets (Probelab client
  mix: Lighthouse D 5/3/10, heartbeat 1 s, 200 peers; Prysm 70, Nimbus 160, Teku 100, Lodestar and other 200 peers,
  D 8/6/12, 0.7 s), IDONTWANT above 1,000 B, peering from the peer manager (no static dials), and client-faithful
  scoring (`bin/cf2`: slow-peer penalty, mesh-delivery P3/P3b and IWANT promises per client). The PQ topic is scored
  as one of 16 PQ subnets: topic weight 1/16, expected rate = the messages actually published on it (302 per slot at
  1,600 signatures). Mesh-delivery scoring on the PQ topic switches on about 204 s after a node joins its mesh, around
  slot 15.
- **Realism layer** (calibrated in `realism-calibration.md` and `gossip-one-subnet-realistic.md`): WonderNetwork RTTs
  between 12 cities, fiber/cable/DSL access latency, jitter, packet loss, signature verification delay with 20 % slow
  CPUs, 30 % of home hosts behind NAT, churn (30 min connection life, 0.143 restarts per day, 0.5 % leave and 0.5 %
  join).
- **TCP:** patched Shadow 3.3.0, rtt6 build: Linux v6.12 CUBIC with HyStart, window validation and slow start after
  idle (stock Linux). The no-slow-start-after-idle lever uses the same binary with `RTT5_SSR=0`, as Linux with
  `net.ipv4.tcp_slow_start_after_idle=0`.
- **Background traffic:** blocks, data columns, aggregates and sync-committee messages at mainnet rates. Today's BLS
  attestations are dropped (`--no-att`): PQ Gasper replaces them, and keeping them would overstate the load. The
  aggregates stay as a stand-in for the aggregation traffic that follows the deadline. One lever run keeps the
  attestations.
- **Scale:** 2,048 hosts × 20 slots per run unless noted, seed 1. The 1,600-signature generation is the same network
  and publisher schedule in every run except where a lever changes it.

## Results

In every table, every node of every class (50/15, 50/25, 1 Gbit) must hold all of the slot's signatures at 8.0 s.
Pass: at least 99 % of each class complete in every slot from slot 2.

### Overview

| Run (2,048 hosts × 20 slots unless noted) | Signatures per subnet per slot (each class must hold all at 8.0 s) | 50/15 complete, worst slot | 50/25 | 1 Gbit | Signatures missing at 8.0 s, 50/15 / 50/25 / 1 Gbit |
|---|---|---|---|---|---|
| Headline (slots 2–14) | 1,600 | 23.3 % | 53.3 % | 98.9 % | 12.8 / 4.1 / 0.020 % |
| Load | 800 | 77.9 % | 90.8 % | 99.6 % | 1.3 / 0.58 / 0.002 % |
| Load | 600 | 90.3 % | 95.5 % | 99.9 % | 0.40 / 0.19 / 0 % |
| Load | 400 | 98.5 % | 99.1 % | 100 % | 0.046 / 0.025 / 0 % |
| Load | 300 | 99.1 % | 99.7 % | 100 % | 0.012 / 0.004 / 0 % |
| Load | 200 | 100 % | 100 % | 100 % | 0 / 0 / 0 |
| 1 Gbit: > 8 validators + 75 % of the rest (1,640 hosts, 80 %) | 1,600 | 23.2 % | 52.9 % | 99.8 % | 7.3 / 2.3 / 0.005 % |
| No packet loss, churn, NAT or slow CPUs | 400 | 99.4 % | 100 % | 100 % | 0.002 / 0 / 0 % |
| No slow start after idle | 400 | 99.1 % | 99.5 % | 100 % | 0.016 / 0.012 / 0 % |
| 512 hosts (512 × 20) | 400 | 98.8 % (1 of 86) | 99.2 % | 100 % | 0.023 / 0.004 / 0 % |
| Today's BLS attestations kept | 300 | 98.8 % (slot 2 only) | 99.7 % | 100 % | 0.024 / 0.005 / 0 % |
| Diagnostic: 30 % leaves, 512 hosts × 8 slots (forwarding / leaf) | 1,600 | 16.4 / 64.0 % | 47.6 / 76.0 % | 97.0 / 96.0 % | 17.3 / 6.6 / 0.25 % (leaves 2.2 / 2.0 / 0.11 %) |

### Load: signatures per subnet per slot (2,048 hosts)

| Signatures per subnet per slot (every class must hold all at 8.0 s) | 200 | 300 | 400 | 600 | 800 | 1,600 (slots 2–14) |
|---|---|---|---|---|---|---|
| Messages and MB per slot | 90, 0.48 | 115, 0.72 | 137, 0.96 | 172, 1.44 | 203, 1.92 | 302, 3.84 |
| 50/15: complete at 8.0 s, worst slot (mean) | 100 % (100 %) | 99.1 % (99.8 %) | 98.5 % (99.3 %) | 90.3 % (94.2 %) | 77.9 % (83.2 %) | 23.3 % (28.5 %) |
| 50/25: complete at 8.0 s, worst slot (mean) | 100 % (100 %) | 99.7 % (99.9 %) | 99.1 % (99.6 %) | 95.5 % (97.0 %) | 90.8 % (92.3 %) | 53.3 % (55.8 %) |
| 1 Gbit: complete at 8.0 s, worst slot (mean) | 100 % (100 %) | 100 % (100 %) | 100 % (100 %) | 99.9 % (99.98 %) | 99.6 % (99.9 %) | 98.9 % (99.5 %) |
| Signatures missing at 8.0 s, 50/15 / 50/25 / 1 Gbit | 0 / 0 / 0 | 0.012 / 0.004 / 0 % | 0.046 / 0.025 / 0 % | 0.40 / 0.19 / 0 % | 1.3 / 0.58 / 0.002 % | 12.8 / 4.1 / 0.020 % |
| Signatures missing at 9.0 s, 50/15 / 50/25 / 1 Gbit | 0 / 0 / 0 | 0.007 / 0.002 / 0 % | 0.023 / 0.009 / 0 % | 0.22 / 0.09 / 0 % | 0.71 / 0.29 / 0 % | 9.5 / 2.5 / 0.011 % |
| Last needed signature, p90, 50/15 / 50/25 / 1 Gbit | 5.3 / 5.2 / 4.9 s | 5.7 / 5.5 / 5.0 s | 6.1 / 5.7 / 5.1 s | 7.0 / 6.3 / 5.0 s | 8.9 / 7.0 / 5.2 s | 15.4 / 11.4 / 5.4 s |
| Late first deliveries (8–16 s) per node and slot, 50/15 / 50/25 | 0 / 0 | 0.01 / 0 | 0.04 / 0.02 | 0.43 / 0.20 | 1.7 / 0.8 | 27 / 9.5 |
| Upload handed to TCP, 4–8 s, 50/15 / 50/25 | 34 / 23 % | 46 / 31 % | 56 / 39 % | 72 / 50 % | 84 / 59 % | 115 / 85 % |
| Upload handed to TCP, 4–5 s, 50/15 / 50/25 | 108 / 75 % | 126 / 93 % | 135 / 101 % | 141 / 107 % | 140 / 108 % | 145 / 110 % |
| Download, 4–8 s, 50/15 / 50/25 | 13 / 13 % | 18 / 18 % | 23 / 24 % | 30 / 32 % | 34 / 39 % | 41 / 50 % |
| PQ sends dropped after 1 s in a peer queue, 50/15 / 50/25 / 1 Gbit | 7 / 5 / 2 % | 14 / 11 / 4 % | 22 / 18 / 6 % | 33 / 29 / 12 % | 39 / 38 / 18 % | 49 / 52 / 39 % |
| 1 Gbit share of the PQ mesh, 50/15 / 50/25 | 46 / 46 % | 43 / 47 % | 41 / 46 % | 37 / 41 % | 36 / 38 % | 35 / 36 % |

Upload above 100 % means the node writes more than its uplink carries and its socket buffers fill.

- **Late first deliveries do not build up in any run** (flat between the halves of each run): the misses happen in
  each slot, not through a backlog.
- **Home uplinks are full in the first second at every load** (4–5 s: 108 % for 50/15 even at 200), so the boundary is
  set by whether the backlog drains before 8.0 s. With load, home upload over 4–8 s rises from 34 to 115 % (50/15) and
  the share of PQ sends dropped after 1 s rises from 7 to 49 %, while home downloads stay at or below 50 %.
- **At 400, the remaining 50/15 misses sit on a few hosts:** 19 of 330 are ever incomplete, led by distant Lighthouse
  nodes with 200 peers (Singapore, Sydney). Their incomplete node-slots had fewer 1 Gbit peers in their PQ mesh than
  complete ones (30 vs 41 %); at 1,600 there was no such difference.
- **To watch:** duplicate copies arriving after 8 s grow during every run (400: 50/15 195 → 863 kB per node and slot from
  slot 2 to 18; 800: 675 → 2,662 kB), and home upload creeps up (800: 50/15 69 → 92 %), while late first deliveries stay
  flat. Longer runs could move the boundaries down.

### 1,600 signatures per subnet per slot (2,048 hosts, slots 2–14)

The watchdog stopped the run at simulated second 227, at the 235 GiB memory cap (memory grows about 8 GiB per slot at
this load). It covers slots 2–14, so not the PQ mesh-delivery scoring that starts around slot 15. The failure is large
and steady over the 13 slots, so it was not rerun.

| 1,600 signatures per subnet per slot; every class must hold all 1,600 at 8.0 s | 50/15 (330 hosts) | 50/25 (976) | 1 Gbit (742) |
|---|---|---|---|
| Nodes holding all 1,600 at 8.0 s: worst slot / mean | 23.3 % / 28.5 % | 53.3 % / 55.8 % | 98.9 % (slot 2) / 99.5 % |
| Signatures missing at 8.0 s / 9.0 s | 12.8 % / 9.5 % (204 per node) | 4.1 % / 2.5 % (65) | 0.020 % / 0.011 % (0.3) |
| Signatures held at 6 / 7 / 8 s | 60 / 80 / 87 % | 76 / 92 / 96 % | 99.5 / 99.9 / 100 % |
| Last needed signature arrives, p50 / p90 | 8.9 / 15.4 s | 7.6 / 11.4 s | 5.2 / 5.4 s |
| Nodes still incomplete at 20 s | 22 % | 5 % | 0 |
| Late first deliveries (8–16 s) per node and slot | 27, flat | 9.5, flat | 0.05 |
| Upload handed to TCP, 4–8 s: mean (busiest node); 4–5 s | 115 % (171 %); 145 % | 85 % (140 %); 110 % | 5 % (13 %); 13 % |
| Download, 4–8 s | 41 % | 50 % | 3 % |
| PQ sends this class dropped after 1 s in a peer queue | 49 % | 52 % | 39 % |
| PQ copies received per needed message; IWANT requests per node and slot | 4.2; 1,140 | 4.6; 1,035 | 4.4; 99 |
| PQ mesh at 3.95 s: degree, 1 Gbit share | 6.1, 35 % | 6.5, 36 % | 8.1, 54 % |

Upload above 100 % means the node writes more than its uplink carries and its socket buffers fill.

- **Late first deliveries do not build up** (50/15: 26.9 per node and slot in both halves of the run), but home upload
  creeps up over the run (50/15 95 → 124 % of its uplink from slot 2 to 14) and copies arriving after 8 s grow (50/15 3.2 → 7.2 MB
  per node and slot).
- **The same nodes fail:** 322 of 330 50/15 hosts and 791 of 976 50/25 hosts are incomplete at least once, and 75 % of
  a slot's incomplete hosts were also incomplete in the slot before.
- **Misses are not concentrated on home publishers' signatures:** 50/15 nodes miss 12.9 % of the signatures from 1 Gbit
  publishers (97.6 % of all signatures) and 7.0 % of those from home publishers. Bundles are missed more often than
  single signatures (12.8 % of signatures, 10.0 % of messages).
- **Scoring:** Lighthouse and the "other" clients mark slow peers negative when their own sends to them fail. 22–26 % of
  connections to 50/15 nodes are negative from slot 6 (20–23 % to 50/25, 12 % to 1 Gbit), and 24–46 % of 50/15 nodes
  have fewer than 6 PQ mesh peers (never 0).

### 1 Gbit share: 80 % of hosts on 1 Gbit, 1,600 signatures per subnet per slot

Hosts with more than 8 validators plus 75 % of the rest on 1 Gbit: 1,640 of 2,048 hosts, against 742 (36 %) in the
headline. 296 hosts stay at 50/25 and 112 at 50/15. All 20 slots ran (slots 2–19 analysed; the headline's slots 2–14).

| 1,600 signatures per subnet per slot; every class must hold all 1,600 at 8.0 s | 50/15: headline / 80 % on 1 Gbit | 50/25 | 1 Gbit |
|---|---|---|---|
| Nodes holding all 1,600 at 8.0 s: worst slot (mean) | 23.3 (28.5) / 23.2 % (33.9 %) | 53.3 (55.8) / 52.9 % (59.1 %) | 98.9 (99.5) / 99.8 % (99.9 %) |
| Signatures missing at 8.0 s / 9.0 s | 12.8 / 9.5 → 7.3 / 5.0 % | 4.1 / 2.5 → 2.3 / 1.4 % | 0.020 → 0.005 % |
| Last needed signature, p90 | 15.4 → 12.4 s | 11.4 → 10.1 s | 5.4 → 5.0 s |
| Late first deliveries (8–16 s) per node and slot | 27 → 14 | 9.5 → 5.0 | 0.05 → 0.01 |
| Upload handed to TCP, 4–8 s; 4–5 s | 115 → 112 %; 145 → 163 % | 85 → 76 %; 110 → 116 % | 5 → 4 % |
| Download, 4–8 s | 41 → 49 % | 50 → 54 % | 3 → 3 % |
| PQ sends dropped after 1 s in a peer queue | 49 → 45 % | 52 → 50 % | 39 → 26 % |
| PQ mesh: degree, 1 Gbit share | 6.1, 35 → 5.7, 81 % | 6.5, 36 → 6.0, 80 % | 8.1, 54 → 7.2, 85 % |

- Fast peers deliver more of each slot (per-signature misses fall by 40–45 %), but a home node still forwards every
  message to its own ~6 mesh peers. Its uplink stays above capacity, and the first second gets worse (50/15: 163 % in
  4–5 s), so the share of home nodes holding every signature does not improve.
- 50/15 late first deliveries rise slightly over the run (13.1 → 14.6 per node and slot between the halves).

### Perturbations, TCP and node count at 400 signatures per subnet per slot

At 400, 50/15 nodes just fail with the full realism layer, so the perturbation, TCP and node-count levers ran at this
load.

| 400 signatures per subnet per slot; every class must hold all 400 at 8.0 s | Full realism (load run) | No packet loss, churn, NAT or slow CPUs | No slow start after idle | 512 hosts |
|---|---|---|---|---|
| 50/15: complete at 8.0 s, worst slot (mean) | 98.5 % (99.3 %): fail | 99.4 % (99.95 %): pass | 99.1 % (99.7 %): pass | 98.8 % (99.6 %): fail, 1 of 86 (the rule allows none) |
| 50/25: complete at 8.0 s, worst slot (mean) | 99.1 % (99.6 %): pass | 100 % (100 %): pass | 99.5 % (99.8 %): pass | 99.2 % (99.9 %): pass |
| 1 Gbit: complete at 8.0 s, worst slot | 100 %: pass | 100 %: pass | 100 %: pass | 100 %: pass |
| Incomplete node-slots, 50/15 / 50/25 (2,048 hosts: of ~5,900 / ~17,500) | 41 / 77 | 3 / 0 | 20 / 42 | 7 / 6 (of 1,547 / 4,365) |
| Signatures missing at 8.0 s / 9.0 s, 50/15 | 0.046 / 0.023 % | 0.002 / 0.002 % | 0.016 / 0.009 % | 0.023 / 0.016 % |
| Signatures missing at 8.0 s / 9.0 s, 50/25 | 0.025 / 0.009 % | 0 / 0 | 0.012 / 0.006 % | 0.004 / 0.002 % |
| Signatures held at 5 s, 50/15 / 50/25 | 72 / 82 % | 90 / 94 % | 80 / 88 % | 72 / 85 % |
| Last needed signature, p99, 50/15 / 50/25 | 7.4 / 6.9 s | 6.3 / 5.7 s | 6.6 / 6.3 s | 7.2 / 6.2 s |
| Late first deliveries (8–16 s) per node and slot, 50/15 | 0.04 | 0.00 | 0.01 | 0.01 |
| Upload handed to TCP, 50/15: 4–8 s; 4–5 s | 56 %; 135 % | 55 %; 164 % | 56 %; 143 % | 58 %; 139 % |
| PQ sends dropped after 1 s in a peer queue, 50/15 / 50/25 / 1 Gbit | 22 / 18 / 6 % | 15 / 8 / 3 % | 21 / 17 / 5 % | 21 / 18 / 6 % |
| IWANT requests per node and slot, 50/15 / 50/25 | 169 / 126 | 78 / 57 | 135 / 99 | 165 / 93 |

- **Without packet loss, churn, NAT or slow CPUs, every class passes.** The 3 incomplete 50/15 node-slots are on 3
  fiber hosts in slots 2–4, once each. Home nodes hand TCP the same bytes over 4–8 s but more of them in the first
  second, and fewer of their sends wait past 1 s.
- **With the perturbations, the misses near the boundary sit on DSL hosts.** DSL access links have the most loss (0.25 %
  each way, against 0.1 % for cable and 0.05 % for fiber), the longest latency (13 ms one way) and the most jitter. The
  run without the perturbations keeps the latency and jitter, and in it every DSL host is complete. NAT makes no
  difference (50/15 at 400: 99.4 % complete behind NAT, 99.3 % without), and a 3× slower CPU a small one for 50/15
  (98.8 vs 99.4 %) and none for 50/25. So packet loss on the home node's own access link is the most likely cause; the
  run removes all four perturbations at once, so this is inferred.

Home node-slots complete at 8.0 s by access type (mean over slots 2–19; 1,600: slots 2–14). 50/15: 143 fiber, 116
cable and 71 DSL hosts; 50/25: 448, 320 and 208.

| Signatures per subnet per slot (every class must hold all at 8.0 s) | 50/15 fiber / cable / DSL | 50/25 fiber / cable / DSL |
|---|---|---|
| 300 | 100 / 99.95 / 99.1 % | 100 / 99.98 / 99.7 % |
| 400 | 99.96 / 99.5 / 97.7 % | 99.95 / 99.8 / 98.3 % |
| 600 | 97.4 / 95.8 / 85.2 % | 99.7 / 98.6 / 88.8 % |
| 800 | 90.3 / 84.6 / 66.7 % | 98.1 / 94.9 / 75.9 % |
| 1,600 | 31.8 / 25.5 / 26.9 % | 62.3 / 55.6 / 42.2 % |
| 400, no packet loss, churn, NAT or slow CPUs | 99.9 / 100 / 100 % | 100 / 100 / 100 % |
| 400, no slow start after idle | 100 / 99.95 / 98.5 % | 100 / 99.97 / 98.9 % |

- At 300 and 400, DSL hosts hold 73–92 % of the incomplete home node-slots, although they hand less to TCP than fiber
  hosts (50/15 at 400: 50 vs 59 % of the uplink over 4–8 s).
- Fiber home nodes are 99.96 % complete at 400 (50/15) and 99.7 % at 600 (50/25), on average over the slots, and fall to
  97.4 % and 98.1 % one step higher. Without the perturbations the home boundaries would therefore likely lie one load
  step higher, at 400–600 (50/15) and 600–800 (50/25); this is inferred, not run.
- **No slow start after idle:** stock Linux drops a connection's congestion window back to its initial size after it
  has been idle for longer than one retransmission timeout, so each slot's burst starts in slow start on idle
  connections. With `net.ipv4.tcp_slow_start_after_idle=0`, every class passes at 400, 50/15 by the rule's last node
  (3 of 330 in its two worst slots). The signatures missing fall about 3× (50/15: 0.046 → 0.016 %) and the incomplete
  home node-slots halve; nearly all of those left are on DSL hosts (19 of 20 for 50/15, 40 of 42 for 50/25). One seed,
  so this is a margin, not a firm pass.
- **512 hosts instead of 2,048:** about the same. A home node's upload is set by its mesh degree, not by the node count
  (50/15: 58 vs 56 % of the uplink over 4–8 s), and 50/15 nodes again just fail. With only 86 50/15 hosts the rule
  allows no incomplete node, and one DSL host in Singapore holds 5 of the 7 incomplete node-slots. Per-signature misses
  halve (50/15: 0.023 vs 0.046 %), partly because the same 400 signatures travel in 73 messages instead of 137 (with
  fewer hosts, each holds more validators and its bundles are fuller) and in fewer hops. So a larger network would
  likely do slightly worse than 2,048 hosts, not better (inferred).

### Today's BLS attestations kept, 300 signatures per subnet per slot

PQ Gasper replaces today's BLS attestations, so every other run drops them. This run keeps them, as the earlier
studies did, at the highest load every class passes without them. They go out in the same window as the PQ signatures
and add about 1.3 MB per home node received in 4–8 s.

| 300 signatures per subnet per slot; every class must hold all 300 at 8.0 s | Without BLS attestations (load run) | With today's BLS attestations |
|---|---|---|
| 50/15: complete at 8.0 s, worst slot (mean) | 99.1 % (99.8 %): pass | 98.8 % in slot 2, then at least 99.1 % (99.6 %): fail |
| 50/25: complete at 8.0 s, worst slot (mean) | 99.7 % (99.9 %): pass | 99.7 % (99.9 %): pass |
| 1 Gbit: complete at 8.0 s, worst slot | 100 %: pass | 100 %: pass |
| Signatures missing at 8.0 s / 9.0 s, 50/15 | 0.012 / 0.007 % | 0.024 / 0.007 % |
| Signatures missing at 8.0 s / 9.0 s, 50/25 | 0.004 / 0.002 % | 0.005 / 0.002 % |
| Last needed signature, p99, 50/15 / 50/25 | 6.4 / 6.3 s | 7.1 / 6.4 s |
| Late first deliveries (8–16 s) per node and slot, 50/15 | 0.01 | 0.01 |
| Upload handed to TCP, 50/15: 4–8 s; 4–5 s | 46 %; 126 % | 63 %; 149 % |
| Upload handed to TCP, 50/25: 4–8 s; 4–5 s | 31 %; 93 % | 42 %; 108 % |
| PQ sends dropped after 1 s in a peer queue, 50/15 / 50/25 / 1 Gbit | 14 / 11 / 4 % | 18 / 14 / 6 % |

BLS attestations missing at 8.0 s in slots 2–15, against the run without PQ (`R20-nopq-rtt6-ps100-cf2-s1`: the same
hosts, stack and attestations):

| BLS attestations missing at 8.0 s (never delivered) | 50/15 | 50/25 | 1 Gbit |
|---|---|---|---|
| Without PQ | 0.007 % (0) | 0.015 % (0) | 0.99 % (0.39 %) |
| With 300 PQ signatures per subnet per slot | 0.063 % (0) | 0.038 % (0.004 %) | 1.11 % (0.36 %) |

- 50/15 nodes fail the rule in slot 2 only, by one node (4 of 330 incomplete; the rule allows 3), and pass every slot
  from slot 3. Their signatures missing double but stay at 0.024 %. 200 would likely pass with the BLS attestations
  too (not run).
- Home BLS attestations missing at 8.0 s rise 9× (50/15) and 2.5× (50/25) but stay below 0.1 %, and nearly all arrive
  later. The 1 Gbit misses all fall on the 176 hosts that join all 64 attestation subnets, as without PQ.
- Blocks are unaffected: none missing, and the block p95 from publish is 0.44–1.01 s per slot (mean 0.69 s), against
  0.52–1.05 s (mean 0.76 s) without PQ. Without PQ, 90 % of block deliveries are done 3.0 s into the slot, before the
  signatures go out.

### What holds back delivery to home nodes

Home downloads average 41–50 % in the 4–8 s window, so the downlink is not the limit. One run (512 hosts × 8 slots,
1,600 signatures per subnet per slot) made 30 % of all hosts leaves that receive but never forward (`--freeride-share
0.3`), so forwarding and non-forwarding nodes on the same links share one network. This is a diagnostic, not a protocol
option.

| 1,600 signatures per subnet per slot; every class must hold all 1,600 at 8.0 s (512 hosts, slots 2–7) | 50/15 forwarding | 50/15 leaf | 50/25 forwarding | 50/25 leaf | 1 Gbit forwarding | 1 Gbit leaf |
|---|---|---|---|---|---|---|
| Nodes holding all at 8.0 s, mean | 24.9 % | 74.0 % | 52.7 % | 79.1 % | 97.9 % | 97.7 % |
| Signatures missing at 8.0 s | 17.3 % | 2.2 % | 6.6 % | 2.0 % | 0.25 % | 0.11 % |
| Upload, 4–8 s | 106 % | 2 % | 88 % | 1 % | 6 % | 0.2 % |
| Download, 4–8 s | 31 % | 46 % | 40 % | 47 % | 2.5 % | 2.0 % |

TCP on the paths from 1 Gbit senders into these nodes, per 1,000 data packets (`.amp-out/leafdiag-Q512x8-m1600-leaf30-s1.txt`):

| Path | TCP timeouts | Retransmitted packets | Smoothed RTT minus the path's base RTT, p50 / p90 / p99 |
|---|---|---|---|
| 1 Gbit → 50/15 forwarding | 12.9 | 49 | 44 / 179 / 441 ms |
| 1 Gbit → 50/15 leaf | 0.41 | 2.7 | 7 / 11 / 24 ms |
| 1 Gbit → 50/25 forwarding | 6.7 | 25 | 12 / 49 / 143 ms |
| 1 Gbit → 50/25 leaf | 0.41 | 2.6 | 6 / 11 / 26 ms |
| 1 Gbit → 1 Gbit | 0.20 | 0.4 | 1 / 3 / 5 ms |

- **The receiving home node's own uplink is the main cause.** The same senders reach a forwarding home node with 16–31×
  the TCP timeouts of a leaf on the same link, and with tens to hundreds of milliseconds more RTT. What differs is the
  receiver's uplink: the forwarding node's ACKs wait behind its own forwards (measured as the RTT above), and so do its
  IWANTs and IDONTWANTs, which share the gossipsub send queue with forwards in rust-libp2p 0.49 (not measured
  separately). After the timeouts the senders' windows collapse, their queues to the node back up, and forwards that
  waited 1 s are dropped. Even 1 Gbit nodes drop 39 % of their PQ sends while using 5 % of their uplink.
- **Saturated mesh peers that drop forwards are the smaller part.** Leaves, whose uplinks are idle, still miss 2 % and
  stay at 74–79 % complete. Home senders reach them with 2.5–3.4 timeouts per 1,000 packets, against 0.4 from 1 Gbit
  senders. (Inferred: the misses are not split by sender.)
- A home node's mesh makeup does not predict completeness. In the headline run, 50/15 node-slots with every signature
  had 32.5 % 1 Gbit peers in their PQ mesh, and those missing some had 36.2 %.
- **Near the boundary, packet loss on a home node's own access link decides which home nodes miss.** At 300 and 400,
  DSL hosts hold 73–92 % of the incomplete home node-slots although they hand less to TCP than fiber hosts, and all of
  them are complete once loss, churn, NAT and slow CPUs are off (see "Perturbations, TCP and node count at 400
  signatures per subnet per slot"). At 1,600 every access type fails by far.
- **Levers that should help** therefore cut a home node's upload in the 4–8 s window: fewer signature bytes per slot,
  not forwarding, a lower mesh degree for home nodes, or uplink queueing that does not hold ACKs and control messages
  behind data. TCP without slow start after idle helps at the margin. A larger 1 Gbit share does not cut a home node's
  own forwarding duty, and the run with 80 % of hosts on 1 Gbit confirms that it does not rescue home nodes at 1,600.

### 800 signatures as a stand-in for 1,600 signatures of about 1.2 kB

Potuz expects attestations to carry "2KB or 1.2KB signatures" (https://www.potuz.net/posts/pq/; 1.2 kB without native
DVT support). 800 signatures of 2,404 B carry 1.92 MB per slot, about as much as 1,600 of 1.2 kB, so the 800 run
approximates that option. Two things differ:

- **Messages:** with bundles of up to 16 per publisher, 1,600 signatures of 1.2 kB make about 302 messages per slot,
  the 800 run 203. Each message costs every node control traffic whatever its size (IHAVE to about a quarter of its
  non-mesh peers over three heartbeats, IDONTWANT, IWANT, framing). The traffic a node receives in 4–8 s besides PQ
  messages rises by 2.8–3.7 kB per extra message per slot from the 200 to the 400 to the 800 run. The 99 extra messages
  would add about 0.3 MB per node in the 4–8 s window: 4–5 % of a 50/15 uplink and 2–3 % of a 50/25 uplink over those
  4 s. The 512-host run points the same way: it carries the same 400 signatures in 73 messages instead of 137 and
  misses half as many (50/15: 0.023 vs 0.046 %), though its node count differs too.
- **Verifications:** 1,600 instead of 800 per slot, if a 1.2 kB signature takes as long to verify as leanXMSS (400 µs
  per signature here). This should not matter: at 1,600, home nodes with a 3× slower CPU did no worse (50/15: 25.9 vs
  29.0 % complete; 50/25: 59.5 vs 55.0 %).

So the 800 run is slightly optimistic for the 1.2 kB option. It already fails for both home classes (worst slot 77.9 %
and 90.8 %), so the different message count changes the margin, not the verdict.

## Caveats

- Every client uses rust-libp2p 0.49.5's send queues: forwards dropped after 1 s in a peer's queue, publishes after
  5 s, and control messages (IHAVE, IWANT, IDONTWANT) in the same queue as forwards. Lighthouse's fork keeps control
  messages in a separate queue, and the non-Rust libraries do not expire queued messages.
- The scoring's maximum positive score still counts the 64 attestation subnets (weight 1) next to the PQ subnets. A
  PQ Gasper client would count only the PQ subnets, so the Teku, Lodestar and Nimbus mesh-delivery penalty for a full
  deficit is −157.5 here instead of −107.5. Both push a peer below 0, which prunes it from the mesh.
- 2,048 hosts stand for one subnet's members. The calibration found the sim's blocks spread faster than mainnet's
  (about one gossip hop fewer than a ~10k-node network). 512 hosts did slightly better than 2,048, so a larger network
  would likely do slightly worse.
- One seed per run. Verdicts decided by the last node the rule allows (50/15 at 300, and at 400 without slow start
  after idle: 3 of 330 incomplete in the worst slot) could flip with another seed.
- The runs last 20 slots (the 1,600 headline 15). Duplicate copies arriving after 8 s and home upload still rise at
  the end of the runs while late first deliveries stay flat, so longer runs could move the boundaries down.
- Mesh-delivery scoring on the PQ topic starts around slot 15. The 20-slot runs cover its first five slots without a
  clear change in delivery; the 1,600 headline stops before it.

## Commands and files

```sh
# one run: NAME HOSTS SLOTS THREADS [lever flags]; ONE flags in runs/run_pq1600.sh, base flags in runs/run_lever.sh
bash runs/run_pq1600.sh Q2048x20-m1600-s1 2048 20 46
# queue: runs/pq1600-queue.sh reads runs/queue-pq1600.txt; watchdog runs/watchdog256.sh 235 30; runs/memlog.sh;
#   half-budget guard runs/pq1600-guard.py; runs/pq1600-memresume.sh. All stopped when the study ended; start each with
#   nohup setsid taskset -c 48-95 nice -n 19 bash runs/SCRIPT ARGS > /dev/null 2>&1 < /dev/null &  (python3 for the guard)
# analysis: python3 -I .amp-out/pq1600.py RUN --per-slot (classes, per-signature misses, completion times, late first
#   deliveries, upload and download, dropped forwards, PQ mesh); .amp-out/pqdiag.py; .amp-out/late.py;
#   .amp-out/leafdiag.py RUN (TCP timeouts by path type, leaves split out; runs with tcpd logging);
#   env SPLIT=access (or nat, city) and SPLITCPU=1 split the home classes by access type, NAT or slow CPU;
# BLS and blocks: .amp-out/pqdiag.py RUN --slots 2 15; .amp-out/attmiss.py RUN; .amp-out/blockslot.py RUN [RUN ...]
```

- `sim/gen_config.py`: `--single-subnet N` (every signature on PQ topic 1, which every node joins; scored as one of N
  PQ subnets). Without it, `--sig-subnets 1` puts the signatures on topic 0, which the scoring does not cover.
- `sim/perturb.py`: `--no-att` (no BLS attestations or attestation-subnet subscriptions; the random draws stay, so the
  other background traffic is unchanged).
- Old flag sets still give byte-identical configs.
