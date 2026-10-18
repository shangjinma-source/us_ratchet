"""Persistent targets with explicit reselection; daily quotations never optimize.

Execution provider is a server-injected evidence verifier, not browser input. It
must verify identity/action continuity from the persisted target through now and
return fresh marks/limits; this module does not fabricate that evidence.
"""
from contextlib import closing
from copy import deepcopy
from datetime import datetime,timezone
from threading import RLock
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import require
from data.strategy_account_preview import preview_scoped_account

LIFECYCLE_PATHS={'core/strategy_monthly_target_store.py','data/strategy_monthly_target_service.py'}

class StrategyMonthlyTargetService:
    def __init__(self,*,selection_service,target_store,execution_provider,clock=None):
        self.selection=selection_service;self.accounts=selection_service.store
        self.targets=target_store;self.execution_provider=execution_provider
        self.clock=clock or (lambda:datetime.now(timezone.utc));self.lock=RLock()
        require(LIFECYCLE_PATHS<=set(selection_service.pins),'MONTHLY_LIFECYCLE_PINS_REQUIRED')
    def _now(self):
        now=self.clock();require(isinstance(now,datetime) and now.utcoffset() is not None,'AWARE_SERVER_CLOCK_REQUIRED');return now
    def _month(self):return self._now().astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')
    def current(self):return self.targets.current()
    def generate(self,*,event_id,reason,expected_revision,previous_target_id):
        require(type(event_id)is str and 0<len(event_id)<=128,'TARGET_EVENT_ID_REQUIRED')
        require(reason in {'INITIAL','MONTHLY_SELECTION','EXPLICIT_RECONFIGURE'},'EXPLICIT_GENERATION_REASON_REQUIRED')
        request=dict(event_id=event_id,reason=reason,expected_revision=expected_revision,previous_target_id=previous_target_id)
        with self.lock:
            old=self.targets.operation(event_id)
            if old:
                require(old['payload']['request']==request,'TARGET_EVENT_CONFLICT');return old
            prior=self.targets.current();require(previous_target_id==(prior['target_id'] if prior else None),'STALE_TARGET')
            month=self._month()
            require((reason=='INITIAL' and prior is None) or (reason=='MONTHLY_SELECTION' and prior is not None and prior['payload']['target_month']<month) or (reason=='EXPLICIT_RECONFIGURE' and prior is not None and prior['payload']['target_month']==month),'TARGET_REASON_MONTH_MISMATCH')
            initial=self.accounts.read();require(initial is not None and initial['revision']==expected_revision,'STALE_REVISION')
            require(prior is None or prior['payload']['account_id']==initial['account_id'],'TARGET_ACCOUNT_MISMATCH')
            select=getattr(self.selection,'select',None)
            result=select() if callable(select) else self.selection.generate()
            require(result['status']=='READY',result.get('reason','TARGET_SELECTION_FAILED'))
            decision,_,selected_state=self.selection.current
            require(selected_state['revision']==expected_revision,'ACCOUNT_CHANGED_DURING_TARGET')
            payload=dict(schema='REAL_STRATEGY_MONTHLY_TARGET_V1',account_id=initial['account_id'],target_month=month,
                created_at=self._now().isoformat(),request=request,previous_target_id=previous_target_id,
                decision=deepcopy(decision),target_quantities=deepcopy(decision['payload']['target_quantities']),
                runtime_pins=deepcopy(self.selection.pins))
            # Never hold the account lock during research; hold it only across
            # final revision validation and independent target publication.
            with closing(self.accounts._connect(False)) as con:
                try:
                    con.execute('BEGIN IMMEDIATE');current,_=self.accounts._read(con)
                    require(current['revision']==expected_revision,'ACCOUNT_CHANGED_DURING_TARGET')
                    require(self._month()==month,'TARGET_MONTH_CHANGED_DURING_SELECTION')
                    self.selection._pins()
                    return self.targets.append(payload)
                finally:con.rollback()
    def preview(self):
        with self.lock:
            target=self.targets.current();require(target is not None,'NO_MONTHLY_TARGET')
            require(target['payload']['target_month']==self._month(),'MONTHLY_TARGET_REQUIRED')
            self.selection._pins();require(target['payload']['runtime_pins']==self.selection.pins,'TARGET_RUNTIME_CHANGED');state=self.accounts.read()
            require(state is not None and state['account_id']==target['payload']['account_id'],'TARGET_ACCOUNT_MISMATCH')
            require(state['cash_confirmation_valid'],'CASH_RECONFIRMATION_REQUIRED')
            now=self._now();evidence=self.execution_provider(deepcopy(state),deepcopy(target),now)
            require(type(evidence)is dict and set(evidence)=={'marks','limits'},'EXECUTION_PROVIDER_FIELDS')
            result=preview_scoped_account(state=state,legacy_shares={},target_quantities=target['payload']['target_quantities'],
                marks=evidence['marks'],limits=evidence['limits'],now=self._now().isoformat(),
                maximum_mark_age_seconds=120,fee_bps=self.selection.fees)
            self.selection._pins()
            require(self.accounts.read()['revision']==state['revision'],'ACCOUNT_CHANGED_DURING_PREVIEW')
            require(self.targets.current()['target_id']==target['target_id'],'TARGET_CHANGED_DURING_PREVIEW')
            require(self._month()==target['payload']['target_month'],'MONTHLY_TARGET_REQUIRED')
            finished=self._now()
            for quote in [*evidence['marks'].values(),*evidence['limits'].values()]:
                observed=datetime.fromisoformat(quote['observed_at'])
                require(observed.utcoffset() is not None and 0<=(finished-observed).total_seconds()<120,'REQUOTE_REQUIRED')
            for limit in evidence['limits'].values():
                require(type(limit.get('reference_valid_until')) is str,'EXECUTION_DEADLINE_REQUIRED')
                deadline=datetime.fromisoformat(limit['reference_valid_until'])
                require(deadline.utcoffset() is not None and finished<deadline,'REQUOTE_REQUIRED')
            for order in result['new_orders']:
                sid=order['security_id'];limit=evidence['limits'][sid];mark=evidence['marks'][sid]
                ticker=limit.get('ticker') or mark.get('ticker')
                require(type(ticker)is str and bool(ticker),'EXECUTION_TICKER_REQUIRED')
                if mark.get('ticker') is not None:require(mark['ticker']==ticker,'EXECUTION_TICKER_MISMATCH')
                reason=limit.get('buy_reason' if order['side']=='BUY' else 'sell_reason')
                require(type(reason)is str and bool(reason),'EXECUTION_REASON_REQUIRED')
                desired=target['payload']['target_quantities'].get(sid,0)
                order.update(ticker=ticker,observed_at=limit['observed_at'],
                    reference_valid_until=limit['reference_valid_until'],execution_reason=reason,
                    strategy_reason=('补足本月目标持仓' if order['side']=='BUY' else
                        '本月目标为零，退出持仓' if desired==0 else '当前持仓高于本月目标，减仓至目标'))
            references={sid:dict(ticker=limit.get('ticker') or evidence['marks'][sid].get('ticker'),
                buy_limit=limit['buy'] if limit.get('buy_evaluated') is True else None,
                sell_limit=limit['sell'],mark_price=evidence['marks'][sid]['price'],
                observed_at=limit['observed_at'],reference_valid_until=limit['reference_valid_until'],
                buy_reason=limit.get('buy_reason'),sell_reason=limit.get('sell_reason'),
                sell_is_exit_reference=True) for sid,limit in evidence['limits'].items()}
            return dict(status='READY',target_id=target['target_id'],target_month=target['payload']['target_month'],
                account_revision=state['revision'],difference=result,reference_quotes=references,core_calls=0,orders_created=False,account_mutated=False,
                generated_at=finished.isoformat(),reference_valid_until=min(
                    (limit['reference_valid_until'] for limit in evidence['limits'].values()),key=lambda value:datetime.fromisoformat(value))
                    if result['new_orders'] else None)
