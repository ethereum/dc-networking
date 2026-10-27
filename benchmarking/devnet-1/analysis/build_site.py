#!/usr/bin/env python3
"""Create small comparison profiles and lazy-loaded slot detail from caches."""
from collections import Counter, defaultdict
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
from ingest import HERE, BUILD, GENESIS, KINDS, phase, atomic_gzip
from payload_load import COMPARISON_NODES, select_loaded_window, validate_observations
from object_sizes import apply_sizes

MATCHED = COMPARISON_NODES
PAYLOAD_KIND = len(KINDS)
DISPLAY_KINDS = [*KINDS[:-1], 'Payload envelope (legacy)', 'Execution payload (applied)']
RUNS = [
    {'id':'spread','number':2,'title':'Spread','subtitle':'Seven voting waves','genesis':GENESIS[0], 'validators':40300,'nodes_total':500,'supernodes':200,'validators_per_super':200,'subnets':2,'committees_per_slot':2,'x':1,'partial':False,'spread':True,'role_boundary':200,'color':'#5374db','config_evidence':'Archived CLI flags and network config; startup logs confirm spread before genesis.'},
    {'id':'partial','number':3,'title':'Partial attestations','subtitle':'Spread + bundles','genesis':GENESIS[0],'validators':40300,'nodes_total':500,'supernodes':200,'validators_per_super':200,'subnets':2,'committees_per_slot':2,'x':1,'partial':True,'spread':True,'role_boundary':200,'color':'#168674','config_evidence':'Archived CLI flags; steady period begins after documented 17:26 UTC rollout completion.'},
    {'id':'staggered','number':4,'title':'Staggered committees','subtitle':'New genesis · X = 3','genesis':GENESIS[1],'validators':80400,'nodes_total':500,'supernodes':100,'validators_per_super':800,'subnets':4,'committees_per_slot':12,'x':3,'partial':False,'spread':False,'role_boundary':100,'color':'#bd7540','config_evidence':'Archive README records X=3 and topology. No regenesis CLI/config snapshot; logged committee indices and timing provide corroboration. Spread is ignored at X>=2 in the pinned code.'},
]


def quantile(hist, q):
    n=sum(hist.values())
    if not n:return None
    target=math.ceil(n*q);total=0
    for value,count in sorted(hist.items()):
        total+=count
        if total>=target:return value


def ranges(values):
    output=[]
    for v in sorted(set(values)):
        if output and v==output[-1][1]+1:output[-1][1]=v
        else:output.append([v,v])
    return output


def sum_rows(rows, key_count, key_filter=lambda x:True):
    result={}
    for row in rows:
        if not key_filter(row):continue
        key=tuple(row[:key_count])
        if key not in result:result[key]=[0]*(len(row)-key_count)
        acc=result[key]
        for i,value in enumerate(row[key_count:]):acc[i]+=value
    return [[*key,*value] for key,value in sorted(result.items())]


def attach_payloads(detail, observations, chain, node):
    """Join the independently audited payload records without reading raw logs.

    Keep the earliest processing-entry record per slot/root. Both timing views
    describe successful applications, including local and request/response paths.
    The observed clock is arrivedMs; completion uses the coarse logger clock.
    """
    slots = set(detail['slots'])
    unique = {}
    for row in observations:
        if row[0] != chain or row[1] != node or row[2] not in slots:
            continue
        key = row[2], row[8]
        previous = unique.get(key)
        if previous and previous[3:7] != row[3:7]:
            raise ValueError('Conflicting payload application records')
        if previous is None or (row[7], row[9]) < (previous[7], previous[9]):
            unique[key] = row
    detail['payloads'] = []
    detail['payload_instrumented'] = any(r[0] == chain and r[1] == node for r in observations)
    for row in sorted(unique.values(), key=lambda r: (r[2], r[8])):
        slot, size = row[2], row[4]
        completed = row[9] - GENESIS[chain] - slot*12000
        detail['payloads'].append([*row[2:8], completed])
        for mode, elapsed in enumerate([row[7], completed]):
            detail['events'].append([mode, slot, math.floor(elapsed/100), PAYLOAD_KIND,
                                     0, 0, 1, 1, size, 0])


