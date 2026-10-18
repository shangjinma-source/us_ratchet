import unittest
from scripts.return_priority_top1_baselines import select_top1


def arguments():
    return dict(prices={'b': '300', 'a': '300'}, metadata={'a': {'ticker': 'A'}, 'b': {'ticker': 'B'}},
                training_scenarios=[{'a': '11/10', 'b': '11/10'} for _ in range(12)],
                scenario_dates=[f'2024-01-{d:02d}' for d in range(1,13)], decision_date='2024-01-12',
                entered_cash='20000', fee_bps='0', minimum_cash_buffer='0')


class Top1Tests(unittest.TestCase):
    def test_exact_tie_full_domain_and_projection(self):
        args = arguments()
        chosen = select_top1(args)
        self.assertEqual(chosen['security_id'], 'a')
        self.assertEqual(chosen['decision_quantity'], 66)
        self.assertEqual(chosen['modes']['TOP1_SAME_PROJECTION'], '99/100')
        self.assertEqual(chosen['modes']['TOP1_FULL_CASH'], '1')
        args['training_scenarios'][-1]['b'] = '11000000000000000001/10000000000000000000'
        self.assertEqual(select_top1(args)['security_id'], 'b')

    def test_unaffordable_winner_not_replaced(self):
        args = arguments()
        args['prices']['a'] = '30000'
        chosen = select_top1(args)
        self.assertEqual(chosen['security_id'], 'a')
        self.assertEqual(chosen['modes']['TOP1_SAME_PROJECTION'], '0')

    def test_missing_and_future_scenarios_rejected(self):
        args = arguments()
        del args['training_scenarios'][0]['a']
        with self.assertRaises(ValueError):
            select_top1(args)
        args = arguments()
        args['scenario_dates'][-1] = '9999-01-01'
        with self.assertRaises(ValueError):
            select_top1(args)


if __name__ == '__main__':
    unittest.main()
