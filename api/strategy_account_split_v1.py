"""Unmounted split-aware account view; ordinary HTTP writes cannot authorize splits.

Server source approval and coordinated target/risk activation remain separate.
Historical fills stay in their original units; holding costs use current units.
"""
from fractions import Fraction
from api.strategy_account import StrategyAccountService, require
from core.strategy_account_split_store_v1 import SplitStrategyAccountStore


class SplitStrategyAccountService(StrategyAccountService):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.store = SplitStrategyAccountStore(kwargs['database_path'], clock=kwargs.get('clock'))

    def project(self,state):
        if state is None:return {'status':'NOT_INITIALIZED'}
        require(state['account_id']==self.account_id,'ACCOUNT_SCOPE_MISMATCH')
        names={}
        for row in state['events']:
            identity=row['payload'].get('identity_evidence')
            if identity:names[identity['security_id']]=identity['ticker']
        keys=('revision','holdings_revision','cash','cash_basis','total_uninvested_cash',
              'available_cash','reserved_cash','cash_confirmation_valid',
              'cash_confirmed_for_holdings_revision','execution_ready')
        account={k:state[k] for k in keys}
        account['holdings']=[dict(security_id=sid,ticker=names.get(sid),quantity=q)
                             for sid,q in sorted(state['shares'].items()) if q]
        account['orders']=[dict(order_id=o['order_id'],security_id=o['security_id'],
            ticker=names.get(o['security_id']),side=o['side'],quantity=o['quantity'],
            filled_quantity=o['filled_quantity'],remaining_quantity=o['remaining_quantity'],
            limit_price=o['limit_price'],reserved_cash=o['reserved_cash'])
            for o in state['orders'].values() if o['status']=='OPEN']
        fills=[]; costs={}; quantities={}; cash_delta=Fraction(0); last_cash=None
        for row in state['events']:
            event=row['payload'];kind=event['kind']
            if kind=='CASH_CONFIRM':
                last_cash=dict(amount=event['amount'],cash_basis=event['cash_basis'])
                cash_delta=Fraction(0)
            if kind == 'SPLIT_CONFIRMED':
                sid = event['security_id']
                quantities[sid] = quantities.get(sid, 0) * event['ratio']
                continue
            if kind not in {'FILL','DIRECT_FILL'}:continue
            order=state['orders'][event['order_id']] if kind=='FILL' else event
            sid=order['security_id'];side=order['side'];quantity=event['quantity']
            price=Fraction(event['price']);fees=Fraction(event['fees'])
            delta=Fraction(row['effect']['cash_delta']);cash_delta+=delta
            held=quantities.get(sid,0);cost=costs.get(sid,Fraction(0))
            if side=='BUY':
                costs[sid]=cost+quantity*price+fees;quantities[sid]=held+quantity
            else:
                costs[sid]=cost*(held-quantity)/held;quantities[sid]=held-quantity
            fills.append(dict(fill_id=event['event_id'],security_id=sid,ticker=names.get(sid),
                side=side,quantity=quantity,price=str(price),fees=str(fees),
                executed_at=event['executed_at'],cash_delta=str(delta)))
        require({sid:q for sid,q in quantities.items() if q} ==
                {sid:q for sid,q in state['shares'].items() if q}, 'SPLIT_COST_QUANTITY_MISMATCH')
        actions = [dict(action_id=row['payload']['action_id'], security_id=row['payload']['security_id'],
                        ratio=row['payload']['ratio'], effective_at=row['payload']['effective_at'],
                        quantity_before=row['effect']['quantity_before'], quantity_after=row['effect']['quantity_after'])
                   for row in state['events'] if row['payload']['kind'] == 'SPLIT_CONFIRMED']
        if actions: account['corporate_actions'] = actions
        account['fills']=fills
        account['holding_costs']=[dict(security_id=sid,ticker=names.get(sid),quantity=q,
            total_cost=str(costs[sid]),average_cost=str(costs[sid]/q))
            for sid,q in sorted(quantities.items()) if q]
        account['cost_basis_method']='RECORDED_ORDER_WEIGHTED_AVERAGE_INCLUDING_BUY_FEES'
        account['cash_summary']=dict(last_confirmation=last_cash,
            recorded_fill_cash_delta_since_confirmation=str(cash_delta),
            derived_total_uninvested_cash_estimate=(str(Fraction(last_cash['amount'])+cash_delta)
                if last_cash and last_cash['cash_basis']=='TOTAL_UNINVESTED' else None),
            current_balance_confirmed=state['cash_confirmation_valid'],automatic_cash_update=False)
        return dict(status='READY',account=account,ticker_scope='RECORDED_IDENTITY',orders_submitted=False)
