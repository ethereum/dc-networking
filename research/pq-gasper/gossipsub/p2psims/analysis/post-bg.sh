#!/bin/bash
# analyses for the 13:30 check: calibration of R-nopq-s1 and an indicative look at the stopped R-pq-s1 (slots 0-3)
cd /home/yann/p2p-ministry-gossip2000
python3 .amp-out/calib.py R-nopq-s1 > .amp-out/calib-R-nopq-s1.txt 2>&1
python3 .amp-out/attmiss.py R-nopq-s1 > .amp-out/attmiss-R-nopq-s1.txt 2>&1
python3 repo/sim/realism_check.py runs/stopped-R-pq-s1-mem/trunc4 > runs/stopped-R-pq-s1-mem/trunc4/realism.txt 2>&1
python3 repo/sim/analyze.py --levers runs/stopped-R-pq-s1-mem/trunc4 > runs/stopped-R-pq-s1-mem/trunc4/levers.md 2>&1
echo done > .amp-out/post-bg.done
