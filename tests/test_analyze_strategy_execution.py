"""Cash dependence is accounting, and invalid timing/units must not look valid."""
from copy import deepcopy
from fractions import Fraction as F
import unittest

from scripts.analyze_strategy_execution import audit_execution


def fixture():
    def order(identity, day, active, sid, side, quantity):
        return dict(id=identity, decision_date=day, active_date=active,
                    security_id=sid, side=side, quantity=quantity)
    def fill(identity, day, sid, side, quantity, price, cash):
        return dict(id=identity, date=day, event='ASSUMED_NEXT_OPEN_FILLED',
                    security_id=sid, side=side, quantity=quantity, price=price,
                    fee='0', cash_after=cash)
    return dict(status='COMPLETE', external_flows='0', fees='0', cash='15/2', slippage_bps='0',
        selection_account_states=[dict(account_state=dict(asof='2025-01-01', cash='100', shares={}),
                                       valuation_quotes=[dict(security_id='A', ticker='AAA')])],
        daily_ledger=[dict(date='2025-01-02', cash='50'), dict(date='2025-01-03', cash='15/2')],
        provider_audit=[dict(orders=[order('one', '2025-01-01', '2025-01-02', 'A', 'BUY', 5)]),
                        dict(orders=[order('two', '2025-01-02', '2025-01-03', 'A', 'SELL', 5),
                                     order('three', '2025-01-02', '2025-01-03', 'B', 'BUY', 8)],
                             risk_overlay=dict(state=dict(session_date='2025-01-02', exited=['A'],
                                                          peaks={'A': '10'}, last_closes={'A': '8'})))],
        order_log=[fill('one', '2025-01-02', 'A', 'BUY', 5, '10', '50'),
                   fill('two', '2025-01-03', 'A', 'SELL', 5, '15/2', '175/2'),
                   fill('three', '2025-01-03', 'B', 'BUY', 8, '10', '15/2')])


class ExecutionAuditTests(unittest.TestCase):
    def test_sale_dependence_is_shortfall_not_all_sales_or_all_purchases(self):
        result = audit_execution(fixture())
        self.assertEqual(result['buy_days'], 2)
        self.assertEqual(result['sale_funded_buy_days'], 1)
        self.assertEqual(F(result['sale_dependent_cash_sum']), 30)
        self.assertEqual(F(result['buy_outflow']), 130)
        stop = result['risk_exit_fills'][0]
        self.assertEqual(F(stop['signal_drop']), F(1, 5))
        self.assertEqual(F(stop['fill_drop']), F(1, 4))
        self.assertEqual(F(stop['open_gap']), F(-1, 16))

    def test_cash_timing_and_unknown_events_fail_closed(self):
        mutations = [lambda b: b['order_log'][1].update(cash_after='90'),
                     lambda b: b['daily_ledger'][0].update(cash='60'),
                     lambda b: b['provider_audit'][1]['orders'][0].update(decision_date='2025-01-03'),
                     lambda b: b['daily_ledger'][1].update(external_flow='1'),
                     lambda b: b['daily_ledger'][1].update(distribution_rights=[{'child': 'C'}]),
                     lambda b: b['order_log'].append(deepcopy(b['order_log'][0])),
                     lambda b: b.update(fees='1')]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                book = fixture()
                mutate(book)
                with self.assertRaises(ValueError):
                    audit_execution(book)

    def test_split_quantity_exit_requires_explicit_evidence(self):
        book = fixture()
        book['provider_audit'][1]['orders'][0]['quantity'] = 1
        with self.assertRaisesRegex(ValueError, 'split evidence'):
            audit_execution(book)
        state = book['provider_audit'][1]['risk_overlay']['state']
        state['peaks']['A'], state['last_closes']['A'] = '50', '40'
        book['order_log'].insert(1, dict(date='2025-01-03', event='CORPORATE_ACTION',
            security_id='A', type='split', action_details=dict(date='2025-01-03', security_id='A',
                new_shares=5, old_shares=1, source_references=['synthetic-only'])))
        result = audit_execution(book)
        self.assertEqual(result['action_unit_exits_rebased'], 1)
        self.assertEqual(F(result['risk_exit_fills'][0]['fill_drop']), F(1, 4))

    def test_fees_are_included_in_cash_dependency(self):
        book = fixture()
        book['order_log'][2].update(fee='1', cash_after='13/2')
        book['daily_ledger'][1]['cash'] = book['cash'] = '13/2'
        book['fees'] = '1'
        result = audit_execution(book)
        self.assertEqual(F(result['sale_dependent_cash_sum']), 31)


if __name__ == '__main__':
    unittest.main()
