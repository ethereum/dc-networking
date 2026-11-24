# One subnet per home staker: unmodified mainnet gossipsub with emergent peering

Follow-up to [gossip-consolidation.md](gossip-consolidation.md). It replaces that report's H3 "two-tier hybrid", whose
wiring was assumed rather than tested. Simulator, regions, latencies, link model and validator sample are unchanged:
Shadow 3.3.0 (patched), rust-libp2p 0.56 / gossipsub 0.49.5, validator counts from `nodes.csv`.

## Verdict

**It works with no protocol or parameter change.** Every cell passes at 2,048 hosts × 10 slots:

- 800k, 600k and 400k validators;
- 3,072 B and 1,229 B signatures;
- unbundled and with 16-signature bundles;
- 3 seeds at 800k × 3 kB unbundled, and 2 seeds bundled;
- with only the hosts above 8 validators on 1 Gbit (`fs0`).

From slot 2 on, at most 2 of 16,384 node·slots missed in any run, and every class was at least 99.7 % complete in
every slot (99.3–99.4 % in slots 0–1). The backlog stayed at 0.00–0.01 MiB per node, and EIP-7870 uplinks peaked at 63 % of cap on the busiest
node. Because nothing failed, no tuning was needed, and "the smallest single change that fixes it" does not apply.

**This rests on a changed success criterion, which is what makes it work.** EIP-7870 hosts receive only their own
subnet: 1/16 of the signatures, i.e. 125 × 3 kB ≈ 384 kB per slot at 800k. Only 1 Gbit hosts must hold all 2,000.
Earlier reports required every node to hold every signature; under that rule today's mesh failed everywhere.

## Observed mesh composition

Peering is not wired. Each node runs a peer manager in wbsim:

- target 50 peers, inbound refused above 60;
- random discovery fills up to the target;
- subnet discovery, standing in for the ENR `attnets` lookup, keeps at least 6 connected peers in each joined subnet;
- pruning above the target drops peers that share no subnet first, and never takes a subnet below 6;
- a 3 s heartbeat during the 30 s warm-up (about 40 gossipsub heartbeats), then 30 s.

The gossipsub mesh then forms by itself through GRAFT/PRUNE, with mainnet D = 8/6/12. The mesh is logged just before
publishing in every slot; the table shows slot 9. Slot 0 differs by at most a few hosts, so the mesh is stable.

| run | subscribers per subnet (EIP-7870 among them) | connections, share on 1 Gbit | EIP-7870 host: peers in own subnet, mean (min) | EIP-7870 host: mesh peers, mean (min) | of which 1 Gbit, mean (min, p10) | EIP-7870 hosts with ≤ 2 fast mesh peers | 1 Gbit host: mesh peers per subnet, fast among them | 1 Gbit-only mesh connected? |
|---|---|---|---|---|---|---|---|---|
| v800 3 kB s1 | 801–838 (59–96) | 50, 34 % | 20.4 (9) | 9.2 (6) | 7.6 (2, 5) | 2 of 1,306 | 8.1, 7.3 | yes, one component in all 16 subnets |
| v800 3 kB s2 | 789–827 (67–105) | 50, 31 % | 19.1 (7) | 9.1 (6) | 7.4 (1, 5) | 3 of 1,326 | 8.2, 7.3 | yes |
| v800 3 kB s3 | 799–830 (68–99) | 50, 33 % | 19.9 (6) | 9.2 (6) | 7.5 (2, 5) | 3 of 1,317 | 8.1, 7.3 | yes |
| v600 | 759–798 (61–100) | 50, 31 % | 19.2 (6) | 9.2 (6) | 7.5 (2, 5) | 2 of 1,350 | 8.1, 7.2 | yes |
| v400 | 698–738 (65–105) | 50, 28 % | 17.9 (7) | 9.1 (6) | 7.2 (1, 5) | 3 of 1,415 | 8.0, 7.0 | yes |
| v800 fs0 (415 fast) | 488–532 (73–117) | 50, 18 % | 13.6 (6) | 8.7 (5) | 5.8 (0, 3) | 51 of 1,633 | 7.7, 6.3 | yes |
| v400 fs0 (279 fast) | 360–410 (81–131) | 50, 12 % | 11.5 (6) | 8.3 (5) | 4.3 (0, 2) | 266 of 1,769 (11 with none) | 7.6, 5.9 | yes |

