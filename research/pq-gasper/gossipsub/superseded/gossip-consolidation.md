# Consolidation, smaller signatures and one-subnet forwarding: what is the least change that carries the PQ load?

Follow-up to [gossip-2000.md](gossip-2000.md) and [gossip-2000-improvements.md](gossip-2000-improvements.md), on the
p2psims machine. Same simulator: Shadow 3.3.0 (patched), real rust-libp2p 0.56 nodes (gossipsub 0.49.5), validator
counts sampled from the mainnet crawl `nodes.csv`, five regions with mainnet-like latencies.

Fixed throughout:

- **Success means every node holds every signature within 4 s of the start of publishing.** No longer deadline is
  used anywhere.
- **Links follow EIP-7870:** 50/25 Mbit/s for hosts with validators and 50/15 for hosts without. Hosts with more than
  8 validators run 1 Gbit ("cloud" class below). Of the rest, 20 % run 1 Gbit as in the earlier phases, except in rows
  marked `fs0`, where only the hosts above 8 validators are fast.
- **Bundles of 16 signatures per message** (`--batch 16`), packed by the publishing host from its own validators, in
  every row. The bytes per slot are unchanged by bundling.
- **Pass:** from slot 2 on, at least 99 % of each link class completes in every slot, backlog stays flat, and no node
  misses in most slots, on every seed that was run. Default scale is 2,048 hosts × 10 slots; rows prefixed `c5-` are
  512-host × 5-slot screens.

## Feasibility map

Least change that passes, per validator count (messages per slot) and signature size. "Today's mesh" is Ethereum's
gossipsub (D = 8, one topic) plus bundling; "one-subnet forwarding" is the hybrid of item 3; "two-tier" means the 1 Gbit
hosts form the mesh and EIP-7870 hosts attach to it (dial 1 Gbit hosts only).

| validators (signatures per slot) | 3,072 B | 1,229 B |
|---|---|---|
| 800k, today (2,000) | **two-tier hybrid** (H3). Passes on 3 seeds at 2,048 hosts, on 2 seeds at 4,096 hosts (99.7–99.8 % per class, 50–55 of 40,960 node·slots missed, worst node·slot 96 % held), and with the > 8-validator core only (fs0). Random-mesh hybrid fails (48–74 % at 512 hosts). | **two-tier hybrid** (H3). Passes on 2 seeds. Random-mesh hybrid with fast dials (Rlazyf2) is marginal: 99.8–99.9 % per class on 2 seeds, but ~140k forwards dropped per slot (timeouts and full queues). |
| 600k (1,500) | **two-tier hybrid** (H3). Passes on 2 seeds. Random-mesh hybrid fails (79–89 % at 512 hosts). | **two-tier hybrid** (H3; H2 also passes). Random-mesh hybrid (Rlazyf2) is marginal: 99.8 % per class, but one 1 Gbit host holds only 68–76 % in every slot. |
| 400k (1,000) | **two-tier hybrid** (H3; H2 also passes). Passes on 2 seeds, at 4,096 hosts, and core-only (fs0). Random-mesh hybrid (Rlazyf2) is marginal: 99.5–99.6 % per class, 51 node·slots missed, 81k drops per slot, tail 0 → 0.04 MiB. | **one-subnet forwarding on a random mesh** (Rlazyf2). 100 % in every slot, 4 misses in 16,384 node·slots, 3k drops per slot, flat tail. The two-tier hybrid also passes. |

**Today's mesh** (D = 8, one topic, with 16-signature bundles) **passes no cell.** That includes the lightest: at
1,000 × 1,229 B (400k validators with leanVM signatures), 2,048 hosts, the 50/15 class completes only 72 % (worst slot
56 %), and 640k forwards are dropped per slot. Consolidation and smaller signatures together cut the bytes by 5×, but
EIP-7870 hosts on a random mesh still relay every message to about 8 peers and saturate their uplinks: the mean upload
of the 50/15 class is 76 % of cap in that cell, and κ is 5.4.

**One-subnet forwarding (Yann's anonymity goal) works at every point on the two-tier mesh.** In H3:

- each EIP-7870 host is a real forwarder (D = 4/2/6) in one home subnet, where its own signatures are published, and a
  non-forwarding leaf (D = 1) in the other 15;
- each EIP-7870 host dials 4 local 1 Gbit hosts;
- 1 Gbit hosts forward in all 16 subnets, with D_hi 16, a 3 s forward queue and a 20,000-message send queue.

H3 passed all six cells at 2,048 hosts × 10 slots on every seed (12 runs), plus the core-only runs and the 4,096-host
runs. At most 28 of 16,384 node·slots missed in any run, a few messages each, mostly on Asian leaves. Backlog stayed
at zero. The home-subnet relaying costs an EIP-7870 host about 0.5–1.1 Mbit/s of upload in the 4 s window, 2.6 Mbit/s
on the busiest node, well under 15 or 25 Mbit/s. Full two-tier (W, leaves never forward) also passes every cell, but
gives no relay cover for a validator's own votes.

**On a plain random mesh, one-subnet forwarding passes only at the lightest cell.** The cell is 400k × 1,229 B, and
the variant needs:

- flood publish;
- more IHAVE gossip;
- 4 extra dials to hosts with the same home subnet;
- 2 extra dials to random 1 Gbit hosts (Rlazyf2).

Without the 1 Gbit dials (Rlazy), a fixed group of hosts with 0–1 1 Gbit peers starves in every slot, at 55–83 %
held. In non-home subnets, their leaf mesh is made of EIP-7870 hosts that never forward there. With the dials, 600k and
800k at 1,229 B reach 99.8–99.9 % per class, but they drop 30k–150k forwards per slot. 400k × 3,072 B is at 99.5 %, and
everything heavier fails. The brief's ~5 Mbit/s upload estimate holds on the random mesh: 5.6–5.9 Mbit/s at
800k × 3 kB. Upload is not what breaks it; download and missing forwarders are.

**Consolidation shrinks the core, but the load shrinks faster.** At 400k, the > 8-validator core is 279 of 2,048 hosts
(14 %, down from 20 % today). On that core alone, with no random 1 Gbit share, H3 passes 400k × 3 kB with zero misses,
and core hosts use 7 % of their uplink. The hardest core-only cell, 800k × 3 kB on 415 core hosts, passes with 28 of
16,384 node·slots missed.

**Per message count:**

- **Today's mesh:** fails at 1,000 × 1,229 B (1.2 MB per slot) and at everything heavier.
- **Random-mesh one-subnet forwarding:** passes at 1,000 × 1,229 B. It is marginal at 1,500–2,000 × 1,229 B
  (1.8–2.5 MB) and at 1,000 × 3,072 B (3.1 MB), and fails at 1,500–2,000 × 3,072 B (4.6–6.1 MB).
- **Two-tier hybrid:** passes at everything up to 2,000 × 3,072 B (6.1 MB).

These figures pair each message count with its consolidated core size, so they are not independent of it.

## How the scenario was scaled

**Messages per slot.** Reference: today's set is taken as 800,000 validators ↔ 2,000 signatures per slot (the
phase-1 load). Scaling linearly gives 600,000 → 1,500 and 400,000 → 1,000. Run names use `v800`, `v600`, `v400` and
carry the message count (`m2000`, `m1500`, `m1000`), so results can be read off per message count for any other
mapping. Note that each message count is only run together with its consolidated validator distribution, so message
count and core size move together.

