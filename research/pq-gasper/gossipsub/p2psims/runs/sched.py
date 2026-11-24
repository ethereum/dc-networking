#!/usr/bin/env python3
"""Run the lever queue within the shared-machine budget.

queue-levers.txt lines: NAME HOSTS SLOTS THREADS MEM_GB gen_config flood flags...
Budget: 48 CPUs (48-95) and 256 GB for this user's simulations; half of that while other users load the machine
(> 8 cores busy or > 64 GB resident). Re-reads the queue every minute, so lines can be appended. Logs to sched.log.
"""
import os, subprocess, time, shlex

ROOT = "/home/yann/p2p-ministry-gossip2000"
os.chdir(ROOT)
LOG = "runs/sched.log"
running = {}  # name -> (Popen, threads, mem)


def log(msg):
    with open(LOG, "a") as f:
        f.write(time.strftime("%H:%M:%S ") + msg + "\n")


def others():
    """CPU cores and GB used by other users right now."""
    out = subprocess.run(["top", "-bn2", "-d2", "-w", "512"], capture_output=True, text=True).stdout
    last = out.split("top - ")[-1].splitlines()
    cpu = 0.0
    hdr = False
    for line in last:
        f = line.split()
        if f[:1] == ["PID"]:
            hdr = True
            continue
        if hdr and len(f) > 8 and f[1] != "yann":
            try:
                cpu += float(f[8])
            except ValueError:
                pass
    rss = subprocess.run(["ps", "-eo", "user=,rss="], capture_output=True, text=True).stdout
    mem = sum(int(r.split()[1]) for r in rss.splitlines() if r.split()[0] != "yann") / 2 ** 20
    return cpu / 100, mem


def mine_gb():
    rss = subprocess.run(["ps", "-u", "yann", "-o", "rss=,comm="], capture_output=True, text=True).stdout
    return sum(int(r.split()[0]) for r in rss.splitlines() if r.split()[1] in ("shadow", "wbsim")) / 2 ** 20


def queue():
    out = []
    for line in open("runs/queue-levers.txt"):
        line = line.split("#")[0].strip()
        if line:
            f = shlex.split(line)
            out.append((f[0], int(f[1]), int(f[2]), int(f[3]), int(f[4]), f[5:]))
    return out


stop_launch = os.path.exists("runs/STOP")
while True:
    for name, (p, _, _) in list(running.items()):
        if p.poll() is not None:
            log(f"done {name} rc={p.returncode}")
            del running[name]
    if os.path.exists("runs/STOP"):
        if not running:
            log("STOP file and nothing running: exit")
            break
        time.sleep(60)
        continue
    pending = [q for q in queue() if not os.path.exists(f"runs/{q[0]}")]
    if not pending and not running:
        time.sleep(60)
        continue
    cpu_o, mem_o = others()
    busy = cpu_o > 8 or mem_o > 64
    cpu_b, mem_b = (24, 128) if busy else (48, 256)
    used_t = sum(t for _, t, _ in running.values())
    used_m = max(mine_gb(), sum(m for _, _, m in running.values()))
    for name, hosts, slots, threads, mem, flags in pending:
        if used_t + threads <= cpu_b and used_m + mem <= mem_b:
            cmd = ["bash", "runs/run_lever.sh", name, str(hosts), str(slots), str(threads)] + flags
            running[name] = (subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL), threads, mem)
            used_t += threads
            used_m += mem
            log(f"start {name} ({threads} thr, est {mem} GB; others {cpu_o:.1f} cores {mem_o:.0f} GB; "
                f"budget {cpu_b}/{mem_b}; now {used_t} thr)")
        break  # keep queue order: never skip ahead of the first pending run
    time.sleep(60)
