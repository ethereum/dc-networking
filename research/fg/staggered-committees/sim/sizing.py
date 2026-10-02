#!/usr/bin/env python3
"""Lane B (network) tables for staggered FG committees.

Run from the staggered-committees folder:   python3 sim/sizing.py
Python 3 standard library only. There is no randomness: every table is a closed
form or a deterministic timeline evaluation. Every number quoted in
analysis/network.md is printed here; section numbers (S1..S9) match the note.

Notation (design/requirements.md:25-29): V = validators (signers), P = peers.
C = units ("cohorts") per round. A "unit" is the Q17 4 s vote + 4 s aggregation
window (research/fg/pipelined-units/README.md:23-24).
"""
from math import ceil, exp, floor

# ----------------------------------------------------------------- constants
# file:line refs are to the vault; "mk" = Mikhail's DC beacon-chain draft
# (/tmp/claude-501/ff0f782b-stagger/mk-dc-beacon-chain.md).
SLOT_MS = 12_000                  # consensus-specs configs/mainnet.yaml:68
ATT_DUE_GLOAS_MS = 3_000          # gloas/validator.md:41 (2500 bps of 12 s)
ATT_DUE_PRE_GLOAS_MS = 4_000      # configs/mainnet.yaml:79 (3333 bps)
AGG_DUE_GLOAS_MS = 6_000          # gloas/validator.md:42 (5000 bps)
SLOTS_PER_EPOCH = 32              # phase0 preset
SUBNETS = 64                      # ATTESTATION_SUBNET_COUNT, phase0/p2p-interface.md:235
SUBNETS_PER_NODE = 2              # phase0/p2p-interface.md:234
AGGS_PER_COMMITTEE = 16           # TARGET_AGGREGATORS_PER_COMMITTEE, phase0/validator.md:105
MAX_COMMITTEES_PER_SLOT = 64      # phase0/beacon-chain.md:235
TARGET_COMMITTEE_SIZE = 128       # phase0/beacon-chain.md:236
D, D_LAZY = 8, 6                  # phase0/p2p-interface.md:439,442
MCACHE_GOSSIP = 3                 # phase0/p2p-interface.md:448
GOSSIP_FACTOR = 0.25              # go-libp2p-pubsub gossipsub.go:54 (Prysm keeps default, pubsub.go:212-222)
IDONTWANT_THRESHOLD = 1024        # go-libp2p-pubsub gossipsub.go:75
MSG_ID = 20                       # altair/p2p-interface.md:159-166
MK_COMMITTEES_PER_ROUND = 2048    # mk:282
MAX_VALIDATORS_PER_AGGREGATE = 2**17  # mk:283
MAX_ATTESTATIONS = 8              # MAX_ATTESTATIONS_ELECTRA, electra/beacon-chain.md:184; reused mk:1164
EXIT_CHURN_ETH = 256              # MAX_PER_EPOCH_ACTIVATION_EXIT_CHURN_LIMIT, configs/mainnet.yaml:129
MAX_SEED_LOOKAHEAD = 4            # phase0/beacon-chain.md:266
ROUNDS_PER_DAY_8 = 86_400 * 1000 // (8 * SLOT_MS)   # 900

# SSZ sizes (bytes). Progressive types serialize like their classic forms:
# EIP-7495:64 (ProgressiveContainer), EIP-7916:106-108 (ProgressiveBitlist/List).
ATT_DATA2 = 8 + (8 + 32) + (8 + 32)          # AttestationData2, mk:311-318 -> 88
ATT_DATA_P0 = 8 + 8 + 32 + 40 + 40           # phase0/beacon-chain.md:404-410 -> 128
SINGLE_ELECTRA = 8 + 8 + ATT_DATA_P0 + 96    # electra/beacon-chain.md:309-313 -> 240
SINGLE_DC = 8 + 8 + ATT_DATA2 + 96           # same envelope, AttestationData2 -> 200
SINGLE_SSZ_MD = 248                          # research/ssz.md:144 (Simplex baseline)
WRAPPER = 208                                # SignedAggregateAndProof, research/ssz.md:206
MK_COMMITTEE_BITS = MK_COMMITTEES_PER_ROUND // 8   # Bitvector[2048], mk:245-251 -> 256
ELECTRA_COMMITTEE_BITS = MAX_COMMITTEES_PER_SLOT // 8  # Bitvector[64] -> 8


def bitlist(nbits):
    """SSZ Bitlist length incl. the delimiter bit."""
    return ceil((nbits + 1) / 8)


def dc_attestation(nbits, committee_bits=MK_COMMITTEE_BITS):
    """mk:363-375: offset(aggregation_bits) + signature + committee_bits + data + bits."""
    return 4 + 96 + committee_bits + ATT_DATA2 + bitlist(nbits)


