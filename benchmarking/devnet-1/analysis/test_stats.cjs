const test=require('node:test');
const assert=require('node:assert/strict');
const S=require('../web/stats.js');

test('Gaussian smoothing preserves total size, including at slot boundaries',()=>{
 const raw=Array(120).fill(0);raw[0]=10;raw[55]=20;raw[119]=30;
 const smoothed=S.smoothProfile(raw,150);
 assert(Math.abs(smoothed.reduce((a,b)=>a+b,0)-60)<1e-10);
 assert(smoothed[1]>0&&smoothed[118]>0);assert(smoothed.every(v=>v>=0));
 assert.deepEqual(S.smoothProfile(raw,0),raw);
 assert(S.smoothProfile(Array(120).fill(null),150).every(v=>v===null));
});

test('topic rates use total tracer exposure, not active-topic exposure',()=>{
 const n={network:[['all','recv',0,1024,100,200,300,400,24,100],['FFG','recv',0,512,0,0,0,0,0,200]]};
 assert.equal(S.networkProfile(n,{direction:'recv',family:'FFG'})[0],5);
 assert.equal(S.rpcRate(n,'recv'),10);
 assert.equal(S.networkProfile(n,{direction:'recv',family:'all'})[1],null);
});
test('missing byte instrumentation is unavailable, not zero',()=>{
 const n={network:[]};assert.equal(S.rpcRate(n,'recv'),null);
 assert(S.networkProfile(n,{direction:'recv',family:'all'}).every(x=>x===null));
});
test('an unsupported SSZ object weight is not a zero-byte object',()=>{
 const n={slots:[1],profiles:[[0,5,5,0,0,1,1,0,1]]};
 assert(S.eventProfile(n,{timing:'0',kind:'5',transport:'all',metric:'ssz'}).every(x=>x===null));
});
test('RPC component selection keeps partial bytes separate',()=>{
 const n={network:[['all','recv',0,1024,100,200,300,400,24,100]]};
 assert.equal(S.networkProfile(n,{direction:'recv',family:'all',component:'partial'})[0],200/100*1000/1024);
});
test('means weight nodes equally rather than pooling events',()=>{
 const a=S.bands([[1,2],[3,6]],'range');assert.deepEqual(a.mean,[2,4]);assert.deepEqual(a.lo,[1,2]);assert.deepEqual(a.hi,[3,6]);
});
test('one home node cannot supply a confidence interval',()=>{
 const a=S.bands([[1,2]],'ci');assert.deepEqual(a.mean,[1,2]);assert.deepEqual(a.lo,[null,null]);assert.deepEqual(a.hi,[null,null]);
});
test('queued local production and ignored aggregates stay out of received success view',()=>{
 const n={slots:[1,2],profiles:[[0,5,0,0,0,10,10,2400,0],[0,5,0,1,0,30,30,7200,0],[2,5,2,0,0,100,100,75900,0]]};
 const o={timing:'0',kind:'all',transport:'all',metric:'events'};
 assert.equal(S.eventProfile(n,o)[5],5);
 assert.equal(S.eventProfile(n,{...o,timing:'2'})[5],50);
});
test('transport filter selects only the specified FFG transport',()=>{
 const n={slots:[1],profiles:[[0,0,0,0,0,5,5,1200,0],[0,0,0,0,1,7,7,1680,0],[0,0,1,0,0,10,10,3050,0]]};
 assert.equal(S.eventProfile(n,{timing:'0',kind:'all',transport:'1',metric:'events'})[0],7);
});
test('CDF retains the tail in its denominator',()=>{
 const n={delays:{'0':{hist:[[5,99],[1000,1]]}}};
 const a=S.delayProfile(n,{transport:'all'},50);assert.equal(a.at(-1),99);assert.equal(S.quantile(S.delayHist(n),.99),5);
});
test('reception CDF uses upper bin edges, observation counts, and the full tail',()=>{
 const n={profiles:[[0,-1,1,0,0,1,100,305,0],[0,0,1,0,0,2,200,610,0],[0,119,1,0,0,1,100,305,0],[0,120,1,0,0,1,100,305,0],
  [0,0,1,1,0,100,100,30500,0],[1,0,1,0,0,100,100,30500,0],[0,0,0,0,0,100,100,24000,0]]};
 const a=S.receptionProfile(n,{metric:'goldfish-cdf'});
 assert.equal(a.length,121);assert.equal(a[0],20);assert.equal(a[1],60);assert.equal(a[119],60);assert.equal(a[120],80);
 assert(a.every((v,i)=>!i||v>=a[i-1]));
});
test('missing or uninstrumented reception samples are unavailable, not a zero CDF',()=>{
 assert(S.receptionProfile({profiles:[]},{metric:'goldfish-cdf'}).every(v=>v===null));
 const n={payload_instrumented:false,profiles:[[0,0,7,0,0,1,1,1000000,0]]};
 assert(S.receptionProfile(n,{metric:'payload-cdf'}).every(v=>v===null));
 n.payload_instrumented=true;assert.equal(S.receptionProfile(n,{metric:'payload-cdf'})[1],100);
});
test('reception CDF normalizes within each node and ignores unrelated hidden filters',()=>{
 const run={matched_nodes:[1,2,202],nodes:[
  {id:1,slots:[1],profiles:[[0,0,1,0,0,100,100,30500,0]]},
  {id:2,slots:[1],profiles:[[0,10,1,0,0,1,1,305,0]]},
  {id:202,slots:[1],profiles:[]} ]};
 const p=S.profile(run,{metric:'goldfish-cdf',cohort:'all',kind:'0',timing:'2',transport:'1',band:'ci',smoothing:'150'});
 assert.equal(p.mean[1],50);assert.equal(p.mean[11],100);assert.equal(p.n,2);
 assert(p.lo.every(v=>v==null||v>=0));assert(p.hi.every(v=>v==null||v<=100));
});
test('matched cohort excludes role changes and nodes without comparable loaded capture',()=>{
 const run={matched_nodes:[1,2,202],nodes:[{id:1,role:'super',slots:[1]},{id:2,role:'super',slots:[1]},{id:200,role:'home',slots:[1]},{id:201,role:'home',slots:[1]},{id:202,role:'home',slots:[1]}]};
 assert.deepEqual(S.cohort(run,'home').map(n=>n.id),[202]);
});
