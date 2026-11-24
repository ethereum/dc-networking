#!/usr/bin/env python3
"""rtt6 (CUBIC) checks from a Shadow run with the tcpd diagnostics (coordinator 01:1x Nov 11).
usage: rtt6diag.py RUNDIR [CONFIGDIR]   (reads RUNDIR/shadow-tcpd.log.gz, shadow.log or shadow.log.gz and
CONFIGDIR/run.json; CONFIGDIR defaults to RUNDIR)
Prints by path type (sender class -> receiver class): the share of data packets released with cwnd >= ssthresh,
HyStart exits by test, CUBIC epochs with K, TX_START events and epoch shifts, congestion-avoidance growth per round
trip; then K against cbrt((W_max - cwnd) / 0.4), the logged targets against W_max + 0.4 (t - K)^3, the logged epoch
shifts against min(epoch + idle, now), and up to three traces of cwnd against the target."""
import collections, gzip, json, os, statistics, sys

run = sys.argv[1]
cfg = sys.argv[2] if len(sys.argv) > 2 else run
rj = json.load(open(f"{cfg}/run.json"))
hostcls = {f"n{n['id']:04d}": n["cls"] for n in rj["nodes"]}
ipcls = {n["ip"]: n["cls"] for n in rj["nodes"]}
G = lambda a, b: ("1G" if a == "cloud" else "home") + "->" + ("1G" if b == "cloud" else "home")
GROUPS = ["1G->1G", "1G->home", "home->1G", "home->home"]
path = next(f"{run}/{n}" for n in ("shadow-tcpd.log.gz", "shadow.log", "shadow.log.gz") if os.path.exists(f"{run}/{n}"))
opener = gzip.open if path.endswith(".gz") else open


def peercls(ip):
    return ipcls.get(".".join(str((ip >> k) & 255) for k in (0, 8, 16, 24)), "?")


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(q * len(v)))] if v else float("nan")


last = {}  # (host, ptr, peer) -> (bin, fields) of the latest snapshot
grp, cur = {}, {}
hys = []  # (path, test, cwnd, ssthresh, dmin, curr, thr, rnd, ackdelay)
eps = []  # (path, cwnd, lastmax, K, origin, dmin)
tr = collections.defaultdict(list)  # (host, ptr, epoch) -> [(now, t, K, origin, target, cwnd, cnt, tcpcwnd, lastmax)]
trpath = {}
txs = []  # (delta, before, after, now)
# rtt6 counters: the latest intact value of each, per endpoint. The first rtt6 build appended them to the 'snap' line,
# whose end the 500-byte log message buffer cut (every snapshot lost 60-140 characters); the rebuilt rtt6 logs them on
# a 'cubsnap' line of their own. txfl and txca are only taken together.
F6 = ("txfl", "txca", "cub", "hstrain", "hsdelay", "epochs", "txstart", "txshift", "rounds", "rndover", "rndoveracked",
      "rndmax")
