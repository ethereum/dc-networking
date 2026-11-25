# Shadow results: gossipsub vs. WB-PQ direct delivery at mainnet subnet scale

Setup: [sim/README.md](../sim/README.md). What one mainnet node sees at 800k
validators:
- **2 gossip subnets**, each with 391 leanSig-size votes (3,272 B) per slot
  (32-slot round) or 1,560 (8-slot DC round);
- **312 hosts**, all members of both subnets in gossip mode (10,000 nodes × 2 / 64);
- **EIP-7870 links** (`eip7870-mix`): 80 % of voters at attester limits
  (50/25 Mbit/s), 20 % at 1 Gbit; 12 of 16 recipients per topic at 1 Gbit, 4
  at attester limits; the proposer as a local block builder (100/50);
- real rust-libp2p 0.56 (TCP + noise + yamux), Shadow 3.3 with two bug fixes
  ([sim/shadow-3.3-fixes.patch](../sim/shadow-3.3-fixes.patch)). Without
  them, Shadow ignores upload limits and stalls large writes;
- 5 slots per run after a 20 s warm-up, 3 topology seeds for the main
  comparison.

Run names: `gp-*` gossip votes with proofs moved by announce-then-pull (the
vote-subnet comparison); `g-*` today's full pipeline, gossip votes and every
proof flooded; `d-*` WB-PQ direct. Suffixes: `-sN` seed, `-dc` 8-slot
cadence, `-min` attesters at 15 Mbit/s upload, `-1sub` one subnet only,
`-cold` direct with connections dialled at vote time.

## Headline (32-slot round, 2 subnets, `eip7870-mix`, 3 seeds × 5 slots)

| | gossip votes (`gp-s1..3`) | WB-PQ direct (`d-s1..3`) |
|---|---|---|
| bytes received per needed vote byte (κ) | **4.2** (5.9 with one subnet, see below) | **1.02** |
| subnet vote traffic per slot, all 312 nodes | 3.13–3.16 GiB | 39.9 MiB (**≈ 80× less**) |
| attester-link voter, vote phase per slot | 10.1–10.2 MiB in + 9.2–9.6 MiB out | 0.14 MiB out |
| vote latency p99 / max | **2.3–2.6 s** / 3.6–3.8 s | **0.42 s** / 0.44 s |
| votes missing at the 4 s deadline | 61–126 of 62,560 per run (0.10–0.20 %); worst aggregator·slot 89.5 % | 0 (480 of 480 recipient·slots complete) |
| gossip forwards dropped by rust-libp2p | ~700k per slot, ~2,300 per node | – |
| proposer: best / random proof per topic after first emitted | 0.28–0.49 s / 0.59–0.82 s | 0.29–0.50 s / 0.76–1.05 s |
| errors (request timeouts, dial failures) | 0 | 0 |

## Runs

### Main comparison: 32-slot round, 3 seeds

