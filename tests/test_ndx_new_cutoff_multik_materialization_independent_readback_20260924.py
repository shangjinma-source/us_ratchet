"""Synthetic source-bound batch envelope and old-reference checks only."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_multik_materialization_independent_readback_20260924 as m
spec=importlib.util.spec_from_file_location('batch_fixture',Path(__file__).with_name('test_ndx_multik_materialization_independent_readback_research.py'))
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)


def documents_fixture():
 args=f.fixture();old=args['old_materialization'];combo=old['combinations'][0]
 index=dict(schema='NEW_CUTOFF_COMPLETED_TASK_INDEX_V1',input_references=dict(plan=m.ref('plan'),materialized=m.ref('old_materialized'),materialization_audit=m.ref('old_materialization_audit')),completed_task_count=3,completed_combination_count=1,completed_original_risk_pass_count=3,completed_original_risk_failure_count=0,original_plan_task_denominator=2355300,remaining_plan_task_count=2355297,original_plan_combination_denominator=785100,remaining_plan_combination_count=785099,completed_coordinate=dict(k=4,rank=0,prefix_security_ids=combo['prefix_security_ids']),completed_tasks=[],source_hashes={})
 for flag in ('fit_performed','task_readback_repeated','materialization_repeated','all_plan_tasks_completed','full_shard_completed','point_in_time_verified','legal_training_input_admitted','promotion_allowed','execution_authorized','full_transitive_source_closure_reverified','anchor_alias_equivalence_verified','economic_comparison_performed'):index[flag]=False
 for i,task in enumerate(combo['tasks']):
  eq=task['numerical_identity']['weight_spec']=='equal_weight'
  row=dict(full_task=deepcopy(task),numerical_task_id=task['numerical_task_id'],weight_spec=task['numerical_identity']['weight_spec'],fit_data_sha256=combo['fit_data_sha256'],status='COMPLETED_EXTERNALLY_AUDITED_ORIGINAL_FIVE_RISKS_PASSED',task_reference=dict(m.ref('old_materialized'),json_pointer='/materialization/combinations/0/tasks/'+str(i)),operation_counts=dict(wrapper_call_attempt_count=1,deterministic_generation_request_count=int(eq),numerical_fit_request_count=int(not eq),import_count=0),targets={sid:dict(ticker=v['ticker'],issuer_id=v['issuer_id'],target_weight=.25) for sid,v in task['numerical_identity']['selected'].items()})
  for key,name in [('started_reference','started.json'),('raw_reference','raw.json'),('postcheck_reference','postcheck.json'),('independent_readback_reference','independent_readback.json')]:
   p=str(m.BASE/'new_cutoff_single_task_20260924_v1'/row['numerical_task_id']/name);row[key]=dict(path=p,sha256='a'*64);index['source_hashes'][p]='a'*64
  index['completed_tasks'].append(row)
 docs=dict(completed_index=index,old_materialized=dict(materialization=old),old_materialization_audit=dict(status='PASSED',candidate_reference=m.ref('old_materialized')))
 return args,docs


class Tests(unittest.TestCase):
 def test_outer_fullpool_sidecars_and_counts_exact(self):
  args,docs=documents_fixture();plan=args['plan']
  plan.update(all_k_combination_count=786431,necessary_bound_excluded_combination_count=1331,planned_canonical_task_count=2355300)
  plan['cardinalities']=[dict(k=k,combination_count=2,necessary_bound_certificates=[]) for k in range(1,20)]
  docs['plan']=dict(complete_observed_provenance_and_missing={'all101':'retained'},preserved_evidence_sidecar_reference={'original':'whole'},preserved_incremental_evidence_sidecar_reference={'increment':'whole'})
  sources={'synthetic':'a'*64};reused=m.reused_reference(docs)
  value=dict(schema='SOURCE_BOUND_NEW_CUTOFF_MULTIK_MATERIALIZATION_V1',scope='CONDITIONAL_RESEARCH_BOUNDED_PREFIX_BATCH_NOT_SEARCH_SELECTION',new_materializations=args['materializations'],reused_completed_reference=reused,input_references={k:m.ref(k) for k in m.BOUND},source_hashes=sources,complete_cardinalities=deepcopy(plan['cardinalities']),all_k_combination_count=786431,necessary_bound_excluded_combination_count=1331,full_pool_planned_task_count=2355300,new_combination_count=31,new_task_count=93,externally_completed_combination_count=1,externally_completed_task_count=3,batch_combination_count=32,batch_task_count=96,new_completed_task_count=0,materializer_invocation_count=16,enumerated_combination_count=31,actual_fitter_invocation_count=0,selection_rule='FIRST_TWO_PREFIX_RANKS_PER_K_4_THROUGH_19_FIXED_WITHOUT_SCORES',**deepcopy(docs['plan']),score_filtering_performed=False,completed_combination_resliced=False,**dict.fromkeys(m.FALSE,False))
  projected=dict(plan=plan,panel=args['panel'],expected_fitter_source_hashes=args['expected_fitter_source_hashes'])
  with patch.object(m.single,'project',return_value=projected),patch.object(m,'producer_sources',return_value=sources),patch.object(m.batch,'verify_slices',return_value={'status':'synthetic'}) as verify:
   self.assertEqual(m.verify_document(value,{**dict.fromkeys(m.single.BOUND,{}),**docs})[0],{'status':'synthetic'});self.assertEqual(verify.call_count,1)
   for field,replacement in [('new_task_count',96),('full_pool_planned_task_count',96),('new_completed_task_count',False),('complete_cardinalities',[]),('preserved_evidence_sidecar_reference',{}),('source_hashes',{}),('all_plan_tasks_completed',True)]:
    changed=deepcopy(value);changed[field]=replacement
    with self.subTest(field=field),self.assertRaises(ValueError):m.verify_document(changed,{**dict.fromkeys(m.single.BOUND,{}),**docs})
   self.assertEqual(verify.call_count,1)
 def test_complete_external_rows_preserved_without_audits(self):
  _,docs=documents_fixture();r=m.reused_reference(docs)
  self.assertEqual(r['completed_tasks'],docs['completed_index']['completed_tasks']);self.assertIsNot(r['completed_tasks'],docs['completed_index']['completed_tasks'])
  self.assertEqual(len(r),6)
 def test_external_coordinate_pointer_counts_and_identity_attacks(self):
  for attack in ('prior','pointer','count','evidence','issuer','authority'):
   _,d=documents_fixture();index=d['completed_index'];row=index['completed_tasks'][0]
   if attack=='prior':row['full_task']['numerical_identity']['requested_previous_target_weights']={'EXIT':.5}
   elif attack=='pointer':row['task_reference']['json_pointer']='/materialization/combinations/0/tasks/1'
   elif attack=='count':index['completed_combination_count']=True
   elif attack=='evidence':row['raw_reference']['path']='other/raw.json'
   elif attack=='issuer':next(iter(row['targets'].values()))['issuer_id']='OTHER'
   else:index['full_shard_completed']=True
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.reused_reference(d)
 def test_pending_anchors_prevent_any_read(self):
  with patch.object(m,'PRODUCER_SHA',None),patch.object(m,'guard') as guard:
   with self.assertRaises(ValueError):m.build()
   guard.assert_not_called()
 def test_guard_conflict_and_existing_final_prevent_work(self):
  a={'source':'a'*64}
  with self.assertRaises(ValueError):m.merge(a,{'source':'b'*64})
  with tempfile.TemporaryDirectory() as tmp:
   output=Path(tmp)/'independent_readback.json';output.write_text('{}')
   with patch.object(m,'OUTPUT',output),patch.object(m,'build') as build:
    with self.assertRaises(ValueError):m.publish()
    build.assert_not_called()

if __name__=='__main__':unittest.main()
