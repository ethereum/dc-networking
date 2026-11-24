# PQ Gasper: which link a node needs for one subnet of 1,600 signatures per slot

*Final, Nov 23, 2026, 22:10 CET: eleven runs at 2,048 hosts (one stopped early) and two at 512 hosts, listed in the runs
table.*

Follow-up to [pq-gasper-one-subnet.md](pq-gasper-one-subnet.md), where one subnet of 1,600 signatures per subnet per slot
failed for home nodes on EIP-7870 links (50/15 and 50/25 Mbit/s) and passed for 1 Gbit nodes. This study asks which link in
between a node needs: the smallest upload and the smallest download at which the home class passes.

**Load and requirement.** One PQ Gasper attestation subnet carries 1,600 signatures per subnet per slot (800,000
validators / 32 slots / 16 subnets), 2,404 B each (leanXMSS), bundled up to 16 per publisher (302 messages and 3.84 MB per
slot), published 4.0–4.5 s into the slot. Every node subscribes, and every node of every class must hold all of the slot's
signatures at 8.0 s.

**Pass rule** (as before): from slot 2, at least 99 % of a class's online nodes hold every signature at 8.0 s in every slot,
and late first deliveries (first received 8–16 s) do not build up. Signatures missing at 8.0 s are reported too.

## Result

At 1,600 signatures per subnet per slot, every node needing all of them at 8.0 s, on 2,048 hosts:

- **The smallest home link that passes is 100 Mbit/s down and 75–100 Mbit/s up, provided the home access line loses almost
  no packets.** With the access links' packet loss off (backbone loss, access latency and jitter kept), the smallest upload
  that passes is 75 Mbit/s at 1,000 down (worst slot 99.4 %; 50 fails narrowly at 96.2 %), and the smallest download is
  100 Mbit/s at 100 up (50 fails clearly at 77.8 %). 100/100 passes on two seeds (worst slot 99.2 and 99.4 %); 100/75 was
  not run.
- **Packet loss on the access line matters more than bandwidth.** With the modelled loss (fiber 0.05 %, cable 0.1 %, DSL
  0.25 % per direction) no home link passes: at 1000/100 and 1000/200 about 80 % of home nodes are complete, while their
  uplinks are a quarter and an eighth busy. At a fifth of that loss only fiber hosts (0.01 %) pass; cable at 0.02 % fails
  narrowly and DSL at 0.05 % clearly. At equal loss DSL hosts do worse than fiber hosts (86 % against 98 % complete at
  0.05 %), so access delay and jitter amplify the loss. The simulated TCP has SACK and a 200 ms minimum RTO but no tail loss
  probe or RACK, so it repairs losses more slowly than Linux, and these results are pessimistic for lossy lines.
- **Why 50 Mbit/s down fails:** Shadow's downlink queue is CoDel with a 10 ms target and no packet limit. At 50 down the
  publish burst keeps a home node's inbound queue above the target (packets wait up to 109 ms at p99), and packets into
  home nodes are lost 6–8 times as often as on the backbone alone; TCP retransmits twice as much as at 100/100 (512-host
  diagnostic). A real access line's queue may delay the burst instead of dropping part of it, so this result depends on the
  queue model.
- **Link use:** at 100/100 a home node uses on average a third of its uplink and two fifths of its downlink over 4–8 s, and
  about 72 % of its uplink and 60 % of its downlink over 4–5 s. At 1000/75 its uplink is at its limit over 4–5 s (106 % of
  the link handed to TCP on average).
- **CPU margin:** with PQ verification five times slower (2,000 µs per signature, 6,000 µs on slow CPUs) 100/100 still
  passes; slow-CPU hosts become CPU-bound and finish at 6.9 s at p99, about 1.1 s before the deadline.
- 1 Gbit nodes pass in every completed run (worst slot at least 99.5 %).

## Setup

- The network of `Q2048x20-m1600-s1`: 2,048 hosts × 20 slots, seed 1, mainnet validator counts; Shadow 3.3.0 with the rtt6
  TCP build (Linux v6.12 CUBIC with HyStart, slow start after idle); client mix with default peer targets and per-client
  gossipsub parameters; client-faithful scoring; WonderNetwork city latencies; fiber, cable and DSL access latency, jitter
  and packet loss; churn; 30 % of home hosts behind NAT; signature verification with 20 % slow CPUs; background traffic
  (blocks, data columns, aggregates, sync messages) and no BLS attestations, which PQ Gasper replaces.
- The 742 hosts on 1 Gbit stay: every host with more than 8 validators, plus 20 % of the rest. The other 1,306 hosts, called
  home hosts below, all get one link D/U (down/up, Mbit/s), with and without validators.
- Checked on the first run: apart from the home links, every host's fields (city, access type, client, validators, NAT,
  CPU) and the publisher schedule are identical to `Q2048x20-m1600-s1`. Home hosts: 591 fiber, 436 cable, 279 DSL; 232 with
  a slow CPU; 409 behind NAT.
- Smoke test (64 hosts × 6 slots, home links 1000/20 so that the cap binds): on the wire a home host never sent more than
  20.3 Mbit/s in any 0.1 s window (pcap), while handing TCP 130 % of its link in 4–5 s.
- `--access-loss-scale X` (new in `sim/perturb.py`) multiplies the packet loss of the home access links only. At the default
  of 1 the generated configuration is byte-identical to the one before the flag; at 0 and 0.2 only the 72 access edges
  change, and backbone loss, latencies and jitter stay as they are (checked on the 1000/200 configuration).

## Step 0: what a node sends and receives when its link does not limit it

From `Q2048x20-m1600-fs75-s1` (1,600 signatures per subnet per slot; 80 % of hosts on 1 Gbit), 1 Gbit hosts, slots 2–19.
Upload is bytes handed to TCP, download bytes read from TCP, all traffic (the PQ topic is 92–97 % of the download).

