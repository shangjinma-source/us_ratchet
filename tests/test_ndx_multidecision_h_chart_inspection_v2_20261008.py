"""Forensic chart XML fixtures, never a formal workbook export."""
from pathlib import Path
import re
import tempfile
import unittest
import zipfile
from scripts import ndx_multidecision_h_chart_inspection_v2_20261008 as checker


def fixture(path, attack=None):
    s, c, a, r = (checker.NS[k] for k in ('s', 'c', 'a', 'r'))
    expected = [dict(sheet_name='图', title='原路径', series=[dict(name='控制',
                    categories_formula="'数据'!$A$5:$A$6", values_formula="'数据'!$B$5:$B$6",
                    categories=['2026-01-01', '2026-01-02'], values=[1.0, 1.25])])]
    def rel(target): return f'<Relationships><Relationship Id="r1" Target="{target}"/></Relationships>'
    members = {
        'xl/workbook.xml': f'<workbook xmlns="{s}" xmlns:r="{r}"><sheets><sheet name="图" r:id="r1"/><sheet name="数据" r:id="r2"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels': '<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/><Relationship Id="r2" Target="worksheets/sheet2.xml"/></Relationships>',
        'xl/worksheets/sheet1.xml': f'<worksheet xmlns="{s}" xmlns:r="{r}"><sheetData/><drawing r:id="r1"/></worksheet>',
        'xl/worksheets/_rels/sheet1.xml.rels': rel('../drawings/drawing1.xml'),
        'xl/drawings/drawing1.xml': f'<drawing xmlns:c="{c}" xmlns:r="{r}"><c:chart r:id="r1"/></drawing>',
        'xl/drawings/_rels/drawing1.xml.rels': rel('../charts/chart1.xml'),
        'xl/worksheets/sheet2.xml': f'<worksheet xmlns="{s}"><sheetData><row><c r="A5" t="inlineStr"><is><t>2026-01-01</t></is></c><c r="B5"><v>1</v></c></row><row><c r="A6" t="inlineStr"><is><t>2026-01-02</t></is></c><c r="B6"><v>1.25</v></c></row></sheetData></worksheet>',
        'xl/charts/chart1.xml': f'''<c:chartSpace xmlns:c="{c}" xmlns:a="{a}"><c:chart><c:title><c:tx><c:rich><a:p><a:r><a:t>原路径</a:t></a:r></a:p></c:rich></c:tx></c:title><c:plotArea><c:lineChart><c:ser><c:tx><c:v>控制</c:v></c:tx><c:cat><c:strRef><c:f>'数据'!$A$5:$A$6</c:f><c:strCache><c:ptCount val="2"/><c:pt idx="0"><c:v>2026-01-01</c:v></c:pt><c:pt idx="1"><c:v>2026-01-02</c:v></c:pt></c:strCache></c:strRef></c:cat><c:val><c:numRef><c:f>'数据'!$B$5:$B$6</c:f><c:numCache><c:ptCount val="2"/><c:pt idx="0"><c:v>1</c:v></c:pt><c:pt idx="1"><c:v>1.25</c:v></c:pt></c:numCache></c:numRef></c:val></c:ser></c:lineChart></c:plotArea></c:chart></c:chartSpace>''',
    }
    key = 'xl/charts/chart1.xml'
    if attack == 'range': members[key] = members[key].replace('$B$6', '$B$5')
    elif attack == 'cache': members[key] = members[key].replace('<c:v>1.25</c:v>', '<c:v>0</c:v>')
    elif attack == 'cell': members['xl/worksheets/sheet2.xml'] = members['xl/worksheets/sheet2.xml'].replace('<v>1.25</v>', '<v>0</v>')
    elif attack == 'name': members[key] = members[key].replace('<c:v>控制</c:v>', '<c:v>候选</c:v>')
    elif attack == 'orphan': members['xl/charts/hidden.xml'] = members[key]
    elif attack == 'order': members[key] = members[key].replace('idx="1"', 'idx="0"')
    elif attack == 'formula': members['xl/worksheets/sheet2.xml'] = members['xl/worksheets/sheet2.xml'].replace('<v>1.25</v>', '<f>1.25</f><v>1.25</v>')
    elif attack in ('sdk_empty_cache', 'sdk_empty_cache_bad_cell'):
        chart = re.sub(r'<c:pt idx="[01]">.*?</c:pt>', '', members.pop(key))
        chart = chart.replace('<c:ptCount val="2"/>', '<c:ptCount val="0"/>')
        members['xl/drawings/charts/chart1.xml'] = chart
        members['xl/drawings/_rels/drawing1.xml.rels'] = rel('charts/chart1.xml')
        if attack == 'sdk_empty_cache_bad_cell':
            members['xl/worksheets/sheet2.xml'] = members['xl/worksheets/sheet2.xml'].replace('<v>1.25</v>', '<v>0</v>')
    with zipfile.ZipFile(path, 'w') as archive:
        for name, content in members.items(): archive.writestr(name, content.encode())
    return expected


class Tests(unittest.TestCase):
    def test_linked_original_cells_and_all_cache_points(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.zip'
            result = checker.inspect_chart_parts(path, fixture(path))
            self.assertEqual(result['chart_count'], 1)
            self.assertEqual(result['checked_axis_points'], 4)

    def test_chart_cannot_substitute_zero_or_wrong_identity_or_range(self):
        for attack in ('range', 'cache', 'cell', 'name', 'orphan', 'order', 'formula'):
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'fixture.zip'
                expected = fixture(path, attack)
                with self.assertRaises(ValueError): checker.inspect_chart_parts(path, expected)

    def test_sdk_empty_cache_resolves_all_original_cells(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.zip'
            expected = fixture(path, 'sdk_empty_cache')
            self.assertEqual(checker.inspect_chart_parts(path, expected)['checked_axis_points'], 4)
            expected = fixture(path, 'sdk_empty_cache_bad_cell')
            with self.assertRaises(ValueError): checker.inspect_chart_parts(path, expected)


if __name__ == '__main__': unittest.main()
