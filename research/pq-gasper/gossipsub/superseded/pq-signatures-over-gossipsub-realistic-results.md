# PQ signatures over gossipsub: realistic results

A running record of the realistic study on p2psims, last updated 2026-11-12. It covers the "one subnet per home staker" scenario under mainnet-calibrated network conditions. On a clean network (no loss, churn or background traffic), this scenario had already passed every cell. The full report is on p2psims and is updated as runs finish.

## Verdict

**Scope: these runs do not test one subnet of 2,000.** They split 2,000 signatures per slot across 16 subnets, 125 per subnet; only the 1 Gbit hosts, in all 16 subnets, take in all 2,000. PQ Gasper's load is about 32k per slot, 2,000 per subnet. One topic of 2,000 was the first study on p2psims (`results/gossip-2000.md`, `results/gossip-consolidation.md`, clean network): with bundles of 16 and 3 kB signatures, home hosts held every signature in 0.4–1.4 % of node·slots and 1 Gbit hosts in 99.8 %.

Bundling will be adopted whatever the results (Yann, 12 November), so the bundled cells decide the verdict. The unbundled results stay as context, and no more unbundled runs are planned.

- **On the build closest to a stock Linux host, 800k × 2.4 kB passes, bundled and unbundled.** That build, rtt6, has Linux's CUBIC and HyStart and restarts idle windows as Linux does by default, so no host setting is needed.
  - **With bundles of 16** it passes with more margin than on any other build: 2 of about 740 1 Gbit hosts are incomplete in its worst slot, where the rule allows 7, and completeness holds over the run. Over 50 slots on 1,024 hosts it passes on two seeds, with no step or decline, though each seed has one slot with no host to spare.
  - **Unbundled** it passes with 1 host to spare: 6 are incomplete in its worst slot. 1 Gbit completeness declines over the run, from 99.84 % in its first third to 99.50 % in its last, as on the fixed build and with the restart switched off, so the margin shrinks.
  - Home stakers get every signature of their subnet in every slot of both runs, and 1 Gbit hosts miss 0.0008–0.029 % of signatures.
- **The result depends on how TCP regrows a connection's window after it sits idle, and on Reno versus CUBIC.** In the model, connections idle about 1 s between bursts, longer than their retransmission timeout. Linux then restarts the window from 10 segments (`net.ipv4.tcp_slow_start_after_idle`, on by default); Shadow never does.
  - **With that restart and Reno** (rtt5 build), 800k × 2.4 kB fails on 1 Gbit hosts, unbundled and with bundles of 16: in the worst slot 12–15 of about 740 are incomplete, where the rule allows 7. Home stakers still get every signature of their subnet in every slot. 1 Gbit hosts miss 0.013–0.051 % of signatures, 50–200 times less often than attestations in the same runs.
  - **With that restart and only CUBIC's smaller cut** (rtt5b build: the window keeps 70 % after a loss instead of half, but still regrows as in Reno), the bundled cell passes with 2 hosts to spare: 5 of about 740 incomplete in its worst slot. 1 Gbit completeness holds over the run (99.71, 99.73 and 99.64 % across its thirds), where on rtt5 it kept falling.
  - **With the setting at 0** (cwv build: no restart, but the window grows only while the sender fills it, as in Linux), 800k × 2.4 kB unbundled passes with no host to spare: 7 of about 740 1 Gbit hosts are incomplete in its worst slot, the most the rule allows. 1 Gbit completeness declines over the run, from 99.91 % in its first third to 99.44 % in its last. This build still uses Reno; with CUBIC instead (cwv6), the 64-host check had the lowest block and signature latencies of any build.
  - **Without the restart or the window limit** (original and fixed builds), it passes, bundled or not; the fixed build has 2 hosts to spare.
  - **With that restart and Linux's CUBIC** (rtt6 build, the closest to a stock Linux host), both 800k cells pass. With bundles, 2 hosts are incomplete in the worst slot, against 5 on rtt5b, 12 on rtt5 and 3 on the original build. Unbundled, 6 are, against about 15 on rtt5, 7 with the setting at 0 (cwv), 5 on the fixed build and 7 on the original build. CUBIC cuts the window less after a loss and regrows it much faster than Reno. Mainnet data can't separate the builds (see Calibration).
- **Without slow start after idle, and with the default link mix, 2.4 kB signatures pass in every 20-slot cell but one,** with no gossipsub protocol or parameter change and each client's own scoring rules. That holds on the original and the fixed TCP build. On 2,048 hosts × 20 slots:
  - **800k validators, unbundled:** passes on two seeds. Seed 1 has zero margin: in its worst slot 7 of about 740 1 Gbit hosts are incomplete, the most the rule allows. Seed 2 has margin: 2 of 722. On the fixed TCP build, seed 1 has margin too: 5 in the worst slot.
  - **800k with 16-signature bundles:** passes with margin on two seeds, 3 hosts in the worst slot of each.
  - **600k:** passes, 3 of about 697 hosts in the worst slot.
  - **400k: fails in one slot, because of a single signature.** Its node had come back online 0.2 s before publishing and had no peer on its subnet yet, so gossipsub refused the publish and the signature never entered the network. That leaves every 1 Gbit host incomplete in slot 19. It is the only refused publish in 24 PQ runs; without it, the worst slot has 1 incomplete host.
- **The pass depends on how many hosts have 1 Gbit links.** By default every host with more than 8 validators and 20 % of the rest are on 1 Gbit, about 740 of 2,048 hosts. With only the hosts above 8 validators on 1 Gbit (about 413), 800k × 2.4 kB fails clearly: 1 Gbit hosts fall below 99 % in 16 of 18 slots, and in the worst slot about 14 are incomplete where the rule allows 4. Home stakers stay at 100 %. On the fixed TCP build it still fails in 16 of 18 slots, with 9 incomplete in the worst slot. The fix halves its PQ misses (0.049 / 0.084 % on 1 Gbit hosts), but without the extra 1 Gbit hosts the cell fails on both builds. With bundles of 16 on the CUBIC build it still fails, in 6 of 18 slots, with 7 incomplete in the worst slot where the rule allows 4, and 1 Gbit completeness falls over the run (99.36, 99.23 and 98.83 % across its thirds). Bundles halve the incomplete node·slots (64, against 126 unbundled on the fixed build) but don't restore the pass.
- **The 20-slot runs end before all scoring is active.** Mesh-delivery scoring (P3) on blocks and aggregates switches on one epoch after a peer joins a mesh, around slot 32. On mainnet most mesh links are older than that, so that is the steady state. In the 50-slot runs it rarely penalised anyone in Teku, Lodestar or Nimbus views, so it probably matters little.
- **Over 50 slots it passes; with bundles, with margin.** On 1,024 hosts at 800k unbundled, 1 Gbit completeness steps down around slot 33 and then holds flat, and five later slots have exactly the 3 incomplete hosts the rule allows. The cause of the step is unknown; the TCP timeout bug is a candidate. With bundles of 16, on the same hosts and seed, no slot has more than 2 incomplete hosts and there is no step. Only 5 node·slots are incomplete in slots 2–49, against 54 unbundled. On the CUBIC build the bundled run passes too, with no step and no decline (1 Gbit completeness 99.81 % in slots 2–15, 99.86 % in 40–49), but one slot has no host to spare and 30 node·slots are incomplete, against 5. A second seed passes too, with only 7 incomplete node·slots, but again one slot has no host to spare.
- **3 kB fails narrowly** at 800k, on 1 Gbit hosts only: below 99 % in 4 of 18 slots, by 2–3 hosts each time.
- **Home stakers** get every signature of their own subnet in every slot of every 20-slot run on the final model, apart from the 400k signature that never entered the network. In the unbundled 50-slot run, one 50/15 host missed once, by under 1 s; in the bundled one, none did.
- **The remaining misses** are on 1 Gbit hosts far from most peers, mostly Prysm hosts with 70 peers. Packet loss on long paths causes them. Shadow 3.3.0 recovers lost packets much more slowly than Linux (see below), which overstates some of them. On the fixed build, the 800k cell has 13 incomplete 1 Gbit node·slots in slots 2–15 instead of 35. In slots 16–19 it has 16 instead of 14: those misses start when mesh-delivery scoring switches on, on both builds. With Linux's slow start after idle added, there are 124 and 40 unbundled, and 75 and 37 with bundles. With the restart switched off but the window limited as in Linux, there are 26 and 22. With full CUBIC (rtt6) there are 24 and 16 unbundled, and 6 and 5 with bundles; with CUBIC's cut alone, 27 and 14 with bundles (rtt5b).
- **With Linux's default slow start after idle and Reno, 800k × 2.4 kB fails, bundled or not.** Linux halves a connection's window for every retransmission timeout it sits idle, down to 10 segments (`net.ipv4.tcp_slow_start_after_idle`, on by default); Shadow never shrinks it. In the model connections sit idle about 1 s between bursts, against a timeout of about 0.3 s, so on a build with this rule (rtt5) almost every burst starts from 10 segments.
  - On 2,048 hosts, unbundled, 1 Gbit hosts fall below 99 % in 12 of 18 slots, against none on the fixed build, with about 15 of 740 incomplete in the worst slot. With bundles of 16 it is 6 of 18 slots and 12 hosts, and 1 Gbit completeness is still falling at slot 19. The rule allows 7. Home stakers stay at 100 % in both.
  - Blocks take about twice as long to spread (p95 from publish 0.37 → 0.73 s), and PQ p99 latency on 1 Gbit hosts rises from 0.68 to 1.18 s.
  - The misses are like those in the cell with fewer 1 Gbit hosts: eight far-away hosts, seven of them Prysm with 70 peers, miss in 9–15 of 18 slots. On the fixed build they miss in at most 5.
  - This one rule carries the whole effect. With Linux's other window rule alone, which stops the window from growing while the sender doesn't fill it, the unbundled cell passes at 2,048 hosts, though with no host to spare. The setting acts on the sending side, so a far-away node gains only if its peers set it.
  - Mainnet data doesn't decide between the two builds (see Calibration).
  - rtt5 errs pessimistic. It uses Reno, which halves the window on each loss, where Linux's CUBIC keeps 70 %. Above ssthresh, Reno also grows the window by one segment per round trip, where CUBIC grows it back toward its size at the last loss by up to 1.5× per round trip. And it has no tail-loss probe. At 64 hosts, CUBIC's cut alone recovers a quarter to two fifths of the slowdown.
  - With CUBIC, as on stock Linux, it passes. CUBIC's smaller cut alone turns the bundled cell into a pass at 2,048 hosts, and the build with Linux's full CUBIC and its early slow-start exit (HyStart), rtt6, passes both cells: bundled with 5 hosts to spare, unbundled with 1.
