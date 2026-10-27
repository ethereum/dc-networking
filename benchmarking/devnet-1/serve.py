#!/usr/bin/env python3
"""Serve only the website and selected audit/documentation files on localhost."""
import argparse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT=Path(__file__).resolve().parent
DOCS={'README.md','SOURCE_MODEL.md','FINDINGS.md','PUBLISHING.md'}
RESULTS={'audit.json','source-manifest.json','source-selection.json','archive-README.md','summary.json','verification.json','cache-migration.json','site-validation.json','metrics.json','http-validation.json','load-validation.json','payload-observations.json','pre-load-comparison.json'}
class Handler(SimpleHTTPRequestHandler):
    def translate_path(self,path):
        path=unquote(urlsplit(path).path).lstrip('/')
        if path in DOCS:
            candidate=(ROOT/path).resolve()
            permitted=candidate.parent==ROOT
        elif path.startswith('results/'):
            candidate=(ROOT/path).resolve()
            permitted=candidate.parent==ROOT/'results' and candidate.name in RESULTS
        else:
            candidate=(ROOT/'web'/(path or 'index.html')).resolve()
            permitted=candidate.is_relative_to(ROOT/'web')
        if not permitted:return str(ROOT/'web'/'__not_found__')
        return str(candidate)
    def end_headers(self):
        self.send_header('Cache-Control','no-cache')
        super().end_headers()
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',type=int,default=8766);a=p.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler)
    print(f'Open http://127.0.0.1:{a.port}',flush=True)
    server.serve_forever()
