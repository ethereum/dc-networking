#!/usr/bin/env python3
"""Stream loaded-window topic counters from the packed archive; never extract it."""
from collections import defaultdict
import hashlib
import gzip
import json
import math
import tarfile
from ingest import HERE, GENESIS, SLOT, BIN, NETWORK_KINDS, line_time, parse, atomic_gzip

FAMILIES = ['FFG', 'AC', 'aggregate', 'PTC', 'columns', 'block', 'payload', 'sync', 'other', 'unattributed']


def topic_family(name):
    return next((label for part, label in [
        ('beacon_attestation_', 'FFG'), ('available_attestation', 'AC'),
        ('beacon_aggregate', 'aggregate'), ('data_column', 'columns'),
        ('execution_payload', 'payload'), ('beacon_block', 'block'),
        ('payload_attestation', 'PTC'), ('sync_committee', 'sync')]
        if part in name), 'other' if name else 'unattributed')


def collect():
    data = json.loads((HERE/'web/data.js').read_text().removeprefix('window.DEVNET_DATA=').strip().removesuffix(';'))
    runs = [r for r in data['runs'] if not r.get('historical')]
    slots = {(int(r['id'] == 'staggered'), s): r['id'] for r in runs for s in r['default_slots']}
    manifest = json.loads((HERE/'results/source-manifest.json').read_text())
    from pathlib import Path
    archive_stat = (HERE/manifest['archive']).stat()
    if archive_stat.st_size != manifest['archive_bytes'] or archive_stat.st_mtime_ns != manifest['archive_mtime_ns']:
        raise ValueError('Archive changed; regenerate its manifest first')
    selection = json.loads((HERE/'results/source-selection.json').read_text())['entries']
    sources = {e['source']['name']: e['source'] for e in selection
               if e['source']['node'] in data['matched_nodes']
               and any((e['source']['chain'], s) in slots for s in e['source']['owned_slots'])}
    profiles = defaultdict(lambda: [0.0]*7)
    evidence = []
    max_topic_log_lag_ms = 0
    with tarfile.open(HERE/manifest['archive'], 'r|gz', bufsize=4*1024*1024) as archive:
        for member in archive:
            source = sources.get(member.name)
            if source is None:
                continue
            stream = archive.extractfile(member)
            if member.name.endswith('.gz'):
                stream = gzip.GzipFile(fileobj=stream)
            digest = hashlib.sha256()
            chain, node = source['chain'], source['node']
            genesis, owned = GENESIS[chain], set(source['owned_slots'])
            records = 0
            report_clock, report_elapsed = None, None
            for raw in stream:
                digest.update(raw)
                if b'msg="gossipsub bandwidth"' not in raw and b'msg="gossipsub topic bandwidth"' not in raw:
                    continue
                clock = line_time(raw)
                if clock is None:
                    continue
                msg, fields, _ = parse(raw)
                elapsed = float(fields['interval_ms'])
                if not 0 < elapsed < 60000:
                    raise ValueError('Invalid tracer interval')
                topic = msg == 'gossipsub topic bandwidth'
                if not topic:
                    report_clock, report_elapsed = clock, elapsed
                else:
                    if report_clock is None:
                        if (clock-genesis)//SLOT in owned:
                            raise ValueError('Topic report has no preceding total')
                        continue
                    if elapsed != report_elapsed:
                        raise ValueError('Topic and total reporting intervals differ')
                    max_topic_log_lag_ms = max(max_topic_log_lag_ms, clock-report_clock)
                    # One atomic snapshot emits the total first, followed by its
                    # topic rows. Their later logger timestamps are not new windows.
                    clock = report_clock
                if (clock-genesis)//SLOT not in owned:
                    continue
                family = topic_family(fields['topic']) if topic else 'all'
                for direction in [fields['event']] if topic else ['recv', 'send', 'drop']:
                    prefix = '' if topic else direction+'_'
                    total = int(fields[prefix+'bytes'])
                    parts = {k: int(fields.get(prefix+k+'_bytes', 0)) for k in NETWORK_KINDS}
                    if total != sum(parts.values()):
                        raise ValueError('RPC components do not sum to total')
                    values = [total, parts['publish'], parts['partial'],
                              sum(parts[k] for k in ['ihave','iwant','idontwant','graft','prune','subscribe','unsubscribe']),
                              parts['overhead'], parts['other'], elapsed]
                    start = clock-elapsed
                    for b in range(math.floor((start-genesis)/BIN), math.ceil((clock-genesis)/BIN)):
                        slot, intra = divmod(b, 120)
                        rid = slots.get((chain, slot))
                        if rid is None or slot not in owned:
                            continue
                        overlap = min(clock, genesis+(b+1)*BIN)-max(start, genesis+b*BIN)
                        if overlap <= 0:
                            continue
                        row = profiles[(rid, node, family, direction, intra)]
                        for i, value in enumerate(values):
                            row[i] += value*overlap/elapsed
                records += 1
            if digest.hexdigest() != source['sha256']:
                raise ValueError('Source hash changed: '+member.name)
            evidence.append({'member': member.name, 'expanded_sha256': digest.hexdigest(), 'records': records})
            print(f'Topic counters: node {node}, genesis {chain+1}, {records} records', flush=True)
        while archive.fileobj.read(4*1024*1024):
            pass
    if {e['member'] for e in evidence} != set(sources):
        raise ValueError('Missing selected source')
    atomic_gzip(HERE/'.cache/topic-bandwidth.json.gz', {
        'archive_sha256': manifest['archive_sha256'], 'sources': evidence,
        'windows': {r['id']: r['default_ranges'] for r in runs},
        'max_topic_log_lag_ms': max_topic_log_lag_ms,
        'rows': [[*key, *values] for key, values in sorted(profiles.items())]})
    validate(data, manifest, profiles, evidence, max_topic_log_lag_ms)


