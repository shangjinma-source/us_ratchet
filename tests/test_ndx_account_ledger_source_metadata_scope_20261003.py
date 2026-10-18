"""Independent source-boundary mutations; no actual research accounts."""
from copy import deepcopy
import unittest

from backtest import ndx_multidecision_account_inspection_research as inspection
from test_ndx_account_ledger_inspection_review_20261003 import case


class SourceMetadataScope(unittest.TestCase):
    def test_fractional_saved_capital_calendar_and_flow_boundary(self):
        track, result = case('CONTINUOUS')
        inspection.inspect_saved_account(prepared_track=track, result=result)
        mutations = {
            'initial_capital': lambda value: value.update(initial_cash_usd=1.),
            'calendar': lambda value: value['calendar'].pop(),
            'flow_identity': lambda value: value['external_flows'][0].update(event_id='0' * 64),
            'flow_boundary': lambda value: value['external_flows'][0].update(performance_boundary='AFTER_REBALANCE'),
            'return_intervals': lambda value: value['summary'].update(return_interval_count=999),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                changed = deepcopy(result)
                mutate(changed)
                with self.assertRaises(ValueError):
                    inspection.inspect_saved_account(prepared_track=track, result=changed)


if __name__ == '__main__':
    unittest.main()
