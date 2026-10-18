"""Independent synthetic claims, not authentication of actual sources."""
import copy
import unittest
from backtest import ndx_membership_evidence_horizon_research as m
from test_ndx_membership_evidence_horizon_research import fixture, gral


class IndependentHorizonTests(unittest.TestCase):
    def test_baseline_chain_not_only_requested_window_and_one_day_hole(self):
        a = fixture(); a['baseline_evidence']['as_of'] = '2026-03-01'
        r = m.evaluate_membership_evidence_horizon(**a)
        self.assertIsNone(r['eligible']); self.assertTrue(r['out_of_certified_horizon'])
        a['event_coverage_evidence'].update(start='2026-03-01', covered_intervals=[dict(start='2026-03-01', end='2026-03-18'), dict(start='2026-03-20', end='2026-09-21')])
        r = m.evaluate_membership_evidence_horizon(**a)
        self.assertIsNone(r['eligible'])
        self.assertIn('EVENT_COVERAGE_HAS_UNCOVERED_INTERVAL', r['reasons'])
        a['event_coverage_evidence']['covered_intervals'][1]['start'] = '2026-03-19'
        self.assertTrue(m.evaluate_membership_evidence_horizon(**a)['eligible'])

    def test_gral_expired_saved_block_is_not_a_removal(self):
        a = fixture(); a.update(required_start='2026-09-21', unresolved_cases=[gral()])
        before = copy.deepcopy(a)
        r = m.evaluate_membership_evidence_horizon(**a)
        self.assertEqual(r['known_active_gap_ids'], [])
        self.assertEqual(r['blocking_case_ids'], ['gral'])
        self.assertEqual(r['membership_status'], 'UNKNOWN')
        self.assertEqual(a, before)
        r['original_unresolved_cases'][0]['original_case']['notes'] = 'tampered output'
        self.assertEqual(a, before)

    def test_attested_hashes_do_not_authorize_and_future_membership_not_known(self):
        a = fixture(); r = m.evaluate_membership_evidence_horizon(**a)
        self.assertTrue(r['eligible'])
        for key in ('formal_eligibility_authorized', 'source_bytes_read', 'source_authenticity_reverified', 'point_in_time_certification_created', 'full_pool_completeness_certified', 'execution_authorized'):
            self.assertIs(r[key], False)
        for key in ('baseline_evidence', 'event_coverage_evidence', 'membership_evidence'):
            b = copy.deepcopy(a); b[key]['available_date'] = '2026-09-21'
            self.assertIsNone(m.evaluate_membership_evidence_horizon(**b)['eligible'])
        a['membership_evidence'].update(status='NONMEMBER', effective_start='2026-09-22', effective_end='2026-09-30')
        self.assertEqual(m.evaluate_membership_evidence_horizon(**a)['membership_status'], 'UNKNOWN')

    def test_hash_conflict_even_unusable_and_share_class_not_issuer_alias(self):
        a = fixture(); a['membership_evidence']['authenticated'] = False
        a['membership_evidence']['source_reference'] = dict(a['baseline_evidence']['source_reference'], sha256='f'*64)
        with self.assertRaises(ValueError): m.evaluate_membership_evidence_horizon(**a)
        a = fixture(); a['membership_evidence']['security_id'] = 'OTHER_CLASS'
        with self.assertRaises(ValueError): m.evaluate_membership_evidence_horizon(**a)
        a = fixture(); a['eligibility_checks']['risk'] = 1
        with self.assertRaises(ValueError): m.evaluate_membership_evidence_horizon(**a)
