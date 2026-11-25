"""Mainnet-realism perturbations for gen_config.py flood runs. Each one is behind its own flag (add_args);
sources for every default are in results/realism-calibration.md.

    --net cities          12-city RTT matrix (WonderNetwork), node shares from Probelab
    --access              home links get fiber/cable/DSL access latency (FCC MBA)
    --jitter              per-packet exponential delay on access and backbone edges (needs the jitter Shadow patch)
    --loss                packet loss on access and backbone edges
    --churn-*             connection churn, restarts, leaves and joins
    --bg                  background traffic: blocks, data columns, attestations, aggregates, sync contributions
    --verify              verification delay before forwarding, per message kind; slow CPUs on some home hosts
    --scoring             gossipsub v1.1 peer scoring with Lighthouse's parameters
    --client-mix          per-client peer targets (and with --client-gs per-client gossipsub parameters)
    --nat-share F         share of home hosts behind NAT (no inbound, not discoverable)
    --bad-share/--freeride-share   misbehaving peers
"""

import json
import math
import os
import random
from collections import defaultdict

# ---------------------------------------------------------------- network
# (name, weight %). Probelab 24 h country shares of ~8.2k dialable CL nodes (2026-11-05): US 31.4 (east:west
# 1,964:607 by city), CA 3.8 (-> us-east), DE 15.5, FI 6.3, FR 5.3, GB 4.2 (+IE), NL 3.3, JP 4.5, SG 3.6, AU 1.9;
# the 20 % "other" is spread over the nearest hub (Europe ~12, Asia ~3, South America 2 [36 Coins, arXiv 2511.15388]).
CITIES = [("us-east", 27.7), ("us-west", 7.5), ("lon", 6.5), ("fra", 19.5), ("ams", 5.5), ("par", 7.0),
          ("hel", 6.3), ("tyo", 5.5), ("sin", 5.0), ("sel", 2.0), ("syd", 1.9), ("gru", 2.0)]
CITY_NAMES = [c for c, _ in CITIES]
CITY_WEIGHTS = [w for _, w in CITIES]
# RTT in ms, WonderNetwork averages fetched 2026-11-06 (us-east = New York, us-west = San Francisco). Pairs marked
# e are estimates from neighbouring measured pairs (e.g. ams ~ lon/fra), not measurements.
_RTT = {
    ("us-east", "us-west"): 63, ("us-east", "lon"): 70, ("us-east", "fra"): 91, ("us-east", "ams"): 76,
    ("us-east", "par"): 82, ("us-east", "hel"): 116, ("us-east", "tyo"): 166, ("us-east", "sin"): 228,
    ("us-east", "sel"): 204, ("us-east", "syd"): 197, ("us-east", "gru"): 110,
    ("us-west", "lon"): 140, ("us-west", "fra"): 156, ("us-west", "ams"): 148, ("us-west", "par"): 148,  # e, e
    ("us-west", "hel"): 180, ("us-west", "tyo"): 104, ("us-west", "sin"): 173, ("us-west", "sel"): 135,  # e, -, -, e
    ("us-west", "syd"): 149, ("us-west", "gru"): 173,  # -, e
    ("lon", "fra"): 18, ("lon", "ams"): 8, ("lon", "par"): 8, ("lon", "hel"): 33, ("lon", "tyo"): 242,
    ("lon", "sin"): 155, ("lon", "sel"): 232, ("lon", "syd"): 255, ("lon", "gru"): 193,
    ("fra", "ams"): 11, ("fra", "par"): 17, ("fra", "hel"): 26, ("fra", "tyo"): 233, ("fra", "sin"): 157,
    ("fra", "sel"): 235, ("fra", "syd"): 248, ("fra", "gru"): 205,  # e, -, e
    ("ams", "par"): 14, ("ams", "hel"): 30, ("ams", "tyo"): 235, ("ams", "sin"): 155, ("ams", "sel"): 235,  # all e
    ("ams", "syd"): 250, ("ams", "gru"): 195,  # e
    ("par", "hel"): 40, ("par", "tyo"): 240, ("par", "sin"): 150, ("par", "sel"): 242,  # e, e, e, measured
    ("par", "syd"): 255, ("par", "gru"): 190,  # e
    ("hel", "tyo"): 260, ("hel", "sin"): 177, ("hel", "sel"): 250, ("hel", "syd"): 275, ("hel", "gru"): 225,  # -,-,e,e,e
    ("tyo", "sin"): 66, ("tyo", "sel"): 31, ("tyo", "syd"): 99, ("tyo", "gru"): 255,  # e
    ("sin", "sel"): 83, ("sin", "syd"): 92, ("sin", "gru"): 324,
    ("sel", "syd"): 166, ("sel", "gru"): 290,  # e
    ("syd", "gru"): 313,
}
INTRA_CITY_RTT = 2.0  # same metro, data centre to data centre (WonderNetwork same-city pings 1-2 ms)


