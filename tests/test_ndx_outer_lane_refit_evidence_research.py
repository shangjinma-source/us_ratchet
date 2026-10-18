from copy import deepcopy
import unittest
from backtest import ndx_multidecision_selected_refit_inputs_research as p
from backtest import ndx_outer_lane_refit_evidence_research as m
from test_ndx_multidecision_selected_refit_inputs_research import fixture as inputs_fixture


def reference(name):return dict(path='/synthetic/'+name,sha256=p.digest(name))


def fixture():
    args=inputs_fixture();f=args['fitter_contract']
    f['source_hashes'].update({'/code/extra'+str(i):p.digest(i) for i in range(22)})
    f.update(fitter_source_fingerprint=p.digest(f['source_hashes']),first_requested_previous_target_weights=None,
        first_effective_turnover_anchor_strength=0,prior_policy='SAME_FX_SAME_LANE_PREVIOUS_ADJACENT_AUDITED_OUTER_REFIT_TARGET',
        runtime_versions=dict(python='synthetic3',numpy='synthetic2',pandas='synthetic2',scipy='synthetic1'),
        required_worker_environment={'PYTHONHASHSEED':'0','sys_flags_hash_randomization':0})
    prepared=p.prepare_selected_cutoff_refit_inputs(**args)
    contract=dict(schema='OUTER_LANE_RECEIPT_INTERFACE_CONTRACT_V1',reader_reference=reference('future_reader'),source_bytes_authenticated=False)
    return prepared,contract


