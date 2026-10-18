from copy import deepcopy
import importlib.util
from itertools import combinations,product
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_v3_completed_task_rebinding_independent_readback_20260925 as m
spec=importlib.util.spec_from_file_location('old_synthetic',Path(__file__).with_name('test_ndx_multik_materialization_independent_readback_research.py'));f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)

def fixture():
 a=f.fixture();oldplan=a['plan'];plan=deepcopy(oldplan);context=plan['context']
 universe=deepcopy(a['panel']['universe']);universe.append(dict(security_id='NEW',ticker='CPRT',issuer_id='I00X',risk_chain='automotive'))
 groups={}
 for r in universe:groups.setdefault(r['issuer_id'],[]).append(r['security_id'])
 plan['canonical_groups']=[dict(issuer_id=i,security_ids=sorted(v)) for i,v in sorted(groups.items())]
 context['panel_reference']=m.ref('panel');context['panel_audit_reference']=m.ref('audit');context['group_fingerprint']=m.digest(dict(order_version=m.ORDER,groups=[(i,sorted(v)) for i,v in sorted(groups.items())]));plan['plan_id']=m.digest(context)
 plan['planned_canonical_task_count']=plan['remaining_canonical_task_count']=4713966;plan['shards']=[];plan['fitter_source_hashes']=a['expected_fitter_source_hashes']
 for k in range(4,20):
  total=m.suffix_count([len(g['security_ids']) for g in plan['canonical_groups']],0,k);identity=dict(context,k=k,start=0,stop=total)
  plan['shards'].append(dict(identity,plan_id=plan['plan_id'],shard_id=m.digest(identity),completed_canonical_task_count=0,remaining_canonical_task_count=3*total,status='PLANNED_NOT_ENUMERATED'))
 def rows(values):
  return [dict(full_task=deepcopy(task),numerical_task_id=task['numerical_task_id'],fit_data_sha256=combo['fit_data_sha256'],status='FITTED_FIVE_RISKS_PASSED',independent_readback_reference={'path':'synthetic/reference','sha256':'a'*64}) for value in values for combo in value['combinations'] for task in combo['tasks']]
 index=dict(schema='NEW_CUTOFF_MULTIK_COMPLETED_TASK_INDEX_V1',batch_saved_attempt_count=96,new_tasks=rows(a['materializations']),old_completed_tasks=rows([a['old_materialization']]))
 frame=m.codec.pd.DataFrame([r+[.025] for r in a['panel']['returns']],index=m.codec.pd.to_datetime(a['panel']['dates']),columns=a['panel']['columns']+['CPRT'])
 panel=dict(schema='LATEST_CONDITIONAL_TYPED_PANEL_V3',conditional_security_count=21,conditional_issuer_count=20,returns=frame,universe=m.codec.pd.DataFrame(universe),panel_content_sha256='b'*64,**dict.fromkeys(m.codec.PANEL_FALSE,False))
 docs=dict(plan=dict(schema='SOURCE_BOUND_NEW_CUTOFF_SHARD_PREPARE_V3',input_references=dict(panel=m.ref('panel'),audit=m.ref('audit')),plan=plan,external_completed_index_reference=m.ref('completed_index'),completed_task_rebinding_verified=False,external_completed_tasks_deducted=0),panel={'panel':{}},audit=dict(status='PASSED',candidate_reference=m.ref('panel'),original_twenty_five_frames_exact=True,panel_content_sha256='b'*64),completed_index=index)
 for d in docs.values():d.update(promotion_allowed=False,execution_authorized=False,legal_training_input_admitted=False)
 return docs,panel

