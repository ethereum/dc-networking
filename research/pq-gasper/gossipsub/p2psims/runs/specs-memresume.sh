#!/bin/bash
# PQ Gasper subnet specs study (Nov 23): runs/pq1600-memresume.sh for runs/queue-specs.txt. After the watchdog stops a
# run for memory (stop-run.sh NAME mem: queue paused, run dir moved to runs/stopped-NAME-mem once its post line is
# written), comment out NAME's line, so it does not rerun, and resume the queue unless the half-budget guard holds it
# (runs/HALF-pq1600). The queue analysed the stopped run's completed slots before its post line, and
# .amp-out/specs-decide.py counts the run if they reach slot 10.
# Start: nohup setsid taskset -c 48-95 nice -n 19 bash runs/specs-memresume.sh > /dev/null 2>&1 < /dev/null &
cd /home/yann/p2p-ministry-gossip2000
touch runs/specs-memresume.done
while true; do
  sleep 30
  for n in $(grep -o 'STOPPED [^ ]* (mem)' runs/realistic.log | awk '{print $2}'); do
    grep -qx "$n" runs/specs-memresume.done && continue
    grep -q "^$n " runs/queue-specs.txt || { echo "$n" >> runs/specs-memresume.done; continue; }
    [ -e "runs/$n" ] && continue  # stop-run.sh has not moved it yet (waits for the post line)
    python3 - "$n" <<'EOF'
import os, sys, time
n, p = sys.argv[1], "runs/queue-specs.txt"
lines = open(p).read().splitlines(keepends=True)
out = [f"# {time.strftime('%b %d %H:%M')} stopped (mem), partial output in runs/stopped-{n}-mem: {l}" if l.startswith(n + " ") else l
       for l in lines]
open(p + ".tmp", "w").writelines(out)
os.replace(p + ".tmp", p)
EOF
    echo "$n" >> runs/specs-memresume.done
    if [ ! -e runs/HALF-pq1600 ]; then rm -f runs/STOP-night; fi
    echo "$(date +%H:%M:%S) MEMRESUME $n stopped for memory: queue line commented out; queue $([ -e runs/STOP-night ] && echo 'still paused (guard)' || echo resumed)" >> runs/realistic.log
  done
done
