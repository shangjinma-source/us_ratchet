"""Synthetic started/raw envelopes; no real attempt or fitter invocation."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_multik_single_task_independent_readback_20260924 as m
spec=importlib.util.spec_from_file_location('fit_fixture',Path(__file__).with_name('test_ndx_single_task_raw_readback_research.py'))
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)


def case(**fit_arguments):
 c=f.case(**fit_arguments);state=dict(queue_reference=m.ref('queue'),queue_audit_reference=m.ref('audit'),completed_index_reference=m.ref('completed_index'),task_reference=dict(m.ref('queue'),json_pointer='/new_materializations/0/combinations/0/tasks/0'),task=c['task'],combination_identity={k:v for k,v in c['combination'].items() if k!='tasks'},input_references={k:m.ref(k) for k in m.BOUND},source_hashes={'synthetic':'f'*64},runtime={'synthetic':'runtime'})
 started=dict(schema='NEW_CUTOFF_MULTIK_SINGLE_TASK_STARTED_V1',**deepcopy(state),planned_operation_counts=m.counts(state['task']),**dict.fromkeys(m.FALSE,False))
 sr=dict(path=str(Path(__file__).resolve().parent/'started.json'),sha256='a'*64)
 raw=dict(schema='NEW_CUTOFF_MULTIK_SINGLE_TASK_RAW_V1',started_reference=sr,numerical_task_id=state['task']['numerical_task_id'],status='FIT_RETURNED',operation_counts=m.counts(state['task']),fitted=c['fitted'],error=None,returned_fit_count=1,internal_optimizer_call_count=None,source_hashes=state['source_hashes'],runtime=state['runtime'],**dict.fromkeys(m.FALSE,False))
 return dict(started=started,raw=raw,state=state,started_reference=sr,numerical_sources=c['numerical_sources'])


def authorized_fixture():
 spec=importlib.util.spec_from_file_location('multik_fixture',Path(__file__).with_name('test_ndx_multik_materialization_independent_readback_research.py'))
 fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures);a=fixtures.fixture()
 values=a['materializations']
 for value in values:
  value['plan_reference']=m.ref('plan');value['panel_reference']=m.ref('panel')
  for combo in value['combinations']:
   for task in combo['tasks']:
    task['location_identity']['plan_reference']=m.ref('plan');task['location_id']=m.pure.digest(task['location_identity'])
 old=[dict(numerical_task_id=v) for v in a['completed_task_ids']]
 index=dict(schema='NEW_CUTOFF_COMPLETED_TASK_INDEX_V1',completed_task_count=3,completed_tasks=old,source_hashes={})
 queue=dict(schema='SOURCE_BOUND_NEW_CUTOFF_MULTIK_MATERIALIZATION_V1',new_materializations=values,reused_completed_reference=dict(completed_index_reference=m.ref('completed_index'),numerical_task_ids=a['completed_task_ids'],completed_tasks=old),new_combination_count=31,new_task_count=93,externally_completed_task_count=3,batch_task_count=96,new_completed_task_count=0,actual_fitter_invocation_count=0,full_pool_planned_task_count=2355300,**dict.fromkeys(('fit_performed','full_shard_completed','all_plan_tasks_completed','completed_combination_resliced','promotion_allowed','execution_authorized'),False))
 audit=dict(schema='NEW_CUTOFF_MULTIK_MATERIALIZATION_INDEPENDENT_READBACK_V1',status='PASSED',candidate_reference=m.ref('queue'),independent_batch_readback_count=1,actual_fitter_invocation_count=0)
 panel=dict(schema='LATEST_CONDITIONAL_TYPED_PANEL_V2',panel_content_sha256=values[0]['panel_content_sha256'],returns=m.pd.DataFrame(a['panel']['returns'],index=m.pd.to_datetime(a['panel']['dates']),columns=a['panel']['columns']),universe=m.pd.DataFrame(a['panel']['universe']),**dict.fromkeys(m.codec.PANEL_FALSE,False))
 docs=dict(queue=queue,audit=audit,completed_index=index,panel={'panel':{}},plan={'plan':a['plan']})
 return docs,panel,values[1]['combinations'][1]['tasks'][2]['numerical_task_id']


class Tests(unittest.TestCase):
 def test_queue_pointer_fullmatrix_and_old_exclusion(self):
  docs,panel,task_id=authorized_fixture()
  with patch.object(m.codec,'decode_frames',return_value=panel):
   state=m.expected_state(docs,task_id)
   self.assertEqual(state['task_reference']['json_pointer'],'/new_materializations/1/combinations/1/tasks/2')
   self.assertEqual(state['task']['numerical_identity']['holding_count'],5)
   with self.assertRaises(ValueError):m.expected_state(docs,docs['completed_index']['completed_tasks'][0]['numerical_task_id'])
   for attack in ('matrix','source','prior','partial','location'):
    d=deepcopy(docs);v=d['queue']['new_materializations'][1];t=v['combinations'][1]['tasks'][2]
    if attack=='matrix':v['combinations'][1]['fit_matrix']['returns'][0][0]=.7
    elif attack=='source':v['fitter_source_hashes']={}
    elif attack=='prior':d['plan']['plan']['context']['previous_target_weights']={'EXIT':1.}
    elif attack=='partial':d['queue']['new_materializations'].pop()
    else:t['location_identity']['rank']=0;t['location_id']=m.pure.digest(t['location_identity'])
    with self.subTest(attack=attack),self.assertRaises(ValueError):m.expected_state(d,task_id)
 def test_complete_saved_equal_envelope(self):
  r=m.inspect_envelopes(**case());self.assertEqual(r['status'],'FITTED_FIVE_RISKS_PASSED')
 def test_saved_original_risk_failure_is_not_numerical_exception(self):
  result=m.inspect_envelopes(**case(weight_spec='constrained_fixed_shrinkage',weights={'a':.8,'b':.1,'m':.05,'z1':.05}))
  self.assertEqual(result['status'],'FITTED_FIVE_RISKS_FAILED');self.assertFalse(result['checks']['MAX_SINGLE_WEIGHT'])
 def test_equal_k5_k19_binary_fraction_and_variable_neff(self):
  for k in (5,19):
   docs,panel,_=authorized_fixture();combo=docs['queue']['new_materializations'][k-4]['combinations'][0];task=combo['tasks'][0]
   with patch.object(m.codec,'decode_frames',return_value=panel):state=m.expected_state(docs,task['numerical_task_id'])
   c=case();fit=c['raw']['fitted'];selected=task['numerical_identity']['selected'];weight=1./k;p=task['numerical_identity']['parameters'];groups={}
   for sid in sorted(selected):groups[selected[sid]['risk_chain']]=groups.get(selected[sid]['risk_chain'],0.)+weight
   checks=dict(MAX_SINGLE_WEIGHT=weight<=p['max_single_weight']+1e-9,MIN_SINGLE_WEIGHT=weight>=p['min_single_weight']-1e-9,SECURITY_TOP3_WEIGHT=sum([weight]*3)<=p['top_weight_cap']+1e-9,MINIMUM_EFFECTIVE_N=1./sum(weight*weight for _ in range(k))>=k*p['minimum_effective_n_ratio']-1e-9,RISK_CHAIN_TOP1_WEIGHT=max(groups.values())<=p['risk_chain_top1_cap']+1e-9)
   fit.update(targets={s:dict(ticker=v['ticker'],issuer_id=v['issuer_id'],target_weight=weight) for s,v in selected.items()},fit_data_sha256=combo['fit_data_sha256'],risk_chains_by_security={s:v['risk_chain'] for s,v in selected.items()},anchor_by_security={s:0. for s in selected},declared_constraint_checks=checks,declared_constraints_passed=all(checks.values()))
   c.update(state=state,started=dict(schema='NEW_CUTOFF_MULTIK_SINGLE_TASK_STARTED_V1',**deepcopy(state),planned_operation_counts=m.counts(task),**dict.fromkeys(m.FALSE,False)))
   c['raw'].update(numerical_task_id=task['numerical_task_id'],source_hashes=state['source_hashes'],runtime=state['runtime'])
   self.assertEqual(m.inspect_envelopes(**c)['checks'],checks)
   fit['targets'][next(iter(selected))]['target_weight']=round(weight,5)
   if round(weight,5)!=weight:
    with self.assertRaises(ValueError):m.inspect_envelopes(**c)
 def test_unselected_task_digest_spec_and_location_must_hold(self):
  for attack in ('digest','spec','location','duplicate'):
   docs,panel,task_id=authorized_fixture();tasks=docs['queue']['new_materializations'][-1]['combinations'][0]['tasks'];task=tasks[0]
   if attack=='digest':task['numerical_identity']['requested_previous_target_weights']={'EXIT':1.}
   elif attack=='spec':tasks.reverse()
   elif attack=='location':task['location_identity']['spec_index']=False;task['location_id']=m.pure.digest(task['location_identity'])
   else:tasks[1]=deepcopy(task)
   with self.subTest(attack=attack),patch.object(m.codec,'decode_frames',return_value=panel),self.assertRaises(ValueError):m.expected_state(docs,task_id)
 def test_exception_does_not_imply_economic_failure_or_optimizer_zero(self):
  c=case();c['raw'].update(status='FIT_EXCEPTION',fitted=None,error={'type':'ValueError','message':'source changed in finally'},returned_fit_count=0)
  r=m.inspect_envelopes(**c);self.assertEqual(r['status'],'NUMERICAL_EXCEPTION_NO_RETURNED_FIT');self.assertIsNone(r['checks']);self.assertTrue(r['optimizer_call_count_unknown'])
 def test_self_signed_started_does_not_authorize_task(self):
  for attack in ('task','matrix','runtime','source','rawcount','internalcalls'):
   c=case()
   if attack=='task':c['started']['task']['numerical_identity']['selected']['a']['issuer_id']='OTHER'
   elif attack=='matrix':c['started']['combination_identity']['fit_matrix']['returns'][0][0]=.9
   elif attack=='runtime':c['started']['runtime']={'synthetic':'changed'}
   elif attack=='source':c['raw']['source_hashes']={}
   elif attack=='rawcount':c['raw']['returned_fit_count']=True
   else:c['raw']['internal_optimizer_call_count']=0
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.inspect_envelopes(**c)
 def test_postcheck_validation_failure_cannot_be_top_level_fit_pass(self):
  c=case();detail=m.inspect_envelopes(**c);rr=dict(path='synthetic/raw.json',sha256='b'*64)
  post=dict(schema='NEW_CUTOFF_MULTIK_SINGLE_TASK_POSTCHECK_V1',status='NUMERICAL_OR_VALIDATION_FAILURE',started_reference=c['started_reference'],raw_reference=rr,numerical_task_id=c['state']['task']['numerical_task_id'],checks=None,error={'type':'ValueError','message':'runtime changed'},**dict.fromkeys(m.FALSE,False))
  m.validate_postcheck(post,c['started_reference'],rr,c['state']['task']['numerical_task_id'],detail)
  self.assertEqual(m.summary_status(detail,post),'VALIDATION_FAILURE_RECORDED');self.assertEqual(detail['status'],'FITTED_FIVE_RISKS_PASSED')
 def test_started_without_raw_no_retry_and_external_hash_required(self):
  with tempfile.TemporaryDirectory() as tmp:
   task='a'*64;folder=Path(tmp)/task;folder.mkdir();(folder/'started.json').write_text('{}')
   with patch.object(m,'OUTPUT_ROOT',Path(tmp)),patch.object(m,'guard',side_effect=AssertionError('should reject before any source read')):
    with self.assertRaisesRegex(ValueError,'without raw'):m.build(task,'b'*64,'c'*64)
    with self.assertRaises(ValueError):m.build(task,'','c'*64)
   self.assertEqual({p.name for p in folder.iterdir()},{'started.json'})
 def test_existing_finalization_refuses_before_build(self):
  with tempfile.TemporaryDirectory() as tmp:
   task='a'*64;folder=Path(tmp)/task;folder.mkdir();(folder/'independent_readback.json').write_text('{}')
   with patch.object(m,'OUTPUT_ROOT',Path(tmp)),patch.object(m,'build') as build:
    with self.assertRaises(ValueError):m.finalize(task,'b'*64,'c'*64)
    build.assert_not_called()

if __name__=='__main__':unittest.main()
