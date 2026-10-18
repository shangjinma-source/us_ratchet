from copy import deepcopy
from datetime import date,timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_first_period_incumbent_cash_flow_paths_20261003 as w


def fixture():
    days=[];day=date(2023,3,31)
    while day<=date(2023,9,1):
        if day.weekday()<5 and str(day) not in ('2023-04-07','2023-05-29','2023-06-19','2023-07-04'):days.append(str(day))
        day+=timedelta(days=1)
    targets={s:dict(ticker=s,issuer_id=s,target_weight=.125) for s in 'ABCDEFGH'}
    risk=dict(zip(('max_single_weight','min_single_weight','top_weight_cap','minimum_effective_n_ratio','risk_chain_top1_cap'),(.45,.05,.8,.7,.55)))
    clocks=[('2023-03-31','2023-04-03'),('2023-04-28','2023-05-01'),('2023-05-31','2023-06-01'),('2023-06-30','2023-07-03'),('2023-07-31','2023-08-01'),('2023-08-31','2023-09-01')]
    schedule=[dict(decision_date=d,execution_date=e,targets=deepcopy(targets)) for d,e in clocks]
    baseline=dict(session=days[0],cash_usd=25000.0,shares={},prices={})
    nominal=dict(schema='ndx_incumbent_nominal_control_research_v1',original_risk_parameters=risk,
        execution=dict(schema='ndx_dynamic_frozen_incumbent_control_v1',daily=[baseline],decisions=[dict(decision_date=days[0],desired_shares={**dict.fromkeys(targets,311),'H':310},delta={**dict.fromkeys(targets,311),'H':310})]),
        original_fixed_schedule=dict(schedule=schedule,calendar=days,transaction_cost_bps=10.0,minimum_cash_buffer_usd=100.0,risk_chains_by_decision={d:dict(zip(targets,targets)) for d,e in clocks}),
        nominal_quotes={'by_ticker':{s:{'rows':[dict(session=d,ticker=s,currency='USD',nominal_open=10.0,nominal_close=10.0) for d in days]} for s in targets}},
        **dict.fromkeys(('point_in_time_verified','promotion_allowed','dividends_modelled','price_identity_binding_verified','risk_is_order_gate'),False))
    refs={k:dict(path=k+'.json',sha256='a'*64) for k in ('inputs','nominal','candidates')}
    rows=[];candidate_rows=[]
    for lane in w.LANES:
        for amount in ('1000','10000'):
            i=len(rows);sid='|'.join((lane,days[0],days[1],amount))
            row=dict(scenario_id=sid,lane=lane,holdings={},starting_cash_usd='25000.0',cash_event=dict(decision_date=days[0],execution_date=days[1],amount_usd=amount),transaction_cost_bps='10',minimum_cash_buffer_usd='100',risk_parameters={k:str(v) for k,v in risk.items()},original_inventory_row={'baseline':deepcopy(baseline)},gaps=[lane],target_weights={lane:'1'},**dict.fromkeys(('point_in_time_verified','orders_executed','promotion_allowed','fork_executable'),False))
            rows.append(row)
            candidate_rows.append(dict(scenario_id=sid,input_row=deepcopy(row),input_reference=w.pointer(refs['inputs'],f'/rows/{i}'),accounting_inputs=dict(initial=dict(session=days[0],cash_usd='25000.0',holdings={},close_prices={}),sessions=[dict(session=d,cash_injection_usd=amount if j==0 else '0') for j,d in enumerate(days[1:])],transaction_cost_bps='10')))
    flags=dict.fromkeys(('point_in_time_verified','orders_executed','promotion_allowed'),False)
    inputs=dict(schema='FIRST_PERIOD_STANDARD_CASH_INPUTS_V1',rows=rows,source_hashes={},**flags)
    candidates=dict(schema='FIRST_PERIOD_CASH_FIXED_BUY_HOLD_PRICE_ONLY_TWR_V1',scenario_count=8,rows=candidate_rows,observed_calendar=days,**flags)
    return inputs,nominal,candidates,refs


