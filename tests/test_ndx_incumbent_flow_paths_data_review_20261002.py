import unittest
from copy import deepcopy
from unittest.mock import Mock,patch
from scripts import ndx_incumbent_cash_flow_paths_20261002 as m

def grouped_fixture():
    rows=[]
    for lane in m.LANES:
        for day,exe,_ in m.CLOCKS:
            for amount in ('1000','10000'):
                rows.append({'scenario_id':lane+day+amount,'branch_role':'MAIN_LANE','lane':lane,'holdings':{'A':1},'starting_cash_usd':'100.0','cash_event':{'decision_date':day,'execution_date':exe,'amount_usd':amount},'transaction_cost_bps':'10.0','minimum_cash_buffer_usd':'100.0','risk_parameters':{},'original_inventory_row':{'baseline':{'day':day}},'target_weights':{lane:'1'},'gaps':[lane]})
    return {'schema':'REMAINING_STANDARD_CASH_INPUTS_V1','rows':rows+[{'branch_role':'CONTROL'} for _ in range(24)],'source_hashes':{}}

def prepare_fixture():
    day,exe='2023-08-31','2023-09-01';sids=list('ABCDEFGH');hold={s:1 for s in sids};risk={'min_single_weight':.05};target={s:{'ticker':s,'issuer_id':s,'target_weight':.125} for s in sids};base={'session':day,'shares':hold,'cash_usd':100.0};labels={s:'chain'+s for s in sids}
    row={'holdings':hold,'securities':target,'risk_parameters':{'min_single_weight':'0.05'},'starting_cash_usd':'100.0','transaction_cost_bps':'10.0','minimum_cash_buffer_usd':'100.0','cash_event':{'decision_date':day,'execution_date':exe,'amount_usd':'1000'},'original_inventory_row':{'baseline':deepcopy(base)}}
    nominal={'schema':'ndx_incumbent_nominal_control_research_v1',**dict.fromkeys(('point_in_time_verified','promotion_allowed','dividends_modelled','price_identity_binding_verified','risk_is_order_gate'),False),'original_risk_parameters':risk,
     'original_fixed_schedule':{'schedule':[{'decision_date':day,'execution_date':exe,'targets':target}],'calendar':[day,exe],'risk_chains_by_decision':{day:labels},'transaction_cost_bps':10.0,'minimum_cash_buffer_usd':100.0},
     'execution':{'schema':'ndx_dynamic_frozen_incumbent_control_v1','daily':[base],'decisions':[{'decision_date':day,'desired_shares':hold,'delta':dict.fromkeys(sids,0)}]},
     'nominal_quotes':{'by_ticker':{s:{'rows':[{'session':d,'ticker':s,'currency':'USD','nominal_open':12.0,'nominal_close':10.0} for d in (day,exe)]} for s in sids}}}
    return row,nominal

class IndependentTests(unittest.TestCase):
    def test_groups_preserve_lane_differences_but_reject_state_drift(self):
        d=grouped_fixture();g=m.grouped_rows(d);self.assertEqual(len(g),10)
        self.assertEqual(len({r['gaps'][0] for _,r in next(iter(g.values()))}),4)
        d['rows'][10]['starting_cash_usd']='101.0'
        with self.assertRaisesRegex(ValueError,'differ'):m.grouped_rows(d)
    def test_prepare_open_close_flow_and_original_weight(self):
        row,n=prepare_fixture();p=m.prepare_path(row,n,{'path':'synthetic','sha256':'a'*64})
        self.assertEqual(p['core_inputs']['initial']['close_prices']['A'],'10.0')
        self.assertEqual(p['core_inputs']['sessions'][0]['open_prices']['A'],'12.0')
        self.assertNotIn('cash_injection_usd',p['core_inputs']['initial'])
        self.assertEqual(p['core_inputs']['sessions'][0]['cash_injection_usd'],'1000')
        self.assertEqual(p['core_inputs']['fixed_weights']['A'],'0.125')
        n['nominal_quotes']['by_ticker']['A']['rows'][0]['currency']='EUR'
        with self.assertRaisesRegex(ValueError,'USD'):m.prepare_path(row,n,{})
    def test_initial_integer_plan_mismatch_cannot_publish(self):
        d=grouped_fixture();row,n=prepare_fixture();prepared=m.prepare_path(row,n,{'path':'synthetic','sha256':'a'*64})
        simulate=Mock(return_value={'decisions':[{'desired_shares':{},'delta':{}}]})
        with patch.object(m,'prepare_path',return_value=prepared):
            with self.assertRaisesRegex(ValueError,'original saved decision'):m.assemble(d,n,{'nominal':{},'inputs':{}},simulate)
        self.assertEqual(simulate.call_count,1)

if __name__=='__main__':unittest.main()
