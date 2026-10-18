"""Independent-reader synthetic attacks; never executes the actual reader entrypoint."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backtest import ndx_prospective_gap_history_research_v3 as pure
from scripts import ndx_prospective_gap_history_independent_readback_20261009_v3 as reader
from test_ndx_prospective_gap_history_research_v3 import fixture


def checker():
    return reader.private_checker(reader.CAPTURE_READER.read_bytes())


def inspect(arguments, expected=None):
    result = reader.reconstruct_history(**arguments, checker=checker())
    if expected is not None:
        reader.exact(result, expected)
    return result


class IndependentGapReadbackTests(unittest.TestCase):
    def test_complete_history_reconstructed_without_pure_or_publisher_call(self):
        arguments = fixture()
        expected = pure.extend_gap_history(**arguments)
        before = deepcopy(arguments)
        with patch.object(pure, 'extend_gap_history', side_effect=AssertionError('New pure called')):
            actual = inspect(arguments, expected)
        self.assertEqual(arguments, before)
        self.assertEqual((actual['typed_row_count'], actual['new_missed_observation_count']), (69, 3))
        self.assertEqual(actual['first_actual_observed_session_by_month']['2026-10'], '2026-10-02')
        self.assertEqual(actual['last_observed_session'], '2026-10-02')
        self.assertTrue(all(actual[key] is False for key in reader.FALSE_FIELDS))

    def test_all_fields_exact_not_only_counts(self):
        arguments = fixture()
        expected = inspect(arguments)
        mutations = [
            lambda h: h['known_typed_rows'][0].update(seal_status='SEALED'),
            lambda h: h['known_typed_rows'][-1]['evidence_reference'].update(json_pointer='/wrong'),
            lambda h: h['parent_attempt_inventory'].clear(),
            lambda h: h['first_actual_observed_session_by_month'].update({'2026-10': '2026-10-05'}),
            lambda h: h.update(last_observed_session='2026-10-07'),
            lambda h: h.update(observation_created=0),
            lambda h: h.update(captured_sources_are_exact_accounted_prefix=True),
            lambda h: h['source_hashes'].clear(),
            lambda h: h['gap_classifications'][0].update(consumes_month_first_opportunity=True),
            lambda h: h.update(extra_authority=True),
        ]
        for index, mutate in enumerate(mutations):
            changed = deepcopy(expected)
            mutate(changed)
            with self.subTest(index=index), self.assertRaises(ValueError):
                reader.exact(changed, expected)

    def test_independent_deadline_boundary_pending_and_unfinished(self):
        cases = [
            fixture(['2026-10-05'], start='2026-10-06T13:29:59+00:00', end='2026-10-06T13:30:01+00:00'),
            fixture(['2026-10-05'], start='2026-10-06T13:30:00+00:00'),
            fixture(['2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08'], start='2026-10-08T21:00:00+00:00'),
            fixture(['2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08']),
        ]
        for arguments in cases:
            with self.subTest(clock=arguments['capture']['document']['capture_started_at']):
                inspect(arguments, pure.extend_gap_history(**arguments))
        self.assertEqual(inspect(cases[0])['new_missed_observation_count'], 0)
        self.assertEqual(inspect(cases[1])['new_missed_observation_count'], 1)
        self.assertEqual(inspect(cases[2])['pending_source_sessions'][0]['session'], '2026-10-08')
        self.assertEqual(inspect(cases[3])['excluded_not_completed_source_sessions'][0]['session'], '2026-10-08')

    def test_capture_plan_and_source_byte_lies_rejected(self):
        for mode in ('dates', 'cleared_diagnostics', 'source', 'baseline', 'tzif', 'clock'):
            arguments = fixture()
            plan = arguments['capture']['document']['plan']
            if mode == 'dates':
                for ticker in ('QQQ', 'SPY'):
                    plan['source_evidence'][ticker]['new_session_dates'].pop()
            elif mode == 'cleared_diagnostics':
                plan['diagnostics'] = []
            elif mode == 'source':
                arguments['source_bytes']['QQQ'] += b'changed'
            elif mode == 'baseline':
                arguments['baseline_bytes']['SPY'] += b'changed'
            elif mode == 'tzif':
                arguments['tzif_bytes'] += b'changed'
            else:
                arguments['capture']['document']['capture_completed_at'] = '2027-01-01T00:00:00+00:00'
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                inspect(arguments)

    def test_inventory_month_flags_and_audit_anchors_rejected(self):
        mutations = [
            lambda a: a['parent']['document']['parent_attempt_inventory'].clear(),
            lambda a: a['parent']['document']['known_typed_rows'][0].update(sequence=True),
            lambda a: a['parent']['publication'].update(future_independent_oos=True),
            lambda a: a['capture']['readback'].update(producer_called=True),
            lambda a: a['capture']['publication']['capture_reference'].update(sha256='f'*64),
            lambda a: a['capture']['readback']['source_hashes'].clear(),
            lambda a: a['capture']['readback']['counts'].update(parent_gap_count=True),
        ]
        for index, mutate in enumerate(mutations):
            arguments = fixture()
            mutate(arguments)
            with self.subTest(index=index), self.assertRaises((ValueError, KeyError)):
                inspect(arguments)

    def test_pending_pins_stop_before_io_or_output(self):
        with (patch.multiple(reader, PRODUCER_SHA=None, HISTORY_SHA=None, PUBLICATION_SHA=None),
              patch.object(Path, 'read_bytes', side_effect=AssertionError('IO before anchors')),
              patch.object(Path, 'mkdir', side_effect=AssertionError('Output before anchors'))):
            with self.assertRaisesRegex(ValueError, 'Pending immutable SHA'):
                reader.readback(execute=True)
        with self.assertRaises(ValueError):
            reader.readback(execute=False)

    def test_duplicate_nonfinite_json_and_conflicting_hashes_rejected(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}'):
            with self.assertRaises(ValueError):
                reader.decode(raw)
        with self.assertRaises(ValueError):
            reader.merge({'same': 'a'*64}, {'path': 'same', 'sha256': 'b'*64})

    def test_missing_parent_authority_field_is_rejected(self):
        for field in reader.PARENT_DOCUMENT_FALSE:
            arguments = fixture()
            arguments['parent']['document'].pop(field)
            with self.subTest(field=field), self.assertRaises((ValueError, KeyError)):
                inspect(arguments)

    def test_private_old_checker_ignores_sys_modules_substitute(self):
        fake = SimpleNamespace(inspect_plan=lambda **kwargs: (_ for _ in ()).throw(AssertionError('Substitute')))
        with patch.dict(sys.modules, {'scripts.ndx_variable_prefix_capture_independent_readback_20261003': fake}):
            result = inspect(fixture())
        self.assertEqual(result['new_missed_observation_count'], 3)
        with self.assertRaises(ValueError):
            reader.private_checker(b'# fake independent reader')

    def test_durable_save_compares_bytes_and_is_create_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'started.json'
            with patch.object(reader.shutil, 'disk_usage', return_value=SimpleNamespace(free=10*1024**3)):
                result = reader.save(path, {'schema': 'synthetic'})
                self.assertEqual(result['sha256'], reader.digest(path.read_bytes()))
                self.assertEqual(path.read_bytes(), reader.encode({'schema': 'synthetic'}))
                with self.assertRaises(FileExistsError):
                    reader.save(path, {'schema': 'replacement'})


if __name__ == '__main__':
    unittest.main()
