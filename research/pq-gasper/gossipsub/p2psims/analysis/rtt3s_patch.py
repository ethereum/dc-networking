#!/usr/bin/env python3
"""rtt3s = rtt3 + Linux's ssthresh rule at a repeated RTO: tcp_enter_loss reduces ssthresh only at the first RTO of a
loss episode, not again while icsk_retransmits > 0 (no ACK of new data since the previous RTO). Shadow's Reno halves it
at every RTO (ssthresh = cwnd / 2 + 1), which with rtt3's post-RTO cwnd of 1 leaves ssthresh at 1 after a second RTO.
Usage: rtt3s_patch.py SHADOW_SRC_DIR (a copy of the rtt3 source)"""
import sys
d = sys.argv[1] + '/src/main/host/descriptor/'
def sub(path, old, new):
    s = open(d + path).read()
    assert s.count(old) == 1, (path, old[:60], s.count(old))
    open(d + path, 'w').write(s.replace(old, new))
sub('tcp_cong_reno.c', 'void tcp_cong_reno_init(TCP *tcp) {\n',
    '/* rtt3s: set ssthresh (keeps it across a repeated RTO, as Linux\'s tcp_enter_loss does) */\n'
    'void tcp_cong_reno_set_ssthresh(TCP *tcp, guint32 ssthresh) {\n'
    '    CAReno *reno = tcp_cong(tcp)->ca;\n'
    '    reno->ssthresh = ssthresh;\n'
    '}\n\n'
    'void tcp_cong_reno_init(TCP *tcp) {\n')
h = open(d + 'tcp_cong_reno.h').read()
anchor = 'void tcp_cong_reno_undo('
assert h.count(anchor) == 1
i = h.index(anchor)
open(d + 'tcp_cong_reno.h', 'w').write(h[:i] + 'void tcp_cong_reno_set_ssthresh(TCP *tcp, guint32 ssthresh);\n' + h[i:])
sub('tcp.c', '''    tcp->cong.hooks->tcp_cong_timeout_ev(tcp);
''', '''    guint32 rtt3sSsthresh = tcp->cong.hooks->tcp_cong_ssthresh(tcp);
    tcp->cong.hooks->tcp_cong_timeout_ev(tcp);
    /* rtt3s: Linux reduces ssthresh only at the first RTO of a loss episode (tcp_enter_loss, net/ipv4/tcp_input.c:
     * not again in the Loss state while icsk_retransmits > 0, which an ACK of new data resets, as it resets
     * backoffCount here) */
    if (tcp->retransmit.backoffCount > 1) {
        tcp_cong_reno_set_ssthresh(tcp, rtt3sSsthresh);
    }
''')
print('rtt3s patch applied to', sys.argv[1])
