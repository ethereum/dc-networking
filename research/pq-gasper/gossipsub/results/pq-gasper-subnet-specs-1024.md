# PQ Gasper on 1,024 hosts: which link a node needs for one subnet of 1,600 signatures per slot

*Final, Nov 24, 2026, 14:28 CET: twelve runs of 1,024 hosts × 20 slots, listed in the runs table, each next to its
2,048-host counterpart.*

The study of [pq-gasper-subnet-specs.md](pq-gasper-subnet-specs.md), repeated on a network of 1,024 hosts instead of 2,048:
which home link passes at 1,600 signatures per subnet per slot, and how the result depends on access-line loss, CPU speed
and memory. Everything else is kept as in the 2,048-host study, so each 1,024-host run is shown next to its 2,048-host
counterpart, which has the same name with 2048 in place of 1024.

**Load and requirement.** One PQ Gasper attestation subnet carries 1,600 signatures per subnet per slot (800,000
validators / 32 slots / 16 subnets), 2,404 B each (leanXMSS), bundled up to 16 per publisher, published 4.0–4.5 s into the
slot. Every node subscribes, and every node of every class must hold all of the slot's signatures at 8.0 s. On 1,024 hosts
the signatures come in fewer, larger messages (211 per slot on average, 200–225, against 302 on 2,048 hosts): the same validators sit on
half as many hosts, so each publisher bundles more of its own signatures.

**Pass rule** (as before): from slot 2, at least 99 % of a class's online nodes hold every signature at 8.0 s in every slot,
and late first deliveries (first received 8–16 s) do not build up. Signatures missing at 8.0 s are reported too. With 658
home hosts the bar allows 6 incomplete home hosts in a slot (2,048 hosts: 13 of 1,306), so a verdict can flip by chance; a
1,024-host verdict that differs from the 2,048-host one is repeated with seed 2 before it is reported.

## Result

At 1,600 signatures per subnet per slot, with every node needing all of them at 8.0 s, the 1,024-host network gives the same
verdict as the 2,048-host network in all 12 runs, for every link class. No verdict differed, so no seed-2 repeat or
bracketing run was added; the planned seed-2 run at 100/100 agrees too.

- **The smallest home link that passes is the same as on 2,048 hosts: 100 Mbit/s down and 75–100 Mbit/s up, when the home
  access line loses almost no packets.** With the access links' loss off, 1000/50 fails (worst slot 96.8 %), 1000/75 passes
  (99.5 %), 50/100 fails (81.0 %) and 100/100 passes on two seeds (99.1 and 99.4 %). On seed 1, 100/100 passes by the
  narrowest margin the rule allows: 6 of 655 home hosts are incomplete in its worst slot. 100/75 was not run.
- **Access-line loss decides, as on 2,048 hosts.** With the modelled loss (fiber 0.05 %, cable 0.1 %, DSL 0.25 % per
  direction) no home link passes: 1000/100 and 1000/200 reach 80.6 and 83.8 % in their worst slots, with uplinks 27 and 14 %
  busy over 4–8 s. At a fifth of that loss, 1000/200 fails (96.5 %): DSL hosts fail clearly, fiber and cable hosts are at the
  bar. At the same loss, DSL hosts do worse than fiber hosts. With loss on, the 1,024-host network completes a few points
  more than the 2,048-host one; per message both miss about the same share, and a 1,024-host slot has fewer messages (211
  against 302 on average, because each publisher bundles more of its own signatures). The simulated TCP has no tail loss
  probe or RACK, so these results are pessimistic for lossy lines on both networks.
- **50 Mbit/s down fails the same way:** the downlink stays at 64 % of its capacity while the demand is above it, the pattern
  the 2,048-host study traced to drops in Shadow's CoDel downlink queue (10 ms target, no packet limit). Its worst slot
  (81.0 %) is far below 95 %, so the diagnostic was not repeated.
- **CPU margin:** with PQ verification at 2,000 µs per signature (6,000 µs on slow CPUs), 100/100 passes (99.85 %), and
  slow-CPU hosts finish at 6.93 s at p99 (2,048 hosts: 6.89 s), about 1.1 s before the deadline. That time is set by their
  own verification work, so it does not depend on the network size.
- **The EIP-7870 links fail as before:** with 50/25 for home hosts with validators and 50/15 for the others, and the usual
  loss, the worst slots are 25.8 % (50/15) and 52.7 % (50/25), against 23.3 and 53.3 % on 2,048 hosts; 50/15 hosts hand TCP
  122 % of their uplink over 4–8 s. The 1 Gbit hosts fail narrowly here too (98.91 % in 2 of 18 slots, 4 of 366 incomplete
  where 3 are allowed; 2,048 hosts: 98.92 % in 1 of 13 slots).
- **80 % of hosts on 1 Gbit does not rescue the home nodes:** 50/15 worst slot 22.0 %, 50/25 48.5 %; the 1 Gbit hosts pass
  (99.51 %). A 1 Gbit host sends and receives on average what it does on 2,048 hosts: over 4–8 s 37–41 Mbit/s up and
  32–33 down, over 4–5 s 122–133 up and 89–93 down.
- **Link use** is close to the 2,048-host values: over 4–8 s, home and 1 Gbit hosts upload and download within 8 % of them
  in every run; over 4–5 s, home hosts upload up to 16 % more. At 100/100 a home node uses 34 % of its uplink and 42 % of
  its downlink over 4–8 s, and 75 and 62 % over 4–5 s.
- **Memory and time:** peaks are 88–120 GiB (0.47–0.49 of the 2,048-host peaks) and wall times 0.95–1.23 h. Shadow's own
  memory halves, to 10–13.5 GiB, but a simulated node holds 76–106 MiB, only 2.5–6 % less than on 2,048 hosts.
- **Subgroups are noisier:** with 139 DSL hosts, two incomplete hosts put the subgroup under 99 %. DSL hosts dip under the bar
  in 1–6 of the 18 slots of four of the five passing runs (2,048 hosts: 0–8), while their mean completion stays at
  99.2–100 %.

## Setup

- The stack and flags of `runs/run_pq1600.sh`, as in the 2,048-host study: 1,024 hosts × 20 slots, seed 1, mainnet
  validator counts; Shadow 3.3.0 with the rtt6 TCP build (Linux v6.12 CUBIC with HyStart, slow start after idle); client mix
  with default peer targets and per-client gossipsub parameters; client-faithful scoring; WonderNetwork city latencies;
  fiber, cable and DSL access latency, jitter and packet loss; churn; 30 % of home hosts behind NAT; signature verification
  with 20 % slow CPUs; background traffic (blocks, data columns, aggregates, sync messages) and no BLS attestations.
- Hosts with more than 8 validators plus 20 % of the rest are on 1 Gbit: 366 hosts (202 + 164). The other 658, called home
  hosts below, all get the link under test, with and without validators: 295 fiber, 224 cable, 139 DSL; 152 with a slow
  CPU; 204 behind NAT. In `Q1024x20-m1600-s1` the 499 home hosts with validators are on 50/25 and the other 159 on 50/15.
- Checked on the first run against the configuration of `Q1024x20-m1600-s1`: apart from the home links, every host's fields
  (city, access type, client, validators, NAT, CPU) and the publisher schedule are identical. The 1,024 hosts carry 87,051
  validators on 822 hosts with validators; the largest (19,524 validators) publishes 23–25 bundles per slot.

## Runs

One run at a time, in the coordinator's order, so that the limits come first: with the home access links' packet loss off
(`--access-loss-scale 0`; backbone loss, access latency and jitter unchanged), 1000/100, 1000/50, 1000/75, 100/100, 50/100
and 100/100 on seed 2; with the usual access loss, 1000/100 and 1000/200; with a fifth of it, 1000/200; 100/100 with PQ
verification at 2,000 µs per signature; the EIP-7870 links (50/25 with validators, 50/15 without) with the usual loss;
and the same with 75 % of the remaining hosts on 1 Gbit (`--fast-share 0.75`, 80 % of all hosts). Each 1,024-host value is
shown next to the 2,048-host one, and the 2,048-host numbers come from the analysis files of the runs in
[pq-gasper-subnet-specs.md](pq-gasper-subnet-specs.md) and [pq-gasper-one-subnet.md](pq-gasper-one-subnet.md).