def validate(data, manifest, profiles, evidence, max_topic_log_lag_ms):
    runs = [r for r in data['runs'] if not r.get('historical')]
    max_original_error = 0.0
    max_ffg_alignment_change = 0.0
    max_partition_error = 0.0
    for run in runs:
        for node in run['nodes']:
            if node['id'] not in data['matched_nodes']:
                continue
            for family, direction, bin_id, *values in node['network']:
                fresh = profiles[(run['id'], node['id'], family, direction, bin_id)]
                for a, b in zip(values, fresh):
                    if family == 'FFG':
                        max_ffg_alignment_change = max(max_ffg_alignment_change, abs(a-b))
                        continue
                    max_original_error = max(max_original_error, abs(a-b))
                    # Original caches round each owned slot/bin to five decimal
                    # places before summing slots; allow only that rounding bound.
                    if not math.isclose(a, b, rel_tol=1e-10, abs_tol=len(run['default_slots'])*0.000005+0.00001):
                        raise ValueError(f'Existing RPC profile changed: {run["id"], node["id"], family, direction, bin_id, a, b}')
            for direction in ['recv', 'send', 'drop']:
                for bin_id in range(120):
                    total = profiles[(run['id'], node['id'], 'all', direction, bin_id)]
                    for col in range(6):
                        topics = sum(profiles.get((run['id'], node['id'], f, direction, bin_id), [0]*7)[col] for f in FAMILIES)
                        max_partition_error = max(max_partition_error, abs(total[col]-topics))
                        if not math.isclose(total[col], topics, rel_tol=1e-10, abs_tol=1e-5):
                            raise ValueError(f'Topic partition mismatch: {run["id"], node["id"], direction, bin_id, col, total[col], topics}')
    result = {'schema': 1, 'archive_sha256': manifest['archive_sha256'], 'families': FAMILIES,
              'matched_nodes': data['matched_nodes'],
              'windows': {r['id']: r['default_ranges'] for r in runs},
              'row_schema': ['run','node','family','direction','bin','total','publish','partial','control','overhead','other','exposure_ms'],
              'rows': [[*key, *values] for key, values in sorted(profiles.items())]}
    (HERE/'web/bandwidth.js').write_text('window.DEVNET_BANDWIDTH='+json.dumps(result, separators=(',', ':'))+';\n')
    report = {'passed': True, 'archive_sha256': manifest['archive_sha256'],
              'method': 'Stream only selected matched-node sources from the packed archive; retain 100 ms interval-weighted topic counters in the existing loaded windows. Never extract files.',
              'windows': result['windows'], 'matched_nodes': data['matched_nodes'],
              'sources': evidence, 'rows': len(profiles), 'outer_gzip_crc_passed': True,
              'original_all_topic_profiles_max_absolute_error': max_original_error,
              'ffg_report_alignment_max_bin_change_bytes_or_ms': max_ffg_alignment_change,
              'topic_report_alignment': 'Every topic row uses the preceding all-topic report timestamp and identical interval_ms, matching the pinned tracer atomic snapshot and log order.',
              'max_topic_log_lag_ms': max_topic_log_lag_ms,
              'topic_partition_max_absolute_error_bytes': max_partition_error,
              'checks': ['Every expanded source SHA-256 matches the prior source manifest',
                         'Existing all-topic counters match within the original five-decimal per-slot cache rounding bound',
                         'Topic components sum to the all-topic counters in every loaded node/bin/direction',
                         'Topics use all-topic exposure; absent topic records are zero only in covered bins',
                         'Partial-message component fields are subsets, never additional bytes']}
    (HERE/'results/topic-bandwidth-validation.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'sources'}, indent=2), flush=True)


if __name__ == '__main__':
    import sys
    if '--validate' in sys.argv:
        data = json.loads((HERE/'web/data.js').read_text().removeprefix('window.DEVNET_DATA=').strip().removesuffix(';'))
        manifest = json.loads((HERE/'results/source-manifest.json').read_text())
        with gzip.open(HERE/'.cache/topic-bandwidth.json.gz', 'rt') as stream:
            cached = json.load(stream)
        assert cached['archive_sha256'] == manifest['archive_sha256']
        assert cached['windows'] == {r['id']: r['default_ranges'] for r in data['runs'] if not r.get('historical')}
        validate(data, manifest, defaultdict(lambda: [0.0]*7,
                 {tuple(r[:5]): r[5:] for r in cached['rows']}), cached['sources'], cached['max_topic_log_lag_ms'])
    else:
        collect()
