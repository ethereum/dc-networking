# Can gossipsub carry 2,000 XMSS signatures per slot?

Independent check on the p2psims machine. A parallel 512-node run on an orb is in thread
T-01a1a58d-2a7b-7574-a777-6fbfb3592c5f.

## Answer

**No.** With Ethereum's gossipsub parameters, 2,000 signatures of 3 kB per slot reach every node within 4 s only when
every node has more than 200/100 Mbit/s (only the all-1 Gbit control passed). With EIP-7870 links anywhere in the network, those nodes never hold all 2,000
in time in any slot, and the backlog grows slot after slot.

- **Gossipsub is not the limit.** With every node on 1 Gbit, 100 % of nodes held all 2,000 at 4 s in every warm
  slot. p99 latency was 0.22 s, and traffic stayed flat over 10 slots.
- **The cost is κ ≈ 7.** Each node receives every signature about 7 times: 41.5 MiB per slot instead of 5.9 MiB,
  nearly all of it in the first second after publishing. Over the 4 s window that averages 87 Mbit/s each way, and up
  to 150 Mbit/s on the busiest nodes. IDONTWANT cannot stop duplicates that are already in flight.
- **EIP-7870 links fail, whatever share of the network runs 1 Gbit.** The rule: hosts with more than *k* validators
  get 1 Gbit, and of the rest 80 % get EIP-7870 links (50/25 attester; 50/15 for hosts without validators) and 20 %
  get 1 Gbit. The share of nodes with all 2,000 at 4 s then tracks the share of 1 Gbit nodes. 1 Gbit nodes
  complete; 50/25 and 50/15 nodes complete in 0–0.4 % of node·slots for every *k* from 8 down to 0.
- **Halving the load does not save it.** At 1,000 messages per slot, only 49–68 % of nodes hold everything at 4 s.
  At 500, traffic is flat over 10 slots (7.5 MiB per node, nothing left to drain), but only 73–94 % of nodes are
  complete at 4 s: half the 50/15 nodes miss some messages in each slot. At 250, 95–99 % are complete (p99 1.5 s); the
  misses are 50/15 nodes (11 % of their node·slots). Even 250 is not clean at EIP-7870 links.
- **100/50 (EIP-7870 builder) links fail too:** 52–73 % of nodes complete (47 % of the 100/50 nodes), and
  post-deadline traffic grows from 0.8 to 5.6 MiB per node over 10 slots.
- **200/100 links come close but still fail:** 84 % of nodes complete in slot 0, rising to 97–98 % (99.9 % of
  messages held), p99 1.8 s. Post-deadline traffic still creeps up (0.01 → 0.89 MiB per node over 10 slots).
- **Stricter than EIP-7870 (25/10) collapses:** 0 % complete, and held messages fall from 31 % to 13 % within 3
  slots.

### 2,000 messages per slot

| run (2,048 hosts, 10 slots) | hosts on 1 Gbit | nodes with all 2,000 at 4 s, per slot | 1 Gbit hosts complete | slow hosts complete | κ, first → last slot | MiB rx per node, first → last slot |
|---|---|---|---|---|---|---|
| `v2000-all1g`: all 1 Gbit (control) | 2,048 (100 %) | 98 % (cold slot 0), then 100 % | 99.8 % | – | 5.1 → 7.1 | 29.9, then 41.5 flat |
| `v2000-t8-200x100`: > 8 validators 1 Gbit, rest 80 % 200/100 | 742 (36 %) | 84, 91, 95, 96, 97, 98, 98, 97, 97, 98 % | 99.8 % | 92.3 % (200/100) | 4.4 → 5.1 | 25.9 → 29.8 |
| `v2000-t8-100x50`: > 8 validators 1 Gbit, rest 80 % 100/50 | 742 (36 %) | 52–73 % | 99.6 % | 46.9 % (100/50) | 3.7 → 5.1 | 21.4 → 29.6 |
| `v2000-t0-eip7870`: every validator host 1 Gbit, rest 80 % 50/15 | 1,721 (84 %) | 82–85 % | 99.8 % | 0.4 % (50/15) | 4.0 → 6.1 | 23.5 → 35.9 |
| `v2000-t1-eip7870`: > 1 validator 1 Gbit, rest 80 % EIP-7870 | 1,487 (73 %) | 70–73 %, 0 % in slot 9 | 90 % | 0.1 % (50/15), 0.3 % (50/25) | 3.6 → 8.1 | 20.9 → 47.6 |
| `v2000-t8-eip7870`: > 8 validators 1 Gbit, rest 80 % EIP-7870 | 742 (36 %) | 34–37 % (slots 0–4), 0 % (5–9) | 49 % | 0.0 % (50/15), 0.3 % (50/25) | 2.8 → 5.1 | 16.5 → 29.7 |
| `probe2048`: 25/10, 10 % random on 1 Gbit, 3 slots | 205 (10 %) | 0 % | 0 % | 0 % | 1.5 → 2.2 | 8.6 → 12.8 |

