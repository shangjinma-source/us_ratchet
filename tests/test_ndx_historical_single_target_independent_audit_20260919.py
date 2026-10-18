import copy
import unittest
from test_ndx_twenty_historical_single_target_20260919 import fixture
from scripts import ndx_historical_single_target_independent_audit_20260919 as m


def bundle():
    state,result,inputs,row=fixture();plan=dict(delta=dict(tasks=[row]));task,fit,calendar,structure=m.reconstruct(inputs,plan)
    marker=dict(path='started.json',sha256='a'*64);rawref=dict(path='raw_fit_receipt.json',sha256='b'*64)
    base={'original-source':'c'*64};rawsources=dict(base,**{marker['path']:marker['sha256']});sources=dict(rawsources,**{rawref['path']:rawref['sha256']})
    started=dict(schema='HISTORICAL_SINGLE_TARGET_ATTEMPT_V1',job_id=m.JOB,input_reference=m.INPUT,attempt_count=1)
    raw=dict(schema='HISTORICAL_SINGLE_TARGET_RAW_FIT_RECEIPT_V1',job_id=m.JOB,original_result=result,explicit_fit_matrix=fit,task=task,input_reference=m.INPUT,independent_input_audit_reference=m.AUDIT,structure_reference=structure,started_reference=marker,historical_expected_source_hashes=rawsources,**dict.fromkeys(m.FALSE,False))
    detail=m.scalar.inspect_result(result,task,dict(returns=fit))
    value=dict(schema='HISTORICAL_SINGLE_CONDITIONAL_TARGET_V1',job_id=m.JOB,task=task,result=result,independent_matrix_and_risk_audit=detail,status='FITTED_FIVE_RISKS_PASSED',raw_fit_reference=rawref,started_reference=marker,input_reference=m.INPUT,independent_input_audit_reference=m.AUDIT,structure_reference=structure,execution_observation_calendar=calendar,baseline_close_date='2026-03-18',first_next_open_observation='2026-03-19',schedule=[dict(decision_date='2026-03-18',execution_date='2026-03-19',targets=result['targets'])],risk_chains_by_decision={'2026-03-18':result['risk_chains_by_security']},target_does_not_prove_order_acceptance=True,static_risk_and_liquidity_roles=dict(risk=inputs['risk_label_role'],liquidity=inputs['latest_liquidity_role']),conditional_coordinate_provenance=inputs['candidate_full_original_provenance'],supplemental_dated_provenance=inputs['candidate_supplemental_dated_provenance'],historical_expected_source_hashes=sources,archive_resolution={},**dict.fromkeys(m.FALSE,False))
    return value,raw,started,inputs,plan,{},base


class IndependentTargetTests(unittest.TestCase):
    def test_real_historical_matrix_and_127_clock_independently_rebuilt(self):
        args=bundle();detail=m.inspect(*args)
        self.assertEqual(detail['fit_end'],'2026-03-18');self.assertEqual(detail['calendar_count'],127)
        future=copy.deepcopy(args[3]);future['prices']['returns']['data'][-1][0]=999.0
        self.assertEqual(m.reconstruct(args[3],args[4])[1],m.reconstruct(future,args[4])[1])

    def test_full_raw_source_and_future_weight_replacement_rejected(self):
        original=bundle()
        for kind in ('source','matrix','date','scope','risk','clock'):
            args=copy.deepcopy(original);value,raw=args[:2]
            if kind=='source':del value['historical_expected_source_hashes']['original-source'];del raw['historical_expected_source_hashes']['original-source']
            elif kind=='matrix':raw['explicit_fit_matrix']['data'][0][0]=999
            elif kind=='date':value['result']['cutoff']='2026-09-17'
            elif kind=='scope':value['promotion_allowed']=True
            elif kind=='risk':value['independent_matrix_and_risk_audit']['risk_pass']=False
            else:value['schedule'][0]['execution_date']='2026-03-18'
            with self.subTest(kind=kind),self.assertRaises(ValueError):m.inspect(*args)

    def test_scope_extra_keys_and_marker_bool_attempt_rejected(self):
        args=list(bundle());args[2]['attempt_count']=True
        with self.assertRaises(ValueError):m.inspect(*args)
        args=list(bundle());args[1]['live_authorized']=True
        with self.assertRaises(ValueError):m.inspect(*args)
        if m.TARGET_SHA is None:
            with self.assertRaises(ValueError):m.build('unsealed','0'*64)


if __name__=='__main__':unittest.main()
