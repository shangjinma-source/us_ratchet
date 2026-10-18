from copy import deepcopy
import unittest

from backtest.ndx_incumbent_flow_split_control_research import simulate_incumbent_flow_split_control
from backtest.ndx_multidecision_incumbent_account_inspection_research import inspect_saved_control
from test_ndx_incumbent_flow_split_control_research import fixture
from test_ndx_multidecision_incumbent_account_inspection_research import prepared


class CancellationScope(unittest.TestCase):
    def test_split_cancels_frozen_basket_but_retains_same_open_flow(self):
        arguments = fixture('WHOLE_LOT')
        second = deepcopy(arguments['schedule'][0])
        second.update(decision_date='2026-04-02', execution_date='2026-04-03')
        arguments['schedule'].append(second)
        arguments['risk_chains_by_decision']['2026-04-02'] = deepcopy(arguments['risk_chains_by_decision']['2026-03-31'])
        arguments['corporate_actions'] = [dict(security_id='A', session='2026-04-03', new_shares=2, old_shares=1, source_url='https://example.test/split', evidence_sha256='a' * 64)]
        arguments['external_flows'] = [dict(session='2026-04-03', amount_usd=200., currency='USD', timing='BEFORE_OPEN', source_reference=dict(path='/synthetic/flow', sha256='b' * 64))]
        for name in ('opens', 'closes'):
            arguments[name].loc['2026-04-03', 'A'] = 5.
        result = simulate_incumbent_flow_split_control(**arguments)
        report = inspect_saved_control(prepared_track=prepared(arguments), result=result)
        self.assertEqual(result['executions'][-1]['status'], 'CANCELLED_SPLIT')
        self.assertEqual(report['cash_injections_exact'], '200')
        self.assertEqual(report['chained_twr_exact'], '0')
        self.assertEqual(result['daily'][-1]['cash_usd'], result['daily'][-2]['cash_usd'] + 200.)
        self.assertFalse(any(row['session'] == '2026-04-03' for row in result['trades']))
        changed = deepcopy(result)
        changed['executions'][-1]['status'] = 'FILLED'
        with self.assertRaises(ValueError):
            inspect_saved_control(prepared_track=prepared(arguments), result=changed)


if __name__ == '__main__':
    unittest.main()