def summarize_node(detail, default_slots, role, evidence):
    slots=set(default_slots)&set(detail['slots'])
    profiles=sum_rows(([r[0],r[2],r[3],r[4],r[5],*r[6:]] for r in detail['events'] if r[1] in slots),5)
    network=sum_rows(([r[2],r[3],r[1],*r[4:]] for r in detail['network'] if r[0] in slots),3)
    delays=defaultdict(Counter)
    for row in detail['delays']:
        if row[0] in slots:
            for delay,count in row[2:]:delays[row[1]][delay]+=count
    blocks=[b for b in detail['blocks'] if b[0] in slots]
    blockslots={b[0] for b in blocks}
    delay_summary={str(t):{'n':sum(h.values()),'p50':quantile(h,.5),'p95':quantile(h,.95),'p99':quantile(h,.99),'negative':sum(c for d,c in h.items() if d<0),'hist':sorted(h.items())} for t,h in delays.items()}
    blockhist=Counter(round(b[1]) for b in blocks)
    blocklag=Counter(b[0]-b[2] for b in blocks)
    # Cumulative host counters are differenced ONLY within one uninterrupted source.
    p2p=[0]*16;duration=0;resets=0
    for sequence in detail.get('p2p',[]):
        for a,b in zip(sequence,sequence[1:]):
            sa=(a[0]-detail['genesis'])//12000;sb=(b[0]-detail['genesis'])//12000
            elapsed=b[0]-a[0]
            if not(0<elapsed<=60000) or sa not in slots or sb not in slots:continue
            deltas=[y-x for x,y in zip(a[1:],b[1:])]
            if min(deltas)<0:resets+=1;continue
            for i,v in enumerate(deltas):p2p[i]+=v
            duration+=elapsed
    return {'id':detail['node'],'role':role,'role_evidence':evidence,'slots':sorted(slots),'coverage':ranges(detail['slots']),
            'profiles':profiles,'network':network,'delays':delay_summary,
            'blocks':{'count':len(blocks),'slots_imported':len(blockslots),'slots_without_import':sorted(slots-blockslots),'p50_ms':quantile(blockhist,.5),'p99_ms':quantile(blockhist,.99),'finalized_lag_p50':quantile(blocklag,.5),'finalized_lag_max':max(blocklag,default=None)},
            'health':{'last_captured_slot':max(detail['slots'],default=None),'last_imported_slot':max((b[0] for b in detail['blocks']),default=None),
                      'last_peer_sample':max(detail.get('peers',[]),default=None)},
            'p2p':{'deltas':p2p,'duration_ms':duration,'resets_excluded':resets},
            'bundle_totals':sum_rows(([r[1],*r[2:]] for r in detail['bundles'] if r[0] in slots),1),
            'payload_instrumented':detail.get('payload_instrumented',False),
            'detail':f'detail-{detail["run"]}-{detail["node"]}.json.gz'}


