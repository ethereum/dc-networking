import json,sys
for run in sys.argv[1:]:
    r=json.load(open(f'runs/{run}/realism.json'))
    print('==',run)
    pq=r.get('pq')
    if isinstance(pq,dict): print(' pq per slot',pq['complete_per_slot_pct'],{c:(v['complete_pct'],v['lat_p50_p99_s']) for c,v in pq['per_class'].items()})
    for k,v in (r.get('prop') or {}).items(): print(' ',k,'miss',v['missing'],'/',v['deliveries'],'start p10..p99',v['from_slot_start_s'])
    sc=r.get('scoring')
    if isinstance(sc,dict): print(' mesh_links/slot',[x['mesh_links'] for x in sc['per_slot']],'neg',[x['peers_with_negative_score'] for x in sc['per_slot']],sc['penalties'])
    p=r.get('peers') or {}
    print(' conns', {g:p[g]['conns']['mean'] for g in p if 'conns' in p[g]})
    print(' mesh_pq/att/block', {g:(p[g].get('mesh_pq',{}).get('mean'),p[g].get('mesh_att',{}).get('mean'),p[g].get('mesh_block',{}).get('mean')) for g in p})
    for k in ('rtt','loss','churn','bg','verify'):
        print(' ',k,json.dumps(r.get(k))[:400])
