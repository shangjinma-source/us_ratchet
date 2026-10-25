import unittest

from backtest.monthly_drift_cap_research import MonthlyDriftCap


class MonthlyDriftCapTests(unittest.TestCase):
    def apply(self, rule, day, *, shares, cash, price, raw=50, risk=None,
              month='2025-01-01', adjustments=()):
        return rule.apply(day=day, month=month, baseline_targets={'A': raw},
                          risk_targets={'A': raw if risk is None else risk},
                          shares={'A': shares}, cash=str(cash), closes={'A': str(price)},
                          adjustments=adjustments)

    def test_initial_and_underfunded_purchase_remain_eligible(self):
        rule = MonthlyDriftCap()
        self.assertEqual(self.apply(rule, '2025-01-01', shares=0, cash=1000, price=10)[0], {'A': 50})
        # Partial fill itself must not latch the 50-share monthly target to 10.
        self.assertEqual(self.apply(rule, '2025-01-02', shares=10, cash=200, price=10)[0], {'A': 50})

    def test_reduce_rising_concentration_without_buyback_on_decline(self):
        rule = MonthlyDriftCap()
        first, audit = self.apply(rule, '2025-01-02', shares=50, cash=500, price=20)
        self.assertEqual(first, {'A': 37})
        self.assertEqual(audit['tradable_equity'], '1500')
        self.assertEqual(self.apply(rule, '2025-01-03', shares=37, cash=760, price=10)[0], {'A': 37})
        # Repeated sell fills are modeled outside this pure target rule.
        self.assertEqual(self.apply(rule, '2025-01-06', shares=37, cash=760, price=10, risk=0)[0], {'A': 0})

    def test_month_reset_restores_new_selection_only(self):
        rule = MonthlyDriftCap()
        self.apply(rule, '2025-01-30', shares=50, cash=500, price=20)
        self.assertEqual(self.apply(rule, '2025-01-31', shares=37, cash=760, price=10,
                                    month='2025-01-31')[0], {'A': 50})

    def test_same_identity_split_migrates_latched_quantity(self):
        action = dict(type='split', date='2025-01-03', security_id='A',
                      old_shares='1', new_shares='10', source_references=['fixture'])
        rule = MonthlyDriftCap([action])
        self.apply(rule, '2025-01-02', shares=50, cash=500, price=20)
        result, _ = self.apply(rule, '2025-01-03', shares=370, cash=760, price=1,
                               raw=500, adjustments=[dict(date='2025-01-03', security_id='A', new_security_id='A')])
        self.assertEqual(result, {'A': 370})

    def test_exact_half_does_not_reduce_or_use_future_execution_price(self):
        rule = MonthlyDriftCap()
        result, audit = self.apply(rule, '2025-01-02', shares=50, cash=500, price=10)
        self.assertEqual(result, {'A': 50})
        self.assertEqual(audit['reductions'], [])

    def test_cash_and_all_delivered_holdings_form_denominator(self):
        rule = MonthlyDriftCap()
        result, audit = rule.apply(day='2025-01-02', month='2025-01-01',
                                   baseline_targets={'A': 50}, risk_targets={'A': 50},
                                   shares={'A': 50, 'B': 30}, cash='100', closes={'A': '20', 'B': '10'})
        self.assertEqual(result, {'A': 35})
        self.assertEqual(audit['tradable_equity'], '1400')

    def test_missing_mark_and_unsupported_migration_fail_closed(self):
        rule = MonthlyDriftCap()
        with self.assertRaisesRegex(ValueError, 'MISSING_COMPLETED_CLOSE'):
            rule.apply(day='2025-01-02', month='2025-01-01', baseline_targets={'A': 50},
                       risk_targets={'A': 50}, shares={'A': 50, 'B': 1}, cash='100', closes={'A': '20'})
        self.apply(rule, '2025-01-02', shares=50, cash=500, price=20)
        with self.assertRaisesRegex(ValueError, 'UNIQUE_SPLIT_EVIDENCE_REQUIRED'):
            self.apply(rule, '2025-01-03', shares=50, cash=500, price=20,
                       adjustments=[dict(date='2025-01-03', security_id='A', new_security_id='A')])


if __name__ == '__main__':
    unittest.main()
