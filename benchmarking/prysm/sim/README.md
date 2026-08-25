# Shadow simulation scripts

The core framework for the decoupled-consensus Shadow simulations: everything
needed to generate a run's config, build its genesis, gate it before launch,
and turn its logs into queryable parquet. Per-run driver scripts, analysis
queries and result data are deliberately not here.

A run is one *rung*: N prysm nodes, 200 validators each, 16 slots, on a
country-weighted latency topology. 70 % of the ELs are meshed, 30 % run
`--maxpeers 0` to make a private block class.

## The scripts

| File | What it does |
| --- | --- |
| `make-rung-config.py` | Writes the ethshadow input yaml for one rung: per-node country placement from the mainnet crawl weights, a full pairwise latency matrix, the supernode/home-staker bandwidth split, the spamoor arms. Also writes eth-slot-sim's `topology.json` with `--topology-out`. |
| `spamoor-premine.py` | Derives spamoor's child wallet addresses from the config and injects them into the yaml's `premine` block. Without it the private arm never gets funded, because a `--maxpeers 0` EL only confirms a funding tx when that one node proposes. Also `--check`s them against a generated genesis alloc. |
| `spamoor-children.go` | The address derivation itself, mirroring spamoor's `prepareChildWallet`. Build it and put the binary in `$SIM_BIN_DIR`. |
| `tune-shadow-config.py` | Edits the *generated* shadow.yaml: `GOMEMLIMIT` on every beacon, a deterministic start-time stagger, and a trim of the prometheus scrape targets. |
| `Dockerfile.genesis-gen` | Patches ethpandaops' genesis generator so Heze stays CL-only (no `bogotaTime` in the EL genesis) and so `SLOTS_PER_EPOCH` is overridable. |
| `make-heze-genesis.sh` | Replaces the generator's CL genesis with a Heze one built by `prysmctl`, over the same mnemonic and index range the validator keystores use. Asserts the CL genesis names the eth1 block geth actually stored. |
| `preflight.sh` | The launch gate. Reads only generated artefacts and checks fork epochs, premined wallets, payload and blob math, the meshed/isolated endpoint split, syscall model, stagger window, beacon flags, binary markers, disk and RAM. Exit status is the number of failed checks. |
| `logs-to-parquet.py` | Turns a finished run's beacon logs into parquet tables with duckdb, with strict parse accounting. |

## Pipeline

Run from the deployed `sim/` directory. `N` is the node count, `LABEL` the run
label (it names the binaries and seeds the spamoor instances), `DATA` the
output directory.

```sh
# 0. once: the patched genesis generator image the config names
docker build -f Dockerfile.genesis-gen -t ethereum-genesis-generator:6.0.2-spe8 .

# 0b. once: the child-wallet deriver
go build -o "$SIM_BIN_DIR/spamoor-children" spamoor-children.go

# 1. config + topology
./make-rung-config.py "$N" "$LABEL" --topology-out "topology-$LABEL.json" \
    > "sim-${N}nodes-$LABEL.yaml"
./spamoor-premine.py "sim-${N}nodes-$LABEL.yaml" --inject

# 2. generate the run
ethshadow --gen-only -d "$DATA" "sim-${N}nodes-$LABEL.yaml"

# 3. strip experimental.runahead (see "Known gaps")
# 4. tune the generated config
./tune-shadow-config.py "$DATA" --stagger 5 180 --memlimit 1700MiB --targets 16

# 5. genesis
SIM_YAML="sim-${N}nodes-$LABEL.yaml" ./make-heze-genesis.sh "$DATA" "$((N * 200))"

# 6. gate
./preflight.sh "$DATA" "sim-${N}nodes-$LABEL.yaml" "$PREFLIGHT_REF"

# 7. launch
shadow -d "$DATA/shadow" "$DATA/shadow.yaml" > "shadow-$LABEL.log" 2>&1

# 8. logs -> parquet
./logs-to-parquet.py "$DATA" "parquet/$LABEL" --validate
```

Order matters at two points: `make-heze-genesis.sh` must run after
`ethshadow --gen-only` (ethshadow has already run `geth init`, so the EL
genesis is fixed and only the CL side may be rewritten), and `preflight.sh`
must run after both the tune pass and genesis, because every check it makes
reads a generated file.

