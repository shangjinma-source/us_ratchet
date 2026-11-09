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
 let flowRevision=null,lastRecommended='[]',queuedReload=null,lastReloadKey=null,reloadScheduled=false;
 function flushAccountReload(){if(disposed||reloadScheduled||!queuedReload||!controller||controller.getState().busy)return;reloadScheduled=true;Promise.resolve().then(()=>{reloadScheduled=false;if(disposed||!queuedReload||controller.getState().busy)return;queuedReload=null;void controller.load();});}
 let controller,disposed=false,edited=false,locked=false,timer=null,lastAmount=null,lastRevision=null;
 const reasons={WAIT_CASH_CONFIRMATION:'成交后请填写券商最新可用现金，再更新建议',WAIT_ACCOUNT_RESERVATIONS:'挂单占用与现金不一致，请核对真实挂单及可用现金',PENDING_OPEN:'等待开盘后确认目标股数',PENDING_CLOSE:'等待收盘执行时段',MISSED:'已错过本次执行时段，等待策略下一次判断',WAIT_SIGNAL:'等待有效策略信号',WAIT_FRESH_QUOTE:'等待最新有效报价',READY:'',CASH_RECONCILIATION_REQUIRED:'现金保存结果待核对，请刷新核对，勿重复提交',CASH_NOT_YET_OBSERVED:'尚未确认现金保存结果，请刷新核对，勿重复提交',CASH_NOT_SAVED_ACCOUNT_CHANGED:'现金未保存：账户已变化，请按券商最新可用现金重新提交',ADVICE_QUOTE_EXPIRED:'报价已过期，请刷新建议',ADVICE_REFRESH_REQUIRED:'建议暂未更新，请重试',ACCOUNT_CHANGED_REFRESH_REQUIRED:'账户已变化，请刷新建议'};
 Object.assign(reasons,{WAIT_EXECUTION_ADMISSION:'执行方式尚待确认，当前仅展示计划',CANCEL_THEN_RECALCULATE:'现有挂单与新目标冲突，请先核对挂单',WAIT_CASH:'可用现金不足，等待资金到账后更新',WAIT_CASH_NO_SELL_PROCEEDS_ASSUMED:'可用现金不足；卖出款实际到账后再更新',PENDING_RECONCILIATION_REQUIRED:'已有未完成挂单，请先核对成交或撤单状态',HOLD:'当前持仓已符合目标，无需买卖'});
 Object.assign(reasons,{PENDING_ORDER:'已有未完成挂单，请先核对成交或撤单状态',WAIT_CLOSE_HISTORY_RECONCILIATION:'收盘持仓状态待核对，暂不生成新挂单',SNAPSHOT_UNAVAILABLE:'建议暂未读取成功，请刷新重试'});
 function draw(state){
  if(disposed)return;
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
  elements:{form,input,save,cashPanel,summary},setCapitalBusy(value){locked=!!value;draw(controller.getState());},
  dispose(){disposed=true;if(lastRecommended!=='[]'){lastRecommended='[]';onRecommendedTickers([]);}if(timer!==null)clearTimer(timer);form.removeEventListener('submit',submit);input.removeEventListener('input',edit);doc.removeEventListener?.('visibilitychange',resume);doc.defaultView?.removeEventListener('focus',resume);controller.accountInvalidated();}};
}
const api={mount};if(typeof module!=='undefined'&&module.exports)module.exports=api;root.StrategyRoaMount=api;
})(typeof window!=='undefined'?window:globalThis);