| metric | gp-s1 | gp-s2 | gp-s3 | d-s1 | d-s2 | d-s3 |
|---|---|---|---|---|---|---|
| mode | gossip, proofs pulled | gossip, proofs pulled | gossip, proofs pulled | direct | direct | direct |
| profile / seed | eip7870-mix / 1 | eip7870-mix / 2 | eip7870-mix / 3 | eip7870-mix / 1 | eip7870-mix / 2 | eip7870-mix / 3 |
| hosts | 312 | 312 | 312 | 312 | 312 | 312 |
| subnets × votes per subnet | 2 × 391 | 2 × 391 | 2 × 391 | 2 × 391 | 2 × 391 | 2 × 391 |
| direct topics × recipients | – | – | – | 2 × 16 | 2 × 16 | 2 × 16 |
| slots analysed | 5 | 5 | 5 | 5 | 5 | 5 |
| vote latency p50/p90/p99/max (ms) | 540/1368/2443/3820 | 600/1441/2613/3771 | 547/1366/2292/3574 | 123/277/423/440 | 126/300/424/434 | 126/300/424/438 |
| vote latency p99 by voter link (ms) | attester 2529, cloud 1863 | attester 2687, cloud 1854 | attester 2362, cloud 1705 | attester 424, cloud 420 | attester 425, cloud 420 | attester 425, cloud 420 |
| votes held at deadline: min / mean | 89.8% / 99.80% | 93.1% / 99.85% | 89.5% / 99.90% | 100.0% / 100.00% | 100.0% / 100.00% | 100.0% / 100.00% |
| aggregators with 100 % (of agg·slots) | 152/160 | 157/160 | 155/160 | 160/160 | 160/160 | 160/160 |
| time to 100 % of votes after vote start: p50 / max (s) | 1.79 / 4.19 | 1.94 / 5.83 | 1.73 / 4.07 | 0.80 / 0.93 | 0.85 / 0.92 | 0.90 / 0.93 |
| proposer: proofs per slot (min–max) | 4–4 | 4–4 | 4–4 | 4–4 | 4–4 | 4–4 |
| proposer: 1st / last proof after 1st emitted (s) | 0.28 / 0.63 | 0.49 / 0.82 | 0.49 / 0.59 | 0.29 / 0.76 | 0.50 / 1.05 | 0.50 / 0.85 |
| proofs | pull | pull | pull | pull | pull | pull |
| proofs emitted per slot | 32 | 32 | 32 | 32 | 32 | 32 |
| network bytes received in vote phase / slot | 3,227.6 MiB | 3,201.5 MiB | 3,233.8 MiB | 39.9 MiB | 39.9 MiB | 39.9 MiB |
| bytes received per needed vote byte (κ) | 4.25 | 4.22 | 4.26 | 1.02 | 1.02 | 1.02 |
| gossip messages dropped from send queues, run total (forward / publish) | 3,524,986 / 5 | 3,505,883 / 8 | 3,674,319 / 10 | – | – | – |
| errors | 0 | 0 | 0 | 0 | 0 | 0 |

**Per-node bytes per slot (mean), vote phase [0 s, 8 s) and proof phase [8 s, 12 s)**

| run | node class | votes rx | votes tx | proofs rx | proofs tx |
|---|---|---|---|---|---|
| gp-s1 | aggregator | 11.14 MiB | 14.05 MiB | 0.28 MiB | 0.09 MiB |
| gp-s1 | proposer | 14.41 MiB | 13.69 MiB | 1.04 MiB | 0.02 MiB |
| gp-s1 | voter-attester | 10.10 MiB | 9.15 MiB | 0.70 MiB | 0.15 MiB |
| gp-s1 | voter-cloud | 10.70 MiB | 14.59 MiB | 0.17 MiB | 0.01 MiB |
| gp-s2 | aggregator | 10.59 MiB | 13.21 MiB | 0.27 MiB | 0.09 MiB |
| gp-s2 | proposer | 16.81 MiB | 15.82 MiB | 1.21 MiB | 0.03 MiB |
| gp-s2 | voter-attester | 10.21 MiB | 9.54 MiB | 0.73 MiB | 0.16 MiB |
| gp-s2 | voter-cloud | 10.16 MiB | 14.34 MiB | 0.17 MiB | 0.01 MiB |
| gp-s3 | aggregator | 10.83 MiB | 13.21 MiB | 0.41 MiB | 0.08 MiB |
| gp-s3 | proposer | 13.73 MiB | 13.12 MiB | 0.99 MiB | 0.01 MiB |
| gp-s3 | voter-attester | 10.17 MiB | 9.61 MiB | 0.77 MiB | 0.18 MiB |
| gp-s3 | voter-cloud | 10.81 MiB | 14.51 MiB | 0.18 MiB | 0.01 MiB |
| d-s1 | aggregator | 1.23 MiB | 0.01 MiB | 0.00 MiB | 0.03 MiB |
| d-s1 | proposer | 0.00 MiB | 0.00 MiB | 0.86 MiB | 0.00 MiB |
| d-s1 | voter-attester | 0.00 MiB | 0.14 MiB | 0.00 MiB | 0.00 MiB |
| d-s1 | voter-cloud | 0.00 MiB | 0.14 MiB | 0.00 MiB | 0.00 MiB |
| d-s2 | aggregator | 1.23 MiB | 0.01 MiB | 0.00 MiB | 0.03 MiB |
| d-s2 | proposer | 0.00 MiB | 0.00 MiB | 0.86 MiB | 0.00 MiB |
| d-s2 | voter-attester | 0.00 MiB | 0.14 MiB | 0.00 MiB | 0.00 MiB |
| d-s2 | voter-cloud | 0.00 MiB | 0.14 MiB | 0.00 MiB | 0.00 MiB |
| d-s3 | aggregator | 1.23 MiB | 0.01 MiB | 0.00 MiB | 0.03 MiB |
| d-s3 | proposer | 0.00 MiB | 0.00 MiB | 0.86 MiB | 0.00 MiB |
| d-s3 | voter-attester | 0.00 MiB | 0.14 MiB | 0.00 MiB | 0.00 MiB |
| d-s3 | voter-cloud | 0.00 MiB | 0.14 MiB | 0.00 MiB | 0.00 MiB |

