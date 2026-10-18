"""Synthetic mixed expired/pending transition; no actual IO or OOS."""
import base64
from copy import deepcopy
from hashlib import sha256
import unittest

from backtest import ndx_accounted_source_prefix_research_v1 as prefix_core
from backtest import ndx_prospective_gap_history_research_v5 as module
from backtest import ndx_prospective_history_parent_view_research_v5 as parent_view
from backtest import ndx_prospective_observation_parent_history_research_v4 as legacy
from test_ndx_prospective_observation_parent_history_research_v4 import fixture, wrap


def reference(path, raw=None):
    return dict(path=path, sha256=sha256(raw if raw is not None else path.encode()).hexdigest())


def arguments(dates=('2026-10-09', '2026-10-12'),
              start='2026-10-12T20:02:00+00:00', end='2026-10-12T20:02:01+00:00',
              expired=('2026-10-09',)):
    seed = fixture()
    parent = wrap(legacy.append_observation_history_v4(**seed))
    view = parent_view.inspect_parent_history_v5(parent)
    baseline = {ticker: base64.b64decode(seed['observation']['payload']
                ['full_original_sources_preserved'][ticker]['sources']['original_csv_bytes_base64'])
                for ticker in ('QQQ', 'SPY')}
    source = {ticker: raw + b''.join((day + ',10,12,8,10,100\n').encode() for day in dates)
              for ticker, raw in baseline.items()}
    source_refs = {ticker: reference('immutable/full/' + ticker, raw) for ticker, raw in source.items()}
    prefix_refs, evidence_refs = {}, {}
    for ticker, raw in source.items():
        prefix, evidence = prefix_core.derive_accounted_prefix(
            source_bytes=raw, source_reference=source_refs[ticker],
            accounted_sessions=[row['session'] for row in view['known_typed_rows']] + list(expired),
            scope_start=view['known_typed_rows'][0]['session'])
        prefix_refs[ticker] = reference('immutable/prefix/' + ticker, prefix)
        evidence_refs[ticker] = reference('immutable/prefix-evidence/' + ticker,
                                          module.prefix_evidence_bytes(evidence))
    return dict(parent=parent, capture_references={role: reference('capture-v5/' + start + '/' + role) for role in module.ROLES},
                source_bytes=source, source_references=source_refs,
                accounted_baseline_bytes=deepcopy(baseline), actual_baseline_bytes=deepcopy(baseline),
                prefix_references=prefix_refs, prefix_evidence_references=evidence_refs,
                capture_started_at=start, capture_completed_at=end,
                tzif_bytes=base64.b64decode(seed['observation']['payload']['tzif_bytes_base64']),
                tzif_reference=seed['observation']['payload']['tzif_reference'])