def evidence(request,fitter,contract):
    key=request['location_id'];refs={k:reference(key+'/'+k) for k in ('request','raw_result','postcheck','readback')}
    refs['reader']=contract['reader_reference'];identity=request['numerical_identity'];selected=identity['selected'];sids=sorted(selected)
    weights={s:1./len(sids) for s in sids};prior=identity['requested_previous_target_weights'] or {}
    mass=sum(prior.get(s,0.) for s in sids)
    body=dict(schema='ndx_dynamic_cutoff_refit_research_v2',cutoff=identity['cutoff'],weight_spec=identity['weight_spec'],
        fit_start=request['fit_matrix']['dates'][0],fit_end=identity['cutoff'],fit_row_count=126,
        fit_data_sha256=identity['fit_data_sha256'],source_hashes=deepcopy(fitter['source_hashes']),
        declared_parameters={k:v for k,v in p.PARAMETERS.items() if k!='fit_days'},
        targets={s:dict(ticker=selected[s]['ticker'],issuer_id=selected[s]['issuer_id'],target_weight=weights[s]) for s in sids},
        risk_chains_by_security={s:selected[s]['risk_chain'] for s in sids},previous_target_weights=prior,
        surviving_anchor_mass=mass,anchor_by_security={s:prior.get(s,0.)/mass if mass else 0. for s in sids},
        effective_anchor_strength=.25 if mass and identity['weight_spec']=='constrained_fixed_shrinkage_turnover_anchor' else 0.,
        anchor_policy='SURVIVING_SECURITY_TARGET_MASS_RENORMALIZED_NEW_ENTRIES_ZERO_NO_OVERLAP_DISABLED',
        declared_constraint_checks=dict.fromkeys(('MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT'),True),
        declared_constraints_passed=True,numerical_projection='V3_CERTIFIED_RECOVERY_ORIGINAL_PROBE_CLOSURE',
        projection_reconstruction_audit=dict(schema='ndx_projection_reconstruction_audit_v1',scope='NUMERICAL_PROJECTION_RECOVERY_NOT_ECONOMIC_QUALIFICATION',attempt_count=0,attempts=[],prior_results_reused=False,promotion_allowed=False),
        **dict.fromkeys(('checkpoint_weights_used','point_in_time_verified','source_authenticity_verified','promotion_allowed','historical_task_evaluation_performed','order_generation_allowed','risk_chain_projection_relaxed','single_name_projection_relaxed','top3_projection_semantics_relaxed'),False))
    sources=deepcopy(fitter['source_hashes'])
    for r in (fitter['reference'],refs['request']):sources[r['path']]=r['sha256']
    common=dict(request_reference=refs['request'],numerical_task_id=request['numerical_task_id'],location_id=request['location_id'],**dict.fromkeys(m.ENVELOPE_FLAGS,False))
    raw=dict(common,schema=m.PREFIX+'RAW_RETURN_V1',returned=True,call_invoked=True,returned_call_count=1,error=None,result=body,
        runtime_versions=fitter['runtime_versions'],worker_environment=fitter['required_worker_environment'],internal_optimizer_call_count=None,source_hashes=deepcopy(sources))
    sources[refs['raw_result']['path']]=refs['raw_result']['sha256']
    post=dict(common,schema=m.PREFIX+'POSTCHECK_V1',outcome='REFIT_PASSED_PENDING_INDEPENDENT_READBACK',error=None,raw_result_reference=refs['raw_result'],source_hashes=deepcopy(sources),current_location_call_invoked=True,current_location_returned_call_count=1)
    for r in (refs['postcheck'],refs['reader']):sources[r['path']]=r['sha256']
    audit=dict(common,schema=m.PREFIX+'INDEPENDENT_READBACK_V1',status='PASS',scope='SAVED_OUTER_RESULT_ARITHMETIC_AND_SOURCE_BINDING_NOT_REOPTIMIZATION',
        raw_result_reference=refs['raw_result'],postcheck_reference=refs['postcheck'],reader_sha256=refs['reader']['sha256'],targets_preserved=deepcopy(body['targets']),raw_result_body_sha256=p.digest(body),source_hashes=sources)
    return deepcopy(dict(request=request,raw_result=raw,postcheck=post,readback=audit,references=refs))


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.prepared,cls.contract=fixture()

    def run_inputs(self,items):
        return m.resolve_adjacent_refit_priors(prepared=self.prepared,prior_evidence=items,receipt_contract=self.contract)

    def test_all_six_adjacent_cutoffs_and_original_prior(self):
        receipts=[];out=self.run_inputs(receipts)
        for j in range(5):
            for row in out['rows'][j*8:(j+1)*8]:
                if row['outer_request'] is not None:receipts.append(evidence(row['outer_request'],self.prepared['fitter_contract_preserved'],self.contract))
            out=self.run_inputs(receipts)
        self.assertEqual(len(receipts),20)
        self.assertEqual(sum(r['outer_request'] is not None for r in out['rows']),24)
        self.assertEqual(sum(r['status']=='SOURCE_BLOCKED' for r in out['rows']),24)
        first=out['rows'][4];last=out['rows'][44]
        self.assertIsNone(first['outer_request']['numerical_identity']['requested_previous_target_weights'])
        self.assertEqual(last['requested_previous_target_weights'],{s:.25 for s in last['selected']})
        self.assertEqual(last['numerical_identity']['requested_previous_target_weights'],last['requested_previous_target_weights'])
        self.assertEqual(len(last['fit_matrix']['returns']),126)
        self.assertFalse(out['source_bytes_authenticated']);self.assertFalse(out['fit_performed'])

    def test_missing_previous_keeps_full_matrix_but_no_id(self):
        out=self.run_inputs([]);r=out['rows'][12]
        self.assertEqual(len(r['fit_matrix']['returns']),126);self.assertIsNone(r['numerical_task_id']);self.assertIsNone(r['outer_request'])
        first=out['rows'][4];e=evidence(first['outer_request'],self.prepared['fitter_contract_preserved'],self.contract)
        e['request']['coordinate'][0]='2026-04-30'
        with self.assertRaises(ValueError):self.run_inputs([e])

    def test_failed_crosslane_raw_weight_and_missing_source_rejected(self):
        request=self.run_inputs([])['rows'][4]['outer_request'];original=evidence(request,self.prepared['fitter_contract_preserved'],self.contract)
        for mutate in (
            lambda e:e['postcheck'].update(outcome='NUMERICAL_EXCEPTION'),
            lambda e:e['request']['coordinate'].__setitem__(2,'BAD_TAIL'),
            lambda e:e['raw_result'].update(returned_call_count=True),
            lambda e:e['raw_result']['worker_environment'].update(PYTHONHASHSEED='1'),
            lambda e:e['readback']['source_hashes'].pop(next(iter(self.prepared['fitter_contract_preserved']['source_hashes']))),
            lambda e:e['readback'].update(reader_sha256='0'*64)):
            with self.subTest(mutate=mutate):
                e=deepcopy(original);mutate(e)
                with self.assertRaises(ValueError):self.run_inputs([e])
        with self.assertRaises((ValueError,KeyError)):self.run_inputs([{'weights':{}}])
        with self.assertRaises(ValueError):self.run_inputs([original,original])

    def test_re_signed_raw_five_risks_anchor_and_input_matrix(self):
        request=self.run_inputs([])['rows'][4]['outer_request'];original=evidence(request,self.prepared['fitter_contract_preserved'],self.contract)
        for field,value in [('fit_row_count',True),('effective_anchor_strength',.25),('previous_target_weights',None),('declared_constraints_passed',1)]:
            e=deepcopy(original);e['raw_result']['result'][field]=value;e['readback']['raw_result_body_sha256']=p.digest(e['raw_result']['result'])
            with self.subTest(field=field),self.assertRaises(ValueError):self.run_inputs([e])
        e=deepcopy(original);e['request']['fit_matrix']['returns'][0][0]=.99
        with self.assertRaises(ValueError):self.run_inputs([e])

    def test_no_reference_alias_and_no_hidden_fit(self):
        original=deepcopy(self.prepared);out=self.run_inputs([]);out['rows'][4]['outer_request']['fit_matrix']['returns'][0][0]=999
        self.assertEqual(self.prepared,original)
        import inspect
        source=inspect.getsource(m)
        self.assertNotIn('refit_dynamic_cutoff_weights(',source)

    def test_anchored_overlap_and_no_overlap_follow_old_contract(self):
        request=deepcopy(self.run_inputs([])['rows'][4]['outer_request']);identity=request['numerical_identity']
        identity['weight_spec']='constrained_fixed_shrinkage_turnover_anchor';sids=sorted(identity['selected'])
        for previous,expected_mass,expected_strength in ((None,0.,0.),({sids[0]:.4,'security:other':.6},.4,.25),({'security:other':1.},0.,0.)):
            identity['requested_previous_target_weights']=previous;request['numerical_task_id']=p.digest(identity)
            e=evidence(request,self.prepared['fitter_contract_preserved'],self.contract)
            raw=e['raw_result']['result'];self.assertEqual(raw['surviving_anchor_mass'],expected_mass)
            self.assertEqual(raw['effective_anchor_strength'],expected_strength)
            result=m.inspect_return(raw,request,self.prepared['fitter_contract_preserved'])
            self.assertEqual(result,{s:.25 for s in sids})
            if expected_mass:self.assertEqual(raw['anchor_by_security'][sids[0]],1.)

    def test_cross_lane_numeric_reuse_keeps_first_raw_and_no_second_call(self):
        rows=self.run_inputs([])['rows'];first=evidence(rows[4]['outer_request'],self.prepared['fitter_contract_preserved'],self.contract)
        other=evidence(rows[5]['outer_request'],self.prepared['fitter_contract_preserved'],self.contract)
        self.assertEqual(first['request']['numerical_task_id'],other['request']['numerical_task_id'])
        other['numerical_reuse_evidence']=deepcopy(first);other['raw_result']=deepcopy(first['raw_result'])
        other['references']['raw_result']=deepcopy(first['references']['raw_result'])
        post=other['postcheck'];post.update(outcome='REUSED_AUDITED_NUMERICAL_RESULT',current_location_call_invoked=False,current_location_returned_call_count=0,raw_result_reference=first['references']['raw_result'])
        post['source_hashes'].update(first['readback']['source_hashes'])
        for r in first['references'].values():post['source_hashes'][r['path']]=r['sha256']
        other['readback']['source_hashes'].update(post['source_hashes']);other['readback']['raw_result_reference']=first['references']['raw_result']
        out=self.run_inputs([first,other]);self.assertIsNotNone(out['rows'][12]['outer_request']);self.assertIsNotNone(out['rows'][13]['outer_request'])
        self.assertEqual(other['raw_result']['location_id'],first['request']['location_id'])
        for change in ('call','raw_location','original_prior'):
            e=deepcopy(other)
            if change=='call':e['postcheck']['current_location_call_invoked']=True
            if change=='raw_location':e['raw_result']['location_id']=e['request']['location_id']
            if change=='original_prior':e['numerical_reuse_evidence']['request']['numerical_identity']['requested_previous_target_weights']={}
            with self.subTest(change=change),self.assertRaises(ValueError):self.run_inputs([first,e])


if __name__=='__main__':unittest.main()
