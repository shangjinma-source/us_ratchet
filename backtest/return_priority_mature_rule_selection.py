"""Past-only finite-family selection, not a return forecast or global optimizer."""
from datetime import date
from fractions import Fraction


def select_mature_rule(*, decision_date, candidate_statuses, completed_blocks,
                       minimum_blocks=3, maximum_blocks=12):
    """Use common mature blocks and decision-time candidates, never later winners.

    Blocks have end_date and net_returns mapping rule -> exact simple return.
    A missing/blocked return excludes that rule; never replace it with zero.
    The same window applies to all rules. Products rank equal-length mean logs
    exactly without using floating point or annualized performance projections.
    The caller must supply nonoverlapping observation intervals and establish
    publication availability. Equality of end_date and decision_date assumes
    an after-close decision; this function does not authenticate PIT sources.
    """
    if date.fromisoformat(decision_date).isoformat() != decision_date:
        raise ValueError('Canonical decision date required')
    if not (type(minimum_blocks) is int and type(maximum_blocks) is int
            and 1 <= minimum_blocks <= maximum_blocks):
        raise ValueError('Explicit positive common-window bounds required')
    if not isinstance(candidate_statuses, dict) or not candidate_statuses:
        raise ValueError('Full decision-time candidate status map required')
    mature = []
    ends = set()
    for block in completed_blocks:
        end = block['end_date']
        if date.fromisoformat(end).isoformat() != end or end in ends:
            raise ValueError('Unique canonical block ends required')
        ends.add(end)
        if end <= decision_date:
            mature.append(block)
    mature.sort(key=lambda block: block['end_date'])
    window = mature[-maximum_blocks:]
    base = dict(decision_date=decision_date, training_end_dates=[b['end_date'] for b in window],
                future_blocks_used=False, forecast_return=None, global_optimum_established=False)
    if len(window) < minimum_blocks:
        return dict(base, status='INSUFFICIENT_MATURE_HISTORY', selected_rule=None, ranking=[], exclusions={})
    ranking, exclusions = [], {}
    for rule, status in sorted(candidate_statuses.items()):
        if status not in ('LEGAL_INDICATIVE_ONLY', 'REFERENCE_ALL_CASH'):
            exclusions[rule] = 'NOT_FEASIBLE_AT_DECISION'
            continue
        growth = Fraction(1)
        for block in window:
            value = block['net_returns'].get(rule)
            if value is None:
                exclusions[rule] = 'INCOMPLETE_COMMON_MATURE_WINDOW'
                break
            if type(value) not in (str, int, float):
                raise ValueError('Exact simple return required; bool denied')
            value = Fraction(str(value))
            if value <= -1:
                raise ValueError('Positive gross wealth required')
            growth *= 1 + value
        else:
            ranking.append(dict(rule=rule, common_block_count=len(window), gross_growth_product=str(growth)))
    ranking.sort(key=lambda row: (-Fraction(row['gross_growth_product']), row['rule']))
    return dict(base, status='SELECTED_PAST_ONLY_FINITE_RULE' if ranking else 'NO_FEASIBLE_RULE_WITH_COMMON_HISTORY',
                selected_rule=ranking[0]['rule'] if ranking else None, ranking=ranking, exclusions=exclusions)
