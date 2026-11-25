#!/bin/bash
# Sequential queue for the PQ Gasper subnet specs study (Nov 23): which home link (down/up) passes at 1,600 signatures
# per subnet per slot. Lines "NAME HOSTS SLOTS THREADS extra-flags..." in runs/queue-specs.txt (re-read before each
# run; '#' lines skipped; names whose run dir exists skipped). Waits while runs/STOP-night exists (set by
# stop-run.sh, the watchdog and runs/pq1600-guard.py). Each run: run_pq1600.sh (the Q2048x20-m1600-s1 stack; later
# flags such as --links win), then .amp-out/pq1600.py (plain, SPLIT=access, SPLITCPU=1), specs.py, pqdiag.py and
# late.py into .amp-out/*-NAME.txt, then .amp-out/specs-decide.py, which appends the search's next run to the queue
# file (or logs that it needs a decision), then the 'post NAME done' line that stop-run.sh waits for.
# Start: nohup setsid taskset -c 48-95 nice -n 19 bash runs/specs-queue.sh > /dev/null 2>&1 < /dev/null &
cd /home/yann/p2p-ministry-gossip2000
while true; do
  [ -e runs/STOP-night ] && { sleep 30; continue; }
  line=$(while read -r n h s t rest; do [ -z "$n" ] || [ "${n:0:1}" = "#" ] && continue; [ -e runs/$n ] || { echo "$n $h $s $t $rest"; break; }; done < runs/queue-specs.txt)
  [ -z "$line" ] && { sleep 30; continue; }
  set -- $line; n=$1; h=$2; s=$3; t=$4; shift 4
  touch runs/nofallback-$n
  echo "$(date +%H:%M) start $n $h x $s ($t threads): $*" >> runs/realistic.log
  bash runs/run_pq1600.sh $n $h $s $t "$@"
  (ulimit -v $((150*1048576))
   POOL=12 python3 -I .amp-out/pq1600.py $n --per-slot > .amp-out/pq1600-$n.txt 2>&1
   SPLIT=access POOL=12 python3 -I .amp-out/pq1600.py $n > .amp-out/pq1600split-access-$n.txt 2>&1
   SPLITCPU=1 POOL=12 python3 -I .amp-out/pq1600.py $n > .amp-out/pq1600cpu-$n.txt 2>&1
   POOL=12 python3 -I .amp-out/specs.py $n > .amp-out/specs-$n.txt 2>&1
   python3 .amp-out/pqdiag.py $n --per-slot > .amp-out/pqdiag-$n.txt 2>&1
   python3 .amp-out/late.py $n > .amp-out/late-$n.txt 2>&1
   python3 -I .amp-out/specs-decide.py $n >> runs/realistic.log 2>&1)
  echo "$(date +%H:%M) post $n done" >> runs/realistic.log
done
