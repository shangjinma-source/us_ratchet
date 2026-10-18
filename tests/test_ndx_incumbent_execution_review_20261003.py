import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from test_ndx_multidecision_incumbent_execution_20261003 import e, physical_execution_sources


class Review(unittest.TestCase):
 def test_private_control_ignores_shared_callable_and_preserves_raw_weights(self):
  from backtest import ndx_incumbent_flow_split_control_research as shared
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);parent,bound=physical_execution_sources(root)
   with patch.object(e,'BOUND',bound),patch.object(e,'PARENT',parent),patch.object(e,'OUTPUT',root/'out'),patch.object(shared,'simulate_incumbent_flow_split_control',side_effect=AssertionError('shared callable forbidden')):
    context=e.load_inputs()
    for track in context['inputs']['rows'][0]['tracks']:
     result=context['engines'][track['track']](**e.restore_kwargs(track,context['pandas']))
     e.verify_return(result,track)
     self.assertEqual(result['original_targets'],track['engine_binding']['keyword_arguments']['schedule'][0]['targets'])
     self.assertIs(result['weights_normalized'],False)
     self.assertIs(result['risk_is_order_gate'],False)

 def test_return_then_parent_drift_keeps_original_return_and_full_partition(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);parent,bound=physical_execution_sources(root);out=root/'out'
   with patch.object(e,'BOUND',bound),patch.object(e,'PARENT',parent),patch.object(e,'OUTPUT',out):
    context=e.load_inputs();original=context['engines']['CONTINUOUS'];returned=[]
    def call(**kwargs):
     result=original(**kwargs);returned.append(result)
     (parent/'inputs.json').write_bytes(b'changed after return')
     return result
    context['engines']['CONTINUOUS']=call
    with patch.object(e,'load_inputs',return_value=context):
     with self.assertRaisesRegex(ValueError,'technical failure'):e.run(execute=True)
     with self.assertRaisesRegex(ValueError,'Exclusive'):e.run(execute=True)
    result=e.decode((out/'result.json').read_bytes())
    raw=e.decode((out/'tracks/00/raw_result.json').read_bytes())
    self.assertEqual(raw['result'],returned[0]);self.assertIs(raw['returned'],True)
    self.assertEqual(result['account_call_count'],1);self.assertEqual(len(result['rows']),16)
    self.assertEqual(result['counts'],{'UNDISPATCHED':15,'VALIDATION_FAILURE':1})
    self.assertTrue((out/'failure.json').exists());self.assertFalse((out/'publication.json').exists())

 def test_post_publication_output_drift_does_not_return_success(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);parent,bound=physical_execution_sources(root);out=root/'out';save=e.save
   def intercept(path,value,emergency=False):
    reference=save(path,value,emergency)
    if Path(path).name=='publication.json':(out/'tracks/00/raw_result.json').write_bytes(b'{}')
    return reference
   with patch.object(e,'BOUND',bound),patch.object(e,'PARENT',parent),patch.object(e,'OUTPUT',out),patch.object(e,'save',side_effect=intercept):
    with self.assertRaisesRegex(ValueError,'Output drift'):e.run(execute=True)
   self.assertTrue((out/'publication.json').exists());self.assertTrue((out/'failure.json').exists())


if __name__=='__main__':unittest.main()