def rtt(a, b):
    return INTRA_CITY_RTT if a == b else _RTT.get((a, b)) or _RTT[(b, a)]


CONTINENT = {"us-east": "NA", "us-west": "NA", "lon": "EU", "fra": "EU", "ams": "EU", "par": "EU", "hel": "EU",
             "tyo": "AS", "sin": "AS", "sel": "AS", "syd": "OC", "gru": "SA"}
# Home access technologies: (name, share, one-way ms, jitter mean ms, loss).
# Latency: FCC MBA 13th report (2022 data) median idle RTT fiber 7-14, cable 12-24, DSL 23-34 ms to the nearest
# server; one-way = (mid-range RTT - 2 ms metro) / 2. Shares: OECD fixed broadband by technology (2024): fibre ~45 %,
# cable ~33 %, DSL ~22 % (rounded). Jitter: no published distribution; 0.5/1.5/2.5 ms one-way mean is an estimate
# within the 1-5 ms residential range. Loss: FCC MBA 12th: "packet loss of a few tenths of a percent is common", DSL
# worst; per-direction values are estimates.
ACCESS = [("fiber", 0.45, 4.0, 0.5, 0.0005), ("cable", 0.33, 8.0, 1.5, 0.001), ("dsl", 0.22, 13.0, 2.5, 0.0025)]
BACKBONE_JITTER_MS = 0.3   # WonderNetwork mdev 0.6-2.3 ms on RTT for long paths
LOSS_INTRA = 0.0001        # ThousandEyes cloud benchmark: inter-region loss < 0.1 %
LOSS_INTER = 0.0005