| Run (1,600 signatures per subnet per slot; every class must hold all at 8.0 s) | Home link | Home: worst slot / mean, 1,024 hosts | Home: worst slot / mean, 2,048 hosts | 1 Gbit: worst slot / mean, 1,024 hosts (2,048) | Signatures missing at 8.0 s, home, 1,024 / 2,048 | Home verdict, 1,024 / 2,048 | Wall, peak PSS, 1,024 hosts (2,048) |
|---|---|---|---|---|---|---|---|
| `S1024x20-h1000x100-al0-s1` | 1000/100, access loss off | 99.69 / 99.86 % | 99.69 / 99.81 % | 99.73 / 99.95 % (99.86 / 99.98 %) | 0.003 / 0.007 % | **pass** / pass | 0.97 h, 88 GiB (1.76 h, 184 GiB) |
| `S1024x20-h1000x50-al0-s1` | 1000/50, access loss off | 96.79 / 98.94 % | 96.16 / 99.02 % | 99.73 / 99.91 % (99.59 / 99.86 %) | 0.040 / 0.040 % | fail / fail | 1.00 h, 97 GiB (1.79 h, 201 GiB) |
| `S1024x20-h1000x75-al0-s1` | 1000/75, access loss off | 99.54 / 99.80 % | 99.39 / 99.81 % | 99.45 / 99.86 % (99.86 / 99.98 %) | 0.012 / 0.006 % | **pass** / pass | 0.98 h, 92 GiB (1.77 h, 190 GiB) |
| `S1024x20-h100x100-al0-s1` | 100/100, access loss off | 99.08 / 99.68 % | 99.16 / 99.72 % | 99.73 / 99.97 % (99.59 / 99.88 %) | 0.013 / 0.013 % | **pass** / pass | 1.01 h, 99 GiB (1.82 h, 204 GiB) |
| `S1024x20-h50x100-al0-s1` | 50/100, access loss off | 81.04 / 86.20 % | 77.82 / 86.37 % | 99.73 / 99.92 % (99.46 / 99.77 %) | 0.315 / 0.283 % | fail / fail | 1.13 h, 111 GiB (1.96 h, 227 GiB) |
| `S1024x20-h100x100-al0-s2` | 100/100, access loss off, seed 2 | 99.39 / 99.74 % | 99.39 / 99.73 % | 100.00 / 100.00 % (99.58 / 99.77 %) | 0.007 / 0.013 % | **pass** / pass | 1.01 h, 98 GiB (1.83 h, 206 GiB) |
| `S1024x20-h1000x100-s1` | 1000/100, usual access loss | 80.61 / 84.13 % | 78.83 / 80.63 % | 99.45 / 99.92 % (99.59 / 99.79 %) | 1.395 / 1.595 % | fail / fail | 1.09 h, 107 GiB (1.94 h, 222 GiB) |
| `S1024x20-h1000x200-s1` | 1000/200, usual access loss | 83.82 / 85.78 % | 77.88 / 81.29 % | 99.45 / 99.89 % (99.86 / 99.92 %) | 1.116 / 1.442 % | fail / fail | 1.08 h, 106 GiB (1.94 h, 221 GiB) |
| `S1024x20-h1000x200-al02-s1` | 1000/200, access loss at a fifth | 96.48 / 97.67 % | 95.16 / 96.30 % | 100.00 / 100.00 % (99.59 / 99.93 %) | 0.119 / 0.153 % | fail / fail | 1.02 h, 96 GiB (1.85 h, 201 GiB) |
| `S1024x20-h100x100-al0-v2000-s1` | 100/100, access loss off, PQ verification 2,000 µs | 99.85 / 99.94 % | 99.62 / 99.87 % | 99.73 / 99.94 % (99.86 / 99.96 %) | 0.002 / 0.003 % | **pass** / pass | 0.95 h, 90 GiB (1.75 h, 189 GiB) |
| `Q1024x20-m1600-s1` | EIP-7870: 50/25 with validators, 50/15 without; usual access loss | 50/15 25.79 / 30.64 %; 50/25 52.73 / 58.38 % | 50/15 23.33 / 28.51 %; 50/25 53.29 / 55.79 % | 98.91 / 99.38 % (98.92 / 99.54 %) | 11.576 / 12.772 %; 3.711 / 4.090 % | fail / fail; fail / fail | 1.23 h, 120 GiB (1.70 h, 236 GiB: stopped for memory, analysed to slot 14) |
| `Q1024x20-m1600-fs75-s1` | EIP-7870 links, usual access loss, 80 % of hosts on 1 Gbit | 50/15 21.95 / 39.30 %; 50/25 48.48 / 62.29 % | 50/15 23.21 / 33.93 %; 50/25 52.88 / 59.11 % | 99.51 / 99.85 % (99.82 / 99.92 %) | 8.320 / 7.324 %; 2.216 / 2.348 % | fail / fail; fail / fail | 1.03 h, 90 GiB (1.87 h, 191 GiB) |

### 1000/100 with the access links' loss off (slots 2–19)

The same verdict as on 2,048 hosts: the home class passes, with its worst slot at 99.69 % (2 of 655), 0.003 % of
signatures missing at 8.0 s, the last needed signature at 5.74 s at p99 (2,048 hosts: 5.85 s) and no build-up of late first
deliveries (0.01 and 0.00 per node-slot in the two halves of the run). Link use is the same as on 2,048 hosts: home hosts
upload 35 % of their link over 4–8 s and 100 % of it over 4–5 s (2,048 hosts: 34 and 94 %), and drop 20 % of their PQ sends
after 1 s in the queue. DSL hosts dip under 99 % in 1 of the 18 slots (98.55 %, 2 of 138): in a group of 139 hosts, two
incomplete hosts are enough.

| Class (1,600 signatures per subnet per slot; must hold all at 8.0 s) | Hosts | Complete at 8.0 s: worst slot / mean | Signatures missing at 8.0 s | Last needed signature p50 / p90 / p99 | Upload 4–8 s: Mbit/s mean, busiest (% of link) | Upload 4–5 s mean | Download 4–8 s: mean, busiest | Download 4–5 s mean | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|---|---|---|
| Home 1000/100, 1,024 hosts | 658 | 99.69 % (2 of 655) / 99.86 % | 0.003 % | 5.05 / 5.41 / 5.74 s | 34.8 (35 %), 64.1 (64 %) | 99.8 (100 %) | 42.8 (4.3 %), 104.0 (10 %) | 92.2 (9.2 %) | 20 % |
| Home 1000/100, 2,048 hosts | 1,306 | 99.69 % (4 of 1,302) / 99.81 % | 0.007 % | 5.17 / 5.37 / 5.85 s | 33.9 (34 %), 60.7 (61 %) | 94.1 (94 %) | 41.5 (4.2 %), 90.9 (9.1 %) | 89.3 (8.9 %) | 20 % |
| 1 Gbit, 1,024 hosts | 366 | 99.73 % (1 of 366) / 99.95 % | 0.001 % | 5.00 / 5.34 / 5.67 s | 55.1 (5.5 %), 92.4 (9.2 %) | 180.8 (18 %) | 36.1 (3.6 %), 110.7 (11 %) | 86.5 (8.6 %) | 10 % |
| 1 Gbit, 2,048 hosts | 742 | 99.86 % (1 of 739) / 99.98 % | 0.000 % | 5.13 / 5.26 / 5.61 s | 53.8 (5.4 %), 103.7 (10 %) | 169.4 (17 %) | 36.1 (3.6 %), 72.7 (7.3 %) | 82.7 (8.3 %) | 10 % |

| Home hosts by access type and CPU (1,600 signatures per subnet per slot, all needed at 8.0 s) | Hosts, 1,024 / 2,048 | Worst slot, 1,024 / 2,048 | Mean complete, 1,024 / 2,048 | Signatures missing at 8.0 s, 1,024 / 2,048 | Last needed p99, 1,024 / 2,048 | Slots under 99 %, 1,024 / 2,048 | Upload 4–8 s / 4–5 s, % of link (1,024) | PQ sends dropped after 1 s (1,024) |
|---|---|---|---|---|---|---|---|---|
| Fiber | 295 / 591 | 99.66 % (1 of 293) / 99.66 % (2 of 589) | 99.98 / 99.92 % | 0.000 / 0.002 % | 5.72 / 5.87 s | 0 / 0 | 37 / 104 % | 18 % |
| Cable | 224 / 436 | 99.55 % (1 of 223) / 99.54 % (2 of 435) | 99.78 / 99.80 % | 0.008 / 0.007 % | 5.74 / 5.71 s | 0 / 0 | 35 / 101 % | 21 % |
| DSL | 139 / 279 | 98.55 % (2 of 138) / 99.28 % (2 of 279) | 99.72 / 99.60 % | 0.003 / 0.017 % | 5.81 / 6.16 s | 1 / 0 | 31 / 89 % | 23 % |
| Slow CPU (3×) | 152 / 232 | 100.00 % (0 of 151) / 99.13 % (2 of 231) | 100.00 / 99.64 % | 0.000 / 0.017 % | 5.60 / 6.16 s | 0 / 0 | 34 / 97 % | 20 % |
| Normal CPU | 506 / 1,074 | 99.60 % (2 of 503) / 99.72 % (3 of 1,070) | 99.81 / 99.85 % | 0.004 / 0.005 % | 5.80 / 5.80 s | 0 / 0 | 35 / 100 % | 20 % |

### 1000/50 with the access links' loss off (slots 2–19)

Fails as on 2,048 hosts, and for the same reason, the uplink: home hosts hand TCP 132 % of their link over 4–5 s (2,048
hosts: 123 %) and drop 39 % of their PQ sends after 1 s in the queue. The home class is under 99 % in 7 of the 18 slots
(slots 2–5, 9, 10 and 13; 2,048 hosts: 4 slots), worst in slot 2 at 96.79 % (21 of 654), with 0.040 % of signatures
missing at 8.0 s, as on 2,048 hosts. Late first deliveries fall rather than build up (0.09 per node-slot in the first half,
0.04 in the second). Fiber and DSL hosts are under 99 % in most slots (11 and 10 of 18), cable hosts in 1.

| Class (1,600 signatures per subnet per slot; must hold all at 8.0 s) | Hosts | Complete at 8.0 s: worst slot / mean | Signatures missing at 8.0 s | Last needed signature p50 / p90 / p99 | Upload 4–8 s: Mbit/s mean, busiest (% of link) | Upload 4–5 s mean | Download 4–8 s: mean, busiest | Download 4–5 s mean | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|---|---|---|
| Home 1000/50, 1,024 hosts | 658 | 96.79 % (21 of 654) / 98.94 % | 0.040 % | 5.47 / 6.13 / 7.48 s | 28.7 (57 %), 49.1 (98 %) | 65.9 (132 %) | 37.6 (3.8 %), 96.2 (9.6 %) | 61.6 (6.2 %) | 39 % |
| Home 1000/50, 2,048 hosts | 1,306 | 96.16 % (50 of 1,302) / 99.02 % | 0.040 % | 5.27 / 5.96 / 7.02 s | 27.5 (55 %), 48.1 (96 %) | 61.6 (123 %) | 36.4 (3.6 %), 85.7 (8.6 %) | 59.9 (6.0 %) | 38 % |
| 1 Gbit, 1,024 hosts | 366 | 99.73 % (1 of 366) / 99.91 % | 0.007 % | 5.21 / 5.80 / 6.15 s | 56.1 (5.6 %), 94.9 (9.5 %) | 168.0 (17 %) | 33.1 (3.3 %), 99.4 (9.9 %) | 73.7 (7.4 %) | 18 % |
| 1 Gbit, 2,048 hosts | 742 | 99.59 % (3 of 739) / 99.86 % | 0.006 % | 5.14 / 5.47 / 6.02 s | 54.1 (5.4 %), 108.0 (11 %) | 156.9 (16 %) | 32.3 (3.2 %), 78.7 (7.9 %) | 69.4 (6.9 %) | 17 % |

