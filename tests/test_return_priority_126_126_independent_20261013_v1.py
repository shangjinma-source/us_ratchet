"""Fresh synthetic chronology and arithmetic; solver always mocked, no real bulk IO."""
from pathlib import Path
import sys,hashlib,importlib.util,unittest
from unittest.mock import patch
from datetime import date,timedelta
from copy import deepcopy
from fractions import Fraction as F
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));SOURCE=ROOT/'backtest/ndx_return_priority_126_126_counterexample_research.py'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()=='956ace11fbd12fdacfed5106a7afb755281f2e76a0cfa1755ad033d57de3487c'
spec=importlib.util.spec_from_file_location('independent126',SOURCE);s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)


def fixture():
    days=['2025-09-18']+[(date(2025,9,19)+timedelta(days=i)).isoformat()for i in range(125)]+['2026-03-20']+[(date(2026,3,21)+timedelta(days=i)).isoformat()for i in range(125)]+['2026-09-21']
    securities=[dict(security_id=f'N{i}',issuer_id=f'U{i if i<76 else 75}',ticker=f'B{i}',risk_chain=f'R{i}')for i in range(77)]
    trained=[F(0)]*125+[F(1,10)];held=[F(-1,20)]+[F(0)]*124+[F(2,25)];allreturns=trained+held
    quotes=[];value=F(100)
    for i,d in enumerate(days):
        if i:value*=1+allreturns[i-1]
        quotes.append(dict(session=d,nominal_close=str(value),nominal_close_exact=str(value)))
    returns=[dict(session=days[i+1],previous_session=days[i],dividends_included=False,split_only_return_exact=str(v),split_only_return_float=float(v))for i,v in enumerate(allreturns)]
    rows=[]
    for security in securities:
        channel=dict(status='CONDITIONAL_NUMERIC_RESULT',ticker=security['ticker'],quote_rows=deepcopy(quotes),return_rows=deepcopy(returns),training_returns=deepcopy(returns[:126]),evaluation_returns=deepcopy(returns[126:]))
        rows.append(dict(coordinate=deepcopy(security),channel=channel))
    bulk=dict(calendar253=days,training_return_count=126,evaluation_return_count=126,security_count=77,issuer_count=76,observed_security_count=101,point_in_time_verified=False,future_independent_oos=False,evaluation_interval_previously_used_for_fitting=True,rows=rows,conditional_numeric_channel_count=77,blocked_price_channel_count=0,original_identity_assumed_window={'first':'2026-03-20'})
    original=[dict(row,target_weight=.125)for row in securities[:7]]+[dict(security_id='TSMCONTROL',issuer_id='TSMI',ticker='TSM',risk_chain='foundry',target_weight=.125)]
    prepared=dict(securities=securities,original8_definition=original,observed_provenance=[dict(ticker=f'OBS{i}')for i in range(101)],source_bindings={},source_checks=[],policy=dict(max_single_weight=.45,min_single_weight=.05,top_three_cap=.8,min_neff_ratio=.7,chain_cap=.55),plan=dict(cash_usd=20000,fee_bps=10,research_buffer_usd=100,finite_budgets=dict(support_proposals_per_k=64,objective_evaluations_per_support=64,integer_deployment_proposals_per_support=128,global_objective_evaluations=311296,global_integer_deployment_proposals=622592)))
    tsm=dict(quotes=[dict(session=d,nominal_close=110.)for d in days[126:]],returns=[dict(session=d,price_return=0.)for d in days[127:]])
    return prepared,bulk,tsm


def check_path(test,row,prices,returns,metric):
    amounts={sid:F(q)*F(str(prices[sid]))for sid,q in row['quantities'].items()};gross=sum(amounts.values(),F(0));fee=gross/1000;cash=20000-gross-fee;path=[F(20000),cash+gross]
    for i in range(126):
        for sid in amounts:amounts[sid]*=1+F(str(returns[sid][i]))
        path.append(cash+sum(amounts.values(),F(0)))
    peak=F(20000);dd=F(0)
    for w in path:peak=max(peak,w);dd=max(dd,1-w/peak)
    test.assertEqual(len(row['net_wealth_path']),128)
    for observed,want in zip(row['net_wealth_path'],path):test.assertAlmostEqual(observed,float(want),places=8)
    test.assertAlmostEqual(row[metric]['cagr'],float((path[-1]/20000)**2-1),places=11);test.assertAlmostEqual(row[metric]['maximum_drawdown'],float(dd),places=11)
    test.assertAlmostEqual(row['fees'],float(fee));test.assertAlmostEqual(row['remaining_cash'],float(cash));test.assertAlmostEqual(row['reconciliation_total'],20000)


