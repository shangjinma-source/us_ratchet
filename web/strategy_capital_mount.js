(function(root){
'use strict';
const capital=typeof module!=='undefined'&&module.exports?require('./strategy_capital_controller.js'):root.StrategyCapitalController;
// Optional secondary action. Mount only with an admitted capital API.
function mount(container,{recoveryOnly=false,onPublished=()=>{},onBalanceChanged=()=>{},onBusy=()=>{},onError=()=>{},...dependencies}){
 const doc=container.ownerDocument;
 const node=(tag,text)=>{const n=doc.createElement(tag);if(text)n.textContent=text;return n;};
 const form=node('form');form.className='capital-inline-form';
 const label=node('label','新增到账资金 USD'),amount=node('input');
 amount.placeholder='例如 5000';amount.inputMode='decimal';amount.required=true;amount.autocomplete='off';
 label.appendChild(amount);
 const submit=node('button','记入现金并重新配置');submit.type='submit';
 const note=node('p','仅填已到账、尚未计入左侧余额的新资金；自动增加现金，无需重复填写。');
 const status=node('p'),recover=node('button','核对上次配置');recover.type='button';recover.hidden=true;
 const withdraw=node('button','撤回本次录入');withdraw.type='button';withdraw.hidden=true;
 for(const n of [label,submit,note])form.appendChild(n);
 const wrapper=node('div');wrapper.className='capital-inline';
 for(const item of [form,status,recover,withdraw])wrapper.appendChild(item);
 container.replaceChildren(wrapper);
 let disposed=false,published=null,balanceRevision=null,lastWork=Promise.resolve(),syncWork=Promise.resolve(),syncing=false;
 function adviceMessage(state){
  if(!state)return '新增本金配置已完成，请查看下方今日动作。';
  if(state.error||!state.daily||state.daily.target_id!==published||state.target?.target_id!==published||
     state.daily.account_revision!==state.account?.revision)throw Error('CAPITAL_ADVICE_BINDING_MISMATCH');
  return state.daily.status==='READY'?
   '新增本金配置及今日判断已更新，请查看下方今日动作。':
   '新增本金配置已完成；今日判断暂不可执行，请查看下方原因。';
 }
 const draw=state=>{
  if(disposed)return;
  submit.disabled=amount.disabled=state.busy||!!state.pending||syncing;
  recover.hidden=!state.pending;recover.disabled=state.busy;
  withdraw.hidden=!state.pending||state.result?.credited!==false;withdraw.disabled=state.busy;
  form.hidden=recoveryOnly||!!state.pending;
  container.hidden=recoveryOnly&&!state.pending&&!state.result&&!state.error;
  const messages={
   IDLE:'',FAILED:'未开始配置，请检查新增金额及当前余额。',
   PENDING_RECOVERY:'上次配置结果待核对，请勿重复提交。',
   INTENT_RECORDED:'到账资金已记入，等待配置。',
   ARRIVAL_RECORDED:'到账记录已保存，点击核对继续处理；不会重复加钱。',
   CASH_RECORDED:'现金已增加，配置尚未完成；点击核对继续处理。',
   CREDITED_REVIEW_REQUIRED:'现金已增加，之后账户发生变动；需核对后继续配置，请勿重复录入。',
   PREPARED_PUBLISH_ONLY:'候选已保存，可以继续发布。',
   RECOVERY_REQUIRED:'配置未完成，已保留记录。请核对上次配置，不要重复录入资金。',
   WITHDRAWN:'未入账记录已撤回，现金与持仓未改变。',
   CONSUMED_BY_PUBLISHED_TARGET:'新增本金配置已完成。',
   INTENT_NOT_RECORDED_REFRESH_REQUIRED:'上次未记录成功。请更新余额后重新提交。',
   BLOCKED:'当前条件不满足，配置已暂停。'
  };
  status.textContent=state.busy?'正在核对并配置…':messages[state.status]??'等待核对配置状态。';
  if(!state.busy&&state.result?.credited===true&&['RECOVERY_REQUIRED','PENDING_RECOVERY'].includes(state.status))
   status.textContent='现金已增加，配置未完成；请核对上次配置，不要再次录入这笔资金。';
  onBusy(state.busy||!!state.pending||syncing);
  if(!state.busy&&['WITHDRAWN','CONSUMED_BY_PUBLISHED_TARGET'].includes(state.status))amount.value='';
  const revision=state.result?.credited===true?(state.result.account_revision||state.pending?.event_id):null;
  const targetId=state.result?.target_id;
  const completed=state.status==='CONSUMED_BY_PUBLISHED_TARGET'&&targetId;
  if(!state.busy&&completed&&published!==targetId){
   published=targetId;balanceRevision=revision;
   syncing=true;submit.disabled=amount.disabled=true;onBusy(true);
   status.textContent='新增本金配置已完成，正在更新今日建议…';
   syncWork=syncWork.then(()=>onPublished(targetId)).then(state=>{
    if(!disposed)status.textContent=adviceMessage(state);
   }).catch(error=>{
    if(!disposed){status.textContent='资金和配置已保存，但今日建议未更新；请点击左侧“更新现金并查看建议”，不要重复录入新增资金。';onError(error);}
   }).finally(()=>{
    syncing=false;
    if(!disposed){submit.disabled=amount.disabled=false;onBusy(false);}
   });
  }else if(!state.busy&&!completed&&revision&&balanceRevision!==revision){
   balanceRevision=revision;
   syncWork=syncWork.then(()=>onBalanceChanged(revision)).catch(onError);
  }
 };
 const controller=capital.createController({...dependencies,onChange:draw});
 let running=false;
 const run=fn=>{
  if(running)return lastWork;
  running=true;
  lastWork=Promise.resolve().then(fn).catch(onError).finally(()=>{running=false;});
  return lastWork;
 };
 const save=event=>{event.preventDefault();if(!recoveryOnly)run(()=>controller.start(amount.value.trim()));};
 const resume=()=>run(()=>controller.resume());
 const cancel=()=>run(()=>controller.withdraw());
 form.addEventListener('submit',save);recover.addEventListener('click',resume);withdraw.addEventListener('click',cancel);
 draw(controller.getState());
 const ready=controller.getState().pending?run(()=>controller.check()):Promise.resolve();
 return {getState:controller.getState,ready,whenIdle:async()=>{await lastWork;await syncWork;},elements:{form,amount,submit,status,recover,withdraw},
  adviceRefreshed(state){
   if(!disposed&&!syncing&&published&&!state.busy&&!state.error&&state.daily&&
      state.daily.target_id===published&&state.target?.target_id===published&&
      state.daily.account_revision===state.account?.revision)
    status.textContent=adviceMessage(state);
  },
  dispose(){disposed=true;
   form.removeEventListener('submit',save);recover.removeEventListener('click',resume);withdraw.removeEventListener('click',cancel);}
 };
}
const api={mount};if(typeof module!=='undefined'&&module.exports)module.exports=api;
root.StrategyCapitalMount=api;
})(typeof window!=='undefined'?window:globalThis);