## Environment

| Variable | Default | Used by |
| --- | --- | --- |
| `ETH_SLOT_SIM_DATA` | `country-data/` next to the script | `make-rung-config.py` — directory holding `country_weights.json` and `country_latencies.json`. They live in `data/` of the eth-slot-sim repo (github.com/sukunrt/eth-slot-sim); point this at that clone's `data`. Also settable with `--country-data`. |
| `SIM_BIN_DIR` | `bin/` next to the script | `make-rung-config.py` (`--bin-dir`), `spamoor-premine.py`, `preflight.sh` — holds `prysm-beacon-<label>`, `prysm-validator-<label>`, `spamoor`, `spamoor-children`. |
| `CL_CONFIG_TEMPLATE` | `../cl-config-goldfish.yaml` | `make-rung-config.py` (`--cl-config`) — baked into the yaml as `cl_config_template`, absolute. |
| `LIGHTHOUSE_BIN` / `LCLI_BIN` | `lighthouse` / `lcli` on `PATH` | `make-rung-config.py` — the bootnode binaries. |
| `PRYSMCTL` | `prysmctl` on `PATH` | `make-heze-genesis.sh` |
| `GETH` | `geth` on `PATH` | `make-heze-genesis.sh` — only for the genesis hash cross-check. |
| `SIM_YAML` | `sim.yaml` | `make-heze-genesis.sh` — the run's config; only the generator image name is read out of it. |
| `SPAMOOR_CHILDREN` | `$SIM_BIN_DIR/spamoor-children` | `spamoor-premine.py` |
| `PREFLIGHT_REF` | unset | `preflight.sh` — a known-good earlier data dir whose generated CL config this run is diffed against. Optional; the diff is skipped when unset. |

The paths in the environment end up *inside* the generated yaml, because
ethshadow resolves them from its own working directory. They are made absolute
at generation time.

## CL config

The chain config is [`../cl-config-goldfish.yaml`](../cl-config-goldfish.yaml),
one directory up — it is documented in `../shadow.md` and is not duplicated
here. `make-rung-config.py` defaults to that path and writes it, absolute, into
the generated yaml's `ethereum.genesis.cl_config_template`. Override with
`--cl-config` or `$CL_CONFIG_TEMPLATE`.

## Deploying to a simulation host

Shadow runs need a lot of RAM and disk, so these run on a dedicated host. Sync
the parent directory, not just `sim/`, so the CL config comes along:

```sh
rsync -av --exclude 'data*' --exclude 'parquet' --exclude '__pycache__' \
    benchmarking/prysm/ <host>:<workdir>/
```

`<workdir>/sim` is then the working directory for the pipeline above: the sim
yaml, the topology json, the data dirs and the parquet output all land there,
next to the scripts. Set the environment on the host (a small `env.sh` sourced
before a run is enough); nothing in these scripts assumes a particular home
directory or user.

The binaries — the prysm fork's beacon and validator, spamoor, lighthouse,
geth, prysmctl, ethshadow — are built separately and are not synced by the
line above. Freeze a beacon/validator pair per run label; `preflight.sh`
checks the beacon carries the ledger marker strings.

## Known gaps

* **The runahead strip has no script.** ethshadow inserts
  `experimental.runahead` on its own, and v4 runs without it. The strip lives
  inline in the per-run driver, which is not part of this set. Between step 2
  and step 4, delete the key from `$DATA/shadow.yaml` and assert it is gone;
  `tune-shadow-config.py` does not put it back.
* **The extra preflight checks are per-run.** `preflight.sh` is the standing
  gate, but each run also carries an `extra<NN>.py` with the checks that run
  cared about (topology asserts, supernode counts, per-class bandwidth). Those
  are run-numbered files and stay out; the topology json has enough in its
  `meta` block to re-derive them.
* **The launch asserts are per-run too** — host count, `stop_time`, the
  distinct-latency check that proves the country topology applied. They live
  in the launch driver.
* **Country data is not vendored.** It comes from eth-slot-sim, which is a
  separate repo; see `ETH_SLOT_SIM_DATA`.
* **Analysis beyond parquet is not here.** The per-run SQL, the vote ledgers
  and the report generators are separate.
