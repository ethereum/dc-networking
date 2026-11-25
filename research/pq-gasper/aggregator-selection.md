---
title: PQ Gasper — 4 RANDAO-drawn aggregators vs a VRF lottery (DoS)
status: wip
date: 2026-11-18
provenance: agent
---

> **Provenance: agent.** Written 2026-11-18 by an agent, expanding the avenue "Reduce number of Aggregators" of [the avenues post](../../posts/pq-gasper-avenues.md). Yann has not reviewed it line by line. Every number comes from [`sim/aggregator_dos.py`](sim/aggregator_dos.py) or [`sim/blind_attack.py`](sim/blind_attack.py) (stdlib; run them with `python3`). The model is back-of-envelope:
> - V = 800,000 validators, 16 subnets, so n ≈ 1,563 voters per subnet per slot and 512 committee-slots per epoch;
> - an aggregate that never appears loses its committee's votes for good, unless a fallback exists.

# Four public aggregators instead of sixteen secret ones: DoS resilience

**Notation.**
- **lottery-k**: a private VRF lottery that targets k aggregators per subnet, as today.
- **draw-k**: exactly k aggregators per subnet, drawn publicly from a RANDAO seed. The proposal under discussion is draw-4.

## Short answer

- **Machines to flood to kill one subnet's aggregate for one slot:**
  - draw-4: **at most 4**, named 32–64 slots ahead if the draw reuses the committee seed.
  - lottery-16, attacker watching subnet joins: **up to 16**, and it sees only the aggregators that had to join the subnet. Prysm, the one client checked, announces the duty up to two epochs ahead.
  - lottery-16, attacker not watching: **~500–1,410 machines** for a 90 % chance, i.e. every machine hosting a committee member except the ~10 least-loaded ([Blind attacker](#blind-attacker-if-the-aggregators-were-secret)).
  - So the draw is **4× cheaper** to attack than a watched lottery and **~125–350× cheaper** than an unwatched one.
- **If aggregators were secret, 4 vs 16 barely matters.** Killing all of them with 90 % probability takes 1,523 of 1,563 members with 4 and 1,553 with 16, i.e. 97.4 % vs 99.4 % of the committee. Secrecy, not the count, is what makes the attack expensive.
- **Halting finality** means suppressing 171 of the epoch's 512 committee-slots.
  - draw-4 with a full validator→IP map: **~21 machines** flooded at any moment, i.e. 684 floods of a few seconds per epoch.
  - With a partial map, finality halts once **76 %** of honest stake sits on machines the attacker can find and flood, or 55 % if it also holds 20 % of stake. A watched lottery-16 needs **93 %** (86 %) spotted in real time.
  - A stalled chain starts the inactivity leak on honest validators whose votes never landed. That is the StakeBleed outcome, reached with per-machine floods instead of BGP hijacks.
- **Without DoS, exactness helps.**
  - draw-4 never leaves a subnet without an aggregator; lottery-4 does so 1.8 % of the time.
  - Against withholding at β = 1/3, draw-4 loses 1.2 % of committee-slots, lottery-4 loses 6.9 %, and lottery-16 only 0.002 %.
- **The crux: can large operators' machines be flooded for a few seconds?** They hold most stake, so under any rule most aggregators sit on them.
  - If yes, draw-4 puts finality within reach of a booter-class attacker.
  - If no, draw-4 only exposes the rare committees whose 4 aggregators are all small machines.
- **Fix that keeps the bandwidth win:** 4 public primaries plus a permissionless fallback that costs bandwidth only when they fail ([Mitigations](#mitigations)). A late aggregate still earns the target vote, so the fallback can be slow.

## The designs

- **Today's lottery.**
  - A committee member aggregates if `hash(BLS slot signature) mod (n // 16) == 0` ([phase0/validator.md:726–739](https://github.com/ethereum/consensus-specs/blob/master/specs/phase0/validator.md#aggregation-selection), `TARGET_AGGREGATORS_PER_COMMITTEE = 16` at :105).
  - BLS signatures are unique, so nobody can grind the output, and only the key holder can compute it before revealing it. That makes it a VRF.
  - The count per subnet is Binomial(n, 16/n), about Poisson(16).
- **It does not port to leanXMSS.** WOTS+ signatures are not unique, so a validator can grind `hash(signature)` until it selects itself ([ethresear.ch/t/24906](https://ethresear.ch/t/24906) §2). A private PQ lottery needs a real PQ VRF:
  - t/24906's PRF-commitment VRF: a 116 KB WHIR proof, 81 ms to prove and 19 ms to verify on an M2. Sent standalone, that adds ~55 % to each 209 KiB aggregate. Proving its three Poseidon calls inside the aggregate's own leanVM proof should make it nearly free (untested).
  - A hash commitment to per-slot tickets. [EIP-8321](https://eips.ethereum.org/EIPS/eip-8321)'s hash chain does this for RANDAO reveals but advances one link per proposal, so per-slot tickets would need an index-addressable variant (e.g. a Merkle tree).
- **The draw.**
  - Exactly 4 per subnet, drawn from a RANDAO seed.
  - Reusing the committee seed (`get_seed`, which reads the mix at the end of epoch E−2: phase0/beacon-chain.md:1052–1059, `MIN_SEED_LOOKAHEAD = 1` at :265) names epoch E's aggregators 32–64 slots ahead.
  - No selection proof is needed: gossip validation is a table lookup.
- **Why 4.**
  - Each aggregate is a 209 KiB leanVM proof ([../pq/README.md](../pq/README.md), leanVM benchmarks @ `035eff47a`).
  - 16 per subnet is 256 aggregates, i.e. 52 MiB per slot or 36.5 Mbit/s per copy. 4 per subnet is 13 MiB, i.e. 9.1 Mbit/s.
- **Why exactly 4.**
  - lottery-4 leaves a subnet empty 1.8 % of the time, about 9.3 committee-slots per epoch.
  - The sync committee targets 16 aggregators per subcommittee for this reason (Ben Edgington, FF chat 2026-09-04; [eth2book](https://eth2book.info/capella/part2/building_blocks/aggregator/#sync-committee-aggregators)).

## Attacker

- **Flood.** The attacker can take one known IP offline for the aggregation window, a few seconds. That is easy against home links and harder against data-center machines behind provider DDoS protection.
- **Map** (validator index → IP).
  - Heimbach et al. (USENIX Security 2025) located over 15 % of validators with 4 passive nodes in 3 days (May 2024).
  - Doumanidis & Apostolaki (FC 2026) mapped all 1.06 M validators to 4,600 IP prefixes with a timing classifier that is 91 % accurate.
  - Since Fulu, a node's ENR also advertises roughly how much stake it runs (custody group count).
- **Watch** (sybil peers read gossipsub SUBSCRIBE messages).
  - In the spec, aggregators join their subnet, while other attesters need not (phase0/validator.md:353–359).
  - Prysm joins as soon as it knows the duty, for every duty through the end of the next epoch (`validator/client/subnets.go:20–74`, `beacon-chain/sync/subscriber_beacon_attestation.go:42–50` @ `88ef966`). Other clients were not checked.
  - So joining a subnet a node isn't on announces "aggregator soon". Aggregators already on the subnet stay invisible: nodes on 2 of the 16 backbone subnets, and super nodes on all of them.
- **Stake.** The attacker may also control a share β of validators, whose aggregators withhold.

## Machines to flood

| Target | draw-4 | lottery-16, watched | lottery-16, not watched |
|---|---:|---:|---:|
| one subnet, one slot | ≤ 4 | ≤ 16 (visible ones only) | ~500–1,410 (90 % kill) |
| all 16 subnets, one slot | ≤ 64 | ≤ 256 | most validator machines |
| finality halt, at any moment | ~21 | ~86 | most validator machines, continuously |
| notice | 32–64 slots | up to 2 epochs (Prysm) | none |

- **Where ~500–1,410 comes from.** It is the blind attacker's budget for a 90 % kill, worked out in the [next section](#blind-attacker-if-the-aggregators-were-secret). Flooding that many machines silences the committee's votes too, not just its aggregators.
- **The draw's targets are named in advance.** A shorter lookahead (a seed from the parent block, ~1 slot of notice) does not change the count, because an attacker that already holds a map needs only seconds. It also makes the aggregator set head-dependent for gossip validation, and gives the previous proposer a 1-bit choice over the draw.

## Blind attacker: if the aggregators were secret

The attacker knows the committee (public) and every member's machine (its map), but not who aggregates. It floods members blind and wins only if every aggregator is among them. Exact numbers for one subnet-slot, N = 1,563 members, are from [`sim/blind_attack.py`](sim/blind_attack.py).

- **secret-k**: exactly k aggregators, kept secret. This would need a secret election, and Whisk-style SSLE is not PQ. Flooding m members kills all k with probability C(m, k) / C(N, k) ≈ (m/N)^k.
- **lottery-k**: today's rule, where each member aggregates with p = 1 / (N // k). Flooding m members kills all with probability (1 − p)^(N − m) ≈ e^(−k(1 − m/N)).

Members to flood:

| rule | P(kill) ≥ 50 % | ≥ 90 % | ≥ 99 % | mean |
|---|---:|---:|---:|---:|
| draw-4 (public) | 4 | 4 | 4 | 4 |
| secret-4 | 1,315 (84 %) | 1,523 (97.4 %) | 1,560 | 1,251 |
| lottery-4 | 1,294 (83 %) | 1,522 (97.4 %) | 1,560 | 1,181 |
| secret-16 | 1,498 (96 %) | 1,553 (99.4 %) | all 1,563 | 1,472 |
| lottery-16 | 1,497 (96 %) | 1,553 (99.4 %) | all 1,563 | 1,467 |

- **"mean"** is the expected number of members flooded, in random order, until the last aggregator is hit. For secret-k it is k(N + 1)/(k + 1).
- **The count barely matters once aggregators are secret.** Going from 4 to 16 raises the 90 % budget by 2 % (1,523 → 1,553) and the 50 % budget by 14 %. Secrecy is the factor of ~380 (1,523 vs 4).
- **What the attacker may leave alone.** With 4 secret aggregators: 248, 40 and 3 members at 50, 90 and 99 %. With 16: 65, 10 and 0. Killing all 16 subnets of a slot with 90 % probability leaves ~2 members per subnet to spare with 4, and none with 16.
- **Partial floods rarely work.**
  - Flooding half the committee kills 4 secret aggregators 6.2 % of the time, and 16 only 0.0014 % of the time.
  - Flooding 90 % kills them 66 % and 18 % of the time.
  - lottery-4 is easier on small budgets (13.5 % at half): 1.8 % of subnets draw no aggregator, and others draw only one or two.

Machines: the attacker floods the most-loaded machines first, so its budget is the number of machines hosting at least one member, minus the members it may leave alone. The table gives the median over 300 random committees for a 90 % kill:

| hosting scenario | machines hosting a member | secret-4 | lottery-16 |
|---|---:|---:|---:|
| Heimbach shape, 5,000 machines | 509 | 469 | 499 |
| Heimbach shape, 8,000 machines | 785 | 745 | 775 |
| Heimbach shape, 10,000 machines | 936 | 896 | 926 |
| 8,000 machines, 96 % of stake on the large ones | 672 | 632 | 662 |
| even spread, 100 per machine | 1,421 | 1,381 | 1,411 |

- **Heimbach shape**: Heimbach et al. found that 27 % of machines host one validator, over half host at most 4, and 11 % host more than 100. Here those 11 % hold 85–92 % of stake. The 96 % row is Kamil's super-node share.
- **So secret-4 needs ~470–1,380 machines and lottery-16 ~500–1,410**, against 4 for the public draw.
- **For finality this route is pointless.** Killing a third of the aggregates means flooding 76 % (secret-4) or 93 % (16) of each committee. That silences those members' own votes anyway, and flooding a third of the voters directly is cheaper. Secret aggregators stop being the weak point. Public ones cost 4 floods per committee.
- **"Secret" assumes nothing leaks.** Under a watched lottery the budget drops to the aggregators that show up joining the subnet ([Attacker](#attacker)).

## Partial maps: when finality halts

The table gives the share of honest stake that halts finality: for a draw, the share the attacker can find and flood; for a lottery, the share it can spot in real time and flood.

| attacker stake β | draw-4 | draw-8 | draw-16 | lottery-16 | lottery-4 |
|---:|---:|---:|---:|---:|---:|
| 0 | 76 % | 87 % | 93 % | 93 % | 73 % |
| 0.2 | 55 % | 75 % | 87 % | 86 % | 44 % |
| 0.3 | 24 % | 55 % | 75 % | 73 % | 0 % |

- **Count matters more than privacy here.** Once detection is real-time, draw-16 ≈ lottery-16 and draw-4 ≈ lottery-4.
- **Privacy matters through what an attacker can detect.**
  - Under a lottery: only aggregators that must join the subnet.
  - Under a draw: every aggregator on a mapped machine.
- **Super nodes.** They reportedly hold ~96 % of stake and would join all subnets (Kamil Salakhiev, [27 Oct call](../../meetings/2026-10-27.md)).
  - Under a lottery their duties never show, so a watcher spots at most ~4 % of aggregators.
  - Under the draw that 96 % is named in advance, so the only question is whether a super node can be flooded for a few seconds.
- **Withholding alone, with no DoS, halts finality** at β ≥ 29.2 % for lottery-4, 32.6 % for draw-4 and 33.3 % for lottery-16.

## Without DoS

| per committee-slot (per epoch) | lottery-16 | lottery-4 | draw-4 |
|---|---:|---:|---:|
| no aggregator at all | 1e-7 (0.00005) | 1.8 % (9.3) | 0 |
| no honest aggregator, β = 1/3 | 2.2e-5 (0.011) | 6.9 % (35.5) | 1.2 % (6.3) |

- **Captured committee.** Every aggregator in it is adversarial, so it can withhold, or publish an aggregate that leaves out chosen validators.
- **Grinding.** The last proposers of epoch E−2 can withhold to pick among 2^k seeds. Choosing the seed with the most captured committees lifts draw-4's 6.3 per epoch to 7.7 (1 bit), 9.0 (2 bits) and 11.1 (4 bits).

## Other effects

- **Targeted slots.** 64 floods remove all of one slot's aggregates.
  - Head credit needs inclusion in the next slot (deneb/beacon-chain.md:264–265).
  - Nodes that are not on a subnet see its votes only through aggregates.
  - That is a cheap lever for reorg and balancing attacks, and it needs the slot, not stake.
- **Upside of a public set.**
  - No selection proof per aggregate (t/24906's standalone proof would be 116 KB).
  - Gossip validation is a lookup.
  - Attesters can push votes straight to the 4.

## Mitigations

1. **Permissionless fallback (recommended).**
   - Rule: if no aggregate covering at least θ of the subnet appears by a deadline τ, any node already on the subnet may produce one.
   - Use announce-then-fetch, as in Kamil's announcement pool (27 Oct call). The bitfield goes out first, and peers fetch the 209 KiB proof only if it beats the best one seen by at least X signatures. Extra traffic is then at most n/X proofs per committee, and zero in the happy case.
   - Suppressing a committee then means flooding everyone on the subnet, including every super node that holds all its votes.
   - Being late is cheap. Deneb accepts votes from the current and previous epoch (deneb/beacon-chain.md:386), and since EIP-7045 the target flag has no inclusion deadline (:261–263). Only the slot's head credit is lost.
   - This also covers captured primaries that withhold.
   - Open: the cost of verifying a leanVM proof for each fetched aggregate.
2. **Private backups** (4 public primaries plus lottery backups).
   - At β = 1/3, 8.6e-4 of committee-slots (0.44 per epoch) end with no honest aggregate.
   - Needs a PQ VRF. Backups also leak by joining the subnet, like today's aggregators, unless they are drawn from nodes already on it.
   - Mitigation 1 does the same job without the VRF.
3. **draw-8 or lottery-8.**
   - draw-8 doubles the flood cost and moves the finality-halt share to 87 %, at 26 MiB per slot.
   - lottery-8 leaves a subnet empty 0.033 % of the time (0.17 committee-slots per epoch).
4. **If any lottery stays,** clients should join an aggregator subnet at the slot, not up to two epochs early. Otherwise a watcher sees most small-node aggregators.
5. **Operators** can put aggregation behind throwaway relays or sentries, so the mapped IP is not the aggregating machine.

## Open questions

- **What share of stake can a booter-class attacker flood for ~5 s?** That share decides whether draw-4 is a finality risk. Answering it means classifying stake by hosting: home, bare metal, or cloud with scrubbing.
- **How long does leanVM take to verify one aggregate?** That bounds the spam cost of the fallback.
- **Can the t/24906 VRF relation go inside the aggregate proof?** Its cost, and where it sits in gossip-validation order, are unknown.
