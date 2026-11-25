#!/usr/bin/env python3
"""rtt3 = rtt2 + Linux's post-RTO window: after a retransmission timeout marks the outstanding data lost, cwnd =
packets in flight + 1 (tcp_enter_loss in net/ipv4/tcp_input.c) instead of Reno's fixed 10 segments.
RTT3_CWND=10 in Shadow's environment restores rtt2's window. Diagnostics (LNXBUF_LOG): "tcpd rto3" at each timeout
(in-flight count, cwnd after) and "tcpd recovered" when every packet outstanding at the RTOs of a recovery is acked
(duration since the first RTO, resends of that data, Eifel verdict). Usage: rtt3_patch.py SHADOW_SRC_DIR"""
import sys

d = sys.argv[1] + '/src/main/host/descriptor/'


def sub(path, old, new):
    s = open(d + path).read()
    assert s.count(old) == 1, (path, old[:60], s.count(old))
    open(d + path, 'w').write(s.replace(old, new))


sub('tcp_retransmit_tally.h', 'size_t retransmit_tally_num_lost_ranges(const void *p);\n',
    'size_t retransmit_tally_num_lost_ranges(const void *p);\n'
    '/* rtt3: packets in flight in [begin, end) as Linux counts them (packets_out - sacked_out - lost_out + retrans_out):\n'
    ' * not SACKed, and not marked lost or marked lost and retransmitted */\n'
    'uint32_t retransmit_tally_count_in_flight(const void *p, uint32_t begin, uint32_t end);\n')

sub('tcp_retransmit_tally.cc', 'void retransmit_tally_populate_lost_ranges(const void *p, uint32_t *lost) {\n',
    'uint32_t retransmit_tally_count_in_flight(const void *p, uint32_t begin, uint32_t end) {\n'
    '   auto rt = cast_and_assert(p);\n'
    '   if (begin >= end) { return 0; }\n'
    '   Ranges out{SeqRange{static_cast<SeqNum>(begin), static_cast<SeqNum>(end)}};\n'
    '   out = ranges_subtract(out, rt->sacked_);\n'
    '   out = ranges_subtract(out, rt->lost_); // lost_ = marked lost - SACKed - retransmitted\n'
    '   SeqNum n = 0;\n'
    '   for (const auto &range : out) { n += range.second - range.first; }\n'
    '   return static_cast<uint32_t>(n);\n'
    '}\n\n'
    'void retransmit_tally_populate_lost_ranges(const void *p, uint32_t *lost) {\n')

sub('tcp.c', 'static int _tcp_diagLog(void) {\n',
    '/* rtt3 switch: RTT3_CWND=10 restores rtt2\'s post-RTO window (Reno\'s fixed 10 segments) */\n'
    'static int _tcp_rtt3Cwnd(void) {\n'
    '    static int on = -1;\n'
    '    if (on < 0) {\n'
    '        const char* v = getenv("RTT3_CWND");\n'
    '        on = !(v && strcmp(v, "10") == 0);\n'
    '    }\n'
    '    return on;\n'
    '}\n\n'
    'static int _tcp_diagLog(void) {\n')

sub('tcp.c', '        gboolean watch;\n        guint32 watchHigh;\n    } undo;\n',
    '        gboolean watch;\n        guint32 watchHigh;\n    } undo;\n\n'
    '    /* rtt3 diagnostics: a recovery runs from an RTO until every packet outstanding at any of its RTOs is acked\n'
    '     * (Linux leaves the Loss state once snd_una reaches high_seq) */\n'
    '    struct {\n'
    '        gboolean active;\n'
    '        CSimulationTime start;\n'
    '        guint32 high;\n'
    '        guint32 outstanding;\n'
    '        guint32 timeouts;\n'
    '        guint32 episodes;\n'
    '        guint32 retx;\n'
    '        gint spurious;\n'
    '    } rec;\n')

