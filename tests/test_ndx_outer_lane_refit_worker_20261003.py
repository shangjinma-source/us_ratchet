import copy,importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import test_ndx_outer_lane_refit_evidence_research as f
from backtest import ndx_outer_refit_result_inspection_research as inspector
P=Path(__file__).resolve().parents[1]/'scripts/ndx_outer_lane_refit_worker_20261003.py'
spec=importlib.util.spec_from_file_location('outerworker',P);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.prepared,cls.contract=f.fixture();cls.helper=f.m
  cls.resolved=cls.helper.resolve_adjacent_refit_priors(prepared=cls.prepared,prior_evidence=[],receipt_contract=cls.contract)
  cls.request=next(r['outer_request'] for r in cls.resolved['rows'] if r['outer_request'])
 def test_pending_reject_before_source_io(self):
  with patch.dict(m.BOUND,{'selection':(m.BOUND['selection'][0],None)}),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')),patch.object(Path,'exists',side_effect=AssertionError('IO')):
   with self.assertRaisesRegex(ValueError,'Pending'):m.load_common(receipt_contract_reference=m.ref(P,'a'*64))
 def execute(self,root,fn,guard=None):
  fitter=self.prepared['fitter_contract_preserved'];c=dict(fitter=fitter,evidence=self.helper,inspector=inspector)
  with patch.object(m,'environment',return_value=fitter['required_worker_environment']),patch.object(m,'runtime',return_value=fitter['runtime_versions']),patch.object(m,'guard',side_effect=guard or (lambda x:None)),patch.object(m,'space'),patch.object(m,'_dispatch',side_effect=fn):
   return m.execute_new(copy.deepcopy(self.request),c,root/'location',root/'numeric',{})
 def test_raw_before_validate_and_no_retry(self):
  body=f.evidence(self.request,self.prepared['fitter_contract_preserved'],self.contract)['raw_result']['result']
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)
   def run(*args):
    self.assertTrue((root/'numeric/started.json').exists());self.assertFalse((root/'numeric/raw_result.json').exists());return body
   r=self.execute(root,run);post=json.loads(Path(r['path']).read_bytes());self.assertEqual(post['outcome'],'REFIT_PASSED_PENDING_INDEPENDENT_READBACK');self.assertTrue(post['current_location_call_invoked']);self.assertEqual(json.loads((root/'numeric/raw_result.json').read_bytes())['result'],body)
   with self.assertRaisesRegex(ValueError,'retry'):self.execute(root,run)
 def test_exception_none_and_risk_are_distinct(self):
  body=f.evidence(self.request,self.prepared['fitter_contract_preserved'],self.contract)['raw_result']['result']
  for mode in ('exception','none','risk','fake_risk','unserializable','repr_failure'):
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
    def fn(*args):
     if mode=='exception':raise RuntimeError('actual synthetic exception')
     if mode=='none':return None
     if mode=='unserializable':return object()
     if mode=='repr_failure':
      class Broken:
       def __repr__(self):raise ValueError('broken repr')
      return Broken()
     b=copy.deepcopy(body);b['declared_constraints_passed']=False
     if mode=='fake_risk':return b
     sids=sorted(b['targets']);weights=[.7]+[.3/(len(sids)-1)]*(len(sids)-1);groups={}
     for sid,w in zip(sids,weights):
      b['targets'][sid]['target_weight']=w;chain=b['risk_chains_by_security'][sid];groups[chain]=groups.get(chain,0.)+w
     b['declared_constraint_checks']=dict(MAX_SINGLE_WEIGHT=False,MIN_SINGLE_WEIGHT=min(weights)>=.05-1e-9,SECURITY_TOP3_WEIGHT=sum(sorted(weights,reverse=True)[:3])<=.8+1e-9,MINIMUM_EFFECTIVE_N=1./sum(w*w for w in weights)>=len(sids)*.7-1e-9,RISK_CHAIN_TOP1_WEIGHT=max(groups.values())<=.55+1e-9);return b
    root=Path(d);r=self.execute(root,fn);post=json.loads(Path(r['path']).read_bytes());raw=json.loads((root/'numeric/raw_result.json').read_bytes())
    self.assertEqual(post['outcome'],{'exception':'NUMERICAL_EXCEPTION','none':'VALIDATION_FAILURE','risk':'REFIT_RISK_FAILED','unserializable':'VALIDATION_FAILURE','repr_failure':'VALIDATION_FAILURE','fake_risk':'VALIDATION_FAILURE'}[mode]);self.assertEqual(raw['returned_call_count'],0 if mode=='exception' else 1)
    if mode in ('unserializable','repr_failure'):self.assertTrue((root/'numeric/unserializable_return.bin').exists());self.assertFalse(raw['original_return_is_json'])
 def test_post_source_drift_keeps_actual_return(self):
  body=f.evidence(self.request,self.prepared['fitter_contract_preserved'],self.contract)['raw_result']['result']
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)
   def guard(s):
    if (root/'numeric/raw_result.json').exists():raise ValueError('post source drift')
   r=self.execute(root,lambda *a:body,guard);self.assertEqual(json.loads(Path(r['path']).read_bytes())['outcome'],'VALIDATION_FAILURE');self.assertEqual(json.loads((root/'numeric/raw_result.json').read_bytes())['result'],body)
 def check_reuse(self,risk=False):
  request=self.resolved['rows'][5]['outer_request'];first=self.request;fitter=self.prepared['fitter_contract_preserved'];origin=f.evidence(first,fitter,self.contract)
  if risk:
   body=origin['raw_result']['result'];sids=sorted(body['targets']);weights=[.7]+[.3/(len(sids)-1)]*(len(sids)-1);groups={}
   for sid,w in zip(sids,weights):
    body['targets'][sid]['target_weight']=w;chain=body['risk_chains_by_security'][sid];groups[chain]=groups.get(chain,0.)+w
   body['declared_constraints_passed']=False;body['declared_constraint_checks']=dict(MAX_SINGLE_WEIGHT=False,MIN_SINGLE_WEIGHT=min(weights)>=.05-1e-9,SECURITY_TOP3_WEIGHT=sum(sorted(weights,reverse=True)[:3])<=.8+1e-9,MINIMUM_EFFECTIVE_N=1./sum(w*w for w in weights)>=len(sids)*.7-1e-9,RISK_CHAIN_TOP1_WEIGHT=max(groups.values())<=.55+1e-9)
   origin['postcheck']['outcome']='REFIT_RISK_FAILED';origin['readback'].update(status='PASS_SAVED_RISK_FAILURE',prior_eligible=False,attempt_outcome='REFIT_RISK_FAILED',targets_preserved=copy.deepcopy(body['targets']),raw_result_body_sha256=m.sha(m.enc(body)))
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);old=origin['references'];replacements={r['path']:str((root/'references'/k).resolve()) for k,r in old.items()};replacements[fitter['reference']['path']]=str((root/'fitter.json').resolve());replacements.update({old['request']['path']:str((root/'locations'/first['location_id']/'request.json').resolve()),old['raw_result']['path']:str((root/'numerical'/first['numerical_task_id']/'raw_result.json').resolve())})
   def substitute(x):
    if type(x)is str:return replacements.get(x,x)
    if type(x)is list:return [substitute(v) for v in x]
    if type(x)is dict:return {substitute(k):substitute(v) for k,v in x.items()}
    return x
   origin=substitute(origin);request=substitute(request);fitter=substitute(fitter);contract=substitute(self.contract);requests={tuple(r['outer_request']['coordinate']):r['outer_request'] for r in self.resolved['rows'] if r['outer_request']};requests={k:substitute(v) for k,v in requests.items()}
   c=dict(fitter=fitter,evidence=self.helper,receipt_contract=contract,inspector=inspector)
   with patch.object(m,'OUTPUT',root),patch.object(m,'guard'),patch.object(m,'space'),patch.object(m,'_dispatch',side_effect=AssertionError('No second fit')):
    r=m.execute_reuse(request,c,origin,requests,root/'locations'/request['location_id'],{})
   post=json.loads(Path(r['path']).read_bytes());self.assertEqual(post['outcome'],'REUSED_AUDITED_NUMERICAL_RISK_FAILURE' if risk else 'REUSED_AUDITED_NUMERICAL_RESULT');self.assertFalse(post['current_location_call_invoked']);self.assertEqual(post['current_location_returned_call_count'],0);self.assertEqual(post['raw_result_reference'],origin['references']['raw_result']);self.assertFalse((root/'numerical').exists())
 def test_reuse_success_and_honest_failure_never_calls_fitter(self):
  self.check_reuse();self.check_reuse(risk=True)
 def test_complete48_strict_block_is_not_published_evidence(self):
  c=dict(prepared=self.prepared,evidence=self.helper,receipt_contract=self.contract,sources={});handle=dict(handle='synthetic',coordinate_count=48,coordinates=[[r['cutoff'],r['fx_mode'],r['lane']] for r in self.prepared['rows']])
  with patch.dict(m._HANDLES,{'synthetic':c}),patch.object(m,'FRESH_CLI',True),patch.object(m,'environment'),patch.object(m,'guard'),patch.object(m,'execute_new',side_effect=AssertionError('No blocked dispatch')):
   result=m.run_coordinate(0,execute=True,common=handle)
  self.assertEqual(result['coordinate_count'],48);self.assertEqual(sum(result['full_status_counts'].values()),48);self.assertEqual(result['full_status_counts']['SOURCE_BLOCKED'],24);self.assertFalse(result['blocked_evidence_persisted']);self.assertTrue(result['coordinator_required'])
if __name__=='__main__':unittest.main()
