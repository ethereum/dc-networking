# Calibration table from realism.json (same metrics as results/realism-calibration.md section 2)
import json, sys
for run in sys.argv[1:]:
    r = json.load(open(f"runs/{run}/realism.json"))
    p, bg, pe, sc = r["prop"], r["bg"], r["peers"], r["scoring"]
    f = lambda xs, idx: " / ".join(f"{xs[i]:.2f}" for i in idx)
    print(f"== {run}: {r['hosts']} hosts, {r['slots']} slots")
    print(" block from slot start p50/p90/p99:", f(p["block"]["from_slot_start_s"], (1, 2, 4)), " missing", p["block"]["missing"], "/", p["block"]["deliveries"])
    print(" block from publish p50/p95/p99:", f(p["block"]["from_publish_s"], (1, 3, 4)))
    a = p["att"]["after_4s_mark_s"]; print(" att after 4 s p50/p95/p99:", f(a, (1, 3, 4)), " missing", p["att"]["missing"], "/", p["att"]["deliveries"], f"({100*p['att']['missing']/p['att']['deliveries']:.2f} %)")
    g = [x - 8 for x in p["agg"]["from_slot_start_s"]]; print(" agg after 8 s p50/p95:", f(g, (1, 3)), " missing", p["agg"]["missing"])
    print(" col from slot start p50/p95:", f(p["col"]["from_slot_start_s"], (1, 3)), " missing", p["col"]["missing"], "/", p["col"]["deliveries"])
    d = bg["copies_per_unique_msg"]; print(" duplicates (copies-1):", {k: round(v - 1, 2) for k, v in d.items()})
    for c, v in bg["per_class"].items():
        bac = (v.get("bg_block_recv_kB_per_slot", 0) + v.get("bg_att_recv_kB_per_slot", 0) + v.get("bg_col_recv_kB_per_slot", 0)) / 12
        print(f"  {c}: n={v['nodes']} block+att+col {bac:.0f} kB/s, rx {v['rx_Mbit_s_mean']} Mbit/s, tx p50 {v['tx_kB_s'][1]*8/1e3:.2f} Mbit/s")
    print(" conns:", {k: v["conns"]["mean"] for k, v in pe.items()})
    print(" mesh means:", {k: {t[5:]: v[t]["mean"] for t in v if t.startswith("mesh_")} for k, v in pe.items() if k.startswith("link:") or k == "lighthouse"})
    print(" mesh_links per slot:", [x["mesh_links"] for x in sc["per_slot"]])
    print(" neg-score peers per slot:", [x["peers_with_negative_score"] for x in sc["per_slot"]], "penalties", sc["penalties"])
    print(" churn:", json.dumps(r.get("churn"))[:300])
    print(" verify:", json.dumps(r.get("verify"))[:300])
