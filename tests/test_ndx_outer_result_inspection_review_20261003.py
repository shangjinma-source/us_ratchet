from copy import deepcopy
import math
import unittest
import test_ndx_outer_lane_refit_evidence_research as f
from backtest import ndx_outer_refit_result_inspection_research as m

class Review(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prepared,cls.contract=f.fixture();cls.fitter=prepared['fitter_contract_preserved']
        cls.request=f.m.resolve_adjacent_refit_priors(prepared=prepared,prior_evidence=[],receipt_contract=cls.contract)['rows'][4]['outer_request']
    def case(self,previous=None):
        request=deepcopy(self.request)
        request['numerical_identity']['weight_spec']='constrained_fixed_shrinkage_turnover_anchor'
        request['numerical_identity']['requested_previous_target_weights']=previous
        request['numerical_task_id']=m.hashlib.sha256(m.encoded(request['numerical_identity'])).hexdigest()
        body=f.evidence(request,self.fitter,self.contract)['raw_result']['result']
        return request,body
    def inspect(self,q,r):return m.inspect_saved_outer_result(request=q,result=r,fitter_contract=self.fitter)

    def test_prior_none_empty_canonical_sid_and_nonoverlap(self):
        q,r=self.case(None);self.assertTrue(self.inspect(q,r)['next_prior_simplex_eligible'])
        q,r=self.case({'OUTSIDE':1.});self.assertEqual(r['effective_anchor_strength'],0.);self.inspect(q,r)
        for prior in ({},{' BAD ':1.},{'':1.},{'OUTSIDE':True}):
            q,r=self.case(prior)
            with self.subTest(prior=prior),self.assertRaises(ValueError):self.inspect(q,r)

    def test_overlap_follows_sid_not_ticker_and_exact_binary64(self):
        sid=sorted(self.request['numerical_identity']['selected'])[0]
        ticker=self.request['numerical_identity']['selected'][sid]['ticker']
        q,r=self.case({sid:.3,'OUTSIDE':.7});self.inspect(q,r)
        self.assertEqual(r['anchor_by_security'][sid],1.)
        wrong=deepcopy(r);wrong['anchor_by_security']={ticker:1.}
        with self.assertRaises(ValueError):self.inspect(q,wrong)
        wrong=deepcopy(r);wrong['surviving_anchor_mass']=math.nextafter(.3,math.inf)
        with self.assertRaises(ValueError):self.inspect(q,wrong)
        q,r=self.case({ticker:1.});self.assertEqual(r['surviving_anchor_mass'],0.);self.inspect(q,r)

    def test_returned_tolerance_separate_from_next_prior_and_honest_failure(self):
        q,r=self.case()
        for v in r['targets'].values():v['target_weight']+=1e-10
        got=self.inspect(q,r);self.assertTrue(got['declared_risks_passed']);self.assertFalse(got['next_prior_simplex_eligible'])
        for v in r['targets'].values():v['target_weight']+=1e-9
        with self.assertRaises(ValueError):self.inspect(q,r)
        q,r=self.case();ids=sorted(r['targets'])
        for sid in ids:q['numerical_identity']['selected'][sid]['risk_chain']='ONE'
        q['numerical_task_id']=m.hashlib.sha256(m.encoded(q['numerical_identity'])).hexdigest()
        r['risk_chains_by_security']={sid:'ONE' for sid in ids}
        r['declared_constraint_checks']['RISK_CHAIN_TOP1_WEIGHT']=False;r['declared_constraints_passed']=False
        self.assertFalse(self.inspect(q,r)['declared_risks_passed'])
        r['declared_constraint_checks']['RISK_CHAIN_TOP1_WEIGHT']=0
        with self.assertRaises(ValueError):self.inspect(q,r)

if __name__=='__main__':unittest.main()
