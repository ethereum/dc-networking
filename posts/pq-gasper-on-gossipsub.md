# Can PQ Gasper run on gossipsub?

*Draft, 2026-11-24.*

**Not at 1,600 signatures per subnet.** With 800k validators, PQ Gasper sends 25,000 signatures per slot, about 1,600 in each of 16 subnets. We simulated one such subnet in Shadow on 2,048 nodes, with home bandwidth, packet loss and churn. In the worst slot, only 23 % of home nodes without validators and 53 % of home stakers had every signature 4 s after publishing began. Gossipsub delivered to every class up to 300 signatures per subnet per slot; beyond that, forwarding fills home uplinks.

## Gasper is the easier change, if gossipsub can carry it

Ethlabs calls PQ Gasper versus PQ decoupled consensus "the biggest open question" for [pqai27](https://ethlabs.org/writings/pqai27.html): Gasper is "plausibly the easier change", but "it is less clear how many compromises that takes". [Potuz](https://www.potuz.net/posts/pq/) wants PQ Gasper first and names the test: "We need POCs on the CL right now to see whether gossipsub is even viable". If Gasper needs new slot or epoch parameters, he would rather move to decoupled consensus.

## A Gasper subnet is four to five times what home nodes can carry

![Bar chart of signatures per subnet per slot, against the 1,600 of one PQ Gasper subnet. Home nodes without validators (50/15 Mbit/s, 330 nodes) passed 300 and failed 400. Home stakers (50/25 Mbit/s, 976 nodes) passed 400 and failed 600. 1 Gbit nodes (742) passed 800 and failed 1,600.](charts/single-subnet.svg)

*Passed: at least 99 % of the class's nodes held every signature 8 s into the slot, in every slot. One run per load; the setup is at the end.*

## Home nodes fail once forwarding takes about half their uplink

![Line chart of mean upload 4–8 s into the slot, as a share of the uplink, against signatures per subnet per slot. Home nodes without validators (50/15 Mbit/s): 34, 46, 56, 72, 84 and 115 % at 200, 300, 400, 600, 800 and 1,600 signatures; they passed up to 300. Home stakers (50/25 Mbit/s): 23, 31, 39, 50, 59 and 85 %; they passed up to 400.](charts/uplink.svg)

- Every node in a subnet's mesh forwards each signature to its mesh peers. At 1,600, a home node without validators hands TCP 115 % of its uplink over 4–8 s on average, and 171 % at the busiest node. A home staker hands it 85 %, and 140 %. Downloads average 41 % and 50 % of the link.
- With the uplink full, the node's ACKs and IWANT requests queue behind its forwards. Paths into it see 16 to 31 times as many TCP timeouts as paths into a home node that doesn't forward, and peers drop forwards that wait more than 1 s.
- In a diagnostic run where 30 % of nodes never forward (512 nodes at 1,600), home nodes that don't forward miss 3 to 8 times fewer signatures: 2.2 % against 17.3 % without validators, and 2.0 % against 6.6 % for stakers.

## No single setting rescues 1,600

- **More 1 Gbit nodes:** with 80 % of nodes on 1 Gbit, the home nodes' worst slots stay at 23 % and 53 %, though they miss about 40 % fewer signatures.
- **Smaller signatures:** 800 signatures of 2.4 kB, the same bytes as 1,600 of Potuz's 1.2 kB option, fail both home classes (78 % and 91 % complete in the worst slot). The 1.2 kB option also sends more messages, so it would fail by slightly more.
- **A cleaner network:** without packet loss, churn, NAT and slow CPUs, or without TCP slow start after idle, home nodes without validators pass at 400, only just.
- **Running today's BLS attestations alongside** turns the pass at 300 into a fail, by one node.

## What PQ Gasper on gossipsub would need

- **About 300 signatures per subnet per slot.** At 25,000 per slot that is about 80 subnets, five times leanVM's 16, so five times as many aggregates to merge. If home nodes keep joining two backbone subnets as today, the budget per subnet nearly halves. With 16 subnets, it means consolidating to about 150k validators.
- **Or home nodes outside the subnet meshes.** They would publish their own signatures without forwarding others', and fast nodes would carry the subnets and aggregate. With 80 % of nodes on 1 Gbit, the 1 Gbit nodes passed 1,600 (99.8 % in the worst slot). How many fast nodes mainnet has, and how many subnets each could carry, is untested.
- **Or decoupled consensus.** Only a 512-member committee votes on the chain's critical path. Finality votes still come from the full validator set, in 4 s units sized like today's attestation slot ([dc-networking](https://github.com/ethereum/dc-networking)), so the same per-subnet limit applies, though a late vote only delays finality.

## Caveats

- One seed per load. At 300 and 400 the two home classes pass with no node to spare.
- 2,048 nodes is the largest network that fits the simulation machine, and the 1,600 run stopped after slot 14 at its memory limit. Mainnet has several times more nodes; at 400, 512 nodes gave the same verdict as 2,048.
- Each node joins one subnet, and aggregation is not simulated. leanVM aggregates 1,400 signatures in 0.4–1.6 s and merges 16 aggregates in another 0.4–1.7 s on 8- to 32-core machines.
- The 1 Gbit share, 36 % of nodes, is an assumption.
- [Barnabé Monnot's aggregation model](https://github.com/barnabemonnot/pq-aggregation-model) assumes 2 copies of each signature per node; our earlier runs measured 4 to 5.

## Setup

- **Nodes:** 2,048, all in the one subnet, each with the validator count of a node from a mainnet crawl. Nodes with more than 8 validators, and a fifth of the rest, are on 1 Gbit (742). The others keep EIP-7870 home links: 50/25 Mbit/s with validators (976) and 50/15 without (330).
- **Signatures:** each slot draws 1,600 signers (200 to 800 in the load runs), weighted by validators, so 98 % of signatures come from 1 Gbit nodes. A signature is 2,404 B (leanXMSS). Each node bundles its own into messages of up to 16 and publishes them 4.0–4.5 s into the slot: at 1,600, that is 302 messages and 3.84 MB per slot.
- **Deadline:** every node needs every signature 8.0 s into the slot, when aggregation starts. A class passes when at least 99 % of its nodes have them all, in every slot from slot 2.
- **Gossipsub:** rust-libp2p 0.49.5 with IDONTWANT. Each node runs one client's peer target, mesh degree and peer scoring, in mainnet's client mix: Lighthouse (53 %, 200 peers, D = 5), Prysm (21 %, 70 peers), and Nimbus, Teku, Lodestar and others (D = 8). The signature topic is scored as one of 16 subnets.
- **Network:** latencies between 12 cities from measured pings; fiber, cable and DSL access with jitter and 0.05–0.25 % packet loss; 30 % of home nodes behind NAT; connections that last 30 minutes on average, and nodes that restart, leave and join. Verifying a signature takes 400 µs, three times as long on a fifth of home nodes. The perturbations are [calibrated](../research/pq-gasper/gossipsub/results/realism-calibration.md) against mainnet's block and attestation arrival times.
- **TCP:** Linux 6.12's CUBIC with HyStart, its RTT estimate and timeouts, and slow start after idle.
- **Other traffic:** blocks, data columns, aggregates and sync-committee messages at mainnet rates; no BLS attestations, which PQ Gasper replaces.

## How the simulations were run

- **Simulator:** [Shadow](https://shadow.github.io/) 3.3.0 runs each node's real binary as a Linux process, and emulates the network and TCP under it in simulated time. [Three patches](../research/pq-gasper/gossipsub/sim/README.md): two Shadow bugs (upload limits were ignored, and writes over 64 KiB could stall a connection), per-packet jitter, and TCP that follows Linux 6.12.
- **Node:** `wbsim`, a rust-libp2p node (TCP, noise, yamux) on gossipsub 0.49.5 that scores peers as each client does. Two gossipsub patches allocate send queues on demand (same limits, less memory) and add the clients' IWANT-promise rules.
- **Runs:** [`sim/gen_config.py`](../research/pq-gasper/gossipsub/sim/gen_config.py) and [`sim/perturb.py`](../research/pq-gasper/gossipsub/sim/perturb.py) write each run's Shadow configuration from flags: nodes, links, clients, perturbations and the publishing schedule. A run is 30 s of warm-up and 20 slots of 12 s. There were twelve runs, all with seed 1: six loads, five single-change levers and one diagnostic.
- **Machine:** one server with 96 CPUs and 503 GiB. A 2,048-node run used 48 CPUs, 1.3–2.6 hours and up to 235 GiB.
- **Analysis:** every node logs each message it receives and, every 0.5 s, its traffic counters; [`pq1600.py`](../research/pq-gasper/gossipsub/p2psims/analysis/pq1600.py) turns the logs into completeness, latency, upload and dropped sends per class and slot.

```sh
# as run on the machine, whose paths the scripts keep: NAME HOSTS SLOTS THREADS [flags]
bash p2psims/runs/run_pq1600.sh Q2048x20-m1600-s1 2048 20 46
bash p2psims/runs/run_pq1600.sh Q2048x20-m400-s1 2048 20 46 --msgs 400
python3 -I p2psims/analysis/pq1600.py Q2048x20-m1600-s1 --per-slot
```

Every run and number is in the [full report](../research/pq-gasper/gossipsub/results/pq-gasper-one-subnet.md). [`charts/generate_charts.py`](charts/generate_charts.py) draws the charts.
