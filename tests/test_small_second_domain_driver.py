import importlib.util,json
from pathlib import Path
import tempfile
from unittest.mock import patch,Mock
import unittest
from test_quantity_integer_box_certificate_prototype import fixture
class DriverTests(unittest.TestCase):
 def load(self):
  spec=importlib.util.spec_from_file_location('small_driver',Path('tmp/run_small_second_domain_enumeration_20261019_v1.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
 def test_readonly_and_existing(self):
  m=self.load()
  with tempfile.TemporaryDirectory() as tmp,patch.object(m,'ROOT',Path(tmp)),patch.object(m,'OUTPUT','out'),patch.object(m,'prepare',return_value=(None,)*8),patch('sys.argv',['driver']),patch('backtest.quantity_small_joint_loss_enumerator.build',side_effect=AssertionError('NO ENUMERATION')) as build:
   m.main();self.assertEqual(build.call_count,0);self.assertFalse((Path(tmp)/'out').exists())
   (Path(tmp)/'out').mkdir()
   with patch('sys.argv',['driver','--execute']),self.assertRaises(FileExistsError):m.main()
 def test_failed_build_kept(self):
  m=self.load();loader=Mock();loader.PINS={};prepared=(loader,loader,loader,{}, {},{}, {},fixture())
  with tempfile.TemporaryDirectory() as tmp,patch.object(m,'ROOT',Path(tmp)),patch.object(m,'OUTPUT','out'),patch.object(m,'prepare',return_value=prepared),patch('sys.argv',['driver','--execute']),patch('backtest.quantity_small_joint_loss_enumerator.build',side_effect=ValueError('synthetic failure')):
   with self.assertRaises(ValueError):m.main()
   self.assertTrue((Path(tmp)/'out/failed.json').exists());self.assertFalse((Path(tmp)/'out/terminal.json').exists())
 def test_budget_stop_preserves_first_upper_and_frontier(self):
  m=self.load();loader=Mock();loader.PINS={};parent=dict(lower_product='1',new_rows=[dict(id='first',upper_product='2'),dict(id='second',upper_product='3')],inherited_closed_rows=[],inherited_fixing_rows=[])
  c=dict(status='BUDGET_STOPPED_UNRESOLVED',selected_candidate={},candidate_product='1',domain_complete=False,checked_points=0,visited_nodes=0,objective_evaluations=0,unsearched_frontier=[[]])
  prepared=(loader,loader,loader,parent,{}, {},{},fixture())
  with tempfile.TemporaryDirectory() as tmp,patch.object(m,'ROOT',Path(tmp)),patch.object(m,'OUTPUT','out'),patch.object(m,'prepare',return_value=prepared),patch.object(m,'check'),patch('sys.argv',['driver','--execute']),patch('backtest.quantity_small_joint_loss_enumerator.build',return_value=c),patch('backtest.quantity_small_joint_loss_enumerator.verify',return_value={'status':'TEST_ONLY'}):
   m.main();report=json.loads((Path(tmp)/'out/report.json').read_bytes());saved=json.loads((Path(tmp)/'out/certificate.json').read_bytes())
   self.assertEqual(report['whole_upper_product'],'3');self.assertEqual(report['first_domain_unchanged'],parent['new_rows'][0]);self.assertFalse(report['global_objective_value_optimal']);self.assertEqual(saved['unsearched_frontier'],[[]]);self.assertFalse((Path(tmp)/'out/failed.json').exists())
if __name__=='__main__':unittest.main()
