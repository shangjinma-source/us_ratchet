"""Research adapter: same-identity split coordinates for a monthly peak rule.

Caller must verify the action bundle's source hashes. Unsupported exposed actions
fail closed. This module does not fetch prices, trade, or change production policy.
"""
from copy import deepcopy
from fractions import Fraction


class SplitAwareMonthlyPeak:
    def __init__(self, risk, actions):
        self.risk = risk
        self.actions = deepcopy(actions)
        self.last_day = None
        self.processed = set()

    def apply(self, *, day, month, target, closes, adjustments=()):
        if self.last_day is not None and day <= self.last_day:
            raise ValueError('RISK_SESSION_MUST_ADVANCE')
        trial = deepcopy(self.risk)
        processed = set(self.processed)
        for change in adjustments:
            sid = change['security_id']
            key = (change['date'], sid)
            if key in processed or change['date'] != day:
                raise ValueError('DUPLICATE_OR_NONCURRENT_SPLIT')
            matches = [a for a in self.actions if (a['date'], a['security_id']) == key]
            if len(matches) != 1:
                raise ValueError('UNIQUE_SPLIT_EVIDENCE_REQUIRED')
            event = matches[0]
            if event['type'] != 'split' or change.get('new_security_id') != sid:
                raise ValueError('SAME_ID_SPLIT_ONLY')
            refs = event.get('source_references')
            if not isinstance(refs, list) or not refs or not all(isinstance(r, str) and r for r in refs):
                raise ValueError('SPLIT_SOURCE_REQUIRED')
            if any(isinstance(event.get(k), bool) for k in ('old_shares', 'new_shares')):
                raise ValueError('POSITIVE_SPLIT_RATIO_REQUIRED')
            old, new = Fraction(event['old_shares']), Fraction(event['new_shares'])
            if old <= 0 or new <= 0:
                raise ValueError('POSITIVE_SPLIT_RATIO_REQUIRED')
            if trial.month == month:
                if sid not in trial.peaks:
                    raise ValueError('EXPOSED_PEAK_REQUIRED')
                trial.peaks[sid] = Fraction(trial.peaks[sid]) * old / new
            # A new month starts with that day's post-split close, no old peak.
            processed.add(key)
        result = trial.apply(day=day, month=month, target=target, closes=closes, adjustments=())
        self.risk, self.processed, self.last_day = trial, processed, day
        return result
