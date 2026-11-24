#!/usr/bin/env python3
"""rtt5 = rtt4 + two Linux congestion-window rules, each behind its own switch (sensitivity build):
- RTT5_CWV (window validation, net/ipv4/tcp_output.c tcp_cwnd_validate and include/net/tcp.h tcp_is_cwnd_limited):
  after each flush the sender records whether the window was cwnd-limited (packets out >= cwnd) or else the most
  packets out in the current window (cwnd_usage_seq bookkeeping); an ACK raises cwnd in slow start or congestion
  avoidance only while tcp_is_cwnd_limited holds: the last window was cwnd-limited, or (slow start) cwnd is below
  2 x max_packets_out. Packets out = sent and not cumulatively acknowledged, in sequence space as Shadow's own window
  check counts them. Fast recovery is not gated (Linux uses PRR there); the ACK that ends it raises cwnd only under
  the same rule. RFC 2861's slow part (tcp_cwnd_application_limited) is not included.
- RTT5_SSR (restart after idle, tcp_slow_start_after_idle_check and tcp_cwnd_restart, tcp_slow_start_after_idle = 1):
  when a new data segment goes out with nothing in flight and more than one RTO since the last data segment,
  ssthresh = tcp_current_ssthresh (unchanged in fast recovery, else at least 3/4 of cwnd) and cwnd is halved once
  per RTO of idle time, but not below min(10, cwnd); a cwnd below ssthresh puts Reno in slow start.
Both default on; RTT5_CWV=0 and RTT5_SSR=0 in Shadow's environment restore rtt4.
Diagnostics (LNXBUF_LOG): 'tcpd ssr' lines (idle and RTO in ms, cwnd and ssthresh before and after each restart);
snapshot fields cwvskip (ACKs whose cwnd increase the rule skipped), ssr (restarts), cwndlim, maxout.
Usage: rtt5_patch.py SHADOW_SRC_DIR (a copy of the rtt4 source)"""
import sys

d = sys.argv[1] + '/src/main/host/descriptor/'


def sub(path, old, new):
    s = open(d + path).read()
    assert s.count(old) == 1, (path, old[:60], s.count(old))
    open(d + path, 'w').write(s.replace(old, new))


SW = '''/* rtt5 switches: RTT5_CWV=0 turns off Linux's window validation, RTT5_SSR=0 its restart after idle; both off = rtt4 */
static int _tcp_rtt5Switch(const char* name, int* on) {
    if (*on < 0) {
        const char* v = getenv(name);
        *on = !(v && strcmp(v, "0") == 0);
    }
    return *on;
}
static int _tcp_rtt5Cwv(void) {
    static int on = -1;
    return _tcp_rtt5Switch("RTT5_CWV", &on);
}
static int _tcp_rtt5Ssr(void) {
    static int on = -1;
    return _tcp_rtt5Switch("RTT5_SSR", &on);
}

'''
sub('tcp.c', 'static int _tcp_diagLog(void) {\n', SW + 'static int _tcp_diagLog(void) {\n')

sub('tcp.c', '    } diag;\n',
    '    } diag;\n\n'
    '    /* rtt5: Linux window validation (tcp_cwnd_validate) and restart after idle (tcp_cwnd_restart) */\n'
    '    struct {\n'
    '        gboolean isCwndLimited;\n'
    '        guint32 maxPacketsOut;\n'
    '        guint32 cwndUsageSeq;\n'
    '        guint64 cwvSkipped;\n'
    '        guint64 restarts;\n'
    '    } rtt5;\n')

