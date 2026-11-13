"""Isolated, explicitly enabled real-strategy journal API; no order submission.

Resolver is server-owned and returns exact ticker/SID plus verified source pins.
The service trusts that injected resolver's source verification, never client SID.
"""
from copy import deepcopy
import json
import re
from fractions import Fraction
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from core.strategy_account_store import StrategyAccountStore
from core.strategy_fill_correction_store import FillCorrectionStore
from hashlib import sha256
from core.strategy_account_ledger import canonical


def require(ok, reason):
    if not ok: raise ValueError(reason)


def token(value, reason):
    require(isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',value),reason)


class WriteOutcomeUncertain(RuntimeError):
    """A write may be durable although its response could not be produced."""


class StrategyAccountService:
    def __init__(self, *, database_path, account_id, resolver, clock=None, valuation_provider=None):
        self.store=StrategyAccountStore(database_path,clock=clock)
        self.corrections=FillCorrectionStore(self.store)
        self.account_id=account_id
        self.resolver=resolver
        self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.valuation_provider=valuation_provider

    def valuation(self):
        state=self.store.read();require(state is not None,'ACCOUNT_NOT_INITIALIZED')
        require(state['account_id']==self.account_id,'ACCOUNT_SCOPE_MISMATCH')
        require(callable(self.valuation_provider),'VALUATION_UNAVAILABLE')
        marks=self.valuation_provider(deepcopy(state));now=self.clock()
        require(now.utcoffset() is not None,'AWARE_SERVER_CLOCK_REQUIRED')
        held={sid:q for sid,q in state['shares'].items() if q}
        require(type(marks) is dict and set(marks)==set(held),'VALUATION_DOMAIN_MISMATCH')
        rows=[];total=Fraction(0)
        for sid,quantity in sorted(held.items()):
            mark=marks[sid];at=datetime.fromisoformat(mark['observed_at'].replace('Z','+00:00'))
            require(at.utcoffset() is not None and 0<=(now-at).total_seconds()<=120,'VALUATION_EXPIRED')
            price=Fraction(mark['price']);require(price>0 and mark['security_id']==sid and mark['currency']=='USD','VALUATION_MARK_INVALID')
            value=price*quantity;total+=value
            rows.append(dict(security_id=sid,ticker=mark['ticker'],quantity=quantity,price=str(price),
                             observed_at=mark['observed_at'],market_value=str(value)))
        current=self.store.read();require(current is not None and current['revision']==state['revision'],'STALE_REVISION')
        confirmed=state['cash_confirmation_valid']
        return dict(status='READY',account_revision=state['revision'],holdings=rows,
                    market_value=str(total),cash_confirmed=confirmed,
                    strategy_total=str(total+Fraction(state['total_uninvested_cash'])) if confirmed else None,
                    valued_at=now.isoformat(),account_mutated=False,
                    public_actions_may_be_missing=True)

    def scoped_fills(self, state, fills):
        """Exclude explicitly archived, completed trade histories from public views.

        The immutable cash/risk journal remains authoritative. Selection is bound
        to original events and cannot hide an open position or part of a cycle.
        Later trades in the same security remain visible.
        """
        path=self.store.path.with_name(self.store.path.stem+'.trade_scope.json')
        if not path.exists():return fills,None
        require(not path.is_symlink() and path.stat().st_size<=65536,'TRADE_SCOPE_INVALID')
        raw=path.read_bytes();document=json.loads(raw)
        require(type(document)is dict and set(document)=={'schema','account_id','archived_events'},'TRADE_SCOPE_INVALID')
        require(document['schema']=='CLOSED_TRADE_ARCHIVE_V1' and document['account_id']==state['account_id'],'TRADE_SCOPE_ACCOUNT')
        selected=document['archived_events']
        require(type(selected)is dict and 0<len(selected)<=1000,'TRADE_SCOPE_INVALID')
        originals={r['payload']['event_id']:r['payload'] for r in state['events']}
        by_id={f['fill_id']:f for f in fills}
        require(set(selected)<=set(by_id),'TRADE_SCOPE_UNKNOWN_FILL')
        for identifier,digest in selected.items():
            require(digest==sha256(canonical(originals[identifier])).hexdigest(),'TRADE_SCOPE_FILL_CHANGED')
        # Every archived security must be a complete prefix ending flat.
        securities={by_id[key]['security_id'] for key in selected}
        for sid in securities:
            history=[f for f in fills if f['security_id']==sid]
            cutoff=max(i for i,f in enumerate(history) if f['fill_id'] in selected)
            require(all(f['fill_id'] in selected for f in history[:cutoff+1]),'TRADE_SCOPE_PARTIAL_HISTORY')
            quantity=0
            for fill in history[:cutoff+1]:
                quantity+=fill['quantity']*(1 if fill['side']=='BUY' else -1)
                require(quantity>=0,'TRADE_SCOPE_INVALID_POSITION')
            require(quantity==0,'TRADE_SCOPE_OPEN_POSITION')
        return [f for f in fills if f['fill_id'] not in selected],sha256(raw).hexdigest()

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
        corrections = {}
        amendments=self.corrections.read(state)
        account['fill_correction_revision']=sha256(canonical(amendments)).hexdigest()
        for record in amendments:
            event=record['event']
            corrections.setdefault(event['fill_id'], []).append(deepcopy(event))
        fills=[]; costs={}; quantities={}; cash_delta=Fraction(0); last_cash=None
        for row in state['events']:
            event=row['payload'];kind=event['kind']
            if kind=='CASH_CONFIRM':
                last_cash=dict(amount=event['amount'],cash_basis=event['cash_basis'])
                cash_delta=Fraction(0)
            if kind not in {'FILL','DIRECT_FILL'}:continue
            order=state['orders'][event['order_id']] if kind=='FILL' else event
            sid=order['security_id'];side=order['side'];quantity=event['quantity']
            history = corrections.get(event['event_id'], [])
            price=Fraction(history[-1]['price'] if history else event['price']);fees=Fraction(event['fees'])
            delta=(quantity*price if side=='SELL' else -quantity*price)-fees;cash_delta+=delta
            held=quantities.get(sid,0);cost=costs.get(sid,Fraction(0))
            if side=='BUY':
                costs[sid]=cost+quantity*price+fees;quantities[sid]=held+quantity
            else:
                costs[sid]=cost*(held-quantity)/held;quantities[sid]=held-quantity
            fills.append(dict(fill_id=event['event_id'],security_id=sid,ticker=names.get(sid),
                side=side,quantity=quantity,price=str(price),fees=str(fees),
                executed_at=event['executed_at'],cash_delta=str(delta)))
            if history:
                fills[-1].update(original_price=event['price'], price_corrections=history)
        fills,scope_revision=self.scoped_fills(state,fills)
        if scope_revision:account['trade_scope_revision']=scope_revision
        trade_results={}
        for fill in fills:
            sid=fill['security_id'];q=fill['quantity'];price=Fraction(fill['price'])
            row=trade_results.setdefault(sid,dict(security_id=sid,ticker=fill['ticker'],quantity=0,
                gross_cost=Fraction(0),realized_gross=Fraction(0),buy_amount=Fraction(0),
                sell_amount=Fraction(0),buy_quantity=0,sell_quantity=0,recorded_fees=Fraction(0)))
            row['recorded_fees']+=Fraction(fill['fees'])
            if fill['side']=='BUY':
                row['quantity']+=q;row['gross_cost']+=q*price
                row['buy_amount']+=q*price;row['buy_quantity']+=q
            else:
                require(0<q<=row['quantity'],'TRADE_PERFORMANCE_QUANTITY')
                basis=row['gross_cost']*q/row['quantity']
                row['realized_gross']+=q*price-basis;row['gross_cost']-=basis;row['quantity']-=q
                row['sell_amount']+=q*price;row['sell_quantity']+=q
        account['trade_results']=[{k:(str(v) if isinstance(v,Fraction) else v) for k,v in row.items()}
                                  for row in trade_results.values()]
        account['trade_results_scope']='RECORDED_TRADES_GROSS_NOT_ACCOUNT_RETURN'
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

    def read(self):return self.project(self.store.read())

    def audit_state(self):
        state=self.store.read()
        if state is not None:
            amendments=self.corrections.read(state)
            if amendments:state=dict(state,_fill_price_corrections=amendments)
        return state

    def committed_projection(self,state):
        try:return self.project(state)
        except Exception as error:raise WriteOutcomeUncertain() from error

    def initialize(self,body):
        require(isinstance(body,dict) and set(body)=={'event_id'},'BODY_FIELDS')
        token(body['event_id'],'EVENT_ID_REQUIRED')
        try:state=self.store.initialize(self.account_id,operation_id=body['event_id'])
        except FileExistsError:state=self.store.initialize(self.account_id,operation_id=body['event_id'])
        return self.committed_projection(state)

    def append(self,body):
        require(isinstance(body,dict) and set(body)=={'expected_revision','event'},'BODY_FIELDS')
        require(isinstance(body['expected_revision'],str) and re.fullmatch('[0-9a-f]{64}',body['expected_revision']),'REVISION_REQUIRED')
        event=deepcopy(body['event']);require(isinstance(event,dict),'EVENT_FIELDS')
        token(event.get('event_id'),'EVENT_ID_REQUIRED')
        fields={'CASH_CONFIRM':{'amount','cash_basis'},
                'ORDER_OPEN':{'order_id','ticker','side','quantity','limit_price','fee_per_share'},
                'DIRECT_FILL':{'ticker','side','quantity','price','fees','executed_at'},
                'FILL':{'order_id','quantity','price','fees','executed_at'},
                'CANCEL':{'order_id'},
                'FILL_PRICE_CORRECTION':{'fill_id','price','previous_price','reason'}}
        kind=event.get('kind')
        require(kind in fields and set(event)==fields[kind]|{'kind','event_id'},'EVENT_FIELDS')
        state=self.store.read();require(state is not None,'ACCOUNT_NOT_INITIALIZED')
        require(state['account_id']==self.account_id,'ACCOUNT_SCOPE_MISMATCH')
        if kind=='FILL_PRICE_CORRECTION':
            effect=self.corrections.append(event,expected_revision=body['expected_revision'])
            return dict(self.read(),effect=effect)
        if kind in {'DIRECT_FILL','ORDER_OPEN'}:
            ticker=event.pop('ticker')
            require(isinstance(ticker,str) and re.fullmatch('[A-Z0-9][A-Z0-9.-]{0,15}',ticker),'TICKER_REQUIRED')
            # A retry uses its original server-verified mapping, not a new mapping.
            previous=next((r['payload'] for r in state['events'] if r['payload']['event_id']==event['event_id']),None)
            if previous:
                identity=previous.get('identity_evidence')
                require(identity and identity['ticker']==ticker,'EVENT_ID_CONFLICT')
            else:
                identity=deepcopy(self.resolver(ticker))
                require(isinstance(identity,dict) and identity.get('ticker')==ticker,'IDENTITY_UNVERIFIED')
                for row in state['events']:
                    old=row['payload'].get('identity_evidence')
                    if old and old['ticker']==ticker:
                        require(old['security_id']==identity.get('security_id'),'IDENTITY_MAPPING_CHANGED')
            event.update(security_id=identity['security_id'],identity_evidence=identity)
        updated,effect=self.store.append(event,expected_revision=body['expected_revision'])
        return dict(self.committed_projection(updated),effect=effect)


def create_router(*,database_path,account_id,resolver,clock=None,valuation_provider=None):
    service=StrategyAccountService(database_path=database_path,account_id=account_id,resolver=resolver,clock=clock,valuation_provider=valuation_provider)
    router=APIRouter()
    async def invoke(request,operation,write=False):
        try:
            require(not request.query_params,'UNSUPPORTED_PARAMETERS')
            if write:
                data=bytearray()
                async for chunk in request.stream():
                    data.extend(chunk);require(len(data)<=8192,'BODY_TOO_LARGE')
                def pairs(items):
                    result={}
                    for key,value in items:
                        require(key not in result,'DUPLICATE_JSON_FIELD');result[key]=value
                    return result
                body=json.loads(data,object_pairs_hook=pairs,parse_constant=lambda x: (_ for _ in ()).throw(ValueError('INVALID_JSON')))
                result=await run_in_threadpool(operation,body)
            else:result=await run_in_threadpool(operation)
            return JSONResponse(result,headers={'Cache-Control':'no-store'})
        except Exception as error:
            if write and (isinstance(error,WriteOutcomeUncertain) or not isinstance(error,ValueError)):
                return JSONResponse(dict(status='BLOCKED',reason='RECONCILE_REQUIRED',
                    write_may_have_occurred=True,reconcile_before_retry=True),
                    status_code=503,headers={'Cache-Control':'no-store'})
            reason=str(error) if isinstance(error,ValueError) and re.fullmatch('[A-Z][A-Z0-9_]{0,79}',str(error)) else 'REQUEST_REJECTED'
            code=409 if reason in {'STALE_REVISION','STALE_FILL_PRICE','EVENT_ID_CONFLICT','INITIALIZATION_CONFLICT','IDENTITY_MAPPING_CHANGED'} else 422
            return JSONResponse(dict(status='BLOCKED',reason=reason),status_code=code,headers={'Cache-Control':'no-store'})
    @router.get('/api/strategy-account')
    async def read(request:Request):return await invoke(request,service.read)
    @router.get('/api/strategy-account/valuation')
    async def valuation(request:Request):return await invoke(request,service.valuation)
    @router.post('/api/strategy-account/initialize')
    async def initialize(request:Request):return await invoke(request,service.initialize,True)
    @router.post('/api/strategy-account/events')
    async def append(request:Request):return await invoke(request,service.append,True)
    return router