### Fewer messages (> 8 validators on 1 Gbit, rest 80 % EIP-7870)

| run | msgs per slot | nodes with all at 4 s, per slot | mean held at 4 s, first → last slot | 50/25 hosts complete | 50/15 hosts complete | latency p50 / p90 | κ, first → last slot |
|---|---|---|---|---|---|---|---|
| `v2000-t8-eip7870` | 2,000 | 34–37 %, then 0 % | 77.3 → 84.5 % | 0.3 % | 0.0 % | 1.03 / 6.92 s | 2.8 → 5.1 |
| `v1000-t8-eip7870` | 1,000 | 49, 56, 58, 60, 63, 66, 64, 62, 64, 68 % | 92.7 → 97.2 % | 47.8 % | 12.4 % | 0.60 / 2.66 s | 3.7 → 5.1 |
| `v500-t8-eip7870` | 500 | 73, 82, 84, 88, 90, 92, 93, 93, 94, 94 % | 98.6 → 99.5 % | 91.7 % | 51.6 % | 0.31 / 1.32 s | 5.2 → 5.2 (flat) |
| `v250-t8-eip7870` | 250 | 95–99 % | 99.94 → 99.97 % | 99.8 % | 88.6 % | 0.23 / 0.69 s (p99 1.50) | 6.4 (flat) |

## Where it breaks

- **By bandwidth:** with 2,000 messages, every node needs roughly 100 Mbit/s or more in both directions for about a
  second after publishing. The 1 Gbit network used at most 15 % of its links over the 4 s window, with peaks of 94 %
  up in single 0.5 s bins. 100/50 fails (52–73 % complete) and 200/100 nearly passes (84–98 %), so the threshold
  for every node every slot lies above 200/100 with this mix.
- **By message count:** at EIP-7870 links (> 8 validators on 1 Gbit), 2,000 and 1,000 messages per slot fail and the
  backlog grows; 500 is stable but 6–27 % of nodes miss some messages each slot; 250 is nearly clean (95–99 % of
  nodes, 99.97 % of messages). The sustainable limit for "every node, every slot" is below 250.
- **Not sustained:** in every failing run, per-node traffic, κ and the bytes still arriving after the deadline grow from
  slot to slot (`v2000-t1`: 1.3 → 5.4 MiB per node in the last 4 s of the slot; 26.5 MiB still arriving after the last
  slot). The 1 Gbit control stays flat at 41.5 MiB and 0.08 MiB after the deadline.

## Why it breaks

1. **Duplicates arrive together.** A node's 7–8 mesh peers forward each message within milliseconds of each other, so
   IDONTWANT (sent on first receipt) usually arrives after the copies are already queued or on the wire. In the 1 Gbit
   control a node receives 88,000 IDONTWANT IDs and still 6.5 copies of each message per slot. On slow links fewer
   copies arrive (2.5–4.2 per message) only because gossipsub drops them.
2. **1 Gbit peers flood slow peers' queues.** rust-libp2p holds at most 5,000 messages per peer and drops forwards
   older than 1 s. With fast nodes in the mesh, a slow node's inbound queues fill at once: in `v2000-t1`, 28 M messages
   per slot were dropped because a queue was full, and 3 M timed out. What is dropped is mostly what the slow node
   needed, so it falls back on IHAVE/IWANT, which round-trips through the same congested link. That is why slow nodes
   do *worse* as fast nodes become the majority (`t8` → `t1` → `t0`: slow-node completion stays at 0–0.4 %).
3. **Slow uplinks saturate.** A 50/25 node's uplink runs at its cap (25.0 Mbit/s over any 0.5–1 s window, from pcap)
   during the publishing burst and stays busy for most of the slot. Its share of forwarding then piles into the next
   slot.

## IDONTWANT, duplicates and drops

Per slot, averaged over 10 slots, all 2,048 nodes:

| run | copies received per message | IDONTWANT IDs rx per node | IWANT per node | forwards dropped (network) | queue-full drops | publishes dropped (run) |
|---|---|---|---|---|---|---|
| `v2000-all1g` (warm slots) | 6.2–6.5 | 82,000–88,500 | 16 | 0.2–1.3 M | 1.7–9.4 M | 0 |
| `v2000-t0-eip7870` | 5.2 | 57,800 | 330 | 5.2 M | 20.3 M | 1,630 |
| `v2000-t1-eip7870` | 4.6 | 53,800 | 540 | 8.2 M | 28.1 M | 4,344 |
| `v2000-t8-eip7870` | 3.5 | 37,000 | 1,100 | 11.6 M | 17.8 M | 3,573 |
| `v1000-t8-eip7870` | 3.8 | 23,700 | 490 | 5.7 M | 3.0 M | 43 |
| `v500-t8-eip7870` | 4.6 | 15,400 | 165 | 2.2 M | 0.04 M | 2 |
| `v250-t8-eip7870` | 5.9 | 9,900 | 39 | 0.42 M | 0 | 0 |
| `v2000-t8-100x50` | 3.9 | 42,900 | 950 | 12.2 M | 23.3 M | 29 |
| `v2000-t8-200x100` | 4.4 | 46,700 | 500 | 9.8 M | 30.7 M | 11 |

"Forwards dropped" are the forwards rust-libp2p dropped from a peer's send queue, as reported by its `SlowPeer` event
(after the 1 s queue timeout or because the queue was full). "Queue-full drops" include IHAVE/IWANT/IDONTWANT control
messages that did not fit.

## Per-node upload and download against link caps

Steady state (slots 2–9), libp2p bytes per node divided by the link cap. Sent bytes are counted when written to TCP,
so they can run ahead of the wire by the socket send buffer; over the 4 s window they exceed 100 % on slow links for
that reason. The packet capture is the on-wire check.

| run | link class | nodes | cap down/up (Mbit/s) | up, whole slot: mean / max node | up, 4 s window: mean | down, 4 s window: mean / max node |
|---|---|---|---|---|---|---|
| `v2000-t8-eip7870` | 50/15 | 330 | 50/15 | 92 % / 110 % | 167 % | 37 % / 53 % |
| | 50/25 | 976 | 50/25 | 71 % / 99 % | 145 % | 51 % / 71 % |
| | 1 Gbit | 742 | 1000/1000 | 2 % / 4 % | 5 % | 4 % / 7 % |
| `v2000-t1-eip7870` | 50/15 | 323 | 50/15 | 90 % / 113 % | 159 % | 32 % / 46 % |
| | 50/25 | 238 | 50/25 | 70 % / 105 % | 133 % | 44 % / 62 % |
| | 1 Gbit | 1,487 | 1000/1000 | 3 % / 5 % | 8 % | 7 % / 16 % |
| `v2000-t8-100x50` | 100/50 | 1,306 | 100/50 | 32 % / 60 % | 90 % | 44 % / 64 % |
| | 1 Gbit | 742 | 1000/1000 | 2 % / 4 % | 7 % | 5 % / 9 % |
| `v2000-t8-200x100` | 200/100 | 1,306 | 200/100 | 17 % / 31 % | 52 % | 29 % / 45 % |
| | 1 Gbit | 742 | 1000/1000 | 2 % / 5 % | 7 % | 6 % / 12 % |
| `v2000-all1g` | 1 Gbit | 2,048 | 1000/1000 | 3 % / 5 % | 9 % (max 15 %) | 9 % / 15 % |

On-wire rates from pcap (`v2000-t8-eip7870`, IP bytes, highest over any window):

| host | link | up peak 0.1 / 0.5 / 1 s (Mbit/s) | down peak 0.1 / 0.5 / 1 s (Mbit/s) |
|---|---|---|---|
| n0001 | 50/25 | 25.37 / 25.07 / 25.04 | 50.59 / 50.02 / 48.34 |
| n0004 | 50/25 | 25.36 / 25.07 / 25.03 | 50.61 / 50.00 / 45.11 |
| n0005 | 50/25 | 25.36 / 25.07 / 25.04 | 50.61 / 50.02 / 49.60 |
| n0000 | 1 Gbit | 366.72 / 120.48 / 95.65 | 235.63 / 120.85 / 84.85 |

**Upload caps are enforced.** Slow hosts upload at exactly their cap (the 0.1 s peak of 25.4 includes one queued
packet) and download at their 50 Mbit/s cap during the burst: they are saturated in both directions. The same check on
a 64-node run gave 10.0 Mbit/s on 25/10 hosts.

## Setup

- **Network:** 2,048 Shadow hosts, all on one gossipsub topic. Each runs a real rust-libp2p 0.56 node
  ([`sim/wbsim`](../sim/wbsim/src/main.rs); libp2p-gossipsub 0.49.5, TCP + noise + yamux) with Ethereum's gossipsub
  parameters: D=8, D_lo=6, D_hi=12, heartbeat 0.7 s, gossip_lazy 6, history 6/3, IDONTWANT above 1,000 B, flood publish
  off, content-hash message IDs, anonymous messages. Send queues are rust-libp2p's defaults: 5,000 messages per peer,
  forwards dropped after 1 s, publishes after 5 s. Each host dials 10 random peers (20 connections and 7.6 mesh peers
  per node on average). No message validation delay, no peer scoring, no packet loss.
