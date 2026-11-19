#!/usr/bin/env python3
"""Who holds the non-consolidated validators?

Takes the active validator set at the finalized state from a beacon API,
groups the 0x01 (32 ETH cap) validators by withdrawal address, classifies each
address as EOA / contract via eth_getCode, and groups contracts by bytecode so
that per-validator pool contracts (e.g. Rocket Pool minipools) are not counted
as independent small stakers.

Standard library only. Downloads ~400 MB of JSON and makes ~500 RPC batches;
everything is cached in --cache, so re-runs are offline.

    python3 snapshot.py --cache /tmp/consolidation --out results/YYYY-MM-DD.json
"""
import argparse
import collections
import hashlib
import json
import math
import os
import time
import urllib.request

ACTIVE = "active_ongoing,active_exiting,active_slashed"
SIZE_EDGES = [(1, 1), (2, 9), (10, 99), (100, 999), (1000, 9999), (10000, None)]

# Bytecode families, keyed by the first 16 hex chars of sha256(runtime code).
# Names come from the verified source of an example (or of the clone target)
# on Sourcify, looked up on 2026-11-19. "per_validator" families deploy one
# contract per validator or per user on behalf of a pool or operator, so a
# cluster of size 1 there says nothing about the size of whoever runs it.
FAMILIES = {
    "70552a0539c43f42": ("Rocket Pool minipool (RocketMinipoolBase clone)", "per_validator"),
    "ba27eff7f8d3b319": ("Rocket Pool minipool (RocketMinipool)", "per_validator"),
    "84a3798e473c6fb6": ("Kiln FeeRecipient clone", "per_validator"),
    "2f18a707cbc1b4c7": ("unverified clone family (target 0x3517d4c4…5025)", "per_validator"),
    "795d0bf061d2617c": ("unverified clone family (target 0x460f5e52…77be)", "per_validator"),
    "22fac77ee171c741": ("Rocket Pool megapool (RocketMegapoolProxy clone)", "owner"),
    "dd0443e7be0a3b5c": ("EigenPod (BeaconProxy)", "owner"),
    "5b8bff324e02136e": ("Safe proxy", "owner"),
    "a8a0fbd3cdf49e75": ("Safe proxy (older)", "owner"),
    "e49f633c212ea826": ("Safe proxy (older)", "owner"),
    "3cdb543ac9f75bb2": ("BitGo WalletSimple clone", "owner"),
    "02df2335274b9054": ("BitGo WalletSimple clone", "owner"),
    "1a7cd826b08b9cc1": ("StakeWise EthVault (ERC1967Proxy)", "owner"),
}


