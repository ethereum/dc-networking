| T64 (64 hosts × 20 slots, same config and seed) | rtt5 (CWV+SSR+DUP) | rtt6, switches off | rtt6 (CUBIC + HyStart) | rtt6, HyStart off |
|---|---|---|---|---|
| block from publish p50 / p95 / p99 (s) | 0.37 / 0.86 / 1.05 | 0.37 / 0.86 / 1.05 | 0.31 / 0.80 / 0.90 | 0.33 / 0.79 / 0.96 |
| attestations after 4 s p95 / p99 (s); missing | 2.69 / 6.41; 1.34 % | 2.69 / 6.41; 1.34 % | 1.95 / 3.57; 4.34 % | 1.93 / 3.47; 4.72 % |
| PQ latency p50 / p99, 50/15 (s) | 0.14 / 0.94 | 0.14 / 0.94 | 0.13 / 0.79 | 0.12 / 0.78 |
| PQ latency p50 / p99, 50/25 (s) | 0.21 / 1.16 | 0.21 / 1.16 | 0.2 / 0.96 | 0.2 / 0.97 |
| PQ latency p50 / p99, 1 Gbit (s) | 0.18 / 2.08 | 0.18 / 2.08 | 0.16 / 1.32 | 0.15 / 1.39 |
| incomplete 1 Gbit node·slots, slots 2–19 (of 396) | 16 | 16 | 1 | 1 |
| first timeouts per 1,000 data packets, 1G→1G / 1G→home / home→1G / home→home | 0.04 / 1.01 / 0.73 / 4.95 | 0.04 / 1.01 / 0.73 / 4.95 | 0.08 / 1.44 / 1.39 / 7.42 | 0.07 / 1.61 / 1.17 / 6.33 |
| resends per 1,000 data packets (same order) | 0.23 / 1.94 / 1.57 / 4.05 | 0.23 / 1.94 / 1.57 / 4.05 | 0.27 / 2.07 / 1.73 / 4.65 | 0.27 / 2.12 / 1.69 / 4.70 |
| all RTOs | 72886 | 72886 | 113054 | 105783 |
| fast-recovery entries per 1,000 data packets (same order) | 0.221 / 1.438 / 1.409 / 2.450 | 0.221 / 1.438 / 1.409 / 2.450 | 0.247 / 1.463 / 1.434 / 2.489 | 0.252 / 1.494 / 1.425 / 2.491 |
| cwnd p50/p90 over the run (same order) | 10/54 / 10/23 / 10/25 / 10/19 | 10/54 / 10/23 / 10/25 / 10/19 | 10/68 / 10/27 / 10/27 / 10/21 | 10/69 / 10/26 / 10/27 / 10/21 |
| restarts after idle per slot (same order) | 3993 / 6778 / 6782 / 8050 | 3993 / 6778 / 6782 / 8050 | 4259 / 6676 / 6786 / 7983 | 3911 / 6766 / 6781 / 7952 |
| ssthresh p50 after a restart, slot 2→18 (same order; unset = mostly never reduced) | 159→51 / 63→21 / 120→24 / unset→15 | 159→51 / 63→21 / 120→24 / unset→15 | 116→63 / 67→26 / 127→33 / unset→16 | 252→77 / 81→25 / 132→33 / unset→16 |
| stalls (snapshots with retransmit data and no timer) | 0 of 99194 | 0 of 99194 | 0 of 99283 | 0 of 99124 |
| RTO = SRTT + rttvar, snapshots without backoff | 93264 of 93264 | 93264 of 93264 | 91364 of 91364 | 91668 of 91668 |
