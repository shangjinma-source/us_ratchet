"""Server-owned monthly target routes and current New York month guidance."""
import json
import re
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool


def require(ok,reason):
    if not ok:raise ValueError(reason)


def revision(value,nullable=False):
    require((nullable and value is None) or (type(value)is str and re.fullmatch('[0-9a-f]{64}',value)), 'REVISION_OR_TARGET_ID_REQUIRED')


def compact(target):
    if target is None:return dict(status='NOT_INITIALIZED',orders_created=False)
    payload=target['payload'];binding=payload['decision']['payload']['input_binding']
    metadata=binding['search_arguments']['metadata']
    return dict(status='SAVED_TARGET',target_id=target['target_id'],target_month=payload['target_month'],
        created_at=payload['created_at'],account_revision=binding['account_revision'],
        targets=[dict(security_id=sid,ticker=metadata[sid]['ticker'],quantity=q) for sid,q in sorted(payload['target_quantities'].items())],
        historical_training_cutoff=binding['training_cutoff_date'],valuation_at=binding['valuation_at'],
        strategy_equity=binding['strategy_equity'],execution_verified=False,orders_created=False)


def create_router(*,service,charts=None):
    """service is an injected StrategyMonthlyTargetService, never client-selected."""
    router=APIRouter()
    def present(value):
        result=compact(value)
        month=service._month()
        prior=value['payload']['target_month'] if value else None
        result['server_month']=month
        result['configuration_reason']=('INITIAL' if prior is None else
            'MONTHLY_SELECTION' if prior<month else
            'EXPLICIT_RECONFIGURE' if prior==month else None)
        return result

    async def invoke(request,operation,write=False,allow_query=False):
        try:
            require(allow_query or not request.query_params,'UNSUPPORTED_PARAMETERS')
            if write:
                raw=bytearray()
                async for chunk in request.stream():
                    raw.extend(chunk);require(len(raw)<=4096,'BODY_TOO_LARGE')
                def pairs(items):
                    value={}
                    for key,item in items:
                        require(key not in value,'DUPLICATE_JSON_FIELD');value[key]=item
                    return value
                body=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('INVALID_JSON')))
                require(type(body)is dict,'BODY_FIELDS')
                result=await run_in_threadpool(operation,body)
            else:result=await run_in_threadpool(operation)
            return JSONResponse(result,headers={'Cache-Control':'no-store'})
        except Exception as error:
            reason=str(error) if isinstance(error,ValueError) and re.fullmatch('[A-Z][A-Z0-9_]{0,99}',str(error)) else 'TARGET_UNAVAILABLE'
            conflict=reason in {'STALE_REVISION','STALE_TARGET','TARGET_EVENT_CONFLICT','ACCOUNT_CHANGED_DURING_TARGET','ACCOUNT_CHANGED_DURING_PREVIEW','TARGET_CHANGED_DURING_PREVIEW'}
            return JSONResponse(dict(status='BLOCKED',reason=reason,orders_created=False),status_code=409 if conflict else 422,headers={'Cache-Control':'no-store'})

    def generate(body):
        require(set(body)=={'event_id','reason','expected_revision','previous_target_id'},'BODY_FIELDS')
        require(type(body['event_id'])is str and re.fullmatch('[A-Za-z0-9_.:-]{1,128}',body['event_id']),'TARGET_EVENT_ID_REQUIRED')
        revision(body['expected_revision']);revision(body['previous_target_id'],True)
        require(body['reason'] in {'INITIAL','MONTHLY_SELECTION','EXPLICIT_RECONFIGURE'},'EXPLICIT_GENERATION_REASON_REQUIRED')
        return present(service.generate(**body))

    def preview(body):
        require(set(body)=={'expected_revision','target_id'},'BODY_FIELDS')
        revision(body['expected_revision']);revision(body['target_id'])
        state=service.accounts.read();target=service.current()
        require(state is not None and state['revision']==body['expected_revision'],'STALE_REVISION')
        require(target is not None and target['target_id']==body['target_id'],'STALE_TARGET')
        result=service.preview()
        require(result['account_revision']==body['expected_revision'],'ACCOUNT_CHANGED_DURING_PREVIEW')
        require(result['target_id']==body['target_id'],'TARGET_CHANGED_DURING_PREVIEW')
        # Difference binding contains raw evidence references: publish only UI fields.
        difference=result['difference']
        fields=('status','strategy_equity','spendable_cash','strategy_market_value','total_uninvested_cash',
                'pending_buy_reserved_cash','new_orders','waiting_cash','cancel_before_recalculate','new_buy_cash_required')
        return dict(status=result['status'],target_id=result['target_id'],target_month=result['target_month'],
            account_revision=result['account_revision'],difference={k:difference[k] for k in fields if k in difference},
            orders_created=False,account_mutated=False,core_calls=0,reference_quotes=result.get('reference_quotes',{}),
            **{k:result[k] for k in ('generated_at','reference_valid_until') if k in result})

    @router.get('/api/strategy-account/target/bars')
    async def historical_bars(request:Request):
        def read():
            require(charts is not None,'TARGET_CHARTS_UNAVAILABLE')
            query=request.query_params
            require(set(query)=={'target_id','security_id','interval'} and len(query.multi_items())==3,'CHART_ARGUMENTS_INVALID')
            service.selection._pins()
            result=charts.bars(**dict(query))
            service.selection._pins()
            return result
        return await invoke(request,read,allow_query=True)

    @router.get('/api/strategy-account/target')
    async def current(request:Request):return await invoke(request,lambda:present(service.current()))
    @router.post('/api/strategy-account/target/generate')
    async def create(request:Request):return await invoke(request,generate,True)
    @router.post('/api/strategy-account/target/preview')
    async def refresh(request:Request):return await invoke(request,preview,True)
    return router
