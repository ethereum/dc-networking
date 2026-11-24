# What a node needs to carry one PQ Gasper subnet

*Draft, 2026-11-24. Follow-up to [Can PQ Gasper run on gossipsub?](pq-gasper-on-gossipsub.md)*

**A node needs about 100 Mbit/s of download and 75 to 100 of upload, on a line that loses almost no packets.** One PQ Gasper subnet carries 1,600 signatures per subnet per slot, and every node must hold all of them 4 s after publishing begins. In simulation, home nodes whose access line drops no packets pass at 100/100 Mbit/s (down/up) with two seeds and at 1,000/75, and they fail at 50 in either direction. With the usual home-line loss of 0.05 to 0.25 % they fail at every speed tested, up to 1,000/200, and with a fifth of that loss only the lines at 0.01 % are at the bar: they pass on 2,048 nodes and are one node short in one slot on 1,024. CPU has room for verification five times slower, and gossip takes tens of MiB of memory. Unless noted, the numbers are from a network of 2,048 nodes. The same study on 1,024 nodes, twelve runs, gives the same verdict for every home link.

![Dot chart on a log scale: the home nodes that miss at least one of a slot's 1,600 signatures at 8.0 s, in each run's worst slot, by home link (down/up in Mbit/s) and by packet loss on the home access line. A run passes with at most 1 %. With the usual loss of 0.05–0.25 %: 50/15 77 %, 50/25 47 %, 1,000/200 22 % and 1,000/100 21 %. With a fifth of it: 1,000/200 4.8 %. On loss-free lines: 50/100 22 %, 1,000/50 3.8 %, 100/100 0.84 % and 0.61 % with two seeds, 1,000/75 0.61 % and 1,000/100 0.31 %.](charts/subnet-link-limits.svg)

*One run per dot, on 2,048 nodes. A run passes when at most 1 % of the home nodes online miss a signature at 8.0 s, in every slot. The loss is per direction on the home access line. 50/15 and 50/25 are the two home classes of the earlier post's run.*

| Requirement | Result | What the runs show | Not tested |
| --- | --- | --- | --- |
| Upload | 75 to 100 Mbit/s | 1,000/75 and 100/100 pass. 1,000/50 fails narrowly, with 96.2 % of home nodes complete in the worst slot | 100/75 |
| Download | 100 Mbit/s | 100/100 passes with two seeds. 50/100 fails at 77.8 %, because the simulated downlink queue drops packets from the burst | Speeds between 50 and 100, and a queue that delays instead of dropping |
| Access line | At most about 0.01 % packet loss per direction | At 1,000/200, nodes on lines losing 0.01 % pass on 2,048 nodes and are one node short in one slot on 1,024. Those at 0.02 % reach 96.8 % in the worst slot and those at 0.05 % reach 81.4 % | Real TCP, which repairs losses faster than the simulated one |
| CPU | Not the limit on 4 cores | At 2 ms per signature, five times the modelled cost, 100/100 still passes. Nodes at 6 ms finish by 6.9 s, 1.1 s before the deadline | Aggregation |
| Memory | Tens of MiB for gossip | The simulated node held about 90 MiB at 100/100 after 20 slots, against about 61 MiB with 200 signatures | Runs longer than 20 slots |

