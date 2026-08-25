# Benchmarking with eth-slot-sim

To simulate all the consensus networking objects [eth-slot-sim](https://github.com/sukunrt/eth-slot-sim) provides a shadow and simnet based simulator. The instructions for running the simulations are in the repo.


## Previous round numbers:

Batched attestations simulation repo: 
- https://github.com/sukunrt/batched-attestation-sim

Slot simulation repo: 
- https://github.com/sukunrt/eth-slot-sim


## Simulation setup

- 4000 nodes, 400_000 validators
    - 1/2 the mainnet size
    - The finality subnets are the same size as you'd expect on mainnet
        - 40 Subnets: 10k validators each
        - on mainnet, we'd have 80Subnets: 10k validators each
    - 50% cloud nodes with 1Gbit bandwidth, 50% home nodes with 25Mbps upload and 50Mbps download
    - cloud nodes have 100-1000 validators with a mean of 200.
    - home nodes have 2-3 validators. 
    - 128kB block size
 ![photo_2026-05-29_16-26-00](https://hackmd.io/_uploads/rJ7Cxgvgfl.jpg)
    - ![image](https://hackmd.io/_uploads/Sywomevlzl.png)



- AC Slot:
    - Block proposal from (random uniform: 2s-2.5s)
    - 512 attestors 
    - **NOTE**: This is not epbs style yet. 
- Finality Slot(Round?):
    - Single finality sub - round spanning 10 AC Slots
        - everyone just votes at the same time
    - 10 finality sub rounds spanning 10 AC Slots 
    - 5 finality sub rounds spanning 5 AC Slots


## Single finality round: 
- As expected the problem with not having sub rounds in a finality round is that it messes up the timings for the AC Slot which corresponds to the start of the Finality Round. 
![brave_screenshot_www.tldraw.com (1)](https://hackmd.io/_uploads/SyRqPW_bfl.png)

- 10 AC Slots per Finality round

| kind                  | p25 | p50 | p75 | p90  | p99    | p99.9  |
  |-----------------------|-----|-----|-----|------|--------|--------|
  | block                 | 391 | 458 | 546 | 668  | 9,892  | 23,539 |
  | columns               | 150 | 184 | 222 | 259  | 330    | 8,184  |
  | AC votes              | 241 | 291 | 348 | 409  | 4,499  | 15,839 |
  | finality attestations | 273 | 493 | 920 | 1,808| 11,984 | 60,967 |
  | finality aggregates   | 205 | 275 | 438 | 821  | 2,032  | 5,936  |

![n4000-base-slot10-delay-h](https://hackmd.io/_uploads/Hk5wMfObMg.png)


## Finality sub rounds: 

every AC slot we run a finality sub round and aggregate from V/NUM_AC_SLOTS_PER_FINALITY_ROUND validators

![brave_screenshot_www.tldraw.com (2)](https://hackmd.io/_uploads/HkXAPbuWMe.png)




## 10 finality sub rounds (current mainnet attestation)
 | kind                  | p25 | p50 | p75 | p90 | p99   | p99.9 |
  |-----------------------|-----|-----|-----|-----|-------|-------|
  | block                 | 524 | 577 | 640 | 711 | 874   | 988   |
  | columns               | 230 | 260 | 292 | 325 | 385   | 421   |
  | AC votes              | 222 | 270 | 323 | 377 | 498   | 754   |
  | finality attestations | 137 | 182 | 236 | 303 | 1,825 | 4,185 |
  | finality aggregates   | 188 | 237 | 298 | 369 | 550   | 777   |

![n4000-seg-k10-slot12-delay-h](https://hackmd.io/_uploads/HkorXfdbfg.png)


## 5 finality sub rounds (current mainnet attestation)
 
message latencies: 

  | kind                  | p25 | p50 | p75 | p90 | p99   | p99.9  |
  |-----------------------|-----|-----|-----|-----|-------|--------|
  | block                 | 485 | 549 | 632 | 742 | 1,529 | 8,881  |
  | columns               | 231 | 260 | 292 | 324 | 388   | 1,125  |
  | AC votes              | 228 | 279 | 338 | 402 | 1,237 | 8,254  |
  | finality attestations | 150 | 210 | 300 | 630 | 2,788 | 10,823 |
  | finality aggregates   | 192 | 245 | 315 | 409 | 2,071 | 4,691  |

![n4000-seg-k5-slot12-delay-h](https://hackmd.io/_uploads/rkqOXMdWzl.png)


## 5 finality sub rounds (batched attestations)

message latencies: 
  | kind                  | p25 | p50 | p75 | p90 | p99   | p99.9 |
  |-----------------------|-----|-----|-----|-----|-------|-------|
  | block                 | 438 | 497 | 574 | 672 | 971   | 7,692 |
  | columns               | 183 | 212 | 246 | 278 | 342   | 391   |
  | AC votes              | 220 | 267 | 321 | 375 | 512   | 6,519 |
  | finality attestations | 155 | 212 | 283 | 401 | 1,432 | 4,655 |
  | finality aggregates   | 199 | 247 | 315 | 401 | 726   | 5,126 |

![n4000-seg-partial-k5-slot6-delay-h](https://hackmd.io/_uploads/Hka9QzdZzl.png)


# Next Steps:
- There's no EL traffic currently. Need to add simulated EL network timings. 
- check with anton regarding large network simulations on a teku client
- simulate with bigger blocks
- add topic level bandwidth plots to better understand the contention
- check why p50 for a single finality round(no subrounds) is better?