def build(allow_incomplete=False):
    selection=json.loads((HERE/'results/source-selection.json').read_text())
    manifest=json.loads((HERE/'results/source-manifest.json').read_text())
    payloads=json.loads((HERE/'results/payload-observations.json').read_text())
    with gzip.open(HERE/'results/size-observations.json.gz','rt') as f:object_sizes=json.load(f)
    if object_sizes['build'] != BUILD or object_sizes['archive_sha256'] != manifest['archive_sha256']:
        raise ValueError('Object sizing metadata does not match this capture/build')
    if payloads['archive_sha256'] != manifest['archive_sha256']:
        raise ValueError('Payload observations belong to another archive')
    load_audit=validate_observations(payloads)
    load_audit['runs']={}
    entries=selection['entries']
    missing=[e['cache'] for e in entries if not (HERE/'.cache'/e['cache']).exists()]
    if missing and not allow_incomplete:raise ValueError(f'{len(missing)} member caches are missing; finish ingestion first')
    entries=[e for e in entries if (HERE/'.cache'/e['cache']).exists()]
    grouped=defaultdict(list)
    coverage=defaultdict(set)
    for entry in entries:
        s=entry['source'];grouped[(s['chain'],s['node'])].append(entry)
        for slot in s['owned_slots']:
            run=phase(s['chain'],slot)
            if run!='rollout' and slot>=50:coverage[(run,s['node'])].add(slot)
    runs=json.loads(json.dumps(RUNS))
    for run in runs:
        samples=[coverage[(run['id'],n)] for n in MATCHED]
        candidates=sorted(set.intersection(*samples)) if all(samples) else []
        run['matched_nodes']=MATCHED
        run['load']=select_loaded_window(payloads['rows'], int(run['id']=='staggered'), candidates, MATCHED,
                                        allowed_missing=[608] if run['id']=='partial' else [])
        run['default_slots']=run['load']['selected_slots']
        run['default_ranges']=ranges(run['default_slots'])
        run['nodes']=[]
        load_audit['runs'][run['id']]=run['load']
    lookup={r['id']:r for r in runs}
    global_audit=Counter();audit_sources=[]
    for (chain,node),jobs in sorted(grouped.items()):
        nodeparts=defaultdict(lambda:{'events':[],'network':[],'topics':[],'delays':[],'blocks':[],'bundles':[],'p2p':[],'peers':[],'slots':set()})
        for job in jobs:
            with gzip.open(HERE/'.cache'/job['cache'],'rt') as f:d=json.load(f)
            global_audit.update(d['audit'])
            audit_sources.append({'name':d['source']['name'],'node':node,'chain':chain,'sha256':d['source']['sha256'],'owned_slots':ranges(d['source']['owned_slots']), 'audit':d['audit'],'warnings':d['warnings'],'errors':d['errors']})
            for slot in d['source']['owned_slots']:
                r=phase(chain,slot)
                if r!='rollout':nodeparts[r]['slots'].add(slot)
            for field in ['events','network','topics','delays','blocks','bundles','peers']:
                for row in d[field]:
                    slot=row[1] if field=='events' else row[0]
                    r=phase(chain,slot)
                    if r!='rollout':nodeparts[r][field].append(row)
            # Preserve source separation for counter differences, including resets/gaps.
            for rid in lookup:
                seq=[row for row in d['p2p'] if phase(chain,(row[0]-GENESIS[chain])//12000)==rid]
                if seq:nodeparts[rid]['p2p'].append(seq)
        for rid,part in nodeparts.items():
            if not part['slots'] or rid not in lookup:continue
            run=lookup[rid]
            part.update(node=node,run=rid,genesis=GENESIS[chain])
            attach_payloads(part,payloads['rows'],chain,node)
            global_audit['payload_profile_applications']+=len(part['payloads'])
            part['slots']=sorted(part['slots'])
            # A late vote can be logged in another source; merge after selection.
            part['events']=sum_rows(part['events'],6)
            apply_sizes(part,object_sizes,chain,node)
            global_audit['unmodeled_observed_events']+=sum(r[9] for r in part['events'] if r[0]==0)
            part['network']=sum_rows(part['network'],4)
            part['topics']=sum_rows(part['topics'],3)
            role='super' if node<=run['role_boundary'] else 'home'
            evidence='Startup supernode flag + archived topology' if chain==0 and role=='super' else 'Archived CLI and topology' if chain==0 else 'Archive README topology; role changes at node 100 after regenesis'
            summary=summarize_node(part,run['default_slots'],role,evidence)
            run['nodes'].append(summary)
            atomic_gzip(HERE/'web'/summary['detail'],part)
        print(f'Built node {node}, genesis {chain+1}',flush=True)
    legacy_path=HERE/'data/devnet0-run.json.gz'
    if not legacy_path.exists():legacy_path=HERE.parents[2]/'xray/data/run.json.gz'
    if legacy_path.exists():
        with gzip.open(legacy_path,'rt') as f:old=json.load(f)
        legacy={'id':'devnet0','number':0,'title':'Devnet 0 / NFT','subtitle':'Historical context','genesis':old['genesis_unix']*1000,'validators':old['validators'],'nodes_total':1000,'supernodes':200,'validators_per_super':600,'subnets':6,'committees_per_slot':6,'x':1,'partial':False,'spread':False,'color':'#8d929e','default_slots':list(range(50,129)),'default_ranges':[[50,128]],'nodes':[],'historical':True,'config_evidence':'Existing xray schema-3 reduction; distinct commit, topology, instrumentation and capture sample. Validator allocation notes conflict with total; no validator-normalized claims.'}
        legacy['load']={'status':'not_verified','note':'Historical context only. Devnet 0 description.md reports no time to start Spamoor before its crash. This curve is not certified as a transaction-loaded comparison.'}
        for node in old['nodes']:
            events=[]
            for mode,key in enumerate(['rows','accepted_rows']):
                for r in node[key]:events.append([mode,r[0],r[1],[0,1,2,3,4,6,5][r[2]],int(r[3]==1),0,r[4],r[5],r[7],r[8]])
            lo,hi=node['coverage']['full_slots']
            part={'node':node['id'],'run':'devnet0','genesis':legacy['genesis'],'slots':list(range(lo,hi+1)),'events':events,'network':[],'topics':[],'delays':[],'blocks':[[m[0],m[2],m[4],m[3],0] for m in node['milestones'] if m[1]==6],'bundles':[],'p2p':[]}
            summary=summarize_node(part,legacy['default_slots'],node['role'],node['role_evidence'])
            legacy['nodes'].append(summary)
            atomic_gzip(HERE/'web'/summary['detail'],part)
        runs.append(legacy)
    quality={'archive_sha256':manifest['archive_sha256'],'archive_bytes':manifest['archive_bytes'],'inventory_members':len(manifest['members']),'selected_members':len(entries),'incomplete':bool(missing),'audit':dict(global_audit),'sources':audit_sources}
    (HERE/'results/audit.json').write_text(json.dumps(quality,indent=2)+'\n')
    (HERE/'results/load-validation.json').write_text(json.dumps(load_audit,indent=2)+'\n')
    data={'schema':2,'title':'DC / Devnet 1','build':BUILD,'kinds':DISPLAY_KINDS,'payload_kind':PAYLOAD_KIND,'size_reference_bytes':240,'size_notes':'Logical uncompressed SSZ volume. Payload bytes logged; column weights derived from logged cell count; beacon block weights are conservative lower bounds. Regenesis AC uses a structural lower bound. Not network bandwidth.','matched_nodes':MATCHED,'runs':runs,'load_validation':{k:v for k,v in load_audit.items() if k!='runs'},
          'missing_run':{'number':1,'title':'Slot-start baseline','reason':'Not present in this archive: all 16 first-genesis validator startup captures already enable vote spreading.'},
          'quality':{k:v for k,v in quality.items() if k!='sources'},
          'warnings':['The four planned configurations have only three represented configurations in this archive.','Empty-payload windows are excluded. Prior spread slots 50–291 were empty and do not support the old loaded-traffic comparison.','Partial-attestation rollout 16:56–17:26 UTC is excluded from steady comparisons.','Regenesis changes validators (40,300 → 80,400), supernode allocation (200 × 200 → 100 × 800), subnet count (2 → 4), and committee schedule. Effects cannot be attributed to X alone.','Node 201 lacks a loaded spread capture; node 200 changes role after regenesis. Matched comparisons use 1, 2, 202, with only one home node.','Source README documents stuck nodes 98, 99, 355 and regenesis node 376, as well as missed slots. This is not an all-clear.']}
    atomic_gzip(HERE/'web/data.json.gz',data)
    # Small JS bootstrap makes the overview usable from file:// as well as HTTP.
    (HERE/'web/data.js').write_text('window.DEVNET_DATA='+json.dumps(data,separators=(',',':'),allow_nan=False)+';\n')
    (HERE/'results/summary.json').write_text(json.dumps({'build':BUILD,'runs':[{k:v for k,v in r.items() if k!='nodes'}|{'node_ids':[n['id'] for n in r['nodes']]} for r in runs],'quality':data['quality']},indent=2)+'\n')
    print(f'Built {len(runs)} datasets; {global_audit["failed_records"]} parser failures.',flush=True)
    return data


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--allow-incomplete',action='store_true')
    build(p.parse_args().allow_incomplete)
