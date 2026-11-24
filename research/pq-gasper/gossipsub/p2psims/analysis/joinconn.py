# Which hosts gained a connection between the ticks around a join, and their RTT to the joiner (Dijkstra over the Shadow graph).
import heapq, json, re, sys, collections
run, me, t_a, t_b = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
dial = float(sys.argv[5]) if len(sys.argv) > 5 else t_a  # time of the joiner's first dial (online + 0.1 s)
y = open(f"{run}/shadow.yaml").read()
g = y[y.index("graph ["):]
adj = collections.defaultdict(list)
for s, t, v, u in re.findall(r'edge \[\s*source (\d+)\s*target (\d+)\s*latency "([\d.]+) ?(ms|us|ns)?"', g):
    v = float(v) * {"ms": 1, "us": 1e-3, "ns": 1e-6}.get(u, 1)
    adj[int(s)].append((int(t), v)); adj[int(t)].append((int(s), v))
ids = {int(a): int(b) for a, b in re.findall(r"\n  n(\d+):\n    network_node_id: (\d+)", y)}
src = ids[me]; dist = {src: 0.0}; pq = [(0.0, src)]
while pq:
    d, x = heapq.heappop(pq)
    if d > dist.get(x, 1e18): continue
    for z, w in adj[x]:
        if d + w < dist.get(z, 1e18): dist[z] = d + w; heapq.heappush(pq, (d + w, z))
self_loop = {s for s, t, *_ in re.findall(r'edge \[\s*source (\d+)\s*target (\d+)', g) if s == t}
def rtt(h):
    n = ids[h]
    if n == src:  # same graph node: Shadow uses the self-loop latency
        return 2 * min((w for z, w in adj[src] if z == src), default=float("nan"))
    return 2 * dist.get(n, float("nan"))
hosts = json.load(open(f"{run}/run.json"))["nodes"]
r = sorted(rtt(h) for h in ids if h != me)
print("hosts by RTT to", me, ": <=31.7 ms", sum(x <= 31.7 for x in r), " <=47.5", sum(x <= 47.5 for x in r), " <=89.5", sum(x <= 89.5 for x in r), " of", len(r))
c = collections.defaultdict(dict)
for line in sys.stdin:
    path, js = line.split(":", 1)
    h = int(re.search(r"/n(\d+)/", path).group(1)); e = json.loads(js)
    c[h][round(e["t"], 1)] = e["conns"]
gain = [(h, c[h][t_a], c[h][t_b]) for h in c if h != me and t_a in c[h] and t_b in c[h] and c[h][t_b] > c[h][t_a]]
print(f"hosts whose conns rose between {t_a} and {t_b}: {len(gain)}")
for h, a, b in sorted(gain, key=lambda x: rtt(x[0])):
    print(f"  {h} {hosts[h]['region']} {hosts[h]['link']} {hosts[h].get('client')} conns {a}->{b} rtt {rtt(h):.1f} ms -> established ~{dial + 2 * rtt(h) / 1e3:.3f} s (first dial + 2 RTT)")
