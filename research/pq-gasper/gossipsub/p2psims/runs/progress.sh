#!/bin/bash
# simulated seconds reached by each run (stop time in brackets)
cd /home/yann/p2p-ministry-gossip2000/runs
for d in [fv]*/; do
  d=${d%/}
  t=$(grep 'Process resource usage' $d/shadow.log 2>/dev/null | tail -1 | grep -o 'simtime [0-9]*' | awk '{printf "%.0f", $2/1e9}')
  stop=$(grep -o 'stop_time: [0-9]*' $d/shadow.yaml | awk '{print $2}')
  st=$(grep -q 'Exit status: 0' $d/time.log 2>/dev/null && echo done || echo "")
  echo "$d ${t:-0}/$stop $st"
done
cat done.log 2>/dev/null