| Home hosts by access type and CPU (1,600 signatures per subnet per slot, all needed at 8.0 s) | Hosts, 1,024 / 2,048 | Worst slot, 1,024 / 2,048 | Mean complete, 1,024 / 2,048 | Signatures missing at 8.0 s, 1,024 / 2,048 | Last needed p99, 1,024 / 2,048 | Slots under 99 %, 1,024 / 2,048 | Upload 4–8 s / 4–5 s, % of link (1,024) | PQ sends dropped after 1 s (1,024) |
|---|---|---|---|---|---|---|---|---|
| Fiber | 295 / 591 | 95.92 % (12 of 294) / 95.25 % (28 of 589) | 98.71 / 99.05 % | 0.048 / 0.034 % | 7.97 / 6.98 s | 11 / 5 | 59 / 134 % | 38 % |
| Cable | 224 / 436 | 98.65 % (3 of 223) / 96.31 % (16 of 434) | 99.65 / 98.89 % | 0.010 / 0.056 % | 6.83 / 7.16 s | 1 / 8 | 57 / 132 % | 39 % |
| DSL | 139 / 279 | 95.62 % (6 of 137) / 97.85 % (6 of 279) | 98.27 / 99.18 % | 0.074 / 0.030 % | 8.34 / 6.94 s | 10 / 9 | 54 / 128 % | 41 % |
| Slow CPU (3×) | 152 / 232 | 95.36 % (7 of 151) / 96.97 % (7 of 231) | 98.57 / 98.58 % | 0.052 / 0.088 % | 8.29 / 8.21 s | 8 / 12 | 57 / 129 % | 39 % |
| Normal CPU | 506 / 1,074 | 97.22 % (14 of 503) / 95.99 % (43 of 1,071) | 99.05 / 99.12 % | 0.037 / 0.030 % | 7.30 / 6.90 s | 4 / 4 | 58 / 133 % | 39 % |

### 1000/75 with the access links' loss off (slots 2–19)

Passes as on 2,048 hosts, so the smallest upload that passes at 1,000 down is 75 Mbit/s on both networks: 50 fails and
75 passes. The home class is at least 99.54 % complete in every slot (3 of 653 in the worst; 2,048 hosts: 99.39 %), 0.012 %
of signatures are missing at 8.0 s and the last needed signature arrives by 6.10 s at p99. Late first deliveries stay flat
(0.02 per node-slot in both halves). The uplink is at its limit over 4–5 s, as on 2,048 hosts (110 % of the link handed to
TCP, against 106 %), and 29 % of the PQ sends are dropped after 1 s in the queue. DSL hosts are under 99 % in 5 of the 18
slots (worst 97.81 %, 3 of 137), which they never are on 2,048 hosts; every other subgroup stays above it in every slot.

| Class (1,600 signatures per subnet per slot; must hold all at 8.0 s) | Hosts | Complete at 8.0 s: worst slot / mean | Signatures missing at 8.0 s | Last needed signature p50 / p90 / p99 | Upload 4–8 s: Mbit/s mean, busiest (% of link) | Upload 4–5 s mean | Download 4–8 s: mean, busiest | Download 4–5 s mean | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|---|---|---|
| Home 1000/75, 1,024 hosts | 658 | 99.54 % (3 of 653) / 99.80 % | 0.012 % | 5.08 / 5.56 / 6.10 s | 31.6 (42 %), 52.5 (70 %) | 82.3 (110 %) | 40.4 (4.0 %), 103.6 (10 %) | 78.5 (7.9 %) | 29 % |
| Home 1000/75, 2,048 hosts | 1,306 | 99.39 % (8 of 1,302) / 99.81 % | 0.006 % | 5.20 / 5.54 / 6.20 s | 31.3 (42 %), 56.3 (75 %) | 79.3 (106 %) | 39.5 (3.9 %), 87.4 (8.7 %) | 75.7 (7.6 %) | 26 % |
| 1 Gbit, 1,024 hosts | 366 | 99.45 % (2 of 366) / 99.86 % | 0.004 % | 4.96 / 5.34 / 5.95 s | 55.3 (5.5 %), 99.5 (9.9 %) | 176.7 (18 %) | 34.4 (3.4 %), 126.2 (13 %) | 80.6 (8.1 %) | 13 % |
| 1 Gbit, 2,048 hosts | 742 | 99.86 % (1 of 739) / 99.98 % | 0.001 % | 5.14 / 5.32 / 5.77 s | 54.2 (5.4 %), 110.7 (11 %) | 164.2 (16 %) | 34.8 (3.5 %), 78.9 (7.9 %) | 76.0 (7.6 %) | 12 % |

| Home hosts by access type and CPU (1,600 signatures per subnet per slot, all needed at 8.0 s) | Hosts, 1,024 / 2,048 | Worst slot, 1,024 / 2,048 | Mean complete, 1,024 / 2,048 | Signatures missing at 8.0 s, 1,024 / 2,048 | Last needed p99, 1,024 / 2,048 | Slots under 99 %, 1,024 / 2,048 | Upload 4–8 s / 4–5 s, % of link (1,024) | PQ sends dropped after 1 s (1,024) |
|---|---|---|---|---|---|---|---|---|
| Fiber | 295 / 591 | 99.32 % (2 of 294) / 99.15 % (5 of 589) | 99.92 / 99.83 % | 0.003 / 0.003 % | 6.24 / 6.21 s | 0 / 0 | 44 / 113 % | 27 % |
| Cable | 224 / 436 | 99.55 % (1 of 223) / 99.54 % (2 of 434) | 99.98 / 99.81 % | 0.000 / 0.009 % | 5.85 / 6.09 s | 0 / 0 | 42 / 111 % | 29 % |
| DSL | 139 / 279 | 97.81 % (3 of 137) / 99.28 % (2 of 276) | 99.23 / 99.78 % | 0.052 / 0.009 % | 6.26 / 6.37 s | 5 / 0 | 38 / 101 % | 32 % |
| Slow CPU (3×) | 152 / 232 | 99.34 % (1 of 151) / 99.57 % (1 of 231) | 99.93 / 99.86 % | 0.003 / 0.003 % | 5.98 / 6.31 s | 0 / 0 | 42 / 108 % | 29 % |
| Normal CPU | 506 / 1,074 | 99.60 % (2 of 502) / 99.35 % (7 of 1,071) | 99.76 / 99.80 % | 0.015 / 0.007 % | 6.13 / 6.18 s | 0 / 0 | 42 / 110 % | 29 % |

### 100/100 with the access links' loss off, seeds 1 and 2 (slots 2–19)

Passes as on 2,048 hosts, by the narrowest margin the rule allows: in the worst slot (slot 14) 6 of 655 home hosts are
incomplete, 99.08 % (2,048 hosts: 99.16 %, 11 of 1,302), and the mean is 99.68 %. 0.013 % of signatures are missing at
8.0 s and the last needed signature arrives by 6.67 s at p99, both as on 2,048 hosts, and late first deliveries stay flat
(0.02 per node-slot in both halves). The downlink carries 42 % of its capacity over 4–8 s and 62 % over 4–5 s (busiest
node 86 % over 4–8 s). DSL hosts are under 99 % in 6 of the 18 slots (worst 97.10 %, 4 of 138; 2,048 hosts: 3 slots) and
slow-CPU hosts in 4 (98.68 %, 2 of 151; 2,048 hosts: 1).

| Class (1,600 signatures per subnet per slot; must hold all at 8.0 s) | Hosts | Complete at 8.0 s: worst slot / mean | Signatures missing at 8.0 s | Last needed signature p50 / p90 / p99 | Upload 4–8 s: Mbit/s mean, busiest (% of link) | Upload 4–5 s mean | Download 4–8 s: mean, busiest | Download 4–5 s mean | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|---|---|---|
| Home 100/100, 1,024 hosts | 658 | 99.08 % (6 of 655) / 99.68 % | 0.013 % | 5.38 / 5.99 / 6.67 s | 34.0 (34 %), 57.6 (58 %) | 75.0 (75 %) | 42.4 (42 %), 86.0 (86 %) | 61.8 (62 %) | 33 % |
| Home 100/100, 2,048 hosts | 1,306 | 99.16 % (11 of 1,302) / 99.72 % | 0.013 % | 5.37 / 6.04 / 6.67 s | 33.2 (33 %), 52.5 (52 %) | 71.4 (71 %) | 41.3 (41 %), 83.0 (83 %) | 59.8 (60 %) | 30 % |
| 1 Gbit, 1,024 hosts | 366 | 99.73 % (1 of 366) / 99.97 % | 0.001 % | 4.97 / 5.32 / 5.81 s | 57.2 (5.7 %), 98.9 (9.9 %) | 173.9 (17 %) | 35.5 (3.6 %), 114.3 (11 %) | 81.0 (8.1 %) | 17 % |
| 1 Gbit, 2,048 hosts | 742 | 99.59 % (3 of 740) / 99.88 % | 0.006 % | 5.14 / 5.28 / 5.73 s | 55.7 (5.6 %), 131.3 (13 %) | 162.2 (16 %) | 35.6 (3.6 %), 75.7 (7.6 %) | 78.6 (7.9 %) | 16 % |

| Home hosts by access type and CPU (1,600 signatures per subnet per slot, all needed at 8.0 s) | Hosts, 1,024 / 2,048 | Worst slot, 1,024 / 2,048 | Mean complete, 1,024 / 2,048 | Signatures missing at 8.0 s, 1,024 / 2,048 | Last needed p99, 1,024 / 2,048 | Slots under 99 %, 1,024 / 2,048 | Upload 4–8 s / 4–5 s, % of link (1,024) | PQ sends dropped after 1 s (1,024) |
|---|---|---|---|---|---|---|---|---|
| Fiber | 295 / 591 | 99.32 % (2 of 294) / 98.98 % (6 of 589) | 99.83 / 99.81 % | 0.007 / 0.008 % | 6.45 / 6.60 s | 0 / 1 | 36 / 83 % | 30 % |
| Cable | 224 / 436 | 99.10 % (2 of 223) / 99.31 % (3 of 435) | 99.75 / 99.68 % | 0.015 / 0.018 % | 6.69 / 6.56 s | 0 / 0 | 33 / 74 % | 34 % |
| DSL | 139 / 279 | 97.10 % (4 of 138) / 98.57 % (4 of 279) | 99.23 / 99.58 % | 0.022 / 0.015 % | 6.92 / 6.80 s | 6 / 3 | 30 / 61 % | 37 % |
| Slow CPU (3×) | 152 / 232 | 98.68 % (2 of 151) / 98.70 % (3 of 231) | 99.52 / 99.69 % | 0.019 / 0.013 % | 6.60 / 6.71 s | 4 / 1 | 32 / 71 % | 34 % |
| Normal CPU | 506 / 1,074 | 99.20 % (4 of 503) / 99.25 % (8 of 1,071) | 99.72 / 99.73 % | 0.011 / 0.013 % | 6.68 / 6.66 s | 0 / 0 | 34 / 76 % | 32 % |

