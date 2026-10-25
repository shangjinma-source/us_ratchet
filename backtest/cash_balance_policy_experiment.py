"""One isolated, predeclared cash-policy case; no implicit search or IO."""
from backtest.cash_balance_policy_book import run_next_open_book
from backtest.cash_balance_policy_provider import build_cash_policy_provider


def run_case(*, case, bundle, seed, mode, stable, selector, selection_recorder):
    flows = [] if stable else case['external_flows']
    provider, audit = build_cash_policy_provider(bundle=bundle, seed=seed, mode=mode,
        flow_dates={row['date'] for row in flows if row['amount'] != '0'},
        selector=selector, selection_recorder=selection_recorder)
    book = run_next_open_book(session_dates=case['sessions'], ohlc=bundle['ohlc'],
        initial_cash=seed['cash'], initial_shares=seed['shares'],
        fee_bps=bundle['fee_bps'], slippage_bps=bundle['slippage_bps'],
        events=bundle['actions'], order_provider=provider,
        cash_stock_merger_events=bundle['cash_stock_merger_events'],
        fractional_settlements=bundle['fractional_settlements'],
        price_source_references=bundle['price_source_references'],
        distribution_events=bundle['distribution_events'],
        distribution_fractional_cash_values=bundle['distribution_fractional_cash_values'],
        account_model=bundle['account_model'], external_cash_flows=flows)
    return dict(case_id=case['id'], mode=mode, stable=stable, book=book,
                audit=audit, production_changes=False)
