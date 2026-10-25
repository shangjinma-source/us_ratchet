"""Per-security half-exposure latch; no prices, execution, IO or clock reads."""
from copy import deepcopy
from datetime import date


class MonthlyHalfLatch:
    def __init__(self):
        self.monthly_decision_date = None
        self.latched = set()

    def advance(self, monthly_decision_date=None, adjustments=()):
        if monthly_decision_date is not None:
            date.fromisoformat(monthly_decision_date)
            if self.monthly_decision_date is not None and monthly_decision_date < self.monthly_decision_date:
                raise ValueError('LATCH_MONTH_REVERSED')
            if monthly_decision_date != self.monthly_decision_date:
                self.monthly_decision_date = monthly_decision_date
                self.latched = set()
                return
        updated = set(self.latched)
        for item in adjustments:
            old = item['security_id']
            new = item.get('new_security_id', old)
            if old not in updated:
                continue
            if item.get('target_after') == 0:
                updated.discard(old)
            elif new != old:
                updated.discard(old)
                updated.add(new)
        self.latched = updated

    def apply(self, risk, monthly_ceiling):
        if self.monthly_decision_date is None:
            raise ValueError('LATCH_MONTH_REQUIRED')
        if risk['base_target']['monthly_decision_date'] != self.monthly_decision_date:
            raise ValueError('LATCH_TARGET_MONTH_MISMATCH')
        if risk['base_target']['quantities'] != monthly_ceiling:
            raise ValueError('LATCH_CEILING_MISMATCH')
        updated = set(self.latched) & set(monthly_ceiling)
        result = deepcopy(risk)
        quantities = {}
        for sid, ceiling in monthly_ceiling.items():
            if type(ceiling) is not int or ceiling < 0:
                raise ValueError('INVALID_LATCH_CEILING')
            if not ceiling:
                quantities[sid] = 0
                continue
            on = risk['diagnostics'][sid]['on']
            if type(on) is not bool:
                raise ValueError('BOOLEAN_TREND_REQUIRED')
            if not on:
                updated.add(sid)
            quantities[sid] = ceiling // 2 if sid in updated else ceiling
        result['target_quantities'] = quantities
        result['policy'] = 'CONTINUOUS32_MONTHLY_LATCHED_HALF_RESEARCH'
        result['monthly_latch'] = dict(monthly_decision_date=self.monthly_decision_date,
            latched_security_ids=sorted(updated), reset='NEW_SUCCESSFUL_MONTHLY_SELECTION_ONLY',
            rounding='FLOOR_ADJUSTED_MONTHLY_CEILING_NOT_CURRENT_HOLDINGS')
        self.latched = updated
        return result