Seed 2 draws another network of 1,024 hosts (364 on 1 Gbit; 660 home hosts: 307 fiber, 201 cable, 152 DSL; 129 slow CPUs)
and another publisher schedule (229 messages per slot). It gives the same result as seed 1, and as seed 2 on 2,048 hosts:
home worst slot 99.39 % (4 of 656; 2,048 hosts: 99.39 %, 8 of 1,319), mean 99.74 %, 0.007 % of signatures missing at
8.0 s, last needed signature at 6.57 s at p99, and no build-up of late first deliveries (0.02 and 0.01 per node-slot). DSL
hosts are under 99 % in 2 of the 18 slots (98.68 %, 2 of 152; 2,048 hosts: 8), and every other subgroup stays above it in
every slot. 100/100 therefore passes on both seeds on both networks.

| Class (1,600 signatures per subnet per slot; must hold all at 8.0 s) | Hosts | Complete at 8.0 s: worst slot / mean | Signatures missing at 8.0 s | Last needed signature p50 / p90 / p99 | Upload 4–8 s: Mbit/s mean, busiest (% of link) | Upload 4–5 s mean | Download 4–8 s: mean, busiest | Download 4–5 s mean | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|---|---|---|
| Home 100/100, seed 2, 1,024 hosts | 660 | 99.39 % (4 of 656) / 99.74 % | 0.007 % | 5.36 / 5.98 / 6.57 s | 33.6 (34 %), 53.9 (54 %) | 75.2 (75 %) | 41.9 (42 %), 81.9 (82 %) | 62.9 (63 %) | 32 % |
| Home 100/100, seed 2, 2,048 hosts | 1,326 | 99.39 % (8 of 1,319) / 99.73 % | 0.013 % | 5.38 / 6.01 / 6.66 s | 34.2 (34 %), 58.4 (58 %) | 73.4 (73 %) | 42.3 (42 %), 83.0 (83 %) | 60.9 (61 %) | 31 % |
| 1 Gbit, seed 2, 1,024 hosts | 364 | 100.00 % (0 of 359) / 100.00 % | 0.000 % | 5.09 / 5.28 / 5.67 s | 56.2 (5.6 %), 104.7 (10 %) | 170.9 (17 %) | 35.1 (3.5 %), 84.9 (8.5 %) | 81.4 (8.1 %) | 16 % |
| 1 Gbit, seed 2, 2,048 hosts | 722 | 99.58 % (3 of 718) / 99.77 % | 0.005 % | 4.96 / 5.24 / 5.97 s | 56.8 (5.7 %), 114.5 (11 %) | 169.0 (17 %) | 35.8 (3.6 %), 91.1 (9.1 %) | 82.9 (8.3 %) | 17 % |

| Home hosts by access type and CPU (seed 2; 1,600 signatures per subnet per slot, all needed at 8.0 s) | Hosts, 1,024 / 2,048 | Worst slot, 1,024 / 2,048 | Mean complete, 1,024 / 2,048 | Signatures missing at 8.0 s, 1,024 / 2,048 | Last needed p99, 1,024 / 2,048 | Slots under 99 %, 1,024 / 2,048 | Upload 4–8 s / 4–5 s, % of link (1,024) | PQ sends dropped after 1 s (1,024) |
|---|---|---|---|---|---|---|---|---|
| Fiber | 307 / 615 | 99.35 % (2 of 306) / 99.34 % (4 of 610) | 99.65 / 99.87 % | 0.009 / 0.003 % | 6.35 / 6.44 s | 0 / 0 | 36 / 83 % | 29 % |
| Cable | 201 / 418 | 100.00 % (0 of 196) / 99.52 % (2 of 417) | 100.00 / 99.87 % | 0.000 / 0.005 % | 6.55 / 6.68 s | 0 / 0 | 33 / 74 % | 33 % |
| DSL | 152 / 293 | 98.68 % (2 of 152) / 98.63 % (4 of 292) | 99.56 / 99.26 % | 0.014 / 0.047 % | 6.69 / 6.97 s | 2 / 8 | 30 / 60 % | 37 % |
| Slow CPU (3×) | 129 / 252 | 99.22 % (1 of 128) / 98.80 % (3 of 251) | 99.70 / 99.65 % | 0.011 / 0.018 % | 6.62 / 6.80 s | 0 / 2 | 32 / 71 % | 34 % |
| Normal CPU | 531 / 1,074 | 99.43 % (3 of 528) / 99.53 % (5 of 1,067) | 99.75 / 99.76 % | 0.006 / 0.012 % | 6.56 / 6.61 s | 0 / 0 | 34 / 76 % | 31 % |

### 50/100 with the access links' loss off (slots 2–19)

Fails clearly, as on 2,048 hosts, and in the same way. The home class is 81–89 % complete in every slot from 2 (worst
81.04 %, 124 of 654; 2,048 hosts: 77.82 %), 86.20 % on average (86.37 %), 0.315 % of signatures are missing at 8.0 s and the
last needed signature arrives at 9.85 s at p99. Late first deliveries are frequent (0.51 per node-slot) but do not build up
(0.53 in the first half, 0.50 in the second). The downlink again stays below its capacity while the demand is above it: it
carries 64 % of its capacity over 4–5 s and over 4–8 s (busiest node 90 %), the pattern that the 512-host diagnostic of the
2,048-host study traced to drops in Shadow's CoDel downlink queue. The worst slot is far below 95 %, so the diagnostic was
not repeated. The smallest download that passes at 100 up is 100 Mbit/s on both networks.

| Class (1,600 signatures per subnet per slot; must hold all at 8.0 s) | Hosts | Complete at 8.0 s: worst slot / mean | Signatures missing at 8.0 s | Last needed signature p50 / p90 / p99 | Upload 4–8 s: Mbit/s mean, busiest (% of link) | Upload 4–5 s mean | Download 4–8 s: mean, busiest | Download 4–5 s mean | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|---|---|---|
| Home 50/100, 1,024 hosts | 658 | 81.04 % (124 of 654) / 86.20 % | 0.315 % | 6.77 / 8.21 / 9.85 s | 31.2 (31 %), 52.5 (52 %) | 45.9 (46 %) | 32.2 (64 %), 45.0 (90 %) | 32.2 (64 %) | 43 % |
| Home 50/100, 2,048 hosts | 1,306 | 77.82 % (289 of 1,303) / 86.37 % | 0.283 % | 6.78 / 8.21 / 9.79 s | 30.3 (30 %), 50.3 (50 %) | 43.4 (43 %) | 31.8 (64 %), 44.8 (90 %) | 31.3 (63 %) | 42 % |
| 1 Gbit, 1,024 hosts | 366 | 99.73 % (1 of 366) / 99.92 % | 0.002 % | 5.02 / 5.32 / 6.25 s | 55.2 (5.5 %), 100.8 (10 %) | 148.2 (15 %) | 34.5 (3.4 %), 100.6 (10 %) | 75.2 (7.5 %) | 35 % |
| 1 Gbit, 2,048 hosts | 742 | 99.46 % (4 of 739) / 99.77 % | 0.013 % | 5.10 / 5.23 / 6.44 s | 53.8 (5.4 %), 120.2 (12 %) | 140.8 (14 %) | 33.8 (3.4 %), 72.9 (7.3 %) | 71.7 (7.2 %) | 33 % |

| Home hosts by access type and CPU (1,600 signatures per subnet per slot, all needed at 8.0 s) | Hosts, 1,024 / 2,048 | Worst slot, 1,024 / 2,048 | Mean complete, 1,024 / 2,048 | Signatures missing at 8.0 s, 1,024 / 2,048 | Last needed p99, 1,024 / 2,048 | Slots under 99 %, 1,024 / 2,048 | Upload 4–8 s / 4–5 s, % of link (1,024) | PQ sends dropped after 1 s (1,024) |
|---|---|---|---|---|---|---|---|---|
| Fiber | 295 / 591 | 83.62 % (48 of 293) / 79.63 % (120 of 589) | 88.34 / 88.86 % | 0.272 / 0.202 % | 9.75 / 9.71 s | 18 / 18 | 33 / 51 % | 42 % |
| Cable | 224 / 436 | 79.37 % (46 of 223) / 77.01 % (100 of 435) | 87.19 / 85.86 % | 0.265 / 0.304 % | 9.86 / 9.77 s | 18 / 18 | 31 / 45 % | 44 % |
| DSL | 139 / 279 | 72.99 % (37 of 137) / 75.27 % (69 of 279) | 80.03 / 81.89 % | 0.489 / 0.418 % | 10.03 / 9.96 s | 18 / 18 | 28 / 37 % | 45 % |
| Slow CPU (3×) | 152 / 232 | 81.58 % (28 of 152) / 78.88 % (49 of 232) | 86.69 / 86.53 % | 0.305 / 0.315 % | 10.04 / 10.07 s | 18 / 18 | 30 / 44 % | 44 % |
| Normal CPU | 506 / 1,074 | 79.72 % (102 of 503) / 76.77 % (249 of 1,072) | 86.05 / 86.33 % | 0.318 / 0.276 % | 9.48 / 9.44 s | 18 / 18 | 32 / 46 % | 43 % |

### 1000/100 and 1000/200 with the usual access loss (slots 2–19)

With the modelled loss on the home access lines (fiber 0.05 %, cable 0.1 %, DSL 0.25 % per direction), 1000/100 fails on
1,024 hosts as on 2,048. The home class is 80.6–87.3 % complete in every slot from 2 (worst 80.61 %, 127 of 655; 2,048
hosts: 78.83 %) and 84.13 % on average (80.63 %); 1.40 % of signatures are missing at 8.0 s (1.60 %), and the last needed
signature arrives at 12.9 s at p99. Late first deliveries are frequent and rise a little, as on 2,048 hosts (2.31 per
node-slot in the first half and 2.54 in the second; 2,048 hosts: 3.28 and 4.00). Bandwidth is not what fails these hosts:
they upload 27 % of their link over 4–8 s and 56 % over 4–5 s, and the same link with the access loss off passes (99.69 %).
Completion follows the loss of the access line, as on 2,048 hosts: fiber 97.6 %, cable 86.2 % and DSL 52.1 % on average.

