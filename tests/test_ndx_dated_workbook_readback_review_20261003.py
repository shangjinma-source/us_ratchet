"""Independent mocked-export wrapper checks; no actual workbook consumption."""
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_dated_comparison_workbook_independent_readback_20261003 as reader
from test_ndx_dated_comparison_workbook_independent_readback_20261003 import setup


class Review(unittest.TestCase):
    def test_preview_bytes_and_unknown_export_residue_block_before_output(self):
        for mode in ('preview', 'residue'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                refs, export, *_ = setup(root)
                if mode == 'preview':
                    (export / 'preview_5.png').write_bytes(b'changed')
                else:
                    (export / 'failure.json').write_text('{}')
                with patch.object(reader, 'RUNTIME_INSPECTION_SIZE', Path(refs['runtime_inspection']['path']).stat().st_size), patch.object(reader, 'BOUND', refs), patch.object(reader, 'EXPORT', export), patch.object(reader, 'OUTPUT', root / 'out'):
                    with self.assertRaises(ValueError):
                        reader.readback(execute=True)
                    self.assertFalse((root / 'out').exists())

    def test_full_inherited_source_union_and_preview_order_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            refs, export, manifest, presentation, publication = setup(Path(tmp))
            presentation['input_references']['summary'] = {'path': 'synthetic-summary', 'sha256': 'a' * 64}
            presentation['source_hashes']['synthetic-summary'] = 'a' * 64
            publication['source_hashes'] = deepcopy(presentation['source_hashes'])
            with patch.object(reader, 'EXPORT', export):
                with self.assertRaises(ValueError):
                    reader.validate(manifest, presentation, publication, refs)
                manifest['source_hashes']['synthetic-summary'] = 'a' * 64
                reader.validate(manifest, presentation, publication, refs)
                manifest['previews'][-1]['sheet'] = manifest['previews'][0]['sheet']
                with self.assertRaises(ValueError):
                    reader.validate(manifest, presentation, publication, refs)

    def test_source_change_after_report_keeps_failed_attempt_and_disallows_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            refs, export, *_ = setup(root)
            original_save = reader.save
            def save_then_drift(path, value):
                result = original_save(path, value)
                if path.name == 'independent_readback.json':
                    (export / 'preview_0.png').write_bytes(b'postwrite drift')
                return result
            with patch.object(reader, 'RUNTIME_INSPECTION_SIZE', Path(refs['runtime_inspection']['path']).stat().st_size), patch.object(reader, 'BOUND', refs), patch.object(reader, 'EXPORT', export), patch.object(reader, 'OUTPUT', root / 'out'), patch.object(reader, 'save', save_then_drift):
                with self.assertRaises(ValueError):
                    reader.readback(execute=True)
                self.assertTrue((root / 'out' / 'independent_readback.json').exists())
                failure = json.loads((root / 'out' / 'failure.json').read_bytes())
                self.assertEqual(failure['status'], 'FAILED_DO_NOT_CONSUME')
                with self.assertRaises(ValueError):
                    reader.readback(execute=True)


if __name__ == '__main__':
    unittest.main()
