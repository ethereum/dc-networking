#!/usr/bin/env python3
"""Back-of-envelope load model: WB-PQ direct delivery vs. gossipsub for PQ votes.

Every number printed comes from PARAMS / SIGS / SCENARIOS below, so the tables
in DESIGN.md can be regenerated after changing an assumption:

    python3 model/load_model.py > results/model.md
"""

from math import ceil, log

KiB = 1024
MiB = 1024 * KiB
# Bytes a gossip subnet member receives per vote byte it needs, measured in Shadow
# (results/sim.md): 6.7 for one 312-member subnet on links that keep up (symmetric
# 50 Mbit/s). EIP-7870 attester uplinks (25 Mbit/s) cannot carry that: rust-libp2p
# drops queued forwards and the measured value falls to 5.9 (one subnet) and 4.2
# (two), with late and missing votes.
KAPPA_GOSSIP = 6.7

PARAMS = dict(
    P=10_000,               # beacon nodes (dc-networking requirements.md: ~1e4)
    K=16,                   # recipients per vote (Wonderboom: 16 representatives)
    S=16,                   # target subscribers (leaf aggregators) per topic, >= K
    fanout=8,               # tree fanout above the leaves (proposer folds <= 8, EIP-8292)
    S2=16,                  # internal aggregators per internal tree node
    pulls_per_child=2,      # Wonderboom: largest + one random aggregate per child
    vote_overhead=168,      # AttestationData 128 B + validator index 8 B + framing 32 B
    proof=220 * KiB,        # leanVM single-message aggregate of ~400 sigs (EIP-8292: 206-227 KiB)
    final_proof=256 * KiB,  # block-level proof (EIP-8292 propagation target)
    prove_sps_8c=270.0,     # leanVM sigs/s on 8 cores (EIP-8292: 1000 sigs in 3.7 s)
    prove_sps_fast=1200.0,  # leanVM sigs/s on a fast box (leanVM README: 1.2K/s)
    prove_budget_s=6.0,     # seconds per slot an aggregator may spend proving
    merge_s=0.30,           # leanVM 2-to-1 recursion (leanVM README)
    send_window_s=1.0,      # a voter's K copies leave within 1 s
    collect_window_s=4.0,   # votes reach a leaf aggregator within 4 s
    proof_window_s=2.0,     # proofs reach the next level within 2 s
    # gossipsub baseline
    gossip_subnets=64,      # today's ATTESTATION_SUBNET_COUNT
    subnets_per_node=2,
    kappa=KAPPA_GOSSIP,     # bytes received per payload byte by a subnet member (see KAPPA_GOSSIP)
    kappa_direct=1.02,      # same for a direct recipient (libp2p framing); measured in Shadow
    attester_up_mbps=25,    # EIP-7870 attester uplink (50/25 Mbit/s); 15 at its "minimum tested" point
    aggs_per_committee=16,  # today's TARGET_AGGREGATORS_PER_COMMITTEE
)

SIGS = {
    "leanSig (3.03 KiB)": 3104,      # eprint 2025/1332, standard instance
    "leanVM XMSS (1.17 KiB)": 1198,  # EIP-8292
}
BLS_VOTE = 96 + 168

SCENARIOS = {
    "800k validators, 32-slot round (today's cadence)": dict(V=800_000, slots=32, topics=64),
    "800k validators, 8-slot round (DC target)": dict(V=800_000, slots=8, topics=256),
}


def mbps(nbytes, seconds):
    return nbytes * 8 / seconds / 1e6


def b(n):
    if n >= 10 * 1024 * MiB:
        return f"{n / (1024 * MiB):,.0f} GiB"
    if n >= MiB:
        return f"{n / MiB:,.1f} MiB"
    if n >= KiB:
        return f"{n / KiB:,.0f} KiB"
    return f"{n:,.0f} B"


