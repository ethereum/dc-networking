#!/usr/bin/env python3
"""Package the current reduced dataset for static hosting, without reading raw logs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parents[1]
DOCS = ['README.md', 'SOURCE_MODEL.md', 'FINDINGS.md', 'PUBLISHING.md']
RESULTS = ['audit.json', 'source-manifest.json', 'source-selection.json', 'archive-README.md',
           'summary.json', 'verification.json', 'cache-migration.json', 'site-validation.json',
           'metrics.json', 'http-validation.json', 'load-validation.json', 'payload-observations.json',
           'pre-load-comparison.json', 'payload-profile-validation.json',
           'size-model-audit.json', 'size-observations.json.gz', 'object-overview-validation.json',
           'topic-bandwidth-validation.json']


def website_files():
    text = (HERE/'web/data.js').read_text()
    data = json.loads(text.removeprefix('window.DEVNET_DATA=').strip().removesuffix(';'))
    files = {'index.html', 'style.css', 'app.js', 'stats.js', 'data.js', 'data.json.gz', 'bandwidth.js'}
    files.update(n['detail'] for run in data['runs'] for n in run['nodes'])
    if any(Path(name).name != name for name in files):
        raise ValueError('Unexpected path in the dataset')
    return data, sorted(files)


def package(destination):
    destination = destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Use an empty output directory; existing output is never deleted automatically')
    target = destination/'devnet-1'
    target.mkdir(parents=True, exist_ok=True)
    (target/'results').mkdir()
    data, files = website_files()
    for name in files:
        shutil.copyfile(HERE/'web'/name, target/name)
    for name in DOCS:
        text = (HERE/name).read_text()
        # Local filesystem paths are not necessary in the public documentation.
        text = text.replace(str(HERE), 'benchmarking/devnet-1')
        (target/name).write_text(text)
    for name in RESULTS:
        source = HERE/'results'/name
        if name == 'source-manifest.json':
            manifest = json.loads(source.read_text())
            manifest['archive'] = Path(manifest['archive']).name
            (target/'results'/name).write_text(json.dumps(manifest, indent=2)+'\n')
        else:
            shutil.copyfile(source, target/'results'/name)
    html = (target/'index.html').read_text()
    html = html.replace('href="/', 'href="./').replace('LOCAL ANALYSIS', 'PUBLIC RESEARCH SNAPSHOT')
    html = html.replace('Local archive → streamed reduction → auditable comparison',
                        '<a href="https://github.com/ethereum/dc-networking/tree/main/benchmarking/devnet-1">Data and analysis in dc-networking</a>')
    (target/'index.html').write_text(html)
    (destination/'.nojekyll').write_text('')
    (destination/'index.html').write_text('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="refresh" content="0; url=./devnet-1/">'
        '<title>DC networking benchmarks</title></head><body>'
        '<p><a href="./devnet-1/">Open the Devnet 1 comparison</a></p></body></html>\n')
    inventory = []
    for path in sorted(destination.rglob('*')):
        if path.is_file():
            inventory.append({'path': str(path.relative_to(destination)), 'bytes': path.stat().st_size,
                              'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    report = {'schema': 1, 'archive_sha256': data['quality']['archive_sha256'],
              'prysm_commit': data['build'], 'matched_nodes': data['matched_nodes'],
              'windows': {r['id']: r['default_ranges'] for r in data['runs'] if not r.get('historical')},
              'policy': 'Only referenced website assets and explicitly selected evidence. Raw logs, source checkouts, caches, duplicate files and unrelated project files are excluded.',
              'files': inventory, 'total_bytes': sum(f['bytes'] for f in inventory)}
    (target/'results/publication-manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f'Packaged {len(inventory)+1} files, {report["total_bytes"]/1e6:.1f} MB into {destination}')
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    package(parser.parse_args().output)
