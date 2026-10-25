import importlib.util,json,tempfile
from pathlib import Path
from unittest.mock import patch
import unittest

class IndependentFiveDriverTests(unittest.TestCase):
 def test_mixed_domain_failures_retained_once(self):
  path=Path('tmp/run_continuous_anchor_five_boxes_20261019_v1.py');spec=importlib.util.spec_from_file_location('five_independent',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  selections=[]
  for i in range(5):
   selections.append(dict(id=str(i),box={'A':[0,2]},effective_empty=i==0,closed_by_inherited_upper=i in (1,2),inherited_evidence={'upper_product':'1' if i<3 else '2'},proof_reference={'source':'synthetic'},capped_parent_path=[]))
  capped=dict(lower_product='1',upper_product='2',selected={})
  with tempfile.TemporaryDirectory() as folder,patch.object(m,'ROOT',Path(folder)),patch.object(m,'OUTPUT','out'),patch.object(m,'prepare',return_value=(capped,{},selections,{},{})),patch.object(m,'check'),patch('sys.argv',['driver','--execute']),patch('backtest.quantity_continuous_anchor_bound.optimize',side_effect=ValueError('SYNTHETIC_FAILURE')) as opt:
   with self.assertRaises(SystemExit):m.main()
   self.assertEqual(opt.call_count,2);out=Path(folder)/'out';report=json.loads((out/'report.json').read_bytes());term=json.loads((out/'terminal.json').read_bytes())
   self.assertEqual(len(report['rows']),5);self.assertEqual([r['id'] for r in report['rows']],list(map(str,range(5))))
   self.assertEqual(term['actual_optimizer_calls'],2);self.assertEqual(term['failed_boxes'],2);self.assertEqual(term['remaining_boxes'],2)
   self.assertEqual(report['upper_product'],'2');self.assertTrue((out/'box-3/failed.json').exists());self.assertTrue((out/'failed.json').exists())
   with self.assertRaises(FileExistsError):m.main()
   self.assertEqual(opt.call_count,2)

if __name__=='__main__':unittest.main()
