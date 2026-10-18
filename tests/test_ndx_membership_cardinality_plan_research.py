from copy import deepcopy
from fractions import Fraction
import hashlib
import itertools
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backtest import ndx_membership_cardinality_plan_research as planner


SCOPE = Path(__file__).resolve().parents[1] / 'config/ndx_membership_scope_research_v1.yaml'


def fixture(directory, count=100):
    path = Path(directory) / 'declared-mathematical-pool.json'
    path.write_text('synthetic input identity pool; not verified NDX membership')
    return dict(securities=[dict(security_id='security:' + str(index), issuer_id='issuer:' + str(index),
        ticker='X' + str(index)) for index in range(count)],
        risk_parameters=dict(max_single_weight=.45, min_single_weight=.05, top_weight_cap=.8,
                             minimum_effective_n_ratio=.7, risk_chain_top1_cap=.55),
        scope_path=SCOPE, scope_sha256=hashlib.sha256(SCOPE.read_bytes()).hexdigest(),
        source_hashes={str(path): hashlib.sha256(path.read_bytes()).hexdigest()},
        membership_input_status='PROXY_INPUT_NOT_VERIFIED_MEMBERSHIP', exact_limit=50000)


class MembershipCardinalityPlanTests(unittest.TestCase):
    def test_full100_k_denominator_original_bounds_and_no_false_membership(self):
        with tempfile.TemporaryDirectory() as directory:
            args = fixture(directory)
            result = planner.build_membership_cardinality_plan_research(**args)
            self.assertEqual([row['holding_count'] for row in result['rows']], list(range(1, 101)))
            self.assertEqual(result['structurally_excluded_cardinality_count'], 83)
            self.assertEqual(result['not_proven_feasible_cardinality_count'], 17)
            for row in result['rows']:
                if 4 <= row['holding_count'] <= 20:
                    self.assertEqual(row['structural_status'], 'NOT_PROVEN_FEASIBLE')
                    self.assertEqual(row['planned_search_mode'], 'BOUNDED_MULTIOBJECTIVE_SEARCH')
                else:
                    self.assertEqual(row['planned_search_mode'], 'NO_SEARCH_NECESSARY_BOUND_PROOF')
                self.assertFalse(row['search_admission_allowed'])
                for certificate in row['infeasibility_certificates']:
                    left = Fraction(int(certificate['left']['numerator']), int(certificate['left']['denominator']))
                    right = Fraction(int(certificate['right']['numerator']), int(certificate['right']['denominator']))
                    self.assertTrue(left < right if certificate['comparison'] == '<' else left > right)
            self.assertEqual(result['input_distinct_issuer_count'], 100)
            self.assertIsNone(result['verified_ndx_issuer_count'])
            self.assertFalse(result['full_ndx_coverage_verified'])
            self.assertFalse(result['membership_evidence_verified'])
            self.assertFalse(result['promotion_allowed'])

    def test_share_class_weighted_combination_dp_matches_enumeration(self):
        with tempfile.TemporaryDirectory() as directory:
            args = fixture(directory, 5)
            args['securities'][1]['issuer_id'] = args['securities'][0]['issuer_id']
            args['securities'][3]['issuer_id'] = args['securities'][2]['issuer_id']
            result = planner.build_membership_cardinality_plan_research(**args)
            self.assertEqual(result['maximum_reported_k'], 3)
            for row in result['rows']:
                combinations = list(itertools.combinations(args['securities'], row['holding_count']))
                unique = sum(len({item['issuer_id'] for item in combo}) == len(combo) for combo in combinations)
                self.assertEqual(int(row['raw_security_combinations']), len(combinations))
                self.assertEqual(int(row['issuer_unique_security_combinations']), unique)

    def test_original_tolerances_do_not_prune_accepted_equal_weight_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            args = fixture(directory, 21)
            for k, changed in ((21, dict(min_single_weight=1/21 + .5e-9)),
                               (4, dict(max_single_weight=.25 - .5e-9)),
                               (4, dict(top_weight_cap=.75 - .5e-9))):
                candidate = deepcopy(args)
                candidate['risk_parameters'].update(changed)
                result = planner.build_membership_cardinality_plan_research(**candidate)
                self.assertEqual(result['rows'][k-1]['infeasibility_certificates'], [])

    def test_small_grid_feasible_weights_never_receive_infeasibility_certificate(self):
        # Independent brute-force witnesses on a 0.1 simplex grid, not the DP.
        for k in range(1, 6):
            for maximum, minimum, top in ((.5, .1, 1.), (.45, .05, .8), (.3, .1, .9)):
                risk = {key: Fraction(str(value)) for key, value in dict(max_single_weight=maximum,
                    min_single_weight=minimum, top_weight_cap=top).items()}
                witnessed = any(max(parts)/10 <= maximum and min(parts)/10 >= minimum
                    and sum(sorted(parts, reverse=True)[:3])/10 <= top
                    for parts in itertools.product(range(1, 11), repeat=k) if sum(parts) == 10)
                if witnessed:
                    self.assertEqual(planner._necessary_bounds(k, risk), [])

    def test_empty_duplicate_bad_identity_parameters_or_verified_status_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for fault in ('empty', 'duplicate', 'bool', 'nan', 'missing', 'verified', 'relative_source', 'limit_bool'):
                args = fixture(directory, 4)
                if fault == 'empty': args['securities'] = []
                if fault == 'duplicate': args['securities'][1] = deepcopy(args['securities'][0])
                if fault == 'bool': args['risk_parameters']['min_single_weight'] = True
                if fault == 'nan': args['risk_parameters']['top_weight_cap'] = float('nan')
                if fault == 'missing': del args['risk_parameters']['risk_chain_top1_cap']
                if fault == 'verified': args['membership_input_status'] = 'VERIFIED_POINT_IN_TIME_MEMBER'
                if fault == 'relative_source': args['source_hashes'] = {'relative.json': 'a'*64}
                if fault == 'limit_bool': args['exact_limit'] = True
                with self.assertRaises(ValueError, msg=fault): planner.build_membership_cardinality_plan_research(**args)

    def test_input_order_invariance_and_source_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            args = fixture(directory, 5)
            before = planner.build_membership_cardinality_plan_research(**args)
            args['securities'].reverse()
            self.assertEqual(before, planner.build_membership_cardinality_plan_research(**args))
            original = planner.combinatorics.issuer_dedup_combination_counts

            def drift(values):
                Path(next(iter(args['source_hashes']))).write_text('changed')
                return original(values)

            with patch.object(planner.combinatorics, 'issuer_dedup_combination_counts', side_effect=drift):
                with self.assertRaisesRegex(ValueError, 'source drift'):
                    planner.build_membership_cardinality_plan_research(**args)


if __name__ == '__main__':
    unittest.main()
