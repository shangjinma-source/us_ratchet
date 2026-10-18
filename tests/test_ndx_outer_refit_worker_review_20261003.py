import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_ndx_outer_lane_refit_worker_20261003 as author
import test_ndx_outer_lane_refit_evidence_research as f

m=author.m

class Review(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prepared,cls.contract=f.fixture();cls.fitter=cls.prepared['fitter_contract_preserved']
        cls.rows=f.m.resolve_adjacent_refit_priors(prepared=cls.prepared,prior_evidence=[],receipt_contract=cls.contract)['rows']
        cls.request=cls.rows[4]['outer_request']
    def context(self):return dict(fitter=self.fitter,evidence=f.m,inspector=author.inspector,receipt_contract=self.contract)

    def test_runtime_drift_after_return_preserves_raw_before_validation(self):
        body=f.evidence(self.request,self.fitter,self.contract)['raw_result']['result']
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);state={'returned':False}
            def dispatch(*args):state['returned']=True;return body
            def runtime():return dict(self.fitter['runtime_versions'],numpy='changed') if state['returned'] else self.fitter['runtime_versions']
            with patch.object(m,'environment',return_value=self.fitter['required_worker_environment']),patch.object(m,'runtime',side_effect=runtime),patch.object(m,'guard'),patch.object(m,'space'),patch.object(m,'_dispatch',side_effect=dispatch) as call:
                r=m.execute_new(self.request,self.context(),root/'location',root/'numeric',{})
                self.assertEqual(json.loads(Path(r['path']).read_bytes())['outcome'],'VALIDATION_FAILURE')
                raw=json.loads((root/'numeric/raw_result.json').read_bytes());self.assertEqual(raw['result'],body);self.assertTrue(raw['returned']);self.assertEqual(call.call_count,1)
                with self.assertRaises(ValueError):m.execute_new(self.request,self.context(),root/'location',root/'numeric',{})

    def test_raw_false_claim_and_unrepresentable_return_are_technical(self):
        class Broken:
            def __repr__(self):raise RuntimeError('repr unavailable')
        for value in ({'declared_constraints_passed':False},Broken()):
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder)
                with patch.object(m,'environment',return_value=self.fitter['required_worker_environment']),patch.object(m,'runtime',return_value=self.fitter['runtime_versions']),patch.object(m,'guard'),patch.object(m,'space'),patch.object(m,'_dispatch',return_value=value):
                    r=m.execute_new(self.request,self.context(),root/'location',root/'numeric',{})
                post=json.loads(Path(r['path']).read_bytes());raw=json.loads((root/'numeric/raw_result.json').read_bytes())
                self.assertEqual(post['outcome'],'VALIDATION_FAILURE');self.assertTrue(raw['returned']);self.assertEqual(raw['returned_call_count'],1)
                if type(value)is dict:self.assertEqual(raw['result'],value)
                else:self.assertFalse(raw['original_return_is_json']);self.assertEqual(raw['repr_error']['message'],'repr unavailable')

    def test_reuse_keeps_original_raw_call_and_new_location_zero_calls(self):
        origin=f.evidence(self.request,self.fitter,self.contract);request=self.rows[5]['outer_request']
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);oldrefs=origin['references']
            paths={oldrefs['request']['path']:str((root/'locations'/self.request['location_id']/'request.json').resolve()),oldrefs['raw_result']['path']:str((root/'numerical'/self.request['numerical_task_id']/'raw_result.json').resolve())}
            def replace(x):
                if type(x)is dict:return {paths.get(k,k):replace(v) for k,v in x.items()}
                if type(x)is list:return [replace(v) for v in x]
                return paths.get(x,x) if type(x)is str else x
            origin=replace(origin);before=copy.deepcopy(origin)
            resolved={tuple(r['outer_request']['coordinate']):r['outer_request'] for r in self.rows if r['outer_request']}
            with patch.object(m,'OUTPUT',root),patch.object(m,'guard'),patch.object(m,'space'),patch.object(m,'_dispatch',side_effect=AssertionError('reuse must not dispatch')):
                r=m.execute_reuse(request,self.context(),origin,resolved,root/'locations'/request['location_id'],{})
                post=json.loads(Path(r['path']).read_bytes());self.assertFalse(post['current_location_call_invoked']);self.assertEqual(post['current_location_returned_call_count'],0)
                self.assertEqual(post['raw_result_reference'],origin['references']['raw_result']);self.assertEqual(origin,before)
                self.assertTrue(origin['raw_result']['call_invoked']);self.assertEqual(origin['raw_result']['returned_call_count'],1)
                with self.assertRaises(ValueError):m.execute_reuse(request,self.context(),origin,resolved,root/'locations'/request['location_id'],{})

    def test_returned_simplex_valid_but_next_prior_invalid_is_not_risk_failure(self):
        request=copy.deepcopy(self.request)
        request['numerical_identity']['weight_spec']='constrained_fixed_shrinkage'
        request['numerical_task_id']=f.p.digest(request['numerical_identity'])
        body=f.evidence(request,self.fitter,self.contract)['raw_result']['result']
        for target in body['targets'].values():target['target_weight']+=1e-10
        checked=author.inspector.inspect_saved_outer_result(request=request,result=body,fitter_contract=self.fitter)
        self.assertTrue(checked['declared_risks_passed']);self.assertFalse(checked['next_prior_simplex_eligible'])
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.object(m,'environment',return_value=self.fitter['required_worker_environment']),patch.object(m,'runtime',return_value=self.fitter['runtime_versions']),patch.object(m,'guard'),patch.object(m,'space'),patch.object(m,'_dispatch',return_value=body):
                result=m.execute_new(request,self.context(),root/'location',root/'numeric',{})
            self.assertEqual(json.loads(Path(result['path']).read_bytes())['outcome'],'VALIDATION_FAILURE')
            self.assertEqual(json.loads((root/'numeric/raw_result.json').read_bytes())['result'],body)

    def test_failed_reuse_preserves_unknown_optimizer_and_exact_risk_scope(self):
        e=f.evidence(self.request,self.fitter,self.contract);body=e['raw_result']['result'];ids=sorted(body['targets'])
        weights=[.7,.1,.1,.1];groups={}
        for sid,w in zip(ids,weights):
            body['targets'][sid]['target_weight']=w
            chain=body['risk_chains_by_security'][sid];groups[chain]=groups.get(chain,0.)+w
        body['declared_constraint_checks']=dict(MAX_SINGLE_WEIGHT=False,MIN_SINGLE_WEIGHT=True,SECURITY_TOP3_WEIGHT=False,MINIMUM_EFFECTIVE_N=False,RISK_CHAIN_TOP1_WEIGHT=max(groups.values())<=.55+1e-9)
        body['declared_constraints_passed']=False;e['postcheck']['outcome']='REFIT_RISK_FAILED'
        e['readback'].update(status='PASS_SAVED_RISK_FAILURE',prior_eligible=False,attempt_outcome='REFIT_RISK_FAILED',targets_preserved=copy.deepcopy(body['targets']),raw_result_body_sha256=f.p.digest(body))
        paths={r['path']:str(Path(r['path']).resolve()) for r in list(e['references'].values())+[self.fitter['reference']]}
        def replace(x):
            if type(x)is dict:return {paths.get(k,k):replace(v) for k,v in x.items()}
            if type(x)is list:return [replace(v) for v in x]
            return paths.get(x,x) if type(x)is str else x
        e=replace(e);request=replace(self.request);context=self.context()
        context['fitter']=replace(context['fitter']);context['receipt_contract']=replace(context['receipt_contract'])
        result=m.validate_failed_reuse(e,request,context,{})
        self.assertFalse(result['declared_risks_passed'])
        for attack in ('optimizer','scope','outcome'):
            bad=copy.deepcopy(e)
            if attack=='optimizer':bad['raw_result']['internal_optimizer_call_count']=7
            if attack=='scope':bad['readback']['scope']='UNVERIFIED'
            if attack=='outcome':bad['readback']['attempt_outcome']='REFIT_PASSED_PENDING_INDEPENDENT_READBACK'
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.validate_failed_reuse(bad,request,context,{})

if __name__=='__main__':unittest.main()
