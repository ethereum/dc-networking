---
title: Decoupled Voting

---

# Decoupled Voting

## Current Proposal

![5fg](https://notes.ethereum.org/_uploads/rk9ov21mMl.png)

*Figure source: `../research/ac/fg_slot_structure_current.excalidraw`. Timing below assumes today's 12 s slots and ~1M validators for concreteness; the structure itself is parametric.*

**How to read the figure.** Two consecutive slots are shown (solid vertical lines = slot boundaries, dashed lines = phase boundaries).

- The **top three bands** are the per-slot AC machinery: the logical consensus phases (propose → heartbeat vote → fast confirm → payload vote → available confirm → freeze), the corresponding network traffic (beacon block, then beacon votes and payload votes as 512-to-all, plus data propagation and sampling ahead of the availability vote), and execution (execute the current payload, then build the next one).
- The **bottom two bands** are the decoupled finality gadget. Logically, a vote's lifetime spans two slots. On the network, the finality votes of the cohort assigned to slot *i* propagate from slot-*i* fast-confirm until deep into slot *i+1* (committee subnets feeding aggregators, "8192-to-256"), after which the aggregates are broadcast on the global topic ("16-to-all"). The second row of arrows is the next cohort, shifted by one slot: rounds are **pipelined across slots**, giving even per-slot load and rewards.

#### Description

1. **Duty assignment — epoch transition.** Each validator runs a VRF to determine (i) the subround (slot) in which it sends its finality vote, (ii) the committee/subnet in which it does so, and (iii) whether it has aggregation duty. Peers / subnet subscriptions are chosen accordingly. Below, the assigned slot is *i*.
2. **Target selection — slot *i*, T = 4s + X.** Pick as target the highest confirmed AC block. The offset X ∈ [0s, 8s] is a design choice:
    - X = 0 adds the least finality latency (the figure shows this case: the vote is cast right after fast confirmation);
    - X = 8s might allow for better healing (the target is picked later, so the AC has had more time to stabilize);
    - anything in between trades latency for robustness.
3. **Vote propagation.** Send the vote through the attestation-propagation mechanism of our choice (in the figure: committee subnets feeding aggregators, 8192-to-256). Propagation may use the whole window up to the aggregation deadline in slot *i+1*.
4. **Aggregation — slot *i+1*, T = 8s.** Aggregators publish their aggregates on the global topic (in the figure: 16-to-all).
5. **Inclusion — slot *i+2*.** The next proposer merges the published aggregates and includes them in its block. With ~100,000 votes per subround this is ~12.5 kB of participation bitfield, plus the aggregate signatures.

#### Advantages

+ **Performance:** votes can propagate across an entire slot and beyond — up to 16 s from vote emission (slot *i*, T = 4s) to aggregation (slot *i+1*, T = 8s), versus ~4 s today. That is **up to ~4× more propagation time off the bat**, obtained by overlapping the tail of slot *i* with the head of slot *i+1*.
+ **Fairness:** the vote window is long, so poorly-connected validators are not disadvantaged.
+ **Load spreading:** FG traffic can be distributed around the critical paths of the other per-slot load (block propagation, payload, sampling).
+ **Even and continuous aggregation:** every slot carries one subround's aggregates, so proposer rewards have little variance.
+ **Configurable:** the vote time X can be tuned depending on the stability requirement of Goldfish.

#### Changes to think about

- [ ] Checkpoints can be finalized in the middle of an epoch (in the common case, a checkpoint finalizes in slot 17 or 25). Is that the point at which the epoch transition (and thus duty assignment) should be computed?
- [ ] Are proposers barred from including "future" attestations? I.e., does an attester have to prove that it is allowed to propagate in its subround, and how much does that proof cost? (TODO — presumably nothing.)
- [ ] Subround-division difficulties, VRF costs / drawbacks, etc. (Note: ~100k votes per subround at 10⁶ validators implies ~8–10 subrounds per round — this is what sizes the 8-slot round budget; as the validator set consolidates, fewer subrounds are needed and rounds can shorten toward the 4-slot stretch goal.)


## (Deprecated) Exploration of Possible Voting Patterns

#### Option 1: Similar to today

![1fg](https://notes.ethereum.org/_uploads/BkgJV2y7fl.png)

+ allows Goldfish-based healing

#### Option 2: Target past slot

![2fg](https://notes.ethereum.org/_uploads/B1U4EnkXzx.png)

+ more time for propagation
+ target is more likely to be equal -> better aggregation
+ more stability?
+ better healing? (possibility mentioned by Roberto)

#### Option 3: Voting across slots

![3fg](https://notes.ethereum.org/_uploads/rJeZ9P31QGx.png)

- without pipelining: uneven rewards and uneven load.

#### Option 4: Voting across slots with uneven spacing

![4fg](https://notes.ethereum.org/_uploads/Hkp5whkmMe.png)

- technically "optimized", but uneven rewards, and load not synced to other loads -> harder to benchmark, maintain, etc.

#### Option 5: Pipelined (current proposal)

![5fg](https://notes.ethereum.org/_uploads/rk9ov21mMl.png)

+ even load
+ makes good use of resources
+ configurable vote time depending on the stability requirement of Goldfish
+ attestations can be propagated across the entire slot (technically ~3× improvement off the bat, possibly even more as we can overlap head & tail)


## Yann's Scratchpad

=> Option 2 or Option 5 make the most sense.

Option 2 has the issue that it increases latency.
Option 5 has the issue that target selection happens very quickly, which might lead to bad side effects.
- However, Option 2 only increases it by 2 Delta (in theory).
- Actually, you can parametrize between 2 and 5: voting can start whenever we want, without big changes! The important thing is that aggregation will only happen next slot.


PQ design: aggregate the best you have.


Idea: Back-Off / Optimistic design — we go for all, already now :)

1. Much more impressive
2. Might not have the opportunity to improve in the future
3. Flexible
4. We need something to strive for
5. Already goes in the direction of PQ => which will be multi-stage too!

- Back-off is also needed because if the first collection is skipped, we might skip even with 2/3 honest.
=> if we don't reach 2/3, we delay the start of the next round by 2x (8 -> 16)

### Idea 1:
- maintain subnet infrastructure (8 slots)
- send immediately to voluntary brokers (cheap side channel)
    - load: 8x regular load for a super node
    - 1M × 100B = 100MB in ~8 seconds. 100Mbit/s most optimistic, but opening connections is the worst part.
    - a 128kB array just to store indices... for a single aggregation...


Open questions:
- Is it too much to even have 1 bit of index per block?
- How does PQ improve this?