- **A fast core forms on its own,** but not because of anything clever. The 1 Gbit hosts join all 16 subnets, so they
  make up 85–93 % of each subnet's subscribers (68–85 % in `fs0`). A random mesh in a subnet is therefore mostly
  1 Gbit. In every run, the 1 Gbit hosts' mesh in each subnet is one connected component.
- **With fewer fast hosts, EIP-7870 hosts get fewer fast mesh peers.** At 400k `fs0`, 11 hosts have no fast mesh peer
  at all and 266 have at most 2. They still completed every slot: their subnet is small enough for EIP-7870 relays to
  carry it.
- **Every subnet is far above the 128-recipient DoS floor:** at least 360 subscribers in every run, and 698–838 with the
  20 % random 1 Gbit share.
- **Anonymity:** each EIP-7870 host is a normal forwarder in its subnet, and its own votes leave the same way as relayed
  ones. But its single subscription reveals which subnet its validators publish to.

## Feasibility map

Least change that passes (2,048 hosts × 10 slots, 4 s deadline, EIP-7870 links, k = 8 plus the 20 % random 1 Gbit
share, one subnet per EIP-7870 host):

| validators (signatures per slot) | 3,072 B | 1,229 B |
|---|---|---|
| 800k (2,000) | **today's gossipsub, unmodified.** Passes unbundled on 3 seeds, bundled (b16) on 2, and with the core only (`fs0`, 415 fast hosts) | **today's gossipsub, unmodified** (1 seed) |
| 600k (1,500) | **today's gossipsub, unmodified** (1 seed) | **today's gossipsub, unmodified** (1 seed) |
| 400k (1,000) | **today's gossipsub, unmodified.** Also passes with the core only (`fs0`, 279 fast hosts) | **today's gossipsub, unmodified** (1 seed) |

Bundling is not needed. It halves forward drops and lowers p99 latency, but changes nothing else that matters.

## Setup

- **Subnets:** 16. Each EIP-7870 host gets one random home subnet; its own validators' signatures are published
  there, and it subscribes to that subnet only. Hosts without validators also get one random subnet. A signature
  published by a 1 Gbit host goes to a random subnet. 1 Gbit hosts subscribe to all 16.
- **Links:** 50/25 Mbit/s for validator hosts and 50/15 for hosts without validators. Hosts with more than 8 validators
  run 1 Gbit, plus 20 % of the rest (`cloud` class). Rows marked `fs0` drop that random 20 % share.
- **Gossipsub:** Ethereum's parameters, unmodified, for every host: D = 8/6/12, D_out 2, heartbeat 0.7 s, gossip_lazy
  6, gossip_factor 0.25, IDONTWANT above 1,000 B, no IDONTWANT on publish, flood publish off, 5,000-message send
  queues, 1 s forward-queue timeout, content-hash message IDs. No no-forward leaves, no per-role D. Peer scoring is
  off, as in all earlier runs.
- **Peering:** the wbsim peer manager described above. No static dials.
- **Load:** messages published within 0.5 s from 4 s into each 12 s slot; publishers chosen in proportion to their
  validators. Deadline 4 s after publishing starts.
- **Pass:** every subscriber of a subnet holds all of that subnet's messages, and every 1 Gbit host holds all
  messages, by the deadline. The per-class completion below uses exactly that rule. From slot 2 on, each class must
  be at least 99 % complete in every slot, with a flat backlog.

## Tables

Per class. Columns:

- per-slot completion at 4 s;
- latency p50/p99 over deliveries in slots ≥ 2;
- κ = bytes received per byte of messages the host needs (its subnet; all 16 subnets for 1 Gbit hosts), including all
  gossipsub and transport overhead;
