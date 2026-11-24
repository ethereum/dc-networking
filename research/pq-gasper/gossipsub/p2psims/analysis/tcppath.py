#!/usr/bin/env python3
"""TCP timeouts, resends, spurious timeouts, Eifel undos, cwnd and ssthresh by path type (sender class -> receiver class)
and slot, from a Shadow run with the tcpd diagnostics (LNXBUF_LOG=1).
usage: tcppath.py RUNDIR [CONFIGDIR]   (reads RUNDIR/shadow-tcpd.log.gz, shadow.log or shadow.log.gz, and
CONFIGDIR/run.json; CONFIGDIR defaults to RUNDIR)
Resends: the sent-resend counter (txretx) when the build logs it (rtt2), else the queued-resend counter (retx), which
equals the sent count in builds without the undo."""
import collections, gzip, json, os, statistics, sys

run = sys.argv[1]
cfg = sys.argv[2] if len(sys.argv) > 2 else run
rj = json.load(open(f"{cfg}/run.json"))
nodes = rj["nodes"]
NS = rj.get("slots", 20)  # slots in the run (20 or 50)
LAST, E = NS - 2, NS - 1  # per-slot deltas cover slots 2..LAST; cwnd and ssthresh compared at slots 2 and E
XS = range(2, LAST + 1)
hostcls = {f"n{n['id']:04d}": n["cls"] for n in nodes}
ipcls = {n["ip"]: n["cls"] for n in nodes}
C = ["cloud", "50x25", "50x15"]
G = lambda a, b: ("1G" if a == "cloud" else "home") + "->" + ("1G" if b == "cloud" else "home")
GROUPS = ["1G->1G", "1G->home", "home->1G", "home->home"]
UNSET = 2**31 - 1  # Reno's initial ssthresh (INT32_MAX)
path = next(f"{run}/{n}" for n in ("shadow-tcpd.log.gz", "shadow.log", "shadow.log.gz") if os.path.exists(f"{run}/{n}"))
opener = gzip.open if path.endswith(".gz") else open


def simsec(line):
    i = line.find("[INFO]")
    t = line[i - 19:i - 1]  # HH:MM:SS.nnnnnnnnn
    return int(t[0:2]) * 3600 + int(t[3:5]) * 60 + int(t[6:8])


def peercls(ip):
    return ipcls.get(".".join(str((ip >> k) & 255) for k in (0, 8, 16, 24)), "?")


