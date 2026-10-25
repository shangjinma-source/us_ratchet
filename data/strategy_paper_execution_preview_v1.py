"""Verified paper daily signal to conditional limits/differences, never orders.

Independent temporary cap evidence; no task, live account, or web permission.
Reviewed unit hashes must be supplied by the owning server, not an HTTP caller.
"""
from copy import deepcopy
import ast
from hashlib import sha256
import json
from pathlib import Path
from backtest.current_strategy_paper_slice_v1 import replay, project
from core.strategy_account_ledger import canonical
from core.strategy_account_difference import require, timestamp, build_strategy_difference
from data.strategy_daily_target_gate import resolve_daily_target
from data.strategy_paper_daily_signal_v1 import verify_paper_daily_signal, CODE_PATHS as DAILY_PINS
from data.strategy_execution_limits_common_v1 import _build_execution_limits_core
from data.strategy_paper_execution_caps_v1 import PaperExecutionCaps

ROOT=Path(__file__).resolve().parents[1]
SCOPE='ISOLATED_CURRENT_STRATEGY_PAPER_TEMPORARY_EXECUTION_PREVIEW_ONLY'
CODE_PATHS=set(DAILY_PINS)|{
    'data/strategy_paper_execution_preview_v1.py','data/strategy_paper_execution_caps_v1.py',
    'data/strategy_execution_limits_common_v1.py','data/strategy_daily_target_gate.py',
    'data/strategy_account_mark_reference.py','data/current_quantity_v2_pullback_runtime.py',
    'data/strategy_halt_aware_pullback_cap_store_v2.py','data/strategy_halt_aware_pullback_cap_store_v1.py',
    'data/strategy_halt_aware_pullback_sources_v1.py','data/strategy_halt_aware_pullback_entry_v1.py',
    'data/strategy_execution_halt_evidence_v1.py','data/strategy_halt_gap_diagnostic_v1.py',
    'data/strategy_account_live_pullback_sources.py','data/strategy_account_live_pullback_entry.py',
}


def _local_import_closure(paths):
    """Pin transitive local imports too; no source execution or rewriting."""
    result=set(paths);pending=list(paths)
    while pending:
        path=pending.pop()
        for node in ast.walk(ast.parse((ROOT/path).read_text(encoding='utf-8-sig'))):
            modules=([node.module] if isinstance(node,ast.ImportFrom) and node.module else
                [alias.name for alias in node.names] if isinstance(node,ast.Import) else [])
            for module in modules:
                dependency=module.replace('.','/')+'.py'
                if (ROOT/dependency).is_file() and dependency not in result:
                    result.add(dependency);pending.append(dependency)
    return result


CODE_PATHS=_local_import_closure(CODE_PATHS)
BUY_WAIT_ERRORS={'RAW_NUMERIC_REQUIRED','MINUTE_GAP','UNEXPLAINED_NULL_MINUTE','RAW_NOT_MINUTE_ALIGNED',
    'HALT_ACTIVE_OR_RESUME_UNCONFIRMED','HALT_EXECUTION_EVIDENCE_REQUIRED','HALT_SOURCE_CLOCK_OR_STALE',
    'POST_RESUMPTION_COMPLETE_BAR_REQUIRED','NONCONTIGUOUS_OR_FUTURE_MINUTE','INCOMPLETE_SESSION_MINUTES',
    'PARTIAL_NULL_MINUTE','ZERO_VOLUME_MINUTE_UNAVAILABLE'}


