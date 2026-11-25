#!/bin/bash
# Runs queue.txt one line at a time. Re-reads the file after every run, so lines can be appended
# while it works; stops when every listed run has a directory.
cd /home/yann/p2p-ministry-gossip2000
while true; do
  next=$(while read -r name rest; do [ -n "$name" ] && [ ! -e runs/$name ] && echo "$name $rest" && break; done < runs/queue.txt)
  [ -z "$next" ] && break
  runs/run_one.sh $next
done
