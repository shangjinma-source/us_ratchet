from copy import deepcopy
import unittest
from backtest import ndx_saved_risk_chain_display_research as core
from backtest import ndx_dated_path_risk_display_research as projection
from test_ndx_dated_path_risk_display_research import fixture


class Tests(unittest.TestCase):
    def test_unknown_zero_original_sum_and_dual_classes(self):
        entries = [dict(security_id='GOOG', risk_chain='internet', saved_value=0.4),
                   dict(security_id='GOOGL', risk_chain='internet', saved_value='0.2'),
                   dict(security_id='unknown', risk_chain=None, saved_value='0.1'),
                   dict(security_id='zero', risk_chain='unclassified', saved_value=0)]
        result = core.grouped(entries)
        self.assertEqual(result['security_count'], 4)
        self.assertEqual(result['saved_literal_total'], core.ratio(core.Fraction(7, 10)))
        self.assertEqual(result['rows'][0]['normalized_display_share'], core.ratio(core.Fraction(6, 7)))
        self.assertEqual(result['unknown_saved_literal_total'], core.ratio(core.Fraction(1, 10)))
        self.assertEqual(len(result['rows']), 3)

    def test_cash_initial_contribution_zero_and_missing_are_distinct(self):
        item = projection.project_saved_comparison(**fixture())
        before = deepcopy(item)
        result = core.project_chain_display(item)
        cash = result['tracks']['candidate_integer']['rows'][0]
        self.assertIsNone(cash['aggregation']['normalized_display_denominator'])
        self.assertEqual(cash['cash_fraction_display'], core.ratio(core.Fraction(1)))
        self.assertIsNone(result['tracks']['candidate_continuous']['rows'][0]['aggregation']['normalized_display_denominator'])
        self.assertEqual(item, before)
        missing = core.project_chain_display(projection.project_saved_comparison(**fixture(missing=True)))
        self.assertIsNone(missing['tracks']['candidate_integer']['rows'])
        self.assertEqual(len(missing['tracks']['candidate_integer']['calendar_slots']), 127)

    def test_saved_stock_sum_not_forced_to_one_and_cash_separate(self):
        args = fixture()
        day = args['document']['comparison']['tracks']['candidate_integer']['original_account_preserved']['daily'][1]
        day.update(shares={'candidate1': 1}, cash_usd=10000., total_value_usd=25000.,
                   risk={'actual_weights': {'candidate1': 0.9999999999999999}, 'checks': {'MAX_SINGLE_WEIGHT': False}},
                   risk_chains={'candidate1': None}, risk_chain_observation_dates={'candidate1': '2026-03-20'})
        result = core.project_chain_display(projection.project_saved_comparison(**args))
        row = result['tracks']['candidate_integer']['rows'][1]
        self.assertEqual(row['aggregation']['saved_literal_total'], core.ratio(core.Fraction('0.9999999999999999')))
        self.assertEqual(row['cash_fraction_display'], core.ratio(core.Fraction(2, 5)))
        self.assertFalse(row['saved_risk']['checks']['MAX_SINGLE_WEIGHT'])
        self.assertEqual(row['aggregation']['unknown_saved_literal_total'], row['aggregation']['saved_literal_total'])

    def test_bad_literals_and_denominator_rejected(self):
        for value in [True, float('nan'), -1, {'numerator':'1','denominator':'0'}]:
            with self.subTest(value=value), self.assertRaises((ValueError, ZeroDivisionError)):
                core.number(value)
        with self.assertRaises(ValueError):
            core.grouped([dict(security_id='x', risk_chain=None, saved_value=1)], defined=False)


if __name__ == '__main__':
    unittest.main()
