# What would make 2,000 × 3 kB PQ signatures per slot work over gossipsub?

Follow-up to [gossip-2000.md](gossip-2000.md), on the p2psims machine. Same simulator: Shadow 3.3.0 (patched), real
rust-libp2p 0.56 nodes (gossipsub 0.49.5), a mainnet validator sample from `nodes.csv`, five regions with
mainnet-like latencies.

Fixed throughout (Yann's constraints):

- **Success means every node holds every signature within 4 s of the start of publishing.** No run here uses an 8 s
  or 12 s deadline; the one planned relative-deadline run (`e-spread8`) was dropped before it ran.
- **The bandwidth baseline is EIP-7870:** 50/25 Mbit/s for validator hosts and 50/15 for hosts without validators.
  Hosts with more than *k* = 8 validators run 1 Gbit. Of the rest, 20 % run 1 Gbit, as in phase 1; "fs0" rows drop
  that random share, so only the hosts with more than *k* validators are fast. The only requirement levers are
  *k* = 1 (EIP-7870 applies only to hosts with one validator or none) and per-validator scaling (`scale`: a host with
  n validators gets n × 50/25, capped at 1 Gbit, so hosts with 40 or more validators reach the cap).
- **Bundled attestations are allowed,** and bundling is a primary axis of the sweep.
- **Requirement changes are kept apart** (last section): smaller signatures, and delivery only to subnet subscribers
  (which gives up validator anonymity). They are not in the feasibility map.

## Answer

**Yes, with a gossipsub topology change and no new hardware requirement: a two-tier mesh.** Hosts already on 1 Gbit
form the mesh. EIP-7870 hosts attach to it as **leaves**:

- **Leaves** dial 4 1 Gbit hosts in their own region, keep exactly one mesh peer (`D = D_lo = D_hi = 1`), and
  **never forward**: they validate every message as `Ignore`, so gossipsub delivers it locally but does not relay it.
  Their own signatures still go out. They also receive IHAVE from all 4 connections, and they pull with IWANT
  whatever their one mesh link misses.
- **1 Gbit hosts** keep Ethereum's D = 8, raise `D_hi` from 12 to 16 so the leaves fit, and keep queued forwards for
  3 s instead of rust-libp2p's 1 s.
- **Bundles of 16 signatures per message,** packed by the publishing host from its own validators. Without
  bundling, the 1 Gbit hosts' send queues must hold 20,000 messages instead of 5,000.

At 2,048 hosts × 10 slots, at least 99.9 % of nodes, in every link class, held all 2,000 signatures within 4 s in
every slot, for each of 4 seeds:

- From slot 2 on, 6 of 65,536 node·slots missed the deadline, all in seed 1 and all by at most 28 ms. Over all 10
  slots, 10 of 81,920 node·slots missed (99.99 % complete). A 20-slot run had no misses at all after slot 1. The worst node·slot still held 97 % of its messages at
  4 s.
- Leaves completed in 1.7 s at the median and 2.5 s at p99; 1 Gbit hosts completed in 0.7 s and 0.8 s.
- κ was 2.8. Leaves received 1.45 copies of each message and uploaded almost nothing. 1 Gbit hosts used 10 % of
  their uplink over the 4 s window (18 % on the busiest node).
- Backlog was flat: 0.00 MiB per node still arriving after the deadline in the last slot, and nothing to drain.

On the same links, today's random mesh gets 31–38 % of nodes complete (the EIP-7870 classes 0–2 %), whatever the
bundle size. With bundles of 16 and the 3 s queue but a random mesh (`X2048-b16-fq3-s1`), 38–40 % complete in slots
0–3, then 0 % from slot 4 on, as the backlog grows.

Leaves with a mesh of 2 instead of 1 also pass at 2,048 × 10 (3 seeds, zero misses after slot 1), but with less
margin: slow hosts' p99 completion is 3.5 s instead of 2.5 s, and they fail first as the load grows.

**It does not depend on the random 20 % 1 Gbit share,** on bundling, or on the bundling method. It also passed at
2,048 × 10 under each of these:

- only hosts with more than 8 validators on 1 Gbit, i.e. 415 of 2,048 hosts (20 %);
- only hosts with more than 16 validators on 1 Gbit, i.e. 279 hosts (14 %);
- *k* = 1;
- no bundling, with 20,000-message queues;
- 64-signature bundles made by a first-hop 1 Gbit bundler;
- 1 ms of serial verification per signature (see below).

**Bundling alone fixes nothing.** On a random mesh, bundles of 4, 16 or 64 leave completion at 35–38 %. They cut the
number of messages and IDs, not the bytes. EIP-7870 nodes still receive about 3 copies of everything and try to
forward copies their uplink cannot carry: libp2p writes 110–140 % of the uplink cap during the 4 s window, and the
excess sits in kernel buffers. In the two-tier mesh, bundling replaces the queue-size change.

**Where it breaks:**

- **Messages per slot.** 3,000 still passes at 2,048 hosts: 99.8 % of slow-node·slots are complete, and the misses
  are spread thinly. 4,000 fails: 93–97 % complete at 512 hosts with bundles of 16 or 64. The limit is the leaf's
  50 Mbit/s downlink: 4,000 × 3 kB × 1.4 copies is about 17 MB in 3.5 s, i.e. 40 Mbit/s.
- **Too small a core.** With D_hi = 16, the core needs about 1 Gbit host per 8 leaves. With 8 % of hosts fast,
  96–98 % complete; with 4 % fast, 5–86 %. Raising the fast hosts' D_hi fixes most of it: with D_hi = 32 and only
  hosts above 64 validators on 1 Gbit (8.6 % of hosts), it passes at 2,048 × 10 with zero misses. With 4 % fast and
  D_hi = 48 it still reaches only 96–97 %. Today's mainnet sample has 20 % of hosts above 8 validators, so the core
  is large enough with margin.
- **Verification CPU.** With 1 ms of serial verification per signature, 2,000 and 3,000 per slot pass, and 4,000
  fails (2 % complete), because 4 s of verification does not fit in 4 s. At 0.1 ms there is no visible effect.

## Feasibility map

Judged on per-class completion at 4 s, from slot 2 on, with a flat backlog. "Pass" means at least 99 % of each class
complete in every slot; "confirmed" means 2,048 hosts × 10 slots.

| condition | result at 4 s | cost | distance from today's mainnet | distance from EIP-7870 |
|---|---|---|---|---|
| Today's gossipsub, EIP-7870 links (`e-base`) | **fail**: 31–36 % of nodes, slow classes 0 % | – | – | – |
| Bundling alone (4, 16, 64; publisher or first-hop bundler) | **fail**: 35–38 %, slow classes 0–2 % | Message format: one gossip message carries several signatures | Bundled attestations | None |
| Queue tuning alone (forward queue 3 s), or verification pacing alone | **fail**: 37–43 %, and 0 % in slot 4 with the 3 s queue | Client config | Small | None |
| *k* = 1 or per-validator links, random mesh | **fail**: 58–71 %, single-validator and 50/15 hosts 0 % | Hardware for multi-validator hosts | Hardware | Applies EIP-7870 differently, not more strictly |
| Random mesh with smaller meshes for slow nodes (`D = 1–3`, slow dial fast only) | **fail**: 45–85 % | Peer-selection policy | Gossipsub topology | None |
| Smaller leaf meshes that still forward, local dial, b16, fq 3 s (`g-leaf1-b16-fq3-local`) | near pass: 98–100 %; 50/15 class 95 % | As below, but leaves keep forwarding | Topology change | None |
| **Two-tier mesh: no-forward leaves (D = 1, 4 local fast peers), fast D_hi 16, fq 3 s, bundles of 16** (`W2048-w1-b16`) | **pass, confirmed, 4 seeds**: ≥ 99.9 % of each class in every slot; slow p99 completion 2.5 s | Gossipsub change: per-node mesh roles, leaves do not forward, 1 Gbit hosts carry all relaying (10 % of their uplink in the window) | Protocol change in peer selection and forwarding, plus bundling | None: leaves need 0 upload and about 35 % of a 50 Mbit/s downlink on average |
| Same, no random 1 Gbit share (only > 8 validators on 1 Gbit) | **pass, confirmed, 3 seeds**, zero misses after slot 1 | Same | Same | None |
| Same, only > 16 validators on 1 Gbit (14 % of hosts) | **pass, confirmed, 1 seed** | Same | Same | None |
| Same, without bundling, send queues 20,000 messages | **pass, confirmed, 1 seed**: 25 of 10,448 slow node·slots missed from slot 2 on | Client config instead of bundling | Same, minus bundling | None |
| Same, first-hop bundler (64) instead of publisher bundling | **pass, confirmed, 1 seed** | Bundlers wait for signatures (+150 ms hop assumed) | Same + bundler role | None |
| Same with *k* = 1, or with per-validator links (no random share) | **pass, confirmed**: *k* = 1 zero misses; per-validator links 99.8 % of node·slots with D_hi 16, 99.99 % with D_hi 32 | Hardware for multi-validator hosts (not needed for the pass) | – | – |
| Same with 1 ms of serial verification per signature | **pass, confirmed**; κ halves to 1.35 | CPU: 2 s of verification per slot per node | – | – |
| 3,000 messages per slot, two-tier mesh | **pass, confirmed**: 99.8 % of slow node·slots | – | – | – |
| 3,500 messages per slot | marginal: 99–100 % at 512 hosts | – | – | – |
| 4,000 messages per slot | **fail**: 93–97 % | Leaf downlink is the limit | – | – |
| Core of 4–8 % of hosts | **fail** (5–98 %) with D_hi 16 at 512 hosts. With D_hi 32, only hosts above 64 validators on 1 Gbit (176 of 2,048, 8.6 %): **pass, confirmed**, zero misses | Fast hosts carry up to 32 mesh peers | – | – |

Excluded by Yann's constraints, not in the map: longer deadlines (8 s, 12 s, or one relative to each publish time),
a 100/50 baseline, and an arbitrary higher 1 Gbit share. Requirement changes are in their own section below.

### What each piece of the winning setup does

- **Leaves don't forward.** On a random mesh, an EIP-7870 node forwards each of 2,000 messages to up to 8 peers. That
  is 6 MB × 8 per slot on a 15–25 Mbit/s uplink: impossible in 4 s. Its uplink fills, its queues drop forwards
  (1–3 million per slot network-wide), and its peers wait. A leaf uploads only its own signatures.
- **Mesh of 1 plus IHAVE/IWANT.** A leaf receives about 1.45 copies of each message: one from its mesh peer and the
  rest pulled with IWANT after IHAVE from its other 3 fast peers. That is about 9 MiB per slot, 35 % of a 50 Mbit/s
  downlink over the 4 s window. A D = 2 leaf receives about 2 copies and misses more often at 3,000 messages
  (`w-b16-m3000`: 93 % vs 100 %).
- **Same-region fast peers.** Without them, leaves in Asia and Oceania fetch from far-away peers, and 10–12 % of slow
  node·slots miss the deadline (`w1-b16-nolocal`).
- **Fast forward queue of 3 s.** With rust-libp2p's 1 s, the 1 Gbit hosts drop forwards to leaves during the burst,
  and 6–7 % of slow node·slots miss (`w1-b16-nofq`).
- **D_hi 16 on fast hosts.** Each fast host must hold its 8 core peers plus the leaves that graft onto it. D_hi 12 was
  not run; the review predicted that it makes fast hosts prune leaves, which then churn under the 60 s backoff. With
  too few fast hosts (fewer than about 1 per 8 leaves), leaves are left without a mesh peer, and raising D_hi to 32
  or 48 recovers most of it.
- **Bundles.** They cut the message count by about 6 (2,000 → about 350 messages per slot, since single-validator
  publishers can't bundle). Without them, 1 Gbit hosts' 5,000-message send queues overflow toward 20–60 peers, and
  11–16 % of slow node·slots miss (`g-leaf2-nofwd-fq3-local`). A 20,000-message queue fixes it just as well.

### Who bundles, and what it costs

- **Publisher bundling (`--batch N`):** a host packs its own validators' signatures into messages of up to N and
  publishes each when its last signature is ready. With mainnet's validator skew, about half the signatures go out in
  full 16-signature bundles. About 7 % go out alone, from hosts with a single signer that slot. Cost: up to the
  0.5 s publish window of extra latency for the first signature in a bundle, and nothing else. It needs no trust
  beyond what the host already has.
- **First-hop bundler (`--bundler N`):** 16 1 Gbit hosts each collect signatures and publish bundles of N, 150 ms
  after the last one arrives (an assumed collection hop). Cost: about 0.15–0.65 s of extra latency. It works: slow
  hosts complete at 2.0 s p50 and 2.7 s p99, against 1.7/2.5 s with publisher bundling. But bundlers become a liveness
  and censorship point, and their 150 ms hop is assumed, not simulated.

## Tables

All 512-host rows have 5 slots; "W2048" rows have 2,048 hosts and 10 slots. Base flags as in
[gossip-2000.md](gossip-2000.md): *k* = 8, 20 % random 1 Gbit share, EIP-7870 links, 2,000 × 3,072 B per slot,
published over 0.5 s from 4 s into the slot, deadline 4 s later. Columns:

- **complete per slot:** % of nodes holding every needed message at 4 s;
- **per class:** % of node·slots complete, by link class (`cloud` = 1 Gbit);
- **latency:** p50/p90/p99 from each message's publish to first receipt, "never" if more than 1 % never arrive;
- **κ:** bytes received ÷ useful bytes, slots 2 onward;
- **fwd dropped:** forwards rust-libp2p dropped from full or timed-out queues, per slot, network-wide;
- **after deadline:** MiB per node still arriving 4–8 s after the deadline, in the first and last slot; growth means
  backlog.

### 1. Today's random mesh: bundling, queue, verification and link levers (512 hosts)

| run | change | complete per slot (%) | per class (%) | latency (s) | κ | fwd dropped | after deadline (MiB) |
|---|---|---|---|---|---|---|---|
| `e-base` | mainnet gossipsub (baseline) | 32 36 36 36 0 | 50x15 0, 50x25 0, cloud 78 | 1.17/6.76/never | 3.15 | 3,304k | 4.00→5.19 |
| `e-batch4` | bundles of 4 | 36 36 36 36 36 | 50x15 0, 50x25 2, cloud 99 | 1.12/4.97/never | 2.95 | 961k | 3.16→4.20 |
| `e-batch16` | bundles of 16 | 35 36 36 36 38 | 50x15 0, 50x25 2, cloud 99 | 1.05/4.50/never | 2.86 | 370k | 3.17→3.96 |
| `e-batch64` | bundles of 64 | 35 36 36 37 37 | 50x15 0, 50x25 1, cloud 99 | 0.43/4.02/never | 2.92 | 202k | 3.23→4.17 |
| `e-bund16` | first-hop bundler, 16 | 35 37 36 37 36 | 50x15 1, 50x25 2, cloud 99 | 1.19/5.55/never | 3.23 | 207k | 3.25→5.61 |
| `e-bund64` | first-hop bundler, 64 | 36 36 37 36 36 | 50x15 0, 50x25 2, cloud 99 | 1.30/6.29/never | 3.48 | 58k | 3.62→6.50 |
| `x-b16-fq3` | b16 + forward queue 3 s | 40 39 39 39 0 | 50x15 2, 50x25 6, cloud 80 | 1.07/5.51/never | 3.99 | 278k | 6.75→7.47 |
| `x-b16-v1000` | b16 + 1 ms/sig verification | 37 40 42 41 39 | 50x15 2, 50x25 9, cloud 100 | 1.39/3.61/never | 2.82 | 371k | 2.86→3.99 |
| `x-b16-fq3-v1000` | b16 + fq 3 s + 1 ms/sig | 38 43 43 38 37 | 50x15 1, 50x25 9, cloud 100 | 1.39/4.62/never | 3.94 | 254k | 7.78→8.35 |
| `e-k1` | k = 1 | 69 71 71 71 71 | 50x15 0, 50x25 1, cloud 99 | 0.14/15.19/never | 4.46 | 2,088k | 1.46→1.92 |
| `e-batch16-k1` | k = 1 + b16 | 71 71 71 71 71 | 50x15 0, 50x25 0, cloud 100 | 0.14/4.85/never | 4.15 | 217k | 0.70→1.42 |
| `e-scale` | per-validator links | 58 61 61 62 63 | 50x15 0, cloud 99, v1 0, v10-39 100, v2-3 55, v4-9 98 | 0.41/7.93/never | 3.57 | 3,010k | 1.63→2.52 |
| `e-base-sb256k` | baseline, fixed 256 KiB send buffers | 31 31 30 31 31 | 50x15 0, 50x25 1, cloud 85 | 1.26/5.22/never | 3.09 | 3,763k | 3.83→4.02 |

None of these pass. Bundling cuts dropped forwards (3.3 M → 0.06–1 M per slot) and IDONTWANT IDs (32,000 → 4,500
per node per slot), but not bytes: κ stays at 2.9–3.5 and EIP-7870 hosts stay at 0–2 %. Duplicates remain: about
3 copies per message. IDONTWANT can't stop a 3 kB message that is already on the wire, and rust-libp2p 0.49 does not
cancel queued forwards.

### 2. Toward the two-tier mesh (512 hosts)

| run | change | complete per slot (%) | per class (%) | latency (s) | κ | fwd dropped | after deadline (MiB) |
|---|---|---|---|---|---|---|---|
| `e-slowd3-s2f` | slow D = 3, dial fast only | 50 49 47 45 51 | 50x15 12, 50x25 23, cloud 100 | 0.54/3.08/never | 3.32 | 1,251k | 0.13→0.76 |
| `e-leaf2` | slow D = 2, dial 4 fast | 65 60 58 52 56 | 50x15 36, 50x25 35, cloud 100 | 0.50/2.49/never | 3.05 | 620k | 0.08→0.50 |
| `e-leaf2-batch16` | + b16 | 73 73 72 74 85 | 50x15 61, 50x25 62, cloud 100 | 0.40/1.80/never | 2.92 | 43k | 0.10→0.27 |
| `e-leaf2-batch16-idw` | + IDONTWANT on publish | 72 73 72 75 85 | 50x15 58, 50x25 64, cloud 100 | 0.40/1.79/never | 2.93 | 44k | 0.09→0.24 |
| `e-leaf1-batch16` | slow D = 1 + b16 | 75 76 73 74 85 | 50x15 62, 50x25 64, cloud 100 | 0.41/1.75/never | 2.94 | 40k | 0.10→0.25 |
| `e-leaf1-b16-fq3` | + fast forward queue 3 s | 89 91 92 93 97 | 50x15 89, 50x25 88, cloud 100 | 0.40/1.73/3.49 | 3.08 | 21k | 0.48→0.37 |
| `r-core-leaf2-nofwd` | slow D = 2, no forward | 72 61 58 58 62 | 50x15 41, 50x25 42, cloud 99 | 0.48/2.20/never | 2.72 | 500k | 0.05→0.31 |
| `r-core-leaf2-nofwd-b16-fq3` | + b16 + fq 3 s | 90 91 93 96 97 | 50x15 91, 50x25 89, cloud 100 | 0.39/1.63/3.27 | 2.87 | 4k | 0.43→0.45 |
| `g-leaf1-b16-fq3-local` | D = 1 forwarding leaf, b16, fq 3 s, local dial | 98 99 99 99 100 | 50x15 95, 50x25 100, cloud 100 | 0.30/1.12/2.04 | 3.05 | 12k | 0.04→0.01 |
| `w-b16-nolocal` | D = 2 no-forward leaf, b16, fq 3 s, any-region dial | 90 91 94 96 97 | 50x15 91, 50x25 90, cloud 100 | 0.39/1.62/3.29 | 2.87 | 4k | 0.45→0.43 |
| `w-b16-nofq` | D = 2 no-forward leaf, local, b16, fq 1 s | 89 81 74 78 89 | 50x15 67, 50x25 74, cloud 100 | 0.31/1.13/never | 2.53 | 35k | 0.00→0.00 |
| `w1-b16-nolocal` | winner, any-region dial | 89 90 93 94 96 | 50x15 88, 50x25 89, cloud 100 | 0.40/1.70/3.39 | 2.86 | 1k | 0.39→0.37 |
| `w1-b16-nofq` | winner, fq 1 s | 99 97 93 92 98 | 50x15 93, 50x25 94, cloud 100 | 0.28/0.91/1.39 | 2.72 | 9k | 0.00→0.00 |
| `w1-b16-dial2` | winner, leaves dial 2 fast peers | 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.26/0.84/1.39 | 2.73 | 0k | 0.00→0.00 |
| `w1-b16` | **winner**: D = 1 no-forward leaf, 4 local fast peers, b16, fq 3 s | 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.27/0.89/1.35 | 2.77 | 0k | 0.00→0.00 |

### 3. Bundling axis on the two-tier mesh (512 hosts)

| run | change | complete per slot (%) | per class (%) | latency (s) | κ | fwd dropped | after deadline (MiB) |
|---|---|---|---|---|---|---|---|
| `g-leaf2-nofwd-fq3-local` | no bundling, 5,000-msg queue (D = 2 leaf) | 94 94 92 92 92 | 50x15 85, 50x25 90, cloud 100 | 0.39/1.32/never | 2.61 | 416k | 0.02→0.00 |
| `w-b1-q20k` | no bundling, 20,000-msg queue (D = 2 leaf) | 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.38/1.25/2.01 | 2.97 | 32k | 0.08→0.04 |
| `w1-b1-q20k` | no bundling, 20,000-msg queue | 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.34/1.07/1.64 | 2.98 | 4k | 0.02→0.02 |
| `w-b4` | bundles of 4 (D = 2 leaf) | 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.33/1.13/1.94 | 2.83 | 5k | 0.01→0.00 |
| `w1-b16` | bundles of 16 | 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.27/0.89/1.35 | 2.77 | 0k | 0.00→0.00 |
| `w-b64` | bundles of 64 (D = 2 leaf) | 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.22/1.04/1.84 | 2.79 | 0k | 0.03→0.00 |
| `w-bund16` | first-hop bundler 16 (D = 2 leaf) | 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.38/1.24/2.00 | 2.77 | 0k | 0.01→0.01 |
| `w-bund64` | first-hop bundler 64 (D = 2 leaf) | 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.54/1.49/2.25 | 2.76 | 0k | 0.08→0.04 |

Time to complete for slow hosts, slots 2 onward (p50/p99): b16 1.7/2.4 s; b4 1.9–2.0/3.3–3.4 s; b64 2.0–2.1/3.3–3.4 s
(D = 2 leaves); first-hop bundler 16 2.1/3.3–3.5 s, bundler 64 2.3/3.6 s; no bundling with 20,000-message queues
1.9–2.1/2.9–3.6 s.

### 4. Robustness and limits of the two-tier mesh (512 hosts)

| run | change | complete per slot (%) | per class (%) | latency (s) | κ | fwd dropped | after deadline (MiB) |
|---|---|---|---|---|---|---|---|
| `w1-b16-fs0` | no random 1 Gbit share (99 fast, 19 %) | 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.36/0.93/1.45 | 1.82 | 0k | 0.00→0.00 |
| `w1-b16-k1-fs0` | k = 1, no random share (326 fast, 64 %) | 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.14/0.77/1.31 | 4.63 | 0k | 0.00→0.00 |
| `w1-b16-scale` | per-validator links | 100 100 100 100 100 | 50x15 100, cloud 100, v1 100, v10-39 100, v2-3 100, v4-9 100 | 0.16/0.73/1.29 | 1.88 | 0k | 0.00→0.00 |
| `w1-b16-fs0-k64` | only > 64 validators fast (41, 8 %) | 96 96 97 97 98 | 50x15 95, 50x25 97, cloud 100 | 0.47/1.25/7.94 | 1.48 | 0k | 0.12→0.08 |
| `w1-b16-fs0-k64-dhi32` | same, fast D_hi 32 | 99 99 99 100 100 | 50x15 100, 50x25 99, cloud 100 | 0.46/1.16/2.07 | 1.50 | 0k | 0.03→0.03 |
| `w1-b16-fs0-k256` | only > 256 validators fast (21, 4 %) | 5 6 80 86 86 | 50x15 54, 50x25 52, cloud 62 | 1.18/2.98/never | 1.10 | 0k | 0.16→0.09 |
| `w1-b16-fs0-k256-dhi48` | same, fast D_hi 48 | 96 97 97 98 97 | 50x15 94, 50x25 97, cloud 100 | 0.61/1.46/3.14 | 1.40 | 0k | 0.17→0.10 |
| `w-b16-m3000` | 3,000 msgs (D = 2 leaf) | 93 93 91 92 92 | 50x15 83, 50x25 90, cloud 100 | 0.47/1.84/3.21 | 2.78 | 20k | 0.42→0.16 |
| `w1-b16-m3000` | 3,000 msgs | 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.42/1.46/2.13 | 2.86 | 0k | 0.01→0.01 |
| `w1-b16-m3500` | 3,500 msgs | 99 100 100 100 100 | 50x15 99, 50x25 99, cloud 100 | 0.49/1.77/2.56 | 2.87 | 3k | 0.09→0.08 |
| `w1-b16-m4000` | 4,000 msgs | 93 96 95 97 97 | 50x15 93, 50x25 94, cloud 100 | 0.56/2.09/2.99 | 2.86 | 9k | 0.52→0.20 |
| `w1-b64-m4000` | 4,000 msgs, b64 | 96 96 95 96 97 | 50x15 93, 50x25 94, cloud 100 | 0.44/1.96/2.94 | 2.85 | 4k | 0.50→0.31 |
| `w-b16-m8000` | 8,000 msgs (D = 2 leaf) | 36 36 36 36 36 | 50x15 0, 50x25 0, cloud 100 | 1.26/never/never | 2.23 | 304k | 3.98→3.91 |
| `w-b16-v100` | 0.1 ms/sig verify (D = 2 leaf) | 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.31/1.13/1.99 | 2.73 | 1k | 0.01→0.00 |
| `w-b16-v1000` | 1 ms/sig verify (D = 2 leaf) | 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.81/1.52/1.75 | 1.24 | 0k | 0.00→0.00 |
| `w-b16-m3000-v300` | 3,000 msgs, 0.3 ms/sig (D = 2 leaf) | 94 94 93 93 93 | 50x15 84, 50x25 91, cloud 100 | 0.53/1.90/3.12 | 2.15 | 12k | 0.48→0.37 |
| `w-b16-m3000-v1000` | 3,000 msgs, 1 ms/sig (D = 2 leaf) | 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 1.30/2.40/2.70 | 1.18 | 0k | 0.00→0.00 |
| `w-b16-m4000-v1000` | 4,000 msgs, 1 ms/sig (D = 2 leaf) | 1 1 2 2 2 | 50x15 0, 50x25 0, cloud 4 | 1.80/3.28/3.68 | 1.14 | 0k | 0.25→0.12 |
| `w1-b16-sb256k` | winner, fixed 256 KiB send buffers | 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.35/0.95/1.46 | 2.72 | 5k | 0.43→0.19 |

- **Verification** is modelled as one serial verifier per node: each message waits n × (µs per signature) before
  it is accepted and forwarded. With 1 ms per signature, nodes spend 2 s of the 4 s window verifying. Completion
  still passes at 2,000 and 3,000, and κ falls to 1.2–1.35, because the delay lets IDONTWANT reach peers before they
  forward. At 4,000 it fails: 4 s of verification. The D = 2 leaf at 3,000 messages passes at 1 ms but not at
  0.3 ms; there the pacing from verification helps more than it costs. That case is not explored further.
- **Fixed 256 KiB send buffers** (Shadow autotuning off) change nothing for the winner (`w1-b16-sb256k`: 100 %) or
  the baseline (`e-base-sb256k`: 30–31 %). The kernel-buffer artefact the review asked about does not drive either
  result.

### 5. Confirmation at 2,048 hosts × 10 slots

| run | change | complete per slot (%) | per class (%) | latency (s) | κ | fwd dropped | after deadline (MiB) |
|---|---|---|---|---|---|---|---|
| `W2048-b16-s1` | D = 2 no-forward leaf, b16, seed 1 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.24/1.10/1.90 | 2.83 | 4k | 0.01→0.01 |
| `W2048-b16-s2` | same, seed 2 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.23/1.08/1.89 | 2.75 | 4k | 0.01→0.01 |
| `W2048-b16-s3` | same, seed 3 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.25/1.10/1.91 | 2.79 | 5k | 0.01→0.00 |
| `W2048-w1-b16-s1` | **winner**, seed 1 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.22/0.88/1.40 | 2.84 | 0k | 0.00→0.00 |
| `W2048-w1-b16-s2` | winner, seed 2 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.22/0.88/1.40 | 2.79 | 0k | 0.00→0.00 |
| `W2048-w1-b16-s3` | winner, seed 3 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.23/0.88/1.38 | 2.84 | 0k | 0.00→0.00 |
| `W2048-w1-b16-s4` | winner, seed 4 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.21/0.88/1.40 | 2.82 | 0k | 0.00→0.00 |
| `W2048-w1-b16-20slots-s1` | winner, 20 slots | 100 100 100 100 100 100 100 100 100 100 100 100 100 100 100 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.21/0.89/1.41 | 2.84 | 0k | 0.00→0.00 |
| `W2048-w1-b16-fs0-s1` | winner, no random 1 Gbit share, seed 1 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.30/0.90/1.41 | 1.82 | 0k | 0.00→0.00 |
| `W2048-w1-b16-fs0-s2` | same, seed 2 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.30/0.90/1.42 | 1.75 | 0k | 0.00→0.00 |
| `W2048-w1-b16-fs0-s3` | same, seed 3 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.31/0.90/1.42 | 1.79 | 0k | 0.00→0.00 |
| `W2048-w1-b16-fs0-k16-s1` | only > 16 validators fast (279, 14 %) | 100 100 100 100 100 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.33/0.92/1.45 | 1.59 | 0k | 0.00→0.00 |
| `W2048-w1-b16-k1-fs0-s1` | k = 1, no random share (1,347 fast) | 100 100 100 100 100 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.15/0.72/1.32 | 4.79 | 0k | 0.00→0.00 |
| `W2048-w1-b16-scale-fs0-s1` | per-validator links, no random share | 100 100 100 100 100 100 100 100 100 100 | 50x15 100, cloud 100, v1 99, v10-39 100, v2-3 100, v4-9 100 | 0.24/0.73/1.45 | 1.33 | 0k | 0.00→0.00 |
| `W2048-w1-b1-q20k-s1` | no bundling, 20,000-msg queues | 100 100 100 100 100 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.33/1.13/1.69 | 3.07 | 19k | 0.01→0.01 |
| `W2048-w1-bund64-s1` | first-hop bundler, 64 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.47/1.21/1.80 | 2.87 | 0k | 0.02→0.00 |
| `W2048-w1-b16-v1000-s1` | 1 ms/sig verification | 100 100 100 100 100 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.73/1.55/1.79 | 1.32 | 0k | 0.00→0.00 |
| `W2048-w1-b16-m3000-s1` | 3,000 msgs | 100 100 100 100 100 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.33/1.44/2.17 | 2.93 | 2k | 0.03→0.02 |
| `W2048-w1-b16-m3000-v1000-s1` | 3,000 msgs + 1 ms/sig | 100 100 100 100 100 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 1.22/2.45/2.75 | 1.24 | 0k | 0.00→0.00 |
| `X2048-b16-fq3-s1` | control: random mesh, b16, fq 3 s | 39 40 40 38 0 0 0 0 0 0 | 50x15 0, 50x25 2, cloud 40 | 0.84/5.24/never | 4.82 | 1,432k | 6.82→11.85 |
| `v2000-t8-eip7870` | phase-1 baseline (mainnet gossipsub) | 34 36 36 37 36 0 0 0 0 0 | 50x15 0, 50x25 0, cloud 49 | 1.03/6.92/never | 3.97 | 11,554k | 3.93→8.70 |
| `W2048-w1-b16-fs0-k64-dhi32-s1` | only > 64 validators fast, fast D_hi 32 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.39/0.98/1.51 | 1.47 | 0k | 0.00→0.00 |
| `W2048-w1-b16-scale-fs0-dhi32-s1` | per-validator links, no random share, fast D_hi 32 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100, cloud 100, v1 100, v10-39 100, v2-3 100, v4-9 100 | 0.25/0.75/1.36 | 1.35 | 0k | 0.00→0.00 |

Time to complete, slots 2 onward, and node·slots that missed 4 s:

| run | EIP-7870 hosts: p50 / p99 / max (s) | 1 Gbit hosts: p50 / p99 (s) | node·slots missing 4 s / total |
|---|---|---|---|
| `W2048-b16-s1` | 2.06 / 3.48 / 3.91 | 0.71 / 0.82 | 0 / 16,384 |
| `W2048-b16-s2` | 2.04 / 3.46 / 3.86 | 0.70 / 0.79 | 0 / 16,384 |
| `W2048-b16-s3` | 2.01 / 3.44 / 3.93 | 0.69 / 0.78 | 0 / 16,384 |
| `W2048-w1-b16-s1` | 1.72 / 2.49 / 4.03 | 0.71 / 0.80 | 6 / 16,384 |
| `W2048-w1-b16-s2` | 1.73 / 2.46 / 3.08 | 0.71 / 0.79 | 0 / 16,384 |
| `W2048-w1-b16-s3` | 1.70 / 2.44 / 3.61 | 0.70 / 0.78 | 0 / 16,384 |
| `W2048-w1-b16-s4` | 1.71 / 2.46 / 3.74 | 0.71 / 0.79 | 0 / 16,384 |
| `W2048-w1-b16-20slots-s1` | 1.74 / 2.45 / 3.47 | 0.70 / 0.80 | 0 / 36,864 |
| `W2048-w1-b16-fs0-s1` | 1.64 / 2.41 / 3.06 | 0.71 / 0.81 | 0 / 16,384 |
| `W2048-w1-b16-fs0-s2` | 1.64 / 2.43 / 3.90 | 0.73 / 0.82 | 0 / 16,384 |
| `W2048-w1-b16-fs0-s3` | 1.60 / 2.45 / 3.58 | 0.70 / 0.79 | 0 / 16,384 |
| `W2048-w1-b16-fs0-k16-s1` | 1.61 / 2.40 / 3.94 | 0.75 / 0.87 | 0 / 16,384 |
| `W2048-w1-b16-k1-fs0-s1` | 1.82 / 2.50 / 3.19 | 0.72 / 0.81 | 0 / 16,384 |
| `W2048-w1-b16-scale-fs0-s1` | 0.98 / 2.38 / never | 0.89 / 0.99 | 30 / 16,384 |
| `W2048-w1-b1-q20k-s1` | 1.91 / 2.85 / never | 0.69 / 0.77 | 25 / 16,384 |
| `W2048-w1-bund64-s1` | 2.02 / 2.66 / 3.54 | 0.89 / 0.98 | 0 / 16,384 |
| `W2048-w1-b16-v1000-s1` | 2.23 / 2.75 / 3.52 | 2.19 / 2.27 | 0 / 16,384 |
| `W2048-w1-b16-m3000-s1` | 2.58 / 3.42 / never | 0.77 / 0.87 | 20 / 16,384 |
| `W2048-w1-b16-m3000-v1000-s1` | 3.21 / 3.69 / 4.94 | 3.16 / 3.25 | 14 / 16,384 |
| `W2048-w1-b16-fs0-k64-dhi32-s1` | 1.64 / 2.48 / 3.92 | 0.83 / 0.94 | 0 / 16,384 |
| `W2048-w1-b16-scale-fs0-dhi32-s1` | 1.02 / 2.33 / 4.28 | 0.91 / 1.03 | 1 / 16,384 |

Link use, `W2048-w1-b16-s1` (libp2p bytes ÷ cap, slots 2 onward; "busiest bin" is the largest 0.5 s bin of any
node, where bursts above 100 % are TCP and kernel buffering):

| class | nodes | cap down/up (Mbit/s) | up, 4 s window mean / max node | down, 4 s window mean / max node | busiest 0.5 s bin up / down |
|---|---|---|---|---|---|
| 50/15 | 330 | 50/15 | 0 % / 0 % | 36 % / 45 % | 1 % / 116 % |
| 50/25 | 976 | 50/25 | 0 % / 0 % | 36 % / 48 % | 1 % / 120 % |
| 1 Gbit | 742 | 1000/1000 | 10 % / 18 % | 6 % / 15 % | 71 % / 79 % |

In the baseline (`e-base`, 512 hosts), 50/15 hosts' libp2p writes reach 139 % of the uplink cap on average over the
window (220 % on the busiest node), and 50/25 hosts 109 % (198 %): their uplinks are the bottleneck.

## Requirement changes (not allowed changes; reported separately)

### Smaller signatures

| run | change | complete per slot (%) | per class (%) | latency (s) | κ | fwd dropped | after deadline (MiB) |
|---|---|---|---|---|---|---|---|
| `e-sig1229` | 1,229 B signatures, today's mesh | 46 55 56 59 66 | 50x15 10, 50x25 41, cloud 99 | 0.60/2.80/never | 4.26 | 3,222k | 0.97→1.11 |

With leanVM-size signatures (1,229 B) on today's mesh, 46–66 % of nodes complete and 50/15 hosts 10 %. Smaller
signatures alone do not pass.

### Delivery only to subnet subscribers (exploratory; gives up validator anonymity)

Signatures are split over 4 or 16 subnets (a validator's subnet is random). Each EIP-7870 host subscribes to one
random subnet, and 1 Gbit hosts subscribe to all, standing in for aggregators. A host "completes" when it holds
every signature of the subnets it joined. Every subnet has at least 128 subscribers holding its signatures within
4 s: 253–273 per subnet with 4 subnets and 195–211 with 16 (182 of those are the 1 Gbit hosts). Completion below is
for subscribers.

| run | change | complete per slot (%) | per class (%) | latency (s) | κ | fwd dropped | after deadline (MiB) |
|---|---|---|---|---|---|---|---|
| `e-sub4` | 4 subnets | 67 73 79 84 88 | 50x15 34, 50x25 79, cloud 99 | 0.14/1.04/3.94 | 5.35 | 736k | 0.04→0.28 |
| `e-sub4-agg` | 4 subnets + 1 aggregate per subnet to all | 65 83 86 86 92 | 50x15 48, 50x25 82, cloud 99 | 0.14/0.99/2.95 | 5.56 | 692k | 4.61→4.99 |
| `a-sub4-b16` | 4 subnets + b16 | 70 73 79 86 95 | 50x15 39, 50x25 81, cloud 100 | 0.15/0.90/2.85 | 5.13 | 95k | 0.01→0.10 |
| `a-sub16-b16` | 16 subnets + b16 | 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.12/0.23/0.58 | 5.84 | 5k | 0.00→0.00 |
| `a-sub4-w` | 4 subnets + two-tier mesh + b16 | 100 100 100 100 100 | 50x15 100, 50x25 100, cloud 100 | 0.10/0.23/0.69 | 4.51 | 0k | 0.00→0.00 |

- **4 subnets on today's mesh fail:** 67–95 %, with 50/15 hosts at 34–48 %. The 1 Gbit hosts subscribed to every
  subnet still relay a quarter of the load through the slow hosts' meshes.
- **16 subnets with bundles of 16 pass on today's mesh:** 100 % of subscribers at 4 s, p99 0.6 s, flat backlog,
  with no topology change. That is the one way found to pass without changing gossipsub, but it means non-aggregator
  nodes no longer see all signatures. Per Yann, that is a meaningful change, not an allowed relaxation.
- With the two-tier mesh, subnets are not needed (`a-sub4-w` passes too, but so does the single topic).

## Setup and method notes

- **Two-tier mesh in wbsim:** gossipsub parameters per node (`--gs-slow`, `--gs-fast`). A leaf's
  `no_forward=true` turns on manual validation and reports every message as `Ignore`: the application receives it,
  gossipsub records it as seen, and it is never forwarded or gossiped onward. The leaf's own publishes are sent
  normally. Dialing is per node: `--dial-policy slow-to-fast --dial-slow 4 --dial-local` makes each EIP-7870 host dial
  4 1 Gbit hosts in its own region (topped up from other regions when there are too few), and each 1 Gbit host dial
  8 other 1 Gbit hosts. Leaves keep `D = D_lo = D_hi = 1` and `mesh_outbound_min = 0`; 1 Gbit hosts keep D = 8,
  D_lo = 6, and get D_hi = 16 and `forward_queue_duration` = 3 s. Everything else is Ethereum's gossipsub config from
  phase 1, including IDONTWANT above 1,000 B and flood publish off.
- **Bundles** are gossip messages of n × 3,072 B; completion requires every bundle. A bundle's deadline is the slot's
  4 s deadline, so the latency of waiting to bundle is counted.
- **Verification delay** (`--gs verify_us_per_sig=N`) is a serial per-node queue: n × N µs per message before it is
  accepted (forwarded) and counted as received.
- **Pass criterion** (from the review thread): at least 99 % of each class complete, every slot, from slot 2 on, with a
  flat backlog. The winner meets it in every 2,048-host run. The stricter "every node holds 99.9 % of signatures"
  holds in all but a handful of node·slots (the worst held 97 % of its messages, 28 ms late).
- **Not modelled:** packet loss, peer scoring (a leaf that never forwards would be penalised by today's scoring
  unless leaves are exempt), churn or attacks on the core, Reno-without-SACK effects on long leaf links (the review
  noted these make leaf downlinks pessimistic), and the WB-PQ scheme from DESIGN.md (not run, no time left for a fair
  comparison).
- **Not run** (ruled out by the review's bounds, or superseded once the two-tier mesh passed): lazy push only,
  IDONTWANT threshold changes, flood publish, a lower D on a random mesh for all nodes, and publishers spread over
  the whole slot (it would need a deadline relative to each publish, which is excluded).

## Machine and commands

p2psims: AMD EPYC 9454P (48 cores, 96 threads), 503 GiB RAM, Ubuntu 24.04.5, kernel 6.8.0-147.

- **Usage:** all runs at nice 19, pinned to CPUs 48–95 (`taskset`), under a scheduler (`runs/sched.py`) holding at
  most 48 threads and 256 GB. Before each launch it checks other users' load (more than 8 cores or 64 GB → half
  budget). Other users never exceeded 0.1 cores and 1 GB, so it stayed at the full budget.
- **Size:** 512-host runs took 3–30 min with 8 Shadow threads and 3–7 GB RSS (up to about 30 GB with wbsim
  processes). 2,048-host runs took 4–31 min with 40 threads and 70–175 GB in total (peak free memory never below 290 GB). 103 runs in total, from 20:30 to
  02:42 CET (6.2 h of the 10 h budget); 14.4 h of Shadow wall time summed over runs, which ran in parallel.

```sh
# base for every run (runs/run_lever.sh NAME HOSTS SLOTS THREADS [flags]):
python3 repo/sim/gen_config.py --mode flood --hosts $HOSTS --slots $SLOTS --drain 8 --parallelism $THREADS \
  --no-cpu-pinning --validators-csv data/nodes.csv --msgs 2000 --fast-above 8 --fast-share 0.2 \
  --links 50/25 --links-novalidator 50/15 [flags] --out runs/$NAME
(cd runs/$NAME && taskset -c 48-95 nice -n 19 shadow shadow.yaml > shadow.log)
python3 repo/sim/analyze.py --levers runs/NAME ...     # rows of these tables (cached in summary2.json)

# the two-tier winner (W2048-w1-b16-s1; seeds 2-4 add --seed N):
run_lever.sh W2048-w1-b16-s1 2048 10 40 \
  --gossip-dial 8 --dial-policy slow-to-fast --dial-slow 4 --dial-local --batch 16 \
  --gs-fast mesh_n_high=16,forward_queue_ms=3000 \
  --gs-slow mesh_n=1,mesh_n_low=1,mesh_n_high=1,mesh_outbound_min=0,no_forward=true

# variants: --fast-share 0 (fs0), --fast-above 1 / 16 / 64 / 256, --scale-links, --msgs 3000/3500/4000/8000,
#   --batch 4/64, --bundler 16/64 (first-hop bundlers, --bundlers 16 --bundle-hop-ms 150),
#   --gs verify_us_per_sig=100/1000, --gs-fast ...,queue_len=20000 (no bundling), --fixed-send-buffer 262144,
#   --sig-subnets 4/16 [--aggregates 1], --msg-bytes 1229 (e-sig1229)
```

Every run's exact flags are in `runs/<name>/run.json` (`lever`) and `runs/queue-levers.txt`.

Changed files (uncommitted): `sim/wbsim/src/main.rs` (per-node gossipsub config, no-forward leaves, verification
delay, topics, per-message size and deadline), `sim/gen_config.py` (lever flags), `sim/analyze.py` (`--levers`), and
this report.
