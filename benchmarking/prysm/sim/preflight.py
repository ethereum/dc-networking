#!/usr/bin/env python3
"""Preflight gate for a generated Shadow run.

    ./preflight.py <data-dir> <sim.yaml> [reference-data-dir]

Every check reads the GENERATED artefacts -- data<N>/shadow.yaml,
data<N>/metadata/genesis.json, data<N>/metadata/config.yaml, data<N>/values.env
-- never the input config, because the input config is not what Shadow runs.

Run it after "ethshadow --gen-only" + tune-shadow-config.py and before shadow.
Exit status is the number of failed checks; every check prints what it read and
what it saw.  This is the standing gate for every rung of the ladder: the recipe
it enforces (peer cap 99, 5s..180s stagger, ~128 kB of transfer payload a block,
6 private blobs, GOMEMLIMIT 1700MiB, ledger + pprof) is frozen for the campaign.

The reference data dir is a known-good earlier run whose generated CL config
this one is diffed against; it is optional, and $PREFLIGHT_REF supplies it when
the argument is left off.  $SIM_BIN_DIR names the binary directory.

Pure Python: the file greps, md5 sums, binary string scan, diff and the disk/RAM
readings are all done in-process.  The only external processes are
spamoor-premine.py (check 2) and the spamoor binary's --help (check 9).
"""

import argparse
import datetime
import difflib
import glob
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import traceback

try:
    import yaml
except ImportError:
    sys.exit("pyyaml is required: pip install pyyaml")

FAILS = 0


def pas(msg):
    print(f"  PASS: {msg}")


def bad(msg):
    global FAILS
    print(f"  FAIL: {msg}")
    FAILS += 1


def hdr(msg):
    print()
    print(f"=== {msg} ===")


def show_grep(pattern, path):
    """What "run grep -E <pattern> <path>" printed: the command, then the
    matching lines, both indented."""
    print(f"  $ grep -E {pattern} {path}")
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError as exc:
        print(f"    grep: {path}: {exc.strerror}")
        return
    rx = re.compile(pattern)
    for line in lines:
        if rx.search(line):
            print(f"    {line}")


def load_yaml(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError) as exc:
        print(f"    (cannot read {path}: {exc})")
        return {}


def normal_diff(a, b):
    """GNU "diff" normal format over two lists of lines (newlines kept)."""

    def rng(start, end, empty):
        if empty:
            return str(start)
        if end - start == 1:
            return str(start + 1)
        return f"{start + 1},{end}"

    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
            None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        cmd = {"replace": "c", "delete": "d", "insert": "a"}[tag]
        out.append(f"{rng(i1, i2, tag == 'insert')}{cmd}"
                   f"{rng(j1, j2, tag == 'delete')}\n")
        for line in a[i1:i2]:
            out.append("< " + line)
        if tag == "replace":
            out.append("---\n")
        for line in b[j1:j2]:
            out.append("> " + line)
    return out