| 1 Gbit hosts (1,600 signatures per subnet per slot; every class must hold all at 8.0 s) | Window | Upload Mbit/s: mean / p90 / p99 / busiest node | Download Mbit/s: mean / p90 / p99 / busiest node |
|---|---|---|---|
| ≤ 8 validators (1,225 hosts) | 4–8 s | 38 / 56 / 73 / 71 | 32 / 47 / 65 / 124 |
| ≤ 8 validators | 4–5 s | 125 / 192 / 253 / 252 | 90 / 134 / 187 / 193 |
| > 8 validators (415 hosts) | 4–8 s | 40 / 58 / 76 / 106 | 32 / 47 / 63 / 79 |
| > 8 validators | 4–5 s | 127 / 196 / 259 / 401 | 92 / 136 / 186 / 188 |

## Runs

One run at a time, each chosen from the previous ones' verdicts. The search started with the upload at 1,000 Mbit/s down.
At 100 and 200 the home class failed alike with mostly idle links, so 1000/400 was stopped at slot 2 and the search
continues with the packet loss of the home hosts' access links switched off (`--access-loss-scale 0`; backbone loss, access
latency and jitter unchanged):

1. upload at 1,000 down: 100, then 50 if it passes or 200 if it fails; U* is the smallest upload that passes (none below 50:
   the home class already uploads 26 Mbit/s on average over 4–8 s);
2. download at U*: 100, then 50 if it passes or 200 if it fails; D* is the smallest download that passes;
3. seed 2 at D*/U*;
4. 1000/200 with the access loss at a fifth of the usual (fiber 0.01 %, cable 0.02 %, DSL 0.05 % per direction);
5. a diagnostic of the 50/100 failure: 512 hosts × 8 slots with access loss off, home links 50/100 and 100/100, on the
   Shadow build that logs TCP state and with the packets of 40 home hosts and one 1 Gbit host captured;
6. D*/U* with PQ verification five times slower (2,000 µs per signature instead of 400);
7. the upload midpoint, 1000/75.

A passing run that the watchdog stops for memory counts if its analysed slots reach slot 14 (marked in the table).

| Run (1,600 signatures per subnet per slot; every class must hold all at 8.0 s) | Home link | Home: complete at 8.0 s, worst slot / mean | 1 Gbit: worst / mean | Signatures missing at 8.0 s, home / 1 Gbit | Home verdict | Wall, peak PSS |
|---|---|---|---|---|---|---|
| `S2048x20-h1000x100-s1` | 1000/100 | 78.8 / 80.6 % | 99.6 / 99.8 % | 1.60 / 0.007 % | fail | 1.94 h, 222 GiB |
| `S2048x20-h1000x200-s1` | 1000/200 | 77.9 / 81.3 % | 99.9 / 99.9 % | 1.44 / 0.002 % | fail | 1.94 h, 221 GiB |
| `S2048x20-h1000x400-s1` | 1000/400 | stopped at slot 2: 100 and 200 give the same result, so 400 cannot change it | | | dropped | 0.3 h, 142 GiB |
| `S2048x20-h1000x100-al0-s1` | 1000/100, access loss off | 99.7 / 99.8 % | 99.9 / 99.98 % | 0.007 / 0.000 % | **pass** | 1.76 h, 184 GiB |
| `S2048x20-h1000x50-al0-s1` | 1000/50, access loss off | 96.2 / 99.0 % | 99.6 / 99.86 % | 0.040 / 0.006 % | fail (slots 2–4 and 6) | 1.79 h, 201 GiB |
| `S2048x20-h100x100-al0-s1` | 100/100, access loss off | 99.2 / 99.7 % | 99.6 / 99.88 % | 0.013 / 0.006 % | **pass** | 1.82 h, 204 GiB |
| `S2048x20-h50x100-al0-s1` | 50/100, access loss off | 77.8 / 86.4 % | 99.5 / 99.77 % | 0.283 / 0.013 % | fail | 1.96 h, 227 GiB |
| `S2048x20-h100x100-al0-s2` | 100/100, access loss off, seed 2 | 99.4 / 99.7 % | 99.6 / 99.77 % | 0.013 / 0.005 % | **pass** | 1.83 h, 206 GiB |
| `S2048x20-h1000x200-al02-s1` | 1000/200, access loss at a fifth | 95.2 / 96.3 % | 99.6 / 99.93 % | 0.153 / 0.001 % | fail (cable and DSL) | 1.85 h, 201 GiB |
| `S512x8-h50x100-al0-log-s1` (512 × 8, slots 2–7) | 50/100, access loss off | 78.7 / 85.8 % | 100 / 100 % | 0.281 / 0.000 % | fail | 0.30 h, 45 GiB |
| `S512x8-h100x100-al0-log-s1` (512 × 8, slots 2–7) | 100/100, access loss off | 99.4 / 99.8 % | 100 / 100 % | 0.010 / 0.000 % | pass | 0.27 h, 41 GiB |
| `S2048x20-h100x100-al0-v2000-s1` | 100/100, access loss off, PQ verification 2,000 µs | 99.6 / 99.9 % | 99.9 / 99.96 % | 0.003 / 0.001 % | **pass** | 1.75 h, 189 GiB |
| `S2048x20-h1000x75-al0-s1` | 1000/75, access loss off | 99.4 / 99.8 % | 99.9 / 99.98 % | 0.006 / 0.001 % | **pass** | 1.77 h, 190 GiB |

### 1000/100 and 1000/200 (slots 2–19; home 1,306 hosts, 1 Gbit 742)

| Class (1,600 signatures per subnet per slot; must hold all at 8.0 s) | Last needed signature p50 / p90 / p99 | Upload 4–8 s: Mbit/s mean, busiest (% of link) | Upload 4–5 s mean | Download 4–8 s: mean, busiest | Download 4–5 s mean | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|
| Home 1000/100 | 5.68 / 9.10 / 13.42 s | 25.6 (26 %), 56.4 (56 %) | 49.1 (49 %) | 33.3 (3.3 %), 87.5 (8.7 %) | 43.7 (4.4 %) | 46 % |
| 1 Gbit (home 1000/100) | 5.05 / 5.27 / 6.31 s | 54.7 (5.5 %), 128.1 (12.8 %) | 154.2 (15.4 %) | 32.4 (3.2 %), 68.4 (6.8 %) | 71.7 (7.2 %) | 24 % |
| Home 1000/200 | 5.61 / 9.02 / 13.06 s | 26.3 (13 %), 70.1 (35 %) | 53.6 (27 %) | 33.4 (3.3 %), 91.1 (9.1 %) | 46.9 (4.7 %) | 45 % |
| 1 Gbit (home 1000/200) | 5.08 / 5.28 / 6.31 s | 54.4 (5.4 %), 119.6 (12.0 %) | 157.6 (15.8 %) | 33.1 (3.3 %), 74.7 (7.5 %) | 76.3 (7.6 %) | 24 % |

