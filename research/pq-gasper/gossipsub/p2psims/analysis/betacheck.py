#!/usr/bin/env python3
"""RTT5_BETA rule check (coordinator 19:0x Nov 10).

At every fast-recovery entry ('tcpd fr' line: cwnd before / after, ssthresh before / after) and at every RTO ('tcpd
timeout' line with the cwnd before the timeout, then the 'tcpd rto3' line of the same connection with the ssthresh the
timeout hook set), compare the new ssthresh with the rule:
  --beta 1: max(cwnd * 717 // 1024, 2)  (CUBIC's bictcp_recalc_ssthresh; rtt5b with RTT5_BETA=1)
  --beta 0: cwnd // 2 + 1               (Reno's ssthresh_halve; rtt5 and rtt5b without the switch)
Usage: betacheck.py RUNDIR --beta 0|1   (reads shadow-tcpd.log.gz, shadow.log.gz or shadow.log)
"""
import gzip
import os
import re
import sys
from collections import Counter

run = sys.argv[1]
beta = int(sys.argv[sys.argv.index('--beta') + 1]) if '--beta' in sys.argv else 1
rule = (lambda c: max(c * 717 // 1024, 2)) if beta else (lambda c: c // 2 + 1)
for name in ('shadow-tcpd.log.gz', 'shadow.log.gz', 'shadow.log'):
    path = os.path.join(run, name)
    if os.path.exists(path):
        break
else:
    sys.exit(f'{run}: no shadow-tcpd.log.gz, shadow.log.gz or shadow.log')
fr_re = re.compile(r'tcpd fr (\S+) from (\w+) adv \d+ cwnd (\d+) (\d+) ssthresh (\d+) (\d+)')
to_re = re.compile(r'tcpd timeout (\S+) rto -?\d+ -> -?\d+ backoff (\d+) srtt -?\d+ rttvar -?\d+ cwnd (\d+) ssthresh (\d+)')
r3_re = re.compile(r'tcpd rto3 (\S+) inflight (\d+) cwnd (\d+) reno (\d+) ssthresh (\d+) outstanding \d+ backoff (\d+)')

fr, rto = Counter(), Counter()
bad = []
last_to = {}
opener = gzip.open if path.endswith('.gz') else open
with opener(path, 'rt', errors='replace') as f:
    for line in f:
        if 'tcpd ' not in line:
            continue
        if 'tcpd fr ' in line:
            m = fr_re.search(line)
            if not m:
                fr['unparsed'] += 1
                continue
            c0, c1, s0, s1 = (int(x) for x in m.groups()[2:])
            fr['n'] += 1
            fr['n_' + m.group(2)] += 1
            if s1 == rule(c0):
                fr['ok'] += 1
            elif len(bad) < 10:
                bad.append(f'fr cwnd {c0} -> ssthresh {s1}, rule {rule(c0)}')
            if c1 == s1 + 3:
                fr['cwnd_ok'] += 1
        elif 'tcpd timeout ' in line:
            m = to_re.search(line)
            if m:
                last_to[m.group(1)] = (int(m.group(2)), int(m.group(3)))
            else:
                rto['unparsed_timeout'] += 1
        elif 'tcpd rto3 ' in line:
            m = r3_re.search(line)
            if not m:
                rto['unparsed_rto3'] += 1
                continue
            t = last_to.pop(m.group(1), None)
            if t is None:
                rto['unpaired'] += 1
                continue
            backoff, c0 = t
            s1 = int(m.group(5))
            kind = 'first' if backoff == 1 else 'repeat'
            rto['n'] += 1
            rto['n_' + kind] += 1
            if s1 == rule(c0):
                rto['ok'] += 1
                rto['ok_' + kind] += 1
            elif len(bad) < 10:
                bad.append(f'rto ({kind}) cwnd {c0} -> ssthresh {s1}, rule {rule(c0)}')


def pct(a, b):
    return f'{100.0 * a / b:.3f} %' if b else 'n/a'


print(f'== {run} ({os.path.basename(path)}), rule: ' + ('max(cwnd * 717 // 1024, 2)' if beta else 'cwnd // 2 + 1'))
print(f'fast-recovery entries {fr["n"]} (from slow start {fr["n_ss"]}, from congestion avoidance {fr["n_ca"]}): '
      f'ssthresh after = rule in {fr["ok"]} ({pct(fr["ok"], fr["n"])}); cwnd after = ssthresh + 3 in {fr["cwnd_ok"]}; '
      f'unparsed {fr["unparsed"]}')
print(f'RTOs {rto["n"]} (first of an episode {rto["n_first"]}, repeated {rto["n_repeat"]}): ssthresh after = rule in '
      f'{rto["ok"]} ({pct(rto["ok"], rto["n"])}; first {rto["ok_first"]}, repeated {rto["ok_repeat"]}); unpaired '
      f'{rto["unpaired"]}, unparsed {rto["unparsed_timeout"] + rto["unparsed_rto3"]}')
print('mismatches (first 10): ' + ('; '.join(bad) if bad else 'none'))
