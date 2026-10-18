"""New independent eight-control binding and small money cases; no actual pool search."""
from pathlib import Path
from fractions import Fraction as F
import hashlib
import importlib.util
import json
import math
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
SOURCE=ROOT/'backtest/ndx_return_priority_first_candidate_inputs_v2.py'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()=='256a851bfddf626856892b4f2588b25a3a85cf737381000b9befdce4fc9db9a8'
spec=importlib.util.spec_from_file_location('independent_eight_control',SOURCE)
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
SCOPE='INITIAL_DEPLOYMENT_DAILY_DIAGNOSTICS_ONLY'


def small_control():
    channels={}
    weights=[.01,.09,.1,.12,.14,.16,.18,.2]
    for i,w in enumerate(weights):
        price=1000. if i==0 else 61.+17*i
        channels[f'B{i}']=dict(target_price=price,initial_price=price/3,returns=[-.1,.2,0.],source='SYNTHETIC',
            definition=dict(security_id=f'B{i}',issuer_id=f'ISS{i}',ticker=f'T{i}',risk_chain=f'C{i}',target_weight=w))
    plan=dict(cash_usd=20000,fee_bps=10,research_buffer_usd=100,
        finite_budgets=dict(support_proposals_per_k=1,objective_evaluations_per_support=1,integer_deployment_proposals_per_support=1,global_objective_evaluations=1,global_integer_deployment_proposals=1))
    return dict(plan=plan,original8_channels=channels,policy=dict(max_single_weight=.45,min_single_weight=.05,top_three_cap=.8,min_neff_ratio=.7,chain_cap=.55))


class IndependentControl(unittest.TestCase):
    def test_real_fixed_bytes_prepare_preserves8_tsm_data_not_pool_or_economics(self):
        pins={relative:hashlib.sha256((ROOT/relative).read_bytes()).hexdigest() for relative,_,_ in s.BOUND.values()}
        with patch.object(s,'run_bounded_search',side_effect=AssertionError('Real search forbidden')),patch.object(s,'evaluate_original8_control',side_effect=AssertionError('Actual control arithmetic forbidden')):
            prepared=s.load_fixed_inputs()
        self.assertEqual(len(prepared['securities']),77)
        self.assertFalse(any(r['ticker']=='TSM' for r in prepared['securities']))
        self.assertEqual(len(prepared['original8_channels']),8)
        tsm=[x for x in prepared['original8_channels'].values() if x['definition']['ticker']=='TSM']
        self.assertEqual(len(tsm),1);self.assertEqual(len(tsm[0]['returns']),126)
        self.assertEqual(tsm[0]['target_price'],445.1400146484375)
        self.assertEqual(prepared['original8_missing_tickers'],[])
        self.assertFalse(prepared['source_qualification_complete'])
        self.assertEqual(pins,{relative:hashlib.sha256((ROOT/relative).read_bytes()).hexdigest() for relative,_,_ in s.BOUND.values()})

    def test_independent_unequal_eight_floor_fees_idle_and_peak(self):
        prepared=small_control();channels=prepared['original8_channels'];before=json.dumps(prepared,sort_keys=True)
        result,budget=s.evaluate_original8_control(prepared=prepared,risk_scope=SCOPE)
        capacity=F(19900)/F(1001,1000)
        q={sid:math.floor(capacity*F(str(c['definition']['target_weight']))/F(str(c['target_price']))) for sid,c in channels.items()}
        invested=sum(q[sid]*F(str(c['target_price'])) for sid,c in channels.items());fee=invested/F(1000);idle=F(20000)-invested-fee
        path=[F(20000),idle+invested,idle+invested*F(9,10),idle+invested*F(27,25),idle+invested*F(27,25)]
        self.assertEqual(result['all_eight_target_quantities'],q)
        self.assertEqual(result['zero_allocated_due_to_whole_share_floor'],['T0'])
        self.assertEqual(result['original_definition_count'],8);self.assertEqual(result['actual_positive_target_count'],7)
        for observed,want in zip(result['net_wealth_path'],path):self.assertAlmostEqual(observed,float(want),places=8)
        self.assertAlmostEqual(result['training_metrics']['cagr'],float(path[-1]/20000)**84-1,places=8)
        self.assertAlmostEqual(result['training_metrics']['maximum_drawdown'],float(1-min(path)/20000),places=12)
        self.assertAlmostEqual(result['remaining_cash'],float(idle),places=8)
        self.assertEqual(budget.objective_calls,1);self.assertEqual(budget.integer_proposals,0)
        self.assertFalse(result['candidate_risk_gate_imposed']);self.assertEqual(result['original_target_weights']['B0'],.01)
        self.assertEqual(before,json.dumps(prepared,sort_keys=True))

    def test_wrapper_one_control_call_counted_separately_without_pool_run(self):
        prepared=small_control()
        prepared.update(securities=[],initial_prices={},target_prices={},returns={},return_dates=[],cutoff='2026-09-21',initial_price_date='2026-03-20',observed_provenance=[],source_checks=[],source_bindings={},source_authority='SYNTHETIC',original8_definition=[x['definition'] for x in prepared['original8_channels'].values()],original8_control_status='SYNTHETIC',original8_missing_tickers=[])
        with patch.object(s,'run_bounded_search',return_value={'budget':{'objective_calls':1}}) as mock:
            result=s.calculate_dated_candidate(prepared=prepared,risk_scope=SCOPE)
        self.assertEqual(mock.call_count,1)
        self.assertEqual(result['control_objective_calls'],1)
        self.assertEqual(result['total_candidate_plus_control_objective_calls'],2)
        self.assertEqual(result['original8_control']['original_definition_count'],8)
        self.assertEqual(result['total_objective_limit'],311297)


if __name__=='__main__':unittest.main()