| Class (1,600 signatures per subnet per slot; must hold all at 8.0 s) | Hosts | Complete at 8.0 s: worst slot / mean | Signatures missing at 8.0 s | Last needed signature p50 / p90 / p99 | Upload 4–8 s: Mbit/s mean, busiest (% of link) | Upload 4–5 s mean | Download 4–8 s: mean, busiest | Download 4–5 s mean | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|---|---|---|
| Home 1000/100, 1,024 hosts | 658 | 80.61 % (127 of 655) / 84.13 % | 1.395 % | 5.61 / 8.67 / 12.88 s | 27.2 (27 %), 58.8 (59 %) | 56.1 (56 %) | 35.1 (3.5 %), 92.6 (9.3 %) | 47.8 (4.8 %) | 47 % |
| Home 1000/100, 2,048 hosts | 1,306 | 78.83 % (275 of 1,299) / 80.63 % | 1.595 % | 5.68 / 9.10 / 13.42 s | 25.6 (26 %), 56.4 (56 %) | 49.1 (49 %) | 33.3 (3.3 %), 87.5 (8.7 %) | 43.7 (4.4 %) | 46 % |
| 1 Gbit, 1,024 hosts | 366 | 99.45 % (2 of 366) / 99.92 % | 0.004 % | 5.00 / 5.37 / 6.16 s | 56.4 (5.6 %), 100.9 (10 %) | 165.2 (16 %) | 32.9 (3.3 %), 96.5 (9.6 %) | 75.6 (7.6 %) | 24 % |
| 1 Gbit, 2,048 hosts | 742 | 99.59 % (3 of 739) / 99.79 % | 0.007 % | 5.05 / 5.27 / 6.31 s | 54.7 (5.5 %), 128.1 (13 %) | 154.2 (15 %) | 32.4 (3.2 %), 68.4 (6.8 %) | 71.7 (7.2 %) | 24 % |

| Home hosts by access type and CPU (1,600 signatures per subnet per slot, all needed at 8.0 s) | Hosts, 1,024 / 2,048 | Worst slot, 1,024 / 2,048 | Mean complete, 1,024 / 2,048 | Signatures missing at 8.0 s, 1,024 / 2,048 | Last needed p99, 1,024 / 2,048 | Slots under 99 %, 1,024 / 2,048 | Upload 4–8 s / 4–5 s, % of link (1,024) | PQ sends dropped after 1 s (1,024) |
|---|---|---|---|---|---|---|---|---|
| Fiber | 295 / 591 | 95.92 % (12 of 294) / 97.27 % (16 of 587) | 97.58 / 98.29 % | 0.141 / 0.086 % | 9.15 / 9.06 s | 17 / 18 | 34 / 79 % | 40 % |
| Cable | 224 / 436 | 81.61 % (41 of 223) / 74.08 % (113 of 436) | 86.22 / 77.89 % | 0.718 / 1.343 % | 11.06 / 13.10 s | 18 / 18 | 25 / 46 % | 51 % |
| DSL | 139 / 279 | 44.93 % (76 of 138) / 43.37 % (158 of 279) | 52.08 / 47.66 % | 5.165 / 5.175 % | 15.63 / 15.58 s | 18 / 18 | 16 / 24 % | 57 % |
| Slow CPU (3×) | 152 / 232 | 79.61 % (31 of 152) / 78.79 % (49 of 231) | 84.71 / 82.57 % | 1.444 / 1.485 % | 12.67 / 13.68 s | 18 / 18 | 26 / 54 % | 48 % |
| Normal CPU | 506 / 1,074 | 80.91 % (96 of 503) / 78.15 % (234 of 1,071) | 83.95 / 80.22 % | 1.381 / 1.619 % | 12.90 / 13.33 s | 18 / 18 | 28 / 57 % | 47 % |

1000/200 fails the same way: worst slot 83.82 % (106 of 655; 2,048 hosts: 77.88 %), mean 85.78 % (81.29 %), 1.12 % of
signatures missing at 8.0 s (1.44 %), last needed signature at 12.3 s at p99. Doubling the upload changes almost nothing,
as on 2,048 hosts: the home uplinks are 14 % busy over 4–8 s. Late first deliveries stay flat (1.89 and 1.90 per node-slot
in the two halves; 2,048 hosts: 2.85 and 3.62).

| Class (1,600 signatures per subnet per slot; must hold all at 8.0 s) | Hosts | Complete at 8.0 s: worst slot / mean | Signatures missing at 8.0 s | Last needed signature p50 / p90 / p99 | Upload 4–8 s: Mbit/s mean, busiest (% of link) | Upload 4–5 s mean | Download 4–8 s: mean, busiest | Download 4–5 s mean | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|---|---|---|
| Home 1000/200, 1,024 hosts | 658 | 83.82 % (106 of 655) / 85.78 % | 1.116 % | 5.56 / 8.47 / 12.28 s | 27.6 (14 %), 75.7 (38 %) | 60.3 (30 %) | 34.8 (3.5 %), 90.2 (9.0 %) | 50.9 (5.1 %) | 47 % |
| Home 1000/200, 2,048 hosts | 1,306 | 77.88 % (288 of 1,302) / 81.29 % | 1.442 % | 5.61 / 9.02 / 13.06 s | 26.3 (13 %), 70.1 (35 %) | 53.6 (27 %) | 33.4 (3.3 %), 91.1 (9.1 %) | 46.9 (4.7 %) | 45 % |
| 1 Gbit, 1,024 hosts | 366 | 99.45 % (2 of 366) / 99.89 % | 0.001 % | 4.99 / 5.26 / 6.09 s | 55.6 (5.6 %), 102.6 (10 %) | 167.1 (17 %) | 33.2 (3.3 %), 102.1 (10 %) | 78.8 (7.9 %) | 24 % |
| 1 Gbit, 2,048 hosts | 742 | 99.86 % (1 of 739) / 99.92 % | 0.002 % | 5.08 / 5.28 / 6.31 s | 54.4 (5.4 %), 119.6 (12 %) | 157.6 (16 %) | 33.1 (3.3 %), 74.7 (7.5 %) | 76.3 (7.6 %) | 24 % |

| Home hosts by access type and CPU (1,600 signatures per subnet per slot, all needed at 8.0 s) | Hosts, 1,024 / 2,048 | Worst slot, 1,024 / 2,048 | Mean complete, 1,024 / 2,048 | Signatures missing at 8.0 s, 1,024 / 2,048 | Last needed p99, 1,024 / 2,048 | Slots under 99 %, 1,024 / 2,048 | Upload 4–8 s / 4–5 s, % of link (1,024) | PQ sends dropped after 1 s (1,024) |
|---|---|---|---|---|---|---|---|---|
| Fiber | 295 / 591 | 96.59 % (10 of 293) / 97.44 % (15 of 587) | 98.52 / 98.21 % | 0.060 / 0.096 % | 8.52 / 8.93 s | 15 / 18 | 18 / 44 % | 39 % |
| Cable | 224 / 436 | 85.20 % (33 of 223) / 73.17 % (117 of 436) | 88.07 / 78.98 % | 0.536 / 1.119 % | 10.89 / 12.31 s | 18 / 18 | 12 / 23 % | 52 % |
| DSL | 139 / 279 | 49.28 % (70 of 138) / 44.09 % (156 of 279) | 54.90 / 49.17 % | 4.306 / 4.786 % | 15.03 / 15.56 s | 18 / 18 | 8 / 12 % | 59 % |
| Slow CPU (3×) | 152 / 232 | 82.89 % (26 of 152) / 78.35 % (50 of 231) | 87.10 / 82.91 % | 1.056 / 1.370 % | 12.29 / 13.20 s | 18 / 18 | 13 / 28 % | 48 % |
| Normal CPU | 506 / 1,074 | 83.67 % (82 of 502) / 77.78 % (238 of 1,071) | 85.38 / 80.94 % | 1.134 / 1.457 % | 12.26 / 13.06 s | 18 / 18 | 14 / 31 % | 47 % |

### 1000/200 with the access links' loss at a fifth (slots 2–19)

With the home access links losing a fifth of the modelled loss (fiber 0.01 %, cable 0.02 %, DSL 0.05 % per direction;
backbone loss, access latency and jitter unchanged), 1000/200 fails on 1,024 hosts as on 2,048: home worst slot 96.48 % (23
of 654; 2,048 hosts: 95.16 %), mean 97.67 % (96.30 %), 0.119 % of signatures missing at 8.0 s (0.153 %), last needed
signature at 8.96 s at p99. Late first deliveries build up mildly, as on 2,048 hosts (0.17 → 0.23 per node-slot from the
first to the second half; 0.27 → 0.36). DSL hosts fail clearly (worst slot 85.51 %, 20 of 138, under 99 % in every slot).
Fiber and cable hosts are at the bar: fiber is under 99 % in 1 of the 18 slots (98.98 %, 3 of 293, where the bar allows 2)
and cable in 2 (worst 98.21 %, 4 of 223). On 2,048 hosts fiber stayed above the bar in every slot and cable was under it in
16. Fiber's mean completion and missing signatures are the same on both networks (99.74 against 99.67 %; 0.009 against
0.011 %), so its one slot under the bar is within chance; the run was not repeated with seed 2, because the home class's
verdict is the same as on 2,048 hosts. Cable does better on 1,024 hosts (99.43 % against 98.23 % on average).

| Class (1,600 signatures per subnet per slot; must hold all at 8.0 s) | Hosts | Complete at 8.0 s: worst slot / mean | Signatures missing at 8.0 s | Last needed signature p50 / p90 / p99 | Upload 4–8 s: Mbit/s mean, busiest (% of link) | Upload 4–5 s mean | Download 4–8 s: mean, busiest | Download 4–5 s mean | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|---|---|---|
| Home 1000/200, 1,024 hosts | 658 | 96.48 % (23 of 654) / 97.67 % | 0.119 % | 5.03 / 5.85 / 8.96 s | 34.4 (17 %), 66.0 (33 %) | 95.1 (48 %) | 40.8 (4.1 %), 109.0 (11 %) | 79.8 (8.0 %) | 29 % |
| Home 1000/200, 2,048 hosts | 1,306 | 95.16 % (63 of 1,301) / 96.30 % | 0.153 % | 5.14 / 6.12 / 9.47 s | 33.0 (16 %), 71.9 (36 %) | 84.9 (42 %) | 39.2 (3.9 %), 105.4 (10 %) | 72.5 (7.2 %) | 30 % |
| 1 Gbit, 1,024 hosts | 366 | 100.00 % (0 of 366) / 100.00 % | 0.000 % | 4.93 / 5.18 / 5.64 s | 53.9 (5.4 %), 92.2 (9.2 %) | 179.2 (18 %) | 35.7 (3.6 %), 81.7 (8.2 %) | 89.8 (9.0 %) | 14 % |
| 1 Gbit, 2,048 hosts | 742 | 99.59 % (3 of 739) / 99.93 % | 0.001 % | 5.07 / 5.17 / 5.99 s | 53.1 (5.3 %), 110.3 (11 %) | 169.4 (17 %) | 35.8 (3.6 %), 88.0 (8.8 %) | 86.3 (8.6 %) | 15 % |

