import json,unittest
from unittest.mock import patch
from pathlib import Path
from scripts import ndx_official_missing_ticker_bridge_diagnostic_v2_20261003 as m
from test_ndx_official_missing_ticker_bridge_diagnostic_20261003 import fixture
import test_ndx_official_missing_ticker_bridge_diagnostic_20261003 as old
class Tests(old.Tests):
 def setUp(self):self.p=patch.object(old,'m',m);self.p.start()
 def tearDown(self):self.p.stop()
 def test_nested_layout_direct_cells_and_exact_offsets(self):
  a=list(fixture());a[1]['ea_suspension']=b'<table><tr><td>layout<div>'+a[1]['ea_suspension']+b'</div></td></tr></table>';a[2]['ea_suspension']['response_reference']=m.ref('ea_suspension.bin',a[1]['ea_suspension'])
  d=m.diagnose(*a);self.assertEqual(d['rows'][0]['evidence'][0]['suspension_effective_date'],'2026-08-05')
  fields=d['rows'][0]['evidence'][0]['fields'];self.assertTrue(all(a[1]['ea_suspension'][v['location']['byte_start']:v['location']['byte_stop']].startswith(b'<tr>')for v in fields.values()))
if __name__=='__main__':unittest.main()
