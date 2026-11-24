# Flood messages ignored by --max-msg-age (wbsim tick counters stale_pq / stale_bg, cumulative), summed over hosts
# from each host's last tick line. usage: python3 .amp-out/stale.py RUN
import glob, json, sys
run = sys.argv[1] if "/" in sys.argv[1] else f"runs/{sys.argv[1]}"
sp = sb = n = 0
for f in glob.glob(f"{run}/shadow.data/hosts/*/wbsim.*.stdout"):
    last = None
    for line in open(f):
        if '"ev":"tick"' in line:
            last = line
    if last:
        e = json.loads(last); sp += e.get("stale_pq", 0); sb += e.get("stale_bg", 0); n += 1
print(f"{run}: stale_pq {sp}, stale_bg {sb} (summed over {n} hosts)")
