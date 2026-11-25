#!/bin/sh
# The rtt5b Shadow build with RTT5_BETA=1 (CUBIC's decrease, ssthresh = max(cwnd * 717 / 1024, 2), at fast-recovery
# entry and at an RTO; the other three rtt5 switches stay on by default) and its tcpd diagnostics logged (LNXBUF_LOG=1),
# which runs/run_lever.sh moves from shadow.log to shadow-tcpd.log.gz. Used through runs/shadowbin-NAME.
RTT5_BETA=1 LNXBUF_LOG=1 exec /home/yann/p2p-ministry-gossip2000/shadow-install-rtt5b/bin/shadow "$@"
