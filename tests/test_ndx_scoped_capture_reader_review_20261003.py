"""Independent scoped-capture counterexamples using synthetic CSV and TZif."""
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import ndx_forward_source_capture_scoped_independent_readback_20261003 as reader
from backtest import ndx_forward_source_capture_scoped_research as fixture_producer
from test_ndx_forward_source_capture_scoped_research import args
from test_ndx_forward_source_capture_research import fixture


def inspect(inputs, plan):
    return reader.inspect_plan(plan, inputs['frontier'], inputs['source_csv_bytes'],
        inputs['baseline_csv_bytes'], inputs['tzif_bytes'], inputs['capture_started_at_utc'], inputs['observed_at_utc'])


class Review(unittest.TestCase):
    def test_65_parent_rows_keep_gap_observation_types_and_baseline_links(self):
        days = []
        day = date(2026, 7, 1)
        while day <= date(2026, 10, 1):
            if day.weekday() < 5 and day.isoformat() not in ('2026-07-03', '2026-09-07'):
                days.append(day.isoformat())
            day += timedelta(days=1)
        self.assertEqual(len(days), 65)
        rows = []
        for index, day in enumerate(days):
            if index < 60:
                rows.append(dict(session=day, kind='SEALED_PARENT_OBSERVED_SESSION', parent_session_index=index, eligibility_reverified=False))
            else:
                rows.append(dict(session=day, kind='MISSED_OBSERVATION', gap_event_index=index-60,
                    gap_event_sha256=format(index, '064x'), counts_as_observed_session=False, decision_eligible=False))
        refs = {key: dict(path=key, sha256='b'*64) for key in ('frontier', 'baseline_QQQ', 'baseline_SPY')}
        flags = dict.fromkeys(('candidate_seal_allowed', 'cohort_registration_allowed', 'canonical_calendar_append_allowed', 'point_in_time_verified', 'promotion_allowed', 'oos_recovery_completed'), False)
        parent = dict(schema='OBSERVATION_GAP_FRONTIER_RESEARCH_V1', source_hashes={},
            last_observed_session=days[59], last_accounted_session=days[-1], last_accounted_gap_session=days[-1],
            unaccounted_source_dates=[], input_references={ticker: refs['baseline_'+ticker] for ticker in ('QQQ', 'SPY')},
            known_accounted_rows=rows, parent_observed_session_count=60, accounted_gap_count=5, **flags)
        receipt = dict(schema='OBSERVATION_GAP_FRONTIER_PUBLICATION_V1', status='PUBLISHED_ACCOUNTED_FRONTIER_ONLY_NO_ELIGIBILITY',
            source_hashes={}, frontier_reference=refs['frontier'], **flags)
        reader.validate_saved_frontier(parent, receipt, refs)
        for mutate in (
            lambda p: p['known_accounted_rows'][60].update(counts_as_observed_session=True),
            lambda p: p['known_accounted_rows'][0].update(parent_session_index=False),
            lambda p: p['known_accounted_rows'][64].update(kind='SEALED_PARENT_OBSERVED_SESSION'),
            lambda p: p['input_references'].update(SPY=dict(path='wrong baseline', sha256='b'*64)),
            lambda p: p.update(last_observed_session=days[-1]),
        ):
            bad = deepcopy(parent); mutate(bad)
            with self.assertRaises(ValueError):
                reader.validate_saved_frontier(bad, receipt, refs)

    def test_all_outer_authority_flags_are_checked(self):
        inputs = args()
        plan = fixture_producer.plan_scoped_forward_source_capture(**inputs)
        flags = [key for key, value in plan.items() if value is False]
        for key in flags:
            for replacement in (True, 0):
                changed = deepcopy(plan); changed[key] = replacement
                with self.subTest(key=key, replacement=replacement), self.assertRaises(ValueError):
                    inspect(inputs, changed)

    def test_scope_raw_bytes_and_indexes_not_repaired_or_hash_relabelled(self):
        inputs = args()
        plan = fixture_producer.plan_scoped_forward_source_capture(**inputs)
        result = inspect(inputs, plan)
        for role in ('source', 'baseline'):
            for ticker in ('QQQ', 'SPY'):
                self.assertEqual(len(result['details'][role][ticker]['out_of_scope_ohlc_diagnostics']), 1)
                for mutate in (
                    lambda e: e['original_rows'][0].update(original_data_row_index=True),
                    lambda e: e.update(excluded_before_scope_ohlc_diagnostics=[]),
                    lambda e: e.update(scoped_sha256=e['original_sha256']),
                    lambda e: e['original_rows'][0]['raw_csv_row'].update(Open='207'),
                ):
                    altered = deepcopy(plan)
                    mutate(altered['csv_scope_evidence'][role][ticker])
                    with self.assertRaises(ValueError):
                        inspect(inputs, altered)
        broken = deepcopy(inputs)
        broken['source_csv_bytes']['SPY'] = broken['source_csv_bytes']['SPY'].replace(b'2026-09-24,10,12,8,10,100\n', b'')
        _, evidence = fixture_producer.scoped_csv(broken['source_csv_bytes']['SPY'], plan['scope_start'])
        with self.assertRaises(ValueError):
            reader.check_csv(broken['source_csv_bytes']['SPY'], evidence, plan['scope_start'], ['2026-09-24'])

    def test_dst_asymmetric_suffix_and_cross_close_use_whole_interval(self):
        inputs = fixture('2026-03-05', ('2026-03-06',), '2026-03-06T21:00:00+00:00', '2026-03-09T13:30:00+00:00')
        plan = fixture_producer.plan_scoped_forward_source_capture(**inputs)
        result = inspect(inputs, plan)
        self.assertIsNone(result['candidate'])
        self.assertEqual(plan['capture_plan']['classifications'][0]['classification'], 'MISSED_SEAL_DEADLINE')
        inputs = args()
        inputs['source_csv_bytes']['QQQ'] += b'2026-09-28,10,12,8,10,100\n'
        plan = fixture_producer.plan_scoped_forward_source_capture(**inputs)
        self.assertEqual(inspect(inputs, plan)['status_observed'], 'SOURCE_SUFFIX_ASYMMETRY_REQUIRES_REVIEW')
        self.assertIsNone(inspect(inputs, plan)['candidate'])
        altered = deepcopy(plan); altered['capture_plan']['unmatched_new_source_dates_by_ticker']['QQQ'] = []
        with self.assertRaises(ValueError):
            inspect(inputs, altered)
        inputs = fixture(start='2026-09-25T19:59:59+00:00', end='2026-09-25T20:01:00+00:00')
        plan = fixture_producer.plan_scoped_forward_source_capture(**inputs)
        self.assertIsNone(inspect(inputs, plan)['candidate'])
        self.assertEqual(plan['capture_plan']['excluded_unfinished_source_dates'], ['2026-09-25'])

    def test_no_live_io_or_producer_calls_and_pending_blocks_read(self):
        inputs = args(); inputs['source_csv_bytes'] = deepcopy(inputs['baseline_csv_bytes'])
        plan = fixture_producer.plan_scoped_forward_source_capture(**inputs)
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('No files or live cache')), \
                patch.object(fixture_producer, 'plan_scoped_forward_source_capture', side_effect=AssertionError('No producer')):
            self.assertEqual(inspect(inputs, plan)['status_observed'], 'NO_NEW_SOURCE_SESSION')
            with patch.object(reader, 'CAPTURE_SHA', None):
                with self.assertRaises(ValueError):
                    reader.readback(execute=True)


if __name__ == '__main__':
    unittest.main()
