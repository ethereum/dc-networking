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
per class. Results: [results/gossip-2000.md](../results/gossip-2000.md).

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

## Run

```sh
# once: Shadow 3.3 from source, patched, and Rust
#   apt deps: https://shadow.github.io/docs/guide/install_dependencies.html
git clone --depth 1 --branch v3.3.0 https://github.com/shadow/shadow.git && cd shadow
git apply /path/to/p2p-ministry/sim/shadow-3.3-fixes.patch
./setup build --clean && ./setup install          # installs ~/.local/bin/shadow
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
