"""A value-pass workbook must still pass the separately pinned style inspector."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ndx_dated_comparison_workbook_independent_readback_20261003 as subject
from test_ndx_dated_comparison_workbook_independent_readback_20261003 import setup


class StyleGateReview(unittest.TestCase):
    def test_style_rejection_is_durable_even_after_value_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            references, export, *_ = setup(root)
            style = Path(references['style_core']['path'])
            raw = b"def inspect_text_styles(x,p):raise ValueError('Display differs from underlying text')"
            style.write_bytes(raw)
            references['style_core']['sha256'] = subject.digest(raw)
            output = root / 'out'
            with patch.object(subject, 'RUNTIME_INSPECTION_SIZE', Path(references['runtime_inspection']['path']).stat().st_size), patch.object(subject, 'BOUND', references), patch.object(subject, 'EXPORT', export), patch.object(subject, 'OUTPUT', output):
                with self.assertRaisesRegex(ValueError, 'Display differs'):
                    subject.readback(execute=True)
                failure = json.loads((output / 'failure.json').read_bytes())
                self.assertFalse(failure['retry_allowed'])
                self.assertFalse((output / 'independent_readback.json').exists())
                with self.assertRaisesRegex(ValueError, 'No overwrite or retry'):
                    subject.readback(execute=True)

    def test_style_result_and_source_are_bound_in_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            references, export, *_ = setup(root)
            with patch.object(subject, 'RUNTIME_INSPECTION_SIZE', Path(references['runtime_inspection']['path']).stat().st_size), patch.object(subject, 'BOUND', references), patch.object(subject, 'EXPORT', export), patch.object(subject, 'OUTPUT', root / 'out'):
                result = subject.readback(execute=True)
            report = json.loads(Path(result['path']).read_bytes())
            self.assertEqual(report['text_style_inspection']['status'], 'PASS')
            self.assertEqual(report['source_hashes'][references['style_core']['path']], references['style_core']['sha256'])
            self.assertFalse(report['visual_acceptance_passed'])


if __name__ == '__main__':
    unittest.main()
