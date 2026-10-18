from copy import deepcopy
from datetime import date, timedelta
import unittest
from unittest.mock import patch
from backtest import ndx_return_priority_first_candidate_inputs_v2 as subject


def fixture():
    days=[(date(2026,1,1)+timedelta(days=i)).isoformat() for i in range(127)]
    securities=[dict(security_id=f'S{i}',issuer_id=f'I{i}',ticker=f'T{i}',risk_chain=f'C{i}') for i in range(77)]
    original=[dict(security_id=f'S{i}',issuer_id=f'I{i}',ticker=f'T{i}',risk_chain=f'C{i}',target_weight=(.03 if i==0 else .97/7)) for i in range(7)]
    original.append(dict(security_id='TSM_CONTROL',issuer_id='ITSM',ticker='TSM',risk_chain='foundry',target_weight=.97/7))
    prepared=dict(securities=securities,cutoff=days[-1],initial_price_date=days[0],return_dates=days[1:],
        initial_prices={f'S{i}':10. for i in range(77)},target_prices={f'S{i}':100000. if i==0 else 100. for i in range(77)},
        returns={f'S{i}':[0.]*126 for i in range(77)},original8_definition=original,
        policy=dict(max_single_weight=.45,min_single_weight=.05,top_three_cap=.8,min_neff_ratio=.7,chain_cap=.55),
        plan=dict(cash_usd=20000,fee_bps=10,research_buffer_usd=100),observed_provenance=[],source_checks=[],source_bindings={},source_authority='SYNTHETIC')
    sidecar=dict(schema='FIXED_TSM_CONTROL_SAME_BASIS_SOURCE_CANDIDATE_V1',status='COMPLETE_127_QUOTES_126_RETURNS_CONDITIONAL_NOT_FORMAL_PIT',cutoff=days[-1],
        quotes=[dict(session=day,close_decimal='10',nominal_close=10.,split_factor='1') for day in days],
        returns=[dict(session=current,previous_session=previous,declared_share_ratio='1',price_return=0.,exact_decimal_quote_return='0') for previous,current in zip(days,days[1:])])
    binding=dict(schema='ROOT_FIXED_ORIGINAL_EIGHT_CONTROL_EXTENSION_V1',separate_control_metric_evaluation_limit=1,candidate_objective_limit_unchanged=311296,
                 tsm_sidecar=dict(sha256=subject.BOUND['tsm_sidecar'][1]),root_independent_quote_readback=dict(sha256=subject.BOUND['tsm_root_readback'][1]))
    readback=dict(status='PASS_CAPTURED_TSM_SAME_BASIS_CONTROL_QUOTES_AND_RETURNS',quotes_compared_to_raw=127,returns_independently_recomputed=126,source_unchanged=True,
                  candidate_reference=dict(sha256=subject.BOUND['tsm_sidecar'][1]),point_in_time_verified=False)
    return prepared,sidecar,binding,readback


def extended():
    prepared,sidecar,binding,readback=fixture()
    return subject.extend_original8_control(prepared=prepared,sidecar=sidecar,binding=binding,readback=readback)


class ControlV2(unittest.TestCase):
    def test_binding_dates_formula_and_tsm_not_candidate(self):
        prepared,sidecar,binding,readback=fixture()
        valid=subject.extend_original8_control(prepared=prepared,sidecar=sidecar,binding=binding,readback=readback)
        self.assertEqual(len(valid['securities']),77)
        self.assertEqual(len(valid['original8_channels']),8)
        self.assertTrue(all(row['ticker']!='TSM' for row in valid['securities']))
        for mode in ('date','return','pin','qualification'):
            altered=deepcopy(sidecar);b=deepcopy(binding);r=deepcopy(readback)
            if mode=='date':altered['quotes'][0]['session']='2099-01-01'
            elif mode=='return':altered['returns'][0]['price_return']=.01
            elif mode=='pin':b['tsm_sidecar']['sha256']='0'*64
            else:r['point_in_time_verified']=True
            with self.assertRaises(ValueError):subject.extend_original8_control(prepared=prepared,sidecar=altered,binding=b,readback=r)

    def test_complete_eight_definition_zero_lot_and_single_metric_budget(self):
        prepared=extended();result,budget=subject.evaluate_original8_control(prepared=prepared,risk_scope='INITIAL_DEPLOYMENT_DAILY_DIAGNOSTICS_ONLY')
        self.assertEqual(result['original_definition_count'],8)
        self.assertEqual(result['original_target_weights']['S0'],.03)
        self.assertEqual(result['all_eight_target_quantities']['S0'],0)
        self.assertEqual(result['zero_allocated_due_to_whole_share_floor'],['T0'])
        self.assertFalse(result['candidate_risk_gate_imposed'])
        self.assertEqual(budget.objective_calls,1)
        self.assertAlmostEqual(result['reconciliation_total'],20000)
        self.assertAlmostEqual(result['training_metrics']['maximum_drawdown'],result['fees']/20000)
        self.assertAlmostEqual(result['training_metrics']['cagr'],(1-result['fees']/20000)**2-1)

    def test_v2_wrapper_outputs_reproduction_seed_and_separate_baseline_budget(self):
        prepared=extended()
        prepared['plan']['finite_budgets']=dict(support_proposals_per_k=64,objective_evaluations_per_support=64,integer_deployment_proposals_per_support=128,
                                              global_objective_evaluations=311296,global_integer_deployment_proposals=622592)
        with patch.object(subject,'run_bounded_search',return_value=dict(budget=dict(objective_calls=7))) as mock:
            result=subject.calculate_dated_candidate(prepared=prepared,risk_scope='INITIAL_DEPLOYMENT_DAILY_DIAGNOSTICS_ONLY')
        self.assertEqual(mock.call_args.kwargs['seed'],20261013)
        self.assertEqual(result['search_seed'],20261013)
        self.assertEqual(result['total_candidate_plus_control_objective_calls'],8)
        self.assertEqual(result['control_objective_calls'],1)


if __name__=='__main__':unittest.main()
