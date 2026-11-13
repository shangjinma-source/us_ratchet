"""Explicitly mounted ROA HTTP orchestration with cash durability semantics."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, FileResponse
from starlette.concurrency import run_in_threadpool
from core.strategy_account_difference import require


def create_router(*, coordinator):
    router=APIRouter()

    @router.get('/static/strategy_roa_controller.js')
    async def controller_asset():
        return FileResponse(Path(__file__).resolve().parents[1]/'web/strategy_roa_controller.js',media_type='application/javascript',headers={'Cache-Control':'no-cache'})

    @router.get('/static/strategy_roa_mount.js')
    async def mount_asset():
        return FileResponse(Path(__file__).resolve().parents[1]/'web/strategy_roa_mount.js',media_type='application/javascript',headers={'Cache-Control':'no-cache'})

    async def invoke(request, retry, status=False):
        dispatched=False
        try:
            require(not request.query_params,'UNSUPPORTED_PARAMETERS')
            raw=bytearray()
            async for part in request.stream():
                raw.extend(part);require(len(raw)<=8192,'BODY_TOO_LARGE')
            def pairs(items):
                result={}
                for key,value in items:
                    require(key not in result,'DUPLICATE_JSON_FIELD');result[key]=value
                return result
            body=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('INVALID_JSON')))
            require(type(body) is dict,'BODY_FIELDS')
            if retry:require(not body,'BODY_FIELDS')
            else:
                require(set(body)=={'expected_revision','event'},'BODY_FIELDS')
                require(type(body['event']) is dict and set(body['event'])=={'event_id','kind','amount','cash_basis'},'CASH_EVENT_FIELDS')
                require(body['event']['kind']=='CASH_CONFIRM','CASH_CONFIRM_REQUIRED')
            dispatched=True
            operation=coordinator.cash_status if status else coordinator.retry_advice if retry else coordinator.save_cash
            result=await run_in_threadpool(operation, *([] if retry else [body]))
            return JSONResponse(result,status_code=503 if not retry and result['cash_saved'] is None else 200,headers={'Cache-Control':'no-store'})
        except Exception as error:
            # Once dispatched, this router cannot infer durability from the
            # exception class. Conservatively request reconciliation.
            uncertain=dispatched and not retry and not status
            reason=str(error) if isinstance(error,ValueError) and re.fullmatch('[A-Z][A-Z0-9_]{0,99}',str(error)) else 'REQUEST_REJECTED'
            return JSONResponse(dict(cash_saved=None if uncertain or retry or status else False,advice_ready=False,
                reason='CASH_WRITE_REQUIRES_RECONCILIATION' if uncertain else reason,orders_created=False),
                status_code=503 if uncertain else 409 if reason=='STALE_REVISION' else 422,headers={'Cache-Control':'no-store'})

    @router.post('/api/strategy-roa/cash-save-and-preview')
    async def save(request:Request):return await invoke(request,False)

    @router.post('/api/strategy-roa/advice-retry')
    async def retry(request:Request):return await invoke(request,True)

    @router.post('/api/strategy-roa/cash-status')
    async def status(request:Request):return await invoke(request,False,True)

    @router.get('/api/strategy-roa/config')
    async def configuration():
        return JSONResponse(dict(active=True,strategy_kind='ROA_DEFENSIVE_V1',strategy_epoch=coordinator.lifecycle.epoch,account_id=coordinator.account_service.account_id),headers={'Cache-Control':'no-store'})

    @router.get('/api/strategy-roa/snapshot')
    async def snapshot():
        try:
            result=await run_in_threadpool(coordinator.snapshot)
            return JSONResponse(result,headers={'Cache-Control':'no-store'})
        except Exception as error:
            result=coordinator.unavailable_snapshot(error)
            return JSONResponse(result,status_code=503,headers={'Cache-Control':'no-store'})

    @router.post('/api/strategy-roa/funding-preview')
    async def funding_preview(request: Request):
        # Read-only calculation. Does not confirm balances, transfer or order.
        try:
            from scripts.preview_broker_transfer import build_preview
            from scripts.verify_roa_live_advice import review
            require(not request.query_params, 'UNSUPPORTED_PARAMETERS')
            raw = bytearray()
            async for part in request.stream():
                raw.extend(part)
                require(len(raw) <= 8192, 'BODY_TOO_LARGE')
            body = json.loads(raw)
            fields = {'hsbc_cash', 'usmart_cash', 'other_fee_reserve',
                      'transfer_fee_reserve', 'hsbc_waiver_exhausted', 'quota_month'}
            require(type(body) is dict and fields <= set(body) <= fields | {'broker_holdings', 'hsbc_quota'}, 'BODY_FIELDS')
            if 'broker_holdings' in body:
                mapping = body['broker_holdings']
                require(type(mapping) is dict and set(mapping) == {'account_revision', 'positions'}, 'BROKER_HOLDINGS_INVALID')
                require(type(mapping['account_revision']) is str and 0 < len(mapping['account_revision']) <= 128, 'BROKER_HOLDINGS_INVALID')
                require(type(mapping['positions']) is list and len(mapping['positions']) <= 100, 'BROKER_HOLDINGS_INVALID')
                for position in mapping['positions']:
                    require(type(position) is dict and set(position) == {'broker', 'security_id', 'quantity'}, 'BROKER_HOLDINGS_INVALID')
                    require(position['broker'] in ('HSBC', 'USMART') and type(position['security_id']) is str and 0 < len(position['security_id']) <= 128, 'BROKER_HOLDINGS_INVALID')
                    require(type(position['quantity']) is int and 0 < position['quantity'] <= 1000000000, 'BROKER_HOLDINGS_INVALID')
            for field in fields - {'hsbc_waiver_exhausted', 'quota_month'}:
                require(type(body[field]) is str and re.fullmatch(r'(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?', body[field]), 'INVALID_BUDGET_AMOUNT')
            require(type(body['hsbc_waiver_exhausted']) is bool, 'INVALID_QUOTA_STATE')
            require(not body['hsbc_waiver_exhausted'] or 'hsbc_quota' not in body, 'CONFLICTING_QUOTA_STATE')
            from zoneinfo import ZoneInfo
            now = datetime.now(timezone.utc)
            require(body['quota_month'] == now.astimezone(ZoneInfo('Asia/Hong_Kong')).strftime('%Y-%m'), 'QUOTA_MONTH_MISMATCH')
            def calculate():
                cash_service = getattr(coordinator, 'broker_cash_service', None)
                require(cash_service is not None, 'BROKER_CASH_CONFIRMATION_REQUIRED')
                cash_split = cash_service.read()
                require(cash_split['status'] == 'CONFIRMED_BROKER_CASH_SPLIT', 'BROKER_CASH_CONFIRMATION_REQUIRED')
                from fractions import Fraction
                for broker, field in [('HSBC', 'hsbc_cash'), ('USMART', 'usmart_cash')]:
                    require(Fraction(body[field]) == Fraction(cash_split['document']['balances'][broker]['available_cash']), 'BROKER_CASH_INPUT_CHANGED')
                before = coordinator.account_service.read()
                snapshot = coordinator.snapshot()
                after = coordinator.account_service.read()
                config = dict(active=True, strategy_kind='ROA_DEFENSIVE_V1',
                              strategy_epoch=coordinator.lifecycle.epoch,
                              account_id=coordinator.account_service.account_id)
                require(cash_service.read() == cash_split, 'BROKER_CASH_CHANGED_DURING_PREVIEW')
                require(before['account']['revision'] == cash_split['account_revision'], 'STALE_BROKER_CASH_BINDING')
                checked = review(before, config, snapshot, after, now=datetime.now(timezone.utc))
                arguments = {key: value for key, value in body.items() if key != 'quota_month'}
                result = build_preview(verification=checked, snapshot=snapshot, **arguments)
                result.update(generated_at=datetime.now(timezone.utc).isoformat(),
                              quota_month=body['quota_month'],
                              reserve_assumptions=dict(other_fee_usd=body['other_fee_reserve'],
                                                       transfer_fee_usd=body['transfer_fee_reserve']),
                              account_written=False, orders_created=False)
                return result
            return JSONResponse(await run_in_threadpool(calculate), headers={'Cache-Control':'no-store'})
        except Exception as error:
            reason = str(error) if isinstance(error, ValueError) and re.fullmatch('[A-Z][A-Z0-9_]{0,99}', str(error)) else 'FUNDING_PREVIEW_UNAVAILABLE'
            return JSONResponse(dict(status=reason, executable=False, account_written=False,
                                     orders_created=False), status_code=422, headers={'Cache-Control':'no-store'})

    return router