| Home hosts by access type, CPU and NAT (1,600 signatures per subnet per slot, all needed at 8.0 s; 1000/100; 1000/200) | Hosts | Complete at 8.0 s: worst slot / mean | Signatures missing at 8.0 s | Upload 4–8 s / 4–5 s, % of link | PQ sends dropped after 1 s |
|---|---|---|---|---|---|
| Fiber | 591 | 97.3 / 98.3 %; 97.4 / 98.2 % | 0.086 %; 0.096 % | 33 / 72 %; 17 / 40 % | 39 %; 37 % |
| Cable | 436 | 74.1 / 77.9 %; 73.2 / 79.0 % | 1.34 %; 1.12 % | 22 / 36 %; 11 / 19 % | 51 %; 51 % |
| DSL | 279 | 43.4 / 47.7 %; 44.1 / 49.2 % | 5.18 %; 4.79 % | 15 / 20 %; 7 / 10 % | 56 %; 57 % |
| Slow CPU (3×) | 232 | 78.8 / 82.6 %; 78.4 / 82.9 % | 1.49 %; 1.37 % | | |
| Normal CPU | 1,074 | 78.2 / 80.2 %; 77.8 / 80.9 % | 1.62 %; 1.46 % | | |
| Behind NAT (1000/200) | 409 | 80.2 / 83.3 % | 1.39 % | | |
| Not behind NAT (1000/200) | 897 | 76.9 / 80.4 % | 1.47 % | | |

The home class fails at 1000/100 and at 1000/200 alike, and not for lack of bandwidth: home links carry on average a quarter
(at 100) and an eighth (at 200) of their upload and 3 % of their download over 4–8 s, and doubling the upload changes
nothing. The misses follow the access type: fiber hosts just miss the bar, cable and DSL hosts fail with mostly idle links.
Slow CPUs and NAT make no difference. Late first deliveries build up mildly (home 3.3 → 4.0 and 2.9 → 3.6 per node-slot from
the first to the second half of the slots).

**Access-link loss.** The modelled access links differ in packet loss as well as in delay: per direction, fiber loses 0.05 %
of packets with 4 ms one-way delay and 0.5 ms mean jitter, cable 0.1 % with 8 ms and 1.5 ms, DSL 0.25 % with 13 ms and
2.5 ms (`sim/perturb.py`, `ACCESS`). Backbone links lose 0.01 % within a continent and 0.05 % between continents. Jitter
never reorders a flow (the patch keeps packets FIFO per destination), so it only adds delay. The completion order
fiber > cable > DSL follows the loss rate. The simulated TCP has SACK and a 200 ms minimum RTO but no tail loss probe or
RACK (`shadow-src-rtt6`, `tcp.c` and `definitions.h`), so it recovers losses at the end of a burst more slowly than Linux,
which makes the result for lossy links pessimistic.

### 1000/100 with the access links' loss off (slots 2–19; home 1,306 hosts, 1 Gbit 742)

Switching off the packet loss of the home access links, with backbone loss, access latency and jitter unchanged, makes the
same home class pass: worst slot 99.7 % instead of 78.8 %, signatures missing at 8.0 s 0.007 % instead of 1.6 %, last
needed signature p99 5.85 s instead of 13.4 s. Late first deliveries do not build up (0.01 per node-slot in both halves of
the run). DSL hosts, with the longest access delay and the most jitter, pass too (worst slot 99.3 %), so delay and jitter
alone do not fail the class: the loss on the home access link does. Without it, home hosts forward their share: they upload
34 % of their link over 4–8 s instead of 26 %, saturate it in 4–5 s (94 % on average, at least 90 % in 55 % of node-slots),
and drop 20 % of their PQ sends after 1 s in the queue instead of 46 %.

| Class (1,600 signatures per subnet per slot; must hold all at 8.0 s) | Last needed signature p50 / p90 / p99 | Upload 4–8 s: Mbit/s mean, busiest (% of link) | Upload 4–5 s mean | Download 4–8 s: mean, busiest | Download 4–5 s mean | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|
| Home 1000/100, access loss off | 5.17 / 5.37 / 5.85 s | 33.9 (34 %), 60.7 (61 %) | 94.1 (94 %) | 41.5 (4.2 %), 90.9 (9.1 %) | 89.3 (8.9 %) | 20 % |
| 1 Gbit (same run) | 5.13 / 5.26 / 5.61 s | 53.8 (5.4 %), 103.7 (10.4 %) | 169.4 (16.9 %) | 36.1 (3.6 %), 72.7 (7.3 %) | 82.7 (8.3 %) | 10 % |

| Home hosts by access type and CPU (1,600 signatures per subnet per slot, all needed at 8.0 s; 1000/100, access loss off) | Hosts | Complete at 8.0 s: worst slot / mean | Signatures missing at 8.0 s | Last needed signature p99 | Upload 4–8 s / 4–5 s, % of link | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|
| Fiber | 591 | 99.7 / 99.92 % | 0.002 % | 5.87 s | 36 / 99 % | 18 % |
| Cable | 436 | 99.5 / 99.80 % | 0.007 % | 5.71 s | 33 / 92 % | 20 % |
| DSL | 279 | 99.3 / 99.60 % | 0.017 % | 6.16 s | 32 / 88 % | 23 % |
| Slow CPU (3×) | 232 | 99.1 / 99.64 % | 0.017 % | 6.16 s | | |
| Normal CPU | 1,074 | 99.7 / 99.85 % | 0.005 % | 5.80 s | | |

### 1000/200 with the access links' loss at a fifth (slots 2–19)

