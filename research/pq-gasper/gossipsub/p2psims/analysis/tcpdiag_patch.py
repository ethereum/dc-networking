# Apply TCP diagnostics (cur, rtt) and the rtt fixes (rtt) to a Shadow tree's tcp.c. usage: tcpdiag_patch.py TREE cur|rtt
import sys
tree, mode = sys.argv[1], sys.argv[2]
F = f"{tree}/src/main/host/descriptor/tcp.c"
s = open(F).read()
def rep(a, b):
    global s
    n = s.count(a)
    if n != 1:
        sys.exit(f"anchor x{n}: {a[:70]!r}")
    s = s.replace(a, b)
if "#include <stdlib.h>" not in s:
    rep("#include <errno.h>\n", "#include <errno.h>\n#include <stdlib.h>\n")
rep("static void _tcp_flush(TCP* tcp, const Host* host);\n", """static void _tcp_flush(TCP* tcp, const Host* host);

/* diagnostics: with LNXBUF_LOG set in Shadow's environment, log per-connection TCP state ("tcpd" lines) at info level */
static int _tcp_diagLog(void) {
    static int on = -1;
    if (on < 0) {
        on = getenv("LNXBUF_LOG") != NULL;
    }
    return on;
}
""")
rep("""        guint backoffCount;

        void *tally;
    } retransmit;
""", """        guint backoffCount;

        void *tally;
    } retransmit;

    /* diagnostics (LNXBUF_LOG) */
    struct {
        guint64 samples;
        guint64 timeouts;
        guint64 spurious;
        guint64 txData;
        gint lastBin;
        gboolean toPending;
        CSimulationTime toTime;
    } diag;
""")
rep("    tcp->autotune.isEnabled = TRUE;\n", "    tcp->autotune.isEnabled = TRUE;\n    tcp->diag.lastBin = G_MININT;\n")
rep("""static void _tcp_updateRTTEstimate(TCP* tcp, const Host* host, CSimulationTime timestamp) {
    MAGIC_ASSERT(tcp);
""", """static void _tcp_updateRTTEstimate(TCP* tcp, const Host* host, CSimulationTime timestamp) {
    MAGIC_ASSERT(tcp);
    tcp->diag.samples++;
""")
rep("""    tcp->retransmit.backoffCount++;
    _tcp_setRetransmitTimeout(tcp, tcp->retransmit.timeout * 2);
    _tcp_setRetransmitTimer(tcp, host, now);
""", """    gint diagOldRTO = tcp->retransmit.timeout;
    tcp->retransmit.backoffCount++;
    _tcp_setRetransmitTimeout(tcp, tcp->retransmit.timeout * 2);
    _tcp_setRetransmitTimer(tcp, host, now);
    tcp->diag.timeouts++;
    tcp->diag.toPending = TRUE;
    tcp->diag.toTime = now;
    if (_tcp_diagLog()) {
        info("tcpd timeout %p rto %d -> %d backoff %u srtt %d rttvar %d", (void*)tcp, diagOldRTO,
             tcp->retransmit.timeout, tcp->retransmit.backoffCount, tcp->timing.rttSmoothed,
             tcp->timing.rttVariance);
    }
""")
rep("""void tcp_networkInterfaceIsAboutToSendPacket(TCP* tcp, const Host* host, Packet* packet) {
    MAGIC_ASSERT(tcp);
""", """void tcp_networkInterfaceIsAboutToSendPacket(TCP* tcp, const Host* host, Packet* packet) {
    MAGIC_ASSERT(tcp);
    if (packet_getPayloadSize(packet) > 0) {
        tcp->diag.txData++;
    }
""")
cond = "header->timestampEcho && tcp->retransmit.backoffCount == 0"
if mode == "rtt":
    cond += " && (flags & TCP_PF_DATA_ACKED)"
