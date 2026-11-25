#!/usr/bin/env python3
"""rtt6 = rtt5b + Linux CUBIC (net/ipv4/tcp_cubic.c, v6.12) with HyStart, behind switches RTT6_CUBIC and RTT6_HYSTART
(both on unless set to 0; RTT6_CUBIC=0 reproduces rtt5b). Applies exact replacements to a copy of shadow-src-rtt5b.
usage: python3 -I rtt6_patch.py SRCDIR   (SRCDIR = shadow-src-rtt6)"""
import sys

D = sys.argv[1] + "/src/main/host/descriptor/"


def patch(name, reps):
    p = D + name
    s = open(p).read()
    for old, new in reps:
        n = s.count(old)
        if n != 1:
            sys.exit(f"{name}: anchor found {n} times: {old[:80]!r}")
        s = s.replace(old, new)
    open(p, "w").write(s)
    print(f"{name}: {len(reps)} replacements")


patch("tcp.h", [(
    "void tcp_rtt5LogFastRecovery(TCP* tcp, gboolean fromSlowStart, guint32 adv, guint32 cwndBefore, guint32 ssthreshBefore);\n",
    "void tcp_rtt5LogFastRecovery(TCP* tcp, gboolean fromSlowStart, guint32 adv, guint32 cwndBefore, guint32 ssthreshBefore);\n"
    "/* rtt6 switch RTT6_CUBIC (on unless RTT6_CUBIC=0): Linux CUBIC (net/ipv4/tcp_cubic.c, v6.12) for Reno's congestion\n"
    " * avoidance and multiplicative decrease; RTT6_HYSTART=0 turns CUBIC's HyStart off. RTT6_CUBIC=0 is rtt5b */\n"
    "gboolean tcp_rtt6Cubic(void);\n"
    "/* rtt6: cubictcp_recalc_ssthresh, at fast-recovery entry and at an RTO */\n"
    "guint32 tcp_rtt6CubicSsthresh(TCP* tcp, guint32 cwnd);\n"
    "/* rtt6: cubictcp_cong_avoid in congestion avoidance: bictcp_update, then tcp_cong_avoid_ai on *cwndCnt */\n"
    "void tcp_rtt6CubicCongAvoid(TCP* tcp, guint32 acked, guint32* cwndCnt);\n")])

patch("tcp_cong_reno.h", [(
    "char tcp_cong_reno_phase(TCP *tcp);\n",
    "char tcp_cong_reno_phase(TCP *tcp);\n"
    "/* rtt6: HyStart found the end of slow start: ssthresh = cwnd, congestion avoidance from this ACK on */\n"
    "void tcp_cong_reno_hystart_exit(TCP *tcp);\n")])

patch("tcp_cong_reno.c", [
    ("static inline void ssthresh_reduce(TCP *tcp, CAReno *reno) {\n    if (tcp_rtt5Beta()) {\n",
     "static inline void ssthresh_reduce(TCP *tcp, CAReno *reno) {\n"
     "    if (tcp_rtt6Cubic()) {\n"
     "        /* rtt6: cubictcp_recalc_ssthresh, which also ends CUBIC's epoch and records W_max (fast convergence) */\n"
     "        reno->ssthresh = tcp_rtt6CubicSsthresh(tcp, tcp_cong(tcp)->cwnd);\n"
     "    } else if (tcp_rtt5Beta()) {\n"),
    ("static void ca_reno_cong_avoid_new_ack_ev_(TCP *tcp, guint32 n) {\n    CAReno *reno = tcp_cong(tcp)->ca;\n\n",
     "static void ca_reno_cong_avoid_new_ack_ev_(TCP *tcp, guint32 n) {\n    CAReno *reno = tcp_cong(tcp)->ca;\n\n"
     "    /* rtt6: CUBIC's congestion avoidance, with Reno's ACK counter as Linux's snd_cwnd_cnt */\n"
     "    if (tcp_rtt6Cubic()) {\n"
     "        tcp_rtt6CubicCongAvoid(tcp, n, &reno->cong_avoid_nacked);\n"
     "        return;\n"
     "    }\n\n"),
    ("    return reno->state_hooks == fast_recovery_hooks_() ? 'f' : 'c';\n}\n",
     "    return reno->state_hooks == fast_recovery_hooks_() ? 'f' : 'c';\n}\n\n"
     "/* rtt6: HyStart (hystart_update) sets ssthresh = cwnd; Linux is then out of slow start (tcp_in_slow_start is\n"
     " * cwnd < ssthresh), so this ACK's increase already follows congestion avoidance and its RTT5_CWV gate */\n"
     "void tcp_cong_reno_hystart_exit(TCP *tcp) {\n"
     "    CAReno *reno = tcp_cong(tcp)->ca;\n"
     "    reno->ssthresh = tcp_cong(tcp)->cwnd;\n"
     "    if (reno->state_hooks == slow_start_hooks_()) {\n"
     "        reno->cong_avoid_nacked = 0;\n"
     "        reno->state_hooks = cong_avoid_hooks_();\n"
     "    }\n"
     "}\n"),
])

