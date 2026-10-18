from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from backtest import ndx_multidecision_h_workbook_display_v2_research as producer
from backtest import ndx_multidecision_h_workbook_display_inspection_v2_research as checker
from scripts import ndx_multidecision_h_chart_inspection_v2_20261008 as charts
from test_ndx_multidecision_h_workbook_display_v2_research import fixture
from test_ndx_multidecision_h_chart_inspection_v2_20261008 import fixture as chart_fixture


class Review(unittest.TestCase):
    def test_source_mapping_does_not_call_producer_and_preserves_last_cells(self):
        args=fixture();display=producer.build_display(**args)
        with patch.object(producer,'build_display',side_effect=AssertionError('producer forbidden')):
            self.assertEqual(checker.inspect_display(display=display,**args)['original_curve_series_count'],26)
        for change in (lambda d:d['tables'][1]['rows'][-1].__setitem__(6,'INTERNAL_ALIAS'),lambda d:d['tables'][-1]['rows'].pop(),lambda d:d['charts'][-1]['rows'][-1].__setitem__(-1,0.0)):
            bad=deepcopy(display);change(bad)
            with self.assertRaises(ValueError):checker.inspect_display(display=bad,**args)

    def test_series_name_reference_must_not_hide_behind_stale_cache(self):
        with tempfile.TemporaryDirectory()as directory:
            path=Path(directory)/'original.zip';expected=chart_fixture(path);mutated=Path(directory)/'mutated.zip'
            with zipfile.ZipFile(path)as source,zipfile.ZipFile(mutated,'w')as target:
                for member in source.namelist():
                    body=source.read(member)
                    if member=='xl/charts/chart1.xml':
                        body=body.replace('<c:tx><c:v>控制</c:v></c:tx>'.encode(),'<c:tx><c:strRef><c:f>\'数据\'!$A$5</c:f><c:strCache><c:ptCount val="1"/><c:pt idx="0"><c:v>控制</c:v></c:pt></c:strCache></c:strRef></c:tx>'.encode())
                    target.writestr(member,body)
            with self.assertRaises(ValueError):charts.inspect_chart_parts(mutated,expected)


if __name__=='__main__':unittest.main()
