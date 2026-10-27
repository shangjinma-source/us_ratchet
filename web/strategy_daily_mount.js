(function(root){
'use strict';
const ui=typeof module!=='undefined'&&module.exports?require('./strategy_daily_controller.js'):root.StrategyDailyController;
// Page integration; strategy availability remains entirely server-controlled.
function cashInput(value){
 const text=String(value);
 if(/^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(text))return text;
 if(!/^\d{1,40}\/[1-9]\d{0,39}$/.test(text))return null;
 const [numerator,denominator]=text.split('/').map(BigInt);
 let remainder=numerator%denominator,fraction='';
 for(let i=0;remainder&&i<18;i++){remainder*=10n;fraction+=String(remainder/denominator);remainder%=denominator;}
 if(remainder)return null; // Never round a balance for a writeable field.
 return String(numerator/denominator)+(fraction?'.'+fraction:'');
}
function mount(container,dependencies){
 const {onTargetChanged=()=>{},onRecommendedTickers=()=>{},onAccountChanged=()=>{},
  onRefreshCompleted=()=>{},onError=()=>{},now=()=>Date.now(),setTimer=setTimeout,clearTimer=clearTimeout,
  ...controllerDependencies}=dependencies;
 const doc=container.ownerDocument,el=(tag,text,className)=>{
  const node=doc.createElement(tag);if(text!==undefined)node.textContent=text;
  if(className)node.className=className;return node;
 };
 const card=el('section',undefined,'strategy-monthly-target');
 const title=el('h3','今日买卖建议'),form=el('form',undefined,'monthly-cash-form');
 const label=el('label','当前可用现金 USD'),input=el('input');
 input.name='amount';input.inputMode='decimal';input.autocomplete='off';input.required=true;
 label.appendChild(input);
 const save=el('button','更新现金并查看建议');save.type='submit';
 form.appendChild(label);form.appendChild(save);
 const cashPanel=el('div',undefined,'daily-cash-panel');cashPanel.appendChild(form);
 const bar=el('div',undefined,'account-header'),heading=el('h3','本月股票与今日动作');
 bar.appendChild(heading);
 const summary=el('div',undefined,'monthly-table-scroll');
 const charts=el('div',undefined,'monthly-stock-charts');
 const titleBar=el('div',undefined,'account-header');titleBar.appendChild(title);
 for(const node of [titleBar,cashPanel,bar,summary,charts])card.appendChild(node);
 container.replaceChildren(card);
 const reviewHost=el('div');titleBar.appendChild(reviewHost);
 let controller,newsState=null;const openedNews=new Set();
 const newsApi=typeof module!=='undefined'&&module.exports?require('./news_investment_review.js'):root.NewsInvestmentReview;
 const newsCell=(cell,sid)=>newsApi.renderImpactCell(cell,sid,newsState,openedNews,now());
 let syncingReview=false,capitalLocked=false;
 const newsReview=(typeof module!=='undefined'&&module.exports?require('./news_investment_review.js'):root.NewsInvestmentReview).mount(reviewHost,{fetch:dependencies.newsReviewFetch||root.fetch?.bind(root),now,setTimer,clearTimer,compact:true,onReviewChange:next=>{newsState=next;if(controller)ui.render(summary,controller.getState(),now(),newsCell);},onComplete:proposal=>{
  if(capitalLocked)throw Error('CAPITAL_UPDATE_IN_PROGRESS');
  if(!proposal.original_preview)throw Error('REVIEW_PREVIEW_MISSING');
  syncingReview=true;
  try{const next=controller.adoptReviewedPreview(proposal);return {account:next.account,target:next.target,daily:next.daily};}
  finally{syncingReview=false;}
 }});
 let disposed=false,chartKey=null,accountKey=null,lastWork=Promise.resolve();
 let wasBusy=false,running=false;
 let expiryTimer=null,cashEdited=false;
 const edited=()=>{cashEdited=true;};
 input.addEventListener('input',edited);
 const safe=fn=>{try{fn();}catch(error){onError(error);}};
 const draw=state=>{
  if(disposed)return;
  if(expiryTimer!==null){clearTimer(expiryTimer);expiryTimer=null;}
  if(state.account?.cash_confirmation_valid===true&&state.account.available_cash!==undefined){
   const value=cashInput(state.account.available_cash);
   // A saved edit is no longer a draft. Later fills must update the field,
   // while an unsaved user edit must survive background account reads.
   if(state.cashSaved&&value!==null&&input.value===value)cashEdited=false;
   if(!cashEdited&&value!==null)input.value=value;
  }
  save.disabled=state.busy||capitalLocked;input.disabled=state.busy||capitalLocked;
  if(!syncingReview)newsReview.update({account:state.account,target:state.target,daily:capitalLocked?null:state.daily});
  const displayed=ui.render(summary,state,now(),newsCell);
  const chartTarget=state.target?structuredClone(state.target):null;
  if(chartTarget){
   const quantities=new Map(displayed.rows.map(row=>[row.security_id,row.monthly_target]));
   chartTarget.targets=ui.targetRows(chartTarget).map(row=>({...row,quantity:quantities.get(row.security_id)??null}));
  }
  const nextChartKey=JSON.stringify([chartTarget?.target_id,chartTarget?.proposal_id,chartTarget?.targets,state.account?.holdings]);
  if(nextChartKey!==chartKey){
   chartKey=nextChartKey;
   const tickers=[...new Set([...ui.targetRows(state.target),...(state.account?.holdings||[])].map(x=>x.ticker).filter(Boolean))];
   safe(()=>onRecommendedTickers(tickers));
   // Caller retains the existing K-line renderer and its own async race guard.
   safe(()=>onTargetChanged(chartTarget,{container:charts,holdings:structuredClone(state.account?.holdings||[])}));
  }
  if(state.account?.revision!==accountKey){accountKey=state.account?.revision;safe(()=>onAccountChanged(structuredClone(state.account)));}
  const finished=wasBusy&&!state.busy;wasBusy=state.busy;
  if(finished)safe(()=>onRefreshCompleted());
  safe(()=>dependencies.onChange?.(structuredClone(state)));
  const deadlines=Object.values(state.daily?.reference_quotes||{}).map(x=>Date.parse(x.reference_valid_until));
  for(const order of state.daily?.new_orders||[])deadlines.push(Date.parse(order.reference_valid_until));
  const future=deadlines.filter(x=>Number.isFinite(x)&&x>now());
  if(future.length&&!state.busy&&!state.error){
   expiryTimer=setTimer(()=>{expiryTimer=null;draw(controller.getState());},
    Math.min(Math.max(1,Math.min(...future)-now()),2147483647));
   expiryTimer?.unref?.();
  }
 };
 controller=ui.createController({...controllerDependencies,now,onChange:draw});
 const run=operation=>{
  if(disposed)return Promise.resolve();
  if(running)return lastWork;
  running=true;
  lastWork=Promise.resolve().then(operation).catch(error=>{onError(error);return null;})
   .finally(()=>{running=false;});
  return lastWork;
 };
 const submit=event=>{
  event.preventDefault();const amount=input.value,state=controller.getState();
  if(capitalLocked||state.busy)return;
  // A confirmed cash save can succeed before preview/target generation fails.
  // Retry that remaining work without another ledger write or new event ID.
  const retrySaved=state.error&&state.cashSaved&&state.account?.cash_confirmation_valid===true&&
   cashInput(state.account.available_cash)===amount;
  run(()=>retrySaved?controller.refresh():controller.saveBalance({amount,expected_revision:state.account?.revision}));
 };
 form.addEventListener('submit',submit);
 // Timers may be suspended during sleep or while the tab is hidden.
 const resume=()=>{if(doc.visibilityState!=='hidden')draw(controller.getState());};
 doc.addEventListener?.('visibilitychange',resume);
 doc.defaultView?.addEventListener('focus',resume);
 doc.defaultView?.addEventListener('pageshow',resume);
 draw(controller.getState());
 return {...controller,ready:run(()=>controller.load()),whenIdle:()=>lastWork,
  setCapitalBusy(value){capitalLocked=!!value;draw(controller.getState());},
  async reloadCash(){
   await controller.load();
   const state=controller.getState(),value=cashInput(state.account?.available_cash);
   if(value!==null&&state.account?.cash_confirmation_valid){input.value=value;cashEdited=false;}
  },
  elements:{form,input,save,cashPanel,summary,charts},
  dispose(){newsReview.dispose();disposed=true;doc.removeEventListener?.('visibilitychange',resume);doc.defaultView?.removeEventListener('focus',resume);doc.defaultView?.removeEventListener('pageshow',resume);if(expiryTimer!==null)clearTimer(expiryTimer);expiryTimer=null;input.removeEventListener('input',edited);form.removeEventListener('submit',submit);controller.invalidate();}
 };
}
const api={mount};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
root.StrategyDailyMount=api;
})(typeof window!=='undefined'?window:globalThis);
