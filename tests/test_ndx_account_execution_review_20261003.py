from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from scripts import ndx_multidecision_account_execution_20261003 as w
from test_ndx_multidecision_account_execution_20261003 import physical

class Review(unittest.TestCase):
 def test_private_dag_ignores_stale_shared_callable_and_hashes_consumed_code(self):
  from backtest import ndx_dynamic_fractional_flow_split_research_v2 as public
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);parent,bound=physical(root)
   with patch.object(w,'ROOT',root),patch.object(w,'PARENT',parent),patch.object(w,'BOUND',bound),patch.object(public,'simulate_dynamic_fractional_flow_split_research',side_effect=AssertionError('shared function forbidden')):
    c=w.load_inputs()
    self.assertIsNot(c['engines']['CONTINUOUS'],public.simulate_dynamic_fractional_flow_split_research)
    self.assertIn('_private_account_',c['engines']['CONTINUOUS'].__module__)
    name=next(iter(w.CODE));path=root/'backtest'/f'{name}.py';path.write_bytes(path.read_bytes()+b'\n# changed')
    with self.assertRaisesRegex(ValueError,'Authenticated same consumed bytes'):w.load_inputs()
 def test_source_drift_after_return_preserves_raw_and_all_slots(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);parent,bound=physical(root);out=root/'out';real=w.private_engines
   def engines(s):
    es,pd,runtime=real(s)
    def call(**kwargs):
     Path(bound['reader'][0]).write_bytes(b'changed after dispatch')
     return {'original_return':['preserved',0,None]}
    es['CONTINUOUS']=call;return es,pd,runtime
   with patch.object(w,'ROOT',root),patch.object(w,'PARENT',parent),patch.object(w,'BOUND',bound),patch.object(w,'OUTPUT',out),patch.object(w,'resource'),patch.object(w,'private_engines',side_effect=engines):
    with self.assertRaises(ValueError):w.run(execute=True)
    with self.assertRaisesRegex(ValueError,'Exclusive'):w.run(execute=True)
   raw=w.decode((out/'tracks/08/raw_result.json').read_bytes());result=w.decode((out/'result.json').read_bytes())
   self.assertEqual(raw['result'],{'original_return':['preserved',0,None]});self.assertTrue(raw['returned'])
   self.assertEqual(result['rows'][8]['outcome'],'VALIDATION_FAILURE');self.assertEqual(result['counts']['UNDISPATCHED'],7)
   self.assertEqual(result['counts']['BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT'],8);self.assertEqual(len(result['rows']),16)
   self.assertTrue((out/'failure.json').exists());self.assertFalse((out/'publication.json').exists())
 def test_post_publication_output_drift_is_not_success(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);parent,bound=physical(root);out=root/'out';real=w.save;realengines=w.private_engines
   def engines(s):
    es,pd,runtime=realengines(s)
    for kind in es:
     def call(kind=kind,**kwargs):
      flags=dict.fromkeys(('point_in_time_verified','promotion_allowed','formal_benchmark_passed','source_bytes_authenticated','actual_orders_executed','source_authenticity_verified','broker_atomic_execution_verified','auto_replan_enabled'),False)
      return dict(schema=w.ENGINES[kind][2],daily=[{'session':str(x.date())} for x in kwargs['closes'].index],**flags)
     es[kind]=call
    return es,pd,runtime
   def save(path,value,emergency=False):
    r=real(path,value,emergency)
    if Path(path).name=='publication.json':(out/'tracks/08/raw_result.json').write_bytes(b'{}')
    return r
   with patch.object(w,'ROOT',root),patch.object(w,'PARENT',parent),patch.object(w,'BOUND',bound),patch.object(w,'OUTPUT',out),patch.object(w,'resource'),patch.object(w,'private_engines',side_effect=engines),patch.object(w,'save',side_effect=save):
    with self.assertRaisesRegex(ValueError,'Output drift'):w.run(execute=True)
   self.assertTrue((out/'failure.json').exists());self.assertTrue((out/'publication.json').exists())

if __name__=='__main__':unittest.main()
