# Gossipsub slow-peer handling by client

Checked in source code on 2026-11-07 for the realistic PQ runs on p2psims. Those runs use libp2p-gossipsub 0.49.5 with Lighthouse's scoring on every host. So every host gets Lighthouse's slow-peer penalty and rust-libp2p's queue expiry, whatever client it represents.

## Summary

| Client (library, version read) | Slow-peer score penalty | Per-peer outbound limit | When full | Do queued messages expire? |
| --- | --- | --- | --- | --- |
| Lighthouse v8.3.2 (sigp rust-libp2p fork, gossipsub 0.51.0) | **Yes.** +1 per failed message, weight −10, threshold 0, decay 0.1 per 12 s, decay\_to\_zero 0.01 | 5,000 data messages; 20,000 GRAFT/PRUNE/IDONTWANT | Refused; +1 penalty | Yes: forwards after 1 s, own publishes after 5 s |
| Grandine develop and 2.0.6 (sigp fork) | **Yes**, same values | Same | Same | Same |
| Prysm v7.3.1 (go-libp2p-pubsub v0.18.0) | No. Score has P1–P7 only | 1,000 RPCs | RPC dropped; metrics only | No. Only a 30 s write deadline, which resets the stream |
| Teku 26.10.3 (jvm-libp2p 1.3.8) | Weak. +1 to P7 after ≥ 4 MiB is pending for 3 heartbeats; P7 threshold 6. May never fire on TCP + mplex | No count limit | Bulk parts trimmed once 4 MiB is pending | No |
| Nimbus v26.10.2 (nim-libp2p v2.3.8) | The term exists, but Nimbus leaves its weight at 0.0 | 1,024 relays, 512 own publishes, 256 control writes in flight | Dropped. At the control cap, the peer is disconnected | No |
| Lodestar v1.50.1 (@libp2p/gossipsub 17.1.2) | No | 16 MiB stream write buffer | Stream aborted and its buffer discarded | No |

## How the Rust penalty works

- +1 for each message refused because the peer's queue is full, and +1 for each queued message dropped on timeout. IHAVE, IWANT and IDONTWANT refusals count too. It is counted per message, not per heartbeat.
- The penalty lands on the peer the node failed to send to. The code never checks whether the local node is the slow side, so a node with a slow uplink or long, lossy paths penalises its own peers.
- At the next heartbeat, any peer with a total score below 0 is pruned from every mesh. It gets a 60 s backoff and its GRAFTs are refused. The mesh is refilled only with peers scoring ≥ 0.

## Where the sim's 0.49.5 differs from Lighthouse's fork (0.51)

- **Queues.** 0.49.5 has 2,500 slots for own publishes and 2,500 shared by forwards, IHAVE, IWANT and IDONTWANT. The fork has one 5,000-slot data queue and puts IDONTWANT in a separate 20,000-slot queue. The sim may therefore refuse, and penalise, more than Lighthouse does.
- **Expiry.** 0.49.5 also drops stale messages at the head of a blocked queue; the fork drops them only when they are taken off the queue.
- **Possible 0.49.x bug** (found by reading the code, not tested): stale own publishes dropped by `poll_stale` don't free their slot in the 2,500 publish cap, so the slots leak until the peer disconnects.

## Lighthouse gossipsub defaults

From config.rs, network\_load 3: D = 5, D\_lo = 3, D\_hi = 10, outbound\_min 2, gossip\_lazy 3, heartbeat 1 s, flood publish off, duplicate cache 768 s.

## Consequence for the PQ runs

- In the calibrated key cell, the chronic 1 Gbit misses come from far-region Prysm and Teku hosts that have scored most of their peers negative. Neither client has this penalty.
- p2psims is rerunning with the penalty on Lighthouse and Grandine hosts only.
- Still a known gap: non-Rust clients don't expire queued forwards, but the sim drops them after 1 s on every host.

## Other per-client scoring differences

Checked on 2026-11-08. The sim applies the Rust behaviour in both columns on every host. p2psims is building a binary (cf2) that applies them per client.

| Client | Mesh-delivery scoring (P3, P3b) | Broken IWANT promises (P7) |
| --- | --- | --- |
| Lighthouse, Grandine | On. Activates 17 slots after a peer joins an attestation-subnet mesh, 1 epoch on blocks and aggregates | +1 for every requested id that doesn't arrive |
| Prysm | **Off on every topic** (`meshDeliveryIsScored = false`) | +1 for one random id per IWANT |
| Teku | On, 17-slot activation on attestation subnets | +1 for one random id per IWANT |
| Lodestar | On, 17-slot activation on attestation subnets | +1 for one random id per IWANT |
| Nimbus | On for block, attestation and aggregate topics (values not checked) | No promise tracking found |

