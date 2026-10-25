"""Profile validation before monthly execution evidence; no reselection in preview."""
from copy import deepcopy
from datetime import datetime
from data.strategy_account_preview import preview_scoped_account
from core.strategy_account_ledger import require
from data.strategy_monthly_target_service import StrategyMonthlyTargetService
from data.strategy_continuous32_target_decision import validate_result,PROFILE_ID,VERSION

class Continuous32MonthlyService(StrategyMonthlyTargetService):
    def preview(self):
        with self.lock:
            target=self.targets.current();require(target is not None,'NO_MONTHLY_TARGET')
            decision=target['payload']['decision'];payload=decision['payload'];binding=payload['input_binding']
            require(decision['status']=='TARGET_READY' and binding.get('selector_profile')==PROFILE_ID
                    and binding.get('selection_method')==VERSION and binding.get('continuous_iterations')==32,
                    'CONTINUOUS32_PROFILE_CHANGED')
            require(validate_result(payload['search_result'],binding['search_arguments'])==payload['target_quantities'],
                    'TARGET_QUANTITIES_CHANGED')
            require(target['payload']['target_month']==self._month(),'MONTHLY_TARGET_REQUIRED')
            self.selection._pins();require(target['payload']['runtime_pins']==self.selection.pins,'TARGET_RUNTIME_CHANGED');state=self.accounts.read()
            require(state is not None and state['account_id']==target['payload']['account_id'],'TARGET_ACCOUNT_MISMATCH')
            require(state['cash_confirmation_valid'],'CASH_RECONFIRMATION_REQUIRED')
            require(self.targets.current()==target,'TARGET_CHANGED_BEFORE_PREVIEW')
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