def electra_attestation(nbits):
    """electra/beacon-chain.md:353-360."""
    return 4 + ATT_DATA_P0 + 96 + ELECTRA_COMMITTEE_BITS + bitlist(nbits)


def hr(title):
    print("\n" + "=" * 100 + "\n" + title + "\n" + "=" * 100)


def fmt_bytes(b):
    if b >= 1e6:
        return f"{b / 1e6:.2f} MB"
    if b >= 1e3:
        return f"{b / 1e3:.1f} kB"
    return f"{b:.0f} B"


# ======================================================== S1: switch lag L
# Timeline model. A unit = (start, sign time, landing). Blocks are proposed at
# slot starts and include every aggregate whose landing <= proposal time
# (pipelined-units/README.md:57,64). Voters see a block delta_b after its
# proposal. Under Mikhail's STF a new height exists only once a block that
# carries the quorum is processed (mk:947-989), and the new target root is that
# very block (mk:950-954), so a voter can name the new height only after it has
# seen the including block ("on-chain switch"). L = number of units strictly
# between the quorum-completing unit k and the first unit whose voters sign
# after seeing the new height.

def grid(name):
    """Return (slot_ms, round_ms, [(start, sign_offset, landing_offset), ...], delta_b_ms)."""
    if name == "Q17 C=23":       # README:57-62
        return SLOT_MS, 96_000, [(4000 * i, 0, 8000) for i in range(23)], ATT_DUE_GLOAS_MS
    if name == "Q17 C=22 (grid +4 s)":  # README:146 variant
        return SLOT_MS, 96_000, [(4000 * (i + 1), 0, 8000) for i in range(22)], ATT_DUE_GLOAS_MS
    if name == "Q17 C=11 (4-slot)":
        return SLOT_MS, 48_000, [(4000 * i, 0, 8000) for i in range(11)], ATT_DUE_GLOAS_MS
    if name == "C=8 today-shaped":  # vote on block (<= due), aggregate at 50 %, land by next slot
        return SLOT_MS, 96_000, [(SLOT_MS * i, None, SLOT_MS) for i in range(8)], ATT_DUE_GLOAS_MS
    if name == "C=8 explainer Opt.5":  # vote slot i +4 s, aggregate slot i+1 +8 s, include slot i+2
        return SLOT_MS, 96_000, [(SLOT_MS * i, 4000, 2 * SLOT_MS) for i in range(8)], ATT_DUE_GLOAS_MS
    if name == "10 s slots C=15 (+0/+5 s)":  # quick slots, msg 1623; 2 units/slot, last dropped
        return 10_000, 80_000, [(5000 * i, 0, 8000) for i in range(15)], 2_500
    raise KeyError(name)


def timeline(name, rounds=4):
    slot_ms, round_ms, units, delta_b = grid(name)
    out = []
    for r in range(rounds):
        for i, (s, sign_off, land_off) in enumerate(units):
            start = r * round_ms + s
            out.append(dict(r=r, i=i, start=start, sign_off=sign_off, land=start + land_off))
    return slot_ms, delta_b, out


def sign_time(u, slot_ms, delta_b, policy):
    if u["sign_off"] is None:          # today-shaped: sign when the slot's block is seen
        return u["start"] + delta_b
    if policy == "wait" and u["start"] % slot_ms == 0:
        # +0 units wait for the slot's block, but no later than their 4 s vote phase
        return u["start"] + min(delta_b, 4000)
    return u["start"] + u["sign_off"]


def lag(name, k_round=1, policy="P1", switch="onchain", missed=0, delta_b=None):
    slot_ms, db, tl = timeline(name)
    round_ms = grid(name)[1]
    if delta_b is not None:
        db = delta_b
    res = []
    for k, u in enumerate(tl):
        if u["r"] != k_round:
            continue
        if switch == "onchain":
            t_block = ceil(u["land"] / slot_ms) * slot_ms + missed * slot_ms
            t_vis = t_block + db
        else:                           # off-chain: switch on aggregate landing
            t_block = None
            t_vis = u["land"]
        j = next(j for j in range(k + 1, len(tl)) if sign_time(tl[j], slot_ms, db, policy) >= t_vis)
        res.append(dict(i=u["i"], start=u["start"] - k_round * round_ms,
                        off=u["start"] % slot_ms, land=u["land"] - k_round * round_ms,
                        t_block=t_block, L=j - k - 1))
    return res


