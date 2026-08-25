#!/usr/bin/env python3
"""Write one rung of the simulation: the frozen recipe at a given node count.

    ./make-rung-config.py 100 r1 --topology-out topology-r1.json > sim-100nodes-r1.yaml
    ./spamoor-premine.py sim-100nodes-r1.yaml --inject

A rung is N prysm nodes, 200 validators each, and 16 slots at the stop_time
of 492 s. Everything else is frozen and lives in the template
below; the only thing that moves between rungs is N. Edit this file, not its
output.

The shape, and why each piece is the way it is:

* 30 % of the ELs run ``--maxpeers 0``. Their pools are reachable only over
  their own RPC, which is what makes a private block class -- a block whose
  columns no other node could have built locally.
* Blob rates are PER POOL, not per network. Each pool settles at two blob
  transactions of three sidecars -- 6 blobs -- so a block carries 6 whichever
  class proposes it, and the private share of all blobs comes out at the
  isolated share of proposals, about 30 %.
* One private blob instance per isolated EL, ``el_count: 1``. The blobs
  scenario picks wallets by pending-transaction count, which does not pin a
  wallet to an endpoint; one instance spread over k isolated ELs would send a
  wallet's nonce n to one and n+1 to another, where n+1 waits behind a nonce
  gap until the first proposes. With one endpoint there is no gap.
* Child wallets are premined. spamoor funds children on chain and WAITS for
  confirmation; against a --maxpeers 0 EL that confirms only when that node
  proposes, which at 100 nodes never happened. See spamoor-premine.py.
* All private arms share one premine root key. They never spend from it --
  every child is already rich -- and their seeds differ, so their child sets
  are disjoint.
* The transfer arm stays at 8 pending 16 KiB-calldata transactions. One
  proposer builds one block out of the shared meshed pool, so a fixed pending
  count keeps payload bytes constant as N grows.

The country topology:

* Every prysm node gets ONE country, sampled from the mainnet crawl weights in
  country_weights.json with a seeded rng. The seed is written into the yaml
  header and into the topology json.
* Every prysm node gets its own ethshadow ``location``. ethshadow builds one
  network vertex for each (location, reliability) pair and a full pairwise
  edge set over them, so each location must give a latency to EVERY location.
  The values come from country_latencies.json, which is asymmetric: the
  source->target value is used, the intra-country diagonal covers a
  same-country pair, and a missing pair falls back to 100 ms.
* packet_loss_to is 0.0 everywhere. use_builtin_locations and
  use_builtin_reliabilities are false, because ethshadow's builtin locations
  carry no latency to ours.
* Bandwidth: a supernode fraction of 0.2 gives 20 % of the nodes 1024/1024
  Mbit and the rest the home-staker 25/50 Mbit.
* The boot node, the prometheus host and every spammer host are pinned to
  germany on the supernode class. They are infrastructure, not measurements.
* eth-slot-sim's topology.json is written next to the yaml with --topology-out.
  prysm picks its own peers, so the adjacency in that file is the FULL pairwise
  latency graph, which is exactly what Shadow gets. The file exists so the
  graph is on record and comparable with an eth-slot-sim run.

The recipe drops ``experimental.runahead``. ethshadow inserts the key itself, so
the generated shadow.yaml has to be stripped after --gen-only; this script only
declines to ask for it.

Paths this script bakes into the yaml come from the environment, so the same
file works on any host:

* ``ETH_SLOT_SIM_DATA`` -- directory holding country_weights.json and
  country_latencies.json. They live in ``data/`` of the eth-slot-sim repo
  (github.com/sukunrt/eth-slot-sim); point this at that clone's ``data``.
  Falls back to ``country-data/`` next to this script. Or pass --country-data.
* ``SIM_BIN_DIR`` -- prysm-beacon-<label>, prysm-validator-<label> and spamoor.
  Defaults to ``bin/`` next to this script. Or pass --bin-dir.
* ``LIGHTHOUSE_BIN`` / ``LCLI_BIN`` -- the bootnode binaries, default to the
  names on PATH.
* ``CL_CONFIG_TEMPLATE`` -- the CL config the genesis generator templates.
  Defaults to ``../cl-config-goldfish.yaml``, which is where the repo keeps it.
"""

