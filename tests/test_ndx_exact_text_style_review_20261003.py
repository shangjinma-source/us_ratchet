"""Independent style attacks; no workbook authoring or actual research input."""
import copy
import io
import unittest
import zipfile
from unittest.mock import patch

from backtest import ndx_dated_exact_text_style_inspection_research as core
from test_ndx_dated_exact_text_style_20261003 import fixture


def rewrite(raw, changes, added=None):
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as source, zipfile.ZipFile(output, 'w') as target:
        for name in source.namelist():
            value = source.read(name)
            target.writestr(name, changes.get(name, lambda b: b)(value))
        for name, value in (added or {}).items():
            target.writestr(name, value)
    return output.getvalue()


class IndependentStyles(unittest.TestCase):
    def test_shared_and_inline_exact_text_and_underlying_type(self):
        value = '000123'
        raw, presentation = fixture(value)
        before = copy.deepcopy(presentation)
        ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        for typ, content, added in [
            ('inlineStr', '<is><t>000123</t></is>', {}),
            ('s', '<v>0</v>', {'xl/sharedStrings.xml': f'<sst xmlns="{ns}"><si><t>000123</t></si></sst>'}),
        ]:
            transformed = rewrite(raw, {'xl/worksheets/sheet1.xml': lambda b: b.replace(b't="str"><v>000123</v>', f't="{typ}">{content}'.encode())}, added)
            result = core.inspect_text_styles(transformed, presentation)
            self.assertEqual(result['exact_literal_cell_count'], 1)
            self.assertIs(result['visual_acceptance_passed'], False)
        malformed = rewrite(raw, {'xl/worksheets/sheet1.xml': lambda b: b.replace(b't="str"', b't="n"')})
        with self.assertRaises(ValueError): core.inspect_text_styles(malformed, presentation)
        self.assertEqual(presentation, before)

    def test_literal_never_masks_numeric_missing_or_extra_cell(self):
        raw, original = fixture('001')
        for value in (None, 0, -2, 0.5, False):
            presentation = copy.deepcopy(original)
            presentation['display']['tables'][0]['rows'][0][0] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                core.inspect_text_styles(raw, presentation)
        raw = rewrite(raw, {'xl/worksheets/sheet1.xml': lambda b: b.replace(b'</row>', b'<c r="B5" t="str"><v>001</v></c></row>')})
        with self.assertRaises(ValueError): core.inspect_text_styles(raw, original)

    def test_conditional_override_and_utf16_doctype_rejected(self):
        raw, presentation = fixture()
        masked = rewrite(raw, {
            'xl/styles.xml': lambda b: b.replace(b'</styleSheet>', b'<dxfs count="1"><dxf><numFmt numFmtId="165" formatCode="&quot;WRONG&quot;"/></dxf></dxfs></styleSheet>'),
            'xl/worksheets/sheet1.xml': lambda b: b.replace(b'</worksheet>', b'<conditionalFormatting sqref="A5"><cfRule type="expression" dxfId="0" priority="1"><formula>1</formula></cfRule></conditionalFormatting></worksheet>'),
        })
        with self.assertRaises(ValueError): core.inspect_text_styles(masked, presentation)
        encoded = rewrite(raw, {'xl/worksheets/sheet1.xml': lambda b: ('<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE worksheet [<!ENTITY x "unused">]>' + b.decode()).encode('utf-16')})
        with self.assertRaises(ValueError): core.inspect_text_styles(encoded, presentation)

    def test_resource_limits_and_missing_target(self):
        raw, presentation = fixture()
        with patch.object(core, 'MAX_UNPACKED', len(raw)//100), self.assertRaises(ValueError):
            core.inspect_text_styles(raw, presentation)
        absent = rewrite(raw, {'xl/worksheets/sheet1.xml': lambda b: b.replace(b'<c r="A5" t="str"><v>6222659648236112670</v></c>', b'')})
        with self.assertRaises(ValueError): core.inspect_text_styles(absent, presentation)


if __name__ == '__main__': unittest.main()
