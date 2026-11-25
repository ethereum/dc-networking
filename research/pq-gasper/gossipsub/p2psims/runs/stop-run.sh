#!/bin/bash
# usage: bash runs/stop-run.sh NAME REASON NOTE
#   REASON: mem (the run itself is too big), avail (machine low on memory), otheruser, ...
# Stops run NAME if it is running (SIGTERM its shadow, then SIGKILL its wbsim) and pauses the queue (runs/STOP-night).
# Waits up to 1 h for night.sh to post-process the stopped run, keeps its partial output as runs/stopped-NAME-REASON
# and turns its queue line into a comment. For REASON mem, runs/queue-edit.py --scale-down puts the line back one step
# down the peer-scale ladder (1.0 > 0.75 > 0.5 > 0.25), moves the later lines with the same host count and scale down
# too, and the queue resumes; at x0.25 (bottom) or for other reasons the queue stays paused for the 2-hourly check.
# A file runs/nofallback-NAME turns the scale-down off for NAME (the queue stays paused): the 20-slot key cell must
# stay at x1.0, and its completed slots are kept in the partial output.
# Called by runs/watchdog256.sh and by the scheduled check. BASE overrides the project directory (tests only).
here=$(dirname "$(readlink -f "$0")")
cd "${BASE:-/home/yann/p2p-ministry-gossip2000}" || exit 1
name=$1; reason=$2; note=$3
touch runs/STOP-night
d=$(readlink -f "runs/$name"); [ -n "$name" ] && [ -d "$d" ] || d=/nonexistent
for p in $(pgrep -u yann -x shadow); do
  [ "$(readlink /proc/$p/cwd 2>/dev/null)" = "$d" ] || continue
  g=$(ps -o pgid= -p $p | tr -d ' ')
  kill -TERM $p; sleep 15
  [ -n "$g" ] && pkill -KILL -x wbsim -g "$g"
done
echo "$(date +%H:%M:%S) STOPPED $name ($reason): $note" >> runs/realistic.log
for i in $(seq 240); do grep -qF "post $name done" runs/realistic.log && break; sleep 15; done
dst=runs/stopped-$name-$reason; [ -e "$dst" ] && dst=$dst-$(date +%H%M)
[ -d "runs/$name" ] && mv -T "runs/$name" "$dst"
why="$(date '+%b %d %H:%M') stopped ($reason), partial output in $dst"
fb=""
if [ "$reason" = mem ] && [ ! -e "runs/nofallback-$name" ]; then
  fb=$(python3 "$here/queue-edit.py" runs/queue-night.txt "$name" "$why" --scale-down 2>> runs/realistic.log)
else
  python3 "$here/queue-edit.py" runs/queue-night.txt "$name" "$why" 2>> runs/realistic.log
fi
if [ -n "$fb" ]; then
  rm -f runs/STOP-night
  echo "$(date +%H:%M:%S) FALLBACK $name -> ${fb%% *} ($fb); queue resumed" >> runs/realistic.log
else
  echo "$(date +%H:%M:%S) $name stopped without fallback: queue paused (runs/STOP-night) until the check decides" >> runs/realistic.log
fi