class Tests(unittest.TestCase):
 def test_rank_against_small_exhaustive_reference(self):
  groups=[dict(issuer_id='A',security_ids=['a','aa']),dict(issuer_id='B',security_ids=['b']),dict(issuer_id='C',security_ids=['c','cc']),dict(issuer_id='D',security_ids=['d'])]
  for k in range(1,5):
   selections=[]
   for chosen in combinations(range(4),k):
    for sids in product(*(groups[i]['security_ids'] for i in chosen)):selections.append(list(sids))
   lookup={s:(i,j) for i,g in enumerate(groups) for j,s in enumerate(g['security_ids'])};selections.sort(key=lambda selected:[lookup[s] for s in selected])
   self.assertEqual([m.independent_rank(groups,s) for s in selections],list(range(len(selections))))
  with self.assertRaises(ValueError):m.independent_rank(groups,['a','aa'])
 def test_all96_rebound_without_numeric_identity_changes(self):
  docs,panel=fixture();before=deepcopy(docs['completed_index'])
  with patch.object(m.codec,'decode_frames',return_value=panel):rows=m.reconstruct_rows(docs)
  self.assertEqual(len(rows),96);self.assertEqual(docs['completed_index'],before);self.assertEqual(len({r['new_location_id'] for r in rows}),96)
  self.assertTrue(any(r['new_location_identity']['rank']!=r['old_completed_row']['full_task']['location_identity']['rank'] for r in rows))
  self.assertTrue(all(r['new_wrapper_call_attempt_count']==0 for r in rows))
 def test_matrix_prior_source_ref_and_partial_attack(self):
  for attack in ('matrix','prior','source','partial','counter','shard','risk','status'):
   docs,panel=fixture()
   if attack=='matrix':panel['returns'].iloc[0,0]=.9
   elif attack=='prior':docs['plan']['plan']['context']['previous_target_weights']={}
   elif attack=='source':docs['plan']['plan']['fitter_source_hashes']={}
   elif attack=='partial':docs['completed_index']['new_tasks'].pop()
   elif attack=='counter':docs['plan']['external_completed_tasks_deducted']=False
   elif attack=='shard':docs['plan']['plan']['shards'][0]['shard_id']='0'*64
   elif attack=='risk':panel['universe'].loc[0,'risk_chain']='different'
   else:docs['completed_index']['new_tasks'][0]['status']='NUMERICAL_EXCEPTION_NO_RETURNED_FIT'
   with self.subTest(attack=attack),patch.object(m.codec,'decode_frames',return_value=panel),self.assertRaises(ValueError):m.reconstruct_rows(docs)
 def test_envelope_rejects_location_oldrow_and_denominator(self):
  docs,panel=fixture()
  with patch.object(m.codec,'decode_frames',return_value=panel):rows=m.reconstruct_rows(docs)
  sources={};value=dict(schema='NEW_CUTOFF_V3_COMPLETED_TASK_REBINDING_V1',input_references={k:m.ref(k) for k in m.BOUND},rows=rows,externally_rebound_task_count=96,externally_rebound_combination_count=32,full_plan_task_denominator=4713966,remaining_uncompleted_task_count=4713870,new_wrapper_call_attempt_count=0,new_fit_count=0,old_full_tasks_and_completion_references_preserved=True,rank_calculation_performed=True,combination_enumeration_performed=False,**dict.fromkeys(m.PRODUCER_FALSE,False),source_hashes=sources)
  with patch.object(m.codec,'decode_frames',return_value=panel),patch.object(m,'producer_sources',return_value=sources):
   self.assertEqual(len(m.verify_candidate(value,docs)),96)
   for attack in ('location','oldrow','count','permission'):
    changed=deepcopy(value)
    if attack=='location':changed['rows'][0]['new_location_identity']['rank']+=1
    elif attack=='oldrow':changed['rows'][0]['old_completed_row']['independent_readback_reference']['sha256']='f'*64
    elif attack=='count':changed['remaining_uncompleted_task_count']=0
    else:changed['all_plan_tasks_completed']=True
    with self.subTest(attack=attack),self.assertRaises(ValueError):m.verify_candidate(changed,docs)
 def test_pending_pin_and_existing_audit_fail_before_work(self):
  with patch.object(m,'PRODUCER_SHA',None),patch.object(m,'guard') as guard:
   with self.assertRaises(ValueError):m.build()
   guard.assert_not_called()
  with tempfile.TemporaryDirectory() as directory:
   out=Path(directory)/'independent_readback.json';out.write_text('{}')
   with patch.object(m,'OUTPUT',out),patch.object(m,'build') as build:
    with self.assertRaises(ValueError):m.publish()
    build.assert_not_called()
if __name__=='__main__':unittest.main()
