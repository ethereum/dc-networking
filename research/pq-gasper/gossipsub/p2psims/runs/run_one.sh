#!/bin/bash
# usage: run_one.sh NAME [gen_config flood flags...]
# One Shadow run, confined to CPUs 48-95 (half the shared machine) at nice 19.
set -u
cd /home/yann/p2p-ministry-gossip2000
name=$1; shift
dir=runs/$name
[ -e $dir/shadow.yaml ] && exit 0  # started or finished already
python3 repo/sim/gen_config.py --mode flood --slots 10 --drain 12 --parallelism 46 --no-cpu-pinning "$@" --out $dir > $dir.gen.txt
mv $dir.gen.txt $dir/gen.txt
cd $dir
start=$(date +%s)
taskset -c 48-95 /usr/bin/time -v env PATH=/home/yann/p2p-ministry-gossip2000/shadow-install/bin:$PATH nice -n 19 shadow shadow.yaml > shadow.log 2> time.log
rc=$?
rm -f shadow.data/hosts/*/wbsim.*.shimlog
echo "$(date +%H:%M) $name rc=$rc wall=$(( $(date +%s) - start ))s $(grep 'Maximum resident' time.log)" >> ../done.log
