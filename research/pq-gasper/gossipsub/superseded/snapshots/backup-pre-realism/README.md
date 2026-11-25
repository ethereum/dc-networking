# p2p-ministry: WB-PQ

A gossipsub alternative for post-quantum finality votes, based on
Wonderboom: anyone can subscribe to a topic to become a direct recipient of
its votes, and aggregates move up a tree instead of being flooded.

| | |
|---|---|
| [DESIGN.md](DESIGN.md) | protocol, example system (800k validators, 32 slots), feasibility verdict |
| [model/load_model.py](model/load_model.py) → [results/model.md](results/model.md) | parametric load math (leanSig and leanVM-XMSS; 32- and 8-slot rounds) |
| [results/gasper.md](results/gasper.md) | Gasper timing (12 s slots): 32k PQ votes to 128 aggregators in 4 s, and how many aggregates reach a hidden proposer |
| [sim/](sim/README.md) → [results/sim.md](results/sim.md) | Shadow simulation of the 2 subnets a node joins (312 members, EIP-7870 links, 32- and 8-slot rounds): gossipsub vs. direct delivery, real rust-libp2p |
