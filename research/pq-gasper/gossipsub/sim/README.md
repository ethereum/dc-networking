# Shadow simulation: the subnets one node joins

Simulates what one mainnet node sees of the example system (800k validators):
the **2 gossip subnets** it joins, each with **~312 members**
(10,000 nodes × 2 / 64). Every host runs [`wbsim`](wbsim/src/main.rs), a
rust-libp2p node (TCP + noise + yamux), in one of two modes. Both modes use
the same hosts, regions and links for a given seed.

| mode | votes | proofs |
|---|---|---|
| `gossip` | every host joins both subnet topics; Ethereum parameters (D=8, D_lo=6, D_hi=12, heartbeat 0.7 s, IDONTWANT for >1,000 B, flood publish off, content-hash message IDs, rust-libp2p's default send-queue timeouts) | 16 aggregators per subnet aggregate it and gossip their 220 KiB proof on an aggregate topic every host joins |
| `direct` | each subnet's votes are split into direct topics with 16 recipients each; a vote goes by request/response to its topic's 16 recipients over pre-opened connections (`--cold-connect`: dialled at vote time) | recipients announce to the proposer, which pulls the largest + one random proof per topic |

`--proofs flood|pull|decoy` overrides the proof delivery in either mode;
`decoy` pushes every proof to `--decoys` nodes that include the proposer.

Scenarios (`gen_config.py` flags):

| scenario | flags | votes per subnet | direct topics | hosts |
|---|---|---|---|---|
| 32-slot round (default) | – | 391 | 2 × 16 recipients | 32 aggregators + proposer + 279 voters |
| 8-slot DC round | `--votes 1560 --topics-per-subnet 4` | 1,560 | 8 × 16 recipients | 128 aggregators + proposer + 183 voters |
| one subnet (control) | `--subnets 1` | 391 | 1 × 16 | 16 + 1 + 295 |

At the 8-slot cadence there are still 64 gossip subnets (1,560 votes each) but
256 direct topics of 390 votes, so one subnet's votes map to 4 direct topics.
The proposer then pulls best + random from 8 topics, which is exactly an
internal aggregator with 8 children. In gossip mode the extra 96 recipient
hosts are plain subnet members (`member-*` in the tables).

Workload per slot: votes at 4.0–4.5 s (3,272 B each, leanSig size),
aggregator cut-off at 8 s, then 1.45 s of simulated proving (391 sigs at
270 sigs/s), then 220 KiB proofs. Five slots after a 20 s warm-up.

Network: five regions with mainnet-like shares and one-way latencies of
10–140 ms. Links follow [EIP-7870](https://eips.ethereum.org/EIPS/eip-7870)
(`--profile`):

| profile | voters | aggregators | proposer |
|---|---|---|---|
| `eip7870-mix` (default) | 80 % attester (50/25 Mbit/s), 20 % 1 Gbit | 12 of 16 per topic 1 Gbit, 4 attester | local block builder (100/50) |
| `eip7870-min` | as above, attesters at 50/15 (EIP-7870 "minimum tested" upload) | as above | as above |
| `legacy` | 50 % 50/25, 50 % 1 Gbit | all 1 Gbit | 50/25 |

Proving is modelled as a delay, not executed.

## Flood mode: N messages per slot on one topic

`--mode flood` asks a different question: can gossipsub deliver N distinct
messages per slot to every node? Every host joins one topic with the same
Ethereum gossipsub parameters. In each slot, `--msgs` messages of
`--msg-bytes` (default 2,000 × 3,072 B, XMSS size) are published by uniformly
random hosts at 4 s + U[0, `--publish-window`) into the slot. The deadline is
4 s after publishing starts. `--links DOWN/UP` (Mbit/s) sets the link of most
hosts and `--fast-share` the share on 1 Gbit. `--drain` keeps the run going
after the last slot, so leftover backlog shows up. `--pcap K` captures packet
headers on K slow hosts and 1 fast host for
[`pcap_rate.py`](pcap_rate.py), which checks on-wire rates against the caps.

`--validators-csv FILE` samples hosts from a mainnet peer crawl (a `validator_count` column) and draws each
message's publisher in proportion to validators per host. `--fast-above K` puts hosts with more than K validators on
1 Gbit; of the rest, `--fast-share` get 1 Gbit, validator hosts get `--links` and the others `--links-novalidator`.
`--no-cpu-pinning` is needed to run Shadow next to other Shadow instances.

Each node logs the first receipt time of every message, plus byte and
gossipsub counters every `--bin` seconds: duplicates, IDONTWANT, IWANT,
dropped and timed-out forwards. `analyze.py` detects flood runs and reports
coverage at the deadline per slot, latency percentiles, κ, drops, and link use
per class. Results: [superseded/gossip-2000.md](../superseded/gossip-2000.md).

```sh
python3 sim/gen_config.py --mode flood --hosts 512 --slots 15 --msgs 2000 --links 25/10 --fast-share 0.1 --out runs/f
(cd runs/f && shadow shadow.yaml > shadow.log)
python3 sim/analyze.py runs/f
```

## Shadow needs two patches

[`shadow-3.3-fixes.patch`](shadow-3.3-fixes.patch) fixes two Shadow 3.3.0
bugs; results without it are wrong.

1. **Host upload limits are ignored.** `src/main/core/sim_config.rs` fills
   `bandwidth_up_bits` from `bandwidth_down`, so every host uploads at its
   download rate. EIP-7870 attesters then upload at 50 instead of 25 Mbit/s.
   A two-host check (client 50 down / 15 up sending 6.7 MB) took 1.1 s before
   the fix and 3.7 s after. Shadow main already has this fix.
2. **A 65,535-byte cap per `send()`.** Shadow's legacy TCP accepts at most
   65,535 bytes per call even when the socket buffer has room. Tokio treats a
   short write as "buffer full" and waits for an EPOLLOUT edge that never
   comes, because the buffer never filled, so the connection's writer stalls
   for good. In wbsim this showed as proposer pulls of the 220 KiB proof
   timing out after 20 s, and the same aggregators' announcements vanishing
   in later slots. It hit fast links only, where the send buffer exceeds
   64 KiB. The pcap showed the aggregator stopping mid-response with no
   window or ACK problem; its syscall trace showed `sendto(…, 94692) = 65535`
   and no further write on that socket.

## wbsim patches libp2p-gossipsub's forward queue

In libp2p-gossipsub 0.49.5 each peer's send queue for forwards and IHAVE/IWANT
is `async_channel::bounded(queue_len / 2)`, which allocates and touches all
2,500 slots (about 230 B each) when the peer connects: 0.55 MiB per peer,
whether or not anything is queued. At Lighthouse's 200 peers that is 110 MB per
node. [`gossipsub-0.49.5-lazy-queue.patch`](gossipsub-0.49.5-lazy-queue.patch)
makes the channel unbounded and enforces the same 2,500 cap in `send_message`.
Messages are queued and dropped exactly as before: with
`model_unblocked_syscall_latency: false`, a 64-host run gives byte-identical
event logs with either build. With it on (the default here), event times shift
by microseconds and runs differ the way two seeds do.

[`gossipsub-0.49.5-sim-scoring.patch`](gossipsub-0.49.5-sim-scoring.patch), applied after it, adds the per-client
scoring options behind `--client-p3-promises` (an IWANT-promise mode in the gossipsub config: which requested ids get
a scored promise, and whether an id still awaited from another peer is requested again) and counters for IWANTs,
promises, re-requests and MessageDeficit penalties per topic. With the default mode (0, rust-libp2p) gossipsub
behaves as before.

## Run

```sh
# once: Shadow 3.3 from source, patched, and Rust
#   apt deps: https://shadow.github.io/docs/guide/install_dependencies.html
git clone --depth 1 --branch v3.3.0 https://github.com/shadow/shadow.git && cd shadow
git apply /path/to/dc-networking/research/pq-gasper/gossipsub/sim/shadow-3.3-fixes.patch
./setup build --clean && ./setup install          # installs ~/.local/bin/shadow
# wbsim builds against a patched libp2p-gossipsub 0.49.5 in sim/wbsim/gossipsub (see below)
curl -sL https://static.crates.io/crates/libp2p-gossipsub/libp2p-gossipsub-0.49.5.crate | tar xz -C sim/wbsim
mv sim/wbsim/libp2p-gossipsub-0.49.5 sim/wbsim/gossipsub
patch -d sim/wbsim/gossipsub -p1 < sim/gossipsub-0.49.5-lazy-queue.patch
patch -d sim/wbsim/gossipsub -p1 < sim/gossipsub-0.49.5-sim-scoring.patch
cargo build --release --manifest-path sim/wbsim/Cargo.toml

python3 sim/gen_config.py --mode gossip --proofs pull --seed 1 --out runs/gp-s1
python3 sim/gen_config.py --mode gossip --seed 1 --out runs/g-s1          # proofs flooded
python3 sim/gen_config.py --mode direct --seed 1 --out runs/d-s1
python3 sim/gen_config.py --mode gossip --proofs pull --votes 1560 --topics-per-subnet 4 --out runs/gp-dc-s1
(cd runs/gp-s1 && shadow shadow.yaml > shadow.log)   # likewise for the others

python3 sim/analyze.py runs/gp-s1 runs/d-s1 ...   # markdown tables
```

Resources, on a 16-core, 31 GB orb with one run at a time:

| run | wall time | memory |
|---|---|---|
| direct, 32-slot | ~30 s | a few GB |
| direct, 8-slot | ~55 s | more: each voter holds connections to up to 128 recipients |
| gossip, proofs pulled (`--proofs pull`) | ~8 min | ~11 GB |
| gossip, 8-slot, proofs pulled | ~17 min | – |
| gossip, proofs flooded | ~13 min | ~22 GB |

A direct 8-slot run next to a flooded gossip run exhausted 31 GB, so run them
one at a time or add swap.

Gasper questions ([results/gasper.md](../results/gasper.md)):

```sh
# Q1: 32,768 votes, each node's votes batched, every vote to all 128 aggregators
python3 sim/gen_config.py --mode direct --subnets 1 --votes 32768 --aggregators 128 \
  --hosts 224 --home-share 0.35 --batch-votes --agg-cloud-share 1.0 --attester-votes 4 --out runs/q1-s1
# Q2: N aggregates at 8 s, pushed to a 16-node decoy set or flooded to everyone
python3 sim/gen_config.py --mode direct --subnets 1 --votes 384 --hosts 312 --agg-cloud-share 1.0 \
  --prove-ms 0 --slots 3 --aggregators 64 --proofs decoy --decoys 16 --out runs/q2-decoy-n64
python3 sim/gen_config.py --mode direct --subnets 1 --votes 384 --hosts 312 --agg-cloud-share 1.0 \
  --prove-ms 0 --slots 3 --aggregators 16 --proofs flood --out runs/q2-flood-n16
```

Run names in `results/sim.md` map to flags: `gp-sN` is `--mode gossip
--proofs pull --seed N`, `g-sN` is `--mode gossip --seed N`, `d-sN` is
`--mode direct --seed N`. Add `--votes 1560 --topics-per-subnet 4` for
`-dc`, `--profile eip7870-min` for `-min`, `--subnets 1` for `-1sub` and
`--cold-connect` for `-cold`.

## Mainnet-realism perturbations (`sim/perturb.py`)

Flood runs take these flags on top of the scenario flags. Each is off by default, and each is independent.
Values and their sources are in [results/realism-calibration.md](../results/realism-calibration.md).

| flag | what it does |
|---|---|
| `--net cities` | 12 cities (Probelab node shares) with a WonderNetwork RTT matrix instead of 5 regions |
| `--access` | home (non-1 Gbit) hosts sit behind a fiber / cable / DSL access edge (FCC MBA idle latency) |
| `--jitter` | exponential per-packet delay on access and backbone edges, FIFO per destination (needs `shadow-3.3-jitter.patch`) |
| `--loss` (`--loss-scale`) | packet loss on access and backbone edges |
| `--churn-conn-life S`, `--churn-restart-per-day R`, `--churn-leave F`, `--churn-join F` | connection churn by the peer manager; restarts (the swarm is dropped, all gossipsub state lost, back after 30–90 s); permanent leaves and late joins. Signatures of validators whose host is down are never published |
| `--bg` | background traffic: blocks (90 % from relays, lognormal publish time around 1 s), 128 data-column topics (Poisson blobs), 64 attestation subnets (2 per node, all 64 above `--all-subnets-above` validators), aggregates, sync contributions; data-column custody 4 / 8–128 by validators |
| `--verify` (`--verify-us`, `--workers-*`, `--slow-cpu-share`, `--slow-cpu-factor`) | verification delay before forwarding, per message kind, on N parallel workers; some home hosts slower |
| `--scoring` (`--score-disconnect`, `--score-slow-peer-weight`) | gossipsub v1.1 peer scoring with Lighthouse's parameters; PQ subnets scored like attestation subnets |
| `--client-mix` (`--client-gs`, `--peer-scale`) | per-client peer targets (and gossipsub parameters) drawn with Probelab client shares |
| `--nat-share F` | share of home hosts behind NAT: never discovered, inbound refused |
| `--bad-share`, `--bad-rate`, `--freeride-share` | hosts that publish invalid messages (rejected, P4), hosts that never forward |
| `--no-pq` | today's BLS load only (calibration) |
| `--ping S` | libp2p ping, RTTs logged (validation) |
| `--client-slow-peer` | with `--client-mix --scoring`: slow-peer score weight 0 on Prysm, Teku, Nimbus and Lodestar hosts (go-libp2p-pubsub and js gossipsub have no such term, Nimbus sets weight 0, Teku's variant is treated as 0); Lighthouse and `other` (Grandine included, not split by client) keep rust-libp2p's −10 |
| `--max-msg-age S` | wbsim ignores (no forward, not recorded) a flood message received more than S s after it was published, as clients' first-seen rules do; counted as `stale_pq` / `stale_bg` in the tick events. Without it, a message held in a stalled connection past gossipsub's 60 s duplicate cache is accepted as new everywhere and re-floods the network (seen from slot 28 of a 1,024-host 50-slot run). Use 60 for runs longer than ~10 slots |
| `--client-p3-promises` | with `--client-mix --scoring`, on top of `--client-slow-peer` (binary `cf2`): mesh-delivery (P3/P3b) weight per observer client on every topic: 0 on Prysm hosts (`meshDeliveryIsScored = false`), −max_positive_score / (topic_weight × threshold²) on Teku, Lodestar and Nimbus hosts (a full deficit costs the sim's whole max positive score, 157.5 with PQ topics, 107.5 without), Lighthouse's −topic_weight on Lighthouse and `other` hosts. Broken IWANT promises cost P7 for every requested id on Lighthouse and `other` hosts (rust-libp2p), for one random id per IWANT on Prysm, Teku and Lodestar hosts, never on Nimbus hosts. Prysm, Teku, Lodestar and Nimbus hosts ask for every unseen id of an IHAVE, even one already requested from another peer (their only limits are per peer and heartbeat); Lighthouse and `other` hosts skip it until that promise is fulfilled or expires (3 s), as rust-libp2p does. Each node logs its view as a `score_cfg` event |
| `--score-mesh-activation S` | with `--scoring`, validation only: P3 activation S seconds on every topic instead of 17 slots (attestation and PQ subnets) or 1 epoch |

With `--scoring`, the PQ topics' expected message rate is msgs / sig-subnets per slot, or the mean number of messages actually published per slot / sig-subnets when `--batch` or `--bundler` packs signatures into fewer messages (about 67.4 instead of 125 with `--batch 16`).

All of these switch wbsim to per-node publish files (`<run>/pubs/<id>.json`); background messages are in
`<run>/bg.json`. `python3 sim/realism_check.py <run>` writes `realism.json`: RTT vs configured, loss and
retransmissions from pcap (`--pcap K`), churn and mesh (re)graft events, background bytes per node, scoring,
block/column/attestation/aggregate arrival percentiles, peers and mesh by client, PQ completion (node·slots with
the host offline are excluded). With `--bg`, `analyze.py --levers` κ and after-deadline bytes include background
traffic.

The jitter patch is a third Shadow patch, applied on top of `shadow-3.3-fixes.patch`:
`git apply shadow-3.3-fixes.patch shadow-3.3-jitter.patch`. Without it, `jitter` edges are parsed and ignored.

Optional TCP-fidelity builds, each applied after the fixes and jitter patches and each replacing the one before
(see the header of each file). Shadow 3.3.0's TCP never takes an RTT sample, so its RTO starts at 1 s and doubles at
every isolated timeout for good:
- `shadow-3.3-rtt.patch`: Linux-default socket buffers, a working timestamp echo, RTO = SRTT + max(4·RTTVAR, 200 ms);
- `shadow-3.3-rtt2.patch`: rtt + Eifel undo of spurious timeouts + Linux's RTT estimator and RTO (v6.12);
- `shadow-3.3-rtt3.patch`: rtt2 + Linux's post-RTO window (cwnd = packets in flight + 1, as `tcp_enter_loss` sets it);
- `shadow-3.3-rtt4.patch`: rtt3 + the RFC 7323 echo rule of Linux's `tcp_replace_ts_recent` (an ACK that waits in the
  upload queue echoes the first segment it newly acknowledges, not the newest one that arrived meanwhile);
- `shadow-3.3-rtt5.patch`: rtt4 + the growth rule of Linux's congestion-window validation (`tcp_is_cwnd_limited`; not
  `tcp_cwnd_application_limited`), restart after idle (`tcp_cwnd_restart`) and RFC 5681 duplicate-ACK counting in
  congestion avoidance (an ACK that advances snd_una resets Reno's count), a sensitivity build. All three are on by
  default; `RTT5_CWV=0`, `RTT5_SSR=0` and `RTT5_DUP=0` in Shadow's environment turn them off, and with all three off
  it behaves exactly like rtt4.
- `shadow-3.3-rtt5b.patch`: rtt5 + a fourth switch, off by default: with `RTT5_BETA=1`, fast-recovery entry and an
  RTO set ssthresh = max(cwnd × 717 / 1024, 2), CUBIC's decrease (`bictcp_recalc_ssthresh`), instead of Reno's
  cwnd / 2 + 1. With the switch unset it behaves exactly like rtt5. Also a sensitivity build.
- `shadow-3.3-rtt6.patch`: rtt5b + Linux's CUBIC (`net/ipv4/tcp_cubic.c`, v6.12) in place of Reno's congestion
  avoidance and decrease: `bictcp_update` with TCP friendliness and the cnt ≥ 2 cap, `tcp_cong_avoid_ai`,
  `cubictcp_recalc_ssthresh` (β = 717/1024, fast convergence), the epoch shift when data goes out with nothing in
  flight (`CA_EVENT_TX_START`), the full reset at every RTO (the Loss state; the Eifel undo does not restore it),
  delay_min from the RTT samples, and HyStart (ack train and delay, v6.12 defaults). Jiffies are milliseconds
  (HZ = 1000). `RTT6_CUBIC` and `RTT6_HYSTART` are on by default; `RTT6_CUBIC=0` behaves exactly like rtt5b and
  `RTT6_HYSTART=0` keeps CUBIC without HyStart. Slow start, fast recovery and the RTO handling stay Reno's. A
  sensitivity build. Its CUBIC and HyStart counters go on a `tcpd cubsnap` line next to each snapshot: appended to
  the snapshot line, they made it longer than Shadow's 500-byte log message buffer, which cut its end. With
  `RTT5_SSR=0` (cwv6) it models Linux with `net.ipv4.tcp_slow_start_after_idle=0`: CUBIC and HyStart with window
  validation but no restart after idle.

With `LNXBUF_LOG` set, these builds log per-connection `tcpd` lines.
