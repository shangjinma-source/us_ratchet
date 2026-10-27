(function(root){
'use strict';
const labels={KEEP:'沿用原策略',PAUSE_BUY:'暂停新增',REDUCE_BUY:'减少新增',REDUCE_HOLDING:'减少持仓',EXIT:'退出持仓',ABSTAIN:'证据不足，未作判断'};
function binding(state){return {account_revision:state.account?.revision,target_id:state.target?.target_id,proposal_id:state.target?.proposal_id??null};}
function snapshot(state){return JSON.stringify([binding(state),state.account?.holdings,state.account?.available_cash,state.daily]);}
function safeUrl(value){try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)?u.href:null;}catch{return null;}}
function localTime(value){const date=new Date(value);return Number.isFinite(date.getTime())?date.toLocaleString('zh-CN',{hour12:false})+'（本地时间）':'未记录';}
function ageText(seconds){return !Number.isFinite(seconds)?'时长未确认':seconds<3600?Math.floor(Math.max(0,seconds)/60)+' 分钟':(Math.max(0,seconds)/3600).toFixed(1)+' 小时';}
function evidenceGroups(items){
 const groups=new Map();
 for(const item of items){
  const key=JSON.stringify([item.source_id||item.url||item.source_url||'',item.source_sha256||'']);
  if(!groups.has(key))groups.set(key,{item,quotes:[]});
  const quotes=groups.get(key).quotes;
  if(typeof item.quote==='string'&&item.quote.trim()&&!quotes.includes(item.quote))quotes.push(item.quote);
 }
 return [...groups.values()];
}
function view(state,proposal,now){
 const b=binding(state),ready=!!(b.account_revision&&b.target_id&&state.daily&&['READY','HOLD'].includes(state.daily.status)&&state.daily.account_revision===b.account_revision&&state.daily.target_id===b.target_id&&(state.daily.proposal_id??null)===b.proposal_id);
 const valid=proposal?.status==='REVIEW_PROPOSAL_ONLY'&&proposal.executable===false&&proposal.orders_created===false&&proposal.original_binding?.account_revision===b.account_revision&&proposal.original_binding?.target_id===b.target_id&&(proposal.original_binding?.proposal_id??null)===b.proposal_id&&Date.parse(proposal.review_valid_until)>now;
 return {ready,valid,rows:valid?(proposal.rows||[]):[],status:!proposal?'尚未复核':proposal.status==='WAIT_RECONCILIATION'?'请先核对持仓':valid?'复核完成 · 独立建议，尚未验证投资效果':'复核已过期，请重新复核'};
}
function renderImpactCell(container,sid,reviewState,opened=new Set(),now=Date.now()){
 const doc=container.ownerDocument,el=(tag,text)=>{const n=doc.createElement(tag);if(text!==undefined)n.textContent=String(text);return n;};
 const row=reviewState?.proposal?.rows?.find(r=>r.security_id===sid);
 if(!row){container.appendChild(el('span',reviewState?.busy?'复核中，原策略仍生效':reviewState?.status?.includes('过期')?'复核已过期，待重新复核':'未复核，不代表无风险'));return;}
 container.appendChild(el('span',row.reviewed===false||row.action==='ABSTAIN'?'证据不足，未作判断':(labels[row.action]||'未识别意见')+' · 投资效果未验证'));
 const old=(row.evidence||[]).some(e=>Number.isFinite(Date.parse(e.published_at))&&(now-Date.parse(e.published_at))/1000>3600);
 if(old)container.appendChild(el('p','历史背景，非即时预警'));
 const details=el('details'),summary=el('summary','依据');details.className='news-impact-details';details.open=opened.has(sid);details.addEventListener('toggle',()=>{details.open?opened.add(sid):opened.delete(sid);});details.appendChild(summary);
 details.appendChild(el('p',row.reason||'未提供理由'));
 if(row.reviewed!==false&&row.action!=='ABSTAIN'&&row.proposed_target_quantity!==undefined)details.appendChild(el('p',`复核目标意见：${row.proposed_target_quantity} 股；未替换正式动作和限价。`));
 for(const [key,label] of [['counterevidence','反证'],['uncertainty','不确定性']])details.appendChild(el('p',label+'：'+(Array.isArray(row[key])&&row[key].length?row[key].join('；'):'未提供，不能视为没有')));
 for(const group of evidenceGroups(Array.isArray(row.evidence)?row.evidence:[])){
  const item=group.item,url=safeUrl(item.url||item.source_url);
  if(url){const link=el('a','查看原文');link.href=url;link.target='_blank';link.rel='noopener noreferrer';details.appendChild(link);}
  details.appendChild(el('p',`发布 ${localTime(item.published_at)} · 本次采集 ${localTime(item.observed_at||item.collected_at)}`));
  for(const quote of group.quotes)details.appendChild(el('blockquote',quote));
 }
 const t=reviewState.proposal.timeliness||{};
 details.appendChild(el('p',`${t.cached?'复用此前分析':'分析完成'} ${localTime(t.analysis_completed_at)}${t.cached?' · 本次重新校验 '+localTime(t.revalidated_at||reviewState.proposal.review_created_at):''} · 复核有效至 ${localTime(reviewState.proposal.review_valid_until)}`));
 container.appendChild(details);
}
function mount(container,{fetch:request=root.fetch?.bind(root),now=()=>Date.now(),setTimer=setTimeout,clearTimer=clearTimeout,pollInterval=2000,maxPolls=180,onComplete=()=>null,compact=false,onReviewChange=()=>{}}={}){
 const doc=container.ownerDocument,el=(tag,text)=>{const n=doc.createElement(tag);if(text!==undefined)n.textContent=String(text);return n;};
 const card=el('section'),title=el('h3','AI 投资复核'),note=el('p','点击后才采集并复核，不持续监控。尚未验证能在价格变动前捕捉消息。原策略继续生效，复核不会下单或修改策略。'),button=el('button',compact?'AI新闻复核':'复核当前建议'),status=el('p'),body=el('div');button.type='button';button.title='按需采集与复核，不持续监控；不会修改正式买卖动作或下单。';
 for(const node of (compact?[button,status]:[title,note,button,status,body]))card.appendChild(node);container.replaceChildren(card);
 let state={},proposal=null,key='',generation=0,disposed=false,busy=false,timer=null,expiry=null,message='',activeJob=null;
 function cancel(){if(timer!==null)clearTimer(timer);if(expiry!==null)clearTimer(expiry);timer=expiry=null;}
 function draw(){
  if(disposed)return;const v=view(state,proposal,now());onReviewChange({proposal:v.valid?structuredClone(proposal):null,status:message||v.status,busy});button.disabled=busy||!v.ready;status.textContent=message||v.status;body.replaceChildren();
  for(const row of (compact?[]:v.rows).slice(0,12)){
   const box=el('div');box.appendChild(el('strong',row.ticker||row.security_id));
   box.appendChild(el('p',`原策略目标 ${row.original_target_quantity??'—'} 股 → AI ${labels[row.action]||'未识别动作'}${row.reviewed===false?'（未准入）':''}`));
   box.appendChild(el('p',row.reason||'未提供理由'));
   box.appendChild(el('p','反证：'+(Array.isArray(row.counterevidence)?row.counterevidence.join('；'):row.counterevidence||'未提供，不能视为没有反证')));
   box.appendChild(el('p','不确定性：'+((Array.isArray(row.uncertainty)?row.uncertainty.join('；'):row.uncertainty)||'未提供，不能视为没有不确定性')));
   if(row.reviewed!==false&&row.proposed_target_quantity!==undefined)box.appendChild(el('p',`复核建议目标 ${row.proposed_target_quantity} 股（未写入策略）`));
   const evidence=Array.isArray(row.evidence)?row.evidence:[];
   for(const group of evidenceGroups(evidence)){
    const item=group.item;
    const url=safeUrl(item.url||item.source_url);const line=el('p');
    if(url){const a=el('a',item.source||item.title||'查看来源');a.href=url;a.target='_blank';a.rel='noopener noreferrer';line.appendChild(a);}
    const measuredAge=(now()-Date.parse(item.published_at))/1000;
    const publishedAge=Number.isFinite(measuredAge)?Math.max(Number.isFinite(item.publication_age_seconds)?item.publication_age_seconds:0,measuredAge):item.publication_age_seconds;
    line.appendChild(el('span',` 距发布 ${ageText(publishedAge)} · 发布 ${localTime(item.published_at)} · 本次采集 ${localTime(item.observed_at||item.fetched_at||item.collected_at)} · ${proposal.timeliness?.cached?'复用此前分析':'分析完成'} ${localTime(item.analyzed_at||proposal.timeliness?.analysis_completed_at)}`));
    if(Number.isFinite(item.discovery_delay_seconds))line.appendChild(el('span',` · 发布至本次采集 ${ageText(item.discovery_delay_seconds)}`));
    if(publishedAge>3600)line.appendChild(el('strong',' 历史背景，不是即时预警'));box.appendChild(line);
    for(const quote of group.quotes)box.appendChild(el('blockquote',quote));
   }body.appendChild(box);
  }
  if(proposal?.analyzed_at)body.appendChild(el('p',`分析时间 ${localTime(proposal.analyzed_at)}`));
  if(proposal?.timeliness&&typeof proposal.timeliness==='object'){const t=proposal.timeliness;body.appendChild(el('p',`按需采集 · 请求 ${localTime(t.requested_at)} · ${t.cached?'复用此前分析':'分析完成'} ${localTime(t.analysis_completed_at)}${t.cached?' · 本次重新校验 '+localTime(t.revalidated_at||proposal.review_created_at):''}${Number.isFinite(t.total_seconds)?' · 用时 '+Math.round(t.total_seconds)+' 秒':''}`));}
  if(proposal)body.appendChild(el('p',`复核时间 ${localTime(proposal.review_created_at)} · 有效至 ${localTime(proposal.review_valid_until)}`));
  if(expiry!==null)clearTimer(expiry);expiry=null;
  const wait=Date.parse(proposal?.review_valid_until)-now();if(wait>0){expiry=setTimer(draw,Math.min(wait,2147483647));expiry?.unref?.();}else if(proposal&&timer!==null){clearTimer(timer);timer=null;}
 }
 async function json(url,options){const response=await request(url,options);const value=await response.json();if(!response.ok&&!(response.status===409&&value.status==='RUNNING'&&value.job_id)&&response.status!==429)throw Error('REQUEST_FAILED');return value;}
 async function accept(result,token,count){
  if(disposed||token!==generation)return;
  if(typeof result.job_id==='string')activeJob=result.job_id;
  if(result.status==='COMPLETE'&&result.proposal){
   if(!view(state,result.proposal,now()).valid)throw Error('REVIEW_EXPIRED_OR_CHANGED');
   if(proposal?.review_id!==result.proposal.review_id||!proposal){
    const next=onComplete(result.proposal);
    if(disposed||token!==generation)return;
    if(next){state=structuredClone(next);key=snapshot(state);}
   }
   proposal=result.proposal;busy=false;message='';draw();
   if(activeJob&&view(state,proposal,now()).valid){timer=setTimer(async()=>{timer=null;if(disposed||token!==generation||!view(state,proposal,now()).valid)return;try{await accept(await json('/api/news/investment-review/job?job_id='+encodeURIComponent(activeJob)),token,count);}catch{if(!disposed&&token===generation){proposal=null;message='无法确认复核仍有效，请重新复核';draw();}}},15000);timer?.unref?.();}return;}
  if(['RUNNING','QUEUED','STARTED'].includes(result.status)&&typeof result.job_id==='string'&&count<maxPolls){
   message='正在复核，原策略仍然生效';draw();timer=setTimer(async()=>{timer=null;try{await accept(await json('/api/news/investment-review/job?job_id='+encodeURIComponent(result.job_id)),token,count+1);}catch{if(!disposed&&token===generation){busy=false;message='复核读取失败，请稍后重试';draw();}}},pollInterval);return;
  }
  busy=false;proposal=null;const errors={ONE_MINUTE_COOLDOWN:'请间隔一分钟后再复核',DAILY_REVIEW_BUDGET_EXHAUSTED:'本日复核次数已达上限',NO_COMPLETE_CURRENT_SOURCE_BODY:'近期没有可用的完整正文，暂不能复核',REFRESH_ACCOUNT_AND_REVIEW:'账户、目标或消息已变化，请刷新后复核'};message=errors[result.error]||(count>=maxPolls?'等待超时，请稍后重新查看':'本次未形成可用复核，请稍后重试');draw();
 }
 async function start(){
  if(disposed||busy||!view(state,proposal,now()).ready)return;
  const token=++generation,b=binding(state);cancel();activeJob=null;busy=true;proposal=null;message='正在提交复核';draw();
  try{await accept(await json('/api/news/investment-review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_revision:b.account_revision,target_id:b.target_id,expected_proposal_id:b.proposal_id})}),token,0);}
  catch{if(!disposed&&token===generation){busy=false;message='复核未完成，原策略未改变';draw();}}
 }
 button.addEventListener('click',start);draw();
 return {update(next){if(disposed)return;const nextKey=snapshot(next);if(nextKey!==key){generation++;cancel();activeJob=null;busy=false;proposal=null;message=key?'账户、目标或报价已变化，请重新复核':'';key=nextKey;}state=structuredClone(next);draw();},dispose(){disposed=true;generation++;cancel();button.removeEventListener('click',start);},elements:{button,status,body},start};
}
const api={renderImpactCell,mount,view,binding,snapshot,safeUrl,localTime,ageText,evidenceGroups};if(typeof module!=='undefined'&&module.exports)module.exports=api;root.NewsInvestmentReview=api;
})(typeof window!=='undefined'?window:globalThis);
