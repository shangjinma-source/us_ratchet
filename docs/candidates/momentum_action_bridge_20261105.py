"""Isolated target/risk action bridge; never authorizes merger cash release."""
from copy import deepcopy
from fractions import Fraction as F
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
from backtest.continuous_guided_cost_monthly_provider import build_cost_monthly_quantity_provider


def build_provider(*, actions, **kwargs):
    translated = deepcopy(actions)
    for event in translated:
        if event['type'] == 'merger':
            if not event.get('source_references') or F(event['share_cash']) <= 0:
                raise ValueError('CASH_MERGER_EVIDENCE_REQUIRED')
            # Only the old provider's target-removal branch is reused. Actual
            # accounting must receive the ORIGINAL cash-only merger event.
            event['type'] = 'cash_stock_merger'
    return build_cost_monthly_quantity_provider(actions=translated, **kwargs)


class ActionRisk(MonthlyExitCoreResearchAdapter):
    def apply(self, *, day, month, target, closes, adjustments=()):
        trial = MonthlyExitCoreResearchAdapter(self.actions)
        trial.state, trial.last_day = deepcopy(self.state), self.last_day
        ordinary = []
        seen = set()
        for change in adjustments:
            key = (change['date'], change['security_id'])
            if key in seen or key[0] != day:
                raise ValueError('DUPLICATE_OR_NONCURRENT_ACTION')
            seen.add(key)
            matches = [e for e in self.actions if (e['date'], e['security_id']) == key]
            if len(matches) != 1 or not matches[0].get('source_references'):
                raise ValueError('UNIQUE_ACTION_EVIDENCE_REQUIRED')
            event = matches[0]
            sid = event['security_id']
            if event['type'] == 'split':
                ordinary.append(change)
                continue
            if event['type'] not in ('split_identity', 'merger'):
                raise ValueError('UNSUPPORTED_ACTION')
            if event['type'] == 'merger':
                if F(event['share_cash']) <= 0 or sid in target or sid in closes:
                    raise ValueError('TERMINATED_SECURITY_STILL_TRACKED')
            else:
                successor = event['new_security_id']
                if any(isinstance(event[k], bool) for k in ('old_shares','new_shares')):
                    raise ValueError('POSITIVE_SPLIT_RATIO_REQUIRED')
                old, new = F(event['old_shares']), F(event['new_shares'])
                if (min(old, new) <= 0 or successor == sid or change.get('new_security_id') != successor
                        or sid in target or sid in closes):
                    raise ValueError('INVALID_SPLIT_IDENTITY')
            if trial.state is None or trial.state['decision_date'] != month:
                continue
            state = trial.state
            if event['type'] == 'split_identity' and sid in state['peaks']:
                if successor in state['peaks']:
                    raise ValueError('SUCCESSOR_RISK_CONFLICT')
                for field in ('peaks', 'last_closes'):
                    state[field][successor] = str(F(state[field].pop(sid)) * old / new)
                state['unit_ids'][successor] = state['unit_ids'].pop(sid) + ':' + day + ':' + successor
                state['exited'] = sorted(successor if s == sid else s for s in state['exited'])
            elif event['type'] == 'merger':
                for field in ('peaks', 'last_closes', 'unit_ids'):
                    state[field].pop(sid, None)
                state['exited'] = [s for s in state['exited'] if s != sid]
        result = trial.apply(day=day, month=month, target=target, closes=closes, adjustments=ordinary)
        self.state, self.last_day = trial.state, trial.last_day
        return result


def require_cash_merger_settlement_evidence(events):
    if any(event['type'] == 'merger' for event in events):
        raise ValueError('CASH_MERGER_AVAILABLE_DATE_AND_RELEASE_NOT_VERIFIED')
