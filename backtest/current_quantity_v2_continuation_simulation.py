"""Explicit same-month 10:00 continuation using existing capture and paper rules.

No search, scheduler, broker writes or automatic expiry. The supplied admission
guard and review providers retain authority; missing evidence is never cleared.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import json

from backtest.current_quantity_v2_annual_clock import build_observation_clock
from backtest.current_quantity_v2_monthly_simulation import _ReadOnlyChain, digest
from backtest.current_quantity_v2_simulated_settlement import _rebuild, accept_orders
from data.current_quantity_v2_continuation_service import QuantityV2ContinuationSourceBridge
from data.current_quantity_v2_current_cash_continuation_sources import CurrentCashContinuationSources
from data.current_quantity_v2_difference_plan import require, stamp
from data.current_quantity_v2_monthly_continuation_sources import QuantityV2MonthlyContinuationSources
from data.current_quantity_v2_monthly_retarget import active_proposal


def apply_continuation(*, store, simulation_id, expected_revision, operation_id,
                       root, schedule_path, schedule_sha256, session, triggered_at,
                       storage_directory, source_admission_guard, fetch, clock,
                       unit_review_reader=None, monthly_review_reader=None,
                       monthly_blob_root=None, pullback_policy=None, pullback_cap_store=None):
    trigger=stamp(triggered_at)
    require(operation_id==simulation_id+':daily-continuation:'+session, 'CONTINUATION_SESSION_OPERATION_REQUIRED')
    request=dict(kind='SAME_MONTH_CONTINUATION_V1',session=session,triggered_at=trigger.isoformat(),
        root=str(Path(root).resolve()),schedule_path=schedule_path,schedule_sha256=schedule_sha256,
        storage_directory=str(Path(storage_directory).resolve()),
        monthly_blob_root=str(Path(monthly_blob_root).resolve()) if monthly_blob_root is not None else None,
        pullback_policy=deepcopy(pullback_policy))
    def transform(simulation):
        simulation,_,last_at=_rebuild(simulation);state=simulation['chain'];ledger=state['ledger']
        local=trigger.astimezone(ZoneInfo('America/New_York'))
        require(local.date().isoformat()==session and (local.hour,local.minute)==(10,0),
                'SIMULATION_TRIGGER_OUTSIDE_WINDOW')
        active=active_proposal(ledger);scope=active.get('target_scope')
        require(scope in ('NEW_CASH_CURRENT_QUOTE_ALLOCATION','MONTHLY_CURRENT_QUOTE_ALLOCATION'),
                'CONTINUATION_SCOPE_UNSUPPORTED')
        require(active['target_month']==session[:7], 'RESELECT_REQUIRED')
        require(all(o['closed'] in ('FILLED','EXPIRED','CANCELLED') for o in ledger['orders'].values())
                and ledger['reserved_cash']=='0' and not any(ledger['reserved_shares'].values()), 'PRIOR_ORDERS_OPEN')
        require(callable(source_admission_guard), 'SOURCE_ADMISSION_GUARD_REQUIRED')
        causal=active['causal_inputs']
        pins=(causal['frozen_execution_package']['source_hashes']
              if scope=='NEW_CASH_CURRENT_QUOTE_ALLOCATION' else causal['source_hashes'])
        source_admission_guard(deepcopy(pins))
        base=Path(root).resolve();path=(base/schedule_path).resolve()
        require(path.is_relative_to(base) and not Path(schedule_path).is_absolute(), 'INVALID_SIMULATION_SCHEDULE_PATH')
        raw=path.read_bytes()
        require(sha256(raw).hexdigest()==schedule_sha256, 'SIMULATION_SCHEDULE_CHANGED')
        schedule=json.loads(raw)
        require(schedule['schema']=='SCHEDULED_REGULAR_SESSIONS_V1', 'SIMULATION_SCHEDULE_SCHEMA')
        rows=[r for r in schedule['sessions'] if r['date']==session]
        require(len(rows)==1,'SIMULATION_SESSION_NOT_SCHEDULED')
        observed=build_observation_clock([dict(rows[0],timezone=rows[0].get('timezone','America/New_York'))])[0]
        require(stamp(observed['observation_at'])<=trigger<stamp(observed['session_close']), 'SIMULATION_TRIGGER_OUTSIDE_WINDOW')
        last=[max(trigger,last_at)]
        def actual_clock():
            now=stamp(clock())
            require(last[0]<=now<stamp(observed['session_close']), 'SIMULATION_CLOCK_OUTSIDE_SESSION')
            last[0]=now;return now
        actual_clock()
        storage=Path(storage_directory)/digest([simulation_id,session,operation_id])
        if scope=='NEW_CASH_CURRENT_QUOTE_ALLOCATION':
            require(callable(unit_review_reader), 'UNIT_REVIEW_SOURCE_UNAVAILABLE')
            sources=CurrentCashContinuationSources(root=root,unit_review_reader=unit_review_reader,
                fetch=fetch,clock=actual_clock,pullback_policy=pullback_policy,
                pullback_cap_store=pullback_cap_store,audit_storage_root=storage)
        else:
            require(monthly_blob_root is not None and monthly_review_reader is not None, 'MONTHLY_ORIGIN_ARCHIVE_REQUIRED')
            sources=QuantityV2MonthlyContinuationSources(storage_root=storage,monthly_blob_root=monthly_blob_root,
                review_reader=monthly_review_reader,fetch=fetch,clock=actual_clock,
                pullback_policy=pullback_policy,pullback_cap_store=pullback_cap_store)
        sources.capture(state)
        bridge=QuantityV2ContinuationSourceBridge(store=_ReadOnlyChain(state),resolver=sources.resolve,clock=actual_clock)
        preview=bridge.preview(account_id=ledger['account_id'],expected_revision=ledger['revision'])
        source_admission_guard(deepcopy(pins))
        if not preview['orders']:return simulation
        proposal=bridge.continuation_resolver(state,preview['proposal_id'],actual_clock())
        source_admission_guard(deepcopy(pins))
        return accept_orders(simulation=simulation,proposal=proposal,
            acceptance_id='daily-continuation-'+session,accepted_at=actual_clock().isoformat(),kind='CONTINUATION')
    result=store.apply(simulation_id=simulation_id,expected_revision=expected_revision,
        operation_id=operation_id,request=request,transform=transform)
    return dict(result,continuation_status='NO_ORDERS' if result['operation_result_revision']==expected_revision else 'SIMULATED_CONTINUATION_ACCEPTED')
