#!/usr/bin/env python3
"""Generate a Shadow experiment for the subnets one mainnet node joins.

    python3 sim/gen_config.py --mode direct --out runs/direct
    cd runs/direct && shadow shadow.yaml > shadow.log

Defaults model what one node sees at 800k validators / 32 slots: it joins 2 of
the 64 subnets (391 votes each per slot), and a subnet has ~312 members
(10,000 nodes x 2 / 64). So 312 hosts, all in both subnets in gossip mode.

- gossip: 16 aggregators per subnet aggregate the subnet and gossip proofs.
- direct: each subnet's votes are split into --topics-per-subnet topics
  (1 at 32 slots; 4 at the 8-slot DC cadence, 1,560 votes per subnet), each
  with --aggregators direct recipients. The proposer pulls best + random per
  topic, so with 8 topics it plays an internal aggregator with 8 children.

The host set, regions and links are the same in both modes for a seed.

- flood: every host joins one topic; each slot --msgs distinct messages of
  --msg-bytes are published by uniformly random hosts at 4 s + U[0, --publish-window)
  into the slot. Links: --links DOWN/UP (Mbit/s) for most hosts, --fast-share on 1 Gbit.

    python3 sim/gen_config.py --mode flood --msgs 2000 --links 25/10 --fast-share 0.1 --out runs/f
"""

import argparse
import csv
import json
import os
import random
import math
from collections import defaultdict
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import perturb  # noqa: E402  mainnet-realism perturbations (flood mode)

# Mainnet-like node geography and one-way latencies (ms) between regions.
REGIONS = ["na-east", "na-west", "europe", "asia", "oceania"]
WEIGHTS = [0.20, 0.15, 0.45, 0.15, 0.05]
ONE_WAY_MS = {
    ("na-east", "na-east"): 10, ("na-west", "na-west"): 10, ("europe", "europe"): 10,
    ("asia", "asia"): 15, ("oceania", "oceania"): 10,
    ("na-east", "na-west"): 35, ("na-east", "europe"): 40, ("na-east", "asia"): 110,
    ("na-east", "oceania"): 100, ("na-west", "europe"): 70, ("na-west", "asia"): 65,
    ("na-west", "oceania"): 75, ("europe", "asia"): 90, ("europe", "oceania"): 140,
    ("asia", "oceania"): 50,
}
HOME = ("50 Mbit", "25 Mbit")   # down, up (eth-slot-sim home profile)
CLOUD = ("1 Gbit", "1 Gbit")
# EIP-7870 recommendations (down, up); HOME equals the EIP-7870 attester limit
ATTESTER = HOME
BUILDER = ("100 Mbit", "50 Mbit")
ATTESTER_MIN = ("50 Mbit", "15 Mbit")  # EIP-7870 "minimum tested" upload
PROFILES = {
    # name: (aggregator, proposer, voter-or-None for the home/cloud mix)
    "legacy": (CLOUD, HOME, None),  # first runs: 50 % home 50/25, all aggregators 1 Gbit
    # 80 % of voters at EIP-7870 attester limits, 20 % 1 Gbit; most aggregators 1 Gbit
    "eip7870-mix": (None, BUILDER, None),
    "eip7870": (ATTESTER, BUILDER, ATTESTER),
    "eip7870-min": (None, BUILDER, "min"),
}
LINK_NAMES = {HOME: "home", CLOUD: "cloud", BUILDER: "builder", ATTESTER_MIN: "attester-15up"}


def latency(a, b):
    return ONE_WAY_MS.get((a, b)) or ONE_WAY_MS[(b, a)]


