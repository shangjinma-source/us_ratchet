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


def require(ok, reason):
    if not ok: raise ValueError(reason)


def token(value, reason):
    require(isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',value),reason)


class StrategyAccountService:
    def __init__(self, *, database_path, account_id, resolver, clock=None, valuation_provider=None):
        self.store=StrategyAccountStore(database_path,clock=clock)
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

    def initialize(self,body):
        require(isinstance(body,dict) and set(body)=={'event_id'},'BODY_FIELDS')
        token(body['event_id'],'EVENT_ID_REQUIRED')
        try:state=self.store.initialize(self.account_id,operation_id=body['event_id'])
        except FileExistsError:state=self.store.initialize(self.account_id,operation_id=body['event_id'])
        return self.project(state)

    def append(self,body):
        require(isinstance(body,dict) and set(body)=={'expected_revision','event'},'BODY_FIELDS')
        require(isinstance(body['expected_revision'],str) and re.fullmatch('[0-9a-f]{64}',body['expected_revision']),'REVISION_REQUIRED')
        event=deepcopy(body['event']);require(isinstance(event,dict),'EVENT_FIELDS')
        token(event.get('event_id'),'EVENT_ID_REQUIRED')
        fields={'CASH_CONFIRM':{'amount','cash_basis'},
                'ORDER_OPEN':{'order_id','ticker','side','quantity','limit_price','fee_per_share'},
                'DIRECT_FILL':{'ticker','side','quantity','price','fees','executed_at'},
                'FILL':{'order_id','quantity','price','fees','executed_at'},
                'CANCEL':{'order_id'}}
        kind=event.get('kind')
        require(kind in fields and set(event)==fields[kind]|{'kind','event_id'},'EVENT_FIELDS')
        state=self.store.read();require(state is not None,'ACCOUNT_NOT_INITIALIZED')
        require(state['account_id']==self.account_id,'ACCOUNT_SCOPE_MISMATCH')
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
        return dict(self.project(updated),effect=effect)


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
            reason=str(error) if isinstance(error,ValueError) and re.fullmatch('[A-Z][A-Z0-9_]{0,79}',str(error)) else 'REQUEST_REJECTED'
            code=409 if reason in {'STALE_REVISION','EVENT_ID_CONFLICT','INITIALIZATION_CONFLICT','IDENTITY_MAPPING_CHANGED'} else 422
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
