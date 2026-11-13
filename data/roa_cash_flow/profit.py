"""Isolated amount-only profit reconciliation. No account writes or return rate."""
from datetime import datetime
from fractions import Fraction as F
from data.strategy_restart_performance import restart_performance
from .audit import audit_cash_changes
from .validation import validate_classification
from core.broker_transfer_cash_reconciliation import reconcile_transfer_cash


def amount_profit(*, baseline, baseline_account, current_account, valuation, classifications, now, transfer_context=None):
    """Transfer context is trusted internal input, including journal receipt times.

    Baseline valuation excludes in-transit assets; adjustments add them at both
    endpoints. This optional path is not yet mounted by the production addon.
    """
    def require(ok, reason):
        if not ok:
            raise ValueError(reason)
    require(now.utcoffset() is not None, 'AWARE_CLOCK_REQUIRED')
    initial = restart_performance(baseline=baseline, valuations=[baseline['valuation_evidence']])
    require(initial['status'] == 'READY_RECONCILED_NO_EXTERNAL_FLOW' and initial['return_fraction'] == '0', 'INVALID_BASELINE')
    require(baseline_account['revision'] == baseline['account_revision'], 'BASELINE_REVISION_MISMATCH')
    require(F(baseline_account['total_uninvested_cash']) == F(baseline['cash']), 'BASELINE_CASH_MISMATCH')
    require({k:v for k,v in baseline_account['shares'].items() if v} == {r['security_id']:r['quantity'] for r in baseline['holdings'] if r['quantity']}, 'BASELINE_HOLDINGS_MISMATCH')
    audit = audit_cash_changes(baseline=baseline_account, current=current_account)
    require(current_account['cash_confirmation_valid'] and valuation['account_revision'] == current_account['revision'], 'CURRENT_ACCOUNT_UNCONFIRMED')
    at = datetime.fromisoformat(valuation['valued_at'])
    start = datetime.fromisoformat(baseline['effective_at'])
    require(at.utcoffset() is not None and start <= at and 0 <= (now-at).total_seconds() <= 120, 'VALUATION_TIME_INVALID')
    synthetic = dict(initial_equity=valuation['strategy_total'], cash=current_account['total_uninvested_cash'], effective_at=valuation['valued_at'], account_revision=current_account['revision'], holdings=[dict(security_id=k, quantity=v) for k,v in current_account['shares'].items() if v])
    check = restart_performance(baseline=synthetic, valuations=[valuation])
    require(check['status'] == 'READY_RECONCILED_NO_EXTERNAL_FLOW' and check['return_fraction'] == '0', 'CURRENT_VALUATION_INVALID')
    known = {row['event_id'] for row in audit['confirmations']}
    require(set(classifications) <= known, 'UNKNOWN_CLASSIFICATION_EVENT')
    reconciliation=None
    residuals={}
    context=None
    if transfer_context is not None:
        require(type(transfer_context)is dict and set(transfer_context)=={
            'transfer_state','expected_transfer_revision','links','confirmation_times'},
            'TRANSFER_CONTEXT_FIELDS')
        context=dict(transfer_context,baseline_at=start,valued_at=at)
        reconciliation=reconcile_transfer_cash(baseline_account=baseline_account,
            current_account=current_account,now=now,**context)
        require(not reconciliation['unlinked_transfer_events'],'UNLINKED_TRANSFER_EVENTS')
        residuals={r['cash_event_id']:r['residual_cash_change'] for r in reconciliation['rows']}
    external = F(0)
    for row in audit['confirmations']:
        document = classifications.get(row['event_id'])
        if document is None:
            require(F(residuals.get(row['event_id'],row['unexplained_net_change'])) == 0, 'UNCLASSIFIED_CASH_CHANGE')
            continue
        result = validate_classification(baseline=baseline_account, current=current_account, document=document, now=now, transfer_context=context)
        require(not result['performance_blocked'], 'ACCOUNT_FACT_REPAIR_REQUIRED')
        require(all(start <= datetime.fromisoformat(item['effective_at']) <= at for item in document['items']), 'FLOW_OUTSIDE_PERFORMANCE_PERIOD')
        if context is not None:
            receipt=datetime.fromisoformat(context['confirmation_times'][row['event_id']])
            require(all(datetime.fromisoformat(item['effective_at']) <= receipt for item in document['items']), 'FLOW_AFTER_CASH_CONFIRMATION')
        external += F(result['net_external_flow'])
    profit = F(valuation['strategy_total'])-F(baseline['initial_equity'])-external
    if reconciliation is not None:profit += F(reconciliation['asset_adjustment_change'])
    return dict(transfer_reconciliation=reconciliation, status='AMOUNT_ONLY_RECONCILED', profit_amount=str(profit), net_external_flow=str(external), return_fraction=None, maximum_drawdown_fraction=None, account_mutated=False, limitation='Classification facts require trusted receipt validation before persistence. No time-weighted return or drawdown is established.')
