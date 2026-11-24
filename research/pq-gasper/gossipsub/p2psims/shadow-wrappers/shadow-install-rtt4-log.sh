#!/bin/sh
# The rtt4 Shadow build with its tcpd diagnostics logged (LNXBUF_LOG=1): the same simulation, plus per-connection TCP
# lines (snapshots per 12 s bin with echo counters, timeouts, recoveries, ACKs after timeouts, Eifel undos), which
# runs/run_lever.sh moves from shadow.log to shadow-tcpd.log.gz. Used through runs/shadowbin-NAME.
LNXBUF_LOG=1 exec /home/yann/p2p-ministry-gossip2000/shadow-install-rtt4/bin/shadow "$@"
