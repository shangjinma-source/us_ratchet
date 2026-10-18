from copy import deepcopy
import ast,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from test_ndx_bulk_budgeted_single_task_independent_readback_20261003 import module as m,documents,case

class IndependentRawReaderReview(unittest.TestCase):
 def test_panel_gap_schedule_and_typed_schema_attacks(self):
  docs,_=documents()
  for attack in ('gap','position','prefix','schema','panel-ref'):
   d=deepcopy(docs)
   if attack=='gap':
    d['panel']['panel']['observed_provenance_and_missing']=deepcopy(d['panel']['panel']['observed_provenance_and_missing']);d['panel']['panel']['observed_provenance_and_missing'][0]['ticker']='REWRITTEN'
   elif attack=='position':
    d['preparation']['schedule']['positions'][-1]=dict(d['preparation']['schedule']['positions'][-1],proposal_index=True)
   elif attack=='prefix':d['preparation']['materialized']['combinations'][-1]['prefix_security_ids'].reverse()
   elif attack=='schema':d['panel']['panel']['schema']='LATEST_CONDITIONAL_TYPED_PANEL_V6'
   else:d['preparation']['materialized']['panel_reference']=dict(m.ref('panel'),sha256='f'*64)
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.validate_documents(d)
 def test_last_rehashed_task_old_collision_and_entire_matrix(self):
  docs,_=documents()
  for attack in ('last','old','unselected'):
   d=deepcopy(docs)
   if attack=='last':
    task=d['preparation']['materialized']['combinations'][-1]['tasks'][-1];task['location_identity']['spec_index']=True;task['location_id']=m.digest(task['location_identity'])
   elif attack=='old':d['rebinding']['rows'][-1]['numerical_task_id']=d['preparation']['materialized']['combinations'][0]['tasks'][0]['numerical_task_id']
   else:d['panel']['panel']['returns']['data'][-1][-1]=True
   with self.assertRaises(ValueError):m.validate_documents(d)
 def test_started_raw_pointer_permission_and_unknown_internal_count(self):
  for attack in ('pointer','runtime','authority','optimizer'):
   a=case()
   if attack=='pointer':a['raw']['started_reference']=dict(a['started_reference'],path='elsewhere')
   elif attack=='runtime':a['raw']['runtime']=dict(a['raw']['runtime'],python='changed')
   elif attack=='authority':a['started']['execution_authorized']=True
   else:a['raw']['internal_optimizer_call_count']=0
   with self.assertRaises(ValueError):m.inspect_envelopes(**a)
 def test_exception_and_different_validation_preserved(self):
  a=case();error={'type':'ArithmeticError','message':'finally returned nothing'};a['raw'].update(status='FIT_EXCEPTION',fitted=None,error=error,returned_fit_count=0)
  detail=m.inspect_envelopes(**a);sr=a['started_reference'];rr={'path':'raw','sha256':'b'*64};tid=a['state']['task']['numerical_task_id']
  post=dict(schema='BULK_BUDGETED_SINGLE_TASK_POSTCHECK_V1',status='NUMERICAL_EXCEPTION_NO_RETURNED_FIT',started_reference=sr,raw_reference=rr,numerical_task_id=tid,checks=None,error=error,**dict.fromkeys(m.FALSE,False))
  self.assertEqual(m.inspect_postcheck(post,sr,rr,tid,detail),'NUMERICAL_EXCEPTION');post['error']={'type':'ValueError','message':'runtime drift'}
  with self.assertRaises(ValueError):m.inspect_postcheck(post,sr,rr,tid,detail)
  post['status']='VALIDATION_FAILURE_RECORDED';self.assertEqual(m.inspect_postcheck(post,sr,rr,tid,detail),'VALIDATION_FAILURE')
 def test_source_conflict_no_producer_import_and_orphan_early_reject(self):
  with self.assertRaises(ValueError):m.guard({str(Path(m.pure.__file__).resolve()):'0'*64})
  tree=ast.parse(Path(m.__file__).read_text(encoding='utf-8-sig'))
  imports=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]+[a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
  self.assertFalse(any(s and ('refit' in s or 'bulk_budgeted_single_task_20261003' in s) for s in imports))
  with tempfile.TemporaryDirectory() as t,patch.object(m,'OUTPUT_ROOT',Path(t)),patch.object(m,'load_common') as load:
   tid='a'*64;folder=Path(t)/tid;folder.mkdir();(folder/'started.json').write_text('{}')
   with self.assertRaises(ValueError):m.readback(tid,{'path':str(folder/'postcheck.json'),'sha256':'b'*64})
   load.assert_not_called();self.assertEqual({p.name for p in folder.iterdir()},{'started.json'})
if __name__=='__main__':unittest.main()