c6 = {}  # (host, ptr, peer) -> {field: (bin, value)}
ncut = nsnap = 0
for line in opener(path, "rt", errors="replace"):
    k = line.find("] tcpd ")
    if k < 0:
        continue
    tok = line[k + 7:].split()
    kind, ptr = tok[0], tok[1]
    if kind not in ("snap", "cubsnap", "hys", "cubep", "cubtr", "txs"):
        continue
    i = line.find("] [n")
    host = line[i + 3:i + 8]
    if kind in ("snap", "cubsnap"):
        if "...<truncated" in line:
            ncut += 1
        d = {k: v for k, v in zip(tok[2::2], tok[3::2]) if v.lstrip("-").isdigit()}  # drops a value cut by the log buffer
        key = (host, ptr, d["peer"])
        b = int(d["bin"])
        if kind == "snap":
            nsnap += 1
            if key not in grp:
                grp[key] = G(hostcls.get(host, "?"), peercls(int(d["peer"])))
            cur[(host, ptr)] = key
            if key not in last or b >= last[key][0]:
                last[key] = (b, d)
        cc = c6.setdefault(key, {})
        pair = "txfl" in d and "txca" in d
        for f in F6:
            if f in d and (pair or f not in ("txfl", "txca")) and (f not in cc or b >= cc[f][0]):
                cc[f] = (b, int(d[f]))
        continue
    pg = grp.get(cur.get((host, ptr)), "?")
    d = dict(zip(tok[2::2], tok[3::2]))
    if kind == "hys":
        hys.append((pg, d["test"], int(d["cwnd"]), int(d["ssthresh"]), int(d["dmin"]), int(d["curr"]), int(d["thr"]),
                    int(d["rnd"]), int(d["ackdelay"])))
    elif kind == "cubep":
        eps.append((pg, int(d["cwnd"]), int(d["lastmax"]), int(d["K"]), int(d["origin"]), int(d["dmin"])))
    elif kind == "cubtr":
        tr[(host, ptr, int(d["epoch"]))].append((int(d["now"]), int(d["t"]), int(d["K"]), int(d["origin"]),
                                                 int(d["target"]), int(d["cwnd"]), int(d["cnt"]), int(d["tcpcwnd"]),
                                                 int(d["lastmax"])))
        trpath[(host, ptr, int(d["epoch"]))] = pg
    elif kind == "txs":
        txs.append((int(tok[3]), int(tok[5]), int(tok[6]), int(tok[8])))

print(f"== {run} ({os.path.basename(path)}): {len(last)} TCP endpoints with snapshots")
S = collections.defaultdict(collections.Counter)
rmax = collections.defaultdict(int)
stale = collections.Counter()  # endpoints whose latest intact value of a counter predates their latest snapshot
for key, (b, d) in last.items():
    g = grp[key]
    cc = c6.get(key, {})
    for f in ("txfl", "txca", "hstrain", "hsdelay", "epochs", "txstart", "txshift", "rounds", "rndover", "rndoveracked"):
        S[g][f] += cc.get(f, (0, 0))[1]
        if cc.get(f, (b - 1, 0))[0] < b:
            stale[f] += 1
    S[g]["n"] += 1
    rmax[g] = max(rmax[g], cc.get("rndmax", (0, 0))[1])
cub = any(cc.get("cub", (0, 0))[1] for cc in c6.values())
print(f"snapshot lines cut by the log buffer: {ncut:,} of {nsnap:,}; endpoints whose counter comes from an earlier"
      f" snapshot or is missing: " + ", ".join(f"{f} {stale[f]}" for f in ("txfl", "txca", "hstrain", "hsdelay",
                                                                          "epochs", "txstart", "txshift", "rounds")))
print(f"CUBIC on: {cub}")
print("data packets released with cwnd >= ssthresh (snapshot counters, to each endpoint's last snapshot):")
tf = tc = 0
for g in GROUPS:
    s = S[g]
    tf, tc = tf + s["txfl"], tc + s["txca"]
    print(f"  {g:10s} {s['txca']:>11,} of {s['txfl']:>11,} = {100 * s['txca'] / max(1, s['txfl']):5.1f} %"
          f"   ({s['n']} endpoints)")
print(f"  {'all':10s} {tc:>11,} of {tf:>11,} = {100 * tc / max(1, tf):5.1f} %")
if not cub:
    sys.exit(0)

print("HyStart exits (tcpd hys lines; both tests can fire on one ACK): train / delay, endpoints with an exit,"
      " cwnd at exit p50/p90")
for g in GROUPS:
    h = [x for x in hys if x[0] == g]
    tn = sum(1 for x in h if x[1] == "train")
    dn = sum(1 for x in h if x[1] == "delay")
    cw = [x[2] for x in h]
    print(f"  {g:10s} train {tn:>6,}  delay {dn:>6,}  (snapshot counters {S[g]['hstrain']:,} / {S[g]['hsdelay']:,}),"
          f" cwnd at exit p50/p90 {pct(cw, .5)}/{pct(cw, .9)}")
