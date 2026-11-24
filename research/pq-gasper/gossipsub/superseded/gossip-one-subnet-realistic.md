# One PQ subnet per home staker on a calibrated, realistic network (2,048 hosts, Shadow)

Status: Nov 12 2026, 01:13 CET. Runs are still in the queue; this file is updated as they finish (see [Pending](#pending)).
Machine: p2psims. Working notes, with every number and run: `.amp-out/results-notes.md` there.

Question: can unmodified mainnet gossipsub, with today's clients, peer counts and background load, deliver 2,000
XMSS-size signatures per slot to every node within 4 s of the start of publishing, slot after slot? The headline
signature size is now 2.4 kB (2,458 B, the cryptographers' newest figure); 3 kB (3,072 B) is a sensitivity point.

## Verdict

**Bundling is assumed from Nov 12** (Yann): signatures travel in gossip messages of up to 16 (`--batch 16`), so the
bundled cells decide the verdict, and the unbundled results below stay as context. Bundled at 2.4 kB, every class
has ≥ 99 % of its nodes complete in every slot on the current build (seeds 1 and 2 over 20 slots, seed 1 over 50
slots) and on rtt6, the build closest to stock Linux (20 slots: worst slot 99.73 %; 50 slots at 1,024 hosts, seeds 1
and 2: worst slots 99.18 and 99.17 %, each with no host to spare). It fails on rtt5, Reno with restart after idle
(worst slot 98.38 %), and on rtt6 without the extra 1 Gbit hosts (`R20-pq-fs0-b16-2k4-rtt6-ps100-cf2-s1`, worst slot
98.30 %). For Yann's subnet question, the bundled rtt6 cell still passes with margin when every home staker also
joins one other random PQ subnet (`R20-pq-b16-2k4-2sub-rtt6-ps100-cf2-s1`): stakers hold both subnets' messages in
every slot, and the worst slot on 1 Gbit hosts is 99.59 % (one subnet: 99.73 %). The cost falls on the stakers: in
the 4–8 s window their upload rises from 27 to 38 % of the 25 Mbit/s cap on average (busiest node 42 → 58 %), and
their PQ p99 from 0.58 to 0.79 s. With today's attestation-subnet structure (`R20-pq-b16-2k4-bb2-rtt6-ps100-cf2-s1`:
every home node joins 2 random backbone subnets, and each staker also its duty subnet) it still passes, but the 15
Mbit/s home nodes without validators, now in 2 subnets, are at the rule's limit in slot 2 (3 of 330, near misses)
and use 58 % of their uplink on average in the 4–8 s window (busiest node 90 %); home PQ p99 reaches about 1 s. Each
extra subnet a home node joins adds about 80 % of the one-subnet PQ upload.

**Unbundled headline (context): 2.4 kB passes the strict rule on both seeds and over 50 slots.** `R20-pq-2k4-ps100-cf2-s1` and
`-s2`: 2,048 hosts × 20 slots, real client peer targets (×1.0), binary `cf2` (client-faithful slow-peer,
mesh-delivery and IWANT-promise scoring, and IHAVE re-requests), `--msg-bytes 2458`, `--max-msg-age 60`.
`L-pq-2k4-ps100-cf2-s1`: the same model at 1,024 hosts × 50 slots.

- **Strict rule: PASS on both seeds; seed 1 has no margin in its worst slot.** The rule requires, in every slot from slot 2, that every
  class has ≥ 99 % of its nodes holding all needed PQ messages by 8 s, with a flat backlog: messages first delivered
  after the deadline stay at a few per node per slot instead of building up from slot to slot. Copies of messages a
  node already holds that arrive after the deadline are a cost the report gives, not a pass condition.
  - Home stakers (one subnet) hold all their messages in every slot: 50/15 and 50/25 100 %.
  - 1 Gbit hosts (all 16 subnets) average 99.66 % in slots 2–15 and 99.53 % in slots 16–19. Their worst slot is
    slot 13 at 99.05 %: 7 of ~740 hosts incomplete, the most the rule allows.
  - Seed 2 (`R20-pq-2k4-ps100-cf2-s2`) passes with margin: 1 Gbit 99.96 % in slots 2–15 and 99.90 % in 16–19,
    worst slot 99.72 % (2 of ~722 hosts; the rule allows 7), 7 incomplete node·slots in all, no chronic host.
  - On the rtt4 Shadow build, which removes the current build's RTO ratchet, seed 1 passes with more margin
    (`R20-pq-2k4-rtt4-ps100-cf2-s1`): 1 Gbit 99.87 % in slots 2–15 and 99.46 % in 16–19, worst slots 17 and 18 at
    99.32 % (5 of ~740 hosts), 29 incomplete node·slots (current build 49), no chronic host.
  - On the rtt5 sensitivity build (rtt4 plus Linux's congestion-window validation, restart after idle and
    consecutive duplicate-ACK counting), seed 1 fails (`R20-pq-2k4-rtt5-ps100-cf2-s1`): 1 Gbit 98.80 % in slots 2–15
    and 98.65 % in 16–19, below 99 % in 12 of 18 slots, worst slot 8 at 97.97 % (about 15 of ~740 hosts), 164
    incomplete node·slots, 8 chronic far-region hosts (7 Prysm with 70 peers). Home classes stay at 100 %, and PQ
    messages still miss 50–80× less often than attestations in the same run. rtt5 tests how much the pass depends on
    Shadow sending bursts with larger windows than Linux would; the main line stays on rtt4 (see Loss and TCP in
    [Caveats](#caveats)). In the matched no-PQ run, block first-seen p95 from publish is 0.90 s, against 0.38 s on
    rtt4 and a relay-timed 0.82 s on mainnet that by itself does not pick a build (see Calibration). On the 64-host
    check the whole rtt5
    slowdown comes from the restart after idle, which `net.ipv4.tcp_slow_start_after_idle=0` turns off; window
    validation alone reproduces rtt4. With 16 signatures per message seed 1 fails on rtt5 too
    (`R20-pq-b16-2k4-rtt5-ps100-cf2-s1`): 1 Gbit 99.28 % in slots 2–15 and 98.75 % in 16–19, below 99 % in 6 of 18
    slots, worst slot 16 at 98.38 % (12 of ~740 hosts), with completion falling over the run. Bundling reduces rtt5's
    shortfall (112 incomplete node·slots against 164, PQ misses about halved) but does not restore the pass. With
    CUBIC's decrease instead of Reno's halving (ssthresh = 0.7 × cwnd at each loss; `RTT5_BETA=1`), the bundled cell
    passes on rtt5 (`R20-pq-b16-2k4-rtt5b-ps100-cf2-s1`): 1 Gbit 99.74 % in slots 2–15 and 99.53 % in 16–19, worst
    slot 19 at 99.33 % (5 of ~740 hosts; the rule allows 7), 41 incomplete node·slots, one chronic host, and
    completion holds over the run.
  - With window validation but no restart after idle (the rtt5 binary with `RTT5_SSR=0`, as Linux with
    `net.ipv4.tcp_slow_start_after_idle=0`), seed 1 passes with no host to spare (`R20-pq-2k4-cwv-ps100-cf2-s1`):
    1 Gbit 99.75 % in slots 2–15 and 99.26 % in 16–19, worst slot 18 at 99.05 % (7 of ~740 hosts; the rule allows
    7), 48 incomplete node·slots, no chronic host. Blocks from publish take 0.42 s at p95 (rtt4 0.37 s, rtt5 0.73 s).
    So the restart after idle, Linux's default, is what fails rtt5.
  - On rtt6, the build closest to stock Linux (rtt5 plus Linux's CUBIC with HyStart), the bundled cell passes with
    margin (`R20-pq-b16-2k4-rtt6-ps100-cf2-s1`): 1 Gbit 99.94 % in slots 2–15 and 99.83 % in 16–19, worst slots 16
    and 19 at 99.73 % (2 of ~740 hosts; the rule allows 7), 11 incomplete node·slots, no chronic host. Blocks from
    publish take 0.65 s at p95, as on rtt5b (current build 0.36 s). The unbundled headline cell passes on rtt6 too,
    with one host to spare (`R20-pq-2k4-rtt6-ps100-cf2-s1`): 1 Gbit 99.77 % in slots 2–15 and 99.46 % in 16–19,
    worst slot 19 at 99.19 % (6 of ~740 hosts), 40 incomplete node·slots (cwv 48, rtt4 29, rtt5 164), one chronic
    host. Its blocks from publish take 0.69 s at p95 (rtt5 0.73 s, cwv 0.42 s, rtt4 0.37 s). The 50-slot runs of
    both cells use rtt6. The bundled one (`L-pq-b16-2k4-rtt6-ps100-cf2-s1`) passes over 50 slots with no host to
    spare in its worst slot: 1 Gbit 99.81–99.86 % per block (current build 99.92–100 %), slot 15 at 99.18 % (3 of
    ~366 hosts; the rule allows 3), 30 incomplete node·slots (current build 5), no chronic host. No backlog builds
    up: messages first delivered after the deadline stay ≤ 0.16 per 1 Gbit node per slot. Late copies of messages
    already held still grow slowly (+6 % per 10 slots on 1 Gbit hosts over slots 30–49), at 25–32 % below the
    current build. Blocks stay at 0.61–0.70 s p95 from publish per 10-slot block (current build 0.30–0.39 s). Seed 2
    (`L-pq-b16-2k4-rtt6-ps100-cf2-s2`, another generated network and publish schedule) passes the same way, with
    fewer misses: 1 Gbit 99.86–100 % per block, slot 40 at 99.17 % (3 of ~361 hosts; the rule allows 3), 7
    incomplete node·slots, no chronic host, late first deliveries ≤ 0.04 per 1 Gbit node per slot, and late copies
    +5 % per 10 slots on 1 Gbit hosts over slots 30–49 and flat on home hosts. The unbundled one
    (`L-pq-2k4-rtt6-ps100-cf2-s1`) was stopped at sim 368 s (slots 0–27) when bundling was adopted on Nov 12.
  - With every home staker also in one other random PQ subnet (`R20-pq-b16-2k4-2sub-rtt6-ps100-cf2-s1`, rtt6,
    bundled), the cell passes with margin: both home classes are complete in every slot, the stakers on both
    subnets, and 1 Gbit hosts reach 99.87 % in slots 2–15 and 99.93 % in 16–19, worst slot 3 at 99.59 % (3 of 742
    hosts; the rule allows 7), 15 incomplete node·slots (one subnet 11), no chronic host. The stakers pay in upload:
    38 % of their 25 Mbit/s cap on average in the 4–8 s window (one subnet 27 %; busiest node 58 against 42 %) and
    110 % in the first second after publish (77 %), and their PQ p99 rises from 0.58 to 0.79 s.
  - With today's attestation-subnet structure (`R20-pq-b16-2k4-bb2-rtt6-ps100-cf2-s1`: every home node joins 2
    random backbone subnets and each staker also its duty subnet; stakers need the duty subnet, the 50/15 hosts both
    of theirs), the cell passes at the limit: 50/15 hosts reach 99.09 % in slot 2 (3 of 330; the rule allows 3, all
    near misses) after 98.48 and 99.09 % in slots 0–1, then miss in one node·slot; stakers reach 99.99 % on their
    duty subnet and 99.98 % on every subscribed subnet (worst 99.9 %); 1 Gbit hosts 99.89 % in slots 2–15 and 99.93
    % in 16–19, worst slot 2 at 99.32 % (5 of ~740). The 15 Mbit/s home nodes without validators carry the most: 58
    % of their uplink on average in the 4–8 s window (one subnet 42 %), 90 % at the busiest node, and 127 % in the
    worst node·slot, so that queue runs past 8 s. Home PQ p99 is 1.06 s (50/15) and 0.97 s (stakers), against 0.60
    and 0.58 s with one subnet.
  - Over 50 slots at 1,024 hosts (`L-pq-2k4-ps100-cf2-s1`), every class stays ≥ 99 % in every slot. 1 Gbit hosts
    reach the limit (3 of ~366 hosts) in five slots after slot 33.
  - With 16 signatures per message over 50 slots (`L-pq-b16-2k4-ps100-cf2-s1`, same hosts and seed), every class
    passes with margin: 1 Gbit ≥ 99.45 % in every slot (2 of ~366 hosts at worst), 5 incomplete node·slots in slots
    2–49, no step around slot 33.
- **3 kB (sensitivity point) fails on the same model.** `R20-pq-ps100-cf2-s1`: 1 Gbit 99.46 % (slots 2–15) and
  98.82 % (16–19), below 99 % in 4 of 18 slots (98.65–98.79 % in slots 13, 16, 17 and 19), by 2–3 hosts in each.
  Home classes 100 %. Earlier models of the 3 kB cell do worse: client-faithful slow-peer scoring only (`cf`)
  98.90 / 97.74 %, every client at −10 (`age60`) 98.78 / 98.31 %.
- **PQ signatures are delivered far more reliably than today's BLS attestations.** At 2.4 kB, 0.010 % (slots 2–15)
  and 0.021 % (16–19) of the PQ messages a 1 Gbit host needs are missing at 8 s, against 2.42 % and 2.66 % of
  attestation deliveries in the same run (all-64-subnet hosts 2.63 / 2.92 %, 2-subnet 1 Gbit hosts 0.30 / 0.09 %).
  Home hosts miss no PQ message and 0.02–0.07 % of attestations. On the same seed without PQ
  (`R20-nopq-ps100-cf2-s1`), attestations miss 0.030 / 0.018 / 1.02 % (slots 2–15) and 0.024 / 0.015 / 1.03 %
  (16–19). So the PQ load raises attestation misses 2–3×, while PQ messages themselves miss about 100× less often
  than attestations do without PQ.
- **Sustained: yes.** No backlog grows: completion, connections (164 per node), mesh links (214–235 per node) and
  failed sends stay flat over 20 slots, and no message re-floods. Over 50 slots at 1,024 hosts, 1 Gbit completion steps down once around slot 33
  (99.84 → ~99.5 %) and then stays flat to slot 49. Links, meshes and BLS misses stay flat, and negative-score peers
  and P3 deficits decline after the slot-15 onset. Only the PQ bytes that arrive after the deadline grow
  (1 Gbit hosts 194 → 1,420–1,630 kB per slot, flat from slot 12; 3 kB: 261 → 1,730–1,925). They are mostly
  duplicate copies: messages first delivered after the deadline stay below one per 1 Gbit node per slot over
  20 slots (seed 1: 0.19 in slots 2–15 and 0.41 in 16–19, at most 0.75; seed 2 at most 0.14), and in the 50-slot
  run they step up to 0.65 per slot in slots 30–49 (at most 1.54, slot 34) and stay level. Home hosts get ≤ 0.01.
- **Who misses.** One chronic far-region 1 Gbit host: 794 (Prysm, Singapore, 70 peers) in 15 of 18 slots, although
  its PQ mesh is full (degree 7.2, 92 % 1 Gbit peers). No Lighthouse host is chronic; 1860 (São Paulo) and 1430
  (Singapore) miss in 3 and 2 slots. When mesh-delivery scoring (P3) activates at slot 15, 1873 (Prysm, São Paulo)
  starts missing (4 of slots 15–19, none before): from slot 16, 2–3 non-Rust peers score it negative, as P3 does in
  Teku, Lodestar and Nimbus views, and it loses about a quarter of its inbound PQ mesh links (90 → 68). At 3 kB the
  chronic hosts are 640 (Prysm, Sydney), 945 (Lighthouse, São Paulo) and 988 (Prysm, São Paulo). Seed 2 has no chronic
  host; v400 has one (1873, Prysm, São Paulo, 14 of 18 slots).
- **Where it passes.** On 2,048 × 6 cells (slots 2–5), every class reaches ≥ 99 % with 16 signatures per message
  (b16), with 600k or 400k validators (1,500 or 1,000 messages), or with 1.2 kB signatures (s1k). It fails at 800k ×
  3 kB unbatched (both seeds) and without the extra 1 Gbit hosts (fs0, cloud 97.2–97.6 %). Over 20 slots on `cf`, b16
  holds 99.22 % on 1 Gbit hosts in slots 2–15 and 16–19 alike and misses the strict rule in only two slots (98.92 and
  98.78 %). At 2.4 kB on cf2 over 20 slots, b16 (`R20-pq-b16-2k4-ps100-cf2-s1`) passes with margin: 1 Gbit hosts
  99.87 % in slots 2–15 and 99.73 % in 16–19, worst slot 99.59 % (3 hosts; the rule allows 7), no chronic host; seed 2
  (`R20-pq-b16-2k4-ps100-cf2-s2`) passes the same way (99.94 and 99.90 %, worst slot 99.58 %, 3 hosts); on the rtt5 sensitivity build b16 fails
  (`R20-pq-b16-2k4-rtt5-ps100-cf2-s1`, worst slot 98.38 %) and passes with CUBIC's decrease
  (`R20-pq-b16-2k4-rtt5b-ps100-cf2-s1`, worst slot 99.33 %, 5 hosts), and with margin on rtt6, which adds Linux's
  CUBIC and HyStart (`R20-pq-b16-2k4-rtt6-ps100-cf2-s1`, worst slot 99.73 %, 2 hosts). 600k passes
  (worst slot 99.57 %, 3 hosts). Without the extra 1 Gbit hosts, 2.4 kB fails over 20 slots too
  (`R20-pq-fs0-2k4-ps100-cf2-s1`): 1 Gbit hosts 98.36 % in slots 2–15 and 97.15 % in 16–19, below 99 % in 16 of 18
  slots, worst 96.6 % (about 14 of ~413 hosts; the rule allows 4); home classes 100 %. On the rtt4 Shadow build
  it still fails (`R20-pq-fs0-2k4-rtt4-ps100-cf2-s1`): rtt4 halves the PQ misses, but 1 Gbit hosts reach only
  98.39 % in slots 2–15 and 98.00 % in 16–19, worst 97.82 % (9 hosts), with five chronic far-region Prysm hosts
  (70 peers). With 16 signatures per message on rtt6 it fails as well
  (`R20-pq-fs0-b16-2k4-rtt6-ps100-cf2-s1`): 1 Gbit hosts 99.21 % in slots 2–15 and 98.91 % in 16–19, below 99 % in 6
  of 18 slots, worst slot 19 at 98.30 % (7 hosts), one chronic host; bundling halves the incomplete node·slots (64
  against 126 on rtt4) but does not restore the pass. So on every build tested, and with bundles on rtt6, the pass
  depends on the extra 1 Gbit hosts. 400k fails the strict rule in slot 19 only: one message reached nobody because
  gossipsub refused its publish (`NoPeersSubscribedToTopic`). Its publisher had joined 0.2 s earlier and most likely
  had connections, but none of them had announced the topic yet. By the publisher-state churn rule that is a
  peer-management failure, not churn, so it counts against the network.[^v400]
- **Packet loss causes the misses, and the lossy model is the better-calibrated one.** With loss off
  (`R6-pq-noloss-ps100-cf-s1`, diagnostic), the same 6-slot key cell has no incomplete node·slot from slot 2 on, and
  BLS attestations miss 2 of 1.16M deliveries. Failed sends fall from 6–10M to ~1.2M per slot, negative-score peers
  fall about 4×, and meshes fill (228 → 257 links per node). Shadow's TCP recovers losses with SACK, as Linux does,
  but in the current build its retransmission timeout never adapts and ratchets up over a run (see
  [Caveats](#caveats)). A corrected build (rtt4) is queued to measure how much of the shortfall that causes. The
  matched no-PQ pair (`R6-nopq-ps100-cf-s1` with loss, `R6-nopq-noloss-ps100-cf-s1` without; same blocks) matches
  mainnet equally where mainnet has numbers: attestations after 4 s p50 / p95 0.94 / 1.93 s and 0.93 / 1.91 s (mainnet
  mean 0.83, P95 1.96), and identical column timing. The lossy model is closer on duplicates (attestation 2.21 vs
  2.95, mainnet median 2; block 3.84 vs 4.17, median 3) and home rx (137 vs 122 kB/s, mainnet 163), so the lossy runs
  stay the calibrated ones. Loss lengthens only the far tail (attestation p99 2.76 vs 2.30 s, 0.33 vs 0.01 % of
  deliveries missing), which mainnet data does not cover. On the same four blocks, loss off does not lower the block
  first-seen p99 (2.85 → 2.88 s), so the block-tail test is inconclusive (see the calibration table).

PQ vs BLS miss rates (% missing at 8 s; 50/15 / 50/25 / 1 Gbit), 2,048 × 20:

| run | slots | node·slots complete | PQ messages missing | BLS attestations missing, same run |
|---|---|---|---|---|
| `R20-pq-2k4-ps100-cf2-s1` (cf2, 2.4 kB) | 2–15 | 100 / 100 / 99.66 | 0 / 0 / 0.010 | 0.070 / 0.061 / 2.42 |
| `R20-pq-2k4-ps100-cf2-s1` (cf2, 2.4 kB) | 16–19 | 100 / 100 / 99.53 | 0 / 0 / 0.021 | 0.068 / 0.022 / 2.66 |
| `R20-pq-2k4-rtt4-ps100-cf2-s1` (cf2, 2.4 kB, rtt4 build) | 2–15 | 100 / 100 / 99.87 | 0 / 0 / 0.0014 | 0.23 / 0.25 / 1.48 |
| `R20-pq-2k4-rtt4-ps100-cf2-s1` (cf2, 2.4 kB, rtt4 build) | 16–19 | 100 / 100 / 99.46 | 0 / 0 / 0.020 | 0.008 / 0.074 / 1.35 |
| `R20-pq-2k4-rtt5-ps100-cf2-s1` (cf2, 2.4 kB, rtt5 sensitivity build) | 2–15 | 100 / 100 / 98.80 | 0 / 0 / 0.032 | 0.092 / 0.19 / 2.54 |
| `R20-pq-2k4-rtt5-ps100-cf2-s1` (cf2, 2.4 kB, rtt5 sensitivity build) | 16–19 | 100 / 100 / 98.65 | 0 / 0 / 0.051 | 0.10 / 0.20 / 2.57 |
| `R20-pq-b16-2k4-rtt5-ps100-cf2-s1` (cf2, 2.4 kB, b16, rtt5 sensitivity build) | 2–15 | 100 / 100 / 99.28 | 0 / 0 / 0.013 | 0.22 / 0.29 / 2.69 |
| `R20-pq-b16-2k4-rtt5-ps100-cf2-s1` (cf2, 2.4 kB, b16, rtt5 sensitivity build) | 16–19 | 100 / 100 / 98.75 | 0 / 0 / 0.025 | 0.064 / 0.13 / 3.10 |
| `R20-pq-b16-2k4-rtt5b-ps100-cf2-s1` (cf2, 2.4 kB, b16, rtt5 with CUBIC's decrease; no matched no-PQ run) | 2–15 | 100 / 100 / 99.74 | 0 / 0 / 0.0031 | 0.15 / 0.12 / 2.14 |
| `R20-pq-b16-2k4-rtt5b-ps100-cf2-s1` (cf2, 2.4 kB, b16, rtt5 with CUBIC's decrease; no matched no-PQ run) | 16–19 | 100 / 100 / 99.53 | 0 / 0 / 0.0068 | 0.15 / 0.14 / 2.27 |
| `R20-pq-b16-2k4-rtt6-ps100-cf2-s1` (cf2, 2.4 kB, b16, rtt6; matched no-PQ run queued) | 2–15 | 100 / 100 / 99.94 | 0 / 0 / 0.0008 | 0.029 / 0.027 / 1.48 |
| `R20-pq-b16-2k4-rtt6-ps100-cf2-s1` (cf2, 2.4 kB, b16, rtt6; matched no-PQ run queued) | 16–19 | 100 / 100 / 99.83 | 0 / 0 / 0.0033 | 0.12 / 0.035 / 1.79 |
| `R20-pq-b16-2k4-2sub-rtt6-ps100-cf2-s1` (cf2, 2.4 kB, b16, rtt6, home stakers in 2 subnets; matched no-PQ run queued) | 2–15 | 100 / 100 / 99.87 | 0 / 0 / 0.0005 | 0.11 / 0.061 / 1.79 |
| `R20-pq-b16-2k4-2sub-rtt6-ps100-cf2-s1` (cf2, 2.4 kB, b16, rtt6, home stakers in 2 subnets; matched no-PQ run queued) | 16–19 | 100 / 100 / 99.93 | 0 / 0 / 0.0004 | 0.009 / 0.048 / 1.47 |
| `R20-pq-b16-2k4-bb2-rtt6-ps100-cf2-s1` (cf2, 2.4 kB, b16, rtt6, home nodes in 2 backbone subnets plus stakers' duty subnet; matched no-PQ run queued) | 2–15 | 99.91 / 99.99 / 99.89 | 0.0016 / 0.0002 / 0.0007 | 0.11 / 0.15 / 1.23 |
| `R20-pq-b16-2k4-bb2-rtt6-ps100-cf2-s1` (cf2, 2.4 kB, b16, rtt6, home nodes in 2 backbone subnets plus stakers' duty subnet; matched no-PQ run queued) | 16–19 | 100 / 99.97 / 99.93 | 0 / 0.0008 / 0.0012 | 0.17 / 0.079 / 1.42 |
| `R20-pq-2k4-cwv-ps100-cf2-s1` (cf2, 2.4 kB, rtt5 binary with window validation only; no matched no-PQ run) | 2–15 | 100 / 100 / 99.75 | 0 / 0 / 0.0032 | 0.14 / 0.16 / 2.01 |
| `R20-pq-2k4-cwv-ps100-cf2-s1` (cf2, 2.4 kB, rtt5 binary with window validation only; no matched no-PQ run) | 16–19 | 100 / 100 / 99.26 | 0 / 0 / 0.020 | 0.030 / 0.10 / 2.48 |
| `R20-pq-2k4-rtt6-ps100-cf2-s1` (cf2, 2.4 kB, rtt6; matched no-PQ run queued) | 2–15 | 100 / 100 / 99.77 | 0 / 0 / 0.0060 | 0.032 / 0.034 / 1.81 |
| `R20-pq-2k4-rtt6-ps100-cf2-s1` (cf2, 2.4 kB, rtt6; matched no-PQ run queued) | 16–19 | 100 / 100 / 99.46 | 0 / 0 / 0.029 | 0.015 / 0.035 / 2.13 |
| `R20-pq-b16-2k4-ps100-cf2-s1` (cf2, 2.4 kB, b16) | 2–15 | 100 / 100 / 99.87 | 0 / 0 / 0.0024 | 0.068 / 0.026 / 1.56 |
| `R20-pq-b16-2k4-ps100-cf2-s1` (cf2, 2.4 kB, b16) | 16–19 | 100 / 100 / 99.73 | 0 / 0 / 0.0028 | 0.18 / 0.030 / 1.75 |
| `R20-pq-b16-2k4-ps100-cf2-s2` (cf2, 2.4 kB, b16, seed 2) | 2–15 | 100 / 100 / 99.94 | 0 / 0 / 0.0006 | 0.013 / 0.020 / 0.98 |
| `R20-pq-b16-2k4-ps100-cf2-s2` (cf2, 2.4 kB, b16, seed 2) | 16–19 | 100 / 100 / 99.90 | 0 / 0 / 0.0005 | 0.025 / 0.021 / 1.53 |
| `R20-pq-2k4-ps100-cf2-s2` (cf2, 2.4 kB, seed 2) | 2–15 | 100 / 100 / 99.96 | 0 / 0 / 0.0001 | 0.019 / 0.042 / 2.17 |
| `R20-pq-2k4-ps100-cf2-s2` (cf2, 2.4 kB, seed 2) | 16–19 | 100 / 100 / 99.90 | 0 / 0 / 0.0018 | 0.030 / 0.038 / 2.13 |
| `R20-pq-v600-2k4-ps100-cf2-s1` (cf2, 2.4 kB, 600k) | 2–15 | 100 / 100 / 99.89 | 0 / 0 / 0.0030 | 0.016 / 0.022 / 0.91 |
| `R20-pq-v600-2k4-ps100-cf2-s1` (cf2, 2.4 kB, 600k) | 16–19 | 100 / 100 / 99.78 | 0 / 0 / 0.0024 | 0.004 / 0.028 / 1.31 |
| `R20-pq-v400-2k4-ps100-cf2-s1` (cf2, 2.4 kB, 400k) | 2–15 | 100 / 100 / 99.88 | 0 / 0 / 0.0039 | 0.007 / 0.017 / 1.05 |
| `R20-pq-v400-2k4-ps100-cf2-s1` (cf2, 2.4 kB, 400k; slot-19 churn message excluded) | 16–19 | 100 / 100 / 99.88 | 0 / 0 / 0.0030 | 0.012 / 0.015 / 1.14 |
| `R20-pq-fs0-2k4-ps100-cf2-s1` (cf2, 2.4 kB, no extra 1 Gbit hosts; no matched no-PQ run) | 2–15 | 100 / 100 / 98.36 | 0 / 0 / 0.093 | 0.145 / 0.109 / 2.36 |
| `R20-pq-fs0-2k4-ps100-cf2-s1` (cf2, 2.4 kB, no extra 1 Gbit hosts; no matched no-PQ run) | 16–19 | 100 / 100 / 97.15 | 0 / 0 / 0.164 | 0.133 / 0.093 / 2.68 |
| `R20-pq-fs0-2k4-rtt4-ps100-cf2-s1` (cf2, 2.4 kB, no extra 1 Gbit hosts, rtt4 build; no matched no-PQ run) | 2–15 | 99.98 / 100 / 98.39 | 0.0007 / 0 / 0.049 | 0.075 / 0.045 / 2.59 |
| `R20-pq-fs0-2k4-rtt4-ps100-cf2-s1` (cf2, 2.4 kB, no extra 1 Gbit hosts, rtt4 build; no matched no-PQ run) | 16–19 | 100 / 99.98 / 98.00 | 0 / 0.0002 / 0.084 | 0.113 / 0.090 / 2.94 |
| `R20-pq-fs0-b16-2k4-rtt6-ps100-cf2-s1` (cf2, 2.4 kB, b16, no extra 1 Gbit hosts, rtt6; no matched no-PQ run) | 2–15 | 100 / 100 / 99.21 | 0 / 0 / 0.0206 | 0.060 / 0.026 / 1.97 |
| `R20-pq-fs0-b16-2k4-rtt6-ps100-cf2-s1` (cf2, 2.4 kB, b16, no extra 1 Gbit hosts, rtt6; no matched no-PQ run) | 16–19 | 100 / 99.98 / 98.91 | 0 / 0.0009 / 0.0185 | 0.036 / 0.028 / 2.50 |
| `L-pq-2k4-ps100-cf2-s1` (cf2, 2.4 kB, 1,024 × 50) | 2–15 | 100 / 100 / 99.84 | 0 / 0 / 0.0039 | 0.10 / 0.027 / 1.21 |
| `L-pq-2k4-ps100-cf2-s1` (cf2, 2.4 kB, 1,024 × 50) | 16–49 | 99.98 / 100 / 99.64 | 0.0001 / 0 / 0.0237 | 0.038 / 0.023 / 1.49 |
| `L-pq-b16-2k4-ps100-cf2-s1` (cf2, 2.4 kB, b16, 1,024 × 50) | 2–15 | 100 / 100 / 99.96 | 0 / 0 / 0.0014 | 0.074 / 0.032 / 0.79 |
| `L-pq-b16-2k4-ps100-cf2-s1` (cf2, 2.4 kB, b16, 1,024 × 50) | 16–49 | 100 / 100 / 99.98 | 0 / 0 / 0.0003 | 0.085 / 0.019 / 1.24 |
| `L-pq-b16-2k4-rtt6-ps100-cf2-s1` (cf2, 2.4 kB, b16, rtt6, 1,024 × 50; no matched no-PQ run) | 2–15 | 100 / 100 / 99.80 | 0 / 0 / 0.0017 | 0.052 / 0.016 / 1.48 |
| `L-pq-b16-2k4-rtt6-ps100-cf2-s1` (cf2, 2.4 kB, b16, rtt6, 1,024 × 50; no matched no-PQ run) | 16–49 | 100 / 100 / 99.84 | 0 / 0 / 0.0027 | 0.037 / 0.027 / 1.88 |
| `L-pq-b16-2k4-rtt6-ps100-cf2-s2` (cf2, 2.4 kB, b16, rtt6, 1,024 × 50, seed 2; no matched no-PQ run) | 2–15 | 100 / 100 / 100 | 0 / 0 / 0 | 0.012 / 0.026 / 1.65 |
| `L-pq-b16-2k4-rtt6-ps100-cf2-s2` (cf2, 2.4 kB, b16, rtt6, 1,024 × 50, seed 2; no matched no-PQ run) | 16–49 | 100 / 100 / 99.94 | 0 / 0 / 0.0006 | 0.025 / 0.024 / 1.72 |
| `R20-pq-ps100-cf2-s1` (cf2, 3 kB) | 2–15 | 100 / 100 / 99.46 | 0 / 0 / 0.015 | 0.043 / 0.044 / 1.51 |
| `R20-pq-ps100-cf2-s1` (cf2, 3 kB) | 16–19 | 100 / 100 / 98.82 | 0 / 0 / 0.039 | 0.16 / 0.13 / 1.85 |
| `R20-pq-ps100-cf-s1` (cf, 3 kB) | 2–15 | 99.91 / 99.99 / 98.90 | 0.0026 / 0.0006 / 0.054 | 0.77 / 0.76 / 3.51 |
| `R20-pq-ps100-cf-s1` (cf, 3 kB) | 16–19 | 99.85 / 99.97 / 97.74 | 0.0048 / 0.0002 / 0.149 | 0.34 / 0.23 / 3.29 |
| no-PQ `R-nopq-ps100-s1` (old binary, every client −10) | 2–15 | – | – | 0.098 / 0.089 / 1.49 |
| no-PQ `R-nopq-ps100-s1` | 16–19 | – | – | 0.023 / 0.024 / 1.55 |
| no-PQ `R20-nopq-ps100-cf2-s1` (cf2, matched to seed 1) | 2–15 | – | – | 0.030 / 0.018 / 1.02 |
| no-PQ `R20-nopq-ps100-cf2-s1` (cf2, matched to seed 1) | 16–19 | – | – | 0.024 / 0.015 / 1.03 |
| no-PQ `R20-nopq-rtt4-ps100-cf2-s1` (cf2, rtt4 build, matched to the rtt4 seed-1 run) | 2–15 | – | – | 0.025 / 0.022 / 0.91 |
| no-PQ `R20-nopq-rtt4-ps100-cf2-s1` (cf2, rtt4 build, matched to the rtt4 seed-1 run) | 16–19 | – | – | 0.094 / 0.105 / 1.37 |
| no-PQ `R20-nopq-rtt5-ps100-cf2-s1` (cf2, rtt5 sensitivity build, matched to the rtt5 seed-1 run) | 2–15 | – | – | 0.045 / 0.052 / 1.53 |
| no-PQ `R20-nopq-rtt5-ps100-cf2-s1` (cf2, rtt5 sensitivity build, matched to the rtt5 seed-1 run) | 16–19 | – | – | 0.058 / 0.034 / 1.67 |

The 1 Gbit attestation figures are dominated by the hosts that subscribe to all 64 attestation subnets (cf2:
2.63–2.92 % at 2.4 kB, 1.64–2.01 % at 3 kB).

The fs0 rows have no matched no-PQ run: `R20-nopq-ps100-cf2-s1` keeps the default link mix with the extra 1 Gbit
hosts, so it is not fs0's baseline. fs0's PQ and BLS misses compare only within its own run; the difference between its
attestation misses and the no-PQ rows is not attributed to PQ.

## Setup

- **Hosts.** 2,048 Shadow hosts from a mainnet validator sample (`data/f9ba162f-nodes.csv`; 126,255 validators on
  1,639 hosts). The 742 "1 Gbit" (cloud) hosts are those with more than 8 validators plus 20 % of the rest. The others
  are home stakers: 976 at 50/25 Mbit/s (with validators) and 330 at 50/15 Mbit/s (without). These are EIP-7870's
  attester and full-node profiles.
- **PQ load.** 2,000 messages per slot of 2,458 B (2.4 kB, headline) or 3,072 B (3 kB) on 16 PQ subnets, each
  published by its signer 4.0–4.5 s into the slot (4 s + U[0, 0.5 s)), deadline 8 s (4 s after publishing starts). Home stakers join one subnet (except in the two subnet cells, see [Pending](#pending)); 1 Gbit hosts join all 16.
  2,000 is the load the study was asked to test (`--msgs 2000`); it is not derived from 800k validators, and the
  600k and 400k cells scale it linearly. Each slot draws its 2,000 signers at random, with replacement, in
  proportion to each host's validator count in the sample (126,255 validators, so each signs with probability of
  about 1.6 % per slot; home stakers publish 43–66 of the 2,000). Each host not on 1 Gbit gets one of the 16 subnets
  uniformly at random for the whole run, and all its signatures go there; a 1 Gbit host sends each signature to a
  random subnet. With `--batch 16`, a publisher's signatures for one subnet travel in messages of up to 16.
- **Background.** Blocks, data columns, 64 attestation subnets, aggregates and sync committee messages at mainnet rates.
- **Realism layer** (calibrated in `results/realism-calibration.md`):
  - city-level RTTs, access technologies, jitter, and loss;
  - signature verification time, with 20 % slow CPUs;
  - Lighthouse peer scoring;
  - Probelab client mix with per-client gossipsub parameters and peer targets;
  - 30 % of home hosts behind NAT;
  - churn: 30 min connection life, 0.143 restarts per day, 0.5 % leaves and 0.5 % joins.
- **Gossipsub.** rust-libp2p 0.49.5 with Ethereum parameters (per client: Lighthouse D 5/3/10 with a 1 s heartbeat;
  others D 8/6/12 with 0.7 s). IDONTWANT above 1,000 B, content-hash message ids, a 1 s forward-queue and a 5 s
  publish-queue timeout.
- **Peer targets.** ×1.0 (real) uses Lighthouse, Lodestar and other 200, Nimbus 160, Teku 100, Prysm 70. ×0.25
  (scaled) uses 50 / 50 / 50 / 40 / 25 / 18.
- **Late first deliveries** (the backlog test): needed PQ messages of the slot, a host's own left out, that an online
  host first receives after the 8 s deadline and by 16 s, from the receive records (`late.py`). An earlier `late.py`
  read gossipsub's receive counter instead. That counter also counts copies more than 60 s old: gossipsub keeps
  message ids for 60 s, so it takes such a copy for a new message, and the client then ignores it as stale. The old
  window also began at 7.5 s when the 8 s sample was logged late. It gave 0–3 per 1 Gbit host per slot over 20 slots
  and 3–6 in slots 36–48 of `L-pq-2k4-ps100-cf2-s1`. In the 15 runs that log per-slot misses, the corrected count
  never exceeds the messages missing at 8 s in any slot. This report gives only corrected values. Copies of messages
  already held are counted separately, as a cost.

### Binaries and scoring labels

| label | binary | what it is |
|---|---|---|
| old | `bin/old` | runs before 14:36 Nov 7; eager gossipsub queues (0.55 MiB per connection) |
| fx | `bin/fixed` | lazy gossipsub queue: same behaviour, half the memory; every client −10 slow-peer weight |
| age60 | `bin/stale` | fixed + `--max-msg-age 60` (ignore flood messages received > 60 s after publishing) |
| cf | `bin/cf` | stale + client-faithful slow-peer penalty: −10 on Lighthouse and `other` hosts (rust-libp2p), 0 on Prysm, Teku, Nimbus and Lodestar |
| cf2 | `bin/cf2` | cf + client-faithful mesh-delivery (P3/P3b) and IWANT-promise scoring and IHAVE re-requests ([below](#client-faithful-scoring)) |

Shadow builds: every run so far uses `current` (Shadow 3.3.0 with `sim/shadow-3.3-fixes.patch`). Runs named `-rtt4-`
use the corrected TCP build described under Loss and TCP in [Caveats](#caveats).

## Calibration (no PQ, 2,048 hosts × 20 slots, slots ≥ 2)

| metric | mainnet | real ×1.0 (`R-nopq-ps100-s1`, old) | scaled ×0.25 (`R-nopq-s1`, old) | `R6-nopq-ps100-cf-s1` (cf, 6 slots) | `R6-nopq-noloss-ps100-cf-s1` (cf, 6 slots, loss off) | `R20-nopq-ps100-cf2-s1` (cf2, 20 slots) | `R20-nopq-rtt4-ps100-cf2-s1` (cf2, 20 slots, rtt4 build) | `R20-nopq-rtt5-ps100-cf2-s1` (cf2, 20 slots, rtt5 sensitivity build) |
|---|---|---|---|---|---|---|---|---|
| block first-seen p50 / p90 / p99 (s) | 2.06 / 3.51 / 4.52 | 1.84 / 2.88 / 4.48 | 1.82 / 2.88 / 4.47 | same 4 blocks: 1.45 / 2.73 / 2.85 | same 4 blocks: 1.40 / 2.79 / 2.88 | 1.80 / 2.85 / 4.46 | 1.81 / 2.86 / 4.46 | 2.08 / 3.05 / 4.83 |
| block from publish p50 / p95 / p99 (s) | relay-timed P95 0.82; start offset to the first publish unknown (see rtt5 below) | – | – | 0.25 / 0.39 / 0.47 | 0.23 / 0.33 / 0.38 | 0.20 / 0.34 / 0.44 | 0.21 / 0.38 / 0.47 | 0.47 / 0.90 / 1.09 |
| attestation after 4 s p50 / p95 / p99 (s) | mean 0.83 / P95 1.96 | 0.94 / 1.93 / 2.94 | 0.95 / 2.21 / 4.06 | 0.94 / 1.93 / 2.76 | 0.93 / 1.91 / 2.30 | 0.94 / 1.94 / 3.26 | 0.94 / 1.94 / 3.31 | 0.97 / 2.08 / 3.78 |
| attestation deliveries missing | – | – | – | 0.33 % | 0.01 % | 0.35 % | 0.33 % | 0.43 % |
| duplicates per attestation | median 2 | 2.17 | 1.11 | 2.21 | 2.95 | 2.45 | 2.35 | 2.46 |
| duplicates per block | median 3 | 3.74 | 3.34 | 3.84 | 4.17 | 3.74 | 3.73 | 3.87 |
| column first-seen p50 / p95 (s) | 1.78 / 3.2 (Xatu, unofficial) | – | – | 1.43 / 2.71 | 1.43 / 2.71 | 1.86 / 4.41 | 1.86 / 4.42 | 1.94 / 4.38 |
| home 50/25 block + attestation + column rx | 163 kB/s | – | – | 137 kB/s | 122 kB/s | 143 kB/s | 143 kB/s | 151 kB/s |
| attestation misses, 2-subnet / all-64 hosts | – | 0.04 % / 1.36 % | 0.52 % / 4.86 % | – / 0.64 % | 0.00 % / 0.01 % | 0.02 % / 1.13 % | 0.04 % / 1.11 % | 0.03 % / 1.72 % |
| mesh links, slot 0 → 19 | – | 377k → 380k (flat) | 358k → 260k (−27 %) | 184 → 188 per node (flat) | 182 → 208 per node (rising) | 185 → 197 per node (flat) | 183 → 194 per node (flat) | 184 → 192 per node (flat) |
| peers with negative score | – | ~20k of ~338k (6 %) | ~16k of ~85k (19 %) | 58 → 10.8k | 3 → 2.1k | 51 → ~9.3k | 43 → ~10.0k | 150 → ~12.1k (peak 15.7k, slot 5) |
| home rx / tx p50 (50/25) | – | 5.13 / 4.96 Mbit/s | 3.22 / 2.90 Mbit/s | 5.03 / 4.92 Mbit/s | 5.03 / 4.99 Mbit/s | 5.14 / 4.94 Mbit/s | 5.15 / 4.96 Mbit/s | 5.28 / 4.97 Mbit/s |

**rtt4 build (no PQ).** `R20-nopq-rtt4-ps100-cf2-s1` (same seed and network, rtt4 build) stays within noise of the
current build on every calibration metric, including block propagation from publish (p95 / p99 0.38 / 0.47 s against
0.34 / 0.44 s). Home BLS misses at 8 s are the same in slots 2–15 (50/15 0.025 %, 50/25 0.022 %, against 0.030 % and
0.018 %). So the higher home misses of `R20-pq-2k4-rtt4-ps100-cf2-s1` in those slots (0.23 % and 0.25 %, against
0.070 % and 0.061 % on the current build) do not come from the build alone: the PQ load adds about 0.2 percentage
points on rtt4 and 0.04 on the current build. In slots 16–19, 237 (receiver, attestation) pairs on 2-subnet hosts
never arrive (0.073 % of 50/15 and 0.080 % of 50/25 deliveries; none on the current build); the cause is not
established. First timeouts climb as in the PQ run (home→home 8.3 per 1,000 data packets in slot 2, 18–21 from slot
10 on), so the climb does not need PQ traffic.

**rtt5 sensitivity build (no PQ).** `R20-nopq-rtt5-ps100-cf2-s1` (same seed and network; rtt5 with all three switches
on, tcpd logging) is the matched run of `R20-pq-2k4-rtt5-ps100-cf2-s1`. Attestations, columns, duplicates and home
traffic stay close to rtt4 and the current build (table above). Blocks are slower: from publish, p50 / p95 / p99 is
0.47 / 0.90 / 1.09 s, against 0.21 / 0.38 / 0.47 s on rtt4 and 0.20 / 0.34 / 0.44 s on the current build. From slot
start, p90 / p99 is 3.05 / 4.83 s, against 2.86 / 4.46 s on rtt4 (mainnet 3.51 / 4.52 s). Block p95 from publish stays
at 2.3–2.4× rtt4's in each six-slot block (2.31×, 2.44× and 2.36× in slots 2–7, 8–13 and 14–19; rtt5 means 0.87,
0.80 and 0.78 s). Over the same slots the median restart's ssthresh falls, mostly by slot 10, from unreduced to 21–24
segments on paths between 1 Gbit and home hosts and to 11 on home→home paths. So, as in the PQ run, the block
slowdown does not grow as ssthresh falls. Windows before a restart are 10 segments at p50 and 21–36 at p90, so most
bursts end before slow start reaches even the lowered ssthresh. Per slot (slots 2–19; ssthresh slots 2–18, u = more
than half of the restarts on connections that never reduced it):

| series | per slot |
|---|---|
| block first-seen from publish p95, rtt4 (s) | 0.35 0.29 0.47 0.43 0.44 0.28 0.31 0.33 0.30 0.37 0.39 0.27 0.31 0.29 0.37 0.35 0.29 0.37 |
| block first-seen from publish p95, rtt5 (s) | 0.79 0.77 0.85 0.84 1.18 0.79 0.77 0.81 0.80 0.89 0.95 0.59 0.67 0.72 0.90 0.84 0.72 0.83 |
| ssthresh p50 after a restart, 1G→1G | u u u u u u u u u u u u u u u u u |
| ssthresh p50 after a restart, 1G→home | u u u 98 45 34 31 27 25 24 24 24 22 22 21 21 21 |
| ssthresh p50 after a restart, home→1G | u u u u u 121 61 36 33 30 28 28 27 25 25 25 24 |
| ssthresh p50 after a restart, home→home | u u u u 31 21 18 16 14 13 13 12 12 12 11 11 11 |

Home BLS attestations missing at 8 s, 50/15 / 50/25: 0.045 / 0.052 % in slots 2–15 (rtt4 0.025 / 0.022 %, current
build 0.030 / 0.018 %) and 0.058 / 0.034 % in slots 16–19 (rtt4 0.094 / 0.105 %, current 0.024 / 0.015 %). No home
delivery is lost for good in either range, so rtt4's 237 never-arriving 2-subnet pairs in slots 16–19 do not recur.
1 Gbit hosts miss 1.53 / 1.67 % (rtt4 0.91 / 1.37 %), almost all on the hosts subscribed to all 64 subnets (1.68 /
1.84 %). Against this matched run, PQ adds 0.05 / 0.13 / 1.0 percentage points to the BLS misses in slots 2–15 of
`R20-pq-2k4-rtt5-ps100-cf2-s1` (50/15 / 50/25 / 1 Gbit; rtt4 0.2 / 0.2 / 0.6, current build 0.04 / 0.04 / 1.4).

TCP, by path type (1G→1G / 1G→home / home→1G / home→home): resends 0.32 / 3.42 / 1.64 / 9.34 per 1,000 data packets
(rtt4 0.33 / 4.18 / 1.69 / 10.74); restarts after idle about 205k / 365k / 368k / 426k per slot; cwnd p50 / p90 over
the run 10 / 18, 10 / 16, 10 / 16 and 10 / 16 (rtt4 329 / 2,542, 115 / 588, 134 / 597 and 45 / 294); fast-recovery
entries 0.30 / 1.44 / 1.38 / 2.26 per 1,000 data packets, all after consecutive duplicate ACKs. 95.8 % of 3.11M Eifel
checks found the timeout spurious and undid it. No snapshot stalls (6.83M), and the RTO formula holds in all
6,361,287 snapshots without backoff. First timeouts per 1,000 data packets climb as on rtt4, at 75–90 % of its
level (run means: home→home 89 %, 1G→home and home→1G 77 %): home→home from 7.4 in slot 2 to 18.1 in slot 18 (rtt4 8.3 → 19.9), 1G→home 2.6 → 5.2 (3.5 → 6.9), home→1G
0.41 → 0.90 (0.50 → 1.19), while 1G→1G stays flat at 0.05 (0.07). So the climb also appears with windows held near
10 segments; it does not need growing windows. Peak 188.7 GiB PSS; wall 9,078 s.

**Mainnet's block figure.** The relay P95 of 0.82 s comes from ethresear.ch post 23016 (M. Silva, September 2025;
slots 12,243,599–12,293,998, 29 July to 5 August 2025). It covers the 52 % of slots whose payload came from the
Ultrasound, Flashbots or Titan relays. For each of those slots it measures the time from the relay's reply to the
proposer's `/eth/v1/builder/blinded_blocks` request (the payload release, from the relays' own data) until each
observer's beacon node emits the Beacon API `block_gossip` event, that is, until the block has arrived over gossip
and passed gossip validation (Xatu table `beacon_api_eth_v1_events_block_gossip`). The observers are 29 ethPandaOps
nodes and 109 community nodes across clients and countries. P95 over node·slot pairs is 816 ms for the ethPandaOps
nodes and 804 ms for the community nodes. The post does not say how the relays' timestamp relates to the first
gossip publish, where the sim's "from publish" starts. Relays also publish the block through their own beacon nodes:
in Flashbots' relay code (`mev-boost-relay` main, `services/api/service.go`), the v1 handler publishes first and
replies only after the publish call returns and a configurable delay (`GETPAYLOAD_RESPONSE_DELAY_MS`, default
1,000 ms). The post's times are positive, so its timestamps cannot include a full second of that delay, but the start
can precede or follow the first publish. So 0.82 s is only roughly a gossip-only P95, sampled at about 138 observers
rather than every node. Read that way, the current build (0.34 s) and rtt4 (0.38 s) reach 41 % and 46 % of it, and
rtt5 (0.90 s) is 10 % above it. Two differences lengthen mainnet's tail regardless of TCP: mainnet (~10k nodes) is
about one gossip hop deeper than 2,048 hosts, and the calibration (`realism-calibration.md`) attributes the rest of
the current build's gap to client-side block handling, which the sim models as 10 ms. So this figure alone does not
say which build is closer to Linux.

**Loss on or off (same seed, same blocks).** Both models match mainnet where it has numbers: attestation p50 and p95
are the same with and without loss, and column timing is identical (both faster than the unofficial Xatu figures).
The lossy model is closer on attestation and block duplicates and on home rx, as in the PQ pair (attestation
duplicates 1.9–2.2 with loss, 3.4 without). Part of the duplicate gap comes from mesh size: without loss fewer peers
score negative and attestation meshes stay fuller (Lighthouse 6.0 vs 5.1, 1 Gbit 6.4 vs 5.1). Loss lengthens only the
far tail (attestation p99, missing deliveries), which mainnet data does not cover. The block-tail test is
inconclusive: the four blocks of slots 2–5 are published 0.90–2.52 s into the slot, the 20-slot run's 4.48 s p99
(mainnet 4.52 s) comes from late-published blocks, and loss off trims only 0.01–0.11 s from each block's p99 (pooled
2.85 → 2.88 s). So the lossy runs remain the calibrated ones, and the 3 kB 1 Gbit shortfall stands.

**Calibration recheck on cf2 (`R20-nopq-ps100-cf2-s1`: 2,048 × 20, no PQ, seed 1).** It matches the earlier
real-peer-count run and mainnet where mainnet has numbers: block first-seen p50 / p90 / p99 1.80 / 2.85 / 4.46 s
(mainnet 2.06 / 3.51 / 4.52), attestations after 4 s p50 / p95 0.94 / 1.94 s (mainnet mean 0.83, P95 1.96),
duplicates per attestation 2.45 and per block 3.74 (mainnet medians 2 and 3), and home 50/25 rx 143 kB/s (163).
Columns are slower at p95 (4.41 s against Xatu's 3.2 s) because, over 20 slots, late-published blocks delay their
columns too. Links per node stay flat (185 → 197), and about 9.3k peers score negative (the old binary, with every
client at −10, had ~20k). This run is also the matched BLS baseline of the 2.4 kB headline run: attestations miss
0.030 / 0.018 / 1.02 % (slots 2–15) and 0.024 / 0.015 / 1.03 % (16–19) on 50/15 / 50/25 / 1 Gbit hosts, against
0.070 / 0.061 / 2.42 % and 0.068 / 0.022 / 2.66 % with PQ. Peak 182.0 GiB PSS; wall 8,536 s.

Real peer counts close two of the three gaps:

- **Attestation duplicates** match mainnet at ×1.0 (2.17 vs 2), not at ×0.25 (1.11).
- **All-64-subnet misses** drop from 4.9 % to 1.4 %.
- **Meshes** stay flat at ×1.0 instead of losing 27 % of their links.
- **Block p90** stays at 2.88 s against mainnet's 3.51 s at either scale. Peer counts don't cause this gap; the
  sim's blocks propagate faster than mainnet's.

Every PQ cell below runs at ×1.0. The ×0.25 runs serve only as comparison points.

## Results

### 2,048 hosts × 6 slots (slots 2–5)

Completion is in % of node·slots. PQ and BLS miss rates are in % at 8 s; 50/15 / 50/25 / 1 Gbit in every column.

| run | binary, scoring | 50/15 | 50/25 | 1 Gbit (worst slot) | strict | PQ missing | BLS missing, same run | chronic 1 Gbit hosts | κ | latency p99 (s) | peak PSS GiB | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R6-pq-ps100-fx-s1 (key cell: 800k × 3 kB) | fx, every client −10 | 99.92 | 100 | 98.65 (98.51) | FAIL | 0.033 / 0 / 0.110 | 0.136 / 0.098 / 1.76 | 12: Prysm 9, Teku 3 | 8.2–8.6 | 0.72 / 0.51 / 0.62 | 160.1 | 3,346 |
| R6-pq-ps100-fx-s2 (seed 2) | fx | 99.92 | 100 | 98.92 (98.75) | FAIL | 0.0006 / 0 / 0.061 | 0.27 / 0.19 / 2.85 | 7 Prysm | 8.1–8.9 | 0.82 / 0.62 / 0.68 | 154.0 | 3,251 |
| R6-pq-b16-ps100-fx-s1 (16 sigs per message) | fx | 100 | 99.97 | 99.22 (99.05) | PASS | 0 / 0.0015 / 0.028 | 0.28 / 0.33 / 1.90 | – | 7.9–8.3 | 0.54 / 0.39 / 0.50 | 158.7 | 3,132 |
| R6-pq-fs0-ps100-fx-s1 (no extra 1 Gbit hosts) | fx | 99.88 | 99.94 | 97.22 (95.87) | FAIL | 0.008 / 0.009 / 0.148 | 0.024 / 0.043 / 2.10 | 12: Prysm 7, Teku 3, Lighthouse 2 | 10.0–10.9 | 0.93 / 0.65 / 1.10 | 148.9 | 3,003 |
| R6-pq-v600-ps100-fx-s1 (600k: 1,500 msgs) | fx | 100 | 100 | 99.64 (99.28) | PASS | 0 / 0 / 0.011 | 0.029 / 0.031 / 1.10 | 3: Prysm 2, Teku 1 | 10.0–10.6 | 0.49 / 0.39 / 0.50 | 152.5 | 3,161 |
| R6-pq-v400-ps100-fx-s1 (400k: 1,000 msgs) | fx | 100 | 100 | 100 (100) | PASS | 0 / 0 / 0 | 0.018 / 0.009 / 0.65 | 0 | 13.5–14.5 | 0.30 / 0.29 / 0.40 | 139.0 | 2,777 |
| R6-pq-s1k-ps100-fx-s1 (1,229 B sigs) | fx | 100 | 100 | 99.86 (99.59) | PASS | 0 / 0 / 0.004 | 0.072 / 0.079 / 1.75 | 0 | 15.0–15.7 | 0.34–0.47 | 152.2 | 3,366 |
| R6-pq-fs0-ps100-cf-s1 | cf | 99.94 | 99.94 | 97.64 (97.09) | FAIL | 0.0005 / 0.012 / 0.078 | 0.19 / 0.15 / 2.13 | 11: Prysm 8, Teku 2, Lighthouse 1 | 10.4–11.1 | 0.68–0.92 | 149.7 | 3,130 |
| R6-pq-b16-ps100-cf-s1 | cf | 100 | 100 | 99.73 (99.59) | PASS | 0 / 0 / 0.016 | 0.083 / 0.014 / 1.35 | 2 Prysm | 7.8–8.4 | 0.41–0.55 | 159.5 | 3,166 |
| R6-pq-noloss-ps100-cf-s1 (loss off, diagnostic) | cf | 100 | 100 | 100 (100) | PASS | 0 / 0 / 0 | 0.000 / 0.000 / 0.000 | 0 | 9.2–10.4 | 0.45 / 0.35 / 0.42 | 163.0 | 3,558 |
| R6-nopq-ps100-cf-s1 (BLS baseline; default link mix, so not the fs0 rows' baseline) | cf | – | – | – | – | – | 0.000 / 0.030 / 0.58 | – | – | – | 131.2 | 2,508 |

- **Load.** Upload in the 4 s window reaches 40–46 % of the cap on 50/15 hosts (max node 60–74 %), 28–31 % on 50/25
  (max 41–48 %) and 6–7 % on 1 Gbit hosts. Download stays ≤ 16 % (max ≤ 27 %).
- **Duplicates.** IDONTWANT messages carry 16–22k ids per node per slot (b16 and fs0: 10–13k), and each PQ message
  arrives 3.7–4.4 times.
- **No backlog in any 6-slot cell.** After-deadline PQ kB per node per slot are flat in the fx cells. They grow in the
  cf cells (fs0-cf 1 Gbit 295 → 1,027, b16-cf 185 → 934), as in R20-cf.
- **Incomplete node·slots** are almost all on 1 Gbit hosts, and almost all are messages never received. Key cell:
  never 34, whole subnet 1, near miss 3, late 2; 15 of 742 hosts account for 92.5 %.

### 2,048 hosts × 20 slots, 2.4 kB: `R20-pq-2k4-ps100-cf2-s1` (cf2, final model, headline)

×1.0, `--msg-bytes 2458`, seed 1. Completion per slot (%, slots 0–19):

| class | per slot |
|---|---|
| 50/15 | 100 in every slot |
| 50/25 | 100 in every slot |
| 1 Gbit | 99.73 99.86 99.73 100 99.86 99.86 99.86 99.59 99.73 99.46 99.86 99.73 99.73 99.05 99.46 99.32 99.32 99.73 99.59 99.46 |

- **Strict rule: PASS.** The worst slot is slot 13 (99.05 %, 7 of ~740 1 Gbit hosts incomplete, the most the rule
  allows). Slots 2–15 average 100 / 100 / 99.66 %, slots 16–19 100 / 100 / 99.53 %.
- **Incomplete node·slots** occur on 1 Gbit hosts only. Slots 2–15: 35 (near miss ≤ 1 s 18, late > 1 s 14, never
  received 2, whole subnet 1). Slots 16–19: 14 (near miss 7, late 5, whole subnet 2). No message was missed by more
  than half of its subscribers.
- **Chronic hosts.** Only 794 (Prysm, Singapore, 70 peers) is incomplete in ≥ 9 of 18 slots (15). Eight hosts are
  incomplete in ≥ 2 slots: six Prysm (794; 1972 Seoul; 852, 988 and 1873 São Paulo; 1355 Tokyo) and two Lighthouse
  (1860 São Paulo, 1430 Singapore). 794 misses with a full PQ mesh (degree 7.2–7.3, 91–92 % 1 Gbit peers); its
  forward timeouts rise from 14k to 25k per slot.
- **Latency** from publish, p50 / p99: 0.10 / 0.61 s (50/15), 0.09 / 0.51 s (50/25), 0.09 / 0.66 s (1 Gbit).
- **κ and duplicates.** κ rises from 9.4 to 10.3 (3 kB: 8.2 → 9.0; control and background bytes stay the same while the
  payload shrinks). PQ copies per message 3.8 → 4.5; IDONTWANT carries 17–23k ids per node per slot.
- **Bandwidth in the 4 s window**, mean / max node, % of cap: upload 45 / 68 (50/15), 28 / 44 (50/25), 6 / 13
  (1 Gbit); download ≤ 15 / 23. Without PQ (`R20-nopq-ps100-cf2-s1`, same hosts and seed), home upload in the same
  window is 21 / 32 % (50/15) and 13 / 20 % (50/25). The difference, PQ traffic plus any change it causes in other
  traffic, is 52–53 % of home upload in the window and 20–21 % over the whole slot (1 Gbit: 79 and 60 %). In the
  first second after publishing starts (4.0–5.0 s; the counters tick every 0.5 s), home hosts write to their
  connections at 130 % (50/15) and 83 % (50/25) of their upload cap on average, against 51 and 32 % without PQ (PQ
  60–61 %). The busiest 50/15 host reaches 206 % (31 Mbit/s; the same host without PQ 76 %), the busiest 50/25 host
  135 % (34 Mbit/s; 52 %); without PQ the busiest are at 83 and 53 %. These are bytes written to the connections
  (libp2p's bandwidth counters), not bytes on the link: above 100 %, more went into the send buffers in that second
  than the uplink could carry, and the rest was still queued at 5.0 s. Over the whole 4–8 s window the busiest home
  node·slot writes 95 % of what its uplink can carry in 4 s. The 3 kB run adds only 2–3 points of home upload in the
  window.
- **Backlog.** After-deadline PQ kB per node per slot grow at first, then flatten: 1 Gbit 194 → 1,420–1,630 from
  slot 12, 50/25 18 → 76. They are duplicates (1 Gbit: 69 → 606 copies per node in 8–16 s, about as at 3 kB);
  messages first delivered after the deadline average 0.19 per 1 Gbit node per slot in slots 2–15 and 0.41 in
  slots 16–19 (at most 0.75, slot 15), and none on home hosts.
- **Mesh.** 214–235 links per node, flat; connections 164 per node (Prysm 71); PQ mesh degree 6.4–7.5.
- **Negative-score peers** rise to 20.1k (slot 4) and settle at 14–17k. Per observer: Lighthouse 11.5, other 18.0,
  Lodestar 0.30, Nimbus 0.24, Teku 0.19, Prysm 0.19.
- **Mesh-delivery (P3) penalties** start at slot 15: 2.1k, 1.2k, 0.89k, 0.72k and 0.73k per slot. By topic: PQ
  729 → 564, attestation subnets 1,409 → 167, blocks and aggregates 0. From slot 15, by observer client (per host):
  Lighthouse PQ 1.17, attestation 0.58; other 3.78 / 1.11; Nimbus 3.24 / 4.30; Teku 2.23 / 5.21; Lodestar 5.53 / 3.86;
  Prysm 0.
- **Slot 15 on.** 1873 (Prysm, São Paulo) misses nothing in slots 2–14 and 63–250 messages in four of slots 15–19.
  Its connections, peer turnover, own PQ mesh degree (6.7 → 6.6) and that mesh's 1 Gbit share (0.84 → 0.82) do not
  change; it sits in fewer of its peers' PQ meshes (90 → 68), and from slot 16, 2–3 non-Rust peers score it negative
  (median −18 in slot 16, −96 to −103 in slots 17–19), consistent with P3 in Teku, Lodestar or Nimbus views. The 138
  other far-region 1 Gbit hosts miss 0.12 → 3.9 messages per slot.
- **IWANT.** Prysm, Teku, Lodestar and Nimbus hosts re-request 9–17 ids per IWANT that are still awaited from another
  peer (6.7M in total); Lighthouse and other hosts never do. Broken promises per IWANT: Lighthouse 0.046, other 0.040,
  Prysm 0.014, Teku 0.0015, Lodestar 0.0010.
- **Failed sends** that cost score: 9.5M per slot (forward timeout 32 %, forward queue-full 40 %, control queue-full
  28 %).
- **Stale messages.** 16,381 PQ and 90,915 background copies older than 60 s were ignored; nothing re-floods
  (bgexcess ≤ 1.019).
- **Background.** Blocks: none missing, first-seen p50 / p99 1.79 / 4.51 s. Columns: 677 of 669k missing.
  Attestations: 1.03 % of deliveries never arrive (3 kB: 0.59 %), almost all on all-64-subnet hosts.
- **Memory and time.** Peak 224.6 GiB PSS; wall 11,965 s.

### 2,048 hosts × 20 slots, 2.4 kB, seed 2: `R20-pq-2k4-ps100-cf2-s2` (cf2)

The headline cell with `--seed 2`: a different host sample, client mix, 1 Gbit selection, publishers and loss draws
(722 1 Gbit hosts instead of 742). Completion per slot (%, slots 0–19):

| class | per slot |
|---|---|
| 50/15 | 100 in every slot |
| 50/25 | 100 in every slot |
| 1 Gbit | 99.72 100 100 99.86 100 100 100 100 100 99.86 100 100 99.86 100 99.86 100 100 99.86 100 99.72 |

- **Strict rule: PASS with margin.** The worst slot from slot 2 is slot 19 at 99.72 % (2 of ~722 1 Gbit hosts; the
  rule allows 7). Slots 2–15 average 100 / 100 / 99.96 %, slots 16–19 100 / 100 / 99.90 %.
- **Incomplete node·slots**, 1 Gbit only: 7 in 18 slots (slots 2–15: never received 1, near miss 3; slots 16–19: near
  miss 2, late 1). No chronic host and no host that starts failing at slot 15; the most frequent is 1016 (other, São
  Paulo) with 3 slots. No message was missed by more than half of its subscribers.
- **PQ vs BLS.** PQ messages missing at 8 s on 1 Gbit hosts: 0.0001 % (slots 2–15) and 0.0018 % (16–19), none at
  home. Attestations in the same run: 0.019 / 0.042 / 2.17 % and 0.030 / 0.038 / 2.13 % (all-64-subnet hosts 2.42 /
  2.36 %).
- **P3** from slot 15: PQ 633 → 549 per slot, attestation subnets 1,684 → 265, blocks and aggregates 0. Per host from
  slot 15, PQ / attestation: Lighthouse 0.81 / 0.65, other 6.16 / 1.56, Teku 3.99 / 7.45, Lodestar 2.79 / 1.18,
  Nimbus 1.87 / 6.03, Prysm 0.
- **Negative-score peers per observer:** Lighthouse 10.8, other 18.6, Teku 0.21, Lodestar 0.18, Nimbus 0.17, Prysm
  0.14. **IWANT re-requests** of ids still awaited from another peer: Prysm 2.68M, Nimbus 1.78M, Teku 1.77M, Lodestar
  1.20M; Lighthouse and other 0.
- **Latency** from publish, p50 / p99: 0.08 / 0.62 s (50/15), 0.08 / 0.52 s (50/25), 0.06 / 0.55 s (1 Gbit). κ 9.3 →
  10.4; PQ copies per message 3.9 → 4.7. **Upload in the 4 s window**, mean / max node, % of cap: 43 / 71 (50/15),
  28 / 42 (50/25), 6 / 12 (1 Gbit); download ≤ 15 / 25.
- **Backlog.** After-deadline PQ kB per 1 Gbit node per slot: 137 → 1,275–1,440 from slot 12. They are duplicates
  (56 → 584 copies); messages first delivered after the deadline stay ≤ 0.14 per node per slot. Links per node stay flat. Failed sends
  that cost score: 9.0M per slot. Stale copies: PQ 9,951, background 57,873; bgexcess ≤ 1.009, so nothing re-floods.
- **Background.** Blocks: none missing, first-seen p50 / p99 1.98 / 4.24 s. Columns: 191 of 610k missing.
  Attestations: 0.66 % of deliveries never arrive.
- **Memory and time.** Peak 216.7 GiB PSS; wall 11,554 s.

### 2,048 hosts × 20 slots, 2.4 kB, rtt4 Shadow build: `R20-pq-2k4-rtt4-ps100-cf2-s1` (cf2)

The headline cell (×1.0, `--msg-bytes 2458`, seed 1, the same flags and generated network) on the rtt4 build, which
removes the current build's RTO ratchet (see Loss and TCP in [Caveats](#caveats)), with TCP logging. Completion per
slot (%, slots 0–19):

| class | per slot |
|---|---|
| 50/15 | 100 in every slot |
| 50/25 | 100 in every slot |
| 1 Gbit | 99.32 99.86 100 99.73 100 100 100 99.86 100 99.86 99.46 99.86 99.86 99.86 99.86 99.86 99.59 99.32 99.32 99.60 |

- **Strict rule: PASS.** The worst slots are 17 and 18 (99.32 %, 5 of ~740 1 Gbit hosts incomplete; the rule allows
  7; current build: slot 13 at 99.05 %, 7 hosts). Slots 2–15 average 100 / 100 / 99.87 % (current build 99.66 %),
  slots 16–19 100 / 100 / 99.46 % (99.53 %).
- **Incomplete node·slots**, 1 Gbit only: 13 in slots 2–15 (never 3, near miss 7, late 3; current build 35) and 16 in
  slots 16–19 (whole subnet 1, never 2, near miss 6, late 7; current build 14). 12 hosts are incomplete at least once,
  none in 9 or more of 18 slots; most often 930 (Lighthouse, Sydney, 6), 1520 (Prysm, Sydney, 5), 1811 (Prysm,
  Sydney, 4) and 852 (Prysm, São Paulo, 3). 1520, 852, 1811 and 1960 (Prysm, Sydney and São Paulo) miss in at most
  one slot before slot 16 and in two or more of slots 16–19, like 1873 on the current build; 1520 misses 207, 184 and
  168 messages in slots 16–18. 794 (Prysm, Singapore), chronic on the current build (15 of 18 slots, its forward
  timeouts rising from 14k to 25k per slot), misses nothing. 34 signatures are lost to churn; no publish is refused.
- **PQ vs BLS.** PQ messages missing at 8 s on 1 Gbit hosts: 0.0014 % (slots 2–15) and 0.020 % (16–19); current
  build 0.010 and 0.021 %. Home hosts miss none. BLS attestations missing in the same run: 0.23 / 0.25 / 1.48 % and
  0.008 / 0.074 / 1.35 % (current build 0.070 / 0.061 / 2.42 and 0.068 / 0.022 / 2.66 %). Attestation deliveries that
  never arrive: 0.53 % (current build 1.03 %).
- **Latency** from publish, p50 / p99: 0.10 / 0.64 s (50/15), 0.09 / 0.51 s (50/25), 0.09 / 0.68 s (1 Gbit), as on the
  current build. κ 9.1 → 10.3; PQ copies per message 3.6 → 4.4; IDONTWANT 15–23k ids per node per slot. **Upload in
  the 4 s window**, mean / max node, % of cap: 45 / 66 (50/15), 29 / 44 (50/25), 6 / 13 (1 Gbit); download ≤ 15 / 22.
- **Backlog.** After-deadline PQ kB per 1 Gbit node per slot: 132 → 1,067–1,188 from slot 12 (current build
  1,420–1,630). They are duplicates (54 → 482 copies per node in 8–16 s); messages first delivered after the deadline
  average 0.02 per node per slot in slots 2–15 and 0.37 in 16–19 (at most 0.50). Links per node 209–236, flat. Failed sends that cost score: 10.0M per slot (forward timeout 33 %,
  forward queue-full 39 %, control queue-full 28 %; current build 9.5M). Stale copies: PQ 9,331, background 59,549;
  nothing re-floods (largest per-topic excess 1.008).
- **Scores.** Negative-score peers reach 23.5k at slot 4 and settle at 15.9–18.3k (current build 20.1k, then
  14–17k). Per observer: Lighthouse 12.8, other 20.6, Lodestar 0.23, Nimbus 0.21, Teku 0.20, Prysm 0.12 (current
  build 11.5, 18.0, 0.30, 0.24, 0.19, 0.19). P3 from slot 15: PQ 784 → 594 per slot, attestation subnets 1,608 → 221,
  blocks and aggregates 0 (current build 729 → 564 and 1,409 → 167); per host, PQ / attestation: Lighthouse
  1.21 / 0.94, other 3.34 / 0.10, Nimbus 3.88 / 6.43, Teku 3.10 / 4.99, Lodestar 6.17 / 1.29, Prysm 0.
- **Background.** Blocks: none missing, first-seen p50 / p99 1.80 / 4.52 s. Columns: 360 of 669k missing.
- **TCP** (path type = sender → receiver; 1G = 1 Gbit host, home = 50/25 or 50/15):
  - Resent data packets per 1,000 data packets, slots 2–18: 1G→1G 0.23, 1G→home 3.68, home→1G 1.75, home→home 10.76,
    flat across slots.
  - First timeouts of an episode per 1,000 data packets climb over the run on every path with a home host, from slot 2
    to 18: 1G→home 3.9 → 6.8, home→1G 0.7 → 1.9, home→home 10.7 → 20.6; 1G→1G stays at 0.06–0.09. Sending endpoints
    and data per endpoint stay flat.
  - 9.20M RTOs in 5.20M episodes. By the Eifel test 5.01M episodes (96.6 %) are spurious and undone, with 0.25 resends
    each on average; the 174k genuine recoveries take 244 / 924 / 5,890 ms (p50 / p90 / p99), 190 / 440 / 758 ms
    when one RTO suffices. 67.6 % of first timeouts start within 1 s after a spurious undo on the same connection.
    Every post-RTO window is in-flight + 1; no connection stalls (0 of 6.95M snapshots).
  - SRTT − configured RTT, p50 / p99: 2 / 6 ms (1G→1G), 10 / 139 ms (1G→home), 5 / 12 ms (home→1G), 13 / 155 ms
    (home→home). 99.79 % of ACKs of new data echo the first segment they newly acknowledge. The RTO equals
    SRTT + rttvar in all 6.33M snapshots without backoff.
  - The same endpoints' windows shrink from slot 2 to 19: cwnd p50 1G→home 129 → 42, home→1G 134 → 46, home→home
    105 → 26 segments (1G→1G 368 → 153); the share with a reduced ssthresh rises from 50–55 % to 90–95 % on paths
    with a home host.
- **Memory and time.** Peak 224.4 GiB PSS; wall 11,792 s; TCP log 1.8 GB compressed.

### 2,048 hosts × 20 slots, 2.4 kB, rtt5 sensitivity build: `R20-pq-2k4-rtt5-ps100-cf2-s1` (cf2)

The headline cell (×1.0, `--msg-bytes 2458`, seed 1, the same flags and generated network) on the rtt5 sensitivity
build with all three switches on (Linux's congestion-window validation, restart after idle and consecutive
duplicate-ACK counting; see Loss and TCP in [Caveats](#caveats)), with TCP logging. Completion per slot (%, slots
0–19):

| class | per slot |
|---|---|
| 50/15 | 100 in every slot |
| 50/25 | 100 in every slot |
| 1 Gbit | 98.38 99.05 99.19 99.19 99.05 99.05 99.19 98.78 97.97 98.65 98.78 99.05 98.78 98.38 98.78 98.38 98.65 98.92 98.65 98.38 |

- **Strict rule: FAIL.** 1 Gbit hosts fall below 99 % in 12 of the 18 slots from slot 2: every slot from slot 7
  except slot 11. The worst is slot 8 at 97.97 % (about 15 of ~740 hosts incomplete; the rule allows 7). Slots 2–15
  average 100 / 100 / 98.80 %, slots 16–19 100 / 100 / 98.65 % (rtt4: 99.87 and 99.46 %, worst slot 99.32 %).
- **PQ vs BLS.** PQ messages missing at 8 s on 1 Gbit hosts: 0.032 % (slots 2–15) and 0.051 % (16–19), against
  0.0014 and 0.020 % on rtt4; home hosts miss none. BLS attestations missing in the same run: 0.092 / 0.19 / 2.54 %
  and 0.10 / 0.20 / 2.57 % (rtt4: 0.23 / 0.25 / 1.48 and 0.008 / 0.074 / 1.35 %), so on 1 Gbit hosts PQ messages
  still miss 50–80× less often than attestations. The matched no-PQ run (`R20-nopq-rtt5-ps100-cf2-s1`, see
  Calibration) misses 0.045 / 0.052 / 1.53 % and 0.058 / 0.034 / 1.67 %, so PQ adds 0.05 / 0.13 / 1.0 percentage
  points in slots 2–15 (rtt4 0.2 / 0.2 / 0.6, current build 0.04 / 0.04 / 1.4).
- **Who misses.** 164 incomplete 1 Gbit node·slots (never 21, near miss 70, late 73; rtt4 29): 124 in slots 2–15
  and 40 in 16–19. 32 of 742 hosts are incomplete at least once (rtt4 12). Chronic: 1529 and 1520 (Prysm, Sydney,
  15 of 18 slots each), 346 (Prysm, Singapore, 14), 939 (Prysm, Seoul, 13), 794 (Prysm, Singapore, 13), 1960
  (Prysm, São Paulo, 12), 795 (Lighthouse, Sydney, 11) and 640 (Prysm, Sydney, 9); every one of these Prysm hosts
  has 70 peers. On rtt4 the same hosts miss in at most 5 slots (1520), 794 in none. The failure mode is fs0's:
  far-region Prysm hosts with 70 peers.
- **Over the run.** 1 Gbit completion steps down after slot 7 and then holds: mean 99.08 % in slots 2–7, 98.60 % in
  8–13 and 98.63 % in 14–19. Their PQ message misses keep rising, from 0.019 % to 0.035 % and 0.056 % in the same
  blocks (slots 15–19 include the P3 onset). ssthresh after a restart falls mostly in slots 4–9 and then drifts down
  by 14–23 % over slots 10–18. Block first-seen from publish, p95, is 2.2× rtt4's in slots 2–7 (0.79 against 0.37 s)
  and 1.7× after (0.56–0.63 against 0.33–0.36 s), so the block slowdown does not grow as ssthresh falls. Per slot
  (slots 2–19; ssthresh slots 2–18, u = more than half of the restarts on connections that never reduced it):

| series | per slot |
|---|---|
| block first-seen from publish p95, rtt4 (s) | 0.33 0.31 0.37 0.37 0.50 0.32 0.30 0.32 0.31 0.36 0.38 0.29 0.33 0.29 0.42 0.36 0.31 0.46 |
| block first-seen from publish p95, rtt5 (s) | 0.80 0.79 0.85 0.71 0.93 0.66 0.69 0.48 0.53 0.64 0.60 0.40 0.62 0.51 0.62 0.59 0.58 0.88 |
| ssthresh p50 after a restart, 1G→1G | u u 353 140 124 109 94 82 73 69 66 66 64 60 57 58 57 |
| ssthresh p50 after a restart, 1G→home | u 61 33 28 26 24 24 22 22 21 21 21 20 19 19 19 19 |
| ssthresh p50 after a restart, home→1G | u u 123 63 46 37 34 31 30 28 28 27 27 27 25 25 25 |
| ssthresh p50 after a restart, home→home | u u u 35 22 18 15 13 13 12 12 12 11 11 10 10 10 |
| 1 Gbit PQ messages missing at 8 s (%) | 0.008 0.015 0.015 0.025 0.022 0.030 0.052 0.039 0.026 0.025 0.029 0.037 0.068 0.064 0.088 0.020 0.051 0.045 |

- **P3** from slot 15: PQ 804 → 926 per slot (rising; rtt4 784 → 594) and attestation 1,169 → 281; block and
  aggregate 0. Per host, PQ / attestation: Lighthouse 1.37 / 0.96, other 10.75 / 2.26, Teku 3.92 / 3.32, Lodestar
  4.02 / 2.43, Nimbus 2.40 / 4.54, Prysm 0. Negative-score peers per observer: Lighthouse 16.3, other 24.1; Teku,
  Lodestar, Nimbus and Prysm 0.18–0.27 (rtt4 12.8, 20.6 and 0.12–0.23).
- **Latency** from publish, p50 / p99: 0.15 / 0.84 s (50/15), 0.14 / 0.82 s (50/25), 0.13 / 1.18 s (1 Gbit); rtt4
  0.10 / 0.64, 0.09 / 0.51 and 0.09 / 0.68 s.
- **κ** 9.0 → 10.3; PQ copies per message 3.6 → 4.4; IDONTWANT 15–22k ids per node per slot (as on rtt4).
- **Bandwidth in the 4 s window**, mean / max node, % of cap: upload 45 / 71 (50/15), 29 / 44 (50/25), 6 / 14
  (1 Gbit); download ≤ 14 / 24. Without PQ (`R20-nopq-rtt5-ps100-cf2-s1`): 22 / 33 % (50/15) and 13 / 21 % (50/25),
  so the PQ difference is 52–53 % of home upload in the window, as on the current build. In 4.0–5.0 s: 127 / 215 %
  (50/15) and 82 / 131 % (50/25) with PQ, against 49 / 81 % and 31 / 54 % without (bytes written to the connections;
  see the headline run).
- **Backlog.** After-deadline PQ kB per 1 Gbit node per slot: 212 → 1,108–1,306 from slot 8 (rtt4 132 → 1,067–1,188
  from slot 12), mostly duplicates (messages first delivered after the deadline: 0.61 per 1 Gbit node per slot in
  slots 2–15 and 1.00 in 16–19, rising from 0.13 at slot 2 to 1.27–1.68 in slots 14–16); home hosts 20–22 → 93–107 kB. Links
  per node 205–232 and connections 163–165 per node, flat. Negative-score peers peak at 30.2k in slot 5 and settle at
  19–20k from slot 13 (rtt4 23.5k and 16–18k). Failed sends that cost score: 217.4M in all (forward timeout 37.6 %,
  forward queue full 34.9 %, control queue full 27.4 %; rtt4 200.0M). Stale copies: PQ 444, background 2,300;
  bgexcess ≤ 1.008. Churn removes 34 of 40,000 signatures; no refused publish.
- **TCP** (path types by sender → receiver):
  - Restarts after idle: about 1.5M per slot (1G→1G 250k, 1G→home 400k, home→1G 410k, home→home 430k), flat over
    the run; median idle time 0.9–1.0 s against a median RTO of 0.29–0.36 s. cwnd before → after, p50 (p90):
    12 (50) → 10 (15) on 1G→1G and 10 (21–27) → 10 (10) elsewhere. 81 % of restarts leave cwnd below ssthresh, and
    all of those continue in slow start.
  - cwnd p50 / p90 over the run: 10 / 35 (1G→1G), 10 / 19 (1G→home and home→1G), 10 / 16 (home→home). The same
    endpoints' cwnd p50 is 10 at slots 2 and 19 on every path type (rtt4: 368 → 153 on 1G→1G, 105 → 26 on
    home→home).
  - Fast-recovery entries per 1,000 data packets: 0.20 (1G→1G), 1.42 (1G→home), 1.38 (home→1G), 2.31 (home→home),
    all after consecutive duplicate ACKs.
  - Resends per 1,000 data packets, flat: 1G→1G 0.21, 1G→home 3.18, home→1G 1.64, home→home 9.42 (rtt4 0.23, 3.68,
    1.75, 10.76). First timeouts per 1,000 data packets still climb (slots 2 → 18): home→home 9.9 → 18.8, 1G→home
    3.3 → 5.5, home→1G 0.5 → 1.3, 1G→1G 0.05 → 0.06, 10–30 % below rtt4's. 7.73M RTOs (rtt4 9.20M); 96.3 % of
    timeout episodes are spurious and undone; no stalls; the RTO formula holds in every snapshot without backoff.
- **Blocks:** none missing; from publish p50 / p95 / p99 0.34 / 0.73 / 0.93 s (rtt4 0.19 / 0.37 / 0.48 s).
  Attestations after 4 s p50 / p95 / p99 1.10 / 2.40 / 4.39 s (rtt4 1.06 / 2.08 / 3.56 s); 0.85 % never arrive
  (rtt4 0.53 %).
- **Memory and time.** Peak 228.3 GiB PSS; wall 11,828 s; TCP log 2.6 GB compressed.
- **Reading.** With Linux's window validation and restart after idle, bursts start from about 10 segments and need
  extra round trips on long paths, and the headline cell fails on the far-region 1 Gbit hosts. Two known differences
  make rtt5 slower than Linux: Reno halves ssthresh where CUBIC keeps 0.7 × cwnd, and there is no tail-loss probe.
  One makes it faster: it never shrinks a window that a busy connection stops filling (Linux's
  `tcp_cwnd_application_limited`; see Loss and TCP in [Caveats](#caveats)). A fourth switch (`RTT5_BETA`, CUBIC's
  decrease) passed its 64-host check and cut block p99 from publish there by 13 %. This cell fails by far more than
  that cut recovered, so the switch is tried on the bundled cell instead, where it could change the outcome, and
  there it turns the fail into a pass (`R20-pq-b16-2k4-rtt5b-ps100-cf2-s1`, see its section). Linux's CUBIC (rtt6)
  recovers most of rtt5's slowdown on the 64-host check (see Loss and TCP in [Caveats](#caveats)), so both headline
  cells run on it; the bundled one passes with margin (`R20-pq-b16-2k4-rtt6-ps100-cf2-s1`) and the unbundled one with
  one host to spare (`R20-pq-2k4-rtt6-ps100-cf2-s1`); see their sections.

### 2,048 hosts × 20 slots, 2.4 kB, 16 signatures per message, rtt5 sensitivity build: `R20-pq-b16-2k4-rtt5-ps100-cf2-s1` (cf2)

The flags of `R20-pq-b16-2k4-ps100-cf2-s1` (×1.0, `--msg-bytes 2458`, `--batch 16`, P3 rate 66.93 from its own
20-slot mean, seed 1, the same generated network) on the rtt5 sensitivity build with all three switches on, with TCP
logging. Completion per slot (%, slots 0–19):

| class | per slot |
|---|---|
| 50/15 | 100 in every slot |
| 50/25 | 100 in every slot |
| 1 Gbit | 99.05 99.46 99.32 99.59 99.59 99.59 99.46 99.32 98.92 99.05 99.32 99.59 99.19 99.05 98.92 98.92 98.38 99.19 98.92 98.52 |

- **Strict rule: FAIL.** 1 Gbit hosts fall below 99 % in 6 of the 18 slots from slot 2 (slots 8, 14, 15, 16, 18 and
  19). The worst is slot 16 at 98.38 % (12 of ~740 hosts; the rule allows 7). Slots 2–15 average 100 / 100 / 99.28 %,
  slots 16–19 100 / 100 / 98.75 % (b16 on the current build: 99.87 and 99.73 %, worst slot 99.59 %; unbundled on
  rtt5: 98.80 and 98.65 %, worst 97.97 %). So the 50-slot run on rtt5 (`L-pq-b16-2k4-rtt5-ps100-cf2-s1`) was not
  queued.
- **PQ vs BLS.** PQ messages missing at 8 s on 1 Gbit hosts: 0.013 % (slots 2–15) and 0.025 % (16–19), against
  0.0024 and 0.0028 % for b16 on the current build and 0.032 and 0.051 % unbundled on rtt5; home hosts miss none. BLS
  attestations missing in the same run: 0.22 / 0.29 / 2.69 % and 0.064 / 0.13 / 3.10 %, so on 1 Gbit hosts PQ
  messages miss 125–210× less often than attestations. Against the matched no-PQ run (`R20-nopq-rtt5-ps100-cf2-s1`:
  0.045 / 0.052 / 1.53 % and 0.058 / 0.034 / 1.67 %), PQ adds 0.18 / 0.24 / 1.16 percentage points in slots 2–15 and
  0.01 / 0.10 / 1.43 in 16–19 (unbundled on rtt5: 0.05 / 0.13 / 1.0 and 0.04 / 0.16 / 0.9). The larger home additions
  sit in slots 3–12 (50/25 up to 0.74 % in slot 10) and fall to 0.05–0.19 % from slot 13; their cause is not
  established.
- **Who misses.** 112 incomplete 1 Gbit node·slots (never 13, near miss 53, late 46; b16 on the current build 21,
  unbundled on rtt5 164): 75 in slots 2–15 and 37 in 16–19. 30 of 742 hosts are incomplete at least once (18 Prysm,
  9 Lighthouse, 3 other; b16 on the current build 9, unbundled on rtt5 32). One chronic host: 795 (Lighthouse, Sydney,
  200 peers, 11 of 18 slots; also chronic unbundled on rtt5). Then 1960 and 852 (Prysm, São Paulo, 8 each), 939
  (Prysm, Seoul, 7), 988 (Prysm, São Paulo, 7), 945 (Lighthouse, São Paulo, 6), 344 (Prysm, Singapore, 6), 1396
  (Lighthouse, Singapore, 6) and 1858 (Prysm, Tokyo, 6); every Prysm host here has 70 peers. Six hosts start failing
  in slots 16–19 (at least twice there, at most once before): 1972 (Prysm, Seoul), 794 and 346 (Prysm, Singapore),
  1065 (Prysm, US West), 525 (other, São Paulo) and 1860 (Lighthouse, São Paulo). On 1972, the worst of them (33–114
  missing messages per slot), the PQ mesh degree falls from 6.3 to 5.1 and that mesh's 1 Gbit share from 0.79 to
  0.70. The failure mode is the unbundled one: far-region 1 Gbit hosts, mostly Prysm with 70 peers.
- **Over the run.** 1 Gbit completion falls block by block: mean 99.48 % in slots 2–7, 99.19 % in 8–13 and 98.81 %
  in 14–19 (unbundled on rtt5 it stepped down and held: 99.08, 98.60, 98.63 %). PQ message misses rise from 0.008 %
  to 0.012 % and 0.026 % in the same blocks (unbundled 0.019, 0.035, 0.056 %; slots 15–19 include the P3 onset).
  ssthresh after a restart falls mostly in slots 3–8 on paths with a home end and keeps falling on 1G→1G paths
  (185 → 64 over slots 7–18). Block first-seen from publish, p95, is 2.2× the current-build b16 run's in slots 2–7
  (0.78 against 0.35 s), 1.7× in 8–13 (0.58 / 0.34 s) and 2.0× in 14–19 (0.68 / 0.34 s), about as unbundled on rtt5
  (0.79, 0.56, 0.63 s), so the block slowdown does not grow as ssthresh falls. Per slot (slots 2–19; ssthresh slots
  2–18, u = more than half of the restarts on connections that never reduced it):

| series | per slot |
|---|---|
| block first-seen from publish p95, b16 current build (s) | 0.32 0.29 0.34 0.37 0.52 0.28 0.31 0.31 0.33 0.34 0.39 0.35 0.31 0.30 0.42 0.34 0.31 0.38 |
| block first-seen from publish p95, unbundled rtt5 (s) | 0.80 0.79 0.85 0.71 0.93 0.66 0.69 0.48 0.53 0.64 0.60 0.40 0.62 0.51 0.62 0.59 0.58 0.88 |
| block first-seen from publish p95, b16 rtt5 (s) | 0.79 0.75 0.78 0.75 0.96 0.66 0.68 0.49 0.69 0.64 0.61 0.39 0.69 0.59 0.68 0.64 0.59 0.88 |
| ssthresh p50 after a restart, 1G→1G | u u u u u 185 143 121 99 96 81 84 79 74 72 69 64 |
| ssthresh p50 after a restart, 1G→home | u 99 37 30 27 25 24 23 22 22 21 21 21 20 19 19 19 |
| ssthresh p50 after a restart, home→1G | u u u 120 61 40 34 31 30 28 27 27 26 25 25 25 25 |
| ssthresh p50 after a restart, home→home | u u u 61 24 19 16 15 13 13 12 12 11 11 10 10 10 |
| 1 Gbit completion, b16 current build (%) | 100 100 100 99.86 100 99.86 100 99.73 99.86 100 99.73 99.86 99.73 99.59 99.86 99.73 99.59 99.73 |
| 1 Gbit completion, b16 rtt5 (%) | 99.32 99.59 99.59 99.59 99.46 99.32 98.92 99.05 99.32 99.59 99.19 99.05 98.92 98.92 98.38 99.19 98.92 98.52 |
| 1 Gbit PQ messages missing at 8 s, b16 current build (%) | 0 0 0 0.0007 0 0.0014 0 0.0058 0.0001 0 0.0013 0.0056 0.0079 0.0101 0.0001 0.0037 0.0046 0.0026 |
| 1 Gbit PQ messages missing at 8 s, b16 rtt5 (%) | 0.0074 0.0036 0.0030 0.0056 0.0099 0.0212 0.0162 0.0111 0.0070 0.0080 0.0126 0.0194 0.0198 0.0361 0.0276 0.0162 0.0143 0.0411 |

- **P3** from slot 15: PQ 1,387 → 2,424 per slot (rising, as for b16 on the current build: 1,302 → 2,527) and
  attestation 1,496 → 296; block and aggregate 0. Per host, PQ / attestation: Lighthouse 4.89 / 0.87, other 21.98 /
  2.90, Teku 3.03 / 2.95, Lodestar 5.95 / 6.86, Nimbus 3.87 / 5.78, Prysm 0. Negative-score peers per observer:
  Lighthouse 14.1, other 20.8; Teku, Lodestar, Nimbus and Prysm 0.17–0.22 (b16 on the current build 9.6, 14.1 and
  0.11–0.22).
- **Latency** from publish, p50 / p99: 0.11 / 0.66 s (50/15), 0.10 / 0.68 s (50/25), 0.10 / 0.96 s (1 Gbit); b16
  on the current build 0.09 / 0.49, 0.08 / 0.43 and 0.08 / 0.60 s.
- **κ** 8.6 → 9.8; PQ copies per message 3.75 → 4.55; IDONTWANT 9.4–13.3k ids per node per slot (b16 on the current
  build 9.0 → 9.9, 4.1 → 4.7 and 10.4–13.7k).
- **Bandwidth in the 4 s window**, mean / max node, % of cap: upload 42 / 63 (50/15), 27 / 42 (50/25), 5 / 12
  (1 Gbit); download ≤ 14 / 23 (b16 on the current build within a point of these).
- **Backlog.** After-deadline PQ kB per 1 Gbit node per slot: 188 → 1,047 by slot 8, then 1,188–1,331 from slot 12
  (b16 on the current build 152 → 1,340–1,555 from slot 12); home hosts 18–22 → 73–78 kB, still rising (b16 on the
  current build, 50/25: 13 → 53). Messages first delivered after the deadline are 0 on home hosts and 0.13 / 0.24
  per 1 Gbit node per slot (slots 2–15 / 16–19, at most 0.38), so these bytes are copies of messages already held. Links per node 210–233 and connections 163–165 per node, flat. Negative-score peers peak at
  24.9k in slot 5 and settle at 17–20k (b16 on the current build 16.4k and 12–13.5k). Failed sends that cost score:
  146.6M (forward timeout 47.9 %, forward queue full 41.6 %, control queue full 10.4 %; b16 on the current build
  132.2M, unbundled on rtt5 217.4M). Stale copies: PQ 0, background 142; bgexcess ≤ 1.008. Churn removes 34 of 40,000
  signatures; no refused publish.
- **TCP** (path types by sender → receiver):
  - Restarts after idle: about 1.5M per slot (1G→1G 250k, 1G→home 405k, home→1G 415k, home→home 430k), flat; median
    idle time 0.9–1.0 s against a median RTO of 0.29–0.36 s. cwnd before → after, p50 (p90): 10 (46) → 10 (14) on
    1G→1G and 10 (21–27) → 10 (10) elsewhere. 81 % of restarts leave cwnd below ssthresh, and all of those continue
    in slow start.
  - cwnd p50 / p90 over the run: 10 / 29 (1G→1G), 10 / 18 (1G→home and home→1G), 10 / 16 (home→home); the same
    endpoints' cwnd p50 is 10 at slots 2 and 19 on every path type.
  - Fast-recovery entries per 1,000 data packets: 0.22 (1G→1G), 1.43 (1G→home), 1.39 (home→1G), 2.30 (home→home),
    all after consecutive duplicate ACKs.
  - Resends per 1,000 data packets, flat: 0.24, 3.29, 1.69 and 9.44 (unbundled on rtt5 0.21, 3.18, 1.64, 9.42). First
    timeouts per 1,000 data packets climb (slots 2 → 18): home→home 9.0 → 18.5, 1G→home 3.2 → 5.6, home→1G 0.60 →
    1.32, 1G→1G 0.05 → 0.07, as unbundled. 7.13M RTOs; 96.2 % of Eifel checks found the timeout spurious and undid
    it, and 66 % of first timeouts start within 1 s after such an undo on the same connection; no stalls (6.95M
    snapshots); the RTO formula holds in all 6,418,294 snapshots without backoff; buffers start at 131,072 /
    174,760 B on every connection.
- **Blocks:** none missing; from publish p50 / p95 / p99 0.34 / 0.74 / 0.93 s (b16 on the current build 0.19 / 0.36 /
  0.48 s, unbundled on rtt5 0.34 / 0.73 / 0.93 s). Attestations after 4 s p50 / p95 / p99 1.09 / 2.40 / 4.63 s;
  0.89 % never arrive (b16 on the current build 1.06 / 2.06 / 3.62 s and 0.55 %).
- **Memory and time.** Peak 220.6 GiB PSS; wall 10,988 s; TCP log 2.5 GB compressed.
- **Reading.** On rtt5, 16 signatures per message reduce the 1 Gbit shortfall (112 incomplete node·slots against
  164, PQ misses about halved, 6 slots below 99 % against 12), but the cell still fails on the same far-region hosts,
  and its completion declines over the 20 slots instead of holding. So bundling does not make the pass independent of
  how fast TCP windows reopen after idle. The 50-slot trend on rtt5 is untested, because the L run was conditional on
  this one passing.

### 2,048 hosts × 20 slots, 2.4 kB, 16 signatures per message, rtt5 with CUBIC's decrease (`RTT5_BETA=1`): `R20-pq-b16-2k4-rtt5b-ps100-cf2-s1` (cf2)

The run above (×1.0, `--msg-bytes 2458`, `--batch 16`, P3 rate 66.93, seed 1, the same generated network), on the
rtt5b build with rtt5's three switches on and `RTT5_BETA=1`, with TCP logging. The only change is that each
fast-recovery entry and each RTO sets ssthresh = max(cwnd × 717 / 1024, 2), CUBIC's decrease, instead of Reno's
cwnd / 2. Completion per slot (%, slots 0–19):

| class | per slot |
|---|---|
| 50/15 | 100 in every slot |
| 50/25 | 100 in every slot |
| 1 Gbit | 99.05 99.32 99.46 100 99.73 99.59 99.73 99.73 99.73 99.46 99.73 99.86 99.73 99.86 99.86 99.86 99.59 99.59 99.59 99.33 |

- **Strict rule: PASS.** Every class is at 99 % or more in every slot from slot 2. The worst is slot 19 at 99.33 % on
  1 Gbit hosts (5 of ~740; the rule allows 7). Slots 2–15 average 100 / 100 / 99.74 %, slots 16–19 100 / 100 /
  99.53 % (b16 on rtt5: 99.28 and 98.75 %, worst 98.38 %; b16 on the current build: 99.87 and 99.73 %, worst
  99.59 %). Misses do not accumulate: 0–5 incomplete hosts per slot (13, 12 and 16 in the three six-slot blocks),
  and messages first delivered after the deadline stay ≤ 0.15 per 1 Gbit node per slot (none on home hosts), so the
  after-deadline bytes are copies of messages already held (see Backlog).
- **PQ vs BLS.** PQ messages missing at 8 s on 1 Gbit hosts: 0.0031 % (slots 2–15) and 0.0068 % (16–19), against
  0.013 and 0.025 % for b16 on rtt5 and 0.0024 and 0.0028 % on the current build; home hosts miss none. BLS
  attestations missing in the same run: 0.15 / 0.12 / 2.14 % and 0.15 / 0.14 / 2.27 % (b16 on rtt5: 0.22 / 0.29 /
  2.69 and 0.064 / 0.13 / 3.10 %), so on 1 Gbit hosts PQ messages miss 330–690× less often than attestations. No
  no-PQ run uses this build (`R20-nopq-rtt5-ps100-cf2-s1` has Reno's halving), so a comparison with a no-PQ run is
  unmatched and its difference is not attributed to PQ.
- **Who misses.** 41 incomplete 1 Gbit node·slots (never 3, near miss 24, late 14; b16 on rtt5 112, b16 on the current
  build 21): 27 in slots 2–15 and 14 in 16–19. 13 of 742 hosts are incomplete at least once (7 Prysm, 5 Lighthouse,
  1 Teku; b16 on rtt5 30). One chronic host: 1960 (Prysm, São Paulo, 70 peers, 10 of 18 slots; 8 on rtt5). Then 795
  (Lighthouse, Sydney, 200 peers, 7; chronic on rtt5 with 11), 794 (Prysm, Singapore, 6), 344 (Prysm, Singapore, 3)
  and 640 (Prysm, Sydney, 3). The failure mode is rtt5's, far-region 1 Gbit hosts, mostly Prysm with 70 peers, on
  fewer hosts.
- **Over the run.** 1 Gbit completion holds: mean 99.71 % in slots 2–7, 99.73 % in 8–13 and 99.64 % in 14–19 (b16 on
  rtt5: 99.48, 99.19, 98.81 %). PQ message misses are 0.0032, 0.0039 and 0.0048 % in the same blocks (b16 on rtt5
  0.008, 0.012, 0.026 %). ssthresh after a restart is higher than on rtt5 on every path type, most on 1G→1G (91
  against 64 at slot 18, the 0.7 / 0.5 ratio of the two decreases) and by 1.1–1.2× on paths with a home end (22 / 28
  / 12 against 19 / 25 / 10). It still falls over the run (1G→1G 358 → 91 over slots 7–18). Block first-seen from
  publish, p95, is 2.0× the current-build b16 run's in slots 2–7 (0.72 against 0.35 s), 1.6× in 8–13 (0.55 / 0.34 s)
  and 1.8× in 14–19 (0.60 / 0.34 s), 6–11 % below b16 on rtt5 (0.78, 0.58, 0.68 s), so the block slowdown does not
  grow as ssthresh falls. Per slot (slots 2–19; ssthresh slots 2–18, u = more than half of the restarts on
  connections that never reduced it; rtt5's ssthresh rows are in the section above):

| series | per slot |
|---|---|
| block first-seen from publish p95, b16 current build (s) | 0.32 0.29 0.34 0.37 0.52 0.28 0.31 0.31 0.33 0.34 0.39 0.35 0.31 0.30 0.42 0.34 0.31 0.38 |
| block first-seen from publish p95, b16 rtt5 (s) | 0.79 0.75 0.78 0.75 0.96 0.66 0.68 0.49 0.69 0.64 0.61 0.39 0.69 0.59 0.68 0.64 0.59 0.88 |
| block first-seen from publish p95, b16 rtt5b (s) | 0.69 0.76 0.77 0.64 0.85 0.62 0.58 0.51 0.67 0.57 0.57 0.38 0.59 0.56 0.59 0.58 0.53 0.76 |
| ssthresh p50 after a restart, 1G→1G | u u u u u 358 291 195 168 148 128 121 112 96 91 93 91 |
| ssthresh p50 after a restart, 1G→home | u 153 61 41 34 30 28 27 25 25 24 24 23 23 23 23 22 |
| ssthresh p50 after a restart, home→1G | u u u 169 117 78 58 42 37 34 33 31 30 30 30 28 28 |
| ssthresh p50 after a restart, home→home | u u u 88 28 21 18 17 16 14 14 13 13 12 12 12 12 |
| 1 Gbit completion, b16 rtt5 (%) | 99.32 99.59 99.59 99.59 99.46 99.32 98.92 99.05 99.32 99.59 99.19 99.05 98.92 98.92 98.38 99.19 98.92 98.52 |
| 1 Gbit completion, b16 rtt5b (%) | 99.46 100 99.73 99.59 99.73 99.73 99.73 99.46 99.73 99.86 99.73 99.86 99.86 99.86 99.59 99.59 99.59 99.33 |
| 1 Gbit PQ messages missing at 8 s, b16 rtt5 (%) | 0.0074 0.0036 0.0030 0.0056 0.0099 0.0212 0.0162 0.0111 0.0070 0.0080 0.0126 0.0194 0.0198 0.0361 0.0276 0.0162 0.0143 0.0411 |
| 1 Gbit PQ messages missing at 8 s, b16 rtt5b (%) | 0.0091 0 0.0019 0.0021 0.0025 0.0034 0.0023 0.0078 0.0049 0.0010 0.0039 0.0036 0.0001 0.0016 0.0014 0.0069 0.0048 0.0139 |

- **P3** from slot 15: PQ 1,134 → 2,068 per slot (b16 on rtt5 1,387 → 2,424) and attestation 1,126 → 381 (1,496 →
  296); block and aggregate 0. Per host, PQ / attestation: Lighthouse 4.24 / 1.23, other 18.08 / 1.58, Teku 3.35 /
  1.97, Lodestar 6.41 / 3.64, Nimbus 3.83 / 4.90, Prysm 0. Negative-score peers per observer: Lighthouse 12.2, other
  18.5; Teku, Lodestar, Nimbus and Prysm 0.13–0.18 (b16 on rtt5 14.1, 20.8 and 0.17–0.22).
- **Latency** from publish, p50 / p99: 0.10 / 0.62 s (50/15), 0.10 / 0.59 s (50/25), 0.09 / 0.78 s (1 Gbit); b16 on
  rtt5 0.11 / 0.66, 0.10 / 0.68 and 0.10 / 0.96 s.
- **κ** 8.8 → 9.9; PQ copies per message 3.85 → 4.64; IDONTWANT 9.7–13.6k ids per node per slot (b16 on rtt5 8.6 →
  9.8, 3.75 → 4.55 and 9.4–13.3k).
- **Bandwidth in the 4 s window**, mean / max node, % of cap: upload 42 / 62 (50/15), 27 / 42 (50/25), 6 / 13
  (1 Gbit); download ≤ 14 / 21 (b16 on rtt5 within a point of these).
- **Backlog.** After-deadline PQ kB per 1 Gbit node per slot: 155 → 1,024 by slot 9, then 964–1,192 from slot 10
  (b16 on rtt5: 188 → 1,047 by slot 8, then 1,188–1,331 from slot 12); home hosts 11–12 → 44–53 kB, still rising (b16
  on rtt5 18–22 → 73–78). Messages first delivered after the deadline stay ≤ 0.15 per 1 Gbit node per slot and are
  0 on home hosts, so these bytes are copies of messages already held. Links per node 212–235 and connections 163–165 per node, flat. Negative-score
  peers peak at 21.8k in slot 4 and settle at 14.8–15.9k from slot 12 (b16 on rtt5 24.9k and 17–20k). Failed sends that
  cost score: 131.9M (forward timeout 47.3 %, forward queue full 43.4 %, control queue full 9.3 %; b16 on rtt5
  146.6M). Stale copies: PQ 0, background 11; bgexcess ≤ 1.008 on background topics. Churn removes 34 of 40,000
  signatures; no refused publish.
- **TCP** (path types by sender → receiver):
  - Restarts after idle: about 1.5M per slot (1G→1G 250k, 1G→home 400k, home→1G 415k, home→home 425k), flat; median
    idle time 0.9–1.0 s against a median RTO of 0.29–0.36 s. cwnd before → after, p50 (p90): 11 (51) → 10 (16) on
    1G→1G and 10 (22–27) → 10 (10) elsewhere. 88 % of restarts leave cwnd below ssthresh (b16 on rtt5 81 %), and all
    of those continue in slow start.
  - cwnd p50 / p90 over the run: 10 / 29 (1G→1G), 10 / 19 (1G→home and home→1G), 10 / 18 (home→home); b16 on rtt5
    10 / 29, 10 / 18 and 10 / 16.
  - Fast-recovery entries per 1,000 data packets: 0.23 (1G→1G), 1.44 (1G→home), 1.40 (home→1G), 2.33 (home→home),
    all after consecutive duplicate ACKs (b16 on rtt5 0.22, 1.43, 1.39, 2.30).
  - Resends per 1,000 data packets, flat: 0.26, 3.40, 1.79 and 10.10 (b16 on rtt5 0.24, 3.29, 1.69, 9.44). First
    timeouts per 1,000 data packets climb (slots 2 → 18): home→home 9.9 → 20.0, 1G→home 3.4 → 6.1, home→1G 0.79 →
    1.92, 1G→1G 0.08 → 0.12, each above b16 on rtt5 (9.0 → 18.5, 3.2 → 5.6, 0.60 → 1.32, 0.05 → 0.07). 7.90M RTOs
    (b16 on rtt5 7.13M); 96.4 % of Eifel checks found the timeout spurious and undid it, and 67 % of first timeouts
    start within 1 s after such an undo on the same connection; no stalls (6.95M snapshots); the RTO formula holds in
    all 6,376,135 snapshots without backoff; buffers start at 131,072 / 174,760 B on every connection.
- **Blocks:** none missing; from publish p50 / p95 / p99 0.34 / 0.67 / 0.85 s (b16 on rtt5 0.34 / 0.74 / 0.93 s, b16
  on the current build 0.19 / 0.36 / 0.48 s). Attestations after 4 s p50 / p95 / p99 1.09 / 2.25 / 4.36 s; 0.58 %
  never arrive (b16 on rtt5 1.09 / 2.40 / 4.63 s and 0.89 %).
- **Memory and time.** Peak 219.0 GiB PSS; wall 11,410 s; TCP log 2.6 GB compressed.
- **Reading.** On rtt5, CUBIC's decrease alone turns the bundled cell from a fail into a pass, with 2 hosts to spare
  in the worst slot, and 1 Gbit completion holds over the 20 slots instead of falling. ssthresh stays higher after
  each loss, so slow start after a restart runs longer; windows over the run barely change, RTOs rise by 11 %, and
  blocks reach the network only 6–11 % sooner, still 1.6–2.0× the current build's time. Whether the pass holds over
  50 slots is untested on rtt5b. rtt6, which includes this decrease and adds CUBIC's window growth, passes this cell
  with more margin (see the next section).

### 2,048 hosts × 20 slots, 2.4 kB, 16 signatures per message, rtt6 (Linux's CUBIC with HyStart): `R20-pq-b16-2k4-rtt6-ps100-cf2-s1` (cf2)

The bundled cell's flags (×1.0, `--msg-bytes 2458`, `--batch 16`, P3 rate 66.93, seed 1, the same generated network)
on rtt6, the build closest to stock Linux: rtt5 with its three switches on (window validation, restart after idle,
consecutive duplicate ACKs) plus Linux's CUBIC and HyStart, all on by default. TCP logging. Completion per slot (%,
slots 0–19):

| class | per slot |
|---|---|
| 50/15 | 100 in every slot |
| 50/25 | 100 in every slot |
| 1 Gbit | 98.38 99.86 99.86 99.86 100 100 99.86 100 100 99.86 100 100 100 100 99.86 99.86 99.73 99.86 100 99.73 |

- **Strict rule: PASS, with margin.** Every class is at 99 % or more in every slot from slot 2. The worst slots are 16
  and 19 at 99.73 % on 1 Gbit hosts (2 of ~740; the rule allows 7). Slots 2–15 average 100 / 100 / 99.94 %, slots
  16–19 100 / 100 / 99.83 % (b16 on rtt5b: 99.74 and 99.53 %, worst 99.33 %; on rtt5: 99.28 and 98.75 %, worst
  98.38 %; on the current build: 99.87 and 99.73 %, worst 99.59 %). Misses do not accumulate: 0–2 incomplete hosts
  per slot, and messages first delivered after the deadline stay ≤ 0.05 per 1 Gbit node per slot (see
  Backlog).
- **PQ vs BLS.** PQ messages missing at 8 s on 1 Gbit hosts: 0.0008 % (slots 2–15) and 0.0033 % (16–19), against
  0.0031 and 0.0068 % on rtt5b, 0.013 and 0.025 % on rtt5 and 0.0024 and 0.0028 % on the current build; home hosts
  miss none. BLS attestations missing in the same run: 0.029 / 0.027 / 1.48 % and 0.12 / 0.035 / 1.79 %, so on 1 Gbit
  hosts PQ messages miss 540–1,850× less often than attestations. The no-PQ run on this build
  (`R20-nopq-rtt6-ps100-cf2-s1`) is queued; until it runs, comparisons with a no-PQ run are unmatched.
- **Who misses.** 11 incomplete 1 Gbit node·slots (never 4, near miss 5, late 2; rtt5b 41, rtt5 112, current build
  21): 6 in slots 2–15 and 5 in 16–19. 6 of 742 hosts are incomplete at least once (3 Prysm, 2 Lighthouse, 1 other),
  none in half the slots. The most frequent is 1732 (other, Seoul, 200 peers, 80 negative-score peers, 5 of 18
  slots). Of the hosts most often incomplete on rtt5b, 1960 (10 slots there) and 795 (7) are incomplete once here,
  794 (6) twice, and 344 and 640 (3 each) never.
- **Over the run.** 1 Gbit completion holds: mean 99.93 % in slots 2–7, 99.98 % in 8–13 and 99.84 % in 14–19 (rtt5b
  99.71, 99.73, 99.64 %; rtt5 99.48, 99.19, 98.81 %; current build 99.95, 99.86, 99.70 %). PQ message misses are
  0.0003, 0.0010 and 0.0028 % in the same blocks (rtt5b 0.0032, 0.0039, 0.0048 %; slots 15–19 include the P3 onset).
  On 1G→1G paths ssthresh after a restart stops falling: 398 at slot 2, 107 at slot 6, then 85–91 from slot 9 to 18
  (rtt5b 358 → 91 and rtt5 185 → 64 over slots 7–18). On paths with a home end it still falls, to higher values than on
  rtt5b: 1G→home 131 → 25, home→1G 139 → 37, home→home 89 → 14 (rtt5b 22 / 28 / 12 and rtt5 19 / 25 / 10 at slot 18).
  Block first-seen from publish, p95, is 2.0× the current-build b16 run's in slots 2–7 (0.70 against 0.35 s), 1.7× in
  8–13 (0.56 / 0.34 s) and 1.7× in 14–19 (0.60 / 0.34 s), within 3 % of rtt5b in each block and 4–12 % below rtt5, so
  the block slowdown does not grow as ssthresh falls, and CUBIC's growth does not shorten it. Per slot (slots 2–19;
  ssthresh slots 2–18, u = more than half of the restarts on connections that never reduced it; rtt5's and rtt5b's
  ssthresh rows are in their sections):

| series | per slot |
|---|---|
| block first-seen from publish p95, b16 current build (s) | 0.32 0.29 0.34 0.37 0.52 0.28 0.31 0.31 0.33 0.34 0.39 0.35 0.31 0.30 0.42 0.34 0.31 0.38 |
| block first-seen from publish p95, b16 rtt5 (s) | 0.79 0.75 0.78 0.75 0.96 0.66 0.68 0.49 0.69 0.64 0.61 0.39 0.69 0.59 0.68 0.64 0.59 0.88 |
| block first-seen from publish p95, b16 rtt5b (s) | 0.69 0.76 0.77 0.64 0.85 0.62 0.58 0.51 0.67 0.57 0.57 0.38 0.59 0.56 0.59 0.58 0.53 0.76 |
| block first-seen from publish p95, b16 rtt6 (s) | 0.78 0.69 0.75 0.60 0.81 0.58 0.65 0.48 0.62 0.66 0.55 0.41 0.61 0.57 0.58 0.53 0.53 0.75 |
| ssthresh p50 after a restart, 1G→1G | 398 170 128 116 107 98 95 90 87 91 88 90 88 86 85 86 87 |
| ssthresh p50 after a restart, 1G→home | u 131 66 49 40 35 33 30 29 28 27 27 26 25 25 25 25 |
| ssthresh p50 after a restart, home→1G | u u u 139 107 84 71 61 55 50 46 45 42 40 40 39 37 |
| ssthresh p50 after a restart, home→home | u u u 89 35 23 19 18 16 15 15 15 15 15 14 14 14 |
| 1 Gbit completion, b16 rtt5 (%) | 99.32 99.59 99.59 99.59 99.46 99.32 98.92 99.05 99.32 99.59 99.19 99.05 98.92 98.92 98.38 99.19 98.92 98.52 |
| 1 Gbit completion, b16 rtt5b (%) | 99.46 100 99.73 99.59 99.73 99.73 99.73 99.46 99.73 99.86 99.73 99.86 99.86 99.86 99.59 99.59 99.59 99.33 |
| 1 Gbit completion, b16 rtt6 (%) | 99.86 99.86 100 100 99.86 100 100 99.86 100 100 100 100 99.86 99.86 99.73 99.86 100 99.73 |
| 1 Gbit PQ messages missing at 8 s, b16 rtt5 (%) | 0.0074 0.0036 0.0030 0.0056 0.0099 0.0212 0.0162 0.0111 0.0070 0.0080 0.0126 0.0194 0.0198 0.0361 0.0276 0.0162 0.0143 0.0411 |
| 1 Gbit PQ messages missing at 8 s, b16 rtt5b (%) | 0.0091 0 0.0019 0.0021 0.0025 0.0034 0.0023 0.0078 0.0049 0.0010 0.0039 0.0036 0.0001 0.0016 0.0014 0.0069 0.0048 0.0139 |
| 1 Gbit PQ messages missing at 8 s, b16 rtt6 (%) | 0.0010 0.0002 0 0 0.0008 0 0 0.0059 0 0 0 0 0.0023 0.0012 0.0023 0.0056 0 0.0051 |

- **CUBIC and HyStart.** Data packets sent with cwnd ≥ ssthresh: 72.3 % (1G→1G), 68.9 % (1G→home), 68.3 % (home→1G)
  and 67.2 % (home→home), 70.4 % in all (64-host check: rtt6 79.7 %, rtt5 61.6 %; the counter exists only in the rtt6
  binary, so the 2,048-host rtt5 and rtt5b runs have none). HyStart exits, ack train / delay: 12,436 / 0 (1G→1G),
  1,558 / 2,623 (1G→home), 2,492 / 5,310 (home→1G), 0 / 4,024 (home→home), with cwnd at exit p50 (p90) 28 (185), 103 (219), 80
  (236) and 109 (240). Train exits fire on short paths (delay_min p50 2.7 ms; the ack train spans 2.0 ms at p50
  against a threshold of 1.8 ms), delay exits when the round's minimum RTT sample (curr_rtt) is 6.0 ms above
  delay_min at p50 (threshold 4.0 ms). Every logged window target (364,846 in 47,734 traced epochs) equals Linux's
  integer formula, origin ± (410 · |t − K|³ >> 40); written with C = 0.4 instead of 410/1024, 853 of them, with
  |t − K| up to 54 s, differ by more than one segment. No congestion-avoidance round grows by more than one segment
  per two packets ACKed, plus one, and all 345,767 traced epoch shifts at a send after idle equal
  min(epoch + idle, now).
- **P3** from slot 15: PQ 1,038 → 2,457 per slot (rtt5b 1,134 → 2,068, rtt5 1,387 → 2,424) and attestation 1,124 →
  370; block and aggregate 0. Per host, PQ / attestation: Lighthouse 5.43 / 1.81, other 17.53 / 1.40, Teku 2.88 /
  2.81, Lodestar 3.93 / 7.33, Nimbus 2.02 / 3.39, Prysm 0. Negative-score peers per observer: Lighthouse 12.6, other
  18.5; Teku, Lodestar, Nimbus and Prysm 0.12–0.15 (rtt5b 12.2, 18.5 and 0.13–0.18).
- **Latency** from publish, p50 / p99: 0.10 / 0.60 s (50/15), 0.09 / 0.58 s (50/25), 0.09 / 0.68 s (1 Gbit); rtt5b
  0.10 / 0.62, 0.10 / 0.59 and 0.09 / 0.78 s; rtt5 0.11 / 0.66, 0.10 / 0.68 and 0.10 / 0.96 s; current build 0.09 /
  0.49, 0.08 / 0.43 and 0.08 / 0.60 s.
- **κ** 8.8 → 9.9; PQ copies per message 3.86 → 4.66; IDONTWANT 9.8–14.1k ids per node per slot (rtt5b 8.8 → 9.9,
  3.85 → 4.64 and 9.7–13.6k).
- **Bandwidth in the 4 s window**, mean / max node, % of cap: upload 42 / 64 (50/15), 27 / 42 (50/25), 6 / 13
  (1 Gbit); download ≤ 14 / 22 (rtt5b within 2 points of these).
- **Backlog.** After-deadline PQ kB per 1 Gbit node per slot: 258 at slot 2, 810 at slot 8, then 852–1,056 over
  slots 9–19, +16.5 kB per slot over slots 10–19 (rtt5b +16.2, rtt5 +26.0, current build +30.2). Home hosts: 50/15
  21 → 48 kB, 50/25 18 → 37 kB, +1.3 and +1.1 kB per slot over slots 10–19 (rtt5b +1.6 / +0.9, rtt5 +2.5 / +2.3,
  current build +1.9 / +1.9). Messages first delivered after the deadline stay ≤ 0.05 per 1 Gbit node per slot and
  are 0 on home hosts, so these bytes are copies of messages already held; they grow at about rtt5b's rate, slower than on the current build (1 Gbit about half).
  Links per node 211–235 and connections 163–165 per node, flat. Negative-score peers peak at 22.3k in slot 5 and
  settle at 14.9–16.4k from slot 12.
  Failed sends that cost score: 131.0M (forward timeout 47.5 %, forward queue full 43.0 %, control queue full
  9.5 %; rtt5b 131.9M). Stale copies: PQ 0, background 396; bgexcess ≤ 1.008 on background topics. Churn
  removes 34 of 40,000 signatures; no refused publish.
- **TCP** (path types by sender → receiver):
  - Restarts after idle: about 1.5M per slot (1G→1G 250k, 1G→home 400k, home→1G 415k, home→home 430k), flat; median
    idle time 0.93–1.00 s against a median RTO of 0.29–0.36 s. cwnd before → after, p50 (p90): 12 (55) → 10 (16) on
    1G→1G and 10 (22–28) → 10 (10) elsewhere. 91 % of restarts leave cwnd below ssthresh, and all of those continue
    in slow start.
  - cwnd p50 / p90 over the run: 10 / 29 (1G→1G), 10 / 18 (1G→home), 10 / 19 (home→1G), 10 / 18 (home→home), as on
    rtt5b.
  - Fast-recovery entries per 1,000 data packets: 0.24 (1G→1G), 1.45 (1G→home), 1.42 (home→1G), 2.32 (home→home),
    all after consecutive duplicate ACKs.
  - Resends per 1,000 data packets, flat: 0.27, 3.37, 1.83 and 9.94. First timeouts per 1,000 data packets climb
    (slots 2 → 18): home→home 9.9 → 19.7, 1G→home 3.4 → 6.3, home→1G 0.80 → 2.21, 1G→1G 0.08 → 0.13, as on rtt5b.
    7.92M RTOs (rtt5b 7.90M); 96.5 % of Eifel checks found the timeout spurious and undid it, and 67 % of first
    timeouts start within 1 s after such an undo on the same connection; no stalls (6.95M snapshots); the RTO formula
    holds in all 6,374,580 snapshots without backoff; buffers start at 131,072 / 174,760 B on every connection.
- **Blocks:** none missing; from publish p50 / p95 / p99 0.33 / 0.65 / 0.84 s (rtt5b 0.34 / 0.67 / 0.85 s, rtt5
  0.34 / 0.74 / 0.93 s, current build 0.19 / 0.36 / 0.48 s). Attestations after 4 s p50 / p95 / p99 1.08 / 2.12 /
  3.64 s; 0.51 % never arrive (rtt5b 1.09 / 2.25 / 4.36 s and 0.58 %).
- **Memory and time.** Peak 218.5 GiB PSS; wall 10,923 s; TCP log 3.1 GB compressed.
- **Build rule.** The pass (decided 08:40 Nov 11) moved fs0-b16 and seed 2 of `L-pq-b16` to rtt6, queued the
  50-slot run `L-pq-b16-2k4-rtt6-ps100-cf2-s1` right after `R20-pq-2k4-rtt6-ps100-cf2-s1`, and queued
  `R20-nopq-rtt6-ps100-cf2-s1` last.
- **Reading.** With Linux's CUBIC and HyStart on top of rtt5, the bundled cell passes with more margin than on any
  other build, the current one included: 11 incomplete 1 Gbit node·slots and a worst slot of 99.73 %. Against rtt5b,
  which has CUBIC's decrease only, the gain is in completion (11 against 41 node·slots) and in the PQ tail (1 Gbit p99
  0.68 against 0.78 s), not in blocks (p95 0.65 against 0.67 s). Blocks stay 1.7–2.0× the current build's time, as
  on every build that restarts windows after idle; the 64-host rule split puts the whole block slowdown on that
  restart. Whether the pass holds over 50 slots is what `L-pq-b16-2k4-rtt6-ps100-cf2-s1` tests.

### 2,048 hosts × 20 slots, 2.4 kB, 16 signatures per message, rtt6, home stakers in 2 PQ subnets: `R20-pq-b16-2k4-2sub-rtt6-ps100-cf2-s1` (cf2)

For Yann's subnet question: `R20-pq-b16-2k4-rtt6-ps100-cf2-s1` (×1.0, `--msg-bytes 2458`, `--batch 16`, P3 rate
66.93, seed 1; the same generated network, background traffic and publish schedule) with `--staker-subnets 2`. Each
of the 976 home stakers (50/25 hosts with validators) joins its duty subnet, the one its signatures go to, plus one
other random PQ subnet, and counts as complete only with both subnets' messages. The 330 50/15 hosts (no validators)
stay in one subnet, the 742 1 Gbit hosts in all 16, and publishing is unchanged. PQ subscriptions rise by 976 (+7.4
%), to 861–903 subscribers per subnet (801–838 with one subnet). TCP logging. Completion per slot (%, slots 0–19):

| class | per slot |
|---|---|
| 50/15 | 100 in every slot |
| 50/25 (stakers, both subnets) | 100 in every slot |
| 1 Gbit | 99.59 99.86 99.86 99.59 99.86 99.86 100 99.86 99.86 100 99.73 99.86 99.86 100 99.86 100 99.86 99.86 100 100 |

- **Strict rule: PASS, with margin.** Every class is at 99 % or more in every slot from slot 2. Both home classes
  are complete in every slot, the stakers on both subnets (1.82M needed staker·message pairs in slots 2–15, against
  0.91M with one subnet). The worst slot is slot 3 at 99.59 % on 1 Gbit hosts (3 of 742; the rule allows 7). Slots
  2–15 average 100 / 100 / 99.87 %, slots 16–19 100 / 100 / 99.93 % (one subnet: 99.94 and 99.83 %, worst 99.73 %).
  Messages first delivered after the deadline stay ≤ 0.02 per 1 Gbit node per slot and are 0 on home hosts, so no
  backlog builds.
- **PQ vs BLS.** PQ messages missing at 8 s on 1 Gbit hosts: 0.0005 % (slots 2–15) and 0.0004 % (16–19), against
  0.0008 and 0.0033 % with one subnet; home hosts miss none. BLS attestations missing in the same run: 0.11 / 0.061
  / 1.79 % and 0.009 / 0.048 / 1.47 % (one subnet 0.029 / 0.027 / 1.48 % and 0.12 / 0.035 / 1.79 %). The home
  differences change sign between the two slot ranges, so the second subnet shows no consistent effect on
  attestations. Comparisons with a no-PQ run stay unmatched until `R20-nopq-rtt6-ps100-cf2-s1` runs.
- **Who misses.** 15 incomplete 1 Gbit node·slots (never 3, near miss 9, late 3; one subnet 11). 9 of 742 hosts are
  incomplete at least once, none in more than 4 of 18 slots: 1960 (Prysm, São Paulo) 4, 1860 (Lighthouse, São Paulo)
  3, 795 (Lighthouse, Sydney) 2. No chronic host.
- **Latency** from publish, p50 / p99: 0.10 / 0.64 s (50/15), 0.11 / 0.79 s (stakers, both subnets), 0.09 / 0.73 s
  (1 Gbit); one subnet 0.10 / 0.60, 0.09 / 0.58 and 0.09 / 0.68 s.

Home upload in the PQ publishing window (`upwin.py`, slots 2–19; % of the upload cap, mean over the class / busiest
node by its mean over the slots). The no-PQ column is `R20-nopq-rtt5-ps100-cf2-s1`, the same network and seed on
rtt5, so it is not build-matched; the rtt6 no-PQ run comes last in the queue:

| class | window | 2 subnets | 1 subnet | no PQ (rtt5) |
|---|---|---|---|---|
| 50/25 (stakers) | 4–8 s | 37.8 / 57.8 | 26.7 / 42.4 | 13.4 / 21.5 |
| 50/25 (stakers) | 4.0–5.0 s | 110.3 / 189.1 | 77.2 / 125.1 | 30.7 / 54.2 |
| 50/15 | 4–8 s | 42.4 / 67.3 | 41.6 / 63.8 | 21.6 / 32.9 |
| 50/15 | 4.0–5.0 s | 119.1 / 207.2 | 118.1 / 186.9 | 48.9 / 81.5 |
| 1 Gbit | 4–8 s | 6.0 / 13.6 | 5.6 / 13.2 | 1.3 / 9.1 |
| 1 Gbit | 4.0–5.0 s | 18.6 / 33.6 | 17.5 / 32.1 | 2.4 / 18.0 |

The busiest staker in the two-subnet cell (host 1135) sends 57.8 % of its cap in 4–8 s and 189 % in 4.0–5.0 s,
against 10.7 and 23.7 % in the no-PQ run; with one subnet the busiest stakers were 319 in 4–8 s (42.4 %; 19.0 %
without PQ) and 1828 in 4.0–5.0 s (125 %; 42.6 %). PQ makes up 65 % of staker upload in 4–8 s and 72 % in 4.0–5.0 s
(one subnet 50 and 60 %). Above 100 % in 4.0–5.0 s means a node queued more than its link carries in that second;
the 4–8 s figures show the queue drains within the window. The second subnet adds 11.1 points in 4–8 s, 83 % of the
one-subnet PQ part (13.4 points), and 33.1 points in 4.0–5.0 s, 71 % of it. So doubling the PQ part overstates the
rise: the first-order doubling of the current-build unbundled figures gave 44 / 69 % (4–8 s) and 135 / 218 %
(4.0–5.0 s), and the same doubling of the one-subnet cell gives 40 / 66 % and 124 / 208 %, against the measured 37.8
/ 57.8 % and 110 / 189 %. Stakers' PQ mesh per joined topic shrinks from 7.11 to 6.55 peers. Staker download in the
4 s window: 21 / 33 % of 50 Mbit/s (one subnet 13 / 22 %). The 50/15 and 1 Gbit means change by about a point; the
busiest 50/15 node rises from 63.8 to 67.3 % (4–8 s) and from 187 to 207 % (4.0–5.0 s).

- **Failed sends** per host per slot, timed out / queue full (slots 2–19): stakers 1,016 / 4 (one subnet 900 / 1),
  50/15 1,160 / 2 (1,168 / 0), 1 Gbit 2,330 / 4,646 (2,268 / 4,465). In all 136.9M (131.0M, +4.5 %): forward timeout
  47.9 %, forward queue full 43.0 %, control queue full 9.0 %. On home hosts 99–100 % are forward timeouts.
- **Negative-score peers** per observer, slots 2–19 mean / slot 19: stakers 8.2 / 7.3 (one subnet 6.7 / 6.3), 50/15
  9.4 / 8.5 (9.4 / 8.2), 1 Gbit 11.6 / 8.9 (10.4 / 8.6). Of the connections to staker peers 5.44 % are negative
  (4.29 %), to 50/15 peers 5.60 % (5.60 %), to 1 Gbit peers 6.61 % (6.08 %). By observer client: Lighthouse 14.3,
  other 21.8, Teku, Lodestar, Nimbus and Prysm 0.12–0.16 (12.6, 18.5 and 0.12–0.15). In all they peak at 25.9k in
  slot 5 and settle at 16.1–18.4k from slot 12 (22.3k and 14.9–16.4k). P3 from slot 15, PQ / attestation per host:
  Lighthouse 3.69 / 0.69, other 13.88 / 2.88, Teku 1.78 / 3.38, Lodestar 0.29 / 3.28, Nimbus 3.71 / 5.07, Prysm 0.
- **Cost.** From slot 2 to 19, κ 9.33 → 9.92 (one subnet 9.40 → 9.85), PQ copies per message 4.69 → 4.96 (4.41 →
  4.66), IDONTWANT 14.3k → 15.7k ids per node per slot (12.4k → 13.6k). After-deadline PQ kB per node per slot over
  slots 9–19: stakers 116–160 kB, +3.1 kB per slot over slots 10–19 (one subnet 27–38, +1.1), 50/15 35–64, +2.3
  (32–48, +1.3), 1 Gbit 930–1,148, +13.1 (852–1,056, +16.5); these are copies of messages already held, a reported
  cost. Links per node 213–237; PQ mesh per joined topic 6.65 (50/15), 6.55 (stakers) and 7.16 (1 Gbit), against
  6.70, 7.11 and 7.06. Stale copies (older than 60 s), summed over hosts and slots: PQ 448, background 1,082 (0 and
  396), about 0.01 per node per slot; bgexcess ≤ 1.008 on background topics. Churn removes 34 of 40,000 signatures;
  no refused publish.
- **Blocks:** none missing; from publish p50 / p95 / p99 0.34 / 0.68 / 0.86 s (one subnet 0.33 / 0.65 / 0.84 s), p95
  per 6-slot block 0.71 / 0.57 / 0.61 s (0.70 / 0.56 / 0.59 s). Attestations after 4 s p50 / p95 / p99 1.11 / 2.26 /
  3.82 s; 0.54 % never arrive (1.08 / 2.12 / 3.64 s and 0.51 %).
- **Over the run.** 1 Gbit completion holds: 99.84 % in slots 2–7, 99.89 % in 8–13 and 99.93 % in 14–19 (one subnet
  99.93, 99.98 and 99.84 %), and PQ message misses stay near 0.0005 % in each block (one subnet 0.0003, 0.0010 and
  0.0028 %). Block p95 from publish does not grow. ssthresh after a restart falls as with one subnet, ending
  slightly lower on paths to home hosts: at slot 18, 85 (1G→1G), 21 (1G→home), 39 (home→1G) and 13 (home→home),
  against 87, 25, 37 and 14. Per slot (slots 2–19; ssthresh slots 2–18, u = more than half of the restarts on
  connections that never reduced it; the one-subnet ssthresh rows are in its section):

| series | per slot |
|---|---|
| 1 Gbit completion, 2 subnets (%) | 99.86 99.59 99.86 99.86 100 99.86 99.86 100 99.73 99.86 99.86 100 99.86 100 99.86 99.86 100 100 |
| 1 Gbit completion, 1 subnet (%) | 99.86 99.86 100 100 99.86 100 100 99.86 100 100 100 100 99.86 99.86 99.73 99.86 100 99.73 |
| 1 Gbit PQ messages missing at 8 s, 2 subnets (%) | 0.0001 0.0011 0.0004 0.0011 0 0.0003 0.0001 0 0.0017 0.0010 0.0006 0 0.0009 0 0.0001 0.0017 0 0 |
| 1 Gbit PQ messages missing at 8 s, 1 subnet (%) | 0.0010 0.0002 0 0 0.0008 0 0 0.0059 0 0 0 0 0.0023 0.0012 0.0023 0.0056 0 0.0051 |
| late first deliveries per 1 Gbit node, 2 subnets | 0.00 0.01 0.00 0.01 0.00 0.00 0.00 0.00 0.02 0.00 0.01 0.00 0.01 0.00 0.00 0.02 0.00 0.00 |
| block first-seen from publish p95, 2 subnets (s) | 0.75 0.70 0.74 0.63 0.84 0.58 0.68 0.49 0.62 0.63 0.56 0.44 0.57 0.55 0.65 0.56 0.53 0.83 |
| block first-seen from publish p95, 1 subnet (s) | 0.78 0.69 0.75 0.60 0.81 0.58 0.65 0.48 0.62 0.66 0.55 0.41 0.61 0.57 0.58 0.53 0.53 0.75 |
| ssthresh p50 after a restart, 1G→1G | 512 174 132 117 109 100 99 95 92 91 88 87 87 84 85 84 85 |
| ssthresh p50 after a restart, 1G→home | 98 53 36 31 28 25 25 24 23 22 22 22 21 21 21 21 21 |
| ssthresh p50 after a restart, home→1G | u u 156 110 88 74 67 59 53 49 46 45 43 42 40 39 39 |
| ssthresh p50 after a restart, home→home | u u 67 27 21 17 15 15 15 14 14 14 13 13 13 13 13 |

- **TCP** (path types by sender → receiver; one subnet in parentheses): cwnd p50 / p90 over the run 10 / 29 (1G→1G),
  10 / 20 (1G→home), 10 / 21 (home→1G) and 10 / 18 (home→home) (10 / 29, 10 / 18, 10 / 19, 10 / 18). Restarts after
  idle about 1.5M per slot, as with one subnet; 90 % leave cwnd below ssthresh, and all of those continue in slow
  start. Data packets sent with cwnd ≥ ssthresh: 72.7, 73.7, 71.2 and 70.4 %, 72.3 % in all (70.4 %). HyStart exits,
  ack train / delay: 12,090 / 0, 1,426 / 5,544, 2,338 / 12,250 and 2 / 5,496 (12,436 / 0, 1,558 / 2,623, 2,492 /
  5,310, 0 / 4,024), so delay exits double on paths between 1 Gbit and home hosts. First timeouts per 1,000 data
  packets, slot 2 → 18: 1G→home 4.8 → 8.1 (3.4 → 6.3), home→1G 1.03 → 2.68 (0.80 → 2.21), home→home 12.0 → 20.2 (9.9
  → 19.7), 1G→1G 0.08 → 0.12 (0.08 → 0.13). 10.69M RTOs (7.92M, +35 %); 96.9 % of 6.11M Eifel checks found the
  timeout spurious and undid it (96.5 %), and 68.8 % of first timeouts start within 1 s after such an undo on the
  same connection (67 %). Fast-recovery entries per 1,000 data packets 0.24, 1.47, 1.43 and 2.38, all after
  consecutive duplicate ACKs (0.24, 1.45, 1.42, 2.32); retransmissions 0.55 % of data packets (0.48 %). No stalls
  (6.97M snapshots); the RTO formula holds in all 6,297,405 snapshots without backoff.
- **Memory and time.** Peak 224.8 GiB PSS (one subnet 218.5); wall 10,973 s (10,923 s).
- **Reading.** A second PQ subnet per home staker keeps every class complete. Stakers hold both subnets' messages in
  every slot, and the 1 Gbit hosts keep their margin: 15 incomplete node·slots against 11, worst slot 99.59 against
  99.73 %, PQ misses no higher. The cost falls on the stakers: in the 4–8 s window their upload rises from 27 to 38
  % of the 25 Mbit/s cap on average and from 42 to 58 % at the busiest node; in the first second after publish it
  runs at 110 % of the cap on average (77 % with one subnet) and 189 % at the busiest node, a queue that drains
  within the window; their PQ p99 rises from 0.58 to 0.79 s. Blocks, attestations and the 50/15 hosts barely change.
  RTOs rise by 35 %, nearly all still spurious.

### 2,048 hosts × 20 slots, 2.4 kB, 16 signatures per message, rtt6, today's attestation-subnet structure: `R20-pq-b16-2k4-bb2-rtt6-ps100-cf2-s1` (cf2)

For Yann's subnet question, the structure of today's attestation subnets: `R20-pq-b16-2k4-rtt6-ps100-cf2-s1` (same
flags, network, background traffic and publish schedule) with `--backbone-subnets 2`. Every home node, 50/25 and
50/15, joins 2 random backbone PQ subnets, and each staker also joins its duty subnet, the one its signatures go to:
843 stakers end up in 3 subnets and 133 in 2 (their duty subnet is one of the backbone ones), and the 330 50/15
hosts in 2. The 742 1 Gbit hosts stay in all 16, and publishing is unchanged. A staker counts as complete with its
duty subnet's messages, a 50/15 host with both of its subnets' messages; stakers' completeness on every subscribed
subnet is given too (`PQ_NEED=all`). PQ subscriptions rise by 2,149 (+16.3 %), to 938–985 subscribers per subnet.
TCP logging; the watchdog cap was 238 GiB for this run (coordinator 03:5x Nov 12). Completion per slot (%, slots
0–19):

| class | per slot |
|---|---|
| 50/15 (both subnets) | 98.48 99.09 99.09 100 100 100 100 100 100 100 99.70 100 100 100 100 100 100 100 100 100 |
| 50/25 stakers, duty subnet | 100 except 99.90 in slots 9 and 16 |
| 50/25 stakers, every subscribed subnet | 100 except 99.90 in slots 2, 9, 11, 16 and 19 |
| 1 Gbit | 99.32 99.59 99.32 99.86 100 99.86 100 100 100 100 100 100 99.86 99.86 99.86 99.86 99.86 100 100 99.87 |

- **Strict rule: PASS, at the limit for 50/15 hosts.** Every class is at 99 % or more in every slot from slot 2.
  50/15 hosts reach 99.09 % in slot 2 (3 of 330; the rule allows 3), the tail of a start-up dip (98.48 and 99.09 %
  in slots 0–1), and miss in one node·slot after that (slot 10). Stakers miss in 2 node·slots on their duty subnet
  (99.99 % in slots 2–15, 99.97 % in 16–19) and in 5 on every subscribed subnet (99.98 and 99.95 %). 1 Gbit hosts
  average 99.89 % (slots 2–15) and 99.93 % (16–19), worst slot 2 at 99.32 % (5 of ~740; the rule allows 7). Messages
  first delivered after the deadline stay ≤ 0.07 per 1 Gbit node per slot (slot 2) and ≤ 0.02 on home hosts, without
  a rise, so the backlog is flat.
- **PQ vs BLS.** PQ messages missing at 8 s, 50/15 / stakers / 1 Gbit: 0.0016 / 0.0002 / 0.0007 % (slots 2–15) and 0
  / 0.0008 / 0.0012 % (16–19); on every subscribed subnet stakers miss 0.0003 and 0.0011 %. BLS attestations missing
  in the same run: 0.11 / 0.15 / 1.23 % and 0.17 / 0.079 / 1.42 % (one subnet 0.029 / 0.027 / 1.48 and 0.12 / 0.035
  / 1.79 %): higher on home hosts in both slot ranges, though still ≤ 0.17 %. Comparisons with a no-PQ run stay
  unmatched until `R20-nopq-rtt6-ps100-cf2-s1` runs.
- **Who misses.** Home misses are near misses: 50/15 4 node·slots (3 within 1 s of the deadline, 1 later), stakers 2
  (1 and 1). 13 incomplete 1 Gbit node·slots (never 1, near miss 8, late 4; one subnet 11, two-subnet cell 15); 10
  of 742 hosts are incomplete at least once, none in more than 3 slots (719, Lighthouse, Sydney); no chronic host.
- **Latency** from publish, p50 / p99: 0.13 / 1.06 s (50/15), 0.13 / 0.97 s (stakers), 0.09 / 0.70 s (1 Gbit); one
  subnet 0.10 / 0.60, 0.09 / 0.58 and 0.09 / 0.68 s; two-subnet cell 0.10 / 0.64, 0.11 / 0.79 and 0.09 / 0.73 s.

Upload in the PQ publishing window (`upwin.py`, slots 2–19; % of the upload cap, mean over the class / busiest node
by its mean over the slots, and in brackets the largest single node·slot; the no-PQ column is
`R20-nopq-rtt5-ps100-cf2-s1`, not build-matched):

| class | window | 1 subnet | stakers in 2 | today's structure | no PQ (rtt5) |
|---|---|---|---|---|---|
| 50/15 | 4–8 s | 41.6 / 63.8 [87] | 42.4 / 67.3 [90] | 58.5 / 90.0 [127] | 21.6 / 32.9 |
| 50/15 | 4.0–5.0 s | 118.1 / 186.9 [278] | 119.1 / 207.2 [276] | 164.0 / 270.7 [394] | 48.9 / 81.5 |
| 50/25 (stakers) | 4–8 s | 26.7 / 42.4 [54] | 37.8 / 57.8 [77] | 46.4 / 74.2 [101] | 13.4 / 21.5 |
| 50/25 (stakers) | 4.0–5.0 s | 77.2 / 125.1 [177] | 110.3 / 189.1 [261] | 131.6 / 224.5 [327] | 30.7 / 54.2 |
| 1 Gbit | 4–8 s | 5.6 / 13.2 [23] | 6.0 / 13.6 [26] | 6.3 / 16.3 [22] | 1.3 / 9.1 |
| 1 Gbit | 4.0–5.0 s | 17.5 / 32.1 [44] | 18.6 / 33.6 [38] | 19.2 / 40.3 [46] | 2.4 / 18.0 |

Each extra subnet adds about 80 % of the one-subnet PQ upload in 4–8 s: 84 % for the 50/15 hosts and 79 % per extra
subnet for the stakers (2.86 subnets each on average), against 83 % in the two-subnet cell; in 4.0–5.0 s 63–71 %.
The 15 Mbit/s home nodes without validators carry the most: 58 % of their uplink on average over 4–8 s and 90 % at
the busiest node (1985; 24.6 % without PQ). In the worst node·slot a 50/15 node had 127 % of the window's capacity
to send, so its queue ran past 8 s; in the first second after publish 50/15 hosts average 164 % and peak at 394 %.
The busiest staker sends 74.2 % in 4–8 s (506; 18.5 % without PQ) and 224.5 % in 4.0–5.0 s (185; 47.9 %). Download
in the 4 s window: 50/15 21 / 37 %, stakers 27 / 45 % of 50 Mbit/s (one subnet 14 / 22 and 13 / 22 %). 1 Gbit hosts
change by 0.7 (4–8 s) and 1.7 points (4.0–5.0 s) on average.

- **Failed sends** per host per slot, timed out / queue full (slots 2–19): 50/15 1,275 / 18 (one subnet 1,168 / 0),
  stakers 1,124 / 25 (900 / 1), 1 Gbit 2,444 / 4,476 (2,268 / 4,465); 140.8M in all (131.0M, +7.5 %): forward
  timeout 50.5 %, forward queue full 42.1 %, control queue full 7.4 %. On home hosts with non-Rust clients, 2.0–2.1
  % of failed sends are full forward queues and 1.0–1.9 % full control queues (one subnet ≤ 0.1 %); the rest are
  timeouts.
- **Negative-score peers** per observer, slots 2–19 mean / slot 19: 50/15 12.3 / 9.1 (one subnet 9.4 / 8.2), stakers
  10.4 / 8.3 (6.7 / 6.3), 1 Gbit 14.4 / 10.6 (10.4 / 8.6). Of the connections to 50/15 peers 7.78 % are negative
  (5.60 %), to staker peers 6.91 % (4.29 %), to 1 Gbit peers 7.86 % (6.08 %). By observer client: Lighthouse 17.8,
  other 29.4, Teku, Lodestar, Nimbus and Prysm 0.10–0.15 (12.6, 18.5 and 0.12–0.15). In all they peak at 33.7k in
  slot 5 and settle at 18.3–22.6k from slot 12 (22.3k and 14.9–16.4k). P3 from slot 15, PQ / attestation per host:
  Lighthouse 3.38 / 1.00, other 14.20 / 1.13, Teku 3.28 / 4.24, Lodestar 3.14 / 3.34, Nimbus 3.31 / 5.54, Prysm 0.
- **Cost.** From slot 2 to 19, κ 8.97 → 9.73 (one subnet 9.40 → 9.85), PQ copies per message 4.72 → 5.10 (4.41 →
  4.66), IDONTWANT 15.7k → 17.7k ids per node per slot (12.4k → 13.6k). After-deadline PQ kB per node per slot over
  slots 9–19, and the slope over slots 10–19: 50/15 162–242 kB, +6.6 kB per slot (one subnet 32–48, +1.3), stakers
  237–340, +10.0 (27–38, +1.1), 1 Gbit 917–1,251, +29.8 (852–1,056, +16.5). These are copies of messages already
  held, a reported cost, but they grow faster than with one subnet in every class. Links per node 216–244; PQ mesh
  per joined topic 6.12 (50/15), 6.27 (stakers) and 7.30 (1 Gbit), against 6.70, 7.11 and 7.06: home meshes sit
  close to D_lo = 6. Stale copies (older than 60 s), summed over hosts and slots: PQ 6, background 4,612 (one subnet
  0 and 396), 0.13 per node per slot; bgexcess ≤ 1.008 on background topics. Churn removes 34 of 40,000 signatures;
  no refused publish.
- **Blocks:** none missing; from publish p50 / p95 / p99 0.32 / 0.67 / 0.88 s (one subnet 0.33 / 0.65 / 0.84 s), p95
  per 6-slot block 0.73 / 0.53 / 0.61 s (0.70 / 0.56 / 0.59 s). Attestations after 4 s p50 / p95 / p99 1.11 / 2.20 /
  3.57 s; 0.39 % never arrive (1.08 / 2.12 / 3.64 s and 0.51 %).
- **Over the run.** 1 Gbit completion: 99.84 % in slots 2–7, 99.95 % in 8–13 and 99.91 % in 14–19 (one subnet 99.93,
  99.98 and 99.84 %); PQ message misses 0.0011, 0.0004 and 0.0010 % (0.0003, 0.0010 and 0.0028 %). Home misses fall
  in slots 2, 9, 10 and 16. Block p95 from publish does not grow. ssthresh after a restart ends where it ends with
  one subnet on 1G→1G and home→1G, and a little lower on the other paths: at slot 18, 86 (1G→1G), 18 (1G→home), 39
  (home→1G) and 12 (home→home), against 87, 25, 37 and 14. Per slot (slots 2–19; ssthresh slots 2–18, u = more than
  half of the restarts on connections that never reduced it; the other cells' rows are in their sections):

| series | per slot |
|---|---|
| 50/15 completion (%) | 99.09 100 100 100 100 100 100 100 99.70 100 100 100 100 100 100 100 100 100 |
| 1 Gbit completion (%) | 99.32 99.86 100 99.86 100 100 100 100 100 100 99.86 99.86 99.86 99.86 99.86 100 100 99.87 |
| 1 Gbit PQ messages missing at 8 s (%) | 0.0062 0.0001 0 0.0002 0 0 0 0 0 0 0.0013 0.0009 0.0001 0.0009 0.0023 0 0 0.0024 |
| late first deliveries per 1 Gbit node | 0.07 0.00 0.00 0.00 0.00 0.00 0.00 0.00 0.00 0.00 0.01 0.01 0.00 0.01 0.02 0.00 0.00 0.03 |
| block first-seen from publish p95 (s) | 0.76 0.71 0.69 0.70 0.85 0.66 0.58 0.50 0.53 0.62 0.56 0.37 0.57 0.55 0.55 0.57 0.51 0.92 |
| ssthresh p50 after a restart, 1G→1G | u 178 133 118 110 97 94 93 90 88 84 86 85 87 85 85 86 |
| ssthresh p50 after a restart, 1G→home | 55 36 27 24 23 21 21 21 20 19 19 19 18 18 18 18 18 |
| ssthresh p50 after a restart, home→1G | u 200 117 90 78 66 61 56 51 48 46 46 44 42 42 40 39 |
| ssthresh p50 after a restart, home→home | u 73 24 18 16 15 14 13 13 12 12 12 12 12 12 11 12 |

- **TCP** (path types by sender → receiver; one subnet in parentheses): cwnd p50 / p90 over the run 10 / 30 (1G→1G),
  10 / 23 (1G→home), 10 / 23 (home→1G), 10 / 19 (home→home) (one subnet 10 / 29, 10 / 18, 10 / 19, 10 / 18).
  Restarts after idle about 1.5M per slot; 90 % leave cwnd below ssthresh, and all of those continue in slow start.
  First timeouts per 1,000 data packets, slot 2 → 18: 1G→home 6.3 → 9.2 (one subnet 3.4 → 6.3), home→1G 1.28 → 3.20
  (0.80 → 2.21), home→home 12.8 → 19.6 (9.9 → 19.7), 1G→1G 0.07 → 0.12 (0.08 → 0.13). Fast-recovery entries per
  1,000 data packets 0.23, 1.55, 1.49 and 2.45, all after consecutive duplicate ACKs (0.24, 1.45, 1.42, 2.32). Data
  packets sent with cwnd ≥ ssthresh: 72.2, 76.5, 71.6 and 74.7 %, 73.4 % in all (one subnet 70.4 %, two-subnet cell
  72.3 %). HyStart exits, ack train / delay: 12,015 / 0, 1,263 / 7,028, 1,981 / 18,276 and 2 / 8,345 (12,436 / 0,
  1,558 / 2,623, 2,492 / 5,310, 0 / 4,024), so delay exits rise 2.1–3.4× on paths with a home end; cwnd at exit p50
  (p90) 28 (176), 131 (243), 82 (224) and 106 (223). 13.36M RTOs (one subnet 7.92M, two-subnet cell 10.69M); 96.7 %
  of 7.76M Eifel checks found the timeout spurious and undid it, and 67.9 % of first timeouts start within 1 s after
  such an undo on the same connection. Retransmissions 0.66 % of data packets (0.48 %). No stalls (7.00M snapshots);
  the RTO formula holds in all 6,218,264 snapshots without backoff.
- **Memory and time.** Peak 232.9 GiB PSS (one subnet 218.5, two-subnet cell 224.8), under the 238 GiB cap set for
  this run; wall 11,317 s (10,923 and 10,973 s).
- **Reading.** Today's structure still passes the strict rule, but with the least margin of the three subnet cells,
  and the pressure moves to the 15 Mbit/s home nodes without validators, which now carry two subnets: they are at
  the rule's limit in slot 2 (near misses at the end of a start-up dip), use 58 % of their uplink on average in the
  4–8 s window and 90 % at the busiest node, and in their worst node·slot had more to send than the window allows.
  Home PQ p99 reaches about 1 s, home meshes sit near D_lo, negative-score peers rise by a third to a half, full
  queues appear at home hosts with non-Rust clients, and late copies grow faster. Each extra subnet a home node
  joins adds about 80 % of the one-subnet PQ upload. One seed and 20 slots (P3 from slot 15).

### 2,048 hosts × 20 slots, 2.4 kB, window validation only (rtt5 binary, `RTT5_SSR=0`): `R20-pq-2k4-cwv-ps100-cf2-s1` (cf2)

The headline cell (×1.0, `--msg-bytes 2458`, seed 1, the same flags and generated network) on the rtt5 binary with
window validation and consecutive duplicate-ACK counting but no restart after idle (`RTT5_CWV=1 RTT5_SSR=0
RTT5_DUP=1`). That is Linux with `net.ipv4.tcp_slow_start_after_idle=0`, a real configuration that rtt4 only
approximates: on the 64-host check the two matched closely, but rtt4's 1G→1G cwnd p90 was 16,967 segments against
254. TCP logging on. Completion per slot (%, slots 0–19):

| class | per slot |
|---|---|
| 50/15 | 100 in every slot |
| 50/25 | 100 in every slot |
| 1 Gbit | 99.32 99.73 99.59 100 100 100 100 99.86 99.86 99.46 99.59 99.73 99.32 99.46 99.73 99.86 99.32 99.46 99.05 99.19 |

- **Strict rule: PASS, with no host to spare.** The worst slot is 18 at 99.05 % (7 of ~740 1 Gbit hosts incomplete;
  the rule allows 7). rtt4's worst slots had 5 (2 to spare); rtt5's had about 15. Slots 2–15 average 100 / 100 /
  99.75 %, slots 16–19 100 / 100 / 99.26 % (rtt4 99.87 and 99.46 %, rtt5 98.80 and 98.65 %). 1 Gbit completion
  declines over the run: 99.91 % in slots 2–7, 99.57 % in 8–13 and 99.44 % in 14–19 (rtt4 99.93, 99.82 and 99.59 %).
- **Who misses.** 48 incomplete 1 Gbit node·slots (never 10, near miss 25, late 13; rtt4 29, rtt5 164): 26 in slots
  2–15 and 22 in 16–19. 19 of 742 hosts are incomplete at least once (rtt4 12, rtt5 32), 11 in two or more slots (8
  Prysm, 3 Lighthouse), none in 9 or more; most often 939 (Prysm, Seoul, 8 of 18), 803 (Prysm, São Paulo, 6), 1960
  (Prysm, São Paulo, 4) and 211 (Prysm, Tokyo, 4). 1960, 211 and 988 (Prysm, São Paulo) miss nothing before slot 16
  and then 6–208 messages per slot, after P3 starts in slot 15. The failure mode is rtt5's and fs0's, far-region Prysm
  hosts with 70 peers, in fewer slots.
- **PQ vs BLS.** PQ messages missing at 8 s on 1 Gbit hosts: 0.0032 % (slots 2–15) and 0.020 % (16–19), against
  0.0014 / 0.020 % on rtt4 and 0.032 / 0.051 % on rtt5; home hosts miss none. BLS attestations missing in the same
  run: 0.14 / 0.16 / 2.01 % and 0.030 / 0.10 / 2.48 % (rtt4 0.23 / 0.25 / 1.48 and 0.008 / 0.074 / 1.35 %), so on
  1 Gbit hosts PQ messages miss 120–600× less often than attestations. There is no no-PQ run on this build, so the PQ
  share of the BLS misses is not measured here.
- **Over the run.** 1 Gbit PQ misses rise from 0.001 % (slots 2–7) to 0.006 % (8–13) and 0.014 % (14–19; rtt5 0.019,
  0.035 and 0.056 %). Block first-seen p95 from publish is 1.07× rtt4's in slots 2–7 and 1.14× in 8–13 and 14–19
  (0.39 / 0.37 / 0.41 s against 0.37 / 0.33 / 0.36 s; rtt5 0.79 / 0.56 / 0.63 s). Per slot (slots 2–19):

| series | per slot |
|---|---|
| block first-seen from publish p95, rtt4 (s) | 0.33 0.31 0.37 0.37 0.50 0.32 0.30 0.32 0.31 0.36 0.38 0.29 0.33 0.29 0.42 0.36 0.31 0.46 |
| block first-seen from publish p95, rtt5 (s) | 0.80 0.79 0.85 0.71 0.93 0.66 0.69 0.48 0.53 0.64 0.60 0.40 0.62 0.51 0.62 0.59 0.58 0.88 |
| block first-seen from publish p95, cwv (s) | 0.38 0.31 0.40 0.37 0.52 0.37 0.40 0.33 0.34 0.44 0.40 0.32 0.35 0.32 0.44 0.40 0.34 0.63 |
| 1 Gbit completion, cwv (%) | 99.59 100 100 100 100 99.86 99.86 99.46 99.59 99.73 99.32 99.46 99.73 99.86 99.32 99.46 99.05 99.19 |
| 1 Gbit PQ messages missing at 8 s, cwv (%) | 0.006 0 0 0 0 0.003 0.000 0.003 0.015 0.002 0.009 0.004 0.002 0.001 0.025 0.023 0.019 0.014 |

- **Latency** from publish, p50 / p99: 0.10 / 0.62 s (50/15), 0.10 / 0.59 s (50/25), 0.09 / 0.76 s (1 Gbit); rtt4
  0.10 / 0.64, 0.09 / 0.51 and 0.09 / 0.68 s; rtt5 0.15 / 0.84, 0.14 / 0.82 and 0.13 / 1.18 s.
- **κ** 9.1 → 10.1; PQ copies per message 3.6 → 4.4; IDONTWANT 15–22k ids per node per slot.
- **Bandwidth in the 4 s window**, mean / max node, % of cap: upload 45 / 70 (50/15), 29 / 43 (50/25), 6 / 13
  (1 Gbit); download ≤ 15 / 23.
- **Backlog.** After-deadline PQ kB per 1 Gbit node per slot: 189 → 938 by slot 9, then 867–1,042 (rtt4 132 →
  1,067–1,188 from slot 12), duplicates (messages first delivered after the deadline: 0.05 per node per slot in slots 2–15, 0.37 in
  16–19, at most 0.45); home hosts 13 → 64–78 kB, still
  rising by about 3 kB per slot (rtt4 50/25 12 → 55, rtt5 20 → 93). Links per node 210–233 and connections 163–165 per
  node, flat. Negative-score peers peak at 26.3k in slots 4–5 and settle at 17.5–21k from slot 8. Failed sends that
  cost score: 205.1M (forward timeout 36.0 %, forward queue full 36.8 %, control queue full 27.1 %; rtt4 200.0M, rtt5
  217.4M). Stale copies: PQ 222, background 13,901; bgexcess ≤ 1.008. Churn removes 34 of 40,000 signatures; no
  refused publish.
- **P3** from slot 15: PQ 412–528 per slot and attestation 1,086 → 166; block and aggregate 0. Per host, PQ /
  attestation: Lighthouse 1.10 / 0.71, other 2.38 / 1.17, Teku 1.42 / 4.49, Lodestar 2.78 / 5.14, Nimbus 2.54 / 3.98,
  Prysm 0. Negative-score peers per observer: Lighthouse 14.7, other 22.0; Teku, Lodestar, Nimbus and Prysm
  0.14–0.23.
- **Blocks:** none missing; from publish p50 / p95 / p99 0.22 / 0.42 / 0.57 s (rtt4 0.19 / 0.37 / 0.48 s, rtt5 0.34
  / 0.73 / 0.93 s). Attestations after 4 s p50 / p95 / p99 1.07 / 2.17 / 3.92 s; 0.83 % never arrive (rtt4 0.53 %,
  rtt5 0.85 %).
- **TCP** (path types by sender → receiver):
  - No restarts after idle (switched off). cwnd p50 / p90 over the run: 76 / 239 (1G→1G), 37 / 125 (1G→home),
    37 / 97 (home→1G), 21 / 52 (home→home); rtt4 300 / 9,438, 63 / 482, 97 / 562 and 38 / 277; rtt5 10 / 35, 10 / 19,
    10 / 19 and 10 / 16. The same endpoints' cwnd p50 falls from slot 2 to slot 19: 100 → 69, 54 → 29, 43 → 32 and
    36 → 19 (rtt4 368 → 153, 129 → 42, 134 → 46 and 105 → 26).
  - Fast-recovery entries per 1,000 data packets: 0.20, 1.43, 1.40, 2.32, all after consecutive duplicate ACKs.
  - Resends per 1,000 data packets, flat: 0.21, 3.61, 1.68, 10.45 (rtt4 0.23, 3.68, 1.75, 10.76). First timeouts per
    1,000 data packets climb (slots 2 → 18): home→home 10.3 → 20.4, 1G→home 3.8 → 6.6, home→1G 0.6 → 1.5, 1G→1G
    0.05 → 0.06; means 17.8, 5.9, 1.2 and 0.06 (rtt4 18.3, 6.1, 1.4, 0.08). 67 % of first timeouts start within 1 s
    after a spurious undo. 8.71M RTOs (rtt4 9.20M, rtt5 7.73M); 96.4 % of timeout episodes are spurious and undone;
    genuine recoveries take 243 / 914 / 5,789 ms at p50 / p90 / p99. No stalls; the RTO formula holds in every
    snapshot without backoff.
- **Memory and time.** Peak 223.4 GiB PSS (sim 271 s); wall 11,777 s; TCP log 1.8 GB compressed.
- **Reading.** Without the restart after idle the cell passes, as on rtt4, but with no host to spare in slot 18 where
  rtt4 had two. Windows stay 2–4× smaller than rtt4's at p50 and about 40× smaller at the 1G→1G p90, and blocks are
  7–14 % slower from publish. So the restart after idle is what fails rtt5, and Linux's window validation by itself
  costs only margin. Linux's default (`tcp_slow_start_after_idle=1`) corresponds to rtt5, which fails. The
  remaining runs (`L-pq-2k4`, fs0-b16 and the two seed-2 L runs) were queued on this configuration until the CUBIC
  build was checked; both rtt6 cells then passed, so they run on rtt6 (see [Pending](#pending)).

### 2,048 hosts × 20 slots, 2.4 kB, rtt6 (Linux's CUBIC with HyStart): `R20-pq-2k4-rtt6-ps100-cf2-s1` (cf2)

The headline cell's flags (×1.0, `--msg-bytes 2458`, P3 rate 125.0, seed 1, the same generated network) on rtt6, the
build closest to stock Linux: rtt5 with its three switches on (window validation, restart after idle, consecutive
duplicate ACKs) plus Linux's CUBIC and HyStart, all on by default. TCP logging. Completion per slot (%, slots 0–19):

| class | per slot |
|---|---|
| 50/15 | 100 in every slot |
| 50/25 | 100 in every slot |
| 1 Gbit | 97.97 99.32 99.46 100 99.73 99.86 100 100 100 99.86 99.73 99.73 99.73 99.46 99.46 99.73 99.59 99.73 99.32 99.19 |

- **Strict rule: PASS, with one host to spare.** Every class is at 99 % or more in every slot from slot 2. The worst
  slot is 19 at 99.19 % on 1 Gbit hosts (6 of ~740; the rule allows 7), then slot 18 at 99.32 % (5). Slots 2–15
  average 100 / 100 / 99.77 %, slots 16–19 100 / 100 / 99.46 % (cwv 99.75 and 99.26 %, worst 99.05 % with 7 hosts;
  rtt4 99.87 and 99.46 %, worst 99.32 % with 5; rtt5 98.80 and 98.65 %, worst 97.97 %, fail). Messages first
  delivered after the deadline stay below one per 1 Gbit node per slot (0.11 in slots 2–15, 0.57 in 16–19, at most
  0.74), within the range of the earlier passes (see Backlog), so misses do not accumulate.
- **PQ vs BLS.** PQ messages missing at 8 s on 1 Gbit hosts: 0.0060 % (slots 2–15) and 0.029 % (16–19), against
  0.0032 and 0.020 % on cwv, 0.0014 and 0.020 % on rtt4 and 0.032 and 0.051 % on rtt5; home hosts miss none. BLS
  attestations missing in the same run: 0.032 / 0.034 / 1.81 % and 0.015 / 0.035 / 2.13 %, so on 1 Gbit hosts PQ
  messages miss 74–300× less often than attestations. The no-PQ run on this build (`R20-nopq-rtt6-ps100-cf2-s1`) is
  queued; until it runs, comparisons with a no-PQ run are unmatched.
- **Who misses.** 40 incomplete 1 Gbit node·slots (never 8, near miss 19, late 13; cwv 48, rtt4 29, rtt5 164): 24 in
  slots 2–15 and 16 in 16–19. 16 of 742 hosts are incomplete at least once (8 Prysm, 6 Lighthouse, 2 other; cwv 19,
  rtt4 12, rtt5 32), 8 in two or more slots (4 Prysm, 3 Lighthouse, 1 other). One host is chronic: 1873 (Prysm, São
  Paulo, 70 peers), incomplete in 11 of 18 slots, which is 11 of the 40 node·slots; it was v400's chronic host too.
  Next come 640 (Prysm, Sydney, 4 slots), then 794 (Prysm, Singapore), 945 (Lighthouse, São Paulo), 1960 (Prysm, São Paulo), 1732 (other, Seoul)
  and 795 (Lighthouse, Sydney) with 3 each: far-region hosts, mostly Prysm with 70 peers, as on cwv, rtt5 and fs0.
- **Over the run.** 1 Gbit completion declines: 99.84 % in slots 2–7, 99.75 % in 8–13 and 99.50 % in 14–19 (cwv
  99.91, 99.57, 99.44 %; rtt4 99.93, 99.82, 99.59 %; rtt5 99.08, 98.60, 98.63 %). PQ message misses rise from
  0.0015 % to 0.0099 % and 0.022 % in the same blocks (cwv 0.001, 0.006, 0.014 %; rtt5 0.019, 0.035, 0.056 %; slots
  15–19 include the P3 onset). On 1G→1G paths ssthresh after a restart falls from 187 at slot 2 to 85 at slot 10 and
  then stays at 78–85 (rtt5 353 → 57 over slots 4–18). On paths with a home end it still falls, to higher values
  than on rtt5: 1G→home 86 → 24, home→1G 168 → 37, home→home 62 → 14 (rtt5 19 / 25 / 10 at slot 18). Block
  first-seen from publish, p95, is 2.0× rtt4's in slots 2–7 (0.72 against 0.37 s), 1.7× in 8–13 (0.54 / 0.33 s) and
  1.7× in 14–19 (0.62 / 0.36 s), 1.5–1.8× cwv's and 2–9 % below rtt5's, so the block slowdown does not grow as
  ssthresh falls, and CUBIC's growth barely shortens it. Per slot (slots 2–19; ssthresh slots 2–18, u = more than
  half of the restarts on connections that never reduced it; rtt5's ssthresh rows are in its section):

| series | per slot |
|---|---|
| block first-seen from publish p95, rtt4 (s) | 0.33 0.31 0.37 0.37 0.50 0.32 0.30 0.32 0.31 0.36 0.38 0.29 0.33 0.29 0.42 0.36 0.31 0.46 |
| block first-seen from publish p95, cwv (s) | 0.38 0.31 0.40 0.37 0.52 0.37 0.40 0.33 0.34 0.44 0.40 0.32 0.35 0.32 0.44 0.40 0.34 0.63 |
| block first-seen from publish p95, rtt5 (s) | 0.80 0.79 0.85 0.71 0.93 0.66 0.69 0.48 0.53 0.64 0.60 0.40 0.62 0.51 0.62 0.59 0.58 0.88 |
| block first-seen from publish p95, rtt6 (s) | 0.67 0.75 0.77 0.60 0.95 0.58 0.60 0.49 0.51 0.65 0.60 0.41 0.57 0.59 0.61 0.58 0.58 0.81 |
| ssthresh p50 after a restart, 1G→1G | 187 135 109 97 93 90 90 87 85 85 83 79 81 79 78 79 78 |
| ssthresh p50 after a restart, 1G→home | u 86 51 39 34 31 30 28 27 26 25 25 25 25 25 24 24 |
| ssthresh p50 after a restart, home→1G | u u 168 116 86 70 63 54 49 46 43 42 41 40 39 37 37 |
| ssthresh p50 after a restart, home→home | u u u 62 29 21 18 16 16 15 15 15 15 15 14 14 14 |
| 1 Gbit completion, rtt4 (%) | 100 99.73 100 100 100 99.86 100 99.86 99.46 99.86 99.86 99.86 99.86 99.86 99.59 99.32 99.32 99.60 |
| 1 Gbit completion, cwv (%) | 99.59 100 100 100 100 99.86 99.86 99.46 99.59 99.73 99.32 99.46 99.73 99.86 99.32 99.46 99.05 99.19 |
| 1 Gbit completion, rtt5 (%) | 99.19 99.19 99.05 99.05 99.19 98.78 97.97 98.65 98.78 99.05 98.78 98.38 98.78 98.38 98.65 98.92 98.65 98.38 |
| 1 Gbit completion, rtt6 (%) | 99.46 100 99.73 99.86 100 100 100 99.86 99.73 99.73 99.73 99.46 99.46 99.73 99.59 99.73 99.32 99.19 |
| 1 Gbit PQ messages missing at 8 s, cwv (%) | 0.006 0 0 0 0 0.003 0.000 0.003 0.015 0.002 0.009 0.004 0.002 0.001 0.025 0.023 0.019 0.014 |
| 1 Gbit PQ messages missing at 8 s, rtt5 (%) | 0.008 0.015 0.015 0.025 0.022 0.030 0.052 0.039 0.026 0.025 0.029 0.037 0.068 0.064 0.088 0.020 0.051 0.045 |
| 1 Gbit PQ messages missing at 8 s, rtt6 (%) | 0.0016 0 0.0062 0.0009 0 0 0 0.0045 0.0091 0.0274 0.0136 0.0047 0.0106 0.0049 0.0324 0.0369 0.0248 0.0204 |

- **CUBIC and HyStart.** Data packets sent with cwnd ≥ ssthresh: 78.2 % (1G→1G), 72.3 % (1G→home), 73.0 % (home→1G)
  and 67.6 % (home→home), 75.3 % in all (bundled cell on rtt6 70.4 %). HyStart exits, ack train / delay: 12,756 / 0
  (1G→1G), 1,654 / 2,599 (1G→home), 2,780 / 5,205 (home→1G), 0 / 3,966 (home→home), with cwnd at exit p50 (p90) 31
  (195), 100 (210), 76 (238) and 115 (240). Train exits fire on short paths (delay_min p50 2.8 ms; the ack train
  spans 2.1 ms at p50 against a threshold of 1.9 ms), delay exits when the round's minimum RTT sample is 5.9 ms above
  delay_min at p50 (threshold 4.0 ms). All 402,883 logged window targets equal Linux's integer formula, origin ±
  (410 · |t − K|³ >> 40). No congestion-avoidance round grows by more than one segment per two packets ACKed, plus
  one, and all 343,479 traced epoch shifts at a send after idle equal min(epoch + idle, now).
- **P3** from slot 15: PQ 512 → 935 per slot (cwv 412–528, rtt5 804 → 926) and attestation 1,330 → 321; block and
  aggregate 0. Per host, PQ / attestation: Lighthouse 1.99 / 1.12, other 7.08 / 1.53, Teku 2.31 / 2.40, Lodestar
  2.09 / 5.12, Nimbus 1.80 / 6.52, Prysm 0. Negative-score peers per observer: Lighthouse 15.0, other 22.6; Teku,
  Lodestar, Nimbus and Prysm 0.14–0.19 (cwv 14.7, 22.0 and 0.14–0.23).
- **Latency** from publish, p50 / p99: 0.14 / 0.78 s (50/15), 0.13 / 0.72 s (50/25), 0.12 / 0.92 s (1 Gbit); cwv
  0.10 / 0.62, 0.10 / 0.59 and 0.09 / 0.76 s; rtt4 0.10 / 0.64, 0.09 / 0.51 and 0.09 / 0.68 s; rtt5 0.15 / 0.84,
  0.14 / 0.82 and 0.13 / 1.18 s.
- **κ** 9.1 → 10.3; PQ copies per message 3.6 → 4.5; IDONTWANT 15.6–23.3k ids per node per slot (cwv 9.1 → 10.1,
  3.6 → 4.4 and 15–22k).
- **Bandwidth in the 4 s window**, mean / max node, % of cap: upload 45 / 71 (50/15), 29 / 44 (50/25), 6 / 12
  (1 Gbit); download ≤ 14 / 23 (cwv within 1 point of these).
- **Backlog.** Messages first delivered after the deadline are 0 per node in every slot on home hosts. On 1 Gbit
  hosts they average 0.11 per node per slot in slots 2–15 and 0.57 in slots 16–19 (at most 0.74, slot 17), never more
  than the messages missing at 8 s (0.5–0.7 per node in slots 16–18). Earlier passes had similar counts: the current
  build 0.19 and 0.41 (at most 0.75; seed 2 at most 0.14), rtt4 0.02 and 0.37 (at most 0.50), cwv 0.05 and 0.37
  (at most 0.45). After-deadline PQ kB per 1 Gbit node per
  slot: 224 at slot 2, 880 at slot 8, then 865–1,143 over slots 9–19, +19.1 kB per slot over slots 10–19 (cwv +12.0,
  rtt4 +23.6, rtt5 +12.7). Home hosts, slot 2 → 19: 50/15 30 → 62 kB, 50/25 21 → 52 kB, +1.4 and +1.2 kB per slot
  over slots 10–19 (cwv +3.3 / +2.3, rtt4 +1.2 / +1.7, rtt5 +3.4 / +3.2). Apart from those first deliveries, these
  bytes are copies of messages already held. Links per node 207–233 and connections 163–165 per node, flat.
  Negative-score peers peak at 27.4k in slot 5 and settle at 17.9–19.2k from slot 12. Failed sends that cost score:
  200.1M (forward timeout 36.1 %, forward queue full 34.8 %, control queue full 29.1 %; cwv 205.1M, rtt4 200.0M,
  rtt5 217.4M). Stale copies: PQ 0, background 2; bgexcess ≤ 1.008 on background topics. Churn removes 34 of
  40,000 signatures; no refused publish.
- **TCP** (path types by sender → receiver):
  - Restarts after idle: about 1.5M per slot (1G→1G 250k, 1G→home 400k, home→1G 410k, home→home 430k), flat; median
    idle time 0.92–1.00 s against a median RTO of 0.29–0.36 s. cwnd before → after, p50 (p90): 15 (59) → 10 (18) on
    1G→1G and 10 (22–28) → 10 (10) elsewhere. 91 % of restarts leave cwnd below ssthresh, and all of those continue
    in slow start.
  - cwnd p50 / p90 over the run: 10 / 37 (1G→1G), 10 / 20 (1G→home), 10 / 21 (home→1G), 10 / 18 (home→home); cwv
    76 / 239, 37 / 125, 37 / 97 and 21 / 52; rtt4 300 / 9,438, 63 / 482, 97 / 562 and 38 / 277; rtt5 10 / 35,
    10 / 19, 10 / 19 and 10 / 16. The same endpoints' cwnd p50 is 10 at slots 2 and 19 on every path type.
  - Fast-recovery entries per 1,000 data packets: 0.21 (1G→1G), 1.44 (1G→home), 1.41 (home→1G), 2.35 (home→home),
    all after consecutive duplicate ACKs.
  - Resends per 1,000 data packets, flat: 0.24, 3.33, 1.78 and 9.90 (cwv 0.21, 3.61, 1.68, 10.45; rtt4 0.23, 3.68,
    1.75, 10.76). First timeouts per 1,000 data packets climb (slots 2 → 18): home→home 10.6 → 19.7, 1G→home 3.6 →
    6.3, home→1G 0.78 → 2.10, 1G→1G 0.07 → 0.12; means 17.6, 5.6, 1.6 and 0.10 (cwv 17.8, 5.9, 1.2, 0.06; rtt4 18.3,
    6.1, 1.4, 0.08). 68 % of first timeouts start within 1 s after a spurious undo on the same connection. 8.83M
    RTOs (cwv 8.71M, rtt4 9.20M, rtt5 7.73M); 96.7 % of Eifel checks found the timeout spurious and undid it; genuine
    recoveries take 133–279 ms at p50 and 437–977 ms at p90, by path type. No stalls (6.96M snapshots); the RTO
    formula holds in all 6,349,737 snapshots without backoff; buffers start at 131,072 / 174,760 B on every
    connection. SRTT − configured RTT, p50 / p99: 2 / 6, 8 / 109, 5 / 12 and 11 / 120 ms.
- **Blocks:** none missing; from publish p50 / p95 / p99 0.34 / 0.69 / 0.88 s (cwv 0.22 / 0.42 / 0.57 s, rtt4 0.19 /
  0.37 / 0.48 s, rtt5 0.34 / 0.73 / 0.93 s). Attestations after 4 s p50 / p95 / p99 1.08 / 2.14 / 3.73 s; 0.72 %
  never arrive (cwv 0.83 %, rtt4 0.53 %, rtt5 0.85 %).
- **Memory and time.** Peak 227.5 GiB PSS; wall 11,789 s; TCP log 3.2 GB compressed.
- **Build rule.** The pass (decided 12:03 Nov 11) moved both seeds of `L-pq-2k4` to rtt6
  (`L-pq-2k4-rtt6-ps100-cf2-s1` and `-s2`); `R20-nopq-rtt6-ps100-cf2-s1` was already queued. Both were dropped
  on Nov 12, when bundling was adopted: seed 1 was stopped at sim 368 s (slots 0–27), and seed 2 never ran.
- **Reading.** With Linux's CUBIC and HyStart on top of rtt5, the unbundled headline cell passes where rtt5 fails,
  with one host to spare in its worst slot (cwv had none, rtt4 two). CUBIC recovers most of rtt5's completion loss
  (40 incomplete node·slots against 164; cwv 48, rtt4 29) but not its block slowdown: blocks stay 1.7–2.0× rtt4's
  from publish and within 9 % of rtt5's, as on every build that restarts windows after idle. 1 Gbit completion
  still declines over the run, as on rtt4 and cwv, so the 20-slot pass carries a shrinking margin. Whether it holds
  over 50 slots stays open: `L-pq-2k4-rtt6-ps100-cf2-s1` was stopped at slot 27 when bundling was adopted.

### 2,048 hosts × 20 slots, 2.4 kB, 600k and 400k validators: `R20-pq-v600-2k4-ps100-cf2-s1`, `R20-pq-v400-2k4-ps100-cf2-s1` (cf2)

Fewer validators after consolidation: `--consolidate 0.75 --msgs 1500` and `--consolidate 0.5 --msgs 1000`, with P3
rates of 93.75 and 62.5 messages per subnet per slot. Consolidation also leaves fewer hosts above the 1 Gbit
threshold (about 697 and 633 online).

| | 600k (1,500 messages) | 400k (1,000 messages) |
|---|---|---|
| 1 Gbit per slot (%, slots 0–19) | 99.86 100 99.86 100 100 100 100 99.86 99.86 99.86 99.86 99.86 99.57 99.71 100 100 99.71 99.86 100 99.57 | 99.84 100 100 99.84 100 99.84 99.84 99.84 100 99.84 99.84 99.84 99.84 99.84 99.84 99.84 99.84 99.84 99.84, then 0.0 in slot 19 (100 with the slot-19 message counted as lost to churn) |
| strict rule | PASS: worst slot 99.57 % (slots 12 and 19, 3 hosts; 6 allowed) | FAIL, in slot 19 only: one refused publish, a peer-management failure; without it the worst slot is 99.84 % (1 host) |
| complete, 50/15 / 50/25 / 1 Gbit (%), slots 2–15 and 16–19 | 100 / 100 / 99.89 and 100 / 100 / 99.78 | 100 / 100 / 99.88 and 100 / 100 / 99.88 (16–19 without that message) |
| PQ missing at 8 s, 1 Gbit, slots 2–15 and 16–19 | 0.0030 / 0.0024 % | 0.0039 / 0.0030 % (excluded as above) |
| BLS attestations missing, same run, slots 2–15 and 16–19 | 0.016 / 0.022 / 0.91 and 0.004 / 0.028 / 1.31 % | 0.007 / 0.017 / 1.05 and 0.012 / 0.015 / 1.14 % |
| hosts incomplete in ≥ 2 slots | 3 Prysm: 791 São Paulo (8 slots), 548 Singapore (4), 1430 Singapore (2) | 1873 (Prysm, São Paulo, 14 of 18: chronic) and 794 (Prysm, Singapore, 2) |
| P3 from slot 15, PQ / attestation, per slot | 618 → 488 / 850 → 140 | 261 → 354 / 997 → 359 |
| negative-score peers per observer, Lighthouse / other / non-Rust | 10.4 / 15.7 / 0.10–0.20 | 7.9 / 13.5 / 0.08–0.19 |
| after-deadline PQ kB per 1 Gbit node, slot 0 → 19 | 140 → 1,238 (first deliveries ≤ 0.15 per node) | 72 → 639 (first deliveries ≤ 0.10 per node) |
| latency p99 from publish, 50/15 / 50/25 / 1 Gbit | 0.48 / 0.42 / 0.54 s | 0.35 / 0.37 / 0.45 s |
| upload in the 4 s window, mean / max node, 50/15 | 39 / 61 % | 33 / 49 % |
| stale copies PQ / background; bgexcess | 9,895 / 44,232; ≤ 1.002 | 4,521 / 55,358; see below |
| peak PSS / wall | 212.4 GiB / 10,967 s | 190.0 GiB / 9,604 s |

- **v400, slot 19.** One message (topic 1) reached no subscriber. Its publisher, host 1218 (Lighthouse, 50/25,
  Singapore), joined the network at 262.22 s. Its peer manager dialled 116 peers at 262.32 s, and at 262.42 s gossipsub
  refused the publish with `NoPeersSubscribedToTopic`, so the message was never cached or sent. Every subscriber of
  that subnet missed it: 1 Gbit 0.0 % and home 95.4–95.8 % in that slot. It is the only refused PQ publish in the 23
  finished PQ runs.
  - **Churn or peer management?** By the coordinator's rule (Nov 9), a message is lost to churn if its publisher was
    offline or had no connections at all at publish time. A publish refused while the publisher has connections is a
    peer-management failure and counts against the network.
  - wbsim logs the connection count every 0.5 s: 0 at 262.00 s (still offline) and 6 at 262.50 s. In the latency
    model 107 hosts are within 47.5 ms RTT of host 1218, close enough to finish TCP and Noise (about 2 RTT) in the
    95 ms between its first dials and the publish; about 6 of its 116 dials are expected to reach one. A Singapore
    1 Gbit host (16 ms RTT, on every subnet) would have announced topic 1 in time, so its first peers were most likely
    home stakers on other subnets.
  - So it most likely had connections, but none that had announced topic 1 yet: a peer-management failure, and the
    strict FAIL stands. The log cannot prove this to the millisecond. `PQ_JOIN_GRACE`, which selected this message, is
    retired.
- **v400, bgexcess.** PQ, attestations and aggregates sit at 1.045–1.061 in slots 0–7, flat, and at ≤ 1.01 from slot
  8. Stale copies are the lowest of the 2.4 kB runs. This is not the growing re-flood seen before the age fix. Its
  cause is not established; it will be looked into only if another run shows it.

[^v400]: Without that message, v400 passes every slot: worst slot 99.84 % (1 host); slots 2–15 and 16–19 at
    100 / 100 / 99.88 %.

### 1,024 hosts × 50 slots, 2.4 kB: `L-pq-2k4-ps100-cf2-s1` (cf2, long horizon)

×1.0, `--msg-bytes 2458`, seed 1, 800k unbundled (P3 rate 125). 2,048 × 50 does not fit in memory, so this is the
long-horizon check of the final model. With half the hosts (159 at 50/15, ~495 at 50/25, ~366 at 1 Gbit), one host
is 0.27 % of the 1 Gbit class.

- **Strict rule: PASS, at the limit in five late slots.** 50/25 100 % in every slot; 50/15 100 % except slot 37
  (99.37 %, one host, a near miss). 1 Gbit ≥ 99.18 % in every slot; 99.18 % (3 of ~366 hosts, the most the rule
  allows) in slots 33, 37, 41, 42 and 44.
- **It levels off.** Means over slots 2–15, 16–29, 30–39 and 40–49, and the slope over slots 30–49:

| series | 2–15 | 16–29 | 30–39 | 40–49 | slope, slots 30–49, per 10 slots |
|---|---|---|---|---|---|
| 1 Gbit complete (%) | 99.84 | 99.84 | 99.51 | 99.48 | −0.02 points |
| PQ missing at 8 s, 1 Gbit (%) | 0.0039 | 0.0015 | 0.045 | 0.033 | +2 % |
| BLS attestations missing, 1 Gbit (%) | 1.21 | 1.44 | 1.66 | 1.38 | −25 % |
| links per node | 214.4 | 214.6 | 216.5 | 218.0 | +1 % |
| PQ mesh degree, 1 Gbit | 6.97 | 6.90 | 6.86 | 6.86 | 0 % |
| negative-score peers per observer, Lighthouse / other | 11.3 / 19.1 | 9.8 / 16.1 | 8.9 / 14.1 | 8.5 / 12.3 | −6 / −16 % |
| same, Teku / Lodestar / Nimbus / Prysm | 0.11 / 0.01 / 0.03 / 0.10 | 0.76 / 0.74 / 0.80 / 0.26 | 0.88 / 1.15 / 1.06 / 0.38 | 0.98 / 1.23 / 1.24 / 0.40 | +8 / +6 / +13 / +7 % |
| P3 deficits per slot, PQ / attestation / block | 11 / 31 / 0 | 266 / 159 / 0 | 251 / 52 / 12 | 201 / 57 / 24 | −32 / +11 / +71 % |
| P3 in Lighthouse / other / Teku / Lodestar / Nimbus views | 11 / 2 / 5 / 5 / 20 | 289 / 52 / 28 / 22 / 36 | 212 / 51 / 7 / 8 / 45 | 173 / 49 / 36 / 11 / 16 | −28 / +4 / +71 / +13 / −66 % |
| after-deadline PQ kB per 1 Gbit node | 880 | 1,339 | 1,484 | 1,562 | +4 % |
| after-deadline PQ kB per 50/15 node | 57 | 89 | 84 | 94 | +11 % |
| after-deadline PQ kB per 50/25 node | 45 | 72 | 75 | 88 | +15 % |

  - 1 Gbit completeness steps down once, around slot 33, and stays flat from there to slot 49. The step coincides
    with the first block-topic P3 deficits (block P3 activates one epoch after a peer joins the mesh). But the most
    frequent misser, 640 (Prysm, Sydney: 17 of slots 16–49, none before), keeps its PQ mesh (in-degree 102–111), so
    the mechanism is not established.
  - **Stale copies and the step** (copies more than 60 s old, counted over each whole slot, 1.6–2.1 times the 8–16 s
    count given below; `stalehosts.py`). A copy held up by a lost segment arrives one retransmission timeout later,
    so stale copies mark TCP stalls of more than 60 s on the connections into a host, and they arrive about 5–10
    slots after the stall began (timeouts of 64–120 s). Per 1 Gbit node per slot, per 10-slot block from slot 2: PQ
    0.00, 1.47, 1.92, 3.07 and 3.15; background 0.1, 6.8, 9.6, 12.1 and 15.1. They don't start with the step: they
    appear at slots 9–10 and stay at 0.25–3.15 per node per slot through slot 35, while only 18 1 Gbit node·slots
    miss in slots 2–32. They surge right after it, to 3.5–7.7 in slots 36–41, which points to stalls that began
    around slots 26–36. And they land on the hosts that miss after the step, one timeout later: 21 of the 28
    incomplete 1 Gbit node·slots in slots 33–44 (75 %; 12 of 18 without 640) are followed by stale copies on the
    same host 5–11 slots later, against 5.8 % of complete node·slots and 26–28 % of the same hosts' complete
    node·slots. Before the step, 6 of 18 are (33 %). 557 (Prysm, Tokyo) misses in slots 33–40 with a single stale
    copy among them (slot 35) and then gets 97–187 per slot in slots 44–46; 640 gets them in every slot from 27 to
    48 and misses from slot 30. So most misses after the step happen during stalls of more than 60 s on connections
    into the missing host. That fits the timeout ratchet, which on this build turns isolated losses into such
    stalls, but doesn't single it out: over 20 slots, rtt4, without the ratchet, still has 9,331 stale PQ copies
    (current build 16,381 on the same seed, 9,951 on seed 2), while rtt5 has 444, cwv 222 and rtt6 none.
    Whether the step remains without them stays open: `L-pq-2k4-rtt6-ps100-cf2-s1` was stopped at slot 27, before the
    step, when bundling was adopted.
  - Negative-score peers decline in Lighthouse and other views. In Teku, Lodestar and Nimbus views they rise to about
    one per observer after P3 activates, and the rise slows by slot 40. PQ and attestation deficits peak after
    activation and then decline; block-topic deficits are small (12–36 per slot over 1,024 hosts) and still rising at
    slot 49.
  - After-deadline PQ bytes still grow, but each 10-slot block adds less (+459, +145, +78 kB). They are mostly
    duplicates. Messages first delivered after the deadline average 0.01, 0.10, 0.01, 0.65 and 0.65 per 1 Gbit node
    per slot in the 10-slot blocks from slot 2 (at most 1.54, slot 34; slot 40 0.46): they step up with the misses
    at 8 s around slot 33 and then stay level, and over slots 2–49 they sum to 14.2 per node against 17.2 missing at
    8 s. Copies older than 60 s, which gossipsub no longer recognises as duplicates and the client ignores, add 0.70,
    0.96, 1.94 and 1.83 per node per slot in the blocks from slot 10 (at most 5.3, slot 40); the earlier count of 3–6
    per node in slots 36–48 included them. Nothing re-floods: bgexcess ≤ 1.014; stale copies total PQ 42,842 and background 204,013 over 1,024 hosts × 50 slots.
  - Home hosts hold every PQ message by the deadline in all but one node·slot, so their after-deadline bytes are
    late copies too. They level off less than the 1 Gbit class: per block 50/15 57 → 89 → 84 → 94 kB and 50/25
    45 → 72 → 75 → 88 kB, +11 and +15 % per 10 slots over slots 30–49 against +4 % for 1 Gbit. In 10-slot blocks
    from slot 2: 50/15 48, 76, 91, 84, 94 kB; 50/25 36, 62, 74, 75, 88 kB.
- **Incomplete node·slots.** Slots 2–15: 8 (near miss 4, late 4). Slots 16–49: 45 on 1 Gbit hosts (whole subnet 4,
  never received 11, near miss 10, late 20) and one 50/15 near miss. No host is incomplete in half the slots. The
  most frequent are 640 (Prysm, Sydney) 17, 557 (Prysm, Tokyo) 8, 420 (Lighthouse, Sydney) 7 and 308 (Prysm, Seoul) 7.
- **PQ vs BLS**, slots 2–15 and 16–49: PQ missing 0.0039 / 0.0237 % on 1 Gbit hosts (home ≤ 0.0001 %); attestations
  0.10 / 0.027 / 1.21 % and 0.038 / 0.023 / 1.49 %.
- **Other.** Negative-score peers per observer over the run: Lighthouse 9.7, other 15.6, Lodestar 0.70, Nimbus 0.70,
  Teku 0.63, Prysm 0.26. IWANT re-requests: Prysm 3.73M, Nimbus 2.34M, Teku 1.82M, Lodestar 1.79M. Failed sends that
  cost score: 3.3M per slot. Peak 125.0 GiB PSS; wall 15,913 s.

Delivery per slot, `L-pq-2k4-ps100-cf2-s1` (1 Gbit = cloud class; PQ and BLS misses at 8 s; after-deadline PQ kB per node, 8-16 s)

| slot | complete 50/15 / 50/25 / 1 Gbit (%) | PQ missing, 1 Gbit (%) | BLS attestations missing, 50/15 / 50/25 / 1 Gbit (%) | after-deadline PQ kB, 50/15 / 50/25 / 1 Gbit | late first PQ deliveries (8-16 s), 1 Gbit host mean |
|---|---|---|---|---|---|
| 0 | 100.00 / 100.00 / 99.45 | – | – / – / – | 16 / 14 / 112 | 0.09 |
| 1 | 100.00 / 100.00 / 99.45 | – | – / – / – | 21 / 13 / 233 | 0.04 |
| 2 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.284 / 0.118 / 0.851 | 29 / 18 / 346 | 0.00 |
| 3 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.005 / 0.971 | 42 / 25 / 466 | 0.00 |
| 4 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.063 / 0.000 / 1.071 | 42 / 27 / 482 | 0.00 |
| 5 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.246 / 0.000 / 1.479 | 47 / 38 / 653 | 0.00 |
| 6 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.005 / 1.199 | 55 / 40 / 728 | 0.00 |
| 7 | 100.00 / 100.00 / 99.73 | 0.0001 | 0.016 / 0.010 / 1.122 | 52 / 39 / 840 | 0.00 |
| 8 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.000 / 1.427 | 61 / 48 / 993 | 0.00 |
| 9 | 100.00 / 100.00 / 99.73 | 0.0097 | 0.000 / 0.111 / 1.259 | 53 / 51 / 988 | 0.12 |
| 10 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.174 / 0.036 / 0.703 | 65 / 53 / 966 | 0.00 |
| 11 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.153 / 0.000 / 0.881 | 55 / 57 / 1032 | 0.00 |
| 12 | 100.00 / 100.00 / 99.73 | 0.0071 | 0.000 / 0.086 / 1.108 | 72 / 60 / 1221 | 0.14 |
| 13 | 100.00 / 100.00 / 99.45 | 0.0051 | 0.015 / 0.000 / 1.637 | 77 / 58 / 1236 | 0.10 |
| 14 | 100.00 / 100.00 / 99.73 | 0.0077 | 0.149 / 0.000 / 1.562 | 80 / 56 / 1128 | 0.15 |
| 15 | 100.00 / 100.00 / 99.45 | 0.0242 | 0.320 / 0.005 / 1.696 | 70 / 64 / 1244 | 0.48 |
| 16 | 100.00 / 100.00 / 99.73 | 0.0015 | 0.000 / 0.005 / 1.582 | 78 / 64 / 1266 | 0.03 |
| 17 | 100.00 / 100.00 / 99.73 | 0.0107 | 0.079 / 0.005 / 1.491 | 82 / 66 / 1228 | 0.06 |
| 18 | 100.00 / 100.00 / 99.73 | 0.0032 | 0.169 / 0.000 / 1.729 | 85 / 64 / 1218 | 0.06 |
| 19 | 100.00 / 100.00 / 99.45 | 0.0010 | 0.155 / 0.005 / 1.164 | 95 / 75 / 1386 | 0.02 |
| 20 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.148 / 0.005 / 1.514 | 92 / 60 / 1328 | 0.00 |
| 21 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.077 / 0.000 / 1.460 | 88 / 66 / 1300 | 0.00 |
| 22 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.005 / 1.195 | 77 / 68 / 1293 | 0.00 |
| 23 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.050 / 1.314 | 95 / 78 / 1413 | 0.00 |
| 24 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.016 / 1.316 | 88 / 73 / 1344 | 0.00 |
| 25 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.030 / 1.426 | 90 / 78 / 1310 | 0.00 |
| 26 | 100.00 / 100.00 / 99.73 | 0.0005 | 0.016 / 0.036 / 1.703 | 104 / 81 / 1441 | 0.01 |
| 27 | 100.00 / 100.00 / 99.73 | 0.0004 | 0.000 / 0.051 / 1.243 | 97 / 81 / 1399 | 0.01 |
| 28 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.000 / 1.573 | 99 / 79 / 1454 | 0.00 |
| 29 | 100.00 / 100.00 / 99.73 | 0.0042 | 0.016 / 0.092 / 1.410 | 77 / 81 / 1361 | 0.08 |
| 30 | 100.00 / 100.00 / 99.73 | 0.0092 | 0.000 / 0.015 / 2.172 | 70 / 72 / 1440 | 0.18 |
| 31 | 100.00 / 100.00 / 99.73 | 0.0211 | 0.015 / 0.005 / 2.082 | 84 / 73 / 1435 | 0.42 |
| 32 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.015 / 1.777 | 74 / 72 / 1450 | 0.00 |
| 33 | 100.00 / 100.00 / 99.18 | 0.0419 | 0.031 / 0.020 / 1.654 | 91 / 78 / 1545 | 0.51 |
| 34 | 100.00 / 100.00 / 99.45 | 0.0896 | 0.000 / 0.010 / 1.777 | 82 / 69 / 1462 | 1.54 |
| 35 | 100.00 / 100.00 / 99.45 | 0.0607 | 0.000 / 0.049 / 1.964 | 91 / 76 / 1482 | 0.53 |
| 36 | 100.00 / 100.00 / 99.45 | 0.0279 | 0.000 / 0.024 / 1.304 | 83 / 70 / 1430 | 0.36 |
| 37 | 99.37 / 100.00 / 99.18 | 0.0285 | 0.077 / 0.024 / 1.149 | 92 / 78 / 1545 | 0.48 |
| 38 | 100.00 / 100.00 / 99.45 | 0.0805 | 0.000 / 0.010 / 1.249 | 85 / 83 / 1541 | 1.09 |
| 39 | 100.00 / 100.00 / 99.45 | 0.0945 | 0.000 / 0.035 / 1.439 | 90 / 81 / 1513 | 1.40 |
| 40 | 100.00 / 100.00 / 99.45 | 0.0279 | 0.094 / 0.093 / 1.684 | 104 / 91 / 1604 | 0.46 |
| 41 | 100.00 / 100.00 / 99.18 | 0.0562 | 0.031 / 0.000 / 1.543 | 85 / 86 / 1562 | 1.12 |
| 42 | 100.00 / 100.00 / 99.18 | 0.0033 | 0.000 / 0.024 / 1.374 | 91 / 85 / 1595 | 0.07 |
| 43 | 100.00 / 100.00 / 99.73 | 0.0119 | 0.016 / 0.005 / 1.323 | 84 / 87 / 1551 | 0.24 |
| 44 | 100.00 / 100.00 / 99.18 | 0.0355 | 0.047 / 0.124 / 1.317 | 94 / 82 / 1596 | 0.71 |
| 45 | 100.00 / 100.00 / 99.45 | 0.0663 | 0.181 / 0.000 / 1.433 | 99 / 86 / 1482 | 1.32 |
| 46 | 100.00 / 100.00 / 99.73 | 0.0264 | 0.151 / 0.015 / 1.428 | 91 / 83 / 1521 | 0.48 |
| 47 | 100.00 / 100.00 / 99.73 | 0.0433 | 0.000 / 0.000 / 1.376 | 99 / 97 / 1543 | 0.86 |
| 48 | 100.00 / 100.00 / 99.45 | 0.0415 | 0.000 / 0.000 / 1.110 | 95 / 94 / 1590 | 0.83 |
| 49 | 100.00 / 100.00 / 99.73 | 0.0181 | 0.000 / 0.025 / 1.251 | 94 / 91 / 1573 | 0.36 |

Scoring per slot, `L-pq-2k4-ps100-cf2-s1` (mesh snapshot at 3.95 s; negative-score peers per observer; P3 = MessageDeficit penalties summed over hosts in the slot; Prysm applies no P3)

| slot | links/node | negative peers per observer: Lighthouse / other / Prysm / Teku / Lodestar / Nimbus | P3 by topic: PQ / attestation / block / aggregate | P3 in the views of Lighthouse / other / Teku / Lodestar / Nimbus |
|---|---|---|---|---|
| 0 | 214.3 | 0.0 / 0.0 / 0.0 / 0.0 / 0.0 / 0.0 | – / – / – / – | – / – / – / – / – |
| 1 | 203.7 | 4.6 / 7.1 / 0.0 / 0.0 / 0.0 / 0.0 | – / – / – / – | – / – / – / – / – |
| 2 | 212.0 | 8.4 / 14.1 / 0.0 / 0.0 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 3 | 222.2 | 11.3 / 19.1 / 0.0 / 0.0 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 4 | 207.4 | 14.2 / 22.9 / 0.0 / 0.0 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 5 | 208.5 | 14.1 / 23.4 / 0.0 / 0.0 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 6 | 214.3 | 12.5 / 21.2 / 0.1 / 0.1 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 7 | 210.7 | 11.6 / 20.1 / 0.1 / 0.1 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 8 | 222.1 | 10.6 / 18.6 / 0.1 / 0.2 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 9 | 219.4 | 11.2 / 18.9 / 0.1 / 0.2 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 10 | 211.5 | 11.3 / 19.3 / 0.1 / 0.1 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 11 | 209.7 | 10.8 / 19.0 / 0.1 / 0.1 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 12 | 217.9 | 10.4 / 18.3 / 0.2 / 0.2 / 0.0 / 0.1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 13 | 223.1 | 10.4 / 17.9 / 0.2 / 0.2 / 0.0 / 0.1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 14 | 212.5 | 10.7 / 17.5 / 0.2 / 0.2 / 0.0 / 0.1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 15 | 210.9 | 10.4 / 17.4 / 0.2 / 0.2 / 0.1 / 0.1 | 150 / 438 / 0 / 0 | 152 / 31 / 65 / 66 / 274 |
| 16 | 216.0 | 10.4 / 17.5 / 0.2 / 0.4 / 0.4 / 0.4 | 109 / 379 / 0 / 0 | 282 / 47 / 32 / 41 / 86 |
| 17 | 208.5 | 10.4 / 17.2 / 0.2 / 0.5 / 0.4 / 0.4 | 157 / 297 / 0 / 0 | 258 / 43 / 45 / 52 / 56 |
| 18 | 218.1 | 9.8 / 16.5 / 0.2 / 0.6 / 0.5 / 0.6 | 257 / 199 / 0 / 0 | 225 / 81 / 26 / 60 / 64 |
| 19 | 221.8 | 10.1 / 16.0 / 0.2 / 0.8 / 0.6 / 0.7 | 211 / 166 / 0 / 0 | 184 / 97 / 24 / 32 / 40 |
| 20 | 211.5 | 10.4 / 17.0 / 0.2 / 0.7 / 0.7 / 0.8 | 275 / 181 / 0 / 0 | 297 / 85 / 24 / 17 / 33 |
| 21 | 210.5 | 10.2 / 16.4 / 0.2 / 0.8 / 0.7 / 0.8 | 368 / 206 / 0 / 0 | 449 / 65 / 16 / 24 / 20 |
| 22 | 210.4 | 9.6 / 15.2 / 0.3 / 0.8 / 0.7 / 0.9 | 344 / 171 / 0 / 0 | 397 / 42 / 40 / 30 / 6 |
| 23 | 224.2 | 9.0 / 15.3 / 0.3 / 0.8 / 0.8 / 0.9 | 305 / 179 / 0 / 0 | 340 / 47 / 48 / 8 / 41 |
| 24 | 211.2 | 9.9 / 15.8 / 0.3 / 0.8 / 0.8 / 0.9 | 290 / 142 / 0 / 0 | 288 / 47 / 29 / 17 / 51 |
| 25 | 210.1 | 9.7 / 15.8 / 0.3 / 0.8 / 0.8 / 0.9 | 320 / 108 / 0 / 0 | 306 / 45 / 30 / 15 / 32 |
| 26 | 217.0 | 9.7 / 15.6 / 0.3 / 0.9 / 0.9 / 0.9 | 321 / 55 / 0 / 0 | 297 / 34 / 20 / 6 / 19 |
| 27 | 210.3 | 9.8 / 16.1 / 0.3 / 0.9 / 1.0 / 1.0 | 285 / 41 / 0 / 0 | 259 / 30 / 17 / 1 / 19 |
| 28 | 221.7 | 9.2 / 15.6 / 0.3 / 0.9 / 1.0 / 1.0 | 246 / 45 / 0 / 0 | 235 / 29 / 6 / 0 / 21 |
| 29 | 213.7 | 9.5 / 15.4 / 0.3 / 0.9 / 1.0 / 1.0 | 242 / 59 / 0 / 0 | 225 / 29 / 30 / 4 / 13 |
| 30 | 217.6 | 9.3 / 15.6 / 0.3 / 0.9 / 1.0 / 1.0 | 262 / 29 / 6 / 7 | 219 / 39 / 17 / 2 / 27 |
| 31 | 213.0 | 9.3 / 15.7 / 0.3 / 0.9 / 1.1 / 1.0 | 298 / 28 / 17 / 0 | 244 / 57 / 3 / 10 / 29 |
| 32 | 211.6 | 8.9 / 14.9 / 0.4 / 0.9 / 1.1 / 1.0 | 292 / 27 / 17 / 0 | 228 / 66 / 0 / 0 / 42 |
| 33 | 228.3 | 8.3 / 13.9 / 0.4 / 0.9 / 1.1 / 1.0 | 263 / 29 / 18 / 0 | 198 / 62 / 0 / 16 / 34 |
| 34 | 218.8 | 9.2 / 14.4 / 0.4 / 0.8 / 1.1 / 1.0 | 218 / 48 / 8 / 1 | 197 / 44 / 1 / 0 / 33 |
| 35 | 211.3 | 9.4 / 13.9 / 0.4 / 0.9 / 1.1 / 1.0 | 257 / 55 / 6 / 1 | 219 / 43 / 2 / 1 / 54 |
| 36 | 210.5 | 9.0 / 13.3 / 0.4 / 0.9 / 1.2 / 1.1 | 280 / 57 / 12 / 13 | 254 / 63 / 9 / 3 / 33 |
| 37 | 215.6 | 8.6 / 12.8 / 0.4 / 0.9 / 1.3 / 1.1 | 282 / 152 / 12 / 31 | 233 / 58 / 19 / 7 / 160 |
| 38 | 222.8 | 8.4 / 13.2 / 0.4 / 0.8 / 1.3 / 1.2 | 199 / 51 / 16 / 18 | 187 / 43 / 18 / 18 / 18 |
| 39 | 215.1 | 8.8 / 12.9 / 0.4 / 0.9 / 1.2 / 1.2 | 154 / 43 / 12 / 12 | 143 / 38 / 0 / 20 / 20 |
| 40 | 218.5 | 8.9 / 12.9 / 0.4 / 0.9 / 1.3 / 1.2 | 223 / 99 / 13 / 2 | 179 / 40 / 81 / 7 / 30 |
| 41 | 213.7 | 9.0 / 13.6 / 0.4 / 1.0 / 1.3 / 1.3 | 255 / 43 / 12 / 0 | 233 / 37 / 33 / 0 / 7 |
| 42 | 211.8 | 8.8 / 13.3 / 0.4 / 1.0 / 1.3 / 1.3 | 302 / 115 / 12 / 0 | 244 / 34 / 55 / 77 / 19 |
| 43 | 221.5 | 8.3 / 13.0 / 0.4 / 1.0 / 1.3 / 1.3 | 287 / 33 / 12 / 0 | 231 / 34 / 44 / 15 / 8 |
| 44 | 220.8 | 8.5 / 12.6 / 0.4 / 1.0 / 1.3 / 1.3 | 205 / 42 / 17 / 0 | 178 / 34 / 30 / 0 / 22 |
| 45 | 217.0 | 8.5 / 12.3 / 0.4 / 0.9 / 1.2 / 1.2 | 171 / 52 / 28 / 2 | 153 / 36 / 43 / 1 / 20 |
| 46 | 214.8 | 8.4 / 11.9 / 0.4 / 1.0 / 1.2 / 1.2 | 163 / 46 / 36 / 0 | 144 / 58 / 18 / 0 / 25 |
| 47 | 218.5 | 8.0 / 11.3 / 0.4 / 1.0 / 1.1 / 1.2 | 191 / 47 / 36 / 1 | 143 / 90 / 31 / 1 / 10 |
| 48 | 226.0 | 7.9 / 11.2 / 0.4 / 1.0 / 1.1 / 1.2 | 117 / 46 / 36 / 8 | 119 / 70 / 14 / 4 / 0 |
| 49 | 217.8 | 8.4 / 11.1 / 0.4 / 1.0 / 1.2 / 1.2 | 97 / 47 / 36 / 11 | 106 / 53 / 11 / 7 / 14 |

#### The step at slot 33

Block and aggregate P3 activate one epoch after graft, around slot 30 in this run, and their deficit penalties start
then: from slot 30, blocks 6–36 and aggregates 0–31 per slot over all observers, against 100–370 for PQ and 30–380
for attestations. The coordinator's hypothesis: a full block or aggregate deficit costs the whole max positive score
(157.5) in Teku, Lodestar and Nimbus views, so it turns the far-region hosts negative there, and a negative score
prunes them from every mesh, PQ included. The per-host data do not support it. Means per slot, slots 16–32 → 33–49:

| host | PQ prunes received | views scoring it negative (of them Teku / Lodestar / Nimbus) | median negative score in Teku / Lodestar / Nimbus views | inbound PQ mesh links |
|---|---|---|---|---|
| 640 (Prysm, Sydney) | 23.3 → 14.4 | 22.0 → 17.1 (2.1 → 1.6) | −19.5 → −10.2 | 110.6 → 108.4 |
| 557 (Prysm, Tokyo) | 19.9 → 9.7 | 11.5 → 8.7 (3.3 → 1.8) | −44.8 → −0.6 | 120.1 → 124.2 |
| 420 (Lighthouse, Sydney) | 28.1 → 18.2 | 53.1 → 41.2 (2.5 → 3.6) | −210.1 → −15.4 | 75.8 → 76.5 |
| 308 (Prysm, Seoul) | 31.0 → 17.2 | 16.2 → 10.7 (1.4 → 1.0) | −30.9 → −16.7 | 72.0 → 78.3 |
| control: 53 far-region 1 Gbit hosts, never incomplete | 12.6 → 11.9 | 15.4 → 13.9 (0.9 → 1.2) | −593 → −187 | 97.5 → 97.1 |

- From slot 33 the four hosts receive fewer prunes, fewer views score them negative, Teku, Lodestar and Nimbus views
  included (1–4 per slot), and they keep or gain inbound PQ mesh links.
- Most negative views are Lighthouse views, where block and aggregate P3 is negligible (weight −topic_weight).
- In Teku, Lodestar and Nimbus views block and aggregate deficits are rare: from slot 15, 22–40 aggregate and 0–1
  block penalties per client in total, against 260–730 for PQ.
- So the step is not a scoring or mesh effect that these metrics show; its cause is not established (30-minute budget).
  The per-slot P3 split above now has an aggregate column.

### 1,024 hosts × 50 slots, 2.4 kB, 16 signatures per message: `L-pq-b16-2k4-ps100-cf2-s1` (cf2, long horizon)

×1.0, `--msg-bytes 2458 --batch 16`, seed 1, P3 rate from the run's own 50-slot mean, Shadow build `current`. Same
hosts and seed as `L-pq-2k4-ps100-cf2-s1`; one host is 0.27 % of the 1 Gbit class.

- **Strict rule: PASS with margin.** 50/15 and 50/25 100 % in every slot. 1 Gbit ≥ 99.45 % in every slot (slot 49:
  2 of ~366 hosts; the rule allows 3). Only 5 node·slots are incomplete in slots 2–49, all on 1 Gbit hosts (late 3,
  near miss 2), and no host misses more than three slots (719, Lighthouse, Sydney: 3).
- **It levels off.** Means over slots 2–15, 16–29, 30–39 and 40–49, and the slope over slots 30–49:

| series | 2–15 | 16–29 | 30–39 | 40–49 | slope, slots 30–49, per 10 slots |
|---|---|---|---|---|---|
| 1 Gbit complete (%) | 99.96 | 100 | 100 | 99.92 | −0.11 points |
| PQ missing at 8 s, 1 Gbit (%) | 0.0014 | 0 | 0 | 0.0012 | – |
| BLS attestations missing, 50/15 / 50/25 / 1 Gbit (%) | 0.074 / 0.032 / 0.79 | 0.082 / 0.014 / 1.21 | 0.053 / 0.021 / 1.38 | 0.124 / 0.025 / 1.13 | 1 Gbit −12 % |
| links per node | 219.6 | 217.8 | 217.5 | 217.9 | 0 % |
| PQ mesh degree, 1 Gbit | 7.13 | 7.02 | 6.95 | 6.94 | 0 % |
| negative-score peers per observer, Lighthouse / other | 8.4 / 13.7 | 7.8 / 11.5 | 7.0 / 11.4 | 6.6 / 10.4 | −6 / −6 % |
| same, Teku / Lodestar / Nimbus / Prysm | 0.06 / 0.06 / 0.06 / 0.08 | 0.39 / 0.59 / 0.46 / 0.19 | 0.59 / 0.84 / 0.63 / 0.23 | 0.76 / 1.05 / 0.72 / 0.28 | +27 / +21 / +14 / +25 % |
| P3 deficits per slot, PQ / attestation / block / aggregate | 71 / 46 / 0 / 0 | 2,311 / 281 / 0 / 0 | 1,933 / 85 / 14 / 6 | 1,830 / 57 / 5 / 4 | −11 / −55 / −52 / +32 % |
| P3 in Lighthouse / other / Teku / Lodestar / Nimbus views | 51 / 17 / 24 / 7 / 17 | 2,003 / 506 / 33 / 20 / 30 | 1,454 / 493 / 26 / 19 / 47 | 1,432 / 375 / 13 / 22 / 55 | −8 / −31 / −60 / −3 / +15 % |
| after-deadline PQ kB per 1 Gbit node | 864 | 1,234 | 1,377 | 1,488 | +8 % |
| after-deadline PQ kB per 50/15 node | 26 | 37 | 35 | 44 | +19 % |
| after-deadline PQ kB per 50/25 node | 22 | 36 | 43 | 44 | +3 % |

  - The PQ P3 deficit, which grew from 1.3k to 2.5k per slot over slots 15–19 in `R20-pq-b16-2k4-ps100-cf2-s1`,
    peaks at slot 20 here (2,731 over 1,024 hosts) and then declines (2,107 at slot 29, 1,712 at slot 39, 1,472 at
    slot 49). It is about 9× the unbundled run's (201–266 per slot), and about three quarters of it is in Lighthouse
    views, where a deficit costs little. Negative-score peers decline in Lighthouse and other views. In Teku, Lodestar and Nimbus
    views they still rise at slot 49 but stay below about one per observer (0.72–1.05), under the unbundled run's
    0.98–1.24.
  - After-deadline PQ bytes grow less with each block (+370, +143, +111 kB). Background bgexcess stays ≤ 1.007; the
    PQ ratio varies between 0.96 and 1.06 around 1.00 with the bundle sizes, without a trend.
  - Home hosts hold every PQ message by the deadline in every slot, so their after-deadline bytes are late copies.
    They are about half the unbundled run's. They level off in the 50/25 class (22 → 36 → 43 → 44 kB per block,
    +3 % per 10 slots over slots 30–49) but not in the 50/15 class (26 → 37 → 35 → 44 kB, +19 %; 1 Gbit +8 %). In
    10-slot blocks from slot 2: 50/15 23, 32, 38, 35, 44 kB; 50/25 19, 30, 37, 43, 44 kB.
- **Against the unbundled run** (`L-pq-2k4-ps100-cf2-s1`, same hosts and seed): 1 Gbit completeness 99.92–100 %
  against 99.48–99.84 % per block, 5 incomplete node·slots against 54, no step around slot 33, and fewer BLS misses
  (1 Gbit 0.79–1.38 % against 1.21–1.66 %).
- **PQ vs BLS**, slots 2–15 and 16–49: PQ missing 0.0014 / 0.0003 % on 1 Gbit hosts (home 0); attestations
  0.074 / 0.032 / 0.79 % and 0.085 / 0.019 / 1.24 %.
- **Other.** Latency p99 from publish 0.49 / 0.43 / 0.56 s; κ 9.4–9.6; 9 signatures lost to churn, no refused
  publish. Peak 125.3 GiB PSS; wall 14,773 s.

Delivery per slot, `L-pq-b16-2k4-ps100-cf2-s1` (1 Gbit = cloud class; PQ and BLS misses at 8 s; after-deadline PQ kB per node, 8-16 s)

| slot | complete 50/15 / 50/25 / 1 Gbit (%) | PQ missing, 1 Gbit (%) | BLS attestations missing, 50/15 / 50/25 / 1 Gbit (%) | after-deadline PQ kB, 50/15 / 50/25 / 1 Gbit | late first PQ deliveries (8-16 s), 1 Gbit host mean |
|---|---|---|---|---|---|
| 0 | 100.00 / 100.00 / 100.00 | – | – / – / – | 9 / 7 / 92 | 0.00 |
| 1 | 100.00 / 100.00 / 100.00 | – | – / – / – | 5 / 9 / 210 | 0.00 |
| 2 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.000 / 0.309 | 11 / 8 / 387 | 0.00 |
| 3 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.000 / 0.507 | 14 / 14 / 489 | 0.00 |
| 4 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.031 / 0.000 / 0.676 | 11 / 17 / 612 | 0.00 |
| 5 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.131 / 0.036 / 0.819 | 24 / 24 / 732 | 0.00 |
| 6 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.097 / 0.000 / 0.740 | 22 / 22 / 769 | 0.00 |
| 7 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.078 / 0.000 / 0.962 | 38 / 20 / 822 | 0.00 |
| 8 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.189 / 0.060 / 0.861 | 34 / 26 / 903 | 0.00 |
| 9 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.290 / 0.010 / 0.894 | 32 / 20 / 956 | 0.00 |
| 10 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.030 / 0.748 | 22 / 24 / 978 | 0.00 |
| 11 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.015 / 0.066 / 0.948 | 24 / 26 / 1031 | 0.00 |
| 12 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.071 / 0.813 | 31 / 27 / 1133 | 0.00 |
| 13 | 100.00 / 100.00 / 99.73 | 0.0111 | 0.000 / 0.092 / 1.012 | 41 / 28 / 1108 | 0.07 |
| 14 | 100.00 / 100.00 / 99.73 | 0.0085 | 0.083 / 0.067 / 0.889 | 28 / 28 / 1069 | 0.06 |
| 15 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.122 / 0.015 / 0.832 | 32 / 29 / 1112 | 0.00 |
| 16 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.045 / 0.014 / 1.066 | 34 / 33 / 1161 | 0.00 |
| 17 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.205 / 0.005 / 1.127 | 36 / 35 / 1118 | 0.00 |
| 18 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.077 / 0.025 / 1.256 | 36 / 30 / 1202 | 0.00 |
| 19 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.124 / 0.030 / 1.187 | 36 / 36 / 1417 | 0.00 |
| 20 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.099 / 0.026 / 1.253 | 26 / 34 / 1284 | 0.00 |
| 21 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.123 / 0.000 / 1.156 | 32 / 35 / 1165 | 0.00 |
| 22 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.010 / 1.033 | 42 / 33 / 1149 | 0.00 |
| 23 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.300 / 0.000 / 1.113 | 43 / 37 / 1323 | 0.00 |
| 24 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.016 / 0.036 / 1.316 | 38 / 38 / 1268 | 0.00 |
| 25 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.016 / 0.000 / 1.180 | 37 / 34 / 1230 | 0.00 |
| 26 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.032 / 0.000 / 1.350 | 41 / 41 / 1317 | 0.00 |
| 27 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.063 / 0.036 / 1.327 | 38 / 37 / 1152 | 0.00 |
| 28 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.015 / 1.367 | 45 / 41 / 1252 | 0.00 |
| 29 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.047 / 0.005 / 1.215 | 37 / 40 / 1232 | 0.00 |
| 30 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.025 / 1.193 | 40 / 39 / 1348 | 0.00 |
| 31 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.031 / 0.005 / 1.531 | 43 / 42 / 1334 | 0.00 |
| 32 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.031 / 0.005 / 1.234 | 40 / 45 / 1326 | 0.00 |
| 33 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.046 / 0.025 / 1.402 | 33 / 44 / 1480 | 0.00 |
| 34 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.046 / 1.464 | 26 / 42 / 1459 | 0.00 |
| 35 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.005 / 1.374 | 28 / 43 / 1347 | 0.00 |
| 36 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.139 / 0.034 / 1.564 | 28 / 43 / 1329 | 0.00 |
| 37 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.046 / 0.058 / 1.288 | 35 / 44 / 1398 | 0.00 |
| 38 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.240 / 0.005 / 1.478 | 42 / 46 / 1393 | 0.00 |
| 39 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.000 / 1.278 | 32 / 47 / 1356 | 0.00 |
| 40 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.016 / 0.005 / 0.894 | 41 / 46 / 1461 | 0.00 |
| 41 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.047 / 0.005 / 1.066 | 45 / 39 / 1320 | 0.00 |
| 42 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.010 / 1.126 | 36 / 39 / 1420 | 0.00 |
| 43 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.110 / 0.051 / 1.195 | 40 / 40 / 1414 | 0.00 |
| 44 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.234 / 0.015 / 1.255 | 48 / 45 / 1519 | 0.00 |
| 45 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.444 / 0.000 / 1.121 | 39 / 45 / 1416 | 0.00 |
| 46 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.076 / 0.044 / 1.225 | 38 / 47 / 1538 | 0.00 |
| 47 | 100.00 / 100.00 / 99.73 | 0.0004 | 0.000 / 0.015 / 0.845 | 53 / 45 / 1715 | 0.00 |
| 48 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.207 / 0.051 / 1.105 | 48 / 42 / 1589 | 0.00 |
| 49 | 100.00 / 100.00 / 99.45 | 0.0116 | 0.107 / 0.055 / 1.445 | 49 / 48 / 1488 | 0.08 |

Scoring per slot, `L-pq-b16-2k4-ps100-cf2-s1` (mesh snapshot at 3.95 s; negative-score peers per observer; P3 = MessageDeficit penalties summed over hosts in the slot; Prysm applies no P3)

| slot | links/node | negative peers per observer: Lighthouse / other / Prysm / Teku / Lodestar / Nimbus | P3 by topic: PQ / attestation / block / aggregate | P3 in the views of Lighthouse / other / Teku / Lodestar / Nimbus |
|---|---|---|---|---|
| 0 | 213.7 | 0.0 / 0.0 / 0.0 / 0.0 / 0.0 / 0.0 | – / – / – / – | – / – / – / – / – |
| 1 | 203.7 | 3.5 / 5.7 / 0.0 / 0.0 / 0.0 / 0.0 | – / – / – / – | – / – / – / – / – |
| 2 | 214.8 | 6.2 / 10.6 / 0.0 / 0.0 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 3 | 226.4 | 8.0 / 13.9 / 0.0 / 0.0 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 4 | 215.0 | 9.8 / 16.1 / 0.0 / 0.0 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 5 | 215.5 | 9.7 / 15.6 / 0.1 / 0.0 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 6 | 217.9 | 8.9 / 14.6 / 0.1 / 0.0 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 7 | 213.9 | 8.4 / 14.1 / 0.1 / 0.1 / 0.1 / 0.1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 8 | 225.6 | 7.8 / 13.5 / 0.1 / 0.1 / 0.1 / 0.1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 9 | 225.3 | 8.3 / 13.7 / 0.1 / 0.1 / 0.1 / 0.1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 10 | 217.8 | 8.6 / 13.9 / 0.1 / 0.1 / 0.1 / 0.1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 11 | 215.7 | 8.5 / 13.9 / 0.1 / 0.1 / 0.1 / 0.1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 12 | 222.8 | 8.1 / 13.7 / 0.1 / 0.1 / 0.1 / 0.1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 13 | 225.4 | 8.1 / 13.2 / 0.1 / 0.1 / 0.1 / 0.1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 14 | 220.5 | 8.4 / 12.8 / 0.1 / 0.1 / 0.1 / 0.1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 15 | 217.3 | 8.1 / 12.3 / 0.1 / 0.1 / 0.1 / 0.1 | 988 / 645 / 0 / 0 | 710 / 243 / 340 / 103 / 237 |
| 16 | 222.7 | 7.9 / 12.1 / 0.2 / 0.3 / 0.4 / 0.3 | 2137 / 389 / 0 / 0 | 1790 / 557 / 75 / 40 / 64 |
| 17 | 216.2 | 8.0 / 12.5 / 0.1 / 0.3 / 0.4 / 0.3 | 2141 / 415 / 0 / 0 | 1873 / 514 / 55 / 33 / 81 |
| 18 | 224.0 | 7.9 / 11.9 / 0.2 / 0.4 / 0.5 / 0.4 | 2356 / 340 / 0 / 0 | 2044 / 555 / 28 / 31 / 38 |
| 19 | 223.0 | 8.1 / 12.0 / 0.2 / 0.4 / 0.5 / 0.4 | 2591 / 379 / 0 / 0 | 2262 / 606 / 16 / 29 / 57 |
| 20 | 215.2 | 8.2 / 12.5 / 0.2 / 0.4 / 0.6 / 0.4 | 2731 / 370 / 0 / 0 | 2357 / 632 / 24 / 37 / 51 |
| 21 | 210.3 | 8.0 / 12.3 / 0.2 / 0.4 / 0.6 / 0.5 | 2588 / 385 / 0 / 0 | 2368 / 511 / 18 / 45 / 31 |
| 22 | 209.8 | 7.8 / 11.1 / 0.2 / 0.4 / 0.6 / 0.5 | 2429 / 342 / 0 / 0 | 2265 / 416 / 33 / 28 / 29 |
| 23 | 225.8 | 7.3 / 10.4 / 0.2 / 0.4 / 0.7 / 0.5 | 2281 / 288 / 0 / 0 | 2110 / 405 / 46 / 7 / 1 |
| 24 | 217.0 | 7.9 / 10.7 / 0.2 / 0.4 / 0.7 / 0.5 | 2163 / 264 / 0 / 0 | 1992 / 375 / 50 / 10 / 0 |
| 25 | 214.4 | 7.7 / 11.0 / 0.2 / 0.4 / 0.6 / 0.5 | 2132 / 243 / 0 / 0 | 1902 / 421 / 43 / 1 / 8 |
| 26 | 220.1 | 7.5 / 10.7 / 0.2 / 0.4 / 0.6 / 0.5 | 2358 / 159 / 0 / 0 | 1947 / 518 / 27 / 3 / 22 |
| 27 | 214.0 | 7.6 / 10.9 / 0.2 / 0.5 / 0.7 / 0.5 | 2222 / 127 / 0 / 0 | 1790 / 529 / 17 / 0 / 13 |
| 28 | 221.8 | 7.4 / 11.1 / 0.2 / 0.4 / 0.7 / 0.6 | 2113 / 113 / 0 / 0 | 1687 / 520 / 18 / 0 / 1 |
| 29 | 215.0 | 7.5 / 11.2 / 0.2 / 0.4 / 0.7 / 0.6 | 2107 / 125 / 0 / 0 | 1661 / 520 / 16 / 17 / 18 |
| 30 | 221.3 | 7.4 / 11.3 / 0.2 / 0.5 / 0.7 / 0.6 | 2167 / 131 / 11 / 2 | 1667 / 558 / 21 / 40 / 25 |
| 31 | 217.6 | 7.5 / 11.6 / 0.2 / 0.5 / 0.8 / 0.6 | 2160 / 112 / 24 / 0 | 1662 / 560 / 7 / 41 / 26 |
| 32 | 213.2 | 7.1 / 11.3 / 0.2 / 0.5 / 0.9 / 0.6 | 2023 / 105 / 14 / 0 | 1555 / 512 / 2 / 18 / 55 |
| 33 | 227.1 | 6.8 / 11.0 / 0.2 / 0.5 / 0.9 / 0.6 | 1981 / 84 / 3 / 2 | 1465 / 530 / 8 / 0 / 67 |
| 34 | 218.1 | 7.1 / 11.2 / 0.2 / 0.5 / 0.8 / 0.6 | 1895 / 75 / 0 / 1 | 1385 / 545 / 20 / 1 / 20 |
| 35 | 212.2 | 7.3 / 11.7 / 0.2 / 0.6 / 0.7 / 0.6 | 1832 / 202 / 9 / 6 | 1348 / 502 / 163 / 5 / 31 |
| 36 | 210.5 | 7.0 / 11.5 / 0.2 / 0.7 / 0.9 / 0.6 | 1908 / 34 / 25 / 18 | 1451 / 439 / 24 / 13 / 58 |
| 37 | 218.4 | 6.8 / 11.6 / 0.3 / 0.7 / 0.9 / 0.7 | 1886 / 30 / 16 / 12 | 1420 / 402 / 12 / 29 / 81 |
| 38 | 220.6 | 6.5 / 11.7 / 0.3 / 0.7 / 0.9 / 0.7 | 1767 / 33 / 24 / 8 | 1318 / 430 / 3 / 20 / 61 |
| 39 | 215.8 | 6.6 / 10.9 / 0.3 / 0.7 / 0.9 / 0.7 | 1712 / 47 / 18 / 11 | 1270 / 452 / 0 / 18 / 48 |
| 40 | 220.5 | 6.4 / 10.5 / 0.3 / 0.7 / 0.9 / 0.7 | 1914 / 52 / 12 / 1 | 1436 / 453 / 14 / 20 / 56 |
| 41 | 215.7 | 6.6 / 10.6 / 0.2 / 0.7 / 1.0 / 0.7 | 2175 / 90 / 2 / 0 | 1724 / 436 / 46 / 0 / 61 |
| 42 | 212.2 | 6.7 / 10.5 / 0.2 / 0.8 / 1.0 / 0.7 | 2052 / 114 / 0 / 0 | 1646 / 412 / 0 / 60 / 48 |
| 43 | 221.4 | 6.4 / 10.2 / 0.3 / 0.7 / 1.0 / 0.7 | 1924 / 52 / 0 / 1 | 1494 / 407 / 6 / 15 / 55 |
| 44 | 221.3 | 6.7 / 9.8 / 0.3 / 0.7 / 1.1 / 0.7 | 1829 / 57 / 0 / 1 | 1344 / 410 / 18 / 32 / 83 |
| 45 | 216.1 | 6.8 / 10.1 / 0.3 / 0.8 / 1.1 / 0.7 | 1820 / 24 / 0 / 6 | 1357 / 402 / 0 / 29 / 62 |
| 46 | 213.3 | 6.8 / 10.1 / 0.3 / 0.8 / 1.1 / 0.7 | 1882 / 36 / 0 / 12 | 1479 / 376 / 7 / 12 / 56 |
| 47 | 219.1 | 6.4 / 10.1 / 0.3 / 0.8 / 1.1 / 0.7 | 1686 / 43 / 9 / 7 | 1357 / 314 / 7 / 11 / 56 |
| 48 | 222.5 | 6.5 / 11.0 / 0.3 / 0.8 / 1.1 / 0.8 | 1542 / 46 / 14 / 13 | 1264 / 278 / 15 / 18 / 40 |
| 49 | 217.1 | 6.8 / 11.2 / 0.3 / 0.8 / 1.1 / 0.8 | 1472 / 57 / 12 / 0 | 1218 / 257 / 12 / 19 / 35 |

### 1,024 hosts × 50 slots, 2.4 kB, 16 signatures per message, rtt6 (Linux's CUBIC with HyStart): `L-pq-b16-2k4-rtt6-ps100-cf2-s1` (cf2, long horizon)

`L-pq-b16-2k4-ps100-cf2-s1`'s flags (×1.0, `--msg-bytes 2458 --batch 16`, seed 1, P3 rate 42.4625 from that run's
50-slot mean) on rtt6, the build closest to stock Linux (rtt5 with its three switches on plus Linux's CUBIC and
HyStart; see Loss and TCP in [Caveats](#caveats)), with TCP logging. Same hosts and seed as the two current-build L
runs; one host is 0.27 % of the 1 Gbit class.

- **Strict rule: PASS, with no host to spare in its worst slot.** 50/15 and 50/25 100 % in every slot. 1 Gbit hosts
  are at ≥ 99.45 % in every slot from slot 2 except slot 15, at 99.18 % (3 of ~366 hosts; the rule allows 3). 30
  node·slots are incomplete in slots 2–49, all on 1 Gbit hosts (late 14, near miss 14, never received 2), against 5
  on the current build. No host is chronic: the most frequent are 640 (Prysm, Sydney, 70 peers) in 12 of 48 slots,
  273 (Prysm, Sydney) in 5, and 420 and 612 (Lighthouse, Sydney) in 3 each.
- **It levels off.** Means over slots 2–15, 16–29, 30–39 and 40–49, and the slope over slots 30–49:

| series | 2–15 | 16–29 | 30–39 | 40–49 | slope, slots 30–49, per 10 slots |
|---|---|---|---|---|---|
| 1 Gbit complete (%) | 99.81 | 99.83 | 99.84 | 99.86 | +0.09 points |
| PQ missing at 8 s, 1 Gbit (%) | 0.0018 | 0.0014 | 0.0056 | 0.0015 | – |
| BLS attestations missing, 50/15 / 50/25 / 1 Gbit (%) | 0.052 / 0.016 / 1.48 | 0.030 / 0.009 / 1.79 | 0.047 / 0.023 / 1.97 | 0.036 / 0.056 / 1.93 | 1 Gbit −1 % |
| links per node | 215.1 | 215.3 | 214.9 | 215.9 | 0 % |
| PQ mesh degree, 1 Gbit | 7.08 | 6.98 | 6.93 | 6.92 | 0 % |
| negative-score peers per observer, Lighthouse / other | 10.8 / 17.9 | 9.3 / 14.6 | 8.2 / 12.1 | 7.8 / 10.7 | −6 / −11 % |
| same, Teku / Lodestar / Nimbus / Prysm | 0.07 / 0 / 0.03 / 0.09 | 0.39 / 0.34 / 0.29 / 0.20 | 0.52 / 0.46 / 0.46 / 0.24 | 0.50 / 0.56 / 0.59 / 0.30 | −1 / +18 / +23 / +23 % |
| P3 deficits per slot, PQ / attestation / block / aggregate | 92 / 48 / 0 / 0 | 2,516 / 295 / 0 / 0 | 1,345 / 124 / 35 / 6 | 1,095 / 81 / 50 / 0.5 | −22 / −43 / +15 / – % |
| P3 in Lighthouse / other / Teku / Lodestar / Nimbus views | 53 / 39 / 21 / 7 / 21 | 1,729 / 917 / 76 / 22 / 67 | 1,118 / 335 / 12 / 13 / 32 | 895 / 260 / 34 / 12 / 26 | −22 / −29 / +72 / +10 / −67 % |
| after-deadline PQ kB per 1 Gbit node | 623 | 895 | 1,011 | 1,110 | +6 % |
| after-deadline PQ kB per 50/15 node | 27 | 38 | 44 | 46 | +2 % |
| after-deadline PQ kB per 50/25 node | 23 | 28 | 30 | 32 | +5 % |

  - **Backlog test.** Messages first delivered after the deadline average 0.01, 0.01, 0.01, 0.04 and 0.01 per 1 Gbit
    node per slot in the 10-slot blocks from slot 2 (at most 0.16, slot 33; current build at most 0.08), and none on
    home hosts. Over slots 2–49 they sum to 0.75 per 1 Gbit node, against 2.3 messages missing at 8 s. No copy is
    older than 60 s (current build up to 0.10 per node per slot). So no backlog builds up.
  - **After-deadline copies**, mean per node per 10-slot block from slot 2, against the current build (in brackets):

| slots | 50/15 (kB) | 50/25 (kB) | 1 Gbit (kB) | late first deliveries per 1 Gbit node per slot |
|---|---|---|---|---|
| 2–9 | 23.7 (23.3) | 20.4 (18.8) | 483 (709) | 0.01 (0.00) |
| 10–19 | 31.8 (32.1) | 27.8 (29.5) | 817 (1,133) | 0.01 (0.01) |
| 20–29 | 39.7 (38.0) | 27.7 (37.0) | 921 (1,237) | 0.01 (0.00) |
| 30–39 | 44.2 (34.5) | 30.1 (43.4) | 1,011 (1,377) | 0.04 (0.00) |
| 40–49 | 45.9 (43.8) | 32.2 (43.5) | 1,110 (1,488) | 0.01 (0.01) |

    1 Gbit hosts get 25–32 % fewer late copies than on the current build. After slot 20 each block adds 90–104 kB
    (current build 104–140 kB), +6 % per 10 slots over slots 30–49 (current build +8 %): the growth slows but has not
    stopped by slot 49. The home classes nearly level off: the last block adds 1.7 kB (50/15) and 2.1 kB (50/25), +2 and
    +5 % per 10 slots. Late copies per 1 Gbit node in 8–16 s rise from 8 at slot 0 to 130 at slot 49 (current build 10
    → 190). Background bgexcess stays ≤ 1.014 and the PQ ratio between 0.97 and 1.06 around 1.00, so nothing re-floods;
    stale copies: PQ 0, background 2,125 (current build 1,049 and 122,923).
  - The PQ P3 deficit peaks in slots 16–29 (2,516 per slot over 1,024 hosts) and then declines (1,345, then 1,095;
    current build 2,311, 1,933 and 1,830); two thirds to three quarters of it is in Lighthouse views. Negative-score
    peers decline in Lighthouse and other views. In Teku, Lodestar and Nimbus views they rise to 0.50–0.59 per
    observer in slots 40–49, below the current build's 0.72–1.05.
- **Against the current build** (`L-pq-b16-2k4-ps100-cf2-s1`, same hosts and seed): 1 Gbit completeness 99.81–99.86 %
  per block against 99.92–100 %; 30 incomplete node·slots against 5; PQ latency p99 from publish 0.65 / 0.58 /
  0.69 s against 0.49 / 0.43 / 0.56 s; blocks from publish p50 / p95 / p99 0.33 / 0.67 / 0.88 s against 0.17 / 0.36 /
  0.53 s. Block p95 per 10-slot block is 0.70, 0.61, 0.67, 0.63 and 0.61 s (current build 0.30, 0.33, 0.37, 0.39 and
  0.35 s), so the slowdown does not grow over 50 slots. 1 Gbit BLS misses are higher (1.48 / 1.88 % in slots 2–15 /
  16–49 against 0.79 / 1.24 %), and late copies fewer (above).
- **PQ vs BLS**, slots 2–15 and 16–49: PQ missing 0.0017 / 0.0027 % on 1 Gbit hosts (home 0); attestations
  0.052 / 0.016 / 1.48 % and 0.037 / 0.027 / 1.88 % (all-64-subnet hosts 1.66 / 2.12 %, 2-subnet 1 Gbit hosts 0.054 /
  0.021 %). No matched no-PQ run exists on rtt6 at 1,024 hosts.
- **TCP**, per 10-slot block (slots 2–9, 10–19, 20–29, 30–39, 40–48):

| path | first timeouts per 1,000 data packets | resends per 1,000 data packets | cwnd p50 / p90 at the block's end (segments) | ssthresh p50 after restarts at the block's end |
|---|---|---|---|---|
| 1G→1G | 0.10 / 0.12 / 0.14 / 0.14 / 0.15 | 0.28 / 0.28 / 0.29 / 0.29 / 0.29 | 10/20, 10/25, 10/20, 10/20, 10/20 | 112 / 96 / 91 / 90 / 85 |
| 1G→home | 4.21 / 5.67 / 6.32 / 6.97 / 7.42 | 3.33 / 3.33 / 3.41 / 3.47 / 3.51 | 10/18, 10/19, 10/18, 10/18, 10/18 | 32 / 25 / 23 / 22 / 21 |
| home→1G | 1.32 / 2.00 / 2.52 / 2.84 / 3.25 | 1.79 / 1.92 / 2.03 / 2.11 / 2.19 | 10/18, 10/20, 10/18, 10/18, 10/17 | 72 / 40 / 35 / 31 / 28 |
| home→home | 12.13 / 16.46 / 18.56 / 19.61 / 20.35 | 9.12 / 8.71 / 8.98 / 9.12 / 9.18 | 10/17, 10/17, 10/15, 10/15, 10/15 | 21 / 15 / 13 / 13 / 12 |

  - The first-timeout climb slows (home→home +4.3, +2.1, +1.1 and +0.7 per block; 1G→home +1.5, +0.7, +0.7 and
    +0.5) but has not stopped by slot 48. Resends stay flat.
  - Windows do not grow: cwnd p50 is 10 segments and p90 15–25 at every block end (over the run 10 / 22, 10 / 18,
    10 / 19 and 10 / 16), because each restart after idle sets cwnd back to 10 or close to it. There are 36.4M restarts, about
    725k per slot (4–7 per data-sending endpoint per slot), roughly flat over the run; cwnd before → after p50 (p90)
    10 (51) → 10 (15) on 1G→1G and 10 (20–27) → 10 (10) elsewhere. 89 % leave cwnd below ssthresh, and all of those
    continue in slow start. Idle time before a restart is ~1 s at p50, against an RTO p50 of 0.29–0.38 s.
  - ssthresh after restarts falls fast over the first ten slots and then levels off (1G→1G 386 at slot 3 → 96 at slot
    19 → 85 at slot 48; home→home 58 at slot 6 → 15 → 12).
  - rtt6 counters: data packets sent with cwnd ≥ ssthresh 69.7 % (1G→1G), 73.7 % (1G→home), 72.3 % (home→1G) and
    73.6 % (home→home). HyStart exits, train / delay: 8,709 / 2, 925 / 2,322, 1,488 / 5,477 and 3 / 2,716 (cwnd at
    exit p50 28, 115, 78 and 108 segments). CUBIC targets equal Linux's integer formula in all 488,886 traced
    recomputations, all 371,915 traced epoch shifts follow Linux, and no congestion-avoidance round grows by more than
    half the ACKed packets + 1.
  - Fast-recovery entries per 1,000 data packets 0.25, 1.49, 1.44 and 2.33, all after consecutive duplicate ACKs.
    11.42M RTOs; 97.5 % of 6.40M Eifel checks found the timeout spurious and undid it. SRTT − configured RTT p50 / p99
    2 / 6, 8 / 111, 5 / 12 and 11 / 126 ms; 99.7 % of ACKs of new data echo the first segment they newly acknowledge.
    No stalls (7.93M snapshots); the RTO formula holds in all 7,309,987 snapshots without backoff.
- **Other.** PQ latency p50 / p99 from publish 0.10 / 0.65 s (50/15), 0.09 / 0.58 s (50/25), 0.08 / 0.69 s (1 Gbit);
  κ 9.2–10.0 per slot from slot 2 (current build 9.0–10.0); PQ copies per message 4.3–4.8 (current build 4.2–4.7); IDONTWANT 7.8–9.2k ids per node per slot (current build 7.4–9.1k).
  Upload in the 4 s window, mean / max node, % of cap: 40 / 61 (50/15), 26 / 39 (50/25), 5 / 12 (1 Gbit); download
  ≤ 13 / 23. Connections 156 / 163 / 167 per node by class (Prysm 71). Failed sends that cost score: 85.8M over 50
  slots (forward timeout 55.9 %, forward queue full 41.1 %, control queue full 2.9 %; current build 86.0M). 9
  signatures lost to churn, no refused publish. Peak 115.6 GiB PSS; wall 13,762 s.

Delivery per slot, `L-pq-b16-2k4-rtt6-ps100-cf2-s1` (1 Gbit = cloud class; PQ and BLS misses at 8 s; after-deadline PQ kB per node, 8-16 s)

| slot | complete 50/15 / 50/25 / 1 Gbit (%) | PQ missing, 1 Gbit (%) | BLS attestations missing, 50/15 / 50/25 / 1 Gbit (%) | after-deadline PQ kB, 50/15 / 50/25 / 1 Gbit | late first PQ deliveries (8-16 s), 1 Gbit host mean |
|---|---|---|---|---|---|
| 0 | 100.00 / 100.00 / 99.18 | – | – / – / – | 12 / 11 / 75 | 0.03 |
| 1 | 100.00 / 100.00 / 99.73 | – | – / – / – | 18 / 11 / 163 | 0.03 |
| 2 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.026 / 0.828 | 17 / 14 / 226 | 0.00 |
| 3 | 100.00 / 100.00 / 99.45 | 0.0058 | 0.099 / 0.021 / 1.130 | 27 / 17 / 268 | 0.04 |
| 4 | 100.00 / 100.00 / 99.73 | 0.0045 | 0.079 / 0.000 / 1.402 | 20 / 19 / 399 | 0.03 |
| 5 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.016 / 0.010 / 1.537 | 24 / 22 / 465 | 0.00 |
| 6 | 100.00 / 100.00 / 99.73 | 0.0008 | 0.000 / 0.000 / 1.363 | 21 / 20 / 585 | 0.01 |
| 7 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.000 / 1.191 | 28 / 20 / 642 | 0.00 |
| 8 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.027 / 1.304 | 27 / 25 / 610 | 0.00 |
| 9 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.107 / 0.019 / 1.474 | 26 / 26 / 671 | 0.00 |
| 10 | 100.00 / 100.00 / 99.73 | 0.0004 | 0.016 / 0.010 / 1.838 | 28 / 27 / 755 | 0.00 |
| 11 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.005 / 1.895 | 37 / 23 / 725 | 0.00 |
| 12 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.015 / 1.719 | 30 / 24 / 842 | 0.00 |
| 13 | 100.00 / 100.00 / 99.73 | 0.0033 | 0.031 / 0.039 / 1.658 | 34 / 28 / 820 | 0.02 |
| 14 | 100.00 / 100.00 / 99.73 | 0.0037 | 0.215 / 0.021 / 1.603 | 28 / 27 / 831 | 0.02 |
| 15 | 100.00 / 100.00 / 99.18 | 0.0062 | 0.168 / 0.025 / 1.756 | 26 / 28 / 877 | 0.04 |
| 16 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.010 / 1.881 | 40 / 30 / 806 | 0.00 |
| 17 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.000 / 1.594 | 36 / 32 / 818 | 0.00 |
| 18 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.000 / 1.877 | 34 / 31 / 838 | 0.00 |
| 19 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.015 / 0.010 / 1.437 | 26 / 26 / 861 | 0.00 |
| 20 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.082 / 0.031 / 1.863 | 39 / 26 / 822 | 0.00 |
| 21 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.031 / 0.000 / 1.738 | 35 / 24 / 888 | 0.00 |
| 22 | 100.00 / 100.00 / 99.73 | 0.0020 | 0.045 / 0.000 / 1.867 | 36 / 25 / 913 | 0.01 |
| 23 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.016 / 0.000 / 1.828 | 48 / 33 / 925 | 0.00 |
| 24 | 100.00 / 100.00 / 99.73 | 0.0012 | 0.048 / 0.021 / 1.822 | 41 / 27 / 906 | 0.01 |
| 25 | 100.00 / 100.00 / 99.45 | 0.0029 | 0.032 / 0.000 / 1.657 | 36 / 27 / 905 | 0.02 |
| 26 | 100.00 / 100.00 / 99.45 | 0.0037 | 0.000 / 0.005 / 1.847 | 38 / 28 / 1021 | 0.02 |
| 27 | 100.00 / 100.00 / 99.73 | 0.0070 | 0.048 / 0.020 / 1.987 | 38 / 29 / 971 | 0.05 |
| 28 | 100.00 / 100.00 / 99.73 | 0.0004 | 0.062 / 0.025 / 2.076 | 49 / 32 / 974 | 0.00 |
| 29 | 100.00 / 100.00 / 99.73 | 0.0020 | 0.047 / 0.005 / 1.630 | 38 / 24 / 885 | 0.01 |
| 30 | 100.00 / 100.00 / 99.45 | 0.0080 | 0.016 / 0.015 / 2.106 | 49 / 30 / 1033 | 0.05 |
| 31 | 100.00 / 100.00 / 99.73 | 0.0020 | 0.000 / 0.064 / 1.957 | 40 / 31 / 974 | 0.01 |
| 32 | 100.00 / 100.00 / 99.73 | 0.0190 | 0.031 / 0.010 / 1.595 | 41 / 30 / 1014 | 0.13 |
| 33 | 100.00 / 100.00 / 99.73 | 0.0232 | 0.000 / 0.025 / 1.855 | 46 / 32 / 1039 | 0.16 |
| 34 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.046 / 0.031 / 2.225 | 52 / 29 / 1078 | 0.00 |
| 35 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.030 / 0.029 / 1.761 | 44 / 28 / 982 | 0.00 |
| 36 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.010 / 1.710 | 31 / 32 / 966 | 0.00 |
| 37 | 100.00 / 100.00 / 99.73 | 0.0040 | 0.077 / 0.034 / 1.887 | 44 / 30 / 1032 | 0.01 |
| 38 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.128 / 0.005 / 2.133 | 45 / 31 / 996 | 0.00 |
| 39 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.144 / 0.005 / 2.470 | 50 / 28 / 993 | 0.00 |
| 40 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.078 / 0.021 / 2.124 | 49 / 35 / 1177 | 0.00 |
| 41 | 100.00 / 100.00 / 99.45 | 0.0042 | 0.093 / 0.000 / 2.010 | 42 / 28 / 1072 | 0.03 |
| 42 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.030 / 0.000 / 1.868 | 44 / 35 / 1116 | 0.00 |
| 43 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.015 / 2.011 | 54 / 32 / 1141 | 0.00 |
| 44 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.109 / 0.094 / 2.037 | 44 / 35 / 1087 | 0.00 |
| 45 | 100.00 / 100.00 / 99.73 | 0.0016 | 0.033 / 0.109 / 1.869 | 50 / 28 / 1105 | 0.01 |
| 46 | 100.00 / 100.00 / 99.73 | 0.0024 | 0.000 / 0.058 / 1.895 | 39 / 30 / 1078 | 0.02 |
| 47 | 100.00 / 100.00 / 99.73 | 0.0069 | 0.000 / 0.134 / 1.676 | 47 / 34 / 1099 | 0.05 |
| 48 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.016 / 0.107 / 1.676 | 43 / 30 / 1133 | 0.00 |
| 49 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.020 / 2.109 | 47 / 35 / 1092 | 0.00 |

Scoring per slot, `L-pq-b16-2k4-rtt6-ps100-cf2-s1` (mesh snapshot at 3.95 s; negative-score peers per observer; P3 = MessageDeficit penalties summed over hosts in the slot; Prysm applies no P3)

| slot | links/node | negative peers per observer: Lighthouse / other / Prysm / Teku / Lodestar / Nimbus | P3 by topic: PQ / attestation / block / aggregate | P3 in the views of Lighthouse / other / Teku / Lodestar / Nimbus |
|---|---|---|---|---|
| 0 | 214.4 | 0.1 / 0.1 / 0.0 / 0.0 / 0.0 / 0.0 | – / – / – / – | – / – / – / – / – |
| 1 | 202.8 | 4.2 / 6.6 / 0.0 / 0.0 / 0.0 / 0.0 | – / – / – / – | – / – / – / – / – |
| 2 | 209.3 | 8.1 / 13.6 / 0.0 / 0.0 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 3 | 218.2 | 10.6 / 17.8 / 0.0 / 0.0 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 4 | 206.0 | 12.9 / 21.1 / 0.0 / 0.0 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 5 | 209.4 | 12.8 / 21.0 / 0.0 / 0.0 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 6 | 218.1 | 11.6 / 20.0 / 0.1 / 0.1 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 7 | 214.3 | 10.9 / 18.4 / 0.1 / 0.1 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 8 | 220.3 | 10.3 / 17.9 / 0.1 / 0.1 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 9 | 218.8 | 10.8 / 18.4 / 0.1 / 0.1 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 10 | 210.9 | 11.1 / 18.3 / 0.1 / 0.1 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 11 | 210.5 | 10.8 / 18.1 / 0.1 / 0.1 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 12 | 218.5 | 10.3 / 17.1 / 0.1 / 0.1 / 0.0 / 0.1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 13 | 225.4 | 10.3 / 16.9 / 0.1 / 0.1 / 0.0 / 0.1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 14 | 217.3 | 10.5 / 15.9 / 0.2 / 0.1 / 0.0 / 0.1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 15 | 214.4 | 10.1 / 16.0 / 0.2 / 0.1 / 0.0 / 0.1 | 1292 / 668 / 0 / 0 | 743 / 541 / 288 / 94 / 294 |
| 16 | 217.0 | 9.8 / 16.3 / 0.2 / 0.2 / 0.2 / 0.2 | 2925 / 355 / 0 / 0 | 1665 / 1295 / 143 / 40 / 137 |
| 17 | 211.7 | 9.6 / 15.4 / 0.2 / 0.3 / 0.2 / 0.2 | 3016 / 420 / 0 / 0 | 1830 / 1192 / 186 / 42 / 186 |
| 18 | 221.7 | 9.0 / 15.4 / 0.2 / 0.3 / 0.3 / 0.3 | 3282 / 338 / 0 / 0 | 2158 / 1186 / 187 / 30 / 59 |
| 19 | 220.6 | 9.2 / 15.4 / 0.2 / 0.4 / 0.2 / 0.3 | 3164 / 336 / 0 / 0 | 2120 / 1201 / 110 / 23 / 46 |
| 20 | 214.5 | 9.5 / 16.1 / 0.2 / 0.4 / 0.3 / 0.3 | 3217 / 343 / 0 / 0 | 2135 / 1264 / 85 / 25 / 51 |
| 21 | 211.4 | 9.6 / 15.3 / 0.2 / 0.4 / 0.3 / 0.3 | 3170 / 314 / 0 / 0 | 2167 / 1182 / 71 / 17 / 47 |
| 22 | 209.4 | 9.4 / 14.9 / 0.2 / 0.4 / 0.3 / 0.3 | 2909 / 291 / 0 / 0 | 2015 / 1058 / 52 / 29 / 46 |
| 23 | 221.4 | 9.0 / 14.4 / 0.2 / 0.3 / 0.3 / 0.3 | 2564 / 301 / 0 / 0 | 1836 / 926 / 30 / 30 / 43 |
| 24 | 212.7 | 9.5 / 14.5 / 0.2 / 0.4 / 0.3 / 0.3 | 2144 / 275 / 0 / 0 | 1586 / 768 / 18 / 27 / 20 |
| 25 | 210.7 | 9.4 / 13.8 / 0.2 / 0.4 / 0.4 / 0.3 | 2017 / 241 / 0 / 0 | 1532 / 659 / 31 / 19 / 17 |
| 26 | 217.1 | 9.1 / 13.7 / 0.2 / 0.4 / 0.4 / 0.3 | 2009 / 226 / 0 / 0 | 1555 / 579 / 53 / 13 / 35 |
| 27 | 211.1 | 9.1 / 13.6 / 0.2 / 0.5 / 0.5 / 0.3 | 1815 / 215 / 0 / 0 | 1374 / 555 / 34 / 7 / 60 |
| 28 | 221.1 | 8.8 / 12.7 / 0.2 / 0.5 / 0.5 / 0.3 | 1570 / 192 / 0 / 0 | 1173 / 518 / 6 / 0 / 65 |
| 29 | 214.4 | 9.2 / 13.1 / 0.2 / 0.5 / 0.5 / 0.4 | 1420 / 285 / 0 / 0 | 1066 / 455 / 62 / 1 / 121 |
| 30 | 215.5 | 8.7 / 12.5 / 0.2 / 0.5 / 0.5 / 0.4 | 1516 / 230 / 22 / 7 | 1201 / 423 / 20 / 6 / 125 |
| 31 | 213.1 | 8.4 / 11.9 / 0.2 / 0.5 / 0.5 / 0.4 | 1723 / 145 / 53 / 2 | 1416 / 421 / 13 / 24 / 49 |
| 32 | 210.7 | 8.0 / 12.0 / 0.2 / 0.5 / 0.5 / 0.4 | 1569 / 131 / 51 / 2 | 1298 / 379 / 8 / 19 / 49 |
| 33 | 225.9 | 7.6 / 11.6 / 0.2 / 0.5 / 0.4 / 0.4 | 1373 / 129 / 30 / 0 | 1149 / 318 / 19 / 13 / 33 |
| 34 | 217.1 | 8.2 / 12.1 / 0.2 / 0.5 / 0.4 / 0.5 | 1302 / 135 / 29 / 0 | 1064 / 339 / 32 / 7 / 24 |
| 35 | 211.7 | 8.6 / 12.6 / 0.2 / 0.5 / 0.4 / 0.5 | 1291 / 120 / 37 / 12 | 1084 / 339 / 7 / 6 / 24 |
| 36 | 209.1 | 8.5 / 12.7 / 0.3 / 0.5 / 0.4 / 0.5 | 1367 / 103 / 36 / 19 | 1142 / 343 / 5 / 26 / 9 |
| 37 | 213.0 | 8.2 / 12.0 / 0.3 / 0.6 / 0.5 / 0.5 | 1226 / 72 / 36 / 14 | 1058 / 264 / 0 / 25 / 1 |
| 38 | 219.1 | 7.9 / 11.8 / 0.3 / 0.6 / 0.5 / 0.5 | 1067 / 89 / 25 / 2 | 898 / 273 / 2 / 7 / 3 |
| 39 | 213.9 | 8.1 / 11.3 / 0.3 / 0.5 / 0.5 / 0.5 | 1016 / 89 / 31 / 2 | 872 / 249 / 13 / 1 / 3 |
| 40 | 217.3 | 8.0 / 11.0 / 0.3 / 0.5 / 0.5 / 0.6 | 1089 / 58 / 59 / 3 | 910 / 254 / 36 / 0 / 9 |
| 41 | 213.0 | 8.2 / 11.2 / 0.3 / 0.5 / 0.5 / 0.5 | 1192 / 47 / 67 / 2 | 969 / 301 / 19 / 0 / 19 |
| 42 | 212.0 | 8.2 / 11.2 / 0.3 / 0.5 / 0.5 / 0.6 | 1136 / 53 / 65 / 0 | 912 / 305 / 17 / 2 / 18 |
| 43 | 221.3 | 7.8 / 10.9 / 0.3 / 0.5 / 0.5 / 0.6 | 1007 / 136 / 55 / 0 | 791 / 285 / 17 / 18 / 87 |
| 44 | 217.9 | 8.1 / 10.8 / 0.3 / 0.5 / 0.6 / 0.6 | 886 / 54 / 35 / 0 | 676 / 242 / 27 / 0 / 30 |
| 45 | 213.3 | 8.0 / 10.9 / 0.3 / 0.5 / 0.6 / 0.6 | 1033 / 105 / 42 / 0 | 822 / 245 / 89 / 0 / 24 |
| 46 | 212.7 | 7.8 / 10.6 / 0.3 / 0.5 / 0.6 / 0.6 | 1220 / 152 / 48 / 0 | 1015 / 251 / 31 / 53 / 70 |
| 47 | 215.7 | 7.4 / 10.1 / 0.3 / 0.5 / 0.6 / 0.6 | 1206 / 36 / 48 / 0 | 995 / 250 / 31 / 7 / 7 |
| 48 | 221.5 | 7.1 / 10.0 / 0.3 / 0.5 / 0.6 / 0.6 | 1109 / 61 / 42 / 0 | 932 / 229 / 34 / 17 / 0 |
| 49 | 214.8 | 7.3 / 10.1 / 0.3 / 0.5 / 0.6 / 0.6 | 1072 / 108 / 36 / 0 | 923 / 239 / 34 / 20 / 0 |

Blocks and TCP per slot, `L-pq-b16-2k4-rtt6-ps100-cf2-s1` (block first-seen from publish p95, against the current
build's `L-pq-b16-2k4-ps100-cf2-s1`; ssthresh p50 after a restart after idle, u = never reduced; first timeouts per
1,000 data packets; TCP figures cover slots 2–48)

| slot | block p95 from publish, rtt6 / current build (s) | ssthresh p50 after restarts, 1G→1G / 1G→home / home→1G / home→home | first timeouts per 1,000 data packets, 1G→1G / 1G→home / home→1G / home→home |
|---|---|---|---|
| 2 | 0.83 / 0.35 | u / u / u / u | 0.09 / 2.90 / 0.86 / 7.67 |
| 3 | 0.87 / 0.33 | 386 / 191 / u / u | 0.09 / 3.33 / 1.05 / 9.26 |
| 4 | 0.78 / 0.30 | 182 / 75 / u / u | 0.11 / 3.91 / 1.16 / 11.07 |
| 5 | 0.58 / 0.28 | 151 / 53 / 168 / u | 0.10 / 4.25 / 1.31 / 12.04 |
| 6 | 0.59 / 0.24 | 135 / 43 / 128 / 58 | 0.11 / 4.68 / 1.43 / 13.40 |
| 7 | 0.77 / 0.34 | 123 / 37 / 100 / 28 | 0.10 / 4.77 / 1.50 / 14.51 |
| 8 | 0.62 / 0.29 | 116 / 34 / 80 / 22 | 0.11 / 4.92 / 1.60 / 13.93 |
| 9 | 0.57 / 0.27 | 112 / 32 / 72 / 21 | 0.11 / 5.04 / 1.64 / 14.87 |
| 10 | 0.48 / 0.28 | 105 / 30 / 61 / 18 | 0.12 / 5.38 / 1.78 / 15.23 |
| 11 | 0.63 / 0.33 | 105 / 28 / 60 / 16 | 0.11 / 5.18 / 1.66 / 15.65 |
| 12 | 0.84 / 0.41 | 102 / 28 / 52 / 16 | 0.12 / 5.44 / 1.87 / 15.50 |
| 13 | 0.55 / 0.29 | 101 / 28 / 51 / 16 | 0.12 / 5.61 / 1.91 / 15.92 |
| 14 | 0.60 / 0.33 | 100 / 27 / 49 / 15 | 0.12 / 5.69 / 1.96 / 16.87 |
| 15 | 0.67 / 0.39 | 96 / 27 / 45 / 15 | 0.13 / 5.88 / 2.12 / 16.24 |
| 16 | 0.54 / 0.23 | 99 / 27 / 48 / 15 | 0.11 / 5.62 / 1.90 / 17.60 |
| 17 | 0.62 / 0.42 | 96 / 25 / 42 / 15 | 0.13 / 5.96 / 2.28 / 17.22 |
| 18 | 0.57 / 0.32 | 91 / 25 / 42 / 15 | 0.12 / 5.85 / 2.16 / 16.97 |
| 19 | 0.56 / 0.29 | 96 / 25 / 40 / 15 | 0.13 / 6.08 / 2.35 / 17.32 |
| 20 | 0.74 / 0.35 | 96 / 25 / 42 / 15 | 0.12 / 5.59 / 2.08 / 17.47 |
| 21 | 0.90 / 0.44 | 95 / 25 / 39 / 15 | 0.14 / 6.21 / 2.49 / 18.82 |
| 22 | 0.46 / 0.32 | 94 / 24 / 37 / 15 | 0.14 / 6.38 / 2.53 / 18.37 |
| 23 | 0.56 / 0.36 | 94 / 24 / 37 / 14 | 0.13 / 6.35 / 2.52 / 18.10 |
| 24 | 0.62 / 0.28 | 94 / 24 / 37 / 14 | 0.14 / 6.28 / 2.47 / 18.58 |
| 25 | 0.86 / 0.40 | 94 / 24 / 36 / 14 | 0.15 / 6.65 / 2.72 / 19.46 |
| 26 | 0.53 / 0.34 | 93 / 24 / 36 / 14 | 0.13 / 6.34 / 2.53 / 18.81 |
| 27 | 0.62 / 0.35 | 91 / 24 / 35 / 14 | 0.14 / 6.61 / 2.72 / 19.49 |
| 28 | 0.60 / 0.36 | 84 / 23 / 34 / 13 | 0.14 / 6.51 / 2.67 / 17.99 |
| 29 | 0.82 / 0.48 | 91 / 23 / 35 / 13 | 0.14 / 6.30 / 2.51 / 18.56 |
| 30 | 0.66 / 0.30 | 90 / 22 / 33 / 13 | 0.14 / 6.82 / 2.75 / 19.94 |
| 31 | 0.70 / 0.34 | 89 / 22 / 33 / 13 | 0.14 / 6.79 / 2.67 / 19.94 |
| 32 | 0.70 / 0.37 | 89 / 22 / 32 / 13 | 0.15 / 6.99 / 2.86 / 19.69 |
| 33 | 0.49 / 0.27 | 89 / 22 / 33 / 13 | 0.13 / 6.67 / 2.73 / 18.37 |
| 34 | 0.72 / 0.57 | 91 / 22 / 33 / 13 | 0.12 / 6.58 / 2.53 / 19.04 |
| 35 | 0.48 / 0.32 | 90 / 22 / 31 / 13 | 0.14 / 7.28 / 3.03 / 20.02 |
| 36 | 0.61 / 0.37 | 88 / 22 / 31 / 13 | 0.15 / 7.38 / 3.05 / 20.23 |
| 37 | 0.61 / 0.33 | 89 / 22 / 31 / 13 | 0.14 / 7.36 / 3.08 / 20.10 |
| 38 | 0.65 / 0.38 | 90 / 22 / 31 / 13 | 0.14 / 7.17 / 2.99 / 19.55 |
| 39 | 0.68 / 0.67 | 90 / 22 / 31 / 13 | 0.13 / 6.61 / 2.67 / 19.35 |
| 40 | 0.61 / 0.38 | 87 / 21 / 30 / 12 | 0.15 / 7.38 / 3.12 / 19.60 |
| 41 | 0.58 / 0.40 | 87 / 21 / 30 / 13 | 0.14 / 7.44 / 3.18 / 20.06 |
| 42 | 0.51 / 0.29 | 87 / 21 / 30 / 12 | 0.15 / 7.60 / 3.27 / 20.65 |
| 43 | 0.60 / 0.33 | 86 / 21 / 29 / 12 | 0.14 / 7.24 / 3.16 / 19.78 |
| 44 | 0.51 / 0.29 | 85 / 21 / 29 / 12 | 0.14 / 7.26 / 3.20 / 20.12 |
| 45 | 0.56 / 0.28 | 85 / 21 / 28 / 12 | 0.15 / 7.41 / 3.28 / 20.56 |
| 46 | 0.56 / 0.37 | 85 / 21 / 28 / 12 | 0.15 / 7.52 / 3.35 / 21.03 |
| 47 | 0.77 / 0.43 | 85 / 21 / 28 / 12 | 0.15 / 7.54 / 3.38 / 21.66 |
| 48 | 0.58 / 0.34 | 85 / 21 / 28 / 12 | 0.15 / 7.38 / 3.32 / 19.75 |
| 49 | 0.80 / 0.36 | – | – |

### 1,024 hosts × 50 slots, 2.4 kB, 16 signatures per message, rtt6, seed 2: `L-pq-b16-2k4-rtt6-ps100-cf2-s2` (cf2, long horizon)

Seed 2 of the bundled 50-slot run on rtt6: `L-pq-b16-2k4-rtt6-ps100-cf2-s1`'s flags (×1.0, `--msg-bytes 2458 --batch
16`) with `--seed 2`, which gives another generated network and publish schedule, and P3 rate 43.99 from its own
50-slot mean. TCP logging. About 361 1 Gbit hosts are online per slot, so one host is 0.28 % of the class and the
rule allows 3 incomplete ones per slot.

- **Strict rule: PASS, with no host to spare in its worst slot.** 50/15 and 50/25 100 % in every slot. 1 Gbit hosts
  are complete in 43 of the 48 slots from slot 2; slots 27, 28, 42 and 44 miss one host each (99.72 %), and slot 40
  misses three (99.17 %, 3 of ~361; the rule allows 3). Per 10-slot block 100 / 100 / 99.94 / 100 / 99.86 % (seed 1
  99.81–99.86 %, current build 99.92–100 %). 7 node·slots are incomplete in slots 2–49, all on 1 Gbit hosts (near
  miss 4, late 2, never received 1), against 30 on seed 1 and 5 on the current build. Four hosts hold them, none in
  more than 2 slots: 770 (Lighthouse, Sydney), 33 (Lighthouse, São Paulo) and 577 (Prysm, São Paulo, 70 peers) 2
  each, 758 (Lighthouse, São Paulo) 1. All 7 fall after slot 26 (2 in slots 27–28, 5 in slots 40–44), too few to
  show a trend; the backlog test below finds no build-up.
- **It levels off.** Means per 10-slot block from slot 2, and the slope over slots 30–49:
  - **Backlog test.** Messages first delivered after the deadline: 0 in 44 of the 48 slots and 0.01–0.04 per 1 Gbit
    node in slots 27, 28, 40 and 44 (seed 1 at most 0.16, current build at most 0.08); none on home hosts. Over
    slots 2–49 they sum to 0.10 per 1 Gbit node, against about 0.13 PQ messages missing at 8 s. PQ copies older than
    60 s: 36 in all (seed 1: 0). So no backlog builds up.
  - **After-deadline copies** per node (table below): on 1 Gbit hosts 527 → 1,192 kB per slot over the five blocks,
    adding 108, 167 and 49 kB per block after slot 20, +5.2 % per 10 slots over slots 30–49 (seed 1 +6.3 %, current
    build +8 %). Home hosts level off after slot 20: −6.3 % (50/15) and −4.3 % (50/25) per 10 slots over slots 30–49
    (seed 1 +2.3 and +4.5 %). Background bgexcess stays ≤ 1.016, so nothing re-floods.
  - **Scoring.** The PQ P3 deficit peaks in slots 16–29 (1,775 per slot over 1,024 hosts) and then falls to 954 and
    1,077 (seed 1 2,516, 1,345 and 1,095). Negative-score peers per observer decline over the run in Lighthouse
    views (12.5 → 8.8 from the first to the last block) and other views (18.6 → 11.8); in Teku, Lodestar and Nimbus
    views they reach 0.44–0.69 in slots 40–49 (seed 1 0.50–0.59, current build 0.72–1.05).

After-deadline PQ kB per node per slot (8–16 s) and late first deliveries per 1 Gbit node, means per 10-slot block
from slot 2: seed 2 / seed 1 on rtt6 / seed 1 on the current build (`L-pq-b16-2k4-ps100-cf2-s1`):

| slots | 50/15 | 50/25 | 1 Gbit | late first, 1 Gbit |
|---|---|---|---|---|
| 2–9 | 28.6 / 23.7 / 23.3 | 18.8 / 20.4 / 18.8 | 527 / 483 / 709 | 0.00 / 0.01 / 0.00 |
| 10–19 | 39.2 / 31.8 / 32.1 | 27.0 / 27.8 / 29.5 | 868 / 817 / 1,133 | 0.00 / 0.01 / 0.01 |
| 20–29 | 45.2 / 39.7 / 38.0 | 26.6 / 27.7 / 37.0 | 976 / 921 / 1,237 | 0.005 / 0.01 / 0.00 |
| 30–39 | 38.0 / 44.2 / 34.5 | 30.5 / 30.1 / 43.4 | 1,143 / 1,011 / 1,377 | 0.00 / 0.04 / 0.00 |
| 40–49 | 38.1 / 45.9 / 43.8 | 29.8 / 32.2 / 43.5 | 1,192 / 1,110 / 1,488 | 0.005 / 0.01 / 0.01 |

- **Against seed 1 and the current build:** PQ latency p99 from publish 0.66 / 0.58 / 0.72 s for 50/15 / 50/25 / 1
  Gbit (seed 1 0.65 / 0.58 / 0.69 s, current build 0.49 / 0.43 / 0.56 s); blocks from publish p50 / p95 / p99 0.30 /
  0.68 / 0.90 s (0.33 / 0.67 / 0.88 s; 0.17 / 0.36 / 0.53 s). Block p95 per 10-slot block is 0.69, 0.67, 0.65, 0.60
  and 0.61 s (seed 1 0.70, 0.61, 0.67, 0.63 and 0.61 s), so the slowdown does not grow over 50 slots.
- **PQ vs BLS**, slots 2–15 and 16–49: PQ missing on 1 Gbit hosts 0 and 0.0006 % (home 0); attestations 0.012 /
  0.026 / 1.65 % and 0.025 / 0.024 / 1.72 % (all-64-subnet hosts 1.85 / 1.93 %, 2-subnet 1 Gbit hosts 0.031 / 0.016
  %). Home BLS deliveries that never arrive (the watch item): 0 in every 10-slot block on both home classes, as on
  seed 1; missing at 8 s per block 0.017 / 0.006 / 0.017 / 0.047 / 0.017 % (50/15) and 0.020 / 0.023 / 0.016 / 0.034
  / 0.029 % (50/25), against 0.036–0.047 and 0.011–0.056 % on seed 1. No matched no-PQ run exists on rtt6 at 1,024
  hosts.
- **TCP** per 10-slot block (slots 2–9, 10–19, 20–29, 30–39, 40–48; path types by sender → receiver):

| path | first timeouts per 1,000 data packets | resends per 1,000 | block-end cwnd p50 / p90 |
|---|---|---|---|
| 1G→1G | 0.10, 0.12, 0.14, 0.14, 0.15 | 0.29–0.31 | 10 / 23, 26, 27, 26, 29 |
| 1G→home | 4.39, 5.79, 6.50, 6.89, 7.29 | 3.48–3.57 | 10 / 18, 18, 18, 18, 19 |
| home→1G | 1.28, 2.02, 2.49, 2.82, 3.11 | 1.82–2.18 | 10 / 19, 20, 18, 18, 18 |
| home→home | 13.5, 18.6, 20.4, 21.4, 22.4 | 9.48–9.81 | 10 / 18, 16, 15, 14, 15 |

  - The first-timeout climb slows (home→home +5.1, +1.8, +1.0 and +1.0 per block; 1G→home +1.4, +0.7, +0.4 and +0.4)
    but has not stopped by slot 48, as on seed 1 (+4.3, +2.1, +1.1, +0.7 and +1.5, +0.7, +0.7, +0.5). Resends stay
    flat, and windows do not grow: cwnd p50 is 10 segments at every block end.
  - 35.9M restarts after idle (seed 1 36.4M); 89 % leave cwnd below ssthresh, and all of those continue in slow
    start. ssthresh p50 after a restart falls fast and levels off: 1G→1G 319 at slot 3 → 96 at slot 19 → 81 at slot
    48, 1G→home 128 → 25 → 21, home→1G 128 at slot 5 → 39 → 28, home→home 100 at slot 5 → 14 → 12 (seed 1 1G→1G 386
    → 96 → 85, home→home 58 at slot 6 → 15 → 12).
  - rtt6 counters: data packets sent with cwnd ≥ ssthresh 70.8 % (1G→1G), 74.1 % (1G→home), 72.6 % (home→1G) and
    73.5 % (home→home), 72.1 % in all (seed 1 69.7, 73.7, 72.3 and 73.6 %). HyStart exits, train / delay: 7,716 / 2,
    948 / 2,300, 1,618 / 5,600 and 2 / 2,990, with cwnd at exit p50 28, 109, 78 and 111 segments (seed 1 8,709 / 2,
    925 / 2,322, 1,488 / 5,477 and 3 / 2,716). CUBIC targets equal Linux's integer formula in all 440,217 traced
    recomputations, all 342,626 traced epoch shifts equal min(epoch + idle, now), and no congestion-avoidance round
    grows by more than half the ACKed packets + 1.
  - Fast-recovery entries per 1,000 data packets 0.26, 1.51, 1.46 and 2.35, all after consecutive duplicate ACKs.
    12.25M RTOs (seed 1 11.42M); 97.4 % of 6.84M Eifel checks found the timeout spurious and undid it. SRTT −
    configured RTT p50 / p99 2 / 6, 8 / 117, 5 / 13 and 11 / 131 ms. No stalls (7.82M snapshots); the RTO formula
    holds in all 7,173,803 snapshots without backoff.
- **Other.** PQ latency p50 / p99 from publish 0.10 / 0.66 s (50/15), 0.09 / 0.58 s (50/25), 0.09 / 0.72 s (1 Gbit);
  κ 8.9–10.2 per slot from slot 2 (seed 1 9.2–10.0); PQ copies per message 4.4–5.0 (4.3–4.8); IDONTWANT 8.0–9.9k ids
  per node per slot (7.8–9.2k). Upload in the 4 s window, mean / max node, % of cap: 40 / 59 (50/15), 25 / 38
  (50/25), 5 / 11 (1 Gbit); download ≤ 13 / 22. Failed sends that cost score: 95.8M over 50 slots (forward timeout
  54.9 %, forward queue full 41.5 %, control queue full 3.6 %; seed 1 85.8M). Stale background copies 8,872 (seed 1
  2,125). Attestations after 4 s p50 / p95 / p99 1.05 / 2.09 / 3.66 s; 0.55 % never arrive. Churn removes 82 of
  100,000 signatures (in 77 messages); no refused publish. Peak 116.6 GiB PSS; wall 13,786 s.
- **Reading.** Seed 2 confirms seed 1 on rtt6: the bundled cell holds over 50 slots, with one slot at the rule's
  limit (slot 40) and fewer misses overall (7 node·slots against 30), and nothing builds up: late first deliveries
  stay within the misses at 8 s, home late copies level off, and blocks hold at 0.60–0.69 s p95 per block. As on
  seed 1, late copies on 1 Gbit hosts and first timeouts still rise slowly at slot 49.

Delivery per slot, `L-pq-b16-2k4-rtt6-ps100-cf2-s2` (1 Gbit = cloud class; PQ and BLS misses at 8 s; after-deadline PQ kB per node, 8-16 s)

| slot | complete 50/15 / 50/25 / 1 Gbit (%) | PQ missing, 1 Gbit (%) | BLS attestations missing, 50/15 / 50/25 / 1 Gbit (%) | after-deadline PQ kB, 50/15 / 50/25 / 1 Gbit | late first PQ deliveries (8-16 s), 1 Gbit host mean |
|---|---|---|---|---|---|
| 0 | 100.00 / 100.00 / 100.00 | – | – / – / – | 10 / 12 / 83 | 0.00 |
| 1 | 100.00 / 100.00 / 100.00 | – | – / – / – | 20 / 10 / 161 | 0.00 |
| 2 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.015 / 0.030 / 1.481 | 19 / 10 / 201 | 0.00 |
| 3 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.005 / 1.517 | 25 / 16 / 296 | 0.00 |
| 4 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.016 / 0.026 / 1.497 | 34 / 15 / 424 | 0.00 |
| 5 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.046 / 1.875 | 20 / 14 / 559 | 0.00 |
| 6 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.089 / 0.000 / 1.609 | 26 / 20 / 577 | 0.00 |
| 7 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.000 / 1.761 | 28 / 24 / 646 | 0.00 |
| 8 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.058 / 1.725 | 43 / 26 / 758 | 0.00 |
| 9 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.015 / 0.000 / 1.613 | 34 / 24 / 755 | 0.00 |
| 10 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.057 / 1.746 | 37 / 27 / 745 | 0.00 |
| 11 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.000 / 1.591 | 34 / 30 / 853 | 0.00 |
| 12 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.015 / 0.034 / 1.569 | 45 / 24 / 833 | 0.00 |
| 13 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.016 / 0.077 / 1.729 | 35 / 31 / 814 | 0.00 |
| 14 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.031 / 1.490 | 41 / 31 / 850 | 0.00 |
| 15 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.000 / 1.861 | 32 / 26 / 898 | 0.00 |
| 16 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.016 / 0.005 / 1.965 | 44 / 27 / 942 | 0.00 |
| 17 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.015 / 0.014 / 2.171 | 46 / 25 / 941 | 0.00 |
| 18 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.000 / 1.613 | 35 / 26 / 924 | 0.00 |
| 19 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.015 / 1.642 | 43 / 24 / 878 | 0.00 |
| 20 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.010 / 1.980 | 43 / 25 / 875 | 0.00 |
| 21 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.031 / 0.020 / 1.794 | 42 / 25 / 915 | 0.00 |
| 22 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.026 / 1.867 | 44 / 27 / 878 | 0.00 |
| 23 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.000 / 1.972 | 50 / 28 / 996 | 0.00 |
| 24 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.048 / 0.010 / 1.652 | 43 / 30 / 942 | 0.00 |
| 25 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.005 / 1.521 | 40 / 25 / 1043 | 0.00 |
| 26 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.030 / 0.035 / 1.691 | 46 / 25 / 994 | 0.00 |
| 27 | 100.00 / 100.00 / 99.72 | 0.0008 | 0.000 / 0.049 / 1.894 | 42 / 22 / 987 | 0.01 |
| 28 | 100.00 / 100.00 / 99.72 | 0.0079 | 0.062 / 0.000 / 2.062 | 56 / 34 / 1066 | 0.04 |
| 29 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.005 / 1.912 | 47 / 24 / 1064 | 0.00 |
| 30 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.092 / 0.005 / 1.872 | 45 / 33 / 1105 | 0.00 |
| 31 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.068 / 1.812 | 40 / 30 / 1057 | 0.00 |
| 32 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.064 / 1.839 | 48 / 30 / 1140 | 0.00 |
| 33 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.093 / 0.010 / 1.821 | 39 / 40 / 1212 | 0.00 |
| 34 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.142 / 0.000 / 1.700 | 40 / 29 / 1194 | 0.00 |
| 35 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.036 / 1.720 | 27 / 31 / 1076 | 0.00 |
| 36 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.060 / 0.030 / 1.402 | 32 / 29 / 1228 | 0.00 |
| 37 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.005 / 1.592 | 35 / 31 / 1114 | 0.00 |
| 38 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.041 / 1.556 | 38 / 28 / 1146 | 0.00 |
| 39 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.088 / 0.075 / 1.820 | 34 / 25 / 1154 | 0.00 |
| 40 | 100.00 / 100.00 / 99.17 | 0.0064 | 0.062 / 0.089 / 1.573 | 43 / 28 / 1206 | 0.04 |
| 41 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.010 / 1.800 | 44 / 28 / 1140 | 0.00 |
| 42 | 100.00 / 100.00 / 99.72 | 0.0050 | 0.000 / 0.021 / 1.838 | 41 / 32 / 1106 | 0.00 |
| 43 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.030 / 0.050 / 1.414 | 36 / 31 / 1198 | 0.00 |
| 44 | 100.00 / 100.00 / 99.72 | 0.0008 | 0.000 / 0.020 / 1.597 | 44 / 29 / 1157 | 0.01 |
| 45 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.052 / 1.172 | 28 / 28 / 1127 | 0.00 |
| 46 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.035 / 1.351 | 31 / 32 / 1191 | 0.00 |
| 47 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.005 / 1.623 | 38 / 30 / 1257 | 0.00 |
| 48 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.072 / 0.010 / 1.637 | 38 / 28 / 1244 | 0.00 |
| 49 | 100.00 / 100.00 / 100.00 | 0.0000 | 0.000 / 0.000 / 1.493 | 38 / 31 / 1291 | 0.00 |

Scoring per slot, `L-pq-b16-2k4-rtt6-ps100-cf2-s2` (mesh snapshot at 3.95 s; negative-score peers per observer; P3 = MessageDeficit penalties summed over hosts in the slot; Prysm applies no P3)

| slot | links/node | negative peers per observer: Lighthouse / other / Prysm / Teku / Lodestar / Nimbus | P3 by topic: PQ / attestation / block / aggregate | P3 in the views of Lighthouse / other / Teku / Lodestar / Nimbus |
|---|---|---|---|---|
| 0 | 211.3 | 0.1 / 0.1 / 0.0 / 0.0 / 0.0 / 0.0 | – / – / – / – | – / – / – / – / – |
| 1 | 197.7 | 4.7 / 6.8 / 0.0 / 0.0 / 0.0 / 0.0 | – / – / – / – | – / – / – / – / – |
| 2 | 201.6 | 9.1 / 13.5 / 0.0 / 0.0 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 3 | 211.6 | 11.9 / 17.9 / 0.0 / 0.0 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 4 | 201.1 | 14.8 / 21.5 / 0.0 / 0.0 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 5 | 203.8 | 15.0 / 21.6 / 0.0 / 0.0 / 0.0 / 0.0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 6 | 211.5 | 13.5 / 20.3 / 0.0 / 0.0 / 0.1 / 0.1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 7 | 208.1 | 12.5 / 18.8 / 0.1 / 0.1 / 0.1 / 0.1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 8 | 214.9 | 11.6 / 17.4 / 0.1 / 0.1 / 0.1 / 0.1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 9 | 212.6 | 12.0 / 17.4 / 0.1 / 0.1 / 0.1 / 0.1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 10 | 207.5 | 12.2 / 17.2 / 0.1 / 0.1 / 0.1 / 0.1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 11 | 206.4 | 11.9 / 17.0 / 0.1 / 0.1 / 0.1 / 0.1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 12 | 214.4 | 11.4 / 17.0 / 0.1 / 0.1 / 0.1 / 0.1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 13 | 219.6 | 11.5 / 17.1 / 0.1 / 0.1 / 0.1 / 0.1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 14 | 213.0 | 12.0 / 17.3 / 0.1 / 0.1 / 0.2 / 0.1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| 15 | 208.0 | 11.6 / 16.6 / 0.1 / 0.1 / 0.2 / 0.1 | 833 / 549 / 0 / 0 | 406 / 312 / 390 / 182 / 92 |
| 16 | 211.5 | 11.5 / 16.9 / 0.2 / 0.3 / 0.4 / 0.3 | 1932 / 212 / 0 / 0 | 888 / 839 / 153 / 203 / 61 |
| 17 | 206.0 | 11.2 / 16.6 / 0.2 / 0.3 / 0.4 / 0.3 | 1850 / 208 / 0 / 0 | 928 / 823 / 78 / 153 / 76 |
| 18 | 216.9 | 10.5 / 15.8 / 0.2 / 0.3 / 0.4 / 0.3 | 2136 / 195 / 0 / 0 | 1062 / 1046 / 61 / 121 / 41 |
| 19 | 216.2 | 10.8 / 15.3 / 0.2 / 0.3 / 0.5 / 0.4 | 2427 / 183 / 0 / 0 | 1097 / 1304 / 75 / 86 / 48 |
| 20 | 210.0 | 10.8 / 15.4 / 0.2 / 0.3 / 0.5 / 0.4 | 2497 / 195 / 0 / 0 | 1152 / 1382 / 56 / 76 / 26 |
| 21 | 208.4 | 10.2 / 14.7 / 0.2 / 0.3 / 0.5 / 0.4 | 2502 / 169 / 0 / 0 | 1131 / 1438 / 47 / 37 / 18 |
| 22 | 205.7 | 9.7 / 14.1 / 0.2 / 0.3 / 0.4 / 0.4 | 2133 / 194 / 0 / 0 | 877 / 1305 / 98 / 30 / 17 |
| 23 | 217.5 | 9.1 / 14.0 / 0.2 / 0.3 / 0.4 / 0.4 | 1913 / 204 / 0 / 0 | 759 / 1199 / 53 / 82 / 24 |
| 24 | 211.2 | 9.7 / 14.4 / 0.2 / 0.3 / 0.5 / 0.5 | 1637 / 124 / 0 / 0 | 625 / 1075 / 34 / 17 / 10 |
| 25 | 210.5 | 9.5 / 13.9 / 0.2 / 0.3 / 0.5 / 0.5 | 1512 / 170 / 0 / 0 | 544 / 1005 / 104 / 21 / 8 |
| 26 | 214.5 | 9.4 / 13.9 / 0.2 / 0.3 / 0.5 / 0.6 | 1461 / 89 / 0 / 0 | 541 / 927 / 43 / 20 / 19 |
| 27 | 209.5 | 9.4 / 14.2 / 0.2 / 0.3 / 0.5 / 0.6 | 1208 / 79 / 0 / 0 | 469 / 752 / 40 / 12 / 14 |
| 28 | 218.1 | 9.4 / 13.7 / 0.2 / 0.3 / 0.5 / 0.6 | 921 / 83 / 0 / 0 | 352 / 591 / 38 / 0 / 23 |
| 29 | 210.6 | 9.9 / 13.8 / 0.2 / 0.3 / 0.5 / 0.6 | 725 / 63 / 0 / 0 | 256 / 465 / 40 / 14 / 13 |
| 30 | 214.8 | 9.8 / 14.2 / 0.2 / 0.3 / 0.5 / 0.6 | 792 / 78 / 22 / 1 | 371 / 398 / 51 / 35 / 38 |
| 31 | 210.7 | 10.2 / 14.2 / 0.2 / 0.4 / 0.5 / 0.6 | 967 / 147 / 54 / 1 | 546 / 434 / 51 / 25 / 113 |
| 32 | 208.1 | 9.9 / 13.6 / 0.2 / 0.4 / 0.6 / 0.6 | 880 / 142 / 60 / 0 | 598 / 383 / 58 / 13 / 30 |
| 33 | 219.7 | 9.6 / 12.9 / 0.2 / 0.4 / 0.6 / 0.7 | 845 / 162 / 77 / 1 | 631 / 330 / 63 / 38 / 23 |
| 34 | 213.0 | 10.0 / 12.9 / 0.2 / 0.3 / 0.6 / 0.7 | 778 / 73 / 87 / 0 | 537 / 278 / 60 / 39 / 24 |
| 35 | 210.0 | 9.9 / 12.6 / 0.2 / 0.3 / 0.6 / 0.7 | 935 / 79 / 72 / 2 | 735 / 265 / 41 / 23 / 24 |
| 36 | 209.7 | 9.7 / 12.1 / 0.2 / 0.4 / 0.6 / 0.7 | 1241 / 40 / 53 / 2 | 912 / 330 / 29 / 19 / 46 |
| 37 | 214.0 | 9.5 / 12.3 / 0.2 / 0.4 / 0.7 / 0.7 | 1201 / 52 / 36 / 0 | 803 / 355 / 30 / 34 / 67 |
| 38 | 218.8 | 9.1 / 12.5 / 0.2 / 0.4 / 0.7 / 0.7 | 1022 / 71 / 36 / 7 | 723 / 305 / 18 / 24 / 66 |
| 39 | 212.8 | 9.4 / 12.5 / 0.2 / 0.5 / 0.7 / 0.7 | 883 / 56 / 26 / 12 | 648 / 263 / 17 / 7 / 42 |
| 40 | 215.8 | 9.1 / 12.1 / 0.2 / 0.4 / 0.6 / 0.7 | 1172 / 89 / 17 / 1 | 792 / 414 / 48 / 7 / 18 |
| 41 | 211.8 | 9.1 / 12.2 / 0.2 / 0.5 / 0.6 / 0.6 | 1478 / 86 / 35 / 0 | 1005 / 528 / 33 / 13 / 20 |
| 42 | 209.5 | 8.8 / 11.9 / 0.2 / 0.5 / 0.6 / 0.6 | 1390 / 139 / 62 / 0 | 973 / 476 / 24 / 61 / 57 |
| 43 | 215.7 | 8.6 / 11.7 / 0.2 / 0.5 / 0.7 / 0.7 | 1319 / 90 / 72 / 0 | 932 / 459 / 17 / 0 / 73 |
| 44 | 216.1 | 8.8 / 11.9 / 0.2 / 0.4 / 0.7 / 0.7 | 1235 / 115 / 55 / 6 | 863 / 483 / 18 / 0 / 47 |
| 45 | 211.2 | 8.7 / 12.2 / 0.2 / 0.4 / 0.7 / 0.7 | 1068 / 97 / 66 / 24 | 810 / 354 / 24 / 9 / 58 |
| 46 | 207.4 | 8.8 / 11.9 / 0.2 / 0.4 / 0.7 / 0.7 | 980 / 57 / 62 / 29 | 755 / 256 / 31 / 17 / 69 |
| 47 | 211.8 | 8.6 / 11.2 / 0.2 / 0.4 / 0.7 / 0.6 | 859 / 46 / 53 / 18 | 660 / 197 / 40 / 18 / 61 |
| 48 | 216.4 | 8.5 / 11.3 / 0.2 / 0.4 / 0.8 / 0.7 | 699 / 38 / 43 / 17 | 559 / 139 / 42 / 6 / 51 |
| 49 | 210.7 | 9.0 / 11.2 / 0.2 / 0.5 / 0.8 / 0.7 | 567 / 44 / 57 / 17 | 503 / 106 / 18 / 0 / 58 |

### Churn and refused publishes, all PQ runs

Coordinator's rule (Nov 9): a PQ message is lost to churn if its publisher was offline at publish time or had no
connections at all. Signatures of offline publishers never exist (perturb.py drops them from the schedule). A publish
that gossipsub refuses while the publisher has connections is a peer-management failure and counts against the network.
wbsim logs each refused PQ publish, and pqdiag counts messages that reached nobody; both find only the v400 case.

| runs | signatures lost to churn (publisher offline) | refused publishes without connections (churn) | refused publishes with connections (network) |
|---|---|---|---|
| 2,048 × 20, 800k, seed 1: `R20-pq-2k4-ps100-cf2-s1`, `R20-pq-2k4-rtt4-ps100-cf2-s1`, `R20-pq-2k4-rtt5-ps100-cf2-s1`, `R20-pq-b16-2k4-rtt5-ps100-cf2-s1`, `R20-pq-b16-2k4-rtt5b-ps100-cf2-s1`, `R20-pq-b16-2k4-rtt6-ps100-cf2-s1`, `R20-pq-b16-2k4-2sub-rtt6-ps100-cf2-s1`, `R20-pq-b16-2k4-bb2-rtt6-ps100-cf2-s1`, `R20-pq-2k4-cwv-ps100-cf2-s1`, `R20-pq-2k4-rtt6-ps100-cf2-s1`, `R20-pq-ps100-cf2-s1`, `-cf-s1`, `-age60-s1`, both b16 | 34 of 40,000 | 0 | 0 |
| 2,048 × 20, 800k, seed 2: `R20-pq-2k4-ps100-cf2-s2` | 25 of 40,000 | 0 | 0 |
| 2,048 × 20, 800k, seed 2, b16: `R20-pq-b16-2k4-ps100-cf2-s2` | 25 of 40,000 (in 22 messages) | 0 | 0 |
| 2,048 × 20, 600k: `R20-pq-v600-2k4-ps100-cf2-s1` | 7 of 30,000 | 0 | 0 |
| 2,048 × 20, 400k: `R20-pq-v400-2k4-ps100-cf2-s1` | 540 of 20,000 | 0 | 1 (slot 19) |
| 2,048 × 20, fs0: `R20-pq-fs0-2k4-ps100-cf2-s1`, `R20-pq-fs0-2k4-rtt4-ps100-cf2-s1`, `R20-pq-fs0-b16-2k4-rtt6-ps100-cf2-s1` | 388 of 40,000 (fs0-b16: in 160 messages) | 0 | 0 |
| 1,024 × 50: `L-pq-2k4-ps100-cf2-s1`, `L-pq-b16-2k4-ps100-cf2-s1`, `L-pq-b16-2k4-rtt6-ps100-cf2-s1`, `L-pq-ps100-fx-s1` | 9 of 100,000 | 0 | 0 |
| 1,024 × 50, seed 2, b16: `L-pq-b16-2k4-rtt6-ps100-cf2-s2` | 82 of 100,000 (in 77 messages) | 0 | 0 |
| 2,048 × 6, 800k: key cell (both seeds), s1k, b16 (fx, cf), noloss, ×0.25 | 11 of 12,000 | 0 | 0 |
| 2,048 × 6, fs0 (fx, cf) | 100 of 12,000 | 0 | 0 |
| 2,048 × 6, 600k / 400k | 2 of 9,000 / 138 of 6,000 | 0 | 0 |

The rule excludes no message beyond the existing churn count in any run. Which hosts carry validators, and so how
many signatures churn removes, depends on the cell (fs0 and v400 lose more). In bundled runs, run.json's
`pq_lost_to_churn` counts messages, not signatures; the signature counts here come from the schedules.

### 2,048 hosts × 20 slots, 2.4 kB, 16 signatures per message: `R20-pq-b16-2k4-ps100-cf2-s1` (cf2)

×1.0, `--batch 16`, `--msg-bytes 2458`, seed 1. Messages carry 1–16 signatures (66.93 per subnet per slot on
average, the P3 expected rate: PQ threshold 36.54, full-deficit cost −5.2 per topic in Lighthouse and other views,
−157.5 in Teku, Lodestar and Nimbus views, 0 in Prysm views). Completion per slot (%, slots 0–19):

| class | per slot |
|---|---|
| 50/15 | 100 in every slot |
| 50/25 | 100 in every slot |
| 1 Gbit | 99.73 100 100 100 100 99.86 100 99.86 100 99.73 99.86 100 99.73 99.86 99.73 99.59 99.86 99.73 99.59 99.73 |

- **Strict rule: PASS with margin.** The worst slots are 15 and 18 (99.59 %, 3 of ~740 1 Gbit hosts incomplete; the
  rule allows 7). Slots 2–15 average 100 / 100 / 99.87 %, slots 16–19 100 / 100 / 99.73 %.
- **Incomplete node·slots**, 1 Gbit only: 13 in slots 2–15 (near miss 9, late 3, never 1) and 8 in slots 16–19 (near
  miss 5, late 3). No host is chronic. All 9 hosts incomplete at least once are Prysm hosts with 70 peers, most often
  1873 (São Paulo, 7 of 18 slots) and 344 (Singapore, 4).
- **P3.** The PQ deficit penalties do not decay after slot 15 as they do unbundled (1,302 → 2,527 per slot against
  729 → 564), but they sit in Lighthouse and other views, where a full deficit costs only −5.2 per topic (from slot 15
  per host: other 25.6, Lighthouse 4.6, Nimbus 5.4, Teku 3.5, Lodestar 3.0, Prysm 0). Attestation-subnet deficits fall
  from 1,188 to 208.
- **Latency** from publish, p50 / p99: 0.09 / 0.49 s (50/15), 0.08 / 0.43 s (50/25), 0.08 / 0.60 s (1 Gbit).
- **κ** 9.0 → 9.9; PQ copies per message 4.1 → 4.7; IDONTWANT 10–14k ids per node per slot.
- **Bandwidth in the 4 s window**, mean / max node, % of cap: upload 42 / 63 (50/15), 27 / 41 (50/25), 6 / 13
  (1 Gbit); download ≤ 14 / 22.
- **Backlog.** After-deadline PQ kB per 1 Gbit node per slot: 152 → 1,340–1,555 from slot 12, duplicates (messages
  first delivered after the deadline ≤ 0.11 per node per slot). Links per node 216–240, flat; negative-score peers 16.4k at slot 4,
  then 12–13.5k. Failed sends that cost score 6.6M per slot (unbundled 9.5M). Stale copies: PQ 2,873, background
  66,689; nothing re-floods.
- **Background.** Blocks: none missing, first-seen p50 / p99 1.79 / 4.46 s. Columns: 311 of 669k missing.
  Attestations: 0.55 % of deliveries never arrive.
- **Memory and time.** Peak 215.4 GiB PSS; wall 10,847 s.

### 2,048 hosts × 20 slots, 2.4 kB, 16 signatures per message, seed 2: `R20-pq-b16-2k4-ps100-cf2-s2` (cf2)

×1.0, `--batch 16`, `--msg-bytes 2458`, seed 2, current Shadow build. P3 expected rate from the run's own mean: 68.38
messages per subnet per slot (seed 1: 66.93). Completion per slot (%, slots 0–19):

| class | per slot |
|---|---|
| 50/15 | 100 in every slot |
| 50/25 | 100 in every slot |
| 1 Gbit | 100 100 100 100 100 100 99.86 100 99.86 100 100 100 99.86 100 100 99.58 99.86 99.86 100 99.86 |

- **Strict rule: PASS with margin.** The worst slot is 15 (99.58 %, 3 of ~720 1 Gbit hosts incomplete; the rule
  allows 7). Slots 2–15 average 100 / 100 / 99.94 %, slots 16–19 100 / 100 / 99.90 % (seed 1: 99.87 / 99.73 %).
- **Incomplete node·slots**, 1 Gbit only: 6 in slots 2–15 (never 1, near miss 3, late 2) and 3 in slots 16–19 (near
  miss 2, late 1). No host is chronic: 6 hosts are incomplete at least once and none more than twice (1200,
  Lighthouse, Sydney; 233, Prysm, Sydney; 1726, Prysm, São Paulo; once each 1208, Lighthouse, Seoul; 1016, other, São
  Paulo; 1525, Prysm, São Paulo). No message is missed by more than half of its subscribers. No publish is refused;
  22 signatures are lost to churn.
- **PQ vs BLS.** PQ messages missing at 8 s on 1 Gbit hosts: 0.0006 % (slots 2–15) and 0.0005 % (16–19); home hosts
  miss none. BLS attestations missing in the same run: 0.013 / 0.020 / 0.98 % and 0.025 / 0.021 / 1.53 %.
- **P3.** As in seed 1, the PQ deficit penalties start at slot 15 and sit in Lighthouse and other views: 2,287 → 4,923
  per slot over slots 15–19 (seed 1: 1,302 → 2,527); from slot 15 per host: other 56.6, Lighthouse 9.0, Teku 6.8,
  Nimbus 5.2, Lodestar 4.2, Prysm 0. Attestation-subnet deficits fall from 1,640 to 275. No block or aggregate
  deficits (their P3 activates one epoch after graft, after the run ends).
- **Latency** from publish, p50 / p99: 0.08 / 0.46 s (50/15), 0.08 / 0.41 s (50/25), 0.08 / 0.49 s (1 Gbit).
- **κ** 8.9 → 10.3; PQ copies per message 4.1 → 4.8; IDONTWANT 10–14k ids per node per slot.
- **Bandwidth in the 4 s window**, mean / max node, % of cap: upload 41 / 65 (50/15), 26 / 41 (50/25), 6 / 12
  (1 Gbit); download ≤ 14 / 24.
- **Backlog.** After-deadline PQ kB per 1 Gbit node per slot: 107 → 1,290–1,570 from slot 12, duplicates (messages
  first delivered after the deadline ≤ 0.06 per node per slot). Links per node 204–226, flat; negative-score peers 15.6k at slot 4,
  then 11.3–12.7k. Failed sends that cost score 6.1M per slot (seed 1: 6.6M). Stale copies: PQ 2,557, background
  35,975; nothing re-floods (largest per-topic excess 1.024).
- **Background.** Blocks: none missing, first-seen p50 / p99 1.98 / 4.32 s. Columns: 54 of 610k missing.
  Attestations: 0.35 % of deliveries never arrive.
- **Memory and time.** Peak 207.5 GiB PSS; wall 10,699 s.

### 2,048 hosts × 20 slots, 2.4 kB, no extra 1 Gbit hosts: `R20-pq-fs0-2k4-ps100-cf2-s1` (cf2)

×1.0, `--fast-share 0`, `--msg-bytes 2458`, seed 1. Only hosts with more than 8 validators run at 1 Gbit (about 415,
against about 740 in the headline cell); every other host is a home staker. Completion per slot (%, slots 0–19):

| class | per slot |
|---|---|
| 50/15 | 100 in every slot |
| 50/25 | 100 in every slot except slot 1 (99.84) |
| 1 Gbit | 99.03 99.76 99.03 99.28 98.79 98.55 98.55 98.07 98.55 97.34 98.06 98.55 98.07 97.83 98.79 97.58 96.60 97.33 97.09 97.57 |

- **Strict rule: FAIL.** 1 Gbit hosts (about 413 online) fall below 99 % in 16 of the 18 slots from slot 2 (all but
  slots 2 and 3). The worst is slot 16 at 96.6 %: about 14 hosts incomplete, where the rule allows 4. Home classes hold
  all their messages in every slot from slot 2. Slots 2–15 average 100 / 100 / 98.36 %, slots 16–19
  100 / 100 / 97.15 %.
- **PQ vs BLS.** PQ messages missing at 8 s on 1 Gbit hosts: 0.093 % (slots 2–15) and 0.164 % (16–19), about 10× the
  headline cell; home hosts miss none. BLS attestations missing in the same run: 0.145 / 0.109 / 2.36 % and
  0.133 / 0.093 / 2.68 %. fs0 has no matched no-PQ run (`R20-nopq-ps100-cf2-s1` keeps the default link mix), so a
  comparison with the no-PQ baseline is unmatched, and the difference is not attributed to PQ.
- **Who misses.** 142 incomplete 1 Gbit node·slots (whole subnet 8, never 42, near miss 37, late 55); 33 of 415 hosts
  are incomplete at least once. Chronic: 1702 (Prysm, Singapore, 17 of 18 slots), 22 (Prysm, Seoul, 15), 1027 and 202
  (Prysm, Singapore, 13 each), 889 (Prysm, Sydney, 10), 794 (Prysm, Singapore, 9), 145 (Prysm, Singapore, 7) and 930
  (Lighthouse, Sydney, 7). All of these Prysm hosts have 70 peers. 939 (Teku, Seoul), 294 (Prysm, São Paulo) and 191
  (Prysm, US West) start missing in slots 16–19.
- **P3** from slot 15: PQ 504 → 447 and attestation 1,480 → 170 per slot; block and aggregate 0. Per host, PQ /
  attestation: Lighthouse 0.68 / 0.44, other 6.70 / 0.53, Teku 1.59 / 5.88, Lodestar 0.92 / 6.25, Nimbus 2.50 / 3.52,
  Prysm 0. Negative-score peers per observer: Lighthouse 12.4, other 20.1, Teku, Lodestar, Nimbus and Prysm 0.2–0.3.
- **Latency** from publish, p50 / p99: 0.11 / 0.75 s (50/15), 0.10 / 0.69 s (50/25), 0.12 / 1.19 s (1 Gbit).
- **κ** 12.2 → 13.5 (headline 9.4 → 10.3); PQ copies per message 3.9 → 4.4; IDONTWANT 11–14k ids per node per slot.
- **Bandwidth in the 4 s window**, mean / max node, % of cap: upload 43 / 68 (50/15), 27 / 42 (50/25), 6 / 14
  (1 Gbit); download ≤ 14 / 23.
- **Backlog.** After-deadline PQ kB per 1 Gbit node per slot: 261 → 1,666 (headline 194 → 1,554), mostly duplicates
  (messages first delivered after the deadline: 1.22 per 1 Gbit node per slot in slots 2–15 and 2.25 in 16–19,
  rising from 0.18 at slot 2 to 1.4–3.3 in slots 14–19). Links per node 197–216 and connections 163–165 per node, flat;
  negative-score peers 16–21k per slot from slot 3. Failed sends that cost score: 168.9M in all (forward timeout 36.4 %,
  forward queue full 46.5 %, control queue full 16.9 %). Stale copies: PQ 5,686, background 54,116; bgexcess ≤ 1.011,
  so nothing re-floods. No refused publish.
- **Blocks:** none missing; first-seen p50 / p99 1.94 / 5.82 s (fewer 1 Gbit hosts carry them).
- **Memory and time.** Peak 213.8 GiB PSS; wall 10,786 s.
- **Against the headline cell** (fast share 0.2, about 740 1 Gbit hosts), which passes with one chronic host: without
  the extra 1 Gbit hosts, the far-region Prysm hosts with 70 peers miss in most slots. The 6-slot fs0 cell failed the
  same way (`R6-pq-fs0-ps100-cf-s1`, 3 kB: 1 Gbit 97.64 %, worst slot 97.09 %).

### 2,048 hosts × 20 slots, 2.4 kB, no extra 1 Gbit hosts, rtt4 Shadow build: `R20-pq-fs0-2k4-rtt4-ps100-cf2-s1` (cf2)

The fs0 cell above on the rtt4 Shadow build, with tcpd logging; nothing else differs (×1.0, `--fast-share 0`,
`--msg-bytes 2458`, seed 1). Completion per slot (%, slots 0–19):

| class | per slot |
|---|---|
| 50/15 | 100 in every slot except slot 15 (99.76) |
| 50/25 | 100 in every slot except slot 19 (99.92) |
| 1 Gbit | 97.34 99.03 99.03 98.31 99.28 98.55 98.31 98.55 98.07 97.82 98.06 98.31 98.07 98.31 98.31 98.55 97.82 98.54 97.82 97.82 |

- **Strict rule: FAIL.** 1 Gbit hosts (about 413 online) fall below 99 % in 16 of the 18 slots from slot 2 (all but
  slots 2 and 4). The worst is 97.82 % in slots 9, 16, 18 and 19: 9 hosts incomplete, where the rule allows 4.
  Slots 2–15 average 99.98 / 100 / 98.39 %, slots 16–19 100 / 99.98 / 98.00 % (current build: 1 Gbit 98.36 and
  97.15 %, worst slot 96.6 %).
- **PQ vs BLS.** PQ messages missing at 8 s on 1 Gbit hosts: 0.049 % (slots 2–15) and 0.084 % (16–19), about half
  the current build's 0.093 and 0.164 %; home hosts miss at most 0.0007 %. BLS attestations missing in the same run:
  0.075 / 0.045 / 2.59 % and 0.113 / 0.090 / 2.94 % (current build 0.145 / 0.109 / 2.36 and 0.133 / 0.093 / 2.68 %).
  As for fs0 on the current build, no matched no-PQ run exists, so a comparison with the no-PQ baselines is
  unmatched, and the difference is not attributed to PQ.
- **Who misses.** 126 incomplete 1 Gbit node·slots (whole subnet 2, never 30, near miss 38, late 56; current build
  142); 28 of 415 hosts are incomplete at least once (current build 33). Chronic: 1027 (Prysm, Singapore, 18 of 18
  slots), 22 (Prysm, Seoul, 16), 525 (Prysm, São Paulo, 13), 794 (Prysm, Singapore, 12) and 1518 (Prysm, Tokyo, 9),
  all with 70 peers; then 930 (Lighthouse, Sydney, 8), 145 (Prysm, Singapore, 7) and 1244 (Teku, Singapore, 7). The
  set shifts between builds (1702, chronic on the current build in 17 slots, misses in 3 here), but the failure mode
  is the same: far-region Prysm hosts with 70 peers.
- **P3** from slot 15: PQ 537 → 458 and attestation 1,531 → 238 per slot; block and aggregate 0. Per host, PQ /
  attestation: Lighthouse 0.87 / 0.18, other 1.82 / 4.23, Teku 1.83 / 7.56, Lodestar 3.77 / 3.57, Nimbus 2.40 / 4.19,
  Prysm 0. Negative-score peers per observer: Lighthouse 13.4, other 21.1, Teku, Nimbus, Prysm and Lodestar
  0.14–0.27.
- **Latency** from publish, p50 / p99: 0.11 / 0.78 s (50/15), 0.10 / 0.70 s (50/25), 0.12 / 1.16 s (1 Gbit).
- **κ** 12.2 → 13.5; PQ copies per message 3.8 → 4.4; IDONTWANT 11–14k ids per node per slot (all as on the current
  build).
- **Bandwidth in the 4 s window**, mean / max node, % of cap: upload 43 / 65 (50/15), 27 / 46 (50/25), 6 / 13
  (1 Gbit); download ≤ 14 / 23.
- **Backlog.** After-deadline PQ kB per 1 Gbit node per slot: 195 → 1,213–1,338 from slot 12 (current build
  261 → 1,666), mostly duplicates (messages first delivered after the deadline: 0.86 per 1 Gbit node per slot in slots 2–15
  and 1.29 in 16–19, at most 1.58). Home hosts' after-deadline bytes rise
  slowly, 17 → 85 kB (50/15) and 20 → 68 kB (50/25). Links per node 192–217 and connections 163–165 per node, flat;
  negative-score peers 17–23k per slot from slot 3. Failed sends that cost score: 184.5M in all (forward timeout
  34.8 %, forward queue full 48.1 %, control queue full 17.0 %). Stale copies: PQ 3,809, background 41,280; bgexcess
  ≤ 1.013. Churn removes 388 of 40,000 signatures, as on the current build; no refused publish.
- **TCP** (path types by sender → receiver). Resends per 1,000 data packets, flat over the run: 1G→1G 0.24,
  1G→home 3.26, home→1G 1.73, home→home 10.43. First timeouts per 1,000 data packets climb as in the headline rtt4
  run (slots 2 → 18): home→home 8.9 → 19.5, 1G→home 2.8 → 4.9, home→1G 0.6 → 1.7, 1G→1G 0.06 → 0.09. 96.1 % of
  timeout episodes are spurious and undone; no stalls; the RTO formula holds in every snapshot without backoff. The
  same endpoints' windows shrink from slot 2 to 19 (cwnd p50 1G→1G 441 → 92, home→home 105 → 25 segments).
- **Blocks:** none missing; first-seen p50 / p99 1.94 / 5.88 s from slot start.
- **Memory and time.** Peak 211.4 GiB PSS; wall 11,131 s.
- **Reading.** rtt4 removes about half of fs0's PQ misses and lifts its worst slot from 96.6 to 97.82 %. So the RTO
  ratchet inflated this failure but does not explain it: without the extra 1 Gbit hosts the cell fails on both
  builds, and the headline pass depends on them. fs0 with 16 signatures per message ran on rtt6
  instead and fails too (next section).

### 2,048 hosts × 20 slots, 2.4 kB, no extra 1 Gbit hosts, 16 signatures per message, rtt6 (Linux's CUBIC with HyStart): `R20-pq-fs0-b16-2k4-rtt6-ps100-cf2-s1` (cf2)

The fs0 cell's flags (×1.0, `--fast-share 0`, `--msg-bytes 2458`, seed 1) with 16 signatures per message
(`--batch 16`, P3 rate 66.58 from its own schedule), on rtt6 with TCP logging. It runs on rtt6 because the bundled
rtt6 cell with the default link mix (`R20-pq-b16-2k4-rtt6-ps100-cf2-s1`) passed the strict rule. A first attempt was
stopped at sim 92 s while another user's Shadow sweep needed the machine; this run started from scratch at 19:30 Nov 11.
Completion per slot (%, slots 0–19):

| class | per slot |
|---|---|
| 50/15 | 100 in every slot |
| 50/25 | 100 in every slot except slot 17 (99.92) |
| 1 Gbit | 98.07 99.76 99.76 99.28 99.28 99.28 99.28 99.28 99.28 99.76 99.03 99.52 98.79 99.03 98.79 98.55 98.79 98.79 99.76 98.30 |

- **Strict rule: FAIL.** 1 Gbit hosts (about 413 online) fall below 99 % in 6 of the 18 slots from slot 2 (slots 12,
  14–17 and 19). The worst is slot 19 at 98.30 %: 7 hosts incomplete, where the rule allows 4. Slots 2–15 average
  100 / 100 / 99.21 %, slots 16–19 100 / 99.98 / 98.91 %; one home node·slot is incomplete (50/25, slot 17: 3
  messages, all within 1 s after the deadline). Unbundled fs0: 98.39 and 98.00 % on rtt4 (worst 97.82 %), 98.36 and
  97.15 % on the current build (worst 96.6 %). b16 with the default link mix: 99.94 and 99.83 % on rtt6 (worst 99.73
  %), 99.87 and 99.73 % on the current build (worst 99.59 %).
- **PQ vs BLS.** PQ messages missing at 8 s on 1 Gbit hosts: 0.0206 % (slots 2–15) and 0.0185 % (16–19); home hosts
  miss at most 0.0009 %. Unbundled fs0 misses 0.049 and 0.084 % on rtt4 and 0.093 and 0.164 % on the current build,
  but there a message is one signature, while here it holds up to 16. BLS attestations missing in the same run:
  0.060 / 0.026 / 1.97 % and 0.036 / 0.028 / 2.50 %, so on 1 Gbit hosts PQ messages miss 96–135× less often than
  attestations. As for the other fs0 runs, no matched no-PQ run exists (`R20-nopq-rtt6-ps100-cf2-s1`, queued, has
  the default link mix), so a comparison with the no-PQ baselines is unmatched, and the difference is not attributed
  to PQ.
- **Who misses.** 64 incomplete 1 Gbit node·slots (never 29, near miss 18, late 17; unbundled fs0 on rtt4 126, on
  the current build 142): 46 in slots 2–15 and 18 in 16–19. 18 of 415 hosts are incomplete at least once (rtt4 28,
  current build 33): 11 Prysm, 4 Lighthouse, 2 Teku and 1 other. One host is chronic: 22 (Prysm, Seoul, 70 peers, 11
  of 18 slots), chronic on rtt4 (16) and on the current build (15) too. Then 219 (Prysm, Paris, 8), 930 (Lighthouse,
  Sydney, 8), 1702 (Prysm, Singapore, 7), 525 (Prysm, São Paulo, 6) and 226 (Prysm, Tokyo, 5). As in the unbundled
  fs0 runs, Prysm hosts with 70 peers dominate (9 of the 12 hosts incomplete in two or more slots), most of them in
  far regions; 219 (Paris) is an exception. Of rtt4's other chronic hosts, 1027 (18 slots there) and 794 (12) miss
  at most once here, and 1518 (9) three times.
- **Over the run.** 1 Gbit completion falls: mean 99.36 % in slots 2–7, 99.23 % in 8–13 and 98.83 % in 14–19
  (unbundled fs0 on rtt4 98.67, 98.11 and 98.14 %; b16 on rtt6 with the default mix 99.93, 99.98 and 99.84 %), with
  5 of the 6 failing slots in 14–19. PQ message misses rise in the same blocks: 0.0119, 0.0216 and 0.0267 %. On
  1G→1G paths ssthresh after a restart falls from 125 at slot 2 to 70–75 from slot 8 on (default-mix cell 85–91 from
  slot 9); on paths with a home end it falls to 24 (1G→home), 33 (home→1G) and 14 (home→home) by slot 18
  (default-mix cell 25, 37 and 14). Block first-seen from publish, p95, is 0.85, 0.69 and 0.67 s in the three
  blocks, 1.6–1.8× unbundled fs0 on rtt4 and 1.13–1.24× the default-mix b16 cell on rtt6, so it does not grow as
  ssthresh falls. Per slot (slots 2–19; ssthresh slots 2–18, u = more than half of the restarts on connections that
  never reduced it):

| series | per slot |
|---|---|
| block first-seen from publish p95, fs0 rtt4 (s) | 0.71 0.49 0.32 0.36 0.38 0.55 0.49 0.46 0.50 0.49 0.34 0.31 0.42 0.32 0.27 0.44 0.54 0.50 |
| block first-seen from publish p95, b16 current build (s) | 0.32 0.29 0.34 0.37 0.52 0.28 0.31 0.31 0.33 0.34 0.39 0.35 0.31 0.30 0.42 0.34 0.31 0.38 |
| block first-seen from publish p95, b16 rtt6, default link mix (s) | 0.78 0.69 0.75 0.60 0.81 0.58 0.65 0.48 0.62 0.66 0.55 0.41 0.61 0.57 0.58 0.53 0.53 0.75 |
| block first-seen from publish p95, fs0-b16 rtt6 (s) | 0.86 1.02 0.76 0.72 0.67 1.09 0.83 0.77 0.72 0.70 0.57 0.58 0.76 0.51 0.45 0.69 0.84 0.78 |
| ssthresh p50 after a restart, 1G→1G | 125 99 85 81 80 76 75 73 73 74 72 70 73 72 72 72 72 |
| ssthresh p50 after a restart, 1G→home | 136 65 44 36 33 31 30 28 27 26 25 25 25 24 24 24 24 |
| ssthresh p50 after a restart, home→1G | u 160 88 65 55 51 46 43 40 37 36 35 34 33 33 32 33 |
| ssthresh p50 after a restart, home→home | u u u 105 39 25 21 18 17 16 16 16 15 15 15 15 14 |
| 1 Gbit completion, fs0 rtt4 (%) | 99.03 98.31 99.28 98.55 98.31 98.55 98.07 97.82 98.06 98.31 98.07 98.31 98.31 98.55 97.82 98.54 97.82 97.82 |
| 1 Gbit completion, fs0-b16 rtt6 (%) | 99.76 99.28 99.28 99.28 99.28 99.28 99.28 99.76 99.03 99.52 98.79 99.03 98.79 98.55 98.79 98.79 99.76 98.30 |
| 1 Gbit PQ messages missing at 8 s, fs0 rtt4 (%, one signature per message) | 0.0083 0.0231 0.0217 0.0496 0.0469 0.0625 0.0347 0.0684 0.0835 0.0394 0.0735 0.0661 0.0535 0.0556 0.0566 0.0714 0.1190 0.0897 |
| 1 Gbit PQ messages missing at 8 s, fs0-b16 rtt6 (%, up to 16 signatures per message) | 0.0062 0.0032 0.0067 0.0280 0.0204 0.0068 0.0011 0.0079 0.0257 0.0352 0.0242 0.0357 0.0372 0.0492 0.0221 0.0259 0.0031 0.0229 |

- **CUBIC and HyStart.** Data packets sent with cwnd ≥ ssthresh: 75.7 % (1G→1G), 69.7 % (1G→home), 70.7 % (home→1G)
  and 67.6 % (home→home), 71.4 % in all (b16 on rtt6 with the default mix 72.3 / 68.9 / 68.3 / 67.2 %, 70.4 % in
  all). HyStart exits, ack train / delay: 5,186 / 0 (1G→1G), 1,458 / 1,663 (1G→home), 2,353 / 3,588 (home→1G), 0 /
  5,949 (home→home), with cwnd at exit p50 (p90) 44 (224), 87 (202), 74 (238) and 108 (239). Train exits: the ack
  train spans 4.9 ms at p50 against a threshold of 4.6 ms (delay_min p50 8.2 ms); delay exits: the round's minimum
  RTT sample is 5.9 ms above delay_min at p50 (threshold 4.4 ms; delay_min p50 35.2 ms). The CUBIC checks hold as in
  the default-mix cells: all 367,842 logged window targets (49,384 traced epochs) equal Linux's integer formula, no
  congestion-avoidance round grows by more than one segment per two packets ACKed, plus one, and all 250,963 traced
  epoch shifts equal min(epoch + idle, now).
- **P3** from slot 15: PQ 914 → 1,813 per slot (2,089 at slot 18) and attestation 1,631 → 260; block and aggregate
  0. Per host, PQ / attestation: Lighthouse 5.14 / 0.85, other 12.12 / 0.31, Teku 1.61 / 7.68, Lodestar 3.08 / 6.58,
  Nimbus 4.66 / 3.42, Prysm 0. Negative-score peers per observer: Lighthouse 13.2, other 21.3; Teku, Lodestar,
  Nimbus and Prysm 0.16–0.23.
- **Latency** from publish, p50 / p99: 0.12 / 0.78 s (50/15), 0.11 / 0.71 s (50/25), 0.13 / 0.96 s (1 Gbit);
  unbundled fs0 on rtt4 0.11 / 0.78, 0.10 / 0.70 and 0.12 / 1.16 s; b16 on rtt6 with the default mix 0.10 / 0.60,
  0.09 / 0.58 and 0.09 / 0.68 s.
- **κ** 11.7 → 13.2 (at most 13.5); PQ copies per message 3.89 → 4.51; IDONTWANT 6.3–8.6k ids per node per slot
  (unbundled fs0 on rtt4 12.2 → 13.5, 3.8 → 4.4 and 11–14k; b16 on rtt6 with the default mix 8.8 → 9.9, 3.86 → 4.66
  and 9.8–14.1k).
- **Bandwidth in the 4 s window**, mean / max node, % of cap: upload 41 / 65 (50/15), 26 / 43 (50/25), 6 / 14 (1
  Gbit); download ≤ 13 / 22 (unbundled fs0 on rtt4 within 3 points of these).
- **Backlog.** After-deadline PQ kB per 1 Gbit node per slot: 301 at slot 2, 827 at slot 8, then 886–1,157 over
  slots 9–19, +16.8 kB per slot over slots 10–19 (b16 on rtt6 with the default mix +16.5). Home hosts: 50/15 19 → 56
  kB, 50/25 20 → 44 kB, +1.6 and +1.3 kB per slot over slots 10–19. Messages first delivered after the deadline:
  0.15 per 1 Gbit node per slot in slots 2–15 and 0.17 in 16–19, at most 0.44 (slot 15), below the 1 Gbit misses at
  8 s in every slot, and 0 on home hosts; they stay at a few tenths per node per slot and do not build up, so the
  bytes are mostly copies of messages already held. Links per node 194–217 and connections 163–165 per node, flat.
  Negative-score peers peak at 22.2k in slot 5 and settle at 17.2–19.3k from slot 7. Failed sends that cost score:
  141.1M (forward timeout 45.3 %, forward queue full 48.3 %, control queue full 6.4 %; unbundled fs0 on rtt4 184.5M,
  b16 on rtt6 with the default mix 131.0M). Stale copies: PQ 0, background 20; bgexcess ≤ 1.013 on background
  topics. Churn removes 388 of 40,000 signatures (in 160 messages), as in both unbundled fs0 runs; no refused
  publish.
- **TCP** (path types by sender → receiver):
  - Restarts after idle: about 1.39M per slot (1G→1G 74k, 1G→home 310k, home→1G 314k, home→home 693k), flat; median
    idle time 0.85–1.00 s against a median RTO of 0.29–0.36 s. cwnd before → after, p50 (p90): 17 (76) → 10 (24) on
    1G→1G and 10 (22–31) → 10 (10) elsewhere. 89 % of restarts leave cwnd below ssthresh, and all of those continue
    in slow start.
  - cwnd p50 / p90 over the run: 10 / 51 (1G→1G), 10 / 20 (1G→home), 10 / 21 (home→1G), 10 / 18 (home→home); b16 on
    rtt6 with the default mix 10 / 29, 10 / 18, 10 / 19 and 10 / 18.
  - Fast-recovery entries per 1,000 data packets: 0.24 (1G→1G), 1.48 (1G→home), 1.43 (home→1G), 2.35 (home→home),
    all after consecutive duplicate ACKs.
  - Resends per 1,000 data packets, flat: 0.27, 3.09, 1.81 and 9.54. First timeouts per 1,000 data packets climb
    (slots 2 → 18): home→home 8.3 → 18.4, 1G→home 2.5 → 4.6, home→1G 0.70 → 1.93, 1G→1G 0.07 → 0.10, as in the
    default-mix rtt6 cells. 9.53M RTOs (b16 on rtt6 with the default mix 7.92M); 96.0 % of Eifel checks found the
    timeout spurious and undid it, and 66 % of first timeouts start within 1 s after such an undo on the same
    connection; every RTO sets cwnd to in-flight + 1; no stalls (6.95M snapshots); the RTO formula holds in all
    6,309,266 snapshots without backoff; buffers start at 131,072 / 174,760 B on every connection.
- **Blocks:** none missing; from publish p50 / p95 / p99 0.38 / 0.80 / 1.05 s (unbundled fs0 on rtt4 0.21 / 0.51 /
  0.66 s; b16 on rtt6 with the default mix 0.33 / 0.65 / 0.84 s; b16 on the current build 0.19 / 0.36 / 0.48 s),
  slower than the default-mix cell most likely because fewer 1 Gbit hosts carry them. Attestations after 4 s p50 /
  p95 / p99 1.08 / 2.24 / 3.97 s; 0.67 % never arrive (unbundled fs0 on rtt4 1.07 / 2.28 / 4.29 s and 0.93 %).
- **Memory and time.** Peak 209.9 GiB PSS; wall 9,978 s; TCP log 3.3 GB compressed.
- **Reading.** With bundles on rtt6, fs0 has half as many incomplete 1 Gbit node·slots as unbundled fs0 on rtt4 (64
  against 126), and its worst slot rises from 97.82 to 98.30 %, but it still fails, and completion falls over the
  run (99.36 → 98.83 % per 6-slot block). The run changes two things against fs0 on rtt4, bundles and build; with
  the default link mix the unbundled cell does no better on rtt6 than on rtt4 (40 against 29 incomplete node·slots),
  so most of the gain is likely from bundling. So the pass depends on the extra 1 Gbit hosts with bundles too. No
  queued run depends on this result.

### 2,048 hosts × 20 slots, 3 kB: `R20-pq-ps100-cf2-s1` (cf2, final model, sensitivity point)

Completion per slot (%, slots 0–19):

| class | per slot |
|---|---|
| 50/15 | 100 in every slot |
| 50/25 | 100 in every slot |
| 1 Gbit | 99.32 99.86 99.73 100 99.86 99.46 99.86 99.32 99.46 99.59 99.32 99.32 99.19 98.78 99.19 99.32 98.65 98.78 99.05 98.79 |

- **Incomplete node·slots** occur on 1 Gbit hosts only. Slots 2–15: 56 (late > 1 s 25, near miss ≤ 1 s 23, never
  received 7, whole subnet 1). Slots 16–19: 35 (late 16, near miss 9, never 7, whole subnet 2, one host that had just
  rejoined). Far fewer messages are never received than in `cf` (58 and 27 node·slots).
- **Chronic hosts** (incomplete in ≥ 9 of 18 slots): 640 (Prysm, Sydney, 14), 945 (Lighthouse, São Paulo, 9) and 988
  (Prysm, São Paulo, 9). 14 hosts are incomplete in ≥ 2 slots: 8 Prysm, 5 Lighthouse, 1 Teku.
  - The Prysm ones score almost no peer negative in their own view (Prysm has neither the slow-peer nor the P3 term).
  - The far-region Lighthouse hosts (945, 1084, 930, 1860, 1278) score 57–116 of their ~200 peers negative: their own
    sends fail on long lossy paths. Up to 90 peers score 945 negative, the non-Rust ones from slot 6 with
    broken-promise (P7) penalties of −140 to −400.
- **Latency** from publish, p50 / p99: 0.10 / 0.74 s (50/15), 0.10 / 0.63 s (50/25), 0.09 / 0.78 s (1 Gbit).
- **κ and duplicates.** κ rises from 8.2 to 9.0, PQ copies per message from 3.7 to 4.4; IDONTWANT carries 16–22k ids
  per node per slot.
- **Bandwidth in the 4 s window**, mean / max node, % of cap: upload 47 / 71 (50/15), 31 / 49 (50/25), 7 / 15
  (1 Gbit); download ≤ 16 / 26.
- **Backlog.** After-deadline PQ kB per node per slot grow at first, then flatten: 1 Gbit 261 → 1,730–1,925 from slot
  12, 50/25 23 → ~110. They are duplicates (1 Gbit: 73 → 600 copies per node in 8–16 s); messages first delivered after
  the deadline average 0.28 per 1 Gbit node per slot in slots 2–15 and 0.60 in 16–19 (at most 0.83).
- **Mesh.** 215–236 links per node, flat; connections 165 per node; PQ mesh degree 5.9–7.4.
- **Negative-score peers** rise to 22.6k (slot 4) and settle at 16–18k. Per observer: Lighthouse 13.0, other 20.1,
  Lodestar 0.28, Nimbus 0.22, Teku 0.21, Prysm 0.17.
- **Mesh-delivery (P3) penalties** start at slot 15: 2.0k, 1.2k, 1.1k, 0.84k and 0.77k per slot (cf: 3.6k → 1.4k).
  By topic: PQ 1,036 → 667, attestation subnets 923 → 103, blocks and aggregates 0. From slot 15, by observer client
  (per host): Lighthouse PQ 1.30, attestation 0.48; other PQ 8.17, attestation 0.44; Teku 3.90 / 2.28; Lodestar
  3.66 / 3.66; Nimbus 3.33 / 3.61; Prysm 0. Teku, Lodestar and Nimbus views spike at slot 15, then settle.
- **IWANT.** Prysm, Teku, Lodestar and Nimbus hosts re-request 11–17 ids per IWANT that are still awaited from another
  peer (7.3M in total); Lighthouse and other hosts never do. Broken promises per IWANT: Lighthouse 0.050, other 0.036,
  Prysm 0.008, Teku 0.003, Lodestar 0.002.
- **Failed sends** that cost score: 9.9M per slot (forward timeout 33 %, forward queue-full 39 %, control queue-full
  28 %), as in `cf`.
- **Stale messages.** 8,338 PQ and 57,842 background copies older than 60 s were ignored; nothing re-floods (bgexcess
  ≤ 1.010).
- **Memory and time.** Peak 229.7 GiB PSS; wall 11,864 s.
- **Slot 16.** The step is half as large as in `cf` (1 Gbit 99.32 → 98.65 %, against 98.51 → 97.57 %), with the same
  signature. Hosts 930 (Lighthouse, Sydney), 1873 (Prysm, São Paulo) and 1175 (Prysm, Tokyo) miss 0–4 messages per
  slot in slots 2–14 and 47–157 in slots 16–19. Their connections and peer turnover do not change, but the 1 Gbit
  share of their PQ mesh falls (0.76 → 0.72, 0.88 → 0.82, 0.80 → 0.72; 129 other far-region 1 Gbit hosts:
  0.89 → 0.88), and Teku, Lodestar and Nimbus views start scoring 1873 negative at slot 16 with P3-sized scores.

### 2,048 hosts × 20 slots: `R20-pq-ps100-cf-s1` (cf)

Completion per slot (%, slots 0–19):

| class | per slot |
|---|---|
| 50/15 | 100 100 100 100 100 100 99.7 99.7 100 100 99.7 100 100 100 99.7 100 99.7 99.7 100 100 |
| 50/25 | 100 100 100 100 100 100 100 100 99.9 100 100 100 100 100 100 100 100 99.9 100 100 |
| 1 Gbit | 98.51 99.59 99.32 99.19 99.19 99.19 98.92 98.78 98.65 98.92 98.51 99.05 98.92 98.65 98.78 98.51 97.57 98.24 97.57 97.57 |

- **Incomplete node·slots** (50/15 / 50/25 / 1 Gbit):
  - Slots 2–15: 4 / 1 / 114. On 1 Gbit hosts: never received 58 (8.0k msgs), late > 1 s 29, near miss ≤ 1 s 24, whole
    subnet 3. 22 of 742 hosts are incomplete at least once, and 96 % of node·slots fall on hosts incomplete ≥ 2 times.
  - Slots 16–19: 2 / 1 / 67. On 1 Gbit hosts: never 27 (4.8k msgs), late 27, near miss 9, whole subnet 4; 27 hosts.
  - None follows a restart or a join.
- **Latency** from publish, p50 / p99: 0.10 / 0.76 s (50/15), 0.10 / 0.62 s (50/25), 0.09 / 0.75 s (1 Gbit).
- **κ and duplicates.** κ (bytes received per useful byte, background included) rises from 8.1 to 9.0. PQ copies per
  message rise from 3.7 to 4.4. IDONTWANT carries 16–22k ids per node per slot.
- **Bandwidth in the 4 s window**, mean / max node, % of cap: upload 46 / 74 (50/15), 31 / 48 (50/25), 7 / 16
  (1 Gbit); download ≤ 15 / 25.
- **Backlog.** After-deadline PQ kB per node per slot grow at first: 50/15 17 → 117, 50/25 16 → 94, 1 Gbit 211 →
  1,728, with a plateau at ~1,450–1,750 from slot 8. They are duplicates pushed by mesh peers (1 Gbit: 69 → 582 copies
  per node in 8–16 s). IWANT replies are ~0, and messages first delivered after the deadline rise from 0.06 per
  1 Gbit node per slot at slot 2 to 1.7–2.4 in slots 15–19.
- **Mesh.** 215–235 links per node, flat, against 227 → 194 in the every-client −10 key cell. Connections 164 per
  node; PQ mesh degree 5.9–7.4.
- **Negative-score peers** rise to 22.9k (slot 4) and settle at 16–17k. Per observer: Lighthouse 12.6, other 20.2,
  Prysm 0.64, Nimbus 0.42, Teku 0.40, Lodestar 0.23.
- **Failed sends:** 9.7M per slot.
  - 1 Gbit hosts on non-Rust clients: forward queue-full 48.5 %, control queue-full 33.3 %, forward timeout 18.1 %.
  - 1 Gbit hosts on Rust clients: 48 / 29 / 23 %.
  - Home hosts: 98–100 % forward timeouts.
- **Stale messages.** 9,484 PQ and 54,477 background copies older than 60 s were ignored; nothing re-floods
  (bgexcess within ±1.6 %).
- **Memory and time.** Peak 227.1 GiB PSS; wall 11,709 s.

#### What changes at slot 16

- **P3 activates at slot 15.** Mesh-delivery scoring on the attestation and PQ subnets starts 17 slots (204 s) after a
  link is grafted, so the warm-up links activate at slot 15. Blocks and aggregates wait 1 epoch, past the 280 s run.
- **Network-wide, P3 is small.** MessageDeficit penalties go from 0 to 3.5k in slot 15 and 1.4–2.1k per slot after.
  They are counted per peer, topic and heartbeat, so about 150–300 deficient peer-topic pairs exist at a time. The
  ~16.5k negative-score peers do not rise.
- **Most of these deficits come with the PQ topics.** The no-PQ run on the old binary shows 0.4–0.8k per slot.
- **Prysm and Nimbus observers see about 10× more deficits per host than Lighthouse observers** (D = 8 vs 5).
- **The 8 chronic hosts are not affected.** Their prunes stay flat, and non-Rust views never score 640 negative.
- **Six far-region 1 Gbit hosts start missing in slots 16–19:** 818 (Nimbus, Singapore), 1960, 1873 and 988 (Prysm,
  São Paulo), 1800 (Prysm, Tokyo), 1944 (Teku, Tokyo). Compared with slots 2–14, and with 129 other 1 Gbit hosts in
  the same cities:
  - unchanged: connected peers, peer turnover (1–3 peers dropped and added per slot, none of them offline or
    restarting) and failed sends (lower after slot 15, as in the control group). TCP retransmissions are not logged in
    these runs.
  - changed, on these hosts only:
    - Peers prune them more. PQ prunes received per slot: 1960 9 → 50, 1944 22 → 53, 1800 39 → 67.
    - They drop out of others' PQ meshes. In-degree: 1873 ~90 → 30–43.
    - They lose 1 Gbit mesh peers. 1 Gbit share of their own PQ mesh: 0.86–0.96 → 0.76–0.87, while the control group
      stays at 0.88–0.89.
  - **Non-Rust views start scoring them negative exactly at slot 16:** none before, 1–6 views after, with P3-sized
    scores. Non-Rust views have no slow-peer term in cf, so only P3 (or P7, which gives scores in the thousands) can
    do this.
- **Reading:** far-region hosts rarely deliver first, so their peers' P3 counters fall short. From activation those
  peers prune them, and they slide toward the edge of the 1 Gbit mesh. cf2 changes this mechanism per client (P3 off
  in Prysm views, 8.7× heavier in Teku, Lodestar and Nimbus views).

### 2,048 hosts × 20 slots, 16 signatures per message: `R20-pq-b16-ps100-cf-s1` (cf)

The P3 expected rate comes from the 1,071 messages actually published per slot (66.9 per subnet). Completion in % of
node·slots; miss rates in % at 8 s, 50/15 / 50/25 / 1 Gbit.

| slots | 50/15 | 50/25 | 1 Gbit | PQ messages missing | BLS attestations missing, same run |
|---|---|---|---|---|---|
| 2–15 | 100 | 99.99 | 99.22 | 0 / 0.0002 / 0.053 | 0.27 / 0.25 / 2.58 |
| 16–19 | 100 | 100 | 99.22 | 0 / 0 / 0.051 | 0.054 / 0.099 / 1.85 |

Strict rule: FAIL, only because 1 Gbit hosts dip to 98.92 % in slot 12 and 98.78 % in slot 14. Every other slot from
slot 2 on is ≥ 99.05 %, and slots 16–19 all pass.

- **No step at P3 activation**, although MessageDeficit penalties are higher than in R20-cf (4.2–5.3k per slot from
  slot 15, against 1.4–3.6k).
- **Who misses:** far-region Prysm 1 Gbit hosts: 1873 (São Paulo) in every slot; 794 (Singapore), 852 (São Paulo),
  640 (Sydney) and 1355 (Tokyo) in 8–9 of slots 2–15.
- **Latency** from publish, p50 / p99: 0.09 / 0.56, 0.09 / 0.47, 0.09 / 0.57 s. PQ copies per message 4.27.
- **Failed sends** that cost score: 122M over 20 slots (forward timeout 43 %, forward queue-full 46 %, control
  queue-full 10 %). Negative-score peers 13–18k; links per node flat at 214–236.
- **Backlog:** none in completion or meshes. PQ bytes arriving after the deadline grow, as in R20-cf: 1 Gbit hosts
  229 → 1,700–1,870 kB per node per slot (plateau from slot 12), 50/25 hosts 19 → ~70 kB. They are duplicate copies:
  messages first delivered after the deadline stay ≤ 0.68 per 1 Gbit node per slot. 2,148 PQ and 47,487 background copies older than 60 s
  were ignored; no recirculation (bgexcess ≤ 1.012).
- **Memory and time:** peak 219.1 GiB PSS; wall 10,575 s.

### 2,048 hosts × 20 slots, every client −10: `R20-pq-ps100-age60-s1` (age60, conservative)

Completion in % of node·slots; miss rates in % at 8 s, 50/15 / 50/25 / 1 Gbit.

| slots | 50/15 | 50/25 | 1 Gbit | PQ messages missing | BLS attestations missing, same run |
|---|---|---|---|---|---|
| 2–5 | 100 | 99.97 | 99.06 | – | – |
| 2–15 | 99.96 | 99.99 | 98.78 | 0.0024 / 0.0009 / 0.068 | 0.31 / 0.37 / 2.95 |
| 16–19 | 100 | 100 | 98.31 | 0 / 0 / 0.177 | 0.36 / 0.52 / 3.84 |
| 2–19 | 99.97 | 99.99 | 98.68 | 0.0019 / 0.0007 / 0.092 | 0.32 / 0.40 / 3.15 |

The 1 Gbit class fails from slot 4 (worst slot 97.97 %, slot 12). Strict rule: FAIL, 1 Gbit only.

- **Incomplete 1 Gbit node·slots:** 176 on 32 hosts, mostly never received (107).
- **Chronic hosts:** 6 Prysm in São Paulo, Seoul, Sydney and Tokyo (17, 17, 15, 14, 13 and 12 of 18 slots) and 1 Teku
  in Sydney; two Lighthouse hosts in Sydney follow at 6–7 slots. Host 1960, which only starts failing at slot 16 in the
  cf run, is chronic from the start here.
- **Against cf,** the −10 penalty on every client prunes more peers from the start: 36–44k negative-score peers
  against 16–17k, and links per node fall from 226 to 193–215 against flat in cf. So 1 Gbit hosts do a little worse
  in slots 2–15 (98.78 vs 98.90 %), and the step at P3 activation is smaller (98.31 vs 97.74 % in slots 16–19).
- **Backlog:** none. Bytes after the deadline stay flat and only 9.1k stale background copies were ignored (cf: 9.5k
  PQ, 54k background). κ is flat at 8.1–8.7.
- **Memory and time:** peak 220.2 GiB PSS; wall 11,214 s.

### 1,024 hosts × 50 slots: `L-pq-ps100-fx-s1` (fx, every client −10, before the age fix)

- **Completion, slots 2–49:** 50/15 99.95 %, 50/25 99.99 %, 1 Gbit 98.15 % (~98.8 % in slots 2–16, ~97.8 % in
  17–49; worst slot 96.72 %). Strict rule: FAIL, 1 Gbit only.
- **Miss rates at 8 s:** PQ 0.018 / 0.0004 / 0.29 %; BLS in the same run 0.24 / 0.12 / 3.5 %.
- **Who misses:** 23 of 366 1 Gbit hosts, slot after slot: far-region and mostly Prysm.
- **Mesh:** flat, 187–208 links per node after slot 1.
- **Recirculation from slot 28** (blocks exactly 2.0× first deliveries in slots 40–41, PQ up to +25 %). It led to
  `--max-msg-age 60`.
- **Memory and time:** peak 131.3 GiB RSS (~124 GiB PSS); wall 15,445 s.

### Scaled peer targets (×0.25): `R6-pq-s1` (old binary, comparison only)

| class | completion |
|---|---|
| 50/15 | 99.75 % |
| 50/25 | 99.78 % |
| 1 Gbit | 96.32 % |

Meshes lose 40 % of their links in 6 slots (220 → 132 per node), and negative-score peers grow from 146 to 25k. The
×1.0 key cell is much closer to passing (98.65 % on 1 Gbit hosts) and keeps its meshes. The ×0.25 shortfall was mostly
an artifact of the scaled peer counts.

## Mechanisms

- **Failed sends.** rust-libp2p drops a forward still queued after 1 s and refuses one into a full queue.
  - Home hosts: the 1,024 aggregates per slot (495 B, below the IDONTWANT threshold) need 2–4 MB to D − 1 mesh peers
    within ~1 s, more than a 15 or 25 Mbit/s uplink can send. Lighthouse keeps these queue defaults, so a real client
    on that uplink drops them too.
  - Whole runs on the fx binary, by kind: forward timeout 53–63 %, forward queue-full 16–24 %,
    IHAVE/IWANT/IDONTWANT queue-full 13–28 %, own publishes 0 %.
- **Negative scores.** They come from the slow-peer penalty (rust-libp2p 0.49: −10 per failed send to that peer,
  decay 0.1 per 12 s, threshold 0, so a peer below 0 leaves every mesh for 60 s). The cf binary applies it only where
  the client has it. Extreme minima (−10⁸ … −10⁹) are P7 behaviour penalties from broken IWANT promises:
  rust-libp2p records a promise for every requested id, so one lost reply for N ids costs N.
- **Recirculation (fixed).** With a 60 s duplicate cache and no age check, a message held more than 60 s in a stalled
  connection was accepted as new and re-flooded everywhere (L from slot 28; R-nopq-ps100-s1 attestations +3–13 % in
  slots 12–19).
  - Fix: `--max-msg-age 60`; wbsim ignores flood messages received more than 60 s after publishing, as clients'
    first-seen rules do.
  - Validated: a 0.05 s cutoff drops exactly the messages older than the cutoff; 60 s drops none in a 3-slot run.
  - All runs from `R20-pq-ps100-age60-s1` on use it.
- **Publish-counter leak (latent).** rust-libp2p 0.49.5 drops stale own publishes without freeing their publish-queue
  slot. In L there are 9.5k own-publish refusals in total, sporadic, ~0.01 per connection per slot and not growing,
  so this is not patched.

## Client-faithful scoring

The per-client behaviour comes from the sources reviewed by the coordinator: Lighthouse v8.3.2 on the sigp
rust-libp2p fork, Grandine, Prysm v7.3.1 on go-libp2p-pubsub v0.18.0, Teku 26.10.3 on jvm-libp2p 1.3.8, Nimbus v26.10.2
on nim-libp2p v2.3.8, and Lodestar v1.50.1 on @libp2p/gossipsub 17.1.2.

| behaviour | Lighthouse, `other` (incl. Grandine) | Prysm | Teku | Lodestar | Nimbus |
|---|---|---|---|---|---|
| slow-peer penalty (cf, cf2) | −10 | 0 | 0 | 0 | 0 |
| P3/P3b weight (cf2) | −topic_weight | 0 | −max_positive / (topic_weight × threshold²) | same as Teku | same as Teku |
| scored IWANT promises (cf2) | every requested id | one random id per IWANT | one random id | one random id | none |
| re-request an id still awaited from another peer (cf2) | no, wait up to 3 s | yes | yes | yes | yes |

- **cf check (T64-cf vs T64-age60-stale, 64 hosts × 3 slots):** negative-score peers per observer fall to 0.00–0.03 in
  Prysm, Teku, Nimbus and Lodestar views and stay at 6–7 in Lighthouse and `other` views.
- **P3 parameters of the PQ topics**, Lighthouse's attestation-subnet formula with our own rate:
  - topic weight 1/16;
  - expected rate = mean PQ messages published per slot / 16: 125, 93.75 and 62.5 at 800k, 600k and 400k, and 66.9
    for b16 (1,071 messages per slot);
  - decay 0.9647 per slot, threshold (rate/50) · d/(1 − d) = 68.2 at 800k, cap 16 × threshold;
  - activation 17 slots, window 2 s.
- **Cost of a full deficit**, per PQ topic: −18.2 at 800k with Lighthouse's weight (−5.2 for b16). In Teku, Lodestar
  and Nimbus views it is −157.5 on every topic: the sim's max positive score, 50 × 3.15, counts the PQ subnets like
  the attestation subnets.
- **cf2 check (T64-cf2, 64 × 4, P3 activation shortened to 24 s):**
  - Prysm views: weight 0, no MessageDeficit penalties, no negative-score peers.
  - Teku, Lodestar and Nimbus views: −157.5 per full deficit on every topic.
  - Lighthouse and other views: −18.2 per PQ topic and −11.8 per attestation subnet.
  - Scored promises per IWANT: exactly 1.000 in Prysm, Teku and Lodestar views (4 / 3 / 0 broken), 0 in Nimbus views,
    15.6 and 10.1 in Lighthouse and other views.
- **Re-request rule (T64-cf2b, same flags):** an IWANT sometimes asks again for an id still awaited from another peer.
  - Lighthouse and other views: 0 such re-requests in 8,203 and 920 IWANTs; they wait for the earlier promise to end,
    at most 3 s.
  - Prysm, Teku, Lodestar and Nimbus views: 26,934, 13,319, 2,620 and 2,817 re-requested ids, 7–19 per IWANT.
  - Promise scoring is unchanged from T64-cf2.
  - This build is `bin/cf2`; every cf2 run uses it.

## Memory and time

- **Peaks.** R20 PQ runs peak at 190–230 GiB PSS (2.4 kB key cell 224.6, seed 2 216.7), the no-PQ R20 run at
  182 GiB, 2,048 × 6 cells at 129–160 GiB, and 1,024 × 50 runs at 124–125 GiB.
- **Watchdog.** The 235 GiB watchdog acts on summed PSS. PSS matches the drop in MemAvailable; summed RSS counts the
  shared binary pages of each process (6.9 MiB) again.
- **Lazy-queue patch** (`sim/gossipsub-0.49.5-lazy-queue.patch`): saves 0.55 MiB per connection (512 × 4 probe:
  83.7 → 39.1 GiB). It is what makes ×1.0 fit at 2,048 hosts.
- **Wall time.** 2,048 × 6: 42–56 min; 2,048 × 20: 3.25 h; 1,024 × 50: 4.3 h. All runs use 46 Shadow threads on CPUs
  48–95 at nice 19.

## Caveats

- The sim applies rust-libp2p's 1 s forward and 5 s publish queue timeouts to every client. None of the four non-Rust
  libraries expires queued messages.
- rust-libp2p 0.49.5's queues (2,500 publish + 2,500 other, with IDONTWANT among the others) differ from Lighthouse's
  fork (one 5,000-slot data queue and a separate 20,000-slot control queue). Up to 26 % of the failed sends that cost
  score are control-queue refusals, so 0.49.5 over-penalises even Rust hosts by up to that share.
- The duplicate cache is 60 s, against Lighthouse's 768 s. `--max-msg-age 60` covers the re-flood this would cause.
- Lighthouse's other gossipsub defaults match (D 5/3/10, out_min 2, gossip_lazy 3, heartbeat 1 s).
- `other` (Grandine, Erigon/Caplin, Hermes, unknown) is not split by client and is treated as rust-libp2p.
- Loss and TCP. With loss off, every miss of the 6-slot key cell disappears, so the 1 Gbit shortfall depends on the
  loss model and on how TCP recovers from loss on long paths. Shadow 3.3's TCP (v3.3.0, commit 5a05740) recovers
  losses with SACK and starts with a 10-segment window. Reno instead of CUBIC and no tail-loss probe or RACK make it
  slower than Linux; resetting cwnd to 10 instead of 1 after a timeout and no slow-start restart after idle make it
  faster.
  - **The current build's retransmission timeout ratchets up.** The RFC 6298 code exists, but no socket ever gets an
    RTT sample: tcp.c fills in the timestamp echo only when the interface sends a packet
    (`tcp_networkInterfaceIsAboutToSendPacket`), and by then the receive path has already cleared it (L2441), so every
    packet carries echo 0 and `_tcp_updateRTTEstimate` is never called (L2364). Every connection's RTO starts at 1 s
    (L2948) and doubles at each timeout (L1540). An ACK of new data resets the backoff count (L2016) but restores 1 s
    only after three timeouts in a row (L2011–L2014), so each isolated timeout doubles the RTO for good, up to 120 s.
    In a 64-host run with the realistic flags, the share of connections with an RTO of at least 2 s grows from 2 % at
    slot 0 to 31 % at slot 19 (≥ 16 s: 0 → 2.1 %), and 55 % of timeouts fire at 2 s or more. Linux uses about
    RTT + 200 ms. Tail losses therefore recover slowly, and more slowly as a run goes on, which may contribute to the
    late decline of 1 Gbit completeness (the slot-33 step of `L-pq-2k4-ps100-cf2-s1`).
  - **Socket buffers are Linux-like anyway.** Without RTT samples, Shadow's bandwidth × delay initial sizing never
    runs: sockets start at 131,072 B send and 174,760 B receive, and the autotuning caps stay at exactly 4 MiB and
    6 MiB, Linux's tcp_wmem[2] and tcp_rmem[2]. A build with Linux-default buffers (`shadow-3.3-lnxbuf.patch`) gave
    byte-identical wbsim output on 64 hosts.
  - **Two corrected builds**, checked on the same 64-host, 20-slot run (`runs/T64-rtt-*`):
    - `rtt` (`shadow-3.3-rtt.patch`) keeps the echo, samples on ACKs of new data and sets RTO = SRTT +
      max(4·RTTVAR, 200 ms). Every data-carrying connection gets samples, and the RTO no longer ratchets (≥ 2 s flat at
      4 %, connections in backoff). But timeouts rise 20× (5,942 → 119,250), because delay spikes at home hosts' links
      exceed SRTT + 200 ms, and resends on paths to or from home hosts rise 1.6–3.5× (per 1,000 data packets:
      1 Gbit→home 1.61 → 5.57, home→home 2.86 → 7.44). Paths between 1 Gbit hosts are unchanged (0.26 → 0.29).
    - `rtt2` (`shadow-3.3-rtt2.patch`) adds an Eifel undo of spurious timeouts (RFC 3522, Linux's tcp_try_undo_loss)
      and Linux's RTT estimator (tcp_rtt_estimator, __tcp_set_rto, v6.12). 94 % of the timeout episodes test spurious
      and are undone, with cwnd restored in every case and 41k queued resends dropped; nothing stalls, and the RTO
      equals SRTT + rttvar in every snapshot. Timeouts fall to 79,926, home latency p99 returns to the current
      build's (0.66 s), and home hosts' attestation misses mostly return (50/15: 0.000 / 0.87 / 0.047 % on current /
      rtt / rtt2). Resends on home paths fall only 3–28 % below rtt's (1 Gbit→home 3.99, home→home 7.20 per 1,000),
      because Shadow's RTO sets cwnd to 10, so a connection's outstanding segments are all resent before the ACK
      that triggers the undo. Linux sets cwnd to in_flight + 1 = 1 and resends one segment (tcp_enter_loss).
    - `rtt3` (`shadow-3.3-rtt3.patch`) adds that post-RTO window: cwnd = packets in flight + 1, counted after the
      timeout marks the outstanding data lost (1 at all 117,733 RTOs). Resends sent fall 31 % below rtt2's (per 1,000
      data packets: 1 Gbit→home 2.37, home→1 Gbit 1.73, home→home 4.91; 1 Gbit→1 Gbit 0.25), nothing stalls, and
      recoveries from a genuine loss with one RTO take as long as on rtt2 (p50 / p99 195 / 797 ms against
      209 / 770 ms). Recoveries that need a second RTO (24 % of genuine ones) take longer (p50 / p90 898 / 3,730 ms
      against 770 / 2,947 ms), because rtt3 restarts from one segment. Timeouts rise 47 % (79,926 → 117,733) because
      there are more timeout episodes; about 85 % of the extra ones start within 1 s after a spurious timeout was undone
      on the same connection, for reasons not established. wbsim outcomes are equal or better: 1 Gbit completeness
      99.75 % (98.74 % on the other three builds; 1 against 5 incomplete node·slots of 396), PQ miss 0.010 %, BLS
      attestation misses at home hosts 0.016 % (50/15) and 0.081 % (50/25).
    - `rtt4` (`shadow-3.3-rtt4.patch`) adds the RFC 7323 echo rule of Linux's tcp_replace_ts_recent. Shadow's
      receiver overwrote the value to echo with every packet it processed and wrote it into TSecr when a packet left
      its upload queue, so an ACK that waited there echoed the newest segment that arrived meanwhile. With the rule,
      99.87 % of ACKs of new data echo the first segment they newly acknowledge (70 % before); most of the rest
      (0.10 %) echo an earlier transmission of a segment that was later resent. The effect is small. At the
      slot-boundary snapshots, SRTT − configured RTT rises by 1–2 ms at the median and 12–16 ms at p99 on paths into
      home hosts (p50 / p99: 1 Gbit→home 8 / 110 ms, home→home 12 / 162 ms). At the first timeouts, RTO − SRTT is
      201 ms at the median on every path with either rule: rttvar sits at its 200 ms floor, so the delay that triggers
      a timeout is not in the estimator beforehand. Timeouts fall 5 % (117,733 → 112,057), 64 % of first timeouts
      still start within 1 s after a spurious timeout was undone (65 % on rtt3), and resends and wbsim outcomes do not
      change beyond noise (1 Gbit 99.49 %, 2 incomplete node·slots of 396 against 1). rtt4 also takes the TSval of
      duplicates that lie entirely below its last ACK, which Linux discards first (0.2–5.4 per 1,000 ACKs of new
      data); at most 0.03 % of ACKs of new data echo a newer segment than the first they acknowledge.
    - In all of them, first timeouts per data packet climb over a run (home→home per 1,000 from slot 2 to 18: 3.4 →
      5.8 on rtt2, 4.9 → 8.8 on rtt3, 4.4 → 8.6 on rtt4) while SRTT, the RTO margin (200 ms) and data per connection
      stay flat; the cause is not established. At 2,048 hosts on rtt4 (`R20-pq-2k4-rtt4-ps100-cf2-s1`) the climb is
      steeper (home→home 10.7 → 20.6), 96.6 % of timeout episodes are spurious and undone, and the same endpoints'
      windows shrink rather than grow (home→home cwnd p50 105 → 26 segments from slot 2 to 19).
    - First rtt4 result: the headline cell still passes, with more margin (worst slot 99.32 % against 99.05 %). Misses
      in slots 2–15 fall from 35 to 13 node·slots and the current build's chronic host 794 misses nothing, while slots
      16–19 are about the same (16 against 14). Its matched no-PQ run (`R20-nopq-rtt4-ps100-cf2-s1`) reproduces the
      current build's calibration (see the calibration table). The fs0 cell still fails on rtt4
      (`R20-pq-fs0-2k4-rtt4-ps100-cf2-s1`: worst slot 97.82 % against 96.6 %, about half the PQ misses).
      `L-pq-2k4` runs on rtt6 instead (see [Pending](#pending)). rtt4 is the final TCP build for this study.
    - `rtt5` (`shadow-3.3-rtt5.patch`) is a sensitivity build, not the main line: rtt4 plus the growth rule of Linux's
      congestion-window validation (the window grows on an ACK only while `tcp_is_cwnd_limited` holds; in slow start, up to twice the
      largest recent flight) and restart after idle (`tcp_cwnd_restart`: when new data leaves with nothing in flight
      more than one RTO after the last data segment, cwnd halves once per RTO of idle time, down to min(10, cwnd)), each
      behind its own switch. With both switches off it reproduces rtt4 byte for byte (wbsim output of all 64 hosts).
      On the 64-host check with both on, connections restart several times per slot (median idle time at a restart
      0.8–1.0 s, against an RTO of about 0.3 s), and windows stay near the initial 10 segments: cwnd p50 / p90 over the
      run is 10 / 52 on 1G→1G, 10 / 23 on 1G→home, 10 / 25 on home→1G and 10 / 19 on home→home, against rtt4's
      161 / 16,967, 52 / 484, 51 / 454 and 33 / 262. Smaller bursts overflow home downlinks less often: first timeouts
      per 1,000 data packets fall from 6.90 to 4.73 on home→home and from 1.80 to 1.16 on 1G→home, home→home resends
      from 5.08 to 3.92 per 1,000, and all timeouts by a third (112,057 → 74,764). But a burst of more than 10 segments
      now takes extra round trips: block p99 from publish rises from 0.46 to 1.03 s, PQ p99 by 45–74 % (1 Gbit 1.36 →
      1.97 s), and 1 Gbit hosts miss more (15 against 2 incomplete node·slots of 396 in slots 2–19, all on two hosts:
      40 in São Paulo and 43 in the US west). Nothing stalls, and the RTO formula holds in every snapshot. Because
      both latencies move by more than 10 %, the headline cell and its no-PQ run are repeated on rtt5
      (`R20-pq-2k4-rtt5-ps100-cf2-s1`, `R20-nopq-rtt5-ps100-cf2-s1`), after two more checks. First, after a
      restart that leaves cwnd below ssthresh, Reno runs in slow start, as Linux's `tcp_in_slow_start` implies: 86 % of
      restarts leave cwnd below ssthresh, and all of those switch to slow start except the 0.02 % that happen during
      fast recovery. Second, a third switch (`RTT5_DUP`) makes an ACK that advances snd_una end Reno's count of
      duplicate ACKs in congestion avoidance, as RFC 5681 counts them (see the duplicate-ACK gap below). The links
      never reorder packets (the jitter patch keeps each source–destination pair FIFO), so every duplicate ACK follows
      a loss. Without the switch, 42–56 % of fast-recovery entries have an ACK that advanced snd_una between their
      duplicates; with it, none do, yet the entries per 1,000 data packets fall by only 1–3 % (home→home 2.52 → 2.45,
      1G→home 1.45 → 1.44), so most of those holes still enter fast recovery. Possibly the first duplicate ACK also
      acknowledged the segment before the hole (a delayed ACK merged into it); this was not traced. ssthresh at
      restarts (p50 over all paths 120 → 124 in slot 2, 22 → 22 in slot 18) and the wbsim outcomes (block p99 from
      publish 1.05 s, PQ p99 0.94 / 1.16 / 2.08 s, 16 incomplete 1 Gbit node·slots) do not change beyond noise. The
      repeated runs use rtt5 with all three switches on. At 2,048 × 20 the headline cell fails on rtt5
      (`R20-pq-2k4-rtt5-ps100-cf2-s1`, see its section): 1 Gbit 98.80 % in slots 2–15 and 98.65 % in 16–19, worst
      slot 97.97 %, with windows near 10 segments (cwnd p90 16–35) and block p95 from publish 1.7–2.2× rtt4's. Its
      no-PQ run (`R20-nopq-rtt5-ps100-cf2-s1`) keeps attestation and column timing, but blocks from publish take
      0.90 / 1.09 s at p95 / p99 (rtt4 0.38 / 0.47 s; mainnet's relay-timed P95 0.82 s; see Calibration). With
      16 signatures per message the cell fails on rtt5 too (`R20-pq-b16-2k4-rtt5-ps100-cf2-s1`: worst slot 98.38 %,
      6 of 18 slots below 99 %), so the 50-slot run on rtt5 was not queued. A fourth switch, `RTT5_BETA` (off by default), replaces Reno's halving at fast-recovery
      entry and at an RTO with CUBIC's decrease, ssthresh = max(cwnd × 717 / 1024, 2) (`bictcp_recalc_ssthresh`;
      `shadow-3.3-rtt5b.patch`). On the 64-host check, with the switch unset the build reproduces rtt5 byte for byte;
      with it set, every fast-recovery entry (47,961) and every RTO (101,643) sets ssthresh by that rule, nothing
      stalls, and the RTO formula holds. Block p99 from publish falls from 1.05 to 0.91 s (−13 %) and 1 Gbit PQ p99
      from 2.08 to 1.79 s (−14 %; home hosts 0.94 → 0.91 and 1.16 → 1.10 s). The unbundled cell fails on rtt5 by far
      more than that, so the switch is tried on the bundled cell, which passes with it
      (`R20-pq-b16-2k4-rtt5b-ps100-cf2-s1`: worst slot 99.33 % against 98.38 % without it, 41 incomplete 1 Gbit
      node·slots against 112, block p95 from publish 6–11 % lower, 11 % more RTOs). Two
      more 64-host runs split rtt5's two Linux rules: window validation
      only (`RTT5_SSR=0`, as Linux with `net.ipv4.tcp_slow_start_after_idle=0`) and restart after idle only
      (`RTT5_CWV=0`), both with `RTT5_DUP=1`. Window validation alone reproduces rtt4: block from publish p50 / p95 /
      p99 0.17 / 0.37 / 0.47 s (rtt4 0.16 / 0.37 / 0.46), 1 Gbit PQ p99 1.31 s (1.36), 4 incomplete 1 Gbit node·slots
      (2). Only home PQ p99 rises, by 11–14 % (0.69 / 0.79 s against 0.62 / 0.69), and the 1G→1G cwnd p90 falls from
      16,967 to 254 segments. Restart after idle alone reproduces rtt5: block from publish 0.33 / 0.87 / 1.03 s (rtt5
      0.37 / 0.86 / 1.05), 1 Gbit PQ p99 1.96 s (2.08), 16 incomplete 1 Gbit node·slots (16). Neither run stalls, and
      the RTO formula holds in every snapshot without backoff. So rtt5's slowdown comes entirely from the restart
      after idle, which `net.ipv4.tcp_slow_start_after_idle=0` turns off. rtt4's column has no `RTT5_DUP`, which alone
      changed nothing beyond noise on this check (rtt5 with and without it). The headline cell is repeated at 2,048 hosts
      with window validation only (`R20-pq-2k4-cwv-ps100-cf2-s1`), because rtt4 only approximates that configuration
      (here rtt4's 1G→1G cwnd p90 was 16,967 segments against 254). It passes with no host to spare (worst slot
      99.05 %, 7 of ~740 hosts), with windows 2–4× smaller than rtt4's at p50.
    - `rtt6` (`shadow-3.3-rtt6.patch`) is a further sensitivity build: rtt5 with all three switches on, plus Linux's
      CUBIC (`net/ipv4/tcp_cubic.c`, v6.12) in place of Reno's window growth and decrease, and HyStart, each behind
      its own switch (`RTT6_CUBIC`, `RTT6_HYSTART`, both on by default). Shadow 3.3.0 has only Reno. The port covers
      `bictcp_update` with TCP friendliness and the cnt ≥ 2 cap, `cubictcp_recalc_ssthresh` (β = 717/1024, fast
      convergence), the epoch shift when data goes out with nothing in flight (`CA_EVENT_TX_START`), the reset on
      entering Loss (which the Eifel undo does not reverse) and delay_min from the RTT samples, keeping rtt5's
      window-validation gate; slow start, fast recovery and the RTO handling stay Reno's. On the 64-host check, with
      both switches off it reproduces rtt5 byte for byte. With them on, ssthresh = max(cwnd × 717 / 1024, 2) at all
      47,310 fast-recovery entries and 113,054 RTOs; the window target stays within one segment of
      W_max + 0.4 (t − K)³ (integer truncation) in all 5,420 logged recomputations, and K matches the formula within
      0.14 % over 43,977 epochs. In none of 603,069 congestion-avoidance round trips does the window grow by more
      than one segment per two packets ACKed, plus one (the cnt ≥ 2 cap). Measured against the window at the start of
      the round, 261 rounds (0.04 %) grow by more than 1.5× plus one segment, because more packets were ACKed in
      them than that window held: they start from a window of a few segments while more data is in flight, as after
      an RTO (not traced one by one). Sending resumed with nothing in flight 1.41 million times; the epoch shifted in
      the 1.03 million of those with an epoch running and some idle time (41 % of the events on home→home, 91 % on
      1G→1G), and each of the 2,137 traced shifts equals min(epoch + idle time, now). Nothing stalls and the RTO
      formula holds in every snapshot without backoff. HyStart's tests fire 617 times in 20 slots: the ack-train
      test on short paths (211 times on 1G→1G, never on home→home), the delay test only on paths with a home end
      (308 times). The delay test fires at cwnd 51 / 121 segments at p10 / p50, about a home link's
      bandwidth-delay product at the median base RTT of 34 ms (some 45–150 segments from a 15 Mbit/s uplink to a
      50 Mbit/s downlink), only 7 times below 32 segments, and 1.4 ms above its threshold at p50. So the delay exits
      look like queueing at home links; the model's jitter (exponential, 0.5–2.5 ms mean per home access link, first
      in first out) may trip some; the two were not separated. With CUBIC and HyStart, 80 % of data packets leave
      with cwnd ≥ ssthresh (rtt5 62 %; 1G→1G 81 % against 44 %, and 46 % without HyStart, whose exits set ssthresh),
      so the congestion-avoidance rule governs most traffic.
      Against rtt5, block p99 from publish falls from 1.05 to 0.90 s (−14 %), PQ p99 by 16 / 17 / 37 % (50/15,
      50/25, 1 Gbit: 0.79 / 0.96 / 1.32 s) and incomplete 1 Gbit node·slots from 16 to 1. The 1 Gbit class is back
      at the level of rtt4 and of window validation only (PQ p99 1.36 and 1.31 s, 2 and 4 node·slots). Home PQ p99
      lands about halfway between rtt5 and rtt4 (0.79 / 0.96 s against 0.94 / 1.16 and 0.62 / 0.69 s), and blocks
      stay close to rtt5 (block p95 from publish 0.80 s; rtt5 0.86, rtt4 0.37 s). CUBIC's decrease alone (rtt5
      with `RTT5_BETA`) gives the same block figures (0.91 s at p99), so CUBIC's growth helps the PQ burst (PQ p99 a
      further 13 / 13 / 26 % lower, incomplete node·slots 12 → 1) but not blocks. Timeouts return to rtt4's level
      (113,054 RTOs against rtt5's 72,886; home→home first timeouts 7.42 per 1,000 data packets against 4.95).
      Without HyStart the outcomes barely change (block p99 from publish 0.96 s, PQ p99 0.78 / 0.97 / 1.39 s). Block
      p99 from publish and PQ p99 both move by more than 10 %, so the bundled and the unbundled headline cells run on rtt6
      (`R20-pq-b16-2k4-rtt6-ps100-cf2-s1`, then `R20-pq-2k4-rtt6-ps100-cf2-s1`), and the bundled 50-slot run follows
      only if the bundled one passes the strict rule. The bundled cell passes with margin (worst slot 99.73 %; 11
      incomplete 1 Gbit node·slots against 41 on rtt5b) with blocks as on rtt5b (p95 from publish 0.65 against
      0.67 s): at 2,048 hosts too, CUBIC's growth helps the PQ burst but not blocks. The unbundled cell passes with
      one host to spare (worst slot 99.19 %; 40 incomplete 1 Gbit node·slots against 164 on rtt5 and 48 on cwv), with
      blocks within 9 % of rtt5's (p95 from publish 0.69 against 0.73 s). The 50-slot runs of both cells use rtt6, so
      no run falls back to cwv6, the rtt6
      binary without the restart after idle (`RTT5_SSR=0`, as Linux with `net.ipv4.tcp_slow_start_after_idle=0`); it
      replaced cwv, which keeps Reno. On the 64-host check cwv6 makes no restart, applies the 0.7 rule at every
      fast-recovery entry (48,049) and RTO (127,367), keeps CUBIC's targets within 1 segment of the curve in all 5,910
      recomputations, never grows a round by more than one segment per 2 packets ACKed + 1, shifts the epoch as Linux
      in all 1,417 traced cases, never stalls, and the RTO formula holds. It matches or beats cwv and rtt4: block from
      publish p50 / p95 / p99 0.15 / 0.34 / 0.45 s (cwv 0.17 / 0.37 / 0.47, rtt4 0.16 / 0.37 / 0.46), PQ p99 0.61 /
      0.69 / 1.05 s (cwv 0.69 / 0.79 / 1.31), 1 incomplete 1 Gbit node·slot (cwv 4), with more timeouts (127,367 RTOs
      against 96,328) and a longer attestation tail (p99 6.07 against 3.56 s, missing 1.15 against 3.00 %).
  - **Remaining gaps against Linux (rtt4):** no tail-loss probe and no RACK (losses at the end of a burst wait for the
    RTO); Reno instead of CUBIC (rtt6 tests CUBIC, above); no slow-start restart after idle and no congestion-window validation (rtt5 adds both,
    above): Shadow calls its
    congestion hook (`tcp_cong_new_ack_ev`) on every ACK of new data, while Linux's Reno and CUBIC grow the window only
    while it limits sending (`tcp_is_cwnd_limited`; in slow start up to twice the largest recent flight), so lightly
    loaded connections reach windows Linux never would (on the 64-host rtt4 check, the 90th percentile on 1G→1G
    connections is 20,700 segments, about 30 MB, at slot 10, far more than any connection can have in flight under the
    4 MiB send and 6 MiB receive buffers). rtt5 adds the growth rule and the restart after idle, but not Linux's decay
    of a window the sender stops filling. In Linux (v6.12, net/ipv4/tcp_output.c), `tcp_cwnd_validate` (L1913–L1947)
    calls `tcp_cwnd_application_limited` (L1895–L1911) under the same sysctl as the restart,
    `net.ipv4.tcp_slow_start_after_idle`: when a sender in the Open state, not held back by its send buffer, has gone
    one RTO without filling its window, ssthresh becomes max(ssthresh, ¾ cwnd) (`tcp_current_ssthresh`,
    include/net/tcp.h L1343–L1353) and cwnd the mean of cwnd and the largest flight used in that time (at least the
    initial window), and this repeats every RTO. rtt5's window
    validation only stops growth (`tcp_rtt5MayRaiseCwnd`) and keeps Linux's `is_cwnd_limited` and `max_packets_out`
    bookkeeping; it has no `snd_cwnd_used` and no reduction. So a connection that keeps some data in flight, and
    therefore never idles for an RTO and never restarts, keeps a window it no longer uses. With idle gaps longer than
    the RTO the restart covers most connections (on rtt5 the median idle time at a restart is 0.9–1.0 s against an
    RTO of about 0.3 s), so this gap leaves rtt5 somewhat faster than Linux only on connections with steady light
    traffic; it is not modelled or tested. It does not affect the window-validation-only run (`RTT5_SSR=0`), because
    Linux with that sysctl at 0 skips the decay as well. The send window is counted in sequence space from
    the first unacknowledged segment, so SACKed segments use window that Linux would give to new or lost ones; and
    Shadow halves ssthresh again at a repeated RTO (cwnd/2 + 1, so 1 after rtt3's cwnd of 1), where Linux keeps it
    within the loss episode. A 64-host check with Linux's ssthresh rule gave the same recovery times and resends and
    no consistent change in wbsim outcomes, so that gap is small. Shadow's Reno also keeps counting duplicate ACKs
    across new ACKs in congestion avoidance (`ca_reno_cong_avoid_new_ack_ev_` in tcp_cong_reno.c never resets the
    count; only slow start, the end of fast recovery and a timeout do), so three duplicate ACKs from separate holes,
    spread over time, start fast recovery and cut the window. RFC 5681 counts only duplicates with no ACK in between
    that advances SND.UNA, and Linux decides from the current SACK scoreboard and RACK. The resend itself does not
    depend on this count: the retransmit tally marks a hole lost only after three duplicate ACKs for the same ACK
    number (tcp_retransmit_tally.cc L199–218), so a fast-recovery entry on an accumulated count cuts the window without
    starting a repair. rtt5's `RTT5_DUP` switch closes the gap; on the 64-host check it removes only 1–3 % of
    fast-recovery entries and changes no outcome beyond noise (see rtt5 above). Also, in Shadow's default FIFO qdisc a
    packet
    without a sequence number (a pure ACK) gets priority 0 (tcp.c L919–925 in 3.3.0), and the interface always sends
    from the socket whose next packet has the lowest priority (interface.rs L94–99). So pure ACKs never wait behind a
    host's upload backlog, where a home router with a FIFO uplink would hold them. That likely explains why the echo
    rule changes little.
  - The matched no-PQ pair
  `R6-nopq-ps100-cf-s1` / `R6-nopq-noloss-ps100-cf-s1` matches mainnet's attestation p50 / p95 and column timing
  equally; the lossy model is closer on duplicates and home rx. The far tail that loss creates (attestation p99,
  missing deliveries) has no mainnet reference.
- cf2 keeps rust-libp2p's habit of also sending IDONTWANT to the peers it sent an IWANT to for that message (go
  sends IDONTWANT to mesh peers only).
- P3 activation. Mesh-delivery scoring (P3) on PQ and attestation topics activates 17 slots after graft (around
  slot 15), so every 6-slot cell ends before it. Block and aggregate P3 activate one epoch after graft (Lighthouse's
  windows, used on every host), around slot 30 here. Every 20-slot run ends before that; only the 50-slot runs reach it
  (from slot ~30). On mainnet most mesh links are older than an epoch, so that is the steady state. A 20-slot run with
  block and aggregate activation shortened to 17 slots (`R20-pq-2k4-act17-ps100-cf2-s1`) was dropped: in the 50-slot
  run block and aggregate P3 rarely penalised anyone, and the current Shadow build's RTO ratchet (see Loss and TCP) is
  the larger time effect.
- Churn at publish time. A message counts as lost to churn only if its publisher was offline at publish time
  (perturb.py drops it from the schedule) or had no connections at all (none in any run). A publish that gossipsub
  refuses while the publisher has connections counts against the network: one case in the 23 finished PQ runs (v400 slot 19,
  a host that had joined 0.2 s before), and it decides that run's verdict. The connection count is logged only every
  0.5 s, so the zero-connection test rests on the dial timing and the latency model. See
  [Churn and refused publishes](#churn-and-refused-publishes-all-pq-runs).

## Pending

| run | what | status |
|---|---|---|
| R20-nopq-rtt6-ps100-cf2-s1 | no PQ on rtt6: the calibration column for rtt6 and the matched BLS baseline of the rtt6 runs | running since 11:20 Nov 12, the last run of the queue; expected to end ~13:50 |

Build rule for the runs after the rtt6 cells: each runs on rtt6 if the rtt6 cell with the same bundling passes the
strict rule, and on cwv6 otherwise: the rtt6 binary without the restart after idle (`RTT5_SSR=0`), as Linux with
`net.ipv4.tcp_slow_start_after_idle=0`. The fs0-b16 run and seed 2 of `L-pq-b16` follow
`R20-pq-b16-2k4-rtt6-ps100-cf2-s1`; `L-pq-2k4` and its seed 2 follow `R20-pq-2k4-rtt6-ps100-cf2-s1`. So the verdict
rests on stock Linux (rtt6) wherever it passes, and on that sysctl only where stock Linux fails. The fs0-b16 run went
first because its build was known first. cwv6 replaced cwv, the rtt5 binary with the same switches, which keeps Reno
where Linux with the sysctl keeps CUBIC; it passed its 64-host check first (see Loss and TCP in [Caveats](#caveats)).
The bundled rtt6 cell passed (decided 08:40 Nov 11), so fs0-b16 and seed 2 of `L-pq-b16` run on rtt6, and
`L-pq-b16-2k4-rtt6-ps100-cf2-s1` and `R20-nopq-rtt6-ps100-cf2-s1` were queued. The unbundled cell passed too (decided
12:03 Nov 11), so both seeds of `L-pq-2k4` were queued on rtt6, and no run uses the fallback. On Nov 12 Yann adopted
bundling, so no more unbundled runs: `L-pq-2k4-rtt6-ps100-cf2-s1` was stopped at sim 368 s (slots 0–27; partial output
kept, not analysed) and its seed 2 dropped. The two subnet cells run ahead of seed 2 of `L-pq-b16` and the no-PQ run.

Dropped: `R20-pq-2k4-lnxbuf-ps100-cf2-s1` (Shadow's socket buffers are already Linux-like here, and a 64-host check gave
byte-identical output), `R20-pq-2k4-act17-ps100-cf2-s1` (see P3 activation in [Caveats](#caveats)), the rtt, rtt2
and rtt3 runs (replaced by the rtt4 set), the current-build seed-2 L runs (run on rtt4 instead),
`L-pq-b16-2k4-rtt5-ps100-cf2-s1` (conditional on `R20-pq-b16-2k4-rtt5-ps100-cf2-s1` passing the strict rule, which it
fails), `R20-pq-2k4-rtt5b-ps100-cf2-s1` (replaced by the bundled `R20-pq-b16-2k4-rtt5b-ps100-cf2-s1`), and both seeds
of `L-pq-2k4-rtt6` (bundling adopted on Nov 12; seed 1 stopped at sim 368 s, partial output in
`runs/stopped-L-pq-2k4-rtt6-ps100-cf2-s1-dropped`).

All runs: 2,048 hosts, ×1.0, seed 1, 20 slots unless noted. The 3 kB b16, v600 and v400 runs on cf2 were dropped
when 2.4 kB became the headline; `R20-pq-b16-ps100-cf2-s1` was stopped at sim 157 s (slots 0–9) and is excluded.
The 1.2 kB run on cf2 was dropped once 2.4 kB passed.

## Commands and files

```sh
# one run: NAME HOSTS SLOTS THREADS, then gen_config/perturb flags
bash runs/run_lever.sh R20-pq-ps100-cf-s1 2048 20 46 $REAL --peer-scale 1.0 --seed 1 --max-msg-age 60 \
  --client-slow-peer --binary bin/cf/wbsim
# REAL (runs/night.sh):
REAL="--sig-subnets 16 --one-subnet --peer-target 50 --warmup 30 --bg --net cities --access --jitter --loss --verify \
  --slow-cpu-share 0.2 --scoring --client-mix --client-gs --peer-scale 0.25 --nat-share 0.3 --churn-conn-life 1800 \
  --churn-restart-per-day 0.143 --churn-leave 0.005 --churn-join 0.005"
# base flags in runs/run_lever.sh: --mode flood --drain 8 --no-cpu-pinning --validators-csv data/f9ba162f-nodes.csv
#   --msgs 2000 --fast-above 8 --fast-share 0.2 --links 50/25 --links-novalidator 50/15
# queue: runs/night.sh reads runs/queue-night.txt (NAME HOSTS SLOTS flags); watchdog: runs/watchdog256.sh 235 30
# analysis (python3 -I .amp-out/<script>.py RUN): pqsum, pqdiag [--slots A B], failsplit, cfcheck, cf2check,
#   bgexcess, stale, calib, attmiss, p3split, farhosts, late (late first deliveries, stale and late copies per slot
#   and class), stalehosts RUN [STEP] (stale copies per slot and host against misses), upwin PQRUN NOPQRUN (upload per class in 4-8 s, 4-5 s and the slot, with and without PQ); TCP (runs with tcpd lines): tcppath, tcpdiag RUN LABEL,
#   rtt3diag (post-RTO cwnd, recoveries), rtt4diag (SRTT vs configured RTT, echo shares, timeouts after an undo),
#   betacheck RUN --beta 0|1 (ssthresh after each fast-recovery entry and RTO), rtt6diag RUN [CONFIG] (CUBIC and
#   HyStart checks); t64table.py NAME... (the 64-host comparison table)
# subnet cells (gen_config): --staker-subnets N (each home staker joins its home (duty) subnet + N-1 random ones) and
#   --backbone-subnets N (every home node joins N random backbone subnets, stakers also their duty subnet, which alone
#   they need: node field need); realism_check, pqdiag, late and failsplit honour need, PQ_NEED=all needs every
#   subscribed subnet; cellcmp RUN [RUN[:all] ...] (side-by-side summary of the analysis outputs)
# Shadow build per run: runs/shadowbin-NAME names a bin directory (default shadow-install/bin). The -log wrappers
#   (shadow-install-rtt-log, -rtt2-log, -rtt3-log, -rtt4-log, -rtt5-log, -rtt6-log) set LNXBUF_LOG=1;
#   shadow-install-rtt5-cwv-log also sets RTT5_CWV=1 RTT5_SSR=0 RTT5_DUP=1 (window validation only) and
#   shadow-install-rtt5b-beta-log RTT5_BETA=1; shadow-install-rtt6-cwv6-log runs the rtt6 binary with RTT5_SSR=0 (cwv6,
#   the fallback build). run_lever.sh moves the tcpd lines to runs/NAME/shadow-tcpd.log.gz.
```

- **Changed files:**
  - `sim/wbsim/src/main.rs`: `--max-msg-age`, per-node slow-peer weight, P3 mode and IWANT-promise mode, a
    `score_cfg` event, new counters.
  - `sim/wbsim/gossipsub/`: libp2p-gossipsub 0.49.5 with `sim/gossipsub-0.49.5-lazy-queue.patch` and
    `sim/gossipsub-0.49.5-sim-scoring.patch`, the sim's scoring changes, applied in that order.
  - `sim/perturb.py`: `--max-msg-age`, `--client-slow-peer`, `--client-p3-promises`, `--score-mesh-activation`, and
    the batched P3 rate.
  - `sim/README.md`.
  - `sim/gen_config.py`: `--staker-subnets` and `--backbone-subnets` (the subnet cells), drawn from their own random
    generator, so everything else matches the one-subnet cell. `sim/realism_check.py`: honours a node's `need` field
    (`PQ_NEED=all` ignores it) and `REALISM_OUT`.
  - `sim/shadow-3.3-lnxbuf.patch` (Linux-default socket buffers), `sim/shadow-3.3-rtt.patch` (lnxbuf + working
    timestamp echo + RTO = SRTT + max(4·RTTVAR, 200 ms) + `tcpd` diagnostics), `sim/shadow-3.3-rtt2.patch` (rtt +
    Eifel undo + Linux's RTT estimator), `sim/shadow-3.3-rtt3.patch` (rtt2 + Linux's post-RTO window) and
    `sim/shadow-3.3-rtt4.patch` (rtt3 + Linux's timestamp echo rule): Shadow 3.3.0 TCP variants, each applied after
    `sim/shadow-3.3-fixes.patch`. Sensitivity variants of the same kind, each complete on its own:
    `sim/shadow-3.3-rtt5.patch` (rtt4 + window validation, restart after idle and the consecutive duplicate-ACK
    rule; `RTT5_CWV`, `RTT5_SSR`, `RTT5_DUP`), `sim/shadow-3.3-rtt5b.patch` (rtt5 + CUBIC's decrease, `RTT5_BETA`)
    and `sim/shadow-3.3-rtt6.patch` (rtt5b + Linux's CUBIC with HyStart; `RTT6_CUBIC`, `RTT6_HYSTART`).
- **Machine:** AMD EPYC 9454P (48 cores, 96 threads), 503 GiB RAM. Runs are limited to CPUs 48–95 at nice 19 and
  ≤ 256 GB.
