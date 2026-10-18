"""Independent closed-form check of funding and the complete two-share domain."""
from copy import deepcopy
import unittest

from backtest import ndx_double_replacement_domain_research as domain
from test_ndx_double_replacement_domain_research import fixture


class RootFundingReview(unittest.TestCase):
    def test_large_joint_budget_count_without_using_budget_helper_as_oracle(self):
        arguments = fixture()
        row = arguments['original_rows'][0]['input_row']
        # Gross sells=50; net sells=49.95; injection=5; buffer=100.
        # C=45.05+10.01*N therefore yields a joint budget of exactly 10.01*N.
        size = 10**20 + 3
        cash_cents = 4505 + 1001 * size
        row['starting_cash_usd'] = f'{cash_cents // 100}.{cash_cents % 100:02d}'
        row['execution_prices']['D'] = '10'
        original = deepcopy(arguments)
        prepared = domain.prepare_double_replacement_domain(**arguments)
        expected = size * (size - 1) // 2
        document = prepared['document']
        self.assertEqual(document['integer_count'], expected)
        self.assertEqual(document['financial_integer_count_before_issuer'], expected)
        self.assertEqual(document['structurally_excluded_integer_count'], 0)
        self.assertEqual(document['pair_count'], 1)
        task = domain.unrank(prepared, expected - 1)
        self.assertEqual(task['identity']['buy_quantities'], [size - 1, 1])
        self.assertEqual(task['signed_trade_quantities'],
                         {'A': -2, 'B': -1, 'C': size - 1, 'D': 1, 'ZERO': 0})
        self.assertEqual(domain.rank(prepared, scenario_index=0,
            outgoing_security_ids=['A', 'B'], incoming_security_ids=['C', 'D'],
            buy_quantities=[size - 1, 1]), expected - 1)
        with self.assertRaises(ValueError):
            domain.rank(prepared, scenario_index=0, outgoing_security_ids=['A', 'B'],
                        incoming_security_ids=['C', 'D'], buy_quantities=[size, 1])
        self.assertEqual(arguments, original)


if __name__ == '__main__':
    unittest.main()