### Today's full pipeline: every proof flooded (`g-s1`, `g-s2`)

| metric | g-s1 | g-s2 |
|---|---|---|
| mode | gossip | gossip |
| profile / seed | eip7870-mix / 1 | eip7870-mix / 2 |
| hosts | 312 | 312 |
| subnets × votes per subnet | 2 × 391 | 2 × 391 |
| direct topics × recipients | – | – |
| slots analysed | 5 | 5 |
| vote latency p50/p90/p99/max (ms) | 614/2291/3583/3993 | 713/2292/3550/3982 |
| vote latency p99 by voter link (ms) | attester 3641, cloud 2089 | attester 3589, cloud 2551 |
| votes held at deadline: min / mean | 0.3% / 91.62% | 0.3% / 89.75% |
| aggregators with 100 % (of agg·slots) | 123/160 | 124/160 |
| time to 100 % of votes after vote start: p50 / max (s) | 3.55 / 15.92 | 3.23 / 17.00 |
| proposer: proofs per slot (min–max) | 21–32 | 28–32 |
| proposer: 1st / last proof after 1st emitted (s) | 0.03 / 4.18 | 0.30 / 3.16 |
| proofs | flood | flood |
| proofs emitted per slot | 32 | 32 |
| proposer: share of proofs held at slot end, min / mean | 59% / 85.6% | 84% / 93.1% |
| any node: share of proofs held at slot end, min / mean, by link | attester 0% / 48.7%, builder 59% / 85.6%, cloud 72% / 93.5% | attester 0% / 48.2%, builder 84% / 93.1%, cloud 41% / 94.0% |
| network bytes received in vote phase / slot | 5,757.0 MiB | 5,757.1 MiB |
| bytes received per needed vote byte (κ) | 7.59 | 7.59 |
| gossip messages dropped from send queues, run total (forward / publish) | 2,638,113 / 1,253 | 2,648,354 / 1,388 |
| errors | 0 | 0 |

| run | node class | votes rx | votes tx | proofs rx | proofs tx |
|---|---|---|---|---|---|
| g-s1 | aggregator | 17.15 MiB | 18.09 MiB | 13.90 MiB | 24.30 MiB |
| g-s1 | proposer | 22.63 MiB | 19.31 MiB | 15.81 MiB | 22.40 MiB |
| g-s1 | voter-attester | 19.61 MiB | 16.73 MiB | 10.59 MiB | 11.90 MiB |
| g-s1 | voter-cloud | 15.20 MiB | 18.02 MiB | 15.63 MiB | 27.14 MiB |
| g-s2 | aggregator | 16.20 MiB | 17.62 MiB | 13.32 MiB | 23.71 MiB |
| g-s2 | proposer | 16.06 MiB | 15.37 MiB | 17.60 MiB | 18.01 MiB |
| g-s2 | voter-attester | 19.65 MiB | 16.93 MiB | 10.53 MiB | 12.16 MiB |
| g-s2 | voter-cloud | 14.74 MiB | 17.83 MiB | 14.31 MiB | 27.10 MiB |

Vote-phase traffic grows each slot: 3.2, 5.4–5.5, 6.1, 6.5, 6.9–7.0 GiB.
Flooding 32 proofs of 220 KiB takes an attester node far longer than the
4 s proof phase on a 25 Mbit/s uplink, so each slot's flood runs into the
next slot's votes.

### Controls: one subnet, EIP-7870 minimum upload, cold connections