import argparse
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_COUNTRY_DATA = os.environ.get(
    "ETH_SLOT_SIM_DATA", os.path.join(HERE, "country-data"))
DEFAULT_BIN_DIR = os.environ.get("SIM_BIN_DIR", os.path.join(HERE, "bin"))
DEFAULT_CL_CONFIG = os.environ.get(
    "CL_CONFIG_TEMPLATE", os.path.join(HERE, os.pardir, "cl-config-goldfish.yaml"))
DEFAULT_LIGHTHOUSE = os.environ.get("LIGHTHOUSE_BIN", "lighthouse")
DEFAULT_LCLI = os.environ.get("LCLI_BIN", "lcli")
FALLBACK_LATENCY_MS = 100
INFRA_COUNTRY = "germany"
INFRA_LOCATION = "infra-germany"
SUPER_UP_DOWN = (1024, 1024)
STAKER_UP_DOWN = (25, 50)

TEMPLATE = """\
# Simulation rung: {n} prysm nodes x {vpn} validators = {v} validators, {slots} slots.
#
# Generated by make-rung-config.py; edit that, not this file. The premine
# block is filled in afterwards by spamoor-premine.py --inject.
#
# {meshed} ELs meshed (endpoint indices 0..{last_meshed}), {isolated} isolated with
# --maxpeers 0 (indices {first_iso}..{last_iso}), the 30 % private split the campaign fixed.
#
# Genesis is at simulated 00:05:00 and slots are 12 s, so stop_time {stop}s
# gives {slots} slots. This is a latency run: the first justification needs slot 24
# and is NOT observable here.
#
# Frozen recipe, identical on every rung: --p2p-max-peers 99 explicit,
# 5s..180s stagger, 6 blobs a block in every pool, ~128 kB of transfer payload
# a block from 16 KiB calldata transfers on the meshed side, GOMEMLIMIT,
# ledger + pprof flags.
#
# Network: country-weighted placement, seed {seed}, supernode fraction
# {superfrac}. {nsuper} of {n} nodes are supernodes at {sup_up}/{sup_down} Mbit; the other
# {nstaker} are home stakers at {stk_up}/{stk_down} Mbit. Countries come from
# country_weights.json and latencies from the asymmetric country_latencies.json
# ({ncountries} distinct countries in this rung). Infrastructure hosts (boot,
# prometheus, every spammer) are pinned to {infra_country} on the supernode class.
#
# The gas floor on this chain is 21,000 + 64 a calldata byte: run 38 had geth
# reject a 750,000-gas 16 KiB transfer with "minimum needed 1069576", and
# 1069576 - 21000 is exactly 64 x 16384. --gaslimit 1150000 is 7 % over.
#
# EL premine root keys (m/44'/60'/0'/0/i off ethshadow's DEFAULT_MNEMONIC):
#   i=0  0x500502A21d83e342193AAeD5b23C7091a9cbffE6  eoatx, meshed
#   i=2  0xc790Df49f74A0571C648B1C08D0937188A6a61D0  blobs, meshed
#   i=3  0x5346FfBF9554174F62491C17812A8734F7D23180  blobs, every isolated EL

general:
  # Required: with this key absent the sim clock froze mid-boot at ~100 nodes
  # (Shadow busy-loop starvation).
  model_unblocked_syscall_latency: true
  stop_time: {stop}s
  progress: true
  heartbeat_interval: 1m

experimental:
  # ethshadow defaults this to true, but it SIGSEGVs Go 1.26 binaries at exec
  # under Shadow 3.3.0.
  use_memory_manager: false
  # The recipe asks for NO runahead key. ethshadow inserts one anyway (or_insert of the
  # minimum edge latency), so gen*.sh strips it from the generated shadow.yaml.

ethereum:
  validators: {v}
  # ethshadow's builtin locations and reliabilities carry no latency to the
  # per-host locations below, and the graph needs every pair.
  use_builtin_locations: false
  use_builtin_reliabilities: false
  genesis:
    # THE payload cap. max_pending alone does not hold: run 39 had two
    # consecutive isolated proposals starve the meshed pool, spamoor reissued
    # the stalled transfers on fresh nonces, and every later block was
    # gas-saturated at 26 transactions and 382 kB against a max_pending of 8.
    # geth packs against gas USED, not the --gaslimit reservation: run 40 fit
    # NINE transfers in a 9.7 M block (9 x 1,069,576) and made 150,866 B.
    # 9.0 M leaves room for eight (8,556,608) plus the blob transactions
    # (3 x 21,000) and stops a ninth. 8 x 16,610 + 542 = 133,422 B.
    gaslimit: 9000000
    generator_image: ethereum-genesis-generator:6.0.2-spe8
    cl_config_template: {cl_config}
    electra_epoch: 0
    fulu_epoch: 0
    # Gloas at 0 gives the EL an amsterdamTime at genesis, which
    # forkchoiceUpdatedV4 requires; prysm gates on GloasForkEpoch.
    gloas_epoch: 0
    extra_env:
      HEZE_FORK_EPOCH: "0"
      HEZE_FORK_VERSION: "0x90000000"
      AVAILABLE_ATTESTATION_DUE_BPS_HEZE: "2500"
      GENESIS_TIMESTAMP: "946685100"
      GENESIS_DELAY: "0"
    # BEGIN spamoor child wallets
    premine: {{}}
    # END spamoor child wallets
  reliabilities:
    staker:
      added_latency: 0ms
      added_packet_loss: 0.0
      bandwidth_up: {stk_up} Mbit
      bandwidth_down: {stk_down} Mbit
    super:
      added_latency: 0ms
      added_packet_loss: 0.0
      bandwidth_up: {sup_up} Mbit
      bandwidth_down: {sup_down} Mbit
  locations:
{locations}  nodes:
{node_entries}  clients:
    prysm:
      type: prysm
      executable: {bin_dir}/prysm-beacon-{label}
      # ethshadow would push --p2p-max-peers (num_cl_clients - 1) at 100 CL
      # clients or fewer, and prysm's own default is 70. The campaign wants one
      # cap on every rung, so its rule is off and the value is explicit.
      lower_target_peers: false
      extra_args: --p2p-max-peers 99 --goldfish-vote-ledger --pprof --pprofaddr=0.0.0.0
    prysm_vc:
      type: prysm_vc
      executable: {bin_dir}/prysm-validator-{label}
      extra_args: --decoupled-ffg-vote-at-slot-start
    lighthouse_bootnode:
      type: lighthouse_bootnode
      executable: {lighthouse}
      lcli_executable: {lcli}
    geth_isolated:
      type: geth
      # No EL peers. The node still follows the chain -- its CL feeds it every
      # payload over the engine API -- but it can only learn a transaction
      # from its own RPC.
      extra_args: --maxpeers 0

    # ---- meshed arm ----
    spamoor_eoatx_public:
      type: spamoor
      executable: {bin_dir}/spamoor
      scenario: eoatx
      # max_pending is what sets the payload size: 8 x (16384 + 226) block
      # bytes + a 542-byte header is 133,422 B.
      throughput: 8
      max_pending: 8
      max_wallets: 8
      el_first: 0
      el_count: {meshed}
      extra_args: --seed {label}-eoa-pub --data random:16384 --gaslimit 1150000 --basefee 100 --rebroadcast 0
      private_key: 0x306cb89d3f8c1da466d8c2762b600b98e911dd45d0daa885c073ac94f45ded31
      start_time: 312s
    spamoor_blobs_public:
      type: spamoor
      executable: {bin_dir}/spamoor
      scenario: blobs
      # Blob count is set by the sidecar count, not by max_pending. The pool
      # settles at max_pending transactions in the steady state and drifts to
      # three or four after a slot whose proposer could not include them, so
      # at --sidecars 3 a block carries 6 blobs normally and at most 9, the
      # cap. Run 41 tried 2 sidecars and got 4 blobs a block -- under target.
      throughput: 2
      max_pending: 2
      max_wallets: 6
      el_first: 0
      el_count: {meshed}
      extra_args: --seed {label}-blob-pub --sidecars 3 --fulu-activation 946685100 --rebroadcast 0
      private_key: 0x47c8d566df4d9d9fa45a245901ec0fe18bc21757bcdf54a9902014e9e883ab7a
      start_time: 312s

    # ---- private arm: one instance per isolated EL, el_count 1 ----
{private_clients}"""

