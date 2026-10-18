"""NAV snapshot regressions with read-only historical stock report reuse."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_dynamic_frozen_comparison_v2 as comparison


class ComparisonSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.csv = self.root / 'mutable.csv'
        self.manifest = self.root / 'mutable.manifest.json'
        source = comparison.ROOT / 'data/cache/funds/012922.csv'
        self.csv.write_bytes(source.read_bytes())
        self.manifest.write_bytes(source.with_name(source.name + '.manifest.json').read_bytes())
        self.arguments = dict(csv_path=self.csv, manifest_path=self.manifest,
            expected_csv_sha256=hashlib.sha256(self.csv.read_bytes()).hexdigest(),
            expected_manifest_sha256=hashlib.sha256(self.manifest.read_bytes()).hexdigest(),
            output_directory=self.root / 'snapshots')

    def capture(self):
        path, digest = comparison.snapshot_nav(**self.arguments)
        return dict(snapshot_path=path, snapshot_sha256=digest)

    def test_historical_rows_identical_and_stock_paths_not_replayed(self):
        result = comparison.compare_snapshot(**self.capture())
        self.assertEqual(result['session_count'], 294)
        self.assertTrue(result['historical_nav_rows_exact_match'])
        self.assertEqual([row['role'] for row in result['rows'][:3]],
                         ['RETURN', 'USER_PREFERENCE', 'INCUMBENT'])
        self.assertEqual(result['rows'][1]['target_cardinalities'], [4])
        self.assertEqual(result['review_status'], 'DRAFT_PENDING_ROOT_REVIEW')
        self.assertEqual(result['nav_report']['schema'], 'ndx_dynamic_nav_research_v2')
        for name, digest in comparison.nav_module._SOURCES.items():
            self.assertEqual(result['source_hashes'][name], digest)
        for key in ('stock_execution_rerun', 'training_rerun', 'point_in_time_verified',
                    'publication_time_verified', 'promotion_allowed', 'historical_nav_source_closure_restored'):
            self.assertIs(result[key], False)

    def test_snapshot_survives_mutable_cache_refresh(self):
        arguments = self.capture()
        before = comparison.compare_snapshot(**arguments)
        self.csv.write_text('Date,Close\n2026-09-12,999\n')
        self.manifest.write_text('{}')
        after = comparison.compare_snapshot(**arguments)
        self.assertEqual(before['rows'], after['rows'])
        self.assertNotIn(str(self.csv), after['source_hashes'])
        self.assertNotIn(str(self.manifest), after['source_hashes'])
        self.assertNotIn(str(comparison.ROOT / 'data/cache/funds/012922.csv'), after['source_hashes'])

    def test_snapshot_content_tampering_rejected(self):
        arguments = self.capture()
        (arguments['snapshot_path'].parent / '012922.csv').write_text('Date,Close\n2023-03-31,99\n')
        with self.assertRaisesRegex(ValueError, 'NAV CSV identity differs'):
            comparison.compare_snapshot(**arguments)

    def test_manifest_content_binding_rejected(self):
        wrong = deepcopy(self.arguments)
        value = json.loads(self.manifest.read_bytes())
        value['content_sha256'] = '0' * 64
        self.manifest.write_text(json.dumps(value))
        wrong['expected_manifest_sha256'] = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, 'sidecar binding differs'):
            comparison.snapshot_nav(**wrong)
        self.assertFalse((self.root / 'snapshots').exists())

    def test_rehashed_snapshot_namespace_tampering_rejected(self):
        arguments = self.capture()
        path = arguments['snapshot_path']
        capture = json.loads(path.read_bytes())
        capture['csv_path'] = str(self.csv)
        path.write_text(json.dumps(capture))
        arguments['snapshot_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, 'namespace differs'):
            comparison.compare_snapshot(**arguments)

    def test_old_nav_noncache_source_remains_required(self):
        arguments = self.capture()
        name, _ = comparison.historical.REPORTS['012922']
        old = json.loads((comparison.historical.DIRECTORY / name).read_bytes())
        extra = self.root / 'historical_extra_evidence.json'
        extra.write_text('original')
        old['source_hashes'][str(extra)] = hashlib.sha256(extra.read_bytes()).hexdigest()
        report = self.root / 'old_nav_fixture.json'
        report.write_text(json.dumps(old))
        digest = hashlib.sha256(report.read_bytes()).hexdigest()
        extra.write_text('changed')
        with patch.dict(comparison.historical.REPORTS, {'012922': (str(report), digest)}):
            with self.assertRaisesRegex(ValueError, 'Comparison source drift'):
                comparison.compare_snapshot(**arguments)

    def test_identical_snapshot_resume_and_create_only_draft(self):
        arguments = self.capture()
        self.assertEqual(arguments, self.capture())
        report = comparison.compare_snapshot(**arguments)
        path = self.root / 'draft.json'
        digest = comparison.save_draft(report, path)
        self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
        with self.assertRaises(FileExistsError):
            comparison.save_draft(report, path)


if __name__ == '__main__':
    unittest.main()