**Validator distribution.** `gen_config.py --consolidate F` models consolidation by merging each operator's
validators: every `nodes.csv` row with n validators gets ⌈n / m⌉, with one merge factor m for the whole CSV chosen by
bisection so the CSV total hits F × today. Hosts with one validator keep one; hosts without validators keep none. Big
operators lose the most validators in absolute terms, and the 2–8 band shifts down, so fewer hosts pass the "> 8
validators → 1 Gbit" rule. Host counts are then sampled from the consolidated CSV as before.

| set | F | m | CSV validators | CSV rows > 8 | 2,048-host sample: > 8 validators | 1 Gbit incl. 20 % share | 1 validator | no validators |
|---|---|---|---|---|---|---|---|---|
| v800 (today) | 1 | 1 | 727,723 | 19.5 % | 415 (20.3 %) | 742 (36 %) | 292 | 409 |
| v600 | 0.75 | 1.345 | 545,785 | 16.8 % | 361 (17.6 %) | 698 (34 %) | 292 | 409 |
| v400 | 0.5 | 2.020 | 363,861 | 12.7 % | 279 (13.6 %) | 633 (31 %) | 563 | 409 |

The `> 8` core shrinks from 20 % to 14 % of hosts at 400k. That is still above the 4–8 % cores that failed in phase 2,
and the `fs0` rows test the core alone.

## Schemes

All rows use the same base (`runs/run_lever.sh`): mainnet sample, k = 8, 20 % random 1 Gbit share, EIP-7870 links,
publishing starts 4 s into each 12 s slot, 16 subnets where used.

| name | what it is | key flags |
|---|---|---|
| **T** | today's mesh: one topic, D = 8/6/12, random dialling (8 peers) | `--batch 16` |
| **R** | random-mesh one-subnet forwarding: 16 subnets, every host joins all of them. Each EIP-7870 host has a random **home** subnet (its own signatures publish there) where it is a normal forwarder with D = 8/6/12; elsewhere it is a non-forwarding leaf with D = 2/1/3. 1 Gbit hosts forward everywhere with D = 8. Random dialling plus 4 extra dials to same-home hosts. | `--sig-subnets 16 --hybrid --dial-home 4`, `--gs-slow mesh_n=2,…,no_forward=true,home_mesh_n=8,…` |
| Rfp / Rl1 / Rl1fp / Rnh | R + flood publish / leaf D = 1 / both / no dial-home + flood publish | |
| **Rlazy** | R + flood publish + more gossip (`gossip_lazy=12, gossip_factor=0.5`) | |
| **Rlazyf2** | Rlazy + each EIP-7870 host also dials 2 random 1 Gbit hosts (16 dials instead of 14) | `--dial-fast 2` |
| **W** | full two-tier (phase-2 winner): 1 Gbit hosts mesh with D = 8/6/16 and a 3 s forward queue; EIP-7870 hosts dial 4 local 1 Gbit hosts, keep D = 1 and never forward | `--dial-policy slow-to-fast --dial-slow 4 --dial-local`, `--gs-slow mesh_n=1,…,no_forward=true` |
| H | two-tier one-subnet forwarding: W, plus each EIP-7870 host forwards in its home subnet with D = 8 and dials 4 same-home hosts | W + `--sig-subnets 16 --hybrid --dial-home 4`, `home_mesh_n=8,…` |
| H2 | as H, but no dial-home and home D = 4/2/6 | `home_mesh_n=4,home_mesh_n_low=2,home_mesh_n_high=6,home_mesh_outbound_min=1` |
| **H3** | H2 + 20,000-message queues on 1 Gbit hosts | `--gs-fast …,queue_len=20000` |

In every hybrid, a leaf validates messages of non-home subnets as `Ignore` (delivered, not relayed) and messages of its
home subnet as `Accept` (relayed). So a validator's own vote leaves the host the same way as the relay traffic of its
home subnet.

## Tables

Columns: per-slot share of all nodes complete at 4 s; steady-state (slot ≥ 2) completion per class with the worst
slot in brackets; node·slots that missed (slot ≥ 2); latency p50/p99 over all deliveries; κ = bytes received per
useful byte (slot ≥ 2); forwards dropped by rust-libp2p (queue timeout + queue full) per slot; MiB per node still
arriving after the deadline in slot 0 and the last slot (backlog); upload in the 4 s window per class as mean / busiest
node, % of the link cap. The window counters count bytes handed to the socket, so values above 100 % mean the kernel
send buffer is filling (backlog), not that the link beat its cap; phase 1 checked the wire rate with pcap.

### 1. Today's mesh (T)