| metric | gp-1sub-s1 | d-1sub-s1 | gp-min-s1 | d-min-s1 | d-cold-s1 |
|---|---|---|---|---|---|
| mode | gossip, proofs pulled | direct | gossip, proofs pulled | direct | direct (cold connect) |
| profile / seed | eip7870-mix / 1 | eip7870-mix / 1 | eip7870-min / 1 | eip7870-min / 1 | eip7870-mix / 1 |
| hosts | 312 | 312 | 312 | 312 | 312 |
| subnets × votes per subnet | 1 × 391 | 1 × 391 | 2 × 391 | 2 × 391 | 2 × 391 |
| direct topics × recipients | – | 1 × 16 | – | 2 × 16 | 2 × 16 |
| slots analysed | 5 | 5 | 5 | 5 | 5 |
| vote latency p50/p90/p99/max (ms) | 404/800/1130/1421 | 121/280/425/439 | 753/1667/2573/3733 | 127/284/425/454 | 126/397/977/1866 |
| vote latency p99 by voter link (ms) | attester 1152, cloud 855 | attester 426, cloud 420 | attester-15up 2656, cloud 1622 | attester-15up 427, cloud 420 | attester 976, cloud 984 |
| votes held at deadline: min / mean | 100.0% / 100.00% | 100.0% / 100.00% | 96.2% / 99.95% | 100.0% / 100.00% | 100.0% / 100.00% |
| aggregators with 100 % (of agg·slots) | 80/80 | 80/80 | 159/160 | 160/160 | 160/160 |
| time to 100 % of votes after vote start: p50 / max (s) | 1.63 / 1.86 | 0.88 / 0.93 | 2.63 / 5.73 | 0.80 / 0.94 | 0.85 / 2.04 |
| proposer: proofs per slot (min–max) | 2–2 | 2–2 | 4–4 | 4–4 | 4–4 |
| proposer: 1st / last proof after 1st emitted (s) | 0.27 / 0.62 | 0.28 / 0.70 | 0.29 / 0.63 | 0.28 / 0.76 | 0.29 / 0.76 |
| proofs | pull | pull | pull | pull | pull |
| proofs emitted per slot | 16 | 16 | 32 | 32 | 32 |
| network bytes received in vote phase / slot | 2,229.6 MiB | 19.9 MiB | 2,447.2 MiB | 39.9 MiB | 40.1 MiB |
| bytes received per needed vote byte (κ) | 5.88 | 1.02 | 3.22 | 1.02 | 1.03 |
| gossip messages dropped from send queues, run total (forward / publish) | 855,843 / 0 | – | 4,165,582 / 10 | – | – |
| errors | 0 | 0 | 0 | 0 | 0 |

| run | node class | votes rx | votes tx | proofs rx | proofs tx |
|---|---|---|---|---|---|
| gp-1sub-s1 | aggregator | 7.08 MiB | 7.99 MiB | 0.00 MiB | 0.03 MiB |
| gp-1sub-s1 | proposer | 13.60 MiB | 12.06 MiB | 0.43 MiB | 0.00 MiB |
| gp-1sub-s1 | voter-attester | 7.36 MiB | 6.74 MiB | 0.02 MiB | 0.00 MiB |
| gp-1sub-s1 | voter-cloud | 6.36 MiB | 8.31 MiB | 0.00 MiB | 0.00 MiB |
| d-1sub-s1 | aggregator | 1.23 MiB | 0.01 MiB | 0.00 MiB | 0.03 MiB |
| d-1sub-s1 | proposer | 0.00 MiB | 0.00 MiB | 0.43 MiB | 0.00 MiB |
| d-1sub-s1 | voter-attester | 0.00 MiB | 0.07 MiB | 0.00 MiB | 0.00 MiB |
| d-1sub-s1 | voter-cloud | 0.00 MiB | 0.06 MiB | 0.00 MiB | 0.00 MiB |
| gp-min-s1 | aggregator | 9.62 MiB | 12.06 MiB | 0.90 MiB | 0.16 MiB |
| gp-min-s1 | proposer | 13.02 MiB | 14.60 MiB | 1.25 MiB | 0.02 MiB |
| gp-min-s1 | voter-attester-15up | 7.26 MiB | 6.72 MiB | 1.32 MiB | 0.60 MiB |
| gp-min-s1 | voter-cloud | 8.82 MiB | 12.81 MiB | 0.72 MiB | 0.09 MiB |
| d-min-s1 | aggregator | 1.23 MiB | 0.01 MiB | 0.00 MiB | 0.03 MiB |
| d-min-s1 | proposer | 0.00 MiB | 0.00 MiB | 0.86 MiB | 0.00 MiB |
| d-min-s1 | voter-attester-15up | 0.00 MiB | 0.14 MiB | 0.00 MiB | 0.00 MiB |
| d-min-s1 | voter-cloud | 0.00 MiB | 0.14 MiB | 0.00 MiB | 0.00 MiB |
| d-cold-s1 | aggregator | 1.24 MiB | 0.02 MiB | 0.00 MiB | 0.03 MiB |
| d-cold-s1 | proposer | 0.00 MiB | 0.00 MiB | 0.86 MiB | 0.00 MiB |
| d-cold-s1 | voter-attester | 0.00 MiB | 0.14 MiB | 0.00 MiB | 0.00 MiB |
| d-cold-s1 | voter-cloud | 0.00 MiB | 0.14 MiB | 0.00 MiB | 0.00 MiB |