# ---------------------------------------------------------------- 1. forks
def check_forks(data, ref):
    hdr("1. fork keys in the generated CL config and values.env")
    cfg_path = f"{data}/metadata/config.yaml"
    show_grep(r"^(ELECTRA|FULU|GLOAS|HEZE)_FORK_(EPOCH|VERSION)", cfg_path)
    cfg = load_yaml(cfg_path)
    for key, want in (("ELECTRA_FORK_EPOCH", "0"), ("FULU_FORK_EPOCH", "0"),
                      ("GLOAS_FORK_EPOCH", "0"), ("HEZE_FORK_EPOCH", "0")):
        got = "" if key not in cfg else str(cfg[key]).replace(" ", "")
        if got == want:
            pas(f"{key}={got}")
        else:
            bad(f"{key}={got}, want {want}")
    show_grep(r"^export (HEZE_FORK_|AVAILABLE_ATTESTATION_DUE_BPS_HEZE"
              r"|GENESIS_TIMESTAMP|GENESIS_DELAY)", f"{data}/values.env")

    ref_cfg = f"{ref}/metadata/config.yaml"
    if not (ref and os.path.isfile(ref_cfg)):
        print(f"  (no reference dir '{ref or 'unset'}', skipping the diff)")
        return
    print(f"  $ diff {ref_cfg} {cfg_path}")
    try:
        with open(ref_cfg, encoding="utf-8", errors="replace") as fh:
            a = fh.readlines()
        with open(cfg_path, encoding="utf-8", errors="replace") as fh:
            b = fh.readlines()
        diff = normal_diff(a, b)
    except OSError as exc:
        diff = [f"diff: {exc.filename}: {exc.strerror}\n"]
    with open("/tmp/preflight-cfg.diff", "w", encoding="utf-8") as fh:
        fh.writelines(diff)
    if not diff:
        pas(f"CL config byte-identical to {ref} (known good)")
        return
    for line in diff:
        print(f"    {line.rstrip(chr(10))}")
    # The validator count moves with the rung. TARGET_COMMITTEE_SIZE is the
    # one v2 change (LADDER-PLAN, 2026-08-25): v1 reference dirs were made
    # before cl-config-goldfish.yaml carried the key at all.
    allowed = (r"MIN_GENESIS_ACTIVE_VALIDATOR_COUNT|TARGET_COMMITTEE_SIZE"
               r"|ATTESTATION_SUBNET_COUNT|SUBNETS_PER_NODE|subnets per node"
               r"|2\*\*6 \(= 64\) subnets")
    rx = re.compile(allowed)
    changed = [ln for ln in diff if ln[:1] in ("<", ">")]
    if any(not rx.search(ln) for ln in changed):
        bad(f"CL config differs from {ref} beyond {allowed}")
    else:
        pas(f"CL config differs from {ref} only in {allowed}")


# ------------------------------------------------------ 2. spamoor wallets
def check_premine(data, sim):
    hdr("2. spamoor root AND derived child wallets are in the EL genesis alloc")
    cmd = ["./spamoor-premine.py", sim, "--check", f"{data}/metadata/genesis.json"]
    print(f"  $ {' '.join(cmd)}")
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True)
        out, rc = proc.stdout, proc.returncode
    except OSError as exc:
        out, rc = f"{cmd[0]}: {exc.strerror}\n", 127
    for line in out.splitlines():
        print(f"    {line}")
    if rc == 0:
        pas("every spamoor wallet is premined")
    else:
        bad("spamoor wallets missing from the genesis alloc -- the private arm "
            "WILL stall on funding")


