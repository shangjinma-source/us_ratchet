import importlib.util,io,json,tempfile,unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from hashlib import sha256
from backtest import quantity_small_joint_loss_enumerator as engine
from test_quantity_small_joint_loss_enumerator import fixture
ROOT=Path(__file__).resolve().parents[1]
def driver():
    spec=importlib.util.spec_from_file_location('second_driver',ROOT/'tmp/run_small_second_domain_enumeration_20261019_v1.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def prepared():
    args,inputs,_=fixture();parent=json.loads(args['parent_report_raw'])
    target,other=parent['new_rows'];target['upper_product']='100';other['upper_product']='200';parent['new_rows']=[other,target]
    raw=json.dumps(parent).encode();args.update(parent_report_raw=raw,expected_parent_report_sha256=sha256(raw).hexdigest())
    helper=SimpleNamespace(PINS={},check=lambda *a:None)
    return helper,helper,helper,parent,args,{}, {},inputs
class SecondDriverIndependent(unittest.TestCase):
    def test_default_and_complete_preserve_first_upper(self):
        m=driver()
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'ROOT',Path(tmp)),patch.object(m,'OUTPUT','result'),patch.object(m,'prepare',side_effect=prepared),patch.object(m,'check'):
            with patch('sys.argv',['driver']),patch.object(engine,'build',side_effect=AssertionError('NO DEFAULT ENUM')),redirect_stdout(io.StringIO()):m.main()
            self.assertFalse((Path(tmp)/'result').exists())
            with patch('sys.argv',['driver','--execute']),redirect_stdout(io.StringIO()):m.main()
            report=json.loads((Path(tmp)/'result/report.json').read_text())
            self.assertEqual(report['first_domain_unchanged'],prepared()[3]['new_rows'][0])
            self.assertEqual(report['whole_upper_product'],'200')
            self.assertFalse(report['global_objective_value_optimal'])
            with patch('sys.argv',['driver','--execute']),patch.object(engine,'build',side_effect=AssertionError('NO RETRY')):
                with self.assertRaises(FileExistsError):m.main()
    def test_budget_stopped_keeps_frontier_and_failure_leaves_evidence(self):
        for fail in (False,True):
            m=driver();original=engine.build
            def limited(**kwargs):
                if fail:raise ValueError('SYNTHETIC')
                return original(**dict(kwargs,node_budget=0))
            with tempfile.TemporaryDirectory() as tmp,patch.object(m,'ROOT',Path(tmp)),patch.object(m,'OUTPUT','result'),patch.object(m,'prepare',side_effect=prepared),patch.object(m,'check'),patch('sys.argv',['driver','--execute']),patch.object(engine,'build',side_effect=limited),redirect_stdout(io.StringIO()):
                if fail:
                    with self.assertRaises(ValueError):m.main()
                    self.assertTrue((Path(tmp)/'result/failed.json').exists());self.assertFalse((Path(tmp)/'result/terminal.json').exists())
                else:
                    m.main();out=Path(tmp)/'result';c=json.loads((out/'certificate.json').read_text());t=json.loads((out/'terminal.json').read_text())
                    self.assertTrue(c['unsearched_frontier']);self.assertEqual(t['status'],'BUDGET_STOPPED_UNRESOLVED');self.assertFalse(t['global_objective_value_optimal'])
if __name__=='__main__':unittest.main()
