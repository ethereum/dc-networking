#!/bin/bash
# every 30 s, per running shadow run: summed RSS of the run (shadow + wbsim, GiB), project summed RSS incl. analysis
# python, machine available (free -g), then (since Nov 07 19:45) the run's and the project's summed PSS (runs/memsum.py).
# The watchdog caps on project PSS; RSS overstates it by the wbsim binary's shared pages (~6.9 MiB per host).
cd /home/yann/p2p-ministry-gossip2000
while true; do
  out=$(python3 runs/memsum.py)
  read tot ptot <<< "$(head -1 <<< "$out")"
  av=$(free -g | awk '/Mem:/{print $7}')
  tail -n +2 <<< "$out" | while read n m p; do d=$(readlink -f runs/$n)
    st=$(grep 'Process resource' $d/shadow.log | tail -1 | grep -o 'simtime [0-9]*' | awk '{printf "%.0f", $2/1e9}')
    echo "$(date +%H:%M:%S) $n sim=${st}s rss=${m}GB proj=${tot}GB avail=${av}GB pss=${p}GB projpss=${ptot}GB"; done >> runs/memlog.txt
  sleep 30; done
