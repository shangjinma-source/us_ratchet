import unittest
from scripts.return_priority_fixed12_holding_prepare import factor_on_date, bind_frozen_weights
from fractions import Fraction


class HoldingPreparationTests(unittest.TestCase):
    def test_successive_splits_restore_session_units_once(self):
        events = [dict(event_date='2024-10-01', factor='10'), dict(event_date='2025-01-02', factor='2')]
        self.assertEqual(factor_on_date('20', events, '2024-09-30'), 20)
        self.assertEqual(factor_on_date('20', events, '2024-10-01'), 2)
        self.assertEqual(factor_on_date('20', events, '2025-01-02'), 1)
        # Ten old shares and quote five: equity unchanged across 10:1 split.
        self.assertEqual(10 * 5 * 20, 100 * 5 * 2)

    def test_price_gaps_do_not_change_frozen_selection(self):
        window = dict(outcome_arguments_without_target_weights=dict(metadata={'a': {}}, nominal_prices={'a': {}}),
                      price_gaps=[{'security_id': 'a'}])
        result = bind_frozen_weights(window, {'a': '3/4'})
        self.assertEqual(result['target_weights'], {'a': '3/4'})
        self.assertEqual(result['nominal_prices']['a'], {})
        self.assertNotIn('target_weights', window['outcome_arguments_without_target_weights'])
        self.assertEqual(bind_frozen_weights(window, {})['target_weights'], {})
        with self.assertRaises(ValueError):
            bind_frozen_weights(window, {'a': '2'})


if __name__ == '__main__':
    unittest.main()
