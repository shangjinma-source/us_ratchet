from copy import deepcopy
import math
import unittest
import test_ndx_outer_lane_refit_evidence_research as f

m,p=f.m,f.p

def reused(first,request,fitter,contract):
    other=f.evidence(request,fitter,contract)
    other['numerical_reuse_evidence']=deepcopy(first)
    other['raw_result']=deepcopy(first['raw_result'])
    other['references']['raw_result']=deepcopy(first['references']['raw_result'])
    post=other['postcheck']
    post.update(outcome='REUSED_AUDITED_NUMERICAL_RESULT',current_location_call_invoked=False,current_location_returned_call_count=0,raw_result_reference=first['references']['raw_result'])
    post['source_hashes'].update(first['readback']['source_hashes'])
    for r in first['references'].values():post['source_hashes'][r['path']]=r['sha256']
    other['readback']['source_hashes'].update(post['source_hashes'])
    other['readback']['raw_result_reference']=first['references']['raw_result']
    return other

class Review(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prepared,cls.contract=f.fixture();cls.fitter=cls.prepared['fitter_contract_preserved']
    def resolve(self,items):return m.resolve_adjacent_refit_priors(prepared=self.prepared,prior_evidence=items,receipt_contract=self.contract)

    def test_reuse_original_location_must_be_registered_not_self_signed(self):
        rows=self.resolve([])['rows'];first=f.evidence(rows[4]['outer_request'],self.fitter,self.contract)
        good=reused(first,rows[5]['outer_request'],self.fitter,self.contract)
        self.assertIsNotNone(self.resolve([good])['rows'][13]['outer_request'])
        for kind in ('foreign_lane','wrong_registered_choice'):
            origin=deepcopy(first);q=origin['request']
            if kind=='foreign_lane':q['coordinate'][2]='FOREIGN_LANE';q['location_identity']['lane']='FOREIGN_LANE'
            else:q['location_identity']['selected_scoring_job_id']='0'*64
            q['location_id']=p.digest(q['location_identity'])
            q['content_sha256']=p.digest({k:v for k,v in q.items() if k!='content_sha256'})
            for obj in ('raw_result','postcheck','readback'):origin[obj]['location_id']=q['location_id']
            attack=reused(origin,rows[5]['outer_request'],self.fitter,self.contract)
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.resolve([attack])

    def test_no_skip_and_no_cross_lane_advance_all_matrices_preserved(self):
        before=deepcopy(self.prepared);base=self.resolve([])
        first=f.evidence(base['rows'][4]['outer_request'],self.fitter,self.contract)
        out=self.resolve([first]);self.assertEqual(len(out['rows']),48)
        self.assertIsNotNone(out['rows'][12]['outer_request'])
        for i in (13,20,28,36,44):
            self.assertIsNone(out['rows'][i]['outer_request']);self.assertIsNone(out['rows'][i]['numerical_task_id'])
            self.assertEqual(len(out['rows'][i]['fit_matrix']['returns']),126)
        failed=deepcopy(first);failed['postcheck']['outcome']='UNKNOWN'
        with self.assertRaises(ValueError):self.resolve([failed])
        self.assertEqual(self.prepared,before)

    def test_saved_binary64_anchor_and_next_prior_simplex_are_exact(self):
        request=deepcopy(self.resolve([])['rows'][4]['outer_request']);identity=request['numerical_identity'];ids=sorted(identity['selected'])
        identity['weight_spec']='constrained_fixed_shrinkage_turnover_anchor'
        identity['requested_previous_target_weights']={ids[0]:.1,ids[1]:.2,'other':.7}
        request['numerical_task_id']=p.digest(identity)
        evidence=f.evidence(request,self.fitter,self.contract);body=evidence['raw_result']['result']
        self.assertEqual(body['surviving_anchor_mass'].hex(),(.1+.2).hex())
        m.inspect_return(body,request,self.fitter)
        for field in ('surviving_anchor_mass','effective_anchor_strength'):
            bad=deepcopy(body);bad[field]=math.nextafter(bad[field],math.inf)
            with self.subTest(field=field),self.assertRaises(ValueError):m.inspect_return(bad,request,self.fitter)
        bad=deepcopy(body)
        for target in bad['targets'].values():target['target_weight']+=1e-10
        self.assertTrue(math.isclose(sum(t['target_weight'] for t in bad['targets'].values()),1.,abs_tol=1e-9,rel_tol=0))
        with self.assertRaises(ValueError):m.inspect_return(bad,request,self.fitter)

if __name__=='__main__':unittest.main()
