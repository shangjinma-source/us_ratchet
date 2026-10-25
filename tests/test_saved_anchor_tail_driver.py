import importlib.util
from pathlib import Path
import tempfile
from unittest.mock import patch,Mock
import unittest
class DriverTests(unittest.TestCase):
 def load(self):
  spec=importlib.util.spec_from_file_location('tail_driver',Path('tmp/run_saved_anchor_tail_tightening_20261019_v1.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
 def test_default_no_build_or_output(self):
  m=self.load()
  with tempfile.TemporaryDirectory() as tmp,patch.object(m,'ROOT',Path(tmp)),patch.object(m,'OUTPUT','out'),patch.object(m,'prepare',return_value=(None,None,None,None,None,None)),patch('sys.argv',['driver']),patch('backtest.quantity_saved_anchor_tail_tightening.build',side_effect=AssertionError('NO BUILD')) as build:
   m.main();self.assertEqual(build.call_count,0);self.assertFalse((Path(tmp)/'out').exists())
 def test_existing_output_rejected(self):
  m=self.load()
  with tempfile.TemporaryDirectory() as tmp,patch.object(m,'ROOT',Path(tmp)),patch.object(m,'OUTPUT','out'),patch.object(m,'prepare',return_value=(None,None,None,None,None,None)),patch('sys.argv',['driver','--execute']):
   (Path(tmp)/'out').mkdir()
   with self.assertRaises(FileExistsError):m.main()
 def test_failed_build_retained(self):
  m=self.load();plan=dict(id='x',fixing_raw=b'x',expected_fixing_sha256='a'*64,fixing_sources={},conditional_bound_calls_max=1)
  loader=Mock();loader.PINS={};parent=dict(lower_product='1',upper_product='2')
  with tempfile.TemporaryDirectory() as tmp,patch.object(m,'ROOT',Path(tmp)),patch.object(m,'OUTPUT','out'),patch.object(m,'prepare',return_value=(loader,loader,parent,[plan],{},{})),patch('sys.argv',['driver','--execute']),patch('backtest.quantity_saved_anchor_tail_tightening.build',side_effect=ValueError('synthetic failure')):
   with self.assertRaises(ValueError):m.main()
   self.assertTrue((Path(tmp)/'out/failed.json').exists());self.assertTrue((Path(tmp)/'out/box-0/failed.json').exists());self.assertFalse((Path(tmp)/'out/terminal.json').exists())
if __name__=='__main__':unittest.main()