# snapshot fields: state, txdata, retx (queued resends), txretx (sent resends, -1 if not logged), cwnd, ssthresh,
# timeouts, rtxq (retransmit queue bytes), tmr (retransmit timer armed), dropped (resends dropped by an undo)
ST, TX, RQ, RS, CW, SS, TO, RTXQ, TMR, DROP, CWV = range(11)  # CWV: ACKs whose cwnd increase rtt5 skipped
snap = {}  # (host, ptr, peer ip) -> {bin: fields}
grp = {}  # same key -> path type
cur = {}  # (host, ptr) -> current key, for the lines without a peer
to = collections.Counter()  # (path type, slot, first of an episode) -> timeouts
aat = collections.Counter()  # (path type, spurious) -> first ACKs of new data after a timeout
undo = []  # (path type, spurious, cwnd before, after, ssthresh before, after, saved cwnd, dropped, rearmed)
ssr = []  # rtt5 restarts after idle: (path type, slot, cwnd before, after, idle ms, RTO ms, ssthresh after, phase after)
fr = []  # rtt5 fast-recovery entries: (path type, slot, from ss|ca, ACKs advancing snd_una between the 3 duplicates)
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
            grp[key] = G(hostcls.get(host, "?"), peercls(int(d["peer"])))
        cur[(host, ptr)] = key
        g = lambda f: int(d.get(f, -1))
        snap.setdefault(key, {})[int(d["bin"])] = (g("state"), g("txdata"), g("retx"), g("txretx"), g("cwnd"),
                                                    g("ssthresh"), g("timeouts"), g("rtxq"), g("tmr"), g("dropped"),
                                                    g("cwvskip"))
        continue
    key = cur.get((host, ptr))
    pg = grp.get(key, "?")
    if kind == "timeout":
        s = simsec(line)
        to[(pg, (s - 30) // 12 if s >= 30 else -1, tok[7] == "1")] += 1
    elif kind == "acked-after-timeout":
        aat[(pg, tok[5] == "1")] += 1
    elif kind == "undo":
        d = dict(zip(tok[2::2], tok[3::2]))
        j = tok.index("cwnd")
        undo.append((pg, tok[3] == "1", int(tok[j + 1]), int(tok[j + 3]), int(tok[j + 5]), int(tok[j + 7]),
                     int(d.get("saved", 0)), int(d.get("dropped", 0)), int(d.get("rearm", 0))))
    elif kind == "ssr":  # rtt5 restart after idle: idle ms, RTO ms, cwnd before / after, ssthresh before / after,
        s = simsec(line)  # and (since 11:3x Nov 10) Reno's phase before / after
        ssr.append((pg, (s - 30) // 12 if s >= 30 else -1, int(tok[7]), int(tok[8]), int(tok[3]), int(tok[5]),
                    int(tok[11]), tok[14] if len(tok) > 14 else None))
    elif kind == "fr":  # rtt5 fast-recovery entry: from ss|ca, ACKs advancing snd_una between the 3 duplicate ACKs
        s = simsec(line)
        fr.append((pg, (s - 30) // 12 if s >= 30 else -1, tok[3], int(tok[5])))

sent = any(v[RS] >= 0 for s in snap.values() for v in s.values())
ri = RS if sent else RQ
print(f"== {run} ({os.path.basename(path)}): {len(snap)} TCP endpoints with snapshots; resends counted as "
      f"{'sent (txretx)' if sent else 'queued (retx; equals sent without the undo)'}")
dp, rt, dpb, rtb, act = (collections.Counter() for _ in range(5))
for key, s in snap.items():
    a, b = hostcls.get(key[0], "?"), peercls(int(key[2]))
    bs = sorted(s)
    for x, y in zip(bs, bs[1:]):
        if y != x + 1 or not 2 <= x <= LAST or s[y][TX] < s[x][TX]:
            continue
        ddp, drt = s[y][TX] - s[x][TX], s[y][ri] - s[x][ri]
        dp[(a, b)] += ddp
        rt[(a, b)] += drt
        dpb[(grp[key], x)] += ddp
        rtb[(grp[key], x)] += drt
        act[(grp[key], x)] += ddp > 0
print(f"resent data packets per 1,000 data packets, slots 2-{LAST}, by sender -> receiver class (data packets):")
print("  " + ", ".join(f"{a}->{b} {1000.0 * rt[(a, b)] / max(1, dp[(a, b)]):.1f} ({dp[(a, b)] / 1e6:.2f}M)"
                       for a in C for b in C))
for g in GROUPS:
    D = sum(dpb[(g, x)] for x in XS)
    R = sum(rtb[(g, x)] for x in XS)
    print(f"  {g:10s} {1000.0 * R / max(1, D):6.2f} per 1,000; per slot 2-{LAST}: "
          + " ".join(f"{1000.0 * rtb[(g, x)] / max(1, dpb[(g, x)]):.1f}" for x in XS))
print(f"timeouts per slot by path type (all | first of an episode), slots 0-{E}:")
for g in GROUPS:
    print(f"  {g:10s} " + " ".join(f"{to[(g, b, False)] + to[(g, b, True)]}|{to[(g, b, True)]}" for b in range(0, NS)))
print(f"per slot 2-{LAST} by path type: first timeouts per 1,000 data packets | endpoints sending data | data packets "
      "per sending endpoint:")
for g in GROUPS:
    D = sum(dpb[(g, x)] for x in XS)
    F = sum(to[(g, x, True)] for x in XS)
    print(f"  {g:10s} all {1000.0 * F / max(1, D):.2f}: "
          + " ".join(f"{1000.0 * to[(g, x, True)] / max(1, dpb[(g, x)]):.2f}" for x in XS))
    print(f"  {'':10s} endpoints " + " ".join(f"{act[(g, x)]}" for x in XS))
    print(f"  {'':10s} packets/endpoint " + " ".join(f"{dpb[(g, x)] / max(1, act[(g, x)]):.0f}" for x in XS))
if NS > 20:  # long runs: 10-slot blocks (2-9, 10-19, ..., 40-LAST)
    BL = [(2, 9)] + [(a, min(a + 9, LAST)) for a in range(10, LAST + 1, 10)]
    print("per 10-slot block by path type: first timeouts per 1,000 data packets | resent data packets per 1,000:")
    for g in GROUPS:
        cells = []
        for a, b in BL:
            D = sum(dpb[(g, x)] for x in range(a, b + 1))
            F = sum(to[(g, x, True)] for x in range(a, b + 1))
            R = sum(rtb[(g, x)] for x in range(a, b + 1))
            cells.append(f"{a}-{b} {1000.0 * F / max(1, D):.2f} | {1000.0 * R / max(1, D):.2f}")
        print(f"  {g:10s} " + "; ".join(cells))
    print("cwnd p50/p90 (segments) by path type at the end of each block (first snapshot in the next slot; established endpoints "
          "with > 100 data packets sent; Shadow has no slow-start restart after idle):")
    for g in GROUPS:
        cells = []
        for a, b in BL:
            cw = sorted(s[b + 1][CW] for key, s in snap.items()
                        if grp[key] == g and b + 1 in s and s[b + 1][ST] == 4 and s[b + 1][TX] > 100)
            cells.append(f"{a}-{b} {cw[len(cw) // 2]}/{cw[9 * len(cw) // 10]} (n={len(cw)})" if cw else f"{a}-{b} -")
        print(f"  {g:10s} " + "; ".join(cells))
print("timeout episodes ended by an ACK of new data, spurious share (TSecr before the timeout), by path type: "
      + ", ".join(f"{g} {aat[(g, True)] + aat[(g, False)]} "
                  f"({100.0 * aat[(g, True)] / max(1, aat[(g, True)] + aat[(g, False)]):.1f} %)" for g in GROUPS))
if undo:
    print(f"Eifel undo checks {len(undo)}: judged spurious and undone {sum(u[1] for u in undo)}, genuine (reduction "
          f"kept) {sum(not u[1] for u in undo)}; timer re-armed after an undo {sum(u[8] for u in undo)}")
    for g in GROUPS:
        us = [u for u in undo if u[1] and u[0] == g]
        if us:
            med = lambda i: statistics.median(u[i] for u in us)
            ssa = [u[5] for u in us if u[5] < UNSET]
            print(f"  {g:10s} undone {len(us)}: cwnd {med(2):.0f} -> {med(3):.0f} (saved {med(6):.0f}; after < saved: "
                  f"{sum(u[3] < u[6] for u in us)}); ssthresh before p50 {med(4):.0f}, after unset in "
                  f"{100.0 * sum(u[5] >= UNSET for u in us) / len(us):.0f} % (else p50 "
                  f"{statistics.median(ssa) if ssa else 0:.0f}); resends dropped {sum(u[7] for u in us)}")
if any(v[TMR] >= 0 for s in snap.values() for v in s.values()):
    allv = [v for s in snap.values() for v in s.values()]
    print(f"stall check: snapshots with retransmit-queue data and no retransmit timer: "
          f"{sum(v[RTXQ] > 0 and v[TMR] == 0 for v in allv)} of {len(allv)}")
    last = [s[max(s)] for s in snap.values()]
    q, r, dr = sum(v[RQ] for v in last), sum(v[RS] for v in last), sum(max(0, v[DROP]) for v in last)
    print(f"resend accounting at each endpoint's last snapshot: queued {q} = sent {r} + dropped by an undo {dr} + "
          f"residual {q - r - dr} (still queued or freed at close)")
print(f"cwnd and ssthresh of the same endpoints at slots 2 and {E} (established at both, > 100 data packets by slot 2), "
      "by path type: cwnd p25/p50/p75; ssthresh reduced share and p50 of the reduced:")
for g in GROUPS:
    m = [(s[2], s[E]) for key, s in snap.items() if grp[key] == g and 2 in s and E in s and s[2][ST] == 4
         and s[E][ST] == 4 and s[2][TX] > 100]
    if not m:
        continue
    out = f"  {g:10s} n={len(m):5d}"
    for j, lab in ((0, "slot 2"), (1, f"slot {E}")):
        cw = sorted(x[j][CW] for x in m)
        out += f" | {lab}: cwnd {cw[len(cw) // 4]}/{cw[len(cw) // 2]}/{cw[3 * len(cw) // 4]}"
        if m[0][j][SS] >= 0:
            red = sorted(x[j][SS] for x in m if x[j][SS] < UNSET)
            out += f", ssthresh reduced {100.0 * len(red) / len(m):.0f} % (p50 {red[len(red) // 2] if red else '-'})"
    tos = sorted(x[1][TO] - x[0][TO] for x in m)
    print(out + f" | timeouts between: mean {sum(tos) / len(tos):.1f}, p90 {tos[9 * len(tos) // 10]}")
q = lambda xs, f: sorted(xs)[int(f * (len(xs) - 1))]
print(f"cwnd over the run (snapshots of established endpoints with > 100 data packets sent, slots 2-{E}), by path type: "
      "p50 / p90 (snapshots):")
for g in GROUPS:
    cw = [v[CW] for key, s in snap.items() if grp[key] == g for b, v in s.items()
          if 2 <= b <= E and v[ST] == 4 and v[TX] > 100]
    if cw:
        print(f"  {g:10s} {q(cw, .5)} / {q(cw, .9)} ({len(cw)})")
if ssr:
    print(f"restart after idle (rtt5), by path type: events per slot 2-{LAST} | cwnd before -> after, p50 (p90) | "
          "idle / RTO p50 ms:")
    for g in GROUPS:
        ev = [e for e in ssr if e[0] == g]
        if ev:
            per = collections.Counter(e[1] for e in ev)
            print(f"  {g:10s} total {len(ev)}: " + " ".join(str(per[x]) for x in XS)
                  + f" | {q([e[2] for e in ev], .5)} ({q([e[2] for e in ev], .9)}) -> {q([e[3] for e in ev], .5)}"
                  f" ({q([e[3] for e in ev], .9)}) | {q([e[4] for e in ev], .5)} / {q([e[5] for e in ev], .5)}")
if any(v[CWV] > 0 for s in snap.values() for v in s.values()):
    lastv = {key: s[max(s)] for key, s in snap.items()}
    print("ACKs whose cwnd increase window validation skipped (rtt5), each endpoint's last snapshot, by path type: "
          + ", ".join(f"{g} {sum(max(0, v[CWV]) for key, v in lastv.items() if grp[key] == g)}" for g in GROUPS))
if ssr and ssr[0][7] is not None:
    def ssp50(v):
        if not v:
            return "-"
        m = q(v, .5)
        return f"{'unset' if m >= UNSET else m} (unset {100.0 * sum(x >= UNSET for x in v) / len(v):.0f} %)"
    print(f"restarts that leave cwnd < ssthresh, the share of those in slow start right after, and ssthresh p50 after "
          f"the restart at slots 2 and {LAST} (unset = never reduced), by path type:")
    for g in GROUPS + ["all"]:
        ev = [e for e in ssr if g == "all" or e[0] == g]
        if not ev:
            continue
        lo = [e for e in ev if e[3] < e[6]]
        print(f"  {g:10s} {len(ev)} restarts, cwnd < ssthresh in {100.0 * len(lo) / len(ev):.1f} %, of those in slow "
              f"start {100.0 * sum(e[7] == 's' for e in lo) / max(1, len(lo)):.1f} % (phase after: "
              + ", ".join(f"{p} {sum(e[7] == p for e in lo)}" for p in "scf")
              + f") | ssthresh slot 2 {ssp50([e[6] for e in ev if e[1] == 2])}, slot {LAST} "
              f"{ssp50([e[6] for e in ev if e[1] == LAST])}")
    print(f"ssthresh p50 after a restart per slot 2-{LAST} by path type ('u' = unset, never reduced):")
    for g in GROUPS:
        cells = []
        for x in XS:
            v = [e[6] for e in ssr if e[0] == g and e[1] == x]
            cells.append("-" if not v else ("u" if q(v, .5) >= UNSET else str(q(v, .5))))
        print(f"  {g:10s} " + " ".join(cells))
if fr:
    print(f"fast-recovery entries per 1,000 data packets, slots 2-{LAST}, by path type: all | consecutive (no ACK "
          "advancing snd_una between the 3 duplicate ACKs) | accumulated; entries from slow start; entries:")
    for g in GROUPS:
        D = sum(dpb[(g, x)] for x in XS)
        ev = [e for e in fr if e[0] == g and e[1] in XS]
        con = sum(e[3] == 0 for e in ev)
        print(f"  {g:10s} {1000.0 * len(ev) / max(1, D):.3f} | {1000.0 * con / max(1, D):.3f} | "
              f"{1000.0 * (len(ev) - con) / max(1, D):.3f}; from slow start {sum(e[2] == 'ss' for e in ev)}; "
              f"entries {len(ev)}")
