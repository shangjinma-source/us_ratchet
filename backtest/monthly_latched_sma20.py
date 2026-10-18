"""Research-only SMA20 exits with no re-entry before actual monthly selection."""
from copy import deepcopy
from backtest.current_quantity_v2_risk_overlays import sma20_target


class MonthlyLatchedSma20:
    def __init__(self):
        self.monthly_decision_date = None
        self.latched = {}

    def migrate(self, adjustments):
        updated = dict(self.latched)
        for row in adjustments:
            old = row['security_id']; new = row.get('new_security_id')
            if row.get('reason') == 'TERMINATED_MIXED_ENTITLEMENT':
                if row['target_after'] != 0: raise ValueError('INVALID_LATCH_TERMINATION')
                updated.pop(old, None)
                continue
            if not isinstance(new, str) or not new: raise ValueError('LATCH_MIGRATION_UNPROVEN')
            if old not in updated and row['target_after']:
                raise ValueError('LATCH_MIGRATION_ORIGIN_MISSING')
            if old != new:
                old_latched = updated.pop(old, False)
                updated[new] = updated.get(new, False) or old_latched
        self.latched = updated

    def target(self, *, actual_monthly_selection=False, **kwargs):
        result = deepcopy(sma20_target(**kwargs))
        monthly = kwargs['base_target']['monthly_decision_date']
        if actual_monthly_selection:
            if monthly != kwargs['signal_date'] or (self.monthly_decision_date is not None and monthly <= self.monthly_decision_date):
                raise ValueError('LATCH_RESET_REQUIRES_NEW_ACTUAL_MONTHLY_SELECTION')
            updated = {sid:False for sid in kwargs['base_target']['quantities']}
        else:
            if monthly != self.monthly_decision_date: raise ValueError('LATCH_MONTH_CHANGED_WITHOUT_SELECTION')
            updated = dict(self.latched)
        before = dict(updated)
        for sid, diagnostic in result['diagnostics'].items():
            if sid not in updated: raise ValueError('LATCH_TARGET_DOMAIN_CHANGED_WITHOUT_MIGRATION')
            updated[sid] = updated[sid] or not diagnostic['on']
            result['target_quantities'][sid] = 0 if updated[sid] else diagnostic['monthly_ceiling']
            diagnostic.update(latched_before=before[sid], latched_after=updated[sid],
                              actual_monthly_reset=actual_monthly_selection)
        self.latched = updated; self.monthly_decision_date = monthly
        result.update(policy='SMA20_MONTHLY_LATCH_FULL_EXIT_RESEARCH',
                      parameter_authority='RESEARCH_HYPOTHESIS_NOT_USER_THRESHOLD',
                      latch_state=deepcopy(updated), actual_monthly_reset=actual_monthly_selection)
        return result