- **Per signature:** across the 2.4 kB runs with the default link mix, 1 Gbit hosts miss 0.0001–0.056 % of PQ signatures, against 0.9–1.7 % of attestations in the runs without PQ.
- **At 800k unbundled on the current build, PQ load doubles attestation misses on 1 Gbit hosts,** from 1.02 % to 2.2–2.7 %, mostly on the 176 hosts in all 64 subnets. With bundles, at 600k and at 400k they stay at 0.9–1.75 %. On the fixed build they are 1.35–1.48 %, against 0.91–1.37 % without PQ, but home hosts' misses rise from about 0.02 % to 0.23–0.25 % in slots 2–15. On the window rules build they are 2.5–3.1 %, against 1.5–1.7 % without PQ. On the CUBIC build they are 1.5–2.1 %; its no-PQ run is queued. This matters only if BLS and PQ run side by side.
- **Home stakers in two subnets pass, with margin** (2sub: rtt6, bundles of 16, seed 1). Each of the 976 stakers also joins a second random PQ subnet and needs both.
  - Both home classes are complete in every slot. The 1 Gbit worst slot has 3 of 742 hosts incomplete, where the rule allows 7 (one subnet: 2), and there are 15 incomplete 1 Gbit node·slots (one subnet: 11). Late first deliveries stay at most 0.02 per 1 Gbit node per slot.
  - Staker upload in the 4–8 s window rises from 26.7 / 42.4 % to 37.8 / 57.8 % of the uplink (mean / busiest node), and in 4.0–5.0 s from 77 / 125 % to 110 / 189 %. Without PQ it is 13.4 / 21.5 % (rtt5 build). The second subnet adds 83 % of what the first did, partly because stakers' mesh per topic falls from 7.1 to 6.6 peers.
  - Staker PQ p99 latency rises from 0.58 to 0.79 s; block propagation and BLS misses don't change consistently.
- **Today's structure passes, at the limit for 50/15 hosts** (bb2: rtt6, bundles of 16, seed 1). Every home node joins two random backbone PQ subnets, and each staker also its duty subnet: 843 stakers in 3 subnets, 133 in 2, the 330 50/15 hosts in 2. Stakers need only their duty subnet; 50/15 hosts need both of theirs.
  - 50/15 hosts become the tightest class. Their worst slot, slot 2, is at 99.09 %: 3 of 330 incomplete, where the rule allows 3, all within 1 s of the deadline. From slot 3 only one 50/15 node·slot misses. Stakers' worst slot has 1 of 976 incomplete, on the duty subnet and on every subscribed subnet. 1 Gbit worst 5 of about 740 (slot 2), 13 incomplete node·slots.
  - Upload in the 4–8 s window (mean / busiest node): 50/15 58.5 / 90.0 %, and one node·slot had 127 % of the window's capacity to send; stakers 46.4 / 74.2 %. Each extra subnet adds about 80 % of the one-subnet PQ upload, so the second-subnet increment predicts this run within about a point.
  - Home PQ p99 latency is 0.97–1.06 s (one subnet 0.58–0.60). Negative-score peers and after-deadline copies grow in every class, and the first queue-full drops appear at homes. Late first deliveries stay at most 0.07 per node per slot, and blocks don't slow. Retransmission timeouts rise from 7.9 M to 13.4 M and retransmissions from 0.48 % to 0.66 % of data packets. Peak 232.9 GiB PSS.

**Pass rule.** From slot 2 on, every link class has at least 99 % of its nodes complete in every slot, and the backlog stays flat: signatures first arriving after the deadline, meshes, connections and failed sends don't keep growing. Late duplicate copies of signatures already held are reported as a cost but don't decide the verdict.

- Signatures go out 4.0–4.5 s into the slot. A node is complete when it holds every signature it needs at 8.0 s.
- Home hosts need their own subnet's signatures (125 per slot at 800k). 1 Gbit hosts need all 2,000.
- Signatures lost to churn don't count: their publisher was offline at publish time, or had no connections at all. Gossipsub refuses a publish when no connected peer is on the topic; if the publisher had connections, that counts as a network failure.

## Setup

- **Load:** 2,000 PQ signatures per slot on 16 subnets, so 125 per subnet. The 2,000 is an input: "800k validators" is a label carried over from the earlier study, and Gasper would send 25K per slot at 800k. leanVM's PQ Gasper design has 1,400 per subnet (716,800 validators), 11 times this. At 600k and 400k, each host's validator count is consolidated to match, giving 1,500 and 1,000 signatures per slot. 2.4 kB means 2,458 B; a leanXMSS signature is 2,404 B.
- **Background traffic:** today's BLS traffic runs alongside: 64 attestation subnets, aggregates, blocks, 128 data-column topics and the sync committee. Each host joins 2 attestation subnets, or all 64 if it has at least 64 validators (176 hosts at 800k).
- **Bundles:** each publishing host packs up to 16 of its own signatures into one message. That gives about 1,070 messages per slot instead of 2,000.
- **Hosts and links:** 2,048 hosts, with validator counts from the mainnet crawl.
  - Hosts with more than 8 validators are on 1 Gbit.
  - Of the rest, 80 % are on EIP-7870 links (50/25 Mbit/s with validators, 50/15 without) and 20 % on 1 Gbit. That puts about 740 hosts on 1 Gbit.
  - One sensitivity cell puts only the hosts above 8 validators on 1 Gbit, about 413.
- **Subscriptions:** home (EIP-7870) hosts join one subnet, the one their validators publish to. 1 Gbit hosts join all 16.
- **Peering:** comes from a peer manager, with discovery and churn; nothing is hand-wired. Each client uses its default peer target: Lighthouse, Lodestar and other 200, Nimbus 160, Teku 100, Prysm 70.
- **Gossipsub parameters:** each client's defaults. Lighthouse uses D = 5/3/10. The other clients use 8/6/12, and Teku, Lodestar and Nimbus also flood-publish.
- **Scoring:** each client's own rules, checked in source ([comparison](../results/gossipsub-scoring-by-client.md)). PQ topics use Lighthouse's attestation-subnet formula, with the expected rate set to the run's mean messages per subnet per slot.
- **Perturbations:**
  - latency: a 12-city WonderNetwork RTT matrix weighted by Probelab node shares, plus access latency and jitter;
  - packet loss;
  - churn: connection churn, restarts, joins and leaves;
  - verification delay and slow CPUs;
  - NAT;
  - invalid publishers and free-riders.
- **Simulator:**
  - Shadow 3.3.0, patched for send size, upload caps and jitter;
  - wbsim on libp2p-gossipsub 0.49.5, with per-client scoring patches.

## Calibration against mainnet

No PQ, 2,048 hosts × 20 slots, client default peer targets. *First calibration* used Lighthouse's scoring on every host; *final model* uses each client's own rules; *fixed TCP* is the final model on the rtt4 build; *window rules* is the final model on the rtt5 build.

| metric | mainnet | first calibration | final model | fixed TCP | window rules |
| --- | --- | --- | --- | --- | --- |
| block first seen from slot start, p50 / p90 / p99 | 2.06 / 3.51 / 4.52 s | 1.84 / 2.88 / 4.48 s | 1.80 / 2.85 / 4.46 s | 1.81 / 2.86 / 4.46 s | 2.08 / 3.05 / 4.83 s |
| block first seen from publish, p95 / p99 | relay P95 0.82 s (see below) | – | 0.34 / 0.44 s | 0.38 / 0.47 s | 0.90 / 1.09 s |
| attestation arrival after the 4 s mark, mean (model: p50) / p95 | 0.83 / 1.96 s | 0.94 / 1.93 s | 0.94 / 1.94 s | 0.94 / 1.94 s | 0.97 / 2.08 s |
| copies received per block / per attestation | 3 / 2 | 3.74 / 2.17 | 3.74 / 2.45 | 3.73 / 2.35 | 3.87 / 2.46 |
| data columns, p50 / p95 | 1.78 / 3.2 s | 1.85 / 4.41 s | 1.86 / 4.41 s | 1.86 / 4.42 s | 1.94 / 4.38 s |
| home download: blocks, attestations and columns | 163 kB/s | 142 kB/s | 143 kB/s | 143 kB/s | 151 kB/s |

