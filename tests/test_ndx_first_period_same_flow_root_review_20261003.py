from fractions import Fraction
import unittest
from backtest import ndx_first_period_same_flow_comparison_research as core
from test_ndx_first_period_same_flow_comparison_research import fixture


class ReviewTests(unittest.TestCase):
    def test_absolute_target_distance_does_not_reward_return_overshoot(self):
        def metrics(r, dd):
            return dict(cumulative_return=core.window.ratio(Fraction(r)),
                        maximum_drawdown=core.window.ratio(Fraction(dd)),
                        annualized_return_diagnostic_decimal=r)
        result = core.nav_distances({'candidate': metrics('.3', '.05'), 'same_flow_incumbent': metrics('.15', '.15')}, metrics('.1', '.2'))
        delta = result['candidate_minus_incumbent_absolute_distance']
        self.assertEqual(core.window.from_ratio(delta['cumulative_return']), Fraction(3, 20))
        self.assertEqual(core.window.from_ratio(delta['maximum_drawdown']), Fraction(1, 10))
        self.assertFalse(result['currency_equivalence_verified'])

    def test_nav_lag_and_unknown_publication_remain_explicit(self):
        args = fixture()
        rows = args['benchmark_document']['nav']['rows']
        rows[1]['nav_date'] = rows[0]['nav_date']
        result = core.nav_reference(args['benchmark_document'], args['benchmark_reference'])
        self.assertEqual(result['observations'][1]['calendar_day_lag'], 3)
        self.assertIsNone(result['observations'][1]['publication_time'])
        self.assertFalse(result['fx_conversion_performed'])
        self.assertFalse(result['formal_admission_allowed'])

    def test_identical_terminal_returns_do_not_hide_interim_drawdown(self):
        args = fixture()
        for row in args['candidate_accounts']['rows']:
            row['account']['rows'][40]['cumulative_twr'] = core.window.ratio(Fraction(-3, 4))
        result = core.compare_first_period_paths(**args)
        for row in result['rows']:
            self.assertEqual(core.window.from_ratio(row['metrics']['candidate']['cumulative_return']), Fraction(1, 5))
            self.assertGreaterEqual(core.window.from_ratio(row['metrics']['candidate']['maximum_drawdown']), Fraction(3, 4))
            self.assertFalse(row['formal_dual_benchmark_admission'])


if __name__ == '__main__':
    unittest.main()
