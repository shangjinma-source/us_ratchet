(function(root){
'use strict';
function wrap(fetchImpl){
 const pending=[];
 let scheduled=false;
 const aborted=()=>new DOMException('Chart request aborted','AbortError');
 function finish(item,error,response){
  if(item.done)return;
  item.done=true;
  item.signal?.removeEventListener('abort',item.onAbort);
  if(error)item.reject(error);else item.resolve(response);
 }
 async function send(items){
  const controller=new AbortController();
  for(const item of items)item.group={controller,items};
  try{
   if(items.length===1){
    const item=items[0];
    const response=await fetchImpl(item.url,{...item.options,signal:controller.signal});
    finish(item,null,response);
    return;
   }
   const query=new URLSearchParams(items[0].common);
   for(const identifier of new Set(items.map(item=>item.identifier)))query.append('security_id',identifier);
   const response=await fetchImpl('/api/strategy-display/latest-batch?'+query,
     {signal:controller.signal,cache:'no-store'});
   if(!response.ok){
    for(const item of items)finish(item,null,{ok:false,status:response.status});
    return;
   }
   const data=await response.json();
   const expected=new Set(items.map(item=>item.identifier));
   if(data.status!=='DISPLAY_ONLY'||data.executable!==false||data.proposal_id!==query.get('expected_proposal_id')||
      !Array.isArray(data.charts)||data.charts.length!==expected.size||
      new Set(data.charts.map(chart=>chart.security_id)).size!==expected.size||
      !data.charts.every(chart=>expected.has(chart.security_id)))throw Error('DISPLAY_BATCH_INVALID');
   for(const item of items){
    const chart=data.charts.find(value=>value.security_id===item.identifier);
    finish(item,null,{ok:true,status:200,json:async()=>structuredClone(chart)});
   }
  }catch(error){for(const item of items)finish(item,error);}
 }
 function flush(){
  scheduled=false;
  const groups=new Map();
  for(const item of pending.splice(0)){
   if(item.done)continue;
   const key=JSON.stringify(item.common);
   if(!groups.has(key))groups.set(key,[]);
   groups.get(key).push(item);
  }
  for(const group of groups.values()){
   for(let start=0;start<group.length;start+=8)void send(group.slice(start,start+8));
  }
 }
 return function fetchChart(url,options={}){
  if(typeof url!=='string'||!url.startsWith('/api/strategy-display/latest-bars?')||
     (options.method&&options.method!=='GET'))return fetchImpl(url,options);
  const query=new URLSearchParams(url.slice(url.indexOf('?')+1));
  const keys=[...query.keys()];
  if(new Set(keys).size!==keys.length||!query.get('expected_proposal_id')||!query.get('security_id')||
     keys.some(key=>!['security_id','expected_proposal_id','interval','bars'].includes(key)))return fetchImpl(url,options);
  if(options.signal?.aborted)return Promise.reject(aborted());
  return new Promise((resolve,reject)=>{
   const item={url,options,resolve,reject,signal:options.signal,done:false,identifier:query.get('security_id'),
    common:[['expected_proposal_id',query.get('expected_proposal_id')],['interval',query.get('interval')||'day'],['bars',query.get('bars')||'90']]};
   item.onAbort=()=>{
    finish(item,aborted());
    if(item.group&&item.group.items.every(member=>member.done))item.group.controller.abort();
   };
   item.signal?.addEventListener('abort',item.onAbort,{once:true});
   pending.push(item);
   if(!scheduled){scheduled=true;queueMicrotask(flush);}
  });
 };
}
const api={wrap};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.StrategyDisplayBatchFetch=api;
})(typeof globalThis!=='undefined'?globalThis:this);
