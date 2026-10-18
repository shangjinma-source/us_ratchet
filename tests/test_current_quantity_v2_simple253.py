import unittest
import json
from pathlib import Path
from copy import deepcopy
from datetime import date,timedelta
from fractions import Fraction as F
from backtest.current_quantity_v2_simple253 import select_simple253, make_simple_decider
from data.current_research_capital_decision_v2 import decide_quantity_v2_for_account, REQUIRED_PINS


def fixture():
    days=[];day=date(2024,1,1)
    while len(days)<253:
        if day.weekday()<5:days.append(day.isoformat())
        day+=timedelta(days=1)
    series={'A':[F(60)]*21+[F(120)]*21+[F(60)]*211,'B':[F(60)]*252+[F(63)]}
    metadata={s:dict(ticker=s,issuer_id=s) for s in series}
    window=dict(decision_cutoff=days[-1],training_dates=days,candidates=[dict(security_id=s,**metadata[s],status='READY_CONDITIONAL',training_close=list(map(str,values)),decision_cost=str(values[-1])) for s,values in series.items()])
    args=dict(prices={s:str(values[-1]) for s,values in series.items()},metadata=metadata,entered_cash='100',fee_bps='0',minimum_cash_buffer='0',decision_date=days[-1],scenario_dates=days[21::21],training_scenarios=[{s:str(values[i+21]/values[i]) for s,values in series.items()} for i in range(0,252,21)],max_objective_evaluations=128,fixed_seed='test')
    return window,args,days


class Simple253Tests(unittest.TestCase):
    def test_endpoint_and_residual_not_v2_equivalent(self):
        w,a,days=fixture();simple=select_simple253(window=w,calendar=days,arguments=a)
        self.assertEqual(simple['selected']['quantities'],{'B':1});self.assertEqual(simple['selected']['residual_cash'],'37')
        common=dict(decision_date=days[-1],account_state=dict(asof=days[-1],revision='test',cash='100',shares={},reserved_cash='0'),
            valuation_quotes=[dict(security_id=s,price=p,as_of=days[-1],price_basis='TEST',source_references=['quote']) for s,p in a['prices'].items()],
            search_arguments=dict(a,quote_as_of=days[-1],price_basis='TEST'),
            source_hashes={p:'a'*64 for p in (*REQUIRED_PINS,'quote','backtest/return_priority_fresh_cash_quantity_search.py')})
        v2=decide_quantity_v2_for_account(**common)
        self.assertEqual(v2['target_quantities'],{'A':1})
        self.assertEqual(F('2')*F('1/2'),1)
        self.assertEqual((F('2/5')+F('3/5')*2)*(F('2/5')+F('3/5')/2),F('28/25'))
        bound=make_simple_decider(training_windows=[w])(**common)
        self.assertEqual(bound['target_quantities'],{'B':1});self.assertEqual(bound['core_calls'],0)

    def test_ties_affordability_and_negative_momentum(self):
        w,a,days=fixture()
        # Both stocks declining identically, no implicit positive-momentum hurdle.
        for row in w['candidates']:row['training_close']=['120']*252+['60'];row['decision_cost']='60'
        a['prices']={'A':'60','B':'60'};a['training_scenarios']=[{'A':'1','B':'1'}]*11+[{'A':'1/2','B':'1/2'}]
        self.assertEqual(select_simple253(window=w,calendar=days,arguments=a)['winner'],'A')
        a['entered_cash']='59'
        self.assertEqual(select_simple253(window=w,calendar=days,arguments=a)['selected']['quantities'],{})
        w,a,days=fixture();a['entered_cash']='60'
        self.assertEqual(select_simple253(window=w,calendar=days,arguments=a)['winner'],'A')

    def test_missing_boundary_domain_and_future_training_rejected(self):
        w,a,days=fixture()
        for mutation in ('gap','domain','future','scenario'):
            ww,aa=deepcopy(w),deepcopy(a)
            if mutation=='gap':ww['training_dates'][4]=ww['training_dates'][3]
            if mutation=='domain':ww['candidates'].pop()
            if mutation=='future':ww['training_dates'][-1]='2099-01-01'
            if mutation=='scenario':aa['training_scenarios'][0]['A']='3'
            with self.assertRaises(ValueError):select_simple253(window=ww,calendar=days,arguments=aa)

    def test_real_tiny_next_open_and_final_audit(self):
        from backtest.return_priority_monthly_execution_inputs_v4 import assemble_monthly_execution_inputs_v4
        from backtest.current_quantity_v2_simple253_next_open import run_simple253_next_open
        p=json.loads(Path('tmp/next12_execution_prepare_20261014_v3/prepared.json').read_text(encoding='utf-8'))
        t=json.loads(Path('tmp/next12_training_prepare_20261014_v1/prepared.json').read_text(encoding='utf-8'))
        a=assemble_monthly_execution_inputs_v4(p)
        a['session_dates']=a['session_dates'][:2];a['monthly_inputs']=a['monthly_inputs'][:1]
        args=a['monthly_inputs'][0]['search_arguments'];sid=sorted(args['prices'])[0]
        args['prices']={sid:args['prices'][sid]};args['metadata']={sid:args['metadata'][sid]}
        args['training_scenarios']=[{sid:x[sid]} for x in args['training_scenarios']]
        tw=deepcopy(t['windows'][0]);tw['candidates']=[row for row in tw['candidates'] if row['security_id']==sid]
        common=dict(assembled=a,training_windows=[tw],initial_cash='2000',fee_bps='0',slippage_bps='0')
        first=run_simple253_next_open(**common,ohlc=p['ohlc'])
        changed=deepcopy(p['ohlc']);changed[sid][a['session_dates'][1]]=dict.fromkeys(['open','high','low','close'],'100000')
        second=run_simple253_next_open(**common,ohlc=changed)
        self.assertEqual(first['status'],'COMPLETE');self.assertEqual(second['status'],'COMPLETE')
        self.assertEqual(first['provider_audit'][0],second['provider_audit'][0])
        self.assertGreaterEqual(F(second['cash']),0)
        self.assertTrue(any(row['event']=='UNFILLED_CASH_RATIONED_INTEGER_FLOOR' for row in second['order_log']))

if __name__=='__main__':unittest.main()