With the home access links losing a fifth of the modelled loss (fiber 0.01 %, cable 0.02 %, DSL 0.05 % per direction;
backbone loss, access latency and jitter unchanged), 1000/200 still fails: home worst slot 95.2 % (63 of 1,301), mean
96.3 %, 0.153 % of signatures missing at 8.0 s, last needed signature at 9.47 s at p99. Fiber hosts pass (worst slot 99.3 %,
4 of 587), cable hosts fail narrowly (96.8 %, 14 of 436) and DSL hosts clearly (81.4 %, 52 of 279). Late first deliveries
build up mildly (home 0.27 → 0.36 per node-slot from the first to the second half of the slots, DSL 0.97 → 1.37), and DSL
completion drifts down from 88–94 % in slots 2–4 to 81–87 % from slot 12 on. With less loss, home hosts forward more of
their share than at full loss: they upload 33 Mbit/s over 4–8 s instead of 26 and 85 instead of 54 over 4–5 s, and drop
30 % of their PQ sends after 1 s instead of 45 %. Slow CPUs make no difference (worst slot 94.8 % against 95.1 %).

| Class (1,600 signatures per subnet per slot; must hold all at 8.0 s) | Last needed signature p50 / p90 / p99 | Upload 4–8 s: Mbit/s mean, busiest (% of link) | Upload 4–5 s mean | Download 4–8 s: mean, busiest | Download 4–5 s mean | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|
| Home 1000/200, access loss at a fifth | 5.14 / 6.12 / 9.47 s | 33.0 (17 %), 71.9 (36 %) | 84.9 (42 %) | 39.2 (3.9 %), 105.4 (10.5 %) | 72.5 (7.2 %) | 30 % |
| 1 Gbit (same run) | 5.07 / 5.17 / 5.99 s | 53.1 (5.3 %), 110.3 (11.0 %) | 169.4 (16.9 %) | 35.8 (3.6 %), 88.0 (8.8 %) | 86.3 (8.6 %) | 15 % |

With the full-loss run this gives completion against the access loss per direction. The loss-off rows are from 1000/100
with the access loss off, where the upload does not bind either.

| Home hosts by access type and access loss (1,600 signatures per subnet per slot, all needed at 8.0 s; slots 2–19) | Access loss per direction | Complete at 8.0 s: worst slot / mean | Signatures missing at 8.0 s | Last needed signature p99 | PQ sends dropped after 1 s |
|---|---|---|---|---|---|
| Fiber, loss off (1000/100) | 0 | 99.7 / 99.92 % | 0.002 % | 5.87 s | 18 % |
| Cable, loss off (1000/100) | 0 | 99.5 / 99.80 % | 0.007 % | 5.71 s | 20 % |
| DSL, loss off (1000/100) | 0 | 99.3 / 99.60 % | 0.017 % | 6.16 s | 23 % |
| Fiber, a fifth | 0.01 % | 99.3 / 99.67 % | 0.011 % | 6.39 s | 22 % |
| Cable, a fifth | 0.02 % | 96.8 / 98.23 % | 0.075 % | 8.67 s | 32 % |
| DSL, a fifth | 0.05 % | 81.4 / 86.18 % | 0.572 % | 11.67 s | 47 % |
| Fiber, full | 0.05 % | 97.4 / 98.21 % | 0.096 % | 8.93 s | 37 % |
| Cable, full | 0.1 % | 73.2 / 78.98 % | 1.12 % | 12.31 s | 51 % |
| DSL, full | 0.25 % | 44.1 / 49.17 % | 4.79 % | 15.56 s | 57 % |
| Slow CPU (3×), a fifth, all access types | | 94.8 / 96.25 % | 0.145 % | 10.12 s | 32 % |
| Normal CPU, a fifth, all access types | | 95.1 / 96.31 % | 0.154 % | 9.30 s | 30 % |

Completion falls with the loss rate within each access type, and at equal loss it depends on the access type. At 0.05 %,
DSL hosts are complete in 86 % of node-slots and fiber hosts in 98 %, although in the full-loss run every other home host's
access link also lost five times as much as here; cable at 0.02 % and fiber at 0.05 % give the same mean. DSL's access link
adds 13 ms of one-way delay and 2.5 ms of mean jitter, against fiber's 4 ms and 0.5 ms. Without loss neither matters (DSL
passes at 1000/100 with the access loss off), so the longer and more variable round trip presumably makes each loss take
longer to repair (not measured directly). On this simulated TCP, without tail loss probe or RACK, home hosts pass only at
about 0.01 % access loss per direction (fiber at a fifth); cable at 0.02 % and fiber at 0.05 % already fail.

### 1000/50 with the access links' loss off (slots 2–19)

At 50 Mbit/s up the home class fails the rule, narrowly and mostly in the first slots. Per slot, home completion at 8.0 s
is 96.2, 98.7, 98.6, 99.2 and 98.7 % in slots 2–6, then at least 99.0 % in every slot from 7 to 19; over all slots 99.0 % of
home node-slots are complete and 0.040 % of signatures are missing at 8.0 s. Late first deliveries fall rather than build up
(0.10 per node-slot in the first half, 0.06 in the second). The uplink is the constraint: over 4–5 s home hosts hand TCP
123 % of their link and the busiest uses 96 % of it over 4–8 s, and 38 % of their PQ sends wait more than 1 s in the queue and
are dropped. Over the first ten slots the network adapts: PQ forwards dropped after the queue timeout fall from about
1.66 million per slot (slots 1–3) to about 1.0 million (slots 10–14), and broken-promise penalties from 175 to about 15 per
slot, consistent with scoring steering IWANT requests away from saturated home uplinks (not shown directly). By the rule 50
fails, marginally; the download search below was run at 100 up, and the midpoint 75 passes (see 1000/75).

| Class (1,600 signatures per subnet per slot; must hold all at 8.0 s) | Last needed signature p50 / p90 / p99 | Upload 4–8 s: Mbit/s mean, busiest (% of link) | Upload 4–5 s mean | Download 4–8 s: mean, busiest | Download 4–5 s mean | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|
| Home 1000/50, access loss off | 5.27 / 5.96 / 7.02 s | 27.5 (55 %), 48.1 (96 %) | 61.6 (123 %) | 36.4 (3.6 %), 85.7 (8.6 %) | 59.9 (6.0 %) | 38 % |
| 1 Gbit (same run) | 5.14 / 5.47 / 6.02 s | 54.1 (5.4 %), 108.0 (10.8 %) | 156.9 (15.7 %) | 32.3 (3.2 %), 78.7 (7.9 %) | 69.4 (6.9 %) | 17 % |