[EIP-7870](https://eips.ethereum.org/EIPS/eip-7870) recommends 50/15 Mbit/s down/up for a full node, 50/25 for an attester and 100/50 for a local block builder, with 4 to 8 cores and 32 to 64 GB of memory. The subnet asks for twice an attester's download and three to four times its upload. A local block builder's 100/50 has the download, and its upload is the 50 that fails narrowly.

## The subnet: 1,600 signatures per slot, all held within 4 s

These are the assumptions of [the earlier post](pq-gasper-on-gossipsub.md#setup), unchanged.

- **Load:** 800k validators ÷ 32 slots ÷ 16 subnets ≈ 1,600 signatures per subnet per slot. Each is a 2,404 B leanXMSS signature, sent in bundles of up to 16 per publisher. That is about 302 messages and 3.84 MB per slot.
- **Deadline:** signatures go out 4.0–4.5 s into the 12 s slot. Every node must hold all 1,600 at 8.0 s, when aggregation starts.
- **Network:** 2,048 nodes, all in the subnet, with mainnet's validator distribution and client mix. Each client keeps its default gossipsub parameters, peer counts and scoring. Latencies between cities, churn, NAT, slow CPUs and Linux's TCP congestion control are modelled. Blocks, data columns and aggregates run alongside.
- **Nodes:** 742 nodes sit on 1 Gbit data-centre links. They are every node with more than 8 validators and a fifth of the others. The other 1,306 are the home nodes, and all of them get the link under test. This is seed 1, the network of the earlier post. Seed 2 draws another network, with 722 data-centre nodes and 1,326 home nodes.
- **Lines:** data-centre links lose 0.01 % of packets within a continent and 0.05 % between continents. Each home node also has an access line, drawn independently of its speed: fiber-grade with probability 45 %, cable-grade 33 % and DSL-grade 22 %. These lose 0.05, 0.1 and 0.25 % of packets in each direction and add 4, 8 and 13 ms each way. The latencies come from FCC measurements; the loss values are estimates within the FCC's "a few tenths of a percent is common" ([`sim/perturb.py`](../research/pq-gasper/gossipsub/sim/perturb.py) and the [calibration notes](../research/pq-gasper/gossipsub/results/realism-calibration.md)).
- **Loss levels:** a run gives the home access lines the usual loss, a fifth of it (0.01, 0.02 and 0.05 %), or none. The lines keep their latency and jitter and the backbone keeps its loss in all three. On a loss-free line a home node sees the same loss as a data-centre node.
- **Pass:** at least 99 % of the home nodes that are online hold every signature at 8.0 s, in every slot. Slots are numbered from 0, and slots 0 and 1 of a run's 20 are left out.

## On loss-free lines, 100/100 and 1,000/75 pass, and 50 fails in either direction

| Home link | Complete, worst slot | Signatures missed | Last signature | Upload, % of the uplink | Download, % of the downlink |
| --- | --- | --- | --- | --- | --- |
| 1,000/100 | 99.7 % (4 of 1,302) | 0.007 % | 5.9 s | 34 / 94 | 4 / 9 |
| 1,000/75 | 99.4 % (8 of 1,302) | 0.006 % | 6.2 s | 42 / 106 | 4 / 8 |
| **100/100** | **99.2 % (11 of 1,302)** | 0.013 % | 6.7 s | 33 / 71 | 41 / 60 |
| **100/100, seed 2** | **99.4 % (8 of 1,319)** | 0.013 % | 6.7 s | 34 / 73 | 42 / 61 |
| 1,000/50 | 96.2 % (50 of 1,302) | 0.040 % | 7.0 s | 55 / 123 | 4 / 6 |
| 50/100 | 77.8 % (289 of 1,303) | 0.28 % | 9.8 s | 30 / 43 | 64 / 63 |

One run per row, slots 2–19, with seed 1 unless the row says otherwise. Home link is down/up in Mbit/s. Complete is the share of home nodes holding every signature at 8.0 s in the run's worst slot, with the incomplete nodes in brackets. Signatures missed is the share a home node lacks at 8.0 s. Last signature is the slot time at which a node's last signature arrives, at the 99th percentile. Upload and download give the share of the link used over the 4 s, then in the first second. Upload is what the node hands to TCP, so a value above 100 means its buffers fill. Data-centre nodes pass in every run of the study, and their worst slot is 99.5 %. Sources: `pq1600-S2048x20-h<down>x<up>-al0-s<seed>.txt` and the matching `specs-…` files (see Runs).

- **100/100 passes with both seeds, by a few nodes.** The bar allows 13 incomplete home nodes in a slot. The worst slot has 11 with seed 1 and 8 with seed 2. In both runs it is slot 2, the first slot counted, and every later slot is at 99.5 % or more. For 99 % of node-slots the last signature is in by 6.7 s, 1.3 s before the deadline.
- **Upload: 75 passes behind a fast downlink, and 50 is just short.** At 1,000/75 the worst slot has 8 of 1,302 home nodes incomplete. The uplink is then at its limit in the first second, when nodes hand TCP 106 % of it. At 1,000/50 the home nodes miss the bar in slots 2, 3, 4 and 6 and are at 99.0 % or more from slot 7 on. 100/75 was not run, so 100/100 is the smallest link that passed with both directions limited.
- **Download: 50 fails because the simulated downlink queue drops packets.** Shadow queues a node's incoming packets with CoDel: once packets have waited more than 10 ms for 100 ms, it drops packets at a rising rate until the wait is short again. A rerun on 512 nodes with packet captures shows it. At 50/100, packets sent in the first second wait up to 109 ms in a home node's queue (99th percentile), 1.5 to 2.2 of every 1,000 packets into home nodes are lost against 0.3 on the backbone alone, and TCP retransmits twice as many packets as at 100/100.
- **So the download limit depends on the queue.** A real line whose queue delays a burst instead of dropping from it may pass with less than 100. A home node takes in 41 Mbit/s over the 4 s when its downlink allows, so 50 leaves little room either way. Speeds between 50 and 100 were not tested.
- **DSL-grade nodes sit at the bar at 100/100.** Their line adds 13 ms each way, the most of the three types. They are complete in 99.6 % of node-slots with seed 1 and 99.3 % with seed 2. Counted as a group of their own, 279 and 293 nodes, they miss 99 % by one or two nodes in 3 and 8 of the 18 slots. At 1,000/75 and 1,000/100 every line type passes.

## Packet loss on the access line fails nodes at any speed

| Line of the node | Delay each way | Usual loss, home links at 1,000/200 | A fifth of the loss, 1,000/200 | No access loss, 1,000/100 |
| --- | --- | --- | --- | --- |
| Data-centre link, 742 nodes | None added | Backbone loss only: 99.9 (99.9) | 99.9 (99.6) | 99.98 (99.9) |
| Fiber-grade, 591 nodes | 4 ms | 0.05 % loss: 98.2 (97.4) | 0.01 % loss: 99.7 (99.3) | 99.9 (99.7) |
| Cable-grade, 436 nodes | 8 ms | 0.1 % loss: 79.0 (73.2) | 0.02 % loss: 98.2 (96.8) | 99.8 (99.5) |
| DSL-grade, 279 nodes | 13 ms | 0.25 % loss: 49.2 (44.1) | 0.05 % loss: 86.2 (81.4) | 99.6 (99.3) |

Each cell gives the line's packet loss per direction, then the percentage of node-slots complete at 8.0 s over slots 2–19, with the worst slot in brackets. All three runs use seed 1. On the usual lines, home links at 1,000/100 give the same picture: 98.3, 77.9 and 47.7 %. Sources: `pq1600split-access-S2048x20-h1000x200-s1.txt`, `…-h1000x200-al02-s1.txt` and `…-h1000x100-al0-s1.txt` (see Runs).

- **More upload does not help.** On the usual lines, 1,000/100 and 1,000/200 leave 78.8 % and 77.9 % of home nodes complete in the worst slot, with uplinks 26 % and 13 % busy over the 4 s.
- **Slower links do worse.** On the same lines, the 50/15 and 50/25 links of the earlier post reached 23 % and 53 %.
- **Loss on the access line is the cause.** Switching it off, with the line's latency and jitter kept, takes the same home nodes at 1,000/100 from 78.8 % to 99.7 %.
- **About 0.01 % per direction is what a line may lose.** With a fifth of the loss, fiber-grade nodes at 0.01 % pass with 99.3 % in the worst slot. Cable-grade nodes at 0.02 % miss the bar at 96.8 %, and the home nodes as one class reach 95.2 %. On 1,024 nodes the fiber-grade nodes are one node short of the bar in one slot.
- **The same loss costs more on a line with more delay.** At 0.05 %, DSL-grade nodes are complete in 86 % of node-slots and fiber-grade nodes in 98 %. Without loss the delay costs little, and DSL-grade nodes pass at 1,000/100.
- **Read the line types as loss and delay levels, not speeds.** The model draws a home node's line independently of its speed, and a real 100 Mbit/s uplink is fiber.
- **The model is probably harsher than real lines.** It drops each packet independently, and real lines lose packets in bursts, which costs TCP less at the same average rate. The [study's notes](../research/pq-gasper/gossipsub/p2psims/analysis/results-notes.md) also say the simulated TCP has no tail loss probe or RACK, so it repairs a loss at the end of a burst more slowly than Linux.

## The load is a burst: a home node uploads 33 Mbit/s over the 4 s and 71 to 94 in the first second

| Mbit/s, mean (90th percentile) | Upload over the 4 s | Upload in the first second | Download over the 4 s | Download in the first second |
| --- | --- | --- | --- | --- |
| Home node at 100/100, loss-free | 33 (46) | 71 (110) | 41 (65) | 60 (74) |
| Home node at 1,000/75, loss-free | 31 (43) | 79 (121) | 40 (56) | 76 (105) |
| Home node at 1,000/100, loss-free | 34 (47) | 94 (137) | 42 (58) | 89 (123) |
| Data-centre node in the 100/100 run | 56 (80) | 162 (252) | 36 (52) | 79 (113) |
| Data-centre node when 80 % of nodes are on 1 Gbit | 38 (56) | 125 (192) | 32 (47) | 90 (134) |

Percentiles are over node-slots, slots 2–19, seed 1. Upload is what the node hands to TCP. Sources: `specs-S2048x20-h100x100-al0-s1.txt`, its counterparts for the other runs, and `specs-step0-Q2048x20-m1600-fs75-s1.txt` (see Runs).

- **The first second sets the link.** Over the 4 s a home node uses a third of a 100 Mbit/s uplink and 41 % of the downlink. In the first second, a home node with 1,000 Mbit/s of download takes in 89 Mbit/s and hands TCP 94.
- **Per slot:** a home node at 100/100 downloads about 21 MB in the 4 s. It receives each message 5.5 times.
- **Data-centre nodes carry more.** They are 36 % of the nodes and send 49 % of the upload in the 100/100 run, 56 Mbit/s each against 33.
- **Validators don't change it.** In the run with 80 % of nodes on 1 Gbit, nodes with more than 8 validators stay within 4 % of the others, although they publish most signatures. The load is forwarding, so the requirement holds for any node in the subnet.

## CPU has room, and gossip needs tens of MiB

- **CPU:** the simulation charges 0.4 ms to verify a signature, so 1,600 signatures cost 0.64 core-seconds per slot. A home node verifies on 4 workers. The [calibration notes](../research/pq-gasper/gossipsub/results/realism-calibration.md) take the 0.4 ms from leanSig benchmarks of 0.19 to 0.39 ms on one Apple M1 core; that source was not re-checked for this note.
- **Five times slower verification still passes.** At 2 ms per signature, 100/100 has 5 of 1,302 home nodes incomplete in the worst slot, fewer than at 0.4 ms. Nodes then forward later, and they hand TCP 60 % of their uplink in the first second instead of 71 %.
- **Slow CPUs:** 232 of the home nodes verify three times slower. At 0.4 ms they do about as well as the others at 100/100: 99.69 % of their node-slots are complete with seed 1 and 99.65 % with seed 2, against 99.73 % and 99.76 %. In the 2 ms run they need 6 ms per signature, so 1,600 signatures take their 4 workers 2.4 s. They finish between 6.7 and 6.9 s, 1.1 s before the deadline, and still pass.
- **Where CPU would bind:** by the same arithmetic, the slow nodes run out of time at about 9 ms per signature on 4 workers. That is an extrapolation, not a run.
- **Memory:** the simulated node runs only the networking stack, built on rust-libp2p's gossipsub. At the end of the two 100/100 runs it held 89 and 91 MiB on average and 135 MiB at most. With 200 signatures per slot the earlier study's nodes held about 61 MiB, estimated from that run's peak memory, so the larger subnet adds about 30 MiB. Across all runs the average ranged from 80 to 102 MiB, and it was still rising slowly when each run ended. It is the simulator's memory, not a client's, so read it as tens of MiB.
- **Not covered:** aggregation is not part of the subnet's gossip and is not simulated.

## On 1,024 nodes, the verdicts are the same

The study was repeated on a network half the size. Only the node count changes: the slots, the 1,600 signatures per subnet per slot, the lines and the pass rule stay as above, so each run has a 2,048-node counterpart. The network has 366 nodes on 1 Gbit and 658 home nodes: 295 fiber-grade, 224 cable-grade and 139 DSL-grade, of which 152 have a slow CPU. A slot's signatures travel in about 211 messages instead of 302, because each publisher bundles more of them.

| Home lines and link | 2,048 nodes | 1,024 nodes |
| --- | --- | --- |
| Loss-free, 1,000/100 | Pass, 99.7 % (4 of 1,302) | Pass, 99.7 % (2 of 655) |
| Loss-free, 1,000/75 | Pass, 99.4 % (8 of 1,302) | Pass, 99.5 % (3 of 653) |
| Loss-free, 100/100 | Pass, 99.2 % (11 of 1,302) | Pass, 99.1 % (6 of 655) |
| Loss-free, 100/100, seed 2 | Pass, 99.4 % (8 of 1,319) | Pass, 99.4 % (4 of 656) |
| Loss-free, 100/100 at 2 ms | Pass, 99.6 % (5 of 1,302) | Pass, 99.8 % (1 of 653) |
| Loss-free, 1,000/50 | Fail, 96.2 % (50 of 1,302) | Fail, 96.8 % (21 of 654) |
| Loss-free, 50/100 | Fail, 77.8 % (289 of 1,303) | Fail, 81.0 % (124 of 654) |
| A fifth of the loss, 1,000/200 | Fail, 95.2 % (63 of 1,301) | Fail, 96.5 % (23 of 654) |
| Usual loss, 1,000/200 | Fail, 77.9 % (288 of 1,302) | Fail, 83.8 % (106 of 655) |
| Usual loss, 1,000/100 | Fail, 78.8 % (275 of 1,299) | Fail, 80.6 % (127 of 655) |
| Usual loss, 50/15 and 50/25 | Fail, 23 % and 53 % | Fail, 26 % and 53 % |
| Same, 80 % of nodes on 1 Gbit | Fail, 23 % and 53 % | Fail, 22 % and 48 % |

Home nodes complete at 8.0 s in each run's worst slot, with the incomplete nodes in brackets. One run per cell, slots 2–19, seed 1 unless the row says otherwise. 2 ms is the time to verify a signature, five times the modelled 0.4 ms. 50/15 and 50/25 are the home links of the earlier post. Of its two 2,048-node runs, the one with 36 % of nodes on 1 Gbit was analysed over slots 2–14. Sources: the `pq1600-S1024x20-…` and `pq1600-Q1024x20-…` counterparts of the files above (see Runs).

- **Every run agrees.** The same links pass and the same links fail, by similar margins.
- **100/100 passes with no node to spare.** With 655 home nodes online the bar allows 6 incomplete nodes in a slot, and the worst slot with seed 1 has 6. With seed 2 it has 4 of 656.
- **A node carries the same load.** At 100/100 a home node hands TCP 34 % of its uplink over the 4 s and 75 % in the first second, and it downloads 42 % and 62 % of its downlink. On 2,048 nodes these are 33, 71, 41 and 60 %. It receives each message 5.7 times, against 5.5, and the simulated node holds 86 MiB of memory, against 89.
- **Data-centre nodes pass in the ten runs that test a home link**, with a worst slot of 99.5 %. With the earlier post's links they miss the bar narrowly, at 98.9 %, as on 2,048 nodes. With 80 % of nodes on 1 Gbit they pass on both networks, at 99.5 % and 99.8 %.
- **With a fifth of the loss, the lines at 0.01 % are one node short.** Fiber-grade nodes have 3 of 293 incomplete in one slot, where the bar allows 2, and pass in the other 17 slots. On 2,048 nodes their worst slot was 99.3 %. Cable-grade nodes at 0.02 % reach 98.2 % and DSL-grade nodes at 0.05 % reach 85.5 %.
- **With loss, the smaller network completes a few points more:** 83.8 % against 77.9 % at 1,000/200 on the usual lines. A likely reason, not tested: a slot's signatures come in 211 messages instead of 302, so a lossy line has fewer to miss.
- **Slow CPUs finish at the same time.** At 2 ms per signature, the nodes that need 6 ms get their last signature at 6.9 s on both networks (99th percentile), and on 1,024 nodes all of them are complete in every slot.

## Runs

The 2,048-node study has eleven runs of 20 slots, on the network of the earlier post, at about 2 hours each. One of them, 1,000/400 on the usual lines, was stopped after 18 minutes because 100 and 200 already agreed. Two diagnostic runs used 512 nodes × 8 slots. The 1,024-node study has twelve runs of 20 slots, at about 60 to 75 minutes each: the ten completed runs again, and the earlier post's two runs with EIP-7870 links.

They ran one at a time on p2psims, a shared server with 96 CPUs and 503 GiB: the 2,048-node runs on 23 November 2026 between 01:54 and 21:45 CET, and the 1,024-node runs on 24 November between 01:20 and 14:06 CET. The machine's usual rules applied: at most 256 GB of RAM, CPUs 48–95 at nice 19, and half of that budget while another user is active. Memory peaked at 184 to 227 GiB in the 2,048-node runs, under the 235 GiB at which the watchdog stops a run, and at 88 to 120 GiB in the 1,024-node runs.

Each run's analysis is a set of files named `<script>-<RUN>.txt`, where a run is `S<nodes>x20-h<down>x<up>[-al0|-al02][-v2000]-s<seed>`: `al0` is no access loss, `al02` a fifth of it, and `v2000` verification at 2 ms. The files of every run are in [`p2psims/analysis/out/`](../research/pq-gasper/gossipsub/p2psims/analysis/out/), in the gossipsub study's folder. [`runs/queue-specs.txt`](../research/pq-gasper/gossipsub/p2psims/runs/queue-specs.txt) lists each 2,048-node run of this study with its flags, and each 1,024-node run uses the flags of its counterpart. The study's two reports have every table, for [2,048 nodes](../research/pq-gasper/gossipsub/results/pq-gasper-subnet-specs.md) and for [1,024 nodes](../research/pq-gasper/gossipsub/results/pq-gasper-subnet-specs-1024.md). [`charts/generate_charts.py`](charts/generate_charts.py) draws the chart.

Not run:

- 100/75, which would say whether 75 of upload is enough behind a 100 Mbit/s downlink.
- A download between 50 and 100.
- A third seed at 100/100, and a second seed for the other links.
- A network with fewer nodes on 1 Gbit.

## Risks

- **Real lossy lines may do better than the model.** The loss rates are estimates, each packet is dropped independently, and the simulated TCP repairs losses more slowly than Linux. Earliest signal: a node measured on a real cable or DSL line, or a testnet.
- **The download limit comes from the simulator's queue.** CoDel with a 10 ms target drops from the burst, and a deeper plain buffer would delay it. Earliest signal: the same measurement on a 50 Mbit/s line.
- **100/100 is close to the bar.** On 2,048 nodes it passes by two nodes with one seed and by five with the other, and on 1,024 nodes by none and by two. DSL-grade nodes alone sit at the bar. Another seed could miss by a node or two in one slot. The runs at 50 and 75 have one seed each.
- **The result assumes that 36 % of nodes are on 1 Gbit.** They send about half of the traffic. With fewer of them, each home node forwards more. No run tests this.

## Out of scope

- A node that joins several subnets. The load adds up per subnet joined.
- Aggregation, and the traffic after 8.0 s.
- Nodes with more than 8 validators on less than 1 Gbit. They stay on 1 Gbit in every run, as in the earlier post, so the runs don't test whether they could publish on a slower link.
