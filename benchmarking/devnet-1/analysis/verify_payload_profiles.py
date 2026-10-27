#!/usr/bin/env python3
"""Reconcile overview payload counts, clocks and bytes to the audited reduction."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]


def verify(baseline=None):
    evidence_path = HERE/'results/payload-observations.json'
    evidence = json.loads(evidence_path.read_text())
    data = json.loads(gzip.decompress((HERE/'web/data.json.gz').read_bytes()))
    previous = json.loads(gzip.decompress(baseline.read_bytes())) if baseline else None
    checks = []
    for run in data['runs']:
        if run.get('historical'):
            continue
        chain = int(run['id'] == 'staggered')
        for node in run['nodes']:
            selected = set(node['slots'])
            earliest = {}
            for row in evidence['rows']:
                if row[:2] != [chain, node['id']] or row[2] not in selected:
                    continue
                identity = row[2], row[8]
                if identity not in earliest or (row[7], row[9]) < (earliest[identity][7], earliest[identity][9]):
                    earliest[identity] = row
            expected = Counter()
            for row in earliest.values():
                clocks = row[7], row[9]-run['genesis']-row[2]*12000
                for mode, clock in enumerate(clocks):
                    expected[mode, clock//100, 'count'] += 1
                    expected[mode, clock//100, 'bytes'] += row[4]
            actual = Counter()
            for row in node['profiles']:
                if row[2] != data['payload_kind']:
                    continue
                assert row[3:5] == [0,0] and row[8] == 0
                actual[row[0], row[1], 'count'] += row[5]
                actual[row[0], row[1], 'bytes'] += row[7]
            assert expected == actual, (run['id'], node['id'], 'payload profile mismatch')
            if previous:
                old_run = next(r for r in previous['runs'] if r['id'] == run['id'])
                old = next(n for n in old_run['nodes'] if n['id'] == node['id'])
                for key in ['slots', 'network', 'delays', 'blocks']:
                    assert node[key] == old[key], (run['id'], node['id'], key)
                assert [p for p in node['profiles'] if p[2] != data['payload_kind']] == old['profiles']
            if node['id'] in data['matched_nodes']:
                assert len(earliest) == run['load']['confirmed_payload_slots']
                checks.append({'run': run['id'], 'node': node['id'],
                               'payloads': len(earliest),
                               'ssz_bytes': sum(r[4] for r in earliest.values()),
                               'comparison_slots': len(selected)})
    report = {'passed': True, 'source': 'results/payload-observations.json',
              'source_sha256': hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
              'method': 'Independent reconciliation of every payload profile bin against the previously audited payload reduction; earliest processing entry per slot/root, separate entry and application-log clocks.',
              'raw_archive_read': False, 'matched_nodes': checks,
              'prior_non_payload_profiles_rpc_delays_blocks_unchanged': True if previous else None}
    (HERE/'results/payload-profile-validation.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path)
    verify(parser.parse_args().baseline)