| Home hosts by access type and CPU (1,600 signatures per subnet per slot, all needed at 8.0 s; 1000/50, access loss off) | Hosts | Complete at 8.0 s: worst slot / mean | Signatures missing at 8.0 s | Last needed signature p99 | Upload 4–8 s / 4–5 s, % of link | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|
| Fiber | 591 | 95.3 / 99.05 % | 0.034 % | 6.98 s | 57 / 129 % | 37 % |
| Cable | 436 | 96.3 / 98.89 % | 0.056 % | 7.16 s | 54 / 121 % | 38 % |
| DSL | 279 | 97.9 / 99.18 % | 0.030 % | 6.94 s | 52 / 115 % | 39 % |
| Slow CPU (3×) | 232 | 97.0 / 98.58 % | 0.088 % | 8.21 s | 53 / 117 % | 39 % |
| Normal CPU | 1,074 | 96.0 / 99.12 % | 0.030 % | 6.90 s | 55 / 125 % | 38 % |

With access loss gone, the access types no longer differ much: fiber hosts, which upload the most, have the worst slot.
Slow CPUs now matter (0.088 % of signatures missing against 0.030 %), presumably because verification delay adds to the
queueing on a saturated uplink.

### 1000/75 with the access links' loss off (slots 2–19)

The upload midpoint passes: home worst slot 99.4 % (8 of 1,302, in slot 2; at least 99.6 % in every later slot), mean
99.8 %, 0.006 % of signatures missing at 8.0 s, last needed signature at 6.20 s at p99, and no build-up of late first
deliveries (0.01 per node-slot in both halves). U* is therefore 75 Mbit/s at 1,000 down: 50 fails narrowly and 75 passes.
The uplink is close to its limit: over 4–5 s home hosts hand TCP 106 % of their link on average (at least 90 % in 63 % of
node-slots), the busiest uses 75 % of it over 4–8 s, and 26 % of their PQ sends are dropped after 1 s (38 % at 50, 20 % at
100). Every access type and both CPU groups pass, fiber hosts with the least margin (worst slot 99.15 %, 5 of 589). 100/75
was not run, so the smallest link tested in both directions stays 100/100.

| Class (1,600 signatures per subnet per slot; must hold all at 8.0 s) | Last needed signature p50 / p90 / p99 | Upload 4–8 s: Mbit/s mean, busiest (% of link) | Upload 4–5 s mean | Download 4–8 s: mean, busiest | Download 4–5 s mean | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|
| Home 1000/75, access loss off | 5.20 / 5.54 / 6.20 s | 31.3 (42 %), 56.3 (75 %) | 79.3 (106 %) | 39.5 (3.9 %), 87.4 (8.7 %) | 75.7 (7.6 %) | 26 % |
| 1 Gbit (same run) | 5.14 / 5.32 / 5.77 s | 54.2 (5.4 %), 110.7 (11.1 %) | 164.2 (16.4 %) | 34.8 (3.5 %), 78.9 (7.9 %) | 76.0 (7.6 %) | 12 % |

| Home hosts by access type and CPU (1,600 signatures per subnet per slot, all needed at 8.0 s; 1000/75, access loss off) | Hosts | Complete at 8.0 s: worst slot / mean | Signatures missing at 8.0 s | Last needed signature p99 | Upload 4–8 s / 4–5 s, % of link | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|
| Fiber | 591 | 99.15 / 99.83 % | 0.003 % | 6.21 s | 44 / 109 % | 25 % |
| Cable | 436 | 99.5 / 99.81 % | 0.009 % | 6.09 s | 41 / 105 % | 26 % |
| DSL | 279 | 99.3 / 99.78 % | 0.009 % | 6.37 s | 39 / 100 % | 29 % |
| Slow CPU (3×) | 232 | 99.6 / 99.86 % | 0.003 % | 6.31 s | 41 / 102 % | 28 % |
| Normal CPU | 1,074 | 99.35 / 99.80 % | 0.007 % | 6.18 s | 42 / 107 % | 26 % |

### 100/100 with the access links' loss off, seeds 1 and 2 (slots 2–19)

With the download cut from 1,000 to 100 Mbit/s at 100 up, the home class still passes (worst slot 99.2 %, 11 of 1,302;
mean 99.7 %; 0.013 % of signatures missing at 8.0 s), with no build-up of late first deliveries (0.03 per node-slot in both
halves). Delivery is a little slower than at 1000/100: the last needed signature arrives by 6.67 s at p99 instead of 5.85 s,
home hosts send 434 IWANT requests per slot instead of 172, and 30 % of their PQ sends are dropped after 1 s instead of 20 %.
The downlink carries 41 % of its capacity over 4–8 s and 60 % over 4–5 s (busiest node 83 % and 77 %). Home hosts receive
later and so upload less in 4–5 s (71 % of their link instead of 94 %). Three subgroups dip just below 99 %:
DSL hosts in 3 of the 18 slots (worst 98.6 %, 4 of 279 hosts), fiber in 1 (98.98 %, 6 of 589) and slow CPU in 1 (98.7 %,
3 of 231), each within a few hosts of the bar; cable and normal-CPU hosts stay above it in every slot.

Seed 2 draws another network (1,326 home hosts: 615 fiber, 418 cable, 293 DSL; 252 slow CPUs) and another publisher schedule
(312 messages per slot), and gives the same result: home worst slot 99.4 % (8 of 1,319), mean 99.7 %, 0.013 % of signatures
missing at 8.0 s, last needed signature p99 6.66 s, no build-up of late first deliveries (0.03 and 0.02 per node-slot).
DSL hosts are under 99 % in 8 of the 18 slots (worst 98.6 %, 4 of 292; in the other seven 3 of 291–293, 98.97–98.98 %),
and slow-CPU hosts in 2 (98.8 %, 3 of 252 and 3 of 251); fiber, cable and normal-CPU hosts stay above it in every slot.

