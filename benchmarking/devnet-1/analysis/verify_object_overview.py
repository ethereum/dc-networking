#!/usr/bin/env python3
"""Check sizing coverage and preserve non-size measurements against a snapshot."""
import argparse
import gzip
import json
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]


def verify(baseline=None):
    data=json.loads(gzip.decompress((HERE/'web/data.json.gz').read_bytes()))
    previous=json.loads(gzip.decompress(baseline.read_bytes())) if baseline else None
    checked=[]
    for run in data['runs']:
        if run.get('historical'):continue
        for node in run['nodes']:
            if previous:
                oldrun=next(r for r in previous['runs'] if r['id']==run['id'])
                old=next(n for n in oldrun['nodes'] if n['id']==node['id'])
                for key in ['slots','network','delays','blocks']:
                    assert node[key]==old[key],(run['id'],node['id'],key)
                assert [p[:7] for p in node['profiles']]==[p[:7] for p in old['profiles']]
                assert [p for p in node['profiles'] if p[2] not in (4,5)]==[p for p in old['profiles'] if p[2] not in (4,5)]
            if node['id'] in data['matched_nodes']:
                rows=[p for p in node['profiles'] if p[0]==0 and p[3]==0]
                assert all(p[8]==0 for p in rows),'Unmodeled object in matched cohort'
                checked.append({'run':run['id'],'node':node['id'],
                                'by_kind':{data['kinds'][kind]:{'events':sum(p[5] for p in rows if p[2]==kind),
                                'ssz_bytes_or_lower_bound':sum(p[7] for p in rows if p[2]==kind)} for kind in sorted({p[2] for p in rows})}})
    report={'passed':True,'scope':'All observed object families in the matched cohort have SSZ weights or documented lower bounds. New weights affect only columns and beacon blocks.',
            'baseline_checked':str(baseline.name) if baseline else None,
            'event_counts_timing_rpc_and_vote_payload_sizes_unchanged':True if previous else None,
            'matched_nodes':checked}
    (HERE/'results/object-overview-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Object overview checks passed; '+str(len(checked))+' matched node/run combinations.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',type=Path)
    verify(p.parse_args().baseline)
