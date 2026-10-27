#!/usr/bin/env python3
"""Reduce complete Docker captures to small, audited per-member caches.

No archive extraction, no raw-line database, no third-party dependencies.
One complete source owns each node/wall-clock slot. Throttled exports and
overlapping copies cannot inflate counts. Rebuild with --force after changes.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
import gzip
import hashlib
import inspect
import json
import math
from pathlib import Path
import re
import tarfile
import time

HERE = Path(__file__).resolve().parents[1]
BUILD = '6c026c484c05c256c7858e9f4a1e8580dd898dbe'
GENESIS = [1791473405000, 1791487800000]
SLOT = 12000
BIN = 100
DAY = int(datetime(2026, 10, 8, tzinfo=timezone.utc).timestamp()*1000)
KINDS = ['FFG vote', 'Goldfish vote', 'FFG aggregate', 'PTC vote', 'Data column', 'Synced new block', 'Payload envelope']
NETWORK_KINDS = ['publish', 'partial', 'ihave', 'iwant', 'idontwant', 'graft', 'prune', 'subscribe', 'unsubscribe', 'overhead', 'other']
INTERESTING = re.compile(rb': (?:FFG vote |Goldfish vote |FFG aggregate |PTC vote |Data column |Synced new block |Payload envelope |P2P bandwidth |Attestation bundles |Connected peers |Submitted new attestations )|msg="gossipsub (?:topic )?bandwidth"')
HEADER = re.compile(r'^\[([^]]+)\]\s+(\w+)\s+([^:]+):\s+(.*)$')
FIELD = re.compile(r'(?:^|\s)([A-Za-z][A-Za-z_0-9]*)=')
LOGFMT = re.compile(r'(?:^|\s)([A-Za-z][A-Za-z_0-9]*)=("(?:\\.|[^"\\])*"|\S*)')
DURATION = re.compile(r'(\d+(?:\.\d+)?)(ns|µs|μs|us|ms|s|m|h)')
SCALES = {'ns':.000001, 'µs':.001, 'μs':.001, 'us':.001, 'ms':1, 's':1000, 'm':60000, 'h':3600000}


@lru_cache(maxsize=60000)
def timestamp(value):
    return round(datetime.fromisoformat(value.replace('Z', '+00:00')).replace(tzinfo=timezone.utc).timestamp()*1000)


def line_time(raw):
    if raw.startswith(b'[2026-10-08 '):
        x = raw[12:raw.index(b']')]
    elif raw.startswith(b'time=2026-10-08T'):
        x = raw[16:raw.index(b'Z')]
    else:
        return None
    return DAY + int(x[:2])*3600000 + int(x[3:5])*60000 + int(x[6:8])*1000 + int((x[9:]+b'000')[:3])


def duration(value):
    parts = DURATION.findall(value)
    if not parts or ''.join(a+b for a,b in parts) != value.lstrip('+-'):
        raise ValueError('invalid duration ' + value)
    return (-1 if value.startswith('-') else 1) * sum(float(a)*SCALES[b] for a,b in parts)


def parse(raw):
    text = raw.decode('utf-8').strip()
    if text.startswith('time='):
        fields = {k: json.loads(v) if v.startswith('"') else v for k,v in LOGFMT.findall(text)}
        return fields.pop('msg'), fields, fields.get('level','INFO')
    match = HEADER.match(text)
    if not match:
        raise ValueError('unrecognized structured line')
    _, level, _, body = match.groups()
    starts = list(FIELD.finditer(body))
    if not starts:
        return body, {}, level
    message = body[:starts[0].start()].strip()
    fields = {}
    for i, field in enumerate(starts):
        val = body[field.end():starts[i+1].start() if i+1<len(starts) else len(body)].strip()
        if val.startswith('"') and val.endswith('"'):
            try: val = json.loads(val)
            except ValueError: pass
        fields[field[1]] = val
    return message, fields, level


def phase(chain, slot):
    if chain == 1:
        return 'staggered'
    t = GENESIS[0] + slot*SLOT
    if t < timestamp('2026-10-08T16:56:00Z'):
        return 'spread'
    if t >= timestamp('2026-10-08T17:26:00Z'):
        return 'partial'
    return 'rollout'


def source_info(member):
    name = member['name']
    if not name.endswith(('beacon.log', 'beacon.log.gz')) or not member.get('first') or not member.get('last'):
        return None
    # The four files at archive root are explicitly documented as throttled.
    if re.fullmatch(r'dc-devnet-1-logs/prysm-geth-\d+/beacon\.log',name):
        return None
    match = re.search(r'prysm-geth-(\d+)', name)
    node = int(match[1]) if match else 355 if 'node-355-' in name else None
    if node is None:
        return None
    chain = int('/run2-genesis-1930/' in name)
    first, last = timestamp(member['first']), timestamp(member['last'])
    lo = max(0, math.ceil((first-GENESIS[chain])/SLOT))
    hi = math.floor((last-GENESIS[chain])/SLOT)-1
    return {'name':name, 'node':node, 'chain':chain, 'first':first, 'last':last,
            'full_slots':[lo,hi], 'sha256':member['sha256'], 'bytes':member['expanded_bytes']}


def select_sources(manifest):
    sources = [s for m in manifest['members'] if (s:=source_info(m))]
    owners = {}
    # Prefer start-to-end captures, then longest window; deterministic ties.
    for s in sorted(sources, key=lambda s:(not s['name'].endswith('.gz'), -(s['last']-s['first']), s['name'])):
        for slot in range(s['full_slots'][0],s['full_slots'][1]+1):
            owners.setdefault((s['chain'],s['node'],slot),s['name'])
    byname = {s['name']:s for s in sources}
    for s in sources: s['owned_slots']=[]
    for (_,_,slot),name in owners.items(): byname[name]['owned_slots'].append(slot)
    for s in sources: s['owned_slots'].sort()
    return byname


def atomic_gzip(path, value):
    path.parent.mkdir(exist_ok=True,parents=True)
    tmp = path.with_suffix(path.suffix+'.tmp')
    with tmp.open('wb') as f, gzip.GzipFile(fileobj=f,mode='wb',mtime=0) as z:
        z.write(json.dumps(value,separators=(',', ':'),allow_nan=False).encode())
    tmp.replace(path)


def parser_fingerprint():
    names=[line_time,timestamp,duration,parse,phase,slot_profile_interval,Reducer]
    code=''.join(inspect.getsource(f) for f in names)
    constants=[BUILD,GENESIS,SLOT,BIN,KINDS,NETWORK_KINDS,INTERESTING.pattern.decode(),HEADER.pattern,FIELD.pattern,LOGFMT.pattern,DURATION.pattern,SCALES]
    return hashlib.sha256((code+json.dumps(constants,sort_keys=True)).encode()).hexdigest()


def slot_profile_interval(end, elapsed, values, owned, genesis, accumulator, suffix):
    """Distribute interval totals by overlap, never treat rate as byte count.

    This is interval-average interpolation, not a packet timestamp reconstruction.
    Only complete owned slots are retained, including at overlap boundaries.
    """
    start = end-elapsed
    first, last = math.floor((start-genesis)/BIN), math.ceil((end-genesis)/BIN)
    for b in range(first,last):
        slot, intra = divmod(b,120)
        if slot not in owned: continue
        overlap = min(end,genesis+(b+1)*BIN)-max(start,genesis+b*BIN)
        if overlap <= 0: continue
        row = accumulator[(slot,intra,*suffix)]
        fraction = overlap/elapsed
        for i,val in enumerate(values): row[i] += val*fraction


class Reducer:
    def __init__(self, source):
        self.source=source
        self.owned=set(source['owned_slots'])
        self.genesis=GENESIS[source['chain']]
        self.audit=Counter()
        self.messages=Counter()
        self.outcomes=Counter()
        self.warnings=Counter()
        self.examples={}
        self.errors=[]
        self.events=defaultdict(lambda:[0,0,0,0])
        self.network=defaultdict(lambda:[0.0]*7)
        self.topics=defaultdict(lambda:[0.0]*6)
        self.p2p=[]
        self.blocks=[]
        self.peers=[]
        self.bundles=defaultdict(lambda:[0]*5)
        self.delays=defaultdict(Counter)
        self.ac=defaultdict(dict)
        self.last_clock=None
        self.digest=hashlib.sha256()

    def add_event(self, mode, slot, when, kind, origin, transport, seats, size, unknown=0):
        # mode: 0 observed; 1 accepted; 2 ignored aggregate (observed timing).
        row=self.events[(mode,slot,math.floor(when/BIN),kind,origin,transport)]
        row[0]+=1;row[1]+=seats;row[2]+=size;row[3]+=unknown
        self.audit[['observed_events','accepted_events','ignored_aggregate_events'][mode]]+=1

    def reject(self, line, error, raw):
        self.audit['failed_records']+=1
        self.audit['error/'+str(error)]+=1
        if len(self.errors)<12:
            self.errors.append({'line':line,'error':str(error),'sample':raw.decode(errors='replace')[:750]})

    def consume(self, raw, line):
        self.digest.update(raw)
        self.audit['lines']+=1
        try: clock=line_time(raw)
        except (ValueError,IndexError): clock=None
        if clock is None:
            self.audit['untimed_lines']+=1
            return
        wallslot=(clock-self.genesis)//SLOT
        if wallslot not in self.owned:
            self.audit['outside_owned_slots']+=1
            return
        self.audit['retained_lines']+=1
        warning=b']  WARN ' in raw or b'] ERROR ' in raw or b'] FATAL ' in raw or b'level=ERROR' in raw
        if not warning and not INTERESTING.search(raw):
            return
        self.audit['matched_records']+=1
        try:
            msg,f,level=parse(raw)
            self.messages[msg]+=1
            self.examples.setdefault(msg,{'line':line,'sample':raw.decode(errors='replace')[:1100]})
            if warning: self.warnings[msg]+=1
            if msg in KINDS:
                self.event(clock,msg,f)
            elif msg=='gossipsub bandwidth':
                self.bandwidth(clock,f)
            elif msg=='gossipsub topic bandwidth':
                self.bandwidth(clock,f,topic=True)
            elif msg=='P2P bandwidth':
                self.p2p.append([clock,*[int(f.get(k,0)) for k in ['totalIn','totalOut','meshsubIn','meshsubOut','attPublishIn','attPublishOut','attBundleIn','attBundleOut','attMetaIn','attMetaOut','attIhaveIn','attIhaveOut','iwantIn','iwantOut','idontwantIn','idontwantOut']]])
            elif msg=='Connected peers':
                self.peers.append([wallslot,int(f.get('total',f.get('active',-1)))])
            elif msg=='Attestation bundles':
                row=self.bundles[(wallslot,f['path'])]
                for i,k in enumerate(['bundles','signatures','peers','new','pending']):row[i]+=int(f.get(k,0))
            self.audit['parsed_records']+=1
        except (ValueError,KeyError,UnicodeError,OverflowError) as error:
            self.reject(line,error,raw)

    def event(self, clock, msg, f):
        kind=KINDS.index(msg)
        slot=int(f['attSlot' if kind in (0,2) else 'voteSlot' if kind==1 else 'slot'])
        arrival=duration(f['sinceSlotStartTime']) if kind==5 else int(f['arrivedMs'])
        outcome=f.get('outcome','import')
        self.outcomes[msg+'/'+outcome]+=1
        origin=int(outcome=='local')
        transport=1 if f.get('transport')=='bundle' else 0
        seats=int(f.get('seats',1))
        if slot<0 or seats<0:raise ValueError('negative slot or seats')
        if kind==0:
            size=240
        elif kind==1:
            # 205 fixed + 100 configured scratch bytes in first genesis.
            # Regenesis has no config snapshot: retain fixed-size lower bound.
            size=305 if self.source['chain']==0 else 205
        elif kind==2:
            n,c=(40300,2) if self.source['chain']==0 else (80400,12)
            ci=int(f['committeeIndex'])
            j=(slot%8)*c+ci
            length=n*(j+1)//(8*c)-n*j//(8*c)
            size=444+length//8+1
        elif kind==3:size=146
        else:size=0
        unknown=int(kind>=4)
        if kind==1:
            if seats<1 or 'validator' not in f:raise ValueError('unidentified AC vote')
            if outcome not in ('local','accepted','queued','replayed','dropped'):raise ValueError('unknown AC outcome')
            # Nested maps save repeated roots; value [first observation, acceptance, local, replay].
            group=self.ac[(slot,f['blockRoot'])]
            key=int(f['validator'])
            # A sampled validator can hold multiple AC seats. The source maps
            # those seats to one validator; message count is still one.
            row=group.setdefault(key,[None,None,origin,False,seats])
            if seats!=row[4]:raise ValueError('AC identity has inconsistent seats')
            if seats>1:self.audit['multi_seat_ac_records']+=1
            if outcome!='replayed':
                if row[0] is not None:self.audit['duplicate_ac_observations']+=1
                row[0]=min(arrival,row[0]) if row[0] is not None else arrival
            else:self.audit['ac_replay_records']+=1
            if outcome in ('local','accepted','replayed'):
                accepted=arrival if origin else int(f['decidedMs'])
                if row[1] is not None:self.audit['duplicate_ac_acceptances']+=1
                if row[1] is None or accepted<row[1]:row[1]=accepted;row[3]=outcome=='replayed'
            return
        if outcome=='ignored':
            if kind!=2:raise ValueError('unexpected ignored object')
            self.add_event(2,slot,arrival,kind,0,transport,seats,size)
            self.audit['ignored/'+f.get('reason','unknown')]+=1
            return
        if outcome not in ('gossip','local','import'):raise ValueError('unknown outcome '+outcome)
        self.add_event(0,slot,arrival,kind,origin,transport,seats,size,unknown)
        accepted=arrival
        if not origin and kind in (0,2,3):
            accepted=int(f['decidedMs']) if 'decidedMs' in f else clock-self.genesis-slot*SLOT
            self.audit['explicit_decision_events' if 'decidedMs' in f else 'logger_decision_events']+=1
        self.add_event(1,slot,accepted,kind,origin,transport,seats,size,unknown)
        if not origin and kind==0:
            delay=accepted-arrival
            self.delays[(slot,transport)][max(-1,min(60000,math.floor(delay)))]+=1
        if kind==5:
            self.blocks.append([slot,arrival,int(f.get('finalizedSlot',0)),f.get('block',''),clock])

    def bandwidth(self, clock, f, topic=False):
        elapsed=float(f['interval_ms'])
        if not 0<elapsed<60000:raise ValueError('invalid tracer interval')
        family='all'
        if topic:
            topicname=f['topic']
            family=next((label for part,label in [('beacon_attestation_','FFG'),('available_attestation','AC'),('beacon_aggregate','aggregate'),('data_column','columns'),('execution_payload','payload'),('beacon_block','block'),('payload_attestation','PTC'),('sync_committee','sync')] if part in topicname),'other' if topicname else 'unattributed')
            directions=[f['event']]
        else:directions=['recv','send','drop']
        for direction in directions:
            prefix='' if topic else direction+'_'
            total=int(f[prefix+'bytes'])
            parts={k:int(f.get(prefix+k+'_bytes',0)) for k in NETWORK_KINDS}
            if total!=sum(parts.values()):raise ValueError('RPC bytes do not equal kind sum')
            # pm_* are subsets of partial, NEVER extra traffic.
            values=[total,parts['publish'],parts['partial'],sum(parts[k] for k in ['ihave','iwant','idontwant','graft','prune','subscribe','unsubscribe']),parts['overhead'],parts['other'],elapsed]
            if not topic or family=='FFG':
                slot_profile_interval(clock,elapsed,values,self.owned,self.genesis,self.network,(family,direction))
            if topic:
                slot=(clock-self.genesis)//SLOT
                row=self.topics[(slot,family,direction)]
                for i,v in enumerate(values[:6]):row[i]+=v
            else:
                self.audit['rpc_'+direction+'_bytes']+=total
                self.audit['rpc_'+direction+'_intervals']+=1

    def finish(self):
        for (slot,root),votes in self.ac.items():
            for observed,accepted,local,replay,seats in votes.values():
                size=305 if self.source['chain']==0 else 205
                if observed is not None:self.add_event(0,slot,observed,1,local,0,seats,size)
                else:self.audit['ac_acceptance_without_original_observation']+=1
                if accepted is not None:
                    self.add_event(1,slot,accepted,1,local,0,seats,size)
                    if replay:self.audit['ac_replay_acceptances']+=1
                    if observed is not None and not local:self.delays[(slot,2)][max(-1,min(60000,accepted-observed))]+=1
                else:self.audit['ac_observation_without_acceptance']+=1
        self.ac.clear()
        assert self.audit['matched_records']==self.audit['parsed_records']+self.audit['failed_records']
        for mode,key in enumerate(['observed_events','accepted_events','ignored_aggregate_events']):
            assert sum(v[0] for k,v in self.events.items() if k[0]==mode)==self.audit[key]
        if self.digest.hexdigest()!=self.source['sha256']:raise ValueError('member hash changed')
        return {'source':self.source,'audit':dict(self.audit),'messages':dict(self.messages),'outcomes':dict(self.outcomes),
                'warnings':dict(self.warnings),'errors':self.errors,'examples':self.examples,
                'events':[[*k,*v] for k,v in sorted(self.events.items())],
                'network':[[*k,*[round(x,5) for x in v]] for k,v in sorted(self.network.items())],
                'topics':[[*k,*v] for k,v in sorted(self.topics.items())],
                'delays':[[*k,*sorted(hist.items())] for k,hist in sorted(self.delays.items())],
                'p2p':self.p2p,'blocks':self.blocks,'peers':self.peers,
                'bundles':[[*k,*v] for k,v in sorted(self.bundles.items())]}


def build(force=False, nodes=None):
    manifest=json.loads((HERE/'results/source-manifest.json').read_text())
    archivepath=HERE/manifest['archive']
    st=archivepath.stat()
    if st.st_size!=manifest['archive_bytes'] or st.st_mtime_ns!=manifest['archive_mtime_ns']:
        raise ValueError('Archive changed; regenerate inventory')
    sources=select_sources(manifest)
    parserhash=parser_fingerprint()
    jobs={}
    index=[]
    for name,s in sources.items():
        if not s['owned_slots'] or (nodes and s['node'] not in nodes):continue
        key=hashlib.sha256((name+s['sha256']+parserhash+json.dumps(s['owned_slots'])).encode()).hexdigest()
        path=HERE/'.cache'/f'{key}.json.gz'
        index.append({'source':s,'cache':path.name})
        if force or not path.exists():jobs[name]=(s,path)
    (HERE/'.cache').mkdir(exist_ok=True)
    (HERE/'results/source-selection.json').write_text(json.dumps({'parser_sha256':parserhash,'entries':index,'policy':'One source per full node wall slot; complete start logs first; no throttled exports.'},indent=2)+'\n')
    start=time.monotonic()
    print(f'{len(jobs)} members to reduce; {len(index)-len(jobs)} cached',flush=True)
    with tarfile.open(archivepath,'r|gz',bufsize=4*1024*1024) as archive:
        for member in archive:
            if member.name not in jobs:continue
            source,path=jobs[member.name]
            print(f'BEGIN node {source["node"]} {member.name}; {len(source["owned_slots"])} full slots',flush=True)
            reducer=Reducer(source)
            stream=archive.extractfile(member)
            if member.name.endswith('.gz'):stream=gzip.GzipFile(fileobj=stream)
            for line,raw in enumerate(stream,1):
                reducer.consume(raw,line)
                if line%1000000==0:print(f'  {line:,} lines; {time.monotonic()-start:.0f}s elapsed',flush=True)
            result=reducer.finish()
            atomic_gzip(path,result)
            print(f'DONE {result["audit"].get("observed_events",0):,} observed; {result["audit"].get("failed_records",0)} errors; {time.monotonic()-start:.1f}s elapsed',flush=True)
    print('Reduction complete.',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--force',action='store_true')
    p.add_argument('--nodes',help='Optional comma-separated subset for debugging')
    a=p.parse_args()
    build(a.force,set(map(int,a.nodes.split(','))) if a.nodes else None)