| Home hosts by access type and CPU (1,600 signatures per subnet per slot, all needed at 8.0 s) | Hosts, 1,024 / 2,048 | Worst slot, 1,024 / 2,048 | Mean complete, 1,024 / 2,048 | Signatures missing at 8.0 s, 1,024 / 2,048 | Last needed p99, 1,024 / 2,048 | Slots under 99 %, 1,024 / 2,048 | Upload 4–8 s / 4–5 s, % of link (1,024) | PQ sends dropped after 1 s (1,024) |
|---|---|---|---|---|---|---|---|---|
| Fiber | 295 / 591 | 98.98 % (3 of 293) / 99.32 % (4 of 587) | 99.74 / 99.67 % | 0.009 / 0.011 % | 6.32 / 6.39 s | 1 / 0 | 20 / 61 % | 21 % |
| Cable | 224 / 436 | 98.21 % (4 of 223) / 96.79 % (14 of 436) | 99.43 / 98.23 % | 0.020 / 0.075 % | 6.64 / 8.67 s | 2 / 16 | 17 / 45 % | 30 % |
| DSL | 139 / 279 | 85.51 % (20 of 138) / 81.36 % (52 of 279) | 90.44 / 86.18 % | 0.516 / 0.572 % | 10.63 / 11.67 s | 18 / 18 | 12 / 24 % | 46 % |
| Slow CPU (3×) | 152 / 232 | 96.05 % (6 of 152) / 94.81 % (12 of 231) | 97.58 / 96.25 % | 0.113 / 0.145 % | 9.69 / 10.12 s | 16 / 18 | 16 / 44 % | 31 % |
| Normal CPU | 506 / 1,074 | 96.22 % (19 of 503) / 95.14 % (52 of 1,070) | 97.70 / 96.31 % | 0.121 / 0.154 % | 8.90 / 9.30 s | 16 / 18 | 18 / 49 % | 29 % |

With the full-loss run and 1000/100 with the access loss off (where the upload does not bind either), this gives completion
against the access loss per direction on both networks:

| Home hosts by access type and access loss (1,600 signatures per subnet per slot, all needed at 8.0 s; slots 2–19) | Access loss per direction | Worst slot / mean, 1,024 hosts | Worst slot / mean, 2,048 hosts | Signatures missing at 8.0 s, 1,024 / 2,048 | Last needed signature p99, 1,024 / 2,048 |
|---|---|---|---|---|---|
| Fiber, loss off (1000/100) | 0 | 99.66 / 99.98 % | 99.66 / 99.92 % | 0.000 / 0.002 % | 5.72 / 5.87 s |
| Cable, loss off (1000/100) | 0 | 99.55 / 99.78 % | 99.54 / 99.80 % | 0.008 / 0.007 % | 5.74 / 5.71 s |
| DSL, loss off (1000/100) | 0 | 98.55 / 99.72 % | 99.28 / 99.60 % | 0.003 / 0.017 % | 5.81 / 6.16 s |
| Fiber, a fifth (1000/200) | 0.01 % | 98.98 / 99.74 % | 99.32 / 99.67 % | 0.009 / 0.011 % | 6.32 / 6.39 s |
| Cable, a fifth | 0.02 % | 98.21 / 99.43 % | 96.79 / 98.23 % | 0.020 / 0.075 % | 6.64 / 8.67 s |
| DSL, a fifth | 0.05 % | 85.51 / 90.44 % | 81.36 / 86.18 % | 0.516 / 0.572 % | 10.63 / 11.67 s |
| Fiber, full (1000/200) | 0.05 % | 96.59 / 98.52 % | 97.44 / 98.21 % | 0.060 / 0.096 % | 8.52 / 8.93 s |
| Cable, full | 0.1 % | 85.20 / 88.07 % | 73.17 / 78.98 % | 0.536 / 1.119 % | 10.89 / 12.31 s |
| DSL, full | 0.25 % | 49.28 / 54.90 % | 44.09 / 49.17 % | 4.306 / 4.786 % | 15.03 / 15.56 s |

At the same loss of 0.05 % per direction, DSL hosts again do worse than fiber hosts (90.4 against 98.5 % complete on
average; 2,048 hosts: 86.2 against 98.2 %), so on both networks the longer access delay and jitter amplify the loss. In all
three runs with access loss, the 1,024-host network completes a few points more than the 2,048-host one (on average 84.1
against 80.6 % at 1000/100, 85.8 against 81.3 % at 1000/200 and 97.7 against 96.3 % at a fifth of the loss), mostly on
cable and DSL hosts. One plausible reason, not tested: a node on 1,024 hosts needs fewer messages per slot (211 instead
of 302 on average, because each publisher bundles more of its own signatures), so a lossy line has fewer to miss.
Per message, both networks miss about the same share at 8.0 s (1.22 against 1.28 % at 1000/100, 0.97 against 1.14 % at
1000/200, 0.10 against 0.12 % at a fifth of the loss), which fits that reason. The verdicts are the
same: with the modelled access loss no home link passes, and at a fifth of it fiber and cable hosts are at the bar while DSL
hosts fail.

### 100/100 with PQ verification five times slower (slots 2–19)

At 100/100 with the access loss off, each PQ signature costs 2,000 µs to verify instead of 400 (6,000 µs on the 152 home
hosts with a slow CPU; block, column, aggregate and sync-message costs unchanged). As on 2,048 hosts, the home class passes
by a wider margin than at 400 µs: worst slot 99.85 % (1 of 653; 2,048 hosts: 99.62 %), mean 99.94 %, 0.002 % of signatures
missing at 8.0 s, and late first deliveries stay flat (0.00 and 0.01 per node-slot). Slow-CPU hosts become CPU-bound as on
2,048 hosts: they hold 30 % of the slot's signatures at 5 s and 71 % at 6 s, and finish in a narrow band at 6.66 / 6.81 /
6.93 s (p50 / p90 / p99; 2,048 hosts: 6.66 / 6.74 / 6.89 s), about 1.1 s before the deadline. That band is set by their own
work (1,600 signatures at 6 ms on four workers take 2.4 s from the burst at 4.0–4.5 s), so it does not depend on the
network size. Normal-CPU hosts finish by 6.61 s at p99. Slower verification again spreads the forwarding out: home hosts
hand TCP 59 % of their uplink over 4–5 s instead of 75 %, and slow-CPU hosts forward less (14 % of their uplink over 4–8 s).

| Class (1,600 signatures per subnet per slot; must hold all at 8.0 s) | Hosts | Complete at 8.0 s: worst slot / mean | Signatures missing at 8.0 s | Last needed signature p50 / p90 / p99 | Upload 4–8 s: Mbit/s mean, busiest (% of link) | Upload 4–5 s mean | Download 4–8 s: mean, busiest | Download 4–5 s mean | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|---|---|---|
| Home 100/100, 1,024 hosts | 658 | 99.85 % (1 of 653) / 99.94 % | 0.002 % | 5.58 / 6.68 / 6.88 s | 28.3 (28 %), 59.3 (59 %) | 59.0 (59 %) | 37.2 (37 %), 82.0 (82 %) | 53.8 (54 %) | 23 % |
| Home 100/100, 2,048 hosts | 1,306 | 99.62 % (5 of 1,302) / 99.87 % | 0.003 % | 5.53 / 6.66 / 6.82 s | 29.3 (29 %), 54.1 (54 %) | 59.5 (60 %) | 37.8 (38 %), 79.2 (79 %) | 53.4 (53 %) | 23 % |
| 1 Gbit, 1,024 hosts | 366 | 99.73 % (1 of 366) / 99.94 % | 0.002 % | 5.17 / 5.54 / 6.09 s | 51.6 (5.2 %), 96.4 (9.6 %) | 147.0 (15 %) | 29.8 (3.0 %), 105.9 (11 %) | 60.1 (6.0 %) | 12 % |
| 1 Gbit, 2,048 hosts | 742 | 99.86 % (1 of 739) / 99.96 % | 0.001 % | 5.35 / 5.48 / 6.03 s | 51.6 (5.2 %), 120.7 (12 %) | 137.1 (14 %) | 31.1 (3.1 %), 83.8 (8.4 %) | 59.2 (5.9 %) | 12 % |

| Home hosts by access type and CPU (1,600 signatures per subnet per slot, all needed at 8.0 s) | Hosts, 1,024 / 2,048 | Worst slot, 1,024 / 2,048 | Mean complete, 1,024 / 2,048 | Signatures missing at 8.0 s, 1,024 / 2,048 | Last needed p99, 1,024 / 2,048 | Slots under 99 %, 1,024 / 2,048 | Upload 4–8 s / 4–5 s, % of link (1,024) | PQ sends dropped after 1 s (1,024) |
|---|---|---|---|---|---|---|---|---|
| Fiber | 295 / 591 | 99.66 % (1 of 293) / 99.66 % (2 of 589) | 99.94 / 99.91 % | 0.002 / 0.001 % | 6.84 / 6.80 s | 0 / 0 | 30 / 64 % | 21 % |
| Cable | 224 / 436 | 99.55 % (1 of 223) / 99.77 % (1 of 434) | 99.90 / 99.89 % | 0.003 / 0.003 % | 6.89 / 6.80 s | 0 / 0 | 28 / 58 % | 23 % |
| DSL | 139 / 279 | 100.00 % (0 of 137) / 99.28 % (2 of 279) | 100.00 / 99.74 % | 0.000 / 0.007 % | 6.89 / 6.88 s | 0 / 0 | 26 / 50 % | 27 % |
| Slow CPU (3×) | 152 / 232 | 100.00 % (0 of 151) / 99.57 % (1 of 231) | 100.00 / 99.98 % | 0.000 / 0.000 % | 6.93 / 6.89 s | 0 / 0 | 14 / 23 % | 22 % |
| Normal CPU | 506 / 1,074 | 99.80 % (1 of 502) / 99.63 % (4 of 1,071) | 99.92 / 99.84 % | 0.003 / 0.004 % | 6.61 / 6.68 s | 0 / 0 | 33 / 70 % | 23 % |

