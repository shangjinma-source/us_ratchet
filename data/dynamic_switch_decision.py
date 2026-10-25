"""Finite first-version research signal, preserving monthly risk restrictions.

Differences are desired holdings, never executable orders. A separate execution
layer must price orders, wait for fills, and revalidate account cash/revision.
"""
from fractions import Fraction
from data.dynamic_switch_risk_comparison import compare_with_monthly_exit


def decide_dynamic_switch(*, account_revision, pending_orders, **inputs):
    if not isinstance(account_revision, str) or not account_revision.strip():
        raise ValueError('ACCOUNT_REVISION_REQUIRED')
    if type(pending_orders) is not list:
        raise ValueError('EXPLICIT_PENDING_ORDERS_REQUIRED')
    base = dict(account_revision=account_revision, research_only=True,
                orders_created=False, production_changes=False,
                signal_date=inputs['history_inputs']['signal_date'],
                risk_anchor=inputs['history_inputs']['base_target']['monthly_decision_date'])
    if pending_orders:
        return dict(base, status='WAIT_PENDING_ORDERS', targets=None, target_differences=[])
    comparison = compare_with_monthly_exit(**inputs)
    equity = Fraction(comparison['candidate_comparison']['equity'])
    if any(q * Fraction(inputs['prices'][sid]) > equity / 2
           for sid, q in inputs['candidate'].items()):
        raise ValueError('CANDIDATE_EXCEEDS_EXISTING_CAP50')
    switch = comparison['ranking'] == 'SWITCH_HIGHER'
    targets = comparison['candidate_targets'] if switch else comparison['retain_targets']
    differences = []
    for sid in sorted(set(inputs['holdings']) | set(targets)):
        delta = targets.get(sid, 0) - inputs['holdings'].get(sid, 0)
        if delta:
            differences.append(dict(security_id=sid, side='BUY' if delta > 0 else 'SELL', quantity=abs(delta)))
    status = 'SWITCH_SIGNAL' if switch else 'RISK_EXIT_SIGNAL' if differences else 'RETAIN_SIGNAL'
    return dict(base, status=status, targets=targets, target_differences=differences,
                comparison=comparison,
                rule='STRICTLY_HIGHER_COMMON_TRAINING_SCORE_ELSE_RETAIN_AFTER_RISK',
                execution_required='Reprice and revalidate cash after actual fills; expected sale proceeds are unavailable')
