#!/usr/bin/env python3
"""TCP diagnostics from a Shadow run with the diag builds (LNXBUF_LOG=1): RTO ratchet per slot, RTT samples, SRTT vs
the configured path RTT, the RTO formula, timeouts, retransmissions and socket buffers.
usage: tcpdiag.py RUNDIR [LABEL]   (reads RUNDIR/shadow.log or shadow.log.gz)"""
import collections, gzip, os, re, statistics, sys

run = sys.argv[1]
label = sys.argv[2] if len(sys.argv) > 2 else run
HOST = re.compile(r"\[(n\d+):")
SNAP = re.compile(r"tcpd snap (\S+) bin (-?\d+) peer (\d+) state (\d+) srtt (-?\d+) rttvar (-?\d+) rto (\d+) backoff (\d+) "
                  r"samples (\d+) timeouts (\d+) spurious (\d+) retx (\d+) txdata (\d+) cfgrtt (\d+) sndbuf (\d+) rcvbuf (\d+)"
                  r"(?: cwnd (\d+))?(?: ssthresh (\d+) est (\d) srtt8us (-?\d+) mdevus (-?\d+) mdevmaxus (-?\d+) rttvarus (-?\d+) "
                  r"txretx (\d+) undochecks (\d+) undone (\d+) dropped (\d+) retxafterundo (\d+))?")
TO = re.compile(r"tcpd timeout (\S+) rto (\d+) -> (\d+) backoff (\d+) srtt (-?\d+)")
SIMT = re.compile(r"\] (\d\d):(\d\d):(\d\d)\.\d+ \[INFO\]")
AAT = re.compile(r"tcpd acked-after-timeout (\S+) echo (\d) spurious (\d) srtt (-?\d+) rttvar (-?\d+) rto (\d+) expect (-?\d+)")
INIT = re.compile(r"lnxbuf initial send (\d+) receive (\d+)")

snaps = collections.defaultdict(dict)  # conn -> bin -> snapshot tuple
timeouts, aat, init = [], [], collections.Counter()
tobin, tofirst = collections.Counter(), collections.Counter()  # timeouts per slot (all; first of an episode)
LOG = next(f"{run}/{n}" for n in ("shadow-tcpd.log.gz", "shadow.log", "shadow.log.gz")
           if os.path.exists(f"{run}/{n}"))
