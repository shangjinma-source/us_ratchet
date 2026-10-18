"""The frozen shortlist is not a completeness proof for the new hypothesis."""
import unittest
import pandas as pd
from scripts.ndx_cardinality_capital_sensitivity import CoordinateAccumulator
from backtest.ndx_dynamic_envelope_policy import evaluate_componentwise_envelope_candidates
from test_ndx_dynamic_envelope_policy import candidate


class OldShortlistCoverageCounterexample(unittest.TestCase):
    def test_actual_limit_eight_can_omit_the_only_jointly_qualified_row(self):
        rows = []
        for index in range(9):
            row = candidate(str(index), tickers='AA;BB;CC;DD',
                weights='AA:.25;BB:.25;CC:.25;DD:.25',
                target_012922_distance=.06, turnover=.1, constraint_failure_reasons='')
            if index < 8:
                row['paired_return_p10_vs_incumbent'] = -.01
            rows.append(row)
        accumulator = CoordinateAccumulator(8, ['AMAT', 'AVGO', 'CDNS', 'GOOG'])
        for row in rows:
            accumulator.add(row, dict(row))
        kept = accumulator.finish()
        self.assertEqual({row['portfolio_id'] for row in kept}, set(map(str, range(8))))
        full = evaluate_componentwise_envelope_candidates(pd.DataFrame(rows))
        reduced = evaluate_componentwise_envelope_candidates(pd.DataFrame(kept))
        self.assertEqual(full['groups'][0]['dual_benchmark_qualified_ids'], ['8'])
        self.assertEqual(reduced['groups'][0]['dual_benchmark_qualified_ids'], [])


if __name__ == '__main__':
    unittest.main()
