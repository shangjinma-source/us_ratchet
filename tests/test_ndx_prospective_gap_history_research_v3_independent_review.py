"""Independent attacks on gap classification, historical pointers and source associations."""
import copy
import unittest
from backtest import ndx_prospective_gap_history_research_v3 as module
import test_ndx_prospective_gap_history_research_v3 as fixtures


class IndependentGapReviewTests(unittest.TestCase):
    def test_parent_publication_and_readback_cannot_contradict_original_oos_boundary(self):
        for role in ('publication', 'readback'):
            for field in ('future_independent_oos', 'live_mutation_allowed', 'production_generator_authorized'):
                args = fixtures.fixture()
                args['parent'][role][field] = True
                with self.subTest(role=role, field=field), self.assertRaises(ValueError):
                    module.extend_gap_history(**args)

    def test_failed_unknown_observation_keeps_october_coordinate_and_bytes(self):
        for status in ('FAILED', 'UNKNOWN'):
            args = fixtures.fixture()
            args['parent']['document']['known_typed_rows'][-1]['seal_status'] = status
            # Parent assertions are intentionally synthetic; the real IO layer must bind hashes.
            args['capture']['document']['plan']['known_typed_rows_preserved'][-1]['seal_status'] = status
            before = copy.deepcopy(args)
            out = module.extend_gap_history(**args)
            self.assertEqual(args, before)
            self.assertEqual(out['known_typed_rows'][:66], before['parent']['document']['known_typed_rows'])
            self.assertEqual(out['known_typed_rows'][65]['seal_status'], status)
            self.assertEqual(out['first_actual_observed_session_by_month']['2026-10'], '2026-10-02')
            self.assertEqual(out['observation_count'], 1)

    def test_empty_new_source_domain_cannot_create_observation_or_gap(self):
        out = module.extend_gap_history(**fixtures.fixture([]))
        self.assertEqual(out['status'], 'NO_EXPIRED_SESSION_TO_APPEND')
        self.assertEqual(out['new_missed_observation_count'], 0)
        self.assertEqual(out['typed_row_count'], 66)
        self.assertEqual(out['last_accounted_session'], '2026-10-02')
        self.assertFalse(out['observation_created'])

    def test_duplicate_historical_pointer_and_reference_hash_conflict_rejected(self):
        for attack in ('pointer', 'source_conflict'):
            args = fixtures.fixture()
            if attack == 'pointer':
                original = args['parent']['document']['known_typed_rows']
                original[1]['evidence_reference'] = copy.deepcopy(original[0]['evidence_reference'])
                args['parent']['document']['genesis_preserved']['document']['projection_inputs']['known_rows'][1]['evidence_reference'] = copy.deepcopy(original[0]['evidence_reference'])
            else:
                reference = args['capture']['reader_reference']
                args['capture']['readback']['source_hashes'][reference['path']] = 'e' * 64
            with self.subTest(attack=attack), self.assertRaises(ValueError):
                module.extend_gap_history(**args)

    def test_whole_interval_before_deadline_even_with_completed_after_deadline_stays_pending(self):
        out = module.extend_gap_history(**fixtures.fixture(['2026-10-05'], start='2026-10-06T13:29:59.999999+00:00', end='2026-10-08T16:00:00+00:00'))
        self.assertEqual(out['new_missed_observation_count'], 0)
        self.assertEqual(out['pending_source_sessions'][0]['session'], '2026-10-05')

    def test_gap_coordinate_source_pointers_and_observation_role_are_separate(self):
        args = fixtures.fixture()
        out = module.extend_gap_history(**args)
        self.assertEqual(out['baseline_role'], 'LAST_ACTUAL_OBSERVATION_BASELINE_NOT_LAST_ACCOUNTED')
        self.assertEqual(out['last_observed_session'], '2026-10-02')
        self.assertEqual(out['last_accounted_session'], '2026-10-07')
        self.assertEqual(out['new_observation_count'], 0)
        self.assertTrue(all(out[key] is False for key in module.FLAGS))
        for row, gap in zip(out['known_typed_rows'][66:], out['gap_classifications']):
            for pointer in gap['source_session_pointer_by_ticker'].values():
                value = args['capture']['document']
                for part in pointer.split('/')[1:]:
                    value = value[int(part)] if isinstance(value, list) else value[part]
                self.assertEqual(value, row['session'])


if __name__ == '__main__':
    unittest.main()