| Class (1,600 signatures per subnet per slot; must hold all at 8.0 s) | Last needed signature p50 / p90 / p99 | Upload 4–8 s: Mbit/s mean, busiest (% of link) | Upload 4–5 s mean | Download 4–8 s: mean, busiest | Download 4–5 s mean | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|
| Home 100/100, access loss off | 5.37 / 6.04 / 6.67 s | 33.2 (33 %), 52.5 (53 %) | 71.4 (71 %) | 41.3 (41 %), 83.0 (83 %) | 59.8 (60 %) | 30 % |
| 1 Gbit (same run) | 5.14 / 5.28 / 5.73 s | 55.7 (5.6 %), 131.3 (13.1 %) | 162.2 (16.2 %) | 35.6 (3.6 %), 75.7 (7.6 %) | 78.6 (7.9 %) | 16 % |
| Home 100/100, seed 2 | 5.38 / 6.01 / 6.66 s | 34.2 (34 %), 58.4 (58 %) | 73.4 (73 %) | 42.3 (42 %), 83.0 (83 %) | 60.9 (61 %) | 31 % |
| 1 Gbit (seed 2) | 4.96 / 5.24 / 5.97 s | 56.8 (5.7 %), 114.5 (11.4 %) | 169.0 (16.9 %) | 35.8 (3.6 %), 91.1 (9.1 %) | 82.9 (8.3 %) | 17 % |

| Home hosts by access type and CPU (1,600 signatures per subnet per slot, all needed at 8.0 s; 100/100, access loss off) | Hosts | Complete at 8.0 s: worst slot / mean | Signatures missing at 8.0 s | Last needed signature p99 | Upload 4–8 s / 4–5 s, % of link | Download 4–8 s / 4–5 s, % of link | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|---|
| Fiber | 591 | 98.98 / 99.81 % | 0.008 % | 6.60 s | 36 / 79 % | 41 / 62 % | 28 % |
| Cable | 436 | 99.3 / 99.68 % | 0.018 % | 6.56 s | 32 / 68 % | 41 / 60 % | 31 % |
| DSL | 279 | 98.6 / 99.58 % | 0.015 % | 6.80 s | 30 / 59 % | 42 / 55 % | 35 % |
| Slow CPU (3×) | 232 | 98.7 / 99.69 % | 0.013 % | 6.71 s | 32 / 67 % | 42 / 60 % | 32 % |
| Normal CPU | 1,074 | 99.3 / 99.73 % | 0.013 % | 6.66 s | 34 / 72 % | 41 / 60 % | 30 % |
| Fiber, seed 2 | 615 | 99.3 / 99.87 % | 0.003 % | 6.44 s | 37 / 81 % | 42 / 63 % | 28 % |
| Cable, seed 2 | 418 | 99.5 / 99.87 % | 0.005 % | 6.68 s | 33 / 71 % | 42 / 61 % | 32 % |
| DSL, seed 2 | 293 | 98.6 / 99.26 % | 0.047 % | 6.97 s | 31 / 61 % | 43 / 56 % | 36 % |
| Slow CPU (3×), seed 2 | 252 | 98.8 / 99.65 % | 0.018 % | 6.80 s | 33 / 68 % | 42 / 60 % | 33 % |
| Normal CPU, seed 2 | 1,074 | 99.5 / 99.76 % | 0.012 % | 6.61 s | 35 / 75 % | 42 / 61 % | 30 % |

### 50/100 with the access links' loss off (slots 2–19)

At 50 Mbit/s down the home class fails clearly: no slot from 2 on reaches 91 %, the worst is 77.8 % (289 of 1,303), and
0.28 % of signatures are missing at 8.0 s. Delivery is slow from the start: home hosts hold 43 % of the slot's signatures at
5 s and 87 % at 6 s (88 % and 99.9 % at 1000/100), and the last needed signature arrives at 9.8 s at p99. Late first
deliveries are frequent (0.61 per node-slot) but do not build up (0.70 in the first half, 0.52 in the second).

Each needed message reaches a home host 5.2 times on average (mesh peers plus IWANT replies, 11.6 kB each), so about
146 Mbit of PQ copies arrive per slot. With 1,000 Mbit/s down, home hosts take in 89 Mbit/s over 4–5 s, more than half of
their 4–8 s download. At 50 down the downlink carries only 31 Mbit/s (63 %) over 4–5 s and 64 % over 4–8 s (the busiest
node 80 % and 90 %): it stays below its capacity while the demand is above it. Home hosts request 901 messages per slot
by IWANT (434 at 100/100) and drop 42 % of their PQ sends after 1 s.

**Shadow's downlink queue.** Packets for a host wait in its router's inbound queue, which Shadow drains at the host's
download rate. That queue is CoDel (RFC 8289) with a 10 ms target (the RFC suggests 5 ms), a 100 ms interval and no packet
limit, without flow queueing (not fq_codel) (`shadow-src-rtt6`, `src/main/network/router/codel_queue.rs` L23–L33). Once
packets have waited more than 10 ms for 100 ms, CoDel drops packets at a rising rate until the wait falls below 10 ms; it
never drops because the queue is full. The upload side has no such queue: a host's outgoing data waits in its TCP send
buffers and is delayed, not dropped. A real access line's downstream queue is set by the ISP's equipment and varies: a
plain FIFO buffer of tens to hundreds of milliseconds would delay this burst instead of dropping part of it, while a
policer, or an AQM with a shorter target, would drop sooner. The likely mechanism of the 50/100 failure is that the publish
burst keeps this queue above 10 ms, CoDel drops packets, and the simulated TCP recovers those losses as slowly as access
losses. The diagnostic runs below confirm it.

