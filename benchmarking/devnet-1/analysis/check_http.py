#!/usr/bin/env python3
import gzip
import json
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1]
checks=[]
for path in ['/', '/app.js','/stats.js','/style.css','/data.js','/data.json.gz','/detail-partial-1.json.gz',
             '/README.md','/SOURCE_MODEL.md','/FINDINGS.md','/results/audit.json','/results/source-manifest.json',
             '/results/source-selection.json','/results/verification.json','/results/metrics.json','/results/site-validation.json',
             '/results/load-validation.json','/results/payload-observations.json','/results/pre-load-comparison.json']:
    with urlopen('http://127.0.0.1:8766'+path,timeout=10) as response:
        data=response.read();assert response.status==200
        if path.endswith('.json.gz'):json.loads(gzip.decompress(data))
        elif path.endswith('.json'):json.loads(data)
        checks.append({'path':path,'status':response.status,'bytes':len(data)})
for path in ['/.sources/prysm/go.mod','/results/%2e%2e/.sources/prysm/go.mod','/results/inventory.json']:
    try:urlopen('http://127.0.0.1:8766'+path,timeout=10)
    except HTTPError as e:assert e.code==404;checks.append({'path':path,'status':404})
    else:raise AssertionError('non-deliverable path exposed: '+path)
result={'passed':True,'checks':checks,'visual_browser_qa':'unavailable: Firefox computer-use access not approved'}
(ROOT/'results/http-validation.json').write_text(json.dumps(result,indent=2)+'\n')
print(f'{len(checks)} HTTP checks passed, including JSON/gzip decoding and file scope.')