def gml_regions():
    lines = ["graph [", "  directed 0"]
    for i, _ in enumerate(REGIONS):
        lines += ["  node [", f"    id {i}", '    host_bandwidth_down "1 Gbit"', '    host_bandwidth_up "1 Gbit"', "  ]"]
    for i, a in enumerate(REGIONS):
        for j, b in enumerate(REGIONS):
            if j >= i:
                lines += ["  edge [", f"    source {i}", f"    target {j}", f'    latency "{latency(a, b)} ms"',
                          "    packet_loss 0.0", "  ]"]
    lines.append("]")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["gossip", "direct", "flood"], required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--hosts", type=int, default=312, help="hosts (subnet members): aggregators + proposer + voters")
    ap.add_argument("--subnets", type=int, default=2, help="gossip subnets, all joined by every node")
    ap.add_argument("--votes", type=int, default=391, help="votes per subnet per slot (1,560 at the 8-slot cadence)")
    ap.add_argument("--topics-per-subnet", type=int, default=1, help="direct topics per subnet (4 at the 8-slot cadence)")
    ap.add_argument("--aggregators", type=int, default=16, help="direct recipients per topic; gossip aggregators per subnet")
    ap.add_argument("--profile", choices=list(PROFILES), default="eip7870-mix",
                    help="eip7870-mix (default): EIP-7870 limits; eip7870-min: attesters at 15 Mbit/s upload")
    ap.add_argument("--agg-cloud-share", type=float, default=0.75,
                    help="eip7870-mix / -min: share of aggregators on 1 Gbit (rest at attester limits)")
    ap.add_argument("--proposer-link", choices=["home", "builder", "cloud"], help="override the proposer's link")
    ap.add_argument("--home-share", type=float, default=0.8, help="share of voter nodes at EIP-7870 attester limits")
    ap.add_argument("--vote-bytes", type=int, default=3104 + 168)
    ap.add_argument("--proof-bytes", type=int, default=220 * 1024)
    ap.add_argument("--slots", type=int, default=5)
    ap.add_argument("--prove-ms", type=int, default=1450, help="391 sigs at 270 sigs/s (8 cores)")
    ap.add_argument("--cold-connect", action="store_true")
    ap.add_argument("--batch-votes", action="store_true",
                    help="direct mode: each node sends all its votes of a slot to a recipient in one message")
    ap.add_argument("--proofs", choices=["flood", "pull", "decoy"],
                    help="flood on an aggregate topic every node joins (gossip default), announce-then-pull "
                         "(direct default), or push to --decoys nodes that include the proposer")
    ap.add_argument("--decoys", type=int, default=16, help="--proofs decoy: size of the set, proposer included")
    ap.add_argument("--attester-votes", type=int,
                    help="votes per slot on each attester-link voter; the rest go to the 1 Gbit voters "
                         "(default: spread evenly over all voters)")
    ap.add_argument("--msgs", type=int, default=2000, help="flood: messages per slot")
    ap.add_argument("--msg-bytes", type=int, default=3072, help="flood: message payload (XMSS signature size)")
    ap.add_argument("--publish-window", type=float, default=0.5, help="flood: publish times spread over this (s)")
    ap.add_argument("--links", default="25/10", help="flood: DOWN/UP Mbit/s of the slow majority")
    ap.add_argument("--fast-share", type=float, default=0.1, help="flood: share of hosts on 1 Gbit/1 Gbit")
    ap.add_argument("--gossip-dial", type=int, default=10, help="random peers each host dials (~2x this many connections)")
    ap.add_argument("--drain", type=float, default=12.0, help="flood: seconds simulated after the last slot")
    ap.add_argument("--bin", type=float, default=0.5, help="flood: counter snapshot interval (s)")
    ap.add_argument("--pcap", type=int, default=0,
                    help="flood: capture packet headers on this many slow and 1 fast host (link-cap check)")
    ap.add_argument("--validators-csv",
                    help="flood: mainnet peer list with a validator_count column; hosts are sampled from its rows and "
                         "each message's publisher is drawn in proportion to validators per host (default: uniform)")
    ap.add_argument("--fast-above", type=int,
                    help="flood: hosts with more than this many validators get 1 Gbit; of the rest, --fast-share get "
                         "1 Gbit, validator hosts get --links and hosts without validators --links-novalidator")
    ap.add_argument("--links-novalidator", help="flood with --fast-above: DOWN/UP of hosts without validators "
                                                "(default: --links)")
    # flood: protocol and requirement levers (see results/gossip-2000-improvements.md)
    ap.add_argument("--gs", default="", help="flood: gossipsub overrides for every node, k=v,... (wbsim GsCfg fields)")
    ap.add_argument("--gs-slow", default="", help="flood: gossipsub overrides for hosts not on 1 Gbit")
    ap.add_argument("--fixed-send-buffer", type=int, metavar="BYTES",
                    help="disable Shadow send-buffer autotuning and fix every socket's send buffer at BYTES")
    ap.add_argument("--gs-fast", default="", help="flood: gossipsub overrides for 1 Gbit hosts")
    ap.add_argument("--dial-policy", choices=["random", "slow-to-fast"], default="random",
                    help="flood: slow-to-fast = hosts not on 1 Gbit dial only 1 Gbit hosts")
    ap.add_argument("--dial-local", action="store_true",
                    help="flood with --dial-policy slow-to-fast: slow hosts dial 1 Gbit hosts in their own region "
                         "(topped up from other regions if there are too few)")
    ap.add_argument("--dial-slow", type=int, help="flood: peers each slow host dials (default --gossip-dial)")
    ap.add_argument("--sig-subnets", type=int, default=1,
                    help="flood: split the signatures over this many topics (a validator's subnet is random)")
    ap.add_argument("--slow-joins", type=int, default=1,
                    help="flood with --sig-subnets: topics each host not on 1 Gbit joins (1 Gbit hosts join all)")
    ap.add_argument("--hybrid", action="store_true",
                    help="flood with --sig-subnets: every host joins every subnet; each host not on 1 Gbit forwards only in "
                         "one home subnet (where its own signatures go) and is a non-forwarding leaf in the others "
                         "(set no_forward=true and home_mesh_* in --gs-slow)")
    ap.add_argument("--one-subnet", action="store_true",
                    help="flood with --sig-subnets: each host not on 1 Gbit joins only its home subnet (where its own "
                         "signatures go; random for hosts without validators); 1 Gbit hosts join all")
    ap.add_argument("--peer-target", type=int,
                    help="flood: wbsim peer manager keeps this many peers by random + subnet discovery (no static dials)")
    ap.add_argument("--peer-max", type=int, help="flood with --peer-target: refuse inbound beyond this many peers")
    ap.add_argument("--subnet-min-peers", type=int, default=6,
                    help="flood with --peer-target: subnet discovery keeps at least this many peers per joined topic")
    ap.add_argument("--warmup", type=float, default=20.0, help="flood: seconds before slot 0 starts")
    ap.add_argument("--dial-home", type=int, default=0,
                    help="flood with --hybrid: each host not on 1 Gbit also dials this many other such hosts with the "
                         "same home subnet (on top of its other dials)")
    ap.add_argument("--dial-fast", type=int, default=0,
                    help="flood: each host not on 1 Gbit also dials this many random 1 Gbit hosts (on top of its "
                         "other dials)")
    ap.add_argument("--consolidate", type=float,
                    help="flood with --validators-csv: shrink the validator set to this fraction by merging each "
                         "operator's validators: n -> ceil(n / m), one m for the whole CSV chosen to hit the fraction "
                         "(hosts with 1 validator keep 1)")
    ap.add_argument("--aggregates", type=int, default=0,
                    help="flood with --sig-subnets: 1 Gbit aggregators per subnet that publish one aggregate each "
                         "on the global topic, which every host joins and must receive")
    ap.add_argument("--agg-bytes", type=int, default=220 * 1024)
    ap.add_argument("--agg-at-ms", type=int, default=9450, help="aggregate publish time after slot start")
    ap.add_argument("--agg-deadline-ms", type=int, default=12000)
    ap.add_argument("--batch", type=int, default=0,
                    help="flood: each publisher packs up to this many of its own signatures per message")
    ap.add_argument("--scale-links", action="store_true",
                    help="flood: a host with n validators gets n x --links (DOWN/UP), capped at 1 Gbit each way, instead "
                         "of the --fast-above rule; hosts without validators keep --links-novalidator")
    ap.add_argument("--bundler", type=int, default=0,
                    help="flood: first-hop bundling; each signature goes to a random 1 Gbit bundler, which publishes "
                         "bundles of this many once the last one has arrived (+ --bundle-hop-ms)")
    ap.add_argument("--bundlers", type=int, default=16, help="flood with --bundler: number of 1 Gbit bundlers")
    ap.add_argument("--bundle-hop-ms", type=int, default=150,
                    help="flood with --bundler: signer to bundler delay (one hop, not simulated on the wire)")
    ap.add_argument("--publish-start", type=float, default=4.0, help="flood: publishing starts this far into the slot")
    ap.add_argument("--deadline-ms", type=int,
                    help="flood: absolute deadline after slot start (default publish start + 4 s)")
    ap.add_argument("--rel-deadline-ms", type=int,
                    help="flood: deadline relative to each message's publish time instead of absolute")
    ap.add_argument("--no-cpu-pinning", action="store_true",
                    help="unpin Shadow's workers; needed to run several Shadow instances side by side, since "
                         "each would otherwise pin to the same first cores")
    perturb.add_args(ap)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--parallelism", type=int, default=os.cpu_count())
    ap.add_argument("--binary", default=os.path.abspath(os.path.join(os.path.dirname(__file__), "wbsim/target/release/wbsim")))
    a = ap.parse_args()

    rng = random.Random(a.seed)
    os.makedirs(a.out, exist_ok=True)
    out = os.path.abspath(a.out)
    if a.mode == "flood":
        return flood(a, rng, out)

    nodes, hosts = [], {}
    topics = a.subnets * a.topics_per_subnet
    assert a.votes % a.topics_per_subnet == 0, "votes per subnet must split evenly into topics"
    per_topic = a.votes // a.topics_per_subnet
    n_aggs = topics * a.aggregators
    roles = ["aggregator"] * n_aggs + ["proposer"] + ["voter"] * (a.hosts - n_aggs - 1)
    voter_ids = [i for i, r in enumerate(roles) if r == "voter"]
    validators = {i: [] for i in range(len(roles))}
    links = {}

    for i, role in enumerate(roles):
        topic, j = divmod(i, a.aggregators) if role == "aggregator" else (0, 0)
        ip = f"11.0.{i // 200}.{i % 200 + 1}"
        region = rng.choices(REGIONS, WEIGHTS)[0]
        agg_bw, prop_bw, voter_bw = PROFILES[a.profile]
        if role == "aggregator":
            bw = agg_bw or (CLOUD if j < round(a.aggregators * a.agg_cloud_share) else ATTESTER)
        elif role == "proposer":
            bw = {"home": HOME, "builder": BUILDER, "cloud": CLOUD}.get(a.proposer_link, prop_bw)
        else:
            mix = HOME if rng.random() < a.home_share else CLOUD  # draw always: same regions per seed
            if voter_bw == "min":
                bw = ATTESTER_MIN if mix == HOME else CLOUD
            else:
                bw = voter_bw or mix
        link = "attester" if bw == ATTESTER and a.profile != "legacy" else LINK_NAMES[bw]
        links[i] = link
        cls = role if role != "voter" else f"voter-{link}"
        if a.mode == "gossip" and role == "aggregator" and topic % a.topics_per_subnet:
            role, cls = "voter", f"member-{link}"  # extra direct recipients: plain subnet members here
        nodes.append(dict(id=i, ip=ip, role=role, cls=cls, topic=topic, validators=validators[i],
                          region=region, link=link))
        hosts[f"n{i:04d}"] = dict(
            network_node_id=REGIONS.index(region), ip_addr=ip,
            bandwidth_down=bw[0], bandwidth_up=bw[1],
            processes=[dict(path=a.binary, args=f"--cfg {out}/run.json --id {i}",
                            start_time="1s", expected_final_state={"exited": 0})])

    # validators: evenly over voters, or a fixed number per attester-link voter
    total = a.votes * a.subnets
    if a.attester_votes is None:
        owners = [voter_ids[v % len(voter_ids)] for v in range(total)]
    else:
        slow = [i for i in voter_ids if links[i] not in ("cloud",)]
        fast = [i for i in voter_ids if links[i] == "cloud"]
        owners = [i for i in slow for _ in range(a.attester_votes)][:total]
        owners += [fast[k % len(fast)] for k in range(total - len(owners))]
    for v, i in enumerate(owners):
        validators[i].append(v)  # same list object as in nodes[i]

    proofs = a.proofs or ("flood" if a.mode == "gossip" else "pull")
    prop = roles.index("proposer")
    others = [i for i, r in enumerate(roles) if r == "voter"]
    decoys = sorted([prop] + rng.sample(others, a.decoys - 1)) if proofs == "decoy" else []

    first_slot = 20.0
    run = dict(mode=a.mode, seed=a.seed, nodes=nodes, topics=topics, subnets=a.subnets,
               votes_per_topic=per_topic, profile=a.profile, vote_bytes=a.vote_bytes, proof_bytes=a.proof_bytes,
               first_slot_s=first_slot, slot_s=12.0, slots=a.slots, vote_offset_s=4.0, vote_jitter_s=0.5,
               agg_deadline_s=8.0, prove_ms=a.prove_ms, proofs=proofs, decoys=decoys, gossip_dial=10, cold_connect=a.cold_connect,
               batch_votes=a.batch_votes,
               announce_wait_ms=500)
    with open(f"{out}/run.json", "w") as f:
        json.dump(run, f, indent=1)

    stop = int(first_slot + 12 * a.slots + 3)
    write_yaml(out, hosts, stop, a)
    print(f"{out}: {len(nodes)} hosts, mode={a.mode}, {a.subnets} subnets x {a.votes} votes, "
          f"{topics} direct topics, stop={stop}s")