FN = '''/* rtt5: Linux's tcp_is_cwnd_limited, asked by Reno before it raises cwnd on an ACK (tcp_reno_cong_avoid) */
gboolean tcp_rtt5MayRaiseCwnd(TCP* tcp, gboolean slowStart) {
    MAGIC_ASSERT(tcp);
    if (!_tcp_rtt5Cwv() || tcp->rtt5.isCwndLimited ||
        (slowStart && tcp->cong.cwnd < 2 * tcp->rtt5.maxPacketsOut)) {
        return TRUE;
    }
    tcp->rtt5.cwvSkipped++;
    return FALSE;
}

/* rtt5: Linux's tcp_cwnd_restart after an idle period of more than one RTO */
static void _tcp_rtt5Restart(TCP* tcp, gint64 idle, gint64 rto) {
    guint32 before = tcp->cong.cwnd;
    guint32 ssBefore = tcp->cong.hooks->tcp_cong_ssthresh(tcp);
    guint32 cwnd = before;
    guint32 restart = MIN((guint32)10, before);
    gint64 delta = idle;
    while ((delta -= rto) > 0 && cwnd > restart) {
        cwnd >>= 1;
    }
    cwnd = MAX(cwnd, restart);
    tcp_cong_reno_restart(tcp, cwnd);
    tcp->rtt5.restarts++;
    if (_tcp_diagLog()) {
        info("tcpd ssr %p idle %" G_GINT64_FORMAT " rto %" G_GINT64_FORMAT " cwnd %u %u ssthresh %u %u", (void*)tcp,
             idle / SIMTIME_ONE_MILLISECOND, rto / SIMTIME_ONE_MILLISECOND, before, (unsigned)tcp->cong.cwnd,
             ssBefore, (unsigned)tcp->cong.hooks->tcp_cong_ssthresh(tcp));
    }
}

'''
sub('tcp.c', 'static void _tcp_flush(TCP* tcp, const Host* host) {\n', FN + 'static void _tcp_flush(TCP* tcp, const Host* host) {\n')

sub('tcp.c', '    /* flush packets that can now be sent to socket */\n    while(!priorityqueue_isEmpty(tcp->throttledOutput)) {\n',
    '    /* rtt5: new data segments sent in this flush (Linux sent_pkts in tcp_write_xmit) */\n'
    '    guint32 rtt5High = tcp->send.highestSequence;\n'
    '    guint rtt5Sent = 0;\n\n'
    '    /* flush packets that can now be sent to socket */\n    while(!priorityqueue_isEmpty(tcp->throttledOutput)) {\n')

sub('tcp.c', '            /* we cant send it if our window is too small */\n',
    '            /* rtt5: restart after idle: a new data segment with nothing in flight, more than one RTO after the\n'
    '             * last data segment (tcp_slow_start_after_idle_check, tcp_cwnd_restart) */\n'
    '            if (_tcp_rtt5Ssr() && header.sequence > tcp->send.highestSequence && tcp->info.lastDataSent > 0 &&\n'
    '                (guint32)(tcp->send.highestSequence + 1) == tcp->send.unacked) {\n'
    '                gint64 rtt5Idle = (gint64)(now - tcp->info.lastDataSent);\n'
    '                gint64 rtt5Rto = (gint64)tcp->retransmit.timeout * SIMTIME_ONE_MILLISECOND;\n'
    '                if (rtt5Idle > rtt5Rto) {\n'
    '                    _tcp_rtt5Restart(tcp, rtt5Idle, rtt5Rto);\n'
    '                    _tcp_updateSendWindow(tcp);\n'
    '                }\n'
    '            }\n\n'
    '            /* we cant send it if our window is too small */\n')

sub('tcp.c', '                /* we will send the data packet */\n                tcp->info.lastDataSent = now;\n',
    '                /* we will send the data packet */\n                tcp->info.lastDataSent = now;\n'
    '                if (header.sequence > rtt5High) {\n'
    '                    rtt5Sent++;\n'
    '                }\n')

sub('tcp.c', '        /* we already checked for space, so this should always succeed */\n        utility_debugAssert(success);\n    }\n',
    '        /* we already checked for space, so this should always succeed */\n        utility_debugAssert(success);\n    }\n\n'
    '    /* rtt5: Linux tcp_cwnd_validate after tcp_write_xmit: remember whether this window was cwnd-limited, or else\n'
    '     * the most packets out in it (sent and not cumulatively acknowledged, in sequence space) */\n'
    '    if (_tcp_rtt5Cwv()) {\n'
    '        guint32 rtt5Next = (guint32)(tcp->send.highestSequence + 1);\n'
    '        guint32 rtt5Out = (gint32)(rtt5Next - tcp->send.unacked) > 0 ? rtt5Next - tcp->send.unacked : 0;\n'
    '        gboolean rtt5Limited = rtt5Out >= tcp->cong.cwnd;\n'
    '        if ((rtt5Sent > 0 || rtt5Limited) &&\n'
    '            ((gint32)(tcp->send.unacked - tcp->rtt5.cwndUsageSeq) >= 0 || rtt5Limited ||\n'
    '             (!tcp->rtt5.isCwndLimited && rtt5Out > tcp->rtt5.maxPacketsOut))) {\n'
    '            tcp->rtt5.isCwndLimited = rtt5Limited;\n'
    '            tcp->rtt5.maxPacketsOut = rtt5Out;\n'
    '            tcp->rtt5.cwndUsageSeq = rtt5Next;\n'
    '        }\n'
    '    }\n')

