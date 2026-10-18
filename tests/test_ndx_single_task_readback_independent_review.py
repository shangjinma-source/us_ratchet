"""Independent synthetic raw checks, without saved result audit or fitter calls."""
from copy import deepcopy
import unittest
import test_ndx_single_task_raw_readback_research as fixture
import test_ndx_new_cutoff_single_task_independent_readback_20260924 as envelopes
from backtest import ndx_single_task_raw_readback_research as m


class IndependentReview(unittest.TestCase):
    def test_full_exit_prior_cannot_be_collapsed_by_issuer(self):
        case=fixture.case({'OTHER_CLASS':.75,'a':.25},'constrained_fixed_shrinkage_turnover_anchor')
        self.assertEqual(m.inspect_fitted(**case)['exited_prior_sids'],['OTHER_CLASS'])
        case['fitted']['surviving_anchor_mass']=1.
        with self.assertRaises(ValueError):m.inspect_fitted(**case)

    def test_equal_rejects_integer_risk_flags_and_projection_claim(self):
        for field in ('risk','relaxation','count'):
            case=fixture.case()
            if field=='risk':case['fitted']['declared_constraint_checks']['MAX_SINGLE_WEIGHT']=1
            if field=='relaxation':case['fitted']['risk_chain_projection_relaxed']=True
            if field=='count':case['fitted']['projection_reconstruction_audit']['attempt_count']=False
            with self.subTest(field=field),self.assertRaises(ValueError):m.inspect_fitted(**case)

    def test_failed_group_attempt_must_not_be_recast_as_ungrouped_failure(self):
        case=fixture.case(weight_spec='constrained_fixed_shrinkage')
        selected=case['task']['numerical_identity']['selected']
        reconstruction=dict(schema='ndx_projection_reconstruction_research_v1',certified=False,
            weights=None,constraints=dict(max_weight=.45,min_weight=.05,top_weight_count=3,
            top_weight_cap=.8,min_effective_n=2.8,
            group_labels={r['ticker']:r['risk_chain'] for r in selected.values()},max_group_weight=.55),
            primal_infeasibility_proven=False,promotion_allowed=False,task_recomputed=False,order_generation_allowed=False)
        fit=case['fitted'];fit['risk_chain_projection_relaxed']=True
        fit['projection_reconstruction_audit'].update(attempt_count=1,
            attempts=[dict(optimizer_message='original internal failure',reconstruction=reconstruction)])
        self.assertTrue(m.inspect_fitted(**case)['projection_audit']['attempts'][0]['saved_failed_internal_group_attempt_preserved'])
        reconstruction['constraints'].update(group_labels=None,max_group_weight=None)
        with self.assertRaises(ValueError):m.inspect_fitted(**case)

    def test_exception_with_claimed_return_or_zero_optimizer_rejected(self):
        for attack in ('return','optimizer'):
            case=envelopes.case();raw=case['raw']
            raw.update(status='FIT_EXCEPTION',fitted=None,returned_fit_count=0,
                       error={'type':'ValueError','message':'finally failed'})
            if attack=='return':raw['returned_fit_count']=1
            else:raw['internal_optimizer_call_count']=0
            with self.subTest(attack=attack),self.assertRaises(ValueError):envelopes.m.inspect_envelopes(**case)


if __name__=='__main__':unittest.main()