def add_args(ap):
    g = ap.add_argument_group("realism (sim/perturb.py)")
    g.add_argument("--net", choices=["regions", "cities"], default="regions",
                   help="cities: 12-city WonderNetwork RTT matrix with Probelab node shares")
    g.add_argument("--access", action="store_true", help="with --net cities: home hosts get fiber/cable/DSL access latency")
    g.add_argument("--jitter", action="store_true", help="per-packet exponential delay (needs shadow-3.3-jitter.patch)")
    g.add_argument("--loss", action="store_true", help="packet loss on access (home) and backbone edges")
    g.add_argument("--loss-scale", type=float, default=1.0, help="multiply all loss rates (validation)")
    g.add_argument("--churn-conn-life", type=float, help="mean connection lifetime (s) after warm-up")
    g.add_argument("--churn-restart-per-day", type=float, default=0.0,
                   help="restarts per node per day (state lost; down 30-90 s)")
    g.add_argument("--churn-leave", type=float, default=0.0, help="share of hosts that leave for good during the run")
    g.add_argument("--churn-join", type=float, default=0.0, help="share of hosts that join during the run")
    g.add_argument("--bg", action="store_true", help="background traffic (blocks, columns, attestations, aggregates)")
    g.add_argument("--active-validators", type=int, default=823_366, help="mainnet active validators (2026-10-22)")
    g.add_argument("--blobs-mean", type=float, default=5.7, help="blobs per block, Poisson mean (7-day avg Sep 2026)")
    g.add_argument("--blobs-max", type=int, default=21, help="BPO2 max blobs per block")
    g.add_argument("--block-pub-median", type=float, default=1.8,
                   help="block publish time after slot start, lognormal median (s): winning bid (median 1,004 ms) plus "
                        "the proposer -> relay -> publish round trip; fitted to Xatu first-seen p50/p90 (C2 -> C3)")
    g.add_argument("--block-pub-sigma", type=float, default=0.45, help="lognormal sigma (fitted, see --block-pub-median)")
    g.add_argument("--mev-share", type=float, default=0.9, help="blocks published by a relay (cloud host)")
    g.add_argument("--duty-spread-median", type=float, default=0.35,
                   help="attestations (after 4 s) and aggregates / sync contributions (after 8 s): lognormal publish "
                        "delay, median (s); 0 = uniform over 0.3 s / 0.2 s as before")
    g.add_argument("--duty-spread-sigma", type=float, default=0.8, help="lognormal sigma of the duty publish delay")
    g.add_argument("--att-track", type=float, default=0.05, help="share of attestations whose receipts are logged")
    g.add_argument("--agg-track", type=float, default=0.2, help="share of aggregates whose receipts are logged")
    g.add_argument("--all-subnets-above", type=int, default=64,
                   help="hosts with at least this many validators subscribe to all 64 attestation subnets")
    g.add_argument("--verify", action="store_true", help="verification delay before forwarding, per message kind")
    g.add_argument("--verify-us", default="pq=400,block=10000,col=1500,att=600,agg=2500,syncc=2000",
                   help="µs per signature by kind (col: per blob)")
    g.add_argument("--workers-home", type=int, default=4)
    g.add_argument("--workers-cloud", type=int, default=8)
    g.add_argument("--slow-cpu-share", type=float, default=0.0, help="share of home hosts with a slow CPU")
    g.add_argument("--slow-cpu-factor", type=float, default=3.0)
    g.add_argument("--scoring", action="store_true", help="gossipsub v1.1 peer scoring, Lighthouse parameters")
    g.add_argument("--score-slow-peer-weight", type=float, help="with --scoring: override slow-peer weight (-10)")
    g.add_argument("--score-disconnect", action="store_true", help="with --scoring: disconnect peers below -4000")
    g.add_argument("--client-mix", action="store_true", help="per-client peer targets (Probelab client shares)")
    g.add_argument("--client-gs", action="store_true", help="with --client-mix: per-client gossipsub parameters")
    g.add_argument("--peer-scale", type=float, default=1.0, help="with --client-mix: scale every client's peer target")
    g.add_argument("--nat-share", type=float, default=0.0, help="share of home hosts behind NAT")
    g.add_argument("--bad-share", type=float, default=0.0, help="share of hosts that publish invalid messages")
    g.add_argument("--bad-rate", type=int, default=5, help="invalid messages per bad host per slot")
    g.add_argument("--freeride-share", type=float, default=0.0, help="share of hosts that never forward")
    g.add_argument("--ping", type=float, help="libp2p ping interval (s); RTTs logged for validation")
    g.add_argument("--no-pq", action="store_true", help="no PQ signatures (today's BLS load only)")


def active(a):
    return any([a.net != "regions", a.bg, a.verify, a.scoring, a.client_mix, a.nat_share, a.bad_share,
                a.freeride_share, a.churn_conn_life, a.churn_restart_per_day, a.churn_leave, a.churn_join, a.ping,
                a.no_pq])


