import unittest
from copy import deepcopy
from backtest.momentum_equal_weight_target_research import build_target


class MomentumSizingTests(unittest.TestCase):
    def setUp(self):
        self.roster = dict(decision_date='2024-01-31',
                           selected=[dict(security_id=str(i), issuer_id=str(i)) for i in range(10)],
                           gate=dict(risk_on=True))
        self.prices = {str(i): '30' for i in range(10)}

    def decide(self, **overrides):
        arguments = dict(roster=self.roster, decision_date='2024-01-31',
                         investable_equity='1000', nominal_prices=self.prices)
        return build_target(**dict(arguments, **overrides))

    def test_unaffordable_slot_stays_cash_without_refill(self):
        self.prices['0'] = '101'
        result = self.decide()
        self.assertEqual(result['target_quantities']['0'], 0)
        self.assertEqual(result['target_value'], '810')
        self.assertEqual(result['unallocated_equity'], '190')
        self.assertTrue(all(q == 3 for s, q in result['target_quantities'].items() if s != '0'))

    def test_off_gate_has_no_stock_target_and_preserves_inputs(self):
        self.roster['gate']['risk_on'] = False
        before = deepcopy(self.roster)
        result = self.decide()
        self.assertEqual(result['target_quantities'], {})
        self.assertEqual(result['unallocated_equity'], '1000')
        self.assertEqual(self.roster, before)

    def test_exact_fraction_boundary_does_not_round_up(self):
        self.prices['0'] = '10000000000000001/100000000000000'
        self.assertEqual(self.decide()['target_quantities']['0'], 0)

    def test_rejects_stale_roster_missing_price_and_duplicate_issuer(self):
        with self.assertRaisesRegex(ValueError, 'ROSTER_DATE'):
            self.decide(decision_date='2024-02-01')
        del self.prices['0']
        with self.assertRaisesRegex(ValueError, 'MISSING_SELECTED_PRICE'):
            self.decide()
        self.roster['selected'][1]['issuer_id'] = '0'
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_ISSUER'):
            self.decide()


if __name__ == '__main__':
    unittest.main()
