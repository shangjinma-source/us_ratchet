"""Real-format synthetic V2/capture envelopes only; no actual capture or publishing."""
from copy import deepcopy
import unittest

from backtest import ndx_prospective_gap_history_research_v3 as module
from backtest import ndx_variable_prefix_capture_research as capture_core
import test_ndx_variable_prefix_capture_research as upstream


def reference(name):
    return upstream.reference(name, name.encode())


def fixture(dates=None, start='2026-10-08T16:00:00+00:00', end=None):
    arguments = upstream.fixture()
    days = [row['session'] for row in arguments['parent']['document']['known_typed_rows']]
    for ticker in ('QQQ', 'SPY'):
        arguments['source_bytes'][ticker] = upstream.csv(
            days + (dates if dates is not None else ['2026-10-05', '2026-10-06', '2026-10-07']), True)
        upstream.resign(arguments, ticker)
    arguments['capture_started_at'] = start
    arguments['capture_completed_at'] = end or start
    return envelope(arguments)


def envelope(arguments):
    plan = capture_core.plan_history_capture(**arguments)
    parent = arguments['parent']
    _, days, _, claims = capture_core.inspect_parent(parent)
    inputs = {role: dict(path='code/' + role, sha256=digest)
              for role, digest in module.DEPENDENCY_SHA256.items()}
    inputs['tzif'] = reference('input-tzif')
    inputs['tzif']['sha256'] = arguments['tzif_reference']['sha256']
    artifacts = dict(arguments['source_references'], tzif=arguments['tzif_reference'])
    for item in (*inputs.values(), *artifacts.values()):
        capture_core.merge(claims, item)
    parent_refs = {role: deepcopy(parent[role]) for role in
                   ('reference', 'publication_reference', 'readback_reference', 'reader_reference')}
    document = dict(
        schema='SOURCE_BOUND_VARIABLE_PREFIX_CAPTURE_V1', plan=plan,
        source_hashes=deepcopy(claims), parent_references=parent_refs,
        input_references=inputs, captured_artifacts=artifacts,
        capture_started_at=arguments['capture_started_at'],
        capture_completed_at=arguments['capture_completed_at'],
        clock_captured_by_runner=True, external_clock_attestation_verified=False,
        **capture_core.FLAGS)
    refs = {role: reference('capture/' + role) for role in
            ('reference', 'publication_reference', 'readback_reference', 'reader_reference')}
    publication = dict(schema='VARIABLE_PREFIX_CAPTURE_PUBLICATION_V1',
        status='PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION', capture_reference=refs['reference'],
        source_hashes=deepcopy(claims), **capture_core.FLAGS)
    audit = dict(schema='VARIABLE_PREFIX_CAPTURE_INDEPENDENT_READBACK_V1', status='PASS',
        capture_reference=refs['reference'], publication_reference=refs['publication_reference'],
        parent_references=deepcopy(parent_refs), reader_sha256=refs['reader_reference']['sha256'],
        producer_called=False, plan_history_capture_called=False, snapshot_bytes_verified=True,
        external_clock_attestation_verified=False,
        source_hashes={**claims, **{item['path']: item['sha256'] for item in refs.values()}},
        counts=dict(status=plan['status'], parent_typed_row_count=len(days),
            parent_observed_count=len(days)-5, parent_gap_count=5,
            candidate_session=plan['candidate_session'], diagnostic_count=len(plan['diagnostics']),
            snapshot_counts={ticker: plan['source_evidence'][ticker]['original_row_count']
                             for ticker in ('QQQ', 'SPY')}), **capture_core.FLAGS)
    return dict(parent=parent, capture=dict(document=document, publication=publication,
        readback=audit, **refs), source_bytes=arguments['source_bytes'],
        baseline_bytes=arguments['baseline_bytes'], tzif_bytes=arguments['tzif_bytes'])