| run | hosts×slots | complete per slot % | steady (slot ≥ 2) per class % (worst slot) | missed node·slots (slot ≥ 2) | p50/p99 s | κ | dropped fwd/slot | after-deadline MiB/node slot 0→last | up in 4 s window mean/max node, % of cap |
|---|---|---|---|---|---|---|---|---|---|
| `c5-T-v800-s3k-m2000-s1` | 512×5 | 35 35.9 35.7 36.1 36.7 | 50x15 0.4 (0), 50x25 1.4 (0), cloud 99.8 (99) | 980 | 1.04/never | 2.85 | 371,444 | 3.24→4.12 | 50x15 115/206, 50x25 102/179, cloud 4/9 |
| `c5-T-v800-s1k-m2000-s1` | 512×5 | 58.8 70.5 71.7 75.6 76.2 | 50x15 29.5 (23), 50x25 71.3 (68), cloud 100.0 (100) | 392 | 0.54/never | 4.01 | 311,464 | 0.28→0.48 | 50x15 91/118, 50x25 72/112, cloud 2/5 |
| `c5-T-v600-s3k-m1500-s1` | 512×5 | 38.5 44.9 43.9 44.9 46.1 | 50x15 6.1 (3), 50x25 21.9 (21), cloud 100.0 (100) | 845 | 0.84/never | 3.32 | 295,289 | 1.57→2.57 | 50x15 108/184, 50x25 95/145, cloud 4/8 |
| `c5-T-v600-s1k-m1500-s1` | 512×5 | 74.6 79.3 81.4 86.1 90.8 | 50x15 55.8 (48), 50x25 86.2 (79), cloud 100.0 (100) | 213 | 0.41/never | 4.63 | 209,225 | 0.08→0.14 | 50x15 81/112, 50x25 62/91, cloud 2/4 |
| `c5-T-v400-s3k-m1000-s1` | 512×5 | 54.3 65.8 67 67.8 73.6 | 50x15 26.9 (24), 50x25 64.9 (61), cloud 100.0 (100) | 469 | 0.71/never | 3.90 | 196,924 | 0.61→1.19 | 50x15 106/161, 50x25 85/136, cloud 3/6 |
| `c5-T-v400-s1k-m1000-s1` | 512×5 | 90.8 88.9 90 94.3 96.5 | 50x15 70.5 (59), 50x25 96.6 (93), cloud 100.0 (100) | 98 | 0.32/2.15 | 5.40 | 109,493 | 0.01→0.04 | 50x15 73/107, 50x25 50/81, cloud 2/3 |
| `C-T-v400-s1k-m1000-s1` | 2048×10 | 87.9 85.6 91.4 93.4 94.3 92.7 94.5 96 96.2 97.3 | 50x15 71.9 (56), 50x25 98.2 (97), cloud 100.0 (100) | 905 | 0.27/2.12 | 5.40 | 643,219 | 0.03→0.06 | 50x15 76/103, 50x25 51/88, cloud 1/3 |

Today's mesh fails everywhere. Consolidation and smaller signatures help in proportion to the bytes (the EIP-7870
classes go from 0–1 % at 800k × 3 kB to 72 % / 98 % at 400k × 1.2 kB), but the EIP-7870 hosts still forward ~5 copies of every
message they get through (κ 2.9–5.4, lower at 3 kB because more forwards are dropped) and their uplinks saturate: the
4 s-window upload of the 50/15 class is 73–115 % of cap on average and up to 206 % on the busiest node, i.e. megabytes queued in the kernel send buffer. Backlog grows across slots
at 3 kB (after-deadline MiB per node 0.6 → 1.2 at v400, 3.2 → 4.1 at v800). The 2,048-host row at 400k × 1.2 kB confirms
the 512-host screen.

### 2. One-subnet forwarding on a random mesh (R family)