def flood(a, rng, out):
    """One topic, --msgs messages per slot from random publishers."""
    n_fast = round(a.hosts * a.fast_share)
    regions = [rng.choices(REGIONS, WEIGHTS)[0] if a.net == "regions"
               else rng.choices(perturb.CITY_NAMES, perturb.CITY_WEIGHTS)[0] for _ in range(a.hosts)]
    if a.validators_csv:
        csv.field_size_limit(sys.maxsize)
        counts = [int(r["validator_count"]) for r in csv.DictReader(open(a.validators_csv))]
        if a.consolidate:
            tgt, lo, hi = a.consolidate * sum(counts), 1.0, float(max(counts))
            for _ in range(60):
                m = (lo + hi) / 2
                lo, hi = (m, hi) if sum(math.ceil(x / m) for x in counts) > tgt else (lo, m)
            counts = [math.ceil(x / hi) for x in counts]
            print(f"consolidated: merge factor {hi:.3f}, CSV total {sum(counts):,}")
        vcount = rng.sample(counts, a.hosts)
    else:
        vcount = [1] * a.hosts
    if a.fast_above is not None:
        big = {i for i in range(a.hosts) if vcount[i] > a.fast_above}
        small = [i for i in range(a.hosts) if i not in big]
        fast = big | set(rng.sample(small, round(len(small) * a.fast_share)))
        n_fast = len(fast)
    else:
        fast = set(rng.sample(range(a.hosts), n_fast))
    slow_links = lambda i: a.links_novalidator if a.fast_above is not None and a.links_novalidator and not vcount[i] \
        else a.links
    nodes, hosts = [], {}
    if a.scale_links:  # n x EIP-7870 per validator; the 20 % random 1 Gbit share of the base stays
        bd, bu = (int(x) for x in a.links.split("/"))
        fast = {i for i in fast if vcount[i] <= a.fast_above} if a.fast_above is not None else fast
        fast |= {i for i in range(a.hosts) if vcount[i] and min(bu * vcount[i], 1000) == 1000}
        n_fast = len(fast)
    for i in range(a.hosts):
        down, up = (f"{x} Mbit" for x in slow_links(i).split("/"))
        link = slow_links(i).replace("/", "x")
        if a.scale_links and vcount[i] and i not in fast:
            v = vcount[i]
            down, up = f"{min(bd * v, 1000)} Mbit", f"{min(bu * v, 1000)} Mbit"
            link = "v1" if v == 1 else "v2-3" if v <= 3 else "v4-9" if v <= 9 else "v10-39"
        bw = CLOUD if i in fast else (down, up)
        link = "cloud" if i in fast else link
        ip = f"11.0.{i // 200}.{i % 200 + 1}"
        nodes.append(dict(id=i, ip=ip, role="voter", cls=link, topic=0, validators=[], region=regions[i], link=link,
                          down=bw[0], up=bw[1], vcount=vcount[i]))
        hosts[f"n{i:04d}"] = dict(
            network_node_id=REGIONS.index(regions[i]) if a.net == "regions" else 0, ip_addr=ip, bandwidth_down=bw[0], bandwidth_up=bw[1],
            processes=[dict(path=a.binary, args=f"--cfg {out}/run.json --id {i}", start_time="1s")])
    slow = [i for i in range(a.hosts) if i not in fast]
    for i in slow[:a.pcap] + sorted(fast)[:1 if a.pcap else 0]:
        hosts[f"n{i:04d}"]["pcap"] = True
    offset_s = a.publish_start
    # a message comes from a random validator, so from a host in proportion to its validators
    sched = [[(rng.choices(range(a.hosts), vcount)[0], int(1000 * offset_s + rng.random() * 1000 * a.publish_window))
              for _ in range(a.msgs)] for _ in range(a.slots)]
    # levers below draw from their own rng, so hosts, links and publishers stay the same per seed
    r2 = random.Random(a.seed * 7919 + 17)
    deadline = a.deadline_ms or int(1000 * offset_s) + 4000
    dl = (lambda off: off + a.rel_deadline_ms) if a.rel_deadline_ms else (lambda off: deadline)
    ns = a.sig_subnets
    home = {i: 1 + r2.randrange(ns) for i in range(a.hosts) if i not in fast} if a.hybrid or a.one_subnet else {}
    sig_topic = (lambda p: 0) if ns == 1 else (lambda p: home[p] if p in home else 1 + r2.randrange(ns))
    full = []
    for msgs in sched:
        if a.bundler:
            bl = r2.sample(sorted(fast), a.bundlers)
            groups = defaultdict(list)
            for p, off in msgs:
                groups[(r2.choice(bl), sig_topic(p))].append(off)
            out_s = []
            for (b, t), offs in sorted(groups.items()):
                offs.sort()
                for j in range(0, len(offs), a.bundler):
                    chunk = offs[j:j + a.bundler]
                    at = chunk[-1] + a.bundle_hop_ms
                    out_s.append([b, at, t, len(chunk) * a.msg_bytes, dl(chunk[0]), len(chunk)])
            full.append(out_s)
        elif a.batch:
            groups = defaultdict(list)
            for p, off in msgs:
                groups[(p, sig_topic(p))].append(off)
            out_s = []
            for (p, t), offs in sorted(groups.items()):
                offs.sort()
                for j in range(0, len(offs), a.batch):
                    chunk = offs[j:j + a.batch]  # published when its last signature is ready
                    out_s.append([p, chunk[-1], t, len(chunk) * a.msg_bytes, dl(chunk[-1]), len(chunk)])
            full.append(out_s)
        else:
            full.append([[p, off, sig_topic(p), a.msg_bytes, dl(off), 1] for p, off in msgs])
    slow = [i for i in range(a.hosts) if i not in fast]
    fast_l = sorted(fast)
    if ns > 1:
        for i in range(a.hosts):
            nodes[i]["topics"] = ([0] if a.aggregates else []) + (
                list(range(1, ns + 1)) if i in fast or a.hybrid else [home[i]] if a.one_subnet
                else sorted(r2.sample(range(1, ns + 1), a.slow_joins)))
            if i in home:
                nodes[i]["home"] = home[i]
        if a.aggregates:
            for s_, msgs in enumerate(full):
                for t in range(1, ns + 1):
                    for g in r2.sample(fast_l, a.aggregates):
                        msgs.append([g, a.agg_at_ms, 0, a.agg_bytes, a.agg_deadline_ms, 0])
    def kv(x):
        d = {}
        for item in filter(None, x.split(",")):
            k, v = item.split("=")
            d[k] = v == "true" if v in ("true", "false") else (float(v) if "." in v else int(v))
        return d
    for i in range(a.hosts):
        g = kv(a.gs_fast if i in fast else a.gs_slow)
        if g:
            nodes[i]["gs"] = g
    if a.dial_policy == "slow-to-fast":
        for i in slow:
            k = min(a.dial_slow or a.gossip_dial, len(fast_l))
            if a.dial_local:
                near = [j for j in fast_l if regions[j] == regions[i]]
                pick = r2.sample(near, min(k, len(near)))
                pick += r2.sample([j for j in fast_l if j not in pick], k - len(pick))
            else:
                pick = r2.sample(fast_l, k)
            nodes[i]["dial"] = sorted(pick)
        for i in fast_l:
            nodes[i]["dial"] = sorted(r2.sample([j for j in fast_l if j != i], min(a.gossip_dial, len(fast_l) - 1)))
    elif a.dial_slow:
        for i in slow:
            nodes[i]["dial"] = sorted(r2.sample([j for j in range(a.hosts) if j != i], a.dial_slow))
    if a.dial_fast:
        for i in slow:
            base = nodes[i].get("dial") or r2.sample([j for j in range(a.hosts) if j != i], a.gossip_dial)
            nodes[i]["dial"] = sorted(base + r2.sample([j for j in fast_l if j not in base], a.dial_fast))
    if a.dial_home:
        by_home = defaultdict(list)
        for i, t in home.items():
            by_home[t].append(i)
        for i, t in home.items():
            base = nodes[i].get("dial") or r2.sample([j for j in range(a.hosts) if j != i], a.gossip_dial)
            mates = [j for j in by_home[t] if j != i and j not in base]
            nodes[i]["dial"] = sorted(base + r2.sample(mates, min(a.dial_home, len(mates))))
    extra = {}
    if a.no_pq:
        full = [[] for _ in full]
    if perturb.active(a):
        extra = perturb.apply(a, a.seed, nodes, hosts, fast, vcount, full, out,
                              lambda i: nodes[i].get("topics") or [0])
        a.gml_text, node_id = perturb.gml(a, gml_regions())
        if node_id:
            for i in range(a.hosts):
                hosts[f"n{i:04d}"]["network_node_id"] = node_id(nodes[i]["city"], nodes[i].pop("_acc"))
        if a.no_pq:
            sched = [[] for _ in sched]
    first_slot = a.warmup
    run = dict(mode="flood", seed=a.seed, nodes=nodes, topics=1, subnets=1, votes_per_topic=1, profile="flood",
               vote_bytes=0, proof_bytes=0, first_slot_s=first_slot, slot_s=12.0, slots=a.slots,
               vote_offset_s=offset_s, vote_jitter_s=a.publish_window, agg_deadline_s=offset_s + 4.0, prove_ms=0,
               proofs="pull", decoys=[], gossip_dial=a.gossip_dial, cold_connect=False, batch_votes=False,
               announce_wait_ms=0, sched=full, msg_bytes=a.msg_bytes, n_topics=ns + 1 if ns > 1 else 1, gs=kv(a.gs),
               lever=" ".join(sys.argv[1:]), bin_s=a.bin, drain_s=a.drain,
               links=a.links, fast_share=a.fast_share, msgs=a.msgs, publish_window=a.publish_window,
               validators_csv=os.path.basename(a.validators_csv or ""), fast_above=a.fast_above,
               links_novalidator=a.links_novalidator, peer_target=a.peer_target,
               peer_max=a.peer_max or (a.peer_target and round(a.peer_target * 1.2)),
               subnet_min_peers=a.subnet_min_peers, **extra)
    with open(f"{out}/run.json", "w") as f:
        json.dump(run, f)
    stop = int(first_slot + 12 * a.slots + a.drain + 2)
    write_yaml(out, hosts, stop, a)
    pubs = [sum(1 for m in full[0] if m[0] == i) for i in range(a.hosts)]
    print(f"slot 0: {len(full[0])} messages, {sum(m[3] for m in full[0]):,} B")
    print(f"{out}: {a.hosts} hosts, flood {a.msgs} x {a.msg_bytes} B per slot, {a.slots} slots, "
          f"links {a.links} (no validators: {a.links_novalidator or a.links}) + {n_fast} at 1 Gbit "
          f"(above {a.fast_above} validators + {a.fast_share:.0%} of the rest), dial {a.gossip_dial}, stop={stop}s; "
          f"{sum(vcount):,} validators on {sum(1 for v in vcount if v)} hosts; slot 0: {sum(1 for x in pubs if x)} publishers, "
          f"max {max(pubs)} msgs, fast hosts publish {sum(pubs[i] for i in fast)}")


