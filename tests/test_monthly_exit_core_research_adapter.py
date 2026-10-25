from copy import deepcopy
import unittest
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter


class CoreRiskAdapterTests(unittest.TestCase):
    def risk(self):
        event = dict(type='split', date='2024-08-08', security_id='A',
                     old_shares=1, new_shares=10, source_references=['fixture-source'])
        risk = MonthlyExitCoreResearchAdapter([event])
        risk.apply(day='2024-07-31', month='2024-07-31', target={'A': 9}, closes={'A': '1000'})
        return risk, dict(date='2024-08-08', security_id='A', new_security_id='A')

    def test_split_threshold_latch_and_month_reset(self):
        risk, change = self.risk()
        target, _ = risk.apply(day='2024-08-08', month='2024-07-31', target={'A': 90},
                               closes={'A': '100'}, adjustments=[change])
        self.assertEqual(target, {'A': 90})
        for day, price in [('2024-08-09', '80'), ('2024-08-12', '120')]:
            self.assertEqual(risk.apply(day=day, month='2024-07-31', target={'A': 90},
                                       closes={'A': price})[0], {'A': 0})
        self.assertEqual(risk.apply(day='2024-08-30', month='2024-08-30', target={'A': 40},
                                   closes={'A': '110'})[0], {'A': 40})

    def test_bad_evidence_does_not_mutate_state(self):
        risk, change = self.risk()
        before = deepcopy(risk.state)
        risk.actions[0]['source_references'] = []
        with self.assertRaisesRegex(ValueError, 'SPLIT_SOURCE_REQUIRED'):
            risk.apply(day='2024-08-08', month='2024-07-31', target={'A': 90},
                       closes={'A': '100'}, adjustments=[change])
        self.assertEqual(risk.state, before)
        self.assertEqual(risk.last_day, '2024-07-31')

    def test_zero_target_is_still_tracked(self):
        risk = MonthlyExitCoreResearchAdapter()
        risk.apply(day='2024-07-31', month='2024-07-31', target={'A': 0}, closes={'A': '100'})
        target, _ = risk.apply(day='2024-08-01', month='2024-07-31', target={'A': 1}, closes={'A': '80'})
        self.assertEqual(target, {'A': 0})


if __name__ == '__main__':
    unittest.main()