sub('tcp.c', '                 " tsdupold %" G_GUINT64_FORMAT,\n',
    '                 " tsdupold %" G_GUINT64_FORMAT " cwvskip %" G_GUINT64_FORMAT " ssr %" G_GUINT64_FORMAT\n'
    '                 " cwndlim %d maxout %u",\n')
sub('tcp.c', 'tcp->diag.tsDupOld);',
    'tcp->diag.tsDupOld, tcp->rtt5.cwvSkipped, tcp->rtt5.restarts,\n'
    '                 (int)tcp->rtt5.isCwndLimited, (unsigned)tcp->rtt5.maxPacketsOut);')

sub('tcp.h', 'void tcp_networkInterfaceIsAboutToSendPacket(TCP* tcp, const Host* host, Packet* packet);\n',
    'void tcp_networkInterfaceIsAboutToSendPacket(TCP* tcp, const Host* host, Packet* packet);\n'
    '/* rtt5: Linux tcp_is_cwnd_limited (TRUE when RTT5_CWV=0) */\n'
    'gboolean tcp_rtt5MayRaiseCwnd(TCP* tcp, gboolean slowStart);\n')

sub('tcp_cong_reno.h', 'void tcp_cong_reno_undo(TCP *tcp, const TCPCongRenoSaved *saved);\n',
    'void tcp_cong_reno_undo(TCP *tcp, const TCPCongRenoSaved *saved);\n'
    '/* rtt5: restart after idle (Linux tcp_cwnd_restart): ssthresh = tcp_current_ssthresh, then cwnd */\n'
    'void tcp_cong_reno_restart(TCP *tcp, guint32 cwnd);\n')

sub('tcp_cong_reno.c', '''static void tcp_cong_reno_new_ack_ev_(TCP *tcp, guint32 n) {
    CAReno *reno = tcp_cong(tcp)->ca;
    reno->state_hooks->tcp_cong_new_ack_ev(tcp, n);
}
''', '''static void tcp_cong_reno_new_ack_ev_(TCP *tcp, guint32 n) {
    CAReno *reno = tcp_cong(tcp)->ca;
    /* rtt5: like Linux's tcp_reno_cong_avoid, raise cwnd in slow start and congestion avoidance only while
     * tcp_is_cwnd_limited; slow start's duplicate ACK reset still runs */
    if (reno->state_hooks != fast_recovery_hooks_() &&
        !tcp_rtt5MayRaiseCwnd(tcp, reno->state_hooks == slow_start_hooks_())) {
        if (reno->state_hooks == slow_start_hooks_()) {
            reno->duplicate_ack_n = 0;
        }
        return;
    }
    reno->state_hooks->tcp_cong_new_ack_ev(tcp, n);
}
''')

sub('tcp_cong_reno.c', '''    reno->duplicate_ack_n = 0;
    tcp_cong(tcp)->cwnd = reno->ssthresh;

    transition_to_cong_avoid(tcp, reno, n);
}
''', '''    reno->duplicate_ack_n = 0;
    tcp_cong(tcp)->cwnd = reno->ssthresh;

    /* rtt5: the ACK that ends recovery raises cwnd only while tcp_is_cwnd_limited */
    transition_to_cong_avoid(tcp, reno, tcp_rtt5MayRaiseCwnd(tcp, FALSE) ? n : 0);
}
''')

sub('tcp_cong_reno.c', 'void tcp_cong_reno_init(TCP *tcp) {\n', '''/* rtt5: Linux tcp_cwnd_restart: ssthresh = tcp_current_ssthresh (unchanged in recovery, else at least 3/4 of the
 * old cwnd), then the caller's cwnd; a cwnd below ssthresh means slow start (tcp_in_slow_start) */
void tcp_cong_reno_restart(TCP *tcp, guint32 cwnd) {
    CAReno *reno = tcp_cong(tcp)->ca;
    if (reno->state_hooks != fast_recovery_hooks_()) {
        guint32 old = tcp_cong(tcp)->cwnd;
        reno->ssthresh = MAX(reno->ssthresh, (old >> 1) + (old >> 2));
    }
    tcp_cong(tcp)->cwnd = cwnd;
    if (reno->state_hooks == cong_avoid_hooks_() && cwnd < reno->ssthresh) {
        reno->state_hooks = slow_start_hooks_();
    }
}

void tcp_cong_reno_init(TCP *tcp) {
''')
print('rtt5 patch applied')