- forwards dropped by rust-libp2p (queue timeout + queue full) per node·slot, slots ≥ 2;
- MiB per node still arriving after the deadline, slot 0 and last slot;
- upload and download in the 4 s window as % of the link cap, mean and busiest node, slots ≥ 2;
- the worst node·slot's share of needed messages held at 4 s (slots ≥ 2).

### 800k validators, 3,072 B (2,000 per slot): seeds, bundling, core only

| run | class | nodes | complete per slot % | p50 / p99 s | κ | dropped fwd per node·slot | after-deadline MiB/node slot 0→last | up in 4 s window mean / max (% of cap) | down mean / max (% of cap) | worst node·slot held |
|---|---|---|---|---|---|---|---|---|---|---|
| `O-v800-s3k-b1-s1` | 50x15 | 330 | 100 100 100 100 100 100 100 100 100 100 | 0.13 / 1.11 | 8.99 | 23 | 0.00→0.01 | 44 / 63 | 14 / 17 | 100.0 % |
| `O-v800-s3k-b1-s1` | 50x25 | 976 | 100 100 100 100 100 100 100 100 100 100 | 0.12 / 0.54 | 9.78 | 19 | 0.00→0.00 | 27 / 40 | 15 / 20 | 100.0 % |
| `O-v800-s3k-b1-s1` | cloud | 742 | 99.7 100 100 100 100 100 100 100 100 100 | 0.10 / 0.33 | 7.62 | 168 | 0.00→0.01 | 9 / 13 | 9 / 14 | 100.0 % |
| `O-v800-s3k-b1-s2` | 50x15 | 329 | 100 99.4 100 100 99.7 100 100 100 100 100 | 0.13 / 1.09 | 9.05 | 21 | 0.00→0.01 | 45 / 63 | 14 / 18 | 99.3 % |
| `O-v800-s3k-b1-s2` | 50x25 | 997 | 100 100 100 100 100 100 100 100 100 100 | 0.12 / 0.53 | 9.59 | 17 | 0.00→0.00 | 27 / 39 | 15 / 20 | 100.0 % |
| `O-v800-s3k-b1-s2` | cloud | 722 | 99.7 100 100 100 100 100 100 100 100 100 | 0.10 / 0.40 | 7.69 | 132 | 0.00→0.01 | 10 / 13 | 9 / 13 | 100.0 % |
| `O-v800-s3k-b1-s3` | 50x15 | 314 | 100 100 99.7 100 100 100 100 100 99.7 100 | 0.12 / 1.10 | 9.08 | 23 | 0.00→0.00 | 45 / 61 | 14 / 17 | 98.1 % |
| `O-v800-s3k-b1-s3` | 50x25 | 1003 | 100 100 100 100 100 100 100 100 100 100 | 0.11 / 0.52 | 9.70 | 18 | 0.00→0.00 | 27 / 39 | 15 / 20 | 100.0 % |
| `O-v800-s3k-b1-s3` | cloud | 731 | 100 100 100 100 100 100 100 100 100 100 | 0.09 / 0.38 | 7.61 | 111 | 0.00→0.00 | 9 / 13 | 9 / 13 | 100.0 % |
| `O-v800-s3k-b16-s1` | 50x15 | 330 | 100 100 100 100 100 100 100 100 100 100 | 0.11 / 0.68 | 9.00 | 6 | 0.00→0.00 | 42 / 61 | 14 / 18 | 100.0 % |
| `O-v800-s3k-b16-s1` | 50x25 | 976 | 100 100 100 100 100 100 100 100 100 100 | 0.11 / 0.37 | 9.49 | 3 | 0.00→0.00 | 26 / 38 | 15 / 20 | 100.0 % |
| `O-v800-s3k-b16-s1` | cloud | 742 | 100 100 100 100 100 100 100 100 100 100 | 0.10 / 0.27 | 7.36 | 9 | 0.00→0.00 | 9 / 13 | 9 / 13 | 100.0 % |
| `O-v800-s3k-b16-s2` | 50x15 | 329 | 100 100 100 100 100 100 100 100 100 100 | 0.11 / 0.72 | 9.01 | 5 | 0.00→0.00 | 43 / 60 | 14 / 18 | 100.0 % |
| `O-v800-s3k-b16-s2` | 50x25 | 997 | 100 100 100 100 100 100 100 100 100 100 | 0.11 / 0.38 | 9.31 | 3 | 0.00→0.00 | 26 / 37 | 14 / 20 | 100.0 % |
| `O-v800-s3k-b16-s2` | cloud | 722 | 100 100 100 100 100 100 100 100 100 100 | 0.10 / 0.29 | 7.38 | 9 | 0.00→0.00 | 9 / 12 | 9 / 13 | 100.0 % |
| `O-v800-s3k-b1-fs0-s1` | 50x15 | 409 | 100 100 100 100 100 99.8 100 100 100 100 | 0.13 / 1.02 | 8.53 | 22 | 0.00→0.00 | 41 / 63 | 13 / 16 | 98.3 % |
| `O-v800-s3k-b1-fs0-s1` | 50x25 | 1224 | 100 100 100 100 100 100 100 100 100 100 | 0.13 / 0.48 | 9.09 | 18 | 0.00→0.00 | 25 / 40 | 14 / 20 | 100.0 % |
| `O-v800-s3k-b1-fs0-s1` | cloud | 415 | 99.3 100 100 100 100 100 100 100 100 100 | 0.12 / 0.33 | 7.03 | 81 | 0.00→0.00 | 9 / 13 | 9 / 13 | 100.0 % |

