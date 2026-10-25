"""One-way quantity reduction after an observed 50% holding-weight breach.

Research only. The caller supplies completed-close prices and already adjusted
holdings. Missing funding or a partial initial fill never latches the target down.
"""
from copy import deepcopy
from fractions import Fraction


class MonthlyDriftCap:
    def __init__(self, actions=()):
        self.actions = deepcopy(actions)
        self.month = None
        self.last_day = None
        self.ceilings = {}

    def apply(self, *, day, month, baseline_targets, risk_targets, shares, cash,
              closes, adjustments=()):
        if self.last_day is not None and day <= self.last_day:
            raise ValueError('DRIFT_SESSION_MUST_ADVANCE')
        if month > day or (self.month is not None and month < self.month):
            raise ValueError('DRIFT_INVALID_MONTH_BINDING')
        if set(baseline_targets) != set(risk_targets):
            raise ValueError('DRIFT_TARGET_DOMAIN_MISMATCH')
        if any(type(q) is not int or q < 0 for mapping in
               (baseline_targets, risk_targets, shares) for q in mapping.values()):
            raise ValueError('DRIFT_INVALID_QUANTITY')
        if any(risk_targets[sid] > quantity for sid, quantity in baseline_targets.items()):
            raise ValueError('DRIFT_RISK_CANNOT_INCREASE_TARGET')
        prices = {sid: Fraction(value) for sid, value in closes.items()}
        if any(price <= 0 for price in prices.values()) or Fraction(cash) < 0:
            raise ValueError('DRIFT_INVALID_CASH_OR_PRICE')
        needed = set(baseline_targets) | {sid for sid, quantity in shares.items() if quantity}
        if not needed <= set(prices):
            raise ValueError('DRIFT_MISSING_COMPLETED_CLOSE')
        equity = Fraction(cash) + sum((quantity * prices[sid] for sid, quantity
                                      in shares.items() if quantity), Fraction(0))
        if equity <= 0:
            raise ValueError('DRIFT_NONPOSITIVE_TRADABLE_EQUITY')
        resetting = month != self.month
        ceilings = dict(baseline_targets) if resetting else dict(self.ceilings)
        if not resetting:
            seen = set()
            for change in adjustments:
                key = change['date'], change['security_id']
                if key in seen or change['date'] != day:
                    raise ValueError('DRIFT_DUPLICATE_OR_NONCURRENT_ACTION')
                seen.add(key)
                matches = [a for a in self.actions if (a['date'], a['security_id']) == key]
                if len(matches) != 1:
                    raise ValueError('DRIFT_UNIQUE_SPLIT_EVIDENCE_REQUIRED')
                event = matches[0]
                sid = change['security_id']
                if event['type'] != 'split' or change.get('new_security_id') != sid:
                    raise ValueError('DRIFT_SAME_ID_SPLIT_ONLY')
                if not event.get('source_references'):
                    raise ValueError('DRIFT_SPLIT_SOURCE_REQUIRED')
                numerator, denominator = Fraction(event['new_shares']), Fraction(event['old_shares'])
                if numerator <= 0 or denominator <= 0:
                    raise ValueError('DRIFT_INVALID_SPLIT_RATIO')
                if sid in ceilings:
                    ceilings[sid] = int(ceilings[sid] * numerator / denominator)
            if set(ceilings) != set(baseline_targets):
                raise ValueError('DRIFT_TARGET_CHANGE_REQUIRES_NEW_MONTH')
        reductions = []
        for sid, raw_quantity in baseline_targets.items():
            ceilings[sid] = min(ceilings[sid], raw_quantity)
            holding = shares.get(sid, 0)
            limit = int(equity / (2 * prices[sid]))
            if holding * prices[sid] > equity / 2 and limit < ceilings[sid]:
                reductions.append(dict(security_id=sid, before=ceilings[sid], after=limit,
                                       held=holding, close=str(prices[sid]),
                                       weight=str(holding * prices[sid] / equity)))
                ceilings[sid] = limit
        effective = {sid: min(risk_targets[sid], ceilings[sid]) for sid in ceilings}
        self.month, self.last_day, self.ceilings = month, day, ceilings
        return effective, dict(policy='MONTHLY_ONE_WAY_DRIFT_CAP50', month=month,
                               day=day, reset=resetting, tradable_equity=str(equity),
                               ceiling=dict(ceilings), reductions=reductions,
                               effective_targets=dict(effective), research_only=True)
