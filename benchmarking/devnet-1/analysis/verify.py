#!/usr/bin/env python3
"""Independent raw-log spot reconciliation and full reduction invariants."""
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import tarfile

HERE=Path(__file__).resolve().parents[1]
GENESIS=[datetime(2026,10,8,15,30,5,tzinfo=timezone.utc).timestamp()*1000,
         datetime(2026,10,8,19,30,tzinfo=timezone.utc).timestamp()*1000]


def verify():
    manifest=json.loads((HERE/'results/source-manifest.json').read_text())
    entries=json.loads((HERE/'results/source-selection.json').read_text())['entries']
    owned=set();block_residuals=[];totals=Counter();samplejobs={}
    requested={(0,1,350),(0,1,620),(1,1,300)}
    for e in entries:
        s=e['source']
        for slot in s['owned_slots']:
            key=(s['chain'],s['node'],slot)
            assert key not in owned,('overlapping source ownership',key)
            owned.add(key)
            if key in requested:samplejobs[s['name']]=(slot,e)
        with gzip.open(HERE/'.cache'/e['cache'],'rt') as f:d=json.load(f)
        assert d['audit'].get('failed_records',0)==0,(s['name'],d['errors'])
        assert d['audit']['matched_records']==d['audit']['parsed_records']
        for mode,key in enumerate(['observed_events','accepted_events','ignored_aggregate_events']):
            n=sum(r[6] for r in d['events'] if r[0]==mode)
            assert n==d['audit'].get(key,0)
            totals[key]+=n
        for row in d['network']:
            assert abs(row[4]-sum(row[5:10]))<.001,('network components',s['name'],row)
        for slot,arrival,_,_,clock in d['blocks']:
            block_residuals.append(abs(clock-(GENESIS[s['chain']]+slot*12000+arrival)))
        totals['lines']+=d['audit']['lines']
    assert len(samplejobs)==3,samplejobs.keys()
    reconciled=[]
    path=HERE/manifest['archive']
    with tarfile.open(path,'r|gz',bufsize=4*1024*1024) as archive:
        for member in archive:
            if member.name not in samplejobs:continue
            slot,e=samplejobs[member.name];s=e['source'];start=GENESIS[s['chain']]+slot*12000;end=start+12000
            expected=Counter();rpc=0.0;votes=0
            f=archive.extractfile(member)
            if member.name.endswith('.gz'):f=gzip.GzipFile(fileobj=f)
            for raw in f:
                if b' INFO sync: FFG vote ' in raw:
                    values=dict(re.findall(rb'\b(attSlot|arrivedMs|decidedMs|transport|outcome)=([^ \r\n]+)',raw))
                    if values.get(b'attSlot')!=str(slot).encode() or values.get(b'outcome')!=b'gossip':continue
                    transport=int(values.get(b'transport')==b'bundle')
                    expected[(0,int(values[b'arrivedMs'])//100,transport)]+=1
                    expected[(1,int(values[b'decidedMs'])//100,transport)]+=1
                    votes+=1
                elif b'msg="gossipsub bandwidth"' in raw:
                    fields=dict(re.findall(rb'\b(time|interval_ms|recv_bytes)=([^ \r\n]+)',raw))
                    t=datetime.fromisoformat(fields[b'time'].decode().replace('Z','+00:00')).timestamp()*1000
                    interval=float(fields[b'interval_ms'])
                    overlap=max(0,min(t,end)-max(t-interval,start))
                    if overlap:rpc+=int(fields[b'recv_bytes'])*overlap/interval
            with gzip.open(HERE/'.cache'/e['cache'],'rt') as f:cached=json.load(f)
            actual=Counter()
            for r in cached['events']:
                if r[0] in (0,1) and r[1]==slot and r[3]==0 and r[4]==0:actual[(r[0],r[2],r[5])]+=r[6]
            assert expected==actual,('FFG bins mismatch',member.name,slot)
            reduced_rpc=sum(r[4] for r in cached['network'] if r[0]==slot and r[2]=='all' and r[3]=='recv')
            # Absolute clocks are float64 here; the parser uses integer ms.
            assert abs(rpc-reduced_rpc)<2,('RPC slot total mismatch',rpc,reduced_rpc)
            reconciled.append({'member':member.name,'slot':slot,'ffg_gossip_successes':votes,'exact_observed_and_accepted_bin_match':True,'rpc_received_bytes':reduced_rpc,'independent_rpc_absolute_error_bytes':abs(rpc-reduced_rpc)})
            print(f'Raw reconciliation passed: {member.name}, slot {slot}, {votes} FFG votes',flush=True)
    # log_helpers.go samples sinceSlotStartTime before assembling/logging the
    # remaining fields. The two clocks are not simultaneous. Check at the
    # plotting resolution and report the handful of larger logging delays.
    residuals=sorted(block_residuals)
    p99=residuals[math.ceil(.99*len(residuals))-1]
    assert p99<=10.1 and max(residuals)<=100,('block clocks disagree beyond plotting resolution',p99,max(residuals))
    with path.open('rb') as f:after=hashlib.file_digest(f,'sha256').hexdigest()
    assert after==manifest['archive_sha256'],'Raw archive changed'
    # tar readers can stop at the tar end marker; explicitly validate outer gzip EOF/CRC.
    with gzip.open(path,'rb') as f:
        while f.read(4*1024*1024):pass
    result={'passed':True,'source_members':len(entries),'unique_owned_node_slots':len(owned),'totals':dict(totals),
            'raw_samples':reconciled,'block_clock_anchors':len(block_residuals),'max_block_clock_residual_ms':max(block_residuals,default=None),
            'block_clock_p99_residual_ms':p99,'block_clock_residuals_above_10ms':sum(v>10 for v in residuals),
            'archive_sha256_after':after,'archive_unchanged':True,'outer_gzip_crc_checked':True,
            'scope':'Complete cache conservation/ownership checks; independent raw reconciliation of three node-slot samples, not an independent full-data parser or protocol verification.'}
    (HERE/'results/verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':verify()