BOOT_HOST = """\
    - location: {loc}
      reliability: super
      tag: boot
      clients:
        el: geth_bootnode
        cl: lighthouse_bootnode
"""

# EL endpoints are registered in node order and geth_bootnode registers none,
# so the meshed group is written first and the spamoor instances slice the
# endpoint list with el_first / el_count. One entry is written per node, because
# every node has a location of its own.
PRYSM_HOST = """\
    - location: {loc}
      reliability: {rel}
{tagline}      clients:
        el: {el}
        cl: prysm
        vc: prysm_vc
"""

INFRA_HOST = """\
    - location: {loc}
      reliability: super
      tag: {tag}
      clients:
        {kind}: {client}
"""

PRIVATE_CLIENT = """\
    spamoor_blobs_priv{j}:
      type: spamoor
      executable: {bin_dir}/spamoor
      scenario: blobs
      throughput: 2
      max_pending: 2
      max_wallets: 4
      el_first: {el}
      el_count: 1
      extra_args: --seed {label}-blob-p{j} --sidecars 3 --fulu-activation 946685100 --rebroadcast 0
      private_key: 0x214a21952164e2d33c9a07a29c9e9a16f95e5d0edd78d4168a19a3fa52dbe767
      start_time: 312s
"""


def slug(country):
    return country.replace(" ", "-").replace("_", "-")