### Consolidation and smaller signatures (unbundled)

| run | class | nodes | complete per slot % | p50 / p99 s | κ | dropped fwd per node·slot | after-deadline MiB/node slot 0→last | up in 4 s window mean / max (% of cap) | down mean / max (% of cap) | worst node·slot held |
|---|---|---|---|---|---|---|---|---|---|---|
| `O-v600-s3k-b1-s1` | 50x15 | 329 | 100 100 100 100 100 100 100 100 100 100 | 0.11 / 0.44 | 9.67 | 5 | 0.00→0.00 | 34 / 51 | 11 / 15 | 100.0 % |
| `O-v600-s3k-b1-s1` | 50x25 | 1021 | 100 100 100 100 100 100 100 100 100 100 | 0.11 / 0.30 | 9.73 | 3 | 0.00→0.00 | 21 / 31 | 11 / 16 | 100.0 % |
| `O-v600-s3k-b1-s1` | cloud | 698 | 100 100 100 100 100 100 100 100 100 100 | 0.10 / 0.29 | 7.59 | 10 | 0.00→0.00 | 7 / 10 | 7 / 10 | 100.0 % |
| `O-v400-s3k-b1-s1` | 50x15 | 332 | 100 100 100 100 100 100 100 100 100 100 | 0.10 / 0.21 | 9.66 | 0 | 0.00→0.00 | 23 / 34 | 7 / 10 | 100.0 % |
| `O-v400-s3k-b1-s1` | 50x25 | 1083 | 100 100 100 100 100 100 100 100 100 100 | 0.10 / 0.22 | 9.58 | 0 | 0.00→0.00 | 14 / 20 | 7 / 11 | 100.0 % |
| `O-v400-s3k-b1-s1` | cloud | 633 | 100 100 100 100 100 100 100 100 100 100 | 0.10 / 0.21 | 7.49 | 0 | 0.00→0.00 | 5 / 7 | 5 / 7 | 100.0 % |
| `O-v400-s3k-b1-fs0-s1` | 50x15 | 409 | 100 100 100 100 100 100 100 100 100 100 | 0.11 / 0.23 | 8.58 | 0 | 0.00→0.00 | 20 / 33 | 7 / 10 | 100.0 % |
| `O-v400-s3k-b1-fs0-s1` | 50x25 | 1360 | 100 100 100 100 100 100 100 100 100 100 | 0.11 / 0.23 | 8.41 | 0 | 0.00→0.00 | 12 / 20 | 6 / 11 | 100.0 % |
| `O-v400-s3k-b1-fs0-s1` | cloud | 279 | 100 100 100 100 100 100 100 100 100 100 | 0.11 / 0.22 | 6.81 | 0 | 0.00→0.00 | 4 / 6 | 4 / 6 | 100.0 % |
| `O-v800-s1k-b1-s1` | 50x15 | 330 | 100 100 100 100 100 100 100 100 100 100 | 0.10 / 0.18 | 10.76 | 0 | 0.00→0.00 | 21 / 32 | 7 / 9 | 100.0 % |
| `O-v800-s1k-b1-s1` | 50x25 | 976 | 100 100 100 100 100 100 100 100 100 100 | 0.10 / 0.19 | 10.72 | 0 | 0.00→0.00 | 13 / 19 | 7 / 10 | 100.0 % |
| `O-v800-s1k-b1-s1` | cloud | 742 | 100 100 100 100 100 100 100 100 100 100 | 0.10 / 0.19 | 8.58 | 87 | 0.00→0.00 | 4 / 6 | 4 / 6 | 100.0 % |
| `O-v600-s1k-b1-s1` | 50x15 | 329 | 100 100 100 100 100 100 100 100 100 100 | 0.10 / 0.18 | 10.78 | 0 | 0.00→0.00 | 16 / 24 | 5 / 7 | 100.0 % |
| `O-v600-s1k-b1-s1` | 50x25 | 1021 | 100 100 100 100 100 100 100 100 100 100 | 0.10 / 0.18 | 10.37 | 0 | 0.00→0.00 | 9 / 14 | 5 / 7 | 100.0 % |
| `O-v600-s1k-b1-s1` | cloud | 698 | 100 100 100 100 100 100 100 100 100 100 | 0.10 / 0.18 | 8.58 | 14 | 0.00→0.00 | 3 / 4 | 3 / 4 | 100.0 % |
| `O-v400-s1k-b1-s1` | 50x15 | 332 | 100 100 100 100 100 100 100 100 100 100 | 0.10 / 0.18 | 10.42 | 0 | 0.00→0.00 | 10 / 16 | 3 / 5 | 100.0 % |
| `O-v400-s1k-b1-s1` | 50x25 | 1083 | 100 100 100 100 100 100 100 100 100 100 | 0.10 / 0.18 | 9.95 | 0 | 0.00→0.00 | 6 / 9 | 3 / 5 | 100.0 % |
| `O-v400-s1k-b1-s1` | cloud | 633 | 100 100 100 100 100 100 100 100 100 100 | 0.10 / 0.17 | 8.51 | 0 | 0.00→0.00 | 2 / 3 | 2 / 3 | 100.0 % |

