# Sources

The facts the post and the studies take from outside sources, collected on 12 November 2026.

## leanVM

- Repository https://github.com/leanEthereum/leanVM, documentation and benchmarks https://leanethereum.github.io/leanVM/ (commit 40f877dc2).
- Benchmark design: 16 subnets of 1,400 leanXMSS signatures per slot, one aggregate proof per subnet, then recursion 16 → 1, one proof per slot. 716,800 validators = 32 slots × 16 subnets × 1,400.
- leanXMSS signature: 2,404 bytes (4 + 1,200 + 1,200); public key 32 bytes. "Not the definitive parameter set." (leanXMSS `main.tex` L48–49)
- Aggregating 1,400 signatures: proof 248 KiB; 0.40 s (EPYC 9355P, 64 threads), 0.95 s (M4 Max), 1.02 s (Core Ultra 7 265), 1.57 s (Ryzen 7 PRO 8700GE); 3.8–5.5 GiB RAM.
- Recursion 16 → 1: proof 358 KiB; 0.43 s, 0.91 s, 1.13 s and 1.69 s on the same machines.
- README (M4 Max): 1,400 XMSS in 0.964 s, 246.8 KiB; 2-to-1 recursion 0.154 s, 321.5 KiB; verifying 6–9 ms. "Not (yet) production ready."

## pq-aggregation-model, Barnabé Monnot

- https://github.com/barnabemonnot/pq-aggregation-model, live at https://cpv-pq-aggregation-model-ef07c8ce.pages.dev
- v2 gossip load per node = backbone subnets × signatures per subnet × (signature + overhead) × duplicates; the subnet drains at the node-weighted mean link capacity.
- Defaults: 1,000,000 validators, 8,000 nodes, 2 backbone subnets per node, 1.2 KiB signatures, 100 B overhead, 2 duplicates ("an assumption"), mesh D 8; home tier 25/50 Mbit/s (87.5 % of nodes, 10 % of stake), pro tier 1 Gbit.
- Calibration: Sukun's decoupled-consensus simulation (P2P call #10): 500 nodes and 2,500 votes per subnet, 2 subnets per node, no IDONTWANT; home nodes peaked near 40 Mbit/s on 25 Mbit/s links and queues cleared before the next burst.
- Our runs measured 3.9–5.1 PQ copies per message with IDONTWANT, so 2 duplicates is optimistic.
- Leaf proving and merge times are calibrated on the leanVM site (15 October 2026).

## Ethereum roadmap context

- pqai27, Ethlabs, https://ethlabs.org/writings/pqai27.html: "pq decoupled consensus or pq Gasper is the biggest open question"; PQ Gasper is "plausibly the easier change", but it is unclear "how many compromises that takes".
- Potuz, https://www.potuz.net/posts/pq/: Gasper broadcasts 30K attestations per slot with 2 KB or 1.2 KB signatures; 300 KB aggregates must reach the proposer; the final recursion takes 2–3 s; "We need POCs on the CL right now to see whether gossipsub is even viable"; he would rather move to decoupled consensus than change slot or epoch parameters.
- Decoupled consensus, ethresear.ch post 24527: a 512-member committee per slot; finality votes from the full validator set, off the critical path.
- https://github.com/ethereum/dc-networking: finality votes in 4 s + 4 s units sized like today's attestation slot (open question 17); about 100k votes per subround at 10⁶ validators.
