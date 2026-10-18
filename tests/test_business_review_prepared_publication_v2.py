"""Saved-runner execution and isolated guards; never mutate sealed originals."""
from pathlib import Path
import builtins
from copy import deepcopy
import hashlib
import runpy
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'tmp/business_review_prepared_publication_20261009_v2'
SAVED_RUNNER = OUTPUT / 'runner.py'


class PublicationCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.functions = runpy.run_path(str(SAVED_RUNNER), run_name='readonly_runner_helpers')

    def test_actual_original_and_saved_runners_reject_existing_output_before_business_io(self):
        original_import = builtins.__import__
        for source in (ROOT / 'tmp/run_business_review_prepared_publication_20261009_v2.py', SAVED_RUNNER):
            business_imports, source_reads = [], []
            def checked_import(name, *args, **kwargs):
                if name == 'backtest' or name.startswith('backtest.'):
                    business_imports.append(name)
                    raise AssertionError('Adapter import before early refusal')
                return original_import(name, *args, **kwargs)
            def checked_read(path):
                source_reads.append(str(path))
                raise AssertionError('Business read before early refusal')
            with self.subTest(source=str(source)), patch.object(builtins, '__import__', side_effect=checked_import), patch.object(Path, 'read_bytes', checked_read):
                with self.assertRaisesRegex(ValueError, 'Existing v2 output'):
                    runpy.run_path(str(source), run_name='__main__')
            self.assertEqual(business_imports, [])
            self.assertEqual(source_reads, [])

    def test_isolated_fixed_bytes_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'fixed.json'
            path.write_bytes(b'{"pending":true}')
            bindings = {path: hashlib.sha256(path.read_bytes()).hexdigest()}
            self.functions['guard'](bindings, {})
            path.write_bytes(b'{"pending":false}')
            with self.assertRaisesRegex(ValueError, 'Fixed bytes changed'):
                self.functions['guard'](bindings, {})

    def test_isolated_fixed_namespace_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            path = folder / 'fixed.json'
            path.write_bytes(b'{}')
            bindings = {path: hashlib.sha256(path.read_bytes()).hexdigest()}
            self.functions['guard'](bindings, {folder: ['fixed.json']})
            (folder / 'failure.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'Fixed namespace changed'):
                self.functions['guard'](bindings, {folder: ['fixed.json']})

    def test_copied_json_csv_exact_and_full_pending_semantics(self):
        earlier = ROOT / 'tmp/business_review_prepared_publication_20261009_v1'
        for name in ('reviewpack.json', 'reviews.csv'):
            self.assertEqual((OUTPUT / name).read_bytes(), (earlier / name).read_bytes())
        raw = (OUTPUT / 'reviewpack.json').read_bytes()
        csv_raw = (OUTPUT / 'reviews.csv').read_bytes()
        template = (ROOT / 'data/ndx_taxonomy_review.py').read_bytes()
        pack = self.functions['check_pack_csv'](raw, csv_raw, template)
        self.assertIsNone(pack['rows'][0]['template']['risk_chain'])
        for change in ('false_to_zero', 'csv_risk', 'fer_identity'):
            bad = deepcopy(pack)
            bad_csv = csv_raw
            if change == 'false_to_zero':
                bad['rows'][0]['accepted'] = 0
            elif change == 'csv_risk':
                bad_csv = csv_raw.replace(b',pending_review,', b',accepted,', 1)
            else:
                bad['rows'][-1]['original_identity_candidates'].pop()
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.functions['check_pack_csv'](self.functions['encoded'](bad), bad_csv, template)


if __name__ == '__main__':
    unittest.main()