dl = [x for x in hys if x[1] == "delay"]
if dl:
    ex = [(x[5] - x[4]) / 1000 for x in dl]
    th = [(x[6] - x[4]) / 1000 for x in dl]
    print(f"  delay exits: curr_rtt - delay_min p10/p50/p90 ms {pct(ex, .1):.1f}/{pct(ex, .5):.1f}/{pct(ex, .9):.1f}"
          f" (threshold {pct(th, .5):.1f} ms at p50); delay_min p50 {pct([x[4] for x in dl], .5) / 1000:.1f} ms")
tl = [x for x in hys if x[1] == "train"]
if tl:
    print(f"  train exits: round time p50 {pct([x[7] for x in tl], .5) / 1000:.1f} ms against threshold p50"
          f" {pct([x[6] for x in tl], .5) / 1000:.1f} ms; ack delay p50 {pct([x[8] for x in tl], .5)} us;"
          f" delay_min p50 {pct([x[4] for x in tl], .5) / 1000:.1f} ms")

print("CUBIC epochs (tcpd cubep lines): count, with W_max > cwnd (concave start), K p50/p90 s, W_max p50 by path type")
kerr = []
for g in GROUPS:
    e = [x for x in eps if x[0] == g]
    cc = [x for x in e if x[2] > x[1]]
    print(f"  {g:10s} {len(e):>7,} epochs ({S[g]['epochs']:,} counted), {len(cc):>7,} below W_max, K p50/p90"
          f" {pct([x[3] / 1024 for x in cc], .5):.2f}/{pct([x[3] / 1024 for x in cc], .9):.2f} s,"
          f" W_max p50 {pct([x[2] for x in cc], .5)}")
for x in eps:
    if x[2] > x[1]:
        kf = ((x[2] - x[1]) / 0.4) ** (1 / 3)
        kerr.append(abs(x[3] / 1024 - kf) / kf)
if kerr:
    print(f"  K against cbrt((W_max - cwnd) / 0.4): relative error p50 {100 * pct(kerr, .5):.2f} %, p99"
          f" {100 * pct(kerr, .99):.2f} %, max {100 * max(kerr):.2f} % over {len(kerr):,} epochs")

print("TX_START (new data with nothing in flight) and epoch shifts: events / shifts of an active epoch")
for g in GROUPS:
    print(f"  {g:10s} {S[g]['txstart']:>9,} / {S[g]['txshift']:>9,}")
if txs:
    bad = sum(1 for dl_, b, a, n in txs if a != min(b + dl_, n))
    capped = sum(1 for dl_, b, a, n in txs if b + dl_ > n)
    print(f"  traced shifts: {len(txs):,}, epoch after = min(epoch + idle, now) in {len(txs) - bad:,} "
          f"({capped:,} capped at now); idle p50/p90 {pct([x[0] for x in txs], .5)}/{pct([x[0] for x in txs], .9)} ms")

print("congestion-avoidance growth per round trip (rounds counted, over 1.5 x starting cwnd + 1, over half the "
      "ACKed packets + 1, max ratio)")
for g in GROUPS:
    s = S[g]
    print(f"  {g:10s} {s['rounds']:>9,} rounds, {s['rndover']:>6,} over 1.5x+1, {s['rndoveracked']:>6,} over"
          f" acked/2+1, max {rmax[g] / 1000:.3f}x")