def write_yaml(out, hosts, stop, a):
    # Hand-written YAML keeps this script dependency-free.
    y = [
        "general:",
        f"  stop_time: {stop}s",
        f"  seed: {a.seed}",
        f"  parallelism: {a.parallelism}",
        "  model_unblocked_syscall_latency: true",
        "network:",
        "  graph:",
        "    type: gml",
        "    inline: |",
    ] + ["      " + l for l in getattr(a, "gml_text", gml_regions()).splitlines()] + [
        "experimental:",
        "  use_memory_manager: false",
    ] + (["  use_cpu_pinning: false"] if a.no_cpu_pinning else []) + ([
        "  socket_send_autotune: false",
        f"  socket_send_buffer: {a.fixed_send_buffer}",
    ] if a.fixed_send_buffer else []) + [
        "hosts:",
    ]
    for name, h in hosts.items():
        p = h["processes"][0]
        y += [
            f"  {name}:",
            f"    network_node_id: {h['network_node_id']}",
            f"    ip_addr: {h['ip_addr']}",
            f"    bandwidth_down: \"{h['bandwidth_down']}\"",
            f"    bandwidth_up: \"{h['bandwidth_up']}\"",
            "    processes:",
            f"    - path: {p['path']}",
            f"      args: {p['args']}",
            f"      start_time: {p['start_time']}",
            "      expected_final_state: {exited: 0}",
        ]
        if h.get("pcap"):
            y += ["    host_options:", "      pcap_enabled: true", "      pcap_capture_size: 64"]
    with open(f"{out}/shadow.yaml", "w") as f:
        f.write("\n".join(y) + "\n")


if __name__ == "__main__":
    main()