### EIP-7870 links with the usual access loss (slots 2–19; 2,048 hosts: slots 2–14)

The links of the earlier post: 50/25 Mbit/s for the 499 home hosts with validators and 50/15 for the 159 without, with the
usual access loss, the 1,024-host counterpart of `Q2048x20-m1600-s1`. That 2,048-host run reached the 235 GiB memory cap in
slot 16 and is analysed to slot 14; the 1,024-host run completes all 20 slots at 120 GiB. Both home classes fail as on 2,048
hosts, by as much: 50/15 hosts are complete in 26–43 % of node-slots per slot from slot 2 (worst 25.79 %, 118 of 159; 2,048
hosts: 23.33 %) and 50/25 hosts in 53–64 % (worst 52.73 %; 2,048 hosts: 53.29 %), and 11.6 and 3.7 % of signatures are
missing at 8.0 s (2,048 hosts: 12.8 and 4.1 %). The uplink is the bottleneck, as before: 50/15 hosts hand TCP 122 % of their
link over 4–8 s and 160 % over 4–5 s, 50/25 hosts 92 and 127 %. Late first deliveries are frequent and do not build up
(50/15: 18.1 per node-slot in the first half, 18.9 in the second; 50/25: 6.6 and 6.4).

The 1 Gbit class fails narrowly, as on 2,048 hosts: it is under 99 % in 2 of the 18 slots (slots 3 and 14, 98.91 %, 4 of 366
where the bar allows 3; mean 99.38 %), against 1 of 13 on 2,048 hosts (slot 2, 98.92 %, 8 of 739; mean 99.54 %). Over slots
2–14 only, the 1,024-host run gives the same picture (worst slot / mean: 50/15 25.79 / 31.35 %, 50/25 52.73 / 58.22 %,
1 Gbit 98.91 / 99.29 %).

| Class (1,600 signatures per subnet per slot; must hold all at 8.0 s) | Hosts | Complete at 8.0 s: worst slot / mean | Signatures missing at 8.0 s | Last needed signature p50 / p90 / p99 | Upload 4–8 s: Mbit/s mean, busiest (% of link) | Upload 4–5 s mean | Download 4–8 s: mean, busiest | Download 4–5 s mean | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|---|---|---|
| 50/15, 1,024 hosts | 159 | 25.79 % (118 of 159) / 30.64 % | 11.576 % | 8.72 / 14.92 / 18.47 s | 18.2 (122 %), 28.5 (190 %) | 24.1 (160 %) | 21.9 (44 %), 38.6 (77 %) | 18.3 (36 %) | 49 % |
| 50/15, 2,048 hosts | 330 | 23.33 % (253 of 330) / 28.51 % | 12.772 % | 8.91 / 15.36 / 18.53 s | 17.2 (115 %), 25.7 (171 %) | 21.7 (145 %) | 20.6 (41 %), 40.7 (81 %) | 17.1 (34 %) | 49 % |
| 50/25, 1,024 hosts | 499 | 52.73 % (234 of 495) / 58.38 % | 3.711 % | 7.51 / 11.03 / 15.95 s | 23.0 (92 %), 35.7 (143 %) | 31.7 (127 %) | 25.7 (51 %), 42.0 (84 %) | 23.5 (47 %) | 53 % |
| 50/25, 2,048 hosts | 976 | 53.29 % (455 of 974) / 55.79 % | 4.090 % | 7.57 / 11.38 / 16.32 s | 21.3 (85 %), 34.9 (140 %) | 27.4 (110 %) | 25.1 (50 %), 42.0 (84 %) | 22.4 (45 %) | 52 % |
| 1 Gbit, 1,024 hosts | 366 | 98.91 % (4 of 366) / 99.38 % | 0.029 % | 5.05 / 5.51 / 7.20 s | 56.7 (5.7 %), 104.6 (10 %) | 141.9 (14 %) | 30.0 (3.0 %), 85.7 (8.6 %) | 70.1 (7.0 %) | 39 % |
| 1 Gbit, 2,048 hosts | 742 | 98.92 % (8 of 739) / 99.54 % | 0.020 % | 5.16 / 5.40 / 6.95 s | 53.6 (5.4 %), 130.0 (13 %) | 131.7 (13 %) | 29.3 (2.9 %), 54.5 (5.5 %) | 66.5 (6.7 %) | 39 % |

| Home hosts by access type and CPU (1,600 signatures per subnet per slot, all needed at 8.0 s) | Hosts, 1,024 / 2,048 | Worst slot, 1,024 / 2,048 | Mean complete, 1,024 / 2,048 | Signatures missing at 8.0 s, 1,024 / 2,048 | Last needed p99, 1,024 / 2,048 | Slots under 99 %, 1,024 (of 18) / 2,048 (of 13) | Upload 4–8 s / 4–5 s, % of link (1,024) | PQ sends dropped after 1 s (1,024) |
|---|---|---|---|---|---|---|---|---|
| 50/15, Fiber | 66 / 143 | 25.76 % (49 of 66) / 23.78 % (109 of 143) | 34.34 / 31.75 % | 8.754 / 11.596 % | 17.27 / 19.00 s | 18 / 13 | 131 / 184 % | 48 % |
| 50/25, Fiber | 229 / 448 | 56.83 % (98 of 227) / 59.33 % (181 of 445) | 63.55 / 62.29 % | 2.642 / 2.469 % | 14.83 / 14.79 s | 18 / 13 | 99 / 139 % | 51 % |
| 50/15, Cable | 58 / 116 | 13.79 % (50 of 58) / 19.83 % (93 of 116) | 27.68 / 25.53 % | 11.618 / 12.783 % | 18.80 / 18.51 s | 18 / 13 | 122 / 156 % | 48 % |
| 50/25, Cable | 166 / 320 | 52.12 % (79 of 165) / 51.25 % (156 of 320) | 59.76 / 55.58 % | 2.848 / 3.850 % | 15.60 / 16.33 s | 18 / 13 | 94 / 133 % | 53 % |
| 50/15, DSL | 35 / 71 | 20.00 % (28 of 35) / 22.54 % (55 of 71) | 28.57 / 26.87 % | 16.828 / 15.119 % | 19.38 / 18.19 s | 18 / 13 | 104 / 125 % | 52 % |
| 50/25, DSL | 104 / 208 | 36.89 % (65 of 103) / 37.50 % (130 of 208) | 44.73 / 42.20 % | 7.466 / 7.932 % | 17.45 / 17.36 s | 18 / 13 | 74 / 90 % | 57 % |
| 50/15, Slow CPU (3×) | 35 / 55 | 22.86 % (27 of 35) / 14.55 % (47 of 55) | 29.52 / 25.87 % | 12.701 / 14.554 % | 18.91 / 18.27 s | 18 / 13 | 118 / 145 % | 48 % |
| 50/25, Slow CPU (3×) | 117 / 177 | 53.85 % (54 of 117) / 56.25 % (77 of 176) | 61.25 / 59.52 % | 3.735 / 3.789 % | 16.27 / 15.93 s | 18 / 13 | 91 / 129 % | 54 % |
| 50/15, Normal CPU | 124 / 275 | 24.19 % (94 of 124) / 25.09 % (206 of 275) | 30.96 / 29.04 % | 11.259 / 12.415 % | 18.41 / 18.65 s | 18 / 13 | 123 / 165 % | 49 % |
| 50/25, Normal CPU | 382 / 799 | 51.85 % (182 of 378) / 51.69 % (385 of 797) | 57.50 / 54.97 % | 3.704 / 4.157 % | 15.79 / 16.35 s | 18 / 13 | 92 / 126 % | 53 % |

### 80 % of hosts on 1 Gbit, EIP-7870 links, usual access loss (slots 2–19)

As the run before, with 75 % instead of 20 % of the hosts with 8 validators or fewer on 1 Gbit (`--fast-share 0.75`): 818
of the 1,024 hosts (80 %) are on 1 Gbit, and 206 home hosts remain, 165 on 50/25 and 41 on 50/15. The 1,024-host counterpart
of `Q2048x20-m1600-fs75-s1`. As on 2,048 hosts, more fast peers do not rescue the home nodes: 50/15 hosts reach 22–49 %
completion per slot from slot 2 (worst 21.95 %, 32 of 41; 2,048 hosts: 23.21 %) and 50/25 hosts 48–73 % (worst 48.48 %;
2,048 hosts: 52.88 %), with 8.3 and 2.2 % of signatures missing at 8.0 s (2,048 hosts: 7.3 and 2.3 %). Their uplinks are
still the bottleneck: 50/15 hosts hand TCP 117 % of their link over 4–8 s and 176 % over 4–5 s, 50/25 hosts 77 and 119 %.
Late first deliveries are frequent and rise a little, as on 2,048 hosts (50/15: 11.0 per node-slot in the first half, 13.5
in the second; 2,048 hosts: 13.1 and 14.6). The 1 Gbit hosts pass (worst slot 99.51 %, 4 of 816; mean 99.85 %), as on
2,048 hosts (99.82 %).

| Class (1,600 signatures per subnet per slot; must hold all at 8.0 s) | Hosts | Complete at 8.0 s: worst slot / mean | Signatures missing at 8.0 s | Last needed signature p50 / p90 / p99 | Upload 4–8 s: Mbit/s mean, busiest (% of link) | Upload 4–5 s mean | Download 4–8 s: mean, busiest | Download 4–5 s mean | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|---|---|---|
| 50/15, 1,024 hosts | 41 | 21.95 % (32 of 41) / 39.30 % | 8.320 % | 8.13 / 12.82 / 17.02 s | 17.5 (117 %), 27.6 (184 %) | 26.4 (176 %) | 24.3 (48 %), 41.4 (83 %) | 23.9 (48 %) | 49 % |
| 50/15, 2,048 hosts | 112 | 23.21 % (86 of 112) / 33.93 % | 7.324 % | 8.48 / 12.35 / 16.20 s | 16.8 (112 %), 28.0 (187 %) | 24.5 (163 %) | 24.5 (49 %), 41.7 (84 %) | 23.9 (48 %) | 45 % |
| 50/25, 1,024 hosts | 165 | 48.48 % (85 of 165) / 62.29 % | 2.216 % | 7.26 / 9.76 / 13.76 s | 19.2 (77 %), 38.7 (155 %) | 29.7 (119 %) | 27.7 (56 %), 43.9 (88 %) | 30.2 (60 %) | 52 % |
| 50/25, 2,048 hosts | 296 | 52.88 % (139 of 295) / 59.11 % | 2.348 % | 7.34 / 10.07 / 14.09 s | 19.0 (76 %), 38.4 (154 %) | 28.9 (116 %) | 27.2 (54 %), 43.5 (87 %) | 28.4 (57 %) | 50 % |
| 1 Gbit, 1,024 hosts | 818 | 99.51 % (4 of 816) / 99.85 % | 0.006 % | 4.92 / 5.11 / 5.97 s | 38.2 (3.8 %), 104.0 (10 %) | 124.8 (12 %) | 31.8 (3.2 %), 109.0 (11 %) | 89.8 (9.0 %) | 28 % |
| 1 Gbit, 2,048 hosts | 1,640 | 99.82 % (3 of 1,633) / 99.92 % | 0.005 % | 4.90 / 5.03 / 5.93 s | 38.6 (3.9 %), 106.4 (11 %) | 125.1 (12 %) | 32.4 (3.2 %), 123.5 (12 %) | 90.8 (9.1 %) | 26 % |

