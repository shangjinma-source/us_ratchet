from copy import deepcopy
from datetime import date,timedelta
import unittest
from scripts import ndx_incumbent_cash_flow_paths_20261002 as module


def fixture():
    days=[]; day=date(2023,3,31)
    while day<=date(2023,9,1):
        if day.weekday()<5 and str(day) not in ('2023-04-07','2023-05-29','2023-06-19','2023-07-04'): days.append(str(day))
        day+=timedelta(days=1)
    targets={sid:{'ticker':sid,'issuer_id':sid,'target_weight':.125} for sid in 'ABCDEFGH'}
    risk={'max_single_weight':.45,'min_single_weight':.05,'top_weight_cap':.8,'minimum_effective_n_ratio':.7,'risk_chain_top1_cap':.55}
    schedule=[{'decision_date':d,'execution_date':e,'targets':deepcopy(targets)} for d,e in [('2023-03-31','2023-04-03')]+[(d,e) for d,e,n in module.CLOCKS]]
    daily=[{'session':day,'cash_usd':100.0,'shares':dict.fromkeys(targets,10)} for day in days]
    nominal=dict(schema='ndx_incumbent_nominal_control_research_v1',original_risk_parameters=risk,
        execution={'schema':'ndx_dynamic_frozen_incumbent_control_v1','daily':daily,
            'decisions':[dict(decision_date=item['decision_date'],desired_shares=dict.fromkeys(targets,10),delta=dict.fromkeys(targets,0)) for item in schedule]},
        original_fixed_schedule={'schedule':schedule,'calendar':days,'transaction_cost_bps':10.0,'minimum_cash_buffer_usd':100.0,
            'risk_chains_by_decision':{item['decision_date']:dict(zip(targets,targets)) for item in schedule}},
        nominal_quotes={'by_ticker':{sid:{'rows':[dict(session=day,ticker=sid,currency='USD',nominal_open=10.0,nominal_close=10.0) for day in days]} for sid in targets}},
        **dict.fromkeys(('point_in_time_verified','promotion_allowed','dividends_modelled','price_identity_binding_verified','risk_is_order_gate'),False))
    rows=[]
    for lane in module.LANES:
        for d,e,n in module.CLOCKS:
            for amount in ('1000','10000'):
                baseline=deepcopy(next(item for item in daily if item['session']==d))
                rows.append(dict(scenario_id='|'.join((lane,d,e,amount)),lane=lane,branch_role='MAIN_LANE',
                    holdings=dict.fromkeys(targets,10),starting_cash_usd='100.0',cash_event={'decision_date':d,'execution_date':e,'amount_usd':amount},
                    transaction_cost_bps='10',minimum_cash_buffer_usd='100',risk_parameters={key:str(value) for key,value in risk.items()},
                    securities={sid:{'ticker':sid,'issuer_id':sid} for sid in targets},original_inventory_row={'baseline':baseline},gaps=[lane]))
    rows += [dict(branch_role='CONTROL') for _ in range(24)]
    return {'schema':'REMAINING_STANDARD_CASH_INPUTS_V1','rows':rows,'source_hashes':{}},nominal


class IncumbentPathTests(unittest.TestCase):
    def test_full_synthetic_assembly_uses_ten_independent_paths(self):
        from backtest.ndx_incumbent_cash_flow_research import simulate_incumbent_cash_flow
        inputs,nominal=fixture(); calls=[]
        def counted(**kwargs):
            calls.append(kwargs)
            return simulate_incumbent_cash_flow(**kwargs)
        result=module.assemble(inputs,nominal,{'nominal':{},'inputs':{}},counted)
        self.assertEqual(len(calls),10); self.assertEqual(len(result['scenario_mappings']),40)
        self.assertEqual(sum(len(path['account']['daily']) for path in result['paths']),442)
        self.assertEqual(sum(len(path['account']['decisions']) for path in result['paths']),30)
        first=result['paths'][0]['account']
        self.assertEqual(first['daily'][0]['holdings_after'],dict.fromkeys('ABCDEFGH',10))
        self.assertTrue(any(row['signed_share_delta']>0 for row in first['trades']))

    def test_only_exact_control_inputs_deduplicate(self):
        inputs,_=fixture(); groups=module.grouped_rows(inputs)
        self.assertEqual(len(groups),10)
        self.assertTrue(all(len(rows)==4 for rows in groups.values()))
        inputs['rows'][10]['starting_cash_usd']='101'
        with self.assertRaisesRegex(ValueError,'inputs differ'):
            module.grouped_rows(inputs)

    def test_complete_window_schedule_and_actual_source_quotes(self):
        inputs,nominal=fixture(); before=deepcopy(inputs['rows'][0])
        result=module.prepare_path(inputs['rows'][0],nominal,{'path':'synthetic','sha256':'a'*64})
        core=result['core_inputs']
        self.assertEqual(len(core['sessions']),87); self.assertEqual(len(core['schedule']),5)
        self.assertEqual(core['fixed_weights'],dict.fromkeys('ABCDEFGH','0.125'))
        self.assertEqual(core['sessions'][0]['cash_injection_usd'],'1000')
        self.assertTrue(all(item['cash_injection_usd']=='0' for item in core['sessions'][1:]))
        self.assertEqual(len(result['quote_evidence']),175)
        self.assertEqual(before,inputs['rows'][0])

    def test_reject_next_close_schema_changed_risk_or_wrong_baseline(self):
        for mutation in ('schema','risk','baseline'):
            inputs,nominal=fixture()
            if mutation=='schema': nominal['execution']['schema']='OLD_NEXT_CLOSE'
            if mutation=='risk': nominal['original_fixed_schedule']['risk_chains_by_decision']['2023-05-31']['A']='different'
            if mutation=='baseline': inputs['rows'][0]['original_inventory_row']['baseline']['cash_usd']=99.0
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                module.prepare_path(inputs['rows'][0],nominal,{'path':'synthetic','sha256':'a'*64})


if __name__=='__main__': unittest.main()