- **Geography:** five regions (North America east and west, Europe, Asia, Oceania; 20/15/45/15/5 %) with one-way
  latencies of 10–140 ms, as in [results/sim.md](../results/sim.md).
- **Validators:** hosts are sampled from a mainnet peer crawl (`nodes.csv`: 13,613 peers, 10,902 with validators,
  727,723 validators). The skew is kept: 20 % of hosts run no validators, the median validator host runs 4, the top
  1 % run more than 1,500. The 2,048 sampled hosts run 126,255 validators.
- **Workload:** in each 12 s slot, 2,000 distinct 3,072 B signatures. Each comes from a random validator, so its
  publisher is a host drawn in proportion to its validator count: about 280 publishers per slot, the busiest
  publishing about 110. Publishing starts 4 s into the slot and is spread over 0.5 s.
- **Deadline:** every host must hold all 2,000 by 4 s after publishing starts (8 s into the slot). Latency is first
  receipt minus publish time; a message never received counts as "never".
- **Length:** 10 consecutive slots after a 20 s warm-up, then a 12 s drain.
- **Bandwidth profiles:** the user's rule. Hosts with more than *k* validators run 1 Gbit (large operators run from
  data centres). Of the rest, 20 % run 1 Gbit and 80 % run EIP-7870 links: 50/25 (attester) for validator hosts, 50/15
  (full node, the "minimum tested" upload) for hosts without validators. *k* = 8 is the base case; *k* = 1 and 0 test
  whether making more of the network fast rescues it. 100/50 and 200/100 bracket the threshold; 25/10 is a stricter
  stress point.
- **Shadow:** 3.3.0 built from source with [`sim/shadow-3.3-fixes.patch`](../sim/shadow-3.3-fixes.patch), so upload
  caps are enforced and large writes no longer stall.

## Limits

- **Cold first slot.** In the 1 Gbit control, 33 nodes (21 in Asia, 11 in Oceania) missed some messages in slot 0
  only. That is probably TCP and yamux windows still growing on long links during the first burst; it is not verified.
- **Size.** 2,048 nodes, one seed. One run at a time used 50–180 GB of RAM and 46 cores for 30–65 minutes. Several
  seeds of the 512-node configuration were started and stopped to keep half the shared machine free; the 512-node
  probe (25/10, 3 slots) matched the 2,048-node probe.
- **Not modelled:** signature verification before forwarding (it would add latency), peer scoring, packet loss, and
  other clients' queueing. With unbounded queues, slow nodes would receive more messages, but later.

## Machine and commands

p2psims: AMD EPYC 9454P (48 cores, 96 threads), 503 GiB RAM, Ubuntu 24.04.5, kernel 6.8.0-147. Runs were confined to
CPUs 48–95 at nice 19, one at a time, to leave half the machine to other users.

```sh
# Shadow 3.3.0, patched, into a private prefix (the existing ~/.local Shadow is untouched)
git clone --depth 1 --branch v3.3.0 https://github.com/shadow/shadow.git shadow-src && cd shadow-src
git apply ../repo/sim/shadow-3.3-fixes.patch
./setup build --clean -j 32 --prefix $PWD/../shadow-install && ./setup install
cargo build --release --manifest-path repo/sim/wbsim/Cargo.toml

# one run (runs/run_one.sh): CSV = mainnet peer crawl with a validator_count column
V="--hosts 2048 --validators-csv data/nodes.csv --slots 10 --drain 12 --parallelism 46 --no-cpu-pinning"
python3 repo/sim/gen_config.py --mode flood $V --msgs 2000 --fast-above 8 --fast-share 0.2 \
    --links 50/25 --links-novalidator 50/15 --pcap 3 --out runs/v2000-t8-eip7870
(cd runs/v2000-t8-eip7870 && taskset -c 48-95 nice -n 19 shadow shadow.yaml > shadow.log)
python3 repo/sim/analyze.py runs/v2000-t8-eip7870     # per-slot and per-class tables
python3 repo/sim/pcap_rate.py runs/v2000-t8-eip7870   # on-wire rates of the captured hosts

# other runs: change the flags
#   v2000-t1/t0:   --fast-above 1 / 0
#   v2000-all1g:   --links 1000/1000 --fast-share 0   (no --fast-above)
#   v2000-t8-100x50 / -200x100: --links 100/50 --links-novalidator 100/50 (resp. 200/100)
#   v1000/v500/v250-t8-eip7870: --msgs 1000 / 500 / 250
#   probe2048:     --msgs 2000 --links 25/10 --fast-share 0.1 --slots 3 (uniform publishers, no CSV)
```
