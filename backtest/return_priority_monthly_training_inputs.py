"""Compile reviewed monthly price scenarios without IO or strategy execution.

Evidence admission is the caller's responsibility. This compiler checks the
full declared member domain and never excludes a ticker because prices are
missing. It does not authenticate membership, identities or price units.
"""
from datetime import date
from fractions import Fraction


def compile_monthly_training_window(*, window, source_hashes, admission):
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    def positive(value):
        require(not isinstance(value, bool), 'BOOLEAN_PRICE')
        number = Fraction(str(value))
        require(number > 0, 'NONPOSITIVE_PRICE')
        return number

    decision = window['decision_cutoff']
    days = window['training_dates']
    require(len(days) == 253 and days == sorted(set(days))
            and days[-1] == decision
            and all(date.fromisoformat(day).isoformat() == day for day in days),
            'INVALID_MATURE_TRAINING_CALENDAR')
    require(admission.get('decision_date') == decision
            and admission.get('status') == 'REVIEWED_CONDITIONAL', 'WINDOW_NOT_ADMITTED')
    references = admission.get('source_references', [])
    require(references and all(ref in source_hashes for ref in references), 'UNPINNED_ADMISSION')
    candidates = window['candidates']
    tickers = [row['ticker'] for row in candidates]
    require(len(set(tickers)) == len(tickers)
            and set(tickers) == set(admission['members'])
            and len(tickers) == len(admission['members']), 'MEMBER_DOMAIN_MISMATCH')
    exclusions = admission.get('training_exclusions', {})
    require(set(exclusions) <= set(tickers), 'EXCLUSION_OUTSIDE_DOMAIN')
    included = []
    for row in candidates:
        ticker = row['ticker']
        require(not row.get('blockers'), 'CANDIDATE_BLOCKED:' + ticker)
        if row['status'] == 'EXCLUDED_TRAINING_RULE':
            evidence = exclusions.get(ticker, {})
            refs = evidence.get('source_references', [])
            require(evidence.get('reason') == 'INSUFFICIENT_253_SESSION_PREDECISION_HISTORY'
                    and refs and all(ref in source_hashes for ref in refs), 'EXCLUSION_NOT_ADMITTED:' + ticker)
            known = evidence.get('known_asof', '')
            require(date.fromisoformat(known).isoformat() == known and known <= decision, 'FUTURE_EXCLUSION:' + ticker)
            continue
        require(ticker not in exclusions and row['status'] == 'READY_CONDITIONAL', 'INVALID_CANDIDATE_STATUS:' + ticker)
        require(row.get('security_id') and row.get('issuer_id'), 'IDENTITY_REQUIRED:' + ticker)
        require(row.get('training_source') in source_hashes, 'UNPINNED_TRAINING:' + ticker)
        values = row['training_close']
        require(len(values) == 253 and not row.get('missing_training_dates'), 'INCOMPLETE_TRAINING:' + ticker)
        values = [positive(value) for value in values]
        gross = [str(values[i + 21] / values[i]) for i in range(0, 252, 21)]
        if row.get('training_gross') is not None:
            require([Fraction(value) for value in row['training_gross']] == [Fraction(value) for value in gross], 'SCENARIO_MISMATCH:' + ticker)
        included.append((row, positive(row['decision_cost']), gross))
    require(included and len({row['security_id'] for row, _, _ in included}) == len(included), 'EMPTY_OR_DUPLICATE_SECURITY_DOMAIN')
    return dict(prices={row['security_id']: str(cost) for row, cost, _ in included},
        metadata={row['security_id']: dict(ticker=row['ticker'], issuer_id=row['issuer_id']) for row, _, _ in included},
        entered_cash='20000', fee_bps='0', minimum_cash_buffer='0',
        training_scenarios=[{row['security_id']: gross[i] for row, _, gross in included} for i in range(12)],
        scenario_dates=days[21::21], decision_date=decision,
        max_objective_evaluations=8192, fixed_seed='fresh-quantity-20261014-v1')
