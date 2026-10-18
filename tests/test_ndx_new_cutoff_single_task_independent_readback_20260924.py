"""Synthetic started/raw envelopes; no real attempt or fitter invocation."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_single_task_independent_readback_20260924 as m
spec=importlib.util.spec_from_file_location('fit_fixture',Path(__file__).with_name('test_ndx_single_task_raw_readback_research.py'))
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)


def case():
 c=f.case();state=dict(task=c['task'],combination_identity={k:v for k,v in c['combination'].items() if k!='tasks'},input_references={k:m.ref(k) for k in m.BOUND},source_hashes={'synthetic':'f'*64},runtime={'synthetic':'runtime'})
 started=dict(schema='NEW_CUTOFF_SINGLE_TASK_STARTED_V1',**deepcopy(state),planned_operation_counts=m.counts(state['task']),**dict.fromkeys(m.FALSE,False))
 sr=dict(path=str(Path(__file__).resolve().parent/'started.json'),sha256='a'*64)
 raw=dict(schema='NEW_CUTOFF_SINGLE_TASK_RAW_V1',started_reference=sr,numerical_task_id=state['task']['numerical_task_id'],status='FIT_RETURNED',operation_counts=m.counts(state['task']),fitted=c['fitted'],error=None,returned_fit_count=1,internal_optimizer_call_count=None,source_hashes=state['source_hashes'],runtime=state['runtime'],**dict.fromkeys(m.FALSE,False))
 return dict(started=started,raw=raw,state=state,started_reference=sr,numerical_sources=c['numerical_sources'])


class Tests(unittest.TestCase):
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
  post=dict(schema='NEW_CUTOFF_SINGLE_TASK_POSTCHECK_V1',status='NUMERICAL_OR_VALIDATION_FAILURE',started_reference=c['started_reference'],raw_reference=rr,numerical_task_id=c['state']['task']['numerical_task_id'],checks=None,error={'type':'ValueError','message':'runtime changed'},**dict.fromkeys(m.FALSE,False))
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
