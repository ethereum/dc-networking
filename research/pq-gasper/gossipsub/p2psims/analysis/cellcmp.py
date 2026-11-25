#!/usr/bin/env python3
"""Side-by-side summary of R20 PQ runs from their analysis outputs in .amp-out (pqdiag, pqsum, late, upwin, failsplit,
cfcheck, calib, blockslot, tcppath, rtt6diag), for the subnet-cell reports (coordinator 00:4x Nov 12).
usage: python3 -I .amp-out/cellcmp.py RUN [RUN ...]
RUN:all reads pqdiag-RUN-all*.txt and late-RUN-all.txt (PQ_NEED=all: every subscribed PQ subnet needed) and RUN's other
outputs. Missing outputs print '-'. Classes: 50x15 (home, no validators), 50x25 (home stakers), cloud (1 Gbit)."""
import ast
import os
import re
import sys

O = "/home/yann/p2p-ministry-gossip2000/.amp-out"
C = ("50x15", "50x25", "cloud")
PATHS = ("1G->1G", "1G->home", "home->1G", "home->home")
NUM = r"-?[0-9.]+"


def rd(name):
    p = os.path.join(O, name)
    return open(p).read() if os.path.exists(p) else ""


def floats(s):
    return [float(x) for x in re.split(r"[,\s]+", s.strip()) if x]


def after(t, head, n=40):
    i = t.find(head)
    return t[i:].splitlines()[1:n + 1] if i >= 0 else []


def rows(t, head, n=12):
    out = {}
    for line in after(t, head, n):
        m = re.match(r"\s+(\S+)\s+\[([^\]]*)\]", line)
        if m and m.group(1).rstrip(":") not in out:
            out[m.group(1).rstrip(":")] = floats(m.group(2)) if "(" not in m.group(2) else ast.literal_eval("[" + m.group(2) + "]")
    return out


