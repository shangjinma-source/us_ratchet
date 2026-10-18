"""Synthetic started/raw envelopes; no real attempt or fitter invocation."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_orly_single_task_independent_readback_20260925 as m
spec=importlib.util.spec_from_file_location('fit_fixture',Path(__file__).with_name('test_ndx_single_task_raw_readback_research.py'))
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)


def case():
 c=f.case();state=dict(queue_reference=m.ref('queue'),queue_audit_reference=m.ref('audit'),rebinding_reference=m.ref('rebinding'),rebinding_audit_reference=m.ref('rebinding_audit'),task_reference=dict(m.ref('queue'),json_pointer='/new_materializations/0/combinations/0/tasks/0'),task=c['task'],combination_identity={k:v for k,v in c['combination'].items() if k!='tasks'},input_references={k:m.ref(k) for k in m.BOUND},source_hashes={'synthetic':'f'*64},runtime={'synthetic':'runtime'})
 started=dict(schema='NEW_CUTOFF_ORLY_SINGLE_TASK_STARTED_V1',**deepcopy(state),planned_operation_counts=m.counts(state['task']),**dict.fromkeys(m.FALSE,False))
 sr=dict(path=str(Path(__file__).resolve().parent/'started.json'),sha256='a'*64)
 raw=dict(schema='NEW_CUTOFF_ORLY_SINGLE_TASK_RAW_V1',started_reference=sr,numerical_task_id=state['task']['numerical_task_id'],status='FIT_RETURNED',operation_counts=m.counts(state['task']),fitted=c['fitted'],error=None,returned_fit_count=1,internal_optimizer_call_count=None,source_hashes=state['source_hashes'],runtime=state['runtime'],**dict.fromkeys(m.FALSE,False))
 return dict(started=started,raw=raw,state=state,started_reference=sr,numerical_sources=c['numerical_sources'])


def authorized_fixture():
 spec=importlib.util.spec_from_file_location('large_synthetic',Path(__file__).with_name('test_ndx_multik_materialization_independent_readback_research.py'));large=importlib.util.module_from_spec(spec);spec.loader.exec_module(large);a=large.fixture()
 universe=deepcopy(a['panel']['universe'])+[dict(security_id='S_BKNG',ticker='BKNG',issuer_id='I97',risk_chain='travel_hospitality'),dict(security_id='S_CPRT',ticker='CPRT',issuer_id='I98',risk_chain='automotive'),dict(security_id=m.ORLY,ticker='ORLY',issuer_id='I99',risk_chain='automotive')]
 lookup={r['security_id']:r for r in universe};groups=deepcopy(a['plan']['canonical_groups'])+[dict(issuer_id='I97',security_ids=['S_BKNG']),dict(issuer_id='I98',security_ids=['S_CPRT']),dict(issuer_id='I99',security_ids=[m.ORLY])]
 frame=m.pd.DataFrame([row+[.021,.022,.023] for row in a['panel']['returns']],index=m.pd.to_datetime(a['panel']['dates']),columns=a['panel']['columns']+['BKNG','CPRT','ORLY']);values=[];selections=[];ids=[];locations=[]
 for k in range(4,21):
  for local in range(2):
   prefix=[g['security_ids'][0] for g in groups[:k-1]]+[m.ORLY]
   if local:
    if k==22:prefix[0]='S00B'
    else:prefix[-2]=groups[k-1]['security_ids'][0]
   rank=10*k+local;selected={sid:{key:lookup[sid][key] for key in ('ticker','issuer_id','risk_chain')} for sid in sorted(prefix)};tickers=[v['ticker'] for v in selected.values()]
   matrix=dict(dates=a['panel']['dates'],tickers=tickers,returns=frame[tickers].values.tolist());matrix_hash=m.pure.digest(matrix);tasks=[];shard=m.pure.digest(('shard',k))
   for index,weight in enumerate(('equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor')):
    numerical=dict(schema='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1',cutoff=a['panel']['dates'][-1],holding_count=k,selected=selected,weight_spec=weight,parameters=a['plan']['context']['parameters'],requested_previous_target_weights=None,fit_data_sha256=matrix_hash,fitter_source_fingerprint=m.pure.digest(a['expected_fitter_source_hashes']))
    location=dict(schema='ISSUER_PREFIX_TASK_LOCATION_IDENTITY_V1',plan_reference=m.ref('plan'),plan_id=a['plan']['plan_id'],shard_id=shard,k=k,rank=rank,spec_index=index,weight_spec=weight)
    task=dict(numerical_identity=numerical,numerical_task_id=m.pure.digest(numerical),location_identity=location,location_id=m.pure.digest(location),status='MATERIALIZED_NOT_ATTEMPTED',wrapper_call_attempt_count=0,fit_performed=False,anchor_alias_equivalence_verified=False,expected_fitter_previous_target_weights={});tasks.append(task);ids.append(task['numerical_task_id']);locations.append(task['location_id'])
   combo=dict(k=k,rank=rank,prefix_security_ids=prefix,fit_matrix=matrix,fit_data_sha256=matrix_hash,tasks=tasks)
   values.append(dict(k=k,start=rank,stop=rank+1,combination_count=1,materialized_task_count=3,completed_task_count=0,plan_reference=m.ref('plan'),panel_reference=m.ref('panel'),fitter_source_hashes=a['expected_fitter_source_hashes'],shard_id=shard,plan_id=a['plan']['plan_id'],status='MATERIALIZED_NOT_ATTEMPTED',fit_performed=False,full_shard_completed=False,all_plan_tasks_completed=False,combinations=[combo],panel_content_sha256='c'*64))
   selections.append(dict(k=k,forced_local_rank=local,full_rank=rank,prefix_security_ids=prefix,shard_id=shard))
 oldids=[m.pure.digest(('old',i)) for i in range(300)]
 queue=dict(schema='NEW_CUTOFF_ORLY_COMBINATION_MATERIALIZATION_V1',new_combination_count=34,new_task_count=102,external_completed_task_count=300,new_completed_task_count=0,actual_fitter_invocation_count=0,full_plan_task_denominator=18868155,forced_sid=m.ORLY,new_materializations=values,selections=selections,reused_completed_reference=dict(rebinding_reference=m.ref('rebinding'),independent_readback_reference=m.ref('rebinding_audit'),numerical_task_ids=oldids),**dict.fromkeys(('fit_performed','full_shard_completed','all_plan_tasks_completed','old_completed_tasks_rematerialized','promotion_allowed','execution_authorized'),False))
 audit=dict(schema='NEW_CUTOFF_ORLY_COMBINATION_INDEPENDENT_READBACK_V1',status='PASSED',candidate_reference=m.ref('queue'),independent_readback_count=1,actual_fitter_invocation_count=0,new_task_count=102,new_combination_count=34,verified_numerical_task_ids=ids,verified_location_ids=locations)
 rebound=dict(schema='NEW_CUTOFF_V5_COMPLETED_TASK_REBINDING_V1',input_references={'plan':m.ref('plan')},rows=[{'numerical_task_id':tid} for tid in oldids])
 previous=dict(status='PASSED',candidate_reference=m.ref('rebinding'),numerical_contracts_unchanged=True,verified_numerical_task_ids=oldids)
 plan=deepcopy(a['plan']);plan['canonical_groups']=groups;plan['fitter_source_hashes']=a['expected_fitter_source_hashes']
 panel=dict(schema='LATEST_CONDITIONAL_TYPED_PANEL_V5',conditional_security_count=23,conditional_issuer_count=22,panel_content_sha256='c'*64,returns=frame,universe=m.pd.DataFrame(universe),**dict.fromkeys(m.codec.PANEL_FALSE,False))
 outer=dict(plan=plan,complete_observed_provenance_and_missing=[{'synthetic':'all101'}])
 keys=('preserved_evidence_sidecar_reference','preserved_incremental_evidence_sidecar_reference','preserved_v3_incremental_evidence_sidecar_reference','preserved_v4_incremental_evidence_sidecar_reference','preserved_v5_incremental_evidence_sidecar_reference')
 for key in keys:outer[key]={'synthetic_pointer':key}
 queue['complete_observed_provenance_and_missing']=deepcopy(outer['complete_observed_provenance_and_missing']);queue['preserved_sidecar_references']=[deepcopy(outer[key]) for key in keys]
 return dict(queue=queue,audit=audit,rebinding=rebound,rebinding_audit=previous,panel={'panel':{}},plan=outer),panel,ids[7]


class Tests(unittest.TestCase):
 def test_five_sidecars_and_complete_gap_binding_before_decode(self):
  for key in ('complete_observed_provenance_and_missing','preserved_sidecar_references'):
   docs,panel,tid=authorized_fixture();docs['queue'][key]=[]
   with self.subTest(key=key),patch.object(m.codec,'decode_frames') as decode:
    with self.assertRaises(ValueError):m.expected_state(docs,tid)
    decode.assert_not_called()
 def test_six_saved_parent_anchors_bytes_only(self):
  for role in m.BOUND:
   r=m.ref(role);self.assertEqual(m.codec.sha(Path(r['path']).read_bytes()),r['sha256'],role)
 def test_complete102_authorization_and_old300_exclusion(self):
  docs,panel,task=authorized_fixture()
  with patch.object(m.codec,'decode_frames',return_value=panel):
   state=m.expected_state(docs,task);self.assertEqual(state['task_reference']['json_pointer'],'/new_materializations/2/combinations/0/tasks/1');self.assertEqual(state['task']['numerical_identity']['holding_count'],5)
   with self.assertRaises(ValueError):m.expected_state(docs,docs['rebinding']['rows'][0]['numerical_task_id'])
 def test_unsigned_task_self_rehash_matrix_scope_and_partial_input(self):
  for attack in ('target','count','partial','unselected','matrix','audit','prior'):
   docs,panel,tid=authorized_fixture()
   if attack=='target':docs['queue']['new_materializations'][0]['combinations'][0]['prefix_security_ids'].pop()
   elif attack=='count':docs['queue']['new_task_count']=198
   elif attack=='partial':docs['queue']['new_materializations'].pop()
   elif attack=='unselected':
    task=docs['queue']['new_materializations'][-1]['combinations'][0]['tasks'][0];task['location_identity']['spec_index']=False;task['location_id']=m.pure.digest(task['location_identity'])
   elif attack=='matrix':panel['returns'].iloc[0,0]=.9
   elif attack=='audit':docs['audit']['verified_location_ids'].reverse()
   else:docs['plan']['plan']['context']['previous_target_weights']={}
   with self.subTest(attack=attack),patch.object(m.codec,'decode_frames',return_value=panel),self.assertRaises(ValueError):m.expected_state(docs,tid)
 def test_complete_saved_equal_envelope(self):
  r=m.inspect_envelopes(**case());self.assertEqual(r['status'],'FITTED_FIVE_RISKS_PASSED')
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
  post=dict(schema='NEW_CUTOFF_ORLY_SINGLE_TASK_POSTCHECK_V1',status='NUMERICAL_OR_VALIDATION_FAILURE',started_reference=c['started_reference'],raw_reference=rr,numerical_task_id=c['state']['task']['numerical_task_id'],checks=None,error={'type':'ValueError','message':'runtime changed'},**dict.fromkeys(m.FALSE,False))
  m.validate_postcheck(post,c['started_reference'],rr,c['state']['task']['numerical_task_id'],detail)
  self.assertEqual(m.summary_status(detail,post),'VALIDATION_FAILURE_RECORDED');self.assertEqual(detail['status'],'FITTED_FIVE_RISKS_PASSED')
 def test_numerical_exception_postcheck_not_mislabeled_validation_failure(self):
  c=case();c['raw'].update(status='FIT_EXCEPTION',fitted=None,error=dict(type='ValueError',message='optimizer failed'),returned_fit_count=0)
  detail=m.inspect_envelopes(**c);post=dict(error=deepcopy(detail['error']))
  self.assertEqual(m.summary_status(detail,post),'NUMERICAL_EXCEPTION_NO_RETURNED_FIT')
  post['error']=dict(type='ValueError',message='source drift during postflight')
  self.assertEqual(m.summary_status(detail,post),'VALIDATION_FAILURE_RECORDED')
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