def load_json(data_dir, name):
    path = os.path.join(data_dir, name)
    with open(path) as fh:
        return json.load(fh)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("n", type=int, help="prysm nodes in the rung")
    ap.add_argument("label", help="run label, e.g. r54 (names binaries and seeds)")
    ap.add_argument("--validators-per-node", type=int, default=200,
                    help="validators for each node")
    ap.add_argument("--stop-time", type=int, default=492,
                    help="shadow stop_time in seconds; genesis is at 300s and "
                         "slots are 12s; 492 gives 16 slots")
    ap.add_argument("--supernode-fraction", type=float, default=0.2,
                    help="fraction of nodes at 1024/1024 Mbit; the rest get the home-staker 25/50")
    ap.add_argument("--seed", type=int, default=54,
                    help="rng seed for the country placement and the supernode draw")
    ap.add_argument("--topology-out", default=None,
                    help="write eth-slot-sim's topology.json here")
    ap.add_argument("--country-data", default=DEFAULT_COUNTRY_DATA,
                    help="directory with country_weights.json and "
                         "country_latencies.json ($ETH_SLOT_SIM_DATA); "
                         "default %(default)s")
    ap.add_argument("--bin-dir", default=DEFAULT_BIN_DIR,
                    help="directory with the prysm and spamoor binaries "
                         "($SIM_BIN_DIR); default %(default)s")
    ap.add_argument("--cl-config", default=DEFAULT_CL_CONFIG,
                    help="CL config template for the genesis generator "
                         "($CL_CONFIG_TEMPLATE); default %(default)s")
    args = ap.parse_args()

    n = args.n
    meshed = round(n * 0.7)
    isolated = n - meshed
    nsuper = round(n * args.supernode_fraction)

    # Absolute, because ethshadow resolves the yaml's paths from its own cwd.
    bin_dir = os.path.abspath(args.bin_dir)
    cl_config = os.path.abspath(args.cl_config)

    weights = load_json(args.country_data, "country_weights.json")
    latencies = load_json(args.country_data, "country_latencies.json")
    countries = list(weights.keys())
    cweights = [weights[c] for c in countries]

    # One rng, used in a fixed order: N country draws, then the supernode draw.
    # The seed alone reproduces the whole placement.
    rng = random.Random(args.seed)
    node_country = [rng.choices(countries, weights=cweights)[0] for _ in range(n)]
    supers = set(rng.sample(range(n), nsuper))

    def lat(a, b):
        return latencies.get(a, {}).get(b, FALLBACK_LATENCY_MS)

    # location name -> country. One location for each prysm node, plus one
    # shared location for the pinned infrastructure hosts.
    loc_country = {}
    node_loc = []
    for i in range(n):
        name = "n%03d-%s" % (i, slug(node_country[i]))
        node_loc.append(name)
        loc_country[name] = node_country[i]
    loc_country[INFRA_LOCATION] = INFRA_COUNTRY

    loc_names = list(loc_country)
    lines = []
    for src in loc_names:
        lines.append("    %s:\n" % src)
        lines.append("      latency_to:\n")
        for dst in loc_names:
            lines.append("        %s: %dms\n"
                         % (dst, lat(loc_country[src], loc_country[dst])))
        lines.append("      packet_loss_to:\n")
        for dst in loc_names:
            lines.append("        %s: 0.0\n" % dst)
    locations = "".join(lines)

    entries = [BOOT_HOST.format(loc=INFRA_LOCATION)]
    for i in range(n):
        entries.append(PRYSM_HOST.format(
            loc=node_loc[i],
            rel="super" if i in supers else "staker",
            tagline="      tag: isolated\n" if i >= meshed else "",
            el="geth_isolated" if i >= meshed else "geth"))
    entries.append(INFRA_HOST.format(loc=INFRA_LOCATION, tag="monitoring",
                                     kind="monitoring", client="prometheus"))
    entries.append(INFRA_HOST.format(loc=INFRA_LOCATION, tag="eoaspam",
                                     kind="spammer", client="spamoor_eoatx_public"))
    entries.append(INFRA_HOST.format(loc=INFRA_LOCATION, tag="blobspam",
                                     kind="spammer", client="spamoor_blobs_public"))
    for j in range(isolated):
        entries.append(INFRA_HOST.format(loc=INFRA_LOCATION, tag="blobspampriv%d" % j,
                                         kind="spammer",
                                         client="spamoor_blobs_priv%d" % j))

    sys.stdout.write(TEMPLATE.format(
        n=n, vpn=args.validators_per_node, v=n * args.validators_per_node,
        meshed=meshed, isolated=isolated, label=args.label,
        stop=args.stop_time, slots=(args.stop_time - 300) // 12,
        last_meshed=meshed - 1, first_iso=meshed, last_iso=n - 1,
        seed=args.seed, superfrac=args.supernode_fraction,
        nsuper=nsuper, nstaker=n - nsuper,
        sup_up=SUPER_UP_DOWN[0], sup_down=SUPER_UP_DOWN[1],
        stk_up=STAKER_UP_DOWN[0], stk_down=STAKER_UP_DOWN[1],
        ncountries=len(set(node_country)), infra_country=INFRA_COUNTRY,
        locations=locations,
        bin_dir=bin_dir, cl_config=cl_config,
        lighthouse=DEFAULT_LIGHTHOUSE, lcli=DEFAULT_LCLI,
        node_entries="".join(entries),
        private_clients="".join(
            PRIVATE_CLIENT.format(j=j, el=meshed + j, label=args.label,
                                  bin_dir=bin_dir)
            for j in range(isolated)),
    ))

    if args.topology_out:
        # eth-slot-sim's schema. prysm picks its own peers, so the adjacency
        # here is the full pairwise latency graph -- exactly what Shadow gets.
        topo = {
            "nodes": [
                {"num": i,
                 "upload_bw_mbps": (SUPER_UP_DOWN if i in supers else STAKER_UP_DOWN)[0],
                 "download_bw_mbps": (SUPER_UP_DOWN if i in supers else STAKER_UP_DOWN)[1],
                 "country": node_country[i]}
                for i in range(n)
            ],
            "edges": [
                {"source": i, "target": j,
                 "latency_ms": lat(node_country[i], node_country[j])}
                for i in range(n) for j in range(n) if i != j
            ],
            "fanout_nodes": [],
            "meta": {
                "label": args.label,
                "seed": args.seed,
                "supernode_fraction": args.supernode_fraction,
                "supernodes": sorted(supers),
                "supernode_count": nsuper,
                "meshed": meshed,
                "isolated": isolated,
                "fallback_latency_ms": FALLBACK_LATENCY_MS,
                "infra_country": INFRA_COUNTRY,
                "infra_location": INFRA_LOCATION,
                "locations": {node_loc[i]: node_country[i] for i in range(n)},
            },
        }
        with open(args.topology_out, "w") as fh:
            json.dump(topo, fh, indent=2)
        sys.stderr.write(
            "topology: %s -- %d nodes, %d countries, %d supernodes "
            "(fraction %s, want round(%s x %d) = %d), seed %d\n"
            % (args.topology_out, n, len(set(node_country)), nsuper,
               args.supernode_fraction, args.supernode_fraction, n, nsuper,
               args.seed))


if __name__ == "__main__":
    main()
