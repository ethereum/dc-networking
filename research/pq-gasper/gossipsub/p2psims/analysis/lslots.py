#!/usr/bin/env python3
"""Per-slot Markdown tables for a long run: delivery (completeness, PQ and BLS misses, after-deadline PQ bytes, first
deliveries after the deadline) and scoring (links per node, negative-score peers per observer by client, P3 deficits by
topic and by observer client). Reads .amp-out/{pqdiag (--per-slot), p3split (RUN HOSTS 2 LAST), pqsum, late}-RUN.txt.
usage: lslots.py RUN"""
import ast, json, re, sys

run, O = sys.argv[1], ".amp-out"
S = json.load(open(f"runs/{run}/run.json"))["slots"]


def series(name, header, label):
    """{slot: value} for the row whose label starts with LABEL in the section headed by a line containing HEADER"""
    lines = open(f"{O}/{name}-{run}.txt").read().splitlines()
    for n, line in enumerate(lines):
        if header not in line:
            continue
        for row in lines[n + 1:]:
            m = re.match(r"\s*(.*?)\s*(\[[^\[\]]*\])\s*$", row)
            if not m:
                break
            if m.group(1).startswith(label):
                v = ast.literal_eval(m.group(2))
                s0 = {S: 0, S - 2: 2}[len(v)]
                return {s0 + k: x for k, x in enumerate(v)}
    return {}


late = {}
for line in open(f"{O}/late-{run}.txt"):
    m = re.match(r"slot (\d+):.*\|\| cloud: .*?\| 8-16 s first ([0-9.]+) later", line)
    if m:
        late[int(m.group(1))] = float(m.group(2))
cl = ["50x15", "50x25", "cloud"]
comp = {c: series("pqdiag", "node-slot completeness per slot", c) for c in cl}
pqm = series("pqdiag", "PQ msg miss % at 8 s by class", "cloud")
bls = {c: series("pqdiag", "per slot, missing at 8 s (% of deliveries)", c) for c in cl}
aft = {c: series("pqsum", "PQ kB received after the deadline", c + ":") for c in cl}
links = series("pqdiag", "# Item 2", "links/node")
clients = ["lighthouse", "other", "prysm", "teku", "lodestar", "nimbus"]
neg = {c: series("pqdiag", "by observer client:", c) for c in clients}
p3t = {g: series("p3split", "MessageDeficit per topic group", g) for g in ("pq", "att", "block", "agg")}
p3c = {c: series("p3split", "MessageDeficit penalties per slot by observer client", c + " ") for c in clients}


def f(d, s, fmt):
    x = d.get(s)
    return "–" if x is None else format(x, fmt)


print(f"Delivery per slot, `{run}` (1 Gbit = cloud class; PQ and BLS misses at 8 s; after-deadline PQ kB per node, 8-16 s)\n")
print("| slot | complete 50/15 / 50/25 / 1 Gbit (%) | PQ missing, 1 Gbit (%) | BLS attestations missing, 50/15 / 50/25 / 1 Gbit (%) "
      "| after-deadline PQ kB, 50/15 / 50/25 / 1 Gbit | late first PQ deliveries (8-16 s), 1 Gbit host mean |")
print("|---|---|---|---|---|---|")
for s in range(S):
    print(f"| {s} | {' / '.join(f(comp[c], s, '.2f') for c in cl)} | {f(pqm, s, '.4f')} | "
          f"{' / '.join(f(bls[c], s, '.3f') for c in cl)} | {' / '.join(f(aft[c], s, '.0f') for c in cl)} | {f(late, s, '.2f')} |")
print(f"\nAfter-deadline PQ kB per node (8-16 s), mean per 10-slot block from slot 2, `{run}` (backlog signal: flat if the load is sustained)\n")
print("| slots | 50/15 | 50/25 | 1 Gbit |")
print("|---|---|---|---|")
B = [2] + list(range(10, S, 10))
for i, b in enumerate(B):
    e = (B[i + 1] if i + 1 < len(B) else S) - 1
    m = [[aft[c][s] for s in range(b, e + 1) if s in aft[c]] for c in cl]
    print(f"| {b}-{e} | {' | '.join('–' if not v else format(sum(v) / len(v), '.1f') for v in m)} |")
print(f"\nScoring per slot, `{run}` (mesh snapshot at 3.95 s; negative-score peers per observer; P3 = MessageDeficit "
      "penalties summed over hosts in the slot; Prysm applies no P3)\n")
print("| slot | links/node | negative peers per observer: Lighthouse / other / Prysm / Teku / Lodestar / Nimbus "
      "| P3 by topic: PQ / attestation / block / aggregate | P3 in the views of Lighthouse / other / Teku / Lodestar / Nimbus |")
print("|---|---|---|---|---|")
for s in range(S):
    print(f"| {s} | {f(links, s, '.1f')} | {' / '.join(f(neg[c], s, '.1f') for c in clients)} | "
          f"{' / '.join(f(p3t[g], s, 'd') for g in ('pq', 'att', 'block', 'agg'))} | "
          f"{' / '.join(f(p3c[c], s, 'd') for c in clients if c != 'prysm')} |")