def preview_paper_execution(*, daily_arguments, application_bytes, trusted_application_sha256,
        market_capture, unit_review, trusted_unit_review_sha256, caps, clock,
        sell_market_capture=None, sell_unit_review=None, trusted_sell_unit_review_sha256=None):
    require(callable(clock),'SERVER_CLOCK_REQUIRED')
    started=timestamp(clock())
    original_arguments=deepcopy(daily_arguments)
    snapshot=deepcopy(original_arguments)
    book=replay(snapshot['book']);state=project(book)
    state['orders']={o['order_id']:dict(o,status='OPEN') for o in state['pending_orders']}
    require(type(application_bytes) is bytes and sha256(application_bytes).hexdigest()==trusted_application_sha256,
        'PAPER_EXECUTION_APPLICATION_HASH')
    app=json.loads(application_bytes)
    require(app.get('schema')=='PAPER_EXECUTION_APPLICATION_V1' and app.get('scope')==SCOPE and
        app.get('authorized') is True and app.get('automatic_acceptance_allowed') is False,'PAPER_EXECUTION_SCOPE')
    require(app['account_id']==state['account_id'] and
        app['account_genesis_sha256']==sha256(canonical(book['application'])).hexdigest() and
        app['daily_application_sha256']==snapshot['trusted_application_sha256'],'PAPER_EXECUTION_BINDING')
    require(timestamp(app['approved_at'])<=timestamp(app['valid_from'])<=started<timestamp(app['valid_until']),
        'PAPER_EXECUTION_APPLICATION_TIME')
    require(set(app['code_sha256'])==CODE_PATHS and all(sha256((ROOT/p).read_bytes()).hexdigest()==h
        for p,h in app['code_sha256'].items()),'PAPER_EXECUTION_CODE_CHANGED')
    require(type(caps) is PaperExecutionCaps,'PAPER_PRIVATE_CAP_REQUIRED');caps.validate(book)
    require(app['cap_namespace_id']==caps.namespace_id,'PAPER_CAP_NAMESPACE_REPLACED')
    snapshot['now']=started.isoformat()
    daily=verify_paper_daily_signal(**snapshot)
    base=dict(schema='VERIFIED_PAPER_EXECUTION_PREVIEW_V1',account_revision=state['revision'],
        account_id=state['account_id'],account_genesis_sha256=app['account_genesis_sha256'],
        daily_application_sha256=app['daily_application_sha256'],cap_namespace_id=caps.namespace_id,
        application_sha256=trusted_application_sha256,daily=daily,orders_created=False,account_mutated=False,
        automatic_acceptance_allowed=False,cap_persistence='TEMPORARY_REVIEW_SESSION_ONLY')
    if daily['status']!='DAILY_SIGNAL_READY':
        return dict(base,status=daily['status'],new_orders=[],limits={})
    signal=daily['signal'];selection=snapshot['selection_result']
    gate=resolve_daily_target(account_id=state['account_id'],account_revision=state['revision'],
        target_id=selection['decision_id'],target_month=selection['payload']['target_month'],
        monthly_quantities=selection['payload']['target_quantities'],strategy_shares=state['shares'],
        available_cash=state['available_cash'],pending_orders=state['pending_orders'],now=started.isoformat(),
        expected_policy_id=signal['policy_id'],signal=signal)
    if gate['status']!='DAILY_TARGET_READY' or any(r['reason']=='PENDING_RECONCILIATION_REQUIRED' for r in gate['rows']):
        return dict(base,status='WAIT_PENDING_RECONCILIATION' if gate['status']=='DAILY_TARGET_READY' else gate['status'],
            daily_gate=gate,new_orders=[],limits={})
    effective=gate['effective_target_quantities'];execution=deepcopy(effective)
    failure=None;waiting=[];proof_start=len(caps.proofs)
    def limits(package,review,review_hash,quantities):
        require(sha256(canonical(review)).hexdigest()==review_hash,'PAPER_UNIT_REVIEW_HASH')
        return _build_execution_limits_core(state=state,target_quantities=quantities,
            market_capture=package,unit_review=review,cap_store=caps,now=clock())
    try:
        evidence=limits(market_capture,unit_review,trusted_unit_review_sha256,execution)
    except ValueError as error:
        if str(error) not in BUY_WAIT_ERRORS:raise
        failure=dict(reason=str(error),source_hashes=deepcopy(market_capture['source_hashes']),
            unit_review_sha256=trusted_unit_review_sha256)
        execution={sid:min(q,state['shares'].get(sid,0)) for sid,q in effective.items()}
        waiting=[dict(security_id=sid,quantity=q-state['shares'].get(sid,0),reason='WAIT_BUY_MINUTE_DATA')
            for sid,q in effective.items() if q>state['shares'].get(sid,0)]
        if not any(q<state['shares'].get(sid,0) for sid,q in execution.items()):
            return dict(base,status='WAIT_BUY_MINUTE_DATA',effective_target_quantities=effective,
                new_orders=[],limits={},waiting_data=waiting,buy_data_failure=failure)
        require(sell_market_capture is not None and sell_unit_review is not None,'PAPER_INDEPENDENT_SELL_CAPTURE_REQUIRED')
        evidence=limits(sell_market_capture,sell_unit_review,trusted_sell_unit_review_sha256,execution)
    finished=timestamp(clock())
    require(finished>=started,'SERVER_CLOCK_MOVED_BACKWARDS')
    require(finished<timestamp(app['valid_until']) and timestamp(signal['valid_from'])<=finished<timestamp(signal['valid_until']),
        'PAPER_SIGNAL_EXPIRED_DURING_PREVIEW')
    require(all(finished<timestamp(ref['reference_valid_until']) for ref in evidence['limits'].values()),'REQUOTE_REQUIRED')
    require(daily_arguments==original_arguments,'PAPER_INPUT_CHANGED_DURING_PREVIEW')
    difference=build_strategy_difference(account_id=state['account_id'],account_revision=state['revision'],
        holdings_revision=state['revision'],cash_confirmed_for_holdings_revision=state['revision'],
        cash_balance=state['cash'],cash_basis='TOTAL_UNINVESTED',strategy_shares=state['shares'],legacy_shares={},
        pending_orders=state['pending_orders'],target_quantities=execution,now=finished.isoformat(),
        maximum_mark_age_seconds=120,fee_bps=book['application']['fee_bps'],**evidence)
    require(failure is None or all(o['side']=='SELL' for o in difference['new_orders']),'PAPER_SELL_ONLY_VIOLATION')
    final=timestamp(clock())
    require(final>=finished,'SERVER_CLOCK_MOVED_BACKWARDS')
    require(final<min(timestamp(app['valid_until']),timestamp(signal['valid_until']),
        *(timestamp(ref['reference_valid_until']) for ref in evidence['limits'].values())), 'REQUOTE_REQUIRED')
    require(daily_arguments==original_arguments,'PAPER_INPUT_CHANGED_DURING_PREVIEW')
    return dict(base,status='CONDITIONAL_SELL_PREVIEW_BUYS_WAIT' if failure else
        ('CONDITIONAL_PREVIEW_READY' if difference['new_orders'] else 'HOLD'),daily_gate=gate,
        effective_target_quantities=effective,execution_quantities=execution,new_orders=difference['new_orders'],
        difference=difference,limits=evidence['limits'],waiting_data=waiting,buy_data_failure=failure,
        cap_proofs=deepcopy(caps.proofs[proof_start:]),finished_at=final.isoformat(),
        input_binding=dict(target_id=selection['decision_id'],evidence_id=signal['evidence_id'],
            primary_source_hashes=deepcopy(market_capture['source_hashes']),
            primary_unit_review_sha256=trusted_unit_review_sha256,
            sell_source_hashes=deepcopy(sell_market_capture['source_hashes']) if failure else None,
            sell_unit_review_sha256=trusted_sell_unit_review_sha256 if failure else None))
