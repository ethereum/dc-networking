
### Gasper: 32,768 votes per slot, each to all 128 aggregators within 4 s

| quantity | leanSig (3.03 KiB) | leanVM XMSS (1.17 KiB) |
|---|---|---|
| aggregator download per slot | 102.2 MiB (214 Mbit/s over 4 s) | 42.7 MiB (90 Mbit/s over 4 s) |
| voter upload per vote (R copies) | 409 KiB | 171 KiB |
| max votes per slot a node can send in 4 s: EIP-7870 minimum (15 Mbit/s up) | 18 (≈ 573 validators) | 43 (≈ 1,373 validators) |
| max votes per slot a node can send in 4 s: EIP-7870 attester (25 up / 50 down) | 30 (≈ 955 validators) | 71 (≈ 2,288 validators) |
| max votes per slot a node can send in 4 s: EIP-7870 local builder (50 up / 100 down) | 60 (≈ 1,910 validators) | 143 (≈ 4,575 validators) |
| max votes per slot a node can send in 4 s: 1 Gbit/s | 1,194 (≈ 38,203 validators) | 2,860 (≈ 91,508 validators) |

### Gasper: aggregates of 220 KiB the next proposer can receive in 4 s (line rate)

| proposer downlink | pushed directly (proposer or decoy set) | flooded to every node (κ = kappa) |
|---|---|---|
| EIP-7870 attester (50 Mbit/s) | 111 | 17 |
| EIP-7870 local builder (100 Mbit/s) | 222 | 33 |
| 1 Gbit/s | 2,219 | 331 |

### 800k validators, 32-slot round (today's cadence)

| quantity | leanSig (3.03 KiB) | leanVM XMSS (1.17 KiB) |
|---|---|---|
| votes per slot / per topic | 25,000 / 391 | 25,000 / 391 |
| vote size on the wire | 3 KiB | 1 KiB |
| tree: topics → … → 1, hops vote→block | 64 → 8 → 1, 3 hops | 64 → 8 → 1, 3 hops |
| **direct** · solo voter: upload per vote (K copies) | 51 KiB (0.42 Mbit/s) | 21 KiB (0.17 Mbit/s) |
| **direct** · 1,000-validator node: upload per slot | 1.6 MiB (6.5 Mbit/s) | 667 KiB (2.7 Mbit/s) |
| **direct** · leaf aggregator: download per topic·slot | 1.2 MiB (2.6 Mbit/s) | 532 KiB (1.1 Mbit/s) |
| **direct** · leaf aggregator: prove one topic (8 cores / fast) | 1.4 s / 0.33 s | 1.4 s / 0.33 s |
| **direct** · leaf aggregator: proof upload per slot | 440 KiB | 440 KiB |
| **direct** · internal aggregator / proposer: download per slot | 3.4 MiB (14 Mbit/s) | 3.4 MiB (14 Mbit/s) |
| **direct** · internal aggregator: fold 8 → 1 | 2.1 s serial, 0.9 s as a 3-level tree | 2.1 s serial, 0.9 s as a 3-level tree |
| **direct** · super-aggregator (all topics): download per slot | 78.0 MiB (164 Mbit/s) | 32.6 MiB (68 Mbit/s) |
| **direct** · every node: final proof (gossip) | 1.7 MiB | 1.7 MiB |
| **direct** · leaf-proving machines needed (8 cores / fast) | 247 / 56 | 247 / 56 |
| **direct** · network vote bytes per slot | 1,273.1 MiB | 531.5 MiB |
| **gossip** · subscribers per subnet | 312 | 312 |
| **gossip** · node in 2 subnets: down ≈ up per slot | 16.3 MiB (34.3 Mbit/s) | 6.8 MiB (14.3 Mbit/s) |
| **gossip** · …that upload on an EIP-7870 attester link (25 Mbit/s) | 5.5 s per slot | 2.3 s per slot |
| **gossip** · every node: aggregate topic, 16 per committee | 1,474.0 MiB (6,182 Mbit/s) | 1,474.0 MiB (6,182 Mbit/s) |
| **gossip** · every node: aggregate topic, 1 per committee | 92.1 MiB (386 Mbit/s) | 92.1 MiB (386 Mbit/s) |
| **gossip** · network vote bytes per slot | 160 GiB | 67 GiB |
| network vote bytes, gossip ÷ direct | 128× | 128× |
| (BLS votes + gossip, same cadence) node in 2 subnets per slot | 1.3 MiB | 1.3 MiB |

