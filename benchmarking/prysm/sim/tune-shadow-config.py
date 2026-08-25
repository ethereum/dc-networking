#!/usr/bin/env python3
"""Tune a generated Shadow data dir before launch.

    ./tune-shadow-config.py <data-dir>
    ./tune-shadow-config.py <data-dir> --targets 16 --stagger 5 120 --dry-run

Runs BETWEEN ``ethshadow --gen-only`` and the shadow launch, and edits only the
generated config -- never a finished run.  Three edits, each independently
switchable, each reported as a count so a run log records what was applied:

1. Every prysm-beacon process gets ``GOMEMLIMIT`` in its process environment.
   Go's default is no heap ceiling, so a beacon under a burst grows until the
   kernel reclaims; the soft limit is the spike backstop.  ``GOGC`` is left
   alone by default, which matters: run 30 set ``GOGC=off`` with a 700MiB
   limit, the limit landed *below* the 861MB startup live heap, and with no
   other trigger every beacon collected back-to-back at 100% CPU -- a 20x
   slowdown.  Routine collection belongs to GOGC's default pacing; the limit
   only catches the spike.  Pass ``--gogc`` to set it anyway.  The validator
   and geth are left alone.

2. Host start times are staggered over a window (default 5s..120s), spread
   deterministically by host index so a rerun of this script produces the same
   file.  Genesis is at simulated 05:00, so every client is up long before the
   chain starts; what this buys is a startup that climbs instead of 256 hosts
   all calling into the kernel at the same simulated instant.  The bootnode and
   the monitoring host keep the earliest slots -- everything else dials them.

3. The generated prometheus scrape config keeps ``--targets`` beacon targets,
   evenly spaced by index, instead of one per node.  Sample metrics survive;
   scraping every process at 256 nodes does not.

Nothing is deleted: the original ``shadow.yaml`` and ``prometheus.yaml`` are
copied to ``*.pre-tune`` first (unless one is already there, which is left
untouched so the first original always wins).
"""

import argparse
import os
import re
import shutil
import sys

try:
    import yaml
except ImportError:
    sys.exit("pyyaml is required: pip install pyyaml")

BEACON_RE = re.compile(r"prysm-beacon")


def backup(path):
    """Keep the first original next to the file; never overwrite a backup."""
    keep = path + ".pre-tune"
    if os.path.exists(path) and not os.path.exists(keep):
        shutil.copy2(path, keep)
        return keep
    return None


def host_index(name):
    """node12 -> 12, node0boot -> 0, node129monitoring -> 129."""
    m = re.search(r"(\d+)", name)
    return int(m.group(1)) if m else 0


def is_beacon(proc):
    return bool(BEACON_RE.search(proc.get("path", "")))


def tune_shadow_yaml(run_dir, memlimit, gogc, lo, hi, dry_run):
    path = os.path.join(run_dir, "shadow.yaml")
    with open(path) as fh:
        cfg = yaml.safe_load(fh)
    hosts = cfg["hosts"]

    # Client hosts are the ones that actually run a beacon; the bootnode and the
    # monitoring host are infrastructure and start first regardless.
    clients = sorted((n for n, h in hosts.items()
                      if any(is_beacon(p) for p in h.get("processes", []))),
                     key=host_index)
    infra = [n for n in hosts if n not in set(clients)]

    env_set = 0
    for name in clients:
        for proc in hosts[name].get("processes", []):
            if is_beacon(proc):
                env = proc.setdefault("environment", {})
                env["GOMEMLIMIT"] = memlimit
                if gogc is not None:
                    env["GOGC"] = gogc
                env_set += 1

    # Deterministic spread: host i of n lands at lo + (hi-lo)*i/(n-1).
    staggered = 0
    span = max(len(clients) - 1, 1)
    for i, name in enumerate(clients):
        when = "%ds" % round(lo + (hi - lo) * i / span)
        for proc in hosts[name].get("processes", []):
            proc["start_time"] = when
        staggered += 1

    # Infrastructure keeps whatever start time the config gave it. ethshadow
    # already starts the bootnode at 0s and the monitoring host early, and a
    # traffic generator's start time is deliberate: it waits for genesis. An
    # earlier version of this function rewrote every non-client host to 0s/1s,
    # which dragged the spammers back to the boot storm -- at a 180 s stagger
    # the ELs are not up yet, and spamoor exits on its first chainid probe
    # ("context deadline exceeded"). Never move a process earlier than asked.

    _ = infra  # kept for the count in the report; start times are left alone
    first_client = "%ds" % lo
    last_client = "%ds" % hi
    if not dry_run:
        backup(path)
        with open(path, "w") as fh:
            yaml.safe_dump(cfg, fh, sort_keys=False, default_flow_style=False)
    return {"clients": len(clients), "infra": len(infra), "env_set": env_set,
            "staggered": staggered, "first": first_client, "last": last_client}


