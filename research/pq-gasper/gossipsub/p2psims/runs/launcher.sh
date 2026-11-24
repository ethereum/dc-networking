#!/bin/bash
# Starts queue2.txt runs one at a time while this user's simulations stay under budget:
# at most 6 Shadow instances and 160 GB RSS at launch (runs grow after they start; the
# target is to stay under ~250 GB, half the machine). CPUs are capped by taskset in run_one.sh.
cd /home/yann/p2p-ministry-gossip2000
while read -r line; do
  [ -z "$line" ] && continue
  while true; do
    n=$(pgrep -u yann -x shadow | wc -l)
    rss=$(ps -u yann -o rss=,comm= | awk '$2=="shadow"||$2=="wbsim"{s+=$1} END{printf "%d", s/1048576}')
    [ "$n" -lt 6 ] && [ "$rss" -lt 160 ] && break
    sleep 60
  done
  echo "$(date +%H:%M) start $line (running $n, ${rss} GB)" >> runs/launcher.log
  setsid runs/run_one.sh $line &
  sleep 120   # let the new run allocate before the next check
done < runs/queue2.txt
wait
