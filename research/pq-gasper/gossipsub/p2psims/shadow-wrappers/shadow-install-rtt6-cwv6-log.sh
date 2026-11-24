#!/bin/sh
# cwv6: the rtt6 Shadow build (Linux's CUBIC with HyStart) with window validation and consecutive duplicate-ACK counting
# but no restart after idle (RTT5_SSR=0), as Linux with net.ipv4.tcp_slow_start_after_idle=0, and its tcpd diagnostics
# logged (LNXBUF_LOG=1), which runs/run_lever.sh moves from shadow.log to shadow-tcpd.log.gz. Used through
# runs/shadowbin-NAME as the fallback build of the runs after the rtt6 cells (coordinator 06:5x Nov 11).
RTT5_CWV=1 RTT5_SSR=0 RTT5_DUP=1 RTT6_CUBIC=1 RTT6_HYSTART=1 LNXBUF_LOG=1 exec /home/yann/p2p-ministry-gossip2000/shadow-install-rtt6/bin/shadow "$@"