CUBIC_STRUCT = r"""
    /* rtt6: Linux CUBIC's state (struct bictcp in net/ipv4/tcp_cubic.c; times in jiffies = ms, HyStart's in us), kept
     * apart from Reno's so that the Eifel undo leaves it as the RTO's Loss reset left it, and diagnostics */
    struct {
        guint32 cnt;
        guint32 lastMaxCwnd;
        guint32 lastCwnd;
        guint32 lastTime;
        guint32 originPoint;
        guint32 K;
        guint32 delayMin;
        guint32 epochStart;
        guint32 ackCnt;
        guint32 tcpCwnd;
        guint8 sampleCnt;
        guint8 found;
        guint32 roundStart;
        guint32 endSeq;
        guint32 lastAck;
        guint32 currRtt;
        gboolean trace;
        guint32 rndEnd;
        guint32 rndCwnd;
        guint32 rndInc;
        guint32 rndAcked;
        guint32 rndMax;
        guint64 rounds;
        guint64 roundsOver;
        guint64 roundsOverAcked;
        guint64 hsTrain;
        guint64 hsDelay;
        guint64 epochs;
        guint64 txStart;
        guint64 txShift;
    } cubic;
"""

CUBIC_FUNCS = r"""
/* rtt6: Linux CUBIC (net/ipv4/tcp_cubic.c, v6.12) with HyStart, for Reno's congestion avoidance and multiplicative
 * decrease (Reno's slow start, fast recovery and RTO handling stay). Switches RTT6_CUBIC and RTT6_HYSTART, both on unless
 * set to 0; RTT6_CUBIC=0 is rtt5b. Jiffies are milliseconds (HZ = 1000). Module defaults: beta 717, bic_scale 41,
 * fast convergence, TCP friendliness, HyStart ack train and delay, low window 16, ack delta 2 ms */
static int _tcp_rtt6CubicOn(void) {
    static int on = -1;
    return _tcp_rtt5Switch("RTT6_CUBIC", &on);
}
static int _tcp_rtt6HystartOn(void) {
    static int on = -1;
    return _tcp_rtt5Switch("RTT6_HYSTART", &on);
}
gboolean tcp_rtt6Cubic(void) {
    return _tcp_rtt6CubicOn() ? TRUE : FALSE;
}

#define RTT6_HZ 1000U
#define RTT6_BICTCP_HZ 10
#define RTT6_BETA 717U
#define RTT6_BETA_SCALE 1024U
#define RTT6_CUBE_RTT_SCALE (41U * 10U)
#define RTT6_CUBE_FACTOR ((1ULL << (10 + 3 * RTT6_BICTCP_HZ)) / (41U * 10U))
#define RTT6_TCP_BETA_SCALE (8U * (RTT6_BETA_SCALE + RTT6_BETA) / 3U / (RTT6_BETA_SCALE - RTT6_BETA))
#define RTT6_HYSTART_LOW_WINDOW 16U
#define RTT6_HYSTART_ACK_DELTA_US 2000
#define RTT6_HYSTART_MIN_SAMPLES 8U
#define RTT6_HYSTART_DELAY_MIN 4000U
#define RTT6_HYSTART_DELAY_MAX 16000U

/* tcp_jiffies32 (offset by 1 so that 0 still means "no epoch") and bictcp_clock_us */
static guint32 _tcp_rtt6Jiffies(void) {
    return (guint32)(worker_getCurrentSimulationTime() / SIMTIME_ONE_MILLISECOND) + 1;
}
static guint32 _tcp_rtt6ClockUs(void) {
    return (guint32)(worker_getCurrentSimulationTime() / SIMTIME_ONE_MICROSECOND);
}

/* bictcp_reset: every field before 'unused' in struct bictcp, and found */
static void _tcp_rtt6Reset(TCP* tcp) {
    tcp->cubic.cnt = 0;
    tcp->cubic.lastMaxCwnd = 0;
    tcp->cubic.lastCwnd = 0;
    tcp->cubic.lastTime = 0;
    tcp->cubic.originPoint = 0;
    tcp->cubic.K = 0;
    tcp->cubic.delayMin = 0;
    tcp->cubic.epochStart = 0;
    tcp->cubic.ackCnt = 0;
    tcp->cubic.tcpCwnd = 0;
    tcp->cubic.found = 0;
}

/* bictcp_hystart_reset: a round starts at snd_nxt */
static void _tcp_rtt6HystartReset(TCP* tcp) {
    tcp->cubic.roundStart = tcp->cubic.lastAck = _tcp_rtt6ClockUs();
    tcp->cubic.endSeq = tcp->send.highestSequence + 1;
    tcp->cubic.currRtt = ~0U;
    tcp->cubic.sampleCnt = 0;
}

/* cubic_root: table lookup followed by one Newton-Raphson iteration */
static guint32 _tcp_rtt6CubicRoot(guint64 a) {
    static const guint8 v[] = {
        /* 0x00 */ 0,   54,  54,  54,  118, 118, 118, 118,
        /* 0x08 */ 123, 129, 134, 138, 143, 147, 151, 156,
        /* 0x10 */ 157, 161, 164, 168, 170, 173, 176, 179,
        /* 0x18 */ 181, 185, 187, 190, 192, 194, 197, 199,
        /* 0x20 */ 200, 202, 204, 206, 209, 211, 213, 215,
        /* 0x28 */ 217, 219, 221, 222, 224, 225, 227, 229,
        /* 0x30 */ 231, 232, 234, 236, 237, 239, 240, 242,
        /* 0x38 */ 244, 245, 246, 248, 250, 251, 252, 254,
    };
    guint32 x, b, shift;
    b = a ? (guint32)(64 - __builtin_clzll(a)) : 0; /* fls64 */
    if (b < 7) {
        /* a in [0..63] */
        return ((guint32)v[(guint32)a] + 35) >> 6;
    }
    b = ((b * 84) >> 8) - 1;
    shift = (guint32)(a >> (b * 3));
    x = ((guint32)(((guint32)v[shift] + 10) << b)) >> 6;
    x = (2 * x + (guint32)(a / ((guint64)x * (guint64)(x - 1))));
    x = ((x * 341) >> 10);
    return x;
}

/* cubictcp_recalc_ssthresh */
guint32 tcp_rtt6CubicSsthresh(TCP* tcp, guint32 cwnd) {
    MAGIC_ASSERT(tcp);
    tcp->cubic.epochStart = 0; /* end of epoch */
    /* Wmax and fast convergence */
    if (cwnd < tcp->cubic.lastMaxCwnd) {
        tcp->cubic.lastMaxCwnd = (cwnd * (RTT6_BETA_SCALE + RTT6_BETA)) / (2 * RTT6_BETA_SCALE);
    } else {
        tcp->cubic.lastMaxCwnd = cwnd;
    }
    tcp->cubic.rndEnd = 0; /* diagnostics: no growth round across a loss */
    return MAX((cwnd * RTT6_BETA) / RTT6_BETA_SCALE, 2U);
}

/* bictcp_update: returns ca->cnt, the packets to ACK per one-segment increase */
static guint32 _tcp_rtt6Update(TCP* tcp, guint32 cwnd, guint32 acked) {
    guint32 now = _tcp_rtt6Jiffies();
    guint32 delta, bic_target = 0, max_cnt;
    guint64 offs, t = 0;
    gboolean full = FALSE;

    tcp->cubic.ackCnt += acked; /* count the number of ACKed packets */

    if (tcp->cubic.lastCwnd == cwnd && (gint32)(now - tcp->cubic.lastTime) <= (gint32)(RTT6_HZ / 32)) {
        return tcp->cubic.cnt;
    }

    /* The CUBIC function can update ca->cnt at most once per jiffy. On all cwnd reduction events, ca->epoch_start is
     * set to 0, which will force a recalculation of ca->cnt. */
    if (tcp->cubic.epochStart && now == tcp->cubic.lastTime) {
        goto tcp_friendliness;
    }

    tcp->cubic.lastCwnd = cwnd;
    tcp->cubic.lastTime = now;

    if (tcp->cubic.epochStart == 0) {
        tcp->cubic.epochStart = now; /* record beginning */
        tcp->cubic.ackCnt = acked;   /* start counting */
        tcp->cubic.tcpCwnd = cwnd;   /* syn with cubic */

        if (tcp->cubic.lastMaxCwnd <= cwnd) {
            tcp->cubic.K = 0;
            tcp->cubic.originPoint = cwnd;
        } else {
            /* Compute new K based on (wmax-cwnd) * (srtt>>3 / HZ) / c * 2^(3*bictcp_HZ) */
            tcp->cubic.K = _tcp_rtt6CubicRoot(RTT6_CUBE_FACTOR * (tcp->cubic.lastMaxCwnd - cwnd));
            tcp->cubic.originPoint = tcp->cubic.lastMaxCwnd;
        }
        tcp->cubic.epochs++;
        if (_tcp_diagLog()) {
            info("tcpd cubep %p cwnd %u lastmax %u K %u origin %u dmin %u", (void*)tcp, cwnd, tcp->cubic.lastMaxCwnd,
                 tcp->cubic.K, tcp->cubic.originPoint, tcp->cubic.delayMin);
        }
    }

    /* cubic function - calc */
    t = (guint64)(gint64)(gint32)(now - tcp->cubic.epochStart);
    t += (tcp->cubic.delayMin + 999U) / 1000U; /* usecs_to_jiffies(ca->delay_min) */
    /* change the unit from HZ to bictcp_HZ */
    t <<= RTT6_BICTCP_HZ;
    t /= RTT6_HZ;

    if (t < tcp->cubic.K) { /* t - K */
        offs = tcp->cubic.K - t;
    } else {
        offs = t - tcp->cubic.K;
    }

    /* c/rtt * (t-K)^3 */
    delta = (guint32)((RTT6_CUBE_RTT_SCALE * offs * offs * offs) >> (10 + 3 * RTT6_BICTCP_HZ));
    if (t < tcp->cubic.K) { /* below origin*/
        bic_target = tcp->cubic.originPoint - delta;
    } else { /* above origin*/
        bic_target = tcp->cubic.originPoint + delta;
    }

    /* cubic function - calc bictcp_cnt*/
    if (bic_target > cwnd) {
        tcp->cubic.cnt = cwnd / (bic_target - cwnd);
    } else {
        tcp->cubic.cnt = 100 * cwnd; /* very small increment*/
    }

    /* The initial growth of cubic function may be too conservative when the available bandwidth is still unknown. */
    if (tcp->cubic.lastMaxCwnd == 0 && tcp->cubic.cnt > 20) {
        tcp->cubic.cnt = 20; /* increase cwnd 5% per RTT */
    }
    full = TRUE;

tcp_friendliness:
    /* TCP Friendly */
    {
        guint32 scale = RTT6_TCP_BETA_SCALE;
        delta = (cwnd * scale) >> 3;
        while (tcp->cubic.ackCnt > delta) { /* update tcp cwnd */
            tcp->cubic.ackCnt -= delta;
            tcp->cubic.tcpCwnd++;
        }
        if (tcp->cubic.tcpCwnd > cwnd) { /* if bic is slower than tcp */
            delta = tcp->cubic.tcpCwnd - cwnd;
            max_cnt = cwnd / delta;
            if (tcp->cubic.cnt > max_cnt) {
                tcp->cubic.cnt = max_cnt;
            }
        }
    }

    /* The maximum rate of cwnd increase CUBIC allows is 1 packet per 2 packets ACKed, meaning cwnd grows at 1.5x per
     * RTT. */
    tcp->cubic.cnt = MAX(tcp->cubic.cnt, 2U);
    if (full && tcp->cubic.trace && _tcp_diagLog()) {
        info("tcpd cubtr %p now %u epoch %u t %" G_GUINT64_FORMAT " K %u origin %u target %u cwnd %u cnt %u tcpcwnd %u"
             " lastmax %u dmin %u", (void*)tcp, now, tcp->cubic.epochStart, t, tcp->cubic.K, tcp->cubic.originPoint,
             bic_target, cwnd, tcp->cubic.cnt, tcp->cubic.tcpCwnd, tcp->cubic.lastMaxCwnd, tcp->cubic.delayMin);
    }
    return tcp->cubic.cnt;
}

/* cubictcp_cong_avoid after Reno's slow start (Reno has already applied RTT5_CWV's tcp_is_cwnd_limited gate):
 * bictcp_update, then tcp_cong_avoid_ai(tp, ca->cnt, acked) (net/ipv4/tcp_cong.c) on Reno's ACK counter */
void tcp_rtt6CubicCongAvoid(TCP* tcp, guint32 acked, guint32* cwndCnt) {
    MAGIC_ASSERT(tcp);
    if (acked == 0) {
        return;
    }
    guint32 cwnd0 = tcp->cong.cwnd;
    /* diagnostics: congestion-avoidance growth per round trip (a round ends when snd_una passes the snd_nxt at its
     * start, as HyStart's rounds; losses, RTOs and restarts end a round uncounted) */
    if (tcp->cubic.rndEnd != 0 && (gint32)(tcp->send.unacked - tcp->cubic.rndEnd) > 0) {
        guint32 c0 = tcp->cubic.rndCwnd, inc = tcp->cubic.rndInc;
        tcp->cubic.rounds++;
        if (2 * inc > c0 + 2) {
            tcp->cubic.roundsOver++; /* more than 1.5 x the round's starting cwnd, plus one segment */
        }
        if (2 * inc > tcp->cubic.rndAcked + 2) {
            tcp->cubic.roundsOverAcked++; /* more than one segment per two packets ACKed, plus one */
        }
        tcp->cubic.rndMax = MAX(tcp->cubic.rndMax, (guint32)((1000ULL * (c0 + inc)) / MAX(c0, 1U)));
        if (tcp->cubic.trace && _tcp_diagLog()) {
            info("tcpd cubrnd %p cwnd %u inc %u acked %u", (void*)tcp, c0, inc, tcp->cubic.rndAcked);
        }
        tcp->cubic.rndEnd = 0;
    }
    if (tcp->cubic.rndEnd == 0) {
        tcp->cubic.rndEnd = tcp->send.highestSequence + 1;
        tcp->cubic.rndCwnd = cwnd0;
        tcp->cubic.rndInc = 0;
        tcp->cubic.rndAcked = 0;
    }

    guint32 w = _tcp_rtt6Update(tcp, cwnd0, acked);

    /* tcp_cong_avoid_ai: if credits accumulated at a higher w, apply them gently now */
    if (*cwndCnt >= w) {
        *cwndCnt = 0;
        tcp->cong.cwnd++;
    }
    *cwndCnt += acked;
    if (*cwndCnt >= w) {
        guint32 delta = *cwndCnt / w;
        *cwndCnt -= delta * w;
        tcp->cong.cwnd += delta;
    }
    tcp->cubic.rndInc += tcp->cong.cwnd - cwnd0;
    tcp->cubic.rndAcked += acked;
}

/* hystart_ack_delay with Linux's sk_pacing_rate, which tcp_update_pacing_rate sets after every ACK even without pacing:
 * 200 % (cwnd < ssthresh / 2) or 120 % of mss x max(cwnd, packets_out) / srtt; sk_gso_max_size 65,536 */
static guint32 _tcp_rtt6AckDelay(TCP* tcp) {
    guint32 cwnd = tcp->cong.cwnd, ssthresh = tcp->cong.hooks->tcp_cong_ssthresh(tcp);
    guint32 next = tcp->send.highestSequence + 1;
    guint32 out = (gint32)(next - tcp->send.unacked) > 0 ? next - tcp->send.unacked : 0;
    guint64 rate = (guint64)CONFIG_TCP_MAX_SEGMENT_SIZE * ((1000000ULL / 100) << 3);
    rate *= (cwnd < ssthresh / 2) ? 200 : 120;
    rate *= MAX(cwnd, out);
    if (tcp->est.srtt8 > 0) {
        rate /= (guint64)tcp->est.srtt8;
    }
    if (rate == 0) {
        return 0;
    }
    return (guint32)MIN((guint64)1000, (65536ULL * 4 * 1000000ULL) / rate);
}

static void _tcp_rtt6LogHystart(TCP* tcp, const char* test, guint32 threshold, guint32 ackDelay) {
    if (_tcp_diagLog()) {
        info("tcpd hys %p test %s cwnd %u ssthresh %u dmin %u curr %u thr %u rnd %u ackdelay %u samples %u", (void*)tcp,
             test, (unsigned)tcp->cong.cwnd, (unsigned)tcp->cong.hooks->tcp_cong_ssthresh(tcp), tcp->cubic.delayMin,
             tcp->cubic.currRtt, threshold, _tcp_rtt6ClockUs() - tcp->cubic.roundStart, ackDelay,
             (unsigned)tcp->cubic.sampleCnt);
    }
}

/* hystart_update */
static void _tcp_rtt6HystartUpdate(TCP* tcp, guint32 delay) {
    guint32 threshold;

    if ((gint32)(tcp->cubic.endSeq - tcp->send.unacked) < 0) { /* after(tp->snd_una, ca->end_seq) */
        _tcp_rtt6HystartReset(tcp);
    }

    /* first detection parameter - ack-train detection */
    guint32 now = _tcp_rtt6ClockUs();
    if ((gint32)(now - tcp->cubic.lastAck) <= RTT6_HYSTART_ACK_DELTA_US) {
        tcp->cubic.lastAck = now;
        guint32 ackDelay = _tcp_rtt6AckDelay(tcp);
        threshold = tcp->cubic.delayMin + ackDelay;
        /* Hystart ack train triggers if we get ack past ca->delay_min/2. Without pacing (SK_PACING_NONE) */
        threshold >>= 1;
        if ((guint32)(gint32)(now - tcp->cubic.roundStart) > threshold) {
            tcp->cubic.found = 1;
            tcp->cubic.hsTrain++;
            _tcp_rtt6LogHystart(tcp, "train", threshold, ackDelay);
            tcp_cong_reno_hystart_exit(tcp);
        }
    }

    /* obtain the minimum delay of more than sampling packets */
    if (tcp->cubic.currRtt > delay) {
        tcp->cubic.currRtt = delay;
    }
    if (tcp->cubic.sampleCnt < RTT6_HYSTART_MIN_SAMPLES) {
        tcp->cubic.sampleCnt++;
    } else {
        guint32 thr = tcp->cubic.delayMin +
                      CLAMP(tcp->cubic.delayMin >> 3, RTT6_HYSTART_DELAY_MIN, RTT6_HYSTART_DELAY_MAX);
        if (tcp->cubic.currRtt > thr) {
            tcp->cubic.found = 1;
            tcp->cubic.hsDelay++;
            _tcp_rtt6LogHystart(tcp, "delay", thr, 0);
            tcp_cong_reno_hystart_exit(tcp);
        }
    }
}

/* cubictcp_acked (pkts_acked), with the RTT estimator's sample (now - TSecr) in us */
static void _tcp_rtt6Acked(TCP* tcp, gint64 rttUs) {
    /* Discard delay samples right after fast recovery */
    if (tcp->cubic.epochStart && (gint32)(_tcp_rtt6Jiffies() - tcp->cubic.epochStart) < (gint32)RTT6_HZ) {
        return;
    }
    guint32 delay = (guint32)rttUs;
    if (delay == 0) {
        delay = 1;
    }
    /* first time call or link delay decreases */
    if (tcp->cubic.delayMin == 0 || tcp->cubic.delayMin > delay) {
        tcp->cubic.delayMin = delay;
    }
    /* hystart triggers when cwnd is larger than some threshold */
    guint32 cwnd = tcp->cong.cwnd;
    if (!tcp->cubic.found && cwnd < tcp->cong.hooks->tcp_cong_ssthresh(tcp) && _tcp_rtt6HystartOn() &&
        cwnd >= RTT6_HYSTART_LOW_WINDOW) {
        _tcp_rtt6HystartUpdate(tcp, delay);
    }
}

/* cubictcp_cwnd_event(CA_EVENT_TX_START): idle for a while, so shift epoch_start to keep cwnd growth on the cubic
 * curve; delta = now - lsndtime (the last data segment sent, new or resent) */
static void _tcp_rtt6TxStart(TCP* tcp, CSimulationTime now) {
    guint32 nowJ = (guint32)(now / SIMTIME_ONE_MILLISECOND) + 1;
    gint32 delta = (gint32)(nowJ - ((guint32)(tcp->info.lastDataSent / SIMTIME_ONE_MILLISECOND) + 1));
    tcp->cubic.txStart++;
    if (tcp->cubic.epochStart && delta > 0) {
        guint32 before = tcp->cubic.epochStart;
        tcp->cubic.epochStart += delta;
        if ((gint32)(nowJ - tcp->cubic.epochStart) < 0) { /* after(ca->epoch_start, now) */
            tcp->cubic.epochStart = nowJ;
        }
        tcp->cubic.txShift++;
        if (tcp->cubic.trace && _tcp_diagLog()) {
            info("tcpd txs %p delta %d epoch %u %u now %u", (void*)tcp, delta, before, tcp->cubic.epochStart, nowJ);
        }
    }
}
"""

