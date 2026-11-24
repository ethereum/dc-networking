#!/bin/bash
# Sequential queue: lines "NAME HOSTS SLOTS extra-flags..." in runs/queue-night.txt (re-read before each run).
# Realism flags (REAL) at 46 threads; skips names whose run dir exists; waits while runs/STOP-night exists.
# Start: nohup setsid taskset -c 48-95 nice -n 19 bash runs/night.sh > /dev/null 2>&1 < /dev/null &
cd /home/yann/p2p-ministry-gossip2000
REAL="--sig-subnets 16 --one-subnet --peer-target 50 --warmup 30 --bg --net cities --access --jitter --loss --verify --slow-cpu-share 0.2 --scoring --client-mix --client-gs --peer-scale 0.25 --nat-share 0.3 --churn-conn-life 1800 --churn-restart-per-day 0.143 --churn-leave 0.005 --churn-join 0.005"
while true; do
  [ -e runs/STOP-night ] && { sleep 30; continue; }
  line=$(while read -r n h s rest; do [ -z "$n" ] || [ "${n:0:1}" = "#" ] && continue; [ -e runs/$n ] || { echo "$n $h $s $rest"; break; }; done < runs/queue-night.txt)
  [ -z "$line" ] && { sleep 30; continue; }
  set -- $line; n=$1; h=$2; s=$3; shift 3
  echo "$(date +%H:%M) start $n $h x $s: $*" >> runs/realistic.log
  bash runs/run_lever.sh $n $h $s 46 $REAL "$@"
  (ulimit -v $((150*1048576)); python3 repo/sim/realism_check.py runs/$n > runs/$n/realism.txt 2>&1
   python3 repo/sim/analyze.py --levers runs/$n > runs/$n/levers.md 2>&1)
  echo "$(date +%H:%M) post $n done" >> runs/realistic.log
done
