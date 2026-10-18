"""Fresh bounded chronology and heldout money checks; actual search always mocked."""
from pathlib import Path
import hashlib, importlib.util,sys,unittest
from unittest.mock import patch
from datetime import date,timedelta
from fractions import Fraction as F
from copy import deepcopy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
SOURCE=ROOT/'backtest/ndx_return_priority_historical_counterexample_research.py'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()=='b8046880dde1d79b2deb789db608961e60b39215c56ed765646fb724cc4f0859'
spec=importlib.util.spec_from_file_location('independent84_42',SOURCE);s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)


def fixture():
    days=[(date(2026,1,1)+timedelta(days=i)).isoformat()for i in range(127)]
    securities=[dict(security_id=f'Z{i}',ticker=f'T{i}',issuer_id=f'I{i}',risk_chain=f'C{i}')for i in range(7)]
    definitions=[dict(row,target_weight=.125)for row in securities]+[dict(security_id='TSM_CONTROL',ticker='TSM',issuer_id='I7',risk_chain='C7',target_weight=.125)]
    panel={'nominal_close':{'index':days,'columns':[r['ticker']for r in securities],'data':[[100+.5*t+i for i in range(7)]for t in range(127)]}}
    returns={r['security_id']:[.001+i*.00001]*84+[-.01]+[.002]*41 for i,r in enumerate(securities)}
    prepared=dict(securities=securities,initial_prices={r['security_id']:100+i for i,r in enumerate(securities)},returns=returns,return_dates=days[1:],initial_price_date=days[0],cutoff=days[-1],original8_definition=definitions,
        plan=dict(cash_usd=20000,fee_bps=10,research_buffer_usd=100,finite_budgets=dict(support_proposals_per_k=1,objective_evaluations_per_support=4,integer_deployment_proposals_per_support=4,global_objective_evaluations=311296,global_integer_deployment_proposals=622592)),
        policy=dict(max_single_weight=.45,min_single_weight=.05,top_three_cap=.8,min_neff_ratio=.7,chain_cap=.55),observed_provenance=[],source_bindings={},source_checks=[])
    sidecar=dict(quotes=[dict(session=d,nominal_close=150+t*.25)for t,d in enumerate(days)],returns=[dict(session=d,price_return=.001)for d in days[1:]])
    return prepared,panel,sidecar


def independent_path(q,prices,returns):
    amounts={sid:F(qty)*F(str(prices[sid]))for sid,qty in q.items()};gross=sum(amounts.values(),F(0));fee=gross/1000;idle=20000-gross-fee;path=[F(20000),idle+gross]
    for i in range(len(next(iter(returns.values())))):
        for sid in amounts:amounts[sid]*=1+F(str(returns[sid][i]))
        path.append(idle+sum(amounts.values(),F(0)))
    peak=F(20000);dd=F(0)
    for w in path:peak=max(peak,w);dd=max(dd,1-w/peak)
    return path,fee,idle,dd