# --------------------------------------------------------- 3..8 the numbers
def check_numbers(data, sim):
    """Payload math, blob rate, endpoint sets, isolated ELs, hygiene, flags.

    Returns the number of failures; a crash in here counts as one failure and
    leaves the rest of the gate running, which is what the shell's separate
    python process did."""
    cfg = yaml.safe_load(open(sim))
    gen = json.load(open(f"{data}/metadata/genesis.json"))
    sh = yaml.safe_load(open(f"{data}/shadow.yaml"))

    fails = []

    def pas(m):
        print(f"  PASS: {m}")

    def bad(m):
        print(f"  FAIL: {m}")
        fails.append(m)

    gas_limit = int(gen["gasLimit"], 16)
    sched = gen["config"]["blobSchedule"]["amsterdam"]
    blob_max, blob_target = sched["max"], sched["target"]
    print(f"  generated EL genesis: gasLimit={gas_limit:,} "
          f"blobs target/max={blob_target}/{blob_max}")

    spammers = {n: c for n, c in cfg["ethereum"]["clients"].items()
                if c.get("type") == "spamoor"}

    # --- 3. payload-size math, from the calldata knob actually configured ---
    # The calldata floor on this chain is 21000 + 64 a byte.  Run 38 proved it
    # the hard way: geth rejected every 750,000-gas transaction with
    # "insufficient gas for floor data gas cost: gas 750000, minimum needed
    # 1069576", and 1069576 - 21000 is exactly 64 * 16384.  A geth --dev node
    # charges the EIP-7623 rate of 10 a token instead (674,410 for the same
    # transaction), so a dev-node measurement does NOT transfer -- both rates
    # are kept below and the larger wins.  TX_OVERHEAD and HEADER are block
    # bytes, which no fee rule touches: one such transaction made a
    # 17,152-byte block.
    TX_OVERHEAD, HEADER = 226, 542
    BAND = (112 * 1024, 160 * 1024)          # 128 KiB target, +/- 25 %

    def eoatx_gas(nbytes):
        zero = nbytes // 256
        nonzero = nbytes - zero
        tokens = zero + 4 * nonzero
        return max(21000 + 16 * nonzero + 4 * zero,   # standard
                   21000 + 10 * tokens,               # EIP-7623 floor
                   21000 + 64 * nbytes)               # this chain's floor

    for name, c in sorted(spammers.items()):
        if c.get("scenario") != "eoatx":
            continue
        extra = c.get("extra_args", "")
        m = re.search(r"--data\s+random:(\d+)", extra)
        if not m:
            bad(f"{name}: no --data random:N, payloads stay at the ~1 kB floor")
            continue
        nbytes = int(m.group(1))
        per_tx_gas = eoatx_gas(nbytes)
        gl = int(re.search(r"--gaslimit\s+(\d+)", extra).group(1))
        pending = int(c["max_pending"])
        # The block gas limit is what actually bounds the payload, not
        # max_pending.  Run 39 proved it: two consecutive isolated proposals
        # starved the meshed pool, spamoor reissued the stalled transfers on
        # fresh nonces, and every later block was gas-saturated at 26
        # transactions and 382 kB against a max_pending of 8. geth packs while
        # the remaining gas covers the next transaction's reservation, so
        # floor(limit / --gaslimit) is the ceiling.
        # geth packs against gas USED, not the reservation: run 40 put NINE
        # transfers in a 9.7 M block (9 x 1,069,576 = 9,626,184) even though
        # nine reservations would have been 10.35 M. Leave room for the blob
        # transactions sharing the block -- three of them at 21,000.
        fits = (gas_limit - 3 * 21000) // per_tx_gas
        n = min(fits, pending)
        payload = n * (nbytes + TX_OVERHEAD) + HEADER
        ceiling = fits * (nbytes + TX_OVERHEAD) + HEADER
        print(f"  {name}: {nbytes} B calldata, {per_tx_gas:,} gas/tx, reserves "
              f"{gl:,}; block limit {gas_limit:,} fits {fits} of them "
              f"(max_pending {pending}) -> payload ~{payload:,} B "
              f"({payload / 1024:.0f} KiB), hard ceiling {ceiling / 1024:.0f} KiB")
        if per_tx_gas > gl:
            bad(f"{name}: per-tx gas {per_tx_gas:,} over --gaslimit {gl:,}, "
                f"txs get rejected")
        if not BAND[0] <= ceiling <= BAND[1]:
            bad(f"{name}: a saturated block is {ceiling:,} B, outside the "
                f"{BAND[0]:,}-{BAND[1]:,} B band -- set ethereum.genesis.gaslimit "
                f"so floor(limit/{gl}) transfers land in the band")
        elif not BAND[0] <= payload <= BAND[1]:
            bad(f"{name}: expected payload {payload:,} B outside the band")
        else:
            pas(f"{name}: {n} transfers a block either way, payload "
                f"{payload / 1024:.0f} KiB, target 128 KiB")
        if "--rebroadcast 0" not in extra:
            bad(f"{name}: --rebroadcast 0 missing; the rebroadcast path reissues "
                f"a stalled transfer on a fresh nonce and inflates the pool")

    # --- 5/6. endpoint sets against the generated shadow.yaml ---------------
    ip2host = {h["ip_addr"]: n for n, h in sh["hosts"].items()}
    isolated, meshed, beacons = set(), set(), []
    for host, h in sh["hosts"].items():
        for p in h["processes"]:
            path, args = p["path"], p["args"]
            if path.rstrip("/").endswith("geth") and "--authrpc.port" in args:
                (isolated if "--maxpeers 0" in args else meshed).add(host)
            if "prysm-beacon" in path:
                beacons.append((host, p))

    targets, blobs_at = {}, {}
    for host, h in sh["hosts"].items():
        for p in h["processes"]:
            if "spamoor" not in p["path"]:
                continue
            a = p["args"]
            hit = {ip2host.get(ip, ip) for ip in re.findall(r"-h http://([\d.]+):", a)}
            targets[host] = hit
            # An arm's blobs land only in the pools it posts to.  A geth with
            # --maxpeers 0 never hears the meshed arm's transactions, so a
            # block's blob count is the sum over the arms aimed at ITS pool,
            # not a network average.
            side = re.search(r"--sidecars\s+(\d+)", a)
            pend = re.search(r"--max-pending\s+(\d+)", a)
            if not (side and pend and a.split()[0].endswith("blobs")):
                continue
            # Steady state is max_pending transactions in the pool; it drifts
            # to three or four for a slot or two after a proposer that could
            # not include them, which is why the cap of 9 has to have headroom
            # over the target of 6. Run 41 measured 2 transactions a block at
            # max_pending 2.
            for el in hit:
                blobs_at[el] = blobs_at.get(el, 0) + int(side.group(1)) * int(pend.group(1))

    print(f"  meshed geths ({len(meshed)}): {sorted(meshed)}")
    print(f"  isolated geths --maxpeers 0 ({len(isolated)}): {sorted(isolated)}")
    if isolated & meshed:
        bad(f"hosts in both classes: {sorted(isolated & meshed)}")
    elif not isolated:
        bad("no geth carries --maxpeers 0; there is no private class")
    else:
        pas(f"--maxpeers 0 on exactly {len(isolated)} geths, disjoint from the "
            f"{len(meshed)} meshed")

    priv_union = set()
    for host, hosts in sorted(targets.items()):
        print(f"  spammer {host} -> {sorted(hosts)}")
        if hosts <= isolated:
            priv_union |= hosts
            if len(hosts) != 1:
                bad(f"{host}: private spammer targets {len(hosts)} ELs; one "
                    f"instance per isolated EL is what keeps its wallet nonces "
                    f"gap-free")
        elif not hosts <= meshed:
            bad(f"{host}: target set straddles the meshed/isolated split: "
                f"{sorted(hosts)}")
    if priv_union == isolated:
        pas(f"private spammers cover every isolated EL exactly: {sorted(priv_union)}")
    else:
        bad(f"isolated ELs with no private spammer: {sorted(isolated - priv_union)}")

    # --- 4. blobs a block, per EL pool --------------------------------------
    for el in sorted(meshed | isolated):
        n = blobs_at.get(el, 0)
        cls = "isolated" if el in isolated else "meshed"
        print(f"  {el} ({cls}): {n} blobs waiting in its pool")
        if n > blob_max:
            bad(f"{el}: {n} blobs over the {blob_max} cap, transactions get dropped")
        elif n != blob_target:
            bad(f"{el}: {n} blobs a block, target is {blob_target}")
    if all(blobs_at.get(el) == blob_target for el in meshed | isolated):
        pas(f"every EL pool holds {blob_target} blobs a block, cap {blob_max}: "
            f"a block carries {blob_target} whichever class proposes it, and the "
            f"{len(isolated)}/{len(meshed | isolated)} isolated share of proposals "
            f"makes that fraction of the blobs private")

    # --- 7. shadow.yaml hygiene: syscall model, memory manager, stagger -----
    # True since the fallback fired: run 44 (flag absent) froze at sim 43.5s;
    # 44b ran clean.
    mus = sh.get("general", {}).get("model_unblocked_syscall_latency")
    if mus is True:
        pas("model_unblocked_syscall_latency: true (fallback fired on run 44)")
    else:
        bad(f"model_unblocked_syscall_latency is {mus!r}; the ladder runs with true")
    mm = sh.get("experimental", {}).get("use_memory_manager")
    if mm is False:
        pas("experimental.use_memory_manager: false")
    else:
        bad(f"experimental.use_memory_manager is {mm!r}, must be false "
            f"(it SIGSEGVs Go 1.26 binaries at exec)")

    starts = {}
    for host, p in beacons:
        starts.setdefault(str(p.get("start_time")), []).append(host)
    secs = sorted(int(s.rstrip("s")) for s in starts)
    span = secs[-1] - secs[0] if secs else 0
    print(f"  beacon start times: {sorted(starts, key=lambda s: int(s.rstrip('s')))}")
    # LADDER-PLAN 4.1 fixes the window at 5s..180s, so every client is up at
    # least 120 s before genesis and the boot phase is comparable across rungs.
    # Runs 38-42 used 5s..11s at 10 nodes; the check accepts any window that
    # starts at 5s and finishes by 180s, and both shapes pass.
    if secs and secs[0] == 5 and secs[-1] <= 180:
        pas(f"stagger {secs[0]}s..{secs[-1]}s ({span}s total) over "
            f"{len(beacons)} beacons, inside the 5s..180s window")
    else:
        bad(f"stagger runs {secs[0] if secs else '?'}s..{secs[-1] if secs else '?'}s; "
            f"the campaign fixes the window at 5s..180s")

    # --- 8. beacon flags and memory ceiling ---------------------------------
    # One value on every rung (LADDER-PLAN 4.1): per-node heap tracks validators
    # per node, which is 100 at every N, so the ceiling does not move with N.
    want_mem = "1700MiB"
    missing_env, missing_flag, wrong_peers, wrong_mem = [], [], [], []
    for host, p in beacons:
        env = p.get("environment", {}) or {}
        if "GOMEMLIMIT" not in env:
            missing_env.append(host)
        elif env["GOMEMLIMIT"] != want_mem:
            wrong_mem.append((host, env["GOMEMLIMIT"]))
        a = p["args"]
        if "--goldfish-vote-ledger" not in a or "--pprof" not in a:
            missing_flag.append(host)
        caps = re.findall(r"--p2p-max-peers\s+(\d+)", a)
        if caps != ["99"]:
            wrong_peers.append((host, caps))
    if missing_env:
        bad(f"{len(missing_env)} beacons without GOMEMLIMIT: {missing_env[:5]}")
    elif wrong_mem:
        bad(f"{len(wrong_mem)} beacons with GOMEMLIMIT != {want_mem}: {wrong_mem[:5]}")
    else:
        pas(f"GOMEMLIMIT={want_mem} on all {len(beacons)} beacons")
    if missing_flag:
        bad(f"{len(missing_flag)} beacons without --goldfish-vote-ledger/--pprof: "
            f"{missing_flag[:5]}")
    else:
        pas(f"--goldfish-vote-ledger and --pprof on all {len(beacons)} beacons")
    if wrong_peers:
        bad(f"{len(wrong_peers)} beacons without exactly one --p2p-max-peers 99: "
            f"{wrong_peers[:5]}")
    else:
        pas(f"--p2p-max-peers 99, once, on all {len(beacons)} beacons")

    print(f"\n  python checks: {len(fails)} failed")
    return min(len(fails), 100)


