#!/usr/bin/env python3
"""PQ Gasper subnet specs study (Nov 23): 1,600 signatures per subnet per slot, every node needs all by 8.0 s.
runs/specs-queue.sh runs this after each run's analysis. It reads the home class's pass verdict from
.amp-out/pq1600-NAME.txt for every run named in runs/queue-specs.txt and appends the next run to that file
(temp file + rename). Plan of the coordinator's 06:1x message (Nov 23); no upload passed with the modelled access
loss, so every run has the home hosts' access-link loss off (family -al0, --access-loss-scale 0) unless noted:
  a. 1000/100; if it fails, 1000/200; if that fails too, stop (jitter is tested next, by hand).
  b. 1000/50 if 1000/100 passes. U* = the smallest of these that passes; nothing below 50, no midpoint yet.
  c. 100/U*; then 50/U* if it passes or 200/U* if it fails. D* = the smallest passing download.
  d. seed 2 at D*/U*.
  e. 1000/200 with access loss at a fifth (family -al02, --access-loss-scale 0.2).
  f. only while nothing else is queued: the upload midpoint (75 if U* = 100, 150 if U* = 200), then D*/U* with PQ
     verification at 2,000 us per signature.
A run the watchdog stopped for memory counts as a fail if its analysed slots reach slot 10 and as a pass if they reach
slot 14; a passing run stopped earlier is rerun with 16 slots (S2048x16-...), whose verdict replaces it. Any other
stop, a missing verdict or a case outside this plan appends nothing and logs 'needs a decision' (the queue idles).
usage: python3 -I .amp-out/specs-decide.py NAME   (prints one log line)"""
import os
import re
import sys
import time

Q = "runs/queue-specs.txt"
VERIFY = "--verify-us pq=2000,block=10000,col=1500,att=600,agg=2500,syncc=2000"
RUN_RE = re.compile(r"\b(S2048x(?:20|16)-h(\d+)x(\d+)(-al02|-al0|-noloss)?(-v2000)?-s(\d+)) 2048 (?:20|16) ")
FAM_FLAGS = {"": "", "-noloss": " --loss-scale 0", "-al0": " --access-loss-scale 0", "-al02": " --access-loss-scale 0.2"}
AL0 = "-al0"


def verdict(n, log):
    """('pass' | 'fail' | 'rerun16' | None, note) for the home class of run n."""
    p = f".amp-out/pq1600-{n}.txt"
    if not os.path.exists(p):
        return None, "no analysis"
    txt = open(p).read()
    m = re.search(r"analysed slots (\d+)-(\d+)", txt)
    pr = re.search(r"pass rule \([^)]*\): (.*)", txt)
    if not m or not pr:
        return None, "no pass-rule line"
    last = int(m.group(2))
    home = [x for x in pr.group(1).split("; ") if not x.startswith("1 Gbit")]
    if len(home) != 1:
        return None, f"home classes {home}"
    ok = " PASS " in home[0]
    since = log.rfind(f" start {n} ")  # a stop of an earlier attempt (rerun from scratch) does not count
    st = re.search(r"STOPPED %s \((\w+)\)" % re.escape(n), log[max(since, 0):])
    where = f"{home[0]}, slots {m.group(1)}-{last}"
    if not st:
        return ("pass" if ok else "fail"), where
    if st.group(1) != "mem":
        return None, f"stopped ({st.group(1)}); {where}"
    if ok and last >= 14:
        return "pass", f"{where}, stopped for memory: counts as a pass (slot 14 reached)"
    if not ok and last >= 10:
        return "fail", f"{where}, stopped for memory"
    if ok and n.startswith("S2048x20-"):
        return "rerun16", f"{where}, stopped for memory before slot 14 while passing"
    return None, f"stopped (mem) too early; {where}"


def name_of(fam, d, u, seed, v2000):
    return f"S2048x20-h{d}x{u}{fam}{'-v2000' if v2000 else ''}-s{seed}"