class IndependentChronology(unittest.TestCase):
    def test_training84_target_notionals_backcast_cagr3(self):
        p,panel,tsm=fixture();sl=s.chronology_inputs(prepared=p,panel=panel,tsm_sidecar=tsm)
        q={f'Z{i}':20 for i in range(4)};budget=s.Budget(1,0)
        row=s.evaluate_allocation(quantities=q,initial_prices=sl['target_prices'],returns=sl['train_returns'],metadata={r['security_id']:r for r in p['securities']},policy=p['policy'],cash=20000,fee_bps=10,buffer=100,budget=budget,enforce_risk=True,risk_scope=s.RISK_SCOPE)
        path,fee,idle,dd=independent_path(q,sl['target_prices'],sl['train_returns'])
        self.assertEqual(len(row['net_wealth_path']),86)
        for observed,want in zip(row['net_wealth_path'],path):self.assertAlmostEqual(observed,float(want),places=8)
        self.assertAlmostEqual(row['training_metrics']['cagr'],float((path[-1]/20000)**3-1),places=11)
        self.assertAlmostEqual(row['training_metrics']['maximum_drawdown'],float(dd),places=11)
        self.assertEqual(budget.objective_calls,1)

    def test_no_heldout_price_return_or_metric_reaches_solver(self):
        p,panel,tsm=fixture();sl=s.chronology_inputs(prepared=p,panel=panel,tsm_sidecar=tsm)
        seen=[];q={f'Z{i}':20 for i in range(4)}
        def select(**kw):
            seen.append(deepcopy(kw));self.assertEqual(kw['returns'],sl['train_returns']);self.assertEqual(kw['target_prices'],sl['target_prices'])
            self.assertEqual(len(kw['return_dates']),84);self.assertEqual(kw['cutoff'],panel['nominal_close']['index'][84]);self.assertNotIn('heldout_returns',kw)
            return {'co_winners':[{'quantities':q}], 'budget':{'objective_calls':1,'integer_proposals':1}}
        with patch.object(s,'run_bounded_search',side_effect=select):r=s.calculate_counterexample(prepared=p,sliced=sl)
        changed=deepcopy(sl)
        changed['heldout_returns']={sid:[.05]*42 for sid in changed['heldout_returns']}
        for channel in changed['control'].values():channel['evaluation_returns']=[.04]*42
        with patch.object(s,'run_bounded_search',side_effect=select):r2=s.calculate_counterexample(prepared=p,sliced=changed)
        self.assertEqual(seen[0],seen[1]);self.assertEqual(r['frozen_training_co_winners'],r2['frozen_training_co_winners'])
        self.assertNotEqual(r['heldout_evaluations'][0]['historical_evaluation_metrics'],r2['heldout_evaluations'][0]['historical_evaluation_metrics'])
        self.assertEqual(r['budgets']['total_objective_calls'],3)
        self.assertFalse(r['fresh_future_oos']);self.assertFalse(r['full_point_in_time_qualification'])

    def test_fixed_quantities_42_netpath_fee_cash_cagr6_and_control(self):
        p,panel,tsm=fixture();sl=s.chronology_inputs(prepared=p,panel=panel,tsm_sidecar=tsm)
        q={f'Z{i}':20 for i in range(4)};saved={'co_winners':[{'quantities':deepcopy(q)}],'budget':{'objective_calls':1,'integer_proposals':1}}
        with patch.object(s,'run_bounded_search',return_value=saved):r=s.calculate_counterexample(prepared=p,sliced=sl)
        candidate=r['heldout_evaluations'][0];path,fee,idle,dd=independent_path(q,sl['target_prices'],sl['heldout_returns'])
        self.assertEqual(candidate['quantities'],q);self.assertEqual(saved['co_winners'][0]['quantities'],q)
        self.assertEqual(len(candidate['net_wealth_path']),44)
        for observed,want in zip(candidate['net_wealth_path'],path):self.assertAlmostEqual(observed,float(want),places=8)
        self.assertAlmostEqual(candidate['fees'],float(fee));self.assertAlmostEqual(candidate['remaining_cash'],float(idle))
        self.assertAlmostEqual(candidate['historical_evaluation_metrics']['cagr'],float((path[-1]/20000)**6-1),places=11)
        self.assertAlmostEqual(candidate['historical_evaluation_metrics']['maximum_drawdown'],float(dd),places=11)
        control=r['original8_heldout_control'];cp={sid:x['target_price']for sid,x in sl['control'].items()};cr={sid:x['evaluation_returns']for sid,x in sl['control'].items()}
        cpath,cfee,cidle,cdd=independent_path(control['quantities'],cp,cr)
        for observed,want in zip(control['net_wealth_path'],cpath):self.assertAlmostEqual(observed,float(want),places=8)
        self.assertAlmostEqual(control['historical_evaluation_metrics']['cagr'],float((cpath[-1]/20000)**6-1),places=11)
        self.assertEqual(len(control['all_eight_target_quantities']),8);self.assertEqual(control['metric_calls'],1)
        self.assertFalse(control['candidate_risk_gate_imposed'])

    def test_bad_boundaries_refuse_not_silently_drop_or_overlap(self):
        for mutation in ('close','tsm','returns'):
            p,panel,tsm=fixture()
            if mutation=='close':panel['nominal_close']['index'][84]=panel['nominal_close']['index'][83]
            if mutation=='tsm':tsm['returns'][84]['session']=tsm['returns'][83]['session']
            if mutation=='returns':p['returns']['Z1'].pop()
            with self.assertRaises(ValueError):s.chronology_inputs(prepared=p,panel=panel,tsm_sidecar=tsm)


if __name__=='__main__':unittest.main()