- **Tolerance:** ±20 % on medians, ±30 % on tails, duplicates and bandwidth. All four models are within it except for the column p95. Block propagation from publish has no directly comparable mainnet figure (see below).
  - In the model only the proposer publishes columns, so a late block delays its columns. On mainnet, nodes also rebuild them from the mempool (getBlobsV2).
  - This gap makes the model pessimistic.
- **Block propagation from publish:** in the final and fixed-TCP models, blocks reach almost every node within about 0.4 s of publish, so block arrival times mostly reflect the fitted publish times. The window rules build (see Caveats) takes 2.4× as long, and the ratio doesn't grow over the run. At 64 hosts the CUBIC build spreads blocks about as slowly as the window rules build.
  - Mainnet's only comparable figure is a P95 of 0.82 s from a relay timestamp to arrival at 138 observer nodes, for blocks from the Ultrasound, Flashbots and Titan relays between 29 July and 5 August 2025.
  - The relay timestamp marks the relay's reply to the proposer. Relays also publish the block through their own beacon nodes, and Flashbots' relay does so before replying, so the offset to the first gossip publish can have either sign.
  - Read as gossip-only, the fixed build reaches 46 % of mainnet's figure and the window rules build 110 %. But mainnet is about one gossip hop deeper than 2,048 hosts, and the model gives each node only 10 ms to handle a block before forwarding it. Both lengthen mainnet's tail whatever the TCP, so this figure doesn't pick a build.
  - At 64 hosts the window rules build had pushed attestation p95 after the 4 s mark to 2.69 s. At 2,048 hosts it is 2.08 s, within tolerance of mainnet's 1.96 s.
- **Peer targets:** at a quarter of the default targets, all-subnet hosts missed 4.9 % of attestations. So every result here uses the full targets.
- **Packet loss:** the model with loss counts as the calibrated one. With loss off:
  - timing stays within mainnet's numbers;
  - attestation copies rise to 2.95 and block copies to 4.17;
  - home download falls to 122 kB/s.

  Loss also stretches the far tail: attestation p99 is 2.76 s with loss and 2.30 s without. Mainnet data doesn't cover that tail. Mainnet attestation figures: [Silva, ethresear.ch](https://ethresear.ch/t/an-analysis-of-attestation-timings-in-a-6-s-slot/23016).

## Results: 2,048 hosts × 20 slots

1 Gbit hosts are the only class that misses. Home classes are at least 99.7 % complete in every slot of every run below, and 100 % in every slot on the final model. Two-number cells give slots 2–15 / slots 16–19.

| cell | scoring | 1 Gbit complete | worst slot (incomplete hosts) | PQ missed, 1 Gbit | attestations missed, 1 Gbit | verdict |
| --- | --- | --- | --- | --- | --- | --- |
| 800k × 2.4 kB, fixed TCP (rtt4) | final | 99.87 / 99.46 % | 99.32 % (5) | 0.0014 / 0.020 % | 1.48 / 1.35 % | **pass** |
| 800k × 2.4 kB, slow start after idle off (cwv) | final | 99.75 / 99.26 % | 99.05 % (7) | 0.0032 / 0.020 % | 2.01 / 2.48 %³ | **pass, no margin** |
| 800k × 2.4 kB, window rules (rtt5) | final | 98.80 / 98.65 % | 97.97 % (about 15) | 0.032 / 0.051 % | 2.54 / 2.57 % | fail, 12 of 18 slots |
| 800k × 2.4 kB, bundles of 16, window rules (rtt5) | final | 99.28 / 98.75 % | 98.38 % (12) | 0.013 / 0.025 % | 2.69 / 3.10 % | fail, 6 of 18 slots |
| 800k × 2.4 kB, bundles of 16, window rules with CUBIC's cut (rtt5b) | final | 99.74 / 99.53 % | 99.33 % (5) | 0.0031 / 0.0068 % | 2.14 / 2.27 %³ | **pass** |
| 800k × 2.4 kB, CUBIC build (rtt6) | final | 99.77 / 99.46 % | 99.19 % (6) | 0.0060 / 0.029 % | 1.81 / 2.13 %³ | **pass** |
| 800k × 2.4 kB, bundles of 16, CUBIC build (rtt6) | final | 99.94 / 99.83 % | 99.73 % (2) | 0.0008 / 0.0033 % | 1.48 / 1.79 %³ | **pass** |
| 800k × 2.4 kB, bundles of 16 | final | 99.87 / 99.73 % | 99.59 % (3) | 0.0024 / 0.0028 % | 1.56 / 1.75 % | **pass** |
| 800k × 2.4 kB, bundles of 16, seed 2 | final | 99.94 / 99.90 % | 99.58 % (3) | in report | in report | **pass** |
| 800k × 2.4 kB | final | 99.66 / 99.53 % | 99.05 % (7) | 0.010 / 0.021 % | 2.42 / 2.66 % | **pass, no margin** |
| 800k × 2.4 kB, seed 2 | final | 99.96 / 99.90 % | 99.72 % (2) | 0.0001 / 0.0018 % | 2.17 / 2.13 % | **pass** |
| 600k × 2.4 kB | final | 99.89 / 99.78 % | 99.57 % (3) | 0.0030 / 0.0024 % | 0.91 / 1.31 % | **pass** |
| 400k × 2.4 kB | final | 99.88 / 99.88 %¹ | 99.84 % (1)¹ | 0.0039 / 0.0030 %¹ | 1.05 / 1.14 % | fail, slot 19 only¹ |
| 800k × 2.4 kB, 1 Gbit only above 8 validators | final | 98.36 / 97.15 % | 96.6 % (\~14) | 0.093 / 0.164 % | 2.36 / 2.68 %² | fail, 16 of 18 slots |
| 800k × 2.4 kB, 1 Gbit only above 8 validators, fixed TCP (rtt4) | final | 98.39 / 98.00 % | 97.82 % (9) | 0.049 / 0.084 % | 2.59 / 2.94 %² | fail, 16 of 18 slots |
| 800k × 2.4 kB, bundles of 16, 1 Gbit only above 8 validators, CUBIC build (rtt6) | final | 99.21 / 98.91 % | 98.30 % (7) | 0.021 / 0.019 % | 1.97 / 2.50 %² | fail, 6 of 18 slots |
| no PQ | final | – | – | – | 1.02 / 1.03 % | baseline |
| no PQ, fixed TCP (rtt4) | final | – | – | – | 0.91 / 1.37 % | baseline |
| no PQ, window rules (rtt5) | final | – | – | – | 1.53 / 1.67 % | baseline |
| 800k × 3 kB | final | 99.46 / 98.82 % | 98.65 % | 0.015 / 0.039 % | 1.51 / 1.85 % | fail, 4 of 18 slots |
| 800k × 3 kB, bundles of 16 | slow-peer fix only | 99.22 / 99.22 % | 98.78 % | 0.053 / 0.051 % | 2.58 / 1.85 % | fail, 2 slots |
| 800k × 3 kB | slow-peer fix only | 98.90 / 97.74 % | 97.57 % | 0.054 / 0.149 % | 3.51 / 3.29 % | fail |
| 800k × 3 kB | Lighthouse rules everywhere | 98.78 / 98.31 % | – | 0.068 / 0.177 % | 2.95 / 3.84 % | fail |

- **Run names in the report,** top to bottom: R20-2k4-rtt4, R20-2k4-cwv, R20-2k4-rtt5, R20-b16-2k4-rtt5, R20-b16-2k4-rtt5b, R20-2k4-rtt6, R20-b16-2k4-rtt6, R20-b16-2k4-cf2 (seeds 1 and 2), R20-2k4-cf2 (seeds 1 and 2), R20-v600-2k4-cf2, R20-v400-2k4-cf2, R20-fs0-2k4-cf2, R20-fs0-2k4-rtt4, R20-fs0-b16-2k4-rtt6, R20-nopq-cf2, R20-nopq-rtt4, R20-nopq-rtt5, R20-cf2, R20-b16-cf, R20-cf, R20-age60. All use seed 1 except the seed 2 rows. All but the three rtt4 runs, the cwv run, the three rtt5 runs, the rtt5b run and the three rtt6 runs use the current TCP build.
- **Scoring models:**
  - *Final* applies each client's own rules.
  - *Slow-peer fix only* limits the slow-peer penalty to Lighthouse and Grandine and keeps Lighthouse's other rules on every host.
  - *Lighthouse rules everywhere* applies Lighthouse's scoring on every host.
- **400k¹:** the figures leave out one slot-19 signature that reached nobody. Its publisher (Lighthouse, 50/25, Singapore) came online 0.20 s before publishing, and gossipsub refused the publish because no connected peer was on its subnet.
  - Connections are logged every 0.5 s: 0 at 262.00 s, 6 at 262.50 s. About 6 of its 116 dials could have completed by the publish at 262.42 s, so it probably had connections, and the refusal counts as a network failure.
  - Counted, it leaves every 1 Gbit host, and every home host on that subnet, incomplete in slot 19. In every other slot, 1 Gbit hosts are at least 99.84 % complete.
