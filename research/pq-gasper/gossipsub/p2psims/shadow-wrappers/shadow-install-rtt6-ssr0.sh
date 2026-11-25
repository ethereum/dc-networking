#!/bin/sh
# ssr0 (PQ Gasper one-subnet study, Nov 17): the rtt6 Shadow build (Linux v6.12 CUBIC with HyStart, window validation,
# consecutive duplicate-ACK counting) without restart after idle (RTT5_SSR=0), as Linux with
# net.ipv4.tcp_slow_start_after_idle=0; cwv6 without the tcpd logging. Used through runs/shadowbin-NAME.
RTT5_CWV=1 RTT5_SSR=0 RTT5_DUP=1 RTT6_CUBIC=1 RTT6_HYSTART=1 exec /home/yann/p2p-ministry-gossip2000/shadow-install-rtt6/bin/shadow "$@"
