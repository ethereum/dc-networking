#!/usr/bin/env python3
"""Verify static publication paths, hashes, gzip integrity and loaded windows."""
import argparse
import gzip
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import urlsplit


def check(root):
    root = root.resolve()
    target = root/'devnet-1'
    manifest = json.loads((target/'results/publication-manifest.json').read_text())
    expected = {f['path'] for f in manifest['files']} | {'devnet-1/results/publication-manifest.json'}
    actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    assert actual == expected, 'Unexpected or missing public files'
    for item in manifest['files']:
        file = root/item['path']
        assert not file.is_symlink(), item['path']
        assert hashlib.sha256(file.read_bytes()).hexdigest() == item['sha256'], item['path']
        if file.suffix == '.gz':
            with gzip.open(file, 'rb') as stream:
                while stream.read(1024*1024):
                    pass
    class Links(HTMLParser):
        def handle_starttag(self, tag, attrs):
            for key, value in attrs:
                if key not in ('href', 'src') or not value or value.startswith(('#', 'data:')):
                    continue
                url = urlsplit(value)
                if url.scheme or url.netloc:
                    continue
                assert not url.path.startswith('/'), 'Root-relative URL breaks hosting below a path: '+value
                path = (self.folder/url.path).resolve()
                assert path.is_relative_to(root), value
                if path.is_dir():
                    path = path/'index.html'
                assert path.is_file(), value
    for file in root.rglob('*.html'):
        parser = Links(); parser.folder = file.parent; parser.feed(file.read_text())
    data = json.loads((target/'data.js').read_text().removeprefix('window.DEVNET_DATA=').strip().removesuffix(';'))
    assert data['matched_nodes'] == [1, 2, 202]
    assert {r['id']: r['default_ranges'] for r in data['runs'] if not r.get('historical')} == {
        'spread': [[333, 379]], 'partial': [[580, 643], [684, 707]], 'staggered': [[251, 274], [284, 370]]}
    for run in data['runs']:
        for node in run['nodes']:
            assert (target/node['detail']).is_file()
    for name in ['load-validation', 'verification', 'site-validation', 'payload-profile-validation', 'size-model-audit', 'object-overview-validation', 'topic-bandwidth-validation']:
        assert json.loads((target/f'results/{name}.json').read_text())['passed']
    print(f'Publication check passed: {len(actual)} files; all links, hashes, gzip streams and loaded windows.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('directory', type=Path)
    check(p.parse_args().directory)
