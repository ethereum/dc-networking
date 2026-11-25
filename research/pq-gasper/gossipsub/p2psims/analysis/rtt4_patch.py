#!/usr/bin/env python3
"""rtt4 = rtt3 + the RFC 7323 section 4.3 / Linux echo rule (tcp_replace_ts_recent, net/ipv4/tcp_input.c): the receiver
takes a segment's TSval as the value to echo only if the segment's sequence is at or below the ACK number of the last
packet that departed (rcv_wup) and its TSval is not older than the current value (PAWS). Shadow's pure ACKs carry
sequence 0, so their TSval counts only when nothing received is still unacknowledged (receive.next <= that ACK number,
Linux's fast-path condition rcv_nxt == rcv_wup). TSecr is still written when a packet departs, so an ACK that waits in
the upload queue echoes the first segment it newly acknowledges instead of the newest one that arrived meanwhile.
RTT4_ECHO=0 in Shadow's environment restores rtt3's rule (every processed packet sets the value to echo).
Diagnostics (LNXBUF_LOG), cumulative per connection in the 'tcpd snap' lines: echoeq / echonew / echoold count the ACKs
of new data whose TSecr equals / is newer than / is older than the TSval of the latest transmission of the first
segment they newly acknowledge; echona those whose first segment is not in the retransmit queue (a resend of it waits
to leave); echozero those with TSecr 0. tsduppend and tsdupold count echo updates by a duplicate data segment:
tsduppend at the last departed ACK number (its first copy arrived after the last departure; Linux updates there too),
tsdupold entirely below it (Linux's tcp_sequence discards such a segment before tcp_replace_ts_recent).
Usage: rtt4_patch.py SHADOW_SRC_DIR (a copy of the rtt3 source)"""
import sys

d = sys.argv[1] + '/src/main/host/descriptor/'


def sub(path, old, new):
    s = open(d + path).read()
    assert s.count(old) == 1, (path, old[:60], s.count(old))
    open(d + path, 'w').write(s.replace(old, new))


sub('tcp.c', 'static int _tcp_diagLog(void) {\n',
    '/* rtt4 switch: RTT4_ECHO=0 restores rtt3\'s echo rule (every processed packet sets the value to echo) */\n'
    'static int _tcp_rtt4Echo(void) {\n'
    '    static int on = -1;\n'
    '    if (on < 0) {\n'
    '        const char* v = getenv("RTT4_ECHO");\n'
    '        on = !(v && strcmp(v, "0") == 0);\n'
    '    }\n'
    '    return on;\n'
    '}\n\n'
    'static int _tcp_diagLog(void) {\n')

sub('tcp.c', '        guint32 maxDeparted;\n        gboolean departedAny;\n',
    '        guint32 maxDeparted;\n        gboolean departedAny;\n'
    '        guint64 echoEq;\n        guint64 echoNew;\n        guint64 echoOld;\n        guint64 echoNA;\n'
    '        guint64 echoZero;\n        guint64 tsDupPending;\n        guint64 tsDupOld;\n')

sub('tcp.c', '''    if(isValidAck) {
        /* the packets just acked''', '''    if(isValidAck) {
        /* rtt4 diagnostics: compare the echo with the TSval of the first segment this ACK newly acknowledges (the
         * lowest unacknowledged one; in the retransmit queue with its latest departure TSval, unless a resend of it is
         * waiting to leave) */
        if (_tcp_diagLog()) {
            Packet* firstAcked = g_hash_table_lookup(tcp->retransmit.queue, GINT_TO_POINTER(tcp->send.unacked));
            if (header->timestampEcho == 0) {
                tcp->diag.echoZero++;
            } else if (firstAcked == NULL) {
                tcp->diag.echoNA++;
            } else {
                CSimulationTime firstTsval = packet_getTCPHeader(firstAcked).timestampValue;
                if (header->timestampEcho == firstTsval) {
                    tcp->diag.echoEq++;
                } else if (header->timestampEcho > firstTsval) {
                    tcp->diag.echoNew++;
                } else {
                    tcp->diag.echoOld++;
                }
            }
        }
        /* the packets just acked''')

sub('tcp.c', '''    tcp->receive.lastTimestamp = header->timestampValue;
''', '''    if (!_tcp_rtt4Echo()) {
        tcp->receive.lastTimestamp = header->timestampValue;
    } else {
        /* rtt4: RFC 7323 section 4.3 (Linux tcp_replace_ts_recent): only a segment at or below the ACK number of the
         * last departed packet (rcv_wup), with a TSval not older than the current value (PAWS); pure ACKs (sequence 0
         * here) only when nothing received is unacknowledged (Linux's fast path: rcv_nxt == rcv_wup) */
        gboolean tsInSeq = header->sequence > 0
                               ? ((guint32)header->sequence <= tcp->send.lastAcknowledgment)
                               : (tcp->receive.next <= tcp->send.lastAcknowledgment);
        if (tsInSeq && header->timestampValue >= tcp->receive.lastTimestamp) {
            if (packetLength > 0 && header->sequence > 0 && !(flags & TCP_PF_DATA_RECEIVED) &&
                (guint32)header->sequence < tcp->receive.next) {
                /* diagnostics: an update by a duplicate segment; Linux makes it at the last departed ACK number
                 * (tsDupPending) but discards a segment entirely below it in tcp_sequence first (tsDupOld) */
                if ((guint32)header->sequence >= tcp->send.lastAcknowledgment) {
                    tcp->diag.tsDupPending++;
                } else if ((guint32)header->sequence + 1 < tcp->send.lastAcknowledgment) {
                    tcp->diag.tsDupOld++;
                }
            }
            tcp->receive.lastTimestamp = header->timestampValue;
        }
    }
''')

sub('tcp.c', '" tmr %d",', '" tmr %d echoeq %" G_GUINT64_FORMAT " echonew %" G_GUINT64_FORMAT " echoold %" G_GUINT64_FORMAT\n'
    '                 " echona %" G_GUINT64_FORMAT " echozero %" G_GUINT64_FORMAT " tsduppend %" G_GUINT64_FORMAT\n'
    '                 " tsdupold %" G_GUINT64_FORMAT,')
sub('tcp.c', '(int)(tcp->retransmit.desiredTimerExpiration != 0));',
    '(int)(tcp->retransmit.desiredTimerExpiration != 0), tcp->diag.echoEq, tcp->diag.echoNew,\n'
    '                 tcp->diag.echoOld, tcp->diag.echoNA, tcp->diag.echoZero, tcp->diag.tsDupPending,\n'
    '                 tcp->diag.tsDupOld);')
print('rtt4 patch applied to', sys.argv[1])