class Independent126(unittest.TestCase):
    def test_all128_training_evaluation_and_control_values_fixedq_fees(self):
        p,b,t=fixture();sl=s.prepare_chronology(prepared=p,bulk=b,tsm=t);q=dict(N0=38,N1=41,N2=45,N3=48);budget=s.Budget(1,0)
        training=s.evaluate_allocation(quantities=q,initial_prices=sl['target_prices'],returns=sl['train_returns'],metadata={r['security_id']:r for r in p['securities']},policy=p['policy'],cash=20000,fee_bps=10,buffer=100,budget=budget,enforce_risk=True,risk_scope=s.RISK_SCOPE)
        selection=dict(co_winners=[training],budget=dict(objective_calls=1,integer_proposals=1))
        with patch.object(s,'run_bounded_search',return_value=selection):out=s.calculate_counterexample(prepared=p,sliced=sl)
        check_path(self,training,sl['target_prices'],sl['train_returns'],'training_metrics');after=out['heldout_evaluations'][0];self.assertEqual(after['quantities'],q);check_path(self,after,sl['target_prices'],sl['heldout_returns'],'historical_evaluation_metrics')
        control=out['original8_heldout_control'];prices={sid:r['target_price']for sid,r in sl['control'].items()};returns={sid:r['evaluation_returns']for sid,r in sl['control'].items()};check_path(self,control,prices,returns,'historical_evaluation_metrics')
        self.assertEqual(control['metric_calls'],1);self.assertEqual(len(control['all_eight_target_quantities']),8);self.assertEqual(out['budgets']['total_objective_calls'],3);self.assertFalse(control['candidate_risk_gate_imposed'])

    def test_future126_cannot_change_solver_arguments_or_frozenq(self):
        p,b,t=fixture();first=s.prepare_chronology(prepared=p,bulk=b,tsm=t);changed=deepcopy(b)
        for row in changed['rows']:
            ch=row['channel']
            for r in ch['return_rows'][126:]:r['split_only_return_exact']='1/20';r['split_only_return_float']=.05
            ch['evaluation_returns']=deepcopy(ch['return_rows'][126:]);ch['quote_rows'][-1].update(nominal_close='99999',nominal_close_exact='99999')
        second=s.prepare_chronology(prepared=p,bulk=changed,tsm=t);seen=[];q={f'N{i}':40 for i in range(4)}
        def solver(**kw):
            seen.append(deepcopy(kw));self.assertEqual(kw['returns'],first['train_returns']);self.assertEqual(kw['target_prices'],first['target_prices']);self.assertEqual(kw['cutoff'],'2026-03-20');self.assertEqual(kw['seed'],20261013)
            return {'co_winners':[{'quantities':q}],'budget':{'objective_calls':1,'integer_proposals':1}}
        with patch.object(s,'run_bounded_search',side_effect=solver):a=s.calculate_counterexample(prepared=p,sliced=first)
        with patch.object(s,'run_bounded_search',side_effect=solver):z=s.calculate_counterexample(prepared=p,sliced=second)
        self.assertEqual(seen[0],seen[1]);self.assertEqual(a['frozen_training_co_winners'],z['frozen_training_co_winners']);self.assertNotEqual(a['heldout_evaluations'][0]['historical_evaluation_metrics'],z['heldout_evaluations'][0]['historical_evaluation_metrics'])
        self.assertEqual(len(a['full_conditional_inventory']),77);self.assertEqual(len({r['issuer_id']for r in a['full_conditional_inventory']}),76);self.assertEqual(len(a['all101_observed_provenance']),101);self.assertNotIn('TSM',{r['ticker']for r in a['full_conditional_inventory']});self.assertFalse(a['parameters_changed']);self.assertFalse(a['fresh_future_oos'])

    def test_missing_boundaries_or_restatement_reject_before_search(self):
        for mutation in ('count','duplicate','exact','split','tsm'):
            p,b,t=fixture()
            if mutation=='count':b['rows'].pop()
            if mutation=='duplicate':b['rows'][-1]['coordinate']=deepcopy(b['rows'][0]['coordinate'])
            if mutation=='exact':b['rows'][1]['channel']['quote_rows'][126]['nominal_close_exact']='-1'
            if mutation=='split':b['rows'][1]['channel']['return_rows'][0]['split_only_return_float']=.2;b['rows'][1]['channel']['training_returns'][0]['split_only_return_float']=.2
            if mutation=='tsm':t['returns'].pop()
            with patch.object(s,'run_bounded_search',side_effect=AssertionError('Unexpected search')),self.assertRaises(ValueError):s.prepare_chronology(prepared=p,bulk=b,tsm=t)


if __name__=='__main__':unittest.main()
