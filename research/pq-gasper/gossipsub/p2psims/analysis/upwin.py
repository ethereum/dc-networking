# Upload per link class in the 4 s window after the vote offset (4-8 s of each slot) and in its first second
# (4.0-5.0 s), from the per-node tx tick counters, slots 2 to the last slot; usage:
#   python3 -I .amp-out/upwin.py PQRUN NOPQRUN [PQRUN NOPQRUN ...]
# Per node: mean over slots of window bytes * 8 / window length / upload cap; per class: mean over nodes and the busiest
# node (largest per-node mean), as analyze.py --levers does for the 4 s window, but each node's own ticks are matched to
# the window edges within 50 ms (node-slots without both ticks or with a counter reset are left out). Each pair is the
# same generated network and seed, so node i is the same host in both runs; the PQ share is 1 - no-PQ / PQ.
import json, re, subprocess, sys
import numpy as np

T_RE, TX_RE, N_RE = re.compile(r'"t":([0-9.]+)'), re.compile(r'"tx":(\d+)'), re.compile(r'"node":(\d+)')
WINDOWS = {"4-8 s": (4.0, 8.0), "4-5 s": (4.0, 5.0), "slot": (0.0, 12.0)}


def cap_bps(s):
    v, u = s.split()
    return float(v) * {"Kbit": 1e3, "Mbit": 1e6, "Gbit": 1e9}[u]


def load(run):
    d = f"runs/{run}"
    cfg = json.load(open(f"{d}/run.json"))
    nodes = cfg["nodes"]
    n, S, t0, sl, off = len(nodes), cfg["slots"], cfg["first_slot_s"], cfg["slot_s"], cfg["vote_offset_s"]
    ticks = [dict() for _ in range(n)]
    p = subprocess.Popen(f"LC_ALL=C grep -h -F '\"ev\":\"tick\"' {d}/shadow.data/hosts/*/wbsim.*.stdout",
                         shell=True, stdout=subprocess.PIPE, text=True, bufsize=1 << 20)
    for line in p.stdout:
        ticks[int(N_RE.search(line).group(1))][round(float(T_RE.search(line).group(1)), 1)] = int(TX_RE.search(line).group(1))
    assert p.wait() == 0
    links = np.array([nd["link"] for nd in nodes])
    up = np.array([cap_bps(nd["up"]) for nd in nodes])
    res = {}
    for w, (a, b) in WINDOWS.items():
        if w != "slot":
            a, b = a - 4.0 + off, b - 4.0 + off
        rate = np.full((n, S - 2), np.nan)
        for s in range(2, S):
            ta, tb = round(t0 + s * sl + a, 1), round(t0 + s * sl + b, 1)
            for i in range(n):
                x, y = ticks[i].get(ta), ticks[i].get(tb)
                if x is not None and y is not None and y >= x:
                    rate[i, s - 2] = (y - x) * 8 / (b - a) / up[i]
        res[w] = rate
    return links, up, res


def main():
    args = sys.argv[1:]
    for k in range(0, len(args), 2):
        pq, nopq = args[k], args[k + 1]
        Lp, Up, Rp = load(pq)
        Ln, Un, Rn = load(nopq)
        assert (Lp == Ln).all() and (Up == Un).all(), "the two runs have different hosts"
        print(f"== {pq} vs {nopq} (slots 2+; % of upload cap; busiest = largest per-node mean)")
        for c in sorted(set(Lp)):
            k_ = Lp == c
            out = []
            for w in WINDOWS:
                mp, mn = np.nanmean(Rp[w], axis=1)[k_], np.nanmean(Rn[w], axis=1)[k_]
                ip, in_ = np.nanargmax(mp), np.nanargmax(mn)
                share = 1 - mn.mean() / mp.mean()
                out.append(f"{w}: PQ {100 * mp.mean():.2f} / {100 * mp[ip]:.2f}, no-PQ {100 * mn.mean():.2f} / "
                           f"{100 * mn[in_]:.2f}, PQ share {100 * share:.0f} %; busiest PQ node {np.flatnonzero(k_)[ip]} "
                           f"{100 * mp[ip]:.2f} vs {100 * mn[ip]:.2f} without PQ; max node-slot PQ "
                           f"{100 * np.nanmax(Rp[w][k_]):.0f} / no-PQ {100 * np.nanmax(Rn[w][k_]):.0f}")
            cap = Up[k_][0] / 1e6
            print(f"  {c} ({k_.sum()} hosts, up {cap:g} Mbit/s, valid node-slots PQ {np.isfinite(Rp['4-8 s'][k_]).mean():.3f} "
                  f"no-PQ {np.isfinite(Rn['4-8 s'][k_]).mean():.3f})")
            for o in out:
                print("    " + o)


main()
