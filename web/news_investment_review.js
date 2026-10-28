(function(root){
'use strict';
const labels={KEEP:'沿用原策略',PAUSE_BUY:'暂停新增',REDUCE_BUY:'减少新增',REDUCE_HOLDING:'减少持仓',EXIT:'退出持仓',ABSTAIN:'证据不足，未作判断'};
function binding(state){return {account_revision:state.account?.revision,target_id:state.target?.target_id,proposal_id:state.target?.proposal_id??null};}
function snapshot(state){return JSON.stringify([binding(state),state.account?.holdings,state.account?.available_cash,state.daily]);}
function safeUrl(value){try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)?u.href:null;}catch{return null;}}
function localTime(value){const date=new Date(value);return Number.isFinite(date.getTime())?date.toLocaleString('zh-CN',{hour12:false})+'（本地时间）':'未记录';}
function eventHealthText(result, labels, currentTime){
 const failed=(Array.isArray(result.source_status)?result.source_status:[]).filter(row=>row?.status!=='LIST_OK');
 const tickers=[...new Set(failed.map(row=>row?.ticker).filter(value=>typeof value==='string'&&/^[A-Z0-9.^-]{1,16}$/.test(value)))];
 const checked=Date.parse(result.checked_at),workerErrorAt=Date.parse(result.last_worker_error?.at);
 const currentError=Number.isFinite(workerErrorAt)&&(!Number.isFinite(checked)||workerErrorAt>=checked);
 let summary;
 if(result.enabled!==true)summary='新事件发现已关闭';
 else if(result.worker_alive===false||result.continuous_monitoring===false)summary='后台未运行，无法持续发现新消息';
 else if(result.worker_alive!==true||result.continuous_monitoring!==true)summary='后台运行状态未确认';
 else if(currentError)summary='最近检查失败，无法确认新稿';
 else if(failed.length)summary=(result.status!=='NO_NEW_TIMELY_BODY'&&labels[result.status]?labels[result.status]+' · ':'')+'来源检查未完成'+(tickers.length?'（'+tickers.join('、')+'）':'')+'，不能确认没有新稿';
 else summary=labels[result.status]||'等待事件校验';
 const conflict=publicationConflictText(result);
 if(conflict&&result.status!=='WAIT_PUBLICATION_TIME_CONFLICT')summary+=' · '+conflict;
 else if(conflict&&result.enabled===true&&result.worker_alive===true&&result.continuous_monitoring===true&&!currentError&&!failed.length)summary=conflict;
 summary+=' · 最近检查 '+localTime(result.checked_at);
 if(Number.isFinite(checked)&&currentTime>=checked)summary+='（距今 '+ageText((currentTime-checked)/1000)+'）';
 if(result.last_worker_error?.at)summary+=' · 曾发生后台错误 '+localTime(result.last_worker_error.at);
 if(result.unsupported_tickers?.length)summary+=' · 部分股票尚无来源覆盖';
 return summary+' · 不自动下单';
}
function publicationConflictText(result){
 const rows=Array.isArray(result?.publication_conflicts)?result.publication_conflicts:[];
 if(!rows.length)return result?.status==='WAIT_PUBLICATION_TIME_CONFLICT'?'消息发布时间存在冲突，尚未形成及时 AI 意见':'';
 const tickers=[...new Set(rows.map(row=>row?.ticker).filter(t=>typeof t==='string'&&/^[A-Z0-9.^-]{1,16}$/.test(t)))].slice(0,12);
 return (tickers.length?tickers.join('、')+'：':'对应消息：')+'发布时间存在冲突，尚未形成及时 AI 意见';
}
function eventTiming(proposal){const t=proposal?.timeliness;return t?.mode==='EVENT_SOURCE_PREANALYSIS_FINALIZED'&&(Date.parse(t.source_discovered_at)<Date.parse(t.first_execution_window?.not_before))?'盘前已发现 · 首个交易窗口复核':'新事件发现后复核';}
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
function exactAmount(value){
 if(typeof value!=='string'&&typeof value!=='number')return null;
 const parts=String(value).split('/');if(parts.length>2||parts.some(x=>!x.trim()))return null;
 const amount=Number(parts[0])/(parts.length===2?Number(parts[1]):1);return Number.isFinite(amount)?amount:null;
}
function money(value){const amount=exactAmount(value);return amount===null?'待核验':'$'+amount.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});}
const riskReasons={WAIT_NEW_QUOTES_REQUIRED:'等待新报价，暂不提供挂单价格',EXISTING_OPEN_ORDERS:'已有未完成挂单，先核对成交或撤单',WAIT_CASH_NO_SELL_PROCEEDS_ASSUMED:'可用现金不足，未成交卖款不计入',WAIT_PENDING_RECONCILIATION:'已有未完成挂单，先核对成交或撤单',NO_ADMITTED_AI_OPINION:'证据不足，未形成 AI 风险方案',REVIEW_EXPIRED:'方案已过期，请重新复核'};
function riskView(proposal,sid,now){
 const reviewRow=proposal?.rows?.find(r=>r.security_id===sid),plan=proposal?.risk_plan;
 if(!reviewRow)return {status:'WAIT',message:'未复核，不代表无风险',orders:[]};
 if(reviewRow.action==='ABSTAIN'||reviewRow.reviewed===false)return {status:'ABSTAIN',message:'证据不足，未作判断；原策略见左侧',orders:[]};
 if(!plan)return {status:'WAIT',message:'尚未生成风险方案报价',orders:[]};
 const bound=plan.schema==='NEWS_AI_RISK_PLAN_V1'&&plan.review_id===proposal.review_id&&plan.executable===false&&plan.orders_created===false&&plan.account_mutated===false&&['account_revision','target_id','proposal_id'].every(k=>plan.original_binding?.[k]===proposal.original_binding?.[k]);
 const valid=bound&&Date.parse(proposal.review_valid_until)>now;
 if(!valid)return {status:'WAIT',message:'方案已过期或绑定不可确认，请重新复核',orders:[]};
 if(plan.status!=='READY')return {status:plan.status==='ABSTAIN'?'ABSTAIN':'WAIT',message:riskReasons[plan.reason]||'等待方案校验，暂不提供挂单价格',orders:[],reason:plan.reason};
 if(!Number.isFinite(Date.parse(plan.valid_until))||Date.parse(plan.valid_until)<=now)return {status:'WAIT',message:'方案报价已过期，请重新复核',orders:[]};
 const row=plan.rows?.find(r=>r.security_id===sid);
 if(!row||row.action!==reviewRow.action||row.held_quantity!==reviewRow.held_quantity||row.proposed_target_quantity!==reviewRow.proposed_target_quantity||!Number.isInteger(row.planned_target_quantity)||row.planned_target_quantity<0||row.planned_target_quantity>reviewRow.original_target_quantity||row.planned_target_quantity>reviewRow.proposed_target_quantity||row.original_target_quantity!==reviewRow.original_target_quantity)return {status:'WAIT',message:'方案数量待核验',orders:[]};
 const orders=(plan.candidate_orders||[]).filter(o=>o.security_id===sid);
 const gap=row.planned_target_quantity-row.held_quantity;
 const validOrders=orders.every(o=>['BUY','SELL'].includes(o.side)&&Number.isInteger(o.quantity)&&o.quantity>0&&exactAmount(o.limit_price)>0&&(o.side==='BUY'?gap>0:gap<0))&&orders.reduce((total,o)=>total+o.quantity,0)<=Math.abs(gap);
 const cash=plan.cash;
 if(!validOrders||!cash||cash.sell_proceeds_assumed!==false||exactAmount(cash.spendable_cash)===null||exactAmount(cash.new_buy_cash_required)===null||exactAmount(cash.spendable_cash)<0||exactAmount(cash.new_buy_cash_required)<0||exactAmount(cash.new_buy_cash_required)>exactAmount(cash.spendable_cash))return {status:'WAIT',message:'方案报价或现金校验未通过',orders:[]};
 return {status:'READY',orders,row,cash,valid_until:plan.valid_until,waiting_cash:(plan.waiting_cash||[]).filter(r=>r.security_id===sid),constraints:(plan.constraints||[]).filter(r=>r.security_id===sid),message:orders.length?'':gap===0?'本方案无需新增买卖':'等待资金或执行条件，暂无可用委托'};
}
function renderRiskPlan(container,proposal,sid,now){
 const doc=container.ownerDocument,el=(tag,text)=>{const n=doc.createElement(tag);n.textContent=String(text);return n;},v=riskView(proposal,sid,now);
 const box=el('div','');box.className='news-risk-plan';box.appendChild(el('strong','未采用'));
 if(v.message)box.appendChild(el('p',v.message));
 if(v.status==='READY'){
  for(const order of v.orders)box.appendChild(el('p',`${order.side==='SELL'?'卖出':'买入'} ${order.quantity} 股 · 限价 ${money(order.limit_price)}`));
  for(const constraint of v.constraints)box.appendChild(el('p',`有 ${constraint.quantity} 股受原策略可买数量限制，未追加买入。`));
  for(const wait of v.waiting_cash)box.appendChild(el('p',`另有 ${wait.quantity} 股待资金；未成交卖款不计入可用现金。`));
  box.appendChild(el('p',`方案合计：可用现金 ${money(v.cash.spendable_cash)} · 买入占用 ${money(v.cash.new_buy_cash_required)}；不预支卖款。`));
  box.appendChild(el('p',`${v.orders.length?'报价':'方案'}有效至 ${localTime(v.valid_until)}${v.orders.length?'；限价不保证成交。':''}`));
 }
 container.appendChild(box);return v;
}
function renderImpactCell(container,sid,reviewState,opened=new Set(),now=Date.now()){
 const doc=container.ownerDocument,el=(tag,text)=>{const n=doc.createElement(tag);if(text!==undefined)n.textContent=String(text);return n;};
 const row=reviewState?.proposal?.rows?.find(r=>r.security_id===sid);
 if(!row){container.appendChild(el('span',reviewState?.busy?'复核中，原策略仍生效':reviewState?.status?.includes('过期')?'复核已过期，待更新':'未复核，不代表无风险'));return;}
 if(row.reviewed!==false&&row.action!=='ABSTAIN')container.appendChild(el('span',labels[row.action]||'未识别意见'));
 renderRiskPlan(container,reviewState.proposal,sid,now);
 const old=(row.evidence||[]).some(e=>Number.isFinite(Date.parse(e.published_at))&&(now-Date.parse(e.published_at))/1000>3600);
 if(reviewState?.proposal?.timeliness?.mode==='EVENT_SOURCE_PREANALYSIS_FINALIZED')container.appendChild(el('p',eventTiming(reviewState.proposal)+' · 未验证提前避跌'));else if(old)container.appendChild(el('p','历史背景，非即时预警'));
 const details=el('details'),summary=el('summary','依据');details.className='news-impact-details';details.open=opened.has(sid);details.addEventListener('toggle',()=>{details.open?opened.add(sid):opened.delete(sid);});details.appendChild(summary);
 details.appendChild(el('p',row.reason||'未提供理由'));
 if(row.reviewed!==false&&row.action!=='ABSTAIN'&&row.proposed_target_quantity!==undefined)details.appendChild(el('p',`风险目标意见：${row.proposed_target_quantity} 股；原 V27 方案仍单独保留。`));
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
function mount(container,{fetch:request=root.fetch?.bind(root),now=()=>Date.now(),setTimer=setTimeout,clearTimer=clearTimeout,pollInterval=2000,maxPolls=180,onComplete=()=>null,compact=false,manualButton=true,onReviewChange=()=>{}}={}){
 const doc=container.ownerDocument,el=(tag,text)=>{const n=doc.createElement(tag);if(text!==undefined)n.textContent=String(text);return n;};
 const card=el('section'),title=el('h3','AI 投资复核'),note=el('p','可按需复核，或开启持仓新事件发现。尚未验证能在价格变动前捕捉消息。原策略继续生效，复核不会下单或修改策略。'),button=el('button',compact?'AI新闻复核':'复核当前建议'),status=el('p'),body=el('div');button.type='button';button.title='按需采集与复核，不持续监控；不会修改正式买卖动作或下单。';
 for(const node of (compact?(manualButton?[button,status]:[status]):[title,note,button,status,body]))card.appendChild(node);container.replaceChildren(card);
 let state={},proposal=null,key='',generation=0,disposed=false,busy=false,timer=null,expiry=null,message='',activeJob=null;
 let flight=null,flightTimer=null,pendingIntent=null;
 const eventButton=el('button','开启新事件发现'),eventStatus=el('span','新事件发现未开启');eventButton.type='button';card.appendChild(eventButton);card.appendChild(eventStatus);
 if(compact){card.className='daily-news-compact';button.className='daily-news-secondary';eventButton.className='daily-news-secondary';status.className='daily-news-status';eventStatus.className='daily-news-status';}
 let eventEnabled=false,eventTimer=null,eventSeenJob=null,eventGeneration=0;
 const eventLabels={DISABLED:'已关闭',WAITING:'等待检查',NO_NEW_TIMELY_BODY:'未发现及时新稿',SOURCE_OPINION_READY:'已解释新稿，等待开盘复核',SOURCE_OPINION_WAIT_FIRST_OPEN:'源意见已保存，等待首个开盘',ANALYZING_PUBLIC_SOURCES:'正在解释新稿',REVIEW_RUNNING:'正在重新验价复核',REVIEW_COMPLETE:'新事件复核完成',ABSTAIN:'本轮未形成意见',WAIT_SHARED_MODEL_BUDGET:'等待共享预算',WAIT_SOURCE_RECONFIRMATION:'等待来源重新确认',WAIT_PUBLICATION_TIME_CONFLICT:'等待消息时间核验'};
 async function eventPoll(){
  if(disposed)return;const eventToken=eventGeneration;
  try{const result=await json('/api/news/events/status');if(disposed||eventToken!==eventGeneration)return;eventEnabled=result.enabled===true;eventButton.textContent=eventEnabled?'关闭新事件发现':'开启新事件发现';eventStatus.textContent=eventHealthText(result,eventLabels,now());
   if(eventEnabled&&result.job_id&&result.job_id!==eventSeenJob&&!busy&&!flight&&!pendingIntent&&view(state,proposal,now()).ready){const token=generation;const job=await json('/api/news/investment-review/job?job_id='+encodeURIComponent(result.job_id));if(!disposed&&token===generation&&eventToken===eventGeneration&&eventEnabled&&!flight&&!pendingIntent&&job.status==='COMPLETE'){eventSeenJob=result.job_id;activeJob=result.job_id;await accept(job,token,0);}}
  }catch{if(!disposed)eventStatus.textContent='新事件状态暂不可确认';}
  if(!disposed){eventTimer=setTimer(eventPoll,15000);eventTimer?.unref?.();}
 }
 async function eventToggle(){
  eventButton.disabled=true;eventGeneration++;const desired=!eventEnabled;
  if(!desired&&proposal?.timeliness?.mode==='EVENT_SOURCE_PREANALYSIS_FINALIZED'){generation++;cancel();proposal=null;busy=false;activeJob=null;eventSeenJob=null;message='新事件发现已关闭，原策略继续生效';draw();}
  try{await json('/api/news/events/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:desired})});eventEnabled=desired;if(eventTimer!==null)clearTimer(eventTimer);await eventPoll();}
  catch{eventStatus.textContent='开关未确认，请重试';}
  finally{if(!disposed)eventButton.disabled=false;}
 }

 eventButton.addEventListener('click',eventToggle);eventPoll();

 function cancel(){if(timer!==null)clearTimer(timer);if(expiry!==null)clearTimer(expiry);timer=expiry=null;}
 function draw(){
  if(disposed)return;const v=view(state,proposal,now());const displayStatus=compact&&!manualButton?(message||v.status).replace(/请重新复核|待重新复核/g,'待更新'):(message||v.status);onReviewChange({proposal:v.valid?structuredClone(proposal):null,status:displayStatus,busy});button.disabled=busy||!v.ready;status.textContent=(compact&&!manualButton?'AI 新闻：':'')+displayStatus;body.replaceChildren();
  for(const row of (compact?[]:v.rows).slice(0,12)){
   const box=el('div');box.appendChild(el('strong',row.ticker||row.security_id));
   box.appendChild(el('p',`原策略目标 ${row.original_target_quantity??'—'} 股 → AI ${labels[row.action]||'未识别动作'}${row.reviewed===false?'（未准入）':''}`));
   box.appendChild(el('p',row.reason||'未提供理由'));
   box.appendChild(el('p','反证：'+(Array.isArray(row.counterevidence)?row.counterevidence.join('；'):row.counterevidence||'未提供，不能视为没有反证')));
   box.appendChild(el('p','不确定性：'+((Array.isArray(row.uncertainty)?row.uncertainty.join('；'):row.uncertainty)||'未提供，不能视为没有不确定性')));
   if(row.reviewed!==false&&row.proposed_target_quantity!==undefined)box.appendChild(el('p',`复核建议目标 ${row.proposed_target_quantity} 股（未写入策略）`));
   renderRiskPlan(box,proposal,row.security_id,now());
   const evidence=Array.isArray(row.evidence)?row.evidence:[];
   for(const group of evidenceGroups(evidence)){
    const item=group.item;
    const url=safeUrl(item.url||item.source_url);const line=el('p');
    if(url){const a=el('a',item.source||item.title||'查看来源');a.href=url;a.target='_blank';a.rel='noopener noreferrer';line.appendChild(a);}
    const measuredAge=(now()-Date.parse(item.published_at))/1000;
    const publishedAge=Number.isFinite(measuredAge)?Math.max(Number.isFinite(item.publication_age_seconds)?item.publication_age_seconds:0,measuredAge):item.publication_age_seconds;
    line.appendChild(el('span',` 距发布 ${ageText(publishedAge)} · 发布 ${localTime(item.published_at)} · 本次采集 ${localTime(item.observed_at||item.fetched_at||item.collected_at)} · ${proposal.timeliness?.cached?'复用此前分析':'分析完成'} ${localTime(item.analyzed_at||proposal.timeliness?.analysis_completed_at)}`));
    if(Number.isFinite(item.discovery_delay_seconds))line.appendChild(el('span',` · 发布至本次采集 ${ageText(item.discovery_delay_seconds)}`));
    if(proposal.timeliness?.mode==='EVENT_SOURCE_PREANALYSIS_FINALIZED')line.appendChild(el('strong',' '+eventTiming(proposal)+' · 未验证提前避跌'));else if(publishedAge>3600)line.appendChild(el('strong',' 历史背景，不是即时预警'));box.appendChild(line);
    for(const quote of group.quotes)box.appendChild(el('blockquote',quote));
   }body.appendChild(box);
  }
  if(proposal?.analyzed_at)body.appendChild(el('p',`分析时间 ${localTime(proposal.analyzed_at)}`));
  if(proposal?.timeliness&&typeof proposal.timeliness==='object'){const t=proposal.timeliness;body.appendChild(el('p',`按需采集 · 请求 ${localTime(t.requested_at)} · ${t.cached?'复用此前分析':'分析完成'} ${localTime(t.analysis_completed_at)}${t.cached?' · 本次重新校验 '+localTime(t.revalidated_at||proposal.review_created_at):''}${Number.isFinite(t.total_seconds)?' · 用时 '+Math.round(t.total_seconds)+' 秒':''}`));}
  if(proposal)body.appendChild(el('p',`复核时间 ${localTime(proposal.review_created_at)} · 有效至 ${localTime(proposal.review_valid_until)}`));
  if(expiry!==null)clearTimer(expiry);expiry=null;
  const deadlines=[proposal?.review_valid_until,proposal?.risk_plan?.valid_until].map(Date.parse).filter(t=>Number.isFinite(t)&&t>now());const wait=(deadlines.length?Math.min(...deadlines):NaN)-now();if(wait>0){expiry=setTimer(draw,Math.min(wait,2147483647));expiry?.unref?.();}else if(proposal&&Date.parse(proposal.review_valid_until)<=now()&&timer!==null){clearTimer(timer);timer=null;}
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
 // Transport lifetime is independent of display invalidation. A cash refresh must
 // retire old opinions immediately, but must not lose an already submitted job.
 function transportFailure(){
  flight=null;pendingIntent=null;busy=false;proposal=null;
  message='复核连接未确认，原策略未改变；请稍后更新现金并查看建议';draw();
 }
 async function receiveFlight(result,current,count){
  if(disposed||flight!==current)return;
  if(result.error==='ANALYSIS_ALREADY_RUNNING')current.collision=true;
  if(['RUNNING','QUEUED','STARTED'].includes(result.status)&&typeof result.job_id==='string'){
   if(count>=maxPolls){transportFailure();return;}
   flightTimer=setTimer(async()=>{flightTimer=null;
    try{await receiveFlight(await json('/api/news/investment-review/job?job_id='+encodeURIComponent(result.job_id)),current,count+1);}
    catch{if(!disposed&&flight===current)transportFailure();}
   },pollInterval);return;
  }
  flight=null;
  const queued=pendingIntent;pendingIntent=null;
  if(queued&&queued.token===generation&&queued.key===key&&view(state,null,now()).ready){
   await launch({...queued,handoffs:1});return;
  }
  if(queued||current.token!==generation||current.key!==key){
   busy=false;proposal=null;message='建议已变化或暂不可用，请更新现金并查看建议';draw();return;
  }
  // A 409 can attach us to an older server job. Allow one handoff only; quota
  // failures and another collision remain visible rather than retrying forever.
  if(current.collision&&current.handoffs===0){
   await launch({...current,collision:false,handoffs:1});return;
  }
  await accept(result,current.token,count);
 }
 async function launch(intent){
  if(disposed||flight||intent.token!==generation||intent.key!==key)return;
  flight=intent;busy=true;message='正在提交复核';draw();
  const b=binding(state);
  try{await receiveFlight(await json('/api/news/investment-review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_revision:b.account_revision,target_id:b.target_id,expected_proposal_id:b.proposal_id})}),intent,0);}
  catch{if(!disposed&&flight===intent)transportFailure();else if(!disposed&&intent.token===generation){busy=false;proposal=null;message='本次复核已失效，原策略未改变';draw();}}
 }
 async function start(){
  if(disposed||!view(state,proposal,now()).ready)return;
  if(flight&&flight.token===generation&&flight.key===key&&!pendingIntent)return;
  const token=++generation;cancel();activeJob=null;busy=true;proposal=null;
  const intent={token,key,handoffs:0,collision:false};
  if(flight){pendingIntent=intent;message='等待上一轮结束，随后复核最新建议';draw();return;}
  await launch(intent);
 }
 button.addEventListener('click',start);draw();
 return {update(next){if(disposed)return;const nextKey=snapshot(next);if(nextKey!==key){generation++;cancel();pendingIntent=null;activeJob=null;busy=false;proposal=null;message=key?'账户、目标或报价已变化，请重新复核':'';key=nextKey;}state=structuredClone(next);draw();},dispose(){disposed=true;generation++;cancel();pendingIntent=null;if(flightTimer!==null)clearTimer(flightTimer);if(eventTimer!==null)clearTimer(eventTimer);eventButton.removeEventListener('click',eventToggle);button.removeEventListener('click',start);},elements:{button,status,body},start,isBusy:()=>busy};
}
const api={eventHealthText,publicationConflictText,riskView,renderRiskPlan,money,eventTiming,renderImpactCell,mount,view,binding,snapshot,safeUrl,localTime,ageText,evidenceGroups};if(typeof module!=='undefined'&&module.exports)module.exports=api;root.NewsInvestmentReview=api;
})(typeof window!=='undefined'?window:globalThis);
