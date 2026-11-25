#!/bin/bash
cd /home/yann/p2p-ministry-gossip2000
REAL="--sig-subnets 16 --one-subnet --peer-target 50 --warmup 30 --bg --net cities --access --jitter --loss --verify --slow-cpu-share 0.2 --scoring --client-mix --client-gs --peer-scale 0.25 --nat-share 0.3 --churn-conn-life 1800 --churn-restart-per-day 0.143 --churn-leave 0.005 --churn-join 0.005"
post() { nice python3 repo/sim/realism_check.py runs/$1 > runs/$1/realism.txt 2>&1; nice python3 repo/sim/analyze.py --levers runs/$1 > runs/$1/levers.md 2>&1; echo "$(date +%H:%M) post $1 done" >> runs/realistic.log; }
bash runs/run_lever.sh R-m512-s1 512 25 46 $REAL --seed 1; post R-m512-s1
