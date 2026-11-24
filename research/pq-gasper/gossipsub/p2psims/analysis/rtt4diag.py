#!/usr/bin/env python3
"""rtt4 checks from the tcpd lines of a run with LNXBUF_LOG=1, by path type (data sender class -> receiver class):
SRTT minus the configured RTT; the rtt4 build's echo counters (ACKs of new data whose TSecr equals the TSval of the
first segment they newly acknowledge, counted at the data sender); echo updates by duplicates that Linux would not
make (counted at the data receiver); and the share of first timeouts (backoff 1) that start within 1 s after a
spurious timeout was undone on the same connection. Runs from builds without the echo counters print only the rest.
usage: rtt4diag.py RUNDIR [CONFIGDIR]   (reads RUNDIR/shadow-tcpd.log.gz, shadow.log or shadow.log.gz)"""
import collections, gzip, json, os, sys

run = sys.argv[1]
cfg = sys.argv[2] if len(sys.argv) > 2 else run
rj = json.load(open(f"{cfg}/run.json"))
NS = rj.get("slots", 20)
hostcls = {f"n{n['id']:04d}": n["cls"] for n in rj["nodes"]}
ipcls = {n["ip"]: n["cls"] for n in rj["nodes"]}
G = lambda a, b: ("1G" if a == "cloud" else "home") + "->" + ("1G" if b == "cloud" else "home")
GROUPS = ["1G->1G", "1G->home", "home->1G", "home->home"]
path = next(f"{run}/{n}" for n in ("shadow-tcpd.log.gz", "shadow.log", "shadow.log.gz") if os.path.exists(f"{run}/{n}"))
opener = gzip.open if path.endswith(".gz") else open


def simsec(line):
    i = line.find("[INFO]")
    t = line[i - 19:i - 1]  # HH:MM:SS.nnnnnnnnn
    return int(t[0:2]) * 3600 + int(t[3:5]) * 60 + float(t[6:])


def peercls(ip):
    return ipcls.get(".".join(str((ip >> k) & 255) for k in (0, 8, 16, 24)), "?")


EC = ["echoeq", "echonew", "echoold", "echona", "echozero"]
grp, cur, last = {}, {}, {}
diff = collections.defaultdict(list)  # path type -> SRTT - configured RTT (ms), snapshots in slots 2..NS-2
lastundo = {}
first, within = collections.Counter(), collections.Counter()
for line in opener(path, "rt", errors="replace"):
    k = line.find("] tcpd ")
    if k < 0:
        continue
    tok = line[k + 7:].split()
    kind, ptr = tok[0], tok[1]
    i = line.find("] [n")
    host = line[i + 3:i + 8]
    if kind == "snap":
        d = dict(zip(tok[2::2], tok[3::2]))
        key = (host, ptr, d["peer"])
        if key not in grp:
            grp[key] = (hostcls.get(host, "?"), peercls(int(d["peer"])))
        cur[(host, ptr)] = key
        last[key] = d
        if 2 <= int(d["bin"]) <= NS - 2 and d.get("state") == "4" and int(d.get("samples", 0)) > 0:
            diff[G(*grp[key])].append(int(d["srtt"]) - int(d["cfgrtt"]))
        continue
    key = cur.get((host, ptr))
    if kind == "undo" and tok[3] == "1":
        lastundo[(host, ptr)] = simsec(line)
    elif kind == "timeout" and tok[7] == "1":
        g = G(*grp[key]) if key in grp else "?"
        first[g] += 1
        t = lastundo.get((host, ptr))
        within[g] += t is not None and simsec(line) - t < 1.0

q = lambda v, p: sorted(v)[min(len(v) - 1, int(p * len(v)))] if v else float("nan")
print(f"== {run} ({os.path.basename(path)}): {len(last)} TCP endpoints")
print(f"SRTT - configured RTT (ms), snapshots of established connections with samples, slots 2-{NS - 2}: "
      "p10 / p50 / p90 / p99 | snapshots")
for g in GROUPS:
    v = diff[g]
    print(f"  {g:10s} {q(v, .1):5} / {q(v, .5):5} / {q(v, .9):5} / {q(v, .99):5} | {len(v)}")
ech, dup = collections.Counter(), collections.Counter()
have = False
for key, d in last.items():
    a, b = grp[key]
    if "echoeq" in d:
        have = True
        for f in EC:
            ech[(G(a, b), f)] += int(d[f])
        for f in ("tsduppend", "tsdupold"):
            dup[(G(b, a), f)] += int(d.get(f, 0))  # counted at the receiver: data flows peer -> host
if have:
    print("ACKs of new data at the data sender (each endpoint's last snapshot): total | TSecr equal to / newer than / "
          "older than the TSval of the latest transmission of the first segment they newly acknowledge | that "
          "segment's resend waiting to leave | TSecr 0")
    for g in GROUPS + ["all"]:
        c = {f: sum(ech[(x, f)] for x in GROUPS) if g == "all" else ech[(g, f)] for f in EC}
        n = max(1, sum(c.values()))
        print(f"  {g:10s} {sum(c.values()):9d} | " + " / ".join(f"{100 * c[f] / n:6.2f}" for f in EC[:3])
              + f" % | {100 * c['echona'] / n:5.2f} % | {100 * c['echozero'] / n:5.2f} %")
    print("echo updates by duplicate data segments, at the data receiver (count, per 1,000 ACKs of new data): at the "
          "last departed ACK number (Linux makes these too) | entirely below it (Linux's tcp_sequence discards these "
          "first)")
    for g in GROUPS:
        n = max(1, sum(ech[(g, f)] for f in EC))
        print(f"  {g:10s} {dup[(g, 'tsduppend')]:7d} ({1000 * dup[(g, 'tsduppend')] / n:.3f}) | "
              f"{dup[(g, 'tsdupold')]:7d} ({1000 * dup[(g, 'tsdupold')] / n:.3f})")
F, W = sum(first.values()), sum(within.values())
print(f"first timeouts (backoff 1) {F}; started within 1 s after a spurious undo on the same connection: "
      f"{100 * W / max(1, F):.1f} % (" + ", ".join(f"{g} {100 * within[g] / max(1, first[g]):.1f} % of {first[g]}"
                                                    for g in GROUPS) + ")")
