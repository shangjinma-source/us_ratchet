import unittest
import test_dynamic_switch_risk_comparison as risk_fixtures
from data.dynamic_switch_decision import decide_dynamic_switch


class DynamicDecisionTests(unittest.TestCase):
    def arguments(self):
        inputs = risk_fixtures.DynamicRiskTests().arguments()
        inputs['cash'] = '110'
        return dict(account_revision='fixture-revision', pending_orders=[], **inputs)

    def test_better_candidate_preserves_exit_and_requires_cash_revalidation(self):
        result = decide_dynamic_switch(**self.arguments())
        self.assertEqual(result['status'], 'SWITCH_SIGNAL')
        self.assertEqual(result['targets'], {'A': 0, 'B': 1})
        self.assertEqual(result['risk_anchor'], '2026-10-01')
        self.assertFalse(result['orders_created'])

    def test_tie_keeps_risk_exit_without_buying(self):
        arguments = self.arguments()
        arguments['scenarios'][0]['B'] = '1'
        result = decide_dynamic_switch(**arguments)
        self.assertEqual(result['status'], 'RISK_EXIT_SIGNAL')
        self.assertEqual(result['target_differences'], [{'security_id': 'A', 'side': 'SELL', 'quantity': 1}])

    def test_pending_orders_wait_and_over_cap_rejected(self):
        arguments = self.arguments()
        arguments['pending_orders'] = [{'order_id': 'fixture'}]
        self.assertEqual(decide_dynamic_switch(**arguments)['status'], 'WAIT_PENDING_ORDERS')
        arguments['pending_orders'] = []
        arguments['candidate']['B'] = 2
        with self.assertRaisesRegex(ValueError, 'CAP50'):
            decide_dynamic_switch(**arguments)


if __name__ == '__main__':
    unittest.main()
