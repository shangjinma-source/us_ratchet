"""Explicit ROA account service. Signal/quote/calendar adapters are server owned."""
import logging,re
from copy import deepcopy
from datetime import timedelta
from fractions import Fraction as F
from threading import RLock
from core.strategy_account_difference import require,timestamp
from data.roa_execution_lifecycle import digest
from data.roa_cash_advice_coordinator import CashAdviceCoordinator
from data.roa_target_account_bridge import preview_target_weights


class RoaStrategyService(CashAdviceCoordinator):
    def __init__(self, *, account_service, lifecycle, signal_provider, session_provider,
                 quote_provider, clock, execution_admission=None):
        super().__init__(account_service=account_service,builder=None)
        self.lifecycle=lifecycle;self.signal_provider=signal_provider;self.session_provider=session_provider
        self.quote_provider=quote_provider;self.clock=clock;self.admission=deepcopy(execution_admission)
        self.lock=RLock()

    def unavailable_snapshot(self,error):
        logging.getLogger(__name__).exception('ROA snapshot unavailable')
        reason=str(error) if re.fullmatch('[A-Z][A-Z0-9_]{0,99}',str(error)) else 'SNAPSHOT_UNAVAILABLE'
        result=dict(strategy_kind='ROA_DEFENSIVE_V1',strategy_epoch=self.lifecycle.epoch,status='WAIT_SIGNAL',
            reason=reason,advice_ready=False,executable=False,rows=[],orders_created=False)
        try:
            state=self.account_service.store.read()
            result.update(account_revision=state['revision'],account=self.account_service.project(state)['account'])
        except Exception:
            logging.getLogger(__name__).exception('ROA fallback account read failed')
        return result

    def retry_advice(self):
        # Refreshing a plan is not a cash write or durability acknowledgement.
        return self._advice(cash_saved=None)

    def _advice(self, *, cash_saved):
        try:result=self.snapshot()
        except Exception as error:result=self.unavailable_snapshot(error)
        result['cash_saved']=cash_saved;return result

    def snapshot(self):
        with self.lock:
            now=self.clock();state=self.account_service.store.read()
            require(state is not None,'ACCOUNT_NOT_INITIALIZED')
            account=self.account_service.project(state)['account']
            signal=self.signal_provider();session=signal['execution_not_before_session']
            calendar=self.session_provider(session)
            opening=timestamp(calendar['open_at']);closing=timestamp(calendar['close_at'])
            admitted=self.admission is not None and self.admission.get('enabled') is True
            if admitted:
                require(self.admission['strategy_epoch']==self.lifecycle.epoch and self.admission['contract_sha256']==self.lifecycle.contract,'EXECUTION_ADMISSION_SCOPE')
                open_until=opening+timedelta(seconds=self.admission['open_window_seconds'])
                close_from=closing-timedelta(seconds=self.admission['close_window_seconds'])
            else:
                # Calendar display envelope only: never authorizes execution.
                open_until=closing;close_from=closing
            standard_open_until=open_until
            late_authorized=admitted and self.admission.get('late_open_session')==session
            if late_authorized:
                require(opening < close_from, 'LATE_OPEN_SESSION_BOUNDS')
                # Never replace an already frozen allocation from a different window.
                prior=self.lifecycle.read()
                require(not any(e['session']==session and e['phase']=='OPEN' and
                    e.get('materialized_revision') and timestamp(e['valid_until'])!=close_from
                    for e in prior['events']), 'LATE_OPEN_ALREADY_MATERIALIZED_REVIEW')
                open_until=close_from
            self.lifecycle.plan(signal=signal,session=session,open_at=opening.isoformat(),
                open_until=open_until.isoformat(),close_at=close_from.isoformat(),
                close_until=(closing+timedelta(microseconds=1)).isoformat())
            view=self.lifecycle.event_view(now=now.isoformat());event=view['event']
            lifecycle_state=self.lifecycle.read()
            if lifecycle_state.get('missed_exits'):view['status']='MISSED'
            if any(e.get('materialized_revision') and e['session']<session for e in lifecycle_state['events']) and (lifecycle_state.get('last_close') or '')<signal['signal_date']:
                view['status']='WAIT_CLOSE_HISTORY_RECONCILIATION'
            if view['status']=='MISSED' and event and not lifecycle_state.get('missed_exits'):
                live_orders=any(o['status']=='OPEN' for o in state['orders'].values())
                if not live_orders:
                    if event['phase']=='OPEN' and event.get('targets') is not None:
                        actual={s:q for s,q in state['shares'].items() if q}
                        expected={s:q for s,q in event['targets'].items() if q}
                        if actual==expected:view['status']='HOLD'
                    elif event['phase']=='CLOSE' and all(state['shares'].get(s,0)==0 for s in event['pending']):
                        view['status']='HOLD'
            names={s['security_id']:s['ticker'] for s in signal['securities']}
            names.update({r['security_id']:r['ticker'] for r in account['holdings']})
            targets=deepcopy(event.get('targets')) if event else None
            result=dict(strategy_kind='ROA_DEFENSIVE_V1',strategy_epoch=self.lifecycle.epoch,
                account_revision=state['revision'],account=account,status=view['status'],phase=view['phase'],
                executable=False,advice_ready=True,signal_date=signal['signal_date'],execution_session=session,
                target_id=None,proposal_id=None,target_quantities=targets,quote_valid_until=None,
                valid_from=event['valid_from'] if event else None,valid_until=event['valid_until'] if event else None,
                rows=[],orders_created=False,execution_assumption='MANUAL_EXECUTION_NOT_GUARANTEED_HISTORICAL_OPEN_CLOSE')
            result['late_execution']=bool(late_authorized and event and event['phase']=='OPEN' and now>=standard_open_until)
            result['standard_open_valid_until']=standard_open_until.isoformat()
            if result['late_execution']:
                result['execution_assumption']='USER_AUTHORIZED_LATE_EXECUTION_NOT_BACKTEST_VALIDATED'
            if view['status']=='WINDOW_OPEN' and not admitted:result['status']='WAIT_EXECUTION_ADMISSION'
            if view['status']=='WINDOW_OPEN' and admitted and not state['cash_confirmation_valid']:
                result.update(status='WAIT_CASH_CONFIRMATION',reason='WAIT_CASH_CONFIRMATION',executable=False,
                    action_required='UPDATE_CASH_AND_VIEW_ADVICE')
            elif view['status']=='WINDOW_OPEN' and admitted and not state['execution_ready']:
                result.update(status='WAIT_ACCOUNT_RESERVATIONS',reason='WAIT_ACCOUNT_RESERVATIONS',executable=False,
                    action_required='RECONCILE_REAL_ORDERS_AND_CASH')
            elif view['status']=='WINDOW_OPEN' and admitted:
                try:
                    needed=set(signal['weights'])|{s for s,q in state['shares'].items() if q}
                    needed|={o['security_id'] for o in state['orders'].values() if o['status']=='OPEN'}
                    quotes=self.quote_provider(deepcopy(state),needed,session,event['phase'],now)
                    for sid in needed:
                        mark=quotes['marks'][sid]
                        require(mark['security_id']==sid and mark['currency']=='USD' and mark['price_basis']=='current','QUOTE_IDENTITY_MISMATCH')
                        require(type(mark['price']) in (str,int) and F(mark['price'])>0,'POSITIVE_QUOTE_REQUIRED')
                    if event['phase']=='OPEN':
                        require(quotes['opening_session']==session,'OPENING_SESSION_MISMATCH')
                        event=self.lifecycle.materialize_open(event_id=event['event_id'],account=state,
                            opening_prices=quotes['opening_prices'],now=now.isoformat())
                        targets=event['targets']
                    else:
                        targets={s:q for s,q in state['shares'].items() if q and s not in event['pending']}
                    weights={s:'0' for s in set(targets)|set(signal['weights'])}
                    advice=preview_target_weights(account=state,expected_revision=state['revision'],weights=weights,
                        marks=quotes['marks'],limits=quotes['limits'],signal_at=self.session_provider(signal['signal_date'])['close_at'],
                        valid_from=event['valid_from'],valid_until=event['valid_until'],now=now.isoformat(),
                        contract_hash=self.lifecycle.contract,frozen_quantities=targets)
                    deadline=min(timestamp(quotes['quote_valid_until']),timestamp(event['valid_until']))
                    require(self.clock()<deadline,'QUOTE_EXPIRED')
                    binding=dict(strategy_epoch=self.lifecycle.epoch,account_revision=state['revision'],event_id=event['event_id'],
                        targets=targets,phase=event['phase'],valid_from=event['valid_from'],valid_until=event['valid_until'])
                    target_id=digest(binding);proposal_id=digest(dict(target_id=target_id,difference=advice['difference'],quote_valid_until=deadline.isoformat()))
                    result.update(status='CANCEL_THEN_RECALCULATE' if advice['difference']['status']=='CANCEL_THEN_RECALCULATE' else 'READY',executable=advice['difference']['status']!='CANCEL_THEN_RECALCULATE',target_id=target_id,proposal_id=proposal_id,
                        target_quantities=targets,quote_valid_until=deadline.isoformat(),difference=advice['difference'])
                except (ValueError,KeyError,TypeError,OSError):
                    result.update(status='WAIT_FRESH_QUOTE',executable=False,quote_valid_until=None)
            orders={r['security_id']:r for r in result.get('difference',{}).get('new_orders',[])}
            domain=set(signal['weights'])|{s for s,q in state['shares'].items() if q}
            waiting={r['security_id'] for r in result.get('difference',{}).get('waiting_cash',[])}
            pending={o['security_id'] for o in state['orders'].values() if o['status']=='OPEN'}
            for sid in sorted(domain):
                order=orders.get(sid) if result['executable'] else None
                result['rows'].append(dict(security_id=sid,ticker=names.get(sid),held=state['shares'].get(sid,0),
                    target_quantity=(targets or {}).get(sid,0) if targets is not None else None,
                    side=order['side'] if order else 'WAIT' if not result['executable'] or sid in waiting or sid in pending else 'HOLD',quantity=order['quantity'] if order else None,
                    limit_price=order['limit_price'] if order else None,reason='PENDING_ORDER' if sid in pending else 'WAIT_CASH' if sid in waiting else 'HOLD' if result['executable'] and not order else result['status']))
            require(self.account_service.store.read()==state,'ACCOUNT_CHANGED_DURING_ADVICE')
            return deepcopy(result)