# ---------------------------------------------------------------- GML
def gml(a, regions_mode_gml):
    """Network graph text, and a function (host index, city, home access or None) -> network node id."""
    if a.net == "regions":
        return regions_mode_gml, None
    C, A = len(CITY_NAMES), len(ACCESS)
    us = lambda ms: f'"{int(round(ms * 1000))} us"'
    lines = ["graph [", "  directed 0"]
    for i in range(C + C * A):
        lines += ["  node [", f"    id {i}", '    host_bandwidth_down "1 Gbit"', '    host_bandwidth_up "1 Gbit"', "  ]"]

    def edge(s, t, lat, jit, loss):
        e = ["  edge [", f"    source {s}", f"    target {t}", f"    latency {us(lat)}"]
        if a.jitter and jit > 0:
            e.append(f"    jitter {us(jit)}")
        e += [f"    packet_loss {loss * a.loss_scale if a.loss else 0.0:.6f}", "  ]"]
        return e
    for i, x in enumerate(CITY_NAMES):
        for j, y in enumerate(CITY_NAMES):
            if j >= i:
                inter = CONTINENT[x] != CONTINENT[y]
                lines += edge(i, j, rtt(x, y) / 2, BACKBONE_JITTER_MS if i != j else 0.0,
                              LOSS_INTER if inter else LOSS_INTRA if i != j else 0.0)
    for c in range(C):
        for k, (_, _, ow, jit, loss) in enumerate(ACCESS):
            n = C + c * A + k
            lines += edge(c, n, ow, jit, loss)
            # two home hosts on the same access node: both access links plus the metro
            lines += edge(n, n, 2 * ow + INTRA_CITY_RTT / 2, 2 * jit, 1 - (1 - loss) ** 2)
    lines.append("]")

    def node_id(city, access):
        c = CITY_NAMES.index(city)
        return c if access is None else C + c * A + access
    return "\n".join(lines), node_id


# ---------------------------------------------------------------- clients
# Probelab agent shares (24 h, 2026-11-05); peer targets from client source (sigp/lighthouse a376def
# peer_manager/config.rs L11: 200; prysm cmd/flags.go: 70; teku DiscoveryConfig: 64-100; nimbus conf.nim: 160;
# lodestar options.ts: 200; grandine defaults.rs: 200). Inbound cap: Lighthouse +10 % excess, others ~ +10 %.
# Gossipsub: Lighthouse/Grandine network_load 3 = mesh 5/3/10, gossip_lazy 3, heartbeat 1 s, history 12/3
# (config.rs L385-L531); Prysm spec values; Teku flood publish <= 16 KiB; Nimbus flood publish, gossip_factor 0.05,
# D_out 3; Lodestar flood publish.
CLIENTS = [
    ("lighthouse", 50.5 + 2.1, 200, dict(mesh_n=5, mesh_n_low=3, mesh_n_high=10, gossip_lazy=3, heartbeat_ms=1000,
                                         history_length=12, history_gossip=3)),
    ("prysm", 20.8, 70, {}),
    ("nimbus", 8.9, 160, dict(flood_publish=True, gossip_factor=0.05, mesh_outbound_min=3)),
    ("teku", 7.8, 100, dict(flood_publish=True)),
    ("lodestar", 2.8, 200, dict(flood_publish=True)),
    ("other", 2.6 + 1.1 + 2.5 + 0.8, 200, {}),  # Hermes, Erigon/Caplin, unknown, rust-libp2p: Grandine-like
]


