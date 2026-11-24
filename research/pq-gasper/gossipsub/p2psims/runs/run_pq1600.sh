#!/bin/bash
# usage: run_pq1600.sh NAME HOSTS SLOTS THREADS [extra gen_config flags, later ones win]
# PQ Gasper one-subnet study (Nov 17): one PQ subnet that every node joins and needs, 1,600 signatures of 2,404 B per
# slot (leanXMSS) in bundles of up to 16 per publisher, published 4.0-4.5 s, deadline 8.0 s. Realism stack of
# results/gossip-one-subnet-realistic.md (client mix and default peer targets, cf2 scoring, cities RTT, access, jitter,
# loss, verification, slow CPUs, NAT, churn) on Shadow rtt6 (Linux v6.12 CUBIC + HyStart, slow start after idle), no
# tcpd logging. Background: blocks, columns, aggregates, sync messages; no BLS attestations (--no-att), which PQ Gasper
# replaces. run_lever.sh adds the base flags (mainnet validator CSV, > 8 validators on 1 Gbit + 20 % of the rest,
# 50/25 with validators, 50/15 without).
cd /home/yann/p2p-ministry-gossip2000
name=$1; hosts=$2; slots=$3; threads=$4; shift 4
ONE="--single-subnet 16 --peer-target 50 --warmup 30 --bg --no-att --net cities --access --jitter --loss --verify
 --slow-cpu-share 0.2 --scoring --client-mix --client-gs --peer-scale 1.0 --nat-share 0.3 --churn-conn-life 1800
 --churn-restart-per-day 0.143 --churn-leave 0.005 --churn-join 0.005 --msgs 1600 --msg-bytes 2404 --batch 16
 --max-msg-age 60 --client-slow-peer --client-p3-promises --binary /home/yann/p2p-ministry-gossip2000/bin/cf2/wbsim
 --seed 1"
# --with-att (this script only): keep today's BLS attestations (drops --no-att)
args=()
for x in "$@"; do [ "$x" = --with-att ] && ONE=${ONE/--no-att/} || args+=("$x"); done
[ -f runs/shadowbin-$name ] || echo /home/yann/p2p-ministry-gossip2000/shadow-install-rtt6/bin > runs/shadowbin-$name
bash runs/run_lever.sh $name $hosts $slots $threads $ONE "${args[@]}"