rep("""    tcp->receive.lastTimestamp = header->timestampValue;
    if(header->timestampEcho && tcp->retransmit.backoffCount == 0) {
        _tcp_updateRTTEstimate(tcp, host, header->timestampEcho);
    }
""", """    tcp->receive.lastTimestamp = header->timestampValue;
""" + ("""    /* rtt: sample only on packets that acknowledge new data, so a packet sent long after the last one received
     * (echoing an old TSval) cannot inflate SRTT */
""" if mode == "rtt" else "") + f"""    if({cond}) {{
        _tcp_updateRTTEstimate(tcp, host, header->timestampEcho);
    }}
""" + """    if (tcp->diag.toPending && (flags & TCP_PF_DATA_ACKED)) {
        tcp->diag.toPending = FALSE;
        gboolean diagSpurious = header->timestampEcho != 0 && header->timestampEcho < tcp->diag.toTime;
        if (diagSpurious) {
            tcp->diag.spurious++;
        }
        if (_tcp_diagLog()) {
            info("tcpd acked-after-timeout %p echo %d spurious %d srtt %d rttvar %d rto %d expect %d", (void*)tcp,
                 (int)(header->timestampEcho != 0), (int)diagSpurious, tcp->timing.rttSmoothed,
                 tcp->timing.rttVariance, tcp->retransmit.timeout,
                 tcp->timing.rttSmoothed + MAX(4 * tcp->timing.rttVariance, CONFIG_TCP_RTO_MIN));
        }
    }
    if (_tcp_diagLog()) {
        gint64 diagMs = (gint64)(worker_getCurrentSimulationTime() / SIMTIME_ONE_MILLISECOND);
        gint diagBin = (gint)((diagMs + 90000) / 12000) - 10; /* 12 s bins, boundaries at 30 s + k x 12 s */
        if (diagBin != tcp->diag.lastBin) {
            tcp->diag.lastBin = diagBin;
            info("tcpd snap %p bin %d peer %u state %d srtt %d rttvar %d rto %d backoff %u samples %" G_GUINT64_FORMAT
                 " timeouts %" G_GUINT64_FORMAT " spurious %" G_GUINT64_FORMAT " retx %" G_GSIZE_FORMAT
                 " txdata %" G_GUINT64_FORMAT " cfgrtt %u sndbuf %" G_GSIZE_FORMAT " rcvbuf %" G_GSIZE_FORMAT " cwnd %u",
                 (void*)tcp, diagBin, (unsigned)tcp_getPeerIP(tcp), (int)tcp->state, tcp->timing.rttSmoothed,
                 tcp->timing.rttVariance, tcp->retransmit.timeout, tcp->retransmit.backoffCount, tcp->diag.samples,
                 tcp->diag.timeouts, tcp->diag.spurious, tcp->info.retransmitCount, tcp->diag.txData,
                 _tcp_calculateRTT(tcp, host), legacysocket_getOutputBufferSize(&(tcp->super)),
                 legacysocket_getInputBufferSize(&(tcp->super)), (unsigned)tcp->cong.cwnd);
        }
    }
""")
if mode == "rtt":
    rep("""    /* clear it so we dont send outdated timestamp echos */
    tcp->receive.lastTimestamp = 0;
""", """    /* rtt: keep the most recent TSval received (RFC 7323 TS.Recent), so every later packet, including delayed ACKs
     * sent by the ACK timer, echoes it; Shadow cleared it here, before the interface sent anything, so every echo
     * was 0 and no RTT sample was ever taken */
""")
    rep("""    gint newRTO = tcp->timing.rttSmoothed + (4 * tcp->timing.rttVariance);""",
        """    /* rtt: like Linux, floor the variance term at 200 ms: RTO = SRTT + max(4 RTTVAR, 200 ms) */
    gint newRTO = tcp->timing.rttSmoothed + MAX(4 * tcp->timing.rttVariance, CONFIG_TCP_RTO_MIN);""")
    for a in ["""            if (_tcp_lnxbufLog() && newSize >= 1048576) {
                info("lnxbuf receive %" G_GSIZE_FORMAT " -> %" G_GSIZE_FORMAT, currentSize, newSize);
            }
""", """        if (_tcp_lnxbufLog() && newSize >= 1048576) {
            info("lnxbuf send %" G_GSIZE_FORMAT " -> %" G_GSIZE_FORMAT " cwnd %u", currentSize, newSize,
                 (unsigned)tcp->cong.cwnd);
        }
"""]:
        rep(a, "")
open(F, "w").write(s)
print("patched", F, mode)
