"""V5 saved-prefix capture plans with retained unconsumed sessions; no IO."""
from copy import deepcopy
from hashlib import sha256
import unittest

from backtest import ndx_accounted_source_prefix_research_v1 as prefix
from backtest import ndx_forward_parent_capture_research_v5 as module
from backtest import ndx_prospective_gap_history_research_v5 as gap
from test_ndx_forward_parent_capture_research_v4 import arguments as legacy_arguments
from test_ndx_prospective_gap_history_research_v5 import arguments as gap_arguments
from test_ndx_prospective_history_parent_view_research_v5 import wrap


def arguments(suffix=('2026-10-12',)):
    initial = gap_arguments(dates=('2026-10-09', *suffix))
    history = gap.extend_gap_history(**initial)
    parent = wrap(history)
    accounted = {}
    for ticker in ('QQQ', 'SPY'):
        accounted[ticker], _ = prefix.derive_accounted_prefix(
            source_bytes=initial['source_bytes'][ticker], source_reference=initial['source_references'][ticker],
            accounted_sessions=[row['session'] for row in history['known_typed_rows']],
            scope_start=history['known_typed_rows'][0]['session'])
    return dict(parent=parent, source_bytes=deepcopy(initial['source_bytes']),
                source_references={ticker: dict(path='v5-new-capture/' + ticker,
                    sha256=sha256(raw).hexdigest()) for ticker, raw in initial['source_bytes'].items()},
                accounted_baseline_bytes=accounted, actual_baseline_bytes=initial['actual_baseline_bytes'],
                capture_started_at='2026-10-12T20:03:00+00:00', capture_completed_at='2026-10-12T20:03:01+00:00',
                tzif_bytes=initial['tzif_bytes'], tzif_reference=initial['tzif_reference'])


def repin(args, ticker):
    args['source_references'][ticker]['sha256'] = sha256(args['source_bytes'][ticker]).hexdigest()


class ForwardCaptureV5Tests(unittest.TestCase):
    def test_v5_one_pending_session_is_candidate_with_true_parent_and_full_provenance(self):
        args = arguments(); before = deepcopy(args)
        result = module.plan_parent_capture(**args)
        self.assertEqual(args, before)
        self.assertEqual(result['status'], 'ONE_NEW_SESSION_CAPTURE_CANDIDATE')
        self.assertEqual(result['candidate_session'], '2026-10-12')
        self.assertEqual(result['actual_parent_schema'], 'PROSPECTIVE_GAP_EXTENSION_HISTORY_V5')
        self.assertEqual(len(result['known_typed_rows']), 71)
        self.assertEqual(len(result['observations']), 2)
        self.assertEqual(result['first_actual_observed_session_by_month']['2026-10'], '2026-10-02')
        self.assertEqual(result['parent_pending_source_sessions'][0]['session'], '2026-10-12')
        self.assertEqual(result['accounted_baseline_references'], args['parent']['document']['history']['accounted_prefix_references'])
        self.assertNotEqual(result['accounted_baseline_references'], result['baseline_references'])
        self.assertTrue(all(result[key] is False for key in module.FLAGS))

    def test_legacy_v4_no_new_and_unique_candidate_remain_supported(self):
        for dates, expected in (((), 'NO_NEW_SESSION'), (('2026-10-09',), 'ONE_NEW_SESSION_CAPTURE_CANDIDATE')):
            result = module.plan_parent_capture(**legacy_arguments(dates))
            self.assertEqual(result['status'], expected)
            self.assertEqual(result['actual_parent_schema'], 'PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V4')
            self.assertEqual(result['parent_pending_source_sessions'], [])
            self.assertEqual(result['dependency_sha256']['parent_view'], module.PARENT_VIEW_SHA256)
            self.assertEqual(result['dependency_sha256']['legacy_view'], module.LEGACY_VIEW_SHA256)

    def test_prior_pending_and_unfinished_dates_cannot_be_deleted_or_redated(self):
        for suffix, deleted in ((('2026-10-12',), '2026-10-12'),
                                (('2026-10-12', '2026-10-13'), '2026-10-13')):
            args = arguments(suffix)
            for ticker in ('QQQ', 'SPY'):
                args['source_bytes'][ticker] = args['source_bytes'][ticker].replace(
                    (deleted + ',10,12,8,10,100\n').encode(), b'')
                repin(args, ticker)
            result = module.plan_parent_capture(**args)
            self.assertEqual(result['status'], 'BLOCKED_SOURCE_DIAGNOSTICS')
            self.assertIsNone(result['candidate_session'])
            self.assertIn('PREVIOUSLY_CAPTURED_SOURCE_SESSIONS_WITHDRAWN_OR_CHANGED', [row['reason'] for row in result['diagnostics']])

    def test_provisional_price_update_is_allowed_but_accounted_revision_is_blocked(self):
        args = arguments()
        for ticker in ('QQQ', 'SPY'):
            args['source_bytes'][ticker] = args['source_bytes'][ticker].replace(
                b'2026-10-12,10,12,8,10,100', b'2026-10-12,10,12,8,11,100')
            repin(args, ticker)
        self.assertEqual(module.plan_parent_capture(**args)['candidate_session'], '2026-10-12')
        args['source_bytes']['QQQ'] = args['source_bytes']['QQQ'].replace(b',10,12,8,10,100', b',10,12,8,11,100', 1)
        repin(args, 'QQQ')
        self.assertIn('ACCOUNTED_BASELINE_PREFIX_REVISED', [row['reason'] for row in module.plan_parent_capture(**args)['diagnostics']])

    def test_clock_rollback_rejects_and_multiple_sessions_cannot_be_single_candidate(self):
        args = arguments(); args['capture_started_at'] = '2026-10-12T20:02:00+00:00'
        with self.assertRaisesRegex(ValueError, 'previously recorded unconsumed'):
            module.plan_parent_capture(**args)
        result = module.plan_parent_capture(**arguments(('2026-10-12', '2026-10-13')))
        self.assertEqual(result['status'], 'BLOCKED_SOURCE_DIAGNOSTICS')
        self.assertIn('MULTIPLE_UNACCOUNTED_SESSIONS', [row['reason'] for row in result['diagnostics']])
        self.assertIsNone(result['candidate_session'])


if __name__ == '__main__':
    unittest.main()
