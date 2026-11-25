# Client-faithful scoring check: negative-score peers in each observer's view, by observer client, against the
# observer's own failed sends (timeouts + queue full) in the 12 s before the mesh snapshot. With --client-slow-peer the
# score losses from failed sends must appear only in Rust observers' views (lighthouse, other).
# usage: python3 .amp-out/cfcheck.py RUN [RUN ...]
import glob, json, sys
from collections import defaultdict
import numpy as np
for name in sys.argv[1:]:
    run = f"runs/{name}"
    cfg = json.load(open(f"{run}/run.json")); nodes, t0 = cfg["nodes"], cfg["first_slot_s"]
    mesh, T = {}, defaultdict(list)
    for f in glob.glob(f"{run}/shadow.data/hosts/*/wbsim.*.stdout"):
        for line in open(f):
            if '"ev":"mesh"' in line:
                e = json.loads(line); mesh[(e["slot"], e["node"])] = e
            elif '"ev":"tick"' in line:
                e = json.loads(line); T[e["node"]].append((e["t"], e.get("f_timeout", 0) + e.get("f_queue_full", 0)))
    A = {i: np.array(sorted(v)) for i, v in T.items()}
    at = lambda i, t: A[i][max(np.searchsorted(A[i][:, 0], t + 1e-6) - 1, 0), 1]
    st = defaultdict(lambda: [0, 0, 0, 0.0])  # client -> observer-slots, negatives, failed sends, min score
    for (s, i), e in mesh.items():
        if s < 1:
            continue
        c = nodes[i]["client"]; a = t0 + 12 * s + 3.95
        sc = e.get("score") or [0, 0, 0, 0]
        st[c][0] += 1; st[c][1] += sc[3]; st[c][2] += at(i, a) - at(i, a - 12); st[c][3] = min(st[c][3], sc[0])
    print(f"== {name}: per observer client, slots 1+: observer-slots, negative-score peers per observer, "
          f"own failed sends per observer per 12 s, lowest score seen")
    for c, (n, ng, fs, mn) in sorted(st.items()):
        w = {(nd.get("gs") or {}).get("slow_peer_weight", "run (-10)") for nd in nodes if nd["client"] == c}
        print(f"   {c:10s} weight {w}: {n:4d}  {ng / n:6.2f}  {fs / n:8.0f}  {mn:10.1f}")