sub('tcp.c', '''    _rswlog(tcp, "Timeout, marking %d as lost.\\n", tcp->receive.lastAcknowledgment);
''', '''    /* rtt3: Linux's post-RTO window (tcp_enter_loss in net/ipv4/tcp_input.c): cwnd = packets in flight + 1, counted
     * after the outstanding data is marked lost, instead of the fixed 10 segments of tcp_cong_reno_timeout_ev_ */
    guint32 rtt3InFlight = retransmit_tally_count_in_flight(tcp->retransmit.tally, tcp->receive.lastAcknowledgment,
                                                            tcp->send.highestSequence + 1);
    guint32 rtt3RenoCwnd = tcp->cong.cwnd;
    if (_tcp_rtt3Cwnd()) {
        tcp->cong.cwnd = rtt3InFlight + 1;
    }
    gboolean rtt3NewWatch = !tcp->rec.active;
    if (rtt3NewWatch) {
        tcp->rec.active = TRUE;
        tcp->rec.start = now;
        tcp->rec.high = tcp->send.highestSequence;
        tcp->rec.outstanding = tcp->send.highestSequence + 1 - tcp->receive.lastAcknowledgment;
        tcp->rec.timeouts = 0;
        tcp->rec.episodes = 0;
        tcp->rec.retx = 0;
        tcp->rec.spurious = -1;
    } else {
        tcp->rec.high = MAX(tcp->rec.high, tcp->send.highestSequence);
    }
    tcp->rec.timeouts++;
    if (tcp->retransmit.backoffCount == 1) {
        tcp->rec.episodes++;
    }
    if (_tcp_diagLog()) {
        info("tcpd rto3 %p inflight %u cwnd %u reno %u ssthresh %u outstanding %u backoff %u newwatch %d", (void*)tcp,
             rtt3InFlight, tcp->cong.cwnd, rtt3RenoCwnd, tcp->cong.hooks->tcp_cong_ssthresh(tcp),
             tcp->send.highestSequence + 1 - tcp->receive.lastAcknowledgment, tcp->retransmit.backoffCount,
             (int)rtt3NewWatch);
    }

    _rswlog(tcp, "Timeout, marking %d as lost.\\n", tcp->receive.lastAcknowledgment);
''')

sub('tcp.c', '''            tcp->diag.txRetx++;
''', '''            tcp->diag.txRetx++;
            if (tcp->rec.active && (guint32)header.sequence <= tcp->rec.high) {
                tcp->rec.retx++;
            }
''')

sub('tcp.c', '''                            (header->timestampEcho != 0 && header->timestampEcho < tcp->undo.retxTime);
''', '''                            (header->timestampEcho != 0 && header->timestampEcho < tcp->undo.retxTime);
        if (tcp->rec.active && tcp->rec.spurious < 0) {
            tcp->rec.spurious = spurious ? 1 : 0;
        }
''')

sub('tcp.c', '''    if (_tcp_diagLog()) {
        gint64 diagMs''', '''    if (tcp->rec.active && (flags & TCP_PF_DATA_ACKED) && tcp->send.unacked > tcp->rec.high) {
        tcp->rec.active = FALSE;
        if (_tcp_diagLog()) {
            info("tcpd recovered %p spurious %d dur %" G_GUINT64_FORMAT " timeouts %u episodes %u resends %u outstanding %u"
                 " cwnd %u ssthresh %u", (void*)tcp, tcp->rec.spurious,
                 (guint64)((worker_getCurrentSimulationTime() - tcp->rec.start) / SIMTIME_ONE_MICROSECOND),
                 tcp->rec.timeouts, tcp->rec.episodes, tcp->rec.retx, tcp->rec.outstanding, (unsigned)tcp->cong.cwnd,
                 (unsigned)tcp->cong.hooks->tcp_cong_ssthresh(tcp));
        }
    }
    if (_tcp_diagLog()) {
        gint64 diagMs''')
print('rtt3 patch applied to', sys.argv[1])
