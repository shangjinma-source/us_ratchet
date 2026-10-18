"""Independent first-actual policy counterexamples, never a real writer run."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from backtest import ndx_gap_monthly_observation_policy_research as policy
from backtest import ndx_prospective_observation_receipt_research as payload
from scripts import ndx_prospective_observation_writer_20261003 as writer
from test_ndx_prospective_observation_receipt_research import fixture, csv_item, ref


def row(sequence, session, kind, seal):
    return dict(sequence=sequence, session=session, kind=kind, seal_status=seal,
                evidence_reference=dict(ref('evidence'+str(sequence)), json_pointer='/rows/'+str(sequence)))


class FirstActualReview(unittest.TestCase):
    def test_gap_never_consumes_month_and_success_cannot_displace_first(self):
        for first_seal in ('NOT_ATTEMPTED', 'FAILED', 'UNKNOWN', 'SEALED'):
            known = [row(1, '2026-10-01', 'MISSED_OBSERVATION', 'NOT_ATTEMPTED')]
            new = [row(2, '2026-10-02', 'PROSPECTIVE_OBSERVED_SESSION', first_seal),
                   row(3, '2026-10-05', 'PROSPECTIVE_OBSERVED_SESSION', 'SEALED')]
            before = deepcopy((known, new))
            out = policy.monthly_observation_coordinates(policy_id=policy.POLICY_ID, known_rows=known, new_prospective_observations=new)
            self.assertEqual([r['monthly_coordinate_eligible'] for r in out['rows']], [False, True, False])
            self.assertEqual(out['months'][0]['first_observed_session'], '2026-10-02')
            self.assertEqual((known, new), before)
            self.assertTrue(all(r['seal_outcome_used_to_select_coordinate'] is False for r in out['rows']))
            self.assertIs(out['candidate_seal_allowed'], False)
            self.assertIs(out['oos_recovery_completed'], False)

    def test_late_first_remains_first_and_failed_parent_blocks_success_shopping(self):
        first = fixture()
        timely = payload.prepare_observation_payload(**first)
        first['writer_completed_at_utc'] = '2026-10-05T13:30:00+00:00'
        late = payload.prepare_observation_payload(**first)
        self.assertEqual(late['observation_id'], timely['observation_id'])
        self.assertEqual(late['timing_classification'], 'LATE_OBSERVATION')
        self.assertTrue(late['month_first_actual_observation'])
        self.assertTrue(all(late[k] is False for k in payload.FLAGS))
        for seal in ('FAILED', 'UNKNOWN'):
            a = fixture()
            a['known_typed_rows'].append(row(2, '2026-10-02', 'PROSPECTIVE_OBSERVED_SESSION', seal))
            a['parent_attempt_inventory'] = [dict(observation_id=late['observation_id'], status='PERSISTED_AND_INDEPENDENTLY_READ_BACK', session='2026-10-02', payload_reference=ref('evidence2'), receipt_reference=ref('receipt2'), independent_readback_reference=ref('audit2'))]
            a['session'] = '2026-10-05'
            for ticker in ('QQQ', 'SPY'):
                a['capture']['baseline_sources'][ticker] = csv_item('base'+ticker, ['2026-10-01', '2026-10-02'])
                a['capture']['sources'][ticker] = csv_item(ticker, ['2026-10-01', '2026-10-02', '2026-10-05'])
            a['capture']['started_at_utc'] = '2026-10-05T20:00:00+00:00'
            a['capture']['completed_at_utc'] = '2026-10-05T20:00:01+00:00'
            a['writer_started_at_utc'] = '2026-10-05T20:00:02+00:00'
            a['writer_completed_at_utc'] = '2026-10-05T20:00:03+00:00'
            out = payload.prepare_observation_payload(**a)
            self.assertFalse(out['month_first_actual_observation'])
            self.assertEqual(out['first_actual_observed_session_of_month'], '2026-10-02')
            self.assertEqual(out['timing_classification'], 'WITHIN_CONSERVATIVE_OBSERVATION_WINDOW')
            self.assertIs(out['candidate_seal_allowed'], False)
            a['parent_attempt_inventory'] = []
            with self.assertRaises(ValueError):
                payload.prepare_observation_payload(**a)

    def test_gap_not_promoted_and_parent_observation_not_skipped(self):
        a = fixture()
        a['known_typed_rows'][0]['seal_status'] = 'SEALED'
        with self.assertRaises(ValueError):
            payload.prepare_observation_payload(**a)
        a = fixture()
        for ticker in ('QQQ', 'SPY'):
            a['capture']['sources'][ticker] = csv_item(ticker, ['2026-10-01', '2026-10-02', '2026-10-05'])
        with self.assertRaises(ValueError):
            payload.prepare_observation_payload(**a)
        with patch.object(writer, 'BOUND', dict.fromkeys(writer.BOUND)), patch.object(Path, 'read_bytes', side_effect=AssertionError('Pending writer must not read sources')):
            with self.assertRaises(ValueError):
                writer.load_inputs()


if __name__ == '__main__':
    unittest.main()
