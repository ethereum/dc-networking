#!/bin/bash
cd /home/user/workspace/repo
REAL="--net cities --access --jitter --loss --verify --slow-cpu-share 0.2 --scoring --client-mix --client-gs
 --nat-share 0.3 --churn-conn-life 1800 --churn-restart-per-day 0.143 --churn-leave 0.005 --churn-join 0.005 --bg"
BASE="--mode flood --drain 4 --no-cpu-pinning --validators-csv data/f9ba162f-nodes.csv --msgs 2000
 --fast-above 8 --fast-share 0.2 --links 50/25 --links-novalidator 50/15 --sig-subnets 16 --one-subnet
 --peer-target 50 --warmup 30"
run() {  # name flags...
  name=$1; shift
  d=runs/$name
  [ -e $d/realism.json ] && return
  rm -rf $d
  python3 sim/gen_config.py $BASE $REAL "$@" --out $d > $d.gen.txt 2>&1 || { echo "$name gen failed" >> runs/stage3.log; return; }
  s=$(date +%s)
  (cd $d && /usr/bin/time -v ~/.local/bin/shadow shadow.yaml > shadow.log 2> time.log)
  rc=$?
  rm -f $d/shadow.data/hosts/*/wbsim.*.shimlog
  python3 sim/realism_check.py $d > /dev/null 2>&1
  python3 sim/analyze.py --levers $d > $d/levers.md 2>&1
  echo "$(date +%H:%M) $name rc=$rc wall=$(( $(date +%s) - s ))s $(grep -o 'Maximum resident.*' $d/time.log)" >> runs/stage3.log
}
run C3 --no-pq --hosts 256 --slots 6 --peer-scale 0.3 --parallelism 16 --seed 1
run M1 --hosts 512 --slots 20 --peer-scale 0.25 --parallelism 16 --seed 1
echo "$(date +%H:%M) stage3 done" >> runs/stage3.log
sleep infinity