| Class (1,600 signatures per subnet per slot; must hold all at 8.0 s) | Last needed signature p50 / p90 / p99 | Upload 4–8 s: Mbit/s mean, busiest (% of link) | Upload 4–5 s mean | Download 4–8 s: mean, busiest | Download 4–5 s mean | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|
| Home 50/100, access loss off | 6.78 / 8.21 / 9.79 s | 30.3 (30 %), 50.3 (50 %) | 43.4 (43 %) | 31.8 (64 %), 44.8 (90 %) | 31.3 (63 %) | 42 % |
| 1 Gbit (same run) | 5.10 / 5.23 / 6.44 s | 53.8 (5.4 %), 120.2 (12.0 %) | 140.8 (14.1 %) | 33.8 (3.4 %), 72.9 (7.3 %) | 71.7 (7.2 %) | 33 % |

| Home hosts by access type and CPU (1,600 signatures per subnet per slot, all needed at 8.0 s; 50/100, access loss off) | Hosts | Complete at 8.0 s: worst slot / mean | Signatures missing at 8.0 s | Last needed signature p99 | Upload 4–8 s / 4–5 s, % of link | Download 4–8 s / 4–5 s, % of link | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|---|
| Fiber | 591 | 79.6 / 88.9 % | 0.202 % | 9.71 s | 32 / 49 % | 65 / 66 % | 40 % |
| Cable | 436 | 77.0 / 85.9 % | 0.304 % | 9.77 s | 29 / 41 % | 63 / 62 % | 42 % |
| DSL | 279 | 75.3 / 81.9 % | 0.418 % | 9.96 s | 28 / 36 % | 63 / 57 % | 43 % |
| Slow CPU (3×) | 232 | 78.9 / 86.5 % | 0.315 % | 10.07 s | 29 / 42 % | 65 / 62 % | 42 % |
| Normal CPU | 1,074 | 76.8 / 86.3 % | 0.276 % | 9.44 s | 31 / 44 % | 64 / 63 % | 41 % |

### Diagnostic of the 50/100 failure (512 hosts × 8 slots, slots 2–7)

Two runs with the access loss off, home links 50/100 and 100/100 (330 home hosts and 182 on 1 Gbit), on the Shadow build
that logs each TCP connection's state (`shadow-install-rtt6-log`). For the paths into home nodes, by sender class, they
give TCP retransmission timeouts and retransmitted packets per 1,000 data packets (`.amp-out/downqtcp.py`, the leaf
diagnostic of the one-subnet study for any link classes). Shadow logs its router's drops only at trace level, which
release builds leave out, so the drops are counted from packet captures of 40 home hosts and one 1 Gbit host instead
(`.amp-out/pcapdrop.py`). Shadow records a sent packet before the path's loss is drawn and a received packet after the
receiver's downlink queue, so between two captured hosts every lost transmission is counted. With the access loss off,
the paths into home nodes lose packets only on the backbone (0.01–0.05 %), and anything beyond that was dropped at the
home node's downlink queue. On the smoke run, where no queue forms, the measured loss matched the configured loss within
noise.

Both runs reproduce the 2,048-host results. At 50/100 the home class fails: worst slot 78.7 %, mean 85.8 %, 0.28 % of
signatures missing at 8.0 s, last needed signature at 9.82 s at p99 (at 2,048 hosts 77.8 %, 86.4 %, 0.28 %, 9.79 s). At
100/100 it passes: 99.4 %, 99.8 %, 0.010 %, 6.67 s (at 2,048 hosts 99.2 %, 99.7 %, 0.013 %, 6.67 s). 1 Gbit hosts hold every
signature at 8.0 s in both runs.

| Paths into home nodes (1,600 signatures per subnet per slot, all needed at 8.0 s; access loss off; slots 2–7) | 50/100 | 100/100 |
|---|---|---|
| Lost per 1,000 transmissions, home → home (configured backbone loss 0.29) | 2.24 (1.95 above configured) | 0.67 (0.38 above) |
| Lost per 1,000 transmissions, 1 Gbit → home (configured 0.27; 0.14 at 100/100) | 1.54 (1.27 above) | 0.38 (0.23 above) |
| Control: lost per 1,000 transmissions, home → 1 Gbit (configured 0.29; 0.19 at 100/100) | 0.31 | 0.08 |
| Lower bound over all senders into the captured home hosts: sequence holes per 1,000 received, from home / 1 Gbit senders | 2.09 / 2.42 | 0.65 / 0.71 |
| Wait in the home node's inbound queue, packets sent 4–5 s, home → home: p50 / p99 / max | 26.5 / 108.5 / 152.5 ms | 13.5 / 62.5 / 95.5 ms |
| Same, 1 Gbit → home | 18.7 / 74.4 / 115.9 ms | 15.8 / 54.1 / 65.4 ms |
| Share of the losses by send time 4–5 / 5–6 / 6–8 s, home → home | 9 / 27 / 52 % | 14 / 34 / 30 % |
| Home downlink: 10-ms intervals in 4–6 s at 90 % of the link or more (captured hosts) | 62 % | 42 % |
| TCP retransmitted packets per 1,000 data packets, 1 Gbit → home / home → home | 3.11 / 3.55 | 1.47 / 1.62 |
| TCP retransmission timeouts per 1,000 data packets (spurious share), 1 Gbit → home / home → home | 0.38 (47 %) / 1.09 (22 %) | 0.54 (19 %) / 1.11 (14 %) |
| For comparison, home → 1 Gbit: retransmitted packets / timeouts per 1,000 data packets | 0.88 / 0.71 | 0.65 / 0.47 |

This confirms the CoDel explanation. Into the 1 Gbit host the measured loss equals the configured backbone loss within
noise. Into home nodes at 50/100 it is 6–8 times the configured loss, 1.3–2.0 packets per 1,000 above it, and with the
access loss off that excess can only have been dropped at the home node's downlink queue. Packets sent 4–5 s wait up to
109 ms there at p99, against CoDel's 10 ms target, and about four fifths of the losses hit packets sent 5–8 s, once the
queue has stayed above the target for longer than CoDel's 100 ms interval and its drop rate has risen. TCP into home nodes
retransmits about twice as many packets as at 100/100 while its retransmission timeouts do not increase, so the extra drops
are repaired by fast retransmission. The excess is comparable to the access loss that fails cable and DSL hosts (1.0 and
2.5 per 1,000 per direction). At 100/100 the excess is a fifth as large (0.2–0.4 per 1,000), and the class passes.

### 100/100 with PQ verification five times slower (slots 2–19)