INIT_FUNC = r"""/* rtt6: cubictcp_init when the connection is established (Linux calls it from tcp_init_transfer, after the handshake's
 * RTT sample, so the ACK of the SYN gives CUBIC no delay sample); 'tcpd cubtr' traces for about 1 in 128 connections,
 * chosen by address */
static void _tcp_rtt6Init(TCP* tcp, const Host* host) {
    _tcp_rtt6Reset(tcp);
    if (_tcp_rtt6HystartOn()) {
        _tcp_rtt6HystartReset(tcp);
    }
    guint32 h = (guint32)host_getDefaultIP(host) ^ ((guint32)tcp_getPeerIP(tcp) * 2654435761U);
    h ^= h >> 16;
    h *= 2246822507U;
    h ^= h >> 13;
    h *= 3266489909U;
    h ^= h >> 16;
    tcp->cubic.trace = (h % 128U) == 0;
}

static void _tcp_setState(TCP* tcp, const Host* host, enum TCPState state) {
"""

patch("tcp.c", [
    ("        guint64 tsDupOld;\n    } diag;\n",
     "        guint64 tsDupOld;\n"
     "        guint64 txFlushed; /* rtt6: data packets released by _tcp_flush, and those released with cwnd >= ssthresh */\n"
     "        guint64 txCa;\n    } diag;\n"),
    ("        guint64 restarts;\n    } rtt5;\n",
     "        guint64 restarts;\n    } rtt5;\n" + CUBIC_STRUCT),
    ("static int _tcp_diagLog(void) {\n    static int on = -1;\n    if (on < 0) {\n        on = getenv(\"LNXBUF_LOG\") != NULL;\n    }\n    return on;\n}\n",
     "static int _tcp_diagLog(void) {\n    static int on = -1;\n    if (on < 0) {\n        on = getenv(\"LNXBUF_LOG\") != NULL;\n    }\n    return on;\n}\n" + CUBIC_FUNCS),
    ("static void _tcp_setState(TCP* tcp, const Host* host, enum TCPState state) {\n", INIT_FUNC),
    ("            tcp->flags |= TCPF_WAS_ESTABLISHED;\n",
     "            tcp->flags |= TCPF_WAS_ESTABLISHED;\n"
     "            if (_tcp_rtt6CubicOn()) {\n"
     "                _tcp_rtt6Init(tcp, host);\n"
     "            }\n"),
    ("    tcp_cong_reno_restart(tcp, cwnd);\n    tcp->rtt5.restarts++;\n",
     "    tcp_cong_reno_restart(tcp, cwnd);\n    tcp->rtt5.restarts++;\n"
     "    tcp->cubic.rndEnd = 0; /* rtt6 diagnostics: no growth round across a restart */\n"),
    ("                /* we will send the data packet */\n                tcp->info.lastDataSent = now;\n",
     "                /* we will send the data packet */\n"
     "                tcp->diag.txFlushed++;\n"
     "                if (tcp->cong.cwnd >= tcp->cong.hooks->tcp_cong_ssthresh(tcp)) {\n"
     "                    tcp->diag.txCa++;\n"
     "                }\n"
     "                /* rtt6: CA_EVENT_TX_START (tcp_event_data_sent): new data goes out with nothing in flight */\n"
     "                if (_tcp_rtt6CubicOn() && header.sequence > tcp->send.highestSequence &&\n"
     "                    (guint32)(tcp->send.highestSequence + 1) == tcp->send.unacked) {\n"
     "                    _tcp_rtt6TxStart(tcp, now);\n"
     "                }\n"
     "                tcp->info.lastDataSent = now;\n"),
    ("    tcp->cong.hooks->tcp_cong_timeout_ev(tcp);\n    debug(\"[CONG] a congestion timeout has occurred on %s\", tcp->super.boundString);\n",
     "    tcp->cong.hooks->tcp_cong_timeout_ev(tcp);\n"
     "    /* rtt6: Linux enters the Loss state at every RTO, and CUBIC then resets all its state (cubictcp_state) */\n"
     "    if (_tcp_rtt6CubicOn()) {\n"
     "        _tcp_rtt6Reset(tcp);\n"
     "        _tcp_rtt6HystartReset(tcp);\n"
     "        tcp->cubic.rndEnd = 0;\n"
     "    }\n"
     "    debug(\"[CONG] a congestion timeout has occurred on %s\", tcp->super.boundString);\n"),
    ("            debug(\"[CONG] %i packets were acked\", nPacketsAcked);\n            tcp->cong.hooks->tcp_cong_new_ack_ev(tcp, nPacketsAcked);\n",
     "            debug(\"[CONG] %i packets were acked\", nPacketsAcked);\n"
     "            /* rtt6: CUBIC's pkts_acked (delay_min and HyStart) before cong_avoid, as in tcp_ack, with the RTT\n"
     "             * estimator's sample (now - TSecr); not for the ACK of the SYN (Linux initialises CUBIC after it) */\n"
     "            if (_tcp_rtt6CubicOn() && header->timestampEcho != 0 &&\n"
     "                (guint32)header->acknowledgment - (guint32)nPacketsAcked > 1) {\n"
     "                gint64 rtt6Us = (gint64)((now - header->timestampEcho) / SIMTIME_ONE_MICROSECOND);\n"
     "                _tcp_rtt6Acked(tcp, rtt6Us <= 0 ? 1 : rtt6Us);\n"
     "            }\n"
     "            tcp->cong.hooks->tcp_cong_new_ack_ev(tcp, nPacketsAcked);\n"),
    ("                 (int)tcp->rtt5.isCwndLimited, (unsigned)tcp->rtt5.maxPacketsOut);\n",
     "                 (int)tcp->rtt5.isCwndLimited, (unsigned)tcp->rtt5.maxPacketsOut);\n"
     "            /* rtt6: CUBIC and HyStart counters on a line of their own: appended to the snapshot line they passed\n"
     "             * the 500-byte log message buffer (log-c2rust), which cut its end */\n"
     "            info(\"tcpd cubsnap %p bin %d peer %u txfl %\" G_GUINT64_FORMAT \" txca %\" G_GUINT64_FORMAT \" cub %d\"\n"
     "                 \" hstrain %\" G_GUINT64_FORMAT \" hsdelay %\" G_GUINT64_FORMAT \" epochs %\" G_GUINT64_FORMAT\n"
     "                 \" txstart %\" G_GUINT64_FORMAT \" txshift %\" G_GUINT64_FORMAT \" rounds %\" G_GUINT64_FORMAT\n"
     "                 \" rndover %\" G_GUINT64_FORMAT \" rndoveracked %\" G_GUINT64_FORMAT \" rndmax %u dmin %u lastmax %u\"\n"
     "                 \" found %d\",\n"
     "                 (void*)tcp, diagBin, (unsigned)tcp_getPeerIP(tcp), tcp->diag.txFlushed, tcp->diag.txCa,\n"
     "                 _tcp_rtt6CubicOn(), tcp->cubic.hsTrain, tcp->cubic.hsDelay, tcp->cubic.epochs, tcp->cubic.txStart,\n"
     "                 tcp->cubic.txShift, tcp->cubic.rounds, tcp->cubic.roundsOver, tcp->cubic.roundsOverAcked,\n"
     "                 tcp->cubic.rndMax, tcp->cubic.delayMin, tcp->cubic.lastMaxCwnd, (int)tcp->cubic.found);\n"),
])
