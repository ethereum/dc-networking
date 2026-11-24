#!/bin/bash
# One perturbation at a time, 128 hosts, PQ one-subnet scenario on. Two lanes of 8 Shadow threads each.
cd /home/user/workspace/repo
B="--mode flood --drain 4 --parallelism 8 --no-cpu-pinning --validators-csv data/f9ba162f-nodes.csv --msgs 2000
 --fast-above 8 --fast-share 0.2 --links 50/25 --links-novalidator 50/15 --sig-subnets 16 --one-subnet
 --peer-target 50 --warmup 30 --hosts 128 --seed 1"
run() {  # name slots flags...
  name=$1; slots=$2; shift 2
  d=runs/V-$name
  [ -e $d/realism.json ] && return
  rm -rf $d
  python3 sim/gen_config.py $B --slots $slots "$@" --out $d > /dev/null 2>&1 || { echo "$name gen failed" >> runs/validate.log; return; }
  s=$(date +%s)
  (cd $d && /usr/bin/time -v ~/.local/bin/shadow shadow.yaml > shadow.log 2> time.log)
  rc=$?
  python3 sim/realism_check.py $d > /dev/null 2>&1
  echo "$(date +%H:%M) $name rc=$rc wall=$(( $(date +%s) - s ))s $(grep -o 'Maximum resident.*' $d/time.log)" >> runs/validate.log
}
lane1() {
  run base 5
  run rtt 4 --net cities --access --jitter --ping 2
  run loss10 4 --net cities --access --loss --loss-scale 10 --pcap 6
  run loss 4 --net cities --access --loss --pcap 6
  run churn 6 --churn-conn-life 600 --churn-restart-per-day 1500 --churn-leave 0.05 --churn-join 0.05
}
lane2() {
  run bg 5 --bg
  run verify 5 --verify --slow-cpu-share 0.3
  run score 5 --bg --scoring --bad-share 0.03
  run nat 5 --client-mix --peer-scale 0.25 --nat-share 0.4
  run free 5 --freeride-share 0.1
}
lane1 & lane2 & wait
echo "$(date +%H:%M) all done" >> runs/validate.log