| Home hosts by access type and CPU (1,600 signatures per subnet per slot, all needed at 8.0 s) | Hosts, 1,024 / 2,048 | Worst slot, 1,024 / 2,048 | Mean complete, 1,024 / 2,048 | Signatures missing at 8.0 s, 1,024 / 2,048 | Last needed p99, 1,024 / 2,048 | Slots under 99 %, 1,024 / 2,048 | Upload 4–8 s / 4–5 s, % of link (1,024) | PQ sends dropped after 1 s (1,024) |
|---|---|---|---|---|---|---|---|---|
| 50/15, Fiber | 18 / 52 | 16.67 % (15 of 18) / 21.15 % (41 of 52) | 30.86 / 33.55 % | 10.095 / 6.864 % | 17.67 / 16.26 s | 18 / 18 | 127 / 190 % | 43 % |
| 50/25, Fiber | 66 / 126 | 46.97 % (35 of 66) / 54.76 % (57 of 126) | 65.66 / 61.99 % | 1.712 / 1.817 % | 13.85 / 12.83 s | 18 / 18 | 86 / 137 % | 47 % |
| 50/15, Cable | 11 / 33 | 9.09 % (10 of 11) / 24.24 % (25 of 33) | 37.37 / 38.22 % | 7.266 / 5.785 % | 16.38 / 15.48 s | 18 / 18 | 120 / 175 % | 47 % |
| 50/25, Cable | 62 / 113 | 50.00 % (31 of 62) / 51.79 % (54 of 112) | 64.25 / 61.15 % | 1.492 / 1.921 % | 12.62 / 14.07 s | 18 / 18 | 77 / 116 % | 52 % |
| 50/15, DSL | 12 / 27 | 33.33 % (8 of 12) / 22.22 % (21 of 27) | 53.70 / 29.42 % | 6.623 / 10.090 % | 16.37 / 16.89 s | 18 / 18 | 97 / 154 % | 57 % |
| 50/25, DSL | 37 / 57 | 43.24 % (21 of 37) / 39.29 % (34 of 56) | 53.00 / 48.56 % | 4.328 / 4.398 % | 14.88 / 15.37 s | 18 / 18 | 60 / 90 % | 60 % |
| 50/15, Slow CPU (3×) | 5 / 22 | 0.00 % (5 of 5) / 9.09 % (20 of 22) | 38.89 / 29.80 % | 5.620 / 8.275 % | 15.90 / 16.91 s | 18 / 18 | 113 / 166 % | 48 % |
| 50/25, Slow CPU (3×) | 28 / 64 | 35.71 % (18 of 28) / 43.75 % (36 of 64) | 60.52 / 57.99 % | 2.175 / 2.139 % | 13.61 / 14.25 s | 18 / 18 | 80 / 122 % | 49 % |
| 50/15, Normal CPU | 36 / 90 | 25.00 % (27 of 36) / 22.22 % (70 of 90) | 39.35 / 34.94 % | 8.694 / 7.091 % | 17.16 / 15.98 s | 18 / 18 | 117 / 177 % | 49 % |
| 50/25, Normal CPU | 137 / 232 | 51.09 % (67 of 137) / 54.35 % (105 of 230) | 62.65 / 59.43 % | 2.224 / 2.406 % | 14.06 / 14.07 s | 18 / 18 | 76 / 118 % | 52 % |

**Step 0 on 1,024 hosts.** What a node sends and receives when its link does not limit it, from the 1 Gbit hosts of
this run, split by validators as in the 2,048-host study (upload: bytes handed to TCP; download: bytes read from TCP; all
traffic, of which the PQ topic is 93–98 % of the download). On average a 1 Gbit host sends and receives the same on both
networks (means within 5 %). Hosts with many validators reach a higher p99 upload over 4–5 s on 1,024 hosts (303 against
259 Mbit/s), because each of them publishes more bundles per slot.

| 1 Gbit hosts (1,600 signatures per subnet per slot; every class must hold all at 8.0 s) | Window | Upload Mbit/s: mean / p90 / p99 / busiest node, 1,024 hosts | Upload, 2,048 hosts | Download Mbit/s: mean / p90 / p99 / busiest node, 1,024 hosts | Download, 2,048 hosts |
|---|---|---|---|---|---|
| ≤ 8 validators (616 / 1,225 hosts) | 4–8 s | 37.4 / 53.9 / 70.2 / 70.0 | 38.3 / 55.8 / 72.8 / 71.3 | 31.5 / 45.2 / 64.3 / 109.0 | 32.4 / 46.5 / 64.7 / 123.5 |
| ≤ 8 validators (616 / 1,225 hosts) | 4–5 s | 122.2 / 186.5 / 245.9 / 241.8 | 124.5 / 191.5 / 252.8 / 251.6 | 88.7 / 131.1 / 176.6 / 230.4 | 90.3 / 134.3 / 186.7 / 192.9 |
| > 8 validators (202 / 415 hosts) | 4–8 s | 40.8 / 59.1 / 83.9 / 104.0 | 39.6 / 57.6 / 75.6 / 106.4 | 32.5 / 46.7 / 65.2 / 94.2 | 32.4 / 46.6 / 62.7 / 78.6 |
| > 8 validators (202 / 415 hosts) | 4–5 s | 132.8 / 205.6 / 302.5 / 394.6 | 126.9 / 196.0 / 259.1 / 400.7 | 93.3 / 137.9 / 182.4 / 165.7 | 92.2 / 135.5 / 185.5 / 187.5 |

## Memory and run time

Shadow's own memory halves with the host count, but the node processes hardly get smaller: a node of the simulated network
(wbsim, built on rust-libp2p's gossipsub 0.49.5 with small patches) holds 2.5–6 % less memory on 1,024 hosts than on 2,048
in every pair of runs; each node still receives and caches all 1,600 signatures of every slot. Like the 2,048-host
figures, these are the simulator's memory at the end of each run, an order of magnitude rather than a client requirement.
Peaks are 0.47–0.49 of the 2,048-host peaks, and wall times 0.55–0.58.

| Run (1,600 signatures per subnet per slot) | Wall, 1,024 hosts (2,048) | Peak summed PSS, 1,024 hosts (2,048) | Shadow; wbsim per node, mean / largest, 1,024 hosts | Same, 2,048 hosts |
|---|---|---|---|---|
| `S1024x20-h1000x100-al0-s1` | 0.97 h (1.76 h) | 88 GiB (184 GiB) | 12.6 GiB; 75.8 / 128.2 MiB | 24.3 GiB; 79.8 / 137.1 MiB |
| `S1024x20-h1000x50-al0-s1` | 1.00 h (1.79 h) | 97 GiB (201 GiB) | 13.5 GiB; 83.6 / 134.5 MiB | 25.5 GiB; 88.0 / 133.7 MiB |
| `S1024x20-h1000x75-al0-s1` | 0.98 h (1.77 h) | 92 GiB (190 GiB) | 12.7 GiB; 79.4 / 127.3 MiB | 24.5 GiB; 82.9 / 126.8 MiB |
| `S1024x20-h100x100-al0-s1` | 1.01 h (1.82 h) | 99 GiB (204 GiB) | 12.6 GiB; 86.4 / 126.4 MiB | 24.7 GiB; 89.4 / 132.5 MiB |
| `S1024x20-h50x100-al0-s1` | 1.13 h (1.96 h) | 111 GiB (227 GiB) | 11.7 GiB; 99.3 / 149.2 MiB | 23.4 GiB; 101.8 / 153.5 MiB |
| `S1024x20-h100x100-al0-s2` | 1.01 h (1.83 h) | 98 GiB (206 GiB) | 12.1 GiB; 85.8 / 126.3 MiB | 24.5 GiB; 90.7 / 134.9 MiB |
| `S1024x20-h1000x100-s1` | 1.09 h (1.94 h) | 107 GiB (222 GiB) | 12.2 GiB; 95.3 / 141.5 MiB | 23.2 GiB; 99.6 / 152.7 MiB |
| `S1024x20-h1000x200-s1` | 1.08 h (1.94 h) | 106 GiB (221 GiB) | 12.0 GiB; 94.4 / 143.9 MiB | 23.4 GiB; 98.7 / 155.6 MiB |
| `S1024x20-h1000x200-al02-s1` | 1.02 h (1.85 h) | 96 GiB (201 GiB) | 12.8 GiB; 83.0 / 136.5 MiB | 24.5 GiB; 88.2 / 151.2 MiB |
| `S1024x20-h100x100-al0-v2000-s1` | 0.95 h (1.75 h) | 90 GiB (189 GiB) | 11.2 GiB; 78.3 / 131.6 MiB | 22.7 GiB; 83.3 / 138.0 MiB |
| `Q1024x20-m1600-s1` | 1.23 h (1.70 h, stopped for memory in slot 16) | 120 GiB (236 GiB) | 13.4 GiB; 106.4 / 161.6 MiB | no per-process log |
| `Q1024x20-m1600-fs75-s1` | 1.03 h (1.87 h) | 90 GiB (191 GiB) | 9.8 GiB; 80.7 / 143.1 MiB | no per-process log |

Per node, memory follows the data waiting in queues, as on 2,048 hosts: it is lowest where links are fast and nothing is
lost (76 MiB at 1000/100 with the access loss off) and highest where home hosts fall behind (99 MiB at 50/100, 106 MiB on the
EIP-7870 links). At 1,024 hosts every run fits the half budget of the machine (117 GiB summed PSS) except the EIP-7870 run
(120 GiB), which ran while no other user was active.