### Network-wide counters (slots ≥ 2 unless noted)

| run | messages per slot | missed node·slots | copies received per useful message | IDONTWANT IDs received per node·slot | forwards dropped per slot, slot 0 → slots ≥ 2 | queue-full drops per slot, slot 0 → slots ≥ 2 |
|---|---|---|---|---|---|---|
| v800 3 kB s1 | 2,000 | 0 | 7.18 | 43,161 | 1.8M → 61k–85k | 9.6M → 34k–257k |
| v800 3 kB b16 s1 | 1,052 bundles | 0 | 7.23 | 23,475 | 378k → 10k–13k | 2.2M → 0–3k |
| v600 3 kB | 1,500 | 0 | 7.19 | 30,720 | 791k → 6k–9k | 5.0M → 0–26k |
| v400 3 kB | 1,000 | 0 | 7.13 | 18,606 | 217k → 15–147 | 1.5M → 0–1k |
| v400 1.2 kB | 1,000 | 0 | 7.14 | 18,602 | 229k → 0–75 | 1.5M → 0–1k |

- **Drops are front-loaded.** Slots 0 and 1 drop far more forwards than later slots (9.6M queue-full drops in slot 0 at
  800k × 3 kB). They fall by an order of magnitude by slot 2 and stay flat after that. Completion was still 99.3–100 %
  in slot 0, so the dropped forwards were duplicates. I did not trace the cause; the likely one is the first burst over
  meshes whose IDONTWANT and duplicate state is still cold.
