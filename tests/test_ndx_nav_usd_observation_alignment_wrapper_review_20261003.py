"""Independent synthetic wrapper review; no real253 conversion."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('nav_usd_wrapper_fixture',ROOT/'tests/test_ndx_nav_usd_observation_alignment_20261003.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f);m=f.m

class Review(unittest.TestCase):
 def test_all_original_literals_and_nd_source_positions_preserved(self):
  docs,refs=f.fixture();literal='1.250000000000000000000000000001';docs['nav_csv'][17].update(Close=literal,UnitNav=literal,AccumNav='9.999',DailyPct='-0.000001');before=deepcopy(docs)
  a=m.project_inputs(docs,refs)
  self.assertEqual(a['nav_rows'][17]['nav_cny_decimal'],literal);self.assertEqual(a['nav_rows'][17]['original_csv_row'],docs['nav_csv'][17]);self.assertEqual(a['nav_rows'][17]['source_reference']['csv_record_number'],19)
  self.assertEqual(a['fx_rows'],docs['fx_readback']['table_rows']);self.assertEqual(len([r for r in a['fx_rows'] if r['status']=='NOT_AVAILABLE_ND']),2)
  self.assertEqual(a['fx_context']['receipts'],docs['fx_readback']['receipts']);self.assertEqual(docs,before)
  self.assertTrue(all(r['available_at'] is None for r in a['nav_rows']))

 def test_raw_capture_nav_snapshot_and_row_reference_conflicts(self):
  mutations=(lambda d:d['fx_manifest']['sources'][1]['raw'].update(sha256='f'*64),lambda d:d['nav_snapshot']['immutable_copies']['nav.csv'].update(path='other'),lambda d:d['fx_readback']['table_rows'][-1]['source_reference'].update(table_row_index=0),lambda d:d['requirements_publication'].update(source_hashes={'injected':'a'*64}),lambda d:d['nav_manifest'].update(row_count=True),lambda d:d['fx_readback'].update(point_in_time_verified=0))
  for mutate in mutations:
   docs,refs=f.fixture();docs=deepcopy(docs);mutate(docs)
   with self.assertRaises(ValueError):m.project_inputs(docs,refs)

 def test_loaded_source_drift_and_failure_before_projection(self):
  with tempfile.TemporaryDirectory() as td:
   source=Path(td)/'source';source.write_bytes(b'changed')
   with patch.object(m,'SOURCE',source),patch.object(m,'LOADED_SHA',m.sha(b'original')):
    with self.assertRaises(ValueError):m.guard({})
   output=Path(td)/'attempt'
   with patch.object(m,'OUTPUT',output),patch.object(m,'load_inputs',return_value=({}, {}, {}, None)) as loader,patch.object(m,'project_inputs',side_effect=ValueError('bad reference')):
    with self.assertRaises(ValueError):m.run(execute=True)
    self.assertEqual({p.name for p in output.iterdir()},{'started.json','failure.json'})
    with self.assertRaises(ValueError):m.run(execute=True)
    self.assertEqual(loader.call_count,1)

if __name__=='__main__':unittest.main()