### 8-slot DC round: 1,560 votes per subnet

Gossip: 2 subnets of 1,560 votes. Direct: the same 3,120 votes in 8 topics of
390 votes × 16 recipients, so the proposer pulls best + random from 8 topics,
the load of an internal aggregator.

| metric | gp-dc-s1 | gp-dc-s2 | d-dc-s1 | d-dc-s2 | d-dc-s3 |
|---|---|---|---|---|---|
| mode | gossip, proofs pulled | gossip, proofs pulled | direct | direct | direct |
| profile / seed | eip7870-mix / 1 | eip7870-mix / 2 | eip7870-mix / 1 | eip7870-mix / 2 | eip7870-mix / 3 |
| hosts | 312 | 312 | 312 | 312 | 312 |
| subnets × votes per subnet | 2 × 1,560 | 2 × 1,560 | 2 × 1,560 | 2 × 1,560 | 2 × 1,560 |
| direct topics × recipients | – | – | 8 × 16 | 8 × 16 | 8 × 16 |
| slots analysed | 5 | 5 | 5 | 5 | 5 |
| vote latency p50/p90/p99/max (ms) | 591/2078/3418/3966 | 669/2215/3499/3990 | 138/300/430/653 | 146/304/432/672 | 140/304/432/678 |
| vote latency p99 by voter link (ms) | attester 3466, cloud 3155 | attester 3525, cloud 3246 | attester 432, cloud 420 | attester 433, cloud 420 | attester 434, cloud 420 |
| votes held at deadline: min / mean | 24.9% / 84.18% | 20.4% / 83.85% | 100.0% / 100.00% | 100.0% / 100.00% | 100.0% / 100.00% |
| aggregators with 100 % (of agg·slots) | 96/160 | 119/160 | 640/640 | 640/640 | 640/640 |
| time to 100 % of votes after vote start: p50 / max (s) | 4.39 / 8.49 | 4.80 / 9.80 | 0.88 / 1.10 | 0.88 / 1.15 | 0.86 / 1.15 |
| proposer: proofs per slot (min–max) | 0–4 | 4–4 | 16–16 | 16–16 | 16–16 |
| proposer: 1st / last proof after 1st emitted (s) | nan / nan | 1.10 / 1.35 | 0.44 / 1.10 | 0.45 / 1.17 | 0.57 / 1.39 |
| proofs | pull | pull | pull | pull | pull |
| proofs emitted per slot | 32 | 32 | 128 | 128 | 128 |
| network bytes received in vote phase / slot | 6,947.5 MiB | 6,725.8 MiB | 159.1 MiB | 159.1 MiB | 159.1 MiB |
| bytes received per needed vote byte (κ) | 2.29 | 2.22 | 1.02 | 1.02 | 1.02 |
| gossip messages dropped from send queues, run total (forward / publish) | 15,288,345 / 2,692 | 15,636,578 / 3,099 | – | – | – |
| errors | 2 | 1 | 0 | 0 | 0 |