def model(V, slots, topics, sig, p=PARAMS):
    vote = sig + p["vote_overhead"]
    vps = V / slots
    vpt = vps / topics
    K, S, F = p["K"], p["S"], p["fanout"]
    depth = ceil(log(topics, F) - 1e-9)  # internal levels incl. the proposer's fold
    r = {}
    r["votes per slot / per topic"] = f"{vps:,.0f} / {vpt:,.0f}"
    r["vote size on the wire"] = b(vote)
    r["tree: topics → … → 1, hops vote→block"] = (
        " → ".join(str(ceil(topics / F ** i)) for i in range(depth + 1)) + f", {depth + 1} hops")

    # per role, WB-PQ direct
    r["**direct** · solo voter: upload per vote (K copies)"] = (
        f"{b(K * vote)} ({mbps(K * vote, p['send_window_s']):.2f} Mbit/s)")
    n = 1000
    up = n / slots * K * vote
    r["**direct** · 1,000-validator node: upload per slot"] = f"{b(up)} ({mbps(up, 2 * p['send_window_s']):.1f} Mbit/s)"
    leaf_in = vpt * K / S * vote * p["kappa_direct"]
    r["**direct** · leaf aggregator: download per topic·slot"] = (
        f"{b(leaf_in)} ({mbps(leaf_in, p['collect_window_s']):.1f} Mbit/s)")
    r["**direct** · leaf aggregator: prove one topic (8 cores / fast)"] = (
        f"{vpt / p['prove_sps_8c']:.1f} s / {vpt / p['prove_sps_fast']:.2f} s")
    r["**direct** · leaf aggregator: proof upload per slot"] = b(p["S2"] * p["pulls_per_child"] / S * p["proof"])
    node_in = F * p["pulls_per_child"] * p["proof"]
    r["**direct** · internal aggregator / proposer: download per slot"] = (
        f"{b(node_in)} ({mbps(node_in, p['proof_window_s']):.0f} Mbit/s)")
    r["**direct** · internal aggregator: fold 8 → 1"] = (
        f"{(F - 1) * p['merge_s']:.1f} s serial, {3 * p['merge_s']:.1f} s as a 3-level tree")
    sup = vps * vote
    r["**direct** · super-aggregator (all topics): download per slot"] = (
        f"{b(sup)} ({mbps(sup, p['collect_window_s']):.0f} Mbit/s)")
    r["**direct** · every node: final proof (gossip)"] = b(p["final_proof"] * p["kappa"])
    work = vps * S
    r["**direct** · leaf-proving machines needed (8 cores / fast)"] = (
        f"{work / (p['prove_sps_8c'] * p['prove_budget_s']):,.0f} / "
        f"{work / (p['prove_sps_fast'] * p['prove_budget_s']):,.0f}")
    r["**direct** · network vote bytes per slot"] = b(vps * K * vote * p["kappa_direct"])

    # gossipsub baseline: same PQ votes, today's subnet pipeline
    G = p["gossip_subnets"]
    subs = p["P"] * p["subnets_per_node"] / G
    net = vps * subs * vote * p["kappa"]
    home = p["subnets_per_node"] * vps / G * vote * p["kappa"]
    r["**gossip** · subscribers per subnet"] = f"{subs:,.0f}"
    r["**gossip** · node in 2 subnets: down ≈ up per slot"] = (
        f"{b(home)} ({mbps(home, p['collect_window_s']):.1f} Mbit/s)")
    r["**gossip** · …that upload on an EIP-7870 attester link (25 Mbit/s)"] = (
        f"{home * 8 / (p['attester_up_mbps'] * 1e6):.1f} s per slot")
    agg16 = G * p["aggs_per_committee"] * p["proof"] * p["kappa"]
    agg1 = G * p["proof"] * p["kappa"]
    r["**gossip** · every node: aggregate topic, 16 per committee"] = (
        f"{b(agg16)} ({mbps(agg16, p['proof_window_s']):,.0f} Mbit/s)")
    r["**gossip** · every node: aggregate topic, 1 per committee"] = (
        f"{b(agg1)} ({mbps(agg1, p['proof_window_s']):,.0f} Mbit/s)")
    r["**gossip** · network vote bytes per slot"] = b(net)
    r["network vote bytes, gossip ÷ direct"] = f"{net / (vps * K * vote * p['kappa_direct']):.0f}×"
    r["(BLS votes + gossip, same cadence) node in 2 subnets per slot"] = (
        f"{b(p['subnets_per_node'] * vps / G * BLS_VOTE * p['kappa'])}")
    return r


def gasper(p=PARAMS):
    """Gasper timing (12 s slots, 4 s per phase): every vote straight to R aggregators,
    then aggregates pushed to the next proposer. Line-rate bounds; Shadow numbers in
    results/gasper.md."""
    V, R, window = 1_048_576, 128, 4.0
    vps = V // 32
    links = {"EIP-7870 minimum (15 Mbit/s up)": 15e6, "EIP-7870 attester (25 up / 50 down)": 25e6,
             "EIP-7870 local builder (50 up / 100 down)": 50e6, "1 Gbit/s": 1e9}
    print(f"\n### Gasper: {vps:,} votes per slot, each to all {R} aggregators within {window:.0f} s\n")
    print("| quantity | " + " | ".join(SIGS) + " |")
    print("|---|" + "---|" * len(SIGS) + "")
    rows = {}
    for name, sig in SIGS.items():
        vote = sig + p["vote_overhead"]
        rows.setdefault("aggregator download per slot", []).append(
            f"{b(vps * vote)} ({mbps(vps * vote, window):.0f} Mbit/s over {window:.0f} s)")
        rows.setdefault("voter upload per vote (R copies)", []).append(b(R * vote))
        for ln, up in links.items():
            n = up * window / 8 / (R * vote)
            rows.setdefault(f"max votes per slot a node can send in {window:.0f} s: {ln}", []).append(
                f"{n:,.0f} (≈ {n * 32:,.0f} validators)")
    for k, v in rows.items():
        print(f"| {k} | " + " | ".join(v) + " |")
    print(f"\n### Gasper: aggregates of {b(p['proof'])} the next proposer can receive in {window:.0f} s (line rate)\n")
    print("| proposer downlink | pushed directly (proposer or decoy set) | flooded to every node (κ = kappa) |")
    print("|---|---|---|")
    for ln, down in {"EIP-7870 attester (50 Mbit/s)": 50e6, "EIP-7870 local builder (100 Mbit/s)": 100e6,
                     "1 Gbit/s": 1e9}.items():
        n = down * window / 8 / p["proof"]
        print(f"| {ln} | {n:,.0f} | {n / p['kappa']:,.0f} |")


def main():
    gasper()
    for name, sc in SCENARIOS.items():
        print(f"\n### {name}\n")
        cols = list(SIGS)
        res = {s: model(sc["V"], sc["slots"], sc["topics"], SIGS[s]) for s in cols}
        print("| quantity | " + " | ".join(cols) + " |")
        print("|---|" + "---|" * len(cols))
        for key in res[cols[0]]:
            print(f"| {key} | " + " | ".join(res[s][key] for s in cols) + " |")

    print("\n### Censorship: chance that all K recipients of a vote are adversarial\n")
    print("| K | adversarial share of subscribers | P(vote censored) | censored votes per 800k |")
    print("|---|---|---|---|")
    for K in (4, 8, 16):
        for f in (0.10, 1 / 3):
            print(f"| {K} | {f:.0%} | {f ** K:.1e} | {f ** K * 800_000:.3g} |")

    print("\n### Parameters\n")
    for k, v in PARAMS.items():
        print(f"- `{k}` = {v}")


if __name__ == "__main__":
    main()