- **1 Gbit only above 8 validators²:** this cell has no matched no-PQ baseline; the no-PQ row uses the default link mix.
- **cwv, rtt5b and rtt6³:** there is no no-PQ run on these builds yet, so their attestation figures have no matched baseline. One on rtt6 is queued.
- **PQ missed** counts messages, so in bundled runs it is the share of bundles missed; a bundle carries up to 16 signatures.
- **Attestations on home hosts:** 0.015–0.03 % missed without PQ, 0.02–0.07 % with it, and 0.09–0.15 % in the cell with fewer 1 Gbit hosts.
  - On the fixed TCP build: 0.02–0.03 % without PQ in slots 2–15, and 0.23–0.25 % with it. So PQ adds about 0.2 points on the fixed build, against 0.04 on the current one.
  - On the window rules build: 0.03–0.06 % without PQ and 0.09–0.20 % with it.
  - In slots 16–19 of the fixed-TCP no-PQ run, 0.07–0.08 % of home deliveries never arrive; the current and window rules builds lose none. The cause is unknown.

**Load at 2.4 kB, unbundled, seed 1:**

- **Upload in the 4 s window, mean / busiest host:** 50/15 45 / 68 %, 50/25 28 / 44 %, 1 Gbit 6 / 13 % of the cap. Without PQ, on the same hosts and seed, it is 21 / 32 %, 13 / 20 % and 1 / 8 %, so signatures are about half of home upload in that window, and a fifth over the whole slot.
- **The first second after publish is the peak:** home hosts write 130 % (50/15) and 83 % (50/25) of what their uplink carries in that second on average, and the busiest 206 % and 135 %; the rest waits in socket buffers. Signatures are about 60 % of it. Home hosts still get every signature.
- **Latency from publish, p99:** 0.61 s (50/15), 0.51 s (50/25), 0.66 s (1 Gbit).
- **Bytes received per useful byte,** including background traffic: 9.4 → 10.3.
- **No backlog:** meshes, connections and failed sends stay flat. Late duplicate copies on 1 Gbit hosts level off at 1.3–1.6 MB per node per slot from slot 12, on both seeds.
- **Cost:** peak memory 224.6 GiB PSS, 3.3 h of wall time.
- **1 Gbit completeness per slot, slots 0–19:** 99.73, 99.86, 99.73, 100, 99.86, 99.86, 99.86, 99.59, 99.73, 99.46, 99.86, 99.73, 99.73, **99.05**, 99.46, 99.32, 99.32, 99.73, 99.59, 99.46.

**Fixed TCP build (rtt4), 800k × 2.4 kB, unbundled, seed 1:**

- **Completeness:** home hosts 100 % in every slot. The worst 1 Gbit slots are 17 and 18, at 99.32 % (5 hosts).
- **Where the fix helps:** slots 2–15 have 13 incomplete 1 Gbit node·slots instead of 35. No host misses in 9 or more slots. The Singapore Prysm host that missed in 15 of 18 slots on the current build misses none.
- **Where it doesn't:** slots 16–19 have 16 incomplete node·slots instead of 14. Those misses start when mesh-delivery scoring switches on (see What causes the misses).
- **Attestations:** 1 Gbit hosts miss fewer (1.48 / 1.35 % against 2.42 / 2.66 %), and home hosts more in slots 2–15 (0.23 / 0.25 % against 0.07 / 0.06 %). Without PQ, the fixed build's home misses in slots 2–15 are 0.025 / 0.022 %, like the current build's, so the rise comes from the build together with the PQ load.
- **No backlog:** links per node stay at 209–236. Late duplicate copies on 1 Gbit hosts level off at 1.07–1.19 MB per host per slot, against 1.4–1.6 MB.
- **Cost:** peak memory 224.4 GiB PSS, 3.3 h of wall time.

**Slow start after idle switched off (cwv), 800k × 2.4 kB, unbundled, seed 1: passes, with no host to spare.** This is Linux's window validation without its restart after idle, as on a Linux host with `net.ipv4.tcp_slow_start_after_idle = 0`.

- **Completeness:** home hosts 100 % in every slot, missing no signatures. The worst 1 Gbit slot is 18, at 99.05 % (7 of about 740 hosts, the most the rule allows).
- **Over the run:** 1 Gbit completeness falls from 99.91 % in slots 2–7 to 99.57 % in 8–13 and 99.44 % in 14–19; on the fixed build it is 99.93, 99.82 and 99.59 %. PQ misses on 1 Gbit hosts rise once mesh-delivery scoring switches on, from 0.0032 % in slots 2–15 to 0.020 % in 16–19, as on the fixed build; no slot exceeds 0.025 %.
- **Against the fixed build:** 48 incomplete 1 Gbit node·slots instead of 29, and 19 hosts ever incomplete instead of 12. None misses in 9 or more slots.
- **TCP:** windows stay bounded. Between 1 Gbit hosts the median window is 76 segments and the 90th percentile 239, against 300 and 9,438 on the fixed build. Blocks spread 7–14 % slower than on the fixed build (p95 from publish 0.42 s against 0.37 s).
- **Attestations:** 1 Gbit hosts miss 2.01 / 2.48 %. There is no no-PQ run on this build to compare with.
- **No backlog on 1 Gbit hosts:** their late copies are flat from slot 9, at 0.87–1.04 MB per host per slot. On home hosts, late copies rise by about 3 kB per slot, to 64–78 kB by slot 19, as on the fixed and window rules builds. All are duplicates of signatures already held; the 50-slot runs will show whether the home figure levels off.
- **Cost:** peak memory 223.4 GiB PSS, 3.3 h of wall time.

**Window rules build (rtt5), 800k × 2.4 kB, unbundled, seed 1: fails.**

- **Completeness:** home hosts 100 % in every slot. 1 Gbit hosts are below 99 % in 12 of 18 slots, every slot from 7 on except 11. The worst is slot 8, at 97.97 % (about 15 hosts).
- **Over the run:** 1 Gbit completeness steps down once after slot 7 and then holds: 99.08 % in slots 2–7, 98.60 % in 8–13 and 98.63 % in 14–19. PQ misses on 1 Gbit hosts keep rising: 0.019, 0.035 and 0.056 % in the same blocks. Slots 15–19 include the switch-on of mesh-delivery scoring, and 20 slots can't show whether the misses level off.
- **Who misses:** of 742 hosts on 1 Gbit, 32 miss at least once. Eight miss in 9–15 of 18 slots: Prysm hosts with 70 peers in Sydney (three), Singapore (two), Seoul and São Paulo, and a Lighthouse host in Sydney. On the fixed build the same hosts miss in at most 5 slots.
- **Mesh-delivery scoring:** PQ deficits grow after it switches on, from 804 to 926 per slot; on the fixed build they fall, from 784 to 594.
- **Latency from publish:** blocks p50 / p95 / p99 0.34 / 0.73 / 0.93 s, against 0.19 / 0.37 / 0.48 s on the fixed build; PQ p99 0.84 / 0.82 / 1.18 s (50/15, 50/25, 1 Gbit), against 0.64 / 0.51 / 0.68 s. Block propagation is 2.2× the fixed build's in slots 2–7 and 1.7× after, so the slowdown doesn't grow.
- **Attestations:** 1 Gbit hosts miss 2.54 / 2.57 %, home hosts 0.09–0.20 %. Without PQ on the same build they miss 1.53 / 1.67 % and 0.03–0.06 %, so in slots 2–15 PQ adds about 1 point on 1 Gbit hosts and 0.05–0.13 points at home.
- **No backlog:** links per node stay at 205–232. Late duplicate copies on 1 Gbit hosts level off at 1.1–1.3 MB per host per slot.
- **Cost:** peak memory 228.3 GiB PSS, 3.3 h of wall time.

**Window rules build (rtt5), 800k × 2.4 kB with bundles of 16, seed 1: fails.**

- **Completeness:** home hosts 100 % in every slot. 1 Gbit hosts are below 99 % in 6 of 18 slots (8, 14, 15, 16, 18 and 19). The worst is slot 16, at 98.38 % (12 hosts, where the rule allows 7).
- **Against the unbundled run on this build:** 112 incomplete 1 Gbit node·slots instead of 164, and about half the PQ misses (0.013 / 0.025 %).
- **Over the run, 1 Gbit completeness keeps falling:** 99.48 % in slots 2–7, 99.19 % in 8–13 and 98.81 % in 14–19. PQ misses rise from 0.008 % to 0.012 % and 0.026 %. Block propagation doesn't slow further. Two things change at the same time:
  - ssthresh between 1 Gbit hosts keeps falling, from 185 segments at slot 7 to 64 at slot 18. In the unbundled run it fell earlier, and completeness stepped down earlier; then both levelled off.
  - Mesh-delivery scoring switches on from slot 15, and PQ deficits grow from 1,387 to 2,424 per slot.
- **Who misses:** 30 of 742 1 Gbit hosts miss at least once, 18 of them Prysm. A Lighthouse host in Sydney with 200 peers misses in 11 of 18 slots, as it did unbundled. The next are hosts in São Paulo, Seoul, Singapore and Tokyo, missing in 6–8 slots, most of them Prysm with 70 peers.
- **Attestations:** 1 Gbit hosts miss 2.69 / 3.10 %, home hosts 0.06–0.29 %. Against the matched no-PQ run, PQ adds 1.2–1.4 points on 1 Gbit hosts and up to 0.24 points at home, mostly in slots 3–12; the cause is unknown.
- **No backlog:** links per node stay at 210–233. Late duplicate copies on 1 Gbit hosts level off at 1.2–1.3 MB per host per slot. On home hosts they are still rising slowly, at 73–78 kB.
- **Cost:** peak memory 220.6 GiB PSS, 3.1 h of wall time.

