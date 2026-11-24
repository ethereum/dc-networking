#!/bin/bash
# PQ publish errors per run: bash .amp-out/puberr.sh NAME... -> .amp-out/puberr-NAME.jsonl and .amp-out/puberr-summary-NAME.txt
cd /home/yann/p2p-ministry-gossip2000
for n in "$@"; do
  f=.amp-out/puberr-$n.jsonl
  taskset -c 48-95 nice -n 19 rg -F -j 4 --no-filename '"ev":"publish_err"' runs/$n/shadow.data/hosts -g '*.stdout' > $f
  echo "$n $(wc -l < $f) $(grep -o "\"err\":\"[A-Za-z]*" $f | sort | uniq -c | tr -s " \n" " ")" | tee .amp-out/puberr-summary-$n.txt
done
