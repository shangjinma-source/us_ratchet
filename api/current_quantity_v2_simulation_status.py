"""Read-only projection of the server-owned isolated automatic simulation."""
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from backtest.current_quantity_v2_simulation_store import SimulationStore
from data.current_quantity_v2_paper_service import compact


def daily_summary(simulation, operations, now):
    """Report persisted evidence, never infer successful runs from account existence."""
    session=now.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    decision='NO_DECISION_RECORD'
    for operation in operations:
        request=operation['request'];kind=request.get('kind')
        day=request.get('monthly_request',{}).get('session') if kind=='BOUND_MONTHLY_OBSERVATION_V1' else request.get('session')
        if day!=session or operation['status']!='COMPLETE':continue
        if kind=='ISOLATED_DAILY_LATE_V1':decision='LATE_NO_NEW_DECISION'
        elif kind in ('SAME_MONTH_CONTINUATION_V1','BOUND_MONTHLY_OBSERVATION_V1'):
            decision='DECISION_STEP_COMPLETE'
    ledger=simulation['chain']['ledger']
    initial=datetime.fromisoformat(ledger['acceptance']['accepted_at'].replace('Z','+00:00'))
    if decision=='NO_DECISION_RECORD' and initial.astimezone(ZoneInfo('America/New_York')).date().isoformat()==session:
        decision='INITIAL_ORDERS_ACCEPTED'
    latest={}
    for batch in simulation['batches']:
        for identifier,result in batch.get('results',{}).items():latest[identifier]=result['status']
    unknown=sum(status=='UNKNOWN' and identifier in ledger['orders'] and not ledger['orders'][identifier]['closed']
                for identifier,status in latest.items())
    return dict(session=session,decision_status=decision,unresolved_order_results=unknown,
                incomplete_operations=sum(operation['status']!='COMPLETE' for operation in operations))


def snapshot(*, database_path, simulation_id, initial_cash='20000', clock=lambda: datetime.now(timezone.utc)):
    base=dict(simulation_only=True,real_account=False,initial_cash=initial_cash,
              holdings=[],targets=[],orders=[])
    path=Path(database_path)
    if not path.is_file():
        attempted=(path.parent/'scheduled-bootstrap-attempt.json').exists()
        return dict(base,status='INITIALIZATION_REQUIRES_REVIEW' if attempted else 'WAITING_FOR_INITIALIZATION')
    try:
        store=SimulationStore(path)
        current=store.read(simulation_id)
        operations=store.inspect_operations(simulation_id)
        if current['revision']!=operations['revision']:
            return dict(base,status='UNAVAILABLE',reason='STATE_CHANGED')
        simulation=current['simulation'];ledger=simulation['chain']['ledger']
        public=compact(simulation['chain'])
        def positions(values):
            return [dict(ticker=public['securities'][sid]['ticker'],shares=q)
                    for sid,q in values.items() if q>0]
        now=clock();orders=[]
        for order in public['orders']:
            row={key:order[key] for key in ('side','quantity','filled_quantity','limit_price','accepted_at','session_close','closed')}
            row['ticker']=public['securities'][order['security_id']]['ticker']
            closed=datetime.fromisoformat(row['session_close'].replace('Z','+00:00'))
            row['display_status']=row['closed'] or ('AWAITING_VERIFICATION' if now>=closed else 'MODEL_ORDER_OPEN')
            orders.append(row)
        pending=[op['status'] for op in operations['operations'] if op['status']!='COMPLETE']
        return dict(base,status='AVAILABLE',cash=public['cash'],reserved_cash=public['reserved_cash'],
                    target_month=public['target_month'],holdings=positions(public['shares']),
                    targets=positions(public['target_quantities']),orders=orders,
                    last_recorded_at=ledger['last_recorded_at'],pending_operations=pending,
                    daily=daily_summary(simulation,operations['operations'],now),
                    observed_at=now.isoformat(),record_type='MODELLED_NOT_BROKER_EXECUTIONS')
    except Exception:
        return dict(base,status='UNAVAILABLE',reason='STATE_UNVERIFIED')


def create_router(*,database_path,simulation_id,initial_cash='20000'):
    router=APIRouter()
    @router.get('/api/current_portfolio_research/automatic_simulation')
    def read_status(request:Request):
        if request.query_params:
            return JSONResponse({'status':'UNAVAILABLE','reason':'UNSUPPORTED_PARAMETERS'},status_code=400)
        return JSONResponse(snapshot(database_path=database_path,simulation_id=simulation_id,initial_cash=initial_cash),
                            headers={'Cache-Control':'no-store'})
    return router
