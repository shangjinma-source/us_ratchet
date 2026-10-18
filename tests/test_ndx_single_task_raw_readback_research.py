"""Synthetic saved-result readback; no fitter import/call."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest
from decimal import localcontext,Inexact
from unittest.mock import patch
from backtest import ndx_single_task_raw_readback_research as m
spec=importlib.util.spec_from_file_location('materialized_fixture',Path(__file__).with_name('test_ndx_issuer_materialization_independent_readback_research.py'))
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)


def case(prior=None,weight_spec='equal_weight',weights=None):
 a=f.fixture(prior);combo=a['value']['combinations'][0];task=combo['tasks'][0];n=task['numerical_identity'];n['weight_spec']=weight_spec;task['numerical_task_id']=m.digest(n);task['location_identity']['weight_spec']=weight_spec;task['location_id']=m.digest(task['location_identity']);sel=n['selected'];p=n['parameters']
 weights=weights or {s:.25 for s in sorted(sel)};previous=prior or {};mass=sum(float(previous.get(s,0.)) for s in sorted(sel));anchor={s:float(previous.get(s,0.))/mass if mass else 0. for s in sorted(sel)};strength=.25 if mass and weight_spec.endswith('turnover_anchor') else 0.
 ordered=sorted(weights.values(),reverse=True);groups={}
 for s,v in weights.items():groups[sel[s]['risk_chain']]=groups.get(sel[s]['risk_chain'],0.)+v
 neff=1./sum(v*v for v in weights.values())
 checks=dict(MAX_SINGLE_WEIGHT=ordered[0]<=p['max_single_weight']+1e-9,MIN_SINGLE_WEIGHT=ordered[-1]>=p['min_single_weight']-1e-9,SECURITY_TOP3_WEIGHT=sum(ordered[:3])<=p['top_weight_cap']+1e-9,MINIMUM_EFFECTIVE_N=neff>=4*p['minimum_effective_n_ratio']-1e-9,RISK_CHAIN_TOP1_WEIGHT=max(groups.values())<=p['risk_chain_top1_cap']+1e-9)
 fit=dict(schema='ndx_dynamic_cutoff_refit_research_v2',weight_spec=weight_spec,cutoff=n['cutoff'],fit_start=combo['fit_matrix']['dates'][0],fit_end=n['cutoff'],fit_row_count=126,fit_data_sha256=combo['fit_data_sha256'],targets={s:dict(ticker=sel[s]['ticker'],issuer_id=sel[s]['issuer_id'],target_weight=weights[s]) for s in sorted(sel)},risk_chains_by_security={s:r['risk_chain'] for s,r in sel.items()},previous_target_weights={s:float(v) for s,v in previous.items()},surviving_anchor_mass=mass,anchor_by_security=anchor,effective_anchor_strength=strength,anchor_policy='SURVIVING_SECURITY_TARGET_MASS_RENORMALIZED_NEW_ENTRIES_ZERO_NO_OVERLAP_DISABLED',declared_parameters={k:float(v) for k,v in p.items() if k!='fit_days'},declared_constraint_checks=checks,declared_constraints_passed=all(checks.values()),risk_chain_projection_relaxed=False,single_name_projection_relaxed=False,top3_projection_semantics_relaxed=False,checkpoint_weights_used=False,point_in_time_verified=False,source_authenticity_verified=False,promotion_allowed=False,source_hashes=a['expected_fitter_source_hashes'],numerical_projection='V3_CERTIFIED_RECOVERY_ORIGINAL_PROBE_CLOSURE',projection_reconstruction_audit=dict(schema='ndx_projection_reconstruction_audit_v1',scope='NUMERICAL_PROJECTION_RECOVERY_NOT_ECONOMIC_QUALIFICATION',attempt_count=0,attempts=[],prior_results_reused=False,promotion_allowed=False),historical_task_evaluation_performed=False,order_generation_allowed=False)
 return dict(task=task,combination=combo,fitted=fit,numerical_sources=a['expected_fitter_source_hashes'])


class Tests(unittest.TestCase):
 def test_equal_returned_result_and_permissions(self):
  r=m.inspect_fitted(**case());self.assertEqual(r['status'],'FITTED_FIVE_RISKS_PASSED');self.assertFalse(r['fitter_called']);self.assertFalse(r['risk_projection_metadata_independently_recomputed'])
 def test_original_risk_failure_is_valid_numerical_result(self):
  r=m.inspect_fitted(**case(weight_spec='constrained_fixed_shrinkage',weights={'a':.8,'b':.1,'m':.05,'z1':.05}))
  self.assertEqual(r['status'],'FITTED_FIVE_RISKS_FAILED');self.assertFalse(r['checks']['MAX_SINGLE_WEIGHT'])
 def test_exit_prior_survivor_anchor_and_zero_mass(self):
  r=m.inspect_fitted(**case({'EXITED':.75,'a':.25},'constrained_fixed_shrinkage_turnover_anchor'));self.assertEqual(r['exited_prior_sids'],['EXITED'])
  self.assertTrue(m.inspect_fitted(**case({'EXITED':1.},'constrained_fixed_shrinkage_turnover_anchor'))['complete_prior_verified'])
 def test_identity_prior_anchor_source_matrix_risk_tampering(self):
  for attack in ('target','prior','anchor','source','matrix','risk','permission','nan'):
   c=case({'EXITED':.75,'a':.25},'constrained_fixed_shrinkage_turnover_anchor');fit=c['fitted']
   if attack=='target':fit['targets']['a']['issuer_id']='OTHER'
   elif attack=='prior':fit['previous_target_weights']={'a':1.}
   elif attack=='anchor':fit['anchor_by_security']['a']=.25
   elif attack=='source':fit['source_hashes']=dict(fit['source_hashes']);fit['source_hashes'].pop(next(iter(fit['source_hashes'])))
   elif attack=='matrix':c['combination']['fit_matrix']['returns'][0][0]=.99
   elif attack=='risk':fit['declared_constraint_checks']['MAX_SINGLE_WEIGHT']=False
   elif attack=='permission':fit['promotion_allowed']=True
   else:fit['targets']['a']['target_weight']=float('nan')
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.inspect_fitted(**c)
 def test_projection_counts_equal_and_boolean_rejected(self):
  for value in (False,1):
   c=case();c['fitted']['projection_reconstruction_audit']['attempt_count']=value
   with self.assertRaises(ValueError):m.inspect_fitted(**c)
 def test_failed_internal_group_recovery_then_successful_original_fallback(self):
  c=case(weight_spec='constrained_fixed_shrinkage');fit=c['fitted'];fit['risk_chain_projection_relaxed']=True
  labels={r['ticker']:r['risk_chain'] for r in c['task']['numerical_identity']['selected'].values()}
  reconstruction=dict(schema='ndx_projection_reconstruction_research_v1',certified=False,status='RECONSTRUCTION_NOT_CERTIFIED',weights=None,
   constraints=dict(max_weight=.45,min_weight=.05,top_weight_count=3,top_weight_cap=.8,min_effective_n=2.8,group_labels=labels,max_group_weight=.55),
   primal_infeasibility_proven=False,promotion_allowed=False,task_recomputed=False,order_generation_allowed=False)
  fit['projection_reconstruction_audit'].update(attempt_count=1,attempts=[dict(optimizer_message='failed grouped line search',reconstruction=reconstruction)])
  r=m.inspect_fitted(**c);self.assertEqual(r['status'],'FITTED_FIVE_RISKS_PASSED')
  self.assertTrue(r['projection_audit']['attempts'][0]['saved_failed_internal_group_attempt_preserved'])
  fit['risk_chain_projection_relaxed']=False
  with self.assertRaises(ValueError):m.inspect_fitted(**c)
 def test_projection_entry_isolates_decimal_precision_and_traps(self):
  def probe(*args):
   from decimal import Decimal,getcontext
   self.assertEqual(getcontext().prec,80)
   self.assertFalse(getcontext().traps[Inexact])
   return Decimal('1.0000000000000000001')-Decimal('1')
  with localcontext() as context:
   context.prec=2;context.traps[Inexact]=True
   with patch.object(m,'_inspect_projection',side_effect=probe):
    self.assertEqual(str(m.inspect_projection({},'equal_weight',{}, {},False,{})),'1E-19')
 def test_float_checks_are_primary_not_decimal_replacement(self):
  c=case();r=m.inspect_fitted(**c)
  self.assertEqual(r['checks'],c['fitted']['declared_constraint_checks']);self.assertIn('extra_decimal_diagnostic_checks',r)

if __name__=='__main__':unittest.main()
