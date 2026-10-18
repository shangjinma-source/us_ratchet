import copy
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from test_ndx_dated_readable_workbook_independent_readback_20261003 import m, presentation, setup, xlsx


def rewrite(raw, transforms):
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as src, zipfile.ZipFile(output, 'w') as dst:
        for name in src.namelist():
            b = src.read(name)
            dst.writestr(name, transforms.get(name, lambda b: b)(b))
    return output.getvalue()


class ReadableReview(unittest.TestCase):
    def test_disabled_alignment_cannot_claim_effective_no_wrap(self):
        p = presentation()
        raw = rewrite(xlsx(p), {'xl/styles.xml': lambda b: b.replace(
            b'<xf numFmtId="49"><alignment wrapText="0"/>',
            b'<xf numFmtId="49" xfId="0" applyAlignment="0"><alignment wrapText="0"/>'
        ).replace(b'</styleSheet>', b'<cellStyleXfs><xf><alignment wrapText="1"/></xf></cellStyleXfs></styleSheet>')})
        with self.assertRaises(ValueError): m.inspect_readable_layout(raw, p, m.expected_layout(p))

    def test_hidden_overlapping_or_shrunk_layout_rejected(self):
        p = presentation()
        changes = [
            {'xl/worksheets/s4.xml': lambda b: b.replace(b'<row r="5"', b'<row hidden="1" r="5"')},
            {'xl/worksheets/s4.xml': lambda b: b.replace(b'</cols>', b'<col min="4" max="4" width="48"/></cols>')},
            {'xl/styles.xml': lambda b: b.replace(b'<alignment wrapText="1"', b'<alignment shrinkToFit="1" wrapText="1"')},
            {'xl/worksheets/s5.xml': lambda b: b.replace(b'customHeight="1"', b'customHeight="0"')},
        ]
        for i, change in enumerate(changes):
            with self.subTest(i=i), self.assertRaises(ValueError):
                m.inspect_readable_layout(rewrite(xlsx(p), change), p, m.expected_layout(p))

    def test_closed_roles_and_false_type_not_author_claims(self):
        with tempfile.TemporaryDirectory() as folder:
            refs, export, manifest, p, pub = setup(Path(folder))
            changes = [lambda d: d['source_hashes'].pop(refs['exporter']['path']),
                       lambda d: d['input_references'].pop('layout'),
                       lambda d: d.update(visual_acceptance_passed=0),
                       lambda d: d['layout_adjustments'].update(values_changed=0)]
            with patch.object(m, 'EXPORT', export):
                for change in changes:
                    bad = copy.deepcopy(manifest); change(bad)
                    with self.assertRaises(ValueError): m.validate(bad, p, pub, refs)
                bad = copy.deepcopy(manifest['runtime_diagnostic_attachment']); bad['numeric_input'] = 0
                with self.assertRaises(ValueError): m.authenticate_runtime_attachment(bad)

    def test_final_extra_file_keeps_failed_readback_and_cannot_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            refs, export, *_ = setup(root)
            original_save = m.save
            def altered(path, value):
                result = original_save(path, value)
                if path.name == 'independent_readback.json': (export/'extra').write_bytes(b'new')
                return result
            with patch.object(m, 'BOUND', refs), patch.object(m, 'EXPORT', export), patch.object(m, 'OUTPUT', root/'audit'), patch.object(m, 'save', altered):
                with self.assertRaises(ValueError): m.readback(execute=True)
                failure = json.loads((root/'audit'/'failure.json').read_bytes())
                self.assertIs(failure['retry_allowed'], False)
                with self.assertRaisesRegex(ValueError, 'overwrite|retry'): m.readback(execute=True)


if __name__ == '__main__': unittest.main()
