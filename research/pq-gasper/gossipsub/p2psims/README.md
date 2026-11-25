# p2psims tooling

What ran the simulations on p2psims (96 CPUs, 503 GiB), copied from the machine on 23 November 2026 at 17:09 CET, while a follow-up study was still running. The analysis outputs that study wrote afterwards were added on 24 November.

- [runs/](runs/): the machine's `runs/` scripts, queues and logs. The run directories themselves (338 GB) are not kept.
- [analysis/](analysis/): the machine's `.amp-out/` analysis scripts. [analysis/results-notes.md](analysis/results-notes.md) is the run registry, with every run and number, and [analysis/out/](analysis/out/) holds each script's output per run as `<script>-<RUN>.txt`.
- [shadow-wrappers/](shadow-wrappers/): the `shadow-install-*/bin/shadow` wrappers, each running one Shadow build with environment switches, such as `LNXBUF_LOG=1` for the TCP logs.

The reports cite these by their machine paths: `runs/X` is `p2psims/runs/X` here, and `.amp-out/X` is `p2psims/analysis/X`. The scripts keep the machine's absolute paths (`/home/yann/p2p-ministry-gossip2000`).

- **PQ Gasper one-subnet study:** `runs/run_pq1600.sh` on top of `runs/run_lever.sh`, and `analysis/pq1600.py`; the report's Commands section lists the rest. It ran on the rtt6 Shadow build (v3.3.0 with `sim/shadow-3.3-fixes.patch`, `shadow-3.3-jitter.patch` and `shadow-3.3-rtt6.patch`) and the `cf2` wbsim binary, which is `sim/wbsim` as committed, built with rustc 1.95.0.
- **Subnet-specs follow-up:** `runs/specs-*`, `runs/queue-specs.txt`, `analysis/specs.py` and `analysis/specs-decide.py`. It was still running at the snapshot. Its reports are [results/pq-gasper-subnet-specs.md](../results/pq-gasper-subnet-specs.md) (2,048 nodes) and [results/pq-gasper-subnet-specs-1024.md](../results/pq-gasper-subnet-specs-1024.md) (1,024 nodes). [analysis/out/](analysis/out/) holds every output of the study, including the 136 files it wrote after the snapshot, between 23 November 17:32 and 24 November 14:26 CET: those of three more 2,048-node runs, two 512-node diagnostics and the twelve 1,024-node runs, and further outputs for earlier runs, such as `slotcounts-*.txt`. The scripts, queues and logs here are as of the snapshot, so those of the 1,024-node runs are missing: `runs/queue-specs1024.txt`, `runs/specs1024-queue.sh` and `analysis/specs1024-*.py`, one of which writes the `slotcounts` files. The run registry ends at the snapshot too.
- The other scripts served the superseded studies; several analysis scripts serve both.
- `run_lever.sh` passes `data/f9ba162f-nodes.csv`, a mainnet node crawl that is not published because it maps validators to nodes. The generator reads only its `validator_count` column: 13,613 rows, 727,723 validators, 10,902 nodes with at least one. A file with just that column, in the same order (sha256 `1f17ea053564d7412f4a082e2fd58bc1108eeb88648497baee31302146a0bfa7`), generates the same configs; only `run.json` records the file name.
- The rules for sharing the machine are in Yann's `using-p2psims` Amp skill.