def f(x, nd=2):
    if x is None or x == "":
        return "-"
    if isinstance(x, float):
        return f"{x:.{nd}f}".rstrip("0").rstrip(".") if nd > 2 else f"{x:.{nd}f}"
    return str(x)


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def pqdiag(t):
    d = {}
    if not t:
        return d
    d["slots"] = rows(t, "node-slot completeness per slot and class", 6)
    m = re.search(r"pass rule \(.*\): (PASS|FAIL)", t)
    d["pass"] = m.group(1) if m else None
    m = re.search(r"worst slot per class \(%, slot\): (\{.*\})", t)
    d["worst"] = ast.literal_eval(m.group(1)) if m else {}
    for line in after(t, "per class  node-slots", 5):
        m = re.match(r"\s+(\S+)\s+(\d+) \| ([0-9.]+) \| ([0-9.]+) \| ([0-9.]+) \| (\d+)", line)
        if m:
            d.setdefault("cls", {})[m.group(1)] = (float(m.group(3)), float(m.group(4)), int(m.group(6)))
    for line in after(t, "incomplete node-slots, slots", 4):
        m = re.match(r"\s+(50x15|50x25|cloud)\s+(\d+):\s*(.*)$", line)
        if m:
            d.setdefault("inc", {})[m.group(1)] = (int(m.group(2)), m.group(3).strip())
    for m in re.finditer(r"^\s+(50x15|50x25|cloud)\s+repeat hosts: (\d+) of (\d+) hosts incomplete at least once;.*max per "
                         r"host (\d+) of (\d+) slots", t, re.M):
        d.setdefault("rep", {})[m.group(1)] = (int(m.group(2)), int(m.group(3)), int(m.group(4)))
    d["top"] = [(h, int(k), cl, cli, reg) for h, k, cl, cli, reg in
                re.findall(r"^   host (\d+): (\d+) \| (\S+) (\S+) \d+ nat=\S+ (\S+)", t, re.M)][:5]
    d["miss_slot"] = rows(t, "PQ msg miss % at 8 s by class", 4)
    for line in after(t, "# BLS attestation miss rate", 4):
        m = re.match(r"\s+(50x15|50x25|cloud)\s+([0-9.]+) / ([0-9.]+) % of (\d+)", line)
        if m:
            d.setdefault("bls", {})[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    m = re.search(r"links/node\s+\[([^\]]*)\]", t)
    d["links"] = floats(m.group(1)) if m else []
    d["mesh"] = {c: floats(m.group(1)) for c in C for m in [re.search(rf"PQ mesh {c}\s+\[([^\]]*)\]", t)] if m}
    m = re.search(r"neg peers\s+\[([^\]]*)\]", t)
    d["neg"] = floats(m.group(1)) if m else []
    d["negobs"] = rows(t, "negative-score peers per observer, by observer class", 4)
    d["negpct"] = rows(t, "% of connections to peers of a class that are negative", 4)
    d["fail"] = {m.group(1): ast.literal_eval("[" + m.group(2) + "]") for m in
                 re.finditer(r"failed sends per host \((\S+)\): timed out / queue full \[(.*)\]\s*$", t, re.M)}
    return d


def pqsum(t):
    d = {}
    for m in re.finditer(rf"^\s+(50x15|50x25|cloud): ({NUM}) % of (\d+) node-slots; latency from publish p50/p99 \[({NUM}), ({NUM})\]",
                         t, re.M):
        d.setdefault("lat", {})[m.group(1)] = (float(m.group(4)), float(m.group(5)))
    for m in re.finditer(r"^\s+(50x15|50x25|cloud): up (\d+) % of cap in the 4 s window \(max node (\d+) %\), down (\d+) % "
                         r"\(max (\d+) %\)", t, re.M):
        d.setdefault("bw", {})[m.group(1)] = tuple(int(m.group(k)) for k in (2, 3, 4, 5))
    for k in ("kappa", "copies", "idontwant"):
        m = re.search(rf"^\s+{k}\s+\[([^\]]*)\]", t, re.M)
        d[k] = floats(m.group(1)) if m else []
    d["late_kB"] = rows(t, "PQ kB received after the deadline", 4)
    d["fails"] = {}
    for line in after(t, "failed sends per node per slot, mean", 4):
        m = re.match(r"\s+(50x15|50x25|cloud): (\[.*\])\s*$", line)
        if m:
            d["fails"][m.group(1)] = ast.literal_eval(m.group(2))
    d["meshj"] = {m.group(1): floats(m.group(2)) for m in re.finditer(r"PQ mesh size per joined PQ topic, (\S+): \[([^\]]*)\]", t)}
    m = re.search(r"PQ signatures lost to churn (\d+)", t)
    d["churn"] = int(m.group(1)) if m else None
    m = re.search(r"^ conns: (\{.*\})", t, re.M)
    d["conns"] = ast.literal_eval(m.group(1)) if m else {}
    return d


def late(t):
    d = {}
    for line in t.splitlines():
        ms = re.match(r"slot (\d+):", line)
        if not ms:
            continue
        for m in re.finditer(r"(50x15|50x25|cloud): 4-8 s first (\d+) copies (\d+) iwant \d+ \| 8-16 s first ([0-9.]+) later "
                             r"([0-9.]+) stale ([0-9.]+) copies (\d+) kB (\d+)", line):
            d[(int(ms.group(1)), m.group(1))] = (float(m.group(4)), int(m.group(8)), float(m.group(6)))
    return d


def upwin(t):
    d, cur = {}, None
    for line in t.splitlines():
        m = re.match(r"  (50x15|50x25|cloud) \(", line)
        if m:
            cur = m.group(1)
            continue
        m = re.match(r"\s+(4-8 s|4-5 s|slot): PQ ([0-9.]+) / ([0-9.]+), no-PQ ([0-9.]+) / ([0-9.]+), PQ share (-?\d+) %; busiest PQ "
                     r"node (\d+) ([0-9.]+) vs ([0-9.]+) without PQ; max node-slot PQ (\d+) / no-PQ (\d+)", line)
        if m and cur:
            d[(cur, m.group(1))] = m.groups()[1:]
    m = re.match(r"== (\S+) vs (\S+)", t)
    d["pair"] = m.groups() if m else ("-", "-")
    return d


def failsplit(t):
    d = {}
    m = re.search(r"share by kind \(%\): (\{.*\}) total (\d+)", t)
    if m:
        d["kind"], d["total"] = ast.literal_eval(m.group(1)), int(m.group(2))
    for m in re.finditer(r"^\s+(50x15|50x25|cloud)\s+(non-rust|rust)\s+hosts=(\d+): fwd timeout (-?[0-9.]+) %, fwd qfull (-?[0-9.]+) %, "
                         r"ctrl qfull (-?[0-9.]+) %.*?\(total (\d+)\)", t, re.M):
        d.setdefault("cls", {})[(m.group(1), m.group(2))] = (int(m.group(3)), float(m.group(4)), float(m.group(5)),
                                                             float(m.group(6)), int(m.group(7)))
    m = re.search(r"chronic cloud hosts \(incomplete in >= half of (\d+) slots\): (\d+)", t)
    d["chronic"] = int(m.group(2)) if m else None
    return d


def cfcheck(t):
    return {m.group(1): float(m.group(3)) for m in
            re.finditer(r"^\s+(lighthouse|lodestar|nimbus|other|prysm|teku)\s+weight .*?:\s+(\d+)\s+([0-9.]+)\s+\d+", t, re.M)}


def calib(t):
    d = {}
    m = re.search(r"block from publish p50/p95/p99: ([0-9.]+) / ([0-9.]+) / ([0-9.]+)", t)
    d["block"] = m.groups() if m else None
    m = re.search(r"att after 4 s p50/p95/p99: ([0-9.]+) / ([0-9.]+) / ([0-9.]+)\s+missing (\d+) / (\d+) \(([0-9.]+) %\)", t)
    d["att"] = (m.group(1), m.group(2), m.group(3), m.group(6)) if m else None
    return d


def tcp(tp, t6):
    d = {}
    for line in after(tp, "cwnd over the run", 5):
        m = re.match(r"\s+(\S+)\s+(\d+) / (\d+) \(", line)
        if m:
            d.setdefault("cwnd", {})[m.group(1)] = (m.group(2), m.group(3))
    for line in after(tp, "first timeouts per 1,000 data packets", 14):
        m = re.match(r"\s+(\S+)\s+all ([0-9.]+): ([0-9. ]+)$", line)
        if m:
            v = floats(m.group(3))
            d.setdefault("ft", {})[m.group(1)] = (m.group(2), v[0], v[-1])
    for line in after(tp, "ssthresh p50 after a restart per slot", 5):
        m = re.match(r"\s+(\S+)\s+([u\d ]+)$", line)
        if m:
            v = m.group(2).split()
            d.setdefault("ss", {})[m.group(1)] = (v[0], v[-1])
    for m in re.finditer(r"^\s+(\S+)\s+[\d,]+ of [\d,]+ =\s+([0-9.]+) %", t6, re.M):
        d.setdefault("ge", {})[m.group(1)] = m.group(2)
    for m in re.finditer(r"^\s+(\S+)\s+train\s+([\d,]+)\s+delay\s+([\d,]+)", t6, re.M):
        d.setdefault("hys", {})[m.group(1)] = (m.group(2), m.group(3))
    return d


def load(spec):
    run, _, var = spec.partition(":")
    sfx = "-all" if var == "all" else ""
    r = dict(name=run, label=run.replace("R20-pq-", "").replace("-ps100-cf2-s1", "") + (" (all)" if sfx else ""))
    r["d"] = pqdiag(rd(f"pqdiag-{run}{sfx}.txt"))
    r["d215"] = pqdiag(rd(f"pqdiag-{run}{sfx}-s2-15.txt"))
    r["d1619"] = pqdiag(rd(f"pqdiag-{run}{sfx}-s16-19.txt"))
    r["s"] = pqsum(rd(f"pqsum-{run}.txt"))
    r["late"] = late(rd(f"late-{run}{sfx}.txt"))
    r["up"] = upwin(rd(f"upwin-{run}.txt"))
    r["fs"] = failsplit(rd(f"failsplit-{run}.txt"))
    r["cf"] = cfcheck(rd(f"cfcheck-{run}.txt"))
    r["cal"] = calib(rd(f"calib-{run}.txt"))
    m = re.search(r"^\s+p95 (.*)$", rd(f"blockslot-{run}.txt"), re.M)
    r["bs"] = floats(m.group(1)) if m else []
    r["tcp"] = tcp(rd(f"tcppath-{run}.txt"), rd(f"rtt6diag-{run}.txt"))
    return r


def main():
    R = [load(a) for a in sys.argv[1:]]
    W = 46
    print("== cellcmp: " + " | ".join(r["label"] for r in R))
    line = lambda k, vals: print(f"{k:<{W}}" + " | ".join(vals))
    trip = lambda xs, nd=2: "/".join(f(x, nd) if x is not None else "-" for x in xs)
    line("strict rule (pqdiag, slots 2-19)", [f(r["d"].get("pass")) for r in R])
    line("worst slot 50x15/50x25/cloud (%, slot)", ["/".join(f"{w[0]:g}({w[1]})" for c in C for w in [r["d"].get("worst", {}).get(c)] if w)
                                                     or "-" for r in R])
    for key, lab in (("d215", "2-15"), ("d1619", "16-19")):
        line(f"complete % {lab}", [trip([r[key].get("cls", {}).get(c, (None,))[0] for c in C]) for r in R])
        line(f"PQ miss % at 8 s {lab}", [trip([r[key].get("cls", {}).get(c, (None, None))[1] for c in C], 4) for r in R])
        line(f"needed pairs {lab}", [trip([r[key].get("cls", {}).get(c, (None, None, None))[2] for c in C], 0) for r in R])
        line(f"BLS att miss % at 8 s {lab}", [trip([r[key].get("bls", {}).get(c, (None,))[0] for c in C], 3) for r in R])
    line("incomplete cloud node-slots (reasons)", [" ".join(map(str, r["d"].get("inc", {}).get("cloud", ("-", "")))) for r in R])
    line("incomplete home node-slots 15/25", ["/".join(str(r["d"].get("inc", {}).get(c, ("-",))[0]) for c in C[:2]) for r in R])
    line("cloud hosts ever incomplete / max slots", ["%s of %s / %s" % r["d"]["rep"]["cloud"] if "cloud" in r["d"].get("rep", {}) else "-"
                                                     for r in R])
    line("chronic cloud hosts (failsplit)", [f(r["fs"].get("chronic")) for r in R])
    line("most often incomplete", [", ".join(f"{h} {cli[:4]} {reg} {k}" for h, k, cl, cli, reg in r["d"].get("top", [])[:4]) or "-"
                                   for r in R])
    line("latency p50/p99 (s) 15 | 25 | cloud", [" ; ".join(trip(r["s"].get("lat", {}).get(c, (None, None))) for c in C) for r in R])
    line("up 4 s window mean/max % (pqsum)", [" ; ".join(trip(r["s"].get("bw", {}).get(c, (None,) * 4)[:2], 0) for c in C) for r in R])
    line("down 4 s window mean/max %", [" ; ".join(trip(r["s"].get("bw", {}).get(c, (None,) * 4)[2:], 0) for c in C) for r in R])
    for c in C:
        for w in ("4-8 s", "4-5 s"):
            line(f"upwin {c} {w} mean/busiest (noPQ, share)",
                 [("%s/%s (%s/%s, %s %%) n%s w/o PQ %s" % tuple(r["up"][(c, w)][k] for k in (0, 1, 2, 3, 4, 5, 7)))
                  if (c, w) in r["up"] else "-" for r in R])
    line("upwin no-PQ pair", [r["up"].get("pair", ("-", "-"))[1] for r in R])
    for k, nd in (("kappa", 2), ("copies", 2), ("idontwant", 0)):
        line(f"{k} slot 2 -> 19 (max)", ["%s -> %s (%s)" % (f(v[2], nd), f(v[-1], nd), f(max(v[2:]), nd)) if len(v) > 2 else "-"
                                         for r in R for v in [r["s"].get(k, [])]])
    for c in C:
        line(f"after-deadline kB {c}: s2 / s8 / 9-19 / slope", [("%.0f / %.0f / %.0f-%.0f / %+.1f" % (
            v[2], v[8], min(v[9:]), max(v[9:]), slope(v[10:20], 10))) if len(v) >= 20 else "-" for r in R
            for v in [r["s"].get("late_kB", {}).get(c, [])]])
    for c in C:
        line(f"late first {c}: 2-15 / 16-19 / max", [lsum(r["late"], c) for r in R])
    line("links/node 2-19 range", ["%.0f-%.0f" % (min(v[2:]), max(v[2:])) if len(v) > 2 else "-" for r in R for v in [r["d"].get("links", [])]])
    line("PQ mesh per joined topic 15/25/cloud", [trip([mean(r["s"].get("meshj", {}).get(c, [])[2:]) for c in C]) for r in R])
    line("neg-score peers total: s5 / 12-19", ["%.0f / %.0f-%.0f" % (v[5], min(v[12:]), max(v[12:])) if len(v) >= 20 else "-"
                                               for r in R for v in [r["d"].get("neg", [])]])
    for c in C:
        line(f"neg peers per observer {c}: 2-19 mean/s19", ["%.1f / %.1f" % (mean(v[2:]), v[-1]) if len(v) > 2 else "-"
                                                            for r in R for v in [r["d"].get("negobs", {}).get(c, [])]])
    for c in C:
        line(f"% conns to {c} peers negative 2-19", ["%.2f" % mean(v[2:]) if len(v) > 2 else "-" for r in R
                                                     for v in [r["d"].get("negpct", {}).get(c, [])]])
    for c in C:
        line(f"failed sends/host {c} TO/QF 2-19 mean", ["%.0f / %.0f" % (mean([x[0] for x in v[2:]]), mean([x[1] for x in v[2:]]))
                                                        if len(v) > 2 else "-" for r in R for v in [r["d"].get("fail", {}).get(c, [])]])
    for c in C:
        line(f"failsplit {c} rust: TO/QF/ctrlQF % (total)", [fsplit(r["fs"], c, "rust") for r in R])
        line(f"failsplit {c} non-rust", [fsplit(r["fs"], c, "non-rust") for r in R])
    line("failed sends total (M) by kind %", ["%.1f %s" % (r["fs"]["total"] / 1e6, {k: v for k, v in r["fs"]["kind"].items() if v})
                                             if "total" in r["fs"] else "-" for r in R])
    line("neg peers per observer: LH/other/rest", ["%s/%s/%s-%s" % (f(cf.get("lighthouse")), f(cf.get("other")),
                                                    f(min(cf.get(k, 99) for k in ("lodestar", "nimbus", "prysm", "teku"))),
                                                    f(max(cf.get(k, 0) for k in ("lodestar", "nimbus", "prysm", "teku")))) if cf else "-"
                                                   for r in R for cf in [r["cf"]]])
    line("blocks from publish p50/p95/p99", ["/".join(r["cal"]["block"]) if r["cal"].get("block") else "-" for r in R])
    line("att after 4 s p50/p95/p99, never %", ["%s/%s/%s, %s" % r["cal"]["att"] if r["cal"].get("att") else "-" for r in R])
    line("churn (pqsum field; messages if b16)", [f(r["s"].get("churn")) for r in R])
    for p in PATHS:
        line(f"cwnd p50/p90 {p}", ["/".join(r["tcp"].get("cwnd", {}).get(p, ("-", "-"))) for r in R])
    for p in PATHS:
        line(f"first timeouts/1,000 {p}: all (s2->s18)", ["%s (%.2f->%.2f)" % r["tcp"]["ft"][p] if p in r["tcp"].get("ft", {}) else "-"
                                                          for r in R])
    for p in PATHS:
        line(f"ssthresh after restart {p} s2->s18", ["->".join(r["tcp"].get("ss", {}).get(p, ("-", "-"))) for r in R])
    line("cwnd >= ssthresh % (4 paths, all)", ["/".join(r["tcp"].get("ge", {}).get(p, "-") for p in PATHS + ("all",)) for r in R])
    line("HyStart train/delay by path", [" ".join("%s/%s" % r["tcp"]["hys"][p] if p in r["tcp"].get("hys", {}) else "-" for p in PATHS)
                                         for r in R])
    print()
    for r in R:
        sl = r["d"].get("slots", {})
        for c in C:
            if c in sl and min(sl[c][2:] or [100]) < 100:
                print(f"{r['label']}: complete % {c} slots 0-19: " + " ".join(f"{x:g}" for x in sl[c]))
        ms = r["d"].get("miss_slot", {})
        for c in C:
            if c in ms and max(ms[c] or [0]) > 0:
                print(f"{r['label']}: PQ miss % {c} slots 2-19: " + " ".join(f"{x:g}" for x in ms[c]))
        if r["bs"]:
            print(f"{r['label']}: block p95 from publish slots 2-19: " + " ".join(f"{x:.2f}" for x in r["bs"]) +
                  "  (means 2-7/8-13/14-19 %.2f/%.2f/%.2f)" % tuple(mean(r["bs"][a:b]) for a, b in ((0, 6), (6, 12), (12, 18))))
        lt = r["late"]
        for c in C:
            v = [lt[(s, c)][0] for s in range(2, 20) if (s, c) in lt]
            if v and max(v) > 0:
                print(f"{r['label']}: late first per node {c} slots 2-19: " + " ".join(f"{x:.2f}" for x in v))


def slope(ys, x0):
    xs = list(range(x0, x0 + len(ys)))
    mx, my = mean(xs), mean(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)


def lsum(lt, c):
    a = [lt[(s, c)][0] for s in range(2, 16) if (s, c) in lt]
    b = [lt[(s, c)][0] for s in range(16, 20) if (s, c) in lt]
    return "%.2f / %.2f / %.2f" % (mean(a), mean(b), max(a + b)) if a and b else "-"


def fsplit(fs, c, k):
    v = fs.get("cls", {}).get((c, k))
    return "%.1f/%.1f/%.1f (%.1fM, %d hosts)" % (v[1], v[2], v[3], v[4] / 1e6, v[0]) if v else "-"


if __name__ == "__main__":
    main()
