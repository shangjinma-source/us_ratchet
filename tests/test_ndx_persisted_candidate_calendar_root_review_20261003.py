"""Independent association attacks against the persisted calendar adapter."""
import unittest

from backtest import ndx_persisted_candidate_calendar_research as subject
from test_ndx_persisted_candidate_calendar_research import fixture


class PersistedCalendarReview(unittest.TestCase):
    def test_writer_version_is_not_inferred_from_audit_label(self):
        for role in ('payload', 'receipt'):
            supplied = fixture()
            supplied['observation'][role]['writer_adapter_schema'] = 'FOREIGN_WRITER'
            with self.subTest(role=role), self.assertRaises(ValueError):
                subject.prepare_persisted_candidate_evidence(**supplied)

    def test_compact_entry_cannot_disagree_with_its_selected_receipt(self):
        replacements = {
            'initial_seal_status': 'SEALED',
            'timing_classification': 'LATE_OBSERVATION',
            'payload_timing_classification': 'LATE_OBSERVATION',
            'month_first_actual_observation': False,
            'first_actual_observed_session_of_month': '2026-11-03',
        }
        for field, value in replacements.items():
            supplied = fixture()
            supplied['history']['document']['observations'][-1][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                subject.prepare_persisted_candidate_evidence(**supplied)

    def test_capture_audit_must_bind_the_snapshot_it_claims_to_verify(self):
        for ticker in ('QQQ', 'SPY', 'tzif'):
            supplied = fixture()
            capture = supplied['capture']
            reference = capture['document']['captured_artifacts'][ticker]
            capture['readback']['source_hashes'].pop(reference['path'], None)
            with self.subTest(ticker=ticker), self.assertRaises(ValueError):
                subject.prepare_persisted_candidate_evidence(**supplied)


if __name__ == '__main__':
    unittest.main()
