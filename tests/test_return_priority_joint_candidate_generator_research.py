"""Small synthetic checks only; no actual prices, search history or book calls."""
from copy import deepcopy
from fractions import Fraction
import unittest

from backtest.return_priority_joint_candidate_generator_research import generate_joint_candidates


def inputs(count=8):
    securities = ['S' + str(index) for index in range(count)]
    metadata = {security: {'ticker': security, 'issuer_id': 'I' + str(index),
                           'risk_chain': 'C' + str(index), 'source_refs': ['SYNTHETIC']}
                for index, security in enumerate(securities)}
    return dict(decision_date='2026-08-20', ordered_security_ids=securities,
                metadata=metadata, close_prices={security: 10 for security in securities},
                entered_cash=100000, fee_bps=10, minimum_cash_buffer=100,
                risk_parameters=dict(min_single_weight='0.05', max_single_weight='0.5',
                                     top_three_cap='0.8', min_neff_ratio='0.5', chain_cap='0.5'),
                source_context=dict(ranking_as_of='2026-08-20', close_as_of='2026-08-20',
                                    qualification_start='2026-03-20', qualification_end='2026-09-21',
                                    source_refs=['SYNTHETIC_ONLY']), fixed_seed='joint-v1')


class JointCandidatesTests(unittest.TestCase):
    def test_joint_variation_and_exact_budget_identity(self):
        arguments = inputs()
        before = deepcopy(arguments)
        output = generate_joint_candidates(**arguments)
        self.assertEqual(before, arguments)
        self.assertEqual(output, generate_joint_candidates(**arguments))
        legal = [row for row in output['records'] if row['status'] == 'LEGAL_INDICATIVE_ONLY']
        self.assertGreater(len({row['requested_k'] for row in legal}), 1)
        four = [row for row in legal if row['requested_k'] == 4]
        self.assertEqual({row['composition_rule'] for row in four}, {'RANK_TOP', 'FIXED_SEED_SUBSET'})
        self.assertGreater(len({tuple(row['security_ids']) for row in four}), 1)
        self.assertEqual({row['weight_rule'] for row in legal}, {'EQUAL', 'ORDINAL_TILT'})
        self.assertEqual({row['stock_exposure'] for row in legal}, {'1/2', '3/4', '1'})
        self.assertLessEqual(len(output['records']), 12 * 8 + 1)
        for row in legal:
            self.assertEqual(Fraction(row['indicative_total_cost']) + Fraction(row['indicative_residual_cash']), 100000)
            self.assertEqual(row['entered_cash_pool'], '100000')
            self.assertEqual(row['actual_k'], row['requested_k'])
            self.assertTrue(row['risk']['all_passed'])
            self.assertEqual(sum(map(Fraction, row['stock_internal_profile_weights'].values())), 1)
        unequal = [row for row in legal if row['weight_rule'] == 'ORDINAL_TILT']
        self.assertTrue(any(len(set(row['stock_internal_profile_weights'].values())) > 1 for row in unequal))

    def test_structural_all_k_and_no_fake_targets(self):
        output = generate_joint_candidates(**inputs(21))
        structural = {row['requested_k']: row for row in output['records'] if row['status'] == 'BLOCKED_STRUCTURAL'}
        self.assertEqual(output['all_k_considered'], list(range(1, 22)))
        self.assertIn('K_TIMES_MIN_WEIGHT_EXCEEDS_ONE', structural[21]['blocked_reasons'])
        self.assertIn('K_TIMES_MAX_WEIGHT_BELOW_ONE', structural[1]['blocked_reasons'])
        self.assertIn('K_AT_MOST_THREE_WITH_TOP_THREE_CAP_BELOW_ONE', structural[3]['blocked_reasons'])
        self.assertTrue(all('target_weights' not in row for row in structural.values()))

    def test_existing_class_competition_and_unique_issuers(self):
        arguments = inputs()
        arguments['metadata']['GOOG'] = dict(arguments['metadata']['S0'], ticker='GOOG')
        arguments['metadata']['GOOGL'] = dict(arguments['metadata']['S0'], ticker='GOOGL')
        del arguments['metadata']['S0']
        arguments['ordered_security_ids'] = ['GOOG', 'GOOGL'] + arguments['ordered_security_ids'][1:]
        del arguments['close_prices']['S0']
        arguments['close_prices'].update(GOOG=10, GOOGL=10)
        # Freeze a fixture seed with a different class choice; no market returns exist.
        arguments['fixed_seed'] = 'class-1'
        output = generate_joint_candidates(**arguments)
        full = [row for row in output['records'] if row.get('requested_k') == 8 and 'security_ids' in row]
        classes = set()
        for row in full:
            selected = row['security_ids']
            self.assertEqual(len({arguments['metadata'][security]['issuer_id'] for security in selected}), len(selected))
            classes.update(set(selected) & {'GOOG', 'GOOGL'})
        self.assertEqual(classes, {'GOOG', 'GOOGL'})

    def test_zero_quantity_missing_price_and_cash_reference(self):
        arguments = inputs()
        arguments['entered_cash'] = 1
        output = generate_joint_candidates(**arguments)
        reference = output['records'][0]
        self.assertEqual(reference['target_shares'], {})
        self.assertEqual(reference['indicative_residual_cash'], '1')
        self.assertFalse(any(row['status'] == 'LEGAL_INDICATIVE_ONLY' for row in output['records']))
        self.assertTrue(any('ZERO_QUANTITY_REQUESTED_MEMBER' in row['blocked_reasons'] for row in output['records']))
        arguments = inputs()
        arguments['close_prices'].pop('S0')
        output = generate_joint_candidates(**arguments)
        affected = [row for row in output['records'] if 'S0' in row.get('security_ids', [])]
        self.assertTrue(all('DECISION_CLOSE_MISSING' in row['blocked_reasons'] for row in affected))

    def test_whole_lot_risk_is_not_assumed_from_profile(self):
        arguments = inputs(4)
        arguments['entered_cash'] = 1000
        arguments['minimum_cash_buffer'] = 0
        arguments['fee_bps'] = 0
        arguments['risk_parameters']['top_three_cap'] = '0.75'
        arguments['close_prices'] = dict(S0=100, S1=70, S2=70, S3=70)
        output = generate_joint_candidates(**arguments)
        full = [row for row in output['records'] if row.get('requested_k') == 4]
        self.assertTrue(any(row['profile_risk']['all_passed'] and
                            'INDICATIVE_WHOLE_LOT_RISK_FAILED' in row['blocked_reasons'] for row in full))

    def test_no_future_dates_and_empty_issuer_domain(self):
        arguments = inputs()
        arguments['source_context']['close_as_of'] = '2026-08-21'
        with self.assertRaises(ValueError):
            generate_joint_candidates(**arguments)
        arguments = inputs()
        arguments['source_context']['qualification_end'] = '2026-08-19'
        with self.assertRaises(ValueError):
            generate_joint_candidates(**arguments)
        output = generate_joint_candidates(**inputs(0))
        self.assertEqual(output['issuer_count'], 0)
        self.assertEqual(len(output['records']), 1)


if __name__ == '__main__':
    unittest.main()