- P7 grows with the square of the count. Penalising every id therefore lets one lost IWANT reply covering many ids push a peer to −10^8 or below, far past the −16,000 graylist threshold.
- P3 strength also differs. Lighthouse and Grandine use weight −topic\_weight ([Lighthouse L339](https://github.com/sigp/lighthouse/blob/a376defa30470923556d91bdeb15a802e297f31f/beacon_node/lighthouse_network/src/service/gossipsub_scoring_parameters.rs#L339)), so a mesh peer that delivers nothing costs at most (topic\_weight × threshold)², about 18 per PQ topic at 800k in the sim. Teku ([L301–L302](https://github.com/Consensys/teku/blob/9591436143efd2b0e457ea2b6614eee678fca770/networking/eth2/src/main/java/tech/pegasys/teku/networking/eth2/gossip/config/GossipScoringConfigurator.java#L301-L302)), Lodestar ([L331–L332](https://github.com/ChainSafe/lodestar/blob/56cf1ab7b16a2805a985e104f2e7fcbaad98a22b/packages/beacon-node/src/network/gossip/scoringParameters.ts#L331-L332)) and Nimbus ([L220–L225](https://github.com/status-im/nimbus-eth2/blob/0abc0dd0fc0750a8875c49089d074f7d7197b62c/beacon_chain/networking/topic_params.nim#L220-L225)) use −max\_positive\_score / (topic\_weight × threshold²), so the same peer costs the whole max positive score, on each topic: 107.5 with Lighthouse's constants, or 157.5 once the 16 PQ subnets count as scored topics, as in the sim's PQ runs.
- Re-requests also differ. rust-libp2p doesn't ask another peer for an id it has already requested until that promise expires after 3 s ([behaviour.rs L1399](https://github.com/sigp/rust-libp2p/blob/accba72bb4eafc692ac518339ef2c4080b6f8461/protocols/gossipsub/src/behaviour.rs#L1399), [config.rs L555](https://github.com/sigp/rust-libp2p/blob/accba72bb4eafc692ac518339ef2c4080b6f8461/protocols/gossipsub/src/config.rs#L555)). go-libp2p-pubsub ([L977–L980](https://github.com/libp2p/go-libp2p-pubsub/blob/9140768cdee6486205fcf0d7f335ae61b7adda3d/gossipsub.go#L977-L980)), js-libp2p ([L1402–L1403](https://github.com/libp2p/js-libp2p/blob/2bad1dfb55978973320019d3b81004644b098602/packages/gossipsub/src/gossipsub.ts#L1402-L1403)), jvm-libp2p ([L416](https://github.com/libp2p/jvm-libp2p/blob/3a832c569c333b34910efa433d75676dacffec69/libp2p/src/main/kotlin/io/libp2p/pubsub/gossip/GossipRouter.kt#L416)) and nim-libp2p ([L309–L317](https://github.com/iftech/nim-libp2p/blob/5ada87dc18938e2fac9635ae3f7caab00a9e0ce0/libp2p/protocols/pubsub/gossipsub/behavior.nim#L309-L317)) request every unseen id from each peer that advertises it, limited only per peer and per heartbeat.
- In the 20-slot PQ run, 1 Gbit completeness steps down at slot 16, after P3 activates at slot 15. Only about 150–300 peer-topic pairs are in deficit at a time, and the 8 hosts that miss in most slots are unaffected. But from slot 16, non-Rust views (no slow-peer penalty in that build) start scoring a few far-region hosts negative with P3-sized scores and prune them, and those hosts lose 1 Gbit mesh peers. P3 is therefore the likely trigger of the step.

Sources: P3 in [Prysm](https://github.com/OffchainLabs/prysm/blob/96d418cd964b083e37519a9df274030a1beac7db/beacon-chain/p2p/gossip_scoring_params.go#L73), [Lighthouse](https://github.com/sigp/lighthouse/blob/a376defa30470923556d91bdeb15a802e297f31f/beacon_node/lighthouse_network/src/service/gossipsub_scoring_parameters.rs#L189-L226), [Grandine](https://github.com/grandinetech/eth2_libp2p/blob/35d69804fac416956998ef3e783b2338bcee75e7/src/service/gossipsub_scoring_parameters.rs#L228), [Teku](https://github.com/Consensys/teku/blob/9591436143efd2b0e457ea2b6614eee678fca770/networking/eth2/src/main/java/tech/pegasys/teku/networking/eth2/gossip/config/GossipScoringConfigurator.java#L226-L238), [Lodestar](https://github.com/ChainSafe/lodestar/blob/56cf1ab7b16a2805a985e104f2e7fcbaad98a22b/packages/beacon-node/src/network/gossip/scoringParameters.ts#L276-L288), [Nimbus](https://github.com/status-im/nimbus-eth2/blob/0abc0dd0fc0750a8875c49089d074f7d7197b62c/beacon_chain/networking/topic_params.nim#L280-L354). Promises in [rust-libp2p (sigp fork)](https://github.com/sigp/rust-libp2p/blob/accba72bb4eafc692ac518339ef2c4080b6f8461/protocols/gossipsub/src/gossip_promises.rs#L53-L61), [go-libp2p-pubsub](https://github.com/libp2p/go-libp2p-pubsub/blob/9140768cdee6486205fcf0d7f335ae61b7adda3d/gossip_tracer.go#L48-L54), [jvm-libp2p](https://github.com/libp2p/jvm-libp2p/blob/3a832c569c333b34910efa433d75676dacffec69/libp2p/src/main/kotlin/io/libp2p/pubsub/gossip/GossipRouter.kt#L851-L856), [js-libp2p](https://github.com/libp2p/js-libp2p/blob/2bad1dfb55978973320019d3b81004644b098602/packages/gossipsub/src/tracer.ts#L45-L48).

## Sources

- Lighthouse: [scoring values](https://github.com/sigp/lighthouse/blob/a376defa30470923556d91bdeb15a802e297f31f/beacon_node/lighthouse_network/src/service/gossipsub_scoring_parameters.rs#L98-L100), [network load](https://github.com/sigp/lighthouse/blob/a376defa30470923556d91bdeb15a802e297f31f/beacon_node/lighthouse_network/src/config.rs#L423-L432), [fork pin](https://github.com/sigp/lighthouse/blob/a376defa30470923556d91bdeb15a802e297f31f/Cargo.toml#L175), [fork queue](https://github.com/sigp/rust-libp2p/blob/accba72bb4eafc692ac518339ef2c4080b6f8461/protocols/gossipsub/src/queue.rs#L30-L84)
- rust-libp2p 0.49.5: [queue-full penalty](https://github.com/libp2p/rust-libp2p/blob/51ed5f00e1b0620ded3444ecadf18477052148ea/protocols/gossipsub/src/behaviour.rs#L2910-L2945), [timeout penalty](https://github.com/libp2p/rust-libp2p/blob/51ed5f00e1b0620ded3444ecadf18477052148ea/protocols/gossipsub/src/behaviour.rs#L3243-L3258), [score term](https://github.com/libp2p/rust-libp2p/blob/51ed5f00e1b0620ded3444ecadf18477052148ea/protocols/gossipsub/src/peer_score.rs#L398-L402), [negative-score prune](https://github.com/libp2p/rust-libp2p/blob/51ed5f00e1b0620ded3444ecadf18477052148ea/protocols/gossipsub/src/behaviour.rs#L2174-L2199)
- Grandine: [scoring values](https://github.com/grandinetech/eth2_libp2p/blob/35d69804fac416956998ef3e783b2338bcee75e7/src/service/gossipsub_scoring_parameters.rs#L103-L105)
- Prysm: [score function](https://github.com/libp2p/go-libp2p-pubsub/blob/9140768cdee6486205fcf0d7f335ae61b7adda3d/score.go#L271-L348), [drops ignored by the score](https://github.com/libp2p/go-libp2p-pubsub/blob/9140768cdee6486205fcf0d7f335ae61b7adda3d/score.go#L841), [queue size flag](https://github.com/OffchainLabs/prysm/blob/96d418cd964b083e37519a9df274030a1beac7db/cmd/flags.go#L188-L192)
- Teku: [slow peer to P7](https://github.com/libp2p/jvm-libp2p/blob/3a832c569c333b34910efa433d75676dacffec69/libp2p/src/main/kotlin/io/libp2p/pubsub/gossip/GossipScore.kt#L317-L323), [thresholds](https://github.com/libp2p/jvm-libp2p/blob/3a832c569c333b34910efa433d75676dacffec69/libp2p/src/main/kotlin/io/libp2p/pubsub/gossip/GossipParams.kt#L36-L44)
- Nimbus: [nim-libp2p defaults](https://github.com/iftech/nim-libp2p/blob/5ada87dc18938e2fac9635ae3f7caab00a9e0ce0/libp2p/protocols/pubsub/gossipsub.nim#L90-L131), [Nimbus parameters](https://github.com/status-im/nimbus-eth2/blob/0abc0dd0fc0750a8875c49089d074f7d7197b62c/beacon_chain/networking/eth2_network.nim#L2585-L2617)
- Lodestar: [no backpressure](https://github.com/libp2p/js-libp2p/blob/2bad1dfb55978973320019d3b81004644b098602/packages/gossipsub/src/stream.ts#L16-L46), [16 MiB buffer](https://github.com/ChainSafe/lodestar/blob/56cf1ab7b16a2805a985e104f2e7fcbaad98a22b/packages/beacon-node/src/network/gossip/gossipsub.ts#L161-L202)