### 800k validators, 8-slot round (DC target)

| quantity | leanSig (3.03 KiB) | leanVM XMSS (1.17 KiB) |
|---|---|---|
| votes per slot / per topic | 100,000 / 391 | 100,000 / 391 |
| vote size on the wire | 3 KiB | 1 KiB |
| tree: topics → … → 1, hops vote→block | 256 → 32 → 4 → 1, 4 hops | 256 → 32 → 4 → 1, 4 hops |
| **direct** · solo voter: upload per vote (K copies) | 51 KiB (0.42 Mbit/s) | 21 KiB (0.17 Mbit/s) |
| **direct** · 1,000-validator node: upload per slot | 6.2 MiB (26.2 Mbit/s) | 2.6 MiB (10.9 Mbit/s) |
| **direct** · leaf aggregator: download per topic·slot | 1.2 MiB (2.6 Mbit/s) | 532 KiB (1.1 Mbit/s) |
| **direct** · leaf aggregator: prove one topic (8 cores / fast) | 1.4 s / 0.33 s | 1.4 s / 0.33 s |
| **direct** · leaf aggregator: proof upload per slot | 440 KiB | 440 KiB |
| **direct** · internal aggregator / proposer: download per slot | 3.4 MiB (14 Mbit/s) | 3.4 MiB (14 Mbit/s) |
| **direct** · internal aggregator: fold 8 → 1 | 2.1 s serial, 0.9 s as a 3-level tree | 2.1 s serial, 0.9 s as a 3-level tree |
| **direct** · super-aggregator (all topics): download per slot | 312.0 MiB (654 Mbit/s) | 130.3 MiB (273 Mbit/s) |
| **direct** · every node: final proof (gossip) | 1.7 MiB | 1.7 MiB |
| **direct** · leaf-proving machines needed (8 cores / fast) | 988 / 222 | 988 / 222 |
| **direct** · network vote bytes per slot | 5,092.5 MiB | 2,126.0 MiB |
| **gossip** · subscribers per subnet | 312 | 312 |
| **gossip** · node in 2 subnets: down ≈ up per slot | 65.3 MiB (137.0 Mbit/s) | 27.3 MiB (57.2 Mbit/s) |
| **gossip** · …that upload on an EIP-7870 attester link (25 Mbit/s) | 21.9 s per slot | 9.2 s per slot |
| **gossip** · every node: aggregate topic, 16 per committee | 1,474.0 MiB (6,182 Mbit/s) | 1,474.0 MiB (6,182 Mbit/s) |
| **gossip** · every node: aggregate topic, 1 per committee | 92.1 MiB (386 Mbit/s) | 92.1 MiB (386 Mbit/s) |
| **gossip** · network vote bytes per slot | 638 GiB | 266 GiB |
| network vote bytes, gossip ÷ direct | 128× | 128× |
| (BLS votes + gossip, same cadence) node in 2 subnets per slot | 5.3 MiB | 5.3 MiB |

### Censorship: chance that all K recipients of a vote are adversarial

| K | adversarial share of subscribers | P(vote censored) | censored votes per 800k |
|---|---|---|---|
| 4 | 10% | 1.0e-04 | 80 |
| 4 | 33% | 1.2e-02 | 9.88e+03 |
| 8 | 10% | 1.0e-08 | 0.008 |
| 8 | 33% | 1.5e-04 | 122 |
| 16 | 10% | 1.0e-16 | 8e-11 |
| 16 | 33% | 2.3e-08 | 0.0186 |

### Parameters

- `P` = 10000
- `K` = 16
- `S` = 16
- `fanout` = 8
- `S2` = 16
- `pulls_per_child` = 2
- `vote_overhead` = 168
- `proof` = 225280
- `final_proof` = 262144
- `prove_sps_8c` = 270.0
- `prove_sps_fast` = 1200.0
- `prove_budget_s` = 6.0
- `merge_s` = 0.3
- `send_window_s` = 1.0
- `collect_window_s` = 4.0
- `proof_window_s` = 2.0
- `gossip_subnets` = 64
- `subnets_per_node` = 2
- `kappa` = 6.7
- `kappa_direct` = 1.02
- `attester_up_mbps` = 25
- `aggs_per_committee` = 16
