"""Independent saved-evidence grammar review. No optimizer or actual replay."""
from copy import deepcopy
import itertools
import unittest
from unittest.mock import patch

from backtest import ndx_registered_scoring_result_inspection_v2_research as subject
from test_ndx_registered_scoring_result_inspection_v2_research import attempt, fixture, source_map


class IndependentReview(unittest.TestCase):
    def test_dp_matches_explicit_grammar_exhaustively(self):
        # Enumerate all evidence words through length four, against explicit
        # per-window grammar rather than duplicating the state transition code.
        securities = [dict(ticker='A')]
        tokens = {
            'G': dict(grouped=True, successful=True, weights={'A': 1.}, raw_target={'A': 2.}),
            'F': dict(grouped=True, successful=False, weights=None, raw_target={'A': 2.}),
            'U': dict(grouped=False, successful=True, weights={'A': 1.}, raw_target={'A': 2.}),
            'X': dict(grouped=False, successful=True, weights={'A': .5}, raw_target={'A': 2.}),
        }
        words = [word for size in range(5) for word in itertools.product(tokens, repeat=size)]
        for flags in itertools.product((False, True), repeat=3):
            grammar = [((), ('F',), ('U',), ('F', 'U')) if relaxed else ((), ('G',)) for relaxed in flags]
            legal = {sum(parts, ()) for parts in itertools.product(*grammar)}
            windows = [dict(weights=[1.], projection_relaxed=flag) for flag in flags]
            with patch.object(subject, 'recovery_attempt', side_effect=lambda token, *_: tokens[token]):
                for word in words:
                    with self.subTest(flags=flags, word=word):
                        if word in legal:
                            report = subject.inspect_recovery_evidence(list(word), windows, securities, subject.SPECS[1], {})
                            self.assertFalse(report['unique_window_assignment_claimed'])
                        else:
                            with self.assertRaises(ValueError):
                                subject.inspect_recovery_evidence(list(word), windows, securities, subject.SPECS[1], {})

    def test_same_window_pair_requires_same_raw_target(self):
        args = fixture(); securities = args['saved_fit']['securities']
        first = attempt(securities, passed=False)
        second = attempt(securities, grouped=False)
        # Different scale preserves both individually normalized objectives.
        second['reconstruction']['raw_target'] = dict.fromkeys(second['reconstruction']['raw_target'], .5)
        windows = [dict(weights=[.25]*4, projection_relaxed=True)]
        with self.assertRaisesRegex(ValueError, 'no legal ordered'):
            subject.inspect_recovery_evidence([first, second], windows, securities, subject.SPECS[1], source_map())
        # Two separate windows permit different raw targets, with ambiguity kept.
        subject.inspect_recovery_evidence([first, second], windows*2, securities, subject.SPECS[1], source_map())

    def test_impossible_saved_early_status_rejected(self):
        args = fixture(); securities = args['saved_fit']['securities']
        base = attempt(securities, passed=False)
        for status in ('SUBSET_BUDGET_EXCEEDED', 'PROPOSED_AFFINE_FACE_UNRESOLVED', 'PROPOSED_FACE_HHI_INTERSECTION_UNRESOLVED'):
            value = deepcopy(base)
            reconstruction = value['reconstruction']
            keep = subject.RECON_BASE if status == 'SUBSET_BUDGET_EXCEEDED' else subject.RECON_BASE | subject.RECON_AFFINE
            if status == 'PROPOSED_FACE_HHI_INTERSECTION_UNRESOLVED':
                keep |= {'hhi_radius_squared'}
            value['reconstruction'] = {key: item for key, item in reconstruction.items() if key in keep}
            value['reconstruction']['status'] = status
            # k=4 gives four subsets, and saved radius is +0.1: neither
            # branch can be produced by the frozen source at these values.
            with self.subTest(status=status), self.assertRaises(ValueError):
                subject.recovery_attempt(value, securities, source_map())

    def test_final_stage_cannot_skip_earlier_failed_guards(self):
        args = fixture(); securities = args['saved_fit']['securities']
        for field, invalid_value in (('affine_center_residuals', [2e-10]), ('hhi_radius_squared', -2e-12)):
            value = attempt(securities, passed=False)
            value['reconstruction'][field] = invalid_value
            with self.subTest(field=field), self.assertRaises(ValueError):
                subject.recovery_attempt(value, securities, source_map())

    def test_legitimate_finite_early_failure_guards(self):
        args = fixture(); securities = args['saved_fit']['securities']
        for status in ('AFFINE_SVD_UNRESOLVED', 'PROPOSED_AFFINE_FACE_UNRESOLVED', 'PROPOSED_FACE_HHI_INTERSECTION_UNRESOLVED'):
            value = attempt(securities, passed=False)
            keep = subject.RECON_BASE.copy()
            if status != 'AFFINE_SVD_UNRESOLVED':
                keep |= subject.RECON_AFFINE
            if status == 'PROPOSED_FACE_HHI_INTERSECTION_UNRESOLVED':
                keep |= {'hhi_radius_squared'}
            value['reconstruction'] = {key: item for key, item in value['reconstruction'].items() if key in keep}
            value['reconstruction']['status'] = status
            if status == 'PROPOSED_AFFINE_FACE_UNRESOLVED':
                value['reconstruction']['affine_center_residuals'] = [-2e-10]
            if status == 'PROPOSED_FACE_HHI_INTERSECTION_UNRESOLVED':
                value['reconstruction']['hhi_radius_squared'] = -2e-12
            with self.subTest(status=status):
                self.assertFalse(subject.recovery_attempt(value, securities, source_map())['successful'])

    def test_original_source_prior_and_score_gates_remain(self):
        for change in ('matrix', 'prior', 'fit_hash', 'score', 'authority'):
            args = fixture()
            if change == 'matrix':
                args['assembled']['rolling_inputs']['candidate_returns'][0][0] += .001
                args['assembled']['content_sha256'] = subject.digest({k: v for k, v in args['assembled'].items() if k != 'content_sha256'})
            elif change == 'prior':
                args['saved_fit']['windows'][1]['requested_inner_prior'] = None
            elif change == 'fit_hash':
                args['saved_fit']['windows'][0]['fit_data_sha256'] = 'f'*64
            elif change == 'score':
                args['saved_score_inspection']['foreign_field'] = True
            else:
                args['saved_fit']['promotion_allowed'] = True
            with self.subTest(change=change), self.assertRaises(ValueError):
                subject.inspect_registered_scoring_result(**args)


if __name__ == '__main__':
    unittest.main()
