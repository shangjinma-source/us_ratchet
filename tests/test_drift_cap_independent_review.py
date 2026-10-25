"""Independent review adversarial cases; fixture uses no execution/strategy code."""
from copy import deepcopy
from fractions import Fraction as F
import subprocess
import sys
import unittest
from unittest.mock import patch

from backtest.drift_cap_independent_review import review_book


def fixture():
    start, first, last = '2025-01-01', '2025-01-02', '2025-01-03'
    plan = dict(decision_date=start, valuation_quotes=[], search_arguments={}, source_hashes={})
    assembled = dict(session_dates=[start, first, last], monthly_inputs=[plan],
        close_prices={'A': {start: '100', first: '200', last: '210'}},
        provider_actions=[], actions=[], distribution_events=[])
    bars = {'A': {first: dict(open='100', close='200'), last: dict(open='220', close='210')}}
    buy_price, buy_fee = F('100.1'), F('1.001')
    cash_after_buy = F(20000) - 100 * buy_price - buy_fee
    first_equity = cash_after_buy + 20000
    reduced = int(first_equity / 400)
    sell_quantity = 100 - reduced
    sell_price = F('219.78')
    sell_fee = sell_quantity * sell_price / 10000
    cash_after_sell = cash_after_buy + sell_quantity * sell_price - sell_fee
    last_equity = cash_after_sell + reduced * 210
    audits, fills, rows = [], [], []
    for decision, day, cash, quantity, price, fee, stock, target in (
        (start, first, cash_after_buy, 100, buy_price, buy_fee, F(20000), 100),
        (first, last, cash_after_sell, sell_quantity, sell_price, sell_fee, F(reduced * 210), reduced)):
        close = assembled['close_prices']['A'][decision]
        side = 'BUY' if decision == start else 'SELL'
        identifier = 'cap:' + decision + ':A'
        order = dict(id=identifier, decision_date=decision, active_date=day,
                     security_id='A', side=side, quantity=quantity)
        reductions = [] if decision == start else [dict(security_id='A', before=100, after=reduced,
                    held=100, close='200', weight=str(F(20000) / first_equity))]
        audits.append(dict(action='NEXT_OPEN_RISK_DIFFERENCES',
            selection=dict(investable_equity='20000', raw_selection=dict(target_quantities={'A': 100}),
                           target_quantities={'A': 100}) if decision == start else None,
            monthly_ceiling={'A': 100}, target_shares={'A': target}, orders=[order],
            risk_overlay=dict(state=dict(decision_date=start, session_date=decision,
                peaks={'A': close}, exited=[], last_closes={'A': close},
                unit_ids={'A': 'research-nominal:A'}), effective_target_quantities={'A': 100}),
            drift_overlay=dict(ceiling={'A': target}, effective_targets={'A': target},
                day=decision, month=start, reductions=reductions,
                tradable_equity='20000' if decision == start else str(first_equity))))
        fills.append(dict(order, date=day, event='ASSUMED_NEXT_OPEN_FILLED',
                          price=str(price), fee=str(fee), cash_after=str(cash)))
        rows.append(dict(date=day, shares={'A': 100 if decision == start else reduced},
            cash=str(cash), stock_value=str(stock), equity=str(stock + cash), receivable='0',
            external_flow='0', distribution_rights=[], merger_entitlements=[]))
    book = dict(status='COMPLETE', fee_bps='1', slippage_bps='10',
        selection_account_states=[dict(plan, account_state=dict(asof=start, cash='20000', shares={}))],
        provider_audit=audits, daily_ledger=rows, order_log=fills,
        fees=str(buy_fee + sell_fee), cash=str(cash_after_sell), shares={'A': reduced},
        state_date=last, last_valued_date=last, terminal_state_valuation_synchronized=True,
        final_wealth_basis='REGULAR_CLOSE_CURRENT_STATE', receivable='0', external_flows='0',
        distribution_rights=[], merger_entitlements=[], total_return=str(last_equity / 20000 - 1),
        drawdown=dict(maximum_close_drawdown='0'))
    return book, assembled, bars


