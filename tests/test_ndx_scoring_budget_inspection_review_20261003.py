"""Independent adversarial checks; producers only supply a synthetic saved fixture."""
from copy import deepcopy
from fractions import Fraction
from math import comb
import unittest
from backtest import ndx_multidecision_scoring_budget_inspection_research as audit
from test_ndx_multidecision_scoring_budget_inspection_research import case, resign


class Review(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arguments, cls.plan = case()

    def rejected(self, change):
        plan = deepcopy(self.plan)
        change(plan)
        resign(plan)
        with self.assertRaises(ValueError):
            audit.inspect_scoring_budget(**self.arguments, saved_plan=plan)

    def test_closed_form_counts_and_exact_bound_witnesses(self):
        self.assertEqual(audit.inspect_scoring_budget(**self.arguments, saved_plan=self.plan)['status'], 'PASS')
        cards = audit.cards(audit.index(audit.groups(self.arguments['universe'])))
        for card in cards:
            k = card['k']
            expected = (comb(75, k) if k <= 75 else 0) + 2 * comb(75, k - 1)
            self.assertEqual(card['combination_count'], expected)
            self.assertEqual(bool(card['necessary_bound_certificates']), k < 4 or k > 20)
            for certificate in card['necessary_bound_certificates']:
                number = lambda x: Fraction(int(x['numerator']), int(x['denominator']))
                left, right = number(certificate['left']), number(certificate['right'])
                self.assertTrue(left < right if certificate['comparison'] == '<' else left > right)
                self.assertEqual(number(certificate['strict_gap']), abs(left - right))
        self.rejected(lambda p: p['rows'][0]['domain_coverage'][0]['necessary_bound_certificates'][0]['strict_gap'].update(numerator='0'))

    def test_transcript_is_not_a_set_or_just_accepted_positions(self):
        log = self.plan['rows'][0]['sampling']['proposal_log']
        rejected_index = next(i for i, row in enumerate(log) if row['outcome'] != 'ACCEPTED')
        def omit_rejection(p):
            sampling = p['rows'][0]['sampling']
            sampling['proposal_log'].pop(rejected_index)
            sampling['proposal_count'] -= 1
            for i, row in enumerate(sampling['proposal_log']): row['proposal_index'] = i
        self.rejected(omit_rejection)
        self.rejected(lambda p: p['rows'][0]['sampling']['proposal_log'].reverse())
        self.rejected(lambda p: p['rows'][0]['sampling']['proposal_log'][0].update(rank=True))
        self.rejected(lambda p: p['rows'][0]['sampling']['cardinality_coverage'][0].update(selected_position_count=False))

    def test_resigned_job_cannot_swap_fee_prior_or_mode(self):
        for field, value in [('internal_initial_previous_weights', {}),
                             ('first_candidate_fee_reference', {'path':'future.json','sha256':'e'*64}),
                             ('fx_mode', 'BACKWARD_LATEST_VALID_FX')]:
            def attack(p, field=field, value=value):
                task = p['rows'][0]['mode_plans'][0]['tasks'][0]
                task['identity'][field] = value
                task['job_id'] = audit.digest(task['identity'])
            self.rejected(attack)
        self.rejected(lambda p: p['rows'][0]['mode_plans'][0].update(score_dispatch_authorized=0))


if __name__ == '__main__': unittest.main()
