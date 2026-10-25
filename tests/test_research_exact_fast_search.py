import unittest
from backtest.return_priority_fresh_cash_quantity_search_v2 import search_fresh_cash_quantities as original
from backtest.research_exact_fast_search import search_fresh_cash_quantities as accelerated


class ExactAccelerationTests(unittest.TestCase):
    def test_complete_output_across_fee_buffer_and_budget_boundaries(self):
        base = dict(prices={'A': '7/3', 'B': '11/7', 'C': '5'},
            metadata={s: dict(ticker=s, issuer_id=s) for s in ('A','B','C')},
            entered_cash='100', fee_bps='0', minimum_cash_buffer='0',
            training_scenarios=[{'A':'9/8','B':'7/9','C':'1'}, {'A':'6/7','B':'5/4','C':'1'}],
            scenario_dates=['2026-09-01','2026-10-01'], decision_date='2026-10-23',
            max_objective_evaluations=128, fixed_seed='exact-equivalence')
        for changes in ({}, {'fee_bps':'1'}, {'minimum_cash_buffer':'99'},
                        {'max_objective_evaluations':1}, {'entered_cash':'1/2'},
                        {'training_scenarios':[{'A':'1','B':'1','C':'1'}], 'scenario_dates':['2026-10-01']}):
            with self.subTest(changes=changes):
                arguments = dict(base, **changes)
                self.assertEqual(accelerated(**arguments), original(**arguments))


if __name__ == '__main__':
    unittest.main()
