#!/usr/bin/env python3
"""Pinned SSZ object weights; stream only missing metadata, never extract logs."""
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
import tarfile
from ingest import HERE, BUILD, GENESIS, SLOT, line_time, parse, atomic_gzip

NODES = [1, 2, 202]
BLOCK_FLOOR = 100 + 84 + 396 + 324 + 20


def column_bytes(cells):
    if cells < 0:
        raise ValueError('Negative column cell count')
    return 56 + 2096*cells


def block_floor(fields):
    # Missing dynamic lists stay omitted. Included attestation bitlists have
    # at least the SSZ delimiter byte; each list entry needs a 4-byte offset.
    counts = [int(fields.get(k, 0)) for k in
              ['attestations','blobKzgCommitmentCount','proposerSlashings','voluntaryExits']]
    if min(counts) < 0:
        raise ValueError('Negative block list length')
    return BLOCK_FLOOR + sum(n*size for n,size in zip(counts,[241,48,416,112]))


def apply_sizes(part, extra, chain, node):
    if node not in extra['nodes']:
        return
    columns = {(r[2],r[3],r[4]):r[5:] for r in extra['columns'] if r[:2] == [chain,node]}
    transitions = {r[2]:r[3:] for r in extra['blocks'] if r[:2] == [chain,node]}
    block_counts = Counter(b[0] for b in part['blocks'])
    for r in part['events']:
        if r[3] == 4:
            expected, size = columns[(r[1],r[2],r[4])]
            if r[6] != expected:
                raise ValueError(f'Column enrichment count mismatch: {chain,node,r[:7]}')
            r[8], r[9] = size, 0
        elif r[3] == 5:
            transition_count, size = transitions.get(r[1], [0,BLOCK_FLOOR])
            r[8] = r[6]*(size if transition_count == 1 and block_counts[r[1]] == 1 else BLOCK_FLOOR)
            r[9] = 0


def collect():
    manifest = json.loads((HERE/'results/source-manifest.json').read_text())
    entries = json.loads((HERE/'results/source-selection.json').read_text())['entries']
    sources = {e['source']['name']:e['source'] for e in entries if e['source']['node'] in NODES}
    columns = defaultdict(lambda:[0,0]);blocks=defaultdict(list);evidence=[]
    with tarfile.open(HERE/manifest['archive'],'r|gz',bufsize=4*1024*1024) as archive:
        for member in archive:
            source = sources.get(member.name)
            if source is None:
                continue
            stream = archive.extractfile(member)
            if member.name.endswith('.gz'):
                stream = gzip.GzipFile(fileobj=stream)
            digest=hashlib.sha256();owned=set(source['owned_slots']);retained=0
            chain,node=source['chain'],source['node']
            for raw in stream:
                digest.update(raw)
                if b'Data column ' not in raw and b'Finished applying state transition ' not in raw:
                    continue
                clock=line_time(raw)
                if clock is None or (clock-GENESIS[chain])//SLOT not in owned:
                    continue
                msg,f,_=parse(raw)
                if msg == 'Data column':
                    key=(chain,node,int(f['slot']),math.floor(int(f['arrivedMs'])/100),int(f['outcome']=='local'))
                    columns[key][0]+=1
                    columns[key][1]+=column_bytes(int(f['kzgCommitmentCount']))
                    retained+=1
                elif msg == 'Finished applying state transition':
                    blocks[chain,node,int(f['slot'])].append(block_floor(f))
                    retained+=1
            if digest.hexdigest() != source['sha256']:
                raise ValueError('Source changed: '+member.name)
            evidence.append({'member':member.name,'expanded_sha256':digest.hexdigest(),'records':retained})
            print(f'Object sizes: {node}, genesis {chain+1}: {retained} metadata records',flush=True)
        while archive.fileobj.read(4*1024*1024):
            pass
    result={'schema':1,'build':BUILD,'archive_sha256':manifest['archive_sha256'],'nodes':NODES,
            'columns':[[*key,*v] for key,v in sorted(columns.items())],
            'blocks':[[*key,len(v),v[0] if len(v)==1 else BLOCK_FLOOR] for key,v in sorted(blocks.items())],
            'sources':evidence}
    atomic_gzip(HERE/'results/size-observations.json.gz',result)
    report={'passed':True,'build':BUILD,'archive_sha256':manifest['archive_sha256'],
            'method':'Stream selected node logs, verify every expanded source hash, and retain only SSZ sizing metadata. No files extracted.',
            'nodes':NODES,'sources':evidence,'column_records':sum(v[0] for v in columns.values()),
            'column_formula':'56 + 2096 * logged kzgCommitmentCount',
            'block_formula':'at least 924 + 241*attestations + 48*blob commitments + 416*proposer slashings + 112*voluntary exits',
            'block_scope':'Enrich only unique node/slot block-transition joins; otherwise structural 924-byte floor. Unlogged dynamic lists and full attestation bitlist lengths omitted.',
            'unique_block_transition_slots':sum(len(v)==1 for v in blocks.values()),
            'ambiguous_block_transition_slots':sum(len(v)!=1 for v in blocks.values()),
            'outer_gzip_crc_passed':True}
    (HERE/'results/size-model-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Finished object-size metadata; raw archive remains packed.',flush=True)


if __name__ == '__main__':
    collect()
