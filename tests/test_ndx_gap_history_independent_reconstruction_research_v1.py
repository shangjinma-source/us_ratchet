"""Independent gap arithmetic fixtures; no actual capture, observation or IO."""
import ast
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import unittest

from backtest import ndx_gap_history_independent_reconstruction_research_v1 as module
from backtest import ndx_prospective_gap_history_research_v5 as producer
from backtest import ndx_prospective_history_parent_view_research_v5 as parent_checker
from backtest import ndx_capture_source_csv_independent_reconstruction_research_v1 as csv_checker
from backtest import ndx_accounted_source_prefix_independent_reconstruction_research_v1 as prefix_checker
from test_ndx_prospective_gap_history_research_v5 import arguments, reference


def reconstruct(args):
    return module.reconstruct_gap_history(**args, parent_checker=parent_checker,
        csv_rows=csv_checker.csv_rows, prefix_checker=prefix_checker)


class IndependentGapHistoryTests(unittest.TestCase):
    def test_zero_pending_unfinished_mixed_and_all_expired_whole_results(self):
        cases = [arguments(), arguments(dates=(), expired=()),
            arguments(dates=('2026-10-09',), start='2026-10-09T20:02:00+00:00',
                      end='2026-10-09T20:02:01+00:00', expired=()),
            arguments(dates=('2026-10-09',), start='2026-10-09T19:59:00+00:00',
                      end='2026-10-09T20:00:01+00:00', expired=()),
            arguments(dates=('2026-10-09','2026-10-12','2026-10-13')),
            arguments(start='2026-10-13T13:30:00+00:00', end='2026-10-13T13:30:01+00:00',
                      expired=('2026-10-09','2026-10-12'))]
        for args in cases:
            before = deepcopy(args)
            with self.subTest(start=args['capture_started_at']):
                result = reconstruct(args)
                self.assertEqual(result, producer.extend_gap_history(**args))
                self.assertEqual(args, before)
                self.assertEqual(result['new_observation_count'], 0)
                self.assertEqual(result['first_actual_observed_session_by_month']['2026-10'], '2026-10-02')

    def test_crossing_deadline_is_pending_and_dst_uses_supplied_tzif(self):
        args = arguments(dates=('2026-10-09',), start='2026-10-12T13:29:59+00:00',
                         end='2026-10-12T13:30:01+00:00', expired=())
        result = reconstruct(args)
        self.assertEqual(result, producer.extend_gap_history(**args))
        self.assertEqual(result['new_missed_observation_count'], 0)
        self.assertEqual(result['pending_source_sessions'][0]['session'], '2026-10-09')
        args = arguments(dates=('2026-10-09','2026-10-12','2026-11-02'),
                         start='2026-11-02T21:01:00+00:00', end='2026-11-02T21:01:01+00:00',
                         expired=('2026-10-09','2026-10-12'))
        result = reconstruct(args)
        self.assertEqual(result, producer.extend_gap_history(**args))
        self.assertEqual(result['pending_source_sessions'][0]['conservative_close_utc'], '2026-11-02T21:00:00+00:00')

    def test_no_producer_gap_prefix_scoped_calls_or_io(self):
        from backtest import ndx_accounted_source_prefix_research_v1 as producer_prefix
        from backtest import ndx_forward_source_capture_scoped_research as producer_csv
        args = arguments(); expected = producer.extend_gap_history(**args)
        with patch.object(producer, 'extend_gap_history', side_effect=AssertionError('Gap producer')), \
                patch.object(producer_prefix, 'derive_accounted_prefix', side_effect=AssertionError('Prefix producer')), \
                patch.object(producer_csv, 'scoped_csv', side_effect=AssertionError('Scoped producer')), \
                patch.object(Path, 'read_bytes', side_effect=AssertionError('IO')):
            self.assertEqual(reconstruct(args), expected)
        tree = ast.parse(Path(module.__file__).read_bytes())
        self.assertFalse(any(isinstance(node, ast.ImportFrom) and (node.module or '').startswith(('backtest', 'scripts'))
                             for node in ast.walk(tree)))

    def test_source_hash_revision_asymmetry_clock_and_evidence_sha_reject(self):
        cases = []
        args = arguments(); args['source_bytes']['QQQ'] += b'\n'; cases.append(args)
        args = arguments(); args['source_bytes']['QQQ'] = args['source_bytes']['QQQ'].replace(b',10,12,8,10,100', b',10,12,8,11,100', 1)
        args['source_references']['QQQ'] = reference('changed/source', args['source_bytes']['QQQ']); cases.append(args)
        args = arguments(); args['source_bytes']['SPY'] += b'2026-10-13,10,12,8,10,100\n'
        args['source_references']['SPY'] = reference('asymmetric/source', args['source_bytes']['SPY']); cases.append(args)
        args = arguments(); args['capture_completed_at'] = '2026-10-12T20:01:00+00:00'; cases.append(args)
        args = arguments(); args['prefix_evidence_references']['QQQ']['sha256'] = '0' * 64; cases.append(args)
        args = arguments(); args['prefix_references']['QQQ']['sha256'] = '0' * 64; cases.append(args)
        args = arguments(); args['tzif_bytes'] += b'\n'; cases.append(args)
        args = arguments(); del args['capture_references']['reader_reference']; cases.append(args)
        for index, args in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(ValueError):
                reconstruct(args)

    def test_typed_pointer_duplicates_strict_sequences_and_summary_types(self):
        args = arguments(); history = reconstruct(args)
        rows = deepcopy(history['known_typed_rows'])
        rows[-1]['evidence_reference'] = deepcopy(rows[0]['evidence_reference'])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            module.validate_typed_rows(rows, {})
        rows = deepcopy(history['known_typed_rows']); rows[0]['sequence'] = True
        with self.assertRaises(ValueError): module.validate_typed_rows(rows, {})
        evidence = dict(excluded_before_scope_rows=[{'raw': '01'}], excluded_before_scope_ohlc_diagnostics=[], flag=False)
        result = module.summary(evidence)
        self.assertEqual(result['excluded_before_scope_rows_sha256'], module.sha256(module.encode([{'raw': '01'}])).hexdigest())
        self.assertEqual(evidence['excluded_before_scope_rows'], [{'raw': '01'}])
        self.assertEqual(result['excluded_before_scope_ohlc_diagnostics_count'], 0)


if __name__ == '__main__':
    unittest.main()
