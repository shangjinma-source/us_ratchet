"""Summarize v4 only when the full close series and terminal state agree."""
from copy import deepcopy
from scripts.return_priority_fixed12_monthly_limit_run import summarize


def summarize_limit_book_v4(outcome, audit, initial_cash, session_dates):
    checked = deepcopy(outcome)
    ledger = checked.get('daily_ledger', [])
    dates = [row['date'] for row in ledger]
    complete = (checked.get('status') == 'COMPLETE'
                and dates == session_dates[1:]
                and checked.get('terminal_state_valuation_synchronized') is True
                and checked.get('final_wealth_basis') == 'REGULAR_CLOSE_CURRENT_STATE')
    if checked.get('status') == 'COMPLETE' and not complete:
        checked['status'] = 'INCOMPLETE_VERIFIED_VALUATION'
        checked['reason'] = 'FULL_CLOSE_SERIES_AND_SYNCHRONIZED_TERMINAL_STATE_REQUIRED'
    result = summarize(checked, audit, initial_cash, session_dates)
    result.update(kernel_status=outcome['status'],
        terminal_state_valuation_synchronized=outcome.get('terminal_state_valuation_synchronized', False),
        final_wealth_basis=outcome.get('final_wealth_basis'),
        terminal_distribution_rights=deepcopy(outcome.get('distribution_rights', [])),
        terminal_merger_entitlements=deepcopy(outcome.get('merger_entitlements', [])),
        last_valued_date=dates[-1] if dates else None,
        after_close_records=deepcopy(outcome.get('after_close_records', [])),
        terminal_target_basis='Latest successful target; terminal differences are meaningful only with a synchronized full-period terminal state.')
    if not complete:
        result['terminal_target_difference'] = None
        result['unfinished_rebalance'] = None
    if not ledger:
        # Initial cash is a starting condition, not an observed market outcome.
        result['partial_observed_drawdown'] = None
        result['last_observed_equity'] = None
    return result