class Tests(unittest.TestCase):
    def test_two_new_paths_no_prior_close_use_of_future_cash(self):
        from backtest.ndx_incumbent_cash_flow_research import simulate_incumbent_cash_flow
        args=fixture();before=deepcopy(args);calls=[]
        def simulate(**kwargs):calls.append(kwargs);return simulate_incumbent_cash_flow(**kwargs)
        result=w.assemble(*args,simulate)
        self.assertEqual(len(calls),2);self.assertEqual(len(result['scenario_mappings']),8)
        self.assertEqual(sum(len(p['account']['daily']) for p in result['paths']),212)
        self.assertEqual(sum(len(p['account']['decisions']) for p in result['paths']),12)
        for p in result['paths']:
            a=p['account'];self.assertEqual(a['decisions'][0]['desired_shares'],{**dict.fromkeys('ABCDEFGH',311),'H':310})
            self.assertFalse(a['decisions'][0]['future_open_flow_included_in_plan'])
            self.assertEqual(a['original_fixed_weights'],dict.fromkeys('ABCDEFGH','0.125'))
            self.assertFalse(a['weights_normalized']);self.assertFalse(a['open_replan_performed'])
        self.assertNotEqual(result['paths'][0]['account']['decisions'][1]['desired_shares'],result['paths'][1]['account']['decisions'][1]['desired_shares'])
        self.assertEqual(args,before)

    def test_empty_baseline_expands_quotes_not_holdings_or_capital(self):
        inputs,nominal,_,refs=fixture();p=w.prepare_path(inputs['rows'][0],nominal,refs['nominal']);initial=p['core_inputs']['initial']
        self.assertEqual(initial['holdings'],{});self.assertEqual(initial['cash_usd'],'25000.0');self.assertEqual(len(initial['close_prices']),8)
        self.assertEqual(len(p['core_inputs']['sessions']),106);self.assertEqual(len(p['core_inputs']['schedule']),6)
        self.assertEqual(len(p['quote_evidence']),213)
        self.assertEqual(p['core_inputs']['sessions'][0]['cash_injection_usd'],'1000')
        self.assertTrue(all(x['cash_injection_usd']=='0' for x in p['core_inputs']['sessions'][1:]))

    def test_lane_difference_mapping_preserved_and_shared_input_drift_rejected(self):
        inputs,nominal,candidates,refs=fixture();self.assertEqual(len(w.grouped_rows(inputs)),2)
        inputs['rows'][2]['starting_cash_usd']='26000'
        with self.assertRaises(ValueError):w.grouped_rows(inputs)
        inputs,nominal,candidates,refs=fixture();candidates['rows'][0]['input_row']['gaps']=[]
        with self.assertRaises(ValueError):w.validate_candidates(inputs,candidates,nominal,refs)

    def test_wrong_flow_calendar_context_and_saved_first_plan_rejected(self):
        from backtest.ndx_incumbent_cash_flow_research import simulate_incumbent_cash_flow
        for attack in ('flow','calendar','risk','firstplan'):
            inputs,nominal,candidates,refs=fixture()
            if attack=='flow':candidates['rows'][0]['accounting_inputs']['sessions'][1]['cash_injection_usd']='1000'
            elif attack=='calendar':candidates['observed_calendar']=candidates['observed_calendar'][1:]
            elif attack=='risk':nominal['original_fixed_schedule']['risk_chains_by_decision']['2023-04-28']['A']='changed'
            else:nominal['execution']['decisions'][0]['desired_shares']['A']=999
            with self.subTest(attack=attack),self.assertRaises(ValueError):w.assemble(inputs,nominal,candidates,refs,simulate_incumbent_cash_flow)

    def test_existing_namespace_rejects_before_source_read(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(w,'OUTPUT',Path(tmp)),patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):w.run(execute=True)
            read.assert_not_called()


if __name__=='__main__':unittest.main()