# --------------------------------------------------------------- 9. binaries
def md5sum(path):
    """One "md5sum <path>" output line."""
    try:
        h = hashlib.md5()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return f"{h.hexdigest()}  {path}"
    except OSError as exc:
        return f"md5sum: {path}: {exc.strerror}"


def has_marker(path, marker):
    """What "strings -a <path> | grep -cF -- <marker>" answered: the markers are
    all longer than the 4-character run strings(1) needs, so a byte search over
    the whole file finds exactly what strings would have printed."""
    needle = marker.encode()
    try:
        with open(path, "rb") as fh:
            tail = b""
            while True:
                chunk = fh.read(1 << 22)
                if not chunk:
                    return False
                if needle in tail + chunk:
                    return True
                tail = chunk[-len(needle):]
    except OSError:
        return False


def check_binaries(sim, bin_dir):
    hdr("9. binaries are the intended build")
    # Whatever binaries THIS config names, not a hardcoded run number.
    clients = load_yaml(sim).get("ethereum", {}).get("clients", {})

    def executable(kind):
        got = next((v["executable"] for v in clients.values()
                    if v.get("type") == kind), "")
        if not got:
            print(f"  (no '{kind}' client in {sim})", file=sys.stderr)
        return got

    beacon = executable("prysm")
    validator = executable("prysm_vc")
    spamoor = f"{bin_dir}/spamoor"
    print(f"  $ md5sum {beacon} {validator} {spamoor}")
    for path in (beacon, validator, spamoor):
        print(f"    {md5sum(path)}")
    # The beacon binary carries no git hash, so the check is for the marker
    # strings each ledger commit introduced. All of these must be present:
    #   goldfish-vote-ledger  the flag that gates every ledger line
    #   kzgCommitmentCount    the data-column line
    #   payloadBytes          the payload-envelope line
    #   PTC vote              the PTC-vote arrival line
    for marker in ("goldfish-vote-ledger", "kzgCommitmentCount", "payloadBytes",
                   "PTC vote"):
        if has_marker(beacon, marker):
            pas(f"beacon binary has the '{marker}' marker")
        else:
            bad(f"beacon binary is missing '{marker}' -- wrong commit")
    try:
        out = subprocess.run([spamoor, "eoatx", "--help"], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True).stdout
    except OSError as exc:
        out = f"{spamoor}: {exc.strerror}"
    for flag in ("--seed", "--data", "--gaslimit"):
        if f"{flag} " in out:
            pas(f"spamoor supports {flag}")
        else:
            bad(f"spamoor has no {flag}")


