#!/usr/bin/env python3
"""Inventory tar/gzip streams without writing any expanded archive members."""
import argparse
import gzip
import hashlib
import json
import os
import re
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
DEFAULT = HERE.parents[2] / 'devnet-1.nosync'
TIMESTAMP = re.compile(r'(2026-10-08)[ T](\d\d:\d\d:\d\d(?:\.\d+)?)')


def inspect_stream(stream):
    digest = hashlib.sha256()
    head = b''
    tail = b''
    size = 0
    while chunk := stream.read(4 * 1024 * 1024):
        digest.update(chunk)
        head += chunk[:max(0, 65536 - len(head))]
        tail = (tail[-65536:] + chunk)[-65536:]
        size += len(chunk)
    return size, digest.hexdigest(), head.decode(errors='replace'), tail.decode(errors='replace')


def build(path):
    members = []
    readme = ''
    with tarfile.open(path, 'r|gz', bufsize=4 * 1024 * 1024) as archive:
        for member in archive:
            if not member.isfile():
                continue
            name = member.name
            rec = {'name': name, 'stored_bytes': member.size}
            islog = name.endswith(('beacon.log', 'beacon.log.gz', 'validator.log', 'validator.log.gz'))
            metadata = name.endswith(('README.md', 'cli-args.txt', 'config.yaml', 'WINDOW.txt', '.status', '.err'))
            if islog or metadata:
                stream = archive.extractfile(member)
                if name.endswith('.log.gz'):
                    stream = gzip.GzipFile(fileobj=stream)
                size, digest, head, tail = inspect_stream(stream)
                rec.update(expanded_bytes=size, sha256=digest)
                if islog:
                    times = TIMESTAMP.findall(head)
                    ends = TIMESTAMP.findall(tail)
                    rec['first'] = 'T'.join(times[0]) + 'Z' if times else None
                    rec['last'] = 'T'.join(ends[-1]) + 'Z' if ends else None
                    rec['startup_flags'] = re.findall(r'Enabled feature flag ([\w-]+)=', head)
                    rec['builds'] = sorted(set(re.findall(r'Prysm/[^ /]+/([0-9a-f]{40})', head)))
                    rec['supernode_startup'] = 'Operating in supernode mode' in head
                    rec['genesis_roots'] = sorted(set(re.findall(r'genesisValidatorsRoot=(0x[0-9a-f]+)', head)))
                elif name.endswith('README.md'):
                    readme = head
                elif name.endswith('cli-args.txt'):
                    # Save only the knobs relevant to this analysis, not addresses or wallet paths.
                    rec['images'] = [x for x in head.splitlines() if x.startswith('ethpandaops/')]
                    rec['flags'] = [x for x in head.splitlines() if x.startswith(('--goldfish', '--gossipsub', '--decoupled', '--ffg-', '--partial-', '--subscribe-all'))]
                elif name.endswith('config.yaml'):
                    rec['config'] = {k: v for k, v in re.findall(r'^([A-Z][A-Z_0-9]+):\s*(.*?)\s*$', head, re.M) if any(x in k for x in ('GENESIS', 'SLOT', 'ROUND', 'SUBNET', 'COMMITTEE', 'AGGREGAT', 'SCRATCH', 'DUE_BPS'))}
                else:
                    rec['text'] = head[:1200]
                if name.endswith('beacon.log.gz'):
                    print(f'Inventoried {name}: {size / 1e6:.1f} MB streamed', flush=True)
            members.append(rec)
    with path.open('rb') as f:
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
    result = {'archive': os.path.relpath(path.resolve(), HERE), 'archive_bytes': path.stat().st_size,
              'archive_mtime_ns': path.stat().st_mtime_ns, 'archive_sha256': digest,
              'stored_member_bytes': sum(m['stored_bytes'] for m in members),
              'members': members, 'readme': readme}
    (HERE / 'results').mkdir(exist_ok=True)
    (HERE / 'results/source-manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    (HERE / 'results/archive-README.md').write_text(readme)
    print(f'Inventory complete: {len(members)} files; no extraction.', flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path)
    args = parser.parse_args()
    build(args.archive or next(DEFAULT.glob('*.tar.gz')))
