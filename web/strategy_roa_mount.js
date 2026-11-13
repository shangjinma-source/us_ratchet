(function(root){
'use strict';
const controllerApi=typeof module!=='undefined'&&module.exports?require('./strategy_roa_controller.js'):root.StrategyRoaController;
const legacyUi=typeof module!=='undefined'&&module.exports?require('./strategy_daily_controller.js'):root.StrategyDailyController;
function cashText(value){
 const text=String(value);
 if(/^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(text))return text;
 if(!/^\d{1,40}\/[1-9]\d{0,39}$/.test(text))return null;
 const [n,d]=text.split('/').map(BigInt);let remainder=n%d,fraction='';
 for(let i=0;remainder&&i<18;i++){remainder*=10n;fraction+=String(remainder/d);remainder%=d;}
 return remainder?null:String(n/d)+(fraction?'.'+fraction:'');
}
function mount(container,dependencies){
 const {now=()=>Date.now(),setTimer=setTimeout,clearTimer=clearTimeout,onAccountChanged=()=>{},onRecommendedTickers=()=>{},onChange=()=>{},activeStrategy=null,...options}=dependencies;
 const doc=container.ownerDocument,element=(tag,text,cls)=>{const n=doc.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
 const section=element('section',undefined,'strategy-monthly-target'),title=element('h3','今日买卖建议');
 if(activeStrategy?.active===true&&activeStrategy.strategy_kind==='ROA_DEFENSIVE_V1'&&activeStrategy.strategy_epoch===options.expectedEpoch&&activeStrategy.account_id){
  title.appendChild(element('span','ROA · 牛熊切换','active-strategy-label'));
 }
 const cashPanel=element('div',undefined,'daily-cash-panel'),form=element('form',undefined,'monthly-cash-form');
 const label=element('label','当前可用现金 USD'),input=element('input');
 input.name='amount';input.inputMode='decimal';input.autocomplete='off';input.required=true;
 label.appendChild(input);const save=element('button','更新现金并查看建议');save.type='submit';form.appendChild(label);form.appendChild(save);cashPanel.appendChild(form);
 const status=element('div',undefined,'daily-status'),summary=element('div',undefined,'monthly-table-scroll');
 for(const n of [title,cashPanel,status,summary])section.appendChild(n);container.replaceChildren(section);
 const funding=element('details'),fundingTitle=element('summary','券商资金规划'),fundingForm=element('form'),fundingResult=element('p');
 funding.appendChild(fundingTitle);
 funding.appendChild(element('p','转出后汇丰保留至少 1,300 美元，仍可用于汇丰内投资。确认当前余额和免佣额度后计算预算；不转账、不下单。'));
 const fundingInputs={};
 for(const [key,text,value] of [['hsbc','汇丰当前可用现金 USD',''],['usmart','盈立当前可用现金 USD','0'],['other','其他费用预算 USD','25'],['transfer','转账费用预算 USD','0']]){
  const field=element('label',text),control=element('input');control.value=value;control.inputMode='decimal';control.required=true;field.appendChild(control);fundingForm.appendChild(field);fundingInputs[key]=control;
 }
 const quotaLabel=element('label','已核实汇丰本月免费额度用尽'),quota=element('input');quota.type='checkbox';quotaLabel.appendChild(quota);fundingForm.appendChild(quotaLabel);
 for(const [key,text,value] of [['remainingQuota','汇丰剩余免佣交易额度 HKD（用尽可勾选上方）',''],['quotaReserve','为其他交易预留额度 HKD','0']]){
  const field=element('label',text),control=element('input');control.value=value;control.inputMode='decimal';field.appendChild(control);fundingForm.appendChild(field);fundingInputs[key]=control;
 }
 const ownershipLabel=element('label','确认现有持仓全部在汇丰'),ownership=element('input');ownership.type='checkbox';ownership.checked=false;ownershipLabel.appendChild(ownership);fundingForm.appendChild(ownershipLabel);
 const ownershipFields=element('div');fundingForm.appendChild(ownershipFields);const ownershipInputs=new Map();
 let ownershipRevision=null;
 const fundingButton=element('button','确认余额并计算预算');fundingButton.type='submit';fundingForm.appendChild(fundingButton);
 funding.appendChild(fundingForm);funding.appendChild(fundingResult);section.appendChild(funding);
 let fundingGeneration=0,fundingBusy=false,fundingPlan=null,fundingTimer=null;
 const budgetAmount=value=>{if(!/^(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?$/.test(value))throw Error('请填写有效美元金额');return Math.round(Number(value)*100);};
 const fundingSubmit=async event=>{
  event.preventDefault();if(fundingBusy)return;
  const current=controller.getState(),token=++fundingGeneration;
  fundingPlan=null;
  try{
   if(current.busy||current.error||!current.advice?.executable)throw Error('请先刷新有效建议');
   if(!quota.checked){
    if(!fundingInputs.remainingQuota.value)throw Error('请核实并填写汇丰剩余免佣额度，将优先使用汇丰');
    if(budgetAmount(fundingInputs.remainingQuota.value)>25000000)throw Error('剩余免佣额度不能超过 250,000 港币');
    budgetAmount(fundingInputs.quotaReserve.value);
   }
   const brokerPositions=[];
   for(const held of current.account.holdings||[]){
    const text=ownership.checked?'0':ownershipInputs.get(held.security_id)?.value;
    if(typeof text!=='string'||!/^(?:0|[1-9]\d*)$/.test(text))throw Error('请确认现有持仓归属：勾选全部在汇丰，或逐只填写盈立股数');
    const remote=Number(text);
    if(!Number.isSafeInteger(remote)||remote>held.quantity)throw Error('盈立股数不能超过该股票总持股数');
    if(held.quantity-remote)brokerPositions.push({broker:'HSBC',security_id:held.security_id,quantity:held.quantity-remote});
    if(remote)brokerPositions.push({broker:'USMART',security_id:held.security_id,quantity:remote});
   }
   const total=budgetAmount(cashText(current.account.available_cash)),usmart=budgetAmount(fundingInputs.usmart.value),hsbc=budgetAmount(fundingInputs.hsbc.value);
   if(usmart>total)throw Error('盈立余额不能超过总可用现金');
   if(hsbc+usmart!==total)throw Error('两家余额合计与当前总现金不一致，请先在上方更新总现金');
   if(Number(current.account.reserved_cash||0)!==0)throw Error('存在挂单占款，请先核对或完成委托后再确认分账户余额');
   budgetAmount(fundingInputs.other.value);budgetAmount(fundingInputs.transfer.value);
   fundingBusy=true;fundingButton.disabled=true;fundingResult.textContent='正在核对当前账户和建议…';
   const binding=await options.request('/api/strategy-account/broker-cash');
   if(binding.account_revision!==current.account.revision)throw Error('账户已变化，请先刷新');
   const observed=new Date(now()).toISOString();
   const document={account_id:binding.account_id,account_revision:binding.account_revision,transfer_revision:binding.transfer_revision,
    balances:{HSBC:{available_cash:fundingInputs.hsbc.value,reserved_cash:'0',observed_at:observed},USMART:{available_cash:fundingInputs.usmart.value,reserved_cash:'0',observed_at:observed}}};
   await options.request('/api/strategy-account/broker-cash',{event_id:options.eventId?options.eventId():crypto.randomUUID(),document});
   const body={hsbc_cash:(hsbc/100).toFixed(2),usmart_cash:fundingInputs.usmart.value,other_fee_reserve:fundingInputs.other.value,transfer_fee_reserve:fundingInputs.transfer.value,hsbc_waiver_exhausted:!!quota.checked,quota_month:new Date(now()+8*3600000).toISOString().slice(0,7)};
   if(!quota.checked)body.hsbc_quota={account_revision:binding.account_revision,month:body.quota_month,observed_at:observed,remaining_hkd:fundingInputs.remainingQuota.value,hkd_per_usd_budget:'8',turnover_reserve_hkd:fundingInputs.quotaReserve.value};
   if(current.account.holdings?.length)body.broker_holdings={account_revision:current.account.revision,positions:brokerPositions};
   const result=await options.request('/api/strategy-roa/funding-preview',body);
   const latest=controller.getState();
   if(disposed||token!==fundingGeneration)return;
   if(result.status==='QUOTA_RECONFIRM_AFTER_HSBC_SELLS')throw Error('本次有汇丰卖出，请成交后核实剩余免佣额度，再计算买入分配');
   if(latest.busy||latest.error||latest.account?.revision!==result.account_revision||!latest.advice?.executable||latest.advice?.proposal_id!==result.proposal_id)throw Error('账户或建议已变化，请刷新后重新计算');
   if(result.status!=='FUNDING_PLAN_ONLY')throw Error(result.status==='INSUFFICIENT_TOTAL_CASH'?'保留汇丰最低余额后，现金不足以覆盖全部目标；需重新分配买入预算':'当前条件不支持转账预览，请核对账户与建议');
   if(!(Date.parse(result.quote_valid_until)>now()))throw Error('报价已过期，请重新计算');
   fundingPlan=result;
   fundingResult.textContent='本次预算：汇丰买入 '+(result.planned_hsbc_buys||[]).length+' 只，盈立买入 '+result.planned_usmart_buys.length+' 只；转账到账金额 '+legacyUi.dollars(result.proposed_transfer_credit_usd)+'，汇丰买入后预计剩余 '+legacyUi.dollars(result.hsbc_remaining_if_funded_usd)+'。费用预算不代表实际费用，到账后重新核价。';
   if(!quota.checked)fundingResult.textContent+=' 免佣额度按 8 港币/美元保守换算，仅为预算。';
   if(result.budget_reduced)fundingResult.textContent+=' 受资金及费用预算限制，部分目标股数暂不覆盖。';
   const allocation=element('table',undefined,'daily-actions-table'),allocationHead=element('tr');
   for(const text of ['股票','方向','券商','计划 → 预算股数'])allocationHead.appendChild(element('th',text));allocation.appendChild(allocationHead);
   for(const original of result.original_strategy_buys||result.planned_usmart_buys){
    const local=(result.planned_hsbc_buys||[]).find(item=>item.symbol===original.symbol),remote=result.planned_usmart_buys.find(item=>item.symbol===original.symbol);
    const row=element('tr');
    for(const text of [original.symbol,'买入','汇丰 '+String(local?.quantity||0)+' / 盈立 '+String(remote?.quantity||0),String(original.quantity)+' → '+String((local?.quantity||0)+(remote?.quantity||0))])row.appendChild(element('td',text));allocation.appendChild(row);
   }
   for(const sale of result.planned_broker_sells||[]){
    const row=element('tr');for(const text of [sale.symbol,'卖出',sale.broker==='HSBC'?'汇丰':'盈立',String(sale.quantity)])row.appendChild(element('td',text));allocation.appendChild(row);
   }
   if(result.planned_broker_sells?.length)fundingResult.textContent+=' 卖出按持仓归属分配，未成交卖款未计入买入预算；卖出费用另计。';
   fundingResult.appendChild(allocation);
   if(fundingTimer!==null)clearTimer(fundingTimer);
   fundingTimer=setTimer(()=>{fundingPlan=null;fundingResult.textContent+=' 该预算已过期，仅供参考。';},Math.max(1,Date.parse(result.quote_valid_until)-now()));
  }catch(error){fundingResult.textContent=error.responseBody?.status?'当前无法生成资金预算，请核对条件后重试。':error.message;}
  finally{fundingBusy=false;fundingButton.disabled=false;}
 };
 fundingForm.addEventListener('submit',fundingSubmit);
 const fundingEdited=()=>{fundingGeneration++;fundingPlan=null;if(fundingTimer!==null){clearTimer(fundingTimer);fundingTimer=null;}fundingResult.textContent='条件已变化，请重新计算。';};
 fundingForm.addEventListener('input',fundingEdited);
 let flowRevision=null,lastRecommended='[]',queuedReload=null,lastReloadKey=null,reloadScheduled=false;
 function flushAccountReload(){if(disposed||reloadScheduled||!queuedReload||!controller||controller.getState().busy)return;reloadScheduled=true;Promise.resolve().then(()=>{reloadScheduled=false;if(disposed||!queuedReload||controller.getState().busy)return;queuedReload=null;void controller.load();});}
 let controller,disposed=false,edited=false,locked=false,timer=null,lastAmount=null,lastRevision=null;
 const reasons={WAIT_CASH_CONFIRMATION:'成交后请填写券商最新可用现金，再更新建议',WAIT_ACCOUNT_RESERVATIONS:'挂单占用与现金不一致，请核对真实挂单及可用现金',PENDING_OPEN:'等待开盘后确认目标股数',PENDING_CLOSE:'等待收盘执行时段',MISSED:'已错过本次执行时段，等待策略下一次判断',WAIT_SIGNAL:'等待有效策略信号',WAIT_FRESH_QUOTE:'等待最新有效报价',READY:'',CASH_RECONCILIATION_REQUIRED:'现金保存结果待核对，请刷新核对，勿重复提交',CASH_NOT_YET_OBSERVED:'尚未确认现金保存结果，请刷新核对，勿重复提交',CASH_NOT_SAVED_ACCOUNT_CHANGED:'现金未保存：账户已变化，请按券商最新可用现金重新提交',ADVICE_QUOTE_EXPIRED:'报价已过期，请刷新建议',ADVICE_REFRESH_REQUIRED:'建议暂未更新，请重试',ACCOUNT_CHANGED_REFRESH_REQUIRED:'账户已变化，请刷新建议'};
 Object.assign(reasons,{WAIT_EXECUTION_ADMISSION:'执行方式尚待确认，当前仅展示计划',CANCEL_THEN_RECALCULATE:'现有挂单与新目标冲突，请先核对挂单',WAIT_CASH:'可用现金不足，等待资金到账后更新',WAIT_CASH_NO_SELL_PROCEEDS_ASSUMED:'可用现金不足；卖出款实际到账后再更新',PENDING_RECONCILIATION_REQUIRED:'已有未完成挂单，请先核对成交或撤单状态',HOLD:'当前持仓已符合目标，无需买卖'});
 Object.assign(reasons,{PENDING_ORDER:'已有未完成挂单，请先核对成交或撤单状态',WAIT_CLOSE_HISTORY_RECONCILIATION:'收盘持仓状态待核对，暂不生成新挂单',SNAPSHOT_UNAVAILABLE:'建议暂未读取成功，请刷新重试'});
 function draw(state){
  if(disposed)return;
  if(state.account?.revision!==ownershipRevision){
   ownership.checked=false;ownershipRevision=state.account?.revision;ownershipFields.replaceChildren();ownershipInputs.clear();
   if(state.account?.holdings?.length)ownershipFields.appendChild(element('p','若分散在两家，请逐只填写盈立持股数；其余计入汇丰。仅用于本次预算，成交后需重新确认。'));
   for(const held of state.account?.holdings||[]){
    const ticker=held.ticker||state.advice?.rows?.find(row=>row.security_id===held.security_id)?.ticker||held.security_id;
    const field=element('label',ticker+' · 总持股 '+held.quantity+' · 盈立股数'),control=element('input');
    control.inputMode='numeric';control.value='';field.appendChild(control);ownershipFields.appendChild(field);ownershipInputs.set(held.security_id,control);
   }
  }
  ownershipLabel.hidden=!state.account?.holdings?.length;
  if(fundingPlan&&(state.busy||state.error||state.account?.revision!==fundingPlan.account_revision||state.advice?.proposal_id!==fundingPlan.proposal_id)){
   fundingPlan=null;fundingGeneration++;if(fundingTimer!==null){clearTimer(fundingTimer);fundingTimer=null;}fundingResult.textContent='账户或建议已更新，请重新计算转账预算。';
  }
  if(timer!==null){clearTimer(timer);timer=null;}
  save.disabled=input.disabled=state.busy||locked;save.textContent=state.busy?'正在更新建议…':'更新现金并查看建议';
  const account=state.account,advice=state.advice;
  const currentHold=!state.busy&&!state.error&&advice?.advice_ready===true&&advice?.status==='HOLD';
  if(!state.busy){const tickers=!state.error&&advice?.advice_ready===true?[...new Set(advice.rows.map(r=>String(r.ticker||'').trim().toUpperCase()).filter(t=>/^[A-Z0-9][A-Z0-9.-]{0,14}$/.test(t)))].sort():[];const key=JSON.stringify(tickers);if(key!==lastRecommended){lastRecommended=key;onRecommendedTickers(tickers);}}
  if(!state.busy&&account?.revision&&flowRevision!==account.revision){flowRevision=account.revision;doc.defaultView?.dispatchEvent(new Event("strategy-account-updated"));}
  const balance=cashText(account?.available_cash);
  if(!edited&&account?.cash_confirmation_valid&&balance!==null)input.value=balance;
  status.textContent=state.busy?'正在读取最新建议…':state.error?(reasons[state.error]||'建议未更新，请刷新核对。'):(reasons[advice?.status]??'等待策略数据');
  const market=advice?.market_signal;
  if(!state.busy&&!state.error&&typeof market?.risk_on==='boolean'&&
     /^\d{4}-\d{2}-\d{2}$/.test(market.signal_date)&&/^\d{4}-\d{2}-\d{2}$/.test(market.execution_session)){
   status.textContent=market.signal_date+' 收盘信号：'+(market.risk_on?'配置股票':'防御持币')+
    ' · '+market.execution_session+' 执行计划（不代表已成交） · '+status.textContent;
  }
  if(advice?.late_execution===true&&!state.busy&&!state.error&&!currentHold)status.textContent=(advice.limit_reference==='SESSION_OPEN'?'延迟执行 · 目标及限价参考今日开盘价，不保证成交。':'延迟执行 · 开盘价计算目标，当前报价计算限价；不代表按开盘回测成交。')+status.textContent;
  if(state.error&&state.cashSaved===true)status.textContent='现金已保存；'+status.textContent;
  const previous=state.lastAdvice;
  const previousDeadline=previous?Math.min(Date.parse(previous.valid_until),Date.parse(previous.quote_valid_until)):NaN;
  const oldReference=previous&&!currentHold&&(!advice?.executable||state.busy||state.error);
  if(previous&&!currentHold&&Number.isFinite(state.lastAdviceAt)){
   status.textContent+=' · 最近有效结果 '+new Date(state.lastAdviceAt).toLocaleTimeString('zh-CN',{hour12:false});
   if(Number.isFinite(previousDeadline))status.textContent+=now()>=previousDeadline?' · 已过期 '+Math.floor((now()-previousDeadline)/1000)+' 秒':' · 有效至 '+new Date(previousDeadline).toLocaleTimeString('zh-CN',{hour12:false});
   if(oldReference)status.textContent+=' · 上次结果仅供参考，需刷新确认';
  }
  const table=element('table',undefined,'daily-actions-table'),head=element('tr');
  for(const text of ['股票','持仓 → 目标','今日建议','原因'])head.appendChild(element('th',text));table.appendChild(head);
  const rows=advice?.rows||previous?.rows||account?.holdings?.map(h=>({security_id:h.security_id,ticker:h.ticker,held:h.quantity}))||[];
  for(const row of rows){
   const tr=element('tr'),actionable=advice?.executable===true&&!state.busy&&!state.error&&['BUY','SELL'].includes(row.side)&&Number.isSafeInteger(row.quantity)&&row.quantity>0;
   tr.appendChild(element('td',row.ticker||row.security_id));
   const currentHolding=account?.holdings?.find(item=>item.security_id===row.security_id);
   const held=Array.isArray(account?.holdings)?currentHolding?.quantity??0:row.held??0;
   tr.appendChild(element('td',String(held)+' → '+(Number.isSafeInteger(row.target_quantity)?row.target_quantity:'待确认')));
   const action=element('td');
   const noAction=!state.busy&&!state.error&&((row.side==='HOLD'&&advice?.executable===true)||(advice?.status==='HOLD'&&row.reason==='HOLD'));
   action.appendChild(element('strong',actionable?(row.side==='BUY'?'买入 ':'卖出 ')+row.quantity+' 股':noAction?'无需操作':'等待'));
   if(actionable)action.appendChild(element('small','限价 '+legacyUi.dollars(row.limit_price),'daily-secondary'));
   const prior=oldReference&&previous.rows.find(item=>item.security_id===row.security_id);
   if(!actionable&&prior&&['BUY','SELL'].includes(prior.side)&&prior.quantity>0&&prior.limit_price){
    action.appendChild(element('small','上次结果（仅供参考）：'+(prior.side==='BUY'?'买入':'卖出')+' '+prior.quantity+' 股 · 限价 '+legacyUi.dollars(prior.limit_price),'daily-secondary'));
   }
   const reason=reasons[row.reason]||(actionable?(advice.phase==='CLOSE'?'按已触发的退出计划处理':'按本次固定目标调整'):
     row.side==='HOLD'?reasons.HOLD:reasons[advice?.status]||'等待有效策略判断');
   tr.appendChild(action);tr.appendChild(element('td',reason));table.appendChild(tr);
  }
  summary.replaceChildren(table);
  if(account&&account.revision!==lastRevision){lastRevision=account.revision;onAccountChanged(structuredClone(account));}
  onChange(structuredClone(state));flushAccountReload();
  if(advice?.executable===true){const expires=Math.min(Date.parse(advice.valid_until),Date.parse(advice.quote_valid_until));if(Number.isFinite(expires)&&expires>now())timer=setTimer(()=>draw(controller.getState()),Math.min(expires-now(),2147483647));}
  else if(oldReference&&Number.isFinite(previousDeadline))timer=setTimer(()=>draw(controller.getState()),1000);
 }
 let historyStore=null;
 if(activeStrategy?.account_id&&activeStrategy.strategy_epoch===options.expectedEpoch){
  const key='roa-advice-history:'+activeStrategy.account_id+':'+options.expectedEpoch;
  historyStore={read(){const raw=doc.defaultView?.sessionStorage?.getItem(key);return raw&&raw.length<=262144?JSON.parse(raw):null;},
   write(value){const raw=JSON.stringify(value);if(raw.length<=262144)doc.defaultView?.sessionStorage?.setItem(key,raw);}};
 }
 controller=controllerApi.createController({...options,historyStore,now,onChange:draw});
 const edit=()=>{edited=true;};input.addEventListener('input',edit);
 let lastWork=Promise.resolve();
 const submit=event=>{
  event.preventDefault();if(locked||controller.getState().busy)return;
  const state=controller.getState(),amount=input.value;
  const retry=state.pending||(state.error&&state.cashSaved===true&&amount===lastAmount);
  if(!retry)lastAmount=amount;
  lastWork=(retry?controller.refresh():controller.save(amount)).then(next=>{if(next.cashSaved===true&&!next.error)edited=false;return next;});
 };
 form.addEventListener('submit',submit);
 const resume=()=>{if(doc.visibilityState!=='hidden')draw(controller.getState());};
 doc.addEventListener?.('visibilitychange',resume);doc.defaultView?.addEventListener('focus',resume);
 draw(controller.getState());
 return {...controller,ready:controller.load(),whenIdle:()=>lastWork,
  requestAccountReload(revision){if(disposed||!revision||revision===lastReloadKey)return;lastReloadKey=revision;queuedReload=revision;flushAccountReload();},
  elements:{form,input,save,cashPanel,summary,fundingForm,fundingResult,fundingInputs,quota,ownership,ownershipInputs},setCapitalBusy(value){locked=!!value;draw(controller.getState());},
  dispose(){disposed=true;fundingGeneration++;if(fundingTimer!==null)clearTimer(fundingTimer);fundingForm.removeEventListener('submit',fundingSubmit);fundingForm.removeEventListener('input',fundingEdited);if(lastRecommended!=='[]'){lastRecommended='[]';onRecommendedTickers([]);}if(timer!==null)clearTimer(timer);form.removeEventListener('submit',submit);input.removeEventListener('input',edit);doc.removeEventListener?.('visibilitychange',resume);doc.defaultView?.removeEventListener('focus',resume);controller.accountInvalidated();}};
}
const api={mount};if(typeof module!=='undefined'&&module.exports)module.exports=api;root.StrategyRoaMount=api;
})(typeof window!=='undefined'?window:globalThis);
