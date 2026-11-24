#!/bin/bash
# post-process one finished run (realism_check + analyze --levers) at nice 19 on CPUs 48-95, capped at $2 GiB virtual
cd /home/yann/p2p-ministry-gossip2000
ulimit -v $(( ${2:-64} * 1048576 ))
s=$(date +%s)
/usr/bin/time -v python3 repo/sim/realism_check.py runs/$1 > runs/$1/realism.txt 2> runs/$1/realism.time
python3 repo/sim/analyze.py --levers runs/$1 > runs/$1/levers.md 2>&1
echo "$(date +%H:%M) post $1 done (manual, $(( $(date +%s) - s ))s, realism_check $(grep -o 'Maximum resident.*' runs/$1/realism.time))" >> runs/realistic.log
