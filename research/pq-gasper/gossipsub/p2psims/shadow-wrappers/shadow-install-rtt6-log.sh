#!/bin/sh
# The rtt6 Shadow build (rtt5 with its three switches on, plus Linux CUBIC with HyStart; RTT6_CUBIC and RTT6_HYSTART on
# by default) with its tcpd diagnostics logged (LNXBUF_LOG=1), which runs/run_lever.sh moves from shadow.log to
# shadow-tcpd.log.gz. Used through runs/shadowbin-NAME.
LNXBUF_LOG=1 exec /home/yann/p2p-ministry-gossip2000/shadow-install-rtt6/bin/shadow "$@"