# ---------------------------------------------------------------- apply
def apply(a, rng_seed, nodes, hosts, fast, vcount, full, out, topics_of):
    """Mutates nodes / hosts / run-level settings. Returns extra run.json keys. `full` is the PQ schedule
    (slot -> [publisher, offset ms, topic, bytes, deadline ms, nsigs]); `topics_of(i)` the node's PQ topics."""
    r = random.Random(rng_seed * 104729 + 3)
    n = len(nodes)
    home = [i for i in range(n) if i not in fast]
    extra = {}
    t_first = a.warmup
    t_end = a.warmup + 12 * a.slots

    # access technology per home host (also recorded for the analysis)
    if a.net == "cities":
        for i in range(n):
            acc = None
            if a.access and i not in fast:
                acc = r.choices(range(len(ACCESS)), [x[1] for x in ACCESS])[0]
                nodes[i]["access"] = ACCESS[acc][0]
            nodes[i]["city"] = nodes[i]["region"]
            nodes[i]["_acc"] = acc

    # client mix
    if a.client_mix:
        for i in range(n):
            c = r.choices(range(len(CLIENTS)), [x[1] for x in CLIENTS])[0]
            name, _, target, gs = CLIENTS[c]
            nodes[i]["client"] = name
            nodes[i]["peer_target"] = max(8, round(target * a.peer_scale))
            nodes[i]["peer_max"] = round(nodes[i]["peer_target"] * 1.1) + 1
            if a.client_gs and gs:
                nodes[i]["gs"] = {**gs, **nodes[i].get("gs", {})}

    # NAT: home hosts only (cloud hosts are dialable)
    for i in home:
        if r.random() < a.nat_share:
            nodes[i]["nat"] = True

    # CPU and verification workers
    if a.verify:
        for i in range(n):
            nodes[i]["workers"] = a.workers_cloud if i in fast else a.workers_home
            if i not in fast and r.random() < a.slow_cpu_share:
                nodes[i]["cpu"] = a.slow_cpu_factor
        kinds = dict(kv.split("=") for kv in a.verify_us.split(","))
        extra["verify_us_kind"] = [int(kinds.get(k, 0)) for k in KINDS]

    # misbehaving peers
    bad = set(r.sample(range(n), round(n * a.bad_share))) if a.bad_share else set()
    for i in bad:
        nodes[i]["bad"] = True
    if a.freeride_share:
        for i in r.sample(range(n), round(n * a.freeride_share)):
            nodes[i]["gs"] = {**nodes[i].get("gs", {}), "no_forward": True}
            nodes[i]["freeride"] = True
            nodes[i].pop("home", None)  # a no_forward leaf still forwards in its home topic; free-riders forward nowhere

    # churn: offline intervals [from, to)
    pq_lost = 0
    for i in range(n):
        off = []
        rate = a.churn_restart_per_day / 86400.0
        t = t_first
        while rate > 0:
            t += r.expovariate(rate)
            if t >= t_end:
                break
            d = r.uniform(30, 90)  # beacon node restart: process restart + peer discovery (estimate)
            off.append((t, t + d))
            t += d
        u = r.random()
        if u < a.churn_leave:
            off.append((r.uniform(t_first, t_end), 1e9))
        elif u < a.churn_leave + a.churn_join:
            off.append((0.0, r.uniform(t_first, t_end)))
        if off:
            nodes[i]["offline"] = sorted(off)
    offline = lambda i, t: any(x <= t < y for x, y in nodes[i].get("offline", []))
    if any("offline" in nd for nd in nodes):
        # signatures of validators whose host is down at publish time never exist
        for s_, msgs in enumerate(full):
            keep = [m for m in msgs if not offline(m[0], t_first + 12 * s_ + m[1] / 1e3)]
            pq_lost += len(msgs) - len(keep)
            msgs[:] = keep
    extra["pq_lost_to_churn"] = pq_lost
    if a.churn_conn_life:
        extra["conn_life_s"] = a.churn_conn_life
        extra["pm_refill"] = True

    # topics: PQ + background subscriptions
    for i in range(n):
        ts = list(topics_of(i)) if not a.no_pq else []
        if a.bg:
            ts += [T_BLOCK, T_AGG, T_SYNCC]
            all64 = vcount[i] >= a.all_subnets_above
            ts += [T_ATT + s for s in (range(64) if all64 else sorted(r.sample(range(64), 2)))]
            cust = 128 if vcount[i] >= 128 else (min(128, max(8, vcount[i])) if vcount[i] else 4)
            ts += [T_COL + c for c in sorted(r.sample(range(128), cust))]
            nodes[i]["custody"] = cust
        nodes[i]["topics"] = ts or [0]

    # per-node publish files
    pubs = defaultdict(list)
    for s_, msgs in enumerate(full):
        for k, m in enumerate(msgs):
            pubs[m[0]].append([s_, k, m[1], m[2], m[3], m[5] if len(m) > 5 else 1, K["pq"], 1])
    bg = []
    if a.bg:
        relays = sorted(r.sample(sorted(fast), min(8, len(fast))))
        w = [max(v, 0) for v in vcount]
        n_att = round(a.active_validators / 32)
        n_agg = 64 * 16
        # validator-client duty timing: VC -> BN -> publish, clock skew. Missed-slot attestations (all due at 4 s)
        # arrive 0.83 s after 4 s on average (ethresear.ch 23016); the lognormal is fitted so arrivals match.
        duty = (lambda u: int(1000 * min(3.5, r.lognormvariate(math.log(a.duty_spread_median), a.duty_spread_sigma)))) \
            if a.duty_spread_median > 0 else (lambda u: int(r.random() * u))
        for s_ in range(a.slots):
            ms = []  # [publisher, offset ms, topic, bytes, kind, track]
            prop = r.choices(range(n), w)[0]
            pub = r.choice(relays) if relays and r.random() < a.mev_share else prop
            t_blk = int(1000 * min(8.0, r.lognormvariate(math.log(a.block_pub_median), a.block_pub_sigma)))
            size = int(min(400_000, r.lognormvariate(math.log(70_000), 0.35)))  # Probelab: 59.6 % in 50-100 kB
            ms.append([pub, t_blk, T_BLOCK, size, K["block"], 1, 1])
            nb = min(a.blobs_max, poisson(r, a.blobs_mean))
            if nb:
                for c in range(128):
                    ms.append([pub, t_blk + 50, T_COL + c, 356 + 2144 * nb, K["col"], 1, nb])
            for _ in range(n_att):
                ms.append([r.choices(range(n), w)[0], 4000 + duty(300), T_ATT + r.randrange(64), 240,
                           K["att"], int(r.random() < a.att_track), 1])
            for _ in range(n_agg):
                ms.append([r.choices(range(n), w)[0], 8000 + duty(200), T_AGG, 495, K["agg"],
                           int(r.random() < a.agg_track), 1])
            for _ in range(64):
                ms.append([r.choices(range(n), w)[0], 8000 + duty(200), T_SYNCC, 360, K["syncc"], 0, 1])
            for i in sorted(bad):
                for _ in range(a.bad_rate):
                    ms.append([i, 4000 + int(r.random() * 4000), T_AGG, 495, K["bad"], 0, 1])
            ms = [m for m in ms if not offline(m[0], t_first + 12 * s_ + m[1] / 1e3)]
            for k, m in enumerate(ms):
                pubs[m[0]].append([s_, k, m[1], m[2], m[3], m[6], m[4], m[5]])
            bg.append([m[:6] for m in ms])
    elif bad:
        for s_ in range(a.slots):
            for i in sorted(bad):
                for _ in range(a.bad_rate):
                    pubs[i].append([s_, 1_000_000 + len(pubs[i]), 4000 + int(r.random() * 4000), nodes[i]["topics"][0],
                                    495, 1, K["bad"], 0])
    d = os.path.join(out, "pubs")
    os.makedirs(d, exist_ok=True)
    for i in range(n):
        with open(os.path.join(d, f"{i}.json"), "w") as f:
            json.dump(sorted(pubs.get(i, []), key=lambda p: (p[0], p[2])), f)
    if bg:
        with open(os.path.join(out, "bg.json"), "w") as f:
            json.dump(bg, f)
    extra["pub_dir"] = d
    extra["pq_counts"] = [len(m) for m in full]
    if a.scoring:
        extra["scoring"] = dict(active_validators=a.active_validators, pq_subnets=0 if a.no_pq else a.sig_subnets,
                                pq_rate=(a.msgs / max(a.sig_subnets, 1)) if not a.no_pq else 0,
                                disconnect_below_gossip=a.score_disconnect, slow_peer_weight=a.score_slow_peer_weight)
    if a.ping:
        extra["ping_s"] = a.ping
    extra["loss_scale"] = a.loss_scale if a.loss else 0.0
    for nd in nodes:
        nd.pop("_acc", None) if a.net != "cities" else None
    return extra


KINDS = ["pq", "block", "col", "att", "agg", "sync", "syncc", "bad"]
K = {k: i for i, k in enumerate(KINDS)}
T_BLOCK, T_AGG, T_SYNCC, T_ATT, T_COL = 100, 101, 102, 200, 400


def poisson(r, lam):
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= r.random()
        if p <= l:
            return k
        k += 1
