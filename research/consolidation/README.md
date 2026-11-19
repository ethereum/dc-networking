---
title: Consolidation — who holds the non-consolidated validators?
status: wip
provenance: agent
---

# Consolidation: who holds the non-consolidated validators?

> **Provenance: agent.** Numbers come from [`snapshot.py`](snapshot.py) run on
> 2026-11-19; not yet reviewed line by line.

**Question.** Of the validators that have not consolidated, how many belong to
small entities (fewer than 10, or fewer than 100, validators)?

**Unit.** Everything below is counted per **unique withdrawal address**, the
party that has to sign a consolidation request. That is a proxy for an entity,
not the same thing: one operator can sit behind many addresses, and many
operators behind one (see [Caveats](#caveats)).

**Answer.** Few. Grouping the 750,795 non-consolidated (0x01) validators by
unique withdrawal address:

- addresses with **fewer than 10** validators hold **28,621 (3.8 %)**;
- addresses with **fewer than 100** validators hold **86,767 (11.6 %)**;
- the other **88.4 %** sit behind 873 addresses with 100 or more validators
  each, and 39.8 % behind just four.

Half of the under-10 group are per-validator contracts of pools (mostly Rocket
Pool minipools), so plain-wallet small stakers are closer to 1.8 % (under 10)
and 8.1 % (under 100).

Small addresses are a small share of what is left to consolidate, but they are
most of what remains after everyone else has: with every address merged down to
2,048 ETH validators the set is about 55,000 validators, and 31,000 of those
belong to addresses with fewer than 10 validators' worth of stake.

## Snapshot

Finalized state at slot 15,688,352 (2026-11-19), active validators only.

| Credentials | Validators | Share | Effective balance | Share |
|---|---:|---:|---:|---:|
| 0x00 (BLS, no withdrawal address) | 8,657 | 1.1 % | 0.28M ETH | 0.6 % |
| 0x01 (32 ETH cap) | 750,795 | 95.7 % | 24.03M ETH | 54.2 % |
| 0x02 (compounding) | 24,984 | 3.2 % | 20.04M ETH | 45.2 % |
| Total | 784,436 | | 44.34M ETH | |

"Non-consolidated" below means 0x01. Two smaller groups are left out of the
tables:

- **0x00**: 8,657 validators that cannot be a consolidation source until they
  set a withdrawal address. They sit behind 6,184 distinct BLS credentials
  (the largest shared by 1,172 validators); 6,386 of them are in groups of
  fewer than 10, which would raise the under-10 share to 4.6 % of 759,452.
- **0x02 still at 32 ETH or less**: 7,668 validators behind 1,851 addresses,
  converted but not merged.

## Non-consolidated validators per unique withdrawal address

Mainnet, finalized state at slot 15,688,352 (19 Nov 2026): 750,795
non-consolidated (0x01) validators behind 23,498 unique withdrawal addresses.
Read as: addresses with fewer than 10 validators hold 3.8 % of them, addresses
with fewer than 100 hold 11.6 %.

| Validators sharing one withdrawal address | Unique withdrawal addresses | Validators | Share of non-consolidated validators | Cumulative |
|---|---:|---:|---:|---:|
| 1 | 18,038 | 18,038 | 2.4 % | 2.4 % |
| 2–9 | 2,773 | 10,583 | 1.4 % | 3.8 % |
| 10–99 | 1,814 | 58,146 | 7.7 % | 11.6 % |
| 100–999 | 806 | 199,489 | 26.6 % | 38.1 % |
| 1,000–9,999 | 63 | 165,392 | 22.0 % | 60.2 % |
| 10,000+ | 4 | 299,147 | 39.8 % | 100 % |

The largest address is Lido's withdrawal vault with 189,039 validators (25.2 %).
Lido has been consolidating its Curated Module since September 2026 (reported
as 265,000+ validators into about 4,000,
[ETH Daily](https://ethdaily.io/lido-begins-validator-consolidation)), so that
block is already scheduled to go. The next three (72,999, 20,315 and 16,794
validators) are not labelled here.

## The same in powers of two (MAX_EB = 2,048 ETH)

64 validators × 32 ETH = 2,048 ETH, one full validator at the maximum effective
balance. An address with fewer than 64 validators cannot fill even one; it ends
up as a single validator however far it consolidates. Same snapshot, same
750,795 validators and 23,498 unique withdrawal addresses.

| Validators sharing one withdrawal address | Unique withdrawal addresses | Validators | Share of non-consolidated validators | Validators left if merged to 2,048 ETH |
|---|---:|---:|---:|---:|
| 1 | 18,038 | 18,038 | 2.4 % | 18,038 |
| 2–63 (less than one full validator) | 4,388 | 53,025 | 7.1 % | 4,388 |
| 64–1,023 | 1,010 | 220,239 | 29.3 % | 3,928 |
| 1,024 or more | 62 | 459,493 | 61.2 % | 7,211 |
| **Total** | **23,498** | **750,795** | **100 %** | **33,565** |

- **90.5 %** of non-consolidated validators belong to addresses that can fill
  at least one 2,048 ETH validator. If only those 1,072 addresses consolidated
  fully, their 679,732 validators would become 11,139.
- The **9.5 %** below 64 are 22,426 addresses. Each can shrink to one validator
  at most, so together they go from 71,063 to 22,426 and no further.
- The last column counts 0x01 validators only (⌈validators / 64⌉ per address);
  the [floor section](#the-floor-if-everyone-consolidates) also includes 0x00
  and 0x02. Finer power-of-two buckets are in the results file
  (`by_power_of_two`).

## What kind of address is it?

A withdrawal address with one validator is not always a solo staker: some pools
deploy one contract per validator. Each address was classified with
`eth_getCode`, and contracts were grouped by bytecode. Cells count 0x01
validators; rows match the first table.

| Validators sharing one withdrawal address | Plain wallet (EOA) | Owner contract | Pool, one contract per validator | Other contract |
|---|---:|---:|---:|---:|
| 1 | 4,106 | 233 | 13,678 | 21 |
| 2–9 | 9,642 | 906 | 0 | 35 |
| 10–99 | 47,391 | 10,418 | 0 | 337 |
| 100–999 | 168,333 | 29,692 | 0 | 1,464 |
| 1,000+ | 190,339 | 22,839 | 0 | 251,361 |

- **Plain wallet**: no code, or an EIP-7702 delegation. The best proxy for an
  independent staker. Under 10: 13,748 validators (1.8 %). Under 100: 61,139
  (8.1 %).
- **Owner contract**: one contract per owner, so the cluster size still means
  something. EigenPods (482 addresses, 32,403 validators), Safes (170 / 21,117),
  BitGo wallets (47 / 5,401), StakeWise vaults (18 / 3,036), Rocket Pool
  megapools (109 / 2,131).
- **Pool, one contract per validator**: Rocket Pool minipools (10,961), an
  unverified clone family (1,862), Kiln `FeeRecipient` clones (738), a second
  unverified family (117). Rocket Pool node operators are often small
  themselves, but their consolidation path is the protocol's (megapools), not
  an individual decision.

So the under-10 figure ranges from 1.8 % (plain wallets only) to 3.8 % (every
address), and the under-100 figure from 8.1 % to 11.6 %.

## The floor if everyone consolidates

If every withdrawal address merged down to ⌈stake / 2,048 ETH⌉ validators.
This table is not the 0x01-only view above: addresses are sized by their total
stake across all credential types, so an address that has already consolidated
counts by its 0x02 stake, and 0x00 validators are grouped by their BLS
credential. That is why 144 addresses reach 1,000+ units here against 67 with
1,000+ 0x01 validators: 15 more get there with 0x02 stake on top of fewer 0x01
validators, 61 hold no 0x01 at all, and one is a 0x00 credential shared by
1,172 validators.

| Total stake per address (32 ETH units, all credential types) | Addresses | Validators today | Validators at the floor |
|---|---:|---:|---:|
| 1 | 25,920 | 25,920 | 25,920 |
| 2–9 | 5,394 | 14,384 | 5,394 |
| 10–99 | 3,005 | 60,973 | 3,282 |
| 100–999 | 1,721 | 201,265 | 7,733 |
| 1,000–9,999 | 138 | 175,551 | 5,168 |
| 10,000+ | 6 | 306,343 | 7,348 |
| Total | 36,184 | 784,436 | 54,845 |

- Addresses under 10 units are 5.1 % of validators today and 57 % of the floor.
- The floor overstates small stakers by the roughly 13,700 per-validator pool
  contracts; with those merged into their pools it is nearer 41,000.
- For [`requirements.md`](../../design/requirements.md): the $V \to 10^4$ end
  of the range needs small stakers to pool or exit, not just large entities to
  consolidate. Large holders alone get to about $5 \times 10^4$.

## Caveats

- **Withdrawal address is not operator.** A staking-as-a-service customer with
  three validators counts as a small address although a large operator runs the
  nodes. For "who must act to consolidate" the owner is the right unit; for
  node counts it is not.
- **Small operators inside large addresses are invisible.** Lido's Community
  Staking Module and Simple DVT operators all sit behind the Lido vault.
- **One owner can use several addresses**, which makes owners look smaller
  than they are. Clustering by deposit address (the heuristic behind hildobby's
  Dune labels) would catch some of this; not done here.
- **Unverified families** are classed as per-validator pool contracts on the
  strength of identical bytecode and cluster size 1 only.

## Cross-checks

- stakefish, snapshot of 2026-10-22: 790,476 0x01 validators, 41.5 % of stake
  on 0x02
  ([blog](https://blog.stake.fish/ethereum-validator-consolidation-2026/)).
  Consistent with 750,795 and 45.2 % four weeks later. No breakdown by holder
  size there.
- Benseddik, Kraner, Tessone, *When Staking Rewards Compound*
  ([arXiv:2606.23337](https://arxiv.org/abs/2606.23337)), data of 2026-04-07:
  splits labelled providers from unlabelled validators only; about 180k 0x01
  validators unlabelled, which they call an upper bound on solo stakers.

## Reproduce

```sh
python3 snapshot.py --cache /tmp/consolidation --out results/YYYY-MM-DD.json
```

Standard library only; public beacon API and execution RPC by default. Output
of the run above: [`results/2026-11-19.json`](results/2026-11-19.json).