- **Redundancy is high.** Every host receives each needed message about 7 times (κ 9–11 including overhead). For an
  EIP-7870 host that is about 3.5 MB per slot at 800k × 3 kB, 14 % of its 50 Mbit/s downlink over the window.
- **Upload matches the back-of-envelope.** Forwarding ~7 copies of a 384 kB subnet in 4 s is ~5 Mbit/s. The 50/15
  class uploaded 44 % of 15 Mbit/s on average in the window (6.6 Mbit/s), 63 % on the busiest node; 50/25 hosts used
  27 % (40 %). The busiest 1 Gbit host used 13 %.

## Not done

- **4,096 hosts.** With 50 peers per node, a 2,048-host run used about 130–140 GB in total (Shadow at most 34 GB, the
  rest in 2,048 wbsim processes). Extrapolated, 4,096 hosts need about 270 GB, above the 256 GB budget, so I did not
  launch it. A lower peer target would fit but would change the scenario.
- **Single seeds** for 600k, 400k and the 1,229 B cells. They pass with zero misses from slot 2 on, which is more
  margin than the 800k × 3 kB cell, where 3 seeds agree.
- **Peer scoring** is off, and the peer manager is simplified (uniform random discovery, a fixed inbound cap,
  no client diversity).

## Commands

Each row is `runs/run_lever.sh NAME 2048 10 46 FLAGS…`, which runs `gen_config.py` with the shared base flags
(`--mode flood --drain 8 --validators-csv data/f9ba162f-nodes.csv --fast-above 8 --fast-share 0.2 --links 50/25
--links-novalidator 50/15`), then Shadow on CPUs 48–95 at nice 19, then `analyze.py`. The per-run flags:

```sh
# 800k x 3 kB, unbundled, seed 1 (seeds 2 and 3: --seed 2 / --seed 3; core only: add --fast-share 0)
--sig-subnets 16 --one-subnet --peer-target 50 --warmup 30 --msgs 2000 --seed 1
# bundled
--sig-subnets 16 --one-subnet --peer-target 50 --warmup 30 --batch 16 --msgs 2000 --seed 1
# 600k / 400k: --consolidate 0.75 --msgs 1500 / --consolidate 0.5 --msgs 1000; leanVM size: --msg-bytes 1229
nice python3 repo/sim/analyze.py --levers runs/NAME   # completion, latency, κ, drops, link use (summary2.json)
nice python3 repo/sim/analyze.py --mesh runs/NAME     # peering and mesh composition (mesh.json)
```

The full flag set of every run is in `runs/queue-levers.txt` (lines starting with `O-`).

## Machine and usage

- AMD EPYC 9454P (48 cores / 96 threads), 503 GiB RAM, shared. CPUs 48–95 only, nice 19.
- One 2,048-host run at a time with 46 Shadow threads, because each needed 130–140 GB. Runs took 10–35 min.
- Started 19:52 CET on 5 Nov. Stopped 20:48–21:57 at Yann's request while the server was reconnected; the interrupted
  baseline is kept as `runs/killed-O-v800-s3k-b1-s1-slot8` and is not used here (its slots 0–7 matched the rerun).
  The 12 runs ran 21:57–02:56. Other users' load was zero throughout.

## Changed files (uncommitted)

- `sim/wbsim/src/main.rs`: peer manager (`peer_target`, `peer_max`, `subnet_min_peers`; random and subnet discovery,
  pruning, inbound cap) and a per-slot `mesh` log of connections and mesh peers per subscribed topic.
- `sim/gen_config.py`: `--one-subnet`, `--peer-target`, `--peer-max`, `--subnet-min-peers`, `--warmup`.
- `sim/analyze.py`: per-class latency, κ, drops, backlog and worst node·slot in `--levers`; new `--mesh`.
- `results/gossip-one-subnet.md` (this file).
