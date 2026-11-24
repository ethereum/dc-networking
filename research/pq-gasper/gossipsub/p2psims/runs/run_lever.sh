#!/bin/bash
# usage: run_lever.sh NAME HOSTS SLOTS THREADS [gen_config flood flags...]
# Base: mainnet validator sample, k=8 (hosts with > 8 validators on 1 Gbit), rest 80 % EIP-7870 (50/25, 50/15
# without validators) and 20 % 1 Gbit, 2,000 x 3,072 B per slot. Later flags override earlier ones.
set -u
cd /home/yann/p2p-ministry-gossip2000
name=$1; hosts=$2; slots=$3; threads=$4; shift 4
dir=runs/$name
[ -e $dir ] && exit 0
mkdir -p $dir
python3 repo/sim/gen_config.py --mode flood --hosts $hosts --slots $slots --drain 8 --parallelism $threads \
  --no-cpu-pinning --validators-csv data/f9ba162f-nodes.csv --msgs 2000 --fast-above 8 --fast-share 0.2 \
  --links 50/25 --links-novalidator 50/15 "$@" --out $dir > $dir/gen.txt 2>&1 || exit 1
# Shadow install: shadow-install/bin, or the bin directory named in runs/shadowbin-NAME (e.g. the lnxbuf build)
sbin=/home/yann/p2p-ministry-gossip2000/shadow-install/bin
[ -f runs/shadowbin-$name ] && sbin=$(cat runs/shadowbin-$name)
echo "$sbin" > $dir/shadow-bin.txt
cd $dir
start=$(date +%s)
taskset -c 48-95 /usr/bin/time -v env PATH=$sbin:$PATH \
  nice -n 19 shadow shadow.yaml > shadow.log 2> time.log
rc=$?
rm -f shadow.data/hosts/*/wbsim.*.shimlog
# Runs with the TCP diagnostics (a shadowbin "-log" wrapper sets LNXBUF_LOG=1): move the "tcpd" and "lnxbuf" lines to
# shadow-tcpd.log.gz, so that shadow.log stays small (analyze.py reads it whole to check its last line).
if grep -a -q -m 1 -F -e '] tcpd ' -e '] lnxbuf ' shadow.log; then
  grep -a -F -e '] tcpd ' -e '] lnxbuf ' shadow.log | gzip -4 > shadow-tcpd.log.gz &&
    grep -a -v -F -e '] tcpd ' -e '] lnxbuf ' shadow.log > shadow.log.split && mv shadow.log.split shadow.log
fi
echo "$(date +%H:%M) $name rc=$rc wall=$(( $(date +%s) - start ))s $(grep 'Maximum resident' time.log)" >> ../done-levers.log
