"""Independent reader counterexamples, no producer import or real fit/account."""
from copy import deepcopy
from pathlib import Path
import unittest
from scripts import ndx_bad_tail_lane_prefix_independent_readback_20260923 as r


def fixture(index=5):
    selected={f'S{i}':dict(ticker=f'T{i}',issuer_id=f'I{i}',risk_chain=f'R{i}') for i in range(4)}
    previous=None if index==0 else dict(S0=.25,S1=.25,S2=.25,EXIT=.25)
    old=deepcopy(selected);old['EXIT']=dict(ticker='OLD',issuer_id='OLDISSUER',risk_chain='old')
    universe=deepcopy(old);universe['EXIT']['risk_chain']='current'
    binding=r.lane_binding(index=index,previous=previous,previous_selected=old,selected=selected,universe=universe,
        context_reference={'path':'context','sha256':'a'*64},input_binding={},
        import_reference={'path':'import','sha256':'b'*64},import_audit_reference={'path':'audit','sha256':'c'*64})
    imported=index in (0,5);actual={} if imported else previous;mass=0 if imported else .75
    params=dict(fit_days=126,shrinkage_intensity=.35,turnover_anchor_strength=.25,max_single_weight=.45,
        min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
    checks=dict.fromkeys(('MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT'),True)
    spec='constrained_fixed_shrinkage' if index==5 else 'constrained_fixed_shrinkage_turnover_anchor'
    fitted=dict(targets={sid:dict(ticker=v['ticker'],issuer_id=v['issuer_id'],target_weight=.25) for sid,v in selected.items()},
        previous_target_weights=actual,checkpoint_weights_used=False,weight_spec=spec,
        declared_parameters={k:v for k,v in params.items() if k!='fit_days'},surviving_anchor_mass=mass,
        anchor_by_security={sid:actual.get(sid,0)/mass if mass else 0 for sid in selected},effective_anchor_strength=.25 if mass else 0,
        risk_chains_by_security={sid:v['risk_chain'] for sid,v in selected.items()},declared_constraint_checks=checks,declared_constraints_passed=True,
        **dict.fromkeys(('point_in_time_verified','source_authenticity_verified','promotion_allowed','historical_task_evaluation_performed','order_generation_allowed'),False))
    previous_ref=None if index==0 else {'path':'prior','sha256':'d'*64}
    common=dict(execution_date=r.DATES[index],plan_reference=r.PLAN)
    started=dict(common,schema='BAD_TAIL_TARGET_SINGLE_ATTEMPT_V1',cutoff=r.CUTOFFS[index],job_id='job',
        previous_target_reference=previous_ref,previous_target_weights=previous,selected=selected,parameters=params,
        weight_spec=spec,source_hashes={},runtime={},new_fit_attempt=not imported,order_generation_allowed=False,numerical_and_lane_binding=binding)
    raw=dict(common,schema='BAD_TAIL_TARGET_RAW_RESULT_V1',previous_target_reference=previous_ref,previous_target_weights=previous,
        started_reference={'path':'started','sha256':'e'*64},new_fit_attempt_count=0 if imported else 1,
        first_fit_imported_without_refit=index==0,numerical_and_lane_binding=binding,status='FIT_RETURNED',fitted=fitted)
    final=dict(common,schema='BAD_TAIL_TARGET_STEP_FINALIZATION_V1',raw_reference={'path':'raw','sha256':'f'*64},
        status='TARGET_FIVE_RISKS_PASSED',risk_checks=checks,detail=None,fallback_performed=False,whole_lot_execution_performed=False,promotion_allowed=False)
    return dict(index=index,started=started,raw=raw,final=final,selected=selected,parameters=params,
        weight_spec=spec,previous=previous,previous_reference=previous_ref,binding=binding)


class ReaderIndependentReview(unittest.TestCase):
    def test_last_actual_empty_prior_and_complete_lane_prior_are_distinct(self):
        args=fixture();observed=r.validate_step(**args)
        self.assertEqual(observed['exited_previous_sids'],['EXIT'])
        self.assertEqual(observed['lane_risk_chains_by_security']['EXIT'],'current')
        for attack in ('actual_prior','lane_prior','count','strength','extra'):
            bad=deepcopy(args)
            if attack=='actual_prior':bad['raw']['fitted']['previous_target_weights']=bad['previous']
            if attack=='lane_prior':bad['raw']['previous_target_weights']={k:v for k,v in bad['previous'].items() if k!='EXIT'}
            if attack=='count':bad['raw']['new_fit_attempt_count']=1
            if attack=='strength':bad['raw']['fitted']['effective_anchor_strength']=.25
            if attack=='extra':bad['raw']['promotion_allowed']=True
            with self.subTest(attack=attack),self.assertRaises(ValueError):r.validate_step(**bad)

    def test_middle_fit_must_keep_exit_in_actual_prior(self):
        args=fixture(2);r.validate_step(**args)
        bad=deepcopy(args);bad['raw']['fitted']['previous_target_weights']={k:v for k,v in bad['previous'].items() if k!='EXIT'}
        with self.assertRaises(ValueError):r.validate_step(**bad)

    def test_prefix_denominator_rejects_skip_and_final_as_first(self):
        refs=[dict(path=str(r.FOLDER/d/'finalization.json'),sha256='a'*64) for d in r.DATES]
        self.assertEqual(len(r.prefix_references(refs)),6)
        for bad in ([],[refs[-1]],refs[:2]+refs[3:]):
            with self.assertRaises(ValueError):r.prefix_references(bad)


if __name__=='__main__':unittest.main()