class IndependentDriftReviewTests(unittest.TestCase):
    def test_real_wrapper_and_execution_with_fixed_selector(self):
        from backtest.drift_capped_next_open_research import run_drift_capped_next_open
        from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
        manual, assembled, bars = fixture()
        assembled['monthly_inputs'][0]['search_arguments']['fee_bps'] = '1'
        assembled.update(cash_stock_merger_events=[], fractional_settlements={},
                         price_source_references={}, distribution_fractional_cash_values={})
        for row in bars['A'].values():
            row.update(high=str(max(F(row['open']), F(row['close']))),
                       low=str(min(F(row['open']), F(row['close']))))
        selected = manual['provider_audit'][0]['selection']
        with patch('backtest.drift_capped_next_open_research.decide_capped_account',
                   return_value=selected) as selector:
            book = run_drift_capped_next_open(assembled=assembled, ohlc=bars,
                initial_cash='20000', fee_bps='1', slippage_bps='10',
                risk=MonthlyExitCoreResearchAdapter([]), drift_enabled=True)
        self.assertEqual(selector.call_count, 1)
        self.assertEqual(book['status'], 'COMPLETE', book.get('reason'))
        self.assertEqual(book['cash'], manual['cash'])
        self.assertEqual(book['shares'], manual['shares'])
        self.assertEqual(book['provider_audit'][1]['drift_overlay']['ceiling'], {'A': 74})
        self.assertEqual(review_book(book, assembled, bars, drift_enabled=True)['fills'], 2)

    def test_manual_book_includes_post_gap_residual_drift(self):
        book, assembled, bars = fixture()
        result = review_book(book, assembled, bars, drift_enabled=True)
        self.assertEqual(result['fills'], 2)
        self.assertEqual(result['reductions'], 1)
        self.assertEqual(result['close_observations'], 2)

    def test_account_and_performance_tampering_rejected(self):
        book, assembled, bars = fixture()
        mutations = [lambda b: b['daily_ledger'][0].update(cash='9999'),
                     lambda b: b.update(total_return='10'),
                     lambda b: b['drawdown'].update(maximum_close_drawdown='1/10'),
                     lambda b: b.update(state_date='2025-01-04'),
                     lambda b: b['order_log'][1].update(price='220'),
                     lambda b: b['order_log'].append(dict(b['order_log'][0], date='2025-01-04'))]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                bad = deepcopy(book)
                mutate(bad)
                with self.assertRaises(AssertionError):
                    review_book(bad, assembled, bars, drift_enabled=True)

    def test_target_risk_time_and_unit_tampering_rejected(self):
        book, assembled, bars = fixture()
        mutations = [lambda a: a['drift_overlay']['ceiling'].update(A=100),
                     lambda a: a['drift_overlay']['reductions'].clear(),
                     lambda a: a['target_shares'].update(A=100),
                     lambda a: a['risk_overlay']['state'].update(session_date='2025-01-03'),
                     lambda a: a['risk_overlay']['state']['unit_ids'].update(A='different-unit'),
                     lambda a: a['risk_overlay']['state']['exited'].append('A')]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                bad = deepcopy(book)
                mutate(bad['provider_audit'][1])
                with self.assertRaises(AssertionError):
                    review_book(bad, assembled, bars, drift_enabled=True)

    def test_wrong_cost_contract_rejected(self):
        book, assembled, bars = fixture()
        book['fee_bps'] = '0'
        with self.assertRaisesRegex(ValueError, 'REGISTERED_COSTS_REQUIRED'):
            review_book(book, assembled, bars, drift_enabled=True)

    def test_optimized_python_cannot_silently_bypass_review(self):
        result = subprocess.run([sys.executable, '-O', '-c',
            'from backtest.drift_cap_independent_review import review_book; '
            'review_book({}, {}, {}, drift_enabled=True)'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('INDEPENDENT_REVIEW_REQUIRES_ASSERTIONS_ENABLED', result.stderr)


if __name__ == '__main__':
    unittest.main()
