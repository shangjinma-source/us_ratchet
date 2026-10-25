"""Research-only adapter around the deployed monthly exit function.

Same-identity splits explicitly migrate price coordinates. Unsupported exposed
actions stop replay; this does not authorize migrations in the live account.
"""
from copy import deepcopy
from fractions import Fraction

from core.monthly_peak_exit import advance_monthly_exit


class MonthlyExitCoreResearchAdapter:
    def __init__(self, actions=()):
        self.actions = deepcopy(actions)
        self.state = None
        self.last_day = None

    def apply(self, *, day, month, target, closes, adjustments=()):
        if self.last_day is not None and day <= self.last_day:
            raise ValueError('RISK_SESSION_MUST_ADVANCE')
        previous = deepcopy(self.state)
        units = {security: 'research-nominal:' + security for security in closes}
        if previous is not None and previous['decision_date'] == month:
            units.update(previous['unit_ids'])
        seen = set()
        for change in adjustments:
            security = change['security_id']
            key = (change['date'], security)
            if key in seen or change['date'] != day:
                raise ValueError('DUPLICATE_OR_NONCURRENT_ACTION')
            seen.add(key)
            matches = [a for a in self.actions if (a['date'], a['security_id']) == key]
            if len(matches) != 1:
                raise ValueError('UNIQUE_ACTION_EVIDENCE_REQUIRED')
            event = matches[0]
            if event['type'] != 'split' or change.get('new_security_id') != security:
                raise ValueError('SAME_ID_SPLIT_ONLY')
            references = event.get('source_references')
            if not isinstance(references, list) or not references or not all(
                isinstance(reference, str) and reference for reference in references
            ):
                raise ValueError('SPLIT_SOURCE_REQUIRED')
            if any(isinstance(event.get(key), bool) for key in ('old_shares', 'new_shares')):
                raise ValueError('POSITIVE_SPLIT_RATIO_REQUIRED')
            old, new = Fraction(event['old_shares']), Fraction(event['new_shares'])
            if old <= 0 or new <= 0:
                raise ValueError('POSITIVE_SPLIT_RATIO_REQUIRED')
            if previous is not None and previous['decision_date'] == month:
                if security not in previous['peaks']:
                    raise ValueError('EXPOSED_PEAK_REQUIRED')
                previous['peaks'][security] = str(Fraction(previous['peaks'][security]) * old / new)
                previous['last_closes'][security] = str(Fraction(previous['last_closes'][security]) * old / new)
                units[security] += ':' + day
                previous['unit_ids'][security] = units[security]
        if not closes:
            if any(target.values()) or (previous is not None and previous['decision_date'] == month and previous['peaks']):
                raise ValueError('RISK_TRACKED_PRICE_MISSING')
            self.state, self.last_day = None, day
            return dict(target), {'empty_target': True}
        outcome = advance_monthly_exit(
            state=previous, account_id='isolated-research', decision_date=month,
            session_date=day, closes=closes, unit_ids=units, baseline_targets=target)
        self.state, self.last_day = outcome['state'], day
        return outcome['effective_target_quantities'], deepcopy(outcome)