At 100/100 with the access loss off, each PQ signature here costs 2,000 µs to verify instead of 400 (6,000 µs on
the 20 % of home hosts with a slow CPU; block, column, aggregate and sync-message costs unchanged). The home class still
passes, by a wider margin than at 400 µs: worst slot 99.6 % (5 of 1,302), mean 99.87 %, 0.003 % of signatures missing at
8.0 s, and no build-up of late first deliveries (0.01 per node-slot in both halves). Hosts with a normal CPU finish as
before (last needed signature at 6.68 s at p99, against 6.66 s at 400 µs). Slow-CPU hosts become CPU-bound: they hold 31 %
of the slot's signatures at 5 s and 72 % at 6 s (72 % and 99.4 % at 400 µs), and they all finish in a narrow band, at
6.66 / 6.74 / 6.89 s (p50 / p90 / p99), about 1.1 s before the deadline. That matches their work: 1,600 signatures at
6 ms on four workers take 2.4 s, starting with the burst at 4.0–4.5 s. They still pass (worst slot 99.6 %, 1 of 231; at
400 µs this subgroup dipped to 98.7 % in one slot). By the same arithmetic, verification could be roughly 1.5 times slower
again (about 3,000 µs per signature) before slow-CPU hosts run out of time; that is an extrapolation, not simulated.

Slower verification spreads each node's forwarding over a longer time, and the network is a little less congested: home
hosts hand TCP 60 % of their uplink over 4–5 s instead of 71 %, request 297 messages per slot by IWANT instead of 434, and
drop 23 % of their PQ sends after 1 s instead of 30 %. Slow-CPU hosts forward less (16 % of their uplink over 4–8 s,
against 32 % for normal hosts). This is presumably why completion is slightly higher than at 400 µs.

| Class (1,600 signatures per subnet per slot; must hold all at 8.0 s) | Last needed signature p50 / p90 / p99 | Upload 4–8 s: Mbit/s mean, busiest (% of link) | Upload 4–5 s mean | Download 4–8 s: mean, busiest | Download 4–5 s mean | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|
| Home 100/100, access loss off, PQ 2,000 µs | 5.53 / 6.66 / 6.82 s | 29.3 (29 %), 54.1 (54 %) | 59.5 (60 %) | 37.8 (38 %), 79.2 (79 %) | 53.4 (53 %) | 23 % |
| 1 Gbit (same run) | 5.35 / 5.48 / 6.03 s | 51.6 (5.2 %), 120.7 (12.1 %) | 137.1 (13.7 %) | 31.1 (3.1 %), 83.8 (8.4 %) | 59.2 (5.9 %) | 12 % |

| Home hosts by access type and CPU (1,600 signatures per subnet per slot, all needed at 8.0 s; 100/100, access loss off, PQ 2,000 µs) | Hosts | Complete at 8.0 s: worst slot / mean | Signatures missing at 8.0 s | Last needed signature p99 | Upload 4–8 s / 4–5 s, % of link | Download 4–8 s / 4–5 s, % of link | PQ sends dropped after 1 s |
|---|---|---|---|---|---|---|---|
| Fiber | 591 | 99.7 / 99.91 % | 0.001 % | 6.80 s | 31 / 65 % | 37 / 54 % | 20 % |
| Cable | 436 | 99.8 / 99.89 % | 0.003 % | 6.80 s | 29 / 57 % | 38 / 54 % | 23 % |
| DSL | 279 | 99.3 / 99.74 % | 0.007 % | 6.88 s | 27 / 52 % | 39 / 51 % | 27 % |
| Slow CPU (3×: 6,000 µs per signature) | 232 | 99.6 / 99.98 % | 0.000 % | 6.89 s | 16 / 27 % | 36 / 54 % | 23 % |
| Normal CPU | 1,074 | 99.6 / 99.84 % | 0.004 % | 6.68 s | 32 / 66 % | 38 / 53 % | 23 % |

## Verification model

- 400 µs per PQ signature: leanSig verification takes 193–393 µs on one M1 core (leanroadmap) and the DKKW Poseidon2 variant
  351 µs; 400 µs rounds up the high end (`results/realism-calibration.md`, verification row).
- Workers: 4 on home hosts and 8 on 1 Gbit hosts. These are estimates, not measurements; the worker count stands in for
  parallel and batch verification. The slow-CPU share (20 % of home hosts) and factor (3×) are estimates too.
- In wbsim a message costs 400 µs × its signatures × the host's CPU factor on the earliest-free worker, before it is
  delivered or forwarded.
- Margin: at 2,000 µs per signature, five times the model, 100/100 still passes; slow-CPU hosts (6,000 µs) become
  CPU-bound and finish at 6.9 s at p99 (see the run above).

## Memory per node

A rough guide to what the subnet adds to a node's memory: the simulated node process (wbsim, built on rust-libp2p's
gossipsub 0.49.5 with small patches, so it holds gossipsub's message cache, seen-message cache and send queues, plus the
simulator's own bookkeeping), at the end of each run.

| Run | Signatures per subnet per slot (all needed at 8.0 s) | Home link | wbsim memory per node: mean / largest | Shadow itself |
|---|---|---|---|---|
| `Q2048x20-m200-s1` (earlier study) | 200 | 50/15 and 50/25 | about 61 MiB mean (peak 133.8 GiB minus Shadow's 12.0 GiB, over 2,048 nodes; no per-process log) | 12.0 GiB |
| `S2048x20-h100x100-al0-s1` | 1,600 | 100/100 | 89.4 / 132.5 MiB | 24.7 GiB |
| `S2048x20-h100x100-al0-s2` (seed 2) | 1,600 | 100/100 | 90.7 / 134.9 MiB | 24.5 GiB |

At 100/100 a subnet of 1,600 signatures per slot takes about 30 MiB per node more than one of 200 (about 90 against 61 MiB;
the largest node 135 MiB). The figure grows with the data waiting in queues: across the runs at 1,600 signatures it ranges
from 80 MiB per node (1000/100 without access loss) to 102 MiB (50/100). It is the simulator's memory, not a client's, so it
gives the order of magnitude only: tens of MiB, not a hardware requirement.
