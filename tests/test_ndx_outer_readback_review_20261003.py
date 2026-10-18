from copy import deepcopy
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import test_ndx_outer_lane_refit_independent_readback_20261003 as f
from backtest import ndx_outer_refit_result_inspection_research as numeric

m=f.m

class Review(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prepared,cls.contract=f.fixture()
        cls.rows=f.prep.resolve_adjacent_refit_priors(prepared=cls.prepared,prior_evidence=[],receipt_contract=cls.contract)['rows']
        cls.request=cls.rows[4]['outer_request'];cls.fitter=cls.prepared['fitter_contract_preserved']
        source=f.source_fixture()
        cls.args=dict(selection=source['selection']['document'],history=source['history']['document'],channels={b['coordinate']['security_id']:b for b in source['channel_bindings']},fitter=cls.fitter,refs=dict(selection=source['selection']['reference'],history=source['history']['reference'],fitter=cls.fitter['reference']))
    def inspect(self,e,original=None):
        return m.inspect_envelope(request=e['request'],raw=e['raw_result'],post=e['postcheck'],refs=e['references'],fitter=self.fitter,arithmetic=numeric.inspect_saved_outer_result,original=original)

    def test_full_source_reconstruction_rejects_resigned_offset_and_prior(self):
        m.inspect_request(self.request,**self.args)
        for attack in ('offset','bool','ticker','foreign_lane'):
            q=deepcopy(self.request);a=deepcopy(self.args)
            if attack=='offset':a['channels'][sorted(q['numerical_identity']['selected'])[0]]['channel']['decisions'][0]['price_index_start']+=1
            if attack=='bool':q['source_slot_evidence'][0]['return_index_start']=True
            if attack=='ticker':q['fit_matrix']['tickers'].reverse()
            if attack=='foreign_lane':q['coordinate'][2]='FOREIGN'
            q['content_sha256']=m.sha(m.enc({k:v for k,v in q.items() if k!='content_sha256'}))
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.inspect_request(q,**a)

    def test_tolerance_and_false_flags_do_not_become_success(self):
        q=deepcopy(self.request);q['numerical_identity']['weight_spec']='constrained_fixed_shrinkage'
        q['numerical_task_id']=m.sha(m.enc(q['numerical_identity']))
        e=f.evidence(q,self.fitter,self.contract)
        for target in e['raw_result']['result']['targets'].values():target['target_weight']+=1e-10
        e['postcheck'].update(outcome='VALIDATION_FAILURE',error={'message':'prior tolerance'})
        result=self.inspect(e);self.assertTrue(result['declared_risks_passed']);self.assertFalse(result['next_prior_simplex_eligible'])
        for outcome in ('REFIT_RISK_FAILED','REFIT_PASSED_PENDING_INDEPENDENT_READBACK'):
            bad=deepcopy(e);bad['postcheck'].update(outcome=outcome,error=None)
            with self.subTest(outcome=outcome),self.assertRaises(ValueError):self.inspect(bad)
        e=f.evidence(self.request,self.fitter,self.contract);e['raw_result']['promotion_allowed']=0
        with self.assertRaises(ValueError):self.inspect(e)

    def test_reuse_cannot_relabel_original_raw_or_invent_call(self):
        from test_ndx_outer_prior_evidence_review_20261003 import reused
        origin=f.evidence(self.request,self.fitter,self.contract);origin['readback']['status']='PASS'
        e=reused(origin,self.rows[5]['outer_request'],self.fitter,self.contract)
        e['postcheck']['numerical_reuse_evidence_references']=deepcopy(origin['references'])
        self.inspect(e,origin)
        for attack in ('location','call','alias','matrix'):
            bad,old=deepcopy(e),deepcopy(origin)
            if attack=='location':bad['raw_result']['location_id']=bad['request']['location_id']
            if attack=='call':bad['postcheck']['current_location_returned_call_count']=1
            if attack=='alias':old['postcheck']['outcome']='REUSED_AUDITED_NUMERICAL_RESULT'
            if attack=='matrix':bad['request']['fit_matrix']['returns'][0][0]+=.1
            with self.subTest(attack=attack),self.assertRaises(ValueError):self.inspect(bad,old)

    def test_physical_start_inventory_and_failed_namespace_never_pass(self):
        helper=f.Tests();helper.prepared=self.prepared;helper.contract=self.contract
        helper.out={'rows':self.rows};helper.request=self.request
        helper.e=f.evidence(self.request,self.fitter,self.contract)
        helper.arithmetic=numeric.inspect_saved_outer_result
        for attack in ('started_runtime','truncate_all','failure'):
            with tempfile.TemporaryDirectory() as folder:
                parent,output,postref,context,numericdir=helper.physical(Path(folder))
                postpath=Path(postref['path']);post=m.loads(postpath.read_bytes())
                startpath=numericdir/'started.json';start=m.loads(startpath.read_bytes())
                if attack=='started_runtime':
                    start['runtime_versions']['numpy']='FOREIGN';startpath.write_bytes(m.enc(start))
                if attack=='truncate_all':
                    rawpath=numericdir/'raw_result.json';raw=m.loads(rawpath.read_bytes())
                    for doc in (start,raw,post):doc['coordinate_inventory'].pop()
                    startpath.write_bytes(m.enc(start));rawbytes=m.enc(raw);rawpath.write_bytes(rawbytes)
                    post['raw_result_reference']['sha256']=m.sha(rawbytes);post['source_hashes'][str(rawpath)]=m.sha(rawbytes)
                    postbytes=m.enc(post);postpath.write_bytes(postbytes);postref=m.reference(postpath,m.sha(postbytes))
                if attack=='failure':(postpath.parent/'failure.json').write_bytes(b'{"status":"FAILED_NO_RETRY"}')
                with patch.object(m,'PARENT',parent),patch.object(m,'OUTPUT',output),patch.object(m,'PRODUCER_SHA','f'*64),patch.object(m,'load_inputs',return_value=context):
                    if attack=='failure':
                        report=m.loads(Path(m.readback(postref,execute=True)['path']).read_bytes())
                        self.assertNotEqual(report['status'],'PASS');self.assertFalse(report['prior_eligible'])
                    else:
                        with self.subTest(attack=attack),self.assertRaises(ValueError):m.readback(postref,execute=True)

if __name__=='__main__':unittest.main()
