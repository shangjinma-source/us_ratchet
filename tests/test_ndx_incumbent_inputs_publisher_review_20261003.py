from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from scripts import ndx_multidecision_incumbent_inputs_20261003 as w
from test_ndx_multidecision_incumbent_inputs_20261003 import physical

class Review(unittest.TestCase):
 def test_physical_private_inputs_never_call_shared_adapter_or_control(self):
  from backtest import ndx_multidecision_incumbent_inputs_research as public
  from backtest import ndx_incumbent_flow_split_control_research as engine
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);bound=physical(root)
   with patch.object(w,'BOUND',bound),patch.object(w,'OUTPUT',root/'out'),patch.object(w,'resource'),patch.object(public,'prepare_incumbent_account_inputs',side_effect=AssertionError('shared adapter')),patch.object(engine,'simulate_incumbent_flow_split_control',side_effect=AssertionError('account forbidden')):
    rr=w.run(execute=True)
   d=w.decode(Path(rr['path']).read_bytes());self.assertEqual(d['inputs']['track_count'],16);self.assertFalse(d['account_simulation_performed'])
   for row in d['inputs']['rows']:
    self.assertFalse(row['risk_is_order_gate']);self.assertFalse(row['weights_normalized'])
 def test_none_raw_before_validation_and_output_tamper_remain_failures(self):
  for badreturn in (True,False):
   with self.subTest(badreturn=badreturn),tempfile.TemporaryDirectory() as td:
    root=Path(td);bound=physical(root);load=w.load_inputs;save=w.save;out=root/'out'
    def context():
     c=load()
     if badreturn:c['core'].prepare_incumbent_account_inputs=lambda **kwargs:None
     return c
    def saved(name,value,emergency=False):
     rr=save(name,value,emergency)
     if not badreturn and name=='publication.json':(out/'inputs.json').write_bytes(b'{}')
     return rr
    with patch.object(w,'BOUND',bound),patch.object(w,'OUTPUT',out),patch.object(w,'resource'),patch.object(w,'load_inputs',side_effect=context),patch.object(w,'save',side_effect=saved):
     with self.assertRaises((TypeError,ValueError)):w.run(execute=True)
     with self.assertRaisesRegex(ValueError,'no retry'):w.run(execute=True)
    self.assertTrue((out/'failure.json').exists())
    if badreturn:self.assertIsNone(w.decode((out/'inputs.json').read_bytes())['inputs']);self.assertFalse((out/'publication.json').exists())

if __name__=='__main__':unittest.main()
