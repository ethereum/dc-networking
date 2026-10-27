/* Pure descriptive statistics shared by the website and its tests. */
(function(root){'use strict';
function cohort(run,which='all') { return run.nodes.filter(n=>(run.historical||(run.matched_nodes||[]).includes(n.id))&&(which==='all'||n.role===which)&&n.slots.length); }
function quantile(hist,q){const a=hist.filter(x=>x[1]>0).sort((a,b)=>a[0]-b[0]);const n=a.reduce((s,x)=>s+x[1],0);if(!n)return null;let sum=0;for(const [v,c]of a){sum+=c;if(sum>=Math.ceil(n*q))return v;}return null;}
function mean(xs){const a=xs.filter(x=>Number.isFinite(x));return a.length?a.reduce((x,y)=>x+y,0)/a.length:null;}
function bands(arrays,type){if(!arrays.length)return {mean:[],lo:[],hi:[],n:0};const m=arrays[0].length,means=[],lo=[],hi=[];for(let i=0;i<m;i++){const v=arrays.map(a=>a[i]).filter(Number.isFinite),avg=mean(v);means.push(avg);if(!v.length){lo.push(null);hi.push(null);continue;}if(type==='ci'&&v.length===1){lo.push(null);hi.push(null);}else if(type==='ci'&&v.length>1){const t={2:12.706,3:4.303,4:3.182,5:2.776,6:2.571,7:2.447,8:2.365}[v.length]||1.96;const se=Math.sqrt(v.reduce((s,x)=>s+(x-avg)**2,0)/(v.length-1)/v.length);lo.push(Math.max(0,avg-t*se));hi.push(avg+t*se);}else{lo.push(Math.min(...v));hi.push(Math.max(...v));}}return {mean:means,lo,hi,n:arrays.length};}
function eventProfile(n,opts){const a=Array(120).fill(0);let known=0,unknown=0;if(opts.kind==='7'&&!n.payload_instrumented)return Array(120).fill(null);if(!n.slots.length)return a;for(const r of n.profiles){const[mode,bin,kind,origin,transport,count,seats,size]=r;if(mode!==+opts.timing||origin||bin<0||bin>=120)continue;if(opts.kind!=='all'&&kind!==+opts.kind)continue;if(opts.transport!=='all'&&(kind!==0||transport!==+opts.transport))continue;known+=count-r[8];unknown+=r[8];a[bin]+=(opts.metric==='ssz'?size/240:count)/n.slots.length;}return opts.metric==='ssz'&&unknown>0&&known===0?Array(120).fill(null):a;}
function networkProfile(n,opts){const a=Array(120).fill(0),exposure=Array(120).fill(0);for(const r of n.network){const[family,dir,bin,total,,, ,,,ms]=r;if(dir!==opts.direction)continue;if(family==='all')exposure[bin]+=ms;if(family===opts.family)a[bin]+=r[({total:3,publish:4,partial:5,control:6,overhead:7,other:8})[opts.component||'total']];}return a.map((v,i)=>exposure[i]>0?v/exposure[i]*1000/1024:null);}
function delayHist(n,transport='all'){const h=new Map();for(const t of transport==='all'?['0','1']:[transport])for(const[d,c]of n.delays[t]?.hist||[])if(d>=0)h.set(d,(h.get(d)||0)+c);return [...h];}
function delayProfile(n,opts,xmax){const h=delayHist(n,opts.transport).sort((a,b)=>a[0]-b[0]);const total=h.reduce((s,x)=>s+x[1],0);if(!total)return Array(121).fill(null);let j=0,count=0;return Array.from({length:121},(_,i)=>{const x=i*xmax/120;while(j<h.length&&h[j][0]<=x)count+=h[j++][1];return 100*count/total;});}
function receptionKind(metric){return metric==='payload-cdf'?7:metric==='goldfish-cdf'?1:null;}
function receptionHist(n,kind){
 if(kind===7&&!n.payload_instrumented)return [];
 const h=new Map();for(const r of n.profiles)if(r[0]===0&&r[2]===kind&&r[3]===0&&r[5]>0)h.set(r[1],(h.get(r[1])||0)+r[5]);
 return [...h].sort((a,b)=>a[0]-b[0]);
}
function receptionProfile(n,opts){
 const h=receptionHist(n,receptionKind(opts.metric)),total=h.reduce((s,r)=>s+r[1],0);
 if(!total)return Array(121).fill(null);
 let j=0,count=0;
 // At i*100 ms include completed bins only; retain early and late records in
 // the denominator. The 12 s endpoint is not forced to 100 percent.
 return Array.from({length:121},(_,i)=>{while(j<h.length&&h[j][0]<i)count+=h[j++][1];return 100*count/total;});
}
function profile(run,opts,xmax=250){const nodes=cohort(run,opts.cohort),reception=receptionKind(opts.metric)!=null;const arrays=nodes.map(n=>opts.metric==='rpc'?networkProfile(n,opts):opts.metric==='delay'?delayProfile(n,opts,xmax):reception?receptionProfile(n,opts):eventProfile(n,opts));const p=bands(arrays,opts.band);if(reception){p.n=arrays.filter(a=>a.some(Number.isFinite)).length;for(const key of ['lo','hi'])p[key]=p[key].map(v=>v==null?null:Math.max(0,Math.min(100,v)));}return p;}
function smoothProfile(values,sigmaMs=0){if(!sigmaMs)return values.slice();const sigma=sigmaMs/100,radius=Math.ceil(3*sigma),out=values.map(v=>v==null?null:0);for(let i=0;i<values.length;i++){if(values[i]==null)continue;const targets=[];let total=0;for(let j=Math.max(0,i-radius);j<=Math.min(values.length-1,i+radius);j++){if(out[j]==null)continue;const w=Math.exp(-.5*((j-i)/sigma)**2);targets.push([j,w]);total+=w;}for(const[j,w]of targets)out[j]+=values[i]*w/total;}return out;}
function objectProfiles(run,opts,kindCount){return Array.from({length:kindCount},(_,kind)=>{const p=profile(run,{...opts,kind:String(kind),band:'none'});return {...p,kind,raw:p.mean,mean:smoothProfile(p.mean,+opts.smoothing||0)};}).filter(p=>(opts.kind==='all'||p.kind===+opts.kind)&&p.raw.some(v=>v>0));}
function topicProfiles(run,opts,traffic){
 const nodes=cohort(run,opts.cohort),families=['FFG','AC','aggregate','PTC','columns','block','payload','sync','other'];
 const index=new Map((traffic?.rows||[]).filter(r=>r[0]===run.id&&r[3]===opts.direction).map(r=>[[r[1],r[2],r[4]].join('/'),r.slice(5)]));
 const component={total:0,publish:1,partial:2,control:3,overhead:4,other:5}[opts.component||'total'];
 return families.filter(f=>opts.family==='all'||opts.family===f).map(family=>{
  const arrays=nodes.map(n=>Array.from({length:120},(_,b)=>{
   const exposure=index.get([n.id,'all',b].join('/'))?.[6];
   if(!(exposure>0))return null;
   const bytes=(index.get([n.id,family,b].join('/'))?.[component]||0)+(family==='other'?(index.get([n.id,'unattributed',b].join('/'))?.[component]||0):0);
   return bytes/exposure*1000/1024;
  }));
  const p=bands(arrays,opts.band||'none');return {...p,family,raw:p.mean};
 }).filter(p=>p.mean.some(v=>v>0));
}
function rpcRate(n,direction){let bytes=0,ms=0;for(const r of n.network)if(r[0]==='all'&&r[1]===direction){bytes+=r[3];ms+=r[9];}return ms?bytes/ms*1000/1024:null;}
function arrivalQuantile(n,mode,q){return quantile(n.profiles.filter(r=>r[0]===mode&&r[2]===0&&r[3]===0).map(r=>[r[1]*100,r[5]]),q);}
function metrics(run,which){const ns=cohort(run,which);return {n:ns.length,ffg:mean(ns.map(n=>n.profiles.filter(r=>r[0]===0&&r[2]===0&&r[3]===0).reduce((s,r)=>s+r[5],0)/n.slots.length)),arrival:mean(ns.map(n=>arrivalQuantile(n,0,.99))),decision:mean(ns.map(n=>quantile(delayHist(n),.99))),recv:mean(ns.map(n=>rpcRate(n,'recv'))),send:mean(ns.map(n=>rpcRate(n,'send'))),bundle:mean(ns.map(n=>{const p=n.profiles.filter(r=>r[0]===0&&r[2]===0&&r[3]===0),total=p.reduce((s,r)=>s+r[5],0);return total?100*p.filter(r=>r[4]===1).reduce((s,r)=>s+r[5],0)/total:null;}))};}
const api={cohort,quantile,mean,bands,eventProfile,networkProfile,delayHist,delayProfile,receptionKind,receptionHist,receptionProfile,profile,smoothProfile,objectProfiles,topicProfiles,rpcRate,metrics};root.DevnetStats=api;if(typeof module!=='undefined')module.exports=api;
})(globalThis);