class GapHistoryV5Tests(unittest.TestCase):
    def test_missed_prefix_and_pending_tail_preserve_actual_month_and_two_sources(self):
        args = arguments(); before = deepcopy(args)
        result = module.extend_gap_history(**args)
        self.assertEqual(args, before)
        self.assertEqual((result['typed_row_count'], result['observation_count'], result['gap_count']), (71, 2, 9))
        self.assertEqual(result['new_observation_count'], 0)
        self.assertEqual([row['session'] for row in result['gap_classifications']], ['2026-10-09'])
        self.assertEqual([row['session'] for row in result['pending_source_sessions']], ['2026-10-12'])
        self.assertEqual(result['excluded_not_completed_source_sessions'], [])
        self.assertEqual(result['first_actual_observed_session_by_month']['2026-10'], '2026-10-02')
        self.assertEqual(result['observations'], args['parent']['document']['history']['observations'])
        self.assertEqual(result['baseline_references'], args['parent']['document']['history']['baseline_references'])
        self.assertNotEqual(result['full_capture_source_references'], result['accounted_prefix_references'])
        self.assertEqual(result['accounted_prefix_evidence']['QQQ']['suffix_sessions'], ['2026-10-12'])
        self.assertTrue(all(result[key] is False for key in module.FLAGS))
        self.assertNotIn('timing_classification_recomputed_from_tzif', result)

    def test_all_expired_is_full_raw_prefix_without_observation(self):
        result = module.extend_gap_history(**arguments(
            start='2026-10-13T13:30:00+00:00', end='2026-10-13T13:30:01+00:00',
            expired=('2026-10-09', '2026-10-12')))
        self.assertEqual((result['typed_row_count'], result['new_missed_observation_count']), (72, 2))
        self.assertEqual(result['pending_source_sessions'], [])
        for ticker, evidence in result['accounted_prefix_evidence'].items():
            self.assertEqual(evidence['prefix_byte_count'], evidence['full_source_byte_count'])
            self.assertEqual(evidence['prefix_sha256'], result['full_capture_source_references'][ticker]['sha256'])

    def test_interval_crosses_deadline_does_not_upgrade_pending_to_missed(self):
        result = module.extend_gap_history(**arguments(
            dates=('2026-10-09',), start='2026-10-12T13:29:59+00:00',
            end='2026-10-12T13:30:01+00:00', expired=()))
        self.assertEqual(result['typed_row_count'], 70)
        self.assertEqual(result['status'], 'NO_EXPIRED_SESSION_TO_APPEND')
        self.assertEqual([row['session'] for row in result['pending_source_sessions']], ['2026-10-09'])
        self.assertEqual(result['gap_classifications'], [])

    def test_expired_prefix_plus_unfinished_source_tail_is_not_observed(self):
        result = module.extend_gap_history(**arguments(
            start='2026-10-12T19:59:59+00:00', end='2026-10-12T20:00:01+00:00'))
        self.assertEqual([row['session'] for row in result['gap_classifications']], ['2026-10-09'])
        self.assertEqual(result['pending_source_sessions'], [])
        self.assertEqual([row['session'] for row in result['excluded_not_completed_source_sessions']], ['2026-10-12'])
        self.assertFalse(result['excluded_not_completed_source_sessions'][0]['counts_as_observed_session'])

    def test_revisions_asymmetry_bad_saved_prefix_and_clock_reversal_reject(self):
        cases = []
        changed = arguments(); changed['source_bytes']['QQQ'] = changed['source_bytes']['QQQ'].replace(b',10,12,8,10,100', b',10,12,8,11,100', 1)
        changed['source_references']['QQQ'] = reference('immutable/full/QQQ', changed['source_bytes']['QQQ']); cases.append(changed)
        changed = arguments(); changed['source_bytes']['SPY'] += b'2026-10-13,10,12,8,10,100\n'
        changed['source_references']['SPY'] = reference('immutable/full/SPY', changed['source_bytes']['SPY']); cases.append(changed)
        changed = arguments(); changed['prefix_references']['QQQ']['sha256'] = '0' * 64; cases.append(changed)
        changed = arguments(); changed['capture_references'] = {role: reference('capture/' + role) for role in module.ROLES}; cases.append(changed)
        changed = arguments(); changed['capture_completed_at'] = '2026-10-12T19:00:00+00:00'; cases.append(changed)
        for args in cases:
            with self.subTest(args=args['capture_completed_at']), self.assertRaises(ValueError):
                module.extend_gap_history(**args)

    def test_previously_pending_date_cannot_disappear_from_later_capture(self):
        from test_ndx_prospective_history_parent_view_research_v5 import wrap as wrap_gap
        args = arguments()
        history = module.extend_gap_history(**args)
        next_args = deepcopy(args)
        next_args['parent'] = wrap_gap(history, 'pending-parent')
        next_args['capture_started_at'] = '2026-10-12T20:03:00+00:00'
        next_args['capture_completed_at'] = '2026-10-12T20:03:01+00:00'
        for ticker in ('QQQ', 'SPY'):
            full = args['source_bytes'][ticker]
            prefix, _ = prefix_core.derive_accounted_prefix(
                source_bytes=full, source_reference=args['source_references'][ticker],
                accounted_sessions=[row['session'] for row in history['known_typed_rows']],
                scope_start=history['known_typed_rows'][0]['session'])
            next_args['accounted_baseline_bytes'][ticker] = prefix
            revised = full.replace(b'2026-10-12,', b'2026-10-13,')
            next_args['source_bytes'][ticker] = revised
            next_args['source_references'][ticker] = reference('immutable/second-full/' + ticker, revised)
        with self.assertRaisesRegex(ValueError, 'Previously captured pending'):
            module.extend_gap_history(**next_args)


if __name__ == '__main__':
    unittest.main()