| run | node class | votes rx | votes tx | proofs rx | proofs tx |
|---|---|---|---|---|---|
| gp-dc-s1 | aggregator | 27.57 MiB | 31.14 MiB | 6.42 MiB | 3.93 MiB |
| gp-dc-s1 | member-attester | 14.45 MiB | 17.41 MiB | 6.69 MiB | 7.87 MiB |
| gp-dc-s1 | member-cloud | 32.89 MiB | 32.95 MiB | 6.69 MiB | 2.57 MiB |
| gp-dc-s1 | proposer | 25.93 MiB | 26.95 MiB | 9.41 MiB | 10.01 MiB |
| gp-dc-s1 | voter-attester | 13.80 MiB | 18.10 MiB | 6.42 MiB | 7.74 MiB |
| gp-dc-s1 | voter-cloud | 31.54 MiB | 32.19 MiB | 6.56 MiB | 2.43 MiB |
| gp-dc-s2 | aggregator | 29.09 MiB | 30.78 MiB | 7.83 MiB | 4.78 MiB |
| gp-dc-s2 | member-attester | 15.54 MiB | 18.08 MiB | 7.42 MiB | 8.05 MiB |
| gp-dc-s2 | member-cloud | 32.27 MiB | 33.37 MiB | 7.64 MiB | 3.41 MiB |
| gp-dc-s2 | proposer | 26.09 MiB | 27.10 MiB | 9.56 MiB | 7.79 MiB |
| gp-dc-s2 | voter-attester | 14.04 MiB | 18.76 MiB | 6.84 MiB | 8.22 MiB |
| gp-dc-s2 | voter-cloud | 28.84 MiB | 28.48 MiB | 7.37 MiB | 2.93 MiB |
| d-dc-s1 | aggregator | 1.23 MiB | 0.01 MiB | 0.00 MiB | 0.03 MiB |
| d-dc-s1 | proposer | 0.00 MiB | 0.00 MiB | 3.45 MiB | 0.01 MiB |
| d-dc-s1 | voter-attester | 0.01 MiB | 0.86 MiB | 0.00 MiB | 0.00 MiB |
| d-dc-s1 | voter-cloud | 0.01 MiB | 0.86 MiB | 0.00 MiB | 0.00 MiB |
| d-dc-s2 | aggregator | 1.23 MiB | 0.01 MiB | 0.00 MiB | 0.03 MiB |
| d-dc-s2 | proposer | 0.00 MiB | 0.00 MiB | 3.45 MiB | 0.01 MiB |
| d-dc-s2 | voter-attester | 0.01 MiB | 0.86 MiB | 0.00 MiB | 0.00 MiB |
| d-dc-s2 | voter-cloud | 0.01 MiB | 0.86 MiB | 0.00 MiB | 0.00 MiB |
| d-dc-s3 | aggregator | 1.23 MiB | 0.01 MiB | 0.00 MiB | 0.03 MiB |
| d-dc-s3 | proposer | 0.00 MiB | 0.00 MiB | 3.45 MiB | 0.01 MiB |
| d-dc-s3 | voter-attester | 0.01 MiB | 0.86 MiB | 0.00 MiB | 0.00 MiB |
| d-dc-s3 | voter-cloud | 0.01 MiB | 0.86 MiB | 0.00 MiB | 0.00 MiB |

In `gp-dc-s1` the proposer received no proof at all in one slot: the
aggregators' announcements queued behind gossip traffic on saturated links
(the 2 errors are those announcements timing out after 20 s).

"MiB" counts libp2p transport bytes (noise + yamux framing included, TCP/IP
headers excluded). κ is the bytes received in the vote phase divided by the
vote payload the receiver needed: every vote of both subnets for a gossip
member, the votes of its topic for a direct recipient.

## What the runs show

1. **Direct delivery is unaffected by scale and EIP-7870 links.**
   - Every recipient held 100 % of its topic's votes at the deadline in every
     slot of every run: 480 recipient·slots at the 32-slot cadence, 1,920 at the
     8-slot cadence, and the 15 Mbit/s-upload stress run.
   - p99 vote latency is 423–434 ms in all of them: one hop plus TCP on
     pre-opened connections. A voter sends 0.14 MiB per slot (0.86 MiB at
     8 slots), far below even a 15 Mbit/s uplink.
   - κ = 1.02 throughout.
