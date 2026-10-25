import importlib.util
from pathlib import Path
import tempfile
from unittest.mock import patch
import unittest
import json

class EmptyDriverTests(unittest.TestCase):
    def test_exact_threshold_and_types(self):
        spec=importlib.util.spec_from_file_location('five_driver_threshold',Path('tmp/run_continuous_anchor_five_boxes_20261019_v1.py'))
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        for upper,expected in [('999/1000','CLOSED'),('1','CLOSED'),('1000000000000000001/1000000000000000000','OPTIMIZE')]:
            self.assertEqual(m.classify(dict(effective_empty=False,effective_upper_product=upper),'1'),expected)
        self.assertEqual(m.classify(dict(effective_empty=True,effective_upper_product=None),'1'),'EMPTY')
        for empty,upper in [(1,None),(False,True),(True,'1')]:
            with self.assertRaises(ValueError):m.classify(dict(effective_empty=empty,effective_upper_product=upper),'1')

    def test_verified_empty_frontier_kept_without_optimizer(self):
        spec=importlib.util.spec_from_file_location('five_driver',Path('tmp/run_continuous_anchor_five_boxes_20261019_v1.py'))
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        rows=[dict(id='r'+str(i),box={'A':[0,0]},effective_empty=True,closed_by_inherited_upper=False,proof_reference={'kind':'VERIFIED_CAPPED_EMPTY','certificate_sha256':m.PINS[m.CAPPED],'node_id':'r'+str(i)},capped_parent_path=[],inherited_evidence=None) for i in range(5)]
        capped=dict(lower_product='1',upper_product='1',selected={})
        with tempfile.TemporaryDirectory() as temp,patch.object(m,'ROOT',Path(temp)),patch.object(m,'OUTPUT','out'),patch.object(m,'prepare',return_value=(capped,{},rows,{},{})),patch.object(m,'check'),patch('sys.argv',['driver','--execute']),patch('backtest.quantity_continuous_anchor_bound.optimize',side_effect=AssertionError('EMPTY OPTIMIZER')) as opt:
            m.main();self.assertEqual(opt.call_count,0)
            report=json.loads((Path(temp)/'out/report.json').read_bytes());terminal=json.loads((Path(temp)/'out/terminal.json').read_bytes())
            self.assertEqual([r['id'] for r in report['rows']],[r['id'] for r in rows]);self.assertEqual(terminal['failed_boxes'],0)
            self.assertEqual(terminal['remaining_boxes'],0)
            self.assertTrue(all(r['status']=='VERIFIED_EMPTY_NO_OPTIMIZER' for r in report['rows']))

if __name__=='__main__':unittest.main()