| run | hosts×slots | complete per slot % | steady (slot ≥ 2) per class % (worst slot) | missed node·slots (slot ≥ 2) | p50/p99 s | κ | dropped fwd/slot | after-deadline MiB/node slot 0→last | up in 4 s window mean/max node, % of cap |
|---|---|---|---|---|---|---|---|---|---|
| `c5-R-v800-s3k-m2000-s1` | 512×5 | 53.1 51.6 47.9 54.5 74.4 | 50x15 38.8 (22), 50x25 35.4 (18), cloud 100.0 (100) | 631 | 0.25/never | 2.41 | 133,444 | 0.04→0.12 | 50x15 37/54, 50x25 24/42, cloud 7/12 |
| `c5-R-v800-s1k-m2000-s1` | 512×5 | 99.2 99.4 99.2 99.2 99.4 | 50x15 100.0 (100), 50x25 98.5 (98), cloud 100.0 (100) | 11 | 0.17/1.09 | 2.81 | 10,154 | 0.00→0.03 | 50x15 16/26, 50x25 10/17, cloud 3/5 |
| `c5-R-v600-s3k-m1500-s1` | 512×5 | 3.3 86.9 2 86.3 94.3 | 50x15 54.5 (1), 50x25 59.0 (3), cloud 66.9 (1) | 601 | 0.22/2.10 | 2.45 | 49,611 | 0.01→0.10 | 50x15 28/44, 50x25 18/28, cloud 6/9 |
| `c5-R-v600-s1k-m1500-s1` | 512×5 | 98.8 99.6 100 99.6 99.4 | 50x15 99.6 (99), 50x25 99.5 (99), cloud 100.0 (100) | 5 | 0.15/1.04 | 2.57 | 1,483 | 0.00→0.00 | 50x15 12/18, 50x25 7/12, cloud 3/4 |
| `c5-R-v400-s3k-m1000-s1` | 512×5 | 98.6 98.8 98.4 97.9 97.9 | 50x15 97.9 (97), 50x25 97.4 (97), cloud 99.3 (99) | 30 | 0.19/1.52 | 2.41 | 9,573 | 0.00→0.04 | 50x15 19/28, 50x25 12/20, cloud 4/7 |
| `c5-R-v400-s1k-m1000-s1` | 512×5 | 2.9 2.9 98.2 98.8 98.4 | 50x15 97.9 (97), 50x25 98.5 (98), cloud 98.9 (99) | 23 | 0.14/1.15 | 2.33 | 166 | 0.00→0.00 | 50x15 8/12, 50x25 5/8, cloud 2/3 |
| `c5-Rfp-v800-s1k-m2000-s1` | 512×5 | 99.4 99.6 99.4 99.2 99 | 50x15 100.0 (100), 50x25 98.4 (98), cloud 100.0 (100) | 12 | 0.16/1.07 | 2.83 | 11,150 | 0.00→0.03 | 50x15 16/26, 50x25 10/17, cloud 3/5 |
| `c5-Rfp-v600-s3k-m1500-s1` | 512×5 | 85 87.3 81.1 82 93.8 | 50x15 79.2 (73), 50x25 78.6 (71), cloud 99.8 (99) | 221 | 0.20/2.11 | 2.46 | 56,249 | 0.01→0.09 | 50x15 28/43, 50x25 18/28, cloud 6/9 |
| `c5-Rfp-v400-s1k-m1000-s1` | 512×5 | 98.6 99.2 99.4 99.4 99 | 50x15 99.6 (99), 50x25 99.2 (99), cloud 99.3 (99) | 11 | 0.13/0.95 | 2.34 | 275 | 0.00→0.00 | 50x15 8/12, 50x25 5/8, cloud 2/3 |
| `c5-Rl1-v800-s1k-m2000-s1` | 512×5 | 99.4 99.6 99.6 98.8 99.4 | 50x15 100.0 (100), 50x25 98.5 (98), cloud 100.0 (100) | 11 | 0.16/1.16 | 2.91 | 5,925 | 0.00→0.01 | 50x15 17/25, 50x25 10/16, cloud 4/5 |
| `c5-Rl1-v600-s3k-m1500-s1` | 512×5 | 90.6 92.6 90.6 89.8 95.9 | 50x15 84.8 (79), 50x25 89.3 (87), cloud 100.0 (100) | 121 | 0.23/2.42 | 2.72 | 13,695 | 0.00→0.05 | 50x15 31/44, 50x25 19/28, cloud 7/10 |
| `c5-Rl1-v400-s1k-m1000-s1` | 512×5 | 98.6 98.2 98.4 97.7 98.2 | 50x15 97.9 (97), 50x25 97.2 (96), cloud 100.0 (100) | 29 | 0.15/1.18 | 2.46 | 672 | 0.00→0.00 | 50x15 8/12, 50x25 5/8, cloud 2/3 |
| `c5-Rl1fp-v800-s1k-m2000-s1` | 512×5 | 99.2 99.6 99.4 99.6 99.2 | 50x15 100.0 (100), 50x25 98.8 (98), cloud 100.0 (100) | 9 | 0.15/1.14 | 2.93 | 6,219 | 0.00→0.00 | 50x15 17/26, 50x25 10/16, cloud 4/6 |
| `c5-Rl1fp-v600-s3k-m1500-s1` | 512×5 | 87.7 90.8 86.7 87.7 94.5 | 50x15 80.1 (77), 50x25 85.9 (81), cloud 100.0 (100) | 159 | 0.22/2.44 | 2.73 | 15,137 | 0.00→0.04 | 50x15 31/43, 50x25 19/28, cloud 7/10 |
| `c5-Rl1fp-v400-s1k-m1000-s1` | 512×5 | 98.6 99 98.2 98 97.9 | 50x15 99.1 (99), 50x25 96.7 (96), cloud 100.0 (100) | 30 | 0.14/1.17 | 2.47 | 658 | 0.00→0.00 | 50x15 8/13, 50x25 5/9, cloud 2/3 |
| `c5-Rnh-v800-s1k-m2000-s1` | 512×5 | 99.6 99.8 99 99.4 99.4 | 50x15 98.8 (98), 50x25 98.9 (98), cloud 100.0 (100) | 11 | 0.15/0.98 | 2.80 | 9,565 | 0.00→0.03 | 50x15 15/23, 50x25 9/13, cloud 3/5 |
| `c5-Rnh-v400-s1k-m1000-s1` | 512×5 | 98.6 99 99.2 98.8 98.6 | 50x15 98.3 (97), 50x25 98.5 (98), cloud 100.0 (100) | 17 | 0.14/0.92 | 2.29 | 235 | 0.00→0.00 | 50x15 7/10, 50x25 4/7, cloud 2/3 |
| `c5-Rlazy-v800-s1k-m2000-s1` | 512×5 | 100 100 99.8 99.6 99.6 | 50x15 100.0 (100), 50x25 99.3 (99), cloud 100.0 (100) | 5 | 0.16/0.99 | 2.89 | 12,419 | 0.00→0.02 | 50x15 16/26, 50x25 10/17, cloud 4/6 |
| `c5-Rlazy-v400-s1k-m1000-s1` | 512×5 | 99.2 99.6 99.6 99.6 99.6 | 50x15 100.0 (100), 50x25 99.6 (100), cloud 99.3 (99) | 6 | 0.13/0.82 | 2.40 | 239 | 0.00→0.00 | 50x15 8/12, 50x25 5/8, cloud 2/3 |
| `c5-Rlazy-v400-s3k-m1000-s1` | 512×5 | 98.8 98.4 98.4 99 99 | 50x15 100.0 (100), 50x25 98.2 (98), cloud 99.3 (99) | 18 | 0.17/1.26 | 2.48 | 10,548 | 0.00→0.03 | 50x15 19/28, 50x25 12/20, cloud 4/7 |
| `C-Rlazy-v800-s1k-m2000-s1` | 2048×10 | 99.6 99.6 99.8 99.7 99.6 99.6 99.5 99.5 99.8 99.9 | 50x15 99.3 (99), 50x25 99.5 (99), cloud 100.0 (100) | 55 | 0.17/1.07 | 3.04 | 180,528 | 0.00→0.04 | 50x15 18/29, 50x25 11/18, cloud 4/6 |
| `C-Rlazy-v600-s1k-m1500-s1` | 2048×10 | 99.5 99.8 99.7 99.8 99.7 99.7 99.6 99.6 99.8 99.7 | 50x15 99.2 (99), 50x25 99.7 (100), cloud 99.9 (100) | 51 | 0.17/0.88 | 2.84 | 35,663 | 0.00→0.01 | 50x15 14/22, 50x25 8/14, cloud 3/4 |
| `C-Rlazy-v400-s1k-m1000-s1` | 2048×10 | 99.5 99.6 99.5 99.5 99.6 99.5 99.5 99.6 99.5 99.5 | 50x15 99.7 (99), 50x25 99.2 (99), cloud 100.0 (100) | 79 | 0.16/0.82 | 2.54 | 3,906 | 0.00→0.00 | 50x15 9/15, 50x25 5/9, cloud 2/3 |
| `C-Rlazyf2-v800-s1k-m2000-s1` | 2048×10 | 99.9 99.8 99.9 99.9 100 100 99.4 99.9 100 100 | 50x15 99.8 (99), 50x25 99.8 (99), cloud 100.0 (100) | 22 | 0.17/0.99 | 3.03 | 148,587 | 0.00→0.04 | 50x15 18/28, 50x25 11/18, cloud 4/5 |
| `C-Rlazyf2-v800-s1k-m2000-s2` | 2048×10 | 99.5 100 100 100 100 99.8 99.5 100 100 100 | 50x15 99.9 (99), 50x25 99.8 (99), cloud 100.0 (100) | 18 | 0.18/1.00 | 2.98 | 140,724 | 0.00→0.04 | 50x15 18/29, 50x25 11/18, cloud 4/5 |
| `C-Rlazyf2-v600-s1k-m1500-s1` | 2048×10 | 99.8 100 100 99.9 100 100 99.8 99.8 100 100 | 50x15 99.8 (99), 50x25 100.0 (100), cloud 99.8 (100) | 16 | 0.17/0.83 | 2.83 | 30,112 | 0.00→0.01 | 50x15 14/22, 50x25 8/13, cloud 3/4 |
| `C-Rlazyf2-v400-s1k-m1000-s1` | 2048×10 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100.0 (100), 50x25 100.0 (100), cloud 99.9 (100) | 4 | 0.16/0.73 | 2.50 | 3,009 | 0.00→0.00 | 50x15 9/15, 50x25 5/9, cloud 2/3 |
| `C-Rlazyf2-v400-s3k-m1000-s1` | 2048×10 | 99.5 99.7 99.5 100 100 99.6 99.6 99.6 99.7 99.6 | 50x15 99.5 (99), 50x25 99.6 (99), cloud 99.9 (100) | 51 | 0.22/1.16 | 2.54 | 81,152 | 0.00→0.04 | 50x15 20/33, 50x25 13/20, cloud 4/6 |

