// Automated DOM harness, not a visual browser test. Exercises the real app.
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('node:assert/strict');
const ROOT=process.env.DEVNET_SITE_ROOT?path.resolve(process.env.DEVNET_SITE_ROOT):path.resolve(__dirname,'../web'),elements=new Map(),downloads=[],blobs=[];
const createURL=URL.createObjectURL;URL.createObjectURL=blob=>{blobs.push(blob);return createURL(blob);};
class Element{
 constructor(id){this.id=id;this.value='';this.checked=false;this.hidden=false;this.listeners={};this.textContent='';this._html='';this.attributes={};}
 set innerHTML(value){this._html=value;discover(value);if(value.includes('<option')){const m=value.match(/<option value="([^"]*)"[^>]*selected/)||value.match(/<option value="([^"]*)"/);if(m)this.value=m[1];}}
 get innerHTML(){return this._html;}
 addEventListener(type,fn){this.listeners[type]=fn;}
 dispatch(type){return this.listeners[type]?.({clientX:300});}
 querySelector(){return new Element('svg');}
 setAttribute(k,v){this.attributes[k]=v;}
 getBoundingClientRect(){return {left:0,width:1000};}
 click(){if(this.download)downloads.push(this.download);return this.dispatch('click');}
}
function discover(html){for(const m of html.matchAll(/<([\w-]+)\b([^>]*\bid="([^"]+)"[^>]*)>/g)){const el=elements.get(m[3])||new Element(m[3]);el.checked=/\bchecked\b/.test(m[2]);elements.set(m[3],el);if(m[1]==='select'){const start=m.index+m[0].length,end=html.indexOf('</select>',start);if(end>=0){const contents=html.slice(start,end),v=contents.match(/<option value="([^"]*)"[^>]*selected/)||contents.match(/<option value="([^"]*)"/);el._html=contents;if(v)el.value=v[1];}}}}
discover(fs.readFileSync(path.join(ROOT,'index.html'),'utf8'));
global.window={};global.document={getElementById:id=>{assert(elements.has(id),'missing element '+id);return elements.get(id);},createElement:tag=>new Element(tag)};
global.fetch=async file=>{const buf=fs.readFileSync(path.join(ROOT,file));return new Response(file.startsWith('detail-staggered-')?require('node:zlib').gunzipSync(buf):buf);};
vm.runInThisContext(fs.readFileSync(path.join(ROOT,'data.js'),'utf8'));vm.runInThisContext(fs.readFileSync(path.join(ROOT,'bandwidth.js'),'utf8'));require(path.join(ROOT,'stats.js'));
window.DevnetStats=global.DevnetStats;vm.runInThisContext(fs.readFileSync(path.join(ROOT,'app.js'),'utf8'));
const el=id=>elements.get(id),change=(id,value)=>{el(id).value=value;el(id).dispatch('change');};
async function waitDetail(){for(let i=0;i<200;i++){if(el('explorer-status').textContent.includes('fully captured'))return;await new Promise(r=>setTimeout(r,10));}throw Error('slot detail did not load: '+el('detail-caption').textContent);}
(async()=>{
 await waitDetail();
 const data=window.DEVNET_DATA;
 assert.equal((el('run-cards').innerHTML.match(/class="run-card"/g)||[]).length,3);
 assert(!el('run-cards').innerHTML.includes('NOT CAPTURED'));assert(!el('integrity').innerHTML.includes('baseline'));
 assert.equal(el('metric').value,'rpc');assert.equal(el('layout').value,'objects');assert.equal(el('smoothing').value,'0');
 assert(el('comparison-chart').innerHTML.includes('Bandwidth (KiB/s / node)'));
 assert(el('chart-caption').textContent.includes('Raw 100 ms bins'));
 assert.equal((el('comparison-chart').innerHTML.match(/class="object-run"/g)||[]).length,3);
 for(const name of ['FFG votes','Goldfish head votes','FFG aggregates','PTC votes','Data columns','Beacon blocks','Execution payload'])assert(el('legend').innerHTML.includes(name),name);
 if(process.env.DEVNET_CAPTURE_OVERVIEW)fs.writeFileSync(process.env.DEVNET_CAPTURE_OVERVIEW,el('comparison-chart').innerHTML);
 for(const run of data.runs.filter(r=>!r.historical))for(const cohort of ['all','super','home'])for(const direction of ['recv','send','drop'])for(const component of ['total','publish','partial','control','overhead']){
  const opts={metric:'rpc',cohort,direction,component,family:'all',band:'none'};
  const parts=window.DevnetStats.topicProfiles(run,opts,window.DEVNET_BANDWIDTH),total=window.DevnetStats.profile(run,opts);
  // Original per-slot byte/exposure caches were rounded to five decimals.
  for(let b=0;b<120;b++)assert(Math.abs(parts.reduce((s,p)=>s+(p.mean[b]||0),0)-(total.mean[b]||0))<1e-6+Math.abs(total.mean[b]||0)*1e-7,`topic bandwidth reconciliation ${run.id}/${cohort}/${direction}/${component}/${b}`);
 }
 change('layout','totals');assert.equal((el('comparison-chart').innerHTML.match(/<path /g)||[]).length,3);
 change('layout','objects');change('metric','ssz');
 change('smoothing','0');assert(el('chart-caption').textContent.includes('raw 100 ms'));
 change('smoothing','150');change('layout','totals');assert(el('comparison-chart').innerHTML.includes('<path'));change('layout','objects');
 for(const run of data.runs.filter(r=>!r.historical)){
  const opts={metric:'ssz',cohort:'all',kind:'all',timing:'0',transport:'all',band:'none',smoothing:'150'};
  const parts=window.DevnetStats.objectProfiles(run,opts,data.kinds.length),total=window.DevnetStats.profile(run,opts);
  const sum=xs=>xs.reduce((a,b)=>a+(b||0),0);
  assert(Math.abs(parts.reduce((s,p)=>s+sum(p.mean),0)-sum(total.mean))<1e-7);
  for(const n of window.DevnetStats.cohort(run))assert(n.profiles.filter(p=>p[0]===0).every(p=>p[8]===0));
 }
 assert.deepEqual(data.matched_nodes,[1,2,202]);
 assert.deepEqual(data.runs.filter(r=>!r.historical).map(r=>r.default_ranges),[[[333,379]],[[580,643],[684,707]],[[251,274],[284,370]]]);
 for(const r of data.runs.filter(r=>!r.historical)){
  assert.deepEqual(window.DevnetStats.cohort(r).map(n=>n.id),[1,2,202]);
  assert.deepEqual(window.DevnetStats.cohort(r,'home').map(n=>n.id),[202]);
  assert(r.load.payload_bytes.min>=32768);assert(r.load.tx_count.min>0);
  for(const n of window.DevnetStats.cohort(r))assert.deepEqual(n.slots,r.default_slots);
 }
 assert(el('load-table').innerHTML.includes('333–379'));
 assert(el('detail-caption').textContent.includes('Logged payload:'));
 change('detail-slot','200');assert(el('detail-caption').textContent.includes('0 transactions'));
 assert(el('detail-caption').textContent.includes('Outside the loaded comparison window'));
 change('detail-slot','350');assert(el('detail-caption').textContent.includes('Inside the loaded comparison window'));
 assert(el('comparison-chart').innerHTML.includes('<svg'));assert(el('detail-chart').innerHTML.includes('<svg'));
 assert.equal(data.kinds[data.payload_kind],'Execution payload (applied)');
 for(const r of data.runs.filter(r=>!r.historical))for(const n of window.DevnetStats.cohort(r)){
  const entries=n.profiles.filter(p=>p[0]===0&&p[2]===data.payload_kind);
  assert.equal(entries.reduce((s,p)=>s+p[5],0),r.load.confirmed_payload_slots);
  assert.equal(entries.reduce((s,p)=>s+p[7],0),r.load.payloads.reduce((s,p)=>s+p[2],0));
 }
 change('metric','events');change('transport','1');change('kind',String(data.payload_kind));
 assert.equal(el('transport').value,'all');assert(el('transport-control').hidden);
 assert(el('comparison-chart').innerHTML.includes('<svg'));
 assert(el('chart-caption').textContent.includes('actual SSZ payload bytes'));
 change('metric','ssz');assert(el('comparison-chart').innerHTML.includes('<svg'));
 assert(el('metric-cards').innerHTML.includes('Payload size · median'));
 change('kind','all');
 for(const metric of ['payload-cdf','goldfish-cdf']){
  change('timing','2');change('transport','1');change('kind','0');change('metric',metric);
  assert.equal((el('comparison-chart').innerHTML.match(/<path /g)||[]).length,3);
  assert(el('chart-caption').textContent.includes('upper edges of raw 100 ms bins'));
  for(const control of ['layout','smoothing','object','timing','transport','direction'])assert(el(control+'-control').hidden);
  assert(!el('band-control').hidden);
  const paths=[...el('comparison-chart').innerHTML.matchAll(/<path d="([^"]+)"/g)].map(m=>m[1]);
  for(const path of paths)assert(![...path.matchAll(/[ML]([\d.]+),/g)].some(m=>+m[1]>982),'CDF exceeds the 12 s endpoint');
  for(const run of data.runs.filter(r=>!r.historical))for(const n of window.DevnetStats.cohort(run)){
   const p=window.DevnetStats.receptionProfile(n,{metric});assert.equal(p[0],0);assert.equal(p.at(-1),100);assert(p.every((v,i)=>v>=0&&v<=100&&(!i||v>=p[i-1])));
   if(metric==='payload-cdf')assert.equal(window.DevnetStats.receptionHist(n,7).reduce((s,r)=>s+r[1],0),run.load.confirmed_payload_slots);
  }
  if(process.env.DEVNET_CAPTURE_CDF)fs.writeFileSync(process.env.DEVNET_CAPTURE_CDF+'-'+metric+'.html',el('comparison-chart').innerHTML);
  el('csv').click();const exported=await blobs.at(-1).text();assert(exported.includes('"time_threshold"'));assert(exported.includes('"percent"'));assert(exported.includes('"sample_events_by_node"'));assert(exported.includes(metric==='payload-cdf'?'"1:47;2:47;202:47"':'"Goldfish head votes"'));
 }
 change('timing','0');change('transport','all');change('kind','all');
 for(const metric of ['rpc','events','ssz','delay','payload-cdf','goldfish-cdf'])for(const cohort of ['all','super','home'])for(const band of ['range','none','ci']){change('metric',metric);change('cohort',cohort);change('band',band);assert(el('comparison-chart').innerHTML.includes('<svg'));assert(!el('comparison-chart').innerHTML.includes('NaN'));}
 change('metric','events');change('timing','2');assert(el('comparison-chart').innerHTML.includes('<svg'));change('timing','0');
 el('legacy').checked=true;el('legacy').dispatch('change');assert(el('comparison-chart').innerHTML.includes('Devnet 0'));
 change('detail-run','partial');await waitDetail();change('detail-slot','620');
 for(const metric of ['events','ssz','rpc']){change('detail-metric',metric);assert(el('detail-chart').innerHTML.includes('<svg'));assert(!el('detail-chart').innerHTML.includes('NaN'));}
 change('detail-metric','ssz');assert(el('detail-legend').innerHTML.includes('Execution payload'));
 change('detail-slot','650');assert(el('detail-chart').innerHTML.includes('no complete capture'));el('next').click();assert(el('detail-chart').innerHTML.includes('<svg'));
 el('csv').click();el('detail-csv').click();assert.deepEqual(downloads,['devnet-1-comparison.csv','devnet-1-comparison.csv','devnet-1-comparison.csv','devnet-1-slot.csv']);
 const csv=await blobs[2].text();assert(csv.includes('"333–379"'));assert(csv.includes('"verified"'));
 assert(csv.includes('"not_verified"'));assert(csv.includes('"node_ids"'));assert(csv.includes('2026-10-08T16:36:41Z'));
 for(const run of ['staggered','devnet0']){change('detail-run',run);await waitDetail();change('detail-metric','events');assert(el('detail-chart').innerHTML.includes('<svg'));}
 const result={passed:true,method:'Node DOM harness using real application, real dataset and compressed detail responses; not visual browser QA',comparison_combinations:54,topic_reconciliation_combinations:135,checks:['only the three compared run cards are displayed','payload and Goldfish reception CDF overlays with bounded percent axes','reception CDFs use raw 100 ms upper edges, full denominators and matching payload sample counts','CDF CSV includes percentages, time thresholds and per-node sample counts','default stacked topic bandwidth in KiB/s, raw 100 ms bins and all seven principal object families','three-run bandwidth overlay remains selectable','topic sums match existing RPC profiles for all cohorts, directions and components','shared-scale panels, raw and optional smoothed object views','per-object stacking and smoothing conserve total size','loaded windows and identical three-node cohort','one-node home cohort','actual payload sizes and transaction minima','payload overview count and byte conservation against independent load evidence','payload selector clears incompatible FFG transport filter','payload relative-size overview and slot detail','empty slot explicitly outside comparison','all metric/cohort/band combinations','ignored aggregate view','historical toggle and unverified load label','all four dataset detail loads with gzip and host-decoded JSON','slot gap and next captured slot','all detail metrics','CSV window, cohort and load-status metadata']};
 if(!process.env.DEVNET_SITE_ROOT)fs.writeFileSync(path.resolve(ROOT,'../results/site-validation.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result,null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
