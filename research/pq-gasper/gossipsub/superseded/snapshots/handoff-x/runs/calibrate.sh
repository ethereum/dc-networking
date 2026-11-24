#!/bin/bash
# Calibration against today's BLS mainnet: no PQ, every perturbation at its sourced value.
cd /home/user/workspace/repo
until grep -q "all done" runs/validate.log && grep -q "validate2 done" runs/validate.log; do sleep 20; done
CAL="--mode flood --drain 4 --parallelism 16 --no-cpu-pinning --validators-csv data/f9ba162f-nodes.csv --msgs 2000
 --fast-above 8 --fast-share 0.2 --links 50/25 --links-novalidator 50/15 --sig-subnets 16 --one-subnet
 --peer-target 50 --warmup 30 --seed 1
 --no-pq --bg --net cities --access --jitter --loss --verify --slow-cpu-share 0.2 --scoring --client-mix --client-gs
 --nat-share 0.3 --churn-conn-life 1800 --churn-restart-per-day 0.143"
run() {  # name hosts slots flags...
  name=$1; hosts=$2; slots=$3; shift 3
  d=runs/$name
  [ -e $d/realism.json ] && return
  rm -rf $d
  python3 sim/gen_config.py $CAL --hosts $hosts --slots $slots "$@" --out $d > /dev/null 2>&1 || { echo "$name gen failed" >> runs/calibrate.log; return; }
  s=$(date +%s)
  (cd $d && /usr/bin/time -v ~/.local/bin/shadow shadow.yaml > shadow.log 2> time.log)
  rc=$?
  python3 sim/realism_check.py $d > /dev/null 2>&1
  echo "$(date +%H:%M) $name rc=$rc wall=$(( $(date +%s) - s ))s $(grep -o 'Maximum resident.*' $d/time.log)" >> runs/calibrate.log
}
run C1 256 6 --peer-scale 0.3
run C2 256 6 --peer-scale 0.3
echo "$(date +%H:%M) batch done" >> runs/calibrate.log; sleep infinity
