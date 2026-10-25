"""Arithmetic tamper tests; V27 proof is a separate already tested reviewer."""
from copy import deepcopy
from unittest.mock import patch
import unittest

import test_relative_volatility_monthly_research as sizing_fixtures
from backtest.relative_volatility_monthly_research import scale_selection
from backtest import relative_variance_independent_review as review


class IndependentRelativeReviewTests(unittest.TestCase):
    def fixture(self):
        selected, window = sizing_fixtures.RelativeSizingTests().fixture(True)
        selected['investable_equity'] = '20000'
        args = selected['raw_selection']['binding']['search_arguments']
        args['scenario_dates'] = window['training_dates'][21::21]
        return scale_selection(selected, window), window

    def assess(self, selected, window):
        original = selected['v27_selection']
        proof = dict(target_quantities=original['target_quantities'],strict_improvement=True,rescored_baskets=3)
        with patch.object(review, '_review_v27', return_value=proof):
            return review.review_selection(selected, window)

    def test_independent_formula_and_proof_fields(self):
        selected, window = self.fixture()
        result = self.assess(selected, window)
        self.assertEqual(result['target_quantities'], selected['target_quantities'])
        self.assertTrue(result['strict_improvement'])
        self.assertEqual(result['rescored_baskets'], 3)

    def test_reject_corrupt_multiplier_target_binding_and_future(self):
        for mutation in ('multiplier','target','binding','future'):
            with self.subTest(mutation=mutation):
                selected, window = self.fixture()
                if mutation == 'multiplier':
                    selected['relative_risk']['multiplier']['numerator_hex'] = '1'
                elif mutation == 'target':
                    selected['target_quantities']['S'] += 1
                elif mutation == 'binding':
                    selected['relative_binding']['training_input_sha256'] = '0'*64
                else:
                    window['training_dates'][-1] = '2030-01-01'
                with self.assertRaises(ValueError):
                    self.assess(selected, window)

    def test_reject_training_change_even_with_self_consistent_binding(self):
        selected, window = self.fixture()
        window = deepcopy(window)
        window['candidates'][0]['training_close'][3] = '101'
        selected['relative_binding']['training_input_sha256'] = review.canonical(dict(
            dates=window['training_dates'], candidates=window['candidates']))
        selected['relative_decision_id'] = review.canonical(selected['relative_binding'])
        with self.assertRaises(ValueError):
            self.assess(selected, window)


if __name__ == '__main__':
    unittest.main()
