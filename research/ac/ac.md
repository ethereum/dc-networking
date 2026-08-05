# AC 

### Q1: How does Goldfish change slot structure?


![Goldfish slot structure](https://notes.ethereum.org/_uploads/SyPp7ms1zl.png)

Learnings: 

1. We don't need 4s for vote phase anymore.
2. Confirm & Freeze phase can be longer than necessary in theory -> better for stability, if we can show that positive things happen during this time!
3. Or we increase Fast Confirm phase, to allow more nodes to fast confirm

![slot structure comparison](https://notes.ethereum.org/_uploads/rJesA77iJMl.png)

(from: https://hackmd.io/d_yOBkWZR8SNWkzAmH9sRg)


### Q2: How to best send heartbeat votes?

Quick anser: Same as PTC votes.
Possible improvement: 
1. Send votes preferentially to validators. -> PoV
2. More resilience to asynchrony -> 512 -> 1
3. High fan-out since almost no load.


### Open questions:
1. FOCIL

## Suggested Experiments

- [ ] (perf) Benchmarking k-to-all (as for PTC) -> on-going w/ Sukun
- [ ] (perf) Benchmarking (k_byz)-to-all -> on-going w/ Sukun
- [ ] (hardening) based on gossipsub: how easy to break sync assumptions?
- [ ] (hardening) design PoV baseed solution: how much can PoV help?
- [ ] (hardening) what's the best timing for fast confirmation? (more safe or more permissive? use single delta?)

