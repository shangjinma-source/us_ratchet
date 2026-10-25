import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from backtest import quantity_saved_anchor_tail_tightening as tail
from test_quantity_saved_anchor_tail_tightening import setup

ROOT=Path(__file__).resolve().parents[1]

def driver():
    spec=importlib.util.spec_from_file_location('independent_tail_driver',ROOT/'tmp/run_saved_anchor_tail_tightening_20261019_v1.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def prepare():
    source,_=setup(); plans=[dict(source,id='open-'+str(i),conditional_bound_calls_max=182) for i in range(2)]
    helper=SimpleNamespace(PINS={},check=lambda *a:None)
    parent=dict(lower_product='1',upper_product='100',integer_selected_unchanged={},inherited_closed_rows=[{'id':str(i)} for i in range(3)],new_rows=[{'id':'fixing-'+str(i)} for i in range(2)])
    return helper,helper,parent,plans,{},{}

class TailDriverIndependent(unittest.TestCase):
    def test_default_no_build_success_keeps_all_parent_references(self):
        m=driver()
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'ROOT',Path(tmp)),patch.object(m,'OUTPUT','result'),patch.object(m,'prepare',side_effect=prepare),patch.object(m,'check'):
            with patch('sys.argv',['driver']),patch.object(tail,'build',side_effect=AssertionError('NO DEFAULT BUILD')),redirect_stdout(io.StringIO()):m.main()
            self.assertFalse((Path(tmp)/'result').exists())
            with patch('sys.argv',['driver','--execute']),redirect_stdout(io.StringIO()):m.main()
            out=Path(tmp)/'result'; report=json.loads((out/'report.json').read_text())
            self.assertEqual(report['inherited_closed_rows'],prepare()[2]['inherited_closed_rows'])
            self.assertEqual(report['inherited_fixing_rows'],prepare()[2]['new_rows'])
            self.assertEqual(len(report['new_rows']),2)
            with patch('sys.argv',['driver','--execute']),patch.object(tail,'build',side_effect=AssertionError('NO RETRY')):
                with self.assertRaises(FileExistsError):m.main()

    def test_failed_build_and_budget_violation_preserve_evidence(self):
        for mode in ('build','budget'):
            m=driver()
            with tempfile.TemporaryDirectory() as tmp,patch.object(m,'ROOT',Path(tmp)),patch.object(m,'OUTPUT','result'),patch.object(m,'prepare',side_effect=prepare),patch('sys.argv',['driver','--execute']):
                effect=ValueError('synthetic failure') if mode=='build' else None
                with patch.object(tail,'build',side_effect=effect,return_value={'conditional_bound_calls':183}) as build:
                    with self.assertRaises(ValueError):m.main()
                    out=Path(tmp)/'result'
                    for name in ('started.json','failed.json','box-0/started.json','box-0/failed.json'):self.assertTrue((out/name).exists())
                    self.assertFalse((out/'report.json').exists());self.assertFalse((out/'terminal.json').exists())
                    with self.assertRaises(FileExistsError):m.main()
                    self.assertEqual(build.call_count,1)

if __name__=='__main__':unittest.main()
