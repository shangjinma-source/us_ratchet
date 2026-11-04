"""Research-only same-economic-claim identity split bridge; original month reset."""
from copy import deepcopy
from fractions import Fraction
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
from backtest.dynamic_risk_units import reviewed_split_schedule, migrate_risk_splits


class SplitIdentityMonthlyRiskAdapter(MonthlyExitCoreResearchAdapter):
    def apply(self, *, day, month, target, closes, adjustments=()):
        # Work on a trial: neither evidence failure nor core rejection advances state.
        trial = MonthlyExitCoreResearchAdapter(self.actions)
        trial.state, trial.last_day = deepcopy(self.state), self.last_day
        normal, schedule, seen = [], [], set()
        for change in adjustments:
            key = (change['date'], change['security_id'])
            if key in seen or key[0] != day:
                raise ValueError('DUPLICATE_OR_NONCURRENT_ACTION')
            seen.add(key)
            matches = [e for e in self.actions if (e['date'], e['security_id']) == key]
            if len(matches) != 1:
                raise ValueError('UNIQUE_ACTION_EVIDENCE_REQUIRED')
            event = matches[0]
            if event['type'] != 'split_identity':
                normal.append(change)
                continue
            old, new = event['security_id'], event.get('new_security_id')
            if not new or new == old or change.get('new_security_id') != new:
                raise ValueError('SPLIT_IDENTITY_SUCCESSOR_MISMATCH')
            refs = event.get('source_references')
            if not isinstance(refs, list) or not refs or not all(isinstance(x, str) and x for x in refs):
                raise ValueError('SPLIT_SOURCE_REQUIRED')
            if any(isinstance(event.get(k), bool) for k in ('old_shares', 'new_shares')):
                raise ValueError('POSITIVE_SPLIT_RATIO_REQUIRED')
            if Fraction(event['old_shares']) <= 0 or Fraction(event['new_shares']) <= 0:
                raise ValueError('POSITIVE_SPLIT_RATIO_REQUIRED')
            prior_unit = (trial.state or {}).get('unit_ids', {}).get(old, 'research-nominal:' + old)
            schedule.append(dict(event, event_id='identity-split:' + day + ':' + old,
                                 old_unit_id=prior_unit, new_unit_id='research-nominal:' + new + ':' + day))
        reviewed = reviewed_split_schedule(schedule)
        # Keep V27 reset exactly as-is; an identity event does not retain last month's peak.
        applied = []
        if trial.state is not None and trial.state['decision_date'] == month:
            trial.state, applied = migrate_risk_splits(trial.state, through_date=day, events=reviewed)
        effective, diagnostics = trial.apply(day=day, month=month, target=target,
                                             closes=closes, adjustments=normal)
        diagnostics['identity_split_migrations'] = applied
        self.state, self.last_day = trial.state, trial.last_day
        return effective, diagnostics
