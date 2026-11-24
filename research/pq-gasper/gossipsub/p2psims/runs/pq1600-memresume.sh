#!/bin/bash
# PQ Gasper one-subnet study (Nov 17): after the watchdog stops a run for memory (stop-run.sh NAME mem: queue paused,
# run dir moved to runs/stopped-NAME-mem once its post line is written), comment out NAME's line in
# runs/queue-pq1600.txt, so it does not rerun, and resume the queue unless the half-budget guard holds it
# (runs/HALF-pq1600). The completed slots of the stopped run stay in its partial output.
# Start: nohup setsid taskset -c 48-95 nice -n 19 bash runs/pq1600-memresume.sh > /dev/null 2>&1 < /dev/null &
cd /home/yann/p2p-ministry-gossip2000
touch runs/pq1600-memresume.done
while true; do
  sleep 30
  for n in $(grep -o 'STOPPED [^ ]* (mem)' runs/realistic.log | awk '{print $2}'); do
    grep -qx "$n" runs/pq1600-memresume.done && continue
    grep -q "^$n " runs/queue-pq1600.txt || { echo "$n" >> runs/pq1600-memresume.done; continue; }
    [ -e "runs/$n" ] && continue  # stop-run.sh has not moved it yet (waits for the post line)
    python3 - "$n" <<'EOF'
import os, sys, time
n, p = sys.argv[1], "runs/queue-pq1600.txt"
lines = open(p).read().splitlines(keepends=True)
out = [f"# {time.strftime('%b %d %H:%M')} stopped (mem), partial output in runs/stopped-{n}-mem: {l}" if l.startswith(n + " ") else l
       for l in lines]
open(p + ".tmp", "w").writelines(out)
os.replace(p + ".tmp", p)
EOF
    echo "$n" >> runs/pq1600-memresume.done
    if [ ! -e runs/HALF-pq1600 ]; then rm -f runs/STOP-night; fi
    echo "$(date +%H:%M:%S) MEMRESUME $n stopped for memory: queue line commented out; queue $([ -e runs/STOP-night ] && echo 'still paused (guard)' || echo resumed)" >> runs/realistic.log
  done
done
