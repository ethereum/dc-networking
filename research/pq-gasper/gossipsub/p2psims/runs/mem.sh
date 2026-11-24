#!/bin/bash
# GB of RSS per run (shadow + its wbsim processes), with simulated time reached
cd /home/yann/p2p-ministry-gossip2000/runs
for p in $(pgrep -u yann -x shadow); do
  run=$(basename $(readlink /proc/$p/cwd))
  kids=$(pgrep -P $p -x wbsim | tr '\n' ',' | sed 's/,$//')
  rss=$( (ps -o rss= -p $p; [ -n "$kids" ] && ps -o rss= -p $kids) | awk '{s+=$1} END{printf "%.1f", s/1048576}')
  t=$(grep 'Process resource usage' $run/shadow.log | tail -1 | grep -o 'simtime [0-9]*' | awk '{printf "%.0f", $2/1e9}')
  state=$(ps -o stat= -p $p | cut -c1)
  echo "$rss GB $run t=$t $state"
done | sort -rn
free -g | sed -n 2p