**Window rules build with CUBIC's cut (rtt5b), 800k × 2.4 kB with bundles of 16, seed 1: passes.** This is rtt5 with one change: after a loss the window keeps 70 %, as in CUBIC, instead of half. Growth is still Reno's.

- **Completeness:** home hosts 100 % in every slot. The worst 1 Gbit slot is 19, at 99.33 % (5 of about 740 hosts; the rule allows 7). 1 Gbit completeness holds over the run: 99.71 % in slots 2–7, 99.73 % in 8–13 and 99.64 % in 14–19.
- **Against rtt5 with the same bundles:** 41 incomplete 1 Gbit node·slots instead of 112, 13 hosts ever incomplete instead of 30, and about a quarter of the PQ misses (0.0031 / 0.0068 %). One Prysm host in São Paulo with 70 peers misses in 10 of 18 slots.
- **TCP:** ssthresh still falls over the run but stays higher than on rtt5, 1.4× between 1 Gbit hosts by slot 18. Blocks spread 6–11 % faster than on rtt5 and still 1.6–2.0× slower than on the original build.
- **Attestations:** 1 Gbit hosts miss 2.14 / 2.27 %, home hosts 0.12–0.15 %. There is no no-PQ run on this build to compare with.
- **No backlog:** late copies on 1 Gbit hosts level off at 0.96–1.19 MB per host per slot from slot 10. On home hosts they rise from 11–12 kB to 44–53 kB, as on every build. All are duplicates.
- **Cost:** peak memory 219.0 GiB PSS, 3.2 h of wall time.

**CUBIC build (rtt6), 800k × 2.4 kB with bundles of 16, seed 1: passes, with 5 hosts to spare.** This is rtt5 with Linux's CUBIC (v6.12) and HyStart in place of Reno; windows restart after idle as on a stock Linux host.

- **Completeness:** home hosts 100 % in every slot. The worst 1 Gbit slots are 16 and 19, at 99.73 % (2 of about 740 hosts; the rule allows 7). 1 Gbit completeness holds over the run: 99.93 % in slots 2–7, 99.98 % in 8–13 and 99.84 % in 14–19.
- **Against the same cell on other builds:** 11 incomplete 1 Gbit node·slots, against 41 on rtt5b, 112 on rtt5 and 21 on the original build. They fall on 6 hosts; the most frequent, in Seoul, misses in 5 of 18 slots. 1 Gbit hosts miss 0.0008 / 0.0033 % of PQ signatures, a quarter to a half of rtt5b's. PQ p99 from publish is 0.60 / 0.58 / 0.68 s (50/15, 50/25, 1 Gbit), against 0.62 / 0.59 / 0.78 s on rtt5b.
- **TCP:** ssthresh at restarts between 1 Gbit hosts stops falling at 85–91 segments from slot 9. On paths with a home end it still falls slowly, but ends above rtt5b's. About 70 % of data goes out with the window at or above ssthresh, where CUBIC's growth applies.
- **Blocks:** p95 from publish is 0.65 s, 1.7–2.0× the original build's and within 3 % of rtt5b's. A block is a short burst after idle that mostly ends in slow start, so CUBIC's growth doesn't shorten it.
- **Attestations:** 1 Gbit hosts miss 1.48 / 1.79 %, home hosts 0.03–0.12 %. There is no no-PQ run on this build yet to compare with.
- **No backlog:** signatures first arriving after the deadline round to 0 per host in every slot. Late duplicate copies on 1 Gbit hosts level off at 0.85–1.06 MB per host per slot from slot 9, still growing about 16 kB per slot, like rtt5b's and about half the original build's. On home hosts they grow about 1 kB per slot, the least of any build.
- **Cost:** peak memory 218.5 GiB PSS, 3.0 h of wall time.

**CUBIC build (rtt6), 800k × 2.4 kB, unbundled, seed 1: passes, with 1 host to spare.**

- **Completeness:** home hosts 100 % in every slot, missing no signatures. The worst 1 Gbit slot is 19, at 99.19 % (6 of about 740 hosts; the rule allows 7), then slot 18 at 99.32 % (5).
- **Over the run, 1 Gbit completeness declines:** 99.84 % in slots 2–7, 99.75 % in 8–13 and 99.50 % in 14–19, as on the fixed build (99.93, 99.82, 99.59 %) and with the restart switched off (99.91, 99.57, 99.44 %). PQ misses on 1 Gbit hosts rise from 0.0015 % to 0.0099 % and 0.022 % over the same thirds; the last includes the switch-on of mesh-delivery scoring.
- **Against the same cell on other builds:** 40 incomplete 1 Gbit node·slots on 16 hosts, against 48 with the restart switched off, 29 on the fixed build and 164 on rtt5. One Prysm host in São Paulo with 70 peers misses in 11 of 18 slots; it was also the host that missed most at 400k. The others are far-away hosts, mostly Prysm.
- **Latency from publish, p99:** 0.78 / 0.72 / 0.92 s (50/15, 50/25, 1 Gbit), against 0.62 / 0.59 / 0.76 s with the restart switched off and 0.84 / 0.82 / 1.18 s on rtt5.
- **Blocks:** p95 from publish is 0.69 s, 1.7–2.0× the fixed build's and 2–9 % below rtt5's, so CUBIC's growth barely shortens them.
- **TCP:** ssthresh at restarts between 1 Gbit hosts settles at 78–85 segments from slot 10; on paths with a home end it still falls but ends above rtt5's. 75 % of data goes out with the window at or above ssthresh.
- **Attestations:** 1 Gbit hosts miss 1.81 / 2.13 %, home hosts 0.015–0.035 %. The no-PQ run on this build is queued.
- **No backlog:** signatures first arriving after the deadline average 0.11 per 1 Gbit host per slot in slots 2–15 and 0.57 in slots 16–19, at most 0.74 and never more than the misses at 8 s; home hosts get none. Late duplicate copies grow about 19 kB per slot on 1 Gbit hosts over slots 10–19 and about 1 kB on home hosts.
- **Cost:** peak memory 227.5 GiB PSS, 3.3 h of wall time.

## 50 slots, 1,024 hosts

**800k × 2.4 kB, unbundled, final model, seed 1: passes, at the limit after slot 33.** At 1,024 hosts the rule allows 3 incomplete 1 Gbit hosts out of about 366.

| slots | 2–15 | 16–29 | 30–39 | 40–49 |
| --- | --- | --- | --- | --- |
| 1 Gbit complete, mean | 99.84 % | 99.84 % | 99.51 % | 99.48 % |
| PQ missed, 1 Gbit | 0.0039 % | 0.0015 % | 0.045 % | 0.033 % |
| attestations missed, 1 Gbit | 1.21 % | 1.44 % | 1.66 % | 1.38 % |
| late PQ copies, kB per 1 Gbit host per slot | 880 | 1,339 | 1,484 | 1,562 |

- **Home stakers:** 50/25 hosts are 100 % complete in every slot; 50/15 hosts too, except one host's near miss in slot 37.
- **Worst slots:** 99.18 % (3 hosts) in slots 33, 37, 41, 42 and 44.
- **It levels off:**
  - Completeness is flat after the step: −0.02 points per 10 slots over slots 30–49.
  - Links per node (214 → 218) and the 1 Gbit PQ mesh degree (6.97 → 6.86) are flat.
  - Late copies are mostly duplicates; they still grow, but by less in each block of slots. On home hosts, in kB per host per slot over slots 2–9, 10–19, 20–29, 30–39 and 40–49, they are 48, 76, 91, 84 and 94 on 50/15 links, and 36, 62, 74, 75 and 88 on 50/25. That is 1–3 kB more per slot up to slot 20 and 0.1–0.7 kB per slot after.
  - Signatures first arriving after the deadline step up with completeness around slot 33 and then hold: 0.01, 0.10, 0.01, 0.65 and 0.65 per 1 Gbit host per slot over slots 2–9, 10–19, 20–29, 30–39 and 40–49, at most 1.54 (slot 34), never more than the misses at 8 s. Copies older than 60 s also arrive, up to 5.3 per host per slot, and hosts drop them as stale; on the CUBIC build none arrive.
- **Scoring:**
  - PQ and attestation deficits fall after their activation peak.
  - Block-topic deficits appear in slots 30–39 (12 per slot, then 24) and are still rising slowly.
  - Negative-score peers fall in Lighthouse views (11.3 → 8.5 per observer) and rise slowly in Teku, Lodestar and Nimbus views (0 → about 1.0–1.2, slowing).
