import copy,io,unittest,zipfile
from xml.sax.saxutils import escape
from backtest.ndx_dated_exact_text_style_inspection_research import inspect_text_styles,expected_format

def fixture(value='6222659648236112670',fmt=None,actual=None):
    fmt=expected_format(value) if fmt is None else fmt;actual=value if actual is None else actual
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main';rel='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    p={'display':{'tables':[{'name':'Sheet'+str(i),'rows':[[value]] if i==1 else []} for i in range(1,7)]}}
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        z.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets>'+''.join(f'<sheet name="Sheet{i}" r:id="r{i}"/>' for i in range(1,7))+'</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships>'+''.join(f'<Relationship Id="r{i}" Target="worksheets/sheet{i}.xml"/>' for i in range(1,7))+'</Relationships>')
        z.writestr('xl/styles.xml',f'<styleSheet xmlns="{ns}"><numFmts><numFmt numFmtId="164" formatCode="{escape(fmt,{chr(34): "&quot;"})}"/></numFmts><cellXfs><xf numFmtId="164"/></cellXfs></styleSheet>')
        for i in range(1,7):z.writestr(f'xl/worksheets/sheet{i}.xml',f'<worksheet xmlns="{ns}"><sheetData>'+ (f'<row r="5"><c r="A5" t="str"><v>{escape(actual)}</v></c></row>' if i==1 else '')+'</sheetData></worksheet>')
    return out.getvalue(),p

class TestStyles(unittest.TestCase):
    def test_exact_and_original_unchanged(self):
        for v in ('6222659648236112670','6222659648236111038','0'*63+'1','0'*63+'a'):
            raw,p=fixture(v);before=copy.deepcopy(p);self.assertEqual(inspect_text_styles(raw,p)['exact_literal_cell_count'],1);self.assertEqual(p,before)
    def test_mutations_rejected(self):
        v='0'*63+'1'
        for fmt in ('"'+v[:-1]+'2"','"1"','"'+v+'";@','[Red]"'+v+'"','[>0]"'+v+'"','@'):
            with self.subTest(fmt=fmt),self.assertRaises(ValueError):inspect_text_styles(*fixture(v,fmt))
        with self.assertRaises(ValueError):inspect_text_styles(*fixture(v,actual='1'))
        with self.assertRaises(ValueError):inspect_text_styles(*fixture('ordinary','"ordinary"'))
    def test_bounds_and_nontext(self):
        self.assertIsNone(expected_format(100));self.assertEqual(expected_format('path/file'),'@')
        with self.assertRaises(ValueError):expected_format('1'*65)
        from unittest.mock import patch
        raw,p=fixture()
        with patch('backtest.ndx_dated_exact_text_style_inspection_research.MAX_BYTES',1),self.assertRaises(ValueError):inspect_text_styles(raw,p)
        with patch('backtest.ndx_dated_exact_text_style_inspection_research.MAX_STYLES',0),self.assertRaises(ValueError):inspect_text_styles(raw,p)