class GapHistoryTests(unittest.TestCase):
    def test_three_expired_sessions_preserve_actual_month_and_entire_prefix(self):
        arguments = fixture()
        before = deepcopy(arguments)
        result = module.extend_gap_history(**arguments)
        parent = arguments['parent']['document']
        self.assertEqual(arguments, before)
        self.assertEqual(result['schema'], module.SCHEMA)
        self.assertEqual((result['parent_typed_row_count'], result['typed_row_count']), (66, 69))
        self.assertEqual(result['known_typed_rows'][:66], parent['known_typed_rows'])
        for key in ('observations', 'parent_attempt_inventory', 'baseline_references',
                    'first_actual_observed_session_by_month', 'genesis_preserved'):
            self.assertEqual(result[key], parent[key])
        self.assertEqual(result['first_actual_observed_session_by_month']['2026-10'], '2026-10-02')
        self.assertEqual(result['last_observed_session'], '2026-10-02')
        self.assertEqual(result['last_accounted_session'], '2026-10-07')
        self.assertEqual((result['observation_count'], result['new_observation_count'],
                          result['new_missed_observation_count']), (1, 0, 3))
        self.assertEqual(sum(row['kind'] == 'MISSED_OBSERVATION' for row in result['known_typed_rows']), 8)
        self.assertTrue(all(result[key] is False for key in module.FLAGS))
        self.assertFalse(result['old_v2_capture_writer_reader_compatible'])
        for gap, row in zip(result['gap_classifications'], result['known_typed_rows'][66:]):
            self.assertEqual(row['seal_status'], 'NOT_ATTEMPTED')
            self.assertFalse(gap['consumes_month_first_opportunity'])
            for ticker, pointer in gap['source_session_pointer_by_ticker'].items():
                value = arguments['capture']['document']
                for key in pointer.strip('/').split('/'):
                    value = value[int(key)] if isinstance(value, list) else value[key]
                self.assertEqual(value, gap['session'])
                self.assertIn(ticker, ('QQQ', 'SPY'))

    def test_latest_timely_remains_pending_and_source_snapshot_is_not_accounted_baseline(self):
        arguments = fixture(['2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08'],
                            start='2026-10-08T21:00:00+00:00')
        result = module.extend_gap_history(**arguments)
        self.assertEqual(result['last_accounted_session'], '2026-10-07')
        self.assertEqual([row['session'] for row in result['pending_source_sessions']], ['2026-10-08'])
        self.assertEqual(result['baseline_references'], arguments['parent']['document']['baseline_references'])
        self.assertFalse(result['captured_sources_are_exact_accounted_prefix'])

    def test_deadline_exact_boundary_and_crossing_interval(self):
        before = module.extend_gap_history(**fixture(['2026-10-05'],
            start='2026-10-06T13:29:59+00:00', end='2026-10-06T13:30:01+00:00'))
        self.assertEqual(before['new_missed_observation_count'], 0)
        self.assertEqual(len(before['pending_source_sessions']), 1)
        exact_boundary = module.extend_gap_history(**fixture(['2026-10-05'],
            start='2026-10-06T13:30:00+00:00'))
        self.assertEqual(exact_boundary['new_missed_observation_count'], 1)

    def test_not_completed_source_rows_are_excluded_never_future_gaps(self):
        result = module.extend_gap_history(**fixture(['2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08'],
            start='2026-10-08T16:00:00+00:00'))
        self.assertEqual(result['new_missed_observation_count'], 3)
        self.assertEqual(result['pending_source_sessions'], [])
        self.assertEqual(result['excluded_not_completed_source_sessions'][0]['session'], '2026-10-08')

    def test_resigned_capture_plan_cannot_invent_dates_or_clear_diagnostics(self):
        for mode in ('dates', 'diagnostic', 'clock'):
            arguments = fixture()
            plan = arguments['capture']['document']['plan']
            if mode == 'dates':
                for ticker in ('QQQ', 'SPY'):
                    plan['source_evidence'][ticker]['new_session_dates'].append('2026-10-08')
            elif mode == 'diagnostic':
                plan['diagnostics'] = []
            else:
                plan['capture_completed_at'] = '2027-01-01T00:00:00+00:00'
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                module.extend_gap_history(**arguments)

    def test_prefix_revision_asymmetry_backfill_missing_and_duplicate_fail_closed(self):
        for mode in ('revision', 'asymmetry', 'missing', 'duplicate', 'backfill'):
            arguments = upstream.fixture()
            days = [row['session'] for row in arguments['parent']['document']['known_typed_rows']]
            if mode == 'revision':
                arguments['source_bytes']['QQQ'] = arguments['source_bytes']['QQQ'].replace(
                    b',10,12,8,10,100', b',10,12,8,11,100', 1)
            elif mode == 'asymmetry':
                arguments['source_bytes']['SPY'] = upstream.csv(days + ['2026-10-06'], True)
            elif mode == 'missing':
                arguments['source_bytes']['QQQ'] = upstream.csv(days[1:] + ['2026-10-05'], True)
            elif mode == 'duplicate':
                arguments['source_bytes']['QQQ'] += b'2026-10-05,10,12,8,10,100\n'
            else:
                arguments['source_bytes']['QQQ'] = upstream.csv(days + ['2026-10-01'], True)
            upstream.resign(arguments, 'QQQ')
            upstream.resign(arguments, 'SPY')
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                module.extend_gap_history(**envelope(arguments))

    def test_capture_audit_bindings_dependency_hash_and_boolean_counts_rejected(self):
        mutations = [
            lambda a: a['capture']['readback'].update(status='FAIL'),
            lambda a: a['capture']['readback'].update(producer_called=True),
            lambda a: a['capture']['readback']['counts'].update(parent_gap_count=True),
            lambda a: a['capture']['publication'].update(capture_reference=reference('wrong')),
            lambda a: a['capture']['document']['input_references']['core'].update(sha256='f'*64),
            lambda a: a['capture']['readback']['source_hashes'].pop(
                a['capture']['document']['captured_artifacts']['QQQ']['path']),
            lambda a: a['parent']['document']['known_typed_rows'][0].update(sequence=True),
            lambda a: a['parent']['document']['first_actual_observed_session_by_month'].update(
                {'2026-10': '2026-10-05'}),
            lambda a: a['parent']['document']['parent_attempt_inventory'][0].update(status='FAILED'),
        ]
        for index, mutate in enumerate(mutations):
            arguments = fixture()
            mutate(arguments)
            with self.subTest(index=index), self.assertRaises(ValueError):
                module.extend_gap_history(**arguments)

    def test_tzif_source_hash_timezone_and_clock_reversal_rejected(self):
        for mode in ('tzif', 'source', 'clock', 'offset'):
            arguments = fixture()
            if mode == 'tzif':
                arguments['tzif_bytes'] += b'changed'
            elif mode == 'source':
                arguments['source_bytes']['QQQ'] += b'changed'
            elif mode == 'clock':
                arguments['capture']['document']['capture_completed_at'] = '2026-10-07T00:00:00+00:00'
            else:
                arguments['capture']['document']['capture_started_at'] = '2026-10-08T16:00:00+08:00'
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                module.extend_gap_history(**arguments)

    def test_parent_extended_authority_flags_are_strict_false(self):
        for field in module.PARENT_AUTHORITY_FLAGS:
            arguments = fixture()
            arguments['parent']['document'][field] = True
            with self.subTest(field=field), self.assertRaises(ValueError):
                module.extend_gap_history(**arguments)
        for role in ('publication', 'readback'):
            for field in module.PARENT_AUTHORITY_FLAGS:
                arguments = fixture()
                arguments['parent'][role][field] = True
                with self.subTest(role=role, field=field), self.assertRaises(ValueError):
                    module.extend_gap_history(**arguments)


if __name__ == '__main__':
    unittest.main()