- **The step around slot 33 is unexplained.** It isn't mesh-delivery scoring on blocks and aggregates, which switches on then.
  - The four hosts that miss most often (Prysm in Sydney, Tokyo and Seoul; Lighthouse in Sydney) are pruned less after slot 33, fewer peers score them negative, and they keep their inbound PQ mesh links.
  - Block and aggregate deficits are rare in Teku, Lodestar and Nimbus views.
  - The step amounts to about one more incomplete host per slot. The bundled run below, on the same hosts and seed, has no step. One candidate is the TCP timeout ratchet described below; an unbundled 50-slot run on the CUBIC build, which has no such stalls, would tell, but none is planned now. After the step, 21 of the 28 incomplete 1 Gbit node·slots in slots 33–44 are followed 5–11 slots later by copies more than 60 s old arriving at the same host, against 26–28 % of the same hosts' complete node·slots. So most of those misses fall in stalls of over a minute on connections into the missing host, the kind the ratchet produces. But such stalls begin around slot 10, well before the step, and the fixed build has about half as many.
- **Cost:** peak memory 125 GiB PSS, 4.4 h of wall time.

**800k × 2.4 kB with bundles of 16, final model, seed 1: passes with margin, and levels off.** Same hosts and seed as the unbundled run.

| slots | 2–15 | 16–29 | 30–39 | 40–49 |
| --- | --- | --- | --- | --- |
| 1 Gbit complete, mean | 99.96 % | 100 % | 100 % | 99.92 % |
| PQ missed, 1 Gbit | 0.0014 % | 0 | 0 | 0.0012 % |
| attestations missed, 1 Gbit | 0.79 % | 1.21 % | 1.38 % | 1.13 % |
| late PQ copies, kB per 1 Gbit host per slot | 864 | 1,234 | 1,377 | 1,488 |

- **Home stakers:** 100 % complete in every slot. They miss at most 0.12 % of attestations.
- **Worst slot:** 99.45 % (2 hosts), in slot 49. Only 5 node·slots are incomplete in slots 2–49, against 54 unbundled. No host misses in more than 3 slots, and there is no step around slot 33.
- **Scoring:**
  - PQ delivery deficits peak at slot 20 (2,731 per slot) and decline to 1,472 by slot 49. They are about 9× the unbundled run's, three quarters of them in Lighthouse views, where a full deficit costs little.
  - Negative-score peers in Teku, Lodestar and Nimbus views still rise slowly at slot 49 (+14–27 % per 10 slots), but stay below the unbundled run's: 0.72–1.05 against 0.98–1.24 per observer in slots 40–49.
- **No backlog:** links per node stay at about 218. Late copies are duplicates and grow by less in each block of slots (+370, +143, +111 kB). On home hosts, over slots 2–9, 10–19, 20–29, 30–39 and 40–49, they are 23, 32, 38, 35 and 44 kB per host per slot on 50/15 links, and 19, 30, 37, 43 and 44 on 50/25, flat on 50/25 from slot 30.
- **Cost:** peak memory 125 GiB PSS, 4.1 h of wall time.

**800k × 2.4 kB with bundles of 16, CUBIC build (rtt6), seed 1: passes, with no host to spare in one slot.** Same hosts and seed as the runs above, on the build closest to stock Linux.

- **Completeness:** home hosts 100 % in every slot. 1 Gbit hosts are at 99.45 % or more in every slot from slot 2 except slot 15, at 99.18 % (3 of about 366 hosts, the most the rule allows). Their means over slots 2–15, 16–29, 30–39 and 40–49 are 99.81, 99.83, 99.84 and 99.86 %, so there is no step and no decline. On the original build they are 99.96, 100, 100 and 99.92 %.
- **Who misses:** 30 incomplete 1 Gbit node·slots, against 5 on the original build. No host misses in more than 12 of 48 slots; the most frequent is a Prysm host in Sydney.
- **No backlog:** signatures first arriving after the deadline stay at 0.01–0.04 per 1 Gbit host per slot by 10-slot block, at most 0.16 (slot 33); home hosts get none, and no copy is older than 60 s. Late duplicate copies on 1 Gbit hosts are 25–32 % below the original build's: 483 kB per host per slot in slots 2–9, rising to 1,110 kB in slots 40–49 and still growing 6 % per 10 slots at the end. On home hosts they nearly level off, at 46 kB (50/15) and 32 kB (50/25) per slot in slots 40–49.
- **Latency from publish:** PQ p99 0.65 / 0.58 / 0.69 s (50/15, 50/25, 1 Gbit), against 0.49 / 0.43 / 0.56 s on the original build. Blocks p95 0.67 s against 0.36 s, with no growth over the run.
- **Attestations:** 1 Gbit hosts miss 1.48 % in slots 2–15 and 1.88 % in slots 16–49, against 0.79 and 1.24 % on the original build.
- **TCP:** about 725k window restarts per slot keep windows near 10 segments. ssthresh levels off after about slot 20. First timeouts on home paths still climb, more slowly each block; resends stay flat.
- **Cost:** 4.0 h of wall time.

**Seed 2 of the CUBIC bundled run: passes, with no host to spare in one slot.** Same build and settings as seed 1, on the second seed's hosts.

- **Completeness:** home hosts 100 % in every slot. 1 Gbit hosts are complete in 43 of 48 slots. Slot 40 is at 99.17 % (3 of about 361 hosts, the most the rule allows), and slots 27, 28, 42 and 44 miss one host each. Means over slots 2–9, 10–19, 20–29, 30–39 and 40–49: 100, 100, 99.94, 100 and 99.86 %.
- **Who misses:** 7 incomplete 1 Gbit node·slots, against 30 on seed 1, on 4 hosts with at most 2 each. All fall after slot 26, too few to call a trend.
- **No backlog:** signatures first arriving after the deadline are 0 in 44 of 48 slots and at most 0.04 per 1 Gbit host per slot. Late duplicate copies level off on home hosts after slot 20 (38 and 30 kB per slot on 50/15 and 50/25 in slots 40–49) and still grow about 5 % per 10 slots on 1 Gbit hosts, to 1,192 kB per slot.
- **Latency and attestations:** PQ p99 0.66 / 0.58 / 0.72 s; blocks p95 0.68 s, with no growth. 1 Gbit hosts miss 1.65 % of attestations in slots 2–15 and 1.72 % in slots 16–49.
- **TCP:** as on seed 1, first timeouts on home paths still climb, more slowly each block, and ssthresh levels off.
- **Cost:** peak memory 116.6 GiB PSS, 3.8 h of wall time.

**Earlier 50-slot run** (3 kB, Lighthouse rules on every host, before the stale-message fix): 1 Gbit hosts averaged 98.15 %. From slot 28, old messages re-flooded once the simulator's 60 s duplicate cache expired, which led to the 60 s age check.

**Why 1,024 hosts for the long horizon.** 2,048 hosts × 50 slots doesn't fit in 256 GB, because memory creeps by about 0.7 MiB per host per slot.

## 6 slots, 2,048 hosts

These runs end before any mesh-delivery scoring switches on, so they are optimistic. Home classes are at least 99.8 % complete. 1 Gbit hosts, slots 2–5:

| cell | 1 Gbit complete |
| --- | --- |
| 3 kB | 98.65 % (seed 2: 98.92 %) |
| 3 kB, bundles of 16 | 99.22–99.73 % |
| 1.2 kB | 99.86 % |
| 1 Gbit only for hosts above 8 validators | 97.2–97.6 % |

## What causes the misses

- **Packet loss on long paths.**
  - With loss off (6 slots), no host missed anything. With loss on, 23 node·slots were incomplete in the same slots.
  - Shadow's TCP recovers most losses with SACK. But Shadow 3.3.0 never measures the round-trip time: it clears the timestamp it should echo before each packet leaves. So the retransmission timeout starts at 1 s and never adapts to the path.
  - Worse, each isolated timeout doubles it for good, because the reset to 1 s needs three timeouts in a row. A long-lived connection that has lost a tail packet a few times waits 4, 8 or 16 s (at most 120 s) before retransmitting. Linux waits about RTT + 200 ms (0.25–0.5 s on these paths) and also sends a tail-loss probe.
  - A 64-host check confirmed the ratchet. The share of connections whose timeout is 2 s or more rises every slot, from 2 % at slot 0 to 31 % at slot 19, and some reach 120 s. With the fix it stays at about 4 %, and measured RTTs match the configured paths (median ratio 1.01).
  - So the misses are probably overstated. In one 64-host run, the fixed builds missed 0.006–0.012 % of PQ signatures on 1 Gbit hosts, against 0.049 % on the current build. The effect grows as connections age, which could explain why 1 Gbit completeness declines over a run.
  - Other differences from Linux point both ways: Reno instead of CUBIC except in rtt6; no congestion-window validation except in cwv, rtt5 and rtt6; no slow-start restart after idle except in rtt5 and rtt6; and a larger window after a timeout on the current build.
- **Who misses.** Hosts in Sydney, São Paulo, Seoul, Singapore and Tokyo, mostly Prysm, which keeps only 70 peers.
  - 800k seed 1: one Prysm host in Singapore misses in 15 of 18 slots despite a full mesh (7.2 peers, 92 % on 1 Gbit). Its forward timeouts rise from 14k to 25k per slot. On the fixed TCP build it misses nothing, so the timeout ratchet caused this.
  - 400k: one Prysm host in São Paulo misses in 14 of 18 slots.
  - 50 slots: a Prysm host in Sydney misses in 17 of slots 16–49.
  - Seed 2, bundles and 600k: no host misses in most slots. With bundles, all 9 hosts that miss at least once are Prysm.
  - 1 Gbit only above 8 validators: seven far-region Prysm hosts with 70 peers and one Lighthouse host in Sydney miss repeatedly. On the fixed TCP build, five far-region Prysm hosts with 70 peers miss in 9–18 of 18 slots.
  - Window rules build, default link mix: eight far-away hosts, seven of them Prysm with 70 peers, miss in 9–15 of 18 slots. With bundles, one Lighthouse host in Sydney misses in 11 slots and no other host in more than 8.
  - Slow start after idle switched off: 19 of 742 1 Gbit hosts miss at least once and none in more than 8 slots. Three Prysm hosts in São Paulo and Tokyo start missing at slot 16, after mesh-delivery scoring switches on.
  - 1 Gbit only above 8 validators, with bundles on the CUBIC build: 64 incomplete node·slots; one Prysm host in Seoul misses in 11 of 18 slots.