# --------------------------------------------------------------- 10. resources
def check_resources(data):
    hdr("10. disk and RAM headroom")
    usage = shutil.disk_usage(".")
    avail_g = math.ceil(usage.free / 2 ** 30)
    print(f"  disk at .: {math.ceil(usage.total / 2 ** 30)}G total, {avail_g}G available")
    free_g = 0
    with open("/proc/meminfo", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("MemAvailable:"):
                free_g = int(line.split()[1]) // (1024 * 1024)
    print(f"  memory: {free_g}G available")
    nodes = len(glob.glob(f"{data}/node*"))
    # Beacons dominate; GOMEMLIMIT is the per-beacon ceiling.
    need_g = nodes * 2
    if avail_g > 50:
        pas(f"disk {avail_g}G free")
    else:
        bad(f"only {avail_g}G disk free")
    if free_g > need_g:
        pas(f"RAM {free_g}G available, {nodes} nodes want about {need_g}G")
    else:
        bad(f"RAM {free_g}G available, {nodes} nodes want about {need_g}G")


def main():
    ap = argparse.ArgumentParser(
        description="Preflight gate for a generated Shadow run.")
    ap.add_argument("data", help="the generated data dir (dataN)")
    ap.add_argument("sim", help="the sim yaml the run was generated from")
    ap.add_argument("ref", nargs="?", default=os.environ.get("PREFLIGHT_REF", ""),
                    help="known-good data dir to diff the CL config against "
                         "(default $PREFLIGHT_REF, skipped when unset)")
    args = ap.parse_args()
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    global FAILS
    print(f"preflight {datetime.datetime.now().astimezone().isoformat(timespec='seconds')}"
          f"  data={args.data} sim={args.sim} ref={args.ref}")

    check_forks(args.data, args.ref)
    check_premine(args.data, args.sim)
    hdr("3-8. payload math, blob rate, endpoint sets, isolated ELs, hygiene, flags")
    try:
        FAILS += check_numbers(args.data, args.sim)
    except Exception:                    # one broken artefact is one failure,
        traceback.print_exc()            # not the end of the gate
        FAILS += 1
    check_binaries(args.sim, os.environ.get("SIM_BIN_DIR", "bin"))
    check_resources(args.data)

    hdr("RESULT")
    if FAILS == 0:
        print("PREFLIGHT PASSED -- clear to launch")
    else:
        print(f"PREFLIGHT FAILED -- {FAILS} check(s) failed, do not launch")
    return FAILS


if __name__ == "__main__":
    sys.exit(main())
