(function(root){
'use strict';
function create({fetch:request,now=()=>Date.now(),setTimer=setTimeout,clearTimer=clearTimeout,onChange=()=>{}}){
 let disposed=false,busy=false,timer=null,expiry=null,generation=0,data=null;
 const endpoint='/api/news/scheduled-earnings';
 function clear(){if(timer!==null)clearTimer(timer);timer=null;if(expiry!==null)clearTimer(expiry);expiry=null;}
 function notify(){
  if(disposed)return;
  if(expiry!==null)clearTimer(expiry);expiry=null;
  const deadlines=(data?.events||[]).flatMap(e=>[Date.parse(e.scheduled_at),Date.parse(e.observed_at)+86400000]).filter(t=>Number.isFinite(t)&&t>now());
  if(deadlines.length){expiry=setTimer(notify,Math.min(...deadlines)-now());expiry?.unref?.();}
  onChange();
 }
 async function read(token,count=0){
  try{
   const response=await request(endpoint,{cache:'no-store'});
   if(!response.ok)throw Error('SCHEDULE_READ_FAILED');
   const next=await response.json();if(disposed||token!==generation)return;
   data=next;notify();
   if(next.refresh?.status==='RUNNING'&&count<60){timer=setTimer(()=>{timer=null;void read(token,count+1);},2000);timer?.unref?.();}
   else busy=false;
  }catch{if(!disposed&&token===generation){data=null;busy=false;notify();}}
 }
 return {
  load(){if(disposed||busy)return Promise.resolve();busy=true;clear();return read(++generation);},
  async refresh(){
   if(disposed||busy)return;busy=true;clear();const token=++generation;
   try{
    const response=await request(endpoint+'/refresh',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    if(!response.ok&&![409,429].includes(response.status))throw Error('SCHEDULE_REFRESH_FAILED');
    if(!disposed&&token===generation)await read(token);
   }catch{if(!disposed&&token===generation){data=null;busy=false;notify();}}
  },
  render(cell,ticker){
   if(ticker!=='MRNA')return;
   const doc=cell.ownerDocument,node=doc.createElement('div');node.className='scheduled-earnings-note';
   const events=data?.status==='CONTEXT_ONLY'?(data.events||[]).filter(e=>e.ticker===ticker&&e.event_kind==='EARNINGS_CALL'&&e.eligible_as_new_trigger===false&&e.may_refresh_event_window===false&&Date.parse(e.scheduled_at)>now()&&Date.parse(e.observed_at)<=now()&&now()-Date.parse(e.observed_at)<=86400000):[];
   if(events.length){
    const stamp=new Date(events[0].scheduled_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false});
    node.textContent='财报会议：'+stamp+'（北京时间）；非业绩结论';
   }else node.textContent='财报安排未核实';
   cell.appendChild(node);
  },
  dispose(){disposed=true;++generation;clear();data=null;}
 };
}
const api={create};if(typeof module!=='undefined'&&module.exports)module.exports=api;root.NewsScheduledEarnings=api;
})(typeof window!=='undefined'?window:globalThis);
