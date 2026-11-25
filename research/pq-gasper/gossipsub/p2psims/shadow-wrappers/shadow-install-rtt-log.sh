#!/bin/sh
# The rtt Shadow build with its tcpd diagnostics logged (LNXBUF_LOG=1): the same simulation, plus per-connection TCP
# lines (snapshots per 12 s bin, timeouts, ACKs after timeouts) in shadow.log. Used through runs/shadowbin-NAME.
LNXBUF_LOG=1 exec /home/yann/p2p-ministry-gossip2000/shadow-install-rtt/bin/shadow "$@"
