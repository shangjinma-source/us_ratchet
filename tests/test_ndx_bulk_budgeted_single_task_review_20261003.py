from copy import deepcopy
from contextlib import ExitStack
import json,tempfile,unittest
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch
from test_ndx_bulk_budgeted_single_task_20261003 import module as m,documents,small_state

class IndependentRunnerReview(unittest.TestCase):
 def test_last_task_rehashed_boolean_location_and_old_id_rejected(self):
  docs,num=documents()
  for attack in ('last-location','old-id','seventh-sidecar'):
   d=deepcopy(docs)
   if attack=='last-location':
    task=d['preparation']['materialized']['combinations'][-1]['tasks'][-1];task['location_identity']['spec_index']=True;task['location_id']=m.digest(task['location_identity'])
   elif attack=='old-id':d['rebinding']['rows'][-1]['numerical_task_id']=d['preparation']['materialized']['combinations'][0]['tasks'][0]['numerical_task_id']
   else:d['preparation']['preserved_evidence_sidecar_references']['bulk_incremental_evidence_and_projection']['json_pointer']='/wrong'
   with self.assertRaises(ValueError):m.validate_common(d,num)
 def test_old_root_appears_after_preflight_stops_before_fit(self):
  state=small_state();tid=state['task']['numerical_task_id']
  with tempfile.TemporaryDirectory() as t:
   old=Path(t)/'old';new=Path(t)/'new'
   def guard(_):(old/tid).mkdir(parents=True)
   with patch.object(m,'OUTPUT_ROOT',new),patch.object(m,'OLD_ROOTS',(old,)),patch.object(m,'preflight',return_value=state),patch.object(m,'guard',side_effect=guard),patch.object(m.fitter,'refit_dynamic_cutoff_weights') as fit:
    with self.assertRaises(ValueError):m.run(tid,execute=True)
    fit.assert_not_called();self.assertFalse(new.exists())
 def test_exception_then_runtime_drift_preserves_raw_unknown_counts(self):
  state=small_state();tid=state['task']['numerical_task_id']
  with tempfile.TemporaryDirectory() as t:
   folder=Path(t)/'new'
   with patch.object(m,'OUTPUT_ROOT',folder),patch.object(m,'OLD_ROOTS',()),patch.object(m,'preflight',return_value=state),patch.object(m,'guard'),patch.object(m,'runtime',side_effect=[state['runtime'],{'changed':True}]),patch.object(m.fitter,'refit_dynamic_cutoff_weights',side_effect=ArithmeticError('internal finally failed')) as fit:
    ref=m.run(tid,execute=True)
   raw=json.loads((folder/tid/'raw.json').read_bytes());post=json.loads(Path(ref['path']).read_bytes())
   self.assertEqual(post['status'],'VALIDATION_FAILURE_RECORDED');self.assertEqual(raw['status'],'FIT_EXCEPTION');self.assertIsNone(raw['fitted']);self.assertIsNone(raw['internal_optimizer_call_count']);self.assertEqual(raw['returned_fit_count'],0);self.assertEqual(fit.call_count,1)
 def test_registered_handle_mutation_and_runtime_are_not_cached_away(self):
  common={'ordered_task_ids':['a'*64]};frozen={'tasks':MappingProxyType({'a'*64:(0,0,b'{}')}),'sources':MappingProxyType({}),'runtime':json.dumps({'old':True}).encode()}
  with patch.dict(m._COMMON_REGISTRY,{id(common):(common,MappingProxyType(frozen))},clear=True),patch.object(m,'check_roots'),patch.object(m,'guard') as guard,patch.object(m,'runtime',return_value={'changed':True}):
   with self.assertRaisesRegex(ValueError,'Runtime'):m.preflight('a'*64,common=common)
   guard.assert_called_once();common['ordered_task_ids'].append('b'*64)
   with self.assertRaisesRegex(ValueError,'order'):m.preflight('a'*64,common=common)
if __name__=='__main__':unittest.main()
