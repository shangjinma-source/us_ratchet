"""Independent checks against the frozen real stage-two selector."""
import unittest
import pandas as pd
from backtest.ndx_cardinality_discovery import select_multifrontier_security_sets
from backtest.ndx_two_stage_joint_coverage import select_joint_coverage_security_sets
from test_ndx_dynamic_envelope_policy import candidate


class JointCoverageOracle(unittest.TestCase):
    def frame(self):
        rows = []
        for index in range(17):
            ticker = f'A{index:02}' if index < 16 else 'AMAT'
            row = candidate(str(index), tickers=f'{ticker};AVGO;CDNS;GOOG',
                weights=f'{ticker}:.25;AVGO:.25;CDNS:.25;GOOG:.25',
                target_012922_distance=.06, turnover=.1)
            if index < 16:
                row['paired_return_p10_vs_incumbent'] = -.01
            rows.append(row)
        return pd.DataFrame(rows)

    def select(self, frame):
        return select_joint_coverage_security_sets(frame,
            selection_date='2024-05-01', decision_data_end='2024-04-30',
            per_frontier_limit=16, pareto_block_size=3)

    def test_actual_sixteen_limit_misses_preference_and_joint_candidate(self):
        frame = self.frame()
        before = frame.copy(deep=True)
        legacy = select_multifrontier_security_sets(frame, per_frontier_limit=16)
        preferred = 'AMAT;AVGO;CDNS;GOOG'
        self.assertNotIn(preferred, set(legacy['tickers']))
        result = self.select(frame)
        selected = set(result['selected']['tickers'])
        self.assertTrue(set(legacy['tickers']).issubset(selected))
        self.assertIn(preferred, selected)
        pd.testing.assert_frame_equal(frame, before)

    def test_block_partition_and_input_order_preserve_exact_union(self):
        frame = self.frame()
        a = self.select(frame)
        b = select_joint_coverage_security_sets(frame.iloc[::-1],
            selection_date='2024-05-01', decision_data_end='2024-04-30',
            per_frontier_limit=16, pareto_block_size=1)
        pd.testing.assert_frame_equal(a['selected'], b['selected'])

    def test_exact_pareto_matches_independent_pairwise_definition(self):
        frame = self.frame().iloc[:12].copy()
        columns = ['return_p50_vs_012922', 'return_p10_vs_012922',
                   'max_drawdown_p50_vs_012922', 'max_drawdown_p90_vs_012922',
                   'paired_return_p50_vs_incumbent', 'paired_return_p10_vs_incumbent',
                   'paired_drawdown_cost_p50_vs_incumbent', 'paired_drawdown_cost_p90_vs_incumbent']
        for i in range(len(frame)):
            values = [((i * 7 + j * 3) % 11 - 5) * .01 for j in range(8)]
            values[4:6] = sorted(values[4:6], reverse=True)
            values[6:8] = sorted(values[6:8])
            frame.loc[i, columns] = values
        vectors = [[max(0., -float(row[k]) if j in (0, 1, 4, 5) else float(row[k]))
                    for j, k in enumerate(columns)] for row in frame.to_dict('records')]
        indexes = [i for i, vector in enumerate(vectors) if not any(
            all(a <= b for a, b in zip(other, vector)) and any(a < b for a, b in zip(other, vector))
            for other in vectors)]
        result = select_joint_coverage_security_sets(frame,
            selection_date='2024-05-01', decision_data_end='2024-04-30',
            per_frontier_limit=1, pareto_block_size=2)
        self.assertEqual(result['audit']['deficit_pareto_count'], len(indexes))
        self.assertTrue(set(frame.iloc[indexes]['tickers']).issubset(set(result['selected']['tickers'])))

    def test_all_zero_deficit_ties_are_kept_without_hidden_limit(self):
        frame = self.frame()
        frame['paired_return_p10_vs_incumbent'] = .01
        result = select_joint_coverage_security_sets(frame,
            selection_date='2024-05-01', decision_data_end='2024-04-30',
            per_frontier_limit=1, pareto_block_size=2)
        self.assertEqual(result['audit']['deficit_pareto_count'], 17)
        self.assertEqual(len(result['selected']), 17)

    def test_invalid_paired_quantile_order_is_rejected(self):
        frame = self.frame()
        frame.loc[0, 'paired_return_p10_vs_incumbent'] = 1.
        with self.assertRaises(ValueError):
            self.select(frame)
        frame = self.frame()
        frame.loc[0, 'paired_drawdown_cost_p50_vs_incumbent'] = 1.
        with self.assertRaises(ValueError):
            self.select(frame)


if __name__ == '__main__':
    unittest.main()
