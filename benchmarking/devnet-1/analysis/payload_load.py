#!/usr/bin/env python3
"""Stream actual payload-load evidence; never expand archive members on disk."""
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import statistics
import tarfile

from ingest import HERE, GENESIS, SLOT, line_time, parse

MATCHED = {1, 2, 201, 202}
COMPARISON_NODES = [1, 2, 202]
MIN_PAYLOAD_BYTES = 32 * 1024
CONFIRMATION_SLOTS = 16
FIELDS = ['chain', 'node', 'slot', 'tx_count', 'payload_bytes', 'gas_used',
          'blob_count', 'arrived_ms', 'block_root', 'logged_ms', 'source']
EL_FIELDS = ['slot', 'number', 'tx_count', 'rlp_block_bytes', 'gas_used', 'timestamp']


def integer(value):
    return int(value, 16) if isinstance(value, str) and value.startswith('0x') else int(value)


def ranges(values):
    out = []
    for value in sorted(set(values)):
        if out and out[-1][1]+1 == value:
            out[-1][1] = value
        else:
            out.append([value, value])
    return out


def utc(clock):
    return datetime.fromtimestamp(clock/1000, timezone.utc).isoformat().replace('+00:00', 'Z')


def distribution(values):
    values = list(values)
    return {'min': min(values), 'median': statistics.median(values), 'max': max(values)} if values else None


def loaded(row):
    return row[3] > 0 and row[4] >= MIN_PAYLOAD_BYTES


def select_loaded_window(observations, chain, candidates, nodes, allowed_missing=()):
    """Select a time boundary, retaining missed slots rather than censoring them.

    Require 16 consecutive fully captured slots with qualifying payloads on
    every matched node. Keep every later candidate slot. Reject any later empty
    or small observed payload, conflict, or unexplained missing observation.
    """
    candidates = set(candidates)
    indexed = {}
    for row in observations:
        if row[0] != chain or row[1] not in nodes or row[2] not in candidates:
            continue
        key = (row[1], row[2])
        if key in indexed and indexed[key][3:7]+[indexed[key][8]] != row[3:7]+[row[8]]:
            raise ValueError(f'Conflicting payload records for {key}')
        indexed.setdefault(key, row)
    start = next((start for start in sorted(candidates)
                  if all(slot in candidates and all((node, slot) in indexed and loaded(indexed[node, slot])
                                                   for node in nodes)
                         for slot in range(start, start+CONFIRMATION_SLOTS))), None)
    if start is None:
        raise ValueError('No sustained loaded capture for the matched cohort')
    selected = sorted(slot for slot in candidates if slot >= start)
    unique = {}
    missing = {str(node): [] for node in nodes}
    for slot in selected:
        for node in nodes:
            row = indexed.get((node, slot))
            if row is None:
                missing[str(node)].append(slot)
                if slot not in allowed_missing:
                    raise ValueError(f'Unexplained missing payload: node {node}, slot {slot}')
                continue
            if not loaded(row):
                raise ValueError(f'Payload load stopped or fell below threshold at slot {slot}')
            if slot in unique and unique[slot][3:7]+[unique[slot][8]] != row[3:7]+[row[8]]:
                raise ValueError(f'Nodes disagree about payload at slot {slot}')
            unique.setdefault(slot, row)
    return {'status': 'verified', 'matched_nodes': nodes, 'first_selected_slot': start,
            'selected_slots': selected, 'selected_ranges': ranges(selected),
            'utc_windows': [[utc(GENESIS[chain]+a*SLOT), utc(GENESIS[chain]+(b+1)*SLOT)] for a,b in ranges(selected)],
            'utc_end_exclusive': True, 'candidate_slots_before_load': sorted(candidates-set(selected)),
            'confirmed_payload_slots': len(unique), 'slots_without_payload': sorted(set(selected)-unique.keys()),
            'missing_by_node': missing, 'observations_by_node': {str(n): len(selected)-len(missing[str(n)]) for n in nodes},
            'tx_count': distribution(r[3] for r in unique.values()),
            'payload_bytes': distribution(r[4] for r in unique.values()),
            'gas_used': distribution(r[5] for r in unique.values()),
            'blob_count': distribution(r[6] for r in unique.values()),
            'empty_payloads': 0, 'small_payloads': 0,
            'payloads': [[s, *r[3:7]] for s,r in sorted(unique.items())]}