UNDO = re.compile(r"tcpd undo (\S+) spurious (\d) retxtime (\d) cwnd (\d+) -> (\d+) ssthresh (\d+) -> (\d+) saved (\d+) dropped (\d+)")
undos = []
for line in (gzip.open if LOG.endswith(".gz") else open)(LOG, "rt", errors="replace"):
    if "tcpd " not in line and "lnxbuf initial" not in line:
        continue
    h = HOST.search(line)
    host = h.group(1) if h else "?"
    m = SNAP.search(line)
    if m:
        g = m.groups()
        conn = (host, g[0], g[2])
        snaps[conn][int(g[1])] = tuple(-1 if x is None else int(x) for x in g[1:2] + g[3:])
        continue
    m = UNDO.search(line)
    if m:
        undos.append(tuple(int(x) for x in m.groups()[1:]))
        continue
    m = TO.search(line)
    if m:
        timeouts.append((int(m.group(2)), int(m.group(3)), int(m.group(4))))
        t = SIMT.search(line)
        if t:
            s = int(t.group(1)) * 3600 + int(t.group(2)) * 60 + int(t.group(3))
            tobin[(s - 30) // 12 if s >= 30 else -1] += 1
            if int(m.group(4)) == 1:
                tofirst[(s - 30) // 12 if s >= 30 else -1] += 1
        continue
    m = AAT.search(line)
    if m:
        aat.append(tuple(int(x) for x in m.groups()[1:]))
        continue
    m = INIT.search(line)
    if m:
        init[(int(m.group(1)), int(m.group(2)))] += 1

# snapshot tuple: bin, state, srtt, rttvar, rto, backoff, samples, timeouts, spurious, retx, txdata, cfgrtt, sndbuf, rcvbuf
B, ST, SRTT, VAR, RTO, BO, SAM, TOS, SPU, RETX, TX, CFG, SND, RCV = range(14)
# rtt2 builds append: cwnd, ssthresh, est (1 = Linux estimator), srtt8us, mdevus, mdevmaxus, rttvarus, txretx (sent
# resends), undochecks, undone, dropped, retxafterundo; -1 where a build does not log them
CWND, SS, EST, S8, MD, MDX, RV, TXR, UC, UD, DR, RAU = range(14, 26)
print(f"== {label}: {len(snaps)} connections with snapshots, {len(timeouts)} timeouts")
print("share of connections with RTO >= 2 / 4 / 8 / 16 s per slot (active in the slot | all established, carried forward):")
last = {}
for b in range(0, 20):
    act = [s[b] for s in snaps.values() if b in s]
    for c, s in snaps.items():
        if b in s:
            last[c] = s[b]
    est = [v for v in last.values() if v[ST] == 4]
    f = lambda xs, t: 100.0 * sum(x[RTO] >= t for x in xs) / max(1, len(xs))
    print(f"  slot {b:2d}: active {len(act):5d}: " + " / ".join(f"{f(act, t):5.1f}" for t in (2000, 4000, 8000, 16000))
          + f" % | established {len(est):5d}: " + " / ".join(f"{f(est, t):5.1f}" for t in (2000, 4000, 8000, 16000)) + " %")
end = [max(s.items())[1] for s in snaps.values()]
EDGES = (300, 500, 1000, 2000, 4000, 8000, 16000, 10**9)
def bk(vals):  # counts per RTO band (ms): < 300, 300-500, ..., >= 16000
    c = collections.Counter(next(e for e in EDGES if v < e) for v in vals)
    return " ".join(f"<{e}:{c[e]}" if e < 10**9 else f">=16000:{c[e]}" for e in EDGES)
print("RTO at each connection's last snapshot: max", max((x[RTO] for x in end), default=0), "ms;",
      bk(x[RTO] for x in end))
if timeouts:
    print("timeouts per slot (all | first of an episode, backoff 1), warm-up first:",
          " ".join(f"{tobin[b]}|{tofirst[b]}" for b in range(-1, 21)))
    print(f"timeouts: RTO before {bk(o for o, _, _ in timeouts)}; "
          f"share with RTO before >= 2 s: {100.0 * sum(o >= 2000 for o, _, _ in timeouts) / len(timeouts):.1f} %; "
          f"backoff after: {dict(sorted(collections.Counter(min(b, 5) for _, _, b in timeouts).items()))}")
data = [x for x in end if x[TX] > 0]
print(f"connections that sent data: {len(data)}; with RTT samples: {sum(x[SAM] > 0 for x in data)} "
      f"({100.0 * sum(x[SAM] > 0 for x in data) / max(1, len(data)):.1f} %)")
tot = lambda k: sum(x[k] for x in data)
if any(x[TXR] >= 0 for x in data):
    print(f"sent resends (txretx): {tot(TXR)} = {100.0 * tot(TXR) / max(1, tot(TX)):.3f} % of data packets; queued resends "
          f"(retx) {tot(RETX)}; undo checks {tot(UC)}, undone {tot(UD)}, resends dropped before sending {tot(DR)}, resends of an "
          f"undone range sent after the undo {tot(RAU)}")
if undos:
    sp = [u for u in undos if u[0]]
    md = lambda xs: statistics.median(xs) if xs else 0
    print(f"undo lines: {len(undos)} checks, {len(sp)} spurious (of them {sum(1 - u[1] for u in sp)} with nothing resent yet); "
          f"cwnd before -> after p50 {md([u[2] for u in sp]):.0f} -> {md([u[3] for u in sp]):.0f} (saved {md([u[6] for u in sp]):.0f}); "
          f"after >= saved in {sum(u[3] >= u[6] for u in sp)}; ssthresh before -> after p50 {md([u[4] for u in sp]):.0f} -> "
          f"{md([u[5] for u in sp]):.0f}, never reduced after the undo (2^31-1) {sum(u[5] >= 2**31 - 1 for u in sp)}; dropped "
          f"{sum(u[7] for u in sp)}")
print(f"per data-carrying connection: data packets {tot(TX) / max(1, len(data)):.0f}, retransmissions "
      f"{tot(RETX) / max(1, len(data)):.2f} ({100.0 * tot(RETX) / max(1, tot(TX)):.3f} % of data packets), timeouts "
      f"{tot(TOS) / max(1, len(data)):.3f}, spurious timeouts {tot(SPU)} of {tot(TOS)}; connections with >= 1 timeout "
      f"{sum(x[TOS] > 0 for x in data)}")
sam = [x for x in end if x[SAM] > 0 and x[CFG] > 0]
if sam:
    r = sorted(x[SRTT] / x[CFG] for x in sam)
    q = lambda p: r[min(len(r) - 1, int(p * len(r)))]
    print(f"SRTT / configured RTT ({len(sam)} connections): p10 {q(0.1):.2f}, median {q(0.5):.2f}, p90 {q(0.9):.2f}, "
          f"max {r[-1]:.2f}; within +-20 %: {100.0 * sum(0.8 <= v <= 1.2 for v in r) / len(r):.1f} %; "
          f"largest SRTT {max(x[SRTT] for x in sam)} ms vs largest configured RTT {max(x[CFG] for x in sam)} ms")
    for lo, hi in ((0, 10), (10, 100), (100, 10**6)):
        g = sorted(x[SRTT] / x[CFG] for x in sam if lo <= x[CFG] < hi)
        if g:
            print(f"  configured RTT {lo}-{hi} ms: {len(g)} connections, median {g[len(g) // 2]:.2f}, "
                  f"within +-20 % {100.0 * sum(0.8 <= v <= 1.2 for v in g) / len(g):.1f} %, below 0.8 "
                  f"{100.0 * sum(v < 0.8 for v in g) / len(g):.1f} %, above 1.2 {100.0 * sum(v > 1.2 for v in g) / len(g):.1f} %")
    ex = sorted(x[SRTT] - x[CFG] for x in sam)
    big = max(cfgmax := max(x[CFG] for x in sam), 0)
    print(f"  SRTT - configured RTT (ms): p50 {ex[len(ex) // 2]}, p90 {ex[int(0.9 * len(ex))]}, p99 {ex[int(0.99 * len(ex))]}, "
          f"max {ex[-1]}; connections with SRTT above the largest configured RTT ({big} ms): {sum(x[SRTT] > big for x in sam)}")
    allsn = [(c, x) for c, s in snaps.items() for x in s.values() if x[SAM] > 0 and x[CFG] > 0]
    c, x = max(allsn, key=lambda cx: cx[1][SRTT])
    print(f"  largest SRTT in any snapshot: {x[SRTT]} ms (configured {x[CFG]} ms, host {c[0]}, slot {x[B]}); snapshots with "
          f"SRTT > {big} ms: {sum(y[SRTT] > big for _, y in allsn)} of {len(allsn)}")
    ok = [x for s in snaps.values() for x in s.values() if x[SAM] > 0 and x[BO] == 0]
    exp = lambda x: min(120000, max(200, x[SRTT] + max(4 * x[VAR], 200)))
    rfc = [x for x in ok if x[EST] != 1]
    if rfc:
        print(f"RTO = SRTT + max(4 RTTVAR, 200 ms) in snapshots without backoff: {sum(x[RTO] == exp(x) for x in rfc)} of {len(rfc)}")
    lin = [x for s in snaps.values() for x in s.values() if x[EST] == 1 and x[S8] > 0 and x[BO] == 0]
    if lin:
        expl = lambda x: max(200, min(120000, (x[S8] // 8 + x[RV] + 999) // 1000))
        bad = [x for x in lin if x[RTO] != expl(x)]
        print(f"Linux estimator: RTO = SRTT + rttvar (us, rounded up to ms, <= 120 s) in snapshots without backoff: "
              f"{len(lin) - len(bad)} of {len(lin)}; rttvar >= 200 ms in {sum(x[RV] >= 200000 for x in lin)}; "
              f"mdev_max <= rttvar in {sum(x[MDX] <= x[RV] for x in lin)}")
        r4 = sorted(x[RV] / max(1, x[S8] // 8) for x in lin)
        print(f"  RTO / SRTT p10/p50/p90 {sorted(x[RTO] * 1000 / max(1, x[S8] // 8) for x in lin)[len(lin) // 10]:.2f}/"
              f"{sorted(x[RTO] * 1000 / max(1, x[S8] // 8) for x in lin)[len(lin) // 2]:.2f}/"
              f"{sorted(x[RTO] * 1000 / max(1, x[S8] // 8) for x in lin)[9 * len(lin) // 10]:.2f}; "
              f"rttvar ms p50/p90/p99 {sorted(x[RV] for x in lin)[len(lin) // 2] / 1000:.0f}/"
              f"{sorted(x[RV] for x in lin)[9 * len(lin) // 10] / 1000:.0f}/{sorted(x[RV] for x in lin)[99 * len(lin) // 100] / 1000:.0f}")
if aat:
    print(f"first ACK of new data after a timeout: {len(aat)}; RTO back at SRTT + max(4 RTTVAR, 200 ms): "
          f"{sum(a[4] == max(200, a[5]) for a in aat)}; with a timestamp echo {sum(a[0] for a in aat)}; spurious {sum(a[1] for a in aat)}")
print("initial buffers (send, receive) at the first RTT sample:", dict(init))
print(f"largest buffers in snapshots: send {max((x[SND] for s in snaps.values() for x in s.values()), default=0)}, "
      f"receive {max((x[RCV] for s in snaps.values() for x in s.values()), default=0)} B; "
      f"first snapshot per connection: send <= 131,072 in {sum(min(s.items())[1][SND] <= 131072 for s in snaps.values())}, "
      f"receive <= 174,760 in {sum(min(s.items())[1][RCV] <= 174760 for s in snaps.values())} of {len(snaps)}")
