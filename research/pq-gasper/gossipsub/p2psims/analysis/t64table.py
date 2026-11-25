#!/usr/bin/env python3
"""T64 wbsim table across Shadow builds (coordinator 12:4x and 19:4x Nov 10).

Usage: python3 -I .amp-out/t64table.py [NAME ...]
  default NAMEs: rtt4 rtt5 rtt5d rtt5beta rtt5cwv rtt5ssr (runs/T64-rtt-NAME)
Reads from .amp-out: calib-T64-rtt6.txt, then calib-T64-rtt5cs.txt (else calib-T64-rtt5beta.txt), pqsum-T64-rtt-NAME.txt,
pqdiag-T64-rtt-NAME.txt (slots 2-19), tcppath-T64-NAME.txt, rtt3diag-T64-NAME.txt and tcpdiag-T64-NAME.txt.
Prints a Markdown table, '-' where a file or value is missing.
"""
import os
import re
import sys

O = os.path.dirname(os.path.abspath(__file__))
NAMES = sys.argv[1:] or ['rtt4', 'rtt5', 'rtt5d', 'rtt5beta', 'rtt5cwv', 'rtt5ssr']
LABELS = {'rtt4': 'rtt4', 'rtt5': 'rtt5, no DUP', 'rtt5d': 'rtt5 (CWV+SSR+DUP)', 'rtt5beta': 'rtt5 + BETA',
          'rtt5cwv': 'CWV+DUP (SSR off)', 'rtt5ssr': 'SSR+DUP (CWV off)', 'rtt6off': 'rtt6, switches off',
          'rtt6': 'rtt6 (CUBIC + HyStart)', 'rtt6nohs': 'rtt6, HyStart off',
          'cwv6': 'cwv6 (rtt6 binary, SSR off)'}
PATHS = ['1G->1G', '1G->home', 'home->1G', 'home->home']


def read(name):
    try:
        with open(os.path.join(O, name)) as f:
            return f.read()
    except OSError:
        return ''


CALIB = read('calib-T64-cwv6.txt') + read('calib-T64-rtt6.txt') + (read('calib-T64-rtt5cs.txt') or read('calib-T64-rtt5beta.txt'))


def calib(n):
    m = re.search(r'^== T64-rtt-%s:.*?(?=^== |\Z)' % re.escape(n), CALIB, re.M | re.S)
    return m.group(0) if m else ''


def after(text, header):
    i = text.find(header)
    return text[i:] if i >= 0 else ''


def per_path(text, pattern, fmt):
    out = []
    for p in PATHS:
        m = re.search(r'^  %s\s+%s' % (re.escape(p), pattern), text, re.M)
        out.append(fmt(m) if m else '-')
    return ' / '.join(out)


def tp(n):
    return read('tcppath-T64-%s.txt' % n)


def blk(n):
    m = re.search(r'block from publish p50/p95/p99: ([\d.]+) / ([\d.]+) / ([\d.]+)', calib(n))
    return ' / '.join(m.groups()) if m else '-'


def att(n):
    m = re.search(r'att after 4 s p50/p95/p99: [\d.]+ / ([\d.]+) / ([\d.]+)\s+missing \d+ / \d+ \(([\d.]+) %\)', calib(n))
    return '%s / %s; %s %%' % m.groups() if m else '-'


def pq(cls):
    def f(n):
        m = re.search(r'%s: [\d.]+ %% of \d+ node-slots; latency from publish p50/p99 \[([\d.]+), ([\d.]+)\]' % cls,
                      read('pqsum-T64-rtt-%s.txt' % n))
        return '%s / %s' % m.groups() if m else '-'
    return f


def incomplete(n):
    m = re.search(r'^  cloud\s+(\d+):', after(read('pqdiag-T64-rtt-%s.txt' % n), 'incomplete node-slots, slots 2-19'), re.M)
    return m.group(1) if m else '-'


def restarts(n):
    return per_path(after(tp(n), 'restart after idle'), r'total (\d+):', lambda m: str(round(int(m.group(1)) / 17)))


def ssth(n):
    return per_path(after(tp(n), 'restarts that leave cwnd < ssthresh'),
                    r'\d+ restarts,.*\| ssthresh slot 2 (\S+) \(unset \d+ %\), slot 18 (\S+) \(unset \d+ %\)',
                    lambda m: '%s→%s' % m.groups())


def num(path, pattern, fmt=lambda m: m.group(1)):
    def f(n):
        m = re.search(pattern, read(path % n), re.M)
        return fmt(m) if m else '-'
    return f


ROWS = [
    ('block from publish p50 / p95 / p99 (s)', blk),
    ('attestations after 4 s p95 / p99 (s); missing', att),
    ('PQ latency p50 / p99, 50/15 (s)', pq('50x15')),
    ('PQ latency p50 / p99, 50/25 (s)', pq('50x25')),
    ('PQ latency p50 / p99, 1 Gbit (s)', pq('cloud')),
    ('incomplete 1 Gbit node·slots, slots 2–19 (of 396)', incomplete),
    ('first timeouts per 1,000 data packets, 1G→1G / 1G→home / home→1G / home→home',
     lambda n: per_path(tp(n), r'all ([\d.]+):', lambda m: m.group(1))),
    ('resends per 1,000 data packets (same order)',
     lambda n: per_path(tp(n), r'([\d.]+) per 1,000;', lambda m: m.group(1))),
    ('all RTOs', num('rtt3diag-T64-%s.txt', r'^RTOs (\d+):')),
    ('fast-recovery entries per 1,000 data packets (same order)',
     lambda n: per_path(after(tp(n), 'fast-recovery entries per 1,000'), r'([\d.]+) \| [\d.]+ \| [\d.]+;',
                        lambda m: m.group(1))),
    ('cwnd p50/p90 over the run (same order)',
     lambda n: per_path(after(tp(n), 'cwnd over the run'), r'(\d+) / (\d+) \(', lambda m: '%s/%s' % m.groups())),
    ('restarts after idle per slot (same order)', restarts),
    ('ssthresh p50 after a restart, slot 2→18 (same order; unset = mostly never reduced)', ssth),
    ('stalls (snapshots with retransmit data and no timer)',
     num('tcppath-T64-%s.txt', r'stall check: .*?: (\d+) of (\d+)', lambda m: '%s of %s' % m.groups())),
    ('RTO = SRTT + rttvar, snapshots without backoff',
     num('tcpdiag-T64-%s.txt', r'in snapshots without backoff: (\d+) of (\d+)', lambda m: '%s of %s' % m.groups())),
]

print('| T64 (64 hosts × 20 slots, same config and seed) | ' + ' | '.join(LABELS.get(n, n) for n in NAMES) + ' |')
print('|---' * (len(NAMES) + 1) + '|')
for label, fn in ROWS:
    vals = []
    for n in NAMES:
        try:
            v = fn(n)
        except Exception:  # noqa: BLE001 - a missing or older-format file prints '-'
            v = '-'
        vals.append(v if v and v.strip(' /-') else '-')
    print('| %s | %s |' % (label, ' | '.join(vals)))