- **Mesh-delivery scoring (P3) on PQ and attestation subnets adds misses when it switches on,** 17 slots after a peer joins the mesh (around slot 15). Far-away hosts deliver fewer messages in time to count, so their peers' delivery counters fall short.
  - Around slot 16, Teku, Lodestar and Nimbus peers start scoring some far-away hosts negative and pruning them. Example at 2.4 kB: a São Paulo Prysm host misses nothing in slots 2–14, then 63–250 signatures in 4 of slots 15–19. Two or three non-Rust peers score it about −18 in slot 16 and −96 to −103 in slots 17–19, and the peers that include it in their PQ mesh fall from 90 to 68.
  - The fixed TCP build shows the same pattern: four far-away hosts miss at most once before slot 16 and in two or more of slots 16–19. So it isn't a TCP effect.
  - On blocks and aggregates it switches on one epoch after a peer joins the mesh (around slot 32). That doesn't explain the 50-slot run's step at slot 33.
- **Bundles and delivery deficits:** in the 20-slot bundled run, PQ mesh-delivery deficits kept growing after slot 15, from 1.3k to 2.5k per slot, almost entirely in Lighthouse views, where a full deficit costs only −5.2. In the 50-slot bundled run they peak at slot 20 and then decline, and no misses followed.

## Simulator corrections along the way

- **Shadow 3.3.0:** send() was capped at 64 KiB and upload caps were ignored. Jitter needed a patch. Its TCP never measured RTT, ratcheted its retransmission timeout and echoed the wrong timestamps. The fixed-TCP runs use a corrected build, rtt4. Further builds add Linux's window rules (rtt5) and then Linux's CUBIC (rtt6); see caveats.
- **Memory and speed:**
  - A lazy gossipsub queue: 39 GiB instead of 84 GiB at 512 hosts × 4 slots.
  - The PQ schedule is no longer copied on every action, which made runs about 4× faster per slot.
  - Memory is capped on PSS. RSS counted 6.9 MiB of shared binary pages once per host.
- **Old messages:** flood messages older than 60 s are ignored, so expired duplicate-cache entries can't re-flood the network.
- **Scoring per client,** each checked in source. These changes cut both ways: Prysm became more lenient; Teku, Lodestar and Nimbus became stricter.
  - The slow-peer penalty applies only in Lighthouse and Grandine.
  - Mesh-delivery scoring is off in Prysm. In Teku, Lodestar and Nimbus it is about 9× stronger on PQ topics than in Lighthouse.
  - Unanswered IWANT requests are penalised per message id in Rust clients, per request in Prysm, Teku and Lodestar, and never in Nimbus.
  - Rust clients wait 3 s before asking another peer for a message; the others ask the next peer at once.

## Caveats

