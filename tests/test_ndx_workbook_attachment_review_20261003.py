"""Independent temporary attachment boundary checks, not an actual XLSX audit."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ndx_dated_comparison_workbook_independent_readback_20261003 as reader
from test_ndx_dated_comparison_workbook_independent_readback_20261003 import setup


class AttachmentReview(unittest.TestCase):
    def test_streamed_only_and_manifest_not_rewritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            refs, export, *_ = setup(root)
            attachment = Path(refs['runtime_inspection']['path'])
            original_read = Path.read_bytes
            saved_manifest = original_read(Path(refs['manifest']['path']))
            def bounded_read(path):
                self.assertNotEqual(path, attachment, 'Runtime attachment must use bounded streaming')
                return original_read(path)
            with patch.object(reader, 'BOUND', refs), patch.object(reader, 'EXPORT', export), patch.object(reader, 'OUTPUT', root/'audit'), patch.object(reader, 'RUNTIME_INSPECTION_SIZE', 10), patch.object(Path, 'read_bytes', bounded_read):
                result = reader.readback(execute=True)
                report = json.loads(original_read(Path(result['path'])))
                self.assertEqual(original_read(Path(refs['manifest']['path'])), saved_manifest)
                self.assertEqual(report['runtime_inspection_attachment']['reference'], refs['runtime_inspection'])
                self.assertIs(report['final_delivery_accepted'], False)

    def test_extra_file_after_report_is_failure_not_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            refs, export, *_ = setup(root)
            original_save = reader.save
            def mutate(path, value):
                result = original_save(path, value)
                if path.name == 'independent_readback.json':
                    (export/'additional.inspect.ndjson').write_bytes(b'not authorized')
                return result
            with patch.object(reader, 'BOUND', refs), patch.object(reader, 'EXPORT', export), patch.object(reader, 'OUTPUT', root/'audit'), patch.object(reader, 'RUNTIME_INSPECTION_SIZE', 10), patch.object(reader, 'save', side_effect=mutate):
                with self.assertRaises(ValueError): reader.readback(execute=True)
                self.assertTrue((root/'audit'/'failure.json').exists())
                with self.assertRaisesRegex(ValueError, 'overwrite|retry'): reader.readback(execute=True)


if __name__ == '__main__': unittest.main()
