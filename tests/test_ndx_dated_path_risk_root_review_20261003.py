from copy import deepcopy
import unittest
from test_ndx_dated_path_risk_display_research import fixture
from backtest import ndx_dated_path_risk_display_research as core


class ReviewTests(unittest.TestCase):
    def test_unknown_held_label_stays_unknown_with_failed_saved_check(self):
        args = fixture()
        daily = args['document']['comparison']['tracks']['candidate_integer']['original_account_preserved']['daily'][1]
        daily.update(shares={'candidate1': 2}, risk={'actual_weights': {'candidate1': 1.0}, 'checks': {'RISK_CHAIN_TOP1_WEIGHT': False}},
                     risk_chains={'candidate1': None}, risk_chain_observation_dates={'candidate1': '2026-03-20'})
        result = core.project_saved_comparison(**args)
        row = result['tracks']['candidate_integer']['risk_rows'][1]
        self.assertIsNone(row['security_exposures'][0]['risk_chain'])
        self.assertEqual(row['security_exposures'][0]['saved_stock_weight'], 1.0)
        self.assertFalse(row['saved_risk']['checks']['RISK_CHAIN_TOP1_WEIGHT'])
        self.assertFalse(result['chain_totals_computed'])

    def test_both_equal_fx_series_have_separate_source_identity(self):
        first = core.project_saved_comparison(**fixture(first=True))
        result = core.collect_projections([first])
        nav = result['tasks'][0]['nav_modes']
        ids = [nav[m]['shared_path_id'] for m in core.MODES]
        self.assertNotEqual(*ids)
        self.assertEqual(result['shared_paths'][ids[0]]['payload']['observations'], result['shared_paths'][ids[1]]['payload']['observations'])
        self.assertFalse(result['source_bytes_authenticated'])
        self.assertFalse(result['full_queue_completeness_verified'])

    def test_cross_document_target_or_shared_source_substitution_rejected(self):
        args = fixture()
        args['inputs_document']['inputs']['original_fit_result']['targets']['candidate1']['target_weight'] = .95
        with self.assertRaises(ValueError):
            core.project_saved_comparison(**args)
        first = core.project_saved_comparison(**fixture(first=True))
        second = core.project_saved_comparison(**fixture())
        changed = deepcopy(second)
        changed['tracks']['incumbent_integer']['source_reference']['json_pointer'] = '/another/daily'
        with self.assertRaises(ValueError):
            core.collect_projections([first, changed])


if __name__ == '__main__':
    unittest.main()