def s1():
    hr("S1  Switch lag L (units strictly between the quorum-completing unit and the first fresh unit)")
    print("Model: on-chain switch (mk:947-989), block seen delta_b after proposal "
          "(3 s = Gloas attestation due, gloas/validator.md:41; 2.5 s for 10 s slots).")
    print("P1 = every voter signs at its unit start (README:32); wait = +0 units sign when the slot's"
          " block is seen; offchain = voters switch when the quorum aggregates land.\n")
    for name in ["Q17 C=23", "Q17 C=22 (grid +4 s)", "Q17 C=11 (4-slot)", "10 s slots C=15 (+0/+5 s)"]:
        p1 = lag(name)
        wt = lag(name, policy="wait")
        oc = lag(name, switch="offchain")
        ms = lag(name, missed=1)
        late = lag(name, delta_b=5000)
        print(f"--- {name}")
        print("unit | start s | offset s | lands s | L P1 | L wait | L offchain | L P1+missed block | L P1, block seen at +5 s")
        for a, b, c, d, e in zip(p1, wt, oc, ms, late):
            print(f"{a['i']:4d} | {a['start']/1000:7.0f} | {a['off']/1000:8.0f} | {a['land']/1000:7.0f} |"
                  f" {a['L']:4d} | {b['L']:6d} | {c['L']:10d} | {d['L']:17d} | {e['L']:6d}")
        n = len(p1)
        print(f"mean over the round: P1 {sum(x['L'] for x in p1)/n:.2f}, wait {sum(x['L'] for x in wt)/n:.2f}, "
              f"offchain {sum(x['L'] for x in oc)/n:.2f}, P1+missed {sum(x['L'] for x in ms)/n:.2f}, "
              f"P1 block at +5 s {sum(x['L'] for x in late)/n:.2f}")
        # interior units: far enough from the round end that no variant crosses the boundary gap
        by_off = {}
        for a, b, c, d, e in zip(p1, wt, oc, ms, late):
            if a["i"] <= n - 7:
                by_off.setdefault(a["off"] // 1000, set()).add((a["L"], b["L"], c["L"], d["L"], e["L"]))
        print("interior units (i <= C-7) by offset -> (P1, wait, offchain, P1+missed, block at +5 s):",
              {k: sorted(v) for k, v in sorted(by_off.items())})
        print("stale window in wall-clock (P1, interior): "
              + ", ".join(f"+{k} s: {sorted(v)[0][0] * (grid(name)[2][1][0] - grid(name)[2][0][0]) / 1000:.0f} s"
                          for k, v in sorted(by_off.items())))
        print(f"round-mean L/C (P1): {sum(x['L'] for x in p1) / n / n * 100:.1f} % of the round's units")
        print()
    for name in ["C=8 today-shaped", "C=8 explainer Opt.5"]:
        p1 = lag(name)
        ms = lag(name, missed=1)
        print(f"--- {name}: L = {sorted(set(x['L'] for x in p1))}, with next block missed: "
              f"{sorted(set(x['L'] for x in ms))}; L/C = {100 * p1[0]['L'] / 8:.1f} % of the round's units")
    print("\nTail weight (cited, not modelled): 95.85 % of mainnet attestations are included in the next "
          f"slot, ~1.2 % in the one after (ethresearch 20020:95-96) -> {100 - 95.85:.2f} % miss the next slot.")
    print(f"MAXIMUM_GOSSIP_CLOCK_DISPARITY = 500 ms = {100 * 500 / 4000:.1f} % of a 4 s unit window; "
          f"seen_ttl = SLOT_DURATION_MS * SLOTS_PER_EPOCH * 2 // 1000 = {SLOT_MS * SLOTS_PER_EPOCH * 2 // 1000} s "
          "(phase0/p2p-interface.md:449-450)")

    print("\nS1b  Late window W: which block can include the late (catch-all) aggregate, Q17 12 s grid")
    print("late aggregators publish at cut + W and need 4 s to land (same propagation budget as on-time)")
    print("offset | on-time lands (s into slot) -> block | W=4 s: late lands -> block | W=8 s: late lands -> block")
    def blk(t):
        return ceil(t / 12) * 12        # first block (slot start, seconds) at or after t

    for off in (0, 4, 8):
        start = off
        on_land = start + 8
        cells = [f"{on_land} -> {blk(on_land)}"]
        for W in (4, 8):
            late_land = start + 4 + W + 4
            same = "same block" if blk(late_land) == blk(on_land) else f"+{(blk(late_land) - blk(on_land)) // 12} block"
            cells.append(f"{late_land} -> {blk(late_land)} ({same})")
        print(f"+{off} s | " + " | ".join(cells))


# ======================================================== S2: sizing
VS = [120_000, 500_000, 1_000_000]
CS = [8, 11, 22, 23]


def slots_per_round(C):
    return 4 if C == 11 else 8


def today(V):
    cps = max(1, min(MAX_COMMITTEES_PER_SLOT, V // SLOTS_PER_EPOCH // TARGET_COMMITTEE_SIZE))
    per_slot = V / SLOTS_PER_EPOCH
    c = per_slot / cps
    aggs = cps * AGGS_PER_COMMITTEE
    agg_b = WRAPPER + electra_attestation(round(c))
    return dict(cps=cps, per_slot=per_slot, c=c, aggs=aggs, agg_b=agg_b,
                vote_b=per_slot * SINGLE_ELECTRA, aggs_b=aggs * agg_b,
                per_subnet_b=c * SINGLE_ELECTRA)


def committees_per_unit(V, C, rule):
    if rule == "A64":
        return 64.0
    if rule == "Afloor":
        return float(max(1, min(SUBNETS, V // C // TARGET_COMMITTEE_SIZE)))
    if rule == "MK":
        return MK_COMMITTEES_PER_ROUND / C
    raise KeyError(rule)


def ihave_per_msg(topic_peers):
    """Bytes of IHAVE ids one node emits per message: mcache_gossip heartbeats x
    max(D_lazy, floor(0.25 x eligible non-mesh peers)), capped by availability
    (go-libp2p-pubsub gossipsub.go:1853-1864)."""
    nonmesh = max(0, topic_peers - D)
    target = min(max(D_LAZY, floor(GOSSIP_FACTOR * nonmesh)), nonmesh)
    return MCACHE_GOSSIP * target * MSG_ID


def s2():
    hr("S2  Sizing per unit and per slot (worst case: every aggregator publishes, msg 1425)")
    print(f"SSZ: SingleAttestation (Electra) {SINGLE_ELECTRA} B; DC single vote with AttestationData2 "
          f"{SINGLE_DC} B; ssz.md baseline {SINGLE_SSZ_MD} B; aggregate wrapper {WRAPPER} B;")
    print(f"DC Attestation fixed part {dc_attestation(0) - bitlist(0)} B with mk CommitteeBits[2048] "
          f"({MK_COMMITTEE_BITS} B) vs {dc_attestation(0, ELECTRA_COMMITTEE_BITS) - bitlist(0)} B with "
          f"Bitvector[64]; Electra Attestation fixed {electra_attestation(0) - bitlist(0)} B.\n")

    print("S2a  today's per-slot load (phase0 get_committee_count_per_slot; Electra sizes)")
    print("V | attesters/slot | committees/slot | committee size | aggregates/slot | vote bytes/slot | "
          "per-subnet bytes/slot | aggregate bytes/slot")
    for V in VS:
        t = today(V)
        print(f"{V:>9,} | {t['per_slot']:>9,.0f} | {t['cps']:>3d} | {t['c']:>6.1f} | {t['aggs']:>5d} | "
              f"{fmt_bytes(t['vote_b'])} | {fmt_bytes(t['per_subnet_b'])} | {fmt_bytes(t['aggs_b'])}")

    print("\nS2b  per unit, committee rule A64 (64 committees per unit = one per subnet)")
    print("V | C | slots/round | units/slot | voters/unit | x today's slot | committee size | "
          "aggregates/unit | agg size | votes/unit (all subnets) | votes/unit/subnet | aggregates/unit | "
          "votes/slot | aggregates/slot")
    for V in VS:
        for C in CS:
            spr = slots_per_round(C)
            ups = C / spr
            vu = V / C
            k = committees_per_unit(V, C, "A64")
            c = vu / k
            aggs = k * AGGS_PER_COMMITTEE
            agg_b = WRAPPER + dc_attestation(round(c))
            print(f"{V:>9,} | {C:2d} | {spr} | {ups:.3f} | {vu:>9,.0f} | {32 / C:.2f} | {c:7.1f} | "
                  f"{aggs:5.0f} | {agg_b} B | {fmt_bytes(vu * SINGLE_DC)} | {fmt_bytes(c * SINGLE_DC)} | "
                  f"{fmt_bytes(aggs * agg_b)} | {fmt_bytes(vu * SINGLE_DC * ups)} | "
                  f"{fmt_bytes(aggs * agg_b * ups)}")
    for V in VS:
        t = today(V)
        c = V / 23 / 64
        per_slot = 64 * AGGS_PER_COMMITTEE * (WRAPPER + dc_attestation(round(c))) * 23 / 8
        print(f"aggregate bytes per slot, V={V:,}: C=23 {fmt_bytes(per_slot)} vs today {fmt_bytes(t['aggs_b'])} "
              f"-> {per_slot / t['aggs_b']:.1f}x")

    print("\nS2c  committee-count rules compared (committees per unit / committee size / aggregates per unit"
          " / aggregates per round / is_aggregator modulo)")
    print("V | C | A64 | Afloor (min size 128) | MK 2048/C")
    for V in VS:
        for C in CS:
            cells = []
            for rule in ["A64", "Afloor", "MK"]:
                k = committees_per_unit(V, C, rule)
                c = V / C / k
                cells.append(f"{k:6.1f} / {c:7.1f} / {k * AGGS_PER_COMMITTEE:6.0f} / "
                             f"{k * AGGS_PER_COMMITTEE * C:7.0f} / mod {max(1, int(c) // AGGS_PER_COMMITTEE)}")
            print(f"{V:>9,} | {C:2d} | " + " | ".join(cells))
    print("2048/C is non-integer for C in {11, 22, 23}: "
          + ", ".join(f"C={C}: {2048 / C:.2f}" for C in [11, 22, 23, 24]))
    for C in (11, 22, 23):
        lo = MK_COMMITTEES_PER_ROUND // C
        n_hi = MK_COMMITTEES_PER_ROUND - lo * C
        base, extra = divmod(lo, SUBNETS)
        print(f"  keeping 2048 at C={C}: {n_hi} unit(s) with {lo + 1} committees, {C - n_hi} with {lo}; "
              f"{lo} committees over 64 subnets -> {extra} subnets carry {base + 1}, {SUBNETS - extra} carry "
              f"{base} ({base + 1}:{base} per-subnet load inside a unit)")
    print("  rule Afloor reaches 64 committees/unit once V >= C x 64 x 128: "
          + ", ".join(f"C={C}: {C * 64 * TARGET_COMMITTEE_SIZE:,}" for C in (8, 11, 22, 23)))
    print(f"  rule A: COMMITTEES_PER_ROUND = C x 64 -> " + ", ".join(
        f"C={C}: {C * 64} ({C * 64 // 8} B CommitteeBits)" for C in (8, 11, 22, 23, 24)))
    print("  landing-to-proposal margin by unit offset (README:64): +0 -> 8 s, +4 -> 4 s, +8 -> 12 s; "
          f"Gloas today: aggregate due {AGG_DUE_GLOAS_MS / 1000:.0f} s -> {(SLOT_MS - AGG_DUE_GLOAS_MS) / 1000:.0f} s margin "
          "(gloas/validator.md:42)")

    print("\nS2d  per-node received FG bytes per unit, A64 (2 backbone subnets + global aggregate topic)")
    print("kappa = copies received per message; 1 = no duplicates, 7 = D-1 eager-push estimate "
          "(all FG messages are below the 1 KiB IDONTWANT threshold, gossipsub.go:75).")
    print("V | C | unit s | subnet votes k=1 | subnet votes k=7 | aggregates k=1 | aggregates k=7 | "
          "IHAVE aggregates (100 peers) | IHAVE votes (12 topic peers) | total k=7 + IHAVE | Mbit/s | "
          "aggregate share of total")
    ih_agg = ihave_per_msg(100)
    ih_vote = ihave_per_msg(12)
    for V in VS:
        for C in CS:
            vu = V / C
            c = vu / 64
            aggs = 64 * AGGS_PER_COMMITTEE
            agg_b = WRAPPER + dc_attestation(round(c))
            sv = SUBNETS_PER_NODE * c * SINGLE_DC
            ag = aggs * agg_b
            ihA = aggs * ih_agg
            ihV = SUBNETS_PER_NODE * c * ih_vote
            tot = 7 * sv + 7 * ag + ihA + ihV
            unit_s = 12 if C == 8 else 4
            print(f"{V:>9,} | {C:2d} | {unit_s:2d} | {fmt_bytes(sv)} | {fmt_bytes(7 * sv)} | {fmt_bytes(ag)} | "
                  f"{fmt_bytes(7 * ag)} | {fmt_bytes(ihA)} | {fmt_bytes(ihV)} | {fmt_bytes(tot)} | "
                  f"{tot * 8 / 1e6 / unit_s:.1f} | {100 * (7 * ag + ihA) / tot:.0f} %")
    print(f"IHAVE bytes per message per node: global topic, 100 peers -> {ih_agg} B; "
          f"subnet with 12 topic peers -> {ih_vote} B")
    for V in VS:
        t = today(V)
        sv_t = SUBNETS_PER_NODE * t["per_subnet_b"]
        ag_t = t["aggs_b"]
        tot_t = 7 * sv_t + 7 * ag_t + t["aggs"] * ih_agg + SUBNETS_PER_NODE * t["c"] * ih_vote
        print(f"today, V={V:,}, same model: subnet votes k=7 {fmt_bytes(7 * sv_t)}, aggregates k=7 "
              f"{fmt_bytes(7 * ag_t)}, total incl. IHAVE {fmt_bytes(tot_t)} per 12 s slot = "
              f"{tot_t * 8 / 1e6 / 12:.1f} Mbit/s")
    print("all-subnet supernode, V=1M, C=23, votes only: "
          f"{fmt_bytes(1e6 / 23 * SINGLE_DC)} unique per unit, k=7 -> "
          f"{7 * 1e6 / 23 * SINGLE_DC * 8 / 1e6 / 4:.0f} Mbit/s")

    print("\nS2e  global-topic levers at V=1M, C=23 (per-node received per 4 s unit, k=7 + IHAVE 100 peers)")
    print("committees/unit | aggregators/committee | aggregates/unit | committee_bits | agg size | "
          "aggregate-topic bytes/unit | Mbit/s")
    for k in (64, 32, 16):
        for a in (16, 8):
            for cb, label in ((MK_COMMITTEE_BITS, "Bitvector[2048]"), (ELECTRA_COMMITTEE_BITS, "Bitvector[64]")):
                c = 1e6 / 23 / k
                agg_b = WRAPPER + dc_attestation(round(c), cb)
                n = k * a
                b = n * (7 * agg_b + ih_agg)
                print(f"{k:3d} | {a:2d} | {n:5d} | {label} | {agg_b} B | {fmt_bytes(b)} | {b * 8 / 1e6 / 4:.1f}")


# ======================================================== S3: inclusion
def s3():
    hr("S3  On-chain inclusion per round (8-slot rounds), one data value per unit unless stated")
    print("per-unit = one Attestation per unit; per-block = units landing in the same block merged via "
          "round-wide committee_bits; per-round = full aggregation (msg 1494), capped by "
          "MAX_VALIDATORS_PER_AGGREGATE = 131072 (mk:283).")
    print("V | C | per-unit: #att, bytes | per-block: #att, bits/att (<=131072?), bytes | per-round: #att, bytes")
    for V in VS:
        for C in [8, 22, 23]:
            vu = V / C
            per_unit_n = C
            per_unit_b = C * (4 + dc_attestation(round(vu)))
            # units per block: Q17 grid lands 2 in the round's first slot and 3 elsewhere (README:59-62)
            if C == 8:
                upb = [1] * 8
            elif C == 23:
                upb = [2] + [3] * 7
            else:
                upb = [3] * 7 + [1]
            per_block_b = sum(4 + dc_attestation(round(u * vu)) for u in upb)
            max_bits = max(upb) * vu
            per_round_n = ceil(V / MAX_VALIDATORS_PER_AGGREGATE)
            per_round_b = per_round_n * 4 + sum(dc_attestation(round(V / per_round_n)) for _ in range(per_round_n))
            print(f"{V:>9,} | {C:2d} | {per_unit_n:3d}, {fmt_bytes(per_unit_b)} | {len(upb)}, "
                  f"{max_bits:,.0f} ({'ok' if max_bits <= MAX_VALIDATORS_PER_AGGREGATE else 'EXCEEDS'}), "
                  f"{fmt_bytes(per_block_b)} | {per_round_n}, {fmt_bytes(per_round_b)}")
    for V in VS:
        vu = V / 23
        a = 23 * (4 + dc_attestation(round(vu)))
        b = sum(4 + dc_attestation(round(u * vu)) for u in [2] + [3] * 7)
        n = ceil(V / MAX_VALIDATORS_PER_AGGREGATE)
        c = n * 4 + n * dc_attestation(round(V / n))
        print(f"V={V:,}, C=23: largest byte gap between the three options = {fmt_bytes(max(a, b, c) - min(a, b, c))}"
              f" per round (participation bits alone: {fmt_bytes(V / 8)})")
    print(f"\nC=8 per-unit bitfield exceeds 2^17 once V > {8 * MAX_VALIDATORS_PER_AGGREGATE:,}; "
          f"Q17 per-block merge (3 units) exceeds it once V > {MAX_VALIDATORS_PER_AGGREGATE * 23 // 3:,}")
    print("\nS3b  fragmentation: extra on-chain attestations and gossip aggregates per height switch")
    # brief section 4 preliminary rounds/height at L=3 (C=23): 0.826 (fixed) .. 0.857 (+1/round)
    for rph in (0.826, 0.857):
        sw = 1 / rph
        print(f"rounds/height {rph} -> {sw:.2f} switches/round -> +{sw:.2f} on-chain attestations/round "
              f"(+{100 * sw / 23:.1f} % of 23), up to +{sw * 1024:.0f} gossip aggregates/round "
              f"(+{100 * sw / 23:.1f} % of {23 * 1024})")
    print("Minority-data votes lost if aggregators only aggregate their own data (phase0/validator.md:745-747):")
    for mu in (0.02, 0.05, 0.10, 0.25):
        print(f"  minority share {mu:.2f}: P(no aggregator holds the minority data) ~ exp(-16*mu) = "
              f"{exp(-AGGS_PER_COMMITTEE * mu):.2f}")


# ======================================================== S4: bit layouts
def s4():
    hr("S4  Bit-layout cost per round (bits = participation bitfield over the index set)")
    exits_per_epoch = EXIT_CHURN_ETH // 32      # 32-ETH validators; fewer if consolidated
    print(f"exit churn <= {EXIT_CHURN_ETH} ETH/epoch -> <= {exits_per_epoch} exits/epoch at 32 ETH "
          "(electra/beacon-chain.md:621-625, configs/mainnet.yaml:129)")
    pending = exits_per_epoch * (1 + 2 + 1 + MAX_SEED_LOOKAHEAD)   # deposit->eligible->finalized->activation
    print(f"registry entries awaiting activation in steady state <= ~{pending} "
          "(8/epoch x (1 eligibility + 2 finality lag + 1 + MAX_SEED_LOOKAHEAD) epochs)")
    print("V | layout | finality lag (epochs) | bits/round | overhead vs active | bytes/round")
    for V in VS:
        for lag_e, label in [(2, "healthy"), (1575, "1 week non-finality")]:
            extra = exits_per_epoch * lag_e + pending
            print(f"{V:>9,} | MK set (exit_epoch > finalized) | {lag_e} ({label}) | {V + extra:,.0f} | "
                  f"+{100 * extra / V:.3f} % | {fmt_bytes((V + extra) / 8)}")
        print(f"{V:>9,} | active at epoch(target) | - | {V:,.0f} | 0 | {fmt_bytes(V / 8)}")
        for r in (1.25, 1.5, 2.0):
            print(f"{V:>9,} | raw registry index (R = {r} V) | - | {r * V:,.0f} | +{100 * (r - 1):.0f} % | "
                  f"{fmt_bytes(r * V / 8)}")
    print("position-array cache for O(1) membership: 4 B x |index set| = "
          + ", ".join(f"{fmt_bytes(4 * V)} at V={V:,}" for V in VS))


# ======================================================== S5: slashing evidence
def indexed2(k):
    return 4 + ATT_DATA2 + 96 + 8 * k          # mk:323-328


def slashing2(k):
    return 8 + 2 * indexed2(k)                 # mk:334-337, two offsets


def s5():
    hr("S5  AttesterSlashing2 size by the aggregate the slasher holds (k signers per side)")
    print("V | C | single votes (k=1) | gossip aggregate (k=c) | per-unit on-chain (k=V/C) | "
          "per-block merged (k=3V/C) | cap k=131072")
    for V in VS:
        for C in [8, 23]:
            vu = V / C
            c = vu / 64
            kb = min(MAX_VALIDATORS_PER_AGGREGATE, (1 if C == 8 else 3) * vu)
            print(f"{V:>9,} | {C:2d} | {fmt_bytes(slashing2(1))} | {fmt_bytes(slashing2(round(c)))} | "
                  f"{fmt_bytes(slashing2(round(vu)))} | {fmt_bytes(slashing2(round(kb)))} | "
                  f"{fmt_bytes(slashing2(MAX_VALIDATORS_PER_AGGREGATE))}")
    print(f"Electra reference: EIP-7549:64 quotes 488 KB (320 KB snappy) per AttesterSlashing at 1M; "
          f"model: {fmt_bytes(2 * 8 * 1_000_000 / 32)} of indices")
    ref = 488 * 1024
    vu = 1e6 / 23
    print(f"ratio vs 488 KB at V=1M, C=23: per-unit {slashing2(round(vu)) / ref:.2f}x, "
          f"per-block {slashing2(round(min(MAX_VALIDATORS_PER_AGGREGATE, 3 * vu))) / ref:.2f}x, "
          f"cap {slashing2(MAX_VALIDATORS_PER_AGGREGATE) / ref:.2f}x")


# ======================================================== S6: bursts
def s6():
    hr("S6  Worst instantaneous FG single-vote burst an adversary with stake beta can place")
    print("in units of one unit's honest load (V/C); bytes at V=1M with 200 B votes")
    C = 23
    print("beta | no windows (any time in round) | hard start + soft end W=1 unit | W=2 | "
          "open-ended soft end (STF horizon = current or previous round, mk:657-660)")
    for beta in (0.1, 1 / 3):
        cells = []
        for units in (beta * C, beta * 2, beta * 3, beta * 2 * C):
            cells.append(f"{units:.2f} units = {fmt_bytes(units * 1e6 / C * SINGLE_DC)}")
        print(f"{beta:.2f} | " + " | ".join(cells))
    print("(adversarial votes only; the honest unit load of 1.00 unit comes on top)")


# ======================================================== S7: churn
def s7():
    hr("S7  Duty-subnet reassignments per validator per day (8-slot rounds: 900 rounds/day)")
    R = ROUNDS_PER_DAY_8
    print("V | fixed or slow positional rotation (subnet = f(cohort identity)) | era shuffle (daily) | "
          "MK slide-by-1 (contiguous, 2048 committees, subnet = k mod 64) | per-epoch reshuffle | "
          "per-round reshuffle | aggregator duties/validator/day (C=23, A64)")
    for V in VS:
        cmk = V / MK_COMMITTEES_PER_ROUND
        c = V / 23 / 64
        print(f"{V:>9,} | 0 | 1 | {R / cmk:.2f} (every {cmk:.0f} rounds = {cmk * 96 / 3600:.1f} h) | "
              f"{R / 4:.0f} | {R} | {R * AGGS_PER_COMMITTEE / c:.1f}")
    print("MK slide-by-1: unit changes every V/C rounds = "
          + ", ".join(f"{V / 23:,.0f} rounds ({V / 23 * 96 / 86400:.0f} d) at V={V:,}" for V in VS))
    print(f"backbone (all candidates): {SUBNETS_PER_NODE} subnets/node, rotated every 256 epochs = "
          f"{256 * 32 * 12 / 3600:.1f} h (phase0/p2p-interface.md:229,1724-1750)")
    for V in VS:
        c = V / 23 / 64
        uniq = c * SINGLE_DC
        print(f"one extra persistently subscribed subnet, V={V:,}, C=23: {fmt_bytes(uniq)} per 4 s unit = "
              f"{uniq * 8 / 1e6 / 4:.2f} Mbit/s unique, {7 * uniq * 8 / 1e6 / 4:.2f} Mbit/s at kappa 7 "
              f"(+{c * ihave_per_msg(12) * 8 / 1e6 / 4:.2f} Mbit/s IHAVE); today's subnet at kappa 7: "
              f"{7 * today(V)['per_subnet_b'] * 8 / 1e6 / 12:.2f} Mbit/s")
    print(f"secret-VRF duty (explainer.md:21,41): proof per vote = 96 B BLS signature -> "
          f"{SINGLE_DC} -> {SINGLE_DC + 96} B (+{100 * 96 / SINGLE_DC:.0f} %) and one more BLS verify per vote")


# ======================================================== S8: single-operator cohorts
def s8():
    hr("S8  Single-operator committees: contiguous layout vs strided, and aggregate censorship")
    print("expected share of an operator batch (b consecutive positions) sitting in committees it fills "
          "entirely; contiguous committees of size c")
    print("c | b=100 | b=1,000 | b=10,000")
    for c in (82, 488, 679):
        row = []
        for b in (100, 1000, 10000):
            full = max(0.0, (b - c + 1) / c)        # E[# committees fully covered], uniform start offset
            row.append(f"{min(1.0, full * c / b) * 100:.0f} %")
        print(f"{c} | " + " | ".join(row))
    print("strided (position mod #committees): 0 % unless the operator holds the whole set")
    print("\nP(no honest aggregator in a committee whose honest share is h) = (1-16/c)^(h c) ~ exp(-16 h)")
    for h in (0.01, 0.05, 0.10, 0.25, 0.5, 2 / 3):
        print(f"h = {h:.2f}: {exp(-AGGS_PER_COMMITTEE * h):.3g}")


# ======================================================== S9: no committees + rate limit
def s9():
    hr("S9  'All vote at round start, transport caps attestations at 20 %' (msg 1476), V=1M")
    V = 1_000_000
    per_subnet = V / SUBNETS * SINGLE_DC
    for link in (25, 50):
        cap = 0.2 * link * 1e6 / 8
        for kappa in (1, 7):
            backlog = SUBNETS_PER_NODE * per_subnet * kappa
            print(f"link {link} Mbit/s, kappa {kappa}: backlog {fmt_bytes(backlog)} on 2 subnets -> "
                  f"{backlog / cap:.0f} s to drain at 20 % (round = 96 s)")
    print(f"without any partition: one aggregate bitfield = V/8 = {fmt_bytes(V / 8)} (msg 1457); "
          f"global single-vote firehose = {fmt_bytes(V * SINGLE_DC)} per round unique")
    print(f"Q17 for comparison: 2 subnets x one unit = {fmt_bytes(2 * V / 23 / 64 * SINGLE_DC)} unique per 4 s")


if __name__ == "__main__":
    s1()
    s2()
    s3()
    s4()
    s5()
    s6()
    s7()
    s8()
    s9()