2. **Gossip saturates EIP-7870 attester links even with one PQ subnet.**
   - A member of two subnets must forward ~9–10 MiB of votes per slot, nearly
     all in the second or two after voting. That is 3.2 s of a 25 Mbit/s
     uplink.
   - rust-libp2p drops forwards that wait in a peer's send queue for more
     than 1 s: ~2,300 per node per slot. Votes still arrive through other
     mesh peers and IHAVE/IWANT, but late: p99 2.3–2.6 s, worst 3.8 s. Each
     run left 0.10–0.20 % of the needed votes missing at the deadline, and
     the worst aggregator·slot held 89.5 %.
   - The drops are why κ is 4.2 rather than the ~6.7 gossip sends when links
     keep up. The network sheds the bytes it cannot carry.
   - One subnet alone (`gp-1sub`) already drops ~170k forwards per slot
     (κ 5.9), but every vote arrives in time (p99 1.1 s).
   - Cloud voters do not escape. Their votes travel through attester-link
     meshes too (p99 1.7–1.9 s).
   - At 15 Mbit/s attester uploads (`gp-min-s1`): p99 2.6 s, more drops
     (κ 3.2), 0.05 % missing.
3. **At the 8-slot cadence gossip fails; direct does not notice.**
   - Gossip with 1,560 votes per subnet (2 seeds): **16 % of the votes
     aggregators needed were missing at the deadline** (39,498 and 40,306 of
     249,600). The worst aggregator·slot held 20–25 %, and only 96–119 of 160
     aggregator·slots ever got every vote. rust-libp2p dropped ~3M forwards
     per slot.
   - Direct: 100 % at every recipient, p99 432 ms. The proposer, acting as an
     internal aggregator, held all 16 pulled proofs (3.45 MiB) 1.1–1.4 s
     after the first was emitted, on a 100/50 builder link.
4. **Flooding proofs breaks gossip outright.** With the 32 proofs of the two subnets flooded
   (`g-s1`, `g-s2`), the proof traffic spills into the next slot:
   - vote-phase traffic climbs every slot (κ 7.6 averaged over 5 slots);
   - 8.4–10.3 % of the needed votes are missing at the deadline, and some
     aggregator·slots held 0.3 %;
   - p99 vote latency is 3.6 s;
   - the proposer itself held only 86–93 % of the proofs by the end of the
     slot (59 % in the worst slot).
   Announce-then-pull moves 0.86 MiB per slot (3.45 MiB at 8 slots) to the
   proposer only.
5. **Cold connections cost about half a second.** Dialling TCP + noise +
   yamux at vote time (`d-cold-s1`) raises the p99 from 0.42 s to 0.98 s and
   the last vote to 2.0 s, inside the budget.

### Corrections to earlier versions of this file

The first runs (217 hosts, one subnet) and the first version of this file
used unpatched Shadow 3.3. It ignores per-host upload limits (every host
uploaded at its download rate), and it stalls writes over 64 KiB. Every
number above comes from the patched build.

| finding | first runs (217 hosts) | 312 hosts, uploads not enforced | now (uploads enforced) |
|---|---|---|---|
| gossip κ | 6.1–6.25 | 5.2 (6.7 one subnet) | 4.2 (5.9 one subnet): saturated queues drop more |
| subnet vote traffic, gossip ÷ direct | ≈ 80× | ≈ 100× | ≈ 80× (2 subnets), 112× (1 subnet) |
| gossip vote p99 | 0.8–1.1 s | 1.4–1.9 s | **2.3–2.6 s** (1 subnet: 1.1 s; 8-slot: 3.4–3.5 s) |
| gossip votes missing at deadline | 0 | 0–4 of 62,560 | **0.10–0.20 %** (8-slot: **16 %**) |
| direct vote p99 | 0.42 s | 0.42 s | 0.42–0.43 s; 100 % delivered everywhere |

## Limits of this simulation

- Two subnets with every host in both, not 64 subnets with 2 each. Per-node
  load is right; mesh overlap is higher than on mainnet.
- Proving and verification are delays (1.45 s), not computed. Signature
  verification CPU is not modelled; gossip would also verify each vote before
  forwarding, which adds to its latency.
- No packet loss, no adversarial aggregators, no peer scoring.
- rust-libp2p's send-queue limits (1 s forward, 5 s publish) shape how gossip
  degrades. Other clients queue differently; with unbounded queues gossip would
  deliver more votes, but later.