def fetch(url, path, timeout=600):
    if not os.path.exists(path):
        req = urllib.request.Request(url, headers={"user-agent": "curl/8"})
        with urllib.request.urlopen(req, timeout=timeout) as r, open(path, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
    return json.load(open(path))


def get_codes(addresses, rpc, path, batch=50):
    """address -> '' (EOA) | '7702:<delegate>' | '<codehash16>'."""
    out = json.load(open(path)) if os.path.exists(path) else {}
    rpcs = rpc.split(",")
    todo = [a for a in addresses if a not in out]
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        body = json.dumps([
            {"jsonrpc": "2.0", "id": k, "method": "eth_getCode", "params": ["0x" + a, "finalized"]}
            for k, a in enumerate(chunk)
        ]).encode()
        for attempt in range(6):
            try:
                req = urllib.request.Request(
                    rpcs[(i // batch + attempt) % len(rpcs)], data=body, headers={"content-type": "application/json", "user-agent": "curl/8"})
                res = json.load(urllib.request.urlopen(req, timeout=40))
                if not isinstance(res, list):
                    raise RuntimeError(str(res)[:200])
                if any("result" not in r for r in res):
                    raise RuntimeError(str(res)[:200])
                for r in res:
                    code = r["result"]
                    if code == "0x":
                        v = ""
                    elif code.startswith("0xef0100"):
                        v = "7702:" + code[8:]
                    else:
                        v = hashlib.sha256(bytes.fromhex(code[2:])).hexdigest()[:16]
                    out[chunk[r["id"]]] = v
                break
            except Exception as e:  # public endpoints rate-limit; back off
                print("retry", i, repr(e)[:120], flush=True)
                time.sleep(2 + 3 * attempt)
        if i % 500 == 0:
            print("codes", len(out), flush=True)
            json.dump(out, open(path, "w"))
    json.dump(out, open(path, "w"))
    return out


def bucket(n):
    for lo, hi in SIZE_EDGES:
        if n >= lo and (hi is None or n <= hi):
            return f"{lo}" if lo == hi else f"{lo}+" if hi is None else f"{lo}-{hi}"


def kind(code):
    if code == "" or code.startswith("7702:"):
        return "eoa"
    fam = FAMILIES.get(code[:16])
    if fam is None:
        return "other_contract"
    return "pool_per_validator" if fam[1] == "per_validator" else "owner_contract"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--beacon", default="https://ethereum-beacon-api.publicnode.com")
    ap.add_argument("--rpc", default="https://ethereum-rpc.publicnode.com",
                    help="execution RPC; comma-separate several to rotate")
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.cache, exist_ok=True)

    header = fetch(f"{a.beacon}/eth/v1/beacon/headers/finalized", f"{a.cache}/header.json")
    vals = fetch(f"{a.beacon}/eth/v1/beacon/states/finalized/validators?status={ACTIVE}",
                 f"{a.cache}/validators.json")["data"]

    n = len(vals)
    by_type = collections.defaultdict(lambda: [0, 0])
    c01 = collections.Counter()             # 0x01 validators per withdrawal address
    stake = collections.Counter()           # ETH per entity key, all credential types
    count = collections.Counter()
    c02_single = collections.Counter()      # 0x02 validators still at <= 32 ETH
    for v in vals:
        w = v["validator"]["withdrawal_credentials"]
        t, eb = w[2:4], int(v["validator"]["effective_balance"]) // 10**9
        key = w[-40:] if t != "00" else "bls:" + w[4:]
        by_type[t][0] += 1
        by_type[t][1] += eb
        stake[key] += eb
        count[key] += 1
        if t == "01":
            c01[key] += 1
        elif t == "02" and eb <= 32:
            c02_single[key] += 1
    total = sum(stake.values())
    n01 = sum(c01.values())

    codes = get_codes(sorted(c01), a.rpc, f"{a.cache}/code.json")

    # 0x01 validators by cluster size x address kind
    table = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    fam = collections.defaultdict(lambda: [0, 0])
    for addr, k in c01.items():
        cell = table[bucket(k)][kind(codes[addr])]
        cell[0] += 1
        cell[1] += k
        name = FAMILIES.get(codes[addr][:16], (None,))[0]
        if name:
            fam[name][0] += 1
            fam[name][1] += k

    # same clusters in power-of-two buckets: 64 validators x 32 ETH = one
    # full 2,048 ETH (MAX_EFFECTIVE_BALANCE_ELECTRA) validator
    pow2 = collections.defaultdict(lambda: [0, 0, 0])
    for addr, k in c01.items():
        lo = 1 << (k.bit_length() - 1)
        cell = pow2[lo]
        cell[0] += 1
        cell[1] += k
        cell[2] += math.ceil(k / 64)

    # floor: every entity merges down to ceil(stake / 2048) validators
    floor = collections.defaultdict(lambda: [0, 0, 0])
    for key, s in stake.items():
        cell = floor[bucket(max(1, round(s / 32)))]
        cell[0] += 1
        cell[1] += count[key]
        cell[2] += math.ceil(s / 2048)

    res = {
        "slot": int(header["data"]["header"]["message"]["slot"]),
        "active_validators": n,
        "effective_balance_eth": total,
        "by_credential_type": {"0x" + t: {"validators": c, "eth": s} for t, (c, s) in sorted(by_type.items())},
        "unconsolidated_0x01": {
            "validators": n01,
            "withdrawal_addresses": len(c01),
            "by_cluster_size": {b: {k: {"addresses": x[0], "validators": x[1]} for k, x in sorted(row.items())}
                                for b, row in table.items()},
            "by_power_of_two": {f"{lo}-{2 * lo - 1}": {"addresses": x[0], "validators": x[1],
                                                       "validators_if_merged_to_2048": x[2]}
                                for lo, x in sorted(pow2.items())},
            "contract_families": {name: {"addresses": x[0], "validators": x[1]}
                                  for name, x in sorted(fam.items(), key=lambda kv: -kv[1][1])},
            "top_addresses": [{"address": "0x" + ad, "validators": k} for ad, k in c01.most_common(10)],
        },
        "0x02_at_32_eth": {"validators": sum(c02_single.values()), "addresses": len(c02_single)},
        "floor_full_consolidation": {
            "validators": sum(x[2] for x in floor.values()),
            "by_entity_size": {b: {"entities": x[0], "validators_now": x[1], "validators_floor": x[2]}
                               for b, x in floor.items()},
        },
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(res, open(a.out, "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