def validate_observations(data):
    """Check independent EL counts/gas, and consistency across log copies/nodes."""
    unique = {}
    slots = {}
    for row in data['rows']:
        key = tuple(row[:3])+ (row[8],)
        if key in unique and row[3:7] != unique[key][3:7]:
            raise ValueError('Conflicting duplicate payload observation')
        unique.setdefault(key, row)
        slotkey = row[0], row[2]
        value = row[3:7]+[row[8]]
        if slotkey in slots and slots[slotkey] != value:
            raise ValueError(f'Payload disagreement across nodes: {slotkey}')
        slots[slotkey] = value
    execution = {r[0]: r for r in data['execution_rows']}
    if len(execution) != len(data['execution_rows']):
        raise ValueError('Duplicate execution block slot')
    checked = set()
    comparisons = 0
    for row in unique.values():
        if row[0] != 0 or row[2] not in execution:
            continue
        el = execution[row[2]]
        if row[3] != el[2] or row[5] != el[4]:
            raise ValueError('Execution export disagrees with logged txCount/gasUsed')
        comparisons += 1
        checked.add(row[2])
    first_tx = min(r[0] for r in execution.values() if r[2])
    regenesis = [r for r in unique.values() if r[0] == 1]
    return {'passed': True, 'raw_payload_records': len(data['rows']), 'unique_node_payload_records': len(unique),
            'duplicate_observations': len(data['rows'])-len(unique), 'cross_node_payload_conflicts': 0,
            'execution_export_blocks': len(execution), 'execution_checked_node_payloads': comparisons,
            'execution_checked_slots': len(checked), 'execution_tx_and_gas_mismatches': 0,
            'first_genesis_first_transaction_slot': first_tx,
            'first_genesis_first_transaction_utc': utc(GENESIS[0]+first_tx*SLOT),
            'regenesis_last_captured_empty_slot': max(r[2] for r in regenesis if not r[3]),
            'regenesis_first_captured_loaded_slot': min(r[2] for r in regenesis if loaded(r)),
            'regenesis_onset_note': 'Exact transaction-load start is inside an uncaptured interval; slot 251 is the first captured loaded slot, not an asserted start time.',
            'archive_sha256': data['archive_sha256'], 'archive_unchanged': data['archive_unchanged'],
            'policy': {'matched_nodes': COMPARISON_NODES, 'min_tx_count': 1, 'min_payload_bytes': MIN_PAYLOAD_BYTES,
                       'consecutive_confirmation_slots': CONFIRMATION_SLOTS,
                       'selection': 'Keep all common steady full slots at or after the first 16-slot loaded confirmation; reject subsequent observed empty/small payloads. Retain documented missed slots.',
                       'cohort_reason': 'Node 201 has no loaded pre-partial capture. Node 200 changes role at regenesis. Use the same two supers (1, 2) and one home (202) throughout.'}}


def collect():
    manifest = json.loads((HERE/'results/source-manifest.json').read_text())
    selection = json.loads((HERE/'results/source-selection.json').read_text())
    sources = {e['source']['name']: e['source'] for e in selection['entries']
               if e['source']['node'] in MATCHED}
    archive_path = HERE/manifest['archive']
    rows, execution, evidence = [], [], []
    counters = Counter()
    with tarfile.open(archive_path, 'r|gz', bufsize=4*1024*1024) as archive:
        for member in archive:
            source = sources.get(member.name)
            is_execution = member.name.endswith('/chain/geth-blocks-full-node1.jsonl.gz')
            if source is None and not is_execution:
                continue
            stream = archive.extractfile(member)
            if member.name.endswith('.gz'):
                stream = gzip.GzipFile(fileobj=stream)
            digest = hashlib.sha256()
            source_id = len(evidence)
            count, size = 0, 0
            owned = set(source['owned_slots']) if source else set()
            for raw in stream:
                digest.update(raw)
                size += len(raw)
                if is_execution:
                    obj = json.loads(raw)
                    # The export contains batches of JSON-RPC responses per line.
                    for response in obj if isinstance(obj, list) else [obj]:
                        block = response.get('result', response)
                        if not isinstance(block, dict) or 'timestamp' not in block:
                            raise ValueError('Unexpected execution block export structure')
                        clock = integer(block['timestamp'])*1000
                        delta = clock-GENESIS[0]
                        if delta % SLOT:
                            raise ValueError('Execution block does not align with first-genesis slot')
                        execution.append([delta//SLOT, integer(block['number']), len(block['transactions']),
                                          integer(block['size']), integer(block['gasUsed']), clock])
                        count += 1
                elif b'Payload received' in raw:
                    message, fields, _ = parse(raw)
                    if message != 'Payload received':
                        continue
                    counters['matched_payload_records'] += 1
                    clock = line_time(raw)
                    if (clock-GENESIS[source['chain']])//SLOT not in owned:
                        counters['outside_owned_wall_slots'] += 1
                        continue
                    rows.append([source['chain'], source['node'], int(fields['slot']),
                                 int(fields['txCount']), int(fields['payloadBytes']), int(fields['gasUsed']),
                                 int(fields['blobCount']), int(fields['arrivedMs']), fields['blockRoot'],
                                 clock, source_id])
                    count += 1
            sha = digest.hexdigest()
            if source and sha != source['sha256']:
                raise ValueError('Source hash changed: '+member.name)
            evidence.append({'name': member.name, 'sha256_expanded': sha,
                             'expanded_bytes_streamed': size, 'records_retained': count})
            print(f'Payload evidence: {member.name}: {count} records', flush=True)
        # Force the outer gzip stream through its trailer/CRC.
        while archive.fileobj.read(4*1024*1024):
            pass
    with open(archive_path, 'rb') as f:
        sha = hashlib.file_digest(f, 'sha256').hexdigest()
    if sha != manifest['archive_sha256']:
        raise ValueError('Archive changed')
    result = {'schema': 1, 'archive_sha256': sha,
              'method': 'Actual Payload received log fields, canonical source ownership, four matched nodes; execution JSON export streamed for independent transaction-count and gas cross-check.',
              'payload_byte_definition': 'payload.SizeSSZ() logged by Prysm 6c026c4; execution payload only, excluding envelope and blob sidecars. Not the relative-size model or a wire-bandwidth measurement.',
              'fields': FIELDS, 'rows': sorted(rows), 'execution_fields': EL_FIELDS,
              'execution_rows': sorted(execution), 'sources': evidence, 'audit': dict(counters),
              'archive_unchanged': True, 'outer_gzip_crc_passed': True}
    (HERE/'results/payload-observations.json').write_text(json.dumps(result, separators=(',', ':'))+'\n')
    print(f'Wrote {len(rows)} payload observations and {len(execution)} execution blocks.', flush=True)
    return result


if __name__ == '__main__':
    collect()
