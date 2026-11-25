#!/bin/bash
# 256 GB rule. When this project's processes (shadow + wbsim + analysis python, see runs/memsum.py) exceed LIMIT GiB
# summed PSS, or the machine has less than MINAVAIL GiB available, stops the largest shadow run with runs/stop-run.sh,
# reason mem (the run itself is too big: stop-run.sh restarts it one peer-scale step down) or avail (machine low on
# memory: the queue stays paused). 235 GiB = 252 GB, under 256 GB either way.
# Since Nov 07 19:45 the cap uses summed PSS, not summed RSS: summed RSS counts the wbsim binary's shared pages once
# per process (+13.8 GiB at 2,048 hosts); summed PSS matched the MemAvailable drop within 1.4 GiB (19:39 check).
# Start: nohup setsid taskset -c 48-95 nice -n 19 bash runs/watchdog256.sh 235 30 > /dev/null 2>&1 < /dev/null &
LIMIT=${1:-235}; MINAVAIL=${2:-30}
cd /home/yann/p2p-ministry-gossip2000
while true; do
  out=$(python3 runs/memsum.py)
  read rss pss <<< "$(head -1 <<< "$out")"
  tot=${pss%.*}
  avail=$(free -g | awk '/Mem:/{print $7}')
  if [ -n "$tot" ] && { [ "$tot" -gt "$LIMIT" ] || [ "$avail" -lt "$MINAVAIL" ]; }; then
    read n best <<< "$(tail -n +2 <<< "$out" | sort -k3 -n -r | head -1 | awk '{print $1, $3}')"
    if [ -n "$n" ]; then
      why=mem; [ "$tot" -gt "$LIMIT" ] || why=avail
      echo "$(date +%H:%M:%S) WATCHDOG project PSS=${pss}GiB RSS=${rss}GiB (limit $LIMIT PSS) avail=${avail}GiB: stopping $n (PSS ${best} GiB), reason $why" >> runs/realistic.log
      bash runs/stop-run.sh "$n" $why "watchdog: project PSS ${pss} GiB (limit $LIMIT), available ${avail} GiB (min $MINAVAIL), run PSS ${best} GiB"
    fi
  fi
  sleep 15
done