def tune_prometheus(run_dir, keep, dry_run):
    """Keep `keep` evenly spaced targets in every scrape job."""
    hits = []
    for root, _dirs, files in os.walk(run_dir):
        for fn in files:
            if fn in ("prometheus.yaml", "prometheus.yml"):
                hits.append(os.path.join(root, fn))
    result = []
    for path in hits:
        with open(path) as fh:
            cfg = yaml.safe_load(fh)
        changed = False
        for job in cfg.get("scrape_configs", []) or []:
            for static in job.get("static_configs", []) or []:
                targets = static.get("targets") or []
                if len(targets) > keep:
                    step = len(targets) / keep
                    static["targets"] = [targets[min(int(i * step), len(targets) - 1)]
                                         for i in range(keep)]
                    result.append((path, job.get("job_name"), len(targets), keep))
                    changed = True
        if changed and not dry_run:
            backup(path)
            with open(path, "w") as fh:
                yaml.safe_dump(cfg, fh, sort_keys=False, default_flow_style=False)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", help="generated data dir")
    ap.add_argument("--memlimit", default="1500MiB", help="GOMEMLIMIT for beacons")
    ap.add_argument("--gogc", default=None,
                    help="GOGC for beacons; unset by default, which leaves Go's "
                         "own pacing in charge (see the module docstring)")
    ap.add_argument("--stagger", nargs=2, type=int, default=(5, 120),
                    metavar=("LO", "HI"), help="client start window, seconds")
    ap.add_argument("--targets", type=int, default=16,
                    help="prometheus targets to keep per job")
    ap.add_argument("--no-env", action="store_true", help="skip the GOMEMLIMIT edit")
    ap.add_argument("--no-stagger", action="store_true", help="skip the start spread")
    ap.add_argument("--no-prometheus", action="store_true", help="skip the scrape trim")
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args()

    if not os.path.isdir(args.run_dir):
        sys.exit("no such run dir: %s" % args.run_dir)

    lo, hi = args.stagger
    if args.no_stagger:
        lo = hi = 5
    info = tune_shadow_yaml(args.run_dir, args.memlimit, args.gogc, lo, hi,
                            args.dry_run or (args.no_env and args.no_stagger))
    print("shadow.yaml: %d client hosts, %d infra hosts" % (info["clients"], info["infra"]))
    if not args.no_env:
        print("  GOMEMLIMIT=%s%s on %d beacon processes"
              % (args.memlimit,
                 " GOGC=%s" % args.gogc if args.gogc else " (GOGC left at Go's default)",
                 info["env_set"]))
    if not args.no_stagger:
        print("  start_time staggered %s .. %s across %d hosts (infra untouched)"
              % (info["first"], info["last"], info["staggered"]))

    if not args.no_prometheus:
        trims = tune_prometheus(args.run_dir, args.targets, args.dry_run)
        if trims:
            for path, job, was, now in trims:
                print("prometheus: %s job %s: %d -> %d targets"
                      % (os.path.relpath(path, args.run_dir), job, was, now))
        else:
            print("prometheus: nothing to trim")
    if args.dry_run:
        print("(dry run -- no files written)")


if __name__ == "__main__":
    main()
