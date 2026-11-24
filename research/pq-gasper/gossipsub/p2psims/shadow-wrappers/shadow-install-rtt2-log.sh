#!/bin/sh
# The rtt2 Shadow build with its tcpd diagnostics logged (LNXBUF_LOG=1): the same simulation, plus per-connection TCP
# lines (snapshots per 12 s bin, timeouts, ACKs after timeouts, Eifel undos), which runs/run_lever.sh moves from
# shadow.log to shadow-tcpd.log.gz. Used through runs/shadowbin-NAME.
LNXBUF_LOG=1 exec /home/yann/p2p-ministry-gossip2000/shadow-install-rtt2/bin/shadow "$@"
