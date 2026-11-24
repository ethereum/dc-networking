# rtt2 = rtt + Eifel undo of spurious timeouts + Linux's RTT estimator (tcp_rtt_estimator, __tcp_set_rto, Linux v6.12).
# Applies to a copy of shadow-src-rtt (lnxbuf + rtt fixes + tcpd diagnostics). usage: rtt2_patch.py TREE
# Runtime switches (Shadow's environment), default = rtt2: RTT2_UNDO=0 turns the undo off; RTT2_EST=rfc restores rtt's
# RFC 6298 estimator, its sampling rule and Shadow's SRTT reset after three timeouts. Both set = rtt behaviour.
import sys
tree = sys.argv[1]
D = f"{tree}/src/main/host/descriptor"


def patch(path, reps):
    s = open(path).read()
    for a, b in reps:
        n = s.count(a)
        if n != 1:
            sys.exit(f"{path}: anchor x{n}: {a[:80]!r}")
        s = s.replace(a, b)
    open(path, "w").write(s)
    print("patched", path)


# --- Reno: save and undo ------------------------------------------------------------------------------------------
patch(f"{D}/tcp_cong_reno.h", [("void tcp_cong_reno_init(TCP *tcp);\n", """void tcp_cong_reno_init(TCP *tcp);

/* rtt2 (Eifel undo): cwnd and the whole Reno state (state machine, duplicate ACK count, CA counter, ssthresh) */
typedef struct TCPCongRenoSaved_ {
    guint32 cwnd;
    unsigned char ca[64];
} TCPCongRenoSaved;
void tcp_cong_reno_save(TCP *tcp, TCPCongRenoSaved *saved);
/* restore the saved Reno state, with cwnd and ssthresh at least their saved values (Linux tcp_undo_cwnd_reduction) */
void tcp_cong_reno_undo(TCP *tcp, const TCPCongRenoSaved *saved);
""")])
patch(f"{D}/tcp_cong_reno.c", [("#include <stdlib.h>\n", "#include <stdlib.h>\n#include <string.h>\n"),
                               ("void tcp_cong_reno_init(TCP *tcp) {", """_Static_assert(sizeof(CAReno) <= sizeof(((TCPCongRenoSaved *)0)->ca), "CAReno does not fit");

void tcp_cong_reno_save(TCP *tcp, TCPCongRenoSaved *saved) {
    saved->cwnd = tcp_cong(tcp)->cwnd;
    memcpy(saved->ca, tcp_cong(tcp)->ca, sizeof(CAReno));
}

void tcp_cong_reno_undo(TCP *tcp, const TCPCongRenoSaved *saved) {
    CAReno *reno = tcp_cong(tcp)->ca;
    CAReno old;
    memcpy(&old, saved->ca, sizeof(CAReno));
    guint32 ssthresh = MAX(reno->ssthresh, old.ssthresh);
    guint32 cwnd = MAX(tcp_cong(tcp)->cwnd, saved->cwnd);
    *reno = old;
    reno->ssthresh = ssthresh;
    tcp_cong(tcp)->cwnd = cwnd;
}

void tcp_cong_reno_init(TCP *tcp) {""")])

# --- retransmit tally: undo -------------------------------------------------------------------------------------
patch(f"{D}/tcp_retransmit_tally.h", [("void retransmit_tally_clear_retransmitted(void *p);\n", """void retransmit_tally_clear_retransmitted(void *p);
/* rtt2 (Eifel undo): clear every lost mark (Linux clears TCPCB_LOST) and unmark the given resends, which were dropped
 * before they were sent, as retransmitted */
void retransmit_tally_undo(void *p, const uint32_t *unsent, size_t n);
""")])
patch(f"{D}/tcp_retransmit_tally.cc", [("void retransmit_tally_clear_retransmitted(void *p) {", """void retransmit_tally_undo(void *p, const uint32_t *unsent, size_t n) {
   auto rt = cast_and_assert(p);
   rt->marked_lost_.clear();
   Ranges drop;
   for (size_t i = 0; i < n; ++i) {
      ranges_insert(&drop, {static_cast<SeqNum>(unsent[i]), static_cast<SeqNum>(unsent[i]) + 1});
   }
   rt->retransmitted_ = ranges_subtract(rt->retransmitted_, drop);
   rt->compute_lost();
}

void retransmit_tally_clear_retransmitted(void *p) {""")])

