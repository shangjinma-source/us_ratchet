from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch
from scripts import ndx_current101_price_archive_audit_20260919 as m
from test_ndx_current101_price_independent_audit_20260919 import fixture


class Tests(TestCase):
    def test_actual_plan_archive_partition_without_price_audit(self):
        plan = m.pure.loads(m.pure.PLAN.read_bytes())
        self.assertEqual(m.pure.digest(m.pure.PLAN.read_bytes()), m.pure.PLAN_SHA)
        contract = m.archive.load_contract()
        m.validate_historical_plan_gaps(plan, contract)
        value = m.partition(plan['historical_expected_source_hashes'], contract)
        self.assertEqual(len(value['archive_resolutions']), 85)
        self.assertEqual(len(value['historical_gap_observations']), 26)
        root_paths = set(contract['rows'])
        self.assertFalse(root_paths & set(value['live_verified_source_hashes']))
        forged = deepcopy(plan)
        forged['historical_price_cache_gap_observations'][0]['historical_bytes_verified'] = True
        with self.assertRaises(ValueError): m.validate_historical_plan_gaps(forged, contract)
        forged = deepcopy(plan)
        forged['historical_price_cache_gap_observations'][0]['observed_current_sha256'] = '0' * 64
        with self.assertRaises(ValueError): m.validate_historical_plan_gaps(forged, contract)

    def test_pure_decimal_reused_without_old_build_or_guard(self):
        body, task, rows = fixture()
        with patch.object(m.pure, 'build', side_effect=AssertionError('Never old strict build')):
            raw = m.pure.inspect_raw(m.json.dumps(body).encode(), 'TEST')
            result = m.pure.audit_rows(rawinfo=raw, task=task, rows=rows)
        self.assertEqual(result['maximum_absolute_decimal_error'], '0')
        with self.assertRaisesRegex(ValueError, 'Hard final'):
            m.build(index_path=m.pure.INDEX, index_sha256='0' * 64)

    def test_report_cannot_upgrade_archive_or_omit_loaded_code(self):
        report = dict(schema=m.SCHEMA, historical_expected_source_hashes=dict(m.LOADED), archive_resolution={})
        flags = ('original_live_root_paths_verified', 'original_strict_reader_passed',
                 'original_26_observations_asserted_live_unchanged', 'historical_full_source_closure_verified',
                 'price_identity_verified', 'point_in_time_verified', 'promotion_allowed')
        report.update(dict.fromkeys(flags, False))
        for flag in flags:
            forged = deepcopy(report); forged[flag] = True
            with self.subTest(flag=flag), self.assertRaisesRegex(ValueError, 'disclosure'): m.verify(forged)
        report['historical_expected_source_hashes'].pop(str(m.SOURCE))
        with self.assertRaisesRegex(ValueError, 'omitted'): m.verify(report)

    def test_atomic_publish_failure_leaves_no_final(self):
        with TemporaryDirectory() as folder:
            target = Path(folder) / 'report.json'
            with patch.object(m, 'verify'), patch.object(m.os, 'link', side_effect=OSError('injected')):
                with self.assertRaises(OSError): m.publish(target, {'x': 1})
            self.assertEqual(list(Path(folder).iterdir()), [])


if __name__ == '__main__': main()
