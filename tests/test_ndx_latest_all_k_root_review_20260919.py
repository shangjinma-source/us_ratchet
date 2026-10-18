"""Independent enumeration checks; no real fitting or artifact publication."""
import copy
import itertools
import unittest
from collections import Counter
from fractions import Fraction

from test_ndx_latest_conditional_all_k_refit_20260919 import panel, PARAMETERS
from scripts import ndx_latest_conditional_all_k_refit_20260919 as recipe


class AllKRootReview(unittest.TestCase):
    def test_exact_sets_specs_and_alias_references(self):
        sample = panel(6)
        plan = recipe.enumerate_plan(sample, PARAMETERS, 50000)
        identifiers = sorted(sample['universe']['security_id'])
        expected = {tuple(c) for k in range(4, 7) for c in itertools.combinations(identifiers, k)}
        by_group = {}
        for task in plan['canonical_tasks']:
            group = tuple(sorted(task['selected']))
            by_group.setdefault(group, []).append(task)
            self.assertEqual(task['task_id'], recipe.digest({k: v for k, v in task.items() if k != 'task_id'}))
            self.assertIsNone(task['previous_target_weights'])
        self.assertEqual(set(by_group), expected)
        for tasks in by_group.values():
            self.assertEqual(Counter(t['weight_spec'] for t in tasks), Counter(equal_weight=1, constrained_fixed_shrinkage=1))
        fitted_ids = {t['task_id']: t for t in plan['canonical_tasks']}
        self.assertEqual(len(plan['anchor_aliases']), len(expected))
        for alias in plan['anchor_aliases']:
            original = fitted_ids[alias['canonical_task_id']]
            self.assertEqual(original['selected'], alias['selected'])
            self.assertEqual(original['weight_spec'], 'constrained_fixed_shrinkage')
            self.assertIs(alias['numerical_equivalence_verified'], False)
            self.assertIs(alias['actual_fitter_called'], False)
        for row in plan['cardinalities']:
            for certificate in row['necessary_infeasibility_certificates']:
                left, right = (Fraction(int(certificate[k]['numerator']), int(certificate[k]['denominator'])) for k in ('left', 'right'))
                self.assertTrue(left < right if certificate['comparison'] == '<' else left > right)

    def test_invalid_original_envelopes_cannot_emit_certificates(self):
        for change in ({'max_single_weight': 0.}, {'top_weight_cap': 1.01},
                       {'min_single_weight': .46}, {'shrinkage_intensity': -.1},
                       {'risk_chain_top1_cap': 0.}, {'turnover_anchor_strength': True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                recipe.enumerate_plan(panel(4), dict(PARAMETERS, **change), 50000)

    def test_modified_panel_is_rejected_before_enumeration(self):
        sample = panel(4)
        sample['returns'].iloc[0, 0] = .25
        with self.assertRaises(ValueError):
            recipe.enumerate_plan(sample, PARAMETERS, 50000)


if __name__ == '__main__':
    unittest.main()