# --- tcp.c ------------------------------------------------------------------------------------------------------
T = f"{D}/tcp.c"
patch(T, [
    # switches
    ("""static int _tcp_diagLog(void) {""", """/* rtt2 switches: RTT2_UNDO=0 turns the Eifel undo off; RTT2_EST=rfc restores rtt's RFC 6298 estimator */
static int _tcp_rtt2Undo(void) {
    static int on = -1;
    if (on < 0) {
        const char* v = getenv("RTT2_UNDO");
        on = !(v && strcmp(v, "0") == 0);
    }
    return on;
}
static int _tcp_rtt2LinuxEst(void) {
    static int on = -1;
    if (on < 0) {
        const char* v = getenv("RTT2_EST");
        on = !(v && strcmp(v, "rfc") == 0);
    }
    return on;
}

static int _tcp_diagLog(void) {"""),
    # state
    ("""        gboolean toPending;
        CSimulationTime toTime;
    } diag;
""", """        gboolean toPending;
        CSimulationTime toTime;
        guint64 undoChecks;
        guint64 undone;
        guint64 dropped;
        guint64 txRetx;
        guint64 retxAfterUndo;
        guint32 maxDeparted;
        gboolean departedAny;
    } diag;

    /* rtt2: Linux's RTT estimator state in microseconds (srtt8 = 8 x SRTT, mdev = 4 x mean deviation) */
    struct {
        gint64 srtt8;
        gint64 mdev;
        gint64 mdevMax;
        gint64 rttvar;
        guint32 rttSeq;
    } est;

    /* rtt2: Eifel undo state of the current timeout episode */
    struct {
        gboolean armed;
        gboolean haveRetxSeq;
        gboolean haveRetxTime;
        guint32 retxSeq;
        CSimulationTime retxTime;
        guint32 seqHigh;
        TCPCongRenoSaved saved;
        gboolean watch;
        guint32 watchHigh;
    } undo;
"""),
    # estimator
    ("""static void _tcp_updateRTTEstimate(TCP* tcp, const Host* host, CSimulationTime timestamp) {
    MAGIC_ASSERT(tcp);
    tcp->diag.samples++;

    CSimulationTime now = worker_getCurrentSimulationTime();
""", """/* rtt2: RTO from Linux's estimator (__tcp_set_rto, tcp_bound_rto): SRTT + rttvar, in ms rounded up, at most 120 s */
static gint _tcp_rtt2RTO(TCP* tcp) {
    gint64 rtoUs = (tcp->est.srtt8 >> 3) + tcp->est.rttvar;
    return (gint)MAX((gint64)CONFIG_TCP_RTO_MIN, MIN((rtoUs + 999) / 1000, (gint64)CONFIG_TCP_RTO_MAX));
}

static void _tcp_updateRTTEstimate(TCP* tcp, const Host* host, CSimulationTime timestamp) {
    MAGIC_ASSERT(tcp);
    tcp->diag.samples++;

    CSimulationTime now = worker_getCurrentSimulationTime();

    if (_tcp_rtt2LinuxEst()) {
        /* rtt2: Linux's tcp_rtt_estimator (net/ipv4/tcp_input.c, v6.12), in microseconds */
        gint64 m = (gint64)((now - timestamp) / SIMTIME_ONE_MICROSECOND);
        if (m <= 0) {
            m = 1;
        }
        const gint64 rtoMinUs = (gint64)CONFIG_TCP_RTO_MIN * 1000;
        gint64 srtt = tcp->est.srtt8;
        gboolean first = (srtt == 0);
        if (!first) {
            m -= (srtt >> 3); /* m is now the error in the RTT estimate */
            srtt += m;        /* SRTT = 7/8 SRTT + 1/8 sample */
            if (m < 0) {
                m = -m;
                m -= (tcp->est.mdev >> 2);
                if (m > 0) {
                    m >>= 3; /* finer gain when the RTT decreases */
                }
            } else {
                m -= (tcp->est.mdev >> 2);
            }
            tcp->est.mdev += m; /* mdev = 3/4 mdev + 1/4 |error| */
            if (tcp->est.mdev > tcp->est.mdevMax) {
                tcp->est.mdevMax = tcp->est.mdev;
                if (tcp->est.mdevMax > tcp->est.rttvar) {
                    tcp->est.rttvar = tcp->est.mdevMax;
                }
            }
            /* once per RTT: snd_una passed rtt_seq */
            if (tcp->send.unacked > tcp->est.rttSeq) {
                if (tcp->est.mdevMax < tcp->est.rttvar) {
                    tcp->est.rttvar -= (tcp->est.rttvar - tcp->est.mdevMax) >> 2;
                }
                tcp->est.rttSeq = tcp->send.highestSequence + 1; /* snd_nxt */
                tcp->est.mdevMax = rtoMinUs;
            }
        } else {
            srtt = m << 3;
            tcp->est.mdev = m << 1;
            tcp->est.rttvar = MAX(tcp->est.mdev, rtoMinUs);
            tcp->est.mdevMax = tcp->est.rttvar;
            tcp->est.rttSeq = tcp->send.highestSequence + 1;
        }
        tcp->est.srtt8 = MAX((gint64)1, srtt);

        /* Shadow's millisecond fields: SRTT drives receive-buffer autotuning; both are logged */
        tcp->timing.rttSmoothed = (gint)MAX((gint64)1, (tcp->est.srtt8 >> 3) / 1000);
        tcp->timing.rttVariance = (gint)(tcp->est.rttvar / 1000);
        if (first) {
            if (_tcp_lnxbufLog()) {
                info("lnxbuf first rtt %d ms enabled %d didinit %d send %" G_GSIZE_FORMAT " receive %" G_GSIZE_FORMAT,
                     tcp->timing.rttSmoothed, (int)tcp->autotune.isEnabled,
                     (int)tcp->autotune.didInitializeBufferSizes, legacysocket_getOutputBufferSize(&(tcp->super)),
                     legacysocket_getInputBufferSize(&(tcp->super)));
            }
            if (tcp->autotune.isEnabled && !tcp->autotune.didInitializeBufferSizes) {
                _tcp_tuneInitialBufferSizes(tcp, host);
            }
        }
        _tcp_setRetransmitTimeout(tcp, _tcp_rtt2RTO(tcp));
        return;
    }
"""),
    # first retransmission of an episode
    ("""    trace("retransmitting packet %d", sequence);
""", """    trace("retransmitting packet %d", sequence);

    /* rtt2: remember the first retransmission of a timeout episode; its departure time is the Eifel reference */
    if (tcp->undo.armed && !tcp->undo.haveRetxSeq) {
        tcp->undo.retxSeq = (guint32)sequence;
        tcp->undo.haveRetxSeq = TRUE;
    }
"""),
    # departures
    ("""    PacketTCPHeader header = packet_getTCPHeader(packet);

    if (header.flags & PTCP_ACK) {
        /* we are sending an ACK already, so we may not need any delayed ACK */""",
     """    PacketTCPHeader header = packet_getTCPHeader(packet);

    /* rtt2 diagnostics: data packets depart in sequence order, so a data packet at or below the highest departed
     * sequence is a resend; and the Eifel reference time (the TSval of the first retransmission) */
    if (packet_getPayloadSize(packet) > 0 && header.sequence > 0) {
        if (tcp->undo.watch && tcp->send.unacked > tcp->undo.watchHigh) {
            tcp->undo.watch = FALSE; /* the undone range is fully acknowledged */
        }
        if (tcp->diag.departedAny && (guint32)header.sequence <= tcp->diag.maxDeparted) {
            tcp->diag.txRetx++;
            if (tcp->undo.watch && (guint32)header.sequence <= tcp->undo.watchHigh) {
                tcp->diag.retxAfterUndo++;
            }
        } else {
            tcp->diag.maxDeparted = (guint32)header.sequence;
            tcp->diag.departedAny = TRUE;
        }
        if (tcp->undo.armed && tcp->undo.haveRetxSeq && !tcp->undo.haveRetxTime &&
            (guint32)header.sequence == tcp->undo.retxSeq) {
            tcp->undo.haveRetxTime = TRUE;
            tcp->undo.retxTime = now;
        }
    }

    if (header.flags & PTCP_ACK) {
        /* we are sending an ACK already, so we may not need any delayed ACK */"""),
    # timeout: arm the undo at the first timeout of an episode
    ("""    gint diagOldRTO = tcp->retransmit.timeout;
    tcp->retransmit.backoffCount++;""", """    gint diagOldRTO = tcp->retransmit.timeout;
    guint32 diagOldCwnd = tcp->cong.cwnd, diagOldSsthresh = tcp->cong.hooks->tcp_cong_ssthresh(tcp);
    /* rtt2: at the first timeout of an episode (backoff 0 -> 1) save cwnd and the Reno state for an Eifel undo */
    if (_tcp_rtt2Undo() && tcp->retransmit.backoffCount == 0) {
        tcp_cong_reno_save(tcp, &tcp->undo.saved);
        tcp->undo.armed = TRUE;
        tcp->undo.haveRetxSeq = FALSE;
        tcp->undo.haveRetxTime = FALSE;
        tcp->undo.seqHigh = tcp->send.highestSequence;
        tcp->undo.watch = FALSE;
    }
    tcp->retransmit.backoffCount++;"""),
    ("""        info("tcpd timeout %p rto %d -> %d backoff %u srtt %d rttvar %d", (void*)tcp, diagOldRTO,
             tcp->retransmit.timeout, tcp->retransmit.backoffCount, tcp->timing.rttSmoothed,
             tcp->timing.rttVariance);""", """        info("tcpd timeout %p rto %d -> %d backoff %u srtt %d rttvar %d cwnd %u ssthresh %u", (void*)tcp, diagOldRTO,
             tcp->retransmit.timeout, tcp->retransmit.backoffCount, tcp->timing.rttSmoothed,
             tcp->timing.rttVariance, diagOldCwnd, diagOldSsthresh);"""),
    # Shadow's SRTT reset after three timeouts in a row: not in Linux, so not with the Linux estimator
    ("""        if(tcp->retransmit.backoffCount > 2) {
            tcp->timing.rttSmoothed = 0;""", """        if(tcp->retransmit.backoffCount > 2 && !_tcp_rtt2LinuxEst()) {
            tcp->timing.rttSmoothed = 0;"""),
    # sampling rule
    ("""    if(header->timestampEcho && tcp->retransmit.backoffCount == 0 && (flags & TCP_PF_DATA_ACKED)) {
        _tcp_updateRTTEstimate(tcp, host, header->timestampEcho);
    }
""", """    if(header->timestampEcho && (flags & TCP_PF_DATA_ACKED) &&
       (_tcp_rtt2LinuxEst() || tcp->retransmit.backoffCount == 0)) {
        _tcp_updateRTTEstimate(tcp, host, header->timestampEcho);
    }
    /* rtt2: Eifel undo (RFC 3522; Linux tcp_try_undo_loss) at the first ACK of new data after a timeout */
    if (tcp->undo.armed && (flags & TCP_PF_DATA_ACKED)) {
        tcp->undo.armed = FALSE;
        tcp->diag.undoChecks++;
        gboolean spurious = !tcp->undo.haveRetxTime ||
                            (header->timestampEcho != 0 && header->timestampEcho < tcp->undo.retxTime);
        guint32 cw0 = tcp->cong.cwnd, ss0 = tcp->cong.hooks->tcp_cong_ssthresh(tcp);
        guint dropped = 0, requeued = 0, freed = 0;
        int rearmed = 0;
        if (spurious) {
            tcp_cong_reno_undo(tcp, &tcp->undo.saved);
            /* the timeout queued every outstanding packet for resending at once; drop the resends not yet sent:
             * back into the retransmit queue if still unacknowledged, freed if already acknowledged */
            GArray* unsent = g_array_new(FALSE, FALSE, sizeof(guint32));
            GQueue keep = G_QUEUE_INIT;
            while (!priorityqueue_isEmpty(tcp->throttledOutput)) {
                Packet* p = priorityqueue_peek(tcp->throttledOutput);
                PacketTCPHeader h = packet_getTCPHeader(p);
                if ((guint32)h.sequence > tcp->undo.seqHigh) {
                    break; /* new data from here on: the queue is in sequence order */
                }
                priorityqueue_pop(tcp->throttledOutput);
                gsize len = packet_getPayloadSize(p);
                if (len == 0 || h.sequence == 0) {
                    g_queue_push_tail(&keep, p);
                    continue;
                }
                tcp->throttledOutputLength -= len;
                guint32 s = (guint32)h.sequence;
                g_array_append_val(unsent, s);
                dropped++;
                if (h.sequence >= tcp->send.unacked) {
                    _tcp_addRetransmit(tcp, p);
                    requeued++;
                } else {
                    freed++;
                }
                packet_unref(p);
            }
            while (!g_queue_is_empty(&keep)) {
                priorityqueue_push(tcp->throttledOutput, g_queue_pop_head(&keep));
            }
            retransmit_tally_undo(tcp->retransmit.tally, (const uint32_t*)unsent->data, unsent->len);
            g_array_free(unsent, TRUE);
            tcp->diag.undone++;
            tcp->diag.dropped += dropped;
            tcp->undo.watch = TRUE;
            tcp->undo.watchHigh = tcp->undo.seqHigh;
            /* the ACK processing above stopped the retransmit timer if the retransmit queue was empty at that point;
             * the requeued packets are outstanding again, so they need a running timer */
            if (tcp->retransmit.queueLength > 0 && tcp->retransmit.desiredTimerExpiration == 0) {
                _tcp_setRetransmitTimer(tcp, host, worker_getCurrentSimulationTime());
                rearmed = 1;
            }
        }
        if (_tcp_diagLog()) {
            info("tcpd undo %p spurious %d retxtime %d cwnd %u -> %u ssthresh %u -> %u saved %u dropped %u requeued %u "
                 "freed %u rearm %d", (void*)tcp, (int)spurious, (int)tcp->undo.haveRetxTime, cw0, tcp->cong.cwnd, ss0,
                 tcp->cong.hooks->tcp_cong_ssthresh(tcp), tcp->undo.saved.cwnd, dropped, requeued, freed, rearmed);
        }
    }
"""),
    # acked-after-timeout expectation follows the active estimator
    ("""                 tcp->timing.rttVariance, tcp->retransmit.timeout,
                 tcp->timing.rttSmoothed + MAX(4 * tcp->timing.rttVariance, CONFIG_TCP_RTO_MIN));""",
     """                 tcp->timing.rttVariance, tcp->retransmit.timeout,
                 _tcp_rtt2LinuxEst() ? _tcp_rtt2RTO(tcp)
                                     : tcp->timing.rttSmoothed + MAX(4 * tcp->timing.rttVariance, CONFIG_TCP_RTO_MIN));"""),
    # snapshot: append ssthresh, the Linux estimator state and the rtt2 counters
    ("""                 \" txdata %\" G_GUINT64_FORMAT \" cfgrtt %u sndbuf %\" G_GSIZE_FORMAT \" rcvbuf %\" G_GSIZE_FORMAT \" cwnd %u\",""",
     """                 \" txdata %\" G_GUINT64_FORMAT \" cfgrtt %u sndbuf %\" G_GSIZE_FORMAT \" rcvbuf %\" G_GSIZE_FORMAT \" cwnd %u\"
                 \" ssthresh %u est %d srtt8us %\" G_GINT64_FORMAT \" mdevus %\" G_GINT64_FORMAT \" mdevmaxus %\" G_GINT64_FORMAT
                 \" rttvarus %\" G_GINT64_FORMAT \" txretx %\" G_GUINT64_FORMAT \" undochecks %\" G_GUINT64_FORMAT
                 \" undone %\" G_GUINT64_FORMAT \" dropped %\" G_GUINT64_FORMAT \" retxafterundo %\" G_GUINT64_FORMAT
                 \" rtxq %\" G_GSIZE_FORMAT \" thr %\" G_GSIZE_FORMAT \" tmr %d\","""),
    ("""                 legacysocket_getInputBufferSize(&(tcp->super)), (unsigned)tcp->cong.cwnd);""",
     """                 legacysocket_getInputBufferSize(&(tcp->super)), (unsigned)tcp->cong.cwnd,
                 (unsigned)tcp->cong.hooks->tcp_cong_ssthresh(tcp), _tcp_rtt2LinuxEst(), tcp->est.srtt8, tcp->est.mdev,
                 tcp->est.mdevMax, tcp->est.rttvar, tcp->diag.txRetx, tcp->diag.undoChecks, tcp->diag.undone,
                 tcp->diag.dropped, tcp->diag.retxAfterUndo, tcp->retransmit.queueLength, tcp->throttledOutputLength,
                 (int)(tcp->retransmit.desiredTimerExpiration != 0));"""),
])
