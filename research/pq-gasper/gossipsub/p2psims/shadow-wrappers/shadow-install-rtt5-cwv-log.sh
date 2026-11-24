#!/bin/sh
# The rtt5 Shadow build with window validation only (RTT5_CWV=1 RTT5_SSR=0 RTT5_DUP=1: no restart after idle, as Linux
# with net.ipv4.tcp_slow_start_after_idle=0) and its tcpd diagnostics logged (LNXBUF_LOG=1), which runs/run_lever.sh
# moves from shadow.log to shadow-tcpd.log.gz. Used through runs/shadowbin-NAME (coordinator 21:1x Nov 10).
RTT5_CWV=1 RTT5_SSR=0 RTT5_DUP=1 LNXBUF_LOG=1 exec /home/yann/p2p-ministry-gossip2000/shadow-install-rtt5/bin/shadow "$@"
