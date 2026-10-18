"""No-flow control order policy remains identical to the frozen incumbent."""
from unittest import TestCase, main
from backtest.ndx_dynamic_frozen_incumbent_control import simulate_dynamic_frozen_incumbent_control
from test_ndx_incumbent_flow_split_control_research import fixture, run


class IncumbentPolicyTests(TestCase):
    def test_fractional_risk_observation_accepts_base_engine_iso_date_index(self):
        arguments = fixture('CONTINUOUS')
        expected = run(**arguments)
        arguments['closes'].index = arguments['closes'].index.strftime('%Y-%m-%d')
        arguments['opens'].index = arguments['opens'].index.strftime('%Y-%m-%d')
        actual = run(**arguments)
        self.assertEqual(actual['daily'], expected['daily'])
        self.assertEqual(actual['trades'], expected['trades'])

    def test_zero_flow_preserves_original_frozen_orders_despite_risk_failure(self):
        arguments = fixture('WHOLE_LOT')
        arguments['transaction_cost_bps'] = 10.
        arguments['closes']['H'] = 100000.
        arguments['opens']['H'] = 100000.
        current = run(**arguments)
        arguments.pop('track')
        arguments.pop('external_flows')
        previous = simulate_dynamic_frozen_incumbent_control(**arguments)
        for role in ('decisions', 'executions', 'trades'):
            self.assertEqual(current[role], previous[role])
        self.assertTrue(current['trades'])
        self.assertFalse(current['daily'][-1]['risk']['all_passed'])
        self.assertIn('H', current['daily'][-1]['risk']['zero_share_security_ids'])


if __name__ == '__main__':
    main()
