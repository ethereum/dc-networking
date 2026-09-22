# Fast Finality Networking


### Settled

Design stance: **conservative delta** — most things don't change compared to today's attestation pipeline.

- 2026-07-20 — **Propagation path (voters → aggregators)**: the standard gossip vertical as of H* (Heze), including whatever updates land by then. No bespoke path (point-to-point-primary stays a future idea, see #11).
- 2026-07-20 — **Aggregation depth**: one layer, as today. Must not foreclose multi-stage later (PQ-forward, #8).
- **Vote-start offset X ∈ [0, 8] s**: not settled — parked on benchmarking (vehicle: the Shadow FF-stack stage in [poc.md](../poc/poc.md)).


### Open Questions

**Legend:** `[AC]` = Available Chain (Goldfish-based), `[FG]` = Finality Gadget. Priority: **hi** = active focus, **med** = needed for decoupled consensus, **lo** = nice-to-have. Type: **spec** / **eng** / **res** (research) / **res+eng**.

| #  | Tag   | Question / Effort                                                                                 | Type    | Prio | Related |
|----|-------|-------------------------------------------------------------------------------------------|---------|------|---------|
| 1  | AC    | How does **Goldfish view-merge** change slot duration and structure (together with ePBS & FOCIL)?           | spec    | med   | P1       |
| 2  | AC    | How to best **send heartbeat votes**?                                                         | eng     | med   | P1      |
| 3  | FG    | **Interaction** with Decoupled Consensus: When is the target decided, effect of timeout votes, target uniformity, etc.                                                               | spec+res    | hi   | P2       |
| 4  | FG    | **Safety Analysis** under Decoupled Consensus: Impact of possible Goldfish instability, short asynchrony, censorship, etc.                                                              | res    | med   | P2       |
| 5  | FG    | **Performance Analysis** under Decoupled Consensus: How short can a **decoupled-FG round** get comfortably? Which [networking patterns](https://notes.ethereum.org/ZIqFmp9ES9Ctm0Vw4LqXmA) are best?                | spec+eng | hi   | P2  |
| 6  | FG    | How does **FG healing** impact rounds & networking?                                           | res     | hi   | P2       |
| 7  | FG    | Rely on RANDAO for shuffling or use a VRF?                                           | res     | hi   | P2       |
| 8 | FG    | **PQ forward design**: leverage more flexible aggregation while dealing with higher load           | res     | hi   | —       |
| 9  | FG    | Co-design with FG: design/investigate a **back-off mechanism** to handle adverse network conditions (crashes, asynchrony or sleepiness)        | res+eng     | hi   | P2       |
| 10  | AC/FG | **PoV** for better security                                                                   | res     | lo  | -      |
| 11  | FG    | Gossip more as fallback: **point-to-point primary**                                          | eng     | lo  | -      |
| 12  | FG    | Optimistic path for faster aggregation through brokers (epecially for one-round FG)                                                          | res     | lo   | —       |
| 13 | AC/FG    | Multiple ideas to improve Privacy and Security      | res     | lo   | —       |
| 14 | AC/FG    | **Transition management** from today's pipeline (raised by Francesco; [poc.md](../poc/poc.md) stage 4 "transition testing")      | spec+eng     | med   | —       |
| 15 | AC/FG    | **Griefing attacks**: cheap, non-slashable degradation — e.g. lazy/withholding aggregators, invalid-signature & duplicate-vote spam, votes timed at phase boundaries to force timeouts (interacts with back-off #9, privacy/security #13)      | res     | med   | —       |
| 16 | FG    | **Transition timing**: early votes (X→0 or previous slot) leave no time for epoch/height-transition computation (duty assignment, subnet churn) — gap slot vs. lookahead vs. deferral vs. precompute; cross-chain survey in [transitions/](transitions/README.md)      | spec+res     | hi   | #3, #7       |
| 17 | FG    | **Pipelined 4 s + 4 s units**: FG votes in fixed units of 4 s vote + 4 s aggregation, three per slot, 23 per 8-slot round; unit-size parity with today's attestation slot as the load argument (needs ≥ 28.1 % consolidation or equivalent bundling); accepted reward variance; end-of-slot catch-all aggregates; committee size under bundled propagation — write-up in [fg/pipelined-units/](fg/pipelined-units/README.md)      | res+eng     | hi   | #3, #5, #16       |



### Our Current Thinking

=> **Spec** the interactions with new consensus in more detail (improve & expand on this: https://notes.ethereum.org/28Qw_qvtSEOI-mOpzaMUOQ?both)
=> **Build a benchmark suite** / proof of concept implementation of networking tailored for FF. Goal is to answer the critical questions above, and then use it to benchmark possible improvements later.
Plan of record: [poc.md](../poc/poc.md) — Shadow → Prysm-on-Shadow → Prysm-on-Kurtosis (August/October Glamsterdam tag-ons); **mid-October (Cambridge) milestone incl. first version of the networking specs**.



## Project P1: Design the AC slot (Goldfish heartbeat).

![image](https://notes.ethereum.org/_uploads/SyPp7ms1zl.png)

**Learnings**: 

1. We don't need 4s for vote phase anymore.
2. Confirm & Freeze phase can be longer than necessary in theory -> better for stability, if we can show that positive things happen during this time!
3. Or we increase Fast Confirm phase, to make fast confirm more live.


![image](https://notes.ethereum.org/_uploads/rJesA77iJMl.png)

(from: https://hackmd.io/d_yOBkWZR8SNWkzAmH9sRg)


#### Q2: How to best send heartbeat votes?

Quick anser: Same as PTC votes.
Possible improvement: 
1. Send votes preferentially to validators. -> PoV
2. More resilience to asynchrony -> 512 -> 1
3. High fan-out since almost no load.


#### Open questions:
- FOCIL

### Suggested Experiments

- [x] (perf) Benchmarking k-to-all (as for PTC) -> on-going w/ Sukun
- [x] (perf) Benchmarking (k_byz)-to-all -> on-going w/ Sukun
- [ ] (hardening) based on gossipsub: how easy to break sync assumptions?
- [ ] (hardening) design PoV baseed solution: how much can PoV help?
- [ ] (hardening) what's the best timing for fast confirmation? (more safe or more permissive? use single delta?)



## Project P2: Design the FG round (same privacy as today).

![image](https://notes.ethereum.org/_uploads/r1fMSXjkzx.png)


### Open questions
- How does **FG healing** impact rounds & networking?
    - On-chain SG or not?
    - Longer rounds every so often?
    - Skip a height (justification/finalization) every so often? 


### Suggested Experiments

- [ ] Benchmark performance of different designs






## Future Ideas


#### P3: Re-design the FG round with improved privacy.


#### P4: Get rid of gossip in the critical path: Explore designs with point-to-point links to aggregator based on PoV, gossip for permissionlessness and fallback.

![image](https://notes.ethereum.org/_uploads/B1REXDEyze.png)

Rationale: Permissionless gossip is great in general, but for attestation propagation to aggregator it might be both lsower and less safe. Only reason so far IMO is (non-existing) privacy.

=> Proposal: send attestation to k potential aggregators, with log(k) of them being actual aggregators.

**Churn/performance rationale (added 2026-08-04, from the [LeanGossip paper](https://doi.org/10.1145/3809481.3812610)):** Kumar–Manolios (DEBS '26) show GossipSub's churn-induced tail degradation is a *gossip-recovery* effect — p99 latency grows $0.7 \to 3.2 \to 4.8 \to 7.8$ s across 0/10/20/30% churn while pure eager-push stays flat at 0.3–0.4 s, and bandwidth blows up super-linearly (single +10%-churn steps range $\sim 1.1$–$8.7\times$ depending on config). Yann's hypothesis (team chat 2026-07-23): limiting churn in the critical path to aggregators — PoV-based point-to-point, exactly this P4 — turns it into a **performance** argument, not just a security/privacy one. Caveat: the paper models mesh-membership churn, not aggregator churn, so the honest version of the argument is "fewer churny gossip hops flatten the tail," not "aggregators are stable" — aggregator-offline remains a hard-fail the gossip fallback and Q15 griefing analysis must cover. Long-term improvement.