The R family keeps today's random dialling and only adds subnets and home forwarding. Findings:

- At 3,072 B it fails at every validator count (R 48–74 % at 800k, 2–94 % at 600k with two collapsed slots; Rfp/Rl1/Rl1fp 79–89 % at 600k;
  R and Rlazy 97–100 % per class at 400k, R's worst slot 97 %), with forward drops of 10k–133k per slot and a growing tail.
- At 1,229 B it is close: Rfp, Rl1fp, Rnh and Rlazy reach 98–100 % per class at 512 hosts. Flood publish is needed (plain R
  at 400k loses slots 0–1 entirely: publishes by 1 Gbit hosts that are not in the home mesh never reach it). Rlazy (more
  IHAVE gossip) was the best variant and was run at 2,048 hosts for all three validator counts.
- At 2,048 hosts Rlazy reaches 99.2–99.7 % per class in every slot at 400k, 600k and 800k, but a fixed set of hosts
  starves every slot (worst node 55–83 % held), forwards are dropped every slot (20k–180k), and at 800k the tail grows
  slowly (0.00 → 0.04 MiB). The starving hosts (checked at 400k) are the ones that dialled 0–1 1 Gbit hosts, which leaves them with no
  forwarding mesh peer in most non-home subnets. **Rlazyf2** adds 2 dials to random 1 Gbit hosts per
  EIP-7870 host, so every one of them has at least 2 fast peers. It passes 400k × 1.2 kB (4 misses, both on 1 Gbit
  hosts, flat tail). At 800k × 1.2 kB (2 seeds) and 600k × 1.2 kB it reaches 99.8–100 % per class, but it still drops
  30k–150k forwards per slot. At 600k, one 1 Gbit host in Europe held only 68–76 % in every slot; I did not find out
  why. At 400k × 3 kB it reaches 99.5 %, with 51 misses and a tail rising 0 → 0.04 MiB. So fast dials fix the
  starving hosts, but the random-mesh hybrid stays near its limit above the lightest cell.

### 3. One-subnet forwarding on the two-tier mesh (H, H2, H3)

| run | hosts×slots | complete per slot % | steady (slot ≥ 2) per class % (worst slot) | missed node·slots (slot ≥ 2) | p50/p99 s | κ | dropped fwd/slot | after-deadline MiB/node slot 0→last | up in 4 s window mean/max node, % of cap |
|---|---|---|---|---|---|---|---|---|---|
| `C-H-v400-s3k-m1000-s1` | 2048×10 | 96.3 96.6 97.5 96.3 96.9 96.5 96.5 97.1 96.8 97.7 | 50x15 94.0 (93), 50x25 96.0 (95), cloud 100.0 (100) | 506 | 0.15/1.30 | 2.74 | 14,293 | 0.00→0.00 | 50x15 16/30, 50x25 9/19, cloud 5/8 |
| `C-H-v400-s1k-m1000-s1` | 2048×10 | 96.3 97 98.1 96.7 96.9 96.5 96.1 96.2 97.1 97.9 | 50x15 94.7 (93), 50x25 95.8 (95), cloud 100.0 (100) | 502 | 0.12/1.21 | 2.84 | 7,749 | 0.00→0.00 | 50x15 7/13, 50x25 4/8, cloud 2/3 |
| `C-H2-v800-s3k-m2000-s1` | 2048×10 | 99.1 94.9 95.4 93.5 94.7 94.3 95.5 95.6 95.5 94.7 | 50x15 91.1 (88), 50x25 92.3 (90), cloud 100.0 (100) | 839 | 0.18/1.40 | 2.97 | 620,007 | 0.00→0.00 | 50x15 7/17, 50x25 5/10, cloud 10/16 |
| `C-H2-v600-s3k-m1500-s1` | 2048×10 | 100 98.9 97.6 98.7 98.3 97.8 98.8 99.1 98.5 98.6 | 50x15 98.1 (97), 50x25 97.5 (96), cloud 100.0 (100) | 258 | 0.16/1.05 | 2.76 | 147,132 | 0.00→0.00 | 50x15 5/13, 50x25 3/8, cloud 7/12 |
| `C-H2-v600-s1k-m1500-s1` | 2048×10 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100.0 (100), 50x25 100.0 (100), cloud 100.0 (100) | 0 | 0.12/0.34 | 2.74 | 55,937 | 0.00→0.00 | 50x15 2/5, 50x25 1/3, cloud 3/5 |
| `C-H2-v400-s3k-m1000-s1` | 2048×10 | 100 100 99.9 100 100 100 100 100 100 100 | 50x15 100.0 (100), 50x25 100.0 (100), cloud 100.0 (100) | 4 | 0.14/0.69 | 2.40 | 7,499 | 0.00→0.00 | 50x15 3/8, 50x25 2/5, cloud 5/9 |
| `C-H2-v400-s1k-m1000-s1` | 2048×10 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100.0 (100), 50x25 100.0 (100), cloud 100.0 (100) | 0 | 0.12/0.30 | 2.49 | 3,705 | 0.00→0.00 | 50x15 1/3, 50x25 1/2, cloud 2/4 |
| `C-H3-v800-s3k-m2000-s1` | 2048×10 | 100 99.8 100 100 99.9 100 100 100 100 99.9 | 50x15 99.9 (100), 50x25 99.9 (100), cloud 100.0 (100) | 7 | 0.18/1.37 | 2.99 | 377 | 0.00→0.00 | 50x15 7/17, 50x25 5/10, cloud 10/17 |
| `C-H3-v800-s3k-m2000-s2` | 2048×10 | 100 99.9 99.9 100 100 100 99.9 99.9 100 100 | 50x15 99.8 (100), 50x25 99.9 (100), cloud 100.0 (100) | 10 | 0.18/1.39 | 2.93 | 272 | 0.00→0.00 | 50x15 8/16, 50x25 4/10, cloud 10/20 |
| `C-H3-v800-s3k-m2000-s3` | 2048×10 | 100 99.9 99.9 99.9 99.8 99.8 100 100 99.9 100 | 50x15 99.7 (99), 50x25 99.9 (100), cloud 100.0 (100) | 19 | 0.17/1.36 | 2.93 | 403 | 0.00→0.00 | 50x15 7/16, 50x25 5/10, cloud 10/16 |
| `C-H3-v800-s1k-m2000-s1` | 2048×10 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100.0 (100), 50x25 100.0 (100), cloud 100.0 (100) | 0 | 0.12/0.61 | 2.94 | 0 | 0.00→0.00 | 50x15 3/7, 50x25 2/4, cloud 4/7 |
| `C-H3-v800-s1k-m2000-s2` | 2048×10 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100.0 (100), 50x25 100.0 (100), cloud 100.0 (100) | 0 | 0.13/0.62 | 2.87 | 0 | 0.00→0.00 | 50x15 3/7, 50x25 2/4, cloud 4/8 |
| `C-H3-v600-s3k-m1500-s1` | 2048×10 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100.0 (100), 50x25 100.0 (100), cloud 100.0 (100) | 1 | 0.16/1.05 | 2.77 | 32 | 0.00→0.00 | 50x15 5/13, 50x25 3/8, cloud 7/13 |
| `C-H3-v600-s3k-m1500-s2` | 2048×10 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100.0 (100), 50x25 100.0 (100), cloud 100.0 (100) | 0 | 0.16/1.05 | 2.68 | 52 | 0.00→0.00 | 50x15 5/13, 50x25 3/7, cloud 7/13 |
| `C-H3-v600-s1k-m1500-s2` | 2048×10 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100.0 (100), 50x25 100.0 (100), cloud 100.0 (100) | 0 | 0.11/0.35 | 2.64 | 0 | 0.00→0.00 | 50x15 2/5, 50x25 1/3, cloud 3/5 |
| `C-H3-v400-s3k-m1000-s2` | 2048×10 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100.0 (100), 50x25 100.0 (100), cloud 100.0 (100) | 0 | 0.14/0.67 | 2.33 | 0 | 0.00→0.00 | 50x15 3/8, 50x25 2/5, cloud 5/8 |
| `C-H3-v400-s1k-m1000-s2` | 2048×10 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100.0 (100), 50x25 100.0 (100), cloud 100.0 (100) | 0 | 0.11/0.29 | 2.42 | 0 | 0.00→0.00 | 50x15 1/3, 50x25 1/2, cloud 2/3 |
| `C-H3-v800-s3k-m2000-fs0-s1` | 2048×10 | 99.9 99.7 99.7 99.9 99.8 99.9 99.9 99.8 99.9 99.9 | 50x15 99.8 (100), 50x25 99.8 (99), cloud 100.0 (100) | 28 | 0.24/1.49 | 1.94 | 229 | 0.00→0.00 | 50x15 6/16, 50x25 4/10, cloud 11/20 |
| `C-H3-v400-s3k-m1000-fs0-s1` | 2048×10 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100.0 (100), 50x25 100.0 (100), cloud 100.0 (100) | 0 | 0.14/0.72 | 1.51 | 1 | 0.00→0.00 | 50x15 3/6, 50x25 2/5, cloud 7/10 |
| `X4096-H3-v800-s3k-m2000-s1` | 4096×10 | 100 99.8 99.7 99.9 99.8 99.9 99.9 99.9 99.9 100 | 50x15 99.8 (99), 50x25 99.8 (100), cloud 100.0 (100) | 50 | 0.20/1.44 | 2.96 | 2,008 | 0.00→0.00 | 50x15 8/17, 50x25 5/10, cloud 10/17 |
| `X4096-H3-v800-s3k-m2000-s2` | 4096×10 | 100 99.8 99.8 99.9 99.8 99.8 99.9 99.8 99.9 99.8 | 50x15 99.8 (100), 50x25 99.7 (100), cloud 100.0 (100) | 55 | 0.20/1.45 | 2.99 | 2,420 | 0.00→0.00 | 50x15 8/17, 50x25 5/10, cloud 10/18 |
| `X4096-H3-v400-s3k-m1000-s1` | 4096×10 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100.0 (100), 50x25 100.0 (100), cloud 100.0 (100) | 0 | 0.14/0.74 | 2.38 | 22 | 0.00→0.00 | 50x15 3/9, 50x25 2/5, cloud 5/9 |

- **H** (home D = 8 plus 4 dials to same-home hosts) fails at 400k (94–96 %): most likely because the dial-home connections pull leaves
  into meshes with other EIP-7870 hosts, which reintroduces the slow-to-slow forwarding paths of the random mesh, and
  1 Gbit hosts' queues overflow (13.7k queue-full drops per slot).
- **H2** (no dial-home, home D = 4/2/6) passes at 400k and at 600k × 1.2 kB, but at 600k × 3 kB (97.5 %) and 800k × 3 kB
  (91 %) the 1 Gbit hosts' 5,000-message send queues overflow (570k queue-full drops per slot at 800k).
- **H3** = H2 with 20,000-message queues on 1 Gbit hosts. Queue-full drops go to zero and every cell passes on every seed.
  Remaining misses (0–28 of 16,384 node·slots per run) are a few messages each on EIP-7870 leaves, mostly in Asia, the
  region farthest from the European and North American publishers. κ is 2.3–3.0; EIP-7870 hosts upload 0.5–1.1 Mbit/s
  on average in the 4 s window (2–7 % of cap) and download 6–19 Mbit/s (12–38 % of 50 Mbit/s). 1 Gbit hosts upload
  39–114 Mbit/s on average, 200 Mbit/s on the busiest node.
- `fs0` rows drop the random 20 % 1 Gbit share: only hosts with more than 8 validators are fast (415 hosts at 800k, 279 at
  400k). Both pass; κ falls (1.5–1.9) because leaves have fewer, busier core peers.
- **4,096 hosts × 10 slots** (1,474 1 Gbit hosts at 800k, 1,249 at 400k): H3 passes. At 800k × 3 kB, 2 seeds reach
  99.7–99.8 % per class, with every class at least 99 % in every slot. Per seed, 50–55 of 40,960 node·slots miss, at
  least 96 % held in the worst node·slot, and the backlog stays at zero. At 400k × 3 kB there are no misses. So the miss
  rate per node is the same as at 2,048 hosts (0.1–0.2 %).

### 4. Full two-tier (W) reference

| run | hosts×slots | complete per slot % | steady (slot ≥ 2) per class % (worst slot) | missed node·slots (slot ≥ 2) | p50/p99 s | κ | dropped fwd/slot | after-deadline MiB/node slot 0→last | up in 4 s window mean/max node, % of cap |
|---|---|---|---|---|---|---|---|---|---|
| `C-W-v800-s3k-m2000-s1` | 2048×10 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100.0 (100), 50x25 100.0 (100), cloud 100.0 (100) | 0 | 0.22/1.40 | 2.84 | 705 | 0.00→0.00 | 50x15 0/0, 50x25 0/0, cloud 10/18 |
| `C-W-v800-s1k-m2000-s1` | 2048×10 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100.0 (100), 50x25 100.0 (100), cloud 100.0 (100) | 0 | 0.13/0.64 | 2.64 | 137 | 0.00→0.00 | 50x15 0/0, 50x25 0/0, cloud 4/7 |
| `C-W-v600-s3k-m1500-s1` | 2048×10 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100.0 (100), 50x25 100.0 (100), cloud 100.0 (100) | 0 | 0.18/1.06 | 2.64 | 0 | 0.00→0.00 | 50x15 0/0, 50x25 0/0, cloud 7/14 |
| `C-W-v600-s1k-m1500-s1` | 2048×10 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100.0 (100), 50x25 100.0 (100), cloud 100.0 (100) | 0 | 0.13/0.54 | 2.50 | 0 | 0.00→0.00 | 50x15 0/0, 50x25 0/0, cloud 3/5 |
| `C-W-v400-s3k-m1000-s1` | 2048×10 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100.0 (100), 50x25 100.0 (100), cloud 100.0 (100) | 0 | 0.15/0.74 | 2.26 | 0 | 0.00→0.00 | 50x15 0/0, 50x25 0/0, cloud 5/9 |
| `C-W-v400-s1k-m1000-s1` | 2048×10 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100.0 (100), 50x25 100.0 (100), cloud 100.0 (100) | 0 | 0.12/0.45 | 2.24 | 0 | 0.00→0.00 | 50x15 0/0, 50x25 0/0, cloud 2/4 |
| `W2048-w1-b16-fs0-s1` | 2048×10 | 100 100 100 100 100 100 100 100 100 100 | 50x15 100.0 (100), 50x25 100.0 (100), cloud 100.0 (100) | 0 | 0.30/1.41 | 1.82 | 4 | 0.00→0.00 | 50x15 0/0, 50x25 0/0, cloud 11/21 |

### 5. Upload against the back-of-envelope

The brief's estimate for N = 16 at 2,000 × 3 kB: one subnet is 125 signatures ≈ 384 kB; forwarding ~7 copies is ~2.6 MB in
4 s, ≈ 5 Mbit/s.

| run | home mesh D | 50/15 class upload in 4 s window, mean / busiest node (Mbit/s) | % of 15 Mbit/s cap | 50/25 class, mean / busiest (Mbit/s) |
|---|---|---|---|---|
| `c5-R-v800-s3k-m2000-s1` (random mesh) | 8 | 5.6 / 8.0 | 37 % / 54 % | 5.9 / 10.5 |
| `c5-R-v600-s3k-m1500-s1` | 8 | 4.2 / 6.7 | 28 % / 44 % | 4.6 / 7.0 |
| `c5-R-v400-s3k-m1000-s1` | 8 | 2.8 / 4.2 | 19 % / 28 % | 3.0 / 5.1 |
| `C-H3-v800-s3k-m2000-s1` (two-tier) | 4 | 1.1 / 2.6 | 7 % / 17 % | 1.1 / 2.6 |
| `C-H3-v600-s3k-m1500-s1` | 4 | 0.8 / 1.9 | 5 % / 13 % | 0.8 / 1.9 |
| `C-H3-v400-s3k-m1000-s2` | 4 | 0.5 / 1.3 | 3 % / 8 % | 0.5 / 1.3 |
| `C-H3-v800-s1k-m2000-s1` | 4 | 0.45 / 1.1 | 3 % / 7 % | 0.45 / 1.0 |

On the random mesh the estimate is right (5.6–5.9 Mbit/s at 800k × 3 kB, i.e. 2.8 MB per host in the window), and it fits
under both 15 and 25 Mbit/s caps; the random mesh fails on download and on the leaves' missing forwarders, not on home-subnet upload. On
the two-tier mesh the home-subnet relay costs only ~1 Mbit/s: with D = 4 and the 1 Gbit core delivering most first copies,
the IDONTWANT/duplicate check suppresses most of a leaf's home forwards. Every host stays well under its upload cap in
every passing run (busiest EIP-7870 node at most 17 % of 15 Mbit/s).

## Commands

Each row is one call of `runs/run_lever.sh NAME HOSTS SLOTS THREADS FLAGS…`, which runs

```sh
python3 repo/sim/gen_config.py --mode flood --hosts $HOSTS --slots $SLOTS --drain 8 --parallelism $THREADS \
  --no-cpu-pinning --validators-csv data/f9ba162f-nodes.csv --msgs 2000 --fast-above 8 --fast-share 0.2 \
  --links 50/25 --links-novalidator 50/15 FLAGS… --out runs/NAME
taskset -c 48-95 nice -n 19 shadow runs/NAME/shadow.yaml
nice python3 repo/sim/analyze.py --levers runs/NAME        # writes runs/NAME/summary2.json
```

The full flag set of every run is in `runs/queue-levers.txt` (scheduler `runs/sched.py`). For example, the H3 row at
800k × 3 kB, seed 2:

```sh
bash runs/run_lever.sh C-H3-v800-s3k-m2000-s2 2048 10 24 --gossip-dial 8 --dial-policy slow-to-fast --dial-slow 4 \
  --dial-local --batch 16 --sig-subnets 16 --hybrid \
  --gs-fast mesh_n_high=16,forward_queue_ms=3000,queue_len=20000 \
  --gs-slow mesh_n=1,mesh_n_low=1,mesh_n_high=1,mesh_outbound_min=0,no_forward=true,home_mesh_n=4,home_mesh_n_low=2,home_mesh_n_high=6,home_mesh_outbound_min=1 \
  --msgs 2000 --seed 2
```

`--consolidate 0.75 --msgs 1500` gives v600, `--consolidate 0.5 --msgs 1000` gives v400, and `--msg-bytes 1229` gives
the leanVM signature size.

## Machine and usage

- Machine: AMD EPYC 9454P (48 cores / 96 threads), 503 GiB RAM, Linux 6.8, shared with other users.
- Budget: CPUs 48–95 only (`taskset -c 48-95`), `nice -n 19`, at most 48 Shadow worker threads and 256 GB for this
  work, halved (24 threads, 128 GB) whenever other users used more than 8 cores or 64 GB. `runs/sched.py` checks
  `top`/`ps` before every launch and keeps queue order.
- Started 06:39:51 CET (`runs/consol-start.txt`), last run finished 15:08:47, about 8.5 h in; write-up after that.
- Other users: idle most of the time. At 11:08 (24.5 cores) and 11:31 (51 cores, 268 GB, another user's Shadow run)
  the scheduler launched at the half budget; the load cleared by 11:35. Two runs of mine already in flight were left to
  finish rather than killed.
- Per run: 2,048 hosts × 10 slots used 24 threads, 60–110 GB and 8–33 min of wall clock; 512 × 5 used 8 threads,
  ~25 GB and 2–5 min; 4,096 × 10 used 46 threads and about 165–220 GB in total (Shadow plus wbsim processes), 19–38 min each.
- 65 runs for this phase (`runs/C-*`, `runs/c5-*`, `runs/X4096-*`); 24 GB of run data on disk under `runs/`
  (shim logs deleted after each run).

## Changed files (uncommitted)

- `sim/wbsim/src/main.rs`: `NodeCfg.home`; gossipsub `home_mesh_n`, `home_mesh_n_low`, `home_mesh_n_high` and
  `home_mesh_outbound_min`, applied as per-topic mesh parameters on the home topic; a `no_forward` node reports
  `Accept` for its home topic and `Ignore` elsewhere.
- `sim/gen_config.py`: `--dial-fast N` (each EIP-7870 host also dials N random 1 Gbit hosts), `--hybrid` (with `--sig-subnets`, every host joins all subnets, each EIP-7870 host gets a random
  home subnet and publishes its own signatures there), `--dial-home N`, `--consolidate F`.
- `sim/analyze.py`: `--levers` class entries also carry the 4 s-window upload and download (mean and busiest node),
  steady-state completion and per-slot completion.
- `results/gossip-consolidation.md` (this file).
