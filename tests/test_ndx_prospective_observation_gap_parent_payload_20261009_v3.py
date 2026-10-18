"""Synthetic next-session payload proof; no writer, receipt or actual observation."""
from copy import deepcopy
import hashlib
from pathlib import Path
from types import ModuleType
import unittest

from test_ndx_forward_gap_parent_capture_research_v3 import fixture

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'backtest/ndx_prospective_observation_receipt_research.py'
CORE_SHA = '6a088c05321b9e9a407765190800acb9443f8f5de6f1c11d456d86f3e0415684'


def arguments():
    data = fixture(['2026-10-08'], '2026-10-08T20:00:00+00:00')
    parent = data['parent']; history = parent['document']['history']
    raw = CORE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == CORE_SHA
    module = ModuleType('_synthetic_gap_payload'); module.__file__ = str(CORE)
    exec(compile(raw, str(CORE), 'exec'), module.__dict__)
    capture = dict(reference={'path': 'synthetic/capture', 'sha256': 'a'*64},
        started_at_utc=data['capture_started_at'], completed_at_utc=data['capture_completed_at'],
        sources={t: dict(bytes=data['source_bytes'][t], reference=data['source_references'][t]) for t in ('QQQ','SPY')},
        baseline_sources={t: dict(bytes=data['accounted_baseline_bytes'][t], reference=history['captured_source_references'][t]) for t in ('QQQ','SPY')},
        tzif=dict(bytes=data['tzif_bytes'], reference=data['tzif_reference']))
    return module, data, dict(parent_reference=parent['reference'], parent_readback_reference=parent['readback_reference'],
        known_typed_rows=deepcopy(history['known_typed_rows']), parent_attempt_inventory=deepcopy(history['parent_attempt_inventory']),
        capture=capture, session='2026-10-08', writer_started_at_utc='2026-10-08T20:01:00+00:00',
        writer_completed_at_utc='2026-10-08T20:01:01+00:00')


class GapParentPayloadTests(unittest.TestCase):
    def test_same_frozen_core_handles_gap_rows_without_new_month_opportunity(self):
        core, data, args = arguments(); before = deepcopy(args)
        payload = core.prepare_observation_payload(**args)
        self.assertEqual(args, before)
        self.assertEqual(payload['sequence'], 70)
        self.assertEqual(payload['session'], '2026-10-08')
        self.assertEqual(payload['first_actual_observed_session_of_month'], '2026-10-02')
        self.assertIs(payload['month_first_actual_observation'], False)
        self.assertEqual(payload['known_typed_rows_preserved'], args['known_typed_rows'])
        self.assertEqual(len(payload['parent_attempt_inventory_preserved']), 1)
        self.assertEqual(sum(row['kind']=='MISSED_OBSERVATION' for row in args['known_typed_rows']), 8)
        self.assertEqual(payload['timing_classification'], 'WITHIN_CONSERVATIVE_OBSERVATION_WINDOW')
        self.assertIs(payload['payload_is_not_a_published_observation_receipt'], True)
        self.assertTrue(all(payload[key] is False for key in core.FLAGS))

    def test_real_late_fact_does_not_change_month_first_or_grant_authority(self):
        core, _, args = arguments()
        args['writer_started_at_utc']='2026-10-09T14:00:00+00:00'
        args['writer_completed_at_utc']='2026-10-09T14:00:01+00:00'
        payload = core.prepare_observation_payload(**args)
        self.assertEqual(payload['timing_classification'], 'LATE_OBSERVATION')
        self.assertIs(payload['month_first_actual_observation'], False)
        self.assertIs(payload['candidate_seal_allowed'], False)
        self.assertIs(payload['cohort_registration_allowed'], False)

    def test_last_actual_baseline_cannot_impersonate_accounted_prefix(self):
        core, data, args = arguments()
        history = data['parent']['document']['history']
        args['capture']['baseline_sources']={t:dict(bytes=data['actual_baseline_bytes'][t], reference=history['baseline_references'][t]) for t in ('QQQ','SPY')}
        with self.assertRaisesRegex(ValueError, 'Baseline exact accounted prefix'):
            core.prepare_observation_payload(**args)

    def test_unresolved_attempt_and_retroactive_gap_rewrite_are_rejected(self):
        for mode in ('unresolved', 'past_gap'):
            core, _, args = arguments()
            if mode=='unresolved': args['parent_attempt_inventory'][0]['status']='PAYLOAD_ONLY'
            else: args['session']='2026-10-06'
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                core.prepare_observation_payload(**args)


if __name__ == '__main__':
    unittest.main()
