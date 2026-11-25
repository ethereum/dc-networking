#!/bin/bash
# Kills the largest running shadow run if machine-wide used memory (total - available) exceeds LIMIT GiB.
LIMIT=${1:-385}
cd /home/yann/p2p-ministry-gossip2000
while true; do
  used=$(free -g | awk '/Mem:/{print $2-$7}')
  if [ "$used" -gt "$LIMIT" ]; then
    best=0; bp=""
    for p in $(pgrep -x shadow); do pg=$(ps -o pgid= -p $p | tr -d ' ');
      m=$(ps -eo pgid=,rss= | awk -v g=$pg '$1==g{m+=$2} END{print int(m/1048576)}'); [ $m -gt $best ] && { best=$m; bp=$p; }; done
    if [ -n "$bp" ]; then d=$(readlink /proc/$bp/cwd); g=$(ps -o pgid= -p $bp | tr -d ' '); kill -TERM $bp; sleep 5; pkill -KILL -x wbsim -g $g 2>/dev/null
      echo "$(date +%H:%M:%S) WATCHDOG used=${used}GiB > $LIMIT: killed $(basename $d) (${best} GiB)" >> runs/realistic.log; fi
  fi
  sleep 10; done