if tr:
    errs = []
    for key, v in tr.items():
        for now, t, K, o, tgt, cw, cnt, tcw, lm in v:
            f = o + (1 if t >= K else -1) * 0.4 * (abs(t - K) / 1024) ** 3
            errs.append(abs(tgt - f) / max(1.0, abs(f - o)))
    print(f"logged targets against W_max + 0.4 (t - K)^3: |target - formula| / |0.4 (t - K)^3| p50"
          f" {100 * pct(errs, .5):.2f} %, p99 {100 * pct(errs, .99):.2f} % over {len(errs):,} recomputations"
          f" in {len(tr)} traced epochs")
    allv = [x for v in tr.values() for x in v]
    ae = [abs(tgt - (o + (1 if t >= K else -1) * 0.4 * (abs(t - K) / 1024) ** 3))
          for now, t, K, o, tgt, cw, cnt, tcw, lm in allv]
    cg = [x for x in allv if x[4] > x[7]]
    big = [x for x in cg if x[8] >= 30]
    print(f"  |target - formula| in segments p50 {pct(ae, .5):.2f}, p99 {pct(ae, .99):.2f}, max {max(ae):.2f};"
          f" within 1 segment {100 * sum(1 for e in ae if e <= 1) / len(ae):.1f} % (integer truncation in bictcp_update)")
    # bictcp_update uses cube_rtt_scale = 410 with >> (10 + 3 * BICTCP_HZ), so C = 410/1024, not 0.4: long epochs
    # (|t - K| of tens of seconds) differ from the 0.4 formula by 0.1 % of the cubic term
    ex = [abs(tgt - (o + (1 if t >= K else -1) * ((410 * abs(t - K) ** 3) >> 40)))
          for now, t, K, o, tgt, cw, cnt, tcw, lm in allv]
    print(f"  against Linux's integer formula origin +- (410 |t - K|^3 >> 40), C = 410/1024: equal in"
          f" {sum(1 for e in ex if e == 0):,} of {len(ex):,}, max |difference| {max(ex)} segments")
    print(f"  cubic target above the Reno-friendly cwnd (cubic governs) in {len(cg):,} of {len(allv):,}"
          f" ({sum(1 for x in cg if x[1] < x[2]):,} concave t < K, {sum(1 for x in cg if x[1] >= x[2]):,} convex);"
          f" with W_max >= 30, cwnd within 3 segments of the target in {sum(1 for x in big if abs(x[5] - x[4]) <= 3):,}"
          f" of {len(big):,}")
    def share(k, conv):  # share of a trace's recomputations where cubic governs (concave or convex part)
        v = tr[k]
        return sum(1 for x in v if x[4] > x[7] and (x[1] >= x[2]) == conv) / len(v)
    longest = sorted(tr, key=lambda k: -len(tr[k]))
    pick = [next((k for k in longest if tr[k][0][8] >= 30 and share(k, False) >= .5), None),
            next((k for k in longest if share(k, True) >= .3), None),
            next((k for k in longest if all(x[4] <= x[7] for x in tr[k])), None)]
    best = [k for k in dict.fromkeys(pick) if k is not None] or longest[:3]
    print("  traces: concave (cubic governs, W_max >= 30), convex (cubic governs past K), Reno-friendly region")
    for key in best:
        v = tr[key]
        o, K, lm = v[0][3], v[0][2], v[0][8]
        print(f"  trace {key[0]} {key[1]} ({trpath[key]}), epoch at {key[2] - 1} ms, origin {o}, K {K / 1024:.2f} s,"
              f" W_max {lm}, {len(v)} recomputations; t - K (s), cwnd, target (code), origin + 0.4 (t - K)^3, cnt,"
              f" Reno-friendly cwnd:")
        for j in sorted(set(int(q * (len(v) - 1)) for q in (0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1))):
            now, t, K, o, tgt, cw, cnt, tcw, lm = v[j]
            f = o + (1 if t >= K else -1) * 0.4 * (abs(t - K) / 1024) ** 3
            print(f"    {(t - K) / 1024:7.3f}  cwnd {cw:6d}  target {tgt:6d}  formula {f:9.1f}  cnt {cnt:6d}"
                  f"  friendly {tcw}")
