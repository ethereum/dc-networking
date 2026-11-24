# Socket buffer sizes logged by the lnxbuf Shadow build (LNXBUF_LOG=1): initial sizes and autotuned growth per link class.
import json, re, sys, collections
run = sys.argv[1]
link = {f"n{n['id']:04d}": n["link"] for n in json.load(open(f"{run}/run.json"))["nodes"]}
H = re.compile(r"\[(n\d{4})[:\]]")
init, sends, recvs, autot = collections.Counter(), collections.defaultdict(list), collections.defaultdict(list), collections.Counter()
rtt = 0
for line in open(f"{run}/shadow.log", errors="replace"):
    if "lnxbuf " not in line:
        continue
    h = H.search(line); c = link.get(h.group(1), "?") if h else "?"
    if "lnxbuf first rtt" in line:
        rtt += 1; continue
    m = re.search(r"lnxbuf initial send (\d+) receive (\d+) autotune send (\d) receive (\d)", line)
    if m:
        init[(c, int(m.group(1)), int(m.group(2)))] += 1; autot[(m.group(3), m.group(4))] += 1; continue
    m = re.search(r"lnxbuf send (\d+) -> (\d+)", line)
    if m:
        sends[c].append(int(m.group(2))); continue
    m = re.search(r"lnxbuf receive (\d+) -> (\d+)", line)
    if m:
        recvs[c].append(int(m.group(2)))
print("initial sizes (class, send, receive): sockets", dict(init))
print("autotune flags (send, receive): sockets", dict(autot))
for c in sorted(set(sends) | set(recvs)):
    s, r = sends.get(c, []), recvs.get(c, [])
    print(f"{c}: send growth steps {len(s)}, max {max(s, default=0)} (at 4 MiB cap: {sum(x == 4194304 for x in s)}); "
          f"receive growth steps {len(r)}, max {max(r, default=0)} (at 6 MiB cap: {sum(x == 6291456 for x in r)})")
allinit = [k for k in init]
ok = all(snd <= 131072 and rcv <= 174760 for _, snd, rcv in allinit) and \
     all(x <= 4194304 for v in sends.values() for x in v) and all(x <= 6291456 for v in recvs.values() for x in v)
print(f"first RTT samples (sockets): {rtt}; initial-size events: {sum(init.values())} (none means Shadow's initial sizing never ran)")
print("CHECK", "PASS" if ok else "FAIL", "(no socket starts above 131,072 / 174,760 B or grows past 4 / 6 MiB)")