def plan(status, free):
    """('queue', fam, down, up, seed, v2000) | ('wait' | 'stop' | 'done', why). status maps (fam, down, up, v2000,
    seed) to the verdict of its latest run, or 'queued' if that run has no analysis yet."""
    def need(d, u, seed=1, v=False, fam=AL0):
        s = status.get((fam, d, u, v, seed), "new")
        if s in ("pass", "fail"):
            return None
        if s == "new":
            return ("queue", fam, d, u, seed, v)
        if s == "queued":
            return ("wait", f"{name_of(fam, d, u, seed, v)} is queued")
        return ("stop", f"{name_of(fam, d, u, seed, v)} has no verdict")

    def ok(d, u, seed=1, v=False, fam=AL0):
        return status[(fam, d, u, v, seed)] == "pass"
    a = need(1000, 100)                                           # a
    if a:
        return a
    if ok(1000, 100):
        a = need(1000, 50)                                        # b
        if a:
            return a
        U = 50 if ok(1000, 50) else 100
    else:
        a = need(1000, 200)
        if a:
            return a
        if not ok(1000, 200):
            return ("stop", "1000/100 and 1000/200 both fail with access loss off (test jitter next)")
        U = 200
    a = need(100, U)                                              # c
    if a:
        return a
    if ok(100, U):
        a = need(50, U)
        if a:
            return a
        D = 50 if ok(50, U) else 100
    else:
        a = need(200, U)
        if a:
            return a
        if not ok(200, U):
            return ("stop", f"U* = {U}: downloads 100 and 200 fail")
        D = 200
    a = need(D, U, seed=2) or need(1000, 200, fam="-al02")      # d, e
    if a:
        return a
    mid = {100: 75, 200: 150}.get(U)                              # f (nothing below 50)
    for args in ([(1000, mid)] if mid else []) + [(D, U, 1, True)]:
        a = need(*args)
        if a:
            return a if a[0] != "queue" or free else ("stop", "step f not queued: other runs are pending")
    return ("done", f"study complete (U* = {U}, D* = {D})")


def append(qtext, line):
    with open(Q + ".tmp", "w") as f:
        f.write(qtext + ("" if qtext.endswith("\n") else "\n") + line + "\n")
    os.replace(Q + ".tmp", Q)


def main(cur):
    os.chdir("/home/yann/p2p-ministry-gossip2000")
    log = open("runs/realistic.log").read()
    qtext = open(Q).read()
    names = {}  # key -> run names in queue order; a 16-slot rerun comes after its 20-slot run
    for m in RUN_RE.finditer(qtext):
        k = (m.group(4) or "", int(m.group(2)), int(m.group(3)), bool(m.group(5)), int(m.group(6)))
        if m.group(1) not in names.get(k, []):
            names.setdefault(k, []).append(m.group(1))
    status = {k: verdict(ns[-1], log)[0] if os.path.exists(f".amp-out/pq1600-{ns[-1]}.txt") else "queued"
              for k, ns in names.items()}
    v, note = verdict(cur, log)
    head = f"{time.strftime('%H:%M:%S')} DECIDE {cur}: home {v.upper() if v else 'no verdict'} ({note})"
    if v is None:
        return head + " -> needs a decision; nothing queued"
    if v == "rerun16":
        line = next((l for l in qtext.splitlines() if l.startswith(cur + " 2048 20 ")), None)
        new = cur.replace("S2048x20-", "S2048x16-", 1)
        if line is None or re.search(r"\b%s " % re.escape(new), qtext):
            return head + " -> needs a decision: cannot queue its 16-slot rerun"
        append(qtext, f"{new} 2048 16 {line.split(' ', 3)[3]}")
        return head + f" -> queued {new}"
    pending = [l.split()[0] for l in qtext.splitlines()
               if l.strip() and not l.startswith("#") and not os.path.exists(f"runs/{l.split()[0]}")]
    act = plan(status, not pending)
    if act[0] != "queue":
        return head + {"wait": " -> ", "stop": " -> needs a decision: ", "done": " -> "}[act[0]] + act[1]
    _, fam, D, U, seed, v2000 = act
    name = name_of(fam, D, U, seed, v2000)
    if re.search(r"\b%s " % re.escape(name), qtext):
        return head + f" -> needs a decision: next run {name} is already in {Q}"
    append(qtext, f"{name} 2048 20 46 --links {D}/{U} --links-novalidator {D}/{U}" + (" --seed 2" if seed == 2 else "")
           + (f" {VERIFY}" if v2000 else "") + FAM_FLAGS[fam])
    return head + f" -> queued {name}"


if __name__ == "__main__":
    print(main(sys.argv[1]))