- **Scoring horizon:** the 2,048-host runs end before block and aggregate mesh-delivery scoring switches on. Only the 1,024-host 50-slot runs cover it, and there it rarely penalised anyone in the strict clients' views, so a 2,048-host run with that activation shortened to 17 slots was dropped.
- **Link mix:** the 20 % 1 Gbit share among hosts with at most 8 validators is a modelling assumption. Without it, 2.4 kB fails on every build tested, with bundles on the CUBIC build too (see Verdict). No data in this study backs the 20 % share.
- **Seeds:** two seeds for 800k × 2.4 kB, unbundled and bundled, on the current build; one for every other cell. The two seeds' worst slots (99.05 % and 99.72 %) differ as much as bundled and unbundled runs do, so single-seed comparisons between cells are not conclusive.
- **Scale:** 2,048 hosts is fewer than mainnet. Runs at that size last 20 slots; the 50-slot runs use 1,024 hosts, where one host is 0.27 % of the 1 Gbit class.
- **Churn rule:** signatures from offline publishers are excluded, 7–540 per 20-slot run, as are those from publishers with no connections, of which there were none. The one refused 400k signature counts as a failure, because its publisher probably had connections.
- **Columns:** the model publishes data columns only from the proposer, which is pessimistic.
- **Forward expiry:** every host drops queued forwards after 1 s, as rust-libp2p does. Prysm, Teku, Lodestar and Nimbus never expire queued messages.
- **TCP loss recovery:** in Shadow 3.3.0 the retransmission timeout never adapts and ratchets up after timeouts (see What causes the misses), so lost packets on long paths recover far more slowly than on Linux. This makes the far-region misses worse than they would be.
  - The first fixed build (RTT measurement, Linux's timeout rule and buffer limits) passed its checks but timed out too eagerly on paths into home hosts.
  - Queuing delay spikes on those paths fired timeouts that Linux would mostly avoid or undo. Shadow has neither Linux's tail-loss probe nor its undo of spurious timeouts. Each timeout shrank the window and resent everything in flight, and in a 64-host check, retransmissions on those paths rose two- to sixfold. Paths between 1 Gbit hosts were unaffected.
  - A second build added Linux's RTT estimator and its undo. Timeouts fell by a third. Of the timeout episodes that ended with an acknowledgement, 94 % were spurious and were undone. But retransmissions on home paths fell only 3–28 %, because after a timeout Shadow resends everything outstanding at once, where Linux resends one segment.
  - A third build also restarts from one segment after a timeout, as Linux does. On long paths, where Linux's tail-loss probe fires at about the timeout, it then repairs a tail loss about as fast as Linux. On short paths it is slower, which errs pessimistic. It passed its check: in a 64-host run, retransmissions on home paths came down to 1.2–1.7× the current build's, and 1 Gbit completeness and PQ misses were as good as or better than on the other builds.
  - Shadow also echoes the wrong timestamp in ACKs: the newest packet received, where Linux echoes the earliest packet the ACK newly acknowledges. The fourth build, rtt4, adds Linux's rule. It is final, and the fixed-TCP runs use it. The rule changed little (timeouts −5 %, still 97 % spurious), because Shadow sends pure ACKs ahead of any queued upload data, so they never wait in a home uplink. A home router with a plain FIFO uplink would hold them; one with fair queuing would not. This is left as is.
  - The spurious timeouts are cheap after the undo, about a quarter of a resent packet each. In the 64-host check, rtt4 had home hosts 100 % complete and missed 0.006 % of PQ signatures on 1 Gbit hosts, against 0.049 % on the current build.
  - On every fixed build, timeouts on home paths become more frequent as the run goes on. At 2,048 hosts on rtt4, home-to-home first timeouts climb from 10.7 to 20.6 per 1,000 data packets between slots 2 and 18, about 2.4 times the 64-host rate. 96.6 % are spurious and undone, at 0.25 resends each. Windows shrink over the same slots (median 105 → 26 segments home to home), so growing windows don't explain the climb. The no-PQ run on rtt4 shows the same climb; in both runs it levels off from about slot 10 at 18–21 per 1,000. On the window rules build, with windows near 10 segments, it runs at 75–90 % of rtt4's level, so it doesn't need growing windows. The source is unknown.
  - Remaining gaps in rtt4: no tail-loss probe or RACK, Reno instead of CUBIC, no congestion-window validation and no slow-start restart after idle. Shadow grows the window on every ACK, even when the sender doesn't fill it, so lightly loaded connections reach windows of thousands of segments. Linux grows it only while it limits sending, and shrinks it after idle. So Shadow sends each burst with a far larger window than Linux, which is optimistic on long paths.
  - Shadow's Reno also counts duplicate ACKs across a whole congestion-avoidance phase, so three out-of-order arrivals far apart can halve the window without starting any repair. Linux counts only the holes currently open.
    - The window sensitivity build fixes this. At 64 hosts the fix removed only 1–3 % of window cuts.
    - Packets on a path are never reordered in the model, so out-of-order arrivals follow losses only.
  - In every build but rtt5b and rtt6, Reno halves the window on each loss, where Linux's CUBIC keeps 70 %, and regrows it more slowly above ssthresh. That is pessimistic.
  - **Window rules build (rtt5):** rtt4 plus Linux's window validation, its restart after idle, and the duplicate-ACK fix. Both window rules are Linux defaults.
    - At 2,048 hosts, connections sit idle 0.9–1.0 s between bursts, against a timeout of about 0.3 s. About 1.5 million restarts per slot reset windows to 10 segments, and the median window over the run is 10 segments on every path type. 81 % of restarts leave the window below ssthresh, and all of those resume slow start, as on Linux.
    - The 800k cell fails on it (see Results). Block propagation from publish roughly doubles, and PQ p99 latency on 1 Gbit hosts rises from 0.68 to 1.18 s.
    - In the unbundled run, ssthresh at restarts falls mostly in slots 4–9, then by only 14–23 % more over slots 10–18, and the block slowdown doesn't grow with it. With bundles, ssthresh between 1 Gbit hosts falls later and is still falling at slot 18. Reno halves ssthresh on each loss, where CUBIC keeps 70 %, so this errs pessimistic. With CUBIC's cut, block p99 from publish and 1 Gbit PQ p99 fell 13–14 % at 64 hosts, a quarter to two fifths of the gap to rtt4; at 2,048 hosts that cut alone turns the bundled 800k cell from a fail into a pass (rtt5b, see Results). A build with CUBIC's growth and HyStart as well, rtt6, is described below.
    - Restart after idle can be switched off on Linux (net.ipv4.tcp\_slow\_start\_after\_idle = 0); window validation can't. At 64 hosts, restart after idle alone reproduces rtt5, and window validation alone reproduces rtt4: block propagation from publish 0.17 / 0.37 / 0.47 s against rtt4's 0.16 / 0.37 / 0.46 s. At 2,048 hosts, window validation alone passes the unbundled cell with no host to spare, and blocks spread 7–14 % slower than on rtt4.
    - rtt5 lacks Linux's decay of an under-used window (`tcp_cwnd_application_limited`): after a timeout's worth of not filling the window, Linux cuts it to the mean of the window and the part actually used. Here the restart covers most of that, because connections idle longer than the timeout. With the setting at 0, Linux skips both, so the window-validation-only run matches that configuration.
  - **CUBIC build (rtt6):** rtt5 plus Linux's CUBIC (v6.12), including its early slow-start exit (HyStart). It is the closest of the builds to a stock Linux host; it still lacks the tail-loss probe, RACK and proportional rate reduction.
    - Its 64-host check passed: ssthresh is 0.7 × the window at every loss, the window follows CUBIC's curve to within a segment, growth stays within CUBIC's cap of one segment per two packets acknowledged, and the curve pauses while a connection idles, as in Linux.
    - At 64 hosts, 1 Gbit hosts had 1 incomplete node·slot of 396 (fixed build 2, cwv 4, rtt5 16), and 1 Gbit PQ p99 was 1.32 s (fixed build 1.36 s, rtt5 2.08 s). Home PQ p99 landed about halfway between rtt5 and the fixed build.
    - Blocks stay close to rtt5 (p95 from publish 0.80 s against 0.86 s; fixed build 0.37 s). A block is one short burst after idle and mostly ends in slow start, where CUBIC and Reno grow alike; CUBIC's faster regrowth helps the longer signature bursts.
    - HyStart ends slow start early on some connections, by delay at home links and by ACK train between 1 Gbit hosts, and changes outcomes little.
    - With the restart switched off (cwv6, as on a Linux host with `net.ipv4.tcp_slow_start_after_idle = 0`), its 64-host check passed too. Block p95 from publish was 0.34 s and 1 Gbit PQ p99 1.05 s, the best of any build (fixed build 0.37 s and 1.36 s). It was the fallback for the remaining runs; with both CUBIC cells passing, none needs it.
    - At 2,048 hosts both 800k cells pass, bundled with 5 hosts to spare and unbundled with 1 (see Results), and every logged window target equals Linux's integer CUBIC formula.
- **Socket buffers** already stay within Linux's default limits in these runs (they start at 128 KiB send and 171 KiB receive and reach at most 4 MiB and 6 MiB), because Shadow sizes them from RTT samples it never takes.
- **Rust hosts are somewhat over-penalised.**
  - Queue-full refusals of control messages (IHAVE, IWANT and IDONTWANT) make up 13–28 % of the failed sends that cost score, and 32–41 % on 1 Gbit hosts.
  - Lighthouse's gossipsub fork gives control messages a separate 20,000-message queue; the simulator's 0.49.5 doesn't.
- **Duplicate cache:** 60 s on every host (Lighthouse uses 768 s), backed by the 60 s age check.
- **PQ topic scoring:** no client has PQ topics yet, so their scoring parameters are our choice.
- **BLS alongside PQ:** BLS attestations and PQ signatures run side by side. That is conservative if PQ replaces BLS.
- **Anonymity:** a home staker's single subscription reveals which subnet its validators publish to. In the clean-network runs every subnet had at least 360 members.
- **Far tail:** mainnet data doesn't cover the far tail that packet loss creates.

## Queue on p2psims

Final status, 17 November. Every run finished; the study is closed and its p2psims thread is archived. Due times are CET and my estimates.

- (Done) 800k × 2.4 kB with 1 Gbit links only for hosts above 8 validators, 20 slots: fails in 16 of 18 slots
- (Done) 1,024 hosts × 50 slots, 800k × 2.4 kB with bundles: passes with margin
- (Done) Seed 2 of the 20-slot bundled run, current build: passes
- (Done) Fixed TCP (rtt4): 800k × 2.4 kB, 20 slots: passes with margin
- (Done) Fixed TCP: no-PQ calibration, 20 slots: calibration unchanged
- (Done) Fixed TCP: 1 Gbit only above 8 validators, 20 slots: fails in 16 of 18 slots
- (Done) Window rules build (rtt5): 800k × 2.4 kB, 20 slots: fails in 12 of 18 slots
- (Done) Window rules build: no-PQ calibration, 20 slots: within tolerance; blocks spread 2.4× slower than on rtt4
- (Done) Window rules build: 800k × 2.4 kB with bundles of 16, 20 slots: fails in 6 of 18 slots
- (Done) Window validation only, which is Linux with slow start after idle switched off: 800k × 2.4 kB, 20 slots: passes, with no host to spare
- (Done) Window rules build with CUBIC's 70 % cut: 800k × 2.4 kB with bundles of 16, 20 slots: passes
- (Done) CUBIC build (rtt6): 800k × 2.4 kB with bundles of 16, 20 slots: passes, with 5 hosts to spare
- (Done) CUBIC build: 800k × 2.4 kB unbundled, 20 slots: passes, with 1 host to spare
- (Done) CUBIC build: 1,024 hosts × 50 slots, 800k × 2.4 kB with bundles: passes, with no host to spare in one slot
- (Done) CUBIC build: 1 Gbit only above 8 validators, with bundles of 16, 20 slots: fails in 6 of 18 slots
- (Done) CUBIC build: 800k × 2.4 kB with bundles of 16, every home staker in two subnets (nodes without validators stay in one), 20 slots: passes with margin
- (Done) CUBIC build: 800k × 2.4 kB with bundles of 16, today's structure (every home node in two backbone subnets, stakers also in their duty subnet), 20 slots: passes, with no 50/15 host to spare in slot 2
- (Done) CUBIC build: seed 2 of the 50-slot bundled run: passes, with no host to spare in one slot
- (Done) CUBIC build: no-PQ calibration, 20 slots: analysed, not added to the p2psims report. 1 Gbit hosts miss 0.99 % of attestations in slots 2–15 and 1.18 % in slots 16–19; PQ raises home attestation misses by at most 0.15 points in the four CUBIC PQ runs

Four runs are dropped. Both unbundled 50-slot runs on the CUBIC build are dropped because bundling will be adopted regardless. The early block-scoring run is dropped because block and aggregate scoring rarely penalised anyone in the 50-slot run. The 800k run on the first fixed build is dropped because the later builds supersede it. Runs go in the order listed. Each run after the CUBIC cells uses the CUBIC build if the CUBIC cell with the same bundling passes, and otherwise Linux with slow start after idle switched off. Both CUBIC cells passed, so every remaining run uses the CUBIC build and none needs the fallback. So the verdict rests on stock Linux wherever stock Linux passes. That fallback uses CUBIC, as a real Linux host with the setting at 0 does; it passed its 64-host check. The 50-slot bundled run on the window rules build was conditional on its 20-slot cell passing, so it doesn't run. The queue was paused from 16:53 to 19:30 while another user ran a Shadow sweep on p2psims, because under the half-budget rule (128 GB and a quarter of the CPUs) none of our runs fit. It ended at 13:50 on 12 November. The p2psims report (`results/gossip-one-subnet-realistic.md`) was not finalized and still lists this last run as queued. Finished on 9 to 11 November and analysed: 800k seed 2, the no-PQ baseline, 600k, 400k, the 1 Gbit-only cell, both 50-slot runs, the bundled seed 2, the fixed-TCP 800k, no-PQ and 1 Gbit-only runs, the window rules 800k, no-PQ and bundled runs, the run with slow start after idle switched off, the bundled run with CUBIC's cut, all three 20-slot CUBIC runs and the bundled 50-slot CUBIC run. Every run finished normally, with peak memory at most 233 GiB PSS. The cap is 235 GiB; it was 238 GiB for the today's-structure run, inside the 256 GB limit.

## Where things are

- **Report:** [gossip-one-subnet-realistic.md](gossip-one-subnet-realistic.md), the full p2psims report.
- **Clean-network one-subnet results:** [gossip-one-subnet.md](gossip-one-subnet.md).
- **Calibration report:** [results/realism-calibration.md](../results/realism-calibration.md).
- **Sources:** [sources.md](../sources.md): [leanVM](https://github.com/leanEthereum/leanVM) and its [benchmarks](https://leanethereum.github.io/leanVM/), Barnabé Monnot's [pq-aggregation-model](https://github.com/barnabemonnot/pq-aggregation-model), pqai27, Potuz's post, the decoupled-consensus post and dc-networking.
