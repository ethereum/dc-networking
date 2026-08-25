#!/usr/bin/env python3
"""Replace the generator's CL genesis with a Heze one built by prysmctl.

    PRYSMCTL=path/to/prysmctl SIM_YAML=sim-100nodes-r1.yaml \\
        ./make-heze-genesis.py <data-dir> <num-validators>

Run this after "ethshadow --gen-only" and before Shadow.

Binaries come from the environment: PRYSMCTL and GETH default to the names on
PATH, SIM_YAML to sim.yaml.  --dry-run prints the external commands and touches
nothing.

Why. ethshadow builds the CL genesis with ethpandaops'
eth-genesis-state-generator. That tool tops out at a Gloas-shaped state, and
even its Gloas state does not match this fork's container ("failed to unmarshal
state, detected fork=gloas: invalid ssz encoding"). Genesis is Heze here and
nothing upgrades into Heze - runtime/interop builds the Heze state directly - so
prysmctl has to make it.

The validator keystores come from eth2-val-tools over the mnemonic, so the
genesis registry must hold exactly those pubkeys in that order. We therefore
feed prysmctl a deposit_data.json for the same mnemonic and index range rather
than its deterministic interop keys.

The EL genesis is NOT rewritten. ethshadow has already run "geth init" for every
node by the time this script runs, so the block prysmctl hashes has to be the
block geth already stored. sim.yaml therefore sets GENESIS_TIMESTAMP to the real
genesis instant and GENESIS_DELAY to 0, which is the only header field prysmctl
would otherwise change. The script asserts the two hashes match before it writes
anything.

Only docker, prysmctl and geth are external; the json plumbing the shell version
did with jq/base64/xxd is done in-process.
"""

import argparse
import base64
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile


def die(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def run(cmd, dry, capture=False, merge=False):
    """subprocess.run(check=True); under --dry-run print the command instead.

    capture takes stdout, merge folds stderr into it (the shell's 2>&1);
    otherwise both are left on the terminal, as they were in the shell."""
    if dry:
        print("$ " + shlex.join(cmd))
        return ""
    if capture:
        return subprocess.run(
            cmd, check=True, stdout=subprocess.PIPE, text=True,
            stderr=subprocess.STDOUT if merge else None).stdout
    subprocess.run(cmd, check=True)
    return ""


def grep1(pattern, path):
    """First "grep -oP" match in a file, or exit 1 the way set -e did."""
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = re.search(pattern, line)
            if m:
                return m.group(1)
    die(f"{path}: no match for {pattern}")


def val(name, values_env):
    """Last  export NAME="..."  value in values.env."""
    got = None
    with open(values_env, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(rf'^export {name}="(.*)"$', line.rstrip("\n"))
            if m:
                got = m.group(1)
    if got is None:
        die(f"{values_env}: no export {name}=")
    return got


def main():
    ap = argparse.ArgumentParser(
        description="Build the Heze CL genesis for a generated data dir.")
    ap.add_argument("data_dir", help="the generated data dir (dataN)")
    ap.add_argument("num_validators")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the docker/prysmctl/geth commands, run nothing")
    args = ap.parse_args()
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    dry = args.dry_run
    data_dir = args.data_dir
    num_validators = args.num_validators
    meta = f"{data_dir}/metadata"
    prysmctl = os.environ.get("PRYSMCTL", "prysmctl")
    geth = os.environ.get("GETH", "geth")
    # SIM_YAML names the run's config; only the generator image is read out of it.
    sim_yaml = os.environ.get("SIM_YAML", "sim.yaml")
    image = grep1(r"generator_image: (.*)", sim_yaml)

    values_env = f"{data_dir}/values.env"
    mnemonic = val("EL_AND_CL_MNEMONIC", values_env)
    genesis_ts = val("GENESIS_TIMESTAMP", values_env)
    genesis_delay = val("GENESIS_DELAY", values_env)
    fork_version = val("GENESIS_FORK_VERSION", values_env)
    print(f"genesis_ts={genesis_ts} delay={genesis_delay} "
          f"fork_version={fork_version}")

    # geth's ToBlock falls back to params.InitialBaseFee when baseFeePerGas is
    # absent, which is what "geth init" already did; prysmctl refuses to guess,
    # so write that same value in. The header is unchanged.
    with open(f"{meta}/genesis.json", encoding="utf-8") as fh:
        el_genesis = json.load(fh)
    if el_genesis.get("baseFeePerGas") in (None, False) and not dry:
        os.chmod(f"{meta}/genesis.json",
                 os.stat(f"{meta}/genesis.json").st_mode | 0o200)
        el_genesis["baseFeePerGas"] = "0x3b9aca00"
        with open(f"{meta}/genesis.json.tmp", "w", encoding="utf-8") as fh:
            json.dump(el_genesis, fh, indent=2)
            fh.write("\n")
        os.replace(f"{meta}/genesis.json.tmp", f"{meta}/genesis.json")

    # eth2-val-tools names the deposit amount "value"; prysmctl wants "amount".
    deposits = run([
        "docker", "run", "--rm", "-i", "--entrypoint", "eth2-val-tools", image,
        "deposit-data",
        "--as-json-list",
        "--source-min", "0", "--source-max", num_validators,
        "--fork-version", fork_version,
        "--withdrawal-credentials-type", "0x00",
        "--validators-mnemonic", mnemonic,
        "--withdrawals-mnemonic", mnemonic,
    ], dry, capture=True)
    if not dry:
        keys = ("pubkey", "withdrawal_credentials", "signature", "deposit_data_root")
        out = [dict([(k, d.get(k)) for k in keys] + [("amount", d.get("value"))])
               for d in json.loads(deposits)]
        with open(f"{meta}/deposit_data.json", "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2)
            fh.write("\n")

        # prysm's file writer refuses to overwrite a file that is not already
        # 0600, and the generator ran as root in docker with a 0644 umask.
        os.chmod(f"{meta}/genesis.ssz", 0o600)

    run([
        prysmctl, "testnet", "generate-genesis",
        "--fork", "heze",
        "--num-validators", num_validators,
        "--chain-config-file", f"{meta}/config.yaml",
        "--deposit-json-file", f"{meta}/deposit_data.json",
        "--geth-genesis-json-in", f"{meta}/genesis.json",
        "--genesis-time", genesis_ts,
        "--genesis-time-delay", genesis_delay,
        "--output-ssz", f"{meta}/genesis.ssz",
        "--output-json", f"{meta}/genesis-state.json",
    ], dry)

    # Cross-check: the eth1 block the CL genesis names must be the block geth
    # stored at init. A mismatch shows up at runtime only as "Unable to retrieve
    # proof-of-stake genesis block data ... not found", and the chain never
    # starts.
    if dry:
        check_dir = "<mktemp -d -p /var/tmp genesis-check-XXXXXX>"
    else:
        with open(f"{meta}/genesis-state.json", encoding="utf-8") as fh:
            cl_hash = base64.b64decode(json.load(fh)["latest_block_hash"]).hex()
        check_dir = tempfile.mkdtemp(prefix="genesis-check-", dir="/var/tmp")
    init = run([geth, "--datadir", check_dir, "init", f"{meta}/genesis.json"],
               dry, capture=True)
    if dry:
        return
    matches = re.findall(r"Successfully wrote genesis state.*hash=([0-9a-f.]+)",
                         init)
    if not matches:
        die("geth init printed no genesis block hash")
    el_hash = "\n".join(matches)
    print(f"CL genesis eth1 block hash: 0x{cl_hash}")
    print(f"EL genesis block hash:      {el_hash} (geth abbreviates)")
    head = el_hash.split("..")[0]
    tail = el_hash.rsplit("..", 1)[-1]
    if not cl_hash.startswith(head) or not cl_hash.endswith(tail):
        print("MISMATCH: the CL genesis names a block geth did not create.",
              file=sys.stderr)
        print("ethshadow ran 'geth init' before this script; the EL genesis must",
              file=sys.stderr)
        print("already have its final timestamp when it does. See sim.yaml.",
              file=sys.stderr)
        sys.exit(1)

    print(f"wrote {meta}/genesis.ssz "
          f"({os.path.getsize(f'{meta}/genesis.ssz')} bytes)")


if __name__ == "__main__":
    main()
